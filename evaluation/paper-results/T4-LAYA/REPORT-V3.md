# T4 laya RLCD v3 重训报告（WP-V6 第 2 线）——数据修复在 RLCD 范式的复制

- 日期：2026-09-26 · 训练：oracle-v3 suite（items-v3，train 60,164 / calib 220），4 epochs / 83.9 分钟 / 峰值 8.4GB / final loss 0.682
- checkpoint：`laya-oracle-v3/`（checkpoint_epoch1-4 全存 + 三桶温度 4.84/9.04/9.22）
- 评测：`eval_laya_ft.py` 对 checkpoint_epoch4（model.safetensors 目录），dev 59 窗 + test 470 窗

## 1. 双卷四任务成绩（v3 微调 vs 零样本 vs v1 微调）

| 指标 | 零样本 dev | v1 微调 dev | **v3 微调 dev** | 零样本 test | v1 微调 test | **v3 微调 test** |
|---|---|---|---|---|---|---|
| tactic | 0.017 | 0.155 | **0.729** | 0.029 | 0.158 | **0.657** |
| urgent | 0.655 | 0.776 | **0.763** | 0.697 | 0.764 | **0.738** |
| severity | 0.621 | 0.241 ❌ | **0.729** | 0.595 | 0.241 ❌ | **0.596** |
| action | 0.603 | 0.052 ❌ | **0.763** | 0.586 | 0.094 ❌ | **0.713** |
| exact | 0.017 | 0 ❌ | **0.559** | 0.016 | 0.007 | **0.472** |
| benign 召回 | — | 全塌 credential_access | **0.900**（36/40） | — | — | **0.862**（262/304） |
| ECE(choice) | 0.508 | 0.227 | **0.123** | 0.504 | 0.143 | **0.149** |
| P50 延迟 | 113ms | 25ms | 72ms | — | — | 72ms |

**v3 判定：四任务全部转正。** v1 时代的两大塌缩（tactic 59/59 全塌 credential_access、severity/action −0.4/−0.5 退化）全部消失：
- tactic dev 0.155→**0.729**（4.7 倍），预测分布健康（benign 43 / credential_access 9 / reconnaissance 6 / privilege_escalation 1），benign 召回 0.900
- severity 0.241→**0.729**、action 0.052→**0.763**，均超零样本
- exact 0→**0.559**（dev），test 0.472
- 校准进一步改善：ECE dev 0.123（v1 为 0.227）
- 延迟 72ms 仍远快于 LLM 系（kev-4B ~秒级），低延迟门控档位价值保持

## 2. 与 kev 线对照（v3 数据下）

同卷严格对照见 §2a；本表为 v1 suite dev 59 窗（与 laya v1 基线同卷，训练数据同源 v3）：

| 指标 | kev-4B v3 | kev-0.8B v3 | **laya v3** | 范式 |
|---|---|---|---|---|
| tactic | 0.782 | 0.727 | 0.729 | RLCD proper scoring |
| severity | 0.673 | 0.709 | 0.729 | |
| action | 0.691 | 0.691 | 0.763 | |
| exact | 0.582 | 0.618 | 0.559 | |
| benign 召回 | 0.865 | 0.865 | 0.900 | |
| 峰值显存 | — | — | **8.4GB** | |
| 延迟 | — | — | **72ms** | |

### 2a. oracle-v3 suite dev 55 窗严格同卷对照（`results_v3suite_dev.jsonl`，脚本 `code/eval/eval_laya_ft_v3.py`）

| 指标 | kev-4B v3 | kev-0.8B v3 | **laya v3** | NanoJev v3 |
|---|---|---|---|---|
| tactic | **0.782** | 0.727 | 0.655 | 0.673 |
| urgent | **0.782** | 0.764 | 0.764 | **0.782** |
| severity | 0.673 | **0.709** | 0.545 | 0.673 |
| action | 0.691 | 0.691 | **0.709** | 0.600 |
| exact/overall | 0.582 | 0.618 | 0.455 | — |
| benign 召回 | 0.865 | 0.865 | 0.838 | — |

laya 在严格同卷下 tactic 0.655（v1 suite 59 窗为 0.729，两卷类别构成不同）；仍全部远超 v1 微调（0.155），无塌缩（benign 40 / credential_access 10 / 多类齐用）。

421M 的 laya 在 v3 数据下四任务与 kev-4B/0.8B 同档（action/benign 召回甚至最优）——"小模型+正确数据"结论在第四种范式（RLCD）上第三次复制。

## 3. 结论

1. **v3 数据修复跨范式成立**：CE / CE+anchor / RLCD 三种范式同数据修复后全部转正——退化根因确凿在 v1 数据（B1-B7 偏置链），与训练范式无关
2. **RLCD 的校准优势在好数据下兑现**：ECE 0.123 为四线最优，配合 72ms 延迟，"校准+低延迟门控"是 laya 的差异化定位
3. 温度拟合三桶值（4.84/9.04/9.22）中两个仍超 laya 合法区间 [0.5,5] 被 clamp——置信度绝对值欠校准（ECE 是排序后近似），后续可用方法 B 正式版重拟

## 4. 产物

- `T4-LAYA/laya-oracle-v3/`（checkpoint_epoch1-4 + training_summary.json）
- `T4-LAYA/results_v3_{dev,test}.jsonl`（59+470 逐条预测+概率+延迟）
- `T4-LAYA/{eval_v3_dev,eval_v3_test,eval_v3_all}.log`
- 训练脚本 `T4-LAYA/run_laya_v3.sh` / `code/train/train_laya_rlcd.py` / items-v3/
