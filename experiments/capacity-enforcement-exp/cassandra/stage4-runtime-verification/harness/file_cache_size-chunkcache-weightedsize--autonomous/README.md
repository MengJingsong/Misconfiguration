# Harness — file_cache_size-chunkcache-weightedsize--autonomous

Stage-4 instruments for the case file
[`file_cache_size-chunkcache-weightedsize--autonomous`](../../../stage3-ai-deep-read/cases/file_cache_size-chunkcache-weightedsize--autonomous.md)
(audit amendments AM1-AM8 in its section D). Results:
[`results/file_cache_size-chunkcache-weightedsize--autonomous.md`](../../results/file_cache_size-chunkcache-weightedsize--autonomous.md).

| File | Tier | What it is |
|---|---|---|
| `ChunkCacheCapTest.java` | unit (B2) | The test of case-file B2a verbatim, plus the `O05 EVID` line of AM7 (misses and requests of the chunk cache, printed after the FINAL line). Copied into `test/unit/org/apache/cassandra/io/util/` of the local tree. |
| `unit-run.sh` | unit | `build`: copy the test in, `ant build-test`. `runs`: `ant testsome` for `fcs.mib` = 32, 33, 64, 128, 256 and the probe (64, `hold.chunks=1024`), each in its own JVM (B2e), then the leftover checks (B2e step 7). |
| `unit-analyze.py` | unit | Joins the test's printf fragments (the junit log has one `SubstituteLogger` line per write) and checks every B2f cell and B2g row; prints `EXPECTED PASS/FAIL` lines. |
| `O05Jmx.java` | cluster (B3) | One JMX read of the B3d MBeans in bytes (AM5): ChunkCache Capacity/Size/Entries/Requests/Misses, BufferPool chunk-cache Size/OverflowSize/UsedSize/Capacity, networking Size, `java.nio` direct MemoryUsed/Count/TotalCapacity, heap used. |
| `cluster-run.py` | cluster | B3e as amended: one node on 127.0.0.1 (storage 7300, ssl 7301, JMX 7499, native 9342), heap 2G, `MaxDirectMemorySize=4G`, NMT summary; stress write 4,000,000 rows (LZ4, AM3), flush, wait for 0 pending compactions (AM4); then for disabled, 64, 256, 512: restart with the setting, 60 s idle samples, 10 min read at 32 threads with samples every 30 s, 60 s post samples. Each sample: O05Jmx, `jcmd VM.native_memory summary` Other (committed), `RssAnon`. `shakedown` mode: 200,000 rows, 60 s reads, settings disabled and 40 (not a frozen value). Every exit stops the node and removes its data. |
| `cluster-analyze.py` | cluster | Per-setting tables and the B3f/B3g checks with the AM2/AM8 thresholds. |
| `freeze-pred.txt` | both | The frozen text of B2f, B2g, B3f, B3g (sha256 in results §1). |

**Instrument checks before run 1.** Unit: the test compiled in `ant build-test` (BUILD SUCCESSFUL, 1 min 42 s). Cluster: three
shakedown attempts found harness faults, fixed before run 1 (none is a reading of a frozen value): (1) unquoted `FIXED(5)` in the
stress command (bash syntax error) and a compaction-wait regex that expected `pending tasks:` (5.0 prints `pending tasks   0`);
(2) the stop routine trusted the pid file, which Cassandra removes before the JVM exits, so the next start found port 7499 busy;
(3) a stopped JVM held its listening sockets a few seconds after `/proc/<pid>/cmdline` emptied: the start now waits up to 90 s
for the ports. Shakedown 4 ran end to end (settings disabled and 40 MiB, 200,000 rows): every instrument returned values, the
analyzer ran. Its logs stay on the node (`/mydata/jingsong-cass-s4/o05/logs/cluster-shake*`).

**Notes.** A background `nohup … &` job ignores SIGINT; stop the runner with SIGTERM and the node by its pid. An inline
`ssh host 'ps … | grep -c CassandraDaemon'` counts its own shell (environment.md §6): use `grep '[C]assandraDaemon'` and match the
run directory.
