# excess_waste_bytes — trace-back only  <!-- file: traceback-only/excess_waste_bytes-uselock-wastetracker--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `helper org.apache.cassandra.db.partitions.AtomicBTreePartition.useLock()` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** EXCESS_WASTE_BYTES (a hard-coded constant, with the derived EXCESS_WASTE_OFFSET and the granularity constants ALLOCATION_GRANULARITY_BYTES and CLOCK_SHIFT) in AtomicBTreePartition, first declared at src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:63. useLock() (line 258-261) only tests `wasteTracker == TRACKER_PESSIMISTIC_LOCKING` (the sentinel Integer.MAX_VALUE, declared at line 58; the field starts at TRACKER_NEVER_WASTED = 0, lines 57 and 80). That sentinel is set in updateWastedAllocationTracker (line 293) when a writer's wasted allocation from a failed CAS retry in the memtable partition update, i.e. memory allocated and thrown away, either is >= EXCESS_WASTE_BYTES in one operation (line 272) or exceeds the acceptable waste rate (lines 278-288); the thread then falls back to pessimistic locking (shouldLock, lines 231-245). The unit is bytes (the tracker counts in ALLOCATION_GRANULARITY_BYTES = 1024 units, line 61, against a clock shifted by CLOCK_SHIFT = 17, line 67, i.e. about 132us ticks). The value is 10 * 1024 * 1024L = 10 MiB (line 63), a literal, not derived from heap or any other setting; EXCESS_WASTE_OFFSET = 10 MiB / 1024 = 10240 units (line 64). It is not settable by yaml key, -D property or JMX, since it is a private static final constant, so changing it needs a code change and a rebuild/restart. It bounds the waste of per-partition memtable allocation (heap/off-heap churn) before lock-based serialization takes over, which is an indirect memory-related cap rather than a size limit on stored data.
