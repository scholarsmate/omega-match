#ifndef OMEGA_REWRITE_H
#define OMEGA_REWRITE_H

#include <stddef.h>
#include <stdint.h>

#include "omega/reactor.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct omega_rewrite_script_struct omega_rewrite_script_t;

typedef enum {
  OMEGA_REWRITE_SCRIPT_DELETE = 1,
  OMEGA_REWRITE_SCRIPT_INSERT = 2,
  OMEGA_REWRITE_SCRIPT_OVERWRITE = 3,
} omega_rewrite_script_op_kind_t;

typedef struct {
  size_t offset;
  size_t length;
  uint64_t rule_id;
  uint32_t kind;       // omega_rewrite_script_op_kind_t
  const uint8_t *data; // script-owned payload for INSERT/OVERWRITE
  size_t data_len;
} omega_rewrite_script_op_t;

/**
 * Lower a rewrite plan into a replayable edit script.
 * Returns NULL on invalid overlapping edits or allocation failure.
 * SIDE_EFFECT actions are ignored by the edit script.
 */
omega_rewrite_script_t *
omega_rewrite_script_create(const omega_rewrite_plan_t *restrict plan);

/**
 * Destroy a rewrite script.
 * Returns 0 on success, -1 on invalid input.
 */
int omega_rewrite_script_destroy(omega_rewrite_script_t *restrict script);

/**
 * Get the number of low-level edit operations in the script.
 */
size_t omega_rewrite_script_get_op_count(
    const omega_rewrite_script_t *restrict script);

/**
 * Get the script-owned low-level operation array.
 */
const omega_rewrite_script_op_t *
omega_rewrite_script_get_ops(const omega_rewrite_script_t *restrict script);

/**
 * Apply a rewrite script to an in-memory input buffer.
 * On success, *output points to a newly allocated buffer owned by the caller.
 * Use omega_rewrite_bytes_destroy() to free it.
 * Returns 0 on success, -1 on failure.
 */
int omega_rewrite_script_apply_bytes(
    const omega_rewrite_script_t *restrict script,
    const uint8_t *restrict input, size_t input_len, uint8_t **restrict output,
    size_t *restrict output_len);

/**
 * Free a byte buffer returned by omega_rewrite_script_apply_bytes().
 */
void omega_rewrite_bytes_destroy(uint8_t *bytes);

/**
 * Return non-zero when the OmegaEdit file adapter is available in this build.
 */
int omega_rewrite_script_omega_edit_available(void);

/**
 * Apply a rewrite script to a file via OmegaEdit and save the edited output.
 * Returns 0 on success, -1 on failure or when the adapter is unavailable.
 */
int omega_rewrite_script_apply_omega_edit(
    const omega_rewrite_script_t *restrict script,
    const char *restrict input_file, const char *restrict output_file);

#ifdef __cplusplus
}
#endif

#endif // OMEGA_REWRITE_H
