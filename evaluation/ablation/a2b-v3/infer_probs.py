#!/usr/bin/env python3
"""A2b-v3 step1: laya-oracle-v3 在 439 窗 V3 test 上重推理并落盘逐题完整概率分布

与 EVAL/LAYA-FAMILY/eval_ours_v3.py 完全同协议（同 ckpt、同 suites/oracle-v3/test.jsonl、
同 SDK 直调、同问题模板 build_questions），唯一差别是 choice 三题（tactic/severity/action）
把完整 probabilities 字典逐题写入 results_439.jsonl（取 probabilities 的写法参考
EVAL/UNIFORM-BF16/run_uniform.py 的 run_e2_laya），urgent 仍只有 noul 标量。

门控校验（必过）：推理 argmax 必须逐窗复现 O3 现役 zeroshot_ours_v3.jsonl 的 pred
（tactic 0.724 / exact 0.522）。不等到 = 协议漂移，退出码 1，后续复算不得执行。

断点续跑：按已写 id 跳过。产物只写本目录，源目录与 suites 只读。
"""
import json, os, statistics, sys, time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, "/home/xxl/MySecAgent/lab/experiments/oracle/code/suite")
from pack_suite import (TACTIC_CRITERIA, TACTIC_INSTR, URGENT_INSTR, SEV_INSTR, SEV_CRIT,
                        ACTION_CRITERIA, ACTION_INSTR)  # noqa: E402
from laya.agent import Agent  # noqa: E402

CKPT = "/home/xxl/MySecAgent/lab/experiments/oracle/T4-LAYA/laya-oracle-v3"
SUITE = "/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3/test.jsonl"
REF = "/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/LAYA-FAMILY/zeroshot_ours_v3.jsonl"
HERE = os.path.dirname(os.path.abspath(__file__))
SEV = ["low", "medium", "high", "critical"]
OUT = f"{HERE}/results_439.jsonl"
GATE_JSON = f"{HERE}/gate_check.json"
QS = ("tactic", "urgent", "severity", "action")
CHOICE_QS = ("tactic", "severity", "action")


def build_questions():
    return {
        "tactic": {"type": "choice", "instructions": TACTIC_INSTR, "criteria": dict(TACTIC_CRITERIA)},
        "urgent": {"type": "noul", "instructions": URGENT_INSTR["question"]},
        "severity": {"type": "choice", "instructions": SEV_INSTR["question"],
                     "criteria": {s: d for s, d in zip(SEV, SEV_CRIT)}},
        "action": {"type": "choice", "instructions": ACTION_INSTR, "criteria": dict(ACTION_CRITERIA)},
    }


def infer():
    recs = [json.loads(l) for l in open(SUITE)]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            try:
                done.add(json.loads(l)["id"])
            except Exception:
                pass
    agent = Agent(CKPT, device="cuda")
    qs = build_questions()
    n = 0
    t0 = time.time()
    with open(OUT, "a") as fh:
        for rec in recs:
            rid = rec["_meta"]["id"]
            if rid in done:
                continue
            labels = rec["_meta"]["labels_full"]
            state = rec["state"]
            state_text = "\n".join(state["raw_log_lines"]) if isinstance(state, dict) else str(state)
            tw = time.time()
            try:
                resp = agent.predict(state_text, qs)
                answers = resp.get("answers", resp) if isinstance(resp, dict) else resp
                pred, conf, probs = {}, {}, {}
                for k, q in qs.items():
                    a = answers.get(k, {}) or {}
                    if q["type"] == "choice":
                        pr = a.get("probabilities") or {}
                        top = max(pr, key=pr.get) if pr else None
                        pred[k] = top; conf[k] = round(max(pr.values()), 4) if pr else None
                        probs[k] = {kk: round(vv, 4) for kk, vv in pr.items()}  # 完整分布落盘
                    else:
                        v = float(a.get("noul", 0) or 0)
                        pred[k] = bool(v >= 0.5); conf[k] = round(max(v, 1 - v), 4)
            except Exception as e:
                pred = {"error": f"{type(e).__name__}"}; conf = {}; probs = {}
            lat = (time.time() - tw) * 1000
            fh.write(json.dumps({"id": rid, "group": rec["_meta"]["group_id"],
                                 "label": {k: labels.get(k) for k in QS},
                                 "pred": pred, "conf": conf, "probs": probs,
                                 "latency_ms": lat}, ensure_ascii=False) + "\n")
            n += 1
            if n % 40 == 0:
                print(f"a2b-v3 infer: {n} new {time.time()-t0:.0f}s", flush=True)
    print(f"infer done: +{n} new in {time.time()-t0:.0f}s -> {OUT}", flush=True)


def gate_check():
    rows = [json.loads(l) for l in open(OUT)]
    ref = {r["id"]: r for r in map(json.loads, open(REF))}
    assert len(rows) == len(ref) == 439, f"row count mismatch: {len(rows)} vs {len(ref)}"
    mismatch = []
    for r in rows:
        rr = ref[r["id"]]
        for q in QS:
            a, b = r["pred"].get(q), rr["pred"].get(q)
            if q == "urgent":
                a, b = bool(a), bool(b)
            if a != b:
                mismatch.append((r["id"], q, a, b))
    n = len(rows)
    tac = sum(1 for r in rows if r["pred"].get("tactic") == r["label"]["tactic"])
    ex = sum(1 for r in rows if all(r["pred"].get(q) == (bool(r["label"][q]) if q == "urgent" else r["label"][q]) for q in QS))
    res = {
        "n_windows": n,
        "pred_full_match_vs_zeroshot_ours_v3": len(mismatch) == 0,
        "n_mismatch": len(mismatch),
        "mismatch_examples": mismatch[:10],
        "tactic_acc": round(tac / n, 4),
        "exact_acc": round(ex / n, 4),
        "expected": {"tactic_acc": 0.724, "exact_acc": 0.522},
    }
    json.dump(res, open(GATE_JSON, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return res["pred_full_match_vs_zeroshot_ours_v3"]


if __name__ == "__main__":
    infer()
    ok = gate_check()
    sys.exit(0 if ok else 1)
