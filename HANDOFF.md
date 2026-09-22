# If-Check Exp — Handoff

For a new session (Claude Code, Cowork, or otherwise) picking up
`if-check-exp` work. Read this first, then
[`cassandra/if-check-exp/README.md`](cassandra/if-check-exp/README.md) for
the full format spec. This file is kept in sync with the Cowork
"Throttling" project's handoff doc (`claude/if-check-exp-handoff.md`) so a
local Claude Code session — which can't read that project's knowledge base
directly — has the same context available on disk.

This handoff currently covers `if-check-exp` specifically, since that's
the repo's active experiment; it lives at the repo root (rather than under
`cassandra/if-check-exp/`) so a new session finds it immediately. If other
experiment folders grow their own handoff needs later, split this back out
per-folder rather than overloading one file.

## What this experiment is

Part of the **Throttling** research project (Target 1: identify resource
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
repo — when setting up verification infrastructure for this folder, assume
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
  - `README.md` — full format spec: scope, required fields, naming rules,
    workflow, how to verify/link against the local Cassandra source, **and
    a "Verifying a case (triggering the disallow branch)" methodology**
    covering: don't assume the disallow branch cleanly rejects anything
    (trace its real effect first); prefer a deterministic single-shot
    trigger over a throughput race; check whether the limit is global or
    scoped before designing the experiment; prefer a unit/programmatic-
    level trigger over live-cluster where one is feasible; capture direct
    evidence (assertion, metric, thread dump), not an ambiguous symptom
    like a hang.
  - `_INDEX.md` — master table of all cases, coverage summary, and a
    "lines considered and rejected" table (check before re-examining a
    line).
  - `_TEMPLATE.md` — template for a new case file; its Verification section
    has `Trigger method` / `Evidence` fields alongside `Status`, and links
    to the README methodology above.
  - `<module>/` — one folder per (loosely, broadly-named) Cassandra module;
    invent a new one freely when a case doesn't fit — no fixed taxonomy.
  - `candidates/` — **the AI-filtering-results folder** (stage 2 of the
    CodeQL + AI preprocessing pipeline; see Open items Priority 1). Stage 1's
    mechanical output is *not* kept here — it stays gitignored under
    `codeql-queries/results/cassandra/`. Planned layout:
    - `candidates/README.md` — what stage 2 is, how a row is triaged, and the
      batch-coverage table (which subpackages have been read).
    - `candidates/positives.md` — surviving candidates, pending promotion to
      a full case file under a `<module>/` folder.
    - `candidates/negatives.md` — rows read and refused, each citing the rule
      it failed.
    - `candidates/deferred.md` — rows left unjudged: those that would qualify
      only under pattern (b) or (c), parked by the scope decision below.
      Kept apart from `negatives.md` because they are undecided, not refused.
    - `candidates/stage2-playbook.md` — **start here to run a batch.** Stage
      1's results, the priority tiers (P1 11 rows / P2 527 / P3 the rest /
      P4 the 1,463 fast-rejected), the verified side-agnostic reject rules,
      and the tricks and pitfalls from the cases filed so far.
- **`codeql-queries/`** (repo root, [README](codeql-queries/README.md)) — the
  CodeQL query packs that feed `candidates/`; the if-check queries and their
  [pipeline README](codeql-queries/cassandra/queries/if-check-exp/README.md)
  are under `codeql-queries/cassandra/queries/if-check-exp/`. Results land in
  the gitignored `codeql-queries/results/` and must be regenerated on a new
  machine.
- **Outside this repo (CloudLab shared mount, see root `README.md` §2):**
  `git-repos/cassandra-src`, `tools/codeql/`, `codeql-dbs/`.

## Cassandra source for verification

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

## Current state — 7 cases: 2 `verified`, 5 `pending`

**Verification is deferred by decision (2026-09-22)**, so `pending` here means
"filed, citations checked, behavioral trigger not run" — not dropped work.
Each pending case's designed trigger is recorded in its own §9 and in the
table below.

| Case (file under `cassandra/if-check-exp/`) | Pattern | Status | Key finding | Next step |
|---|---|---|---|---|
| `memtable/memtable_heap_space-tryAllocate-limit.md` | (b) | verified | Disallow parks the caller; a `markBlocking()` op overshoots the limit (escape hatch). | none |
| `memtable/memtable_offheap_space-tryAllocate-limit.md` | (b) | verified | Same check on the `offHeap` `SubPool`; same escape hatch. | optional: purpose-built timeout test (see Open items) |
| `net/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md` | (b) | pending | Per-connection byte cap (default 4MiB); disallow registers on a wait queue, message not dropped; no escape hatch found yet. | design a unit trigger: `InboundMessageHandler` with tiny `queueCapacity` and exhausted reserves, feed one oversized frame; check `test/unit/.../net/` for scaffolding first |
| `net/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md` | (b) | pending | Same check via `CQLMessageHandler` (default 1MiB). With the default `native_transport_throw_on_overload=false` the message is still decoded; only `throwOnOverload=true` rejects. | two triggers: `throwOnOverload=true` (expect `OverloadedException`, no decode) and `false` (expect decode despite over-limit) |
| `hints/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md` | (a) | pending | JVM property cap (default 3) on off-heap `HintsBuffer`s; disallow blocks on `reserveBuffers.take()`; no escape hatch found. | run existing `HintsBufferPoolTest.testBackpressure()` via `ant testsome -Dtest.name=org.apache.cassandra.hints.HintsBufferPoolTest`; confirm Byteman resolves as a test dependency |
| `commitlog/cdc_total_space-processNewSegment-allowance.md` | (b) | pending | Byte cap on un-consumed CDC segments; `processNewSegment():335` sets a `CDCState`, `throwIfForbidden():214` throws `CDCWriteException` (clean reject). Escape hatch: `cdc_block_writes=false`. | run `CommitLogSegmentManagerCDCTest` via `ant testsome`; find which `@Test` isolates the `cdc_total_space` boundary vs. the `cdc_block_writes` tests |
| `compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md` | (c) | pending | Disk guard: refuses a compaction whose estimated output exceeds the target directory's free space (device bytes − `min_free_space_per_drive`, default 50MiB). **The guard does not dominate the allocation** — on the default `diskBoundaries != null` path the `SSTableWriter` is created with no space check at all. | verification deferred; when resumed the trigger must force `diskBoundaries == null` (a partitioner with no splitter), else the guard never executes |

Details for the two verified cases follow. The pending cases' details live in
their case files.

- **`cassandra/if-check-exp/memtable/memtable_heap_space-tryAllocate-limit.md`** — on-heap path. If-check:
  [`MemtablePool.SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156),
  gating `ByteBuffer.allocate(size)` via `HeapPool.Allocator.allocate()`.
  Limit traced from `Config.java`'s `memtable_heap_space` through to
  `SubPool.limit`. **Status: `verified` — the primary trigger has been run
  and recorded.**
  - **Primary trigger (executed 2026-09-16):** the new unit test
    `test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java` (full
    source in the case file's Verification section) was saved into the
    shared `cassandra-src` clone at
    `/proj/misconfiguration-PG0/git-repos/cassandra-src` and run on
    CloudLab node pc80 via
    `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.HeapPoolTest`.
    JDK 11 (11.0.32) and `ant` (1.10.12) were installed on pc80 for this
    (previously absent, checked 2026-09-15) — **still not installed on the
    other cluster nodes**, install per-node if verification work moves
    there. Result: `BUILD SUCCESSFUL`, `Tests run: 2, Failures: 0, Errors: 0`.
    Both `@Test` methods passed, proving (1) the disallow branch parks the
    calling thread on `SubPool.hasRoom` until released, and (2) a
    `markBlocking()`-marked op instead silently overshoots the limit
    (escape-hatch behavior — flagged for Target 3, not pursued here). Full
    evidence recorded in the case file's Verification table and pushed to
    `origin/main` (commit `e878607`).
  - **Secondary trigger (optional, not run):** live-cluster confirmation,
    documented in the case file as this experiment's own independent
    setup — skipped since the unit test already provides direct evidence
    for both branches; would only be a reasonable next step if end-to-end
    (real daemon) confirmation becomes valuable later.
- **`cassandra/if-check-exp/memtable/memtable_offheap_space-tryAllocate-limit.md`** — off-heap sibling case.
  Same if-check, `offHeap` `SubPool` instance instead of `onHeap`, reached
  via `NativePool`/`NativeAllocator` instead of `HeapPool`; limit is
  `memtable_offheap_space`. Object created is a `NativeAllocator.Region`
  (native memory via `MemoryUtil.allocate()`), not a `ByteBuffer`.
  **Status: `verified` — the primary trigger has been run and recorded.**
  - **Primary trigger (executed 2026-09-16):** the existing unit test
    `test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java`
    (no new harness needed — `testBookKeeping()` already exercises this exact
    if-check both ways) was run against the `cassandra-src` clone at
    `/proj/misconfiguration-PG0/git-repos/cassandra-src` via
    `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NativeAllocatorTest`
    on this session's node (JDK 11.0.32, Ant 1.10.12 — already present, no
    provisioning needed). Result: `BUILD SUCCESSFUL`, `Tests run: 1,
    Failures: 0, Errors: 0`. The test's own assertions
    (`verifyUsedReclaiming(80, 0)` then `verifyUsedReclaiming(110, 110)`)
    directly demonstrate both disallow-branch outcomes at
    `MemtablePool.java:156` on the `offHeap` `SubPool`: accounting capped at
    the 100-byte limit, then forced through to 110 once `markBlocking()`
    fires — the same escape-hatch behavior as the heap case. Full evidence
    recorded in the case file's Verification table and pushed to
    `origin/main` (commit `0198e25`).
    **Caveat vs. the heap case's evidence:** `testBookKeeping()` is a
    pre-existing test reused as-is, not purpose-built like `HeapPoolTest`.
    It proves the escape-hatch outcome cleanly (110 > limit 100 is only
    reachable via the disallow branch), but — unlike `HeapPoolTest`'s
    explicit timed `Future.get()` — it never isolates a proof that the
    "normal case" call actually *parked* before being released; it only
    confirms the correct numeric end-state. Equal outcome, not equal
    verification rigor. A `HeapPoolTest`-style purpose-built test (two
    isolated `@Test`s, explicit timeout-based blocking proof) would close
    this gap if stronger evidence is wanted later — not done, per Jingsong's
    call to skip it for now.
  - **Secondary trigger (optional, not run):** live-cluster confirmation,
    same rationale as the heap case — skipped since the unit test already
    gives direct evidence for both branches.
- **Shared discovery (both cases):** the if-check's disallow branch does
  **not** reject or fail the caller. `MemtableAllocator.SubAllocator.allocate()`
  (`MemtableAllocator.java:169-197`) either parks the caller on
  `SubPool.hasRoom` until something releases memory, or — if the caller's
  `OpOrder.Group` is already marked "blocking" (done for in-flight writes a
  flush barrier must wait out, `ColumnFamilyStore.java:1238`) — silently
  forces the allocation through past `limit` instead. This is documented in
  both case files' §5 and flagged as a Target-3 bypass candidate, not
  pursued further under Target 1+2.

## Key rules (summary; full text in `cassandra/if-check-exp/README.md`)

- **Three locations per case** (README §3.1): capacity check (usage-vs-limit
  comparison), decision point (where allow and disallow diverge), allocation
  site (where the memory- or disk-significant object is created).
- **Enforcement patterns** (§3.2), recorded per case: **(a)** the check is
  itself the decision (hints case); **(b)** the check sets a verdict — flag,
  enum, or return value — read by a separate decision point (memtable ×2,
  internode, native transport, CDC; CDC sets a per-segment `CDCState` in
  `processNewSegment():335` and reads it in `throwIfForbidden():214`);
  **(c)** guard clauses `throw`/`return` before an allocation outside any
  branch (the disk candidate `getWriteDirectory():282`).
- **Rules** (§3.4–§3.6): a capacity check against a limit-side operand; the
  limit bounds total memory or disk bytes of the gated allocation (thread-pool
  sizes, rate limiters, time checks and writer rollover don't qualify); the
  verdict must reach a decision point whose outcome differs for object
  creation.
- **Scope** (§1, §3.3, §4): memory and disk (disk added 2026-09-18); every
  case covers Target 1 and Target 2 together; no cross-referencing other
  experiments; no bypass analysis.
- **Naming** (§6.1, changed 2026-09-21): `[constraint]-[function]-[operand].md`
  (follows the data flow: limit source → checking function → operand), anchored
  on the capacity check. On a name collision the existing file is **not**
  renamed; only the newcomer gets a `-2` (then `-3`, ...) postfix. The object
  created lives only in `_INDEX.md`'s Object column and each case's §7.
- **Discovery** (§7.2): CodeQL only shrinks the search space; qualification
  is decided by reading each row, with no fixed keyword list.

## Open items / next steps

### Two discovery methods (recorded 2026-09-22)

Both feed the same case files and answer to the same three rules
(README §3.4–§3.6); they are complementary, not alternatives. Full write-up
in `cassandra/if-check-exp/README.md` §7.2.

1. **Direct AI search.** An AI session reads the Cassandra source directly,
   following subsystems and call chains, and identifies real if-check cases
   end to end with no mechanical pre-filter. This is how last week's cases
   were found. *Strength:* follows semantics a structural query cannot
   express — it found the `cdc_total_space` ternary that the CodeQL pipeline
   structurally cannot surface. *Weakness:* the source is far larger than one
   session can read, so coverage is opportunistic rather than systematic, and
   it puts a heavy burden on the reading session. That burden is the reason
   for method 2.
2. **CodeQL + AI preprocessing.** Stage 1 (CodeQL) narrows ~17k `if`
   statements structurally; stage 2 (AI) then works **from the rows alone**,
   without opening the source — ruling out what a row visibly cannot be and
   **ranking** the rest into priority tiers. Neither stage applies the three
   rules: those qualify a real case and need the code, so they belong to
   method 1's deep read, which takes `positives.md` in tier order. The point
   of method 2 is to cheaply *narrow and order* the corpus, so method 1's
   expensive per-case reading is spent on the most promising rows first.

**Rejections stay separated by method, in `_INDEX.md` and
`candidates/negatives.md` respectively** (decided 2026-09-22). They differ in
kind: method 1's are few, narrative, and often deferred-rather-than-refused
(e.g. `ConnectionLimitHandler`); method 2's are bulk, per-batch, one line
each citing the rule failed. Keeping `_INDEX.md` for method 1 also stops it
absorbing thousands of triage rows. **One line is recorded in exactly one of
the two** — if stage 2 reaches a line method 1 already judged, cite the
`_INDEX.md` entry instead of re-recording it (`db/compaction/` rows were
triaged both ways and would otherwise duplicate).

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
   and record everything under `cassandra/if-check-exp/candidates/` — that
   folder *is* the AI-filtering-results store. Ranked survivors go to
   `positives.md` (with a tier), row-level rejects to `negatives.md`,
   pattern-(b)/(c)-only rows to `deferred.md`.

   **Stage 2 does *not* apply the three rules** (README §3.4–§3.6). Those
   qualify a real case and need the code — Rule 3 asks whether the branches
   diverge on object creation, which no row can answer. They belong to the
   deep-read pass (method 1), which takes `positives.md` in tier order and
   promotes what qualifies into case files.

   **Because stage 2 is blind, it should rank far more than it rejects.** A
   wrong rejection is permanent and invisible; a wrong promotion costs a
   little reading. Verified tiers and reject rules are in
   `candidates/stage2-playbook.md`.

### Next step (decided 2026-09-22): run P1 tier-first

**The immediate next task is the P1 tier — 34 rows, corpus-wide.** Stage 2's
ranking (see `candidates/stage2-playbook.md`) puts a row in P1 when a
capacity word appears on either side of the comparison *and* the usage side
is a compound expression — the `current + requested vs limit` shape.

Tier-first rather than batch-first, deliberately:

- **Fastest route to new cases.** P1 already contains two known cases
  (`MemtablePool.tryAllocate():156`, `AbstractMessageHandler.acquireCapacity():419`)
  as free calibration, one known rejection to cite rather than re-judge
  (`HintsBuffer.allocateBytes():190`), and several strong unknowns —
  `BufferPool$GlobalPool.allocateMoreChunks():443` (`> memoryUsageThreshold`),
  `ResourceLimits$Basic.tryAllocate():213`, `NativeAllocator$Region.allocate():273`
  and `SlabAllocator$Region.allocate():201` (both `> capacity`),
  `MmappedRegions.updateState():208` (`> MAX_SEGMENT_SIZE`).
- **It tests the ranking cheaply.** The tiers are currently validated against
  only four labelled positives. Running P1 checks them on a real sample
  *before* ~5,000 remaining rows get ordered by them. If P1 yields two or
  three real cases the tiering is justified and P2 (371 rows) follows; if it
  yields nothing new, better to learn that now and fall back to completing
  packages batch by batch.

**Caveat to record when it runs:** P1's rows are scattered across ~15
packages, so it completes no package. Log it as its own coverage entry rather
than marking any package done.

Note P1 is a *deep-read* task — it applies the three rules with the source
open. Stage 2's own remaining work (ranking the rest of the corpus) is
separate and can proceed independently.

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

- **Already-filed cases are unaffected.** Four of the six existing cases are
  pattern (b), two of them already `verified`. This decision governs *new
  candidate triage* only — verifying the filed pending cases (item 1 below)
  continues regardless of their pattern.
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
  deep-read pass** — not by stage 1, and not by stage 2 either, since neither
  sees the branches.
**Verification is deferred too (2026-09-22).** The README §8 "trigger the
disallow branch" step is not being run for now — the focus is discovery.
Cases are filed with their citations checked against the pinned tag and left
at `Status: pending`; §8 stands unchanged as the methodology for when
verification resumes. This supersedes item 1 below as the top call on time,
though the four pending cases' designed triggers remain recorded and ready.

- **Deferred with (b)/(c):** the disk candidate `getWriteDirectory():282`
  (pattern (c) — previously item 2 below), the three planned structural
  CodeQL queries (comparisons anywhere, guard clauses, verdict links — they
  exist only to surface (b)/(c)), and the 2026-09-20 re-audit of earlier
  rejections under (b)/(c). All three are listed under "Deferred until
  pattern (a) is finished" below.

### `candidates/` layout (applied 2026-09-22)

`candidates.md` was folded into `candidates/README.md` (which keeps the
batch-coverage table and the judging procedure) and the rest split into
`positives.md`, `negatives.md` and `deferred.md`, so each file has one job.
References in `_INDEX.md`, the codeql pipeline README and the
`native_transport` case file were updated to match.

`_INDEX.md` keeps its own rejection section for method-1 findings (see "Two
discovery methods" above) — the two sets are not merged. **Stage-2
rejections made before 2026-09-22 also remain in `_INDEX.md`**, since this
file did not exist when they were recorded and migrating them would churn
several cross-references for no analytical gain. So: `_INDEX.md` is
authoritative for every rejection up to 2026-09-22, `negatives.md` for
stage-2 rejections after it. Check `_INDEX.md` before adding a row.

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
     the source in the deep-read pass.
   - *Progress:* 329 of 4,489 `NarrowedIfStatements` rows triaged
     (`concurrent`, `cache`, `transport`, `db/compaction` — each a subtree).
     Refreshed counts, including the second input file, are in
     `candidates/README.md`. **Remaining: 5,145 rows (4,160 narrowed + 985
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
     so it is parked in `candidates/deferred.md` rather than written up.
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
   deferred rather than rejected; see `_INDEX.md`.
4. **Optional rigor gap (off-heap memtable case):** its evidence reuses
   `NativeAllocatorTest.testBookKeeping()`, which proves the escape-hatch
   outcome but not, as `HeapPoolTest` does, that the normal call actually
   parked. A purpose-built test would close this; not prioritized.

### Deferred until pattern (a) is finished

Parked by the 2026-09-22 scope decision above; all still in scope, none
abandoned. **The worklist itself lives in
[`cassandra/if-check-exp/candidates/deferred.md`](cassandra/if-check-exp/candidates/deferred.md)**
— full detail there; this is the summary.

- ~~**The disk candidate** `getWriteDirectory():282`~~ — **done 2026-09-22**,
  processed with method 1 as a deliberate single-candidate exception to the
  pattern-(a) scope (method 1 needs neither the stage-1 CSV nor the unwritten
  (b)/(c) queries). Filed as
  [`cassandra/if-check-exp/compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`](cassandra/if-check-exp/compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md).
  **Headline finding: the guard does *not* dominate the allocation.** Its only
  caller consults it solely when the table has no disk boundaries; on the
  default path (`Murmur3Partitioner`, node owning ranges) the `SSTableWriter`
  is created with no disk-space check at all — a stronger default-mode gap
  than the memtable `markBlocking()` or native-transport
  `throw_on_overload=false` hatches, since the check is never executed rather
  than overridden. Flagged for Target 3. Two lessons carried into
  `candidates/deferred.md` for the eventual (c) pass: non-domination is a
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
concurrency), and `cache/`. All are logged in `cassandra/if-check-exp/_INDEX.md`'s
rejected table so they aren't re-scanned. The filter rules themselves are in
`cassandra/if-check-exp/README.md` §3.4–§3.6.
