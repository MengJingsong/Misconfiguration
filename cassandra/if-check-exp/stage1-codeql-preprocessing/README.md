# Stage 1 — structural preprocessing (CodeQL)

Stage 1 narrows Cassandra's ~17k `if` statements **structurally** — by the
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
| Queries + their full documentation | [`codeql-queries/cassandra/queries/if-check-exp/`](../../../codeql-queries/cassandra/queries/if-check-exp/README.md) |
| Shared predicates | `codeql-queries/cassandra/ifcheck/IfCheck.qll` |
| Results (**gitignored**, regenerate per machine) | `codeql-queries/results/cassandra/` |
| CodeQL CLI / databases (outside the repo) | `/proj/misconfiguration-PG0/tools/codeql/`, `/proj/misconfiguration-PG0/codeql-dbs/` |

That pipeline README is the single source of truth for what each query does.
Nothing here duplicates it.

## Running it

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
cd /proj/misconfiguration-PG0/git-repos/misconfiguration/codeql-queries
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/NarrowedIfStatements.ql
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/HelperGuardedIfStatements.ql
```

Results are gitignored and regenerated per machine, so **no row count here is
pinned to a commit** — re-run before quoting one.

## Output, and what it is worth

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
at any tier.

This is not hypothetical: the `cdc_total_space` check in
`CDCSizeTracker.processNewSegment()` is a ternary inside a method argument,
so it appears in no stage-1 CSV. It was found by stage 3 reading the source
directly — which is why that feed is a standing obligation and not a
convenience (see [`../stage3-ai-deep-read/README.md`](../stage3-ai-deep-read/README.md)).

Three planned structural extensions (comparisons anywhere, guard clauses,
verdict links) would close part of the gap; none is written, and all wait on
the pattern-(b)/(c) resumption (`../README.md` §7.5).
