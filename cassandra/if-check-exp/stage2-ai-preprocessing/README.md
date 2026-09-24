# Stage 2 — AI lexical preprocessing

This folder holds the **stage-2 verdicts**. Stage 2 takes the stage-1 rows —
one row per `if` statement — and an AI session reads them without opening the
Cassandra source. It does **one** thing: **rank every row** by how
likely it is to become a valid case. The ranked rows are stage 2's result,
and stage 3's queue.

**Stage 2 rules nothing out** (decided 2026-09-23). A row that looks
impossible gets the bottom rank, not an exit from the queue. See
[`../README.md` §7.2](../README.md#72-discover-and-qualify-candidate-capacity-checks) for how the three stages relate, and §7.5 for
the scope currently in force.

**Input:** the two stage-1 CSVs, described in
[`../stage1-codeql-preprocessing/README.md`](../stage1-codeql-preprocessing/README.md)
— which is also where the row counts, the run commands and stage 1's
structural blind spot live. They are gitignored and regenerated per machine,
so nothing about a result set is committed or pinned. Read `magnitude` rows
before `equality` ones.

## Files

| File | Holds |
|---|---|
| [`bands.md`](bands.md) | **Stage 2's result** — the bands explained, band A grouped by what the limit is, and the run's provenance. Stage 3's 3a queue, a work list, **not** a list of qualified cases. |
| [`bands.csv`](bands.csv) | **The per-row verdicts** — `uid, kind, band, reason, model, date, batch`. Committed, because an AI band cannot be regenerated the way the old keyword tiers could. |
| [`playbook.md`](playbook.md) | **Start here when running a batch.** The four bands, the batch procedure, the calibration rows, and the tricks and pitfalls learned so far. Not a verdict store. |

Every row stage 2 reads lands in `bands.md` with a rank. **Stage 2 has no
other outcome** — it cannot refuse a row, and it cannot defer one (see below).

## How a row is ranked

> Practical technique — the four bands, how to run a batch, what signals exist
> in a row — is in
> [`playbook.md`](playbook.md). This section is the definition
> of what stage 2 is and is not.

Stage 2 works **only from the row**: `lhs`, `op`, `rhs`, `pkg`,
`declaringType`, `method`, `opClass`, and for helper rows `helper` /
`helperLine`. It does **not** open the Cassandra source.

**It does not apply the three rules**
([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)).
Those decide whether a candidate is a real case and require reading the
code — Rule 3 asks whether the branches diverge on object creation, which no
row can answer. They belong to stage 3, the pass that follows.

What stage 2 does instead: an AI session reads each row as a sentence —
`declaringType` + `method` + `lhs op rhs` — and assigns one of four bands by
lexical and semantic judgement, with a one-line reason. Each row goes to
[`bands.md`](bands.md) with its band.

| Band | The row reads as |
|---|---|
| **A** | A real capacity check — usage compared against a memory or disk limit |
| **B** | Plausibly a resource bound, but the row alone does not settle it |
| **C** | Named operands, nothing resource-shaped — the insurance band |
| **D** | Clearly not one: startup validation, ordering test, loop index, bare literal, serialization arithmetic |

**No keyword list and no mechanical pre-filter** (2026-09-23). The banding is
the AI's reading of the row, start to finish. Rows that look hopeless take
band D and stay in the queue; before 2026-09-23 they were refused outright,
and that is the decision this folder reversed.

**Stage 2 cannot defer.** Deciding that a line "would qualify only under
pattern (b) or (c)" means tracing where the verdict is read and whether the
branches diverge — which no row shows. Deferral is a stage-3 judgment and
lives in
[`../stage3-ai-deep-read/deferred.md`](../stage3-ai-deep-read/deferred.md).
If a row *smells* like (b)/(c), **downrank it and let stage 3 decide**; do
not park it and do not refuse it.

> **Done 2026-09-24.** The banding ran as designed: 37 batches, anchors in
> every batch, model and date recorded per batch, and the acceptance test held
> throughout. Re-running it is only needed if the bands are re-derived with a
> different model. See [`playbook.md`](playbook.md#how-to-run-a-batch).

**Rank, never rule out.** Stage 2 is cheap and blind; the deep read is
expensive and sighted. A row wrongly refused here would never be seen again,
while a row wrongly ranked high only costs some reading — and a row wrongly
ranked low is still reachable. That asymmetry is the whole argument for having
no reject step.

## One line, one place

Rejections made by **stage 3** (source open, three rules applied) live in
[`../stage3-ai-deep-read/rejected.md`](../stage3-ai-deep-read/rejected.md),
not here — they differ in kind: few, narrative, often
deferred-rather-than-refused, and citing a rule rather than a row-level
ground. If stage 2 reaches a line that stage 3 already judged, **cite that
entry rather than re-recording it here.**

Verdicts are filed by **the stage that judged**, not the stage that surfaced
the row: a row stage 2 ranked and stage 3 then refused is a *stage-3*
rejection.

## Progress at a glance

> **Update this block first** when a batch finishes; the detail tables below
> are the working record, this is the summary. All counts reproduce from the
> CSVs in `codeql-queries/results/cassandra/` — see
> [`playbook.md`](playbook.md#counts-and-scopes) before quoting any
> single number elsewhere.

**Stage 2 is one operation** — rank every stage-1 row by AI lexical and
semantic judgement. See
[`playbook.md`](playbook.md#what-stage-2-does--rank-every-row).

**The banding is complete, and covers every stage-1 row.** 4,789 units over
40 batches on 2026-09-23/24 with `claude-opus-5`; per-row verdicts are in
[`bands.csv`](bands.csv), grouped and explained in
[`bands.md`](bands.md).

| Input | Units | Banded |
|---|---|---|
| `NarrowedIfStatements.csv` | 4,489 rows | **4,489 (100%)** |
| `HelperGuardedIfStatements.csv` | 1,099 rows → 300 distinct helpers | **300 (100%)** |

| Band | Meaning | Units | Share |
|---|---|---|---|
| **A** | Reads as a real capacity check | **134** | 2.8% |
| **B** | Plausibly a resource bound, row does not settle it | 174 | 3.6% |
| **C** | Named operands, nothing resource-shaped — the insurance band | 94 | 2.0% |
| **D** | Clearly not one | 4,387 | 91.6% |

**Anchors passed on all 40 batches** — the 8 labelled rows came back A every
time, which is the only designed evidence that separate batches share one
yardstick. One accidental check corroborates it: 8 helpers fell into both
scopes and were judged twice in unrelated batches, and all 8 agreed.

**Reading `bands.csv`'s `batch` column: group by `(batch, date)`, not
`batch`.** The 40 batches carry only 38 distinct labels — the second run
restarted numbering at `batch-01`, colliding with the first on `batch-01`
to `batch-03` (703 units). Provenance only, no verdict affected; the detail
is in [`bands.md`](bands.md)'s Run section.

Band A splits three ways, and only the first is likely to survive §6.1:
**A1 configuration-derived (65)**, **A2 constants and structural bounds (30)**,
**A3 grow-when-full array reallocations (39)**. The split is a reading aid, not
a verdict — see [`bands.md`](bands.md).

| | State |
|---|---|
| Ranking | ✅ complete, full coverage |
| Rule-outs | None, from 2026-09-23. Stage 2 has no rejection file. |
| Next | Stage 3 reads band A in A1 → A2 → A3 order |

Which CSV a row came from, whether it is magnitude or equality, and whether
its comparison hides behind a helper are **signals and reading order**, not
further stages. **Reading a band is stage 3's job**, not stage 2's.

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
| Capacity-word pass (corpus-wide, ~15 pkgs — **overlaps** the above) | 34 | — | 09-22 | 4 candidates, 22 rejected, 3 deferred |

**Stage 2 — remaining:**

| | Narrowed | Helper | Total |
|---|---|---|---|
| magnitude (the real queue) | 2,454 | 487 | **2,941** |
| equality (low-priority sweep) | 1,706 | 498 | **2,204** |
| **all** | **4,160** | **985** | **5,145** |

The former keyword tiers — four bands of 34 / 371 / 746 / 1,337 rows,
strongest first — were **dropped on 2026-09-23** and are not being carried
forward. Why, and what was given up
with them, is in
[`playbook.md`](playbook.md#why-the-keyword-list-was-dropped-2026-09-23).

The 487 remaining helper-magnitude rows collapse to **185 distinct helpers**,
so the honest workload is ~2,454 narrowed rows + ~185 helper judgments, not
2,941 rows.

**Stage-3 outcomes from rows this folder ranked:** 4 candidates awaiting
write-up (`../stage3-ai-deep-read/pending.md`) + 1 pattern-(b) find parked in
`../stage3-ai-deep-read/deferred.md`. No case has yet been *established* from
this queue — all 7 filed cases came from feed 3b.

## Batch coverage

Triage proceeds by directory batch rather than top-to-bottom, since the corpus
is far too large to read linearly in one pass. Batches are recorded here so
later sessions don't re-scan them.

> **This table tracks which stage-1 rows have been *consumed*, whichever
> stage consumed them.** Most entries are stage-2 triage batches, but the
> "capacity-word pass" row records a **stage-3** deep read of rows this folder had
> ranked. It is kept here because its purpose is the same — stopping a later
> session re-reading rows already judged — and because the row counts it
> retires are stage-1 row counts. The verdicts themselves live with the
> stage that made them.

Counts below come from the `pkg` column, refreshed 2026-09-22 after stage 1
gained named columns and the `HelperGuardedIfStatements.ql` query. **A batch
name is a subtree**: `transport` covers `transport` and `transport/messages`,
`db/compaction` covers it plus `db/compaction/unified` and
`db/compaction/writers`. The `pkg` column is a leaf, so group on a prefix of
it to reproduce a batch.

### Done

| **Full-corpus AI banding** | **4,789 units** | 2026-09-23/24 | **Done.** 40 batches, `claude-opus-5`: 37 over the un-triaged corpus, then 3 over the four subtrees below, which had verdicts but no band. A 134 / B 174 / C 94 / D 4,387. Anchors passed on every batch. Supersedes the package-by-package plan below for stage-2 purposes: **every stage-1 row now has a band.** The subtrees' older verdicts stand — a band never overrides one made with the source open. |

| Batch (subtree) | Narrowed rows | Date | Result |
|---|---|---|---|
| `concurrent` | 17 | 2026-09-18 | 0 survivors — all thread-pool/permit concurrency checks (Rule 2 fail, same reasoning as `concurrent_compactors`). |
| `cache` | 15 | 2026-09-18 | 0 survivors — ref-counting, overflow guards, and trivial validation; no capacity-vs-limit divergence found. |
| `transport` | 89 | 2026-09-18 | 1 survivor, since promoted to a case file + rejects logged in `../stage3-ai-deep-read/rejected.md`. |
| `db/compaction` | 208 | 2026-09-18 | 0 survivors under the then-current scope; 1 row later reclassified as a live candidate and since written up. Rejects logged in `../stage3-ai-deep-read/rejected.md`. |
| helper rows in those four subtrees | 114 | 2026-09-22 | **Done.** 23 distinct helpers judged; 21 rejected (108 rows), 1 cited to an existing `../stage3-ai-deep-read/_INDEX.md` entry (4 rows), 1 candidate found: `Directories.hasDiskSpaceForCompactionsAndStreams():551`, parked in `../stage3-ai-deep-read/deferred.md` as pattern (b). Those 21 helpers now carry band D in `bands.csv`; the
per-helper arguments are in git history at `43a3c27`. |

| **Capacity-word pass, corpus-wide** (not a package) | 34 | 2026-09-22 | **Done** — but by **stage 3**, not stage 2. 4 candidates (`../stage3-ai-deep-read/pending.md`), 22 rejected (`../stage3-ai-deep-read/rejected.md`), 3 deferred (`../stage3-ai-deep-read/deferred.md` — **only 2 are on file**, see its §1c), 5 already covered. Spans ~15 packages and completes none of them — see the note below. |

**Narrowed: 329 of 4,489 rows. Helper: 114 of 1,099 rows. Capacity-word pass: 34
rows (deep-read, overlapping the package counts).**

> **Those 34 rows are not a package.** They are scattered across ~15
> packages, so no package may be marked done on their account. When a package
> batch runs later, some of its rows are already judged — check
> `../stage3-ai-deep-read/pending.md`, `rejected.md` and `deferred.md` before
> re-reading a row. This is why coverage is now tracked per row rather than
> per band.
>
> **They are also the calibration set.** The batch recovered both known filed
> cases and produced 4 new candidates plus 1 pattern-(b) find — roughly a
> 1-in-3 hit rate on rows not already accounted for. That result was about the
> keyword list, which is gone, but the 34 stage-3 verdicts remain the material
> the AI banding is checked against
> ([`playbook.md`](playbook.md#calibration--the-labelled-rows)).

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

- **2026-09-24** — `positives.md` renamed to [`bands.md`](bands.md), and
  `negatives.md` **deleted**. The rename: the file had held every row in all
  four bands since stage 2 stopped ruling rows out on 2026-09-23, so
  "positives" named a distinction it no longer drew. `candidates.md` was not
  reused — it is a retired name from before 2026-09-22 and would re-imply the
  qualification only stage 3 does. The deletion, decided by Jingsong: the
  file had been closed since 2026-09-23 and could only ever be an archive.
  Its two reference lists — row-level rule-out grounds, and the grounds that
  need the source — moved to [`playbook.md`](playbook.md) first, since that
  guidance is still live; the 108 refused rows carry band D in `bands.csv`,
  and the per-helper arguments stay recoverable in git history at `43a3c27`.
  **`../stage3-ai-deep-read/rejected.md` is now the experiment's only
  rejection file.** No verdict changed and no count moved.
- **2026-09-24** — **coverage closed**: the 329 rows in the four
  already-triaged subtrees, and the 8 anchor rows, had no band — 4,438 units
  had been banded against 4,489 narrowed rows. Three more batches and a direct
  write of the anchors bring it to 4,789 units and 100% coverage. Band A went
  from 113 to 134; the anchors alone account for 8 of that, since band A had
  been missing the filed cases it was validated against.
- **2026-09-24** — **the banding ran to completion**: 4,438 units, 37
  batches, `claude-opus-5`, anchors passing throughout. Verdicts in
  `bands.csv`; band A grouped in `bands.md`. Three bugs in the batch
  builder were caught before any banding — most importantly that `path:line`
  is not a unique row id (340 lines carry more than one comparison, affecting
  738 rows), so ids are now `path:line#n`.
- **2026-09-23** — **the four keyword tiers were dropped.** Ranking is now
  AI lexical/semantic judgement of the row into four bands (A–D) with a
  one-line reason each, over the whole 5,588-row corpus, with no keyword list
  and no mechanical pre-filter. Decided by Jingsong. The list's track
  record — 4/4 known cases in 527 rows, ~1-in-3 on the top tier — was evidence about the
  list, not about ranking, so the banding starts its track record over; the
  labelled rows are the acceptance test.
- **2026-09-23** — **stage 2 no longer rules anything out.** Decided by
  Jingsong: rank every stage-1 row, and let "impossible" be the bottom rank
  rather than an exit from the queue, since a rule-out is permanent and
  invisible while a bad rank self-corrects. `negatives.md` was closed to new
  entries the same day and deleted on 2026-09-24; its rows are now
  bottom-ranked, not refused. Two earlier drafts
  that day — five passes (2.1–2.5), then two operations (rule out / rank) —
  were both superseded as over-structured. No verdict changed and no count
  moved.
- **2026-09-22** — coverage table refreshed against the new `pkg` column and
  the new `HelperGuardedIfStatements.csv`; batch names clarified as subtrees,
  and the 114 unread helper rows inside the four done batches recorded.
- **2026-09-22** — folder restructured into `positives.md` (now `bands.md`) /
  `negatives.md` (since deleted) /
  `../stage3-ai-deep-read/deferred.md`; the former single `candidates.md` was folded into this
  README (coverage table) and those three files.
- **2026-09-18** — disk (on-disk bytes) added alongside memory to this
  folder's scope, per Jingsong's call; see
  [`../README.md` §3.3](../README.md#33-resource-scope-memory-and-disk). One
  row previously rejected for being disk-scoped
  (`CompactionAwareWriter.getWriteDirectory():282`) was reclassified live as
  a direct result.
