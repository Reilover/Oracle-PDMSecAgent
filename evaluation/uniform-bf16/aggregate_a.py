#!/usr/bin/env python3
"""aggregate_a.py — 计划A 汇总：evaluate.py 全量指标 + P50 + 新旧逐格对照 + E1/E2 gate + REPORT.md"""
import json, os, statistics, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
ORACLE = HERE.parent.parent
EVAL = ORACLE / 'EVAL'
BU = EVAL / 'BASELINE-UNIFY'
V3 = EVAL / 'V3-TEST-BASELINE'
DEV = BU / 'dev-supplement'
EV = ORACLE / 'code/eval/evaluate.py'
OUTDIR = HERE

TASKS = ('tactic', 'urgent', 'severity', 'action')

# row -> 旧产物（test, dev）
OLD = {
    'e2-laya': (BU / 'analysis_laya-zs_test.json', DEV / 'analysis_laya-zs_development.json'),
    'e1-nanojev': (BU / 'analysis_nanojev-zs_test.json', DEV / 'analysis_nanojev-zs_development.json'),
    'c-logprobs': (BU / 'analysis_minicpm-opt_test.json', DEV / 'analysis_minicpm-opt_development.json'),
    'b-gen': (BU / 'analysis_minicpm-gen_test.json', DEV / 'analysis_minicpm-gen_development.json'),
    'h-gen': (BU / 'analysis_spark-gen_test.json', DEV / 'analysis_spark-gen_development.json'),
    'f1-glm': (V3 / 'analysis_glm_test_v3.json', DEV / 'analysis_glm_development.json'),
    'f2-dsk': (V3 / 'analysis_dsk_test_v3.json', DEV / 'analysis_dsk_development.json'),
}
ROW_DESC = {
    'e2-laya': 'E2 laya-zs GPU bf16（旧:CPU fp32）',
    'e1-nanojev': 'E1 NanoJev-zs GPU bf16（旧:CPU fp32）',
    'c-logprobs': 'C MiniCPM-opt prefill-logprobs vLLM bf16 temp0（旧:Q8+5采样计数+CPU temp0.1）',
    'b-gen': 'B MiniCPM-gen vLLM bf16 greedy（旧:Q8+temp0.1+CPU）',
    'h-gen': 'H Spark-gen vLLM bf16 greedy（旧:Q8+temp0.1+CPU）',
    'f1-glm': 'F1 GLM-5.3 云 temp0（旧:temp0.1）',
    'f2-dsk': 'F2 DeepSeek 云 temp0（旧:temp0.1）',
    'mb-bf16': 'MB ModernBERT GPU bf16（旧:GPU fp32, BERT-CALIB）',
    'verdict': 'V Verdict-151M（本目录新测 P50；旧产物无延迟）',
}
GATE_ROWS = ('e1-nanojev', 'e2-laya')
GATE = 0.01


def run_eval(res):
    out = OUTDIR / res.name.replace('results_', 'analysis_').replace('.jsonl', '.json')
    md = out.with_suffix('.md')
    r = subprocess.run([sys.executable, str(EV), '--rows', str(res), '--out', str(out), '--md', str(md)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f'[evaluate FAIL] {res}: {r.stderr[-300:]}')
        return None, None
    return json.load(open(out)), out


def accs(analysis):
    if not analysis:
        return {}
    t = analysis.get('tasks', {})
    d = {k: t.get(k, {}).get('acc') for k in TASKS}
    d['exact'] = analysis.get('exact_match')
    return d


def p50(res_path, drop_first=1):
    rows = [json.loads(l) for l in open(res_path)]
    lat = [r['latency_ms'] for r in rows if r.get('latency_ms') is not None and not r.get('error')]
    lat.sort()
    if len(lat) > drop_first:
        lat = lat[drop_first:]
    return (statistics.median(lat) if lat else None), len(lat)


def main():
    report = []
    summary = {}
    fails = []
    files = sorted(OUTDIR.glob('results_*_*.jsonl'))
    for res in files:
        stem = res.name.replace('results_', '').replace('.jsonl', '')
        parts = stem.rsplit('_', 1)
        method, split = parts[0], parts[1]
        an, anpath = run_eval(res)
        if an is None:
            fails.append(f'{res}: evaluate.py 失败')
            continue
        med, n = p50(res)
        e = summary.setdefault(method, {})
        e[split] = {'accs': accs(an), 'p50_ms': round(med, 1) if med else None, 'n': an.get('n_rows'),
                    'analysis': str(anpath), 'results': str(res)}
        print(f'{method}/{split}: n={an["n_rows"]} tactic={an["tasks"]["tactic"]["acc"]:.4f} '
              f'urgent={an["tasks"]["urgent"]["acc"]:.4f} sev={an["tasks"]["severity"]["acc"]:.4f} '
              f'act={an["tasks"]["action"]["acc"]:.4f} exact={an["exact_match"]:.4f} P50={med and round(med,1)}ms')

    # 新旧对照
    comp = {}
    for method, (oldt, oldd) in OLD.items():
        for split, oldp in (('test', oldt), ('development', oldd)):
            new = summary.get(method, {}).get(split)
            if not new or not oldp or not oldp.exists():
                continue
            old = json.load(open(oldp))
            oa = accs(old)
            na = new['accs']
            comp[f'{method}/{split}'] = {k: {'old': oa.get(k), 'new': na.get(k),
                                             'delta': (na.get(k) - oa.get(k)) if (na.get(k) is not None and oa.get(k) is not None) else None}
                                         for k in TASKS + ('exact',)}
    # E1/E2 gate
    gate_res = {}
    for method in GATE_ROWS:
        for split in ('test', 'development'):
            c = comp.get(f'{method}/{split}')
            if not c:
                continue
            worst = max((abs(v['delta']) for v in c.values() if v['delta'] is not None), default=0)
            gate_res[f'{method}/{split}'] = {'max_abs_delta': worst, 'pass': worst <= GATE}
            if worst > GATE:
                fails.append(f'GATE {method}/{split} max|Δ|={worst:.4f} > {GATE}')
    # mb 旧值（BERT-CALIB dev）
    mbold = EVAL / 'BERT-CALIB/bert_calib_result.json'
    if mbold.exists() and summary.get('mb-bf16', {}).get('development'):
        bc = json.load(open(mbold))
        summary['mb-bf16']['development']['bert_calib_old'] = bc
    json.dump({'summary': summary, 'compare': comp, 'gate': gate_res},
              open(OUTDIR / 'aggregate_a.json', 'w'), ensure_ascii=False, indent=1)

    # REPORT.md
    R = report.append
    R('# 计划A：表2统一重测 REPORT（UNIFORM-BF16）\n')
    R(f'> 生成：{__import__("datetime").datetime.now().isoformat(timespec="seconds")}；方案：docs/02-执行交接/表2配置统一补测方案.md v3.1\n')
    R('统一口径：同 runner（run_uniform.py，协议模板逐字复用 baseline_unify_runner/v3_baseline_runner）、'
      '同 55/439 卷（oracle-v3 development/test）、同 11 选项约定、idle GPU0、bf16 原生权重、'
      '确定性解码（greedy/prefill-logprobs/argmax）；精度格与延迟格同一次运行（latency_ms 逐窗记录）。\n')
    R('## 1. 新测结果（test + dev）\n')
    R('| 行 | split | n | tactic | urgent | severity | action | exact | P50(ms) |')
    R('|---|---|---|---|---|---|---|---|---|')
    for method in ('e2-laya', 'e1-nanojev', 'mb-bf16', 'verdict', 'c-logprobs', 'b-gen', 'h-gen', 'f1-glm', 'f2-dsk'):
        for split in ('test', 'development'):
            e = summary.get(method, {}).get(split)
            if not e:
                continue
            a = e['accs']
            fm = lambda v: f'{v:.4f}' if isinstance(v, float) else ('—' if v is None else v)
            R(f"| {method} | {split} | {e['n']} | {fm(a.get('tactic'))} | {fm(a.get('urgent'))} | "
              f"{fm(a.get('severity'))} | {fm(a.get('action'))} | {fm(a.get('exact'))} | {e['p50_ms'] if e['p50_ms'] else '—'} |")
    R('\n注：P50 为逐窗 latency_ms 中位数（剔除首窗暖机）；c-logprobs/b-gen 延迟含整窗 4 任务打分/生成；'
      'f1/f2 为云 API 整窗单次调用墙钟（网络口径声明保留）。\n')
    R('## 2. 新旧逐格对照（acc）\n')
    R('| 行/split | task | 旧 | 新 | Δ |')
    R('|---|---|---|---|---|')
    for key, c in comp.items():
        for k, v in c.items():
            fm = lambda x: f'{x:.4f}' if isinstance(x, float) else str(x)
            R(f"| {key} | {k} | {fm(v['old'])} | {fm(v['new'])} | {v['delta']:+.4f} |" if v['delta'] is not None
              else f"| {key} | {k} | {fm(v['old'])} | {fm(v['new'])} | — |")
    R('\n## 3. E1/E2 验收 gate（|Δ|≤0.01）\n')
    R('| 行/split | max abs Δ | 判定 |')
    R('|---|---|---|')
    for k, v in gate_res.items():
        R(f"| {k} | {v['max_abs_delta']:.4f} | {'PASS' if v['pass'] else '**FAIL**'} |")
    cs = OUTDIR / 'coldstart.json'
    if cs.exists():
        R('\n## 4. 冷启动（launch→ready / launch→首行落盘）\n')
        R('```json\n' + json.dumps(json.load(open(cs)), ensure_ascii=False, indent=1) + '\n```')
    R('\n## 5. 差异归因（衔接计划B）\n')
    R('- B/H：Q8量化+temp0.1采样+CPU → bf16+greedy+GPU vLLM（量化/解码/框架三因素，见 CONFIG-SENSITIVITY 因素1/5/7 分解）；')
    R('- C：协议本身更换（5采样计数→prefill-logprobs，因素6）叠加 B/H 同款三因素；')
    R('- E1/E2：精度迁移 fp32→bf16（因素2，已知近并列翻转率 2/439 量级）+硬件 CPU→GPU（因素3）；')
    R('- F1/F2：仅解码 temp0.1→temp0（因素5 云侧）；D/G/I/O/A 行不动。\n')
    if fails:
        R('## ⚠ 异常清单\n')
        for f in fails:
            R(f'- {f}')
    (OUTDIR / 'REPORT.md').write_text('\n'.join(report) + '\n')
    print('\nREPORT ->', OUTDIR / 'REPORT.md')
    for f in fails:
        print('FAIL:', f)


if __name__ == '__main__':
    main()
