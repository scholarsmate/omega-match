// hash_table.c

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "omega/details/common.h"
#include "omega/details/attr.h"
#include "omega/details/hash.h"
#include "omega/details/hash_table.h"
#include "omega/details/util.h"

#if defined(_M_X64) || defined(__x86_64__) || defined(_M_IX86) || defined(__i386__)
#include <immintrin.h>
#if defined(_MSC_VER)
#include <intrin.h>
static inline int olm_cpu_supports_avx2(void) {
  static int cached = -1;
  if (cached != -1) return cached;
  int cpuInfo[4] = {0};
  __cpuid(cpuInfo, 0);
  int maxId = cpuInfo[0];
  if (maxId < 1) { cached = 0; return cached; }
  __cpuid(cpuInfo, 1);
  const int osxsave = (cpuInfo[2] & (1 << 27)) != 0;
  const int avx = (cpuInfo[2] & (1 << 28)) != 0;
  if (!(osxsave && avx)) { cached = 0; return cached; }
  // Check XCR0 for XMM (bit 1) and YMM (bit 2)
  unsigned long long xcr0 = _xgetbv(0);
  if ((xcr0 & 0x6) != 0x6) { cached = 0; return cached; }
  // AVX2 is leaf 7 EBX bit 5
  if (maxId >= 7) {
    __cpuidex(cpuInfo, 7, 0);
    cached = ((cpuInfo[1] & (1 << 5)) != 0);
    return cached;
  }
  cached = 0;
  return cached;
}
#else
#include <cpuid.h>
static inline unsigned long long olm_read_xcr0(void) {
  unsigned int eax, edx;
  // xgetbv
  __asm__ volatile ("xgetbv" : "=a"(eax), "=d"(edx) : "c"(0));
  return ((unsigned long long)edx << 32) | eax;
}
static inline int olm_cpu_supports_avx2(void) {
  static int cached = -1;
  if (cached != -1) return cached;
  unsigned int eax, ebx, ecx, edx;
  // Get max basic CPUID leaf
  if (!__get_cpuid(0, &eax, &ebx, &ecx, &edx)) { cached = 0; return cached; }
  unsigned int maxId = eax;
  // Feature flags in leaf 1
  if (!__get_cpuid(1, &eax, &ebx, &ecx, &edx)) { cached = 0; return cached; }
  const int osxsave = (ecx & (1u << 27)) != 0;
  const int avx = (ecx & (1u << 28)) != 0;
  if (!(osxsave && avx)) { cached = 0; return cached; }
  // Verify XCR0 enables XMM (bit 1) and YMM (bit 2)
  unsigned long long xcr0 = olm_read_xcr0();
  if ((xcr0 & 0x6ULL) != 0x6ULL) { cached = 0; return cached; }
  // AVX2 is leaf 7 EBX bit 5
  if (maxId >= 7) {
    unsigned int eax7, ebx7, ecx7, edx7;
    __get_cpuid_count(7, 0, &eax7, &ebx7, &ecx7, &edx7);
    cached = ((ebx7 & (1u << 5)) != 0);
    return cached;
  }
  cached = 0;
  return cached;
}
#endif
#else
static inline int olm_cpu_supports_avx2(void) { return 0; }
#endif

// --- Hash table parameters ---
// Hash table load factor (threshold for resizing). Lower to reduce probe chain
// lengths and improve lookup performance.
#define INITIAL_HASH_CAPACITY (8192) // Initial capacity for the hash table
#define LOAD_FACTOR (0.70)

// Empty slot marker for the fixed index array
#define EMPTY_SLOT (0xFFFFFFFFu)

static inline uint32_t probe_distance(uint32_t base, uint32_t idx,
                                      uint32_t mask) {
  return (idx - base) & mask;
}

// Initialize the hash table
void hash_table_init(hash_table_t *restrict table, uint32_t initial_size) {
  memcpy(table->header, HASH_HEADER, HASH_HEADER_SIZE);
  if (initial_size == 0) {
    initial_size = INITIAL_HASH_CAPACITY;
  }
  // Round up to power-of-two
  if ((initial_size & (initial_size - 1)) != 0) {
    initial_size = (uint32_t)next_power_of_two(initial_size);
  }
  table->size = initial_size;
  table->used = 0;
  table->entries = calloc(table->size, sizeof(hash_entry_t));
  if (!table->entries) {
    ABORT("calloc hash_table entries");
  }
}

// Free hash table resources
void hash_table_free(const hash_table_t *restrict ctable) {
  hash_table_t *table = (hash_table_t *)ctable; // cast away const for free
  if (!table || !table->entries) return;
  for (uint32_t i = 0; i < table->size; ++i) {
    if (table->entries[i].count > 0) {
      free(table->entries[i].patterns);
      table->entries[i].patterns = NULL;
      table->entries[i].count = 0;
      table->entries[i].capacity = 0;
    }
  }
  free(table->entries);
  table->entries = NULL;
  table->size = 0;
  table->used = 0;
}

// Resize and rehash using robin-hood placement
void hash_table_resize(hash_table_t *restrict table) {
  const uint32_t old_size = table->size;
  const uint32_t new_size = (old_size == 0) ? INITIAL_HASH_CAPACITY : (old_size << 1);
  hash_entry_t *new_entries = calloc(new_size, sizeof(hash_entry_t));
  if (!new_entries) {
    ABORT("calloc hash_table resize");
  }
  const uint32_t new_mask = new_size - 1;
  // Move all existing entries
  for (uint32_t i = 0; i < old_size; ++i) {
    hash_entry_t moving = table->entries[i];
    if (moving.count == 0) continue;
    uint32_t base = hash_uint32(moving.key) & new_mask;
    uint32_t pos = base;
    uint32_t dist = 0;
    for (;;) {
      hash_entry_t *dst = &new_entries[pos];
      if (dst->count == 0) {
        // place here
        *dst = moving;
        dst->dist = dist;
        break;
      }
      if (dist > dst->dist) {
        // swap and continue with displaced entry
        hash_entry_t tmp = *dst;
        *dst = moving;
        dst->dist = dist;
        moving = tmp;
        base = hash_uint32(moving.key) & new_mask;
        dist = probe_distance(base, pos, new_mask);
      }
      pos = (pos + 1) & new_mask;
      ++dist;
    }
  }
  free(table->entries);
  table->entries = new_entries;
  table->size = new_size;
  // used count remains the same
}

#if defined(_M_ARM64) || defined(__aarch64__) || defined(__ARM_NEON)
#include <arm_neon.h>
#endif

// Probe the compiled-time index/bucket arrays for a candidate key
int probe_bucket(const uint8_t *restrict control_bytes,
                 const uint32_t *restrict idx_arr,
                 const uint8_t *restrict bucket_data, uint32_t table_mask,
                 uint32_t cand, uint32_t *slot_offset) {
  uint32_t idx = hash_uint32(cand) & table_mask;
  const uint32_t size = table_mask + 1;
  if (control_bytes) {
#if defined(_M_X64) || defined(__x86_64__) || defined(_M_IX86) || defined(__i386__)
    const uint8_t cand_fp = (uint8_t)((hash_uint32(cand) >> 24) | 1u);
  // Use AVX2 path only if the compiler supports AVX2 intrinsics; otherwise
  // fall back to the SSE2 path. Runtime check still avoids executing AVX2
  // on unsupported CPUs when compiled with AVX2.
#if defined(__AVX2__) || defined(_MSC_VER)
  if (olm_cpu_supports_avx2()) {
      const __m256i rep32 = _mm256_set1_epi8((char)cand_fp);
      const __m256i zero32 = _mm256_setzero_si256();
      uint32_t probed = 0;
      while (probed < size) {
        const uint32_t contiguous = (idx + 32 <= size) ? 32u : (size - idx);
        if (contiguous < 32) {
          for (uint32_t k = 0; k < contiguous && probed < size; ++k) {
            const uint8_t c = control_bytes[idx];
            if (c == 0) return 0;
            if (c == cand_fp) {
              const uint32_t slot = idx_arr[idx];
              if (slot == EMPTY_SLOT) return 0;
              const uint32_t key_at_slot = *(const uint32_t *)(bucket_data + slot);
              if (key_at_slot == cand) { *slot_offset = slot; return 1; }
            }
            idx = (idx + 1) & table_mask; ++probed;
          }
          continue;
        }
        const __m256i block = _mm256_loadu_si256((const __m256i *)(control_bytes + idx));
        const __m256i empties = _mm256_cmpeq_epi8(block, zero32);
        const __m256i matches = _mm256_cmpeq_epi8(block, rep32);
        const int empties_mask = _mm256_movemask_epi8(empties);
        const int matches_mask = _mm256_movemask_epi8(matches);
        if (empties_mask == 0 && matches_mask == 0) { idx = (idx + 32) & table_mask; probed += 32; continue; }
        for (uint32_t b = 0; b < 32; ++b) {
          const int bit = 1 << b;
          if (empties_mask & bit) return 0;
          if (matches_mask & bit) {
            const uint32_t pos = (idx + b) & table_mask;
            const uint32_t slot = idx_arr[pos];
            if (slot == EMPTY_SLOT) return 0;
            const uint32_t key_at_slot = *(const uint32_t *)(bucket_data + slot);
            if (key_at_slot == cand) { *slot_offset = slot; return 1; }
          }
        }
        idx = (idx + 32) & table_mask; probed += 32;
      }
    } else
#endif
    {
      const __m128i rep16 = _mm_set1_epi8((char)cand_fp);
      const __m128i zero16 = _mm_setzero_si128();
      uint32_t probed = 0;
      while (probed < size) {
        const uint32_t contiguous = (idx + 16 <= size) ? 16u : (size - idx);
        if (contiguous < 16) {
          for (uint32_t k = 0; k < contiguous && probed < size; ++k) {
            const uint8_t c = control_bytes[idx];
            if (c == 0) return 0;
            if (c == cand_fp) {
              const uint32_t slot = idx_arr[idx];
              if (slot == EMPTY_SLOT) return 0;
              const uint32_t key_at_slot = *(const uint32_t *)(bucket_data + slot);
              if (key_at_slot == cand) { *slot_offset = slot; return 1; }
            }
            idx = (idx + 1) & table_mask; ++probed;
          }
          continue;
        }
        const __m128i block = _mm_loadu_si128((const __m128i *)(control_bytes + idx));
        const __m128i empties = _mm_cmpeq_epi8(block, zero16);
        const __m128i matches = _mm_cmpeq_epi8(block, rep16);
        const int empties_mask = _mm_movemask_epi8(empties);
        const int matches_mask = _mm_movemask_epi8(matches);
        if ((empties_mask | matches_mask) == 0) { idx = (idx + 16) & table_mask; probed += 16; continue; }
        for (uint32_t b = 0; b < 16; ++b) {
          const int bit = 1 << b;
          if (empties_mask & bit) return 0;
          if (matches_mask & bit) {
            const uint32_t pos = (idx + b) & table_mask;
            const uint32_t slot = idx_arr[pos];
            if (slot == EMPTY_SLOT) return 0;
            const uint32_t key_at_slot = *(const uint32_t *)(bucket_data + slot);
            if (key_at_slot == cand) { *slot_offset = slot; return 1; }
          }
        }
        idx = (idx + 16) & table_mask; probed += 16;
      }
    }
    return 0;
#elif defined(_M_ARM64) || defined(__aarch64__) || defined(__ARM_NEON)
    {
      const uint8_t cand_fp = (uint8_t)((hash_uint32(cand) >> 24) | 1u);
      const uint8x16_t rep16 = vdupq_n_u8(cand_fp);
      const uint8x16_t zero16 = vdupq_n_u8(0);
      uint32_t probed = 0;
      while (probed < size) {
        const uint32_t contiguous = ((idx + 16) <= size) ? 16u : (size - idx);
        if (contiguous < 16) {
          for (uint32_t k = 0; k < contiguous && probed < size; ++k) {
            const uint8_t c = control_bytes[idx];
            if (c == 0) return 0;
            if (c == cand_fp) {
              const uint32_t slot = idx_arr[idx];
              if (slot == EMPTY_SLOT) return 0;
              const uint32_t key_at_slot = *(const uint32_t *)(bucket_data + slot);
              if (key_at_slot == cand) { *slot_offset = slot; return 1; }
            }
            idx = (idx + 1) & table_mask; ++probed;
          }
          continue;
        }
        const uint8x16_t block = vld1q_u8(control_bytes + idx);
        const uint8x16_t empties = vceqq_u8(block, zero16);
        const uint8x16_t matches = vceqq_u8(block, rep16);
        uint8_t ebuf[16], mbuf[16];
        vst1q_u8(ebuf, empties);
        vst1q_u8(mbuf, matches);
        int any = 0;
        for (uint32_t b = 0; b < 16; ++b) {
          if (ebuf[b]) return 0;
          if (mbuf[b]) {
            const uint32_t pos = (idx + b) & table_mask;
            const uint32_t slot = idx_arr[pos];
            if (slot == EMPTY_SLOT) return 0;
            const uint32_t key_at_slot = *(const uint32_t *)(bucket_data + slot);
            if (key_at_slot == cand) { *slot_offset = slot; return 1; }
            any = 1;
          }
        }
        if (!any) { idx = (idx + 16) & table_mask; probed += 16; continue; }
        idx = (idx + 16) & table_mask; probed += 16;
      }
    }
    return 0;
#else
    // Scalar 16-byte blocks using bit tricks
    const uint8_t cand_fp = (uint8_t)((hash_uint32(cand) >> 24) | 1u);
    const uint64_t rep = 0x0101010101010101ULL * cand_fp;
    uint32_t probed = 0;
    while (probed < size) {
      const uint32_t contiguous = (idx + 16 <= size) ? 16u : (size - idx);
      if (contiguous < 16) {
        for (uint32_t k = 0; k < contiguous && probed < size; ++k) {
          const uint8_t c = control_bytes[idx];
          if (c == 0) return 0;
          if (c == cand_fp) {
            const uint32_t slot = idx_arr[idx];
            if (slot == EMPTY_SLOT) return 0;
            const uint32_t key_at_slot = *(const uint32_t *)(bucket_data + slot);
            if (key_at_slot == cand) { *slot_offset = slot; return 1; }
          }
          idx = (idx + 1) & table_mask; ++probed;
        }
        continue;
      }
      uint64_t block1, block2;
      memcpy(&block1, control_bytes + idx, sizeof(block1));
      memcpy(&block2, control_bytes + idx + 8, sizeof(block2));
      const uint64_t z1 = (block1 - 0x0101010101010101ULL) & (~block1) & 0x8080808080808080ULL;
      const uint64_t z2 = (block2 - 0x0101010101010101ULL) & (~block2) & 0x8080808080808080ULL;
      const uint64_t x1 = block1 ^ rep;
      const uint64_t x2 = block2 ^ rep;
      const uint64_t m1 = (x1 - 0x0101010101010101ULL) & (~x1) & 0x8080808080808080ULL;
      const uint64_t m2 = (x2 - 0x0101010101010101ULL) & (~x2) & 0x8080808080808080ULL;
      if ((z1 | m1 | z2 | m2) == 0) { idx = (idx + 16) & table_mask; probed += 16; continue; }
      for (uint32_t b = 0; b < 16; ++b) {
        const uint64_t bit = 0x80ULL << ((b & 7) * 8);
        const int in_second = (b >= 8);
        if ((in_second ? (z2 & bit) : (z1 & bit))) return 0;
        if ((in_second ? (m2 & bit) : (m1 & bit))) {
          const uint32_t pos = (idx + b) & table_mask;
          const uint32_t slot = idx_arr[pos];
          if (slot == EMPTY_SLOT) return 0;
          const uint32_t key_at_slot = *(const uint32_t *)(bucket_data + slot);
          if (key_at_slot == cand) { *slot_offset = slot; return 1; }
        }
      }
      idx = (idx + 16) & table_mask; probed += 16;
    }
    return 0;
#endif
  }

  // Backward-compatible scalar probe when no control bytes are available
  uint32_t probed = 0;
  while (probed < size) {
    const uint32_t slot = idx_arr[idx];
    if (slot == EMPTY_SLOT) return 0;
    const uint32_t key_at_slot = *(const uint32_t *)(bucket_data + slot);
    if (key_at_slot == cand) { *slot_offset = slot; return 1; }
    idx = (idx + 1) & table_mask;
    ++probed;
  }
  return 0;
}

// Insert a key-pattern pair into the hash table
void hash_table_insert(hash_table_t *restrict table, const uint32_t key,
                       const uint64_t offset, const uint32_t len) {
  if ((float)(table->used + 1) / (float)table->size > LOAD_FACTOR) {
    hash_table_resize(table);
  }

  const uint32_t mask = table->size - 1;
  const uint32_t base = hash_uint32(key) & mask;

  uint32_t pos = base;
  uint32_t dist = 0;
  uint32_t insert_pos = UINT32_MAX; // first position where dist > entry->dist
  uint32_t found_pos = UINT32_MAX;  // position of existing key if found
  uint32_t empty_pos = UINT32_MAX;  // position of first empty slot (end of cluster)

  // Single pass: look for existing key while locating ideal insert position
  while (dist < table->size) {
    hash_entry_t *entry = &table->entries[pos];

    if (entry->count == 0) {
      empty_pos = pos;
      break; // end of probe cluster
    }

    if (entry->key == key) {
      found_pos = pos;
      break;
    }

    if (insert_pos == UINT32_MAX && dist > entry->dist) {
      insert_pos = pos; // robin-hood preferred position
    }

    ++dist;
    pos = (pos + 1) & mask;
  }

  // If key exists, append pattern and return
  if (found_pos != UINT32_MAX) {
    hash_entry_t *entry = &table->entries[found_pos];
    if (entry->count == entry->capacity) {
      const uint32_t newCap = entry->capacity ? (entry->capacity << 1) : 4;
      pattern_t *tmp = realloc(entry->patterns, newCap * sizeof(pattern_t));
      if (!tmp) {
        ABORT("realloc pattern array");
      }
      // Zero-initialize the newly allocated region
      memset(tmp + entry->capacity, 0,
             (newCap - entry->capacity) * sizeof(pattern_t));
      entry->patterns = tmp;
      entry->capacity = newCap;
    }
    entry->patterns[entry->count].offset = offset;
    entry->patterns[entry->count].len = len;
    ++entry->count;
    return;
  }

  // No existing key; we must insert a new entry
  // Determine actual insertion index
  if (insert_pos == UINT32_MAX) {
    // We never found a position with dist > entry->dist; insert at empty_pos
    insert_pos = empty_pos;
  }

  // Prepare new entry
  hash_entry_t new_entry;
  new_entry.key = key;
  new_entry.count = 1;
  new_entry.capacity = 4;
  new_entry.patterns = calloc(1, new_entry.capacity * sizeof(pattern_t));
  if (!new_entry.patterns) {
    ABORT("calloc new entry pattern array");
  }
  new_entry.patterns[0].offset = offset;
  new_entry.patterns[0].len = len;
  new_entry.dist = probe_distance(base, insert_pos, mask);

  // If insert at empty_pos, just place and return
  if (insert_pos == empty_pos) {
    table->entries[insert_pos] = new_entry;
    ++table->used;
    return;
  }

  // Shift entries forward from empty_pos back to insert_pos to make room
  uint32_t cur = empty_pos;
  while (cur != insert_pos) {
    const uint32_t prev = (cur - 1) & mask;
    table->entries[cur] = table->entries[prev];
    // Increment probe distance since we moved it one slot forward
    if (table->entries[cur].count != 0) {
      ++table->entries[cur].dist;
    }
    cur = prev;
  }

  // Place new entry
  table->entries[insert_pos] = new_entry;
  ++table->used;
}
