# BERT-CALIB 执行报告 — ModernBERT 四头基线 Method-A 分桶温度校准（2026-11-11）

- 任务：TASK-MODERNBERT-CALIB-20261111（JISA 转投补强；审稿 R2 质疑 ModernBERT 基线校准处理未说明）
- 执行：oracle 补充实验（不重训，仅补校准）；脚本 `bert_calib_eval.py`，日志 `run.log`，逐窗 raw logits 落盘 `logits_{calibration,test,development}.json`（可 `--replay` 纯 CPU 复算）

## 协议（与 ORACLE kev 线方法 A 完全同口径）

| 项 | 口径 |
|---|---|
| checkpoint | `EVAL/BATCH2-TRAIN/bert-baseline/bert_baseline.pt`（B1 原始权重，未动、未重训） |
| 数据 | suites/oracle-v3：`calibration.jsonl`（55 窗）拟合，`test.jsonl`（439 窗）出数 |
| 分桶 | 按题型各一桶：tactic / urgent / severity / action 四头各一个单参数温度 T |
| 拟合 | `kev.metrics.fit_temperature(**TEMPERATURE_FIT)`——calib split raw logits 上 min micro NLL，121 点 log 网格 0.25..4（与 kev 主线 head.pt T=2.047 同一实现，`code/eval/methodA_test_formal.py` 同款） |
| 指标 | acc / exact（argmax 温度不变）；ECE = **15 等频桶**（`train_bert_baseline.py` / evaluate.py 论文口径）；NLL 逐头 + 全题 micro 均值 |
| 资源纪律 | GPU 推理绑核 48-63 + nice 10 + ionice c3；卡上仅自有 vLLM（27GB），未触碰他人进程 |

**复核**：development 55 窗推理精确复现训练时 `bert-baseline/metrics.json`（tactic 0.6909 / exact 0.6727 / tactic ECE15 0.29545），确认 checkpoint 加载与推理和 B1 训练时逐位一致。

## 拟合温度（calib 55 窗）

| 题型 | T |
|---|---|
| tactic | 1.8661 |
| urgent | 2.0000 |
| severity | 2.1435 |
| action | 1.6625 |

四桶 T 均落在 1.66–2.14，与 ORACLE kev-4B 主线 T=2.047 同量级——过置信方向/幅度同源。

## test 439 窗：校准前（T=1）vs 校准后（逐头 Method-A T）

| 头 | acc 前→后 | ECE15 前→后 | NLL 前→后 | mean_conf 前→后 |
|---|---|---|---|---|
| tactic | 0.6811 → 0.6811 | **0.2636 → 0.2765** | 1.9721 → 1.3621 | 0.934 → 0.719 |
| urgent | 0.7813 → 0.7813 | 0.1720 → 0.1974 | 0.8842 → 0.6084 | 0.944 → 0.825 |
| severity | 0.6902 → 0.6902 | 0.2754 → 0.2752 | 1.7349 → 1.0492 | 0.966 → 0.777 |
| action | 0.6879 → 0.6879 | 0.2484 → 0.2322 | 1.2761 → 0.9994 | 0.903 → 0.747 |
| **exact** | **0.6811 → 0.6811** | — | — | — |
| **micro NLL（全 1756 题）** | — | — | **1.4668 → 1.0048（−31.5%）** | — |

机器可读全量指标：`bert_calib_result.json`。

## 结论（如实报告）

1. **准确率不变**：温度缩放不改 argmax，tactic 0.6811 / exact 0.6811（439 窗）与校准前逐位一致。
2. **NLL 大幅改善、置信度回落**：micro NLL −31.5%（1.467→1.005），四头 mean_conf 从 0.90–0.97 降到 0.72–0.83——严重过置信（raw mean_conf ≈0.94 vs tactic acc 0.68）被 Method-A 温度实质软化。
3. **ECE 基本持平、分头涨跌互现**：tactic 0.264→0.277（+0.013）、urgent 0.172→0.197（+0.025）、severity 持平、action 0.248→0.232（−0.016）。即与 ORACLE 主线同款的"NLL/置信度大幅改善、ECE 分任务陈述"模式——**分桶温度修 NLL，不修 15 等频 ECE**。
4. **公平性结论（回应 R2）**：给 ModernBERT 基线补上与 ORACLE 线完全同口径的 Method-A 分桶温度校准后，其 tactic ECE（0.277）仍约为 ORACLE kev-4B 校准后（0.140）的 2 倍，tactic acc 低 17pp——**校准处理差异不构成基线劣势的解释，substrate（PDM 底座）必要性结论不受影响**。论文 §6.2 可将"未校准"标注升级为"已做同口径校准，结论不变"。
5. 数据注记：test 上 exact（299/439）与 tactic 正确数（299/439）恰好相等——四头错误高度相关（tactic 错的窗几乎必有其它头同错），已逐窗核验非计算错误。

## 产物清单

- `bert_calib_eval.py`（推理+拟合+指标，`--replay` 可复算）
- `bert_calib_result.json`（结果 JSON：协议、拟合温度、前后对照、dev 复核）
- `logits_{calibration,test,development}.json`（逐窗 raw logits，复算依据）
- `run.log`（执行日志，RC=0）
- 本报告
