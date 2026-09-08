# Entry-Restriction Pairs — Master Index

Navigation hub and progress tracker for all entry-restriction pairs.
See [README.md](README.md) for the format.

**Source:** apache/cassandra @ tag `cassandra-5.0.9`
**Status legend:** `pending` · `in-progress` · `verified`

| Entry Point | Pair | Type | Restriction Location | Failure Mode(s) flagged | Status | Summary | Codepath |
|-------------|------|------|----------------------|-------------------------|--------|---------|----------|
| memtable_heap_space | 01 | Config | `SubPool.needsCleaning():128` → `maybeClean()` (soft flush trigger) | enforcement-point ⚠ (post-hoc + async flush); proxy ⚠ | verified | [link](memtable_heap_space/memtable_heap_space-01-summary.md) | [link](memtable_heap_space/memtable_heap_space-01-codepath.md) |
| memtable_heap_space | 02 | Config | `SubPool.tryAllocate():156` (hard allocation cap) | enforcement-point ✗ (blocking-op bypass); proxy ⚠ | verified | [link](memtable_heap_space/memtable_heap_space-02-summary.md) | [link](memtable_heap_space/memtable_heap_space-02-codepath.md) |

<!-- Add one row per pair. -->

## Coverage summary

| Metric | Count |
|--------|-------|
| Entry points identified | 1 |
| Total pairs | 2 |
| Verified | 2 |
| Pending | 0 |
