#!/usr/bin/env python3
# D1-4B-TIER2 分析步（纯 CPU 回放，只读原始数据）
# 输入: ../D1-E2E/raw/d1_records.jsonl (439 窗 D1 原始,只读) + kev4b_439.jsonl (全 439 窗 kev-4B@8018 逐题输出)
#       ../D2-ESCALATION/matrix.json (0.8B 版归因,对照用)
# 输出: routing_share.json / tau_scan.json / latency.json / sys_accuracy.json / matrix.json
# 口径: tier2 输出整体替换为 kev-4B（同 state/同模板/同内嵌温度,仅换 serve 8018）;
#       rule 窗仍走规则答案; tier1(laya) 输出不变; 门控 τ/τ_h 与 D1 相同。
import json, os, statistics
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
QS = ["tactic", "urgent", "severity", "action"]
MAIN_TAU, MAIN_TAU_H = 0.90, 0.70

recs = [json.loads(l) for l in open(f"{HERE}/../D1-E2E/raw/d1_records.jsonl", encoding="utf-8")]
N = len(recs)
k4 = {}
for l in open(f"{HERE}/kev4b_439.jsonl", encoding="utf-8"):
    r = json.loads(l)
    k4[r["window_id"]] = r
assert len(k4) == N and set(k4) == {r["window_id"] for r in recs}
d2_08 = json.load(open(f"{HERE}/../D2-ESCALATION/matrix.json", encoding="utf-8"))  # 0.8B 对照

def t2_4b(rec):
    return k4[rec["window_id"]]["tier2_4b"]

def t2_4b_lat(rec):
    return k4[rec["window_id"]]["latency_ms"]

def gate(conf, tau, tau_h):
    if conf >= tau: return "auto"
    if conf >= tau_h: return "confirm"
    return "escalate"

def replay(rec, tau, tau_h):
    """每题 final (pred, gate, source)。rule 窗直接规则答案; 非规则窗 tier2 用 kev-4B 输出。
    全 439 窗 4B 输出齐备 → 任何 τ 都是精确回放, 无近似。"""
    out = {}
    if "tier0_rule" in rec["path"]:
        for q in QS:
            out[q] = {"pred": rec["final"][q]["pred"], "gate": "auto", "source": "rule"}
        return out, False
    t1 = rec["tier1"]
    need_t2 = any(gate(t1[q]["conf"], tau, tau_h) == "escalate" for q in QS)
    t2 = t2_4b(rec) if need_t2 else None  # 4B 输出全量齐备, 无兜底
    src_answers = t2 if t2 else t1
    src = "tier2" if t2 else "tier1"
    for q in QS:
        a = src_answers[q]
        out[q] = {"pred": a["pred"], "gate": gate(a["conf"], tau, tau_h), "source": src}
    return out, False

def correct_q(rec, q, pred):
    lab = rec["labels"][q]
    if q == "urgent":
        return (str(pred).lower() == "true") == bool(lab) if isinstance(pred, (str, bool)) else pred == lab
    return pred == lab

def eval_tau(recs, tau, tau_h):
    tau_h = round(tau_h, 2)
    n_q = 0; auto_q = 0; human_win = 0; tactic_ok = 0; exact_ok = 0
    auto_tactic_ok = 0; auto_exact_ok = 0; auto_win = 0; t2_engaged = 0
    for rec in recs:
        res, approx = replay(rec, tau, tau_h)
        all_ok = True; win_auto = True
        for q in QS:
            f = res[q]; n_q += 1
            ok = correct_q(rec, q, f["pred"])
            all_ok &= ok
            if f["source"] == "tier2": t2_engaged += 0  # 题级占位,窗级另计
            if f["gate"] == "auto":
                auto_q += 1
                auto_tactic_ok += ok if q == "tactic" else 0
            else:
                win_auto = False
        tactic_ok += correct_q(rec, "tactic", res["tactic"]["pred"])
        exact_ok += all_ok
        if any(res[q]["source"] == "tier2" for q in QS): t2_engaged += 1
        if win_auto:
            auto_win += 1
            auto_exact_ok += all_ok
        else:
            human_win += 1
    auto_tactic_n = sum(1 for rec in recs for q in QS
                        if q == "tactic" and replay(rec, tau, tau_h)[0][q]["gate"] == "auto")
    return {
        "tau": tau, "tau_h": tau_h,
        "question_level": {
            "n_questions": n_q, "auto_share": round(auto_q / n_q, 4),
            "human_involved_share": round(1 - auto_q / n_q, 4)},
        "window_level": {
            "n_windows": N,
            "windows_human": human_win, "windows_full_auto": auto_win,
            "tier2_4b_engaged_windows": t2_engaged,
            "tactic_acc": round(tactic_ok / N, 4),
            "exact_acc(all4)": round(exact_ok / N, 4),
            "auto_only_tactic_acc": round(auto_tactic_ok / max(auto_tactic_n, 1), 4) if auto_tactic_n else None,
            "auto_only_exact_acc": round(auto_exact_ok / max(auto_win, 1), 4)},
        "approx_replay_windows": 0,
    }

def p50p90(vals):
    v = sorted(vals)
    return {"n": len(v), "p50_ms": round(statistics.median(v), 1),
            "p90_ms": round(v[min(int(len(v) * 0.9), len(v) - 1)], 1),
            "mean_ms": round(statistics.mean(v), 1)}

# ---------- 1) routing_share.json (主档 τ=0.90/τ_h=0.70, tier2=kev-4B) ----------
path_win = Counter("→".join(rec["path"]) for rec in recs)
q_route = Counter()
human_qs = 0
for rec in recs:
    res, _ = replay(rec, MAIN_TAU, MAIN_TAU_H)
    for q in QS:
        q_route[f'{res[q]["source"]}/{res[q]["gate"]}'] += 1
        if res[q]["gate"] != "auto": human_qs += 1
routing_share = {
    "tau": MAIN_TAU, "tau_h": MAIN_TAU_H, "n_windows": N,
    "tier2_model": "kev-4B v3 @8018 (全 439 窗逐题输出, 精确回放)",
    "window_paths": {k: {"count": v, "share": round(v / N, 4)} for k, v in path_win.items()},
    "question_routes (source/gate)": {k: {"count": v, "share": round(v / (N * 4), 4)} for k, v in sorted(q_route.items())},
    "questions_sent_to_human": {"count": human_qs, "share": round(human_qs / (N * 4), 4)},
    "windows_with_human": sum(1 for rec in recs if "tier3_human" in rec["path"]),
}
json.dump(routing_share, open(f"{HERE}/routing_share.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 2) tau_scan.json (0.75-0.95 全档精确回放) ----------
scan = []
for tau in [0.75, 0.80, 0.85, 0.90, 0.95]:
    s = eval_tau(recs, tau, tau - 0.20)
    s["effective_acc_question_level"] = round(s["question_level"]["auto_share"] * (
        s["window_level"]["tactic_acc"]), 4)  # 带宽×精度(近似口径, 同 D1 公式)
    scan.append(s)
json.dump(scan, open(f"{HERE}/tau_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 3) latency.json (tier2 段=4B 实测; 其余段沿用 D1 实测) ----------
def engaged_4b(rec, tau=MAIN_TAU, tau_h=MAIN_TAU_H):
    if "tier0_rule" in rec["path"]: return False
    return any(gate(rec["tier1"][q]["conf"], tau, tau_h) == "escalate" for q in QS)

lat = {}
for k in ["state_ms", "tier0_ms", "tier1_ms", "gate_ms"]:
    vals = [rec["latency_ms"][k] for rec in recs if rec["latency_ms"].get(k) is not None]
    if vals: lat[k] = p50p90(vals)
lat["tier2_kev4b"] = p50p90([t2_4b_lat(rec) for rec in recs if engaged_4b(rec)])
lat["tier2_kev08 (D1 原版对照)"] = p50p90([rec["latency_ms"]["tier2_ms"] for rec in recs
                                          if rec["latency_ms"].get("tier2_ms") is not None])
# 端到端重算: D1 各段实测 + tier2 段换 4B 实测(主档 τ 下实际升级的窗)
e2e = []
for rec in recs:
    lm = rec["latency_ms"]
    t = lm["state_ms"] + lm["tier0_ms"] + lm["gate_ms"]
    if lm.get("tier1_ms") is not None: t += lm["tier1_ms"]
    if engaged_4b(rec): t += t2_4b_lat(rec)
    e2e.append(t)
lat["end_to_end_4b_tier2"] = p50p90(e2e)
lat["end_to_end_d1_original (0.8B tier2)"] = p50p90([rec["total_ms"] for rec in recs])
lat["note"] = ("tier1(laya) 为 CPU 口径(P50≈1.15s, D1 实测沿用); tier2 段=kev-4B@8018 实测 "
               "(P50≈165ms, 0.8B@8023 P50≈111ms); state_ms 为取用预构建 state 的开销。"
               "端到端=各段实测之和, tier2 段按主档 τ=0.90 实际升级窗计入 4B 延迟。")
json.dump(lat, open(f"{HERE}/latency.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 4) sys_accuracy.json ----------
main = eval_tau(recs, MAIN_TAU, MAIN_TAU_H)
sys_acc = {
    "tau": MAIN_TAU, "tau_h": MAIN_TAU_H, "n_windows": N,
    "tier2_model": "kev-4B v3 @8018",
    "system_tactic_acc": main["window_level"]["tactic_acc"],
    "system_exact_acc": main["window_level"]["exact_acc(all4)"],
    "single_model_baseline (kev-4B, 论文口径)": {"tactic": 0.850, "exact": 0.629},
    "d1_system_08_tier2 (对照)": {"tactic": 0.554, "exact": 0.437},
    "window_level_detail": main["window_level"],
    "question_level_detail": main["question_level"],
    "metric_note": "final.pred 口径同 D1: 人工确认窗沿用模型建议答案; exact=四题全对; "
                   "tier2 输出整体替换为 kev-4B(同 state/同模板/同内嵌温度), rule/tier1 不变。",
}
json.dump(sys_acc, open(f"{HERE}/sys_accuracy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 5) matrix.json (D2 同款归因, L2=kev-4B; 对照 0.8B 版) ----------
def ok(rec, q, pred):
    lab = rec["labels"][q]
    if q == "urgent":
        return (str(pred).lower() == "true") == bool(lab) if isinstance(pred, str) else bool(pred) == bool(lab)
    return pred == lab

sub_dual = [r for r in recs if r["tier1"] and "tier2_kev" in r["path"]]   # 231 D1 升级窗
sub_dual_layer = [r for r in recs if r["tier1"]]                          # 299 非规则窗(全有 4B 输出)

def quadrant(pool):
    quad = {"tactic": Counter(), "exact": Counter()}
    per_class = {"tactic": Counter()}
    for r in pool:
        t2 = t2_4b(r)
        l1_all_ok = all(ok(r, q, r["tier1"][q]["pred"]) for q in QS)
        l2_all_ok = all(ok(r, q, t2[q]["pred"]) for q in QS)
        for metric, l1_ok, l2_ok in (("tactic", ok(r, "tactic", r["tier1"]["tactic"]["pred"]),
                                      ok(r, "tactic", t2["tactic"]["pred"])),
                                     ("exact", l1_all_ok, l2_all_ok)):
            cell = "both_correct" if (l1_ok and l2_ok) else "l1_only_correct" if l1_ok else \
                   "l2_only_correct" if l2_ok else "both_wrong"
            quad[metric][cell] += 1
        l1t, l2t = ok(r, "tactic", r["tier1"]["tactic"]["pred"]), ok(r, "tactic", t2["tactic"]["pred"])
        cell = "both_correct" if (l1t and l2t) else "l1_only_correct" if l1t else \
               "l2_only_correct" if l2t else "both_wrong"
        per_class["tactic"][f'{r["labels"]["tactic"]}/{cell}'] += 1
    return quad, per_class

quad_dual, pc_dual = quadrant(sub_dual)
quad_299, pc_299 = quadrant(sub_dual_layer)

def acc_tactic(pool, getter): return round(sum(ok(r, "tactic", getter(r)["tactic"]["pred"]) for r in pool) / len(pool), 4)
def acc_exact(pool, getter): return round(sum(all(ok(r, q, getter(r)[q]["pred"]) for q in QS) for r in pool) / len(pool), 4)

def cascade4b(r):
    return t2_4b(r) if engaged_4b(r) else r["tier1"]

configs = {
    "L1_only": {"n": 299, "tactic": acc_tactic(sub_dual_layer, lambda r: r["tier1"]),
                "exact": acc_exact(sub_dual_layer, lambda r: r["tier1"])},
    "L1_to_L2_cascade (4B)": {"n": 299, "tactic": acc_tactic(sub_dual_layer, cascade4b),
                              "exact": acc_exact(sub_dual_layer, cascade4b)},
    "L2_only_4b (231 escalated)": {"n": 231, "tactic": acc_tactic(sub_dual, t2_4b),
                                   "exact": acc_exact(sub_dual, t2_4b)},
    "L2_only_4b (non-rule 299)": {"n": 299, "tactic": acc_tactic(sub_dual_layer, t2_4b),
                                  "exact": acc_exact(sub_dual_layer, t2_4b)},
    "L2_only_4b (full 439)": {"n": 439, "tactic": acc_tactic(recs, t2_4b),
                              "exact": acc_exact(recs, t2_4b)},
}

l2_win = sum(1 for r in sub_dual_layer if (not ok(r, "tactic", r["tier1"]["tactic"]["pred"])) and ok(r, "tactic", t2_4b(r)["tactic"]["pred"]))
l1_win = sum(1 for r in sub_dual_layer if ok(r, "tactic", r["tier1"]["tactic"]["pred"]) and (not ok(r, "tactic", t2_4b(r)["tactic"]["pred"])))
ia_total_439 = sum(1 for r in recs if r["labels"]["tactic"] == "initial_access")
ia_blind_299 = pc_299["tactic"].get("initial_access/both_wrong", 0)

matrix = {
    "n_dual_output_windows": 231,
    "n_full_4b_windows": 439,
    "note": "D2 同款归因矩阵, L2 整体替换为 kev-4B v3@8018(全 439 窗逐题, 同 state/同模板/同内嵌温度); L1=D1 tier1(laya) 不变; 0.8B 对照引自 D2-ESCALATION/matrix.json",
    "quadrant_tactic (231 escalated)": dict(quad_dual["tactic"]),
    "quadrant_exact (231 escalated)": dict(quad_dual["exact"]),
    "quadrant_dual_layer_299_tactic": dict(quad_299["tactic"]),
    "quadrant_dual_layer_299_exact": dict(quad_299["exact"]),
    "quadrant_dual_layer_299_tactic_pct": {k: round(v / len(sub_dual_layer), 4) for k, v in quad_299["tactic"].items()},
    "quadrant_dual_layer_299_exact_pct": {k: round(v / len(sub_dual_layer), 4) for k, v in quad_299["exact"].items()},
    "per_gt_class_tactic_dual_layer_299": dict(sorted(pc_299["tactic"].items())),
    "configs": configs,
    "complementarity_299": {
        "l2_wins_l1_loses_tactic": l2_win, "l1_wins_l2_loses_tactic": l1_win,
        "tie": len(sub_dual_layer) - l2_win - l1_win,
        "initial_access_total_windows_439": ia_total_439,
        "initial_access_both_wrong_299": ia_blind_299,
    },
    "compare_08 (D2 matrix 原文)": {
        "quadrant_dual_layer_299_tactic": d2_08["quadrant_dual_layer_299_tactic"],
        "quadrant_dual_layer_299_exact": d2_08["quadrant_dual_layer_299_exact"],
        "configs": d2_08["configs"],
        "complementarity": d2_08["complementarity"],
    },
}
json.dump(matrix, open(f"{HERE}/matrix.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 摘要 ----------
print(json.dumps({
    "sys_4b": {"tactic": sys_acc["system_tactic_acc"], "exact": sys_acc["system_exact_acc"]},
    "sys_08": {"tactic": 0.554, "exact": 0.437},
    "tau_scan": [{"tau": s["tau"], "auto": s["question_level"]["auto_share"],
                  "tactic": s["window_level"]["tactic_acc"], "exact": s["window_level"]["exact_acc(all4)"],
                  "t2_engaged": s["window_level"]["tier2_4b_engaged_windows"],
                  "eff": s["effective_acc_question_level"]} for s in scan],
    "latency": {"tier2_4b": lat["tier2_kev4b"], "tier2_08": lat["tier2_kev08 (D1 原版对照)"],
                "e2e_4b": lat["end_to_end_4b_tier2"], "e2e_08": lat["end_to_end_d1_original (0.8B tier2)"]},
    "quadrant_299_tactic_4b": dict(quad_299["tactic"]),
    "quadrant_299_tactic_08": d2_08["quadrant_dual_layer_299_tactic"],
    "configs": configs,
    "ia": {"total_439": ia_total_439, "blind_299_4b": ia_blind_299,
           "blind_299_08": d2_08["per_gt_class_tactic_dual_layer_299"].get("initial_access/both_wrong")},
    "q_routes": {k: v["count"] for k, v in routing_share["question_routes (source/gate)"].items()},
}, ensure_ascii=False, indent=1))
