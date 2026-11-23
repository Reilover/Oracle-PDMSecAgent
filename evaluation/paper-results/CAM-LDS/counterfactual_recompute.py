#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cam-lds 反事实精确重算（kev-4B，551 可评窗）
=================================================

背景
----
论文 §6.3 / 表 tab:camlds 原文写道："lifting the three below-strong tiers
(348 weak/sparse/zero windows) to the strong-tier conditional (0.611) would
raise overall accuracy from 0.240 to ~0.382, and to the recon+execution
mean (0.703) to ~0.406"。第二轮审稿 R3' W6 指出 0.436 不可复现，修正稿给出
0.382/0.406，但未写明口径。本脚本从原始 results_kev4b-v3.jsonl 逐窗重算，
穷举三种口径（A/B/C）并输出 counterfactual.json，供论文定稿采用。

输入
----
- results_kev4b-v3.jsonl   （主数据，551 行，每行含 label.tactic / pred.tactic）
- 其余 results_*.jsonl 仅作旁证（各线 overall），不参与反事实。

训练支持分档（v3 训练语料，来源：论文 Table tab:camlds 表注 + REPORT-FOURLINE.md）
--------------------------------------------------------------------------------
  strong  >=500  : credential_access 2887, execution 1354, reconnaissance 1024
  weak    100-499: exfiltration 444, initial_access 317, command_and_control 299, discovery 181
  sparse  1-99   : privilege_escalation 91
  zero    0      : persistence, defense_evasion

注意：更早的 v3 支持口径（REPORT-FOURLINE §2，execution 877 / credential 2294
 ait 单源）把 exfiltration / C2 也算零支持，由此产生"142 窗零支持组"
（defense_evasion 65 + C2 37 + persistence 33 + exfiltration 7 = 142）。
0.382/0.406 的来源与该旧分组直接相关，见口径 C2。

口径定义（全部基于逐窗真实数据，可复算）
----------------------------------------
A  三档全抬：348 个 below-strong 窗全部抬到目标条件召回 c，strong 档保持实际。
B  仅抬 weak 档：198 个 weak 窗抬到 c，其余保持实际。
C1 仅抬 142 零支持类窗（旧口径四类），其余全部保持实际逐窗结果。
C2 142 零支持类窗抬到 c，strong 档保持实际 124 对，其余 206 窗（discovery/
   priv_esc/initial_access）隐式按 0 计 —— 审稿人 R3' W6 的算术。
C3 加权部分抬升：348 窗按 (support/500) 截断线性加权抬到 c（覆盖剂量的连续化）。

目标条件召回 c 的两个取值：
  c_strong = strong 档实际条件召回（=124/203）
  c_reexec = recon+execution 实际均值（=121/172，credential_access 不计入）

用法：python3 counterfactual_recompute.py   （CPU 秒级，无依赖）
输出：stdout 摘要 + 同目录 counterfactual.json
"""

import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results_kev4b-v3.jsonl")
OUT = os.path.join(HERE, "counterfactual.json")

# ---- 训练支持分档（论文 Table tab:camlds 表注口径） ------------------------
TIER = {
    "reconnaissance":       ("strong", 1024),
    "execution":            ("strong", 1354),
    "credential_access":    ("strong", 2887),
    "exfiltration":         ("weak",   444),
    "initial_access":       ("weak",   317),
    "command_and_control":  ("weak",   299),
    "discovery":            ("weak",   181),
    "privilege_escalation": ("sparse",  91),
    "persistence":          ("zero",     0),
    "defense_evasion":      ("zero",     0),
}
# 旧 v3 支持口径下的"严格零支持"四类（REPORT-FOURLINE §2b 合计 142 窗）
ZERO142 = {"defense_evasion", "command_and_control", "persistence", "exfiltration"}


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("pred") and r["pred"].get("tactic") is not None:
                rows.append(r)
    return rows


def main():
    rows = load(RESULTS)
    n = len(rows)
    correct = lambda r: 1 if r["pred"]["tactic"] == r["label"]["tactic"] else 0

    # ---- 逐类 / 逐档统计 ---------------------------------------------------
    per_class = defaultdict(lambda: {"n": 0, "correct": 0})
    for r in rows:
        c = per_class[r["label"]["tactic"]]
        c["n"] += 1
        c["correct"] += correct(r)

    tier_stat = defaultdict(lambda: {"n": 0, "correct": 0})
    for t, (tier, _) in TIER.items():
        tier_stat[tier]["n"] += per_class[t]["n"]
        tier_stat[tier]["correct"] += per_class[t]["correct"]

    overall_correct = sum(v["correct"] for v in per_class.values())
    overall = overall_correct / n

    strong = tier_stat["strong"]
    c_strong = strong["correct"] / strong["n"]                       # 0.611
    re_ex_n = per_class["reconnaissance"]["n"] + per_class["execution"]["n"]
    re_ex_c = per_class["reconnaissance"]["correct"] + per_class["execution"]["correct"]
    c_reexec = re_ex_c / re_ex_n                                     # 0.703

    below = tier_stat["weak"]["n"] + tier_stat["sparse"]["n"] + tier_stat["zero"]["n"]
    weak = tier_stat["weak"]
    n142 = sum(per_class[t]["n"] for t in ZERO142)
    weak_nonzero_classes_n = below - n142                            # discovery+priv+initial = 206
    weak_nonzero_classes_correct = (
        per_class["discovery"]["correct"]
        + per_class["privilege_escalation"]["correct"]
        + per_class["initial_access"]["correct"]
    )

    # ---- 口径 A：三档 348 窗全抬到 c，strong 保持实际 ----------------------
    def caliber_A(c):
        return (strong["correct"] + below * c) / n

    # ---- 口径 B：仅抬 weak 档 198 窗，其余保持实际 --------------------------
    def caliber_B(c):
        return (overall_correct - weak["correct"] + weak["n"] * c) / n

    # ---- 口径 C1：仅抬 142 零支持类窗，其余保持实际逐窗 --------------------
    def caliber_C1(c):
        return (overall_correct + n142 * c) / n   # 142 类实际 0 对，直接加期望

    # ---- 口径 C2：142 窗抬到 c；strong 保持实际 124；其余 206 窗按 0 计 -----
    #      （审稿人 R3' W6 的算术：未声明地丢弃 discovery/priv_esc/initial 的 8 个真对）
    def caliber_C2(c):
        return (strong["correct"] + n142 * c) / n

    # ---- 口径 C3：348 窗按 min(support/500,1) 加权抬到 c -------------------
    def caliber_C3(c):
        lifted = 0.0
        for t, (tier, sup) in TIER.items():
            if tier == "strong":
                continue
            w = min(sup / 500.0, 1.0)
            lifted += per_class[t]["n"] * w * (c - per_class[t]["correct"] / per_class[t]["n"])
        return (overall_correct + lifted) / n

    targets = {"strong_conditional_0.611": c_strong, "recon_exec_mean_0.703": c_reexec}
    calibers = {
        "A_lift_all_348_below_strong": caliber_A,
        "B_lift_weak_198_only": caliber_B,
        "C1_lift_zero142_keep_actual_rest": caliber_C1,
        "C2_lift_zero142_zero_the_206": caliber_C2,
        "C3_support_weighted_partial_lift": caliber_C3,
    }

    result = {
        "source": "results_kev4b-v3.jsonl",
        "model": "kev-4B v3",
        "n_windows_scored": n,
        "n_windows_total": 562,
        "baseline": {
            "overall_correct": overall_correct,
            "overall_recall": round(overall, 4),
        },
        "tiers": {
            t: {"n": s["n"], "correct": s["correct"],
                "conditional": round(s["correct"] / s["n"], 4)}
            for t, s in tier_stat.items()
        },
        "per_class_recall": {
            t: {"n": v["n"], "correct": v["correct"],
                "recall": round(v["correct"] / v["n"], 4)}
            for t, v in sorted(per_class.items())
        },
        "target_conditionals": {
            "c_strong": {"value": round(c_strong, 4),
                         "derivation": f"{strong['correct']}/{strong['n']} (strong tier actual)"},
            "c_reexec": {"value": round(c_reexec, 4),
                         "derivation": f"{re_ex_c}/{re_ex_n} (reconnaissance+execution actual, credential_access excluded)"},
        },
        "groups": {
            "below_strong_348": below,
            "weak_198": weak["n"],
            "zero142_old_definition": n142,
            "weak_nonzero_206_actual_correct": weak_nonzero_classes_correct,
        },
        "counterfactuals": {
            cname: {tname: round(fn(c), 4) for tname, c in targets.items()}
            for cname, fn in calibers.items()
        },
        "published_numbers": {"v1_claimed": 0.436, "v2_corrected": [0.382, 0.406]},
        "match_analysis": {},
    }

    # ---- 匹配判定：0.382 / 0.406 -------------------------------------------
    matches = defaultdict(list)
    for cname, vals in result["counterfactuals"].items():
        for tname, v in vals.items():
            for pub in (0.382, 0.406):
                if abs(v - pub) < 0.0015:  # 三位小数舍入容差
                    matches[pub].append((cname, tname, v))
    result["match_analysis"] = {str(k): v for k, v in matches.items()}

    # ---- 输出 ---------------------------------------------------------------
    with open(OUT, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"baseline overall = {overall_correct}/{n} = {overall:.4f}")
    print(f"c_strong = {strong['correct']}/{strong['n']} = {c_strong:.4f}")
    print(f"c_reexec = {re_ex_c}/{re_ex_n} = {c_reexec:.4f}")
    print(f"zero142 group n = {n142}; weak-nonzero 206 windows hold "
          f"{weak_nonzero_classes_correct} actual corrects")
    print()
    for cname, vals in result["counterfactuals"].items():
        for tname, v in vals.items():
            star = "  <== matches published" if any(
                abs(v - p) < 0.0015 for p in (0.382, 0.406)) else ""
            print(f"{cname:38s} c={tname:26s} -> {v:.4f}{star}")
    print()
    print(f"wrote {OUT}")
    return result


if __name__ == "__main__":
    main()
