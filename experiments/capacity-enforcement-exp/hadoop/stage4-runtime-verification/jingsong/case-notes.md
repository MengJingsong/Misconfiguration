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

## Open calls for Jingsong (2026-11-25, orders 6, 14, 22, 26–31)

- Order 14 `DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK`: the cluster `[B` deltas of arms A and B sit about
  3.37 MB below the frozen point values (A −3,364,232 B, B −3,372,736 B); the frozen B3f noise allowance and the B − A
  check (28.99 MiB) make the tier Confirmed (filed **true positive**). Read strictly (no allowance) the cluster tier is Not
  confirmed and the class **weak true positive** (results §5, §8).

## Findings beyond the verdicts (upstream / doc candidates; check JIRA first)

- S3A `SingleFilePerBlockCache` at `fs.s3a.prefetch.max.blocks.count=1`: two puts at the same seek can evict a
  block a reader has looked up but not yet locked; the read fails with `NoSuchFileException` (2 of 3 runs).
- S3A prefetch on JDK 8: every prefetched block allocates a transient block-sized `byte[]` outside the buffer pool
  (`BufferData.setReady:215` → `getChecksum:161-166` → `CRC32.update` on a read-only copy).
- S3A prefetch with random reads: buffers stuck in CACHING stalled a reader (about 22 of 100 reads in 300 s).
- `LocalDirAllocator.java:528` only feeds the "max free space" figure in the error message (ablation changes nothing else).
- **2026-11-25 (orders 6, 14, 22, 26–31):**
  - `FsDatasetImpl.cleanupReplica` reads the meta length after deleting the meta file, so every disk-balancer (and Mover)
    move off a volume over-counts that volume's `dfsUsed` by one meta file (131,079 B per 16 MiB block) until a DU refresh
    (order 26).
  - `DiskBalancer.java:1138` compares the destination's headroom with the whole `bytesToCopy`, not the block, and stops
    early on a nearly full destination (order 26; cf. HDFS-13892).
  - `AvailableSpaceVolumeChoosingPolicy`: at exactly `replicaSize` available, line 166 (`<`) keeps the low group and the
    round robin (`>`) rejects it — a spurious `DiskOutOfSpaceException` while another volume has room (order 27).
  - `FsVolumeImpl.append`: `dfsUsed` grows by the whole new block length after an append until the next DU refresh, so
    later appends are refused early (order 28, conservative).
  - `Mover.run` builds a new `Mover` per iteration and re-registers `MoverMetrics`; the second iteration throws
    `MetricsException … already exists` and the Mover exits 255 (order 29). `FsVolumeList.getVolumeByMount` leaks a volume
    reference on refusal (order 29, guided stage-5 side note).
  - pmem cache: directories on one file system each get `maxBytes = getUsableSpace()`, so the advertised capacity doubles
    (orders 30, 31); `PmemMappableBlockLoader.load:97` ignores `transferTo`'s return value (order 31); the cancel path
    releases before close and leaves an uncounted cache file (order 31); a DataNode restarted with cache capacity 0 sends
    no cache reports, so the NameNode keeps a stale cached list and re-sends `DNA_UNCACHE` (order 30).
  - TFile with 64 KiB keys stores about twice the key bytes (one index key per block); log aggregation under a space quota
    leaves a partial `.tmp` file (order 6).

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
9. **Clocks (2026-11-25 nodes):** the shell on `pc91`/`pc82`/`pc72` runs in MST, the session in EST (MST + 2 h), and the
   Hadoop daemon and surefire log lines are in **UTC** (MST + 7 h). Convert before matching log lines to sampler rows or the
   freeze time.
10. **MapReduce shuffle and merge logging** (`org.apache.hadoop.mapreduce.task.reduce`) goes to the reducer container's
    `syslog.shuffle`, not `syslog` (`container-log4j.properties`, `MRApps.java:662`); copy both (order 6, runbook defect 1).
11. **Loop volumes for disk-limit cases: use ext2 `-m 0`.** ext4 keeps 4096 reserved clusters (16 MiB on a small image) even
    with `-m 0`, so Free ≠ Available and every `DF.getAvailable()` operand shifts; ext2 `-m 0` gives Free == Available
    (order 28).
12. **Harness logging wrappers must not write into input files:** a wrapper that tees its own lines into the file it creates
    changes the workload (order 29: the staging file grew by 66 B, so each put made a 64 MiB and a 66 B block). Create input
    files with plain `dd`/`head`, log elsewhere.
13. **SSH to `localhost` fails on the nodes:** case files that say `start-dfs.sh`/`start-yarn.sh` need an amendment to start
    each daemon with `hdfs --daemon start …` / `yarn --daemon start …` from the run's distribution copy (`environment.md`;
    orders 6, 29, 30 amended this; stage-3 write-ups should name `--daemon` and `copy-source.sh` up front).

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
