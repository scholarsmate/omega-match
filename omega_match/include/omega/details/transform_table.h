#ifndef OMEGA_LIST_MATCHER__DETAILS__TRANSFORM_TABLE_H
#define OMEGA_LIST_MATCHER__DETAILS__TRANSFORM_TABLE_H

#include <stddef.h>
#include <stdint.h>

#define TRANSFORM_SKIP (-1)
#define TRANSFORM_ELIDE_SPACE (-2)

typedef struct {
  int16_t table[256]; // transform table
  uint8_t *buffer;    // transformation buffer
  uint32_t capacity;  // capacity of buffer
} transform_table_t;

int transform_init(transform_table_t *pt, int case_insensitive,
                   int ignore_punctuation, int elide_whitespace);
const uint8_t *transform_apply(transform_table_t *restrict pt,
                               const uint8_t *restrict src, uint32_t len,
                               uint32_t *restrict out_len,
                               size_t *restrict backmap);
void transform_free(transform_table_t *pt);

#endif // OMEGA_LIST_MATCHER__DETAILS__TRANSFORM_TABLE_H
