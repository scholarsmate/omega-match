// compiler.c

#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "omega/details/bloom.h"
#include "omega/details/common.h"
#include "omega/details/dedupe_set.h"
#include "omega/details/hash_table.h"
#include "omega/details/hash.h"
#include "omega/details/pattern_store.h"
#include "omega/details/transform_table.h"
#include "omega/details/util.h"
#include "omega/list_matcher.h"

#define BLOOM_NUM_BITS_PER_ENTRY (20) // bits per entry (higher -> fewer FPs)
#define INITIAL_SHORT_CAPACITY (64)

typedef struct {
  short_matcher_t sm;
  uint32_t cap3;
  uint32_t cap4;
  dedup_set_t *dedup_set;
  // Key arrays for short patterns (parallel storage, NULL when not using keys)
  uint64_t keys1[256];   // key for each 1-byte pattern (indexed by byte value)
  uint64_t *keys3;       // parallel to arr3
  uint64_t *keys4;       // parallel to arr4
  uint32_t *vals2;       // sorted 2-byte values (for key lookup)
  uint64_t *keys2;       // parallel to vals2
  uint32_t len2_keyed;   // number of 2-byte keyed entries
  uint32_t cap2_keyed;   // capacity of vals2/keys2 arrays
} short_matcher_builder_t;

struct omega_list_matcher_compiler_struct {
  hash_table_t table;
  omega_match_pattern_store_stats_t stats;
  uint32_t compiler_flags;
  short_matcher_builder_t smb;
  const char *compiled_file_name;
  transform_table_t *transform_table;
  FILE *compiled_fp;
  pattern_store_t *store;
  int has_keys; // Set to 1 when any pattern has a user-defined key
};

OLM_ALWAYS_INLINE static int compare_patterns(const void *restrict a,
                                              const void *restrict b) {
  const pattern_t *p1 = (const pattern_t *)a;
  const pattern_t *p2 = (const pattern_t *)b;
  // Primary: length descending
  if (p1->len != p2->len) {
    return (p2->len > p1->len) - (p2->len < p1->len);
  }
  // Tie-breaker: offset ascending (deterministic ordering)
  if (p1->offset != p2->offset) {
    return (p1->offset > p2->offset) - (p1->offset < p2->offset);
  }
  return 0;
}

// Paired uint32 + uint64 for parallel sorting of short matcher arrays with keys
typedef struct {
  uint64_t key;
  uint32_t val;
} val_key_pair_t;

// Paired pattern_t + uint64 for sorting bucket patterns with keys in sync
typedef struct {
  pattern_t pat;
  uint64_t key;
} pattern_key_pair_t;

OLM_ALWAYS_INLINE static int compare_uint32(const void *restrict a,
                                            const void *restrict b) {
  const uint32_t v1 = *(const uint32_t *)a;
  const uint32_t v2 = *(const uint32_t *)b;
  return (v1 > v2) - (v1 < v2);
}

OLM_ALWAYS_INLINE static int compare_pattern_key_pair(const void *restrict a,
                                                       const void *restrict b) {
  const pattern_key_pair_t *p1 = (const pattern_key_pair_t *)a;
  const pattern_key_pair_t *p2 = (const pattern_key_pair_t *)b;
  // Primary: length descending (same as compare_patterns)
  if (p1->pat.len != p2->pat.len) {
    return (p2->pat.len > p1->pat.len) - (p2->pat.len < p1->pat.len);
  }
  // Tie-breaker: offset ascending
  if (p1->pat.offset != p2->pat.offset) {
    return (p1->pat.offset > p2->pat.offset) - (p1->pat.offset < p2->pat.offset);
  }
  return 0;
}

OLM_ALWAYS_INLINE static int compare_val_key_pair(const void *restrict a,
                                                   const void *restrict b) {
  const val_key_pair_t *p1 = (const val_key_pair_t *)a;
  const val_key_pair_t *p2 = (const val_key_pair_t *)b;
  return (p1->val > p2->val) - (p1->val < p2->val);
}

// This is the only place bucket order should be changed. patterns[] and
// user_keys[] form a logical pair: any reorder must happen in lockstep.
static inline void
sort_hash_entry_patterns(hash_entry_t *restrict entry) {
  if (entry->count <= 1) {
    return;
  }
  if (entry->user_keys) {
    const uint32_t cnt = entry->count;
    pattern_key_pair_t *pairs = malloc(cnt * sizeof(pattern_key_pair_t));
    if (unlikely(!pairs)) {
      ABORT("malloc pattern_key_pairs");
    }
    for (uint32_t i = 0; i < cnt; ++i) {
      pairs[i].pat = entry->patterns[i];
      pairs[i].key = entry->user_keys[i];
    }
    qsort(pairs, cnt, sizeof(pattern_key_pair_t), compare_pattern_key_pair);
    for (uint32_t i = 0; i < cnt; ++i) {
      entry->patterns[i] = pairs[i].pat;
      entry->user_keys[i] = pairs[i].key;
    }
    free(pairs);
    return;
  }
  qsort(entry->patterns, entry->count, sizeof(pattern_t), compare_patterns);
}

static inline void
short_matcher_init(omega_list_matcher_compiler_t *restrict compiler) {
  short_matcher_builder_t *smb = &compiler->smb;
  smb->sm.arr3 = calloc(INITIAL_SHORT_CAPACITY, sizeof(uint32_t));
  smb->sm.arr4 = calloc(INITIAL_SHORT_CAPACITY, sizeof(uint32_t));
  smb->keys3 = calloc(INITIAL_SHORT_CAPACITY, sizeof(uint64_t));
  smb->keys4 = calloc(INITIAL_SHORT_CAPACITY, sizeof(uint64_t));
  smb->dedup_set = dedup_set_create();
  if (unlikely(!smb->sm.arr3 || !smb->sm.arr4 || !smb->keys3 || !smb->keys4 ||
               !smb->dedup_set)) {
    free(smb->sm.arr3);
    free(smb->sm.arr4);
    free(smb->keys3);
    free(smb->keys4);
    dedup_set_destroy(smb->dedup_set);
    ABORT("init short_matcher_builder");
  }
  smb->sm.len3 = smb->sm.len4 = 0;
  smb->cap3 = smb->cap4 = INITIAL_SHORT_CAPACITY;
  memset(smb->keys1, 0, sizeof(smb->keys1));
  smb->vals2 = NULL;
  smb->keys2 = NULL;
  smb->len2_keyed = 0;
  smb->cap2_keyed = 0;
}

static inline void
short_matcher_free(const omega_list_matcher_compiler_t *restrict compiler) {
  const short_matcher_builder_t *smb = &compiler->smb;
  dedup_set_destroy(smb->dedup_set);
  free(smb->sm.arr3);
  free(smb->sm.arr4);
  free(smb->keys3);
  free(smb->keys4);
  free(smb->vals2);
  free(smb->keys2);
}

static int short_matcher_add(omega_list_matcher_compiler_t *restrict compiler,
                             const uint8_t *restrict buf, const uint32_t len,
                             const uint64_t user_key) {
  short_matcher_builder_t *smb = &compiler->smb;

  // Check for duplicates
  if (dedup_set_add(smb->dedup_set, buf, len) == 0) {
    ++compiler->stats.duplicate_patterns;
    return 0;
  }

  switch (len) {
  case 1: {
    smb->sm.bitmap1[buf[0] >> 3] |= (1 << (buf[0] & 7));
    smb->keys1[buf[0]] = user_key;
    ++smb->sm.len1;
    break;
  }
  case 2: {
    const uint16_t v = ((uint16_t)buf[0] << 8) | buf[1];
    smb->sm.bitmap2[v >> 3] |= (1 << (v & 7));
    // Store key in sparse array for 2-byte patterns
    if (smb->len2_keyed == smb->cap2_keyed) {
      const uint32_t newCap =
          smb->cap2_keyed ? (smb->cap2_keyed << 1) : INITIAL_SHORT_CAPACITY;
      uint32_t *new_vals2 = malloc(newCap * sizeof(uint32_t));
      uint64_t *new_keys2 = malloc(newCap * sizeof(uint64_t));
      if (unlikely(!new_vals2 || !new_keys2)) {
        free(new_vals2);
        free(new_keys2);
        return -1;
      }
      if (smb->len2_keyed > 0) {
        memcpy(new_vals2, smb->vals2, smb->len2_keyed * sizeof(uint32_t));
        memcpy(new_keys2, smb->keys2, smb->len2_keyed * sizeof(uint64_t));
      }
      free(smb->vals2);
      free(smb->keys2);
      smb->vals2 = new_vals2;
      smb->keys2 = new_keys2;
      smb->cap2_keyed = newCap;
    }
    smb->vals2[smb->len2_keyed] = (uint32_t)v;
    smb->keys2[smb->len2_keyed] = user_key;
    ++smb->len2_keyed;
    ++smb->sm.len2;
    break;
  }
  case 3: {
    if (smb->sm.len3 == smb->cap3) {
      const uint32_t new_cap3 = smb->cap3 << 1;
      uint32_t *new_arr3 = malloc(new_cap3 * sizeof(uint32_t));
      uint64_t *new_keys3 = malloc(new_cap3 * sizeof(uint64_t));
      if (unlikely(!new_arr3 || !new_keys3)) {
        free(new_arr3);
        free(new_keys3);
        return -1;
      }
      if (smb->sm.len3 > 0) {
        memcpy(new_arr3, smb->sm.arr3, smb->sm.len3 * sizeof(uint32_t));
        memcpy(new_keys3, smb->keys3, smb->sm.len3 * sizeof(uint64_t));
      }
      free(smb->sm.arr3);
      free(smb->keys3);
      smb->sm.arr3 = new_arr3;
      smb->keys3 = new_keys3;
      smb->cap3 = new_cap3;
    }
    smb->sm.arr3[smb->sm.len3] =
        ((uint32_t)buf[0] << 16) | (buf[1] << 8) | buf[2];
    smb->keys3[smb->sm.len3] = user_key;
    ++smb->sm.len3;
    break;
  }
  case 4: {
    if (smb->sm.len4 == smb->cap4) {
      const uint32_t new_cap4 = smb->cap4 << 1;
      uint32_t *new_arr4 = malloc(new_cap4 * sizeof(uint32_t));
      uint64_t *new_keys4 = malloc(new_cap4 * sizeof(uint64_t));
      if (unlikely(!new_arr4 || !new_keys4)) {
        free(new_arr4);
        free(new_keys4);
        return -1;
      }
      if (smb->sm.len4 > 0) {
        memcpy(new_arr4, smb->sm.arr4, smb->sm.len4 * sizeof(uint32_t));
        memcpy(new_keys4, smb->keys4, smb->sm.len4 * sizeof(uint64_t));
      }
      free(smb->sm.arr4);
      free(smb->keys4);
      smb->sm.arr4 = new_arr4;
      smb->keys4 = new_keys4;
      smb->cap4 = new_cap4;
    }
    smb->sm.arr4[smb->sm.len4] = ((uint32_t)buf[0] << 24) |
                                  ((uint32_t)buf[1] << 16) |
                                  ((uint32_t)buf[2] << 8) | buf[3];
    smb->keys4[smb->sm.len4] = user_key;
    ++smb->sm.len4;
    break;
  }
  default:
    ABORT("short_matcher_add: invalid pattern length");
  }
  ++compiler->stats.short_pattern_count;
  return 0;
}

omega_list_matcher_compiler_t *omega_list_matcher_compiler_create(
    const char *restrict compiled_file, const int case_insensitive,
    const int ignore_punctuation, const int elide_whitespace) {
  FILE *out = fopen(compiled_file, "wb");
  if (unlikely(!out)) {
    perror("fopen compiled_file");
    ABORT("fopen compiled_file");
  }
  const compiled_header_t header = {0};
  if (unlikely(fwrite(&header, sizeof(header), 1, out) != 1)) {
    ABORT("fwrite header");
  }
  omega_list_matcher_compiler_t *compiler = calloc(1, sizeof(*compiler));
  if (unlikely(!compiler)) {
    fclose(out);
    ABORT("calloc compiler");
  }

  compiler->store = init_pattern_store(out, &compiler->stats);
  if (unlikely(!compiler->store)) {
    fclose(out);
    free(compiler);
    ABORT("init_pattern_store");
  }

  // Only create the transform table if needed
  if (case_insensitive || ignore_punctuation || elide_whitespace) {
    compiler->transform_table = malloc(sizeof(transform_table_t));
    if (unlikely(!compiler->transform_table)) {
      fclose(out);
      free(compiler);
      ABORT("malloc pattern transform");
    }
    if (unlikely(transform_init(compiler->transform_table, case_insensitive,
                                ignore_punctuation, elide_whitespace) != 0)) {
      free(compiler->transform_table);
      fclose(out);
      free(compiler);
      ABORT("pattern_transform_init");
    }
    if (case_insensitive) {
      compiler->compiler_flags |= FLAG_IGNORE_CASE;
    }
    if (ignore_punctuation) {
      compiler->compiler_flags |= FLAG_IGNORE_PUNCTUATION;
    }
    if (elide_whitespace) {
      compiler->compiler_flags |= FLAG_ELIDE_WHITESPACE;
    }
  }

  compiler->compiled_file_name = strdup(compiled_file);
  if (unlikely(!compiler->compiled_file_name)) {
    transform_free(compiler->transform_table);
    free(compiler->transform_table);
    fclose(out);
    free(compiler);
    ABORT("strdup compiled_file_name");
  }
  compiler->compiled_fp = out;
  hash_table_init(&compiler->table, 0);
  short_matcher_init(compiler);
  return compiler;
}

int omega_list_matcher_compiler_add_pattern(
    omega_list_matcher_compiler_t *restrict compiler,
    const uint8_t *restrict pattern, uint32_t len) {
  return omega_list_matcher_compiler_add_pattern_with_key(compiler, pattern, len, 0);
}

int omega_list_matcher_compiler_add_pattern_with_key(
    omega_list_matcher_compiler_t *restrict compiler,
    const uint8_t *restrict pattern, uint32_t len, uint64_t user_key) {
  if (unlikely(len == 0 || !pattern)) {
    ABORT("omega_list_matcher_compiler_add_pattern_with_key: invalid arguments");
  }
  if (user_key != 0) {
    compiler->has_keys = 1;
  }
  if (compiler->transform_table) {
    pattern =
        transform_apply(compiler->transform_table, pattern, len, &len, NULL);
    if (unlikely(len == 0)) {
      return 0; // pattern normalized to nothing (e.g. all punctuation); skip
    }
  }
  if (len <= 4) {
    if (unlikely(short_matcher_add(compiler, pattern, len, user_key) != 0)) {
      ABORT("short_matcher_add");
    }
    if (len < compiler->stats.smallest_pattern_length) {
      compiler->stats.smallest_pattern_length = len;
    }
    if (len > compiler->stats.largest_pattern_length) {
      compiler->stats.largest_pattern_length = len;
    }
    compiler->stats.total_input_bytes += len;
  } else {
    const uint64_t offset = store_pattern(compiler->store, pattern, len);
    if (unlikely(offset == UINT64_MAX)) {
      return 0;
    }
    const uint32_t key = pack_gram(pattern);
    hash_table_insert(&compiler->table, key, offset, len, user_key);
  }
  return 0;
}

const omega_match_pattern_store_stats_t *
omega_list_matcher_compiler_get_pattern_store_stats(
    const omega_list_matcher_compiler_t *restrict compiler) {
  if (unlikely(!compiler)) {
    ABORT("omega_list_matcher_compiler_get_pattern_store_stats: invalid "
          "arguments");
  }
  return &compiler->stats;
}

int omega_list_matcher_compiler_destroy(
    omega_list_matcher_compiler_t *restrict compiler) {
  if (unlikely(!compiler)) {
    ABORT("omega_list_matcher_compiler_destroy: invalid arguments");
  }

  // Flushes the pattern store to the file
  destroy_pattern_store(compiler->store);

  compiled_header_t header = {0};

  // Make sure the next serialized section begins on an 8-byte boundary. The
  // padding belongs to the pattern-store span but is never referenced by a
  // pattern offset.
  fseek(compiler->compiled_fp, 0, SEEK_END);
  const long pattern_store_end = ftell(compiler->compiled_fp);
  const uint32_t pattern_store_padding =
      (uint32_t)((8 - (pattern_store_end & 7L)) & 7L);
  if (pattern_store_padding != 0) {
    const uint8_t zero[8] = {0};
    fwrite(zero, pattern_store_padding, 1, compiler->compiled_fp);
  }
  header.pattern_store_size =
      ftell(compiler->compiled_fp) - sizeof(compiled_header_t);

  // Create the bloom filter
  bloom_filter_t bf;
  bloom_filter_init(&bf, (size_t)((uint64_t)compiler->table.size *
                                  BLOOM_NUM_BITS_PER_ENTRY));

  uint32_t min_bucket = UINT_MAX, max_bucket = 0;
  for (uint32_t i = 0; i < compiler->table.size; ++i) {
    if (compiler->table.entries[i].count > 0) {
      bloom_filter_add(&bf, compiler->table.entries[i].key);
      if (compiler->table.entries[i].count < min_bucket) {
        min_bucket = compiler->table.entries[i].count;
      }
      if (compiler->table.entries[i].count > max_bucket) {
        max_bucket = compiler->table.entries[i].count;
      }
      sort_hash_entry_patterns(&compiler->table.entries[i]);
    }
  }

  header.bloom_filter_size = bloom_filter_size(&bf);
  header.num_occupied_buckets = compiler->table.used;
  header.table_size = compiler->table.size;
  header.min_bucket_size = (min_bucket == UINT_MAX ? 0 : min_bucket);
  header.max_bucket_size = max_bucket;
  header.load_factor =
      compiler->table.size
          ? (float)header.num_occupied_buckets / compiler->table.size
          : 0.0f;
  header.stored_pattern_count = compiler->stats.stored_pattern_count;
  header.avg_bucket_size =
      header.num_occupied_buckets
          ? (float)header.stored_pattern_count / compiler->table.used
          : 0.0f;

  bloom_filter_write(&bf, compiler->compiled_fp);
  bloom_filter_destroy(&bf);

  // Write the hash table header to include the size and used count
  fwrite(compiler->table.header, sizeof(compiler->table.header), 1,
         compiler->compiled_fp);

  // Reserve and write control-byte fingerprint array (version >=2 layout)
  //   0x00 => empty slot; non-zero => 8-bit fingerprint of key's hash
  const long control_array_start = ftell(compiler->compiled_fp);
  uint8_t *control_array = calloc(compiler->table.size, sizeof(uint8_t));
  if (unlikely(!control_array)) {
    ABORT("calloc control_array");
  }
  fwrite(control_array, sizeof(uint8_t), compiler->table.size,
         compiler->compiled_fp);

  // Reserve space for the index array
  const long index_array_start = ftell(compiler->compiled_fp);
  // Initialize all entries to 0xFFFFFFFF (EMPTY_SLOT sentinel)
  uint32_t *index_array = malloc(compiler->table.size * sizeof(uint32_t));
  if (unlikely(!index_array)) {
    ABORT("malloc index_array");
  }
  memset(index_array, 0xFF, compiler->table.size * sizeof(uint32_t));

  // Reserve space for the hash table index array with the current sentinel values
  fwrite(index_array, sizeof(uint32_t), compiler->table.size,
         compiler->compiled_fp);

  // Write the hash table entries
  const long bucket_data_start = ftell(compiler->compiled_fp);
  for (uint32_t i = 0; i < compiler->table.size; ++i) {
    if (compiler->table.entries[i].count == 0) {
      continue;
    }
    const long offset = ftell(compiler->compiled_fp);
    index_array[i] = (uint32_t)(offset - bucket_data_start);
    // Compute an 8-bit fingerprint from the key's hash. Ensure non-zero.
    const uint8_t fp = (uint8_t)((hash_uint32(compiler->table.entries[i].key) >> 24) | 1u);
    control_array[i] = fp;
    fwrite(&compiler->table.entries[i].key, sizeof(uint32_t), 1,
           compiler->compiled_fp);
    fwrite(&compiler->table.entries[i].count, sizeof(uint32_t), 1,
           compiler->compiled_fp);
    fwrite(compiler->table.entries[i].patterns, sizeof(pattern_t),
           compiler->table.entries[i].count, compiler->compiled_fp);
    // Write user keys for this bucket (only when FLAG_HAS_KEYS is set)
    if (compiler->has_keys) {
      const uint32_t cnt = compiler->table.entries[i].count;
      if (compiler->table.entries[i].user_keys) {
        fwrite(compiler->table.entries[i].user_keys, sizeof(uint64_t), cnt,
               compiler->compiled_fp);
      } else {
        // Write zeros for entries without explicit keys
        for (uint32_t j = 0; j < cnt; ++j) {
          const uint64_t zero = 0;
          fwrite(&zero, sizeof(uint64_t), 1, compiler->compiled_fp);
        }
      }
    }
  }

  // Record the size of the hash buckets in the header
  header.hash_buckets_size =
      (uint32_t)(ftell(compiler->compiled_fp) - bucket_data_start);

  // Go back and write the populated index array
  fseek(compiler->compiled_fp, index_array_start, SEEK_SET);
  fwrite(index_array, sizeof(uint32_t), compiler->table.size,
         compiler->compiled_fp);
  free(index_array);

  // Write the populated control-byte array
  fseek(compiler->compiled_fp, control_array_start, SEEK_SET);
  fwrite(control_array, sizeof(uint8_t), compiler->table.size,
    compiler->compiled_fp);
  free(control_array);

  // Write the short matcher if it has any patterns
  if (compiler->smb.sm.len4 > 0 || compiler->smb.sm.len3 > 0 ||
      compiler->smb.sm.len2 > 0 || compiler->smb.sm.len1 > 0) {
    // Sort 3-byte and 4-byte arrays with keys in parallel
    if (compiler->has_keys) {
      // Sort arr3 + keys3 together
      if (compiler->smb.sm.len3 > 0) {
        val_key_pair_t *pairs3 = malloc(compiler->smb.sm.len3 * sizeof(val_key_pair_t));
        if (unlikely(!pairs3)) { ABORT("malloc pairs3"); }
        for (uint32_t i = 0; i < compiler->smb.sm.len3; ++i) {
          pairs3[i].val = compiler->smb.sm.arr3[i];
          pairs3[i].key = compiler->smb.keys3[i];
        }
        qsort(pairs3, compiler->smb.sm.len3, sizeof(val_key_pair_t), compare_val_key_pair);
        for (uint32_t i = 0; i < compiler->smb.sm.len3; ++i) {
          compiler->smb.sm.arr3[i] = pairs3[i].val;
          compiler->smb.keys3[i] = pairs3[i].key;
        }
        free(pairs3);
      }
      // Sort arr4 + keys4 together
      if (compiler->smb.sm.len4 > 0) {
        val_key_pair_t *pairs4 = malloc(compiler->smb.sm.len4 * sizeof(val_key_pair_t));
        if (unlikely(!pairs4)) { ABORT("malloc pairs4"); }
        for (uint32_t i = 0; i < compiler->smb.sm.len4; ++i) {
          pairs4[i].val = compiler->smb.sm.arr4[i];
          pairs4[i].key = compiler->smb.keys4[i];
        }
        qsort(pairs4, compiler->smb.sm.len4, sizeof(val_key_pair_t), compare_val_key_pair);
        for (uint32_t i = 0; i < compiler->smb.sm.len4; ++i) {
          compiler->smb.sm.arr4[i] = pairs4[i].val;
          compiler->smb.keys4[i] = pairs4[i].key;
        }
        free(pairs4);
      }
      // Sort vals2 + keys2 together
      if (compiler->smb.len2_keyed > 0) {
        val_key_pair_t *pairs2 = malloc(compiler->smb.len2_keyed * sizeof(val_key_pair_t));
        if (unlikely(!pairs2)) { ABORT("malloc pairs2"); }
        for (uint32_t i = 0; i < compiler->smb.len2_keyed; ++i) {
          pairs2[i].val = compiler->smb.vals2[i];
          pairs2[i].key = compiler->smb.keys2[i];
        }
        qsort(pairs2, compiler->smb.len2_keyed, sizeof(val_key_pair_t), compare_val_key_pair);
        for (uint32_t i = 0; i < compiler->smb.len2_keyed; ++i) {
          compiler->smb.vals2[i] = pairs2[i].val;
          compiler->smb.keys2[i] = pairs2[i].key;
        }
        free(pairs2);
      }
    } else {
      qsort(compiler->smb.sm.arr3, compiler->smb.sm.len3, sizeof(uint32_t),
            compare_uint32);
      qsort(compiler->smb.sm.arr4, compiler->smb.sm.len4, sizeof(uint32_t),
            compare_uint32);
    }

    fseek(compiler->compiled_fp, 0, SEEK_END);
    const long int sm_start = ftell(compiler->compiled_fp);
    fwrite(SHORT_MATCHER_MAGIC, SHORT_MATCHER_MAGIC_SIZE, 1,
           compiler->compiled_fp); // short matcher magic
    fwrite(compiler->smb.sm.bitmap1, 1, 32, compiler->compiled_fp);
    fwrite(compiler->smb.sm.bitmap2, 1, 8192, compiler->compiled_fp);
    fwrite(&compiler->smb.sm.len1, sizeof(uint32_t), 1, compiler->compiled_fp);
    fwrite(&compiler->smb.sm.len2, sizeof(uint32_t), 1, compiler->compiled_fp);
    fwrite(&compiler->smb.sm.len3, sizeof(uint32_t), 1, compiler->compiled_fp);
    fwrite(&compiler->smb.sm.len4, sizeof(uint32_t), 1, compiler->compiled_fp);
    fwrite(compiler->smb.sm.arr3, sizeof(uint32_t), compiler->smb.sm.len3,
           compiler->compiled_fp);
    fwrite(compiler->smb.sm.arr4, sizeof(uint32_t), compiler->smb.sm.len4,
           compiler->compiled_fp);

    // Write key arrays for short matcher (only when FLAG_HAS_KEYS is set)
    if (compiler->has_keys) {
      // arr3/arr4 contain 32-bit values, so an odd combined element count can
      // leave the following uint64_t key arrays at offset 4 mod 8.
      const long key_array_start = ftell(compiler->compiled_fp);
      const uint32_t padding = (uint32_t)((8 - (key_array_start & 7L)) & 7L);
      if (padding != 0) {
        const uint8_t zero[8] = {0};
        fwrite(zero, padding, 1, compiler->compiled_fp);
      }
      // 1-byte keys: 256 entries indexed by byte value
      fwrite(compiler->smb.keys1, sizeof(uint64_t), 256, compiler->compiled_fp);
      // 2-byte keys: sparse sorted array
      fwrite(&compiler->smb.len2_keyed, sizeof(uint32_t), 1, compiler->compiled_fp);
      if (compiler->smb.len2_keyed > 0) {
        fwrite(compiler->smb.vals2, sizeof(uint32_t), compiler->smb.len2_keyed,
               compiler->compiled_fp);
      }
      // The uint32_t count and values may leave the following uint64_t key
      // arrays at offset 4 mod 8. Keep every v4 key array naturally aligned.
      const long key2_array_start = ftell(compiler->compiled_fp);
      const uint32_t key2_padding =
          (uint32_t)((8 - ((key2_array_start - sm_start) & 7L)) & 7L);
      if (key2_padding != 0) {
        const uint8_t zero[8] = {0};
        fwrite(zero, key2_padding, 1, compiler->compiled_fp);
      }
      if (compiler->smb.len2_keyed > 0) {
        fwrite(compiler->smb.keys2, sizeof(uint64_t), compiler->smb.len2_keyed,
               compiler->compiled_fp);
      }
      // 3-byte keys: parallel to arr3
      fwrite(compiler->smb.keys3, sizeof(uint64_t), compiler->smb.sm.len3,
             compiler->compiled_fp);
      // 4-byte keys: parallel to arr4
      fwrite(compiler->smb.keys4, sizeof(uint64_t), compiler->smb.sm.len4,
             compiler->compiled_fp);
    }

    header.short_matcher_size =
        (uint32_t)(ftell(compiler->compiled_fp) - sm_start);
  }

  // Complete the header population and write it at the beginning of the file
  memcpy(header.magic, HEADER_MAGIC, HEADER_MAGIC_SIZE);
  header.version = VERSION;
  header.flags = compiler->compiler_flags;
  if (compiler->has_keys) {
    header.flags |= FLAG_HAS_KEYS;
  }
  header.stored_pattern_count = compiler->stats.stored_pattern_count;
  header.smallest_pattern_length = compiler->stats.smallest_pattern_length;
  header.largest_pattern_length = compiler->stats.largest_pattern_length;

  fseek(compiler->compiled_fp, 0, SEEK_SET);
  fwrite(&header, sizeof(compiled_header_t), 1, compiler->compiled_fp);
  // The stream error flag is sticky, so this catches any earlier failed
  // fwrite (e.g. disk full) as well as the final flush/close.
  int status = 0;
  if (fflush(compiler->compiled_fp) != 0 ||
      ferror(compiler->compiled_fp) != 0) {
    status = -1;
  }
  if (fclose(compiler->compiled_fp) != 0) {
    status = -1;
  }
  free((void *)compiler->compiled_file_name);
  hash_table_free(&compiler->table);
  if (compiler->transform_table) {
    transform_free(compiler->transform_table);
    free(compiler->transform_table);
  }
  short_matcher_free(compiler);
  free(compiler);
  return status;
}

int omega_list_matcher_compile_patterns(
    const char *restrict compiled_file, const uint8_t *restrict patterns_buf,
    const uint64_t patterns_buf_size, const int case_insensitive,
    const int ignore_punctuation, const int elide_whitespace,
    omega_match_pattern_store_stats_t *restrict pattern_store_stats) {
  if (!compiled_file || !patterns_buf || patterns_buf_size == 0) {
    ABORT("Invalid arguments to omega_list_matcher_compile_patterns");
  }

  // Create the streaming compiler
  omega_list_matcher_compiler_t *compiler = omega_list_matcher_compiler_create(
      compiled_file, case_insensitive, ignore_punctuation, elide_whitespace);
  if (!compiler) {
    ABORT("omega_list_matcher_compiler_create");
  }

  const uint8_t *ptr = patterns_buf;
  const uint8_t *end = patterns_buf + patterns_buf_size;

  while (ptr < end) {
    const uint8_t *newline = memchr(ptr, '\n', end - ptr);
    if (!newline) {
      newline = end;
    }

    uint32_t line_len = (uint32_t)(newline - ptr);
    if (line_len > 0 && ptr[line_len - 1] == '\r') {
      --line_len;
    }
    if (line_len > 0) {
      omega_list_matcher_compiler_add_pattern(compiler, ptr, line_len);
    }
    ptr = newline + 1;
  }

  if (pattern_store_stats) {
    // Copy the pattern store statistics before destroying the compiler
    *pattern_store_stats =
        *omega_list_matcher_compiler_get_pattern_store_stats(compiler);
  }

  // Finalize the matcher, emitting the compiled file
  return omega_list_matcher_compiler_destroy(compiler);
}

int omega_list_matcher_compile_patterns_filename(
    const char *restrict compiled_file, const char *restrict patterns_file,
    const int case_insensitive, const int ignore_punctuation,
    const int elide_whitespace,
    omega_match_pattern_store_stats_t *restrict pattern_store_stats) {
  if (!compiled_file || !patterns_file) {
    return -1;
  }

  // Check if the patterns file exists and is readable
  if (oa_matcher_access(patterns_file) != 0) {
    return -1;
  }

  // Map the patterns file into memory
  // We use mmap to read the patterns file into memory for compilation and then
  // unmap it after compilation is complete. This is done to avoid reading the
  // entire file into a buffer.
  size_t patterns_buf_size = 0;
  const uint8_t *patterns_buf =
      omega_matcher_map_filename(patterns_file, &patterns_buf_size, 1);
  if (!patterns_buf) {
    ABORT("mmap patterns_file");
  }

  // DEBUG
  // fprintf(stderr, "Compiling matcher from patterns file %s (size: %zu)\n",
  // patterns_file, patterns_buf_size);

  const int result = omega_list_matcher_compile_patterns(
      compiled_file, patterns_buf, patterns_buf_size, case_insensitive,
      ignore_punctuation, elide_whitespace, pattern_store_stats);
  if (omega_matcher_unmap_file(patterns_buf, patterns_buf_size) != 0) {
    ABORT("unmap patterns_file");
  }
  return result;
}

// Check compiled header magic
int omega_list_matcher_is_compiled(const char *restrict compiled_file) {
  FILE *fp = fopen(compiled_file, "rb");
  if (!fp) {
    return 0;
  }
  char buf[HEADER_MAGIC_SIZE];
  const size_t n = fread(buf, 1, HEADER_MAGIC_SIZE, fp);
  fclose(fp);
  return (n == HEADER_MAGIC_SIZE &&
          memcmp(buf, HEADER_MAGIC, HEADER_MAGIC_SIZE) == 0);
}
