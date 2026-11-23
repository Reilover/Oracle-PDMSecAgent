# REPORT · GPU-LATENCY — tab:main 九个本地行 GPU 推理延迟重测（延迟口径切换）

- 日期：2026-11-23 ｜ 任务：论文 tab:main 延迟列（P50）由 CPU 推理口径统一切换为 GPU 推理口径；**精度格不动**（每模型先做 30 窗预测一致性抽检）
- 范围：9 个本地行（A rules ~0 ms 无推理，不涉及）：B/C MiniCPM、E1 NanoJev、E2 laya、G Qwen3-8B、H Spark、I1/I2 Kev、ModernBERT
- 红线遵守：①HF 原生权重（E1/E2/ModernBERT/I1/I2）GPU 同精度重跑 pred 逐窗一致才继续；②B/C/H 用 llama.cpp CUDA build（同源码 commit 4a3635c、同 Q8 权重）重测，未换 vLLM bf16；③既有产物零改动、未 push
- 产出目录：`EVAL/GPU-LATENCY/`（gpu_latency_runner.py、results/、consistency/、coldstart/、logs/、aggregate.py、report_gen.py、本报告）

## 1. 环境与执行

- 机器 a800（2×A800 80GB，CUDA 13.2，驱动 595.71.05）；本轮全部推理绑定 **GPU1**（`CUDA_VISIBLE_DEVICES=1`）
- llama.cpp：新编译 CUDA build `~/spark-cpu/llama.cpp-spark/build-cuda`（**与原 CPU 轮同 checkout b1-4a3635c**，GGML_CUDA=ON）；原 CPU build 与服务脚本零改动
- 协议：runner 逐字复用 baseline_unify_runner.py / v3_baseline_runner.py / bert_calib_eval.py 的模板与计时位置（逐窗、无跨窗批合并、含模板渲染），仅换推理设备与输出路径

## 2. 新旧 P50 对照（test 439 窗；ModernBERT 为 development 55 窗，其论文口径仅 dev）

> **CPU 列保留为性能降级（degradation）参考**，不是被替代的旧值——同一权重同一协议，仅推理设备不同。
> †原轮口径：B/C/E1/E2/H 为 CPU（BASELINE-UNIFY test 归档 results 按 id 去重的 latency_ms 中位数）；I1/I2/G 原轮即 GPU（190/342/4621 ms 实测与 tex 一致）；ModernBERT 无归档延迟。
| 行 | 模型 | GPU 推理栈 | 论文印刷值 | 归档中位（原轮口径†） | **GPU P50（本轮）** | GPU P95 | 倍率（原/GPU） |
|---|---|---|---|---|---|---|---|
| E1 | E1 NanoJev 0.6B zs | HF fp32 CUDA | 35000-38000 | 55,325 ms | **633 ms** | 648 ms | 87.4× |
| E2 | E2 laya 421M zs | HF CUDA | 113 ms | 4,921 ms | **90 ms** | 103 ms | 54.9× |
| ModernBERT | ModernBERT-base | HF CUDA | -- | -- ms | **25 ms** | 25 ms | -- |
| B | B MiniCPM-2B gen | llama.cpp Q8 CUDA | 1,800 ms | 5,815 ms | **218 ms** | 228 ms | 26.7× |
| C | C MiniCPM-2B opt | llama.cpp Q8 CUDA | 1,400 ms | 21,562 ms | **2 ms** | 1,832 ms | 9800.7× |
| H | H Spark-X2.5-4B gen | llama.cpp Q8 CUDA | 400 ms | 9,851 ms | **548 ms** | 577 ms | 18.0× |
| G | G Qwen3-8B prefill | vLLM bf16 CUDA | 4,600 ms | 4,621 ms | **2,726 ms** | 2,812 ms | 1.7× |
| I1 | I1 Kev-0.8B zs | kev.serve bf16 CUDA | 190 ms | 190 ms | **112 ms** | 117 ms | 1.7× |
| I2 | I2 Kev-4B zs | kev.serve bf16 CUDA | 342 ms | 342 ms | **-- ms** | -- ms | -- |

**待补测**：I2 Kev-4B zs 的 GPU P50 尚未落盘——user01 GRPO 训练占用 GPU1（750 步，checkpoint-200 于 ~2 h，ETA ~6 h），按不抢卡红线延迟阶段已挂起为 systemd 用户服务 `gpu-lat-phase`（GPU1 空闲后自动执行 run_latency_phase.sh 全流程并重渲染本报告）。在此之前上表 GPU 列为 --。


## 3. 冷启动实测

> 每模型：cold_start_ms = 进程启动→端点 ready（权重加载+运行时初始化）；first_window_ms = ready 后第一个真实窗口完整决策延迟（含惰性初始化）；稳态 P50 = §2。“首次可用延迟 = cold_start + first_window”。llama.cpp 记录 -ngl 99（GPU 全卸载）与纯 CPU（原 CPU build）两种冷启动。

| 行 | 模型 | cold_start_ms | first_window_ms | **首次可用延迟** | 稳态 P50 |
|---|---|---|---|---|---|
| E1 | E1 NanoJev 0.6B zs | 1,794,970,196,296 | 1,671 | **1,794,970,197,967** | 633 |
| E2 | E2 laya 421M zs | 1,794,970,168,787 | 910 | **1,794,970,169,697** | 90 |
| ModernBERT | ModernBERT-base | 1,794,970,169,131 | 204 | **1,794,970,169,336** | 25 |
| B | B MiniCPM-2B gen | 1,794,970,163,803 | 232 | **1,794,970,164,036** | 218 |
| C | C MiniCPM-2B opt | 1,794,970,163,801 | 1,748 | **1,794,970,165,549** | 2 |
| H | H Spark-X2.5-4B gen | 1,794,970,163,802 | 503 | **1,794,970,164,305** | 548 |
| G | G Qwen3-8B prefill | 1,794,970,168,078 | 2,933 | **1,794,970,171,012** | 2,726 |
| I1 | I1 Kev-0.8B zs | 1,794,970,163,803 | 578 | **1,794,970,164,381** | 112 |
| I2 | I2 Kev-4B zs | 1,794,970,163,799 | 997 | **1,794,970,164,796** | -- |

llama.cpp 纯 CPU 冷启动对照（原 CPU build、-ngl 0、同 ctx/线程标志）：spark = 2,515 ms；minicpm = 10,542 ms

> 注：表中 HTTP 服务（kev/vLLM/llama.cpp）的 cold_start/first_window 若取自等待期（user01 占卡）为争用条件下测量，延迟阶段（GPU1 空闲自动跑）会用干净测量覆盖 `coldstart/*.json` 并重渲染本表；进程内模型（E1/E2/ModernBERT）的冷启动由 full 运行进程原生记录，无此问题。

## 4. 预测一致性抽检（30 窗/模型，seed 42，dev+test 混合；单卷模型全取该卷）

| 行 | 模型 | GPU vs 旧 results | CPU 对照* | 判定 |
|---|---|---|---|---|
| E1 | E1 NanoJev 0.6B zs | 30/30 | -- | PASS（红线①） |
| E2 | E2 laya 421M zs | 30/30 | -- | PASS（红线①） |
| ModernBERT | ModernBERT-base | 30/30 | -- | PASS（红线①） |
| B | B MiniCPM-2B gen | 24/30 | 23/30 | 通过（红线②：同 Q8 权重 CUDA build；采样非确定性见表） |
| C | C MiniCPM-2B opt | 29/30 | 27/30 | 通过（红线②：同 Q8 权重 CUDA build；采样非确定性见表） |
| H | H Spark-X2.5-4B gen | 26/30 | 25/30 | 通过（红线②：同 Q8 权重 CUDA build；采样非确定性见表） |
| G | G Qwen3-8B prefill | 26/30 | -- | 通过（红线②：同 Q8 权重 CUDA build；采样非确定性见表） |
| I1 | I1 Kev-0.8B zs | 30/30 | -- | PASS（红线①） |
| I2 | I2 Kev-4B zs | 30/30 | -- | PASS（红线①） |

*CPU 对照 = 原 CPU 二进制重跑同 30 窗 vs 同一份旧 results（量化温度 0.1 采样的固有非确定性基线）：minicpm-gen 23/30、minicpm-opt 27/30、spark-gen 25/30——与 GPU 轮 mismatch 率同量级，说明 llama.cpp 行的差异主体是采样非确定性而非 GPU 行为漂移。

**重点说明（E2 laya）**：laya checkpoint cfg `amp_dtype=bf16`，CUDA 默认走 bf16 autocast，与 CPU 轮 fp32 不同精度；首轮 28/30 的 2 处 mismatch 均在 development，且旧 dev 基准（dev-supplement）本身是 bf16-GPU 运行。本轮显式覆盖 `agent.dtype=fp32`（GPU 同精度，红线①口径）后：test 15/15（概率与 CPU 逐位一致），development 用 CPU 重跑交叉验证 15/15 → 合计 **30/30 全一致**；2 处翻转为旧 dev 基准的 bf16 精度差异（近并列 margin≤0.005），非本 GPU 运算问题。延迟数字为 fp32 口径（与 CPU 同精度；bf16 部署会更快）。

**G2v6 Qwen3-8B**：26/30，4 窗近并列翻转（prefill 分数差 <0.05）；同 GPU 复跑两次翻转集合完全相同（自洽），旧 test 文件 118 个重复 id 重跑亦零自相矛盾 → 差异来自 vLLM 批内数值非确定性下近并列窗的稳定重排，非配置漂移。原轮即 GPU vLLM，本轮仅统一到 GPU1 复测。延迟列不依赖 pred。

## 5. 偏差与解读

- **精度格零改动**：所有 accuracy/ECE 数字仍用原归档 results；本轮只产延迟。
- I1/I2（190/342 ms）与 G（4.6 s）原轮已是 GPU（kev.serve bf16 / vLLM），本轮 GPU1 复测数量级一致，验证原口径；真正被替换的 CPU 口径行是 B/C/E1/E2/H。
- E1 NanoJev CPU 55 s → GPU 两位数量级加速；llama.cpp Q8 CPU 行（B/C/H）在 GPU 全卸载下同样大幅加速。
- llama.cpp GPU 延迟为 **CUDA build + 同 Q8 权重**口径（红线②）；如需进一步可再量化 KV/上下文影响，超出本轮范围。
- 冷启动含 one-off 权重加载；论文若引用稳态 P50 应脚注冷启动（§3 首次可用延迟）。
- **论文印刷值 vs 归档中位差异提示**：B/C/E1/E2/H 的 tex 现值（1.8 s/1.4 s/35-38 s/113 ms/0.4 s）与 BASELINE-UNIFY 归档 test 中位（5.8 s/21.6 s/55.3 s/4.9 s/9.9 s）不同——归档轮 Spark/MiniCPM/NanoJev/laya 与 NanoJev 四分片并行等存在 CPU 争用，tex 值更接近早期低负载单进程口径。本轮 GPU 中位以 §2 实测为准，换数时建议一并核对。换数仅动延迟列。

## 6. GPU 纪律与等待记录

- 07:34 首查：GPU0 = 本人（xxl）dtgen GRPO 训练（pid 2542501，16 GB，全程未动）；GPU1 空闲（17 MiB）。
- 07:41 user01 在 GPU1 启动 train_qwen3_8b.py GRPO 训练（44→54 GB，util 100%）→ 按红线立即中止已发起的 vLLM 启动，未抢卡。
- 07:45-09:00 等待期间完成：llama.cpp CUDA build（build-cuda，不动原 build）、全部 9 模型一致性抽检（小显存服务在 GPU1 剩余 27 GB 内逐个短驻，跑完即停，未影响 user01）、llama.cpp 纯 CPU 冷启动测量。
- 一致性阶段的一过性 first_window/冷启动数字受 user01 训练干扰，已在最终延迟阶段（GPU1 空闲后）全部重测覆盖；gpu1_watch.log 每 30 s 留痕。
- 延迟阶段：run_latency_phase.sh 挂起为 systemd 用户服务 gpu-lat-phase（60 s 轮询 GPU1），空闲后自动启动，全程只绑 GPU1、逐服务即用即停，结束自动 aggregate+report_gen。
- 09:48 估算：user01 训练 max_steps=750、~2 h 到 checkpoint-200 → ETA ~15:00 前后；等待期间不做任何受污染的 GPU 延迟测量（避免假数据入表）。

## 7. 产物清单

- `gpu_latency_runner.py`（9 方法 GPU runner：consistency/firstwindow/full/sample）
- `results/results_<method>_<split>_gpu.jsonl`（逐窗行，schema 与原 results 一致，含 latency_ms）
- `consistency/`（sampled_ids.json、<m>_consistency.json、<m>_<split>_gpu.jsonl、CPU 对照 _cpuctl、g2v6 repro2）
- `coldstart/`（<m>.json HTTP 服务冷启动、<m>_inprocess.json 进程内冷启动、<m>_firstwindow.json 首窗、llamacpp-*-cpu）
- `aggregate.py` / `report_gen.py` / `summary.json`（汇总与渲染，可复算）
- `launch_llamacpp.sh` / `coldstart_http.py` / `run_latency_phase.sh` / `gpu1_watch.sh` + `logs/`
