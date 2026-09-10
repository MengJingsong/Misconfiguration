# Entry-Restriction Pairs — Master Index

Navigation hub and progress tracker for all entry-restriction pairs.
See [README.md](README.md) for the format.

**Source:** apache/cassandra @ tag `cassandra-5.0.9`
**Status legend:** `pending` · `in-progress` · `verified`

| Entry Point | Pair | Type | Restriction Location | Failure Mode(s) flagged | Status | Summary | Codepath |
|-------------|------|------|----------------------|-------------------------|--------|---------|----------|
| `memtable_heap_space` | 01 | Config | [`SubPool.needsCleaning():128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SubPool.java#L128) → soft flush trigger | proxy ⚠; enforcement ⚠ (post-hoc + async flush); default ✓ | verified | [link](memtable_heap_space/memtable_heap_space-01-summary.md) | [link](memtable_heap_space/memtable_heap_space-01-codepath.md) |
| `memtable_heap_space` | 02 | Config | [`SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SubPool.java#L156) (hard allocation cap) | proxy ⚠; enforcement ✗ (blocking-op bypass + row-overhead overshoot); default ✓ | verified | [link](memtable_heap_space/memtable_heap_space-02-summary.md) | [link](memtable_heap_space/memtable_heap_space-02-codepath.md) |
| `memtable_flush_writers` | 01 | Config | [`Config.java:184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L184) → [`DatabaseDescriptor.java:753`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L753) (auto-sizing + thread pool creation) | proxy ⚠; enforcement ⚠ (config-time check + unbounded queue at runtime); default ✗ (minimum too low) | verified | [link](memtable_flush_writers/memtable_flush_writers-01-summary.md) | [link](memtable_flush_writers/memtable_flush_writers-01-codepath.md) |
| `memtable_flush_writers` | 02 | Hardcoded | [`ExecutorPlus.pooled()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L1) (unbounded LinkedBlockingQueue) | proxy ⚠; enforcement ✗ (no capacity check + no backpressure); default ✗ (unbounded with no config) | verified | [link](memtable_flush_writers/memtable_flush_writers-02-summary.md) | [link](memtable_flush_writers/memtable_flush_writers-02-codepath.md) |
| `memtable_flush_writers` | 03 | Implicit | [`ColumnFamilyStore.PerDiskFlushExecutors:3503-3511`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3503-L3511) (one flush pool per data directory; distributed constraint) | proxy ✗; enforcement ✗ (no global cross-disk cap + slow-disk blocking join); default ✗ (1 thread/pool for multi-dir) | verified | [link](memtable_flush_writers/memtable_flush_writers-03-summary.md) | [link](memtable_flush_writers/memtable_flush_writers-03-codepath.md) |
| `file_cache_size` | 01 | Config | [`ChunkCache.<init>():151-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L151-L157) (Caffeine `maximumWeight`, logical cache) | proxy ⚠; enforcement ✗ (unconditional load before post-hoc eviction); default ✓ | verified | [link](file_cache_size/file_cache_size-01-summary.md) | [link](file_cache_size/file_cache_size-01-codepath.md) |
| `file_cache_size` | 02 | Config | [`BufferPool.GlobalPool.allocateMoreChunks():438-452`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L438-L452) (physical off-heap allocator) | proxy ✓; enforcement ✗ (unpooled unbounded fallback bypasses threshold entirely); default ✓ | verified | [link](file_cache_size/file_cache_size-02-summary.md) | [link](file_cache_size/file_cache_size-02-codepath.md) |

<!-- Add one row per pair. -->

## Coverage summary

| Metric | Count |
|--------|-------|
| Entry points identified | 3 |
| Total pairs | 7 |
| Verified | 7 |
| Pending | 0 |

---

## Notes on Entry Points

### memtable_heap_space
Resource constraint limiting maximum in-memory memtable size (per-table). Two pairs:
- **Pair 01:** Soft cleanup trigger (early flush at threshold)
- **Pair 02:** Hard allocation cap (blocking when exceeded)

### memtable_flush_writers
Resource constraint limiting concurrent and queued flush operations. Two entry points forming three pairs:
- **Pair 01:** Thread pool size config (`memtable_flush_writers` parameter) with auto-sizing logic
- **Pair 02:** Queue depth hardcoded unbounded in executor factory (implicit bypass of thread limit)
- **Pair 03:** Per-disk pool contention — one flush pool per data directory, each sized by the single `memtable_flush_writers` value with its own unbounded queue; no global cross-disk memory cap and the flush blocks on the slowest disk, so one slow disk stalls reclamation node-wide

**Key insight:** Pairs 01 + 02 compound: low thread count (01) → queue buildup (02) → memory exhaustion despite heap_space limit. Pair 03 distributes that weakness across disks: the multi-directory default of 1 thread/pool, replicated unbounded queues, and a blocking split-join join mean a single slow disk can drive node-wide OOM. Independent weaknesses create cascading failure.

### file_cache_size
Resource constraint limiting the off-heap memory used to cache decompressed SSTable chunks read from disk. One config value, two independent enforcement layers:
- **Pair 01:** `ChunkCache`'s Caffeine `maximumWeight` — a soft, approximate cap on cached-chunk weight (`file_cache_size - 32 MiB`); enforcement is post-hoc (load happens before eviction runs), so the cache can transiently overshoot under concurrent misses.
- **Pair 02:** The underlying `BufferPool` (`chunk-cache` instance) — a hard cap on *pooled* off-heap allocation, thresholded on the raw (un-reduced) `file_cache_size`. Once the pool is saturated, allocation silently falls through to an **unpooled, unbounded** direct allocation (`ByteBuffer.allocateDirect()`) that is not bounded by the threshold at all — tracked only in an unbounded counter and logged at most once per 15 minutes.

**Key insight:** the two pairs share one config value but enforce at different layers with different effective thresholds (a 32 MiB skew). Pair 01's weakness is cosmetic (transient overshoot, bounded by pair 02's pool). Pair 02's weakness is the real exposure: sustained pool saturation degrades `file_cache_size` from a hard cap into an advisory one, with off-heap usage bounded only by `-XX:MaxDirectMemorySize` or physical RAM — a strong Target 3 (bypass) candidate.
