#!/usr/bin/env python3
"""evaluate.py — ORACLE 统一评测框架（WP-G）

输入: results_*.jsonl(逐条预测+概率,与 kev benchmark rows.json 或 run_kev.py 输出兼容)
输出: analysis_*.json(指标汇总) + 可选 markdown 表

指标口径(对齐实验总方案 §5 验收线):
  - tactic_acc(9 类支持集宏 F1 也报) / urgent_acc / sev_acc(+加权 Kappa,MAE) / action_acc / exact_match
  - ECE 15 bins 等频(tactic 任务,温度拟合前后双版本)
  - risk-coverage 曲线 + τ 扫描(自动化率 vs 误处置率)
  - bootstrap 95% CI(1000 重采样,按 group_id 剧本段聚类——web/dvwa 镜像同进同出,D3 决议)
  - E-3 spray/stuffing 子集单独报告(防"全报急"退化,D4 决议)
  - severity 分档报告(critical 单列样本量警示,D2 决议)

用法:
  python3 evaluate.py --suite <dir> --rows <rows.json 或 results.jsonl> --out analysis.json [--md table.md]
  # 或批量: --rows 支持逗号分隔多文件
"""
import argparse, collections, json, math, random, sys
from pathlib import Path

SEVS = ["low", "medium", "high", "critical"]
TACTICS = ["benign", "reconnaissance", "initial_access", "execution", "persistence",
           "privilege_escalation", "defense_evasion", "credential_access", "discovery",
           "command_and_control", "exfiltration"]
TASKS = ["tactic", "urgent", "severity", "action"]


# ---------- 行格式统一 ----------

def load_rows(path):
    """兼容两种格式: kev benchmark rows.json(list) / run_kev.py results jsonl(逐条含 pred+probs)"""
    p = Path(path)
    if p.suffix == ".json":
        data = json.load(open(p))
        return [normalize_kev_row(r) for r in data]
    rows = []
    for line in open(p):
        line = line.strip()
        if line:
            rows.append(normalize_raw_row(json.loads(line)))
    return rows


def normalize_kev_row(r):
    """kev rows.json: {id, group, question(=任务名), type, keys(选项名列表), label(索引), p(概率数组), ...}
    score 的 keys 是档位索引 '0'..'3'(映射 severity 级);noul 的 keys 是 ['false','true']"""
    keys = r.get("keys") or []
    p = r.get("p") or []
    pred_i = max(range(len(p)), key=lambda i: p[i]) if p else None
    label_i = r.get("label")
    task = r.get("question")

    def as_name(idx):
        if not isinstance(idx, int) or idx >= len(keys):
            return idx
        k = keys[idx]
        if task == "severity" and k.isdigit():
            return SEVS[int(k)]  # '0'..'3' -> low..critical
        if task == "urgent":
            return k == "true"  # 'true'/'false' -> bool
        return k

    pred = as_name(pred_i) if pred_i is not None else None
    label = as_name(label_i)
    conf = p[pred_i] if pred_i is not None and p else None
    return {
        "id": r.get("id"), "group": r.get("group") or r.get("id"),
        "task": task, "type": r.get("type"),
        "label": label, "pred": pred, "conf": conf,
        "correct": (pred == label) if pred is not None and label is not None else None,
        "probs": dict(zip([as_name(i) for i in range(len(keys))], p)) if keys and p else None,
        "variant": r.get("variant", "clean"),
    }


def normalize_raw_row(r):
    """run_kev.py 风格: {id, pred:{tactic,urgent,severity,action}, probs:{tactic:{...}}, ...}"""
    out = []
    for task in TASKS:
        pred = (r.get("pred") or {}).get(task)
        if pred is None:
            continue
        pr = (r.get("probs") or {}).get(task)
        if isinstance(pr, dict):
            conf = pr.get(str(pred), pr.get(pred))
        else:
            conf = None
        out.append({
            "id": r.get("id"), "group": (r.get("id") or "").rsplit("-", 1)[0], "task": task,
            "type": "choice" if task in ("tactic", "action") else ("noul" if task == "urgent" else "score"),
            "label": r.get("label", {}).get(task), "pred": pred, "conf": conf,
            "correct": pred == r.get("label", {}).get(task), "probs": pr,
            "meta": r.get("meta", {}),
        })
    return out  # 注意: 该格式一行展开为多 task 行


def flat_rows(paths):
    rows = []
    for p in paths:
        for x in load_rows(p):
            if isinstance(x, list):
                rows.extend(x)
            else:
                rows.append(x)
    return [r for r in rows if r.get("variant", "clean") == "clean"]


# ---------- 核心指标 ----------

def task_metrics(rows, task):
    tr = [r for r in rows if r["task"] == task and r.get("correct") is not None]
    if not tr:
        return {"n": 0}
    n = len(tr)
    acc = sum(r["correct"] for r in tr) / n
    out = {"n": n, "acc": acc}
    if task == "tactic":
        # 宏 F1(有支持样本的类)
        labels = sorted({r["label"] for r in tr})
        f1s = []
        for lb in labels:
            tp = sum(1 for r in tr if r["pred"] == lb and r["label"] == lb)
            fp = sum(1 for r in tr if r["pred"] == lb and r["label"] != lb)
            fn = sum(1 for r in tr if r["pred"] != lb and r["label"] == lb)
            prec = tp / (tp + fp) if tp + fp else 0.0
            rec = tp / (tp + fn) if tp + fn else 0.0
            f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
        out["macro_f1"] = sum(f1s) / len(f1s)
        out["classes"] = labels
    if task == "severity":
        # 加权 Kappa(有序) + MAE
        obs = collections.Counter((r["label"], r["pred"]) for r in tr)
        lb_freq = collections.Counter(r["label"] for r in tr)
        pr_freq = collections.Counter(r["pred"] for r in tr)
        po = sum(obs[(s, s)] for s in SEVS) / n
        pe = sum(lb_freq[s] * pr_freq[s] for s in SEVS) / (n * n)
        w = sum(sum(obs[(a, b)] * (abs(SEVS.index(a) - SEVS.index(b)) / 3) ** 2
                    for b in SEVS) for a in SEVS) / n
        out["quadratic_kappa"] = 1 - (w / pe) if pe else None
        out["mae"] = sum(abs(SEVS.index(r["label"]) - SEVS.index(r["pred"])) for r in tr) / n
        by_sev = {s: {"n": lb_freq[s], "acc": sum(1 for r in tr if r["label"] == s and r["pred"] == s) / lb_freq[s]} for s in SEVS if lb_freq[s]}
        out["by_severity"] = by_sev
    return out


def ece_equifreq(pairs, bins=15):
    """等频 ECE: pairs=[(conf, correct)]"""
    if not pairs:
        return None
    pairs = sorted(pairs)
    n = len(pairs)
    e, curves = 0.0, []
    for b in range(bins):
        grp = pairs[b * n // bins:(b + 1) * n // bins if b < bins - 1 else n]
        if not grp:
            continue
        ac = sum(c for c, _ in grp) / len(grp)
        aa = sum(1 for _, ok in grp if ok) / len(grp)
        e += len(grp) / n * abs(ac - aa)
        curves.append({"conf": round(ac, 3), "acc": round(aa, 3), "n": len(grp)})
    return {"ece": round(e, 4), "reliability": curves}


def risk_coverage(rows, task="tactic"):
    """按置信度降序的 selective 曲线"""
    tr = sorted((r for r in rows if r["task"] == task and r.get("conf") is not None),
                key=lambda r: -r["conf"])
    if not tr:
        return []
    n = len(tr)
    out, err = [], 0
    for i, r in enumerate(tr, 1):
        err += 0 if r["correct"] else 1
        out.append({"coverage": i / n, "risk": err / i})
    return out


def tau_scan(rows, task="tactic", misaction_tasks=("action",)):
    """τ 扫描: conf≥τ 自动处置,否则 escalate;报告 (自动化率, 误处置率)"""
    tr = [r for r in rows if r["task"] == task and r.get("conf") is not None]
    if not tr:
        return []
    out = []
    for tau in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]:
        auto = [r for r in tr if r["conf"] >= tau]
        if not auto:
            continue
        wrong = sum(1 for r in auto if not r["correct"])
        out.append({"tau": tau, "automation_rate": len(auto) / len(tr), "misaction_rate": wrong / len(auto)})
    return out


def bootstrap_ci(rows, stat_fn, n_boot=1000, seed=42, alpha=0.05):
    """按 group 聚类 bootstrap(D3 决议)"""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r.get("group") or r["id"]].append(r)
    keys = list(groups)
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        sample = [r for k in (rng.choice(keys) for _ in range(len(keys))) for r in groups[k]]
        s = stat_fn(sample)
        if s is not None:
            stats.append(s)
    if not stats:
        return None
    stats.sort()
    return {"lo": stats[int(alpha / 2 * len(stats))], "hi": stats[int((1 - alpha / 2) * len(stats))]}


def analyze(rows, source_meta=None):
    result = {"n_rows": len(rows), "source": source_meta or ""}
    result["tasks"] = {t: task_metrics(rows, t) for t in TASKS}
    # exact match: 按 group 内四任务全对
    by_group = collections.defaultdict(dict)
    for r in rows:
        by_group[r["group"]][r["task"]] = r["correct"]
    full = [all(v.get(t) for t in TASKS if t in v) and len(v) >= 3 for v in by_group.values()]
    result["exact_match"] = sum(full) / len(full) if full else None
    # ECE / risk-coverage / tau(主要任务 tactic)
    for t in TASKS:
        pairs = [(r["conf"], r["correct"]) for r in rows if r["task"] == t and r.get("conf") is not None]
        if pairs:
            result.setdefault("ece", {})[t] = ece_equifreq(pairs)
            result.setdefault("risk_coverage", {})[t] = risk_coverage(rows, t)
            if t in ("tactic", "action"):
                result.setdefault("tau_scan", {})[t] = tau_scan(rows, t)
    # CI(关键指标)
    for t, key in (("tactic", "tactic_acc"), ("severity", "sev_acc"), ("urgent", "urgent_acc")):
        tr = [r for r in rows if r["task"] == t]
        ci = bootstrap_ci(tr, lambda s, t=t: (sum(bool(r["correct"]) for r in s) / len(s)) if s and all(r["correct"] is not None for r in s) else None)
        if ci:
            result.setdefault("ci", {})[key] = ci
    # E-3 难度梯度子集(id 前缀 e3)
    e3 = [r for r in rows if str(r["id"]).startswith(("e3", "range-windows-ssh-e3"))]
    if e3:
        e3u = [r for r in e3 if r["task"] == "urgent" and r["correct"] is not None]
        result["e3_subset"] = {
            "urgent_acc": (sum(bool(r["correct"]) for r in e3u) / len(e3u)) if e3u else None,
            "n": len({r["group"] for r in e3}),
        }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True, help="rows.json 或 results jsonl,逗号分隔可多个")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", help="可选 markdown 输出")
    a = ap.parse_args()
    rows = flat_rows([x.strip() for x in a.rows.split(",")])
    res = analyze(rows, source_meta=a.rows)
    Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    print(f"n_rows={res['n_rows']}  tactic={res['tasks']['tactic'].get('acc')}  "
          f"urgent={res['tasks']['urgent'].get('acc')}  sev={res['tasks']['severity'].get('acc')}  "
          f"exact={res['exact_match']}")
    if a.md:
        lines = ["| task | n | acc | 备注 |", "|---|---|---|---|"]
        for t, m in res["tasks"].items():
            note = []
            if t == "tactic" and "macro_f1" in m:
                note.append(f"macroF1={m['macro_f1']:.3f}")
            if t == "severity" and m.get("by_severity"):
                note.append(" ".join(f"{s}:{d['n']}/{d['acc']:.2f}" for s, d in m["by_severity"].items()))
            lines.append(f"| {t} | {m.get('n', 0)} | {m.get('acc', '—')} | {'; '.join(note)} |")
        lines.append(f"| exact | {len(res.get('ci', {}))} | {res['exact_match']} | |")
        Path(a.md).write_text("\n".join(lines) + "\n")
        print("markdown:", a.md)


if __name__ == "__main__":
    main()
