# If-Check Exp — Handoff

For a new session picking up `if-check-exp` work. Read this first, then
[`cassandra/if-check-exp/README.md`](cassandra/if-check-exp/README.md) for
the full format spec. This file is self-contained: everything a session
needs is here or in the repo, with no external document required.

This handoff covers `if-check-exp` specifically, since that's the repo's
active experiment; it lives at the repo root (rather than under
`cassandra/if-check-exp/`) so a new session finds it immediately. The paused
sibling experiment has its own brief at
[`cassandra/entry-restriction-exp/HANDOFF.md`](cassandra/entry-restriction-exp/HANDOFF.md)
(split out 2026-09-23) — one handoff per experiment folder, rather than
overloading this one.

**Project context:** the three project-wide targets are in the repo-root
[`README.md`](README.md) §0. The running plan and findings live in two
Google Docs — [*Meeting Summary*](https://docs.google.com/document/d/1tldFFEk28qtQD0QdsnC2Br-BisTyOUp8OCwG1SZ_6Jk/edit)
(per-meeting decisions and next steps) and
[*Progress Report*](https://docs.google.com/document/d/1gMRFwaTvgahSiRi10ad_Y3CLDkxyF1QTYkAhZ4be4x8/edit)
(running log of entry points, cases and findings); a session with the Google
Drive connector enabled can read them directly.

## What this experiment is

Part of the **misconfiguration** research project (Target 1: identify resource
constraints that limit memory/CPU usage; Target 2: show how each constraint
restricts usage via its exact code path; Target 3: bypass analysis — out of
scope for this folder), scoped to **Apache Cassandra 5.0.9**. `if-check-exp`
inventories **capacity checks** and the **decision points** they feed: a
comparison of usage against a capacity limit, and the code where the outcome
diverges (one outcome lets a memory- or disk-significant allocation happen,
the other blocks, defers, or rejects it). Each case always covers Target 1
and Target 2 together: it names the constraint (found by tracing the limit
back to where it is first declared) and shows how the code enforces it.

It is a **standalone inventory** — deliberately not cross-referenced against
the sibling `entry-restriction-exp` folder, even when a line happens to
coincide. It also does **not** do bypass analysis or failure-mode scoring —
pure Target 1 + 2 — though bypass-relevant observations made along the way
are noted in case files for later Target-3 use, not chased down here.

**`if-check-exp` is its own independent experiment.** It does not share
infrastructure, cluster state, or config with any other experiment in this
repo — when setting up infrastructure for this folder, assume
nothing is already provisioned and build/configure it from scratch under
this folder's own scope.

## Working preferences (for a new session)

- **Plan before editing.** For changes to rules, naming, scope, or folder
  structure, first give an opinion or an update plan (which files, what
  changes) and wait for Jingsong's go-ahead. Show old-vs-new names or a
  file-by-file list when asked. Small factual fixes to a file you are
  already working on don't need this.
- **Commit and push only on request.** "Commit" and "push" are asked for
  separately; never do either unprompted.
- **Sync before restructuring.** Jingsong also uploads files to GitHub
  directly, so `git fetch` and compare with `origin/main` before renaming or
  reorganizing files. If local edits exist, stash, fast-forward, then re-apply.
- **Keep settled decisions.** For example, the "no cross-referencing other
  experiments" rule in `cassandra/if-check-exp/README.md` §4 stays because
  Jingsong may not return to `entry-restriction-exp`; don't propose
  cross-check steps against it.

## Where things live

- **Repo:** `MengJingsong/Misconfiguration` on GitHub.
- **Local clone:** kept wherever the current working session's local
  machine keeps it — path and device vary by environment, not fixed
  (a session only writes local files, and commits or pushes only when
  Jingsong asks — see "Working preferences" below).
- **Folder:** `cassandra/if-check-exp/`
  - `README.md` — full format spec: scope, the three rules, required
    fields, naming rules, workflow, how to verify/link line numbers against
    the local Cassandra source, and **§1.1 targets vs. stages** (the two
    numberings are unrelated) and **§7.2 the three stages**.
  - `stage3-ai-deep-read/_INDEX.md` — master table of all cases and the coverage summary.
    **Cases only** — the "lines considered and rejected" table moved to
    `stage3-ai-deep-read/rejected.md` on 2026-09-23.


  - **`stage1-codeql-preprocessing/`** — stage-1 entry point. Holds no
    queries and no results, only pointers: the queries live at the repo root
    under `codeql-queries/`, the CSVs are gitignored. Also records stage 1's
    output counts and its structural blind spot.
  - **`stage2-ai-preprocessing/`** — stage-2 verdicts (lexical, rows only).
    - `README.md` — what stage 2 is, how a row is triaged, the
      "Progress at a glance" dashboard, and the batch-coverage table.
    - `playbook.md` — **start here to run a batch.** The one rule (rank,
      never rule out), the four bands (A–D), what band D looks like and the
      grounds that need the source instead, how to run a batch, the
      calibration rows, and the tricks and pitfalls learned so far.
    - `bands.md` — the banding result: bands explained, band A grouped by
      what the limit is, run provenance. Stage 3's 3a queue.
    - `bands.csv` — **the per-row verdicts**, committed because an AI band
      cannot be regenerated the way the old keyword tiers could.
  - **`stage3-ai-deep-read/`** — stage-3 verdicts (semantic, source open).
    This is the deciding stage.
    - `README.md` — what stage 3 is, its two feeds, and where verdicts go.
    - `playbook.md` — how to run a pass: the order to check things, and the
      verified pitfalls.
    - `_TEMPLATE.md` — template for a new case file (stage 3's output, so
      the template lives with stage 3). Its §9 Provenance records the feed
      (`3a`/`3b`) and the date the cited lines were checked.
    - `rejected.md` — read with the source open, refused against the three
      rules. Moved here from `stage3-ai-deep-read/_INDEX.md` on 2026-09-23.
    - `cases/` — **the results**: one flat file per case (flattened from
      per-module folders 2026-09-23; module is a field, not a folder).
    - `deferred.md` — unjudged: would qualify only under pattern (b) or (c),
      parked by the scope decision below. Kept apart from `rejected.md`
      because they are undecided, not refused. Moved here from the stage-2
      folder, since **stage 2 cannot produce a pattern deferral**.
- **`codeql-queries/`** (repo root, [README](codeql-queries/README.md)) — the
  CodeQL query packs that feed `stage2-ai-preprocessing/`; the if-check queries
  and their
  [pipeline README](codeql-queries/cassandra/queries/if-check-exp/README.md)
  are under `codeql-queries/cassandra/queries/if-check-exp/`. Results land in
  the gitignored `codeql-queries/results/` and must be regenerated on a new
  machine.
- **Outside this repo (CloudLab shared mount, see root `README.md` §2):**
  `git-repos/cassandra-src`, `tools/codeql/`, `codeql-dbs/`.

## Cassandra source (for stage-3 reading)

- **Local clone:** `/proj/misconfiguration-PG0/git-repos/cassandra-src`, a git
  clone of `apache/cassandra` at tag `cassandra-5.0.9` (separate from this
  repo, not tracked by it). On another machine, clone it yourself (command in
  `cassandra/if-check-exp/README.md` §2). Unit-test verification runs
  `ant testsome` in this clone.
- Confirm the version with `git describe --tags` (prints `cassandra-5.0.9`);
  `build.xml`'s `base.version` and `CHANGES.txt`'s top entry both read `5.0.9`.
- **Always grep/read the local clone to verify a line number**, then build
  the GitHub link as `.../blob/cassandra-5.0.9/<path relative to repo
  root>#L<NN>`. Never cite a line from memory or from a GitHub fetch alone.

## Current state — 7 cases filed

All seven are stage-3 complete: judged against the three rules with the
source open, citations checked against the pinned `cassandra-5.0.9` tag.
**There is no `Status` field** — manual and runtime verification are out of
this folder, reserved for a future **stage 4** (2026-09-23, see "Scope
decisions"). A filed case is complete *as stage-3 evidence*, not a verified
result. `Feed` records which stage-3 feed found it (`3a` = via
stage 1/2, `3b` = direct source reading).

| Case (file under `cassandra/if-check-exp/`) | Pattern | Feed | Key finding |
|---|---|---|---|
| `memtable_heap_space-tryAllocate-limit.md` | (b) | 3b | Disallow parks the caller; a `markBlocking()` op overshoots the limit (escape hatch). |
| `memtable_offheap_space-tryAllocate-limit.md` | (b) | 3b | Same check on the `offHeap` `SubPool`; same escape hatch. |
| `internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md` | (b) | 3b | Per-connection byte cap (default 4MiB); disallow registers on a wait queue, message not dropped; no escape hatch found. |
| `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md` | (b) | 3b | Same check via `CQLMessageHandler` (default 1MiB). With the default `native_transport_throw_on_overload=false` the message is still decoded; only `throwOnOverload=true` rejects. |
| `MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md` | (a) | 3b | JVM property cap (default 3) on off-heap `HintsBuffer`s; disallow blocks on `reserveBuffers.take()`; no escape hatch found. |
| `cdc_total_space-processNewSegment-allowance.md` | (b) | 3b | Byte cap on un-consumed CDC segments; `processNewSegment():335` sets a `CDCState`, `throwIfForbidden():214` throws `CDCWriteException` (clean reject). Escape hatch: `cdc_block_writes=false`. |
| `DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md` | (c) | 3b | Disk guard on compaction output vs. free space. **The guard does not dominate the allocation** — on the default `diskBoundaries != null` path the `SSTableWriter` is created with no space check at all. |

Each case's full detail lives in its own file.

## Open items / next steps

### ⏵ Resume here (state as of 2026-09-24, end of session)

**Where the pipeline stands.** Stage 1 is complete for pattern (a) — four
CodeQL queries, two CSVs, 5,588 rows. **Stage 2 is complete, with every
stage-1 row banded**: 4,789 units (4,489 narrowed rows + 300 distinct helpers
standing for 1,099 helper rows) over 40 batches on 2026-09-23/24 with
`claude-opus-5`. Verdicts are in `stage2-ai-preprocessing/bands.csv`, grouped
in `bands.md`. Seven cases are filed, all stage-3 complete, and 34 further
rows carry stage-3 verdicts from the capacity-word pass.

| Band | Meaning | Units |
|---|---|---|
| **A** | Reads as a real capacity check | **134** |
| **B** | Plausibly a resource bound | 174 |
| **C** | Named operands, nothing resource-shaped — the insurance band | 94 |
| **D** | Clearly not one | 4,387 |

Band A splits into **A1 configuration-derived (65)**, **A2 constants and
structural bounds (30)**, **A3 grow-when-full reallocations (39)**. Only A1 is
likely to survive §6.1. Anchors — the 8 labelled rows — passed on all 40
batches; that is the only designed evidence separate batches share one
yardstick, since run-to-run consistency is deliberately not measured. One
accidental check corroborates it: 8 helpers fell into both batch scopes and
were judged twice in unrelated batches, and all 8 agreed.

**Stage 3 is now the bottleneck.** Its 3a queue is full for the first time.

| Stage-1 corpus | Rows | magnitude | equality |
|---|---|---|---|
| `NarrowedIfStatements.csv` | 4,489 | 2,681 | 1,808 |
| `HelperGuardedIfStatements.csv` | 1,099 | 577 | 522 |
| **Total** | **5,588** | **3,258** | **2,330** |

| Stage-2 coverage | Narrowed | Helper | Total |
|---|---|---|---|
| Consumed — 4 subtrees + the capacity-word pass (overlapping) | 329 | 114 | — |
| Not yet consumed | 4,160 | 985 | **5,145** |

**All 5,588 rows need a band**, including the consumed ones if a band is ever
wanted for them; coverage is tracked **per row**, by whether it carries a
stage-3 verdict, not per band. The canonical version of every number here
lives in `stage2-ai-preprocessing/README.md`'s "Progress at a glance" —
update that first.

**Stage 2 is one operation** — rank every stage-1 row by AI lexical and
semantic judgement into four bands: **A** reads as a real capacity check, **B**
plausibly a resource bound, **C** named operands with nothing resource-shaped
(the insurance band), **D** clearly not one. Each row also carries a one-line
reason. Output is `bands.md`.

**It rules nothing out** (2026-09-23): a hopeless row takes band D rather than
an exit from the queue, because a rule-out is permanent and invisible while a
bad band self-corrects. **Stage 2 has no rejection file at all** — the
former `negatives.md` was deleted on 2026-09-24. **The four keyword tiers
were dropped the same day** — no fixed word list and no mechanical
pre-filter; the banding is the AI's reading of the row, start to finish.
Ranking the whole corpus costs about 107k input / 140k output tokens, so there
is no saving worth buying with a heuristic that might drop a real case.

**The immediate next work, in order:**

1. **Stage 3 reads band A, in A1 → A2 → A3 order.** 134 rows, but far fewer
   distinct arguments: A3's 39 rows share one shape (`size == capacity` before
   growing an array), so judge them as a group rather than one at a time. Two
   A-band rows are **already refused** — `NativeAllocator$Region.allocate():273`
   and `SlabAllocator$Region.allocate():201`, in `rejected.md` — so check the
   stage-3 files before reading any row.
2. **Three open items the banding independently surfaced**, each already in
   band A:
   - `CommitLogSegmentManagerCDC.java:345` — the third `cdc_total_space` site,
     which item 3 below says is recorded nowhere. Still needs judging.
   - `ResourceLimits$Basic.tryAllocate():213` and `$Concurrent:138` — the
     mechanism the two net cases fail to cite (item 3 below).
   - `Directories.hasDiskSpaceForCompactionsAndStreams():551` — the pattern-(b)
     find parked in `deferred.md`.
3. **Write up the 4 candidates from the capacity-word pass as case files.** Found,
   judged and recorded in `stage3-ai-deep-read/pending.md`, but no case file
   exists yet. Start with `BufferPool_memoryUsageThreshold` (strongest); its
   main open task is tracing `memoryUsageThreshold` to its config source for
   the §6.1 constraint name. `TeeDataInputPlus_limit` is the weakest — confirm
   `limit`'s origin before committing to it. `Integer_MAX_VALUE` needs a §6.1
   naming judgement, since the constraint is a *type bound*.
4. **One correction to existing case files**, found by the capacity-word pass: the two
   net cases should link `ResourceLimits$Basic.tryAllocate():213` as the
   mechanism behind their reserve sub-checks. They currently name
   `ResourceLimits.Outcome` (the enum) but never cite the comparison itself.
   *(The other correction — `cdc_total_space` missing the
   `permitSegmentMaybe():200` second check site — was **already applied**;
   the case file cites it as "Second check site, same verdict". Verified
   2026-09-23.)*
5. **Then band B (174)**, then C (94) — C is the insurance band and is not
   optional. D is 4,387 rows and is read last, if at all.

**What stage 2 will not tell you.** A band is a reading order, nothing more.
The bands were assigned from the row alone, with the source unread, so a
band-A row can still fail any of the three rules — and several will. The
banding's only measured property is that the 8 labelled rows land in A.

**Do not** start patterns (b)/(c), and do not run behavioral verification —
both are deferred by decision (see "Scope decisions" below). `deferred.md`
is their worklist.

### ⏵ Step 1 in detail — the AI banding (decided 2026-09-23)

**Ranking is AI lexical/semantic judgement of the row, and nothing else.** The
fixed capacity-word list that produced the four tiers is gone, and so is the
bare-literal / `compareTo` fast-reject; both were dropped on 2026-09-23. The
full procedure is in `stage2-ai-preprocessing/playbook.md` — this is the
summary.

**Why the list went.** It failed in both directions. False positives:
`phi_convict_threshold > 16`, `repair_session_max_tree_depth > 20`,
`memtable_cleanup_threshold > 0.99f`, `default_keyspace_rf <
..._fail_threshold` — all contain `threshold`/`max`, none bounds bytes, and
all sit in `applySimpleConfig`, i.e. startup validation. False negatives:
capacity-shaped vocabulary the list never anticipated (`remaining()`,
`keysWritten >= keysEstimate`, `unused`). This is what README §7.2's
"deliberately no fixed keyword list" rule always implied.

**What went with it.** The list's track record — 4/4 known cases selected in
527 of 2,681 magnitude rows, ~1-in-3 hit rate on the top tier — was evidence about *the
list*, not about ranking in general. The banding starts its track record over.

**How it works:**

- Judge the row as a sentence — `declaringType` + `method` + `lhs op rhs`.
  Context usually decides before the operand does; anything in
  `applySimpleConfig`/`validate*` is validation whatever it compares, and
  anything in a `*Pool.allocate` deserves a look whatever it is called.
- Assign one of four bands — A real capacity check / B plausible / C named
  operands, nothing resource-shaped / D clearly not one — plus a **one-line
  reason**, which is what makes a wrong band reviewable.
- **C is not optional.** `memtable_heap_space` and `MAX_HINT_BUFFERS` share no
  vocabulary at all, so a real case can read as unremarkable in every word.
  Merging C into D rebuilds the keyword list's blind spot.
- **D is read eventually** — the bottom of the order, not a bin.
- Anchor every batch against the same ~8 labelled rows; record model and date.
  Run-to-run consistency is **not** measured (2026-09-23).
- Acceptance test: the known cases must land in band A.

**The limit that remains either way:** lexical meaning cannot settle the three
rules. Stage 2 orders the queue; qualification stays with the deep read.


### The three stages and stage 3's two feeds (revised 2026-09-23)

Both feed the same case files and answer to the same three rules
(README §3.4–§3.6); they are complementary, not alternatives. Full write-up
in `cassandra/if-check-exp/README.md` §7.2.

Work is organised as **three stages, numbered by evidence standard** — how
strongly a line has been evidenced — not by position in a pipeline. A stage
can be entered directly. (These numbers have nothing to do with the three
Target numbers; see `cassandra/if-check-exp/README.md` §1.1.)

| Stage | Evidence | Reads source? | Decides? | Folder |
|---|---|---|---|---|
| **1** | structural — the shape of the code (CodeQL) | queries the DB | no | `stage1-codeql-preprocessing/` |
| **2** | lexical — operand, class, method and package *names*, banded A–D by AI | **no** | no | `stage2-ai-preprocessing/` |
| **3** | semantic — the code itself, against the three rules | yes | **yes** | `stage3-ai-deep-read/` |

**Stage 3 is the only stage that decides.** Stages 1 and 2 produce no
findings — they shrink and order what stage 3 must read.

**Stage 3 has two feeds, and both are required:**

- **3a — from stage 1/2.** Takes `bands.md` in band order. Bounded and
  enumerable, so progress is measurable.
- **3b — from raw source.** The session reads subsystems and call chains
  directly. Unbounded, so there is no denominator and no percentage to
  report. **Not optional:** it is the standing insurance against stage 1's
  structural blind spot — it found the `cdc_total_space` ternary, which
  stage 1 cannot surface at all because it is not an `if` condition.

Record the feed (`3a`/`3b`) on every case and verdict.

**Verdicts are filed by the stage that judged them, not the stage that
surfaced the row** (revised 2026-09-23). A row stage 2 ranked and stage 3
then read and refused is a *stage-3* rejection.

| | Stage 2 verdict | Stage 3 verdict |
|---|---|---|
| Rejected | *(cannot reject)* | `stage3-ai-deep-read/rejected.md` |
| Deferred | *(cannot defer)* | `stage3-ai-deep-read/deferred.md` |
| Qualified | *(cannot qualify)* | a case file in `stage3-ai-deep-read/cases/`, indexed in `_INDEX.md` |

**Stage 2 cannot produce a pattern-(b)/(c) deferral** — deciding that needs
the branches read, which no row shows. All deferrals are stage-3 judgments,
which is why `deferred.md` lives in the stage-3 folder.

One line is recorded in exactly one place — if stage 2 reaches a line stage 3
already judged, cite the stage-3 entry instead of re-recording it
(`db/compaction/` rows were triaged both ways and would otherwise duplicate).

**Priority 1 — CodeQL + AI preprocessing (2026-09-22).** Candidate discovery
is an explicit two-stage pipeline, and running it takes precedence over the
remaining items below.

1. **Stage 1 — mechanical filtering (CodeQL).** Run the queries to narrow the
   search space. Results stay where they already land: the **gitignored**
   `codeql-queries/results/cassandra/` (decided 2026-09-22 — no
   `mechanical-filtering-results/` folder in the experiment tree, and nothing
   about a result set is pinned or committed, since it is regenerated per
   machine from the pinned queries and the `cassandra-5.0.9` DB anyway).
   CodeQL only shrinks the search space — it decides nothing about
   qualification.
2. **Stage 2 — AI filtering (preprocessing only).** Work from the stage-1
   rows alone — operand names, enclosing class/method, package, operator
   class — **without reading the Cassandra source**. One operation: **band
   every row A–D** by AI lexical/semantic judgement of how likely it is to
   become a valid case; nothing is ruled out. Record everything under
   `cassandra/if-check-exp/stage2-ai-preprocessing/` — that
   folder *is* the AI-filtering-results store. Every row goes to
   `bands.md` with a band and a one-line reason — there is no second
   destination; pattern-(b)/(c)-only rows to `deferred.md`.

   **Stage 2 does *not* apply the three rules** (README §3.4–§3.6). Those
   qualify a real case and need the code — Rule 3 asks whether the branches
   diverge on object creation, which no row can answer. They belong to the
   stage-3 pass, which takes `bands.md` in band order and
   promotes what qualifies into case files.

   **Because stage 2 is blind, it ranks and never rejects.** A wrong
   rejection is permanent and invisible; a wrong promotion costs a little
   reading. The band definitions, what band D looks like, and the grounds
   that need the source instead are in
   `stage2-ai-preprocessing/playbook.md`.

### The capacity-word pass — run 2026-09-22, done

The 34 rows selected by a capacity word on either side **and** a compound
usage side — the top tier of the keyword scale, before that scale was
dropped on 2026-09-23. All 34 deep-read against the three rules. Outcome: **4 new
candidates, 22 rejected, 3 deferred as pattern (b)/(c), 5 already covered.**
*(Audit 2026-09-24: only 2 deferrals are on file, so 33 of the 34 rows are
accounted for — see `stage3-ai-deep-read/deferred.md` §1c.)*
Details in `stage2-ai-preprocessing/bands.md` and
`stage3-ai-deep-read/rejected.md` / `deferred.md`.

**The ranking validated.** The pass recovered both known filed cases as calibration
and yielded 4 new candidates plus 1 strong pattern-(b) find — about a
1-in-3 hit rate on rows not already accounted for.

> **Superseded 2026-09-23.** This section closed by naming the next tier
> down — 371 rows — as the next step. The keyword tiers were dropped the
> next day and that pass never ran; the whole corpus was banded A–D instead. **Do not act on that
> next step** — the current one is band A, in the "Resume here" section
> above. What survives from this pass is its 34 stage-3 verdicts and the 4
> candidates below.

**The 4 candidates** (none written up yet — this is the immediate next work):

| Candidate | Check |
|---|---|
| `BufferPool_memoryUsageThreshold` | `BufferPool$GlobalPool.allocateMoreChunks():443` — disallow returns `null`, allow does `new Chunk(allocateDirectAligned(MACRO_CHUNK_SIZE))`. Strongest of the four; an explicit off-heap ceiling immediately before the allocation. |
| `MAX_MATERIALIZED_KEYS` | `QueryController.materializeKeysAndCloseSource():449` — disallow discards the accumulated `List<PrimaryKey>` and returns `null`. |
| `Integer_MAX_VALUE` (index summary) | `IndexSummaryBuilder.maybeAddEntry():204` — disallow skips the entry and logs "index summary exceeded (2GiB)". Constraint is a **type bound**, which Target 1 admits but §6.1 naming does not cleanly cover. |
| `TeeDataInputPlus_limit` | `TeeDataInputPlus.maybeWrite():58` — weakest; confirm `limit`'s origin before writing it up. |

**Two open actions on existing cases**, both surfaced by the capacity-word pass:

1. `CommitLogSegmentManagerCDC.permitSegmentMaybe():200` is a **second check
   site of the filed `cdc_total_space` case** (the re-permit path, same
   `CDCState` verdict, same decision point). README §6.1's "one case, several
   check sites" applies; that case file does not list it.
2. `ResourceLimits$Basic.tryAllocate():213` is the generic limiter behind the
   two net cases' reserve sub-checks. Worth linking from those case files
   rather than filing separately.

**Notable rejection worth remembering:** `NativeAllocator$Region.allocate():273`
and `SlabAllocator$Region.allocate():201` look like memtable capacity checks
but are writer-rollover — a full region just causes `trySwapRegion()` to
allocate a new one. The real ceiling is the already-filed
`MemtablePool.tryAllocate()`. Same archetype as the 5 `BTree MAX_KEYS` rows
and `MmappedRegions`.

### Scope decisions: pattern (a) only (2026-09-22); verification is stage 4 (2026-09-23); stage 2 never rules out (2026-09-23)

**Triage is restricted to enforcement pattern (a)** — the capacity check is
itself the `if` whose branches decide allow vs. disallow (README §3.2).
Patterns (b) (check sets a verdict read by a separate decision point) and
(c) (guard clause before an allocation outside any branch) are **not being
triaged yet**: how to handle them systematically is still an open question,
so they are deliberately parked rather than half-done. **They resume once
pattern (a) is finished** — this is a sequencing decision, not a narrowing of
the folder's scope; (b) and (c) remain in scope and their rules in README
§3.2 stand unchanged.

What follows from this:

- **Already-filed cases are unaffected.** Four of the seven existing cases
  are pattern (b). This decision governs *new candidate triage* only;
  existing case files keep their recorded pattern.
- **(b)/(c)-only rows go to `deferred.md`, not a rejection file.** A row
  dropped only because "the `if`'s own branches don't diverge" is not
  rejected — it is simply unjudged under (b)/(c). A separate file (rather
  than a status column, which invites skimming past it) means resuming
  (b)/(c) later is a matter of reading one file instead of re-scanning the
  corpus. Rejections on pattern-independent grounds (thread-pool or
  concurrency caps, rate limiters, config validation, time checks, writer
  rollover) were once recorded in the stage-2 `negatives.md`; it closed on
  2026-09-23 when stage 2 stopped rejecting rows and was deleted on
  2026-09-24, its rows now carrying band D in `bands.csv` — bottom-ranked,
  not settled.
- **The existing CodeQL scripts already fit pattern (a) — confirmed by
  reading `NarrowedIfStatements.ql` (2026-09-22), not just its README.** It
  selects `BinaryExpr` comparisons whose `getEnclosingStmt()` is an `IfStmt`,
  numeric operands only, nulls and literal-only pairs dropped — structurally
  exactly pattern (a). No query changes are needed and the three planned
  structural queries are *not* prerequisites, so stage 2 is unblocked now.
  The boolean-helper gap — a pattern-(a) check hidden behind a helper such as
  `if (!pool.hasRoom())`, leaving the `if` with no comparison — was **closed
  2026-09-22** by the new `HelperGuardedIfStatements.ql` (1,099 rows from 300
  distinct helpers), so stage 1's pattern-(a) input is now
  `NarrowedIfStatements.csv` **plus** `HelperGuardedIfStatements.csv`. One
  residual limit stands: the queries capture the *form* only, so Rule 3 (do
  the branches actually diverge on allocation?) can be answered **only by the
  stage 3** — not by stage 1, and not by stage 2 either, since neither sees
  the branches.
**Verification is out of this folder, reserved for a future stage 4
(2026-09-23).** Decided by Jingsong. A stage-3 case still needs **manual
verification** (a person reads the traced path and agrees) and **runtime
verification** (a trigger drives execution into the disallow branch on a
running cluster). Neither happens here: this folder ends at stage 3, the
README's verification section is gone, and there is no `Status` field. A
case's evidence is its traced code path checked against the pinned tag — what
Target 2 asks for, and complete as stage-3 evidence.

Stage 4 is **reserved, not scheduled** — nothing built, no folder, no case
queued. It gets its own number because the stage numbers mean *evidence
standard*, not pipeline position (README §7.2), and behavioral evidence is a
higher standard. Keeping it outside also preserves this folder's rule that
everything here is decidable from source alone — no cluster, no build, no run.
Earlier trigger designs and results are recoverable from git history
(`git show e7f9963`).

- **Deferred with (b)/(c):** the disk candidate `getWriteDirectory():282`
  (pattern (c) — previously item 2 below), the three planned structural
  CodeQL queries (comparisons anywhere, guard clauses, verdict links — they
  exist only to surface (b)/(c)), and the 2026-09-20 re-audit of earlier
  rejections under (b)/(c). All three are listed under "Deferred until
  pattern (a) is finished" below.

### `stage2-ai-preprocessing/` layout (applied 2026-09-22)

`candidates.md` was folded into `stage2-ai-preprocessing/README.md` (which keeps the
batch-coverage table and the judging procedure) and the rest split into
`bands.md`, `negatives.md` and `deferred.md`, so each file has one job.
(`negatives.md` was deleted on 2026-09-24 — see below.)
References in `stage3-ai-deep-read/_INDEX.md`, the codeql pipeline README and the
`native_transport` case file were updated to match.

**There is one rejection file: `stage3-ai-deep-read/rejected.md`, and it is
authoritative for every rejection in this folder.** The split by judging
stage ended on 2026-09-24, when the stage-2 `negatives.md` was deleted —
stage 2 had stopped rejecting rows on 2026-09-23, so the file could only ever
shrink in relevance, and the 108 rows in it now carry band D in `bands.csv`.
Its detail is in git history at `43a3c27` if a later pass wants the
per-helper arguments. Check `stage3-ai-deep-read/_INDEX.md` before adding a
row.

Remaining items, in the order they were previously prioritized:

1. **Verify the 4 pending cases** — *deferred (2026-09-22, see above); not
   currently being worked.* Each case's designed trigger stays recorded in
   the status table above, ready to run when verification resumes.
2. **Continue the CodeQL-assisted triage** — carried out as the two-stage
   pipeline in Priority 1 above, restricted to pattern (a).
   - *Pipeline:* `codeql-queries/` (own [README](codeql-queries/README.md);
     queries under `codeql-queries/cassandra/queries/if-check-exp/`, own
     [README](codeql-queries/cassandra/queries/if-check-exp/README.md))
     narrows ~17k `if` statements: `AllIfStatements.ql` →
     `ComparisonIfStatements.ql` (~10,147 rows) → `NarrowedIfStatements.ql`
     (null, literal-only and non-numeric comparisons dropped; ~4,490 rows).
     This is stage 1; its output belongs in
     the gitignored `codeql-queries/results/cassandra/`. There is
     deliberately no fixed keyword list. Stage 2 ranks these rows from the
     rows themselves; whether one *qualifies* is decided later, by reading
     the source in stage 3.
   - *Progress:* 329 of 4,489 `NarrowedIfStatements` rows triaged
     (`concurrent`, `cache`, `transport`, `db/compaction` — each a subtree).
     Refreshed counts, including the second input file, are in
     `stage2-ai-preprocessing/README.md`. **Remaining: 5,145 rows (4,160
     narrowed + 985
     helper), of which 2,941 are magnitude-class** — the realistic first
     pass, equality being a lower-priority sweep. Largest: `db` (529
     magnitude), `utils` (476), `index` (343), `io` (329), `service` (309).
     **First stage-2 batch run 2026-09-22:** the 114 helper rows inside the
     four already-done subtrees, which predated
     `HelperGuardedIfStatements.ql`. 23 distinct helpers judged (the
     judge-the-helper-once trick held: 114 rows, 23 decisions); 21 rejected,
     1 cited to an existing entry, **1 candidate found** —
     `Directories.hasDiskSpaceForCompactionsAndStreams():551`, a per-filestore
     disk check gating whether a compaction starts at all. It is pattern (b),
     so it is parked in `stage3-ai-deep-read/deferred.md` rather than
     written up.
   - *Known gap (deferred, not blocking):* the pipeline only sees comparisons
     inside `if` conditions, so it cannot find pattern-(b)/(c) checks written
     as ternaries or assignments (the CDC comparison was missed). Under the
     pattern-(a)-only scope this is exactly the right input, so the three
     planned structural queries (comparisons anywhere, guard clauses, verdict
     links; none written yet) wait until (b)/(c) resume.
3. **Native-transport follow-up:** `PreV5Handlers.LegacyDispatchHandler.checkLimits()`
   (`PreV5Handlers.java:197-209`, pre-protocol-V5 connections, uses
   `channelPayloadBytesInFlight`) may be a related but distinct capacity path;
   not yet investigated. `ConnectionLimitHandler` (connection-count caps) is
   deferred rather than rejected; see `stage3-ai-deep-read/_INDEX.md`.
### Deferred until pattern (a) is finished

Parked by the 2026-09-22 scope decision above; all still in scope, none
abandoned. **The worklist itself lives in
[`cassandra/if-check-exp/stage3-ai-deep-read/deferred.md`](cassandra/if-check-exp/stage3-ai-deep-read/deferred.md)**
— full detail there; this is the summary.

- ~~**The disk candidate** `getWriteDirectory():282`~~ — **done 2026-09-22**,
  processed via stage-3 feed 3b as a deliberate single-candidate exception to the
  pattern-(a) scope (feed 3b needs neither the stage-1 CSV nor the unwritten
  (b)/(c) queries). Filed as
  [`cassandra/if-check-exp/stage3-ai-deep-read/cases/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`](cassandra/if-check-exp/stage3-ai-deep-read/cases/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md).
  **Headline finding: the guard does *not* dominate the allocation.** Its only
  caller consults it solely when the table has no disk boundaries; on the
  default path (`Murmur3Partitioner`, node owning ranges) the `SSTableWriter`
  is created with no disk-space check at all — a stronger default-mode gap
  than the memtable `markBlocking()` or native-transport
  `throw_on_overload=false` hatches, since the check is never executed rather
  than overridden. Flagged for Target 3. Two lessons carried into
  `stage3-ai-deep-read/deferred.md` for the eventual (c) pass: non-domination
  is a
  finding to record rather than grounds for rejection, and it cannot be seen
  in a CSV row — it requires reading the callers.
- **The three planned structural CodeQL queries** — comparisons anywhere,
  guard clauses, verdict links (specified in the CodeQL README). They exist
  only to surface (b)/(c) candidates, so they are not needed for the
  pattern-(a) pass.
- **The 2026-09-20 re-audit** of rows and earlier rejections judged only on
  "the `if`'s own branches don't diverge". These are `deferred-(b)/(c)`, not
  rejected; recording them as such in `deferred.md` is what makes this
  resumable as a filter rather than a re-scan.

Already explored, no case retained: the whole `db/compaction/` subpackage
(the `concurrent_compactors` check fails Rule 2; the rest is selection logic,
writer rollover, or config validation), `concurrent/` executors (thread-pool
concurrency), and `cache/`. All are logged in `cassandra/if-check-exp/stage3-ai-deep-read/_INDEX.md`'s
rejected table so they aren't re-scanned. The filter rules themselves are in
`cassandra/if-check-exp/README.md` §3.4–§3.6.
