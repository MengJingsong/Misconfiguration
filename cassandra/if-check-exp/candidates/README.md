# Candidates — AI filtering results (method 2, stage 2)

This folder holds the **stage-2 (AI filtering) verdicts** of the *CodeQL + AI
preprocessing* discovery method. See
[`../README.md` §7.2](../README.md#72-discover-candidate-capacity-checks-target-1)
for how the two discovery methods relate, and §7.5 for the scope currently in
force.

Stage 1's pattern-(a) output is two files — `NarrowedIfStatements.csv`
(comparisons in an `if` condition) and `HelperGuardedIfStatements.csv`
(comparisons one call frame down, behind a boolean helper). Both carry `pkg`
and `opClass` columns; read `magnitude` rows before `equality` ones.

That output is **not** kept here: the CodeQL queries under
[`codeql-queries/cassandra/queries/if-check-exp/`](../../../codeql-queries/cassandra/queries/if-check-exp/README.md)
write to the gitignored `codeql-queries/results/cassandra/` and are
regenerated per machine, so nothing about a result set is committed or
pinned.

## Files

| File | Holds |
|---|---|
| [`positives.md`](positives.md) | Rows that passed all three rules — live candidates pending promotion to a full case file under a `<module>/` folder. |
| [`negatives.md`](negatives.md) | Rows read and refused, each citing the rule it failed. |
| [`deferred.md`](deferred.md) | Rows left **unjudged** — they would qualify only under enforcement pattern (b) or (c), which are parked by the §7.5 scope decision. Not refused; awaiting the (b)/(c) resumption. |

The three are mutually exclusive: every row read in stage 2 lands in exactly
one of them.

## How a row is judged

Read the row's actual source in the local `cassandra-src` clone (grep/window
it — don't fetch whole files through GitHub), then apply the three rules in
[`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case):
Rule 1 (is the limit-side operand a real capacity?), Rule 2 (does it bound
total memory/disk **bytes**, not rate or concurrency?), Rule 3 (does the
verdict reach a decision point that diverges on object creation?).

There is deliberately **no fixed keyword list** — real cases like
`memtable_heap_space` share no predictable vocabulary, so this is a
read-and-judge pass over CodeQL's structural narrowing, not a grep. CodeQL
only shrinks the search space; it decides nothing about qualification.

**Current scope: pattern (a) only.** A row whose capacity check is itself the
deciding `if` is judged normally. A row that would only qualify under pattern
(b) or (c) goes to `deferred.md` — do not refuse it.

## One line, one place

Rejections from the *other* discovery method (direct AI search) live in
[`../_INDEX.md`](../_INDEX.md)'s "lines considered and rejected" section, not
here — they differ in kind (few, narrative, often deferred rather than firmly
refused). If stage 2 reaches a line that method 1 already judged, **cite the
`_INDEX.md` entry rather than re-recording it here.**

## Batch coverage

Triage proceeds by directory batch (grouping the stage-1 rows by their
`src/java/org/apache/cassandra/<dir>/` path) rather than top-to-bottom, since
4,490 rows is too many to read linearly in one pass. Batches recorded here so
later sessions don't re-scan them.

| Batch (subpackage) | Rows | Date | Result |
|---|---|---|---|
| `concurrent/` | 17 | 2026-09-18 | 0 survivors — all thread-pool/permit concurrency checks (Rule 2 fail, same reasoning as `concurrent_compactors`). |
| `cache/` | 15 | 2026-09-18 | 0 survivors — ref-counting, overflow guards, and trivial validation; no capacity-vs-limit divergence found. |
| `transport/` | 89 | 2026-09-18 | 1 survivor (since promoted, see `positives.md`) + rejects logged in `_INDEX.md`. |
| `db/compaction/` | 208 | 2026-09-18 | 0 survivors under the then-current scope; 1 row later reclassified as a live candidate (now in `deferred.md`). Rejects logged in `_INDEX.md`. |

**Triaged: 329 of 4,490 rows.**

### Remaining un-triaged subpackages

Row counts from the same grouping. `db/compaction/` is done, so `db`'s
remaining rows are 982 − 208 = 774, spread across `marshal` (143), `tries`
(80), `commitlog` (78 — `CommitLogSegment.java:242` already rejected, see
`_INDEX.md`, but not the rest of the subpackage), `rows` (67),
`RangeTombstoneList.java` (48), `context` (39), `filter` (33),
`ColumnFamilyStore.java` (27), `Slices.java` (23), `partitions` (18),
`streaming` (16, db-local), `lifecycle` (15), `view` (14), `Columns.java`
(13), `memtable` (13, partially covered by existing memtable cases),
`ClusteringPrefix.java` (12), `monitoring` (11), `ReadCommand.java` (10),
`virtual` (10), and many smaller single-digit files.

Then: `utils` (717), `index` (487), `io` (466), `cql3` (368), `service`
(267), `tools` (167), `config` (154), `net` (140, partially covered by the
existing `internode_application_receive_queue_capacity` case), `locator`
(98), `serializers` (91), `dht` (78), `gms` (74), `repair` (62), `schema`
(48), `metrics` (44), `hints` (34, partially covered by the existing
`MAX_HINT_BUFFERS` case), `auth` (30), `streaming` (23, top-level),
`batchlog` (10), `security` (10), `tracing` (6), `audit` (4), `diag` (3),
`exceptions` (3), `triggers` (2).

## History

- **2026-09-22** — folder restructured into `positives.md` / `negatives.md` /
  `deferred.md`; the former single `candidates.md` was folded into this
  README (coverage table) and those three files.
- **2026-09-18** — disk (on-disk bytes) added alongside memory to this
  folder's scope, per Jingsong's call; see
  [`../README.md` §3.3](../README.md#33-resource-scope-memory-and-disk). One
  row previously rejected for being disk-scoped
  (`CompactionAwareWriter.getWriteDirectory():282`) was reclassified live as
  a direct result.
