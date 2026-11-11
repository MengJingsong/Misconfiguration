# compressed_read_ahead_buffer_size (JMX setter floor in setCompressedReadAheadBufferSizeInKb) — verification solution  <!-- file: cases/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:2556`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2556) (`2556#1`, `sizeInKb < 256`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available in the sandbox), 2026-10-25, band D triage |
| Estimate | `positive` (scoped: sets a per-scanner buffer size, not an aggregate cap). The value set here becomes the size of the direct (off-heap) read-ahead buffer that each sequential scan of a compressed SSTable allocates, one per thread per file (`CompressedChunkReader.java:236-238`, `ThreadLocalReadAheadBuffer.java:84`), freed when the scan ends (`ThreadLocalReadAheadBuffer.java:147,155`). Off-heap usage of concurrent scans therefore follows the knob linearly (k open scanners use k × size). Line 2556 only rejects runtime values under 256 KiB, and that includes `0`, which startup accepts as "disabled". |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `compressed_read_ahead_buffer_size` is a configuration entry ([`Config.java:341`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L341), `DataStorageSpec.IntKibibytesBound`, default `"256KiB"`). The shipped `conf/cassandra.yaml` does not list it. It can be set in two ways:
- **Startup (yaml).** [`DatabaseDescriptor.java:960-961`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L960-L961) rejects values in (0, 256) KiB with a `ConfigurationException`. `0` is accepted and disables the feature.
- **Runtime (JMX).** `StorageServiceMBean.setCompressedReadAheadBufferInKB(int)` ([`StorageServiceMBean.java:815`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageServiceMBean.java#L815), implemented at [`StorageService.java:1941-1944`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L1941-L1944)) calls `DatabaseDescriptor.setCompressedReadAheadBufferSizeInKb` ([`DatabaseDescriptor.java:2554-2560`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2554-L2560)). That method:
  - throws `IllegalArgumentException` for `sizeInKb < 256` (target line 2556). This includes `0`, so the feature cannot be disabled at runtime.
  - otherwise builds the value through `createIntKibibyteBoundAndEnsureItIsValidForByteConversion` (`:2559`, `:4581-4586`). This throws `ConfigurationException` when the byte value is `< 0` or `> Integer.MAX_VALUE - 1` (`:4593-4594`), so the largest accepted value is 2097151 KiB.

Getters: `getCompressedReadAheadBufferSize()` returns bytes (`:2544-2547`), and `getCompressedReadAheadBufferSizeInKB()` (`:2549-2552`) is exposed as JMX `CompressedReadAheadBufferInKB` ([`StorageService.java:1935-1938`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L1935-L1938)). No nodetool command exists.

A runtime change does not need a restart, but it only affects SSTable readers built after the change. The value is read once, in the `CompressedChunkReader.Standard` constructor ([`CompressedChunkReader.java:236`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/CompressedChunkReader.java#L236)).


**Limit type (2026-10-29).** not-a-case: the entry-pointer `if` validates the value against a literal minimum (`< 256`), not usage against a capacity ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)). The verification solution and the stage-4 results are kept as filed.
**A2. What it caps.** It caps off-heap memory: it is the capacity in bytes of each read-ahead `ByteBuffer`. LZ4, the default compressor, prefers `BufferType.OFF_HEAP` (`LZ4Compressor.java:240-243`), which means `ByteBuffer.allocateDirect` (`BufferType.java:33-36`). The quantity compared at 2556 is the requested size itself in KiB; no usage figure is compared. The memory that follows from the setting is the number of open scan buffers × the size.

**A3. Mechanism.**
1. When the data file is not mmapped, `FileHandle.Builder.complete` builds a `CompressedChunkReader.Standard` for a compressed data file ([`FileHandle.java:424`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java#L424)). With the default `disk_access_mode: mmap_index_only`, data is read with `standard` access ([`DatabaseDescriptor.java:533-536`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L533-L536), [`Config.java:122`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L122)). Mmapped data files use `CompressedChunkReader.Mmap` ([`FileHandle.java:411`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java#L411)), which has no read-ahead buffer.
2. The `Standard` constructor reads the size. It creates a `ScanCompressedReader` only if `size > 0 && size > chunkLength` ([`CompressedChunkReader.java:236-238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/CompressedChunkReader.java#L236-L238)); otherwise `scanReader` is null and no buffer is ever allocated.
3. A sequential scan opens the data file with `openDataReaderForScan` ([`SSTableScanner.java:78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableScanner.java#L78), [`SSTableSimpleScanner.java:76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableSimpleScanner.java#L76), [`SSTableReader.java:1383-1385`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java#L1383-L1385)). That path reaches `instantiateRebufferer(true)` → `forScan()` → `scanReader.allocateResources()` → `ThreadLocalReadAheadBuffer.allocateBuffer()` (`CompressedChunkReader.java:93-96,240-246,201-205`). This allocates `bufferType.allocate(bufferSize)` ([`ThreadLocalReadAheadBuffer.java:79-86`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/ThreadLocalReadAheadBuffer.java#L79-L86)). The buffer lives in a `FastThreadLocal<Map<filePath, Block>>` (`:41-48`), so there is one buffer per (thread, data file).
4. When the reader closes, `BufferManagingRebufferer.closeReader` → `releaseUnderlyingResources` → `deallocateResources` → `clear(true)` → `FileUtils.clean` ([`BufferManagingRebufferer.java:50-55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java#L50-L55), `CompressedChunkReader.java:248-253,207-211`, [`ThreadLocalReadAheadBuffer.java:132-150`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/ThreadLocalReadAheadBuffer.java#L132-L150)). The direct buffer is freed at that point.
5. When the limit check at 2556 trips (value < 256), an exception is thrown and the old value is kept. When the value passes, it is stored. Nothing bounds the number of buffers: a compaction over N SSTables holds N buffers on one thread, and C concurrent scanning threads hold C × N.

There are two bypasses:
- When the chunk cache is enabled (`file_cache_enabled`, default false, [`Config.java:499`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L499)), `maybeCached` wraps the reader. `ChunkCache`'s rebufferer ignores `isScan` ([`ChunkCache.java:261-265`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L261-L265)), so no read-ahead buffer is used.
- Mmapped data files never use the buffer (step 1).

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), A3 (audit statement: when a reader picks up the size, what a reader opened before a change keeps, and three corrections; no claim changed).** Checked in `~/cassandra-src` at `cassandra-5.0.9`. **When the size is read.** `DatabaseDescriptor.getCompressedReadAheadBufferSize()` is called in exactly one place on the read path, the `CompressedChunkReader.Standard` constructor ([`CompressedChunkReader.java:234-238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/CompressedChunkReader.java#L234-L238)); the value goes into the `final int bufferSize` of the reader's `ThreadLocalReadAheadBuffer` (`ThreadLocalReadAheadBuffer.java:50, 53-58`) and is never re-read: every later `allocateBuffer()` / `fill()` uses that field (`:74-88, 95-104`). `Standard` is built only in `FileHandle.Builder.complete` for a compressed, non-mmapped data file ([`FileHandle.java:420-425`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java#L420-L425)), i.e. when a new data `FileHandle` is built: an SSTable opened from disk (start-up, `SSTableReader.open`, import/refresh, a streamed SSTable) or a writer's final or early-opened reader (a flush, a compaction output). **What a reader opened before a change keeps.** Its own size, for its whole life: every clone of a reader (`cloneWithNewStart`, `cloneWithRestoredStart`, `cloneAndReplace`, [`BigTableReader.java:516-557`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L516-L557)) is rebuilt through `unbuildTo(…, sharedCopy=true)`, which hands over `dfile.sharedCopy()` ([`SSTableReader.java:640-644`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java#L640-L644)), and `FileHandle.sharedCopy()` keeps the same `rebuffererFactory` ([`FileHandle.java:122-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java#L122-L125)). So after `setCompressedReadAheadBufferInKB(v)` ([`StorageService.java:1941-1945`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L1941-L1945)) the SSTables that already exist keep the old size until they are replaced (compaction) or the node restarts; only SSTables written or opened afterwards use v. A reader whose `Standard` was built when the size was ≤ chunk length has no `ScanCompressedReader` and never gets one (`:237-238`). The per-thread map is keyed by file path, not by reader (`ThreadLocalReadAheadBuffer.java:41-48, 90-93`), so an old and a new reader of the same file scanned on the same thread share one block, whose capacity is set by whichever allocated it (not exercised: the runs scan each reader on its own threads). **Setter.** `sizeInKb < 256` → `IllegalArgumentException("compressed_read_ahead_buffer_size_in_kb must be at least 256KiB")` before anything is stored ([`DatabaseDescriptor.java:2554-2557`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2554-L2557)); otherwise `createIntKibibyteBoundAndEnsureItIsValidForByteConversion` (`:4581-4586`) throws `ConfigurationException("compressed_read_ahead_buffer_size must be positive value <= 2147483646B, but was <n>B")` above 2,097,151 KiB (`:4591-4598`), again before storing; an accepted value logs INFO `set compressed read ahead buffer size to <v>KiB` ([`StorageService.java:1944`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L1944)). A rejected value logs nothing on the node: the exception goes to the caller (over JMX wrapped in `javax.management.RuntimeMBeanException`). **Other direct memory a scan adds** (bounds the bands below): (1) each scanning thread's `ThreadLocalByteBufferHolder` keeps one direct buffer of the largest compressed chunk it read plus 4 CRC bytes ([`ThreadLocalByteBufferHolder.java:69-80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/ThreadLocalByteBufferHolder.java#L69-L80), [`CompressedChunkReader.java:173-176`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/CompressedChunkReader.java#L173-L176)); for a 16 KiB LZ4 chunk that is ≤ 4 + 16,464 + 4 = 16,472 B (LZ4 bound of 16,384 B plus the 4-byte length header), for a 1 MiB chunk ≤ 1,052,712 B; it is not freed when the scanner closes. (2) each scanner's rebufferer buffer comes from `BufferPools.forChunkCache()` ([`BufferManagingRebufferer.java:42-47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java#L42-L47)): from an 8 MiB macro-chunk allocated when the pool runs short (`BufferPool.java:128, 385, 443-460`), or allocated directly when the chunk exceeds 128 KiB (`:906-925, 233-238`) and freed on close (`:810-819`). Both are counted by `BufferPools.forChunkCache().sizeInBytes()` (`:274-277`: macro-chunks plus direct overflow), so the unit tier subtracts that pool's change from the direct-pool change. **Corrections to the filed text:** (a) B2a — the test `cassandra.yaml` does set both keys: `disk_access_mode: mmap_index_only` (`test/conf/cassandra.yaml:28`, → `standard` data access, fine) and **`file_cache_enabled: true`** (`:55`), which wraps every reader in `ChunkCache.CachingRebufferer` and skips `forScan()` ([`ChunkCache.java:261-265`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L261-L265)), so the filed unit tier would see no read-ahead buffer at all; (b) B3c — `cassandra-stress` creates its table **uncompressed** unless `-schema compression=…` is given (`tools/stress/src/org/apache/cassandra/stress/settings/SettingsSchema.java:140-143, 211`), not "default LZ4"; (c) B3c — `nodetool disableautocompaction` without a keyspace applies to the keyspaces that exist when it runs (`DisableAutoCompaction.java`, [`NodeTool.java:476-489`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tools/NodeTool.java#L476-L489)), so run before the stress run that creates `ra_<v>` it leaves that keyspace's compaction on and 16 flushes would be compacted at 4 SSTables; (d) B3c — `bin/cassandra` sets `-XX:MaxDirectMemorySize` to a quarter of RAM (`conf/cassandra-env.sh:57-66, 139-158`; 8192M on this machine), not "= Xmx".

**A4. Other consumers.** Other consumers of off-heap memory sit outside this constraint:
- `ThreadLocalByteBufferHolder` buffers for compressed chunks (`CompressedChunkReader.java:164`).
- The chunk/networking `BufferPool`s (`BufferManagingRebufferer.java:45`).
- Memtables (offheap allocators).
- Netty.
- Bloom filters, index summaries, and off-heap merkle trees.

**A5. Evidence beyond the source.** CASSANDRA-15452, "Improve disk access patterns during compaction and range reads" (`CHANGES.txt:148`), https://issues.apache.org/jira/browse/CASSANDRA-15452. JDK `BufferPoolMXBean` (`java.nio:type=BufferPool,name=direct`), https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html.

## B. Verification solution

**B1. Claim under test.** The value accepted by `setCompressedReadAheadBufferSizeInKb` (≥ 256 KiB) determines the direct-memory buffer allocated per open SSTable scan on readers opened afterwards: direct memory used by k simultaneously open scans grows by about k × value and returns to baseline when the scans close. Values below 256 KiB, including 0, are rejected and leave the setting unchanged.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Clone to local disk, never inside the shared clone: `git clone --depth 1 --branch cassandra-5.0.9 <shared-clone-path> /local/c509 && cd /local/c509`. Put the test at `/local/c509/test/unit/org/apache/cassandra/io/util/ReadAheadSetterTest.java`. Build and run with `ant testsome -Dtest.name=org.apache.cassandra.io.util.ReadAheadSetterTest`; this builds main and test classes, and the test JVM has `maxmemory=1024m` (`build.xml:1153`). Do not change the test's `cassandra.yaml`: it does not set `disk_access_mode` or `file_cache_enabled`, so both keep their defaults.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2a.** This host (`environment-advisor.md`): run clone `$W/cassandra-run23` (`W=~/Library/Caches/stage4`; tag `cassandra-5.0.9`, `b5f2a54210`), built with `ant -Dlocal.repository=$W/m2 build-test`. The test (`harness/<stem>/ReadAheadSetterTest.java`) is copied to `$W/cassandra-run23/test/unit/org/apache/cassandra/io/util/ReadAheadSetterTest.java` and run with `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.io.util.ReadAheadSetterTest -Dtest.jvm.args="-Dstage4.out=<file> -Dstage4.label=<rep>"` (own JVM per run). **The test yaml is changed** (correction (a) of the A3 amendment): before each run it is restored with `git checkout` and line 55 is set to `file_cache_enabled: false`; nothing else is changed (the knob stays unset: default 256 KiB at start); after the last run it is restored and the test removed (`git status` clean). Script `unit-run.sh`.

**B2b. Knobs.** Set `sizeInKb` through `StorageService.instance.setCompressedReadAheadBufferInKB(v)`, which is the JMX path into line 2556.
- **Rejection values:** `0, 128, 255` (expect an exception), `2097152` (expect `ConfigurationException` from `:4594`).
- **Accepted values:** `256, 1024, 4096, 16384`, which span 64×. `2097151` is accepted but is only checked through the getter and never allocated.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2b.** Values as filed, all set through `StorageService.instance.setCompressedReadAheadBufferInKB`; `2097151` is set after the rejections and read back (it is in B2b but not in the filed skeleton). One control added (B2h): **stale reader** — after the loop (knob at 16384), T = 8 scanners on the table's **live** reader, which was opened by the flush at the start-up value 256 KiB.

**B2c. Workload.**
1. Create a table with `compression = {'class':'LZ4Compressor','chunk_length_in_kb':16}`, insert 20 000 rows of 1 KiB random blob (about 20 MiB), and flush to one SSTable.
2. For each accepted value v, set v, then open a fresh reader on that SSTable's descriptor: `SSTableReader.open(cfs, sstable.descriptor)` (`SSTableReader.java:359`). This builds a new `Standard` reader that reads v.
3. Open T scanners (`reader.getScanner()`) on T threads, T ∈ {1, 8}. Each thread reads one partition and then waits at a barrier while the scanner is open.

The limit is reached by construction: every v ≥ 256 KiB is greater than the 16 KiB chunk, so `scanReader` is created.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2c.** As filed: one LZ4 table (`chunk_length_in_kb: 16`), 20,000 inserts of 1,024 random bytes (`Random(1)`), one `flush()` → one SSTable. Gate control (B2e): a second table `chunk_length_in_kb: 1024` with the same 20,000 inserts and one flush. For each v the fresh reader is `SSTableReader.open(cfs, descriptor)`, released after its cycles.

**B2d. Observables and instruments.**
- `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` entry `direct`: `getMemoryUsed()` and `getCount()`. Sample on the main thread at three points: before the scanners open, while all T are held at the barrier, and after all close.
- `DatabaseDescriptor.getCompressedReadAheadBufferSizeInKB()` after each setter call.

Per-thread buffer identity cannot be observed without reflection. Instead, read the size via `getCount()` deltas together with the `MemoryUsed` delta.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2d (instruments added; the filed observables are kept).** Per cycle, at the filed three points (before / all T held open / after close): `direct` `getMemoryUsed()`, `getCount()`, and **`BufferPools.forChunkCache().sizeInBytes()`** (A3 amendment). Derived: `openDelta`, `countDelta`, `closedDelta` as filed; `poolOpen`, `poolClosed` = the chunk-cache pool's change to the open / closed point; **`openDeltaC = openDelta − poolOpen`**, **`closedDeltaC = closedDelta − poolClosed`** (direct memory not from that pool). **Per buffer:** each worker thread, while it holds its scanner open, reads its own `ThreadLocalReadAheadBuffer.blockMap` by reflection and reports the number of entries with a buffer and, for the entry keyed by the reader's data file, the buffer's `capacity()` and `isDirect()`. **Per reader:** the size captured in the reader under test (its data `FileHandle.rebuffererFactory()` → `Standard.scanReader` → `ThreadLocalReadAheadBuffer.bufferSize`, by reflection; `null` scanReader recorded as `none`). Read-backs per run: live SSTable count, chunk length, factory class (`CompressedChunkReader$Standard`), `getFileCacheEnabled()` = false, `getDiskAccessMode()` = `standard`, the getter after every setter call. Output: `STAGE4` lines to `stage4.out`.

**B2e. Procedure.** Test skeleton (JUnit, extends `org.apache.cassandra.cql3.CQLTester`):
```java
@Test public void setterAndBuffers() throws Throwable {
  createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':16}");
  java.util.Random r = new java.util.Random(1);
  for (int i = 0; i < 20000; i++) { byte[] b = new byte[1024]; r.nextBytes(b); execute("INSERT INTO %s (k, v) VALUES (?, ?)", i, java.nio.ByteBuffer.wrap(b)); }
  flush();
  ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
  Descriptor d = cfs.getLiveSSTables().iterator().next().descriptor;
  for (int bad : new int[]{0, 128, 255, 2097152}) {
    int before = DatabaseDescriptor.getCompressedReadAheadBufferSizeInKB();
    try { StorageService.instance.setCompressedReadAheadBufferInKB(bad); System.out.println("ACCEPTED " + bad); }
    catch (RuntimeException e) { System.out.println("REJECTED " + bad + " " + e.getClass().getSimpleName()); }
    System.out.println("after " + bad + " getter=" + DatabaseDescriptor.getCompressedReadAheadBufferSizeInKB() + " before=" + before);
  }
  BufferPoolMXBean direct = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class).stream().filter(p -> p.getName().equals("direct")).findFirst().get();
  for (int v : new int[]{256, 1024, 4096, 16384}) {
    StorageService.instance.setCompressedReadAheadBufferInKB(v);
    SSTableReader rd = SSTableReader.open(cfs, d);
    try (ISSTableScanner w = rd.getScanner()) { if (w.hasNext()) w.next().close(); }   // warm thread-local holders
    for (int T : new int[]{1, 8}) {
      java.util.concurrent.CyclicBarrier open = new java.util.concurrent.CyclicBarrier(T + 1), done = new java.util.concurrent.CyclicBarrier(T + 1);
      long m0 = direct.getMemoryUsed(), c0 = direct.getCount();
      for (int t = 0; t < T; t++) new Thread(() -> {
        try (ISSTableScanner s = rd.getScanner()) { if (s.hasNext()) s.next().close(); open.await(); done.await(); } catch (Exception e) { throw new RuntimeException(e); }
      }).start();
      open.await(); long m1 = direct.getMemoryUsed(), c1 = direct.getCount();
      done.await(); Thread.sleep(500); long m2 = direct.getMemoryUsed();
      System.out.printf("v=%d T=%d openDelta=%d countDelta=%d closedDelta=%d%n", v, T, m1 - m0, c1 - c0, m2 - m0);
    }
    rd.selfRef().release();
  }
}
```
Run: `cd /local/c509 && ant testsome -Dtest.name=org.apache.cassandra.io.util.ReadAheadSetterTest 2>&1 | tee /local/ra-unit.log`. The `printf` lines are in `build/test/output/TEST-org.apache.cassandra.io.util.ReadAheadSetterTest.xml` (system-out). Run three times.

Negative control: add a second table with `chunk_length_in_kb: 1024`, set v = 512, and repeat T = 8. The `Standard` reader gate is `size > chunkLength`, which fails here.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2e (exact form of the filed skeleton).** Order inside one test run: table, inserts, flush, read-backs; the four rejections (each printing `REJECTED <v> <class> <message>` or `ACCEPTED <v>`, then the getter); `2097151` and its getter; for v ∈ {256, 1024, 4096, 16384}: set, getter, fresh reader, captured size, warm-up scan on the test thread, cycles T = 1 then T = 8; the stale-reader cycle (T = 8, live reader, knob 16384); the gate control (second table, set 512, fresh reader, T = 8). Each cycle starts with `System.gc()` and a 1 s pause (so buffers of earlier, finished threads are released before *before*), uses barrier waits of at most 60 s (a timeout fails the test), and after the filed `Thread.sleep(500)` joins its worker threads (≤ 10 s) before reading *after*. `unit-run.sh` runs the test three times (`rep1`–`rep3`), each its own `ant testsome`; the `STAGE4` lines go to `stage4.out` and `summary.txt`.

**B2f. Predictions.**
- **Rejections.** `0`, `128` and `255` print `REJECTED … IllegalArgumentException`. `2097152` prints `REJECTED … ConfigurationException`. The getter stays at its previous value (256 at test start) after each.
- **Allocations.** For v ∈ {256, 1024, 4096, 16384} KiB, `openDelta` ≈ T × v × 1024 B. That is 262 144 / 1 048 576 / 4 194 304 / 16 777 216 B per scanner, within ±T × 40 KiB for per-thread `ThreadLocalByteBufferHolder` buffers on the new threads. `countDelta` ≥ T. `closedDelta` is within T × 40 KiB of 0, because the read-ahead buffer is cleaned.
- **Gate control.** chunk 1024 KiB with v = 512: `openDelta` ≤ T × 1.1 MiB (holder buffers only), with no term proportional to v.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2f (exact forms; the filed relations and bands are kept and applied to the pool-corrected deltas of B2d).** In every repetition: (r) `0`, `128`, `255` → `REJECTED … IllegalArgumentException compressed_read_ahead_buffer_size_in_kb must be at least 256KiB`; `2097152` → `REJECTED … ConfigurationException compressed_read_ahead_buffer_size must be positive value <= 2147483646B, but was 2147483648B`; the getter reads 256 after each; `2097151` → accepted, getter 2097151. (s) For v ∈ {256, 1024, 4096, 16384}: captured size of the fresh reader = v × 1024; at T = 1 and T = 8 every worker reports a live direct buffer of exactly v × 1024 B for the data file; `openDeltaC` within ±T × 40 KiB of T × v × 1024 (the holders of (1) in the A3 amendment are ≤ T × 16,472 B); `countDelta` ≥ T; `closedDeltaC` within T × 40 KiB of 0 (the read-ahead buffers are freed at close; holders may remain). (t) Stale reader: captured size 262,144; every worker's buffer is 262,144 B, not 16,777,216; `openDeltaC` within ±8 × 40 KiB of 8 × 262,144. (u) Gate control: captured `none`; no worker has a buffer; `openDeltaC` ≤ 8 × 1.1 MiB (holders only; the 1 MiB rebufferer buffers are direct pool overflow and are removed by the correction). The raw `openDelta`/`closedDelta` are reported too.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `openDelta/T` tracks v (ratio ≈ 1 ± 0.15 for all four v), `closedDelta` ≈ 0 | Claim confirmed: per-scan direct memory = setting |
| A value < 256 accepted, or the getter changes after a rejection | Setter floor not enforced (line 2556 claim wrong) |
| `openDelta` independent of v | Setting does not size the buffer on new readers (claim wrong) |
| `closedDelta` ≈ `openDelta` | Buffer not freed at scan close; usage accumulates (claim's release half wrong) |
| Gate control shows a v-proportional delta | Gate at `CompressedChunkReader.java:237` not as traced |

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2g (verdict mapping; rows added, the filed rows keep their meaning).** **Confirmed**: (r)–(u) of B2f hold in all three repetitions. **Refuted (setter floor)** (filed row 2): a value < 256 accepted, or the getter changes after a rejection. **Refuted (sizing)** (filed row 3): a worker's buffer ≠ v × 1024, or `openDeltaC` independent of v. **Refuted (pick-up)**: the stale reader's buffers are 16,777,216 B (the size is not fixed when the reader is built: a reader opened before the change sees it) — or a fresh reader's captured size ≠ v × 1024 (a reader opened after the change does not see it). **Refuted (release)** (filed row 4): a worker's buffer still live after close, or `closedDeltaC` ≈ `openDeltaC`. **Refuted (gate)** (filed row 5): a buffer or a v-proportional `openDeltaC` in the gate control. **Not confirmed**: every per-buffer and per-reader reading as predicted but an `openDeltaC`/`closedDeltaC` outside its band, or the repetitions disagree. **Invalid**: a read-back differs (factory not `Standard`, file cache on, SSTable count ≠ 1), or the test fails or times out. The filed ratio "≈ 1 ± 0.15" is implied by the B2f band for v ≥ 1024; at v = 256 the B2f band (±15.6 %) governs.

**B2h. Controls.**
- Warm-up scan before measuring, so thread-local holders on the main thread are excluded.
- Fresh reader per v, which rules out stale size captured at construction.
- Repeat at T = 1 and T = 8 to show linearity in the number of scanners.
- Gate control at a large chunk length.
- Three repetitions for noise.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2h.** Added: the stale-reader control (B2b), which separates "the size is fixed when a reader is built" from "the size is read at scan time"; the fresh-reader cycles alone cannot. The gate control's filed bound applies to `openDeltaC` (B2f (u)).

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, JDK 11, built from `/local/c509` with `ant jar`. Copy `conf/` to `/local/node1/conf` and edit it:
- `data_file_directories: [/local/node1/data]`, `commitlog_directory: /local/node1/commitlog`, `hints_directory: /local/node1/hints`, `saved_caches_directory: /local/node1/saved_caches`, `cdc_raw_directory: /local/node1/cdc`.
- `compressed_read_ahead_buffer_size: 256KiB`.
- Leave `disk_access_mode` and `file_cache_enabled` commented, so the defaults apply (standard data access, no chunk cache).

In `/local/node1/conf/jvm-server.options` (or `jvm11-server.options`) set `-Xms2G -Xmx2G`. Keep JMX local on port 7199 (`cassandra-env.sh:228-235`).

Start: `CASSANDRA_CONF=/local/node1/conf CASSANDRA_LOG_DIR=/local/node1/logs bin/cassandra -p /local/node1/pid`.

At least 10 GB free on `/local` is needed.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3a.** This host: one node from `$W/cassandra-run23` (built by `build-test`, which includes `jar`) on 127.0.0.1; `conf/` copied to `$W/node-crs/conf` with the filed yaml edits (directories under `$W/node-crs/`, `compressed_read_ahead_buffer_size: 256KiB`, `disk_access_mode` and `file_cache_enabled` left unset) plus `num_tokens: 1`, `initial_token: 0`; heap via `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (`cassandra-env.sh` sets `-Xms2G -Xmx2G` from it); started as `bin/cassandra -f` in the background (no `setsid`, pid tracked by the script instead of `-p`). The Byteman agent with `readahead.btm` (copied unchanged from `harness/compressed_read_ahead_buffer_size-applySimpleConfig-…/`; Cassandra classes, no `boot:`) is on the node's command line through `JVM_EXTRA_OPTS`; its trace goes to the run's log folder. `Jmx.java` is the filed client, saved in the harness folder and run as `java Jmx.java 127.0.0.1:7199 …` (JDK 11 single-file launch). Logs under `$W/logs/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb/`. ≥ 20 GiB free is required (139 GiB free at step E).

**B3b. Knobs.** Set `CompressedReadAheadBufferInKB` over JMX: 256, 4096, 16384. Also try 255 and 0, which must be rejected. Use this single-file JDK client, saved outside the clone as `/local/tools/Jmx.java`:
```java
import javax.management.*; import javax.management.remote.*; import java.util.*;
public class Jmx { public static void main(String[] a) throws Exception {
  MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
  switch (a[1]) {
    case "set": try { m.setAttribute(new ObjectName("org.apache.cassandra.db:type=StorageService"), new Attribute("CompressedReadAheadBufferInKB", Integer.parseInt(a[2]))); System.out.println("OK " + a[2]); }
                catch (Exception e) { System.out.println("REJECTED " + a[2] + " " + e); }
                System.out.println("now " + m.getAttribute(new ObjectName("org.apache.cassandra.db:type=StorageService"), "CompressedReadAheadBufferInKB")); break;
    case "poll": ObjectName d = new ObjectName("java.nio:type=BufferPool,name=direct"); long end = System.currentTimeMillis() + Long.parseLong(a[2]) * 1000;
                while (System.currentTimeMillis() < end) { System.out.println(System.currentTimeMillis() + "," + m.getAttribute(d, "MemoryUsed") + "," + m.getAttribute(d, "Count")); Thread.sleep(100); } break;
  } } }
```
Run as `java /local/tools/Jmx.java 127.0.0.1:7199 set 4096`.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3b.** Values as filed (`set 255`, `set 0`, then 256, 4096, 16384 and the repeat 4096). Two controls added (B3h): **stale** — keyspace `ra_stale` written at 256, then `set 16384`, then compacted (16 SSTables opened before the change); **ctl-cache** (the filed optional control, run) — a second start with `file_cache_enabled: true`, `set 16384`, one keyspace `ra_cc`.

**B3c. Workload.** For each v, in a fresh keyspace so that every SSTable is opened after v is set:
1. Set v.
2. `nodetool disableautocompaction`.
3. Create the schema with cassandra-stress and write 16 SSTables: run `tools/bin/cassandra-stress write n=100000 no-warmup -pop seq=$((i*100000+1))..$(((i+1)*100000)) -rate threads=32 -schema "keyspace=ra_$v" -node 127.0.0.1` followed by `bin/nodetool flush ra_$v standard1`, for i = 0..15. Each SSTable holds about 20 MB, with default LZ4 at 16 KiB chunks.
4. `bin/nodetool setcompactionthroughput 16`, so that the compaction lasts about 20 s.
5. `bin/nodetool compact ra_$v standard1`. A major compaction opens 16 scanners on one compaction thread, one per file, so it holds 16 buffers of v.

Arithmetic: peak read-ahead = 16 × v. That is 4 MiB at v = 256 KiB, 64 MiB at 4096 KiB, and 256 MiB at 16384 KiB, all below the default max direct memory (= Xmx = 2 GiB).

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3c (corrections (b), (c) of the A3 amendment; sizes as filed).** Every stress run is `tools/bin/cassandra-stress write n=100000 no-warmup -pop seq=<i·100000+1>..<(i+1)·100000> -rate threads=32 -schema keyspace=ra_<label> compression=LZ4Compressor -node 127.0.0.1` (i = 0…15; LZ4, default chunk 16 KiB). `nodetool disableautocompaction ra_<label>` runs right after the first stress run (which creates the keyspace; nothing has been flushed yet), then `nodetool flush ra_<label> standard1` after every run → 16 SSTables. Then `nodetool setcompactionthroughput 16` and the B3e compaction. Peak read-ahead 16 × v as filed; `MaxDirectMemorySize` is 8192M here (correction (d)), not 2 GiB.

**B3d. Observables and instruments.**
- `java.nio:type=BufferPool,name=direct` `MemoryUsed`/`Count`, polled every 100 ms over JMX during the compaction (`Jmx poll 120`).
- `nodetool compactionstats` to bracket the start and end of the compaction.
- `system.log` for the `IllegalArgumentException` on rejected sets.

Per-file buffer attribution cannot be seen. The quantity used is the baseline-subtracted peak.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3d.** (1) The filed poller (`Jmx.java … poll 120`, 100 ms) writes `epoch_ms,MemoryUsed,Count`; the script records the epoch ms just before and after the blocking `nodetool compact` (the compaction window) and one `nodetool compactionstats` 2 s into it. (2) **Per buffer**: the Byteman trace has one `alloc` line per read-ahead allocation (`knob`, returned `cap`, `direct`, file, thread, ms) and one `free` line per release. (3) `nodetool tablestats ra_<label>.standard1` before and after the compaction (SSTable count, `SSTable Compression Ratio`). (4) Read-backs: JMX `CompressedReadAheadBufferInKB` after every set (`now …`), `DiskAccessMode is …` and `Node configuration` in `system.log`, `MaxDirectMemorySize` on the node's command line. (5) Setter evidence: the client's `OK`/`REJECTED` line and read-back; in `system.log`, one INFO `set compressed read ahead buffer size to <v>KiB` per accepted set and none for a rejected one (the filed "system.log for the IllegalArgumentException" does not exist: the exception goes to the client, A3 amendment).

**B3e. Procedure.**
1. Start the node and wait for `nodetool status` UN.
2. Run `java Jmx.java 127.0.0.1:7199 set 255`, then `set 0`. Expect REJECTED and `now 256` both times.
3. For v in 256 4096 16384:
   1. `set v`.
   2. Run the workload steps.
   3. Start `java Jmx.java 127.0.0.1:7199 poll 120 > /local/ra-$v.csv &`, wait 5 s (baseline), then run `nodetool compact ra_$v standard1`, then wait for the poller.
   4. Clean up: run `bin/cqlsh -e "DROP KEYSPACE ra_$v"` and `bin/nodetool clearsnapshot --all`.
4. Repeat the v = 4096 run once more for noise.
5. Stop: `kill $(cat /local/node1/pid)`, then check `pgrep -f CassandraDaemon` is empty.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3e.** Script `cluster-run.sh`. Pre-checks: no Cassandra process, ports 7000/7199/9042/9091 free, ≥ 20 GiB free. Start `n1` (yaml 256KiB), wait for `UN` and `statusbinary` `running` (fail at once if the process dies). `set 255`, `set 0`. Then, for each label in `v256 v4096 v16384 v4096b stale`: set v (stale: 256), the B3c writes and flushes (stale: then `set 16384`), tablestats, `setcompactionthroughput 16`, poller started, 5 s, `nodetool compact ra_<label> standard1`, wait for the poller, tablestats, `DROP KEYSPACE ra_<label>`, `nodetool clearsnapshot --all`. Stop `n1` (`nodetool drain`, then `kill`; check no process). Start `cc` (yaml 256KiB + `file_cache_enabled: true`), `set 16384`, one arm `ra_cc` the same way, stop. Wipe `$W/node-crs`. A start or a step that fails ends the run (Invalid). A shakedown (`sd`: one start, `set 2048`, 4 × 20,000 rows, compaction; Byteman `TestScript`) runs before run 1 as a harness check, not a reading.

**B3f. Predictions.** Define peak = max(MemoryUsed during compaction) − median(MemoryUsed in the 5 s baseline).
- peak(v) ≈ B + 16 × v, where B is the v-independent compaction overhead.
- The run-to-run differences are therefore:
  - peak(4096) − peak(256) ≈ 60 MiB (±15 %).
  - peak(16384) − peak(4096) ≈ 192 MiB (±15 %).
- After the compaction ends, MemoryUsed returns to within 8 MiB of the baseline.
- `set 255` and `set 0` are rejected, and the attribute remains 256.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3f (exact forms; the filed relations and bands are kept).** With baseline = median `MemoryUsed` of the samples before the compaction window, peak = max `MemoryUsed` inside the window − baseline, after = median of the samples from 5 s after the window to the end − baseline: (i) `set 255` / `set 0` → `REJECTED <v> …` whose exception chain contains `IllegalArgumentException: compressed_read_ahead_buffer_size_in_kb must be at least 256KiB` (the JMX wrapper class is not part of the prediction), and `now 256`; no INFO set line for them. (ii) Every accepted set → `OK <v>`, `now <v>`, one INFO line. (iii) Per buffer (trace, the arm's `Data.db` files): v256 / v4096 / v16384 / v4096b — exactly 16 `alloc` lines inside the window, each `cap` = v × 1024 and `direct=true`, on one `CompactionExecutor` thread, 16 matching `free` lines; stale — the same with `cap` = 262,144. (iv) Real resource: peak(v4096) − peak(v256) in [51, 69] MiB (60 MiB ± 15 %) and peak(v16384) − peak(v4096) in [163.2, 220.8] MiB (192 MiB ± 15 %), for both 4096 runs; |peak(stale) − peak(v256)| ≤ 9 MiB and peak(v16384) − peak(stale) in [214.2, 289.8] MiB (252 MiB ± 15 %); after within 8 MiB of baseline in every arm. (v) Validity: 16 SSTables and a compression ratio in (0, 1) before, 1 SSTable after, `nodetool compact` rc 0, `DiskAccessMode is standard`, file cache false (cc: true).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak differences match 16 × Δv within 15 % and drop back after the compaction | Claim confirmed at node level |
| Peak independent of v | Setting does not govern scan buffers on this path (claim wrong); check that the data really is non-mmapped (`DiskAccessMode is standard` in the log) |
| Peak grows but does not return after the compaction | Buffers leak beyond scan close (release half wrong) |
| `set 0`/`set 255` accepted | Floor at 2556 not enforced |

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3g (verdict mapping; rows added, the filed rows keep their meaning).** **Confirmed**: (i)–(v) of B3f and the B3h controls hold. **Refuted (setter floor)** (filed row 4): 255 or 0 accepted, or the attribute ≠ 256 after them. **Refuted (sizing)** (filed row 2): an arm's `alloc` lines with `cap` ≠ v × 1024, or a peak difference independent of v. **Refuted (pick-up)**: the stale arm's buffers are 16,777,216 B, or its peak sits within the v16384 band (readers opened before the change see the new value). **Refuted (release)** (filed row 3): `free` lines missing or after > 8 MiB above baseline. **Not confirmed**: (iii) holds but a (iv) difference falls outside its band, or fewer than 3 samples inside a window. **Invalid**: a read-back or validity item of (v) fails, k ≠ 16, the table uncompressed, a compaction or start fails.

**B3h. Controls.**
- A fresh keyspace per v, so SSTables are opened after the setting changes.
- The same data size and SSTable count for every v.
- A baseline window before every compaction.
- A repeat run at 4096.
- Optional negative control: restart with `file_cache_enabled: true` and v = 16384. The peak difference against 256 should vanish, because `ChunkCache.java:261-265` ignores scan mode.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3h.** ctl-cache (filed optional control, run): no `alloc` line for `ra_cc` files (`ChunkCache.java:261-265`). The filed "peak difference against 256 should vanish" is not guaranteed by the source — the chunk cache fills its own direct `BufferPool` up to `file_cache_size` (512 MiB at a 2 GiB heap) while compaction reads through it — so its JMX peak is INFO only. Stale control: (iii) and (iv) of B3f.

**B4. Risks and cleanup.**
- Unit: the test writes under `/local/c509/build/test`. Afterwards run `rm -rf /local/c509/build/test/cassandra`.
- Cluster: everything stays under `/local/node1`, about 6 GB peak. After the runs:
  - drop the keyspaces;
  - `kill $(cat /local/node1/pid)`;
  - confirm `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` print nothing;
  - `rm -rf /local/node1/{data,commitlog,hints,saved_caches,cdc,logs}`.
- Never write in the shared clone.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B4.** This host: unit — the clone's test yaml restored and the test removed (`git -C $W/cassandra-run23 status` clean), `build/test/cassandra` removed. Cluster — ≈ 0.7 GB per arm under `$W/node-crs`, dropped per arm and wiped at the end; drain and stop the node; `ps -eo command | grep '[C]assandraDaemon'` and `pgrep -f cassandra-stress` empty; ports free; the repository root has no `build/` or log folder.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/service/StorageService.java
- src/java/org/apache/cassandra/service/StorageServiceMBean.java
- src/java/org/apache/cassandra/io/util/CompressedChunkReader.java
- src/java/org/apache/cassandra/io/util/ThreadLocalReadAheadBuffer.java
- src/java/org/apache/cassandra/io/util/FileHandle.java
- src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java
- src/java/org/apache/cassandra/cache/ChunkCache.java
- src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java
- src/java/org/apache/cassandra/io/sstable/format/SSTableScanner.java
- src/java/org/apache/cassandra/io/sstable/format/SSTableSimpleScanner.java
- src/java/org/apache/cassandra/io/compress/LZ4Compressor.java
- src/java/org/apache/cassandra/io/compress/BufferType.java
- conf/cassandra.yaml, conf/cassandra-env.sh, build.xml, CHANGES.txt
- https://issues.apache.org/jira/browse/CASSANDRA-15452
- https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html

## D. Stage-4 feedback

**2026-10-25, stage 4 run 1 (Claude Opus 5.5; uncommitted; results [`../../stage4-runtime-verification/results/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous.md`](../../stage4-runtime-verification/results/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous.md)).** Frozen at sha256 `a037495a…9244` after the audit's eighteen amendments (before any reading; no runbook defect). **Unit: Confirmed** (B2g) — 0/128/255 refused with `IllegalArgumentException` and 2097152 with `ConfigurationException`, getter unchanged; fresh readers captured v and every scanner held one direct buffer of exactly v (256 KiB–16 MiB), direct memory = T × v plus a 16,287-byte holder per thread, back on close; the reader opened before `set 16384` kept 262,144-byte buffers; no buffer when v ≤ chunk length; three identical repetitions. **Cluster: Confirmed** (B3g) — JMX `set 255`/`set 0` refused, attribute stays 256 (no server log line for a rejection); after each set a 16-SSTable compaction held exactly 16 buffers of the value set (peaks 4.1 / 64.1 / 256.1 MiB at 256 KiB / 4 MiB / 16 MiB; differences 60.0 and 192.0 MiB), all freed; SSTables written before `set 16384` were compacted with 256 KiB buffers (4.1 MiB); no buffer with the chunk cache on (whose own pool took 345 MiB). **Effect: caps each buffer of readers opened after the change (size = the value set); does not cap the total** (= scanners × value). Self-check 246/246. For stage 3: the unit yaml sets `file_cache_enabled: true` (the filed unit tier would have seen no buffer); stress tables are uncompressed unless `-schema compression=…`; `nodetool disableautocompaction` without a keyspace does not cover one created later; `MaxDirectMemorySize` is a quarter of RAM under `bin/cassandra`; a claim about "readers opened afterwards" needs a reader opened before the change as its control.
