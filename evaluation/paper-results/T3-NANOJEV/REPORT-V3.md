# T3 NanoJev v3 重训报告（WP-V6 第 3 线）——数据修复在自建 SFT 入口的复制

- 日期：2026-09-26 · 训练：data-nanojev-v3（oracle-v3 suite 转换），1400 步全量 / 13,415s（3.7h，与 WL llamafactory 共享 GPU 而非独占 ~80min）/ 峰值 16.55GB / loss 16.97→~1（正常收敛）
- checkpoint：`nanojev-oracle-v3/best.safetensors`（min dev gold NLL 选择，best @ step 100，NLL 1.321）
- 重训说明：首轮在 step 25 被中断（残次品保留于 `nanojev-oracle-v3-interrupted-step25/`），本轮全量重跑

## 1. dev 四任务三重对照（220 问 = 55 窗 × 4 任务）

| 指标 | 零样本探针（unified 热启动） | v1 微调 | **v3 微调（best）** |
|---|---|---|---|
| tactic | 0.182 | 0.224 | **0.673**（3.0 倍 v1）|
| urgent | 0.236 | 0.776 | **0.782** |
| severity | 0.164 | 0.448 | **0.673** |
| action | 0.0 | 0.069 | **0.600** |
| overall acc | 0.145 | 0.379 | **0.682** |

**收敛轨迹**：loss 16.97→1 左右；dev NLL 在 step 100 即达最优 1.321，此后 1.3~3.3 波动（acc 稳定 0.66-0.71）——0.4 epoch 已充分，1400 步训练过量无害（best 选择机制兜底）。

## 2. 四线赛马 v3 终表（oracle-v3 dev 卷）

| 线 | 范式 | tactic | urgent | severity | action | 备注 |
|---|---|---|---|---|---|---|
| kev-4B v3 | 指针 CE | **0.782** | **0.782** | 0.673 | 0.691 | exact 0.582 / benign 0.865 |
| kev-0.8B v3 | 指针 CE（无 anchor） | 0.727 | 0.764 | **0.709** | 0.691 | exact 0.618 / benign 0.865 |
| laya v3（421M） | RLCD proper scoring | 0.655 | 0.764 | 0.545 | **0.709** | exact 0.455 / benign 0.838 / 72ms（v1 suite 59 窗另测 0.729/0.763/0.729/0.763） |
| **NanoJev v3** | SFT gold CE（自建入口） | 0.673 | **0.782** | 0.673 | 0.600 | overall 0.682（按问，无逐窗 exact） |

**四线全部转正**——v1 时代"坏数据伤强底座"的规律在 v3 数据下消失：最弱底座 NanoJev（零样本 tactic 0.182）v3 后 0.673，与 4B 的差距缩到 0.109。数据质量是第一位变量的结论在全部四种范式（CE / CE+anchor / RLCD / 自建 gold-CE SFT）上一致成立。

## 3. 结论

1. **v3 修复在 NanoJev 线复制成功**：四任务相对 v1 全部大幅提升（tactic +0.449 / severity +0.225 / action +0.531）
2. 1400 步（0.4 epoch）后 dev NLL 最优出现在 step 100——小底座对 6 万级问答对收敛极快，后续可减步省时
3. urgent 达 0.782 与 kev-4B 并列第一；action 0.600 为四线最低但仍远超 v1 的 0.069

## 4. 产物

- `T3-NANOJEV/nanojev-oracle-v3/`（best.safetensors + train_log.json 1400 步 + summary.json）
- `T3-NANOJEV/train-log-v3/`（train.log + gpu_mem.log 采样）
- `T3-NANOJEV/nanojev-oracle-v3-interrupted-step25/`（首轮中断现场，仅 25 步日志，留档）
