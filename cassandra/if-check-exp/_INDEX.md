# If-Check Cases — Master Index

Navigation hub and progress tracker for all if-check cases.
See [README.md](README.md) for the format.

**Source:** apache/cassandra @ tag `cassandra-5.0.9`
**Status legend:** `pending` · `in-progress` · `verified`

| Module | Limit | Object | Location | Status | File |
|--------|-------|--------|----------|--------|------|
| `memtable` | `memtable_heap_space` | `bytebuffer` | [`SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) | in-progress | [link](memtable/memtable_heap_space-bytebuffer.md) |

<!-- Add one row per case. -->

## Coverage summary

| Metric | Count |
|--------|-------|
| Modules covered | 1 |
| Total cases | 1 |
| Verified | 0 |
| Pending / in-progress | 1 |

## Lines considered and rejected

_Track if-checks that were examined but don't qualify (no branch divergence
on object creation, pure validation, etc.), so later passes don't re-examine
them._

| Location | Reason rejected |
|----------|------------------|

## Notes on Modules

### memtable
Storage-engine module covering memtable memory allocation and pooling
(`utils/memory`, `db/memtable`). One case so far:
- **`memtable_heap_space-bytebuffer`:** hard allocation cap in `SubPool.tryAllocate()`, gating `ByteBuffer.allocate()` for memtable writes.
