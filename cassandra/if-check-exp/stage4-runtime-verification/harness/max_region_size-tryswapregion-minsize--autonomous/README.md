# Harness: max_region_size-tryswapregion-minsize--autonomous

Written 2026-10-28 (stage 4, node `pc32`). Run copies (from `copy-source.sh` of `cassandra/cassandra-5.0.9`): `~/s4-mrs` (default build, `ant build-test`) and
`~/s4-mrs256` (`MAX_REGION_SIZE = 256 * 1024` at `NativeAllocator.java:46`, one line, `ant jar`; patch kept in the run's logs as `arm-R256.patch`).
Adapted from `../row_overhead_size-intrie_init-limitinmb--autonomous/` (`make-node.sh`, `Jmx.java`, the unit launcher); no conclusions are reused.

Unit tier (B2): `NativeAllocatorRegionProbe.java` (package `org.apache.cassandra.utils.memory`, so the protected `NativeAllocator(NativePool)` constructor
is visible; compiled by `unit-all.sh` into `<copy>/build/probe`, not into the repository). Private state (`regions`, `Region.capacity`) is read by reflection.
One JVM per case and repetition through the plain `java` launcher (`unit-run.sh`), so the static `RACE_ALLOCATED` stash is empty at start. `unit-all.sh <arm> <copy>` runs
C1, C2, C3 x4 sizes, C4 x3 allocator counts, Z (zero-slack control) and P1 (positive control), 3 repetitions. P1 uses a no-op cleaner and releases 6400 B with
`offHeap().adjust(-6400)` to wake the blocked writer (not `setDiscarded`, which would free the regions under a woken writer).

Cluster tier (B3): `cluster-run.py` (one node start end to end: node conf from `make-node.sh`, `-Xms2G -Xmx2G -XX:+AlwaysPreTouch`, a Byteman rule `region.btm` printing
`REGION <capacity>` for each `NativeAllocator$Region` constructed, 1 Hz `sumpoll` of `MemtableOffHeapSize` through `Jmx.java`, snapshots `base` / `end` / `blob` of
`/proc/PID/status` (`RssAnon`, `VmData`), the JMX sums and the ledger), `workload.py` (python driver bundled in the copy's `lib/`; T tables x 1200 rows x 1000 B; a 4 MiB blob row),
`chain.sh` (the whole of run 1: unit arms, then six node starts), `selfcheck.py` (independent re-parse of the raw files).
The node runs in the foreground (`bin/cassandra -f`): in daemon mode `CassandraDaemon.java:738` closes `System.out` after start-up and the Byteman lines stop.
The node's `stdout.txt` (not `system.log`) carries the ledger. System tables also use `NativeAllocator` under `offheap_objects`, so all readings are deltas from `base`.
