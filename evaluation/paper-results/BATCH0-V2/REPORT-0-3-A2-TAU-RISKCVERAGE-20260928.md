# REPORT-0-3 A2 τ/τ_h 阈值反推 + test risk-coverage 运营点

- 计划编号：**0-3 A2**（补充实验执行计划 v2 批次 0 · 2026-09-28）
- 结论一句话：**在严格窗口级 mishandling 口径（四任务任一错即误处置）下，calib 220 问只能支撑 τ=0.9896（自动化率 1.8%）；test 439 窗上 4B 在 ≤5% 预算下无可行 τ（顶部有 9 个连续高置信错窗），计划书"coverage ~60-75%"预期不成立——如实报告。**
- 复算脚本：`code/analysis/batch0_v2_20260928.py` · 数字来源：`EVAL/BATCH0-V2/batch0-results.json` `tau_derivation` / `test_risk_coverage` / `tier_routing` · 曲线数据 `risk-coverage-curves.json`（论文第 3 张图）

## 0. 口径说明（重要）

- 部署概率 = 方法 A 温度缩放后（4B T=2.0467 / 0.8B T=1.9097，bench-calib 拟合、head.pt 已载）。
- **窗口级 mishandling（主口径）**：门控信号 = tactic 校准置信度；一个窗四任务（tactic/urgent/severity/action）任一错即 mishandled——与"自动化处置整个窗"的路由语义一致。
- 问题级（参考口径）单独列出，因 calib 顶部有 1 个 action 高置信错问，问题级在 1%/2%/5% 预算下直接无解。
- τ 语义 = kev.metrics.select_threshold：按 conf 降序最大可接受前缀末端的 conf。

## 1. τ 反推（T1-KEV4B/round3-v3/bench-calib/rows.json，220 问 / 55 窗，methodA_T 概率）

| 预算 | 口径 | τ | calib 自动化率 | calib 实测 mishandling |
|---|---|---|---|---|
| ≤5% | 窗口级 | **0.9896** | 1.8% (1/55) | 0.0 |
| ≤2% | 窗口级 | **0.9896** | 1.8% | 0.0 |
| ≤5% | 问题级 | 无解 | — | — |
| ≤2% | 问题级 | 无解 | — | — |

55 窗的 calib 卷在窗口级口径下只有 1 个窗满足 ≤2%（离散粒度太粗，τ_5% 与 τ_2% 同值）。

## 2. test 439 窗 risk-coverage（methodA_T）

| 线 | 窗口级 cov@1%/2%/5% | 窗口级全量 risk | tactic 问级 cov@5% | tactic 全量 risk |
|---|---|---|---|---|
| kev-4B | **0 / 0 / 0** | 0.371 | 0 | 0.150 |
| kev-0.8B | 0.002 / 0.002 / 0.002 | 0.406 | 0.011 | 0.237 |

4B 不可行的直接原因（逐窗核实）：test tactic 置信度前 10 窗中 9 个错——e4-batch_deploy / e4-routine_login / e4-backup_job / e1-normal 等良性窗以 conf≈0.989-0.992 被持续判为 credential_access（pred=7，label=0=benign），错误聚集在置信度顶部，任何 ≤5% 预算的前缀都被这批窗击穿。这不是校准问题（这些窗真的错了），是"批量部署/例行登录"类良性窗与 sg4 credential_access 训练形态的系统性混淆——**与 cam-lds 发现的"4B 过度泛化到最熟悉类（execution 260 窗误报）"同一失败模式的 test 卷版本**。

0.8B 反而有 0.2-1.1% 微覆盖：其错误不聚集在顶部。

## 3. 各 tier 路由占比（τ=0.9896 外推到 test，methodA_T，窗口级）

| 线 | Tier1 自动 (conf≥0.9896) | Tier2 人工带 | Tier3 入队 | Tier1 实测 mishandling |
|---|---|---|---|---|
| kev-4B | 2.05% | 0%（τ_2%=τ_5% 同值，带空） | 97.95% | 1.00（9/9 全错） |
| kev-0.8B | 5.69% | 0% | 94.31% | 0.80 |

**运营读法：当前 4B 在严格四任务口径下不具备"高置信自动处置"能力**；若放宽为 tactic 单任务 mishandling（风险=错误分类本身），4B tactic 全量 risk 0.150、0.8B 0.237，且 AURC（0-4 报告）显示 4B 排序质量优于 0.8B——门控在"分级路由（Tier2/3 人工+队列）"意义上仍然有效（98% 进人工/队列 = 零漏报自动化），但"高置信直通"运营点需要先解决顶部良性误判簇（候选：batch_deploy/routine_login 类加规则白名单，或 C1 对抗探针后扩 calib 卷）。

## 4. 与计划书预期的偏离（如实声明）

- 预期"kev-4B 在 mishandling≤5% 档 coverage ~60-75%（test tactic 0.850 推算）"**未兑现**。推算错在两点：①0.850 是 tactic 单任务准确率，窗口级四任务全对率仅 0.629（exact）；②高置信区错误聚集（顶部 10 窗 9 错）使前缀型阈值无解——accuracy 高不等于 selective 风险低，这正是 risk-coverage 曲线要暴露的。
- 论文回填建议：§3.3/§6.4 运营点表按本报告数字写"realized operating points"：τ(≤5%, 窗口级)=0.99、自动化 2%、其余路由人工/队列——诚实呈现"当前门控价值在漏报拦截而非自动直通"，同时 §6.4 配第 3 张图（曲线数据已存）。

## 5. 产物

- `risk-coverage-curves.json`：calib 55 窗 + test 439 窗两线窗口级全曲线（coverage/risk/conf 三元组，可直接画图）
- 全部数字在 `batch0-results.json`，由 `code/analysis/batch0_v2_20260928.py` 一键复算
