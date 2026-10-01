#!/usr/bin/env python3
"""置信门 + Tier 3 人工 CLI + 审计日志

门控（论文 §4.3，逐题型）：
  conf ≥ τ (0.90)         → auto（白名单动作自动执行[dry-run 模拟]，no_action/monitor 直接过）
  τ_h (0.70) ≤ conf < τ   → confirm（Tier 3 叙述 + y/n 人工确认）
  conf < τ_h              → escalate（问题升级 Tier 2 重打分；仍低 → Tier 3 人工队列）

窗口级路由：任一题 <τ 即整窗升级 Tier 2（对齐论文"escalates whole"），
升级后逐题重新门控；Tier 2 后仍 <τ_h 的题进 Tier 3 人工。
"""
import datetime
import json
import os

TAU = 0.90
TAU_H = 0.70
AUTO_ACTIONS = {"block_ip", "disable_user", "isolate_host", "reset_credentials",
                "quarantine_message", "monitor", "no_action"}  # escalate 永不自动


def gate(conf, tau=TAU, tau_h=TAU_H):
    if conf >= tau:
        return "auto"
    if conf >= tau_h:
        return "confirm"
    return "escalate"


def gate_all(answers, tau=TAU, tau_h=TAU_H):
    return {q: gate(a["conf"], tau, tau_h) for q, a in answers.items()}


def needs_tier2(gates):
    return any(g == "escalate" for g in gates.values())


# ---------------- Tier 3 人工 CLI ----------------
EVIDENCE_TEMPLATES = {
    "bruteforce_rate": "同源 IP 高速登录失败（凭据填充）",
    "bruteforce_success": "多次失败后出现成功登录——疑似爆破得手",
    "password_spray": "多用户少量失败——密码喷洒模式",
    "privesc_su_pattern": "su/sudo 失败模式——疑似提权尝试",
    "implanted_key_login": "失败后 publickey 登录——疑似植入密钥持久化",
    "webscan": "短时大量 4xx——Web 扫描/目录爆破",
    "local_bruteforce": "本地账户高频认证失败——疑似本地爆破/提权",
}


def narrate(window, tier2_out=None, rule_out=None):
    """证据叙述（模板拼装；生成式叙述后续接 Spark）+ 建议动作"""
    st = window.get("window_stats", {})
    lines = [f"窗口 {window['id']}（场景 {window.get('scenario')}/{window.get('kind')}，源 {window.get('source')}）"]
    lines.append(f"统计: n_lines={st.get('n_lines')} failed_logins={st.get('failed_logins')} "
                 f"accepted_logins={st.get('accepted_logins')} unique_users={st.get('unique_users')} "
                 f"unique_src_ips={st.get('unique_src_ips')} http_4xx={st.get('http_4xx')}")
    if rule_out:
        lines.append(f"[Tier0 规则] {rule_out['rule_id']} → "
                     f"{EVIDENCE_TEMPLATES.get(rule_out['rule_id'].split('(')[0], '规则命中')}")
    src = tier2_out or {}
    for layer, out in (("Tier1", src.get("tier1")), ("Tier2", out if False else src.get("tier2"))):
        if not out:
            continue
        lines.append(f"[{layer}] " + " | ".join(
            f"{q}={a['pred']} (conf {a['conf']:.2f})" for q, a in out["answers"].items()))
    if src.get("tier2"):
        action = src["tier2"]["answers"]["action"]
        lines.append(f"建议动作: {action['pred']}（重层置信 {action['conf']:.2f}）")
    elif src.get("tier1"):
        action = src["tier1"]["answers"]["action"]
        lines.append(f"建议动作: {action['pred']}（轻层置信 {action['conf']:.2f}）")
    return "\n".join(lines)


def human_confirm(text, suggestion, non_interactive="y"):
    """CLI y/n。非交互模式（默认批准/拒绝可配）供批量验收跑。"""
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)
    if non_interactive in ("y", "n"):
        print(f"[non-interactive] auto-answer: {non_interactive}")
        return non_interactive == "y"
    while True:
        ans = input(f"执行建议动作 [{suggestion}] ? (y/n) ").strip().lower()
        if ans in ("y", "n"):
            return ans == "y"


# ---------------- 审计日志 ----------------
class AuditLog:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def append(self, **kw):
        rec = {"ts": datetime.datetime.now().isoformat(timespec="milliseconds")}
        rec.update(kw)
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec
