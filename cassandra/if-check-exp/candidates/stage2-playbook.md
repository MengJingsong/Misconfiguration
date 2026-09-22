# Stage 1 results & stage 2 playbook

What the CodeQL stage produced, and how to work through it. Written
2026-09-22, after stage 1 was finished for enforcement **pattern (a)**.
See [`README.md`](README.md) for the folder's rules and batch coverage, and
[`../README.md` §7.2](../README.md#72-discover-candidate-capacity-checks-target-1)
for how the two discovery methods relate.

---

## Part 1 — Stage 1 results

### What exists

Two CSVs feed pattern-(a) triage. Both live in the **gitignored**
`codeql-queries/results/cassandra/` and are regenerated per machine:

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
cd /proj/misconfiguration-PG0/git-repos/misconfiguration/codeql-queries
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/NarrowedIfStatements.ql
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/HelperGuardedIfStatements.ql
```

| File | Rows | What it contains |
|---|---|---|
| `NarrowedIfStatements.csv` | 4,489 | Numeric comparisons written **directly in an `if` condition**. Nulls, literal-only pairs and non-numeric operands already dropped. |
| `HelperGuardedIfStatements.csv` | 1,099 | Comparisons **one call frame down**, inside a boolean helper the `if` calls (`if (!pool.hasRoom())`). Adds `helper` and `helperLine` columns. |

Columns: `path, line, pkg, declaringType, method, lhs, op, rhs, opClass`
(+ `helper, helperLine`). Rows are `order by`-ed, so runs are reproducible
across machines.

Narrowing so far: **17,343** `if` statements → **10,147** comparisons →
**4,489** numeric non-trivial, plus **1,099** helper-guarded.

### Why these two files are the complete pattern-(a) input

Pattern (a) is "the capacity check is itself the `if` whose branches decide".
`NarrowedIfStatements.ql` keeps comparisons whose enclosing statement is an
`if` — structurally exactly that. `HelperGuardedIfStatements.ql` covers the
one way an (a) check can hide from it: the comparison living inside a boolean
helper, leaving the `if` with no comparison of its own.

Patterns (b) and (c) are **not** covered and are parked (see
[`deferred.md`](deferred.md)). Do not go looking for them in these files.

### Sanity check: the known cases are all in there

Every already-filed case whose check sits in an `if` appears in
`NarrowedIfStatements.csv`, all magnitude-class:

| Case | Row |
|---|---|
| `MAX_HINT_BUFFERS` | `HintsBufferPool.java:113` — `allocatedBuffers >= MAX_ALLOCATED_BUFFERS` |
| both memtable cases | `MemtablePool.java:156` — `... + ... > limit` |
| both `*_receive_queue_capacity` cases | `AbstractMessageHandler.java:419` — `... + ... <= queueCapacity` |
| the compaction disk case | `CompactionAwareWriter.java:282` — `availableSpace < estimatedWriteSize` |

(`cdc_total_space` is absent by design — it is a ternary, hence pattern (b),
and was found by method 1.)

This matters for calibration: **these four rows are what a true positive
looks like in the CSV.** Note how little the row itself tells you — two of
them render the usage side as `... + ...`. The row locates the check; it
never decides it.

---

## Part 2 — Stage 2 playbook

### What stage 2 is

Stage 2 reads **only the rows**, never the Cassandra source. Its job is to
rule out what a row visibly cannot be, and to **order** the rest so the
expensive deep-read pass starts with the most promising rows.

It does **not** apply the three rules — those qualify a real case and need
the code (Rule 3 asks whether the branches diverge on object creation, which
no row can show). See [`README.md`](README.md).

**Therefore: rank far more than you reject.** A wrong rejection is permanent
and invisible — nothing re-reads `negatives.md`. A wrong promotion costs a
few minutes of reading. When unsure, assign a low tier rather than refusing.

### Signals actually available in a row

`lhs`, `op`, `rhs`, `pkg`, `declaringType`, `method`, `opClass`, and for
helper rows `helper` / `helperLine`. Everything below is derived from those.

**The limit side is *not* determined by the operator.** Both of these are
real capacity checks:

```
availableSpace       <  estimatedWriteSize     <- limit on the LEFT
allocatedBuffers     >= MAX_ALLOCATED_BUFFERS  <- limit on the RIGHT
```

Which operand is the limit is semantic, not syntactic. **Every heuristic must
look at both sides.** (An earlier draft of this file assumed limit = rhs of
`<`/`<=` and lhs of `>`/`>=`; that is wrong and gets the hints case exactly
backwards.)

### Fast-reject: verified, side-agnostic

Reject a magnitude row if **either** operand is a bare numeric literal, or if
either mentions `compareTo()` / `compare()`.

- Drops **1,463 of 2,681** magnitude rows → **1,218** remain.
- **Loses none of the four known real cases.**

One judgment call to be aware of: dropping literal-operand rows would also
drop a capacity check written against a hardcoded number (`if (size > 65536)`).
That is accepted because a bare literal has no declaring variable, so it
could not name a constraint under §6.1 — but it is a real, if small, risk.
Keep the dropped rows **listed** in `negatives.md` by ground rather than
deleted, so the decision stays auditable.

### Priority tiers

Counts are over the **remaining** magnitude rows — the 2,454 left after
excluding the four finished subtrees — since that is the work ahead:

| Tier | Definition | Rows |
|---|---|---|
| **P1** | Capacity word on either side **and** compound usage side (`... + ...`) | **34** |
| **P2** | Capacity word on either side | **371** (incl. P1) |
| **P3** | Both operands named, no capacity vocabulary | **746** (rest of the 1,117 fast-reject survivors) |
| **P4** | Fast-rejected — parked at the bottom, not deleted | **1,337** |

Capacity vocabulary: `limit`, `capacity`, `max`, `threshold`, `space`,
`bytes`, `free`, `avail`, `quota`, `reserve`, `allowance`, `budget`.

**Validation:** measured over the whole magnitude corpus (2,681 rows,
finished subtrees included, so the known cases are in scope), the
capacity-word test on either side catches **4 of 4** known real cases while
selecting only 527 rows. The compound-usage signal
(`current + requested vs limit`) covers 2 of the 4.

**P1 is the next thing to run** (decided 2026-09-22): 34 rows, one sitting,
and it already contains two known cases as free calibration plus one known
rejection to cite rather than re-judge. Running it first also tests the
ranking on a bigger sample than four labels before the remaining ~5,000 rows
are ordered by it.

**Caveat worth keeping in view:** four labelled positives is a very small
validation set. 4/4 is encouraging, not proof. This is exactly why P3 exists
and why the folder's rules refuse a fixed keyword list — `memtable_heap_space`
and `MAX_HINT_BUFFERS` share no vocabulary, and a future case may share none
with the list above. **P3 is not optional; it is the insurance.**

### Other row-level signals

- **Method name** — `validate*`, `apply*Config`, `serializedSize`,
  `hashCode`, `equals`, `toString` mark mechanical code. The whole `config`
  package is dominated by `applySimpleConfig` and `validate*`.
- **Declaring type** — `*Spec`, `*Options`, `Config*` mean startup
  validation; `*Pool`, `*Allocator`, `*Buffer`, `*Writer`, `*Manager` are
  allocation-adjacent and deserve an uprank.
- **Repetition** — many rows in one method, or one helper across many call
  sites, is usually one judgment, not many.

### Tried and rejected: the config-name join

Joining the limit operand against the 414 `Config.java` field names and 328
`CassandraRelevantProperties` entries **does not work**: only 18 rows match
corpus-wide, and **none of the four known cases**. Operand names at the check
site (`limit`, `queueCapacity`, `MAX_ALLOCATED_BUFFERS`) are not config
names — the config name is reached by *tracing* the limit back to its
declaration, which is deep-read work (README §5, question 4). Recorded so it
is not attempted again.

### Tricks that save real time

**Judge the helper, not the row.** 1,099 helper rows come from ~300 distinct
helpers (577 magnitude rows from 197). Sort by `helper`, judge once, apply to
every call site. The most repeated are obviously not capacity checks
(`ProtocolVersion.isGreaterOrEqualTo()` 40 rows, `DeletionTime.supersedes()`
28).

**Work a whole method or file at once.** Rows are sorted by `pkg, path,
line`, and rows cluster heavily by method — 51 of the `config` batch's 69
surviving rows are in `DatabaseDescriptor.java`, most in `applySimpleConfig`.
One judgment about that method disposes of dozens of rows.

**Stage 2 needs no clone access at all.** It is pure CSV work, so it is cheap
and parallelisable across batches; keep it that way rather than drifting into
source reading, which is the next pass's job.

### Output of a batch

1. Row-level rejects → [`negatives.md`](negatives.md), citing the ground.
2. Everything else → [`positives.md`](positives.md) **with a tier**.
3. Pattern-(b)/(c)-only rows → [`deferred.md`](deferred.md).
4. Batch line added to [`README.md`](README.md)'s coverage table.

The deep-read pass then takes `positives.md` in tier order, applies the three
rules with the source open, and promotes what qualifies into case files.

### Suggested order

**Next: P1, corpus-wide (34 rows).** Tier-first rather than batch-first —
this is the fastest route to new cases and the cheapest test of whether the
ranking predicts them. Its rows are scattered across ~15 packages, so record
it as its own coverage entry rather than treating any package as finished.

Then, depending on what P1 yields: **P2** (371) if the tiering holds up, or
fall back to completing packages batch by batch if it does not.

Batch order for the package-by-package work:

1. ~~The 114 unread helper rows inside the four "done" batches~~
   (`transport` 63, `db/compaction` 43, `concurrent` 6, `cache` 2) — **done
   2026-09-22**; 23 distinct helpers judged, 1 candidate found.
2. **`config` (115 magnitude) and `net` (98)** — `config` is worth doing
   first because it is *fast*, not because it is promising: it is almost
   entirely `applySimpleConfig`/`validate*` config validation, so expect
   close to zero survivors. It is a good calibration batch for exactly that
   reason.
3. **`db`, `utils`, `index`, `io`** — over half the remaining work.

Because stage 2 does not read source, a session can cover much more than the
deep-read pass: a whole top-level package at a time is reasonable.
