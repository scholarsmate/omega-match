#!/usr/bin/env python3
"""
callgrind_report.py

Generate concise summaries and hotspot reports from one or two callgrind
profile outputs. Designed to be lightweight (no external deps) and friendly
for Windows + WSL workflows.

Usage examples:
  python scripts/callgrind_report.py callgrind.main.out
  python scripts/callgrind_report.py callgrind.main.out callgrind.perf_branch.out
  python scripts/callgrind_report.py --top 30 callgrind.main.out callgrind.perf_branch.out
  python scripts/callgrind_report.py --sort delta callgrind.main.out callgrind.perf_branch.out

Outputs:
- Prints summary total Ir and top-N function hotspots.
- With two files, prints side-by-side totals and a delta/ratio overview.
- Optional CSV/JSON exports for further analysis.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, TypedDict, cast

FN_RE_WITH_ID = re.compile(r"^fn=\((?:\d+)\)\s+(.*)$")
FN_RE_SIMPLE = re.compile(r"^fn=(.*)$")
SUMMARY_RE = re.compile(r"^summary:\s*(\d+)")
LINE_EV_RE = re.compile(r"^\s*(\d+)\s+(\d+)(?:\s|$)")

@dataclass
class Profile:
    path: str
    summary: int
    by_fn: Dict[str, int]

    def top(self, n: int) -> List[Tuple[str, int, float]]:
        total = self.summary if self.summary > 0 else 1
        items = sorted(self.by_fn.items(), key=lambda kv: kv[1], reverse=True)
        return [(name, val, (val/total) * 100.0) for name, val in items[:n]]


def parse_callgrind(path: str) -> Profile:
    summary: int = 0
    by_fn: Dict[str, int] = {}
    cur_fn: Optional[str] = None

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = SUMMARY_RE.match(line)
                if m:
                    try:
                        summary = int(m.group(1))
                    except ValueError:
                        pass
                    continue
                if line.startswith("fn="):
                    m = FN_RE_WITH_ID.match(line)
                    if m:
                        cur_fn = m.group(1).strip()
                    else:
                        m2 = FN_RE_SIMPLE.match(line)
                        cur_fn = m2.group(1).strip() if m2 else None
                    continue
                # Skip meta/call lines
                if line.startswith(("fl=", "ob=", "cfn=", "calls=")):
                    continue
                # Collect per-line event counts (Ir only)
                lm = LINE_EV_RE.match(line)
                if lm and cur_fn:
                    try:
                        ev = int(lm.group(2))
                        by_fn[cur_fn] = by_fn.get(cur_fn, 0) + ev
                    except ValueError:
                        pass
    except FileNotFoundError:
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)

    return Profile(path=path, summary=summary, by_fn=by_fn)


def human(n: int) -> str:
    return f"{n:,}"


def print_single(profile: Profile, top: int) -> None:
    print(f"File: {profile.path}")
    print(f"  summary Ir: {human(profile.summary)}")
    print(f"  top {top} functions:")
    for name, val, pct in profile.top(top):
        print(f"    {name:48}  {human(val):>14}  {pct:6.2f}%")
    print()


def align_functions(a: Profile, b: Profile) -> Dict[str, Tuple[int, int]]:
    keys = set(a.by_fn.keys()) | set(b.by_fn.keys())
    out: Dict[str, Tuple[int, int]] = {}
    for k in keys:
        out[k] = (a.by_fn.get(k, 0), b.by_fn.get(k, 0))
    return out


def print_compare(a: Profile, b: Profile, top: int, sort_by: str) -> None:
    print(f"A: {a.path}")
    print(f"B: {b.path}")
    print(f"  A summary Ir: {human(a.summary)}")
    print(f"  B summary Ir: {human(b.summary)}")
    ratio = (a.summary / b.summary) if b.summary else 0.0
    print(f"  Total Ir reduction (A/B): {ratio:.2f}x\n")

    pairs = align_functions(a, b)

    rows: List[Tuple[str, int, float, int, float, int, float]] = []
    atotal = a.summary if a.summary else 1
    btotal = b.summary if b.summary else 1
    for name, (av, bv) in pairs.items():
        ap = (av / atotal) * 100.0
        bp = (bv / btotal) * 100.0
        delta = av - bv
        r = (av / bv) if bv else float('inf') if av > 0 else 0.0
        rows.append((name, av, ap, bv, bp, delta, r))

    if sort_by == "A":
        rows.sort(key=lambda x: x[1], reverse=True)
    elif sort_by == "B":
        rows.sort(key=lambda x: x[3], reverse=True)
    elif sort_by == "delta":
        rows.sort(key=lambda x: x[5], reverse=True)
    else:
        rows.sort(key=lambda x: x[1], reverse=True)

    print(f"Top {top} functions (sorted by {sort_by}):")
    print(f"{'function':48}  {'A Ir':>14}  {'A%':>6}   {'B Ir':>14}  {'B%':>6}   {'Δ(A-B)':>14}  {'A/B':>8}")
    for name, av, ap, bv, bp, delta, r in rows[:top]:
        r_str = (f"{r:.2f}x" if r != float('inf') else "inf")
        print(f"{name:48}  {human(av):>14}  {ap:6.2f}   {human(bv):>14}  {bp:6.2f}   {human(delta):>14}  {r_str:>8}")
    print()


def export_outputs(a: Profile, b: Optional[Profile], csv_path: Optional[str], json_path: Optional[str], top: int, sort_by: str) -> None:
    # JSON-serializable output container with explicit shapes to aid type checkers
    data: Dict[str, Any] = {
        "A": {
            "path": a.path,
            "summary_Ir": a.summary,
            "top": a.top(top),
        }
    }
    if b is not None:
        # Build aligned rows as in print_compare
        pairs = align_functions(a, b)
        atotal = a.summary if a.summary else 1
        btotal = b.summary if b.summary else 1
        class Row(TypedDict):
            function: str
            A_Ir: int
            A_pct: float
            B_Ir: int
            B_pct: float
            delta: int
            ratio: float

        rows: List[Row] = []
        for name, (av, bv) in pairs.items():
            ap = (av / atotal) * 100.0
            bp = (bv / btotal) * 100.0
            delta = av - bv
            r = (av / bv) if bv else float('inf') if av > 0 else 0.0
            rows.append(cast(Row, {
                "function": name,
                "A_Ir": av,
                "A_pct": ap,
                "B_Ir": bv,
                "B_pct": bp,
                "delta": delta,
                "ratio": r,
            }))
        if sort_by == "A":
            rows.sort(key=lambda x: x["A_Ir"], reverse=True)
        elif sort_by == "B":
            rows.sort(key=lambda x: x["B_Ir"], reverse=True)
        elif sort_by == "delta":
            rows.sort(key=lambda x: x["delta"], reverse=True)
        data["B"] = {
            "path": b.path,
            "summary_Ir": b.summary,
        }
        data["compare_top"] = rows[:top]

    if json_path:
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(data, jf, indent=2)

    if csv_path:
        try:
            import csv
            with open(csv_path, "w", newline="", encoding="utf-8") as cf:
                writer = csv.writer(cf)
                if b is None:
                    writer.writerow(["function", "Ir", "percent"]) 
                    for name, val, pct in a.top(top):
                        writer.writerow([name, val, f"{pct:.4f}"])
                else:
                    writer.writerow(["function", "A_Ir", "A_pct", "B_Ir", "B_pct", "delta", "ratio"])
                    comp_rows = cast(List[Row], data.get("compare_top", []))
                    for row in comp_rows:
                        ratio_val = row["ratio"]
                        writer.writerow([
                            row["function"], row["A_Ir"], f"{row['A_pct']:.4f}",
                            row["B_Ir"], f"{row['B_pct']:.4f}", row["delta"],
                            ("inf" if ratio_val == float('inf') else f"{ratio_val:.4f}")
                        ])
        except Exception as e:
            print(f"[WARN] Failed to write CSV: {e}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Summarize/compare callgrind profiles (Ir)")
    p.add_argument("files", nargs="+", help="One or two callgrind output files")
    p.add_argument("--top", type=int, default=20, help="Top-N functions to show")
    p.add_argument("--sort", choices=["A", "B", "delta"], default="A", help="Sort order for comparisons")
    p.add_argument("--csv", type=str, help="Optional CSV export path")
    p.add_argument("--json", type=str, help="Optional JSON export path")
    args = p.parse_args(argv)

    if len(args.files) == 0 or len(args.files) > 2:
        p.error("Provide one or two callgrind files")

    a = parse_callgrind(args.files[0])
    if len(args.files) == 1:
        print_single(a, args.top)
        export_outputs(a, None, args.csv, args.json, args.top, args.sort)
        return 0

    b = parse_callgrind(args.files[1])
    print_compare(a, b, args.top, args.sort)
    export_outputs(a, b, args.csv, args.json, args.top, args.sort)
    return 0


if __name__ == "__main__":
    sys.exit(main())
