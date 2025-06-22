# OmegaMatch

[![CI Build and Test](https://github.com/scholarsmate/omega-match/actions/workflows/cmake-multi-platform.yml/badge.svg)](https://github.com/scholarsmate/omega-match/actions/workflows/cmake-multi-platform.yml)
[![Release](https://github.com/scholarsmate/omega-match/actions/workflows/release.yml/badge.svg)](https://github.com/scholarsmate/omega-match/actions/workflows/release.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Version](https://img.shields.io/badge/version-0.1.0-green.svg)](https://github.com/scholarsmate/omega-match/releases)

OmegaMatch is a high-performance, multithreaded, multipattern matching library written in C. It combines a Bloom filter, hash table, and optimized "short matcher" to scan large text for multiple patterns in parallel.

## Features

- Parallel matching using [OpenMP](https://www.openmp.org/)
- Bloom filter pre-filtering
- Exact match via highly optimized hash table scans and comparisons
- Specialized short matcher for patterns length 1–4
- Post-processing filters: no-overlap, longest-only, word-boundary, begin and end of line anchors
- Optimized radix sort for results: length descending, offset ascending
- Optional case-insensitive, punctuation ignoring, whitespace eliding via transform table
- Configurable memory sanitizers and thread/chunk sizes
- **Persistable compiled pattern store:** compile patterns once to disk and memory-map for fast, concurrent reuse by multiple matcher instances with very low memory overhead

## Build

This project uses CMake with flexible build options:

### Standard Build (CLI tool + libraries)
```sh
cmake --preset release
cmake --build --preset release
ctest --preset release --output-on-failure
```

### Language Bindings Build (libraries only)
```sh
cmake --preset release -DOLM_BUILD_CLI=OFF
cmake --build --preset release
cmake --install build-gcc-release --prefix /usr/local
```

This creates both static and shared libraries without the CLI tool, ideal for:
- Python bindings (ctypes, Cython, pybind11)
- Node.js native modules
- Go cgo bindings
- Rust FFI
- Any language that can call C libraries

### Building on Windows (MSVC)

From a *Developer Command Prompt for VS 2022* run:

```sh
cmake --preset msvc-release
cmake --build --preset msvc-release
```

### Building on Linux (GCC)

```sh
cmake --preset release
cmake --build --preset release
```

### Building on macOS (Clang)

First, install `libomp` if you don't have it:
```sh
brew install libomp
```

Then run the build:
```sh
cmake --preset macos-release
cmake --build --preset macos-release
```

### Testing

After building, run the test suite using `ctest` with the same preset used for building:

```sh
ctest --preset <name-of-preset> --output-on-failure
```

For example:
```sh
ctest --preset release --output-on-failure
```

### Packaging

After building, installers can be created with CPack. Example:

```sh
cpack -G TGZ --config build/CPackConfig.cmake
cpack -G DEB --config build/CPackConfig.cmake
cpack -G RPM --config build/CPackConfig.cmake
# on Windows with WiX installed
cpack -G WIX --config build/CPackConfig.cmake
```

### Multi-platform CI

The GitHub workflow `cmake-multi-platform.yml` builds and packages artifacts
on Windows (MSVC), Linux (GCC), and macOS (Clang). Packages produced by
these builds are uploaded as workflow artifacts for each compiler.

## Usage

### Command-line tool

```sh
./olm <command> <patterns> <input_file> [options]
```

**Commands:**

-  `compile`    Compile patterns
-  `match`      Match patterns

**Compile Command Options:**

- `--ignore-case`         Ignore case in patterns
- `--ignore-punctuation`  Ignore punctuation in patterns
- `--elide-whitespace`    Remove whitespace in patterns
- `-v, --verbose`         Enable verbose output
- `-h, --help`            Show this help message

**Match Command Options:**

- `-o, --output FILE`     Write results to FILE instead of stdout (UTF-8 and LF EOL)
- `--ignore-case`         Ignore case during matching
- `--ignore-punctuation`  Ignore punctuation during matching
- `--elide-whitespace`    Remove whitespace during matching
- `--longest`             Only return longest matches
- `--no-overlap`          Avoid overlapping matches
- `--word-boundary`       Only match at word boundaries
- `--word-prefix`         Only match at word prefixes
- `--word-suffix`         Only match at word suffixes
- `--line-start`          Only match at the start of a line
- `--line-end`            Only match at the end of a line
- `--threads N`           Number of threads to use
- `--chunk-size N`        Chunk size for parallel processing
- `-v, --verbose`         Enable verbose output
- `-h, --help`            Show this help message

### C API

```c
#include <omega/list_matcher.h>

// Create matcher (compiling patterns if needed)
omega_list_matcher_t *m = omega_list_matcher_create("patterns.txt", /*case_insensitive=*/0, /*ignore_punctuation=*/0, /*elide_ws=*/0, NULL);

// Perform match on buffer
const uint8_t *data = ...; size_t len = ...;
omega_match_results_t *r = omega_list_matcher_match(m, data, len, /*no_overlap=*/1, /*longest_only=*/1, /*word_boundary=*/1, /*word_prefix=*/0, /*word_suffix=*/0);

// Iterate results
for (size_t i = 0; i < r->count; ++i) {
  printf("match at %zu length %u\n", r->matches[i].offset, r->matches[i].len);
}

omega_match_results_destroy(r);
omega_list_matcher_destroy(m);
```

## Implementation Details

OmegaMatch uses a two-tier matching pipeline:

- **Bloom filter** for fast pre-filtering of candidate positions.
- **Hash table scan** for exact matches of patterns length ≥ 5.
- **Short matcher** optimized for patterns length 1–4 (bitmap lookup and binary search).
- **Radix sort** (length desc, offset asc) followed by optional post-filters:
  - No-overlap
  - Longest-only
  - Word-boundary, prefix, suffix checks
- **Transform table** (when enabled) for case-insensitive, punctuation ignoring, and whitespace eliding.
- **Compiled pattern store** is serialized into a compact binary format and memory-mapped by each matcher, enabling low startup cost, minimal per-instance memory overhead, and parallel sharing across threads or processes.

## Compiler Options

Supported compilers: GCC, Clang, MSVC (via CMake).

- Requires **C11** support and **OpenMP**.
- CMake options:
  - `-DENABLE_SANITIZERS=ON|OFF`   Enable AddressSanitizer and UndefinedBehaviorSanitizer
  - `-DCMAKE_BUILD_TYPE=<Debug|Release>`  Select build type
- Recommended flags for high performance:
  - `-O3`
  - `-fopenmp` (or `/openmp` for MSVC)

## Performance

- Benchmarks in `perf_test.py` and Gnuplot script `perf_plot.gp`.
- Consider using `-DENABLE_SANITIZERS=OFF` for maximum speed.
- Adjust `--threads` and `--chunk` options to tune parallel load.

## CI/CD

Continuous integration runs on GitHub Actions. Every push and pull request
builds the libraries, installs the release binaries and executes the full test
suite using the installed `olm` executable. When a commit is
tagged with a semantic version (`vMAJOR.MINOR.PATCH`), additional cross builds
produce installable packages for Linux x64, Linux ARM64, macOS ARM64 and Windows x64.
The resulting artifacts are attached to the GitHub release automatically under
`dist/native/<platform>`.

## License

The OmegaMatch project is licensed under the [Apache License 2.0](LICENSE).

OmegaMatch is not an official Apache Software Foundation (ASF) project.
