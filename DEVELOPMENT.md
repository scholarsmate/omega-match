# OmegaMatch Development & Performance Guide

This document collects build instructions, performance benchmarking guidance, PGO workflows, A/B comparison tips, implementation details, and CI/CD information that were formerly in the top-level README.

## Contents
- [Build](#build)
- [Performance Testing](#performance-testing)
  - [Running Performance Tests](#running-performance-tests)
  - [Test Results Overview](#test-results-overview)
  - [Latest Snapshot](#latest-linux-wsl2-almalinux-10-gcc-1421-snapshot--aug-2025)
  - [Understanding the Results](#understanding-the-results)
  - [Test Data](#test-data)
  - [Targeted Testing](#targeted-testing)
  - [Cross-Platform Testing](#cross-platform-testing)
- [A/B Performance Testing (Branches or Binaries)](#ab-performance-testing-branches-or-binaries)
- [Performance Visualization](#performance-visualization)
- [Profile Guided Optimization (PGO) Builds](#profile-guided-optimization-pgo-builds)
- [Implementation Details](#implementation-details)
- [Compiler Options](#compiler-options)
- [General Performance Notes](#general-performance-notes)
- [CI/CD](#cicd)

---
## Build
This project uses CMake build presets.

### Standard Build (CLI tool + libraries)
```sh
cmake --preset release
cmake --build --preset release
ctest --preset release --output-on-failure
```
Require OpenMP explicitly:
```sh
cmake --preset release -DOMEGA_MATCH_REQUIRE_OPENMP=ON
```
### Language Bindings Build (libraries only)
```sh
cmake --preset release -DOMEGA_MATCH_BUILD_CLI=OFF
cmake --build --preset release
cmake --install build-gcc-release --prefix /usr/local
```
Creates static + shared libraries only (no CLI) for Python, Node.js, Go, Rust, etc.

### Windows (MSVC)
```sh
cmake --preset msvc-release
cmake --build --preset msvc-release
```
### Linux (GCC)
```sh
cmake --preset release
cmake --build --preset release
```
### macOS (Clang)
Install OpenMP runtime:
```sh
brew install libomp
```
Then:
```sh
cmake --preset macos-release
cmake --build --preset macos-release
```
### Testing
```sh
ctest --preset <preset-name> --output-on-failure
```
### Packaging
```sh
cpack -G TGZ --config build-gcc-release/CPackConfig.cmake
cpack -G DEB --config build-gcc-release/CPackConfig.cmake
cpack -G RPM --config build-gcc-release/CPackConfig.cmake
# Windows (WiX installed)
cpack -G WIX --config build-msvc-release/CPackConfig.cmake
```
---
## Performance Testing
`perf_test.py` benchmarks debug / release / PGO builds and (optionally) `grep`.

When `--no-grep` is used the harness adds `--quiet` automatically (reduces IO noise only).

### Running Performance Tests
```sh
python perf_test.py --show-status
python perf_test.py --tests baseline,ignore-case,word-boundary --show-status
python perf_test.py --no-grep --show-status
python perf_test.py --tests list
```
### Test Results Overview
Example (Windows MSVC excerpt):
```
Test Case                              | Debug MB/s | Release MB/s | Grep MB/s | Ratio  | Compare
... (truncated) ...
```
### Latest Linux (WSL2 AlmaLinux 10, GCC 14.2.1) Snapshot – Aug 2025
Environment:
| Item | Value |
|------|-------|
| OS | AlmaLinux 10 (WSL2) |
| CPU | Intel Core Ultra 7 165H (22 HW threads reported) |
| Compiler | GCC 14.2.1 |
| OpenMP threads | 8 |
| PGO Training | `scripts/pgo_workflow.py --compiler gcc` (all 40 workloads succeeded) |
Key throughput (MB/s) for selected scenarios:
| Test Case | Debug | Release | Release+PGO | Δ PGO vs Release |
|-----------|-------|---------|-------------|------------------|
| baseline | 10,338 | 15,286 | 18,003 | +17.8% |
| ignore-case+no-overlap+longest | 4,488 | 7,584 | 8,182 | +7.9% |
| line-end | 12,228 | 23,389 | 23,411 | ~0% |
| line-end+ignore-case | 7,870 | 14,923 | 16,546 | +10.9% |
| line-start+line-end | 11,475 | 21,722 | 20,740 | -4.5% (variance) |
| longest+no-overlap | 10,306 | 19,962 | 20,206 | +1.2% |
| longest+no-overlap+word-boundary | 9,170 | 18,506 | 19,204 | +3.8% |
Observations:
* PGO: 5–18% gains on transformation-heavy paths; anchor-heavy already near peak.
* Minor regression within variance.
* Grep ratios (50x–200x+) depend on environment & normalization.
Reproduce:
```bash
cmake --preset debug && cmake --build --preset debug
cmake --preset release && cmake --build --preset release
python3 scripts/pgo_workflow.py --compiler gcc
python3 perf_test.py --show-status
python3 scripts/plot_perf.py
```
Plot: `images/perf_results_log.png`.
### Understanding the Results
Columns:
* Debug / Release / Grep MB/s – throughput
* Ratio – Release OLM ÷ Grep
* Compare – Output diff (OK = identical)
### Test Data
* Patterns: `data/names.txt` (~2K)
* Haystack: `data/kjv.txt` (~4MB)
* Logical size normalization constant (1GB) in harness.
### Targeted Testing
```sh
python perf_test.py --tests baseline,ignore-case,word-boundary
python perf_test.py --tests line-start,line-end,line-start+line-end
python perf_test.py --tests longest+no-overlap,longest+no-overlap+word-boundary
```
### Cross-Platform Testing
Uses platform grep automatically or skips.
---
## A/B Performance Testing (Branches or Binaries)
Compare two builds with identical test sets and preserve CSVs:
Windows (PowerShell):
```powershell
$perf = "$(Get-Location)\build-msvc-release\Release\olm.exe"
$main = "$(Get-Location)\build-msvc-release-2\Release\olm.exe"
python perf_test.py --no-grep --no-debug --release-binary $perf --tests baseline,line-start+line-end
Copy-Item perf_results.csv perf_perf.csv
python perf_test.py --no-grep --no-debug --release-binary $main --tests baseline,line-start+line-end
Copy-Item perf_results.csv perf_main.csv
python .\scripts\compare_branches.py perf_main.csv perf_perf.csv
```
Linux:
```bash
perf=./build-gcc-release/olm
main=../omega-match-main/build-gcc-release/olm
python3 perf_test.py --no-grep --no-debug --release-binary "$perf" --tests baseline,line-start+line-end
cp perf_results.csv perf_perf.csv
python3 perf_test.py --no-grep --no-debug --release-binary "$main" --tests baseline,line-start+line-end
cp perf_results.csv perf_main.csv
python3 scripts/compare_branches.py perf_main.csv perf_perf.csv
```
Tips: idle system, copy CSVs quickly, repeat outliers.
---
## Performance Visualization
1. `gnuplot perf_plot.gp` – publication-quality (requires gnuplot)
2. `python scripts/plot_perf.py` – fallback matplotlib (log scale, background bands, value labels)
Images: `perf_results.png`, `images/perf_results_log.png`.
---
## Profile Guided Optimization (PGO) Builds
PGO improves hot-path layout & inlining (5–20%).
Quick workflow:
```bash
python3 scripts/pgo_workflow.py --compiler gcc   # or clang / msvc
```
Manual:
```bash
cmake --preset gcc-pgo-generate && cmake --build --preset gcc-pgo-generate
# run workloads
cmake --preset gcc-pgo-use && cmake --build --preset gcc-pgo-use
```
Compare:
```bash
python scripts/compare_pgo_performance.py
```
Training includes help/version, compilation, flags combos, thread counts, chunk sizes, anchors, normalization modes.
VS Code tasks: PGO Workflow - GCC / Clang / MSVC.
CI publishes PGO variants; Python wheel auto-selects.
Troubleshooting:
| Issue | Action |
|-------|--------|
| No profile data | Re-run workflow; grep for errors |
| Perf regression | Bias workloads or re-run harness |
| Build failure | Use `--clean`; check compiler versions |
---
## Implementation Details
Pipeline:
1. Bloom filter pre-filter
2. Hash table buckets (length-desc sorted)
3. Short matcher (1–4 bytes) bitmap + binary search
4. Per-thread result buffers merged (offset asc, length desc)
5. Post-filters: longest-only, no-overlap, word-boundary, prefix/suffix, line anchors
6. Transform table (case / punctuation / whitespace) optional
7. Memory-mapped compiled pattern store (low per-instance overhead)
---
## Compiler Options
* Requires C11 + OpenMP
* CMake flags:
  * `-DENABLE_SANITIZERS=ON` (ASan+UBSan)
  * `-DOMEGA_MATCH_REQUIRE_OPENMP=ON` (hard requirement)
* Presets supply `-O3 -fopenmp` (or platform equivalent).
---
## General Performance Notes
* Disable sanitizers for final numbers.
* Tune `--threads` (often 4–8) and `--chunk-size` (4–16KB sweet spot).
* Keep test lists stable; avoid thermal throttling; pin CPU if needed.
---
## CI/CD
GitHub Actions:
* `ci.yml` – multi-platform build & test (Windows MSVC, Linux GCC, macOS Clang, x64 & ARM64)
* `release.yml` – tagged release packaging (DEB/RPM/TGZ/WIX), multi-variant Python wheel, artifacts upload.
PGO variants published; Python wheel selects best variant at import.
---
Questions or contributions? Open an issue or PR. Happy hacking! 🚀
