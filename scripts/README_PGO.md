# Profile Guided Optimization (PGO) Cross-Platform Guide

This document describes how to use Profile Guided Optimization (PGO) with GCC, Clang, and MSVC across different platforms to improve the performance of OmegaMatch.

## Unified PGO Workflow

The `pgo_workflow.py` script provides a unified, cross-platform solution for PGO builds:

- **Windows**: Supports MSVC, GCC (WSL), and Clang (WSL)  
- **Linux/WSL**: Supports GCC and Clang
- **macOS**: Supports Clang and GCC (if available)

## Prerequisites

### For WSL/Linux (GCC/Clang)
1. **WSL Setup**: Ensure you have WSL with Ubuntu 24.04 installed
2. **Required Tools**: Install build tools in WSL:
   ```bash
   sudo apt update
   sudo apt install -y gcc clang build-essential cmake ninja-build
   ```

### For Windows (MSVC)
1. **Visual Studio**: Install Visual Studio 2019/2022 with C++ tools
2. **Python**: Ensure Python 3.7+ is available

## Quick Start

Use the unified automated PGO script:

```bash
# Navigate to project in WSL
cd /mnt/c/Users/schol/OneDrive/Documents/GitHub/omega-match

# Run GCC PGO workflow
python3 scripts/pgo_workflow.py --compiler gcc

# Or run Clang PGO workflow  
python3 scripts/pgo_workflow.py --compiler clang

# Or run MSVC PGO workflow (on Windows)
python scripts/pgo_workflow.py --compiler msvc
```

## Manual PGO Process

### GCC PGO

1. **Build instrumented version**:
   ```bash
   cmake --preset gcc-pgo-generate
   cmake --build --preset gcc-pgo-generate
   ```

2. **Run training workloads**:
   ```bash
   cd build-gcc-pgo-generate
   # Run representative workloads to collect profile data
   ./olm match ../data/names.txt ../data/kjv.txt > /tmp/training1.txt
   ./olm match --ignore-case ../data/names.txt ../data/kjv.txt > /tmp/training2.txt
   ./olm match ../data/surnames.txt ../data/kjv.txt > /tmp/training3.txt
   ./olm compile /tmp/compiled.olm ../data/names.txt
   ./olm match ../data/small_pats.txt ../data/small_hay.txt > /tmp/training4.txt
   ./olm --help
   cd ..
   ```

3. **Copy profile data**:
   ```bash
   # For GCC, profile data is in CMakeFiles directory structure
   rm -rf build-gcc-pgo-use/CMakeFiles
   cp -r build-gcc-pgo-generate/CMakeFiles build-gcc-pgo-use/
   ```

4. **Build optimized version**:
   ```bash
   cmake --preset gcc-pgo-use
   cmake --build --preset gcc-pgo-use
   ```

### Clang PGO

1. **Build instrumented version**:
   ```bash
   cmake --preset clang-pgo-generate
   cmake --build --preset clang-pgo-generate
   ```

2. **Run training workloads**:
   ```bash
   cd build-clang-pgo-generate
   # Run typical workloads
   ./olm data/patterns.txt data/input.txt
   ./olm --help
   cd ..
   ```

3. **Merge profile data**:
   ```bash
   llvm-profdata merge -output=build-clang-pgo-generate/pgo-profiles/merged.profdata build-clang-pgo-generate/pgo-profiles/*.profraw
   ```

4. **Copy profile data**:
   ```bash
   mkdir -p build-clang-pgo-use/pgo-profiles
   cp -r build-clang-pgo-generate/pgo-profiles/* build-clang-pgo-use/pgo-profiles/
   ```

5. **Build optimized version**:
   ```bash
   cmake --preset clang-pgo-use
   cmake --build --preset clang-pgo-use
   ```

## Script Options

The automated script supports several options:

- `--compiler gcc|clang|msvc`: Choose the compiler
- `--build-only`: Only build instrumented version, skip training
- `--clean`: Clean build directories before starting

Examples:
```bash
# Build instrumented version only
python3 scripts/pgo_workflow.py --compiler gcc --build-only

# Clean and rebuild with Clang
python3 scripts/pgo_workflow.py --compiler clang --clean

# Cross-platform MSVC workflow
python scripts/pgo_workflow.py --compiler msvc
```

## Performance Testing

After PGO optimization, test performance:

```bash
# Test the optimized binary
cd build-gcc-pgo-use  # or build-clang-pgo-use
time ./olm large_patterns.txt large_input.txt

# Compare with non-PGO version
cd ../build-gcc-release
time ./olm large_patterns.txt large_input.txt
```

## Training Data Guidelines

For best PGO results:

1. **Representative workloads**: Use data similar to production usage
2. **Multiple patterns**: Include various pattern types and sizes
3. **Different inputs**: Test with various input file characteristics
4. **Edge cases**: Include boundary conditions and error cases

## Troubleshooting

### Common Issues

1. **Profile directory not found**: Ensure training workloads were run
2. **No .profraw files**: Check that the instrumented binary executed successfully
3. **Merge failures**: Verify llvm-profdata is available for Clang PGO

### Verification

1. **Check profile data**:
   ```bash
   ls -la build-*/pgo-profiles/
   ```

2. **Verify optimization flags**:
   ```bash
   cmake --build --preset gcc-pgo-use -- VERBOSE=1
   ```

3. **Run tests**:
   ```bash
   cmake --build --preset gcc-pgo-use --target test
   ```

## Important Notes

### PGO Implementation Details

1. **Shared Library Handling**: During PGO phases (both generation and use), the shared library build is automatically skipped to avoid profile data conflicts. Only the static library and CLI tool are built with PGO optimization.

2. **Profile Data Location**: For GCC, profile data (`.gcda` files) is stored in the `CMakeFiles` directory structure, not in a separate `pgo-profiles` directory.

3. **Training Data**: The automated script uses `data/names.txt` as patterns and `data/kjv.txt` as haystack for comprehensive training coverage.

## Expected Performance Gains

PGO typically provides:
- **5-15%** performance improvement for compute-intensive code
- **Better branch prediction** for conditional code
- **Improved function inlining** decisions
- **Optimized loop unrolling** for hot loops

The actual gains depend on the workload and how well the training data represents production usage.

## CI/CD Integration

The GitHub Actions release workflow automatically builds PGO-optimized versions alongside regular builds:

### Release Artifacts

Each release includes multiple variants:
- **Regular builds**: Standard `-O3` optimization
- **GCC PGO builds**: Profile-guided optimization with GCC (Linux x64)
- **Clang PGO builds**: Profile-guided optimization with Clang (Linux x64)

### Artifact Naming

- `linux-x64-*`: Regular GCC build
- `linux-x64-gcc-pgo-*`: GCC PGO optimized build
- `linux-x64-clang-pgo-*`: Clang PGO optimized build

### Package Formats

Each variant is available in multiple formats:
- `.deb` packages for Debian/Ubuntu
- `.rpm` packages for RHEL/CentOS/Fedora
- `.tar.gz` archives for universal Linux

### Performance Comparison

Based on our test suite:
- **GCC PGO**: 4.8% smaller binary, 1.6% smaller static library
- **Clang PGO**: 18.7% smaller binary, 9.5% smaller static library

Choose the variant that best fits your performance requirements and deployment environment.
