#!/usr/bin/env python3
"""E-2: 补 208 窗 kev-only 推理（D2 归因扩到全量 439 窗）

D1 全量 439 窗中 tier2 已有 231 窗（D1 运行时升级）,缺:
  - 140 规则窗（tier0 命中,从未走模型层）
  - 68 非规则未升级窗（tier1 有,tier2 无）
共 208 窗,用 kev-0.8B v3 serve @8023 补齐——与 D1 tier2 完全同协议
(同 state_builder suite_state / 同问题模板 / 同 serve,探针验证 conf 逐位一致;
注意: D1 tier2 就是 8023 上的 kev-0.8B,不是 8018 的 4B,故此处对齐用 8023)。

输出: kev208.jsonl（逐窗四题 pred/conf/probabilities/latency,断点续跑）
"""
import json, os, sys, time

sys.path.insert(0, "/home/user/MySecAgent/oracle-pipeline")
from run_d1_full import build_all_windows  # noqa: E402
from tier2_kev import KevTier  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = f"{HERE}/kev208.jsonl"
D1 = "/home/user/MySecAgent/lab/experiments/oracle/EVAL/D1-E2E/raw/d1_records.jsonl"
KEV_URL = "http://127.0.0.1:8023"  # kev-0.8B v3, D1 tier2 同 serve


def main():
    recs = [json.loads(l) for l in open(D1)]
    have_t2 = {r["window_id"] for r in recs if r["tier2"]}
    wins, pools, _ = build_all_windows()
    todo = [w for w in wins if w["id"] not in have_t2]
    print(f"[plan] 439 窗 · 已有 tier2 {len(have_t2)} · 待补 {len(todo)}")

    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            try:
                done.add(json.loads(l)["window_id"])
            except Exception:
                pass
    todo = [w for w in todo if w["id"] not in done]
    print(f"[resume] 实际待跑 {len(todo)}")

    kev = KevTier(base_url=KEV_URL)
    if not kev.healthy():
        print("[abort] kev serve 8023 未就绪")
        sys.exit(2)

    t0 = time.time()
    with open(OUT, "a") as fh:
        for i, w in enumerate(todo):
            out = kev.decide(w["suite_state"])
            rec = {"window_id": w["id"], "tier": "kev08@8023",
                   "labels": w.get("labels"),
                   "tier2_backfill": {q: {"pred": a["pred"], "conf": a["conf"],
                                          "probabilities": a["probabilities"]}
                                      for q, a in out["answers"].items()},
                   "latency_ms": out["latency_ms"]}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if (i + 1) % 20 == 0 or i + 1 == len(todo):
                el = time.time() - t0
                print(f"[{i+1}/{len(todo)}] {el:.0f}s", flush=True)
    print(f"[done] → {OUT}")


if __name__ == "__main__":
    main()
