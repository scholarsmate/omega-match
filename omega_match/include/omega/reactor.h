#ifndef OMEGA_REACTOR_H
#define OMEGA_REACTOR_H

#include <stddef.h>
#include <stdint.h>

#include "omega/list_matcher.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct omega_builtin_reactor_struct omega_builtin_reactor_t;
typedef struct omega_native_reactor_struct omega_native_reactor_t;
typedef struct omega_native_reactor_builder_struct
    omega_native_reactor_builder_t;
typedef struct omega_rewrite_plan_struct omega_rewrite_plan_t;

typedef int (*omega_native_reactor_handler_fn)(
    omega_rewrite_plan_t *plan, const omega_match_result_t *match,
    void *handler_ctx);

typedef int (*omega_native_reactor_plugin_init_fn)(
    omega_native_reactor_builder_t *builder, void *plugin_ctx);

typedef enum {
  OMEGA_REWRITE_NOOP = 0,
  OMEGA_REWRITE_OVERWRITE = 1,
  OMEGA_REWRITE_REPLACE = 2,
  OMEGA_REWRITE_INSERT = 3,
  OMEGA_REWRITE_DELETE = 4,
  OMEGA_REWRITE_SIDE_EFFECT = 5,
} omega_rewrite_action_kind_t;

typedef enum {
  OMEGA_REACTOR_BUILTIN_UPPER = 1,
  OMEGA_REACTOR_BUILTIN_LOWER = 2,
  OMEGA_REACTOR_BUILTIN_REDACT = 3,
  OMEGA_REACTOR_BUILTIN_UUID = 4,
} omega_builtin_reactor_opcode_t;

typedef struct {
  size_t start;                      // Inclusive original-input offset
  size_t end;                        // Exclusive original-input offset
  uint64_t rule_id;                  // Match key / rule ID
  omega_rewrite_action_kind_t kind;  // Action kind
  const uint8_t *data;               // Plan-owned replacement payload
  size_t data_len;                   // Replacement payload length
} omega_rewrite_action_t;

typedef struct {
  uint64_t rule_id;                  // Match key / rule ID to react to
  uint32_t opcode;                   // omega_builtin_reactor_opcode_t
  uint8_t redact_byte;               // Fill byte used by REDACT
  uint8_t _reserved[3];
} omega_builtin_reactor_rule_t;

typedef struct {
  uint64_t rule_id;                       // Match key / rule ID to react to
  omega_native_reactor_handler_fn handler; // Native function to run
  void *handler_ctx;                     // Optional caller/plugin context
} omega_native_reactor_rule_t;

/**
 * Create a builtin reactor from a set of rule IDs and builtin opcodes.
 * Rules are copied internally and may be freed by the caller after return.
 * Duplicate rule IDs, invalid opcodes, or a rule ID of 0 cause failure and
 * return NULL. Rule ID 0 is reserved: matches from patterns compiled without
 * a key carry key 0 and must never dispatch to a rule.
 */
omega_builtin_reactor_t *omega_builtin_reactor_create(
    const omega_builtin_reactor_rule_t *restrict rules, size_t rule_count);

/**
 * Destroy a builtin reactor.
 * Returns 0 on success, -1 on invalid input.
 */
int omega_builtin_reactor_destroy(
    omega_builtin_reactor_t *restrict reactor);

/**
 * Build a rewrite plan from an existing native match result stream.
 * Unknown rule IDs are ignored. Returned plan must be destroyed by the caller.
 */
omega_rewrite_plan_t *omega_builtin_reactor_plan_matches(
    const omega_builtin_reactor_t *restrict reactor,
    const omega_match_results_t *restrict results);

/**
 * Convenience wrapper: run the matcher and immediately build a rewrite plan.
 * Returned plan must be destroyed by the caller.
 */
omega_rewrite_plan_t *omega_builtin_reactor_plan(
    const omega_builtin_reactor_t *restrict reactor,
    const omega_list_matcher_t *restrict matcher,
    const uint8_t *restrict haystack, size_t haystack_size, int no_overlap,
    int longest_only, int word_boundary, int word_prefix, int word_suffix,
    int line_start, int line_end);

/**
 * Create an empty native reactor builder for manual registration or plugin
 * loading. The builder remains mutable until omega_native_reactor_builder_build
 * succeeds.
 */
omega_native_reactor_builder_t *omega_native_reactor_builder_create(void);

/**
 * Destroy a native reactor builder and unload any libraries loaded into it.
 * Returns 0 on success, -1 on invalid input.
 */
int omega_native_reactor_builder_destroy(
    omega_native_reactor_builder_t *restrict builder);

/**
 * Add a native rule binding to the builder.
 * Duplicate rule IDs, NULL handlers, or a rule ID of 0 cause failure and
 * return -1. Rule ID 0 is reserved: matches from patterns compiled without a
 * key carry key 0 and must never dispatch to a rule.
 */
int omega_native_reactor_builder_add_rule(
    omega_native_reactor_builder_t *restrict builder, uint64_t rule_id,
    omega_native_reactor_handler_fn handler, void *handler_ctx);

/**
 * Load a plugin shared library into the builder and invoke its init function.
 * If init_symbol is NULL or empty, "omega_reactor_plugin_init" is used.
 * Plugin-added rules are rolled back if loading or initialization fails.
 */
int omega_native_reactor_builder_load_plugin(
    omega_native_reactor_builder_t *restrict builder,
    const char *restrict library_path, const char *restrict init_symbol,
    void *plugin_ctx);

/**
 * Build an immutable native reactor with a dense runtime dispatch table.
 * The returned reactor owns any loaded plugin handles and must be destroyed by
 * the caller. On success, the builder is reset to an empty state.
 *
 * Native reactors optimize for runtime dispatch and therefore expect dense rule
 * IDs. Extremely large sparse rule IDs are rejected to avoid excessive table
 * allocations.
 */
omega_native_reactor_t *omega_native_reactor_builder_build(
    omega_native_reactor_builder_t *restrict builder);

/**
 * Convenience constructor for a native reactor from an in-memory rule array.
 * Rules are copied internally. Duplicate rule IDs or NULL handlers cause
 * failure and return NULL.
 */
omega_native_reactor_t *omega_native_reactor_create(
    const omega_native_reactor_rule_t *restrict rules, size_t rule_count);

/**
 * Destroy a native reactor and unload any plugin libraries it owns.
 * Returns 0 on success, -1 on invalid input.
 */
int omega_native_reactor_destroy(omega_native_reactor_t *restrict reactor);

/**
 * Build a rewrite plan from an existing match stream using native handlers.
 * Unknown rule IDs are ignored. Returned plan must be destroyed by the caller.
 */
omega_rewrite_plan_t *omega_native_reactor_plan_matches(
    const omega_native_reactor_t *restrict reactor,
    const omega_match_results_t *restrict results);

/**
 * Convenience wrapper: run the matcher and immediately build a rewrite plan
 * using native handlers. Returned plan must be destroyed by the caller.
 */
omega_rewrite_plan_t *omega_native_reactor_plan(
    const omega_native_reactor_t *restrict reactor,
    const omega_list_matcher_t *restrict matcher,
    const uint8_t *restrict haystack, size_t haystack_size, int no_overlap,
    int longest_only, int word_boundary, int word_prefix, int word_suffix,
    int line_start, int line_end);

/**
 * Append a single action to a rewrite plan.
 * The payload bytes are copied into plan-owned storage.
 * Returns 0 on success, -1 on invalid input or allocation failure.
 */
int omega_rewrite_plan_add_action(omega_rewrite_plan_t *restrict plan,
                                  size_t start, size_t end, uint64_t rule_id,
                                  omega_rewrite_action_kind_t kind,
                                  const uint8_t *data, size_t data_len);

/**
 * Create an empty rewrite plan that can be populated incrementally.
 * Returned plan must be destroyed by the caller.
 */
omega_rewrite_plan_t *omega_rewrite_plan_create(void);

/**
 * Get the number of actions in a rewrite plan.
 */
size_t omega_rewrite_plan_get_action_count(
    const omega_rewrite_plan_t *restrict plan);

/**
 * Get a pointer to the plan-owned action array.
 * The returned pointer remains valid until omega_rewrite_plan_destroy().
 */
const omega_rewrite_action_t *omega_rewrite_plan_get_actions(
    const omega_rewrite_plan_t *restrict plan);

/**
 * Destroy a rewrite plan.
 * Returns 0 on success, -1 on invalid input.
 */
int omega_rewrite_plan_destroy(omega_rewrite_plan_t *restrict plan);

#ifdef __cplusplus
}
#endif

#endif // OMEGA_REACTOR_H
