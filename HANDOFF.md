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

## Where things live

- **Repo:** `MengJingsong/Misconfiguration` on GitHub.
- **Local clone:** kept wherever the current working session's local
  machine keeps it — path and device vary by environment, not fixed
  (Jingsong pushes commits himself — a session only writes local files and
  commits locally when asked; pushing is Jingsong's call).
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

## Cassandra source for verification

- Local clone (separate from the Misconfiguration repo) — path and device
  vary by environment, not fixed.
- Confirmed as tag `cassandra-5.0.9` by content (`build.xml`'s
  `base.version` and `CHANGES.txt`'s top entry both read `5.0.9`).
- **Always grep/read the local clone to verify a line number**, then build
  the GitHub link as `.../blob/cassandra-5.0.9/<path relative to repo
  root>#L<NN>`. Never cite a line from memory or from a GitHub fetch alone.

## Current state — 2 cases `verified`, 3 `pending`

- **`cassandra/if-check-exp/memtable/tryAllocate-limit-memtable_heap_space.md`** — on-heap path. If-check:
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
- **`cassandra/if-check-exp/memtable/tryAllocate-limit-memtable_offheap_space.md`** — off-heap sibling case.
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

## Enforcement patterns (added 2026-09-20)

The first cases assumed the capacity check was an `if` whose own branches
allow or disallow the allocation. The `cdc_total_space` case showed that is
only one of three shapes; every case now records which one it follows (see
`cassandra/if-check-exp/README.md` §3.2):

- **(a)** the capacity check is itself the decision (`hints` case);
- **(b)** the check produces a verdict — a flag, enum, or return value —
  and a separate decision point reads it (memtable ×2, internode, native
  transport, and CDC cases; CDC uses a per-segment `CDCState` set in
  `processNewSegment():335` and read in `throwIfForbidden():214`);
- **(c)** guard clauses that `throw`/`return` before an allocation that is
  not inside a branch (the disk candidate `getWriteDirectory():282`).

Case files now record three locations — capacity check, decision point,
allocation site — and are named after the capacity check
(`[function]-[operand]-[constraint].md`). The CDC case was re-anchored and
renamed on that basis. `NarrowedIfStatements.ql` only keeps comparisons
inside `if` conditions, so it cannot see pattern-(b) checks written as
ternaries or assignments (the CDC comparison was missed); three extra
structural queries are planned (see the CodeQL README) and the triage done so
far needs a re-read for rows rejected only for "non-diverging branches"
(see `cassandra/if-check-exp/candidates/candidates.md`). Both READMEs now
have numbered sections and subsections for easy reference.

## Case file naming policy (changed 2026-09-20)

Case files are now named `[function]-[operand]-[constraint].md` (enclosing
method of the if-statement, limit-side operand as written at the check, and
the resource constraint's first-declared variable on the limit
initialization path — config entry, JVM property variable, constant, or
accessor). Name collisions get a `-n` postfix. The old `[limit]-[object]`
scheme is retired; the object created now lives only in `_INDEX.md`'s
Object column and each case's §7. All 5 existing case files, Case IDs and
cross-links were renamed accordingly. See `cassandra/if-check-exp/README.md`
§ Naming for the full rules.

## Scope change: disk added alongside memory (2026-09-18)

`if-check-exp` was originally memory-only (Rule 2 in
`cassandra/if-check-exp/README.md`). **Disk (on-disk bytes) is now also
in scope**, per Jingsong's call — Rule 2's wording, the required-fields
spec (§7/§8), and `_TEMPLATE.md` were all updated to say "memory or disk"
throughout. A line found during the `db/compaction/` triage batch and
rejected purely for being disk-scoped —
[`CompactionAwareWriter.getWriteDirectory():282`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L282)
(`availableSpace < estimatedWriteSize`, a disk-space check gating whether a
compaction writer starts writing an SSTable) — was reclassified as a live
candidate in `cassandra/if-check-exp/candidates/candidates.md` as a direct
result; not yet written up as a full case file or verified. No other
previously-rejected lines in `_INDEX.md` were disk-related as of this date
(reviewed the existing table when making this change), so this is currently
the only reclassification.

## Open items / natural next steps

- **CodeQL-assisted discovery pipeline in progress (started 2026-09-17):**
  a new `codeql-queries/` folder at the repo root (own
  [README](codeql-queries/README.md)) builds a CodeQL database from the
  `cassandra-src` clone (kept at
  `/proj/misconfiguration-PG0/codeql-dbs/cassandra-db`, CLI at
  `/proj/misconfiguration-PG0/tools/codeql/`) and runs queries under
  `codeql-queries/cassandra/queries/if-check-exp/` (own
  [README](codeql-queries/cassandra/queries/if-check-exp/README.md)) to
  mechanically narrow Cassandra's ~17k `if` statements toward Target-1
  candidates — this supersedes Workflow step 2's manual keyword-grep
  approach below. Pipeline so far: `AllIfStatements.ql` (full inventory) →
  `ComparisonIfStatements.ql` (narrows to `if` conditions built from a
  direct `<`/`<=`/`>`/`>=`/`==`/`!=` comparison, ~10,147 rows) →
  `NarrowedIfStatements.ql` (2026-09-18: drops null comparisons,
  literal-vs-literal comparisons, and non-numeric-typed comparisons —
  keeps only magnitude comparisons; ~4,490 rows). **Deliberately no fixed
  keyword list** — per Jingsong's call, the memory-relatedness judgment
  (Rule 1/Rule 2) is made by reading each row, not by grepping for a
  canned vocabulary, since real cases (`memtable_heap_space`,
  `HintsBufferPool_MAX_ALLOCATED_BUFFERS`) don't share predictable
  vocabulary. Remaining rows still include structural noise mechanical
  filtering can't remove without keyword judgment (e.g. `index == 0`,
  comparator results like `compareIPs() < 0`) — left for the triage pass.
  **Semantic triage started 2026-09-18** (batched by subpackage directory,
  not linearly — see `cassandra/if-check-exp/candidates/candidates.md`'s
  "Batches triaged so far" table for exact coverage and row counts):
  `concurrent/` (17 rows, 0 survivors), `cache/` (15 rows, 0 survivors),
  `transport/` (89 rows, 1 survivor), `db/compaction/` (208 rows, 0
  survivors — extends the earlier informal compaction survey to the whole
  subpackage: writer-switch-on-full, candidate-selection logic, and config
  validation account for nearly all rows) triaged so far — 329 of 4,490
  rows total; rejects logged in `_INDEX.md`. One live candidate found and
  written up:
  `acquireCapacity-queueCapacity-native_transport_receive_queue_capacity` — the CQL/native-transport
  sibling of the already-filed `internode_application_receive_queue_capacity`
  case (same `AbstractMessageHandler.acquireCapacity():419` if-check, reached
  via `CQLMessageHandler` instead of `InboundMessageHandler`, gated by
  `native_transport_receive_queue_capacity` config instead) — this sibling
  was already flagged as unfiled in the internode case's own notes; this pass
  confirmed it independently by reading `CQLMessageHandler`'s source and
  config wiring. **Promoted to a full case file 2026-09-18**:
  [`cassandra/if-check-exp/net/acquireCapacity-queueCapacity-native_transport_receive_queue_capacity.md`](cassandra/if-check-exp/net/acquireCapacity-queueCapacity-native_transport_receive_queue_capacity.md),
  `Status: pending` (trigger not yet designed/run). Writing it up surfaced
  a significant divergence from its internode sibling: under the
  **default** `native_transport_throw_on_overload=false` config, the
  disallow branch does not withhold message deserialization at all —
  decoding proceeds regardless, only a client-visible overload flag is
  set; the check only behaves like a real gate under the non-default
  `throwOnOverload=true`. Flagged as Target-3-relevant (a default-mode
  escape hatch, stronger than the memtable cases' `markBlocking()` pattern
  since no special caller state is required — it's the out-of-the-box
  behavior). `_INDEX.md` coverage summary now: 5 total cases, 2 verified,
  3 pending. Remaining subpackages still to triage (row counts as of
  2026-09-18; see `cassandra/if-check-exp/candidates/candidates.md` for the
  `db/` breakdown by sub-directory): `db` (774 remaining after
  `compaction/`), `utils` (717), `index` (487), `io` (466), `cql3`
  (368), `service` (267), `tools` (167), `config` (154), `net` (140, partial),
  `locator` (98), `serializers` (91), `dht` (78), `gms` (74), `repair` (62),
  `schema` (48), `metrics` (44), `hints` (34, partial), `auth` (30),
  `streaming` (23), `batchlog` (10), `security` (10), `tracing` (6), `audit`
  (4), `diag` (3), `exceptions` (3), `triggers` (2). Next: continue triage
  batch-by-batch (biggest remaining: `db/marshal`, `db/tries`, `utils/`),
  then promote the `acquireCapacity-queueCapacity-native_transport_receive_queue_capacity`
  candidate to a full case file.
- **New case drafted, not yet verified (2026-09-17):**
  `cassandra/if-check-exp/commitlog/processNewSegment-allowance-cdc_total_space.md` — byte cap on total un-consumed
  CDC-hard-linked commit log segment data
  (`cdc_total_space`, auto-derived default 1/8 of the `cdc_raw_directory`
  filesystem, capped at 4096MiB), compared in `CDCSizeTracker.processNewSegment():335` (re-evaluated by `permitSegmentMaybe()`) and enforced in
  [`CommitLogSegmentManagerCDC.throwIfForbidden():214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L214)
  (fed by the byte-count comparison in the sibling `permitSegmentMaybe()`).
  Gates whether a CDC-tracked mutation may be written into the current
  commit log segment. Disallow branch throws `CDCWriteException` (a
  `RequestExecutionException`) — a **clean reject**, the first case in this
  folder that isn't a block-and-wait or backpressure-register. Escape hatch
  found: `cdc_block_writes = false` (live-mutable via JMX) bypasses the
  check entirely, same shape as the memtable cases' `markBlocking()`.
  `Status: pending` — line numbers verified against the local pinned-tag
  clone (2026-09-17), no trigger run yet. Next step: run the existing
  `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java`
  (uses `testWithCDCSpaceInMb()` + `bulkWrite()` helpers that already drive
  writes to exhaustion and assert `CDCWriteException`) via `ant testsome
  -Dtest.name=org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDCTest`
  — identify which specific `@Test` method most directly isolates the
  `cdc_total_space` boundary (vs. the `cdc_block_writes`-toggle tests)
  before citing it as primary evidence.
- **New case drafted, not yet verified:**
  `cassandra/if-check-exp/net/acquireCapacity-queueCapacity-internode_application_receive_queue_capacity.md` — per-connection
  byte cap (`internode_application_receive_queue_capacity`, default 4MiB) in
  [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419),
  gating deserialization of inbound internode `Message` objects. Disallow
  branch backpressures (registers on `endpointWaitQueue`/`globalWaitQueue`)
  rather than dropping the message — no escape hatch found yet, unlike the
  memtable cases' `markBlocking()`. `Status: pending` — line numbers verified
  against the local pinned-tag clone (2026-09-17), but no trigger designed or
  run. Next step: design a unit-level trigger (construct an
  `InboundMessageHandler` with a tiny `queueCapacity` and exhausted reserve
  `Limit`s, feed one oversized message frame) per the case file's
  Verification section, checking `test/unit/org/apache/cassandra/net/` for
  reusable scaffolding first.
- **New case drafted, not yet verified:**
  `cassandra/if-check-exp/hints/switchCurrentBuffer-MAX_ALLOCATED_BUFFERS-MAX_HINT_BUFFERS.md` — cap
  (`MAX_ALLOCATED_BUFFERS`, a JVM system property `cassandra.MAX_HINT_BUFFERS`,
  default 3) on off-heap `HintsBuffer` allocations in
  [`HintsBufferPool.switchCurrentBuffer():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L113).
  Disallow branch blocks the caller on `reserveBuffers.take()` until a
  flushed buffer is recycled via `offer()`, rather than allocating a new
  one — no escape hatch found yet. `Status: pending`. Next step: run the
  existing `test/unit/org/apache/cassandra/hints/HintsBufferPoolTest.java`'s
  `testBackpressure()` test as-is (`ant testsome
  -Dtest.name=org.apache.cassandra.hints.HintsBufferPoolTest`) — it already
  uses a byteman rule at the exact `reserveBuffers.take()` call inside this
  if-check's disallow branch, so no new harness is needed, just execution +
  recording the result in the case file's Verification table. Confirm
  Byteman is resolved as a test dependency by `ant testsome` before running.
- Broader survey (2026-09-17) also considered and rejected:
  `CommitLogSegment.java:242` and `HintsBuffer.java:190` (both allocate a new
  segment/buffer on "full" rather than diverging into block/reject — same
  non-diverging pattern as prior compaction rejects), and
  `BatchStatement.java:349` (`verifyBatchSize()`, rejects an already-built
  batch post hoc, doesn't gate object creation). Logged in `cassandra/if-check-exp/_INDEX.md`.
- **Both memtable cases are `verified` and pushed** (commit `0198e25`).
- **Optional rigor gap:** the offheap case's evidence (reused
  `testBookKeeping()`) doesn't isolate a timeout-based proof of the
  "blocks" outcome the way `HeapPoolTest` does for the heap case — see
  caveat above. Writing a purpose-built `NativeAllocatorTest`-style test
  mirroring `HeapPoolTest`'s two isolated `@Test`s would close this gap;
  explicitly not prioritized for now.
- **Filter rules refined into three explicit rules (see README § Core
  concept):** Rule 1 (identify the limit-side operand as a
  capacity/constraint), Rule 2 (the allow branch creates memory-significant
  objects, and the operand bounds *total bytes*, not rate/concurrency/
  throughput), Rule 3 (the disallow branch must produce some observably
  different outcome from the allow branch — not necessarily a clean reject,
  per the verification methodology's "trace the real effect" rule). This
  supersedes the earlier informal "memory-magnitude filter" note — same
  substance, now split out and tied explicitly to the folder's stated
  purpose (find resource constraints that limit memory usage, where the
  constraint takes effect via the if-check itself). This is a narrowing of
  `if-check-exp` specifically — the project's broader Target 1 scope still
  covers CPU-limiting constraints too, just not in this folder's inventory.
- **`compaction` module explored, no case retained:** surveyed
  `db/compaction/**` for candidates. The one real candidate found,
  `CompactionManager.submitBackground():245`'s `concurrent_compactors` check
  (gating scheduling of a `BackgroundCompactionCandidate` task on the
  compaction thread pool), was drafted then removed after adopting the
  memory-magnitude test now codified as Rule 2: `concurrent_compactors`
  bounds thread-pool *concurrency*, not the bytes a compaction task
  allocates once running. Logged in `cassandra/if-check-exp/_INDEX.md`'s
  "lines considered and rejected" table along with the other compaction lines surveyed (mostly
  config-validation, non-diverging selection logic) so this module isn't
  re-scanned from scratch.
- **Other modules still undecided:** native transport / request queues,
  concurrent executors remain open per the README's Target-1 discovery
  step — apply all three filter rules when evaluating candidates there too
  (e.g. a queue *depth* limit only counts under Rule 2 if each queued slot
  holds a memory-significant object, not a lightweight task reference).
