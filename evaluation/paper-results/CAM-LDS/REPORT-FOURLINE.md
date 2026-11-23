# cam-lds 第二外部卷四线对照报告（kev-4B / kev-0.8B / laya / NanoJev，全部 v3 数据微调）

- 日期：2026-09-26 · 卷：cam-lds 562 窗（与训练/靶场零重叠；551 纳入统计，11 窗超 8192 token 被各推理端拒绝，集中在 autostart/cron/sshkey 长剧本窗）
- 四线全部用各自 T2/T3/T4 口径评测：kev 系走 kev.serve `/v1/systemone`；laya 走 `Agent.predict`（run 根目录）；NanoJev 走官方 `DecisionPredictor`（CUDA bf16，max_length 8192，选项打分口径）
- 单线首测详情（kev-4B）见本目录 `REPORT.md`

## 1. 四线 cam-lds 总表（551 可评窗）

| 指标 | kev-4B v3 | kev-0.8B v3 | laya v3 | NanoJev v3 | （参考）四线主域 dev tactic |
|---|---|---|---|---|---|
| tactic | **0.240** | 0.062 | 0.058 | 0.033 | 0.782 / 0.727 / 0.655 / 0.673 |
| urgent | **0.588** | 0.452 | 0.470 | 0.470 | 0.782 / 0.764 / 0.764 / 0.782 |
| severity | **0.526** | 0.181 | 0.285 | 0.281 | 0.673 / 0.709 / 0.545 / 0.673 |
| action | **0.347** | 0.102 | 0.098 | 0.071 | 0.691 / 0.691 / 0.709 / 0.600 |
| exact | **0.116** | 0.054 | 0.049 | 0.004 | 0.582 / 0.618 / 0.455 / — |
| 峰值显存 | ~18.5GB | 3.8GB | 8.4GB | ~25GB* | |
| 每窗延迟 | ~秒级 | P50≈0.4s | P50≈0.15s | ~3.5s | |

\* NanoJev 与 WL 训练共卡时实测 19-25GB（fp32 权重+bf16 autocast，max_length 8192）。laya 按可比 551 窗口径列出（562 窗全跑：tactic 0.062 / urgent 0.479 / severity 0.294 / action 0.109 / exact 0.052，与 551 窗口径差 <0.011）。

## 2. 按训练支持分组的 tactic 召回（核心验证）

v3 训练支持类：reconnaissance（ait 1,024 窗）、execution（sg4+linuxapt 877 窗）、credential_access（2,294 窗，但 cam 攻击形态不同）；零支持类：discovery / defense_evasion / privilege_escalation / command_and_control / persistence / initial_access / exfiltration。

### 2a. 分组条件 tactic 准确率

| 分组 | kev-4B | kev-0.8B | laya | NanoJev |
|---|---|---|---|---|
| **有支持类**（n=203） | **0.611** | 0.163 | 0.133 | 0.089 |
| **零支持类**（n=348） | 0.023 | 0.003 | 0.014 | **0.000** |
| 比值（有/零） | 27× | 54× | 10× | ∞（0.089 vs 0） |

### 2b. 逐类召回

| 真值 tactic | 支持 | n | kev-4B | kev-0.8B | laya | NanoJev |
|---|---|---|---|---|---|---|
| reconnaissance | ✅ | 68/75 | 0.721 | 0.471 | 0.387 | 0.265 |
| execution | ✅ | 104 | 0.692 | 0.000 | 0.000 | 0.000 |
| credential_access | ⚠️ 形态异 | 31 | 0.097 | 0.032 | 0.000 | 0.000 |
| discovery | ❌ | 127/130 | 0.047 | 0.000 | 0.000 | 0.000 |
| privilege_escalation | ❌ | 52/53 | 0.038 | 0.019 | 0.094 | 0.000 |
| initial_access | ❌ | 27 | 0.000 | 0.000 | 0.037 | 0.000 |
| defense_evasion / C2 / persistence / exfiltration | ❌ | 142 | **全部 0.000** | **全部 0.000** | **全部 0.000** | **全部 0.000** |

（laya 列按 562 窗全量；n=68/75 等差异来自 11 拒绝窗的类别归属。）

## 3. 结论：4B 的"类覆盖=迁移边界"模式跨范式复制

1. **零支持类全灭是四线普遍律**：defense_evasion / C2 / persistence / exfiltration 四个零支持类在全部四条线（CE+anchor 的 kev 双档、RLCD 的 laya、gold-CE 选项打分的 NanoJev）召回严格 = 0.000；零支持组整体条件准确率 ≤0.023。4B 单点上观察到的边界不是 4B 的特例，而是"训练类覆盖决定迁移边界"的范式无关机制。
2. **有支持类的迁移幅度随模型容量分层**：同为支持类，kev-4B 迁移保持 0.61（recon 0.72 / execution 0.69，接近主域 0.78），三个小模型只有 0.09-0.16——它们把支持类也大量塌到 benign（kev08 预测 benign 429/551、laya 416、nanojev 406 vs 4B 的 136）。即：覆盖是必要条件，兑现迁移还需容量（4B 才把支持类"接住"）。
3. **失败模式两态**：4B 过度泛化到最熟悉类（execution 260 窗误报），小模型保守塌缩到 benign——同一覆盖边界在两端的不同表现，论文 Discussion 可并列。
4. **对论文**：cam-lds 表补齐三行后，"训练域覆盖决定迁移边界"由单点变为 CE/RLCD/选项打分三范式四线互证；小模型的 benign 塌缩同时给出第二条结论（容量门控迁移兑现），支持"公开数据后训练适用范围"的双因素表述（覆盖 × 容量）。

## 4. 产物

- `results_kev08-v3.jsonl`（551 ok + 11 serve 422）、`results_laya-v3.jsonl`（562 ok）、`results_nanojev-v3.jsonl`（551 ok + 11 超长拒绝，同 11 窗）
- 评测脚本：`code/eval/camlds_eval_laya.py`（新增）、`code/eval/camlds_eval_nanojev.py`（新增）、`code/eval/camlds_eval_kev.py`（已有）
- NanoJev v3 ckpt 目录补齐 `tokenizer/`、`backbone_config/`（自 NanoJev-unified warm-start 底座拷贝，官方 DecisionPredictor 要求）

## 5. 反事实精确重算（2026-09-29 补存档）

脚本：`counterfactual_recompute.py`（CPU 秒级、零依赖，读 `results_kev4b-v3.jsonl` 逐窗重算）；
机读输出：`counterfactual.json`。基线：overall = 132/551 = **0.240**；
strong 档条件召回 = 124/203 = **0.611**；recon+execution 均值 = 121/172 = **0.703**。

### 5a. 各口径总召回（kev-4B，551 窗）

| 口径 | 抬到 0.611 | 抬到 0.703 | 说明 |
|---|---|---|---|
| A：三档 348 窗全抬，strong 保持实际 | 0.611 | 0.669 | 论文正文当前文字（"lifting the three below-strong tiers"）**字面所指**，但显然不是 0.382 的来源 |
| B：仅抬 weak 档 198 窗 | 0.448 | 0.482 | |
| C1：仅抬 142 零支持类窗，其余保持实际 | 0.397 | 0.421 | 最"干净"的口径：反事实只作用于全零类 |
| **C2：142 零支持类窗抬到 c；strong 保持 124 对；其余 206 窗按 0 计** | **0.382** | **0.406** | **= 修正稿两数**；审稿人 R3' W6 的算术：(124+86.8)/551、(124+99.9)/551 |
| C3：348 窗按 min(support/500,1) 加权部分抬升 | 0.347 | 0.364 | 覆盖剂量连续化，供参考 |

### 5b. 结论：0.382 / 0.406 的精确归属

两数**精确复现**于口径 **C2**（三位小数全等）：

- 0.382 = (124 + 142×0.611)/551 = 210.7/551 —— 142 个严格零支持类窗（旧 v3 支持口径：defense_evasion 65 + C2 37 + persistence 33 + exfiltration 7）抬到 strong 档条件召回，strong 档保持实际 124 对；
- 0.406 = (124 + 142×0.703)/551 = 223.9/551 —— 同一 142 窗抬到 recon+execution 均值。

**C2 的隐含假设**：discovery(127)/privilege_escalation(52)/initial_access(27) 这 206 个 below-strong 窗按 0 计（丢弃其真实 8 个正确预测），且 baseline 由 0.240 下调到 (124+0)/551 = 0.225。这是审稿人复算路径，但与论文表内"三档"叙事不一致——表口径下应报告 C1（0.397/0.421，基线 0.240 不变）。

### 5c. 论文表述建议

正文当前句子自相矛盾：主语是"348 weak/sparse/zero windows"（→ 应得 0.611/0.669），数字却是 142 窗口径（0.382/0.406）。二选一：

1. **最小改动（推荐）**：保留 0.382/0.406，但把主语改为与数字一致的 142 窗严格零支持组，并把基线口径写明："lifting the 142 strictly-zero-support windows to the strong-tier conditional would raise those windows from 0.00 to 0.611 (0.703); combined with the strong tier's actual 124/203 this corresponds to an overall 0.382 (0.406), conservatively zeroing the remaining 206 below-strong windows"；
2. **口径一致（更干净）**：改用 C1：0.397 / 0.421，基线 0.240 不变、其余窗保持实际，与表 tab:camlds 三档叙事自洽，且同样是保守下界。

若采用方案 2，记得同步更新审稿回复中"0.382–0.406"的表述为"0.397–0.421"。
