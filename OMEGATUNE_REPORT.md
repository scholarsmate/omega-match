# OMEGATUNE — OmegaMatch Autonomous Optimization Journal

This file is the persistent memory for an overnight autonomous optimization
campaign driven by fresh Hermes cron sessions. Each session reads this file
first, performs exactly ONE bounded experiment, appends the result, and exits.

## Standing rules

- Work happens ONLY on branch `perf/omega-tune-2026-09` in the worktree
  `/home/davin/git/OMEGA/omega-match-tune`. Never modify `main`.
- Never push to any remote.
- Never discard pre-existing user work; verify `git status` before changes.
- Never remove or weaken correctness tests.
- Never report a performance improvement without measurements.
- One experiment per session. Do not start a second experiment.

## Campaign state

- Current accepted branch: `perf/omega-tune-2026-09`
- Current HEAD at campaign start: 407f128 (same as origin/main)
- Current accepted baseline: EXP-001 (fast integer output writer) — see
  numbers under "Original baseline" (pre-EXP-001) and EXP-001 entry below.
- Session log: EXP-001 accepted (this entry), 2026-09-21/22.

## Environment (fixed for the campaign)

- Host: Intel Core Ultra 7 165H, 22 logical CPUs (16C/22T), 24 MiB L3,
  single NUMA node. Governor: powersave (no root to change; affects absolute
  numbers only — interleaved A/B comparisons remain valid).
- gcc 16.2.1 20260810, cmake 4.4.3, Ninja.
- Build: `cmake --preset release -DOMEGA_MATCH_REQUIRE_OPENMP=ON &&
  cmake --build --preset release` → `build-gcc-release/olm`.
- No `hyperfine`, `valgrind`, or working `perf report` available; `perf
  record` produces no usable report. Profiling = differential timing
  experiments (interleaved A/B) + source reading.

## Original baseline (pre-EXP-001, commit 407f128 lineage)

Harness: `python3 scripts/benchmark_scaling.py --olm
release=build-gcc-release/olm --sizes-mib 64,256 --cases
longest-no-overlap,line-start --threads 8 --runs 7 --mode output
--olm-pattern-mode both --work-dir /tmp/omega-match-scaling --skip-grep
--skip-ripgrep`. Corpus in `/tmp/omega-match-scaling` (haystack-64m.bin,
haystack-256m.bin, patterns-base.olm — regenerate with the same script if
missing).

Harness medians (7 runs, match-only, output mode):
- longest-no-overlap 64 MiB:  0.1693 s (378 MiB/s)
- longest-no-overlap 256 MiB: ~0.66–0.68 s (~375–395 MiB/s)
- line-start 64 MiB:          0.0348 s (1840 MiB/s)

Direct wall-time medians (bash `date +%s%N`, `olm match --threads 8
--longest --no-overlap patterns-base.olm haystack-256m.bin`, 7 reps, output
to file) — the interleave-A/B methodology used for experiment comparisons
since it kills drift on the powersave governor: baseline ≈ 658 ms
(range 645–685, ~±3%). Quiet-mode floor (`--quiet`) ≈ 449 ms, i.e. output
formatting was ~165–180 ms (~28%) of wall time.

Noise margin observed in interleaved A/B: ±10 ms (~1.5%) per rep; accept
threshold ≥ 3× margin with consistent sign across reps.

## Accepted experiments

### EXP-001 — fast u64 writer replaces snprintf in match-output loop — ACCEPTED

Hypothesis: `print_results_buffered_fd()` in `omega_match/main.c` used
`snprintf(prefix, "%zu:%zu:", offset, key)` per match line; glibc snprintf
parsing/formatting dominates that cost. Replace with a branchy two-digits-
at-a-time decimal writer (`write_u64_digits` + `emit_output` in main.c) that
formats offset (and key when `--show-keys`) directly into a small stack
buffer, keeping the existing buffered-write logic identical.

Evidence: differential timing `--quiet` vs output showed formatting cost
165–180 ms on 4,067,333 match lines (~40–44 ns/line).

Implementation: +33/−5 lines in `omega_match/main.c` only.

Correctness:
- All 18 CTest tests pass (`ctest --test-dir build-gcc-release -E
  python_pytest`; the 19th, `python_pytest`, is blocked in this environment
  — no pip-installable venv — and was already failing pre-change).
- Byte-identical stdout vs pre-change binary on 256 MiB corpus for
  `--longest --no-overlap`, `--line-start --longest --no-overlap`,
  `--ignore-case --word-boundary --longest --no-overlap` (sha256 compared).
- Byte-identical on `--show-keys` (keyed patterns, numeric keys) and on
  tiny edge-case corpora.

Benchmark (interleaved A/B, old vs new binary, ≥5–7 reps):
- longest-no-overlap 256 MiB: B 645–685 ms vs E 573–586 ms → Δ ≈ −80 ms,
  −12.2% (7/7 reps, separation never overlapped).
- longest-no-overlap 64 MiB:  B 166–183 ms vs E 148–156 ms → Δ ≈ −17 ms,
  −9.7% (5/5 reps).
- line-start 256 MiB:         B 129–134 ms vs E 102–114 ms → Δ ≈ −25 ms,
  −18.5% (5/5 reps).
Output files byte-identical at the end of each A/B series.

New accepted baseline (post-EXP-001, wall medians, `--threads 8`, output
mode, same corpus/commands as above):
- longest-no-overlap 256 MiB: ≈ 578 ms (~443 MiB/s)
- longest-no-overlap 64 MiB:  ≈ 152 ms (~421 MiB/s)
- line-start 256 MiB:         ≈ 106 ms
- line-start 64 MiB:          ≈ 30 ms (measured 30–31; pre-change ≈ 35.5 ms,
  −15%)
Quiet-mode floors unchanged (~449 ms / ~100 ms) — search itself untouched.

## Rejected / inconclusive experiments

(none yet)

## Known dead ends

- `perf record`/`perf report` produce no usable output on this host (no
  symbols/kallsyms access); `valgrind`/`hyperfine` not installed; `sudo`
  unavailable. Don't waste a session trying to install system profilers —
  use interleaved A/B differential timing instead.
- Python venv creation + `pip install pytest` fails in this sandbox (exit
  -1). CTest (`-E python_pytest`, 18 tests) + byte-identical-output diffs
  are the working correctness gate.

## Recommended next experiments

1. Vectorize the line-start newline skip (matcher.c scan loop): the scan
   advances byte-by-byte to the next `\n`; SSE2/AVX2 `_mm_cmpeq_epi8` scan
   should cut line-start cost further (currently ~106 ms / 256 MiB; even
   memory-bound, per-byte loop likely leaves throughput on the table).
   Validate by timing `--line-start` with dense vs sparse newlines.
2. Output-buffer size / write granularity in `print_results_buffered_fd`
   (OUTPUT_BUFFER_SIZE currently 64 KiB — try 256 KiB/1 MiB; few writes vs
   many). Cheap, isolated.
3. Chunk-size tuning sweep in the match pipeline (chunk_size option) for
   the 256 MiB case at 8 threads.
4. Bloom-filter probe layout (`omega_match/src/bloom.c` ~lines 30–95,
   `bloom_filter_add`/`bloom_filter_query`; 3 probes into one bitmap per
   `omega/details/bloom.h`): consider a blocked/squarized layout to reduce
   misses per candidate position. Profile via differential timing on a
   low-match-rate corpus where candidate rejection dominates.
5. `--line-end` + `--line-start` combined mode currently produces zero
   matches on the base corpus — verify intent before optimizing it.

## Profiling findings

- Differential quiet-vs-output timing (pre-EXP-001): output formatting of
  4.07M match lines cost ~28% of wall time on the 256 MiB longest case;
  EXP-001 removed most of it (see accepted entry).
- Quiet-mode floors (search-only, 256 MiB): longest-no-overlap ≈ 449 ms
  (~570 MiB/s at 8 threads), line-start ≈ 100 ms. Remaining headroom is in
  the scan loops themselves, not I/O.
- Read of matcher.c scan loops (lines ~1021–1425): candidate positions are
  gated by a per-position bloom probe; line-start mode then walks to the
  line start byte-by-byte. bloom.c uses 3 hash probes into one bitmap.
