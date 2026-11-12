# Harness — commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous

Stage-4 instruments for the case file of the same stem (audit amendments M1-M10 in the case file). Working tree
`/mydata/jingsong-cass-s4/o44/src` (`copy-source.sh` copy, `ant build-test`); all run data under `/mydata/jingsong-cass-s4/o44/`.

| File | Tier | What it does |
|---|---|---|
| `PoolCapManagerTest.java` | unit, class 1 | BMUnit test modelled on `CommitLogSegmentBackpressureTest`: LZ4, 1 MiB segments, `CAP_N` (env) buffers, sync blocked by two Byteman rules; 64 × 256 KiB mutations from one writer thread; prints `O44 BASE` (u0, d0, w0), `O44 SAMPLE` at 3 s and 5 s (active segments, usedBuffers, atLimit, direct delta, waits, writer alive, writer parked in `awaitAvailableSegment`), `O44 AFTER` (waitsAfter after the sync is released). |
| `PoolQueueCapacityTest.java` | unit, class 2 | `SimpleCachedBufferPool` alone: 10 buffers past N, release, count identical buffers returned (= idle buffers retained), N = 1 construction. |
| `unit-run.sh` | unit | copies the two classes into the tree, `ant build-test`, then `CAP_N=N ant testsome` for N = 3, 5, 8 with the BMUnit listener on 9491 (`-Dtest.jvm.args`); copies `build/test/logs/_jdk11/TEST-<class>.log` per run. |
| `unit-analyze.py` | unit | checks B2f/B2g as amended (M2-M4), prints PASS/FAIL per check and the matched row. |
| `Sampler.java` | cluster | JMX client (amendment M7): every 2 s `epoch_ms,direct MemoryUsed,direct Count,WaitingOnSegmentAllocation Count,segment files`. Run as `java Sampler.java <jmx-port> <commitlog-dir> <out.csv> <stop-file>`. |
| `cluster-run.py` | cluster | one node on 127.0.0.1 (storage 7400, ssl 7401, native 9442, JMX 7599), per value: wipe, write conf (B3a as amended M5, M10), start with `MAX_HEAP_SIZE=4G MAX_DIRECT_MEMORY_SIZE=3G` and NMT, wait UN + binary, 30 s idle, `cassandra-stress` 180 s (M6 port fix), NMT and `du` every 30 s, stop (M8). Values `3 6 12 24 mmap6`. |
| `cluster-analyze.py` | cluster | windows and thresholds of amendment M9, matched B3g row. |
| `selfcheck.py` | both | re-reads the committed excerpts under `results/<stem>/run1/` independently of the analyzers. |

Instrument checks: class 1's Byteman rules are those of the upstream `CommitLogSegmentBackpressureTest`; the first sample of every run
shows the writer parked in `AbstractCommitLogSegmentManager.awaitAvailableSegment` and `atLimit=true` (rules fired, sync blocked).
`Sampler.java` compiled with `javac` before the run; its first idle lines were checked against NMT "Other" (216,424,646 B vs 227,754 KB).

Harness faults found and fixed during run 1 (none changes a threshold; listed in the results file, section 3):
- the first `ant build-test` failed on a missing import in `PoolCapManagerTest.java` (no test ran);
- D1: `TEST-<class>.log` is appended across `ant testsome` runs, so `unit-analyze.py` first read N = 3's lines for every N; it now keeps only the lines of its own `CAP_N`;
- D3: Cassandra deletes its pid file when shutdown starts, so `stop_node()` reported a still-draining node as stopped (the N = 12 node then held JMX 7599 and the first N = 24 start failed); `cluster-run.py` now tracks the PID itself and refuses to start while an o44 node is alive, and `cluster-analyze.py` reads the last attempt of a value.
