#!/usr/bin/env python3
"""Z-3: NanoJev 选项顺序翻转评测（嵌入式 DecisionPredictor 直调，不起 8765 HTTP——历史上被占用）
原序 11 tactic vs 全反转序，55 dev 窗，与 eval_option_order.py 同协议。
输出 ./results_nanojev_v3.jsonl
"""
import json, os, statistics, sys

sys.path.insert(0, '/home/user/Mylocllm/NanoJev/scripts')
sys.path.insert(0, '/home/user/MySecAgent/lab/experiments/oracle/code/suite')
from pack_suite import TACTIC_CRITERIA, TACTIC_INSTR  # noqa: E402

TACTICS = ['benign', 'reconnaissance', 'initial_access', 'execution', 'persistence',
           'privilege_escalation', 'defense_evasion', 'credential_access',
           'discovery', 'command_and_control', 'exfiltration']
REV = list(reversed(TACTICS))
SUITE = "/home/user/MySecAgent/lab/experiments/oracle/suites/oracle-v3/development.jsonl"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results_nanojev_v3.jsonl")


def qs_with_order(order):
    return {'tactic': {'type': 'choice', 'instructions': TACTIC_INSTR,
                       'criteria': {t: t.replace("_", " ") for t in order}}}


def main():
    from predict_toy_decisions import DecisionPredictor
    eng = DecisionPredictor('/home/user/Mylocllm/NanoJev/checkpoints/NanoJev-unified',
                            precision='bf16', disable_native_triton=True)
    recs = []
    for line in open(SUITE):
        recs.append(json.loads(line))
        if len(recs) >= 55:
            break
    rows = []
    for i, r in enumerate(recs, 1):
        state_text = "\n".join(r["state"]["raw_log_lines"]) if isinstance(r["state"], dict) else str(r["state"])
        gt = r["questions"]["tactic"]["label"]
        try:
            a1 = eng.predict({'states': [{'id': 's0', 'state': state_text, 'questions': qs_with_order(TACTICS)}]})['states'][0]['answers']['tactic']
            p1, pr1 = a1.get('choice'), (a1.get('probabilities') or {})
            c1 = max(pr1.values()) if pr1 else None
            a2 = eng.predict({'states': [{'id': 's0', 'state': state_text, 'questions': qs_with_order(REV)}]})['states'][0]['answers']['tactic']
            p2, pr2 = a2.get('choice'), (a2.get('probabilities') or {})
            c2 = max(pr2.values()) if pr2 else None
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
    d = [abs(r["conf_orig"] - r["conf_rev"]) for r in rows if r["conf_orig"] is not None and r["conf_rev"] is not None]
    print(f"\n=== NanoJev 选项顺序翻转 ===")
    print(f"翻转率: {flip}/{len(rows)} = {flip/len(rows):.3f}  双序均对: {both}/{len(rows)}")
    if d:
        print(f"|dconf| mean={statistics.mean(d):.4f} median={statistics.median(d):.4f} max={max(d):.4f}")


if __name__ == "__main__":
    main()
