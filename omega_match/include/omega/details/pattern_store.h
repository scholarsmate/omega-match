#ifndef OMEGA_LIST_MATCHER__DETAILS__PATTERN_STORE_H
#define OMEGA_LIST_MATCHER__DETAILS__PATTERN_STORE_H

#include <stdint.h>
#include <stdio.h>

#include "../list_matcher.h"

typedef struct pattern_store pattern_store_t;

typedef uint64_t (*store_pattern_func_t)(const pattern_store_t *store,
                                         const uint8_t *pattern, uint32_t len);
typedef void (*destroy_pattern_store_func_t)(pattern_store_t *store);

struct pattern_store {
  omega_match_pattern_store_stats_t *stats;
  store_pattern_func_t store_pattern;
  destroy_pattern_store_func_t destroy;

  void *backend; // backend-specific internal state
};

pattern_store_t *init_pattern_store(FILE *restrict fp,
                                    omega_match_pattern_store_stats_t *stats);
uint64_t store_pattern(const pattern_store_t *restrict store,
                       const uint8_t *restrict pattern, uint32_t len);
void destroy_pattern_store(pattern_store_t *restrict store);

#endif
