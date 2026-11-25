# MAX_BUFFER_SIZE — verification solution  <!-- file: cases/max_buffer_size-roundbuffersize-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set: the constant's declaration), **linked**: [`DiskOptimizationStrategy.java:32`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java#L32) — `int MAX_BUFFER_SIZE = 1 << 16; // 64k` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive` — the constant is the upper clamp of the per-reader read buffer for uncompressed SSTable files read in `standard` access mode (`roundBufferSize` and `roundForCaching` both `min(..., MAX_BUFFER_SIZE)`), so each open data-file reader holds at most 64 KiB of direct memory however large the partitions are. It caps a per-buffer size, not a total: aggregate usage is K readers x 64 KiB. |
| Ground | — |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). For this capacity-set unit the "if statement" is the given line (the declaration);
> the clamps that apply it are also linked in A3.

## A. Constraint trace

**A1. The constraint.**
- Name: `DiskOptimizationStrategy.MAX_BUFFER_SIZE`.
- Kind: compile-time constant (implicitly `public static final int` field of an interface).
- Declaration: [`DiskOptimizationStrategy.java:32`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java#L32), `int MAX_BUFFER_SIZE = 1 << 16; // 64k`.
- Unit: bytes. Default 65536, a literal; the comment at `DiskOptimizationStrategy.java:26-31` says it was chosen for historical consistency, as a reasonable upper bound, and because the BufferPool "currently has a maximum allocation size of this" (the pool's normal-chunk size is in fact 128 KiB in this tree, `BufferPool.java:128`, so that remark is out of date).
- Companion lower bound: `MIN_BUFFER_SIZE = 1 << 12` (4096), `DiskOptimizationStrategy.java:23`.
- How it can be set: **not settable** — no yaml key, no `-D` property, no JMX. Changing it needs a source edit and a **clean** rebuild (being a compile-time constant it is inlined into callers such as `FileHandle.java:207` and `BigSSTableReaderLoadingBuilder.java:304`), then a restart.
- Not to be confused with the unrelated `DataOutputStreamPlus.MAX_BUFFER_SIZE` (`DataOutputStreamPlus.java:51`, `-Dcassandra.data_output_stream_plus_temp_buffer_size`, default 8192).

**A2. What it caps.** Off-heap (direct) memory: the size of the read buffer that each `RandomAccessReader` over an SSTable file allocates when the file is read through a `SimpleChunkReader` (uncompressed file, non-mmap). The quantity compared against the limit is the *buffer size* derived from the SSTable's estimated record size: for data files the `disk_optimization_estimate_percentile` (default 0.95) of `estimatedPartitionSize` (`SortedTableWriter.java:346`, `SortedTableReaderLoadingBuilder.java:57-58`), for BIG index files `indexFileLength / indexSummary.size()` (`BigTableWriter.java:169`, `BigSSTableReaderLoadingBuilder.java:299`). Secondary, non-memory use: the rate-limit quantum per rebuffer for throttled readers (`FileHandle.java:207`, `LimitingRebufferer.java:59-63`).

**A3. Mechanism.**
1. Buffer size from the record size. `DatabaseDescriptor.java:950-957` picks `SsdDiskOptimizationStrategy(disk_optimization_page_cross_chance)` (default `ssd`, page-cross chance 0.1, `Config.java:516-520`) or `SpinningDiskOptimizationStrategy`. `SsdDiskOptimizationStrategy.bufferSize` adds one 4 KiB page if `(r % 4096)/4096 >= chance` (`SsdDiskOptimizationStrategy.java:73-76`), spinning always adds one page (`SpinningDiskOptimizationStrategy.java:29`); both call `roundBufferSize`.
2. **First clamp** — [`DiskOptimizationStrategy.java:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java#L45-L49): `size <= 0` -> 4096; else round up to a 4 KiB multiple and `return (int)Math.min(size, MAX_BUFFER_SIZE)`. Outcome at the limit: any record size above ~60 KiB yields exactly 65536; nothing fails, the buffer is just smaller than one record.
3. The size is handed to `FileHandle.Builder.bufferSize(...)` (`SortedTableWriter.java:351-357`, `SortedTableReaderLoadingBuilder.java:63`, `BigTableWriter.java:171`, `BigSSTableReaderLoadingBuilder.java:303-307`; the BIG index builder also uses `MAX_BUFFER_SIZE` itself as the default when there is no index summary, `BigSSTableReaderLoadingBuilder.java:304`).
4. **Second clamp** — in `FileHandle.Builder.complete()` for an uncompressed, non-mmapped file, `chunkSize = DiskOptimizationStrategy.roundForCaching(bufferSize, ChunkCache.roundUp)` (`FileHandle.java:428`), which rounds to a power of two and clamps: [`DiskOptimizationStrategy.java:72`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java#L63-L72) `return Math.min(MAX_BUFFER_SIZE, ret);`. `ChunkCache.roundUp` = `file_cache_round_up`, default true only for `spinning` (`DatabaseDescriptor.java:580-581`).
5. A `SimpleChunkReader(channel, length, bufferType, chunkSize)` is built (`FileHandle.java:429`), wrapped by the chunk cache only if one is configured with capacity > 0 (`FileHandle.java:444-449`).
6. Every `createReader*()` (`FileHandle.java:132-157`) instantiates a `BufferManagingRebufferer.Aligned/Unaligned` (`SimpleChunkReader.java:58-64`) whose constructor takes `BufferPools.forChunkCache().get(chunkSize, OFF_HEAP)` (`BufferManagingRebufferer.java:42-46`) and keeps it until `closeReader()` returns it (`BufferManagingRebufferer.java:49-54`). Sizes <= 128 KiB come from the pooled slabs (`BufferPool.java:910-944`); larger ones are direct-allocated and counted as overflow (`BufferPool.java:233-239`).
7. Readers that hold this buffer: per-read data readers (`SSTableReader.java:1111`, `BigTableReader.java:334`), scanners for range reads and compaction (`SSTableScanner.java:78`, `SSTableSimpleScanner.java:76`), verifier/scrubber (`SortedTableVerifier.java:98-99`, `SortedTableScrubber.java:156-157`), SAI/SASI builders.

Paths that bypass or overshoot it:
- **Compressed tables (the default, LZ4 16 KiB chunks):** the reader is `CompressedChunkReader`, whose buffer size comes from the compression `chunk_length_in_kb` (`CompressedChunkReader.java:40-47,81`), not from this constant; a table with `chunk_length_in_kb: 1024` gets 1 MiB buffers.
- **mmap access** (`disk_access_mode: mmap`, or index files under the default `mmap_index_only`, `DatabaseDescriptor.java:533-537`): no read buffer; `bufferSize` only feeds `MmappedRegions` (`FileHandle.java:415-416`).
- **Chunk cache enabled** (`file_cache_enabled: true`): buffers become cache entries of `chunkSize` each (`ChunkCache.java:154`); per-entry size is still clamped by this constant, the total by `file_cache_size`.
- It caps only per-reader size: the number of concurrently open readers is unbounded by this constant, so aggregate = K x chunkSize.

**A4. Other consumers.** Of the same chunk-cache `BufferPool` / direct memory: compressed-chunk buffers (sized by `chunk_length_in_kb`), chunk-cache entries (`file_cache_size`), `SequentialWriter` buffers of flush/compaction writers, the networking pool (`networking_cache_size`, `BufferPools.java`), off-heap memtables, bloom filters, index summaries, commit-log segments, mmapped index files (page cache, not heap). The pool threshold `file_cache_size` (default min(512 MiB, heap/4), `DatabaseDescriptor.java:576-577`) does not stop allocation; beyond it the pool allocates unpooled (`BufferPool.java:904-924`).

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/io/util/DiskOptimizationStrategyTest.java:31-44,89-135` asserts the 65536 clamp of both methods (e.g. `roundBufferSize(10000000000000000L) == 65536`).
- `conf/cassandra.yaml:753-765` (file cache / buffer pool, `disk_optimization_strategy`), `Config.java:504-516` (javadoc: buffer "capped between 4 KiB minimum and 64 kb maximum by the DiskOptimizationStrategy").
- CASSANDRA-8630 is cited in the comment at `DiskOptimizationStrategy.java:29` (https://issues.apache.org/jira/browse/CASSANDRA-8630). Git history is not present in the copy.

## B. Verification solution

**B1. Claim under test.** For an uncompressed SSTable read in `standard` access mode with the chunk cache disabled, each open reader holds a direct buffer of `min(f(p95 partition size), MAX_BUFFER_SIZE)` bytes, so with partitions of 1 MiB the buffer per reader is 65536 bytes and K concurrently open readers use K x 64 KiB of direct memory; rebuilding with a different `MAX_BUFFER_SIZE` moves that per-reader amount to the new value. The claim is wrong if per-reader usage exceeds 64 KiB on the stock build, or does not change with the rebuilt constant.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Three build copies on local disk (never the shared tree):
```
mkdir -p ~/s3probe && for v in v64 v32 v1m; do rsync -a ~/cassandra-5.0.9/ ~/s3probe/$v/; done
sed -i 's/int MAX_BUFFER_SIZE = 1 << 16;/int MAX_BUFFER_SIZE = 1 << 15;/' ~/s3probe/v32/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java
sed -i 's/int MAX_BUFFER_SIZE = 1 << 16;/int MAX_BUFFER_SIZE = 1 << 20;/' ~/s3probe/v1m/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java
grep -n "MAX_BUFFER_SIZE =" ~/s3probe/*/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java   # expect 16, 15, 20
for v in v64 v32 v1m; do (cd ~/s3probe/$v && ant realclean && ant build-test) || break; done
```
> **Amendment A1 (stage-4 audit, 2026-11-24; paths only, B2f/B2g unchanged).** Work directory `W=/mydata/jingsong-cass-s4/o120` on the run node in place of `~`: the three copies are `cp -a /mydata/s4/cassandra-base $W/s3probe/<v>` (a `copy-source.sh` copy of the repository's `systems/cassandra/source/`, 5.0.9, unmodified), patched with the two `sed` lines above, then `ant realclean && ant build-test` each. `~/s3probe` below means `$W/s3probe`, `~/s3node/<v>` means `$W/s3node/<label>` (one directory per cluster run), and scripts and the probe are read from `$W/harness/` (copy of the harness folder). Outputs go to `$W/run1/`.

`realclean` is required because the constant is inlined into other classes. JVM options: those of `ant testsome` (test conf `test/conf/cassandra.yaml`: `ssd`, `file_cache_round_up` unset -> false, `ChunkCache.roundUp == false`). The probe creates FileHandles **without** a chunk cache so each reader owns a buffer.

Test source `test/unit/org/apache/cassandra/io/util/MaxBufferSizeProbeTest.java` (same file in each copy; same package to read the protected `buffer` field):
```java
package org.apache.cassandra.io.util;

import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

public class MaxBufferSizeProbeTest
{
    static final long[] RECORD_SIZES = { 1000, 10000, 30000, 65536, 100000, 200000, 1L << 20, 16L << 20 };
    static final int K = 32;

    @BeforeClass
    public static void setup() { DatabaseDescriptor.daemonInitialization(); }

    @Test
    public void probe() throws Exception
    {
        File f = FileUtils.createTempFile("probe", ".db");
        byte[] data = new byte[4 << 20];               // 4 MiB > any buffer under test
        new Random(42).nextBytes(data);
        Files.write(f.toPath(), data);
        BufferPool pool = BufferPools.forChunkCache();
        System.out.println("PROBE MAX_BUFFER_SIZE=" + DiskOptimizationStrategy.MAX_BUFFER_SIZE);
        DiskOptimizationStrategy[] strategies = { new SsdDiskOptimizationStrategy(0.1), new SpinningDiskOptimizationStrategy() };
        for (DiskOptimizationStrategy s : strategies)
            for (long r : RECORD_SIZES)
            {
                int bufferSize = s.bufferSize(r);
                try (FileHandle fh = new FileHandle.Builder(f).mmapped(false).bufferSize(bufferSize).complete())
                {
                    long used0 = pool.usedSizeInBytes(), over0 = pool.overflowMemoryInBytes();
                    List<RandomAccessReader> readers = new ArrayList<>();
                    for (int i = 0; i < K; i++) { RandomAccessReader rr = fh.createReader(); rr.readByte(); readers.add(rr); }
                    long used1 = pool.usedSizeInBytes(), over1 = pool.overflowMemoryInBytes();
                    System.out.printf("PROBE strategy=%s r=%d bufferSize=%d chunk=%d bufCap=%d dUsed=%d dOverflow=%d perReader=%d%n",
                                      s.getClass().getSimpleName(), r, bufferSize, fh.rebuffererFactory().chunkSize(),
                                      readers.get(0).buffer.capacity(), used1 - used0, over1 - over0, (used1 - used0) / K);
                    for (RandomAccessReader rr : readers) rr.close();
                }
            }
        f.tryDelete();
    }
}
```
> **Amendment A2 (stage-4 audit, 2026-11-24; compile fix, B2f/B2g unchanged).** `RebuffererFactory` declares no `chunkSize()` (it is declared by `ChunkReader`, `ChunkReader.java:44`), so the line above does not compile. A FileHandle built without a chunk cache has the `SimpleChunkReader` itself as its factory (`FileHandle.java:429`, `maybeCached` returns the reader when `chunkCache == null`), so the probe prints `((ChunkReader) fh.rebuffererFactory()).chunkSize()`. Same observable.

**B2b. Knobs.** (1) The constant, by build copy: `v32` = 32768, `v64` = 65536 (stock), `v1m` = 1048576 — one below, the actual, one far above (and above the pool's 128 KiB normal chunk, so it also exercises the overflow path). (2) The record size `r` (the check's input) in `RECORD_SIZES`, spanning below, at and far above the cap. (3) Strategy ssd vs spinning.

**B2c. Workload.** K = 32 readers opened simultaneously on one 4 MiB uncompressed file, each forced to rebuffer once (`readByte`). For r = 1 MiB on v64, uncapped sizing would ask for 1 MiB per reader (32 MiB total); the cap makes it 64 KiB (2 MiB total). r >= 65536 on v64 already reaches the cap; r = 16 MiB is 256x past it.

**B2d. Observables and instruments.** Per (strategy, r): `bufferSize` (output of `roundBufferSize`, clamp 1), `chunk` (`rebuffererFactory().chunkSize()`, after clamp 2), `bufCap` (actual `ByteBuffer.capacity()` held by a reader), `dUsed` / `dOverflow` (deltas of the chunk-cache pool's `usedSizeInBytes()` / `overflowMemoryInBytes()` across opening the 32 readers; these are the numbers behind the JMX gauges `BufferPool.chunk-cache.UsedSize/OverflowSize`, `BufferPoolMetrics.java:50-63`), `perReader = dUsed/K`. All read once, single thread. Not directly observable: physical RSS of pooled slabs (the pool reserves 8 MiB macro chunks, so RSS moves in steps, not per buffer) — that is why the pool's accounting is used here and the JVM direct counter is used in B3.

**B2e. Procedure.**
```
for v in v64 v32 v1m; do
  cp MaxBufferSizeProbeTest.java ~/s3probe/$v/test/unit/org/apache/cassandra/io/util/
  (cd ~/s3probe/$v && ant testsome -Dtest.name=org.apache.cassandra.io.util.MaxBufferSizeProbeTest) | tee ~/s3probe/unit-$v.log
  grep -h PROBE ~/s3probe/$v/build/test/output/TEST-org.apache.cassandra.io.util.MaxBufferSizeProbeTest*.xml ~/s3probe/unit-$v.log | sort -u > ~/s3probe/probe-$v.txt
done
```
Check the first line prints the expected `MAX_BUFFER_SIZE` for each copy.

> **Amendment A6 (stage-4 run 1, 2026-11-24; runbook defect D1, B2f/B2g unchanged).** Under `ant testsome` the test JVM routes `System.out` through a logger that writes one log line per `write` call, so each `printf` line arrives in pieces (`PROBE strategy=`, `SsdDiskOptimizationStrategy`, ` r=`, `1000`, …) and the `grep … | sort -u` above yields only `PROBE strategy=`. The pieces are rejoined in order from `unit-$v.log` instead: `grep 'SubstituteLogger.java:[0-9]* - ' unit-$v.log | sed 's/^.*SubstituteLogger.java:[0-9]* - //' | awk '/^PROBE /{if(rec!="")print rec; rec=$0; next} rec ~ /^PROBE strategy/ && rec !~ /perReader=-?[0-9]+$/ {rec=rec $0} END{if(rec!="")print rec}' > probe-$v.txt` (`harness/unit-run.sh`). The unit tier was restarted from its beginning.

**B2f. Predictions.** ssd strategy (chance 0.1), `roundUp=false`; `chunk = bufCap = perReader`, `dUsed = 32 x chunk`:

| r | v32 bufferSize / chunk | v64 bufferSize / chunk | v1m bufferSize / chunk |
|---|---|---|---|
| 1000 | 8192 / 8192 | 8192 / 8192 | 8192 / 8192 |
| 10000 | 16384 / 16384 | 16384 / 16384 | 16384 / 16384 |
| 30000 | 32768 / 32768 | 36864 / 32768 | 36864 / 32768 |
| 65536 | 32768 / 32768 | 65536 / 65536 | 65536 / 65536 |
| 100000 | 32768 / 32768 | 65536 / 65536 | 106496 / 65536 |
| 200000 | 32768 / 32768 | 65536 / 65536 | 204800 / 131072 |
| 1 MiB | 32768 / 32768 | **65536 / 65536** | 1048576 / 1048576 |
| 16 MiB | 32768 / 32768 | **65536 / 65536** | 1048576 / 1048576 |

`dOverflow = 0` everywhere except v1m with chunk 1048576 (`dOverflow = dUsed = 33554432`). On v64 no row exceeds `perReader = 65536`. Spinning: same caps (r=1 MiB -> 65536 on v64, 32768 on v32, 1048576 on v1m); small r differ by the extra page only.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| v64: perReader = 65536 for every r >= 65536; v32: 32768; v1m: grows to 1048576 | Claim confirmed at unit level: the per-reader buffer follows the constant. |
| v64: perReader > 65536 for some r (e.g. 1 MiB at r = 1 MiB) | Claim wrong: the clamp does not bound the allocated buffer. |
| bufferSize clamped but `bufCap`/`dUsed` larger than `chunk` | A path between FileHandle and the pool ignores the chunk size; claim wrong for real memory. |
| v1m equals v64 for r = 1 MiB | Patch not compiled in (stale inlined constant) — not confirmed; redo `realclean`. |
| dUsed = 0 for all rows | Pool accounting not seeing the buffers (e.g. ON_HEAP type) — not confirmed; use `bufCap` and B3. |
| Small-r rows (1000, 10000) differ between variants | Something other than the constant changed; investigate before concluding. |

**B2h. Controls.** Small-r rows (identical across all builds) show the variants differ only above the cap. v1m is the positive control: the same workload with a cap that does not bind at 1 MiB moves usage 16x. `chunk` vs `bufCap` vs `dUsed` cross-check that the computed size is what is actually allocated. Same file, same K, same thread for every row.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, JDK 11, local disk with >= 4 GiB free. Build each variant: `cd ~/s3probe/$v && ant realclean && ant jar` (v64, v1m required; v32 optional). Per run, a fresh node directory `~/s3node/$v` holding `data/`, `commitlog/`, `saved_caches/`, `hints/`, `logs/`. `conf/cassandra.yaml` in the build copy, changed only as:
```
cluster_name: s3probe
data_file_directories: [ /home/$USER/s3node/<v>/data ]     # absolute path
commitlog_directory: /home/$USER/s3node/<v>/commitlog
saved_caches_directory: /home/$USER/s3node/<v>/saved_caches
hints_directory: /home/$USER/s3node/<v>/hints
commitlog_total_space: 1024MiB
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
seed_provider: [ {class_name: org.apache.cassandra.locator.SimpleSeedProvider, parameters: [{seeds: "127.0.0.1:7000"}]} ]
disk_access_mode: mmap_index_only     # default: data files are 'standard'
file_cache_enabled: false             # default: each reader owns its buffer
disk_optimization_strategy: ssd       # default
compaction_throughput: 1MiB/s
```
JVM: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, `CASSANDRA_LOG_DIR=~/s3node/<v>/logs`, JMX local on 7199.

> **Amendment A4 (stage-4 audit, 2026-11-24; environment, B3f/B3g unchanged).** The yaml is written by `harness/mkyaml.py` from a pristine `conf/cassandra.yaml.orig`, setting exactly the keys above (paths per A1), fresh for every run. The run node's soft `ulimit -n` is 1024, so the run script sets `ulimit -n 100000` before `bin/cassandra` (stage-4 `environment.md` §7). The node is used by this run alone (node lock), so the default ports 7000/7199/9042 are used; they are checked free first.

**B3b. Knobs.** (1) Build variant (constant): v64 (stock), v1m (cap far above partition size; positive control), v32 optional. (2) Partition size S: 1 MiB (16 rows x 64 KiB, far above the cap) and 8 KiB (1 row x 8 KiB, below every cap; negative control). (3) Number of simultaneously open readers K = 32 (and K = 8 for v64 to check linearity). All set per run; nothing changes at runtime except `nodetool setcompactionthroughput`.

**B3c. Workload.** Table:
```
CREATE KEYSPACE p WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE p.t (pk text, ck int, v blob, PRIMARY KEY (pk, ck))
  WITH compression = {'enabled':'false'}
  AND compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};
```
Loader `~/s3probe/load.py` (uses the driver bundled for cqlsh):
```python
import os, subprocess, sys, glob
sys.path.insert(0, glob.glob(os.path.expanduser('~/s3probe/v64/lib/cassandra-driver-internal-only-*.zip'))[0])
from cassandra.cluster import Cluster
v, K, PARTS, ROWS, VSIZE = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
s = Cluster(['127.0.0.1']).connect()
ins = s.prepare("INSERT INTO p.t (pk, ck, v) VALUES (?, ?, ?)")
nt = os.path.expanduser('~/s3probe/%s/bin/nodetool' % v)
for k in range(K):
    for p in range(PARTS):
        for c in range(ROWS):
            s.execute(ins, ('s%d-p%d' % (k, p), c, os.urandom(VSIZE)))
    subprocess.check_call([nt, 'flush', 'p', 't'])
```
> **Amendment A3 (stage-4 audit, 2026-11-24; runbook fix, B3f/B3g unchanged).** The bundled zip holds the driver package under `cassandra-driver-3.29.0/` (as `bin/cqlsh.py` adds it), so `sys.path` gets `<zip>/cassandra-driver-3.29.0`; with the zip alone the import fails (`ModuleNotFoundError`, seen in an earlier stage-4 run). Paths per A1; the loader also prints one line per flush.
Sizes: S = 1 MiB: `python3 load.py <v> 32 16 16 65536` -> 32 SSTables x 16 partitions x 1 MiB = 512 MiB data. S = 8 KiB: `python3 load.py <v> 32 2048 1 8192` -> 32 x 16 MiB = 512 MiB. Then `nodetool compact p t` (major STCS compaction of all 32 SSTables); `CompactionTask.java:199-201` opens one scanner per SSTable up front, each holding a data-file reader buffer for the whole task. At 1 MiB/s, 512 MiB keeps the task running ~8.5 min, which is the sampling window. Arithmetic: v64 & S = 1 MiB: 32 x 65536 = 2 MiB; v1m: 32 x 1 MiB = 32 MiB, a 30 MiB difference, well above background noise.

**B3d. Observables and instruments.** Sampled every 5 s with `nodetool sjk mx` (bundled SJK):
- `org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=UsedSize` attr `Value` (buffers handed out + overflow);
- `...,name=OverflowSize` attr `Value`;
- `java.nio:type=BufferPool,name=direct` attr `MemoryUsed` (JVM direct memory actually allocated — the real resource);
- `nodetool compactionstats` (task running, 32 inputs).
Also `tools/bin/sstablemetadata` on one input SSTable: the Partition Size histogram gives the p95 bucket, from which B2f's function gives the expected chunk. Not directly observable: per-reader buffer size (no metric) — inferred as delta/K; pooled slabs reserve direct memory in 8 MiB macro chunks (`BufferPool.java:384-385,460`), so `MemoryUsed` for the pooled case moves in 8 MiB steps.

**B3e. Procedure.** For each run (v, S, K):
1. `mkdir -p ~/s3node/$v/{data,commitlog,saved_caches,hints,logs}`; edit yaml as B3a.
2. `cd ~/s3probe/$v && CASSANDRA_LOG_DIR=~/s3node/$v/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M bin/cassandra -p ~/s3node/$v/pid`; wait for `bin/nodetool status` UN. Confirm in `system.log`: `DiskAccessMode is standard, indexAccessMode is mmap`.
3. Create keyspace/table (B3c) with `bin/cqlsh 127.0.0.1`; `bin/nodetool disableautocompaction p t`.
4. Load with `load.py` (B3c); `bin/nodetool tablestats p.t | grep "SSTable count"` = K (32).
5. Baseline: sample the three MBeans 12 times at 5 s (`for i in $(seq 12); do for b in "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=UsedSize Value" "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=OverflowSize Value" "java.nio:type=BufferPool,name=direct MemoryUsed"; do set -- $b; echo "$(date +%s) $1 $(bin/nodetool sjk mx -mg -b "$1" -f $2 | tail -1)"; done; sleep 5; done >> ~/s3node/$v/base.txt`).
6. `bin/nodetool setcompactionthroughput 1`; `bin/nodetool compact p t &`; wait 20 s; confirm `compactionstats` shows the task; sample as in step 5 for 120 s into `during.txt`.
7. Let compaction finish (or `bin/nodetool stop COMPACTION`), sample 6 more times (`after.txt`).
8. `bin/nodetool stopdaemon`; confirm no process: `pgrep -f "s3probe/$v" || echo none`; `rm -rf ~/s3node/$v`.
Runs: (v64, 1 MiB, 32), (v64, 1 MiB, 8), (v64, 8 KiB, 32), (v1m, 1 MiB, 32), (v1m, 8 KiB, 32), optional (v32, 1 MiB, 32).
Compute Δ = median(during) − median(base) per MBean.

> **Amendment A5 (stage-4 audit, 2026-11-24; sampling made exact, B3f/B3g unchanged).** Each `nodetool sjk mx` call starts a JVM, so one sample reads the three MBeans in parallel and records its epoch second; the real period is 5 s plus the call time. Each `during` sample also runs `nodetool compactionstats`; only `during` samples taken while it lists the compaction of `p.t` enter median(during), and fewer than 3 such samples matches the B3g row "compaction finished before sampling". Step 7 uses `nodetool stop COMPACTION` after the 120 s window. Step 8: the process check is `ps -eo cmd | grep '[C]assandraDaemon'` (stage-4 README), and the run's logs (`system.log`, samples) are kept while data, commit log, hints and caches are deleted. A run is driven by `harness/cluster-run.sh <v> <PARTS> <ROWS> <VSIZE> <K> <label>`, which logs every command, and analysed by `harness/cluster-analyze.py`.

> **Amendment A7 (stage-4 run 1, 2026-11-25; runbook defect D2, B3f/B3g unchanged).** `nodetool compact p t` starts a task of type `Major compaction` (`compactionstats` lists `Major compaction p t …`), (`CompactionManager.java:1061`, `OperationType.java:30`), and `nodetool stop COMPACTION` stops only tasks whose type equals `COMPACTION` (`CompactionManager.java:2217-2225`), so step 7 as written leaves the major compaction running: in run 1 it kept running through the six `after` samples and ended only at `nodetool stopdaemon` in step 8. Step 7 is therefore `nodetool stop MAJOR_COMPACTION` (or `nodetool stop -id <compaction id>`). The `after` samples carry no prediction in B3f, so run 1's readings (Δ = median(during) − median(base)) do not depend on this step; see the results file §3.

**B3f. Predictions.**

| Run | ΔUsedSize | ΔOverflowSize | Δ direct MemoryUsed |
|---|---|---|---|
| v64, 1 MiB, K=32 | ≈ 2 MiB (32 x 65536; accept 1.5–3 MiB) | ≈ 0 | 0 or one 8 MiB step (≤ 9 MiB) |
| v64, 1 MiB, K=8 | ≈ 0.5 MiB | ≈ 0 | ≤ 9 MiB |
| v64, 8 KiB, K=32 | ≈ 32 x (8 or 16 KiB) = 256–512 KiB | ≈ 0 | ≤ 9 MiB |
| v1m, 1 MiB, K=32 (positive control) | ≈ 32 MiB | ≈ 32 MiB | ≥ +32 MiB |
| v1m, 8 KiB, K=32 | same as v64, 8 KiB | ≈ 0 | ≤ 9 MiB |
| v32, 1 MiB, K=32 | ≈ 1 MiB | ≈ 0 | ≤ 9 MiB |

Per-reader ΔUsedSize/K on v64 with 1 MiB partitions = 64 KiB, independent of K. The claim is wrong if v64 with 1 MiB partitions shows ΔUsedSize/K ≥ 128 KiB, or ΔOverflowSize ≥ 16 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| v64 ΔUsed ≈ 2 MiB, v1m ΔUsed ≈ ΔOverflow ≈ Δdirect ≈ 32 MiB | Confirmed: direct memory per open reader follows the constant. |
| v64 ΔUsed/K ≥ 128 KiB, or large overflow/direct growth on v64 | Claim wrong: buffers above the cap are allocated on the real path. |
| v64 and v1m equal for 1 MiB partitions | Constant not governing (or not compiled in, or table compressed / mmap) — check yaml, `system.log`, `realclean`; if all correct, claim refuted. |
| v1m does not move (positive control failed) | Instruments do not see reader buffers — not confirmed. |
| ΔUsed scales with K (8 vs 32) at 64 KiB each | Expected: the constant caps per reader, not the total. |
| 8 KiB runs differ between v64 and v1m | Something other than the constant differs; result not attributable. |
| `compactionstats` shows fewer than 32 inputs / compaction finished before sampling | Limit never exercised — not confirmed; lower throughput or enlarge data. |

**B3h. Controls.** Positive control v1m (same data, same workload, cap that does not bind) must move usage by ~30 MiB. Negative control S = 8 KiB (below every cap) must be identical across builds. K = 8 vs 32 separates per-reader size from count. Baseline sampling subtracts background pool users (system tables are compressed and use their own chunk-sized buffers, unchanged across builds). Uncompressed table, chunk cache off and standard data access remove the bypass paths of A3.

**B4. Risks and cleanup.** Builds only in `~/s3probe/<v>` copies, never in the shared tree. Disk: per cluster run ≤ 512 MiB data + ≤ 512 MiB compaction output + ≤ 1 GiB commitlog (capped) on local disk; unit tier writes one 4 MiB temp file (deleted). Ports 7000/7199/9042 on 127.0.0.1 only. After each run: `nodetool stopdaemon`, `pgrep -f s3probe` empty (else `kill $(cat ~/s3node/<v>/pid)`), `rm -rf ~/s3node/<v>`; at the end `rm -rf ~/s3probe ~/s3node` once results are copied out. `ant testsome` JVMs exit on their own; check `pgrep -f junit` empty.

## C. Sources read

src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java
src/java/org/apache/cassandra/io/util/SsdDiskOptimizationStrategy.java
src/java/org/apache/cassandra/io/util/SpinningDiskOptimizationStrategy.java
src/java/org/apache/cassandra/io/util/FileHandle.java
src/java/org/apache/cassandra/io/util/SimpleChunkReader.java
src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java
src/java/org/apache/cassandra/io/util/LimitingRebufferer.java
src/java/org/apache/cassandra/io/util/MmappedRegions.java
src/java/org/apache/cassandra/io/util/CompressedChunkReader.java
src/java/org/apache/cassandra/io/util/RandomAccessReader.java
src/java/org/apache/cassandra/io/util/RebufferingInputStream.java
src/java/org/apache/cassandra/io/util/DataOutputStreamPlus.java
src/java/org/apache/cassandra/io/util/FileUtils.java
src/java/org/apache/cassandra/io/util/File.java
src/java/org/apache/cassandra/io/sstable/IOOptions.java
src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
src/java/org/apache/cassandra/io/sstable/format/SortedTableReaderLoadingBuilder.java
src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java
src/java/org/apache/cassandra/io/sstable/format/SSTableScanner.java
src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java
src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java
src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java
src/java/org/apache/cassandra/utils/memory/BufferPool.java
src/java/org/apache/cassandra/utils/memory/BufferPools.java
src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
src/java/org/apache/cassandra/cache/ChunkCache.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/cql3/statements/BatchStatement.java
src/java/org/apache/cassandra/db/compaction/CompactionTask.java
src/java/org/apache/cassandra/db/compaction/CompactionController.java
src/java/org/apache/cassandra/hints/HintsService.java
src/java/org/apache/cassandra/utils/EstimatedHistogram.java
src/java/org/apache/cassandra/tools/SSTableMetadataViewer.java
test/unit/org/apache/cassandra/io/util/DiskOptimizationStrategyTest.java
test/unit/org/apache/cassandra/io/util/RandomAccessReaderTest.java
test/conf/cassandra.yaml
conf/cassandra.yaml
build.xml
tools/cqlstress-example.yaml
lib/cassandra-driver-internal-only-3.29.0.zip (listed only)
https://issues.apache.org/jira/browse/CASSANDRA-8630 (cited from the source comment, not fetched)

## D. Stage-4 feedback

- **2026-11-25, stage-4 run 1 (Jingsong, node `pc91`, x86_64; results `results/max_buffer_size-roundbuffersize-size--autonomous.md`).** Audit: Ready (A1–A6 already applied; frozen sha256 `37fa5497…b250`, commit `bef6bc8a6`). **Unit: Confirmed** — B2g row 1: 48/48 rows equal B2f; per-reader buffer 65536 on v64 for every r ≥ 65536, 32768 on v32, 1048576 on v1m (with 32 MiB overflow at K=32). **Cluster: Confirmed** — B3g row 1 (and row 5): v64 1 MiB partitions ΔUsedSize 2.000 MiB = 32 x 64 KiB, overflow 0, Δdirect ≈ 0 (pooled); K=8 0.5 MiB; v1m ΔUsedSize = ΔOverflowSize = 32 MiB, Δdirect 31.99 MiB; v32 1.000 MiB; 8 KiB partitions 0.25 MiB in v64 and v1m alike. **Effect: caps** (per reader; total = K x cap). **Outcome class: true positive.** Runbook defect D2 fixed by amendment A7 (step 7); harness defects H1–H4 are in the results file §3. No run 2.
