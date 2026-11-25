#!/usr/bin/env python3
# fig4 accuracy-latency 散点图 v3 重绘（2026-10-06）
# 用户要求：①消除模型名重叠 ②每模型独立符号(marker) ③完整 legend 说明每个数据点归属
# 数据：tab:main test 列 + D1/tier2 延迟（与 v2 相同数据源，数字不变）
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# 模型: (latency_ms_p50, tactic_acc, marker, color, label, 家族)
# 家族: ORACLE(绿) / local-zs(蓝) / cloud(红)；marker 每模型唯一
D = [
    # ORACLE 线（后训练，延迟口径：tier 级 P50）
    (25,   0.724, 'o', 'ORACLE laya-421M',     'oracle'),
    (114,  0.763, 's', 'ORACLE Kev-0.8B',      'oracle'),
    (173,  0.850, 'D', 'ORACLE Kev-4B',        'oracle'),
    (154, 0.670, 'v', 'ORACLE NanoJev', 'oracle'),
    (14,  0.681, '^', 'ModernBERT (control)', 'local'),
    # 本地 zero/few-shot（延迟=表列）
    (0.3,   0.446, 'P', 'Rule engine',         'local'),
    (112,  0.282, 'X', 'Kev-0.8B (zs)',       'local'),
    (173,   0.761, '<', 'Kev-4B (zs)',         'local'),
    (25,   0.025, '>', 'laya-421M (zs)',      'local'),
    (138, 0.137, '*', 'NanoJev-0.6B (zs)',   'local'),
    (2726, 0.403, 'h', 'Qwen3-8B (prefill)',      'local'),
    (363,  0.007, 'p', 'Spark-X2.5-4B (gen)', 'local'),
    (269,  0.132, 'H', 'MiniCPM-2B (gen)',    'local'),
    (1697,  0.638, 'x', 'GLM-5.3 (cloud)',     'cloud'),
    (775,   0.697, 'd', 'DeepSeek-chat (cloud)',    'cloud'),
    (1630,  0.636, '2', 'Jev 1.13 (cloud)',    'cloud'),
]

fig, ax = plt.subplots(figsize=(9.2, 5.4), dpi=300)

fam_col = {'oracle': '#1a9850', 'local': '#3288bd', 'cloud': '#d73027'}
for lat, acc, mk, name, fam in D:
    ax.scatter(lat, acc, marker=mk, s=110 if fam == 'oracle' else 80,
               color=fam_col[fam], edgecolors='white', linewidths=0.8, zorder=3)

# 引线标注（手动偏移避让，替代自动 adjustText——可控性更好）
ann = [
    ('Rule engine',        (0.3, 0.446),   (4, 8),   'left'),
    ('Kev-0.8B (zs)',      (112, 0.282),   (10, -10),'left'),
    ('laya-421M (zs)',     (25, 0.025),   (-8, 7),  'right'),
    ('ORACLE laya-421M',   (25, 0.724),    (-12, -2),'right'),
    ('ORACLE Kev-0.8B',    (114, 0.763),   (-12, 5), 'right'),
    ('Kev-4B (zs)',        (173, 0.761),   (12, -12),'left'),
    ('ORACLE Kev-4B',      (173, 0.850),   (14, 5),  'left'),
    ('DeepSeek-chat (cloud)',   (775, 0.697),   (10, 10), 'left'),
    ('Jev 1.13 (cloud)',   (1630, 0.636),  (-14, -15), 'right'),
    ('GLM-5.3 (cloud)',    (1697, 0.638),  (-14, 8),  'right'),
    ('Qwen3-8B (prefill)',     (2726, 0.403),  (-12, 7), 'right'),
    ('MiniCPM-2B (gen)',   (269, 0.132),  (10, -6), 'left'),
    ('Spark-X2.5-4B (gen)',(363, 0.007),   (8, 6),   'left'),
    ('NanoJev-0.6B (zs)',  (138, 0.137), (-14, -13), 'right'),
    ('ORACLE NanoJev', (154, 0.670), (-14, -4),'right'),
    ('ModernBERT (control)', (14, 0.681), (10, -16), 'left'),
]
from matplotlib.lines import Line2D
mk_lookup = {name: mk for lat, acc, mk, name, fam in D}
for name, (x, y), (dx, dy), ha in ann:
    ax.annotate(name, xy=(x, y), xytext=(dx, dy), textcoords='offset points',
                fontsize=7.2, ha=ha,
                arrowprops=dict(arrowstyle='-', color='#999999', lw=0.6,
                                shrinkA=0, shrinkB=3))

ax.set_xscale('log')
ax.set_xlabel('P50 latency per window (ms, log scale)', fontsize=9)
ax.set_ylabel('Tactic accuracy (test)', fontsize=9)
ax.set_ylim(-0.03, 1.05)
ax.grid(True, which='both', axis='both', linestyle=':', color='#cccccc', lw=0.5, zorder=0)

# 完整 legend：每个模型一项（marker+颜色），按家族分三列排
handles = [Line2D([0], [0], marker=mk, color='none', markerfacecolor=fam_col[fam],
                  markeredgecolor='white', markersize=7, label=name)
           for lat, acc, mk, name, fam in D]
ax.legend(handles=handles, loc='upper left', bbox_to_anchor=(0.0, 1.0),
          ncol=3, fontsize=6.3, frameon=True, framealpha=0.95,
          columnspacing=0.9, handletextpad=0.3, title='Model', title_fontsize=7)

plt.tight_layout()
plt.savefig('/home/xxl/Mypaper/PDM4SecAgent/journal-template/figures/accuracy-latency.png',
            bbox_inches='tight')
print('fig4 saved')
