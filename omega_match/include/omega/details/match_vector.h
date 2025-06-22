#ifndef OMEGA_LIST_MATCHER__DETAILS__MATCH_VECTOR_H
#define OMEGA_LIST_MATCHER__DETAILS__MATCH_VECTOR_H

#include <stdint.h>
#include <stdlib.h>

#include "../list_matcher.h" // defines omegaomega_match_t
#include "common.h"

#define INITIAL_MATCH_CAPACITY (8192) // initial capacity for match vectors

typedef struct {
  uint32_t count;
  uint32_t capacity;
  omega_match_result_t *data;
} match_vector_t;

static inline int reserve_match_vector(match_vector_t *restrict mv,
                                       size_t min_cap) {
  if (mv->capacity < min_cap) {
    mv->capacity = mv->capacity ? mv->capacity << 1 : INITIAL_MATCH_CAPACITY;
    while (mv->capacity < min_cap) {
      mv->capacity <<= 1;
    }
    mv->data = realloc(mv->data, mv->capacity * sizeof(omega_match_result_t));
    if (unlikely(!mv->data)) {
      ABORT("realloc match vector");
    }
  }
  return 0;
}

static inline void init_match_vector(match_vector_t *restrict mv) {
  mv->count = 0;
  mv->capacity = INITIAL_MATCH_CAPACITY;
  mv->data = (omega_match_result_t *)malloc(mv->capacity *
                                            sizeof(omega_match_result_t));
  if (unlikely(!mv->data)) {
    ABORT("malloc match vector");
  }
}

static inline void free_match_vector(match_vector_t *restrict mv) {
  free(mv->data);
  mv->data = NULL;
  mv->count = 0;
  mv->capacity = 0;
}

static inline void grow_match_vector(match_vector_t *restrict mv) {
  mv->capacity <<= 1;
  mv->data = (omega_match_result_t *)realloc(
      mv->data, mv->capacity * sizeof(omega_match_result_t));
  if (unlikely(!mv->data)) {
    ABORT("realloc match vector");
  }
}

static inline void append_match(match_vector_t *restrict mv,
                                const omega_match_result_t *restrict m) {
  if (unlikely(mv->count == mv->capacity)) {
    grow_match_vector(mv);
  }
  mv->data[mv->count++] = *m;
}

#endif // OMEGA_LIST_MATCHER__DETAILS__MATCH_VECTOR_H
