# file_cache_size — Pair 02 · Summary

> **Codepath:** [file_cache_size-02-codepath.md](file_cache_size-02-codepath.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## Identity

| Field | Content |
|-------|---------|
| **Entry Point ID** | FILE_CACHE_SIZE |
| **Name** | file_cache_size |
| **Type** | Configuration (feeding a hardcoded allocator threshold) |
| **Declaration Location** | [`Config.java:496-497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L496-L497) — `file_cache_size` field |
| **Default Value** | auto-sized: `min(512 MiB, maxMemory / 4)` |
| **Value Type / Size** | `long` bytes (`memoryUsageThreshold` in `BufferPool`), derived from `DataStorageSpec.IntMebibytesBound` |
| **Description** | Caps the physical off-heap memory the `chunk-cache` named `BufferPool` instance may allocate in pooled macro-chunks |
| **Restriction Location** | `BufferPool.GlobalPool.allocateMoreChunks():` (memory-threshold check before allocating a new macro-chunk) |
| **Pair** | 02 of 2 |

**Restriction character:** Hard cap on *pooled* allocation — but with an unpooled fallback path that is **not** bounded by this threshold at all.

## Key Decision Points

1. **read/lookup:** [`DatabaseDescriptor.java:3784-3793`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3784-L3793) `getFileCacheSizeInMiB()`
2. **derive/store:** `BufferPools.java` — `FILE_MEMORY_USAGE_THRESHOLD = getFileCacheSizeInMiB() * 1024L * 1024L` (static init); passed into `new BufferPool("chunk-cache", FILE_MEMORY_USAGE_THRESHOLD, true)`, stored as `BufferPool.memoryUsageThreshold`
3. **submission:** `ChunkCache.load()` → `bufferPool.get(size, bufferType)` → `LocalPool.get()` → `LocalPool.tryGetInternal()` → `LocalPool.addChunkFromParent()` → `GlobalPool.get()`
4. **check:** `GlobalPool.allocateMoreChunks()` — compares `memoryAllocated.get() + MACRO_CHUNK_SIZE` against `memoryUsageThreshold`
5. **action (pooled path):** if over threshold, returns `null` — no macro-chunk allocated, no exception
6. **action (fallback / bypass):** `LocalPool.get()` catches the pooled-allocation miss and calls `allocate(size, BufferType.OFF_HEAP)`, which does a **raw, unpooled** `ByteBuffer.allocateDirect(size)` — tracked only in `overflowMemoryUsage`, which has no cap

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | `BufferPool.GlobalPool.allocateMoreChunks()` — `if (cur + MACRO_CHUNK_SIZE > memoryUsageThreshold) return null;` |
| **Action on Breach** | Pooled allocation is refused (returns `null`); caller (`LocalPool.get()`) silently falls back to an **unpooled** direct allocation that bypasses `memoryUsageThreshold` entirely |

## Failure Mode Analysis

| Mode | Status (✓/✗/⚠) | Notes |
|------|-----------------|-------|
| **Proxy Match** | ✓ | `memoryAllocated` tracks actual off-heap macro-chunk bytes allocated by this pool — a direct measure of the resource being constrained (for the pooled path). |
| **Enforcement Point** | ✗ | The check runs *before* the pooled allocation (good), but on refusal the caller does not block, queue, or reject — it silently allocates the same size **unpooled**, via `ByteBuffer.allocateDirect()`, with zero connection to `memoryUsageThreshold`. The hard cap only bounds the pooled portion of usage; total off-heap usage for this subsystem (`sizeInBytes() = memoryAllocated + overflowMemoryUsage`) is unbounded. |
| **Default State** | ✓ | Threshold is always positive by default (same auto-sizing as pair 01, but without the 32 MiB reservation), so the pooled cap is active out of the box — it's the fallback path's total absence of a cap that is the finding, not a disabled default. |

## Related / Dependent Constraints

- Same source config as [[file_cache_size-01]] (`ChunkCache`'s Caffeine `maximumWeight`), but this `BufferPool` threshold uses the **un-reduced** `file_cache_size` (no 32 MiB subtraction) — so nominally this hard cap sits 32 MiB *above* the logical cache's soft target, meaning the logical cache should, in the steady state, stay comfortably under this pool's ceiling. The finding here is what happens when that assumption breaks (bursty/concurrent misses, large individual chunk sizes near `NORMAL_CHUNK_SIZE`, or many small `LocalPool`s each holding partially-used chunks).
- Shares its allocator with any other in-process caller that requests off-heap buffers from this named pool — but in 5.0.9, `BufferPools.forChunkCache()` is used exclusively by `ChunkCache`, so in practice this pool's usage is driven only by chunk-cache activity.
- Distinct from `BufferPools.NETWORKING_POOL` (backs `networking_cache_size`), which has the same architecture and thus the same class of bypass — out of scope for this pair but worth flagging for a future pair under a `networking_cache_size` entry point.

## Bypass Potential (Target 3 seed)

- **Primary bypass:** once `memoryAllocated` for the chunk-cache pool reaches `memoryUsageThreshold`, every subsequent buffer request that cannot be served from already-owned local/global chunks falls through to an unpooled `ByteBuffer.allocateDirect()` call with no size or aggregate limit. A workload that keeps missing the pool (e.g., sustained wide scans across many distinct SSTables, chunk sizes that fragment the 128 KiB `NORMAL_CHUNK_SIZE` pool) can drive off-heap usage well past `file_cache_size` indefinitely, bounded only by `-XX:MaxDirectMemorySize` (or physical RAM if unset) — this is a direct resource-exhaustion vector for Target 3.
- **Compounding with pair 01:** pair 01's post-hoc eviction only returns buffers to *this* `BufferPool`; if the pool is already saturated and buffers are flowing through the unpooled fallback, evicted buffers don't relieve fallback pressure until the caller matches `put()` calls correctly (unpooled buffers are freed via `FileUtils.clean()`, not returned to the pool) — so the two constraints can appear "healthy" independently while the aggregate off-heap footprint keeps growing.
- **Silent failure mode:** the pooled-allocation refusal is logged only via `noSpamLogger.info(...)` (rate-limited to once per 15 minutes) — an operator watching only `memoryAllocated`/pool metrics would not see the unpooled overflow growing unless they specifically check `overflowMemoryInBytes()` / `sizeInBytes()`.

## Verification

| Field | Content |
|--------|---------|
| **Status** | verified |
| **Verified By / Date** | Jingsong, 2026-09-10 (traced and line-checked against local `cassandra-5.0.9` clone) |
| **Notes** | Confirmed via `BufferPool.java`: `allocate()` (on-heap and unpooled off-heap path) only calls `updateOverflowMemoryUsage(size)`, which has no comparison against `memoryUsageThreshold` anywhere in the class. |

---

## Notes

- Module: `org.apache.cassandra.utils.memory` (BufferPool / GlobalPool / LocalPool / Chunk).
- The `BufferPool` class is generic (used for both the chunk-cache pool and the networking pool); this pair documents its behavior specifically as instantiated for `file_cache_size` via `BufferPools.forChunkCache()`.
