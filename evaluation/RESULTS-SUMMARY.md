# ORACLE 实验结果总汇总（RESULTS-SUMMARY）

> 2026-11-25 建。**唯一的结果汇总入口**：论文表 2/表 3/正文数字的当前值全部在此对账；后续任何补测/重测更新本文件。
> 约定：dev=oracle-v3 55 窗 development split，test=439 窗 oracle split，11 选项同约定、同 runner；本地行 bf16 GPU 确定性解码（云行 temp0）。
> 逐行溯源：`~/MySecAgent/lab/experiments/oracle/EVAL/`（镜像 GitHub 匿名仓 `evaluation/`）。

## 1. 表 2 主表当前值（2026-11-25 终态）

精度格 = dev / test（tactic 列分两格）；ECE 为 dev/test 对（或行内自洽单值）；P50 为 439 窗 idle GPU0 部署精度实测。

| 行 | tactic dev/test | urgent | severity | action | exact | ECE | P50 |
|---|---|---|---|---|---|---|---|
| A rules | 0.400 / 0.446 | .527/.649 | .236/.205 | .255/.235 | .200/.194 | -- | ~0ms |
| B MiniCPM-gen | 0.091 / 0.132 | .509/.547 | .400/.405 | .091/.125 | .036/.052 | -- | 269ms |
| C MiniCPM-opt | 0.673 / 0.677 | .236/.230 | .691/.656 | .164/.107 | .000/.000 | .297/.149 | 1.14s |
| D Jev 1.13 云 | 0.582 / 0.636 | .800/.843 | .582/.670 | .309/.260 | .145/.148 | .338/.284 | 1.6s |
| E1 NanoJev-zs | 0.182 / 0.137 | .236/.230 | .145/.107 | .000/.000 | .000/.000 | .238/.117 | 138ms |
| E2 laya-zs | 0.055 / 0.025 | .709/.690 | .636/.631 | .582/.592 | .055/.009 | .460/.509 | 25ms |
| F1 GLM-5.3 | 0.582 / 0.638 | .855/.854 | .727/.695 | .200/.134 | .055/.034 | -- | 1.7s |
| F2 DeepSeek | 0.655 / 0.697 | .764/.804 | .691/.743 | .236/.205 | .145/.141 | -- | 0.8s |
| G Qwen3-8B | 0.291 / 0.403 | .800/.815 | .455/.458 | .273/.262 | .182/.130 | .244/.103 | 2.7s |
| H Spark-gen | 0.000 / 0.007 | .327/.321 | .273/.150 | .182/.089 | .000/.002 | -- | 363ms |
| I1 kev08-zs | 0.309 / 0.282 | .764/.761 | .200/.178 | .127/.132 | .018/.002 | .193/.119 | 112ms |
| I2 kev4b-zs | 0.727 / 0.761 | .800/.831 | .345/.410 | .691/.636 | .200/.194 | .321/.237 | 173ms |
| MB（仅dev） | 0.691 / -- | .782/-- | .691/-- | .673/-- | .673/-- | .281 | 14ms |
| V Verdict | 0.025 / 0.000 | --/.148 | --/.661 | --/.148 | --/.000 | 0.34 | 263ms |
| **O1 ORACLE-4B** | 0.782 / 0.850 | .782/.822 | .673/.724 | .691/.754 | .582/.629 | .140 | 173ms |
| **O2 ORACLE-0.8B** | 0.727 / 0.763 | .764/.779 | .709/.729 | .691/.677 | .618/.595 | .112 | 114ms |
| **O3 ORACLE-laya** | 0.655 / 0.724 | .764/.770 | .545/.645 | .709/.740 | .455/.522 | .123 | 25ms |
| **O4 ORACLE-NanoJev** | 0.673 / 0.670 | .782/.770 | .673/.640 | .600/.590 | --/.567 | -- | 154ms |
| 消融 w/o ord_w | -- / .832 | --/.810 | --/.714 | --/.718 | --/.597 | -- | -- |

冷启动：kev/进程内头 7–10s；**vLLM 端点精测 MiniCPM 72.3s / Spark 52.2s**（2s 粒度，首请求 0.47–0.77s）；llama.cpp 备胎 1.5–2.1s。

## 2. 关键 gate 与验证记录

- **E1/E2 复现 gate**（统一重测，UNIFORM-BF16）：E1 test 逐格 Δ=0.0000；E2 test maxΔ=0.0046、dev 全 0 —— PASS
- **噪声底座**（CONFIG-SENSITIVITY 因素0）：本地 bf16/greedy 重跑 100% 逐窗一致；云 temp0 一致率 GLM 63%/DSK 78%
- **bf16↔fp32**：argmax 头 Δ=0（MB 439/439 位同；kev Δ≤0.009；NanoJev 翻转 14/439）
- **MB 温度阶段 bf16 复测**（bert-bf16-test，D9）：NLL 1.466→1.004，tempered tactic ECE 0.276（与 fp32 差 ≤0.0008）
- **I2 dev 55 窗补测**（2026-11-25）：替换 59 窗早期残值（0.746/.814/.424/.627/.190/.278 → 0.727/.800/.345/.691/.200/.321）

## 3. 已修正的历史口径事故（审计链）

1. NanoJev dev exact ".455" 无产物依据 → "--"
2. laya test 早期 470 窗列 → 同约定值（0.724/.770/.645/.740/.522）
3. dev 列 59 窗早期残值三处：E1（0.103→0.182）、I1（0.254→0.309）、I2（0.746→0.727，补测）
4. G 行 test ECE 早期 470 窗残值 .118 → .103
5. 正文两处 "DeepSeek exact 0.552" 早期 dev 残值 → 现口径
6. 摘要 72ms → 25ms；引言 72–195ms → 25–173ms + 全管线 P50 1.1s
7. ORACLE 4B 延迟三处三数 → 统一 173ms（441ae7b 直测）；0.8B 120 旧值 → 114ms（终版 json）
8. 表内 ECE 单值口径混杂（D=dev、I1=test）→ 统一 dev/test 对
9. syscmp 两点陈旧值（ORACLE laya 0.657/0.472、Kev-4B-zs 0.706）→ 修正

## 4. 延迟终表（P50，439 窗 idle GPU0 部署精度）

rules ~0.1ms < laya-ORACLE 25ms = laya-zs 25ms < MB 14ms(dev) ≈ NanoJev-zs 138ms < kev08-zs 112ms ≈ ORACLE-0.8B 114ms < ORACLE-NanoJev 154ms < kev4b-zs 173ms = ORACLE-4B 173ms < C-opt 1.14s < D-Jev 1.6s < F1-GLM 1.7s < G-Qwen 2.7s；云：DSK 775ms < GLM 1697ms。CPU 降级：NanoJev ~55s、laya 4.9s、LLM 行 Q8 5.8–21.6s、MB 273ms。

## 5. 溯源目录索引

| 内容 | 目录 |
|---|---|
| 统一重测（B/C/E1/E2/F1/F2/H/MB/V）+ gate | EVAL/UNIFORM-BF16/ |
| 配置敏感性因素 0–8 | EVAL/CONFIG-SENSITIVITY/ |
| MB 温度阶段 bf16（D9） | EVAL/BERT-CALIB/bert-bf16-test/ |
| vLLM 冷启动精测（D10） | EVAL/GPU-LATENCY/coldstart/vllm-coldstart-precise.json |
| kev4b-zs dev 55 窗补测 | EVAL/V3-TEST-BASELINE/（analysis_kev4b-zs_dev_v3.*） |
| ORACLE 三线 P50 | EVAL/GPU-LATENCY/coldstart/oracle_p50.json |
| 其余基线/主表产物 | EVAL/paper-results 各子目录（GitHub 同名） |

> 更新纪律：每次补测/换数后，第 1 节对应行与第 2/4 节同步更新，并在 git commit 中注明。
