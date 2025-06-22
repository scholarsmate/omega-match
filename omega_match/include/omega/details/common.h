// common.h
// Common definitions for the OMG library

#ifndef OMEGA_LIST_MATCHER__DETAILS__COMMON_H
#define OMEGA_LIST_MATCHER__DETAILS__COMMON_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h> // for abort()

#ifdef _MSC_VER
#define strdup _strdup
#define unlink _unlink
#endif

// --- Magic and version ---
#define HEADER_MAGIC "0MGM4tCH"
#define HEADER_MAGIC_SIZE (8)
#define VERSION (1)

// --- Flags for compiled file header (32-bits) ---
#define FLAG_IGNORE_CASE (1 << 1)
#define FLAG_IGNORE_PUNCTUATION (1 << 2)
#define FLAG_ELIDE_WHITESPACE (1 << 3)

// Define the bloom filter header constant
#define BLOOM_HEADER "0MG8L0oM"
#define BLOOM_HEADER_SIZE (8)

// Define the hash table header constant
#define HASH_HEADER "0MG*H4sH"
#define HASH_HEADER_SIZE (8)

// Magic header for short matcher files
#define SHORT_MATCHER_MAGIC "0MG5HOrT"
#define SHORT_MATCHER_MAGIC_SIZE (8)

// --- Error Handling Macro ---
#define ABORT(msg)                                                             \
  do {                                                                         \
    perror(msg);                                                               \
    abort();                                                                   \
  } while (0)

static const uint8_t _punctmap[256] = {
    ['!'] = 1,  ['"'] = 1, ['#'] = 1, ['$'] = 1, ['%'] = 1, ['&'] = 1,
    ['\''] = 1, ['('] = 1, [')'] = 1, ['*'] = 1, ['+'] = 1, [','] = 1,
    ['-'] = 1,  ['.'] = 1, ['/'] = 1, [':'] = 1, [';'] = 1, ['<'] = 1,
    ['='] = 1,  ['>'] = 1, ['?'] = 1, ['@'] = 1, ['['] = 1, ['\\'] = 1,
    [']'] = 1,  ['^'] = 1, ['`'] = 1, ['{'] = 1, ['|'] = 1, ['}'] = 1,
    ['~'] = 1};
#define IS_PUNCT(c) (_punctmap[(uint8_t)(c)])

static const uint8_t _space_map[256] = {
    ['\t'] = 1, ['\n'] = 1, ['\v'] = 1, ['\f'] = 1,
    ['\r'] = 1, [' '] = 1,  ['\a'] = 1, ['\b'] = 1};
#define IS_SPACE(c) (_space_map[(uint8_t)(c)])

#ifdef _MSC_VER
#ifndef __builtin_expect
#define __builtin_expect(x, y) (x)
#endif
#define unlikely(x) (x)
#else
#ifndef unlikely
#define unlikely(x) __builtin_expect(!!(x), 0)
#endif
#endif

// --- Compiled File Header Structure ---
// Compiled header structure size is 72 bytes

#ifdef _MSC_VER
#pragma pack(push, 1)
#endif

typedef struct {
  char magic[HEADER_MAGIC_SIZE];    // "0MGM4TCH"
  uint32_t version;                 // Version number
  uint32_t flags;                   // Flags
  uint64_t pattern_store_size;      // Length of the pattern store
  uint32_t stored_pattern_count;    // Total patterns processed
  uint32_t smallest_pattern_length; // Global smallest pattern length
  uint32_t largest_pattern_length;  // Global largest pattern length
  uint32_t bloom_filter_size;       // Size of the bloom filter in bytes
  uint32_t hash_buckets_size;       // Size of the hash table in bytes
  uint32_t table_size;              // Size of the fixed-index array (power of 2)
  uint32_t num_occupied_buckets;    // Number of occupied buckets (non-empty slots)
  uint32_t min_bucket_size;         // Minimum patterns in any bucket
  uint32_t max_bucket_size;         // Maximum patterns in any bucket
  uint32_t short_matcher_size;      // Size of the short matcher (if present)
  float load_factor;                // Computed load factor = num_occupied_buckets / table_size
  float avg_bucket_size;            // Average patterns per bucket = total_patterns / num_occupied_buckets
}
#ifdef __GNUC__
__attribute__((packed))
#endif
compiled_header_t;

#ifdef _MSC_VER
#pragma pack(pop)
#endif

_Static_assert(sizeof(compiled_header_t) == 72,
               "Header must be 8-byte aligned");

// --- Bloom filter structure ---
#ifdef _MSC_VER
#pragma pack(push, 1)
typedef struct {
  char header[BLOOM_HEADER_SIZE];
  uint32_t bit_size;
  uint32_t _reserved; // For alignment
  uint64_t *bits;
} bloom_filter_t;
#pragma pack(pop)
#else
typedef struct __attribute__((packed)) {
  char header[BLOOM_HEADER_SIZE];
  uint32_t bit_size;
  uint32_t _reserved; // For alignment
  uint64_t *bits;
} bloom_filter_t;
#endif
_Static_assert(sizeof(bloom_filter_t) == 24,
               "Bloom filter must be 8-byte aligned");

// --- Pattern structure ---
#ifdef _MSC_VER
#pragma pack(push, 1)
typedef struct {
  uint64_t offset;    // Offset in the file where the pattern is stored
  uint32_t len;       // Length of the pattern
  uint32_t _reserved; // For alignment
} pattern_t;
#pragma pack(pop)
#else
typedef struct __attribute__((packed)) {
  uint64_t offset;    // Offset in the file where the pattern is stored
  uint32_t len;       // Length of the pattern
  uint32_t _reserved; // For alignment
} pattern_t;
#endif
_Static_assert(sizeof(pattern_t) == 16, "Pattern must be 8-byte aligned");

// --- Hash table entry structure ---
// An entry is considered empty if count == 0.
#ifdef _MSC_VER
#pragma pack(push, 1)
typedef struct {
  uint32_t key;        // Packed 32-bit gram key
  uint32_t dist;       // Probe distance for robin‑hood
  uint32_t count;      // Number of patterns (0 means empty)
  uint32_t capacity;   // Allocated capacity of the pattern array
  pattern_t *patterns; // Dynamic array of patterns for this key
} hash_entry_t;
#pragma pack(pop)
#else
typedef struct __attribute__((packed)) {
  uint32_t key;        // Packed 32-bit gram key
  uint32_t dist;       // Probe distance for robin‑hood
  uint32_t count;      // Number of patterns (0 means empty)
  uint32_t capacity;   // Allocated capacity of the pattern array
  pattern_t *patterns; // Dynamic array of patterns for this key
} hash_entry_t;
#endif
_Static_assert(sizeof(hash_entry_t) == 24, "Hash entry must be 8-byte aligned");

// --- Hash table structure ---
#ifdef _MSC_VER
#pragma pack(push, 1)
typedef struct {
  char header[HASH_HEADER_SIZE];
  uint32_t size;         // Table size (power of 2)
  uint32_t used;         // Number of entries with count > 0
  hash_entry_t *entries; // Array of hash_entry_t (size = table_size)
} hash_table_t;
#pragma pack(pop)
#else
typedef struct __attribute__((packed)) {
  char header[HASH_HEADER_SIZE];
  uint32_t size;         // Table size (power of 2)
  uint32_t used;         // Number of entries with count > 0
  hash_entry_t *entries; // Array of hash_entry_t (size = table_size)
} hash_table_t;
#endif
_Static_assert(sizeof(hash_table_t) == 24, "Hash table must be 8-byte aligned");

// --- Short matcher structure ---
#ifdef _MSC_VER
#pragma pack(push, 1)
typedef struct {
  uint8_t bitmap1[32];
  uint8_t bitmap2[8192];
  uint32_t len1; // Number of 1-byte patterns of size uint32_t
  uint32_t len2; // Number of 2-byte patterns of size uint32_t
  uint32_t len3; // Number of 3-byte patterns of size uint32_t
  uint32_t len4; // Number of 4-byte patterns of size uint32_t
  uint32_t *arr3;
  uint32_t *arr4;
} short_matcher_t;
#pragma pack(pop)
#else
typedef struct __attribute__((packed)) {
  uint8_t bitmap1[32];
  uint8_t bitmap2[8192];
  uint32_t len1; // Number of 1-byte patterns of size uint32_t
  uint32_t len2; // Number of 2-byte patterns of size uint32_t
  uint32_t len3; // Number of 3-byte patterns of size uint32_t
  uint32_t len4; // Number of 4-byte patterns of size uint32_t
  uint32_t *arr3;
  uint32_t *arr4;
} short_matcher_t;
#endif
_Static_assert(sizeof(short_matcher_t) == 8256,
               "Short matcher must be 8-byte aligned");

int emit_header_info(const compiled_header_t *restrict header,
                     FILE *restrict fp);

#endif // OMEGA_LIST_MATCHER__DETAILS__COMMON_H
