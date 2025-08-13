#!/usr/bin/env python3
"""Generate performance bar chart from perf_results.csv.
Fallback replacement for gnuplot when not available. Produces perf_results.png.
"""
from __future__ import annotations
import csv
from pathlib import Path
import math
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

CSV = Path('perf_results.csv')
OUT = Path('images/perf_results_log.png')
if not CSV.exists():
    print('perf_results.csv not found')
    sys.exit(1)

rows = []
with CSV.open(newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

# Columns: test_case, threads, debug_mb_s, release_mb_s, pgo_mb_s, grep_mb_s, release_grep_ratio, compare_status
# We plot only tests where grep_mb_s != 'N/A' (grep-comparable) for readability; include PGO if present.
plot_rows = [r for r in rows if r.get('grep_mb_s') not in ('N/A', None, '')]
if not plot_rows:
    # fallback: use all rows
    plot_rows = rows

labels = [r['test_case'] for r in plot_rows]
release_vals = []
pgo_vals = []
grep_vals = []
for r in plot_rows:
    def parse(v):
        try:
            return float(v)
        except Exception:
            return math.nan
    release_vals.append(parse(r.get('release_mb_s', 'nan')))
    pgo_vals.append(parse(r.get('pgo_mb_s', 'nan')))
    grep_vals.append(parse(r.get('grep_mb_s', 'nan')))

x = list(range(len(labels)))
width = 0.28
OUT.parent.mkdir(parents=True, exist_ok=True)
plt.figure(figsize=(18, 9), facecolor='black')
ax = plt.gca()
ax.set_facecolor('black')
# Alternating background bands to improve readability across many categories.
# We shade even-indexed clusters using axvspan spanning one category width (index +/- 0.5).
for i in x:
    if i % 2 == 0:
        ax.axvspan(i - 0.5, i + 0.5, facecolor='#222222', alpha=0.35, zorder=0)
# Positions
release_pos = [i - width for i in x]
pgo_pos = x
grep_pos = [i + width for i in x]

ax.bar(release_pos, release_vals, width, label='Release', color='#1f77b4')      # blue
ax.bar(pgo_pos, pgo_vals, width, label='Release+PGO', color='#9467bd')          # purple
ax.bar(grep_pos, grep_vals, width, label='grep', color='#ff7f0e')               # orange

# Add value labels on top of each bar (log scale safe: use multiplicative offset)
def fmt(v: float) -> str:
    if not math.isfinite(v):
        return ''
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 100:
        return f"{v:.0f}"
    if v >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"

# Recreate containers to annotate (matplotlib doesn't expose them since we didn't keep refs)
bars = [
    (release_pos, release_vals, '#1f77b4'),
    (pgo_pos, pgo_vals, '#9467bd'),
    (grep_pos, grep_vals, '#ff7f0e')
]
for xpos, vals, color in bars:
    for x_i, v in zip(xpos, vals):
        if not math.isfinite(v) or v <= 0:
            continue
        ax.text(x_i, v * 1.05, fmt(v), ha='center', va='bottom', rotation=90,
                fontsize=9, color='white', clip_on=False)

ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=45, ha='right', color='white')
ax.set_xlim(-0.5, len(x) - 0.5)
ax.set_ylabel('Throughput (MB/s, log scale)', color='white')
ax.set_title('OmegaMatch Performance (Release vs PGO vs grep) - Log Scale', color='white')
ax.set_yscale('log')
ax.set_ylim(bottom=10)  # avoid log(0); adjust as needed
ax.tick_params(colors='white')
for spine in ax.spines.values():
    spine.set_color('white')
leg = ax.legend(facecolor='#111111', edgecolor='white', fontsize=14, framealpha=0.9)
for text in leg.get_texts():
    text.set_color('white')
ax.grid(axis='y', color='#444444')
plt.tight_layout()
plt.savefig(OUT, dpi=150, facecolor='black')
print(f'Wrote {OUT}')
