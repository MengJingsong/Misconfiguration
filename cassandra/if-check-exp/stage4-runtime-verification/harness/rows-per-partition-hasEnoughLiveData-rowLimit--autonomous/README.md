# Harness: rows-per-partition-hasEnoughLiveData-rowLimit--autonomous

Written 2026-10-27, tag `p75`, node `pc12`. Not upstream code. The case file's sha256 at the freeze is in the results file §1 (written before this harness).
Trees: unit `~/s4-b11-p75-u` (`copy-source.sh`, `ant build-test`), node `~/s4-b11-p75-n` (`copy-source.sh`, `ant jar`; no `ant` once the node has started).
Port slot 5: loopback 127.0.5.1, storage 7000, native 9042, JMX 7150. Node data on tmpfs `/dev/shm/s4-b11-p75`; logs `~/s4-b11-p75-logs/<run>/`.
Python driver: the 3.29.0 driver unzipped from `lib/cassandra-driver-internal-only-3.29.0.zip` into `~/s4-b11-p75-drv/`.
Adapted from `harness/rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous/` (same driver, JMX reader and node handling; different test, workload, arms and analyzers).

| File | Tier | What it does |
|---|---|---|
| `RowCachePartitionLimitTest.java` | unit (B2) | `CQLTester` test in `org.apache.cassandra.db`, copied into the unit tree by `unit-run.sh`. Arms `5`, `50`, `ALL`, `NONE`, `TTL`, `TOMB` (one 200-row partition each): populate read (LIMIT 1), entry shape and cache sizes, then for L in 1, 4, 5, 6, 49, 50, 51, 1000 the direct calls `hasEnoughLiveData` and `isFilterFullyCoveredBy` and one real read with the hit / miss / out-of-range deltas; entry and sizes again at the end. Then `NOCK`. Writes `$STAGE4_OUT/unit.txt`. The first trigger (N=5 leaves an entry) stops the test if it fails. |
| `unit-run.sh <tree> <outdir> [rows]` | unit | copies the test in, `ant testsome`, runs `analyze_unit.py`. `rows` defaults to 200; other values are shakedown only. |
| `analyze_unit.py`, `mk-known-answer.py` | unit | EXPECTED lines for B2f/B2g (frozen text). `mk-known-answer.py good|bad` writes a synthetic `unit.txt`. |
| `Jmx.java` | cluster | row-cache gauges (`Size`, `Capacity`, `Entries`) and the table's `RowCacheHit/Miss/HitOutOfRange` counters over JMX. |
| `loader.py` | cluster | Python-driver client: `load` (ck 0-199, 100-character text), `del` (ck 0-99 row deletions), `full` (whole-partition warm-up), `scan` (`SELECT * ... WHERE pk=<pk> LIMIT <limit>`, **unprepared**, 128 in flight). |
| `cluster-run.py` | cluster | `... load` and `... arm n5 n50 nall none t5`, one node lifetime each, cold cache, heap pre-touched; baseline, P1 (LIMIT 1), P2 (LIMIT 100), P3 (LIMIT 1) checkpoints; the n50 arm then runs `setcachecapacity 0 8 0` (informational). Stops at a failed first-trigger check (exit 3); node stopped on any exit. |
| `analyze_cluster.py` | cluster | EXPECTED lines for B3f/B3g (frozen text) from each arm's `ckpt.jsonl` and `jmx.csv`. |
| `run1-chain.sh` | both | unit tier, then cluster load and all arms, then the analyzer; appends the timing lines. |
| `selfcheck.py` | both | independent re-parse of the raw logs (stage-4 self-check). |
| `shake-cluster.sh` | cluster | small-data instrument check; not a reading. |

**Instrument checks (not readings; outputs in `~/s4-b11-p75-logs/shake-*` on `pc12`, not used):**
1. `analyze_unit.py` on the synthetic `good` file: 0 primary mismatches of 105; on `bad` (N=5 caches 8 rows and the entry changes after the L reads): flags `rowCount`, `cachedLiveRows`, `rowsWithNonExpiringCells` and the unchanged-entry check, class "cachedLiveRows > N ... refuted".
2. Unit test at 120 rows per partition (`unit-run.sh ... 120`): runs, first trigger OK, all checks match except the three that depend on 200 rows (ALL `rowCount`, `cachedLiveRows`, `rowsWithNonExpiringCells` = 120). The shakedown output was discarded and nothing was edited because of it.
3. Cluster chain on 400 + 80 partitions (arms n5 n50 none t5, `analyze_cluster.py ... 400 80`): load, known-answer reads, all arms ran, first-trigger checks passed, the node was stopped each time ("daemons left: []"), counters and Size / Entries as predicted; the only mismatches are the absent `nall` arm and the 12 MB lower bound on Size, which needs 20,000 partitions. The n50 shrink step ran (Size did not change in 60 s with the cache at 2.3 MB, below the new 8 MiB capacity; not informative at that scale).
