# Stage 2 playbook

How to work through the stage-1 rows. Written 2026-09-22, after stage 1 was
finished for enforcement **pattern (a)**; revised 2026-09-23 when stage 1
gained its own folder.

See [`README.md`](README.md) for this folder's rules and batch coverage,
[`../README.md` §7.2](../README.md#72-discover-and-qualify-candidate-capacity-checks)
for how the three stages relate, and
[`../stage1-codeql-preprocessing/README.md`](../stage1-codeql-preprocessing/README.md)
for the input: the two CSVs, their row counts, the commands that regenerate
them, and stage 1's structural blind spot. **That file is the single source
of truth for stage-1 output — this one does not restate it.**

What you get per row: `path, line, pkg, declaringType, method, lhs, op, rhs,
opClass`, plus `helper, helperLine` for helper rows. Rows are `order by`-ed,
so runs are reproducible across machines.

---

## Calibration: what a true positive looks like as a row

Every already-filed case whose check sits in an `if` appears in
`NarrowedIfStatements.csv`, all magnitude-class:

| Case | Row |
|---|---|
| `MAX_HINT_BUFFERS` | `HintsBufferPool.java:113` — `allocatedBuffers >= MAX_ALLOCATED_BUFFERS` |
| both memtable cases | `MemtablePool.java:156` — `... + ... > limit` |
| both `*_receive_queue_capacity` cases | `AbstractMessageHandler.java:419` — `... + ... <= queueCapacity` |
| the compaction disk case | `CompactionAwareWriter.java:282` — `availableSpace < estimatedWriteSize` |

(`cdc_total_space`'s **cited** check is absent — `processNewSegment():335` is
a ternary, so no `if`-anchored query can reach it; it was found by feed 3b.
But note the constraint is **not** absent from the CSV: `:345`
(`!blocking && sizeInProgress.get() > allowance`) and
`permitSegmentMaybe():200` both compare the same usage against the same limit
in real `if`s and are both present. Corrected 2026-09-23 — the earlier "absent
by design" wording overstated the gap.)

This matters for calibration: **these four rows are what a true positive
looks like in the CSV.** Note how little the row itself tells you — two of
them render the usage side as `... + ...`. The row locates the check; it
never decides it.

## What stage 2 is

Stage 2 reads **only the rows**, never the Cassandra source. Its job is to
rule out what a row visibly cannot be, and to **order** the rest so the
expensive stage 3 starts with the most promising rows.

It does **not** apply the three rules — those qualify a real case and need
the code (Rule 3 asks whether the branches diverge on object creation, which
no row can show). See [`README.md`](README.md).

**Therefore: rank far more than you reject.** A wrong rejection is permanent
and invisible — nothing re-reads `negatives.md`. A wrong promotion costs a
few minutes of reading. When unsure, assign a low tier rather than refusing.

## Signals actually available in a row

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

## Fast-reject: verified, side-agnostic

Reject a magnitude row if **either** operand is a bare numeric literal, or if
either mentions `compareTo()` / `compare()`.

- Drops **1,463 of 2,681** magnitude rows → **1,218** remain
  (*full-corpus scope* — finished subtrees included).
- In *work-ahead scope* (finished subtrees excluded) it drops **1,337 of
  2,454** → **1,117** remain. These are the P4 / survivor counts in the tier
  table below.
- **Loses none of the four known real cases.**

One judgment call to be aware of: dropping literal-operand rows would also
drop a capacity check written against a hardcoded number (`if (size > 65536)`).
That is accepted because a bare literal has no declaring variable, so it
could not name a constraint under §6.1 — but it is a real, if small, risk.
Keep the dropped rows **listed** in `negatives.md` by ground rather than
deleted, so the decision stays auditable.

## Priority tiers

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

**Validation:** measured in *validation scope* — the whole magnitude corpus
(2,681 rows, finished subtrees included, so the known cases are in scope) and
**before** the fast-reject — the capacity-word test on either side catches
**4 of 4** known real cases while selecting only **527** rows. The
compound-usage signal (`current + requested vs limit`) covers 2 of the 4.

## Scope table — read this before quoting a number

The same filter yields three different counts depending on the row set it is
measured over, and all three appear in these docs. **Always name the scope.**

| Scope | Row set | Fast-reject applied? | Magnitude rows | Capacity-word hits |
|---|---|---|---|---|
| **Validation** | whole magnitude corpus | no | 2,681 | **527** |
| **Full-corpus** | whole magnitude corpus | yes | 1,218 survivors | 429 |
| **Work-ahead** | finished subtrees excluded | yes | 1,117 survivors | **371** (= P2) |

Validation scope is the one that justifies the filter (4/4 known cases);
work-ahead scope is the one that sizes the remaining job. The tier table
above is work-ahead scope. All counts reproduce from the CSVs.

**P1 is done** (run 2026-09-22): 34 rows read in stage 3 — 4 candidates, 22
rejected, 3 deferred, 5 already covered. It contained two known cases as free
calibration, and validated the ranking at roughly a 1-in-3 hit rate on rows
not already accounted for. **Next is P2** (371 rows incl. the 34 done), after
the lexical re-rank below.

**Caveat worth keeping in view:** four labelled positives is a very small
validation set. 4/4 is encouraging, not proof. This is exactly why P3 exists
and why the folder's rules refuse a fixed keyword list — `memtable_heap_space`
and `MAX_HINT_BUFFERS` share no vocabulary, and a future case may share none
with the list above. **P3 is not optional; it is the insurance.**

## Lexical judgement — the next stage-2 pass (planned 2026-09-22)

**This replaces the fixed capacity-word list the tiers above are built on.**
Jingsong's plan, to run before P2: *use AI to scan the operand names and any
other text in a stage-1 row — enclosing class, method, package — and sort
candidates by what those names actually mean, rather than by matching a word
list.*

The tiers above key off a fixed capacity-word list, which **fails in both
directions** — this is exactly what
[`../README.md` §7.2](../README.md#72-discover-and-qualify-candidate-capacity-checks)'s
"deliberately no fixed keyword list" rule warns about.

*Keyword hits that are not byte capacities:* `phi_convict_threshold > 16`
(failure-detector float), `repair_session_max_tree_depth > 20` (a depth),
`memtable_cleanup_threshold > 0.99f` (a ratio), `default_keyspace_rf <
..._fail_threshold` (replica count). All match `threshold`/`max`; all sit in
`applySimpleConfig`, i.e. startup validation — the *method* gives them away
before the operand does.

*Capacity vocabulary the list never anticipated:* `remaining()`,
`keysWritten >= keysEstimate`, `unused`, `pendingTasks`.

**How to run it.**

- **Judge the row as a sentence**, not the operand alone: `declaringType` +
  `method` + `lhs op rhs`. Context usually decides before the operand does —
  everything in `applySimpleConfig`/`validate*` is startup validation
  whatever it compares, and everything in a `*Pool.allocate` deserves a look
  whatever it is called.
- **Layer it after the mechanical fast-reject** (bare literal, `compareTo`),
  which stays because it is free, deterministic and reproducible. That strips
  ~1,337 rows before any judgement is spent.
- **Emit a one-line reason per row**, not just a label, so the pass is
  auditable and does not drift across sessions. *"`phi_convict_threshold` —
  failure-detector tuning, not a byte bound"* is a complete justification.
- **Reject only lexical certainties; downrank anything ambiguous.**
  `remaining() < 4` looks capacity-shaped and is really a deserialization
  bounds check — stage 2 cannot know that, so it ranks low rather than
  refusing. The standing asymmetry applies: a wrong rejection is permanent
  and invisible, a wrong promotion costs a little reading.
- **Record model and date per batch.** These judgements are model-dependent
  in a way CodeQL output is not. Regression-check each batch against the
  known rows, and re-judge ~10 rows from the previous batch to confirm the
  same row still gets the same verdict.
- **Re-rank before P2.** P2's membership comes from the keyword list this
  pass supersedes, so re-ranking first means it is read in a trustworthy
  order instead of being re-read later.

Either way, lexical meaning **cannot** settle the three rules; it improves
ranking and removes the obvious, and qualification stays with the deep read.

## Other row-level signals

- **Method name** — `validate*`, `apply*Config`, `serializedSize`,
  `hashCode`, `equals`, `toString` mark mechanical code. The whole `config`
  package is dominated by `applySimpleConfig` and `validate*`.
- **Declaring type** — `*Spec`, `*Options`, `Config*` mean startup
  validation; `*Pool`, `*Allocator`, `*Buffer`, `*Writer`, `*Manager` are
  allocation-adjacent and deserve an uprank.
- **Repetition** — many rows in one method, or one helper across many call
  sites, is usually one judgment, not many.

## Tried and rejected: the config-name join

Joining the limit operand against the 414 `Config.java` field names and 328
`CassandraRelevantProperties` entries **does not work**: only 18 rows match
corpus-wide, and **none of the four known cases**. Operand names at the check
site (`limit`, `queueCapacity`, `MAX_ALLOCATED_BUFFERS`) are not config
names — the config name is reached by *tracing* the limit back to its
declaration, which is stage-3 work (README §5, question 4). Recorded so it
is not attempted again.

## Tricks that save real time

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

## Output of a batch

1. Row-level rejects → [`negatives.md`](negatives.md), citing the ground.
2. Everything else → [`positives.md`](positives.md) **with a tier**.
3. Batch line added to [`README.md`](README.md)'s coverage table.

There is no third bucket. **Stage 2 cannot defer** — judging a row as
pattern-(b)/(c)-only needs the branches read, so that is a stage-3 call
recorded in
[`../stage3-ai-deep-read/deferred.md`](../stage3-ai-deep-read/deferred.md).
A row that smells like (b)/(c) gets a low tier, not a park and not a
refusal.

Stage 3 then takes `positives.md` in tier order, applies the three
rules with the source open, and promotes what qualifies into case files.

## Suggested order

| # | Step | Size | Status |
|---|---|---|---|
| 1 | ~~P1 tier, corpus-wide~~ | 34 rows | ✅ **done 2026-09-22** — 4 candidates, ranking validated |
| 2 | Lexical re-rank (supersedes the keyword list) | 1,117 survivors | ⏵ **next** |
| 3 | P2 tier, or its re-ranked equivalent | 371 (incl. the 34 done) | pending step 2 |
| 4 | P3 tier — the insurance, not optional | 746 | pending |
| 5 | Equality sweep | 2,204 | lowest priority |

Tier-first beat batch-first on P1, so keep it. P1's rows were scattered
across ~15 packages, so no package may be marked done on its account —
record a tier as its own coverage entry.

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
stage-3 pass: a whole top-level package at a time is reasonable.
