// hash.h

#ifndef OMEGA_LIST_MATCHER__DETAILS__HASH_H
#define OMEGA_LIST_MATCHER__DETAILS__HASH_H

#include "attr.h"
#include <stdint.h>

// --- Hash functions ---
#define FNV1A_PRIME (0x01000193)

// Based on murmur3 finalizer
OLM_ALWAYS_INLINE static uint32_t fast_gram_hash(uint32_t gram) {
  gram ^= gram >> 16;
  gram *= 0x85ebca6b;
  gram ^= gram >> 13;
  gram *= 0xc2b2ae35;
  gram ^= gram >> 16;
  return gram;
}

// Hash function for 32-bit integers (inlined)
OLM_ALWAYS_INLINE static uint32_t hash_uint32(const uint32_t x) {
  return (x ^ 0x9e3779b9) * FNV1A_PRIME;
}

// Hash function for memory buffers of arbitrary length (inlined)
OLM_ALWAYS_INLINE static uint32_t hash_buf(const uint8_t *restrict buf,
                                           const size_t len) {
  // FNV-1a for arbitrary length
  uint32_t hash = 2166136261u;
  for (size_t i = 0; i < len; ++i) {
    hash ^= buf[i];
    hash *= 16777619u;
  }
  return hash;
}

#endif // OMEGA_LIST_MATCHER__DETAILS__HASH_H
