# omega_match.py

import atexit
import os
import platform
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Protocol, Tuple, Dict

from cffi import FFI

ffi = FFI()
ffi.cdef(
    """
typedef struct omega_list_matcher_compiler_struct omega_list_matcher_compiler_t;

// Opaque matcher handle
typedef struct omega_list_matcher_struct omega_list_matcher_t;

// Structure for a single match result (aligned to 8 bytes)
typedef struct {
  size_t offset;        // Byte offset in haystack
  uint32_t len;         // Length of the match
  const uint8_t *match; // Pointer to matched bytes in haystack
} omega_match_result_t;

// Collection of match results
typedef struct {
  size_t count;                  // Number of matches
  omega_match_result_t *matches; // Array of matches
} omega_match_results_t;

// Pattern store statistics
typedef struct {
  uint64_t total_input_bytes;
  uint64_t total_stored_bytes;
  uint32_t stored_pattern_count;
  uint32_t short_pattern_count;
  uint32_t duplicate_patterns;
  uint32_t smallest_pattern_length;
  uint32_t largest_pattern_length;
} omega_match_pattern_store_stats_t;

// Match statistics
typedef struct {
  uint64_t total_hits;
  uint64_t total_misses;
  uint64_t total_filtered;
  uint64_t total_attempts;
  uint64_t total_comparisons;
} omega_match_stats_t;

/**
 * Create a streaming matcher compiler instance.
 * @param compiled_file Path to the output `.olm` file.
 * @param case_insensitive Whether to normalize patterns to uppercase.
 * @param ignore_punctuation Whether to remove punctuation when compiling.
 * @param elide_whitespace
 * @return A new compiler instance or NULL on failure.
 */
omega_list_matcher_compiler_t *
omega_list_matcher_compiler_create(const char *restrict compiled_file,
                                   int case_insensitive, int ignore_punctuation,
                                   int elide_whitespace);

/**
 * Add a single pattern to the compiler.
 * @param compiler Compiler handle.
 * @param pattern Pointer to pattern bytes.
 * @param len Length in bytes of the pattern.
 * @return 0 on success, -1 on error (e.g., disallowed 1-byte pattern).
 */
int omega_list_matcher_compiler_add_pattern(
    omega_list_matcher_compiler_t *restrict compiler,
    const uint8_t *restrict pattern, uint32_t len);

/**
 * Get pattern store statistics from the compiler.
 * @param compiler Compiler handle.
 * @return Pointer to omega_match_pattern_store_stats_t structure.
 */
const omega_match_pattern_store_stats_t *
omega_list_matcher_compiler_get_pattern_store_stats(
    const omega_list_matcher_compiler_t *restrict compiler);

/**
 * Finalize the matcher and write it to the compiled output file.
 * @param compiler Compiler handle.
 * @return 0 on success, -1 on failure.
 */
int omega_list_matcher_compiler_destroy(
    omega_list_matcher_compiler_t *restrict compiler);

/**
 * Check if a file is a compiled matcher file.
 * @param compiled_file Path to the matcher file to check.
 * @return 1 if compiled, 0 otherwise.
 */
int omega_list_matcher_is_compiled(const char *restrict compiled_file);

/**
 * Write matcher header information to a file pointer.
 * @param matcher Matcher handle.
 * @param fp File pointer to write header info.
 * @return 0 on success, -1 on error.
 */
int omega_list_matcher_emit_header_info(
    const omega_list_matcher_t *restrict matcher, FILE *restrict fp);

/**
 * Compile patterns from a buffer into a matcher file.
 * @param compiled_file Output matcher file path.
 * @param patterns_buf Buffer containing patterns.
 * @param patterns_buf_size Size of the patterns buffer.
 * @param case_insensitive Whether to normalize patterns to uppercase.
 * @param ignore_punctuation Whether to remove punctuation.
 * @param elide_whitespace Whether to elide whitespace.
 * @param pattern_store_stats Optional pointer to store pattern stats.
 * @return 0 on success, -1 on error.
 */
int omega_list_matcher_compile_patterns(
    const char *restrict compiled_file, const uint8_t *restrict patterns_buf,
    uint64_t patterns_buf_size, int case_insensitive, int ignore_punctuation,
    int elide_whitespace,
    omega_match_pattern_store_stats_t *restrict pattern_store_stats);

/**
 * Compile patterns from a file into a matcher file.
 * @param compiled_file Output matcher file path.
 * @param patterns_file Input patterns file path.
 * @param case_insensitive Whether to normalize patterns to uppercase.
 * @param ignore_punctuation Whether to remove punctuation.
 * @param elide_whitespace Whether to elide whitespace.
 * @param pattern_store_stats Optional pointer to store pattern stats.
 * @return 0 on success, -1 on error.
 */
int omega_list_matcher_compile_patterns_filename(
    const char *restrict compiled_file, const char *restrict patterns_file,
    int case_insensitive, int ignore_punctuation, int elide_whitespace,
    omega_match_pattern_store_stats_t *restrict pattern_store_stats);

/**
 * Create a matcher from a buffer of patterns, compiling on the fly.
 * @param compiled_file Path to output matcher file (optional).
 * @param patterns_buffer Buffer containing patterns.
 * @param patterns_buffer_size Size of the patterns buffer.
 * @param case_insensitive Whether to normalize patterns to uppercase.
 * @param ignore_punctuation Whether to remove punctuation.
 * @param elide_whitespace Whether to elide whitespace.
 * @param stats Optional pointer to store pattern stats.
 * @return New matcher handle or NULL on failure.
 */
omega_list_matcher_t *omega_list_matcher_create_from_buffer(
    const char *restrict compiled_file, const uint8_t *restrict patterns_buffer,
    uint64_t patterns_buffer_size, int case_insensitive, int ignore_punctuation,
    int elide_whitespace, omega_match_pattern_store_stats_t *restrict stats);

/**
 * Create a matcher from a compiled matcher file or a patterns file.
 * @param compiled_or_patterns_file Path to matcher or patterns file.
 * @param case_insensitive Whether to normalize patterns to uppercase.
 * @param ignore_punctuation Whether to remove punctuation.
 * @param elide_whitespace Whether to elide whitespace.
 * @param stats Optional pointer to store pattern stats.
 * @return New matcher handle or NULL on failure.
 */
omega_list_matcher_t *
omega_list_matcher_create(const char *restrict compiled_or_patterns_file,
                          int case_insensitive, int ignore_punctuation,
                          int elide_whitespace,
                          omega_match_pattern_store_stats_t *restrict stats);

/**
 * Attach statistics collection to a matcher.
 * @param matcher Matcher handle.
 * @param stats Statistics structure to attach.
 * @return 0 on success, -1 on error.
 */
int omega_list_matcher_add_stats(omega_list_matcher_t *restrict matcher,
                                 omega_match_stats_t *restrict stats);

/**
 * Free matcher resources.
 * @param matcher Matcher handle to destroy.
 * @return 0 on success, -1 on error.
 */
int omega_list_matcher_destroy(omega_list_matcher_t *restrict matcher);

/**
 * Perform pattern matching on a haystack buffer.
 * @param matcher Matcher handle.
 * @param haystack Buffer to search.
 * @param haystack_size Size of the haystack buffer.
 * @param no_overlap If non-zero, suppress overlapping matches.
 * @param longest_only If non-zero, keep only the longest match at each position.
 * @param word_boundary Only match at word boundaries.
 * @param word_prefix Only match at word prefixes (start of word).
 * @param word_suffix Only match at word suffixes (end of word).
 * @param line_start Only match at the start of a line.
 * @param line_end Only match at the end of a line.
 * @return Pointer to omega_match_results_t array. Call omega_match_results_destroy() to free.
 */
omega_match_results_t *
omega_list_matcher_match(const omega_list_matcher_t *restrict matcher,
                         const uint8_t *restrict haystack, size_t haystack_size,
                         int no_overlap, int longest_only, int word_boundary,
                         int word_prefix, int word_suffix, int line_start,
                         int line_end);

/**
 * Free the results array returned by the matcher.
 * @param results Results array to free.
 */
void omega_match_results_destroy(omega_match_results_t *restrict results);

/**
 * Memory-map a file for reading.
 * @param file File pointer to map.
 * @param size Output: size of the mapped region.
 * @param prefetch_sequential Hint for sequential access.
 * @return Pointer to mapped memory, or NULL on error.
 */
uint8_t *omega_matcher_map_file(FILE *restrict file, size_t *restrict size,
                                int prefetch_sequential);

/**
 * Memory-map a file by filename.
 * @param filename Path to file to map.
 * @param size Output: size of the mapped region.
 * @param prefetch_sequential Hint for sequential access.
 * @return Pointer to mapped memory, or NULL on error.
 */
uint8_t *omega_matcher_map_filename(const char *restrict filename,
                                    size_t *restrict size,
                                    int prefetch_sequential);

/**
 * Unmap a memory-mapped file region.
 * @param addr Address of mapped region.
 * @param size Size of mapped region.
 * @return 0 on success, -1 on error.
 */
int omega_matcher_unmap_file(const uint8_t *restrict addr, size_t size);

/**
 * Set the number of threads for parallel matching on a matcher.
 * @param matcher Matcher handle.
 * @param threads Number of threads to use.
 * @return 0 on success, -1 if threads is out of valid range.
 */
int omega_matcher_set_num_threads(omega_list_matcher_t *restrict matcher,
                                  int threads);

/**
 * Get the number of threads used for matching on a matcher.
 * @param matcher Matcher handle.
 * @return Number of threads.
 */
int omega_matcher_get_num_threads(const omega_list_matcher_t *restrict matcher);

/**
 * Set the OpenMP chunk size (static schedule) for a matcher.
 * @param matcher Matcher handle.
 * @param chunk Chunk size (rounded up to next power of two if needed).
 * @return 0 on success, -1 on invalid chunk size.
 */
int omega_matcher_set_chunk_size(omega_list_matcher_t *restrict matcher,
                                 int chunk);

/**
 * Get the OpenMP chunk size (static schedule) for a matcher.
 * @param matcher Matcher handle.
 * @return Chunk size.
 */
int omega_matcher_get_chunk_size(const omega_list_matcher_t *restrict matcher);

/**
 * Get the version string of the library.
 * @return Version string.
 */
const char *omega_match_version(void);

"""
)

# C library FFI handle
C = None

# Global variable to store library information for get_library_info()
_library_info: Optional[Dict[str, str]] = None


@dataclass
class PatternStoreStats:
    total_input_bytes: int
    total_stored_bytes: int
    stored_pattern_count: int
    short_pattern_count: int
    duplicate_patterns: int
    smallest_pattern_length: int
    largest_pattern_length: int


@dataclass
class MatchStats:
    total_hits: int
    total_misses: int
    total_filtered: int
    total_attempts: int
    total_comparisons: int


@dataclass
class MatchResult:
    offset: int
    match: bytes

    @property
    def length(self) -> int:
        return len(self.match)


def _detect_platform():
    """Detect platform and architecture information."""
    system = sys.platform
    arch = platform.machine().lower()

    if arch in {"x86_64", "amd64"}:
        arch = "x64"
    elif arch in {"aarch64", "arm64"}:
        arch = "arm64"
    else:
        raise RuntimeError(f"Unsupported architecture: {arch}")

    return system, arch


def _get_available_pgo_variants(system: str, arch: str) -> List[Tuple[str, str, str]]:
    """Get available PGO variants in priority order (best first)."""
    variants = []

    if system.startswith("linux") and arch == "x64":
        # Linux x64: Prefer Clang PGO > GCC PGO > Standard
        variants = [
            (
                "libomega_match-linux-x64-clang-pgo.so",
                "linux-x64-clang-pgo",
                "PGO (Clang)",
            ),
            ("libomega_match-linux-x64-gcc-pgo.so", "linux-x64-gcc-pgo", "PGO (GCC)"),
            ("libomega_match-linux-x64.so", "linux-x64", "Standard"),
        ]
    elif system.startswith("linux") and arch == "arm64":
        # Linux ARM64: Only standard build available currently
        variants = [
            ("libomega_match-linux-arm64.so", "linux-arm64", "Standard"),
        ]
    elif system in {"win32", "cygwin"} and arch == "x64":
        # Windows x64: Prefer MSVC PGO > Standard
        variants = [
            (
                "libomega_match-windows-x64-msvc-pgo.dll",
                "windows-x64-msvc-pgo",
                "PGO (MSVC)",
            ),
            ("libomega_match-windows-x64.dll", "windows-x64", "Standard"),
        ]
    elif system == "darwin" and arch == "arm64":
        # macOS ARM64: Only standard build available currently
        variants = [
            ("libomega_match-macos-arm64.dylib", "macos-arm64", "Standard"),
        ]
    elif system == "darwin" and arch == "x64":
        # macOS x64: Not currently provided
        variants = []

    return variants


def _find_best_library_variant(lib_dir_path: Path) -> Tuple[Path, str, str]:
    """Find the best available library variant."""

    system, arch = _detect_platform()
    variants = _get_available_pgo_variants(system, arch)

    if not variants:
        raise RuntimeError(
            f"No library variants available for platform: {system}-{arch}"
        )

    # Try variants in priority order
    for filename, variant_id, optimization in variants:
        lib_path = lib_dir_path / filename
        if lib_path.is_file():
            return lib_path, variant_id, optimization

    # If no variants found, provide helpful error message
    available_files = [f.name for f in lib_dir_path.glob("libomega_match-*")]
    raise RuntimeError(
        f"No compatible native library found for {system}-{arch}.\n"
        f"Looking for: {', '.join(v[0] for v in variants)}\n"
        f"Available files: {', '.join(available_files) if available_files else 'None'}\n"
        f"Library directory: {lib_dir_path}"
    )


def _load_library():
    override = os.getenv("OMEGA_MATCH_LIB_PATH")
    if override:
        # Store library info for override path
        global _library_info
        _library_info = {
            "path": override,
            "variant": "custom-override",
            "optimization": "Unknown",
            "platform": f"{sys.platform}-{platform.machine().lower()}",
        }
        return ffi.dlopen(override)

    lib_dir_path = Path(os.path.dirname(__file__)) / "native" / "lib"

    # Find the best available library variant
    lib_path, variant_id, optimization = _find_best_library_variant(lib_dir_path)

    # Store library info for get_library_info()
    _library_info = {
        "path": str(lib_path),
        "variant": variant_id,
        "optimization": optimization,
        "platform": f"{sys.platform}-{platform.machine().lower()}",
    }

    # Platform-specific loading
    system, _arch = _detect_platform()
    if system in {"win32", "cygwin"}:
        os.add_dll_directory(os.path.dirname(lib_dir_path))

    return ffi.dlopen(str(lib_path))


def _get_library():
    global C
    if C is None:
        try:
            C = _load_library()
        except OSError as e:
            raise RuntimeError("Failed to load native library: " + str(e))
    return C


def get_version() -> str:
    version = _get_library().omega_match_version()
    if version == ffi.NULL:
        raise RuntimeError("Failed to get native library version")
    return ffi.string(version).decode("utf-8")


def get_library_info() -> Dict[str, str]:
    """Get information about the loaded native library variant.

    Returns:
        Dictionary containing:
        - path: Full path to the loaded library file
        - variant: Variant identifier (e.g., 'linux-x64-clang-pgo')
        - optimization: Optimization level (e.g., 'PGO (Clang)', 'Standard')
        - platform: Platform string (e.g., 'linux-x64')
    """
    global _library_info

    if _library_info is None:
        # Force library loading to populate _library_info
        _get_library()

    if _library_info is None:
        return {
            "path": "unknown",
            "variant": "unknown",
            "optimization": "unknown",
            "platform": "unknown",
        }

    return _library_info.copy()


class Compiler:
    def __init__(
        self,
        compiled_file: str,
        case_insensitive: bool = False,
        ignore_punctuation: bool = False,
        elide_whitespace: bool = False,
    ) -> None:
        lib = _get_library()
        self._lib = lib
        # Ensure the function exists in the loaded library
        if not hasattr(lib, "omega_list_matcher_compiler_create"):
            raise AttributeError(
                "Native library does not export omega_list_matcher_compiler_create. "
                "Make sure the correct native library is present and loaded."
            )
        try:
            self._compiler = lib.omega_list_matcher_compiler_create(
                compiled_file.encode("utf-8"),
                int(case_insensitive),
                int(ignore_punctuation),
                int(elide_whitespace),
            )
        except AttributeError as e:
            raise AttributeError(
                "Failed to access omega_list_matcher_compiler_create. "
                "Check that the native library exports this symbol."
            ) from e
        if self._compiler == ffi.NULL:
            raise RuntimeError("Failed to create compiler")

        register_compiler(self)

    def __enter__(self):
        return self

    def __exit__(
        self,
        _exc_type: Optional[type[BaseException]],
        _exc_val: Optional[BaseException],
        _exc_tb: Optional[BaseException],
    ) -> None:
        self.destroy()

    def __del__(self):
        self.destroy()

    def add_pattern(self, pattern: bytes) -> None:
        if not isinstance(pattern, (bytes, bytearray)):
            raise TypeError("Pattern must be bytes")
        if (
            self._lib.omega_list_matcher_compiler_add_pattern(
                self._compiler, pattern, len(pattern)
            )
            != 0
        ):
            raise ValueError("Failed to add pattern")

    def get_stats(self) -> PatternStoreStats:
        stats_ptr = self._lib.omega_list_matcher_compiler_get_pattern_store_stats(
            self._compiler
        )
        if stats_ptr == ffi.NULL:
            raise RuntimeError("Failed to retrieve stats")
        return PatternStoreStats(
            **{k: getattr(stats_ptr, k) for k in PatternStoreStats.__annotations__}
        )

    def destroy(self) -> None:
        if hasattr(self, "_compiler") and self._compiler and C is not None:
            self._lib.omega_list_matcher_compiler_destroy(self._compiler)
            self._compiler = ffi.NULL

    @staticmethod
    def compile_from_filename(
        compiled_file: str,
        patterns_file: str,
        case_insensitive: bool = False,
        ignore_punctuation: bool = False,
        elide_whitespace: bool = False,
    ) -> PatternStoreStats:
        stats = ffi.new("omega_match_pattern_store_stats_t*")
        if (
            _get_library().omega_list_matcher_compile_patterns_filename(
                compiled_file.encode("utf-8"),
                patterns_file.encode("utf-8"),
                int(case_insensitive),
                int(ignore_punctuation),
                int(elide_whitespace),
                stats,
            )
            != 0
        ):
            raise RuntimeError("Compilation failed")
        return PatternStoreStats(
            **{k: getattr(stats, k) for k in PatternStoreStats.__annotations__}
        )

    @staticmethod
    def compile_from_buffer(
        compiled_file: str,
        patterns_buf: bytes,
        case_insensitive: bool = False,
        ignore_punctuation: bool = False,
        elide_whitespace: bool = False,
    ) -> PatternStoreStats:
        stats = ffi.new("omega_match_pattern_store_stats_t*")
        if (
            _get_library().omega_list_matcher_compile_patterns(
                compiled_file.encode("utf-8"),
                patterns_buf,
                len(patterns_buf),
                int(case_insensitive),
                int(ignore_punctuation),
                int(elide_whitespace),
                stats,
            )
            != 0
        ):
            raise RuntimeError("Compilation failed")
        return PatternStoreStats(
            **{k: getattr(stats, k) for k in PatternStoreStats.__annotations__}
        )


class Matcher:
    _matcher = None
    _lib = None

    def __init__(
        self,
        compiled_or_patterns_file: str,
        case_insensitive: bool = False,
        ignore_punctuation: bool = False,
        elide_whitespace: bool = False,
    ) -> None:
        lib = _get_library()
        self._lib = lib
        pat_stats = ffi.new("omega_match_pattern_store_stats_t*")
        m = lib.omega_list_matcher_create(
            compiled_or_patterns_file.encode("utf-8"),
            int(case_insensitive),
            int(ignore_punctuation),
            int(elide_whitespace),
            pat_stats,
        )
        if m == ffi.NULL:
            raise RuntimeError("Failed to create matcher")
        self._matcher = m

        self._match_stats = ffi.new("omega_match_stats_t*")
        if lib.omega_list_matcher_add_stats(self._matcher, self._match_stats) != 0:
            raise RuntimeError("Failed to attach stats to matcher")

        register_matcher(self)

    def __enter__(self):
        return self

    def __exit__(
        self,
        _exc_type: Optional[type[BaseException]],
        _exc_val: Optional[BaseException],
        _exc_tb: Optional[BaseException],
    ) -> None:
        self.destroy()

    def __del__(self):
        self.destroy()

    def match(
        self,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> List[MatchResult]:
        if not isinstance(haystack, (bytes, bytearray)):
            raise TypeError("haystack must be bytes or bytearray")
        lib = _get_library()
        buf = ffi.new("uint8_t[]", haystack)
        res = lib.omega_list_matcher_match(
            self._matcher,
            buf,
            len(haystack),
            int(no_overlap),
            int(longest_only),
            int(word_boundary),
            int(word_prefix),
            int(word_suffix),
            int(line_start),
            int(line_end),
        )
        if res == ffi.NULL:
            return []

        out: List[MatchResult] = []
        for i in range(res.count):
            m = res.matches[i]
            out.append(
                MatchResult(offset=m.offset, match=bytes(ffi.buffer(m.match, m.len)))
            )
        lib.omega_match_results_destroy(res)
        return out

    def get_match_stats(self) -> MatchStats:
        ms = self._match_stats
        return MatchStats(
            **{k: int(getattr(ms, k)) for k in MatchStats.__annotations__}
        )

    def reset_match_stats(self) -> None:
        ms = self._match_stats
        for k in MatchStats.__annotations__:
            setattr(ms, k, 0)

    def set_threads(self, threads: int) -> None:
        if _get_library().omega_matcher_set_num_threads(self._matcher, threads) != 0:
            raise ValueError(f"Invalid thread count: {threads}")

    def get_threads(self) -> int:
        return _get_library().omega_matcher_get_num_threads(self._matcher)

    def set_chunk_size(self, chunk: int) -> None:
        if _get_library().omega_matcher_set_chunk_size(self._matcher, chunk) != 0:
            raise ValueError(f"Invalid chunk size: {chunk}")

    def get_chunk_size(self) -> int:
        return _get_library().omega_matcher_get_chunk_size(self._matcher)

    def destroy(self) -> None:
        if hasattr(self, "_matcher") and self._matcher and hasattr(self, "_lib"):
            self._lib.omega_list_matcher_destroy(self._matcher)
            self._matcher = ffi.NULL


_destroyed_objects: set[int] = set()
_destroy_lock = threading.Lock()


class Destroyable(Protocol):
    def destroy(self) -> None: ...


def _safe_destroy(obj: Destroyable, name: str):
    with _destroy_lock:
        if id(obj) in _destroyed_objects:
            return
        try:
            obj.destroy()
        except Exception as e:
            print(f"Exception in {name}.destroy(): {e}", file=sys.stderr)
        _destroyed_objects.add(id(obj))


# Register atexit cleanup for all live Compiler/Matcher objects
_live_compilers: List["Compiler"] = []
_live_matchers: List["Matcher"] = []


def register_compiler(c: "Compiler") -> None:
    _live_compilers.append(c)


def register_matcher(m: "Matcher") -> None:
    _live_matchers.append(m)


def cleanup_all():
    for c in _live_compilers:
        _safe_destroy(c, "Compiler")
    for m in _live_matchers:
        _safe_destroy(m, "Matcher")


atexit.register(cleanup_all)
