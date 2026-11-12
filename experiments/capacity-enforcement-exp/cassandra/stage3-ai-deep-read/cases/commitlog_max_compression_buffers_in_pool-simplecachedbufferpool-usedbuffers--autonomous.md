# commitlog_max_compression_buffers_in_pool — verification solution  <!-- file: cases/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the capacity assignment, as given, **linked**: [`SimpleCachedBufferPool.java:62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java#L62) (`this.maxBufferPoolSize = maxBufferPoolSize;`). The checks that enforce it are linked in A3. |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive`, conditionally. When the commit log is compressed, encrypted or in `direct` mode, the segment-allocator thread refuses to create a new segment while `usedBuffers >= commitlog_max_compression_buffers_in_pool`. Since pooled buffers are only created when the pool is empty, the number of live segment buffers (in use plus pooled) is at most N, so commit-log segment buffer memory is at most N × `commitlog_segment_size`. In the default `legacy` uncompressed configuration (mmap), the pool is `null` and the constraint does nothing. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `commitlog_max_compression_buffers_in_pool`. It is a configuration entry (a cassandra.yaml key; it is not in the shipped `conf/cassandra.yaml`, but every public `Config` field can be set in yaml). It is declared at
[`Config.java:400`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L400):
`public int commitlog_max_compression_buffers_in_pool = 3;`.
- Unit: a count of buffers. Each buffer is `commitlog_segment_size` bytes (default 32 MiB, `Config.java:397`; in `direct` mode it is `segment_size + fsBlockSize - 1`).
- Default: the literal `3`. The Javadoc at `DatabaseDescriptor.java:2813-2815` explains it: "one segment in compression, one written to, one in reserve".
- Read via `DatabaseDescriptor.getCommitLogMaxCompressionBuffersInPool()` (`DatabaseDescriptor.java:2817-2820`). The setter `setCommitLogMaxCompressionBuffersPerPool` (`:2822-2825`) is used only by tests. There is no JMX setter and no `-D` property, and no validation of the value. The value is captured once, when `AbstractCommitLogSegmentManager.start()` builds the pool (`AbstractCommitLogSegmentManager.java:155`), so a change needs a restart.
- Lower bound (not in Cassandra code): the bounded queue is a JCTools `MpmcArrayQueue` (jctools-core 3.1.0, `.build/parent-pom-template.xml`). It rejects a capacity below 2 and rounds the capacity up to a power of two. A value of 1 (or 0 or a negative value) should therefore fail commit-log start with an `IllegalArgumentException`. This is a prediction for stage 4 to check, not traced in the pinned tree.

**A2. What it caps.** Memory held by commit-log segment buffers:
- off-heap (direct `ByteBuffer`s) for LZ4/Snappy/Zstd compression (`LZ4Compressor.java:242`, `SnappyCompressor.java:112`, `ZstdCompressor.java:210` return `OFF_HEAP`) and for `direct` I/O (`DirectIOSegment.java:200-202`);
- heap for encryption (`EncryptedSegment.java:175-177`, `BufferType.ON_HEAP`) and for the Deflate compressor (`DeflateCompressor.java:231`).

The quantity compared against the limit is `SimpleCachedBufferPool.usedBuffers` (`SimpleCachedBufferPool.java:43`). It is the number of segment buffers currently handed out: incremented in `createBuffer()` (`:70`) and decremented in `releaseBuffer()` (`:90`).

**A3. Mechanism.**
1. At commit-log start, `AbstractCommitLogSegmentManager.start()` calls `segmentBuilder.createBufferPool()` (`AbstractCommitLogSegmentManager.java:155`). For compressed, encrypted and direct segments this calls `new SimpleCachedBufferPool(getCommitLogMaxCompressionBuffersInPool(), getCommitLogSegmentSize()[+fsBlockSize-1], type)` (`CompressedSegment.java:113-118`, `EncryptedSegment.java:173-178`, `DirectIOSegment.java:190-202`). For mmap segments it returns `null` (`MemoryMappedSegment.java:130-133`). The builder is chosen at `AbstractCommitLogSegmentManager.java:121-143`.
2. The constructor sizes a bounded queue with N (`SimpleCachedBufferPool.java:61`) and stores the cap (`:62`, the entry pointer).
3. **The check:** [`SimpleCachedBufferPool.java:117-120`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java#L117-L120) `atLimit()` returns `usedBuffers.get() >= maxBufferPoolSize`. It is wrapped by [`AbstractCommitLogSegmentManager.java:241-244`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L241-L244) `atSegmentBufferLimit()`, which is used in two places:
   - the allocator thread's wait condition, [`AbstractCommitLogSegmentManager.java:108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L108) `availableSegment == null && !atSegmentBufferLimit()`, waited on at `:225` (`WaitQueue.waitOnCondition` loops while the condition is false, `WaitQueue.java:477-485`);
   - the if statement [`AbstractCommitLogSegmentManager.java:194`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L194) `if (availableSegment == null && !atSegmentBufferLimit()) return;` (loop and create again immediately). Otherwise the thread goes on to `maybeFlushToReclaim()` and the wait.
4. The only caller of `createBuffer()` is the `CommitLogSegment` constructor (`CommitLogSegment.java:168`, `:192-195`). Segments are built only by the allocator thread (`AbstractCommitLogSegmentManager.java:189`, `:275-278`). So a new buffer is taken only after the check passes, which gives `usedBuffers <= N`.
5. **Outcome at the limit.** The allocator thread blocks. Writers that fill the current segment call `advanceAllocatingFrom` and block in `awaitAvailableSegment` (`AbstractCommitLogSegmentManager.java:296-318`, `:337-348`), timed by the `CommitLog.WaitingOnSegmentAllocation` metric. Writes stall (back-pressure); nothing is dropped or failed.
6. **Release.** When the sync thread has fully written a finished segment, `sync()` calls `internalClose()` (`CommitLogSegment.java:367-368`). `FileDirectSegment.internalClose` and `DirectIOSegment.internalClose` call `releaseBuffer` and then `notifyBufferFreed()` → `wakeManager()` (`FileDirectSegment.java:58-68`, `DirectIOSegment.java:147-158`, `AbstractCommitLogSegmentManager.java:645-657`). `releaseBuffer` offers the buffer to the bounded queue and frees it with `FileUtils.clean` if the queue is full (`SimpleCachedBufferPool.java:94-95`). So the buffer is freed when the segment is synced and closed, not when the segment file is discarded.
7. **Total live buffers.** `createBuffer` polls the pool first and allocates only when the pool is empty (`:71-77`). At every new allocation, pooled = 0, so live = used ≤ N. A release only moves a buffer from used to pooled. So used + pooled ≤ N at all times.
8. **Overshoot and bypass paths.**
   - (a) `SimpleCachedBufferPool` itself does not refuse to allocate past N (the class comment at `:28-30` says "Will allow you to go past the max"). Enforcement depends entirely on the caller's check. Any other caller of `createBuffer()` would bypass it, but there is none in the tree.
   - (b) The queue capacity is rounded up to a power of two by JCTools. If more than N buffers ever existed, up to roundUpPow2(N) of them could be retained, despite the comment at `:60`. This is unreachable through the manager.
   - (c) `mmap` mode (the default for an uncompressed commit log) has no pool (`MemoryMappedSegment.java:130-133`, `atSegmentBufferLimit` is `false` for a null pool), so the constraint does not apply.
   - (d) The per-thread compression/encryption output buffer, `getThreadLocalReusableBuffer` (`SimpleCachedBufferPool.java:80-83`, `ThreadLocalByteBufferHolder.getBuffer`), is allocated outside the count. It is used by the sync thread in `CompressedSegment.write` (`CompressedSegment.java:68`) and sized at about `compressBound(section length)`, which is up to about one segment.

**A4. Other consumers.**
- Off-heap: the chunk cache and the networking `BufferPool` (`file_cache_size`, `networking_cache_size`), Netty buffers, and the thread-local compression buffer from A3(8d).
- Heap: memtables (which hold the same writes), and the same thread-local buffer when the type is `ON_HEAP`.
- Disk: commit-log files are not bounded by this constraint. Closed segments that are waiting for memtable flush keep their files after their buffer has been released. Commit-log disk is governed by `commitlog_total_space` (`maybeFlushToReclaim`, `AbstractCommitLogSegmentManager.java:246-264`).
- mmap segments use page cache, not this pool.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentBackpressureTest.java`: with N = 3, LZ4, 1 MiB segments and sync blocked by Byteman, it asserts that exactly 3 active segments exist ("Should only be able to create 3 segments not 7").
- `DatabaseDescriptor.java:2813-2815` Javadoc.
- JCTools `MpmcArrayQueue` / `ConcurrentCircularArrayQueue` capacity rules (minimum 2, power-of-two rounding): https://github.com/JCTools/JCTools/blob/v3.1.0/jctools-core/src/main/java/org/jctools/queues/MpmcArrayQueue.java (cited from memory of the public source; stage 4 should confirm with the N=1 control).
- JDK `BufferPoolMXBean`: https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html

## B. Verification solution

**B1. Claim under test.** With a compressed commit log (LZ4/Zstd, off-heap buffers), the number of live commit-log segment buffers never exceeds N = `commitlog_max_compression_buffers_in_pool`. When the sync thread lags, usage plateaus at N × `commitlog_segment_size`, and writers block instead of allocating more. So segment-buffer direct memory follows N: it grows by about S per unit of N and never goes above N × S. The claim is wrong if live buffers or direct memory exceed N × S (beyond the thread-local buffer and A4 noise), or if the plateau does not move with N.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11 and Ant.
- Copy the tree to local disk: `rsync -a ~/cassandra-5.0.9/ /mydata/o45/unit/cassandra/`, then `cd /mydata/o45/unit/cassandra`.
- Add the two test sources from B2c, then run `ant jar build-test` (about 10–20 min).
- Tests run under `ant testsome` with the default `test/conf` and the build's test JVM options. Byteman comes from the test classpath (BMUnitRunner).
- *Stage-4 audit amendment (2026-11-11, runbook only):* the run node is `apt138` (16 cores, ~14 GiB free; shared with another project). The tree is made with the repository's `copy-source.sh` (not `~/cassandra-5.0.9`) and lives at `/mydata/jingsong-cass-s4/o45/src`; it is built once with `ant build-test` (which includes the main build). Every `/mydata/o45/...` path in this file reads `/mydata/jingsong-cass-s4/o45/...`.

**B2b. Knobs.**
- N ∈ {2, 3, 6}. 2 is the JCTools minimum; 3 is the default; 6 shows proportionality.
- Each value is set in code with `DatabaseDescriptor.setCommitLogMaxCompressionBuffersPerPool(N)` before `SchemaLoader.prepareServer()`, as the existing backpressure test does.
- Pool-only test: N ∈ {1, 2, 3, 6, 12}. N=1 is expected to throw.

**B2c. Workload.**

*Test 1, pool alone:* `test/unit/org/apache/cassandra/io/util/SimpleCachedBufferPoolCapTest.java` with a `@BeforeClass DatabaseDescriptor.daemonInitialization()`. For each N it runs these steps on a fresh pool:
1. `pool = new SimpleCachedBufferPool(N, 1<<20, BufferType.OFF_HEAP)`; read `direct0`.
2. For k = 1..2N: `bufs.add(pool.createBuffer())`, then record `k`, `pool.atLimit()`, `pool.toString()` and direct `MemoryUsed − direct0`.
3. Release all 2N and record `MemoryUsed − direct0`.
4. Create N again and record `MemoryUsed − direct0`.
5. Release all again, then `emptyBufferPool()`.

Wrap each N in try/catch and log any exception (expected for N=1).

The arithmetic: 2N × 1 MiB = 2N MiB of direct memory at the peak, which drives `usedBuffers` to 2× the cap. This shows that the class alone does not refuse, so enforcement must come from the caller.

*Test 2, manager path:* generate three classes from the existing test:
```
for N in 2 3 6; do sed -e "s/CommitLogSegmentBackpressureTest/CommitLogBufferCap${N}Test/g" \
  -e "s/setCommitLogMaxCompressionBuffersPerPool(3)/setCommitLogMaxCompressionBuffersPerPool(${N})/" \
  -e "s/i < 20/i < 60/" -e "s/spinAssertEquals(3,/spinAssertEquals(${N},/g" -e "s/assertEquals(3,/assertEquals(${N},/" \
  test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentBackpressureTest.java \
  > test/unit/org/apache/cassandra/db/commitlog/CommitLogBufferCap${N}Test.java; done
```
In each class, after each `spinAssertEquals`, also add a `System.out.println` of:
- `clsm.getBufferPool()` (its `toString` shows `usedBuffers`; the method is package-private, and the test is in the same package);
- `clsm.getActiveSegments().size()`;
- direct `MemoryUsed`, read via `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` where `name == "direct"`. Record this before the writer starts too.

The workload is 60 mutations × 256 KiB = 15 MiB into 1 MiB LZ4 segments with sync blocked. That needs about 15+ segments, far more than N ≤ 6, so the limit is reached.

*Stage-4 audit amendment (2026-11-11, instrument detail only):* each Test-2 class prints one line `CAP <class> <label> N=<N> active=<n> pool=<toString> directUsed=<bytes> directCount=<n>` at these points: `pre-writer` (after `allowSync.acquire()`, before `dummyThread.start()`), `plateau1` (after the first `spinAssertEquals`), `after-sleep` (after the 1 s sleep), `plateau2` (after the second `spinAssertEquals`) and `final` (in the `finally` block, before `allowSync.release()`, so a failed assertion still leaves a reading). "direct MemoryUsed − pre-writer" in B2f is `directUsed(label) − directUsed(pre-writer)`. The B2h control is a fourth class, `CommitLogBufferCapCtlTest`: the N=3 class with `DatabaseDescriptor.setCommitLogCompression(null)` (with `commitlog_disk_access_mode: legacy` from `test/conf`, `initializeCommitLogDiskAccessMode()` then resolves to `mmap`, `DatabaseDescriptor.java:1525-1527`), the same Byteman sync block, 60 mutations, and the three `spinAssertEquals`/`assertEquals` replaced by a 5 s wait followed by a print (`ctl-5s`, then `ctl-6s` after the 1 s sleep); it asserts nothing. The control "moved" when `active > 3` at `ctl-5s`.

**B2d. Observables and instruments.**
- `usedBuffers` from `pool.toString()`;
- `atLimit()`;
- `getActiveSegments().size()`;
- direct `BufferPoolMXBean.getMemoryUsed()` and `getCount()`, sampled at each step listed in B2c;
- test stdout in `build/test/output/TEST-*.xml` / `build/test/logs`.

Pooled-buffer count is not exposed directly. Infer it from MemoryUsed staying flat when buffers are re-taken.

**B2e. Procedure.**
1. Add the sources, then `ant jar build-test`.
2. `ant testsome -Dtest.name=org.apache.cassandra.io.util.SimpleCachedBufferPoolCapTest`
3. For N in 2 3 6: `ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CommitLogBufferCap${N}Test`
4. Collect stdout from `build/test/output/`.
5. Check that no java process remains: `pgrep -f CommitLogBufferCap`.

*Stage-4 audit amendment (2026-11-11, runbook only):* step 1 is `ant build-test` (done once when the tree is made). Steps 2-3 add `-Dtest.jvm.args=-Dorg.jboss.byteman.contrib.bmunit.agent.port=9391` (the node is shared; BMUnit's default agent port 9091 must stay free), and step 3 also runs `CommitLogBufferCapCtlTest` (the B2h control). Step 4: test stdout is read from `build/test/logs/_jdk11/TEST-<class>.log` (and the junit XML under `build/test/output/`). Step 5: `ps -eo pid,args | grep '[C]ommitLogBufferCap\|[S]impleCachedBufferPoolCapTest'` must print nothing.

*Stage-4 audit amendment (2026-11-11; how B2g is read, fixed before any reading; the B2f/B2g text is unchanged):* B2g row 1 holds when, for each N in {2, 3, 6}, `active` = `usedBuffers` = N at `plateau1`, `after-sleep` and `plateau2`, `directUsed(plateau1) − directUsed(pre-writer)` is within (N−2) MiB ± 0.2 MiB, and `directUsed(plateau2) − directUsed(plateau1)` is within ± 0.2 MiB. Row 2: `active` or `usedBuffers` > N at any label of a compressed class, or `directUsed − directUsed(pre-writer)` > (N−2) MiB + 0.2 MiB at any label. Row 3: the three plateaus (`active` at `plateau1`) are equal. Row 4: `active` < N at `plateau1` (the spin assertion fails). A run whose B2h control does not move (`active` ≤ 3 at `ctl-5s`) is not confirmed whatever the other rows say. The Test-1 rows (5-7) test A1 and A3(8a-b) only; they do not decide the claim.

**B2f. Predictions.**
- Test 1:
  - N=1 throws `IllegalArgumentException` at construction.
  - For N ≥ 2: `atLimit()` is false for k < N and true for k ≥ N. `usedBuffers = k` up to 2N, because the class does not refuse.
  - Direct delta is k MiB (±0.1 MiB).
  - After releasing 2N, the delta is roundUpPow2(N) MiB: N=2 → 2, 3 → 4, 6 → 8, 12 → 16. This is more than N for N = 3, 6, 12 because of JCTools rounding.
  - Re-taking N buffers does not change the delta.
- Test 2, for each N:
  - the active segment count plateaus at exactly N;
  - `usedBuffers = N`;
  - direct `MemoryUsed` − pre-writer ≈ (N − 2) MiB (two buffers already exist from start-up: the first segment plus the reserve), and the total segment-buffer memory is N MiB ± 0.2 MiB;
  - after `archiveAndDiscard` of all active segments the count returns to N, with no new direct allocation (MemoryUsed flat ± 0.2 MiB);
  - the plateau stays at N after a 1 s sleep.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Active segments = `usedBuffers` = N and stays there; direct memory ≈ N × 1 MiB | Claim holds at unit level: the manager's check caps live buffers at N |
| Active segments or `usedBuffers` > N, or direct grows past N MiB with sync blocked | Claim wrong: the check is bypassed or racy |
| Plateau identical for N = 2, 3, 6 | Claim wrong: the knob does not govern (or the cap comes from elsewhere) |
| Plateau < N (e.g., stuck at 2) | Limit not reached (workload or sync block failed); not confirmed, so check the Byteman rule fired |
| Test 1: `atLimit` flips at k=N but allocation continues to 2N | Expected: the class is advisory and the caller enforces it (supports A3 step 8a) |
| Test 1: retained after release = N, not roundUpPow2(N) | A3 step 8b wrong (JCTools does not round); harmless to the claim |
| N=1 starts without error | A1 lower-bound prediction wrong |

**B2h. Controls.**
- Test 1 shows that memory follows allocations one for one, so the instrument can see each buffer.
- Comparing N = 2, 3, 6 on the identical workload isolates the knob.
- The second fill after discard shows buffer reuse, not new allocation.
- Control run: N=3 with `setCommitLogCompression(null)` and `commitlog_disk_access_mode` `mmap`. The pool is null and no direct growth comes from segment buffers, so the cap does not apply. Active segments are not bounded at 3 (expect more than 3 once 15 MiB is written, because mmap segments do not wait on the cap). This shows that the limit, not something else, stops allocation in the compressed runs.

### B3. Cluster tier

**B3a. Environment and build.**
- One node on the stage-4 machine (16 cores, ~14 GiB free).
- Copy the tree: `rsync -a ~/cassandra-5.0.9/ /mydata/o45/node/cassandra/`, then `cd` there and run `ant jar`. Run `ant stress-build` too if `tools/bin/cassandra-stress` does not run.
- Use local disk `/mydata/o45/data` (≥ 40 GiB free). Check with `df -h /mydata`.
- Edit `conf/jvm-server.options` / `conf/jvm11-server.options`: `-Xms4G -Xmx4G` and `-XX:MaxDirectMemorySize=4G`.
- `conf/cassandra.yaml`:
```
data_file_directories: [/mydata/o45/data/data]
commitlog_directory: /mydata/o45/data/commitlog
hints_directory: /mydata/o45/data/hints
saved_caches_directory: /mydata/o45/data/saved_caches
cdc_raw_directory: /mydata/o45/data/cdc_raw
commitlog_segment_size: 64MiB
commitlog_compression:
  - class_name: ZstdCompressor
    parameters:
      compression_level: 19
commitlog_disk_access_mode: legacy
commitlog_sync: periodic
commitlog_sync_period: 10000ms
commitlog_total_space: 8192MiB
file_cache_size: 64MiB
networking_cache_size: 64MiB
commitlog_max_compression_buffers_in_pool: <N>
```
- Zstd level 19 runs on the single `COMMIT-LOG-WRITER` sync thread at only a few MB/s. Each 64 MiB segment takes many seconds to compress, so writers at tens of MB/s outrun sync and the cap binds.
- Use JMX on localhost:7199 with the default no-auth local setting.
- *Stage-4 audit amendment (2026-11-11, runbook only; predictions and conclusions unchanged):*
  - Node `apt138`, shared with another project. The node runs from `/mydata/jingsong-cass-s4/o45/node`, a copy of the built unit tree (so `ant` never runs in the tree the node runs from); data under `/mydata/jingsong-cass-s4/o45/data`, logs under `/mydata/jingsong-cass-s4/o45/node/logs`.
  - Heap and direct memory are set through `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M MAX_DIRECT_MEMORY_SIZE=4G` in the environment of `bin/cassandra`, not by editing `jvm*-server.options`: 5.0.9's `conf/cassandra-env.sh` adds `-Xmx`/`-Xmn` and `-XX:MaxDirectMemorySize` itself (`cassandra-env.sh:132-140`).
  - Ports (the node is shared): `storage_port: 7300`, `ssl_storage_port: 7301`, `native_transport_port: 9342`, JMX `7499` (`JMX_PORT` in `conf/cassandra-env.sh`); "localhost:7199" above reads `localhost:7499`.
  - Added to the yaml: `periodic_commitlog_sync_lag_block: 600000ms`. Reason (from the source, not a reading): in periodic mode every writer blocks once the last sync started more than 1.5 × `commitlog_sync_period` = 15 s ago (`PeriodicCommitLogService.java:36-45`, `DatabaseDescriptor.java:3423-3428`). With Zstd-19 one sync pass over a 64 MiB section takes longer than that, so this second back-pressure could stop writers before (N−1) × S of backlog exists (N=12 needs about 704 MiB, about 23 s at 30 MB/s), and the cap would not be the limiter B1 describes.
  - *Runbook defect D1 (2026-11-11, found by the stage-4 cluster shakedown before run 1; fix leaves B3f/B3g unchanged):* the `commitlog_compression` block above does not load: `ParameterizedClass(Map)` reads `parameters` as a **list** of maps (`ParameterizedClass.java:62-66`), so the node refuses the yaml (`ClassCastException: ConcurrentHashMap cannot be cast to List`). Write it as `parameters:` / `  - compression_level: "19"` (a list item; quoted, because the compressor reads the value as a `String`).
  - Added to the yaml: `write_request_timeout: 600000ms`, `native_transport_timeout: 600000ms`. A write blocked on the cap waits until the sync thread finishes a whole 64 MiB segment (many seconds by the estimate above), longer than the 2 s / 12 s defaults.

**B3b. Knobs.**
- N ∈ {3, 6, 12}, set in cassandra.yaml with a restart per value. With S = 64 MiB, the caps on segment buffers are 192, 384 and 768 MiB.
- Optional N=1 start to confirm the startup failure.
- Control C1: N=12 with `LZ4Compressor` instead of Zstd. Sync is fast, so the cap should not bind and usage should stay well under 12 × S.
- Control C2: N=3 with `commitlog_compression` removed (mmap). There is no pool and no segment-buffer direct memory.

**B3c. Workload.**
- After schema creation by stress: `tools/bin/cassandra-stress write duration=240s no-warmup cl=ONE -col n=FIXED(8) size=FIXED(1024) -rate threads=64 -node 127.0.0.1 -mode native cql3 -log file=/mydata/o45/stress-N.log`.
- That is about 8.4 KiB per row. Unthrottled, 64 threads can offer more than 30 MB/s of mutations.
- Sync at Zstd-19 handles roughly 2–6 MB/s, so after (N−1) × 64 MiB of backlog (at most about 11 × 64 MiB = 704 MiB), writers block. The plateau is reached within 30–60 s for N=12 and sooner for smaller N.
- Total data written is throttled by the sync rate to at most about 2 GiB over 240 s, so it fits in the 4 GiB heap with memtable flushes and on disk.
- *Stage-4 audit amendment (2026-11-11, runbook only):* the command adds `-port native=9342 jmx=7499` and `-errors ignore` (the client driver's own 12 s request timeout would otherwise end stress after 9 retries while writes wait on the cap; the server-side state under test is unchanged), and logs to `/mydata/jingsong-cass-s4/o45/run1/<cfg>/stress.log`.

**B3d. Observables and instruments.**
- Every 2 s, `nodetool sjk mx -b "java.nio:type=BufferPool,name=direct" -mg -f MemoryUsed` (and `-f Count`), logged with a timestamp.
- Every 10 s, `nodetool sjk mx -b "org.apache.cassandra.metrics:type=CommitLog,name=WaitingOnSegmentAllocation" -mg -f Count`, which shows writers blocked on the cap.
- Every 10 s, `jstack <pid> | grep -A8 '"COMMIT-LOG-ALLOCATOR'`, which should show it parked under `WaitQueue.waitOnCondition` (`AbstractCommitLogSegmentManager.java:225`) when at the cap.
- `ls /mydata/o45/data/commitlog | wc -l`, for context only (it includes closed segments).
- `ps -o rss= -p <pid>` every 10 s.

*Stage-4 audit amendment (2026-11-11, instrument only):* the 2 s and 10 s `nodetool sjk mx` calls are replaced by one JMX poller (`O45Jmx.java` in the harness, JDK classes only) that reads the same beans once per second over port 7499: `java.nio:type=BufferPool,name=direct` `MemoryUsed` and `Count`, `name=mapped` `MemoryUsed`, `CommitLog` `WaitingOnSegmentAllocation` `Count`, and, for context only, `CommitLog` `WaitingOnCommit` `Count`, `BufferPool` `Size` (`networking`, `chunk-cache`) and heap used. Reason: each `nodetool` call starts a JVM (1-2 s), so two attributes cannot keep a 2 s cadence. `jstack` (every 10 s) is kept, and the whole dump is saved, because the allocator also parks in `waitOnCondition` when a reserve segment is ready: the disallow state is the allocator in `waitOnCondition` **and** at least one writer thread in `awaitAvailableSegment` in the same dump.

`usedBuffers` itself is not exposed over JMX. It is inferred as (direct − baseline) / 64 MiB. Also not exposed: the thread-local Zstd output buffer (one buffer, up to about `compressBound(64 MiB)` ≈ 64 MiB, direct) and the Netty/chunk-cache share. Those are covered by the baseline and by differencing across N.

**B3e. Procedure.** For each configuration (N=3, 6, 12, C1, C2), in order:
1. `rm -rf /mydata/o45/data/*` and set the yaml.
2. `bin/cassandra -p /mydata/o45/cass.pid` and wait for `nodetool status` to show UN.
3. Sample direct `MemoryUsed` for 30 s idle to get the baseline B0. B0 already includes two segment buffers: the first segment plus the reserve.
4. Start the sampler loop in the background, writing to `/mydata/o45/samples-<cfg>.log`.
5. Run the stress command from B3c.
6. Keep sampling 30 s after stress ends.
7. Take the `jstack` snapshots during the plateau.
8. `nodetool drain; kill $(cat /mydata/o45/cass.pid)`, wait for exit, and confirm with `pgrep -f CassandraDaemon` (empty).
9. Kill the sampler loop.

*Stage-4 audit amendment (2026-11-11; analysis windows and thresholds fixed before any reading; the B3f/B3g text is unchanged):*
- Order: N=3, 6, 12, C1, C2, then the optional N=1 start. `nodetool` uses `-p 7499`; the process check is `ps -eo pid,args | grep '[C]assandraDaemon'` filtered to this run's tree.
- Windows: stress window = from the stress process's start to its exit (epoch ms, logged by the run script). B0 = the median of direct `MemoryUsed` over the samples of the 30 s idle window that ends at stress start. P = the maximum direct `MemoryUsed` over the samples inside the stress window. S = 64 MiB.
- "Writers blocked" (per run) = `WaitingOnSegmentAllocation` `Count` at stress end minus at stress start ≥ 1, **and** at least one `jstack` dump inside the stress window shows `COMMIT-LOG-ALLOCATOR` in `WaitQueue.waitOnCondition` together with ≥ 1 thread in `awaitAvailableSegment`.
- B3g row 1 (confirmed) holds when, for each N in {3, 6, 12}, (N−3)·S ≤ P(N) − B0(N) ≤ (N−1)·S + 64 MiB; |P(6) − P(3) − 192 MiB| ≤ 64 MiB and |P(12) − P(6) − 384 MiB| ≤ 64 MiB; and writers are blocked in all three Zstd runs.
- Row 2: P(N) − B0(N) > (N−1)·S + 64 MiB for any Zstd N. Row 3: max − min of P over N = 3, 6, 12 ≤ 64 MiB with writers blocked in all three. Row 4: no Zstd run has writers blocked and P(N) − B0(N) < (N−3)·S for every N (one rerun at `compression_level: 22` is then allowed, per the row). Row 5: C1 P − B0 ≥ 9·S (576 MiB). Row 6: C2 P − B0 ≥ 64 MiB.
- C1 between 3·S and 9·S, or a C1 run with writers blocked, is a missed C1 prediction (no row): recorded, and the cluster verdict then cannot be better than Partial. A reading set that matches no row is "Not confirmed (no matching row)".

**B3f. Predictions.** S = 64 MiB. P(N) is the maximum direct `MemoryUsed` during the stress.
- **Ceiling:** P(N) − B0 ≤ (N − 2) × S + S (thread-local Zstd buffer) + 64 MiB (noise).
  - N=3: ≤ 192 MiB
  - N=6: ≤ 384 MiB
  - N=12: ≤ 768 MiB
- **Plateau:** for each N with Zstd-19, P(N) − B0 ≥ (N − 2) × S − S. That is, the cap is reached, since sync lags.
- **Slope:** P(6) − P(3) ≈ 192 MiB ± 64 MiB, and P(12) − P(6) ≈ 384 MiB ± 64 MiB.
- `WaitingOnSegmentAllocation` Count rises during stress for every Zstd run, and the allocator thread is seen parked in `waitOnCondition`.
- C1 (LZ4, N=12): P − B0 ≤ about 2 × S + S, far below the 640 MiB that a binding N=12 cap would allow, and `WaitingOnSegmentAllocation` stays near flat.
- C2 (mmap): no growth of direct memory tied to segments (P − B0 < 64 MiB). Commit-log memory shows instead as mapped file pages in RSS.
- N=1: start-up fails with `IllegalArgumentException` from JCTools (the commit-log start error is logged).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| P(N) − B0 tracks (N−2)·S (+≤1 S), slope ≈ 64 MiB per unit N, writers blocked at the plateau | Claim confirmed: the constraint caps commit-log segment-buffer memory |
| P(N) − B0 > (N−1)·S + 64 MiB for some N, or direct grows unboundedly during stress | Claim wrong: buffers escape the cap |
| P(3) ≈ P(6) ≈ P(12) with the Zstd workload and writers blocked | Claim wrong: something other than N bounds the buffers |
| No writer blocking and P well below the cap for all N | Limit not reached (sync keeps up). Not confirmed: raise `compression_level` to 22 or `-rate threads=128` and rerun |
| C1 (LZ4) plateaus near 12·S | Either sync is slow even with LZ4 (check the disk) or allocation ignores the sync rate; re-examine |
| C2 shows N-dependent direct growth | A3 step 8c wrong |

**B3h. Controls.**
- The same workload with three N values isolates the knob, and the slope prediction is specific (S per unit N).
- C1 (fast sync) shows that the plateau comes from the cap binding under lag, not from a fixed allocation pattern.
- C2 (mmap) shows that the constraint applies only to pooled modes.
- The baseline B0 per run, and fixed `file_cache_size` and `networking_cache_size`, keep other off-heap consumers constant.
- `WaitingOnSegmentAllocation` and `jstack` give independent evidence that the allocator is stopped by `atSegmentBufferLimit` and not by an error.

**B4. Risks and cleanup.**
- Unit tier: everything stays in `/mydata/o45/unit` (build about 1–2 GiB). Test commit logs go under `build/test`.
- Cluster tier:
  - data and commit log go in `/mydata/o45/data`, at most about 8 GiB of commit log (`commitlog_total_space`) plus a few GiB of sstables;
  - check `df` before each run and `rm -rf /mydata/o45/data/*` between runs;
  - the node's memory is about 4 GiB heap + ≤ 1.5 GiB direct + metaspace and threads, under 7 GiB.
- After each run: `nodetool drain`, kill the pid, `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` both empty, and kill the sampler loops.
- At the end: `rm -rf /mydata/o45`.
- Never write into `~/cassandra-5.0.9`.

## C. Sources read

```
src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java
src/java/org/apache/cassandra/io/util/ThreadLocalByteBufferHolder.java
src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java
src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java
src/java/org/apache/cassandra/db/commitlog/CompressedSegment.java
src/java/org/apache/cassandra/db/commitlog/EncryptedSegment.java
src/java/org/apache/cassandra/db/commitlog/DirectIOSegment.java
src/java/org/apache/cassandra/db/commitlog/FileDirectSegment.java
src/java/org/apache/cassandra/db/commitlog/MemoryMappedSegment.java
src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java (grep)
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/utils/concurrent/WaitQueue.java
src/java/org/apache/cassandra/io/compress/{LZ4,Snappy,Zstd,Deflate,Noop}Compressor.java (preferredBufferType)
src/java/org/apache/cassandra/tools/nodetool/Sjk.java (existence)
test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentBackpressureTest.java
conf/cassandra.yaml, conf/jvm-server.options, conf/jvm11-server.options
build.xml, .build/cassandra-deps-template.xml, .build/parent-pom-template.xml
https://github.com/JCTools/JCTools/blob/v3.1.0/jctools-core/src/main/java/org/jctools/queues/MpmcArrayQueue.java (from knowledge of the public source)
https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
```

## D. Stage-4 feedback

**2026-11-12, run 1 (unit and cluster, node apt138):** results file [`../../stage4-runtime-verification/results/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous.md`](../../stage4-runtime-verification/results/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous.md).

- **Verdict:** unit **Not confirmed**, cluster **Not confirmed**; effect `undetermined`; Outcome class undetermined (estimate `positive`).
- **Why not confirmed.** Each tier's frozen reading rule (audit amendments M7, M8) matched the "claim wrong" row on direct memory. The self-check rejected that match.
  - Segment-buffer counts followed N exactly: `active` = `usedBuffers` = N for N = 2, 3, 6.
  - The cluster plateaus were 2.15 / 5.15 / 11.15 S for N = 3 / 6 / 12, a slope of exactly 3 S and 6 S, with writers parked on the cap in every Zstd run.
  - The excess over the prediction was not a segment buffer. Unit: a constant +524,388 B (writer serialization scratch buffer), identical in the no-pool control, and +792,121 B after discard (the closing thread's LZ4 buffer). Cluster N=12: a +64.2 MiB step when `MemtablePostFlush` synced a discarded, clean but unsynced segment itself (`discard → close() → sync() → CompressedSegment.write`), which gives that thread its own thread-local Zstd buffer outside `usedBuffers`.
- **The trace held.**
  - A1: N=1 fails at start-up with JCTools `IllegalArgumentException: capacity: 1 (expected: >= 2)`.
  - A3: the step-3 check and the step-5 back-pressure were seen (allocator waiting, writers in `awaitAvailableSegment`).
  - A3 (8a): the class alone allows 2N.
  - A3 (8b): a released pool retains roundUpPow2(N) buffers.
  - A3 (8c): mmap has no pool.
  - A3 (8d) is broader than written: there is one thread-local buffer **per thread that syncs a segment**, and memtable-flush threads sync through `CommitLogSegment.close()`.
- **For stage 3.**
  - B1/B3f should allow one compression buffer per compressing thread.
  - B2f should allow the writer scratch buffer and the closing thread's buffer.
  - C1 is not a fast-sync control: buffers are released only by the periodic sync, and C1 bound at 11.16 S.
  - Read `usedBuffers` directly (Byteman) in a redesign.
- **Amendments made by stage 4.** M1-M8 (2026-11-11, runbook, instrument and reading rules only) and runbook defect D1 (2026-11-11, the yaml `parameters` list form). All are dated next to the text they change; B2f, B2g, B3f and B3g are unchanged.
