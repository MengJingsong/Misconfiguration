# mapreduce.task.index.cache.limit.bytes — verification solution  <!-- file: cases/mapreduce.task.index.cache.limit.bytes-spillSingleRecord-indexCacheMemoryLimit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`MapTask.java:1775`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MapTask.java#L1775), `if (totalIndexCacheMemory >= indexCacheMemoryLimit)` in `MapTask.MapOutputBuffer.spillSingleRecord` (the oversized-record spill path). The same check in `sortAndSpill` at [`MapTask.java:1698`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MapTask.java#L1698) is the main enforcement point for normal spills; both behave identically. |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `negative`. The limit only decides whether each spill's index record (`partitions × 24` bytes) stays in the map task's heap or goes to a spill-index file on local disk *while the map is still collecting*. At the end of the map, `mergeParts` reads every paged-out index file back into the same in-heap list without checking the limit. So the most heap that spill index records ever take in the map task is `numSpills × partitions × 24` bytes, whatever the limit is. |
| Ground | The bypass is at [`MapTask.java:1892-1895`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MapTask.java#L1892-L1895): `for (int i = indexCacheList.size(); i < numSpills; ++i) indexCacheList.add(new SpillRecord(indexFileName, job));`. After it runs, `indexCacheList` holds all `numSpills` records for the rest of the merge. The limit decides when the memory is held (during collection or during the merge), not how much. It bounds the collect-phase cache, to under `limit + partitions × 24` bytes, but not the task's peak usage. |

## A. Constraint trace

**A1. The constraint.**
- Name: `mapreduce.task.index.cache.limit.bytes`. It is a configuration key, declared as `MRJobConfig.INDEX_CACHE_MEMORY_LIMIT` at [`MRJobConfig.java:325`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java#L325), and also reachable as `JobContext.INDEX_CACHE_MEMORY_LIMIT` through the `org.apache.hadoop.mapred.JobContext` interface.
- `*-default.xml` entry: none. `mapred-default.xml` has no entry for this key (grep finds no match), so nothing in the default resources overrides it.
- Unit: bytes, read as an `int`, so at most 2147483647.
- Default: 1048576 (1 MiB), from the hard-coded `MapOutputBuffer.INDEX_CACHE_MEMORY_LIMIT_DEFAULT = 1024 * 1024` (`MapTask.java:959`). It is read in `MapOutputBuffer.init` with `job.getInt(JobContext.INDEX_CACHE_MEMORY_LIMIT, INDEX_CACHE_MEMORY_LIMIT_DEFAULT)` (`MapTask.java:988-989`). The Java constant wins because no default XML value exists.
- How to set it:
  - per job, with `-Dmapreduce.task.index.cache.limit.bytes=<n>` on a `ToolRunner` job, or `JobConf.setInt`;
  - cluster-wide, in `mapred-site.xml` on the submitting client.
- Restart: none needed. The value is read once per map task attempt when its `MapOutputBuffer` is initialized, so a new job picks up a new value.
- Validation: none. A value of 0 or below makes the check always true, so every spill index goes to disk. That is the behaviour `TestMiniMRWithDFSWithDistinctUsers.testMultipleSpills` relies on (`TestMiniMRWithDFSWithDistinctUsers.java:140`).
- Reader: the MapReduce map task JVM (`YarnChild` running a `MapTask` that has reducers, with the default `MapOutputBuffer` collector). No daemon reads it.
- Other sources of the limit-side quantity:
  - The usage side is `partitions × MAP_OUTPUT_INDEX_RECORD_LENGTH`, where `MAP_OUTPUT_INDEX_RECORD_LENGTH = 24` (`MapTask.java:87`) and `partitions = job.getNumReduceTasks()` (`MapTask.java:980`), so it scales with `mapreduce.job.reduces`.
  - The number of spills is driven by `mapreduce.task.io.sort.mb`, `mapreduce.map.sort.spill.percent` and the record sizes.

**A2. What it caps.**
- Resource: map-task JVM heap held by `SpillRecord` objects in `MapOutputBuffer.indexCacheList` (`MapTask.java:954-955`). Each `SpillRecord` wraps a heap `ByteBuffer` of `partitions × 24` bytes (`SpillRecord.java:50-54`).
- Trade-off: what is not cached goes to local disk as one spill-index file per spill, `partitions × 24 + 8` bytes each (8-byte CRC trailer, `SpillRecord.java:130-142`). The files go under the task's local directories (`mapreduce.cluster.local.dir`; on YARN, the NodeManager local dirs, named `<attempt>_spill_<n>.out.index`, `YarnOutputFiles.java:45-47`).
- Compared quantity: the running sum `totalIndexCacheMemory` (`MapTask.java:956`), an `int` that grows by `spillRec.size() * 24` for each cached spill (`MapTask.java:1784-1785`, `1707-1708`).

**A3. Mechanism.**
1. `init` reads the limit (`MapTask.java:988-989`) and the partition count (`MapTask.java:980`).
2. **Entering the target path.**
   - A record whose serialized size cannot fit in the sort buffer when no other record is buffered makes `BlockingBuffer.write` throw `MapBufferTooSmallException` (`MapTask.java:1441-1450`).
   - `collect` catches the exception, logs `Record too large for in-memory buffer` and calls `spillSingleRecord` (`MapTask.java:1206-1208`).
   - `spillSingleRecord` writes a whole spill file containing just that record, with one `IFile` segment per partition (`MapTask.java:1725-1772`).
   - It builds a `SpillRecord(partitions)` (`MapTask.java:1732`).
3. **The check.** [`MapTask.java:1775`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MapTask.java#L1775) `if (totalIndexCacheMemory >= indexCacheMemoryLimit)`:
   - **true:** the record is written to a spill-index file (`MapTask.java:1777-1781`) and the in-heap object becomes garbage.
   - **false:** the record is appended to `indexCacheList` and `totalIndexCacheMemory += partitions × 24` (`MapTask.java:1783-1785`).
   - Then `incrementNumSpills()` (`MapTask.java:1787`, `2049-2056`).
   - The check runs *before* the add, so the cache can overshoot the limit by up to one record: the final value is `< limit + partitions × 24`.
   - The normal spill path `sortAndSpill` has the same check at [`MapTask.java:1698`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MapTask.java#L1698), with the add at `1706-1708`.
4. **End of map.**
   - `flush()` (`MapTask.java:1485`) waits for the spill thread, spills any buffered remainder, releases the sort buffer (`kvbuffer = null`, `MapTask.java:1537`) and calls `mergeParts()` (`MapTask.java:1538`).
   - **Bypass:** with more than one spill, `mergeParts` reads every spill-index file that was paged out (`indexCacheList.size() .. numSpills-1`) back into `indexCacheList` as new `SpillRecord(path, job)` objects (`MapTask.java:1892-1895`), without looking at the limit or `totalIndexCacheMemory`.
   - The list is then read per partition for the whole merge (`MapTask.java:1953`) and keeps all `numSpills` records until the task ends.
   - One more `SpillRecord(partitions)` is allocated for the final output index.
   - With exactly one spill, the cached record (if any) is written out, or the index file is renamed (`MapTask.java:1873-1888`).
5. **Net effect.**
   - During collection: in-heap index bytes `< limit + partitions × 24`.
   - During the merge: in-heap index bytes `= numSpills × partitions × 24` (plus one final record) for any limit.
   - Disk side: the number of spill-index files is `numSpills − cachedCount`.
   - No exception, log or counter reports either outcome. `spillSingleRecord` does not even log `Finished spill` (compare `MapTask.java:1710`).
6. **Overshoot and bypass routes.**
   - the one-record overshoot (item 3);
   - the merge-phase reload (item 4);
   - `totalIndexCacheMemory` is an `int` and can wrap for very large `partitions × spills`, which is not reachable at practical sizes;
   - limit values of 0 or below simply disable caching.

**A4. Other consumers.**
- Map-task heap: the sort buffer `kvbuffer` (`mapreduce.task.io.sort.mb`, `MapTask.java:1009-1011`), which is released before the merge.
- Merge buffers and readers (`Merger`, factor `mapreduce.task.io.sort.factor`).
- Combiner state, and the user's mapper.
- Local disk: spill files, intermediate merge files, the final `file.out`/`file.out.index`.
- On the NodeManager side, the shuffle's separate `IndexCache` (`mapreduce.reduce.shuffle.indexcache.mb`, default 10 MB, `IndexCache.java:46`) caches final map-output index files. It is a different key and a different process.
- `mapreduce.task.spill.files.count.limit` (`MapTask.java:990-999`, `2049-2056`) caps the number of spills, which indirectly caps the merge-phase index memory. Its default is unlimited (-1).

**A5. Evidence beyond the source.**
- `TestMiniMRWithDFSWithDistinctUsers.testMultipleSpills` (`hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/mapred/TestMiniMRWithDFSWithDistinctUsers.java:127-150`): a regression test for MAPREDUCE-2327 (https://issues.apache.org/jira/browse/MAPREDUCE-2327). It sets the limit to 0 so that "the spill records don't fit in index cache" and checks only that the job succeeds.
- `TestMapTask` (`hadoop-mapreduce-client-core/src/test/java/org/apache/hadoop/mapred/TestMapTask.java`): the harness pattern for driving `MapOutputBuffer` directly.
- The key is not documented in `mapred-default.xml` or in `MapReduceTutorial.md`.

## B. Verification solution

**B1. Claim under test.** In a map task with `numSpills > 1`, the most heap held by spill index records (`SpillRecord` objects reachable from `MapOutputBuffer.indexCacheList`) is `numSpills × partitions × 24` bytes, whatever the value of `mapreduce.task.index.cache.limit.bytes`. That most is reached during `mergeParts`. The limit only bounds the collect phase, to `< limit + partitions × 24` bytes, and moves `numSpills − cached` records to spill-index files on disk. The claim is wrong if the peak count or bytes held during the merge follows the limit, that is, if it is lower for a small limit than for a large one.

### B2. Unit tier

**B2a. Environment and build.**
- Toolchain: Linux, JDK 8, Maven 3.3+.
- Copy the source to local disk, then build:
  ```
  rsync -a <pinned source>/ /local/hadoop-3.4.2-s4/
  cd /local/hadoop-3.4.2-s4
  mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core -am install -DskipTests
  ```
- Add one test class, `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/test/java/org/apache/hadoop/mapred/TestIndexCacheLimitProbe.java`. It must be in package `org.apache.hadoop.mapred`, because `MapOutputBuffer.indexCacheList` and `numSpills` are package-private.
- Run it:
  ```
  mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core test -Dtest=TestIndexCacheLimitProbe
  ```
- The default surefire heap is enough (peak is about 1 MB sort buffer plus about 1.5 MB of index records and a 1.2 MB record).
- `test.build.data` points to `target/`, on local disk.

**B2b. Knobs.** Each value runs as its own `@Test` with a fresh `MapOutputBuffer`; the limit is set with `JobConf.setInt`.

| `mapreduce.task.index.cache.limit.bytes` | Why |
|---|---|
| 0 | caching off |
| 100000 | a few records |
| 1048576 | default |
| 2147483647 | everything cached |

Fixed: `partitions = 1000` (`conf.setNumReduceTasks(1000)`, so 24,000 B per `SpillRecord`) and `mapreduce.task.io.sort.mb = 1`.

**B2c. Workload.**
- Collect N = 60 records through `mob.collect(key, value, i % 1000)`, then call `mob.flush()`.
- Key/value class: `BytesWritable`. Key 10 bytes; value 1,200,000 bytes.
- The record serializes to 1,200,004 bytes of value, more than the 1 MiB `kvbuffer` (1,048,576 bytes, minus alignment), so every record takes the `MapBufferTooSmallException` → `spillSingleRecord` path (the target line). That gives exactly N = 60 spills.
- Cached count for limit L: records are added while `24,000·k < L`, so `cached = min(60, ceil(L / 24,000))`, and `cached = 0` for L = 0. That gives 0, 5, 44, 60.
- Spill data on disk: about 60 × 1.2 MB = 72 MB, plus the same again for the final output.

**B2d. Observables and instruments.** After each `collect`, and after `flush`, read:

| Observable | How it is read |
|---|---|
| `totalIndexCacheMemory` | reflection (`getDeclaredField("totalIndexCacheMemory")`, `setAccessible(true)`) |
| `mob.indexCacheList.size()` | direct field access |
| `mob.numSpills` | direct field access |
| spill-index files on disk | count of files matching `spill*.out.index` under `<LOCAL_DIR>/output/` |
| in-heap index bytes | Σ `spillRecord.size() × 24` over `indexCacheList` |

- Record the maximum of each value during collection, and its value after `flush` (the merge phase).
- Also count the `Record too large for in-memory buffer` log lines, or call `getCounter` on a real `Counter` for `MAP_OUTPUT_RECORDS`, to confirm N.
- Not observable here: the GC'd paged-out `SpillRecord` objects themselves. The bytes are computed from list contents, which are the strongly reachable set.

**B2e. Procedure.**
1. Write `TestIndexCacheLimitProbe` copying the setup of `TestMapTask.testShufflePermissions` (`TestMapTask.java:73-103`), plus the settings below:
   - inherited from that test: `MRConfig.LOCAL_DIR` = the test dir, `MROutputFiles`, and a mocked `MapTask` returning `getMapOutputFile`, `getTaskID` and `getSortPhase(new Progress())`;
   - a mocked `TaskReporter` whose `getCounter(any(TaskCounter.class))` returns `new Counter()`;
   - `conf.setNumReduceTasks(1000)`;
   - `conf.setMapOutputKeyClass(BytesWritable.class)` and `conf.setMapOutputValueClass(BytesWritable.class)`;
   - `conf.setInt(MRJobConfig.IO_SORT_MB, 1)`;
   - `conf.setInt(MRJobConfig.INDEX_CACHE_MEMORY_LIMIT, L)`.
2. `mob.init(ctx)`.
3. For i in 0..59: `mob.collect(new BytesWritable(10 random bytes), new BytesWritable(new byte[1_200_000]), i % 1000)`, then sample the observables (B2d) and print one line: `i, numSpills, listSize, totalIndexCacheMemory, indexFilesOnDisk`.
4. `mob.flush()`, then sample again and print `after-merge listSize, bytes`.
5. `mob.close()`, then delete the test dir. Repeat for each L (one method per L).
6. Assert, so that a failure is visible:
   - `numSpills == 60`;
   - collect-phase `listSize == expectedCached(L)` and `indexFiles == 60 − expectedCached(L)`;
   - after-merge `listSize == 60` for every L.

**B2f. Predictions.**

| L | collect: cached / totalIndexCacheMemory | collect: index files | after merge: listSize / bytes |
|---|---|---|---|
| 0 | 0 / 0 | 60 | 60 / 1,440,000 |
| 100000 | 5 / 120,000 | 55 | 60 / 1,440,000 |
| 1048576 | 44 / 1,056,000 | 16 | 60 / 1,440,000 |
| 2147483647 | 60 / 1,440,000 | 0 | 60 / 1,440,000 |

For every L > 0, the collect-phase `totalIndexCacheMemory` stays below `L + 24,000`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Collect-phase cached count follows L as predicted, and after-merge `listSize` = 60 for every L | claim confirmed: the limit binds only during collection, and the peak is independent of L |
| After-merge `listSize` or bytes is smaller for small L (for example, stays at cached count) | claim refuted: usage follows the constraint |
| Collect-phase cached count does not follow L (for example 60 for L = 0) | the mechanism is not as traced; the limit does not even bind in the collect phase (also refutes A3) |
| `numSpills` ≠ 60, or no `Record too large` lines | the workload did not reach the target path; not confirmed, so re-size the record |
| L = 2147483647 and L = 0 give the same collect-phase cached count | the control did not move; not confirmed |

**B2h. Controls.**
- Positive control (a cap that is known to bind): the collect-phase cached count and on-disk index file count must move with L. This shows the knob is read and the instrument sees it.
- Second control: rerun the default L with `partitions = 2000`. After-merge bytes must double (2,880,000), so the merge-phase reading tracks `numSpills × partitions × 24` and not the limit.
- Optional: run the normal `sortAndSpill` path with 100-byte records, `mapreduce.map.sort.spill.percent=0.05` and N large enough for more than 20 spills. Read `numSpills` and compare against `min(numSpills, ceil(L/24,000))`. The relation should be the same.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host, pseudo-distributed.
- Build: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true` in a local copy, then unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/local/s4/hadoop-base`.
- Daemons: NameNode, DataNode, ResourceManager, NodeManager. The JobHistory server is optional.
- `HADOOP_HEAPSIZE_MAX=1g`. `HADOOP_LOG_DIR=/local/s4/logs`.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=/local/s4/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=/local/s4/nn`, `dfs.datanode.data.dir=/local/s4/dn`.
- `yarn-site.xml`:
  - `yarn.nodemanager.aux-services=mapreduce_shuffle`;
  - `yarn.nodemanager.local-dirs=/local/s4/nm-local`;
  - `yarn.nodemanager.log-dirs=/local/s4/nm-logs`;
  - `yarn.nodemanager.resource.memory-mb=8192`;
  - `yarn.nodemanager.delete.debug-delay-sec=600`, so the map's local output and spill-index files survive long enough to count;
  - `yarn.nodemanager.vmem-check-enabled=false`.
- `mapred-site.xml`: `mapreduce.framework.name=yarn`, `mapreduce.map.memory.mb=1024`, `mapreduce.map.java.opts=-Xmx820m`.
- At least 2 GB free local disk.

**B3b. Knobs.** `mapreduce.task.index.cache.limit.bytes`, passed per job with `-D` (no restart): 0, 1048576 (default), 2400000, 2147483647. Fixed:

| Setting | Value | Effect |
|---|---|---|
| `mapreduce.job.reduces` (via `sort -r`) | 2000 | 48,000 B per `SpillRecord` |
| `mapreduce.task.io.sort.mb` | 1 | — |
| `mapreduce.task.io.sort.factor` | 100 | one merge pass per partition |
| `mapreduce.job.reduce.slowstart.completedmaps` | 1.0 | no reducers start before the map completes |

**B3c. Workload.**
1. Generate the input once:
   ```
   hadoop jar hadoop-mapreduce-examples-3.4.2.jar randomwriter \
     -Dmapreduce.randomwriter.totalbytes=120000000 \
     -Dmapreduce.randomwriter.bytespermap=120000000 \
     -Dmapreduce.randomwriter.minkey=10 -Dmapreduce.randomwriter.maxkey=10 \
     -Dmapreduce.randomwriter.minvalue=1200000 -Dmapreduce.randomwriter.maxvalue=1200000 \
     /s4/in
   ```
   - This is one map (`RandomWriter.java:247-261`), map-only (`RandomWriter.java:278`).
   - The loop writes records until `numBytesToWrite ≤ 0` (`RandomWriter.java:190-200`), which gives `ceil(120,000,000 / 1,200,010) = 100` records.
   - Output is one SequenceFile of about 120 MB, under one 128 MB block, so one split.
2. Per knob value, run:
   ```
   hadoop jar hadoop-mapreduce-examples-3.4.2.jar sort \
     -Dmapreduce.task.io.sort.mb=1 \
     -Dmapreduce.task.io.sort.factor=100 \
     -Dmapreduce.job.reduce.slowstart.completedmaps=1.0 \
     -Dmapreduce.task.index.cache.limit.bytes=<L> \
     -r 2000 /s4/in /s4/out-<L>
   ```
   - Mapper is identity, key/value `BytesWritable` (`Sort.java:125-142`).
   - Each 1.2 MB record exceeds the 1 MiB sort buffer, so the map makes exactly 100 spills via `spillSingleRecord`.
   - In-heap index at the merge: 100 × 2000 × 24 = 4.8 MB.
   - Once the map attempt is SUCCEEDED, kill the job (`mapred job -kill <jobId>`) so the 2000 reducers need not run.
   - Duration: a few minutes per run, mostly the merge over 2000 partitions × 100 segments.

**B3d. Observables and instruments.**
- **Heap.** Find the map JVM with `jps -lm | grep YarnChild | grep '_m_000000'`. Every 2 s, sample `jcmd <pid> GC.class_histogram | grep ' org.apache.hadoop.mapred.SpillRecord$'`: the instance count × (48,000 B array + about 100 B of object overhead) is the in-heap index bytes. The histogram forces a full GC, so it shows reachable objects only.
- **Phase marker.** Tail the attempt's `syslog` under `/local/s4/nm-logs/<app>/<container>/`. Mark the merge phase from `Starting flush of map output` (`MapTask.java:1487`) and `Merging 100 sorted segments` (`Merger.java:607`). Count `Record too large for in-memory buffer` lines (expected 100).
- **Disk.** Every 2 s, run `find /local/s4/nm-local -name '*_spill_*.out.index' | wc -l` and `du -sb` on the attempt's `output/` directory.
- **Optional.** Map task counters `SPILLED_RECORDS` and `MAP_OUTPUT_RECORDS` from `mapred job -status`, or the job history.
- **Not directly observable:** which `SpillRecord` instances belong to `indexCacheList` and which are the transient per-spill or final one. Count up to 2 extra as noise.

**B3e. Procedure.**
1. Format the NameNode, then `start-dfs.sh` and `start-yarn.sh`. Check `jps`.
2. Generate the input (B3c step 1). Check `hdfs dfs -ls /s4/in` shows one part file of about 120 MB.
3. For each L in [0, 1048576, 2400000, 2147483647]:
   1. Submit the sort job in the background.
   2. Wait for the `YarnChild` of `_m_000000`, then start the histogram and `find` sampler loops (2 s), writing to `/local/s4/run-<L>.tsv` with a timestamp.
   3. When the attempt syslog shows the task done (or `mapred job -status` shows the map at 100%), stop the samplers, run `mapred job -kill`, and run `hdfs dfs -rm -r -skipTrash /s4/out-<L>`.
   4. Record the collect-phase maximum and the merge-phase maximum of the `SpillRecord` count, and the maximum count of index files.
4. Positive and sensitivity control: rerun L = 1048576 with `-r 1000`. Expected index bytes are half.
5. Optional amplified run: L = 1048576, `-r 10000`, `mapreduce.map.java.opts=-Xmx128m`. 100 × 10000 × 24 = 24 MB at the merge, against a 1 MiB limit. This shows the overshoot can be about 23 times the limit in a small heap.
6. Clean up (B4).

**B3f. Predictions.**

| L | collect-phase max SpillRecord count (bytes) | max spill-index files | merge-phase max count (bytes) |
|---|---|---|---|
| 0 | ≤ 2, transient (≈0) | 100 | 100–102 (≈4.8 MB) |
| 1048576 | 22 (+≤2) (1,056,000) | 78 | 100–102 (≈4.8 MB) |
| 2400000 | 50 (+≤2) (2,400,000) | 50 | 100–102 (≈4.8 MB) |
| 2147483647 | 100 (+≤2) (4,800,000) | 0 | 100–102 (≈4.8 MB) |

Spill-index file size: 48,008 B each.

Relation: the merge-phase maximum is the same, within ±2 instances, for all L. The collect-phase maximum rises with L as `min(100, ceil(L/48,000))`. With `-r 1000`, the merge-phase bytes halve to about 2.4 MB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Merge-phase SpillRecord count ≈100 for all L, and collect-phase count follows `ceil(L/48,000)` | claim confirmed: the limit caps only the collect-phase cache; peak index heap = numSpills × partitions × 24 |
| Merge-phase count follows L (for example ≈22 for the default, ≈0 for L = 0) | claim refuted: usage follows the constraint |
| Collect-phase count does not follow L (positive control did not move) | not confirmed; check that `-D` reached the job (job conf in the history or the AM UI) and that 100 spills happened |
| Fewer than 100 `Record too large` lines, or more than one map | the workload missed the target path; not confirmed |
| `-r 1000` does not halve the merge-phase bytes | the instrument or attribution is wrong; not confirmed |

**B3h. Controls.**
- The collect-phase reading is the positive control: the same workload moves in-heap index usage where the cap binds.
- The `-r` change separates "follows partitions × spills" from "follows the limit".
- L = 0 and L = max bracket the knob range.
- The spill-index file count on disk independently confirms which branch of the check was taken.
- Identical input across runs: the same `/s4/in`, and records of fixed size.

**B4. Risks and cleanup.**
- Disk: about 120 MB of HDFS input; about 240 MB local per run (spills plus final output); index files up to about 4.8 MB. Everything goes under `/local/s4`, never shared storage.
- Ports: the defaults (9000, 9870, 8088, 8042 and others); check nothing else holds them.
- Cluster cleanup:
  - `mapred job -kill` any job still running;
  - `stop-yarn.sh`, `stop-dfs.sh`, and `mapred --daemon stop historyserver` if it was started;
  - `jps` must show no `NameNode`, `DataNode`, `ResourceManager`, `NodeManager` or `YarnChild`;
  - `rm -rf /local/s4/{tmp,nn,dn,nm-local,nm-logs}` when done.
- Unit tier cleanup: `TestIndexCacheLimitProbe` deletes its test dir in `@After`. Remove the local source copy when done.
- `jcmd` full GCs slow the map but do not change what is reachable.

## C. Sources read

- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MapTask.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/SpillRecord.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MROutputFiles.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IndexCache.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/Merger.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/site/markdown/MapReduceTutorial.md
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/test/java/org/apache/hadoop/mapred/TestMapTask.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/mapred/TestMiniMRWithDFSWithDistinctUsers.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/main/java/org/apache/hadoop/mapred/YarnOutputFiles.java
- hadoop-mapreduce-project/hadoop-mapreduce-examples/src/main/java/org/apache/hadoop/examples/RandomWriter.java
- hadoop-mapreduce-project/hadoop-mapreduce-examples/src/main/java/org/apache/hadoop/examples/Sort.java
- hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/resources/yarn-default.xml
- https://issues.apache.org/jira/browse/MAPREDUCE-2327 (cited from the test comment only)

## D. Stage-4 feedback

none yet
