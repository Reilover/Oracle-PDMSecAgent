#!/usr/bin/env python3
"""状态构建 + 窗口选择（移植 lab/experiments/oracle/code/suite/pack_suite.py，勿改源）
build_state: raw_log_lines + window_stats → 384 Qwen-token 紧凑 state（与训练同分布）。
select_windows: oracle-v3 test split 上选 20 窗 —— 分层抽样保证高/低置信 + 规则命中覆盖。
"""
import glob
import json
import os
import sys

SECAGENT = "/home/xxl/MySecAgent"
sys.path.insert(0, f"{SECAGENT}/lab/experiments/oracle/code/suite")
sys.path.insert(0, f"{SECAGENT}/judge")

# ---- state 构建（与 pack_suite.build_state 同口径）----
from pack_suite import build_state  # noqa: E402

RANGE_DATA = f"{SECAGENT}/range-data/batch1"
SUITE_V3 = f"{SECAGENT}/lab/experiments/oracle/suites/oracle-v3"
LAYA_TEST_ROWS = f"{SECAGENT}/lab/experiments/oracle/T4-LAYA/results_v3_test.jsonl"


def load_raw_index():
    """window_id → raw 记录路径（range-data/batch1 全量索引）"""
    idx = {}
    for p in glob.glob(f"{RANGE_DATA}/*/*.jsonl"):
        idx[p.rsplit("/", 1)[1][:-6]] = p
    return idx


def load_laya_rows():
    """T4 已有 test 逐条预测（选择分层用；管线内 laya 现场重打分）"""
    return {json.loads(l)["id"]: json.loads(l) for l in open(LAYA_TEST_ROWS)}


def window_record(rec, raw):
    """suite 记录 + 原始窗口 → 管线输入记录（state 用原 suite state，Tier0 用完整 stats）"""
    return {
        "id": rec["_meta"]["id"],
        "group": rec["_meta"]["group_id"],
        "source": rec["_meta"]["source"],
        "suite_state": rec["state"],
        "raw_lines": raw["state"]["raw_log_lines"],
        "window_stats": raw["state"].get("window_stats", {}),
        "labels": rec["_meta"].get("labels_full") or {},
        "scenario": raw.get("scenario"),
        "kind": raw.get("kind"),
    }


def laya_min_conf(row):
    """choice 题型（tactic/severity/action）的 min-max-prob（旧结果行无 urgent 概率，仅分层用）"""
    cs = [max(row["probs"][q].values()) for q in ("tactic", "severity", "action") if row["probs"].get(q)]
    return min(cs) if cs else 0.0


def select_windows(k=20, seed=20260928, quota=None):
    """分层选窗：规则命中(R) + 高置信(H ≥0.90) + 中(M 0.70–0.90) + 低(L <0.70)。
    默认 quota R4/H6/M6/L4（规则少截、轻层自动多数、升级/人工少量——对齐验收口径）。"""
    from rules import judge_rule
    import random

    quota = quota or {"rule": 4, "high": 6, "mid": 8, "low": 8}
    # 注：laya v3 校准温度（clamp 5）下 test split 无 min-conf≥0.90 的窗（high 池实测为 0），
    # quota 自动把高置信份额摊给 mid/low；实际选中数 = min(quota, 池大小) 之和。
    rng = random.Random(seed)
    raw_idx = load_raw_index()
    laya_rows = load_laya_rows()
    recs = [json.loads(l) for l in open(f"{SUITE_V3}/test.jsonl")]

    pools = {"rule": [], "high": [], "mid": [], "low": []}
    for rec in recs:
        rid = rec["_meta"]["id"]
        if rid not in raw_idx or rid not in laya_rows:
            continue
        raw = json.loads(open(raw_idx[rid]).readline())
        ev = {"raw_lines": raw["state"]["raw_log_lines"], "window_stats": raw["state"].get("window_stats", {})}
        hit = judge_rule(ev)
        m = laya_min_conf(laya_rows[rid])
        if hit:
            pools["rule"].append((rid, hit["rule_hit"], m))
        elif m >= 0.90:
            pools["high"].append((rid, None, m))
        elif m >= 0.70:
            pools["mid"].append((rid, None, m))
        else:
            pools["low"].append((rid, None, m))

    picked, meta = [], []
    for bucket, n in quota.items():
        pool = pools[bucket]
        # 低置信池优先取 conf 最低的（真难例），其余随机
        if bucket == "low":
            pool = sorted(pool, key=lambda x: x[2])[: max(n, len(pool) // 2)]
        take = rng.sample(pool, min(n, len(pool)))
        for rid, rhit, m in take:
            rec = next(r for r in recs if r["_meta"]["id"] == rid)
            raw = json.loads(open(raw_idx[rid]).readline())
            picked.append(window_record(rec, raw))
            meta.append({"id": rid, "bucket": bucket, "prior_rule_hit": rhit, "laya_prior_min_conf": round(m, 4)})
    return picked, meta, {b: len(v) for b, v in pools.items()}


if __name__ == "__main__":
    wins, meta, sizes = select_windows()
    print(json.dumps({"pool_sizes": sizes, "selected": meta}, ensure_ascii=False, indent=1))
