# commitlog_max_compression_buffers_in_pool — verification solution  <!-- file: cases/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SimpleCachedBufferPool.java:61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java#L61) — `this.bufferPool = new MpmcArrayQueue<>(maxBufferPoolSize);` (a capacity getting its value, not an if statement; the enforcing checks are linked in A3) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive` — when the commit log uses a buffer pool (compression, encryption or `direct` access mode), the segment-manager thread refuses to build a new segment while `usedBuffers >= commitlog_max_compression_buffers_in_pool`, so the live segment buffers (each `commitlog_segment_size` bytes, off-heap for LZ4/Snappy/Zstd/direct, on-heap for Deflate/encryption) are capped at N × segment size; writers block instead. Not applicable under the default `legacy`→`mmap` uncompressed mode (no pool), and one per-thread compression buffer sits outside the cap. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `commitlog_max_compression_buffers_in_pool`; configuration entry (cassandra.yaml), plain `int`, unit = number of buffers (each buffer is one commit-log segment). Declared at [`Config.java:400`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L400) with default `3` (literal; no derivation). Not listed in `conf/cassandra.yaml` (grep finds nothing), but the yaml loader accepts any public `Config` field (it appears in `test/data/config/version=5.0-alpha1.yml:208` as a known key). Read via `DatabaseDescriptor.getCommitLogMaxCompressionBuffersInPool()` (`DatabaseDescriptor.java:2817-2820`, javadoc 2812-2816: "should not be set lower than [3] (one segment in compression, one written to, one in reserve)"). The only setter, `setCommitLogMaxCompressionBuffersPerPool` (`DatabaseDescriptor.java:2822-2825`), is used by tests; there is no JMX or nodetool path. No validation of the value in `DatabaseDescriptor`. The pool is built once when the segment manager starts (`AbstractCommitLogSegmentManager.java:155`), so a change needs a restart.

Related values: buffer size = `commitlog_segment_size` (`Config.java:397`, default 32MiB, must be < 2048 MiB, `DatabaseDescriptor.java:891-896`); for direct I/O the buffer is `segment size + fsBlockSize − 1` (`DirectIOSegment.java:200-202`).

**A2. What it caps.** Memory held by commit-log segment buffers. Each live `CommitLogSegment` owns one buffer from the pool (`CommitLogSegment.java:168`, `192-195`). Buffer type depends on the mode:
- compression: `compressor.preferredBufferType()` (`CompressedSegment.java:113-118`) — off-heap (`ByteBuffer.allocateDirect`, `BufferType.java:33-36`) for LZ4 (`LZ4Compressor.java:240-243`), Snappy, Zstd; on-heap for Deflate (`DeflateCompressor.java:229-231`);
- encryption: on-heap (`EncryptedSegment.java:173-178`);
- `direct` access mode: off-heap (`DirectIOSegment.java:190-233`);
- `mmap` (the default for uncompressed, unencrypted logs under `legacy`): `createBufferPool()` returns `null` (`MemoryMappedSegment.java:130-133`), so the constraint has no effect.

The quantity compared against the limit is `usedBuffers` — buffers handed out by `createBuffer()` and not yet returned by `releaseBuffer()` (`SimpleCachedBufferPool.java:43`, `70`, `90`, `119`).

**A3. Mechanism.**
1. Manager start: `segmentBuilder.createBufferPool()` constructs `SimpleCachedBufferPool(N, segmentSize, type)` (`AbstractCommitLogSegmentManager.java:155`); the given line [`SimpleCachedBufferPool.java:61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java#L61) creates the queue of idle buffers with requested capacity N.
2. The check, [`SimpleCachedBufferPool.java:119`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java#L119): `return usedBuffers.get() >= maxBufferPoolSize;`, called through [`AbstractCommitLogSegmentManager.java:243`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L243) (`atSegmentBufferLimit()`).
3. The enforcing use: the single `COMMIT-LOG-ALLOCATOR` thread builds a segment (`AbstractCommitLogSegmentManager.java:189`), then waits on [`AbstractCommitLogSegmentManager.java:108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L108) `managerThreadWaitCondition = () -> (availableSegment == null && !atSegmentBufferLimit())` (`waitOnCondition` at line 225). So a new segment (and so a new buffer) is only built when no spare segment exists **and** `usedBuffers < N`. Also [`AbstractCommitLogSegmentManager.java:194`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L194) uses the same check.
4. At the limit: writers that filled `allocatingFrom` call `advanceAllocatingFrom` → `awaitAvailableSegment` (`AbstractCommitLogSegmentManager.java:317`, `337-348`) and block, timed by the `WaitingOnSegmentAllocation` metric (`CommitLogMetrics.java:52`). They resume when a segment is synced to its end and closed: `CommitLogSegment.sync` → `internalClose()` (`CommitLogSegment.java:365-369`) → `releaseBuffer` + `notifyBufferFreed()` → `wakeManager()` (`FileDirectSegment.java:58-69`, `DirectIOSegment.java:147-158`, `AbstractCommitLogSegmentManager.java:654-657`).
5. Release side, [`SimpleCachedBufferPool.java:94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java#L94): `if (!bufferPool.offer(buffer)) FileUtils.clean(buffer);` — idle buffers are kept if the queue has room, otherwise freed.

Bound: only the allocator thread creates segments, and it creates one only while `usedBuffers < N`, so `usedBuffers ≤ N`. Total allocated buffers = used + idle; a new buffer is allocated only when the idle queue is empty (`SimpleCachedBufferPool.java:71-77`), so at that moment total = used ≤ N; release/poll never raise the total. Hence live segment buffers ≤ N × buffer size.

Overshoot / bypass:
- `createBuffer()` itself does not refuse anything (class javadoc lines 29-30: "Will allow you to go past the max"); the cap lives only in the manager's wait condition. A caller that creates buffers without the manager is unbounded.
- Line 61 does not size the queue to exactly N: jctools 3.1.0 (`.build/parent-pom-template.xml:1074-1077`) `MpmcArrayQueue(capacity)` requires `capacity >= 2` and `ConcurrentCircularArrayQueue` rounds it up to a power of two (`Pow2.roundToPowerOfTwo`). So N=3 keeps up to 4 idle buffers, N=5 keeps 8, contrary to the comment on line 60. In the commit-log integration this does not raise the total (argument above), but the pool on its own can retain more than N; and N ≤ 1 throws `IllegalArgumentException` at commit-log start.
- Outside the cap: the per-thread reusable buffer (`getThreadLocalReusableBuffer`, `ThreadLocalByteBufferHolder.java:71-82`) used by the sync thread for the compressed output (`CompressedSegment.java:67-68`, ≈ `initialCompressedBufferLength(length)` ≤ about one segment) or encrypted output (`EncryptedSegment.java:112`, one segment size), grown but never shrunk.
- The pool is drained only at shutdown (`AbstractCommitLogSegmentManager.java:595`).

**A4. Other consumers.** Direct memory: Cassandra's chunk-cache/networking `BufferPool` (`file_cache_size`, `networking_cache_size`), Netty, compression of sstables during flush, memtables with `offheap_*` allocation. Heap: memtables, caches, everything else. Disk: commit-log files themselves are bounded separately by `commitlog_total_space` (`Config.java:389-390`, flush-to-reclaim in `AbstractCommitLogSegmentManager.java:246-263`), not by this constraint.

**A5. Evidence beyond the source.**
- Existing test `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentBackpressureTest.java:77-145` — with sync blocked by Byteman, LZ4, 1 MiB segments and N=3, it asserts exactly 3 active segments (lines 117-122).
- jctools 3.1.0 source: https://github.com/JCTools/JCTools/blob/v3.1.0/jctools-core/src/main/java/org/jctools/queues/MpmcArrayQueue.java (capacity ≥ 2 check) and https://github.com/JCTools/JCTools/blob/v3.1.0/jctools-core/src/main/java/org/jctools/queues/ConcurrentCircularArrayQueue.java (`Pow2.roundToPowerOfTwo`).
- JDK `BufferPoolMXBean`: https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html

## B. Verification solution

**B1. Claim under test.** With commit-log compression enabled, the number of live commit-log segment buffers never exceeds `commitlog_max_compression_buffers_in_pool` (N), so the memory they occupy is at most N × `commitlog_segment_size` (plus one per-thread compression buffer); when writers outrun sync, they block (`WaitingOnSegmentAllocation` grows) rather than allocating more. The claim is wrong if live segment buffers / their memory exceed N per segment size, or if the plateau does not move with N.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk: `rsync -a ~/cassandra-5.0.9/ /mydata/s4-o44/unit/cassandra/` and work only there. `cd /mydata/s4-o44/unit/cassandra && ant jar build-test` (once). Two new test classes under `test/unit/org/apache/cassandra/db/commitlog/` in the copy (below). Test JVM uses the build's default test JVM options; direct memory default is fine (≤ 8 MiB needed).

Class 1, `PoolCapManagerTest.java` (modelled on `CommitLogSegmentBackpressureTest`, BMUnitRunner, the same two `@BMRule`s blocking `AbstractCommitLogService$SyncRunnable.run` around `CommitLog.sync(boolean)` with a static `Semaphore allowSync`):
```java
int n = Integer.parseInt(System.getenv().getOrDefault("CAP_N", "3"));
DatabaseDescriptor.daemonInitialization();
DatabaseDescriptor.setCommitLogCompression(new ParameterizedClass("LZ4Compressor", ImmutableMap.of()));
DatabaseDescriptor.setCommitLogSegmentSize(1);                 // 1 MiB
DatabaseDescriptor.setCommitLogSync(CommitLogSync.periodic);
DatabaseDescriptor.setCommitLogSyncPeriod(10_000);
DatabaseDescriptor.setCommitLogMaxCompressionBuffersPerPool(n);
DatabaseDescriptor.initializeCommitLogDiskAccessMode();
SchemaLoader.prepareServer(); /* create KEYSPACE1/Standard1 as in the existing test */
BufferPoolMXBean direct = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)
        .stream().filter(b -> b.getName().equals("direct")).findFirst().get();
long d0 = direct.getMemoryUsed();
long w0 = CommitLog.instance.metrics.waitingOnSegmentAllocation.getCount();
allowSync.acquire();                                           // block sync => no segment is ever closed
Thread t = new Thread(() -> { for (int i = 0; i < 64; i++) CommitLog.instance.add(m); }); // m = 256 KiB random value
t.setDaemon(true); t.start();
Thread.sleep(5000);
AbstractCommitLogSegmentManager clsm = CommitLog.instance.segmentManager;
System.out.printf("CAP_N=%d active=%d pool=%s directDelta=%d waits=%d alive=%b%n",
    n, clsm.getActiveSegments().size(), clsm.getBufferPool(), direct.getMemoryUsed() - d0,
    CommitLog.instance.metrics.waitingOnSegmentAllocation.getCount() - w0, t.isAlive());
allowSync.release(); t.join(60_000);
```
(`getBufferPool()` is package-private, `AbstractCommitLogSegmentManager.java:640`; the test is in the same package. `toString()` prints `usedBuffers`, `SimpleCachedBufferPool.java:122-131`.)

Class 2, `PoolQueueCapacityTest.java` (plain JUnit, no Cassandra startup): for the given N, `new SimpleCachedBufferPool(n, 1<<20, BufferType.OFF_HEAP)`; call `createBuffer()` K=10 times keeping references; print `toString()`, `atLimit()`, direct-pool delta; release all 10; then call `createBuffer()` 10 more times and count how many come back with the identical identity of a released buffer (`IdentityHashMap`) = retained idle count; print direct delta after release. Also `new SimpleCachedBufferPool(1, …)` inside `assertThrows`.

> **Stage-4 audit amendment M1 (2026-11-11, environment, no prediction change).** Working tree `/mydata/jingsong-cass-s4/o44/src` made with `cassandra/stage4-runtime-verification/copy-source.sh` (not `rsync ~/cassandra-5.0.9`), `ant build-test` once; unit logs in `/mydata/jingsong-cass-s4/o44/unit/`. The node is shared, so the BMUnit Byteman listener is moved off 9091: every `ant testsome` gets `-Dtest.jvm.args=-Dorg.jboss.byteman.contrib.bmunit.agent.port=9491`.

> **Stage-4 audit amendment M2 (2026-11-11, before any reading; B2d/B2f).** `d0` and `w0` are read after `SchemaLoader.prepareServer()` has restarted the commit log (`ServerTestUtils.cleanupAndLeaveDirs` → `CommitLog.restartUnsafe`), when the allocating segment and the reserve segment already hold `u0` buffers (expected `u0 = 2`). Class 1 therefore also prints `u0` (`usedBuffers` at the moment `d0` is read), and the direct-delta prediction is `(N − u0) × 1 MiB`, tolerance the larger of ±10 % and ±256 KiB (B2f amended below).

> **Stage-4 audit amendment M3 (2026-11-11, before any reading; B2d/B2f/B2g).** The `WaitingOnSegmentAllocation` timer is stopped only when a wait ends (signalled or cancelled, `WaitQueue.java:446-468`), so the wait the writer is blocked in at the 5 s sample is not yet counted and `waits` at the sample can be 0 while the cap binds. Class 1 therefore also prints, at the sample: `atLimit` (`getBufferPool().atLimit()`) and whether the writer thread's stack contains `AbstractCommitLogSegmentManager.awaitAvailableSegment` (`writerInAwait`); and after `allowSync.release(); t.join(60_000)`: `waitsAfter` (count − `w0`) and `activeAfter`. In B2g row 1, "writer blocked, waits ≥ 1" is read as: writer alive **and** `writerInAwait=true` at the sample, **and** `waitsAfter ≥ 1`. The same class also samples at 3 s (context only, to show the count is not still rising).

**B2b. Knobs.** `CAP_N` ∈ {3, 5, 8} (default, a non-power-of-two above it, a power of two), plus N=1 in class 2 only. Set by environment variable inherited by the forked test JVM.

**B2c. Workload.** Class 1: 64 mutations × 256 KiB = 16 MiB into 1 MiB segments → about 16+ segments needed, far above N=8; with sync blocked no segment can close, so the limit is reached and passed by demand. Class 2: 10 buffers > N for all N.

**B2d. Observables and instruments.** Class 1: `getActiveSegments().size()`, `usedBuffers` from `toString()`, `BufferPoolMXBean("direct").getMemoryUsed()` delta (LZ4 buffers are direct), `WaitingOnSegmentAllocation` count, whether the writer thread is still alive (blocked). Class 2: `usedBuffers`, `atLimit()`, direct delta, retained-idle count. Not observable directly: which thread holds a buffer; the plateau is inferred from counts at a single 5 s sample.

**B2e. Procedure.**
1. `echo "start unit $(date -u +%FT%TZ)"`; `cd /mydata/s4-o44/unit/cassandra`.
2. Add the two classes; `ant build-test`.
3. For N in 3 5 8: `CAP_N=$N ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.PoolCapManagerTest 2>&1 | tee /mydata/s4-o44/unit/mgr-$N.log` and the same for `PoolQueueCapacityTest` → `queue-$N.log`.
4. `grep CAP_N /mydata/s4-o44/unit/*.log`; check no leftover JVM (`pgrep -f PoolCap` empty).

**B2f. Predictions.**
| N | active segments | usedBuffers | direct delta (class 1) | waits | writer thread |
|---|---|---|---|---|---|
| 3 | 3 | 3 | ≈ 3 MiB (3 × 1 MiB, ±10%) | ≥ 1 | alive (blocked) |
| 5 | 5 | 5 | ≈ 5 MiB | ≥ 1 | alive |
| 8 | 8 | 8 | ≈ 8 MiB | ≥ 1 | alive |

> **Stage-4 audit amendment M2/M3 (2026-11-11, before any reading).** The direct-delta column reads `(N − u0) × 1 MiB` (±10 % or ±256 KiB, whichever is larger): 1 / 3 / 6 MiB for N = 3 / 5 / 8 when `u0 = 2`. The waits column is `waitsAfter ≥ 1` (M3); at the sample also `atLimit = true` and `writerInAwait = true`. Pass/fail of each cell is computed by `harness/.../unit-analyze.py` from these definitions.

Class 2: usedBuffers = 10 and direct delta ≈ 10 MiB for every N (pool alone does not cap); `atLimit()` true; retained idle after release = 4 (N=3), 8 (N=5), 8 (N=8); N=1 throws `IllegalArgumentException`.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| active = usedBuffers = N, direct ≈ N MiB, writer blocked, waits ≥ 1 | Claim supported: the check caps segment buffers at N |
| active or usedBuffers > N | Claim wrong: the manager overshoots the limit |
| active < N and writer finished | Limit not reached (workload too small or sync not blocked) — not confirmed; rerun with more mutations / check Byteman rule fired |
| active = N but direct delta ≫ N MiB | Buffers come from elsewhere; cap on count does not bound memory — claim partly wrong |
| Class 2 retained = N exactly | Queue not rounded; the A3 overshoot note is wrong (does not affect B1) |
| Class 2 usedBuffers < 10 | Pool itself caps; A3 description wrong |

> **Stage-4 audit amendment M4 (2026-11-11, before any reading).** A reading that matches no row is "Not confirmed (no matching row)". "Claim supported" (row 1) needs row 1 to hold for **all three** N, the plateau to track N (B2h), and class 2 usedBuffers = 10 for every N (the positive control). Writer blocked elsewhere (`writerInAwait=false` while alive with active < N) matches no row.

**B2h. Controls.** Varying N with everything else fixed: the plateau must track N (3→5→8), ruling out an unrelated limit (e.g. `commitlog_total_space`, which is ≥ GB here). Class 2 is the positive control that the same allocation path allocates past N when the manager's check is absent. Byteman rule firing is verified by `waits ≥ 1` and the writer thread being alive.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node (16 cores, ~14 GiB free). `rsync -a ~/cassandra-5.0.9/ /mydata/s4-o44/node/cassandra/`; `cd /mydata/s4-o44/node/cassandra && ant jar` (JDK 11). Copy `conf/` to `/mydata/s4-o44/node/conf` and set `CASSANDRA_CONF` to it. In `conf/cassandra.yaml`:
```yaml
cluster_name: o44
data_file_directories: [/mydata/s4-o44/node/data]
commitlog_directory: /mydata/s4-o44/node/commitlog
saved_caches_directory: /mydata/s4-o44/node/saved_caches
hints_directory: /mydata/s4-o44/node/hints
cdc_raw_directory: /mydata/s4-o44/node/cdc_raw
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
seed_provider: [{class_name: org.apache.cassandra.locator.SimpleSeedProvider, parameters: [{seeds: "127.0.0.1:7100"}]}]
storage_port: 7100
native_transport_port: 9142
commitlog_segment_size: 64MiB
commitlog_compression:
  - class_name: ZstdCompressor
    parameters:
      compression_level: 19          # slow, off-heap; makes sync lag writers so the cap binds
commitlog_sync: periodic
commitlog_sync_period: 10000ms
periodic_commitlog_sync_lag_block: 600000ms   # keep the periodic-lag block out of the way
commitlog_total_space: 8192MiB
write_request_timeout: 60000ms
commitlog_max_compression_buffers_in_pool: <N>
```
In `conf/cassandra-env.sh` set `JMX_PORT="7299"`. In `conf/jvm-server.options`/`jvm11-server.options`: `-Xms4G -Xmx4G`, `-XX:MaxDirectMemorySize=3G`, `-XX:NativeMemoryTracking=summary`. Total ≤ ~8 GiB resident at N=24 (heap 4 GiB + up to 1.6 GiB commit-log buffers + other), within 14 GiB.

> **Stage-4 audit amendment M5 (2026-11-11, environment, no prediction change).** Paths and ports: everything under `/mydata/jingsong-cass-s4/o44/node/` (data, commitlog, saved_caches, hints, cdc_raw, conf, logs, pid); the node runs from the unit tier's tree `/mydata/jingsong-cass-s4/o44/src` (built; no `ant` runs while the node is up). Ports (shared node): `storage_port: 7400`, `ssl_storage_port: 7401`, `native_transport_port: 9442`, seeds `127.0.0.1:7400`, `JMX_PORT=7599`. Heap and direct memory are set by environment at start, `MAX_HEAP_SIZE=4G MAX_DIRECT_MEMORY_SIZE=3G` (5.0.9's `cassandra-env.sh:139-158` adds its own `-XX:MaxDirectMemorySize` unless set this way), and `JVM_EXTRA_OPTS=-XX:NativeMemoryTracking=summary` scoped to the `bin/cassandra` command. `native_transport_timeout: 60000ms` is added so a write held by a blocked commit log is not cut at 12 s (load shape only; the readout is direct memory).

**B3b. Knobs.** `commitlog_max_compression_buffers_in_pool` ∈ {3, 6, 12, 24}: caps 192, 384, 768, 1536 MiB at 64 MiB segments, well separated from noise (tens of MiB) and under `MaxDirectMemorySize` 3 GiB. Set in yaml, restart between values with wiped data/commitlog dirs.

**B3c. Workload.** `tools/bin/cassandra-stress write n=2000000 cl=ONE -rate threads=64 -col n=FIXED\(1\) size=FIXED\(4096\) -mode native cql3 port=9142 -node 127.0.0.1 -errors ignore -schema "replication(factor=1)"` (≈ 8 GiB offered, stopped at 180 s if not done). Random 4 KiB values are near-incompressible; Zstd level 19 compresses only a few MB/s on the single sync thread, while 64 writer threads append at ≥ 100 MB/s, so a 64 MiB segment fills in under a second and full segments accumulate faster than sync closes them → `usedBuffers` reaches N within seconds for N ≤ 24 (24 × 64 MiB = 1.5 GiB < ~20 s of writes). Duration 180 s per N.

> **Stage-4 audit amendment M6 (2026-11-11, runbook defect found by a parse check without a server, no prediction change).** In 5.0.9 `-mode native cql3 port=9142` ignores `native` and `cql3` as deprecated and does not set the native port (stress printed `Native Port: 9042`, so it would write to the wrong port). The command uses `-port native=9442 jmx=7599` instead and drops `-mode native cql3 port=…`; everything else is as filed.

> **Stage-4 run amendment M10 (2026-11-11, runbook defect D2 found when the first cluster start refused the yaml, before any reading; no prediction change).** In B3a `commitlog_compression` → `parameters` must be a list of maps (`ParameterizedClass.java:61-65` casts it to `List` and takes element 0; `conf/cassandra.yaml:665-668`); as filed (a map) the node dies at start with `ClassCastException: ConcurrentHashMap cannot be cast to List`. Written as `parameters: [ {compression_level: "19"} ]`. The cluster tier restarted from its beginning.

**B3d. Observables and instruments.** Every 2 s (script below):
- direct memory: `bin/nodetool -p 7299 sjk mx -b java.nio:type=BufferPool,name=direct -mg -f MemoryUsed` (main readout) and `-f Count`;
- `bin/nodetool -p 7299 sjk mx -b org.apache.cassandra.metrics:type=CommitLog,name=WaitingOnSegmentAllocation -mg -f Count`;
- `ls /mydata/s4-o44/node/commitlog/*.log | wc -l` (segment files; includes closed-but-not-yet-recycled ones, so ≥ live buffers — context only);
- every 30 s `jcmd <pid> VM.native_memory summary | grep -A2 Other` (cross-check of direct memory);
- `du -sh /mydata/s4-o44/node`.
Not observable directly: `usedBuffers` itself (no JMX); inferred from direct-memory plateau differences between N values.

> **Stage-4 audit amendment M7 (2026-11-11, instrument, observables unchanged).** One JMX client JVM (`harness/.../Sampler.java`) reads the same attributes every 2 s (`java.nio:type=BufferPool,name=direct` `MemoryUsed` and `Count`; `org.apache.cassandra.metrics:type=CommitLog,name=WaitingOnSegmentAllocation` `Count`) instead of three `nodetool sjk` JVM starts per sample, and adds the segment-file count; NMT summary every 30 s and `du -sb` of the node folder every 30 s by the run script.

**B3e. Procedure.** For each N in 3 6 12 24:
1. `rm -rf /mydata/s4-o44/node/{data,commitlog,saved_caches,hints,cdc_raw}`; set N in yaml.
2. `CASSANDRA_CONF=/mydata/s4-o44/node/conf bin/cassandra -p /mydata/s4-o44/node/pid > /mydata/s4-o44/node/out-$N.log 2>&1`; wait until `bin/nodetool -p 7299 status` shows `UN`. Check `grep -i "commitlog_max_compression_buffers_in_pool\|ZstdCompressor" logs/system.log` shows the values.
3. Baseline 30 s of samples at idle.
4. Start the sampler: `while sleep 2; do echo "$(date +%s) $(nodetool ... MemoryUsed) $(nodetool ... WaitingOnSegmentAllocation Count) $(ls commitlog/*.log|wc -l)"; done > samples-$N.txt &`.
5. Run the stress command with `timeout 180`.
6. Stop sampler; `bin/nodetool -p 7299 drain`; `kill $(cat pid)`; wait for exit; `pgrep -f CassandraDaemon` must be empty.
Then one control run: N=6 with `commitlog_compression` removed (legacy → mmap, no pool).

> **Stage-4 audit amendment M8 (2026-11-11, stop condition, no prediction change).** Step 6: with Zstd level 19 a drain must compress up to N × 64 MiB at a few MB/s, so `nodetool drain` is bounded at 120 s, then SIGTERM with 60 s, then SIGKILL of the node's own PID; data are wiped before the next value anyway. Each value's run also stops early if `df` shows < 30 GiB free on `/mydata`.

**B3f. Predictions.** Plateau of direct `MemoryUsed` during stress, minus idle baseline, = N × 64 MiB + ≤ ~70 MiB (sync-thread compression buffer) + other direct users (same across runs, B3h): about 0.2–0.3 GiB (N=3), 0.4–0.5 GiB (6), 0.8–0.9 GiB (12), 1.5–1.65 GiB (24). Pairwise plateau differences ≈ ΔN × 64 MiB (192, 384, 768 MiB) within ±15%. `WaitingOnSegmentAllocation` Count increases during stress for every N (cap binds). Never exceeding (N+2) × 64 MiB + baseline-variance at any sample. mmap control: plateau independent of the knob, no growth of direct memory by segment buffers.

> **Stage-4 audit amendment M9 (2026-11-11, before any reading; windows and thresholds).** The idle baseline already holds the buffers of the allocating segment and the reserve segment (`u0 = 2`: `AbstractCommitLogSegmentManager.start()` and the manager loop, lines 150-190), so plateau − baseline ≈ (N − 2) × 64 MiB + ≤ ~70 MiB + other; the absolute bands are amended to **(N − 2) × 64 MiB + [0, 160] MiB**: 64–224 MiB (N=3), 256–416 (6), 640–800 (12), 1408–1568 (24). Pairwise differences are unchanged (ΔN × 64 MiB ± 15 %). Fixed windows: **baseline** = median of the direct `MemoryUsed` samples of the 30 s idle window before stress; **plateau** = median of the samples from stress start + 60 s to stress end; **flat** = max − min within the plateau window ≤ 96 MiB; **never exceeding** = max sample from stress start to stress end − baseline ≤ (N + 2) × 64 MiB + 32 MiB; **waits grow** = Count at stress end − Count at stress start ≥ 1; **pairwise** = consecutive pairs 3→6, 6→12, 12→24, each within ±15 % of ΔN × 64 MiB. **mmap control holds** if its plateau − baseline ≤ 64 MiB; it "shows the same N-dependence" if its plateau − baseline ≥ (compressed N=6 plateau − baseline) − 64 MiB. B3g row 4 ("limit not reached") = waits growth 0 **and** plateau − baseline < (N − 2) × 64 MiB. "Plateau does not change with N" = plateau(24) − plateau(3) < 0.5 × 21 × 64 MiB. A reading that matches no row is "Not confirmed (no matching row)". Computed by `harness/.../cluster-analyze.py`.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| Plateaus step by ≈ ΔN × 64 MiB, flat within each run, waits grow | Claim supported: the constraint caps commit-log buffer memory |
| Direct memory above N × 64 MiB + compression buffer + baseline at any sample | Claim wrong: overshoot |
| Plateau does not change with N while waits grow | Something else binds first; claim not supported |
| Waits stay 0 and plateau < N × 64 MiB | Limit not reached (sync kept up) — not confirmed; raise threads, compression level, or use smaller N |
| mmap control shows the same N-dependence | Plateau not caused by the pool — measurement invalid |

**B3h. Controls.** Same workload, same build, only N varies (differences cancel other direct users). The N=24 run is the positive control that this workload can push commit-log buffers far beyond the smaller caps, so a flat plateau at small N is the cap, not lack of demand. The mmap run (no pool) shows the knob has no effect without the pool. NMT "Other" must agree with the MXBean within ~10%.

**B4. Risks and cleanup.** Unit: only the copy under `/mydata/s4-o44/unit` is modified; test JVMs exit; `pgrep -f PoolCap` empty. Cluster: data + commit log + sstables on `/mydata/s4-o44/node` (local disk; expect < 15 GiB per run since writers are throttled by sync; check `df -h /mydata` before each run, abort if < 30 GiB free); stop the node with drain + kill, verify no `CassandraDaemon`/`cassandra-stress` process and no listener on 7100/9142/7299 (`ss -ltnp`). Remove `/mydata/s4-o44` when results are filed. Never touch the shared source tree.

## C. Sources read

src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java
src/java/org/apache/cassandra/io/util/ThreadLocalByteBufferHolder.java
src/java/org/apache/cassandra/io/compress/BufferType.java
src/java/org/apache/cassandra/io/compress/LZ4Compressor.java
src/java/org/apache/cassandra/io/compress/DeflateCompressor.java
src/java/org/apache/cassandra/io/compress/ZstdCompressor.java
src/java/org/apache/cassandra/io/compress/SnappyCompressor.java
src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java
src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java
src/java/org/apache/cassandra/db/commitlog/FileDirectSegment.java
src/java/org/apache/cassandra/db/commitlog/CompressedSegment.java
src/java/org/apache/cassandra/db/commitlog/EncryptedSegment.java
src/java/org/apache/cassandra/db/commitlog/DirectIOSegment.java
src/java/org/apache/cassandra/db/commitlog/MemoryMappedSegment.java
src/java/org/apache/cassandra/db/commitlog/CommitLog.java
src/java/org/apache/cassandra/db/commitlog/PeriodicCommitLogService.java
src/java/org/apache/cassandra/metrics/CommitLogMetrics.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/tools/nodetool/Sjk.java
conf/cassandra.yaml
test/conf/cassandra.yaml
test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentBackpressureTest.java
test/unit/org/apache/cassandra/db/commitlog/DirectIOSegmentTest.java
test/data/config/version=5.0-alpha1.yml
.build/parent-pom-template.xml
doc/modules/cassandra/pages/architecture/storage-engine.adoc
doc/modules/cassandra/pages/managing/operating/compression.adoc
https://raw.githubusercontent.com/JCTools/JCTools/v3.1.0/jctools-core/src/main/java/org/jctools/queues/MpmcArrayQueue.java
https://raw.githubusercontent.com/JCTools/JCTools/v3.1.0/jctools-core/src/main/java/org/jctools/queues/ConcurrentCircularArrayQueue.java

## D. Stage-4 feedback

**2026-11-11, run 1 (unit and cluster tiers), results file [`../../stage4-runtime-verification/results/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous.md`](../../stage4-runtime-verification/results/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous.md).** Unit **Not confirmed (no matching row)**, cluster **Not confirmed (B3g row 4, limit not reached at N=24)**; Effect `undetermined` on both tiers; Outcome class **undetermined**. Audit amendments M1-M9 and runbook fix M10 are above, each next to the text it changes.

- Unit: for N = 3, 5, 8, active segments = usedBuffers = N exactly, `atLimit` true, writer parked in `awaitAvailableSegment`, waits after release ≥ 17, and the direct delta steps by exactly 1 MiB per buffer (2,097,152 B for 3→5, 3,145,728 B for 5→8). Each direct delta is (N − 2) MiB + 262,195 B. The extra 262,195 B is the writer thread's direct `DataOutputBuffer.scratchBuffer` (`DataOutputBuffer.java:63-90`, direct by default), grown to one serialized mutation and kept, so it is outside the pool. For N = 3 it exceeds the frozen tolerance (±256 KiB) by 51 B, so row 1 does not hold for all three N (M4) and no row matches. Class 2 (positive control): the pool alone hands out 10 buffers for every N; it keeps 4 / 8 / 8 idle buffers for N = 3 / 5 / 8 (power-of-two rounding, as A3 says), and N = 1 throws `IllegalArgumentException`.
- Cluster (Zstd level 19, 64 MiB segments): plateaus net of the idle baseline are 137.5 / 329.6 / 713.6 MiB for N = 3 / 6 / 12. The steps are exactly 192.0 and 384.0 MiB (ΔN × 64 MiB), each plateau flat to ≤ 0.3 MiB, and `WaitingOnSegmentAllocation` grows by 352 / 384 / 192. At N = 24 the plateau stopped at 969.7 MiB (about 16 buffers) with no completed waits. MutationStage was still 32 active / 96 pending after stress, and the client timed out. Another bound stopped demand before 24 buffers were needed; it fits the 1024 MiB memtable on-heap threshold (= 16 × 64 MiB), but that is inferred. The mmap control (no pool) moved 9.6 MiB.
- For stage 3: (1) A4 omits the per-writer-thread direct `DataOutputBuffer` scratch buffer, one more direct consumer outside the cap, about one mutation per writer thread. (2) B3's N = 24 needs more commit-log demand than the default memtable space allows: raise the heap or `memtable_heap_space`, or use N ≤ 12 plus a value between 12 and 16. (3) The unit tolerance on the direct delta needs room for that scratch buffer. (4) B3h's NMT "Other" cross-check cannot hold in absolute terms: under stress NMT "Other" exceeds the MXBean by a constant 528 MiB (about 540,690 KB) at every value, including mmap, while the differences across N agree to < 0.2 MiB.
