# oracle-pipeline 完整使用说明（v0.1）

- 版本：v0.1 · 打包日期 2026-09-29 · 对象：`oracle-pipeline/`（ORACLE 双层 PDM 置信升级管线 + Tier-3 人工控制台 UI）
- 定位：**论文 §4/§7 代码落地的实验原型**，在 a800 实验环境实测跑通（20 窗全管线无崩溃，M1–M4 验收通过）。不是生产级产品，部署适配点见 §8。
- 快速导航：§1 系统要求 · §2 实验环境完整配置表 · §3 安装指南 · §4 快速开始（三步）· §5 目录结构 · §6 常见问题 · §7 端口清单 · §8 当前限制声明

---

## 1. 系统要求

### 1.1 软件版本

| 组件 | 版本（实测） | 说明 |
|---|---|---|
| Python（管线 + UI） | 3.11.5 | venv `~/spark2_5`（torch 2.13.0 / transformers 5.16.1 / numpy 2.3.5 / laya 0.3.4 / fastapi 0.136.3 / uvicorn 0.52.4 / sse-starlette 3.4.11 / pydantic 2.13.5） |
| Python（kev serve） | 3.12.4 | venv `~/Mylocllm/kev/kev-repo/.venv`（随 kev-repo 自带） |
| OS | Linux（a800 共享服务器，无 sudo） | 内核 6.8.0-124-generic |
| Docker | 靶场容器已由环境预置 | 管线本身不直接调 Docker，只读其日志产物（range-data） |

### 1.2 Python 依赖清单

管线/UI 侧（spark2_5 venv）：`torch`、`transformers`、`numpy`、`laya`（SDK，本地目录 `/home/xxl/laya`）、`fastapi`、`uvicorn`、`sse-starlette`、`pydantic`。
kev serve 侧：依赖打包在 kev-repo `.venv` 内，无需另装。

### 1.3 硬件门槛（CPU vs GPU）

| 部件 | 最低要求 | 实测 |
|---|---|---|
| Tier 0 规则 + 状态构建 | 纯 CPU，可忽略 | ~0.3 ms/窗 |
| Tier 1 laya-421M | **纯 CPU 即可**（单次前向） | ~1.0–1.3 s/窗（绑核 0-15） |
| Tier 2 Kev-0.8B serve | **需 GPU，显存 ≥8GB**（脚本 `serve_kev.sh` 硬检查 free<8000MiB 即 abort） | NVIDIA A800 80GB PCIe，实测占用 ~4GB 显存，~190 ms/窗 |
| UI（server.py） | 纯 CPU，可忽略 | FastAPI 单进程 |

> 只想看 UI 回放样例数据（不跑 Tier 2）：零 GPU 可用。跑全管线必须有 GPU 起 kev serve。

---

## 2. 实验环境完整配置表（a800 服务器）

| 项 | 值 |
|---|---|
| 服务器 | a800 共享服务器（无 sudo，见共享纪律） |
| GPU | NVIDIA A800 80GB PCIe；kev-0.8B serve 实测占用 ~4GB 显存，`serve_kev.sh` 启动前检查空闲 ≥8GB |
| CPU 绑核/资源纪律 | 所有计算进程统一 `nice -n 10 ionice -c3 taskset -c 0-15`（低优先级 + idle IO + 绑 0-15 核，不与他人抢占） |
| Tier 1 laya（CPU 版） | venv `/home/xxl/spark2_5`（python3 → 3.11.5）；SDK `/home/xxl/laya`；ckpt `~/MySecAgent/lab/experiments/oracle/T4-LAYA/laya-oracle-v3`（内嵌逐题类校准温度 choice 4.84 / score 9.04 / noul 9.22，clamp [0.5,5] 默认生效） |
| Tier 2 kev serve | 仓库 `/home/xxl/Mylocllm/kev/kev-repo`（`.venv/bin/python -m kev.serve --run runs/oracle-kev08-v3`）；head.pt 内嵌全局拟合温度 T=1.9097 默认生效，`KEV_TEMPERATURE=1.0` 可还原 raw logits；`HF_HOME=/home/xxl/Mylocllm/kev/hf-cache HF_HUB_OFFLINE=1` |
| kev serve 启动命令与端口 | `bash serve_kev.sh [port]`（默认 8021，前台等就绪）；`bash start_serve8023.sh`（**8023**，nohup 后台，管线/UI 常用）；`bash start_serve8018.sh`（**8018**，kev-**4B** v3，附加实验链用）。就绪探活 `curl http://127.0.0.1:<port>/v1/models` |
| suite 路径 | `~/MySecAgent/lab/experiments/oracle/suites/oracle-v3`（train/dev/calibration/test jsonl + manifest；test 439 窗为选窗池） |
| 靶场容器日志源 | `~/MySecAgent/range-data/batch1/`（靶场 Docker 容器日志经批处理导出的 jsonl，`state_builder.load_raw_index` 全量索引；选窗实际可用 315 窗） |
| 代码侧外部只读依赖 | `lab/experiments/oracle/code/suite/pack_suite.py`（state 构建同口径）、`judge/rules.py`（Tier 0 规则 R1–R6）、`T4-LAYA/results_v3_test.jsonl`（选窗分层） |
| UI 启动 | `cd ~/MySecAgent/oracle-pipeline/ui && python3 server.py` → **uvicorn 监听 8024**（spark2_5 环境；`http://127.0.0.1:8024/`，API docs `/api/docs`） |
| 阈值 | τ=0.90（自动线）/ τ_h=0.70（人工下限），`gating.py` 顶部常量；UI 滑块可调（写 `ui/ui_runtime.json` 并落审计） |
| 白名单自动动作 | `block_ip / disable_user / isolate_host / reset_credentials`（`gating.AUTO_ACTIONS`，dry-run 记账不真执行） |

---

## 3. 分步安装指南

> 本包在 a800 上解包即用（路径已就位）。以下为**全新机器**的适配步骤；在 a800 上只需第 0 步。

### 0.（a800 已有环境）解包归位

```bash
tar xzf oracle-pipeline-v0.1-20260929.tar.gz -C ~/MySecAgent/
# 确认依赖路径存在：
ls /home/xxl/spark2_5/bin/python /home/xxl/laya /home/xxl/Mylocllm/kev/kev-repo \
   ~/MySecAgent/lab/experiments/oracle/suites/oracle-v3 ~/MySecAgent/range-data/batch1
```

### 1. 依赖安装

```bash
# 管线/UI venv（对齐实测版本）
python3.11 -m venv ~/spark2_5
~/spark2_5/bin/pip install torch==2.13.0 transformers==5.16.1 numpy==2.3.5 \
    fastapi uvicorn sse-starlette pydantic
~/spark2_5/bin/pip install laya        # 或从本地 laya SDK 目录安装

# kev serve：克隆/复刻 kev-repo 并建其自带 venv（含 kev 包与 serve 依赖）
```

### 2. 模型准备

- **laya-421M v3 ckpt**：放到 `~/MySecAgent/lab/experiments/oracle/T4-LAYA/laya-oracle-v3/`（`tier1_laya.CKPT` 指向此处，改路径就改该常量）。
- **Kev-0.8B v3 run**：放到 `~/Mylocllm/kev/kev-repo/runs/oracle-kev08-v3/`（serve 启动参数 `--run` 指向；含 head.pt 温度头）。
- HF 缓存离线化：serve 脚本已带 `HF_HOME=… HF_HUB_OFFLINE=1`，勿改。

### 3. 环境变量 / 路径适配（迁移机器必改）

| 位置 | 改什么 |
|---|---|
| `tier1_laya.py` | `SECAGENT`、`sys.path` 的 `/home/xxl/laya`、`CKPT` |
| `state_builder.py` | `SECAGENT`、`RANGE_DATA`（靶场日志源）、`SUITE_V3`、`LAYA_TEST_ROWS` |
| `serve_kev.sh` / `start_serve8023.sh` / `start_serve8018.sh` | `KEV=` 仓库路径、`LOG=` 日志路径 |
| `run_pipeline.py` 调用 | `--kev-url`（默认 8021；a800 实跑用 8023） |
| `ui/server.py` | 路径按 `PIPE=../` 相对推导，随包迁移无需改；端口 8024 在 `server.py` 末尾 uvicorn.run |

---

## 4. 快速开始（三步）

```bash
# ① 起 kev serve（GPU；a800 实跑用 8023）
cd ~/MySecAgent/oracle-pipeline
bash start_serve8023.sh            # 或 bash serve_kev.sh 8023（前台等就绪）
curl -s http://127.0.0.1:8023/v1/models | head -c 200   # 探活

# ② 跑管线（选窗 → Tier0/1/2 → 门控 → 人工 → 审计）
nice -n 10 ionice -c3 taskset -c 0-15 /home/xxl/spark2_5/bin/python \
    run_pipeline.py --windows 20 --non-interactive y \
    --kev-url http://127.0.0.1:8023 \
    --audit logs/audit.jsonl --windows-json logs/windows.json
# 产出：logs/audit.jsonl（append-only 审计）+ logs/windows.json + logs/routing_summary.json

# ③ 开 UI（Tier-3 控制台）
cd ui && python3 server.py         # http://127.0.0.1:8024/
```

跑完 ② 后刷新 ③ 的队列页即可看到 20 窗回放（路由/逐题分布/延迟/人工决策入口）。
仅回放样例（零 GPU）：跳过 ①②，直接 ③ —— 包内自带 `logs/audit.jsonl` 样例（20 窗 window_done + UI 决策/阈值/标注事件）。

---

## 5. 包内目录结构

```
oracle-pipeline/
├── README-完整使用说明.md   ← 本文件
├── README.md / REPORT.md    ← 模块清单 / 20 窗实测报告
├── run_pipeline.py          ← 编排器（选窗→四层→审计→路由统计）
├── state_builder.py         ← state 构建（pack_suite 同口径）+ 分层选窗
├── tier0_rules.py           ← Tier 0 规则（复用 judge/rules.py R1–R6）
├── tier1_laya.py            ← Tier 1 laya-421M v3（CPU，四题 typed 分布）
├── tier2_kev.py             ← Tier 2 kev serve 客户端（/v1/systemone）
├── gating.py                ← τ/τ_h 门控 + Tier 3 CLI + 审计日志类
├── serve_kev.sh / start_serve8023.sh / start_serve8018.sh
├── run_d1.sh / run_d1_full.py / run_addon_chain.sh / run_addon_12.sh  ← D1 全量/附加实验链
├── logs/
│   ├── audit.jsonl          ← 样例审计日志（20 窗 + UI 事件，26 行）
│   └── windows.json / routing_summary.json（样例产物）
└── ui/
    ├── server.py            ← FastAPI 后端（8024，SSE 推送）
    ├── static/index.html · en.html   ← 单页前端（中/英，零 CDN）
    ├── README.md · USAGE-GUIDE.md · REPORT.md(-EN)
    ├── ui_runtime.json      ← τ/τ_h 运行时可调值
    ├── decisions/           ← 人工决策落盘（按窗 JSON）
    ├── labelled_replays.jsonl ← 标注导出
    └── screenshots/         ← 演示截图
```

## 6. 常见问题（FAQ）

**Q1 端口冲突（8018/8021/8023/8024 被占）**
`ss -ltnp | grep -E '801[88]|802[134]'` 查占用。kev serve 换端口：`bash serve_kev.sh <新端口>` 并在 `run_pipeline.py --kev-url` 同步；8023 与 8018 是 a800 上并存的两个 serve（0.8B / 4B），别混用。UI 端口改 `ui/server.py` 末尾 `uvicorn.run(..., port=…)`。

**Q2 显存不足 / serve 起不来**
`serve_kev.sh` 自检 free<8000MiB 直接 abort —— 等大任务释放或换卡（多卡机 `CUDA_VISIBLE_DEVICES` 指定空闲卡）；kev-0.8B 实际只需 ~4GB。若进程秒退，查 `logs/serve_kev_<port>.log`（常见：ckpt 路径错 / HF 离线缓存缺失）。

**Q3 laya 加载失败 / import laya 报错**
必须用 `/home/xxl/spark2_5/bin/python`（系统 python 无 torch）；SDK 路径 `/home/xxl/laya` 需在 `tier1_laya.py` 的 `sys.path`。`HF_HUB_OFFLINE=1` 由代码自动设置，勿在联网拉取上卡住。

**Q4 路径适配（迁移机器）**
所有硬编码绝对路径集中在 `tier1_laya.py` / `state_builder.py` / 三个 serve 脚本（§3.3 表）。缺 `range-data/batch1` 或 `suites/oracle-v3` 时 `run_pipeline.py` 在选窗阶段即报 KeyError —— 这是预期行为（本包不含数据，见 §8）。

**Q5 run_pipeline 报 "kev serve 未就绪"**
先探活 `curl http://127.0.0.1:<port>/v1/models`；默认 `--kev-url` 是 8021，a800 实跑 8023，记得显式传参（run_d1.sh 已默认 8023）。

**Q6 UI 打开空白/无数据**
UI 只读 `../logs/audit.jsonl` 与 `../logs/windows.json` —— 先跑过管线或确认包内样例在位；SSE 队列依赖同源 8024，勿用 file:// 直开 html。

## 7. 端口清单

| 端口 | 用途 |
|---|---|
| 8018 | kev-**4B** v3 serve（附加实验链：对抗探针/选项翻转） |
| 8021 | kev-0.8B v3 serve 默认端口（`serve_kev.sh` 不传参时；`--kev-url` 缺省值） |
| 8023 | kev-0.8B v3 serve 常驻（nohup；管线/UI 主用） |
| 8024 | UI FastAPI（uvicorn，`python3 server.py`） |

## 8. 当前限制声明（诚实清单）

本包是**实验环境原样交付**，以下限制与"后续解决工程化"计划对应，实际部署需逐项适配：

1. **路径强绑定实验环境**：`tier1_laya.py` / `state_builder.py` / serve 脚本内硬编码 `~/MySecAgent`、`~/Mylocllm/kev`、`~/spark2_5`、`/home/xxl/laya` 等绝对路径，未抽成配置文件/env；换机器必须手改（§3.3）。
2. **数据不含在包内**：选窗依赖 `suites/oracle-v3`、`range-data/batch1`（靶场日志导出）、`T4-LAYA/results_v3_test.jsonl`，均为 a800 上的实验资产；模型 ckpt（laya-oracle-v3、runs/oracle-kev08-v3）同样不在包内。
3. **依赖 Docker 靶场日志源**：管线输入是靶场容器日志的**离线导出**（jsonl），未接实时日志流/Docker API；日志格式与 batch1 切窗器产出绑定。
4. **非生产级工程化**：
   - 无 CI/CD、无单元测试、无 requirements.txt 锁定（版本以 §1.1 实测清单为准）；
   - 单进程批处理，无并发/队列/断点续跑；UI 单用户假设，无鉴权（仅内网 127.0.0.1 使用）；
   - 审计为 append-only JSONL 文件，无数据库/备份轮转；
   - 人工动作是 dry-run 记账（`AUTO_ACTIONS` 白名单模拟执行），不对接任何真实 SOAR/防火墙 API；
   - kev serve 无 systemd/守护，进程挂了需手动重启。
5. **校准与选窗口径**：laya 高置信池为空（v3 校准温度下 min-conf≥0.90 不存在），选窗配额实为 R4/M8/L8；τ/τ_h 为实验值，部署需按业务重标定。
6. **版本耦合**：torch 2.13 / transformers 5.16 / laya 0.3.4 / kev-repo 自带 venv 的组合是实测可用组合，升级任意组件未验证。
