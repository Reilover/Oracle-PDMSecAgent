"""B3 种子方差分析: seed1/seed2 raw logits → 方法A温度拟合(calib) → test 加温复算 → 四任务指标 → 三点方差
协议与 methodA_test_formal.py / evaluate.py 完全同款。纯 CPU。
"""
import json
from pathlib import Path

import torch

from kev.metrics import TEMPERATURE_FIT, fit_temperature, metrics, raw_row, scored_rows, tempered_row
from kev.suite import read_json, write_json

BASE = Path("/home/xxl/MySecAgent/lab/experiments/oracle")
EVAL = BASE / "EVAL/BATCH2-TRAIN"
SUITE_MAIN = BASE / "T1-KEV4B/round3-v3"

out = {}
for seed in (1, 2):
    d = EVAL / f"seed{seed}-test"
    calib = scored_rows(read_json(d / "bench-calib/rows.json"))
    raw_calib = [raw_row(r) for r in calib]
    T_A = fit_temperature(raw_calib, **TEMPERATURE_FIT)

    test = read_json(d / "bench-test/rows.json")
    served = scored_rows(test)
    raw_test = [raw_row(r) for r in served]
    tempered = [tempered_row(r, T_A) for r in raw_test]

    m_raw = metrics(raw_test)
    m_cal = metrics(tempered)
    keys = ("n", "acc", "ece", "brier", "nll", "mean_conf", "confident_error_rate",
            "coverage_at_5pct_error", "aurc")
    out[f"seed{seed}"] = {
        "calib_refit_temperature": T_A,
        "test_n_rows": len(test),
        "arms": {"raw_T1": {k: m_raw[k] for k in keys},
                 "methodA_calibrated": {k: m_cal[k] for k in keys}},
    }
    write_json(d / "rows-TmethodA.json", tempered)
    print(f"seed{seed}: T={T_A:.4f}")
    print(f"  test raw : acc={m_raw['acc']:.4f} ece={m_raw['ece']:.4f} nll={m_raw['nll']:.4f}")
    print(f"  test +T  : acc={m_cal['acc']:.4f} ece={m_cal['ece']:.4f} nll={m_cal['nll']:.4f}")

write_json(EVAL / "seed_variance_kev_metrics.json", out)
print("DONE")
