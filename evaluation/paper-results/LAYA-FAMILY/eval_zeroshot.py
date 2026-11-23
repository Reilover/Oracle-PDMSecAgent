#!/usr/bin/env python3
"""B-3: laya 家族三个官方 checkpoint 零样本评测 oracle-v3 test 439 窗四任务
laya-base(421M) / laya-multilingual(322M) / laya-typed-decisions(421M-td)
SDK 直调（Agent, 与 T4 训练版同接口），零样本（无我们安全域后训练）。
输出 ./zeroshot_<tag>.jsonl + 汇总 zeroshot.json
"""
import json, os, statistics, sys, time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, "/home/xxl/MySecAgent/lab/experiments/oracle/code/suite")
from pack_suite import (TACTIC_CRITERIA, TACTIC_INSTR, URGENT_INSTR, SEV_INSTR, SEV_CRIT,
                        ACTION_CRITERIA, ACTION_INSTR)  # noqa: E402
from laya.agent import Agent  # noqa: E402

FAMILY = {
    "laya-base": "/home/xxl/Mylocllm/laya-family/laya-base",
    "laya-multilingual": "/home/xxl/Mylocllm/laya-family/laya-multilingual",
    "laya-td": "/home/xxl/Mylocllm/laya-family/laya-typed-decisions",
}
SUITE = "/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3/test.jsonl"
HERE = os.path.dirname(os.path.abspath(__file__))
SEV = ["low", "medium", "high", "critical"]


def build_questions():
    return {
        "tactic": {"type": "choice", "instructions": TACTIC_INSTR, "criteria": dict(TACTIC_CRITERIA)},
        "urgent": {"type": "noul", "instructions": URGENT_INSTR["question"]},
        "severity": {"type": "choice", "instructions": SEV_INSTR["question"],
                     "criteria": {s: d for s, d in zip(SEV, SEV_CRIT)}},
        "action": {"type": "choice", "instructions": ACTION_INSTR, "criteria": dict(ACTION_CRITERIA)},
    }


def eval_ckpt(tag, path, recs, device="cuda"):
    out_path = f"{HERE}/zeroshot_{tag}.jsonl"
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path):
            try:
                done.add(json.loads(l)["id"])
            except Exception:
                pass
    agent = Agent(path, device=device)
    qs = build_questions()
    n = 0
    with open(out_path, "a") as fh:
        for rec in recs:
            rid = rec["_meta"]["id"]
            if rid in done:
                continue
            labels = rec["_meta"]["labels_full"]
            state = rec["state"]
            state_text = "\n".join(state["raw_log_lines"]) if isinstance(state, dict) else str(state)
            t0 = time.time()
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
            lat = (time.time() - t0) * 1000
            fh.write(json.dumps({"id": rid, "group": rec["_meta"]["group_id"],
                                 "label": {k: labels.get(k) for k in ("tactic", "urgent", "severity", "action")},
                                 "pred": pred, "conf": conf, "latency_ms": lat}, ensure_ascii=False) + "\n")
            n += 1
            if n % 40 == 0:
                print(f"{tag}: {n} new", flush=True)
    # stats
    rows = [json.loads(l) for l in open(out_path)]
    QS = ("tactic", "urgent", "severity", "action")
    acc = {}
    for q in QS:
        acc[q] = round(sum(1 for r in rows if r["pred"].get(q) == (r["label"][q] if q != "urgent" else bool(r["label"][q]))) / len(rows), 4)
    exact = round(sum(1 for r in rows if all(
        (r["pred"].get(q) == (bool(r["label"][q]) if q == "urgent" else r["label"][q])) for q in QS)) / len(rows), 4)
    lats = [r["latency_ms"] for r in rows]
    return {"n": len(rows), "tactic_acc": acc["tactic"], "urgent_acc": acc["urgent"],
            "severity_acc": acc["severity"], "action_acc": acc["action"], "exact_acc": exact,
            "latency_p50_ms": round(statistics.median(lats), 1)}


def main():
    recs = [json.loads(l) for l in open(SUITE)]
    summary = {}
    for tag, path in FAMILY.items():
        print(f"==== {tag} ====", flush=True)
        summary[tag] = eval_ckpt(tag, path, recs)
        print(tag, summary[tag], flush=True)
    summary["ours_laya_ft (T4 后训练版, 论文口径)"] = {"tactic": 0.657, "exact": 0.472,
                                                   "note": "early 470 窗 4-option 口径; 与零样本三线同表对照"}
    json.dump(summary, open(f"{HERE}/zeroshot.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
