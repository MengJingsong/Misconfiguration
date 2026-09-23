# if-check-exp queries

CodeQL queries that narrow Cassandra's ~17k `if` statements down to a shortlist of candidate
capacity checks (**memory or disk** — disk entered scope 2026-09-18), for manual triage
against the three rules in
[../../../../cassandra/if-check-exp/README.md](../../../../cassandra/if-check-exp/README.md).
Survivors of triage get written up as full case files there; this folder only produces the
CSV working lists that feed that process. Results are gitignored and stay
under `codeql-queries/results/cassandra/`; the AI-filtering verdicts made
from them live in that folder's `stage2-ai-filtering/`.

CodeQL narrows the search space mechanically (structure of the code); it cannot judge whether
a check is actually a capacity check — that's a semantic call made by reading each row, not a
fixed keyword filter, since real cases (`memtable_heap_space`, `MAX_HINT_BUFFERS`,
`cdc_total_space`, ...) don't share vocabulary predictably enough for one to be reliable.

**Current scope: enforcement pattern (a) only** (see
[`../../../../cassandra/if-check-exp/README.md` §7.5](../../../../cassandra/if-check-exp/README.md)).
`NarrowedIfStatements.ql` selects numeric comparisons whose enclosing statement is an `if` —
structurally exactly pattern (a) — so the pipeline below already fits that scope with **no
changes needed**. The three planned extensions further down exist only to surface patterns
(b) and (c), which are parked until (a) is finished.

## Shared predicates

`isNumeric`, `operandName`, `pkgDir`, `opClass` and `isCandidateComparison` live in
[`cassandra/ifcheck/IfCheck.qll`](../../ifcheck/IfCheck.qll), imported as
`import ifcheck.IfCheck`. They were previously copy-pasted into each query, which risked the
queries drifting apart on what counts as "numeric" or "a candidate comparison". The library is
Cassandra-local rather than in `common/` because it encodes this experiment's notion of a
candidate check; it sits in `ifcheck/` rather than beside the queries because QL module names
cannot contain hyphens, so `queries/if-check-exp/` is not an importable path.

## Output columns

All queries emit named columns (`path`, `line`, `pkg`, `declaringType`, `method`, ...) and are
`order by`-ed, so runs are reproducible and diffable across machines — which matters because
results are gitignored and regenerated per machine, not committed. Two columns exist
specifically to serve triage:

- **`pkg`** — the package directory under `org/apache/cassandra` (`db/compaction`, `utils`,
  `net`). Triage proceeds by directory batch, so this is emitted rather than re-derived from
  the path by hand. Group on a prefix of it for coarser batches.
- **`opClass`** — `magnitude` (`<`, `<=`, `>`, `>=`) or `equality` (`==`, `!=`). A capacity
  check is inherently a magnitude comparison, so equality rows are mostly noise (`index == 0`,
  sentinel tests) — in `NarrowedIfStatements.csv` they are 1,808 of 4,489 rows. They are
  **kept, not dropped**: an exact-value counter cap (`count == MAX`) is conceivable, and
  discarding 40% of the corpus silently would be an invisible decision. Rows are sorted
  `opClass` first so magnitude rows are read first and equality swept afterward at lower
  priority.

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
4. *(in progress)* **Stage-2 triage** of the remaining rows — a preprocessing pass that
   works from the rows alone, **without opening the source**: rule out what a row visibly
   cannot be (bare-literal operand, ordering test, loop index, mechanical method name) and
   rank the rest into priority tiers by operand and context names. Not expressible as a
   CodeQL predicate, since there's no reliable fixed vocabulary to grep for — and equally
   not a qualification: stage 2 does **not** apply the three rules, which need the code.
   Verdicts go to `../../../../cassandra/if-check-exp/stage2-ai-filtering/`
   (`positives.md` with a tier / `negatives.md` / `deferred.md`), and the deep-read pass
   then applies the rules in tier order.

## Pattern-(a) completeness: `HelperGuardedIfStatements.ql`

Steps 1-3 find the capacity check only when the comparison is written **directly in the `if`
condition**. When it hides behind a boolean helper — `if (!pool.hasRoom())`,
`if (isOverLimit())` — the `if` carries no comparison and the row never appears, even though
the `if`'s own branches are what decide allow vs. disallow. That is still pattern (a); the
check just sits one call frame down.

`HelperGuardedIfStatements.ql` closes that gap: `if` statements whose condition calls a
boolean method declared in Cassandra's own source, where that method's body holds a candidate
numeric comparison. It reports both the `if` site and the comparison inside the callee
(`helper`, `helperLine`). **1,099 rows — 577 magnitude, 522 equality.**

Note the real unit of work is much smaller than the row count: the 577 magnitude rows come
from only **197 distinct helpers**, so triage judges each *helper* once and then applies the
verdict to all its call sites. The most-repeated helpers are plainly not capacity checks
(`ProtocolVersion.isGreaterOrEqualTo()`, 40 rows; `DeletionTime.supersedes()`, 28), so sorting
by helper frequency disposes of a large share quickly.

As with the others, this is mechanical narrowing only. It does not check that the helper's
comparison is a usage-vs-limit test, nor that the `if`'s branches diverge on object creation —
both stay read-and-judge calls.

## Known gap and planned extensions (2026-09-20)

`if-check-exp` now recognizes three enforcement patterns (see
[`../../../../cassandra/if-check-exp/README.md` §3.2](../../../../cassandra/if-check-exp/README.md#3-core-concept-the-if-check-case)):
(a) the capacity check is itself the deciding `if`; (b) the check produces a
verdict — a flag, enum, or return value — that a separate decision point
reads; (c) guard clauses before an allocation that sits outside any branch.
Steps 1-3 above only keep comparisons that sit inside an `if` condition, and
`HelperGuardedIfStatements.ql` extends that to comparisons one call frame down — but all of
them are anchored on an `if` whose branches decide, i.e. pattern (a). None of them can reach
patterns (b) and (c). Known miss: the `cdc_total_space`
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
