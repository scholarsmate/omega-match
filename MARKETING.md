# OmegaMatch — High-Throughput Multi‑Pattern Text Matching Engine

OmegaMatch is a fast, embeddable, multi‑pattern exact matcher for products and platforms that need to scan large text streams against thousands of patterns **in near real time**. It couples a memory‑mapped compiled pattern store with cache‑efficient data structures, multi‑threaded execution (OpenMP), and optional normalization (case‑insensitive, punctuation‑ignoring, whitespace‑eliding) — all in a lean Apache 2.0 licensed package.

> Build search, compliance, moderation, enrichment, deduplication, or security pipelines that must never become the bottleneck.

---
## At a Glance
| Capability | What it means for you |
|------------|------------------------|
| Memory‑mapped compiled pattern store | Compile once and reuse with low matcher setup cost. |
| Multi-threaded (OpenMP) core | Parallel matching with configurable thread counts. |
| Profile-Guided Optimization (PGO) builds | Optional Linux GCC/Clang and Windows MSVC variants; gains are workload-dependent and measurable with the included harness. |
| Two-tier pipeline (Bloom + hash table) | Rejects many non-matches before exact lookup. |
| Specialized short‑pattern accelerator | Ultra-fast handling of 1–4 byte patterns (bitmap + binary search). |
| Rich post-filters | Word/line anchors, longest-only, no-overlap, prefix/suffix constraints. |
| Transform layer | Case-insensitive, ignore punctuation, elide whitespace — without per-call reallocation. |
| Deterministic & exact | No false positives (Bloom pre-filters only; exact hash validation). |
| Cross-platform | Windows, Linux, macOS (C library + Python bindings + CLI tools). |
| Low operational footprint | Share the same compiled pattern file across processes; minimal per-instance memory. |
| Apache 2.0 FOSS | Use in commercial, cloud, on-prem, embedded — no licensing friction. |

---
## Why Teams Adopt OmegaMatch
1. **Throughput Headroom** — Keeps pace with high-volume ingestion (logs, chat, email, documents) without sharding complexity.
2. **Operational Simplicity** — Pattern lists become artifacts you can version, sign, ship, and hot‑reload.
3. **Predictable Latency** — Pure CPU, no GC pauses, no dynamic regex backtracking explosions.
4. **Feature Pragmatism** — Focused on *exact multi-pattern* matching with powerful structural filters, not an overgeneral regex VM.
5. **Transparent Performance** — Benchmarked openly (includes its own performance harness). PGO builds available for maximum optimization.
6. **Extensible Surface** — Clean C API plus Python module and CLI tools for rapid integration and prototyping.

---
## Core Differentiators
- **Compile → Map → Match** workflow decouples pattern management from runtime workloads.
- **Cache-conscious layout** — Patterns clustered; short patterns fast‑pathed; streaming k‑way merge enables linear post‑filter passes.
- **Selective transforms** — Applied only when requested; no permanent preprocessing cost.
- **Pluggable concurrency** — Tune thread count and chunk size to balance throughput vs. tail latency.

---
## Supporting Higher-Level DSLs (e.g., OmegaOMG)
Higher‑level rule / grammar DSLs (such as **OmegaOMG**) can layer on top of OmegaMatch. OmegaMatch contributes:
- High‑throughput literal multi‑pattern baseline feeding grammar evaluation.
- Pre‑anchored longest / non‑overlapping match streams that reduce downstream search.
- Memory‑mapped compiled store for fast cold starts and concurrent evaluators with minimal overhead.
- Structural filters (word / line boundaries, prefix / suffix) to prune impossible spans early.
- Optional normalization (case‑insensitive, ignore punctuation, elide whitespace) applied consistently before higher‑level assembly.
- Deterministic, stable match offsets for reliable resolver / AST mapping.

This lets the DSL runtime focus on rule semantics while delegating raw scanning to OmegaMatch.

---
## Performance Snapshot (Representative Excerpts)

The September 2026 Linux/WSL2 snapshot used 29,156 patterns, a warm 256 MiB
corpus on a native Linux filesystem, and complete output from every tool.
OmegaMatch used eight OpenMP threads; GNU grep was single-threaded, and
ripgrep received `-j 8`. Values are medians, not guarantees.

| Scenario | OmegaMatch PGO | GNU grep 3.11 | ripgrep 15.2 |
|----------|---------------:|--------------:|---------------:|
| longest + no-overlap | 266 MiB/s | 196 MiB/s | 129 MiB/s |
| line start | 1,018 MiB/s | 24 MiB/s | 252 MiB/s |
| line end | 606 MiB/s | 27 MiB/s | 51 MiB/s |

OmegaMatch loaded a persisted pattern store compiled before timing, whereas
grep and ripgrep parsed patterns on every invocation. The anchored comparator
times include construction of 29,156 regular expressions; the line-end case
has zero matches in this corpus. See the
[performance methodology](DEVELOPMENT.md#performance-testing) and reproduce
the comparison with `scripts/benchmark_scaling.py` on your own data.

---
## Ideal Use Cases
| Domain | Examples |
|--------|----------|
| Security & Threat Intel | IOC / keyword sweeps across logs, email gateways, DLP scanners. |
| Trust & Safety / Moderation | Disallowed phrases, brand abuse, impersonation handles. |
| Compliance & Governance | Policy term detection (PII tokens, restricted lexicons). |
| Data Enrichment / ETL | Tagging entities (names, TLDs, usernames) before downstream NLP. |
| Deduplication / Filtering | Fast elimination of already-known markers or signatures. |
| Content Analytics | Pre-filter candidate spans before heavier semantic / ML stages. |

If your workload involves (a) large text streams, (b) thousands of *literal* patterns, and (c) strict latency / throughput targets — OmegaMatch is purpose‑built.

---
## How It Works (Internal Pipelines)

### 1. Compilation (one-time or on pattern change)
```
patterns.txt
  │  (read & parse; normalize options flags)
  ▼
Pattern Store Builder ──> store literals contiguously
  │
  ├── Build Short Matcher (len1..len4 bitmaps/arrays)
  ├── Build Bloom Filter (n hashes, sized by pattern set)
  ├── Build Hash Table (index array + bucket data for ≥5)
  ▼
Serialize Header + [Pattern Store][Bloom][Hash][Short Matcher]
  ▼
Binary File (memory‑mappable)
```

### 2. Runtime (long patterns ≥5)
```
Memory‑map compiled file (O(1) startup)
  │
  │ (optional transform table active?)
  ├── Yes: chunked normalize window (case / punct / ws) + offset map
  │       ▼
  │   Normalized chunk
  │
  │ (OpenMP / threaded scan over haystack positions)
  ▼
Boundary Fast Check (word/line anchors pre-skip)
  │ (if remaining ≥4 bytes)
  ▼
Pack 4‑gram → Bloom Filter
  │  (likely reject → skip)
  │  (pass)
  ▼
Hash Probe → Bucket Scan (exact compare, append matches)
  ▼
Per‑thread Match Vectors
  ▼ (merge)
K‑way Merge (offset asc, length desc)
  ▼
Post Filters (longest-only → no-overlap; residual boundary / prefix / suffix checks)
  ▼
Result Set (stable offsets remapped if normalized)
```

### 3. Runtime (short patterns 1–4)
Runs in the same positional scan; short path is independent of Bloom/Hash.
```
Position Scan
  │
  ├── Optional boundary pre-check (skip if not at potential boundary when required)
  │
  ├── len4 array binary search (if any len4 patterns)
  ├── len3 array binary search (if any len3 patterns)
  ├── len2 array bitmap / array lookup
  └── len1 bitmap lookup
      (each successful probe emits candidate; boundary / line / prefix / suffix validated)
  ▼
Short Matches Appended
  (coalesced with long pattern matches before k‑way merge)
```

### 4. Optional Transform Path
When normalization flags are set, each chunk is transformed (case fold, punctuation stripped, whitespace elided) with a position map so match offsets are remapped back to the original haystack after matching.

### 5. Output Guarantees
- Exact literal matches (no false positives beyond requested filters).
- Offsets stable and deterministic (post normalization remap if used).
- Ordering invariant: primary sort offset ascending, secondary length descending.
  - Enables O(n) longest-only (first at offset is longest) and O(n) no-overlap (single forward pass) post-filters.

---
## Quick Start (C)
```c
#include <omega/list_matcher.h>
omega_list_matcher_t *m = omega_list_matcher_create("patterns.txt", /*case_insensitive=*/0, /*ignore_punctuation=*/0, /*elide_ws=*/0, NULL);
// ... load data into buffer ...
omega_match_results_t *r = omega_list_matcher_match(m, data, len, /*no_overlap=*/1, /*longest_only=*/1, /*word_boundary=*/1, /*word_prefix=*/0, /*word_suffix=*/0, /*line_start=*/0, /*line_end=*/0);
// iterate r->matches
omega_match_results_destroy(r);
omega_list_matcher_destroy(m);
```

## Quick Start (Python)
```python
from omega_match.omega_match import Compiler, Matcher

# Compile once (creates matcher.olm). You can also stream patterns with Compiler().
stats = Compiler.compile_from_filename("matcher.olm", "patterns.txt", case_insensitive=True)
print("Patterns compiled:", stats.stored_pattern_count + stats.short_pattern_count)

# Auto-selects best native variant (prefers PGO when bundled)
with Matcher("matcher.olm") as matcher:
  hay = open("haystack.txt", "rb").read()
  results = matcher.match(hay, word_boundary=True, longest_only=True, no_overlap=True)
  for r in results:
    print(r.offset, r.length)
```

## Quick Start (Python CLI)
```bash
# Compile patterns
python bindings/python/olm.py compile patterns.olm patterns.txt --ignore-case

# Match with output to file
python bindings/python/olm.py match patterns.olm haystack.txt --output results.txt --word-boundary --longest
```

---
## Adoption Path
1. Identify your static (or periodically updated) pattern list(s).
2. Compile once (implicitly on first create) and store alongside app artifacts.
3. Memory-map in each worker/process (startup remains lightweight).
4. Tune thread count (`OMP_NUM_THREADS` or API) and chunk size for workload.
5. Layer domain logic (e.g., entity tagging, suppression) on returned offsets.

---
## Architectural Advantages
- **Zero‑copy pattern sharing** — Multiple workers reuse the same mapped file.
- **Branch locality** — Short path for most non‑matching positions (early rejection via boundary + Bloom).
- **Deterministic post‑filters** — Order‑independent final semantics (idempotent longest / no‑overlap passes).
- **Incremental scalability** — Add CPU cores; no specialized hardware or external indexing cluster.

---
## Comparison (Conceptual)
| Approach | Trade-offs |
|----------|-----------|
| Naïve N×M substring scans | O(N·M) work; cache-thrashing; no sharing. |
| Regex engine per pattern set | Higher compile cost + backtracking risk; overkill for literals. |
| Inverted index / search engine | Heavy ingestion / memory; tuned for term search, not anchored literal spans. |
| GPU / SIMD bespoke solution | Higher complexity & maintenance; narrower developer familiarity. |
| OmegaMatch | Purpose-built, balanced complexity vs. performance; portable; exact semantics. |

---
## Transparency & Limits
OmegaMatch is optimized for **exact literal multi‑pattern matching with structural filters**. It is **not** a general regex engine, fuzzy matcher, or semantic classifier. For fuzzy or NLP tasks, use it as a *front‑line accelerator* to reduce candidate volume before heavier processing.

---
## Licensing & Governance
- **License:** Apache License 2.0 (permissive, patent grant included)
- **Commercial use:** Allowed — bundle, modify, redistribute with attribution.
- **Contribution model:** Standard fork + PR; CLA not required (see repository guidelines).

---
## Roadmap Ideas (Community-Driven)
- Incremental / delta pattern compilation.
- Streaming window API (bounded latency on unbounded sources).
- Pluggable custom normalization tables.
- Optional SIMD path exploration for additional micro-gains.
- Language bindings (Rust, Go) if demand surfaces.

> Want one of these sooner? Open an issue or contribute a design proposal.

---
## Integrate Today
| Goal | Action |
|------|--------|
| Evaluate performance | Run `perf_test.py` on your corpus. |
| Prototype quickly | Use Python binding in a notebook or script. |
| Production embed | Link C library, ship compiled pattern store. |
| Share feedback | File issues (features, perf anomalies, datasets). |
| Contribute | Improve docs, port bindings, add benchmarks. |

**Call to Action:** Clone. Benchmark. Replace brittle multi‑regex loops. Ship faster.

```
git clone https://github.com/scholarsmate/omega-match
cd omega-match
python perf_test.py --show-status
```

---
## Contact & Community
- GitHub Issues: feature requests & bugs
- Discussions: architecture, optimization, design questions
- PRs: Welcome — focus on measurable performance or clarity improvements

> If OmegaMatch saves you infrastructure or developer time, consider starring the repo and sharing a benchmark comparison — it helps the ecosystem grow.

---
**Build the fastest multi‑pattern literal filter layer in your stack — with OmegaMatch.**
