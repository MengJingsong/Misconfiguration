# If-Check Exp — Handoff

For a new session (Claude Code, Cowork, or otherwise) picking up
`if-check-exp` work. Read this first, then `README.md` for the full format
spec. This file is kept in sync with the Cowork "Throttling" project's
handoff doc (`claude/if-check-exp-handoff.md`) so a local Claude Code
session — which can't read that project's knowledge base directly — has
the same context available on disk.

## What this experiment is

Part of the **Throttling** research project (Target 1: identify resource
constraints that limit memory/CPU usage; Target 2: show how each constraint
restricts usage via its exact code path; Target 3: bypass analysis — out of
scope for this folder), scoped to **Apache Cassandra 5.0.9**. `if-check-exp`
inventories individual **if-checks**: single `if` statements where one
operand relates to object/resource creation and the other to a capacity
limit, and the two branches genuinely diverge (one allows the allocation,
the other blocks/rejects it).

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

## Current state — both cases `verified`

- **`memtable/memtable_heap_space-bytebuffer.md`** — on-heap path. If-check:
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
- **`memtable/memtable_offheap_space-region.md`** — off-heap sibling case.
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

## Open items / natural next steps

- **Both memtable cases are now `verified` and pushed** (commit `0198e25`).
- **Optional rigor gap:** the offheap case's evidence (reused
  `testBookKeeping()`) doesn't isolate a timeout-based proof of the
  "blocks" outcome the way `HeapPoolTest` does for the heap case — see
  caveat above. Writing a purpose-built `NativeAllocatorTest`-style test
  mirroring `HeapPoolTest`'s two isolated `@Test`s would close this gap;
  explicitly not prioritized for now.
- **New scope filter adopted — memory-magnitude only:** README now has a
  "Memory-magnitude filter" rule (see below). A candidate's limit-side
  operand must bound the *total bytes* that can be allocated/held, not just
  the rate/concurrency/throughput of processing. This is a narrowing of
  `if-check-exp` specifically — the project's broader Target 1 scope still
  covers CPU-limiting constraints too, just not in this folder's inventory.
- **`compaction` module explored, no case retained:** surveyed
  `db/compaction/**` for candidates. The one real candidate found,
  `CompactionManager.submitBackground():245`'s `concurrent_compactors` check
  (gating scheduling of a `BackgroundCompactionCandidate` task on the
  compaction thread pool), was drafted then removed after the memory-
  magnitude filter was adopted: `concurrent_compactors` bounds thread-pool
  *concurrency*, not the bytes a compaction task allocates once running.
  Logged in `_INDEX.md`'s "lines considered and rejected" table along with
  the other compaction lines surveyed (mostly config-validation, non-
  diverging selection logic) so this module isn't re-scanned from scratch.
- **Other modules still undecided:** native transport / request queues,
  concurrent executors remain open per the README's Target-1 discovery
  step — apply the memory-magnitude filter when evaluating candidates there
  too (e.g. a queue *depth* limit only counts if each queued slot holds a
  memory-significant object, not a lightweight task reference).
