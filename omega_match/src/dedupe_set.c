// dedupe_set.c

#include "omega/details/dedupe_set.h"
#include "omega/details/common.h"
#include "omega/details/hash.h"
#include <stdlib.h>
#include <string.h>

#define INITIAL_DEDUP_CAPACITY (8192)
#define DEDUP_LOAD_FACTOR (0.9f)

typedef struct {
  uint32_t hash; // hash of the normalized pattern
  uint32_t len;  // pattern length
  uint8_t *buf;  // malloc'ed normalized pattern
  uint32_t dist; // robin hood distance
} dedup_entry_t;

struct dedup_set {
  dedup_entry_t *entries;
  uint32_t size; // number of slots
  uint32_t used; // number of used slots
};

dedup_set_t *dedup_set_create(void) {
  dedup_set_t *set = calloc(1, sizeof(dedup_set_t));
  if (!set) {
    ABORT("calloc dedup_set");
  }

  set->size = INITIAL_DEDUP_CAPACITY;
  set->entries = calloc(set->size, sizeof(dedup_entry_t));
  if (!set->entries) {
    ABORT("calloc dedup_set entries");
  }
  return set;
}

void dedup_set_destroy(dedup_set_t *restrict set) {
  if (!set) {
    return;
  }
  for (uint32_t i = 0; i < set->size; ++i) {
    if (set->entries[i].buf) {
      free(set->entries[i].buf);
    }
  }
  free(set->entries);
  free(set);
}

static void dedup_set_resize(dedup_set_t *restrict set) {
  const uint32_t old_size = set->size;
  dedup_entry_t *old_entries = set->entries;

  set->size = old_size << 1; // double the size (next power of two)
  set->used = 0;
  set->entries = calloc(set->size, sizeof(dedup_entry_t));
  if (!set->entries) {
    ABORT("calloc dedup_set resize");
  }

  for (uint32_t i = 0; i < old_size; ++i) {
    dedup_entry_t *old = &old_entries[i];
    if (!old->buf) {
      continue;
    }

    // Re-insert
    uint32_t pos = old->hash & (set->size - 1);
    uint32_t dist = 0;
    while (set->entries[pos].buf) {
      if (dist > set->entries[pos].dist) {
        // Swap
        dedup_entry_t temp = set->entries[pos];
        set->entries[pos] = *old;
        *old = temp;
        dist = old->dist;
      }
      ++dist;
      pos = (pos + 1) & (set->size - 1);
      old->dist = dist;
    }
    set->entries[pos] = *old;
    ++set->used;
  }

  free(old_entries);
}

int dedup_set_add(dedup_set_t *restrict set, const uint8_t *restrict buf,
                  const size_t len) {
  if ((float)(set->used + 1) / (float)set->size > DEDUP_LOAD_FACTOR) {
    dedup_set_resize(set);
  }

  const uint32_t h = hash_buf(buf, len);
  uint32_t pos = h & (set->size - 1);
  uint32_t distance = 0;

  while (1) {
    dedup_entry_t *entry = &set->entries[pos];
    if (!entry->buf) {
      // Insert new
      entry->hash = h;
      entry->len = (uint32_t)len;
      entry->buf = malloc(len);
      if (!entry->buf) {
        ABORT("malloc dedup pattern buf");
      }
      memcpy(entry->buf, buf, len);
      entry->dist = distance;
      ++set->used;
      return 1;
    }

    if (entry->hash == h && entry->len == len &&
        memcmp(entry->buf, buf, len) == 0) {
      return 0; // already exists
    }

    if (distance > entry->dist) {
      // Robin hood swapping
      const dedup_entry_t temp = *entry;
      entry->hash = h;
      entry->len = (uint32_t)len;
      entry->buf = malloc(len);
      if (!entry->buf) {
        ABORT("malloc dedup pattern buf (robin hood)");
      }
      memcpy(entry->buf, buf, len);
      entry->dist = distance;
      *entry = temp;
      distance = entry->dist;
    }

    ++distance;
    pos = (pos + 1) & (set->size - 1);
  }
}
