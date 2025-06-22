// common.c

#include "omega/details/common.h"
#include "omega/details/util.h"

int emit_header_info(const compiled_header_t *restrict header,
                     FILE *restrict fp) {
  if (!header || !fp) {
    return -1; // Invalid arguments
  }
  // buffers for pretty numbers
  char buf_patterns[32], buf_smallest[32], buf_largest[32], buf_store[32],
      buf_bloom[32], buf_occupied[32], buf_table[32], buf_minbkt[32],
      buf_maxbkt[32];

  // Format numeric fields
  format_u64(header->stored_pattern_count, buf_patterns);
  format_u64(header->smallest_pattern_length, buf_smallest);
  format_u64(header->largest_pattern_length, buf_largest);
  format_u64(header->pattern_store_size, buf_store);
  format_u64(header->bloom_filter_size, buf_bloom);
  format_u64(header->num_occupied_buckets, buf_occupied);
  format_u64(header->table_size, buf_table);
  format_u64(header->min_bucket_size, buf_minbkt);
  format_u64(header->max_bucket_size, buf_maxbkt);

  fprintf(fp,
          "Header v%d stats: total_patterns=%s, smallest_pattern_length=%s, "
          "largest_pattern_length=%s,"
          " case_insensitive_support=%s, string_store_size=%s, "
          "bloom_filter_size=%s, num_occupied_buckets=%s,"
          " table_size=%s, min_bucket_size=%s, max_bucket_size=%s, "
          "load_factor=%.2f,"
          " avg_bucket_size=%.2f\n",
          header->version, buf_patterns, buf_smallest, buf_largest,
          (header->flags & FLAG_IGNORE_CASE) ? "yes" : "no", buf_store,
          buf_bloom, buf_occupied, buf_table, buf_minbkt, buf_maxbkt,
          header->load_factor, header->avg_bucket_size);
  return 0;
}
