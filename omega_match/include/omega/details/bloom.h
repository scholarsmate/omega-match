// bloom.h

#ifndef OMEGA_LIST_MATCHER__DETAILS__BLOOM_H
#define OMEGA_LIST_MATCHER__DETAILS__BLOOM_H

#include <stdint.h>
#include <stdio.h>

#include "common.h"

void bloom_filter_init(bloom_filter_t *restrict bf, size_t bit_size);
uint32_t bloom_filter_size(const bloom_filter_t *restrict bf);
void bloom_filter_write(const bloom_filter_t *restrict bf, FILE *restrict fp);
void bloom_filter_add(const bloom_filter_t *restrict bf, uint32_t key);
int bloom_filter_query(const bloom_filter_t *restrict bf, uint32_t key);
void bloom_filter_destroy(bloom_filter_t *restrict bf);

#endif // OMEGA_LIST_MATCHER__DETAILS__BLOOM_H
