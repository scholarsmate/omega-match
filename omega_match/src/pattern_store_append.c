// pattern_store_append.c

#include <stdlib.h>
#include <string.h>

#include "omega/details/common.h"
#include "omega/details/dedupe_set.h"
#include "omega/details/pattern_store.h"
#include "omega/list_matcher.h"

// #define ALIGN_PATTERNS

typedef struct {
  FILE *fp;
  uint64_t store_offset;
  dedup_set_t *dedup_set;
} store_append_t;

uint64_t store_pattern_append(const pattern_store_t *iface,
                              const uint8_t *pattern, const uint32_t len) {
  const store_append_t *store = (store_append_t *)iface->backend;

  // Check for duplicates
  if (dedup_set_add(store->dedup_set, pattern, len) == 0) {
    if (iface->stats) {
      ++iface->stats->duplicate_patterns;
    }
    return UINT64_MAX; // Duplicate pattern
  }

  const long offset = ftell(store->fp);
  if (offset < 0) {
    ABORT("ftell failed");
  }
  const uint64_t pattern_offset = (uint64_t)offset - store->store_offset;
  if (fwrite(pattern, 1, len, store->fp) != len) {
    ABORT("fwrite pattern");
  }
#ifdef ALIGN_PATTERNS
  const size_t pad = (8 - (len % 8)) % 8;
  static const uint8_t zero_pad[8] = {0};
  if (pad && fwrite(zero_pad, 1, pad, store->fp) != pad) {
    return UINT64_MAX;
  }
#endif
  if (iface->stats) {
    if (len < iface->stats->smallest_pattern_length) {
      iface->stats->smallest_pattern_length = len;
    }
    if (len > iface->stats->largest_pattern_length) {
      iface->stats->largest_pattern_length = len;
    }
    ++iface->stats->stored_pattern_count;
    iface->stats->total_input_bytes += len;
#ifdef ALIGN_PATTERNS
    iface->stats->total_stored_bytes = pattern_offset + len + pad;
#else
    iface->stats->total_stored_bytes = pattern_offset + len;
#endif
  }

  return pattern_offset;
}

void destroy_store_append(pattern_store_t *iface) {
  store_append_t *store = (store_append_t *)iface->backend;
  fflush(store->fp);
  dedup_set_destroy(store->dedup_set);
  free(store);
  free(iface);
}

pattern_store_t *init_store_append(FILE *fp,
                                   omega_match_pattern_store_stats_t *stats) {
  if (unlikely(!fp)) {
    return NULL;
  }

  store_append_t *store = calloc(1, sizeof(store_append_t));
  if (unlikely(!store)) {
    fclose(fp);
    return NULL;
  }

  store->fp = fp;
  store->store_offset = ftell(fp);
  store->dedup_set = dedup_set_create();
  if (unlikely(!store->dedup_set)) {
    fclose(fp);
    free(store);
    return NULL;
  }
  pattern_store_t *iface = calloc(1, sizeof(pattern_store_t));
  if (unlikely(!iface)) {
    fclose(fp);
    dedup_set_destroy(store->dedup_set);
    free(store);
    return NULL;
  }
  iface->stats = stats;
  iface->store_pattern = store_pattern_append;
  iface->destroy = destroy_store_append;
  iface->backend = store;

  if (stats) {
    memset(stats, 0, sizeof(omega_match_pattern_store_stats_t));
    stats->smallest_pattern_length = UINT32_MAX;
  }
  return iface;
}
