#!/usr/bin/env python3
"""A2b-v3 门控份额消融（离线复算，439 窗 V3 test 口径）

与 a2b/recompute_gating.py 协议完全一致，仅数据源换成 a2b-v3/results_439.jsonl。
choice 题 probs = softmax(z/4.843491554260254)，T=1 口径 raw = p^4.843 归一化，
D1 同款门控（τ=0.90 / τ_h=0.70，conf=max prob）：
  - 题级：auto / confirm / escalate 份额
  - 窗级：任一题 escalate → 整窗升 Tier2（对齐 D1 窗口级路由）
输出 gating_share.json
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = f"{HERE}/results_439.jsonl"
T_CHOICE = 4.843491554260254
QS = ["tactic", "severity", "action"]  # 有存档概率的 choice 题（urgent 无存概率，不参与）
TAU, TAU_H = 0.90, 0.70


def gate(conf):
    if conf >= TAU:
        return "auto"
    if conf >= TAU_H:
        return "confirm"
    return "escalate"


rows = [json.loads(l) for l in open(ROWS)]


def stats(mode):
    from collections import Counter
    q_gates = Counter()
    win_escalate = 0
    for r in rows:
        any_esc = False
        for q in QS:
            pr = r["probs"][q]
            if mode != "calib":  # 去校准: p^T 归一
                raw = {k: v ** T_CHOICE for k, v in pr.items()}
                s = sum(raw.values())
                pr = {k: v / s for k, v in raw.items()}
            conf = max(pr.values())
            g = gate(conf)
            q_gates[g] += 1
            if g == "escalate":
                any_esc = True
        if any_esc:
            win_escalate += 1
    nq = len(rows) * len(QS)
    return {
        "n_windows": len(rows),
        "n_questions": nq,
        "question_level": {
            "auto_share": round(q_gates["auto"] / nq, 4),
            "confirm_share": round(q_gates["confirm"] / nq, 4),
            "escalate_share": round(q_gates["escalate"] / nq, 4),
        },
        "window_level_escalate_share(任一题escalate→整窗升Tier2)": round(win_escalate / len(rows), 4),
    }


res = {
    "model": "laya-421M oracle-v3, 门控回放协议与 D1 同款 (tau=0.90, tau_h=0.70)",
    "data": "a2b-v3/results_439.jsonl 439 窗 choice 三题 (tactic/severity/action；urgent 无存档概率不参与)",
    "note": "choice 桶 T=4.843 为实际生效温度（score/noul 桶超 5 被 clamp，与 choice 题无关）；conf=max prob",
    "with_calibration (T_choice=4.84)": stats("calib"),
    "without_calibration (T=1)": stats("raw"),
}
json.dump(res, open(f"{HERE}/gating_share.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
