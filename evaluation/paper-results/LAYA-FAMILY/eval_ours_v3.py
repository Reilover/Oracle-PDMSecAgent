#!/usr/bin/env python3
"""E-4: ours T4 laya-421M v3 后训练版在 oracle-v3 test 439 窗 11-opt 同口径重评

三官方 ckpt 零样本(B-3)用的就是 oracle-v3 439 窗 11 类 tactic 选项空间;
遗留缺口是 ours 行——旧 0.657/0.472 来自早期 470 窗卷(items-v3 早期版),
本脚本把 T4 ckpt 按 eval_zeroshot.py 完全同协议(SDK 直调、同 state 同问题模板)
在 suites/oracle-v3/test.jsonl 439 窗上重评,产出严格同表可比的 ours 行。

输出 ./zeroshot_ours_v3.jsonl + 更新 zeroshot.json
"""
import json, os, statistics, sys, time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, "/home/xxl/MySecAgent/lab/experiments/oracle/code/suite")
from pack_suite import (TACTIC_CRITERIA, TACTIC_INSTR, URGENT_INSTR, SEV_INSTR, SEV_CRIT,
                        ACTION_CRITERIA, ACTION_INSTR)  # noqa: E402
from laya.agent import Agent  # noqa: E402

CKPT = "/home/xxl/MySecAgent/lab/experiments/oracle/T4-LAYA/laya-oracle-v3"
SUITE = "/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3/test.jsonl"
HERE = os.path.dirname(os.path.abspath(__file__))
SEV = ["low", "medium", "high", "critical"]
OUT = f"{HERE}/zeroshot_ours_v3.jsonl"


def build_questions():
    return {
        "tactic": {"type": "choice", "instructions": TACTIC_INSTR, "criteria": dict(TACTIC_CRITERIA)},
        "urgent": {"type": "noul", "instructions": URGENT_INSTR["question"]},
        "severity": {"type": "choice", "instructions": SEV_INSTR["question"],
                     "criteria": {s: d for s, d in zip(SEV, SEV_CRIT)}},
        "action": {"type": "choice", "instructions": ACTION_INSTR, "criteria": dict(ACTION_CRITERIA)},
    }


def main():
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
                pred, conf = {}, {}
                for k, q in qs.items():
                    a = answers.get(k, {}) or {}
                    if q["type"] == "choice":
                        pr = a.get("probabilities") or {}
                        top = max(pr, key=pr.get) if pr else None
                        pred[k] = top; conf[k] = round(max(pr.values()), 4) if pr else None
                    else:
                        v = float(a.get("noul", 0) or 0)
                        pred[k] = bool(v >= 0.5); conf[k] = round(max(v, 1 - v), 4)
            except Exception as e:
                pred = {"error": f"{type(e).__name__}"}; conf = {}
            lat = (time.time() - tw) * 1000
            fh.write(json.dumps({"id": rid, "group": rec["_meta"]["group_id"],
                                 "label": {k: labels.get(k) for k in ("tactic", "urgent", "severity", "action")},
                                 "pred": pred, "conf": conf, "latency_ms": lat}, ensure_ascii=False) + "\n")
            n += 1
            if n % 40 == 0:
                print(f"ours_v3: {n} new {time.time()-t0:.0f}s", flush=True)
    # stats
    rows = [json.loads(l) for l in open(OUT)]
    QSq = ("tactic", "urgent", "severity", "action")
    acc = {}
    for q in QSq:
        acc[q] = round(sum(1 for r in rows if r["pred"].get(q) == (r["label"][q] if q != "urgent" else bool(r["label"][q]))) / len(rows), 4)
    exact = round(sum(1 for r in rows if all(
        (r["pred"].get(q) == (bool(r["label"][q]) if q == "urgent" else r["label"][q])) for q in QSq)) / len(rows), 4)
    lats = [r["latency_ms"] for r in rows]
    stats = {"n": len(rows), "tactic_acc": acc["tactic"], "urgent_acc": acc["urgent"],
             "severity_acc": acc["severity"], "action_acc": acc["action"], "exact_acc": exact,
             "latency_p50_ms": round(statistics.median(lats), 1)}
    summary = json.load(open(f"{HERE}/zeroshot.json"))
    summary["ours_laya_ft (T4 后训练版, oracle-v3 439 窗 11-opt 同口径, E-4 重评)"] = stats
    json.dump(summary, open(f"{HERE}/zeroshot.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
