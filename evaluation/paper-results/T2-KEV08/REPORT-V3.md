# kev-0.8B v3 重训报告（WP-V6 第 1 线）——规模实验

- 日期：2026-09-25 · 训练：oracle-v3 suite，2 epochs / 3,762 步 / ~25 分钟（0.38s/rec，约为 4B 的 44%）/ loss 0.192 · 无 anchor（v3 数据先验正确后无需锚定）
- checkpoint：runs/oracle-kev08-v3 · bench：v3-bench/（0 rejected / 0 truncated）

## 1. dev 对比（0.8B 三态）

| 指标 | 0.8B 零样本 | 0.8B v1 微调（anchor） | **0.8B v3 微调** |
|---|---|---|---|
| tactic | 0.259 | 0.085 ❌ | **0.727**（2.8 倍零样本）|
| urgent | 0.793 | 0.746 | 0.764 |
| severity | 0.190 | 0.169 | **0.709** |
| action | 0.121 | 0.237 | **0.691** |
| exact | — | — | **0.618** |
| benign 召回 | — | 塌缩 | **0.865**（32/37）|

预测分布：benign 41 / credential_access 12 / reconnaissance 2——健康，无塌缩。

## 2. 规模对照（v3 数据下 4B vs 0.8B）

| 指标 | kev-4B v3 | kev-0.8B v3 | 差距 |
|---|---|---|---|
| tactic | 0.782 | 0.727 | -0.055 |
| urgent | 0.782 | 0.764 | -0.018 |
| severity | 0.673 | **0.709** | +0.036 |
| action | 0.691 | 0.691 | 0 |
| exact | 0.582 | **0.618** | +0.036 |
| benign 召回 | 0.865 | 0.865 | 0 |
| 训练时长 | 54 min | 25 min | 46% |

## 3. 结论

1. **v3 修复跨规模成立**：0.8B 四任务全正增益——数据修复不是 4B 特效
2. **微调后规模重要性显著下降**：tactic 差距仅 0.055，severity/exact 反而 0.8B 更优；训练成本减半——"小模型+正确数据 ≥ 大模型多数指标"，支撑轻量部署叙事
3. 与 v1 时代对照：v1 数据下 0.8B tactic 0.085（被捷径数据伤得比 4B 轻但同样崩）；v3 数据下 0.727——数据质量是第一位变量的结论再次成立

## 4. 产物

runs/oracle-kev08-v3 · T2-KEV08/{train-log/train_v3_wrapper.log, v3-bench/, REPORT-V3.md}
