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
  const uint8_t *control_bytes; // optional control-byte fingerprint array (v2+); NULL for v1 format files (backward compatibility)
  const uint32_t *index_array;
  const uint8_t *bucket_data;
  int case_insensitive;
  int ignore_punctuation;
  int has_keys; // non-zero if compiled with FLAG_HAS_KEYS
  omega_match_stats_t *stats;
  char *temp_path; // non-NULL if compiled on the fly
  transform_table_t *transform_table;
  const uint8_t *short_matcher_base;
  short_matcher_t short_matcher;
  // Two-byte prefix filters avoid binary-searching the 3/4-byte pattern
  // arrays at positions that cannot possibly match.
  uint8_t short_prefix3[8192];
  uint8_t short_prefix4[8192];
  // Short matcher key arrays (offsets into short_matcher_base when has_keys)
  uint32_t sm_keys1_offset;    // 256 packed uint64_t entries for 1-byte patterns
  const uint32_t *sm_vals2;    // sorted 2-byte values for key lookup
  uint32_t sm_keys2_offset;    // packed uint64_t array parallel to sm_vals2
  uint32_t sm_len2_keyed;      // number of 2-byte keyed entries
  uint32_t sm_keys3_offset;    // packed uint64_t array parallel to arr3
  uint32_t sm_keys4_offset;    // packed uint64_t array parallel to arr4
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

static OLM_ALWAYS_INLINE uint32_t load_u32_unaligned(
    const uint8_t *restrict ptr) {
  uint32_t value;
  memcpy(&value, ptr, sizeof(value));
  return value;
}

static OLM_ALWAYS_INLINE uint64_t load_u64_unaligned(
    const uint8_t *restrict ptr) {
  uint64_t value;
  memcpy(&value, ptr, sizeof(value));
  return value;
}

static OLM_ALWAYS_INLINE int file_span_in_bounds(
    const uint8_t *restrict base, size_t size, const uint8_t *restrict ptr,
    size_t span) {
  if (ptr < base) {
    return 0;
  }
  const size_t offset = (size_t)(ptr - base);
  return offset <= size && span <= size - offset;
}

// Scan through the bucket's patterns and append exact matches.
static uint64_t scan_bucket_and_append(
    const uint8_t *restrict bucket_ptr, const uint8_t *restrict pat_store,
    match_vector_t *restrict local, const uint8_t *restrict haystack,
    const size_t haystack_size, const size_t pos, const int word_boundary,
    const int word_prefix, const int word_suffix, const int line_start,
    const int line_end, const int has_keys, uint64_t *restrict compares) {
  uint64_t matches = 0;
  const uint32_t num_patterns = *(const uint32_t *)(bucket_ptr + 4);
  const uint8_t *pattern_ptr = bucket_ptr + 8;
  // User keys follow the pattern array when has_keys is set
  const uint8_t *user_keys =
      has_keys ? (pattern_ptr + num_patterns * sizeof(pattern_t)) : NULL;
  const uint8_t *hay_pos = haystack + pos;
  const size_t remaining = haystack_size - pos;
  
  // Pre-compute word boundary checks for position
  const bool pos_at_word_start = !word_prefix || (pos == 0 || !IS_WORD(haystack[pos - 1]));
  const bool pos_at_line_start = !line_start || is_at_line_start(haystack, pos);
  
  for (uint32_t j = 0; j < num_patterns; ++j) {
    const pattern_t *pat = (const pattern_t *)pattern_ptr;
    const uint32_t len = pat->len;
  // Prefetch next pattern header to hide latency
  OLM_PREFETCH(pattern_ptr + sizeof(pattern_t));
    
    // Early exit if pattern doesn't fit
    if (unlikely(len > remaining)) {
      pattern_ptr += sizeof(pattern_t);
      continue;
    }
    
    const size_t offset = pat->offset;
    pattern_ptr += sizeof(pattern_t);
    ++(*compares);
    
  // Prefetch a small window ahead in the haystack to reduce misses
  OLM_PREFETCH(hay_pos + 16);
    // Optimized comparison: check first/last bytes before full memcmp
    const uint8_t *pattern_data = pat_store + offset;
    
    // Fast path for single character patterns
    if (len == 1) {
      if (hay_pos[0] != pattern_data[0]) continue;
    } else {
      // Multi-character pattern: check first and last bytes first
      if (hay_pos[0] != pattern_data[0] || hay_pos[len-1] != pattern_data[len-1]) {
        continue;
      }
      // Only do memcmp if length > 2 and first/last bytes match
      if (len > 2 && memcmp(hay_pos + 1, pattern_data + 1, len - 2) != 0) {
        continue;
      }
    }
    
    // Pattern matches, now check filters
    const size_t match_end = pos + len;
    
    // Word boundary checks (optimized with pre-computed values)
    if (word_boundary && match_end < haystack_size && IS_WORD(haystack[match_end])) {
      continue;
    }
    if (!pos_at_word_start) {
      continue;
    }
    if (word_suffix && match_end < haystack_size && IS_WORD(haystack[match_end])) {
      continue;
    }
    
    // Line checks
    if (!pos_at_line_start) {
      continue;
    }
    if (line_end && !is_at_line_end(haystack, haystack_size, pos, len)) {
      continue;
    }
    
    const uint64_t ukey =
        user_keys ? load_u64_unaligned(user_keys + (j * sizeof(uint64_t))) : 0;
    append_match(local, &(omega_match_result_t){
        .offset = pos, .len = len, ._reserved = 0,
        .match = haystack + pos, .key = ukey});
    ++matches;
  }
  return matches;
}

/*-------------------------------------------------------------*/

static int oa_matcher_load(const char *path, omega_list_matcher_t *matcher) {
  size_t size;
  uint8_t *map = omega_matcher_map_filename(path, &size, 0);
  if (unlikely(!map)) {
    return -1;
  }
#define LOAD_FAIL()                                                            \
  do {                                                                         \
    omega_matcher_unmap_file(map, size);                                       \
    return -1;                                                                 \
  } while (0)

  if (unlikely(size < sizeof(compiled_header_t))) {
    LOAD_FAIL();
  }

  // Needed to unmap the file later
  matcher->mapped_file_base = map;
  matcher->mapped_file_size = size;

  // 1. Map the header
  compiled_header_t *hdr = (compiled_header_t *)map;
  if (unlikely(memcmp(hdr->magic, HEADER_MAGIC, HEADER_MAGIC_SIZE) != 0)) {
    LOAD_FAIL();
  }
  if (unlikely(hdr->version > VERSION)) {
    LOAD_FAIL();
  }
  matcher->header = hdr;

  size_t offset = sizeof(compiled_header_t);

  // 2. Pattern store
  if (unlikely(hdr->pattern_store_size > size - offset)) {
    LOAD_FAIL();
  }
  matcher->pattern_store = map + offset;
  offset += hdr->pattern_store_size;

  // 3. Bloom filter
  if (unlikely(!file_span_in_bounds(map, size, map + offset,
                                    BLOOM_HEADER_SIZE + sizeof(uint32_t)))) {
    LOAD_FAIL();
  }
  if (unlikely(memcmp(map + offset, BLOOM_HEADER, BLOOM_HEADER_SIZE) != 0)) {
    LOAD_FAIL();
  }
  offset += BLOOM_HEADER_SIZE;
  matcher->bf.bit_size = load_u32_unaligned(map + offset);
  offset += sizeof(matcher->bf.bit_size);
  if (hdr->version >= 4) {
    if (unlikely(
            !file_span_in_bounds(map, size, map + offset, sizeof(uint32_t)))) {
      LOAD_FAIL();
    }
    offset += sizeof(uint32_t); // reserved alignment word
  }
  if (unlikely(hdr->bloom_filter_size > size - offset)) {
    LOAD_FAIL();
  }
  if (unlikely(hdr->version >= 4 && ((uintptr_t)(map + offset) & 7u) != 0)) {
    LOAD_FAIL();
  }
  matcher->bf.bits = (uint64_t *)(map + offset);
  offset += hdr->bloom_filter_size;

  // 4. Hash table
  if (unlikely(!file_span_in_bounds(map, size, map + offset, HASH_HEADER_SIZE))) {
    LOAD_FAIL();
  }
  if (unlikely(memcmp(map + offset, HASH_HEADER, HASH_HEADER_SIZE) != 0)) {
    LOAD_FAIL();
  }
  offset += HASH_HEADER_SIZE;

  // Set has_keys from header flags
  matcher->has_keys = (hdr->flags & FLAG_HAS_KEYS) ? 1 : 0;

  // For version >= 2, a control-byte array (table_size bytes) precedes index array
  if (hdr->version >= 2) {
    if (unlikely(hdr->table_size > size - offset)) {
      LOAD_FAIL();
    }
    matcher->control_bytes = (const uint8_t *)(map + offset);
    offset += hdr->table_size * sizeof(uint8_t);
  } else {
    matcher->control_bytes = NULL;
  }

  // 4a. Index array
  if (unlikely(hdr->table_size > (size - offset) / sizeof(uint32_t))) {
    LOAD_FAIL();
  }
  matcher->index_array = (const uint32_t *)(map + offset);
  offset += hdr->table_size * sizeof(uint32_t);

  // 4b. Bucket data
  if (unlikely(hdr->hash_buckets_size > size - offset)) {
    LOAD_FAIL();
  }
  matcher->bucket_data = map + offset;
  offset += hdr->hash_buckets_size;

  // 5. Optional short matcher
  if (hdr->short_matcher_size > 0) {
    if (unlikely(hdr->short_matcher_size > size - offset)) {
      LOAD_FAIL();
    }
    const uint8_t *sm_start = map + offset;
    matcher->short_matcher_base = sm_start;
    if (unlikely(memcmp(sm_start, SHORT_MATCHER_MAGIC,
                        SHORT_MATCHER_MAGIC_SIZE) != 0)) {
      fputs("Short matcher magic mismatch\n", stderr);
      LOAD_FAIL();
    }

    const uint8_t *p = sm_start + SHORT_MATCHER_MAGIC_SIZE; // +8
    if (unlikely(!file_span_in_bounds(map, size, p, 32 + 8192 + (4 * sizeof(uint32_t))))) {
      LOAD_FAIL();
    }
    memcpy(matcher->short_matcher.bitmap1, p, 32);
    p += 32;
    memcpy(matcher->short_matcher.bitmap2, p, 8192);
    p += 8192;

    matcher->short_matcher.len1 = load_u32_unaligned(p);
    p += sizeof(uint32_t);
    matcher->short_matcher.len2 = load_u32_unaligned(p);
    p += sizeof(uint32_t);
    matcher->short_matcher.len3 = load_u32_unaligned(p);
    p += sizeof(uint32_t);
    matcher->short_matcher.len4 = load_u32_unaligned(p);
    p += sizeof(uint32_t);

    if (matcher->short_matcher.len3 > 0) {
      if (unlikely(!file_span_in_bounds(map, size, p,
                                        matcher->short_matcher.len3 *
                                            sizeof(uint32_t)))) {
        LOAD_FAIL();
      }
      matcher->short_matcher.arr3 = (uint32_t *)p;
      p += matcher->short_matcher.len3 * sizeof(uint32_t);
    } else {
      matcher->short_matcher.arr3 = NULL;
    }

    if (matcher->short_matcher.len4 > 0) {
      if (unlikely(!file_span_in_bounds(map, size, p,
                                        matcher->short_matcher.len4 *
                                            sizeof(uint32_t)))) {
        LOAD_FAIL();
      }
      matcher->short_matcher.arr4 = (uint32_t *)p;
      p += matcher->short_matcher.len4 * sizeof(uint32_t);
    } else {
      matcher->short_matcher.arr4 = NULL;
    }

    for (uint32_t i = 0; i < matcher->short_matcher.len3; ++i) {
      const uint32_t prefix = matcher->short_matcher.arr3[i] >> 8;
      matcher->short_prefix3[prefix >> 3] |= (uint8_t)(1u << (prefix & 7));
    }
    for (uint32_t i = 0; i < matcher->short_matcher.len4; ++i) {
      const uint32_t prefix = matcher->short_matcher.arr4[i] >> 16;
      matcher->short_prefix4[prefix >> 3] |= (uint8_t)(1u << (prefix & 7));
    }

    // Read short matcher key arrays (version >= 3 with FLAG_HAS_KEYS)
    if (matcher->has_keys) {
      if (hdr->version >= 4) {
        const size_t relative = (size_t)(p - sm_start);
        const size_t padding = (8 - (relative & 7u)) & 7u;
        if (unlikely(!file_span_in_bounds(map, size, p, padding))) {
          LOAD_FAIL();
        }
        p += padding;
      }
      // 1-byte keys: 256 entries
      if (unlikely(!file_span_in_bounds(map, size, p, 256 * sizeof(uint64_t)))) {
        LOAD_FAIL();
      }
      matcher->sm_keys1_offset = (uint32_t)(p - sm_start);
      p += 256 * sizeof(uint64_t);
      // 2-byte keys: sparse sorted array
      if (unlikely(!file_span_in_bounds(map, size, p, sizeof(uint32_t)))) {
        LOAD_FAIL();
      }
      matcher->sm_len2_keyed = load_u32_unaligned(p);
      p += sizeof(uint32_t);
      if (matcher->sm_len2_keyed > 0) {
        if (unlikely(!file_span_in_bounds(map, size, p,
                                          matcher->sm_len2_keyed *
                                              sizeof(uint32_t)))) {
          LOAD_FAIL();
        }
        matcher->sm_vals2 = (const uint32_t *)p;
        p += matcher->sm_len2_keyed * sizeof(uint32_t);
      } else {
        matcher->sm_vals2 = NULL;
      }
      if (hdr->version >= 4) {
        const size_t relative = (size_t)(p - sm_start);
        const size_t padding = (8 - (relative & 7u)) & 7u;
        if (unlikely(!file_span_in_bounds(map, size, p, padding))) {
          LOAD_FAIL();
        }
        p += padding;
      }
      if (matcher->sm_len2_keyed > 0) {
        if (unlikely(!file_span_in_bounds(map, size, p,
                                          matcher->sm_len2_keyed *
                                              sizeof(uint64_t)))) {
          LOAD_FAIL();
        }
        matcher->sm_keys2_offset = (uint32_t)(p - sm_start);
        p += matcher->sm_len2_keyed * sizeof(uint64_t);
      } else {
        matcher->sm_keys2_offset = 0;
      }
      // 3-byte keys: parallel to arr3
      if (matcher->short_matcher.len3 > 0) {
        if (unlikely(!file_span_in_bounds(map, size, p,
                                          matcher->short_matcher.len3 *
                                              sizeof(uint64_t)))) {
          LOAD_FAIL();
        }
        matcher->sm_keys3_offset = (uint32_t)(p - sm_start);
        p += matcher->short_matcher.len3 * sizeof(uint64_t);
      } else {
        matcher->sm_keys3_offset = 0;
      }
      // 4-byte keys: parallel to arr4
      if (matcher->short_matcher.len4 > 0) {
        if (unlikely(!file_span_in_bounds(map, size, p,
                                          matcher->short_matcher.len4 *
                                              sizeof(uint64_t)))) {
          LOAD_FAIL();
        }
        matcher->sm_keys4_offset = (uint32_t)(p - sm_start);
        p += matcher->short_matcher.len4 * sizeof(uint64_t);
      } else {
        matcher->sm_keys4_offset = 0;
      }
    } else {
      matcher->sm_keys1_offset = 0;
      matcher->sm_vals2 = NULL;
      matcher->sm_keys2_offset = 0;
      matcher->sm_len2_keyed = 0;
      matcher->sm_keys3_offset = 0;
      matcher->sm_keys4_offset = 0;
    }
  } else {
    matcher->short_matcher_base = NULL;
    matcher->short_matcher.len3 = 0;
    matcher->short_matcher.len4 = 0;
    matcher->short_matcher.arr3 = NULL;
    matcher->short_matcher.arr4 = NULL;
    matcher->sm_keys1_offset = 0;
    matcher->sm_vals2 = NULL;
    matcher->sm_keys2_offset = 0;
    matcher->sm_len2_keyed = 0;
    matcher->sm_keys3_offset = 0;
    matcher->sm_keys4_offset = 0;
  }
  if (hdr->short_matcher_size + offset != size) {
    fputs("Short matcher size mismatch\n", stderr);
    LOAD_FAIL();
  }

#undef LOAD_FAIL
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

// Removed legacy post-merge filter helpers (now handled during k-way merge)

// finalize helper merging thread-local vectors
// Run descriptor used by k-way merge and its comparator
typedef struct { const omega_match_result_t *arr; size_t len; size_t idx; } run_t;
OLM_ALWAYS_INLINE static int cmp_run(size_t a, size_t b, const run_t *restrict runs) {
  const omega_match_result_t *ra = &runs[a].arr[runs[a].idx];
  const omega_match_result_t *rb = &runs[b].arr[runs[b].idx];
  if (ra->offset != rb->offset) return (ra->offset < rb->offset) ? -1 : 1;
  if (ra->len == rb->len) return 0;
  return (ra->len > rb->len) ? -1 : 1; // longer first when offsets equal
}

// Helper function to perform sift-down on a heap
OLM_ALWAYS_INLINE static void sift_down(size_t *heap, size_t n, size_t start, const run_t *runs) {
  size_t idx = start;
  for (;;) {
    size_t l = 2 * idx + 1, r = l + 1, smallest = idx;
    if (l < n && cmp_run(heap[l], heap[smallest], runs) < 0) smallest = l;
    if (r < n && cmp_run(heap[r], heap[smallest], runs) < 0) smallest = r;
    if (smallest == idx) break;
    size_t tmp = heap[idx];
    heap[idx] = heap[smallest];
    heap[smallest] = tmp;
    idx = smallest;
  }
}

// finalize helper merging thread-local vectors
static omega_match_results_t *
finalize_match_results(match_vector_t **restrict thread_matches,
                       const size_t num_chunks, const int no_overlap,
                       const int longest_only) {
  // Compute total to preallocate output buffer
  size_t total = 0;
  for (size_t i = 0; i < num_chunks; ++i) {
    total += thread_matches[i]->count;
  }

  // K-way merge state: one cursor per chunk
  run_t *runs = (run_t *)malloc(num_chunks * sizeof(run_t));
  if (unlikely(!runs)) {
    ABORT("finalize_match_results: malloc runs");
  }
  size_t active = 0;
  match_vector_t *single = NULL; // the only non-empty vector when active == 1
  for (size_t i = 0; i < num_chunks; ++i) {
    match_vector_t *v = thread_matches[i];
    if (v->count > 0) {
      runs[active].arr = v->data;
      runs[active].len = v->count;
      runs[active].idx = 0;
      single = v;
      ++active;
    }
  }

  // Min-heap over runs by (offset asc, len desc)
  // Heap stores indices into runs[0..active)
  if (active == 0) {
    // Free inputs and return empty result
    for (size_t i = 0; i < num_chunks; ++i) {
      free_match_vector(thread_matches[i]);
      free(thread_matches[i]);
    }
    free(thread_matches);
    free(runs);
    omega_match_results_t *out = (omega_match_results_t *)malloc(sizeof(*out));
    if (unlikely(!out)) {
      ABORT("finalize_match_results: malloc results");
    }
    out->count = 0;
    out->matches = NULL;
    return out;
  }

  if (active == 1) {
    // Single sorted run: no merge needed. Apply the on-merge filters in place
    // and hand the run's buffer to the caller without copying.
    size_t kept = single->count;
    if (no_overlap || longest_only) {
      omega_match_result_t *arr = single->data;
      uint64_t last_offset = (uint64_t)-1;
      uint64_t last_end = 0;
      size_t w = 0;
      for (size_t i = 0; i < single->count; ++i) {
        const omega_match_result_t cur = arr[i];
        if (longest_only && cur.offset == last_offset) {
          continue; // already emitted longest at this offset
        }
        if (no_overlap && cur.offset < last_end) {
          continue;
        }
        arr[w++] = cur;
        last_offset = cur.offset;
        if (no_overlap) {
          const uint64_t end = cur.offset + cur.len;
          if (end > last_end) {
            last_end = end;
          }
        }
      }
      kept = w;
    }
    omega_match_results_t *out = (omega_match_results_t *)malloc(sizeof(*out));
    if (unlikely(!out)) {
      ABORT("finalize_match_results: malloc results");
    }
    out->count = kept;
    out->matches = single->data;
    single->data = NULL; // ownership transferred to the results
    for (size_t i = 0; i < num_chunks; ++i) {
      free_match_vector(thread_matches[i]);
      free(thread_matches[i]);
    }
    free(thread_matches);
    free(runs);
    return out;
  }

  // Prepare output vector
  match_vector_t merged;
  init_match_vector(&merged);
  reserve_match_vector(&merged, total);

  size_t *heap = (size_t *)malloc(active * sizeof(size_t));
  if (unlikely(!heap)) {
    ABORT("finalize_match_results: malloc heap");
  }

  // Comparison helper defined at file scope: cmp_run

  // Heapify
  for (size_t i = 0; i < active; ++i) heap[i] = i;
  for (ptrdiff_t i = (ptrdiff_t)active / 2 - 1; i >= 0; --i) {
    // Sift-down from i
    size_t start = (size_t)i;
    sift_down(heap, active, start, runs);
  }

  // On-merge filtering state
  uint64_t last_offset = (uint64_t)-1;
  uint64_t last_end = 0;

  // Merge loop
  while (active > 0) {
    // Pop min
    size_t top = heap[0];
    const omega_match_result_t *cur = &runs[top].arr[runs[top].idx];

    // Apply on-merge filters in offset-asc, len-desc stream
    int keep = 1;
    if (longest_only && cur->offset == last_offset) {
      keep = 0; // already emitted longest at this offset
    }
    if (keep && no_overlap && cur->offset < last_end) {
      keep = 0;
    }
    if (keep) {
      append_match(&merged, cur);
      last_offset = cur->offset;
      if (no_overlap) {
        uint64_t end = cur->offset + cur->len;
        if (end > last_end) last_end = end;
      }
    }

    // Advance run
    runs[top].idx++;
    if (runs[top].idx >= runs[top].len) {
      // Remove from heap
      heap[0] = heap[active - 1];
      --active;
    } else {
      // Restore heap property at root only
  // Advance handled; restore heap property below via sift-down
    }
    if (active > 0) {
      // Place root properly using sift-down
      sift_down(heap, active, 0, runs);
    }
  }

  // Free inputs
  for (size_t i = 0; i < num_chunks; ++i) {
    free_match_vector(thread_matches[i]);
    free(thread_matches[i]);
  }
  free(thread_matches);
  free(heap);
  free(runs);

  // Produce results
  omega_match_results_t *out = (omega_match_results_t *)malloc(sizeof(*out));
  out->count = merged.count;
  out->matches = merged.data;
  return out;
}

static OLM_ALWAYS_INLINE int binary_search_uint32_optimized(
    const uint32_t *restrict arr, const uint32_t count, const uint32_t key) {
  // Early exit for small arrays
  // If the array is empty, there is no match.
  if (unlikely(count == 0)) return 0;
  
  // If the array has only one element, directly compare it to the key.
  if (unlikely(count == 1)) return arr[0] == key;
  
  // Fast path for very small arrays (2-4 elements)
  // For arrays with 2-4 elements, use bitwise OR to check all elements in a single pass.
  // This avoids the overhead of a loop and improves performance for small arrays.
  if (count <= 4) {
    if (count == 2) {
      return (arr[0] == key) | (arr[1] == key);
    }
    if (count == 3) {
      return (arr[0] == key) | (arr[1] == key) | (arr[2] == key);
    }
    // count == 4
    return (arr[0] == key) | (arr[1] == key) | (arr[2] == key) | (arr[3] == key);
  }
  
  // Binary search with fewer branches for larger arrays
  uint32_t lo = 0, hi = count;
  while (lo < hi) {
    const uint32_t mid = lo + ((hi - lo) >> 1);
    const uint32_t val = arr[mid];
    if (key < val) {
      hi = mid;
    } else if (key > val) {
      lo = mid + 1;
    } else {
      return 1; // Found
    }
  }
  return 0;
}

// Binary search for 2-byte key lookup in sorted sparse array
static OLM_ALWAYS_INLINE uint64_t
sm_lookup_key2(const uint32_t *restrict vals, const uint8_t *restrict keys,
               uint32_t count, uint32_t target) {
  if (!vals || count == 0) return 0;
  uint32_t lo = 0, hi = count;
  while (lo < hi) {
    const uint32_t mid = lo + ((hi - lo) >> 1);
    if (vals[mid] == target) {
      return load_u64_unaligned(keys + (mid * sizeof(uint64_t)));
    }
    if (vals[mid] < target) lo = mid + 1; else hi = mid;
  }
  return 0;
}

// Binary search for 3/4-byte key lookup in sorted array (returns index or -1)
static OLM_ALWAYS_INLINE int
sm_find_index(const uint32_t *restrict arr, uint32_t count, uint32_t target) {
  uint32_t lo = 0, hi = count;
  while (lo < hi) {
    const uint32_t mid = lo + ((hi - lo) >> 1);
    if (arr[mid] == target) return (int)mid;
    if (arr[mid] < target) lo = mid + 1; else hi = mid;
  }
  return -1;
}

// --

// Optimized short matcher queries with better branch prediction
static OLM_ALWAYS_INLINE int
short_matcher_query1_fast(const short_matcher_t *restrict sm, const uint8_t b) {
  return sm->bitmap1[b >> 3] & (1 << (b & 7));
}

static OLM_ALWAYS_INLINE int
short_matcher_query2_fast(const short_matcher_t *restrict sm,
                         const uint8_t *restrict ptr) {
  const uint16_t v = ((uint16_t)ptr[0] << 8) | ptr[1];
  return sm->bitmap2[v >> 3] & (1 << (v & 7));
}

static OLM_ALWAYS_INLINE int
short_matcher_prefix_query(const uint8_t *restrict bitmap,
                           const uint8_t *restrict ptr) {
  const uint16_t prefix = ((uint16_t)ptr[0] << 8) | ptr[1];
  return bitmap[prefix >> 3] & (1u << (prefix & 7));
}

static OLM_ALWAYS_INLINE int
short_matcher_query3_fast(const short_matcher_t *restrict sm,
                         const uint8_t *restrict ptr) {
  if (unlikely(sm->len3 == 0)) return 0;
  const uint32_t key =
      ((uint32_t)ptr[0] << 16) | ((uint32_t)ptr[1] << 8) | ptr[2];
  return binary_search_uint32_optimized(sm->arr3, sm->len3, key);
}

static OLM_ALWAYS_INLINE int
short_matcher_query4_fast(const short_matcher_t *restrict sm,
                         const uint8_t *restrict ptr) {
  if (unlikely(sm->len4 == 0)) return 0;
  const uint32_t key = ((uint32_t)ptr[0] << 24) | ((uint32_t)ptr[1] << 16) |
                       ((uint32_t)ptr[2] << 8) | ptr[3];
  return binary_search_uint32_optimized(sm->arr4, sm->len4, key);
}

static OLM_ALWAYS_INLINE int
short_matcher_index3_fast(const short_matcher_t *restrict sm,
                         const uint8_t *restrict ptr) {
  if (unlikely(sm->len3 == 0)) return -1;
  const uint32_t key =
      ((uint32_t)ptr[0] << 16) | ((uint32_t)ptr[1] << 8) | ptr[2];
  return sm_find_index(sm->arr3, sm->len3, key);
}

static OLM_ALWAYS_INLINE int
short_matcher_index4_fast(const short_matcher_t *restrict sm,
                         const uint8_t *restrict ptr) {
  if (unlikely(sm->len4 == 0)) return -1;
  const uint32_t key = ((uint32_t)ptr[0] << 24) | ((uint32_t)ptr[1] << 16) |
                       ((uint32_t)ptr[2] << 8) | ptr[3];
  return sm_find_index(sm->arr4, sm->len4, key);
}



// Core case-sensitive matcher with performance optimizations
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

  // Hoist matcher fields and create local copies to improve cache locality
  const uint32_t table_mask = matcher->header->table_size - 1;
  const uint32_t *restrict idx_arr = matcher->index_array;
  const uint8_t *restrict bucket = matcher->bucket_data;
  const uint8_t *restrict pat_st = matcher->pattern_store;
  const bloom_filter_t *restrict bf = &matcher->bf;
  const short_matcher_t *restrict sm = &matcher->short_matcher;
  const uint8_t *restrict sm_prefix3 = matcher->short_prefix3;
  const uint8_t *restrict sm_prefix4 = matcher->short_prefix4;
  const uint32_t smallest = matcher->header->smallest_pattern_length;
  const uint32_t largest = matcher->header->largest_pattern_length;

  const bool use_sm = smallest <= 4;
  const bool use_sm1 = sm->len1 > 0;
  const bool use_sm2 = sm->len2 > 0;
  const bool use_sm3 = sm->len3 > 0;
  const bool use_sm4 = sm->len4 > 0;

  // Short matcher key lookup data (hoisted for cache locality)
  const uint8_t *sm_base = matcher->short_matcher_base;
  const uint8_t *sm_keys1 = matcher->sm_keys1_offset
                                ? sm_base + matcher->sm_keys1_offset
                                : NULL;
  const uint32_t *sm_vals2 = matcher->sm_vals2;
  const uint8_t *sm_keys2 = matcher->sm_keys2_offset
                                ? sm_base + matcher->sm_keys2_offset
                                : NULL;
  const uint32_t sm_len2_keyed = matcher->sm_len2_keyed;
  const uint8_t *sm_keys3 = matcher->sm_keys3_offset
                                ? sm_base + matcher->sm_keys3_offset
                                : NULL;
  const uint8_t *sm_keys4 = matcher->sm_keys4_offset
                                ? sm_base + matcher->sm_keys4_offset
                                : NULL;

  // Optional word-boundary fast-path. Line-start matching instead scans the
  // input once with an early boundary branch below: materializing every line
  // start could require about eight bytes of offsets per input byte for
  // newline-dense data.
  size_t *candidate_pos = NULL;
  size_t candidate_cnt = 0;
  if (word_boundary && !line_start) {
    // First pass: count boundaries
    size_t cnt = 0;
    uint8_t prev_is_word = 0;
    for (size_t i = 0; i < haystack_size; ++i) {
      const uint8_t c = haystack[i];
      const uint8_t curr_is_word = IS_WORD(c) ? 1 : 0;
      if (curr_is_word != prev_is_word) {
        ++cnt;
      }
      prev_is_word = curr_is_word;
    }
    if (cnt > 0) {
      candidate_pos = (size_t *)malloc(cnt * sizeof(size_t));
      if (unlikely(!candidate_pos)) {
        ABORT("malloc word_boundary positions");
      }
      // Second pass: fill positions
      size_t w = 0;
      prev_is_word = 0;
      for (size_t i = 0; i < haystack_size; ++i) {
        const uint8_t c = haystack[i];
        const uint8_t curr_is_word = IS_WORD(c) ? 1 : 0;
        if (curr_is_word != prev_is_word) {
          candidate_pos[w++] = i;
        }
        prev_is_word = curr_is_word;
      }
      candidate_cnt = w;
    }
  }

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

    if (candidate_pos && candidate_cnt > 0) {
      // MSVC requires signed integral type for OpenMP loop index (C3016)
      ptrdiff_t bi;
#ifdef OMEGA_MATCH_USE_OPENMP
#pragma omp for schedule(runtime)
#endif
      for (bi = 0; bi < (ptrdiff_t)candidate_cnt; ++bi) {
        const ptrdiff_t pos = (ptrdiff_t)candidate_pos[bi];
        const uint8_t *restrict h_ptr = haystack + pos;
        const size_t remaining = hsize - pos;

        // Hash table for patterns ≥ 5 with optimized bloom filter check
        if (largest >= 5 && remaining >= 4) {
          ++total_attempts;
          const uint32_t cand = pack_gram(h_ptr);
          if (unlikely(!bloom_filter_query(bf, cand))) {
            ++total_filtered;
          } else {
            uint32_t slot_offset;
            if (!probe_bucket(matcher->control_bytes, idx_arr, bucket, table_mask,
                             cand, &slot_offset)) {
              ++total_misses;
            } else {
              ++total_hits;
              scan_bucket_and_append(bucket + slot_offset, pat_st, local,
                                     haystack, (size_t)hsize, pos, word_boundary,
                                     word_prefix, word_suffix, line_start,
                                     line_end, matcher->has_keys,
                                     &total_comparisons);
            }
          }
        }

        // Short matcher for patterns of length 1–4
        if (use_sm) {
          const bool word_prefix_ok = !word_prefix || (pos == 0 || !IS_WORD(haystack[pos - 1]));
          const bool line_start_ok = !line_start || is_at_line_start(haystack, pos);

          if (use_sm4 && remaining >= 4) {
            const int idx4 =
                !short_matcher_prefix_query(sm_prefix4, h_ptr) ? -1
                : sm_keys4 ? short_matcher_index4_fast(sm, h_ptr)
                           : (short_matcher_query4_fast(sm, h_ptr) ? 0 : -1);
            if (idx4 >= 0) {
              const bool word_boundary_ok =
                  !word_boundary || (pos + 4 >= hsize) ||
                  !IS_WORD(haystack[pos + 4]);
              const bool word_suffix_ok = !word_suffix || (pos + 4 >= hsize || !IS_WORD(haystack[pos + 4]));
              const bool line_end_ok = !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 4);
              if (word_boundary_ok && word_prefix_ok && word_suffix_ok && line_start_ok && line_end_ok) {
                ++total_hits;
                { const uint64_t k4 = sm_keys4 ? load_u64_unaligned(sm_keys4 + (idx4 * sizeof(uint64_t))) : 0;
                append_match(local, &(omega_match_result_t){ .offset = pos, .len = 4, ._reserved = 0, .match = h_ptr, .key = k4 }); }
              } else {
                ++total_misses;
              }
            }
          }
          if (use_sm3 && remaining >= 3) {
            const int idx3 =
                !short_matcher_prefix_query(sm_prefix3, h_ptr) ? -1
                : sm_keys3 ? short_matcher_index3_fast(sm, h_ptr)
                           : (short_matcher_query3_fast(sm, h_ptr) ? 0 : -1);
            if (idx3 >= 0) {
              const bool word_boundary_ok =
                  !word_boundary || (pos + 3 >= hsize) ||
                  !IS_WORD(haystack[pos + 3]);
              const bool word_suffix_ok = !word_suffix || (pos + 3 >= hsize || !IS_WORD(haystack[pos + 3]));
              const bool line_end_ok = !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 3);
              if (word_boundary_ok && word_prefix_ok && word_suffix_ok && line_start_ok && line_end_ok) {
                ++total_hits;
                { const uint64_t k3 = sm_keys3 ? load_u64_unaligned(sm_keys3 + (idx3 * sizeof(uint64_t))) : 0;
                append_match(local, &(omega_match_result_t){ .offset = pos, .len = 3, ._reserved = 0, .match = h_ptr, .key = k3 }); }
              } else {
                ++total_misses;
              }
            }
          }
          if (use_sm2 && remaining >= 2) {
            if (short_matcher_query2_fast(sm, h_ptr)) {
              const bool word_boundary_ok =
                  !word_boundary || (pos + 2 >= hsize) ||
                  !IS_WORD(haystack[pos + 2]);
              const bool word_suffix_ok = !word_suffix || (pos + 2 >= hsize || !IS_WORD(haystack[pos + 2]));
              const bool line_end_ok = !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 2);
              if (word_boundary_ok && word_prefix_ok && word_suffix_ok && line_start_ok && line_end_ok) {
                ++total_hits;
                { const uint16_t v2 = ((uint16_t)h_ptr[0]<<8)|h_ptr[1]; const uint64_t k2 = sm_keys2 ? sm_lookup_key2(sm_vals2, sm_keys2, sm_len2_keyed, (uint32_t)v2) : 0;
                append_match(local, &(omega_match_result_t){ .offset = pos, .len = 2, ._reserved = 0, .match = h_ptr, .key = k2 }); }
              } else {
                ++total_misses;
              }
            }
          }
          if (use_sm1) {
            if (short_matcher_query1_fast(sm, *h_ptr)) {
              const bool word_boundary_ok = !word_boundary || (pos + 1 >= hsize || !IS_WORD(haystack[pos + 1]));
              const bool word_suffix_ok = !word_suffix || (pos + 1 >= hsize || !IS_WORD(haystack[pos + 1]));
              const bool line_end_ok = !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 1);
              if (word_boundary_ok && word_prefix_ok && word_suffix_ok && line_start_ok && line_end_ok) {
                ++total_hits;
                { const uint64_t k1 = sm_keys1 ? load_u64_unaligned(sm_keys1 + ((size_t)(*h_ptr) * sizeof(uint64_t))) : 0;
                append_match(local, &(omega_match_result_t){ .offset = pos, .len = 1, ._reserved = 0, .match = h_ptr, .key = k1 }); }
              } else {
                ++total_misses;
              }
            }
          }
        }
      }
    } else {
      ptrdiff_t pos;
#ifdef OMEGA_MATCH_USE_OPENMP
#pragma omp for schedule(runtime)
#endif
      for (pos = 0; pos < hsize; ++pos) {
        // Match only byte zero and bytes immediately following a line ending.
        // This single parallel pass keeps line-start auxiliary memory constant
        // even when nearly every byte is a newline.
        if (line_start && pos > 0 && !is_line_end(haystack[pos - 1])) {
          continue;
        }

        // Word boundary optimization: skip non-boundary positions early
        const uint8_t curr_char = haystack[pos];
        if (word_boundary) {
          const bool curr_is_word = IS_WORD(curr_char);
          const bool prev_is_word = (pos > 0) ? IS_WORD(haystack[pos - 1]) : false;
          if (curr_is_word == prev_is_word) {
            continue;
          }
        }

        const uint8_t *restrict h_ptr = haystack + pos;
        const size_t remaining = hsize - pos;

      // Hash table for patterns ≥ 5 with optimized bloom filter check
      if (largest >= 5 && remaining >= 4) {
        ++total_attempts;
        const uint32_t cand = pack_gram(h_ptr);
        
        // Use the official bloom filter check which implements 3-hash bloom filter
        if (unlikely(!bloom_filter_query(bf, cand))) {
          ++total_filtered;
        } else {
          uint32_t slot_offset;
          if (!probe_bucket(matcher->control_bytes, idx_arr, bucket, table_mask,
                           cand, &slot_offset)) {
            ++total_misses;
          } else {
            ++total_hits;
            scan_bucket_and_append(bucket + slot_offset, pat_st, local,
                                   haystack, (size_t)hsize, pos, word_boundary,
                                   word_prefix, word_suffix, line_start,
                                   line_end, matcher->has_keys,
                                   &total_comparisons);
          }
        }
      }

  // Short matcher for patterns of length 1–4 with optimizations
  if (use_sm) {
        // Pre-compute common boundary checks for this position
        const bool word_prefix_ok = !word_prefix || (pos == 0 || !IS_WORD(haystack[pos - 1]));
        const bool line_start_ok = !line_start || is_at_line_start(haystack, pos);
        
        // Check length 4 patterns first (most selective) - better cache utilization
        if (use_sm4 && remaining >= 4) {
          const int idx4 =
              !short_matcher_prefix_query(sm_prefix4, h_ptr) ? -1
              : sm_keys4 ? short_matcher_index4_fast(sm, h_ptr)
                         : (short_matcher_query4_fast(sm, h_ptr) ? 0 : -1);
          if (idx4 >= 0) {
            const bool word_boundary_ok =
                !word_boundary || (pos + 4 >= hsize) ||
                !IS_WORD(haystack[pos + 4]);
            const bool word_suffix_ok = !word_suffix || (pos + 4 >= hsize || !IS_WORD(haystack[pos + 4]));
            const bool line_end_ok = !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 4);
            
            if (word_boundary_ok && word_prefix_ok && word_suffix_ok && 
                      line_start_ok && line_end_ok) {
              ++total_hits;
              { const uint64_t k4 = sm_keys4 ? load_u64_unaligned(sm_keys4 + (idx4 * sizeof(uint64_t))) : 0;
              append_match(local, &(omega_match_result_t){ .offset = pos, .len = 4, ._reserved = 0, .match = h_ptr, .key = k4 }); }
            } else {
              ++total_misses;
            }
          }
        }

        // Check length 3 patterns
        if (use_sm3 && remaining >= 3) {
          const int idx3 =
              !short_matcher_prefix_query(sm_prefix3, h_ptr) ? -1
              : sm_keys3 ? short_matcher_index3_fast(sm, h_ptr)
                         : (short_matcher_query3_fast(sm, h_ptr) ? 0 : -1);
          if (idx3 >= 0) {
            const bool word_boundary_ok =
                !word_boundary || (pos + 3 >= hsize) ||
                !IS_WORD(haystack[pos + 3]);
            const bool word_suffix_ok = !word_suffix || (pos + 3 >= hsize || !IS_WORD(haystack[pos + 3]));
            const bool line_end_ok = !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 3);

            if (word_boundary_ok && word_prefix_ok && word_suffix_ok &&
                      line_start_ok && line_end_ok) {
              ++total_hits;
              { const uint64_t k3 = sm_keys3 ? load_u64_unaligned(sm_keys3 + (idx3 * sizeof(uint64_t))) : 0;
              append_match(local, &(omega_match_result_t){ .offset = pos, .len = 3, ._reserved = 0, .match = h_ptr, .key = k3 }); }
            } else {
              ++total_misses;
            }
          }
        }

        // Check length 2 patterns (bitmap check is fast)
        if (use_sm2 && remaining >= 2) {
          if (short_matcher_query2_fast(sm, h_ptr)) {
            const bool word_boundary_ok =
                !word_boundary || (pos + 2 >= hsize) ||
                !IS_WORD(haystack[pos + 2]);
            const bool word_suffix_ok = !word_suffix || (pos + 2 >= hsize || !IS_WORD(haystack[pos + 2]));
            const bool line_end_ok = !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 2);

            if (word_boundary_ok && word_prefix_ok && word_suffix_ok &&
                      line_start_ok && line_end_ok) {
              ++total_hits;
              { const uint16_t v2 = ((uint16_t)h_ptr[0]<<8)|h_ptr[1]; const uint64_t k2 = sm_keys2 ? sm_lookup_key2(sm_vals2, sm_keys2, sm_len2_keyed, (uint32_t)v2) : 0;
              append_match(local, &(omega_match_result_t){ .offset = pos, .len = 2, ._reserved = 0, .match = h_ptr, .key = k2 }); }
            } else {
              ++total_misses;
            }
          }
        }

        // Check length 1 patterns (bitmap check is fastest)
        if (use_sm1) {
          if (short_matcher_query1_fast(sm, *h_ptr)) {
            const bool word_boundary_ok = !word_boundary || (pos + 1 >= hsize || !IS_WORD(haystack[pos + 1]));
            const bool word_suffix_ok = !word_suffix || (pos + 1 >= hsize || !IS_WORD(haystack[pos + 1]));
            const bool line_end_ok = !line_end || is_at_line_end(haystack, (size_t)hsize, pos, 1);

            if (word_boundary_ok && word_prefix_ok && word_suffix_ok &&
                      line_start_ok && line_end_ok) {
              ++total_hits;
              { const uint64_t k1 = sm_keys1 ? load_u64_unaligned(sm_keys1 + ((size_t)(*h_ptr) * sizeof(uint64_t))) : 0;
              append_match(local, &(omega_match_result_t){ .offset = pos, .len = 1, ._reserved = 0, .match = h_ptr, .key = k1 }); }
            } else {
              ++total_misses;
            }
          }
        }
        }
      }
    }
  }

  omega_match_results_t *results = finalize_match_results(
      thread_matches, max_threads, no_overlap, longest_only);

  if (candidate_pos) {
    free(candidate_pos);
  }

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

// Transform-aware wrapper processing the haystack in overlapping windows so
// matches spanning window boundaries are not lost. Each window carries one
// byte of left context (for word/line start checks) and largest_pattern_length
// bytes of right overlap so every match starting inside a window is fully
// contained in it; matches starting in the overlap belong to the next window.
// Per-window matching runs unfiltered and no_overlap/longest_only are applied
// once in the global merge, keeping their greedy semantics consistent across
// window boundaries.
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
  const size_t win_size = CASE_INSENSITIVE_WINDOW_SIZE;
  const int flags = matcher->header->flags;
  // Punctuation skipping and whitespace elision shrink the input, so windows
  // must be cut in normalized coordinates with a backmap; case folding alone
  // is 1:1 and windows can be cut directly in original coordinates.
  const int needs_backmap =
      (flags & (FLAG_IGNORE_PUNCTUATION | FLAG_ELIDE_WHITESPACE)) != 0;

  if (!needs_backmap && haystack_size <= win_size) {
    // Single 1:1 window: filters keep their semantics inside core_match, and
    // offsets are unchanged, so only the match pointers need remapping from
    // the normalized buffer back to the original haystack.
    uint32_t processed_len = 0;
    const uint8_t *normalized =
        transform_apply(matcher->transform_table, haystack,
                        (uint32_t)haystack_size, &processed_len, NULL);
    omega_match_results_t *r = core_match(
        matcher, normalized, processed_len, no_overlap, longest_only,
        word_boundary, word_prefix, word_suffix, line_start, line_end);
    if (unlikely(!r)) {
      ABORT("core_match failed"); // OOM
    }
    for (size_t i = 0; i < r->count; ++i) {
      r->matches[i].match = haystack + r->matches[i].offset;
    }
    return r;
  }

  // Every non-final window consumes win_size bytes of input (a normalized
  // byte consumes at least one original byte), so this bounds window count.
  const size_t max_windows = haystack_size / win_size + 2;
  match_vector_t **window_vectors =
      calloc(max_windows, sizeof(match_vector_t *));
  if (unlikely(!window_vectors)) {
    ABORT("calloc window_vectors"); // OOM
  }
  size_t used = 0;

  if (!needs_backmap) {
    size_t base = 0; // original offset where this window's owned region starts
    for (;;) {
      const size_t lead = base > 0 ? 1 : 0;
      const size_t start = base - lead;
      const size_t want = lead + win_size + max_pat;
      const size_t avail = haystack_size - start;
      const size_t span = avail < want ? avail : want;
      const int has_next = base + win_size < haystack_size;

      uint32_t processed_len = 0;
      const uint8_t *normalized =
          transform_apply(matcher->transform_table, haystack + start,
                          (uint32_t)span, &processed_len, NULL);
      omega_match_results_t *r =
          core_match(matcher, normalized, processed_len, 0, 0, word_boundary,
                     word_prefix, word_suffix, line_start, line_end);
      if (unlikely(!r)) {
        ABORT("core_match failed"); // OOM
      }

      match_vector_t *local = calloc(1, sizeof(*local));
      if (unlikely(!local)) {
        ABORT("calloc window vector"); // OOM
      }
      reserve_match_vector(local, r->count);
      const size_t keep_end = lead + win_size;
      for (size_t i = 0; i < r->count; ++i) {
        omega_match_result_t *m = &r->matches[i];
        if (m->offset < lead) {
          continue; // left-context byte, owned by the previous window
        }
        if (has_next && m->offset >= keep_end) {
          continue; // right overlap, owned by the next window
        }
        m->offset += start;
        m->match = haystack + m->offset;
        append_match(local, m);
      }
      omega_match_results_destroy(r);
      window_vectors[used++] = local;

      if (!has_next) {
        break;
      }
      base += win_size;
    }
  } else {
    // Stream the transform into a sliding buffer of normalized bytes with a
    // per-byte backmap to original positions. A normalized match can span
    // arbitrarily many original bytes (elided runs, skipped punctuation), so
    // the overlap must be measured in normalized coordinates.
    const size_t buf_cap = 1 + win_size + max_pat;
    uint8_t *norm = malloc(buf_cap);
    size_t *backmap = malloc(buf_cap * sizeof(size_t));
    if (unlikely(!norm || !backmap)) {
      ABORT("malloc transform window"); // OOM
    }
    const int16_t *restrict table = matcher->transform_table->table;

    size_t src = 0;      // next original byte to consume
    size_t norm_len = 0; // valid bytes in norm[]
    size_t lead = 0;     // left-context bytes at the front of norm[]
    int in_space = 0;    // whitespace-elision state, carried across windows
    for (;;) {
      const size_t fill_to = lead + win_size + max_pat;
      while (norm_len < fill_to && src < haystack_size) {
        const int16_t mapped = table[haystack[src]];
        if (mapped == TRANSFORM_SKIP) {
          ++src;
          continue;
        }
        if (mapped == TRANSFORM_ELIDE_SPACE) {
          if (!in_space) {
            norm[norm_len] = ' ';
            backmap[norm_len] = src;
            ++norm_len;
            in_space = 1;
          }
          ++src;
          continue;
        }
        norm[norm_len] = (uint8_t)mapped;
        backmap[norm_len] = src;
        ++norm_len;
        in_space = 0;
        ++src;
      }
      const int has_next = src < haystack_size;

      omega_match_results_t *r =
          core_match(matcher, norm, norm_len, 0, 0, word_boundary, word_prefix,
                     word_suffix, line_start, line_end);
      if (unlikely(!r)) {
        ABORT("core_match failed"); // OOM
      }

      match_vector_t *local = calloc(1, sizeof(*local));
      if (unlikely(!local)) {
        ABORT("calloc window vector"); // OOM
      }
      reserve_match_vector(local, r->count);
      const size_t keep_end = lead + win_size;
      for (size_t i = 0; i < r->count; ++i) {
        omega_match_result_t *m = &r->matches[i];
        if (m->offset < lead) {
          continue; // left-context byte, owned by the previous window
        }
        if (has_next && m->offset >= keep_end) {
          continue; // right overlap, owned by the next window
        }
        const size_t original_offset = backmap[m->offset];
        const size_t original_end = backmap[m->offset + m->len - 1];
        m->offset = original_offset;
        m->len = (uint32_t)(original_end - original_offset + 1);
        m->match = haystack + original_offset;
        append_match(local, m);
      }
      omega_match_results_destroy(r);
      window_vectors[used++] = local;

      if (!has_next) {
        break;
      }
      // Slide: keep one byte of left context plus the right-overlap tail.
      const size_t keep_from = keep_end - 1;
      const size_t tail = norm_len - keep_from;
      memmove(norm, norm + keep_from, tail);
      memmove(backmap, backmap + keep_from, tail * sizeof(size_t));
      norm_len = tail;
      lead = 1;
    }
    free(norm);
    free(backmap);
  }

  return finalize_match_results(window_vectors, used, no_overlap,
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
