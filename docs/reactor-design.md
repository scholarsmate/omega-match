# Reactor Design

This document describes the planned "reactor" layer that sits above OmegaMatch and below an edit engine such as OmegaEdit.

The reactor is responsible for taking keyed match results from OmegaMatch, interpreting those keys as rule IDs, and turning the resulting match stream into:

- edit actions against the original haystack or file
- side effects such as lookup tables, audit logs, or database writes

OmegaMatch remains a pure matching engine. OmegaEdit remains a pure editing engine. The reactor is the composition layer between them.

## Goals

- Keep the matcher focused on fast, portable pattern matching.
- Reuse keyed patterns as dense runtime rule IDs.
- Support builtin transforms, native plugins, and Python callbacks.
- Preserve original match coordinates even when replacements change byte length.
- Keep compiled matcher artifacts portable across processes and machines.
- Make rewrite plans inspectable and testable before edits are applied.

## Non-Goals

- Storing raw function addresses in compiled matcher files.
- Mutating the haystack while matching.
- Entangling OmegaMatch's on-disk format with reactor or editor internals.
- Making OmegaEdit responsible for side effects beyond byte edits.

## Layering

The planned architecture has three layers:

1. OmegaMatch
   - Compiles patterns.
   - Produces `omega_match_result_t` records.
   - Exposes an opaque `uint64_t key` field on each match result.

2. Reactor
   - Interprets `omega_match_result_t.key` as a rule ID.
   - Dispatches that rule ID to a builtin operation, native handler, or Python callback.
   - Emits edit actions and side effects against the original haystack coordinates.

3. OmegaEdit
   - Applies the resulting edit script to a file or session.
   - Owns byte-level mutation, persistence, undo, and replay.

This keeps the responsibilities crisp:

- OmegaMatch reports facts.
- Reactor decides intent.
- OmegaEdit applies bytes.

## Core Design Rules

The reactor design follows a few strict rules:

1. Match first, edit later.

   Matching always runs against the original haystack or original file bytes. The reactor only begins after the match stream is final.

2. Match coordinates are always relative to the original input.

   Variable-width replacements do not shift later match offsets because later matches are never computed from an already-mutated haystack.

3. Compiled matcher files remain pure data.

   Raw code pointers are never serialized. The key field remains an opaque 64-bit value chosen at compile time and interpreted by the runtime reactor.

4. Side effects live in the reactor, not in OmegaEdit.

   Examples include UUID lookup tables, hyperlink metadata, audit trails, and database writes.

## Data Flow

The expected end-to-end workflow is:

1. Compile patterns with keys that act as rule IDs.
2. Run OmegaMatch on the original haystack or file.
3. Receive an ordered `omega_match_result_t` stream.
4. Dispatch each match by `rule_id = result.key`.
5. Emit edit actions and side effects.
6. Validate and coalesce the action plan.
7. Apply the plan with OmegaEdit.
8. Persist the edited output and any side-effect artifacts.

For most workloads, the match stream is already ordered by offset ascending and length descending, which is a good fit for deterministic rewrite planning.

## Dispatch Model

The hot runtime lookup should be numeric, not string-based.

The current keyed-pattern support already gives each match an opaque `uint64_t key`. The reactor should treat that key as a dense rule ID whenever possible and build a direct runtime dispatch table after initialization.

That means the hot path becomes:

```c
const omega_reactor_entry_t *entry = &reactor->entries[result.key];
entry->handler(&ctx, &result, entry->handler_ctx);
```

String lookups such as `dlopen` + `dlsym` are still useful during setup, but not during per-match dispatch.

## Action Model

The reactor should emit typed actions rather than mutating bytes directly inside the handler.

Planned action kinds:

```c
typedef enum {
  OMEGA_REWRITE_NOOP = 0,
  OMEGA_REWRITE_OVERWRITE,
  OMEGA_REWRITE_REPLACE,
  OMEGA_REWRITE_INSERT,
  OMEGA_REWRITE_DELETE,
  OMEGA_REWRITE_SIDE_EFFECT
} omega_rewrite_action_kind_t;
```

Planned action payload:

```c
typedef struct {
  uint64_t start;
  uint64_t end; /* exclusive; relative to the original input */
  uint64_t rule_id;
  omega_rewrite_action_kind_t kind;
  const uint8_t *data;
  uint32_t data_len;
  void *user_ctx;
} omega_rewrite_action_t;
```

The action model is intentionally simple:

- `OVERWRITE`: write replacement bytes over an existing span, normally same-length
- `REPLACE`: replace a span with a new byte sequence of any length
- `INSERT`: insert bytes at an original-coordinate offset
- `DELETE`: remove a span from the original input
- `SIDE_EFFECT`: record metadata or external work without editing bytes

The reactor may also emit multiple actions from a single match if later phases need that flexibility, but the initial implementation should optimize for one primary action per match plus optional side effects.

## Handler ABI Sketch

The planned reactor context should let handlers observe the original input, emit actions, and attach side effects without doing byte surgery themselves.

```c
typedef struct omega_rewrite_plan_struct omega_rewrite_plan_t;

typedef struct {
  const uint8_t *input;
  size_t input_len;
  omega_rewrite_plan_t *plan;
  void *runtime_ctx;
} omega_reactor_context_t;

typedef int (*omega_reactor_handler_fn)(
    omega_reactor_context_t *ctx,
    const omega_match_result_t *match,
    void *handler_ctx);
```

Planned runtime dispatch entry:

```c
typedef enum {
  OMEGA_REACTOR_BUILTIN = 1,
  OMEGA_REACTOR_NATIVE = 2,
  OMEGA_REACTOR_PYTHON = 3
} omega_reactor_handler_kind_t;

typedef struct {
  uint64_t rule_id;
  omega_reactor_handler_kind_t kind;
  omega_reactor_handler_fn native_fn;
  void *handler_ctx;
  uint32_t builtin_opcode;
} omega_reactor_entry_t;
```

This is intentionally still a design sketch, not a finalized public ABI. The important point for issue `#17` is the shape:

- dispatch is rule-ID driven
- handlers consume match facts
- handlers emit actions, not edits
- handlers may also produce side effects through their context

## Overlap and Conflict Policy

The planner must resolve invalid or conflicting action sets before OmegaEdit applies them.

The initial policy should be conservative:

- reject overlapping edit actions by default
- allow multiple `SIDE_EFFECT` actions over the same span
- allow multiple actions from one match only if they are internally ordered and non-conflicting

Later phases may add more advanced policies, but the initial implementation should prefer correctness and debuggability over cleverness.

Recommended future policy options:

- `STRICT`: fail on any conflicting edit actions
- `FIRST_WINS`: keep the earliest action
- `LAST_WINS`: keep the most recent action
- `RULE_PRIORITY`: prefer explicitly higher-priority rules

## Builtin Operations

The first builtin handlers are expected to be:

- `upper`
- `lower`
- `redact`
- `uuid`

These are a good fit because they cover:

- same-length rewrites
- configurable same-length rewrites
- variable-length replacements
- a side effect path for generated UUID lookup tables

`uuid` is the best example of why matching and editing must be decoupled. The reactor can generate a UUID, emit a `REPLACE` action for the matched span, and separately emit a side effect such as:

- `uuid -> original bytes`
- `uuid -> normalized entity`
- `uuid -> external database record`

No offset adjustment is needed during matching because all offsets refer to the original input.

## Native and Python Participation

The reactor should support three participation lanes:

1. Builtins
   - Fastest path.
   - Configured at runtime, executed in native code.

2. Native plugins
   - Runtime-loaded shared objects.
   - Used for custom performance-sensitive handlers.

3. Python callbacks
   - Most flexible path.
   - Used when developer ergonomics or custom business logic matter more than raw per-match throughput.

Python should still be able to configure builtin handlers, which keeps common transforms on the fast path even for Python users.

## OmegaEdit Integration

OmegaEdit is a strong fit for the apply layer because it already provides the edit primitives the reactor needs:

- overwrite
- insert
- delete
- save

Relevant OmegaEdit examples and APIs in this workspace:

- `extern/omega-edit/core/src/examples/play.cpp`
- `extern/omega-edit/core/src/examples/replay.cpp`
- `extern/omega-edit/core/src/examples/apply_script.cpp`
- `extern/omega-edit/core/src/include/omega_edit/edit.h`

The first OmegaEdit-backed applier should use reverse-order replay for sparse variable-width edits:

1. Sort edit actions by original offset descending.
2. Apply each action against the original-coordinate session.
3. Save the resulting session.

Reverse replay is simple and correct because later actions never need offset adjustment after an earlier replacement grows or shrinks the file.

For workloads where a large fraction of the file changes, a future dense-rewrite path may be faster:

- copy untouched gap
- emit replacement bytes
- continue from the next original span

That optimization should be separate from the initial design.

## Why Not Store Function Addresses?

Storing code pointers in matcher files was considered and rejected.

Reasons:

- pointers are process-local and not portable across runs
- ASLR makes them unstable
- serialized addresses break artifact portability
- it would entangle the matcher format with runtime loader state

Dense runtime dispatch tables give nearly all of the hot-path performance benefit without sacrificing portability.

## Repository Boundary

The reactor should begin life in this repository, but as a clearly separated module.

That gives us:

- fast iteration while the design is still moving
- easy access to OmegaMatch internals and tests
- a clean path to split the reactor into its own repository later if it grows into a broader workflow engine

Recommended initial boundary:

- OmegaMatch core remains matcher-only
- reactor code lives in a separate module or directory
- OmegaEdit integration stays in the reactor layer

## Phased Delivery

This design doc supports the current issue breakdown:

- `#17` Design reactor architecture and action model
- `#18` Implement builtin reactor operations
- `#19` Add OmegaEdit-backed edit script applier
- `#20` Add native plugin reactor API and runtime dispatch table
- `#21` Add Python reactor API for builtins and callbacks
- `#22` Add reactor examples, documentation, and performance coverage

## Summary

The reactor design keeps the system modular and fast:

- OmegaMatch finds matches
- the reactor interprets keyed matches as rule-driven actions
- OmegaEdit applies the resulting edit script

This gives OmegaMatch a clean path into large-scale rewrite, redaction, annotation, enrichment, and side-effect-heavy workflows without bloating the matcher core or sacrificing portability.
