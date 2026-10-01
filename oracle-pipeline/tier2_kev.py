#!/usr/bin/env python3
"""Tier 2 — 重层 PDM Kev-0.8B v3（LoRA + pointer head，kev-repo serve /v1/systemone）

同 state 同协议重打分（range_eval_kev.py 口径）。温度：head.pt 内嵌全局拟合温度
T=1.9097（min-NLL on calibration split），kev.serve 加载时默认应用于返回概率；
KEV_TEMPERATURE=1.0 可还原 raw。显存 <10GB（实测 serve 约 3-4GB）。
"""
import json
import time
import urllib.request

SEV_LEVELS = ["low", "medium", "high", "critical"]
# 与 pack_suite 模板一致（tier1 同款，避免跨模块依赖顺序问题时直接内联）
import sys
sys.path.insert(0, "/home/xxl/MySecAgent/lab/experiments/oracle/code/suite")
from pack_suite import (  # noqa: E402
    TACTIC_CRITERIA, TACTIC_INSTR, URGENT_INSTR, SEV_INSTR, SEV_CRIT,
    ACTION_CRITERIA, ACTION_INSTR,
)


def build_questions():
    return {
        "tactic": {"type": "choice", "instructions": TACTIC_INSTR, "criteria": dict(TACTIC_CRITERIA)},
        "urgent": {"type": "noul", "instructions": URGENT_INSTR["question"]},
        "severity": {"type": "score", "instructions": SEV_INSTR["question"], "criteria": list(SEV_CRIT)},
        "action": {"type": "choice", "instructions": ACTION_INSTR, "criteria": dict(ACTION_CRITERIA)},
    }


class KevTier:
    def __init__(self, base_url="http://127.0.0.1:8021", timeout=120):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def healthy(self):
        try:
            with urllib.request.urlopen(f"{self.base}/v1/models", timeout=5) as r:
                return json.loads(r.read()) is not None
        except Exception:
            return False

    def decide(self, state_text):
        qs = build_questions()
        body = json.dumps({"state": state_text, "model": "kev-latest", "questions": qs}).encode()
        req = urllib.request.Request(f"{self.base}/v1/systemone", body,
                                     {"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            d = json.loads(r.read())
        lat_ms = d.get("latency_ms", (time.time() - t0) * 1000)
        answers = d["answers"]
        out = {"latency_ms": float(lat_ms), "answers": {}}
        for qid, q in qs.items():
            a = answers.get(qid, {}) or {}
            if q["type"] == "choice":
                pr = {k: float(v) for k, v in (a.get("probabilities") or {}).items()}
                top = max(pr, key=pr.get) if pr else None
                out["answers"][qid] = {"pred": top, "probabilities": pr,
                                       "conf": float(max(pr.values())) if pr else 0.0}
            elif q["type"] == "score":
                pr = {SEV_LEVELS[int(k)]: float(v) for k, v in (a.get("probabilities") or {}).items()}
                top = max(pr, key=pr.get) if pr else None
                out["answers"][qid] = {"pred": top, "probabilities": pr,
                                       "conf": float(max(pr.values())) if pr else 0.0}
            else:  # noul: P(true)
                pt = float(a.get("noul", 0.0) or 0.0)
                out["answers"][qid] = {"pred": pt >= 0.5,
                                       "probabilities": {"true": pt, "false": 1.0 - pt},
                                       "conf": max(pt, 1.0 - pt)}
        return out
