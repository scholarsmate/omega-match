// util.h

#ifndef OMEGA_LIST_MATCHER__DETAILS__UTIL_H
#define OMEGA_LIST_MATCHER__DETAILS__UTIL_H

#include "attr.h"
#include <stdint.h>

// Next power of two (used for bloom and hash table sizes)
OLM_ALWAYS_INLINE static uint32_t next_power_of_two(uint32_t v) {
  if (v == 0) {
    return 1;
  }
  --v;
  v |= v >> 1;
  v |= v >> 2;
  v |= v >> 4;
  v |= v >> 8;
  v |= v >> 16;
  return v + 1;
}

OLM_ALWAYS_INLINE static uint32_t pack_gram(const uint8_t *restrict pattern) {
  return ((uint32_t)pattern[0] << 24) | ((uint32_t)pattern[1] << 16) |
         ((uint32_t)pattern[2] << 8) | ((uint32_t)pattern[3]);
}

// Helper to format uint64_t with commas into buf (must be large enough, e.g. 32
// chars)
static inline char *format_u64(uint64_t v, char *restrict buf) {
  // write digits to tmp in reverse
  char tmp[32];
  int ti = 0;
  if (v == 0) {
    tmp[ti++] = '0';
  }
  while (v) {
    tmp[ti++] = '0' + (v % 10);
    v /= 10;
  }
  // build output with commas
  const int num = ti;
  int prefix = num % 3;
  if (prefix == 0) {
    prefix = 3;
  }
  char *p = buf;
  int count = 0;
  for (int i = ti - 1; i >= 0; --i) {
    *p++ = tmp[i];
    ++count;
    if (i > 0 && count == prefix) {
      *p++ = ',';
      count = 0;
      prefix = 3;
    }
  }
  *p = '\0';
  return buf;
}

int oa_matcher_access(const char *restrict filename);

#endif // OMEGA_LIST_MATCHER__DETAILS__UTIL_H
