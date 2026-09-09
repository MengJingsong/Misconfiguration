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

<!-- Add one row per pair. -->

## Coverage summary

| Metric | Count |
|--------|-------|
| Entry points identified | 2 |
| Total pairs | 5 |
| Verified | 5 |
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
