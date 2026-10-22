# Harness — NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous

Instruments for the case file's section B (stage 4), written on 2026-10-22 after the design audit
([results §1](../../results/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md)). The sampler and the Byteman rule style
come from the `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` harness. Clone `~/cassandra-ncs`
(`cassandra-5.0.9`, `ant build-test`). Frozen run copy: `pc07:~/stage4-harness-run/ncs/` (with `SHA256SUMS`, and each
cluster run's `harness-sha256.txt`).

| File | What it is |
|---|---|
| `FreeUnusedPortionProbeTest.java` | The unit tier: B2e's test with amendment U2 (`dDirect` per row and `directDelta` per CTL line, from the JVM's direct `BufferPoolMXBean`) and fix D1 (`fill()` returns its buffers before `unsafeReset()`). Package `org.apache.cassandra.utils.memory`. |
| `unit-run.sh <outdir>` | Copies the test into the clone and runs it (`ant testsome`), extracts the `INFO/ROW/PUT/SHIFT/CTL` lines from the console log (fix D2), runs the shipped `BufferPoolTest#testPuttingUnusedPortion`, and removes the test file again. |
| `ncs.btm` | Byteman observation rules (K1): `made` (one trace line per networking-pool slab), `refuse` (`allocateMoreChunks` returned null), `gtrue`/`gfalse`/`gtiny` (the :1521 outcome at `Chunk.freeUnusedPortion` entry), `ovftrim` (trims of overflow buffers), and a `dump` line on `StorageService.getReleaseVersion()`. Parse- and type-checked with `org.jboss.byteman.check.TestScript` against the build (no errors). |
| `PoolSampler.java <jmx-port> <out.csv> <stop-file> [period_ms]` | One JMX connection per node; every 5 s it reads networking `Capacity`, `Size`, `UsedSize`, `OverflowSize`, `Hits`, `Misses`, and java.nio direct `MemoryUsed` and `Count`, then reads `ReleaseVersion` (which fires the `dump` line). Compiled into `classes/` of the run copy. |
| `cluster-run.sh <label> <NCS MiB>` | One NCS value: two nodes on 127.0.0.4 (seed, JMX 7204) and 127.0.0.6 (JMX 7206) from fresh copies of the tag's conf, 4 GiB heap, `-XX:MaxDirectMemorySize=2g`, and the agent. It takes a 30 s idle baseline, runs stress write `n=1500000` and read `n=1000000` at CL=ALL over native protocol v5 with 256 threads, then a 60 s tail. Both nodes are stopped and the data removed on any exit. Output goes to `~/stage4-logs/ncs/cluster/<label>/`. |
| `all-runs.sh` | Runs 4, 8, 16 and 128 MiB in order. |
| `analyze.py [dir]` | Builds the per-node tables and evaluates the rows of amendment K2b from the raw files (analysis only; edited once after V4 so that it skips runs still in progress). |
