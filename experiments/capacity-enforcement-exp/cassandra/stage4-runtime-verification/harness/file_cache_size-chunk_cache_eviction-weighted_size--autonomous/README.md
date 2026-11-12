# Harness — file_cache_size-chunk_cache_eviction-weighted_size--autonomous

Stage-4 instruments for the case file of the same stem (autonomous, tiers B2 and B3, audit amendments AM1–AM6 in its section D).
Results: [`../../results/file_cache_size-chunk_cache_eviction-weighted_size--autonomous.md`](../../results/file_cache_size-chunk_cache_eviction-weighted_size--autonomous.md).

| File | Tier | What it does |
|---|---|---|
| `ChunkCacheCapProbeTest.java` | unit (B2c, B2d, AM4) | The B2c probe as a JUnit test. `PROBE_FCS` = F (MiB) is injected through `DatabaseDescriptor.daemonInitialization(Supplier<Config>)` with `file_cache_enabled = true`; writes a 256 MiB seeded-random file, opens it uncompressed with 64 KiB chunks through `ChunkCache.instance`, reads it sequentially and then in a seeded random order, samples `weightedSize()`, `size()` and the chunk-cache pool after every 64 KiB read; prints `PROBEINFO`, `PROBEFILE`, `PROBEPASS` (per pass), `PROBE` (B2d line, plus misses and evictions = misses − entries) and `PROBEAFTERCLOSE` to `$PROBE_OUT`. |
| `unit-run.sh` | unit (B2e) | Copies the probe into `test/unit/org/apache/cassandra/cache/` of `/mydata/jingsong-cass-s4/o06/src`, runs one `ant testsome` (fresh JVM) per F, keeps the junit XML and the PROBE lines under `/mydata/jingsong-cass-s4/o06/logs/<run>/unit/`, removes the probe and any `ccprobe*` file. |
| `mkconf.py` | cluster (B3a, AM3) | Writes the node's `cassandra.yaml` (127.0.0.1, ports 7400/7401/9442, `file_cache_enabled: true`, `file_cache_size: <F>MiB`, `key_cache_size: 0MiB`, `disk_access_mode: mmap_index_only`, data under `/mydata/jingsong-cass-s4/o06/node`), `cassandra-env.sh` (JMX 7599, heap 2G / new 400M) and `jvm-server.options` (+`-XX:MaxDirectMemorySize=4G -XX:NativeMemoryTracking=summary`) into a separate conf dir (`CASSANDRA_CONF`). |
| `CcJmx.java` | cluster (B3d, AM4) | One JMX client (single-file `java CcJmx.java`), every 5 s one CSV row: ChunkCache Capacity/Size/Entries/Misses/Hits, chunk-cache pool Size/UsedSize/OverflowSize/Capacity, networking pool Size/OverflowSize, `java.nio` direct MemoryUsed/TotalCapacity/Count, heap used. Absent MBeans (cache disabled) are empty fields. |
| `cluster-run.sh` | cluster (B3c, B3e) | Starts the node at F=32, loads 1.5M × 1 KiB rows with LZ4 (AM2), flush, compact, checks LZ4 16 KiB; then per F ∈ {32, 96, 288, 2080}: restart with F, wait UN + binary + 30 s, baseline sample, start samplers (CcJmx, cqlsh `system_views.caches` every 5 s, `jcmd VM.native_memory summary` "Other" + RSS every 5 s), 3M uniform stress reads, 60 s tail, `nodetool info`. Stops the node at the end. Logs every step to `session.txt`. |
| `cluster-analyze.py` | cluster | Per-F readings and the B3f / B3g (AM6) checks from the raw files. |
| `selfcheck.py` | both | Re-parses the raw files with its own code for results §5. |

**Instrument check (2026-11-12, before run 1):** a shakedown of the probe at F=40 (not a design value; tables already frozen) ran the full
pipeline: `PROBEINFO` showed `getFileCacheSizeInMiB=40`, `cacheSize=8388608`, the file was wrapped by `ChunkCache$CachingRebufferer`, the
environment variable reached the forked JVM, cleanup left no `ccprobe*` file. The cluster sampler was checked live on the F=32 baseline
(rows with empty cache fields, pool and direct values present).
