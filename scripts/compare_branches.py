#!/usr/bin/env python3
"""
Compare two perf_test.py CSV outputs and print side-by-side MB/s with ratios.
Usage:
  python scripts/compare_branches.py perf_main.csv perf_perf.csv
Note: CSVs should be from perf_test.py runs with --no-grep --no-debug.
"""
import csv
import sys
from collections import OrderedDict

if len(sys.argv) != 3:
    print("Usage: compare_branches.py main.csv perf.csv")
    sys.exit(1)

main_csv, perf_csv = sys.argv[1], sys.argv[2]

def load(path):
    rows = OrderedDict()
    with open(path, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            name = row.get('test_case') or row.get('Test Case')
            rel = row.get('release_mb_s') or row.get('Release MB/s')
            try:
                rows[name] = float(rel)
            except Exception:
                pass
    return rows

main = load(main_csv)
perf = load(perf_csv)

keys = [k for k in perf.keys() if k in main]
print("Case                                MAIN_MB/s   PERF_MB/s   PERF/MAIN")
for k in keys:
    m = main[k]
    p = perf[k]
    ratio = (p/m) if m > 0 else 0.0
    print(f"{k:34} {m:10.2f}   {p:10.2f}     {ratio:6.2f}x")
