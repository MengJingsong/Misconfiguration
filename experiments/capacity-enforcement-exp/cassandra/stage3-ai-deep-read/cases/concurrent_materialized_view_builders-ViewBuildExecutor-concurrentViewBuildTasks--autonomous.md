# concurrent_materialized_view_builders — verification solution  <!-- file: cases/concurrent_materialized_view_builders-ViewBuildExecutor-concurrentViewBuildTasks--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the place the value takes effect (there is no if statement on it; it is the pool size of the view-build executor), **linked**: [`CompactionManager.java:2127`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L2127) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code (stage-3 autonomous subagent; CLI version not shown to the agent), 2026-11-26 |
| Estimate | `negative`. The entry only sets how many `ViewBuilderTask`s run at once on the `ViewBuildExecutor`; each running task holds a small, transient working set (key iterators over memory-mapped index files plus one partition read streamed row by row), so heap, off-heap and disk do not follow the entry in any significant amount. |
| Ground | It bounds CPU/IO concurrency, not a memory- or disk-significant object. Per running task the retained state is O(#base SSTables) small objects and at most a few pooled read buffers (well under 1 MiB per task for the workloads below); the memory and disk the view build actually consumes (view memtables, commit log, local batchlog, flushed view SSTables) are capped by other entries (`memtable_heap_space`, `commitlog_total_space`, ...) or are fixed by the view's data size, independent of this entry. The number of tasks is in addition capped per view by `NUM_TASKS = 4 × availableProcessors` ([ViewBuilder.java:64](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/view/ViewBuilder.java#L64)). |

## A. Constraint trace

**A1. The constraint.** `concurrent_materialized_view_builders`; configuration entry (cassandra.yaml key, `Config` field). Declared at
[`Config.java:346`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L346)
as `public volatile int concurrent_materialized_view_builders = 1;`. Unit: number of threads (view-build tasks running
concurrently). Default `1` (hard-coded field initializer; `conf/cassandra.yaml:1242` and `conf/cassandra_latest.yaml:1226`
also set `1`). Validation: must be `> 0`, else startup fails (`DatabaseDescriptor.java:787-788`). Set by:
- yaml key `concurrent_materialized_view_builders` (read once at startup when `CompactionManager` builds the executor, `CompactionManager.java:162`, `:2127`);
- at runtime, no restart: JMX `org.apache.cassandra.db:type=StorageService` attribute `ConcurrentViewBuilders`
  (`StorageService.java:2031-2042`, `StorageServiceMBean.java:841-842`) or `nodetool setconcurrentviewbuilders <n>` /
  `getconcurrentviewbuilders` (`tools/nodetool/SetConcurrentViewBuilders.java:37`, `NodeProbe.java:1446-1453`). The setter
  writes the Config field (`DatabaseDescriptor.java:2539-2541`) and resizes the pool (`CompactionManager.java:2248-2266`).
- also, bypassing the Config field: `CompactionManagerMBean` `CoreViewBuildThreads` / `MaximumViewBuildThreads`
  (`CompactionManager.java:2361-2382`).

**A2. What it caps.** Nothing memory or disk directly. It is the core and maximum thread count of the
`ViewBuildExecutor` thread pool (queue limit `Integer.MAX_VALUE`, `CompactionManager.java:2127`), i.e. the number of
`ViewBuilderTask.call()` executions in progress at once. The "operand" is therefore the count of concurrently running
view-build tasks (visible as `View build` entries in `CompactionManager.active`, `ViewBuilderTask.java:207,213`,
`OperationType.VIEW_BUILD`), and, per task, the working set it holds. The question for memory/disk is whether that
working set is significant.

**A3. Mechanism.** Step by step:
1. `DatabaseDescriptor.getConcurrentViewBuilders()` returns the field (`DatabaseDescriptor.java:2534-2536`).
2. **The place it takes effect:** [`CompactionManager.java:2127`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L2127)
   `super(DatabaseDescriptor.getConcurrentViewBuilders(), "ViewBuildExecutor", Integer.MAX_VALUE);` → `CompactionExecutor`
   → `executorFactory().withJmxInternal().configurePooled(name, threads)...withQueueLimit(queueSize)` (`CompactionManager.java:2032-2039`).
   Runtime resize: `adjustCoreSize` (`CompactionManager.java:2252-2266`) sets core and max pool size.
   There is no comparison against the value anywhere; the pool simply runs at most N tasks and queues the rest (queue unbounded).
3. Producer: creating a view (or startup with an unbuilt view) calls `View.build()` → `new ViewBuilder(...).start()`
   (`View.java:213-214`; `ViewManager.java:134,182`). `ViewBuilder.start()` flushes the base table (`ViewBuilder.java:98`),
   then `build()` splits the node's local ranges into `NUM_TASKS = 4 × availableProcessors()` sub-ranges
   (`ViewBuilder.java:64`, `:156-160`) and submits one `ViewBuilderTask` per sub-range at once
   (`ViewBuilder.java:164-173` → `CompactionManager.submitViewBuilder`, `CompactionManager.java:1986-2003`).
   So effective concurrency per view = min(N, 4·P); with several views building, tasks of all views share the N threads.
4. What a running task holds (`ViewBuilderTask.call()`, `ViewBuilderTask.java:120-174`):
   - `baseCfs.selectAndReference(...)` (`:142`): `Refs` on every canonical base SSTable whose bounds intersect the range.
     With a random partitioner every SSTable spans the ring, so every task references every base SSTable. A reference
     keeps an SSTable (and its files) alive until the task ends — disk retention of compacted-away base SSTables.
   - `new ReducingKeyIterator(sstables)` (`:144`; `ReducingKeyIterator.java:41-55`): one `KeyIterator` per SSTable
     (`SSTableReader.java:947-950` → `keyReader()`, `BigTableReader.java:153-156`). With the default
     `disk_access_mode: mmap_index_only` (`Config.java:122`) the index file is memory-mapped and shared, so each key reader
     holds only small objects, no private buffer.
   - Per key, `buildKey` (`ViewBuilderTask.java:95-119`): a local `SinglePartitionReadCommand` (`:110`) whose data-file readers
     take buffers from the chunk-cache `BufferPool` (`BufferManagingRebufferer`, `BufferManagingRebufferer.java:45`; pool limit
     `file_cache_size`, `BufferPools.java:38-39`); `TableViews.generateViewUpdates(..., separateUpdates=true)` emits view
     mutations one base row at a time (`TableViews.java:285-330`); each is applied by `StorageProxy.mutateMV`
     (`ViewBuilderTask.java:117`, `StorageProxy.java:1010-1113`): locally and synchronously (`mutation.apply`, `:1072`) when the
     paired view replica is this node; otherwise stored in the local batchlog (`:1102`) and sent asynchronously without
     waiting (`:1106`).
   - Checkpoint every 1000 keys into `system.view_builds_in_progress` (`ViewBuilderTask.java:70`, `:163-164`).
5. Outcome "at the limit": the (N+1)-th task waits in the executor queue holding only its small `ViewBuilderTask` object
   (no refs, no iterators; those are taken inside `call()`). Nothing is rejected, nothing blocks the producer.
6. Bypass/overshoot: `CoreViewBuildThreads`/`MaximumViewBuildThreads` JMX change the pool without the Config field
   (`CompactionManager.java:2367-2382`). N larger than 4·P × (views building) has no further effect.

**A4. Other consumers.** Memory/disk that a view build does consume, outside this entry's control:
- view memtables (and batchlog memtable): `memtable_heap_space` / `memtable_offheap_space`, `memtable_allocation_type`
  (`conf/cassandra.yaml:797,825`); writes block on memtable allocation when full;
- commit log for view mutations (`mutateMV(..., writeCommitLog=true)`): `commitlog_total_space` (`conf/cassandra.yaml:883`);
- flushed and compacted view SSTables: final size fixed by the view's content; transient compaction space by
  `concurrent_compactors` and compaction strategy;
- read buffers: chunk-cache `BufferPool`, capped by `file_cache_size` (`conf/cassandra.yaml:753`), overflow by
  `buffer_pool_use_heap_if_exhausted`;
- remote-paired view mutations (multi-node only): internode outbound queue limits and `write_request_timeout` (`conf/cassandra.yaml:1330`).

**A5. Evidence beyond the source.**
- `NEWS.txt:639-642` (4.0 notes): "The initial build of materialized views can be parallelized. The number of concurrent
  builder threads is specified by ... `concurrent_materialized_view_builders`" — CASSANDRA-12245
  (https://issues.apache.org/jira/browse/CASSANDRA-12245, cited, not fetched).
- `doc/modules/cassandra/pages/developing/cql/mvs.adoc:45-52`: same; "materialized views are built in a single thread" by default.
- `conf/cassandra.yaml:1241`: "Number of simultaneous materialized view builder tasks to allow."
- Tests: `test/unit/org/apache/cassandra/cql3/ViewTest.java:427-473` (sets the value via `CompactionManager.setConcurrentViewBuilders`),
  `test/unit/org/apache/cassandra/db/view/ViewBuilderTaskTest.java` (drives a `ViewBuilderTask` directly).
None describes it as a memory or disk limit.

## B. Verification solution

**B1. Claim under test.** Raising `concurrent_materialized_view_builders` from 1 to 16 raises the number of view-build tasks
running at once to min(N, 4·P) but does **not** raise the node's memory (post-GC heap, chunk-cache buffer pool, RSS) or disk
(peak and final data-directory size) beyond a small, bounded amount: less than 64 MiB and less than 5% of the N=1 value for
memory, less than 10% for peak disk. The claim is wrong if any of these grows roughly in proportion to N.

### B2. Unit tier

**B2a. Environment and build.** One Linux host, JDK 11, Ant. Copy the tree to local disk and build there:
```
export W=/local/s3-cmvb            # any local disk with >= 10 GiB free; not shared storage
mkdir -p $W && rsync -a <pinned-source-copy>/ $W/cassandra-5.0.9/
cd $W/cassandra-5.0.9 && ant jar build-test
```
New test file only in the copy: `$W/cassandra-5.0.9/test/unit/org/apache/cassandra/db/view/ViewBuildConcurrencyMemoryTest.java`,
`extends ViewAbstractTest` (in package `org.apache.cassandra.cql3`; import it), which uses `test/conf/cassandra.yaml`
(`materialized_views_enabled: true`, line 53). Unit test JVM gets the build's default test heap; record `-Xmx` from the
`testsome` jvmargs and `Runtime.getRuntime().availableProcessors()` (= P) in the output.

**B2b. Knobs.** `N ∈ {1, 4, 16}` set in-test with `CompactionManager.instance.setConcurrentViewBuilders(N)` (the JMX/nodetool
path, `CompactionManager.java:2248`) before creating the view. Why: 1 is the default; 4 and 16 multiply concurrency by
4× and 16× and, if P ≥ 4, stay ≤ NUM_TASKS = 4·P. If P < 4, replace 16 by 4·P and note it. Base-SSTable count S = 20 fixed.

**B2c. Workload.** Table `k int, c int, v text, PRIMARY KEY(k, c)`; `cfs.disableAutoCompaction()`; insert 20 batches of
25 000 rows (`k` = row id, `c` = 0, `v` = 100-char string from `k`), `Util.flush(cfs)` after each batch → S = 20 SSTables,
500 000 partitions. Then `createViewAsync("CREATE MATERIALIZED VIEW %s AS SELECT * FROM %s WHERE v IS NOT NULL AND k IS NOT NULL
AND c IS NOT NULL PRIMARY KEY (v, k, c)")`. The build creates 4·P tasks (≥ 16 for P ≥ 4), so a pool of N threads is fully
occupied while the build lasts: the "limit" N is reached as soon as the build starts. Per task predicted working set:
S KeyIterators (a few hundred bytes each) + ≤ S read buffers of ≤ 64 KiB only while a key is read (bloom filters
make it ≈1 SSTable per key here since each partition is in exactly one SSTable) → ≤ ~200 KiB per task.
After each N: `waitForViewBuild(view)`, drop the view, `System.gc()`, next N (new view name).

**B2d. Observables and instruments.** In a sampler thread started before `createViewAsync`, every 5 ms until built:
- `a` = number of `CompactionManager.instance.active.getCompactions()` entries whose `getCompactionInfo().getTaskType() == OperationType.VIEW_BUILD`; keep max.
- `BufferPools.forChunkCache().usedSizeInBytes()`; keep max (off-heap pooled read buffers).
- The first time `a == min(N, 4P)`: call `System.gc()` then `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed()` (`H_N`),
  and invoke the `com.sun.management:type=DiagnosticCommand` MBean operation `gcClassHistogram` (args `new String[]{"-all"}` as
  `Object[]{String[]}`, signature `String[].class.getName()`); parse rows for `org.apache.cassandra.io.sstable.KeyIterator`,
  `org.apache.cassandra.io.sstable.ReducingKeyIterator`, `org.apache.cassandra.db.view.ViewBuilderTask`,
  `org.apache.cassandra.io.util.RandomAccessReader` (instances and bytes).
- Baseline `H_base` = same post-GC heap read just before `createViewAsync`.
- Build wall time (createViewAsync → isViewBuilt).
Print one line per N: `N a_max KI_inst KI_bytes RKI_inst VBT_inst RAR_inst RAR_bytes H_N-H_base pool_max build_ms`.
Cannot be observed directly: retained size of task-local iterators (locals of `call()`), hence the histogram counts.

**B2e. Procedure.**
1. Write the test as above (one `@Test` method looping N over {1,4,16}, plus the sensitivity control in B2h).
2. `cd $W/cassandra-5.0.9 && ant testsome -Dtest.name=org.apache.cassandra.db.view.ViewBuildConcurrencyMemoryTest`
3. Read the printed lines from `build/test/output/TEST-org.apache.cassandra.db.view.ViewBuildConcurrencyMemoryTest.xml` (stdout section).
4. Repeat the run 3 times; use the median per N.

**B2f. Predictions.** (P ≥ 4)
| N | a_max | KeyIterator instances at sample | ΔH = H_N − H_base | pool_max | build time |
|---|---|---|---|---|---|
| 1 | 1 | ≈ 1·S = 20 | baseline value D1 (view memtable dominated) | ≤ 1 MiB | T1 |
| 4 | 4 | ≈ 80 | D1 ± 32 MiB | ≤ 4 MiB | < T1 (≈ T1/2–T1/4) |
| 16 | 16 | ≈ 320 | D1 ± 32 MiB | ≤ 16 MiB | ≤ T4 |
KeyIterator+ReducingKeyIterator+RandomAccessReader shallow bytes in total < 1 MiB at N=16.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| a_max = N, KeyIterator count ≈ a_max·S, ΔH within ±32 MiB of N=1 and pool_max ≤ N MiB, while the sensitivity control (B2h) reads +32 MiB | claim confirmed: the operand (concurrent tasks) follows N, memory does not materially |
| ΔH(16) − ΔH(1) ≥ 64 MiB and grows with N roughly linearly (ΔH(4) between) | claim refuted: per-task working set is memory-significant; record per-task bytes |
| pool_max grows ≥ 1 MiB per task and reaches `file_cache_size` capacity | refuted for off-heap: read buffers scale with N |
| a_max < N (e.g. stays 1) | not confirmed: the knob was not applied or the build was too short; enlarge data or check pool size via `getCoreViewBuildThreads()` |
| sensitivity control does not read ~+32 MiB | not confirmed: instrument cannot see differences of the claimed size |

**B2h. Controls.**
- Mechanism control: a_max and KeyIterator count must follow N (proves the knob is live and the histogram sees per-task state).
- Sensitivity (positive) control: after the N=1 sample, allocate and keep a `byte[32 << 20]` in a static field, `System.gc()`,
  read heap: must show +32 MiB (±4 MiB); release it. Shows a 32 MiB difference would be seen.
- Same data, same S, same view definition each N; autocompaction disabled on the base so S does not change;
  the view memtable is flushed (`Util.flush(cfs.viewManager)`) before H_base so memtable content does not differ.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node (single node is enough: view replicas are local, `StorageProxy.java:1067-1076`),
JDK 11, Ant, ≥ 4 cores, ≥ 30 GiB free local disk.
```
export W=/local/s3-cmvb ; cd $W/cassandra-5.0.9 && ant jar        # copy from B2a
export CASSANDRA_HOME=$W/cassandra-5.0.9 ; mkdir -p $W/node/{data,commitlog,hints,saved_caches,cdc}
```
`conf/cassandra.yaml` in the copy: `data_file_directories: [$W/node/data]`, `commitlog_directory: $W/node/commitlog`,
`hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under `$W/node`; `materialized_views_enabled: true`;
`concurrent_compactors: 1`; `compaction_throughput: 64MiB/s`; listen/rpc `127.0.0.1`; all else default.
JVM: `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M` (env), add to `conf/jvm-server.options` (copy only):
`-XX:NativeMemoryTracking=summary` and `-Xlog:gc*:file=$W/node/gc-%p.log:time,uptime`.

**B3b. Knobs.** `concurrent_materialized_view_builders ∈ {1, 4, 16}` in the yaml, node restarted per value (also confirm with
`nodetool getconcurrentviewbuilders`). With P cores, keep ≤ 4·P. Positive-control knob: `memtable_heap_space ∈ {1024MiB, 128MiB}` at N=4.

**B3c. Workload.** Load once, reuse the same base SSTables for every run:
1. Start node, `bin/nodetool disableautocompaction` after `tools/bin/cassandra-stress write n=10000000 cl=ONE -rate threads=64 -node 127.0.0.1`
   creates `keyspace1.standard1` (key blob + `C0`..`C4` 34-byte blobs); run `nodetool disableautocompaction keyspace1 standard1`
   right after the keyspace appears, then `nodetool flush`. Expected base size ≈ 10 M × ~190 B ≈ 1.8–2.2 GiB; S = number of
   `*-Data.db` files (record).
2. `nodetool drain`, stop node, `cp -a $W/node/data/keyspace1 $W/seed-keyspace1` and the `system*` dirs (whole `$W/node/data`
   to `$W/seed-data`). Each run starts from `rm -rf $W/node/* ; cp -a $W/seed-data $W/node/data`.
3. Per run: start node, wait for `nodetool status` UN, `nodetool enableautocompaction keyspace1 standard1` stays **off**, then
   `bin/cqlsh -e "CREATE MATERIALIZED VIEW keyspace1.mv AS SELECT * FROM keyspace1.standard1 WHERE \"C0\" IS NOT NULL AND key IS NOT NULL PRIMARY KEY (\"C0\", key);"`
   The view build writes ≈ 10 M view rows (≈ 2 GiB of view data) through memtables → flushes; the pool is saturated for the
   whole build (4·P ≥ 16 tasks queued). Duration: until `nodetool viewbuildstatus keyspace1.mv` shows SUCCESS (expect minutes to tens of minutes at N=1).
4. Then `nodetool flush keyspace1` and `nodetool compact keyspace1 mv`; measure final size.

**B3d. Observables and instruments.** Sampler script (`$W/sample.sh`, every 1 s while building, CSV to `$W/runs/N<n>.csv`):
- tasks: `nodetool compactionstats | grep -c "View build"` and `nodetool tpstats | grep ViewBuildExecutor` (Active, Pending);
- heap: post-GC heap from the GC log (`grep -o "->[0-9]*M" gc-*.log`, take max of "after GC" values over the build), and `jstat -gc <pid> 1000`;
- off-heap pooled buffers: `nodetool sjk mx -b "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=UsedSize" -mg -f Value` (also `Size`, `OverflowSize`);
- memtables: `nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize" -mg -f Value` (every 5 s);
- native: `jcmd <pid> VM.native_memory summary` every 30 s (Thread and Other categories);
- process: `ps -o rss= -p <pid>`;
- disk: `du -sb $W/node/data $W/node/commitlog` every 5 s (peak), final after step 4;
- build time: CREATE → SUCCESS.
Not directly observable: per-task retained bytes (inferred from differences across N).

**B3e. Procedure.**
1. Build and configure (B3a); load and save seed (B3c 1–2).
2. For N in 1 4 16, three repetitions each: restore seed; set N in yaml; `bin/cassandra -p $W/node/pid`; wait UN; start sampler;
   CREATE view; wait SUCCESS; stop sampler; flush + compact view; record final `du`; `nodetool drain`; `kill $(cat $W/node/pid)`; wait for exit.
3. Positive control: N=4 with `memtable_heap_space: 128MiB`, one run each (compare with N=4 at default 1024MiB, the default for a 4G heap).
4. Compute per run: max tasks, max post-GC heap, max BufferPool UsedSize, max RSS, peak and final disk, build time.

**B3f. Predictions.**
| N | View build tasks Active | max post-GC heap | max chunk-cache UsedSize | max RSS | peak disk / final disk | build time |
|---|---|---|---|---|---|---|
| 1 | 1 | H1 | U1 | R1 | Dp1 / Df1 | T1 |
| 4 | 4 | H1 ± max(64 MiB, 5%) | ≤ U1 + 4 MiB | R1 ± 5% | Dp1 ± 10% / Df1 ± 2% | < T1 |
| 16 | min(16, 4P) | H1 ± max(64 MiB, 5%) | ≤ U1 + 16 MiB | R1 ± 5% | Dp1 ± 10% / Df1 ± 2% | ≤ T4 |
NMT "Thread" committed grows by about (N−1) × 256 KiB (`-Xss256k`, `conf/jvm-server.options:123`) — negligible.
`AllMemtablesOnHeapDataSize` peak ≤ ~1024 MiB in every N run.
Positive control: peak `AllMemtablesOnHeapDataSize` at 128 MiB ≤ ~140 MiB, at 1024 MiB clearly higher (≥ 200 MiB) — the cap binds.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| Active = min(N,4P), build time falls with N, heap/pool/RSS/disk within the bands above, positive control's memtable peak follows `memtable_heap_space` | claim confirmed (usage flat while the control moves) |
| max post-GC heap or RSS rises with N by ≥ 64 MiB and ≥ 5% per step (monotone over 1→4→16 in all repetitions) | claim refuted: usage follows the entry |
| chunk-cache UsedSize/OverflowSize grows ≥ 1 MiB per added thread | refuted for off-heap |
| peak disk rises ≥ 10% with N, traced to base SSTables kept by task `Refs` (`lsof`/`ls` shows compacted base files still present) | refuted for disk (retention by concurrent tasks) |
| Active stays 1 for N > 1, or build too short for samples (< 30 s) | not confirmed: knob not applied or workload too small; double n |
| positive control memtable peak does not move | not confirmed: workload does not exercise memory where a cap is known to bind |

**B3h. Controls.**
- Same seed data (identical S and bytes) for every run; base autocompaction disabled so no base compaction overlaps the build.
- `concurrent_compactors: 1` and fixed `compaction_throughput` so view compaction is the same across N.
- Three repetitions per N; compare medians; noise band from the spread at N=1.
- Build-time and Active-task readings show the knob is effective (a flat memory reading is not due to an inert knob).
- Positive control (memtable_heap_space) shows the same workload moves memory where a cap binds.

**B4. Risks and cleanup.** All data, commit log, hints, logs under `$W` on local disk (≤ ~12 GiB: base ~2 GiB, seed copy ~2 GiB,
view ~2 GiB, compaction headroom, commit log ≤ 8 GiB cap — set `commitlog_total_space: 2048MiB` if `$W` is small). Never build in
the shared source tree. After each run: `nodetool drain`, kill the pid, then `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress`
and `pgrep -f "ant|junit"` must be empty (kill leftovers). At the end: `rm -rf $W/node $W/seed-data` (keep `$W/runs/*.csv`, GC logs);
remove `$W/cassandra-5.0.9` if not reused. Unit tier: the test writes under `$W/cassandra-5.0.9/build/test/`; delete the copy afterwards.

## C. Sources read

- src/java/org/apache/cassandra/config/Config.java (122, 340-350)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (780-792, 2530-2545)
- src/java/org/apache/cassandra/db/compaction/CompactionManager.java (162-174, 277-320, 1984-2060, 2110-2140, 2240-2270, 2355-2385)
- src/java/org/apache/cassandra/db/compaction/OperationType.java (42)
- src/java/org/apache/cassandra/service/StorageService.java (2028-2045)
- src/java/org/apache/cassandra/service/StorageServiceMBean.java (841-842, via grep)
- src/java/org/apache/cassandra/service/StorageProxy.java (1010-1113)
- src/java/org/apache/cassandra/tools/NodeProbe.java, tools/nodetool/SetConcurrentViewBuilders.java, GetConcurrentViewBuilders.java (via grep)
- src/java/org/apache/cassandra/db/view/ViewBuilder.java (57-249)
- src/java/org/apache/cassandra/db/view/ViewBuilderTask.java (30-215)
- src/java/org/apache/cassandra/db/view/TableViews.java (160-330, 480-550)
- src/java/org/apache/cassandra/db/view/View.java (213-214), ViewManager.java (134, 182) (via grep)
- src/java/org/apache/cassandra/io/sstable/ReducingKeyIterator.java
- src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java (940-960), format/big/BigTableReader.java (153-156)
- src/java/org/apache/cassandra/io/util/FileHandle.java (grep), BufferManagingRebufferer.java (45-52)
- src/java/org/apache/cassandra/utils/memory/BufferPools.java (35-70); src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java; metrics/TableMetrics.java (506-515)
- conf/cassandra.yaml (42, 448, 736-760, 797-825, 883, 1172, 1225-1245, 1330, 1981), conf/cassandra_latest.yaml (1226), conf/jvm-server.options (123)
- NEWS.txt (630-645); doc/modules/cassandra/pages/developing/cql/mvs.adoc (40-56)
- test/unit/org/apache/cassandra/cql3/ViewTest.java (400-480), ViewAbstractTest.java, CQLTester.java (1075-1180), test/unit/org/apache/cassandra/db/view/ViewBuilderTaskTest.java, test/conf/cassandra.yaml (53), build.xml (testsome target)
- https://issues.apache.org/jira/browse/CASSANDRA-12245 (cited from NEWS.txt; not fetched)

## Config-first: places found

1. [`CompactionManager.java:2127`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L2127) — `ViewBuildExecutor` core/max threads = value: caps the number of `ViewBuilderTask`s running at once, each holding SSTable `Refs`, a `ReducingKeyIterator` over all base SSTables and one partition read (small, transient). **This case file.**
2. `CompactionManager.java:2248-2266` (via `StorageService.java:2036-2042`, `DatabaseDescriptor.java:2539-2541`) — runtime resize of the same pool (JMX `ConcurrentViewBuilders`, `nodetool setconcurrentviewbuilders`); same restriction as place 1, no separate memory/disk effect.
3. `ViewBuilderTask.java:142` reached through place 1 — the number of concurrently held base-SSTable reference sets (`selectAndReference`) equals the running-task count; can keep compacted-away base SSTables on disk while tasks run. Second-order disk effect, covered by B3g's disk row; not given its own file.
4. `DatabaseDescriptor.java:787-788` — startup validation `> 0`; restricts no memory or disk.
5. `DatabaseDescriptor.java:2534-2536` / `StorageService.java:2031-2033` / `NodeProbe.java:1451-1453` — getters (reporting only).

Bounding factor outside the entry: `ViewBuilder.java:64` (`NUM_TASKS = 4 × availableProcessors`) caps tasks per view regardless of the value.

## D. Stage-4 feedback

none yet
