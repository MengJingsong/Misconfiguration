# Harness — file_cache_size-allocateMoreChunks-memoryUsageThreshold

Instruments for the case's section 9 (stage 4), as amended by the step-0 audit of 2026-10-14. Written 2026-10-14 after the
freeze. The results are in
[`../../results/file_cache_size-allocateMoreChunks-memoryUsageThreshold.md`](../../results/file_cache_size-allocateMoreChunks-memoryUsageThreshold.md).

| File | What it is | Checked how |
|---|---|---|
| `BufferPoolCeilingTest.java` | Unit tier. Package `org.apache.cassandra.utils.memory`; copy it into `test/unit/org/apache/cassandra/utils/memory/` of a clone at `cassandra-5.0.9`. Pools of 16 · 20 · 64 · 100 MiB, 128 KiB direct buffers to the ceiling and five past it, `tryGet`, put back. Prints `STAGE4 check` and `STAGE4 figures` lines (stdout and `-Dstage4.out`); a mismatch is recorded, and the test fails at the end. | `javac` against the clone's classpath before the run |
| `unit-run.sh [upstream\|harness\|all]` | Runs upstream `BufferPoolTest` and the harness test: `~/stage4-logs/fcs/unit/`. | — |
| `hold.btm` | Byteman: the 500 ms read hold at `UnfilteredRowMergeIterator.close()` (keyspace `ks1`), and counters for chunk-cache macro chunks made, refusals and overflow allocations, with a `dump` line on every `StorageService.getReleaseVersion()` (`nodetool version`). Line formats in the file's header. | Byteman `TestScript`: no errors (re-run by `cluster-run.py` before every start); `Submit -l` lists the rules |
| `PoolSampler.java` | One JMX connection; one CSV row per second with every pool gauge and the JDK's direct-pool `MemoryUsed` read in one pass. | the instrument run |
| `send-cql.py` | Bundled Python driver, protocol 5: `probe`, `load <pass>` (2,000 partitions × 4 rows of 1 KiB), `read <C> <seconds>` (slice reads, *C* outstanding). | `probe` prints the protocol |
| `make-node-yaml.sh <MiB\|default>` | The tag's yaml plus `concurrent_reads: 256`, `native_transport_max_threads: 256`, `file_cache_size: <n>MiB`. | prints its diff into the log |
| `netty-probe.btm` | **Supplementary, not used by the counted runs** (written after run 1): on each `nodetool version`, Netty's no-cleaner direct memory and the chunk-cache pool's full vs partial recycle counts. Run by appending it to a *copy* of `hold.btm` in a separate harness copy (`~/stage4-harness-run/fcs-supp/`) with `HOME` pointed at a separate log root, `cluster-run.py value default`. | `TestScript`: no errors |
| `cluster-run.py build\|instrument\|value <v>\|compare` | The cluster tier (9e as amended). Logs `session.log`, `summary.txt` (`EXPECTED:` lines), `samples.csv`, `phases.csv`, `nmt/` + `nmt.csv`, `bm.trace`, `result.json`, `system.log`. Stops on a failed instrument or dataset check; stops the node on any exit. | the instrument mode |

Copy the folder to the node (`~/stage4-harness-run/fcs`) and compare `md5sum` before a run. The node's clone is `~/cassandra-run1` at
commit `b5f2a54` (`cassandra-5.0.9`).
