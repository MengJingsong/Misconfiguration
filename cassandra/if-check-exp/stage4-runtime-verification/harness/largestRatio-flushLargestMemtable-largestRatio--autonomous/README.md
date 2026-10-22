# Harness — largestRatio-flushLargestMemtable-largestRatio--autonomous

Stage-4 harness for the autonomous case file (audit freeze sha256 `60974bb2…`; run-1 versions after runbook fixes D1
`54e8da0e…` (unit) and D2 `45a1ce01…` (cluster); see the results file
[§1](../../results/largestRatio-flushLargestMemtable-largestRatio--autonomous.md)). Written 2026-10-21 on `pc07`
(`node0.jason92-320876`), run from a copy `~/stage4-harness-run/lrt/` (md5 in `~/stage4-harness-run/lrt.md5`) against
`~/cassandra-lrt` (M-orig) and `~/cassandra-lrt-mut` (mutants), both `cassandra-5.0.9` (`b5f2a54210`). Logs go to
`~/stage4-logs/lrt/<run>/`. Another stage-4 session shared the host, so the node uses 127.0.0.4, JMX 7204 and
`~/stage4-lrt/`, and only `java` processes whose command line contains `cassandra-lrt` are ever stopped. Not committed.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `FlushLargestSelectionTest.java` | unit (B2) | `extends CQLTester`, package `org.apache.cassandra.db.memtable`. `u1Selection` (three tables, the test's own argmax vs the CFS `flushLargestMemtable()` switched), `u2ZeroRatio` (after flushing every CFS; R3 / D1: up to 20 attempts until every ratio is 0 at the call), `u3CapSkew` / `u3CapEven` (4 writers, 13,000 × L/32 MiB rows each, 30 s per insert, a 5 ms sampler of `MEMORY_POOL.onHeap`; R2). Result lines go to `-Dprobe.out`. | `javac` against the clone; unit shakedown1 |
| `unit-run.sh <run> orig\|first\|never\|all` | unit (B2e) | Sets `memtable_heap_space` before the `memtable:` block of `test/conf/cassandra.yaml`, runs `ant testsome` per (build, L), applies and checks each mutant diff in `~/cassandra-lrt-mut` and rebuilds. M-never's JVM is given 240 s (harness fix H2). | shakedown1 |
| `unit-analyze.py <run>/unit` | unit | B2f/B2g checks as `EXPECTED:` lines. | — |
| `cluster-run.py <run> <arm>...` | cluster (B3e) | Arms `L256-skew L256-even L1024-skew L1024-even never`; per arm a fresh node directory and JVM (4 GiB, G1), the B3a yaml lines, stress with `no-warmup` and quoted options (R5), a JMX poll every 1 s (R6), the `system.log` window between the stress-start and stress-end offsets (R7), tablestats, `du`, then SIGTERM / SIGKILL after 60 s. Disk guard 25 GB free. `LRT_SCALE` divides `n` for shakedowns only. | shakedown2 (found H3), shakedown3 (found D2 and two parser bugs, H4) |
| `cluster-analyze.py <run>/cluster` | cluster | B3f/B3g (R6–R8, D2) checks as `EXPECTED:` lines; old gen after GC from `gc.log` (D2). | shakedown3 |
| `Jmx.java` | cluster | JMX client from the `concurrent_writes` harness (`poll`). | shakedowns |
| `diag-first-histo.sh <name>` | unit, SUPPLEMENTARY | After run 1: M-first, S-even, L = 128 MiB alone, with a class histogram of the test JVM every 1 s. | — |
| `selfcheck.py <run>` | both | Independent re-parse of the raw files (copied with its output to `results/<stem>/run1/`). | — |

Run order (run 1):

```bash
H=~/stage4-harness-run/lrt
bash $H/unit-run.sh run1 all
python3 $H/cluster-run.py run1 L256-skew L256-even L1024-skew L1024-even
# apply M-never in ~/cassandra-lrt-mut (line 251 -> Float.MAX_VALUE) and `ant build-test`, then:
python3 $H/cluster-run.py run1 never
python3 $H/cluster-analyze.py ~/stage4-logs/lrt/run1/cluster; python3 $H/unit-analyze.py ~/stage4-logs/lrt/run1/unit
python3 $H/selfcheck.py ~/stage4-logs/lrt/run1
```
