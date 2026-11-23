# ADVERSARIAL-PROBE READY（3-1 C1 最小对抗探针 · 数据构造完成）

- 完成时间：2026-09-28（UTC 时钟见 PROBE-MANIFEST.json 旁 window_id）
- 状态：**数据构造完成，待模型推理评测**（kev-4B v3 正被 B3 种子训练占 GPU，评测等 B3 完）
- 数量与配比：50 窗（ssh_bruteforce_payload 12 / cred_dump_tool 10 / reverse_shell_path 10 / sqli_in_benign_field 8 / spray_disguised 6 / xxe_in_config_log 4）
- 自检：window_selfcheck PASS（空窗 0%、schema 0 错、同 state 多标签组 0）
- 可复算：生成脚本 + PROBE-MANIFEST.json + seed=20260928 全在位，骨架序列/类别序列重放一致（已验证）
- 骨架口径：batch1/windows/ 中 labels.tactic=='benign' 的 354 个良性窗（只读），每骨架最多复用 2 次
- 评测口径：每窗 labels = 注入攻击类别 ground truth（tactic/urgent/severity/action 全档高危）；结果判据见计划 v2 §3-1（tactic ≥0.7 且高危样本被门控送人工 → "substantially reduces" 站稳；<0.4 → 措辞再降级，两种结果都可发表）
- 评测入口：lab/experiments/oracle/EVAL/ADVERSARIAL-PROBE/windows/*.jsonl（state 结构与 oracle-v3 test range 窗同构）

## 实验侧评测指引（B3 完成后）

1. 逐窗送 kev-4B v3（oracle-v3 主线 checkpoint），state 按 suite 同款拼装
2. 指标：tactic 命中率（按 6 类分别 + 总体）、门控率（高危样本 p 高于 τ 送人工的比例）、与 oracle-v3 test 中同类 tactic 的差距
3. 结果回填：论文 §4.3/§8 对抗探针小节（Q5 终审）
