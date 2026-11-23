# laya 家族梯度·零样本对照 REPORT（B-3 + E-4 同口径补全）

日期：2026-09-29（E-4 当日）｜ 脚本 `eval_zeroshot.py`（三官方 ckpt）、`eval_ours_v3.py`（E-4 ours 同卷重评）｜ 逐窗输出 `zeroshot_{base,multilingual,td,ours_v3}.jsonl`，汇总 `zeroshot.json`

## 口径澄清（E-4 核实结论）

- **三官方 ckpt 零样本本来就是 11-opt 口径**：B-3 用的就是 oracle-v3 suite 的 `TACTIC_CRITERIA`（11 类），逐窗预测实际覆盖 persistence/execution 等 6 类；旧 REPORT 里"零样本三线为 11-opt vs ours 4-opt"的说法中，**ours 侧才是异质口径**——0.657/0.472 来自早期 470 窗卷（items-v3 早期版，tactic 标签仅 benign/initial_access/credential_access 三类主导，但选项空间同为 11 类模板）。
- **E-4 补的是 ours 行**：T4 laya-oracle-v3 ckpt 在 `suites/oracle-v3/test.jsonl` 439 窗上按 `eval_zeroshot.py` 完全同协议（SDK 直调、同 state、同问题模板、GPU 共卡）重评，`zeroshot_ours_v3.jsonl` 439/439。

## 对照表（4-opt 旧卷 vs 11-opt 同卷，全部 oracle-v3 test 439 窗同口径）

| 模型 | tactic | urgent | severity | action | exact | 延迟 P50 |
|---|---|---|---|---|---|---|
| laya-base 421M（零样本） | 0.025 | 0.690 | 0.631 | 0.592 | 0.009 | 24.8ms |
| laya-multilingual 322M（零样本） | 0.107 | 0.221 | 0.169 | 0.105 | 0.005 | 19.6ms |
| laya-td 421M typed（零样本） | 0.116 | 0.759 | 0.141 | 0.087 | 0.000 | 25.2ms |
| **ours laya-421M（T4 后训练）** | **0.724** | **0.770** | **0.645** | **0.740** | **0.522** | 24.9ms |
| ours 旧卷口径（470 窗早期卷，仅参照） | 0.657 | — | — | — | 0.472 | — |

### 4-opt vs 11-opt 对照解读

- 旧 0.657 → 同卷 **0.724（+0.067）**、exact 0.472 → **0.522（+0.050）**：差异来自**卷不同**（470 窗早期卷 vs 439 窗 v3 test 卷，类别构成与打包版本不同），不是选项空间变化（两侧模板同为 11 类）。
- 同卷下后训练增益结论**增强**：同骨干 base 0.025 → ours 0.724（**28.9 倍**），exact 0.009 → 0.522（57 倍）。
- 同卷严格同表后，"零样本全灭 vs 后训练大幅增益"的 §6.2 substrate 论证现在无口径瑕疵，可直接引用 0.724/0.522。

## 结论（B-3 结论复核，E-4 后全部维持）

1. 三官方 ckpt 零样本全灭结论不变（tactic 0.025-0.116 ≈ 11 选 1 随机 0.09 水平）。
2. 后训练增益 26 倍 → **28.9 倍**（同卷口径）。
3. 322M 判据复核：0.107 < 0.30，**不值得后训练**结论不变。
4. typed-decisions 与本域不对齐结论不变。

## 局限

- ours E-4 重评为 GPU 共卡口径（24.9ms/窗），与三官方零样本评测条件一致。
- 旧 470 窗卷与 v3 439 窗卷的类别构成差异（initial_access 96→67 等）使两行数字不可互相归因于模型变化。

## 可复算

`eval_zeroshot.py` / `eval_ours_v3.py`（断点续跑支持）；`zeroshot_{base,multilingual,td,ours_v3}.jsonl` 各 439 行含逐窗 pred/conf/latency。
