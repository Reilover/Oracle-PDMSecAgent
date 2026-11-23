#!/usr/bin/env python3
"""Z-2: non-stealth 档双协议评测驱动（复用 eval_adversarial_probe_v3 的函数，windows 目录取参数）"""
import argparse, glob, json, os, sys
sys.path.insert(0, "/home/xxl/MySecAgent/lab/experiments/oracle/code/eval")
import eval_adversarial_probe_v3 as v3

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8018)
    ap.add_argument("--probe", required=True, help="目录，其下直接是 *.jsonl 窗文件")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    instructions = "Which MITRE ATT&CK tactic best matches this security alert?"
    dev = os.path.expanduser("~/MySecAgent/lab/experiments/oracle/suites/oracle-v3/development.jsonl")
    for line in open(dev):
        q = json.loads(line)["questions"].get("tactic")
        if q:
            instructions = q["instructions"]; break

    files = sorted(glob.glob(os.path.join(args.probe, "*.jsonl")))
    rows = []
    for f in files:
        rec = json.loads(open(f).readline())
        gt = (rec.get("labels") or {}).get("tactic") or "unknown"
        st_dep, how = v3.build_state(rec)
        st_vis = v3.visible_state(rec)
        try:
            p_dep, c_dep = v3.call_systemone(args.port, st_dep,
                                             {t: t.replace("_", " ") for t in v3.TACTICS}, instructions)
        except Exception as e:
            p_dep, c_dep = f"ERROR:{type(e).__name__}", None
        try:
            p_vis, c_vis = v3.call_systemone(args.port, st_vis,
                                             {t: t.replace("_", " ") for t in v3.TACTICS}, instructions)
        except Exception as e:
            p_vis, c_vis = f"ERROR:{type(e).__name__}", None
        rows.append({"window_id": rec["window_id"], "kind": rec.get("kind"),
                     "intensity": rec.get("intensity"), "gt": gt,
                     "pred_deploy": p_dep, "conf_deploy": c_dep, "trunc_deploy": how,
                     "pred_visible": p_vis, "conf_visible": c_vis,
                     "hit_deploy": p_dep == gt, "hit_visible": p_vis == gt})
        print(f"[{len(rows)}/{len(files)}] {rec.get('kind','?')} gt={gt} "
              f"deploy={p_dep}({c_dep}) visible={p_vis}({c_vis})", flush=True)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w") as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import defaultdict
    for tag, pk in (("deploy(build_state trunc)", "hit_deploy"), ("visible(payload kept)", "hit_visible")):
        hd = sum(r[pk] for r in rows)
        pkey = "pred_deploy" if pk == "hit_deploy" else "pred_visible"
        bm = sum(1 for r in rows if r[pkey] == "benign" and r["gt"] != "benign")
        gated = sum(1 for r in rows if r[pkey] != "benign" or (r.get(f'conf_{pkey.split("_")[1]}') or 0) < 0.90)
        print(f"\n=== {tag} ===  hits {hd}/{len(rows)} = {hd/max(len(rows),1):.3f}  benign-miss {bm}")
        by = defaultdict(lambda: [0, 0])
        for r in rows:
            by[r["kind"]][1] += 1
            by[r["kind"]][0] += int(r[pkey] == r["gt"])
        for k, (h, t) in sorted(by.items()):
            print(f"  {k}: {h}/{t} = {h/max(t,1):.3f}")

if __name__ == "__main__":
    main()
