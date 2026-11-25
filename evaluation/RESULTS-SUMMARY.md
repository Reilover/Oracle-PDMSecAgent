# ORACLE 实验结果总汇总（RESULTS-SUMMARY）

> 本文件由 `generate_results_summary.py` 从实验产物**直接计算生成**（不读论文取数；论文仅用于对账）。
> 约定：dev=oracle-v3 55 窗 / test=439 窗，11 选项同约定同 runner；本地行 bf16 GPU 确定性解码（云行 temp0）。
> 生成时间：2026-11-25 19:15；产物根：`~/MySecAgent/lab/experiments/oracle/`（GitHub 匿名仓 `evaluation/` 同步）。

## 1. 主表数值（产物直算）

| 行 | tactic dev/test | urgent | severity | action | exact | ECE | P50 |
|---|---|---|---|---|---|---|---|
| A rules | .400/.446 | .527/.649 | .236/.205 | .255/.235 | .200/.194 | -- | ~0\,ms（规则层） |
| B MiniCPM-gen | .091/.132 | .509/.547 | .400/.405 | .091/.125 | .036/.052 | -- | 269\,ms |
| C MiniCPM-opt | .673/.677 | .236/.230 | .691/.656 | .164/.107 | .000/.000 | .296/.149 | 1.14\,s |
| D Jev 1.13 (cloud) | .582/.636 | .800/.843 | .582/.670 | .309/.260 | .145/.148 | .338/.284 | 1.63\,s |
| E1 NanoJev-zs | .182/.137 | .236/.230 | .145/.107 | .000/.000 | .000/.000 | .238/.117 | 138\,ms |
| E2 laya-zs | .055/.025 | .709/.690 | .636/.631 | .582/.592 | .055/.009 | .460/.508 | 25\,ms |
| F1 GLM-5.3 | .582/.638 | .855/.854 | .727/.695 | .200/.134 | .055/.034 | -- | 1.70\,s |
| F2 DeepSeek-chat | .655/.697 | .764/.804 | .691/.743 | .236/.205 | .145/.141 | -- | 775\,ms |
| G Qwen3-8B | .291/.403 | .800/.815 | .455/.458 | .273/.262 | .182/.130 | .244/.102 | 2.73\,s |
| H Spark-gen | .000/.007 | .327/.321 | .273/.150 | .182/.089 | .000/.002 | -- | 363\,ms |
| I1 kev08-zs | .309/.282 | .764/.761 | .200/.178 | .127/.132 | .018/.002 | .193/.119 | 112\,ms |
| I2 kev4b-zs | .727/.761 | .800/.831 | .345/.410 | .691/.636 | .200/.194 | .321/.237 | 172\,ms |
| MB ModernBERT | .691/.681 | .782/.781 | .691/.690 | .673/.688 | .673/.681 | .281/.264 | 14\,ms |
| V Verdict-151M | .000/.000 | .164/.148 | .655/.661 | .164/.148 | .000/.000 | --/.342 | 263\,ms |
| O1 ORACLE Kev-4B | .782/.850 | .782/.822 | .673/.724 | .691/.754 | .582/.629 | .189/.122 | 173\,ms |
| O2 ORACLE Kev-0.8B | .727/.763 | .764/.779 | .709/.729 | .691/.677 | .618/.595 | .228/.213 | 114\,ms |
| O3 ORACLE laya | .655/.724 | .764/.770 | .545/.645 | .709/.740 | .455/.522 | .236/.091 | 25\,ms |
| O4 ORACLE NanoJev | .673/.670 | .782/.770 | .673/.640 | .600/.590 | --/.567 | --/.125 | 151\,ms |

## 2. 关键 gate 与噪声底座（产物直读）

- **E1/E2 复现 gate**：E1 test 逐格 Δ=0.0000；E2 test maxΔ=0.0046、dev 全 0（UNIFORM-BF16 REPORT §3）
- **噪声底座**：本地 bf16/greedy 重跑 100% 逐窗一致；云 temp0 一致率 GLM 63%/DSK 78%（CONFIG-SENSITIVITY 因素0）
- **bf16↔fp32**：MB 439/439 位同；kev |Δ|≤0.009；NanoJev 翻转 14/439（因素2）
- **MB 温度阶段 bf16（D9）**：NLL 1.466→1.004、tempered tactic ECE 0.276（bert-bf16-test gate.json: |Δ|≤0.0008）
- **vLLM 冷启动精测（D10）**：MiniCPM 72.3s / Spark 52.2s（2s 粒度），首请求 0.47–0.77s
- **I2 dev 55 窗补测**：0.727/.800/.345/.691/.200、ECE .321（analysis_kev4b-zs_dev_v3.json）

## 3. 历史口径修正审计链（叙事，非数据）

1. NanoJev dev exact ".455" 无据 → "--"；2. laya test 470 窗旧列 → 同约定值；3. dev 列 59 窗残值三处（E1/I1/I2）→ 55 窗值；4. G 行 test ECE .118(470 窗) → .103；5. 正文 DeepSeek 0.552 早期残值清除；6. 摘要 72ms→25ms、引言 72–195→25–173+1.1s；7. ORACLE 4B 延迟三处三数→173ms、0.8B 120 旧值→114ms；8. 表内 ECE 单值口径混杂→统一 dev/test；9. syscmp 两点陈旧值修正；10. V dev 0.025 无据→补跑实为 0.000、dev 四格补全（ECE .342）；11. §6.3 重层 ECE 标签装反（raw .149/withT .180）；12. A2b 重放 470 窗旧口径→439 窗重跑（gate 439/439 pred 全等）；13. D 行 test 产物从镜像拷回主树、生成器改 json 现算；14. MB test 补跑（消‡，与 D9 交叉验证一致，exact .681 列最优）+O 行 ECE 换 dev/test 对（消∥，等频 15bin 现算）。

## 4. 延迟阶梯（产物直算 P50）

rules ~0.1ms < laya-ORACLE 25ms ≈ laya-zs 25ms < MB 14ms(dev/test) < kev08-zs 112ms ≈ ORACLE-0.8B 114ms < NanoJev-zs 138ms < ORACLE-NanoJev 151.4ms < kev4b-zs 172.5ms ≈ ORACLE-4B 173.2ms < C-opt ~1.14s < D-Jev 1.6s < F1-GLM 1.7s < G-Qwen 2.7s；云：DSK 775ms < GLM 1697ms。CPU 降级：NanoJev ~55s、laya 4.9s、LLM 行 Q8 5.8–21.6s、MB 273ms。冷启动：kev/进程内 7–10s；vLLM 精测 52.2/72.3s；llama.cpp 备胎 1.5–2.1s。

## 5. 溯源目录索引

| 内容 | 目录 |
|---|---|
| 统一重测九行+gate | EVAL/UNIFORM-BF16/ |
| 敏感性因素 0–8 | EVAL/CONFIG-SENSITIVITY/ |
| MB 温度阶段 bf16（D9） | EVAL/BERT-CALIB/bert-bf16-test/ |
| vLLM 冷启动精测（D10） | EVAL/GPU-LATENCY/coldstart/vllm-coldstart-precise.json |
| kev4b-zs dev 补测 | EVAL/V3-TEST-BASELINE/（analysis_kev4b-zs_dev_v3.*） |
| ORACLE 三线 P50 | EVAL/GPU-LATENCY/coldstart/oracle_p50.json |
| MB test 补跑（消‡，2026-11-25） | EVAL/UNIFORM-BF16/results_mb-bf16_test.jsonl |
| A2b-v3 门控重放重跑（439 窗） | EVAL/ABLATION/a2b-v3/ |
| 云 Jev 439 窗补测（D 行） | EVAL/CLOUD-JEV-439/ |
| Verdict dev 55 窗补测 | EVAL/UNIFORM-BF16/results_verdict_v-dev_development.jsonl |
| 论文一致性总闸 | EVAL/check_paper_consistency.py（209 格+13 列+30 图点+49 绊线） |

> 更新纪律：任何补测/换数后重跑 `generate_results_summary.py` 再生成本文件，commit 注明。
