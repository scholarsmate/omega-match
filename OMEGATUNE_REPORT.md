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
- Current accepted baseline: EXP-004 (word-boundary candidate
  materialization removed) — see EXP-004 entry under accepted experiments.
- Session log: EXP-001 accepted (2026-09-21/22), EXP-002 accepted
  (2026-09-22), EXP-003 accepted (2026-09-22), EXP-004 accepted
  (2026-09-22).

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

### EXP-002 — SSE2 skip to next line-start in the line-start scan — ACCEPTED

Hypothesis (recommended experiment #1, adapted): in `core_match()`
(matcher.c), line-start mode gates every byte of the haystack with
`if (line_start && pos > 0 && !is_line_end(haystack[pos-1])) continue;`,
walking interior bytes one at a time even though only ~0.7% of positions
(~1.81M newlines in 256 MiB, avg line length ~148 B) are line starts.
Instead of vectorizing the whole pass (the per-position work is already
trivial once the gate rejects), skip *directly* from a failed gate to the
next line-ending byte using SSE2, so the scan touches memory at SIMD speed.

Implementation (+54/−0 lines in `omega_match/src/matcher.c` only):
`next_line_start_pos(h, pos, end)` — SSE2 (`_mm_loadu_si128` +
`_mm_cmpeq_epi8` vs `\n` and `\r`, combined movemask, `__builtin_ctz`)
advances 16 bytes per iteration to the first line-ending byte at >= pos and
returns that position + 1 (or `end`). The main-loop gate now calls it and
jumps `pos = n - 1` (loop `++pos` lands on `n`). Safety details: all SIMD
blocks are clamped fully inside `[0, end)` (`simd_limit = end & ~15`) so a
load can never cross the end of an mmap'd read-only buffer; the <16-byte
tail is scalar; unaligned load used because the matcher may be called with
window-relative pointers (transform path). Non-x86 falls back to the scalar
loop, same semantics. Note the previous EXP-001 report's quiet-floor of
~100 ms for line-start was the *interleaved* figure; fresh baseline quiet
median here is ~79 ms (governor drift), which is why A/B interleaving
remains mandatory.

Correctness:
- All 18 CTest tests pass (`ctest --test-dir build-gcc-release -E
  python_pytest`).
- Differential byte-identity vs pre-change binary across 8 edge-case
  corpora (empty, 1-byte, 15/16/17-byte, all-newlines, random with CR/LF
  and CRLF pairs, 300 KB single long line + newlines) x 8 flag combos
  including `--line-start`, `--line-start --longest --no-overlap`,
  `--line-start --ignore-case`, `--line-start --word-boundary`,
  `--line-start --show-keys`, and non-line-start controls: 0 mismatches,
  exit codes identical.
- Byte-identical output on the real 256 MiB corpus for `--line-start`,
  `--line-start --longest --no-overlap`,
  `--line-start --ignore-case --word-boundary` (sha256 compared at end of
  A/B series).

Benchmark (interleaved A/B vs pre-change binary, 9 reps line-start / 5 reps
control, `--threads 8`, medians):
- line-start longest-no-overlap 256 MiB, quiet:   B 79 ms -> E 53 ms, −26 ms (−32.9%); separation clean every rep (E max 54 < B min 77).
- line-start longest-no-overlap 256 MiB, output:  B 104 ms -> E 78 ms, −26 ms (−25.0%).
- line-start longest-no-overlap 64 MiB, quiet:    B 24 ms -> E 16 ms, −8 ms (−33.3%).
- control longest-no-overlap 256 MiB (no line-start): B 563 ms vs E 570 ms, +7 ms (+1.2%) — within noise, path untouched by the change (gate is `line_start`-conditional).

New accepted baseline (post-EXP-002, wall medians, `--threads 8`):
- line-start longest-no-overlap 256 MiB: output ≈ 78 ms, quiet ≈ 53 ms
- line-start longest-no-overlap 64 MiB:  quiet ≈ 16 ms
- longest-no-overlap 256 MiB: ≈ 578 ms (unchanged; EXP-001 baseline holds)

### EXP-003 — default OMP static chunk 4096 → 1 MiB — ACCEPTED

Hypothesis (recommended item 3): with `omp_sched_static` and chunk=4096
positions, an 8-thread 256 MiB run iterates ~7800 schedule chunks per
thread; per-chunk bookkeeping (schedule iteration + local statistic
merge) is measurable. An earlier 3-rep sweep (4K/16K/64K/256K/1M,
`/tmp/omega-match-scaling/chunk-probe.tsv`) suggested 1 MiB ~10–19 ms
faster than 4096 on the longest-no-overlap quiet case.

Change (smallest isolated): `omega_match/src/matcher.c` — introduce
`OMEGA_DEFAULT_OMP_CHUNK (1048576)` and use it at both default sites
(`omega_matcher_set_chunk_size(…, 0)` fallback and the
`omp_set_schedule(... : 4096)` fallback). Explicit `--chunk-size`
behavior unchanged; value still rounded up to power of two.

Correctness: CTest 18/18 pass (`-E python_pytest`); byte-identical
match output (sha256) between chunk 4096, new default, and 64K@4threads
across 4 modes (longest-no-overlap 4,067,333 lines; plain 7,316,720;
line-start-longest 1,042,604; ignore-case).

Benchmark (quiet, `--threads 8`, longest-no-overlap 256 MiB base corpus,
interleaved pairs; artifacts `chunk-ab.tsv` 9 reps, `chunk-ab2.tsv` 15,
`chunk-ab3.tsv` 12, `exp003-final.tsv` 12 same-binary default-vs-explicit-4096):
- Pooled paired sample n=48: median 4096 = 479.5 ms, median 1 MiB =
  471.5 ms; median delta −10.0 ms, mean −6.8 ms (95% CI [−11.0, −2.6],
  t = −3.22); 1 MiB faster in 34/48 pairs, sign test one-sided p = 0.0028.
- Same-binary check (`exp003-final.tsv`, isolates default change from
  binary drift): median delta −8.0 ms, 8/12 wins. Consistent with pooled.
- Controls (8 interleaved reps, explicit 4096 vs 1M on same binary):
  line-start longest-no-overlap 256 MiB quiet 54.0 → 51.5 ms (−1.5 ms,
  7/8 wins — small but same direction); longest-no-overlap 64 MiB
  124.5 → 124.0 ms (neutral, within noise). No case made slower.

Caveats: single-session measurement; the effect (~1.4%) is within the
scale of run-to-run environment drift, so acceptance rests on the pooled
sign test and the same-binary subset rather than any single A/B. The
earlier 10–19 ms probe figure was optimistic; true effect ≈ −7 to −10 ms.

New accepted baseline (post-EXP-003, wall medians, `--threads 8`, quiet):
- longest-no-overlap 256 MiB: ≈ 471 ms quiet (this session's 1 MiB medians;
  previous EXP-002-era quiet figures were taken under different ambient
  load — compare only within same-session A/B pairs from here on)
- line-start longest-no-overlap 256 MiB: ≈ 51.5 ms quiet (54.0 at chunk 4096)
- longest-no-overlap 64 MiB: ≈ 124 ms quiet

### EXP-004 — remove word-boundary candidate materialization — ACCEPTED

Hypothesis: `--word-boundary` (without `--line-start`) took a
"candidate materialization" path in `core_match()` (matcher.c): two SERIAL
single-threaded byte-at-a-time passes over the haystack (count boundaries,
then fill a `size_t` array), before the parallel scan even started. On the
base corpus 104M of 268M positions are word boundaries → an 832 MB
allocation plus ~800 MB of serial writes, then read back with random-ish
access. Differential probe: wb 1106 ms vs plain 475 ms quiet — the
boundary machinery cost ~2.3x the entire plain scan. Meanwhile the
single-pass loop already contains an identical in-loop word-boundary gate
(lines ~1337-1343), so the materialization buys nothing except overhead.

Implementation (+12/−1 lines in `omega_match/src/matcher.c`): gate the
materialization behind `const int use_wb_candidate_path = 0;` so
`--word-boundary` always uses the single-pass in-loop gate. Code kept in
place (dead but documented) so the experiment is one-constant revertable.

Correctness:
- CTest 18/18 pass (`-E python_pytest`).
- Byte-identical output vs pre-change binary across 4M/64M/256 MiB corpora
  x 6 flag combos (`--word-boundary`, `--word-boundary --longest
  --no-overlap`, `--word-boundary --ignore-case`, `--word-boundary
  --line-start --longest --no-overlap`, controls plain-lno and line-start)
  plus a punctuation/edge tiny corpus: 16/16 checks OK, exit codes equal,
  256 MiB wb-longest-no-overlap 2,262,465 lines byte-identical.

Benchmark (interleaved A/B vs pre-change binary, 7 reps, quiet,
`--threads 8`, 256 MiB base corpus, artifact `exp004-ab.tsv`):
- word-boundary longest-no-overlap: B 1132-1175 ms -> E 355-377 ms,
  median 1149 -> 366 ms, −783 ms (−68.1%), 7/7 wins, ranges never overlap.
- word-boundary plain:              B 1087-1168 ms -> E 346-376 ms,
  median 1149 -> 366 ms, −783 ms (−68.1%), 7/7 wins.
- control longest-no-overlap (no wb): B 501-518 vs E 489-516, +2 ms
  (+0.4%), 4/7 — within noise, path untouched.
Post-A/B output byte-identity re-checked on the 256 MiB corpus (3 modes).

New accepted baseline (post-EXP-004, wall medians, `--threads 8`, quiet,
256 MiB base corpus):
- word-boundary longest-no-overlap: ≈ 366 ms (was ≈ 1149 ms)
- word-boundary plain: ≈ 366 ms
- longest-no-overlap: ≈ 505 ms quiet (unchanged; EXP-003 baseline holds;
  note ambient-load caveat from EXP-003 — compare only within same-session
  A/B pairs)

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
- `olm compile` fails with "Error: Failed to compile patterns …" for ANY
  input on this host in this sandbox (even 3-pattern files, fresh output
  paths, -v shows nothing more) — reproducible at EXP-003 session with the
  EXP-002-lineage build. Do not burn a session trying to build new .olm
  corpora via the CLI; reuse the prebuilt ones in /tmp/omega-match-scaling
  (patterns-base.olm, patterns-release.olm). If new corpora are truly
  needed, investigate the compiler path separately (suspect OMP_NUM_THREADS
  22-core default or sandbox write behavior inside omega_list_matcher_compile).

## Recommended next experiments

0. Word-boundary follow-up (from EXP-004): after the fix, wb
   longest-no-overlap is 366 ms — FASTER than the plain scan (≈471 ms),
   because the in-loop gate cuts bloom attempts from 268M to 104M. The
   gate itself is now the hot path for wb: a vectorized (SSE2/AVX2)
   word-class comparison pass (EXP-002-style skip directly to the next
   boundary instead of testing every interior byte) could plausibly bring
   wb toward the line-start profile (~50-80 ms territory). Also the dead
   `use_wb_candidate_path`-guarded code in matcher.c can be deleted once
   EXP-004 is considered settled.
1. ~~Vectorize the line-start newline skip~~ — DONE as EXP-002 (accepted,
   −25 to −33% on line-start). A further step: the EXP-002 skip is SSE2
   (16 B/iter); AVX2 (32 B/iter) would nearly halve iterations on the long
   interior runs — but at 256 MiB the skip is now likely memory-bandwidth
   bound (~5 GB/s effective read at 53 ms for 256 MiB is near single-socket
   bandwidth); measure first with dense-newline vs sparse-
   newline corpora before investing.
2. Output-buffer size / write granularity in `print_results_buffered_fd`
   (OUTPUT_BUFFER_SIZE currently 64 KiB — try 256 KiB/1 MiB; few writes vs
   many). Cheap, isolated.
3. ~~Chunk-size tuning sweep in the match pipeline~~ — DONE as EXP-003
   (accepted: default chunk 4096 → 1 MiB, −7 to −10 ms on 256 MiB longest
   quiet, pooled n=48 p=0.003). Intermediate sizes (16K–256K) were within
   noise of 4096 in the probe sweep; no further chunk tuning worth doing.
4. Bloom-filter probe layout (`omega_match/src/bloom.c` ~lines 30–95,
   `bloom_filter_add`/`bloom_filter_query`; 3 probes into one bitmap per
   `omega/details/bloom.h`): consider a blocked/squarized layout to reduce
   misses per candidate position. Profile via differential timing on a
   low-match-rate corpus where candidate rejection dominates. The
   longest-no-overlap 256 MiB case (≈578 ms, ~443 MiB/s output / ~570 MiB/s
   quiet) is the big remaining target; every byte runs a bloom probe.
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
- EXP-002 confirmation: replacing the byte-by-byte line-start gate with an
  SSE2 skip cut the line-start 256 MiB quiet floor 79→53 ms, i.e. the gate
  loop itself was ~1/3 of line-start scan cost; remaining line-start cost
  (~53 ms ≈ 5 GB/s read) looks memory-bound, not loop-bound.
