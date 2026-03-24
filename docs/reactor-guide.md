# Reactor Guide

This guide turns the reactor architecture into something practical:

- what each layer does
- which API to reach for
- how to pick between builtin, native plugin, and Python callback lanes
- where to find runnable examples

## Quick Model

The rewrite stack now has three explicit layers:

1. OmegaMatch finds keyed matches.
2. A reactor turns those keyed matches into rewrite actions and side effects.
3. A rewrite script or OmegaEdit session applies the byte edits.

That separation matters because it keeps offsets stable:

- matching always happens on the original input
- rewrites happen afterward
- variable-width replacements never disturb later match coordinates

## Choosing a Lane

Use the fastest lane that still expresses the behavior you need.

| Lane | Best for | Hot path |
|------|----------|----------|
| Builtins | upper/lower/redact/uuid | native |
| Native plugins | custom high-performance handlers | native |
| Python callbacks | bespoke transforms and side effects | native match + Python action emission |

Practical rule:

- if a builtin can do it, use the builtin
- if it needs custom native logic, use a plugin
- if it needs Python business logic or external integration, use a Python callback

## Core Python Shapes

The Python API now exposes:

- `BuiltinReactor` for direct low-level builtin use
- `NativePluginReactor` for plugin-backed handlers
- `Reactor` as the higher-level Python API
- `RewriteAction`, `ReactorEmission`, and `ReactorSideEffect`
- `RewriteScript` for replay and optional OmegaEdit-backed file application

## End-to-End Flow

Typical Python flow:

```python
from omega_match import Compiler, Matcher, Reactor, RewriteAction

with Compiler("rules.olm") as compiler:
    compiler.add_pattern(b"SECRET", key=1)
    compiler.add_pattern(b"alice", key=2)

with Matcher("rules.olm") as matcher, Reactor() as reactor:
    reactor.add_builtin(1, "redact", redact_byte=ord("X"))
    reactor.add_callback(2, lambda match: RewriteAction.replace(match, b"PERSON-1"))

    emission = reactor.plan(matcher, b"alice shared a SECRET")
    rewritten = reactor.rewrite_bytes(matcher, b"alice shared a SECRET")
```

`Reactor.plan(...)` returns:

- `actions`: byte edits that can be lowered into a `RewriteScript`
- `side_effects`: out-of-band records for audit trails, UUID maps, link tables, and similar metadata

## Examples

Runnable Python examples live in:

- `bindings/python/examples/reactor_redactor.py`
- `bindings/python/examples/reactor_uuid_sidecar.py`
- `bindings/python/examples/reactor_hyperlinks.py`
- `bindings/python/examples/reactor_acronyms.py`
- `bindings/python/examples/reactor_benchmark.py`

These cover:

- builtin redaction
- UUID replacement with sidecar metadata
- hyperlink annotation
- acronym expansion
- a small benchmark comparing matcher-only, builtin reactor, and Python callback paths

The functional examples above are smoke-tested through the Python test suite, so they
travel with the same CI regression net as the rest of the binding surface. The
benchmark example is intended as a runnable workload sketch rather than a strict
pass/fail performance gate.

If you want file-backed replay through OmegaEdit in a local build, configure CMake
with `-DOMEGA_MATCH_ENABLE_OMEGA_EDIT=ON` and keep a checkout available at
`extern/omega-edit`. OmegaMatch now consumes OmegaEdit in its upstream embed mode.

## Rewrite Scripts

`RewriteScript` is the concrete replay form between the reactor and the editor.

Today it supports:

- low-level edit ops for delete/insert/overwrite
- in-memory replay
- optional OmegaEdit-backed file replay when OmegaEdit is available in the build

The default overlap policy is strict:

- overlapping edit actions are rejected
- side effects remain allowed because they do not mutate bytes

## OmegaEdit Path

When OmegaEdit is present in the build, the same rewrite script can be applied to a file-backed session:

```python
with reactor.build_script(matcher, haystack) as script:
    script.apply_omega_edit("input.txt", "output.txt")
```

That is the large-file path.

For small buffers or tests, `rewrite_bytes(...)` and `RewriteScript.apply_bytes(...)` are usually the simplest route.

## Performance Notes

Performance expectations are intentionally explicit:

- matcher-only is the baseline
- builtin/native reactors stay on the native fast path
- Python callbacks are the flexible lane and cost more per emitted action

If Python callbacks become hot:

- push common logic down into builtins or plugins
- batch work where practical
- keep side effects lightweight during the hot pass

## Current Guardrails

The current test/benchmark surface covers:

- overlap rejection
- reverse-order replay correctness
- OmegaEdit-backed file replay smoke coverage
- native plugin registration and dispatch
- Python builtin and callback behavior

Use the benchmark example as a starting point for workload-specific measurements rather than treating it as a definitive throughput report.
