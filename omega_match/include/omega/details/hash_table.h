// hash_table.h

#ifndef OMEGA_LIST_MATCHER__DETAILS__HASH_TABLE_H
#define OMEGA_LIST_MATCHER__DETAILS__HASH_TABLE_H

#include <stdint.h>

#include "../include/omega/details/common.h"

void hash_table_init(hash_table_t *restrict table, uint32_t initial_size);
void hash_table_free(const hash_table_t *restrict table);
void hash_table_resize(hash_table_t *restrict table);
int probe_bucket(const uint32_t *restrict idx_arr,
                 const uint8_t *restrict bucket_data, uint32_t table_mask,
                 uint32_t cand, uint32_t *slot_offset);
void hash_table_insert(hash_table_t *restrict table, uint32_t key,
                       uint64_t offset, uint32_t len);

#endif // OMEGA_LIST_MATCHER__DETAILS__HASH_TABLE_H
