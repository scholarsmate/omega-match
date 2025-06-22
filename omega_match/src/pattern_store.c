// pattern_store.c

#include <stdio.h>

#include "omega/details/pattern_store.h"
#include "omega/list_matcher.h"

// Backends
pattern_store_t *init_store_append(FILE *fp,
                                   omega_match_pattern_store_stats_t *stats);

pattern_store_t *init_pattern_store(FILE *fp,
                                    omega_match_pattern_store_stats_t *stats) {
  return init_store_append(fp, stats);
}

uint64_t store_pattern(const pattern_store_t *store, const uint8_t *pattern,
                       const uint32_t len) {
  return store->store_pattern(store, pattern, len);
}

void destroy_pattern_store(pattern_store_t *store) {
  if (store) {
    store->destroy(store);
  }
}
