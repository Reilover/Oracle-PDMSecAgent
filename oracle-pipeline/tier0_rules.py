#!/usr/bin/env python3
"""Tier 0 — 规则前置（复用 judge/rules.py，勿改源）
输入 window 记录（raw_lines + window_stats），命中返回 {verdict, rule_id}，否则 pass-through。
"""
import sys

sys.path.insert(0, "/home/xxl/MySecAgent/judge")
from rules import judge_rule  # noqa: E402


def tier0(window):
    ev = {"raw_lines": window["raw_lines"], "window_stats": window["window_stats"]}
    hit = judge_rule(ev)
    if not hit:
        return None
    return {
        "verdict": {
            "tactic": hit["tactic"],
            "severity": hit["severity"],
            "urgent": hit["urgent"],
            "action": hit["action"],
        },
        "rule_id": hit["rule_hit"],
    }
