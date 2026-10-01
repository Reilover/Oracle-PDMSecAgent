# REPORT — ORACLE Tier-3 Console（BS 架构 UI）

**任务**：TASK-ORACLE-UI-20260928 · **日期**：2026-09-28 · **产出**：`~/MySecAgent/oracle-pipeline/ui/`
**状态**：✅ P0 五项全部完成，P1 两项全部完成；M1-M4 里程碑验收全部通过（API 实测 + 浏览器 E2E 实测）；服务已在 8024 端口实测运行

## 1. 交付物

| 文件 | 说明 |
|---|---|
| `server.py` | FastAPI 后端（8024）：audit.jsonl 回放/实时读取、决策写回、SSE 推送。复用管线模块 `gating`（门控/AuditLog/叙述模板），零逻辑复制 |
| `static/index.html` | 无构建单页前端（原生 ESM，深色 SOC 风格）：队列/窗详情/回放时间线/看板/标注 五页，hash 路由 |
| `decisions/*.json` | 人工决策落盘快照（按窗） |
| `labelled_replays.jsonl` | 标注导出（回放反馈实证物，训练脚本可读格式） |
| `ui_runtime.json` | 运行配置（τ/τ_h 可调值） |
| `screenshots/` | 论文 §7 演示截图 4 张（队列/窗详情×2/看板） |
| `README.md` / `REPORT.md` | 本档 |

## 2. 功能完成度清单

### P0（5/5 ✅）
| # | 功能 | 状态 | 验证方式 |
|---|---|---|---|
| 1 | 队列视图（window_id/场景/来源/路径/逐题置信三色着色 ≥τ 绿·[τ_h,τ) 黄·<τ_h 红） | ✅ | 浏览器实测：16 窗队列渲染，边界值抽查（0.90 绿/0.89 黄/0.68 红）全部正确 |
| 2 | 窗详情（384-token state 原文、T1/T2 逐题对照含温度校准后置信+门控、证据关键行高亮） | ✅ | 浏览器实测：四题 T1 vs T2 对照 + 终局芯片；证据行命中 60 行（web/ssh 两类日志模式） |
| 3 | 决策操作（逐题 approve/veto/改判 11 tactic+4 severity+8 action、整窗 confirm/reject；决策落 audit） | ✅ | 浏览器 E2E：点 ✓/✗ + Confirm → audit.jsonl 出现 human_decision 事件（20→21 行）且 SSE 推回 UI toast |
| 4 | 管线看板（路由路径分布、逐题路由计数、τ/τ_h 滑块写运行配置） | ✅ | API 实测：τ 0.90→0.85 预览，tier1/auto 4→9、tier2/auto 6→16 实时重门控；写配置落 threshold_change 事件 |
| 5 | 审计回放（任一窗完整决策链时间线：State→Tier0→1→2→门控→human 每步延迟与输出） | ✅ | 浏览器实测：sqli 窗 8 节点时间线（含每层延迟、逐题输出、executed 终态） |

### P1（2/2 ✅）
| # | 功能 | 状态 | 验证方式 |
|---|---|---|---|
| 6 | 标注模式（模糊窗 correct label → 导出 labelled replays JSONL） | ✅ | API 实测：标注 sqli 窗 → 导出 1 条，行含 id/state/questions(type+label)/pipeline_final/tier1_dists/tier2_dists/ambiguous |
| 7 | 延迟分解面板（state/tier0/tier1/tier2/gate/human 各段 P50 直方图） | ✅ | 浏览器实测：6 行直方图 + P50/mean/max 统计（tier1 P50=1027.7ms n=16、tier2 P50=192.0ms n=12） |

### P2（0/2，按任务书后置）
- 8 Spark 生成式证据摘要（:18080）未接——沿用 gating.narrate 模板拼装，接口已留位
- 9 多会话/密码保护未做（单机内网原型，任务书明示不需要）

## 3. 里程碑验收

| 阶段 | 验收标准 | 结果 |
|---|---|---|
| M1 | 浏览器列出 20 窗审计回放 | ✅ replay=20（API+浏览器） |
| M2 | 浏览器 approve 一窗 → audit.jsonl 出现决策事件 | ✅ E2E 实测通过（含 SSE 推送回环） |
| M3 | τ 调整后回放路由分布实时变化 | ✅ 0.85/0.60 预览路由计数变化 + 队列 pending 16→15 |
| M4 | labelled replays JSONL 可被训练脚本读取格式 | ✅ 导出字段含 state/questions(type,label)，与 oracle suite 行结构兼容 |

## 4. 启动命令

```bash
cd ~/MySecAgent/oracle-pipeline/ui
python3 server.py            # http://127.0.0.1:8024/  （依赖 fastapi/uvicorn/sse-starlette，系统 python 已装）
```

可选：`uvicorn server:app --host 127.0.0.1 --port 8024`。

## 5. 与任务书偏差

1. **前端框架**：任务书"Vue3 CDN 或原生 ESM"二选一 → 取**原生 ESM 零依赖**（连 CDN 都不依赖，内网断网可用）；其余无偏差。
2. **决策转发管线（§2-②"转发给管线"）**：当前决策写 audit.jsonl + decisions/ 快照，**不回灌正在运行的管线进程**（管线为批处理式跑完即退，无常驻进程可转发；回放视图会即时反映决策状态）。若 D 系列需要在线管线，可在 run_pipeline 增设从 decisions/ 读取的会话模式，属后续工作。
3. **τ 滑块生效范围**：写 `ui_runtime.json` + audit 事件并作用于**回放重门控**；正在批量运行的 run_pipeline 进程仍用 gating.py 常量（管线进程重启后由启动脚本读 runtime 值即可接入，未改 run_pipeline.py——产出隔离红线只写 ui/）。
4. **8021 端口说明**：任务书写"8021 被靶场 FTP 占用"，实测 8021 当前是 kev serve（管线自身）；UI 用 8024，无冲突。
5. **P1-6 导出格式**：任务书未给 schema，采用与 oracle suite test.jsonl 同构的 `{id, state, questions:{type,label}}` + 附加 pipeline_final/tier1_dists/tier2_dists/ambiguous，训练脚本可零改动读取 questions 部分。

## 6. 红线遵守

- ✅ 产出只写 `oracle-pipeline/ui/`（oracle-paper/ 零改动）
- ✅ 复用管线 import（`gating.AuditLog`/`gate`/`narrate`），零复制逻辑
- ✅ audit.jsonl 只追加（20→26 行，前 20 行 hash 校验未变：beb6fd11e16c）
- ✅ 无数据库/Redis/Docker/node 构建；UI 纯 CPU，未启任何 GPU serve
- ✅ 端口 8024

## 7. 测试期间写入的数据（演示现场可直接用）

audit.jsonl 追加了 6 条 UI 事件（3× human_decision、1× label、2× threshold_change，τ 已恢复 0.90/0.70 默认值）；decisions/ 3 个决策快照；labelled_replays.jsonl 1 条标注。均为真实操作产物，可留作演示或删除重录。
