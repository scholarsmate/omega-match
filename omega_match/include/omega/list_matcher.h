// list_matcher.h

#ifndef OMEGA_LIST_MATCHER_H
#define OMEGA_LIST_MATCHER_H

#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

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

#ifdef __cplusplus
}
#endif

#endif // OMEGA_LIST_MATCHER_H
