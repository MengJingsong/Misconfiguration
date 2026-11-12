# Harness — file_cache_size-chunkcache-cachesize--autonomous

Stage-4 instruments for [the case file](../../../stage3-ai-deep-read/cases/file_cache_size-chunkcache-cachesize--autonomous.md)
(B2, B3 and audit amendments A1–A9). Results: [`../../results/file_cache_size-chunkcache-cachesize--autonomous.md`](../../results/file_cache_size-chunkcache-cachesize--autonomous.md).

| File | Tier | What it does |
|---|---|---|
| `ChunkCacheCapProbeTest.java` | unit | CQLTester probe (B2c–B2e, A3): LZ4 16 KiB table, 64 partitions × 200 rows × 16 KiB random blobs in 4 flushed batches, compaction disabled, two sequential read passes; writes `CAPACITY`/`CACHE_NULL`, `SAMPLE` every 256 reads (weighted, entries, misses, chunk-cache pool size/overflow/used, JVM direct `MemoryUsed`), `FINAL`, `MAX` to the file in `-Dfc.out`. `-Dfc.shakedown=true` uses 4 partitions (instrument check). |
| `unit-run.sh` | unit | Makes the yaml variants (B2e.1 + A2 ports), copies the probe into the tree, runs `ant testsome` once per value (32, 64, 128, 1024, off; each a fresh JVM), collects output, junit XML and the test log, removes the probe and the test data, runs `unit-analyze.py`. |
| `unit-analyze.py` | unit | Prints readings and each B2f / B2g condition as TRUE/FALSE facts; matches no row itself. |
| `JmxSampler.java` | cluster | One JMX connection (port 7499): every N ms appends cache `Capacity/Size/Entries/Misses`, chunk-cache pool `Capacity/Size/OverflowSize/UsedSize`, `java.nio` direct `MemoryUsed/Count` (A5). `once` mode for snapshots. |
| `cluster-run.sh` | cluster | Conf copy with 127.0.0.1 and ports 7300/7301/9342/7499 (A4), NMT on, `MAX_DIRECT_MEMORY_SIZE=2G` (A9); loads 500k × 1 KiB with `-schema compression=LZ4Compressor` (A8), flush, compact, checks the table is compressed; then C0–C3: restart, pool-limit log line, baseline snapshot (cqlsh `system_views.caches`, RSS, NMT, JMX), 10 s samplers, two 2M uniform reads with snapshots, 60 s idle, final snapshot, stop by PID. Logs every command in `cmd.log`; stops at the first failed check. |
| `cluster-analyze.py` | cluster | Prints readings and each B3f / B3g condition as TRUE/FALSE facts. |

Instrument checks before run 1 (2026-11-12): unit shakedown (`unit-run.sh shakedown shakedown`, fc64, 4 partitions): 805 entries for 12.6 MiB of data, misses = entries, second pass all hits — the known answer for data below the cap. The cluster script's yaml edit was dry-run on a copy of `conf/cassandra.yaml` (diff checked). Cluster attempt 1 found runbook defects D1 and D2 (results §3) before any measured read finished; it was stopped and the tier restarted.

Working tree, data and full logs: `/mydata/jingsong-cass-s4/o07/` on node0 (outside the repository).
