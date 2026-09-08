# Entry-Restriction Experiment — Results Format

Structured results for **Target 1** (identify resource constraints) and
**Target 2** (show how each constraint restricts resource usage) of the
Throttling project, scoped to **Cassandra-5.0.9**.

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
- The two files cross-link to each other and to `_INDEX.md`.

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

1. Identify an entry point (Target 1).
2. For each restriction location it reaches, create a pair `NN`.
3. Fill `-summary.md` from `_TEMPLATE-summary.md` and `-codepath.md` from
   `_TEMPLATE-codepath.md`.
4. Add a row to `_INDEX.md`.
5. Verify the code path (Target 2) and update the pair's `Status`.

## Failure modes checked per pair

- **Proxy mismatch** — constraint limits a proxy weakly correlated with actual resource usage.
- **Enforcement-point mismatch** — check runs at the wrong lifecycle stage (after resource already used).
- **Default-off** — constraint disabled by default.
