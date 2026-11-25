#!/usr/bin/env python3
# check_paper_consistency.py —— 论文数字一致性总闸
# 用法：python3 check_paper_consistency.py   （需在 EVAL/ 下）
# 退出码 0=全绿；非 0=有不一致（输出逐条明细）
#
# 三层防线：
#   L1 表 2：19 行 × 13 列逐格数值对账（产物直算值 vs 论文格）+ 粗体=每列全系统最优校验
#   L2 图：fig4（accuracy-latency）与 fig:syscmp 的每个数据点 vs 产物值
#   L3 正文绊线：论文正文/摘要/脚注中每个实验数字以"精确字符串"钉死——任何编辑改动该数即报警，
#      修改时必须同步更新本登记并给出产物依据
import json, re, sys, os, subprocess

BASE = '/disk1/models/datacollect/xxl-data/projects/MySecAgent/lab/experiments/oracle'
EVAL = f'{BASE}/EVAL'
TEX  = '/home/xxl/Mypaper/PDM4SecAgent/journal-template'
FIGS = '/home/xxl/Mypaper/PDM4SecAgent/figures_src'
SEC  = {n: open(f'{TEX}/sections/{n}.tex').read() for n in
        ['sec1-intro','sec2-related','sec3-formulation','sec4-architecture',
         'sec5-training','sec6-experiments','sec789-tail']}
MAIN = open(f'{TEX}/main.tex').read()

has_bold = lambda s: '\\textbf{' in s
fails = []
def bad(msg): fails.append(msg); print('  ✗', msg)
def ok(msg):  print('  ✓', msg)

# ---------- 0. 产物真值（复用生成器） ----------
ns = {'__name__': '__gen__'}
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(open(f'{EVAL}/generate_results_summary.py').read(), 'gen', 'exec'), ns)
R = ns['R']  # 18 行: (name, dev_accs, test_accs, ece_dev, ece_test, p50, note)

# 消融行(第19行): BATCH2 两种子均值
abl = {}
for s in ['1', '2']:
    f = json.load(open(f'{EVAL}/BATCH2-TRAIN/seed{s}-test/analysis_test_methodA.json'))
    for k in ['tactic', 'urgent', 'severity', 'action']:
        abl.setdefault(k, []).append(f['tasks'][k]['acc'])
    abl.setdefault('exact', []).append(f['exact_match'])
ABL = {k: sum(v) / 2 for k, v in abl.items()}

# ---------- L1: 表 2 逐格对账 ----------
print('== L1 表 2 逐格对账 ==')
tex6 = SEC['sec6-experiments']
lines = [l for l in tex6.split('\n') if (' & local &' in l or ' & \\emph{cloud} &' in l) and '\\\\' in l]
rowkey = {'A rules':'A','B Mini':'B','C Mini':'C','D Jev':'D','E1':'E1','E2':'E2',
          'F1':'F1','F2':'F2','G1':'G','H Spark':'H','I1':'I1','I2':'I2','ModernBERT':'MB','Verdict':'V',
          'Kev-4B}$':'O1','Kev-0.8B}$':'O2','laya 421M}$':'O3','NanoJev}$':'O4','sys{} laya':'O3','sys{} NanoJev':'O4','w/o':'ABL'}
gen = {}
for name, dv, tv, ed, et, p50, note in R:
    gen[name.split()[0]] = (dv, tv, ed, et, p50)

def cellv(s):
    s = s.replace('\\textbf{','').replace('$^{\\P}$','').replace('$^{\\parallel}$','').replace('$^{\\ddagger}$','').replace('}','').replace('\\,','')
    s = s.replace('\\,ms','').replace('\\,s','').replace('~','').strip()
    return [None if ('--' in x or not x.replace('.','').isdigit()) else float(x) for x in s.split('/')]
def has_bold(s): return '\\textbf{' in s

n_cells = n_bold = 0
tabrows = {}
for l in lines:
    p = [x.strip() for x in l.split('&')]
    key = next((v for k, v in rowkey.items() if k in l), None)
    if key is None: continue
    tabrows[key] = p
    if key == 'ABL':
        for i, task in enumerate(['tactic','urgent','severity','action','exact']):
            cell = p[3] if i == 0 else p[3 + i]
            cv = cellv(cell)
            got = cv[0] if i == 0 else (cv[1] if len(cv) > 1 else None)
            exp = ABL[task]
            if got is None or abs(got - exp) > 6e-4: bad(f'ABL {task}: 表 {got} vs 产物 {round(exp,4)}')
            else: n_cells += 1
        continue
    dv, tv, ed, et, p50 = gen[key]
    cells = {'tactic_d': (cellv(p[2])[0], dv and dv.get('tactic')),
             'tactic_t': (cellv(p[3])[0], tv and tv.get('tactic'))}
    for j, f in enumerate(['urgent','severity','action','exact']):
        cs = cellv(p[4 + j])
        cells[f + '_d'] = (cs[0], dv and dv.get(f))
        cells[f + '_t'] = (cs[1], tv and tv.get(f))
    ec = cellv(p[8])
    cells['ece_d'] = (ec[0], ed if ed is not None else et)
    cells['ece_t'] = (ec[1] if len(ec) > 1 else ec[0], et if et is not None else ed)
    for cname, (paper, art) in cells.items():
        if paper is None and art is None: continue
        if (paper is None) != (art is None):
            bad(f'{key} {cname}: 表={paper} 产物={art}'); continue
        if abs(paper - art) > 6e-4:
            bad(f'{key} {cname}: 表 {paper} vs 产物 {round(art, 4)}')
        else: n_cells += 1
    # P50
    ptxt = p[9].replace('\\textbf{','').replace('}','').replace('$^{\\P}$','').strip()
    pv = None
    m = re.match(r'~?(\\sim)?([\\d.]+)\\s*(\\\\,)?(ms|s)', ptxt) or re.match(r'([\\d.]+)', ptxt.replace('\\,',''))
    m2 = re.search(r'([\\d.]+)\\,?(ms|s)?', ptxt.replace('\\',''))
    if m2 and m2.group(1).replace('.','').isdigit():
        pv = float(m2.group(1)) * (1000 if (m2.group(2) == 's' and float(m2.group(1)) < 10) else 1)
    if isinstance(p50, (int, float)) and pv is not None:
        if abs(pv - p50) > (5 if pv >= 100 else 1.5):
            bad(f'{key} P50: 表 {pv} vs 产物 {round(p50,1)}')
        else: n_cells += 1
ok(f'表格数值 {n_cells} 格对账')

# 粗体=每列全系统最优(消融行除外)
print('== L1b 粗体校验 ==')
def colbest(rows, idx, mode='max'):
    flat = []
    for k, p in rows.items():
        if k == 'ABL': continue
        c = cellv(p[idx])
        if len(c) > 0 and c[0] is not None: flat.append((c[0], has_bold(p[idx].split('/')[0]), k))
    bv = (max if mode == 'max' else min)(x[0] for x in flat)
    return [(v, b, k) for v, b, k in flat if (abs(v - bv) < 5e-4) != b]
sev_bold_err = []
for idx in [4, 5, 6, 7, 8]:
    for sub in [0, 1]:
        errs = []
        for k, p in tabrows.items():
            if k == 'ABL': continue
            c = cellv(p[idx])
            if len(c) <= sub or c[sub] is None: continue
            flat = [(cellv(pp[idx])[sub], has_bold(pp[idx].split('/')[sub])) for kk, pp in tabrows.items()
                    if kk != 'ABL' and len(pp[idx].split('/')) > sub and len(cellv(pp[idx])) > sub and cellv(pp[idx])[sub] is not None]
            bv = (min if idx == 8 else max)(x[0] for x in flat)
            if (abs(c[sub] - bv) < 5e-4) != has_bold(p[idx].split('/')[sub]):
                errs.append(f'{k}[{sub}]')
        sev_bold_err += errs
if sev_bold_err: [bad(f'粗体: {e}') for e in sev_bold_err]
else: ok('13 列粗体=全系统最优')

# ---------- L2: 图数据点对账 ----------
print('== L2 图数据点 ==')
f4 = open(f'{FIGS}/plot_accuracy_latency_v3.py').read()
pts = re.findall(r"\(([\d.]+),\s*([\d.]+),\s*'(\w+)',\s*'([^']+)'", f4)
exp_map = {}
for name, dv, tv, ed, et, p50, note in R:
    k = name.split()[0] if name[0] in 'ABCDEFGHIV' else name[:2]
    exp_map[k] = (tv and tv.get('tactic'), p50 if isinstance(p50, (int, float)) else None)
name2key = {'Rule':'A','Rule engine':'A','Rules':'A','Kev-0.8B (zs)':'I1','Kev-4B (zs)':'I2',
            'laya-421M (zs)':'E2','NanoJev-0.6B (zs)':'E1','Qwen3-8B (gen)':'G','Qwen3-8B':'G',
            'Spark-X2.5-4B (gen)':'H','Spark (gen)':'H','MiniCPM-2B (gen)':'B','MiniCPM-2B (opt)':'C',
            'GLM-5.3 (cloud)':'F1','GLM-5.3':'F1','DeepSeek (cloud)':'F2','DeepSeek-chat':'F2',
            'Jev 1.13 (cloud)':'D','ORACLE laya-421M':'O3','ORACLE Kev-0.8B':'O2',
            'ORACLE Kev-4B':'O1','ORACLE NanoJev-0.6B':'O4','ORACLE NanoJev':'O4','Verdict-151M':'V'}
nfig = 0
for lat, acc, mk, name in pts:
    k = name2key.get(name)
    if not k: bad(f'fig4 未知点 {name}'); continue
    e_acc, e_lat = exp_map[k]
    if e_acc is not None and abs(float(acc) - round(e_acc, 3)) > 1e-3: bad(f'fig4 {name} acc {acc} vs {round(e_acc,3)}')
    if e_lat is not None and abs(float(lat) - e_lat) > 6: bad(f'fig4 {name} lat {lat} vs {round(e_lat,1)}')
    nfig += 1
sc = open(f'{FIGS}/plot_system_comparison.py').read()
pts2 = re.findall(r"\((0\.\d+),\s*(0\.\d+),\s*'([^']+)'", sc)
for tac, ex, name in pts2:
    k = name2key.get(name)
    if not k: bad(f'syscmp 未知点 {name}'); continue
    e_acc, _ = exp_map[k]
    if e_acc is not None and abs(float(tac) - round(e_acc, 3)) > 1e-3: bad(f'syscmp {name} tac {tac} vs {round(e_acc,3)}')
    nfig += 1
ok(f'图数据点 {nfig} 个对账')

# ---------- L3: 正文数字绊线登记 ----------
print('== L3 正文数字绊线 ==')
WIRE = [
 # (label, 文件, 精确字符串)
 ('摘要-最强线', MAIN, 'reaches 0.85 tactic'),
 ('摘要-最快线', MAIN, '25\\,ms per decision'),
 ('引言-双值', SEC['sec1-intro'], '25--173\\,ms per model-tier decision'),
 ('引言-全管线', SEC['sec1-intro'], 'full-pipeline\nP50 of 1.1\\,s'),
 ('引言-贡献2-undeployable', SEC['sec1-intro'], 'zero-shot severity 0.345, ECE 0.321'),
 ('§5-语料量', SEC['sec5-training'], '15{,}041 windows / 60{,}164 typed questions'),
 ('§6.2-稳定带', SEC['sec6-experiments'], '0.809 [0.770, 0.847] / exact 0.656'),
 ('§6.2-主CI', SEC['sec6-experiments'], '0.850\ntactic [0.815, 0.884] / 0.629 exact [0.583, 0.674]'),
 ('§6.2-四delta', SEC['sec6-experiments'], '$+0.089$/$+0.153$/$+0.212$/$+0.214$'),
 ('§6.2-I2描述', SEC['sec6-experiments'], '(Kev-4B, 0.727 dev / 0.761 test)'),
 ('§6.2-I2门控倍数', SEC['sec6-experiments'], '$4.7$--$6.4\\times$'),
 ('§6.2-例外urgent', SEC['sec6-experiments'], 'urgent (GLM-5.3 cloud, 0.854)'),
 ('§6.2-例外severity', SEC['sec6-experiments'], 'severity (DeepSeek-chat, 0.743 vs.\\ 0.724)'),
 ('§6.2-GLM-noaction', SEC['sec6-experiments'], 'in 2/439 windows'),
 ('§6.2-0.8B行', SEC['sec6-experiments'], 'posts 0.763 [0.722, 0.804] / 0.595'),
 ('§6.2-MB句', SEC['sec6-experiments'], 'reaches dev tactic 0.691 / exact 0.673'),
 ('§6.2-MB-NLL', SEC['sec6-experiments'], 'NLL drops from 1.466 to 1.004'),
 ('§6.2-MB-ECE', SEC['sec6-experiments'], 'tactic ECE stays at 0.276'),
 ('§6.2-MB-未校准', SEC['sec6-experiments'], '0.263 (test) /\n0.281 (development)'),
 ('§6.2-laya句', SEC['sec6-experiments'], 'reaches exact 0.522 on the same split at 25\\,ms'),
 ('§6.2-云exact', SEC['sec6-experiments'], '(Jev 1.13, 0.148; DeepSeek-chat 0.141)'),
 ('§6.2-NanoJev', SEC['sec6-experiments'], 'NanoJev posts exact 0.567'),
 ('§6.2-NanoJev延迟', SEC['sec6-experiments'], 'at 154\\,ms'),
 ('§6.2-rules区间', SEC['sec6-experiments'], 'fall to 0.400--0.446'),
 ('§6.2-laya族区间', SEC['sec6-experiments'], 'score 0.025--0.116 tactic'),
 ('§6.2-Verdict塌缩', SEC['sec6-experiments'], 'collapses 438/439 windows'),
 ('§6.2-Verdict-ECE', SEC['sec6-experiments'], 'one class\nat 0.342 ECE'),
 ('§6.2-29x', SEC['sec6-experiments'], 'domain gain from post-training alone'),
 ('表注-ECE口径', SEC['sec6-experiments'], 'Acceptance-basis ECE, on neither development nor test'),
 ('§6.3-OOF-0.8B', SEC['sec6-experiments'], 'ECE moves 0.112$\\to$0.102'),
 ('§6.3-OOF-4B', SEC['sec6-experiments'], '0.140$\\to$0.150'),
 ('§6.3-over-soften', SEC['sec6-experiments'], 'raw ECE 0.180'),
 ('§6.3-4B主域', SEC['sec6-experiments'], 'reconnaissance 0.72, execution 0.69'),
 ('§7-阶梯', SEC['sec789-tail'], 'NanoJev 154\\,ms $<$ zero-shot Kev-4B 173\\,ms $<$\nDeepSeek-chat 775\\,ms $<$ GLM-5.3 1{,}697\\,ms $<$ Qwen3-8B 2{,}726\\,ms'),
 ('§7-端到端', SEC['sec789-tail'], 'P50 over the 439-window split is 1{,}061\\,ms'),
 ('§7-CPU降级', SEC['sec789-tail'], 'NanoJev ${\\sim}$55\\,s and laya-421M 4.9\\,s'),
 ('§7-CPU降级2', SEC['sec789-tail'], '5.8--21.6\\,s under Q8'),
 ('§7-MB-CPU', SEC['sec789-tail'], 'ModernBERT 273\\,ms'),
 ('§7-冷启动', SEC['sec789-tail'], '7--10\\,s\nfor the kev endpoints'),
 ('§7-冷启动vLLM', SEC['sec789-tail'], '52--72\\,s for the\nvLLM-hosted small-LLM endpoints'),
 ('§7-首请求', SEC['sec789-tail'], '0.5--0.8\\,s on the vLLM endpoints'),
 ('§8-云噪声', SEC['sec789-tail'], '63--78\\% of windows'),
 ('§8-结论', SEC['sec789-tail'], 'test-confirmed at 0.850\ntactic / 0.629 exact'),
 ('§8-增益', SEC['sec789-tail'], '(+0.091 tactic / +0.073 exact at 187 windows'),
]
for label, body, s in WIRE:
    if s in body: pass
    else: bad(f'绊线-{label}: 未找到 "{s[:50]}"')
ok(f'正文绊线 {len(WIRE)} 条')

print()
print('=' * 46)
if fails:
    print(f'FAIL：{len(fails)} 处不一致'); sys.exit(1)
print(f'ALL GREEN：表 {n_cells} 格 + 粗体 13 列 + 图 {nfig} 点 + 绊线 {len(WIRE)} 条')
