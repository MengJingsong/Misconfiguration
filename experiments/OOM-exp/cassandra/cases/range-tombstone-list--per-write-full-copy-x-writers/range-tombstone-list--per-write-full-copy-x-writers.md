# U11 — RangeTombstoneList of a memtable partition: uncounted full copy per write attempt × concurrent writers  <!-- file: cassandra/cases/range-tombstone-list--per-write-full-copy-x-writers/range-tombstone-list--per-write-full-copy-x-writers.md -->

| Field | Value |
|---|---|
| Case ID | `U11` (unprotected accumulation; README "ID prefixes") |
| From | cluster `OC-206` (primary), `OC-200`, `OC-201`, `OC-202`, `OC-368` of the phase 1 OOM candidate list |
| Phase-1 case files | [`range_tombstone_list_growth_factor-addInternal-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-addInternal-capacity--autonomous.md), [`range_tombstone_list_growth_factor-grow-newLength--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-grow-newLength--autonomous.md), [`range_tombstone_list_growth_factor-growToFree-newLength--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-growToFree-newLength--autonomous.md), [`none-addall-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/none-addall-size--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`), build `/mydata/s4/cassandra-base` on `pc96`, OpenJDK 11.0.33, G1 as shipped in `conf/jvm11-server.options` |
| Stage 1 (design) | OOM-agent stage-1 session (workflow wave 4), 2026-11-18 ≈ 13:40–14:20 America/New_York, repository HEAD `411b6a8f` |
| Stage 2 (verify) | fresh OOM-agent stage-2 session (workflow wave 4), 2026-11-18 13:52–15:50 America/New_York, on `pc96`; freeze hash checked (match) |
| Verdict | **`retry`** (detail: `candidate` — GC service loss 1/1 at a 512 MiB heap, not repeated; no OOM 0/6 at 512 MiB, 2 GiB, 8 GiB) |

## Summary

- **Conclusion:** no heap OOM in any run (T ×3 and D at 2 GiB, 8 GiB, 512 MiB: 0/6). The in-flight copies were measured
  (219–302 MiB at 2 GiB, 949 MiB at 8 GiB) and drive GC thrash (467–476 full GCs per 300 s at 2 GiB, 79 % STW); the live
  heap at full GCs stayed at 0.19–0.37 × heap. At 512 MiB the default service-loss criterion was met once (≥ 90 % STW for
  ≈ 100 s, 1/1 run): a gap without OOM, so the verdict is **retry** (§4); OOM itself looks unreachable at defaults.
- **Root cause (measured by arm D and B8 L1; §3.3):** every write attempt that carries a range tombstone into a memtable
  partition copies the partition's whole `RangeTombstoneList` (four arrays trimmed to size n) and then grows the copy
  by 1.5× (≈ 50 B × n of transient arrays). Only the size delta of the merged list is charged to the memtable pool,
  failed CAS attempts are charged nothing, and the AtomicBTreePartition waste tracker sees the charged delta
  (≈ 0.5–1 KiB), not the copy, so nothing bounds the copies except the number of `MutationStage` permits
  (`concurrent_writes` = 32). n itself is bounded by the memtable flush trigger (⅓ of `memtable_heap_space`).

## 1. Candidate

### 1.1 The cluster rows (quoted from `phase1-oom-candidates.md`, Status as of 2026-11-18)

| ID | Date | Phase-1 case file | Agent | Clue (mechanism, rough magnitude at defaults) | Patterns | Status |
|---|---|---|---|---|---|---|
| OC-200 | 2026-11-17 | `range_tombstone_list_growth_factor-addInternal-capacity--autonomous` | autonomous | Every range-delete write into a memtable partition that already holds N range tombstones copies the partition's whole RangeTombstoneList. [details](runs/wave1.md#oc-200) | — | picked: U11 |
| OC-201 | 2026-11-17 | `range_tombstone_list_growth_factor-grow-newLength--autonomous` | autonomous | This is the same memtable merge path as in the sibling RTL cases (the target line, grow(int) from copyArrays, does not read the factor). [details](runs/wave1.md#oc-201) | — | picked: U11 |
| OC-202 | 2026-11-17 | `range_tombstone_list_growth_factor-growToFree-newLength--autonomous` | autonomous | Each write into a memtable partition with N range tombstones copies the partition's RangeTombstoneList. [details](runs/wave1.md#oc-202) | — | picked: U11 |
| OC-206 | 2026-11-17 | `range_tombstone_list_growth_factor-addInternal-capacity--autonomous` | guided | Holder: the full RangeTombstoneList copy that every memtable merge into a partition with range tombstones makes. [details](runs/wave1.md#oc-206) | CP-1, CP-7 | picked: U11 |
| OC-368 | 2026-11-18 | `none-addall-size--autonomous` | autonomous | Holder: the transient per-write copy of a memtable partition's whole RangeTombstoneList. [details](runs/wave2.md#oc-368) | — | picked: U11 |

Full text (`runs/wave1.md`, `runs/wave2.md`), quoted:

> **OC-206** (primary). Holder: the full RangeTombstoneList copy that every memtable merge into a partition with range
> tombstones makes. BTreePartitionUpdater.merge calls existing.mutableCopy(), which runs RangeTombstoneList.copy() and
> copies all four arrays at size n. add() then grows the copy by the factor. Only the delta newInfo.unsharedHeapSize() -
> existing.unsharedHeapSize() is charged to the memtable, so the old list and each in-flight copy are never counted.
> Nothing bounds how many copies exist at once except the writers in flight on that partition: up to concurrent_writes =
> 32, and more under AtomicBTreePartition CAS retries before the waste tracker forces pessimistic locking. The retained
> part is over-counted (stage 4: about 504 B counted vs about 275 B live per tombstone), so the memtable flushes at about
> half the real volume, but the transient part is outside every limit. Rough size at defaults: with an 8 GiB heap,
> memtable_heap_space is 2 GiB and the flush trigger is about 1/3 of that. One hot partition can hold about 1.3 M range
> tombstones before a flush. Each in-flight write then holds about (1 + 1.5) x 1.3 M x 20 B = about 65 MB of uncounted
> young-gen arrays, so 32 concurrent writers hold about 2 GB. Each write also costs O(n) copying (O(n^2) over a fill). The
> same mechanism shows up in range_tombstone_list_growth_factor-growToFree-newLength--autonomous and
> range_tombstone_list_growth_factor-grow-newLength--autonomous; file it once. **Where:**
> BTreePartitionUpdater.java:120-121; MutableDeletionInfo.java:83; RangeTombstoneList.java:106-114, :683;
> AtomicBTreePartition.java:153, :239-294; conf/cassandra.yaml:723

> **OC-200.** Every range-delete write into a memtable partition that already holds N range tombstones copies the
> partition's whole RangeTombstoneList. existing.mutableCopy() calls ranges.copy(), which trims all four arrays to size.
> The add then finds the list full, and growToFree reallocates all four arrays at ceil(N x 1.5). That is about 20 B x N
> for the copy plus about 30 B x N for the growth, all transient. Only the size delta is charged to the memtable
> (onAllocatedOnHeap(new - existing)), so nothing bounds these copies. Each optimistic CAS attempt in AtomicBTreePartition
> repeats the copy; it switches to locking only after 10 MiB of waste, so up to concurrent_writes (32) attempts can each
> hold a copy. Rough size at defaults: an 8 GiB heap has memtable_heap_space 2 GiB and flushes at about 1/3 of that. At
> about 500 accounted B per tombstone, one partition can reach about 1.3 M tombstones, so each write allocates about 65
> MB, including several multi-MB humongous arrays such as a ClusteringBound[] of about 5 MB. 32 writers in flight would be
> about 2 GB of transient heap. Even with a single writer, steady writes to that partition generate garbage at about 65
> MB x write rate. **Where:** BTreePartitionUpdater.java:120-121; MutableDeletionInfo.java:83;
> RangeTombstoneList.java:105-113,664-689,700-739; AtomicBTreePartition.java:63,258-293

> **OC-201.** This is the same memtable merge path as in the sibling RTL cases (the target line, grow(int) from
> copyArrays, does not read the factor). Each write to a memtable partition that holds N range tombstones copies its
> RangeTombstoneList, trimmed to size, and then grows it by the factor (default 1.5). That is about 50 B x N of transient
> arrays per write. Only the size delta is charged to the memtable (onAllocatedOnHeap(newInfo - existing)). Contended
> writers each make their own copy until AtomicBTreePartition's 10 MiB waste tracker switches to locking. Rough size at
> defaults: on an 8 GiB heap a partition can reach about 1.3 M tombstones before the memtable flushes (about 500
> accounted B per tombstone against about 680 MiB), so each write allocates about 65 MB, mostly in humongous arrays. With
> up to 32 concurrent writes, that is about 2 GB of transient heap that no limit counts. **Where:** as OC-200 (:680-689,
> :700-739).

> **OC-202.** Each write into a memtable partition with N range tombstones copies the partition's RangeTombstoneList.
> mutableCopy calls copy(), which trims the arrays to exactly size, so the add then always triggers growToFree to ceil(N x
> factor). At the default 1.5 that is about 50 B x N of transient allocation per write. It is outside memtable
> accounting, which charges only the delta, and it is repeated by each contended CAS attempt until the 10 MiB waste
> tracker forces locking. Rough size at defaults: on an 8 GiB heap a partition can reach about 1.3 M tombstones before
> the flush (1/3 of memtable_heap_space at about 500 accounted B per tombstone). That gives about 65 MB per write, in
> multi-MB humongous arrays, and about 2 GB transient with 32 concurrent writes. **Where:** as OC-201.

> **OC-368.** Holder: the transient per-write copy of a memtable partition's whole RangeTombstoneList. Every update that
> carries range tombstones runs existing.mutableCopy().add(update), which copies all n slots (20 B/slot: two
> ClusteringBound[], long[], int[] at capacity == size) and then, through addAll, immediately grows the full copy by 1.5x
> (another 30 B/slot). That is about 50·n bytes of short-lived arrays per write attempt. For n beyond about 100k these are
> G1 humongous objects. Why nothing stops it: it uses HeapCloner, not the memtable allocator, and only the delta of
> unsharedHeapSize is charged, so no pool or limit sees the copy. Each CAS retry on a contended partition copies again,
> and the Updater lock does not exclude. Rough size at defaults: up to concurrent_writes=32 writers each hold one copy. A
> partition with n = 500k range tombstones in the memtable gives ~25 MB per attempt × 32 ≈ 0.8 GB live at once. A few
> million tombstones, which the heap/4 memtable pool allows, give several GB, on top of the memtable itself.
> **Where:** BTreePartitionUpdater.java:120-121; MutableDeletionInfo.java:81-83,138-141;
> RangeTombstoneList.java:106-112,213-232,664-686

Triage row (`runs/triage-2026-11-18.md`, rank 20), quoted: *"OC-206 | yes | single ARM node | Every write that carries
range tombstones into a memtable partition already holding N of them copies the whole RangeTombstoneList and grows it
1.5x (about 50 B x N), and only the size delta is charged to the memtable. Each contended CAS retry repeats the copy. At
a 2 GiB heap a hot partition holds about 300-500k range tombstones before flush, so 32 concurrent writers hold about
0.5-0.8 GB of uncounted humongous arrays on top of the memtable. The likely endpoint is GC thrash; a heap OOM is
plausible but not certain. | No existing case. CAS-retry amplification shared with OC-323. Duplicates OC-200, OC-201,
OC-202 and OC-368."* Notes §1: "Range-tombstone list copy: OC-200, 201, 202, 206, 368."

### 1.2 What the design covers

| Row | Covered by this design | Not covered (and why) |
|---|---|---|
| OC-206 | All of it: per-attempt copy + growth, delta-only charge, multiplicity up to `concurrent_writes`, CAS retries, n at the flush trigger, the 8 GiB magnitude (arm B8) | — |
| OC-200 | Same holder and magnitude; its "switches to locking only after 10 MiB of waste" is corrected in §2.1 (the tracker sees the charged delta, and the lock excludes no one) and is read only indirectly (in-flight count) | "garbage at 65 MB × write rate" as a single-writer GC cost: recorded as GC/allocation readings, not an OOM claim |
| OC-201 | Same holder (the growth half, `grow(i, newLength)`) | — |
| OC-202 | Same holder (`growToFree`) | — |
| OC-368 | Same holder, magnitude at n ≈ 0.3 M (2 GiB) and ≈ 1.2–1.4 M (8 GiB) | "A few million tombstones, which the heap/4 memtable pool allows": not reachable in one memtable at defaults — the cleaner flushes at ⅓ of the pool (`MemtablePool.java:125-145`, `DatabaseDescriptor.java:761-763`); the design runs at that cap, and §2.4 handles a stalled flush by arithmetic |
| all | — | the deep clone of the *update* (`update.clone(HeapCloner.instance)`, `BTreePartitionUpdater.java:120`) for updates carrying many range tombstones is a mutation-expansion holder (OC-15/B6 family), not this cluster's copy of the *existing* list; the O(n²) CPU cost is recorded, not judged |

### 1.3 Phase-1 cases and stage-4 evidence

All four phase-1 case files are `negative` estimates of a *capacity check* (the growth factor, the `addAll` branch
literal), and stage 4 filed all four as **true negative** ("does not cap"). Relevant measured facts:

- `range_tombstone_list_growth_factor-addInternal-capacity--autonomous` (results file, run 1, `pc07`, 8 GiB heap,
  2026-10-23): memtable counter **504 B/tombstone at f = 1.2, 510 B at f = 1.5, 580 B at f = 5.0**; live heap from
  `GC.class_histogram` **277–311 B/tombstone** (counter over-counts by ≈ 240 B, the double-counted bound size,
  `RangeTombstoneList.java:178` + `:766`); positive control at `memtable_heap_space: 128MiB` flushed 5 times. Single-partition
  load (S1, one request in flight): 30,000 writes from n = 20 k to 50 k in 23.8 s (≈ 0.8 ms per write at n ≈ 35 k, i.e.
  ≈ 18–20 ns per slot of copy+grow on one thread).
- `range_tombstone_list_growth_factor-grow-newLength--autonomous` and `…-growToFree-newLength--autonomous`: same
  counter values (504/510/520/580 B), live 272–363 B/tombstone with 1,000,000 tombstones per lifetime (50 partitions).
- `none-addall-size--autonomous` (unit tier, `pc39`, 2026-10-29): retained size 240.0 B per element beyond the arrays;
  growth allocates exactly 20 B × capacity (`300,064` B for capacity 15,000); `unsharedHeapSize()` double-counts
  bounds on the `add()` branch. Cluster tier `n/a`.

None of these runs had more than one request in flight per partition, so **no stage-4 run measured the in-flight
copies**; that is the gap this case fills.

### 1.4 JIRA prior art (read only; nothing posted)

Survey file `jira-oom-survey.csv`: `CASSANDRA-21492` "Make RangeTombstoneList.copy() copy-on-write to avoid O(N²)
array copying on range-tombstone memtable merges" — Unresolved, screened `excluded` ("allocation-cost improvement; no
OOM reported"). Related, different mechanism: 3741 / 6655 / 9194 (deletes under-charged → memtable never flushes;
fixed 1.1–2.1; 5.0.9 over-charges range tombstones instead), 13624 (upgradesstables OOM with many range tombstones,
unresolved, offline tool path), 8559 (tombstone warning message, fixed).

JIRA REST search, 2026-11-18 ≈ 13:50 (anonymous GET, `issues.apache.org/jira/rest/api/2/search`):

| Query (JQL) | Hits | Relevant |
|---|---|---|
| `key=CASSANDRA-21492` | 1 | **CASSANDRA-21492**, created 2026-07-08, status *Triage Needed*, no fix version. Describes exactly this path (`BTreePartitionUpdater.merge` → `mutableCopy()` → `copy()` copies all four arrays on every range-tombstone write; "421,953,645 B/op" allocation at N = 4096 in JMH) as a CPU/allocation cost; proposes copy-on-write. No OOM, no concurrency or memory-budget discussion. |
| `project=CASSANDRA AND text ~ "RangeTombstoneList" ORDER BY created DESC` | 49 | 21492 (above); 15763 (made the growth factor and initial size tunable, fixed 4.0); the rest are correctness bugs (14894, 15924, 21018, 21498, legacy-layout) |
| `project=CASSANDRA AND text ~ "range tombstone" AND text ~ "memtable" AND (OOM/OutOfMemory/GC)` | 68 | none reports an OOM from memtable range-tombstone merges; 21492 is the only hit on this path |

**Verdict: `known-open` for the per-write copy as a cost (CASSANDRA-21492, unfixed in 5.0.9); `new` as a memory-budget /
multiplicity claim.** Not a known-fixed bug, so not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism (direction: **unprotected accumulation · multiplicity**)

A write whose `PartitionUpdate` carries a range tombstone reaches `AtomicBTreePartition.Updater.addAll`
(`AtomicBTreePartition.java:146-177`), which loops `tryUpdateData` (`:179-186`): read `ref`, build the merged partition,
CAS. `makeMergedPartition` → `BTreePartitionUpdater.merge(DeletionInfo, DeletionInfo)` (`BTreePartitionUpdater.java:105-123`):
unless the update is live, `existing.mutableCopy().add(update.clone(HeapCloner.instance))` (`:120`).
`MutableDeletionInfo.mutableCopy()` (`MutableDeletionInfo.java:81-84`) calls `RangeTombstoneList.copy()`
(`RangeTombstoneList.java:106-114`), which allocates the four arrays `starts`, `ends` (`ClusteringBound<?>[]`, 4 B per
compressed reference), `markedAts` (`long[]`) and `delTimesUnsignedIntegers` (`int[]`) at **exactly size n** = 20 B × n.
`add(DeletionInfo)` (`MutableDeletionInfo.java:130-145`) → `addAll` (`RangeTombstoneList.java:184-232`) → for a
one-tombstone update `add(...)` (`n > 10 × 1`) → `addInternal` (`:664-674`), and because the copy is full,
`growToFree` → `grow(i, ceil(1.5 n))` (`:680-698`, `:700-739`) allocates four new arrays = 30 B × n. Peak per attempt
≈ **50 B × n** of short-lived arrays (bound objects are shared, not copied). The merged list replaces the memtable's
list on CAS success (old arrays become garbage); on CAS failure the whole copy is garbage and the loop repeats.

Accounting: `onAllocatedOnHeap(newInfo.unsharedHeapSize() - existing.unsharedHeapSize())` (`:121`) charges only the
delta (≈ 510 B per new tombstone at f = 1.5, stage 4), via `reportAllocatedMemory` → `allocator.onHeap().adjust(...)`
(`:180-183`) once, after the successful CAS; `tryUpdateData` resets `heapSize` per attempt, so failed attempts are charged
nothing. The waste tracker (`AtomicBTreePartition.java:239-294`, `EXCESS_WASTE_BYTES` 10 MiB at `:63`) is fed
`shouldLock(heapSize, writeOp)` (`:168`), i.e. the charged delta (≈ 0.5–1 KiB per failed attempt, rounded to 1 KiB
granules against an allowance of 7.63 KiB/ms), not the ≈ 50 B × n actually wasted, so at millisecond-scale attempts it
does not trip; and when it does, `synchronized (this)` (`:157`) locks the per-call `Updater`, which excludes no other
writer (also noted by OC-323). So **the number of live copies is bounded only by the number of threads inside
`addAll` on the partition**: local writes run through `Stage.MUTATION.maybeExecuteImmediately` (`StorageProxy.java:1566-1569`,
`:1674-1676`; `SEPExecutor.java:218-230`), which takes one of `concurrent_writes` = 32 work permits
(`conf/cassandra.yaml:723`). n is bounded by the memtable cleaner: a flush of the largest memtable is triggered when the
pool's used bytes exceed `reclaiming + limit × memtable_cleanup_threshold` (`MemtablePool.java:125-145`), threshold
= 1/(1 + `memtable_flush_writers` = 2) = ⅓ (`DatabaseDescriptor.java:753-763`), limit = `memtable_heap_space` =
heap/4 (`DatabaseDescriptor.java:587`).

Technique note: [`combo-playbook.md`](../../../combo-playbook.md) step 1 (multiplicity of one bounded-per-instance holder
against a shared budget), applied to an unprotected holder (no control covers the copy at all, so this is
**unprotected accumulation**, not a bypass of the memtable pool, whose contract covers only the retained list).

### 2.2 Protection map

| Domain | Allocation and owner | Counter / limit | Scope and multiplicity | Lifetime | At the limit |
|---|---|---|---|---|---|
| D1 in-flight RTL copy (the claimed holder) | `RangeTombstoneList.copy()` + `grow(i, …)` on the writer thread (`BTreePartitionUpdater.java:120`) | **none**; failed attempts charge 0, successful ones charge the delta | one per thread in `Updater.addAll` on the partition; ≤ 32 `MutationStage` permits | from `mutableCopy()` to CAS (success → becomes D2, failure → garbage) | nothing |
| D2 retained memtable RTL (arrays at capacity ≈ 1.5 n + bound objects) | memtable partition's `DeletionInfo` | memtable pool `memtable_heap_space` = heap/4 (counted ≈ 510 B, live ≈ 280–300 B per tombstone) | per memtable; ≤ 1 live + flushing memtables | until flush completes | cleaner flushes the largest memtable at ⅓ of the pool; writers block at the pool limit |
| D3 waste tracker / pessimistic lock | `AtomicBTreePartition.wasteTracker` | charged delta vs 10 MiB excess | per partition | — | a lock on a per-call object (excludes nobody) |
| D4 request in flight | native transport `Message` / `Mutation` (one tombstone, < 200 B) | `native_transport_max_request_data_in_flight` heap/10, per IP heap/40 (bytes on the wire) | client in-flight 64 | until response | not reached (64 × < 1 KiB) |
| D5 baseline | caches (key cache ≤ min(5 % heap, 100 MiB), counter cache, empty), schema, metrics, Netty | own caps | node | standing | — |

Budget: the Java heap (`-Xmx`). D1–D5 are all heap; no direct or native domain is involved
(`memtable_allocation_type: heap_buffers` default, and `HeapCloner` is on-heap anyway).

### 2.3 Configuration and budget audit

- **Source / build:** Cassandra 5.0.9 at repository commit `411b6a8f` (`systems/cassandra/source/`), built tree
  `/mydata/s4/cassandra-base` on `pc96` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`); stage 2 copies it once to
  `/mydata/s4/u11/cassandra` and never runs `ant` there. OS Ubuntu 22.04, kernel 5.15.0-198-generic, OpenJDK 11.0.33,
  cgroup v2, 8 GiB swap (kept at 0 for the node: `MemorySwapMax=0`).
- **Node `pc96`** (checked read-only 2026-11-18 13:45): x86_64, 32 cores, 125 GiB RAM (≈ 122 GiB available), `/mydata`
  572 GiB free, no `CassandraDaemon` running, load ≈ 2.
- **Capacity constraints, all at shipped defaults (V6):** `concurrent_writes: 32` (yaml :723) ·
  `range_tombstone_list_growth_factor: 1.5` and `initial_range_tombstone_list_allocation_size: 1` (`Config.java:798-802`,
  not in the yaml) · `memtable_heap_space` unset → heap/4 · `memtable_cleanup_threshold` unset → ⅓ ·
  `memtable_flush_writers` unset → 2 · `memtable_allocation_type: heap_buffers` (yaml :825) · memtable implementation
  default (skiplist) · `max_mutation_size` unset → 16 MiB · native-transport in-flight limits default ·
  `write_request_timeout: 2000ms`, `native_transport_timeout` 12 s default · batch thresholds default (single-partition
  batches are not size-checked, `BatchStatement.java:333-335`) · key/counter/row caches default. Resolved values to record
  per run (read from `system_views.settings` and JMX): `memtable_heap_space`, `memtable_cleanup_threshold`,
  `memtable_flush_writers`, `concurrent_writes`, `range_tombstone_list_growth_factor`.
- **Budgets (V7):** heap `MAX_HEAP_SIZE` = **2 GiB** (ideal, primary), plus **512 MiB** (minimum acceptable) and
  **8 GiB** in the budget search, **15,872 MiB** optional (what `cassandra-env.sh` resolves on `pc96` by itself:
  min(½ RAM, 15,872 MiB); it then sets `MaxDirectMemorySize` 7,936 MiB). With `MAX_HEAP_SIZE` set by hand,
  `cassandra-env.sh` still sets `MaxDirectMemorySize` = 7,936M on this host: record it (direct memory is not a domain
  here). No container memory limit (only `MemorySwapMax=0` in a user scope). All heap values ≥ 512 MiB: V7 met without
  per-case review.
- **JVM as shipped** (`jvm-server.options`, `jvm11-server.options`): G1, `G1HeapRegionSize=16m` (humongous ≥ 8 MiB),
  `G1NewSizePercent=50`, `MaxTenuringThreshold=2`, `MaxGCPauseMillis=300`, IHOP 70, `AlwaysPreTouch`,
  `PerfDisableSharedMem` (no `jstat`), `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError="kill -9 %p"`.
- **Deviations (all environment or instrumentation, none capacity):**
  - E1 single node on loopback; ports storage 7610, ssl 7611, native 9642, JMX 7699 (if busy: the next free block, recorded); `cluster_name`, data/commitlog/hints/saved_caches directories under the run directory.
  - E2 CPU: the node runs under `taskset -c` on **8 cores** chosen at the start as the least loaded (`mpstat`), the client on 1–2 other cores, the same set for every arm (the node is shared). The JVM then sees 8 processors (`ParallelGCThreads` 8): record it. The holder count does not depend on cores (a descheduled writer still holds its copy).
  - E3 instrumentation: the GC log line is moved into the run's `jvm-server.options` (so `cassandra-env.sh` does not add its own) as `-Xlog:gc*=info,gc+heap=debug,safepoint=info:file=<run>/logs/gc.log:time,uptime,level,tags:filecount=50,filesize=20M`; `-XX:HeapDumpPath=<run>/`; `-Dcassandra.printHeapHistogramOnOutOfMemoryError=true` (shipped commented, prints a histogram only on OOM). No Byteman or patch in arms T, C, I, B.
  - E4 no change to any capacity setting except `nodetool setconcurrency MutationStage 1` in the intervention arm only.

### 2.4 Ceiling arithmetic (before any reading)

Per budget H (MiB): pool = H/4; flush trigger ≈ ⅓ × H/4 counted; at 510 counted B per tombstone the hot partition's
n reaches n_max ≈ H/12/510. The run fills to **n₀ = 0.85 n_max** and adds ≤ 20,000 more (≈ +10 MB counted), so n stays
in [0.85, 0.92] × n_max without a flush. D1 per attempt = 50 B × n (with 16 MiB G1 regions an array ≥ 8 MiB occupies
whole regions, which matters only at ≥ 4 GiB); D2 live ≈ 290 B × n (one memtable; two if a flush overlaps); D5 ≈ 70–150 MB
(stage 4 histogram baseline 66–83 MB at 8 GiB).

| H | n at 0.85–0.92 n_max | D1 per attempt (content / region occupancy) | 32 × D1 | D2 (1–2 memtables) | D5 | Predicted peak live | / H |
|---|---|---|---|---|---|---|---|
| 512 MiB | 74 k – 81 k | 3.7–4.0 MB | 120–130 MB | 21–47 MB | 60–100 MB | 0.20–0.28 GB | 0.40–0.55 |
| 2 GiB | 298 k – 323 k | 15–16 MB | 480–520 MB | 86–190 MB | 70–150 MB | 0.64–0.86 GB | 0.30–0.40 |
| 8 GiB | 1.19 M – 1.29 M | 60–65 MB / ≈ 90–110 MiB | 1.9 GB content, ≈ 2.9–3.5 GiB of regions | 0.35–0.75 GB | 0.1–0.2 GB | 3.4–4.4 GiB of regions | 0.42–0.55 |
| 15,872 MiB | 2.3 M – 2.5 M | 115–125 MB / ≈ 144–160 MiB | ≈ 4.5–5.0 GiB of regions | 0.7–1.4 GB | 0.1–0.2 GB | 5.3–6.6 GiB | 0.34–0.42 |

The ratio is roughly independent of H because n_max ∝ H; with every domain at its contract capacity and all 32
permits holding a copy at the same instant, the sum stays **≈ 0.3–0.55 × H**. Overlaps named and settled by arithmetic:
(a) a stalled flush (external disk fault) does not raise n: the next memtable is switched at ⅓ again because
`reclaiming` is added to the trigger (`MemtablePool.java:143`), it only adds memtables up to the pool limit (≤ 3 ×
≈ 0.05 H live) → ≤ 0.65 H; (b) more client in-flight requests than permits only queue small mutations (D4);
(c) more hot partitions split n and lower Σ D1. **So the ceiling does not reach the budget at any acceptable heap;
a heap OOM at defaults would need live memory the protection map does not contain** (e.g. GC failing to reclaim
garbage in time, G1 humongous fragmentation at 16 MiB regions). The design therefore measures D1 directly and runs
the budgets where those G1 effects are largest (8 GiB: humongous rounding; 512 MiB: baseline share).

### 2.5 Workload and environment

- **Node:** `pc96` (local, no ssh), one Cassandra node from `/mydata/s4/u11/cassandra`, run directory
  `/mydata/s4/u11/<run-label>/` (fresh per run: `conf/` copy with E1/E3 edits, `data/`, `commitlog/`, `hints/`,
  `saved_caches/`, `logs/`). Launch: `( setsid nohup systemd-run --user --scope -p MemorySwapMax=0 taskset -c <8 cores>
  env CASSANDRA_CONF=<run>/conf CASSANDRA_LOG_DIR=<run>/logs MAX_HEAP_SIZE=<H> <cassandra>/bin/cassandra -f
  < /dev/null > <run>/logs/stdout.txt 2>&1 & )`; wait for the native port with a bounded poll (≤ 120 s). Before
  each run: `ps -eo pid,cmd | grep '[C]assandraDaemon'` (another agent's node may run: leave it alone, use free ports),
  `free -g` (need ≥ H + 4 GiB available), ports free (`ss -ltn`). Kill by PID at the end; delete the run's `data/`
  and `commitlog/` after the readings are copied (keep logs, GC log, histograms; keep one `.hprof` per arm at most,
  delete larger ones after extracting their histogram).
- **Client:** Python 3 with the bundled driver (`lib/cassandra-driver-internal-only-3.29.0.zip`, loading as in the
  stage-4 `client.py`), protocol v4, `WhiteListRoundRobinPolicy(['127.0.0.1'])`, `FallthroughRetryPolicy`, CL ONE,
  client request timeout 30 s. Schema: `CREATE KEYSPACE u11 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE u11.rt (pk int, ck int, v int, PRIMARY KEY (pk, ck))`. Statement S =
  `DELETE FROM u11.rt WHERE pk = ? AND ck > ? AND ck < ?` bound to `(pk, 4i, 4i+2)` (one non-empty slice per i;
  disjoint and ascending in i).
- **Phase F (fill), one request in flight:** unlogged `BatchStatement` of 100 S statements to one partition (one
  mutation, 100 tombstones), i ascending; after every 50 batches read the table's `MemtableOnHeapDataSize` over JMX;
  stop when it reaches **0.85 × memtable_cleanup_threshold × memtable_heap_space** (resolved values read at start).
  Check `MemtableSwitchCount` = 0 and acknowledged tombstones = written. Predicted F time: < 30 s at 2 GiB, ≈ 2–4 min at
  8 GiB (O(n) per batch).
- **Quiesce Q:** 10 s idle, then one `jcmd <pid> GC.class_histogram` (baseline L0: total, `[Lorg.apache.cassandra.db.ClusteringBound;`,
  `[J`, `[I`, `BufferClusteringBound`), then 20 s idle.
- **Phase W (contention), 64 requests in flight:** single-statement S writes with fresh ascending i above the fill
  range, kept at 64 outstanding (callback-chained `execute_async`), until **20,000 acknowledged**, or **300 s**, or the
  node dies, or `MemtableSwitchCount` rises (then stop W: n has reset), whichever comes first. Timeouts and errors are
  counted, not retried.
- **Arms** (labels used in §3):
  - **T (test)**: one hot partition `pk = 0` in F and W. H = 2 GiB, **×3**.
  - **C (matched control)**: the same F target counter and the same W count/in-flight/statement, but spread over
    1,000 partitions (`pk = k mod 1000`; F batches of 100 to one partition at a time, round-robin), so n per
    partition ≈ n₀/1000 and D1 ≈ 15 KB per attempt; same K trajectory, same flush distance, same writers. H = 2 GiB, **×3**.
  - **I (intervention: bound the multiplicity)**: as T, but after Q `nodetool -p <jmx> setconcurrency MutationStage 1`
    (check `getconcurrency` = 1); same W stop rule; record the acknowledged rate. H = 2 GiB, **×3**.
  - **B (budget search, T at other heaps)**: if any T run reaches OOM at 2 GiB → T at 4 GiB, then 8 GiB, then 15,872 MiB
    (×1 each, stop at the first survivor), then ×3 at the largest failing heap if time allows. If no T run fails at
    2 GiB → **B8: T at 8 GiB ×1** and **B05: T at 512 MiB ×1**; any OOM there → ×3 at that heap plus C and I ×3 at it.
  - **D (diagnostic attribution, intrusive)**: as T at 2 GiB, ×1, with `jcmd GC.class_histogram` every 20 s during W
    (each forces a full GC, so D is never counted toward V1/V2).
- **Stopping budget:** per run ≤ 300 s of W; ≤ 15 runs; no escalation beyond 15,872 MiB; no change of any constraint
  after a failure; a node that does not answer JMX for 120 s is `jcmd Thread.print`-ed once and killed by PID.

### 2.6 Instruments (U independent of K)

- **K (the control's counter):** table `MemtableOnHeapDataSize` and `MemtableSwitchCount`
  (`org.apache.cassandra.metrics:type=Table,keyspace=u11,scope=rt,…`), `AllMemtablesOnHeapDataSize`; sampled every 1 s.
- **Multiplicity A:** `org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=ActiveTasks`
  and `PendingTasks`, every 1 s (expected A = 32 in T/C W, 1 in I).
- **U (physical, independent of K):**
  - every 1 s over JMX: `G1 Eden Space`, `G1 Survivor Space`, `G1 Old Gen` usage and `G1 Old Gen` *collection usage*
    (live after the last old/mixed/full collection), GC MXBean counts and times (as stage-4 `HeapPoll.java`, extended);
  - the GC log: per collection the heap before→after, humongous regions before→after, pause type and duration; every
    `Pause Full` gives the live heap at that instant with the writers' in-flight copies stopped at the safepoint;
  - L0 / L1 histograms (end of Q / after W drains), and arm D's 20 s histograms: **U_D1 = (ClusteringBound[] + long[] +
    int[] bytes) − the same classes in L0**, compared with A × 50 × n (the arrays per in-flight copy are
    ClusteringBound[] 2 × (4n + 6n), long[] 8n + 12n, int[] 4n + 6n).
  - on OOM: the first `OutOfMemoryError` line and thread from `system.log`/`stdout.txt`, the printed histogram
    (`printHeapHistogramOnOutOfMemoryError`), the `.hprof`, and the last GC-log lines (V5).
- **Workload:** client per-second acknowledged writes, timeouts, errors, p50/p99 latency; n from acknowledged tombstones
  (checked against L0/L1 `BufferClusteringBound` / 2).
- **Derived per run:** peak `Old Gen collection usage` and peak full-GC after-size minus L0 total (= U_D1 + D2 growth);
  STW fraction per 60 s window (sum of pause durations / 60 s) and its maximum over W; allocation-rate estimate from
  young-GC before sizes.

### 2.7 Predicted response, endpoints and verdict mapping

Predictions (before readings):

1. F reaches n₀ with `MemtableSwitchCount` 0 in every arm; K ≈ 510 B × n (± 5 %).
2. **T/W at 2 GiB:** A = 32 during W; acknowledged rate ≈ 50–200 writes/s (roughly one success per O(n) attempt);
   peak live (full-GC after-size or Old collection usage) ≈ L0 + 0.3–0.55 GB, **≤ 0.5 × H**; **no OOM**; STW fraction
   high (allocation ≈ 15 MB per attempt) but below the 90 % service-loss criterion. Arm D: U_D1 at a histogram ≈
   (0.5–1.0) × 32 × 50 B × n ≈ 0.25–0.52 GB while K moves by < 1 MB between two histograms.
3. **C:** same K trajectory, A = 32, U_D1 ≈ 0 (< 5 MB); peak live ≈ L0 + < 0.1 GB; no OOM; W finishes in seconds.
4. **I:** A = 1; peak live ≈ L0 + ≈ 16 MB; acknowledged rate not lower than T's by more than 2× (contention already
   serialises successes in T).
5. **B8 (8 GiB):** humongous regions dominate D1 (several hundred 16 MiB regions in flight); peak ≈ 0.42–0.55 × H;
   **no OOM** predicted; **B05 (512 MiB):** peak ≈ 0.4–0.55 × H, no OOM predicted.

Endpoints (protocol "Measurement and outcomes"): Java heap OOM (first error + thread, histogram showing
ClusteringBound[]/long[]/int[] above L0); GC service loss (≥ 90 % STW over ≥ 60 s, from the GC log); kernel kill
(not expected: no cgroup limit); none.

Verdict mapping for stage 2 ([`oom-agent-playbook.md`](../../../oom-agent-playbook.md)):

- **true positive** — T (or a B budget) reaches a Java heap OOM in ≥ 3 runs at one heap, C survives ×3 and I survives
  ×3 at that heap, the OOM-time histogram shows the D1 arrays above L0 (V1–V7).
- **false positive** — every T/B run reached its target (n₀, A = 32, 20,000 writes or 300 s) without OOM, D1 was
  measured (arm D) and the peak live stayed below the budget, consistent with §2.4 (which already settles the named
  overlaps a–c).
- **retry** — GC service loss without OOM (`verified-gap`), or a run that did not reach its target (A < 32, F flushed,
  node instability unrelated to the mechanism), or arm D not run (D1 unmeasured).

### 2.8 Controls, intervention, time plan

- **Matched control:** arm C (×3): same counter trajectory, same writer multiplicity, same statement and count; only n
  per partition differs (≈ 300 vs ≈ 300,000). This isolates D1 (the copy) from D2 (retained, counted) and D4.
- **Causal intervention:** arm I (×3): bound the multiplicity of D1 to 1 via `setconcurrency` (a runtime change in the
  intervention arm only). If `setconcurrency MutationStage 1` is refused, use 2 and record it. A code intervention
  (copy-on-write as in CASSANDRA-21492) is not used: its `isolate()` still reallocates the arrays on the first write, so
  it does not remove the per-attempt O(n) allocation.
- **Time plan (America/New_York, 2026-11-18; deadline 18:07):** stage 2 starts at S (expected ≤ 14:45). S → S+0:40
  harness (`harness/`: `run.sh`, `client.py`, `Poll.java`, `analyze.py`) and one shakedown at n₀ = 20 k (not a reading);
  then T×3 (≈ 8 min each, 2 GiB), C×3 (≈ 5 min each), I×3 (≈ 8 min each), D×1 (≈ 10 min), B8 (≈ 14 min), B05
  (≈ 6 min): ≈ 1 h 55 min of runs → S+2:35; write-up and clean-up ≈ 30 min → **S+3:05**. Latest S for the full plan:
  **15:00**. If S is later or a run overruns, drop in this order: B05, then B8's repeat, then D's later histograms
  (keep at least two), then reduce C and I to ×3 at the expense of nothing else; never start a run after **17:35**;
  stop every process by **17:50**.
- **Resources:** peak RAM ≈ 8 GiB heap + ≈ 1 GiB native (15,872 MiB only if ≥ 30 GiB available and time allows);
  disk < 30 GiB per arm including one `.hprof`; CPU 8 cores for the node + 1–2 for the client.
- **Left on the node at the end:** `/mydata/s4/u11/` with logs (data directories deleted), nothing running.

`sha256 of §1–§2 at freeze: 8baea9f6d3ec1167d472c79488e27c80a0029e328effd1f3aff8387a400ddf6a` (lines 26–375 of this file, from "## 1. Candidate" through the line before this one, `sed -n '26,375p' | sha256sum`; 2026-11-18 13:52 America/New_York) · amendments after the freeze: execution deviations only, dated 2026-11-18 in §3.2 (no design change).

## 3. Runs (stage 2)

Stage-2 session (fresh, workflow wave 4), 2026-11-18, started 13:52 America/New_York. Freeze hash checked first:
`sed -n '26,375p' | sha256sum` = `8baea9f6…400ddf6a`, equal to §2's line. Every run below follows §2.5–§2.8 as frozen;
the only differences are execution details, listed in §3.2.

### 3.1 Environment

- **Node:** `pc96` (local, `node0.jason92-325405…`), x86_64, 2 sockets × 8 cores × 2 threads = 32 CPUs, 125 GiB RAM
  (≈ 122 GiB available at start), 8 GiB swap (kept from the node by `MemorySwapMax=0`), `/mydata` 572 GiB free, kernel
  5.15.0-198-generic, OpenJDK 11.0.33. `pgrep -af CassandraDaemon` at start: nothing running. Other agent sessions
  (Claude CLI processes, an `ssh` to another node) ran on the host the whole time. Load average stayed at ≈ 2–11.
- **Build:** a one-time copy of `/mydata/s4/cassandra-base` (`bin conf lib build pylib tools`, built jar
  `build/apache-cassandra-5.0.9-SNAPSHOT.jar`) to `/mydata/s4/u11-w4/cassandra`. `ant` was not run.
- **Per run:** a fresh `/mydata/s4/u11-w4/<label>/` holding a `conf/` copy and its own data, commitlog, hints,
  saved_caches and logs directories. The `conf/` copy changes only E1 (cluster name, ports 7610/7611/9642/JMX 7699,
  directories) and E3 (the GC-log line added to `jvm-server.options`). The diff is in `logs/<label>/conf.diff`.
  Launch: `systemd-run --user --scope -p MemorySwapMax=0 taskset -c 24-31 bin/cassandra -f`, with
  `MAX_HEAP_SIZE=<H>`, `CASSANDRA_HEAPDUMP_DIR=<run>`, `JVM_EXTRA_OPTS=-Dcassandra.printHeapHistogramOnOutOfMemoryError=true`.
  The client and poller ran on CPUs 22,23.
- **Resolved values, the same in every run** (from `system_views.settings`, `logs/<label>/settings.json`):
  - `concurrent_writes` 32, `range_tombstone_list_growth_factor` 1.5, `initial_range_tombstone_list_allocation_size` 1;
  - `memtable_cleanup_threshold` 0.33333334, `memtable_flush_writers` 2, `memtable_allocation_type` heap_buffers;
  - `max_mutation_size` 16384 KiB, `write_request_timeout` 2000 ms, `native_transport_timeout` 12 s, `key_cache_size` 100 MiB;
  - `native_transport_max_request_data_in_flight` 214748364 B (the per-IP limit 53687091 B) at 2 GiB;
  - `memtable_heap_space` = heap/4: 128 MiB at 512 MiB, 512 MiB at 2 GiB, 2048 MiB at 8 GiB.
- **JVM** (from the `JVM Arguments` line in `system.log`):
  - `-Xms = -Xmx = H`, G1 with 16 MiB regions, `G1NewSizePercent=50`, `MaxTenuringThreshold=2`, `MaxGCPauseMillis=300`,
    IHOP 70, `AlwaysPreTouch`;
  - resolved **`-XX:MaxDirectMemorySize=15872M`** (not the 7,936M §2.3 expected; direct memory is not a domain here);
  - `-XX:ParallelGCThreads=32 -XX:ConcGCThreads=32`: `cassandra-env.sh` sets these from the host's core count, so they
    are 32 even though `taskset` gives the JVM 8 CPUs;
  - `-XX:OnOutOfMemoryError=kill -9 %p`, `HeapDumpOnOutOfMemoryError`.
- **Harness** (`harness/`):
  - `run.sh` runs one run end to end;
  - `seq.sh` runs the arms one after another (it would not start a run after 17:35);
  - `client.py` is the bundled Python driver 3.29.0, protocol 4, whitelist 127.0.0.1, `FallthroughRetryPolicy`, CL ONE,
    a 30 s client timeout, token metadata off;
  - `Poll.java` reads over JMX every 1 s: the G1 pools, Old Gen collection usage, the GC MXBeans, the table's
    `MemtableOnHeapDataSize` and `MemtableSwitchCount`, `AllMemtablesOnHeapDataSize`, and MutationStage
    Active/Pending/Completed;
  - `analyze.py` builds the per-run JSON; `excerpt.sh` copies the excerpts.
  - Excerpts are in `logs/<label>/`: `analysis.json`, `driver.log`, `fill.json`, `write.json`, `settings.json`,
    `conf.diff`, `persec.csv`, `poll-every10s.txt`, `gc-excerpt.txt`, and the first 25 lines of each histogram.
    Full logs are on `pc96` in `/mydata/s4/u11-w4/<label>/logs/` and `/mydata/s4/u11-w4/<label>/hist/`.
- **Shakedown** (`shake`, not a reading): T at 2 GiB with n₀ = 20.5 k and 2,000 W writes. It acknowledged them all in
  1 s. The shakedown showed that `bin/cassandra -p` does not write the pid file in this setup, so `run.sh` was fixed to
  find the PID from the process list.

### 3.2 Deviations from §2 (dated 2026-11-18, stage 2; none changes a capacity setting, budget, workload or arm)

1. **Run directory.** `/mydata/s4/u11-w4/` instead of `/mydata/s4/u11/`, as the stage-2 task instructed.
2. **Resolved values that differ from §2.3's expectations.** These are recorded, not changed:
   - `MaxDirectMemorySize` is 15,872M, not 7,936M;
   - `ParallelGCThreads` and `ConcGCThreads` are 32, not 8.
3. **Arm C's fill.** It reached the same K target (145.2–145.4 MiB counted) with 485.5–486.5 k tombstones at
   ≤ 500 per partition, not ≈ 300 k. At small n a tombstone is counted at ≈ 300 B, not ≈ 510 B. So C's retained list
   holds more tombstones than T's (L0 185 MiB vs 139.5 MiB), which makes C the heavier control on D2.
4. **B05's W.** It stopped on its frozen rule "`MemtableSwitchCount` rises" after 179 s, at 17,243 acknowledged.
   §2.4's "≤ 20,000 more keeps n in [0.85, 0.92] n_max" holds only at ≥ 2 GiB; at 512 MiB, 20,000 writes is +26 % of
   n₀ = 75.5 k. The flush came at n ≈ 92.7 k, i.e. the cleaner trigger working as designed. The service-loss window
   (§3.4) lies before the flush.
5. **The 1 s poll's eden+survivor+old sum is not atomic.** It reads up to 2.7 GiB on a 2 GiB heap. Heap peaks are
   therefore taken from the GC log and Old Gen collection usage, not from that sum.

### 3.3 Runs (in order; every one from a clean start: fresh directory, fresh JVM)

The "W stop" column is why W ended: `maxsec` = 300 s, `count` = 20,000 acknowledged (the client's last callbacks add
up to 63 more), `switch` = a memtable switch. "Full-GC after" is the heap right after each `Pause Full` in W (the live
heap, with the writers' in-flight copies held at the safepoint), given as min / median / max. **STW60** is the largest
60 s window's share of wall time in STW pauses. **A** is MutationStage ActiveTasks (mean over W; max 32 in every
T, D and B run).

| Run (NY time) | H | Fill: tombstones / max n per partition / K | W stop · acked / timeouts / errors · seconds | ack rate /s · p50 / p99 ms | A mean · pending max | Pauses in W: young / full | Full-GC after (MiB) | Max post-GC heap (MiB) | STW60 | L0 → L1 live (MiB) | OOM |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 13:57 | 2 GiB | 299,000 / 299,000 / 145.2 MiB | maxsec · 9,409 / 3,161 / 0 · 300 | 31.3 · 1,271 / 2,353 | 32.0 · 56 | 2,182 / 467 | 186 / 417 / 482 | 2,008 | 0.787 | 139.3 → 148.3 | none |
| T2 14:07 | 2 GiB | 300,000 / 300,000 / 145.7 MiB | maxsec · 9,395 / 3,181 / 0 · 300 | 31.3 · 1,269 / 2,328 | 32.0 · 60 | 2,190 / 468 | 347 / 417 / 494 | 2,011 | 0.793 | 139.6 → 148.0 | none |
| T3 14:16 | 2 GiB | 300,000 / 300,000 / 145.7 MiB | maxsec · 9,506 / 3,116 / 0 · 300 | 31.6 · 1,253 / 2,393 | 32.0 · 57 | 2,190 / 476 | 320 / 418 / 479 | 2,009 | 0.792 | 139.5 → 147.8 | none |
| C1 14:25 | 2 GiB | 485,500 / 500 / 145.2 MiB | count · 20,063 / 0 / 0 · 3.0 | 6,670 · 7 / 20 | 0.0 · 0 | 0 / 0 | — | — | 0.000 | 184.9 → 195.5 | none |
| C2 14:31 | 2 GiB | 486,500 / 500 / 145.4 MiB | count · 20,063 / 0 / 0 · 3.0 | 6,664 · 7 / 19 | 0.7 · 1 | 0 / 0 | — | — | 0.000 | 185.0 → 195.8 | none |
| C3 14:36 | 2 GiB | 486,500 / 500 / 145.4 MiB | count · 20,063 / 0 / 0 · 3.0 | 6,667 · 7 / 19 | 0.0 · 0 | 0 / 0 | — | — | 0.000 | 185.1 → 196.6 | none |
| I1 14:42 | 2 GiB | 299,500 / 299,500 / 145.4 MiB | count · 20,063 / 0 / 0 · 78.1 | 256.9 · 245 / 343 | 1.0 · 63 | 258 / 0 | — | 166 | 0.103 | 139.4 → 149.3 | none |
| I2 14:47 | 2 GiB | 300,500 / 300,500 / 145.9 MiB | count · 20,063 / 0 / 0 · 78.1 | 256.9 · 247 / 323 | 1.0 · 63 | 261 / 0 | — | 170 | 0.104 | 139.6 → 149.6 | none |
| I3 14:52 | 2 GiB | 300,500 / 300,500 / 145.9 MiB | count · 20,063 / 0 / 0 · 78.1 | 256.9 · 246 / 294 | 1.0 · 63 | 260 / 0 | — | 173 | 0.105 | 139.9 → 149.5 | none |
| D1 14:58 | 2 GiB | 300,000 / 300,000 / 145.7 MiB | maxsec · 9,323 / 3,113 / 0 · 300 | 31.0 · 1,275 / 2,410 | 32.0 · 59 | 2,141 / 476 (14 forced by histograms) | 337 / 417 / 489 | 2,008 | 0.791 | 139.6 → 148.7 | none |
| B8 15:07 | 8 GiB | 1,194,500 / 1,194,500 / 580.7 MiB | maxsec · **52** / **8,810** / 0 · 300 | 0.2 · 1,374 / 26,867 | 32.0 · **6,434** | 1,083 / 156 (82 humongous-allocation) | 1,126 / 1,373 / 1,584 | 8,067 | 0.648 | 374.7 → 1,336.8 | none |
| B05 15:25 | 512 MiB | 75,500 / 75,500 / 36.5 MiB | switch · 17,243 / 1,189 / 0 · 179 | 96.2 · 431 / 2,021 | 31.8 · 46 | 1,709 / 559 | 67 / 160 / 188 | 491 | **0.920** | 81.5 → 67.8 (after the flush) | none |

Readings by prediction (§2.7):

1. **F (fill).** Every arm reached n₀ with `MemtableSwitchCount` 0, and the T/I/D/B fills reached the predicted n:
   - 2 GiB: n = 299–300.5 k (predicted 298–323 k), K/n = 509 B (predicted 510 ± 5 %);
   - 8 GiB: n = 1.19 M (predicted 1.19–1.29 M), K/n = 510 B;
   - 512 MiB: n = 75.5 k (predicted 74–81 k), K/n = 507 B.

   With one request in flight the fill ran at ≈ 20 batches/s up to n ≈ 300 k (153 s). At 8 GiB it slowed with n
   (701 s), the O(n) copy of every batch.
2. **T/W at 2 GiB (×3) and D.** No OOM in 4/4. A = 32 for the whole of W (`active_ge30_frac` 1.0) with 56–60 pending.
   - **Rate and timeouts.** 31.0–31.6 acknowledged/s, the low end of the predicted 50–200. A further ≈ 3,100 per run
     (25 %) timed out at the 2 s `write_request_timeout`, p50 1.27 s. K grew by 6.26–6.35 MB per run ≈ 12.4 k
     tombstones applied, i.e. the ≈ 3,000 timed-out writes were applied late.
   - **GC.** 467–476 `Pause Full (G1 Evacuation Pause)` per 300 s, after "To-space exhausted" young pauses (heap at
     2,008–2,011 MiB before them). The full GCs brought the heap back to 417 MiB median, 479–494 MiB max. That is the
     **peak live ≈ 0.24 × H**, below the predicted 0.30–0.40 × H. **STW60 0.787–0.793**, below the 90 %
     service-loss criterion, as predicted ("high but below").
   - **Arm D (U independent of K).** 14 histograms, one every 20 s of W:
     - U_D1 = (ClusteringBound[] + long[] + int[]) − L0 = **219–302 MiB, mean 266 MiB**;
     - over the same 20 s steps K moved by ≈ 0.4 MB, and `BufferClusteringBound` (the retained bounds) by ≈ +41 KB (≈ 850 tombstones) per step;
     - one in-flight copy at n ≈ 300–310 k is 50 B × n ≈ 15 MB (14.5 MiB), so ≈ 15–21 copies were live at each
       histogram of the 32 active writers;
     - this is the low half of the predicted 0.25–0.52 GB (238–496 MiB);
     - at L1 (5 s after W) the arrays are back to L0 + 0.4 MiB, so the copies are transient and not retained.
3. **C (×3).** No OOM in 3/3, as predicted. 20,000 writes over 1,000 partitions finished in 3.0 s (6,664–6,670/s,
   p99 ≤ 20 ms), with no GC pause in W, A sampled 0–2 (the writes finish within a poll interval) and U_D1 at L1 = 3.4 MiB.
   So with the same counter trajectory and writer count, n ≈ 500 per partition gives none of T's GC load.
4. **I (×3, `setconcurrency MutationStage 1`, `getconcurrency` = 0/1 in each).**
   - A = 1 and pending 63 throughout W, so the copies were bounded to one.
   - 20,000 writes completed in 78 s at **256.9/s (8.2 × T's rate)**, with **0 timeouts** and p50 245 ms.
   - **0 full GCs**; post-GC heap max 166–173 MiB; STW60 0.103–0.105.
   - The intervention removes the thrash and does not reduce useful work. T's 32 writers mostly copy and fail their CAS.
5. **B8 (8 GiB, T ×1).** **No OOM.** A = 32.
   - **GC.** The young pauses ran with the heap at 8,027–8,080 MiB and up to 225 humongous regions (3.5 GiB) before a
     pause: each copy's arrays (CB[] 2 × 7.2 MB, long[] 14.3 MB, int[] 7.2 MB at n = 1.19–1.2 M) are G1 humongous
     objects. There were 156 full GCs (82 "Humongous Allocation", 74 "Evacuation"), 0.5–0.59 s each.
   - **Live heap.** Full-GC after 1,126–1,584 MiB (median 1,373) = **peak live ≈ 0.19 × H** (predicted 0.42–0.55 × H
     counting region rounding).
   - **STW60 0.648.** The service-loss criterion was not met.
   - **Throughput.** It collapsed: **52 acknowledged and 8,810 timed out (99.4 %)** in 300 s. K grew by 1.2 MB, so
     ≈ 2,350 writes were applied, almost all after their 2 s timeout. MutationStage pending reached 6,434.
   - **L1** (5 s after the client stopped, queue still draining): U_D1 = **949 MiB** of copy arrays, a second direct
     reading of D1 (≈ 16 copies of ≈ 60 MB).
6. **B05 (512 MiB, T ×1).** **No OOM.** A = 31.8.
   - **GC.** 559 full GCs in 179 s; full-GC after median 160, max 188 MiB = **peak live ≈ 0.37 × H** (predicted 0.40–0.55).
   - **STW60 = 0.920.** The 60 s windows starting 20–120 s into W are all ≥ 0.90 (0.906–0.919), i.e. ≈ 100 s above the
     criterion, before the memtable switch at 179 s. So the **default service-loss criterion was met once**.
   - **Throughput.** The node still acknowledged 50–86 writes/s in that window, with 4–9 timeouts/s (15 s buckets, `persec.csv`).
   - After the flush (n reset), the last 15 s acknowledged 6,471 writes.

### 3.4 V1–V7 table (against the frozen endpoints)

| | OOM endpoint | GC service-loss endpoint (≥ 90 % STW over ≥ 60 s) |
|---|---|---|
| V1 repetition | 0/6 (T1–T3, D1 at 2 GiB; B8; B05) | 2 GiB 0/4 (STW60 0.79); 8 GiB 0/1 (0.65); **512 MiB 1/1** (0.92) — not repeated |
| V2 matched control | C ×3 at 2 GiB: no OOM, STW60 0 | C not run at 512 MiB (frozen B rule runs C/I at another heap only after an OOM there) |
| V3 measurement | U_D1 by histogram (arm D, B8 L1) independent of K (K moved < 1 MB per 20 s) | same |
| V4 intervention | I ×3 at 2 GiB: 0 full GCs, STW60 0.10, rate 8.2 × T, 0 timeouts | not run at 512 MiB |
| V5 initiating failure | no OOM to record | GC log over the B05 window (`logs/B05-512M/gc-excerpt.txt`, full log on the node) |
| V6 default constraints | met (every constraint at its shipped default, §3.1) | met |
| V7 acceptable budget | 512 MiB, 2 GiB, 8 GiB heaps (≥ 512 MiB, no container limit) | 512 MiB = the minimum acceptable heap |

**Clean-up.** Each run killed its node and poller by PID and deleted its `data/`, `commitlog/`, `hints/`, `cdc_raw/` and
`saved_caches/`. There were no OOMs, so no `.hprof` files. After the last run (15:31) neither `CassandraDaemon` nor
`Poll` was running, and nothing that this session started remained.

## 4. Conclusion (stage 2)

**Verdict: `retry`.** Detail status: `candidate` (unprotected accumulation · multiplicity; conditions `deployment`: all
constraints at defaults, heaps ≥ 512 MiB, deviations environment/instrumentation only).

**Why.**
- The claimed holder is real and unprotected. Every write attempt on a hot partition copies and grows the whole
  RangeTombstoneList outside the memtable counter.
- The copies were measured directly. At 2 GiB they reached 219–302 MiB (≈ 15–21 copies of 15 MB) while K moved by
  < 1 MB. At 8 GiB, 949 MiB was measured at L1.
- They drive G1 into continuous evacuation failure and full GCs: 467–476 full GCs per 300 s at 2 GiB, STW 79 %,
  25 % of writes timing out; at 8 GiB, 99.4 % of writes time out.
- They are bounded by the 32 MutationStage permits, and that bound held. The live heap at the full GCs stayed at
  0.24 × H (2 GiB), 0.19 × H (8 GiB) and 0.37 × H (512 MiB), all below §2.4's ceiling. **No heap OOM in 0/6 runs.**
- So the OOM endpoint behaves as a false positive would. But the frozen mapping (§2.7) and the playbook treat a GC
  service loss without OOM as **retry**. B05 met the default service-loss criterion (STW ≥ 90 % for ≈ 100 s at the
  512 MiB minimum budget), but once only, without C or I at that heap. That makes it a gap, not even `verified-gap`.
- The causal link is clear at 2 GiB:
  - arm C (n ≈ 500 per partition, same K, same writers) has no GC load;
  - arm I (one writer) has 0 full GCs and 8 × the throughput.

  The thrash is the multiplicity of D1, not D2.

**Limits of attribution.**
- The 8 GiB throughput collapse is partly CPU: 32 threads each copy ≈ 60 MB per attempt on 8 CPUs (the O(n) cost of
  CASSANDRA-21492). It is not service loss under the STW criterion (0.65).
- `ParallelGCThreads=32` on 8 CPUs (resolved by `cassandra-env.sh`) may lengthen the pauses.
- C's retained list held more tombstones than T's (deviation 3), which only makes C the stricter control.

**What a better design should change (retry).**
- Target the service-loss endpoint, not OOM. At 512 MiB (and 768 MiB / 1 GiB to search upward), run T, C and I ×3
  each with a W that stays below the flush: fill fraction 0.75 and ≤ 5,000 writes, or stop W at 150 s.
- Predefine the window (≥ 60 s of W before any switch), so the B05 result can become `verified-gap · service-loss · deployment`.
- Optionally add an availability criterion, e.g. the share of writes timed out, for the 8 GiB collapse, with I at 8 GiB.
- A heap OOM at defaults looks unreachable for this holder alone: the live share was ≤ 0.37 × H in every run. Only a
  stacked design (S) with a second heap holder that grows during the thrash could reach it, and the 6,434 queued
  mutations at 8 GiB are too small for that.
