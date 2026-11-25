# REPORT · Kev-4B zero-shot oracle-v3 dev 补评（论文表 2 I2 行 dev 侧，55 窗统一约定）

- 日期：2026-11-25 · 任务：表 2 I2 行（kev-4B zero-shot）dev 侧五格 + ECE 为 RANGE-BASELINE 早期 59 窗约定残值（0.746/.814/.424/.627/.190/ECE .278，n=59），55 窗 v3 dev 无现成产物——按 55 窗同约定重跑补齐（test 侧 n=439 现有产物零改动）。
- 模型：本地快照 jaredpalmer/kev-4b（snapshot 485ace87，release_date 2026-09-22，与 test 侧同源），kev.serve bf16 CUDA GPU0，`systemd-run --user --collect -p MemoryMax=infinity` 拉起、离线 env（HF_HUB_OFFLINE=1/TRANSFORMERS_OFFLINE=1），独立端口 8028，测后即停。
- 协议：与 V3-TEST-BASELINE 五方重评的 kev4b-zs test 路径**完全一致**——同一 `v3_baseline_runner.py kev4b-zs development`（问题模板/四问构造/emit 行格式/断点续跑零改动），同一 oracle-v3 development.jsonl（55 窗 / 220 问，11 选项 TACTIC_CRITERIA + 8 选项 ACTION_CRITERIA）；指标用同 `evaluate.py`（同 schema，含 macro-F1/QWK/MAE/ECE15 等频/risk-coverage/bootstrap CI/每窗 latency）。
- 终态：**55/55 窗、0 error 行、id 集合与 suite 完全一致、每行 probs.tactic 恰 11 键 / probs.action 恰 8 键**；一次跑通，无断点续跑，无 rm，历史文件零改动。

## 1. dev 55 窗正式数字（表 2 I2 行 dev 侧）

| 任务 | acc | 备注 |
|---|---|---|
| tactic | **0.727** | macroF1 0.543 |
| urgent | **0.800** | |
| severity | **0.345** | QWK 0.713，MAE 0.67；low 37/0.30、medium 9/0.89、high 8/0.00、critical 1/0.00 |
| action | **0.691** | |
| exact | **0.200** | 11/55 |
| ECE15（tactic / action） | **0.321** / 0.371 | 等频 15 bin（同 evaluate.py 口径） |
| 每窗延迟 | P50 304.6 ms / P95 373.6 ms | 首窗暖机 94.7 ms；含一次性 serve 冷启动不在窗内 |

来源：`analysis_kev4b-zs_dev_v3.json`（bootstrap 95% CI：tactic 0.618-0.836 / severity 0.218-0.473 / urgent 0.691-0.891，按 group 聚类）。

## 2. 与旧 59 窗残值 / test 侧的关系

| | 旧 dev（59 窗残值，弃用） | 新 dev（55 窗 v3） | test（n=439，不动） |
|---|---|---|---|
| tactic | 0.746 | **0.727** | 0.761 |
| urgent | 0.814 | **0.800** | 0.831 |
| severity | 0.424 | **0.345** | 0.410 |
| action | 0.627 | **0.691** | 0.636 |
| exact | 0.190 | **0.200** | 0.194 |
| ECE | 0.278 | **0.321** | 0.237 |

1. dev 55 与 test 439 同带一致（tactic 0.727 vs 0.761、action 0.691 vs 0.636），差异方向与窗口集合差异（dev benign 37/55=67% vs test 299/439=68%，量级相近）相符，无异常。
2. severity 0.345 与 test 0.410 同为 0.3-0.4 弱项带：零样本 score 头未校准（dev high/critical 0/9 命中，与 test 侧 by_severity 模式一致），微调后 0.724 的论文论断不受影响。
3. 旧 59 窗残值与新值的差（severity -0.079 / action +0.064）属窗口集合差异（55 vs 59）+ 同协议重测波动，量级在 bootstrap CI 内，无系统性偏移。表 2 I2 行 dev 侧应回填新值并使 n 标注统一为 55 窗 v3 约定。

## 3. 产物

- rows：`results_kev4b-zs_dev_v3.jsonl`（55 行；runner 原始输出名 `results_kev4b-zs_development.jsonl`，按交付命名约定改名，内容一字未动）
- 指标：`analysis_kev4b-zs_dev_v3.{json,md}`（evaluate.py 同 schema）
- 日志：`logs/kev4b_serve_dev.log`（serve 冷启动/服务端请求流）、`logs/kev4b_zs_dev.log`（runner 进度）
- 报告：本文件（REPORT-KEV4B-ZS-DEV.md）
- test 侧零改动：`results_kev4b-zs_test.jsonl`（439 行）及 `analysis_kev4b-zs_test_v3.{json,md}` 哈希前后一致（452eba91…/e29bae26…/bfac5b4b…）。

## 4. 执行偏离

无。一次跑通（55/55、0 err），无断点续跑发生，无 rm，历史文件零改动；serve 用 systemd-run 临时单元拉起、测后即停，GPU0 全程未触碰队友进程（GPU1）。
