# D9 — ModernBERT 温度阶段 bf16 复测（test 439 窗）REPORT

任务：消除表 2 MB 行的 bf16/fp32 混精度口径——用与 fp32 存档（`../bert_calib_result.json`）完全同协议的 bf16 GPU 推理，在 oracle-v3 test 439 窗复测温度阶段结果，并逐项对照。

日期：2026-11-25 · 脚本：`bert_bf16_test.py` · 产物：`bert_bf16_test_result.json`、`results_bf16_test.jsonl`（439 行）、`logits_test_bf16.json`、`gate.json`

## 协议

- checkpoint：`EVAL/BATCH2-TRAIN/bert-baseline/bert_baseline.pt`（四头，fp32 权重加载后 `model.eval()`、转 `cuda + bfloat16`，dropout 关闭；输出 logits 立即转 fp32 落盘）。
- 数据与 tokenize 与 fp32 完全一致：`suites/oracle-v3/test.jsonl`（439 窗），`max_length=1024, padding=max_length`，batch 16，顺序推理。
- **温度直接采用 fp32 已拟合值（不重拟合）**：tactic T=1.8661、urgent T=2.0000、severity T=2.1435、action T=1.6625。
- 指标口径：ECE = 15 equal-frequency bins（`train_bert_baseline.py` 同款）；argmax/exact 温度不变；NLL 逐头 + 四头 micro 平均（各头 n 相等，算术平均 = micro）。
- GPU：GPU0（空闲 17 MiB），CUDA_VISIBLE_DEVICES=0，MPS 隔离；439 窗 bf16 推理耗时 2.6 s。

## 结果：bf16 raw (T=1) vs bf16 tempered（逐头 T），并与 fp32 存档逐项对照

| 头 | bf16 raw acc/ECE15/NLL/mean_conf | bf16 tempered acc/ECE15/NLL/mean_conf | fp32 tempered ECE15/NLL（Δ: bf16−fp32） |
|---|---|---|---|
| tactic | .6811 / .2629 / 1.9695 / .9349 | .6811 / .2759 / 1.3598 / .7194 | .2765 / 1.3621（Δ −0.0006 / −0.0023） |
| urgent | .7813 / .1722 / .8868 / .9448 | .7813 / .1966 / .6087 / .8262 | .1974 / .6084（Δ −0.0008 / +0.0003） |
| severity | .6902 / .2825 / 1.7337 / .9655 | .6902 / .2847 / 1.0491 / .7762 | .2752 / 1.0492（Δ +0.0095 / −0.0001） |
| action | .6879 / .2487 / 1.2743 / .9026 | .6879 / .2273 / .9982 / .7475 | .2322 / .9994（Δ −0.0049 / −0.0012） |
| exact | .6811 | .6811 | .6811（温度不变，逐位一致） |
| micro NLL | 1.4661 | **1.0040** | 1.0048（Δ −0.0008） |
| micro ECE15 | 0.2416 | 0.2461 | 0.2453（Δ +0.0008） |

## 一致性与 gate

- **439/439 窗全量完成**；逐窗 argmax 与 fp32 存档 logits（`../logits_test.json`）四头全部 1.000 一致（tactic/urgent/severity/action 均 439/439）。
- Gate（|bf16−fp32| ≤ 0.02）：tempered tactic ECE Δ = **0.0006**（0.2759 vs 0.2765）；tempered micro ECE Δ = **0.0008**（0.2461 vs 0.2453）→ **PASS**，可回填。
- raw micro NLL：fp32 1.467 → bf16 1.466；tempered micro NLL：fp32 1.005 → bf16 1.004。数值在第三位小数内一致，bf16 推理对校准结论无实质影响。

## 论文可写实数（bf16 同口径）

- 温度阶段后 tactic ECE15 = **0.276**（bf16 实测 0.2759，fp32 0.2765；原正文 "~0.28" 可写实数）。
- 温度阶段后四头 micro NLL = **1.004**（raw 1.466；即 1.47→1.00 的口径在 bf16 下复现）。
- 其余逐头数值见上表；混精度口径差异（bf16 vs fp32）≤ 0.01（最大为 severity ECE +0.0095）。
