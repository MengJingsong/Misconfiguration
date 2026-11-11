# fs.s3a.prefetch.max.blocks.count — verification solution  <!-- file: cases/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SingleFilePerBlockCache.java:426`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/SingleFilePerBlockCache.java#L426) — `if (entryListSize > maxBlocksCount && !closed.get())` in `addToLinkedListAndEvictIfRequired` (this is also the main enforcement point) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-06 |
| Estimate | `positive` — the check evicts (deletes) the LRU block file whenever the number of cached block files of one S3A prefetching input stream exceeds `fs.s3a.prefetch.max.blocks.count`, so the local-disk bytes held by that stream's cache are bounded by about `(maxBlocksCount + 1) × fs.s3a.prefetch.block.size`. The cap is per open stream only (no process-wide bound), it is transiently overshot by one block, and it can leak a file when the eviction cannot take the entry's write lock within 5 s. |
| Ground | — |

Name parts: constraint `fs.s3a.prefetch.max.blocks.count`; function `addToLinkedListAndEvictIfRequired`; operand `maxBlocksCount`.

## A. Constraint trace

**A1. The constraint.**
- Name: `fs.s3a.prefetch.max.blocks.count` (configuration key), declared as
  `Constants.PREFETCH_MAX_BLOCKS_COUNT` at
  [`Constants.java:1684`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/Constants.java#L1684);
  default `DEFAULT_PREFETCH_MAX_BLOCKS_COUNT = 4` at `Constants.java:1690`.
- `*-default.xml`: no entry. `core-default.xml` has no `fs.s3a.prefetch.*` key (grep found only an ABFS
  readahead line, `core-default.xml:2336`), so the Java default 4 is what is used at runtime.
  The key is also not documented in `hadoop-aws/.../prefetching.md` (its table at lines 40-45 lists only
  stream type, the deprecated enable flag, block size and block count).
- Unit: number of blocks (each block is one local file of up to `fs.s3a.prefetch.block.size` bytes,
  `PREFETCH_BLOCK_SIZE_KEY`, default 8 MiB, `Constants.java:1642-1643`).
- Read: `S3ACachingInputStream` constructor, `conf.getInt(PREFETCH_MAX_BLOCKS_COUNT, DEFAULT_PREFETCH_MAX_BLOCKS_COUNT)`
  (`S3ACachingInputStream.java:93-94`), with `conf` being the S3A filesystem's configuration
  (`PrefetchingInputStreamFactory.java:85-87` passes `getConfig()`). It is passed through
  `BlockManagerParameters.withMaxBlocksCount` (`BlockManagerParameters.java:204-211`) →
  `CachingBlockManager` constructor (`CachingBlockManager.java:130-131`) → `createCache`
  (`CachingBlockManager.java:554-555`) → `SingleFilePerBlockCache` constructor, which stores it and
  requires `> 0` (`SingleFilePerBlockCache.java:228-229`).
- Set by: `core-site.xml` or `-D fs.s3a.prefetch.max.blocks.count=N` on the client command line, or a
  per-bucket `fs.s3a.bucket.<bucket>.prefetch.max.blocks.count`. It is read once per opened stream, so a
  change takes effect for the next `FileSystem` instance / next opened stream; no daemon restart is
  involved (no daemon reads it).
- Reader: whatever JVM is the S3A client — a `hadoop fs` / `hadoop jar` client JVM or a YARN task/container
  JVM — and only when the prefetching stream is selected (`fs.s3a.input.stream.type=prefetch`, or the
  deprecated `fs.s3a.prefetch.enabled=true`, `StreamIntegration.java:139-143`) and the object is larger
  than one prefetch block (`S3APrefetchingInputStream.java:111-128`).
- Related sources: `fs.s3a.prefetch.block.size` (bytes per cached file), `fs.s3a.buffer.dir`
  (`Constants.java:547`; default `${env.LOCAL_DIRS:-${hadoop.tmp.dir}}/s3a`, `core-default.xml:1805-1806`),
  which is where the files go (`S3AStoreImpl.java:290-295` builds the `LocalDirAllocator` on that key).

**A2. What it caps.** Local disk used by the S3A prefetch block-file cache of **one input stream**, in the
directories of `fs.s3a.buffer.dir`. The quantity compared is `entryListSize`, the count of entries in the
cache's LRU linked list (`SingleFilePerBlockCache.java:94`), which is incremented once per new cached
block (`:425`) and decremented once per successfully deleted file (`:459`). Bytes on disk ≈
`entryListSize × blockSize` (last block of the object may be smaller).

**A3. Mechanism.**
1. A block is requested for caching when the reader leaves a buffer that was **not** fully read
   (`S3ACachingInputStream.java:133-145`; a fully read buffer is released without caching, `:135-139`).
   `CachingBlockManager.requestCaching` queues a `CachePutTask` (`CachingBlockManager.java:439-481`);
   `addToCacheAndRelease` waits for the prefetch, then `cachePut` → `cache.put` (`:484-532`, `:558-564`).
2. `SingleFilePerBlockCache.put` (`:371-413`): if the block is already cached, only moves it to the LRU
   head (`:379-389`). Otherwise creates a temp file `fs-cache-*.bin` in a `fs.s3a.buffer.dir` directory
   (`getTempFilePath`, `:649-658`), **writes the whole block to it** (`:402`), records the entry in
   `blocks` (`:405`), bumps the `stream_read_blocks_in_cache` gauge (`:411`), and calls
   `addToLinkedListAndEvictIfRequired` (`:412`).
3. `addToLinkedListAndEvictIfRequired` (`:421-439`), under `blocksLock` write lock: add at head,
   `entryListSize++` (`:425`), then the check
   [`if (entryListSize > maxBlocksCount && !closed.get())`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/SingleFilePerBlockCache.java#L426).
   - True: unlink the tail (LRU) entry (`:427-433`) and `deleteBlockFileAndEvictCache` (`:446-471`): take
     the entry's write lock with a 5 s timeout (`PrefetchConstants.java:36,42`); on success
     `Files.deleteIfExists`, and if it deleted, `entryListSize--`, gauge −1, remove from `blocks`,
     `stream_evict_blocks_from_cache` +1 (`:458-463`).
   - False: nothing; the new file stays.
   Only **one** entry is evicted per put, so in the normal path `entryListSize` returns to `maxBlocksCount`.
4. Overshoot and bypass paths:
   - Transient +1: the new file is fully written (`:402`) before the eviction (`:412`), so momentarily
     `maxBlocksCount + 1` files exist; peak disk ≈ `(maxBlocksCount+1) × blockSize`.
   - Lock timeout (`:451-455`) or `deleteIfExists` returning false / throwing (`:458`, `:464-465`): the
     entry has already been unlinked from the list but stays in `blocks` and on disk, and
     `entryListSize` is **not** decremented. The orphan is never in the list again, so it is never chosen
     for eviction again; it is removed only on `close()` (`deleteCacheFiles`, `:513-538`, which iterates
     `blocks`). `entryListSize` stays one higher, so the next put evicts again, keeping the listed count at
     `maxBlocksCount` while the orphans add files on top: files on disk = `maxBlocksCount + #orphans`.
   - `writeFile` throwing after `getTempFilePath` created the file (`:393-402`) leaves an untracked file
     (caught as a caching error, `CachingBlockManager.java:534-537`); not deleted on close.
   - After `close()` (`closed` true), no eviction (`:426`), but `put` returns early anyway (`:373-375`).
5. Scope: one `SingleFilePerBlockCache` per `S3ACachingInputStream` (`CachingBlockManager.java:126-131`).
   N concurrently open streams can hold `N × (maxBlocksCount+1) × blockSize`; nothing caps the total.
   All of a stream's files are deleted at stream close (`S3ACachingInputStream.java:105-111` →
   `SingleFilePerBlockCache.close`, `:503-508`).
6. `isCacheSpaceAvailable` (`:621-633`) is not called anywhere in main code (grep), so there is no
   free-space check before writing.

**A4. Other consumers.** Same `fs.s3a.buffer.dir`: S3A disk-buffered uploads (`fs.s3a.fast.upload.buffer=disk`)
and S3A committer temp files (`LocalTempDir.java:29-47`). Heap: the prefetch buffer pool,
`(fs.s3a.prefetch.block.count + 1) × blockSize` per stream (`S3ACachingInputStream.java:84-85`,
`Constants.java:1636-1649`), not controlled by this key. Other streams' caches, other files on the volume,
and (in YARN) the NodeManager local dir that `LOCAL_DIRS` points to.

**A5. Evidence beyond the source.**
- Existing tests: `hadoop-aws/src/test/java/org/apache/hadoop/fs/s3a/ITestS3APrefetchingLruEviction.java`
  (parameterized max-blocks 1 and 2; asserts `stream_read_blocks_in_cache == maxBlocks` and
  evictions ≥ 4; needs a real S3 bucket). `hadoop-common/src/test/.../prefetch/TestBlockCache.java`
  (put/get with maxBlocksCount 2, no eviction assertions).
- `hadoop-aws/src/site/markdown/tools/hadoop-aws/prefetching.md` (stream selection, caching on random
  reads; no mention of the max-blocks key).
- JIRA: the LRU eviction is from HADOOP-18291 (S3A prefetch LRU cache for `SingleFilePerBlockCache`),
  https://issues.apache.org/jira/browse/HADOOP-18291 — cited from memory, not fetched in this session.

## B. Verification solution

**B1. Claim under test.** For one S3A prefetching input stream, the number of `fs-cache-*.bin` files in
`fs.s3a.buffer.dir` (and their total bytes) never exceeds `maxBlocksCount + 1` blocks
(`(maxBlocksCount + 1) × blockSize` bytes) and settles at `min(maxBlocksCount, #distinct partially read
blocks)`, scaling with `fs.s3a.prefetch.max.blocks.count`; if the write lock cannot be taken for eviction,
files exceed the cap by one per failed eviction until close.

### B2. Unit tier

**B2a. Environment and build.** JDK 8, Maven 3.3+. Copy the tree to local disk
(`rsync -a /users/jason92/hadoop-3.4.2/ /local/$USER/hadoop-src/`). Build once:
`cd /local/$USER/hadoop-src && mvn -pl hadoop-common-project/hadoop-common -am install -DskipTests`.
Add the test class `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/impl/prefetch/TestBlockCacheLruCap.java`
in the copy (same package, so `EmptyPrefetchingStatistics` and package-private members are reachable).
Run: `mvn -pl hadoop-common-project/hadoop-common test -Dtest=TestBlockCacheLruCap`. Default surefire JVM
options are fine (blocks are 1 MiB).

> **Amendment A1 (2026-11-06, stage-4 audit, before any reading) — node paths and commands.** On the stage-4 node (`pc29`,
> Jingsong's `environment.md`) the copy is made with `copy-source.sh /mydata/jingsong-s4/<stem-without-suffix>-run1/src` (the
> filed `rsync` source `~/hadoop-3.4.2` and `/local/$USER` do not exist). No `install` build: the node's `~/.m2` holds all
> `3.4.2` artifacts (`environment.md` §3). The test class is kept in the harness folder
> (`stage4-runtime-verification/jingsong/harness/<stem>/`) and copied into the copy's
> `hadoop-common/src/test/java/org/apache/hadoop/fs/impl/prefetch/`; the run is `mvn -B test -Dtest=TestBlockCacheLruCap
> -DfailIfNoTests=false` from `src/hadoop-common-project/hadoop-common`, JDK 8. The build returns 0 on test failures, so the run
> reads the surefire count (`Tests run: 3, Failures: 0, Errors: 0`), not the exit code.

**B2b. Knobs.** `maxBlocksCount` passed to `new SingleFilePerBlockCache(stats, maxBlocksCount, null)` —
values 1, 2, 4 (the default), 8, and positive control 1000 (never reached). Block size fixed at 1 MiB.
A second knob, for the bypass test only: a subclass that overrides `readFile` (protected, `:285`) to sleep
7 s, so a concurrent `get()` holds the entry's read lock longer than the 5 s eviction timeout.

**B2c. Workload.** Configuration `conf.set("test.prefetch.dir", <tmpdir>)`,
`LocalDirAllocator alloc = new LocalDirAllocator("test.prefetch.dir")`. For `b = 0 .. 19`:
`cache.put(b, buf_b, conf, alloc)` where `buf_b` is a 1 MiB heap buffer filled with byte `b`. 20 puts
> every finite knob value, so each run passes the limit by 20 − max puts. Wrap `PrefetchingStatistics`
with a counting implementation (extend `EmptyPrefetchingStatistics` or implement the interface) to count
`blockAddedToFileCache`, `blockRemovedFromFileCache`, `blockEvictedFromFileCache`.
LRU check (max=4): put 0..3, `get(0, ...)`, put 4 → block 1 must be evicted, 0 must remain.
Bypass test (max=2), on the subclass whose `readFile` sleeps 7 s only while a test flag is set:
put 0, put 1 (list 1→0). Set the flag. Thread A `get(0, buf)` (0 moves to head, then A holds 0's read
lock for 7 s); after 200 ms thread B `get(1, buf)` (1 moves to head, so 0 is the tail again). After
another 200 ms the main thread does `put(2)`: `entryListSize` 3 > 2, tail 0 is unlinked, its write-lock
attempt times out after 5 s, file 0 is not deleted. Join A and B, clear the flag, then put 3 and put 4
(each evicts the current tail: 1, then 2).

**B2d. Observables and instruments.** After each put: `cache.size()` (= `blocks.size()`),
the number of files matching `fs-cache-*.bin` in `<tmpdir>` (`Files.list`), their total bytes, and the
counter values. Peak inside a put (transient +1) is not visible between calls; sample it with the
`writeFile` override (protected, `:478`) by counting files right after `super.writeFile`. `entryListSize`
is private: read it by reflection (`getDeclaredField("entryListSize")`). After `close()`: file count.

**B2e. Procedure.**
1. Write `TestBlockCacheLruCap` with: `testCapScales` (parameterized over 1, 2, 4, 8, 1000), `testLruOrder`,
   `testEvictionLockTimeoutLeaks`; each uses a fresh `@Rule TemporaryFolder` dir on local disk.
2. Log one line per put: `max, b, cacheSize, files, bytes, entryListSize, peakFilesInWrite, evicted`.
3. Run the mvn command in B2a; collect `target/surefire-reports/*TestBlockCacheLruCap-output.txt`.
4. Delete the test file from the copy afterwards (or delete the copy).

> **Amendment A2 (2026-11-06, stage-4 audit, before any reading) — test structure and log format.** (a) "Parameterized" is a
> loop inside `testCapScales` over max ∈ {1, 2, 4, 8, 1000} × 3 repetitions (B2h), each (max, rep) with a fresh temp folder, a
> fresh cache and a counting `PrefetchingStatistics`; after the 20 puts the cache is closed and the files counted. `testLruOrder`
> and `testEvictionLockTimeoutLeaks` also loop 3 repetitions. (b) The subclass used everywhere overrides `writeFile` (count
> `fs-cache-*.bin` files in the folder right after `super.writeFile`; the per-put peak is that count, the run's peak its maximum)
> and `readFile` (sleep 7 s while the test flag is set). In the bypass test thread B's `get(1)` also sleeps 7 s (the flag is
> set); that only holds block 1's read lock, which no eviction asks for before the joins, so B2f is unchanged. (c) One stdout
> line per put: `IFCHK,cap,<max>,<rep>,<b>,<cacheSize>,<files>,<bytes>,<entryListSize>,<peakInPut>,<evicted>,<added>,<removed>`
> (`evicted`/`added`/`removed` = counts of `blockEvictedFromFileCache`/`blockAddedToFileCache`/`blockRemovedFromFileCache`), one
> `IFCHK,close,<max>,<rep>,<files>` line after close, and analogous `IFCHK,lru,…` and `IFCHK,bypass,<rep>,<step>,…` lines (the
> bypass lines also carry the duration of `put(2)` in ms and `containsBlock(0)`). The test asserts nothing about the readings
> (only that the setup ran), so a contradicting reading is logged, not hidden by an early assertion failure.

**B2f. Predictions.** Blocks of 1 MiB = 1,048,576 B.
| max | files after put b (b=0..19) | files after 20 puts | bytes after 20 puts | peak in-put files | evictions | files after close |
|---|---|---|---|---|---|---|
| 1 | min(b+1, 1) | 1 | 1,048,576 | 2 | 19 | 0 |
| 2 | min(b+1, 2) | 2 | 2,097,152 | 3 | 18 | 0 |
| 4 | min(b+1, 4) | 4 | 4,194,304 | 5 | 16 | 0 |
| 8 | min(b+1, 8) | 8 | 8,388,608 | 9 | 12 | 0 |
| 1000 (control) | b+1 | 20 | 20,971,520 | 20 | 0 | 0 |
`cacheSize == files == entryListSize` in every row. LRU test: after put 4, `containsBlock(0)` true,
`containsBlock(1)` false. Bypass test (max=2): put 2 takes ≈5 s; afterwards files = 3, `cacheSize` = 3,
evictions = 0, `entryListSize` = 3; after puts 3 and 4: files = 3 (2 listed + orphan 0), `entryListSize`
= 3, evictions = 2; block 0 still `containsBlock` true; after close files = 0.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| Files plateau at `max` and peak at `max+1`, for every finite max; control grows to 20 | Claim confirmed at unit level |
| Files exceed `max+1` in the normal (no-contention) path for some max | Claim wrong: cap does not hold |
| Files plateau at the same value for all max | Claim wrong: knob not effective |
| Control (1000) also plateaus | Workload/instrument broken (e.g. files written elsewhere); result void |
| Bypass test: files stay at 2 | Leak path predicted in A3.4 does not occur; amend A3 |
| Files remain after close in the normal test | Close path does not clean; disk not bounded over stream lifetime |

> **Amendment A3 (2026-11-06, stage-4 audit, before any reading) — a verdict for every row, missing rows.** The rows above read,
> in the stage-4 vocabulary (claim B1; "Confirmed" = B1 held): row 1 (all finite max: files after 20 puts = max, peak in put
> ≤ max + 1, `cacheSize == files == entryListSize`; control grows to 20; files after close 0) → **Confirmed — caps**. Row 2
> (files > max + 1 in the normal path) → **Refuted — caps only on some paths (bypass)**, or **does not cap** if the count keeps
> growing with the puts. Row 3 (same plateau for every finite max, control growing) → **Refuted — does not cap**. Row 4
> (control also plateaus) → **Invalid**. Row 6 (files after close > 0 in the normal test) → **Refuted — caps only on some paths
> (bypass)** (disk is not released across stream lifetimes). Row 5 and the bypass test do not decide the cap verdict: bypass as
> B2f predicts (put 2 ≈ 5 s, files 3, then 3 after puts 3 and 4, 0 after close) confirms B1's soft-cap sentence; files stay at
> 2 is feedback to A3.4 only; files rising by one per later put (4, 5) after a single failed eviction → **Refuted — caps only
> on some paths (bypass)**. Added rows: (7) counter capped but the real resource grows — `cacheSize`/`entryListSize` ≤ max while
> `files` > max + 1 in the normal path → **Refuted — caps only on some paths (bypass)**; (8) files settle at a value that scales
> with max but differs from max (still ≤ max + 1) → **Not confirmed** (the prediction missed; effect `caps` noted, unsettled);
> (9) the LRU test fails (block 0 evicted or block 1 kept) while row 1 holds → **Confirmed — caps**, with an LRU-order note to
> A3; (10) the limit is never reached (fewer than max + 1 puts succeed for some finite max) → **Invalid**; (11) the three
> repetitions disagree → the worst repetition decides the row. A test error before the readings are written is a runbook defect,
> not a verdict.

**B2h. Controls.** The 1000 control shows the same workload grows disk without the cap. Counting files
directly on disk (not only `cache.size()`) separates map bookkeeping from real bytes. The dedicated temp
dir excludes other writers. LRU test rules out "evicts arbitrary/new block". Re-run each case 3× for
determinism (the unit path is single-threaded except the bypass test).

### B3. Cluster tier

**B3a. Environment and build.** One Linux host (≥ 8 GB RAM, ≥ 10 GB free local disk).
- Build distribution in the local copy:
  `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`; unpack
  `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/local/$USER/hadoop`.
- S3 endpoint: an S3-compatible object store on the same host (e.g. a MinIO server binary bound to
  `127.0.0.1:9000`, data dir `/local/$USER/s3data`), bucket `pf`. This is the only non-Hadoop piece; S3A
  has no S3 server of its own.
- Hadoop daemons: pseudo-distributed YARN (ResourceManager + NodeManager) from the distribution, used for
  the in-container variant; HDFS is not needed (`fs.defaultFS` stays `file:///`).
- `etc/hadoop/hadoop-env.sh`: `export HADOOP_OPTIONAL_TOOLS=hadoop-aws`,
  `export HADOOP_LOG_DIR=/local/$USER/hlogs`, `export HADOOP_HEAPSIZE_MAX=1g`.
- `core-site.xml`: `hadoop.tmp.dir=/local/$USER/htmp`; `fs.s3a.endpoint=http://127.0.0.1:9000`;
  `fs.s3a.endpoint.region=us-east-1`; `fs.s3a.path.style.access=true`;
  `fs.s3a.connection.ssl.enabled=false`; `fs.s3a.access.key`/`fs.s3a.secret.key` = the local store's
  test credentials (local only); `fs.s3a.input.stream.type=prefetch`;
  `fs.s3a.prefetch.block.size=1048576`; `fs.s3a.buffer.dir=/local/$USER/s3abuf` (client run).
- `yarn-site.xml`: `yarn.nodemanager.local-dirs=/local/$USER/nm-local`,
  `yarn.nodemanager.log-dirs=/local/$USER/nm-logs`, `yarn.nodemanager.resource.memory-mb=4096`,
  `yarn.nodemanager.aux-services=mapreduce_shuffle`.
- Workload program `SeekReader` (one class, compiled against `$(hadoop classpath)` into `seekreader.jar`):
  args `<s3a path> <holdSeconds>`; opens the file; for `b = 0 .. numBlocks-1`: `seek(b × 1 MiB + 100)`,
  `read` 4096 bytes (partial block → the previous block is queued for caching on the next seek); after
  the loop sleeps `holdSeconds` with the stream open, prints `in.getIOStatistics()` and closes.

> **Amendment A4 (2026-11-06, stage-4 audit, before any reading) — node, S3 store, daemons.** Node `pc29`; every `/local/$USER`
> above and below means the run folder `R=/mydata/jingsong-s4/<stem-without-suffix>-run1` (local disk). No rebuild: the
> distribution `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` is copied to `R/hadoop` (`environment.md` §4);
> it has `share/hadoop/tools/lib/hadoop-aws-3.4.2.jar` and `bundle-2.29.52.jar`. **S3 store: moto server** (Python, in a venv at
> `R/venv`, `moto_server -H 127.0.0.1 -p 9000`, objects in memory) instead of MinIO, whose binaries are no longer served
> (`dl.min.io` answered HTTP 410 on 2026-11-06); any access/secret key is accepted (`testing`/`testing`). It serves the same
> S3 calls S3A makes here (HEAD, ranged GET, LIST, PUT). YARN daemons are started with `yarn --daemon start
> resourcemanager|nodemanager` (no SSH to `localhost`, so not `start-yarn.sh`) and stopped with `--daemon stop`;
> `yarn.nodemanager.aux-services` is left unset (distributed shell needs no shuffle) and
> `yarn.nodemanager.vmem-check-enabled=false` (a 40-core node's JVM reserves several GB of virtual memory; a vmem kill would void
> a container run). The container variant uses a second configuration directory `R/conf-ctr`, identical except that
> `fs.s3a.buffer.dir` is not set, so the default `${env.LOCAL_DIRS:-${hadoop.tmp.dir}}/s3a` (`core-default.xml:1805-1806`)
> resolves to the container's directory under `R/nm-local`.

**B3b. Knobs.** `fs.s3a.prefetch.max.blocks.count` ∈ {1, 4 (default, unset), 16} plus positive control
1000, passed as `-Dfs.s3a.prefetch.max.blocks.count=N` to `hadoop jar` (generic option parsed by
`ToolRunner`; implement `SeekReader` as a `Tool`) — no restart. For the container variant, the same `-D`
is given in the distributed-shell command's environment via `HADOOP_CLIENT_OPTS` or the program args.

**B3c. Workload.** Object `s3a://pf/obj64m` of 64 MiB (`dd if=/dev/urandom of=/local/$USER/obj64m bs=1M
count=64; hadoop fs -put /local/$USER/obj64m s3a://pf/obj64m`) → 64 blocks of 1 MiB; the loop leaves 63
blocks partially read (block 63 is never left), so 63 cache requests, far above every finite knob (and
63 < 1000 for the control). Pace the loop with a 200 ms sleep between seeks so each async cache put
completes and slow-caching auto-disable (`CachingBlockManager.java:541-548`, > 5 s) does not trigger.
Duration ≈ 13 s loop + 20 s hold.

**B3d. Observables and instruments.**
- Disk: a sampler started before the client, every 100 ms, writing
  `timestamp, $(find /local/$USER/s3abuf -name 'fs-cache-*.bin' | wc -l), $(du -sb /local/$USER/s3abuf | cut -f1)`
  to a CSV; report max and value at end of hold.
- Stream statistics printed by `SeekReader` before close: gauge `stream_read_blocks_in_cache`, counters
  `stream_evict_blocks_from_cache`, `stream_file_cache_eviction` (`StreamStatisticNames.java:449-490`).
- Free space: `df -B1 /local/$USER/s3abuf` before/after.
- Not directly observable: the internal `entryListSize`; orphaned (unlisted) files are only seen as the
  difference between file count and the gauge.

**B3e. Procedure.**
1. Start the local S3 store; create bucket `pf`; `mkdir -p /local/$USER/{s3abuf,htmp,hlogs,nm-local,nm-logs}`.
2. Upload the object (B3c). `hadoop fs -ls s3a://pf/` to confirm access.
3. For N in 1, 4, 16, 1000 (each 3 times): clear `/local/$USER/s3abuf`; start the sampler; run
   `hadoop jar seekreader.jar SeekReader -Dfs.s3a.prefetch.max.blocks.count=N s3a://pf/obj64m 20`
   (for N=4 also once with the key unset); stop the sampler; record max files/bytes, files at end of hold,
   files 5 s after exit, and the printed statistics.
4. Container variant (N=2 and N=1000): `start-yarn.sh`; run SeekReader through distributed shell
   (`yarn jar share/hadoop/yarn/hadoop-yarn-applications-distributedshell-3.4.2.jar -jar <same jar>
   -shell_command "hadoop jar seekreader.jar SeekReader -Dfs.s3a.prefetch.max.blocks.count=N s3a://pf/obj64m 20"
   -container_memory 1024`, shipping `seekreader.jar` with `-shell_script`/localized file), with
   `fs.s3a.buffer.dir` left at default so it resolves to the container's `LOCAL_DIRS` under
   `/local/$USER/nm-local/usercache/...`; sample `find /local/$USER/nm-local -name 'fs-cache-*.bin'`.
   `stop-yarn.sh` afterwards.
5. Stop the S3 store; `jps` shows no Hadoop process.

> **Amendment A5 (2026-11-06, stage-4 audit, before any reading) — exact procedure.** (a) `SeekReader` is a `Tool` run by
> `ToolRunner`; before closing it prints one line `IFCHK,stats,<N>,<wrapped stream class>,<stream_read_blocks_in_cache>,
> <stream_evict_blocks_from_cache>,<stream_file_cache_eviction count>` plus the full IOStatistics. (b) The sampler is a Python
> loop (every 100 ms: count and summed bytes of `fs-cache-*.bin` under the sampled directory, recursively; `du -sb` of the
> directory every 1 s), started 1 s before the client and stopped 5 s after it exits; "files 5 s after exit" is its last
> sample. `df -B1` of `/mydata` before and after each run. (c) Order: instrument check (`hadoop fs -ls`, `-put`, and a
> `-cat | md5sum` of the 64 MiB object against the local file); then N = 1, 4, 16, 1000, each 3 times, then the key unset once,
> then the sequential `hadoop fs -cat s3a://pf/obj64m > /dev/null` once with the sampler on `R/s3abuf`; then the container variant
> N = 2 and N = 1000, once each. (d) Container variant: distributed shell with `-shell_script ds.sh` (the script exports
> `HADOOP_CONF_DIR=R/conf-ctr` and runs `R/hadoop/bin/hadoop jar R/harness-jar/seekreader.jar SeekReader -D… s3a://pf/obj64m 20`
> by absolute path — one node, same user, so no localization of the jar is needed), `-container_memory 1024`, `-num_containers 1`;
> the sampler watches `R/nm-local`. `fs.defaultFS` stays `file:///`, so the client stages its files on local disk. (e) Any failed
> step or a wait over 180 s stops the run (runbook stop); every process the run started is stopped on any exit.

> **Amendment A8 (2026-11-06, stage-4 run 1, runbook defect before any cluster reading) — bucket name.** `pf` is not a valid
> S3 bucket name (3–63 characters; moto answers `InvalidBucketName`). The bucket is **`ifchk-pf`**: every `s3a://pf/…` and
> "bucket `pf`" in B3 means `s3a://ifchk-pf/…`. Nothing else changes; B3f and B3g are unchanged.

> **Amendment A9 (2026-11-06, stage-4 run 1, runbook defect in the cluster tier) — read errors in `SeekReader`.** In the
> second N = 1 client run the reader died at block 1 with `NoSuchFileException` on a cache file (`CachingBlockManager` "error
> reading block 1", from `SingleFilePerBlockCache.get` → `readFile`): at the first seek two puts (block 0 left, block 1 from
> `cancelPrefetches`) run together, and with N = 1 the second put evicts the block a concurrent `get` has looked up but not yet
> read-locked (`get` takes the entry's read lock only after `getEntry`, `SingleFilePerBlockCache.java:273-277`; the eviction's `tryLock` then succeeds and
> deletes the file). That is a reader failure, not a cache-size reading. `SeekReader` therefore retries a block whose seek/read
> throws (up to 3 attempts, re-seeking to the same offset; the third failure ends the run) and prints
> `IFCHK,readerror,<block>,<attempt>,<exception>` per failure and `IFCHK,readerrors,<count>` after the loop. The workload (one
> partial read per block) and B3f/B3g are unchanged; read errors are reported per run as a finding. The tier restarts.

**B3f. Predictions.** Block 1 MiB.
| N | max files (sampled) | max bytes | files at end of hold | gauge at end | evictions | files after exit |
|---|---|---|---|---|---|---|
| 1 | ≤ 2 | ≤ 2,097,152 | 1 | 1 | 62 | 0 |
| 4 (and unset) | ≤ 5 | ≤ 5,242,880 | 4 | 4 | 59 | 0 |
| 16 | ≤ 17 | ≤ 17,825,792 | 16 | 16 | 47 | 0 |
| 1000 (control) | 63 | 66,060,288 | 63 | 63 | 0 | 0 |
Container variant: same relation for N=2 (≤ 3 files, 2 at hold) and 63 for N=1000, under the NM
local dir. Small deviations below the predicted cached count are allowed if some cache puts were skipped
(block already cached, prefetch errors); any reading above `N+1` with no "write lock could not be
acquired" ERROR in the client log contradicts the claim.

> **Amendment A6 (2026-11-06, stage-4 audit, before any reading) — the number of cache puts.** B3c counts 63 cache requests
> (the left blocks). From the source there can be one more: every out-of-order read calls `blockManager.cancelPrefetches()`
> (`S3ACachingInputStream.java:146-150`), which requests caching of every buffer still `PREFETCHING` or `READY`
> (`CachingBlockManager.java:295-306`), i.e. the block prefetched after the previous seek — the very block the reader is
> about to read. So block `b` is normally cached by the seek to `b` (and leaving it later finds it cached,
> `CachingBlockManager.java:459-462`), and block 63, prefetched at the seek to 62, is cached at the seek to 63. The number of
> distinct cached blocks is therefore **P ∈ {63, 64}** (64 expected), observed as `P = evictions + gauge at end of hold`. The
> table's evictions column reads `P − N` (63/60/48 for N = 1/4/16 when P = 64; 62/59/47 when P = 63), and the control's
> max files, max bytes, files at end of hold and gauge read `P` and `P × 1,048,576` (63 or 64). Container variant N = 2:
> evictions `P − 2`. The `≤ N + 1`, `= N at end of hold` and `0 after exit` predictions are unchanged. (One put runs per seek
> after the first, so at most one new file is in flight once the cache is full; two concurrent puts could transiently reach
> N + 2 — left as a note for stage 3; the 100 ms sampler is not expected to see a transient either way.)

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| Files plateau at N, never above N+1, scaling with N; control reaches ~63 | Claim confirmed: the key caps the stream's cache disk |
| Files above N+1 with no lock-timeout ERROR logged | Claim wrong: another path bypasses the cap |
| Files above N+1 with "deletion would not be attempted" ERROR | Leak path (A3.4) confirmed in practice; cap is soft |
| Same plateau for all N | Key not reaching the stream (wrong stream type, per-bucket override); check `hadoop jar` log and stats |
| Control stays low too | Caching not triggered (reads fully consuming blocks, caching auto-disabled, or object ≤ block size); fix workload, result void |
| Files remain after exit | Close does not clean (or untracked failed-write files); disk not bounded across stream lifetimes |

> **Amendment A7 (2026-11-06, stage-4 audit, before any reading) — a verdict for every row, missing rows.** Row 1 (every
> finite N, all repetitions: sampled max ≤ N + 1, files at end of hold = N, gauge = N, scaling with N; control reaches P − 1 or
> more; files after exit 0) → **Confirmed — caps**. Row 2 (above N + 1, no lock-timeout ERROR) → **Refuted — caps only on some
> paths (bypass)**, or **does not cap** if the end-of-hold count grows with the blocks read. Row 3 (above N + 1 with the
> "deletion would not be attempted" ERROR, by at most the number of such ERRORs) → **Confirmed — caps** (soft; the leak of B1).
> Row 4 (same plateau for every N including 1000) and row 5 (control stays low) → **Invalid**. Row 6 (files after exit > 0) →
> **Refuted — caps only on some paths (bypass)**. Added rows: (7) gauge ≤ N but on-disk files > N + 1 at end of hold without
> the ERROR → **Refuted — caps only on some paths (bypass)** (counter capped, real resource not); (8) the end-of-hold count
> scales with N but differs from N while staying ≤ N + 1 → **Not confirmed**; (9) the unset run differs from N = 4 → the
> default is not 4: recorded, the cap verdict comes from rows 1–8; (10) the sequential `-cat` leaves cache files → recorded as
> feedback to A3.1, verdict unchanged; (11) the container variant disagrees with the client runs (above N + 1, or the control
> does not grow) → the verdict comes from the client runs and the container result is recorded as a deviation, except that
> files above N + 1 there without the ERROR → **Refuted — caps only on some paths (bypass)**; a container run that fails to
> start is a runbook defect for that variant only; (12) the repetitions disagree → the worst repetition decides the row.

**B3h. Controls.** Positive control N=1000 with identical workload shows growth to the number of
partially read blocks. Unset-key run equals N=4 (default). Gauge vs on-disk count separates bookkeeping
from bytes. Dedicated empty buffer dir rules out other writers (no uploads run during measurement). Three
repetitions per N for async timing variance. A sequential `hadoop fs -cat s3a://pf/obj64m > /dev/null`
run should produce 0 cache files (fully read blocks are not cached, `S3ACachingInputStream.java:135-139`),
showing caching is due to the seek pattern.

**B4. Risks and cleanup.** Disk use is < 100 MB in buffer dirs plus 64 MB object and its copy in the local
S3 store — all under `/local/$USER`, never shared storage. Ports: S3 store 9000 (bind 127.0.0.1), YARN
8088/8030-8033/8040-8042 — check free first. Kill the sampler loop; `stop-yarn.sh`; stop the S3 store
process; `jps` must list nothing from this run; `rm -rf /local/$USER/{s3abuf,htmp,hlogs,nm-local,nm-logs,s3data,obj64m}`.
Unit tier: delete the test class and the copied tree when done; temp folders are removed by the rule.
Do not put real AWS credentials in `core-site.xml`.

## C. Sources read

hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/SingleFilePerBlockCache.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/CachingBlockManager.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/BlockManagerParameters.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/PrefetchConstants.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/statistics/StreamStatisticNames.java
hadoop-common-project/hadoop-common/src/main/resources/core-default.xml
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/impl/prefetch/TestBlockCache.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/Constants.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/S3AInstrumentation.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/S3ACachingInputStream.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/S3APrefetchingInputStream.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/PrefetchingInputStreamFactory.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/impl/streams/StreamIntegration.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/impl/S3AStoreImpl.java (grep)
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/commit/LocalTempDir.java (grep)
hadoop-tools/hadoop-aws/src/test/java/org/apache/hadoop/fs/s3a/ITestS3APrefetchingLruEviction.java
hadoop-tools/hadoop-aws/src/site/markdown/tools/hadoop-aws/prefetching.md
hadoop-tools/hadoop-aws/src/site/markdown/tools/hadoop-aws/reading.md (grep)
https://issues.apache.org/jira/browse/HADOOP-18291 (cited, not fetched)

## D. Stage-4 feedback

**D1. Audit amendments (2026-11-06, stage 4, before any harness run or reading).** Results file:
[`../../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md`](../../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.md).
A1 (B2a) node paths and commands, surefire counts; A2 (B2c–B2e) test structure, 3 repetitions, log format; A3 (B2g) a
verdict for every row and the missing rows; A4 (B3a) node, moto server as the S3 store (MinIO binaries not served), YARN
daemon start, vmem check off, container configuration; A5 (B3b–B3e) exact procedure, sampler, order; A6 (B3f) cache puts
P ∈ {63, 64} because `cancelPrefetches` caches the prefetched block, evictions `P − N`; A7 (B3g) a verdict for every row and
the missing rows. Filed sha256 `33c11116…91354ef3`; the sha256 after A1–A7 is recorded in the results file §1.
Run-1 runbook defects in the cluster tier (2026-11-06, before the reported cluster readings; prediction and conclusion text
unchanged): A8 (B3) bucket `ifchk-pf` (`pf` is not a valid bucket name); A9 (B3a) `SeekReader` retries a block whose read throws
(eviction/get race at N = 1). sha256 after A8, A9: `a03e64963bbbb16ab9df6f94916fde098f152620d0c9628f49d680742453def3`.

**D2. Stage-4 verdict (2026-11-06, run 1 + self-check; results file above).** Unit tier: **Confirmed — caps** (B2g row 1):
after 20 puts the files were exactly max (1, 2, 4, 8) with an in-put peak of max + 1, `cacheSize == files == entryListSize`
in all 300 put rows, control 1000 grew to 20, 0 files after close; the LRU order held; the lock-timeout test showed exactly the
predicted soft-cap leak (put 2 took 5006 ms, files 3, one orphan until close). Cluster tier: **Confirmed — caps** (B3g row 1):
with a 64 MiB object and 1 MiB blocks, end-of-hold cache files = gauge = N for N = 1, 4 (and unset), 16 and the container run
N = 2; sampled maximum ≤ N + 1; control 1000 cached all 64 blocks (67,108,864 B); 0 files after exit; no lock-timeout ERROR.
Outcome class: **true positive**. Findings: the prefetched block is cached at every out-of-order seek (A6, observed 64 puts);
with N = 1, concurrent puts can evict a block a reader is about to read, failing the read with `NoSuchFileException` (A9;
2 of 3 N = 1 runs) — a reader failure, not a cap violation. The estimate stands.
