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
#include "omega/details/pattern_store.h"
#include "omega/details/transform_table.h"
#include "omega/details/util.h"
#include "omega/list_matcher.h"

#define BLOOM_NUM_BITS_PER_ENTRY (16) // bits per entry
#define INITIAL_SHORT_CAPACITY (64)

typedef struct {
  short_matcher_t sm;
  uint32_t cap3;
  uint32_t cap4;
  dedup_set_t *dedup_set;
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
};

OLM_ALWAYS_INLINE static int compare_patterns(const void *restrict a,
                                              const void *restrict b) {
  const pattern_t *p1 = a;
  const pattern_t *p2 = b;
  return (p2->len > p1->len) -
         (p2->len < p1->len); // Descending order by length
}

OLM_ALWAYS_INLINE static int compare_uint32(const void *restrict a,
                                            const void *restrict b) {
  const uint32_t v1 = *(const uint32_t *)a;
  const uint32_t v2 = *(const uint32_t *)b;
  return (v1 > v2) - (v1 < v2);
}

static inline void
short_matcher_init(omega_list_matcher_compiler_t *restrict compiler) {
  short_matcher_builder_t *smb = &compiler->smb;
  smb->sm.arr3 = calloc(INITIAL_SHORT_CAPACITY, sizeof(uint32_t));
  smb->sm.arr4 = calloc(INITIAL_SHORT_CAPACITY, sizeof(uint32_t));
  smb->dedup_set = dedup_set_create();
  if (unlikely(!smb->sm.arr3 || !smb->sm.arr4 || !smb->dedup_set)) {
    free(smb->sm.arr3);
    free(smb->sm.arr4);
    dedup_set_destroy(smb->dedup_set);
    ABORT("init short_matcher_builder");
  }
  smb->sm.len3 = smb->sm.len4 = 0;
  smb->cap3 = smb->cap4 = INITIAL_SHORT_CAPACITY;
}

static inline void
short_matcher_free(const omega_list_matcher_compiler_t *restrict compiler) {
  const short_matcher_builder_t *smb = &compiler->smb;
  dedup_set_destroy(smb->dedup_set);
  free(smb->sm.arr3);
  free(smb->sm.arr4);
}

static int short_matcher_add(omega_list_matcher_compiler_t *restrict compiler,
                             const uint8_t *restrict buf, const uint32_t len) {
  short_matcher_builder_t *smb = &compiler->smb;

  // Check for duplicates
  if (dedup_set_add(smb->dedup_set, buf, len) == 0) {
    ++compiler->stats.duplicate_patterns;
    return 0;
  }

  switch (len) {
  case 1: {
    smb->sm.bitmap1[buf[0] >> 3] |= (1 << (buf[0] & 7));
    ++smb->sm.len1;
    break;
  }
  case 2: {
    const uint16_t v = ((uint16_t)buf[0] << 8) | buf[1];
    smb->sm.bitmap2[v >> 3] |= (1 << (v & 7));
    ++smb->sm.len2;
    break;
  }
  case 3: {
    if (smb->sm.len3 == smb->cap3) {
      smb->cap3 <<= 1;
      smb->sm.arr3 = realloc(smb->sm.arr3, smb->cap3 * sizeof(uint32_t));
      if (unlikely(!smb->sm.arr3)) {
        return -1;
      }
    }
    smb->sm.arr3[smb->sm.len3++] =
        ((uint32_t)buf[0] << 16) | (buf[1] << 8) | buf[2];
    break;
  }
  case 4: {
    if (smb->sm.len4 == smb->cap4) {
      smb->cap4 <<= 1;
      smb->sm.arr4 = realloc(smb->sm.arr4, smb->cap4 * sizeof(uint32_t));
      if (unlikely(!smb->sm.arr4)) {
        return -1;
      }
    }
    smb->sm.arr4[smb->sm.len4++] = ((uint32_t)buf[0] << 24) |
                                   ((uint32_t)buf[1] << 16) |
                                   ((uint32_t)buf[2] << 8) | buf[3];
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
  if (unlikely(len == 0 || !pattern)) {
    ABORT("omega_list_matcher_compiler_add_pattern: invalid arguments");
  }
  if (compiler->transform_table) {
    pattern =
        transform_apply(compiler->transform_table, pattern, len, &len, NULL);
  }
  if (len <= 4) {
    if (unlikely(short_matcher_add(compiler, pattern, len) != 0)) {
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
      // fprintf(stderr, "WARNING: Duplicate pattern found: %.*s\n", len,
      // pattern);
      return 0;
    }
    const uint32_t key = pack_gram(pattern);
    hash_table_insert(&compiler->table, key, offset, len);
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

  // Make sure the file pointer is at the end of the file
  fseek(compiler->compiled_fp, 0, SEEK_END);
  header.pattern_store_size =
      ftell(compiler->compiled_fp) - sizeof(compiled_header_t);

  // Create the bloom filter
  bloom_filter_t bf;
  bloom_filter_init(&bf, compiler->table.size * BLOOM_NUM_BITS_PER_ENTRY);

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
      qsort(compiler->table.entries[i].patterns,
            compiler->table.entries[i].count, sizeof(pattern_t),
            compare_patterns);
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

  // Reserve space for the index array
  const long index_array_start = ftell(compiler->compiled_fp);
  uint32_t *index_array = calloc(compiler->table.size, sizeof(uint32_t));

  // Reserve space for the hash table index array
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
    fwrite(&compiler->table.entries[i].key, sizeof(uint32_t), 1,
           compiler->compiled_fp);
    fwrite(&compiler->table.entries[i].count, sizeof(uint32_t), 1,
           compiler->compiled_fp);
    fwrite(compiler->table.entries[i].patterns, sizeof(pattern_t),
           compiler->table.entries[i].count, compiler->compiled_fp);
  }

  // Record the size of the hash buckets in the header
  header.hash_buckets_size =
      (uint32_t)(ftell(compiler->compiled_fp) - bucket_data_start);

  // Go back and write the populated index array
  fseek(compiler->compiled_fp, index_array_start, SEEK_SET);
  fwrite(index_array, sizeof(uint32_t), compiler->table.size,
         compiler->compiled_fp);
  free(index_array);

  // Write the short matcher if it has any patterns
  if (compiler->smb.sm.len4 > 0 || compiler->smb.sm.len3 > 0 ||
      compiler->smb.sm.len2 > 0 || compiler->smb.sm.len1 > 0) {
    qsort(compiler->smb.sm.arr3, compiler->smb.sm.len3, sizeof(uint32_t),
          compare_uint32);
    qsort(compiler->smb.sm.arr4, compiler->smb.sm.len4, sizeof(uint32_t),
          compare_uint32);

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
    header.short_matcher_size =
        (uint32_t)(ftell(compiler->compiled_fp) - sm_start);
  }

  // Complete the header population and write it at the beginning of the file
  memcpy(header.magic, HEADER_MAGIC, HEADER_MAGIC_SIZE);
  header.version = VERSION;
  header.flags = compiler->compiler_flags;
  header.stored_pattern_count = compiler->stats.stored_pattern_count;
  header.smallest_pattern_length = compiler->stats.smallest_pattern_length;
  header.largest_pattern_length = compiler->stats.largest_pattern_length;

  fseek(compiler->compiled_fp, 0, SEEK_SET);
  fwrite(&header, sizeof(compiled_header_t), 1, compiler->compiled_fp);
  fflush(compiler->compiled_fp);
  fclose(compiler->compiled_fp);
  free((void *)compiler->compiled_file_name);
  hash_table_free(&compiler->table);
  if (compiler->transform_table) {
    transform_free(compiler->transform_table);
    free(compiler->transform_table);
  }
  short_matcher_free(compiler);
  free(compiler);
  return 0;
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
    ABORT("patterns_file not found or not readable");
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
