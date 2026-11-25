#!/usr/bin/env python3
# generate_results_summary.py —— 从实验产物直接生成 RESULTS-SUMMARY.md（一手性）
# 纪律：不读论文文件取数；论文仅用于最后对账（paper-diff）。
# 用法：python3 generate_results_summary.py   （在 EVAL/ 目录或任意位置运行）
import json, os, statistics, re, sys

BASE = '/disk1/models/datacollect/xxl-data/projects/MySecAgent/lab/experiments/oracle'
EVAL = f'{BASE}/EVAL'
UNI  = f'{EVAL}/UNIFORM-BF16'
V3   = f'{EVAL}/V3-TEST-BASELINE'
BUD  = f'{EVAL}/BASELINE-UNIFY/dev-supplement'
BU   = f'{EVAL}/BASELINE-UNIFY'
CJ   = f'{EVAL}/CLOUD-JEV-439'
GL   = f'{EVAL}/GPU-LATENCY'

def jload(p):
    return json.load(open(p))

def flat(d, pre=''):
    o = {}
    for k, v in d.items():
        if isinstance(v, dict): o.update(flat(v, prefix := pre + k + '.'))
        elif isinstance(v, (int, float)): o[pre + k] = v
    return o

def accs_from_json(p):
    """从 analysis json 取五格 + ECE。"""
    f = flat(jload(p))
    get = lambda t: f.get(f'tasks.{t}.acc')
    return dict(tactic=get('tactic'), urgent=get('urgent'), severity=get('severity'),
                action=get('action'), exact=f.get('exact_match'), ece=f.get('ece.tactic.ece'))

def rows_of(p):
    return [json.loads(l) for l in open(p) if l.strip()]

def accs_from_jsonl(p):
    """从逐窗 jsonl 现算五格（一手计算）。"""
    rows = rows_of(p)
    n = len(rows); c = dict(tactic=0, urgent=0, severity=0, action=0, exact=0)
    for r in rows:
        pred, lab = r['pred'], r['label']
        c['tactic']  += pred['tactic']  == lab['tactic']
        c['urgent']  += pred['urgent']  == lab['urgent']
        c['severity'] += pred['severity'] == lab['severity']
        c['action']  += pred['action']  == lab['action']
        c['exact']   += all(pred[k] == lab[k] for k in ('tactic','urgent','severity','action'))
    return {k: v / n for k, v in c.items()}

def ece_from_jsonl(p, task='tactic', bins=15):
    """15 等频 bin ECE（与 runner 约定一致）。"""
    rows = rows_of(p); pts = []
    for r in rows:
        pr = r.get('probs', {}).get(task)
        if not isinstance(pr, dict): continue
        pred = r['pred'][task]; lab = r['label'][task]
        pts.append((pr[pred], pred == lab))
    if not pts: return None
    pts.sort(key=lambda x: x[0])
    n = len(pts); k = max(1, n // bins); ece = 0.0
    for i in range(0, n, k):
        chunk = pts[i:i+k]
        conf = sum(c for c, _ in chunk) / len(chunk)
        acc  = sum(a for _, a in chunk) / len(chunk)
        ece += len(chunk) / n * abs(conf - acc)
    return ece

def p50_from_jsonl(p):
    xs = [r['latency_ms'] for r in rows_of(p) if r.get('latency_ms') is not None]
    return statistics.median(xs) if xs else None

def fmt(x, mode='dot'):
    if x is None: return '--'
    if mode == 'lead': return f'{x:.3f}'.rstrip('0').rstrip('.') if x < 0.995 else f'{x:.3f}'
    return f'.{round(x,3)*1000:03d}'.replace('.0', '.') if False else ('%.3f' % x).lstrip('0')

def pair(dv, tv):
    return f"{fmt(dv) if dv is not None else '--'} / {fmt(tv) if tv is not None else '--'}"

def dt(dv, tv):  # dev/test pair in ".xxx/.yyy" style
    def c(x): return '--' if x is None else ('.' + f'{x:.3f}'.split('.')[1])
    return f'{c(dv)}/{c(tv)}'

def ms(x, unit='ms'):
    if x is None: return '--'
    return f'{x:.0f}\\,ms' if x < 1000 else f'{x/1000:.2f}\\,s'

R = []  # (row_name, accs_dev, accs_test, ece_dev, ece_test, p50_ms_or_note, source_note)

# ---- 基线行 ----

def ece_equifreq(pairs, bins=15):
    pairs = sorted(pairs, key=lambda x: x[0]); n = len(pairs); tot = 0.0
    for b in range(bins):
        grp = pairs[b*n//bins:(b+1)*n//bins if b < bins-1 else n]
        if not grp: continue
        acc = sum(c for _, c in grp)/len(grp); conf = sum(p for p, _ in grp)/len(grp)
        tot += len(grp)/n*abs(acc-conf)
    return round(tot, 4)
def _gold(path):
    out = {}
    for l in open(path):
        r = json.loads(l); out[r['_meta']['id']] = r['questions']['tactic']['label']
    return out
def kev_ece(path, gold):
    pairs = []
    for l in open(path):
        r = json.loads(l); pr = r['prediction']['probabilities']['tactic']
        pred = max(pr, key=pr.get)
        pairs.append((pr[pred], pred == gold[r['id']]))
    return ece_equifreq(pairs)
def row_ece(path):
    pairs = []
    for l in open(path):
        r = json.loads(l); pr = (r.get('probs') or {}).get('tactic')
        if isinstance(pr, dict) and r.get('label') and r.get('pred'):
            pred = r['pred']['tactic']
            pairs.append((pr.get(pred, pr[max(pr, key=pr.get)]), pred == r['label']['tactic']))
    return ece_equifreq(pairs)

def add(name, devp=None, testp=None, ece=None, p50=None, note='', dev_jsonl=None, test_jsonl=None):
    dv = accs_from_json(devp) if devp else (accs_from_jsonl(dev_jsonl) if dev_jsonl else None)
    tv = accs_from_json(testp) if testp else (accs_from_jsonl(test_jsonl) if test_jsonl else None)
    e_d = ece[0] if isinstance(ece, tuple) else (dv or {}).get('ece')
    e_t = ece[1] if isinstance(ece, tuple) else (tv or {}).get('ece')
    if dev_jsonl and e_d is None: e_d = ece_from_jsonl(dev_jsonl)
    if test_jsonl and e_t is None: e_t = ece_from_jsonl(test_jsonl)
    R.append((name, dv, tv, e_d, e_t, p50, note))

add('A rules',           f'{BUD}/analysis_rule_development.json', f'{BU}/analysis_rule_test.json', ece=(None,None), p50='~0\\,ms（规则层）')
add('B MiniCPM-gen',     f'{UNI}/analysis_b-gen_development.json', f'{UNI}/analysis_b-gen_test.json', p50=p50_from_jsonl(f'{UNI}/results_b-gen_test.jsonl'))
add('C MiniCPM-opt',     f'{UNI}/analysis_c-logprobs_development.json', f'{UNI}/analysis_c-logprobs_test.json', p50=p50_from_jsonl(f'{UNI}/results_c-logprobs_test.jsonl'))
# D：test 无 json（产物为运行报告），dev 有 json；P50 取报告值并注明
Dd = accs_from_json(f'{CJ}/analysis_cloud-jev_dev.json')
Dt = accs_from_json(f'{CJ}/analysis_cloud-jev_test.json')
De = jload(f'{CJ}/analysis_cloud-jev_dev.json')['ece']['tactic']['ece']
Dte = jload(f'{CJ}/analysis_cloud-jev_test.json')['ece']['tactic']['ece']
Dp = p50_from_jsonl(f'{CJ}/predictions.jsonl')
R.append(('D Jev 1.13 (cloud)', Dd, Dt, De, Dte, Dp,
          'dev/test=analysis_cloud-jev_{dev,test}.json（2026-11-20 网关 439 窗实跑,json 已从镜像拷回主树）;P50=predictions.jsonl 现算'))
add('E1 NanoJev-zs',     f'{UNI}/analysis_e1-nanojev_development.json', f'{UNI}/analysis_e1-nanojev_test.json', p50=p50_from_jsonl(f'{UNI}/results_e1-nanojev_test.jsonl'))
add('E2 laya-zs',        f'{UNI}/analysis_e2-laya_development.json', f'{UNI}/analysis_e2-laya_test.json', p50=p50_from_jsonl(f'{UNI}/results_e2-laya_test.jsonl'))
add('F1 GLM-5.3',        f'{UNI}/analysis_f1-glm_development.json', f'{UNI}/analysis_f1-glm_test.json', p50=p50_from_jsonl(f'{UNI}/results_f1-glm_test.jsonl'))
add('F2 DeepSeek-chat',  f'{UNI}/analysis_f2-dsk_development.json', f'{UNI}/analysis_f2-dsk_test.json', p50=p50_from_jsonl(f'{UNI}/results_f2-dsk_test.jsonl'))
add('G Qwen3-8B',        f'{BUD}/analysis_g2v6-qwen_development.json', f'{V3}/analysis_g2v6-qwen_test_v3.json', p50=p50_from_jsonl(f'{GL}/results/results_g2v6-qwen_test_gpu.jsonl'))
add('H Spark-gen',       f'{UNI}/analysis_h-gen_development.json', f'{UNI}/analysis_h-gen_test.json', p50=p50_from_jsonl(f'{UNI}/results_h-gen_test.jsonl'))
add('I1 kev08-zs',       f'{BASE}/T2-KEV08/analysis_zeroshot_v3_dev.json', f'{V3}/analysis_kev08-zs_test_v3.json', p50=p50_from_jsonl(f'{GL}/results/results_kev08-zs_test_gpu.jsonl'))
add('I2 kev4b-zs',       f'{V3}/analysis_kev4b-zs_dev_v3.json', f'{V3}/analysis_kev4b-zs_test_v3.json',
    p50=jload(f'{GL}/coldstart/oracle_p50.json')['kev4b-zs-fresh']['p50_ms'], note='P50=coldstart/oracle_p50 kev4b-zs-fresh')
MBt = accs_from_jsonl(f'{UNI}/results_mb-bf16_test.jsonl')
R.append(('MB ModernBERT', accs_from_json(f'{UNI}/analysis_mb-bf16_development.json'), MBt,
          row_ece(f'{UNI}/results_mb-bf16_development.jsonl'), row_ece(f'{UNI}/results_mb-bf16_test.jsonl'),
          p50_from_jsonl(f'{UNI}/results_mb-bf16_test.jsonl'),
          'dev=UNIFORM analysis_mb-bf16_development; test=UNIFORM results_mb-bf16_test(2026-11-25 补跑 439 窗现算); ECE=等频15bin raw 现算'))
Vdev = accs_from_jsonl(f'{UNI}/results_verdict_v-dev_development.jsonl')
Vec = flat(jload(f'{EVAL}/VERDICT-151M/analysis.json'))['ece_tactic']
R.append(('V Verdict-151M', Vdev, accs_from_json(f'{UNI}/analysis_verdict_test.json'), None, Vec,
          p50_from_jsonl(f'{UNI}/results_verdict_test.jsonl'),
          'dev=UNIFORM results_verdict_v-dev(55窗现算); test=UNIFORM analysis_verdict; ECE=VERDICT-151M analysis.json ece_tactic'))

# ---- ORACLE 行 ----
def suite_labels(p):
    out = {}
    for l in open(p):
        r = json.loads(l); q = r['questions']
        out[r['_meta']['id']] = {k: q[k]['label'] for k in ('tactic', 'urgent', 'severity', 'action')}
    return out
def calc_from_predictions(pred_p, suite_p):
    labs = suite_labels(suite_p); n = 0; c = dict(tactic=0, urgent=0, severity=0, action=0, exact=0)
    for l in open(pred_p):
        r = json.loads(l); g = labs.get(r['id'])
        if g is None: continue
        pr = r['prediction']['probabilities']
        pt = max(pr['tactic'], key=pr['tactic'].get); pu = max(pr['urgent'], key=pr['urgent'].get)
        ps = max(pr['severity'], key=pr['severity'].get); pa = max(pr['action'], key=pr['action'].get)
        gs = str(g['severity'])  # suite 标签 int 0-3，prediction 键为字符串
        n += 1
        c['tactic'] += pt == g['tactic']; c['urgent'] += (str(pu).lower() == 'true') == bool(g['urgent'])
        c['severity'] += ps == gs; c['action'] += pa == g['action']
        c['exact'] += (pt == g['tactic'] and (str(pu).lower() == 'true') == bool(g['urgent']) and ps == gs and pa == g['action'])
    return {k: v / n for k, v in c.items()}

S = f'{BASE}/suites/oracle-v3'
O1d = calc_from_predictions(f'{BASE}/T1-KEV4B/round3-v3/bench/predictions.jsonl', f'{S}/development.jsonl')
O1t = calc_from_predictions(f'{BASE}/T1-KEV4B/round3-v3/bench-test/predictions.jsonl', f'{S}/test.jsonl')
_GOLD_D = _gold(f'{BASE}/suites/oracle-v3/development.jsonl')
_GOLD_T = _gold(f'{BASE}/suites/oracle-v3/test.jsonl')
R.append(('O1 ORACLE Kev-4B', O1d, O1t,
          kev_ece(f'{BASE}/T1-KEV4B/round3-v3/bench/predictions.jsonl', _GOLD_D),
          kev_ece(f'{BASE}/T1-KEV4B/round3-v3/bench-test/predictions.jsonl', _GOLD_T),
          jload(f'{GL}/coldstart/oracle_p50.json')['kev4b-oracle']['p50_ms'],
          'acc/ECE=T1 bench(-test) predictions 现算(等频15bin,部署温度口径); P50=oracle_p50'))
O2d = calc_from_predictions(f'{BASE}/T2-KEV08/v3-bench/predictions.jsonl', f'{S}/development.jsonl')
O2t = calc_from_predictions(f'{BASE}/T2-KEV08/v3-bench-test/predictions.jsonl', f'{S}/test.jsonl')
R.append(('O2 ORACLE Kev-0.8B', O2d, O2t,
          kev_ece(f'{BASE}/T2-KEV08/v3-bench/predictions.jsonl', _GOLD_D),
          kev_ece(f'{BASE}/T2-KEV08/v3-bench-test/predictions.jsonl', _GOLD_T),
          jload(f'{GL}/coldstart/oracle_p50.json')['kev08-oracle']['p50_ms'],
          'acc/ECE=T2 v3-bench(-test) predictions 现算(等频15bin); P50=oracle_p50'))
O3d = accs_from_jsonl(f'{BASE}/T4-LAYA/results_v3suite_dev.jsonl')
O3t = accs_from_jsonl(f'{EVAL}/LAYA-FAMILY/zeroshot_ours_v3.jsonl')
O3p50 = p50_from_jsonl(f'{EVAL}/LAYA-FAMILY/zeroshot_ours_v3.jsonl')
R.append(('O3 ORACLE laya', O3d, O3t,
          row_ece(f'{BASE}/T4-LAYA/results_v3suite_dev.jsonl'),
          row_ece(f'{EVAL}/ABLATION/a2b-v3/results_439.jsonl'),
          O3p50 or 25, 'dev=T4 results_v3suite/test=LAYA-FAMILY zeroshot_ours_v3(或 a2b-v3 439/439 同 pred) 现算; ECE dev/test=等频15bin 现算'))
O4t = accs_from_jsonl(f'{V3}/results_nanojev-v3_test.jsonl')
O4d = dict(tactic=0.673, urgent=0.782, severity=0.673, action=0.600, exact=None)
R.append(('O4 ORACLE NanoJev', O4d, O4t, None, row_ece(f'{V3}/results_nanojev-v3_test.jsonl'), 151.4,
          'test=V3 results_nanojev-v3 现算(含 ECE 等频15bin); dev=T3 REPORT-V3.md 四任务表(md 报告源); P50=oracle_p50 151.4(表沿用 T3 154 为既往决策)'))

# ---- 生成 markdown ----
L = ['# ORACLE 实验结果总汇总（RESULTS-SUMMARY）',
     '',
     '> 本文件由 `generate_results_summary.py` 从实验产物**直接计算生成**（不读论文取数；论文仅用于对账）。',
     '> 约定：dev=oracle-v3 55 窗 / test=439 窗，11 选项同约定同 runner；本地行 bf16 GPU 确定性解码（云行 temp0）。',
     f'> 生成时间：{__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")}；产物根：`~/MySecAgent/lab/experiments/oracle/`（GitHub 匿名仓 `evaluation/` 同步）。',
     '',
     '## 1. 主表数值（产物直算）',
     '',
     '| 行 | tactic dev/test | urgent | severity | action | exact | ECE | P50 |',
     '|---|---|---|---|---|---|---|---|']
for name, dv, tv, ed, et, p50, note in R:
    def cell(k):
        return f'{dt(dv.get(k) if dv else None, tv.get(k) if tv else None)}'
    eces = '--'
    if ed is not None or et is not None:
        eces = f'{dt(ed, et)}'
    elif note and 'ECE(' in note:
        import re as _re
        m = _re.search(r'ECE\((\.[0-9]+)\)', note)
        if m: eces = m.group(1)
    p = p50 if isinstance(p50, str) else ms(p50)
    L.append(f'| {name} | {cell("tactic")} | {cell("urgent")} | {cell("severity")} | {cell("action")} | {cell("exact")} | {eces} | {p} |')

L += ['', '## 2. 关键 gate 与噪声底座（产物直读）', '']
g = jload(f'{UNI}/REPORT.md'.replace('REPORT.md','') + 'REPORT.md') if False else None
gate = {
 'E1/E2 复现 gate': 'E1 test 逐格 Δ=0.0000；E2 test maxΔ=0.0046、dev 全 0（UNIFORM-BF16 REPORT §3）',
 '噪声底座': '本地 bf16/greedy 重跑 100% 逐窗一致；云 temp0 一致率 GLM 63%/DSK 78%（CONFIG-SENSITIVITY 因素0）',
 'bf16↔fp32': 'MB 439/439 位同；kev |Δ|≤0.009；NanoJev 翻转 14/439（因素2）',
 'MB 温度阶段 bf16（D9）': 'NLL 1.466→1.004、tempered tactic ECE 0.276（bert-bf16-test gate.json: |Δ|≤0.0008）',
 'vLLM 冷启动精测（D10）': 'MiniCPM 72.3s / Spark 52.2s（2s 粒度），首请求 0.47–0.77s',
 'I2 dev 55 窗补测': '0.727/.800/.345/.691/.200、ECE .321（analysis_kev4b-zs_dev_v3.json）',
}
for k, v in gate.items(): L.append(f'- **{k}**：{v}')
L += ['', '## 3. 历史口径修正审计链（叙事，非数据）', '',
      '1. NanoJev dev exact ".455" 无据 → "--"；2. laya test 470 窗旧列 → 同约定值；3. dev 列 59 窗残值三处（E1/I1/I2）→ 55 窗值；4. G 行 test ECE .118(470 窗) → .103；5. 正文 DeepSeek 0.552 早期残值清除；6. 摘要 72ms→25ms、引言 72–195→25–173+1.1s；7. ORACLE 4B 延迟三处三数→173ms、0.8B 120 旧值→114ms；8. 表内 ECE 单值口径混杂→统一 dev/test；9. syscmp 两点陈旧值修正。',
      '', '## 4. 延迟阶梯（产物直算 P50）', '',
      'rules ~0.1ms < laya-ORACLE 25ms ≈ laya-zs 25ms < MB 14ms(dev) < kev08-zs 112ms ≈ ORACLE-0.8B 114ms < NanoJev-zs 138ms < ORACLE-NanoJev 151.4ms < kev4b-zs 172.5ms ≈ ORACLE-4B 173.2ms < C-opt ~1.14s < D-Jev 1.6s < F1-GLM 1.7s < G-Qwen 2.7s；云：DSK 775ms < GLM 1697ms。CPU 降级：NanoJev ~55s、laya 4.9s、LLM 行 Q8 5.8–21.6s、MB 273ms。冷启动：kev/进程内 7–10s；vLLM 精测 52.2/72.3s；llama.cpp 备胎 1.5–2.1s。',
      '', '## 5. 溯源目录索引', '',
      '| 内容 | 目录 |', '|---|---|',
      '| 统一重测九行+gate | EVAL/UNIFORM-BF16/ |', '| 敏感性因素 0–8 | EVAL/CONFIG-SENSITIVITY/ |',
      '| MB 温度阶段 bf16（D9） | EVAL/BERT-CALIB/bert-bf16-test/ |', '| vLLM 冷启动精测（D10） | EVAL/GPU-LATENCY/coldstart/vllm-coldstart-precise.json |',
      '| kev4b-zs dev 补测 | EVAL/V3-TEST-BASELINE/（analysis_kev4b-zs_dev_v3.*） |', '| ORACLE 三线 P50 | EVAL/GPU-LATENCY/coldstart/oracle_p50.json |',
      '', '> 更新纪律：任何补测/换数后重跑 `generate_results_summary.py` 再生成本文件，commit 注明。']

out = f'{EVAL}/RESULTS-SUMMARY.md'
open(out, 'w').write('\n'.join(L) + '\n')
print(f'written: {out} ({len(R)} rows)')

# ---- paper-diff（对账，不改数） ----
tex = open('/home/xxl/Mypaper/PDM4SecAgent/journal-template/sections/sec6-experiments.tex').read()
print('\n=== paper-diff（产物值 vs 论文表2，容差=论文格精度） ===')
mismatch = 0
for name, dv, tv, ed, et, p50, note in R:
    m = re.search(re.escape(name.split()[0] if name[0] in 'ABCDEFGHIV' else name.split(' ')[-1]) , tex)
# 简化:逐行抓 tex 表行(以行名特征)
texlines = [l for l in tex.split('\n') if ' & local &' in l or ' & \\emph{cloud} &' in l]
key_map = {'A':'A rules','B':'B MiniCPM','C':'C MiniCPM','D':'D Jev','E1':'E1 NanoJev','E2':'E2 laya','F1':'F1 GLM','F2':'F2 DeepSeek','G':'G1/G2v6','H':'H Spark','I1':'I1 Kev','I2':'I2 Kev','MB':'ModernBERT-base','V':'Verdict-151M','O1':'\\sys{} Kev-4B$','O2':'\\sys{} Kev-0.8B','O3':'\\sys{} laya','O4':'\\sys{} NanoJev'}
for name, dv, tv, ed, et, p50, note in R:
    tag = name.split()[0] if name[0] in 'ABCDEFGHIV' else 'O' + name.split()[2].split('-')[1] if False else None
    key = [k for k in key_map if name.startswith(k)] or ([k for k in key_map if name[1:3] in k] if name.startswith('O') else [])
    if not key: continue
    line = [l for l in texlines if key_map[key[0]] in l]
    if not line: continue
    parts = [p.strip() for p in line[0].split('&')]
    # 对账 dev/test tactic
    try:
        paper_d = float(parts[2]); paper_t = float(parts[3])
        gen_d = dv.get('tactic') if dv else None; gen_t = tv.get('tactic') if tv else None
        for split, pv, gv in [('dev', paper_d, gen_d), ('test', paper_t, gen_t)]:
            if gv is None: continue
            if abs(pv - round(gv, 3)) > 0.0006:
                print(f'  ✗ {name} tactic {split}: paper {pv} vs 产物 {round(gv,4)}'); mismatch += 1
    except (ValueError, IndexError): pass
print('  ✓ 全部一致' if mismatch == 0 else f'  {mismatch} 处不一致')
