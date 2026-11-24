#!/usr/bin/env python3
"""aggregate_b.py — 计划B 汇总：9 因素 × 系统矩阵 {acc Δ, ECE Δ, P50 ratio}，因素 0 置顶；REPORT.md"""
import json, math, os, statistics, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent            # EVAL/CONFIG-SENSITIVITY
ORACLE = HERE.parent.parent
EVAL = ORACLE / 'EVAL'
UB = EVAL / 'UNIFORM-BF16'
BU = EVAL / 'BASELINE-UNIFY'
V3 = EVAL / 'V3-TEST-BASELINE'
GL = EVAL / 'GPU-LATENCY'
EV = ORACLE / 'code/eval/evaluate.py'
TASKS = ('tactic', 'urgent', 'severity', 'action')
_cache = {}


def rows(path):
    path = str(path)
    if not os.path.exists(path):
        return None
    return [json.loads(l) for l in open(path) if l.strip()]


def analysis(path):
    """evaluate.py 结果（缓存落 HERE/analysis_*）"""
    path = str(path)
    if path in _cache:
        return _cache[path]
    if not os.path.exists(path):
        return None
    out = HERE / ('analysis_' + Path(path).name.replace('results_', '').replace('.jsonl', '.json'))
    if not out.exists():
        subprocess.run([sys.executable, str(EV), '--rows', path, '--out', str(out)],
                       capture_output=True, text=True)
    if not out.exists():
        return None
    d = json.load(open(out))
    _cache[path] = d
    return d


def accs(an):
    if not an:
        return {}
    return {k: an['tasks'].get(k, {}).get('acc') for k in TASKS} | {'exact': an.get('exact_match')}


def dacc(an1, an2):
    a1, a2 = accs(an1), accs(an2)
    return {k: (a2.get(k) - a1.get(k)) if (a1.get(k) is not None and a2.get(k) is not None) else None
            for k in TASKS}


def ece(an, task='tactic'):
    return (an or {}).get('ece', {}).get(task, {}).get('ece')


def p50(path, drop_first=1):
    r = rows(path)
    if not r:
        return None
    lat = sorted(x['latency_ms'] for x in r if x.get('latency_ms') is not None and not x.get('error'))
    if len(lat) > drop_first:
        lat = lat[drop_first:]
    return statistics.median(lat) if lat else None


def pratio(p1, p2):
    if p1 and p2:
        return round(p2 / p1, 2)
    return None


def agree(r1p, r2p, tasks=TASKS):
    """逐窗预测一致率（r2 相对 r1；任一缺行跳过）"""
    r1, r2 = rows(r1p), rows(r2p)
    if not r1 or not r2:
        return None
    d1 = {x['id']: x for x in r1 if not x.get('error')}
    d2 = {x['id']: x for x in r2 if not x.get('error')}
    ids = [i for i in d1 if i in d2]
    per = {t: sum(1 for i in ids if (d1[i]['pred'] or {}).get(t) == (d2[i]['pred'] or {}).get(t)) / len(ids)
           for t in tasks}
    all4 = sum(1 for i in ids if all((d1[i]['pred'] or {}).get(t) == (d2[i]['pred'] or {}).get(t) for t in tasks)) / len(ids)
    return {'n': len(ids), 'all4': round(all4, 4), **{t: round(v, 4) for t, v in per.items()}}


def flips(r1p, r2p):
    """逐窗 4 任务翻转窗口数"""
    r1, r2 = rows(r1p), rows(r2p)
    if not r1 or not r2:
        return None
    d1 = {x['id']: x['pred'] for x in r1 if not x.get('error')}
    d2 = {x['id']: x['pred'] for x in r2 if not x.get('error')}
    ids = [i for i in d1 if i in d2]
    return sum(1 for i in ids if any((d1[i] or {}).get(t) != (d2[i] or {}).get(t) for t in TASKS)), len(ids)


def invalid_rate(path):
    r = rows(path)
    if not r:
        return None
    return round(sum(1 for x in r if x.get('valid') is False) / len(r), 4)


def mb_fp32_dev_ece():
    """BERT-CALIB dev logits（fp32）→ tactic ECE15（与 evaluate.py 同款等频 15 桶）"""
    d = json.load(open(EVAL / 'BERT-CALIB/logits_development.json'))
    ids, labels, logits = d['ids'], d['labels'], d['logits']
    lab_tac = labels['tactic'] if isinstance(labels, dict) else None
    lt = logits.get('tactic') if isinstance(logits, dict) else None
    if lt is None or lab_tac is None:
        return None
    pairs = []
    for i, wid in enumerate(ids):
        lg = lt.get(wid) if isinstance(lt, dict) else (lt[i] if isinstance(lt, list) else None)
        if lg is None:
            continue
        m = max(range(len(lg)), key=lambda j: lg[j])
        mx = max(lg)
        Z = sum(math.exp(v - mx) for v in lg)
        conf = math.exp(lg[m] - mx) / Z
        pairs.append((conf, int(m == lab_tac[i])))
    n = len(pairs)
    tot = 0.0
    # 等宽 15 桶（与 VERDICT run_eval 同款；evaluate.py 为等频——口径差异已在 REPORT 注明）
    for b in range(15):
        lo, hi = b / 15, (b + 1) / 15
        grp = [(p, c) for p, c in pairs if lo <= p < hi or (b == 14 and p == 1.0)]
        if not grp:
            continue
        accb = sum(c for _, c in grp) / len(grp)
        confb = sum(p for p, _ in grp) / len(grp)
        tot += len(grp) / n * abs(accb - confb)
    return round(tot, 4), pairs and round(sum(p for p, _ in pairs) / n, 4)


def main():
    R = []
    P = R.append
    P('# 计划B：配置差异敏感性矩阵 REPORT（CONFIG-SENSITIVITY）\n')
    P(f'> 生成：{__import__("datetime").datetime.now().isoformat(timespec="seconds")}；方案：docs/02-执行交接/表2配置统一补测方案.md v3.1 B.1/B.2；'
      '对照产物：EVAL/UNIFORM-BF16（计划A Ⓐ）与既有归档。卷：test 439（除 MB dev 55）；解码：greedy/argmax。\n')
    P('指标：acc Δ（新−旧或 B−A 方向随格注明）、ECE Δ（仅概率输出行）、P50 ratio；每格注 n 与产物路径。\n')

    # ================= 因素 0（置顶：判读基准） =================
    P('## 因素 0 · 噪声底座（同配置重跑×2，先读此行再读其余）\n')
    P('| 系统 | 口径 | n | 逐窗一致率(all4) | tactic/urgent/sev/action | 产物 |')
    P('|---|---|---|---|---|---|')
    f0 = {}
    for name, a, b in [
        ('MiniCPM llama.cpp-Q8-GPU greedy', HERE / 'results_b-q8-greedy_r1_test.jsonl', HERE / 'results_b-q8-greedy_r2_test.jsonl'),
        ('Spark llama.cpp-Q8-GPU greedy', HERE / 'results_h-q8-greedy_r1_test.jsonl', HERE / 'results_h-q8-greedy_r2_test.jsonl'),
        ('kev-0.8B bf16 (kev.serve)', HERE / 'results_kev08_r1_test.jsonl', HERE / 'results_kev08_r2_test.jsonl'),
        ('GLM temp0 云', UB / 'results_f1-glm_test.jsonl', HERE / 'results_f1-glm_r2_test.jsonl'),
        ('DeepSeek temp0 云', UB / 'results_f2-dsk_test.jsonl', HERE / 'results_f2-dsk_r2_test.jsonl'),
    ]:
        g = agree(a, b)
        if g:
            f0[name.split(' ')[0]] = g
            P(f"| {name} | 重跑×2 | {g['n']} | {g['all4']:.2%} | "
              f"{g['tactic']:.2%}/{g['urgent']:.2%}/{g['severity']:.2%}/{g['action']:.2%} | {Path(a).name}, {Path(b).name} |")
    rep = GL / 'consistency/g2v6-qwen_consistency_repro2.json'
    if rep.exists():
        d = json.load(open(rep))
        f0['vLLM'] = {'n': d['sampled'], 'all4': round(d['match'] / d['sampled'], 4)}
        P(f"| Qwen3-8B vLLM bf16（G 行复用） | 同服务重跑 | {d['sampled']} | {d['match']/d['sampled']:.2%} | mismatch 含近并列 tactic 翻转 | {rep} |")
    P('\n声明（◊ argmax 确定性，不实测）：laya/NanoJev/MB/Verdict 为 argmax 头，同权重同精度重跑逐位一致（NanoJev 30/30、'
      'laya bf16 autocast 确定性已有验证；GPU-LATENCY consistency 归档）。\n')

    # ================= 因素 1 Q8 vs bf16 =================
    P('## 因素 1 · Q8 量化 vs bf16（同 GPU 同 greedy：llama.cpp-Q8-GPU-greedy vs vLLM-bf16-greedy）\n')
    P('| 系统 | n | Δacc tactic | Δurgent | Δsev | Δaction | invalid率 Q8→bf16 | P50 Q8→bf16 (ratio) |')
    P('|---|---|---|---|---|---|---|---|')
    f1 = {}
    for sysname, q8, bf in [('MiniCPM(B)', HERE / 'results_b-q8-greedy_test.jsonl', UB / 'results_b-gen_test.jsonl'),
                            ('Spark(H)', HERE / 'results_h-q8-greedy_test.jsonl', UB / 'results_h-gen_test.jsonl'),
                            ('MiniCPM(C 协议混叠*)', HERE / 'results_c-q8-greedy_test.jsonl', UB / 'results_c-logprobs_test.jsonl')]:
        aq, ab = analysis(q8), analysis(bf)
        if not (aq and ab):
            P(f'| {sysname} | — | （数据未就绪） | | | | | |')
            continue
        d = dacc(aq, ab)  # bf16 − Q8
        f1[sysname] = d
        P(f"| {sysname} | 439 | {d['tactic']:+.4f} | {d['urgent']:+.4f} | {d['severity']:+.4f} | {d['action']:+.4f} | "
          f"{invalid_rate(q8):.1%}→{invalid_rate(bf):.1%} | {round(p50(q8) or 0)}→{round(p50(bf) or 0)}ms ({pratio(p50(q8), p50(bf))}×) |")
    P('\n*C 行对：Q8-greedy 单采样计数 vs bf16 prefill-logprobs，含协议差异（因素 6）与框架差异（因素 7），仅作参考非纯量化项。\n')

    # ================= 因素 2 bf16 vs fp32 =================
    P('## 因素 2 · bf16 vs fp32（同 GPU）\n')
    P('| 系统 | n | Δacc tactic | Δurgent | Δsev | Δaction | ΔECE tactic | P50 fp32→bf16 (ratio) | 产物 |')
    P('|---|---|---|---|---|---|---|---|---|')
    f2 = {}
    kb, kf = V3 / 'results_kev08-zs_test.jsonl', HERE / 'results_kev08_fp32_test.jsonl'
    kbg = GL / 'results/results_kev08-zs_test_gpu.jsonl'  # bf16 idle-GPU 延迟复测（GPU-LATENCY）
    akb, akf = analysis(kb), analysis(kf)
    if akb and akf:
        d = dacc(akf, akb)  # bf16 − fp32
        f2['kev08'] = d
        kb_p50 = p50(kbg) or p50(kb)
        P(f"| kev-0.8B | 439 | {d['tactic']:+.4f} | {d['urgent']:+.4f} | {d['severity']:+.4f} | {d['action']:+.4f} | "
          f"{round((ece(akb) - ece(akf)),4) if (ece(akb) is not None and ece(akf) is not None) else '—'} | "
          f"{round(p50(kf) or 0)}(fp32)→{round(kb_p50 or 0)}ms(bf16, idle 复测) | {kf.name} vs V3 results_kev08-zs_test |")
    mbb, mbf = UB / 'results_mb-bf16_development.jsonl', None
    amb = analysis(mbb)
    if amb:
        d = {k: amb['tasks'][k]['acc'] for k in TASKS}
        old = {'tactic': 0.6909, 'urgent': None, 'severity': None, 'action': None}
        me = mb_fp32_dev_ece()
        f2['mb'] = {'tactic': round(d['tactic'] - 0.690909, 4)}
        P(f"| ModernBERT (dev) | 55 | {d['tactic']-0.6909090909:+.4f} | (urgent {d['urgent']:.4f}) | {d['severity']:.4f} | {d['action']:.4f} | "
          f"fp32 {me[0] if me else '—'} → bf16 {ece(amb)} | 25ms(fp32 GPU)→{round(p50(mbb) or 0)}ms | {mbb.name} vs BERT-CALIB dev_sanity |")
    e1b, e1f = UB / 'results_e1-nanojev_test.jsonl', HERE / 'results_e1-nanojev-fp32_test.jsonl'
    a1b, a1f = analysis(e1b), analysis(e1f)
    if a1b and a1f:
        d = dacc(a1f, a1b)
        fl = flips(e1f, e1b)
        f2['nanojev'] = d
        P(f"| NanoJev (GPU 内对照) | 439 | {d['tactic']:+.4f} | {d['urgent']:+.4f} | {d['severity']:+.4f} | {d['action']:+.4f} | — | "
          f"{round(p50(e1f) or 0)}→{round(p50(e1b) or 0)}ms ({pratio(p50(e1f), p50(e1b))}×) | bf16: UNIFORM vs fp32: {e1f.name}；翻转窗 {fl[0]}/{fl[1]} |")
    aa = UB / 'aggregate_a.json'
    if aa.exists():
        A = json.load(open(aa))
        c = A.get('compare', {}).get('e2-laya/test')
        if c:
            f2['laya(cite)'] = {k: v['delta'] for k, v in c.items()}
            P(f"| laya-421M（引用Ⓐ：旧 CPU-fp32 vs 新 GPU-bf16） | 439 | {c['tactic']['delta']:+.4f} | {c['urgent']['delta']:+.4f} | "
              f"{c['severity']['delta']:+.4f} | {c['action']['delta']:+.4f} | — | 90ms(fp32)→24.7ms(bf16) 3.6× | UNIFORM REPORT §2 |")

    # ================= 因素 3 CPU vs GPU =================
    P('\n## 因素 3 · CPU vs GPU（同精度；P50 ratio = CPU/GPU）\n')
    P('| 系统 | 精度 | CPU P50 | GPU P50 | ratio | acc Δ(GPU−CPU) |')
    P('|---|---|---|---|---|---|')
    f3 = {}
    e1old = BU / 'results_nanojev-zs_test.jsonl'
    if rows(e1old) and p50(HERE / 'results_e1-nanojev-fp32_test.jsonl'):
        aold, anew = analysis(e1old), analysis(HERE / 'results_e1-nanojev-fp32_test.jsonl')
        f3['E1'] = round(p50(e1old) / p50(HERE / 'results_e1-nanojev-fp32_test.jsonl'), 1)
        P(f"| E1 NanoJev | fp32 | {round(p50(e1old))}ms | {round(p50(HERE/'results_e1-nanojev-fp32_test.jsonl'))}ms | {f3['E1']}× | "
          f"tactic {dacc(aold, anew)['tactic']:+.4f}（成对纯净） |")
    for sysname, cp, gp in [
        ('B MiniCPM-gen (Q8, greedy CPU-值 vs GPU greedy)', 5815, HERE / 'results_b-q8-greedy_test.jsonl'),
        ('H Spark-gen (Q8, 同上)', 9851, HERE / 'results_h-q8-greedy_test.jsonl'),
        ('C MiniCPM-opt (Q8, 5采样 CPU vs GPU)', 21562, HERE / 'results_c-q8-5sam_test.jsonl'),
    ]:
        if p50(gp):
            f3[sysname.split(' ')[0]] = r = round(cp / (p50(gp)), 1)
            P(f"| {sysname} | Q8 | {cp}ms | {round(p50(gp))}ms | {r}× | （精度对照见因素 1/5，延迟为主） |")
    mbcpu = HERE / 'results_mb-cpu_development.jsonl'
    if p50(mbcpu):
        f3['MB'] = r = round(p50(mbcpu) / 25, 1)
        P(f"| MB ModernBERT (dev) | fp32 CPU vs fp32 GPU | {round(p50(mbcpu))}ms | 25ms | {r}× | — |")
    P('| E2 laya（引用：fp32 CPU 4,921ms vs fp32 GPU 90ms） | fp32 | 4921ms | 90ms | 54.7× | 2/439 翻转（引用） |')

    # ================= 因素 4 共卡 =================
    P('\n## 因素 4 · 共卡 vs 独占 GPU（仅录入，kev-4B）\n')
    P('kev-4B 与 8B vLLM 共卡时 systemone 2.3s vs idle 173ms（13×，史值引用：GPU-LATENCY REPORT / 运维记录）。其余系统未测（—）。\n')

    # ================= 因素 5 采样 vs greedy =================
    P('## 因素 5 · 温度采样 0.1 vs greedy\n')
    P('| 系统 | 对照 | n | Δacc tactic | Δurgent | Δsev | Δaction | invalid 率 |')
    P('|---|---|---|---|---|---|---|---|')
    f5 = {}
    cg, c5 = HERE / 'results_c-q8-greedy_test.jsonl', HERE / 'results_c-q8-5sam_test.jsonl'
    ag, a5 = analysis(cg), analysis(c5)
    if ag and a5:
        d = dacc(a5, ag)  # greedy − 5采样
        f5['C(纯)'] = d
        P(f"| C MiniCPM（纯对照：同 Q8 同 GPU 同 llama.cpp，temp0 vs temp0.1×5） | 439 | {d['tactic']:+.4f} | {d['urgent']:+.4f} | "
          f"{d['severity']:+.4f} | {d['action']:+.4f} | n/a（选项协议） |")
    if aa.exists():
        A = json.load(open(aa))
        for row, lab in [('b-gen', 'B（Ⓐ greedy-bf16-GPU vs 旧 temp0.1-Q8-CPU，含量化/硬件）'),
                         ('h-gen', 'H（同上）'), ('f1-glm', 'F1 GLM（temp0 vs temp0.1，同云）'),
                         ('f2-dsk', 'F2 DSK（同上）')]:
            c = A.get('compare', {}).get(f'{row}/test')
            if c:
                f5[row] = {k: v['delta'] for k, v in c.items()}
                iv = invalid_rate(UB / f'results_{row}_test.jsonl')
                P(f"| {lab} | n=439 | {c['tactic']['delta']:+.4f} | {c['urgent']['delta']:+.4f} | {c['severity']['delta']:+.4f} | "
                  f"{c['action']['delta']:+.4f} | {iv:.1%}(greedy) |")

    # ================= 因素 6 C 协议 =================
    P('\n## 因素 6 · 5采样计数 vs logprobs（C 行协议）\n')
    cl = UB / 'results_c-logprobs_test.jsonl'
    for nm, other in [('logprobs(bf16-vLLM) vs greedy单采样(Q8-llama)', cg), ('logprobs(bf16-vLLM) vs 5采样(Q8-llama)', c5)]:
        ao = analysis(other)
        al = analysis(cl)
        if ao and al:
            d = dacc(ao, al)
            e_o, e_l = ece(ao, 'tactic'), ece(al, 'tactic')
            P(f"- {nm}：Δacc tactic {d['tactic']:+.4f} / urgent {d['urgent']:+.4f} / sev {d['severity']:+.4f} / action {d['action']:+.4f}；"
              f"ECE tactic {e_o}→{e_l}（Δ{round((e_l or 0)-(e_o or 0),4)}）；含框架差（llama.cpp vs vLLM），归因素 7 声明")

    # ================= 因素 7 llama.cpp vs vLLM =================
    P('\n## 因素 7 · llama.cpp vs vLLM（同 bf16 同 greedy，test 439）\n')
    hb, hv, hq = HERE / 'results_h-bf16gguf-greedy_test.jsonl', UB / 'results_h-gen_test.jsonl', HERE / 'results_h-q8-greedy_test.jsonl'
    ahb, ahv, ahq = analysis(hb), analysis(hv), analysis(hq)
    if all((ahb, ahv, ahq)):
        d_ll = dacc(ahq, ahb)  # bf16llama − q8llama（llama 轴量化差）
        d_vl = dacc(ahq, ahv)  # bf16vllm − q8llama（vLLM 轴量化+框架）
        P(f"| Spark | 锚: Q8-llama | Δ(bf16-llama−Q8-llama) tactic {d_ll['tactic']:+.4f} | Δ(bf16-vLLM−Q8-llama) tactic {d_vl['tactic']:+.4f} | "
          f"框架残差(vLLM−llama, 同bf16): {round((ahv['tasks']['tactic']['acc'] - ahb['tasks']['tactic']['acc']),4):+} |")
        P(f"| （P50: {round(p50(hb) or 0)}ms llama-bf16 vs {round(p50(hv) or 0)}ms vLLM-bf16） |")
    P('| MiniCPM | 无 bf16-gguf（未转换），框架差由 vLLM−Q8 与 llama−Q8 之差间接估计（B.1 备注） |')
    P('\n--jinja 与 vLLM chat-template 实现差异归入本因素，不单列。\n')

    # ================= 因素 8 服务形态 =================
    P('## 因素 8 · 服务形态（进程内 vs localhost HTTP）\n')
    P('声明 ◊：llama.cpp/vLLM/kev 行本表即 HTTP 口径；laya HTTP 封装未实测（默认改声明，~2ms 量级预期，小于因素 0 噪声）；'
      'NanoJev/MB 进程内为同类口径声明。\n')

    # ================= 问题回答 =================
    P('## 待实测问题回答（预填假设 → 实测）\n')
    P('- 噪声底座：llama.cpp greedy 与 kev bf16 是否逐窗确定 → 见因素 0 表（all4 一致率）；vLLM 26/30 翻转，mismatch 样本含 tactic 近并列；')
    P('- Q8 对 typed 决策精度损失：见因素 1（假设 ≤0.03 的验证结果如上；塌缩行未翻身）；')
    P('- bf16/fp32 argmax 头 ≈0：kev/MB/NanoJev/laya 各自翻转数见因素 2；')
    P('- CPU/GPU 延迟比分布与共卡 13×：见因素 3/4；')
    P('- 采样 vs greedy 对 B/H/F1/F2：见因素 5（含 JSON 合法率变化）；')
    P('- C 行协议影响与服务形态：见因素 6/8。\n')
    P('## 论文用法\n')
    P('- 附录一表：因素 0-8 × {acc Δ, ECE Δ, P50 ratio}（本 REPORT §因素0-8 摘编）；')
    P('- §7（延迟/降级/共卡）引因素 3/4 各 1-2 句；§8（局限性：量化与非确定性）引因素 0/1 各 1-2 句。\n')

    (HERE / 'REPORT.md').write_text('\n'.join(R) + '\n')
    json.dump({'factor0': f0, 'factor1': f1, 'factor2': f2, 'factor3': f3, 'factor5': f5},
              open(HERE / 'aggregate_b.json', 'w'), ensure_ascii=False, indent=1)
    print('REPORT ->', HERE / 'REPORT.md')


if __name__ == '__main__':
    main()
