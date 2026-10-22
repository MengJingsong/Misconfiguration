# Harness — maximumPoolSize-takeTaskPermit-workPermits--autonomous

This is the stage-4 harness for the autonomous case file.
- Audit freeze: sha256 `c004650f…`.
- Run-1 version, after runbook fixes D1 and D2: sha256 `66fb7060…` (with the D2 line citation corrected, `e50549b2…`; see the results file §1).

It was written 2026-10-21 on `pc07` (`node0.jason92-320876`) and run from a copy, `~/stage4-harness-run/mps/` (md5 list in `~/stage4-harness-run/mps.md5`). It runs against `~/cassandra-mps`, a fresh clone of `cassandra-5.0.9` (`b5f2a54210`) built with `ant build-test`. Logs go to `~/stage4-logs/mps/<run>/` on the node. Node directories are `~/stage4-mps/{A,B}`. Nothing in this folder is committed.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `SEPMemoryProbeTest.java` | unit (B2) | The case file's B2a test, verbatim (Phases 1–3: 64 KiB payload per task; shrink 32 → 4 drives `workPermits` to −28 at `SEPExecutor.java:165`; `ResourceLimits.Concurrent` byte cap). Plus R4's `workingMemoryPerRunningTask` (Phase 4): a task allocates 1 MiB only when it starts running. Phase 4 also logs the JVM's max heap. | `javac` against the clone |
| `unit-run.sh [run] \| --remove` | unit | Copies the test into the clone and runs `ant testsome` three times. Uses `-Dtest.jvm.args="-XX:-UseConcMarkSweepGC -XX:+UseG1GC"` (runbook fix D1; ant's `maxmemory` sets 1 GiB). Rebuilds the `PROBE` lines from the ant log (harness defect H1, as in `concurrent_writes`), then runs `unit-analyze.py`. | D1 found by the first two attempts |
| `unit-analyze.py <dir>` | unit | B2f/B2g/R2/R4 checks as `EXPECTED:` lines. | — |
| `make-node-yaml.sh A\|B [k=v \| k=__DELETE__ ...]` | cluster | Builds `~/stage4-mps/<node>/conf` from the clone with B3a's lines. A is 127.0.0.21 (JMX 7221) and B is 127.0.0.22 (JMX 7222), environment deviation E1. | yaml tail in `session.log` |
| `Jmx.java` | cluster | JMX client, copied from the `concurrent_writes` harness. `poll` reads heap used, direct `MemoryUsed`, the networking `BufferPool` `UsedSize`/`OverflowSize` and the `MutationStage` gauges every 1 s. | shakedowns |
| `hold-mutation.btm` | cluster (R5, D2) | Byteman rule for B in the bind arm only: `Thread.sleep(2000)` at the entry of `MutationVerbHandler.doVerb`. The message is already deserialized there, so a running task holds its mutation for 2 s. | `TestScript`: parsed and type-checked; bind shakedown 2 |
| `cluster-run.py all \| down \| reanalyze` | cluster (B3e + R3 + R5) | L1 runs the warm-up, the baseline and v = 32 · 8 · 1 · 0. Then the control at 16 · 128 · 512 MiB (one B lifetime each), the drift repeat (R3), and the bind arm S/L × v = 1 · 8 · 32 · 128 (a fresh B with Byteman per phase, A with `write_request_timeout` 300 s). Samplers: B tpstats every 5 s, JMX every 1 s. A sample is flush → `internode_inbound` → JMX → `jmap -histo:live` → `GC.heap_info`. Writes `EXPECTED:` lines. `reanalyze` matches baselines by time stamp (harness defect H2). Env: `MPS_RUN`, `MPS_ONLY=bind`, `MPS_BIND_S/T/SET` (shakedowns only). | cluster attempt 1 (found D2-i), bind shakedowns 1 and 2 (found D2-ii, D2-iii and the `using_bytes` definition) |
| `selfcheck.py <run dir>` | both | Independent re-parse of the raw run-1 files: the per-test log, histogram files, `system.log` resize lines, tpstats, cqlsh output and stress outputs. It does not read the summaries, `analysis.json` or `samples-heap.jsonl`. | output in `results/<stem>/run1/selfcheck.txt` |

Run order (run 1):

```bash
H=~/stage4-harness-run/mps
bash $H/unit-run.sh run1
( setsid nohup python3 $H/cluster-run.py all < /dev/null > ~/stage4-logs/mps/cluster-run1.out 2>&1 & )   # about 50 min
python3 $H/selfcheck.py ~/stage4-logs/mps/run1
```
