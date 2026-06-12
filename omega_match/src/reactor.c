#include <ctype.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "omega/details/common.h"
#include "omega/reactor.h"

#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

typedef struct {
  omega_native_reactor_handler_fn handler;
  void *handler_ctx;
} native_dispatch_entry_t;

#define OMEGA_NATIVE_REACTOR_MAX_DENSE_RULE_ID 1048575ULL

struct omega_builtin_reactor_struct {
  omega_builtin_reactor_rule_t *rules;
  size_t rule_count;
};

struct omega_native_reactor_struct {
  native_dispatch_entry_t *dispatch;
  size_t dispatch_size;
  void **plugin_handles;
  size_t plugin_count;
};

struct omega_native_reactor_builder_struct {
  omega_native_reactor_rule_t *rules;
  size_t rule_count;
  size_t rule_capacity;
  void **plugin_handles;
  size_t plugin_count;
  size_t plugin_capacity;
};

struct omega_rewrite_plan_struct {
  omega_rewrite_action_t *actions;
  size_t action_count;
  size_t action_capacity;
  uint8_t *data_blob;
  size_t data_blob_len;
  size_t data_blob_capacity;
};

static int compare_builtin_rules(const void *a, const void *b) {
  const omega_builtin_reactor_rule_t *r1 =
      (const omega_builtin_reactor_rule_t *)a;
  const omega_builtin_reactor_rule_t *r2 =
      (const omega_builtin_reactor_rule_t *)b;
  return (r1->rule_id > r2->rule_id) - (r1->rule_id < r2->rule_id);
}

static int is_valid_opcode(uint32_t opcode) {
  return opcode >= OMEGA_REACTOR_BUILTIN_UPPER &&
         opcode <= OMEGA_REACTOR_BUILTIN_UUID;
}

static const omega_builtin_reactor_rule_t *
find_builtin_rule(const omega_builtin_reactor_t *reactor, uint64_t rule_id) {
  size_t lo = 0;
  size_t hi = reactor->rule_count;
  while (lo < hi) {
    const size_t mid = lo + ((hi - lo) >> 1);
    const uint64_t mid_id = reactor->rules[mid].rule_id;
    if (mid_id < rule_id) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  if (lo < reactor->rule_count && reactor->rules[lo].rule_id == rule_id) {
    return &reactor->rules[lo];
  }
  return NULL;
}

omega_rewrite_plan_t *omega_rewrite_plan_create(void) {
  return (omega_rewrite_plan_t *)calloc(1, sizeof(omega_rewrite_plan_t));
}

static int reserve_actions(omega_rewrite_plan_t *plan, size_t extra) {
  omega_rewrite_action_t *new_actions;
  size_t needed;
  size_t new_capacity;

  if (extra > SIZE_MAX - plan->action_count) {
    return -1;
  }
  needed = plan->action_count + extra;
  if (needed <= plan->action_capacity) {
    return 0;
  }

  new_capacity = plan->action_capacity ? plan->action_capacity : 8;
  while (new_capacity < needed) {
    if (new_capacity > (SIZE_MAX >> 1)) {
      new_capacity = needed;
      break;
    }
    new_capacity <<= 1;
  }

  new_actions = (omega_rewrite_action_t *)realloc(
      plan->actions, new_capacity * sizeof(*new_actions));
  if (!new_actions) {
    return -1;
  }
  plan->actions = new_actions;
  plan->action_capacity = new_capacity;
  return 0;
}

static uint8_t *append_blob(omega_rewrite_plan_t *plan, const uint8_t *data,
                            size_t data_len) {
  uint8_t *old_blob;
  uint8_t *new_blob;
  uint8_t *dst;
  size_t *offsets = NULL;
  size_t needed;
  size_t new_capacity;
  size_t i;

  if (data_len == 0) {
    return NULL;
  }
  if (data_len > SIZE_MAX - plan->data_blob_len) {
    return NULL;
  }
  needed = plan->data_blob_len + data_len;
  if (needed > plan->data_blob_capacity) {
    new_capacity = plan->data_blob_capacity ? plan->data_blob_capacity : 64;
    old_blob = plan->data_blob;
    if (old_blob && plan->action_count > 0) {
      offsets = (size_t *)malloc(plan->action_count * sizeof(*offsets));
      if (!offsets) {
        return NULL;
      }
      for (i = 0; i < plan->action_count; ++i) {
        if (plan->actions[i].data) {
          offsets[i] = (size_t)(plan->actions[i].data - old_blob);
        } else {
          offsets[i] = SIZE_MAX;
        }
      }
    }
    while (new_capacity < needed) {
      if (new_capacity > (SIZE_MAX >> 1)) {
        new_capacity = needed;
        break;
      }
      new_capacity <<= 1;
    }
    new_blob = (uint8_t *)realloc(plan->data_blob,
                                  new_capacity * sizeof(*new_blob));
    if (!new_blob) {
      free(offsets);
      return NULL;
    }
    plan->data_blob = new_blob;
    plan->data_blob_capacity = new_capacity;
    if (offsets && old_blob != new_blob) {
      for (i = 0; i < plan->action_count; ++i) {
        if (offsets[i] != SIZE_MAX) {
          plan->actions[i].data = new_blob + offsets[i];
        }
      }
    }
    free(offsets);
  }

  dst = plan->data_blob + plan->data_blob_len;
  memcpy(dst, data, data_len);
  plan->data_blob_len += data_len;
  return dst;
}

#ifndef _WIN32
static int resolve_plugin_init_symbol(void *handle, const char *symbol_name,
                                      omega_native_reactor_plugin_init_fn *out) {
  void *symbol;

  if (!handle || !symbol_name || !out) {
    return -1;
  }

  symbol = dlsym(handle, symbol_name);
  if (!symbol) {
    return -1;
  }
  if (sizeof(symbol) != sizeof(*out)) {
    return -1;
  }
  memcpy(out, &symbol, sizeof(symbol));
  return 0;
}
#endif

int omega_rewrite_plan_add_action(omega_rewrite_plan_t *restrict plan,
                                  size_t start, size_t end, uint64_t rule_id,
                                  omega_rewrite_action_kind_t kind,
                                  const uint8_t *data, size_t data_len) {
  omega_rewrite_action_t *action;

  if (!plan || end < start) {
    return -1;
  }
  if (data_len > 0 && data == NULL) {
    return -1;
  }
  if (reserve_actions(plan, 1) != 0) {
    return -1;
  }

  action = &plan->actions[plan->action_count];
  action->start = start;
  action->end = end;
  action->rule_id = rule_id;
  action->kind = kind;
  action->data_len = data_len;
  action->data = append_blob(plan, data, data_len);
  if (data_len > 0 && action->data == NULL) {
    return -1;
  }

  ++plan->action_count;
  return 0;
}

static uint64_t fnv1a64_seeded(uint64_t seed, const uint8_t *data, size_t len) {
  uint64_t h = seed;
  size_t i;
  for (i = 0; i < len; ++i) {
    h ^= (uint64_t)data[i];
    h *= 1099511628211ULL;
  }
  return h;
}

static uint64_t fnv1a64_u64(uint64_t seed, uint64_t value) {
  uint8_t buf[8];
  size_t i;
  for (i = 0; i < 8; ++i) {
    buf[i] = (uint8_t)(value & 0xFFu);
    value >>= 8;
  }
  return fnv1a64_seeded(seed, buf, sizeof(buf));
}

static void make_uuid_v8(char out[36], uint64_t rule_id, size_t start,
                         uint32_t len, const uint8_t *match) {
  static const char hex[] = "0123456789abcdef";
  uint8_t bytes[16];
  uint64_t h1 = 1469598103934665603ULL;
  uint64_t h2 = 1099511628211ULL;
  size_t i;
  size_t j = 0;

  h1 = fnv1a64_u64(h1, rule_id);
  h1 = fnv1a64_u64(h1, (uint64_t)start);
  h1 = fnv1a64_u64(h1, (uint64_t)len);
  h1 = fnv1a64_seeded(h1, match, len);

  h2 = fnv1a64_u64(h2, rule_id ^ 0x9E3779B97F4A7C15ULL);
  h2 = fnv1a64_u64(h2, (uint64_t)start ^ 0xD6E8FEB86659FD93ULL);
  h2 = fnv1a64_u64(h2, (uint64_t)len ^ 0xA5A3564E27F88691ULL);
  h2 = fnv1a64_seeded(h2, match, len);

  for (i = 0; i < 8; ++i) {
    bytes[i] = (uint8_t)((h1 >> (8 * (7 - i))) & 0xFFu);
    bytes[8 + i] = (uint8_t)((h2 >> (8 * (7 - i))) & 0xFFu);
  }

  bytes[6] = (uint8_t)((bytes[6] & 0x0Fu) | 0x80u);
  bytes[8] = (uint8_t)((bytes[8] & 0x3Fu) | 0x80u);

  for (i = 0; i < 16; ++i) {
    if (j == 8 || j == 13 || j == 18 || j == 23) {
      out[j++] = '-';
    }
    out[j++] = hex[(bytes[i] >> 4) & 0x0Fu];
    out[j++] = hex[bytes[i] & 0x0Fu];
  }
}

static int append_builtin_action(omega_rewrite_plan_t *plan,
                                 const omega_builtin_reactor_rule_t *rule,
                                 const omega_match_result_t *match) {
  const size_t start = match->offset;
  const size_t len = (size_t)match->len;
  int rc;
  uint8_t *tmp = NULL;
  size_t i;

  if (len > SIZE_MAX - start) {
    return -1;
  }

  switch (rule->opcode) {
  case OMEGA_REACTOR_BUILTIN_UPPER:
  case OMEGA_REACTOR_BUILTIN_LOWER:
  case OMEGA_REACTOR_BUILTIN_REDACT:
    if (len > 0) {
      tmp = (uint8_t *)malloc(len);
      if (!tmp) {
        return -1;
      }
    }
    if (rule->opcode == OMEGA_REACTOR_BUILTIN_REDACT) {
      if (len > 0) {
        memset(tmp, rule->redact_byte, len);
      }
    } else if (rule->opcode == OMEGA_REACTOR_BUILTIN_UPPER) {
      for (i = 0; i < len; ++i) {
        tmp[i] = (uint8_t)toupper((unsigned char)match->match[i]);
      }
    } else {
      for (i = 0; i < len; ++i) {
        tmp[i] = (uint8_t)tolower((unsigned char)match->match[i]);
      }
    }
    rc = omega_rewrite_plan_add_action(plan, start, start + len, match->key,
                                       OMEGA_REWRITE_OVERWRITE, tmp, len);
    free(tmp);
    return rc;

  case OMEGA_REACTOR_BUILTIN_UUID: {
    char uuid[36];
    make_uuid_v8(uuid, match->key, start, match->len, match->match);
    return omega_rewrite_plan_add_action(plan, start, start + len, match->key,
                                         OMEGA_REWRITE_REPLACE,
                                         (const uint8_t *)uuid, sizeof(uuid));
  }

  default:
    return -1;
  }
}

omega_builtin_reactor_t *omega_builtin_reactor_create(
    const omega_builtin_reactor_rule_t *restrict rules, size_t rule_count) {
  omega_builtin_reactor_t *reactor;
  size_t i;

  if (rules == NULL || rule_count == 0) {
    return NULL;
  }

  reactor = (omega_builtin_reactor_t *)calloc(1, sizeof(*reactor));
  if (!reactor) {
    return NULL;
  }

  if (rule_count > SIZE_MAX / sizeof(*reactor->rules)) {
    free(reactor);
    return NULL;
  }
  reactor->rules = (omega_builtin_reactor_rule_t *)malloc(rule_count *
                                                          sizeof(*reactor->rules));
  if (!reactor->rules) {
    free(reactor);
    return NULL;
  }
  memcpy(reactor->rules, rules, rule_count * sizeof(*reactor->rules));
  reactor->rule_count = rule_count;

  for (i = 0; i < rule_count; ++i) {
    // rule_id 0 is reserved: matches from patterns compiled without a key
    // carry key 0, so a rule registered as 0 would fire on every unkeyed
    // match.
    if (reactor->rules[i].rule_id == 0 ||
        !is_valid_opcode(reactor->rules[i].opcode)) {
      omega_builtin_reactor_destroy(reactor);
      return NULL;
    }
  }

  qsort(reactor->rules, reactor->rule_count, sizeof(*reactor->rules),
        compare_builtin_rules);

  for (i = 1; i < reactor->rule_count; ++i) {
    if (reactor->rules[i - 1].rule_id == reactor->rules[i].rule_id) {
      omega_builtin_reactor_destroy(reactor);
      return NULL;
    }
  }

  return reactor;
}

int omega_builtin_reactor_destroy(omega_builtin_reactor_t *restrict reactor) {
  if (!reactor) {
    return -1;
  }
  free(reactor->rules);
  free(reactor);
  return 0;
}

omega_rewrite_plan_t *omega_builtin_reactor_plan_matches(
    const omega_builtin_reactor_t *restrict reactor,
    const omega_match_results_t *restrict results) {
  omega_rewrite_plan_t *plan;
  size_t i;

  if (!reactor || !results) {
    return NULL;
  }

  plan = omega_rewrite_plan_create();
  if (!plan) {
    return NULL;
  }

  for (i = 0; i < results->count; ++i) {
    const omega_match_result_t *match = &results->matches[i];
    const omega_builtin_reactor_rule_t *rule =
        find_builtin_rule(reactor, match->key);
    if (!rule) {
      continue;
    }
    if (append_builtin_action(plan, rule, match) != 0) {
      omega_rewrite_plan_destroy(plan);
      return NULL;
    }
  }

  return plan;
}

omega_rewrite_plan_t *omega_builtin_reactor_plan(
    const omega_builtin_reactor_t *restrict reactor,
    const omega_list_matcher_t *restrict matcher,
    const uint8_t *restrict haystack, size_t haystack_size, int no_overlap,
    int longest_only, int word_boundary, int word_prefix, int word_suffix,
    int line_start, int line_end) {
  omega_match_results_t *results;
  omega_rewrite_plan_t *plan;

  if (!reactor || !matcher || (!haystack && haystack_size != 0)) {
    return NULL;
  }

  results = omega_list_matcher_match(matcher, haystack, haystack_size,
                                     no_overlap, longest_only, word_boundary,
                                     word_prefix, word_suffix, line_start,
                                     line_end);
  if (!results) {
    return NULL;
  }

  plan = omega_builtin_reactor_plan_matches(reactor, results);
  omega_match_results_destroy(results);
  return plan;
}

static int reserve_native_rules(omega_native_reactor_builder_t *builder,
                                size_t extra) {
  omega_native_reactor_rule_t *new_rules;
  size_t needed;
  size_t new_capacity;

  if (extra > SIZE_MAX - builder->rule_count) {
    return -1;
  }
  needed = builder->rule_count + extra;
  if (needed <= builder->rule_capacity) {
    return 0;
  }
  new_capacity = builder->rule_capacity ? builder->rule_capacity : 8;
  while (new_capacity < needed) {
    if (new_capacity > (SIZE_MAX >> 1)) {
      new_capacity = needed;
      break;
    }
    new_capacity <<= 1;
  }
  new_rules = (omega_native_reactor_rule_t *)realloc(
      builder->rules, new_capacity * sizeof(*new_rules));
  if (!new_rules) {
    return -1;
  }
  builder->rules = new_rules;
  builder->rule_capacity = new_capacity;
  return 0;
}

static int reserve_plugin_handles(omega_native_reactor_builder_t *builder,
                                  size_t extra) {
  void **new_handles;
  size_t needed;
  size_t new_capacity;

  if (extra > SIZE_MAX - builder->plugin_count) {
    return -1;
  }
  needed = builder->plugin_count + extra;
  if (needed <= builder->plugin_capacity) {
    return 0;
  }
  new_capacity = builder->plugin_capacity ? builder->plugin_capacity : 4;
  while (new_capacity < needed) {
    if (new_capacity > (SIZE_MAX >> 1)) {
      new_capacity = needed;
      break;
    }
    new_capacity <<= 1;
  }
  new_handles =
      (void **)realloc(builder->plugin_handles, new_capacity * sizeof(void *));
  if (!new_handles) {
    return -1;
  }
  builder->plugin_handles = new_handles;
  builder->plugin_capacity = new_capacity;
  return 0;
}

static int builder_has_rule(const omega_native_reactor_builder_t *builder,
                            uint64_t rule_id) {
  size_t i;
  for (i = 0; i < builder->rule_count; ++i) {
    if (builder->rules[i].rule_id == rule_id) {
      return 1;
    }
  }
  return 0;
}

omega_native_reactor_builder_t *omega_native_reactor_builder_create(void) {
  return (omega_native_reactor_builder_t *)calloc(
      1, sizeof(omega_native_reactor_builder_t));
}

int omega_native_reactor_builder_destroy(
    omega_native_reactor_builder_t *restrict builder) {
  size_t i;
  if (!builder) {
    return -1;
  }
  for (i = 0; i < builder->plugin_count; ++i) {
#ifdef _WIN32
    FreeLibrary((HMODULE)builder->plugin_handles[i]);
#else
    dlclose(builder->plugin_handles[i]);
#endif
  }
  free(builder->rules);
  free(builder->plugin_handles);
  free(builder);
  return 0;
}

int omega_native_reactor_builder_add_rule(
    omega_native_reactor_builder_t *restrict builder, uint64_t rule_id,
    omega_native_reactor_handler_fn handler, void *handler_ctx) {
  omega_native_reactor_rule_t *rule;
  // rule_id 0 is reserved: matches from patterns compiled without a key
  // carry key 0, so a rule registered as 0 would fire on every unkeyed match.
  if (!builder || !handler || rule_id == 0 ||
      builder_has_rule(builder, rule_id)) {
    return -1;
  }
  if (reserve_native_rules(builder, 1) != 0) {
    return -1;
  }
  rule = &builder->rules[builder->rule_count];
  rule->rule_id = rule_id;
  rule->handler = handler;
  rule->handler_ctx = handler_ctx;
  ++builder->rule_count;
  return 0;
}

int omega_native_reactor_builder_load_plugin(
    omega_native_reactor_builder_t *restrict builder,
    const char *restrict library_path, const char *restrict init_symbol,
    void *plugin_ctx) {
  const char *symbol_name;
  omega_native_reactor_plugin_init_fn init_fn;
  void *handle;
  size_t old_rule_count;

  if (!builder || !library_path || library_path[0] == '\0') {
    return -1;
  }

  symbol_name = (init_symbol && init_symbol[0] != '\0')
                    ? init_symbol
                    : "omega_reactor_plugin_init";

#ifdef _WIN32
  handle = (void *)LoadLibraryA(library_path);
  if (!handle) {
    return -1;
  }
  init_fn = (omega_native_reactor_plugin_init_fn)(void *)GetProcAddress(
      (HMODULE)handle, symbol_name);
#else
  handle = dlopen(library_path, RTLD_NOW);
  if (!handle) {
    return -1;
  }
  if (resolve_plugin_init_symbol(handle, symbol_name, &init_fn) != 0) {
    dlclose(handle);
    return -1;
  }
#endif
  if (!init_fn) {
#ifdef _WIN32
    FreeLibrary((HMODULE)handle);
#else
    dlclose(handle);
#endif
    return -1;
  }

  if (reserve_plugin_handles(builder, 1) != 0) {
#ifdef _WIN32
    FreeLibrary((HMODULE)handle);
#else
    dlclose(handle);
#endif
    return -1;
  }

  old_rule_count = builder->rule_count;
  if (init_fn(builder, plugin_ctx) != 0) {
    builder->rule_count = old_rule_count;
#ifdef _WIN32
    FreeLibrary((HMODULE)handle);
#else
    dlclose(handle);
#endif
    return -1;
  }

  builder->plugin_handles[builder->plugin_count++] = handle;
  return 0;
}

omega_native_reactor_t *omega_native_reactor_builder_build(
    omega_native_reactor_builder_t *restrict builder) {
  omega_native_reactor_t *reactor;
  native_dispatch_entry_t *dispatch;
  size_t i;
  uint64_t max_rule_id = 0;

  if (!builder || builder->rule_count == 0) {
    return NULL;
  }

  for (i = 0; i < builder->rule_count; ++i) {
    if (!builder->rules[i].handler) {
      return NULL;
    }
    if (builder->rules[i].rule_id > max_rule_id) {
      max_rule_id = builder->rules[i].rule_id;
    }
  }

  if (max_rule_id > OMEGA_NATIVE_REACTOR_MAX_DENSE_RULE_ID) {
    return NULL;
  }
  if (max_rule_id > (uint64_t)(SIZE_MAX - 1)) {
    return NULL;
  }
  if ((size_t)max_rule_id > SIZE_MAX / sizeof(*dispatch) - 1) {
    return NULL;
  }

  reactor = (omega_native_reactor_t *)calloc(1, sizeof(*reactor));
  if (!reactor) {
    return NULL;
  }

  reactor->dispatch_size = (size_t)max_rule_id + 1;
  dispatch = (native_dispatch_entry_t *)calloc(reactor->dispatch_size,
                                               sizeof(*dispatch));
  if (!dispatch) {
    free(reactor);
    return NULL;
  }
  reactor->dispatch = dispatch;

  for (i = 0; i < builder->rule_count; ++i) {
    const size_t idx = (size_t)builder->rules[i].rule_id;
    if (reactor->dispatch[idx].handler) {
      omega_native_reactor_destroy(reactor);
      return NULL;
    }
    reactor->dispatch[idx].handler = builder->rules[i].handler;
    reactor->dispatch[idx].handler_ctx = builder->rules[i].handler_ctx;
  }

  reactor->plugin_handles = builder->plugin_handles;
  reactor->plugin_count = builder->plugin_count;
  builder->plugin_handles = NULL;
  builder->plugin_count = 0;
  builder->plugin_capacity = 0;

  free(builder->rules);
  builder->rules = NULL;
  builder->rule_count = 0;
  builder->rule_capacity = 0;

  return reactor;
}

omega_native_reactor_t *omega_native_reactor_create(
    const omega_native_reactor_rule_t *restrict rules, size_t rule_count) {
  omega_native_reactor_builder_t *builder;
  omega_native_reactor_t *reactor;
  size_t i;

  if (!rules || rule_count == 0) {
    return NULL;
  }

  builder = omega_native_reactor_builder_create();
  if (!builder) {
    return NULL;
  }
  for (i = 0; i < rule_count; ++i) {
    if (omega_native_reactor_builder_add_rule(
            builder, rules[i].rule_id, rules[i].handler,
            rules[i].handler_ctx) != 0) {
      omega_native_reactor_builder_destroy(builder);
      return NULL;
    }
  }
  reactor = omega_native_reactor_builder_build(builder);
  omega_native_reactor_builder_destroy(builder);
  return reactor;
}

int omega_native_reactor_destroy(omega_native_reactor_t *restrict reactor) {
  size_t i;
  if (!reactor) {
    return -1;
  }
  for (i = 0; i < reactor->plugin_count; ++i) {
#ifdef _WIN32
    FreeLibrary((HMODULE)reactor->plugin_handles[i]);
#else
    dlclose(reactor->plugin_handles[i]);
#endif
  }
  free(reactor->dispatch);
  free(reactor->plugin_handles);
  free(reactor);
  return 0;
}

omega_rewrite_plan_t *omega_native_reactor_plan_matches(
    const omega_native_reactor_t *restrict reactor,
    const omega_match_results_t *restrict results) {
  omega_rewrite_plan_t *plan;
  size_t i;

  if (!reactor || !results) {
    return NULL;
  }

  plan = omega_rewrite_plan_create();
  if (!plan) {
    return NULL;
  }

  for (i = 0; i < results->count; ++i) {
    const omega_match_result_t *match = &results->matches[i];
    // Compare in uint64 so high key bits are not truncated on 32-bit size_t
    if (match->key >= (uint64_t)reactor->dispatch_size) {
      continue;
    }
    if (reactor->dispatch[match->key].handler) {
      if (reactor->dispatch[match->key].handler(
              plan, match, reactor->dispatch[match->key].handler_ctx) != 0) {
        omega_rewrite_plan_destroy(plan);
        return NULL;
      }
    }
  }

  return plan;
}

omega_rewrite_plan_t *omega_native_reactor_plan(
    const omega_native_reactor_t *restrict reactor,
    const omega_list_matcher_t *restrict matcher,
    const uint8_t *restrict haystack, size_t haystack_size, int no_overlap,
    int longest_only, int word_boundary, int word_prefix, int word_suffix,
    int line_start, int line_end) {
  omega_match_results_t *results;
  omega_rewrite_plan_t *plan;

  if (!reactor || !matcher || (!haystack && haystack_size != 0)) {
    return NULL;
  }

  results = omega_list_matcher_match(matcher, haystack, haystack_size,
                                     no_overlap, longest_only, word_boundary,
                                     word_prefix, word_suffix, line_start,
                                     line_end);
  if (!results) {
    return NULL;
  }

  plan = omega_native_reactor_plan_matches(reactor, results);
  omega_match_results_destroy(results);
  return plan;
}

size_t omega_rewrite_plan_get_action_count(
    const omega_rewrite_plan_t *restrict plan) {
  return plan ? plan->action_count : 0;
}

const omega_rewrite_action_t *omega_rewrite_plan_get_actions(
    const omega_rewrite_plan_t *restrict plan) {
  return plan ? plan->actions : NULL;
}

int omega_rewrite_plan_destroy(omega_rewrite_plan_t *restrict plan) {
  if (!plan) {
    return -1;
  }
  free(plan->actions);
  free(plan->data_blob);
  free(plan);
  return 0;
}
