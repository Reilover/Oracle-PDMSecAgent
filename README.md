# ORACLE

Code and data for the paper *"ORACLE: Offense detection with Reasoned Alert triage and Calibrated local Engines"*.

- **What**: A fully local two-tier PDM (parallel decision model) pipeline for SOC alert triage and response recommendation. No data egress, no cloud APIs.
- **Status**: Artifact release in preparation. This repository currently holds the license and landing page; code, frozen data suites, and evaluation harness will be pushed in step with the preprint posting.
- **License**: Apache-2.0 (code); suite labels CC BY-SA 4.0. See [LICENSE](LICENSE).

## Post-trained checkpoints (ModelScope)

| Model | Test tactic / exact | Link |
|---|---|---|
| ORACLE kev-4B (pointer CE) | 0.850 / 0.629 | [Reilover/oracle-kev4b](https://www.modelscope.cn/models/Reilover/oracle-kev4b) |
| ORACLE kev-0.8B (pointer CE) | 0.763 / 0.595 | [Reilover/oracle-kev08](https://www.modelscope.cn/models/Reilover/oracle-kev08) |
| ORACLE laya-421M (RLCD) | 0.724 / 0.522 (same-split) | [Reilover/oracle-laya-421m](https://www.modelscope.cn/models/Reilover/oracle-laya-421m) |
| ORACLE NanoJev-0.6B (SFT) | 0.670 / 0.567 | [Reilover/oracle-nanojev-0.6b](https://www.modelscope.cn/models/Reilover/oracle-nanojev-0.6b) |

Each checkpoint ships with a bilingual model card (base-model provenance with pinned revisions, training recipe, fitted-temperature usage, evaluation numbers with per-split provenance) and SHA256 manifests. Base weights are not redistributed; fetch them per the card.

## Source corpora

The four third-party training corpora (security-gym-v4, AIT-LDS, linux-apt-2024, soc-alert-attack) are public datasets; links and per-corpus notes are maintained here rather than redistributing them.

## Citation (forthcoming)

The preprint will be announced here once posted.
