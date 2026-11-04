# Harness: cql-row-limit-hasEnoughLiveData-rowLimit--autonomous

Written 2026-10-27, tag `c74`, node `pc12`, port slot 4 (loopback 127.0.4.1, storage 7000, native 9042, JMX 7140, Byteman agent 19140). Not upstream code.
Trees: unit `~/s4-b11-c74` (`copy-source.sh`, `ant build-test`), node `~/s4-b11-c74-n` (`copy-source.sh`, `ant jar`; no `ant` once the node has started). Node data on tmpfs `/dev/shm/s4-b11-c74`; logs `~/s4-b11-c74-logs/`. Python driver 3.29.0 unzipped from the build's `lib/` into `~/s4-b11-c74-drv`.
Adapted from the harness of `rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous` (same `Jmx.java`, node start/stop and checkpoint code).

| File | Tier | What it does |
|---|---|---|
| `HasEnoughLiveDataProbeTest.java` | unit (B2) | `CQLTester` test copied into the unit tree. Per R in 100 (first trigger), ALL, 500: one table, one partition of 1000 rows, populate read, then 3 seeded-shuffled rounds over L in {1, 50, 100, 101, 1000, 1000000, none}: direct `hasEnoughLiveData` return, CQL read with counter deltas, `weightedSize`, `size()`, used heap after `System.gc()`, thread-allocated bytes. Negative control: `setRowCacheCapacityInMB(0)`. Writes `$STAGE4_OUT/unit.txt`. |
| `unit-run.sh`, `analyze_unit.py`, `mk-known-answer.py` | unit | driver; EXPECTED lines (frozen B2f/B2g); a synthetic good / bad `unit.txt` for the analyzer's check. |
| `cluster-run.py`, `loader.py`, `Jmx.java` | cluster (B3) | `load` (ks.t 200 x 2000 x 200 B, ks.t2 100 x 2000 for the warm-up); `arm <label>...` one node lifetime per arm: warm-up, `baseline`, populate pass, `populated`, 10,000 random reads with LIMIT L (seed 74), `window`, 60 s idle, `idle`; gauges and `RssAnon` sampled every 5 s. Arms: l1000 l10 l100 l100k lnone (R=100, 64 MiB), a100 anone (ALL, 64 MiB), s256 (ALL, 256 MiB), off10 off1000 offnone (row cache 0). Stops at a failed first-trigger check (exit 3). |
| `analyze_cluster.py` | cluster | EXPECTED lines (frozen B3f/B3g). |
| `run1-chain.sh` | both | unit, then load and all arms, then the analyzer; timing lines. |
| `shake-cluster.sh` | cluster | small-data instrument check (not a reading). |
| `selfcheck.py` | both | independent re-parse of the raw logs (written after run 1 from the raw formats; changes no reading). |

**Instrument checks (shakedowns, not readings; outputs in `~/s4-b11-c74-logs/shake-*`):**
1. `analyze_unit.py` on `mk-known-answer.py good`: 0 primary mismatches of 454; on `bad` (weightedSize grows with L): 18 flagged.
2. Unit test at 300 rows per partition: first trigger OK; every R=100 and R=ALL check ok; only the R=500 checks fail (the partition has 300 rows).
3. Cluster chain on 40 partitions x 400 reads: first-trigger checks ok. Found: with R=ALL at 8 MiB nothing is cached (the OHC cache splits its capacity into segments and stores no entry larger than a segment: entries are 428 KB); at 64 MiB only part of the set is cached (35 of 40). Control and ALL predictions amended in the case file before run 1 (section D items 5 and 6).
4. `unit-run.sh` leftover filter matched the node tree as well (`...-c74` prefix of `...-c74-n`): fixed to `$TREE[/ ]`.
5. First full unit pass (discarded, see results §3 defect 3): `weightedSize` is the whole cache, and the test left earlier arms' entries in it. The arm now invalidates every earlier table's entries and records `pre.size`.
