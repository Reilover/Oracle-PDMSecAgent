#!/usr/bin/env python3
"""C1 探针 non-stealth（高强度）档构造器——Z-2 补档 2026-09-29

与 gen_adversarial_probe.py（stealth 档）同骨架同载荷池，差异仅注入强度：
  - stealth（原版）: 注入 1-4 条载荷行（spray 3 行模板×1）
  - non-stealth（本档）: 注入 6-12 条载荷行（spray 3 行模板×3-4），seed=20260929
其余（骨架池过滤、配比 50 窗、截断保注入、window_stats 同构、标签全档高危）与原版一致。
输出: windows_nonstealth/ 50 窗 + PROBE-MANIFEST-NONSTEALTH.json
"""
import argparse, datetime, glob, hashlib, json, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 复用原版生成器的载荷/标签/配比/工具函数（import 不执行其 main）
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "genstealth", os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen_adversarial_probe.py"))
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)

PAYLOADS, CLASS_LABELS, QUOTA = _gen.PAYLOADS, _gen.CLASS_LABELS, _gen.QUOTA
window_stats, render, pick_skeletons = _gen.window_stats, _gen.render, _gen.pick_skeletons

OUT = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260929)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    wdir = f"{OUT}/windows_nonstealth"
    os.makedirs(wdir, exist_ok=True)
    for f in glob.glob(f"{wdir}/*.jsonl"):
        os.remove(f)

    plan = [c for c, k in QUOTA.items() for _ in range(k)]
    rng.shuffle(plan)
    skeletons = pick_skeletons(rng, len(plan))
    manifest = {"seed": args.seed, "intensity": "non-stealth",
                "generator": "gen_adversarial_probe_nonstealth.py",
                "skeleton_pool": _gen.RANGE_DIR, "quota": QUOTA,
                "injection": "6-12 payload lines per window (stealth=1-4); spray 3-line template x3-4", "windows": []}

    for i, (cls, sk_path) in enumerate(zip(plan, skeletons)):
        sk = json.loads(open(sk_path).read())
        lines = list(sk["state"]["raw_log_lines"])
        tpls = PAYLOADS[cls]
        n_inj = rng.randint(6, 12) if cls != "spray_disguised" else rng.choice([9, 12])
        idxs = sorted(rng.sample(range(len(lines) + 1), k=min(n_inj, len(lines) + 1)), reverse=True)
        injected = []
        for pos in idxs:
            ref = lines[min(pos, len(lines) - 1)] if lines else ""
            sel = (tpls if cls == "spray_disguised" else rng.sample(tpls, k=1))
            # non-stealth: spray 每位 3 行模板全渲染 ×3 组
            reps = 1 if cls != "spray_disguised" else 3
            for _ in range(reps):
                for t in sel:
                    r_line = render(t, rng, ref)
                    injected.append(r_line)
                    lines.insert(pos, r_line)
        lines = lines[:100]
        inj_survived = sum(1 for l in lines if l in injected)
        if inj_survived == 0 and lines:
            lines = lines[:-1] + [injected[0]]
        wid = f"advns-{cls}-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{i:04d}"
        lab = dict(CLASS_LABELS[cls])
        rec = {
            "window_id": wid, "batch": "adv-probe", "scenario": f"adv_{cls}",
            "kind": cls, "intensity": "non-stealth", "outcome": "injected",
            "time_range": sk["time_range"],
            "state": {"raw_log_lines": lines, "window_stats": window_stats(lines)},
            "labels": lab,
            "meta": {"tool": "adversarial-injector-nonstealth", "src_ips": sorted(set(_gen.ATTACK_SRC_POOL)),
                     "adv_probe": {"injected_class": cls, "n_injected_lines": len(injected),
                                   "skeleton_window_id": sk["window_id"],
                                   "skeleton_labels_tactic": sk["labels"]["tactic"], "seed": args.seed}},
        }
        with open(f"{wdir}/{wid}.jsonl", "w") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        manifest["windows"].append({"window_id": wid, "class": cls, "skeleton": sk["window_id"],
                                    "n_injected": len(injected), "n_lines": len(lines),
                                    "gt_tactic": lab["tactic"]})
    with open(f"{OUT}/PROBE-MANIFEST-NONSTEALTH.json", "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    from collections import Counter
    c = Counter(w["class"] for w in manifest["windows"])
    inj = [w["n_injected"] for w in manifest["windows"]]
    print(f"== non-stealth 探针 {len(manifest['windows'])} 窗 -> {wdir}")
    for k, v in sorted(c.items()):
        print(f"  {k}: {v}")
    print(f"注入行数: min={min(inj)} max={max(inj)} mean={sum(inj)/len(inj):.1f}")


if __name__ == "__main__":
    main()
