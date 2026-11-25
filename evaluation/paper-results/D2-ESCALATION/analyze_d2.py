#!/usr/bin/env python3
"""D2 轻重串联增益归因（E-2 扩全量版）——D1 逐题输出 + kev208 补跑回放

四象限(L1对L2错 / L2对L1错 / 都对 / 都错) tactic+exact 两口径:
  - 双输出 231 窗（D1 运行时升级窗,与 B1-1 相同子集,保留对照）
  - 全量 439 窗（231 + E-2 补跑 kev208.jsonl 208 窗,kev-0.8B@8023 同 D1 serve）
三配置对照: 仅L1(299窗) / L1→L2串联(299窗) / 仅L2(全量439窗,E-2 新增)。
输出: matrix.json
"""
import json, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
recs = [json.loads(l) for l in open(f"{HERE}/../D1-E2E/raw/d1_records.jsonl", encoding="utf-8")]
QS = ["tactic", "urgent", "severity", "action"]

# E-2 补跑的 208 窗 kev 输出 → 注入 rec["tier2_backfill"]
backfill = {}
for l in open(f"{HERE}/kev208.jsonl", encoding="utf-8"):
    r = json.loads(l)
    backfill[r["window_id"]] = r["tier2_backfill"]

def get_t2(rec):
    return rec["tier2"] or backfill.get(rec["window_id"])

def ok(rec, q, pred):
    lab = rec["labels"][q]
    if q == "urgent":
        return (str(pred).lower() == "true") == bool(lab
                                                     ) if isinstance(pred, str) else bool(pred) == bool(lab)
    return pred == lab

both = [r for r in recs if get_t2(r) is not None]
t1_all = [r for r in recs if r["tier1"]]

# ---- 四象限（全量 439 窗 = 231 D1 升级窗 + 208 补跑窗） ----
def quadrant(pool):
    quad = {"tactic": Counter(), "exact": Counter()}
    per_class = {"tactic": Counter(), "exact": Counter()}
    for r in pool:
        t2 = get_t2(r)
        l1_all_ok = r["tier1"] is not None and all(ok(r, q, r["tier1"][q]["pred"]) for q in QS)
        l2_all_ok = all(ok(r, q, t2[q]["pred"]) for q in QS)
        for metric, l1_ok, l2_ok in (("tactic", (r["tier1"] is not None and ok(r, "tactic", r["tier1"]["tactic"]["pred"])) if r["tier1"] else False,
                                      ok(r, "tactic", t2["tactic"]["pred"])),
                                     ("exact", l1_all_ok, l2_all_ok)):
            cell = "both_correct" if (l1_ok and l2_ok) else "l1_only_correct" if l1_ok else \
                   "l2_only_correct" if l2_ok else "both_wrong"
            quad[metric][cell] += 1
            if r["tier1"] is not None:  # 有 L1 输出的窗才进按类分解
                per_class[metric][f'{r["labels"]["tactic"]}/{cell}'] += 1
    return quad, per_class

# 子集 A: D1 双输出 231 窗（原 B1-1 口径,保留对照）
sub_dual = [r for r in recs if r["tier1"] and r["tier2"]]
quad_dual, pc_dual = quadrant(sub_dual)
# 子集 B: 全量 439 窗（L1 侧: 299 非规则窗有 tier1;140 规则窗无 → 该子集 L1 记 both_wrong/L2 判定照常）
quad_full, pc_full = quadrant(both)

# 子集 C: 严格双层 299 窗（tier1 与补齐后 tier2 都有,干净四象限）
sub_dual_layer = [r for r in recs if r["tier1"] and get_t2(r)]
quad_299, pc_299 = quadrant(sub_dual_layer)

# ---- 三配置 ----
def acc_tactic(pool, getter):
    return round(sum(ok(r, "tactic", getter(r)["tactic"]["pred"]) for r in pool) / len(pool), 4)

def acc_exact(pool, getter):
    return round(sum(all(ok(r, q, getter(r)[q]["pred"]) for q in QS) for r in pool) / len(pool), 4)

def cascade(r):
    src = r["tier2"] if r["tier2"] else r["tier1"]
    return src

# L2 全量口径: 299 非规则窗可用 tier2(231 已有 + 68 补跑); 140 规则窗用补跑输出
def t2_any(r):
    return get_t2(r)

configs = {
    "L1_only": {"n": len(t1_all), "tactic": acc_tactic(t1_all, lambda r: r["tier1"]), "exact": acc_exact(t1_all, lambda r: r["tier1"])},
    "L1_to_L2_cascade": {"n": len(t1_all),
                         "tactic": acc_tactic(t1_all, cascade), "exact": acc_exact(t1_all, cascade)},
    "L2_only(conditional,231 escalated windows)": {"n": len(sub_dual), "tactic": acc_tactic(sub_dual, lambda r: r["tier2"]), "exact": acc_exact(sub_dual, lambda r: r["tier2"])},
    "L2_only(non-rule 299, dual-layer)": {"n": len(sub_dual_layer), "tactic": acc_tactic(sub_dual_layer, t2_any), "exact": acc_exact(sub_dual_layer, t2_any)},
    "L2_only(full 439, E-2 backfilled)": {"n": len(both), "tactic": acc_tactic(both, t2_any), "exact": acc_exact(both, t2_any)},
}

# 互补性量化（原 231 升级窗口径）
rescued = quad_dual["tactic"]["l2_only_correct"]
lost = quad_dual["tactic"]["l1_only_correct"]

# 全量 439 口径的 L2 vs L1 逐窗对比（299 窗两层都有输出）
both_layers = [r for r in recs if r["tier1"] and get_t2(r)]
l2_win = sum(1 for r in both_layers
             if (not ok(r, "tactic", r["tier1"]["tactic"]["pred"])) and ok(r, "tactic", get_t2(r)["tactic"]["pred"]))
l1_win = sum(1 for r in both_layers
             if ok(r, "tactic", r["tier1"]["tactic"]["pred"]) and (not ok(r, "tactic", get_t2(r)["tactic"]["pred"])))
tie = len(both_layers) - l2_win - l1_win

matrix = {
    "n_dual_output_windows": len(sub_dual),
    "n_full_backfilled_windows": len(both),
    "note": "四象限原口径=D1 逐题输出零 GPU 回放(231 升级窗); E-2 已补 208 窗 kev-0.8B@8023 同 serve 推理(kev208.jsonl,与 D1 tier2 同协议同模型,探针 conf 逐位一致),L2 全量 439 窗口径齐",
    "backfill_source": "kev208.jsonl (kev-0.8B v3 @8023, D1 tier2 同 serve/同协议; 140 规则窗 + 68 非规则未升级窗)",
    "quadrant_tactic": dict(quad_dual["tactic"]),
    "quadrant_exact": dict(quad_dual["exact"]),
    "quadrant_tactic_pct": {k: round(v / len(sub_dual), 4) for k, v in quad_dual["tactic"].items()},
    "quadrant_exact_pct": {k: round(v / len(sub_dual), 4) for k, v in quad_dual["exact"].items()},
    "per_gt_class_tactic": {k: v for k, v in sorted(pc_dual["tactic"].items())},
    "quadrant_full439_tactic": dict(quad_full["tactic"]),
    "quadrant_full439_exact": dict(quad_full["exact"]),
    "quadrant_full439_tactic_pct": {k: round(v / len(both), 4) for k, v in quad_full["tactic"].items()},
    "quadrant_full439_exact_pct": {k: round(v / len(both), 4) for k, v in quad_full["exact"].items()},
    "per_gt_class_tactic_full439": {k: v for k, v in sorted(pc_full["tactic"].items())},
    "quadrant_dual_layer_299_tactic": dict(quad_299["tactic"]),
    "quadrant_dual_layer_299_exact": dict(quad_299["exact"]),
    "quadrant_dual_layer_299_tactic_pct": {k: round(v / len(sub_dual_layer), 4) for k, v in quad_299["tactic"].items()},
    "quadrant_dual_layer_299_exact_pct": {k: round(v / len(sub_dual_layer), 4) for k, v in quad_299["exact"].items()},
    "per_gt_class_tactic_dual_layer_299": {k: v for k, v in sorted(pc_299["tactic"].items())},
    "configs": configs,
    "complementarity": {
        "escalated_windows_L2_rescues_tactic": rescued,
        "escalated_windows_L2_loses_tactic": lost,
        "net_tactic_gain_on_escalated": lost - rescued,
        "net_tactic_gain_share": round((lost - rescued) / len(sub_dual), 4),
        "full439_dual_layer_windows": len(both_layers),
        "full439_l2_wins_l1_loses_tactic": l2_win,
        "full439_l1_wins_l2_loses_tactic": l1_win,
        "full439_tie_or_both_same_tactic": tie,
    },
}
json.dump(matrix, open(f"{HERE}/matrix.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(matrix, ensure_ascii=False, indent=1))
