#!/usr/bin/env python3
"""A2b-v3 去逐题类温度校准消融（laya，离线复算，439 窗 V3 test 口径）

与 a2b/recompute.py 协议完全一致，仅数据源换成 a2b-v3/results_439.jsonl
（439 窗，11-opt tactic 同 O3 现役口径）。
ckpt 内嵌温度 [4.843, 9.042, 9.223]（choice/score/noul），serve 侧 clamp 到 [0.5,5]
→ choice 桶实际 T=4.843491554260254（未超上限，clamp 不变）。
存储的 choice 题 probs = softmax(z/4.843)。去校准 = softmax(z/1) = p^4.843 归一化。
ECE 15 等宽分箱；choice 三题 = tactic/severity/action（urgent 无分布不参与）。
输出 result.json
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = f"{HERE}/results_439.jsonl"
T_CHOICE = 4.843491554260254  # 实际生效（未超上限，clamp 不变）
QS = ["tactic", "severity", "action"]  # choice 题（score/noul 无存概率，不参与本消融）

def ece(pairs, bins=15):
    n = len(pairs); tot = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        grp = [(p, c) for p, c in pairs if (lo <= p < hi) or (b == bins - 1 and p == 1.0)]
        if not grp: continue
        acc = sum(c for _, c in grp) / len(grp); conf = sum(p for p, _ in grp) / len(grp)
        tot += len(grp) / n * abs(acc - conf)
    return round(tot, 4)

rows = [json.loads(l) for l in open(ROWS)]

def stats(mode):
    pairs = []; tactic = exact = exact4 = 0
    for r in rows:
        ok_all = ok_t = None
        for q in QS:
            pr = r["probs"][q]
            if mode == "calib":
                p1 = pr
            else:  # 去校准: p^T 归一
                raw = {k: v ** T_CHOICE for k, v in pr.items()}
                s = sum(raw.values()); p1 = {k: v / s for k, v in raw.items()}
            top = max(p1, key=p1.get); ok = top == r["label"][q]
            if q == "tactic": ok_t = ok
            elif ok_all is None: ok_all = ok
            else: ok_all = ok_all and ok
            pairs.append((p1[top], ok))
        ok_all = ok_all and (r["pred"]["urgent"] == bool(r["label"]["urgent"]))
        tactic += ok_t; exact += ok_all
        exact4 += (ok_t and ok_all)  # 补充口径: 含 tactic 的四题全对（a2b 原协议不含 tactic）
    n = len(rows)
    return {"n_windows": n, "tactic_acc": round(tactic / n, 4), "exact_acc": round(exact / n, 4),
            "exact_acc_all4_suppl": round(exact4 / n, 4),
            "ece_3choiceq": ece(pairs), "mean_conf": round(sum(p for p, _ in pairs) / len(pairs), 4)}

res = {
    "model": "laya-421M oracle-v3 (T4-LAYA/laya-oracle-v3)",
    "data": "a2b-v3/results_439.jsonl 439 窗（oracle-v3 test, 11-opt tactic, 与 O3 现役 zeroshot_ours_v3 同口径同 pred）",
    "temperatures": {"fitted_raw": [4.843, 9.042, 9.223], "effective_clamped": [4.843, 5.0, 5.0],
                     "note": "仅 choice 桶（4.843）实际影响 choice 题 probs；score/noul 超 5 被 clamp"},
    "with_calibration (T_choice=4.84)": stats("calib"),
    "without_calibration (T=1)": stats("raw"),
}
json.dump(res, open(f"{HERE}/result.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
