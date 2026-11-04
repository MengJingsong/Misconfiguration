# Harness: cql-row-limit-incrementRowCount-rowsCounted--autonomous

Written 2026-10-27, tag `c76`, node `pc12`, port slot 6 (loopback 127.0.6.1, storage 7000, native 9042, JMX 7160). Not upstream code.
Trees: unit `~/s4-b11-c76` (`copy-source.sh`, `ant build-test`), node `~/s4-b11-c76-n` (`copy-source.sh`, `ant jar`; no `ant` once the node has started). Node data on tmpfs `/dev/shm/s4-b11-c76`; logs `~/s4-b11-c76-logs/`. Python driver 3.29.0 unzipped from the build's `lib/` into `~/s4-b11-c76-drv`.
Structure adapted from the harness of `cql-row-limit-hasEnoughLiveData-rowLimit--autonomous` (node start/stop, conf rewriting).

| File | Tier | What it does |
|---|---|---|
| `RowLimitMemoryProbeTest.java` | unit (B2) | `CQLTester` test copied into the unit tree. Lazy synthetic one-partition source (fresh value buffer per row), `DataLimits.cqlLimits(L)` counter, retained rows, heap after 3 `System.gc()`, `unsharedHeapSize` sum; grid of widths 16 B / 1 KiB / 64 KiB x limits under the 300 MB rule, 5 repetitions; NONE series; dead-row series (every 10th row live); byte-stop control (8 MiB). Writes `$STAGE4_OUT/unit.txt`. |
| `unit-run.sh`, `analyze_unit.py`, `mk-known-answer.py` | unit | driver; EXPECTED lines (frozen B2f/B2g); a synthetic good / bad `unit.txt` for the analyzer's check. |
| `cluster-run.py`, `loader.py`, `Jmx.java` | cluster (B3) | `load` (three tables, one partition each, tmpfs); `life U` (uncapped) and `life C` (`read_thresholds_enabled`, `local_read_size_fail_threshold` 20 MiB): warm-up of every query shape, a first-trigger check, then each shape 3 times in seeded shuffled order with `GC.run` and 3 s quiet before it. `Jmx.java` samples the all-thread allocation counter and heap used every 25 ms. Stops at a failed first-trigger check (exit 3). |
| `analyze_cluster.py` | cluster | per-query A (allocated bytes minus idle drift), H, per-page A; EXPECTED lines (frozen B3f/B3g). |
| `run1-chain.sh` | both | unit, then load, lifetime U, lifetime C, then the analyzer; timing lines. |
| `shake-cluster.sh` | cluster | small-data instrument check (not a reading). |
| `selfcheck.py` | both | independent re-parse of the raw logs (written after run 1 from the raw formats; changes no reading). |

**Instrument checks (shakedowns, not readings; outputs in `~/s4-b11-c76-logs/shake-*`):**
1. `analyze_unit.py` on `mk-known-answer.py good`: 0 mismatches; on `bad` (retained heap independent of width): 8 flagged.
2. Unit test at 50 000 rows, 2 repetitions: first trigger ok; every check ok except the linearity check, whose design was wrong for a 0.3 MB reading noise (changed before the freeze); after the change 0 mismatches. Row cost seen: about 160 B retained heap, 304 B by `unsharedHeapSize`, for a 16 B cell.
3. Cluster chain on small data (`STAGE4_SCALE=small`: 12 000 / 1 200 / 300 rows): both first-trigger checks ok (U: 300 rows, 166 MB allocated; C: read-size abort at 21 MB), control passes and caps; the remaining mismatches are scale artifacts (LIMIT above the table size). Found: a paged query ends with an empty page when LIMIT exceeds the rows; a sample-to-sample window double counts neighbouring pages (samples every 26 ms, pages 40 to 80 ms), so the page allocation is read by interpolating the cumulative counter; one allocation window read negative (a thread that died takes its count with it), which the median over three repeats absorbs; the `OutOfMemory` grep matched the JVM options line (now `java.lang.OutOfMemoryError`).
