# Stage 4 — notes from the closed Hadoop cases (Jingsong's share)

Read after the protocol, [`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md), and the node
setup, [`environment.md`](environment.md). Yang's [`../yang/case-notes.md`](../yang/case-notes.md) applies too. One row per closed case.

| Case (stem) | Node | Verdict | Outcome class | Results |
|---|---|---|---|---|
| `DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous` | pc41 | unit Confirmed, cluster Confirmed — does not cap | true negative | [results](results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md) |
| `RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous` | pc39 | unit Confirmed, cluster (no-daemon `hadoop jar`) Confirmed — caps | true positive | [results](results/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md) |
| `fs.s3a.prefetch.block.count-acquireHelper-size--autonomous` | pc39 | unit Not confirmed, cluster Not confirmed (frozen heap bounds missed; buffer count capped exactly) | undetermined | [results](results/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md) |
| `fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous` | pc29 | unit Confirmed, cluster Confirmed — caps | true positive | [results](results/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md) |
| `MAX_KEY_SIZE-write-limit--autonomous` | pc41 | unit Confirmed — does not cap; cluster n/a | true negative | [results](results/MAX_KEY_SIZE-write-limit--autonomous.md) |

## Open calls for Jingsong (batch 1)

- `MAX_KEY_SIZE-write-limit`: one retained-heap reading (C = L = 16 MiB row) came out at −6872 B against a
  C ± 1 MiB prediction. The agent judged it an instrument artefact (the previous row's stream counted in the
  "before" reading, reproduced with no writes) and kept Confirmed. A strict reading of amendment A6 would make
  the unit tier Not confirmed and the case undetermined (results §8).
- `fs.s3a.prefetch.block.count`: the mechanism caps exactly (`count + 1` buffers, disallow branch observed), but
  the frozen heap tolerances missed: unit from a shared-JVM baseline, cluster from a transient 32 MiB array per
  block (JDK 8 `CRC32.update` on a read-only buffer, `BufferData.getChecksum`). Undetermined unless overruled.
- `fs.s3a.prefetch.max.blocks.count`: 2 of 3 N = 1 runs had 66 cache puts against 63–64 predicted (reader retry,
  A9); no conclusions row uses it; `selfcheck.py` flags it (stricter than the table).

## Findings beyond the verdicts (upstream / doc candidates; check JIRA first)

- S3A `SingleFilePerBlockCache` at `fs.s3a.prefetch.max.blocks.count=1`: two puts at the same seek can evict a
  block a reader has looked up but not yet locked; the read fails with `NoSuchFileException` (2 of 3 runs).
- S3A prefetch on JDK 8: every prefetched block allocates a transient block-sized `byte[]` outside the buffer pool
  (`BufferData.setReady:215` → `getChecksum:161-166` → `CRC32.update` on a read-only copy).
- S3A prefetch with random reads: buffers stuck in CACHING stalled a reader (about 22 of 100 reads in 300 s).
- `LocalDirAllocator.java:528` only feeds the "max free space" figure in the error message (ablation changes nothing else).

## Environment lessons

1. **Surefire ignores `-DargLine`** (`hadoop-project/pom.xml:2469` sets `<argLine>${maven-surefire-plugin.argLine}</argLine>`).
   Pass `-Dmaven-surefire-plugin.argLine="-Xmx… -XX:+UseSerialGC -D…"` and confirm it from inside the test (max heap, GC name).
   It also drops the default `-XX:+HeapDumpOnOutOfMemoryError`.
2. **hadoop-common tests from a per-case copy** (`mvn -B test -Dtest=<Class>`, artifacts from `~/.m2`): compile ~20–25 s, whole
   unit run ~70 s. Patching a hard-coded constant (`sed`, run, `git checkout`) is a cheap way to get knob arms; log the constant by
   reflection. For ablations use `mvn -o test` / `mvn -o package` in the module and swap the jar in the distribution copy;
   **never install an ablated build into the shared `~/.m2`**.
3. **No MinIO** (dl.min.io returns HTTP 410) and **no pip** on the nodes. S3 endpoints that worked: moto 5.2.5
   (`python3 -m venv --without-pip`, `get-pip.py`, `pip install "moto[server]"`; buckets via boto3, names ≥ 3 chars) and S3Proxy
   2.1.0 from Maven Central (JDK 11). S3A settings: path-style access, SSL off, `fs.s3a.endpoint.region=us-east-1`, fake keys.
4. **`hadoop jar` from a distribution copy** (with `HADOOP_HEAPSIZE_MAX`, `-Djava.io.tmpdir`) is a usable no-daemon cluster tier
   for client-side code; `javap` the shipped class. `hadoop <Class>` only runs a class name containing a dot (use a package).
5. **HDFS restart:** run `hdfs dfsadmin -safemode wait` before submitting (≈30 s safe-mode extension). With log aggregation off the
   NodeManager deletes container logs on restart: copy each application's logs when it ends.
6. **Disk-limit cases:** loop filesystems (images and mount points under the run folder; `sudo` works) give exact free-space arms.
7. **Distributed shell** with `fs.defaultFS=file:///` works; set `HADOOP_CLIENT_OPTS=-Duser.home=<run>/dshome`, turn off the NM
   vmem check, call the jar by absolute path.
8. **Shell hygiene:** `until ! pgrep -f "<script path>"` matches its own shell; a teardown that kills every process with the run
   folder in its command line also kills your own `ssh pcNN '…$R…'` poll. pc39/pc29 clocks are MST, the session clock EST:
   record both when ordering freeze time against runs.

## Method lessons

1. On JDK 8 `ThreadMXBean.getThreadAllocatedBytes` is exact (`new byte[1 MiB]` = 1,048,592 B); measure around the single call
   and separate exception cost from buffer growth. Retained-heap readings across loop iterations (or from the first test in a
   shared surefire JVM) carry earlier objects: warm up, use one JVM per knob value, or rely on allocation counts.
2. Heap-bound predictions for S3A prefetch must allow for one transient block-sized array per block (see Findings).
3. Clients that can hang need flushed periodic readings and a `jstack` before the timeout kill. With ParallelGC set `-Xmn`
   explicitly in tight-heap OOM arms; with `HeapDumpOnOutOfMemoryError` the OOM text goes to stdout (lost inside a pipe).
4. A seek-per-block workload makes the S3A prefetch stream cache every block (`cancelPrefetches`); harness readers should log and
   retry at small cache sizes.
5. `Logger.setLevel(DEBUG)` inside a hadoop-common unit test produced no DEBUG lines; in task containers
   `-Dmapreduce.map.log.level=DEBUG` works. Find a map container by the logger prefix `] org.apache.hadoop.mapred.MapTask: `.

## Left on the nodes (2026-11-06; no process running)

- pc41: `/mydata/jingsong-s4/DF_getAvailable-getLocalPathForWrite-maxCapacity-run1/` (~1.9 GB; its distribution copy holds the
  ablated `hadoop-common` jar plus `.orig`), `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1/` (356 MB).
- pc39: `/mydata/jingsong-s4/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE-run1/` (1.5 GB),
  `/mydata/jingsong-s4/fs.s3a.prefetch.block.count-acquireHelper-size-run1/` (1.5 GB).
- pc29: `/mydata/jingsong-s4/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount-run1/` (1.4 MB, logs and conf only).
- Each node: `/mydata/jingsong-s4/hadoop-base/` (built distribution) and `~/.m2`. Source copy for stage 3: `~/hadoop-3.4.2/` on pc41.
