# if-check-exp queries

CodeQL queries that narrow Cassandra's ~17k `if` statements down to a shortlist of candidate
memory-capacity checks, for manual triage against the three rules in
[../../../../cassandra/if-check-exp/README.md](../../../../cassandra/if-check-exp/README.md).
Survivors of triage get written up as full case files there; this folder only produces the
CSV working lists that feed that process (see `candidates/` in that folder).

CodeQL narrows the search space mechanically (structure of the code); it cannot judge whether
a check is actually a *memory*-capacity check — that's a semantic call made by reading each
row, not a fixed keyword filter, since real cases (`memtable_heap_space`,
`HintsBufferPool_MAX_ALLOCATED_BUFFERS`, ...) don't share vocabulary predictably enough for
one to be reliable.

## Pipeline

1. **`AllIfStatements.ql`** — every `if` statement in `src/java/...`. Pure inventory, no
   filtering. ~17,343 rows.
2. **`ComparisonIfStatements.ql`** — narrows to `if` conditions that are a direct comparison
   (`<`, `<=`, `>`, `>=`, `==`, `!=`) between two operands, with a best-effort name for each
   operand (variable/field name, method-call name, or literal text) plus file/line/enclosing
   class/method. ~10,147 rows.
3. *(planned)* Further **mechanical** (structural, not keyword) narrowing — e.g. drop
   comparisons against `null`, drop comparisons between two literals with no variable
   involved, drop comparisons whose operand types are booleans/enums. Not yet a separate
   query file.
4. *(planned)* **Semantic triage** of the remaining rows — for each, judge by reading it
   whether the limit-side operand is capacity/threshold-shaped *and* the subject (operand
   name, enclosing class, or field's declaring type) is memory-related. This is a
   read-and-judge pass, not something expressible as a CodeQL predicate, since there's no
   reliable fixed vocabulary to grep for. Survivors go to `../../../../cassandra/if-check-exp/candidates/`.

## Running

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
cd /proj/misconfiguration-PG0/git-repos/misconfiguration/codeql-queries
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/ComparisonIfStatements.ql
```

Output lands in `results/cassandra/<QueryName>.csv` (gitignored).
