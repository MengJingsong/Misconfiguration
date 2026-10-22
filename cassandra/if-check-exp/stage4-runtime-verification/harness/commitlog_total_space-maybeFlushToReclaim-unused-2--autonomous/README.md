# Harness — commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous

Code for the case file's B2 (unit), B2i (the line-259 arm added by the audit, R5) and B3 (cluster), as amended 2026-10-21. Results:
[`../../results/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md`](../../results/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md).
Node copies are in `pc06:~/stage4-harness-run/cl2/` (md5s in `../../results/…/run1/harness.md5`). Not committed.

| File | What it is |
|---|---|
| `CommitLogTotalSpaceTest.java` | B2e's test, copied into `<clone>/test/unit/org/apache/cassandra/db/commitlog/`. System properties: `clcap.totalMiB`, `clcap.sleepMs`, `clcap.n`, `clcap.mode` (`single` = `CLCap.Standard1`; `M` = 24 tables `M00`–`M23`, mutation i to `M⌊i/15⌋`), `clcap.nobreak`, `clcap.out`. 1 MiB mmap segments; a 1-ms sampler writes `tMs,phase,onDiskSize,activeSegments,dirBytes,memtableSwitches`; SUMMARY goes to `<out>.summary`. Runs under `BMUnitRunner` with four rules: `CHECK` (entry of `maybeFlushToReclaim`), `SELECT` (at the `flushDataFrom` call: `unused`, `flushingSize`, `segmentsToRecycle`, `allocatingFrom`), `FLUSH` (`ColumnFamilyStore.forceFlush(CommitLogPosition)` from `flushDataFrom`), and `nobreak` (`AT LINE 259`, sets `flushingSize = Long.MIN_VALUE/2` when `clcap.nobreak=true`, i.e. line 259 never breaks). Byteman locals need `debuglevel=…vars` (`build.xml:33`, the default). |
| `CLCapTrace.java` | The rules' helper. Writes `CHECK`/`SELECT`/`FLUSH` lines to `<out>.trace`. In a `SELECT` line, `gap = allocatingFrom.id − lastSelected.id − 1` is the race-free count of older segments left unselected (H1). `stop259` and `minimal` are computed from the selected segments' true sizes. |
| `unit-run.sh` | `bash unit-run.sh <outdir> [N] [label:T:sleepMs:mode:nobreak ...]`. The default runs the eight arms. Each arm is one `ant testsome` JVM in `~/cassandra-cl2`, with `build/test/{cassandra,logs}` cleared first. Keeps the CSV, summary, trace, JUnit XML, `ant.log` and raw test-log tree, and counts flush reasons with `find … \| xargs zcat -f`. |
| `cluster-run.sh` | `bash cluster-run.sh <outroot> <capMiB> [n]`. One node under `~/stage4-cl2/node`, with its own `CASSANDRA_CONF`; the shipped yaml keys are checked, the commented ones appended, and each must occur once. Sets `ulimit -n 100000` and waits for `UN` and `statusbinary`. Creates the schema with `write n=1` and flushes, then samples `du`/file count/data `du` every 0.25 s and the JMX gauge back to back. Runs `write n=1000000 -col 'size=FIXED(1000)' 'n=FIXED(1)' -rate threads=32`, settles 60 s, takes the census, then drains, stops and wipes the node. |
| `cluster-chain.sh` | The four arms in B3e's order: 8192 (control), 128, 256, 512. |
| `analyze_unit.py`, `analyze_cluster.py` | Readings and `EXPECTED:` lines per B2f / B2i / B3f, and the B2g / B2i / B3g row in the amended order (cluster row 4c added after attempt 1). |
| `selfcheck.sh` | The independent re-derivation with awk, grep and zcat from the raw files (results §5). |

**Instrument checks:**
- Compiled with `ant build-test` (12 s).
- Unit shakedown 1 (N = 40) showed the rules fire and the nobreak rule sets the local. It found H1 (`older` races with discards).
- Unit shakedown 2 checked the `gap` fix.
- The cluster shakedown (128 MiB, n = 100,000) found H2, a false "archiving configured" check matching `precision=`, and then passed.

Logs: `pc06:~/stage4-logs/cl2/{unit-shakedown,unit-shakedown2,cluster-shakedown}/`.
