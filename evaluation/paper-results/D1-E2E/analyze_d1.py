#!/usr/bin/env python3
# Z-1 D1 端到端分析步（纯 CPU 回放，不改原始数据）
# 输入: raw/d1_records.jsonl (439 窗, 只读)
# 输出: routing_share.json / tau_scan.json / latency.json / sys_accuracy.json
import json, os, statistics
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
QS = ["tactic", "urgent", "severity", "action"]
MAIN_TAU, MAIN_TAU_H = 0.90, 0.70

recs = [json.loads(l) for l in open(f"{HERE}/raw/d1_records.jsonl", encoding="utf-8")]
N = len(recs)

def gate(conf, tau, tau_h):
    if conf >= tau: return "auto"
    if conf >= tau_h: return "confirm"
    return "escalate"

def replay(rec, tau, tau_h):
    """返回每题 final (pred, gate, source)。rule 窗直接规则答案。"""
    out = {}
    if "tier0_rule" in rec["path"]:
        for q in QS:
            out[q] = {"pred": rec["final"][q]["pred"], "gate": "auto", "source": "rule"}
        return out
    t1 = rec["tier1"]
    need_t2 = any(gate(t1[q]["conf"], tau, tau_h) == "escalate" for q in QS)
    t2 = rec["tier2"] if (need_t2 and rec["tier2"]) else None
    approx = need_t2 and rec["tier2"] is None  # τ 抬高后需 tier2 但未跑过 → tier1 兜底（仅 τ=0.95 出现）
    src_answers = t2 if t2 else t1
    src = "tier2" if t2 else "tier1"
    for q in QS:
        a = src_answers[q]
        out[q] = {"pred": a["pred"], "gate": gate(a["conf"], tau, tau_h), "source": src}
    return out, approx

def correct_q(rec, q, pred):
    lab = rec["labels"][q]
    if q == "urgent":
        return (str(pred).lower() == "true") == bool(lab) if isinstance(pred, (str, bool)) else pred == lab
    return pred == lab

def eval_tau(recs, tau, tau_h):
    tau_h = round(tau_h, 2)
    n_q = 0; auto_q = 0; human_win = 0; tactic_ok = 0; exact_ok = 0
    auto_tactic_ok = 0; auto_exact_ok = 0; auto_win = 0
    approx_wins = []
    for rec in recs:
        res = replay(rec, tau, tau_h)
        approx = False
        if isinstance(res, tuple): res, approx = res
        if approx: approx_wins.append(rec["window_id"])
        all_ok = True; any_auto_human = False
        win_auto = True
        for q in QS:
            f = res[q]; n_q += 1
            ok = correct_q(rec, q, f["pred"])
            all_ok &= ok
            if f["gate"] == "auto":
                auto_q += 1
                auto_tactic_ok += ok if q == "tactic" else 0
            else:
                win_auto = False
        tactic_ok += correct_q(rec, "tactic", res["tactic"]["pred"])
        exact_ok += all_ok
        if win_auto:
            auto_win += 1
            auto_exact_ok += all_ok
        else:
            human_win += 1
    auto_tactic_n = sum(1 for rec in recs for q in QS
                        if q == "tactic" and replay_q(rec, tau, tau_h, q)[1] == "auto")
    return {
        "tau": tau, "tau_h": tau_h,
        "question_level": {
            "n_questions": n_q, "auto_share": round(auto_q / n_q, 4),
            "human_involved_share": round(1 - auto_q / n_q, 4)},
        "window_level": {
            "n_windows": N,
            "windows_human": human_win, "windows_full_auto": auto_win,
            "tactic_acc": round(tactic_ok / N, 4),
            "exact_acc(all4)": round(exact_ok / N, 4),
            "auto_only_tactic_acc": round(auto_tactic_ok / max(auto_tactic_n, 1), 4) if auto_tactic_n else None,
            "auto_only_exact_acc": round(auto_exact_ok / max(auto_win, 1), 4)},
        "approx_replay_windows": len(approx_wins),
        "_approx_ids": approx_wins[:50],
    }

def replay_q(rec, tau, tau_h, q):
    if "tier0_rule" in rec["path"]:
        return rec["final"][q]["pred"], "auto"
    r = replay(rec, tau, tau_h)
    if isinstance(r, tuple): r = r[0]
    return r[q]["pred"], r[q]["gate"]

def p50p90(vals):
    v = sorted(vals)
    return {"n": len(v), "p50_ms": round(statistics.median(v), 1),
            "p90_ms": round(v[min(int(len(v) * 0.9), len(v) - 1)], 1),
            "mean_ms": round(statistics.mean(v), 1)}

# ---------- 1) routing_share.json (主档 τ=0.90/τ_h=0.70) ----------
path_win = Counter("→".join(rec["path"]) for rec in recs)
q_route = Counter()
human_qs = 0
for rec in recs:
    res = replay(rec, MAIN_TAU, MAIN_TAU_H)
    if isinstance(res, tuple): res = res[0]
    for q in QS:
        q_route[f'{res[q]["source"]}/{res[q]["gate"]}'] += 1
        if res[q]["gate"] != "auto": human_qs += 1
routing_share = {
    "tau": MAIN_TAU, "tau_h": MAIN_TAU_H, "n_windows": N,
    "window_paths": {k: {"count": v, "share": round(v / N, 4)} for k, v in path_win.items()},
    "question_routes (source/gate)": {k: {"count": v, "share": round(v / (N * 4), 4)} for k, v in sorted(q_route.items())},
    "questions_sent_to_human": {"count": human_qs, "share": round(human_qs / (N * 4), 4)},
    "windows_with_human": sum(1 for rec in recs if "tier3_human" in rec["path"]),
}
json.dump(routing_share, open(f"{HERE}/routing_share.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 2) tau_scan.json ----------
scan = []
for tau in [0.75, 0.80, 0.85, 0.90, 0.95]:
    s = eval_tau(recs, tau, tau - 0.20)
    s["effective_acc_question_level"] = round(s["question_level"]["auto_share"] * (
        s["window_level"]["tactic_acc"]), 4)  # 带宽×精度（近似口径：auto_share × 系统tactic）
    scan.append(s)
json.dump(scan, open(f"{HERE}/tau_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 3) latency.json ----------
lat = {}
for k in ["state_ms", "tier0_ms", "tier1_ms", "tier2_ms", "gate_ms"]:
    vals = [rec["latency_ms"][k] for rec in recs if rec["latency_ms"].get(k) is not None]
    if vals: lat[k] = p50p90(vals)
lat["end_to_end"] = p50p90([rec["total_ms"] for rec in recs])
lat["note"] = ("tier1(laya) 为 CPU 口径（P50≈1.15s）；GPU 批量口径补测留 D1b 可选（B1-2）。"
               "state_ms 计的是取用预构建 state 的开销，非构建耗时。")
json.dump(lat, open(f"{HERE}/latency.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 4) sys_accuracy.json ----------
main = eval_tau(recs, MAIN_TAU, MAIN_TAU_H)
sys_acc = {
    "tau": MAIN_TAU, "tau_h": MAIN_TAU_H, "n_windows": N,
    "system_tactic_acc": main["window_level"]["tactic_acc"],
    "system_exact_acc": main["window_level"]["exact_acc(all4)"],
    "single_model_baseline (kev-4B, 论文口径)": {"tactic": 0.850, "exact": 0.629},
    "window_level_detail": main["window_level"],
    "question_level_detail": main["question_level"],
    "metric_note": "final.pred 口径：人工确认窗沿用模型建议答案（run 时 non-interactive=y 全批准）；"
                   "exact = tactic/urgent/severity/action 四题全对。",
}
json.dump(sys_acc, open(f"{HERE}/sys_accuracy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(json.dumps({"routing": {k: v["count"] for k, v in routing_share["window_paths"].items()},
                  "q_routes": {k: v["count"] for k, v in routing_share["question_routes (source/gate)"].items()},
                  "sys": {k: sys_acc[k] for k in ("system_tactic_acc", "system_exact_acc")},
                  "tau_scan": [{ "tau": s["tau"], "auto_share": s["question_level"]["auto_share"],
                                 "tactic": s["window_level"]["tactic_acc"], "exact": s["window_level"]["exact_acc(all4)"],
                                 "approx_wins": s["approx_replay_windows"]} for s in scan]},
                 ensure_ascii=False, indent=1))
