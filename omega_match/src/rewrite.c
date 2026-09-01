#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

#include "omega/rewrite.h"

#ifdef OMEGA_MATCH_HAVE_OMEGA_EDIT
#include "omega_edit.h"
#include "omega_edit/fwd_defs.h"
#endif

typedef struct {
  size_t index;
  size_t start;
  size_t end;
  size_t order;
} action_ref_t;

struct omega_rewrite_script_struct {
  omega_rewrite_script_op_t *ops;
  size_t op_count;
  size_t op_capacity;
  uint8_t *data_blob;
  size_t data_blob_len;
  size_t data_blob_capacity;
};

static int is_edit_action(omega_rewrite_action_kind_t kind) {
  return kind == OMEGA_REWRITE_OVERWRITE || kind == OMEGA_REWRITE_REPLACE ||
         kind == OMEGA_REWRITE_INSERT || kind == OMEGA_REWRITE_DELETE;
}

static int compare_action_refs_desc(const void *a, const void *b) {
  const action_ref_t *r1 = (const action_ref_t *)a;
  const action_ref_t *r2 = (const action_ref_t *)b;

  if (r1->start != r2->start) {
    return (r1->start < r2->start) - (r1->start > r2->start);
  }
  if (r1->end != r2->end) {
    return (r1->end < r2->end) - (r1->end > r2->end);
  }
  // Descending order tiebreak: both apply paths replay the descending-offset
  // op list such that, of two same-position inserts, the one applied later
  // ends up first in the output — so the earlier-emitted action must sort
  // later for emission order to be preserved in the output.
  return (r1->order < r2->order) - (r1->order > r2->order);
}

static void sort_action_refs(action_ref_t *refs, size_t count,
                             const omega_rewrite_action_t *actions) {
  size_t i;
  for (i = 0; i < count; ++i) {
    const omega_rewrite_action_t *action = &actions[refs[i].index];
    refs[i].start = action->start;
    refs[i].end = action->end;
  }
  qsort(refs, count, sizeof(*refs), compare_action_refs_desc);
}

static int reserve_script_ops(omega_rewrite_script_t *script, size_t extra) {
  if (extra > SIZE_MAX - script->op_count) {
    return -1;
  }
  {
    const size_t needed = script->op_count + extra;
    size_t new_cap;
    omega_rewrite_script_op_t *new_ops;
    if (needed <= script->op_capacity) {
      return 0;
    }
    new_cap = script->op_capacity ? script->op_capacity : 8;
    while (new_cap < needed) {
      if (new_cap > (SIZE_MAX >> 1)) {
        new_cap = needed;
        break;
      }
      new_cap <<= 1;
    }
    new_ops = (omega_rewrite_script_op_t *)realloc(
        script->ops, new_cap * sizeof(*new_ops));
    if (!new_ops) {
      return -1;
    }
    script->ops = new_ops;
    script->op_capacity = new_cap;
  }
  return 0;
}

static const uint8_t *append_script_blob(omega_rewrite_script_t *script,
                                         const uint8_t *data, size_t data_len) {
  uint8_t *old_blob;
  size_t *offsets = NULL;
  if (data_len == 0) {
    return NULL;
  }
  if (data_len > SIZE_MAX - script->data_blob_len) {
    return NULL;
  }
  {
    const size_t needed = script->data_blob_len + data_len;
    if (needed > script->data_blob_capacity) {
      size_t new_cap = script->data_blob_capacity ? script->data_blob_capacity : 64;
      uint8_t *new_blob;
      size_t i;
      old_blob = script->data_blob;
      if (old_blob && script->op_count > 0) {
        offsets = (size_t *)malloc(script->op_count * sizeof(*offsets));
        if (!offsets) {
          return NULL;
        }
        for (i = 0; i < script->op_count; ++i) {
          if (script->ops[i].data) {
            offsets[i] = (size_t)(script->ops[i].data - old_blob);
          } else {
            offsets[i] = SIZE_MAX;
          }
        }
      }
      while (new_cap < needed) {
        if (new_cap > (SIZE_MAX >> 1)) {
          new_cap = needed;
          break;
        }
        new_cap <<= 1;
      }
      new_blob = (uint8_t *)realloc(script->data_blob, new_cap);
      if (!new_blob) {
        free(offsets);
        return NULL;
      }
      script->data_blob = new_blob;
      script->data_blob_capacity = new_cap;
      if (offsets && old_blob != new_blob) {
        for (i = 0; i < script->op_count; ++i) {
          if (offsets[i] != SIZE_MAX) {
            script->ops[i].data = new_blob + offsets[i];
          }
        }
      }
      free(offsets);
    }
  }
  {
    uint8_t *dst = script->data_blob + script->data_blob_len;
    memcpy(dst, data, data_len);
    script->data_blob_len += data_len;
    return dst;
  }
}

static int append_script_op(omega_rewrite_script_t *script, uint32_t kind,
                            size_t offset, size_t length, uint64_t rule_id,
                            const uint8_t *data, size_t data_len) {
  omega_rewrite_script_op_t *op;
  if (reserve_script_ops(script, 1) != 0) {
    return -1;
  }
  op = &script->ops[script->op_count];
  op->offset = offset;
  op->length = length;
  op->rule_id = rule_id;
  op->kind = kind;
  op->data_len = data_len;
  op->data = append_script_blob(script, data, data_len);
  if (data_len > 0 && op->data == NULL) {
    return -1;
  }
  ++script->op_count;
  return 0;
}

static int actions_conflict(const omega_rewrite_action_t *current,
                            const omega_rewrite_action_t *previous) {
  if (current->end <= previous->start) {
    return 0;
  }
  if (current->start == current->end && current->start == previous->start &&
      previous->start == previous->end) {
    return 0;
  }
  return 1;
}

omega_rewrite_script_t *
omega_rewrite_script_create(const omega_rewrite_plan_t *restrict plan) {
  omega_rewrite_script_t *script;
  action_ref_t *refs;
  size_t edit_count = 0;
  size_t i;
  const omega_rewrite_action_t *actions;

  if (!plan) {
    return NULL;
  }

  actions = omega_rewrite_plan_get_actions(plan);
  if (!actions && omega_rewrite_plan_get_action_count(plan) != 0) {
    return NULL;
  }

  for (i = 0; i < omega_rewrite_plan_get_action_count(plan); ++i) {
    if (is_edit_action(actions[i].kind)) {
      ++edit_count;
    }
  }

  script = (omega_rewrite_script_t *)calloc(1, sizeof(*script));
  if (!script) {
    return NULL;
  }

  if (edit_count == 0) {
    return script;
  }

  refs = (action_ref_t *)malloc(edit_count * sizeof(*refs));
  if (!refs) {
    omega_rewrite_script_destroy(script);
    return NULL;
  }

  edit_count = 0;
  for (i = 0; i < omega_rewrite_plan_get_action_count(plan); ++i) {
    if (is_edit_action(actions[i].kind)) {
      refs[edit_count].index = i;
      refs[edit_count].start = 0;
      refs[edit_count].end = 0;
      refs[edit_count].order = edit_count;
      ++edit_count;
    }
  }

  sort_action_refs(refs, edit_count, actions);

  for (i = 1; i < edit_count; ++i) {
    const omega_rewrite_action_t *prev = &actions[refs[i - 1].index];
    const omega_rewrite_action_t *cur = &actions[refs[i].index];
    if (actions_conflict(cur, prev)) {
      free(refs);
      omega_rewrite_script_destroy(script);
      return NULL;
    }
  }

  for (i = 0; i < edit_count; ++i) {
    const omega_rewrite_action_t *action = &actions[refs[i].index];
    const size_t len = action->end - action->start;
    switch (action->kind) {
    case OMEGA_REWRITE_OVERWRITE:
      if (action->data_len != len) {
        free(refs);
        omega_rewrite_script_destroy(script);
        return NULL;
      }
      if (append_script_op(script, OMEGA_REWRITE_SCRIPT_OVERWRITE, action->start,
                           len, action->rule_id, action->data,
                           action->data_len) != 0) {
        free(refs);
        omega_rewrite_script_destroy(script);
        return NULL;
      }
      break;
    case OMEGA_REWRITE_REPLACE:
      if (append_script_op(script, OMEGA_REWRITE_SCRIPT_DELETE, action->start, len,
                           action->rule_id, NULL, 0) != 0 ||
          append_script_op(script, OMEGA_REWRITE_SCRIPT_INSERT, action->start, 0,
                           action->rule_id, action->data,
                           action->data_len) != 0) {
        free(refs);
        omega_rewrite_script_destroy(script);
        return NULL;
      }
      break;
    case OMEGA_REWRITE_INSERT:
      if (append_script_op(script, OMEGA_REWRITE_SCRIPT_INSERT, action->start, 0,
                           action->rule_id, action->data,
                           action->data_len) != 0) {
        free(refs);
        omega_rewrite_script_destroy(script);
        return NULL;
      }
      break;
    case OMEGA_REWRITE_DELETE:
      if (append_script_op(script, OMEGA_REWRITE_SCRIPT_DELETE, action->start, len,
                           action->rule_id, NULL, 0) != 0) {
        free(refs);
        omega_rewrite_script_destroy(script);
        return NULL;
      }
      break;
    default:
      break;
    }
  }

  free(refs);
  return script;
}

int omega_rewrite_script_destroy(omega_rewrite_script_t *restrict script) {
  if (!script) {
    return -1;
  }
  free(script->ops);
  free(script->data_blob);
  free(script);
  return 0;
}

size_t omega_rewrite_script_get_op_count(
    const omega_rewrite_script_t *restrict script) {
  return script ? script->op_count : 0;
}

const omega_rewrite_script_op_t *
omega_rewrite_script_get_ops(const omega_rewrite_script_t *restrict script) {
  return script ? script->ops : NULL;
}

int omega_rewrite_script_apply_bytes(
    const omega_rewrite_script_t *restrict script,
    const uint8_t *restrict input, size_t input_len, uint8_t **restrict output,
    size_t *restrict output_len) {
  uint8_t *buffer;
  size_t out_size;
  size_t cursor;
  size_t write_pos;
  size_t i;

  if (!script || !output || !output_len || (!input && input_len != 0)) {
    return -1;
  }

  // Ops are stored in descending offset order over non-overlapping input
  // spans, so walking them in reverse yields a single ascending pass that
  // stitches the output together in O(input + output) instead of one tail
  // memmove per op.
  //
  // First pass: validate the ops and compute the exact output size.
  out_size = 0;
  cursor = 0;
  for (i = script->op_count; i-- > 0;) {
    const omega_rewrite_script_op_t *op = &script->ops[i];
    if (op->offset < cursor || op->offset > input_len) {
      return -1;
    }
    if (op->offset - cursor > SIZE_MAX - out_size) {
      return -1;
    }
    out_size += op->offset - cursor;
    cursor = op->offset;
    switch (op->kind) {
    case OMEGA_REWRITE_SCRIPT_OVERWRITE:
      if (op->data_len != op->length || op->length > input_len - cursor ||
          op->length > SIZE_MAX - out_size) {
        return -1;
      }
      out_size += op->length;
      cursor += op->length;
      break;
    case OMEGA_REWRITE_SCRIPT_DELETE:
      if (op->length > input_len - cursor) {
        return -1;
      }
      cursor += op->length;
      break;
    case OMEGA_REWRITE_SCRIPT_INSERT:
      if (op->data_len > SIZE_MAX - out_size) {
        return -1;
      }
      out_size += op->data_len;
      break;
    default:
      return -1;
    }
  }
  if (input_len - cursor > SIZE_MAX - out_size) {
    return -1;
  }
  out_size += input_len - cursor;

  buffer = (uint8_t *)malloc(out_size ? out_size : 1);
  if (!buffer) {
    return -1;
  }

  // Second pass: copy the untouched gaps and the op payloads in order.
  cursor = 0;
  write_pos = 0;
  for (i = script->op_count; i-- > 0;) {
    const omega_rewrite_script_op_t *op = &script->ops[i];
    const size_t gap = op->offset - cursor;
    if (gap > 0) {
      memcpy(buffer + write_pos, input + cursor, gap);
      write_pos += gap;
      cursor = op->offset;
    }
    switch (op->kind) {
    case OMEGA_REWRITE_SCRIPT_OVERWRITE:
      if (op->length > 0) {
        memcpy(buffer + write_pos, op->data, op->length);
        write_pos += op->length;
      }
      cursor += op->length;
      break;
    case OMEGA_REWRITE_SCRIPT_DELETE:
      cursor += op->length;
      break;
    default: // OMEGA_REWRITE_SCRIPT_INSERT
      if (op->data_len > 0) {
        memcpy(buffer + write_pos, op->data, op->data_len);
        write_pos += op->data_len;
      }
      break;
    }
  }
  if (cursor < input_len) {
    memcpy(buffer + write_pos, input + cursor, input_len - cursor);
  }

  *output = buffer;
  *output_len = out_size;
  return 0;
}

void omega_rewrite_bytes_destroy(uint8_t *bytes) { free(bytes); }

int omega_rewrite_script_omega_edit_available(void) {
#ifdef OMEGA_MATCH_HAVE_OMEGA_EDIT
  return 1;
#else
  return 0;
#endif
}

int omega_rewrite_script_apply_omega_edit(
    const omega_rewrite_script_t *restrict script,
    const char *restrict input_file, const char *restrict output_file) {
#ifdef OMEGA_MATCH_HAVE_OMEGA_EDIT
  omega_session_t *session;
  omega_edit_script_op_t *edit_ops;
  size_t edit_op_count;
  size_t i;
  int rc;

  if (!script || !input_file || !output_file) {
    return -1;
  }

  session = omega_edit_create_session(input_file, NULL, NULL, NO_EVENTS, NULL);
  if (!session) {
    return -1;
  }

  edit_ops = (omega_edit_script_op_t *)calloc(script->op_count ? script->op_count : 1,
                                              sizeof(*edit_ops));
  if (!edit_ops) {
    omega_edit_destroy_session(session);
    return -1;
  }

  edit_op_count = 0;
  for (i = 0; i < script->op_count; ++i) {
    const omega_rewrite_script_op_t *op = &script->ops[i];

    if (op->offset > (size_t)INT64_MAX || op->length > (size_t)INT64_MAX ||
        op->data_len > (size_t)INT64_MAX) {
      free(edit_ops);
      omega_edit_destroy_session(session);
      return -1;
    }

    if (op->kind == OMEGA_REWRITE_SCRIPT_DELETE && i + 1 < script->op_count &&
        script->ops[i + 1].kind == OMEGA_REWRITE_SCRIPT_INSERT &&
        script->ops[i + 1].offset == op->offset) {
      const omega_rewrite_script_op_t *next = &script->ops[i + 1];
      if (next->data_len > (size_t)INT64_MAX) {
        free(edit_ops);
        omega_edit_destroy_session(session);
        return -1;
      }
      edit_ops[edit_op_count].offset = (int64_t)op->offset;
      edit_ops[edit_op_count].length = (int64_t)op->length;
      edit_ops[edit_op_count].kind = OMEGA_EDIT_SCRIPT_REPLACE;
      edit_ops[edit_op_count].bytes = next->data;
      edit_ops[edit_op_count].bytes_length = (int64_t)next->data_len;
      ++edit_op_count;
      ++i;
      continue;
    }

    edit_ops[edit_op_count].offset = (int64_t)op->offset;
    edit_ops[edit_op_count].length = (int64_t)op->length;
    edit_ops[edit_op_count].bytes = op->data;
    edit_ops[edit_op_count].bytes_length = (int64_t)op->data_len;

    switch (op->kind) {
    case OMEGA_REWRITE_SCRIPT_OVERWRITE:
      edit_ops[edit_op_count].kind = (omega_edit_script_op_kind_t)OMEGA_EDIT_SCRIPT_OVERWRITE;
      break;
    case OMEGA_REWRITE_SCRIPT_DELETE:
      edit_ops[edit_op_count].kind = (omega_edit_script_op_kind_t)OMEGA_EDIT_SCRIPT_DELETE;
      break;
    case OMEGA_REWRITE_SCRIPT_INSERT:
      edit_ops[edit_op_count].kind = (omega_edit_script_op_kind_t)OMEGA_EDIT_SCRIPT_INSERT;
      break;
    default:
      free(edit_ops);
      omega_edit_destroy_session(session);
      return -1;
    }
    ++edit_op_count;
  }

  rc = omega_edit_apply_script(session, edit_ops, edit_op_count);
  free(edit_ops);
  if (rc != 0) {
    omega_edit_destroy_session(session);
    return -1;
  }

  rc = omega_edit_save(session, output_file, IO_FLG_OVERWRITE, NULL);
  omega_edit_destroy_session(session);
  return rc == 0 ? 0 : -1;
#else
  (void)script;
  (void)input_file;
  (void)output_file;
  return -1;
#endif
}
