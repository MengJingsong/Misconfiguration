# mapreduce.reduce.markreset.buffer.percent — verification solution  <!-- file: cases/mapreduce.reduce.markreset.buffer.percent-reserve-availableSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BackupStore.java:601`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java#L601) — `if (availableSize == 0) { return 0; }` in `BackupStore.BackupRamManager.reserve(int)` (unit kind: row; extension unit started from this line) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`: the mark-reset memory budget (`maxSize`, from `mapreduce.reduce.markreset.buffer.percent` × reduce-JVM max heap, or `mapreduce.reduce.markreset.buffer.size` when > 0) caps the heap the reducer's `BackupStore` memory cache holds; records past the budget go to a local-disk file. The cap is soft: slack returned when a block is closed is re-lent while the closed block's `byte[]` keeps its full capacity, so retained heap can exceed the budget by up to just under 2× for adversarial record sizes (negligible, ≤ 118 B per 1 MiB block, for small uniform records). Line 601 itself is a degenerate guard: its true branch is taken only when the budget is 0 (the default), and it returns the same 0 that `Math.min` would. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**

- **Primary:** `mapreduce.reduce.markreset.buffer.percent` — configuration key, declared as
  `MRJobConfig.REDUCE_MARKRESET_BUFFER_PERCENT` at
  [`MRJobConfig.java:507`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java#L507).
  `mapred-default.xml:596-602` documents it with value `0.0`: "The percentage of memory -relative to
  the maximum heap size- to be used for caching values when using the mark-reset functionality."
  Unit: fraction of the reduce JVM's `Runtime.getRuntime().maxMemory()` (range checked to [0.0, 1.0],
  `BackupStore.java:97-100`, otherwise `IOException`). Java default in the read is `0f`
  (`BackupStore.java:94-95`), equal to the XML default, so the effective default is 0.0 → budget 0.
  Deprecated alias: `mapred.job.reduce.markreset.buffer.percent` (`ConfigUtil.java:255-256`).
- **Secondary (overrides the primary when > 0):** `mapreduce.reduce.markreset.buffer.size` —
  `MRJobConfig.REDUCE_MARKRESET_BUFFER_SIZE` at
  [`MRJobConfig.java:509`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java#L509);
  bytes; read with default 0 (`BackupStore.java:106-109`); **not** in `mapred-default.xml` (undocumented).
- **Derived limit:** `maxSize = (int) min(maxMemory × percent, Integer.MAX_VALUE)`
  (`BackupStore.java:102-103`), replaced by `buffer.size` if that is > 0 (`:106-109`), logged at INFO
  as "Created a new BackupStore with a memory of <maxSize>" (`:117`). It becomes
  `BackupRamManager.maxSize`/`availableSize` (`:389-390`, `:590-592`); the operand at line 601 is the
  remaining budget `availableSize`.
- **How set:** per job (job configuration, `mapred-site.xml`, or `-D` on a `ToolRunner` job). Read by
  the **reduce task JVM** (`YarnChild` / `LocalJobRunner`) when the reducer first calls `mark()` on its
  values iterator (`ReduceContextImpl.java:255-258`). No daemon restart: it takes effect for the next job.
- Only reducers written against the new API that wrap their values in `MarkableIterator`
  (`MarkableIterator.java:34-50`) and call `mark()` ever create a `BackupStore`.

**A2. What it caps.** Reduce-task JVM **heap**: the `byte[]` blocks of `BackupStore.MemoryCache`, which
cache the serialized key/value bytes iterated after `mark()` so that `reset()` can replay them. The
quantity compared against the limit is the ram manager's `availableSize` = `maxSize` − (sum of reserved
block bytes, minus slack returned when blocks are closed). It does **not** cap disk: records that do not
fit go to an unbounded IFile on the task's local dirs.

**A3. Mechanism.**

1. `ValueIterator.mark()` (`ReduceContextImpl.java:254-276`) creates the store on first use and calls
   `backupStore.reinitialize()` → `memCache.reinitialize(true)` (`BackupStore.java:304-309`, `:405-413`):
   `availableSize = maxSize` (`:626-628`), then `createNewMemoryBlock(defaultBlockSize, defaultBlockSize)`
   where `defaultBlockSize = min(1 MiB, maxSize)` (`:387-393`).
2. `createNewMemoryBlock` (`:415-426`) calls `ramManager.reserve(requested, min)` (`:610-618`): returns 0
   if `availableSize < minSize`, else `reserve(requested)` (`:600-608`):
   **[`if (availableSize == 0) return 0;`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java#L601)**,
   else grants `min(requested, availableSize)` and subtracts it. A non-zero grant allocates
   `new DataOutputBuffer(allocatedSize)` (`:422`) — a `byte[allocatedSize]`.
   - When is line 601 true? It is reached only after `availableSize >= minSize` (`:611`). `minSize` is
     either `defaultBlockSize` (`:409-410`, `:603` path) or `length + EOF_MARKER_SIZE` ≥ 18 (`:447-448`).
     So `availableSize == 0` at line 601 requires `minSize == 0`, i.e. `defaultBlockSize == 0`, i.e.
     `maxSize == 0` — the **default** configuration. Then 601 returns 0, `dataOut = null`,
     `blockSize = 0` (`:418-420`). The false branch would also yield `min(0, 0) = 0`, so the check is
     behaviourally redundant; the real gate for every positive budget is `:611`.
3. Every cached record (`nextKeyValue` → `backupStore.write`, `ReduceContextImpl.java:148-150`;
   `BackupStore.write`, `:128-144`; the first record via `getOutputStream`, `:337-344`) first calls
   `memCache.reserveSpace(len)` (`:435-451`): fits if `blockSize − usedSize ≥ len + 18`. Otherwise the
   current block is closed by `createInMemorySegment` (`:488-516`: write two EOF vints, count 18 bytes,
   **`ramManager.unreserve(blockSize − usedSize)`** at `:506`, wrap the block's whole backing array in an
   `InMemoryReader`, `InMemoryReader.java:44-52`) and a new block of `max(len+18, defaultBlockSize)` is
   requested with `minSize = len+18`. A grant of 0 → `reserveSpace` returns false → `fileCache.activate()`
   and **all further records of this mark go to disk** (`:133-143`, `:554-557`).
4. **Limit reached:** no exception, no task failure; the cache spills to
   `<mapreduce.cluster.local.dir>/output/backup_<taskId>_<n>.out` via `LocalDirAllocator` with size `-1`
   (`:570-582`), an uncompressed IFile with a 4-byte checksum (`IFile.java:105-127`).
5. **Release:** `Reducer.run` calls `resetBackupStore()` after each key (`Reducer.java:170-176`) →
   `reinitialize()` → `clearSegmentList()` (`BackupStore.java:369-378`) closes segments and the budget is
   reset to `maxSize`; a fresh `defaultBlockSize` block is allocated immediately (`:405-413`).
6. **Overshoot path (soft cap):** at step 3 the slack `blockSize − usedSize` is returned to the budget
   (`:506`) but the closed block's `byte[blockSize]` stays referenced by its `InMemoryReader` until the
   segment is closed. The slack is then lent to later blocks. Retained heap = Σ block capacities, while the
   budget counts Σ used bytes. Slack in a block is < (size of the record that did not fit + 18), and that
   record then occupies the next block, so retained ≤ ~2 × `maxSize` (+ the open block). With uniform
   100-byte records slack is 58 B per 1 MiB block (negligible); with alternating tiny/≈1 MiB records it
   approaches 2×.
7. **Under-count the other way:** `mark()` during reset drops leading segments without `unreserve`
   (`:159-172`), so the budget is consumed by freed memory until the next `reinitialize` — earlier spill,
   never overshoot.
8. **Disk:** unbounded; backup files are created with `preserve = true` (`:562`) so `Segment.close()` never
   deletes them (`Merger.java:352-357`); `FileCache.reinitialize` just resets `spillNumber` (`:548-552`) so
   names are reused (overwritten) on one local dir, and old files stay until the container's directories
   are cleaned.

**A4. Other consumers.** In the reduce JVM, outside this budget: shuffle buffers
(`mapreduce.reduce.shuffle.input.buffer.percent`) and in-memory map outputs retained into the reduce
phase (`mapreduce.reduce.input.buffer.percent`, default 0.0); IFile read buffers and the
`DataInputBuffer`s/`currentValue` of the store (small); the user reducer's own objects. On disk, the
shuffle's on-disk map outputs and the reduce output share the same local dirs and are not bounded by this
key. YARN's container memory limit (`mapreduce.reduce.memory.mb`) bounds the whole process.

**A5. Evidence beyond the source.** `mapred-default.xml:596-602` (description of the percent key);
`hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/mapreduce/TestValueIterReset.java:522-536`
(functional test of mark/reset with `buffer.size = 128`, checks correctness only, not memory);
code comment cites HADOOP-5494 (`BackupStore.java:266-268`,
https://issues.apache.org/jira/browse/HADOOP-5494), not relied on for memory claims.

## B. Verification solution

**B1. Claim under test.** For a reducer that marks and replays a key's values, the heap held by the
`BackupStore` memory cache grows with the data only up to the budget `maxSize` (from
`mapreduce.reduce.markreset.buffer.percent` × max heap, or `buffer.size`) and is ≈ 0 at the default 0.0;
everything beyond goes to a local backup file. Retained heap may exceed `maxSize` only by the closed-block
slack: ≤ (blocks × 118 B) for uniform 100-byte records, and < 2 × `maxSize` for any record pattern.
Wrong if cached heap tracks the data size independent of `maxSize`, or exceeds 2 × `maxSize` + 1 MiB.

### B2. Unit tier

**B2a. Environment and build.** JDK 8, Maven 3.3+. Copy the tag to local disk
(`rsync -a <shared-src>/ $WORK/hadoop-3.4.2/`; never build in the shared tree). Module
`hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core`. Add test
`src/test/java/org/apache/hadoop/mapred/TestBackupStoreBudget.java` (same package as `BackupStore`, so
`segmentList` and `Merger.Segment.reader` are package-visible; private fields via reflection). Surefire
JVM uses `-Xmx2048m` (`hadoop-project/pom.xml:187`).

```
cd $WORK/hadoop-3.4.2
mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core -am install -DskipTests
mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core test -Dtest=TestBackupStoreBudget
```

**B2b. Knobs.**

| Run | `buffer.percent` | `buffer.size` | Why |
|---|---|---|---|
| U0 | 0.0 (default) | unset | default; drives line 601 true |
| U1 | 0.0 | 1048576 (1 MiB) | budget = exactly one default block |
| U4 | 0.0 | 4194304 (4 MiB) | mid |
| U16 | 0.0 | 16777216 (16 MiB) | larger; still < data |
| UP | 0.01 | unset | percent path: `maxSize = (int)(Runtime.maxMemory() × 0.01)` (≈ 19–20 MB under -Xmx2048m) |
| UA4 / UA16 | 0.0 | 4 MiB / 16 MiB | adversarial record pattern (overshoot bound) |

Set with `conf.setFloat(MRJobConfig.REDUCE_MARKRESET_BUFFER_PERCENT, p)` /
`conf.setInt(MRJobConfig.REDUCE_MARKRESET_BUFFER_SIZE, s)` on a fresh `Configuration` per run; also
`conf.set(MRConfig.LOCAL_DIR, <junit temp dir>)` so the file cache writes to a known local directory.

**B2c. Workload.**
- Uniform (U0–U16, UP): 335,544 records, key 8 bytes, value 90 bytes → record = 8 + 90 + 1 + 1 = 100 B
  (vint size 1 for lengths ≤ 127, `WritableUtils.java:400-412`); data D = 33,554,400 B (≈ 32 MiB),
  larger than every budget. A 1 MiB block holds ⌊(1048576 − 18)/100⌋ = 10,485 records.
- Adversarial (UA): 40 pairs of (tiny: key 1 B + value 1 B → 4 B; huge: key 1 B + value 1,048,550 B →
  1 + 1048550 + 1 + 4 = 1,048,556 B). Tiny opens a 1 MiB block; the huge one cannot fit
  (needs 1,048,574 > 1,048,572 free) and gets its own 1 MiB block; the next tiny then cannot fit in the
  20 B left (needs 22), so every block is closed — half of them nearly empty but full-size.

Driver: `store = new BackupStore<>(conf, new org.apache.hadoop.mapred.TaskAttemptID("jt", 1, TaskType.REDUCE, 0, 0));`
`store.reinitialize();` then for each record `store.write(keyBuf, valBuf)` with `DataInputBuffer`s reset
onto the record bytes; then `store.reset();` then iterate `while (store.hasNext()) { store.next(); ... }`
and assert count and bytes equal to what was written (correctness control).

**B2d. Observables and instruments.** Read after the writes and again after `reset()`:
- `maxSize`, `availableSize`: reflection `store.memCache.ramManager.{maxSize,availableSize}`;
  accounted = `maxSize − availableSize`.
- Retained cache heap `R` = Σ over `store.segmentList` with `s.inMemory()` of
  `((IFile.Reader) s.reader).buffer.length` (field `IFile.java:295`) + `memCache.dataOut.getData().length`
  if `dataOut != null` (the open block). This is the exact byte[] capacity the cache keeps reachable.
- In-memory record count (count records while replaying until the first on-disk segment), disk
  segment count, and `du -b`/`File.length()` of `<localdir>/output/backup_*.out`.
- Line 601 directly: a counter is not available; infer from `dataOut == null && blockSize == 0` after
  `reinitialize()` with `maxSize == 0` (only line 601 produces that state for `maxSize == 0`).
- Optionally `MemoryMXBean` heap-used after `System.gc()` as a coarse cross-check (noisy; not decisive).

**B2e. Procedure.**
1. Copy tree, add the test, build (B2a).
2. For each run in B2b: new temp local dir, new `Configuration`, create store, reinitialize, record state
   (1st reading), write workload, record state (2nd), `reset()`, record state (3rd), replay and verify,
   `store.reinitialize()` (= `clearSegmentList`), record `availableSize == maxSize` (4th), print one line
   per run: `run maxSize accounted R inmemRecords diskRecords diskFileBytes`.
3. Delete the temp dir.

**B2f. Predictions** (from the code arithmetic, B2c; after `reset()`):

| Run | maxSize | in-memory records | accounted | retained R | disk records | backup file bytes |
|---|---|---|---|---|---|---|
| U0 | 0 | 0 | 0 | 0 (no block; line 601 true at reinitialize) | 335,544 | 33,554,400 + 6 |
| U1 | 1,048,576 | 10,485 | 1,048,518 | 1,048,576 | 325,059 | 32,505,900 + 6 |
| U4 | 4,194,304 | 41,942 | 4,194,290 | 4,194,536 (= maxSize + 232) | 293,602 | 29,360,200 + 6 |
| U16 | 16,777,216 | 167,769 | 16,777,206 | 16,778,144 (= maxSize + 928) | 167,775 | 16,777,500 + 6 |
| UP | ⌊maxMemory×0.01⌋ | ≈ ⌊maxSize/1048518⌋ × 10,485 (+ a few) | ≤ maxSize | ≤ maxSize + blocks × 118 | rest | rest × 100 + 6 |
| UA4 | 4,194,304 | 7 | 3,145,810 | ≈ 7,339,972 (≈ 1.75 × maxSize) | 73 | ≈ 38.8 MB |
| UA16 | 16,777,216 | 31 | 15,728,962 | ≈ 32,505,556 (≈ 1.94 × maxSize) | 49 | ≈ 26.2 MB |

General relation: accounted ≤ maxSize always; R ≤ 2 × maxSize + 1 MiB; disk = D − in-memory bytes.
After `reinitialize()`: `availableSize == maxSize` (minus the fresh block) and R of closed segments = 0.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| R ≈ predicted per row, in-memory count matches, rest on disk | claim confirmed (cap holds, soft by slack) |
| R or in-memory records grow with D (all 335,544 in memory) at U1–U16 | claim wrong: budget not enforced |
| R > 2 × maxSize + 1 MiB in any run | claim wrong: overshoot bound wrong |
| U0 shows a non-null `dataOut` or any in-memory record | claim wrong about the default/line 601 path |
| UA R ≈ maxSize (no overshoot) | mechanism of A3 step 6 wrong (slack not re-lent or block not retained); cap stricter than claimed |
| Replay count/bytes differ | harness bug; readings invalid |

**B2h. Controls.** Same workload at four budgets (memory steps with budget, disk steps inversely); U0
as the zero-budget case known to bind (all to disk); correctness replay; UA vs U4 (same budget, different
record pattern) isolates the slack effect; percent run UP checks the `maxMemory × percent` derivation
against the INFO log line (`BackupStore.java:117`).

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed: NameNode, DataNode,
ResourceManager, NodeManager (no JobHistory server needed). JDK 8. Build the distribution from the local
copy: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`; unpack
`hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$RUN/hadoop` (`$RUN` = a local disk with ≥ 10 GB free).
Environment: `HADOOP_HOME=$RUN/hadoop`, `HADOOP_CONF_DIR=$RUN/conf`, `HADOOP_LOG_DIR=$RUN/logs`,
`HADOOP_PID_DIR=$RUN/pids`, `HADOOP_HEAPSIZE_MAX=1g` for daemons.

- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$RUN/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=file://$RUN/nn`, `dfs.datanode.data.dir=file://$RUN/dn`.
- `yarn-site.xml`: `yarn.nodemanager.aux-services=mapreduce_shuffle`,
  `yarn.nodemanager.local-dirs=$RUN/nm-local` (single dir, so backup file names are deterministic),
  `yarn.nodemanager.log-dirs=$RUN/nm-logs`, `yarn.nodemanager.resource.memory-mb=6144`,
  `yarn.scheduler.maximum-allocation-mb=4096`, `yarn.nodemanager.vmem-check-enabled=false`,
  `yarn.nodemanager.delete.debug-delay-sec=600` (keep container dirs/logs for inspection).
- `mapred-site.xml`: `mapreduce.framework.name=yarn`; `yarn.app.mapreduce.am.env`, `mapreduce.map.env`,
  `mapreduce.reduce.env` = `HADOOP_MAPRED_HOME=$RUN/hadoop`; `mapreduce.reduce.memory.mb=2048`;
  `mapreduce.reduce.java.opts=-Xmx1536m`; `mapreduce.map.memory.mb=1536`, `mapreduce.map.java.opts=-Xmx1200m`;
  `mapreduce.job.reduces=1`; `mapreduce.task.timeout=1200000`.
- Check default ports are free first (`ss -ltn | grep -E ':(9000|9870|9864|9866|8088|8030|8031|8032|8042|13562)\b'`).

Job jar `markreset.jar` (built with `javac -cp "$($RUN/hadoop/bin/hadoop classpath)" -d classes MarkResetJob.java && jar cf markreset.jar -C classes .`),
a `Tool` run via `ToolRunner` so `-D` works:
- Input: one HDFS text file with one line → one map task. The mapper reads `markreset.records`,
  `markreset.mode` (`uniform` | `adversarial`) and emits `(LongWritable seq, BytesWritable v)` for
  `seq = 0 .. records-1`.
  - uniform: `v` = 86 random bytes → value raw length 4 + 86 = 90, record = 8 + 90 + 1 + 1 = 100 B.
  - adversarial: even `seq` → 0-byte value (record 8 + 4 + 1 + 1 = 14 B); odd `seq` → 1,048,539-byte value
    (record 8 + 1048543 + 1 + 4 = 1,048,556 B).
- Grouping comparator `AllEqual extends WritableComparator(LongWritable.class)` whose `compare` returns 0
  → the single reducer sees **one** key group with values in `seq` order (map-side sort by key keeps
  this order; plain same-key values would come in no guaranteed order).
- Reducer (`mode=markreset`): `MarkableIterator<BytesWritable> it = new MarkableIterator<>(values.iterator()); it.mark();`
  pass 1 counts all values; `hold("H1")`; `it.reset()`; pass 2 counts again; `hold("H2")`; write
  `n1,n2`. `hold` logs `HOLD <label> start/end` and sleeps `markreset.hold.ms` (default 90000) calling
  `context.progress()` every 5 s.
- Reducer (`mode=retain`, positive control for the instrument): no mark; copies the first
  `markreset.retain.records` values into an `ArrayList<byte[]>` (`v.copyBytes()`), then `hold("H1")`.

**B3b. Knobs** (all per job with `-D`, no restart):

| Run | `mapreduce.reduce.markreset.buffer.percent` | `...buffer.size` | mode / records |
|---|---|---|---|
| C0 | 0.0 (default) | unset | uniform, 2,684,354 |
| C5 | 0.05 | unset | uniform, 2,684,354 |
| C10 | 0.10 | unset | uniform, 2,684,354 |
| C25 | 0.25 | unset | uniform, 2,684,354 |
| CS | 0.25 | 33554432 (32 MiB) | uniform, 2,684,354 (size overrides percent) |
| CA | 0.0 | 67108864 (64 MiB) | adversarial, 400 (200 pairs) |
| CR | 0.0 | unset | retain, 745,654 values (control) |

Percentages chosen so budgets bracket the data: with `-Xmx1536m`, `maxMemory` is a little below 1536 MiB
(the exact `maxSize` is read from the task log), giving ≈ 70–80 MB (C5), ≈ 140–160 MB (C10) < D, and
≈ 350–400 MB (C25) > D.

**B3c. Workload.** Uniform: 2,684,354 × 100 B = D = 268,435,400 B (≈ 256 MiB) of marked data in one key
group — reachable since every value iterated after `mark()` is copied into the store
(`ReduceContextImpl.java:148-150`). Adversarial: 200 × (14 + 1,048,556) ≈ 200 MiB. Each job: map ≈ 1–2 min,
reduce two passes + two 90 s holds; ≈ 6–8 min per run.

**B3d. Observables and instruments.**
- Reduce task `syslog` (`$RUN/nm-logs/<app>/<container>/syslog`): `Created a new BackupStore with a memory of N`
  (gives `maxSize`), `Created file: output/backup_...` (spill to disk happened), `HOLD` markers.
- Reduce JVM pid: `jps -lm | grep YarnChild | grep '_r_'`.
- Heap retained by byte arrays at each hold: `jcmd <pid> GC.class_histogram | awk '$4=="[B"{print $3}'`
  (forces a full GC; live objects only) — sample once in the middle of H1 and of H2. Also `jstat -gc <pid>`
  (OU, old-gen used) at the same moments.
- Disk: `find $RUN/nm-local -name 'backup_*.out' -printf '%s %p\n'` and `du -sb $RUN/nm-local` during H1/H2.
- Process RSS `grep VmRSS /proc/<pid>/status` (secondary: heap is not returned to the OS, so RSS only shows
  growth, not the exact cache size).
- Not observable directly: `availableSize` (covered by the unit tier); attribution of `[B` bytes to the
  cache — handled by subtracting the C0 baseline at the same hold point.

**B3e. Procedure.**
1. Build, unpack, write configs (B3a); `hdfs namenode -format -force`; `start-dfs.sh`; `start-yarn.sh`;
   `jps` shows NN, DN, RM, NM.
2. `hdfs dfs -mkdir -p /mr && echo x | hdfs dfs -put - /mr/in.txt`.
3. For each run in B3b (one at a time):
   `yarn jar markreset.jar MarkResetJob -D mapreduce.reduce.markreset.buffer.percent=<p> [-D mapreduce.reduce.markreset.buffer.size=<s>] -D markreset.mode=<m> -D markreset.records=<n> /mr/in.txt /mr/out-<run>`;
   when the reduce `syslog` shows `HOLD H1 start`, take the `jcmd`, `jstat`, `find`, `VmRSS` readings;
   repeat at `HOLD H2 start`; after the job, verify output `n1 == n2 == records` and save the syslog.
4. `hdfs dfs -rm -r -skipTrash /mr/out-<run>` between runs.
5. Stop: `stop-yarn.sh; stop-dfs.sh`; `jps` must show no Hadoop process; `rm -rf $RUN/{nn,dn,tmp,nm-local}`
   after copying logs.

**B3f. Predictions.** Let `N` = logged `maxSize`, `Δ` = `[B` bytes minus C0's at the same hold point.

| Run | N | Δ at H1 / H2 | backup files at H2 |
|---|---|---|---|
| C0 | 0 | 0 (baseline) | one file ≈ 268,435,406 B |
| C5 | ⌊0.05 × maxMemory⌋ | ≈ N (between N − 1 MiB and N + 1 MiB; slack ≤ 58 B/block) | ≈ D − (in-memory records × 100) |
| C10 | ⌊0.10 × maxMemory⌋ | ≈ N, ≈ 2 × C5's Δ | ≈ D − ≈2 × C5's in-memory bytes |
| C25 | ⌊0.25 × maxMemory⌋ > D | ≈ 257 MiB = 269,484,032 B (all 2,684,354 records in 257 full 1 MiB blocks; flat, not N) | none |
| CS | 33,554,432 | ≈ 33,556,288 (= N + 1,856) | ≈ 234,881,606 B |
| CA | 67,108,864 | ≈ 133 MB (≈ 1.98 × N; 127 records in memory, 66,062,210 B accounted) | ≈ 143.7 MB |
| CR | 0 | ≈ 745,654 × 104 B ≈ 77.5 MB (`copyBytes()` returns `byte[86]`, `BytesWritable.java:83-85`; 16 B header + 86 B, 8-byte aligned, 64-bit JDK 8 with compressed oops) | none |

Relation: Δ rises linearly with N while N < D and flattens at ≈ D once N ≥ D; disk falls correspondingly.
The claim is wrong if Δ ≈ D in C5/C10/CS, or C0's backup file is missing, or Δ in any run exceeds
2 × N + 1 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Δ follows N (C5 < C10 < D), C25 flat at ≈ D, disk = D − cached | claim confirmed |
| Δ ≈ D in C5/C10/CS (everything cached) | claim wrong: budget not enforced |
| Δ ≈ 0 in all runs, all data on disk | percent/size not reaching the task (check `N` in syslog); if N > 0, mechanism wrong |
| CA Δ ≈ 2 × N | soft-cap overshoot confirmed at cluster level |
| CA Δ ≤ N | slack not retained; cap stricter than claimed |
| CA Δ > 2 × N + 1 MiB | overshoot bound wrong |
| CR Δ not ≈ 77.5 MB (± 5 %) | instrument does not see retained byte arrays; all Δ readings invalid |
| `n1 ≠ n2` | replay broken; run invalid |

**B3h. Controls.** C0 (budget 0 — the cap known to bind: no cache, all disk) as baseline for Δ; CR
(instrument positive control: known retained bytes); one key group and single reducer so only one store
exists; `mapreduce.reduce.input.buffer.percent` left at 0.0 so no shuffle data is held in heap during
reduce; the same job and data across C0–CS so only the knob differs; CS checks that `buffer.size` overrides
`percent`; holds taken after a forced GC (`GC.class_histogram`) to count live bytes only.

**B4. Risks and cleanup.** Unit tier: ≤ 40 MB of temp files in the JUnit temp dir, ≤ 2 GB test heap;
delete the temp dir. Cluster tier: ≈ 0.3 GB HDFS data, ≈ 0.6 GB map output + ≤ 0.3 GB backup files per run
under `$RUN` (local disk only, never shared storage); reduce container 2 GB + map 1.5 GB + AM 1.5 GB fit in
6 GB NM memory — check the host has ≥ 8 GB free; ports as in B3a (use another port set if taken). After the
last run `stop-yarn.sh`, `stop-dfs.sh`, `jps` empty of NameNode/DataNode/ResourceManager/NodeManager/YarnChild/
MRAppMaster, kill any leftover `YarnChild` by pid, remove `$RUN/{nn,dn,tmp,nm-local,nm-logs}` after saving
logs. Backup files are not deleted by the task itself (A3 step 8); `debug-delay-sec=600` keeps them for
600 s, after which the NodeManager removes the application directory.

## C. Sources read

hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java (lines 500-512, 1069)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRConfig.java (line 35)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/util/ConfigUtil.java (lines 255-256)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml (lines 596-602)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/ReduceContextImpl.java (lines 60-340)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/Reducer.java (lines 160-185)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MarkableIterator.java
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/InMemoryReader.java (lines 35-80)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/Merger.java (lines 215-380)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IFile.java (lines 85-180, 225-245, 295, 455-461)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/TaskAttemptID.java (constructors)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/main/java/org/apache/hadoop/mapred/YarnChild.java (lines 279-282)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/mapreduce/TestValueIterReset.java (lines 49-60, 522-550)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/DataOutputBuffer.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/WritableUtils.java (lines 400-412)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/BytesWritable.java (lines 83-85)
hadoop-project/pom.xml (line 187)
https://issues.apache.org/jira/browse/HADOOP-5494 (cited by code comment only; not opened)

## D. Stage-4 feedback

none yet
