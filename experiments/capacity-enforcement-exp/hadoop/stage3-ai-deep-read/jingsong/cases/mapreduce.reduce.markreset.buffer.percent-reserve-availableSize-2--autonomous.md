# mapreduce.reduce.markreset.buffer.percent — `BackupStore.java:611` — verification solution  <!-- file: cases/mapreduce.reduce.markreset.buffer.percent-reserve-availableSize-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BackupStore.java:611`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java#L611) — `if (availableSize < minSize)` in `BackupStore.BackupRamManager.reserve(int requestedSize, int minSize)` |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — the check refuses a new in-memory block once the budget derived from `mapreduce.reduce.markreset.buffer.percent` (or the absolute override `mapreduce.reduce.markreset.buffer.size`) is spent, and every later value goes to a spill file on local disk, so the heap held by the mark-reset cache stops growing at a level set by the knob. The cap is loose: the unused tail of each closed 1 MiB block is given back to the budget (`BackupStore.java:506`) while the whole array stays referenced (`InMemoryReader.java:51`), so retained heap can reach about 2× the configured size for values just over half a block. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `mapreduce.reduce.markreset.buffer.percent` (primary, the documented knob). Kind: configuration key (per-job). Declared as `MRJobConfig.REDUCE_MARKRESET_BUFFER_PERCENT` at [`MRJobConfig.java:507`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java#L507); `mapred-default.xml` entry at [`mapred-default.xml:597`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml#L597) with value `0.0`. Deprecated alias `mapred.job.reduce.markreset.buffer.percent` (`ConfigUtil.java:255-256`, `DeprecatedProperties.md:132`).
- Unit: fraction of the task JVM's `Runtime.getRuntime().maxMemory()` (0.0–1.0; outside that range the `BackupStore` constructor throws, `BackupStore.java:97-100`).
- Default: Java default `0f` at the read site (`BackupStore.java:94-95`) and `0.0` in `mapred-default.xml:598`; they agree, so the default budget is 0 bytes.
- Second source: `mapreduce.reduce.markreset.buffer.size` (`MRJobConfig.REDUCE_MARKRESET_BUFFER_SIZE`, [`MRJobConfig.java:509`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java#L509)), bytes, no `mapred-default.xml` entry, Java default 0; when > 0 it replaces the percent-derived size (`BackupStore.java:105-109`).
- Derived value: `maxSize = (int) min(maxMemory * percent, Integer.MAX_VALUE)` (`BackupStore.java:102-103`), or `buffer.size` if > 0. This becomes `BackupRamManager.maxSize` and the initial `availableSize` (`BackupStore.java:111`, `:390`, `:590-592`). It is logged: `Created a new BackupStore with a memory of <maxSize>` (`BackupStore.java:117`).
- How set: `mapred-site.xml` or, per job, `-D` / `job.getConfiguration()`; read when the task JVM creates the `BackupStore` (first `mark()` on a values iterator, `ReduceContextImpl.java:255-258`), so a change applies to the next job, no daemon restart.
- Process: the reduce task JVM (`YarnChild` running `ReduceTask`), and also a map task JVM when a new-API combiner uses mark/reset (`Task.java:1906` builds a `ReduceContextImpl` for the combiner).

**A2. What it caps.** Heap of the reduce (or combiner) task JVM used by the mark-reset values cache of `ReduceContextImpl.ValueIterator` / `MarkableIterator`: the byte arrays of `MemoryCache` blocks (`DataOutputBuffer(allocatedSize)`, `BackupStore.java:422`) that hold the serialized key/value pairs written after `mark()`. The quantity compared is the remaining budget `availableSize` (= `maxSize` − bytes currently reserved) against `minSize`, the bytes needed for the next record plus 18 bytes of EOF-marker room (`BackupStore.java:446-448`). It does not cap disk: values that do not fit go to an unbounded spill file.

**A3. Mechanism.**
1. `ValueIterator.mark()` creates the `BackupStore` on first use and calls `reinitialize()` (`ReduceContextImpl.java:255-262`), which clears segments and resets the budget to `maxSize` (`BackupStore.java:304-309`, `:405-408`, `:626-628`) and asks for a first block of `defaultBlockSize` = min(1 MiB, `maxSize`) (`BackupStore.java:387-393`, `:409-410`).
2. Every value read after the mark is copied in: `ReduceContextImpl.nextKeyValue()` → `backupStore.write(nextKey, nextVal)` (`ReduceContextImpl.java:151-153`); the already-read current record is copied through `getOutputStream(requestedSize)` (`ReduceContextImpl.java:267-273`, `BackupStore.java:337-344`).
3. `BackupStore.write` (`BackupStore.java:128-144`): once the file cache is active everything goes to disk; otherwise `memCache.reserveSpace(key, value)` (`:453-462`) → `reserveSpace(length)` (`:435-451`). If the current block has room (`blockSize - usedSize >= length + 18`, `:437`) the record is appended to the block. If not, the block is closed into an in-memory segment (`createInMemorySegment`, `:488-516`) and a new block of `max(length+18, defaultBlockSize)` with minimum `length+18` is requested via `createNewMemoryBlock` → `ramManager.reserve(requestedSize, minSize)` (`:415-426`).
4. **The check**: [`BackupStore.java:611`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java#L611) `if (availableSize < minSize)`:
   - true → returns 0 (`:612-614`); `createNewMemoryBlock` sets `dataOut = null`, `blockSize = 0` (`:418-420`); `reserveSpace` returns false (`:450`); `write` calls `fileCache.activate()` and writes the record to `output/backup_<id>_<n>.out` under `mapreduce.cluster.local.dir` (`:141-142`, `:554-557`, `:570-582`). All further values of this mark go to disk (`:133-136`).
   - false → `reserve(requestedSize)` takes `min(requestedSize, availableSize)` from the budget (`:600-608`) and a new `byte[allocatedSize]` is allocated (`:422`).
5. Release: on closing a block, `usedSize += 18` and `ramManager.unreserve(blockSize - usedSize)` (`:504-506`) — the unused tail is returned to the budget, but the `InMemoryReader` built on `dataOut.getData()` keeps the full array (`:508-511`, `InMemoryReader.java:44-53`). The budget is fully restored only by `reinitialize()` at the next `mark()` outside reset, `clearMark()`, or at the next key (`Reducer.java:173-176` → `ReduceContextImpl.java:316-322`).
6. Overshoot path: because of step 5, the arrays held (`Σ blockSize`) exceed the bytes reserved (`Σ usedSize ≤ maxSize`) by the per-block tails. With values whose record size `r` is slightly more than half a block (r > (1 MiB − 18)/2 = 524,279 bytes), every 1 MiB block holds one record and nearly half of it is unreserved, so retained heap approaches 2 × `maxSize` (worked numbers in B2f). For small records the tail is < r + 18 per block, so retained ≈ `maxSize`. For records ≥ 1 MiB the block is sized exactly `r + 18` (`:446`) and there is no gap.
7. Under-use path (not an overshoot): `BackupStore.mark()` during reset mode drops leading segments with `s.close()` but never calls `memCache.unreserve` (`BackupStore.java:161-172`; compare `clearSegmentList`, `:369-378`), so budget leaks until the next `reinitialize()` and later values spill to disk earlier than the knob implies.
8. Default `0.0` / size 0 → `maxSize = 0` → `defaultBlockSize = 0`, `reserve(0,0)` returns 0 because `availableSize == 0` (`:601-603`), so with the defaults every marked value goes to disk.
9. Edge: `getOutputStream` reserves `requestedSize` computed from raw lengths but writes re-serialized key/value (`ReduceContextImpl.java:337-352`); a serializer that emits more bytes than the raw form would grow the `DataOutputBuffer` past `blockSize` (its `Buffer` extends `java.io.ByteArrayOutputStream`, which reallocates on overflow; `DataOutputBuffer.java:58-60`, `:93-95`). Not exercised with standard Writables.

**A4. Other consumers.**
- Disk: the file cache has no limit; `LocalDirAllocator.getLocalPathForWrite(..., -1, conf)` (`BackupStore.java:577-578`) only picks a directory. Spill bytes = marked bytes not held in memory. Disk segments are created with `preserve = true` (`:562`), so `close()` does not delete them (`Merger.java:352-357`); the file name is reused after `reinitialize()` (spill number back to 0, `:548-552`), and the files go away with the container's app cache.
- Heap in the same reduce JVM outside this budget: shuffle buffers (`mapreduce.reduce.shuffle.input.buffer.percent` 0.70, released before reduce when `mapreduce.reduce.input.buffer.percent` = 0.0, `mapred-default.xml:514-524`), merge reader buffers, the deserialized key/value objects, user reducer state.
- A combiner using mark/reset gets its own `BackupStore` in the map JVM (`Task.java:1906`).

**A5. Evidence beyond the source.**
- `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/mapreduce/TestValueIterReset.java:536` — the only test, sets `buffer.size` = 128 to force memory→disk transitions; checks correctness only, not memory.
- `hadoop-common-project/hadoop-common/src/site/markdown/DeprecatedProperties.md:132` — old key name.
- `BackupStore.java:268` cites HADOOP-5494 (memory→disk segment switch corruption); not used for the claim.

## B. Verification solution

**B1. Claim under test.** When a reducer marks a values iterator and iterates a key group larger than the budget, the heap held by the mark-reset cache rises with `mapreduce.reduce.markreset.buffer.percent` / `.size` and then stops, the rest of the group going to `backup_*.out` on local disk; for small values the held heap is ≈ the configured size (within one block), and for ≈ 512 KiB values it is ≈ 2 × the configured size while the budget's own accounting stays ≤ the configured size. The claim is wrong if the held heap keeps growing with the group size (no spill), or if it does not change with the knob.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8, Maven 3.3+. Copy the tree to local disk first: `rsync -a <source>/ $W/hadoop-src/` (`$W` = a local work dir, e.g. `/mydata/<run>/unit`).
- Module `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core`. New test `src/test/java/org/apache/hadoop/mapred/TestBackupStoreCap.java` in the copy (package `org.apache.hadoop.mapred`, so `TaskAttemptID` resolves to `org.apache.hadoop.mapred.TaskAttemptID` as the cast at `BackupStore.java:510` requires, and the test can read the package-private `segmentList`, `Segment.inMemory()`, `Segment.getReader()` and the protected `IFile.Reader.buffer`; private `memCache`, `MemoryCache.ramManager`, `BackupRamManager.availableSize/maxSize` via reflection).
- Build: `cd $W/hadoop-src && mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core -am install -DskipTests -Dmaven.javadoc.skip=true`.
- Run: `mvn -pl hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core test -Dtest=TestBackupStoreCap`. Surefire runs with `-Xmx2048m` (`hadoop-project/pom.xml:187`), enough for ≤ 140 MB retained.

Test core (one call per knob × shape):

```java
static void run(String label, int sizeBytes, float percent, int keyLen, int valLen, int n)
    throws Exception {
  File dir = new File(System.getProperty("test.build.data", "target/test-dir"), "bscap-" + label);
  FileUtil.fullyDelete(dir); dir.mkdirs();
  Configuration conf = new Configuration();
  if (sizeBytes > 0) conf.setInt(MRJobConfig.REDUCE_MARKRESET_BUFFER_SIZE, sizeBytes);
  conf.setFloat(MRJobConfig.REDUCE_MARKRESET_BUFFER_PERCENT, percent);
  conf.set(MRConfig.LOCAL_DIR, dir.getAbsolutePath());
  TaskAttemptID tid = new TaskAttemptID("cap", 1, TaskType.REDUCE, 0, 0);
  long heap0 = usedAfterGc();
  BackupStore<BytesWritable, BytesWritable> bs = new BackupStore<>(conf, tid);
  bs.reinitialize();                               // what ValueIterator.mark() does
  byte[] k = new byte[keyLen], v = new byte[valLen];
  DataInputBuffer kb = new DataInputBuffer(), vb = new DataInputBuffer();
  for (int i = 0; i < n; i++) { kb.reset(k, 0, keyLen); vb.reset(v, 0, valLen); bs.write(kb, vb); }
  bs.reset();                                      // closes last block / spill file into a segment
  long heap1 = usedAfterGc();
  // operand side
  Object mc = field(bs, "memCache"); Object rm = field(mc, "ramManager");
  int maxSize = (Integer) field(rm, "maxSize"), avail = (Integer) field(rm, "availableSize");
  // actual arrays held by in-memory segments (identity set, no double count)
  Set<byte[]> arrays = Collections.newSetFromMap(new IdentityHashMap<>());
  int memSegs = 0; long memSegLen = 0;
  for (Merger.Segment<BytesWritable, BytesWritable> s : bs.segmentList)
    if (s.inMemory()) { memSegs++; memSegLen += s.getLength(); arrays.add(s.getReader().buffer); }
  long retained = 0; for (byte[] a : arrays) retained += a.length;
  long disk = 0;
  try (java.util.stream.Stream<java.nio.file.Path> st = java.nio.file.Files.walk(dir.toPath())) {
    for (java.nio.file.Path f : (Iterable<java.nio.file.Path>) st::iterator)
      if (f.getFileName().toString().matches("backup_.*\\.out")) disk += java.nio.file.Files.size(f);
  }
  long count = 0; while (bs.hasNext()) { bs.next(); count++; }   // all n readable back
  System.out.printf("CAP %s maxSize=%d accounted=%d retained=%d memSegs=%d memSegLen=%d disk=%d heapDelta=%d count=%d%n",
      label, maxSize, maxSize - avail, retained, memSegs, memSegLen, disk, heap1 - heap0, count);
}
```

(`usedAfterGc()` = three `System.gc()` calls then `MemoryMXBean.getHeapMemoryUsage().getUsed()`; `field()` = `getDeclaredField` + `setAccessible(true)`, walking superclasses. `memSegLen / (r + 18)` ≈ in-memory record count for one-record blocks.)

**B2b. Knobs.** `mapreduce.reduce.markreset.buffer.size` ∈ {0 (default, percent 0.0), 4 MiB = 4,194,304, 16 MiB = 16,777,216, 64 MiB = 67,108,864}, set in the test `Configuration`. Plus one percent run: `buffer.percent = 0.03125`, size unset (maxSize = 0.03125 × `maxMemory()` of the surefire JVM, read from reflection/log). Values chosen so that the budget spans 1–64 blocks and the 2× effect grows with block count.

Record shapes (record size r = key + value + vint(key) + vint(value), `BackupStore.java:458-460`):
- small: key 4 B, value 1,019 B → r = 4 + 1,019 + 1 + 3 = 1,027; n = 131,072 (134.6 MB total).
- half-block: key 4 B, value 524,291 B → r = 4 + 524,291 + 1 + 4 = 524,300 (> 524,279); n = 300 (157.3 MB).
- large: key 4 B, value 2,000,000 B → r = 2,000,009; n = 80 (160.0 MB).

**B2c. Workload.** n records written after one `reinitialize()`, as in a single marked key group. Each total (≥ 134 MB) is more than twice the largest budget (64 MiB), so the check at `:611` must fire for every non-zero knob.

**B2d. Observables and instruments.** Printed `CAP` line: `maxSize` and `accounted` (= maxSize − availableSize, the check's own operand side), `retained` (sum of distinct `byte[]` lengths held by in-memory segments — the actual heap of the cache), `memSegs`/`memSegLen`, `disk` (bytes in `backup_*.out`, excluding `.crc`), `heapDelta` (coarse cross-check, ±a few MB), `count` (must equal n). Also `LOG.info` line `Created a new BackupStore with a memory of` and `Created file:` (spill started). Not observable directly: per-block tails (inferred from retained − accounted).

**B2e. Procedure.**
1. Copy tree, add the test, build (B2a).
2. Run `mvn ... test -Dtest=TestBackupStoreCap`; the test calls `run()` for each knob × shape (12 runs) plus the percent run, each in its own local dir, deleting the dir after reading it.
3. Collect `CAP` lines from `target/surefire-reports/org.apache.hadoop.mapred.TestBackupStoreCap-output.txt`.
4. Delete `$W/hadoop-src/.../target/test-dir/bscap-*`.

**B2f. Predictions.** (Exact from the code arithmetic; `heapDelta` ≈ `retained` ± 4 MB; `count` = n in every run.)

| size | shape | in-mem records | retained (B) | accounted (B) | retained / size | disk ≈ (B) |
|---|---|---|---|---|---|---|
| 0 | any | 0 | 0 | 0 | — | n × r (all) |
| 4 MiB | small | 4,083 | 4,198,376 | 4,193,331 | 1.001 | 126,989 × 1,027 |
| 16 MiB | small | 16,335 | 16,793,504 | 16,776,351 | 1.001 | 114,737 × 1,027 |
| 64 MiB | small | 65,343 | 67,174,016 | 67,108,431 | 1.001 | 65,729 × 1,027 = 67.5 MB |
| 4 MiB | half | 7 | 7,339,852 | 3,670,226 | 1.750 | 293 × 524,300 |
| 16 MiB | half | 31 | 32,504,956 | 16,253,858 | 1.937 | 269 × 524,300 |
| 64 MiB | half | 127 | 133,165,372 | 66,588,386 | 1.984 | 173 × 524,300 = 90.7 MB |
| 4 MiB | large | 2 | 4,000,054 | 4,000,054 | 0.954 | 78 × 2,000,009 |
| 16 MiB | large | 8 | 16,000,216 | 16,000,216 | 0.954 | 72 × 2,000,009 |
| 64 MiB | large | 33 | 66,000,891 | 66,000,891 | 0.983 | 47 × 2,000,009 |

Disk files also carry a few bytes of IFile EOF/checksum. Percent run (small shape): `retained` ≈ maxSize × 1.001, `accounted` ≤ maxSize, where maxSize = ⌊0.03125 × maxMemory⌋ as logged.
Relations: `accounted ≤ maxSize` always; `retained` monotone in size and independent of n once n×r > 2×size.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| retained and in-memory records match the table; disk > 0 for all non-zero sizes | Claim confirmed: the check caps the cache and overflows to disk, with the predicted ≈2× gap for half-block records |
| retained ≈ size (≤ 1.01×) for half-block records | The cap is tighter than traced (tail not retained); positive estimate stands, A3 step 6 wrong |
| retained grows with n (e.g. ≈ n × r) or disk = 0 at size < n×r | Claim refuted: the check does not cap usage |
| retained the same for all sizes | Claim refuted: usage does not follow the knob |
| accounted > maxSize | Accounting broken; claim refuted as stated |
| count ≠ n | Run invalid (data loss); not a cap result |
| size 0 shows retained > 0 | Default does not disable the cache; A3 step 8 wrong |

**B2h. Controls.** Size 0 (no cache) vs. non-zero sizes on the same workload isolates the knob. The large shape (no tail gap) shows the 2× effect comes from tails, not from measurement. `heapDelta` cross-checks the reflection sum against the JVM's own heap figure. `count = n` rules out records being dropped instead of spilled.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host, ≥ 8 GB free RAM, ≥ 20 GB free local disk; pseudo-distributed HDFS (NameNode, DataNode) + YARN (ResourceManager, NodeManager). JDK 8.
- Build a distribution from a local copy: `cd $W/hadoop-src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`; use `hadoop-dist/target/hadoop-3.4.2` as `$HADOOP_HOME`, with `HADOOP_CONF_DIR=$R/conf` and `HADOOP_LOG_DIR=$R/logs` (`$R` = local run dir, e.g. `/mydata/<run>/cluster`).
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$R/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=$R/nn`, `dfs.datanode.data.dir=$R/dn`.
- `yarn-site.xml`: `yarn.nodemanager.aux-services=mapreduce_shuffle`, `yarn.nodemanager.resource.memory-mb=6144`, `yarn.scheduler.maximum-allocation-mb=4096`, `yarn.nodemanager.vmem-check-enabled=false`, `yarn.nodemanager.local-dirs=$R/nm-local`, `yarn.nodemanager.log-dirs=$R/nm-logs`, `yarn.nodemanager.delete.debug-delay-sec=600` (keeps container logs/local dirs for inspection).
- `mapred-site.xml`: `mapreduce.framework.name=yarn`, `yarn.app.mapreduce.am.env`, `mapreduce.map.env`, `mapreduce.reduce.env` = `HADOOP_MAPRED_HOME=$HADOOP_HOME`.
- Job jar `markcap.jar` (compiled with `javac -cp $(hadoop classpath) MarkCap.java && jar cf markcap.jar MarkCap*.class`):
  - Mapper (`Mapper<LongWritable,Text,IntWritable,BytesWritable>`): in `cleanup()` emits `markcap.n` records `(IntWritable(0), BytesWritable(new byte[markcap.vlen]))`. Raw value length = vlen + 4 (`BytesWritable.java:192-195`), key raw length 4.
  - Reducer (`Reducer<IntWritable,BytesWritable,IntWritable,LongWritable>`): `pause("A")`; `MarkableIterator it = new MarkableIterator(values.iterator()); it.mark();` iterate all (c1); `pause("B")`; `it.reset(); pause("C")`; iterate all (c2); write `(key, c1*1_000_000 + c2)`. `pause(tag)` prints `MARKCAP-PAUSE-<tag>` to stderr, then sleeps `markcap.pause.ms` (default 60000) calling `context.progress()`.
  - Input: one HDFS file with one line (one map task).

**B3b. Knobs.** Per job on the command line (no restart): `-D mapreduce.reduce.markreset.buffer.size=<S>` or `-D mapreduce.reduce.markreset.buffer.percent=<p>`.

| Run | knob | shape (vlen, n) |
|---|---|---|
| C0 | defaults (percent 0.0, size unset) | small (1,015, 131,072) |
| C1 | size 67,108,864 | small (1,015, 131,072) |
| C2 | size 67,108,864 | half (524,287, 300) |
| C3 | size 16,777,216 | half (524,287, 300) |
| C4 | percent 0.0625, size unset | small (1,015, 131,072) |
| C5 | size 67,108,864 | small (1,015, 30,000) — group fits, no spill |

vlen 1,015 → raw value 1,019 → r = 1,027; vlen 524,287 → raw value 524,291 → r = 524,300 (same shapes as B2).
Fixed job settings: `-D mapreduce.job.reduces=1 -D mapreduce.reduce.memory.mb=2048 -D mapreduce.reduce.java.opts=-Xmx1536m -D mapreduce.map.memory.mb=1536 -D mapreduce.map.java.opts=-Xmx1024m -D mapreduce.task.io.sort.mb=256 -D mapreduce.map.output.compress=false`.

**B3c. Workload.** `yarn jar markcap.jar MarkCap <knobs> -D markcap.n=<n> -D markcap.vlen=<vlen> /markcap/in /markcap/out-<run>`. One key group of 134.6 MB (small) or 157.3 MB (half) — both > 2 × 64 MiB, so the cache must fill and spill (except C5: 30.8 MB < 64 MiB). Duration ≈ 5 min per run including three 60 s pauses.

**B3d. Observables and instruments.**
- Reduce JVM pid: `jps -l | grep YarnChild` during the reduce (single YarnChild then); confirm with `ps -o args` showing `attempt_..._r_000000_0`.
- Live `byte[]` bytes: `jcmd $PID GC.class_histogram | awk '$4=="[B"{print $3}'` at each pause (histogram forces a full GC, live objects only). Retained cache ≈ `[B`(B) − `[B`(A).
- Heap after GC: `jstat -gc $PID` (OU + EU + S0U + S1U) at each pause; `VmRSS` from `/proc/$PID/status` (context only).
- maxSize: reduce container `syslog` line `Created a new BackupStore with a memory of <n>` (`$R/nm-logs/application_*/container_*_000003/syslog` or `yarn logs -applicationId`); spill start: `Created file: output/backup_0_0.out`.
- Disk at pause C (spill writer closed by `reset()`): `find $R/nm-local -name 'backup_*.out' -printf '%s\n' | paste -sd+ | bc`.
- Correctness: output value = n × 1,000,001.
- Pause detection: poll `$R/nm-logs/.../stderr` for `MARKCAP-PAUSE-<tag>`.
Not observable directly: which arrays belong to the cache (inferred by the A→B delta).

**B3e. Procedure.**
1. Build distribution, write configs (B3a), `hdfs namenode -format`, `start-dfs.sh`, `start-yarn.sh`; `hdfs dfs -mkdir -p /markcap/in && echo x | hdfs dfs -put - /markcap/in/one.txt`.
2. For each run C0–C5: launch the job in the background; when `MARKCAP-PAUSE-A` appears, take histogram + jstat; same at B; at C also run the `find` for disk; after completion, record `maxSize` from syslog and check the output count. `hdfs dfs -rm -r /markcap/out-<run>` afterwards.
3. Wait for the app's local dirs to clear (or remove `$R/nm-local/usercache/*/appcache/*` after the run) before the next run.
4. Cleanup (B4).

**B3f. Predictions.** (Δ = `[B`(B) − `[B`(A), ± 8 MB for IFile/merge buffers and GC timing.)

| Run | maxSize (log) | Δ heap | disk at C |
|---|---|---|---|
| C0 | 0 | ≈ 0 | ≈ 134.6 MB (all 131,072 records) |
| C1 | 67,108,864 | ≈ 67.2 MB | ≈ 67.5 MB (65,729 records) |
| C2 | 67,108,864 | ≈ 133.2 MB (≈ 1.98 × S) | ≈ 90.7 MB (173 records) |
| C3 | 16,777,216 | ≈ 32.5 MB (≈ 1.94 × S) | ≈ 141.0 MB (269 records) |
| C4 | ⌊0.0625 × maxMemory(-Xmx1536m)⌋, ≈ 85–96 MB | ≈ maxSize × 1.001 | ≈ 134.6 MB − maxSize |
| C5 | 67,108,864 | ≈ 30.8 MB | 0 (no `backup_*.out`) |

Relations: Δ(C1) ≈ Δ(C5)+36 MB only up to S, i.e. C1 stops at ≈ S although its group is 4.4× larger; Δ(C2)/Δ(C3) ≈ 4.1; all outputs = n × 1,000,001.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Δ follows the table; disk > 0 exactly when group > budget | Claim confirmed in real daemons |
| Δ(C1) ≈ group size (≈ 135 MB) or no spill file in C1–C4 | Claim refuted: the knob does not cap the cache |
| Δ(C1) ≈ Δ(C0) | Claim refuted: knob has no effect on held heap (or cache not used) |
| Δ(C2) ≈ 67 MB (≈ S) | Cap tighter than traced; positive stands, tail-retention analysis wrong |
| Δ(C5) not ≈ 30.8 MB | Instrument does not see the cache; reading of C1–C4 not valid |
| Reduce OOM or output count wrong | Run invalid; rerun with larger -Xmx |

**B3h. Controls.** C0 (budget 0) is the same workload with no cache; C5 is a positive control showing the instrument sees cache growth (Δ follows group size when the group fits); C1 vs. C5 shows the stop is due to the budget, not the workload. Single reducer and single key avoid mixing several `BackupStore`s; baseline A is taken inside the same reduce call after shuffle buffers are released.

**B4. Risks and cleanup.**
- Unit tier: ≤ 160 MB per run in `target/test-dir`; delete after each run; build only in the local copy.
- Cluster tier: ≤ 1 GB HDFS data, ≤ 0.5 GB spill under `$R/nm-local` per run; all under `$R` on local disk. Ports 9000, 9870, 9864-9867, 8088, 8030-8033, 8040-8042, 13562 — check they are free (`ss -ltn`) or move them. Container memory ≤ 2 GB reduce + 1.5 GB map + 1.5 GB AM within 6 GB.
- Cleanup: `stop-yarn.sh; stop-dfs.sh; mapred --daemon stop historyserver` (if started), `jps` must list no `NameNode`, `DataNode`, `ResourceManager`, `NodeManager`, `YarnChild`, `MRAppMaster`; kill any leftover by pid; `rm -rf $R`.

## C. Sources read

- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/BackupStore.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/util/ConfigUtil.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/ReduceContextImpl.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/Reducer.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MarkableIterator.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/InMemoryReader.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/Merger.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/IFile.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/Task.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/ReduceTask.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/TaskAttemptID.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/JobContext.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRConfig.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/main/java/org/apache/hadoop/mapred/YarnChild.java
- hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/mapreduce/TestValueIterReset.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/DataOutputBuffer.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/WritableUtils.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/BytesWritable.java
- hadoop-common-project/hadoop-common/src/site/markdown/DeprecatedProperties.md
- hadoop-project/pom.xml

## D. Stage-4 feedback

none yet
