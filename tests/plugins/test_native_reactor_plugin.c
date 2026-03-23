#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "omega/reactor.h"

#ifdef _WIN32
#define OMEGA_REACTOR_PLUGIN_EXPORT __declspec(dllexport)
#else
#define OMEGA_REACTOR_PLUGIN_EXPORT __attribute__((visibility("default")))
#endif

typedef struct {
  uint8_t open_ch;
  uint8_t close_ch;
  uint8_t fill_ch;
} plugin_rule_config_t;

static plugin_rule_config_t g_default_config = {'[', ']', '#'};

static int wrap_match_handler(omega_rewrite_plan_t *plan,
                              const omega_match_result_t *match, void *ctx) {
  const plugin_rule_config_t *cfg = (const plugin_rule_config_t *)ctx;
  uint8_t *buf;
  const size_t len = (size_t)match->len;
  int rc;

  if (len > SIZE_MAX - 2) {
    return -1;
  }
  buf = (uint8_t *)malloc(len + 2);
  if (!buf) {
    return -1;
  }
  buf[0] = cfg->open_ch;
  if (len > 0) {
    memcpy(buf + 1, match->match, len);
  }
  buf[len + 1] = cfg->close_ch;
  rc = omega_rewrite_plan_add_action(plan, match->offset, match->offset + len,
                                     match->key, OMEGA_REWRITE_REPLACE, buf,
                                     len + 2);
  free(buf);
  return rc;
}

static int fill_match_handler(omega_rewrite_plan_t *plan,
                              const omega_match_result_t *match, void *ctx) {
  const plugin_rule_config_t *cfg = (const plugin_rule_config_t *)ctx;
  uint8_t *buf;
  const size_t len = (size_t)match->len;
  int rc;

  buf = (uint8_t *)malloc(len);
  if (len > 0 && !buf) {
    return -1;
  }
  if (len > 0) {
    memset(buf, cfg->fill_ch, len);
  }
  rc = omega_rewrite_plan_add_action(plan, match->offset, match->offset + len,
                                     match->key, OMEGA_REWRITE_OVERWRITE, buf,
                                     len);
  free(buf);
  return rc;
}

OMEGA_REACTOR_PLUGIN_EXPORT int
omega_reactor_plugin_init(omega_native_reactor_builder_t *builder,
                          void *plugin_ctx) {
  plugin_rule_config_t *cfg =
      plugin_ctx ? (plugin_rule_config_t *)plugin_ctx : &g_default_config;

  if (omega_native_reactor_builder_add_rule(builder, 201, wrap_match_handler,
                                            cfg) != 0) {
    return -1;
  }
  if (omega_native_reactor_builder_add_rule(builder, 202, fill_match_handler,
                                            cfg) != 0) {
    return -1;
  }
  return 0;
}

OMEGA_REACTOR_PLUGIN_EXPORT int
omega_reactor_plugin_init_sparse_rule(omega_native_reactor_builder_t *builder,
                                      void *plugin_ctx) {
  plugin_rule_config_t *cfg =
      plugin_ctx ? (plugin_rule_config_t *)plugin_ctx : &g_default_config;

  return omega_native_reactor_builder_add_rule(builder, 100000000ULL,
                                               wrap_match_handler, cfg);
}
