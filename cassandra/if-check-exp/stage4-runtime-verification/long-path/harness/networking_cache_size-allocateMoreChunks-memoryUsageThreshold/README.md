# Harness — networking_cache_size-allocateMoreChunks-memoryUsageThreshold

Instruments for the case's §9 (stage 4), written 2026-10-15 after the design audit (results
[§1](../../results/networking_cache_size-allocateMoreChunks-memoryUsageThreshold.md)), reusing the `file_cache_size` harness's
sampler and rule style. Clone `$CASSANDRA_HOME` (default `~/cassandra-run3`); node copy `~/stage4-harness-run/ncs/`.

| File | What it is |
|---|---|
| `NetworkingPoolCeilingTest.java` | Unit U2 (the ceiling on `recyclePartially = false` pools, frame-sized requests, six *T*) and U3 (the recycle contrast with a `Debug` hook), package `org.apache.cassandra.utils.memory`. |
| `NetworkingPoolConfigTest.java` | Unit U4: the real networking instance at 16 MiB through the raw config; CRC payloads filled as `Flusher` fills them; the −6 B drift. Own JVM. |
| `unit-run.sh [suffix]` | U1 upstream `BufferPoolTest`, `BufferPoolAllocatorTest`, then U2–U4. Output `~/stage4-logs/ncs/unit[-suffix]/`. |
| `net.btm` | Counting rules (`made` traced per slab; `refuse`, `overflow`, `ovfadd`/`ovfsub`, `payload_full/small`, `encoded`/`freed` of frame-sized buffers only, amended 2026-10-15) and a `dump` line on `StorageService.getReleaseVersion()`. |
| `PoolSampler.java` | Every second, one JMX pass: networking `Capacity`, `Size`, `UsedSize`, `OverflowSize`, `Hits`, `Misses`; chunk-cache `Size`, `OverflowSize`; `java.nio` direct; `ReleaseVersion` (a dump line). |
| `drv.py`, `stall-client.py <R> <stop>`, `send-cql.py` | Bundled driver path; the raw v5 client that never reads after READY (`SO_RCVBUF` 64 KiB, one self-contained CRC frame per QUERY, `SO_LINGER` 0 at close); probe, build (v4), big-insert (v5). |
| `make-node-yaml.sh <MiB\|default>` | `~/stage4-ncs/conf`: the tag's yaml, directories under `~/stage4-ncs/`, the knob. |
| `cluster-run.py <run> build \| instrument \| value <v> \| leak` | The lifetimes of 9e with `EXPECTED:` lines; heap 4G, NMT summary, `MaxDirectMemorySize` 8G, the agent. Output `~/stage4-logs/ncs/<run>/<label>/`. |
