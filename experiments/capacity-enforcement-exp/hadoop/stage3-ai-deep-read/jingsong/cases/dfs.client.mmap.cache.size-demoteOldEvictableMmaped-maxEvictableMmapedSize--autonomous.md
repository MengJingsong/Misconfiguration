# dfs.client.mmap.cache.size — verification solution  <!-- file: cases/dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ShortCircuitCache.java:543`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/shortcircuit/ShortCircuitCache.java#L543): `if (evictableMmapped.size() < maxEvictableMmapedSize)` in `ShortCircuitCache.demoteOldEvictableMmaped(long)` (unit kind: row; this is also the main enforcement point) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`: the check limits how many idle (unreferenced) memory-mapped block replicas a DFSClient's short-circuit cache keeps mapped. Each one is a read-only `mmap` of a whole HDFS block file (up to 2 GiB of address space, plus the file-backed pages already touched). So the key bounds the client's idle mmap footprint. From the source the effective bound is `max(S−1, 0)` entries per cache, not `S`. Mmaps still in use are not counted. |
| Ground | — |

**Naming parts.** constraint = `dfs.client.mmap.cache.size` (key string of
`HdfsClientConfigKeys.Mmap.CACHE_SIZE_KEY`); function = `demoteOldEvictableMmaped` (encloses the
given if, which is also the main enforcement point); operand = `maxEvictableMmapedSize` (the
limit-side operand as written at line 543). Kind: configuration key.

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/<full path under the repository root>#L123)`
> (a range is `#L123-L130`). Check that the line number is the line you mean. Other citations may
> stay plain `file:line`.

## A. Constraint trace

**A1. The constraint.**
- **Name:** `dfs.client.mmap.cache.size`.
- **Kind:** HDFS client configuration key.
- **Declared:** [`HdfsClientConfigKeys.java:507`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java#L507)
  (`String CACHE_SIZE_KEY = PREFIX + "cache.size";` inside `interface Mmap`, whose
  `PREFIX = "dfs.client.mmap."`, `HdfsClientConfigKeys.java:502-503`). The Java default
  `CACHE_SIZE_DEFAULT = 256` is at `HdfsClientConfigKeys.java:508`.
- **`hdfs-default.xml` entry:** `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml:2884-2899`,
  value `256`. It says the key is "the maximum number of entries that we will keep in that cache"
  and that "you can still do zero-copy reads when this size is set to 0".
- **Unit and default:** the unit is a count of cache entries, meaning mmapped block replicas. Both
  defaults are 256, so they do not conflict. When `hdfs-default.xml` is loaded (any
  `HdfsConfiguration`), its 256 is what `conf.getInt` returns. The Java constant is used only if
  the resource is absent.
- **Read path:** read once per `ShortCircuitConf` in `DfsClientConf.java:850-852`
  (`conf.getInt(Mmap.CACHE_SIZE_KEY, Mmap.CACHE_SIZE_DEFAULT)`), passed by
  `ShortCircuitCache.fromConf` (`ShortCircuitCache.java:369-378`, argument at line 373), checked
  `>= 0` and stored in the field `maxEvictableMmapedSize` (`ShortCircuitCache.java:389-391`).
  Negative values throw `IllegalArgumentException`.
- **How to set:** client side only. Use `hdfs-site.xml` on the client's classpath, `-D` on a
  `Tool`/`hadoop jar` command, or a per-`Configuration` setting. It is not reconfigurable at
  runtime. It takes effect when a new `ClientContext` is created. `ClientContext.get` caches
  contexts by `dfs.client.context` name (`ClientContext.java:210-235`), so a new value needs a new
  client JVM or a new context name. No daemon restart is needed. The NameNode and DataNode do not
  read it.
- **Which process reads it:** any process that creates a `DFSClient` with short-circuit reads on
  (`dfs.client.read.shortcircuit=true`): `hdfs dfs`, MapReduce or YARN tasks, HBase, Impala-style
  readers, tests.
- **Related keys** (not the primary constraint):
  - `dfs.client.mmap.enabled` (`HdfsClientConfigKeys.java:505-506`)
  - `dfs.client.mmap.cache.timeout.ms` (`:509-510`, default 60 min): time-based demotion at the
    same place.
  - `dfs.client.read.shortcircuit.streams.cache.size` (default 256): the `maxTotalSize` that also
    trims the mmapped list, see A3.
  - `dfs.client.short.circuit.num` (`HdfsClientConfigKeys.java:154-155`, default 1): the number of
    `ShortCircuitCache` instances per context, each with its own limit (`ClientContext.java:168-170`).

**A2. What it caps.**
- **Resource:** HDFS-client process memory, specifically memory-mapped (off-heap, file-backed)
  regions. `ShortCircuitReplica.loadMmapInternal()` maps the whole block data file read-only
  (`ShortCircuitReplica.java:277-283`, `channel.map(READ_ONLY, 0, min(Integer.MAX_VALUE, size))`).
  Each mapping costs:
  - virtual address space equal to the block length (VmSize), and
  - resident file-backed pages for whatever the reader touched (RssFile / `Rss` of the VMA), until
    `munmap`.
- **Quantity compared:** `evictableMmapped.size()`, the number of replicas that still hold a
  mapping and that no reader references (refCount == 1, held only by the cache). These are counted
  per `ShortCircuitCache`.
- **Not compared:** mmaps currently referenced by a reader (a `ClientMmap` not yet released or a
  live block reader) are not in `evictableMmapped` and are not counted.

**A3. Mechanism.**

How a replica gets into the list and how the check trims it:

1. **Creating a mapping.** A zero-copy read `FSDataInputStream.read(ByteBufferPool, int, EnumSet<ReadOption>)`
   goes through `DFSInputStream.read` (`DFSInputStream.java:1803`) and `tryReadZeroCopy`
   (`:1841`, only if `dfs.client.mmap.enabled`), then `BlockReaderLocal.getClientMmap`
   (`BlockReaderLocal.java:677-697`). That calls `ShortCircuitCache.getOrCreateClientMmap`
   (`ShortCircuitCache.java:846-896`), which maps the file, increments `outstandingMmapCount`
   (line 887), stores the `MappedByteBuffer` in `replica.mmapData` and refs the replica.
2. **Unreferencing.** `releaseBuffer` (`DFSInputStream.java:1917-1929`) closes the `ClientMmap`,
   which unrefs the replica. The stream's block reader is closed when the stream moves to the next
   block (`blockSeekTo`, `DFSInputStream.java:611`) or is closed (`:746`). When `unref` brings
   refCount down to 1 and the replica still `hasMmap()`, it is appended to `evictableMmapped`
   (`ShortCircuitCache.java:496-498`) and `trimEvictionMaps()` runs (`:516-517`).
3. **Trimming.** `trimEvictionMaps` (`:568-587`) first calls `demoteOldEvictableMmaped(now)`
   (`:532-563`). The loop takes the eldest entry:
   - If it is younger than `dfs.client.mmap.cache.timeout.ms` (line 542), the size check runs:
     [`ShortCircuitCache.java:543`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/shortcircuit/ShortCircuitCache.java#L543)
     `if (evictableMmapped.size() < maxEvictableMmapedSize) break;`.
   - **Under the limit:** stop, and the entries stay mapped.
   - **At or over the limit** (`size >= max`): set `needMoreSpace` and demote the eldest:
     - remove it from `evictableMmapped` (line 557);
     - `munmap` it (line 558 → `:594-597` → `ShortCircuitReplica.munmap`
       `ShortCircuitReplica.java:221-224` → `NativeIO.POSIX.munmap`, which frees the mapping
       through `CleanerUtil`, `NativeIO.java:491-501`);
     - decrement `outstandingMmapCount`;
     - re-insert the replica, with its file descriptors still open, into the non-mmapped
       `evictable` map (line 559).
   - The loop repeats until the eldest is young and the size is below the limit.
   - Expired entries are demoted regardless of size.
4. **Effective bound.** The loop stops only when `size < max`, so right after every insertion
   `evictableMmapped.size() ≤ max(S−1, 0)`. `S = 0` and `S = 1` both keep no idle mmaps, and the
   default 256 keeps at most 255. This is one less than `hdfs-default.xml` states. It is a
   prediction from the source and stage 4 should confirm it.
5. **Background thread.** The cache cleaner thread also calls `demoteOldEvictableMmaped`
   (`ShortCircuitCache.java:110`), every `min(streams expiry, mmap timeout)/4` ms (`:155-160`).
6. **Shutdown.** On `close()` the limit is forced to 0 and everything is purged (`:909-920`).

Paths that bypass or overshoot the cap:
- **In-use mmaps.** Mappings that are referenced (not yet released buffers, or the current block
  reader's replica) are never counted. A client that holds many zero-copy buffers maps without
  bound, limited only by the number of blocks it has open buffers for.
- **Per cache, not per process.** The limit applies per `ShortCircuitCache`. With
  `dfs.client.short.circuit.num = k`, or with several `ClientContext`s (different
  `dfs.client.context` names; a differing conf under the same name only logs a warning,
  `ClientContext.java:218-219`), the process total is `k × (S−1)` per context.
- **Unmap not available.** If `CleanerUtil.UNMAP_SUPPORTED` is false (`CleanerUtil.java:75-86`),
  `munmap` only logs at TRACE (`NativeIO.java:498-500`). The entry leaves the list, but the mapping
  stays until the `MappedByteBuffer` is garbage-collected. The count is capped but the memory is
  not.
- **Close path.** A replica closed through `purge` → `unref` → `close` is unmapped directly by
  `ShortCircuitReplica.close` (`ShortCircuitReplica.java:241-242`), without decrementing
  `outstandingMmapCount`. The counter can then read high. The `/proc` mapping count is the reliable
  instrument.
- **Second, tighter cap.** `trimEvictionMaps` also purges from `evictableMmapped` when
  `evictable.size() + evictableMmapped.size() > maxTotalSize` (streams cache size,
  `ShortCircuitCache.java:572-585`). That key can therefore cap mmaps below `S`.

**A4. Other consumers.**
- Mmaps held by readers in use (not capped, A3).
- The page cache itself. Kernel-owned; `munmap` drops the process's mapping and its RssFile
  attribution, but the pages may stay cached.
- DataNode-side mmaps for centralized cache management, capped by
  `dfs.datanode.max.locked.memory`, a different process.
- Client heap: replica objects and file descriptors of demoted replicas, which stay in `evictable`
  under `dfs.client.read.shortcircuit.streams.cache.size` and its expiry.
- Short-circuit shared-memory segments (`DfsClientShmManager`, `/dev/shm`).
- Mmaps from other code in the same JVM.

**A5. Evidence beyond the source.**
- `hdfs-default.xml:2884-2899` (description of the key).
- `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md:31` (zero-copy
  read API).
- Existing tests:
  - `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/fs/TestEnhancedByteBufferAccess.java:118-136`
    (zero-copy setup with `CACHE_SIZE_KEY=3`) and `:329-428` (`testZeroCopyMmapCache`; checks
    outstanding and expiry counts, not the size bound).
  - `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/shortcircuit/TestShortCircuitCache.java:177-190`
    (negative values rejected).
- No JIRA was relied on.

## B. Verification solution

**B1. Claim under test.** For a DFSClient doing zero-copy short-circuit reads that releases each
buffer, the number of idle block-file mappings kept by one `ShortCircuitCache`, and the memory
they hold (mapped bytes, file-backed RSS), stays at or below `max(S−1, 0)` mappings, where
`S = dfs.client.mmap.cache.size`. It grows with `S` until it reaches the number of blocks read.
The claim is refuted if idle mappings exceed `S` for any `S`, or if the count does not change
with `S`.

### B2. Unit tier

**B2a. Environment and build.**
- **Host:** one Linux host, JDK 8, Maven 3.3+.
- **Native code:** native `libhadoop` is required, because short-circuit reads need
  `DomainSocket` and `NativeIO`. Without it `TestEnhancedByteBufferAccess`-style tests are skipped
  by `Assume`. Install native build prerequisites per `BUILDING.txt:54-64`: `build-essential cmake
  zlib1g-dev pkg-config libssl-dev libsasl2-dev`, plus protobuf 3.21.12 per `BUILDING.txt:77`.
- **Copy the source** to local disk outside any shared tree:
  `rsync -a ~/hadoop-3.4.2/ /mydata/<run>/src/`. Build in the copy:
  ```
  cd /mydata/<run>/src
  mvn -pl hadoop-common-project/hadoop-common -Pnative install -DskipTests -Dmaven.javadoc.skip=true
  mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true
  ```
- **Library path:** surefire gets `LD_LIBRARY_PATH` with
  `${hadoop.common.build.dir}/native/target/usr/local/lib` (`hadoop-project/pom.xml:2474`).
- **New test file:**
  `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/fs/TestMmapCacheSizeCap.java`
  (package `org.apache.hadoop.fs`, as in `TestEnhancedByteBufferAccess`). The test resources'
  `hdfs-site.xml` already sets `dfs.namenode.fs-limits.min-block-size=0`.
- **Surefire JVM:** default; the mapped files are 12 MiB in total.

**B2b. Knobs.**
- **Varied:** `S = dfs.client.mmap.cache.size ∈ {0, 1, 2, 3, 5, 8, 13, 256}`.
  - 0 and 1 test the off-by-one.
  - 2, 3, 5 and 8 are below N.
  - 13 = N+1 is the first value that should keep all 12.
  - 256 is the default.
- **Fixed:**
  - `dfs.client.mmap.cache.timeout.ms=3600000`, so no time-based demotion in the window.
  - `dfs.client.read.shortcircuit.streams.cache.size=256`, so the total cap does not bind.
  - `dfs.client.short.circuit.num=1`.
  - `dfs.client.read.shortcircuit=true`, `dfs.client.read.shortcircuit.skip.checksum=true`,
    `dfs.client.mmap.enabled=true`.
  - `dfs.domain.socket.path=<TemporarySocketDirectory>/mmapcap._PORT.sock`, with
    `DomainSocket.disableBindPathValidation()`.
  - `dfs.blocksize=1048576`.
  - A distinct `dfs.client.context=mmapcap-S<S>` per value, so each value gets a fresh
    `ShortCircuitCache`.
- **How set:** each value is set on the test's `HdfsConfiguration`. Use one `MiniDFSCluster` per
  value, or one cluster and a fresh `FileSystem` (`FileSystem.newInstance`) per context.

**B2c. Workload.**
- Write one file `/mmapcap` of `N × 1 MiB = 12 MiB` (`DFSTestUtil.createFile(fs, path, 12L<<20,
  (short)1, seed)`) with `MiniDFSCluster.Builder(conf).numDataNodes(1)`, and wait for replication.
- Open it and loop over i = 0..11:
  1. `ByteBuffer b = in.read(null, 1<<20, EnumSet.of(ReadOption.SKIP_CHECKSUMS))`. The `null` pool
     makes a non-zero-copy read throw `UnsupportedOperationException`, per
     `ByteBufferUtil.java:60-63`, so every buffer is a real mmap.
  2. Assert `b.remaining()==1<<20`.
  3. Touch one byte per 4096.
  4. `in.releaseBuffer(b)`.
  5. Snapshot the cache.
- Close the stream and snapshot again.
- **Arithmetic:** 12 distinct mmapped replicas become idle, one per block, which is more than
  `S−1` for every `S ≤ 12`. So the limit is reached and exceeded for `S ∈ {0..8}`, and not reached
  for 13 and 256.

**B2d. Observables and instruments.**
- **Primary (the check's operand):** `evictableMmapped.size()` from
  `ClientContext.get("mmapcap-S<S>", conf).getShortCircuitCache(0).accept(CacheVisitor)`
  (`ShortCircuitCache.java:964-993`).
- **Also recorded:** `numOutstandingMmaps`, `evictable.size()` and `replicas.size()`.
- **Memory side, same JVM:** read `/proc/self/maps` and count the lines whose path contains
  `/blk_` and does not end in `.meta`. Also sum `(end − start)` over those lines for mapped bytes.
  This JVM also hosts the DataNode, which maps no block files because
  `dfs.datanode.max.locked.memory=0` by default.
- **Sampling:** a snapshot after each `releaseBuffer`, one after `close()`, and one 2 s later.
- **Not observable directly:** which entry was demoted. Enable TRACE on `ShortCircuitCache` to see
  `demoteOldEvictable: demoting ... because we need more space` (`ShortCircuitCache.java:550-555`).

**B2e. Procedure.**
1. Build as in B2a.
2. Write `TestMmapCacheSizeCap#testCap`. It loops over the S values. For each value it:
   - builds the conf from B2b;
   - starts `MiniDFSCluster`;
   - runs B2c;
   - records the snapshots (log lines `S=<S> step=<i> evictableMmapped=.. outstanding=..
     evictable=.. blkMaps=.. blkMappedBytes=..`);
   - shuts down.
3. Copy the `@BeforeClass` setup from `TestEnhancedByteBufferAccess.java:88-100`, minus the mlock
   manipulator if not needed. Add `Assume.assumeTrue(NativeIO.isAvailable())` and fail loudly
   instead if it is false, so a silent skip is not mistaken for a pass.
4. Run
   `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestMmapCacheSizeCap -Pnative -DfailIfNoTests=false`
   and keep `target/surefire-reports/*-output.txt`.
5. Run the controls in B2h the same way, as separate methods.

**B2f. Predictions.** N = 12, M(S) = `min(12, max(S−1, 0))`.

| S | after step i, i = 0..11: evictableMmapped | outstanding | blkMaps | after close: evictableMmapped = outstanding = blkMaps | evictable (non-mmapped) after close | blkMappedBytes after close |
|---|---|---|---|---|---|---|
| 0 | 0 | 1 | 1 | 0 | 12 | 0 |
| 1 | 0 | 1 | 1 | 0 | 12 | 0 |
| 2 | min(i,1) | +1 | +1 | 1 | 11 | 1 MiB |
| 3 | min(i,2) | +1 | +1 | 2 | 10 | 2 MiB |
| 5 | min(i,4) | +1 | +1 | 4 | 8 | 4 MiB |
| 8 | min(i,7) | +1 | +1 | 7 | 5 | 7 MiB |
| 13 | i | +1 | +1 | 12 | 0 | 12 MiB |
| 256 | i | +1 | +1 | 12 | 0 | 12 MiB |

- "+1" means the evictableMmapped value plus one: the current block's mapping, held by the open
  block reader.
- `replicas.size()` stays 12 throughout after the loop.
- **Relation:** the after-close count is non-decreasing in S, equals S−1 for 2 ≤ S ≤ 13, and is
  0 at S ≤ 1.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| After-close evictableMmapped = M(S) for every S, and blkMaps equals it | Claim confirmed; mechanism as traced, including the off-by-one |
| evictableMmapped = min(12, S) (S kept, not S−1) but still bounded and rising with S | Cap holds; off-by-one in A3 wrong; amend A3, claim still confirmed in substance |
| evictableMmapped or blkMaps > S for some S < 12 | Claim refuted: the key does not cap idle mmaps |
| evictableMmapped capped but blkMaps not reduced (mappings stay) | Count is capped but memory is not: munmap is ineffective (check `CleanerUtil.UNMAP_SUPPORTED`); memory claim refuted on this JDK |
| Counts identical for all S (e.g. always 12) | Key not reaching the cache (context reuse, conf not applied): run invalid; check the `ShortCircuitConf` log line / context names |
| blkMaps = 0 and `UnsupportedOperationException` | Zero-copy not active (native missing, short-circuit off): the limit was never reached; not confirmed |

**B2h. Controls.**
- **Positive control (cap known to bind):** S=256 with
  `dfs.client.read.shortcircuit.streams.cache.size=4`. `trimEvictionMaps` must purge down to 4
  total, so the after-close evictableMmapped and blkMaps both equal 4. This shows the instrument
  sees unmapping when a cap binds.
- **Time control:** S=256 with `dfs.client.mmap.cache.timeout.ms=500`. After close, wait 3 s; the
  cleaner (rate 125 ms) brings evictableMmapped and blkMaps to 0. This shows munmap really removes
  `/proc` mappings on this JDK.
- **Baseline:** the same loop with a heap `ElasticByteBufferPool` and `dfs.client.mmap.enabled=false`
  gives blkMaps = 0. Any `/blk_` mapping then comes from zero-copy only.
- **Repeats:** run the whole sweep twice. Results must be identical (deterministic).

### B3. Cluster tier

**B3a. Environment and build.**
- **Host:** one Linux host. Pseudo-distributed HDFS: one NameNode and one DataNode, the client on
  the same host, so short-circuit applies. No YARN.
- **Disk:** run root `R=/mydata/<run>/mmapcap` on local disk with at least 5 GiB free.
- **Distribution:** built in the local source copy:
  `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`.
- **Native library:**
  1. Build it with `mvn -pl hadoop-common-project/hadoop-common -Pnative install -DskipTests`.
  2. Copy `hadoop-common-project/hadoop-common/target/native/target/usr/local/lib/libhadoop.so*`
     into `$HADOOP_HOME/lib/native/`. Alternatively build the whole dist with `-Pnative` if
     Boost/protobuf are present.
  3. Check with `hadoop checknative -a`: the `hadoop:` line must say `true`.
- **Environment:** `HADOOP_HOME=$R/hadoop-3.4.2` (the untarred dist),
  `HADOOP_CONF_DIR=$R/conf`, `HADOOP_LOG_DIR=$R/logs`, `HADOOP_PID_DIR=$R/pids`,
  `HADOOP_HEAPSIZE_MAX=1g` for the daemons. `HADOOP_CLIENT_OPTS="-Xmx512m"` for the probe client;
  the mappings are off-heap.
- **`core-site.xml`:** `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$R/tmp`.
- **`hdfs-site.xml`** (read by daemons and the client):
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=$R/nn`, `dfs.datanode.data.dir=$R/dn`
  - `dfs.blocksize=67108864`
  - `dfs.domain.socket.path=$R/sock/dn_socket`
  - `dfs.client.read.shortcircuit=true`, `dfs.client.read.shortcircuit.skip.checksum=true`
  - `dfs.client.mmap.enabled=true`
  - `dfs.client.mmap.cache.timeout.ms=3600000`
  - `dfs.client.read.shortcircuit.streams.cache.size=256`
  - `dfs.client.short.circuit.num=1`
  - `dfs.datanode.max.locked.memory=0` (default)
- **Socket directory:** `mkdir -p $R/sock && chmod 755 $R $R/sock`. The DataNode validates that no
  ancestor of the socket path is writable by others; check with `namei -l $R/sock`. If an ancestor
  of `/mydata` fails, use a directory such as `$HOME/mmapcap-sock` (mode 755) instead.
- **Probe:** `MmapCapProbe.java` (below), compiled outside the source tree in `$R/probe`.

`MmapCapProbe` (the whole workload client):
```java
import java.nio.ByteBuffer; import java.nio.file.*; import java.util.*;
import org.apache.hadoop.conf.Configured; import org.apache.hadoop.fs.*;
import org.apache.hadoop.util.*;
public class MmapCapProbe extends Configured implements Tool {
  static String snap() throws Exception {
    long n = 0, bytes = 0;
    for (String l : Files.readAllLines(Paths.get("/proc/self/maps"))) {
      if (l.contains("/blk_") && !l.endsWith(".meta")) {
        String[] r = l.split(" ")[0].split("-");
        n++; bytes += Long.parseLong(r[1], 16) - Long.parseLong(r[0], 16);
      }
    }
    String vm = "", rf = "";
    for (String l : Files.readAllLines(Paths.get("/proc/self/status"))) {
      if (l.startsWith("VmSize:")) vm = l.replaceAll("\\s+", " ");
      if (l.startsWith("RssFile:")) rf = l.replaceAll("\\s+", " ");
    }
    return "blkMaps=" + n + " blkMappedBytes=" + bytes + " " + vm + " " + rf;
  }
  public int run(String[] a) throws Exception {
    Path p = new Path(a[0]); int holdSec = Integer.parseInt(a[1]);
    FileSystem fs = p.getFileSystem(getConf());
    FileStatus st = fs.getFileStatus(p);
    long bs = st.getBlockSize(); int nb = (int) (st.getLen() / bs);
    System.out.println("conf dfs.client.mmap.cache.size=" + getConf().get("dfs.client.mmap.cache.size"));
    System.out.println("before " + snap());
    try (FSDataInputStream in = fs.open(p)) {
      for (int i = 0; i < nb; i++) {
        ByteBuffer b = in.read(null, (int) bs, EnumSet.of(ReadOption.SKIP_CHECKSUMS));
        if (b == null || b.remaining() != bs) throw new IllegalStateException("short zero-copy read at " + i);
        long s = 0; for (int o = b.position(); o < b.limit(); o += 4096) s += b.get(o);
        in.releaseBuffer(b);
        System.out.println("step " + i + " sum=" + s + " " + snap());
      }
    }
    System.out.println("after-close " + snap());
    Thread.sleep(holdSec * 1000L);
    System.out.println("end " + snap());
    return 0;
  }
  public static void main(String[] a) throws Exception { System.exit(ToolRunner.run(new MmapCapProbe(), a)); }
}
```

**B3b. Knobs.**
- **Varied:** `S = dfs.client.mmap.cache.size ∈ {0, 1, 2, 5, 9, 17, 256}`, passed per client run
  as `-Ddfs.client.mmap.cache.size=S`. Each run is a new client JVM, so it gets a new
  `ClientContext`. No daemon restart or refresh is needed, because the key is client-only.
  - 0 and 1 test the off-by-one.
  - 2, 5 and 9 lie below N = 16.
  - 17 = N+1 is the first value that keeps all 16.
  - 256 is the default.
- **Fixed:** all other keys as in B3a.

**B3c. Workload.**
- **Data:** `head -c 1073741824 /dev/urandom > $R/data/f16.bin`, then
  `hdfs dfs -D dfs.blocksize=67108864 -put $R/data/f16.bin /mmapcap/f16`. That is 16 blocks of
  64 MiB, replication 1, 1 GiB on the DataNode volume `$R/dn`.
- **Run:** `hadoop jar $R/probe/probe.jar MmapCapProbe -Ddfs.client.mmap.cache.size=S /mmapcap/f16 30`.
  It zero-copy reads every block, touches every page (16 × 64 MiB = 1 GiB of file-backed pages),
  releases each buffer, closes, and holds 30 s.
- **Arithmetic:** 16 idle mmapped replicas of 64 MiB each are offered to the cache, more than
  `S−1` for all `S ≤ 16`. Without the cap, 1 GiB of mappings would be kept.
- **Duration:** about 1 min per S value.

**B3d. Observables and instruments.**
- **Probe output (in-process):**
  - `blkMaps`: the number of `/proc/self/maps` lines mapping DataNode block files `…/blk_<id>`.
  - `blkMappedBytes`: the sum of those VMA sizes.
  - `VmSize` and `RssFile` from `/proc/self/status`.
- **External cross-check:** during the 30 s hold, from another shell:
  - `pid=$(jps | awk '/MmapCapProbe|RunJar/{print $1}')`;
  - `grep -c '/blk_[0-9]*$' /proc/$pid/maps`;
  - `grep -E 'VmSize|RssFile' /proc/$pid/status`;
  - `pmap -x $pid | grep blk_` (RSS per mapping).
- **Short-circuit check:** the DataNode log (`$R/logs/*datanode*.log`) should show
  `REQUEST_SHORT_CIRCUIT_FDS` / `cliID` lines. `hdfs dfsadmin -report` is not needed.
- **Not observable directly:** the client's internal `evictableMmapped`. `blkMaps` after close
  equals it, because no reader holds a mapping then. With TRACE logging on
  `org.apache.hadoop.hdfs.shortcircuit.ShortCircuitCache` (`-Dhadoop.root.logger=TRACE,console`
  is too noisy; use a log4j.properties line), the demotion messages show it.

**B3e. Procedure.**
1. Build the dist and native library, untar into `$R`, write the configs, create `$R/sock` (B3a),
   then run `hdfs namenode -format -nonInteractive`.
2. Start the daemons: `hdfs --daemon start namenode; hdfs --daemon start datanode`. Check `jps`.
   Check `hdfs dfsadmin -report` shows 1 live DataNode. Check the DataNode log has no
   "domain socket" errors.
3. Load the data as in B3c and check `hdfs fsck /mmapcap/f16 -blocks` shows 16 blocks.
4. Compile the probe:
   - `mkdir -p $R/probe/classes`
   - `javac -cp $(hadoop classpath) -d $R/probe/classes MmapCapProbe.java`
   - `jar cf $R/probe/probe.jar -C $R/probe/classes .`
5. Baseline: `hdfs dfs -cat /mmapcap/f16 > /dev/null` while sampling. A regular read creates no
   `blk_` mapping.
6. For each S in B3b, run the probe once, save stdout to `$R/out/S<S>.log`, and run the external
   check once during the hold.
7. Run the controls (B3h).
8. Repeat the S=2, 9 and 256 runs once for repeatability.
9. Stop the daemons: `hdfs --daemon stop datanode; hdfs --daemon stop namenode`. Check `jps`.

**B3f. Predictions.** N = 16, block = 64 MiB = 67108864 B, M(S) = `min(16, max(S−1, 0))`.

| S | blkMaps during step i | after-close / end blkMaps | after-close blkMappedBytes | RssFile and VmSize vs the S=0 run, at end |
|---|---|---|---|---|
| 0 | 1 | 0 | 0 | ≈ 0 |
| 1 | 1 | 0 | 0 | ≈ 0 |
| 2 | min(i+1, 2) | 1 | 64 MiB | ≈ +64 MiB |
| 5 | min(i+1, 5) | 4 | 256 MiB | ≈ +256 MiB |
| 9 | min(i+1, 9) | 8 | 512 MiB | ≈ +512 MiB |
| 17 | i+1 | 16 | 1024 MiB | ≈ +1 GiB |
| 256 | i+1 | 16 | 1024 MiB | ≈ +1 GiB |

- During step i for S = 0 and 1, the single mapping is the current block, which is still
  referenced.
- RssFile can be a little lower than predicted if the kernel reclaimed some file pages; the host
  should have more than 2 GiB of free RAM.
- "end" equals "after-close", because there is no time-based demotion with a 1 h timeout.
- **Relation:** retained mapped bytes are a step function of S with slope 64 MiB per unit for
  2 ≤ S ≤ 17, flat at 0 for S ≤ 1 and at 1 GiB for S ≥ 17.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| after-close blkMaps = M(S) and RssFile/VmSize deltas ≈ M(S) × 64 MiB | Claim confirmed: the key caps idle mapped memory (at S−1 entries) |
| after-close blkMaps = min(16, S) | Cap holds with no off-by-one; A3's S−1 is wrong (amend), claim confirmed in substance |
| blkMaps > S for some S ≤ 15 after close | Claim refuted: idle mapped memory not bounded by the key |
| blkMaps ≤ S but RssFile/VmSize not reduced vs S=256 | Entries demoted but mappings not freed (unmap unsupported on this JDK): memory claim refuted |
| Same blkMaps (16) for every S | Key not applied (check the probe's `conf` line) or a different cache in use: run invalid |
| `UnsupportedOperationException` / blkMaps always 0 | Zero-copy short-circuit not active (no libhadoop, socket path rejected): limit never reached; not confirmed |

**B3h. Controls.**
- **Positive control (cap known to bind):** S=256 with
  `-Ddfs.client.read.shortcircuit.streams.cache.size=4`. The after-close blkMaps must be 4, about
  256 MiB, through the `maxTotalSize` purge at `ShortCircuitCache.java:572-585`. Same workload,
  usage moves when a cap binds.
- **Unmap control:** S=256 with `-Ddfs.client.mmap.cache.timeout.ms=2000`. After close, within
  about 3 s of the hold, blkMaps falls from 16 to 0 and RssFile falls by about 1 GiB. This shows
  munmap is effective on this JDK.
- **Baseline:** `hdfs dfs -cat` (step 5) shows that regular short-circuit reads leave no `blk_`
  mappings.
- **Same data:** use the same file and data for all S, run sequentially, so the page-cache state is
  comparable. Optionally run `sync; echo 1 | sudo tee /proc/sys/vm/drop_caches` before each run if
  allowed; this is not required.
- **Run on JDK 8 and, if possible, JDK 11.** The `CleanerUtil` paths differ: `sun.misc.Cleaner`
  versus `Unsafe.invokeCleaner`.

**B4. Risks and cleanup.**
- **Disk:** about 1 GiB data plus 1 GiB HDFS block plus logs, all under `$R` on local disk.
- **Memory:** the client maps at most about 1 GiB of file-backed pages (reclaimable), daemons
  1 GiB heap each.
- **Ports:** 9000, 9870, 9864, 9866, 9867 must be free. Check with `ss -ltn` first, or move them
  in `hdfs-site.xml`.
- **Unit tier:** MiniDFSCluster uses ephemeral ports and a `TemporarySocketDirectory`. It cleans
  up on `cluster.shutdown()`; check that no surefire JVM is left (`jps`).
- **Cleanup:**
  - stop the DataNode and NameNode; confirm with `jps` that no `NameNode`, `DataNode`,
    `MmapCapProbe` or `RunJar` remains;
  - `rm -rf $R/{nn,dn,tmp,data,sock,logs,pids}` after copying `$R/out`;
  - never write into the shared source tree; all builds are in the local copy.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/shortcircuit/ShortCircuitCache.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/shortcircuit/ShortCircuitReplica.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/shortcircuit/ClientMmap.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/impl/DfsClientConf.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/impl/BlockReaderLocal.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/impl/BlockReaderFactory.java (getShortCircuitCache calls)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSInputStream.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/ClientContext.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/nativeio/NativeIO.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/util/CleanerUtil.java
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/ByteBufferUtil.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/fs/TestEnhancedByteBufferAccess.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/shortcircuit/TestShortCircuitCache.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/resources/hdfs-site.xml
- hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/CentralizedCacheManagement.md
- hadoop-project/pom.xml (surefire LD_LIBRARY_PATH)
- BUILDING.txt

## D. Stage-4 feedback

none yet
