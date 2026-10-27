# excess_waste_offset — trace-back only  <!-- file: traceback-only/excess_waste_offset-updatewastedallocationtracker-delta--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:283` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** EXCESS_WASTE_OFFSET (and its source EXCESS_WASTE_BYTES) is a hard-coded constant, first declared in src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:63-64 (`EXCESS_WASTE_BYTES = 10 * 1024 * 1024L`; `EXCESS_WASTE_OFFSET = (int)(EXCESS_WASTE_BYTES / ALLOCATION_GRANULARITY_BYTES)`, with ALLOCATION_GRANULARITY_BYTES = 1024 at line 61). The check at line 283 (in `updateWastedAllocationTracker(long wastedBytes)`, declared line 269) tests `delta < -EXCESS_WASTE_OFFSET`, where delta is the tracker value minus a time counter (`nanoTime() >>> CLOCK_SHIFT`, CLOCK_SHIFT = 17 at line 66, line 281); it caps how much memory allocated by lost CAS races (wasted work in memtable partition updates) a partition may accumulate before switching to pessimistic locking (TRACKER_PESSIMISTIC_LOCKING, line 58, set at line 293); line 272 applies the same 10 MiB limit to a single huge wasted allocation. Unit: the offset is in 1 KiB allocation-granularity units (the waste budget is bytes), default 10 MiB = 10240 units, derived by plain arithmetic from the literal; the allowed waste rate is roughly 7.63 KiB per ms (about 7.45 MiB/s) per the comment at lines 73-74. It is not settable (no yaml key, -D property, or JMX); changing it requires editing the source and rebuilding/restarting.
