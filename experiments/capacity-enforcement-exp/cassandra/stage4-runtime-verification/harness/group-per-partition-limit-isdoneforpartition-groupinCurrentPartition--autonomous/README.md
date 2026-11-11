# Harness: group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous

Written 2026-10-27, tag `g73`, node `pc07`, port slot 3. Not upstream code. Case file sha256 at the freeze: results file section 1.
Trees: unit `~/s4-b11-g73` (`copy-source.sh`, `ant build-test`), node `~/s4-b11-g73-n` (`copy-source.sh`, `ant jar`; no `ant` once the node has started).
Slot 3: loopback 127.0.3.1, storage 7000, native 9042, JMX 7130. Node data on tmpfs `/dev/shm/s4-b11-g73`; logs `~/s4-b11-g73-logs/`. Python driver: copy of 3.29.0 in `~/s4-b11-g73-drv`.

| File | Tier | What it does |
|---|---|---|
| `GroupPerPartitionLimitTest.java` | unit (B2) | `CQLTester` test in `org.apache.cassandra.db`, copied into the unit tree by `unit-run.sh`. R rows in one partition (memtable), `DataLimits.groupByLimits(NO_LIMIT, N, NO_LIMIT, spec)` with `aggregatePkPrefixFactory(comparator, 1)`; counts rows pulled under the counter, groups returned, `counter.counted()`, thread-allocated bytes, retained heap after three `System.gc()`; 5 reps per N in {1,10,100,1000,NO_LIMIT}; a no-query noise arm; a second pass that clones and keeps every returned row (positive control). First trigger: N=10 must return 10 groups and pull < R/2 rows, else the test stops. |
| `unit-run.sh <tree> <out> [rows]` | unit | copies the test in, `ant testsome`, `analyze_unit.py`. |
| `analyze_unit.py`, `mk-known-answer.py` | unit | EXPECTED lines for B2f/B2g; `mk-known-answer.py good|bad` writes a synthetic `unit.txt` (good must print CLASS row 1, bad, with retained heap rising with N, must not). |
| `Jmx.java` | cluster | 100 ms sampler: heap used, sum of G1 pool collection usage, sum of thread-allocated bytes. |
| `query.py` | cluster | Python-driver client: `load`, `group` (single-partition `GROUP BY k, ck [PER PARTITION LIMIT N]`, every page read, row count checked per query, marker line per query), `point` (unrelated point reads, the noise arm). |
| `cluster-run.py` | cluster | `load` (10 x 200000 rows, flush, known-answer count) and `run` (one node lifetime: warm-up, forward sweep, noise, page-size control, reverse sweep, exploratory arms). Heap 1 GiB G1 with the young generation capped at 2 % (`G1MaxNewSizePercent=2`) so garbage adds at most about 20 MB to a sampled peak. Stops at a failed row-count check (exit 3). |
| `analyze_cluster.py` | cluster | EXPECTED lines for B3f/B3g with the thresholds fixed before run 1. |
| `run1-chain.sh` | both | unit tier, then cluster, then the analyzer; appends the timing lines. |
| `selfcheck.py` | both | independent re-parse of the raw logs. |

**Instrument checks (not readings; outputs in `~/s4-b11-g73-logs/shake-*` on `pc07`):**
1. `mk-known-answer.py good|bad` through `analyze_unit.py`: good prints CLASS row 1; bad flags `retained` (30 % spread).
2. Unit test at R=3000 (`unit-run.sh ... 3000`): ran, first trigger OK, groups = min(N,R), pulled = N+1, retained spread 0.16 %, control delta rises with N (0.4 kB per row).
3. **Defect found and fixed before run 1 (heap instrument).** The first cluster shakedown (20,000 rows per partition) read heap through the G1 pools' `CollectionUsage` (0 in most windows) and `HeapMemoryUsage.used`, whose peak was 285-600 MB at the work-heavy arms: Cassandra's `jvm11-server.options` floors the young generation at 50 % of the heap (`G1NewSizePercent=50`), so a sampled peak measured garbage. The node now appends `G1HeapRegionSize=4m`, `G1NewSizePercent=1`, `G1MaxNewSizePercent=2` (young generation about 20 MB); the second shakedown peaks were 4-25 MB.
4. Full-size shakedown (200,000 rows per partition, 1 repetition, `shake-cl3`): all 12 arms ran, row counts exact, peak heap 0-17 MB at P=1000 for every N, 643 MB at P=300000, disk unchanged; the page-size control moves by 626 MB, far above the 30 MB threshold, so the control is able to show an effect at this size. These were not readings; run 1 uses 10 repetitions.
