# ipc.server.max.response.size — verification solution  <!-- file: cases/ipc.server.max.response.size-setupResponse-maxRespSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`Server.java:3557`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/Server.java#L3557) — `if (response.length > maxRespSize)` in `Server.setupResponse(RpcCall, RpcResponseHeaderProto, Writable)`. This is the enforcement point named in the stem. The only other check on the same key is the buffer-shrink check at `Server.java:3576` in `setupResponseForWritable`, covered in A3. |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `negative`. At the target line the key only decides whether a WARN is logged. The response `byte[]` is already fully built, and it is sent whatever its size. The only memory effect of the key is elsewhere (`Server.java:3576`): it shrinks a per-handler thread-local buffer *after* a call. That path is the Writable path only, which NameNode/RM/NM protocols on `ProtobufRpcEngine2` do not take, and it never bounds the peak size. |
| Ground | `response.length` is compared with `maxRespSize` only after `setupResponseForProtobuf`/`setupResponseForWritable` has allocated the whole response (`Server.java:3552-3556`). Both branches of the check end at `call.setResponse(ByteBuffer.wrap(response))` (`Server.java:3561`), so the response is neither rejected, truncated nor split. The quantity the check measures (response size, and the heap allocated to hold it until the Responder writes it) cannot follow the key. |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/<full path under the repository root>#L123)`
> (a range is `#L123-L130`). Check that the line number is the line you mean. Other citations may
> stay plain `file:line`.

## A. Constraint trace

**A1. The constraint.**
- **Name:** `ipc.server.max.response.size` (exact key; no placeholder).
- **Kind:** configuration key (`int`).
- **Declared:** [`CommonConfigurationKeys.java:63-64`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/CommonConfigurationKeys.java#L63-L64) as `IPC_SERVER_RPC_MAX_RESPONSE_SIZE_KEY`. The Javadoc at `CommonConfigurationKeys.java:62` says "Responses larger than this will be logged". The default `IPC_SERVER_RPC_MAX_RESPONSE_SIZE_DEFAULT = 1024*1024` is at `CommonConfigurationKeys.java:66-67`.
- **`core-default.xml` entry:** `core-default.xml:2516-2522`, value `1048576`. Its description reads "The maximum size when large IPC handler response buffer is reset." The Java constant and the XML value agree, both 1 MiB.
- **Unit:** bytes.
- **Read:** once, in the `Server` constructor: `this.maxRespSize = conf.getInt(...)` at `Server.java:3332-3334`, into a `private final int` field (`Server.java:486`). It is not per-port (no `ipc.<port>.` prefix lookup), and no `reconfig` list includes it, so a change needs the daemon to restart.
- **How to set:** `core-site.xml` (or the daemon's own `*-site.xml` merged into the conf passed to the RPC server), or `-D` for a server built in a test/program.
- **Who reads it:** every Hadoop IPC server built from `org.apache.hadoop.ipc.Server`/`RPC.Server`, for example the NameNode client and service RPC servers, the DataNode IPC server, the ResourceManager, the NodeManager, the JobHistory server and ZKFC.
- **Related constant:** `Server.INITIAL_RESP_BUF_SIZE = 10240` (`Server.java:262`, static, not configurable except by tests). This is the size the buffer is reset to.

**A2. What it caps.**
- The key is meant to bound **daemon heap** held by IPC response buffers. Its name suggests a cap on RPC response size, but it is not one.
- **Quantity compared at the target check:** `response.length`, the length of the fully serialized response `byte[]` (header plus payload plus 4-byte frame) for one call.
- **Quantity compared at the sibling check (`Server.java:3576`):** `buf.capacity()`, the capacity of the handler thread's reusable `ResponseBuffer` (a `ThreadLocal`, `Server.java:487-493`), on the Writable serialization path only.

**A3. Mechanism.**
1. A handler finishes a call and runs `RpcCall.doResponse` (`Server.java:1309-1327`). That calls `setupResponse(call, status, ...)` (`Server.java:3507`), which builds the header and calls `setupResponse(call, header, rv)` (`Server.java:3529` or `:3545`).
2. `Server.java:3551-3556` serializes the response.
   - If `rv == null` or `rv instanceof RpcWritable.ProtobufWrapper`, it calls `setupResponseForProtobuf` (`Server.java:3585-3608`). That method allocates `new byte[length + 4]` sized exactly to the message (`Server.java:3593`). This is the path for every response of an `RPC_PROTOCOL_BUFFER` call on `ProtobufRpcEngine2`, because `ProtobufRpcEngine2.java:640` returns `RpcWritable.wrap(result)`, which yields `ProtobufWrapper` for a shaded `Message` (`RpcWritable.java:43-45`). Error responses (`rv == null`, `Server.java:3545`) and SASL-wrapped responses (`Server.java:3659`, an `RpcSaslProto`) take this path too.
   - Otherwise it calls `setupResponseForWritable` (`Server.java:3564-3581`). That writes into the thread-local `ResponseBuffer` (`Server.java:3566`), which grows as a `ByteArrayOutputStream` (`ResponseBuffer.java:76-104`), and then copies it out with `buf.toByteArray()` (`Server.java:3572`). This path covers `RPC_BUILTIN` Writable servers, `WritableRpcEngine` (`ObjectWritable` results, `WritableRpcEngine.java:615`), and the deprecated unshaded `ProtobufRpcEngine` (`ProtobufWrapperLegacy`, `RpcWritable.java:46-48`).
3. **The check:** [`Server.java:3557`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/Server.java#L3557), `if (response.length > maxRespSize)`.
   - True: `LOG.warn("Large response size " + response.length + " for call " + call)` (`Server.java:3558-3559`). The logger is `org.apache.hadoop.ipc.Server` (`Server.java:320`).
   - False: nothing happens.
   - **Both outcomes** go on to `call.setResponse(ByteBuffer.wrap(response))` (`Server.java:3561`). The whole response is kept in `call.rpcResponse` (`Server.java:1172`, `:1304-1305`) until the Responder or handler writes it (`Server.java:1844-1876`, which nulls it after the last byte at `:1876`). Nothing is rejected, truncated or deferred, and nothing applies back-pressure.
4. **Sibling check:** `Server.java:3576`, `if (buf.capacity() > maxRespSize) buf.setCapacity(INITIAL_RESP_BUF_SIZE)`, inside the `finally` of `setupResponseForWritable`. After a Writable response has been copied out, the handler's thread-local buffer is shrunk back to 10240 bytes (plus 4 framing bytes; `ResponseBuffer.java:95-97` does `Arrays.copyOf`) if it grew past the key. This is the behaviour HADOOP-6577 made configurable (A5). It bounds only the buffer **retained** per handler thread between calls. Within a call the buffer still grows to the full response size, and `toByteArray` doubles the peak.
5. **Bypasses and overshoots.**
   - The protobuf path never touches the thread-local buffer, so the key has no memory effect there at all.
   - On the Writable path the peak per call is at least about 2 × response size (the buffer plus the `toByteArray` copy), whatever the key.
   - With N handlers, up to N responses of any size can be in flight, plus every queued unsent response in each connection's `responseQueue`. None of this is bounded by the key.
   - A small key value makes the Writable path *re-grow* the buffer on every large response, which adds allocation churn.
6. **In-tree production users of the Writable path:** none found. `WritableRpcEngine` is referenced only from `RPC.java` (as the default engine, `RPC.java:220-229`) and itself. The only in-tree caller of the unshaded `ProtobufRpcEngine` is `DFSUtil.addPBProtocol` (`DFSUtil.java:1417-1422`, `@Deprecated`), and nothing in main code calls it. So in the HDFS/YARN/MR daemons of 3.4.2 the key's only effect is the WARN at the target line.

**A4. Other consumers.**
- **Daemon heap outside this key:**
  - Request buffers, bounded by `ipc.maximum.data.length` (`CommonConfigurationKeys.java:82-86`, server side).
  - The call queue, bounded by `ipc.server.handler.queue.size` × handlers (`Server.java:3325-3331`).
  - Queued unsent responses per connection.
  - Each protocol's own result objects: the NameNode `getListing` batch bounded by `dfs.ls.limit` (`FSDirectory.java:368-371`), block locations, and so on.
- **Client side:** `ipc.maximum.response.length` (`CommonConfigurationKeys.java:88-92`, default 128 MiB) is the setting that actually rejects an oversized response, at `Client.java:1937-1940` ("RPC response has a length of %d exceeds maximum data length"). The client then allocates the response at `Client.java:1941`. This is used as the positive control below.
- **Disk:** the WARN line itself goes to the daemon log, which grows by one line per large response.

**A5. Evidence beyond the source.**
- HADOOP-6577 "IPC server response buffer reset threshold should be configurable" (https://issues.apache.org/jira/browse/HADOOP-6577). Its release note `hadoop-common-project/hadoop-common/src/site/markdown/release/0.21.0/RELEASENOTES.0.21.0.md:1859-1863` says the key is "the maximum size when large IPC handler response buffer is reset". It is a buffer-reset threshold, not a response cap.
- `core-default.xml:2516-2522` (same wording).
- Existing test `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/ipc/TestIPCServerResponder.java:137-144` (`testResponseBuffer`). It sets the key to 1 and `INITIAL_RESP_BUF_SIZE` to 1 and only checks that calls still succeed, which is consistent with "does not reject".

## B. Verification solution

**B1. Claim under test.** Changing `ipc.server.max.response.size` (1 KiB, 1 MiB, 64 MiB) does not change the size of any RPC response a Hadoop IPC server builds and sends, nor the heap allocated per call to build it. At the target check it changes only whether `Large response size` is logged. The claim is refuted if the response size, the bytes sent, or the per-call allocation for the same workload moves with the key, or if a response above the key is rejected or truncated.
(Side claim, used as a positive control: on the Writable path only, the handler's retained thread-local buffer after a call is `INITIAL_RESP_BUF_SIZE` when the response exceeded the key, and about the response size otherwise.)

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8 (HotSpot or OpenJDK; `com.sun.management.ThreadMXBean` is required), Maven 3.3+.
- Work in a local copy of the tag on local disk, never in the shared tree. For example `rsync -a <source>/ $RUN/src/`, where `$RUN` is a local-disk directory with at least 10 GB free.
- Build: `cd $RUN/src && mvn -pl hadoop-common-project/hadoop-common -am install -DskipTests -Dmaven.javadoc.skip=true`.
- Add one test file, `$RUN/src/hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/ipc/TestMaxRespSizeVerification.java`. It goes in package `org.apache.hadoop.ipc` to reach the package-private `ResponseBuffer.capacity()` and `Client.call(..., int serviceClass, AtomicBoolean)`, and it extends `TestRpcBase`.
- The test JVM uses the default surefire `argLine` from `hadoop-project/pom.xml`. The largest response is 16 MiB, so a heap of 1 GB or more is plenty.

Test outline (complete enough to type in):

```java
package org.apache.hadoop.ipc;
// imports: java.lang.management.ManagementFactory, java.lang.reflect.Field, java.net.InetSocketAddress,
// org.apache.hadoop.conf.Configuration, org.apache.hadoop.fs.CommonConfigurationKeys,
// org.apache.hadoop.io.*, org.apache.hadoop.ipc.Client.ConnectionId, org.apache.hadoop.ipc.protobuf.TestProtos,
// org.apache.hadoop.ipc.protobuf.TestRpcServiceProtos, org.apache.hadoop.net.NetUtils,
// org.apache.hadoop.test.GenericTestUtils.LogCapturer, org.apache.hadoop.thirdparty.protobuf.*, org.junit.Test
public class TestMaxRespSizeVerification extends TestRpcBase {
  static final com.sun.management.ThreadMXBean TMX =
      (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
  static volatile long a1, a2; static volatile int capAtProbe;
  static long alloc() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }
  @SuppressWarnings("unchecked")
  static int tlCapacity() throws Exception {               // handler thread's ResponseBuffer
    Field f = Server.class.getDeclaredField("responseBuffer"); f.setAccessible(true);
    return ((ThreadLocal<ResponseBuffer>) f.get(Server.get())).get().capacity();
  }
  // --- Writable path (setupResponseForWritable) ---
  static class WServer extends Server {
    WServer(Configuration c) throws java.io.IOException { super("0.0.0.0", 0, IntWritable.class, 1, c); }
    @Override public Writable call(RPC.RpcKind k, String p, Writable param, long t) throws java.io.IOException {
      int n = ((IntWritable) param).get();
      if (n == 0) { a2 = alloc(); try { capAtProbe = tlCapacity(); } catch (Exception e) { throw new java.io.IOException(e); }
                    return new BytesWritable(new byte[0]); }
      BytesWritable out = new BytesWritable(new byte[n]); a1 = alloc(); return out;
    }
  }
  // --- Protobuf path (setupResponseForProtobuf) ---
  static class ProbeImpl extends PBServerImpl {
    @Override public TestProtos.EchoResponseProto echo(RpcController c, TestProtos.EchoRequestProto r) throws ServiceException {
      if (r.getMessage().length() == 1) { a2 = alloc(); try { capAtProbe = tlCapacity(); } catch (Exception e) { throw new ServiceException(e); } }
      TestProtos.EchoResponseProto resp = TestProtos.EchoResponseProto.newBuilder().setMessage(r.getMessage()).build();
      resp.getSerializedSize(); a1 = alloc(); return resp;   // memoize size before A1
    }
  }
  // For each key value K in {1024, 1048576, 67108864} and N in {524288, 4194304, 16777216}:
  //  conf.setInt(CommonConfigurationKeys.IPC_SERVER_RPC_MAX_RESPONSE_SIZE_KEY, K); fresh server, 1 handler;
  //  LogCapturer logs = LogCapturer.captureLogs(Server.LOG);
  //  probe -> C0 ; big(N) ; probe -> D1=a2-a1, C1 ; big(N) ; probe -> D2=a2-a1, C2 ;
  //  record: client-received payload length, D1, D2, C0..C2, count of "Large response size" in logs.getOutput()
  //  and the size printed in it; RpcMetrics sentBytes before/after (server.getRpcMetrics().getSentBytes()
  //  if available, else read MutableCounterLong via MetricsAsserts.getMetrics(server.getRpcMetrics().name())).
  //  Writable: Client cl = new Client(BytesWritable.class, conf); ConnectionId id = ConnectionId.getConnectionId(
  //    NetUtils.getConnectAddress(ws), null, null, 0, null, conf);
  //    cl.call(RPC.RpcKind.RPC_BUILTIN, new IntWritable(N), id, RPC.RPC_SERVICE_CLASS_DEFAULT, null);  probe: IntWritable(0)
  //  Protobuf: RPC.Server s = new RPC.Builder(conf).setProtocol(TestRpcService.class)
  //    .setInstance(TestRpcServiceProtos.TestProtobufRpcProto.newReflectiveBlockingService(new ProbeImpl()))
  //    .setBindAddress("0.0.0.0").setPort(0).setNumHandlers(1).build(); s.start();
  //    (call setupConf() first so ProtobufRpcEngine2 is registered); proxy = getClient(NetUtils.getConnectAddress(s), conf);
  //    proxy.echo(null, newEchoRequest(<N 'a' chars>));  probe: newEchoRequest("x")
  //  Print one line per (path, K, N) to stdout and to target/maxresp-<path>.csv; stop server and client.
}
```

**B2b. Knobs.**
- `ipc.server.max.response.size` set by `conf.setInt` before the server is built (read only in the constructor). Values:
  - `1024`: far below every large response; the WARN fires and the Writable buffer is always reset.
  - `1048576`: the default; sits between N = 512 KiB and N = 4 MiB.
  - `67108864`: above every response; no WARN and no reset.
- Response payload size N ∈ {512 KiB, 4 MiB, 16 MiB}, chosen to lie on both sides of each key value. This is a workload parameter, not a knob of the constraint.
- Serialization path: Writable vs protobuf.

**B2c. Workload.**
- One handler, so the same thread runs every call and its thread-local is observed.
- Per (K, N) pair: probe, big, probe, big, probe.
- Response length:
  - Writable path: response = varint header (about 20 bytes) + 4-byte `BytesWritable` length + N, plus the 4-byte frame, so `response.length` ≈ N + about 28 bytes.
  - Protobuf path: response = header + `EchoResponseProto{message}`, so `response.length` ≈ N + about 30 bytes (ASCII string, 1 byte per char).
- `response.length` > K whenever N ≥ 512 KiB and K = 1024; > K for N ≥ 4 MiB at K = 1 MiB; never > K at K = 64 MiB. Every limit is reached and exceeded on at least one side.

**B2d. Observables and instruments.**

| Observable | What it is | How it is measured |
|---|---|---|
| R | Size of the received payload | Client side: `BytesWritable.getLength()` or `getMessage().length()` |
| L | Response size and WARN status | Count of `Large response size <len>` lines in `LogCapturer` output, plus the `<len>` printed; this gives `response.length` directly when logged |
| D | Bytes the handler thread allocated between finishing the big call's `call()`/`echo()` (A1) and starting the next probe (A2) | `ThreadMXBean.getThreadAllocatedBytes`. This window contains `setupResponse` and the handler-side write. Probes are 1 byte, so the probe's own request parsing is negligible. |
| C | Thread-local `ResponseBuffer` capacity as seen at the next probe | Reflection |
| S | Bytes the server wrote to sockets | `RpcMetrics.sentBytes` (`RpcMetrics.java:121`, incremented at `Server.java:3929`), delta per run |

Not directly observable: the instantaneous heap peak inside `setupResponse`. D is used as its proxy.

**B2e. Procedure.**
1. Build as in B2a.
2. `cd $RUN/src && mvn -pl hadoop-common-project/hadoop-common test -Dtest=TestMaxRespSizeVerification -DfailIfNoTests=false`.
3. Collect `hadoop-common-project/hadoop-common/target/maxresp-*.csv` and `target/surefire-reports/*TestMaxRespSizeVerification-output.txt`.
4. Run the whole test 3 times and keep all rows. D may vary by small amounts (logging and string building).
5. Confirm with `jps` that no forked surefire JVM is left.

**B2f. Predictions** (stated before any run).

*Protobuf path (target check)*, for every K:
- R = N.
- S per big call ≈ N + about 30 bytes.
- D ≈ N to 2N (one `byte[N+~34]` plus possible serialization temporaries). D is **the same for K = 1024, 1 MiB and 64 MiB** within ±64 KiB or ±5 %, whichever is larger.
- C = 10240 at every probe; the protobuf path never touches the buffer.
- L: WARN present iff N + ~30 > K. So it appears for all three N at K = 1024, for N = 4 MiB and 16 MiB at K = 1 MiB, and never at K = 64 MiB. The logged length equals `response.length` ≈ N + ~30 in each case.

*Writable path*, R = N and S ≈ N + ~28 for every K:

| K | N | C1, C2 | D1 | D2 | WARN |
|---|---|---|---|---|---|
| 1024 | any | 10240 (reset every time) | ≈ 2N | ≈ 2N (re-grow + copy) | yes |
| 1 MiB | 512 KiB | ≈ N + ~28 (retained, ≤ 1 MiB) | ≈ 2N | ≈ N (copy only) | no |
| 1 MiB | 4 MiB, 16 MiB | 10240 | ≈ 2N | ≈ 2N | yes |
| 64 MiB | any | ≈ N + ~28 (retained) | ≈ 2N | ≈ N | no |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Protobuf path: R = N, S and D the same across K, C stays 10240, WARN only when length > K | Claim confirmed: at the target check the key only logs |
| Protobuf path: R < N, or the call fails with an exception, when N > K | Claim refuted: the key rejects or truncates responses |
| Protobuf path: D or S shrinks as K falls (beyond the noise band) | Claim refuted: usage follows the key |
| Writable path: C = 10240 exactly when length > K, ≈ N otherwise (positive control moves) | The key is read and binds where the source says (retained buffer); confirms the server under test saw K |
| Writable path: C does not change with K | Positive control failed: the key was not applied (the conf did not reach the server). The run does not confirm anything; fix the setup. |
| WARN never appears at K = 1024 | The target check was not reached (wrong path, or logger level); not confirmed |
| Large D on both paths but K-independent | Usage is real and unbounded by the key: confirms the negative estimate |

**B2h. Controls.**
- The Writable-path rows are the positive control: the same key on the same server class visibly changes retained memory.
- The WARN presence or absence per (K, N) shows that each K value was in effect.
- A fresh server and client per K avoids carry-over of the thread-local buffer.
- Probes isolate `setupResponse` allocation from request parsing.
- Each N is run at all three K values, so any D difference is attributable to K.
- Three repetitions bound the noise.

### B3. Cluster tier

**B3a. Environment and build.**

*Host, build and runtime*
- One Linux host, pseudo-distributed HDFS: a NameNode and one DataNode. The NameNode is the RPC server under test; it uses `ProtobufRpcEngine2` for `ClientProtocol`.
- Distribution: `cd $RUN/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`. Then unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$RUN/hadoop`.
- Run the daemons on **JDK 11** so the `jfr` CLI is available; JDK 8 is fine for the build. If only JDK 8 is available, drop the JFR observable and keep the others.

*`etc/hadoop/hadoop-env.sh`*
```
export JAVA_HOME=<jdk11>
export HADOOP_LOG_DIR=$RUN/logs
export HADOOP_PID_DIR=$RUN/pids
export HADOOP_HEAPSIZE_MAX=1g
export HDFS_NAMENODE_OPTS="-XX:+UseG1GC -Xms1g"
```

*`core-site.xml`*
- `fs.defaultFS=hdfs://localhost:29820`
- `hadoop.tmp.dir=$RUN/tmp`
- `ipc.server.max.response.size=<K>`, the knob.

*`hdfs-site.xml`*
- `dfs.replication=1`
- `dfs.namenode.name.dir=$RUN/nn`
- `dfs.datanode.data.dir=$RUN/dn`
- `dfs.ls.limit=10000`, so one `getListing` returns a multi-MB response.
- Non-default ports to avoid colliding with other users: `dfs.namenode.http-address=localhost:29870`, `dfs.datanode.address=localhost:29866`, `dfs.datanode.http.address=localhost:29864`, `dfs.datanode.ipc.address=localhost:29867`.

*Disk:* `$RUN` on local disk. The usage is less than 1 GB: no blocks are written, only metadata and logs.

**B3b. Knobs.**
- `ipc.server.max.response.size` ∈ {`1024`, `1048576` (default), `67108864`}, set in `core-site.xml`. Same reasons as B2b: below, between and above the roughly 2.5 MB response.
- Each change needs a **NameNode restart** (`hdfs --daemon stop namenode; hdfs --daemon start namenode`). The key is a final field read once in the constructor and cannot be refreshed.
- `dfs.ls.limit=10000` stays fixed.

**B3c. Workload.**
- Once, after format: create `/big` with 10000 subdirectories, each named with 195 `a` characters plus a 5-digit index (200 chars, under the 255-byte `dfs.namenode.fs-limits.max-component-length`):
  ```
  P=$(printf 'a%.0s' $(seq 195)); seq -w 0 9999 | sed "s|^|/big/$P|" | xargs -n 1000 hdfs dfs -mkdir -p
  ```
- Each entry is an `HdfsFileStatusProto` of roughly 250 to 300 bytes (200-byte name plus about 60 to 100 bytes of fields). One `getListing` response is therefore about 2.5 to 3 MB:
  - above K = 1024 and K = 1 MiB, so the WARN fires;
  - below K = 64 MiB, so no WARN;
  - well below the client cap of 128 MiB.
- Per K value: `for i in $(seq 20); do hdfs dfs -ls /big | wc -l; done`. Each ls is one `getFileInfo` plus one `getListing` of 10000 entries; about 2 minutes, dominated by JVM start-up.

**B3d. Observables and instruments.**

| Observable | Instrument | Sampling |
|---|---|---|
| Entries returned | `hdfs dfs -ls /big \| wc -l`; expect 10001 (with the `Found` line) | Every run |
| Logged response length | `grep -c 'Large response size' $RUN/logs/hadoop-*-namenode-*.log` and the lengths printed | Before and after each K run |
| Bytes sent by the NN client RPC server | `curl -s 'http://localhost:29870/jmx?qry=Hadoop:service=NameNode,name=RpcActivityForPort29820' \| grep -E 'SentBytes\|RpcProcessingTimeNumOps'` | Before and after the 20 calls; per-call delta = ΔSentBytes / 20, minus the small `getFileInfo` |
| Per-call allocation for the response | NN JFR: `jcmd <nnpid> JFR.start name=r settings=profile filename=$RUN/jfr-<K>.jfr` before the loop, `jcmd <nnpid> JFR.stop name=r` after, then `jfr print --events jdk.ObjectAllocationOutsideTLAB --stack-depth 6 $RUN/jfr-<K>.jfr` | Filter events whose top frames include `Server.setupResponseForProtobuf`; record `allocationSize`. With G1 and a 1 GB heap, a 2.5 MB array is humongous and always outside a TLAB. |
| Retained heap | `jcmd <nnpid> GC.run` then `jcmd <nnpid> GC.heap_info` (old/humongous used), and `jcmd <nnpid> GC.class_histogram \| grep '\[B'` | Before and after the loop |

Not directly observable: the per-call peak heap. The JFR allocation sizes and SentBytes are its proxies.

**B3e. Procedure.**
1. Build, unpack and write the configuration as in B3a, with K = 1048576.
2. `hdfs namenode -format -force`.
3. `hdfs --daemon start namenode && hdfs --daemon start datanode`.
4. `hdfs dfsadmin -safemode wait`.
5. Create `/big` (B3c).
6. For K in 1024, 1048576, 67108864:
   1. Edit `core-site.xml`.
   2. Restart the NameNode and `hdfs dfsadmin -safemode wait`.
   3. Note the WARN count and the JMX `SentBytes`.
   4. Start JFR.
   5. Run the 20-ls loop and record the line counts.
   6. Stop JFR.
   7. Note the WARN count and `SentBytes` again.
   8. Run `jcmd GC.run` and `GC.heap_info`.
   9. Extract the JFR allocations.
7. **Positive control**, at K = 67108864 (so no server-side effect is in play):
   - `hdfs dfs -D ipc.maximum.response.length=1048576 -ls /big`. Expect failure with `RPC response has a length of <~2.5e6> exceeds maximum data length`.
   - `hdfs dfs -D ipc.maximum.response.length=4194304 -ls /big`. Expect 10001 lines.
8. Repeat step 6 once more for K = 1024 to check repeatability.
9. Clean up as in B4.

**B3f. Predictions** (stated before any run).

| K | Lines per ls | New `Large response size` lines | Per-`getListing` ΔSentBytes | JFR allocation in `setupResponseForProtobuf` | Old/humongous after `GC.run` |
|---|---|---|---|---|---|
| 1024 | 10001 every time | ≥ 20, each printing ≈ the same length L (about 2.5–3 MB); may also include other small responses > 1 KiB | ≈ L | One event per `getListing` of ≈ L + 4 bytes | Equal to the other K values within ±5 % |
| 1048576 | 10001 | Exactly 20 at length L (`getFileInfo` responses are far below 1 MiB) | ≈ L, equal to K = 1024 within ±1 % | ≈ L + 4 | Same |
| 67108864 | 10001 | 0 | ≈ L, same | ≈ L + 4 | Same |

Positive control: failure at a client cap of 1 MiB; success at 4 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Listing complete, SentBytes and JFR allocation size equal across K; WARN only at 1024 and the default; positive control fails at 1 MiB | Claim confirmed: usage does not follow the key, and the same workload is capped where a real cap (`ipc.maximum.response.length`) binds |
| Fewer than 10001 lines, or an RPC error, at K = 1024 or 1 MiB but not at 64 MiB | Claim refuted: the key rejects or truncates responses |
| ΔSentBytes per call or the JFR allocation size falls as K falls (beyond ±5 %) | Claim refuted: usage follows the key |
| WARN count does not change with K | Knob not applied (wrong file, or NN not restarted); not confirmed |
| Positive control does not fail at a client cap of 1 MiB | The response is not as large as computed (workload did not reach the limit); not confirmed. Raise the entry count or name length. |
| No JFR events at all | Instrument gap (TLAB/humongous assumption wrong); rely on SentBytes and the WARN length; not a refutation |

**B3h. Controls.**
- The WARN lines prove which K was in force and that the target check ran on these exact calls. They print `response.length`, so they also give the measured operand.
- The client-side `ipc.maximum.response.length` run is the positive control: same workload, a cap that binds.
- The same namespace is reused for every K, so the response content is identical.
- 20 repetitions per K plus a repeat of K = 1024 rule out drift.
- `RpcProcessingTimeNumOps` deltas confirm the expected number of calls.
- No DataNode block traffic is involved: directories only.

**B4. Risks and cleanup.**
- **Unit tier:**
  - The test JVM uses up to about 100 MB beyond its baseline (16 MiB responses, doubled).
  - Ports are ephemeral (port 0).
  - Remove the added test file from the local copy afterwards. Never put it in the shared tree.
- **Cluster tier:**
  - Ports 29820, 29870, 29864, 29866 and 29867 must be free (`ss -ltn`).
  - Disk is less than 1 GB under `$RUN`. At K = 1024 the NN log may gain many WARN lines; check `du -sh $RUN/logs`.
  - The NN heap is 1 GB; make sure the host has at least 4 GB free.
- **Cleanup:**
  - `hdfs --daemon stop datanode; hdfs --daemon stop namenode`.
  - `jps` must show no `NameNode`/`DataNode`.
  - Kill any leftover `jcmd`/JFR recordings (they end with the JVM).
  - `rm -rf $RUN/nn $RUN/dn $RUN/tmp $RUN/pids` (keep `$RUN/logs`, the `.jfr` files and the readings).
  - Nothing is written outside `$RUN`.

## C. Sources read

```
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/Server.java (lines 255-266, 320, 345, 480-495, 1088-1110, 1172, 1300-1385, 1844-1880, 3320-3340, 3500-3665, 3795, 3915-3932)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/CommonConfigurationKeys.java (lines 55-92)
hadoop-common-project/hadoop-common/src/main/resources/core-default.xml (lines 2516-2522)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/ResponseBuffer.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/RpcWritable.java (lines 36-60)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/ProtobufRpcEngine2.java (lines 440, 613, 640)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/ProtobufRpcEngine.java (lines 408, 503)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/WritableRpcEngine.java (lines 158, 615)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/RPC.java (lines 200-230, 995)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/Client.java (lines 374, 409, 1415-1470, 1894-1942)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/ipc/metrics/RpcMetrics.java (lines 121, 256-257)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSUtil.java (lines 1398-1422)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (line 455)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirectory.java (lines 365-372)
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (dfs.ls.limit, lines 5113-5118)
hadoop-common-project/hadoop-common/src/site/markdown/release/0.21.0/RELEASENOTES.0.21.0.md (lines 1859-1863)
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/ipc/TestIPCServerResponder.java
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/ipc/TestRpcBase.java (lines 60-140, 367-392, 603)
hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/test/GenericTestUtils.java (line 479)
hadoop-common-project/hadoop-common/src/test/proto/test.proto (EchoRequestProto/EchoResponseProto)
https://issues.apache.org/jira/browse/HADOOP-6577 (cited via the in-tree release note)
```

## D. Stage-4 feedback

none yet
