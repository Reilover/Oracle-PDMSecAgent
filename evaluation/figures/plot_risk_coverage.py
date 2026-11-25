#!/usr/bin/env python3
"""fig:rc window-level risk-coverage (temperature-scaled Kev-4B: test 439 + calibration 55).
数据源: EVAL/BATCH0-V2/risk-coverage-curves.json (test_window/kev-4B 与 calib_window_4B_methodA)
输出: journal-template/figures/risk-coverage.png
"""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

d = json.load(open('/home/xxl/MySecAgent/lab/experiments/oracle/EVAL/BATCH0-V2/risk-coverage-curves.json'))
test = [p for p in d['test_window']['kev-4B'] if isinstance(p, dict) and 'risk' in p]
calib = [p for p in d['calib_window_4B_methodA'] if isinstance(p, dict) and 'risk' in p]

fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=300)
ax.plot([p['coverage'] for p in test], [p['risk'] for p in test],
        color='#1a9850', lw=1.8, label='test (439 windows)')
ax.plot([p['coverage'] for p in calib], [p['risk'] for p in calib],
        color='#3288bd', lw=1.8, ls='--', label='calibration (55 windows)')
ax.axhline(0.05, color='#d73027', lw=0.9, ls=':', label='5\\% mishandling budget')
ax.set_xlabel('coverage (top-ranked high-confidence windows)', fontsize=10)
ax.set_ylabel('window-level mishandling rate', fontsize=10)
ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
ax.grid(alpha=0.25, lw=0.5)
ax.legend(fontsize=8, loc='upper right', framealpha=0.9)
for s in ('top', 'right'):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig('/home/xxl/Mypaper/PDM4SecAgent/journal-template/figures/risk-coverage.png', bbox_inches='tight')
print('fig:rc saved')
