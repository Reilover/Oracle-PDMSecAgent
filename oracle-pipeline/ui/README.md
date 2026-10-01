# ORACLE Tier-3 Console（BS 架构 UI）

浏览器/服务器架构的 ORACLE 人工层操作台：FastAPI 后端（端口 **8024**）+ 无构建单页前端（原生 ESM，深色 SOC 风格）。替代 CLI y/n 确认，支撑论文 §7 演示与 D 系列人机协同实验。

## 启动

```bash
cd ~/MySecAgent/oracle-pipeline/ui
python3 server.py          # 或 uvicorn server:app --port 8024
# 浏览器打开 http://127.0.0.1:8024/
```

依赖：`fastapi`、`uvicorn`、`sse-starlette`（服务器 python 环境已装；无数据库/Redis/Docker/node）。
数据前置：`../logs/audit.jsonl` 与 `../logs/windows.json`（由 `run_pipeline.py` 产出；当前 20 窗审计已在位）。

## 页面

| 页 | 功能 | 对应任务书 |
|---|---|---|
| 队列 | 待人工窗列表，逐题置信着色（≥τ 绿 / [τ_h,τ) 黄 / <τ_h 红），已决策/待裁决状态 | P0-1 |
| 窗详情 | 384-token state 原文、T1/T2 逐题输出对照（温度校准后置信+门控）、证据关键行高亮；逐题 ✓/✗/改判（11 tactic、4 severity、8 action）+ 整窗 confirm/reject → 写 audit | P0-2/3 |
| 回放 | 全部窗列表 + 单窗决策链时间线（State→Tier0→Tier1→Tier2→门控→Tier3 逐步延迟与输出） | P0-5 |
| 看板 | 路径分布（五路）、逐题路由计数、τ/τ_h 滑块（仅预览 / 应用写配置，回放按当前值重门控）、延迟分解 P50 直方图 | P0-4, P1-7 |
| 标注 | 模糊窗 correct label → 导出 labelled replays JSONL（回放反馈实证物） | P1-6 |

实时性：SSE（`/api/stream`）tail `audit.jsonl`，新窗完成/决策/标注事件即时推送并刷新队列。

## API

- `GET /api/queue[?tau=&tau_h=]` — 队列+回放+看板视图（可传临时阈值做预览）
- `GET /api/window/{id}` — 窗完整数据（state/审计事件/决策/证据行）
- `POST /api/decide` — 逐题决策+整窗 confirm → audit 追加 `human_decision` 事件 + `decisions/<id>.json`
- `POST /api/label` — 标注 → audit 追加 `label` 事件
- `POST /api/threshold` — τ/τ_h 写 `ui_runtime.json` → audit 追加 `threshold_change`
- `GET /api/labels/export` — 导出 `labelled_replays.jsonl`
- `GET /api/stream` — SSE
- 交互式文档：`/api/docs`

## 数据约定

- `../logs/audit.jsonl` **只追加不修改**（红线）；UI 决策以新事件类型（`human_decision`/`label`/`threshold_change`）写入
- `ui_runtime.json` 当前 τ/τ_h；`decisions/` 决策快照；`labelled_replays.jsonl` 标注导出
