# none — trace-back only  <!-- file: traceback-only/none-allocateoversize-peer--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/NativeAllocator.java:194` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** None: the line at NativeAllocator.java:194 (`if ((peer = region.allocate(size)) == -1) throw new AssertionError();`) is inside `allocateOversize(int size)` (NativeAllocator.java:186-198) and is pure bookkeeping, not a memory/disk cap. The `Region` is created at line 190 with `capacity == size` (`new Region(MemoryUtil.allocate(size), size)`), and `Region.allocate` (NativeAllocator.java:269-277 in the Region class) returns -1 only when `newOffset + size > capacity`, which cannot happen for the first allocation (offset 0) of a region sized exactly `size`; so the check is a never-expected sanity assertion on the allocator's own offset arithmetic. The only related limit is the hard-coded constant `MAX_CLONED_SIZE = 128 * 1024` (NativeAllocator.java:47, bytes), which merely routes allocations larger than that to `allocateOversize` (line 144-145) instead of the shared regions; it is a fixed constant (not settable by yaml, -D property or JMX; a change would need a code edit and rebuild), unrelated to capping memory use. The actual off-heap memtable accounting happens separately via `offHeap().allocate(size, opGroup)` (NativeAllocator.java:141), whose limit (the memtable off-heap space setting) was not traced here and is not verified.
