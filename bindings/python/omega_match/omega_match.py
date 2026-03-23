# omega_match.py

import atexit
import ctypes
import os
import platform
import sys
import threading
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Protocol, Sequence, Tuple, Union

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
  uint32_t _reserved;   // Padding for alignment
  const uint8_t *match; // Pointer to matched bytes in haystack
  uint64_t key;         // User-defined key (0 if not compiled with keys)
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
 * Add a single pattern with an associated user-defined key.
 * @param compiler Compiler handle.
 * @param pattern Pointer to pattern bytes.
 * @param len Length in bytes of the pattern.
 * @param key User-defined 64-bit key associated with this pattern.
 * @return 0 on success, -1 on error.
 */
int omega_list_matcher_compiler_add_pattern_with_key(
    omega_list_matcher_compiler_t *restrict compiler,
    const uint8_t *restrict pattern, uint32_t len, uint64_t key);

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

typedef struct omega_builtin_reactor_struct omega_builtin_reactor_t;
typedef struct omega_native_reactor_struct omega_native_reactor_t;
typedef struct omega_native_reactor_builder_struct omega_native_reactor_builder_t;
typedef struct omega_rewrite_plan_struct omega_rewrite_plan_t;
typedef struct omega_rewrite_script_struct omega_rewrite_script_t;

typedef int (*omega_native_reactor_handler_fn)(
    omega_rewrite_plan_t *plan, const omega_match_result_t *match,
    void *handler_ctx);

typedef int (*omega_native_reactor_plugin_init_fn)(
    omega_native_reactor_builder_t *builder, void *plugin_ctx);

typedef enum {
  OMEGA_REWRITE_NOOP = 0,
  OMEGA_REWRITE_OVERWRITE = 1,
  OMEGA_REWRITE_REPLACE = 2,
  OMEGA_REWRITE_INSERT = 3,
  OMEGA_REWRITE_DELETE = 4,
  OMEGA_REWRITE_SIDE_EFFECT = 5
} omega_rewrite_action_kind_t;

typedef enum {
  OMEGA_REACTOR_BUILTIN_UPPER = 1,
  OMEGA_REACTOR_BUILTIN_LOWER = 2,
  OMEGA_REACTOR_BUILTIN_REDACT = 3,
  OMEGA_REACTOR_BUILTIN_UUID = 4
} omega_builtin_reactor_opcode_t;

typedef struct {
  size_t start;
  size_t end;
  uint64_t rule_id;
  omega_rewrite_action_kind_t kind;
  const uint8_t *data;
  size_t data_len;
} omega_rewrite_action_t;

typedef struct {
  uint64_t rule_id;
  uint32_t opcode;
  uint8_t redact_byte;
  uint8_t _reserved[3];
} omega_builtin_reactor_rule_t;

typedef struct {
  uint64_t rule_id;
  omega_native_reactor_handler_fn handler;
  void *handler_ctx;
} omega_native_reactor_rule_t;

typedef struct {
  size_t offset;
  size_t length;
  uint64_t rule_id;
  uint32_t kind;
  const uint8_t *data;
  size_t data_len;
} omega_rewrite_script_op_t;

omega_builtin_reactor_t *omega_builtin_reactor_create(
    const omega_builtin_reactor_rule_t *restrict rules, size_t rule_count);
int omega_builtin_reactor_destroy(omega_builtin_reactor_t *restrict reactor);
omega_rewrite_plan_t *omega_builtin_reactor_plan_matches(
    const omega_builtin_reactor_t *restrict reactor,
    const omega_match_results_t *restrict results);
omega_rewrite_plan_t *omega_builtin_reactor_plan(
    const omega_builtin_reactor_t *restrict reactor,
    const omega_list_matcher_t *restrict matcher,
    const uint8_t *restrict haystack, size_t haystack_size, int no_overlap,
    int longest_only, int word_boundary, int word_prefix, int word_suffix,
    int line_start, int line_end);
size_t omega_rewrite_plan_get_action_count(
    const omega_rewrite_plan_t *restrict plan);
const omega_rewrite_action_t *omega_rewrite_plan_get_actions(
    const omega_rewrite_plan_t *restrict plan);
int omega_rewrite_plan_destroy(omega_rewrite_plan_t *restrict plan);
omega_native_reactor_builder_t *omega_native_reactor_builder_create(void);
int omega_native_reactor_builder_destroy(
    omega_native_reactor_builder_t *restrict builder);
int omega_native_reactor_builder_add_rule(
    omega_native_reactor_builder_t *restrict builder, uint64_t rule_id,
    omega_native_reactor_handler_fn handler, void *handler_ctx);
int omega_native_reactor_builder_load_plugin(
    omega_native_reactor_builder_t *restrict builder,
    const char *restrict library_path, const char *restrict init_symbol,
    void *plugin_ctx);
omega_native_reactor_t *omega_native_reactor_builder_build(
    omega_native_reactor_builder_t *restrict builder);
omega_native_reactor_t *omega_native_reactor_create(
    const omega_native_reactor_rule_t *restrict rules, size_t rule_count);
int omega_native_reactor_destroy(omega_native_reactor_t *restrict reactor);
omega_rewrite_plan_t *omega_native_reactor_plan_matches(
    const omega_native_reactor_t *restrict reactor,
    const omega_match_results_t *restrict results);
omega_rewrite_plan_t *omega_native_reactor_plan(
    const omega_native_reactor_t *restrict reactor,
    const omega_list_matcher_t *restrict matcher,
    const uint8_t *restrict haystack, size_t haystack_size, int no_overlap,
    int longest_only, int word_boundary, int word_prefix, int word_suffix,
    int line_start, int line_end);
omega_rewrite_plan_t *omega_rewrite_plan_create(void);
int omega_rewrite_plan_add_action(omega_rewrite_plan_t *restrict plan,
                                  size_t start, size_t end, uint64_t rule_id,
                                  omega_rewrite_action_kind_t kind,
                                  const uint8_t *data, size_t data_len);
omega_rewrite_script_t *omega_rewrite_script_create(
    const omega_rewrite_plan_t *restrict plan);
int omega_rewrite_script_destroy(omega_rewrite_script_t *restrict script);
size_t omega_rewrite_script_get_op_count(
    const omega_rewrite_script_t *restrict script);
const omega_rewrite_script_op_t *omega_rewrite_script_get_ops(
    const omega_rewrite_script_t *restrict script);
int omega_rewrite_script_apply_bytes(
    const omega_rewrite_script_t *restrict script,
    const uint8_t *restrict input, size_t input_len, uint8_t **restrict output,
    size_t *restrict output_len);
void omega_rewrite_bytes_destroy(uint8_t *bytes);
int omega_rewrite_script_omega_edit_available(void);
int omega_rewrite_script_apply_omega_edit(
    const omega_rewrite_script_t *restrict script,
    const char *restrict input_file, const char *restrict output_file);

"""
)

# C library FFI handle
C = None
_pinned_native_libraries: Dict[str, object] = {}
_dll_directory_handles: Dict[str, object] = {}
UINT64_MAX = (1 << 64) - 1

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
    key: int = 0

    @property
    def length(self) -> int:
        return len(self.match)


@dataclass
class RewriteAction:
    start: int
    end: int
    rule_id: int
    kind: int
    data: bytes

    @property
    def length(self) -> int:
        return self.end - self.start

    @staticmethod
    def overwrite(match: MatchResult, data: bytes) -> "RewriteAction":
        if len(data) != match.length:
            raise ValueError("overwrite data length must match the match length")
        return RewriteAction(
            start=match.offset,
            end=match.offset + match.length,
            rule_id=match.key,
            kind=BuiltinReactor.KIND_OVERWRITE,
            data=bytes(data),
        )

    @staticmethod
    def replace(match: MatchResult, data: bytes) -> "RewriteAction":
        return RewriteAction(
            start=match.offset,
            end=match.offset + match.length,
            rule_id=match.key,
            kind=BuiltinReactor.KIND_REPLACE,
            data=bytes(data),
        )

    @staticmethod
    def delete(match: MatchResult) -> "RewriteAction":
        return RewriteAction(
            start=match.offset,
            end=match.offset + match.length,
            rule_id=match.key,
            kind=BuiltinReactor.KIND_DELETE,
            data=b"",
        )

    @staticmethod
    def insert(offset: int, data: bytes, rule_id: int = 0) -> "RewriteAction":
        return RewriteAction(
            start=offset,
            end=offset,
            rule_id=rule_id,
            kind=BuiltinReactor.KIND_INSERT,
            data=bytes(data),
        )


@dataclass
class ReactorSideEffect:
    kind: str
    rule_id: int
    offset: int
    length: int
    payload: Any = None

    @staticmethod
    def for_match(match: MatchResult, kind: str, payload: Any = None) -> "ReactorSideEffect":
        return ReactorSideEffect(
            kind=kind,
            rule_id=match.key,
            offset=match.offset,
            length=match.length,
            payload=payload,
        )


@dataclass
class ReactorEmission:
    actions: List[RewriteAction] = field(default_factory=list)
    side_effects: List[ReactorSideEffect] = field(default_factory=list)


@dataclass
class RewriteScriptOp:
    offset: int
    length: int
    rule_id: int
    kind: int
    data: bytes


@dataclass
class NativeReactorRule:
    rule_id: int


@dataclass
class BuiltinReactorRule:
    rule_id: int
    opcode: int
    redact_byte: int = ord("X")


ReactorCallbackReturn = Union[
    None,
    RewriteAction,
    ReactorSideEffect,
    ReactorEmission,
    Sequence[Union[RewriteAction, ReactorSideEffect]],
]


def _plan_ptr_to_actions(lib, plan) -> List[RewriteAction]:
    actions_ptr = lib.omega_rewrite_plan_get_actions(plan)
    action_count = lib.omega_rewrite_plan_get_action_count(plan)
    actions: List[RewriteAction] = []
    for i in range(action_count):
        action = actions_ptr[i]
        data = (
            bytes(ffi.buffer(action.data, action.data_len))
            if action.data != ffi.NULL and action.data_len > 0
            else b""
        )
        actions.append(
            RewriteAction(
                start=int(action.start),
                end=int(action.end),
                rule_id=int(action.rule_id),
                kind=int(action.kind),
                data=data,
            )
        )
    return actions


def _normalize_emission(
    value: ReactorCallbackReturn, match: Optional[MatchResult] = None
) -> ReactorEmission:
    if value is None:
        return ReactorEmission()
    if isinstance(value, ReactorEmission):
        return ReactorEmission(
            actions=list(value.actions), side_effects=list(value.side_effects)
        )
    if isinstance(value, RewriteAction):
        return ReactorEmission(actions=[value])
    if isinstance(value, ReactorSideEffect):
        return ReactorEmission(side_effects=[value])
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        emission = ReactorEmission()
        for item in value:
            item_emission = _normalize_emission(item, match)
            emission.actions.extend(item_emission.actions)
            emission.side_effects.extend(item_emission.side_effects)
        return emission
    if match is not None:
        raise TypeError(
            f"callback for rule_id {match.key} returned unsupported value: {type(value)!r}"
        )
    raise TypeError(f"unsupported reactor emission value: {type(value)!r}")


def _validate_rewrite_action(action: RewriteAction) -> None:
    if not isinstance(action.start, int) or not isinstance(action.end, int):
        raise TypeError("RewriteAction start/end must be integers")
    if action.start < 0 or action.end < action.start:
        raise ValueError("RewriteAction must satisfy 0 <= start <= end")
    if not isinstance(action.rule_id, int):
        raise TypeError("RewriteAction rule_id must be an integer")
    if action.rule_id < 0 or action.rule_id > UINT64_MAX:
        raise ValueError("RewriteAction rule_id must be between 0 and 2^64 - 1")
    if action.kind not in {
        BuiltinReactor.KIND_NOOP,
        BuiltinReactor.KIND_OVERWRITE,
        BuiltinReactor.KIND_REPLACE,
        BuiltinReactor.KIND_INSERT,
        BuiltinReactor.KIND_DELETE,
        BuiltinReactor.KIND_SIDE_EFFECT,
    }:
        raise ValueError(f"unsupported rewrite action kind: {action.kind}")
    if not isinstance(action.data, (bytes, bytearray)):
        raise TypeError("RewriteAction data must be bytes or bytearray")
    if action.kind == BuiltinReactor.KIND_OVERWRITE and len(action.data) != action.length:
        raise ValueError("overwrite action data length must match action span length")
    if action.kind == BuiltinReactor.KIND_DELETE and len(action.data) != 0:
        raise ValueError("delete action must not carry payload bytes")
    if action.kind == BuiltinReactor.KIND_INSERT and action.start != action.end:
        raise ValueError("insert action must have start == end")


def _build_plan_ptr_from_actions(lib, actions: Sequence[RewriteAction]):
    plan = lib.omega_rewrite_plan_create()
    if plan == ffi.NULL:
        raise RuntimeError("Failed to create rewrite plan")
    try:
        for action in actions:
            _validate_rewrite_action(action)
            data = bytes(action.data)
            rc = lib.omega_rewrite_plan_add_action(
                plan,
                action.start,
                action.end,
                action.rule_id,
                action.kind,
                data if data else ffi.NULL,
                len(data),
            )
            if rc != 0:
                raise RuntimeError("Failed to add rewrite action to native plan")
        return plan
    except Exception:
        lib.omega_rewrite_plan_destroy(plan)
        raise


def _script_from_plan_ptr(lib, plan) -> "RewriteScript":
    script = lib.omega_rewrite_script_create(plan)
    if script == ffi.NULL:
        raise RuntimeError("Failed to build rewrite script (possibly overlapping edits)")
    return RewriteScript(lib, script)


def _fnv1a64_seeded(seed: int, data: bytes) -> int:
    h = seed & UINT64_MAX
    for byte in data:
        h ^= byte
        h = (h * 1099511628211) & UINT64_MAX
    return h


def _fnv1a64_u64(seed: int, value: int) -> int:
    return _fnv1a64_seeded(seed, value.to_bytes(8, "little", signed=False))


def _make_uuid_v8(rule_id: int, start: int, length: int, match: bytes) -> bytes:
    h1 = 1469598103934665603
    h2 = 1099511628211
    h1 = _fnv1a64_u64(h1, rule_id)
    h1 = _fnv1a64_u64(h1, start)
    h1 = _fnv1a64_u64(h1, length)
    h1 = _fnv1a64_seeded(h1, match)

    h2 = _fnv1a64_u64(h2, rule_id ^ 0x9E3779B97F4A7C15)
    h2 = _fnv1a64_u64(h2, start ^ 0xD6E8FEB86659FD93)
    h2 = _fnv1a64_u64(h2, length ^ 0xA5A3564E27F88691)
    h2 = _fnv1a64_seeded(h2, match)

    raw = bytearray(h1.to_bytes(8, "big") + h2.to_bytes(8, "big"))
    raw[6] = (raw[6] & 0x0F) | 0x80
    raw[8] = (raw[8] & 0x3F) | 0x80
    parts = (
        raw[0:4].hex(),
        raw[4:6].hex(),
        raw[6:8].hex(),
        raw[8:10].hex(),
        raw[10:16].hex(),
    )
    return f"{parts[0]}-{parts[1]}-{parts[2]}-{parts[3]}-{parts[4]}".encode("ascii")


def _emit_builtin_action(match: MatchResult, rule: BuiltinReactorRule) -> RewriteAction:
    if rule.opcode == BuiltinReactor.OP_UPPER:
        return RewriteAction.overwrite(match, match.match.upper())
    if rule.opcode == BuiltinReactor.OP_LOWER:
        return RewriteAction.overwrite(match, match.match.lower())
    if rule.opcode == BuiltinReactor.OP_REDACT:
        return RewriteAction.overwrite(
            match, bytes([rule.redact_byte]) * match.length
        )
    if rule.opcode == BuiltinReactor.OP_UUID:
        return RewriteAction.replace(
            match,
            _make_uuid_v8(match.key, match.offset, match.length, match.match),
        )
    raise ValueError(f"unsupported builtin opcode: {rule.opcode}")


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
    if system in {"win32", "cygwin"}:
        canonical_name = "omega_match.dll"
    elif system == "darwin":
        canonical_name = "libomega_match.dylib"
    else:
        canonical_name = "libomega_match.so"

    canonical_path = lib_dir_path / canonical_name
    if canonical_path.is_file():
        return canonical_path, "local-build", "Development"

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
        override = os.path.abspath(override)
        # Store library info for override path
        global _library_info
        _library_info = {
            "path": override,
            "variant": "custom-override",
            "optimization": "Unknown",
            "platform": f"{sys.platform}-{platform.machine().lower()}",
        }
        _pin_native_library(override)
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

    _pin_native_library(str(lib_path))
    return ffi.dlopen(str(lib_path))


def _pin_native_library(lib_path: str) -> None:
    if sys.platform in {"win32", "cygwin"}:
        lib_dir = os.path.dirname(lib_path)
        if lib_dir and lib_dir not in _dll_directory_handles:
            _dll_directory_handles[lib_dir] = os.add_dll_directory(lib_dir)

    if lib_path in _pinned_native_libraries:
        return

    # Keep an explicit ctypes handle alive for the lifetime of the process so
    # the cffi handle is not the final owner during interpreter shutdown.
    if sys.platform in {"win32", "cygwin"}:
        _pinned_native_libraries[lib_path] = ctypes.WinDLL(lib_path)
    else:
        _pinned_native_libraries[lib_path] = ctypes.CDLL(lib_path)


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
        self._omega_destroyed = False
        self._omega_destroying = False
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
        if globals().get("_is_shutting_down") or globals().get("ffi") is None:
            return
        try:
            self.destroy()
        except Exception:
            pass

    def add_pattern(self, pattern: bytes, key: int = 0) -> None:
        if not isinstance(pattern, (bytes, bytearray)):
            raise TypeError("Pattern must be bytes")
        if not isinstance(key, int):
            raise TypeError("key must be an integer")
        if key < 0 or key > UINT64_MAX:
            raise ValueError("key must be between 0 and 2^64 - 1")
        if key != 0:
            if (
                self._lib.omega_list_matcher_compiler_add_pattern_with_key(
                    self._compiler, pattern, len(pattern), key
                )
                != 0
            ):
                raise ValueError("Failed to add pattern with key")
        else:
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
        module_ffi = globals().get("ffi")
        compiler = getattr(self, "_compiler", None)
        lib = getattr(self, "_lib", None)
        if module_ffi is None or lib is None or compiler in (None, module_ffi.NULL):
            self._omega_destroyed = True
            _live_compilers.discard(self)
            return
        lib.omega_list_matcher_compiler_destroy(compiler)
        self._compiler = module_ffi.NULL
        self._omega_destroyed = True
        _live_compilers.discard(self)

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
        self._omega_destroyed = False
        self._omega_destroying = False
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
        if globals().get("_is_shutting_down") or globals().get("ffi") is None:
            return
        try:
            self.destroy()
        except Exception:
            pass

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
                MatchResult(offset=m.offset, match=bytes(ffi.buffer(m.match, m.len)),
                            key=int(m.key))
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
        module_ffi = globals().get("ffi")
        matcher = getattr(self, "_matcher", None)
        lib = getattr(self, "_lib", None)
        if module_ffi is None or lib is None or matcher in (None, module_ffi.NULL):
            self._omega_destroyed = True
            _live_matchers.discard(self)
            return
        lib.omega_list_matcher_destroy(matcher)
        self._matcher = module_ffi.NULL
        self._omega_destroyed = True
        _live_matchers.discard(self)


class BuiltinReactor:
    OP_UPPER = 1
    OP_LOWER = 2
    OP_REDACT = 3
    OP_UUID = 4

    KIND_NOOP = 0
    KIND_OVERWRITE = 1
    KIND_REPLACE = 2
    KIND_INSERT = 3
    KIND_DELETE = 4
    KIND_SIDE_EFFECT = 5
    SCRIPT_DELETE = 1
    SCRIPT_INSERT = 2
    SCRIPT_OVERWRITE = 3

    def __init__(self, rules: List[BuiltinReactorRule]) -> None:
        if not rules:
            raise ValueError("rules must not be empty")
        self._omega_destroyed = False
        self._omega_destroying = False
        c_rules = ffi.new("omega_builtin_reactor_rule_t[]", len(rules))
        for i, rule in enumerate(rules):
            if not isinstance(rule.rule_id, int):
                raise TypeError("rule_id must be an integer")
            if rule.rule_id < 0 or rule.rule_id > UINT64_MAX:
                raise ValueError("rule_id must be between 0 and 2^64 - 1")
            if not isinstance(rule.opcode, int):
                raise TypeError("opcode must be an integer")
            if rule.opcode not in {
                self.OP_UPPER,
                self.OP_LOWER,
                self.OP_REDACT,
                self.OP_UUID,
            }:
                raise ValueError(f"unsupported builtin opcode: {rule.opcode}")
            if not isinstance(rule.redact_byte, int):
                raise TypeError("redact_byte must be an integer")
            if rule.redact_byte < 0 or rule.redact_byte > 0xFF:
                raise ValueError("redact_byte must be between 0 and 255")

            c_rules[i].rule_id = rule.rule_id
            c_rules[i].opcode = rule.opcode
            c_rules[i].redact_byte = rule.redact_byte

        lib = _get_library()
        reactor = lib.omega_builtin_reactor_create(c_rules, len(rules))
        if reactor == ffi.NULL:
            raise RuntimeError("Failed to create builtin reactor")

        self._lib = lib
        self._reactor = reactor
        register_reactor(self)

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
        if globals().get("_is_shutting_down") or globals().get("ffi") is None:
            return
        try:
            self.destroy()
        except Exception:
            pass

    def plan(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> List[RewriteAction]:
        if not isinstance(haystack, (bytes, bytearray)):
            raise TypeError("haystack must be bytes or bytearray")
        if getattr(matcher, "_matcher", ffi.NULL) == ffi.NULL:
            raise RuntimeError("Matcher has been destroyed")

        plan = self._build_plan_ptr(
            matcher,
            haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        )

        try:
            return _plan_ptr_to_actions(self._lib, plan)
        finally:
            self._lib.omega_rewrite_plan_destroy(plan)

    def build_script(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> "RewriteScript":
        plan = self._build_plan_ptr(
            matcher,
            haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        )
        try:
            return _script_from_plan_ptr(self._lib, plan)
        finally:
            self._lib.omega_rewrite_plan_destroy(plan)

    def rewrite_bytes(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> bytes:
        with self.build_script(
            matcher,
            haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        ) as script:
            return script.apply_bytes(haystack)

    def _build_plan_ptr(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ):
        buf = ffi.new("uint8_t[]", haystack)
        plan = self._lib.omega_builtin_reactor_plan(
            self._reactor,
            matcher._matcher,
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
        if plan == ffi.NULL:
            raise RuntimeError("Failed to build rewrite plan")
        return plan

    def destroy(self) -> None:
        module_ffi = globals().get("ffi")
        reactor = getattr(self, "_reactor", None)
        lib = getattr(self, "_lib", None)
        if module_ffi is None or lib is None or reactor in (None, module_ffi.NULL):
            self._omega_destroyed = True
            _live_reactors.discard(self)
            return
        lib.omega_builtin_reactor_destroy(reactor)
        self._reactor = module_ffi.NULL
        self._omega_destroyed = True
        _live_reactors.discard(self)


class Reactor:
    """High-level Python reactor that combines native builtins and Python callbacks.

    Performance model:
    - builtin-only reactors use the native builtin path
    - reactors with any Python callback run action emission in Python
    """

    def __init__(self) -> None:
        self._builtin_rules: Dict[int, BuiltinReactorRule] = {}
        self._callbacks: Dict[int, Callable[[MatchResult], ReactorCallbackReturn]] = {}
        self._native_builtin: Optional[BuiltinReactor] = None
        self._omega_destroyed = False
        self._omega_destroying = False
        register_reactor(self)

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
        if globals().get("_is_shutting_down") or globals().get("ffi") is None:
            return
        try:
            self.destroy()
        except Exception:
            pass

    def add_builtin(
        self, rule_id: int, operation: str, *, redact_byte: int = ord("X")
    ) -> "Reactor":
        if rule_id in self._callbacks or rule_id in self._builtin_rules:
            raise ValueError(f"rule_id {rule_id} is already registered")
        opcode_map = {
            "upper": BuiltinReactor.OP_UPPER,
            "lower": BuiltinReactor.OP_LOWER,
            "redact": BuiltinReactor.OP_REDACT,
            "uuid": BuiltinReactor.OP_UUID,
        }
        if not isinstance(rule_id, int):
            raise TypeError("rule_id must be an integer")
        if rule_id < 0 or rule_id > UINT64_MAX:
            raise ValueError("rule_id must be between 0 and 2^64 - 1")
        if operation not in opcode_map:
            raise ValueError(
                "operation must be one of: upper, lower, redact, uuid"
            )
        if not isinstance(redact_byte, int):
            raise TypeError("redact_byte must be an integer")
        if redact_byte < 0 or redact_byte > 0xFF:
            raise ValueError("redact_byte must be between 0 and 255")
        self._builtin_rules[rule_id] = BuiltinReactorRule(
            rule_id=rule_id, opcode=opcode_map[operation], redact_byte=redact_byte
        )
        self._drop_native_builtin()
        return self

    def add_callback(
        self, rule_id: int, callback: Callable[[MatchResult], ReactorCallbackReturn]
    ) -> "Reactor":
        if rule_id in self._callbacks or rule_id in self._builtin_rules:
            raise ValueError(f"rule_id {rule_id} is already registered")
        if not isinstance(rule_id, int):
            raise TypeError("rule_id must be an integer")
        if rule_id < 0 or rule_id > UINT64_MAX:
            raise ValueError("rule_id must be between 0 and 2^64 - 1")
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._callbacks[rule_id] = callback
        self._drop_native_builtin()
        return self

    on = add_callback

    def plan(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> ReactorEmission:
        if not isinstance(haystack, (bytes, bytearray)):
            raise TypeError("haystack must be bytes or bytearray")
        if getattr(matcher, "_matcher", ffi.NULL) == ffi.NULL:
            raise RuntimeError("Matcher has been destroyed")
        if not self._callbacks and self._builtin_rules:
            native = self._get_native_builtin()
            return ReactorEmission(
                actions=native.plan(
                    matcher,
                    haystack,
                    no_overlap=no_overlap,
                    longest_only=longest_only,
                    word_boundary=word_boundary,
                    word_prefix=word_prefix,
                    word_suffix=word_suffix,
                    line_start=line_start,
                    line_end=line_end,
                )
            )

        results = matcher.match(
            haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        )
        emission = ReactorEmission()
        for result in results:
            builtin_rule = self._builtin_rules.get(result.key)
            if builtin_rule is not None:
                emission.actions.append(_emit_builtin_action(result, builtin_rule))
            callback = self._callbacks.get(result.key)
            if callback is not None:
                callback_emission = _normalize_emission(callback(result), result)
                for action in callback_emission.actions:
                    _validate_rewrite_action(action)
                emission.actions.extend(callback_emission.actions)
                emission.side_effects.extend(callback_emission.side_effects)
        return emission

    def build_script(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> "RewriteScript":
        if not self._callbacks and self._builtin_rules:
            native = self._get_native_builtin()
            return native.build_script(
                matcher,
                haystack,
                no_overlap=no_overlap,
                longest_only=longest_only,
                word_boundary=word_boundary,
                word_prefix=word_prefix,
                word_suffix=word_suffix,
                line_start=line_start,
                line_end=line_end,
            )
        emission = self.plan(
            matcher,
            haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        )
        plan = _build_plan_ptr_from_actions(_get_library(), emission.actions)
        try:
            return _script_from_plan_ptr(_get_library(), plan)
        finally:
            _get_library().omega_rewrite_plan_destroy(plan)

    def rewrite_bytes(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> bytes:
        with self.build_script(
            matcher,
            haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        ) as script:
            return script.apply_bytes(haystack)

    def destroy(self) -> None:
        self._drop_native_builtin()
        self._omega_destroyed = True
        _live_reactors.discard(self)

    def _get_native_builtin(self) -> BuiltinReactor:
        if self._native_builtin is None:
            self._native_builtin = BuiltinReactor(
                list(sorted(self._builtin_rules.values(), key=lambda rule: rule.rule_id))
            )
        return self._native_builtin

    def _drop_native_builtin(self) -> None:
        if self._native_builtin is not None:
            self._native_builtin.destroy()
            self._native_builtin = None


class NativePluginReactor:
    def __init__(self, plugin_path: str, init_symbol: Optional[str] = None) -> None:
        if not isinstance(plugin_path, str) or not plugin_path:
            raise ValueError("plugin_path must be a non-empty string")
        lib = _get_library()
        builder = lib.omega_native_reactor_builder_create()
        if builder == ffi.NULL:
            raise RuntimeError("Failed to create native reactor builder")
        self._lib = lib
        self._reactor = ffi.NULL
        self._builder = builder
        self._omega_destroyed = False
        self._omega_destroying = False
        try:
            symbol = (
                ffi.NULL
                if init_symbol is None
                else init_symbol.encode("utf-8")
            )
            rc = lib.omega_native_reactor_builder_load_plugin(
                builder,
                plugin_path.encode("utf-8"),
                symbol,
                ffi.NULL,
            )
            if rc != 0:
                raise RuntimeError("Failed to load native reactor plugin")
            reactor = lib.omega_native_reactor_builder_build(builder)
            if reactor == ffi.NULL:
                raise RuntimeError("Failed to build native reactor")
            self._reactor = reactor
            register_reactor(self)
        finally:
            if self._builder != ffi.NULL:
                lib.omega_native_reactor_builder_destroy(self._builder)
                self._builder = ffi.NULL

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
        if globals().get("_is_shutting_down") or globals().get("ffi") is None:
            return
        try:
            self.destroy()
        except Exception:
            pass

    def plan(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> List[RewriteAction]:
        plan = self._build_plan_ptr(
            matcher,
            haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        )
        try:
            return _plan_ptr_to_actions(self._lib, plan)
        finally:
            self._lib.omega_rewrite_plan_destroy(plan)

    def build_script(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> "RewriteScript":
        plan = self._build_plan_ptr(
            matcher,
            haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        )
        try:
            return _script_from_plan_ptr(self._lib, plan)
        finally:
            self._lib.omega_rewrite_plan_destroy(plan)

    def rewrite_bytes(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ) -> bytes:
        with self.build_script(
            matcher,
            haystack,
            no_overlap=no_overlap,
            longest_only=longest_only,
            word_boundary=word_boundary,
            word_prefix=word_prefix,
            word_suffix=word_suffix,
            line_start=line_start,
            line_end=line_end,
        ) as script:
            return script.apply_bytes(haystack)

    def _build_plan_ptr(
        self,
        matcher: Matcher,
        haystack: bytes,
        no_overlap: Literal[True, False] = False,
        longest_only: Literal[True, False] = False,
        word_boundary: Literal[True, False] = False,
        word_prefix: Literal[True, False] = False,
        word_suffix: Literal[True, False] = False,
        line_start: Literal[True, False] = False,
        line_end: Literal[True, False] = False,
    ):
        if not isinstance(haystack, (bytes, bytearray)):
            raise TypeError("haystack must be bytes or bytearray")
        if getattr(matcher, "_matcher", ffi.NULL) == ffi.NULL:
            raise RuntimeError("Matcher has been destroyed")
        if getattr(self, "_reactor", ffi.NULL) == ffi.NULL:
            raise RuntimeError("NativePluginReactor has been destroyed")
        buf = ffi.new("uint8_t[]", haystack)
        plan = self._lib.omega_native_reactor_plan(
            self._reactor,
            matcher._matcher,
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
        if plan == ffi.NULL:
            raise RuntimeError("Failed to build rewrite plan")
        return plan

    def destroy(self) -> None:
        module_ffi = globals().get("ffi")
        reactor = getattr(self, "_reactor", None)
        lib = getattr(self, "_lib", None)
        if module_ffi is None or lib is None or reactor in (None, module_ffi.NULL):
            self._omega_destroyed = True
            _live_reactors.discard(self)
            return
        lib.omega_native_reactor_destroy(reactor)
        self._reactor = module_ffi.NULL
        self._omega_destroyed = True
        _live_reactors.discard(self)


class RewriteScript:
    def __init__(self, lib, script) -> None:
        self._lib = lib
        self._script = script
        self._omega_destroyed = False
        self._omega_destroying = False
        register_rewrite_script(self)

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
        if globals().get("_is_shutting_down") or globals().get("ffi") is None:
            return
        try:
            self.destroy()
        except Exception:
            pass

    def ops(self) -> List[RewriteScriptOp]:
        script = getattr(self, "_script", ffi.NULL)
        if script == ffi.NULL:
            raise RuntimeError("RewriteScript has been destroyed")
        ops_ptr = self._lib.omega_rewrite_script_get_ops(script)
        op_count = self._lib.omega_rewrite_script_get_op_count(script)
        ops: List[RewriteScriptOp] = []
        for i in range(op_count):
            op = ops_ptr[i]
            data = (
                bytes(ffi.buffer(op.data, op.data_len))
                if op.data != ffi.NULL and op.data_len > 0
                else b""
            )
            ops.append(
                RewriteScriptOp(
                    offset=int(op.offset),
                    length=int(op.length),
                    rule_id=int(op.rule_id),
                    kind=int(op.kind),
                    data=data,
                )
            )
        return ops

    def apply_bytes(self, haystack: bytes) -> bytes:
        if not isinstance(haystack, (bytes, bytearray)):
            raise TypeError("haystack must be bytes or bytearray")
        script = getattr(self, "_script", ffi.NULL)
        if script == ffi.NULL:
            raise RuntimeError("RewriteScript has been destroyed")
        out_ptr = ffi.new("uint8_t **")
        out_len = ffi.new("size_t *")
        rc = self._lib.omega_rewrite_script_apply_bytes(
            script, haystack, len(haystack), out_ptr, out_len
        )
        if rc != 0:
            raise RuntimeError("Failed to apply rewrite script to bytes")
        try:
            if out_ptr[0] == ffi.NULL or out_len[0] == 0:
                return b""
            return bytes(ffi.buffer(out_ptr[0], out_len[0]))
        finally:
            self._lib.omega_rewrite_bytes_destroy(out_ptr[0])

    def apply_omega_edit(self, input_file: str, output_file: str) -> None:
        script = getattr(self, "_script", ffi.NULL)
        if script == ffi.NULL:
            raise RuntimeError("RewriteScript has been destroyed")
        rc = self._lib.omega_rewrite_script_apply_omega_edit(
            script, input_file.encode("utf-8"), output_file.encode("utf-8")
        )
        if rc != 0:
            raise RuntimeError("OmegaEdit apply failed or is unavailable")

    @staticmethod
    def omega_edit_available() -> bool:
        return bool(_get_library().omega_rewrite_script_omega_edit_available())

    def destroy(self) -> None:
        module_ffi = globals().get("ffi")
        script = getattr(self, "_script", None)
        lib = getattr(self, "_lib", None)
        if module_ffi is None or lib is None or script in (None, module_ffi.NULL):
            self._omega_destroyed = True
            _live_rewrite_scripts.discard(self)
            return
        lib.omega_rewrite_script_destroy(script)
        self._script = module_ffi.NULL
        self._omega_destroyed = True
        _live_rewrite_scripts.discard(self)


_destroy_lock = threading.Lock()
_is_shutting_down = False


class Destroyable(Protocol):
    def destroy(self) -> None: ...


def _mark_destroying(obj: Any) -> bool:
    with _destroy_lock:
        if getattr(obj, "_omega_destroyed", False) or getattr(
            obj, "_omega_destroying", False
        ):
            return False
        setattr(obj, "_omega_destroying", True)
        return True


def _clear_destroying(obj: Any, *, destroyed: bool) -> None:
    with _destroy_lock:
        setattr(obj, "_omega_destroying", False)
        if destroyed:
            setattr(obj, "_omega_destroyed", True)


def _safe_destroy(obj: Destroyable, name: str):
    if not _mark_destroying(obj):
        return
    try:
        obj.destroy()
    except Exception as e:
        _clear_destroying(obj, destroyed=False)
        stderr = getattr(sys, "stderr", None)
        if stderr is not None:
            print(f"Exception in {name}.destroy(): {e}", file=stderr)
    else:
        _clear_destroying(obj, destroyed=True)


# Register atexit cleanup for all live Compiler/Matcher objects without
# keeping them alive solely for shutdown bookkeeping.
_live_compilers = weakref.WeakSet()
_live_matchers = weakref.WeakSet()
_live_reactors = weakref.WeakSet()
_live_rewrite_scripts = weakref.WeakSet()


def register_compiler(c: "Compiler") -> None:
    _live_compilers.add(c)


def register_matcher(m: "Matcher") -> None:
    _live_matchers.add(m)


def register_reactor(r: "BuiltinReactor") -> None:
    _live_reactors.add(r)


def register_rewrite_script(script: "RewriteScript") -> None:
    _live_rewrite_scripts.add(script)


def cleanup_all():
    global _is_shutting_down
    _is_shutting_down = True
    for script in list(_live_rewrite_scripts):
        _safe_destroy(script, "RewriteScript")
    for r in list(_live_reactors):
        _safe_destroy(r, "BuiltinReactor")
    for m in list(_live_matchers):
        _safe_destroy(m, "Matcher")
    for c in list(_live_compilers):
        _safe_destroy(c, "Compiler")
    _live_rewrite_scripts.clear()
    _live_reactors.clear()
    _live_matchers.clear()
    _live_compilers.clear()


atexit.register(cleanup_all)
