# ORACLE: Offense detection with Reasoned Alert triage and Calibrated local Engines

**A fully local, calibrated, two-tier PDM (parallel decision model) pipeline for SOC alert triage and response recommendation — no data egress, no cloud APIs.**

> Code and data release accompanying the paper *"ORACLE: ..."* (preprint forthcoming on arXiv). This repository currently holds the license and landing page; the full artifact set is pushed in step with the preprint posting.

## What ORACLE is

Modern SOCs face an automation dilemma: fully automated response requires decisions that are both *accurate* and *certified* (confidence-honest), and no single decision maker provides both across the whole alert stream. ORACLE resolves it with a confidence-escalation pipeline:

- **Tier 0 — deterministic rules**: known patterns adjudicated in ~0 ms
- **Tier 1 — light PDM** (laya-421M, encoder/RLCD): adjudicates volume; per-question-type temperature calibration keeps confidences honest; any window below the automation threshold τ travels whole to the next tier
- **Tier 2 — heavy PDM** (Kev-0.8B/4B, decoder + trainable pointer head): re-adjudicates the hard band for accuracy
- **Tier 3 — human analysts**: own the tail below τ_h with a browser console (evidence narration, per-question approve/veto/relabel, threshold setting); labelled replays retrain both PDM layers, shrinking the tail over time

All tiers log to an append-only audit trail; every routing decision is replayable.

## Key results (range test split, 439 windows / 1,756 typed questions)

| | tactic acc | exact match | ECE | P50 latency |
|---|---|---|---|---|
| Kev-4B zero-shot | 0.761 | 0.237 | 0.237 | 342 ms |
| **ORACLE Kev-4B** | **0.850** | **0.629** | 0.140 | 2.3 s* |
| **ORACLE laya 421M** | 0.657 | 0.472 | **0.123** | **72 ms** |
| ORACLE NanoJev 0.6B | 0.670 | 0.567 | — | 154 ms |

*GPU-shared steady state. Post-training lifts the 0.8B line from 0.282 → 0.763 tactic (+0.481); all three official laya checkpoints score 0.025–0.116 zero-shot (chance) — domain post-training is the missing ingredient, not model scale.

## Repository layout (on preprint posting)

```
oracle-pipeline/     # reference implementation: state builder, tiers, gating, audit, UI
suites/              # oracle suite manifests (SHA-256 frozen)
calibration/         # fitted-temperature methodology (Method A/B, OOF protocol)
evaluation/          # benchmark harness incl. bootstrap-CI computation
```

## Substrates

- [Kev](https://github.com/jaredpalmer/kev) (Apache-2.0) — decoder PDM, LoRA + pointer head
- [laya](https://huggingface.co/convaiinnovations/laya) (Apache-2.0) — ModernBERT encoder, RLCD with strictly proper scoring
- [NanoJev](https://github.com/TianyuCodings/NanoJev) (MIT) — set-attention scorer

## License

Apache-2.0 (code); suite labels CC BY-SA 4.0. See [LICENSE](LICENSE).

## Contact

Xinli Xiong (corresponding author) — xiongxinli_@nudt.edu.cn
