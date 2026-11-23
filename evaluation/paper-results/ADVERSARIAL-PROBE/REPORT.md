# C1 对抗探针 — stealth vs non-stealth 对照 REPORT（Z-2）

日期：2026-09-29 ｜ serve：kev-4B v3 @8018（复用，taskset 0-7 + nice/ionice）｜ 判据（事先定）：tactic≥0.7 且高危被门控 → §8 "substantially reduces" 站稳；<0.4 → 措辞降级

## 数据

- stealth 档：`results_kev4b_dual.jsonl`（50 窗，seed 20260928，注入 1-4 行，只读续用）
- **non-stealth 档（本次补）**：`windows_nonstealth/` + `PROBE-MANIFEST-NONSTEALTH.json`（seed 20260929，注入 6-12 行，spray 3行模板×3；六类配比与 stealth 一致）→ 推理 `results_kev4b_nonstealth.jsonl`（50/50，双协议口径）
- 生成器 `gen_adversarial_probe_nonstealth.py` 复用原版载荷/标签/骨架逻辑，只改注入强度；评测驱动 `eval_nonstealth_driver.py` 复用 v3 双协议函数。

## 总体对照（tactic 检出率，50 窗）

| 档 | 部署协议（build_state 截断） | 可见协议（载荷保留） | 误判良性（deploy） |
|---|---|---|---|
| stealth | 1/50 = 0.02 | 4/50 = 0.08 | 46/50 |
| **non-stealth（6-12 行）** | **1/50 = 0.02** | **10/50 = 0.20** | 38/50 |

**强度敏感性结论（judgment）**：把注入强度提高 3-6 倍（1-4 行→6-12 行）后，部署协议检出率**不动**（0.02→0.02），可见协议仅 0.08→0.20。模型对日志内注入基本不具备判别力，且**不是强度问题**——载荷多到占满窗口也救不回来。检出率远低于 0.4 判据 → §8 "substantially reduces" 措辞必须降级（由论文会话执行）。

## 六类分解（non-stealth）

| 类 | deploy | visible |
|---|---|---|
| cred_dump_tool | 1/10 | **9/10（0.90）** |
| xxe_in_config_log | 0/4 | 1/4 |
| reverse_shell_path | 0/10 | 0/10 |
| spray_disguised | 0/6 | 0/6 |
| sqli_in_benign_field | 0/8 | 0/8 |
| ssh_bruteforce_payload | 0/12 | 0/12 |

- 唯一例外是 cred_dump_tool 在可见协议下 0.90（mimikatz/secretsdump 等工具名是训练分布内的强特征）；ssh 暴破载荷连可见协议都 0/12——骨架的良性 Accepted 上下文压倒了注入的 Failed 行。
- dual 口径结论维持：**截断不是唯一原因**——non-stealth 下可见协议也仅 0.20，dual 差距（0.02 vs 0.20）说明 state 打包丢弃注入行是第一道损失，模型判别力缺失是第二道。

## 门控送人工率（τ=0.90/τ_h=0.70 口径，deploy conf）

| 档 | conf<τ（进 confirm/escalate） | conf<τ_h（escalate→人工） | benign 误判且 conf≥τ（自动放行的假阴性） |
|---|---|---|---|
| stealth | 49/50 | — | **0/50** |
| non-stealth | 46/50 | 24/50 | **2/50** |

- **门控是必要防线这一条站得住**：绝大多数被注入窗置信度被压低送人工（stealth 49/50、non-stealth 46/50）。代价：non-stealth 下出现 2 窗高置信（≥0.90）自动放行的假阴性（benign 误判），stealth 0 窗——高强度注入反而把部分窗的模型置信推高过线，值得论文脚注一句。
- 判据双条件中 tactic≥0.7 不成立（0.02），按预案走措辞降级分支：建议 §8 从 "substantially reduces" 改为"探针显示对日志内注入脆弱，门控是必要防线"（与 B18 Decision Hijacking 互证），具体措辞由论文会话定。

## 与论文表述的偏差清单

1. §8 措辞降级触发（<0.4 判据），需论文会话执行，本报告只出数。
2. 六类几乎全灭 + 强度不敏感 → "注入检测"不能作为系统卖点表述；cred_dump_tool 可见协议 0.90 是唯一可用亮点（工具名特征在训练分布内）。
3. 高强度档引入 2/50 高置信假阴性（stealth 为 0），若论文引用 stealth 档门控安全性需补此脚注。

## 可复算

`gen_adversarial_probe_nonstealth.py --seed 20260929` 重生成 50 窗（sha 见 manifest）；`eval_nonstealth_driver.py --port 8018 --probe windows_nonstealth --out results_kev4b_nonstealth.jsonl` 重推理。原始 stealth 数据未改动。
