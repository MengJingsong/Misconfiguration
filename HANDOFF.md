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

  - `<module>/` — one folder per (loosely, broadly-named) Cassandra module;
    invent a new one freely when a case doesn't fit — no fixed taxonomy.
  - **`stage1-codeql-preprocessing/`** — stage-1 entry point. Holds no
    queries and no results, only pointers: the queries live at the repo root
    under `codeql-queries/`, the CSVs are gitignored. Also records stage 1's
    output counts and its structural blind spot.
  - **`stage2-ai-preprocessing/`** — stage-2 verdicts (lexical, rows only).
    - `README.md` — what stage 2 is, how a row is triaged, the
      "Progress at a glance" dashboard, and the batch-coverage table.
    - `playbook.md` — **start here to run a batch.** Stage 1's results, the
      priority tiers (**work-ahead scope**: P1 34 / P2 371 incl. P1 / P3 746
      / P4 1,337 fast-rejected — see that file's scope table before quoting
      any of them), the verified side-agnostic reject rules, and the tricks
      and pitfalls learned so far.
    - `positives.md` — ranked survivors; this is stage 3's 3a queue.
    - `negatives.md` — refused from the row alone, source unread.
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
**There is no `Status` field** — behavioral verification was removed from
this folder's scope on 2026-09-23 (see "Scope decisions"), so a filed case is
finished work. `Feed` records which stage-3 feed found it (`3a` = via
stage 1/2, `3b` = direct source reading).

| Case (file under `cassandra/if-check-exp/`) | Pattern | Feed | Key finding |
|---|---|---|---|
| `memtable/memtable_heap_space-tryAllocate-limit.md` | (b) | 3b | Disallow parks the caller; a `markBlocking()` op overshoots the limit (escape hatch). |
| `memtable/memtable_offheap_space-tryAllocate-limit.md` | (b) | 3b | Same check on the `offHeap` `SubPool`; same escape hatch. |
| `net/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md` | (b) | 3b | Per-connection byte cap (default 4MiB); disallow registers on a wait queue, message not dropped; no escape hatch found. |
| `net/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md` | (b) | 3b | Same check via `CQLMessageHandler` (default 1MiB). With the default `native_transport_throw_on_overload=false` the message is still decoded; only `throwOnOverload=true` rejects. |
| `hints/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md` | (a) | 3b | JVM property cap (default 3) on off-heap `HintsBuffer`s; disallow blocks on `reserveBuffers.take()`; no escape hatch found. |
| `commitlog/cdc_total_space-processNewSegment-allowance.md` | (b) | 3b | Byte cap on un-consumed CDC segments; `processNewSegment():335` sets a `CDCState`, `throwIfForbidden():214` throws `CDCWriteException` (clean reject). Escape hatch: `cdc_block_writes=false`. |
| `compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md` | (c) | 3b | Disk guard on compaction output vs. free space. **The guard does not dominate the allocation** — on the default `diskBoundaries != null` path the `SSTableWriter` is created with no space check at all. |

Each case's full detail lives in its own file.

## Open items / next steps

### ⏵ Resume here (state as of 2026-09-22, end of session)

**Where the pipeline stands.** Stages 1 and 2 are built and running. Stage 1 is
complete for pattern (a) — four CodeQL queries, two CSVs. Stage 2 has ranked
the magnitude corpus into tiers and the **P1 tier has been deep-read**. Seven
Seven cases are filed, all stage-3 complete.

| Stage-1 corpus | Rows | magnitude | equality |
|---|---|---|---|
| `NarrowedIfStatements.csv` | 4,489 | 2,681 | 1,808 |
| `HelperGuardedIfStatements.csv` | 1,099 | 577 | 522 |
| **Total** | **5,588** | **3,258** | **2,330** |

| Stage-2 progress | Narrowed | Helper | Total |
|---|---|---|---|
| Processed (4 subtrees + P1 tier, overlapping) | 329 | 114 | done |
| Remaining — magnitude (the real queue) | 2,454 | 487 | **2,941** |
| Remaining — equality (low-priority sweep) | 1,706 | 498 | 2,204 |
| **Remaining total** | **4,160** | **985** | **5,145** |

Tiers over the 2,454 remaining narrowed-magnitude rows (*work-ahead scope*):
**P1 34 ✅ done / P2 371 incl. P1 / P3 746 / P4 1,337 fast-rejected.** The
canonical, scope-labelled version of every number here lives in
`stage2-ai-preprocessing/README.md`'s "Progress at a glance" and
`stage2-ai-preprocessing/playbook.md`'s scope table — update those first.

**The immediate next work, in order:**

1. **The lexical stage-2 pass — Jingsong's plan, to be done next.** In his
   words:

   > *"In stage 2, can we use AI to scan the operand's name or any text from
   > stage 1 results and extract valid/invalid candidates by their lexical
   > meanings?"*

   Yes — and it replaces the fixed capacity-word list the current tiers are
   built on. Full rationale, evidence and the working design are in
   `stage2-ai-preprocessing/playbook.md` ("Lexical judgement") and
   summarised below. **Do this before P2**, because P2's membership is defined by the
   keyword list this pass supersedes; re-ranking first means P2 is read in a
   trustworthy order rather than re-read later.
2. **Write up the 4 P1 candidates as case files.** They are found, judged
   against the three rules, and recorded in
   `stage2-ai-preprocessing/positives.md`, but none exists as a case file yet.
   Independent of step 1, so it can be done in either order. Start with `BufferPool_memoryUsageThreshold` (strongest);
   its main open task is tracing `memoryUsageThreshold` to its config source
   for the §6.1 constraint name. `TeeDataInputPlus_limit` is the weakest —
   confirm `limit`'s origin before committing to it. `Integer_MAX_VALUE`
   needs a §6.1 naming judgement call, since the constraint is a *type
   bound*.
3. **Two corrections to existing case files**, both found by the P1 pass and
   detailed in the "P1 tier" section below: `cdc_total_space` is missing a
   second check site (`permitSegmentMaybe():200`), and the two net cases
   should link `ResourceLimits$Basic.tryAllocate():213` as the mechanism
   behind their reserve sub-checks.
4. **Then run the P2 tier (371 rows, or its re-ranked equivalent after step
   1)**, continuing tier-first rather than package-first. P1 gave roughly a
   1-in-3 hit rate on rows not already accounted for, which is why tier order
   is worth keeping.

**Do not** start patterns (b)/(c), and do not run behavioral verification —
both are deferred by decision (see "Scope decisions" below). `deferred.md`
is their worklist.

### ⏵ Step 1 in detail — the lexical stage-2 pass (planned 2026-09-22)

**Stage 2's ranking moves from keyword matching to AI lexical judgement of
the row.** Decided by Jingsong 2026-09-22 as the next step; the design below
is settled in shape, and only the mechanics are open.

The current tiers key off a fixed capacity-word list, and that list fails in
both directions. False positives: `phi_convict_threshold > 16`,
`repair_session_max_tree_depth > 20`, `memtable_cleanup_threshold > 0.99f`,
`default_keyspace_rf < ..._fail_threshold` — all contain `threshold`/`max`,
none bounds bytes, and all sit in `applySimpleConfig`, i.e. startup
validation. False negatives: capacity-shaped vocabulary the list never
anticipated (`remaining()`, `keysWritten >= keysEstimate`, `unused`).

This is what README §7.2's "deliberately no fixed keyword list" rule is
guarding against, so lexical judgement is the more faithful method — it is
what the rule always implied stage 2 should be doing. How it works:

- Judge the row as a sentence — `declaringType` + `method` + `lhs op rhs`.
  Context usually decides before the operand does; anything in
  `applySimpleConfig`/`validate*` is validation whatever it compares.
- Layer it *after* the mechanical fast-reject (bare literal, `compareTo`),
  which is free, deterministic and reproducible.
- Emit a one-line reason per row, not just a label, so the pass is auditable
  and does not drift across sessions.
- Reject only lexical certainties; downrank anything ambiguous. `remaining()
  < 4` looks capacity-shaped and is really a deserialization bounds check —
  stage 2 cannot know that, so it ranks low rather than refusing.
- Record model and date per batch; these judgements are model-dependent in a
  way CodeQL output is not. Regression-check each batch against the known
  rows, and re-judge ~10 rows from the previous batch for consistency.

**The limit that remains either way:** lexical meaning cannot settle the
three rules. Stage 2 improves ranking and removes the obvious; qualification
stays with the deep read.


### Two discovery methods (recorded 2026-09-22)

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
| **2** | lexical — operand, class, method and package *names* | **no** | no | `stage2-ai-preprocessing/` |
| **3** | semantic — the code itself, against the three rules | yes | **yes** | `stage3-ai-deep-read/` |

**Stage 3 is the only stage that decides.** Stages 1 and 2 produce no
findings — they shrink and order what stage 3 must read.

**Stage 3 has two feeds, and both are required:**

- **3a — from stage 1/2.** Takes `positives.md` in tier order. Bounded and
  enumerable, so progress is measurable.
- **3b — from raw source.** The session reads subsystems and call chains
  directly. Unbounded, so there is no denominator and no percentage to
  report. **Not optional:** it is the standing insurance against stage 1's
  structural blind spot — it found the `cdc_total_space` ternary, which
  stage 1 cannot surface at any tier because it is not an `if` condition.

Record the feed (`3a`/`3b`) on every case and verdict.

**Verdicts are filed by the stage that judged them, not the stage that
surfaced the row** (revised 2026-09-23). A row stage 2 ranked and stage 3
then read and refused is a *stage-3* rejection.

| | Stage 2 verdict | Stage 3 verdict |
|---|---|---|
| Rejected | `stage2-ai-preprocessing/negatives.md` | `stage3-ai-deep-read/rejected.md` |
| Deferred | *(cannot defer)* | `stage3-ai-deep-read/deferred.md` |
| Qualified | *(cannot qualify)* | a case file under `<module>/`, indexed in `stage3-ai-deep-read/_INDEX.md` |

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
   class — **without reading the Cassandra source**. Rule out rows the row
   itself shows are not capacity checks, rank the rest into priority tiers,
   and record everything under `cassandra/if-check-exp/stage2-ai-preprocessing/`
   — that
   folder *is* the AI-filtering-results store. Ranked survivors go to
   `positives.md` (with a tier), row-level rejects to `negatives.md`,
   pattern-(b)/(c)-only rows to `deferred.md`.

   **Stage 2 does *not* apply the three rules** (README §3.4–§3.6). Those
   qualify a real case and need the code — Rule 3 asks whether the branches
   diverge on object creation, which no row can answer. They belong to the
   stage-3 pass, which takes `positives.md` in tier order and
   promotes what qualifies into case files.

   **Because stage 2 is blind, it should rank far more than it rejects.** A
   wrong rejection is permanent and invisible; a wrong promotion costs a
   little reading. Verified tiers and reject rules are in
   `stage2-ai-preprocessing/playbook.md`.

### P1 tier — run 2026-09-22, done

All 34 P1 rows deep-read against the three rules. Outcome: **4 new
candidates, 22 rejected, 3 deferred as pattern (b)/(c), 5 already covered.**
Details in `stage2-ai-preprocessing/positives.md`, `negatives.md`, `deferred.md`.

**The ranking validated.** P1 recovered both known filed cases as calibration
and yielded 4 new candidates plus 1 strong pattern-(b) find — about a
1-in-3 hit rate on rows not already accounted for. **Next: P2, 371 rows**,
continuing tier-first.

**The 4 candidates** (none written up yet — this is the immediate next work):

| Candidate | Check |
|---|---|
| `BufferPool_memoryUsageThreshold` | `BufferPool$GlobalPool.allocateMoreChunks():443` — disallow returns `null`, allow does `new Chunk(allocateDirectAligned(MACRO_CHUNK_SIZE))`. Strongest of the four; an explicit off-heap ceiling immediately before the allocation. |
| `MAX_MATERIALIZED_KEYS` | `QueryController.materializeKeysAndCloseSource():449` — disallow discards the accumulated `List<PrimaryKey>` and returns `null`. |
| `Integer_MAX_VALUE` (index summary) | `IndexSummaryBuilder.maybeAddEntry():204` — disallow skips the entry and logs "index summary exceeded (2GiB)". Constraint is a **type bound**, which Target 1 admits but §6.1 naming does not cleanly cover. |
| `TeeDataInputPlus_limit` | `TeeDataInputPlus.maybeWrite():58` — weakest; confirm `limit`'s origin before writing it up. |

**Two open actions on existing cases**, both surfaced by P1:

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

### Scope decisions (2026-09-22): pattern (a) only; verification deferred

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
- **(b)/(c)-only rows go to `deferred.md`, not `negatives.md`.** A row
  dropped only because "the `if`'s own branches don't diverge" is not
  rejected — it is simply unjudged under (b)/(c). A separate file (rather
  than a status column, which invites skimming past it) means resuming
  (b)/(c) later is a matter of reading one file instead of re-scanning the
  corpus. Rejections on pattern-independent grounds (thread-pool or
  concurrency caps, rate limiters, config validation, time checks, writer
  rollover) are true rejections and stay settled in `negatives.md`.
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
**Behavioral verification is out of scope (2026-09-23).** Driving execution
into the disallow branch is no longer part of this folder's workflow, the
README's verification section is gone, and there is no `Status` field. A
case's evidence is its traced code path, checked against the pinned tag —
that is what Target 2 asks for; an executed trigger was always supplementary,
never the deliverable. Earlier trigger designs and results are recoverable
from git history (`git show e7f9963`).

- **Deferred with (b)/(c):** the disk candidate `getWriteDirectory():282`
  (pattern (c) — previously item 2 below), the three planned structural
  CodeQL queries (comparisons anywhere, guard clauses, verdict links — they
  exist only to surface (b)/(c)), and the 2026-09-20 re-audit of earlier
  rejections under (b)/(c). All three are listed under "Deferred until
  pattern (a) is finished" below.

### `stage2-ai-preprocessing/` layout (applied 2026-09-22)

`candidates.md` was folded into `stage2-ai-preprocessing/README.md` (which keeps the
batch-coverage table and the judging procedure) and the rest split into
`positives.md`, `negatives.md` and `deferred.md`, so each file has one job.
References in `stage3-ai-deep-read/_INDEX.md`, the codeql pipeline README and the
`native_transport` case file were updated to match.

`stage3-ai-deep-read/_INDEX.md` keeps its own rejection section for method-1 findings (see "Two
discovery methods" above) — the two sets are not merged. **Stage-2
rejections made before 2026-09-22 also remain in `stage3-ai-deep-read/_INDEX.md`**, since this
file did not exist when they were recorded and migrating them would churn
several cross-references for no analytical gain. So: `stage3-ai-deep-read/_INDEX.md` is
authoritative for every rejection up to 2026-09-22, `negatives.md` for
stage-2 rejections after it. Check `stage3-ai-deep-read/_INDEX.md` before adding a row.

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
  [`cassandra/if-check-exp/compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`](cassandra/if-check-exp/compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md).
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
  rejected; recording them as such in `negatives.md` is what makes this
  resumable as a filter rather than a re-scan.

Already explored, no case retained: the whole `db/compaction/` subpackage
(the `concurrent_compactors` check fails Rule 2; the rest is selection logic,
writer rollover, or config validation), `concurrent/` executors (thread-pool
concurrency), and `cache/`. All are logged in `cassandra/if-check-exp/stage3-ai-deep-read/_INDEX.md`'s
rejected table so they aren't re-scanned. The filter rules themselves are in
`cassandra/if-check-exp/README.md` §3.4–§3.6.
