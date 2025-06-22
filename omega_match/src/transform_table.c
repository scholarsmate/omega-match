// transform_table.c

#include <ctype.h>
#include <stdlib.h>

#include "omega/details/common.h"
#include "omega/details/transform_table.h"

#define TOUPPER(b) (uint8_t)toupper((b))
#define INITIAL_TRANSFORM_BUFFER_SIZE                                          \
  (8192) // initial size of the transform buffer

int transform_init(transform_table_t *restrict pt, const int case_insensitive,
                   const int ignore_punctuation, const int elide_whitespace) {
  if (unlikely(!pt)) {
    ABORT("transform_init: invalid arguments");
  }

  for (int i = 0; i < 256; ++i) {
    if (elide_whitespace && IS_SPACE(i)) {
      pt->table[i] = TRANSFORM_ELIDE_SPACE;
    } else if (ignore_punctuation && IS_PUNCT(i)) {
      pt->table[i] = TRANSFORM_SKIP;
    } else if (case_insensitive) {
      pt->table[i] = TOUPPER(i);
    } else {
      pt->table[i] = (int16_t)i;
    }
  }

  pt->capacity = INITIAL_TRANSFORM_BUFFER_SIZE;
  pt->buffer = malloc(pt->capacity);
  return pt->buffer ? 0 : -1;
}

const uint8_t *transform_apply(transform_table_t *restrict pt,
                               const uint8_t *restrict src, const uint32_t len,
                               uint32_t *restrict out_len,
                               size_t *restrict backmap) {
  if (unlikely(len > pt->capacity)) {
    uint32_t new_cap = pt->capacity;
    while (new_cap < len) {
      new_cap <<= 1;
    }
    uint8_t *new_buf = realloc(pt->buffer, new_cap);
    if (unlikely(!new_buf)) {
      ABORT("realloc transform buffer");
    }
    pt->buffer = new_buf;
    pt->capacity = new_cap;
  }

  uint32_t j = 0;
  int in_space = 0;

  for (uint32_t i = 0; i < len; ++i) {
    const int16_t mapped = pt->table[src[i]];

    if (mapped == TRANSFORM_SKIP) {
      continue;
    }
    if (mapped == TRANSFORM_ELIDE_SPACE) {
      if (!in_space) {
        pt->buffer[j] = ' ';
        if (backmap) {
          backmap[j] = i;
        }
        ++j;
        in_space = 1;
      }
      continue;
    }
    pt->buffer[j] = (uint8_t)mapped;
    if (backmap) {
      backmap[j] = i;
    }
    ++j;
    in_space = 0;
  }

  // Trim trailing space if the last character is ' '
  if (j > 0 && pt->buffer[j - 1] == ' ') {
    --j;
  }

  *out_len = j;
  return pt->buffer;
}

void transform_free(transform_table_t *restrict pt) {
  free(pt->buffer);
  pt->buffer = NULL;
  pt->capacity = 0;
}
