# if-check-exp queries

Four CodeQL queries that narrow Cassandra's ~17k `if` statements down to the working list
that **stage 2** ranks and **stage 3** reads, for the three rules in
[`../../../../cassandra/if-check-exp/README.md`](../../../../cassandra/if-check-exp/README.md).
This folder produces CSVs and nothing else: the queries decide nothing, and no case file is
written from them directly.

CodeQL narrows **structurally** — by the shape of the code. It cannot judge whether a check is
actually a capacity check; real cases (`memtable_heap_space`, `MAX_HINT_BUFFERS`,
`cdc_total_space`, ...) share no vocabulary reliable enough for a keyword filter, which is why
that judgement belongs to stage 2 and the qualification to stage 3.

**Current scope: enforcement pattern (a) only** (see
[`../../../../cassandra/if-check-exp/README.md` §7.5](../../../../cassandra/if-check-exp/README.md#75-active-scope-decision-2026-09-22-pattern-a-only)).
All four queries anchor on an `if` whose branches decide, which is structurally exactly
pattern (a), so the pipeline already fits that scope with **no changes needed**. The three
planned extensions further down exist only to surface patterns (b) and (c), which are parked
until (a) is finished.

## The four queries

| Query | Selects | Rows |
|---|---|---|
| `AllIfStatements.ql` | every `if` in `src/java/...` — pure inventory, no filtering | 17,343 |
| `ComparisonIfStatements.ql` | those whose condition is a direct comparison between two operands, with a best-effort name for each | 10,147 |
| `NarrowedIfStatements.ql` | of those, the ones worth ranking: **the stage-2 input** | **4,489** |
| `HelperGuardedIfStatements.ql` | `if`s whose condition calls a Cassandra boolean helper that itself holds a candidate comparison: **the other stage-2 input** | **1,099** |

The first three form a chain, each narrowing the previous one's output. The fourth is a
**sibling, not a funnel step** — it finds pattern-(a) checks the chain structurally cannot see,
and its rows are additional, not a subset. Both CSVs feed stage 2 as equals.

### The chain — `All` → `Comparison` → `Narrowed`

`NarrowedIfStatements.ql` is where the real filtering happens. `isCandidateComparison` in
[`IfCheck.qll`](../../ifcheck/IfCheck.qll) keeps a comparison only when **neither operand is
`null`**, **not both operands are literals**, and **both operands are numeric-typed**. Measured
over the 5,658 rows it drops:

| Cause | Rows | Example |
|---|---|---|
| Null check | 4,215 | `getKeyspace() != null` |
| Enum constant or object reference | 975 | `flag() == NONE`, `bytes == UNSET_BYTE_BUFFER` |
| Reference identity | 376 | `this == o` (167), `getClass() != getClass()` (121) |
| `char` operand | 91 | `c >= '0'` in `Hex.java:38`, where `c` is declared `char` |
| Boolean | 1 | `considerZeroes == true` |
| Literal vs literal | **0** | — javac constant-folds these before CodeQL sees them |

Three things worth knowing about that table:

- **The filter is on operand *types*, not on the operator.** Equality rows survive it in
  quantity — 1,808 of the 4,489. `size() == 0` is kept; `kind() == STATIC` is not.
- **`char` is dropped, and it is not obvious.** CodeQL's `NumericType` covers `byte, short,
  int, long, float, double` — not `char`. All 25 dropped *magnitude* comparisons are char
  comparisons. The contrast is sharp: `TypeSizes.encodedUTF8Length`'s `c <= 0x007F` is kept
  because `int c = st.charAt(i)`, while `Hex.java`'s `c <= '9'` is dropped because the loop
  variable is declared `char`. Nothing capacity-related is lost, but the rule should be read
  rather than discovered.
- **The literal-vs-literal guard is a no-op** on this corpus. It costs nothing and documents
  intent, but it is not one of the reasons the row count falls.

Remaining noise that mechanical filtering cannot remove without keyword judgment — `index == 0`,
comparator results (`compareIPs() < 0`) — is left for stage 2.

### `HelperGuardedIfStatements.ql` — closing the boolean-helper gap

The chain finds the capacity check only when the comparison is written **directly in the `if`
condition**. When it hides behind a boolean helper — `if (!pool.hasRoom())`,
`if (isOverLimit())` — the `if` carries no comparison and the row never appears, even though
the `if`'s own branches are what decide allow vs. disallow. That is still pattern (a); the
check just sits one call frame down.

This query reports both the `if` site and the comparison inside the callee (`helper`,
`helperLine`). **1,099 rows — 577 magnitude, 522 equality — from 300 distinct helpers.**

The real unit of work is the *helper*, not the row: stage 2 judges each helper once and applies
the verdict to all its call sites, so 1,099 rows cost 300 judgements. The most-repeated helpers
are plainly not capacity checks (`ProtocolVersion.isGreaterOrEqualTo()` 40 rows,
`DeletionTime.supersedes()` 28), so sorting by helper frequency disposes of a large share
quickly. It found at least one real check the chain missed:
`HintsBufferPool.switchCurrentBuffer()`, the filed `MAX_HINT_BUFFERS` case, reached through
its helper.

As with the chain, this is mechanical narrowing only. It does not check that the helper's
comparison is a usage-vs-limit test, nor that the `if`'s branches diverge on object creation —
both stay read-and-judge calls.

## Output columns and row identity

All queries emit named columns (`path`, `line`, `pkg`, `declaringType`, `method`, ...) and are
`order by`-ed, so runs are reproducible and diffable across machines — which matters because
results are gitignored and regenerated per machine, not committed.

> **`path:line` is not a unique row id.** 340 lines carry more than one comparison, affecting
> **738 rows**, so a consumer keying on the pair silently merges them. Stage 2 keys on
> `path:line#n`, where `n` is the 1-based index of the row among those sharing a line, in CSV
> order — stable because the queries are `order by`-ed. This matters in practice:
> `TeeDataInputPlus.java:58` holds two comparisons and only the first is the capacity check.

Two columns exist specifically to serve the downstream stages:

- **`pkg`** — the package directory under `org/apache/cassandra` (`db/compaction`, `utils`,
  `net`). It is emitted rather than re-derived from the path by hand. Early triage batched by
  directory; stage 2's banding instead reads `pkg` as part of the sentence it judges
  (`pkg | Type.method | lhs op rhs`), and batches by fixed size across the whole corpus.
- **`opClass`** — `magnitude` (`<`, `<=`, `>`, `>=`) or `equality` (`==`, `!=`). A capacity
  check is inherently a magnitude comparison, so equality rows are far more likely to be noise
  (`index == 0`, sentinel tests). They are **kept, not dropped**: an exact-value counter cap
  (`count == MAX`) is conceivable, and discarding 40% of the corpus silently would be an
  invisible decision.

> **The `order by opClass` puts equality *first*, not magnitude.** Ascending string order makes
> `equality` precede `magnitude`, so the first 1,808 rows of `NarrowedIfStatements.csv` are the
> low-priority ones. This is the opposite of what the sort was intended to achieve, and it is
> not free: stage 2's banding read 14 batches — about 1,680 rows — before reaching its first
> magnitude row. Left as-is because the banding is complete and re-sorting would renumber every
> batch; a future consumer should sort by `opClass desc` itself, or the query should.

## Shared predicates

`isNumeric`, `operandName`, `pkgDir`, `opClass` and `isCandidateComparison` live in
[`cassandra/ifcheck/IfCheck.qll`](../../ifcheck/IfCheck.qll), imported as
`import ifcheck.IfCheck`. They were previously copy-pasted into each query, which risked the
queries drifting apart on what counts as "numeric" or "a candidate comparison". The library is
Cassandra-local rather than in `common/` because it encodes this experiment's notion of a
candidate check; it sits in `ifcheck/` rather than beside the queries because QL module names
cannot contain hyphens, so `queries/if-check-exp/` is not an importable path.

## Known gap and planned extensions (2026-09-20)

`if-check-exp` now recognizes three enforcement patterns (see
[`../../../../cassandra/if-check-exp/README.md` §3.2](../../../../cassandra/if-check-exp/README.md#3-core-concept-the-if-check-case)):
(a) the capacity check is itself the deciding `if`; (b) the check produces a
verdict — a flag, enum, or return value — that a separate decision point
reads; (c) guard clauses before an allocation that sits outside any branch.
The chain only keeps comparisons that sit inside an `if` condition, and
`HelperGuardedIfStatements.ql` extends that to comparisons one call frame down — but all four
queries are anchored on an `if` whose branches decide, i.e. pattern (a). None of them can reach
patterns (b) and (c). Known miss: the `cdc_total_space`
comparison in `CDCSizeTracker.processNewSegment()` (line 335) is a ternary
inside a method argument, so it is not in `NarrowedIfStatements.csv`. **The
constraint itself is not missed, though** — line 345 in the same method
(`!blocking && sizeInProgress.get() > allowance`, the eviction path) and
`permitSegmentMaybe():200` both compare the same usage against the same limit
in real `if`s and do appear. The miss is this *enforcement site*, not the
constraint. (Earlier wording called line 345 "an unrelated `if`"; it is not —
same usage, same limit, different response. Corrected 2026-09-23.)

Planned structural (still non-keyword) extensions, not yet written:

1. **Comparisons anywhere** — the same numeric-comparison narrowing as
   `NarrowedIfStatements.ql`, but over all comparison expressions, not only
   those inside an `IfStmt` condition (ternaries, assignments, `return`
   expressions, method arguments), reporting the enclosing statement kind.
2. **Guard clauses** — `if` statements with a numeric comparison whose
   then-branch ends in `throw` or `return`, for pattern (c); candidates are
   later checked for an allocation that the guard dominates.
3. **Verdict links** — writes of a boolean/enum field (or a returned
   boolean/enum) whose value derives from a comparison, joined to the `if`
   conditions that read that field or call that method, for pattern (b).

As with the four above, these only shrink the search space; whether a row
qualifies is still decided by reading it (README §3.4–§3.6).

## Running

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
cd /proj/misconfiguration-PG0/git-repos/misconfiguration/codeql-queries
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/NarrowedIfStatements.ql
```

Output lands in `results/cassandra/<QueryName>.csv` (gitignored).

## What happens next

The two CSVs are the input to **stage 2**, which ranks every row by AI lexical and semantic
judgement — it rules nothing out, and it does not apply the three rules. Its design, bands and
verdicts live in
[`../../../../cassandra/if-check-exp/stage2-ai-preprocessing/`](../../../../cassandra/if-check-exp/stage2-ai-preprocessing/README.md);
nothing about it is restated here, so that this file does not go stale when stage 2 changes.
The batch inputs are built by `../../../scripts/make-stage2-batches.py`, which reads both CSVs
directly.
