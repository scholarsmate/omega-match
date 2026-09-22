# OMEGATUNE — OmegaMatch Autonomous Optimization Journal

This file is the persistent memory for an overnight autonomous optimization
campaign driven by fresh Hermes cron sessions. Each session reads this file
first, performs exactly ONE bounded experiment, appends the result, and exits.

## FINAL REPORT — campaign finalization (2026-09-22)

### Executive summary

The overnight campaign ran six bounded experiments (EXP-001 … EXP-006), all
accepted, on branch `perf/omega-tune-2026-09`. Every change was gated on
18/18 CTest passes plus byte-identical-output differentials against the
pre-change binary. Cumulatively, vs the original baseline binary (same
session, interleaved A/B, this finalization):

- longest-no-overlap 256 MiB (primary case): **673 ms → 590 ms, −12.3%**
  (output mode); quiet search floor 501 → 477 ms, −4.8%
- longest-no-overlap 64 MiB: **176 ms → 149 ms, −15.3%**
- line-start longest-no-overlap 256 MiB: **130 ms → 78 ms, −40.0%**
- line-start longest-no-overlap 64 MiB: **37 ms → 23 ms, −37.8%**
- word-boundary longest-no-overlap 256 MiB (quiet): **1146 ms → 334 ms,
  −70.9%** — the single largest win, from removing serial candidate
  materialization (EXP-004) plus the SSE2 boundary skip (EXP-005)

No experiment was rejected or inconclusive; two sub-variants were rejected
mid-experiment on regression evidence (EXP-005 always-inline variant;
EXP-006 prefetch/batch bloom variants — recorded as dead ends). The final
binary reproduces the EXP-006 recorded baseline (quiet lno ≈477–485 ms) and
is byte-identical to the original on every flag combination tested.

### Original baseline (commit 407f128 lineage, binary `olm-baseline`,
sha256 3e3eec7b…)

Harness medians (7 runs, match-only, output mode, `--threads 8`):
- longest-no-overlap 64 MiB: 0.1693 s (378 MiB/s)
- longest-no-overlap 256 MiB: ~0.66–0.68 s (~375–395 MiB/s)
- line-start 64 MiB: 0.0348 s (1840 MiB/s)

Direct wall-time (this finalization's interleaved A/B against the preserved
original binary, medians of 7 reps for 256 MiB / 5 for 64 MiB, output mode
unless noted): lno 256 = 673 ms (651–727); lno 64 = 176 ms (172–180);
ls 256 = 130 ms (124–140); ls 64 = 37 ms (36–38); lno 256 quiet = 501 ms
(492–533); wb 256 quiet = 1146 ms (1125–1187).

### Final baseline (HEAD 27ecca3, EXP-006 accepted state)

Harness medians (this finalization, 7 runs, match-only, output mode):
- longest-no-overlap 64 MiB: **0.1484 s (431.2 MiB/s)**
- longest-no-overlap 256 MiB: **0.6301 s (406.3 MiB/s)**
- line-start 64 MiB: **0.0243 s (2630.1 MiB/s)**
- line-start 256 MiB: **0.0851 s (3008.9 MiB/s)**

Direct wall-time (same interleaved A/B session as above): lno 256 = 590 ms
(586–603); lno 64 = 149 ms (146–152); ls 256 = 78 ms (74–89); ls 64 = 23 ms
(22–23); lno 256 quiet = 477 ms (469–493); wb 256 quiet = 334 ms (326–356).
Harness correctness lines: `longest-no-overlap: OK (14465441 bytes)`,
`line-start: OK (3855881 bytes)`.

### Cumulative percentage improvement (same-session A/B, final vs original
binary — the authoritative figures; artifact
`~/.hermes/cache/scratch/omegafinal/final-ab.tsv`)

| Case (threads 8)                    | Original | Final   | Δ        | %      |
|-------------------------------------|---------:|--------:|---------:|-------:|
| longest-no-overlap 256 MiB (output) |   673 ms |  590 ms |    −83 ms | −12.3% |
| longest-no-overlap 256 MiB (quiet)  |   501 ms |  477 ms |    −24 ms |  −4.8% |
| longest-no-overlap 64 MiB (output)  |   176 ms |  149 ms |    −27 ms | −15.3% |
| line-start lno 256 MiB (output)     |   130 ms |   78 ms |    −52 ms | −40.0% |
| line-start lno 64 MiB (output)      |    37 ms |   23 ms |    −14 ms | −37.8% |
| word-boundary lno 256 MiB (quiet)   |  1146 ms |  334 ms |   −812 ms | −70.9% |

Final-vs-original separation was clean in every rep of lno64, ls256, ls64
and wb256 (ranges never overlapped); on lno256 the base max (651) and final
min (586) also never overlapped. Harness comparison agrees directionally
(64 MiB lno −12.3%, line-start 64 MiB −30.2%) but cross-session absolute
numbers carry the powersave-governor drift caveat noted throughout.

### Accepted experiments (all on `perf/omega-tune-2026-09`)

1. **EXP-001** `45902c5` — fast u64 writer replaces snprintf in
   match-output loop. −12.2% lno 256 output, −18.5% line-start 256.
2. **EXP-002** `9830f4c` — SSE2 skip to next line-start in line-start
   gate. −25 to −33% on line-start cases.
3. **EXP-003** `56bd19c` — default OMP static chunk 4096 → 1 MiB.
   −7 to −10 ms on lno 256 quiet (pooled n=48, sign test p=0.003).
4. **EXP-004** `e933485` — route `--word-boundary` through the
   single-pass in-loop gate (dead-code the materialization path).
   −68.1% on word-boundary (1149 → 366 ms).
5. **EXP-005** `37ce3f0` — SSE2 skip to next word boundary in the in-loop
   gate (noinline variant). −3.3% on wb; code-layout lesson recorded.
6. **EXP-006** `27ecca3` — inline `bloom_filter_query` into matcher.c TU
   (kills per-position PLT call). −3.4% on lno 256 (p=10⁻⁸, 37/40 pairs).

### Rejected / inconclusive experiments

No top-level experiment was rejected; acceptance rate 6/6. Rejected
sub-variants and dead ends (see Known dead ends above):
- EXP-005 always-inline SIMD skip: wb win kept but +3.9% regression on the
  non-wb control (18/18 pairs) → reverted to `noinline` form (accepted).
- Bloom layout/prefetch/batching variants (EXP-006 microbenchmark): all
  no-better-or-worse; 64 KiB bloom never leaves L1/L2 on base corpus.
- No result in this campaign was left inconclusive; EXP-003's small effect
  was resolved by pooling n=48 rather than declared inconclusive.

### Remaining bottlenecks

- **lno 256 quiet floor ≈ 477 ms (~535 MiB/s at 8 threads)**: dominated by
  the per-position scan itself — `pack_gram`/`fast_gram_hash` chain plus
  u32 candidate-list append and `core_match` bookkeeping — not I/O, not the
  bloom probe (now inlined).
- **line-start ≈ 53–60 ms quiet at 256 MiB (~5 GB/s effective)**: likely
  memory-bandwidth bound; further SIMD width (AVX2) needs a
  compute-bound (dense-newline) demonstration first.
- **word-boundary ≈ 334 ms**: also close to memory-bound after EXP-004/005.
- Output path is now cheap (EXP-001); the residual output-vs-quiet gap is
  ~113 ms for 4.07M lines (~28 ns/line), i.e. buffered write + emit loop.

### Recommended next experiments

1. Per-position scan bookkeeping: reduce `pack_gram`/`fast_gram_hash`
   chain cost at every position (biggest remaining target per EXP-006).
2. u32 candidate-list append + `core_match` per-position bookkeeping.
3. `OUTPUT_BUFFER_SIZE` 64 KiB → 256 KiB/1 MiB in
   `print_results_buffered_fd` (cheap, isolated, output mode only).
4. Delete the dead `use_wb_candidate_path`-guarded materialization code
   (hygiene; EXP-004/005 settled the wb path).
5. AVX2 variants of the SSE2 skips — ONLY after a dense-corpus A/B proves
   the skips are compute- not bandwidth-bound.
6. Fix `olm compile` in this sandbox, then build a 100k-pattern corpus
   whose bloom spills past L2 to re-open probe-layout work.
7. Verify `--line-end` + `--line-start` zero-match intent (EXP list item 5).

### Exact reproduction commands

```bash
cd /home/davin/git/OMEGA/omega-match-tune   # worktree, branch perf/omega-tune-2026-09

# Build
cmake --preset release -DOMEGA_MATCH_REQUIRE_OPENMP=ON   # NOTE: cache here is Unix Makefiles;
cmake --build --preset release                           # delete CMakeCache.txt first if re-gen'ing with Ninja

# Correctness (python_pytest blocked in this sandbox — excluded, pre-existing)
ctest --test-dir build-gcc-release -E python_pytest

# Primary benchmark harness (corpus auto-regenerated in /tmp/omega-match-scaling if missing)
python3 scripts/benchmark_scaling.py --olm release=build-gcc-release/olm \
  --sizes-mib 64,256 --cases longest-no-overlap,line-start --threads 8 --runs 7 \
  --mode output --olm-pattern-mode both --work-dir /tmp/omega-match-scaling \
  --skip-grep --skip-ripgrep

# Direct wall-time A/B methodology (powersave governor makes cross-session
# absolute numbers unreliable; interleave old vs new binary per rep):
#   date +%s%N around: olm match --threads 8 [--quiet] [--longest --no-overlap |
#   --line-start --longest --no-overlap | --word-boundary --longest --no-overlap]
#   patterns-base.olm haystack-{64,256}m.bin   (7+ reps, medians, check range separation)

# Byte-identity differential vs original baseline binary (14 checks):
bash ~/.hermes/cache/scratch/omegafinal/identity-check.sh
```

### Final branch / commit

- Final branch: `perf/omega-tune-2026-09` (worktree
  `/home/davin/git/OMEGA/omega-match-tune`); nothing pushed to any remote.
- Final accepted code commit: `27ecca3` (EXP-006).
- Correctness at finalization: CTest 18/18 pass; final-vs-original binary
  byte-identity differential 14/14 OK (4M + 64M corpora × 7 flag combos);
  harness internal correctness checks OK.

## Standing rules

- Work happens ONLY on branch `perf/omega-tune-2026-09` in the worktree
  `/home/davin/git/OMEGA/omega-match-tune`. Never modify `main`.
- Never push to any remote.
- Never discard pre-existing user work; verify `git status` before changes.
- Never remove or weaken correctness tests.
- Never report a performance improvement without measurements.
- One experiment per session. Do not start a second experiment.

## Campaign state

- **CAMPAIGN CLOSED 2026-09-22 (finalization pass).** Final branch
  `perf/omega-tune-2026-09` @ 27ecca3 (code) + final report commit. All
  figures above are final; see FINAL REPORT at top of this file.
- Current accepted branch: `perf/omega-tune-2026-09`
- Current HEAD at campaign start: 407f128 (same as origin/main)
- Current accepted baseline: EXP-006 (bloom_filter_query inlined into
  matcher.c TU) — see EXP-006 entry under accepted experiments.
- Session log: EXP-001 accepted (2026-09-21/22), EXP-002 accepted
  (2026-09-22), EXP-003 accepted (2026-09-22), EXP-004 accepted
  (2026-09-22), EXP-005 accepted (2026-09-22), EXP-006 accepted
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

### EXP-005 — SSE2 skip to next word boundary in the in-loop gate — ACCEPTED

Hypothesis (recommended item 0 after EXP-004): with the materialization
path dead, `--word-boundary` runs the in-loop gate byte-at-a-time — every
interior word byte is re-tested individually before the bloom probe. On the
base corpus ~104M of 268M positions are boundaries, so ~160M interior
positions pay a scalar test each. An SSE2 skip that jumps directly from a
failed position to the next class-change byte should remove that scalar
walk (EXP-002-style, for word boundaries instead of newlines).

Implementation (+78/−1 lines in `omega_match/src/matcher.c`): new
`word_class_mask()` (SSE2: classify 16 bytes as `[A-Za-z0-9_]` with signed
compares; `(v|0x20)` cannot alias bytes ≥0x80 into the letter range) and
`next_word_boundary_pos()` (mask XOR `mask<<1|carry` gives in-block
boundary bits; `__builtin_ctz` picks the first ≥ pos; scalar tail past the
last full aligned block; page-safety argument identical to EXP-002's
`next_line_start_pos` — loads stay inside aligned blocks fully contained
in [0, end)). The failed-branch of the wb gate calls it and rewinds `pos`
by 1 so the loop's `++pos` lands on the next boundary. `pos == 0`
(chunk-local) is kept as a candidate, mirroring the `pos > 0` guard. In
combined line-start+wb mode the two skips alternate; each skipped region
provably lacks one of the two predicates, so no valid match is jumped.

Variant history (important layout lesson):
- `exp005` (helper `OLM_ALWAYS_INLINE`): wb 378→363 ms, BUT the plain
  control regressed +20 ms (+3.9%, n=18 pooled, 18/18 pairs) — inlining
  the SIMD block bloated the shared scan loop for non-wb runs where the
  branch is never taken.
- `exp005b` (helper `__attribute__((noinline))`): control regression gone
  (paired mean −3.9 ms, 5/10 — noise), wb win retained. ACCEPTED form.
  Lesson: SIMD skip helpers called off the hottest path must stay
  noinline; always-inline them poisons adjacent-loop code layout.

Correctness:
- CTest 18/18 pass (`-E python_pytest`) for both exp005 and exp005b.
- 88-combo edge-case differential (tiny punct/word corpus x flag combos vs
  head binary): 0 mismatches.
- Byte-identity vs head binary on 256 MiB corpus across 7 flag combos
  (wb, wb-lno, wb-ic, wb-ls-lno, lno, ls, plain): 7/7 OK, exit codes equal.

Benchmark (alternating-order A/B vs head binary, `--threads 8`, quiet,
256 MiB base corpus; artifacts `exp005b-ab.tsv` n=10 + `exp005-final.tsv`
n=12, pooled):
- word-boundary: head med 365 ms (n=22, 349-383) vs exp med 353 ms
  (n=22, 328-366): −12 ms (−3.3%), 12/12 paired-rep wins in exp005-final,
  10/10 in the wb block of exp005b-ab.
- control longest-no-overlap: head med 504 vs exp med 513 raw, but paired
  mean −3.9 ms with 5/10 wins — ranges overlap heavily; treated as no
  regression (the +20 ms inline-variant regression is definitively gone).
Modest win: the skip helps but wb is now close to memory-bandwidth-bound;
most gate savings were already captured by EXP-004.

New accepted baseline (post-EXP-005, wall medians, `--threads 8`, quiet,
256 MiB base corpus):
- word-boundary longest-no-overlap: ≈ 353 ms (was ≈ 366 ms)
- longest-no-overlap: ≈ 504 ms quiet (unchanged)
- line-start: ≈ 53-79 ms (EXP-002 territory; unchanged)

### EXP-006 — inline bloom_filter_query into matcher.c's TU — ACCEPTED

Hypothesis (from item 4, reframed by microbenchmark evidence): the bloom
probe itself (random-access layout) is NOT the scan bottleneck, but the
*out-of-line PLT call* into `bloom_filter_query` is paid at every scan
position. Evidence chain:
- `patterns-base.olm` bloom = 512 Kbit → 64 KiB bitmap, 6.0% fill → fits
  L1/L2; ~9,155 probe hits per 64 Mi of haystack text (~144 ppm hit rate,
  3-probe FPR ~2.2e-1 for a full bitmap but empirically tiny since the
  corpus text rarely hashes to a live 4-gram). The probe's 2nd/3rd random
  accesses almost never execute — so layout changes (blocked/squarized
  bloom) have no fuel to burn.
- Standalone microbenchmark (`bloom_micro`, 64 MiB prefix of
  haystack-64m.bin against the real .olm bits, single thread): current
  serial short-circuit query 114-117 ms; prefetch-h2 128-133 ms (WORSE —
  prefetch of probe-2 on the ~always-miss path adds work); batched 8-wide
  probe-1 loads 141-160 ms (WORSE — breaks the short-circuit); software-
  pipelined next-position probe-1 111-114 ms (~neutral). Conclusion: the
  probe *algorithm* is already at its local optimum; the dead ends are
  layout/prefetch/batching variants.
- Disassembly of `matcher.c.o`: `bloom_filter_query` appears as
  `R_X86_64_PLT32` relocation — a real call per candidate position in
  `core_match`'s hot loop (LTO is OFF by default:
  `OMEGA_MATCH_ENABLE_LTO=OFF`), while `fast_gram_hash` and the short
  matcher helpers are all inlined. The call forces `cand` into arg
  registers, clobbers caller registers across the hottest branch in the
  program, and blocks cross-statement scheduling around the probe.

Implementation (+32/−3 lines in `omega_match/src/matcher.c`): added
`#include "omega/details/hash.h"` and a `static OLM_ALWAYS_INLINE
bloom_filter_query_inline()` — a byte-for-byte copy of `bloom.c`'s query
body — and switched BOTH `core_match` call sites (candidate-list loop
~line 1330, single-pass loop ~line 1478) to it. `bloom.c`'s out-of-line
`bloom_filter_query` left untouched (still used elsewhere / by external
linkers). Verified after build: `objdump -dr matcher.c.o | grep -c
bloom_filter_query` → 0 PLT refs (probe fully inlined). Per the EXP-005
code-layout lesson this helper IS on the hot path for all modes, so
always_inline is correct here (unlike the off-path SIMD skips), and the
non-probe control mode (line-start, where the probe runs but the SSE2
skip dominates) was A/B'd as the regression check.

Correctness:
- CTest 18/18 pass (`-E python_pytest`).
- Byte-identical stdout vs head binary AND identical exit codes across
  3 corpora (4M/64M/256 MiB) × 7 flag combos (lno, ls-lno, wb-lno,
  ic-lno, wb+ls-lno, ls, plain) = 21 checks + 16M lno control: 22/22 OK.

Benchmark (interleaved A/B vs head binary, `--threads 8`, quiet, 256 MiB
base corpus; artifacts `exp006-ab.tsv` n=12 + `exp006-final.tsv` n=14 +
`exp006-final2.tsv` n=14 on the final binary, pooled
`exp006-poolall.tsv` for the primary case; final2 = 14 reps after both
call sites were converted):
- longest-no-overlap 256 MiB: head med 504.0 ms (464-590) vs exp med
  485.0 ms (474-529): paired median delta −17.0 ms (−3.4%), mean −17.9 ms,
  exp faster in 37/40 pairs (sign test one-sided p ≈ 10⁻⁸). Final-binary
  alone (final2, n=14): −17.0 ms median, 13/14 wins — consistent.
- word-boundary longest-no-overlap: head med 358.0 vs exp med 352.0:
  paired median −4.0 ms (−1.1%), 18/24 wins — consistent direction, same
  mechanism (also crosses the probe), magnitude within wb noise band.
- line-start longest-no-overlap (control): paired median 0.0 ms, 10/24
  wins — pure noise, no regression (the always_inline bloat concern from
  EXP-005 does not materialize; helper body is 3 test-and-branch blocks).

New accepted baseline (post-EXP-006, wall medians, `--threads 8`, quiet,
256 MiB base corpus):
- longest-no-overlap: ≈ 485 ms (was ≈ 504 ms)
- word-boundary longest-no-overlap: ≈ 352 ms (was ≈ 358 ms; within-band)
- line-start: ≈ 60 ms (unchanged; within noise)

## Known dead ends

- Bloom-probe layout/ILP variants (EXP-006 microbenchmark evidence,
  `bloom_micro.c` in scratch): prefetching probe-2's line on the
  short-circuit path (128-133 vs 114-117 ms baseline), 8-wide batched
  probe-1 loads (141-160 ms), and software-pipelined next-position
  probe-1 (~neutral) are all no-better-or-worse than the current serial
  short-circuit query. The base .olm bloom is 64 KiB at 6% fill — it
  lives in L1/L2 and the 2nd/3rd probes almost never execute, so
  blocked/squarized bloom or prefetch schemes have no cache-miss fuel.
  Don't re-litigate bloom layout without a corpus where the bloom
  actually spills (e.g. 100k-pattern compile — blocked on the `olm
  compile` sandbox failure above).

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

0. ~~Word-boundary follow-up~~ DONE as EXP-005 (accepted, −3.3% on wb;
   wb now ≈353 ms and close to memory-bandwidth-bound). Follow-ups that
   remain: AVX2 version of `next_word_boundary_pos` (32 B/iter — but see
   bandwidth caveat in item 1; measure dense-vs-sparse corpora first), and
   deleting the dead `use_wb_candidate_path`-guarded code in matcher.c now
   that EXP-004+005 have settled the wb path.
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
4. ~~Bloom-filter probe layout~~ — investigated as EXP-006 (accepted:
   inlined the query into matcher.c's TU, −3.4% on the primary case).
   Layout/prefetch/batching variants are now recorded dead ends (see
   Known dead ends) — the 64 KiB base-corpus bloom never leaves L1/L2.
   Remaining probe-side idea: only viable once `olm compile` works to
   build a corpus whose bloom spills past L2 (100k patterns).
   Biggest remaining targets are elsewhere: e.g. the u32 candidate-list
   append + `core_match` per-position bookkeeping itself, and
   `pack_gram`/`fast_gram_hash` chain cost at every position.
5. `--line-end` + `--line-start` combined mode currently produces zero
   matches on the base corpus — verify intent before optimizing it.

## Profiling findings

- Code-layout sensitivity (EXP-005): `OLM_ALWAYS_INLINE` on the SIMD
  word-boundary skip helper cost the NON-wb control path +20 ms (+3.9%)
  by bloating the shared scan loop, even though the branch is never
  taken there; `noinline` removed the regression entirely while keeping
  the wb win. Any future SIMD helper on a conditional path in the scan
  loop: keep it noinline and A/B the non-conditional control mode.
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
