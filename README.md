# ORACLE

Code and data for the paper *"ORACLE: Offense detection with Reasoned Alert triage and Calibrated local Engines"*.

- **What**: A fully local two-tier PDM (parallel decision model) pipeline for SOC alert triage and response recommendation. No data egress, no cloud APIs.
- **Status**: Code and data artifacts released with the preprint.

## Repository layout

- `oracle-pipeline/` — reference implementation of the full inference pipeline: state construction (Drain3 templating, key-line extraction), Tier-0 rules, light/heavy PDM tiers, per-question confidence gating, append-only audit log, and the Tier-3 browser console (bilingual). See `oracle-pipeline/README-完整使用说明.md` for the full environment guide and current limitations.
- `suites/` — frozen oracle suite manifest (SHA-256 pinned partitions and provenance).
- `evaluation/` — evaluation and calibration harness: the unified baseline runner, the four-task evaluator, suite packing (typed-question conversion), and the fitted-temperature (Method A) calibration script.
- **License**: Apache-2.0 (code); suite labels CC BY-SA 4.0. See [LICENSE](LICENSE).

## Post-trained checkpoints (ModelScope)

| Model | Test tactic / exact | Link |
|---|---|---|
| ORACLE kev-4B (pointer CE) | 0.850 / 0.629 | [Reilover/oracle-kev4b](https://www.modelscope.cn/models/Reilover/oracle-kev4b) |
| ORACLE kev-0.8B (pointer CE) | 0.763 / 0.595 | [Reilover/oracle-kev08](https://www.modelscope.cn/models/Reilover/oracle-kev08) |
| ORACLE laya-421M (RLCD) | 0.724 / 0.522 (same-split) | [Reilover/oracle-laya-421m](https://www.modelscope.cn/models/Reilover/oracle-laya-421m) |
| ORACLE NanoJev-0.6B (SFT) | 0.670 / 0.567 | [Reilover/oracle-nanojev-0.6b](https://www.modelscope.cn/models/Reilover/oracle-nanojev-0.6b) |

Each checkpoint ships with a bilingual model card (base-model provenance with pinned revisions, training recipe, fitted-temperature usage, evaluation numbers with per-split provenance) and SHA256 manifests. Base weights are not redistributed; fetch them per the card.

## Supplementary evaluation: cloud Jev 1.13 (same-convention re-run)

`evaluation/cloud-jev-439/` — the commercial cloud PDM (Jev 1.13) evaluated on the frozen
oracle-v3 test split (439 windows / 1,756 questions) and development split (55 windows)
under the identical eleven-option convention: tactic 0.636 / exact 0.148 on test, with
per-window raw predictions (`predictions*.jsonl`), per-task analyses, and the runner.

## Source corpora

The four third-party training corpora (security-gym-v4, AIT-LDS, linux-apt-2024, soc-alert-attack) are public datasets; links and per-corpus notes are maintained here rather than redistributing them.

## Citation (forthcoming)

## Citation

X. Xiong, J. Huang, Z. Wei, Y. Wang, and L. Niu, "ORACLE: Calibrated Parallel Decision Models for Local Alert Triage and Response Action Recommendation," 2026. doi: 10.5281/zenodo.23092472.

Preprint: https://zenodo.org/record/23092472 (CC BY-SA 4.0).

## Supplementary evaluation: baseline dev re-run (unified convention)

`evaluation/baseline-unify-dev/` — the eight baseline systems of the main
comparison re-evaluated on the 55-window development split under the same
11-option convention and runner as the test split (the paper's original dev
columns for these rows came from an earlier 4-option convention). Includes
per-model predictions, analyses, and an old-vs-new REPORT.

## Supplementary evaluation: GPU latency, CPU degradation, and cold start

`evaluation/gpu-latency/` — every local system re-measured on an idle GPU
(439-window test split, per-window medians): replaces the earlier CPU-based
latency column, verifies prediction consistency (HF-precision rows identical;
llama.cpp/vLLM rows differ only by sampling nondeterminism), and adds measured
CPU-degradation ratios and cold-start/first-window times.

## Paper-results bundle

`evaluation/paper-results/` — the per-experiment artifacts backing every number
in the paper's tables and figures: baseline test/dev re-runs
(BASELINE-UNIFY, V3-TEST-BASELINE), the four ORACLE training-line reports and
bench rows (T2/T3/T4), calibration and ModernBERT control (BERT-CALIB),
cross-domain transfer (CAM-LDS), the laya same-convention re-evaluation
(LAYA-FAMILY), the local-label gain curve (E3P-TEST-CONFIRM), end-to-end
cascade simulation (D1-E2E), the adversarial robustness probe
(ADVERSARIAL-PROBE), and the headline bootstrap intervals (CI-HEADLINE.json).
