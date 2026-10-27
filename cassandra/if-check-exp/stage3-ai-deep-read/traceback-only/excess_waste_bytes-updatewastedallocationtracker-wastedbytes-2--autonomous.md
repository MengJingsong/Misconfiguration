# excess_waste_bytes — trace-back only  <!-- file: traceback-only/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:272` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** EXCESS_WASTE_BYTES is a hard-coded constant (`private static final long`) first declared at src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:63, as `10 * 1024 * 1024L`. Its unit is bytes of heap allocation wasted by a thread when its compare-and-swap update of a memtable partition fails and the work is redone. The default is simply the literal 10 MiB, and it is not derived from any other value. A single wasted-allocation report at or above this size (the check at line 272 in `updateWastedAllocationTracker`, which compares `wastedBytes < EXCESS_WASTE_BYTES`) skips the rate tracker and sets the partition to pessimistic locking (line 293). The constant also sets `EXCESS_WASTE_OFFSET` (line 64) as `EXCESS_WASTE_BYTES / ALLOCATION_GRANULARITY_BYTES`, where granularity is 1024 (line 61). That offset is the cumulative-waste window used at lines 283-284. It caps wasted memory churn, not a memory or disk size limit, because it only decides when to switch to locking. It cannot be set through a yaml key, a -D property, or JMX, and changing it means editing the source and rebuilding, which needs a restart.
