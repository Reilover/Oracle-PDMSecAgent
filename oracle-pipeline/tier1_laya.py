#!/usr/bin/env python3
"""Tier 1 — 轻层 PDM laya-421M v3（本地权重，CPU 单次前向，四题 typed 分布）

协议与训练侧一致（code/eval/eval_laya_ft_v3.py 同口径：pack_suite 问题模板）。
温度：ckpt 内嵌逐题类温度（choice 4.84 / score 9.04 / noul 9.22，已在 Agent 内
clamp 到 [0.5,5] 并默认应用于返回概率）；本层同时保留原始 logits 供门控做二次缩放。

依赖 venv: /home/xxl/spark2_5（torch 2.13 + transformers 5.16）
"""
import os
import sys
import time

SECAGENT = "/home/xxl/MySecAgent"
sys.path.insert(0, f"{SECAGENT}/lab/experiments/oracle/code/suite")
sys.path.insert(0, "/home/xxl/laya")

CKPT = f"{SECAGENT}/lab/experiments/oracle/T4-LAYA/laya-oracle-v3"

from pack_suite import (  # noqa: E402
    TACTIC_CRITERIA, TACTIC_INSTR, URGENT_INSTR, SEV_INSTR, SEV_CRIT,
    ACTION_CRITERIA, ACTION_INSTR,
)

SEV_LEVELS = ["low", "medium", "high", "critical"]


def build_questions():
    return {
        "tactic": {"type": "choice", "instructions": TACTIC_INSTR, "criteria": dict(TACTIC_CRITERIA)},
        "urgent": {"type": "noul", "instructions": URGENT_INSTR["question"]},
        "severity": {"type": "choice", "instructions": SEV_INSTR["question"],
                     "criteria": {s: d for s, d in zip(SEV_LEVELS, SEV_CRIT)}},
        "action": {"type": "choice", "instructions": ACTION_INSTR, "criteria": dict(ACTION_CRITERIA)},
    }


class LayaTier:
    def __init__(self, device="cpu"):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from laya.agent import Agent
        self.agent = Agent(CKPT, device=device)
        self.device = device

    def decide(self, state_text):
        qs = build_questions()
        t0 = time.time()
        resp = self.agent.predict(state_text, qs)
        lat_ms = (time.time() - t0) * 1000
        answers = resp.get("answers", resp)
        out = {"latency_ms": lat_ms, "answers": {}}
        for qid, q in qs.items():
            a = answers.get(qid, {}) or {}
            if q["type"] == "noul":
                # laya noul 协议: {"noul": P(true), "confidence": max(p,1-p)}（无 probabilities）
                pt = float(a.get("noul", 0.5) or 0.0)
                out["answers"][qid] = {
                    "pred": pt >= 0.5,
                    "probabilities": {"true": pt, "false": 1.0 - pt},
                    "conf": float(a.get("confidence", max(pt, 1.0 - pt))),
                }
                continue
            pr = a.get("probabilities") or {}
            top = max(pr, key=pr.get) if pr else None
            out["answers"][qid] = {
                "pred": top,
                "probabilities": {k: float(v) for k, v in pr.items()},
                "conf": float(max(pr.values())) if pr else 0.0,  # 已是内嵌温度校准后概率
            }
        return out
