#!/usr/bin/env python3
"""B1-2 D1b: laya GPU 口径延迟补测（64 窗批，cuda device）
CPU 口径已有（D1 latency.json tier1 P50 1149.9ms）。输出 gpu_latency.json 追加双口径。
"""
import json, os, statistics, sys, time

sys.path.insert(0, "/home/xxl/MySecAgent/oracle-pipeline")
from tier1_laya import LayaTier, build_questions  # noqa: E402

SUITE = "/home/xxl/MySecAgent/lab/experiments/oracle/suites/oracle-v3/test.jsonl"
HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    laya = LayaTier(device="cuda")
    qs = build_questions()
    recs = []
    for line in open(SUITE):
        recs.append(json.loads(line))
        if len(recs) >= 64:
            break
    lats = []
    for i, r in enumerate(recs, 1):
        st = r["state"]
        state_text = "\n".join(st["raw_log_lines"]) if isinstance(st, dict) else str(st)
        t0 = time.time()
        laya.agent.predict(state_text, qs)
        lats.append((time.time() - t0) * 1000)
        if i % 16 == 0:
            print(f"[{i}/64] p50-so-far={statistics.median(lats):.1f}ms", flush=True)
    v = sorted(lats)
    out = {
        "device": "cuda", "n_windows": len(lats),
        "warm_model_resident": True,
        "p50_ms": round(statistics.median(lats), 1),
        "p90_ms": round(v[min(int(len(v) * 0.9), len(v) - 1)], 1),
        "mean_ms": round(statistics.mean(lats), 1),
        "note": "steady-state per-window, model resident (excl. load); 与 D1 latency.json tier1(CPU) 对照; GPU 与 serve 8018/8023 共卡",
    }
    with open(f"{HERE}/gpu_latency.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
