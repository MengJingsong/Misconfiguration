# mapreduce.reduce.shuffle.indexcache.mb — verification solution  <!-- file: cases/mapreduce.reduce.shuffle.indexcache.mb-readIndexFileToCache-totalMemoryAllowed--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`IndexCache.java:132`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IndexCache.java#L132), `if (totalMemoryUsed.addAndGet(newInd.getSize()) > totalMemoryAllowed)` in `IndexCache.readIndexFileToCache` (row unit; this is also the main enforcement point) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`. The NodeManager's ShuffleHandler keeps one `IndexCache` whose accounted size (24 bytes × partitions per cached map attempt) is checked against `indexcache.mb × 2^20` after every load and brought back under it by FIFO eviction, so the number of cached map-output indexes, and the heap they hold, follows the key. Caveat: only the index payload is counted, not about 330 bytes of per-entry object overhead, so real heap is about 1.04× the cap with ~400 reducers per job and up to about 15× with 1 reducer. |
| Ground | — |

Parts of the stem: constraint `mapreduce.reduce.shuffle.indexcache.mb`; function `readIndexFileToCache` (the method holding the given `if`); operand `totalMemoryAllowed`.

## A. Constraint trace

**A1. The constraint.**
- Name: `mapreduce.reduce.shuffle.indexcache.mb`. It is a configuration key, declared as `MRJobConfig.SHUFFLE_INDEX_CACHE` at [`MRJobConfig.java:590`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java#L590).
- Deprecated aliases map to it: `mapred.tasktracker.indexcache.mb` and `mapreduce.tasktracker.indexcache.mb` (`ConfigUtil.java:291-294`; `TTConfig.java:38-39`; `hadoop-common/src/site/markdown/DeprecatedProperties.md:211-212`).
- `*-default.xml` entry: **none**. The key does not appear in `mapred-default.xml` or any other `*-default.xml` in the tree. The only default is the Java fallback `10` in `conf.getInt(MRJobConfig.SHUFFLE_INDEX_CACHE, 10)` at [`IndexCache.java:45-46`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IndexCache.java#L45-L46), so that value applies when the key is unset.
- Unit: MiB. The code converts it to bytes with `* 1024 * 1024` in `int` arithmetic, giving `totalMemoryAllowed` (field at `IndexCache.java:33`). The default is 10 MiB = 10,485,760 bytes.
- Integer overflow: values of 2048 or more overflow. 2048 gives `Integer.MIN_VALUE`, 2049–4095 give negative values, and 4096 gives 0. See A3.
- Who reads it: the **NodeManager**, through the `mapreduce_shuffle` auxiliary service (`ShuffleHandler`).
  - `ShuffleHandler.serviceStart` calls `createHandlerContext()` once (`ShuffleHandler.java:421`).
  - That builds `new IndexCache(new JobConf(conf))` from the NM's own configuration (`ShuffleHandler.java:358-403`, line 400).
- Despite the `mapreduce.reduce.` prefix, a per-job setting has **no effect**. The cache is per NodeManager and is built once from the NM configuration.
- How to set it: in `yarn-site.xml` on the NM host. `mapred-site.xml` also works, because the `JobConf` static initializer adds `mapred-site.xml` as a default resource (`JobConf.java:123-124`, `ConfigUtil.java:41-46`). The value is read once, in the constructor (`IndexCache.java:43-48`), so a change needs an **NM restart**. There is no refresh command.
- The value in effect is logged: `IndexCache created with max memory = <bytes>` (`IndexCache.java:47`).

**A2. What it caps.**
- Resource: NodeManager JVM **heap** held by the shuffle index cache. Each entry is the in-memory copy of one map attempt's `file.out.index`: a `SpillRecord` backed by a heap `ByteBuffer` of `partitions × 24` bytes (`SpillRecord.java:65-90`; `MapTask.MAP_OUTPUT_INDEX_RECORD_LENGTH = 24` at `MapTask.java:87`).
- Quantity compared: `totalMemoryUsed`, an `AtomicInteger` (`IndexCache.java:34`). It is the sum over cached entries of `IndexInformation.getSize() = mapSpillRecord.size() × 24` (`IndexCache.java:191-195`), where `size()` is the number of partitions (`SpillRecord.java:99-101`).
- The number of partitions equals the job's reducer count. The final index is written with `partitions = numReduceTasks` (`MapTask.java:1914-1933`), and the reader recovers it as `(24P+8)/24 = P` (`SpillRecord.java:74-76`).
- Object overhead is **not counted**: the map node, the `mapId` String key, the queue node, the `IndexInformation`, the `SpillRecord`, the `HeapByteBuffer`, the `LongBuffer` view and the array header.

**A3. Mechanism.**
1. A reducer's fetcher sends an HTTP shuffle request to the NM's ShuffleHandler port, listing map attempt ids. For each map, `ShuffleChannelHandler.populateHeaders` (`ShuffleChannelHandler.java:376-385`) and `sendMap` (`:303-328`) call `getMapOutputInfo` (`:339-372`). That resolves the index path through the `pathCache` and calls `indexCache.getIndexInformation(mapId, reduce, indexPath, user)` (`:359-360`).
2. `getIndexInformation` (`IndexCache.java:61-89`):
   - **Hit** (`cache.get(mapId)` is non-null): wait while the entry is under construction, then return.
   - **Miss**: call `readIndexFileToCache` (`:68`).
3. `readIndexFileToCache` (`IndexCache.java:97-136`):
   - It reserves the key with `putIfAbsent` and an empty placeholder (`:102-103`). The placeholder's `getSize()` is 0.
   - It reads the whole index file into a new `SpillRecord`, which allocates `ByteBuffer.allocate(P×24)` (`:119`, `SpillRecord.java:77`).
   - It publishes the record (`:125-128`) and appends `mapId` to the FIFO `queue` (`:130`).
4. **The check** at [`IndexCache.java:132`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IndexCache.java#L132): `if (totalMemoryUsed.addAndGet(newInd.getSize()) > totalMemoryAllowed) freeIndexInformation();`
   - **Under or at the limit:** nothing is evicted, and the entry stays cached.
   - **Over the limit:** `freeIndexInformation` (`IndexCache.java:178-186`, `synchronized`) loops `while (totalMemoryUsed.get() > totalMemoryAllowed)`. Each pass pops the oldest `mapId` from the queue, removes it from `cache`, and subtracts its size. The policy is FIFO by load time: hits do not refresh position, so it is not LRU. The just-loaded entry is still returned to the caller even if it was itself evicted.
   - Nothing blocks or fails. A later request for an evicted map re-reads the index file from local disk.
5. Steady state: with equal-sized entries of `24P` bytes, the cache holds at most `floor(totalMemoryAllowed / 24P)` entries once eviction has run.

Overshoot and bypass paths:
- **Transient overshoot, by design.** The check runs *after* the buffer is allocated and counted. Usage exceeds the cap by up to one entry per concurrent loader. Up to `mapreduce.shuffle.max.threads` netty workers can load at once (default `2 × cores`, `ShuffleHandler.java:335-354`), and entries under construction count 0 (`IndexCache.java:192`). Overshoot is at most about `workers × 24P` bytes.
- **Under-accounting of object overhead (A2).** Per-entry real heap is about `24P + ~330` bytes on a 64-bit JDK 8 with compressed oops. This estimate is not measured here; B2 measures it.
  - Components: ConcurrentHashMap node 32, a ~37-char `attempt_…` String key ~120, LinkedBlockingQueue node 24, `IndexInformation` 16, `SpillRecord` 24, `HeapByteBuffer` 48, array header 16, `ByteBufferAsLongBufferB` 48, table slot ~4–8.
  - With P=1, the cap of N MiB allows `N×2^20/24` entries but holds about 15× N MiB of heap. With the default 10 MiB that is about 437k entries and about 150 MiB.
- **Stale entries are kept.** `removeMap` (`IndexCache.java:146-160`) has no production caller; only tests call it. `ShuffleHandler.stopApplication` (`ShuffleHandler.java:321-331`) does not touch the cache. Entries of finished applications therefore stay until FIFO pushes them out. This does not break the cap, but the cache fills to the cap over NM uptime and stays full.
- **Int overflow of the cap.** `indexcache.mb ≥ 2048` overflows `int` (`IndexCache.java:46`).
  - 2048–4095 give a negative `totalMemoryAllowed`. On the first load, `freeIndexInformation` empties the queue, still sees `0 > negative`, and `queue.remove()` throws `NoSuchElementException`. That `RuntimeException`, not an `IOException`, escapes `getIndexInformation`.
  - 4096 gives 0, which disables caching: every entry is evicted right after it loads.
- **Values ≤ 0** (`0`, negative): `0` disables caching. Negative values behave like the overflow case.

**A4. Other consumers.** Other uses of NM heap in the shuffle path that this key does not control:
- The ShuffleHandler `pathCache`. It is a Guava cache bounded by `mapreduce.shuffle.pathcache.max-weight` (default 10 MiB of string length, `ShuffleHandler.java:109-111, 361-394`), with access expiry.
- Per-request `mapOutputInfoMap`, bounded by `mapreduce.shuffle.mapoutput-info.meta.cache.size` (`ShuffleChannelHandlerContext.java:113-115`, `ShuffleChannelHandler.java:382`).
- Netty buffers and transfer of the data file (`mapreduce.shuffle.transfer.buffer.size`, readahead).
- The NM's own state: containers, the NM state store, metrics.
- On disk, map output lives in `yarn.nodemanager.local-dirs`. The index cache never touches disk.
- Reducer-side shuffle memory (`mapreduce.reduce.shuffle.input.buffer.percent`, …) is in the reduce JVM and is unrelated.

**A5. Evidence beyond the source.**
- `hadoop-mapreduce-client-core/src/test/java/org/apache/hadoop/mapred/TestIndexCache.java`: `testLRCPolicy` (lines 53-123) fills a 1 MiB cache with 24,000-byte entries and checks that the oldest entry is pushed out. The test calls it "LRC"; the policy is FIFO.
- `hadoop-common/src/site/markdown/DeprecatedProperties.md:211-212`: the deprecated aliases.
- The Hadoop 3.4.2 `mapred-default.xml` documentation has no entry for this key, consistent with the tree.

## B. Verification solution

**B1. Claim under test.**
- The cap: with `mapreduce.reduce.shuffle.indexcache.mb = L`, after any shuffle load completes, the NodeManager's index cache's accounted size is ≤ `L × 2^20` bytes. It holds exactly `min(#distinct maps loaded, floor(L×2^20 / 24P))` entries, so the cache's heap scales linearly with L.
- The secondary claim: real retained heap per entry exceeds the accounted `24P` by a roughly constant ~300–400 bytes. For small P, real heap is therefore many times L.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8 and Maven 3.3+.
- Copy the tree to local disk first: `cp -a ~/hadoop-3.4.2 /tmp/s3u-o44/hadoop` (any local path with ~5 GB free; never the shared copy).
- Build once: `cd /tmp/s3u-o44/hadoop && mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core -am install -DskipTests -Dmaven.javadoc.skip=true`.
- Test source: a new file `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/test/java/org/apache/hadoop/mapred/TestIndexCacheCap.java`. It must be in package `org.apache.hadoop.mapred`, because `IndexCache` is package-private.
- JVM: the surefire default `-Xmx2048m` (`hadoop-project/pom.xml:187`) is enough.

**B2b. Knobs.**
- Part 1 (cap enforcement): `SHUFFLE_INDEX_CACHE` ∈ {1, 2, 4} MiB, set with `conf.setInt(MRJobConfig.SHUFFLE_INDEX_CACHE, L)` on a fresh `JobConf` and a new `IndexCache` per value. With entries of 9,600 B, 1 and 2 force eviction and 4 does not, so 4 is the no-eviction control.
- Part 2 (heap versus accounted): L ∈ {1, 4} MiB with P=1 (24 B accounted per entry).
- Part 3 (edge values, optional): L ∈ {0, 2048, 4096}.

**B2c. Workload.**
- Part 1:
  - Write one valid index file with P=400 partitions (400 × 24 B + 8 B CRC). Reuse the `writeFile` helper pattern of `TestIndexCache.java:319-331`.
  - Call `cache.getIndexInformation("attempt_1700000000000_0001_m_" + String.format("%06d", i) + "_0", i % 400, file, currentUser)` for i = 0..399, so N = 400 distinct map ids. The cache key is the map id, so one file serves every id.
  - Accounted per entry: 9,600 B. Total offered: 3,840,000 B.
  - Arithmetic: 1 MiB = 1,048,576 holds 109 entries (110 × 9,600 = 1,056,000 > cap). 2 MiB = 2,097,152 holds 218. 4 MiB = 4,194,304 holds all 400.
- Part 2:
  - Write one index file with P=1 (32 bytes). Load N = 60,000 distinct ids of the same `attempt_…` form.
  - L=1: cap 1,048,576 / 24 = 43,690 entries.
  - L=4: 174,762 ≥ 60,000, so all 60,000 stay.
- Part 3: load 3 ids with P=400 for each edge value.

**B2d. Observables and instruments.**
- Through reflection on the private fields `totalMemoryUsed` (`AtomicInteger`), `cache` (`ConcurrentHashMap`), `queue` and `totalMemoryAllowed`:
  - After each call: `totalMemoryUsed.get()`, `cache.size()`, `queue.size()`.
  - The maximum of `totalMemoryUsed` over all calls.
  - `cache.checkTotalMemoryUsed()` (`IndexCache.java:167-173`) at the end.
- Live instance counts from a class histogram taken inside the test: `ManagementFactory.getPlatformMBeanServer().invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"), "gcClassHistogram", new Object[]{new String[0]}, new String[]{String[].class.getName()})`.
  - This forces a full GC (live objects only).
  - Parse the rows for `org.apache.hadoop.mapred.IndexCache$IndexInformation`, `org.apache.hadoop.mapred.SpillRecord`, `java.nio.HeapByteBuffer` and `java.nio.ByteBufferAsLongBufferB`.
- Part 2 also measures heap: `MemoryMXBean.getHeapMemoryUsage().getUsed()` after the histogram call (which GCs), taken once after creating the empty cache and once after loading. Use the delta, and as a cross-check the per-class bytes reported in the histogram.
- Not observable directly: object layout. It is inferred from the histogram bytes per class.

**B2e. Procedure.**
1. Build (B2a).
2. Write `TestIndexCacheCap` with three test methods (`testCapEnforced`, `testHeapPerEntry`, `testEdgeValues`), each printing one line per knob value in this form:
   - `RESULT L=<mb> P=<p> N=<n> used=<bytes> entries=<n> maxUsed=<bytes> consistent=<bool> histIndexInfo=<n> histSpillRecord=<n> heapDelta=<bytes>`
   - Use `-Dtest.build.data=/tmp/s3u-o44/data` for the index files.
   - Part 3: wrap each `getIndexInformation` in try/catch and print the exception class.
3. Run: `cd /tmp/s3u-o44/hadoop && mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core test -Dtest=TestIndexCacheCap -Dtest.build.data=/tmp/s3u-o44/data`.
4. Collect the `RESULT` lines from `target/surefire-reports/org.apache.hadoop.mapred.TestIndexCacheCap-output.txt`.

**B2f. Predictions.**

| Part | L (MiB) | P | N | final `entries` (= hist IndexInformation = hist SpillRecord) | final `used` | max `used` seen after a call |
|---|---|---|---|---|---|---|
| 1 | 1 | 400 | 400 | **109** | 1,046,400 | ≤ 1,048,576 (single-threaded, each call evicts before returning) |
| 1 | 2 | 400 | 400 | **218** | 2,092,800 | ≤ 2,097,152 |
| 1 | 4 | 400 | 400 | **400** | 3,840,000 | 3,840,000 |
| 2 | 1 | 1 | 60,000 | **43,690** | 1,048,560 | ≤ 1,048,576 |
| 2 | 4 | 1 | 60,000 | **60,000** | 1,440,000 | 1,440,000 |

- In every case `consistent=true` and `queue.size() == entries`.
- Part 2 heap: `heapDelta / entries` ≈ 24 + 300–400 B. That gives about 14–17 MB retained for L=1 (43,690 entries), about 15× the 1 MiB cap.
- Part 3:
  - L=0: `entries` = 0 after each call, and the calls still return correct records.
  - L=4096: same as L=0 (cap wraps to 0).
  - L=2048: the first call throws `java.util.NoSuchElementException` out of `getIndexInformation`.
- **What would refute the claim:**
  - Final `entries` for L=1 or L=2 greater than the prediction, or `used` above `L×2^20` after a single-threaded call returns.
  - Entries the same for L=1, 2 and 4. That would mean the cap does not bind.
  - For the secondary claim: `heapDelta/entries` within ~10% of 24 B for P=1.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Entries 109 / 218 / 400 for L = 1 / 2 / 4 and `used ≤ L×2^20` after every call | Cap enforced as traced: claim confirmed for the unit tier |
| Entries grow with N regardless of L (400 for all L) | Check at `:132` not binding: claim refuted |
| Entries below prediction (for example 0 or 1) for L=1, 2 | Over-eviction (for example a wrong unit). The cap binds but not as traced; investigate |
| L=4 control shows 400 while L=1 shows 109 | Positive control moved; the difference is caused by L |
| P=1 `heapDelta/entries` ≈ 330–380 B | Under-accounting confirmed: real heap ≈ 15 × L for P=1 |
| P=1 `heapDelta/entries` ≈ 24–40 B | Overhead claim refuted (accounting near exact) |
| L=2048 throws `NoSuchElementException` | Overflow edge confirmed |
| L=2048 behaves like 2 GiB (no eviction, no error) | Overflow claim refuted |

**B2h. Controls.**
- L=4 (no eviction) shows that the workload loads 400 distinct entries.
- `checkTotalMemoryUsed()` shows the counter matches the cache.
- The histogram counts confirm that `cache.size()` matches live objects, with no hidden leftover references.
- Part 2 uses one shared index file, so file-system caches and handles are the same across L.
- Run each L in a fresh `IndexCache` and call the histogram (full GC) before measuring the baseline.

### B3. Cluster tier

**B3a. Environment and build.**
- Hardware: one Linux host (pseudo-distributed), ≥ 8 cores, ≥ 16 GB RAM, ≥ 30 GB free local disk.
- Build the distribution from a local copy, not the shared tree: `cp -a ~/hadoop-3.4.2 /local/s3c-o44/src && cd /local/s3c-o44/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`. Unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/local/s3c-o44/hadoop` (`$HADOOP_HOME`).
- Daemons: NameNode, DataNode, ResourceManager, one NodeManager (running the `mapreduce_shuffle` aux service), and optionally a JobHistory server.
- Environment, in `etc/hadoop/hadoop-env.sh` / `yarn-env.sh`: `export HADOOP_LOG_DIR=/local/s3c-o44/logs`, `export YARN_NODEMANAGER_HEAPSIZE=1024`.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=/local/s3c-o44/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=/local/s3c-o44/nn`, `dfs.datanode.data.dir=/local/s3c-o44/dn`.
- `yarn-site.xml`:
  - Aux service: `yarn.nodemanager.aux-services=mapreduce_shuffle`, `yarn.nodemanager.aux-services.mapreduce_shuffle.class=org.apache.hadoop.mapred.ShuffleHandler`.
  - Resources: `yarn.nodemanager.resource.memory-mb=8192`, `yarn.nodemanager.resource.cpu-vcores=32`, `yarn.scheduler.minimum-allocation-mb=256`.
  - Directories: `yarn.nodemanager.local-dirs=/local/s3c-o44/nm-local`, `yarn.nodemanager.log-dirs=/local/s3c-o44/nm-logs`.
  - Memory checks: `yarn.nodemanager.vmem-check-enabled=false`.
  - **The knob**: `mapreduce.reduce.shuffle.indexcache.mb` (B3b).
- `mapred-site.xml`:
  - `mapreduce.framework.name=yarn`.
  - Container sizes: `mapreduce.map.memory.mb=256`, `mapreduce.reduce.memory.mb=256`, `mapreduce.map.java.opts=-Xmx200m`, `mapreduce.reduce.java.opts=-Xmx200m`, `yarn.app.mapreduce.am.resource.mb=1024`.
  - `mapreduce.job.reduce.slowstart.completedmaps=1.0`.
  - Classpath: `yarn.app.mapreduce.am.env`, `mapreduce.map.env` and `mapreduce.reduce.env` all `HADOOP_MAPRED_HOME=$HADOOP_HOME`.
  - **Do not** set the knob here, to keep the per-job control clean.

**B3b. Knobs.**
- `mapreduce.reduce.shuffle.indexcache.mb` in the NM's `yarn-site.xml`, values L ∈ {1, 2, 4}. With 9,600-byte entries (R=400), 1 and 2 evict and 4 holds the whole workload. Optionally add 10 (unset, default), which should match 4.
- Each value needs a **NodeManager restart**: `yarn --daemon stop nodemanager; yarn --daemon start nodemanager`. The restart also empties the cache. There is no refresh.
- Confirm the value with `grep "IndexCache created with max memory" $HADOOP_LOG_DIR/*nodemanager*.log`. Expected values: 1,048,576 / 2,097,152 / 4,194,304.

**B3c. Workload.**
- Command: `yarn jar $HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-client-jobclient-3.4.2-tests.jar sleep -m 400 -r 400 -mt 1 -rt 1`. SleepJob is registered as `sleep` in `MapredTestDriver.java:92`, with options at `SleepJob.java:250-275`.
- Each map writes a final index of 400 partitions (9,608 B on disk). Each of the 400 reducers fetches its partition from all 400 maps through the NM's ShuffleHandler, so every map id is loaded into the cache at least once.
- Accounted total: 400 × 9,600 = 3,840,000 B (3.66 MiB). That is > 1 and 2 MiB, so they evict, and < 4 MiB, so 4 does not.
- About 800 containers of 256 MB, about 28 concurrent within 8 GB. Expect about 5–15 minutes per run.
- The cache keeps entries after the job ends (no `removeMap` caller), so it can be measured after completion.

**B3d. Observables and instruments.**
- NM pid: `jps | grep NodeManager`.
- Cache entry count after the job: `jmap -histo:live <nmpid> | grep -E 'IndexCache\$IndexInformation|mapred\.SpillRecord|java\.nio\.HeapByteBuffer'`. The command forces a full GC. The NM has no other users of `SpillRecord`.
  - `#instances` of `IndexCache$IndexInformation` = cache entries.
  - `SpillRecord` instances should match.
- Approximate retained cache heap: `#entries × (9,600 + 16)` for the arrays plus the per-class bytes of the classes above, taken from the histogram.
- Sampling during the job: every 30 s, `jmap -histo:live` on the NM (cheap at a 1 GB heap; note that it pauses the NM), to see the count never exceed the cap value.
- NM heap after full GC: `jcmd <nmpid> GC.heap_info`, before the job and after the job, as a coarse cross-check. The difference between L=1 and L=4 should be about 2.8–3 MB, which is near the noise of other NM heap, so the histogram count is the primary reading.
- NM log line from `IndexCache.java:47`.
- Not observable without debug logging: the order of eviction. FIFO is shown in B2 only.

**B3e. Procedure.**
1. Build and unpack (B3a). `hdfs namenode -format`, then `start-dfs.sh` and `start-yarn.sh`. Check `jps` shows NN, DN, RM and NM.
2. For L in 1, 2, 4:
   1. Set the value in `yarn-site.xml`.
   2. Restart the NM (B3b) and confirm the log line.
   3. `jmap -histo:live <nmpid> | grep IndexInformation`. Expect no row, or 0.
   4. Run the B3c job and wait for SUCCEEDED (`yarn application -list -appStates FINISHED`).
   5. Run `jmap -histo:live` and `jcmd GC.heap_info`, and record the counts.
3. **Per-job control.** With the NM at L=4, run the same job with `-Dmapreduce.reduce.shuffle.indexcache.mb=1` on the command line (`sleep -Dmapreduce.reduce.shuffle.indexcache.mb=1 -m 400 -r 400 -mt 1 -rt 1`). Restart the NM before it so the cache is empty.
4. **Accumulation control.** With the NM at L=4 and without restarting, run a second identical job, then measure. 800 entries × 9,600 = 7,680,000 B > 4 MiB, so the count should drop to the L=4 cap.
5. Stop everything: `stop-yarn.sh`, `stop-dfs.sh`, and `mapred --daemon stop historyserver` if it was started. `jps` should show no Hadoop daemon.

**B3f. Predictions.**

| Run | NM L (MiB) | IndexInformation / SpillRecord live after job | Accounted bytes |
|---|---|---|---|
| L=1 | 1 | **109** | 1,046,400 |
| L=2 | 2 | **218** | 2,092,800 |
| L=4 | 4 | **400** | 3,840,000 |
| L=10 (unset, optional) | 10 | **400** | 3,840,000 |
| Per-job `-D…=1`, NM at 4 | 4 | **400** (per-job value ignored) | 3,840,000 |
| Second job, NM at 4 | 4 | **436** (floor(4,194,304 / 9,600)) | 4,185,600 |

- Samples taken during the job never exceed the cap count by more than the number of concurrent netty workers (≤ 2 × cores) for a moment.
- Heap held by the cache's arrays ≈ entries × 9,616 B: about 1.05 MB for L=1 and 3.85 MB for L=4.
- **What would refute the claim:**
  - Counts for L=1 or L=2 near 400.
  - Counts not ordered 109 < 218 < 400.
  - The second-job run above 436.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| 109 / 218 / 400 entries for L = 1 / 2 / 4 | The NM configuration key caps the shuffle index cache's heap: claim confirmed |
| 400 entries for all L | Cap not enforced in the real NM: claim refuted |
| L=4 run shows 400 (positive control moved) and the L=1 run 109 | Change is caused by the key, not the workload |
| Per-job `-D` run shows 400 | Confirms the key is NM-scoped; per-job setting ignored |
| Per-job `-D` run shows 109 | The NM picks up the job's value, contradicting A1; amend A1 |
| Second job at L=4 shows 436 | Stale entries retained and bounded by the cap |
| Second job at L=4 shows 800 | Cap not enforced across applications: refuted |
| Count 0 after the job for every L | Shuffle not served by the cache, or `jmap` not attached to the NM: run invalid, not a reading |

**B3h. Controls.**
- The NM log line confirms the value in effect for each run.
- Restarting the NM before each L run gives an empty cache.
- The same job (same M, R) is used for every L.
- The L=4 / default runs are the positive control: the same workload with a non-binding cap.
- The per-job `-D` control rules out the job configuration as the source.
- Use `jmap -histo:live` (full GC) so dead, evicted entries are not counted.
- Check the job counters (`mapreduce shuffle` / `Shuffled Maps` = 400 × 400 = 160,000) to confirm every map was fetched.

**B4. Risks and cleanup.**
- Unit tier:
  - The index files and the 60,000-entry run are small (< 1 MB on disk, < 100 MB heap).
  - Delete `/tmp/s3u-o44` after collecting results.
  - Surefire forks exit at the end of the run; check `jps` for no leftover `surefire` JVM.
- Cluster tier:
  - About 800 short containers. Keep `yarn.nodemanager.resource.memory-mb` within host RAM (8 GB plus a 1 GB NM, the RM and HDFS daemons).
  - Map output: R × M × (small records) plus 400 × 9.6 KB of index files under `/local/s3c-o44/nm-local`. The NM deletes them at application end.
  - All data and log directories are under `/local/s3c-o44` on local disk, never shared storage.
  - Ports: default ports (9000, 9870, 8088, 8042, 13562 shuffle). Check none are in use first (`ss -ltnp`). On conflict, change `mapreduce.shuffle.port` and the web ports.
  - `jmap -histo:live` pauses the NM for a full GC (sub-second at 1 GB). Avoid running it more often than every 30 s.
  - Cleanup: `stop-yarn.sh; stop-dfs.sh; mapred --daemon stop historyserver`. Check `jps` lists no NameNode, DataNode, ResourceManager, NodeManager, JobHistoryServer, MRAppMaster or YarnChild. Then `rm -rf /local/s3c-o44`.

## C. Sources read

- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IndexCache.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/SpillRecord.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MapTask.java (lines 87, 1614-1940)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/JobConf.java (lines 123-124)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java (line 590)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/util/ConfigUtil.java (lines 41-46, 285-296)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/server/tasktracker/TTConfig.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml (searched; no entry for the key)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/test/java/org/apache/hadoop/mapred/TestIndexCache.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-shuffle/src/main/java/org/apache/hadoop/mapred/ShuffleHandler.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-shuffle/src/main/java/org/apache/hadoop/mapred/ShuffleChannelHandler.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-shuffle/src/main/java/org/apache/hadoop/mapred/ShuffleChannelHandlerContext.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/test/MapredTestDriver.java (line 92)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/mapreduce/SleepJob.java (lines 56, 250-297)
- hadoop-common-project/hadoop-common/src/site/markdown/DeprecatedProperties.md (lines 211-212)
- hadoop-project/pom.xml (lines 58, 187)
- hadoop-yarn-project/hadoop-yarn/conf/yarn-env.sh (lines 69-82)

## D. Stage-4 feedback

none yet
