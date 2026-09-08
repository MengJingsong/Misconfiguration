# memtable_heap_space — Pair 02 · Summary

> **Codepath:** [memtable_heap_space-02-codepath.md](memtable_heap_space-02-codepath.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## Identity

| Field | Content |
|-------|---------|
| **Entry Point ID** | MEMTABLE_HEAP_SPACE |
| **Name** | memtable_heap_space |
| **Type** | Configuration (`cassandra.yaml`) |
| **Declaration Location** | `Config.java:187` (`DataStorageSpec.IntMebibytesBound memtable_heap_space`) |
| **Default Value** | ¼ of max heap — `Runtime.getRuntime().maxMemory() / (4 * 1048576)` MiB (`DatabaseDescriptor.java:586-587`) |
| **Value Type / Size** | `int` mebibytes; converted to `long` bytes via `<< 20` (→ `SubPool.limit`) |
| **Description** | Same budget as pair 01, but here it acts as a **hard cap** on outstanding allocation: a request that would exceed `limit` is refused and the writer blocks. |
| **Restriction Location** | `MemtablePool.SubPool.tryAllocate():151-161` (hard cap: `allocated + size > limit → false`) |
| **Pair** | 02 of 02 |

**Restriction character:** **Hard limit / back-pressure.** Distinct from pair 01
(which flushes): here the allocating write thread is **blocked** on a wait queue
until memory is released, unless a bypass applies.

## Key Decision Points

1. **read/store:** same as pair 01 — `SubPool.limit` (`MemtablePool.SubPool.<init>():119`)
2. **allocate entry:** `MemtableAllocator.SubAllocator.allocate():169`
3. **hard check:** `SubPool.tryAllocate():156` (`(cur = allocated) + size > limit → return false`)
4. **block:** `SubAllocator.allocate():185,195` (register on `hasRoom`, `signal.awaitThrowUncheckedOnInterrupt()`)
5. **bypass:** `SubAllocator.allocate():180-183` (`opGroup.isBlocking()` → `allocated(size)` regardless of limit)
6. **bypass trigger:** `ColumnFamilyStore.java:1236-1238` (`writeBarrier.markBlocking()` during flush → sets `isBlocking=true` for pre-barrier writes, `OpOrder.java:319-321,333-335`)
7. **overshoot (post-insert):** `SkipListMemtable.java:122-125` (row/partition overhead charged *after* insert → "can overshoot our declared limit")

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | `SubPool.tryAllocate():156` (pre-allocation check inside the CAS loop) |
| **Action on Breach** | Writer registers on `hasRoom` `WaitQueue` and blocks (`allocate():185,195`) until `SubPool.released():192-197` calls `hasRoom.signalAll():196`. **Two designed overshoot paths let it exceed the limit:** (1) if `opGroup.isBlocking()` — set by `writeBarrier.markBlocking()` during flush (`ColumnFamilyStore.java:1236-1238`) — `allocated(size)` books the memory anyway (`allocate():180-183`); (2) row/partition overhead is charged *after* insert (`SkipListMemtable.java:122-125`), so it can push past `limit`. |

## Failure Mode Analysis

| Mode | Status | Notes |
|------|--------|-------|
| **Proxy Match** | ⚠ | `allocated` is an **estimated** footprint (data + metadata via `unsharedHeapSize()` / `ROW_OVERHEAD_HEAP_SIZE`; `BTreePartitionUpdater.java:175-182`, `SkipListMemtable.java:124-125`), not measured JVM heap — same proxy gap as pair 01. |
| **Enforcement Point** | ✗ | `tryAllocate` is pre-allocation (good), **but** the limit is soft: (a) `opGroup.isBlocking()` — set by flush's `writeBarrier.markBlocking()` (`ColumnFamilyStore.java:1236-1238`) — books memory over the limit via `allocate():180-183` → `adjustAllocated()`, which the source states “bypass[es] any limits” (`MemtablePool.java:163-167`); (b) row/partition overhead is charged **after** insert (`SkipListMemtable.java:122-125`), overshooting by design. The enforced invariant is “`allocated ≤ limit` in steady state, with bounded transient overshoots,” not a hard cap. |
| **Default State** | ✓ | Enabled by default (same limit as pair 01). |

## Related / Dependent Constraints

- `memtable_cleanup_threshold` — in practice pair 01 should flush and free memory before this hard cap is hit; the hard cap is the last-resort back-pressure.
- `memtable_allocation_type` — same `limit` applies across pool implementations.
- OpOrder / write path — `opGroup.isBlocking()` state determines whether the bypass fires.

## Bypass Potential (Target 3 seed)

- **Blocking-op bypass (primary):** during flush, `writeBarrier.markBlocking()`
  (`ColumnFamilyStore.java:1236-1238`) sets `isBlocking=true` for pre-barrier
  writes; those take the force branch `allocate():180-183` and book bytes **over
  the limit** (deadlock avoidance — the flush needs those writes to drain before
  it can reclaim their memory). A workload that keeps ops in the blocking state
  pushes usage past `memtable_heap_space`. Overshoot here is bounded by
  pre-barrier in-flight write volume (concurrency × size).
- **Post-insert overhead overshoot:** partition/row structural overhead is
  charged only *after* the row is inserted (`SkipListMemtable.java:122-125`), so
  `allocated` can cross `limit` before the charge lands.
- **Estimate-fidelity divergence:** `allocated` counts an *estimated* footprint
  (see Proxy Match); crafting data whose true retained size exceeds its
  `unsharedHeapSize` estimate lets real heap exceed `allocated` while "under
  limit." Combined-overshoot / OOM reachability is an empirical chaos question.

## Verification

| Field | Content |
|-------|---------|
| **Status** | verified (static trace) |
| **Verified By / Date** | Claude + Jingsong, 2026-09-08 |

## Notes

- The two pairs share steps 1–9 of the code path (declaration → `SubPool.limit`); they diverge at how `limit` is consumed (`needsCleaning` vs `tryAllocate`).
- `used()`/`allocated` is a `volatile long` updated via `AtomicLongFieldUpdater`; the check is a CAS loop, so it is race-free for the accounting but not for the async flush timing.
- **What `allocated` measures:** estimated footprint = cloned data + explicit structural overhead (`SkipListMemtable.java:124-125`; `BTreePartitionUpdater onAllocatedOnHeap → onHeap().adjust()`, `:132-182`). Same accounting as pair 01 (repeated here so this pair stands alone).
- `isBlocking` is not a client input — it is set by the flush write barrier (`ColumnFamilyStore.java:1238`), so the bypass is reachable by driving the node into sustained flushing.
