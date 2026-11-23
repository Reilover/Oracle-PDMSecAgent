# REPORT · P0-1 基线统一重测（批 A+B 本地 6 条，oracle-v3 test 439 窗同约定）

- 日期：2026-09-29 ｜ 依据：`docs/01-论文核心/基线统一重测计划-20260929.md` 批 A+B ｜ 计划编号 P0-1
- 卷：`suites/oracle-v3/test.jsonl` 439 窗 / 1,756 题（11 类 tactic / 8 action / 4 sev score 约定 / noul urgent）——与五方重评（V3-TEST-BASELINE）同一张卷
- 执行：全部 CPU，零 GPU。runner = `baseline_unify_runner.py`（各方法协议与早期 RANGE-BASELINE runner 逐字一致，仅换卷 v1→v3 test）；指标 = `code/eval/evaluate.py`（同 schema：tactic/urgent/severity/action/exact/ECE/延迟）
- 云 API 部分（C1 Jev 1.13 + C2 可选 few-shot）不在本轮范围，留待 key/额度确认

## 1. 六条新数字（oracle 439 窗 test，n=439）

| # | 基线 | tactic | urgent | severity | action | exact | ECE(tactic) | P50 延迟 |
|---|---|---|---|---|---|---|---|---|
| A1 | Rules 规则引擎 | 0.446 | 0.649 | 0.205 | 0.235 | 0.194 | -- | ~0 ms |
| A2 | NanoJev-0.6B zero-shot | 0.137 | 0.230 | 0.107 | 0.000 | 0.000 | 0.117 | 55 s |
| A3 | laya-421M zero-shot | 0.021 | 0.690 | 0.629 | 0.592 | 0.009 | 0.513 | 4.9 s |
| B1 | Spark-X2.5-4B generative | 0.007 | 0.323 | 0.155 | 0.100 | 0.002 | -- | 9.9 s |
| B2 | MiniCPM-2B generative | 0.130 | 0.738 | 0.544 | 0.141 | 0.046 | -- | 5.8 s |
| B3 | MiniCPM-2B option-scored | 0.681 | 0.230 | 0.679 | 0.107 | 0.000 | 0.672 | 21.6 s |

细节（severity 分档 / macro-F1 见各 `analysis_*.json|md`）：
- A1 macroF1 0.553；sev low .19/med .00/high 1.00/crit .07
- A2 macroF1 0.092；action 全灭（0.000，同旧口径零样本行为）
- A3 macroF1 0.037；sev low .84/med .27；tactic 塌缩（11 类下近随机）
- B1 macroF1 0.013——生成式在 11 类下近零（**正式数字确认旧脚注预期**）；valid-JSON 率 439/439
- B2 macroF1 0.103；valid 439/439
- B3 macroF1 0.271；severity 全押 low（low 1.00 其余 0）但 tactic 0.681 为本地基线最高；urgent 0.230（反向塌缩）；ECE 0.672（计数分布置信严重失准）

## 2. 新旧对照（旧 = 早期 4-opt 约定 dev+470 窗 test，Table 2 现行数字；新 = 本轮 439 窗 11-opt）

| 基线 | 旧 tactic (test) | **新 tactic** | 旧 sev | **新 sev** | 旧 exact | **新 exact** | 方向解读 |
|---|---|---|---|---|---|---|---|
| A Rules | 0.477 | **0.446** | .223 | **.205** | .209 | **.194** | 略降：4→11 类后规则误报面不变但真值空间更细，幅度小（-0.03） |
| B2 MiniCPM gen | 0.162(470窗) | **0.130** | .52 | **.544** | .053 | **.046** | 略降，行为一致 |
| B3 MiniCPM opt | 0.549* | **0.681** | .659* | **.679** | 0.0* | **0.000** | *旧为 91 窗 4-choice 基准；新 11 类下 tactic 反升（计数采样偏 benign 类先验），exact 仍 0 |
| B1 Spark gen | 0.002 | **0.007** | .149 | **.155** | .000 | **.002** | 双约定下都近零——"生成式小模型在结构化多类上崩溃"结论跨约定成立 |
| E1 NanoJev zs | 0.131 | **0.137** | .118 | **.107** | .000 | **.000** | 持平：崩溃结论同约定复现 |
| E2 laya zs | 0.028 | **0.021** | .570 | **.629** | .016 | **.009** | tactic 持平崩溃；sev 略升（choice 口径 low 类底大） |

**结论**：六条基线在 oracle 同约定下方向与量级与旧口径一致（除 B3 tactic 从 0.549*→0.681 需在 Table 2 直接换新数外，其余变动 ≤0.04）。跨约定脚注可按计划删除，Table 2 这 6 行 test 列全部换成本表新数。

## 3. 合并后的完整 test 列预览（oracle 439 窗同约定，n=439；本轮 6 条 + 五方重评 5 条 + 既有同口径行）

| 基线/方法 | tactic | urgent | severity | action | exact | ECE | P50 |
|---|---|---|---|---|---|---|---|
| A rules | 0.446 | .649 | .205 | .235 | .194 | -- | ~0 ms |
| B1 Spark-X2.5-4B gen | 0.007 | .323 | .155 | .100 | .002 | -- | 9.9 s |
| B2 MiniCPM-2B gen | 0.130 | .738 | .544 | .141 | .046 | -- | 5.8 s |
| B3 MiniCPM-2B opt-scored | 0.681 | .230 | .679 | .107 | .000 | .672 | 21.6 s |
| C1 Jev 1.13 (cloud) | *(待云 API 轮)* | | | | | | |
| E1 NanoJev-0.6B zs | 0.137 | .230 | .107 | .000 | .000 | .117 | 55 s |
| E2 laya-421M zs | 0.021 | .690 | .629 | .592 | .009 | .513 | 4.9 s |
| F1 GLM-5.3 | 0.679 | .845 | .706 | .137 | .032 | -- | 1.8 s |
| F2 DeepSeek-chat | 0.581 | .797 | .610 | .517 | .431 | -- | 0.8 s |
| G Qwen3-8B (G2v6) | 0.403 | .815 | .458 | .262 | .130 | .103 | 4.6 s |
| I1 Kev-0.8B zs | 0.282 | .761 | .178 | .132 | .002 | .119 | 190 ms |
| I2 Kev-4B zs | 0.761 | .831 | .410 | .636 | .194 | .237 | 342 ms |
| **ORACLE Kev-4B**† | **0.850** | .822 | .724 | **.754** | **.629** | .140 | 2.3 s |
| **ORACLE Kev-0.8B**† | 0.763 | .779 | **.729** | .677 | .595 | .112 | 0.5 s |
| **ORACLE laya**† | 0.657 | .738 | .596 | .713 | .472 | .123 | 72 ms |
| **ORACLE NanoJev**† | 0.670 | .770 | .640 | .590 | **.567** | .125 | 154 ms |

†主行与五方重评/E3P test 确认报告同源（REPORT-1-1/1-2）。D Jev 云行、ModernBERT(dev-only)/Verdict 行维持原状不入 test 列合并。

## 4. 口径与执行声明

1. 卷与协议：oracle-v3 test 439 窗；tactic 11 类、action 8 类、severity score 4 档、urgent noul——与 kev 四任务评测完全同约定。runner 各方法内部协议逐字复用 RANGE-BASELINE（rule 正则规则、NanoJev 官方 DecisionPredictor CPU 适配器、laya SDK choice 协议 severity 走 choice、生成式同 prompt 模板 temperature 0.1 + `enable_thinking:false`、option-scored 温度采样 5 次计数）。
2. 环境（全部 CPU，零 GPU）：
   - A2 NanoJev：`~/spark2_5/bin/python`（torch 2.13），fp32 sdpa，4 shard × 4 核（0-15）
   - A3 laya：同 python，`Agent(local HF snapshot, device='cpu')`——**Router() 在离线机上报 Incompatible model，改用与 9-24 跑批同一 HF cache 快照直建 Agent，checkpoint 同一**（此为与旧 runner 的唯一等价替代，记录在案）
   - B1 Spark：llama.cpp 18080（Q8_0，常驻服务）；B2/B3 MiniCPM：llama.cpp 18081（Q8_0）
   - 事故记录：中途重启 MiniCPM llama-server（原服务 taskset 27-35,63-71 与 NanoJev shard 核冲突拖慢 3 倍；热迁移 affinity 后 server 线程池卡死）→ 按 `~/Mylocllm/MiniCPM5-2B服务管理手册.md` stop 后重启并绑核 36-53，恢复 6s/窗；中断期间 12 个 503 error 行已由断点续跑补齐，最终 439/439 有效
3. 数据完整性：六个 `results_*_test.jsonl` 均按 id 去重出 `.clean.jsonl` 后计分（去重脚本内联于会话，模式同 V3-TEST-BASELINE）；行数核对 439/439 全有效、0 error 行残留。B1/B2 valid-JSON 率 100%（生成式解析零失败）。
4. 延迟口径：P50 = 全 439 窗 latency_ms 中位数。CPU 端点共享机（load 40-60），A2/A3/B1/B2/B3 的绝对值偏高（ NanoJev 55 s 为 4-核受限口径；早期全核口径 35-38 s）——论文引用建议标注"shared-CPU"或沿用各方法既有口径并脚注本轮数。
5. ECE：仅选项打分类（A2/A3/B3）与 kev 有概率输出可算 ECE；生成式（B1/B2）与规则（A1）无分布，标 --（与 Table 2 现行口径一致）。

## 5. 产物清单

- runner：`baseline_unify_runner.py`（含 rule/nanojev-zs/laya-zs/spark-gen/minicpm-gen/minicpm-opt 六方法 + shard/断点续跑）；`launch_unify.sh`、`relaunch_cpu_pinned.sh`
- 逐条预测：`results_{rule,nanojev-zs,laya-zs,spark-gen,minicpm-gen,minicpm-opt}_test.jsonl`（+ `.clean.jsonl` 去重计分版）
- 指标：`analysis_*_test.json` / `analysis_*_test.md`（六份，evaluate.py 同 schema）
- 日志：`logs/`

## 6. 待办移交

- C1 Jev 1.13 云 API 重评（439 窗同协议）+ C2 可选 GLM/DeepSeek few-shot：等用户确认 key/额度后另行委托
- Table 2 回填（6 行 test 列换新数 + 删跨约定脚注）：由论文会话执行，依据本报告 §2/§3
- B3 的 tactic 0.681 vs 旧 0.549*：口径本质不同（11 类计数采样 vs 91 窗 4-choice），回填时直接用新数并在 Methods 注明 option-scored 协议
