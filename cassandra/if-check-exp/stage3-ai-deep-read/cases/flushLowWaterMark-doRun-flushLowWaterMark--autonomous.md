# flushLowWaterMark — verification solution  <!-- file: cases/flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/net/OutboundConnection.java:871` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.305, 2026-10-22 |
| Estimate | `negative`. The check at :871 is the *resume* threshold of a hysteresis pair. It decides when the event-loop delivery starts serializing again after a stall. It does not cap anything. The peak of the in-flight bytes it watches is set by the companion `flushHighWaterMark` check at :854 (plus at most one frame of overshoot). The value is also a hard-coded 32 KiB per connection that cannot be set by configuration. |
| Ground | `flushLowWaterMark` is compared only at :871, inside the write-completion listener, after `flushingBytes` has already been decremented. A lower or higher value only moves the point where `isWritable` flips back to `true`. It never stops `flushingBytes` from growing: the only stop is `flushingBytes >= flushHighWaterMark` at :854. So the peak Netty outbound-buffer occupancy, and the networking buffer-pool memory behind it, should be the same for any `flushLowWaterMark < flushHighWaterMark`. The bytes involved are also already counted against `internode_application_send_queue_capacity` and its reserves (`pendingBytes` includes in-flight bytes; capacity is released only at :866), so this pair is a sub-limit inside a cap that already exists. |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `flushLowWaterMark`, a `public final int` field of `OutboundConnectionSettings` (`src/java/org/apache/cassandra/net/OutboundConnectionSettings.java:87`, declared together with `flushHighWaterMark`).
- **Kind:** a hard-coded constant carried in a settings object. It is not a configuration entry, not a `-D` property and not a JMX attribute.
- **Value origin:** the only public constructors pass literals. `OutboundConnectionSettings(InetAddressAndPort to, InetAddressAndPort preferred)` calls the private constructor with `1 << 15, 1 << 16` (`OutboundConnectionSettings.java:101-104`; the literals are at :104 and land in parameters :117-118, assigned at :144-145). Every `with*` copier passes the field through unchanged (:167-321). So does `withDefaults(...)` (:467-480).
- **Unit:** bytes, compared against `flushingBytes`, which is measured in "canonical" message bytes (the size at the current messaging version, see `canonicalSize` use at :821, :851).
- **Default:** 32768 B (32 KiB) for the low mark, with high = 65536 B (64 KiB). It is the same for every connection type and every peer.
- **How it can be set:** not settable. `withNettyBufferBounds(WriteBufferWaterMark)` (:252-259) looks like it should set it but ignores its argument and copies the existing fields. Nothing in `Config.java`, `DatabaseDescriptor` or `CassandraRelevantProperties` refers to it. Production callers (`MessagingService.java:666`, `ReconnectableSnitchHelper.java:69`, `NettyStreamingConnectionFactory.java:91,100`) always go through the literal constructor. Changing it needs a source patch and a rebuild (or reflection inside a test JVM).

**A2. What it caps.**
- **Resource:** in principle off-heap memory. These are the serialized frame buffers that `EventLoopDelivery` has handed to Netty (`writeAndFlush`, `OutboundConnection.java:840`) and that have not yet been written to the socket. They are allocated from the networking `BufferPool` (`FrameEncoder.java:32` → `BufferPools.forNetworking()`, `BufferPools.java:44-45`) via `established.payloadAllocator.allocate(...)` (`OutboundConnection.java:782, 810`). They stay held by Netty's `ChannelOutboundBuffer` until the write completes.
- **Quantity compared:** `EventLoopDelivery.flushingBytes` (`OutboundConnection.java:741`). This is the sum of the canonical sizes of frames whose `writeAndFlush` did not complete synchronously and whose completion listener has not yet run.
- **What the low mark does:** it is the lower bound of the hysteresis band. The upper bound is `flushHighWaterMark`, checked at :854. The low mark only governs *when the delivery becomes writable again*, not how high the in-flight bytes can go.

**A3. Mechanism.**
1. `enqueue` acquires queue capacity for `canonicalSize` against the per-connection `pendingCapacityInBytes` and then the endpoint and global reserves (`OutboundConnection.java:335, 383-441`). The message goes into `queue`, and `delivery.execute()` is called (:348-349). `pendingBytes` therefore covers both queued and in-flight bytes (comment at :120-123).
2. `EventLoopDelivery.doRun` (:757). If `!isWritable`, it returns at once (:759-760). Otherwise it builds one frame of at most `maxSendBytes = min(pendingBytes - flushingBytes, LARGE_MESSAGE_THRESHOLD)` (:766). `LARGE_MESSAGE_THRESHOLD` is 64 KiB minus the frame header (`OutboundConnections.java:69-70`; property `cassandra.otcp_large_message_threshold`, default 65536, `CassandraRelevantProperties.java:388`). It drains messages from the queue into that frame (:786-834) and calls `writeAndFlush` (:840).
3. If the write completed synchronously (socket had room), the frame is counted as sent and `canonicalSize` is released in `finally` (:843-848, :902-903). `flushingBytes` is not touched.
4. If not, `flushingBytes += canonicalSize` (:851). **High check** (:854): if `flushingBytes >= flushHighWaterMark`, then `isWritable = false` and `promiseToExecuteLater()` (:855-859). From then on `doRun` exits at :759, so no further frames are handed to Netty. Messages pile up in the application queue, which is bounded by the send-queue capacity and its reserves. They are not pulled into Netty.
5. In the completion listener (:864-891): `releaseCapacity(...)` (:866), then `flushingBytes -= releaseBytesFinal` (:867). **Target check** (:871): `if (!isWritable && flushingBytes <= settings.flushLowWaterMark)`, set `isWritable = true` and call `executeAgain()` (:872-875). This is the resume step.
6. `finally` re-schedules delivery while `pendingBytes() > flushingBytes && isWritable` (:908-909).

Outcome of :871:
- **True:** delivery resumes and can push `flushingBytes` back up to the high mark.
- **False:** delivery stays paused until a later completion brings `flushingBytes` down to the low mark. Nothing is dropped and nothing is rejected.

Overshoot and bypasses:
- `flushingBytes` can exceed the high mark by up to one frame. The check at :854 runs *after* adding the frame, so the overshoot is up to `LARGE_MESSAGE_THRESHOLD` bytes, or one single message larger than that, which gets its own buffer at :810 (bounded by `internode_max_message_size`, :793).
- Synchronously completed writes never enter `flushingBytes` (:843).
- `LargeMessageDelivery` (large-messages connection) ignores these fields. It uses Netty's channel `WriteBufferWaterMark` instead, inside `AsyncMessageOutputPlus` (`AsyncMessageOutputPlus.java:69-71`).
- Kernel socket buffers (SO_SNDBUF on the sender, SO_RCVBUF on the receiver) hold bytes that have already "completed" from Netty's point of view.

**A4. Other consumers.**
- The application send queue: messages waiting in `OutboundMessageQueue` (heap objects), bounded by `internode_application_send_queue_capacity` (4 MiB per link), `..._reserve_endpoint_capacity` (128 MiB) and `..._reserve_global_capacity` (512 MiB) (`Config.java:250-254`; `cassandra.yaml` comment at lines 1370-1391). In-flight bytes are inside this accounting.
- The large-messages link (`LargeMessageDelivery`, Netty's default watermark of 32 KiB/64 KiB, see Netty docs).
- Inbound frame buffers and CQL native-transport frames, which share the networking `BufferPool`.
- Kernel TCP buffers (`internode_socket_send_buffer_size` / `internode_socket_receive_buffer_size`, `Config.java:243, 246`; applied at `OutboundConnectionInitiator.java:200-201` and `InboundConnectionInitiator.java:175`).
- Streaming connections (`AsyncStreamingOutputPlus.java:66`).

**A5. Evidence beyond the source.**
- CASSANDRA-15066, the internode messaging rewrite in 4.0 that introduced `OutboundConnection` / `EventLoopDelivery`: https://issues.apache.org/jira/browse/CASSANDRA-15066
- Netty `WriteBufferWaterMark` (defaults 32 KiB low / 64 KiB high, the same pattern): https://netty.io/4.1/api/io/netty/channel/WriteBufferWaterMark.html
- In-tree tests: no test under `test/` refers to `flushLowWaterMark` or `flushHighWaterMark` (grep is empty). The harness patterns reused below come from `test/unit/org/apache/cassandra/net/ConnectionTest.java:230-260` and `ProxyHandlerConnectionsTest.java:355-389`.
- Git history: the local clone is shallow at the tag (a single commit), so it gives no history for these lines.

## B. Verification solution

**B1. Claim under test.**
For an event-loop (small or urgent) outbound connection whose peer has stopped reading, the peak bytes held in Netty for that connection (`flushingBytes`, Netty's `totalPendingWriteBytes`, and the networking `BufferPool` used size) do **not** follow `flushLowWaterMark`. For every low mark below the high mark, the peak stays in `[flushHighWaterMark, flushHighWaterMark + one frame (≤ 64 KiB))`. Changing `flushHighWaterMark` with the same workload moves the peak proportionally (positive control). The low mark only shifts the resume point (`flushingBytes` at the false→true flip of `isWritable` is ≤ `flushLowWaterMark`).

The claim is wrong if the stalled peak changes with `flushLowWaterMark` by more than one frame (65536 B) while the high mark is fixed.

### B2. Unit tier

**B2a. Environment and build.**
- **Clone and build:** JDK 11.0.32.1, Ant 1.10.12. Clone the tag to local disk, never to the shared tree:
  ```
  mkdir -p /tmp/fwm && cd /tmp/fwm
  <repo>/cassandra/if-check-exp/stage4-runtime-verification/copy-source.sh c509
  cd c509 && ant -Dno-checkstyle=true jar build-test
  ```
- **Test source:** a new file in the local clone only, `/tmp/fwm/c509/test/unit/org/apache/cassandra/net/FlushWaterMarkProbeTest.java`. It must be in package `org.apache.cassandra.net` to reach the package-private `OutboundConnection` constructor and `OutboundDebugCallbacks`. Run it with
  ```
  ant -Dno-checkstyle=true testsome -Dtest.name=org.apache.cassandra.net.FlushWaterMarkProbeTest
  ```
  This uses the default test JVM options from `build.xml` and `test/conf/cassandra.yaml`.
- **Results:** the test writes CSV to `/tmp/fwm/results/unit.csv`.
- **Amendment 2026-10-22 (stage-4 audit, A1 — environment and command; B2f/B2g unaffected):** the run uses `pc13:~/cassandra-flw` (cloned from `~/cassandra-run1` at `cassandra-5.0.9`, `b5f2a54`, built with `ant build-test`) in place of `/tmp/fwm/c509`, and `pc13:~/stage4-logs/flw/unit/` in place of `/tmp/fwm/results`. The `testsome` command gets `-Dtest.timeout=1800000`: 24 configurations with up to 18 MiB each, a 2 s stability wait and a throttled drain can exceed `build.xml`'s default 480 s. The CSV path is passed as `-Dstage4.csv=<file>`. The decision between the TCP proxy and the pipeline-pause fallback (end of B2d) is made in stage-4 step 1 by a handshake check (connect through the proxy, deliver one message), after this file is frozen and before any reading.

**B2b. Knobs.**
Neither mark is settable, so the test sets the two `final int` fields reflectively on the `OutboundConnectionSettings` instance *before* passing it to `new OutboundConnection(...)`. On JDK 11, `Field.setAccessible(true)` + `setInt` works on non-static final fields. `withDefaults` in the constructor (`OutboundConnection.java:308`) copies the patched values into `template`, and `Established.settings` comes from `template` (:1212, :1128). The test asserts this by reading back `((OutboundConnectionSettings) get(outbound,"template")).flushLowWaterMark`.

| Run set | flushHighWaterMark (H) | flushLowWaterMark (L) | Why |
|---|---|---|---|
| S0 stock | 65536 (no reflection) | 32768 (no reflection) | shipped behaviour |
| L-set (claim) | 1048576 | 1024; 32768; 524288; 1040384 | sweep L across almost the whole [0, H) range with H fixed, large enough that one-frame overshoot (≤64 KiB) is small relative to H |
| P-set (positive control) | 65536; 1048576; 8388608 | H/2 | the same workload where the known stop (:854) binds |

Run each configuration 3 times (fresh connection each time).

**B2c. Workload.**
- **Payload:** override the `Verb._TEST_1` serializer (`verb.unsafeSetSerializer`, as `ProxyHandlerConnectionsTest` does) with a payload of 128 longs = 1024 B. Each message is then about 1.05 KiB canonical.
- **Expiry:** override expiration to 10 minutes with `unsafeSetExpiration(Verb._TEST_1, u -> u.convert(10, MINUTES))` so nothing expires while stalled.
- **Connection type:** `ConnectionType.SMALL_MESSAGES`, which uses `EventLoopDelivery`. Framing is forced to `Framing.CRC` so the on-wire size equals the canonical size (no LZ4).
- **Queue capacity:** `withApplicationSendQueueCapacityInBytes(64 << 20)`, so the queue can hold far more than H.
- **Backpressure:** an in-test TCP proxy between outbound and inbound (`PausableProxy`, code below). While `paused`, it stops reading from the outbound side. Its accepted socket has SO_RCVBUF = 4096 and the outbound has `withSocketSendBufferSizeInBytes(4096)`. Kernel buffering therefore stays in the tens of KiB at most, after which Netty writes stop completing and `flushingBytes` grows.
- **Volume per run:** enqueue `E = 2*H + 2 MiB` of messages, i.e. `ceil(E / 1024)` messages: 2176 for H=64 KiB, 4096 for 1 MiB, 18432 for 8 MiB. Since `E > H + 64 KiB + kernel buffers`, the high mark is necessarily reached.
- **Resume phase:** the proxy is unpaused with a throttle of one 4 KiB read per 1 ms (≈ 4 MB/s). This makes completions arrive frame by frame, so the :871 transitions happen many times.

**B2d. Observables and instruments.**
All in-JVM, via reflection on the outbound's event loop, so reads are consistent with the single-threaded writer.
- `S` (stalled in-flight bytes): `OutboundConnection.delivery` → `EventLoopDelivery.flushingBytes`, plus `isWritable`. Read via `eventLoop.submit(callable).get()`. Sample every 10 ms during the stall. The stall is "stable" when the value is unchanged for 2 s and `isWritable == false`. S is the stable value, which is also the peak, since nothing completes while paused.
- `N` (Netty bytes actually held): `((Established) state).channel.unsafe().outboundBuffer().totalPendingWriteBytes()`, read on the event loop at the stable point.
- `U` (pool memory): `BufferPools.forNetworking().usedSizeInBytes()` (the same gauge as JMX `BufferPool/networking/UsedSize`, `BufferPoolMetrics.java:62`). Take the median of 20 samples just before pausing, then at the stable point; `U = stable − before`.
- `P`: `outbound.pendingBytes()` at the stable point. It must be > S, which shows the queue still had work and the high mark is what stopped delivery.
- `R` (resume levels): a custom `OutboundDebugCallbacks` passed via `withDebugCallbacks`. Its `onSentSmallFrame` runs inside the listener *after* :867-875 (it is called at :881). On each call it reads `isWritable` and `flushingBytes` reflectively. If the previous callback saw `isWritable == false` and this one sees `true`, it records `R = flushingBytes`, which is exactly the value that passed the :871 test.
- **Not observable directly:** kernel socket memory (out of scope here), and heap of queued `Message` objects (bounded by send-queue capacity, not by this constraint).
- **Amendment 2026-10-22 (stage-4 audit, A2 — the R instrument; B2f/B2g unaffected):** the rule above ("previous callback saw `false`, this one sees `true`") misses a flip that happens in the *first* listener after a stall, because the stall (`:857`) is set in `doRun`, where no callback runs after it. That is every flip whenever `H − L` is less than one frame (S0's 32 KiB band against 64 KiB frames; L = 1040384 against H = 1 MiB), so the rule would record no R for exactly the runs B2f's manipulation check needs. The instrument is therefore: on every `onSendSmallFrame` read `flushingBytes` (f0) and `isWritable` (must be `true`); on every `onSentSmallFrame` decide from the call stack whether it is the listener (`lambda$doRun…`) or the synchronous path (`:847`); for a listener, the level before it is `f_now + bytes` (CRC framing, one messaging version: `bytes` = the canonical size), and `isWritable` before it is the value after the previous listener, or, if an asynchronous send happened since, `f0 + bytes < H` for the last such send (the code's own `:854` test). A flip is a listener with `isWritable` false before and `true` after; R = `flushingBytes` after it. Each run also records: *resume-send levels* (f0 of the first send after each flip; ≤ R), the number of flips, the number of listeners that left `isWritable` false with `flushingBytes ≤ L` (should be 0: the guard did not fire when it should have), the number that inferred `true` before but found `false` after (should be 0: an inference error), and the peak pre-listener level. These are the R and manipulation readings of B2f/B2g; nothing else changes.

Probe skeleton (complete enough to type in; imports as in `ProxyHandlerConnectionsTest`, plus `java.net.*`, `java.io.*`, `java.lang.reflect.Field`, `java.nio.file.*`, `java.util.*`, `java.util.concurrent.*`, `org.apache.cassandra.utils.memory.BufferPools`, `io.netty.channel.Channel`):
```java
package org.apache.cassandra.net;
public class FlushWaterMarkProbeTest {
  static final SocketFactory factory = new SocketFactory();
  @BeforeClass public static void up() { DatabaseDescriptor.daemonInitialization(); CommitLog.instance.start(); }
  @AfterClass public static void down() throws Exception { factory.shutdownNow(); }

  static Object get(Object o, String f) throws Exception { Class<?> c=o.getClass(); while(true){ try{ Field x=c.getDeclaredField(f); x.setAccessible(true); return x.get(o);}catch(NoSuchFieldException e){ c=c.getSuperclass(); if(c==null) throw e; } } }
  static void setInt(Object o, String f, int v) throws Exception { Field x=OutboundConnectionSettings.class.getDeclaredField(f); x.setAccessible(true); x.setInt(o, v); }

  static final class PausableProxy implements Closeable {
    final ServerSocket server = new ServerSocket(); final InetSocketAddress target;
    volatile boolean paused; volatile int sleepMsPerChunk; final ExecutorService ex = Executors.newCachedThreadPool(); final List<Socket> socks = new CopyOnWriteArrayList<>();
    PausableProxy(InetSocketAddress target) throws IOException { this.target=target; server.setReceiveBufferSize(4096); server.bind(new InetSocketAddress("127.0.0.1",0)); ex.submit(this::accept); }
    int port(){ return server.getLocalPort(); }
    void accept(){ try { while(!server.isClosed()){ Socket a=server.accept(); Socket b=new Socket(); b.connect(target); socks.add(a); socks.add(b);
        ex.submit(() -> pump(a,b,true)); ex.submit(() -> pump(b,a,false)); } } catch(IOException ignore){} }
    void pump(Socket from, Socket to, boolean fwd){ byte[] buf=new byte[4096]; try { InputStream in=from.getInputStream(); OutputStream out=to.getOutputStream();
        while(true){ if(fwd) while(paused) Thread.sleep(1); int n=in.read(buf); if(n<0) break; out.write(buf,0,n); out.flush(); if(fwd && sleepMsPerChunk>0) Thread.sleep(sleepMsPerChunk);} } catch(Exception ignore){} }
    public void close() throws IOException { server.close(); for(Socket s:socks) s.close(); ex.shutdownNow(); }
  }

  static final class Resume implements OutboundDebugCallbacks {
    volatile Object delivery; boolean prevWritable = true; final List<Integer> levels = new ArrayList<>();
    public void onSendSmallFrame(int c,int b){}
    public void onSentSmallFrame(int c,int b){ try { boolean w=(Boolean)get(delivery,"isWritable"); int f=(Integer)get(delivery,"flushingBytes");
        if(!prevWritable && w) levels.add(f); prevWritable=w; } catch(Exception e){ throw new RuntimeException(e);} }
    public void onFailedSmallFrame(int c,int b){}
    public void onConnect(int v, OutboundConnectionSettings s){}
  }

  void runOne(String set, int H, int L, boolean reflect, int rep) throws Throwable {
    // serializer: Long payload written 128 times (1024 B); handler counts arrivals; expiration 10 min (restore in finally)
    InetAddressAndPort ep = FBUtilities.getBroadcastAddressAndPort();
    InboundSockets inbound = new InboundSockets(Collections.singletonList(new InboundConnectionSettings().withBindAddress(ep).withSocketFactory(factory)));
    inbound.open().sync();
    PausableProxy proxy = new PausableProxy(new InetSocketAddress(ep.getAddress(), ep.getPort()));
    Resume cb = new Resume();
    OutboundConnectionSettings s = new OutboundConnectionSettings(ep)
        .withConnectTo(InetAddressAndPort.getByAddressOverrideDefaults(InetAddress.getByName("127.0.0.1"), proxy.port()))
        .withFraming(OutboundConnectionSettings.Framing.CRC).withSocketSendBufferSizeInBytes(4096)
        .withApplicationSendQueueCapacityInBytes(64 << 20).withDefaultReserveLimits()
        .withSocketFactory(factory).withDebugCallbacks(cb);
    if (reflect) { setInt(s,"flushHighWaterMark",H); setInt(s,"flushLowWaterMark",L); }
    ResourceLimits.EndpointAndGlobal reserve = new ResourceLimits.EndpointAndGlobal(new ResourceLimits.Concurrent(s.applicationSendQueueReserveEndpointCapacityInBytes), s.applicationSendQueueReserveGlobalCapacityInBytes);
    OutboundConnection out = new OutboundConnection(ConnectionType.SMALL_MESSAGES, s, reserve);
    // assert template carries H/L; cb.delivery = get(out,"delivery");
    // 1 connect: enqueue one message, wait for the handler (10 s)
    // 2 baseline U0 = median of 20 BufferPools.forNetworking().usedSizeInBytes() samples
    // 3 proxy.paused = true; sleep 200 ms
    // 4 enqueue ceil((2*H + (2<<20))/1024) messages
    // 5 every 10 ms on the event loop read (flushingBytes,isWritable); stable = unchanged 2 s && !isWritable (timeout 60 s => record "never stalled")
    // 6 record S, N=outboundBuffer().totalPendingWriteBytes(), U=usedSize-U0, P=out.pendingBytes()
    // 7 proxy.sleepMsPerChunk = 1; proxy.paused = false; wait until handler count == all messages (timeout 120 s)
    // 8 write CSV row: set,H,L,rep,S,N,U,P,count(R),max(R),median(R)
    // finally: out.close(false).get(30,SECONDS); proxy.close(); inbound.close().get(30,SECONDS); restore verb overrides
  }

  @Test public void sweep() throws Throwable {
    for (int rep=0; rep<3; rep++) {
      runOne("S0",65536,32768,false,rep);
      for (int L : new int[]{1024,32768,524288,1040384}) runOne("L",1048576,L,true,rep);
      for (int H : new int[]{65536,1048576,8388608}) runOne("P",H,H/2,true,rep);
    }
  }
}
```
If the handshake does not go through the TCP proxy, use the fallback: `inbound.open(pipeline -> pipeline.addFirst("pause", new ChannelDuplexHandler(){ public void read(ChannelHandlerContext c){ if(!paused) c.read(); else pendingRead=true; } }))` plus `channel.config().setAutoRead(false)` while paused, with `withConnectTo(ep)`. On resume, flip `paused` and call `c.read()` if a read is pending.

**B2e. Procedure.**
1. Clone and build as in B2a. Create `/tmp/fwm/results`.
2. Write `FlushWaterMarkProbeTest.java` into the local clone and run `ant -Dno-checkstyle=true build-test`.
3. Run `ant -Dno-checkstyle=true testsome -Dtest.name=org.apache.cassandra.net.FlushWaterMarkProbeTest 2>&1 | tee /tmp/fwm/results/unit.log`.
4. Copy `/tmp/fwm/results/unit.csv` and `build/test/output/TEST-org.apache.cassandra.net.FlushWaterMarkProbeTest.xml`.
5. Check `pgrep -f FlushWaterMarkProbeTest` is empty and `ss -ltnp | grep java` shows nothing left by the test.

**B2f. Predictions** (stated before any run).
- **S0 (stock):** 65536 ≤ S < 131072. N ∈ [S, S + 4096] (CRC header 6 B + trailer 4 B per frame). U ∈ [S, S + 262144]. P > S. R values all ≤ 32768.
- **L-set (H = 1 MiB):**
  - For each L: 1048576 ≤ S < 1114112.
  - Across the four L values (spread 1,039,360 B), `max(S) − min(S) < 65536`. The same holds for N and, within 256 KiB, for U.
  - No monotone trend of S with L.
- **L-set, manipulation check:** every R ≤ L for that run. Median R for L=1040384 > 524288. Max R for L=1024 ≤ 1024.
- **P-set (positive control):** S ∈ [H, H + 65536) for H = 64 KiB, 1 MiB, 8 MiB. So S(8 MiB) / S(64 KiB) ≥ 64. N and U follow H the same way.
- **What would show the claim wrong:** S (or N or U) differing across the L-set by ≥ 65536 B in a direction that follows L, or S < H for some L.
- **Amendment 2026-10-22 (stage-4 audit, A3 — how the L-set relations are judged; stated before any reading):**
  - *Spread* is max − min over all 12 L-set runs (4 values × 3 repetitions). A *trend* is judged on the per-L medians of the 3 repetitions: "follows L" means the four medians are monotone in L **and** max − min ≥ 65536 B for S and N, ≥ 262144 B for U (U's stated tolerance). An ordering within those amounts is noise, not a trend, so "no monotone trend" above is met whenever the spread is below them.
  - N is predicted from the Netty accounting as `S + k·(10 + 96)` for k pending frames (CRC header and trailer, plus Netty's per-entry overhead), so N ∈ [S, S + 4096] for S0 and N − S < 65536 for every run.
  - "N and U follow H the same way" (P-set) means: in every P-set run, N ∈ [S, S + 65536) and U ∈ [S, S + 262144], so both track H within those bounds at H = 64 KiB, 1 MiB and 8 MiB.
  - S0's numbers are a baseline; they are checked and reported, but they are not part of the B2g row 1 test.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| L-set S all in [H, H+64 KiB), spread < 64 KiB; P-set S tracks H; R ≤ L | Claim confirmed: usage is flat in the low mark while the positive control moves; the knob took effect (R) but does not cap |
| L-set S (or N, U) rises or falls with L by ≥ 64 KiB | Claim refuted: usage follows `flushLowWaterMark` |
| S < H in some L-set run with P > S | Delivery stalled below the high mark for another reason (e.g. queue lock, kernel); not confirmed, investigate |
| Never stalled (`isWritable` stays true, S ≈ 0) | Backpressure not created (proxy not in path or kernel absorbed everything); limit never reached, so not confirmed. Use the pipeline-pause fallback |
| P-set S does not track H | Positive control failed (reflection not effective or wrong delivery type); not confirmed |
| Template read-back ≠ H/L set | Knob not applied; run invalid |
| R values > L | The :871 check does not behave as traced; the mechanism claim is wrong (report it) |
| N ≫ S (e.g. > S + 64 KiB) | Netty holds bytes outside `flushingBytes` accounting (e.g. sync frames queued behind); note it, since usage then exceeds the traced bound regardless of L |

**Amendment 2026-10-22 (stage-4 audit, A4 — verdict words and missing rows; stated before any reading).** The rows above map to verdicts as follows, applied in this order (the first that applies is the tier's verdict):
1. *Template read-back ≠ H/L set*, or **(new)** any run with a connection reset, a failed frame (`onFailedSmallFrame`), or fewer messages handled than enqueued by the resume timeout → **Invalid** (the tier).
2. *Never stalled* → **Not confirmed** (limit never reached). *P-set S does not track H* → **Not confirmed** (positive control failed). *S < H in some L-set run with P > S* → **Not confirmed**.
3. *L-set S (or N, U) rises or falls with L* → **Refuted — usage follows the low mark (Effect: caps)**, judged as in A3 (per-L medians monotone in L with max − min ≥ 65536 B for S or N, ≥ 262144 B for U).
4. *R values > L*, **(new)** any listener that left `isWritable` false with `flushingBytes ≤ L`, any inference error (A2), or **(new)** an L-set or P-set S ≥ H + 65536 → **Not confirmed (mechanism differs from A3; report it)**: the manipulation check failed, so "flat" cannot be credited to a knob that acted as traced.
5. **(new)** S and N meet row 1, but U's spread over the L-set is ≥ 262144 B without following L → **Not confirmed** (the real-resource measure is too noisy to show flatness; the counter alone is flat).
6. *L-set S in [H, H + 64 KiB) with spread < 64 KiB, P-set S tracking H (B2f: S ∈ [H, H + 65536) at each H, ratio ≥ 64), R ≤ L with the manipulation values of B2f (median R for L = 1040384 > 524288)*, and N and U meeting B2f → **Confirmed — does not cap**.
7. **(new)** Anything else (e.g. row 6 met except a B2f N bound, or no R recorded for some L) → **Not confirmed (no matching row)**, Effect undetermined.
The *N ≫ S* row is a note added to whichever verdict applies; if N follows L it is row 3. A missed S0 baseline number (A3) is reported as a missed sub-prediction and does not change the row.

**B2h. Controls.**
- **S0** gives the shipped baseline without reflection.
- **P-set** is the positive control on the same workload.
- **Template read-back** confirms the knob was applied.
- **R levels** confirm the low mark actually changed behaviour, so "flat" is not because the knob was ignored.
- **`P > S`** shows the queue held more than H, so the stop came from :854, not from running out of work.
- **CRC framing** removes compression effects.
- **The 10-minute expiration** removes expiry drops.
- **Fresh connection and proxy per run, and 3 repetitions,** guard against carry-over and noise.
- **`U` measured as a delta** around the pause removes pool warm-up.

### B3. Cluster tier

Stock configuration cannot vary `flushLowWaterMark` (A1). So this tier runs **patched builds** in the private local clone. Only the literal at `OutboundConnectionSettings.java:104` is changed. Everything else is the stock 5.0.9 build. This is a stated deviation from "configuration only". Without it, the cluster tier can only run the stock value (variant V0) and cannot sweep the knob.

**B3a. Environment and build.**
- **Nodes:** one Linux host, two nodes on loopback: A = 127.0.0.1 (sender, measured) and B = 127.0.0.2 (receiver, frozen). Two separate hosts also work.
- **Source and builds:** `/tmp/fwm/c509` from B2a. Make one source copy per variant, each built with `ant -Dno-checkstyle=true jar`:
  ```
  for v in V0 V1 V2 V3 V4; do cp -a /tmp/fwm/c509 /tmp/fwm/$v; done
  # V0: stock (no change)
  sed -i '104s/1 << 15, 1 << 16/1 << 10, 1 << 26/'            /tmp/fwm/V1/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java
  sed -i '104s/1 << 15, 1 << 16/1 << 25, 1 << 26/'            /tmp/fwm/V2/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java
  sed -i '104s/1 << 15, 1 << 16/(1 << 26) - (1 << 20), 1 << 26/' /tmp/fwm/V3/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java
  sed -i '104s/1 << 15, 1 << 16/1 << 21, 1 << 22/'            /tmp/fwm/V4/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java
  for v in V0 V1 V2 V3 V4; do (cd /tmp/fwm/$v && grep -n 'null, null, null, null, null, null, null' src/java/org/apache/cassandra/net/OutboundConnectionSettings.java && ant -Dno-checkstyle=true jar); done
  ```
  The `grep` must show the patched literals on line 104 before each build.
- **Per-node config:** copy `conf/` to `/tmp/fwm/confA` and `/tmp/fwm/confB` and edit `cassandra.yaml`:
  - `cluster_name: fwm`
  - `listen_address` / `rpc_address`: 127.0.0.1 for A, 127.0.0.2 for B
  - `seed_provider ... seeds: "127.0.0.1:7000"`
  - `data_file_directories: [/tmp/fwm/dataX/data]`, `commitlog_directory: /tmp/fwm/dataX/cl`, `saved_caches_directory: /tmp/fwm/dataX/caches`, `hints_directory: /tmp/fwm/dataX/hints`
  - `hinted_handoff_enabled: false`
  - `internode_compression: none`
  - `internode_socket_send_buffer_size: 4KiB` (A)
  - `internode_socket_receive_buffer_size: 4KiB` (B)
  - **Amendment 2026-10-22 (stage-4 runbook defect 1, found in the step-1 shakedown before any counted cluster reading; B3f/B3g unchanged):** the two 4 KiB socket-buffer lines are **dropped** (both nodes keep the default, 0 = kernel autotuning). With them, A's small link to B drained about 17 KB/s under load (`internode_outbound.sent_bytes` +33.5 KB per 2 s, 400k expiries in 20 s, Small `PendingBytes` held at ≈ 84.7 MB) *before any freeze*: B's 4 KiB receive window throttles the sender to zero-window probing. Then the link is saturated before the freeze, `flushingBytes` would sit at H in the pre window too, and D (plateau − pre) could not show H. With the defaults (shakedown `diag1`, the same stress, no freeze) Small `PendingBytes` stayed ≤ 4.2 KB and `UsedSize` ≤ 8 KB. The kernel buffers then hold a few MB more during the freeze; those bytes have left the pool, so D is unaffected, and H is still reached within about a second (B3c arithmetic).
  - `internode_tcp_user_timeout: 0ms` (keeps the stalled connection open)
  - `phi_convict_threshold: 16`
  - `num_tokens: 16`
  - `concurrent_compactors: 2`
- **JVM and ports:** `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`, JMX ports 7199 (A) and 7299 (B) via `JMX_PORT` in `cassandra-env.sh`, `LOCAL_JMX=yes`.
- **Starting a node:** `CASSANDRA_CONF=/tmp/fwm/confA /tmp/fwm/$v/bin/cassandra -p /tmp/fwm/A.pid` (B likewise, after A is up).
- **Amendment 2026-10-22 (stage-4 audit, A5 — environment; B3f/B3g unaffected):** on `pc13`, V0 is the unit tier's clone `~/cassandra-flw` (stock; the unit test file is removed from it before the cluster tier) and V1–V4 are copies `~/cassandra-flw-p1` … `-p4` of it after `ant build-test`. In each copy the line-104 `sed` is applied, `build/classes/main/org/apache/cassandra/net/OutboundConnectionSettings*.class` is deleted (Ant compares 1 s timestamps, so a copied class file can hide the edit), and `ant jar </dev/null` is run; the B3h `javap -c` check is made on the built class. Node data, commit log, hints and caches go on a 40 GiB tmpfs `~/stage4-flw/nodes/{A,B}` (`pc13`'s disk is a spinning volume; tmpfs keeps flush stalls out of the 500 ms samples); each node's `conf/` is rebuilt per lifetime under `~/stage4-flw/{A,B}/conf` from the variant's tree, with B3a's lines plus `auto_bootstrap: false` on B (an empty ring, nothing to stream), `JMX_PORT` set in that copy's `cassandra-env.sh`, `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`, and `ulimit -n 100000`. Daemons are matched by `java` + `CassandraDaemon` + working directory = the variant tree (their command lines show only `bin/../`).

**B3b. Knobs.**

| Variant | H (flushHighWaterMark) | L (flushLowWaterMark) | Role |
|---|---|---|---|
| V0 | 64 KiB | 32 KiB | stock |
| V1 | 64 MiB | 1 KiB | claim (L low) |
| V2 | 64 MiB | 32 MiB | claim (L mid) |
| V3 | 64 MiB | 63 MiB | claim (L high) |
| V4 | 4 MiB | 2 MiB | positive control (H moved, compare with V2) |

The large H makes the per-connection effect (tens of MiB) visible above node-level noise in the networking pool. The cap is set by build, and each change needs a restart on a new build.

**B3c. Workload.**
- **Schema:** cassandra-stress (`tools/bin/cassandra-stress` in the variant tree) against A only, RF = 2, so every write is replicated A→B over the small-messages link (mutation ≈ 2.2 KiB < 64 KiB threshold).
- **Command:**
  ```
  /tmp/fwm/$v/tools/bin/cassandra-stress write n=400000 cl=ONE no-warmup \
    -schema "replication(strategy=SimpleStrategy,factor=2)" keyspace=fwm \
    -col "size=FIXED(2048)" "n=FIXED(1)" -rate threads=64 \
    -node whitelist 127.0.0.1 -mode native cql3
  ```
- **Arithmetic:** reaching 64 MiB + 64 KiB in flight needs about 30,000 mutations. With CL=ONE, A acknowledges locally while B is frozen. At even 5,000 writes/s that takes ~6 s, well inside the ~20-40 s before A convicts B at phi 16. A's send-queue capacity of 4 MiB + 128 MiB endpoint reserve (≈ 132 MiB) exceeds 64 MiB, so the queue does not overflow first.
- **Duration:** ~60 s of stress per run. B is frozen for 25 s in the middle.
- **Disk:** about 400k × 2 KiB × 2 nodes ≈ 1.6 GB plus commitlog, all on `/tmp`.
- **Amendment 2026-10-22 (stage-4 audit, A6 — the stress command; B3f/B3g unaffected):** `n=400000` unthrottled can finish before the freeze at t = 15 s (two nodes on 40 cores take well over 30,000 writes/s), which would leave nothing to fill the link. The command is therefore `write duration=60s cl=ONE no-warmup … -rate threads=64 fixed=20000/s …` with the same schema, columns, node and mode. At 20,000 × ~2.2 KiB ≈ 44 MB/s, 64 MiB + 64 KiB is in flight about 1.5 s after the freeze, and the stress client still runs through the whole 25 s freeze. Data per lifetime ≈ 1.2 M rows × 2.2 KiB × 2 nodes ≈ 5.3 GB, on the tmpfs (A5), wiped per lifetime.

**B3d. Observables and instruments.**
- **Main measure, on A:** networking pool used bytes, JMX `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize` (`BufferPoolMetrics.java:62`; includes overflow). Sample every 500 ms:
  ```
  while true; do echo "$(date +%s.%N),$(/tmp/fwm/$v/bin/nodetool -h 127.0.0.1 -p 7199 sjk mx -b 'org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize' -mg -f Value | tail -1)"; sleep 0.5; done > /tmp/fwm/results/$v-used.csv &
  ```
- **Secondary, on A:** JVM direct memory `java.nio:type=BufferPool,name=direct` attribute `MemoryUsed` (same sjk command, sampled every 500 ms into `$v-direct.csv`).
- **Queue level, on A:** `cqlsh 127.0.0.1 -e "select peer_address, pending_bytes, using_reserve_bytes from system_views.internode_outbound"` every 2 s (`InternodeOutboundTable.java:119-122`). This shows the queue exceeded H, i.e. there was work beyond the cap.
- **Kernel, on A, for the record:** `ss -tmn dst 127.0.0.2:7000` every 2 s (Send-Q, skmem).
- **Derived:** D = median(UsedSize over the 5 s plateau while B frozen) − median(UsedSize over the 10 s before freezing, under load).
- **Not observable directly:** `flushingBytes` per connection. D is the sum over A's connections to B (the urgent link carries gossip, which is small) plus noise from CQL frames.
- **Amendment 2026-10-22 (stage-4 audit, A7 — sampler and windows; stated before any reading):** `nodetool sjk mx` starts a JVM per call and cannot sample every 500 ms. One persistent JMX client on A (`Jmx.java poll`, reused from the closed `internode_application_send_queue_capacity-releaseCapacity…--autonomous` harness) samples every 500 ms: networking `UsedSize`, direct `MemoryUsed`, `Connection,scope=127.0.0.2_7000` Small and Urgent `PendingBytes`, and heap used. `system_views.internode_outbound` (with `active_connections`) and `ss -tmn` are sampled every 2 s. The times are fixed relative to the freeze (`pause`, the SIGSTOP time): **pre window** = [pause − 11 s, pause − 1 s], **plateau window** = [pause + 10 s, pause + 22 s] (replacing "flat for 5 s"). D = median(UsedSize, plateau window) − median(UsedSize, pre window); D_direct likewise. A variant's D is the mean of its two lifetimes; each lifetime's D is also reported.
- **Amendment 2026-10-22 (stage-4 audit, A8 — direct observation of the two checks on A; stated before any reading):** node A runs with a Byteman agent (`-javaagent:…byteman-4.0.20.jar=script:flw.btm`, no listener; output by `traceOpen` to a file, since the daemon closes stdout) with two observation rules on `OutboundConnection$EventLoopDelivery.doRun`: **STALL** at line 857 (`isWritable = false`) prints the epoch ms, the link type and peer, `flushingBytes`, and `settings.flushHighWaterMark` and `settings.flushLowWaterMark` read from the running connection, and flags the delivery; **RESUME** at method entry, if the delivery is flagged and `isWritable` is true, prints `flushingBytes` (the level at the first delivery run after the `:871` flip, which is ≤ the flip level) and clears the flag. Line 857 and the method are unchanged by the line-104 patch. This is the knob read-back in the running JVM and the per-link reading that D cannot give.
- **Amendment 2026-10-22 (stage-4 runbook defect 2, found in the step-1 shakedown before any counted cluster reading; B3f/B3g unchanged):** the STALL rule is placed `AFTER INVOKE promiseToExecuteLater` in `doRun` instead of `AT LINE 857`. That call (`:858`) is the only one in `doRun` (bytecode offset 641), inside the same `if (hasOverflowed)` branch and right after `isWritable = false`. Byteman's `AT LINE n` injects at the first bytecode whose line is ≥ n. In `doRun` that is an inlined copy of the `finally` block (line 902 at offset 104, on an early-return path), so the first shakedown printed STALL levels of 0 and of one frame, below H. Checked with the fixed rule (`diag3`, V0 with a freeze): 25 STALL lines, levels 67,552–130,882 B, all in [H, H + 65536), (H, L) = (65536, 32768), and every RESUME level 0 ≤ L.

**B3e. Procedure** (per variant v ∈ V0…V4, 2 repetitions each; fresh data dirs per run).
1. `rm -rf /tmp/fwm/dataA /tmp/fwm/dataB`. Start A, wait for `nodetool -p 7199 status` UN. Start B, wait until both are UN.
2. Start the samplers (B3d).
3. Start stress (B3c) in the background.
4. At t = 15 s run `kill -STOP $(cat /tmp/fwm/B.pid)`.
5. Watch `$v-used.csv` until UsedSize is flat for 5 s (or 25 s elapse). Record the plateau.
6. At t = 40 s run `kill -CONT $(cat /tmp/fwm/B.pid)`. Let stress finish or stop it after 60 s.
7. Stop the samplers. Run `nodetool -p 7299 stopdaemon`, then `-p 7199 stopdaemon`. If needed, `kill $(cat /tmp/fwm/A.pid) $(cat /tmp/fwm/B.pid)`.
8. Check that `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` are empty.

**B3f. Predictions** (stated before any run).
- **V0:** D < 1 MiB (the in-flight cap per link is ≤ 128 KiB; the rest is noise).
- **V1, V2, V3:** each D ∈ [64 MiB, 70 MiB]. Pairwise `|D_i − D_j| ≤ 4 MiB`, with no ordering by L. During the freeze, `pending_bytes` > 64 MiB.
- **V4 (positive control):** D ∈ [4 MiB, 8 MiB], so D(V2) − D(V4) ≥ 56 MiB.
- **Direct `MemoryUsed`:** the deltas follow the same pattern.
- **What would show the claim wrong:** D varying with L across V1-V3 by more than 4 MiB in the order of L (e.g. V1 ≪ V3), or D(V1) ≪ 64 MiB while `pending_bytes` > 64 MiB.
- **Amendment 2026-10-22 (stage-4 audit, A9 — added predictions from A8, and how the relations are judged; stated before any reading):**
  - **Knob read-back:** every STALL line of a lifetime shows the variant's (H, L): V0 (65536, 32768), V1 (67108864, 1024), V2 (67108864, 33554432), V3 (67108864, 66060288), V4 (4194304, 2097152).
  - **Stall level:** every STALL level is in [H, H + 65536). In every lifetime at least one STALL on the small link to 127.0.0.2 falls inside the freeze, and the highest such level is in [H, H + 65536).
  - **Resume level:** every RESUME level is ≤ L.
  - **Judging D:** the ranges apply to each lifetime's D. "Pairwise ≤ 4 MiB" and "ordered by L" are judged on the per-variant means of V1, V2, V3. "Ordered by L" means the three means are monotone in L **and** max − min > 4 MiB; an ordering within 4 MiB is noise.
  - D(V0) < 1 MiB is a baseline prediction; a miss is reported (B3g row 6) and is not part of the row 1 test.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| D(V1) ≈ D(V2) ≈ D(V3) ≈ 64 MiB, D(V4) ≈ 4 MiB, D(V0) ≈ 0 | Claim confirmed: usage flat in L, while the same workload moves usage when H (the known cap) changes |
| D ordered by L with gaps > 4 MiB | Claim refuted: usage follows `flushLowWaterMark` |
| D(V1-V3) ≪ 64 MiB and `pending_bytes` < 64 MiB | Limit never reached (workload too slow, B convicted too early); not confirmed. Raise threads, freeze earlier |
| D(V4) ≈ D(V2) | Positive control did not move (patch not in the running jar, or the measure is blind); not confirmed |
| Connection reset during freeze (`active_connections` drops) | tcp_user_timeout or conviction reset the link; run invalid |
| D(V0) several MiB | Noise floor too high for small effects; acceptable here because V1-V4 differences are tens of MiB |

**Amendment 2026-10-22 (stage-4 audit, A10 — verdict words and missing rows; stated before any reading).** Applied in this order; the first that applies is the tier's verdict:
1. *Connection reset during freeze* — judged by `active_connections` dropping, or A's log showing `Interrupted outbound connections to /127.0.0.2` or `/127.0.0.2:7000 is now DOWN` inside the freeze — or **(new)** a STALL line whose (H, L) is not the variant's (A9 knob read-back) → **Invalid** (the tier).
2. *D(V1-V3) ≪ 64 MiB and `pending_bytes` < 64 MiB* → **Not confirmed** (limit never reached). *D(V4) ≈ D(V2)*, i.e. D(V2) − D(V4) < 56 MiB, with V2 meeting its range → **Not confirmed** (positive control did not move).
3. *D ordered by L with gaps > 4 MiB* (as judged in A9) → **Refuted — usage follows the low mark (Effect: caps)**.
4. **(new)** A RESUME level > L, or a STALL level outside [H, H + 65536) → **Not confirmed (mechanism differs from A3; report it)**.
5. **(new)** D(V1-V3) pairwise ≤ 4 MiB and not ordered, but some lifetime's D outside [64 MiB, 70 MiB] while `pending_bytes` > 64 MiB and the STALL levels meet A9 → **Not confirmed**: the per-link stall is at H as traced, but D does not measure it at the predicted size.
6. **(new)** D(V1-V3) neither within 4 MiB pairwise nor ordered by L → **Not confirmed** (noise).
7. *D(V1) ≈ D(V2) ≈ D(V3) ≈ 64 MiB, D(V4) ≈ 4 MiB*, read as B3f's numbers (each lifetime's D in [64, 70] MiB for V1-V3 and [4, 8] MiB for V4; V1-V3 means pairwise ≤ 4 MiB; D(V2) − D(V4) ≥ 56 MiB) with A9's STALL and RESUME predictions met → **Confirmed — does not cap**. V0's D is reported as the baseline.
8. **(new)** Anything else → **Not confirmed (no matching row)**, Effect undetermined.

**B3h. Controls.**
- **V4 vs V2** is the positive control on the same workload.
- **V0** is the stock baseline.
- **The line-104 `grep` per build and a `jar tf`/`javap -c` check** of `OutboundConnectionSettings` in each variant's jar (the literals appear as `ldc`/`sipush` constants in the 2-arg constructor) prove which values ran.
- **Measuring D as a delta under steady load** removes CQL-frame and pool warm-up effects.
- **Disabled hints** remove hint-buffer and disk effects.
- **`internode_compression: none`** makes wire size equal canonical size.
- **The `pending_bytes` record** confirms the queue held more than H, so the plateau is the cap, not starvation.
- **Repetitions (2 per variant)** give a noise estimate.

**B4. Risks and cleanup.**
- **Shared clone:** never build or write in the repository's `cassandra/cassandra-5.0.9/`. All clones, builds, data and results live under `/tmp/fwm` on local `/`.
- **Disk:** unit tier < 1 GB (build). Cluster tier: 5 build copies × ~1.5 GB, plus ≤ 3 GB data per run. Check that `df -h /` has ≥ 20 GB free before starting.
- **Memory:** A may hold up to ~132 MiB queued plus 64 MiB in flight, far below 4 GB heap and the host RAM.
- **Processes:** the unit-tier test JVM exits after `testsome`. In the cluster tier, a frozen B must be `kill -CONT` before stopping, otherwise `stopdaemon` hangs. After each run, `pgrep -f 'CassandraDaemon|cassandra-stress|FlushWaterMarkProbeTest'` must be empty; kill any leftovers with `kill -9`. Kill sampler loops with `kill %1 %2 ...` or `pkill -f 'sjk mx'`.
- **Ports:** 7000, 7199, 7299 and 9042 on 127.0.0.1/.2. Check they are free first: `ss -ltn`.
- **Cleanup:** `rm -rf /tmp/fwm/dataA /tmp/fwm/dataB` after each run, and `rm -rf /tmp/fwm` at the end (after copying `/tmp/fwm/results`).
- **Amendment 2026-10-22 (stage-4 audit, A11 — paths and process checks on `pc13`):** the `/tmp/fwm` paths map to `~/cassandra-flw`, `~/cassandra-flw-p{1..4}` (A5), `~/stage4-flw/` (node conf and the tmpfs data) and `~/stage4-logs/flw/` (logs). The process check is `ps -eo pid,args` filtered to `java` + `CassandraDaemon` (+ working directory), never `pgrep -f` inside an inline ssh string. At the end the patched copies and the tmpfs are removed, and disk use stays under 35 GB.

## C. Sources read

- src/java/org/apache/cassandra/net/OutboundConnection.java
- src/java/org/apache/cassandra/net/OutboundConnectionSettings.java
- src/java/org/apache/cassandra/net/OutboundConnections.java (LARGE_MESSAGE_THRESHOLD)
- src/java/org/apache/cassandra/net/OutboundDebugCallbacks.java
- src/java/org/apache/cassandra/net/OutboundConnectionInitiator.java (SO_SNDBUF)
- src/java/org/apache/cassandra/net/InboundConnectionSettings.java (with* methods)
- src/java/org/apache/cassandra/net/InboundConnectionInitiator.java (SO_RCVBUF line)
- src/java/org/apache/cassandra/net/AsyncMessageOutputPlus.java
- src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java (watermark line)
- src/java/org/apache/cassandra/net/FrameEncoder.java
- src/java/org/apache/cassandra/net/Verb.java (_TEST_1, unsafeSet*)
- src/java/org/apache/cassandra/net/Message.java (out)
- src/java/org/apache/cassandra/net/MessagingService.java:666
- src/java/org/apache/cassandra/locator/ReconnectableSnitchHelper.java:69
- src/java/org/apache/cassandra/streaming/async/NettyStreamingConnectionFactory.java:91,100
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:388
- src/java/org/apache/cassandra/config/Config.java:238-272, 493-494
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java:3796-3804
- src/java/org/apache/cassandra/utils/memory/BufferPools.java
- src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
- src/java/org/apache/cassandra/db/virtual/InternodeOutboundTable.java
- conf/cassandra.yaml (internode queue, buffer, timeout, compression sections)
- test/unit/org/apache/cassandra/net/ConnectionTest.java
- test/unit/org/apache/cassandra/net/ProxyHandlerConnectionsTest.java
- test/unit/org/apache/cassandra/net/proxy/InboundProxyHandler.java
- cassandra/if-check-exp/README.md §6.1 (naming)
- https://issues.apache.org/jira/browse/CASSANDRA-15066
- https://netty.io/4.1/api/io/netty/channel/WriteBufferWaterMark.html

## D. Stage-4 feedback

**2026-10-22. Audited, run 1 at both tiers, self-checked; no run 2. Results:** [`results/flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md`](../../stage4-runtime-verification/results/flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md). Run on `pc13`.

**Case-file sha256 values:**
- as filed: `16b0da55a6454033fd77d712e0e921f2d331565af0dd9d9f6c6dc538f84295e9`
- frozen after the audit (A1–A11): `f754e36f8f7ab5edc281986809cf4291722348b29f732ba63c7ed0f7a8bcf69d`
- after runbook defects 1–2: `b797d658c074694d4e0ed46386f63d414f519fb3f23f87840c1f57c0c864fb98`

**Verdicts:**
- **Unit: Not confirmed (no matching row) — Effect undetermined.**
- **Cluster: Not confirmed (B3g/A10 row 5) — Effect undetermined.**

No prediction or row was changed after a reading.

**What was measured.** At both tiers the in-flight peak is flat in `flushLowWaterMark` and follows `flushHighWaterMark`, and the low mark moves only the resume level:
- **Unit, S:** 1.061–1.084 MB for L = 1 KiB … 1016 KiB at H = 1 MiB. The spread is 22.9 KB, with no trend.
- **Unit, U (pool):** spread 45.1 KB.
- **Unit, P-set S:** tracks H with ratio 64.1.
- **Unit, R:** ≤ L in 24 of 24 runs: 0 at L ≤ 32 KiB, ≈ 523 KB at L = 512 KiB, ≈ 981 KB at L = 1016 KiB.
- **Cluster:** networking-pool D = 116.65 / 116.45 / 116.33 MiB at L = 1 KiB / 32 MiB / 63 MiB (H = 64 MiB), against 7.19 MiB at H = 4 MiB.
- **Cluster, Byteman (the running H and L, read back):** the stall is at H + 1,937 B; every resume level is ≤ L.

**Why neither tier reached Confirmed.** Each tier missed one frozen magnitude prediction, and neither miss concerns L:
1. **Unit (B2f/A3, the Netty measure N).** `OutboundConnectionInitiator.java:197` installs `NoSizeEstimator`, whose `size()` returns 0. Netty's `totalPendingWriteBytes` therefore counts only 96 B per frame (N = 192 / 1,632 / 12,384 = 2 / 17 / 129 × 96), so "N ≥ S" fails by construction. The audit did not catch this.
2. **Cluster (B3f, D ∈ [64, 70] MiB).** The pool holds ≈ 1.82 × H. The likely cause (inferred) is that before H is reached delivery runs once per enqueue, so a frame typically carries one ~2.1 KiB mutation, and the pool keeps whole 2 KiB units: 4 KiB per one-message frame. V1's plateau is exactly 59,631 units for ≈ 31,791 messages.

**Runbook defects, both fixed before any counted cluster reading:**
1. The 4 KiB socket buffers throttled the link to ~17 KB/s before any freeze; they were dropped.
2. `AT LINE 857` in Byteman lands on the inlined `finally` (line 902); the rule now uses `AFTER INVOKE promiseToExecuteLater`.

**For stage 3 (not applied here):**
- Drop N, or predict it as `frames × 96`.
- Predict the pool's footprint from the frame size (per-message frames under light load) rather than as H + one frame; or record the frame count, for example `onSendSmallFrame` counts.
- With those two changes, both tiers' readings as measured would have matched "flat in L, positive control moves".

**Overlap.** The closed `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous` (Confirmed — caps) shows that the same in-flight bytes are inside `pendingBytes`: here pending reached the send-queue limit, 132 MiB = 4 MiB + 128 MiB, during every V1–V3 freeze. This pair of water marks is a sub-limit inside that cap, as this file's Ground says.

**The Estimate line is left as filed (negative).**
