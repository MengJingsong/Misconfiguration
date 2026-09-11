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
repo (e.g. `oom-exp`) — when setting up verification infrastructure for
this folder, assume nothing is already provisioned and build/configure it
from scratch under this folder's own scope.

## Where things live

- **Repo:** `MengJingsong/Misconfiguration` on GitHub.
- **Local clone:** `Downloads\Misconfiguration` on device `heisenberg-laptop`
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

- Local clone (separate from the Misconfiguration repo) at
  `Downloads\cassandra-cassandra-5.0.9` on `heisenberg-laptop`.
- Confirmed as tag `cassandra-5.0.9` by content (`build.xml`'s
  `base.version` and `CHANGES.txt`'s top entry both read `5.0.9`).
- **Always grep/read the local clone to verify a line number**, then build
  the GitHub link as `.../blob/cassandra-5.0.9/<path relative to repo
  root>#L<NN>`. Never cite a line from memory or from a GitHub fetch alone.

## Current state — two cases written, both `in-progress`

- **`memtable/memtable_heap_space-bytebuffer.md`** — on-heap path. If-check:
  [`MemtablePool.SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156),
  gating `ByteBuffer.allocate(size)` via `HeapPool.Allocator.allocate()`.
  Limit traced from `Config.java`'s `memtable_heap_space` through to
  `SubPool.limit`. **Verification is fully designed and documented in the
  case file, not yet executed:**
  - **Primary trigger (do this first — cheap, deterministic):** a complete
    new unit test, `test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java`
    (full source is written out in the case file's Verification section,
    ready to save and run) — two `@Test` methods proving (1) the disallow
    branch parks the calling thread on `SubPool.hasRoom` until released,
    and (2) a `markBlocking()`-marked op instead silently overshoots the
    limit (escape-hatch behavior — flagged for Target 3, not pursued here).
    Jingsong will run this **on a cluster node reached over SSH from a
    control machine (WSL)**, not locally on `heisenberg-laptop` — the case
    file's instructions cover provisioning that node from scratch (JDK,
    `ant`, a fresh `cassandra-5.0.9` source clone — assume none of these
    are already present) and running via
    `ssh <user>@<node> "cd <source-tree> && ant testsome -Dtest.name=org.apache.cassandra.utils.memory.HeapPoolTest"`.
  - **Secondary trigger (optional, after the unit test passes):**
    live-cluster, documented in the case file as this experiment's own
    independent setup — a single node, provisioned and configured from
    scratch (no assumption of existing Cassandra install, config, or
    guardrail state, from this or any other experiment), with a
    `jstack`-over-SSH thread dump as the primary evidence (JMX metric as
    optional corroboration only, since `nodetool` has no built-in MBean
    reader).
  - `Status` stays `in-progress` until a trigger is actually run and its
    result (pass/fail, actual evidence) is recorded in the case file's
    `Trigger method`/`Evidence` fields.
- **`memtable/memtable_offheap_space-region.md`** — off-heap sibling case.
  Same if-check, `offHeap` `SubPool` instance instead of `onHeap`, reached
  via `NativePool`/`NativeAllocator` instead of `HeapPool`; limit is
  `memtable_offheap_space`. Object created is a `NativeAllocator.Region`
  (native memory via `MemoryUtil.allocate()`), not a `ByteBuffer`.
  Verification section names a recommended trigger
  (`test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java`'s
  existing `testBookKeeping()` already exercises this exact if-check both
  ways — reuse/extend it rather than writing a new harness) but, unlike the
  heap case, has **not** had a full ready-to-run test written out yet — that
  would be a reasonable next step if this case is prioritized.
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

- **Run `HeapPoolTest`** on a cluster node (see above) and record the
  result in `memtable_heap_space-bytebuffer.md`'s Verification section.
- **Neither case is `verified` yet** — both need an actual trigger run with
  recorded evidence, per the README methodology, before flipping `Status`.
- **`memtable_offheap_space-region.md` has no ready-to-run test written
  out** (unlike the heap case) — only a pointer to `NativeAllocatorTest`.
- **Next module/if-check to inventory is undecided** — no scope commitment
  beyond memtable allocation yet. Natural candidates per the README's
  Target-1 discovery step: native transport / request queues, compaction,
  concurrent executors.
