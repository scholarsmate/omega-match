# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Byte-accurate scaling benchmark for OmegaMatch, GNU grep, and ripgrep with
  exact-size corpora, full-output draining, digest validation, raw samples,
  environment metadata, and native-filesystem work directories.
- Compiled-layout assertions covering Bloom, hash table, bucket, and short
  matcher section alignment and extent.

### Changed

- Compiled pattern format bumped to v4. New stores naturally align the mapped
  Bloom bit array and keyed short-pattern arrays; the loader remains compatible
  with v1-v3 stores.
- Three- and four-byte patterns use two-byte prefix filters before binary
  search, and Bloom misses probe subsequent hashes lazily.
- Line-start matching builds and scans only line-start candidates, including
  parallel candidate construction for thread scaling.
- PGO anchor workloads now pass the line-start and line-end options they are
  intended to train.

### Fixed

- Performance throughput now uses the haystack's physical byte size instead of
  a hard-coded 1 GiB numerator.
- GNU grep benchmark output is fully consumed through a pipe, preventing its
  `/dev/null` early-exit optimization from measuring only the first match.
- Removed unsupported historical multi-GB/s and extreme grep-ratio claims from
  rendered documentation and replaced them with reproducible measurements.

## [0.2.1] - 2025-08-13

### Changed
- Release workflow hardened: added pre-publish hash verification (blake2_256 + sha256) to ensure local wheel matches any existing PyPI artifact when re-running a release.
- Improved artifact uniqueness assurance and idempotent PyPI publishing logic.

### Fixed
- YAML workflow indentation issues that previously broke the release pipeline during hash verification step introduction.


## [0.2.0] - 2025-08-10

### Added
- SIMD-accelerated control-byte probing for hash table lookups (AVX2/SSE2 on x86; NEON on arm64) with runtime CPU feature detection and safe compile-time guards.
- Streaming k-way merge of per-thread results (offset asc, length desc) with on-merge filters (longest-only, no-overlap) in O(n).
- Optional `--quiet` flag for CLI to suppress match output; perf harness auto-detects and enables when grep is disabled.
- Callgrind helpers and reporting tools: `profile_callgrind`, `profile_callgrind_report`, `profile_callgrind_compare` targets and `scripts/callgrind_report.py`.
- A/B performance comparison helper `scripts/compare_branches.py`.
- CMake options to toggle LTO/IPO and tuning: `OMEGA_MATCH_ENABLE_LTO`, `OMEGA_MATCH_MARCH_NATIVE`, `OMEGA_MATCH_MTUNE_NATIVE`.
- Python CLI tool (`bindings/python/olm.py`) with `--output` option for feature parity with native CLI.
- PGO library variant naming and automatic selection in Python bindings for optimal performance.

### Changed
- Persisted compiled format bumped to v2: control-byte fingerprint array precedes index array; loader/compiler updated.
- Hash table insertion simplified to single-pass robin-hood; lower load factor to reduce probe chains.
- Bloom filter tuned to 20 bits/entry; improved word sharing and prefetching.
- Portable prefetch macro refined for MSVC and GCC/Clang.
- OpenMP handling: optional by default with `OMEGA_MATCH_REQUIRE_OPENMP` to enforce in CI/packaging.
- Python bindings now automatically select and use PGO-optimized libraries when available.

### Performance
- Faster candidate probing and bucket scans; fewer cache misses.
- Eliminated global radix sort in favor of streaming k-way merge with linear-time filters.

### CI/Tooling
- Hardened PGO workflow (GCC/Clang/MSVC) with broader `llvm-profdata` discovery and non-fatal missing-profile handling for Clang.
- macOS libomp discovery hints; MSVC OpenMP loop index fix.
- Perf harness improvements: flags cleanup, binary overrides, grep detection, and CSV outputs.

### Fixed
- MSVC PGO build failure caused by CMake WINDOWS_EXPORT_ALL_SYMBOLS crash during instrumentation phase.
- Added explicit `.def` file for symbol export during MSVC PGO builds to avoid CMake object file analysis issues.
- Implemented hybrid optimization strategy: PGO for executable, standard optimization for shared library to work around MSVC profile database limitations.

### Notes
- The compiled pattern store file layout changed (format v2). Recompile pattern stores before use.


## [0.1.0] - 2025-06-22

### Features
- Initial release of omgmatch high-performance pattern matching library
- Bloom filter pre-filtering for fast candidate exclusion
- Robin Hood hash table scan for candidate patterns with ≥ 5 characters
- Short matcher optimized for patterns with 1-4 characters (bitmap lookup + binary search)
- Optimized radix sort for results (length descending, offset ascending)
- Post-processing filters: no-overlap, longest-only, word-boundary, begin and end of line anchors
- Transform table support for case-insensitive, punctuation ignoring, whitespace eliding
- Persistable compiled pattern store with memory-mapping
- OpenMP parallel divide and conquor matching
- Cross-platform support (Windows, Linux, macOS)
- Command-line tool (`omega_match`) with compile and match commands
- C API and ABI for library integration and language bindings
- Dual static/shared library build options
- Comprehensive test suite with CI/CD
- Performance benchmarks and optimization
- CMake build system with presets
- Package generation (DEB, RPM, TGZ, WIX)
- Apache 2.0 licensing

### Performance
- Historical release materials reported 7-9K MB/s using the legacy benchmark;
  see `[Unreleased]` for the corrected methodology and current measurements.
- Efficient memory usage with memory-mapped compiled patterns
- Parallel match processing with configurable thread counts
- Optimized algorithms for different pattern lengths

### Documentation
- Complete API documentation
- Usage examples for CLI and C API
- Build instructions for all platforms
- Performance tuning guidelines
