# Harness — maxTasksQueued-takeTaskPermit-taskPermits--autonomous

Stage-4 harness for the autonomous case file (as filed sha256 `58849d2c…`; frozen after the step-0 amendments 2026-10-22:
`eb691cfc…`; see the results file [§1](../../results/maxTasksQueued-takeTaskPermit-taskPermits--autonomous.md)). Written
2026-10-22 on `pc13` (`node3.jason92-320876`), run from a copy `~/stage4-harness-run/mtt/` (md5 in `~/stage4-harness-run/mtt.md5`)
against `~/cassandra-mtt` (`cassandra-5.0.9`, `b5f2a54210`, `ant build-test`). Logs: `~/stage4-logs/mtt/<run>/`, outside the repo.
`pc13` is used by this session alone, so the node runs on 127.0.0.1 with JMX 7199 (B3a). No Byteman.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `SEPQueueBoundProbe.java` | unit (B2) | The "small program" of B2a as a plain `main` (amendment R1): `SharedExecutorPool.newExecutor(1,…)`, a latch-blocked task holds the only work permit, then `execute()` of N tasks (`new byte[P]` captured) cumulatively to 10^4, 10^5, 10^6 (4 x 10^6 for P = 0); per point pending, `getMaxTasksQueued()`, wall time, slowest call, heap after 3 x GC; a class histogram at the end and a drain check. Control (`kind=control`): `ThreadPoolExecutor(1,1,0,ms,ArrayBlockingQueue(10000),AbortPolicy)`, same series. | `javac` against the clone; shakedown1 (N <= 20,000) |
| `unit-run.sh [run] [shakedown]` | unit | Compiles the probe, runs it as `java -Xms2g -Xmx2g -XX:+UseG1GC` for sep and control, P = 0 and 1024, two repetitions (own JVM each), then `unit-analyze.py`. | shakedown1 |
| `unit-analyze.py <dir>` | unit | The amended B2f/B2g definitions (R3) as `EXPECTED:` lines. | shakedown output |
| `make-node-yaml.sh [k=v … \| -k]` | cluster | `~/stage4-mtt/node1/conf`: the tag's conf plus B3a's lines (directories on local disk, `commitlog_total_space: 2GiB`), the node on 127.0.0.1 / JMX 7199, `-Xms1g -Xmx1g` appended to the node copy of `jvm11-server.options`, the run's keys; `-k` removes a shipped key. | the yaml tail in `summary.txt` |
| `Jmx.java` | cluster | JMX client (from the `concurrent_writes` harness): `poll` samples the beans once a second on one connection. | shakedown1 |
| `cluster-run.py all \| down \| reanalyze` | cluster (B3e) | Arms A (512 MiB limits, 2000 threads), B (16 MiB, 2000), A2 (512 MiB, 256), each a fresh node lifetime on wiped directories; samplers (tpstats 5 s, heap after GC + memtable size 15 s, JMX 1 s), class histogram at +180 s; the amended statistics (R9) and `EXPECTED:` lines. | shakedown1 (found D1, D2) |
| `selfcheck.py` | both | Independent re-parse of the raw run-1 files (copied to `results/<stem>/run1/` with its output). | — |

Run order (run 1):

```bash
H=~/stage4-harness-run/mtt
bash $H/unit-run.sh run1
MTT_RUN=run1 python3 $H/cluster-run.py all      # one background job, about 35 min
```
