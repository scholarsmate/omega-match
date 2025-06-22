// matcher.c

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

// Define target architecture for Windows headers
#if defined(_M_X64) || defined(__x86_64__)
#ifndef _AMD64_
#define _AMD64_
#endif
#elif defined(_M_IX86) || defined(__i386__)
#ifndef _X86_
#define _X86_
#endif
#elif defined(_M_ARM64) || defined(__aarch64__)
#ifndef _ARM64_
#define _ARM64_
#endif
#elif defined(_M_ARM) || defined(__arm__)
#ifndef _ARM_
#define _ARM_
#endif
#endif

#include <windows.h>
#else
#include <limits.h>
#include <unistd.h>
#endif

#ifdef OMEGA_MATCH_USE_OPENMP
#include <omp.h>
#else
static inline int omp_get_max_threads(void) { return 1; }
static inline int omp_get_thread_num(void) { return 0; }
static inline void omp_set_num_threads(int n) { (void)n; }
static inline void omp_set_schedule(int kind, int chunk_size) {
  (void)kind;
  (void)chunk_size;
}
#endif
#include <stdbool.h>

#include "omega/details/attr.h"
#include "omega/details/bloom.h"
#include "omega/details/common.h"
#include "omega/details/hash_table.h"
#include "omega/details/match_vector.h"
#include "omega/details/transform_table.h"
#include "omega/details/util.h"
#include "omega/list_matcher.h"

#define CASE_INSENSITIVE_WINDOW_SIZE (4 * 1024 * 1024) // 4MB

#ifndef PATH_MAX
#ifdef _WIN32
#define PATH_MAX MAX_PATH // Windows-specific
#else
#define PATH_MAX (4096) // POSIX-safe fallback
#endif
#endif

// Opaque matcher structure
struct omega_list_matcher_struct {
  uint8_t *mapped_file_base;
  size_t mapped_file_size;
  int omp_num_threads;
  int omp_chunk_size;
  compiled_header_t *header;
  const uint8_t *pattern_store;
  bloom_filter_t bf;
  const uint32_t *index_array;
  const uint8_t *bucket_data;
  int case_insensitive;
  int ignore_punctuation;
  omega_match_stats_t *stats;
  char *temp_path; // non-NULL if compiled on the fly
  transform_table_t *transform_table;
  short_matcher_t short_matcher;
};

// Fast lookup table for word characters
static const uint8_t _wordmap[256] = {
    ['_'] = 1, ['0'] = 1, ['1'] = 1, ['2'] = 1, ['3'] = 1, ['4'] = 1,
    ['5'] = 1, ['6'] = 1, ['7'] = 1, ['8'] = 1, ['9'] = 1, ['A'] = 1,
    ['B'] = 1, ['C'] = 1, ['D'] = 1, ['E'] = 1, ['F'] = 1, ['G'] = 1,
    ['H'] = 1, ['I'] = 1, ['J'] = 1, ['K'] = 1, ['L'] = 1, ['M'] = 1,
    ['N'] = 1, ['O'] = 1, ['P'] = 1, ['Q'] = 1, ['R'] = 1, ['S'] = 1,
    ['T'] = 1, ['U'] = 1, ['V'] = 1, ['W'] = 1, ['X'] = 1, ['Y'] = 1,
    ['Z'] = 1, ['a'] = 1, ['b'] = 1, ['c'] = 1, ['d'] = 1, ['e'] = 1,
    ['f'] = 1, ['g'] = 1, ['h'] = 1, ['i'] = 1, ['j'] = 1, ['k'] = 1,
    ['l'] = 1, ['m'] = 1, ['n'] = 1, ['o'] = 1, ['p'] = 1, ['q'] = 1,
    ['r'] = 1, ['s'] = 1, ['t'] = 1, ['u'] = 1, ['v'] = 1, ['w'] = 1,
    ['x'] = 1, ['y'] = 1, ['z'] = 1};

// Check if a character is a word character (alphanumeric or underscore)
#define IS_WORD(c) (_wordmap[(uint8_t)(c)])

// Check if a character is a line ending (cross-platform)
OLM_ALWAYS_INLINE static int is_line_end(uint8_t c) {
  return c == '\n' || c == '\r';
}

// Check if position is at line start (beginning of buffer or after line ending)
OLM_ALWAYS_INLINE static int is_at_line_start(const uint8_t *restrict haystack,
                                              size_t pos) {
  if (pos == 0) {
    return 1;
  }
  return is_line_end(haystack[pos - 1]);
}

// Check if position is at line end (at line ending or end of buffer)
OLM_ALWAYS_INLINE static int is_at_line_end(const uint8_t *restrict haystack,
                                            size_t haystack_size, size_t pos,
                                            size_t len) {
  size_t end_pos = pos + len;
  if (end_pos >= haystack_size) {
    return 1;
  }
  return is_line_end(haystack[end_pos]);
}

// --- OMP Functions ---

// Set number of threads for matching on a specific matcher
// Returns 0 on success, -1 if 'threads' is out of valid range
int omega_matcher_set_num_threads(omega_list_matcher_t *restrict matcher,
                                  int threads) {
  const int max_threads = omp_get_max_threads();
  if (threads == 0) {
    threads = max_threads; // Use maximum available threads
  } else if (threads < 0 || threads > max_threads) {
    return -1; // invalid thread count
  }
  matcher->omp_num_threads = threads;
  return 0;
}

int omega_matcher_get_num_threads(
    const omega_list_matcher_t *restrict matcher) {
  return matcher->omp_num_threads;
}

// Set OpenMP chunk size (static schedule) for a specific matcher
// The 'chunk' should be a positive integer, rounded up to the next power of two
// if not already a power of two. Returns 0 on success, -1 on invalid chunk
// size.
int omega_matcher_set_chunk_size(omega_list_matcher_t *restrict matcher,
                                 int chunk) {
  if (chunk == 0) {
    chunk = 4096; // Default chunk size
  } else if (chunk < 1) {
    return -1; // invalid chunk size
  }
  // Ensure chunk size is a power of two
  else if ((chunk & (chunk - 1)) != 0) {
    chunk = (int)next_power_of_two(chunk);
  }
  matcher->omp_chunk_size = chunk;
  return 0;
}

int omega_matcher_get_chunk_size(const omega_list_matcher_t *restrict matcher) {
  return matcher->omp_chunk_size;
}

// Emit header information to a file (for the matcher)
int omega_list_matcher_emit_header_info(
    const omega_list_matcher_t *restrict matcher, FILE *restrict fp) {
  return emit_header_info(matcher->header, fp);
}

// Scan through the bucket's patterns and append exact matches.
static uint64_t scan_bucket_and_append(
    const uint8_t *restrict bucket_ptr, const uint8_t *restrict pat_store,
    match_vector_t *restrict local, const uint8_t *restrict haystack,
    const size_t haystack_size, const size_t pos, const int word_boundary,
    const int word_prefix, const int word_suffix, const int line_start,
    const int line_end, uint64_t *restrict compares) {
  uint64_t matches = 0;
  const uint32_t num_patterns = *(const uint32_t *)(bucket_ptr + 4);
  const uint8_t *pattern_ptr = bucket_ptr + 8;
  for (uint32_t j = 0; j < num_patterns; ++j) {
    const pattern_t *pat = (const pattern_t *)pattern_ptr;
    const uint32_t len = pat->len;
    if (unlikely(pos + len > haystack_size)) {
      pattern_ptr += sizeof(pattern_t);
      continue;
    }
    const size_t offset = pat->offset;
    pattern_ptr += sizeof(pattern_t);
    ++(*compares);
    if (memcmp(haystack + pos, pat_store + offset, len) != 0) {
      continue;
    }
    // Word boundary check (end of match)
    if (word_boundary &&
        (pos + len < haystack_size && IS_WORD(haystack[pos + len]))) {
      continue;
    }
    // Word prefix check (start of match)
    if (word_prefix && !(pos == 0 || !IS_WORD(haystack[pos - 1]))) {
      continue;
    }
    // Word suffix check (end of match)
    if (word_suffix &&
        !(pos + len == haystack_size || !IS_WORD(haystack[pos + len]))) {
      continue;
    }
    // Line start check (beginning of match)
    if (line_start && !is_at_line_start(haystack, pos)) {
      continue;
    }
    // Line end check (end of match)
    if (line_end && !is_at_line_end(haystack, haystack_size, pos, len)) {
      continue;
    }
    append_match(local, &(omega_match_result_t){pos, len, haystack + pos});
    ++matches;
  }
  return matches;
}

// --- Radix Sort for Matches ---
#define OFFSET_BYTES ((int)sizeof(size_t))
#define PASSES (OFFSET_BYTES + (int)sizeof(uint32_t))

static void radix_sort_matches(const match_vector_t *restrict mv) {
  const size_t n = mv->count;
  if (unlikely(n < 2)) {
    /* nothing to sort */
    return;
  }

  omega_match_result_t *tmp = malloc(n * sizeof(omega_match_result_t));
  uint8_t *keys = malloc(n * sizeof(uint8_t)); // cache per-pass key bytes
  if (unlikely(!tmp || !keys)) {
    ABORT("malloc for radix sort");
  }

  omega_match_result_t *in = mv->data;
  omega_match_result_t *out = tmp;

  for (int pass = 0; pass < PASSES; ++pass) {
    size_t count[256] = {0};

    /* 1. compute and histogram key bytes */
    for (size_t i = 0; i < n; ++i) {
      if (pass < 4) {
        // First 4 passes: sort by ~len (descending match length)
        keys[i] = (uint8_t)(~in[i].len >> (pass << 3) & 0xFFu);
      } else {
        // Remaining passes: sort by offset (ascending match position)
        keys[i] = (uint8_t)(in[i].offset >> ((pass - 4) << 3) & 0xFFu);
      }
      ++count[keys[i]];
    }

    /* 2. exclusive prefix sum */
    size_t sum = 0;
    for (size_t b = 0; b < 256; ++b) {
      const size_t c = count[b];
      count[b] = sum;
      sum += c;
    }

    /* 3. scatter using cached key bytes */
    for (size_t i = 0; i < n; ++i) {
      out[count[keys[i]]++] = in[i];
    }

    /* 4. swap roles */
    omega_match_result_t *tmp_ptr = in;
    in = out;
    out = tmp_ptr;
  }

  free(keys);
  free(tmp);
}

/*-------------------------------------------------------------*/

static int oa_matcher_load(const char *path, omega_list_matcher_t *matcher) {
  size_t size;
  uint8_t *map = omega_matcher_map_filename(path, &size, 0);

  // Needed to unmap the file later
  matcher->mapped_file_base = map;
  matcher->mapped_file_size = size;

  // 1. Map the header
  compiled_header_t *hdr = (compiled_header_t *)map;
  if (unlikely(memcmp(hdr->magic, HEADER_MAGIC, HEADER_MAGIC_SIZE) != 0)) {
    omega_matcher_unmap_file(map, size);
    return -1;
  }
  matcher->header = hdr;

  size_t offset = sizeof(compiled_header_t);

  // 2. Pattern store
  matcher->pattern_store = map + offset;
  offset += hdr->pattern_store_size;

  // 3. Bloom filter
  if (unlikely(memcmp(map + offset, BLOOM_HEADER, BLOOM_HEADER_SIZE) != 0)) {
    omega_matcher_unmap_file(map, size);
    return -1;
  }
  offset += BLOOM_HEADER_SIZE;
  matcher->bf.bit_size = *(uint32_t *)(map + offset);
  offset += sizeof(matcher->bf.bit_size);
  matcher->bf.bits = (uint64_t *)(map + offset);
  offset += hdr->bloom_filter_size;

  // 4. Hash table
  if (unlikely(memcmp(map + offset, HASH_HEADER, HASH_HEADER_SIZE) != 0)) {
    omega_matcher_unmap_file(map, size);
    return -1;
  }
  offset += HASH_HEADER_SIZE;

  // 4a. Index array
  matcher->index_array = (const uint32_t *)(map + offset);
  offset += hdr->table_size * sizeof(uint32_t);

  // 4b. Bucket data
  matcher->bucket_data = map + offset;
  offset += hdr->hash_buckets_size;

  // 5. Optional short matcher
  if (hdr->short_matcher_size > 0) {
    const uint8_t *sm_start = map + offset;
    if (unlikely(memcmp(sm_start, SHORT_MATCHER_MAGIC,
                        SHORT_MATCHER_MAGIC_SIZE) != 0)) {
      fputs("Short matcher magic mismatch\n", stderr);
      omega_matcher_unmap_file(map, size);
      return -1;
    }

    const uint8_t *p = sm_start + SHORT_MATCHER_MAGIC_SIZE; // +8
    memcpy(matcher->short_matcher.bitmap1, p, 32);
    p += 32;
    memcpy(matcher->short_matcher.bitmap2, p, 8192);
    p += 8192;

    // Safely read len3 and len4 (validate boundaries)
    if ((uintptr_t)(p + sizeof(uint32_t) * 2) - (uintptr_t)map > size) {
      omega_matcher_unmap_file(map, size);
      return -1;
    }
    matcher->short_matcher.len1 = *(const uint32_t *)p;
    p += sizeof(uint32_t);
    matcher->short_matcher.len2 = *(const uint32_t *)p;
    p += sizeof(uint32_t);
    matcher->short_matcher.len3 = *(const uint32_t *)p;
    p += sizeof(uint32_t);
    matcher->short_matcher.len4 = *(const uint32_t *)p;
    p += sizeof(uint32_t);

    if (matcher->short_matcher.len3 > 0) {
      matcher->short_matcher.arr3 = (uint32_t *)p;
      p += matcher->short_matcher.len3 * sizeof(uint32_t);
    } else {
      matcher->short_matcher.arr3 = NULL;
    }

    if (matcher->short_matcher.len4 > 0) {
      matcher->short_matcher.arr4 = (uint32_t *)p;
    } else {
      matcher->short_matcher.arr4 = NULL;
    }
  } else {
    matcher->short_matcher.len3 = 0;
    matcher->short_matcher.len4 = 0;
    matcher->short_matcher.arr3 = NULL;
    matcher->short_matcher.arr4 = NULL;
  }
  if (hdr->short_matcher_size + offset != size) {
    fputs("Short matcher size mismatch\n", stderr);
    omega_matcher_unmap_file(map, size);
    return -1;
  }

  return 0;
}

omega_list_matcher_t *omega_list_matcher_create_from_buffer(
    const char *restrict compiled_file, const uint8_t *restrict patterns_buffer,
    const uint64_t patterns_buffer_size, const int case_insensitive,
    const int ignore_punctuation, const int elide_whitespace,
    omega_match_pattern_store_stats_t *restrict stats) {
  return !patterns_buffer || patterns_buffer_size == 0 ||
                 omega_list_matcher_compile_patterns(
                     compiled_file, patterns_buffer, patterns_buffer_size,
                     case_insensitive, ignore_punctuation, elide_whitespace,
                     stats) != 0
             ? NULL
             : omega_list_matcher_create(compiled_file, case_insensitive,
                                         ignore_punctuation, elide_whitespace,
                                         stats);
}

// Create a matcher, compiling if needed
omega_list_matcher_t *omega_list_matcher_create(
    const char *restrict compiled_or_patterns_file, const int case_insensitive,
    const int ignore_punctuation, const int elide_whitespace,
    omega_match_pattern_store_stats_t *restrict stats) {
  const char *load_file = compiled_or_patterns_file;
  char *temp_path = NULL;

  if (!omega_list_matcher_is_compiled(compiled_or_patterns_file)) {
    char tmp[PATH_MAX] = {0};
#ifdef _WIN32
    if (GetTempFileNameA(".", "oa_matcher", 0, tmp) == 0) {
      return NULL;
    }
#else
    snprintf(tmp, PATH_MAX, "/tmp/oa_matcher_XXXXXX");
    const int fd = mkstemp(tmp);
    if (unlikely(fd < 0)) {
      perror("mkstemp");
      return NULL;
    }
    close(fd);
#endif
    if (omega_list_matcher_compile_patterns_filename(
            tmp, compiled_or_patterns_file, case_insensitive,
            ignore_punctuation, elide_whitespace, stats) != 0) {
      unlink(tmp);
      return NULL;
    }
    temp_path = strdup(tmp);
    load_file = temp_path;
  }

  omega_list_matcher_t *m = calloc(1, sizeof(omega_list_matcher_t));
  if (unlikely(!m)) {
    ABORT("omega_list_matcher_create: calloc");
  }

  m->temp_path = temp_path;
  m->case_insensitive = case_insensitive;
  m->ignore_punctuation = ignore_punctuation;

  if (unlikely(oa_matcher_load(load_file, m) != 0)) {
    omega_list_matcher_destroy(m);
    return NULL;
  }

  // Initialize transform table if needed
  if (m->header->flags &
      (FLAG_IGNORE_CASE | FLAG_IGNORE_PUNCTUATION | FLAG_ELIDE_WHITESPACE)) {
    m->transform_table = malloc(sizeof(transform_table_t));
    if (unlikely(transform_init(
                     m->transform_table, m->header->flags & FLAG_IGNORE_CASE,
                     m->header->flags & FLAG_IGNORE_PUNCTUATION,
                     m->header->flags & FLAG_ELIDE_WHITESPACE) != 0)) {
      ABORT("omega_list_matcher_create: transform_init");
    }
  }

  // Default OpenMP config
  omega_matcher_set_num_threads(m, 0);
  omega_matcher_set_chunk_size(m, 0);
  return m;
}

// Add match statistics to the matcher
int omega_list_matcher_add_stats(omega_list_matcher_t *restrict matcher,
                                 omega_match_stats_t *restrict stats) {
  if (unlikely(!matcher || !stats)) {
    ABORT("omega_list_matcher_add_stats: invalid arguments");
  }
  matcher->stats = stats;
  return 0;
}

// Destroy matcher and free resources
int omega_list_matcher_destroy(omega_list_matcher_t *restrict matcher) {
  if (unlikely(!matcher)) {
    ABORT("omega_list_matcher_destroy: invalid arguments");
  }
  if (matcher->mapped_file_base) {
    omega_matcher_unmap_file(matcher->mapped_file_base,
                             matcher->mapped_file_size);
  }
  if (matcher->temp_path) {
    unlink(matcher->temp_path);
    free(matcher->temp_path);
  }
  if (matcher->transform_table) {
    transform_free(matcher->transform_table);
    free(matcher->transform_table);
  }
  free(matcher);
  matcher = NULL;
  return 0;
}

// Strategy function type for filtering matches
typedef int (*match_filter_fn)(const omega_match_result_t *prev,
                               const omega_match_result_t *curr);

// Generic apply filter: keep matches where filter(prev, curr) is true
static void apply_filter(match_vector_t *restrict v,
                         const match_filter_fn filter) {
  size_t write = 0;
  for (size_t i = 0; i < v->count; ++i) {
    if (write == 0 || filter(&v->data[write - 1], &v->data[i])) {
      v->data[write++] = v->data[i];
    }
  }
  v->count = (uint32_t)write;
}

// Filter for longest-only: keep only the first occurrence per offset
OLM_ALWAYS_INLINE static int filter_longest(const omega_match_result_t *prev,
                                            const omega_match_result_t *curr) {
  return curr->offset != prev->offset;
}

// Filter for no-overlap: keep match if it doesn't overlap previous
OLM_ALWAYS_INLINE static int
filter_no_overlap(const omega_match_result_t *prev,
                  const omega_match_result_t *curr) {
  return (curr->offset >= (prev->offset + prev->len));
}

// Apply longest-only: keep only the longest match at each offset
OLM_ALWAYS_INLINE static void apply_longest(match_vector_t *restrict v) {
  apply_filter(v, filter_longest);
}

// Apply no-overlap: drop any match that overlaps the previous one
OLM_ALWAYS_INLINE static void apply_no_overlap(match_vector_t *restrict v) {
  apply_filter(v, filter_no_overlap);
}

// finalize helper merging thread-local vectors
static omega_match_results_t *
finalize_match_results(match_vector_t **restrict thread_matches,
                       const size_t num_chunks, const int no_overlap,
                       const int longest_only) {
  size_t total = 0;
  for (size_t i = 0; i < num_chunks; ++i) {
    total += thread_matches[i]->count;
  }
  match_vector_t *all = malloc(sizeof(match_vector_t));
  init_match_vector(all);
  reserve_match_vector(all, total);
  for (size_t i = 0; i < num_chunks; ++i) {
    match_vector_t *v = thread_matches[i];
    for (size_t j = 0; j < v->count; ++j) {
      append_match(all, &v->data[j]);
    }
    free_match_vector(v);
    free(v);
  }
  free(thread_matches);

  // qsort(all->data, all->count, sizeof(omega_match_result_t),
  // compare_matches);
  radix_sort_matches(all);
  if (longest_only) {
    apply_longest(all);
  }
  if (no_overlap) {
    apply_no_overlap(all);
  }

  omega_match_results_t *out = malloc(sizeof(omega_match_results_t));
  out->count = all->count;
  out->matches = all->data;
  free(all);
  return out;
}

static OLM_ALWAYS_INLINE int binary_search_uint32(const uint32_t *restrict arr,
                                                  const uint32_t count,
                                                  const uint32_t key) {
  int lo = 0, hi = (int)count - 1;
  while (lo <= hi) {
    const int mid = lo + ((hi - lo) >> 1);
    const uint32_t val = arr[mid];
    if (key < val) {
      hi = mid - 1;
    } else if (key > val) {
      lo = mid + 1;
    } else {
      // Found
      return 1;
    }
  }
  return 0;
}

static OLM_ALWAYS_INLINE int
short_matcher_query1(const short_matcher_t *restrict sm, const uint8_t b) {
  return sm->bitmap1[b >> 3] & (1 << (b & 7));
}

static OLM_ALWAYS_INLINE int
short_matcher_query2(const short_matcher_t *restrict sm,
                     const uint8_t *restrict ptr) {
  const uint16_t v = ((uint16_t)ptr[0] << 8) | ptr[1];
  return sm->bitmap2[v >> 3] & (1 << (v & 7));
}

static OLM_ALWAYS_INLINE int
short_matcher_query3(const short_matcher_t *restrict sm,
                     const uint8_t *restrict ptr) {
  if (sm->len3 == 0 || sm->arr3 == NULL) {
    return 0;
  }
  const uint32_t key =
      ((uint32_t)ptr[0] << 16) | ((uint32_t)ptr[1] << 8) | ptr[2];
  return binary_search_uint32(sm->arr3, sm->len3, key);
}

static OLM_ALWAYS_INLINE int short_matcher_query4(const short_matcher_t *sm,
                                                  const uint8_t *ptr) {
  if (sm->len4 == 0 || sm->arr4 == NULL) {
    return 0;
  }
  const uint32_t key = ((uint32_t)ptr[0] << 24) | ((uint32_t)ptr[1] << 16) |
                       ((uint32_t)ptr[2] << 8) | ptr[3];
  return binary_search_uint32(sm->arr4, sm->len4, key);
}

// Core case-sensitive matcher
static omega_match_results_t *
core_match(const omega_list_matcher_t *restrict matcher,
           const uint8_t *restrict haystack, const size_t haystack_size,
           const int no_overlap, const int longest_only,
           const int word_boundary, const int word_prefix,
           const int word_suffix, const int line_start, const int line_end) {
  // Runtime OpenMP config
  const int num_threads = (matcher->omp_num_threads <= 0)
                              ? omp_get_max_threads()
                              : matcher->omp_num_threads;
  omp_set_num_threads(num_threads);
#ifdef OMEGA_MATCH_USE_OPENMP
// Only call omp_set_schedule if it's available (OpenMP 3.0+)
#if _OPENMP >= 200805
  omp_set_schedule(omp_sched_static, matcher->omp_chunk_size > 0
                                         ? matcher->omp_chunk_size
                                         : 4096);
#endif
#endif

  // Statistic counters
  uint64_t total_attempts = 0;
  uint64_t total_hits = 0;
  uint64_t total_misses = 0;
  uint64_t total_filtered = 0;
  uint64_t total_comparisons = 0;

  const int max_threads = omp_get_max_threads();
  match_vector_t **thread_matches =
      calloc(num_threads, sizeof(match_vector_t *));
  if (unlikely(!thread_matches)) {
    ABORT("calloc thread_matches"); // OOM
  }

  // Hoist matcher fields
  const uint32_t table_mask = matcher->header->table_size - 1;
  const uint32_t *idx_arr = matcher->index_array;
  const uint8_t *bucket = matcher->bucket_data;
  const uint8_t *pat_st = matcher->pattern_store;
  const bloom_filter_t *bf = &matcher->bf;
  const short_matcher_t *sm = &matcher->short_matcher;
  const uint32_t smallest = matcher->header->smallest_pattern_length;
  const uint32_t largest = matcher->header->largest_pattern_length;

  const bool use_sm = smallest <= 4;
  const bool use_sm1 = sm->len1 > 0;
  const bool use_sm2 = sm->len2 > 0;
  const bool use_sm3 = sm->len3 > 0;
  const bool use_sm4 = sm->len4 > 0;

#ifdef OMEGA_MATCH_USE_OPENMP
#pragma omp parallel reduction(+ : total_attempts, total_hits, total_misses,   \
                                   total_filtered, total_comparisons)
#endif
  {
    const int tid =
#ifdef OMEGA_MATCH_USE_OPENMP
        omp_get_thread_num();
#else
        0;
#endif
    match_vector_t *local = malloc(sizeof(*local));
    init_match_vector(local);
    thread_matches[tid] = local;
    const ptrdiff_t hsize = (ptrdiff_t)haystack_size;

    ptrdiff_t pos;
#ifdef OMEGA_MATCH_USE_OPENMP
#pragma omp for schedule(runtime)
#endif
    for (pos = 0; pos < hsize; ++pos) {
      // Word boundary logic (only for scan start, not for prefix/suffix)
      if (word_boundary && IS_WORD(haystack[pos]) ==
                               (pos > 0 ? IS_WORD(haystack[pos - 1]) : 0)) {
        continue;
      }

      const uint8_t *h_ptr = haystack + pos;

      // Hash table for patterns ≥ 5
      if (largest >= 5 && pos + 4 <= hsize) {
        ++total_attempts;
        const uint32_t cand = pack_gram(h_ptr);
        OLM_PREFETCH(&bf->bits[(cand >> 6) & ((bf->bit_size / 64) - 1)]);
        if (!bloom_filter_query(bf, cand)) {
          ++total_filtered;
        } else {
          uint32_t slot_offset;
          if (!probe_bucket(idx_arr, bucket, table_mask, cand, &slot_offset)) {
            ++total_misses;
          } else {
            ++total_hits;
            scan_bucket_and_append(bucket + slot_offset, pat_st, local,
                                   haystack, (size_t)hsize, pos, word_boundary,
                                   word_prefix, word_suffix, line_start,
                                   line_end, &total_comparisons);
          }
        }
      }

      // Short matcher for patterns of length 1–4
      if (use_sm) {
        if (use_sm4 && pos + 4 <= hsize && short_matcher_query4(sm, h_ptr)) {
          int prefix_ok =
              !word_prefix || (pos == 0 || !IS_WORD(haystack[pos - 1]));
          int suffix_ok =
              !word_suffix || (pos + 4 == hsize || !IS_WORD(haystack[pos + 4]));
          int line_start_ok = !line_start || is_at_line_start(haystack, pos);
          int line_end_ok =
              !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 4);
          if ((!word_boundary ||
               (pos + 4 >= hsize || !IS_WORD(haystack[pos + 4]))) &&
              prefix_ok && suffix_ok && line_start_ok && line_end_ok) {
            ++total_hits;
            append_match(local, &(omega_match_result_t){
                                    .offset = pos, .len = 4, .match = h_ptr});
          } else {
            ++total_misses;
          }
        }
        if (use_sm3 && pos + 3 <= hsize && short_matcher_query3(sm, h_ptr)) {
          int prefix_ok =
              !word_prefix || (pos == 0 || !IS_WORD(haystack[pos - 1]));
          int suffix_ok =
              !word_suffix || (pos + 3 == hsize || !IS_WORD(haystack[pos + 3]));
          int line_start_ok = !line_start || is_at_line_start(haystack, pos);
          int line_end_ok =
              !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 3);
          if ((!word_boundary ||
               (pos + 3 >= hsize || !IS_WORD(haystack[pos + 3]))) &&
              prefix_ok && suffix_ok && line_start_ok && line_end_ok) {
            ++total_hits;
            append_match(local, &(omega_match_result_t){
                                    .offset = pos, .len = 3, .match = h_ptr});
          } else {
            ++total_misses;
          }
        }
        if (use_sm2 && pos + 2 <= hsize && short_matcher_query2(sm, h_ptr)) {
          int prefix_ok =
              !word_prefix || (pos == 0 || !IS_WORD(haystack[pos - 1]));
          int suffix_ok =
              !word_suffix || (pos + 2 == hsize || !IS_WORD(haystack[pos + 2]));
          if ((!word_boundary ||
               (pos + 2 >= hsize || !IS_WORD(haystack[pos + 2]))) &&
              prefix_ok && suffix_ok) {
            ++total_hits;
            append_match(local, &(omega_match_result_t){
                                    .offset = pos, .len = 2, .match = h_ptr});
          } else {
            ++total_misses;
          }
        }
        if (use_sm1 && short_matcher_query1(sm, *h_ptr)) {
          int prefix_ok =
              !word_prefix || (pos == 0 || !IS_WORD(haystack[pos - 1]));
          int suffix_ok =
              !word_suffix || (pos + 1 == hsize || !IS_WORD(haystack[pos + 1]));
          if ((!word_boundary ||
               (pos + 1 >= hsize || !IS_WORD(haystack[pos + 1]))) &&
              prefix_ok && suffix_ok) {
            ++total_hits;
            append_match(local, &(omega_match_result_t){
                                    .offset = pos, .len = 1, .match = h_ptr});
          } else {
            ++total_misses;
          }
        }
      }
    }
  }

  omega_match_results_t *results = finalize_match_results(
      thread_matches, max_threads, no_overlap, longest_only);

  if (matcher->stats) {
    matcher->stats->total_attempts += total_attempts;
    matcher->stats->total_hits += total_hits;
    matcher->stats->total_misses += total_misses;
    matcher->stats->total_filtered += total_filtered;
    matcher->stats->total_comparisons += total_comparisons;
  }
  return results;
}

// Normalize whitespace and optionally remove punctuation, producing a remapped
// haystack and backmap. This function reduces all whitespace runs to a single
// space, optionally strips punctuation, and builds a map from normalized
// indices back to the original input positions.
//
// Returns the length of the normalized haystack.
size_t normalize_haystack(const uint8_t *restrict input, size_t len,
                          uint8_t *restrict output, size_t *restrict backmap,
                          int ignore_punct, int elide_whitespace) {
  size_t out_pos = 0;
  bool in_space = false;

  for (size_t i = 0; i < len; ++i) {
    uint8_t c = input[i];

    if (ignore_punct && IS_PUNCT(c)) {
      continue;
    }

    if (elide_whitespace && IS_SPACE(c)) {
      if (!in_space) {
        output[out_pos] = ' ';
        backmap[out_pos++] = i;
        in_space = true;
      }
      continue;
    }

    output[out_pos] = c;
    backmap[out_pos++] = i;
    in_space = false;
  }

  return out_pos;
}

// Case-insensitive wrapper using sliding uppercase
omega_match_results_t *omega_list_matcher_match(
    const omega_list_matcher_t *matcher, const uint8_t *haystack,
    const size_t haystack_size, const int no_overlap, const int longest_only,
    const int word_boundary, const int word_prefix, const int word_suffix,
    const int line_start, const int line_end) {
  if (!matcher->transform_table) {
    return core_match(matcher, haystack, haystack_size, no_overlap,
                      longest_only, word_boundary, word_prefix, word_suffix,
                      line_start, line_end);
  }

  const size_t max_pat = matcher->header->largest_pattern_length;
  const size_t chunk_size = CASE_INSENSITIVE_WINDOW_SIZE;
  const size_t num_chunks = (haystack_size + chunk_size - 1) / chunk_size;

  uint8_t *buf = malloc(chunk_size + max_pat);
  if (unlikely(!buf)) {
    ABORT("malloc for buf"); // OOM
  }
  size_t *position_map = NULL;
  if (matcher->header->flags & FLAG_IGNORE_PUNCTUATION ||
      matcher->header->flags & FLAG_ELIDE_WHITESPACE) {
    position_map = malloc((chunk_size + max_pat) * sizeof(size_t));
    if (unlikely(!position_map)) {
      ABORT("malloc for position_map"); // OOM
    }
  }

  match_vector_t **chunk_vectors = calloc(num_chunks, sizeof(match_vector_t *));
  if (unlikely(!chunk_vectors)) {
    ABORT("calloc chunk_vectors"); // OOM
  }

  for (size_t chunk_idx = 0; chunk_idx < num_chunks; ++chunk_idx) {
    const size_t base = chunk_idx * chunk_size;
    const size_t rem = haystack_size - base;
    const size_t win = rem < chunk_size ? rem : chunk_size;

    uint32_t processed_len = 0;
    const uint8_t *normalized =
        transform_apply(matcher->transform_table, haystack + base,
                        (uint32_t)win, &processed_len, position_map);

    omega_match_results_t *r = core_match(
        matcher, normalized, processed_len, no_overlap, longest_only,
        word_boundary, word_prefix, word_suffix, line_start, line_end);
    if (unlikely(!r)) {
      ABORT("core_match failed"); // OOM
    }
    match_vector_t *local = calloc(1, sizeof(*local));
    reserve_match_vector(local, r->count);

    if (position_map) {
      // Remap the offsets back to the original haystack
      for (size_t i = 0; i < r->count; ++i) {
        omega_match_result_t *m = &r->matches[i];
        // Map cleaned offset back to the original haystack
        const size_t original_offset = base + position_map[m->offset];
        const size_t original_end = base + position_map[m->offset + m->len - 1];
        m->offset = original_offset;
        m->len = (uint32_t)(original_end - original_offset + 1);
        m->match = haystack + m->offset;
        append_match(local, m);
      }
    } else {
      // 1-to-1 mapping from normalized to original haystack
      for (size_t i = 0; i < r->count; ++i) {
        omega_match_result_t *m = &r->matches[i];
        m->offset += base;
        m->match = haystack + m->offset;
        append_match(local, m);
      }
    }

    omega_match_results_destroy(r);
    chunk_vectors[chunk_idx] = local;
  }

  free(buf);
  if (position_map) {
    free(position_map);
  }

  return finalize_match_results(chunk_vectors, num_chunks, no_overlap,
                                longest_only);
}

// Free results array
void omega_match_results_destroy(omega_match_results_t *restrict results) {
  free(results->matches);
  results->matches = NULL;
  results->count = 0;
  free(results);
  results = NULL;
}
