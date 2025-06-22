# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Achieves 7-9K MB/s throughput on typical workloads
- Efficient memory usage with memory-mapped compiled patterns
- Parallel match processing with configurable thread counts
- Optimized algorithms for different pattern lengths

### Documentation
- Complete API documentation
- Usage examples for CLI and C API
- Build instructions for all platforms
- Performance tuning guidelines
