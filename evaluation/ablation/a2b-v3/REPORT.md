# A2b-v3：去逐题类温度校准消融（laya-421M，439 窗 V3 test 口径重跑）

日期：2026-11-25 ｜ 任务：将 §6.3 的 laya 门控重放消融从 470 窗 early-suite 旧口径
（a2b/，2026-09-29，T4-LAYA/results_v3_test.jsonl）换到现行 439 窗 V3 test
（suites/oracle-v3/test.jsonl，与 O3 现役行同口径），协议不变。

## 产物

- `results_439.jsonl` — 439 窗逐题完整概率分布（choice 三题 tactic/severity/action 全
  probabilities 字典 + urgent noul 标量 + pred/label），由 `infer_probs.py` 新推理落盘
  （Agent(T4-LAYA/laya-oracle-v3, device='cuda')，SDK 直调，同 eval_ours_v3.py 协议）。
- `gate_check.json` — 校验 gate 结果（见下）。
- `recompute.py` → `result.json` — ECE/准确率双臂复算（协议与 a2b/recompute.py 逐行一致）。
- `recompute_gating.py` → `gating_share.json` — 门控回放双臂（协议与 a2b/recompute_gating.py 逐行一致）。

## 校验 gate（必过）

新推理 argmax 与 O3 现役 `EVAL/LAYA-FAMILY/zeroshot_ours_v3.jsonl` 逐窗 pred 全等：

- 439/439 窗 pred 全等（tactic/urgent/severity/action 四题，0 mismatch）
- tactic_acc 0.7244 / exact_acc 0.5216（预期 0.724/0.522）✅ **PASS**

## 协议（与 a2b/ 完全一致，仅换数据源）

- ckpt 内嵌温度 [4.843, 9.042, 9.223]（choice/score/noul），serve clamp [0.5,5]
  → choice 桶实际 T=4.843491554260254（未超上限；score/noul 被 clamp 至 5，与 choice 题无关）。
- 去校准臂 = p^4.843491554260254 归一化的幂变换（即 softmax(z/1)）。
- ECE 15 等宽分箱；choice 三题 = tactic/severity/action（urgent 无分布不参与）。
- 门控 τ=0.90 / τ_h=0.70，conf=max prob；任一题 escalate → 整窗升 Tier2。
- a2b 原版 `exact_acc` 定义 = severity ∧ action ∧ urgent（不含 tactic，代码原样保留），
  本版另补 `exact_acc_all4_suppl`（四题全对，对齐 O3 现役 exact 口径 0.5216）。

## 新结果（439 窗 V3 test）

准确率与 ECE（choice 三题，`result.json`）：

| 口径 | tactic | exact(a2b 协议) | exact(all4, 补充) | ECE | mean conf |
|---|---|---|---|---|---|
| w/ calibration (T=4.84) | 0.7244 | 0.5399 | 0.5216 | **0.110** | 0.778 |
| w/o calibration (T=1) | 0.7244 | 0.5399 | 0.5216 | 0.222 | 0.925 |

门控路径份额（τ=0.90/τ_h=0.70，`gating_share.json`）：

| 口径 | 题级 auto | 题级 confirm | 题级 escalate | 窗级升 Tier2 |
|---|---|---|---|---|
| w/ calibration | 0.217 | 0.543 | 0.240 | 0.476 |
| w/o calibration | **0.792** | 0.068 | 0.141 | 0.305 |

## 新旧对照（470 窗旧口径 vs 439 窗 V3 新口径，逐项）

| 指标 | 口径 | 旧（a2b/, 470 窗 early-suite） | 新（a2b-v3/, 439 窗 V3 test） | Δ |
|---|---|---|---|---|
| n_windows | — | 470 | 439 | −31 窗（口径更换） |
| n_questions（choice 三题） | — | 1410 | 1317 | — |
| tactic_acc | 两臂同 | 0.6574 | 0.7244 | +0.0670（V3 11-opt 同 O3 训练口径，模型更强） |
| exact_acc（a2b 协议） | 两臂同 | 0.4936 | 0.5399 | +0.0463 |
| ECE | w/ calib | 0.1491 | **0.1104** | −0.0387 |
| ECE | w/o calib | 0.2689 | **0.2221** | −0.0468 |
| ECE 恶化幅度（去校准） | — | +0.120 | +0.112 | 方向不变，幅度略收 |
| mean_conf | w/o calib | 0.9242 | **0.9252** | +0.0010（过信结论不变） |
| 题级 auto_share | w/ calib | 0.2248 | 0.2172 | −0.0076 |
| 题级 auto_share | w/o calib | 0.7943 | **0.7920** | −0.0023（虚假自动化带结论不变） |
| 题级 confirm_share | w/ → w/o | 0.5355 → 0.0603 | 0.5429 → 0.0676 | — |
| 题级 escalate_share | w/ → w/o | 0.2397 → 0.1454 | 0.2399 → 0.1405 | — |
| 窗级升 Tier2 | w/ calib | 0.4702 | 0.4761 | +0.0059 |
| 窗级升 Tier2 | w/o calib | 0.3085 | **0.3052** | −0.0033 |

**结论：§6.3 叙事方向全部保持，数字换新即可。** 去校准仍显著恶化 ECE
（0.110→0.222）且严重过信（conf 0.925）；题级 auto 0.217→0.792（虚假自动化带宽
+0.57）；窗级升级率反降 0.476→0.305——未校准轻层把大量错误答案以高置信放进自动带，
门控 + 校准组合立论不变。论文引用建议改为：ECE 0.110→0.222、conf 0.925、
auto share 0.217→0.792、窗级升级 0.476→0.305。

## 偏差清单

1. **GPU0 共享**：起服务前 nvidia-smi 显示 GPU0 已有 user02 的 llama2_7B 训练
   （17.5GB/80GB，100% util）。按任务书"若占则报告"处置：显存余量充足（laya-421M
   推理 <2GB），实际推理 439 窗仅 20s 完成，无冲突。
2. **laya 包路径**：任务书写 sys.path /home/xxl/Mylocllm，但该目录下无 laya 包
   （仅有 laya-family ckpts）。实际生效包路径 /home/xxl/laya（与原 eval_ours_v3.py
   一致，已验证 import 成功），未做额外 sys.path 注入。
3. **解释器**：系统默认 python3 无 transformers；使用 /home/xxl/spark2_5/bin/python
   （T4 训练同款环境，见 T4-LAYA/run_laya_v3.sh；torch 2.13.0+cu130, transformers 5.16.1）。
4. **result.json 新增补充字段** `exact_acc_all4_suppl`：原 a2b `exact_acc` 协议
   （sev∧act∧urgent，不含 tactic）逐行保留未改，补充字段仅为对齐 O3 现役 exact 口径
   （0.5216），报告表格中双列呈现。
5. **probs 落盘精度**：round(v, 4)，与旧 results_v3_test.jsonl 存储精度一致。
6. 源目录（EVAL/LAYA-FAMILY、T4-LAYA、suites/）只读未动；本次推理未回写
   zeroshot.json（与 eval_ours_v3.py 原行为的唯一差异，产物只写本目录）。
