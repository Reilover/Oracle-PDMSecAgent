#!/usr/bin/env python3
"""fig:e3p local-label gain curve (dev split, 0/50/187 audited windows).
数据源: E3P-LOCAL-LABELS/dev{0,_n050,_n200}_analysis.json (n200 文件=187 唯一窗档)
输出: journal-template/figures/e3p-gain-curve.png
"""
import json
from pathlib import Path

OUT = Path('/home/xxl/MySecAgent/lab/experiments/oracle/E3P-LOCAL-LABELS')
FIG = Path('/home/xxl/Mypaper/PDM4SecAgent/journal-template/figures/e3p-gain-curve.png')
FILES = {
    0: OUT / 'dev0_baseline_analysis.json',
    50: OUT / 'dev_n050_analysis.json',
    187: OUT / 'dev_n200_analysis.json',
}

def summ(p):
    d = json.load(open(p)); t = d['tasks']
    return {k: t[k]['acc'] for k in ('tactic', 'urgent', 'severity', 'action')}, d['exact_match']

data = {}
for n, p in FILES.items():
    accs, em = summ(p)
    data[n] = {**accs, 'exact': em}

(OUT / 'gain-curve-data.json').write_text(json.dumps({n: {k: round(v, 4) for k, v in r.items()} for n, r in data.items()}, indent=2))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

xs = sorted(data)
tasks = ['tactic', 'urgent', 'severity', 'action', 'exact']
colors = {'tactic': '#2563eb', 'urgent': '#0891b2', 'severity': '#ca8a04',
          'action': '#ea580c', 'exact': '#111827'}
fig, ax = plt.subplots(figsize=(7, 4.2), dpi=300)
for t in tasks:
    ys = [data[x][t] for x in xs]
    ax.plot(xs, ys, marker='o', label=t, color=colors[t], linewidth=1.8)
    ax.annotate(f'{ys[-1]:.3f}', (xs[-1], ys[-1]), textcoords='offset points',
                xytext=(6, 0), fontsize=8, color=colors[t])
ax.set_xlabel('audited local windows', fontsize=10)
ax.set_ylabel('development-split accuracy', fontsize=10)
ax.set_xticks(xs)
ax.grid(alpha=0.25, linewidth=0.5)
ax.legend(fontsize=8, ncol=5, loc='lower center', bbox_to_anchor=(0.5, 1.02),
            frameon=False, columnspacing=1.2, handlelength=1.6)
for s in ('top', 'right'):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(FIG, bbox_inches='tight')
print('wrote', FIG)
print(json.dumps(data, indent=2))
