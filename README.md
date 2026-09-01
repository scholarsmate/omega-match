# OmegaMatch

[![CI/CD Pipeline](https://github.com/scholarsmate/omega-match/actions/workflows/ci.yml/badge.svg)](https://github.com/scholarsmate/omega-match/actions/workflows/ci.yml)
[![Release](https://github.com/scholarsmate/omega-match/actions/workflows/release.yml/badge.svg)](https://github.com/scholarsmate/omega-match/actions/workflows/release.yml)
[![PyPI version](https://badge.fury.io/py/omega_match.svg)](https://badge.fury.io/py/omega_match)
[![Python versions](https://img.shields.io/pypi/pyversions/omega_match.svg)](https://pypi.org/project/omega_match/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![GitHub release](https://img.shields.io/github/v/release/scholarsmate/omega-match?include_prereleases)](https://github.com/scholarsmate/omega-match/releases)

OmegaMatch is a high-performance, multi-threaded, multi-pattern matching library written in C. It combines a Bloom filter, hash table, and optimized "short matcher" to scan large content for multiple patterns in parallel.

> Need build, performance benchmarking, PGO, or architecture details? See the **[Development & Performance Guide](DEVELOPMENT.md)**.
>
> Exploring the upcoming rewrite pipeline? See **[Documentation](docs/README.md)**, starting with the **[Reactor Design](docs/reactor-design.md)**.
>
> Want a practical walkthrough? See the **[Reactor Guide](docs/reactor-guide.md)**.

## Features

- Parallel matching using [OpenMP](https://www.openmp.org/)
- Bloom filter pre-filtering
- Exact match via highly optimized hash table scans and comparisons
- Specialized short matcher for patterns of length 1–4
- Post-processing filters: no-overlap, longest-only, word-boundary, and line anchors
- Streaming k-way merge of per-thread results (offset asc, length desc), enabling linear-time longest-only and no-overlap filters
- Optional case-insensitive, punctuation-ignoring, and whitespace-eliding transformations
- Configurable memory sanitizers and thread/chunk sizes
- **Persistable compiled pattern store:** compile patterns once to disk and memory-map for fast, concurrent reuse by multiple matcher instances with very low memory overhead.

## Build

This project uses CMake with flexible build presets:

### Standard Build (CLI tool + libraries)
```sh
cmake --preset release
cmake --build --preset release
ctest --preset release --output-on-failure
```

If you need the build to fail when OpenMP isn't available (e.g., packaging jobs), enable the hard requirement:

```sh
cmake --preset release -DOMEGA_MATCH_REQUIRE_OPENMP=ON
```

### Language Bindings Build (libraries only)
```sh
cmake --preset release -DOMEGA_MATCH_BUILD_CLI=OFF
cmake --build --preset release
# The build directory depends on the preset, e.g., 'build-gcc-release' for the 'release' preset
cmake --install build-gcc-release --prefix /usr/local
```

This creates both static and shared libraries without the CLI tool, ideal for:
- Python bindings (ctypes, Cython, pybind11)
- Node.js native modules
- Go cgo bindings
- Rust FFI
- Any language that can call C libraries

### Building on Windows (MSVC)

From a *Developer Command Prompt for VS 2022*, run:

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
# The CPack config is in the build directory, e.g., build-gcc-release
cpack -G TGZ --config build-gcc-release/CPackConfig.cmake
cpack -G DEB --config build-gcc-release/CPackConfig.cmake
cpack -G RPM --config build-gcc-release/CPackConfig.cmake
# on Windows with WiX installed
cpack -G WIX --config build-msvc-release/CPackConfig.cmake
```

## Performance Testing

Use `scripts/benchmark_scaling.py` for comparative or scaling claims. It
generates exact-size corpora on a caller-selected filesystem, precompiles the
OmegaMatch pattern store, drains complete output from every tool, verifies
byte counts and SHA-256 digests, and records raw samples in CSV and JSON. GNU
grep and ripgrep are both included when installed.

```sh
python3 scripts/benchmark_scaling.py \
  --olm release=build-gcc-release/olm \
  --olm pgo=build-gcc-pgo-use/olm \
  --sizes-mib 4,16,64,256 \
  --cases longest-no-overlap,line-start,line-end \
  --threads 8 --runs 5 --work-dir /tmp/omega-match-scaling
```

The checked-in `data/names.txt` contains 29,156 patterns. On an Intel Core
Ultra 7 165H under Ubuntu 24.04/WSL2, the September 2026 PGO build produced
the following medians over a warm 256 MiB KJV-derived corpus on the native
Linux filesystem. These are output-equivalent CLI measurements: every tool's
complete output was consumed at every size, and byte counts plus SHA-256
digests matched on the 4 MiB validation corpus.

| Mode | OmegaMatch PGO | GNU grep 3.11 | ripgrep 15.2 |
|---|---:|---:|---:|
| longest + no-overlap | 266 MiB/s | 196 MiB/s | 129 MiB/s |
| line start | 1,188 MiB/s | 24 MiB/s | 252 MiB/s |
| line end | 606 MiB/s | 27 MiB/s | 51 MiB/s |

OmegaMatch used eight OpenMP threads. GNU grep is single-threaded; ripgrep was
given `-j 8`, although a single input file does not necessarily use all eight
workers. OmegaMatch's persisted pattern store was compiled before timing,
while grep and ripgrep rebuild their pattern engines on each invocation. That
is representative of OmegaMatch's intended match-many deployment model, but
it is not a scan-kernel-only comparison. Regex construction dominates much of
the anchored comparator time, and the line-end case has no matches in this
corpus. The output sizes at 256 MiB were 60.9 MB, 16.4 MB, and 0 bytes for the
three rows respectively.

For `longest + no-overlap`, OmegaMatch PGO rose from 154 MiB/s at 4 MiB to
224, 274, and 266 MiB/s at 16, 64, and 256 MiB respectively; it did not
progressively degrade with input size. Results depend on CPU, tool versions,
pattern distribution, match density, storage, cache state, thread count, and
whether output is materialized. Treat this snapshot as a reproducible data
point, not a universal throughput guarantee. See
[DEVELOPMENT.md](DEVELOPMENT.md#performance-testing) for methodology,
output-suppressed thread and pattern-count scaling, profiling results, and
known pitfalls.

`perf_test.py` remains useful as a broad cross-platform smoke benchmark. It
now uses the physical haystack size as its throughput numerator and drains
grep output through a pipe. Historical results produced by older revisions
used a fixed 1 GiB numerator for the 4.39 MiB checked-in file and could let GNU
grep stop after its first match when output was `/dev/null`; those figures and
ratios are invalid.

## Profile Guided Optimization (PGO) Builds

OmegaMatch supports Profile Guided Optimization (PGO). Its benefit is
workload-dependent, so compare it with the same revision's standard release
build on representative inputs.

### Quick Start - PGO Builds

Use the unified PGO workflow script for any platform:

```bash
# Linux/WSL - GCC PGO (most stable)
python3 scripts/pgo_workflow.py --compiler gcc

# Linux/WSL - Clang PGO
python3 scripts/pgo_workflow.py --compiler clang

# Windows - MSVC PGO
python scripts/pgo_workflow.py --compiler msvc
```

### Available PGO Variants

| Variant | Platform | Compiler | Expected result |
|---------|----------|----------|-----------------|
| `linux-x64-gcc-pgo` | Linux x64 | GCC | Workload-dependent; benchmark against release |
| `linux-x64-clang-pgo` | Linux x64 | Clang | Workload-dependent; benchmark against GCC and release |
| `windows-x64-msvc-pgo` | Windows x64 | MSVC | Workload-dependent; benchmark against release |

### Selecting the Best PGO Variant

No compiler is universally fastest. Build the applicable variants and compare
them on representative inputs with the scaling harness:

```bash
python3 scripts/benchmark_scaling.py \
  --olm release=build-gcc-release/olm \
  --olm gcc-pgo=build-gcc-pgo-use/olm \
  --sizes-mib 64,256 --runs 5 --skip-grep --skip-ripgrep \
  --work-dir /tmp/omega-match-pgo-comparison
```

### Manual PGO Build Process

For advanced users, you can build PGO variants manually:

#### Step 1: Build Instrumented Binary
```bash
# Configure for PGO instrumentation
cmake --preset gcc-pgo-generate    # or clang-pgo-generate, msvc-pgo-generate
cmake --build --preset gcc-pgo-generate
```

#### Step 2: Run Training Workloads
```bash
# Run comprehensive training (automatic)
python3 scripts/pgo_workflow.py --compiler gcc

# Or run custom training workloads
cd build-gcc-pgo-generate
./olm compile /tmp/patterns.olm ../data/names.txt
./olm match --threads 4 --longest --no-overlap /tmp/patterns.olm ../data/kjv.txt
# Add more workloads representative of your use case...
```

#### Step 3: Build Optimized Binary
```bash
# Configure for PGO optimization
cmake --preset gcc-pgo-use
cmake --build --preset gcc-pgo-use

# Test the optimized build
ctest --test-dir build-gcc-pgo-use --output-on-failure
```

### PGO Training Workloads

The automated PGO training includes comprehensive workloads:

- **Basic Operations**: Help, version commands
- **Pattern Compilation**: Various pattern types and sizes
- **Matching Modes**: Case sensitivity, word boundaries, longest match, no-overlap
- **Threading**: Single and multi-threaded execution (1, 2, 4, 8 threads)
- **Chunk Sizes**: Various buffer sizes (512B to 16KB)
- **Advanced Features**: Line anchors, whitespace handling, output modes
- **Stress Testing**: Complex flag combinations simulating real-world usage

### Testing PGO Performance

Compare PGO vs standard builds:

```bash
python3 scripts/benchmark_scaling.py \
  --olm release=build-gcc-release/olm \
  --olm pgo=build-gcc-pgo-use/olm \
  --sizes-mib 16,64,256 --runs 5 --skip-grep --skip-ripgrep \
  --work-dir /tmp/omega-match-pgo-comparison
```

### VS Code Integration

PGO workflows are available as VS Code tasks:

- **Ctrl+Shift+P** → "Tasks: Run Task"
- Select "PGO Workflow - GCC", "PGO Workflow - Clang", or "PGO Workflow - MSVC"

### CI/CD PGO Integration

The CI/CD pipeline automatically builds PGO variants for releases:

- **Linux**: GCC PGO and Clang PGO variants
- **Windows**: MSVC PGO variant  
- **Artifacts**: All PGO variants available in GitHub releases
- **Python Wheel**: Includes all PGO variants with automatic selection

### Troubleshooting PGO Builds

**No profile data generated:**
```bash
# Check training execution
python3 scripts/pgo_workflow.py --compiler gcc 2>&1 | grep -i "error\|failed"

# Verify data files exist
ls -la data/
```

**Performance regression:**
```bash
# Compare release and PGO on representative inputs
python3 scripts/benchmark_scaling.py \
  --olm release=build-gcc-release/olm \
  --olm pgo=build-gcc-pgo-use/olm \
  --sizes-mib 64,256 --runs 5 --skip-grep --skip-ripgrep

# Add custom training workloads to pgo_workflow.py
```

**Build failures:**
```bash
# Clean and retry
python3 scripts/pgo_workflow.py --compiler gcc --clean

# Check compiler versions
gcc --version
cmake --version
```

For more details, see the [cross-platform PGO guide](scripts/README_PGO.md).

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
- `-q, --quiet`           Suppress match output (no results printed)
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

## Python Language Bindings

OmegaMatch provides Python bindings with a clean, Pythonic API that wraps the high-performance native C library. The bindings support all major platforms (Linux, macOS, Windows) and Python versions 3.9+.

The Python package can select an available PGO (Profile Guided Optimization)
variant for the current platform. PGO can help, have little effect, or regress
a workload when its training profile is not representative, so benchmark the
selected native library on production-like data.

### Installation

```bash
pip install omega_match
```

The package includes multiple optimized native library variants:
- **Linux x64**: Standard, GCC PGO, and Clang PGO variants
- **Linux ARM64**: Optimized for ARM processors  
- **Windows x64**: Standard and MSVC PGO variants
- **macOS ARM64**: Apple Silicon optimized

The best variant is automatically selected at runtime based on your platform.

### Quick Start

```python
from omega_match.omega_match import Compiler, Matcher

# Compile patterns
patterns = ["foo", "bar", "bazinga"]
with open("patterns.txt", "w") as f:
    f.write("\n".join(patterns))

# Create compiled matcher file
stats = Compiler.compile_from_filename("matcher.olm", "patterns.txt")
print(f"Compiled {stats.stored_pattern_count + stats.short_pattern_count} patterns")

# Load matcher and search
with Matcher("matcher.olm") as matcher:
    haystack = b"foo bar test bazinga"
    results = matcher.match(haystack)
    
    for result in results:
        print(f"Found '{result.match.decode()}' at offset {result.offset}")
```

### API Reference

#### Compiler Class

The `Compiler` class handles pattern compilation and supports both streaming and batch compilation:

```python
# Streaming compilation
with Compiler("output.olm", case_insensitive=True) as compiler:
    compiler.add_pattern(b"pattern1")
    compiler.add_pattern(b"pattern2")
    stats = compiler.get_stats()

# Batch compilation from file
stats = Compiler.compile_from_filename("output.olm", "patterns.txt", 
                                       case_insensitive=True)

# Batch compilation from buffer
pattern_buffer = b"foo\nbar\nbaz"
stats = Compiler.compile_from_buffer("output.olm", pattern_buffer)
```

**Compiler Options:**
- `case_insensitive`: Normalize patterns to uppercase for case-insensitive matching.
- `ignore_punctuation`: Remove punctuation from patterns during compilation.
- `elide_whitespace`: Remove whitespace from patterns during compilation.

#### Matcher Class

The `Matcher` class performs pattern matching on data:

```python
with Matcher("compiled.olm") as matcher:
    results = matcher.match(haystack,
                           no_overlap=True,      # Suppress overlapping matches
                           longest_only=True,    # Keep only longest at each position
                           word_boundary=True,   # Match only at word boundaries
                           word_prefix=False,    # Match at word start
                           word_suffix=False,    # Match at word end
                           line_start=False,     # Match at line start
                           line_end=False)       # Match at line end
    
    # Configure threading
    matcher.set_threads(4)        # Use 4 threads for matching
    matcher.set_chunk_size(1024)  # OpenMP chunk size
```

#### Match Results

Each match result contains:

```python
for result in results:
    print(f"Offset: {result.offset}")      # Byte offset in haystack
    print(f"Length: {result.length}")      # Match length in bytes
    print(f"Match: {result.match}")        # Matched bytes (bytes object)
```

#### Statistics

Get compilation and matching statistics:

```python
# Pattern store statistics (from compilation)
stats = compiler.get_stats()
print(f"Total patterns: {stats.stored_pattern_count + stats.short_pattern_count}")
print(f"Input bytes: {stats.total_input_bytes}")
print(f"Stored bytes: {stats.total_stored_bytes}")

# Match statistics (from matching operations)
match_stats = matcher.get_match_stats()
print(f"Total hits: {match_stats.total_hits}")
print(f"Total attempts: {match_stats.total_attempts}")
matcher.reset_match_stats()  # Reset counters
```

### Advanced Usage

#### Case-Insensitive and Normalized Matching

```python
# Compile with normalization options
with Compiler("normalized.olm", 
              case_insensitive=True,
              ignore_punctuation=True,
              elide_whitespace=True) as compiler:
    compiler.add_pattern(b"Hello, World!")
    
# The pattern will match "helloworld", "HELLO WORLD", etc.
with Matcher("normalized.olm",
             case_insensitive=True,
             ignore_punctuation=True,
             elide_whitespace=True) as matcher:
    results = matcher.match(b"Say: hello world!")
```

#### Word Boundary Matching

```python
with Matcher("words.olm") as matcher:
    text = b"The cat catches cats"
    
    # Match "cat" only as complete words (not in "catches" or "cats")
    results = matcher.match(text, word_boundary=True)
    
    # Match only at word starts
    results = matcher.match(text, word_prefix=True)
    
    # Match only at word ends  
    results = matcher.match(text, word_suffix=True)
```

#### Line-Based Matching

```python
with Matcher("lines.olm") as matcher:
    text = b"start of line\nmiddle\nend of line"
    
    # Match only at line start
    results = matcher.match(text, line_start=True)
    
    # Match only at line end
    results = matcher.match(text, line_end=True)
```

#### Performance Tuning

```python
with Matcher("patterns.olm") as matcher:
    # Configure for your workload
    matcher.set_threads(8)         # Use all CPU cores
    matcher.set_chunk_size(4096)   # Larger chunks for big data
    
    # Process large data efficiently
    large_data = b"..." * 1000000
    results = matcher.match(large_data)
```

### Cross-Platform Support

The Python package includes pre-built native libraries for:
- **Linux x64**: Standard, GCC PGO, and Clang PGO variants
- **Linux ARM64**: Optimized for ARM64 processors
- **macOS ARM64**: Apple Silicon optimized (M1, M2, M3, etc.)
- **Windows x64**: Standard and MSVC PGO variants

The optimal library variant is automatically selected based on:
1. **Platform detection** (OS and architecture)
2. **Performance requirements** (PGO variants preferred)
3. **Compatibility fallback** (standard builds if needed)

**PGO Variant Selection**: The Python bindings use intelligent variant selection to provide maximum performance:

```python
import omega_match

# Automatically uses the best PGO variant available
# - Linux: Prefers Clang PGO > GCC PGO > Standard
# - Windows: Prefers MSVC PGO > Standard  
# - macOS: Uses optimized standard build (PGO coming soon)
matcher = omega_match.Matcher("patterns.olm")
```

You can check which variant is being used:

```python
import omega_match
print(f"Using variant: {omega_match.get_library_info()['variant']}")
print(f"Performance level: {omega_match.get_library_info()['optimization']}")
```

### Command-Line Tool (olm.py)

The Python package includes `olm.py`, a command-line tool that mirrors the functionality of the native `olm` binary. This tool provides a pure Python interface for pattern compilation and matching operations, making it easy to use OmegaMatch from the command line on any platform where Python is available.

You can use `olm.py` to:
- Compile large pattern lists into efficient matcher files for fast repeated searches.
- Search for multiple patterns in large text or binary files, with support for advanced options like word boundaries, no-overlap, and multi-threading.
- Integrate high-performance pattern matching into your data pipelines or automation scripts without writing any C code.

#### Example

Finding names from the King James version of the Bible:

```powershell
.\build-msvc-release\Release\olm.exe match --no-overlap --word-boundary --longest .\data\names.txt .\data\kjv.txt
```

You can also use the Python CLI version (works on all platforms):

```bash
python -m omega_match.olm match --no-overlap --word-boundary --longest data/names.txt data/kjv.txt
```

#### Usage

```bash
# Compile patterns from a file into a matcher
python -m omega_match.olm compile patterns.olm patterns.txt

# Match patterns in a haystack file  
python -m omega_match.olm match patterns.olm haystack.txt
```

#### Commands and Options

**Compile Command:**
```bash
python -m omega_match.olm compile <output.olm> <patterns.txt> [options]
```
- `--ignore-case`         Ignore case in patterns
- `--ignore-punctuation`  Ignore punctuation in patterns
- `--elide-whitespace`    Remove whitespace in patterns
- `-v, --verbose`         Enable verbose output

**Match Command:**
```bash
python -m omega_match.olm match <compiled.olm> <haystack.txt> [options]
```
- `--ignore-case`         Ignore case during matching
- `--ignore-punctuation`  Ignore punctuation during matching
- `--elide-whitespace`    Remove whitespace during matching
- `--longest`             Only return longest matches
- `--no-overlap`          Avoid overlapping matches
- `--word-boundary`       Only match at word boundaries
- `--word-prefix`         Only match at word prefixes
- `--word-suffix`         Only match at word suffixes
- `--line-start`          Only match at line starts
- `--line-end`            Only match at line ends
- `--threads N`           Number of threads to use
- `--chunk-size N`        Chunk size for parallel processing
- `-v, --verbose`         Enable verbose output
- `-h, --help`            Show this help message

#### Example

```bash
# Compile a pattern list with normalization
python -m omega_match.olm compile mypatterns.olm mypatterns.txt --ignore-case --elide-whitespace -v

# Match patterns with filtering options
python -m omega_match.olm match mypatterns.olm input.txt --longest --no-overlap --threads 4 -v
```

The output format matches the native `olm` binary: each match is reported as `offset:matched_text` (one per line, with Unix-style newlines).

## Implementation Details

OmegaMatch uses a two-tier matching pipeline:

- **Bloom filter** for fast pre-filtering of candidate positions.
- **Hash table scan** for exact matches of patterns of length ≥ 5.
    - Buckets are pre-sorted by length descending (longest-first within a bucket).
- **Short matcher** optimized for patterns of length 1–4 (bitmap lookup and binary search).
- **Streaming k-way merge** of per-thread results (offset asc, length desc) with linear post-filters:
  - No-overlap
  - Longest-only
  - Word-boundary, prefix, and suffix checks
- **Transform table** (when enabled) for case-insensitive, punctuation-ignoring, and whitespace-eliding transformations.
- **Compiled pattern store** is serialized into a compact binary format and memory-mapped by each matcher, enabling low startup cost, minimal per-instance memory overhead, and parallel sharing across threads or processes.

## Comparison with Other Multi-String Matchers

### Feature Comparison

| Feature | OmegaMatch | Aho-Corasick | Hyperscan | Wu-Manber | Commentz-Walter |
| ------- | ---------- | ------------ | --------- | --------- | --------------- |
| Multi-pattern matching | Yes | Yes | Yes | Yes | Yes |
| Regex support | No (literals only) | No | Yes | No | No |
| SIMD acceleration | AVX2/SSE2/NEON | Varies by impl | AVX2/AVX-512 | No | No |
| Multi-threaded | Yes (OpenMP) | No (typically) | Yes | No | No |
| Compiled pattern store | Yes (memory-mapped) | In-memory only | Serializable | In-memory only | In-memory only |
| Case-insensitive | Built-in | Wrapper needed | Built-in | Wrapper needed | Wrapper needed |
| Word boundary filters | Built-in | Post-processing | Partial | Post-processing | Post-processing |
| Line anchor filters | Built-in | Post-processing | Yes | Post-processing | Post-processing |
| Longest-only / no-overlap | Built-in (linear time) | Post-processing | Partial | Post-processing | Post-processing |
| Streaming results | Yes (k-way merge) | Yes (automaton) | Yes | No | No |
| Short pattern optimization | Yes (direct and prefix bitmaps + binary search) | No (uniform trie) | Yes | Poor (short shifts) | Poor (short shifts) |
| Memory overhead per pattern | Low (hash table) | High (trie nodes + failure links) | Moderate | Moderate (shift tables) | Moderate (shift tables) |
| Profile-Guided Optimization | Yes (GCC/Clang/MSVC) | No (typically) | No | No | No |
| Language bindings | C, Python | Many | C, C++, Python | Few | Few |

### Algorithmic Approach

| Algorithm | Core Technique | Strengths | Weaknesses |
| --------- | ------------- | --------- | ---------- |
| **OmegaMatch** | Bloom filter + hash table with SIMD control-byte probing | Cache-friendly, low memory per pattern, rich built-in filters, parallelized | Literals only, no substring skipping |
| **Aho-Corasick** | Trie + failure function (finite automaton) | Guaranteed linear time, theoretical elegance, single-pass | Pointer-chasing (cache-unfriendly), high memory for large alphabets |
| **Hyperscan** | Hybrid (DFAs, NFA, SIMD literal matchers) | Fastest for regex workloads, Intel-optimized | Intel-only (x86), complex, large binary, no ARM |
| **Wu-Manber** | Bad-character shift tables | Good skip distance for longer patterns | Degrades with short patterns or large pattern sets |
| **Commentz-Walter** | Boyer-Moore extended to multi-pattern | Skip-based scanning | Complex failure handling, poor on short patterns |
| **Rabin-Karp** | Rolling hash | Simple, good for few patterns | Single-pattern focus, hash collision overhead at scale |

### Performance Profile

OmegaMatch's hash-based design avoids the pointer-chasing inherent in
trie-based matchers and the short-pattern limitations of shift-table
algorithms. Performance is workload-dependent: on the reproducible 256 MiB
snapshot above, PGO OmegaMatch was 1.36x faster than GNU grep and 2.07x faster
than ripgrep for `longest + no-overlap`, with larger advantages for line
anchors. Output-suppressed matcher throughput scales with OpenMP threads, but
formatting and dense match sets can become the limiting cost. Use the scaling
harness on representative data instead of extrapolating these ratios.

### What Is Distinctive About OmegaMatch

OmegaMatch does not introduce a new algorithm in the academic sense. Its individual components -- Bloom filters, Robin Hood hashing, SIMD-accelerated probing, k-way merging -- are established techniques. What is distinctive is **how they are combined into an end-to-end system**:

1. **Hash-based multi-pattern matching instead of automata.** Most multi-pattern matchers descend from Aho-Corasick (trie + failure links). OmegaMatch replaces the automaton with a Bloom filter feeding a SIMD-probed hash table. This trades the automaton's guaranteed single-pass property for better cache locality and lower memory overhead -- a practical win on modern hardware where cache misses dominate.

2. **Two-tier pattern specialization.** Patterns of length 1--4 bypass the
   Bloom filter and hash table. One- and two-byte patterns use direct bitmaps;
   three- and four-byte patterns use two-byte prefix bitmaps before a keyed
   binary search.

3. **Compile-once, memory-map, match-many architecture.** The compiled pattern
   store is a flat binary file whose primary tables can be mapped directly and
   shared across processes. Matcher setup only builds small derived prefix
   indexes rather than reconstructing the main table.

4. **Streaming merge with integrated filtering.** Per-thread results are merged via a min-heap ordered by (offset ascending, length descending). Longest-only and no-overlap filters are evaluated *during* the merge in a single linear pass, rather than as a separate post-processing step. This guarantees O(n log t) total merge cost (where t = thread count) with no intermediate materialization.

5. **Rich structural filter vocabulary at the engine level.** Word boundaries, word prefixes/suffixes, line-start/line-end anchors, case folding, punctuation removal, and whitespace elision are all first-class options in the matching engine rather than bolted-on post-filters. This allows the engine to short-circuit early (e.g., skipping non-boundary positions entirely) rather than generating matches and discarding them.

In short, OmegaMatch is a systems-engineering combination of established
techniques designed around cache behavior, SIMD probing, multiple cores, and
memory-mapped reuse. Whether that design beats an automaton, grep, ripgrep, or
another matcher depends on the pattern lengths, pattern count, match density,
filters, output requirements, and hardware; the benchmark harness exists to
measure those tradeoffs explicitly.

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
- Adjust `--threads` and `--chunk-size` options to tune parallel load.

## CI/CD

This project uses GitHub Actions for Continuous Integration and Continuous Deployment.

- **CI Pipeline (`ci.yml`)**: On every push and pull request to `main`, the CI pipeline builds and tests the project on Windows (MSVC), Linux (GCC), and macOS (Clang) across x64 and ARM64 architectures.
- **Release Pipeline (`release.yml`)**: When a new tag matching `v*` is pushed, the release pipeline builds, tests, and packages the project. It creates platform-specific installers (DEB, RPM, TGZ, WIX), builds a universal Python wheel, publishes it to PyPI, and creates a GitHub Release with all the generated artifacts.

## Used By

- [OmegaOMG](https://github.com/scholarsmate/omega-omg) - OmegaOMG is an efficient Object Matching Grammar (OMG) that looks and feels like regex

## License

The OmegaMatch project is licensed under the [Apache License 2.0](LICENSE).

OmegaMatch is *not* an official Apache Software Foundation (ASF) project.
