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

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | `SubPool.tryAllocate():156` (pre-allocation check inside the CAS loop) |
| **Action on Breach** | Writer registers on `hasRoom` `WaitQueue` and blocks (`allocate():185,195`) until `SubPool.released():192-197` calls `hasRoom.signalAll():196`. **Exception:** if `opGroup.isBlocking()`, `allocated(size)` books the memory anyway (`allocate():180-183`). |

## Failure Mode Analysis

| Mode | Status | Notes |
|------|--------|-------|
| **Proxy Match** | ⚠ | Same proxy as pair 01 — allocator-tracked bytes, not JVM heap. |
| **Enforcement Point** | ✗ | `tryAllocate` itself is pre-allocation (good), **but** two paths bypass it: (a) `opGroup.isBlocking()` books memory over the limit (`:180-183`); (b) `SubPool.allocated()` uses `adjustAllocated()` which the source states “bypass[es] any limits” (`:167-175`). |
| **Default State** | ✓ | Enabled by default (same limit as pair 01). |

## Related / Dependent Constraints

- `memtable_cleanup_threshold` — in practice pair 01 should flush and free memory before this hard cap is hit; the hard cap is the last-resort back-pressure.
- `memtable_allocation_type` — same `limit` applies across pool implementations.
- OpOrder / write path — `opGroup.isBlocking()` state determines whether the bypass fires.

## Bypass Potential (Target 3 seed)

- **Blocking-op bypass (primary):** `allocate():180-183` — when the op group is
  already blocking, allocation is booked via `allocated(size)` **over the
  limit**. A workload that drives ops into the blocking state can push on-heap
  memtable usage past `memtable_heap_space`.
- **Retroactive accounting:** `adjustAllocated()` (`:167-175`) is explicitly
  limit-bypassing; any caller routing through `allocated()`/`allocatedRetroactively`
  adds bytes without the `tryAllocate` gate.

## Verification

| Field | Content |
|-------|---------|
| **Status** | verified (static trace) |
| **CodeQL Pattern** | candidate: if-check on `tryAllocate` return controlling allocation |
| **Verified By / Date** | Claude + Jingsong, 2026-09-08 |

## Notes

- The two pairs share steps 1–9 of the code path (declaration → `SubPool.limit`); they diverge at how `limit` is consumed (`needsCleaning` vs `tryAllocate`).
- `used()`/`allocated` is a `volatile long` updated via `AtomicLongFieldUpdater`; the check is a CAS loop, so it is race-free for the accounting but not for the async flush timing.
