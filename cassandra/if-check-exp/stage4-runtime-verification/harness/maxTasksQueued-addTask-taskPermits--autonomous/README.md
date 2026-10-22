# Harness — maxTasksQueued-addTask-taskPermits--autonomous

Stage-4 harness for the autonomous case file (as filed sha256 `5b59741e…`; audit freeze `e8ac528c…`; version the cluster tier ran
`5b27ef30…` after runbook fix D1; see the results file [§1](../../results/maxTasksQueued-addTask-taskPermits--autonomous.md)).
Written 2026-10-22 on `pc07`, run from a copy `~/stage4-harness-run/mta/` (md5 in `~/stage4-harness-run/mta.md5`) against
`~/cassandra-mta` (`cassandra-5.0.9`, `b5f2a54`, `ant build-test`). Logs: `~/stage4-logs/mta/<run>/`. The host was shared; this harness
uses only 127.0.0.4, JMX 7204 and `~/stage4-mta/` (no Byteman). Adapted from the `concurrent_writes-takeWorkPermit` harness.

| File | Tier | What it does |
|---|---|---|
| `SepQueueProbe.java` | unit (B2, U1-U4) | `main` in package `org.apache.cassandra.concurrent`: `sep` = `SharedExecutorPool` executor with c blockers on a latch then N tasks each holding a `byte[P]`; `tpe` = B2h's `ThreadPoolExecutor` with `ArrayBlockingQueue(1000)`; `base`. Prints `PROBE` (active, pending, `getMaxTasksQueued`, live heap after 3 x GC minus baseline, max block of 1e5 submits) and `DRAIN` lines; class histogram via `DiagnosticCommand` for N = 1e6. Catches the first `OutOfMemoryError` and prints the counts. |
| `unit-run.sh [run] [quick\|oom]` | unit | Compiles the probe outside the clone, one fresh `-Xms2g -Xmx2g` G1 JVM per configuration (16 sep + 2 tpe + base), then `unit-analyze.py`. `oom` reruns only the two OOM configurations (defect H1). |
| `unit-analyze.py <dir>` | unit | `EXPECTED:` lines for B2f / B2g / U-a..U-d. |
| `make-node-yaml.sh [k=v ...]` | cluster | `~/stage4-mta/node1/conf`: the tag's conf plus B3a lines; 127.0.0.4, JMX 7204; receive queue 0B (C2). |
| `Jmx.java` | cluster | JMX client; `poll` samples RequestsSize, heap, MutationStage Active / Pending / MaxTasksQueued each second. |
| `cluster-run.py all\|down\|reanalyze` | cluster | Arms A B C D (C4), each a fresh node lifetime; `concurrent_writes` 1 is set live after start (runbook fix D1); stress 6000 threads, 150 s; `EXPECTED:` lines carry the C5 / C6 / C7 definitions. |
| `selfcheck.py` | both | Independent re-parse of the raw run-1 files (copied with its output to `results/<stem>/run1/`). |

Run order: `bash unit-run.sh run1` (then `bash unit-run.sh run1 oom` if the OOM arms printed no `PROBE` line), `MTA_RUN=run1 python3 cluster-run.py all`.
