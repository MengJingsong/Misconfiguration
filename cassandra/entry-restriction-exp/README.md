# Entry-Restriction Experiment — Results Format

Structured results for **Target 1** (identify resource constraints) and
**Target 2** (show how each constraint restricts resource usage) of the
Throttling project, scoped to **Cassandra-5.0.9**.

## Project context (the three targets)

- **Target 1** — identify all resource constraints (config, hardcoded constants, variable types, etc.) that limit memory/CPU usage.
- **Target 2** — show *how* each constraint restricts usage, via the exact code path.
- **Target 3** — investigate bypass methods that could lead to resource exhaustion.

This folder captures **Target 1 + Target 2**. Every pair also seeds Target 3
through its `Bypass Potential` field. The overarching aim of the research is to
replace *indirect proxy* limits with *direct* resource limits, memory first.

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
| `[entry_name]-[NN]-summary.md` | Everything **except** the full code path (metadata, key decision points, enforcement, failure-mode analysis, bypass seed, verification). |
| `[entry_name]-[NN]-codepath.md` | **Only** the full continuous code path for that pair. |

- `[entry_name]` — the entry point name, keeping underscores (e.g. `memtable_heap_space`).
- `[NN]` — zero-padded pair index **within that entry point** (`01`, `02`, ...).
- **Entry Point ID** — the entry name upper-cased (e.g. `memtable_heap_space` → `MEMTABLE_HEAP_SPACE`); shared across all pairs of that entry point.
- The two files cross-link to each other and to `_INDEX.md`.
- When two pairs share a code-path prefix, **repeat** the shared steps in each
  codepath file so every file is self-contained.

## Directory layout

```
cassandra/entry-restriction-exp/
├── README.md                     # this file
├── _INDEX.md                     # master index of every pair (navigation + progress)
├── _TEMPLATE-summary.md          # copy for each new summary file
├── _TEMPLATE-codepath.md         # copy for each new codepath file
└── <entry_name>/                 # one folder per entry point
    ├── <entry_name>-01-summary.md
    ├── <entry_name>-01-codepath.md
    ├── <entry_name>-02-summary.md
    └── <entry_name>-02-codepath.md
```

## Workflow

**Orient (before starting):**

0. Read the Google Docs (*Meeting Summary*, *Progress Report*) for the current plan, scope, and next step.
1. Open `_INDEX.md` to see which entry points/pairs already exist and what's pending — continue from there, don't duplicate.

**Target 1 — discover entry points:**

2. Find candidate constraints in the current scope. Where to look:
   - `conf/cassandra.yaml` (config names), `Config.java` (field declarations), `DatabaseDescriptor.java` (defaults, validation, getters); plus hardcoded constants and typed bounds.
   - Approaches: **AI** (read + reason), **CodeQL** (taint tracking), or **Hybrid** (AI proposes, CodeQL verifies).
   - Current focus scope: the storage-engine memtable path (`org.apache.cassandra.db` + config layer). Use the `memtable_heap_space` pair as the worked reference.

**Target 2 — trace & verify (inseparable from Target 1):**

3. From the entry point, trace the continuous path: **declaration → default/validation → getter → consumer(s) → each place the value gates/limits a resource (enforcement) → action on breach.** Each distinct restriction location = one pair `NN`. An entry point isn't "done" until its restriction path is traced.
4. Fill `-summary.md` and `-codepath.md` from the templates; repeat shared path prefixes so each codepath file is self-contained.
5. Run the failure-mode analysis (proxy / enforcement-point / default) using the legend; record bypass hypotheses in `Bypass Potential` (Target 3 seed).
6. Add/refresh the `_INDEX.md` row and coverage counts; set `Status` (`pending` → `in-progress` → `verified` once checked against the pinned tag).

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

## CodeQL pattern field

The summary's `CodeQL Pattern` field refers to the **3 if-check patterns** used
by the project's CodeQL taint-tracking queries to locate conditionals that
control metadata/resource creation. Those patterns are defined in the repo's
CodeQL scripts (Hadoop work), **not yet transcribed here**.

> **TODO:** document the three if-check patterns in this README so pairs can cite
> them by number. Until then, use `n/a` for manually-traced pairs.

## Related context (for a new session)

- **Google Docs** — *Meeting Summary* and *Progress Report* hold the current plan and next steps; read them first (the Claude project is configured to surface them).
- **Sibling work** — `cassandra/oom-exp/` and `cassandra/constraint-analysis/` in this repo hold related chaos-testing and constraint analysis.
