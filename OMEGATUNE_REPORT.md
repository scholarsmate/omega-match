# OMEGATUNE — OmegaMatch Autonomous Optimization Journal

This file is the persistent memory for an overnight autonomous optimization
campaign driven by fresh Hermes cron sessions. Each session reads this file
first, performs exactly ONE bounded experiment, appends the result, and exits.

## Standing rules

- Work happens ONLY on branch `perf/omega-tune-2026-09` in the worktree
  `/home/davin/git/OMEGA/omega-match-tune`. Never modify `main`.
- Never push to any remote.
- Never discard pre-existing user work; verify `git status` before changes.
- Never remove or weaken correctness tests.
- Never report a performance improvement without measurements.
- One experiment per session. Do not start a second experiment.

## Campaign state

- Current accepted branch: `perf/omega-tune-2026-09`
- Current HEAD at campaign start: 407f128 (same as origin/main)
- Current accepted baseline: TBD — first session must establish and record it.

## Original baseline

To be recorded by the first session: environment (CPU, compiler, flags),
benchmark methodology (see `perf_test.py`, `scripts/`, `DEVELOPMENT.md`),
repetition count, and per-case numbers against 407f128.

## Benchmark methodology

Record the exact commands used. Existing harness: `perf_test.py`
(documented in `DEVELOPMENT.md` / `README.md`). Build preset available:
`build-gcc-release`. Use enough repetitions to distinguish signal from
normal variance and state the noise margin.

## Accepted experiments

(none yet)

## Rejected / inconclusive experiments

(none yet)

## Known dead ends

(none yet)

## Recommended next experiments

(none yet — first session: profile and propose a queue here.)

## Profiling findings

(none yet)
