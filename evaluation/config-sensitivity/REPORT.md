# 计划B：配置差异敏感性矩阵 REPORT（CONFIG-SENSITIVITY）

> 生成：2026-11-24T00:37:08；方案：docs/02-执行交接/表2配置统一补测方案.md v3.1 B.1/B.2；对照产物：EVAL/UNIFORM-BF16（计划A Ⓐ）与既有归档。卷：test 439（除 MB dev 55）；解码：greedy/argmax。

指标：acc Δ（新−旧或 B−A 方向随格注明）、ECE Δ（仅概率输出行）、P50 ratio；每格注 n 与产物路径。

## 因素 0 · 噪声底座（同配置重跑×2，先读此行再读其余）

| 系统 | 口径 | n | 逐窗一致率(all4) | tactic/urgent/sev/action | 产物 |
|---|---|---|---|---|---|
| MiniCPM llama.cpp-Q8-GPU greedy | 重跑×2 | 30 | 100.00% | 100.00%/100.00%/100.00%/100.00% | results_b-q8-greedy_r1_test.jsonl, results_b-q8-greedy_r2_test.jsonl |
| Spark llama.cpp-Q8-GPU greedy | 重跑×2 | 30 | 100.00% | 100.00%/100.00%/100.00%/100.00% | results_h-q8-greedy_r1_test.jsonl, results_h-q8-greedy_r2_test.jsonl |
| kev-0.8B bf16 (kev.serve) | 重跑×2 | 30 | 100.00% | 100.00%/100.00%/100.00%/100.00% | results_kev08_r1_test.jsonl, results_kev08_r2_test.jsonl |
| GLM temp0 云 | 重跑×2 | 439 | 63.33% | 76.99%/92.26%/79.73%/93.62% | results_f1-glm_test.jsonl, results_f1-glm_r2_test.jsonl |
| DeepSeek temp0 云 | 重跑×2 | 439 | 78.13% | 88.15%/94.53%/89.75%/91.34% | results_f2-dsk_test.jsonl, results_f2-dsk_r2_test.jsonl |
| Qwen3-8B vLLM bf16（G 行复用） | 同服务重跑 | 30 | 86.67% | mismatch 含近并列 tactic 翻转 | /disk1/models/datacollect/xxl-data/projects/MySecAgent/lab/experiments/oracle/EVAL/GPU-LATENCY/consistency/g2v6-qwen_consistency_repro2.json |

声明（◊ argmax 确定性，不实测）：laya/NanoJev/MB/Verdict 为 argmax 头，同权重同精度重跑逐位一致（NanoJev 30/30、laya bf16 autocast 确定性已有验证；GPU-LATENCY consistency 归档）。

## 因素 1 · Q8 量化 vs bf16（同 GPU 同 greedy：llama.cpp-Q8-GPU-greedy vs vLLM-bf16-greedy）

| 系统 | n | Δacc tactic | Δurgent | Δsev | Δaction | invalid率 Q8→bf16 | P50 Q8→bf16 (ratio) |
|---|---|---|---|---|---|---|---|
| MiniCPM(B) | 439 | -0.0023 | -0.1959 | -0.1367 | -0.0068 | 0.0%→0.0% | 216→269ms (1.25×) |
| Spark(H) | 439 | +0.0023 | +0.0091 | +0.0046 | -0.0046 | 0.0%→0.0% | 553→363ms (0.66×) |
| MiniCPM(C 协议混叠*) | 439 | -0.0046 | +0.0000 | -0.0251 | +0.0000 | 0.0%→0.0% | 374→1145ms (3.06×) |

*C 行对：Q8-greedy 单采样计数 vs bf16 prefill-logprobs，含协议差异（因素 6）与框架差异（因素 7），仅作参考非纯量化项。

## 因素 2 · bf16 vs fp32（同 GPU）

| 系统 | n | Δacc tactic | Δurgent | Δsev | Δaction | ΔECE tactic | P50 fp32→bf16 (ratio) | 产物 |
|---|---|---|---|---|---|---|---|---|
| kev-0.8B | 439 | -0.0091 | +0.0000 | +0.0000 | -0.0023 | 0.0136 | 128(fp32)→112ms(bf16, idle 复测) | results_kev08_fp32_test.jsonl vs V3 results_kev08-zs_test |
| ModernBERT (dev) | 55 | +0.0000 | (urgent 0.7818) | 0.6909 | 0.6727 | fp32 0.2629 → bf16 0.2807 | 25ms(fp32 GPU)→14ms | results_mb-bf16_development.jsonl vs BERT-CALIB dev_sanity |
| NanoJev (GPU 内对照) | 439 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | — | 633→138ms (0.22×) | bf16: UNIFORM vs fp32: results_e1-nanojev-fp32_test.jsonl；翻转窗 14/439 |
| laya-421M（引用Ⓐ：旧 CPU-fp32 vs 新 GPU-bf16） | 439 | +0.0046 | +0.0000 | +0.0023 | +0.0000 | — | 90ms(fp32)→24.7ms(bf16) 3.6× | UNIFORM REPORT §2 |

## 因素 3 · CPU vs GPU（同精度；P50 ratio = CPU/GPU）

| 系统 | 精度 | CPU P50 | GPU P50 | ratio | acc Δ(GPU−CPU) |
|---|---|---|---|---|---|
| E1 NanoJev | fp32 | 55336ms | 633ms | 87.4× | tactic +0.0000（成对纯净） |
| B MiniCPM-gen (Q8, greedy CPU-值 vs GPU greedy) | Q8 | 5815ms | 216ms | 26.9× | （精度对照见因素 1/5，延迟为主） |
| H Spark-gen (Q8, 同上) | Q8 | 9851ms | 553ms | 17.8× | （精度对照见因素 1/5，延迟为主） |
| C MiniCPM-opt (Q8, 5采样 CPU vs GPU) | Q8 | 21562ms | 1726ms | 12.5× | （精度对照见因素 1/5，延迟为主） |
| MB ModernBERT (dev) | fp32 CPU vs fp32 GPU | 273ms | 25ms | 10.9× | — |
| E2 laya（引用：fp32 CPU 4,921ms vs fp32 GPU 90ms） | fp32 | 4921ms | 90ms | 54.7× | 2/439 翻转（引用） |

## 因素 4 · 共卡 vs 独占 GPU（仅录入，kev-4B）

kev-4B 与 8B vLLM 共卡时 systemone 2.3s vs idle 173ms（13×，史值引用：GPU-LATENCY REPORT / 运维记录）。其余系统未测（—）。

## 因素 5 · 温度采样 0.1 vs greedy

| 系统 | 对照 | n | Δacc tactic | Δurgent | Δsev | Δaction | invalid 率 |
|---|---|---|---|---|---|---|---|
| C MiniCPM（纯对照：同 Q8 同 GPU 同 llama.cpp，temp0 vs temp0.1×5） | 439 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | n/a（选项协议） |
| B（Ⓐ greedy-bf16-GPU vs 旧 temp0.1-Q8-CPU，含量化/硬件） | n=439 | +0.0023 | -0.1913 | -0.1390 | -0.0159 | 0.0%(greedy) |
| H（同上） | n=439 | +0.0000 | -0.0023 | -0.0046 | -0.0114 | 0.0%(greedy) |
| F1 GLM（temp0 vs temp0.1，同云） | n=439 | -0.0410 | +0.0091 | -0.0114 | -0.0023 | 0.0%(greedy) |
| F2 DSK（同上） | n=439 | +0.1162 | +0.0068 | +0.1321 | -0.3121 | 0.0%(greedy) |

## 因素 6 · 5采样计数 vs logprobs（C 行协议）

- logprobs(bf16-vLLM) vs greedy单采样(Q8-llama)：Δacc tactic -0.0046 / urgent +0.0000 / sev -0.0251 / action +0.0000；ECE tactic 0.6765→0.1487（Δ-0.5278）；含框架差（llama.cpp vs vLLM），归因素 7 声明
- logprobs(bf16-vLLM) vs 5采样(Q8-llama)：Δacc tactic -0.0046 / urgent +0.0000 / sev -0.0251 / action +0.0000；ECE tactic 0.6697→0.1487（Δ-0.521）；含框架差（llama.cpp vs vLLM），归因素 7 声明

## 因素 7 · llama.cpp vs vLLM（同 bf16 同 greedy，test 439）

| Spark | 锚: Q8-llama | Δ(bf16-llama−Q8-llama) tactic +0.0023 | Δ(bf16-vLLM−Q8-llama) tactic +0.0023 | 框架残差(vLLM−llama, 同bf16): +0.0 |
| （P50: 572ms llama-bf16 vs 363ms vLLM-bf16） |
| MiniCPM | 无 bf16-gguf（未转换），框架差由 vLLM−Q8 与 llama−Q8 之差间接估计（B.1 备注） |

--jinja 与 vLLM chat-template 实现差异归入本因素，不单列。

## 因素 8 · 服务形态（进程内 vs localhost HTTP）

声明 ◊：llama.cpp/vLLM/kev 行本表即 HTTP 口径；laya HTTP 封装未实测（默认改声明，~2ms 量级预期，小于因素 0 噪声）；NanoJev/MB 进程内为同类口径声明。

## 待实测问题回答（预填假设 → 实测）

- 噪声底座：llama.cpp greedy 与 kev bf16 是否逐窗确定 → 见因素 0 表（all4 一致率）；vLLM 26/30 翻转，mismatch 样本含 tactic 近并列；
- Q8 对 typed 决策精度损失：见因素 1（假设 ≤0.03 的验证结果如上；塌缩行未翻身）；
- bf16/fp32 argmax 头 ≈0：kev/MB/NanoJev/laya 各自翻转数见因素 2；
- CPU/GPU 延迟比分布与共卡 13×：见因素 3/4；
- 采样 vs greedy 对 B/H/F1/F2：见因素 5（含 JSON 合法率变化）；
- C 行协议影响与服务形态：见因素 6/8。

## 论文用法

- 附录一表：因素 0-8 × {acc Δ, ECE Δ, P50 ratio}（本 REPORT §因素0-8 摘编）；
- §7（延迟/降级/共卡）引因素 3/4 各 1-2 句；§8（局限性：量化与非确定性）引因素 0/1 各 1-2 句。

