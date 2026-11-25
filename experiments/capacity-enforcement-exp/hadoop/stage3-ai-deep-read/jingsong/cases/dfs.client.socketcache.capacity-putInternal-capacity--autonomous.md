# dfs.client.socketcache.capacity — verification solution  <!-- file: cases/dfs.client.socketcache.capacity-putInternal-capacity--autonomous.md -->

<!-- Hadoop version of ../../stage3-ai-deep-read/_TEMPLATE-autonomous.md (2026-11-06): same headings;
     tag, permalinks, configuration and build wording changed for Hadoop 3.4.2. -->

| Field | Value |
|---|---|
| Entry pointer | [`PeerCache.java:196`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/PeerCache.java#L196) — `if (capacity == multimap.size()) { evictOldest(); }` in `PeerCache.putInternal` |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `negative` — the check caps the **number of idle, cached client-to-DataNode sockets** (connections / file descriptors) held by one DFS client context; each cached entry costs only a few KB of client heap and no disk, so memory or disk usage should not follow the knob in any significant way. |
| Ground | The bounded object is a connection count (the playbook's "connections" category). A cached entry is a `Peer` wrapper around an already-drained socket (no data buffer is kept with it: the packet buffer belongs to the closed `BlockReaderRemote`), plus a `Key`/`Value` pair and a multimap node. The only memory that can scale with the knob is indirect: each cached socket keeps one idle `DataXceiver` thread alive on the DataNode until `dfs.datanode.socket.reuse.keepalive` expires — a thread-count effect that is bounded independently by the DataNode's keepalive and `dfs.datanode.max.transfer.threads`. |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/<full path under the repository root>#L123)`
> (a range is `#L123-L130`). Check that the line number is the line you mean. Other citations may
> stay plain `file:line`.

**Naming parts.** constraint = `dfs.client.socketcache.capacity`; function = `putInternal` (the method
enclosing the given if; it is also the main enforcement point — the only place the cache grows);
operand = `capacity` (the limit-side operand of `capacity == multimap.size()`).

## A. Constraint trace

**A1. The constraint.**
- Name: `dfs.client.socketcache.capacity` (exact key; no placeholder).
- Kind: configuration key (HDFS client side).
- First declared: [`HdfsClientConfigKeys.java:96-98`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java#L96-L98)
  (`DFS_CLIENT_SOCKET_CACHE_CAPACITY_KEY = "dfs.client.socketcache.capacity"`,
  `DFS_CLIENT_SOCKET_CACHE_CAPACITY_DEFAULT = 16`); re-exported as
  `DFSConfigKeys.DFS_CLIENT_SOCKET_CACHE_CAPACITY_KEY/_DEFAULT` (`hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java:1975-1979`).
- `hdfs-default.xml` entry: `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml:4631-4638`,
  value `16`, described as "Socket cache capacity (in entries) for short-circuit reads. If this value
  is set to 0, the client socket cache is disabled." (The description is narrower than the code:
  the same cache holds TCP peers for ordinary remote reads too, see A3.)
- Unit: entries (cached `Peer` objects, i.e. open sockets).
- Default: 16. Java constant and `hdfs-default.xml` agree; when `hdfs-default.xml` is on the
  classpath its value is what `conf.getInt` returns, otherwise the Java default 16 is used — same value.
- Companion key (other source of the same mechanism): `dfs.client.socketcache.expiryMsec`
  (`HdfsClientConfigKeys.java:99-101`, default 3000 ms; `hdfs-default.xml:4640-4646`) — the age after
  which a cached entry is closed. DataNode side: `dfs.datanode.socket.reuse.keepalive`
  (`DFSConfigKeys.java:470-471`, default 4000 ms; `hdfs-default.xml:4919`) — how long the DataNode
  keeps an idle reused socket (and its thread) open.
- How set: client-side `hdfs-site.xml` (or `core-site.xml`) on the client host, `-D
  dfs.client.socketcache.capacity=<n>` for a `ToolRunner`-based client (`hadoop jar`, `hdfs dfs`), or
  `Configuration.setInt` in a program. Read once in `DfsClientConf.ShortCircuitConf`
  (`hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/impl/DfsClientConf.java:792-794`)
  and fixed at `ClientContext` construction (`ClientContext.java:174-175`). `ClientContext`s are
  cached per JVM by name (`dfs.client.context`, default `default`; `ClientContext.java:210-224`), so
  a new value takes effect only in a **new client JVM** or a **new context name**; a later client in
  the same JVM with a different value only gets a warning (`ClientContext.java:243-254`). No daemon
  restart is involved (no daemon reads it for its own reads, except when a DataNode/other daemon acts
  as an HDFS client).
- Read by: every process that acts as an HDFS client (`hdfs dfs`, MapReduce tasks, YARN NodeManager
  localization, HBase etc.).

**A2. What it caps.** The number of idle sockets (TCP `NioInetPeer`/`BasicInetPeer`, or Unix-domain
`DomainPeer` when short-circuit reads are on) that one client context keeps open to DataNodes for
reuse. The compared quantity is `multimap.size()` — total entries in the `LinkedListMultimap<Key,
Value>` across all DataNodes and both socket kinds (`PeerCache.java:93-94, 196`). Resource category:
connections / file descriptors, with a few KB of client heap per entry and, indirectly, one idle
`DataXceiver` thread per entry on the DataNode. No disk.

**A3. Mechanism.**
1. `ClientContext` builds `new PeerCache(scConf.getSocketCacheCapacity(), scConf.getSocketCacheExpiry())`
   (`ClientContext.java:174-175`). Constructor: capacity 0 → cache disabled (debug log); capacity ≠ 0
   with expiry 0 → `IllegalStateException` (`PeerCache.java:98-108`).
2. A remote block read: `BlockReaderFactory.nextTcpPeer()` first tries `PeerCache.get(dn, false)`
   (`BlockReaderFactory.java:821-827`), otherwise `DFSClient.newConnectedPeer` opens a new socket
   (`BlockReaderFactory.java:829-831`; `DFSClient.java:3067-3088`). Domain peers likewise
   (`BlockReaderFactory.java:798-810`).
3. When the reader has consumed the whole requested range it sends `CHECKSUM_OK`/`SUCCESS`
   (`BlockReaderRemote.java:232-239`, `sentStatusCode = true` at `:330`). On `BlockReaderRemote.close()`
   the peer is returned to the cache only if the status was sent (`BlockReaderRemote.java:309-315`);
   otherwise it is closed. The short-circuit fd-request path also returns its domain peer
   (`BlockReaderFactory.java:546`). The reader is closed by `DFSInputStream.closeCurrentBlockReaders`
   on stream close or seek to another block (`DFSInputStream.java:611, 1760-1769`).
4. `PeerCache.put` drops closed peers, and with `capacity <= 0` closes the peer at once
   (`PeerCache.java:181-191`).
5. `putInternal` (synchronized) starts the expiry daemon, then the check
   [`PeerCache.java:196`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/PeerCache.java#L196):
   `if (capacity == multimap.size())` → `evictOldest()` closes and removes the oldest entry
   (insertion order of `LinkedListMultimap`, `PeerCache.java:228-240`); then the new peer is added
   (`:199-200`). Because every growth step is one synchronized `put` of one entry starting from 0,
   `size()` can never pass `capacity` even though the test is `==` rather than `>=`.
   Outcome when the limit is reached: the oldest idle socket is closed (client FD released; the
   DataNode's `DataXceiver` sees EOF and its thread exits, `DataXceiver.java:276-282`). Below the limit:
   the socket stays open.
6. Expiry: the daemon thread sleeps `expiryPeriod` and closes entries older than it
   (`PeerCache.java:210-223, 246-258`); `get` also closes stale entries it encounters (`:156-176`).
   Independently, the DataNode waits at most `dfs.datanode.socket.reuse.keepalive` for a next op on a
   reused socket, then closes it (`DataXceiver.java:263-275, 301-302`). So with defaults a cached
   entry lives at most ~3–4 s.
7. Bypass / overshoot: sockets **in use** by open block readers are not in the cache and are
   unbounded by this key (one per concurrently open `DFSInputStream`/block reader); the key only limits
   what is kept *after* use. Each distinct `dfs.client.context` name has its own cache, so a JVM can
   hold `capacity × #contexts` idle sockets. Closed-on-the-DN-side sockets remain counted until
   expiry/eviction (`peer.isClosed()` only reflects the local side).

**A4. Other consumers.** Of the client's file descriptors / sockets: active block readers and
`DFSOutputStream` pipelines, NameNode RPC connections (`ipc.client.*`), the short-circuit
`ShortCircuitCache` (`dfs.client.read.shortcircuit.streams.cache.size`, holding block file FDs and
mmaps), `DomainSocketWatcher`. Of client heap: block reader packet buffers (`PacketReceiver` direct
buffers from `DirectBufferPool`, `PacketReceiver.java:55, 273-298`), `ByteArrayManager`, the
application's own buffers. On the DataNode: xceiver threads for all active transfers, capped by
`dfs.datanode.max.transfer.threads` (default 4096, `hdfs-default.xml:1651`).

**A5. Evidence beyond the source.**
- Tests: `hadoop-hdfs-client/src/test/java/org/apache/hadoop/hdfs/TestPeerCache.java` (`testEviction`
  :199-231 asserts size stays at `CAPACITY` and the oldest is evicted);
  `hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/TestConnCache.java:86-121` (one socket cached
  after repeated reads); `hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/TestDataTransferKeepalive.java`
  (keepalive/expiry interplay, cache sizes).
- `hdfs-default.xml:4631-4646` descriptions.
- JIRA history of the socket cache (not relied on for any claim here): HDFS-2246-era socket reuse
  (`SocketCache`, later renamed `PeerCache`), HDFS-3357 (DataNode keepalive). none relied on beyond the source.

## B. Verification solution

**B1. Claim under test.** `dfs.client.socketcache.capacity` bounds the number of idle cached
client→DataNode sockets to `min(N, C)` after `N` fully-read streams are closed, but it does **not**
bound any memory or disk quantity: client heap (and client RSS) differ between `C = 0` and `C = 1024`
by no more than ~4 KB per cached entry (≤ 4 MB total), and no disk use depends on `C`. The claim is
wrong if client heap retained by the cache grows by more than ~4 KB per entry (≥ 4 MB at `C = 1024`
over `C = 0`) or if any disk usage changes with `C`.

### B2. Unit tier

**B2a. Environment and build.** JDK 8, Maven 3.3+. Copy the tag to local disk (never the shared tree),
e.g. `rsync -a <source>/ $WORK/hadoop-3.4.2/`. Build:
`cd $WORK/hadoop-3.4.2 && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
Add test `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/TestPeerCacheCapacityProbe.java`
(package `org.apache.hadoop.hdfs`, so the package-private `PeerCache.clear()` and the test utility
`MiniDFSCluster` are reachable). Surefire JVM: default test argLine of the module plus
`-XX:+UseSerialGC` (deterministic full GC for heap readings); `ulimit -n` ≥ 8192 for the shell that
runs Maven (both socket ends live in this JVM).

Test outline (two parts):

```java
public class TestPeerCacheCapacityProbe {
  // Part 1: pure PeerCache, operand only. Reuse TestPeerCache.FakePeer (copy it in; it is private).
  @Test public void operandBound() throws Exception {
    for (int c : new int[]{0, 1, 16, 256, 1024}) {
      PeerCache cache = new PeerCache(c, 600_000);
      int n = 2048, closed = 0;
      FakePeer[] p = new FakePeer[n];
      int maxSize = 0;
      for (int i = 0; i < n; i++) {
        DatanodeID dn = new DatanodeID("127.0.0.1", "h" + (i % 8), "dn" + (i % 8), 1, 2, 3, 4);
        p[i] = new FakePeer(dn, false);
        cache.put(dn, p[i]);
        maxSize = Math.max(maxSize, cache.size());
      }
      for (FakePeer f : p) if (f.isClosed()) closed++;
      System.out.println("PART1 C=" + c + " N=" + n + " maxSize=" + maxSize
          + " size=" + cache.size() + " closed=" + closed);
      cache.close();
    }
  }
  // Part 2: real sockets through MiniDFSCluster; one run per C (set by -Dprobe.capacity).
  @Test public void realPeers() throws Exception {
    int c = Integer.getInteger("probe.capacity", 16), n = 1024;
    Configuration conf = new HdfsConfiguration();
    conf.setInt("dfs.datanode.socket.reuse.keepalive", 600_000);
    conf.setInt("dfs.datanode.max.transfer.threads", 4096);
    MiniDFSCluster cl = new MiniDFSCluster.Builder(conf).numDataNodes(1).build();
    try {
      FileSystem fs0 = cl.getFileSystem();
      for (int i = 0; i < n; i++) DFSTestUtil.createFile(fs0, new Path("/p/f" + i), 65536, (short) 1, i);
      Configuration cc = new Configuration(conf);
      cc.set("dfs.client.context", "probe-" + c);            // fresh, isolated cache
      cc.setInt("dfs.client.socketcache.capacity", c);
      cc.setLong("dfs.client.socketcache.expiryMsec", 600_000);
      FileSystem fs = FileSystem.newInstance(cl.getURI(), cc);
      PeerCache cache = ClientContext.getFromConf(cc).getPeerCache();
      long h0 = heapAfterGc(); int fd0 = fdCount();
      FSDataInputStream[] in = new FSDataInputStream[n]; byte[] b = new byte[65536];
      for (int i = 0; i < n; i++) { in[i] = fs.open(new Path("/p/f" + i)); while (in[i].read(b) > 0) {} }
      long hOpen = heapAfterGc(); int fdOpen = fdCount(); long dOpen = directUsed();
      for (FSDataInputStream s : in) s.close();
      in = null;
      long h1 = heapAfterGc(); int fd1 = fdCount();
      String histo = histogram("NioInetPeer|SocketChannelImpl|PeerCache\\$|LinkedListMultimap\\$Node");
      System.out.println("PART2 C=" + c + " N=" + n + " size=" + cache.size()
          + " heap0=" + h0 + " heapOpen=" + hOpen + " heapClosed=" + h1
          + " fd0=" + fd0 + " fdOpen=" + fdOpen + " fdClosed=" + fd1
          + " directOpen=" + dOpen + " xceivers=" + cl.getDataNodes().get(0).getXceiverCount());
      System.out.println(histo);
      fs.close();
    } finally { cl.shutdown(); }
  }
  // heapAfterGc(): 3 x System.gc() + 200 ms sleep, then MemoryMXBean heap used.
  // fdCount(): new File("/proc/self/fd").list().length.
  // directUsed(): BufferPoolMXBean named "direct" -> getMemoryUsed().
  // histogram(re): run "jcmd <ownPid> GC.class_histogram" (pid from RuntimeMXBean name),
  //                keep lines matching re.
}
```

> **Amendment A1 (2026-11-24, stage-4 audit, before any reading) — node paths, no install build, JVM options.** On the
> stage-4 node `pc82`, `R = /mydata/jingsong-s4/dfs.client.socketcache.capacity-putInternal-capacity-run1`. The source copy is
> `R/src` (made by `jingsong/copy-source.sh`, rel/release-3.4.2); `$WORK/hadoop-3.4.2` reads `R/src`. No `-am install`: the 3.4.2
> artifacts (including the `hadoop-hdfs` and `hadoop-common` test jars) are in `~/.m2` from the node's base build
> (`/mydata/jingsong-s4/hadoop-base`), and nothing from a per-case copy is installed into the shared `~/.m2`; the test runs with
> `mvn -B test` in `R/src/hadoop-hdfs-project/hadoop-hdfs`. Surefire ignores `-DargLine` in this tree
> (`hadoop-project/pom.xml:2469` uses `${maven-surefire-plugin.argLine}`): JVM options are passed as
> `-Dmaven-surefire-plugin.argLine="-Xmx2g -XX:+UseSerialGC -Dprobe.capacity=$C -Dprobe.rep=$REP -Dprobe.out=<dir>"`, and the
> test prints its max heap and GC names so the options are confirmed from inside. Surefire failures do not fail `mvn test` here:
> read the surefire counts. `ulimit -n 65536` in the shell that runs Maven.

> **Amendment A2 (2026-11-24, stage-4 audit, before any reading) — instrument additions to the unit test.** Part 2 also
> prints, on its `PART2` line: `rep`, `direct0` (direct pool used before the opens, read with `h0`), `maxHeap` and the GC names;
> and writes the full `GC.class_histogram` at the closed state to `<probe.out>/histo-C<C>-r<rep>.txt` (for the attribution in A3).
> `histogram(re)` reads `GC.class_histogram` with `$JAVA_HOME/bin/jcmd` (JDK 8: `java.home/../bin/jcmd`). Each part-2 run is one
> Maven invocation (fresh JVM) per (C, rep), rep ∈ {1, 2}; order 0, 16, 256, 1024, then the list again. Part 1 runs once (it is
> deterministic). Nothing else changes in the outline.

**B2b. Knobs.** `dfs.client.socketcache.capacity` C ∈ {0, 16, 256, 1024} (part 2) and
{0, 1, 16, 256, 1024} (part 1): 0 = disabled baseline, 16 = default, 256 and 1024 = large enough
that a per-entry cost of even 1 KB would sum to a measurable heap delta. Set via `Configuration`
in the test (part 2 via `-Dprobe.capacity=<C>`, one Maven run per value so each run is a fresh JVM).
`expiryMsec` and the DataNode keepalive are pinned at 600 000 ms so nothing expires during the
measurement.

**B2c. Workload.** Part 1: 2048 `put`s of fake peers across 8 DataNode IDs (N = 2048 ≥ 2 × max C, so
the limit is reached and passed by ≥ 1024 puts for every C). Part 2: N = 1024 one-block files of
64 KB (64 MB in the MiniDFSCluster's `target/test/data`), opened concurrently, each read to EOF so
the status code is sent (`BlockReaderRemote.java:232-239`), then all closed → 1024 `put`s: for
C = 16, 1008 evictions; for C = 1024, none (limit reached exactly).

**B2d. Observables and instruments.** Operand: `PeerCache.size()` (= `multimap.size()`), and in part 1
its running max and the count of peers closed by eviction. Resource proxies: client heap after full
GC (MemoryMXBean); class histogram counts and bytes for `NioInetPeer`, `SocketChannelImpl`,
`PeerCache$Key`, `PeerCache$Value`, `LinkedListMultimap$Node` (`jcmd GC.class_histogram`); process
FD count (`/proc/self/fd`) — note both client and DataNode socket ends are in this JVM, so each
cached connection counts ~2 FDs; direct buffer pool usage (positive control); DataNode
`getXceiverCount()`. Not observable here: kernel socket buffer memory, and client vs DataNode heap
separately (same JVM) — the histogram isolates the client-side cache objects.

**B2e. Procedure.**
1. Build (B2a); add the test file.
2. `cd hadoop-hdfs-project/hadoop-hdfs && mvn test -Dtest=TestPeerCacheCapacityProbe#operandBound`
   → record the `PART1` lines.
3. For C in 0 16 256 1024:
   `mvn test -Dtest=TestPeerCacheCapacityProbe#realPeers -Dprobe.capacity=$C -DargLine="-Xmx2g -XX:+UseSerialGC -Dprobe.capacity=$C"`
   → record the `PART2` line and histogram lines from
   `target/surefire-reports/org.apache.hadoop.hdfs.TestPeerCacheCapacityProbe-output.txt`.
4. Clean up: `rm -rf target/test/data`; check `jps` shows no surefire JVM left.

**B2f. Predictions.**
- Part 1: `maxSize = size = min(2048, C)` for C > 0, `size = 0` for C = 0; `closed = 2048 − min(2048, C)`
  (C = 0: 2048 closed by `put`; C = 16: 2032; C = 1024: 1024).
- Part 2: `size = min(1024, C)` → 0, 16, 256, 1024. `xceivers` ≈ `size` (+0–2). `fdClosed − fd0`
  ≈ 2 × `size` (+ a few selector FDs). Histogram `NioInetPeer` instances = `size`.
- Heap: `heapClosed − heap0` differs between C = 1024 and C = 0 by ≤ 4 MB (≤ ~4 KB per entry; the
  histogram bytes of the five classes above, summed, ≤ 1.5 KB × `size` client side). Same for
  C = 16 vs 0: indistinguishable from noise (< 0.5 MB).
- Positive control: `directOpen` ≥ 1024 × 64 KB ≈ 64 MB above the C = 0 run's pre-open level while
  all 1024 readers are open (each reader's packet buffer), and `fdOpen − fd0` ≈ 2 × 1024 regardless
  of C.

> **Amendment A3 (2026-11-24, stage-4 audit, before any reading) — unit predictions with both socket ends in one JVM.**
> From the source, not from a reading: the DataNode wraps every accepted socket as an `NioInetPeer` too
> (`TcpPeerServer.java:85` → `DFSUtilClient.peerFromSocket`, `DFSUtilClient.java:810-813`), and each idle cached connection keeps
> one DataNode `DataXceiver` thread and its objects alive in the same JVM (`DataXceiver.java:255-305`). So in part 2:
> - Histogram at the closed state: `PeerCache$Key` = `PeerCache$Value` = `size` (exactly; no other context reads);
>   `NioInetPeer` and `SocketChannelImpl` ≈ 2 × `size` + k, where k is the C = 0 run's count (same rep) — not `size`.
> - Definitions (each relative to the C = 0 run of the same rep): **ΔH(C)** = `(heapClosed − heap0)(C) − (heapClosed − heap0)(0)`,
>   the whole-JVM retained heap, which includes the DataNode-side objects of the idle xceivers and is therefore an **upper bound**
>   on the client-side delta; **B_client(C)** = Δbytes(`PeerCache$Key` + `PeerCache$Value` + `LinkedListMultimap$Node`) +
>   ½ Δbytes(`NioInetPeer` + `SocketChannelImpl`) (the other half is the DataNode end).
> - Predictions: ΔH(1024) ≤ 4 MiB (4,194,304 B); ΔH(16) < 0.5 MiB; B_client(C) ≤ 1.5 KiB × `size`.
> - Positive control, every run: `directOpen − direct0` ≥ 64 MiB (67,108,864 B; one ≥ 64 KiB packet buffer per open reader,
>   `BlockReaderRemote.java:101`, `PacketReceiver.java:273-289`) and `fdOpen − fd0` ≥ 2000.
> - `xceivers` (closed state) = `size` + 0–2; `fdClosed − fd0` = 2 × `size` ± 20.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Part 1 `maxSize` ≤ C and `size = min(N, C)`; part 2 `size = min(1024, C)` | Mechanism works as traced: the check bounds the entry count. |
| Part 1 `maxSize > C` for any C > 0 | Check is broken / bypassable (e.g. concurrent growth) — trace wrong. |
| Per-entry retained heap ≤ ~4 KB and total delta C=1024 vs C=0 ≤ 4 MB, while FDs/`size` follow C | **Claim confirmed**: the knob caps connections, not a memory-significant quantity. |
| Heap delta grows ≥ 4 MB at C = 1024 vs 0, scaling with `size` (e.g. buffers retained per peer) | **Claim refuted**: cached entries hold memory; usage follows the constraint. |
| `size` stays 0 or tiny for C ≥ 256 (e.g. peers not returned: status not sent, sockets closed by DN) | Limit never reached → **not confirmed**; fix workload (keepalive, read to EOF) and repeat. |
| `directOpen` does not rise by tens of MB with 1024 open readers | Instrument cannot see memory at this scale → **not confirmed**. |

> **Amendment A4 (2026-11-24, stage-4 audit, before any reading) — a verdict for every row, missing rows.** Read with A3's
> definitions; "both reps" means rep 1 and rep 2 of the same C.
>
> | Observation (unit) | Verdict |
> |---|---|
> | Part 1 exact for every C (`maxSize = size = min(2048, C)`, `closed = 2048 − min(2048, C)`), part-2 `size = min(1024, C)` in every run, the positive control met in every run, ΔH(1024) ≤ 4 MiB in both reps and B_client(1024) ≤ 4 KiB × `size` | **Confirmed** — does not cap (row 3 above). ΔH is the whole JVM, so the client-side bound holds a fortiori. A missed ΔH(16) < 0.5 MiB or B_client ≤ 1.5 KiB × `size` is recorded as a flag, not a different row. |
> | As row 1, but ΔH(1024) > 4 MiB in either rep while B_client(1024) ≤ 4 KiB × `size` | **Not confirmed** (unit): the excess cannot be assigned to the client in a shared JVM (the DataNode's idle xceivers are in it, B2d); the histogram diff's top classes are reported; the cluster tier (separate JVMs) decides the client-heap question. |
> | B_client(1024) > 4 KiB × `size` in both reps | **Refuted** — caps: the client's cached-peer objects themselves hold memory that follows C (row 4 above). |
> | Part 1 `maxSize > C`, or `size > C`, for some C > 0 | **Refuted** (the entry bound of B1 is wrong; trace wrong, row 2 above). |
> | Part-2 `size` < 0.9 × min(1024, C) for C ∈ {256, 1024} in any run | **Not confirmed** (limit never reached, row 5 above). |
> | Positive control missed in any run | **Not confirmed** (row 6 above). |
> | The two reps fall in different rows of this table | **Not confirmed** (repetitions disagree). |

**B2h. Controls.** C = 0 baseline (cache disabled, same workload). Fresh JVM and fresh context name per C
(no shared cache). Expiry and DN keepalive pinned long so entries do not age out mid-measurement. Full
GC before each heap reading, three times; repeat each C run twice to estimate noise. Positive control:
direct-buffer and FD rises while the readers are open show the instruments resolve per-reader memory
and per-connection FDs at N = 1024.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed HDFS (NameNode + 1 DataNode; YARN
not needed), JDK 8. Distribution built from the local copy:
`mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`; unpack
`hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$RUN/hadoop` where `$RUN` is a local-disk directory
with ≥ 5 GB free (not shared storage). `export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf
HADOOP_LOG_DIR=$RUN/logs HADOOP_PID_DIR=$RUN/pids`; `HADOOP_HEAPSIZE_MAX=1g` for daemons;
`HADOOP_CLIENT_OPTS="-Xmx1g -XX:+UseSerialGC -XX:NativeMemoryTracking=summary"`;
`HDFS_DATANODE_OPTS="-XX:NativeMemoryTracking=summary"`. `ulimit -n` ≥ 8192 in the shell starting the
daemons and the client.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$RUN/tmp`.
- `hdfs-site.xml` (daemons): `dfs.replication=1`, `dfs.namenode.name.dir=$RUN/nn`,
  `dfs.datanode.data.dir=$RUN/dn`, `dfs.datanode.socket.reuse.keepalive=600000`,
  `dfs.datanode.max.transfer.threads=4096`.
- Client program `PeerCacheProbe` (normal FileSystem client path), compiled
  `javac -cp $(hadoop classpath) -d $RUN/probe PeerCacheProbe.java && jar cf $RUN/probe.jar -C $RUN/probe .`:

```java
import org.apache.hadoop.conf.*; import org.apache.hadoop.fs.*;
import org.apache.hadoop.hdfs.ClientContext; import org.apache.hadoop.util.*;
public class PeerCacheProbe extends Configured implements Tool {
  public int run(String[] a) throws Exception {
    int n = Integer.parseInt(a[0]); Path dir = new Path(a[1]); long holdMs = Long.parseLong(a[2]);
    Configuration conf = getConf(); FileSystem fs = FileSystem.get(conf);
    FSDataInputStream[] in = new FSDataInputStream[n]; byte[] b = new byte[65536];
    for (int i = 0; i < n; i++) { in[i] = fs.open(new Path(dir, "f" + i)); while (in[i].read(b) > 0) {} }
    System.out.println("PHASE OPEN " + System.currentTimeMillis()); System.out.flush();
    Thread.sleep(holdMs);                       // window 1: N readers open (positive control)
    for (FSDataInputStream s : in) s.close(); in = null;
    System.gc();
    System.out.println("PHASE CLOSED size=" + ClientContext.getFromConf(conf).getPeerCache().size()); System.out.flush();
    Thread.sleep(holdMs);                       // window 2: only cached peers remain
    System.out.println("PHASE END size=" + ClientContext.getFromConf(conf).getPeerCache().size());
    return 0;
  }
  public static void main(String[] a) throws Exception { System.exit(ToolRunner.run(new PeerCacheProbe(), a)); }
}
```

> **Amendment A5 (2026-11-24, stage-4 audit, before any reading) — node, distribution, daemons, probe additions.** `$RUN` =
> `R/cluster` on `pc82` (`R` as in A1; `/mydata`, local disk). The distribution is not rebuilt or unpacked: it is copied
> (`cp -a`) from the node's base build `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` to `$RUN/hadoop`
> (same `mvn … -Pdist -Dtar` build from the same source). `start-dfs.sh` needs SSH to localhost, which the nodes do not have
> (`environment.md`): daemons are started with `hdfs --daemon start namenode` and `hdfs --daemon start datanode` (no
> SecondaryNameNode; it plays no part), after `hdfs dfsadmin -safemode wait`, and stopped with `hdfs --daemon stop`.
> `HADOOP_HEAPSIZE_MAX=1g` applies to daemons and client. Probe additions (instruments only): after `FileSystem.get` it prints
> `PHASE START` and holds 40 s (window 0, the pre-open level B3f compares against); at `PHASE START`, `PHASE OPEN`,
> `PHASE CLOSED` and `PHASE END` it also prints, from inside the JVM, the cache `size`, the heap used after 3 × `System.gc()` +
> 200 ms (`MemoryMXBean`), the direct buffer pool used (`BufferPoolMXBean` "direct"), the FD count (`/proc/self/fd`), max heap
> and GC names. The class stays in the default package (run with `hadoop jar`).

**B3b. Knobs.** `dfs.client.socketcache.capacity` C ∈ {0, 16, 256, 1024}, passed per client run as
`-D dfs.client.socketcache.capacity=$C` together with `-D dfs.client.socketcache.expiryMsec=600000`
(client-only; each run is a new client JVM, no daemon restart). The DataNode keepalive (600000) is set
once in `hdfs-site.xml` before starting the DataNode (restart needed to change it).

**B3c. Workload.** 1024 files × 256 KB (256 MB in HDFS, one block each):
`mkdir -p $RUN/files && for i in $(seq 0 1023); do head -c 262144 /dev/urandom > $RUN/files/f$i; done && hdfs dfs -put $RUN/files /probe`.
Each client run opens all 1024, reads each to EOF, holds 60 s, closes all, holds 60 s. N = 1024 ≥ C
for every C, so the cap is reached (C = 1024) or passed by 1008 evictions (C = 16). Duration ≈ 2.5 min
per run, 4 C values × 2 repetitions ≈ 20 min.

**B3d. Observables and instruments.** Sampled once per window, ≥ 20 s after the `PHASE` line (client
pid from `jps | grep RunJar`, DataNode pid from `jps | grep DataNode`):
- Client connections: `ss -tnp state established '( dport = :9866 )' | grep -c "pid=$CPID,"`;
  client FDs: `ls /proc/$CPID/fd | wc -l`.
- Client memory: `jcmd $CPID GC.run`, then `jcmd $CPID GC.heap_info` (heap used),
  `jcmd $CPID GC.class_histogram | egrep 'NioInetPeer|SocketChannelImpl|PeerCache\$|LinkedListMultimap\$Node'`,
  `jcmd $CPID VM.native_memory summary` (Internal/Other = direct buffers on JDK 8/11),
  `grep VmRSS /proc/$CPID/status`.
- DataNode: `curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo' | grep XceiverCount`;
  `jcmd $DNPID Thread.print | grep -c '"DataXceiver'`; `jcmd $DNPID VM.native_memory summary`
  (Thread committed); `grep VmRSS /proc/$DNPID/status`.
- Disk: `du -sb $RUN/dn $RUN/nn $RUN/logs $RUN/tmp` before and after each run.
- The client prints the cache `size` (operand) at each phase.
Not directly observable: kernel socket buffer memory (only via `ss -tm` skmem per socket; sample it
too, `ss -tmn '( dport = :9866 )'`, for information).

**B3e. Procedure.**
1. Build and unpack (B3a); write configs; `hdfs namenode -format -nonInteractive`; `start-dfs.sh`;
   `jps` shows NameNode, DataNode (SecondaryNameNode allowed).
2. Create the workload (B3c); `hdfs dfs -ls /probe | wc -l` = 1025 (incl. header).
3. Baseline sample of the DataNode (XceiverCount, DataXceiver threads, NMT Thread, RSS).
4. For C in 0 16 256 1024 (then repeat the list once):
   `hadoop jar $RUN/probe.jar PeerCacheProbe -D dfs.client.socketcache.capacity=$C -D dfs.client.socketcache.expiryMsec=600000 1024 /probe 60000 > $RUN/out-$C.txt 2>&1 &`;
   wait for `PHASE OPEN`, sample (window 1); wait for `PHASE CLOSED`, sample (window 2); wait for exit.
   Sample the DataNode once more 10 s after exit (xceivers back to baseline).
5. Cleanup (B4).

> **Amendment A6 (2026-11-24, stage-4 audit, before any reading) — exact procedure and JDK 8 instruments.** (a) `jcmd
> GC.heap_info` does not exist on JDK 8 (added in JDK 9): the client heap reading is `jcmd $CPID GC.run` followed by
> `jstat -gc $CPID`, heap used = S0U + S1U + EU + OU (KB × 1024); the probe's own after-GC reading (A5) is recorded beside it.
> (b) The sampler (`harness/…/sample.sh`) takes one sample per window, 20 s after the `PHASE START`, `PHASE OPEN` and
> `PHASE CLOSED` lines (window 0, 1, 2): client ESTABLISHED to 9866 by pid, client FDs, `GC.run` + `jstat -gc`, the class
> histogram lines of B3d, NMT summary (Internal and Thread), `VmRSS`; DataNode XceiverCount (JMX), `"DataXceiver` thread count,
> NMT Thread, `VmRSS`. DataNode sample also before each run and 10 s after the client exits; `du -sb` of `$RUN/dn $RUN/nn
> $RUN/tmp $RUN/logs` before and after each run. (c) Order: C = 0, 16, 256, 1024, then the list again (rep 1, rep 2); one run
> at a time; the next run starts only when the DataNode XceiverCount is back to its pre-run baseline (± 2) or after 60 s.
> (d) `ulimit -n 65536` in the shell that starts the daemons and the client. (e) The client command is
> `HADOOP_CLIENT_OPTS="-Xmx1g -XX:+UseSerialGC -XX:NativeMemoryTracking=summary" hadoop jar $RUN/probe.jar PeerCacheProbe
> -D dfs.client.socketcache.capacity=$C -D dfs.client.socketcache.expiryMsec=600000 1024 /probe 60000`.

**B3f. Predictions.**
- Window 1 (all readers open), every C: client ESTABLISHED to 9866 ≈ 1024; DN XceiverCount ≈ 1024;
  client direct/Internal NMT ≥ ~64 MB above its pre-open level (1024 × ≥ 64 KB packet buffers) —
  positive control, independent of C.
- Window 2 (after close): `size` = client ESTABLISHED to 9866 = DN XceiverCount (± 2) = min(1024, C):
  0, 16, 256, 1024. DN `DataXceiver` thread count follows the same numbers.
- Client heap used after GC, window 2: C = 1024 vs C = 0 differs by ≤ 4 MB; C = 16 vs 0 ≤ 0.5 MB (noise).
  Client RSS difference C = 1024 vs 0: ≤ 8 MB.
- Disk (`du`) of `$RUN/dn`, `$RUN/nn`, `$RUN/tmp`: no difference between C values (logs may differ
  by a few KB of DataXceiver debug/info lines).
- DataNode: NMT Thread committed and RSS rise roughly in proportion to the idle xceiver threads
  (expected tens of KB of touched stack per thread, i.e. order of tens of MB at 1024) — this is the
  indirect thread-count effect named in Ground, and it also occurs in window 1 for every C.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Window-2 connections = min(1024, C), and the positive control (window 1 direct memory ≥ 64 MB, 1024 connections) moved | The cap binds — on connections — and the instruments resolve memory at this scale. |
| …and client heap/RSS flat in C (≤ 4 MB / ≤ 8 MB at C = 1024 vs 0), disk flat | **Claim confirmed** (negative): usage of memory/disk does not follow the constraint on the client. |
| Client heap or RSS grows ≥ 4 MB / 8 MB with C, proportional to `size` | **Claim refuted**: cached peers retain memory; usage follows the constraint. |
| Any disk quantity changes with C beyond log lines | **Claim refuted** for disk. |
| DN NMT Thread/RSS grows with min(N, C) in window 2 by tens of MB | Indirect thread memory follows the connection count; report it separately — it is the same per-thread cost seen in window 1 for every C and is bounded by the DN keepalive and `dfs.datanode.max.transfer.threads`; if stage 4 judges it significant, it is the one ground on which the negative estimate could be revised. |
| Window-2 connections ≈ 0 for all C (or much less than min(N, C)) | Limit never reached (status not sent, DN keepalive not applied, expiry) → **not confirmed**; check `hdfs-site.xml` keepalive and that files are read to EOF. |
| Window-1 direct memory does not move | Instrument insensitive → **not confirmed**. |

> **Amendment A7 (2026-11-24, stage-4 audit, before any reading) — a verdict for every row, numbers, missing rows.**
> Definitions (relative to the C = 0 run of the same rep): **ΔH2(C)** = client heap used in window 2 (A6a, `jstat` after
> `GC.run`) at C minus at C = 0; **ΔRSS2(C)** likewise for client `VmRSS`. **Connections2(C)** = client ESTABLISHED to 9866 in
> window 2. **Positive control** (every run): probe direct pool at `PHASE OPEN` minus at `PHASE START` ≥ 64 MiB, and
> window-1 client ESTABLISHED ≥ 1000. **Disk flat**: `du -sb` of `$RUN/dn + $RUN/nn + $RUN/tmp` after minus before each run
> ≤ 1 MiB in every run (logs reported, not judged).
>
> | Observation (cluster) | Verdict |
> |---|---|
> | Connections2 = printed `size` = min(1024, C) ± 2 for every C in both reps; positive control met in every run; ΔH2(1024) ≤ 4 MiB and ΔRSS2(1024) ≤ 8 MiB in both reps; disk flat | **Confirmed** — does not cap (rows 1 and 2 above). A missed ΔH2(16) ≤ 0.5 MiB is a flag. |
> | ΔH2(1024) > 4 MiB or ΔRSS2(1024) > 8 MiB in both reps, and the same quantity at C = 256 is 10–50 % of its value at C = 1024 in both reps (follows `size`) | **Refuted** — caps (row 3 above). |
> | ΔH2(1024) > 4 MiB or ΔRSS2(1024) > 8 MiB, but not in both reps or not following `size` as above | **Not confirmed** (memory reading not settled). |
> | Disk not flat in some run, with the change growing with C | **Refuted** for disk (row 4 above); not growing with C → **Not confirmed**. |
> | Connections2 < 0.9 × min(1024, C) for C ∈ {256, 1024} in any run | **Not confirmed** (limit never reached, row 6 above). |
> | Positive control missed in any run | **Not confirmed** (row 7 above). |
> | The two reps fall in different rows of this table | **Not confirmed** (repetitions disagree). |
>
> The DataNode row (row 5 above) is **reported, not judged**: B1 claims nothing about DataNode memory (its idle-thread cost is
> the indirect effect named in Ground, bounded by `dfs.datanode.socket.reuse.keepalive` and `dfs.datanode.max.transfer.threads`),
> so it does not change the verdict; its numbers go in the results file's findings. Effect on the constraint for a Confirmed row:
> `does not cap`; for a Refuted row: `caps`.

**B3h. Controls.** C = 0 run with the identical workload as baseline; two repetitions per C; heap read
only after `GC.run`; DataNode sampled before each run to confirm xceivers returned to baseline (no
carry-over between runs); the positive-control window inside every run; `ss` filtered by the client pid
so other clients' sockets are not counted; nothing else uses the cluster during runs.

**B4. Risks and cleanup.** Disk: unit tier ~64 MB under `target/test/data`; cluster tier ~256 MB local
files + 256 MB HDFS block data + logs, all under `$RUN` on local disk; never point any data/log dir at
shared storage. FDs: up to ~2100 per JVM in the unit tier (both ends) — raise `ulimit -n`. Ports: 9000,
9866, 9864, 9867, 9870, 9868 — check free beforehand (`ss -ltn`). Memory: client 1 GB, daemons 1 GB each.
Cleanup: `stop-dfs.sh`; `jps` must show no NameNode/DataNode/SecondaryNameNode/RunJar/surefire JVM; kill
leftovers by pid; `rm -rf $RUN/files $RUN/dn $RUN/nn $RUN/tmp` (keep `$RUN/out-*.txt` and logs for the
results); in the source copy `rm -rf hadoop-hdfs-project/hadoop-hdfs/target/test/data`.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/PeerCache.java
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/ClientContext.java (140-265)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java (96-101)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/impl/DfsClientConf.java (764-797, 877-880)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/impl/BlockReaderRemote.java (101, 124, 232-239, 290-335)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/impl/BlockReaderFactory.java (530-550, 790-870)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSInputStream.java (600-615, 1760-1769)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSClient.java (3067-3088)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSUtilClient.java (852-854)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/net/NioInetPeer.java (30-75)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/datatransfer/PacketReceiver.java (55, 89, 273-304)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (470-471, 1975-1985)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataXceiver.java (148, 239, 255-305)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DNConf.java (150-152)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java (2744-2756)
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (125-127, 1651-1654, 3168-3171, 4631-4646, 4919-4925)
- hadoop-hdfs-project/hadoop-hdfs-client/src/test/java/org/apache/hadoop/hdfs/TestPeerCache.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/TestConnCache.java (86-121)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/TestDataTransferKeepalive.java (test list)

## D. Stage-4 feedback

**D1. Audit amendments (2026-11-24, stage 4, before any harness run or reading).** Results file: `results.md` beside this file
(`~/writeup-hadoop/out/o11/results.md`). A1 (B2a) node paths, no install build, surefire options through
`maven-surefire-plugin.argLine`; A2 (B2 test) `direct0`, rep, histogram file, run order; A3 (B2f) predictions with both socket
ends in one JVM (`NioInetPeer` ≈ 2 × `size`), ΔH and B_client defined, positive control in numbers; A4 (B2g) a verdict for every
row, the shared-JVM row and the repetitions row; A5 (B3a) node, distribution copy, `hdfs --daemon`, probe window 0 and in-process
readings; A6 (B3d/B3e) `jstat` instead of JDK 9's `GC.heap_info`, exact sampling and order; A7 (B3g) a verdict for every row,
numbers, the DataNode row reported but not judged. Filed sha256 `f824ab0d…50feee84`; the sha256 after A1–A7 is recorded in the
results file §1.

**D2. Stage-4 run 1 and verdict (2026-11-25, node `pc82`).** Results file: `results/dfs.client.socketcache.capacity-putInternal-capacity--autonomous.md`
(drafted at `~/writeup-hadoop/out/o11/results.md`). Frozen version: sha256 `54b7f50d…1bb5` (this file with A1–A7, re-audited
2026-11-25, no new amendment). Harness: `TestPeerCacheCapacityProbe.java`, `unit-run.sh`, `PeerCacheProbe.java`, `sample.sh`,
`cluster-run.sh`, `summarize.py`. Runbook defects: none.
- **Unit tier: Confirmed — does not cap** (A4 row 1). Part 1 exact for C ∈ {0, 1, 16, 256, 1024} (`maxSize = size = min(2048, C)`,
  `closed = 2048 − min(2048, C)`). Part 2, both reps: `size` = 0/16/256/1024 = DataNode xceivers; client cache objects
  B_client = 232 B per entry (237,496 B at C = 1024); whole-JVM ΔH(1024) = −98.9 / −99.6 MiB by MemoryMXBean (noisy) and
  +3.96 / +3.90 MiB by the live class histogram (DataNode-side idle-thread objects); positive control +65.06 MiB direct and
  ≥ 5114 FDs with 1024 readers open in every run.
- **Cluster tier: Confirmed — does not cap** (A7 row 1). Window-2 connections = `size` = DN XceiverCount = 0/16/256/1024, both reps;
  client heap ΔH2(1024) = +0.75 / +0.76 MiB, ΔRSS2(1024) = +2.6 / +2.6 MiB; disk unchanged (0 B) in every run; positive control
  +64.54 MiB direct and 1024 connections in window 1 of every run. Reported, not judged: DataNode RSS +25–44 MiB and NMT Thread
  +1 GiB reserved stack at C = 1024 (one idle `DataXceiver` per cached socket).
- **Effect on the constraint:** `does not cap` (both tiers). **Outcome class: true negative.** The estimate stands.
- Feedback (not applied): A3's `fdClosed − fd0 = 2 × size ± 20` misses the pooled NIO selectors of `SocketIOWithTimeout` (3 FDs each);
  the unit ΔH should be read from the live class-histogram total rather than MemoryMXBean in a shared client+DataNode JVM.
