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

## How a row is triaged

> Practical technique — the priority tiers, the verified reject rules, what
> signals exist in a row — is in
> [`stage2-playbook.md`](stage2-playbook.md). This section is the definition
> of what stage 2 is and is not.

Stage 2 works **only from the row**: `lhs`, `op`, `rhs`, `pkg`,
`declaringType`, `method`, `opClass`, and for helper rows `helper` /
`helperLine`. It does **not** open the Cassandra source.

**It does not apply the three rules**
([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)).
Those decide whether a candidate is a real case and require reading the
code — Rule 3 asks whether the branches diverge on object creation, which no
row can answer. They belong to the deep-read pass that follows.

What stage 2 does instead:

1. **Rule out** rows the row itself shows are not capacity checks — a
   comparison against a bare literal, an ordering test (`compareTo()`), a
   loop index, a method whose name marks it as config validation or
   serialization arithmetic. These go to [`negatives.md`](negatives.md) citing
   the *row-level* ground, not a rule number.
2. **Rank** everything else into priority tiers on the evidence in the row:
   capacity-shaped operand names, a compound usage side (`... + ...`),
   allocation-adjacent class and method names. These go to
   [`positives.md`](positives.md) **with their tier**.
3. **Park** anything that would only qualify under pattern (b) or (c) in
   [`deferred.md`](deferred.md).

> **Next pass (planned 2026-09-22):** stage 2's ranking moves from the fixed
> capacity-word list to **AI lexical judgement** of the row — reading the
> operand names, class, method and package for what they actually mean
> instead of matching a word list. This is what §7.2's "deliberately no fixed
> keyword list" rule always implied. Rationale, the keyword list's
> demonstrated failure modes, and how to run it are in
> [`stage2-playbook.md`](stage2-playbook.md).

**Rank rather than reject when unsure.** Stage 2 is cheap and blind; the
deep read is expensive and sighted. A row wrongly rejected here is never seen
again, while a row wrongly promoted only costs some reading. Downranking is
always available and always safer than refusing.

## One line, one place

Rejections from the *other* discovery method (direct AI search) live in
[`../_INDEX.md`](../_INDEX.md)'s "lines considered and rejected" section, not
here — they differ in kind (few, narrative, often deferred rather than firmly
refused). If stage 2 reaches a line that method 1 already judged, **cite the
`_INDEX.md` entry rather than re-recording it here.**

## Progress at a glance

> **Update this block first** when a batch finishes; the detail tables below
> are the working record, this is the summary. All counts reproduce from the
> CSVs in `codeql-queries/results/cassandra/` — see
> [`stage2-playbook.md`](stage2-playbook.md)'s scope table before quoting any
> single number elsewhere.

**Stage 1 — the pattern-(a) corpus (fixed, regenerable):**

| Input | Rows | magnitude | equality |
|---|---|---|---|
| `NarrowedIfStatements.csv` | 4,489 | 2,681 | 1,808 |
| `HelperGuardedIfStatements.csv` | 1,099 | 577 | 522 |
| **Total** | **5,588** | **3,258** | **2,330** |

Funnel: 17,343 `if` statements → 10,147 direct comparisons → 4,489 numeric
non-trivial, plus 1,099 helper-guarded (a sibling query, not a funnel step).

**Stage 2 — processed so far:**

| Unit | Narrowed | Helper | Date | Yield |
|---|---|---|---|---|
| 4 subtrees (`concurrent`, `cache`, `transport`, `db/compaction`) | 329 | 114 | 09-18 / 09-22 | 2 promoted, 1 deferred |
| P1 tier (corpus-wide, ~15 pkgs — **overlaps** the above) | 34 | — | 09-22 | 4 candidates, 22 rejected, 3 deferred |

**Stage 2 — remaining:**

| | Narrowed | Helper | Total |
|---|---|---|---|
| magnitude (the real queue) | 2,454 | 487 | **2,941** |
| equality (low-priority sweep) | 1,706 | 498 | **2,204** |
| **all** | **4,160** | **985** | **5,145** |

Tiering of the 2,454 remaining narrowed-magnitude rows:

| Tier | Rows | Status |
|---|---|---|
| P1 | 34 | ✅ done 2026-09-22 |
| P2 (excl. P1) | 337 | next, after the lexical re-rank |
| P3 | 746 | pending — the insurance tier |
| P4 (fast-rejected) | 1,337 | parked, not deleted |

The 487 remaining helper-magnitude rows collapse to **185 distinct helpers**,
so the honest workload is ~2,454 narrowed rows + ~185 helper judgments, not
2,941 rows.

**Cases produced by method 2 so far:** 7 filed (2 verified, 5 pending) + 4 P1
candidates awaiting write-up + 1 pattern-(b) find parked in `deferred.md`.

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
| helper rows in those four subtrees | 114 | 2026-09-22 | **Done.** 23 distinct helpers judged; 21 rejected (108 rows), 1 cited to an existing `_INDEX.md` entry (4 rows), 1 candidate found: `Directories.hasDiskSpaceForCompactionsAndStreams():551`, parked in `deferred.md` as pattern (b). Rejects in `negatives.md`. |

| **P1 tier, corpus-wide** (not a package) | 34 | 2026-09-22 | **Done.** Deep read against the three rules. 4 candidates (`positives.md`), 22 rejected (`negatives.md`), 3 deferred as pattern (b)/(c) (`deferred.md`), 5 already covered by existing records. Spans ~15 packages and completes none of them — see the note below. |

**Narrowed: 329 of 4,489 rows. Helper: 114 of 1,099 rows. P1 tier: 34 rows
(deep-read, overlapping the package counts).**

> **The P1 row is a tier, not a package.** Its 34 rows are scattered across
> ~15 packages, so no package may be marked done on its account. When a
> package batch runs later, its P1 rows are already judged — check
> `positives.md` / `negatives.md` / `deferred.md` before re-reading a row.
>
> **P1 validated the ranking.** It recovered both known filed cases as
> calibration and produced 4 new candidates plus 1 strong pattern-(b) find
> from 34 rows — roughly a 1-in-3 hit rate on rows not already accounted
> for. That justifies continuing tier-first with **P2 (371 rows)**.

> The four subtrees above were first triaged before
> `HelperGuardedIfStatements.ql` existed, so their helper rows were swept
> separately on 2026-09-22 (row above) rather than as a re-audit — those rows
> were ones the pipeline could not produce at the time. All four subtrees are
> now complete against **both** stage-1 inputs.

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

**Reading the numbers.** **5,145 rows remain** (4,160 narrowed + 985 helper;
the 114 helper rows above are now done), but the realistic first pass is the
**2,941 magnitude rows**; the 2,204 equality rows are a lower-priority sweep
afterwards. The helper rows shrink further in practice:
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
