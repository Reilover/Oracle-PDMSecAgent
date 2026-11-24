# 计划A：表2统一重测 REPORT（UNIFORM-BF16）

> 生成：2026-11-23T23:35:00；方案：docs/02-执行交接/表2配置统一补测方案.md v3.1

统一口径：同 runner（run_uniform.py，协议模板逐字复用 baseline_unify_runner/v3_baseline_runner）、同 55/439 卷（oracle-v3 development/test）、同 11 选项约定、idle GPU0、bf16 原生权重、确定性解码（greedy/prefill-logprobs/argmax）；精度格与延迟格同一次运行（latency_ms 逐窗记录）。

## 1. 新测结果（test + dev）

| 行 | split | n | tactic | urgent | severity | action | exact | P50(ms) |
|---|---|---|---|---|---|---|---|---|
| e2-laya | test | 1756 | 0.0251 | 0.6902 | 0.6310 | 0.5923 | 0.0091 | 24.8 |
| e2-laya | development | 220 | 0.0545 | 0.7091 | 0.6364 | 0.5818 | 0.0545 | 24.8 |
| e1-nanojev | test | 1756 | 0.1367 | 0.2301 | 0.1071 | 0.0000 | 0.0000 | 137.9 |
| e1-nanojev | development | 220 | 0.1818 | 0.2364 | 0.1455 | 0.0000 | 0.0000 | 136.9 |
| mb-bf16 | development | 220 | 0.6909 | 0.7818 | 0.6909 | 0.6727 | 0.6727 | 13.7 |
| verdict | test | 1756 | 0.0000 | 0.1481 | 0.6606 | 0.1481 | 0.0000 | 262.9 |
| c-logprobs | test | 1756 | 0.6765 | 0.2301 | 0.6560 | 0.1071 | 0.0000 | 1144.5 |
| c-logprobs | development | 220 | 0.6727 | 0.2364 | 0.6909 | 0.1636 | 0.0000 | 1139.4 |
| b-gen | test | 1756 | 0.1321 | 0.5467 | 0.4055 | 0.1253 | 0.0524 | 268.8 |
| b-gen | development | 220 | 0.0909 | 0.5091 | 0.4000 | 0.0909 | 0.0364 | 309.1 |
| h-gen | test | 1756 | 0.0068 | 0.3212 | 0.1503 | 0.0888 | 0.0023 | 362.6 |
| h-gen | development | 220 | 0.0000 | 0.3273 | 0.2727 | 0.1818 | 0.0000 | 365.4 |
| f1-glm | test | 1756 | 0.6378 | 0.8542 | 0.6948 | 0.1344 | 0.0342 | 1697.4 |
| f1-glm | development | 220 | 0.5818 | 0.8545 | 0.7273 | 0.2000 | 0.0545 | 1723.0 |
| f2-dsk | test | 1756 | 0.6970 | 0.8041 | 0.7426 | 0.2050 | 0.1412 | 774.8 |
| f2-dsk | development | 220 | 0.6545 | 0.7636 | 0.6909 | 0.2364 | 0.1455 | 854.4 |

注：P50 为逐窗 latency_ms 中位数（剔除首窗暖机）；c-logprobs/b-gen 延迟含整窗 4 任务打分/生成；f1/f2 为云 API 整窗单次调用墙钟（网络口径声明保留）。

## 2. 新旧逐格对照（acc）

| 行/split | task | 旧 | 新 | Δ |
|---|---|---|---|---|
| e2-laya/test | tactic | 0.0205 | 0.0251 | +0.0046 |
| e2-laya/test | urgent | 0.6902 | 0.6902 | +0.0000 |
| e2-laya/test | severity | 0.6287 | 0.6310 | +0.0023 |
| e2-laya/test | action | 0.5923 | 0.5923 | +0.0000 |
| e2-laya/test | exact | 0.0091 | 0.0091 | +0.0000 |
| e2-laya/development | tactic | 0.0545 | 0.0545 | +0.0000 |
| e2-laya/development | urgent | 0.7091 | 0.7091 | +0.0000 |
| e2-laya/development | severity | 0.6364 | 0.6364 | +0.0000 |
| e2-laya/development | action | 0.5818 | 0.5818 | +0.0000 |
| e2-laya/development | exact | 0.0545 | 0.0545 | +0.0000 |
| e1-nanojev/test | tactic | 0.1367 | 0.1367 | +0.0000 |
| e1-nanojev/test | urgent | 0.2301 | 0.2301 | +0.0000 |
| e1-nanojev/test | severity | 0.1071 | 0.1071 | +0.0000 |
| e1-nanojev/test | action | 0.0000 | 0.0000 | +0.0000 |
| e1-nanojev/test | exact | 0.0000 | 0.0000 | +0.0000 |
| c-logprobs/test | tactic | 0.6811 | 0.6765 | -0.0046 |
| c-logprobs/test | urgent | 0.2301 | 0.2301 | +0.0000 |
| c-logprobs/test | severity | 0.6788 | 0.6560 | -0.0228 |
| c-logprobs/test | action | 0.1071 | 0.1071 | +0.0000 |
| c-logprobs/test | exact | 0.0000 | 0.0000 | +0.0000 |
| c-logprobs/development | tactic | 0.6727 | 0.6727 | +0.0000 |
| c-logprobs/development | urgent | 0.2364 | 0.2364 | +0.0000 |
| c-logprobs/development | severity | 0.6727 | 0.6909 | +0.0182 |
| c-logprobs/development | action | 0.1818 | 0.1636 | -0.0182 |
| c-logprobs/development | exact | 0.0000 | 0.0000 | +0.0000 |
| b-gen/test | tactic | 0.1298 | 0.1321 | +0.0023 |
| b-gen/test | urgent | 0.7380 | 0.5467 | -0.1913 |
| b-gen/test | severity | 0.5444 | 0.4055 | -0.1390 |
| b-gen/test | action | 0.1412 | 0.1253 | -0.0159 |
| b-gen/test | exact | 0.0456 | 0.0524 | +0.0068 |
| b-gen/development | tactic | 0.0909 | 0.0909 | +0.0000 |
| b-gen/development | urgent | 0.7455 | 0.5091 | -0.2364 |
| b-gen/development | severity | 0.5273 | 0.4000 | -0.1273 |
| b-gen/development | action | 0.1455 | 0.0909 | -0.0545 |
| b-gen/development | exact | 0.0364 | 0.0364 | +0.0000 |
| h-gen/test | tactic | 0.0068 | 0.0068 | +0.0000 |
| h-gen/test | urgent | 0.3235 | 0.3212 | -0.0023 |
| h-gen/test | severity | 0.1549 | 0.1503 | -0.0046 |
| h-gen/test | action | 0.1002 | 0.0888 | -0.0114 |
| h-gen/test | exact | 0.0023 | 0.0023 | +0.0000 |
| h-gen/development | tactic | 0.0000 | 0.0000 | +0.0000 |
| h-gen/development | urgent | 0.3636 | 0.3273 | -0.0364 |
| h-gen/development | severity | 0.3091 | 0.2727 | -0.0364 |
| h-gen/development | action | 0.1818 | 0.1818 | +0.0000 |
| h-gen/development | exact | 0.0000 | 0.0000 | +0.0000 |
| f1-glm/test | tactic | 0.6788 | 0.6378 | -0.0410 |
| f1-glm/test | urgent | 0.8451 | 0.8542 | +0.0091 |
| f1-glm/test | severity | 0.7062 | 0.6948 | -0.0114 |
| f1-glm/test | action | 0.1367 | 0.1344 | -0.0023 |
| f1-glm/test | exact | 0.0319 | 0.0342 | +0.0023 |
| f1-glm/development | tactic | 0.6111 | 0.5818 | -0.0293 |
| f1-glm/development | urgent | 0.8333 | 0.8545 | +0.0212 |
| f1-glm/development | severity | 0.7222 | 0.7273 | +0.0051 |
| f1-glm/development | action | 0.2222 | 0.2000 | -0.0222 |
| f1-glm/development | exact | 0.0741 | 0.0545 | -0.0195 |
| f2-dsk/test | tactic | 0.5809 | 0.6970 | +0.1162 |
| f2-dsk/test | urgent | 0.7973 | 0.8041 | +0.0068 |
| f2-dsk/test | severity | 0.6105 | 0.7426 | +0.1321 |
| f2-dsk/test | action | 0.5171 | 0.2050 | -0.3121 |
| f2-dsk/test | exact | 0.4305 | 0.1412 | -0.2893 |
| f2-dsk/development | tactic | 0.6909 | 0.6545 | -0.0364 |
| f2-dsk/development | urgent | 0.8000 | 0.7636 | -0.0364 |
| f2-dsk/development | severity | 0.7091 | 0.6909 | -0.0182 |
| f2-dsk/development | action | 0.2545 | 0.2364 | -0.0182 |
| f2-dsk/development | exact | 0.1818 | 0.1455 | -0.0364 |

## 3. E1/E2 验收 gate（|Δ|≤0.01）

| 行/split | max abs Δ | 判定 |
|---|---|---|
| e1-nanojev/test | 0.0000 | PASS |
| e2-laya/test | 0.0046 | PASS |
| e2-laya/development | 0.0000 | PASS |

## 4. 冷启动（launch→ready / launch→首行落盘）

```json
{
 "e2-laya": {
  "launch_to_first_row_s": 10.0
 },
 "e1-nanojev": {
  "launch_to_first_row_s": 15.0
 },
 "mb-bf16": {
  "launch_to_first_row_s": 10.0
 },
 "verdict": {
  "launch_to_first_row_s": 10.0
 },
 "c-logprobs": {
  "launch_to_ready_s": 60.0
 },
 "b-gen": {
  "launch_to_ready_s": 60.0
 },
 "h-gen": {
  "launch_to_ready_s": 60.0
 }
}
```

## 5. 差异归因（衔接计划B）

- B/H：Q8量化+temp0.1采样+CPU → bf16+greedy+GPU vLLM（量化/解码/框架三因素，见 CONFIG-SENSITIVITY 因素1/5/7 分解）；
- C：协议本身更换（5采样计数→prefill-logprobs，因素6）叠加 B/H 同款三因素；
- E1/E2：精度迁移 fp32→bf16（因素2，已知近并列翻转率 2/439 量级）+硬件 CPU→GPU（因素3）；
- F1/F2：仅解码 temp0.1→temp0（因素5 云侧）；D/G/I/O/A 行不动。

