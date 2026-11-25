# mapreduce.reduce.markreset.buffer.percent — verification solution  <!-- file: cases/mapreduce.reduce.markreset.buffer.percent-reserveSpace-availableSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BackupStore.java:437`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java#L437), `if (availableSize >= length + EOF_MARKER_SIZE)` in `BackupStore.MemoryCache.reserveSpace(int)`. This is the per-block check; the check that enforces the total limit is [`BackupStore.java:611`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java#L611) in `BackupRamManager.reserve(int,int)`, which `reserveSpace` reaches when line 437 fails. The file is named after the given method, `reserveSpace`. |
| Pinned source | `rel/release-3.4.2` |
| Session / date | stage-3 autonomous agent, 2026-11-24 |
| Estimate | `positive`. The limit is `maxSize = min(Runtime.maxMemory() × percent, Integer.MAX_VALUE)`, or `mapreduce.reduce.markreset.buffer.size` when that is > 0. It caps the reduce task's heap held by the mark/reset memory cache: once the cache is full, every further marked record goes to a local-disk spill file. The cap is approximate, not exact. Accounting charges a closed block only for its used bytes, while the whole block array stays live. With records of one size the held heap stays within maxSize plus a few KB. With an adversarial mix of record sizes it can reach about 2 × maxSize. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `mapreduce.reduce.markreset.buffer.percent`. It is a configuration key (float, a fraction of the reduce JVM's max heap).
- **Declaration:** [`MRJobConfig.java:507`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java#L507), `REDUCE_MARKRESET_BUFFER_PERCENT`.
- **Documented default:** `0.0`, at [`mapred-default.xml:597-602`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml#L597-L602). The description reads "percentage of memory -relative to the maximum heap size- to be used for caching values when using the mark-reset functionality".
- **Code default:** `0f`, from `conf.getFloat(..., 0f)` at `BackupStore.java:94-95`. The two defaults agree, so nothing conflicts.
- **Deprecated alias:** `mapred.job.reduce.markreset.buffer.percent` (`ConfigUtil.java:255-256`; `DeprecatedProperties.md:132`).
- **Validation:** a value > 1.0 or < 0.0 throws `IOException` when the store is built (`BackupStore.java:97-100`).
- **Derived limit:** `maxSize = (int) min(Runtime.getRuntime().maxMemory() * percent, Integer.MAX_VALUE)` (`BackupStore.java:102-103`). It is in bytes, relative to the reduce JVM's `-Xmx` and clamped at 2 GiB − 1.
- **Second source of the limit:** `mapreduce.reduce.markreset.buffer.size` (`MRJobConfig.java:509`). It is an absolute byte count and is not in `mapred-default.xml`; the code default is 0 (`BackupStore.java:106`). When it is > 0 it replaces the percent-derived value (`BackupStore.java:106-109`). The percent key is the primary, documented one.
- **How it is set:** per job, in `mapred-site.xml`, the job configuration or `-D` on `yarn jar` (both keys). No daemon restart is needed; it is read when each reduce task attempt builds its store.
- **Who reads it:** the reduce task JVM (`YarnChild`), in `new BackupStore(conf, taskid)`. That constructor runs lazily from `ReduceContextImpl.ValueIterator.mark()` (`ReduceContextImpl.java:255-258`), so only reducers that call `MarkableIterator.mark()` (new API) read it.
- **Default behaviour:** at `0.0`, `maxSize = 0`, so every marked value goes to disk (see A3).

**A2. What it caps.** It caps the reduce-task JVM heap held by the `BackupStore` in-memory cache. That cache is a chain of `byte[]` blocks (`DataOutputBuffer`), default 1 MiB each (`BackupStore.java:387`), holding the marked records of the current key in IFile format. Three quantities are compared:
- **Per block (line 437):** the remaining space of the current block, `availableSize = blockSize − usedSize` (line 436), against `length + EOF_MARKER_SIZE`. `length` is the record's serialized size (`klen + vlen + vint(klen) + vint(vlen)`, lines 455-461), and `EOF_MARKER_SIZE` is 18 bytes (lines 66-67).
- **Total (line 611):** the `BackupRamManager` budget `availableSize` (initially `maxSize`, lines 587-592) against the minimum size of the next block, `length + 18`.

The disk side, the spill file under `mapreduce.cluster.local.dir`, is not capped by this or any other key.

**A3. Mechanism.**
1. **Store creation.** `ValueIterator.mark()` creates the store on the first `mark()` (`ReduceContextImpl.java:256-258`). The constructor computes `maxSize` (`BackupStore.java:94-109`) and builds `MemoryCache(maxSize)`. That creates `BackupRamManager(maxSize)` and lowers the block size to `maxSize` when `maxSize` < 1 MiB (`BackupStore.java:389-394`). It logs `Created a new BackupStore with a memory of <maxSize>` (line 117).
2. **First block.** `mark()` then calls `backupStore.reinitialize()` (`ReduceContextImpl.java:261`), which calls `memCache.reinitialize(true)` (`BackupStore.java:308`). That resets the budget to `maxSize` (`BackupStore.java:626-628`) and reserves the first block, `createNewMemoryBlock(defaultBlockSize, defaultBlockSize)` (`BackupStore.java:409-425`). A block of `allocatedSize` is a `new DataOutputBuffer(allocatedSize)`, a `byte[allocatedSize]` (`BackupStore.java:422`).
3. **Records enter the store.** The current record enters via `getOutputStream(length)` (`BackupStore.java:337-344`; `ReduceContextImpl.java:268-273`). Every later value enters via `nextKeyValue()` → `backupStore.write` while marked (`ReduceContextImpl.java:151-153`). `write` goes to the file cache if that is active (`BackupStore.java:133-136`). Otherwise it calls `memCache.reserveSpace(key, value)` (line 138).
4. **The given check,** [`BackupStore.java:437`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java#L437): `if (availableSize >= length + EOF_MARKER_SIZE) return true;`.
   - **True:** the record is appended to the current block (`MemoryCache.write`, lines 470-482). `usedSize` grows by `length`, so the `byte[]` never has to grow.
   - **False:** the current block is closed, `createInMemorySegment()` (lines 488-516). It writes two 1-byte EOF vints but adds 18 to `usedSize` (line 504). It returns `blockSize − usedSize` to the budget (line 506) and wraps `dataOut.getData()`, the whole array, in an `InMemoryReader` segment (lines 508-513). A new block is then requested, `createNewMemoryBlock(max(length+18, defaultBlockSize), length+18)` (lines 446-448).
5. **The total check,** [`BackupStore.java:611`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java#L611): `if (availableSize < minSize) return 0;`. Otherwise the new block gets `min(requested, available)` bytes (lines 600-608). A 0 result makes `reserveSpace` return false (line 450). `write` then calls `fileCache.activate()` and writes the record to a local file `output/backup_<attempt>_<n>.out`, allocated by `LocalDirAllocator(mapreduce.cluster.local.dir)` (`BackupStore.java:141-142, 554-557, 570-582`). From then on every marked record of this key window goes to disk (lines 133-136).
6. **At default `0.0`:** `maxSize = 0` and the block size is 0, so the first `reserveSpace` fails at 611 (`0 < length+18`). Everything goes to disk.
7. **Release.**
   - The budget is reset per key: `Reducer.run` calls `resetBackupStore()` after every `reduce()` (`Reducer.java:170-176`). That calls `reinitialize()`, which releases the segments' accounted lengths (`BackupStore.java:369-378`) and resets the budget (line 407). The old arrays become garbage, so the cap applies per key window, not across keys.
   - `reset()` closes the open block into a segment (lines 188-194).
   - `exitResetMode()` reserves a fresh block from the remaining budget (lines 328-330).
   - In the YARN task, `mapreduce.cluster.local.dir` is set to the container's `LOCAL_DIRS` (`YarnChild.java:279-280`).

**Overshoot paths (where the heap held exceeds maxSize).**
- **(a) Accounting is on used bytes, not array capacity.** Line 506 returns the unused tail of a closed block to the budget, but the segment keeps the whole `byte[blockSize]` live (the `InMemoryReader` holds `buffer = data`, `InMemoryReader.java:51`). It is released only by `Reader.close()` (`IFile.java:455-461`) or by dropping the segment. A block closed with few bytes used therefore pins up to 1 MiB while only those few bytes are charged.
   - **Uniform record sizes:** the returned tails are at most `length+18` each, so the overshoot is a few KB.
   - **Adversarial pattern:** alternate a tiny record with one large enough (> `blockSize − tiny − 18`) not to fit beside it. Each 1 MiB block then holds one tiny record and is charged 34 bytes, so the held heap approaches 2 × maxSize. The tiny records alternate with near-1 MiB records, and each of those is charged at almost its full size, which keeps the ratio just under 2 (see the B2f arithmetic).
- **(b) First-record path.** `getOutputStream(length)` reserves `length` from the raw key/value lengths, but the record is re-serialized with the job's serializers (`ReduceContextImpl.java:333-347`). A serializer that writes more bytes than the raw length would grow the `DataOutputBuffer` past its block (`DataOutputBuffer.java:58-65`). Built-in Writables round-trip exactly, so this is only an edge case.
- **(c) Accounting leak toward under-use.** `mark()` while in reset mode closes dropped segments without unreserving them (`BackupStore.java:161-172`). That makes the budget conservative (earlier spill), not looser.
- **(d) No cross-check with other heap users.** Nothing checks percent plus the shuffle percents against 1.0 (see A4). A large percent can OOM the task even though the cache honours its own budget.

**A4. Other consumers.**
- **Reduce-side heap that this key does not control:**
  - the shuffle in-memory merge buffer, `mapreduce.reduce.shuffle.input.buffer.percent`, default 0.70;
  - map outputs retained during the reduce phase, `mapreduce.reduce.input.buffer.percent`, default 0.0;
  - the user reducer's own objects and the deserialized key/value;
  - a fresh 1 MiB block allocated on every `reinitialize`, i.e. once per key (`Reducer.java:175` → `BackupStore.java:308-309`). This is garbage churn, not retained.
- **Local disk:**
  - The BackupStore spill files have no size limit. `LocalDirAllocator` is called with size −1 (`BackupStore.java:577-578`), so no capacity check applies.
  - The files are also kept after their segment closes, because `preserve=true` (`BackupStore.java:562`; `Merger.java:352-356`). They are reused by name across keys (`spillNumber` is reset to 0, line 549) and removed only with the application's local directories.
  - The local FS also writes `.crc` side files of about 1/128 of the size.
  - Shuffle merge files share the same local dirs.

**A5. Evidence beyond the source.**
- `mapred-default.xml:597-602` (description of the key).
- `DeprecatedProperties.md:132` (alias).
- HADOOP-5494, cited in `BackupStore.java:266-268` (memory-to-disk segment transition bug): https://issues.apache.org/jira/browse/HADOOP-5494.
- The existing test `TestValueIterReset` sets `mapreduce.reduce.markreset.buffer.size=128` to force disk spill (`hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/mapreduce/TestValueIterReset.java:536`). This shows the authors treat the key as the memory/disk switch.
- JDK `Runtime.maxMemory()` documentation (https://docs.oracle.com/javase/8/docs/api/java/lang/Runtime.html#maxMemory--): it reports the max heap the JVM will try to use, which can be slightly below `-Xmx` (e.g. one survivor space excluded under ParallelGC).

## B. Verification solution

**B1. Claim under test.** For one key window of a reducer that uses `mark()`/`reset()`, the heap held by the BackupStore memory cache is bounded by the limit:
- **The limit:** `maxSize = min(maxMemory × mapreduce.reduce.markreset.buffer.percent, 2^31−1)`, or `mapreduce.reduce.markreset.buffer.size` when that is > 0.
- **The bound:** maxSize plus at most one record per block with uniform record sizes, and below 2 × maxSize for any record-size mix.
- **Disk spill:** every record beyond it goes to the local-disk spill file.
- **At the default 0.0:** no record is held in memory.

The claim is wrong if the held heap grows past these bounds as records are added, or if it does not track maxSize.

### B2. Unit tier

**B2a. Environment and build.**
- **Machine:** Linux, JDK 8, Maven ≥ 3.3.
- **Copy the tree:** `rsync -a ~/hadoop-3.4.2/ /mydata/<run>/hadoop-src/`, run from local disk and never in the shared tree. Then `cd /mydata/<run>/hadoop-src`.
- **Build:** `mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core -am install -DskipTests -Dmaven.javadoc.skip=true`.
- **New test file:** `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/test/java/org/apache/hadoop/mapred/TestBackupStoreCap.java`, in package `org.apache.hadoop.mapred` so the package-private `segmentList`, `Merger.Segment.reader`/`inMemory()` and the protected `IFile.Reader.buffer` are reachable. The private fields are read by reflection: `BackupStore.memCache`, `MemoryCache.ramManager`/`blockSize`/`usedSize`/`dataOut`, and `BackupRamManager.availableSize`/`maxSize`.
- **JVM options:** override the surefire heap with `-Dmaven-surefire-plugin.argLine="-Xmx512m -XX:+UseParallelGC"` (default from `hadoop-project/pom.xml:187`).

**B2b. Knobs.**
- **K1, `mapreduce.reduce.markreset.buffer.size`** (exact bytes, set on the `Configuration` passed to `BackupStore`), with percent left at 0. Values:
  - 0, the default path (maxSize 0, all on disk);
  - 65536, smaller than a block (block size becomes 64 KiB);
  - 1048576, one block;
  - 4194304 (4 MiB);
  - 8388608 (8 MiB);
  - 16777216 (16 MiB, which also exercises a partial tail block);
  - 67108864 (64 MiB, larger than the workload, so the cap is never reached).
- **K2, `mapreduce.reduce.markreset.buffer.percent`**, with `buffer.size` unset: 0.0, 0.01 and 0.02 at `-Xmx512m`. This checks the percent path; maxSize is recomputed in the test from `Runtime.getRuntime().maxMemory()`.
- **K3, validation:** percent = 1.5 and −0.1.

**B2c. Workload.**
- **Construction:** `TaskAttemptID tid = new org.apache.hadoop.mapred.TaskAttemptID("cap", 1, TaskType.REDUCE, 0, 0)`. Set `conf.set(MRConfig.LOCAL_DIR, <fresh temp dir on local disk>)`. Then `BackupStore<BytesWritable,BytesWritable> s = new BackupStore<>(conf, tid); s.reinitialize();`.
- **W1, uniform records:**
  - N = 50,000 calls to `s.write(k, v)`, where `k` is a `DataInputBuffer` over 4 raw bytes and `v` is one over 1000 raw bytes, both reset before each call.
  - Record length is `L = 4 + 1000 + vint(4)=1 + vint(1000)=3 = 1008` bytes (`WritableUtils.java:400-412`), so 50.4 MB in total, which exceeds every K1 value below 64 MiB.
  - Per 1 MiB block, records fit while `1048576 − 1008k ≥ 1026`, so 1040 records per block. On close, the block is charged 1040 × 1008 + 18 = 1,048,338 bytes.
- **W2, adversarial sizes:** maxSize = 8 MiB and 40 pairs of records alternating:
  - a small record (key 4 bytes, value 10 bytes, L = 16);
  - a large record (key 4 bytes, value 1,048,560 bytes, L = 1,048,569). Its `L + 18 > 1048576 − 16`, so it never fits beside a small record.
- After writing: call `s.reset()`, then iterate `while (s.hasNext()) { s.next(); count++; }` to check correctness.

**B2d. Observables and instruments.**
- **O1, accounted bytes:** `ramManager.maxSize − ramManager.availableSize`, read by reflection after the write loop and again after `reset()`.
- **O2, actual retained cache arrays:** after `reset()`, collect `seg.reader.buffer` (an `IFile.Reader` protected field) for every segment with `seg.inMemory()`, plus `memCache.dataOut.getData()` if it is non-null. De-duplicate by identity (`IdentityHashMap`) and sum `.length`. This is the cache's real heap footprint, exact to the byte, without GC noise.
- **O3, records in memory:**
  - W1: Σ over in-memory segments of `(seg.getLength() − 18) / 1008`; `getLength()` is the `usedSize` including the 18-byte charge (`InMemoryReader` `fileLength`).
  - W2: count in-memory records while iterating, by checking `seg.inMemory()` of `s.segmentList` when `hasNext()` moves on.
  - Both: N − O3 = records on disk.
- **O4, disk:** the size of each `output/backup_*.out` under the temp local dir, plus its `.crc`.
- **O5, the log line** `Created a new BackupStore with a memory of <maxSize>` (`BackupStore.java:117`); set log4j to INFO for `org.apache.hadoop.mapred.BackupStore`.
- **O6, GC-level cross-check (optional, noisy):** `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed()` after `System.gc()` twice, read before the store is created and after the write loop.
- **Not observable directly:** none of significance at this tier. O2 is exact.

**B2e. Procedure.**
1. Copy the tree, then run the build in B2a.
2. Write `TestBackupStoreCap` with one `@Test` per (knob, workload). Each test does the following:
   1. Create a new temp local dir.
   2. Build the store, then `reinitialize()`.
   3. Run the write loop.
   4. Read O1.
   5. Call `reset()`.
   6. Read O1 again, then O2, O3 and O4.
   7. Iterate and assert that the count equals N.
   8. Print one line `knob,maxSize,O1,O2,O3,diskRecs,O4`.
   9. Delete the temp dir in `@After`.
3. Run `mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core test -Dtest=TestBackupStoreCap -Dmaven-surefire-plugin.argLine="-Xmx512m -XX:+UseParallelGC"`.
4. Collect the lines from `target/surefire-reports/TestBackupStoreCap-output.txt`.
5. For K3, assert that `new BackupStore(conf, tid)` throws `IOException`.

**B2f. Predictions** (stated before any run; derived by tracing the code with W1/W2 sizes).

| Knob (maxSize) | Workload | O3 records in memory | Disk records | O1 accounted after reset | O2 arrays retained | O4 spill file bytes |
|---|---|---|---|---|---|---|
| size 0 (default; maxSize 0) | W1 | 0 | 50,000 | 0 | 0 | 50,400,000 + 6 (2 EOF bytes + 4-byte CRC) |
| 65,536 | W1 | 64 | 49,936 | 64,530 | 65,536 | 50,335,488 + 6 |
| 1,048,576 | W1 | 1,040 | 48,960 | 1,048,338 | 1,048,576 | 49,351,680 + 6 |
| 4,194,304 | W1 | 4,160 | 45,840 | 4,193,352 | 4,194,304 | 46,206,720 + 6 |
| 8,388,608 | W1 | 8,321 | 41,679 | 8,387,730 | 8,390,512 | 42,012,432 + 6 |
| 16,777,216 | W1 | 16,643 | 33,357 | 16,776,450 | 16,781,024 | 33,623,856 + 6 |
| 67,108,864 | W1 | 50,000 | 0 | 50,400,882 | 51,380,224 (49 blocks) | no file |
| 8,388,608 | W2 (40 pairs) | 15 (8 small, 7 large) | 65 | 7,340,381 | 15,728,402 (≈ 1.875 × maxSize) | 34,603,289 + 6 |

How to read the table:
- **Relations:** O1 ≤ maxSize always. For W1 below the workload size, O2 − maxSize ≤ 4 KB, and O3 ≈ 1040 × maxSize/MiB. O2 is 0 at the default. W2 is the adversarial case: O2/maxSize ≈ 1.875.
- **K2, percent path:**
  - Logged maxSize equals `(int)(Runtime.getRuntime().maxMemory() * p)`, computed in the same JVM. For p = 0.01 at `-Xmx512m` that is about 5.0–5.4 MB.
  - O3 is about 1040 × floor(maxSize / 1048576) plus a partial tail block, and O2 ≤ maxSize + 4 KB.
  - At p = 0.02, O3 and O2 are about double those at 0.01.
- **K3:** `IOException` for both values.
- **O6:** the live-heap delta ≈ O2 + under 2 MB of bookkeeping.
- **Accepted slack:** the exact numbers may shift by one record if the IFile EOF/CRC trailer or vint sizes differ from the trace. A difference larger than that is a finding.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| O2 ≤ maxSize + ~4 KB for every W1 value below 50.4 MB; O3 and the disk records as tabled; iteration count = N | The claim holds: the limit caps the cache, and the overflow goes to disk |
| O2 grows with N past maxSize for W1 (e.g. at 4 MiB, O2 ≫ 4.2 MB, or no spill file) | The claim is refuted: the check does not cap memory |
| O3 and O2 do not change across K1 values | The claim is refuted: the knob does not govern usage |
| At size 0 / percent 0.0, O3 > 0 | Refuted for the default path |
| W2 O2/maxSize ≈ 1.87 | Confirms the accounting-overshoot path (a): the cap is approximate, bounded by 2 × maxSize |
| W2 O2/maxSize > 2 | The overshoot bound is wrong; the cap is weaker than traced |
| W2 O2/maxSize ≈ 1.0 | Path (a) traced wrongly (harmless) |
| 64 MiB case shows a spill file | Accounting is more conservative than traced (e.g. per-key leak); the claim is not refuted, but recheck |
| K2 logged maxSize ≠ `(int)(maxMemory × p)` | The derivation in A1 is wrong |

**B2h. Controls.**
- **Same workload, different knob:** the 64 MiB case shows the cache holding all 50,000 records when the limit is not reached. This is the positive control that the store does keep data in memory, and that the spill seen in the other cases comes from the limit.
- **Default case:** shows the disk path alone.
- **Iteration check:** iterating after `reset()` proves the records were stored rather than dropped.
- **Exact measurement:** O2 counts real arrays, so GC timing cannot explain the result.
- **Repeat:** run each test twice in fresh JVMs (`-Dsurefire.reuseForks=false`).

### B3. Cluster tier

**B3a. Environment and build.**
- **Host:** one Linux host, pseudo-distributed, running NameNode, DataNode, ResourceManager and NodeManager.
- **JDK and build:** JDK 8. On the copied tree (B2a), run `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`, then unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop`.
- **Environment:** set `HADOOP_LOG_DIR=/mydata/<run>/logs` and `HADOOP_HEAPSIZE_MAX=1g`.
- **`core-site.xml`:** `fs.defaultFS=hdfs://localhost:9000` and `hadoop.tmp.dir=/mydata/<run>/tmp`.
- **`hdfs-site.xml`:** `dfs.replication=1`, `dfs.namenode.name.dir=/mydata/<run>/nn` and `dfs.datanode.data.dir=/mydata/<run>/dn`.
- **`yarn-site.xml`:**
  - `yarn.nodemanager.aux-services=mapreduce_shuffle`
  - `yarn.nodemanager.resource.memory-mb=6144`
  - `yarn.scheduler.minimum-allocation-mb=512`
  - `yarn.nodemanager.local-dirs=/mydata/<run>/nm-local`
  - `yarn.nodemanager.log-dirs=/mydata/<run>/nm-logs`
  - `yarn.nodemanager.vmem-check-enabled=false`
  - `yarn.nodemanager.delete.debug-delay-sec=600`, so spill files can be listed after the job.
- **`mapred-site.xml`:**
  - `mapreduce.framework.name=yarn`
  - `yarn.app.mapreduce.am.env`, `mapreduce.map.env` and `mapreduce.reduce.env` all set to `HADOOP_MAPRED_HOME=/mydata/<run>/hadoop`
  - `mapreduce.reduce.memory.mb=1536`
  - `mapreduce.reduce.java.opts=-Xmx1024m -XX:+UseParallelGC -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:<LOG_DIR>/gc.log` (`<LOG_DIR>` is expanded by MapReduce)
  - `mapreduce.map.memory.mb=1024`
  - `mapreduce.job.reduces=1`
- **Disk:** `/mydata` is local disk with at least 5 GB free. Run D peaks at about 0.4 GB of map output, 0.4 GB of reduce merge and 0.4 GB of backup file.
- **Job jar:** `MarkResetCap.jar`, compiled against `share/hadoop/mapreduce/hadoop-mapreduce-client-core-3.4.2.jar` and `share/hadoop/common/hadoop-common-3.4.2.jar` with `javac -cp $(hadoop classpath)`. It contains:
  - **Mapper:** for each input line i, emits key `IntWritable(0)` and value `BytesWritable` of 1000 bytes filled from i. Raw value = 4 + 1000 = 1004 bytes, so the record length is L = 4 + 1004 + 1 + 3 = 1012 (1036 records per 1 MiB block).
  - **Reducer, mode `mark`:**
    1. `MarkableIterator<BytesWritable> it = new MarkableIterator<>(values.iterator()); it.mark();`
    2. Take heap sample P0, then pass 1: `while (it.hasNext()) it.next()`, counting n.
    3. Take sample P1. Each sample runs `System.gc()` twice, then logs `MemoryMXBean` heap used to stderr with a tag.
    4. `Thread.sleep(pauseSec × 1000)`, while `context.progress()` is called every 5 s.
    5. `it.reset()`, then pass 2, counting m. Assert m == n, then take sample P2.
  - **Reducer, mode `nomark`:** the same, without `mark`/`reset` (one pass only).
  - The mode and `pauseSec` (default 60) come from the job configuration.

**B3b. Knobs.** Each is passed per job with `-D` on `yarn jar`, so no restart is needed.
- **Run A:** `mapreduce.reduce.markreset.buffer.percent` ∈ {0.0 (default), 0.05, 0.10, 0.20}.
- **Run B:** percent 0.20 plus `mapreduce.reduce.markreset.buffer.size=67108864`, to show the absolute size overrides the percent (expected maxSize 64 MiB).
- **Run N:** mode `nomark`, percent 0.20, as a control.
- **Run C (optional, adversarial):** percent 0.10 with the secondary-sort job in B3c.

**B3c. Workload.**
- **Input:** `seq 1 400000 > /mydata/<run>/in.txt; hdfs dfs -put` it as one ~2.6 MB file, so there is a single map task.
- **Volume:** one key with 400,000 marked values, 400,000 × 1012 B ≈ 405 MB, more than the largest cap (≈ 0.20 × ~980 MB ≈ 196 MB). Every run therefore reaches the limit and spills.
- **Shuffle memory:** with `mapreduce.reduce.input.buffer.percent` at its default 0.0, the shuffle's in-memory map output is merged to disk before `reduce()` starts. Shuffle buffers are therefore not held during the pass-1 sample.
- **Duration:** about 2–4 min per run, including the 60 s pause.
- **Run C:**
  - Key `IntPair(group=0, seq=i)`, with a sort comparator on (group, seq), a grouping comparator and partitioner on group only (as in the shipped `SecondarySort` example), so values arrive in seq order.
  - Values alternate a `BytesWritable` of 10 bytes and one of 1,048,540 bytes. The large record (L = 8 + 1,048,544 + 1 + 4 = 1,048,557) cannot fit in a block beside a small one (L = 24), so it triggers the 2× path.
  - 300 pairs ≈ 315 MB.
  - The map side needs `mapreduce.task.io.sort.mb=256` and `mapreduce.map.memory.mb=1536` with `-Xmx1200m`.

**B3d. Observables and instruments.**
- **R1, the reduce task syslog line** `Created a new BackupStore with a memory of <maxSize>` gives the exact maxSize. Also `Created file: output/backup_0_0.out` appears when it spills. Find both with `yarn logs -applicationId <app> -log_files syslog | grep -E 'BackupStore|Created file'`.
- **R2, heap samples P0/P1/P2** from the task's stderr (`yarn logs ... -log_files stderr`). The key quantity is ΔH = P1 − P0, the live heap after full GC holding a full window.
- **R3, during the pause:**
  - Find the YarnChild pid with `jps -l | grep YarnChild` and pick the reduce attempt with `ps -o args`.
  - `jcmd <pid> GC.class_histogram | awk '$4=="[B"'` gives the total bytes of `byte[]` instances. Compare it across runs against the percent 0.0 run.
  - `jstat -gc <pid> 1000 10` shows old-gen occupancy.
- **R4, disk:** `find /mydata/<run>/nm-local/usercache -name 'backup_*.out*' -exec ls -l {} +` during the pause and after the job.
- **R5, GC log:** heap occupancy after the explicit full GCs.
- **Not directly observable:** the per-block split between memory and disk. It is inferred as memory records ≈ 400,000 − (backup file bytes / 1012).

**B3e. Procedure.**
1. Build the distribution and set the configuration (B3a).
2. `hdfs namenode -format`, then `start-dfs.sh` and `start-yarn.sh`. Check with `jps` that NN, DN, RM and NM are running.
3. Put the input into HDFS.
4. For each run in B3b, in this order: A 0.0, A 0.05, A 0.10, A 0.20, B, N, (C).
   1. Start the job: `yarn jar MarkResetCap.jar MarkResetCap -Dmapreduce.reduce.markreset.buffer.percent=<p> [-D...size=...] -Dmrc.mode=mark -Dmrc.pauseSec=60 /in /out-<run>`.
   2. When the reducer's stderr shows the P1 tag, take R3 and R4 within the pause, e.g. from a script that tails the container's stderr file under `/mydata/<run>/nm-logs/<app>/<container>/stderr`.
   3. After the job finishes, collect R1, R2 and R5 and check that the job reports m == n.
   4. `hdfs dfs -rm -r /out-<run>`.
5. Repeat runs A 0.10 and A 0.20 once more for spread.
6. Stop and check:
   1. `stop-yarn.sh`, then `stop-dfs.sh`.
   2. `jps` shows no NameNode, DataNode, ResourceManager, NodeManager or YarnChild.

**B3f. Predictions** (stated before any run). Let M = R1's logged maxSize. With `-Xmx1024m` under ParallelGC, `maxMemory` is roughly 950–1024 MiB, so M ≈ 0.05/0.10/0.20 × that.

| Run | M | ΔH = P1 − P0 | Backup file bytes (R4) | Records in memory |
|---|---|---|---|---|
| A 0.0 | 0 | ≈ 0 (< 5 MB) | ≈ 404,800,006 (400,000 × 1012 + 6) | 0 |
| A 0.05 | ≈ 50 MB | ≈ M ± 5 MB | ≈ 404.8 MB − M | ≈ 1036 × M/MiB |
| A 0.10 | ≈ 100 MB | ≈ M ± 5 MB | ≈ 404.8 MB − M | ≈ 1036 × M/MiB |
| A 0.20 | ≈ 200 MB | ≈ M ± 5 MB | ≈ 404.8 MB − M | ≈ 1036 × M/MiB |
| B | 67,108,864 exactly | ≈ 64 MiB ± 5 MB | ≈ 404.8 MB − 64 MiB | ≈ 66,300 |
| N | — (no store created; no BackupStore log line) | ≈ 0 | none | — |
| C (0.10) | ≈ 100 MB | ≈ 1.8–2.0 × M | the remainder of ≈ 315 MB | about M / 1 MiB pairs |

Further relations:
- ΔH tracks M linearly across A: ΔH(0.20) / ΔH(0.10) ≈ 2.
- The R3 `[B` total minus the A 0.0 run's total ≈ M.
- The `.crc` files add about 0.8% (4 bytes per 512) to R4.
- The claim is wrong if ΔH in A 0.05/0.10/0.20 exceeds M by much more than one block (> 10 MB), if ΔH does not scale with M, if A 0.0 shows ΔH ≈ the workload size, or if C shows ΔH > 2.05 × M.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| ΔH ≈ M for each A run; backup file ≈ 404.8 MB − M; A 0.0 has ΔH ≈ 0 and the full file | The claim holds at the cluster level: the key caps the cache's heap; the overflow goes to local disk |
| ΔH ≫ M (approaching 405 MB) or the reduce task OOMs at 0.05 | The claim is refuted: the cache is not capped |
| ΔH is the same across A values | The claim is refuted: the key does not govern usage |
| B gives M = 64 MiB regardless of percent | `buffer.size` override confirmed |
| N shows ΔH ≈ 0 while A 0.20 shows ΔH ≈ 200 MB | Positive control: the heap delta is due to the BackupStore, not the shuffle or the reducer |
| C ΔH ≈ 1.8–2.0 × M | Overshoot path (a) confirmed in a real task: the cap is approximate |
| C ΔH > 2.05 × M | The overshoot bound is wrong |
| R1 missing | Mark was never reached (the job is wrong); not confirmed |

**B3h. Controls.**
- **A 0.0:** shows the disk path alone and gives the heap baseline.
- **N (`nomark`):** separates the BackupStore from other reduce-side heap.
- **Run order and repeats:** runs go from small to large percent and are repeated, which rules out drift.
- **No shuffle memory retained:** `mapreduce.reduce.input.buffer.percent=0.0` stays at its default, so no map outputs are kept in memory during `reduce()`.
- **Same JVM settings:** every run uses the same `-Xmx` and GC.
- **Measured state:** samples are taken after explicit full GCs, so ΔH is live data, not garbage.
- **Correctness:** the m == n assertion proves the records were kept, not dropped.

**B4. Risks and cleanup.**
- **Disk:**
  - The unit tier writes up to about 50 MB per test into its temp dir.
  - The cluster tier peaks at about 1.5 GB per run under `/mydata/<run>`. Keep `debug-delay-sec` at 600 so files can be listed, then wait or delete them.
  - Never use shared storage or the shared source tree.
- **Ports:** 9000, 9870, 9864/9866/9867, 8030–8033, 8088, 8040/8042 and 13562. Check they are free first (`ss -ltn`).
- **Memory:** about 1.5 GB for the reduce container plus about 1.5 GB for the AM and map, and about 3 GB for the daemons. The host needs about 8 GB free.
- **Cleanup:**
  1. `stop-yarn.sh`, then `stop-dfs.sh`.
  2. `jps` shows no Hadoop JVMs; `pkill -f YarnChild` if any task is left.
  3. `rm -rf /mydata/<run>/{tmp,nn,dn,nm-local,nm-logs}` once the readings are copied.
  4. For the unit tier, the `@After` hook deletes the temp dirs. Check that surefire forks have exited (`jps`).

## C. Sources read

- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java (507-517, 1225-1233)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml (324-380, 596-602, 2076-2080)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/util/ConfigUtil.java (255-256)
- hadoop-common-project/hadoop-common/src/site/markdown/DeprecatedProperties.md (132)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/ReduceContextImpl.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/Reducer.java (165-180)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MarkableIterator.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/InMemoryReader.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IFile.java (Writer constructor and close, Reader constructor and close)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/Merger.java (Segment, 218-380)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/main/java/org/apache/hadoop/mapred/YarnChild.java (279-282)
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/mapreduce/TestValueIterReset.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/DataOutputBuffer.java (58-93)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/WritableUtils.java (400-412)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/LocalDirAllocator.java (82, 429-530)
- hadoop-project/pom.xml (187)
- BUILDING.txt
- https://issues.apache.org/jira/browse/HADOOP-5494 (cited from the source comment)
- https://docs.oracle.com/javase/8/docs/api/java/lang/Runtime.html#maxMemory--

## D. Stage-4 feedback

none yet
