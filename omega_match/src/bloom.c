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

  // Version 4 compiled files keep the uint64_t bit array naturally aligned.
  // The compiled header and pattern store both end on an 8-byte boundary, so
  // this reserved word moves the array from offset 4 mod 8 to offset 0 mod 8.
  // Older readers reject newer format versions; the v4 reader still handles
  // the historical v1-v3 layout without this word.
  const uint32_t reserved = 0;
  fwrite(&reserved, sizeof(reserved), 1, fp);

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
  const uint32_t mask = bf->bit_size - 1;
  const uint64_t *restrict bits = bf->bits;

  // Test the sparse filter one bit at a time. Most candidate grams fail the
  // first bit, so eagerly calculating and loading all three random words adds
  // two unnecessary cache accesses to the overwhelmingly common miss path.
  uint32_t bit_pos = h1 & mask;
  if ((bits[bit_pos >> 6] & (1ULL << (bit_pos & 63))) == 0) {
    return 0;
  }

  const uint32_t h2 = key * 0x9e3779b1U; // GOLDEN_RATIO_32
  bit_pos = (bit_pos + (h2 & mask)) & mask;
  if ((bits[bit_pos >> 6] & (1ULL << (bit_pos & 63))) == 0) {
    return 0;
  }

  bit_pos = (bit_pos + (h2 & mask)) & mask;
  return (bits[bit_pos >> 6] & (1ULL << (bit_pos & 63))) != 0;
}

// Destroy bloom filter and free resources
void bloom_filter_destroy(bloom_filter_t *restrict bf) {
  free(bf->bits);
  bf->bits = NULL;
  bf->bit_size = 0;
}
