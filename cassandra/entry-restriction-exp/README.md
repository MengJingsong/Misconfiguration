# Entry-Restriction Experiment — Results Format

Structured results for **Target 1** (identify resource constraints) and
**Target 2** (show how each constraint restricts resource usage) of the
misconfiguration project, scoped to **Cassandra-5.0.9**.

## Project context (the three targets)

- **Target 1** — identify all resource constraints (config, hardcoded constants, variable types, etc.) that limit memory/CPU usage.
- **Target 2** — show *how* each constraint restricts usage, via the exact code path.
- **Target 3** — investigate bypass methods that could lead to resource exhaustion.

This folder captures **Target 1 + Target 2**. Every pair also seeds Target 3
through its `Bypass Potential` field. The overarching aim of the research is to
replace *indirect proxy* limits with *direct* resource limits, memory first.

### How this folder finds pairs — and how it differs from `if-check-exp`

**Method: AI deep read, constraint-first.** An AI session reads the Cassandra
source and works *forward* from a resource constraint: starting at the place
the constraint is declared or initialised, it traces where that value flows
and finds the locations where it actually restricts something. Each such
location becomes a pair. **Every real pair is manually checked** before being
recorded — the AI trace locates candidates, a human confirms them.

This is the mirror image of the sibling folder. Both serve Target 1 + 2 and
both read source, but they enter from opposite ends:

| | `entry-restriction-exp` (this folder) | `if-check-exp` |
|---|---|---|
| Starts from | the **constraint's declaration** | the **code that enforces a limit** |
| Traces | forward: declaration → restriction sites | backward: check → the limit's declaration |
| Unit of record | an `(entry point, restriction location)` pair | an if-check case |
| Confirmation | manual check of each pair | the three rules (its README §3.4–§3.6) |

Neither is a subset of the other, and **they are deliberately not
cross-referenced** — a line may legitimately appear in both.

> **`if-check-exp`'s stage numbers do not apply here.** That folder numbers
> its own working stages (structural → lexical → semantic) to say how
> strongly a line has been evidenced. This folder has no such ladder; it is
> deep reading plus manual confirmation throughout. The **targets**, by
> contrast, are project-wide and shared — see the repo-root
> [`README.md`](../../README.md) §0.

## Source of truth (version pinning — read this first)

Every `file:line` reference in these results is pinned to one exact source ref:

```
git clone --depth 1 --branch cassandra-5.0.9 https://github.com/apache/cassandra.git
```

**All line numbers are only valid for `apache/cassandra` @ tag `cassandra-5.0.9`.**
Before trusting or extending any pair, check out that exact tag and re-verify the
lines — a different checkout (trunk, another patch release) will drift. Each pair
file restates its source ref in the header for this reason.

## Core concept: the entry-restriction pair

An **entry point** is a resource constraint — a config, hardcoded constant,
variable type, etc. — that limits memory/CPU usage.

A single entry point may restrict resource usage at **several** locations in
the code. Each `(entry point, one restriction location)` combination is an
**entry-restriction pair** and is recorded independently.

## Files per pair

Each pair is recorded in **two** markdown files:

| File | Content |
|------|---------|
| `[entry_name]-[NN]-summary.md` | Everything **except** the full code path (metadata, key decision points, enforcement, failure-mode analysis, bypass seed, verification). Use `_TEMPLATE-summary.md` as reference. |
| `[entry_name]-[NN]-codepath.md` | **Only** the full continuous code path for that pair. Use `_TEMPLATE-codepath.md` as reference. |

### Naming
- `[entry_name]` — the entry point name, keeping underscores (e.g. `memtable_heap_space`).
- `[NN]` — zero-padded pair index **within that entry point** (`01`, `02`, ...).
- **Entry Point ID** — the entry name upper-cased (e.g. `memtable_heap_space` → `MEMTABLE_HEAP_SPACE`); shared across all pairs of that entry point.

### Cross-linking and self-containment
- The two files cross-link to each other and to `_INDEX.md`.
- When two pairs share a code-path prefix, **repeat** the shared steps in each codepath file so every file is self-contained.

### Code-trace steps (case-specific, not generic)

> **"Code-trace steps" here are not `if-check-exp`'s numbered stages.** These are the
> hops along one constraint's code flow, named per case. They were called
> "stages" before that word was given a different meaning in the sibling
> folder (2026-09-23); renamed to keep the two apart.

- Codepath files trace constraint from declaration/init through enforcement to action.
- **Code-trace steps are extracted from the actual code flow** — configuration parameters, hardcoded constants, factory methods, queues, and distributed constraints have different patterns.
  - **Configuration parameter example** (memtable_heap_space): declaration → load → validate → store → read → check → action
  - **Hardcoded/factory example** (memtable_flush_writers queue): factory definition → pool init → submission → queue state → execution → (missing backpressure)
- Each codepath file defines its own code-trace steps based on the specific constraint type; do not force a generic pattern.
- Each `Location` cell **links** to the pinned source on GitHub — short display text (`File.java:NN`), full path in the href (`…/blob/cassandra-5.0.9/<path>#Lnn`).

## Directory layout

```
cassandra/entry-restriction-exp/
├── README.md                     # this file
├── _INDEX.md                     # master index of every pair (navigation + progress)
├── _TEMPLATE-summary.md          # template for each new summary file
├── _TEMPLATE-codepath.md         # template for each new codepath file (table + flexible notes)
└── <entry_name>/                 # one folder per entry point
    ├── <entry_name>-01-summary.md
    ├── <entry_name>-01-codepath.md
    ├── <entry_name>-02-summary.md
    └── <entry_name>-02-codepath.md
```

## Workflow

**Orient (before starting):**

0. Read the Google Docs ([*Meeting Summary*](https://docs.google.com/document/d/1tldFFEk28qtQD0QdsnC2Br-BisTyOUp8OCwG1SZ_6Jk/edit), [*Progress Report*](https://docs.google.com/document/d/1gMRFwaTvgahSiRi10ad_Y3CLDkxyF1QTYkAhZ4be4x8/edit)) for the current plan, scope, and next step.
1. Open `_INDEX.md` to see which entry points/pairs already exist and what's pending — continue from there, don't duplicate.

**Target 1 — discover entry points:**

2. Find candidate constraints in the current scope. Where to look:
   - `conf/cassandra.yaml` (config names), `Config.java` (field declarations), `DatabaseDescriptor.java` (defaults, validation, getters); plus hardcoded constants and typed bounds.
   - Approaches: **AI** (read + reason), **CodeQL** (taint tracking), or **Hybrid** (AI proposes, CodeQL verifies).
   - Current focus scope: the storage-engine memtable path (`org.apache.cassandra.db` + config layer). Use the `memtable_heap_space` pair as the worked reference.

**Target 2 — trace & verify (inseparable from Target 1):**

3. From the entry point, trace the continuous path from declaration/initialization through to enforcement and action on breach. **The specific code-trace steps depend on the constraint type:**
   - **Configuration parameters** (like `memtable_heap_space`): declaration → load/parse → validate → store limit → read/getter → transform → check → action
   - **Hardcoded constants or factory defaults** (like `ExecutorPlus.pooled()`): factory definition → pool/object initialization → usage/submission → state evolution → (enforcement or missing enforcement)
   - **Distributed or implicit constraints** (like per-disk pools): initialization → routing → per-pool behavior → cascade effects
   
   Each distinct restriction location = one pair `NN`. An entry point isn't "done" until all its restriction paths are traced.

4. Fill `-summary.md` and `-codepath.md` from the templates; repeat shared path prefixes so each codepath file is self-contained. **Key Decision Points in summary should reflect your constraint's specific enforcement chain (may be 3 points, 5 points, 7 points, or different sequence).**

5. Run the failure-mode analysis (proxy / enforcement-point / default) using the legend; record bypass hypotheses in `Bypass Potential` (Target 3 seed).

6. Add/refresh the `_INDEX.md` row and coverage counts; set `Status` (`pending` → `in-progress` → `verified` once the cited lines are checked against the pinned tag — `verified` means *citations checked*, not *behavior tested*).

**Drafting convention:** draft new/changed result files in the Claude session
first for review, then push to `main` after approval.

## Failure modes checked per pair

Three ways a guardrail can fail to actually bound the resource:

- **Proxy mismatch** — constraint limits a proxy weakly correlated with actual resource usage.
- **Enforcement-point mismatch** — check runs at the wrong lifecycle stage (after the resource is already used).
- **Default-off** — constraint disabled by default.

### Failure-mode legend (symbol polarity)

In the summary's Failure Mode Analysis table, the symbol always encodes
*"is this failure mode present?"* — **✗ = the weakness is present (a finding)**:

| Symbol | Meaning | Proxy Match | Enforcement Point | Default State |
|--------|---------|-------------|-------------------|---------------|
| **✓** | no weakness on this axis | measures the actual resource | checked **before** the resource is used | enabled by default, constraint active |
| **⚠** | partial / at risk | proxy loosely correlated | checked late, or after-the-fact with mitigation (e.g. async reclaim) | enabled but weak/soft default |
| **✗** | weakness present (finding) | proxy weakly correlated / mismatch | after the resource is already used, or bypassable | disabled by default (default-off) |

## Related context (for a new session)

- **Google Docs** — [*Meeting Summary*](https://docs.google.com/document/d/1tldFFEk28qtQD0QdsnC2Br-BisTyOUp8OCwG1SZ_6Jk/edit) (per-meeting decisions and next steps) and [*Progress Report*](https://docs.google.com/document/d/1gMRFwaTvgahSiRi10ad_Y3CLDkxyF1QTYkAhZ4be4x8/edit) (running log of entry points, cases and findings). Both live in Jingsong's Google Drive; a session with the Google Drive connector enabled can read them directly.
- **Sibling work** — [`cassandra/if-check-exp/`](../if-check-exp/README.md), the repo's active experiment, covers the same Target 1 + 2 from the opposite direction (from the enforcing check back to the constraint). The two are deliberately **not** cross-referenced — see that folder's README §4. The older `cassandra/oom-exp/` chaos-testing experiments were removed in `52a621a`, superseded by `cassandra/build-cassandra-dist/` on Cassandra 5.0.9.
