# Harness: group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous

Written 2026-10-27, tag `g80`, node `pc12`, port slot 10. Not upstream code. Adapted from the sibling harness `group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous` (same node-config and sampler code).
Trees: unit `~/s4-b11-g80` (`copy-source.sh`, `ant build-test`), node `~/s4-b11-g80-n` (`copy-source.sh`, `ant jar`). Slot 10: loopback 127.0.10.1, storage 7000, native 9042, JMX 7200. Node data on tmpfs `/dev/shm/s4-b11-g80`; logs `~/s4-b11-g80-logs/`. Python driver: copy of 3.29.0 in `~/s4-b11-g80-drv`.

| File | Tier | What it does |
|---|---|---|
| `GroupPerPartitionLimitProbeTest.java` | unit (B2) | `CQLTester` test in `org.apache.cassandra.db`, copied into the unit tree by `unit-run.sh`. Shape A: 20 partitions x 1000 rows grouped by clustering column; shape B: 4 x 100000 rows grouped by partition key. `PartitionRangeReadCommand` -> `DataLimits.groupByLimits(NO_LIMIT, gppl, rowLimit, spec).newCounter(...).applyTo(partitions)`; counts rows pulled under the counter, rows returned, `counted()`, `countedInCurrentPartition()` before and after close, thread-allocated bytes; gppl {1,10,NO_LIMIT} x rowLimit {100,10000,NO_LIMIT}, 5 reps. First trigger: shape A gppl=10 must return 200 rows and pull < 1000, else the test stops. |
| `unit-run.sh <tree> <out> [shapeB-rows]` | unit | copies the test in, `ant testsome`, `analyze_unit.py`. |
| `analyze_unit.py`, `mk-known-answer.py` | unit | EXPECTED lines for B2f/B2g; `mk-known-answer.py good|bad` writes a synthetic `unit.txt` (good prints CLASS row 1; bad, shape B pulling less at gppl=1, flags B_pull, B_alloc, B_rl). |
| `Jmx.java` | cluster | 100 ms sampler: heap used, sum of G1 pool collection usage, sum of thread-allocated bytes. |
| `query.py` | cluster | Python-driver client: `load` (20 partitions x 200000 rows), `scan A|B <fetch> <L|abs> <reps>` (the two GROUP BY range queries, every page read, row count checked per query), `point` (noise arm). |
| `cluster-run.py` | cluster | `load` and `run` (one node lifetime: warm-up, 16 forward arms, noise, 6 reverse arms; `rchar` read at each arm's start and end; stops at a failed row-count check, exit 3). Heap 1 GiB G1, young generation capped at 2 %, compression off, autocompaction disabled. |
| `analyze_cluster.py` | cluster | EXPECTED lines for B3f/B3g with thresholds fixed before run 1. |
| `run1-chain.sh` | both | unit tier, then cluster, then the analyzer; appends the timing lines. |
| `selfcheck.py` | both | independent re-parse of the raw logs. |

**Instrument checks (not readings; outputs in `~/s4-b11-g80-logs/shake-*` on `pc12`):**
1. `mk-known-answer.py good|bad` through `analyze_unit.py`: good prints CLASS row 1; bad prints MISMATCH for B_pull, B_alloc, B_rl.
2. Unit test at shape-B rows 3000, 2 reps (`shake-unit`): ran, first trigger OK; all A_* and B_pull/B_rl/control relations held; B_alloc ratio 1.59 at 12,000 rows (allocation noise of the first cell of each loop, at full size 400,000 rows the same absolute noise is far below 10 %).
3. Cluster shakedown at 20,000 rows per partition, 2 reps (`shake-cl`, `shake-bad`): all 22 arms ran, row counts exact, shape B bytes read identical across L, control moved the peak by 166 MB; A_reads mismatch at that size is a scale artifact (L=100 covers half of 200 groups). A doctored copy (shape B L=1 reading 30 MB less) makes `analyze_cluster.py` print B_reads MISMATCH. `rows` check fixed to skip the mixed-shape warm-up arm.
4. Defect found before run 1 (not a reading): the python driver directory must be `~/s4-b11-g80-drv/cassandra-driver-3.29.0`.
