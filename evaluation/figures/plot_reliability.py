#!/usr/bin/env python3
"""fig:rel reliability diagrams (2 lines x raw/scaled, 15 equal-frequency bins, 1756 questions).
数据源: EVAL/BATCH0-V2/reliability-diagrams.json (all1756 arms)
输出: journal-template/figures/reliability-diagrams.png
"""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

d = json.load(open('/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/BATCH0-V2/reliability-diagrams.json'))
lines = [('Kev-4B', 'kev-4B'), ('Kev-0.8B', 'kev-0.8B')]
arms = [('raw', 'raw_all1756'), ('temperature-scaled', 'methodA_all1756')]

fig, axes = plt.subplots(2, 2, figsize=(7.6, 6.2), dpi=300, sharex=True, sharey=True)
for i, (lname, lkey) in enumerate(lines):
    for j, (aname, akey) in enumerate(arms):
        ax = axes[i][j]
        bins = d[f'{lkey}_{akey}']
        N = sum(b['n'] for b in bins)
        ece = sum(b['n']/N*abs(b['conf']-b['acc']) for b in bins)
        conf = [b['conf'] for b in bins]; acc = [b['acc'] for b in bins]
        w = [b['n']/N for b in bins]
        ax.bar(conf, [a-c for c, a in zip(conf, acc)], width=0.055, bottom=[c for c in conf],
               color='#fdae61', alpha=0.85, label='gap', zorder=2)
        ax.plot([0, 1], [0, 1], color='#999999', lw=0.8, ls='--', zorder=1)
        ax.plot(conf, acc, 'o-', color='#3288bd', lw=1.4, ms=3.5, zorder=3)
        ax.set_title(f'{lname}, {aname} (ECE {ece:.3f})', fontsize=9)
        if j == 0: ax.set_ylabel('accuracy', fontsize=9)
        if i == 1: ax.set_xlabel('confidence', fontsize=9)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.grid(alpha=0.2, lw=0.4)
fig.tight_layout()
fig.savefig('/home/xxl/Mypaper/PDM4SecAgent/journal-template/figures/reliability-diagrams.png', bbox_inches='tight')
print('fig:rel saved')
