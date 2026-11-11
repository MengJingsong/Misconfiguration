# fs.s3a.prefetch.block.count — verification solution  <!-- file: cases/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BoundedResourcePool.java:176`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/BoundedResourcePool.java#L176) — `if (createdItems.size() < size)` in `BoundedResourcePool.acquireHelper(boolean)` |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-06 |
| Estimate | `positive` — for one S3A prefetching stream reading a file larger than one block, the check caps the number of heap `ByteBuffer`s the stream ever allocates at `size = fs.s3a.prefetch.block.count + 1`, each `fs.s3a.prefetch.block.size` bytes, so the stream's prefetch-buffer heap is bounded by `(count + 1) × block.size`. The cap is per stream, not per JVM (N open streams hold up to N times that), and does not cover files ≤ one block (read whole into memory by another path). |
| Ground | — |

> Stem parts: constraint `fs.s3a.prefetch.block.count`; function `acquireHelper` (the method
> enclosing the given if, which is the enforcement point); operand `size` (the limit-side operand of
> `createdItems.size() < size`).

## A. Constraint trace

**A1. The constraint.**
- Name: `fs.s3a.prefetch.block.count` (exact key, no placeholder).
- Kind: configuration key (S3A client).
- Declared: [`Constants.java:1648`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/Constants.java#L1648)
  (`PREFETCH_BLOCK_COUNT_KEY`), default constant `PREFETCH_BLOCK_DEFAULT_COUNT = 8` at
  `Constants.java:1649`. There is **no** `core-default.xml` entry for any `fs.s3a.prefetch.*` key
  (grep of `hadoop-common/src/main/resources/core-default.xml` finds none), so the Java default 8
  wins. Documented in `hadoop-tools/hadoop-aws/src/site/markdown/tools/hadoop-aws/prefetching.md:44-45`.
- Unit: number of blocks (count). Minimum 1, enforced by `S3AUtils.intOption(..., 1)`
  (`PrefetchingInputStreamFactory.java:75-76`, `S3AUtils.java:903-910`) and again by
  `PrefetchOptions.java:46`.
- Derivation to the pool size: `S3ACachingInputStream.java:84-85` sets
  `numBlocksToPrefetch = count` and `bufferPoolSize = numBlocksToPrefetch + 1`; passed through
  `BlockManagerParameters.withBufferPoolSize` (`BlockManagerParameters.java:160-162`) to
  `CachingBlockManager.java:119,128` → `new BufferPool(bufferPoolSize, blockSize, stats)` →
  `BufferPool.java:100` → `new BoundedResourcePool<ByteBuffer>(size)` → field `size`
  (`BoundedResourcePool.java:60`).
- Co-sources (name only, the user tunes `block.count`): `fs.s3a.prefetch.block.size`
  (`Constants.java:1642-1643`, default 8 MiB, the per-buffer byte size, `PrefetchingInputStreamFactory.java:70-74`);
  `fs.s3a.input.stream.type` (`Constants.java:1583`) must be `prefetch` for any of this to run
  (default stream type is `classic`, `StreamIntegration.java:79`), or the deprecated
  `fs.s3a.prefetch.enabled=true` (`Constants.java:1628`, mapped in `StreamIntegration.java:140-143`).
- How set: `core-site.xml` (or per-bucket `fs.s3a.bucket.<b>.prefetch.block.count`), `-D` on the
  client command line, or a job/Configuration property. Read once when the S3A filesystem's
  stream factory is initialised (`serviceInit`, `PrefetchingInputStreamFactory.java:68-81`), so a
  change needs a new `FileSystem` instance / new client JVM; no daemon restart is involved.
- Reader: the S3A client JVM — `hadoop fs`, `distcp`, any MapReduce/Spark task or daemon that
  opens an `s3a://` file for reading.

**A2. What it caps.** Client JVM **heap**: the per-stream pool of heap `ByteBuffer`s
(`ByteBuffer.allocate(bufferSize)`, `BufferPool.java:103`) into which S3 object blocks are read and
prefetched. The quantity compared at the check is `createdItems.size()` = number of buffers this
stream's pool has created so far; limit `size = count + 1`. Memory bound per stream =
`(count + 1) × block.size` (default 9 × 8 MiB = 72 MiB). The source comments state the same
intent (`CachingBlockManager.java:66-69`, `Constants.java:1636-1637`).

**A3. Mechanism.**
1. `S3ACachingInputStream.ensureCurrentBuffer` issues up to `numBlocksToPrefetch` prefetch
   requests after the current block (`S3ACachingInputStream.java:159-175`) and then
   `blockManager.get(current)` (`:177-180`).
2. Prefetch: `CachingBlockManager.requestPrefetch` → `bufferPool.tryAcquire(b)`
   (`CachingBlockManager.java:265`); if null, the prefetch is silently skipped (`:266-268`).
   Synchronous read: `CachingBlockManager.get` → `bufferPool.acquire(b)` (`:159`), which retries
   `tryAcquire` with a `Retryer` up to 600 s and, on status ticks, force-releases the READY block
   farthest from the wanted one (`BufferPool.java:125-150, 222-241`).
3. `BufferPool.acquireHelper` first releases DONE blocks and reuses an existing buffer for the same
   block (`BufferPool.java:181-189`), then asks the bounded pool (`:191`).
4. `BoundedResourcePool.acquireHelper` (`BoundedResourcePool.java:165-194`): reuse a free buffer
   from `items` (`:169-172`); otherwise, under the `createdItems` lock, **the check**
   [`BoundedResourcePool.java:176`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/BoundedResourcePool.java#L176)
   `if (createdItems.size() < size)`:
   - true → `createNew()` (= `ByteBuffer.allocate(blockSize)` + `memoryAllocated` gauge,
     `BufferPool.java:102-105`), record it in `createdItems`, return it (`:177-179`);
   - false (limit reached) → no allocation; `tryAcquire` returns `null` (`:191-192`), `acquire`
     blocks on `items.take()` until a buffer is released (`:183-190`).
5. Release returns buffers to `items` (`BoundedResourcePool.java:89-111`) — never frees them; the
   pool keeps up to `size` buffers alive until `BufferPool.close()` (`BufferPool.java:257-275`),
   called from `CachingBlockManager.close()` / `S3ACachingInputStream.close()`
   (`S3ACachingInputStream.java:105-112`).
- Bypasses / overshoot: (a) files with length ≤ `block.size` use `S3AInMemoryInputStream`
  (`S3APrefetchingInputStream.java:111-118`), which allocates one `ByteBuffer` of the whole file
  (`S3AInMemoryInputStream.java:70`) and never touches the pool; (b) the cap is per stream (a new
  `BufferPool` per `CachingBlockManager`), so there is no JVM-wide cap; (c) the check and the add
  are under one lock, so there is no race overshoot; `createdItems` is only cleared at close.
  (d) `ByteBuffer.duplicate()` views (`BufferPool.java:178`, `CachingBlockManager.java:529`) share
  memory, adding no heap.

**A4. Other consumers.** Other S3A heap/disk users not governed by this key: the on-disk block
cache `SingleFilePerBlockCache` (bounded separately by `fs.s3a.prefetch.max.blocks.count`, default
4, `Constants.java:1684-1690`, files under `fs.s3a.buffer.dir`/`hadoop.tmp.dir`); the 64 KiB copy
buffer per read in `S3ARemoteObjectReader.java:50,152`; AWS SDK HTTP buffers; the in-memory
small-file stream (A3a); classic/analytics streams; S3A output (upload) buffers
(`fs.s3a.fast.upload.buffer`). The key also sizes the prefetch thread requirement
(`PrefetchingInputStreamFactory.java:103`), which is threads, not memory.

**A5. Evidence beyond the source.** `prefetching.md` (in tree, `hadoop-tools/hadoop-aws/src/site/markdown/tools/hadoop-aws/prefetching.md:44-45, 158-170`):
"The size of this pool is = prefetch block count + 1"; Hadoop 3.4.2 docs
https://hadoop.apache.org/docs/r3.4.2/hadoop-aws/tools/hadoop-aws/prefetching.html; existing tests
`TestBoundedResourcePool`, `TestBufferPool` (hadoop-common) and `TestS3ACachingBlockManager`,
`S3APrefetchFakes` (hadoop-aws). Feature origin: HADOOP-18028 (S3A prefetching input stream),
https://issues.apache.org/jira/browse/HADOOP-18028 (cited for history, not relied on for the trace).

## B. Verification solution

**B1. Claim under test.** For an S3A prefetching stream over a file larger than one block, the
number of prefetch `ByteBuffer`s ever allocated by that stream never exceeds
`fs.s3a.prefetch.block.count + 1`, so the stream's retained prefetch heap is at most
`(count + 1) × fs.s3a.prefetch.block.size` and grows with `count`. The claim is wrong if the
created-buffer count (unit) or the client's retained heap attributable to the stream (cluster)
exceeds that bound, or does not change when `count` changes while the workload is held fixed.

### B2. Unit tier

**B2a. Environment and build.** JDK 8, Maven 3.3+. Copy the tree to local disk
(`rsync -a <src>/ /mydata/<run>/hadoop-3.4.2/`); build:
`mvn -pl hadoop-tools/hadoop-aws -am install -DskipTests -Dmaven.javadoc.skip=true`.
New test class `hadoop-tools/hadoop-aws/src/test/java/org/apache/hadoop/fs/s3a/prefetch/TestPrefetchPoolBound.java`
(package `org.apache.hadoop.fs.s3a.prefetch`, so it can use `S3APrefetchFakes` and the
package-visible/protected accessors). Run:
`mvn -pl hadoop-tools/hadoop-aws test -Dtest=TestPrefetchPoolBound -Dsurefire.failIfNoSpecifiedTests=false`
(unit test; no S3 credentials needed, the fakes use `MockS3ARemoteObject`). JVM: surefire default
heap is enough (worst case 17 × 1 MiB).

> **Amendment A1 (2026-11-06, stage-4 audit, before any reading) — node paths and commands.** On the stage-4 node (`pc39`,
> Jingsong's stage-4 `environment.md`) the working tree is `/mydata/jingsong-s4/fs.s3a.prefetch.block.count-acquireHelper-size-run1``/src`, made by `copy-source.sh`; no `install` build is
> needed (all 3.4.2 modules are in `~/.m2`). The test class (harness `TestPrefetchPoolBound.java`) is copied to the path above and
> run from `hadoop-tools/hadoop-aws` with `mvn -B test -Dtest=TestPrefetchPoolBound -DfailIfNoTests=false` (JDK 8, surefire's
> default `-Xmx2048m`). The Hadoop build returns 0 on test failures, so the run reads the surefire count
> (`Tests run: N, Failures: 0, Errors: 0`), not the exit code. Script: harness `unit-run.sh`.

**B2b. Knobs.** `prefetchBlockCount` ∈ {1, 2, 4, 8, 16} (min, small, default-ish, default,
double) passed as the last argument of `S3APrefetchFakes.createS3CachingInputStream(...)`
(this is exactly what `PrefetchingInputStreamFactory` would derive from
`fs.s3a.prefetch.block.count`). Fixed: `prefetchBlockSize = 1 MiB` (1048576),
`fileSize = 64 MiB` (64 blocks, so the file is far larger than any pool).

**B2c. Workload.** Per knob value: `ExecutorServiceFuturePool` over a
`Executors.newFixedThreadPool(32)` (more threads than any pool so threads are never the limit);
open the fake caching stream; read it sequentially in 64 KiB chunks to EOF, **with a
`Thread.sleep(20)` after each 1 MiB consumed**, so prefetches (fake read delay ≤100 ms,
`S3APrefetchFakes.java:377-381`) run ahead and each block's read requests `count` prefetches
(`S3ACachingInputStream.java:159-175`). Demand = 1 current + `count` prefetched blocks per step,
i.e. exactly `count + 1`, plus stale READY/DONE blocks not yet released — so the pool is driven to
its limit on every step. Second sub-workload (pressure past the limit): after each `seek` back to
a random earlier offset and read 1 byte (random reads put blocks into CACHING and keep them
allocated longer), 100 times.

> **Amendment A2 (2026-11-06, stage-4 audit, before any reading) — the random sub-workload, exactly.** On the same stream,
> after the sequential pass reaches EOF: 100 iterations of `seek(off)` and one `read()`, with `off` drawn by
> `new Random(20261106L + count).nextInt(fileSize)`; the byte read must equal `MockS3ARemoteObject.byteAtOffset(off)`. No sleep
> between iterations: the pressure comes from blocks left in CACHING by out-of-order reads (`S3ACachingInputStream.java:135-151`,
> `CachingBlockManager.java:295-306`). Each test method has a 300 s JUnit timeout (stop condition).

**B2d. Observables and instruments.** Operand of the check: `createdItems.size()`. It is exposed
through `stream.toString()` → `CachingBlockManager.toString()` → `BufferPool.toString()` →
`BoundedResourcePool.toString()` which prints `size = %d, #created = %d`
(`BoundedResourcePool.java:154-158`). Parse both numbers with a regex
`size = (\d+), #created = (\d+)`; sample after every 1 MiB read and keep the max of `#created`
and the printed `size`. Secondary (memory): `retainedBytes = maxCreated × blockSize`. Optional
heap cross-check: `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed()` after
`System.gc()` before open, at peak, and after `close()` — noisy, used only as a relation.
Not observable directly: per-buffer identity (only counts).

> **Amendment A3 (2026-11-06, stage-4 audit, before any reading) — direct observation of the operand and of the disallow
> branch.** Sampling `toString()` once per MiB can miss short peaks and cannot show the false branch. The test also wraps the fake
> block manager (a `FakeS3ACachingBlockManager` subclass returned by an overridden `createBlockManager` of a
> `FakeS3ACachingInputStream` subclass) and, read-only through reflection on `CachingBlockManager.bufferPool` and `BufferPool.pool`,
> records after every `requestPrefetch(b)` and `get(b)` call `numCreated()` (= `createdItems.size()`, under its lock) and the
> pool's `size` field. A **denial** is a `requestPrefetch(b)` call for a block that held no buffer before the call and still holds
> none after it: `BufferPool.tryAcquire` returned null (`CachingBlockManager.java:265-268`), which at a full pool
> (`numCreated == size`) is the false branch of `BoundedResourcePool.java:176` followed by `return null` (`:191-192`). Only the
> reader thread acquires or releases buffers, so nothing else changes the pool between the two looks. Heap = `MemoryMXBean` used
> heap after `System.gc()`, sampled before open, after 32 MiB read (pool saturated), and after `close()`. Output: one line per count,
> `IFCHK,count,printedSize,poolSize,seqMaxCreated,rndMaxCreated,hookMaxCreated,seqDenials,rndDenials,denialsAtFull,crcSeq,rndMismatches,heapBefore,heapPeak,heapAfter`,
> plus `IFCHK-CTL` lines for the controls (B2h).

**B2e. Procedure.**
1. Write the test with a `@Test` per count (or a parameterised loop) doing B2c and asserting
   nothing — it logs `count, size, maxCreated, maxCreated*blockSize, heapDelta` to stdout.
2. Add a control method (B2h) with `createS3InMemoryInputStream(pool, "b", "k", 512 KiB)`.
3. Run the `mvn test` command of B2a; collect lines from
   `hadoop-tools/hadoop-aws/target/surefire-reports/*TestPrefetchPoolBound-output.txt`.
4. Shut down the executor in `@After`; `close()` every stream.

**B2f. Predictions.**

| count | printed `size` | max `#created` | retained bytes |
|---|---|---|---|
| 1 | 2 | 2 (≤ 2) | ≤ 2 MiB |
| 2 | 3 | 3 | ≤ 3 MiB |
| 4 | 5 | 5 | ≤ 5 MiB |
| 8 | 9 | 9 | ≤ 9 MiB |
| 16 | 17 | 17 | ≤ 17 MiB |

`max #created == count + 1` exactly for every value (the workload saturates the pool), and never
`> count + 1`. Heap delta at peak grows roughly by 1 MiB per extra count step and drops by about
`(count+1)` MiB after `close()` + GC.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `#created == count+1` for all counts, never higher | Claim confirmed at unit level: check caps buffer creation at the configured value. |
| `#created > size` at any sample | Claim wrong: check is bypassed or racy. |
| `#created < count+1` for large counts | Workload did not saturate (prefetch too fast / thread pool too small) — not a refutation; slow the consumer or raise threads and rerun. |
| `#created` the same for all counts | Claim wrong: key does not reach the pool (or test wiring wrong; check printed `size`). |
| heap delta not monotone in count | Noise or GC timing; rely on `#created`. |

> **Amendment A4 (2026-11-06, stage-4 audit, before any reading) — predictions in numbers and a verdict for every row.**
> Added to B2f: `hookMaxCreated == count + 1` and `≤ poolSize` for every count; `denialsAtFull == rndDenials`; `rndDenials ≥ 1` for at
> least one count (the disallow branch fired); `rndMismatches = 0`; `crcSeq` the same for all counts. Heap: with
> `Δ(c) = heapPeak − heapBefore` (it includes the fake object's 64 MiB `contents` array, `MockS3ARemoteObject.java:65-68`, the same
> for every count), `Δ(c) − Δ(1) = (c − 1) MiB ± 4 MiB`, and `heapPeak − heapAfter ≥ (c + 1) MiB − 4 MiB`.
> Verdicts, in order (the first row that matches): (i) **Invalid run** — a test fails or errors, `crcSeq` differs between counts,
> `rndMismatches > 0`, a printed `size ≠ count + 1` (wiring), or the `count = 0` control is not rejected. (ii) **Refuted** — any
> `#created` (printed or hook) `> size`, or `max #created` the same for all counts. (iii) **Not confirmed (not saturated)** —
> `max #created < count + 1` for some count. (iv) **Not confirmed (disallow never observed)** — `rndDenials = 0` for every count:
> the limit was never passed. (v) **Not confirmed (counter capped, heap not)** — `Δ(c) − Δ(1) > (c − 1) MiB + 4 MiB` for some count.
> (vi) **Confirmed** — none of the above: `#created == count + 1`, never more, at least one denial at a full pool, heap follows
> `count`. A heap reading that misses only on the low side is recorded as an instrument note and does not change (vi), since
> `#created × blockSize` is the pool's exact allocation (`BufferPool.java:102-105`). Effect on the constraint for (vi): `caps`.

**B2h. Controls.** (1) Printed `size` must equal `count + 1` — shows the knob reached the pool.
(2) In-memory control: a 512 KiB file with block size 1 MiB goes through
`S3AInMemoryInputStream` and shows no pool (its `toString` has no `#created`) — confirms the
bypass in A3a and that the bound applies only to the caching path. (3) Same file read with
`count = 1` vs `16` gives identical data (checksum) — rules out reads failing early.
(4) Pool size 1 is impossible (min count 1 → size 2); `count = 0` must fail
`PrefetchOptions` validation (negative control of the knob path).

### B3. Cluster tier

The constraint lives in the S3A **client**, not in an HDFS/YARN daemon, so "the actual resource" is
the heap of a real Hadoop client JVM started from the built distribution reading from an S3
endpoint. No AWS account is needed: use a local S3-compatible server (MinIO) as the object store.

**B3a. Environment and build.** One Linux host, ≥ 8 GB RAM, ≥ 10 GB free local disk.
- Build: in the local copy, `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`;
  unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop-3.4.2`
  (`HADOOP_HOME`).
- `etc/hadoop/hadoop-env.sh`: `export HADOOP_OPTIONAL_TOOLS="hadoop-aws"`,
  `export HADOOP_LOG_DIR=/mydata/<run>/logs`.
- Object store: MinIO server binary (https://min.io/docs/minio/linux/index.html) run as
  `MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD=minioadmin minio server /mydata/<run>/minio --address 127.0.0.1:9000`;
  create bucket `prefetch` with `mc mb local/prefetch` (or `hadoop fs -mkdir s3a://prefetch/` will
  not create buckets — use `mc`).
- `etc/hadoop/core-site.xml`:
  `fs.s3a.endpoint=http://127.0.0.1:9000`, `fs.s3a.endpoint.region=us-east-1`,
  `fs.s3a.path.style.access=true`, `fs.s3a.connection.ssl.enabled=false`,
  `fs.s3a.access.key=minioadmin`, `fs.s3a.secret.key=minioadmin` (local throwaway credentials),
  `fs.s3a.input.stream.type=prefetch`, `fs.s3a.prefetch.block.size=32M`,
  `fs.s3a.buffer.dir=/mydata/<run>/s3a-buf`, `hadoop.tmp.dir=/mydata/<run>/tmp`.
  No HDFS/YARN daemons are needed (none started).
- Client JVM options: `export HADOOP_CLIENT_OPTS="-Xms64m -Xmx<X> -XX:+UseParallelGC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/mydata/<run>/dumps"`.

> **Amendment A5 (2026-11-06, stage-4 audit, before any reading) — node, object store and tools.** (a) Node `pc39`; run folder
> `R=``/mydata/jingsong-s4/fs.s3a.prefetch.block.count-acquireHelper-size-run1`; no new build: `cp -a` of the built distribution (Jingsong's stage-4 `environment.md` §3) to `$R/hadoop`;
> `HADOOP_CONF_DIR=$R/conf` (`cp -r` of `etc/hadoop`, with the B3a `core-site.xml` and `hadoop-env.sh` lines and `JAVA_HOME` = JDK 8).
> (b) MinIO cannot be installed here (`dl.min.io` answers HTTP 410 for the server binary; no `mc`): the S3-compatible endpoint is
> **S3Proxy 2.1.0** (`org.gaul:s3proxy:2.1.0`, `jar-with-dependencies`, from Maven Central, sha1 `40f6b0b64077ed09e43172504bd7fc9cc4a29ab9`),
> filesystem backend under `$R/s3store`, JDK 11, `-Xmx1g`, bound to `127.0.0.1:9000`, identity/credential `minioadmin`/`minioadmin`;
> the bucket is the directory `$R/s3store/prefetch`. It is a separate JVM; only the client JVM is measured. (c) `pv` is not installed:
> harness `throttle.py <MiB/s>` (reads stdin in 1 MiB chunks, sleeps to hold the rate, discards the data, prints the byte count)
> replaces `pv -q -L <rate> > /dev/null`. (d) Heap dumps are read by harness `hprof_count.py` (counts live `byte[]` by exact
> length in the HPROF file) instead of MAT/jhat. Script: harness `cluster-run.py`.

**B3b. Knobs.** `fs.s3a.prefetch.block.count` ∈ {1, 4, 8, 16}, passed per run as
`-Dfs.s3a.prefetch.block.count=<n>` on the `hadoop fs` command (generic option; no restart, each
run is a new JVM). Fixed `block.size = 32 MiB` so the pool is large relative to baseline heap.
Second knob for the bound test: client `-Xmx` ∈ {large = 1g, tight = 256m}.

**B3c. Workload.** Upload one 2 GiB object:
`dd if=/dev/urandom of=/mydata/<run>/data/obj.bin bs=1M count=2048` then
`hadoop fs -put /mydata/<run>/data/obj.bin s3a://prefetch/obj.bin` (put uses the output path, not
the prefetch stream). Read it through the client with a slowed consumer so prefetches run ahead
and the pool fills:
`hadoop fs -Dfs.s3a.prefetch.block.count=<n> -cat s3a://prefetch/obj.bin | pv -q -L 40m > /dev/null`
(≈ 50 s at 40 MiB/s; `pv` back-pressure stalls the reader while prefetch threads fill buffers).
Arithmetic: pool = (n+1)×32 MiB → n=1: 64 MiB, n=4: 160 MiB, n=8: 288 MiB, n=16: 544 MiB; file =
64 blocks, so every n is reached. Tight-heap run: `-Xmx256m` with n=8 (288 MiB > 256 MiB) and with
n=4 (160 MiB fits).

> **Amendment A6 (2026-11-06, stage-4 audit, before any reading) — heap layout of the tight runs, controls, stop conditions.**
> (a) With `-XX:+UseParallelGC -Xmx256m` the old generation is about 171 MiB and a 32 MiB array cannot stay in a ~64 MiB eden, so
> the n=4 run (160 MiB of pool plus the client's baseline) could fail for a generational reason, not because of the cap. The tight
> runs use `-Xmx256m -Xmn32m` (old generation 224 MiB): n=4 needs 160 MiB of pool, n=8 needs 288 MiB, more than the whole heap.
> (b) "Completes" = exit status 0 of `hadoop fs -cat` and `throttle.py` counting 2147483648 bytes; "fails with OOM" =
> `java.lang.OutOfMemoryError` in the client's stderr (exit status recorded). (c) Every read run is sampled until the client
> exits; stop condition 300 s per run (then killed and recorded). (d) Controls: classic stream (B3h 1) at n=1 and n=16, `-Xmx1g`,
> dump at 10 s and histograms as for the prefetch runs; small file (B3h 3): a 16 MiB object read at n=1 and n=16 through
> `throttle.py 1` (1 MiB/s) so the stream is still open at the dump, taken at 5 s; local baseline (B3h 5):
> `hadoop fs -cat file://$R/data/obj.bin` at `-Xmx1g`, histograms only.
>
> **Amendment A7 (2026-11-06, stage-4 audit, before any reading) — a pressure workload on the real client (direct disallow
> evidence).** A sequential `-cat` never asks for more than `n + 1` buffers: when block b is entered, block b−1 has just been
> released (`S3ACachingInputStream.java:135-140`) and its buffer is reused by `items.poll()` (`BoundedResourcePool.java:169-172`)
> before the check is reached, so the false branch of `:176` is not exercised and the direct evidence that the disallow branch fired
> is missing. Added: harness `RandomReads.java`, a client run through the distribution (`hadoop RandomReads …`, `HADOOP_CLASSPATH`
> = its compiled class, same `core-site.xml`, `-Xmx1g`). It opens `s3a://prefetch/obj.bin` with `fs.s3a.prefetch.block.count` =
> n ∈ {1, 8} and does 100 iterations of `seek(off)` and `readFully` of 1 MiB, `off = floorMod(new Random(20261106L + n).nextLong(),
> fileSize − 1 MiB)`, comparing the bytes with the local copy `$R/data/obj.bin`. A sampler thread in the same JVM, every 1 ms,
> records (1) the operand: `numCreated()` of the stream's `BoundedResourcePool` and its `size` (read-only reflection through
> `S3APrefetchingInputStream.inputStream` → `S3ACachingInputStream.blockManager` → `CachingBlockManager.bufferPool` →
> `BufferPool.pool`; `numCreated()` locks only `createdItems`), and (2) a **wait sample**: the main thread's stack has
> `Retryer.continueRetry` called from `BufferPool.acquire` — that loop continues only when `tryAcquire` returned null
> (`BufferPool.java:125-141`), i.e. no free buffer and the check at `:176` false. Output:
> `IFCHK-RR,n,size,maxCreated,waitSamples,maxCreatedAtWait,bytesRead,mismatches,samples`. Histograms every 2 s as for the
> sequential runs. Prediction: `size = n + 1`, `maxCreated ≤ n + 1` in both runs; `waitSamples ≥ 1` in at least one, with
> `maxCreatedAtWait = n + 1`; `[B` rise ≤ (n + 1) × 32 MiB + 16 MiB; `mismatches = 0`.
>
> **Amendment A10 (2026-11-06, stage-4 run 1, runbook defect; B1, B3f, B3g and A7's prediction unchanged).** `hadoop RandomReads …`
> cannot run as written: the `hadoop` script accepts a user class only if its name contains a dot
> (`hadoop_validate_classname`, `libexec/hadoop-functions.sh:1107-1119`) and printed its usage instead. The class is now
> `ifchk.RandomReads` (package `ifchk`), run as `hadoop ifchk.RandomReads …`. The cluster tier restarts from its beginning.
>
> **Amendment A11 (2026-11-06, stage-4 run 1, instrument defect; B1, B3f, B3g and A7's prediction unchanged).** When a run reaches
> the A6c stop condition (300 s) the client is killed, and `RandomReads` printed its readings only on a normal exit, so a killed
> run left none. `RandomReads` now also prints, every 1 s from its sampler thread and flushed,
> `IFCHK-RR-PROGRESS,n,size,maxCreated,waitSamples,maxCreatedAtWait,iterations,bytesRead,mismatches,samples,mainState=…`; for a
> killed run the last such line is its reading. Before any timeout kill the harness saves `jstack <pid>` to `<run>.jstack`. The
> cluster tier restarts from its beginning.

**B3d. Observables and instruments.**
- Retained heap of the client JVM: `jcmd <pid> GC.class_histogram` every 2 s (find pid via
  `jps -l | grep FsShell`); record the `[B` (byte[]) total bytes and instance count, and
  `jstat -gc <pid> 1000` (OU+EU+S0U+S1U) for heap used. A `ByteBuffer.allocate` buffer is a
  `byte[]` of exactly 32 MiB; count large arrays with
  `jcmd <pid> GC.heap_dump /mydata/<run>/dumps/n<n>.hprof` at mid-run (one per n) and, offline,
  count `byte[]` of length 33554432 (Eclipse MAT or `jhat` OQL
  `select a from [B a where a.length == 33554432`).
- S3A gauge `stream_read_active_memory_in_use` (`StreamStatisticNames.java:461-462`, updated by
  `memoryAllocated`/`memoryFreed`, `S3AInstrumentation.java:1438-1445`): printed at stream close
  when `-Dfs.iostatistics.logging.level=info` is passed (`CommonConfigurationKeys.java:465`);
  read its max value.
- OOM: exit status of `hadoop fs -cat` and `java.lang.OutOfMemoryError` in stderr.
- Not observable directly: which byte[] belongs to the pool versus SDK buffers (use the exact
  33554432 length as the discriminator).

> **Amendment A8 (2026-11-06, stage-4 audit, before any reading) — the gauge, the heap rise, tolerances.** (a)
> `stream_read_active_memory_in_use` cannot show a peak at close: `BufferPool.close()` calls `memoryFreed(numCreated × bufferSize)`
> (`BufferPool.java:258-274`) before the stream's statistics reach the filesystem's, which are logged at `close()`
> (`S3AFileSystem.java:4422`), so the logged value is 0 by construction. It is recorded as an informational line only; the B3f gauge
> column is not used for a verdict. (b) `[B` rise of a run = maximum `[B` bytes over its histograms − maximum `[B` bytes over the
> classic-control run at n=1 (same `-Xmx1g`); "≈" in B3f = within ±16 MiB. (c) Array counts come from the live-object dump
> (`jcmd <pid> GC.heap_dump <file>`, live objects by default) at 10 s; "= n+1" is exact. (d) The pid is the `jps -l` entry
> `org.apache.hadoop.fs.FsShell` (or `RandomReads`) of this run.

**B3e. Procedure.**
1. Build, unpack, configure (B3a); start MinIO; create bucket; upload object (B3c).
2. For n in 1 4 8 16 with `-Xmx1g`: start the read pipeline in background; after 10 s take the
  heap dump; sample `jcmd GC.class_histogram` and `jstat` every 2 s until exit; save
  `/mydata/<run>/out/n<n>.*`.
3. Tight-heap runs: `-Xmx256m`, n=4 then n=8; record exit status and OOM.
4. Control runs (B3h).
5. Stop: `pkill -f "minio server"`; `jps` shows no FsShell; remove `/mydata/<run>/data`,
   `/mydata/<run>/minio`, dumps after analysis.

**B3f. Predictions.**

| n | pool bound | 32 MiB byte[] in mid-run dump | peak `stream_read_active_memory_in_use` | `[B` bytes rise over baseline |
|---|---|---|---|---|
| 1 | 64 MiB | 2 | 67108864 | ≈ 64 MiB (+ small SDK buffers) |
| 4 | 160 MiB | 5 | 167772160 | ≈ 160 MiB |
| 8 | 288 MiB | 9 | 301989888 | ≈ 288 MiB |
| 16 | 544 MiB | 17 | 570425344 | ≈ 544 MiB |

Count of 32 MiB arrays ≤ n+1 always and = n+1 when saturated; heap rise roughly linear in n with
slope ≈ 32 MiB per count. Tight heap (256 MiB): n=4 completes; n=8 fails with
`OutOfMemoryError: Java heap space` (pool needs 288 MiB). Wrong if: more than n+1 such arrays, or
the n=8/256m run completes with the gauge above 256 MiB, or the heap rise is flat across n.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| 32 MiB arrays = n+1, gauge = (n+1)×32 MiB, heap linear in n | Confirmed: the key caps the stream's prefetch heap at (n+1)×block.size. |
| arrays or gauge > (n+1)×32 MiB | Refuted: buffers created past the check. |
| heap / arrays flat across n | Refuted (or the stream is not the prefetch one — check the control 1). |
| fewer than n+1 arrays at large n | Pool not saturated (consumer too fast); lower `pv -L`, rerun — not a refutation. |
| n=8 at 256m OOMs, n=4 completes | Confirms the cap scales and binds heap need. |
| n=8 at 256m completes with gauge ≤ 256 MiB | Pool not filled; inconclusive, re-check saturation. |

> **Amendment A9 (2026-11-06, stage-4 audit, before any reading) — a verdict for every row, and the missing rows.** In order
> (the first row that matches): (i) **Invalid run** — the classic control shows any 32 MiB array, or its `[B` maximum at n=16
> exceeds that at n=1 by ≥ 32 MiB (attribution broken); a 1g read does not deliver all bytes; or `RandomReads` reports a mismatch.
> (ii) **Refuted** — more than n+1 arrays of 32 MiB in any dump, or `maxCreated > size` in `RandomReads`; or the array count and
> `[B` rise are the same at n=1 and n=16. (iii) **Not confirmed (not saturated)** — fewer than n+1 arrays at some n (sequential
> runs). (iv) **Not confirmed (counter capped, heap not)** — n+1 arrays but a `[B` rise above `(n+1) × 32 MiB + 16 MiB` at some n.
> (v) **Not confirmed (disallow never observed)** — `waitSamples = 0` in both `RandomReads` runs. (vi) **Not confirmed (tight
> heap)** — n=4 at `-Xmx256m -Xmn32m` fails with OOM, or n=8 there completes. (vii) **Confirmed** — none of the above: n+1 arrays
> and a `[B` rise within ±16 MiB of (n+1) × 32 MiB for n ∈ {1, 4, 8, 16}, n=4 completes and n=8 fails with OOM at 256 MiB, at
> least one wait sample at a full pool. A `[B` rise below `(n+1) × 32 MiB − 16 MiB` with n+1 arrays is an instrument note (the
> arrays are counted exactly). The small-file control (B3h 3) tests the A3a bypass, not B1; a result other than one 16 MiB array
> and no 32 MiB array is recorded as feedback and does not change the row. Effect on the constraint for (vii): `caps`.

**B3h. Controls.** (1) Same read with `-Dfs.s3a.input.stream.type=classic`: no 32 MiB arrays,
gauge 0, heap rise small and independent of n — confirms the effect comes from the prefetch pool.
(2) Positive control for the measurement: n=16 must show visibly more heap than n=1 (a moving
reading). (3) Small-file bypass: `hadoop fs -cat` of a 16 MiB object (≤ block size) shows one
16 MiB array regardless of n (A3a). (4) Per-stream scope is not exercised here (`hadoop fs -cat` of several files opens them one
after another); it rests on the code (A3b) and is noted as a limit of the claim. (5) Baseline heap: the same command against a local `file://`
copy shows the non-S3A baseline.

**B4. Risks and cleanup.** Disk: 2 GiB object + MinIO copy ≈ 4 GiB, plus heap dumps up to ~1 GiB
each — all under `/mydata/<run>/`, never shared storage; delete after analysis. Port 9000 (and
MinIO console 9001) bound to 127.0.0.1 only; check free first (`ss -ltn`). Memory: client
`-Xmx1g` max. Processes: stop MinIO (`pkill -f "minio server"`), confirm with `jps` no
`FsShell`/test JVM remains and `pgrep minio` is empty; unit tier leaves only `target/` in the local
copy. Credentials are MinIO throwaway defaults on localhost only. Do not build inside the shared
source tree.

## C. Sources read

hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/BoundedResourcePool.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/BufferPool.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/CachingBlockManager.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/BlockManagerParameters.java (grep)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/BlockManager.java (grep)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/statistics/StreamStatisticNames.java (grep)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/CommonConfigurationKeys.java (grep)
hadoop-common-project/hadoop-common/src/main/resources/core-default.xml (grep)
hadoop-common-project/hadoop-common/src/main/conf/hadoop-env.sh (grep)
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/impl/prefetch/TestBufferPool.java
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/impl/prefetch/TestBoundedResourcePool.java (grep)
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/Constants.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/S3AUtils.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/S3AInstrumentation.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/impl/streams/StreamIntegration.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/PrefetchingInputStreamFactory.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/PrefetchOptions.java (grep)
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/S3APrefetchingInputStream.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/S3ACachingInputStream.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/S3ARemoteInputStream.java
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/S3AInMemoryInputStream.java (grep)
hadoop-tools/hadoop-aws/src/main/java/org/apache/hadoop/fs/s3a/prefetch/S3ARemoteObjectReader.java (grep)
hadoop-tools/hadoop-aws/src/test/java/org/apache/hadoop/fs/s3a/prefetch/S3APrefetchFakes.java
hadoop-tools/hadoop-aws/src/site/markdown/tools/hadoop-aws/prefetching.md
/users/jason92/hadoop-s3-method/playbook-autonomous.md
/users/jason92/hadoop-s3-method/_TEMPLATE-autonomous.md
https://hadoop.apache.org/docs/r3.4.2/hadoop-aws/tools/hadoop-aws/prefetching.html (cited, not fetched)
https://issues.apache.org/jira/browse/HADOOP-18028 (cited, not fetched)

## D. Stage-4 feedback

**D1. Audit amendments (2026-11-06, stage 4, before any harness run or reading).** Results file:
[`../../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md`](../../../stage4-runtime-verification/jingsong/results/fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.md).
A1 (B2a) node paths, no install build, surefire counts; A2 (B2c) the random sub-workload exactly; A3 (B2d) the operand and the
disallow branch observed directly (block-manager hook, denials), heap sample points, output columns; A4 (B2f/B2g) predictions in
numbers and a verdict for every row; A5 (B3a) node, S3Proxy instead of MinIO, `throttle.py` instead of `pv`, `hprof_count.py`
instead of MAT/jhat; A6 (B3c) `-Xmn32m` for the tight runs, completion/OOM, stop conditions, the controls exactly; A7 (B3c/B3e) a
random-read pressure client for direct disallow evidence in the real client; A8 (B3d) the gauge is 0 at close (informational
only), the `[B` rise and its tolerance; A9 (B3g) a verdict for every row and the missing rows. Filed sha256 `a31a6adf…a484c942b`;
the sha256 after A1–A9 is recorded in the results file §1. A10 (A7, 2026-11-06, run 1) fixes a runbook defect (the client
class needs a package); A11 (A7, 2026-11-06, run 1) makes the pressure client's readings survive the 300 s stop and saves a
`jstack` before a timeout kill; the cluster tier restarted after each.

**D2. Stage-4 result (2026-11-06, run 1, autonomous stage-4 session; results file above).** Unit **Not confirmed** (A4 row v),
cluster **Not confirmed** (A9 row iv, row vi also met); Effect `undetermined` on both; outcome class **undetermined** (estimate
`positive` left as filed). What the run showed: the check caps the pool exactly. Buffers created = `count + 1` for every count on both
tiers, never more. The false branch of `BoundedResourcePool.java:176` fired under pressure: 38 denied prefetches at a full pool in the
unit tier, and a real client waiting in `BufferPool.acquire:141` at a full pool, 237838 samples at n=1 and 716 at n=8. The frozen
heap tolerances failed for two reasons. (1) Unit: the first count's heap baseline was 12.5 MiB above the others (shared surefire
JVM, test order). (2) Cluster: on JDK 8 every block made READY also allocates a transient block-sized `byte[]`
(`BufferData.setReady:215` → `getChecksum:161-166` → `CRC32.update` of a read-only duplicate; 64 such 32 MiB allocations per 2 GiB
read in a JFR diagnostic), outside the check. That is one extra 32 MiB array at the `[B` peak for n = 4 and 8, and an OOM in a
prefetch thread at n=4 under `-Xmx256m -Xmn32m`, after which the reader waited for the never-finished block until killed. Also seen:
random reads with caching stalled the client at n=1 and n=8 (buffers stuck in CACHING). For a new design (stage 3 / a new audit):
take the unit heap baseline after a warm-up or with one JVM per count; in the cluster tier count in-flight checksum copies in the
heap bound, or run the client on a JDK whose `CRC32.update(ByteBuffer)` does not copy whole buffers; state the claim as "retained
pool ≤ (count+1) × block.size; transient ≤ + one block per prefetch in flight".
