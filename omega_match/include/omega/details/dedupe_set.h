#ifndef OMEGA_LIST_MATCHER__DETAILS__DEDUPE_SET_H
#define OMEGA_LIST_MATCHER__DETAILS__DEDUPE_SET_H

#include <stddef.h> // for size_t
#include <stdint.h>

// Opaque deduplication set
typedef struct dedup_set dedup_set_t;

// Create a new dedup set
dedup_set_t *dedup_set_create(void);

// Free the dedup set
void dedup_set_destroy(dedup_set_t *restrict set);

// Insert a memory buffer into the dedup set
// Returns 0 if the buffer content already exists, 1 if it was added
int dedup_set_add(dedup_set_t *restrict set, const uint8_t *restrict buf,
                  size_t len);

#endif // OMEGA_LIST_MATCHER__DETAILS__DEDUPE_SET_H
