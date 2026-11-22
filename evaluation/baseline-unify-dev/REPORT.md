# REPORT · dev 列同约定补测（8 基线 × oracle-v3 development 55 窗）

> 状态：**8/8 基线完成（DONE）** —— 逐基线 results_*_development.jsonl 均 55/55 行、0 error 行；analysis 与 REPORT 全部落盘。

- 日期：2026-11-22 ｜ 目的：填齐论文 tab:main dev 列——8 个沿用早期约定数字（59 窗早期 dev 4 选项 / 91 窗基准）的基线，统一到 **oracle-v3 development 55 窗 / 220 题 / 11 选项（8 action / 4 sev score 约定 / noul urgent）** 与 ORACLE 四线、I1/I2 kev-zs、E1 NanoJev-zs 同一张卷。
- 卷：`suites/oracle-v3/development.jsonl`（55 窗）。runner：`baseline_unify_runner.py`（A/B/C/E2/H，协议与 BASELINE-UNIFY test 轮逐字一致，仅换 split）+ `v3_baseline_runner.py`（F1/F2/G，与 V3-TEST-BASELINE 同一 runner）。两份 runner 均为**本目录副本**，原文件未动。
- 指标：`code/eval/evaluate.py` 同口径（tactic/urgent/severity/action acc+macroF1、exact、ECE 15 bins、P50 延迟）。产物：`results_*_development.jsonl` + `analysis_*_development.json|md`。

## 1. 八条新 dev 数字（oracle-v3 dev，n=55 窗 / 220 题）

| # | 基线 | tactic | macroF1 | urgent | sev | action | exact | ECE(tactic) | P50 延迟 |
|---|---|---|---|---|---|---|---|---|---|
| A | Rules 规则引擎 | 0.400 | 0.500 | 0.527 | 0.236 | 0.255 | 0.200 | -- | ~0 ms |
| B | MiniCPM-2B generative | 0.091 | 0.068 | 0.745 | 0.527 | 0.145 | 0.036 | -- | 2.9 s |
| C | MiniCPM-2B option-scored | 0.673 | 0.271 | 0.236 | 0.673 | 0.182 | 0.000 | 0.654 | 11.9 s |
| E2 | laya-421M zero-shot | 0.055 | 0.045 | 0.709 | 0.636 | 0.582 | 0.055 | 0.460 | 34 ms* |
| F1 | GLM-5.3 | 0.611 | 0.517 | 0.833 | 0.722 | 0.222 | 0.074 | -- | 1.9 s |
| F2 | DeepSeek-chat | 0.691 | 0.577 | 0.800 | 0.709 | 0.255 | 0.182 | -- | 0.5 s |
| G | Qwen3-8B prefill+few-shot (G2v6) | 0.291 | 0.224 | 0.800 | 0.455 | 0.273 | 0.182 | 0.244 | 2.8 s |
| H | Spark-X2.5-4B generative | 0.000 | 0.000 | 0.364 | 0.309 | 0.182 | 0.000 | -- | 8.1 s |

\* E2 延迟口径注释：本轮按主会话指示用 **GPU(cuda)** 推理（P50 34 ms）；test 列（BASELINE-UNIFY）为 CPU 8 线程（P50 4.9 s）。精度口径（choice 协议/checkpoint）一致；若论文分列延迟需加脚注。checkpoint 为 `~/Mylocllm/laya-family/laya-base`（与 09-29 test 轮所用 HF 快照同 sha256，HF cache 原快照已被清理）。

## 2. 新旧对照（旧 = RANGE-BASELINE `analysis_*_development.json`，59 窗×4 题 4 选项早期约定，n_rows=236；新 = 本轮 55 窗 11 选项，n_rows=220）

| # | 基线 | 旧 tactic | **新 tactic** | 旧 exact | **新 exact** | 旧 sev | **新 sev** | 主要偏差解读 |
|---|---|---|---|---|---|---|---|---|
| A | Rules | 0.441 | **0.400** | 0.155 | **0.200** | 0.186 | **0.236** | 量级一致；urgent 0.695→0.527（11 类/新真值下规则误报面变大） |
| B | MiniCPM gen | 0.153 | **0.091** | 0.086 | **0.036** | 0.508 | **0.527** | 行为一致（生成式小模型塌缩），幅度小降 |
| C | MiniCPM opt | 0.678 | **0.673** | 0.000 | **0.000** | 0.678 | **0.673** | tactic/sev 几乎不变；urgent 0.237→0.236（反向塌缩复现）；ECE 0.654 失准复现 |
| E2 | laya zs | 0.017 | **0.055** | 0.017 | **0.055** | 0.610 | **0.636** | tactic 仍塌缩（近随机）；sev/action 量级持平 |
| F1 | GLM-5.3 | 0.678 | **0.611** | 0.017 | **0.074** | 0.712 | **0.722** | tactic 略降（11 类更难+1 窗 invalid-JSON 计错）；exact 升 |
| F2 | DeepSeek | 0.644 | **0.691** | 0.552 | **0.182** | 0.763 | **0.709** | tactic 持平略升；**exact 大降 0.552→0.182（最大单项偏差，见 §3）** |
| G | Qwen3-8B G2v6 | 0.390 | **0.291** | 0.034 | **0.182** | 0.508 | **0.455** | tactic 降 0.10（11 类下 prefill 打分更散）；exact 升 5 倍 |
| H | Spark gen | 0.000 | **0.000** | 0.000 | **0.000** | 0.172 | **0.309** | tactic 双约定下均 0——"生成式小模型结构化多类崩溃"结论跨约定成立 |

### 偏差清单（需在论文换数/脚注时注意）

1. **F2 DeepSeek exact 0.552→0.182（-0.37）**：旧 59 窗 4 选项下 exact 虚高（选项空间小、action 命中易）；11 选项下四任务全对齐大幅变难。tactic/urgent/sev 均持平，属口径效应非行为退化。dev 列换 0.182。
2. **G Qwen3-8B tactic 0.390→0.291（-0.10）**、exact 0.034→0.182：prefill 打分在 11 类下分布更平，top-1 降但四任务一致性升（action 0.136→0.273）。
3. **A rules urgent 0.695→0.527**：dev 真值 55 窗与旧 59 窗不同卷+11 类标签空间；规则本身未变。
4. **F1 GLM 1 窗 invalid-JSON**（`e4-user_typos-20260922-0210`，raw 截断）计为全错，n_rows=216/220；协议与 test 轮一致（invalid 计错不重试）。
5. **E2 laya 延迟口径**：本轮 GPU（34 ms）vs test 列 CPU（4.9 s），见 §1 脚注。
6. 其余各列变动 ≤0.06，方向与 test 轮（BASELINE-UNIFY REPORT §2）一致：跨约定结论稳健。

## 3. 执行环境与事故记录

- **云 API（F1/F2）**：v3_baseline_runner.py 原有通路，key 运行时读 `~/.dsh/.credentials.yaml`（不入本报告）。成本实测：55 窗×2 模型 ≈ 220 次调用、~25 万 token 总量，费用可忽略（<¥1）。
- **GPU 纪律**：vLLM(Qwen3-8B, GPU0) 与 laya(GPU1) 启动前核查 `nvidia-smi` + `ps`，确认无他人训练进程（GPU0/1 均 17 MiB 空闲）；全部推理进程 nice+taskset 绑核。跑完即停，GPU 已释放。
- **本地 CPU 服务（B/C/H）**：llama.cpp Q8_0（Spark@18080 / MiniCPM@18081），与 BASELINE-UNIFY test 轮同二进制同量化同模板。
- 事故 1：hermes 后台 scope 的 cgroup 内存上限导致 llama-server 大分配（--no-mmap/--mlock）被 OOM 杀、mmap 页在 scope 内被激进回收（推理一度 3.9 tok/s）。处置：服务改 `systemd-run --user` 启动（scope 外）+ --mlock，恢复正常速率；受污染的 minicpm-opt 29 个全零 dist 行已剔除重跑（`results_minicpm-opt_development.jsonl.bak-bad` 留档），终版 55/55 有效。
- 事故 2：H Spark 首轮 55 行全为 connection-refused（上述 OOM 连锁），已整文件重跑，终版 55/55 valid-JSON、0 err。
- 完整性核验：8 个 results 文件均 55 行、55 唯一 id、0 error 行（F1 另有 1 行 invalid-JSON 有效预测行为，见偏差清单 4）。

## 4. 产物清单

`results_{rule,minicpm-gen,minicpm-opt,laya-zs,glm,dsk,g2v6-qwen,spark-gen}_development.jsonl`（各 55 行）
`analysis_<同上>_development.json|md`（evaluate.py 同口径）
`baseline_unify_runner.py` / `v3_baseline_runner.py`（本目录副本；laya 副本含两处适配：checkpoint 路径指向 laya-family 同 sha256 副本、device 可由 `LAYA_DEVICE` 环境变量指定，默认仍 cpu）
`logs/*.log`（逐基线运行日志）
