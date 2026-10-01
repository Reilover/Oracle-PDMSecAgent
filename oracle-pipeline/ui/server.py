#!/usr/bin/env python3
"""ORACLE UI — FastAPI 后端（BS 架构，论文 §7 Tier-3 人工层演示原型）

职责（任务书 §2，仅三件事）：
  ① 回放/实时读取 audit.jsonl（唯一事实源，append-only）
  ② 人工决策（逐题 approve/veto/改判 + 整窗 confirm + 调 τ/τ_h + 标注）
     写回决策文件并落 audit.jsonl 新事件
  ③ SSE 推送新窗事件

复用管线模块 import（单一事实源，零复制逻辑）：gating / tier0_rules / state_builder。
无数据库 / 无 Redis / 无 Docker / 无 node 构建。纯 CPU。

启动（spark2_5 环境）：
  cd ~/MySecAgent/oracle-pipeline/ui && python3 server.py   # 端口 8024

数据目录约定（都在 ../logs/，红线：只追加不改历史行）：
  audit.jsonl              管线 window_done 事件 + UI 决策事件（human_decision /
                           human_confirm / label / threshold_change）
  windows.json             run_pipeline.py 选窗产物（state/raw_lines/labels 原文）
  ui_runtime.json          UI 运行配置（τ/τ_h 可调值，滑块写这里）
  decisions/               人工决策落盘（按窗 JSON，可被后续管线/训练脚本读取）
  labelled_replays.jsonl   标注导出（P1-6：correct-label 回放反馈实证物）
"""
import asyncio
import datetime
import json
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)                      # oracle-pipeline/
sys.path.insert(0, PIPE)

import gating  # noqa: E402  复用门控/审计（单一事实源）

LOGS = f"{PIPE}/logs"
AUDIT_PATH = f"{LOGS}/audit.jsonl"
WINDOWS_PATH = f"{LOGS}/windows.json"
RUNTIME_PATH = f"{HERE}/ui_runtime.json"
DECISIONS_DIR = f"{HERE}/decisions"
LABELLED_PATH = f"{HERE}/labelled_replays.jsonl"

for d in (LOGS, DECISIONS_DIR):
    os.makedirs(d, exist_ok=True)

app = FastAPI(title="ORACLE Tier-3 Console", docs_url="/api/docs")

# ---------------- 工具 ----------------
TACTICS = ["benign", "reconnaissance", "initial_access", "execution", "persistence",
           "privilege_escalation", "defense_evasion", "credential_access",
           "discovery", "command_and_control", "exfiltration"]
SEVERITIES = ["low", "medium", "high", "critical"]
ACTIONS = ["block_ip", "disable_user", "isolate_host", "reset_credentials",
           "quarantine_message", "monitor", "no_action", "escalate"]
QUESTIONS = ["tactic", "urgent", "severity", "action"]
TAXONOMY = {"tactic": TACTICS, "severity": SEVERITIES, "action": ACTIONS,
            "urgent": ["true", "false"]}


def now_iso():
    return datetime.datetime.now().isoformat(timespec="milliseconds")


def load_runtime():
    if not os.path.exists(RUNTIME_PATH):
        return {"tau": gating.TAU, "tau_h": gating.TAU_H}
    return json.load(open(RUNTIME_PATH))


def save_runtime(rt):
    with open(RUNTIME_PATH, "w") as f:
        json.dump(rt, f, ensure_ascii=False, indent=1)


def read_audit():
    recs = []
    if not os.path.exists(AUDIT_PATH):
        return recs
    with open(AUDIT_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 尾部半行（实时写入中）跳过
    return recs


def load_windows():
    if os.path.exists(WINDOWS_PATH):
        return json.load(open(WINDOWS_PATH))
    return {"pool_sizes": {}, "selected": [], "windows": []}


def evidence_lines(window, route):
    """从 raw_lines 挑证据关键行高亮（Failed password / Invalid user / Accepted /
    4xx / sudo 失败等），供窗详情面板。"""
    keys = ["failed password", "invalid user", "accepted password", "accepted publickey",
            "authentication failure", "pre-auth", "sudo:", "su:", " 404 ", " 403 ",
            " 400 ", " 401 ", " 500 ", " 502 ", " 302 ", "error", "trace",
            "path traversal", "..", "union", "select", "sqlmap", "nikto", "nmap",
            "gobuster", "dirbuster", "hydra", "medusa", "wp-login", "admin",
            "connection closed", "break-in", "reverse mapping", "possible break"]
    hits = []
    for i, ln in enumerate(window.get("raw_lines") or []):
        low = ln.lower()
        if any(k in low for k in keys):
            hits.append({"idx": i, "line": ln})
    return hits[:60]


# ---------------- 数据视图 ----------------

def build_views(tau=None, tau_h=None):
    """构建队列 + 看板视图。tau/tau_h 不传 = 运行配置值（回放重门控时覆盖）。"""
    rt = load_runtime()
    tau = rt["tau"] if tau is None else tau
    tau_h = rt["tau_h"] if tau_h is None else tau_h
    wins = {w["id"]: w for w in load_windows()["windows"]}
    recs = read_audit()

    done = {}          # window_id → 最新 window_done
    decisions = {}     # window_id → 最新人工决策事件
    labels_done = {}   # window_id → 最新标注事件
    other_events = []  # 其余事件（回放时间线用）
    for r in recs:
        ev = r.get("event")
        wid = r.get("window_id")
        if ev == "window_done" and wid:
            done[wid] = r
        elif ev == "human_decision" and wid:
            decisions[wid] = r
        elif ev == "label" and wid:
            labels_done[wid] = r
        if ev not in ("window_done",):
            other_events.append(r)

    queue, replay = [], []
    for wid, w in wins.items():
        d = done.get(wid)
        if not d:
            continue  # 管线未处理完的窗不进回放
        route = d.get("route", {})
        # 回放重门控（τ/τ_h 变更后路由实时变化——M3 验收口径）
        min_conf = None
        confs = {}
        for q, f in route.get("final", {}).items():
            c = f.get("conf")
            if c is not None:
                confs[q] = round(c, 4)
                min_conf = c if min_conf is None else min(min_conf, c)
        needs_human = any(
            (f.get("conf", 0) < tau and f.get("source") != "rule")
            for f in route.get("final", {}).values())
        dec = decisions.get(wid)
        status = "pending"
        if route.get("human"):
            status = "awaiting_decision" if not dec else "decided"
        elif "tier0_rule" in (route.get("path") or []):
            status = "auto_rule"
        elif not needs_human:
            status = "auto"
        item = {
            "window_id": wid,
            "scenario": w.get("scenario"),
            "kind": w.get("kind"),
            "source": w.get("source"),
            "path": route.get("path", []),
            "rule_hit": route.get("rule_hit"),
            "confs": confs,                       # 逐题最终置信度（前端着色）
            "min_conf": round(min_conf, 4) if min_conf is not None else 1.0,
            "needs_human": needs_human,
            "status": status,
            "human": route.get("human"),
            "total_ms": round(d.get("total_ms", 0), 1),
            "ts": d.get("ts"),
            "decision": ({k: dec.get(k) for k in
                          ("ts", "decision", "question_decisions", "note")}
                         if dec else None),
            "label_event": labels_done.get(wid),
        }
        replay.append(item)
        if status in ("awaiting_decision", "decided"):
            queue.append(item)

    # 看板统计（按当前 tau/tau_h 回放重门控）
    path_dist, q_route = {}, {}
    lat_lists = {"state_ms": [], "tier0_ms": [], "tier1_ms": [], "tier2_ms": [],
                 "gate_ms": [], "human_ms": []}
    for wid, d in done.items():
        p = "→".join(d.get("route", {}).get("path", []))
        path_dist[p] = path_dist.get(p, 0) + 1
        for q, f in d.get("route", {}).get("final", {}).items():
            if f.get("source") == "rule":
                key = "rule/adjudicated"
            else:
                key = f"{f.get('source')}/{gating.gate(f.get('conf', 0), tau, tau_h)}"
            q_route[key] = q_route.get(key, 0) + 1
        for k, lst in lat_lists.items():
            v = (d.get("latency_ms") or {}).get(k)
            if v is not None:
                lst.append(v)

    def stats(v):
        if not v:
            return {"n": 0}
        v2 = sorted(v)
        return {"n": len(v), "mean": round(sum(v) / len(v), 1),
                "p50": round(v2[len(v2) // 2], 1), "max": round(v2[-1], 1),
                "p90": round(v2[int(len(v2) * 0.9) - 1 if len(v2) >= 10 else -1], 1),
                "values": [round(x, 1) for x in v2]}  # values 供前端直方图

    return {
        "queue": sorted(queue, key=lambda x: x["ts"]),
        "replay": sorted(replay, key=lambda x: x["ts"]),
        "dashboard": {
            "n_windows": len(done),
            "path_distribution": path_dist,
            "question_route_counts": dict(sorted(q_route.items())),
            "latency_breakdown_ms": {k: stats(v) for k, v in lat_lists.items()},
            "pending": sum(1 for i in queue if i["status"] == "awaiting_decision"),
            "decided": sum(1 for i in queue if i["status"] == "decided"),
            "labelled": len(labels_done),
        },
        "thresholds": {"tau": tau, "tau_h": tau_h},
        "audit_events_total": len(recs),
    }


# ---------------- SSE ----------------

async def sse_tail():
    """audit.jsonl 增量 tail：新事件即推 {type:'audit', data}；心跳 15s。"""
    pos = 0
    with open(AUDIT_PATH, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
    idle = 0
    while True:
        await asyncio.sleep(1.0)
        try:
            with open(AUDIT_PATH, "rb") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
        except FileNotFoundError:
            continue
        if chunk:
            idle = 0
            for line in chunk.split(b"\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield {"event": "audit", "data": json.dumps(rec, ensure_ascii=False)}
        else:
            idle += 1
            if idle % 15 == 0:
                yield {"event": "ping", "data": now_iso()}


# ---------------- API ----------------

@app.get("/api/taxonomy")
def api_taxonomy():
    return {"questions": QUESTIONS, "taxonomy": TAXONOMY,
            "auto_actions": sorted(gating.AUTO_ACTIONS)}


@app.get("/api/queue")
def api_queue(tau: float = None, tau_h: float = None):
    return build_views(tau=tau, tau_h=tau_h)


@app.get("/api/window/{wid}")
def api_window(wid: str):
    wins = {w["id"]: w for w in load_windows()["windows"]}
    if wid not in wins:
        raise HTTPException(404, "window not found")
    w = wins[wid]
    evs = [r for r in read_audit() if r.get("window_id") == wid]
    done = next((e for e in reversed(evs) if e.get("event") == "window_done"), None)
    evs = sorted(evs, key=lambda r: r.get("ts", ""))
    if done:
        # 证据高亮（tier0 规则窗无 raw 统计时也走 raw_lines）
        done = dict(done)
        done["evidence_lines"] = evidence_lines(w, done.get("route", {}))
        done["narrative"] = gating.narrate(w, None, (
            {"rule_id": done["rule_id"]} if done.get("rule_id") else None))
    dec_file = f"{DECISIONS_DIR}/{wid.replace('/', '_')}.json"
    decision = json.load(open(dec_file)) if os.path.exists(dec_file) else None
    return {"window": w, "audit_events": evs, "window_done": done,
            "decision": decision}


class DecisionReq(BaseModel):
    window_id: str
    question_decisions: dict = Field(default_factory=dict)  # q → {action: approve|veto|change, value?}
    decision: str = "confirm"          # 整窗：confirm | reject
    note: str = ""


@app.post("/api/decide")
def api_decide(req: DecisionReq):
    """逐题决策 + 整窗 confirm → 落 decisions/<wid>.json + audit human_decision 事件（append-only）。"""
    wins = {w["id"]: w for w in load_windows()["windows"]}
    if req.window_id not in wins:
        raise HTTPException(404, "window not found")
    for q, d in req.question_decisions.items():
        if q not in QUESTIONS:
            raise HTTPException(400, f"unknown question: {q}")
        act = d.get("action")
        if act not in ("approve", "veto", "change"):
            raise HTTPException(400, f"bad action: {act}")
        val = d.get("value")
        if act == "change":
            if q == "urgent":
                if not isinstance(val, bool):
                    raise HTTPException(400, "urgent value must be bool")
            elif val not in TAXONOMY[q]:
                raise HTTPException(400, f"bad {q} value: {val}")
    rec = {
        "ts": now_iso(),
        "event": "human_decision",
        "window_id": req.window_id,
        "decision": req.decision,
        "question_decisions": req.question_decisions,
        "note": req.note,
        "actor": "analyst@ui",
    }
    audit = gating.AuditLog(AUDIT_PATH)   # 复用管线审计器（同 append 协议）
    audit.append(**rec)
    # 决策快照（可被管线/训练脚本读取的落盘形态）
    with open(f"{DECISIONS_DIR}/{req.window_id.replace('/', '_')}.json", "w") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    return {"ok": True, "event": rec}


class LabelReq(BaseModel):
    window_id: str
    labels: dict            # tactic/urgent/severity/action correct labels
    ambiguous: bool = False
    note: str = ""


@app.post("/api/label")
def api_label(req: LabelReq):
    wins = {w["id"]: w for w in load_windows()["windows"]}
    if req.window_id not in wins:
        raise HTTPException(404, "window not found")
    done = next((r for r in reversed(read_audit())
                 if r.get("window_id") == req.window_id and r.get("event") == "window_done"), None)
    preds = {q: f.get("pred") for q, f in (done.get("route", {}).get("final", {}).items())} if done else {}
    rec = {
        "ts": now_iso(),
        "event": "label",
        "window_id": req.window_id,
        "labels": req.labels,
        "ambiguous": req.ambiguous,
        "pipeline_preds": preds,
        "note": req.note,
        "actor": "analyst@ui",
    }
    gating.AuditLog(AUDIT_PATH).append(**rec)
    return {"ok": True, "event": rec}


class ThresholdReq(BaseModel):
    tau: float = Field(ge=0.5, le=0.99)
    tau_h: float = Field(ge=0.3, le=0.95)


@app.post("/api/threshold")
def api_threshold(req: ThresholdReq):
    if req.tau_h >= req.tau:
        raise HTTPException(400, "tau_h must be < tau")
    old = load_runtime()
    save_runtime({"tau": req.tau, "tau_h": req.tau_h})
    gating.AuditLog(AUDIT_PATH).append(
        ts=now_iso(), event="threshold_change",
        old=old, new={"tau": req.tau, "tau_h": req.tau_h}, actor="analyst@ui")
    return {"ok": True, "thresholds": {"tau": req.tau, "tau_h": req.tau_h}}


@app.get("/api/labels/export")
def api_labels_export():
    """P1-6：labelled replays 导出（训练脚本可读 JSONL：state + final preds + correct labels）。"""
    wins = {w["id"]: w for w in load_windows()["windows"]}
    done = {}
    for r in read_audit():
        if r.get("event") == "window_done":
            done[r.get("window_id")] = r
    n = 0
    with open(LABELLED_PATH, "w") as f:
        for r in read_audit():
            if r.get("event") != "label":
                continue
            wid = r.get("window_id")
            w, d = wins.get(wid), done.get(wid)
            if not w or not d:
                continue
            f.write(json.dumps({
                "id": wid,
                "state": w.get("suite_state"),
                "questions": {
                    q: {"type": "noul" if q == "urgent" else
                        ("score" if q == "severity" else "choice"),
                        "label": r["labels"].get(q)}
                    for q in QUESTIONS},
                "pipeline_final": {q: f.get("pred") for q, f in
                                   d.get("route", {}).get("final", {}).items()},
                "tier1_dists": d.get("tier1_dists"),
                "tier2_dists": d.get("tier2_dists"),
                "ambiguous": r.get("ambiguous", False),
                "label_ts": r.get("ts"), "note": r.get("note", ""),
            }, ensure_ascii=False) + "\n")
            n += 1
    return {"ok": True, "n": n, "path": LABELLED_PATH}


@app.get("/api/stream")
async def api_stream():
    return EventSourceResponse(sse_tail())


@app.get("/")
def index():
    return FileResponse(f"{HERE}/static/index.html")


app.mount("/static", StaticFiles(directory=f"{HERE}/static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8024, log_level="info")
