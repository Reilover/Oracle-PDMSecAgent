#!/usr/bin/env python3
"""D1-4B-TIER2 第①步: 全 439 窗 kev-4B v3 @8018 逐题输出采集

对 D1 全量 439 test 窗(231 升级窗 + 140 规则窗 + 68 未升级窗)逐窗打 kev-4B,
协议完全对齐 D1 tier2: 同 state_builder(build_all_windows 的 suite_state)、
同问题模板(build_questions 内嵌 pack_suite 模板)、同内嵌温度(serve head.pt 拟合温度)。
仅换 serve 端口 8018(kev-4B v3), 0.8B 版对照见 D2-ESCALATION/kev208.jsonl + D1 tier2。

输出: kev4b_439.jsonl(逐窗四题 pred/conf/probabilities/latency, 断点续跑)
"""
import json, os, sys, time

sys.path.insert(0, "/home/user/MySecAgent/oracle-pipeline")
from run_d1_full import build_all_windows  # noqa: E402
from tier2_kev import KevTier  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = f"{HERE}/kev4b_439.jsonl"
D1 = "/home/user/MySecAgent/lab/experiments/oracle/EVAL/D1-E2E/raw/d1_records.jsonl"
KEV_URL = "http://127.0.0.1:8018"  # kev-4B v3 serve (D1 单模型线同款)


def main():
    recs = [json.loads(l) for l in open(D1)]
    d1_ids = {r["window_id"] for r in recs}
    wins, pools, missing = build_all_windows()
    wins = [w for w in wins if w["id"] in d1_ids]
    print(f"[plan] D1 记录 {len(recs)} 窗 · 构建出 {len(wins)} 窗 · 待全量打 kev-4B@8018")

    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            try:
                done.add(json.loads(l)["window_id"])
            except Exception:
                pass
    todo = [w for w in wins if w["id"] not in done]
    print(f"[resume] 实际待跑 {len(todo)}")

    kev = KevTier(base_url=KEV_URL)
    if not kev.healthy():
        print("[abort] kev serve 8018 未就绪")
        sys.exit(2)

    t0 = time.time()
    with open(OUT, "a") as fh:
        for i, w in enumerate(todo):
            out = kev.decide(w["suite_state"])
            rec = {"window_id": w["id"], "tier": "kev4b@8018",
                   "labels": w.get("labels"),
                   "tier2_4b": {q: {"pred": a["pred"], "conf": a["conf"],
                                    "probabilities": a["probabilities"]}
                                for q, a in out["answers"].items()},
                   "latency_ms": out["latency_ms"]}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if (i + 1) % 25 == 0 or i + 1 == len(todo):
                el = time.time() - t0
                print(f"[{i+1}/{len(todo)}] {el:.0f}s", flush=True)
    print(f"[done] → {OUT}")


if __name__ == "__main__":
    main()
