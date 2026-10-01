#!/usr/bin/env python3
"""pack_suite.py — ORACLE 四任务数据 → kev 冻结套件（WP-B 核心）

输入（schema v2 记录，见 ~/MySecAgent/datasets/converters/schema.py）:
  {id, source, state:{raw_log_lines, window_stats}, questions:{tactic,urgent,severity,action}, labels:{...}, meta}

输出 kev suite 目录:
  manifest.json + train.jsonl / calibration.jsonl / development.jsonl / test.jsonl
  record 格式: {state: str, questions: {qk: {type, instructions|criteria..., label, src}}, _meta:{source,row_sha256,text_sha256,...}}

关键设计:
  1. state 压缩: raw_log_lines(≤100行) 拼接 + window_stats JSON 行 → 超过 kev MAX_STATE(384 tok) 时
     分级截断: 先砍行(保尾部,日志新事件在后) → 再压 stats(只保留关键键) → 兜底按 token 截断
     截断策略与截断统计进 manifest.truncation 报告
  2. 四问题映射:
     tactic   → choice, criteria = 11 选项文案(与 run_kev.py 基准一致的风格), label=str
     urgent   → noul, instructions{question,focus}, criteria{true/false 文案}, label=bool
     severity → score, criteria=[4 级描述], label=int(0..3)  (kev score 是有序档,带 --ord_w 正则)
     action   → choice, criteria = 7+1 选项; label=None 时整题剔除(不填 no_action, P2 决议)
  3. 校准红线: calibration 分区只接收 source=range 的靶场窗口(温度拟合唯一来源); 其余分区可混
  4. 去重: state 文本 sha256 跨分区查重(select_unique 语义), 重复丢弃计数进 manifest

用法:
  python3 pack_suite.py --inputs <train.jsonl(开源)> [--extra-inputs soc/train.jsonl ...]
      --range-dir ~/MySecAgent/range-data/batch1 --calib-frac 0.10 --dev-frac 0.10
      --out ~/MySecAgent/lab/experiments/oracle/suites/oracle-v1
"""
import argparse, hashlib, json, random, sys
from pathlib import Path

# 与 kev.suite.digest 语义一致(整文件 sha256,UTF-8),独立实现避免拉入 torch/transformers 依赖
def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

# ---------- 常量: 问题模板(与 91 条基准 experiment-data/scripts/run_kev.py 文案同风格,英文) ----------

TACTIC_CRITERIA = {
    "benign": "Normal business or administrative behavior",
    "reconnaissance": "Scanning, probing, or discovery of external resources",
    "initial_access": "Getting an initial foothold from outside",
    "execution": "Running malicious code or commands",
    "persistence": "Maintaining access across restarts or sessions",
    "privilege_escalation": "Gaining higher privileges than intended",
    "defense_evasion": "Avoiding or tampering with defenses and logging",
    "credential_access": "Stealing or guessing credentials, e.g. brute force",
    "discovery": "Reconnaissance of the internal environment",
    "command_and_control": "Beaconing or communication with attacker infrastructure",
    "exfiltration": "Data leaving the organization",
}
TACTIC_INSTR = "Which MITRE ATT&CK tactic best matches this security alert?"

URGENT_INSTR = {"question": "Does this alert require immediate human intervention?", "focus": "Pick the single best fit."}
URGENT_CRIT = {"true": "Act now: ongoing or imminent compromise", "false": "Routine: can wait for normal triage"}

SEV_INSTR = {"question": "How severe is this security incident?", "focus": "Pick the single best fit."}
SEV_CRIT = [
    "low: benign or informational, no response needed",
    "medium: suspicious activity, monitor or investigate",
    "high: likely partial compromise, respond promptly",
    "critical: confirmed compromise with major impact",
]
SEV_LEVELS = ["low", "medium", "high", "critical"]

ACTION_CRITERIA = {
    "block_ip": "Block the source IP at the firewall",
    "disable_user": "Disable or lock the targeted user account",
    "isolate_host": "Isolate the affected host from the network",
    "reset_credentials": "Reset credentials or force a password change",
    "quarantine_message": "Quarantine the email or file",
    "monitor": "Increase monitoring on this source, take no action yet",
    "no_action": "No action needed",
    "escalate": "Escalate to a human analyst now (gating only, never a training label)",
}
ACTION_INSTR = "What is the recommended defensive action?"

# ---------- state 构造与截断 ----------

STATS_KEYS_CORE = ["n_lines", "failed_logins", "accepted_logins", "unique_users", "unique_src_ips", "http_4xx", "http_5xx"]
TOKEN_BUDGET_STATE = 384  # kev MAX_STATE;留 ~30 token 余量给模板
TOKEN_BUDGET_BRANCH = 1024

_TOK = None
def get_tokenizer():
    """加载 Qwen tokenizer(kev venv 或 hf-cache 离线);失败退回字符估算"""
    global _TOK
    if _TOK is not None:
        return _TOK
    import os
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("HF_HOME", "/home/xxl/Mylocllm/kev/hf-cache")
    try:
        from transformers import AutoTokenizer
        _TOK = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-0.8B-Base")
        return _TOK
    except Exception as e:
        print(f"[warn] tokenizer 不可用({e}),退回字符估算", file=sys.stderr)
        _TOK = False
        return None

def est_tokens(s: str) -> int:
    """优先真实 Qwen tokenizer 计数;不可用时字符粗估(英文日志 ~3.5 字符/token)"""
    tok = get_tokenizer()
    if tok:
        return len(tok(s, add_special_tokens=False)["input_ids"]) + 2
    return max(1, int(len(s) / 3.5)) + 2


def build_state(rec, tokenizer_est=est_tokens):
    """raw_log_lines + stats → 单个 state 字符串;分级截断"""
    lines = rec.get("state", {}).get("raw_log_lines") or []
    stats = rec.get("state", {}).get("window_stats") or {}
    meta_src = rec.get("meta", {})
    hdr = f"Security log window ({meta_src.get('source', 'unknown')}):"
    # 级1: 砍日志行(保尾部)
    def join(lines_, stats_):
        st = " ".join(f"{k}={stats_[k]}" for k in STATS_KEYS_CORE if k in stats_)
        return hdr + "\n" + "\n".join(lines_) + (f"\nContext: {st}" if st else "")

    cur = join(lines, stats)
    if tokenizer_est(cur) <= TOKEN_BUDGET_STATE:
        return cur, "none"
    lo, hi = 0, len(lines)
    best = None
    while lo < hi:  # 二分找最大可容纳行数(保尾部)
        mid = (lo + hi + 1) // 2
        if tokenizer_est(join(lines[-mid:], stats)) <= TOKEN_BUDGET_STATE:
            lo = mid
        else:
            hi = mid - 1
    cur, how = join(lines[-lo:], stats), f"tail_lines:{lo}/{len(lines)}"
    if tokenizer_est(cur) <= TOKEN_BUDGET_STATE and lo > 0:
        return cur, how
    # 级2: 砍 stats + 兜底字符截断
    cur = hdr + "\n" + "\n".join(lines[-lo:] if lo else [])
    if tokenizer_est(cur) > TOKEN_BUDGET_STATE:
        cur = cur[: TOKEN_BUDGET_STATE * 3]
    return cur, "hard_trunc"


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def to_kev_record(rec, src_name):
    """schema v2 记录 → kev record(state str + questions dict 内嵌 label);兼容 91 条旧格式 {lines,ctx,label}"""
    # 旧格式适配(PB-01 dataset.jsonl): {id, lines, ctx, label:{tactic,urgent,severity,action}}
    if "state" not in rec and "lines" in rec:
        rec = {
            "id": rec.get("id"), "source": "bench91",
            "state": {"raw_log_lines": rec["lines"], "window_stats": {}},
            "labels": rec.get("label", {}),
            "meta": {"source": "bench91", "extra_context": rec.get("ctx", "")},
        }
    state, trunc = build_state(rec)
    labels = rec.get("labels", {})
    qs = {
        "tactic": {"type": "choice", "instructions": TACTIC_INSTR, "criteria": dict(TACTIC_CRITERIA), "label": labels.get("tactic"), "src": src_name},
        "urgent": {"type": "noul", "instructions": dict(URGENT_INSTR), "criteria": dict(URGENT_CRIT), "label": bool(labels.get("urgent")), "src": src_name},
        "severity": {"type": "score", "instructions": dict(SEV_INSTR), "criteria": list(SEV_CRIT), "label": SEV_LEVELS.index(labels["severity"]) if labels.get("severity") in SEV_LEVELS else None, "src": src_name},
    }
    act = labels.get("action")
    if act in ACTION_CRITERIA and act != "escalate":  # escalate 绝不入训练标签
        qs["action"] = {"type": "choice", "instructions": ACTION_INSTR, "criteria": dict(ACTION_CRITERIA), "label": act, "src": src_name}
    rec_out = {
        "state": state,
        "questions": {k: q for k, q in qs.items() if q["label"] is not None or q["type"] == "noul"},
        "_meta": {
            "source": src_name,
            "id": rec.get("id") or rec.get("window_id") or sha(state)[:16],
            "group_id": (rec.get("id") or rec.get("window_id") or sha(state)[:16]).rsplit("-", 1)[0],
            "variant": "clean",
            "row_sha256": sha(json.dumps({"id": rec.get("id")}, sort_keys=True)),
            "text_sha256": sha(state),
            "oracle_id": rec.get("id") or rec.get("window_id"),
            "truncation": trunc,
            "labels_full": labels,  # 保留 evidence 等评测侧字段
            "meta": {k: v for k, v in rec.get("meta", {}).items()},
        },
    }
    return rec_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True, help="开源训练输入(schema v2 jsonl,可多个)")
    ap.add_argument("--range-dir", default="/home/xxl/MySecAgent/range-data/batch1", help="靶场目录(windows*/*.jsonl)")
    ap.add_argument("--range-dir2", default="", help="第二个靶场目录(如 batch1p5)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--calib-frac", type=float, default=0.10)
    ap.add_argument("--dev-frac", type=float, default=0.10, help="从靶场 test 主卷再划 dev(kev development 分区)")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    rng = random.Random(a.seed)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    # ---- 1. 开源训练数据 ----
    train_recs = []
    for f in a.inputs:
        p = Path(f)
        src = "bench91" if "experiment-data" in str(p) else p.parent.name  # 91条基准特殊命名
        for line in open(f):
            line = line.strip()
            if line:
                train_recs.append(to_kev_record(json.loads(line), src))
    # ---- 2. 靶场: test 主卷 + calib(dev 从 test 主卷再切) ----
    import glob as _glob
    # 剧本-容器匹配规则: 环境 e1/e3/e4 剧本只切到对应容器目录(e2 才切 web/dvwa);batch1p5 用 b15-/e4- 前缀+其目录名
    ENV_OF = {"e1": ("windows-ssh",), "e2": ("windows-web", "windows-dvwa"), "e3": ("windows-ssh-e3b",), "e4": ("windows", "windows-normal"),
              "b15": ("windows-ssh", "windows-dvwa", "windows-normal")}
    # 污染检测(T0 验收 §2): benign/normal 标签窗内含攻击特征即剔除(时段重叠噪声,17.4%)
    ATTACK_SIG = ("sqlmap", "dirb", "gobuster", "hydra", "patator", "or 1=1", "union select", "../")
    range_recs, trunc_stats = [], {}
    mismatch_dropped = polluted_dropped = 0
    RANGE_DIRS = [a.range_dir]
    if a.range_dir2:
        RANGE_DIRS.append(a.range_dir2)
    for rd in RANGE_DIRS:
        for f in sorted(_glob.glob(str(Path(rd) / "windows*" / "*.jsonl"))):
            env = (Path(f).parent.parent.name + "/" + Path(f).parent.name) if a.range_dir2 else Path(f).parent.name
            for line in open(f):
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                eid = (d.get("window_id") or "")[:2]
                if eid in ENV_OF and Path(f).parent.name not in ENV_OF[eid]:
                    mismatch_dropped += 1
                    continue
                # 污染剔除: normal/benign 窗含攻击特征
                lab = d.get("labels", {})
                if (lab.get("tactic") == "benign" or d.get("scenario") == "normal_ops"):
                    text = "\n".join(d.get("state", {}).get("raw_log_lines", [])).lower()
                    if any(s in text for s in ATTACK_SIG):
                        polluted_dropped += 1
                        continue
                r = to_kev_record(d, f"range-{Path(f).parent.name}")
                range_recs.append(r)
                trunc_stats[r["_meta"]["truncation"]] = trunc_stats.get(r["_meta"]["truncation"], 0) + 1
    # web/dvwa 镜像去重: 同 window_id(web 与 dvwa 完全同名)只留 windows-web 侧
    seen_ids, deduped = set(), []
    for r in range_recs:
        oid = r["_meta"].get("oracle_id") or ""
        if oid:
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
        deduped.append(r)
    dropped_mirror = len(range_recs) - len(deduped)
    range_recs = deduped
    rng.shuffle(range_recs)
    n = len(range_recs)
    n_calib = max(1, int(n * a.calib_frac))
    n_dev = max(1, int(n * (a.dev_frac)))
    calib, dev, test = range_recs[:n_calib], range_recs[n_calib : n_calib + n_dev], range_recs[n_calib + n_dev :]

    # ---- 3. 跨分区 state 去重(calibration 独立性保护) ----
    def dedup_vs(pool, ref_hashes):
        keep, dropped = [], 0
        for r in pool:
            h = r["_meta"]["text_sha256"]
            if h in ref_hashes:
                dropped += 1
            else:
                keep.append(r); ref_hashes.add(h)
        return keep, dropped

    seen_h = set()
    train_recs, d1 = dedup_vs(train_recs, seen_h)
    calib, d2 = dedup_vs(calib, seen_h)
    dev, d3 = dedup_vs(dev, seen_h)
    test, d4 = dedup_vs(test, seen_h)

    # ---- 4. 写文件 + manifest ----
    partitions = {"train.jsonl": train_recs, "calibration.jsonl": calib, "development.jsonl": dev, "test.jsonl": test}
    files = {}
    for name, recs in partitions.items():
        p = out / name
        with open(p, "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        files[name] = {"sha256": digest(p), "records": len(recs), "questions": sum(len(r["questions"]) for r in recs)}

    manifest = {
        "version": 1,
        "seed": a.seed,
        "suite": "oracle-v1",
        "holdout_sources": [],
        "base_revisions": {
            "Qwen/Qwen3.5-0.8B-Base": "dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68",
            "Qwen/Qwen3.5-4B-Base": "1001bb4d826a52d1f399e183466143f4da7b741b",
        },
        "trainable_sources": sorted({r["_meta"]["source"] for r in train_recs}),
        "eval_only_sources": sorted({r["_meta"]["source"] for r in test + calib + dev}),
        "context": {"max_state": 384, "max_branch": 1024, "max_packed": 2048, "truncate": False},
        "selection": "ORACLE: open-source backbone (GUIDE/soc) for train; range windows for calib/dev/test only. "
                     "Mirror windows (web/dvwa same scenario) deduped by scenario segment id. "
                     "State-level sha256 dedup across partitions.",
        "objective": "ORACLE four-task decision training; calibration partition = range data only.",
        "files": files,
        "oracle": {
            "calib_source": "range-only",
            "mirror_dropped": dropped_mirror,
            "dedup_dropped": {"train": d1, "calib": d2, "dev": d3, "test": d4},
            "truncation": trunc_stats,
            "range_split": {"calib": n_calib, "dev": n_dev, "test": len(test), "total": n},
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest["oracle"], indent=2))
    print("wrote", out)
    for k, v in files.items():
        print(f"  {k}: {v['records']} records / {v['questions']} questions")


if __name__ == "__main__":
    main()
