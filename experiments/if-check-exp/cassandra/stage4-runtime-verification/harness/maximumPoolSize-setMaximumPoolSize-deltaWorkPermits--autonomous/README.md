# Harness — maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous

Stage-4 harness for the autonomous case file (audit freeze sha256 `d75be538…`; run-1 version after runbook fix D1 `9f1c742c…`; see the
results file [§1](../../results/maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous.md)). Written 2026-10-22 on `pc07`
(`node0.jason92-320876`), run from a copy `~/stage4-harness-run/mps2/` (md5 in `~/stage4-harness-run/mps2.md5`) against `~/cassandra-mps2`
(`cassandra-5.0.9`, `b5f2a54210`, `ant build-test`). Logs go to `~/stage4-logs/mps2/<run>/` on the node, outside the repo. The host is
shared with another stage-4 session, so the harness uses only 127.0.0.5, JMX 7205 and `~/stage4-mps2/` (no Byteman). Nothing here is committed.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `SepCapProbe.java` | unit (B2) | Main class (no clone files are changed). Per configuration a fresh `SharedExecutorPool`, `newExecutor(n)`; variant A (T = 2000, the running task allocates and registers 1 MiB, blocks on a latch, releases on the gate), variant B (T = 600, the submitting thread allocates 1 MiB per task); byte-queue control (`ThreadPoolExecutor`, `ArrayBlockingQueue(64)`, `AbortPolicy`); the resize sequence with a counting listener and a logback appender on `SEPExecutor`. Prints `PROBE` / `CTRL` / `RESIZE` lines. | `javac`; 3-rep shakedown (found the registry leak and the pool-thread count) |
| `unit-run.sh [run]` | unit | Compiles the probe and runs it in three JVMs (`-Xmx2g -Xms2g -Xss256k -XX:+UseG1GC -XX:G1HeapRegionSize=4m -XX:NativeMemoryTracking=summary`, amendment U1), then `unit-analyze.py`. | shakedown |
| `unit-analyze.py <dir>` | unit | B2f/B2g/U3/U4 checks as `EXPECTED:` lines. | shakedown |
| `make-node-yaml.sh [k=v …]` | cluster | `~/stage4-mps2/node1/conf`: the tag's conf plus B3a's lines (directories, 2 GiB commit log cap, 127.0.0.5, JMX 7205, NMT) and the run's keys. | yaml tail in `summary.txt` |
| `Jmx.java` | cluster | JMX client (from the `concurrent_writes` harness): `poll` samples every second on one connection. | shakedowns |
| `cluster-run.py all \| down \| reanalyze` | cluster | Nine node lifetimes (n32, n4, n256, n32b, RS, PC0, PC, M64, M256), samplers (tpstats 5 s; GC.run + heap_info, RSS, NMT, thread dumps 30 s; JMX 1 s), `phases.json`, `EXPECTED:` lines for C5/C6/C7. Env: `MPS_RUN`, `MPS_ONLY`, `MPS_ROWS`, `MPS_READ_S`, `MPS_IDLE_S`, `MPS_RS_S`, `MPS_PC_S`. | 4-lifetime and 8-lifetime shakedowns at small sizes |
| `selfcheck.py <run dir>` | both | Independent re-parse of the raw run-1 files; output in `results/<stem>/run1/selfcheck.txt`. | — |

Run order (run 1):

```bash
H=~/stage4-harness-run/mps2
bash $H/unit-run.sh run1
( MPS_RUN=run1 setsid nohup python3 $H/cluster-run.py all < /dev/null > ~/stage4-logs/mps2/cluster-run1.out 2>&1 & )   # about 2 h
python3 $H/selfcheck.py ~/stage4-logs/mps2/run1
```
