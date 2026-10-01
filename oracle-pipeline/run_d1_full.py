#!/usr/bin/env python3
"""D1 — 端到端 439 窗全量串联实测（rules → laya → kev → gate）

与 run_pipeline.py（20 窗 demo）同口径，扩展：
  - 全量 439 test 窗（不抽样）
  - 逐窗记录 tier1/tier2 全题分布（probabilities）→ τ 扫描离线回放
  - 结构化 d1_records.jsonl + audit.jsonl（append-only）
  - 断点续跑：已完成的 window_id 自动跳过

用法（spark2_5 venv，kev serve 先起，见 serve_kev.sh 8023）:
  python3 run_d1_full.py --kev-url http://127.0.0.1:8023 \
      --out-dir ~/MySecAgent/lab/experiments/oracle/EVAL/D1-E2E/raw
"""
import argparse
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SECAGENT = "/home/xxl/MySecAgent"
sys.path.insert(0, f"{SECAGENT}/lab/experiments/oracle/code/suite")
sys.path.insert(0, f"{SECAGENT}/judge")

from state_builder import window_record, load_raw_index, load_laya_rows  # noqa: E402
from tier0_rules import tier0  # noqa: E402
import gating  # noqa: E402

SUITE_V3 = f"{SECAGENT}/lab/experiments/oracle/suites/oracle-v3"


def build_all_windows():
    """全量 439 test 窗 → 管线输入记录 + 分层池统计"""
    from rules import judge_rule
    raw_idx = load_raw_index()
    laya_rows = load_laya_rows()
    recs = [json.loads(l) for l in open(f"{SUITE_V3}/test.jsonl")]
    wins, missing_raw, pools = [], [], {"rule": 0, "high": 0, "mid": 0, "low": 0}
    for rec in recs:
        rid = rec["_meta"]["id"]
        raw_path = raw_idx.get(rid)
        raw = (json.loads(open(raw_path).readline()) if raw_path is not None
               else {"state": {"raw_log_lines": [], "window_stats": {}},
                     "scenario": None, "kind": None})
        # 缺 raw 记录的窗：规则层无输入 → pass-through，两层照跑（保证 439 全覆盖）
        if raw_path is not None:
            ev = {"raw_lines": raw["state"]["raw_log_lines"],
                  "window_stats": raw["state"].get("window_stats", {})}
            hit = judge_rule(ev)
            if hit:
                pools["rule"] += 1
            elif rid in laya_rows:
                row = laya_rows[rid]
                cs = [max(row["probs"][q].values()) for q in ("tactic", "severity", "action")
                      if row["probs"].get(q)]
                m = min(cs) if cs else 0.0
                if m >= 0.90:
                    pools["high"] += 1
                elif m >= 0.70:
                    pools["mid"] += 1
                else:
                    pools["low"] += 1
        else:
            missing_raw.append(rid)
        wins.append(window_record(rec, raw))
    return wins, pools, missing_raw


def process_window(w, laya, kev, audit_path):
    """单窗全管线，返回结构化记录（含两 tier 全题分布，供离线 τ 回放）"""
    t_start = time.time()
    wid = w["id"]
    lat = {"state_ms": 0.0, "tier0_ms": None, "tier1_ms": None,
           "tier2_ms": None, "gate_ms": 0.0, "human_ms": None}
    rec = {"window_id": wid, "labels": w.get("labels"), "scenario": w.get("scenario"),
           "kind": w.get("kind"), "path": [], "rule_hit": None,
           "tier1": None, "tier2": None, "final": {}}

    # Tier 0 规则
    t0 = time.time()
    rule_out = tier0(w)
    lat["tier0_ms"] = (time.time() - t0) * 1000
    if rule_out:
        rec["path"].append("tier0_rule")
        rec["rule_hit"] = rule_out["rule_id"]
        rec["final"] = {q: {"pred": v, "conf": 1.0, "source": "rule"}
                        for q, v in rule_out["verdict"].items()}
        rec["latency_ms"] = {k: (round(v, 3) if v is not None else None)
                             for k, v in lat.items()}
        rec["total_ms"] = (time.time() - t_start) * 1000
        return rec

    state = w["suite_state"]

    # Tier 1 laya
    t1_out = laya.decide(state)
    lat["tier1_ms"] = t1_out["latency_ms"]
    rec["path"].append("tier1_laya")
    rec["tier1"] = {q: {"pred": a["pred"], "conf": a["conf"],
                        "probabilities": a["probabilities"]}
                    for q, a in t1_out["answers"].items()}
    g1 = gating.gate_all(t1_out["answers"])

    # 窗口级升级判定（任一题 escalate → 整窗升 Tier 2）
    t2_out = None
    g2 = None
    if gating.needs_tier2(g1):
        rec["path"].append("tier2_kev")
        t2_out = kev.decide(state)
        lat["tier2_ms"] = t2_out["latency_ms"]
        g2 = gating.gate_all(t2_out["answers"])
        rec["tier2"] = {q: {"pred": a["pred"], "conf": a["conf"],
                            "probabilities": a["probabilities"]}
                        for q, a in t2_out["answers"].items()}

    # 逐题终局路由（τ=0.90/τ_h=0.70 运行档；其余档离线回放）
    t0 = time.time()
    confirm_qs, human_qs = [], []
    for q in t1_out["answers"]:
        if t2_out is not None:
            src, a, g = "tier2", t2_out["answers"][q], g2[q]
        else:
            src, a, g = "tier1", t1_out["answers"][q], g1[q]
        rec["final"][q] = {"pred": a["pred"], "conf": round(a["conf"], 4),
                           "gate": g, "source": src}
        if g == "confirm":
            confirm_qs.append(q)
        elif g == "escalate":
            human_qs.append(q)
    lat["gate_ms"] = (time.time() - t0) * 1000

    # Tier 3：非交互模式（批量实测默认批准建议——与 20 窗 demo 同口径）
    if confirm_qs or human_qs:
        rec["path"].append("tier3_human")
        rec["human"] = {"mode": "non_interactive_approve",
                        "confirm_questions": confirm_qs,
                        "escalated_questions": human_qs}
        for q in confirm_qs:
            rec["final"][q]["executed"] = "human_approved"
        for q in human_qs:
            rec["final"][q]["executed"] = "human_decision"
    else:
        act = rec["final"].get("action") or {"pred": None}
        act["executed"] = "auto" if act["pred"] in gating.AUTO_ACTIONS else "blocked_not_whitelisted"
        rec["final"]["action"] = act

    rec["latency_ms"] = {k: (round(v, 3) if v is not None else None)
                         for k, v in lat.items()}
    rec["total_ms"] = (time.time() - t_start) * 1000

    # 审计（append-only）
    with open(audit_path, "a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "event": "window_done", "window_id": wid,
                            "path": rec["path"], "rule_hit": rec["rule_hit"],
                            "latency_ms": rec["latency_ms"],
                            "total_ms": round(rec["total_ms"], 1),
                            "labels": rec["labels"]}, ensure_ascii=False) + "\n")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kev-url", default="http://127.0.0.1:8023")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0=全部（冒烟用）")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    rec_path = os.path.join(args.out_dir, "d1_records.jsonl")
    audit_path = os.path.join(args.out_dir, "audit.jsonl")

    done = set()
    if os.path.exists(rec_path):
        for l in open(rec_path):
            done.add(json.loads(l)["window_id"])
        print(f"[resume] {len(done)} 已完成窗，跳过")

    # kev 健康检查
    from tier2_kev import KevTier
    kev = KevTier(base_url=args.kev_url)
    if not kev.healthy():
        print(f"[abort] kev serve 未就绪: {args.kev_url}")
        sys.exit(2)

    t0 = time.time()
    from tier1_laya import LayaTier
    laya = LayaTier(device="cpu")
    print(f"[laya] loaded in {time.time()-t0:.1f}s (CPU)")

    wins, pools, missing = build_all_windows()
    print(f"[pool] {pools} · raw 缺失 {len(missing)} 窗（tier0 现场判 + 两层全跑，不受影响）")
    if args.limit:
        wins = wins[: args.limit]
    todo = [w for w in wins if w["id"] not in done]
    print(f"[run] 总 {len(wins)} 窗 · 待跑 {len(todo)}")

    t_start = time.time()
    n_err = 0
    with open(rec_path, "a") as out:
        for i, w in enumerate(todo):
            try:
                rec = process_window(w, laya, kev, audit_path)
            except Exception as e:
                n_err += 1
                rec = {"window_id": w["id"], "error": f"{type(e).__name__}: {e}",
                       "labels": w.get("labels")}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if (i + 1) % 20 == 0 or i + 1 == len(todo):
                el = time.time() - t_start
                eta = el / (i + 1) * (len(todo) - i - 1)
                print(f"[{i+1}/{len(todo)}] elapsed {el:.0f}s ETA {eta:.0f}s "
                      f"err={n_err} last={rec.get('path')}", flush=True)
    print(f"[done] {len(todo)} 窗完成，错误 {n_err} → {rec_path}")


if __name__ == "__main__":
    main()
