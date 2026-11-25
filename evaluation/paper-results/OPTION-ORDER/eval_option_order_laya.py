#!/usr/bin/env python3
"""Z-3: laya 选项顺序翻转评测（SDK 直调，协议同 eval_option_order.py）
原序 11 tactic vs 全反转序，55 dev 窗。温度用 ckpt 内嵌 head.pt 拟合口径（Agent 默认应用）。
输出 ./results_laya_v3.jsonl
"""
import json, os, statistics, sys

sys.path.insert(0, "/home/user/MySecAgent/oracle-pipeline")
from tier1_laya import LayaTier, build_questions  # noqa: E402

TACTICS = ['benign', 'reconnaissance', 'initial_access', 'execution', 'persistence',
           'privilege_escalation', 'defense_evasion', 'credential_access',
           'discovery', 'command_and_control', 'exfiltration']
REV = list(reversed(TACTICS))
SUITE = "/home/user/MySecAgent/lab/experiments/oracle/suites/oracle-v3/development.jsonl"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results_laya_v3.jsonl")


def qs_with_order(order):
    qs = build_questions()
    qs["tactic"]["criteria"] = {t: t.replace("_", " ") for t in order}
    return qs


def main():
    laya = LayaTier(device="cpu")
    recs = []
    for line in open(SUITE):
        r = json.loads(line)
        recs.append(r)
        if len(recs) >= 55:
            break
    rows = []
    for i, r in enumerate(recs, 1):
        st = r["state"]
        state_text = "\n".join(st["raw_log_lines"]) if isinstance(st, dict) else str(st)
        gt = r["questions"]["tactic"]["label"]
        try:
            a1 = laya.agent.predict(state_text, qs_with_order(TACTICS))["answers"]["tactic"]
            p1 = max(a1["probabilities"], key=a1["probabilities"].get)
            c1 = max(a1["probabilities"].values())
            a2 = laya.agent.predict(state_text, qs_with_order(REV))["answers"]["tactic"]
            p2 = max(a2["probabilities"], key=a2["probabilities"].get)
            c2 = max(a2["probabilities"].values())
        except Exception as e:
            p1 = p2 = f"ERROR:{type(e).__name__}"; c1 = c2 = None
        flip = (p1 != p2)
        rows.append({"id": r.get("_meta", {}).get("id", str(i)), "gt": gt,
                     "pred_orig": p1, "pred_rev": p2, "conf_orig": c1, "conf_rev": c2, "flip": flip})
        print(f"[{i}/{len(recs)}] gt={gt} orig={p1} rev={p2} {'FLIP' if flip else 'stable'}", flush=True)
    with open(OUT, "w") as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")
    flip = sum(r["flip"] for r in rows)
    both = sum(1 for r in rows if r["pred_orig"] == r["gt"] and r["pred_rev"] == r["gt"])
    d = [abs(r["conf_orig"] - r["conf_rev"]) for r in rows if r["conf_orig"] is not None]
    print(f"\n=== laya 选项顺序翻转 ===")
    print(f"翻转率: {flip}/{len(rows)} = {flip/len(rows):.3f}  双序均对: {both}/{len(rows)}")
    print(f"|dconf| mean={statistics.mean(d):.4f} median={statistics.median(d):.4f} max={max(d):.4f}")


if __name__ == "__main__":
    main()
