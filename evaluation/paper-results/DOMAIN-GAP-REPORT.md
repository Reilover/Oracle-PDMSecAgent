# 三域数据分布差距分析（DOMAIN GAP）

- 日期：2026-09-25 · 目的：定位 v3 训练集（sg4+ait+linuxapt，100% 公开日志）→ cam-lds 第二外部卷 tactic 0.240（靶场 dev 0.782）的域移位来源
- 数据：v3 训练集 = sg4+ait+linuxapt 的 train+val（13,774 窗）；cam-lds test 562 窗；靶场 = oracle-v3 suites calibration+development+test（549 窗，state 内嵌原始行）
- 方法：全部 python3 统计，无模型推理。**token 为近似估计 = 窗口字符数 / 3.5**（英文日志经验值，未跑 tokenizer）；8192 阈值与 serve 端拒判一致
- 逐类召回来自 EVAL/CAM-LDS/results_kev4b-v3.jsonl（551/562 纳入，11 窗 422）

## 1. 三域对照总表

| 维度 | v3训练集 | cam-lds | 靶场 |
|---|---|---|---|
| 窗口数 | 14774 | 562 | 549 |
| 日志源 | security-gym-v4(eBPF audit: open/exec...) + AIT-LDS 8靶场(Apache) + linux-apt-2024(syslog auth) | cam-lds manifestations（dnsmasq/syslog 多设备合成） | 自研靶场 range-windows（sshd/auth/paramiko playbook） |
| 主时间戳格式 | 其他/无时间戳 59%, ISO8601-Z(μs/ns) 34%, syslog(Mon dd HH:MM:SS) 6%, apache([Tue Jan ..]) 0% | 其他/无时间戳 83%, syslog(Mon dd HH:MM:SS) 17%, apache([Tue Jan ..]) 1%, ISO8601-Z(μs/ns) 0% | ISO8601-Z(μs/ns) 91%, 其他/无时间戳 9% |
| JSON 行占比 | 2.78% | 4.21% | 0.00% |
| 行数 p50/p90/max | 62/100/100 | 38/43/49 | 5/6/6 |
| token≈chars/3.5 p50/p90/max | 2921/7293/43818 | 1394/2606/17925 | 134/143/155 |
| 超 8192 token 占比 | 1361/14774 (9.2%) | 10/562 (1.8%) | 0/549 (0.0%) |
| 良性占比 | 67.7% | 0.0% | 69.0% |
| urgent=true 占比 | 10.4% | 52.1% | 22.2% |
| severity 分布 | low 60%, medium 30%, high 10%, critical 0% | high 58%, medium 42% | 0 69%, 1 20%, 2 8%, 3 3% |
| action 分布 | no_action 58%, monitor 32%, block_ip 9%, isolate_host 0% | monitor 42%, isolate_host 33%, block_ip 25% | no_action 69%, monitor 20%, block_ip 11%, disable_user 0% |

> 靶场 severity 为 0-3 数值口径（0=benign），v3/cam-lds 为 low/medium/high/critical 文本口径。

## 2. 日志源与行格式细节

### v3训练集(sg4+ait+linuxapt)

- 时间戳分布（按日志行）：其他/无时间戳 59%, ISO8601-Z(μs/ns) 34%, syslog(Mon dd HH:MM:SS) 6%, apache([Tue Jan ..]) 0%
- syslog 程序名 top10：CRON(16442), sshd(8231), sudo(80), systemd-logind(56), systemd(32), su(24), pkexec(6), kernel(6), kesl(2), useradd(1)
- eBPF comm= 进程名 top10：sshd(170574), systemd-journal(62676), systemd(12563), bash(11471), w(10068), lspci(9802), ss(5704), wget(2910), nginx(1700), cat(1568)
- IP /16 网段 top8：66.249.x.x(82619), 173.199.x.x(43707), 24.246.x.x(39011), 192.168.x.x(29811), 198.84.x.x(8947), 101.226.x.x(8346), 1.8.x.x(7961), 1.5.x.x(7954)
- 用户名 top8：root(16747), HTTP(1799), postgres(636), admin(549), ubuntu(540), deploy(531), www-data(495), git(357)

### cam-lds测试卷

- 时间戳分布（按日志行）：其他/无时间戳 83%, syslog(Mon dd HH:MM:SS) 17%, apache([Tue Jan ..]) 1%, ISO8601-Z(μs/ns) 0%
- syslog 程序名 top10：dnsmasq(1126), kernel(830), systemd(498), sudo(92), sshd(28), systemd-logind(23), rustdesk(22), web_php(18), mariadbd(16), crontab(12)
- eBPF comm= 进程名 top10：4267494F5468727E506F6F6C202331(9), 536F636B657420546872656164(3), 57656220436F6E74656E74(1), 43616368653220492F4F(1), 53747265616D5472616E7320233138(1)
- IP /16 网段 top8：192.42.x.x(3933), 172.17.x.x(1257), 192.168.x.x(374), 127.0.x.x(23), 236.0.x.x(19), 237.0.x.x(19), 238.0.x.x(19), 239.0.x.x(19)
- 用户名 top8：root(295), executed(83), www-data(40), Message(38), Manager(37), Target(35), Runtime(34), debian(25)

### 靶场测试卷(v3 suites)

- 时间戳分布（按日志行）：ISO8601-Z(μs/ns) 91%, 其他/无时间戳 9%
- syslog 程序名 top10：—（无 syslog 格式行）
- eBPF comm= 进程名 top10：—
- IP /16 网段 top8：172.28.x.x(2749)
- 用户名 top8：child(282), monitor(91), deploy(65), clumsy(51), admin(43), ubuntu(37), postgres(34), git(32)

## 3. 词汇 top20 与跨域重叠（Jaccard）

**v3训练集(sg4+ait+linuxapt)** top20 词：root(687422), pct(469205), msg(464989), audit(413638), comm(381018), jan(333996), mozilla(303422), open(290254), flags(290213), o_rdonly(252970), t22(227352), norm(222264), ouid(207300), ogid(207300), compatible(196876), app(194030), tabs(193964), syscall(189938), sshd(189501), auid(186568)

**cam-lds测试卷** top20 词：root(13493), msg(7675), audit(7325), ouid(5129), ogid(4911), usr(4823), syscall(4689), bin(4330), auid(3983), fsuid(3399), proctitle(3368), gid(3289), euid(3126), suid(3124), egid(3124), sgid(3124), fsgid(3124), judy(3124), arch(3102), sep(2925)

**靶场测试卷(v3 suites)** top20 词：connection(929), t01(748), t02(707), ssh2(446), password(445), rdomain(384), monitor(343), sqlmap(294), invalid(289), child(282), t07(279), t13(270), t12(264), received(262), starting(257), sep(256), transferred(237), sent(237), bytes(237), deploy(235)

| 重叠度 | top20 词 Jaccard | 全词表(≥5次) Jaccard | 全词表 Jaccard |
|---|---|---|---|
| 训练↔cam-lds | 0.212 | 0.023 | 0.007 |
| 训练↔靶场 | 0.000 | 0.003 | 0.001 |
| cam-lds↔靶场 | 0.026 | 0.026 | 0.009 |

## 4. 恶意行为覆盖矩阵（三域 × 11 tactic 窗数）

| tactic | v3训练集 | cam-lds | 靶场 | cam-lds召回(kev4b-v3) |
|---|---|---|---|---|
| benign | 10002 | 0 | 379 | — |
| reconnaissance | 1024 | 75 | 0 | 49/68 = 0.72 |
| initial_access | 76 | 27 | 78 | 0/27 = 0.00 |
| execution | 877 | 104 | 0 | 72/104 = 0.69 |
| persistence | 0 | 33 | 0 | 0/33 = 0.00 |
| privilege_escalation | 57 | 53 | 0 | 2/52 = 0.04 |
| defense_evasion | 0 | 65 | 0 | 0/65 = 0.00 |
| credential_access | 2294 | 31 | 92 | 3/31 = 0.10 |
| discovery | 0 | 130 | 0 | 6/127 = 0.05 |
| command_and_control | 0 | 37 | 0 | 0/37 = 0.00 |
| exfiltration | 444 | 7 | 0 | 0/7 = 0.00 |
| 合计 | 14774 | 562 | 549 | 0.240 总体 |

- 有训练支持的恶意类（reconnaissance,initial_access,execution,privilege_escalation,credential_access,exfiltration）：召回 126/289 = **0.436**
- 零支持类（persistence,defense_evasion,discovery,command_and_control）：召回 6/262 = **0.023**
- 预测 tactic 分布（模型侧倾斜）：execution 47%, benign 25%, reconnaissance 12%, privilege_escalation 7%, credential_access 3%, command_and_control 2%, initial_access 2%, discovery 1%, persistence 0%, exfiltration 0%

## 5. 8192 token 拒判（422）核对

- chars/3.5 估计超限：10 窗；serve 端实际 422：11 窗；两者重合 10
- 实际 422 名单：cam-1_autostart_localaccount-3, cam-1_autostart_sshkey-13, cam-1_autostart_sshkey-16, cam-1_cron_localaccount-3, cam-1_cron_sshkey-4, cam-1_pwnkit_sshkey-4, cam-1_racecondition_pam-13, cam-1_racecondition_sshkey-4, cam-1_sudo_pam-13, cam-1_sudo_sshkey-3, cam-1_validaccount_pam-4

## 6. Top5 域移位因素（按对 0.240 的贡献排序）

1. **tactic 类支持缺失/长尾支持不足（最大因素）**：cam-lds 10 个恶意类中 4 类（persistence/defense_evasion/discovery/C2，262/551=48% 评测窗）在 v3 训练集 **0 支持**，召回 6/262=0.023；另有 initial_access（训练 76 窗）与 exfiltration（444 窗）在 cam 上同样 0/34 全错——形态错配使'名义有支持'失效。合计 6 类 296/551=54% 的窗只贡献 6 个正确。反事实：若零支持 4 类达到有支持类平均召回 0.44，总体将从 0.240 升至约 0.436——类覆盖缺口解释了与靶场 0.782 差距的大部分。
2. **良恶比/标签先验移位**：cam-lds 100% 恶意（0 良性窗）vs 训练集 68% 良性、靶场 69% 良性；模型在零良性卷上仍把 25% 的窗预测为 benign（136/551，全部计错，直接压掉 ~25% 个百分点）。urgent 52% vs 训练 10%、action 需要 isolate_host 33% 而训练集 isolate_host≈0——severity/action 的 acc 塌陷（0.526/0.347）同源于此。
3. **同 tactic 表面形态错配**：credential_access 训练 2,294 窗（eBPF sshd 暴破/填鸭形态）但 cam 形态不同（PAM race/valid account），召回仅 0.10；privilege_escalation 57 窗→0.04。cam 的 auditd 词汇（msg/audit/ouid/syscall，top20 与训练重叠 Jaccard 0.212）带来部分可迁移特征——这正是 recon 0.72 / execution 0.69 的来源；dnsmasq/JSON 设备行则是训练中不存在的形态。
4. **实体命名空间移位**：IP 网段（cam 192.42.x/172.17.x vs 训练 66.249.x/192.168.x）、主机名（corpdns）、用户名（judy 等）与训练集分布不重叠；cam 还含十六进制编码 comm 名等训练中无对应物的 token。PTR 反查/NXDOMAIN 等 DNS 侦控行为模式在训练集无先例。
5. **窗口规模与长窗 422 拒判**：11/562=2.0% 窗超 8192 token 被 serve 端拒判（chars/3.5 估计 10 窗、与实际 422 名单重合 10），全部集中在 autostart/cron/sshkey/pam 长剧本（偏 persistence/privilege_escalation）；窗口规模本身三域差异大（行数 p50：训练 62 / cam 38 / 靶场 5，token p50：2,921/1,394/134），靶场高分是在极小窗+良性主导条件下取得，与 cam 长窗条件不可比。模型侧还出现 execution 过度泛化（预测分布 execution 47%）。

## 7. 结论

- 0.240 的构成：recon+execution 两类贡献 121/551=22% 的正确（占总正确 121/132=92%）——**迁移只发生在'有支持且形态部分重叠'的类上**；零支持 4 类 48% 的窗近乎全灭。
- 衰减分解（定性+数字）：0.782→0.240 的落差 ≈ 类覆盖缺口（~20% 个百分点可归因）+ 良恶先验反转（benign 误判 ~25%pp）+ 形态/实体移位（有支持类召回 0.436 而非靶场档位）。
- 靶场 0.782 的高分依赖三个 cam-lds 不具备的条件：68% 良性主导的类分布、sshd/auth 短窗形态、仅 3 个 tactic 的窄类目。
- 论文 Discussion：沿用'训练域覆盖决定迁移边界'叙事；把良恶比先验移位与实体命名空间移位列为公开数据后训练的两条明确局限；报告 422 拒判为部署层边界（2% 长窗损失）。

---
复现：`python3 lab/experiments/oracle/code/analysis/domain_gap.py`（本脚本，输出即本报告）
