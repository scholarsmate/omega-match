// hash_table.c

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "omega/details/common.h"
#include "omega/details/hash.h"
#include "omega/details/hash_table.h"
#include "omega/details/util.h"

// --- Hash table parameters ---
#define INITIAL_HASH_CAPACITY (8192) // Initial capacity for the hash table
#define LOAD_FACTOR                                                            \
  (0.9) // Hash table load factor (threshold for resizing) 90% okay for "robin
        // hood" hashing

// Empty slot marker for the fixed index array
#define EMPTY_SLOT (0xFFFFFFFFu)

// Initialize the hash table
void hash_table_init(hash_table_t *restrict table, uint32_t initial_size) {
  memcpy(table->header, HASH_HEADER, HASH_HEADER_SIZE);
  // Round to the next power of two, if not already a power of two
  if (initial_size == 0) {
    initial_size = INITIAL_HASH_CAPACITY;
  }
  if ((initial_size & (initial_size - 1)) != 0) {
    initial_size = next_power_of_two(initial_size);
  }
  table->size = initial_size;
  table->used = 0;
  table->entries = calloc(table->size, sizeof(hash_entry_t));
  if (!table->entries) {
    ABORT("calloc hash table");
  }
}

// Free the hash table
void hash_table_free(const hash_table_t *restrict table) {
  for (uint32_t i = 0; i < table->size; ++i) {
    if (table->entries[i].count > 0) {
      free(table->entries[i].patterns);
    }
  }
  free(table->entries);
}

// Resize the hash table when it exceeds the load factor
void hash_table_resize(hash_table_t *restrict table) {
  const uint32_t old_size = table->size;
  hash_entry_t *old_entries = table->entries;
  const uint32_t new_size = table->size << 1;
  hash_table_t new_table;
  memcpy(new_table.header, HASH_HEADER, HASH_HEADER_SIZE);
  new_table.size = new_size;
  new_table.used = 0;
  new_table.entries = calloc(new_size, sizeof(hash_entry_t));
  if (!new_table.entries) {
    ABORT("calloc new hash table");
  }

  for (uint32_t i = 0; i < old_size; ++i) {
    if (old_entries[i].count == 0) {
      continue;
    }
    hash_entry_t entry = old_entries[i];
    entry.dist = 0;
    const uint32_t h = hash_uint32(entry.key);
    uint32_t pos = h & (new_table.size - 1);
    uint32_t d = 0;
    while (new_table.entries[pos].count != 0) {
      if (d > new_table.entries[pos].dist) {
        const hash_entry_t temp = new_table.entries[pos];
        new_table.entries[pos] = entry;
        entry = temp;
        d = entry.dist;
      }
      ++d;
      pos = (pos + 1) & (new_table.size - 1);
      entry.dist = d;
    }
    new_table.entries[pos] = entry;
    ++new_table.used;
  }
  free(old_entries);
  *table = new_table;
}

// Linear-probe the hash table to find a matching slot for 'cand'.
int probe_bucket(const uint32_t *idx_arr, const uint8_t *bucket_data,
                 const uint32_t table_mask, const uint32_t cand,
                 uint32_t *slot_offset) {
  uint32_t probe = 0;
  uint32_t idx = hash_uint32(cand) & table_mask;
  while (probe < table_mask + 1) {
    const uint32_t slot = idx_arr[idx];
    if (slot == EMPTY_SLOT) {
      return 0;
    }
    if (*(const uint32_t *)(bucket_data + slot) == cand) {
      *slot_offset = slot;
      return 1;
    }
    ++probe;
    idx = (idx + 1) & table_mask;
  }
  return 0;
}

// Insert a key-pattern pair into the hash table
void hash_table_insert(hash_table_t *restrict table, const uint32_t key,
                       const uint64_t offset, const uint32_t len) {
  if ((float)(table->used + 1) / (float)table->size > LOAD_FACTOR) {
    hash_table_resize(table);
  }

  const uint32_t h = hash_uint32(key);
  uint32_t pos = h & (table->size - 1);
  uint32_t probe_pos = pos;
  uint32_t probe_dist = 0;

  // First, search for an existing entry with the same key
  // TODO: use probe_bucket
  while (probe_dist < table->size) {
    hash_entry_t *entry = &table->entries[probe_pos];
    if (entry->count == 0) {
      break; // Found empty slot, key doesn't exist
    }
    if (entry->key == key) {
      // Found existing entry with same key, just add the pattern
      if (entry->count == entry->capacity) {
        const uint32_t newCap = entry->capacity << 1;
        pattern_t *tmp = realloc(entry->patterns, newCap * sizeof(pattern_t));
        if (!tmp) {
          ABORT("realloc pattern array");
        }
        // Zero-initialize the newly allocated memory
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
    ++probe_dist;
    probe_pos = (probe_pos + 1) & (table->size - 1);
  }

  // Key not found, create a new entry
  hash_entry_t new_entry;
  new_entry.key = key;
  new_entry.dist = 0;
  new_entry.count = 1;
  new_entry.capacity = 4;
  new_entry.patterns = calloc(1, new_entry.capacity * sizeof(pattern_t));
  if (!new_entry.patterns) {
    ABORT("calloc new entry pattern array");
  }
  new_entry.patterns[0].offset = offset;
  new_entry.patterns[0].len = len;

  // Now do robin-hood insertion to optimize the position
  pos = h & (table->size - 1);
  uint32_t distance = 0;

  while (1) {
    hash_entry_t *entry = &table->entries[pos];
    if (entry->count == 0) {
      // Found empty slot, insert the new entry
      *entry = new_entry;
      ++table->used;
      return;
    }
    if (distance > entry->dist) {
      // Swap the new entry with the existing one
      const hash_entry_t temp = *entry;
      *entry = new_entry;
      new_entry = temp;
      distance = new_entry.dist;
    }
    ++distance;
    pos = (pos + 1) & (table->size - 1);
    new_entry.dist = distance;
  }
}
