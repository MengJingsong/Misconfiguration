# excess_waste_bytes — trace-back only  <!-- file: traceback-only/excess_waste_bytes-updatewastedallocationtracker-wastedbytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `helper org.apache.cassandra.db.partitions.AtomicBTreePartition.updateWastedAllocationTracker()` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** EXCESS_WASTE_BYTES (kind: constant, a `private static final long` in AtomicBTreePartition) is first declared at src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:63 and is compared at line 272 (`if (wastedBytes < EXCESS_WASTE_BYTES)`) against the `wastedBytes` argument of updateWastedAllocationTracker (declared at line 269). That argument is the `addWaste` value that shouldLock passes in at lines 239-241. The unit is bytes. The default is the hard-coded literal `10 * 1024 * 1024L`, which is 10 MiB. It is not derived from anything. The derived constant EXCESS_WASTE_OFFSET (line 64) is this value divided by ALLOCATION_GRANULARITY_BYTES (1024, line 61), which gives 10240 units. That offset is the tracker window used in lines 283-284. It caps the memory allocation that is wasted when a compare-and-swap (CAS) update to a partition is retried. A single retry that wastes at least 10 MiB skips the rate accounting. The code then sets wasteTracker to TRACKER_PESSIMISTIC_LOCKING (lines 292-294), so later updates to that partition take a lock instead of retrying. Otherwise the waste is rounded up to 1 KiB units (line 275) and checked against a time-based allowance of about 7.45 MB/s (the comment at lines 72-75, using CLOCK_SHIFT = 17 at line 66). Setting it: it is not settable. There is no yaml key, no -D property and no JMX hook, so a change requires editing the source and rebuilding.
