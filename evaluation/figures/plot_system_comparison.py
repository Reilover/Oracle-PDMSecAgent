#!/usr/bin/env python3
# fig2 system-comparison 重绘（2026-11-20）：tab:main test 列（cloud-Jev 已换同约定 439 窗数字）
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# (tactic_test, exact_test, label, family) —— test 列；exact 缺者不绘 exact 点
D = [
    (0.850, 0.629, 'ORACLE Kev-4B',    'oracle'),
    (0.763, 0.595, 'ORACLE Kev-0.8B',  'oracle'),
    (0.724, 0.522, 'ORACLE laya-421M', 'oracle'),
    (0.670, 0.567, 'ORACLE NanoJev',   'oracle'),
    (0.636, 0.148, 'Jev 1.13 (cloud)', 'cloud'),
    (0.638, 0.034, 'GLM-5.3',          'cloud'),
    (0.697, 0.141, 'DeepSeek-chat',    'cloud'),
    (0.761, 0.194, 'Kev-4B (zs)',      'local'),
    (0.282, 0.002, 'Kev-0.8B (zs)',    'local'),
    (0.137, 0.000, 'NanoJev-0.6B (zs)','local'),
    (0.025, 0.009, 'laya-421M (zs)',   'local'),
    (0.403, 0.130, 'Qwen3-8B',         'local'),
    (0.446, 0.194, 'Rule engine',            'local'),
    (0.677, 0.000, 'MiniCPM-2B (opt)', 'local'),
    (0.132, 0.052, 'MiniCPM-2B (gen)', 'local'),
    (0.007, 0.002, 'Spark-X2.5-4B (gen)',      'local'),
    (0.000, 0.000, 'Verdict-151M',     'local'),
    (0.681, 0.681, 'ModernBERT (control)', 'local'),
]
fam_col = {'oracle': '#1a9850', 'local': '#3288bd', 'cloud': '#d73027'}
fig, ax = plt.subplots(figsize=(9.2, 5.6), dpi=300)
for tac, ex, name, fam in D:
    ax.scatter(tac, ex, s=120 if fam == 'oracle' else 70,
               color=fam_col[fam], edgecolors='white', linewidths=0.8, zorder=3)
ann_off = {
    'ORACLE Kev-4B': (-10, 6), 'ORACLE Kev-0.8B': (8, -10), 'ORACLE laya-421M': (-8, -12),
    'ORACLE NanoJev': (-10, 6), 'Jev 1.13 (cloud)': (-10, -6), 'GLM-5.3': (-12, -4),
    'DeepSeek-chat': (8, 4), 'Kev-4B (zs)': (-10, 6), 'Kev-0.8B (zs)': (8, 7),
    'NanoJev-0.6B (zs)': (8, 5), 'laya-421M (zs)': (2, 14), 'Qwen3-8B': (8, -8),
    'Rule engine': (8, 4), 'MiniCPM-2B (opt)': (8, 8), 'MiniCPM-2B (gen)': (8, -4),
    'Spark-X2.5-4B (gen)': (10, -2), 'Verdict-151M': (-8, -8),
    'ModernBERT (control)': (10, 6),
}
for tac, ex, name, fam in D:
    dx, dy = ann_off[name]
    ax.annotate(name, xy=(tac, ex), xytext=(dx, dy), textcoords='offset points',
                fontsize=7.2, ha='left' if dx > 0 else 'right',
                arrowprops=dict(arrowstyle='-', color='#999999', lw=0.6, shrinkA=0, shrinkB=3))
ax.set_xlabel('Tactic accuracy (439-window test)', fontsize=9)
ax.set_ylabel('Four-task exact match (test)', fontsize=9)
ax.set_xlim(-0.12, 0.95); ax.set_ylim(-0.04, 0.75)
ax.grid(True, linestyle=':', color='#cccccc', lw=0.5, zorder=0)
from matplotlib.lines import Line2D
ax.legend(handles=[Line2D([], [], marker='o', ls='', color=fam_col[f], label=l)
                   for f, l in [('oracle', 'ORACLE (post-trained)'), ('local', 'local systems'), ('cloud', 'cloud APIs')]],
          fontsize=8, loc='upper left', framealpha=0.9)
plt.tight_layout()
plt.savefig('/home/xxl/Mypaper/PDM4SecAgent/journal-template/figures/system-comparison.png', bbox_inches='tight')
print('fig2 saved')
