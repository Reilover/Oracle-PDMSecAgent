# REPORT · Kev-0.8B zero-shot oracle-v3 test 补评（论文 tab:main I1 行）

- 日期：2026-09-28 · 任务：KEV08-COMPAT/REPORT.md 建议 B 的落地——把 kev-0.8B 零样本首次按 439 窗 oracle 约定在 test 卷正式评测
- 模型：**本地快照 jaredpalmer/kev-0.8b（snapshot 54f4f877，2026-09-22 落盘，head.pt temperature 2.406 / fp32）**。serve 返回 `release_date: 2026-09-22` 已验证未用上游 09-24 round-15 新权重
- 协议：与 V3-TEST-BASELINE 五方重评的 kev-4b-zs **完全一致**——同一 `v3_baseline_runner.py`（新增 `kev08-zs` 方法，问题模板/四问构造/emit 行格式逐行复用 kev4b-zs 路径）、同一 oracle-v3 test.jsonl（439 窗 / 1,756 问，11 选项 TACTIC_CRITERIA + 8 选项 ACTION_CRITERIA）、`kev.serve /v1/systemone` 独立端口 8031；指标用同 `evaluate.py`（analysis_*_test_v3.{json,md} 同 schema）
- GPU 合规：启动前 nvidia-smi 确认（free 20,655 MiB，队友训练 PID 461041 全程未触碰）；0.8B bf16 服务实测占用 ~4.2 GB（<10 GB 红线）；nice 10 + ionice c3 + 绑核 48-63
- 终态：**439/439 窗、0 error 行、id 集合与 suite 完全一致、每行 probs.tactic 恰 11 键**；断点续跑按 id 去重；历史数据零改动

## 1. 正式 test 数字（439 窗 / 1,756 问）

| 任务 | acc | 备注 |
|---|---|---|
| tactic | **0.282** | 宏 F1 0.373；benign 召回 66/299 = 0.221 |
| urgent | 0.761 | |
| severity | 0.178 | QWK 0.458，MAE 0.87；预测塌缩：406/439→medium、33→high，low/critical 0 预测 |
| action | 0.132 | |
| exact match | 0.0023 | 1/439 |
| ECE (tactic / action) | 0.119 / 0.118 | 等频 15 bin；概率近均匀 → 置信度天花板 ~0.2，ECE 反而小 |
| 中位延迟 | 190 ms/窗 | 4B-zs 为 342 ms |

来源：`analysis_kev08-zs_test_v3.json`（同 kev4b-zs schema，含 by_severity / reliability / risk_coverage / bootstrap CI 全字段）。

## 2. 与 dev 0.254 的关系

test 0.282 vs dev 0.254（T2-KEV08 59 窗口径 0.2542；论文脚注 0.259 为 58 唯一 id 口径）——**同带波动，无异常**。三个口径连起来看：v1 470 窗 test 0.245 / v1 dev 0.254 / v3 439 窗 test 0.282，0.8B 零样本 tactic 稳定落在 0.24-0.28 区间。test 略高是窗口集合差异（v3 卷 benign 占比 299/439 = 68%，0.8B 零样本对 benign 有一点高于随机的信号，66/299 vs 随机 299/11≈27），不是能力差异。

## 3. 与 kev-4B-zs 0.761 的对比解读

| | kev-0.8B-zs | kev-4B-zs | Δ |
|---|---|---|---|
| tactic | 0.282 | 0.761 | **-0.479** |
| urgent | 0.761 | 0.831 | -0.070 |
| severity | 0.178 | 0.410 | -0.232 |
| action | 0.132 | 0.636 | -0.504 |
| exact | 0.0023 | 0.194 | -0.191 |

1. **确认 KEV08-COMPAT 结论**：0.8B 零样本在 11 选项下"能跑通且格式合法"（439/439 全 11 键、0 error），但被稀释到近随机——本次实测平均置信度天花板与预测分布（defense_evasion 131 / credential_access 80 / benign 66）与 v1 卷的塌缩模式一致。tactic 0.282 相对 1/11≈0.091 的均匀基线有余量，但相对 benign-majority 基线（0.681）为深度负增益——**入表价值在于展示"上游合成决策预训练在小模型上不可迁移到 11 类 MITRE 约定"，论文 caption 建议措辞 near-chance（0.28），而非 mis-parses**。
2. 0.8B 与 4B 的差距（-0.48 tactic）远大于 4B-zs 与 ORACLE-4B 微调的差距（0.761→0.850，-0.089）：零样本能力在这个基座尺寸段是量变到质变（4B 指针头已能对齐安全 criteria，0.8B 完全对不齐），不是平滑缩放。
3. severity 塌缩（406/439→medium）与 4B-zs 的 severity 弱项（0.410）同方向但更极端：score 头在两个尺寸都未校准，0.8B 连 high/critical 的排序信号都几乎没有。
4. ECE 0.119 < 4B-zs 的 0.237 不是校准更好，而是**均匀分布天然"诚实"**（conf≈acc≈0.2 附近），risk-coverage 无区分度，论文引用时应注意这一解释。

## 4. 产物

- rows：`results_kev08-zs_test.jsonl`（439 行，schema 与 results_kev4b-zs_test.jsonl 完全一致）
- 指标：`analysis_kev08-zs_test_v3.{json,md}`（evaluate.py 同 schema）
- runner：`v3_baseline_runner.py` 新增 `kev08-zs` 方法（kev4b-zs 路径逐行复用，仅输出名不同；原五方法零改动）
- 日志：`logs/kev08_serve.log`、`logs/kev08_zs_test.log`
- 驱动脚本：`/home/xxl/.hermes/cache/scratch/run_kev08_zs_test.sh`（含显存检查/serve/eval 链）

## 5. 执行偏离

无。一次跑通，无断点续跑发生，无 rm，历史文件零改动。
