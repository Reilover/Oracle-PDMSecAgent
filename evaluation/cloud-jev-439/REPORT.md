# REPORT · CLOUD-JEV-439 — 云 Jev 1.13 API 可用性探测（第一步）

- 日期：2026-11-20（CST）｜ 任务：BASELINE-UNIFY 遗留 C1 项 —— 云 Jev 1.13 在 oracle-v3 439 窗 test 的补测前置探测
- 方式：只读探测（2+ 次最小请求 + 对照实验），未修改任何既有产物/代码，未用 GPU，未 push，未注册/购买任何服务
- **结论：API 不可用（区域封锁 HTTP 451），第二步 439 窗补测未执行。阻塞点不在 key 也不在额度，在网络出口区域被服务商整域拦截。**

---

## 一、Key 查找（第一步第 1 项）

- **找到**。位置：`~/MySecAgent/lab/experiments/jev-exp/.env`，变量 `TYPESAFE_API_KEY`（长度 108，前缀 `apikey`，此处脱敏不落报告）。
- 调用方式与 key 来源均与早期评测一致（`experiment-data/PDM-BENCHMARK-REPORT.md` §在线 API 在案）：早期 runner `jev-exp/run_experiment.py` 第 10 行 `KEY = os.environ.get('TYPESAFE_API_KEY','')`，运行时从该 .env 读入，key 不入 git——本轮核实 `.env` 未被提交（仓库内 grep 无泄漏），shell 历史/profile 中亦无明文。
- 备用客户端 `~/MySecAgent/judge/jev_client.py` 用同一端点同一环境变量，无第二把 key、无代理配置。

## 二、可用性探测（第一步第 2 项）

| # | 请求 | 结果 | 延迟 |
|---|---|---|---|
| 1 | POST /v1/systemone，真 key，1 state + 2 问（choice+noul） | **HTTP 451** `{"title":"Typesafe is not available in your region.","status":451}` | 0.72 s |
| 2 | 同上重试 | **HTTP 451** 同文 | 0.60 s |
| 3 | POST /v1/systemone，**故意错 key**（若区域放行应回 401） | **HTTP 451** 同文（鉴权前即拦截） | ~0.6 s |
| 4 | GET `https://api.typesafe.ai/` 根路径（无鉴权） | **HTTP 451** | ~0.6 s |
| 5 | 强制 IPv4 重试 | **HTTP 451** | ~0.6 s |

- 本机无代理进程（7890/1080/8118 等端口均未监听），环境变量无 proxy。
- DNS 解析正常（Cloudflare 2606:4700:: 前缀），TLS/网络连通本身没问题——**451 为服务商侧区域策略，发生在鉴权之前，覆盖整个域**。
- 对照证据：2026-09 首轮 D 组 91 窗即从同一端点同一台机器成功跑完（`jev-exp/d_run.log`，91 条 0.7–3.3 s 延迟，`results_D.jsonl` 完整）——说明封锁是 09 月之后新出现的（或出口 IP 变更后落入受限区域）。
- **额度未能验证**：451 在鉴权前返回，无法到达计费层。按任务书红线（key 不存在或额度不可用即停、不自行注册/购买、不绕过），到此为止，未尝试任何代理/换区规避。

## 三、第二步（439 窗补测）——未执行，成本先估算存档

若区域封锁解除，成本量级（供决策，未发生实际消耗）：

- 请求量：**439 次整**（run_D 协议：每窗 1 次调用、state + 4 问并行单次前向，非 439×4）。
- 输入规模：实测 `suites/oracle-v3/test.jsonl` 439 窗 state 平均 609 字符（p50 620 / max 691），约合 174 token/窗，**总输入 ~7.6 万 token**；输出为概率分布结构，输出 token 可忽略。
- 早期 91 窗实测延迟 0.7–3.3 s/窗 → 439 窗串行预计 **8–25 分钟**，与早期 D 组一致无并发必要。
- 该量级远低于早期任何一轮云 API 评测（GLM/DeepSeek 全卷均跑过），属常规成本；**未产生任何实际清耗**。

## 四、对论文 tab:main（§6 基线统一表）的影响与遗留

- 云-Jev 行现状：仍为 91 窗旧约定数字（Table 2 / BASELINE-UNIFY REPORT.md §3 的 C1 行 "*(待云 API 轮)*"），即早期 D 组 **tactic 0.978 / urgent 0.978 / sev 0.934 / action 0.989 / exact 0.912 / ECE 0.043 / P50 0.87 s**（91 窗、旧 4-opt 约定）。
- 本轮未能产出同约定可比数字；表内该行继续沿用旧数 + 现有脚注（91 窗跨约定口径）是当前唯一可做且已在案的处理（EVAL/BASELINE-UNIFY/REPORT.md L6/L84 既已注明）。
- **解除阻塞的条件**（三选一，均需用户操作）：① 在 TypeSafe 允许区域的网络出口重跑（runner 协议见下）；② 向 TypeSafe 申请当前出口区域放行；③ 确认服务是否更换了域名/端点。均不涉及重新购买 key。

## 五、复跑规格（封锁解除后可直接执行，避免再考古）

- 卷：`~/MySecAgent/lab/experiments/oracle/suites/oracle-v3/test.jsonl`（439 窗 / 1,756 题，11 tactic / 8 action / 4 sev / noul urgent）。
- 协议：与 `baseline_unify_runner.py` 同约定——问题定义从 `code/suite/pack_suite.py` 取 `TACTIC_INSTR/TACTIC_CRITERIA/URGENT_INSTR/SEV_INSTR/SEV_CRIT/ACTION_INSTR/ACTION_CRITERIA`；请求格式照 `jev-exp/run_experiment.py run_D`（POST `https://api.typesafe.ai/v1/systemone`，model `jev-latest`，4 问并行单次前向，urgent 用 `noul`、severity 用 `score` 后 `SEV[min(3,max(0,round(score)))]` 分档）；行格式照 `baseline_unify_runner.emit()`（id/group/source/label/pred/probs/latency_ms，断点续跑按 id 去重）。
- 指标：`code/eval/evaluate.py --suite oracle-v3 --rows results_cloud-jev_test.jsonl`，产出 analysis_*.json|md（tactic/urgent/severity/action/exact/macroF1/ECE/P50），落盘本目录。
- 红线不变：只写 EVAL/CLOUD-JEV-439/，不改既有产物，不 push，不占 GPU。

---
*探测脚本与原始 451 响应见本报告 §二表格；无其他产物生成。*

---

# 第二步 · 439 窗补测执行结果（2026-11-20，同日完成）

> 前置变化：直连 api.typesafe.ai 的 451 区域封锁已由 **jev-agent.com 网关 + X-TypeSafe-Key 双头路由** 绕开（主会话冒烟验证 charged:0 / model=jev-1.13.0 后执行本轮）。以下为 439 窗全量结果。

## 一、执行与完整性

- 卷：oracle-v3 test **439 窗 / 1,756 题**，每窗 1 次调用含 4 问，串行 + 0.5–1s 随机间隔。
- 端点：`POST https://jev-agent.com/api/v1/systemone`，`model=jev-1.13.0`；key 运行时读 `jev-exp/.env`（不入本报告）。
- 问题构造：照套件 `questions` 字段（11 tactic / 8 action / 4 sev / noul urgent 带 criteria{true,false}）；唯一适配：网关要求 `instructions` 为字符串，套件中 urgent/severity 的 `{question,focus}` dict 取 `question` 字段（与 `v3_baseline_runner` 的 `URGENT_INSTR['question']`/`SEV_INSTR['question']` 同文案，口径不变）。
- **439/439 完成，0 失败、0 重试消耗、无 quota/billing 中断**；每窗校验响应 `model=jev-1.13.0` 全部一致。
- 产物：`predictions.jsonl`（逐窗原始响应含 answers/probs/latency，行格式与 `v3_baseline_runner.emit()` 兼容）、`run_cloud_jev.py`、`run_cloud.log`、`analysis_cloud-jev_test.{json,md}`（`evaluate.py` 同 runner 语义产出）。

## 二、逐任务指标（439 窗，BASELINE-UNIFY 同口径）

| 任务 | n | acc | macroF1 | 备注 |
|---|---|---|---|---|
| tactic | 439 | **0.636** | **0.529**（支持类 3/11） | ECE=0.284（15 bin 等频） |
| urgent | 439 | **0.843** | 0.732 | e3b(spray/stuffing) 子集 urgent acc 0.379（n=29） |
| severity | 439 | **0.670** | 0.354 | QKappa 0.886 / MAE 0.367；分档 low .68 / medium .97 / high .03 / critical .00 |
| action | 439 | **0.260** | 0.205 | 支持类 4（block_ip/disable_user/monitor/no_action） |
| exact（四任务全对） | — | **0.148** | — | — |

- 延迟：**P50 1.63 s / P95 4.17 s / mean 1.94 s / max 11.1 s**（网关路由较旧直连 P50 0.87 s 增加约 0.8 s）。

## 三、与 91 窗旧约定数字对照（tab:main 云-Jev 行更新依据）

| 指标 | 旧 91 窗（4-opt 旧约定） | 新 439 窗（v3 统一约定） | 偏差 |
|---|---|---|---|
| tactic acc | 0.978 | 0.636 | **−0.342** |
| urgent acc | 0.978 | 0.843 | −0.135 |
| severity acc | 0.934 | 0.670 | −0.264 |
| action acc | 0.989 | 0.260 | **−0.729** |
| exact | 0.912 | 0.148 | **−0.764** |
| ECE(tactic) | 0.043 | 0.284 | +0.241 |
| P50 延迟 | 0.87 s | 1.63 s | +0.76 s（网关） |

## 四、偏差清单（逐项归因）

1. **action −0.729（最大项）**：旧约定 4 选项 → v3 统一 8 选项（新增 isolate_host/reset_credentials/quarantine_message/escalate），云 Jev 在新选项集上的分布几乎不迁移；e3b 子集 action acc=0。
2. **tactic −0.342**：4 类 → 11 类。逐源看：ssh 0.898 / ssh-e3b 1.0 / normal 0.739 / range 0.711，但 **dvwa(70 窗) 与 web(2 窗) tactic acc=0.0**——这些窗口标签落在 execution/persistence/defense_evasion 等新类，模型从不预测这些类。
3. **severity −0.264**：高档系统性低估——high 0.03 / critical 0.00（模型几乎只输出 low/medium），但有序性尚可（QKappa 0.886）。
4. **urgent −0.135**：主要由 e3b spray/stuffing 反退化子集拖累（0.379，其余源 urgent≈1.0）——旧 91 窗无该源。
5. **exact −0.764**：action/severity 双塌方的复合效应。
6. **ECE 0.043→0.284**：11 类下 tactic 概率显著过自信（11 选项下概率分散但 argmax 置信仍高）。
7. 结论：全线下降主因是**任务定义扩容（4→11/8 选项）与新增更难源（dvwa/web/e3b）**，而非 API 通路退化（响应结构/概率完整、0 错误）；论文 tab:main 云-Jev 行应改用本轮 439 窗数字并去掉"91 窗跨约定"脚注。

## 五、红线遵守

只写 `EVAL/CLOUD-JEV-439/`（新增 5 个文件，REPORT.md 为追加）；未改既有产物/代码；未 push；未用 GPU；key 未落任何产物。

## 追加：dev 55 窗补跑（主会话执行，2026-11-20）

- 同 runner（run_cloud_jev_dev.py，SUITE 换 development.jsonl），55/55 窗 0 错，model 全 jev-1.13.0
- dev：tactic 0.582 / urgent 0.800 / severity 0.582 / action 0.309 / exact 0.145 / ECE(tactic) 0.338 / P50 1.53s
- 产物：predictions_dev.jsonl + analysis_cloud-jev_dev.{json,md}（evaluate.py 同口径）
- 论文 tab:main D 行已更新为同约定双卷数字；91 窗旧约定数字（0.978/0.912/0.043）移入表脚注作参照
