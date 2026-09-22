# if-check-exp queries

CodeQL queries that narrow Cassandra's ~17k `if` statements down to a shortlist of candidate
memory-capacity checks, for manual triage against the three rules in
[../../../../cassandra/if-check-exp/README.md](../../../../cassandra/if-check-exp/README.md).
Survivors of triage get written up as full case files there; this folder only produces the
CSV working lists that feed that process. Results are gitignored and stay
under `codeql-queries/results/cassandra/`; the AI-filtering verdicts made
from them live in that folder's `candidates/`.

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
3. **`NarrowedIfStatements.ql`** — further **mechanical** (structural, not keyword) narrowing
   of step 2's output: drops comparisons against `null`, comparisons between two literals with
   no variable/call involved, and comparisons whose operands aren't numeric-typed (keeps only
   magnitude comparisons, drops boolean/enum/reference equality checks). ~4,490 rows (down
   from ~10,147). Remaining noise mechanical filtering can't remove without keyword judgment —
   e.g. `index == 0`, comparator results (`compareIPs() < 0`) — is left for step 4.
4. *(in progress)* **Semantic triage** of the remaining rows — for each, judge by reading it
   whether the limit-side operand is capacity/threshold-shaped *and* the subject (operand
   name, enclosing class, or field's declaring type) is memory-related. This is a
   read-and-judge pass, not something expressible as a CodeQL predicate, since there's no
   reliable fixed vocabulary to grep for. Verdicts go to `../../../../cassandra/if-check-exp/candidates/`
   (`positives.md` / `negatives.md` / `deferred.md`).

## Known gap and planned extensions (2026-09-20)

`if-check-exp` now recognizes three enforcement patterns (see
[`../../../../cassandra/if-check-exp/README.md` §3.2](../../../../cassandra/if-check-exp/README.md#3-core-concept-the-if-check-case)):
(a) the capacity check is itself the deciding `if`; (b) the check produces a
verdict — a flag, enum, or return value — that a separate decision point
reads; (c) guard clauses before an allocation that sits outside any branch.
Steps 1–3 above only keep comparisons that sit inside an `if` condition, so
they can miss patterns (b) and (c). Known miss: the `cdc_total_space`
comparison in `CDCSizeTracker.processNewSegment()` (line 335) is a ternary
inside a method argument, so it is not in `NarrowedIfStatements.csv`; only
an unrelated `if` in the same method was.

Planned structural (still non-keyword) extensions, not yet written:

1. **Comparisons anywhere** — the same numeric-comparison narrowing as step
   3, but over all comparison expressions, not only those inside an `IfStmt`
   condition (ternaries, assignments, `return` expressions, method
   arguments), reporting the enclosing statement kind.
2. **Guard clauses** — `if` statements with a numeric comparison whose
   then-branch ends in `throw` or `return`, for pattern (c); candidates are
   later checked for an allocation that the guard dominates.
3. **Verdict links** — writes of a boolean/enum field (or a returned
   boolean/enum) whose value derives from a comparison, joined to the `if`
   conditions that read that field or call that method, for pattern (b).

As with steps 1–3, these only shrink the search space; whether a row
qualifies is still decided by reading it (README §3.4–§3.6).

## Running

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
cd /proj/misconfiguration-PG0/git-repos/misconfiguration/codeql-queries
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/NarrowedIfStatements.ql
```

Output lands in `results/cassandra/<QueryName>.csv` (gitignored).
