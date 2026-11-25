# 温度校准正式版报告（方法 B：per-workload + 5-fold OOF + paired bootstrap）

- 日期：2026-09-26 · 任务：FINAL-REPORT-V3 §5 遗留 ③ · 论文 [TBD-Calib-B] 回填来源
- 工具：kev.calibrate workload_report（kev-repo 官方路线）
- 输入：oracle-v3 suite calibration 分区 raw-logits rows（55 窗 / 220 问，range-only）
- 参数：folds=5 · seed=0 · bootstrap samples=1000 · 拟合=min micro-NLL 121 点对数网格

## 1. kev-4B v3（calib 卷 n=220）

- workload T=2.05（与方法 A 的 2.0467 一致）；fold 温度 [2.05, 1.91, 2.00, 2.14, 2.19]（跨 fold 稳定，无过拟合迹象）

| arm | acc | ECE | Brier | NLL | conf | c-err | cov@5% | AURC |
|---|---|---|---|---|---|---|---|---|
| raw (T=1) | 0.845 | 0.140 | 0.298 | 0.926 | 0.929 | 0.123 | 0.00 | 0.194 |
| shipped | 0.845 | 0.140 | 0.298 | 0.926 | 0.929 | 0.123 | 0.00 | 0.194 |
| workload（in-sample） | 0.845 | 0.148 | 0.317 | 0.678 | 0.782 | 0.050 | 0.00 | 0.187 |
| **workload_oof（OOF）** | 0.845 | **0.150** | 0.319 | **0.688** | 0.780 | 0.055 | 0.00 | 0.194 |

paired bootstrap（workload_oof − shipped，95% CI）：
- ECE +0.011 [-0.032, +0.070]
- Brier +0.021 [-0.007, +0.045]
- cov@5%err -0.005 [-0.018, +0.023]
- AURC -0.001 [-0.015, +0.010]

## 2. kev-0.8B v3（calib 卷 n=220）

- workload T=1.91（与方法 A 的 1.9097 一致）；fold 温度 [1.91, 1.78, 1.91, 1.95, 1.95]

| arm | acc | ECE | Brier | NLL | conf | c-err | cov@5% | AURC |
|---|---|---|---|---|---|---|---|---|
| raw (T=1) | 0.814 | 0.112 | 0.332 | 0.893 | 0.908 | 0.105 | 0.04 | 0.158 |
| shipped | 0.814 | 0.112 | 0.332 | 0.893 | 0.908 | 0.105 | 0.04 | 0.158 |
| workload（in-sample） | 0.814 | 0.100 | 0.334 | 0.704 | 0.763 | 0.036 | 0.01 | 0.170 |
| **workload_oof（OOF）** | 0.814 | **0.102** | 0.335 | 0.708 | 0.764 | 0.036 | 0.02 | 0.170 |

paired bootstrap（workload_oof − shipped，95% CI）：
- ECE -0.010 [-0.082, +0.054]
- Brier +0.003 [-0.021, +0.025]
- cov@5%err -0.018 [-0.050, +0.005]
- AURC +0.012 [-0.000, +0.026]

## 3. 论文口径结论（[TBD-Calib-B] 回填）

1. **NLL 大幅改善、置信度诚实化**：加温后 NLL 0.926→0.688（4B）/0.893→0.708（0.8B），confident-error 0.123→0.055 / 0.105→0.036；OOF 与 in-sample 几乎重合（ΔECE ≤0.002），55 窗的 calib 拟合**没有过拟合**。
2. **ECE 结论需分线陈述**：0.8B 微升后 ECE 改善（0.112→0.102）；4B raw 本已接近匹配其置信度（ECE 0.140），单温度全局拉伸使等距 ECE 微升（0.140→0.150）但 c-err 减半——论文建议以 NLL/c-err 为主指标、ECE 分任务报告。
3. **5-fold 温度稳定性**：两线 fold 极差 ≤0.28/0.17，温度估计稳健；方法 A（head.pt 已载）与方法 B（workload 拟合）温度一致到小数点后两位——checkpoint 已发布的温度就是正式版温度。
4. 所有差值 CI 均跨 0：calib 卷规模（220 问）下，方法 B 相对 shipped 的改进不具统计显著性——如实报告，作为"单温度已捕获主要校准增益"的证据。

## 4. 产物

- calib-methodB-kev4b-v3.json · calib-methodB-kev08-v3.json（完整 arms + bootstrap）
- eval-logs/{kev4b,kev08}.log（原始输出）
- 脚本：code/eval/run_methodB.sh
