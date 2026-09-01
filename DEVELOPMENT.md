# OmegaMatch Development and Performance Guide

This guide covers reproducible builds, correctness testing, benchmarking,
profiling, and PGO. Performance numbers are only meaningful when the input
bytes, output work, pattern compilation, storage, and comparator semantics are
controlled.

## Build and test

```sh
cmake --preset release -DOMEGA_MATCH_REQUIRE_OPENMP=ON
cmake --build --preset release
ctest --preset release --output-on-failure
```

For a sanitizer build:

```sh
cmake -S . -B build-gcc-sanitize -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug -DENABLE_SANITIZERS=ON
cmake --build build-gcc-sanitize
ctest --test-dir build-gcc-sanitize --output-on-failure
```

The Python tests need `pytest` and `cffi`. A temporary virtual environment is
enough:

```sh
python3 -m venv /tmp/omega-match-venv
/tmp/omega-match-venv/bin/pip install pytest cffi argcomplete
TMPDIR=/tmp /tmp/omega-match-venv/bin/python -m pytest -q
```

## Performance testing

### Reproducible scaling harness

Use `scripts/benchmark_scaling.py` for performance claims and comparisons with
GNU grep or ripgrep:

```sh
python3 scripts/benchmark_scaling.py \
  --olm release=build-gcc-release/olm \
  --olm pgo=build-gcc-pgo-use/olm \
  --sizes-mib 4,16,64,256 \
  --cases longest-no-overlap,line-start,line-end \
  --threads 8 --runs 5 --mode output \
  --work-dir /tmp/omega-match-scaling
```

The harness:

- generates exact-size corpora in `--work-dir`;
- compiles each OmegaMatch pattern store outside the timed region;
- strips the source UTF-8 BOM so offsets agree across byte-oriented tools;
- orders comparator patterns longest-first and regex-escapes anchored forms;
- consumes every byte of stdout instead of redirecting it to `/dev/null`;
- checks output size and SHA-256 on the smallest corpus; and
- writes all samples and environment metadata to CSV and JSON.

`--mode output` compares complete CLI work. `--mode quiet` passes `--quiet` to
OmegaMatch only and is intended for matcher/thread-scaling analysis, not a
direct comparison with grep or ripgrep. Use `--skip-grep` and
`--skip-ripgrep` for OmegaMatch-only runs.

Put large generated corpora on a native, fast filesystem. In WSL, `/tmp` or a
Linux home directory avoids making Windows-mounted filesystem behavior part of
the result. Warm-cache results still include mapping and page traversal but do
not represent cold-storage latency.

### Corrected September 2026 snapshot

Environment: Ubuntu 24.04.3 under WSL2, Intel Core Ultra 7 165H, GCC 13.3,
eight OpenMP threads, GNU grep 3.11, ripgrep 15.2, 29,156 name patterns, and a
warm 256 MiB KJV-derived corpus on `/tmp`. Values are medians of five runs for
longest matching and three runs for anchors. Complete outputs were consumed
at every size; byte counts and SHA-256 digests agreed on the 4 MiB validation
corpus.

| Mode | Original PGO (`cbb6ae4`) | Optimized PGO | GNU grep | ripgrep |
|---|---:|---:|---:|---:|
| longest + no-overlap | 148 MiB/s | 266 MiB/s | 196 MiB/s | 129 MiB/s |
| line start | 179 MiB/s | 1,018 MiB/s | 24 MiB/s | 252 MiB/s |
| line end | 198 MiB/s | 606 MiB/s | 27 MiB/s | 51 MiB/s |

OmegaMatch used eight OpenMP threads. GNU grep is single-threaded, and
ripgrep's `-j 8` does not guarantee eight-way processing of one input file.
OmegaMatch loaded a store compiled outside the timed region; grep and ripgrep
parsed their pattern files during every invocation. This measures the intended
compile-once/match-many CLI workflow, including each comparator's unavoidable
startup, rather than isolated scan kernels. The anchored tools also compile
29,156 regular expressions, which dominates much of their elapsed time. At
256 MiB, output sizes were 60,867,206 bytes for longest matching, 16,418,305
bytes for line start, and zero for line end.

Input-size scaling for output-equivalent `longest + no-overlap`:

| Input | Original PGO | Optimized PGO | GNU grep | ripgrep |
|---:|---:|---:|---:|---:|
| 4 MiB | 113 MiB/s | 154 MiB/s | 83 MiB/s | 31 MiB/s |
| 16 MiB | 126 MiB/s | 224 MiB/s | 176 MiB/s | 72 MiB/s |
| 64 MiB | 137 MiB/s | 274 MiB/s | 203 MiB/s | 109 MiB/s |
| 256 MiB | 148 MiB/s | 266 MiB/s | 196 MiB/s | 129 MiB/s |

The larger files amortize startup and pattern-engine construction. OmegaMatch
does not progressively lose throughput as the haystack grows in this test.

Output-suppressed PGO matcher scaling on the 256 MiB corpus (`--mode quiet`,
median of seven runs):

| Threads | longest + no-overlap | line start | line end |
|---:|---:|---:|---:|
| 1 | 99 MiB/s | 442 MiB/s | 114 MiB/s |
| 2 | 170 MiB/s | 729 MiB/s | 211 MiB/s |
| 4 | 289 MiB/s | 1,118 MiB/s | 369 MiB/s |
| 8 | 443 MiB/s | 1,618 MiB/s | 653 MiB/s |
| 16 | 610 MiB/s | 2,161 MiB/s | 894 MiB/s |

Scaling is substantial but not linear: memory bandwidth, result merging,
allocation, scheduling, and output become limiting factors. Dense positive
matches can therefore scale differently from negative or sparse workloads.

Pattern-count tests make that distinction visible. On a 64 MiB corpus, nested
name subsets reduced release OmegaMatch throughput from about 280 MiB/s at 256
patterns to 118 MiB/s at 29,156 patterns while output grew from zero to
13.8 MiB. With synthetic non-matching 16-byte patterns, OmegaMatch instead
stayed between 833 and 919 MiB/s from 256 through 65,536 patterns; at 65,536,
GNU grep reached 276 MiB/s and ripgrep 159 MiB/s. The search structure scales
well with pattern count, but match density and result materialization can still
dominate an end-to-end workload.

### Legacy harness

`perf_test.py` remains a broad cross-platform smoke benchmark. It now divides
by the physical haystack size and fully drains grep output. Older revisions
used a hard-coded 1,024 MiB numerator even though `data/kjv.txt` is 4,606,957
bytes. They also sent grep stdout directly to `/dev/null`; GNU grep detects
that destination and can stop after its first match. Historical 7--20 GB/s and
50--500x claims produced by that setup are invalid.

For quiet A/B comparisons with the legacy matrix:

```sh
python3 perf_test.py --no-grep --no-debug \
  --release-binary build-gcc-release/olm \
  --tests longest+no-overlap,line-start,line-end --show-status
```

Keep the test list and binary type identical, repeat noisy cases, and preserve
each generated CSV before the next run.

## Profiling

Callgrind is useful here because it works in WSL without kernel performance
counter access and provides deterministic instruction, cache, and branch
comparisons. Build an optimized binary with debug information, then keep the
profile corpus small because Valgrind is intentionally slow:

```sh
cmake -S . -B build-gcc-profile -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DOMEGA_MATCH_REQUIRE_OPENMP=ON
cmake --build build-gcc-profile

valgrind --tool=callgrind --cache-sim=yes --branch-sim=yes \
  --callgrind-out-file=/tmp/callgrind-longest.out \
  build-gcc-profile/olm match --quiet --threads 1 \
  --longest --no-overlap patterns.olm haystack-1m.bin

python3 scripts/callgrind_report.py /tmp/callgrind-longest.out
callgrind_annotate --inclusive=yes --auto=yes \
  /tmp/callgrind-longest.out build-gcc-profile/olm
```

One-thread Callgrind results on the 1 MiB corpus:

| Mode | Original instructions | Optimized instructions | Reduction |
|---|---:|---:|---:|
| longest + no-overlap | 474.3 M | 128.7 M | 72.9% |
| line start | 482.0 M | 28.7 M | 94.0% |
| line end | 473.4 M | 127.8 M | 73.0% |

The original profile showed that anchors still ran the full per-byte matcher.
It also exposed two dominant ordinary-search costs: binary searches for
three- and four-byte patterns at every byte, and three eager random Bloom
filter loads even though most candidates fail the first bit. Prefix bitmaps,
lazy Bloom probing, and explicit line-start candidates account for most of the
reduction. The optimized longest profile recorded about 384,000 simulated L1
data misses and 448,000 branch mispredictions.

Other useful tools:

- `perf stat` and `perf record` provide real hardware counters and sampled
  stacks when the host/WSL kernel permits access.
- `hyperfine` provides convenient warmups, repetitions, parameter sweeps, and
  exported timing data; the repository harness adds correctness validation.
- `gprof` can give a quick function-level CPU profile, but instrumentation and
  OpenMP make it less representative than Callgrind or `perf` for this code.
- Valgrind Massif or `heaptrack` can explain memory growth when pattern or
  result counts increase.

## Profile-guided optimization

Run the platform workflow after changing hot matching code:

```sh
python3 scripts/pgo_workflow.py --compiler gcc --clean
# --compiler clang and --compiler msvc are also supported
```

The training set covers compilation, transformations, filters, thread counts,
chunk sizes, large datasets, output modes, and explicit line-start, line-end,
and exact-line searches. Always compare PGO with the same source revision's
ordinary release build; stale profile data or an old PGO executable gives a
misleading result.

## Compiled format and memory mapping

Version 4 of the compiled format pads serialized sections so the memory-mapped
Bloom `uint64_t` array and keyed short-pattern arrays are naturally aligned.
The loader validates the new Bloom alignment and remains able to load versions
1--3. Older binaries intentionally reject version 4, so regenerate compiled
stores when deploying the new binary. Layout assertions in
`tests/compile_match.py` guard the section offsets and file extent.

## General performance practice

- Benchmark release or PGO builds with sanitizers and verbose statistics off.
- Separate compile time, matcher compute time, output formatting, and storage
  latency when diagnosing a change.
- Use medians and keep raw samples; rotate tool order to reduce thermal bias.
- Test multiple haystack sizes, pattern counts, match densities, and thread
  counts. A single repeated corpus does not establish universal scaling.
- Verify outputs before comparing speeds. Similar-looking flags across tools
  do not always imply identical leftmost/longest or anchoring semantics.
