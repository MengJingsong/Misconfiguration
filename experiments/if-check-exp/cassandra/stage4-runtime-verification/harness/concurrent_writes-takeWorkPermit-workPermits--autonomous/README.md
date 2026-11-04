# Harness — concurrent_writes-takeWorkPermit-workPermits--autonomous

Stage-4 harness for the autonomous case file (audit sha256 `af2af2e5…`, run-1 version after runbook fixes D1–D2
`12fb743b…`; see the results file [§1](../../results/concurrent_writes-takeWorkPermit-workPermits--autonomous.md)).
Written 2026-10-21 on `pc07` (`node0.jason92-320876`), run from a copy `~/stage4-harness-run/sep/` (md5 in
`~/stage4-harness-run/sep.md5`) against `~/cassandra-sep` (`cassandra-5.0.9`, `b5f2a54210`, `ant build-test`). Logs go to
`~/stage4-logs/sep/<run>/` on the node, outside the repo. Another stage-4 session shared the host, so this harness uses
only 127.0.0.11, JMX 7211 and `~/stage4-sep/` (no Byteman).

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `SEPQueueHeapProbeTest.java` | unit (B2) | The case file's B2a test, verbatim (package `org.apache.cassandra.concurrent`): per configuration a fresh `SharedExecutorPool`, `newExecutor(N)`, *M* tasks of 64 KiB blocked on a latch, the caller-runs probe at line 196, live heap after 3 × `System.gc()`; claim arm N = 0 · 2 · 32 · 128, positive control `ResourceLimits.Concurrent` 16 / 64 MiB at N = 2 · 128. One added method, `supplementaryIdleCallerRuns` (marked SUPPLEMENTARY, not in B2f/B2g): `maybeExecuteImmediately` on an idle executor. | `javac` against the clone; shakedown1 (M = 400) |
| `unit-run.sh [run]` | unit | Copies the test into the clone's `test/unit/org/apache/cassandra/concurrent/`, runs `ant testsome` three times (rep1 and rep2 at M = 4000, R6; m8000 at M = 8000), rebuilds the `PROBE` lines from the ant log (the test JVM logs `System.out` one printf argument per line: harness defect H1), runs `unit-analyze.py`. `--remove` deletes the copied test. | shakedown1 |
| `unit-analyze.py <dir>` | unit | B2f/B2g checks with R6's definitions as `EXPECTED:` lines. | — |
| `make-node-yaml.sh [k=v ...]` | cluster (B3a) | `~/stage4-sep/node1/conf`: the tag's conf plus B3a's lines (directories under `~/stage4-sep/node1`, `commitlog_total_space: 2GiB`, both in-flight limits 256 MiB), 127.0.0.11 (environment deviation E1), JMX 7211, `-XX:HeapDumpPath` under the node's logs, plus the run's keys. | the yaml tail in `summary.txt` |
| `Jmx.java` | cluster | JMX client (from the `WRITE_BUFFER_SIZE` harness): `poll` samples `RequestsSize`, heap used and the `MutationStage` gauges every second on one connection. | shakedowns 2–3 |
| `cluster-run.py all \| down \| reanalyze` | cluster (B3e) | R0 (pool 0 at runtime for 120 s), R32, R2, R128 (throttled 400/s, 120 s), PC0 and PC (unthrottled 60 s; D1: receive queue 0B; PC per-IP 4 MiB), each in a fresh node lifetime (R2) after `TRUNCATE` + `clearsnapshot`; stress with `no-warmup` (R1). Samplers: tpstats + `du` every 5 s, `jcmd GC.run` + `GC.heap_info` + tablestats every 15 s, JMX every 1 s. Supplementary class histograms in R0. `phases.json`, `samples-*.csv`, `stress-*.out`, `summary.txt` with `EXPECTED:` lines (R4/R5/D2 definitions). `reanalyze` re-runs the analysis on a finished run. | shakedown2 (found the stress quoting bug), shakedown3 (found D1; 20–30 s arms) |
| `selfcheck.py` | both | Independent re-parse of the raw run-1 files (copied to `results/<stem>/run1/` with its output). | — |

Run order (run 1):

```bash
H=~/stage4-harness-run/sep
bash $H/unit-run.sh run1
SEP_RUN=run1 python3 $H/cluster-run.py all        # one background job, about 30 min
```
