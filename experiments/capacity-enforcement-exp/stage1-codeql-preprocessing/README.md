# Stage 1 — structural preprocessing (CodeQL)

Stage 1 narrows a system's `if` statements (Cassandra ~17k, Hadoop ~44k) **structurally** — by the
shape of the code, with no keyword list — down to a worklist that stage 2
ranks and stage 3 reads. It decides nothing: it cannot tell a capacity check
from any other numeric comparison.

See [`../README.md` §7.2](../README.md#72-discover-and-qualify-candidate-capacity-checks)
for how the three stages relate.

## Where the queries and results live

This folder holds **no queries and no results** — it is the stage-1 entry
point and its notes. The queries are shared infrastructure at the repo root,
because the same CodeQL database serves other work:

| What | Where |
|---|---|
| Queries + their full documentation | [`../../../codeql-queries/cassandra/queries/capacity-enforcement-exp/README.md`](../../../codeql-queries/cassandra/queries/capacity-enforcement-exp/README.md) (Hadoop: [`../../../codeql-queries/hadoop/queries/capacity-enforcement-exp/README.md`](../../../codeql-queries/hadoop/queries/capacity-enforcement-exp/README.md), same logic) |
| Shared predicates | `codeql-queries/common/lib/IfCheckCore.qll` (system-agnostic) + `codeql-queries/<system>/ifcheck/IfCheck.qll` (scope, batching) |
| Results (**gitignored**, regenerate per machine) | `codeql-queries/results/<system>/` |
| Per-system scope, database and counts | [`../cassandra/`](../cassandra/) (counts below) · [`../hadoop/stage1-codeql-preprocessing/README.md`](../hadoop/stage1-codeql-preprocessing/README.md) |
| CodeQL CLI / databases (outside the repo) | `/proj/misconfiguration-PG0/tools/codeql/`, `/proj/misconfiguration-PG0/codeql-dbs/` |

That pipeline README is the single source of truth for what each query does.
Nothing here duplicates it.

## Running it

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
cd <your checkout>/codeql-queries   # the CloudLab copy was removed 2026-10-06 (root README §2); clone the repo to a node's local disk, not under /proj/.../git-repos
./scripts/run-query.sh cassandra cassandra/queries/capacity-enforcement-exp/NarrowedIfStatements.ql
./scripts/run-query.sh cassandra cassandra/queries/capacity-enforcement-exp/HelperGuardedIfStatements.ql
```

Results are gitignored and regenerated per machine, so **no row count here is
pinned to a commit** — re-run before quoting one.

## Output, and what it is worth (Cassandra)

| File | Rows | magnitude | equality |
|---|---|---|---|
| `NarrowedIfStatements.csv` | 4,489 | 2,681 | 1,808 |
| `HelperGuardedIfStatements.csv` | 1,099 | 577 | 522 |
| **Pattern-(a) corpus** | **5,588** | **3,258** | **2,330** |

Funnel: 17,343 `if` statements → 10,147 direct comparisons → 4,489 numeric
non-trivial, plus 1,099 helper-guarded (a sibling query, not a funnel step).
Counts as of 2026-09-22.

## The structural blind spot — why stage 3 also reads raw source

Stage 1 only sees comparisons that sit **in an `if` condition** (or one call
frame down, behind a boolean helper). A capacity check written as a ternary,
an assignment, a `return` expression or a method argument is invisible to it
entirely — no later ranking can recover a row stage 1 never emitted.

This is not hypothetical: the `cdc_total_space` check in
`CDCSizeTracker.processNewSegment()` is a ternary inside a method argument,
so it appears in no stage-1 CSV. It was found by stage 3 reading the source
directly — which is why that feed is a standing obligation and not a
convenience (see [`../stage3-ai-deep-read/README.md`](../stage3-ai-deep-read/README.md)).

Three planned structural extensions are specified and none is written. Since
patterns (b)/(c) were unparked (2026-09-25, `../README.md` §7.5), **none of
them blocks stage 3** — the existing CSVs already contain (b) and (c)
candidates, because the queries filter on a *syntactic* shape (comparison
inside an `if`), not on an enforcement pattern. Only "comparisons anywhere"
closes a real coverage gap; "guard clauses" and "verdict links" are precision
aids for rows already in the corpus.

## Extension beyond `if` (decided 2026-11-11, in progress)

With the rename to `capacity-enforcement-exp`, stage 1 is where new forms of
enforcement places and the capacity-set places are added
([`../README.md` §3.7](../README.md#37-enforcement-places-and-capacity-set-places-2026-11-11)).
This takes up "comparisons anywhere" above and widens it. Stages 2–4 are
unchanged, and the new rows are ordinary feed-3a rows (no new feed).

- **The four existing queries and their output stay frozen.** The stage-2 bands and
  the stage-3 queues are keyed by their `file:line#n` uids.
- **Two new queries, with the same leading columns as the `if` queries** (`path`, `line`,
  `pkg`, `declaringType`, `method`) plus `place` (`enforcement` or `capacity-set`) and
  `pattern` (the form): `EnforcementPlaces.ql` and `CapacitySetPlaces.ql`, with shared
  predicates in `codeql-queries/common/lib/CapacityEnforcementCore.qll`.
- **Enforcement places:**
  - one generalized query takes every comparison that passes the existing
    candidate test (`common/lib/IfCheckCore.qll`) and records its context
    (ternary, loop condition, `return`, boolean assignment, method argument,
    lambda) instead of requiring an `if`. Counted `for` loops (the condition tests
    the loop's own counter) are dropped, like the null and literal-only comparisons
    (decided 2026-11-11 after the pilot);
  - a small API model, matched by method signature and not by identifier names,
    covers comparisons without an operator: `Math.min`/`max`, comparator calls,
    `remaining()`-style methods, bit tests, overflow checks, library calls that
    enforce a capacity (bounded queues, `Semaphore`, cache builders, Netty
    writability), exception handlers, `Preconditions` and `assert`;
  - the helper-guarded query is widened to any call depth, through overrides, and to
    every place a helper's verdict is used, including `switch`.
- **Capacity-set places:**
  - the initializers, assignments and setters of every variable or field that is an
    operand of a candidate comparison (found structurally from the enforcement rows);
  - container creation with a capacity (arrays, `ByteBuffer.allocate*`, bounded
    queues, `Semaphore`, cache builders, sized collections). Initial-size hints are
    included (ruling 2026-11-11);
  - where a size comes from is recorded in a `sizeSource` column (literal, constant,
    field, parameter, call, ...). A size taken from the data shows up as a parameter or a
    call; it is kept, not filtered out, so stage 2 can rank it down.
- **Pilot on Cassandra first.** The report gives the rows per pattern, how many of
  the existing case targets each pattern recovers (in particular the cases found
  only by reading source, such as `cdc_total_space`), and how many rows are new.
  Hadoop follows once the pilot is reviewed. **Pilot report (2026-11-11):**
  [`../cassandra/stage1-codeql-preprocessing/pilot-2026-11-11.md`](../cassandra/stage1-codeql-preprocessing/pilot-2026-11-11.md).
  It found 5,321 new enforcement places (970 of them counted `for` loops) and 2,492
  capacity-set rows. 13 of the 15 case targets the `if` corpus misses are recovered,
  including all three with a real constraint. Open decisions are listed in its §5.
