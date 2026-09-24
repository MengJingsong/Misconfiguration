# Stage 2 playbook

How to work through the stage-1 rows. Written 2026-09-22 after stage 1 was
finished for enforcement **pattern (a)**; rewritten 2026-09-23 when the
keyword tiers were dropped in favour of AI ranking.

See [`README.md`](README.md) for this folder's rules and batch coverage,
[`../README.md` §7.2](../README.md#72-discover-and-qualify-candidate-capacity-checks)
for how the stages relate, and
[`../stage1-codeql-preprocessing/README.md`](../stage1-codeql-preprocessing/README.md)
for the input: the two CSVs, their row counts, the commands that regenerate
them, and stage 1's structural blind spot. **That file is the single source
of truth for stage-1 output — this one does not restate it.**

---

## What stage 2 does — rank every row

Stage 2 takes the stage-1 rows — one row per `if` statement — and an AI
session reads them. It does **one** thing:

> **Rank every stage-1 row by how likely it is to become a valid case, using
> lexical and semantic judgement of the row's text.**

The ranked rows are stage 2's result and stage 3's queue.

**No keyword list, and no mechanical filter** (decided 2026-09-23). Ranking is
the AI's reading of the row, start to finish. The fixed capacity-word list
that produced the old P1–P4 tiers is gone; so is the bare-literal /
`compareTo` fast-reject, which now survives only as one thing the AI notices
while reading, not as a separate stage.

**Stage 2 rules nothing out** (decided 2026-09-23). A row that looks
impossible gets band D; it is never removed from the queue. A rule-out is
permanent and invisible, while a bad band costs a little reading and
self-corrects as stage 3 works down the list.

**Cost is not a reason to filter first.** The whole 5,588-row corpus is about
107k input and 140k output tokens to rank — roughly 45 batches. There is no
saving worth buying with a heuristic that might drop a real case.

## The one rule

**Rank, never rule out.** A rule-out is permanent and invisible — nothing
re-reads a rejection. A bad rank costs a few minutes of stage-3 reading and is
corrected the moment someone looks at the row.

Every signal that would once have argued for refusing a row now argues for
band D.

What stage 2 *is* — rows only, never the source, and never the three rules —
is defined in [`README.md`](README.md)'s "How a row is ranked", which is
authoritative. This file is technique only.

## The four bands

| Band | The row reads as | Stage-3 order |
|---|---|---|
| **A** | A real capacity check — usage compared against a memory or disk limit | first |
| **B** | Plausibly a resource bound, but the row alone does not settle it | second |
| **C** | Named operands, nothing resource-shaped about them | third |
| **D** | Clearly not one: startup validation, an ordering test, a loop index, a bare literal, serialization arithmetic | last |

**C is the insurance band, and it is not optional.** `memtable_heap_space` and
`MAX_HINT_BUFFERS` are both real cases and share no vocabulary at all, so a
future case may read as unremarkable in every word it uses. C is where such a
case hides. Merging it into D would rebuild the blind spot the keyword list
had.

**D is read, eventually.** It is the bottom of the order, not a bin.

**Four bands, not a score.** A rank is used one way — what to read next — and
four buckets answer that. A score of 72 against 68 would imply a distinction
the row cannot support; the average row is 67 characters. Bands also stay
arguable: "B because the limit is unnamed" is a claim a later session can
overturn, where "64" is not.

## How to run a batch

**Batch size ~100–150 rows.** Present each row as a sentence plus its
`path:line` id, and write the verdicts back keyed on that id:

```
utils.memory | MemtablePool.allocate | ... + ... > limit
  -> A  "usage plus request against a pool limit"
config | DatabaseDescriptor.applySimpleConfig | phi_convict_threshold > 16
  -> D  "failure-detector tuning inside startup validation"
schema | CompressionParams.validate | chunkLength > maxCompressedLength
  -> B  "byte lengths, but a validate* method — may be config-time only"
```

**Judge the row as a sentence**, not the operand alone: `declaringType` +
`method` + `lhs op rhs`. Context usually decides before the operand does —
anything in `applySimpleConfig`/`validate*` is startup validation whatever it
compares, and anything in a `*Pool.allocate` deserves a look whatever it is
called.

**Always emit the one-line reason.** A band with no reason is unreviewable.
With one, a wrong band is visible at a glance and a later session can overturn
it without re-deriving anything. This is what replaces the reproducibility the
keyword list had for free.

**Anchor every batch.** Include the same fixed anchor rows in every batch —
about 8 of 120, roughly 7% of the run. If they come back in their expected
bands, that batch is on the same yardstick as every other; if they do not,
re-run it. Without anchors, band A in batch 3 and band A in batch 40 are two
unrelated judgements, since AI ranking has no global membership rule the way
the keyword list did.

*This is not run-to-run consistency testing, which this folder decided not to
do (2026-09-23). It makes separate batches comparable at all — a different
problem.*

**Record the model and the date per batch.** These judgements are
model-dependent in a way CodeQL output is not, and a later session needs to
know what produced a band.

**Rank the whole corpus.** Every stage-1 row needs a place in the order,
including equality rows and helper rows. Nothing is exempt because it looks
unpromising — that is what band D is for.

## Calibration — the labelled rows

**The acceptance test: the known cases must land in band A.** If they do not,
the ranking is wrong however good the rest looks.

Every already-filed case whose check sits in an `if` appears in
`NarrowedIfStatements.csv`, all magnitude-class:

| Case | Row |
|---|---|
| `MAX_HINT_BUFFERS` | `HintsBufferPool.java:113` — `allocatedBuffers >= MAX_ALLOCATED_BUFFERS` |
| both memtable cases | `MemtablePool.java:156` — `... + ... > limit` |
| both `*_receive_queue_capacity` cases | `AbstractMessageHandler.java:419` — `... + ... <= queueCapacity` |
| the compaction disk case | `CompactionAwareWriter.java:282` — `availableSpace < estimatedWriteSize` |

The four qualified candidates from the P1 pass belong in band A too:

| Candidate | Row |
|---|---|
| `BufferPool_memoryUsageThreshold` | `BufferPool.java:443` — `cur + MACRO_CHUNK_SIZE > memoryUsageThreshold` |
| `MAX_MATERIALIZED_KEYS` | `QueryController.java:449` — `MAX_MATERIALIZED_KEYS < ++count` |
| `Integer_MAX_VALUE` | `IndexSummaryBuilder.java:204` — `entries.length() + getEntrySize(key) <= Integer.MAX_VALUE` |
| `TeeDataInputPlus_limit` | `TeeDataInputPlus.java:58` — `teeBuffer.position() + length < limit` |

**Note how little the row gives you.** Two of the filed cases render the usage
side as `... + ...`, and `MAX_MATERIALIZED_KEYS < ++count` puts the limit on
the left. The row locates the check; it never decides it.

(`cdc_total_space`'s **cited** check is absent — `processNewSegment():335` is
a ternary, so no `if`-anchored query can reach it; it was found by feed 3b.
The constraint is **not** absent from the CSV, though: `:345` and
`permitSegmentMaybe():200` both compare the same usage against the same limit
in real `if`s.)

**The 34 P1 rows all carry stage-3 verdicts** — 4 qualified, 22 refused, 3
deferred, 5 already covered — which makes them the largest labelled set
available. **But the refusals are weak anchors.** Many were refused on Rule 3
(the branches do not diverge on object creation), which stage 2 cannot see, so
a good ranking may legitimately put them in band A. Use a refusal as an anchor
only where the refusal ground is visible in the row itself. The **qualified**
rows are the strong anchors.

**The limit side is *not* determined by the operator.** Both of these are real
capacity checks:

```
availableSpace       <  estimatedWriteSize     <- limit on the LEFT
allocatedBuffers     >= MAX_ALLOCATED_BUFFERS  <- limit on the RIGHT
```

Which operand is the limit is semantic, not syntactic. **Every judgement must
look at both sides.**

## Input: the stage-1 rows

Per row: `path, line, pkg, declaringType, method, lhs, op, rhs, opClass`, plus
`helper, helperLine` for helper rows. Rows are `order by`-ed, so runs are
reproducible across machines.

Two CSVs feed stage 2 — `NarrowedIfStatements.csv` (the comparison is in the
`if` condition) and `HelperGuardedIfStatements.csv` (the comparison is one
call frame down, behind a boolean helper). They are read the same way; the
helper file just has a cheaper shortcut (see "Tricks").

**`opClass` is a signal, not a filter.** A capacity check compares usage
against a limit, which is a magnitude relation, so an equality row usually
earns a low band — but it is ranked like everything else, because a sentinel
(`== MIN_VALUE`) or an exact-fit test can still be one.

**Signals actually available in a row:**

- **Operand names** — the obvious one, and the weakest on its own.
- **Method name** — `validate*`, `apply*Config`, `serializedSize`, `hashCode`,
  `equals`, `toString` mark mechanical code. The whole `config` package is
  dominated by `applySimpleConfig` and `validate*`.
- **Declaring type** — `*Spec`, `*Options`, `Config*` mean startup validation;
  `*Pool`, `*Allocator`, `*Buffer`, `*Writer`, `*Manager` are
  allocation-adjacent and deserve an uprank.
- **Repetition** — many rows in one method, or one helper across many call
  sites, is usually one judgment, not many.

## Why the keyword list was dropped (2026-09-23)

Recorded so it is not rebuilt. The old scale ranked rows by a fixed
capacity-word list (`limit`, `capacity`, `max`, `threshold`, `space`, `bytes`,
`free`, `avail`, `quota`, `reserve`, `allowance`, `budget`) into tiers P1–P4.
It **failed in both directions**, which is what
[`../README.md` §7.2](../README.md#72-discover-and-qualify-candidate-capacity-checks)'s
"deliberately no fixed keyword list" rule warns about:

*Keyword hits that are not byte capacities:* `phi_convict_threshold > 16`
(failure-detector float), `repair_session_max_tree_depth > 20` (a depth),
`memtable_cleanup_threshold > 0.99f` (a ratio), `default_keyspace_rf <
..._fail_threshold` (replica count). All match `threshold`/`max`; all sit in
`applySimpleConfig` — the *method* gives them away before the operand does.

*Capacity vocabulary the list never anticipated:* `remaining()`,
`keysWritten >= keysEstimate`, `unused`, `pendingTasks`.

**What was given up with it.** The list's track record — 4/4 known cases
selected in 527 of 2,681 magnitude rows, and a ~1-in-3 hit rate on P1's 34
rows — was evidence about *the list*, not about ranking in general. Dropping
it starts the track record over, with the labelled rows above as the only
check. That is why the acceptance test matters more now than it did before.

## Tried and rejected: the config-name join

Joining the limit operand against the 414 `Config.java` field names and 328
`CassandraRelevantProperties` entries **does not work**: only 18 rows match
corpus-wide, and **none of the four known cases**. Operand names at the check
site (`limit`, `queueCapacity`, `MAX_ALLOCATED_BUFFERS`) are not config
names — the config name is reached by *tracing* the limit back to its
declaration, which is stage-3 work (README §5, question 4). Recorded so it is
not attempted again.

## Tricks that save real time

**Judge the helper, not the row.** The 1,099 helper rows come from ~300
distinct helpers (577 magnitude rows from 197). Sort by `helper`, judge once,
apply the band to every call site. The most repeated are obviously not
capacity checks (`ProtocolVersion.isGreaterOrEqualTo()` 40 rows,
`DeletionTime.supersedes()` 28). The 487 remaining helper-magnitude rows
collapse to **185 distinct helpers**. A helper row carries `helper` and
`helperLine` on top of the usual columns, and the helper's own name is often
the whole sentence.

*Helper progress:* 23 distinct helpers judged on 2026-09-22, covering the 114
helper rows inside the four finished subtrees — 21 rejected (108 rows), 1
cited to an existing
[`../stage3-ai-deep-read/_INDEX.md`](../stage3-ai-deep-read/_INDEX.md) entry
(4 rows), 1 candidate found
(`Directories.hasDiskSpaceForCompactionsAndStreams():551`, parked in
[`../stage3-ai-deep-read/deferred.md`](../stage3-ai-deep-read/deferred.md) as
pattern (b)). Those verdicts predate the bands; re-read them as D and A
respectively if a band is needed.

**Work a whole method or file at once.** Rows are sorted by `pkg, path, line`,
and cluster heavily by method — 51 of the `config` batch's 69 surviving rows
are in `DatabaseDescriptor.java`, most in `applySimpleConfig`. One judgment
about that method disposes of dozens of rows.

**Stage 2 needs no clone access at all.** It is pure CSV work, so it is cheap
and parallelisable across batches; keep it that way rather than drifting into
source reading, which is stage 3's job.

## Counts and scopes

All counts reproduce from the CSVs in `codeql-queries/results/cassandra/`, and
the CSVs are gitignored and regenerated per machine, so **no count here is
pinned to a commit**. The corpus is 5,588 rows (4,489 narrowed + 1,099
helper). When quoting a smaller number, say what it excludes — the four
finished subtrees (`concurrent`, `cache`, `transport`, `db/compaction`)
account for 329 narrowed and 114 helper rows, and the 34 P1 rows are already
read.

## Output of a batch

1. Every row → [`positives.md`](positives.md) **with a band and a one-line
   reason**. There is no second destination:
   [`negatives.md`](negatives.md) is closed and takes no new entries.
2. Batch line added to [`README.md`](README.md)'s coverage table, recording
   the model and date.

**Stage 2 cannot defer.** Judging a row as pattern-(b)/(c)-only needs the
branches read, so that is a stage-3 call recorded in
[`../stage3-ai-deep-read/deferred.md`](../stage3-ai-deep-read/deferred.md). A
row that smells like (b)/(c) gets a low band — not a park, and not a refusal.

Stage 3 then takes `positives.md` in band order, reads each row's context in
the source — tracing backward and forward through related code — applies the
three rules and the three patterns, and promotes what qualifies into case
files.
