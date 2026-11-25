#!/usr/bin/env python3
"""B2-A2 去温度校准消融（零 GPU 离线复算）
kev-4B head.pt T=2.0467 (方法A) vs T=1.0，oracle-v3 test rows.json（raw logits, inference_temperature=1.0）
复算 tactic/exact/ECE 前后对照。输出 result.json
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = "/home/user/MySecAgent/lab/experiments/oracle/T1-KEV4B/round3-v3/bench-test/rows.json"
T_FIT = 2.04674778399355

def softmax(v):
    m = max(v); e = [math.exp(x - m) for x in v]; s = sum(e)
    return [x / s for x in e]

def stats(rows, T):
    byq = {}
    for r in rows:
        if r.get("variant") != "clean" or r.get("source") == "unknowable":
            continue
        z = r["logits"]
        p = softmax([v / T for v in z]) if T != 1.0 else r["p"]
        pred = max(range(len(p)), key=lambda i: p[i])
        byq.setdefault(r["group"], {})[r["question"]] = (pred == r["label"], max(p))
    n = len(byq)
    tactic = sum(1 for w in byq.values() if w.get("tactic", (False,))[0])
    exact = sum(1 for w in byq.values() if all(w.get(q, (False,))[0] for q in ("tactic", "urgent", "severity", "action")))
    # ECE question-level (15 bins) over all 4 questions
    pairs = [(c, ok) for w in byq.values() for ok, c in w.values()]
    bins = 15; tot = 0.0; nn = len(pairs)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        grp = [(p, c) for p, c in pairs if (lo <= p < hi) or (b == bins - 1 and p == 1.0)]
        if not grp: continue
        acc = sum(c for _, c in grp) / len(grp); conf = sum(p for p, _ in grp) / len(grp)
        tot += len(grp) / nn * abs(acc - conf)
    return {"n_windows": n, "tactic_acc": round(tactic / n, 4), "exact_acc": round(exact / n, 4),
            "ece_question_level": round(tot, 4),
            "mean_conf": round(sum(p for p, _ in pairs) / nn, 4)}

rows = json.loads(open(ROWS).read())
res = {
    "model": "kev-4B v3 (runs/oracle-kev4b-v3)",
    "data": "oracle-v3 test 439 窗 (bench-test rows.json, raw logits)",
    "with_temperature_calibration (T=2.0467)": stats(rows, T_FIT),
    "without_temperature_calibration (T=1.0)": stats(rows, 1.0),
}
json.dump(res, open(f"{HERE}/result.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
