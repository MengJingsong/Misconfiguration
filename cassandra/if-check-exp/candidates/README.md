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
| [`stage2-playbook.md`](stage2-playbook.md) | **Start here when running a batch.** Stage 1's results, the prioritization ladder, verified fast-reject rules, and the tricks/pitfalls learned from the cases filed so far. Not a verdict store — the three files above are. |

The three are mutually exclusive: every row read in stage 2 lands in exactly
one of them.

## How a row is judged

> Practical guidance — what to read first, what to reject on sight, how to
> avoid re-reading files — is in
> [`stage2-playbook.md`](stage2-playbook.md). The rules below are the
> definition; the playbook is the technique.

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

Triage proceeds by directory batch rather than top-to-bottom, since the corpus
is far too large to read linearly in one pass. Batches are recorded here so
later sessions don't re-scan them.

Counts below come from the `pkg` column, refreshed 2026-09-22 after stage 1
gained named columns and the `HelperGuardedIfStatements.ql` query. **A batch
name is a subtree**: `transport` covers `transport` and `transport/messages`,
`db/compaction` covers it plus `db/compaction/unified` and
`db/compaction/writers`. The `pkg` column is a leaf, so group on a prefix of
it to reproduce a batch.

### Done

| Batch (subtree) | Narrowed rows | Date | Result |
|---|---|---|---|
| `concurrent` | 17 | 2026-09-18 | 0 survivors — all thread-pool/permit concurrency checks (Rule 2 fail, same reasoning as `concurrent_compactors`). |
| `cache` | 15 | 2026-09-18 | 0 survivors — ref-counting, overflow guards, and trivial validation; no capacity-vs-limit divergence found. |
| `transport` | 89 | 2026-09-18 | 1 survivor (since promoted, see `positives.md`) + rejects logged in `_INDEX.md`. |
| `db/compaction` | 208 | 2026-09-18 | 0 survivors under the then-current scope; 1 row later reclassified as a live candidate and since written up (see `positives.md`). Rejects logged in `_INDEX.md`. |

**Narrowed: 329 of 4,489 rows triaged.**

> **These four are complete only against `NarrowedIfStatements.csv`.** They
> were triaged before `HelperGuardedIfStatements.ql` existed, and that query
> finds **114 further rows inside the same four subtrees** (`transport` 63,
> `db/compaction` 43, `concurrent` 6, `cache` 2) that **have never been read**.
> They are not a re-audit — they are rows the pipeline could not produce at
> the time. Worth sweeping before or alongside the next new batch, since these
> subtrees are already familiar.

### Remaining

Two files feed pattern-(a) triage: `NarrowedIfStatements.csv` (comparison in
the `if` condition) and `HelperGuardedIfStatements.csv` (comparison one call
frame down, behind a boolean helper). Grouped by top-level package, with
magnitude-class counts in parentheses — those are the rows to read first,
since a capacity check is inherently a magnitude comparison.

| Top-level package | Narrowed (magnitude) | Helper (magnitude) | Combined magnitude |
|---|---|---|---|
| `db` | 774 (409) | 303 (120) | **529** |
| `utils` | 717 (428) | 92 (48) | **476** |
| `index` | 487 (286) | 94 (57) | **343** |
| `io` | 466 (288) | 72 (41) | **329** |
| `service` | 267 (195) | 169 (114) | **309** |
| `cql3` | 368 (165) | 52 (34) | **199** |
| `config` | 154 (115) | 8 (0) | **115** |
| `net` | 140 (93) | 16 (5) | **98** |
| `tools` | 167 (82) | 21 (5) | **87** |
| `locator` | 98 (58) | 22 (17) | **75** |
| `serializers` | 91 (61) | 18 (2) | **63** |
| `dht` | 78 (52) | 11 (10) | **62** |
| `gms` | 74 (50) | 6 (2) | **52** |
| `repair` | 62 (33) | 43 (16) | **49** |
| `metrics` | 44 (32) | 7 (3) | **35** |
| `schema` | 48 (31) | 11 (1) | **32** |
| `hints` | 34 (23) | 17 (4) | **27** |
| `streaming` | 23 (15) | 9 (5) | **20** |
| `auth` | 30 (13) | 11 (2) | **15** |
| `batchlog` | 10 (8) | 1 (0) | **8** |
| `tracing` | 6 (5) | 1 (1) | **6** |
| `security` | 10 (5) | 0 (0) | **5** |
| `exceptions` | 3 (3) | 0 (0) | **3** |
| `diag` | 3 (2) | 0 (0) | **2** |
| `audit` | 4 (1) | 0 (0) | **1** |
| `triggers` | 2 (1) | 1 (0) | **1** |
| **Total** | **4160 (2454)** | **985 (487)** | **2941** |

**Reading the numbers.** 5,145 rows remain in total, but the realistic first
pass is the **2,941 magnitude rows**; the 2,204 equality rows are a
lower-priority sweep afterwards. The helper rows shrink further in practice:
across the whole corpus they come from only ~300 distinct helpers, so triage
judges each *helper* once and applies the verdict to all its call sites —
sorting a batch's helper rows by frequency disposes of the repeated
non-candidates (`ProtocolVersion.isGreaterOrEqualTo()`, `DeletionTime.supersedes()`)
in one judgment each.

**Suggested order.** `config` and `net` are small, dense in magnitude rows,
and adjacent to constraints already understood (`net` partly covered by the
two `*_receive_queue_capacity` cases), so they are cheap batches to
recalibrate on. `db`, `utils`, `index` and `io` together hold over half the
remaining work and are better attempted once the judging pace is established.

## History

- **2026-09-22** — coverage table refreshed against the new `pkg` column and
  the new `HelperGuardedIfStatements.csv`; batch names clarified as subtrees,
  and the 114 unread helper rows inside the four done batches recorded.
- **2026-09-22** — folder restructured into `positives.md` / `negatives.md` /
  `deferred.md`; the former single `candidates.md` was folded into this
  README (coverage table) and those three files.
- **2026-09-18** — disk (on-disk bytes) added alongside memory to this
  folder's scope, per Jingsong's call; see
  [`../README.md` §3.3](../README.md#33-resource-scope-memory-and-disk). One
  row previously rejected for being disk-scoped
  (`CompactionAwareWriter.getWriteDirectory():282`) was reclassified live as
  a direct result.
