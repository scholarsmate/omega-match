// bloom.c

#include <stdlib.h>
#include <string.h>

#include "omega/details/bloom.h"
#include "omega/details/common.h"
#include "omega/details/attr.h"
#include "omega/details/hash.h"
#include "omega/details/util.h"

// Initialize bloom filter (size in bits, rounded up to multiple of 64)
void bloom_filter_init(bloom_filter_t *restrict bf, const size_t bit_size) {
  // bit_size is serialized as uint32 and must stay a power of two for the
  // mask arithmetic, so the largest usable size is 2^31 bits (2^28 bytes);
  // clamp oversized requests instead of wrapping to zero (a smaller filter
  // only raises the false-positive rate, it stays correct).
  uint64_t byte_size = (((uint64_t)bit_size + 63) & ~63ULL) >> 3;
  if (byte_size < 8) {
    byte_size = 8; // at least one 64-bit word so the mask has a home
  }
  byte_size = byte_size > (1ULL << 28)
                  ? (1ULL << 28)
                  : next_power_of_two((uint32_t)byte_size);
  bf->bit_size = (uint32_t)(byte_size << 3);
  bf->bits = calloc(bf->bit_size >> 6, sizeof(uint64_t));
  if (unlikely(!bf->bits)) {
    ABORT("bloom_filter_init: calloc");
  }
  memcpy(bf->header, BLOOM_HEADER, BLOOM_HEADER_SIZE);
}

// Get the size of the bloom filter in bytes
uint32_t bloom_filter_size(const bloom_filter_t *restrict bf) {
  return bf->bit_size >> 3;
}

// Emit the bloom filter to a file
void bloom_filter_write(const bloom_filter_t *restrict bf, FILE *restrict fp) {
  // Write the header
  fwrite(bf->header, sizeof(bf->header), 1, fp);

  // Write the bit size
  fwrite(&bf->bit_size, sizeof(bf->bit_size), 1, fp);

  // Write the bit array itself
  fwrite(bf->bits, sizeof(uint64_t), bf->bit_size >> 6, fp);
}

// Add 4-byte element to bloom filter
void bloom_filter_add(const bloom_filter_t *restrict bf, const uint32_t key) {
  const uint32_t h1 = fast_gram_hash(key);
  const uint32_t h2 = key * 0x9e3779b1;
  const uint32_t mask = bf->bit_size - 1;

  // Unrolled to eliminate loop overhead for the fixed 3 iterations
  uint32_t bit_pos = h1 & mask;
  bf->bits[bit_pos >> 6] |= 1ULL << (bit_pos & 63);
  bit_pos = (bit_pos + (h2 & mask)) & mask;
  bf->bits[bit_pos >> 6] |= 1ULL << (bit_pos & 63);
  bit_pos = (bit_pos + (h2 & mask)) & mask;
  bf->bits[bit_pos >> 6] |= 1ULL << (bit_pos & 63);
}

int bloom_filter_query(const bloom_filter_t *restrict bf, const uint32_t key) {
  const uint32_t h1 = fast_gram_hash(key);
  const uint32_t h2 = key * 0x9e3779b1U; // GOLDEN_RATIO_32
  const uint32_t mask = bf->bit_size - 1;

  const uint32_t bitpos0 = (h1 + 0 * h2) & mask;
  const uint32_t bitpos1 = (h1 + 1 * h2) & mask;
  const uint32_t bitpos2 = (h1 + 2 * h2) & mask;

  const uint32_t word0 = bitpos0 >> 6;
  const uint32_t word1 = bitpos1 >> 6;
  const uint32_t word2 = bitpos2 >> 6;

  const uint64_t m0 = 1ULL << (bitpos0 & 63);
  const uint64_t m1 = 1ULL << (bitpos1 & 63);
  const uint64_t m2 = 1ULL << (bitpos2 & 63);

  const uint64_t *restrict bits = bf->bits;

  // Prefetch next likely words to hide latency on large tables.
  // Safe, best-effort hint; cross-platform via OLM_PREFETCH.
  OLM_PREFETCH(bits + word0);
  OLM_PREFETCH(bits + word1);
  OLM_PREFETCH(bits + word2);

  // Load and test; combine loads if multiple positions share the same word.
  const uint64_t w0 = bits[word0];
  const uint64_t w1 = (word1 == word0) ? w0 : bits[word1];
  const uint64_t w2 = (word2 == word0) ? w0 : (word2 == word1) ? w1 : bits[word2];

  return ((w0 & m0) && (w1 & m1) && (w2 & m2));
}

// Destroy bloom filter and free resources
void bloom_filter_destroy(bloom_filter_t *restrict bf) {
  free(bf->bits);
  bf->bits = NULL;
  bf->bit_size = 0;
}
