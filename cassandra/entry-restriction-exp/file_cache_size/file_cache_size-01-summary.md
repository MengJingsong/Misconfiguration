# file_cache_size — Pair 01 · Summary

> **Codepath:** [file_cache_size-01-codepath.md](file_cache_size-01-codepath.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## Identity

| Field | Content |
|-------|---------|
| **Entry Point ID** | FILE_CACHE_SIZE |
| **Name** | file_cache_size |
| **Type** | Configuration |
| **Declaration Location** | [`Config.java:496-497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L496-L497) — `file_cache_size` field |
| **Default Value** | auto-sized: `min(512 MiB, maxMemory / 4)` (set at [`DatabaseDescriptor.java:576-577`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L576-L577) when unset) |
| **Value Type / Size** | `DataStorageSpec.IntMebibytesBound` |
| **Description** | Caps the logical size (weighted byte count) of the `ChunkCache`, the off-heap cache of decompressed/decrypted SSTable chunks read from disk |
| **Restriction Location** | `ChunkCache.<init>():151-157` (Caffeine `maximumWeight`) |
| **Pair** | 01 of 2 |

**Restriction character:** Soft, approximate cap on cached-chunk weight — a Caffeine `LoadingCache` eviction policy, not a hard allocation block. New chunks always load; the cache evicts older entries afterward to trend back toward the weight limit.

## Key Decision Points

1. **read/lookup:** [`DatabaseDescriptor.java:3784-3793`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3784-L3793) `getFileCacheSizeInMiB()` — reads `conf.file_cache_size`
2. **derive:** [`ChunkCache.java:49-50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L49-L50) — `cacheSize = (getFileCacheSizeInMiB() - RESERVED_POOL_SPACE_IN_MiB) * 1MiB` (static init, computed once at class load)
3. **store/configure:** [`ChunkCache.java:151-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L151-L157) — Caffeine builder configured with `maximumWeight(cacheSize)` and a `weigher` that returns each buffer's byte capacity
4. **load (unconditional):** [`ChunkCache.java:160-175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L160-L175) — `load(Key)` always fetches and caches a new chunk on a miss, regardless of current weight
5. **check/evict (post-hoc, async):** internal to Caffeine — after each cache write, Caffeine schedules eviction to bring weighted size back under `maximumWeight`; here `.executor(ImmediateExecutor.INSTANCE)` runs it synchronously on the calling thread, but only *after* the triggering load has already completed
6. **action:** `onRemoval()` at [`ChunkCache.java:177-181`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L177-L181) — evicted buffer is released back to the underlying `BufferPool`

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | [`ChunkCache.java:151-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L151-L157) (Caffeine `maximumWeight` policy), triggered post-load via Caffeine's internal eviction on every cache write |
| **Action on Breach** | Caffeine evicts the least-valuable entries (approximate LRU/frequency) until weighted size is back under the cap; evicted `Buffer.release()` returns the buffer to `BufferPool` |

## Failure Mode Analysis

| Mode | Status (✓/✗/⚠) | Notes |
|------|-----------------|-------|
| **Proxy Match** | ⚠ | Weigher measures `ByteBuffer.capacity()` per cached chunk — a fairly direct proxy for the *logical* cache footprint, but it does not account for the underlying `BufferPool` slab/chunk overhead (128 KiB chunks, macro-chunk fragmentation), so actual off-heap usage can exceed the weighted total. |
| **Enforcement Point** | ✗ | `load()` is unconditional — a new chunk is always fetched and inserted *before* any eviction runs. Eviction is a cleanup step after the resource is already used, not a gate before use, so the cache can transiently exceed `maximumWeight` under burst load, especially with many concurrent misses. |
| **Default State** | ✓ | Enabled by default (`file_cache_enabled = FILE_CACHE_ENABLED.getBoolean()`, default true) with a non-zero auto-sized default. |

## Related / Dependent Constraints

- Shares the same source value (`file_cache_size`) with [[file_cache_size-02]] (the `BufferPool` hard threshold) — but the two derive *different* effective caps from it: this pair uses `file_cache_size - 32 MiB` (`RESERVED_POOL_SPACE_IN_MiB`), while pair 02's `BufferPool` threshold uses the raw, un-reduced `file_cache_size`. This 32 MiB skew means the physical allocator's ceiling is always slightly higher than the logical cache's target weight.
- `file_cache_round_up` / `disk_optimization_strategy` — affects chunk alignment, not sizing, but shares the same config load path.

## Bypass Potential (Target 3 seed)

- Burst of concurrent cache misses (e.g., a wide scan touching many distinct SSTable chunks) can insert many buffers before Caffeine's eviction catches up — since eviction is synchronous-but-post-hoc per write, high write concurrency means many `load()`s can race ahead of eviction, each briefly experienced as an "unenforced" allocation.
- Because eviction only reclaims the *logical* cache's own accounting, actual off-heap pressure is really bounded by pair 02's `BufferPool` threshold — meaning this pair's cap is best understood as a soft target that pair 02 is the real backstop for (see pair 02's own bypass, which is more severe).

## Verification

| Field | Content |
|--------|---------|
| **Status** | verified |
| **Verified By / Date** | Jingsong, 2026-09-10 (traced and line-checked against local `cassandra-5.0.9` clone) |
| **Notes** | Reserved-pool-space offset (32 MiB) confirmed at `ChunkCache.java:49`; cross-checked against `BufferPools.java` to confirm the two layers use different effective thresholds from the same config value. |

---

## Notes

- Module: `org.apache.cassandra.cache` (ChunkCache) — logical/API layer over the off-heap chunk buffer pool.
- See [[file_cache_size-02]] for the physical allocation layer (`BufferPool`) that actually backs these buffers and is the harder resource boundary.
