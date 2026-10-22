# Harness — commitlog_total_space-maybeFlushToReclaim-unused--autonomous

Code the stage-4 run needs, for the case file's B2 (unit) and B3 (cluster), as amended 2026-10-21 (R1–R4). Results:
[`../../results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md`](../../results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md).

| File | What it is |
|---|---|
| `CommitLogTotalSpaceCapTest.java` | B2e's test, copied into `<clone>/test/unit/org/apache/cassandra/db/commitlog/`. Changes from the filed code: `memtable_heap_space = 768 MiB` (R1), a wall-clock column, and `SUMMARY` printed as one string and appended to `$CLCAP_OUT.summary` (R2). Parameters by environment: `CLCAP_MIB`, `CLCAP_SLEEP_MS`, `CLCAP_N`, `CLCAP_OUT`. |
| `unit-run.sh` | `bash unit-run.sh <outdir> [N] [MiB:sleep ...]`. Runs each arm in a fresh `ant testsome` JVM from `~/cassandra-cts`, clearing `build/test/cassandra` and `build/test/logs` first. Keeps the CSV, the summary, the JUnit XML, `ant.log` and the raw test-log tree, and counts flush reasons into `reasons.txt`. |
| `cluster-run.sh` | `bash cluster-run.sh <outroot> <label> <capMiB> <throttled 1/0> [n]`. One node under `/tmp/clcap`, configured exactly as in B3a. Waits for `UN` and `statusbinary running`. Samples `du -sb`/`du -sk`/file count/data `du` every 1 s, and the JMX gauge `TotalCommitLogSize` every 10 s (`nodetool sjk mx`). Runs B3c's stress command, settles for 60 s, and counts flush reasons from this lifetime's `system.log`. It stops the node on any exit, checks for leftover daemons with `ps … '[j]ava.*CassandraDaemon'`, and wipes the node. |
| `cluster-chain.sh` | Runs the four arms in order: 256, 1024, 16384, 256p. |
| `analyze.py` | The run script's analysis. It prints the readings and one `EXPECTED:` line per B2f/B3f prediction. |
| `selfcheck.py` | An independent check. It re-parses the raw files (CSV by hand; every test log, plain or `.gz`; the node's full `system.log` and `debug.log.gz`; `stress.out`) without using `reasons.txt`, `counts.txt`, `flushes.txt` or `analyze.py`. It then re-applies B2g/B3g as amended. |

**Instrument checks (not readings):**
- `javac` through `ant build-test`: 12 s, `BUILD SUCCESSFUL`.
- Unit shakedown 1 (N = 40, arms 15:10 and 100000:10). The test, CSV, summary and knob read-back worked, but the flush-reason count read 0 while the log held the lines: `zgrep -r` does not recurse here. Fixed to `find … | xargs zcat -f`.
- Unit shakedown 2 (N = 40, 15:10): the count works.
- Cluster shakedown (256 MiB, n = 300,000): config read-back, both samplers, the stress summary, flush counts and the node stop all work.
- Logs: `pc06:~/stage4-logs/cts/{unit-shakedown,unit-shakedown2,cluster-shakedown}/`.

Node copies are in `pc06:~/stage4-harness-run/cts/`, with md5s in `../../results/…/run1/harness.md5`. Not committed.
