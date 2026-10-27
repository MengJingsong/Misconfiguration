# no_constraint — trace-back only  <!-- file: traceback-only/no_constraint-avoidreservedvalues-wastetracker--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:300` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** None. Line 300 (`AtomicBTreePartition.java:300`) is in `avoidReservedValues(int wasteTracker)` (declared at line 298), which compares the computed tracker value against the sentinel constants `TRACKER_NEVER_WASTED = 0` (line 57) and `TRACKER_PESSIMISTIC_LOCKING = Integer.MAX_VALUE` (line 58) and, on a collision, adds 1 (line 301) so the packed timestamp never equals a reserved state value. This is pure bookkeeping on a 32-bit time-offset counter (the `wasteTracker` field, line 80), not a cap on memory or disk. The nearby waste-limit constants (`EXCESS_WASTE_BYTES = 10 * 1024 * 1024L` at line 63, `ALLOCATION_GRANULARITY_BYTES = 1024` at line 61, `EXCESS_WASTE_OFFSET` at line 64, `CLOCK_SHIFT = 17` at line 66) are hard-coded `private static final` values with no yaml key, -D property or JMX setting, and they are used in the caller (`shouldLock`, lines 272-293) to decide when to switch to pessimistic locking after wasted allocation from CAS retries. They throttle contention behavior, not a configured memory or disk limit, and the method at line 300 does not use them.
