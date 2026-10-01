#!/usr/bin/env python3
"""ORACLE 置信升级管线编排器：rules → laya → (升级的) → kev → (仍低的) → 人工 CLI

用法（spark2_5 venv）:
  python3 run_pipeline.py --windows 20 --non-interactive y \
      --audit logs/audit.jsonl --windows-json logs/windows.json

延迟分解 / 路由统计自动落 logs/routing_summary.json。
"""
import argparse
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from state_builder import select_windows  # noqa: E402
from tier0_rules import tier0  # noqa: E402
import gating  # noqa: E402


def process_window(window, laya, kev, audit, non_interactive="y"):
    """单窗全管线。返回路由记录（含延迟分解与逐题分布）。"""
    t_start = time.time()
    wid = window["id"]
    lat = {"state_ms": None, "tier0_ms": None, "tier1_ms": None, "tier2_ms": None,
           "gate_ms": 0.0, "human_ms": None}
    route = {"window_id": wid, "path": [], "rule_hit": None, "human": None,
             "questions": {}, "final": {}}

    # ---- Tier 0 规则 ----
    t0 = time.time()
    rule_out = tier0(window)
    lat["tier0_ms"] = (time.time() - t0) * 1000
    if rule_out:
        route["path"].append("tier0_rule")
        route["rule_hit"] = rule_out["rule_id"]
        route["final"] = {q: {"pred": v, "conf": 1.0, "source": "rule"} for q, v in rule_out["verdict"].items()}
        audit.append(window_id=wid, event="window_done", rule_id=rule_out["rule_id"],
                     verdict=rule_out["verdict"], route=route,
                     latency_ms={k: (round(v, 3) if v is not None else None) for k, v in lat.items()},
                     labels=window.get("labels"), tier1_dists=None, tier2_dists=None,
                     total_ms=(time.time() - t_start) * 1000)
        rec = {"window_id": wid, "latency": lat, "route": route,
               "tier1": None, "tier2": None}
        return rec

    # ---- state（沿用 suite 同口径构建；此处计时用缓存的预构建） ----
    t0 = time.time()
    state = window["suite_state"]
    lat["state_ms"] = (time.time() - t0) * 1000  # 构建已在 selection 阶段完成，此处为取用

    # ---- Tier 1 laya ----
    t1_out = laya.decide(state)
    lat["tier1_ms"] = t1_out["latency_ms"]
    route["path"].append("tier1_laya")
    g1 = gating.gate_all(t1_out["answers"])
    t0 = time.time()
    if gating.needs_tier2(g1):
        pass  # 判定本身在 gate_all；此处仅计量汇总开销
    lat["gate_ms"] += (time.time() - t0) * 1000

    route["questions"] = {q: {"tier1": {"pred": a["pred"], "conf": round(a["conf"], 4),
                                        "gate": g1[q]}} for q, a in t1_out["answers"].items()}

    # 窗口级：任一题 escalate → 整窗升 Tier 2（论文 "escalates whole"）
    t2_out = None
    g2 = None
    if gating.needs_tier2(g1):
        route["path"].append("tier2_kev")
        t2_out = kev.decide(state)
        lat["tier2_ms"] = t2_out["latency_ms"]
        g2 = gating.gate_all(t2_out["answers"])
        for q, a in t2_out["answers"].items():
            route["questions"][q]["tier2"] = {"pred": a["pred"], "conf": round(a["conf"], 4),
                                              "gate": g2[q]}

    # ---- 逐题终局路由 ----
    t0 = time.time()
    confirm_qs, human_qs = [], []
    for q in t1_out["answers"]:
        if t2_out is not None:
            src, a, g = "tier2", t2_out["answers"][q], g2[q]
        else:
            src, a, g = "tier1", t1_out["answers"][q], g1[q]
        route["final"][q] = {"pred": a["pred"], "conf": round(a["conf"], 4), "gate": g, "source": src}
        if g == "confirm":
            confirm_qs.append(q)
        elif g == "escalate":
            human_qs.append(q)  # Tier 2 后仍 <τ_h → 人工队列（不自动）
    lat["gate_ms"] += (time.time() - t0) * 1000

    # ---- Tier 3 人工（confirm 题 + 仍 escalate 题）----
    if confirm_qs or human_qs:
        route["path"].append("tier3_human")
        t0 = time.time()
        evidence = gating.narrate(window, {"tier1": t1_out, "tier2": t2_out}, None)
        suggestion = route["final"].get("action", {}).get("pred")
        approved = gating.human_confirm(evidence, suggestion, non_interactive=non_interactive)
        lat["human_ms"] = (time.time() - t0) * 1000
        route["human"] = {"approved": approved, "confirm_questions": confirm_qs,
                          "escalated_questions": human_qs}
        if approved:
            for q in confirm_qs:
                route["final"][q]["executed"] = "human_approved"
        else:
            for q in confirm_qs:
                route["final"][q]["executed"] = "human_rejected"
        for q in human_qs:
            route["final"][q]["executed"] = "human_decision"
    else:
        # 全 auto：白名单动作模拟执行（dry-run 记账）
        act = route["final"].get("action") or {"pred": None}
        act["executed"] = "auto" if act["pred"] in gating.AUTO_ACTIONS else "blocked_not_whitelisted"

    audit.append(window_id=wid, event="window_done", route=route,
                 latency_ms={k: (round(v, 3) if v is not None else None) for k, v in lat.items()},
                 labels=window.get("labels"),
                 tier1_dists={q: {k: round(v, 4) for k, v in a["probabilities"].items()}
                              for q, a in t1_out["answers"].items()},
                 tier2_dists=({q: {k: round(v, 4) for k, v in a["probabilities"].items()}
                               for q, a in t2_out["answers"].items()} if t2_out else None),
                 total_ms=(time.time() - t_start) * 1000)
    return {"window_id": wid, "latency": lat, "route": route,
            "tier1": t1_out, "tier2": t2_out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", type=int, default=20)
    ap.add_argument("--non-interactive", default="y", help="y/n/ask（ask=真 CLI 交互）")
    ap.add_argument("--audit", default=f"{HERE}/logs/audit.jsonl")
    ap.add_argument("--windows-json", default=f"{HERE}/logs/windows.json")
    ap.add_argument("--kev-url", default="http://127.0.0.1:8021")
    ap.add_argument("--skip-kev-serve-check", action="store_true")
    args = ap.parse_args()

    # 1. 选窗（分层：规则/高/中/低）
    wins, sel_meta, pool_sizes = select_windows(k=args.windows)
    os.makedirs(os.path.dirname(args.windows_json), exist_ok=True)
    json.dump({"pool_sizes": pool_sizes, "selected": sel_meta, "windows": wins},
              open(args.windows_json, "w"), ensure_ascii=False, indent=1)
    print(f"[select] pools={pool_sizes} → {len(wins)} windows")

    # 2. kev serve 健康检查（Tier 2 前置）
    from tier2_kev import KevTier
    kev = KevTier(base_url=args.kev_url)
    if not kev.healthy():
        print(f"[abort] kev serve 未就绪: {args.kev_url}/v1/models（先起 serve，见 serve_kev.sh）")
        sys.exit(2)

    # 3. laya 加载（CPU）
    from tier1_laya import LayaTier
    t0 = time.time()
    laya = LayaTier(device="cpu")
    print(f"[laya] loaded in {time.time()-t0:.1f}s (CPU)")

    audit = gating.AuditLog(args.audit)
    results = []
    for i, w in enumerate(wins):
        rec = process_window(w, laya, kev, audit, non_interactive=args.non_interactive)
        results.append(rec)
        r = rec["route"]
        print(f"[{i+1}/{len(wins)}] {r['window_id']} path={'→'.join(r['path'])} "
              f"human={'Y' if r.get('human') else '-'} rule={r.get('rule_hit') or '-'}")

    # 4. 汇总
    summarize(results, sel_meta, pool_sizes, args)
    return results


def summarize(results, sel_meta, pool_sizes, args):
    paths = {}
    lat_lists = {"state_ms": [], "tier0_ms": [], "tier1_ms": [], "tier2_ms": [], "gate_ms": []}
    q_route = {}
    human_n = 0
    for rec in results:
        p = "→".join(rec["route"]["path"])
        paths[p] = paths.get(p, 0) + 1
        if rec["route"].get("human"):
            human_n += 1
        for k, lst in lat_lists.items():
            v = rec["latency"].get(k)
            if v is not None:
                lst.append(v)
        for q, f in rec["route"]["final"].items():
            if "gate" not in f:  # tier0 规则窗无门控字段
                key = (f.get("source", "rule"), "rule_adjudicated")
            else:
                key = (f["source"], f["gate"])
            q_route[key] = q_route.get(key, 0) + 1
    lat_stats = {k: {"n": len(v), "mean_ms": round(statistics.mean(v), 1),
                     "p50_ms": round(statistics.median(v), 1),
                     "max_ms": round(max(v), 1)} for k, v in lat_lists.items() if v}
    n = len(results)
    summary = {
        "n_windows": n,
        "path_distribution": paths,
        "windows_with_tier2": sum(1 for r in results if "tier2_kev" in r["route"]["path"]),
        "windows_with_human": human_n,
        "windows_rule_hit": sum(1 for r in results if "tier0_rule" in r["route"]["path"]),
        "question_route_counts": {f"{s}/{g}": c for (s, g), c in sorted(q_route.items())},
        "latency_breakdown_ms": lat_stats,
        "thresholds": {"tau": gating.TAU, "tau_h": gating.TAU_H},
        "pool_sizes": pool_sizes,
        "selection": sel_meta,
        "config": {"kev_url": args.kev_url, "non_interactive": args.non_interactive},
    }
    out = f"{HERE}/logs/routing_summary.json"
    json.dump(summary, open(out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: summary[k] for k in ("n_windows", "path_distribution",
                                              "windows_with_tier2", "windows_with_human",
                                              "windows_rule_hit", "question_route_counts")},
                     ensure_ascii=False, indent=1))
    print(f"[summary] → {out}")


if __name__ == "__main__":
    main()
