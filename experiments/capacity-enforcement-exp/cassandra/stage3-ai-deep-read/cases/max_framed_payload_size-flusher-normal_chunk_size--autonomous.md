# MAX_FRAMED_PAYLOAD_SIZE (native protocol v5 outbound frame size) — verification solution  <!-- file: cases/max_framed_payload_size-flusher-normal_chunk_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set: the field initializer of `Flusher.MAX_FRAMED_PAYLOAD_SIZE`, the `Math.min(BufferPool.NORMAL_CHUNK_SIZE, …)` operand), **linked**: [`Flusher.java:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L48) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. The line sets a fixed per-frame slice size (131060 bytes) for outbound CQL v5 responses. It limits how big each single frame buffer is. It does not limit how many frames a response is cut into, or how many frames wait in a channel. Outbound off-heap usage therefore grows with response size × responses pending, whatever value this constant has. |
| Ground | The value controls how a response is cut up, not how much memory it uses. `flushLargeMessage` loops until the whole response body has been copied into frames ([`Flusher.java:170-198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L170-L198)). Each frame is handed to Netty with `writeAndFlush`, and nothing checks channel writability anywhere in `transport/`: the only write watermark is set at `PipelineConfigurator.java:139` and nothing reads it. So all `ceil(size/K)` frames are allocated off-heap and stay held until the socket drains. A smaller K only adds per-frame rounding overhead from the `BufferPool` allocation unit, so usage goes slightly **up** as K goes down. The memory-significant object (the queued frames of a response, of any size) is not bounded by the constant. |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (here: the given line; the Entry pointer row above and
> A3). Other citations may stay plain `file:line` (paths relative to the source root).

## A. Constraint trace

**A1. The constraint.**
- **Name:** `Flusher.MAX_FRAMED_PAYLOAD_SIZE` (the given line is its first operand). It is declared at [`Flusher.java:47-49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L47-L49):
  `MAX_FRAMED_PAYLOAD_SIZE = Math.min(BufferPool.NORMAL_CHUNK_SIZE, FrameEncoder.Payload.MAX_SIZE - Math.max(FrameEncoderCrc.HEADER_AND_TRAILER_LENGTH, FrameEncoderLZ4.HEADER_AND_TRAILER_LENGTH))`.
- **Kind:** a constant, `public static final int`. It is computed at class initialisation. It is not a compile-time constant (it is a method call), so classes that use it read it at run time.
- **Inputs:**
  - `BufferPool.NORMAL_CHUNK_SIZE = 128 << 10 = 131072`, at [`BufferPool.java:128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L128).
  - `FrameEncoder.Payload.MAX_SIZE = 1 << 17 = 131072`, at [`FrameEncoder.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoder.java#L41).
  - `FrameEncoderCrc.HEADER_AND_TRAILER_LENGTH = 10` (`net/FrameEncoderCrc.java:37`) and `FrameEncoderLZ4.HEADER_AND_TRAILER_LENGTH = 12` (`net/FrameEncoderLZ4.java:50`).
- **Unit:** bytes.
- **Default:** `min(131072, 131072 − 12) = 131060`. The `NORMAL_CHUNK_SIZE` term on the given line does **not** bind. The effective value comes from the v5 frame-format limit of 128 KiB per payload minus the larger header+trailer.
- **How to set:** it cannot be set. There is no yaml key, no `-D` property and no JMX. Changing it needs a source patch and a rebuild, then a restart. For this verification only, B2a gives a one-line test patch that reads an optional `-D` property and can only lower the value. With the property unset, the patched build behaves exactly as stock.

**A2. What it caps.**
- **Resource:** off-heap (direct) memory, through the size of **each single buffer** taken from the networking `BufferPool` (`BufferPools.forNetworking()`, `utils/memory/BufferPools.java:44-45,67-70`). Each of these buffers holds one outbound v5 frame on a native-transport (client) connection.
- **Compared quantity:** `envelopeSize(outbound.header)`, the size of one response envelope (9-byte header + body), at `Flusher.java:152` (`CQLMessageHandler.java:744-747`). In the per-frame loop it is `body.readableBytes()` (`Flusher.java:172`). For small responses it is the `FlushBuffer` byte total (`Flusher.java:278`).
- **What it does not cap:** the number of frames, the bytes queued per channel, or the bytes in flight across channels. It is a limit on frame size, not on usage.

**A3. Mechanism.**
1. **The given line** [`Flusher.java:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L48) fixes K = 131060 when the class initialises.
2. A v5 request completes. `CQLMessageHandler.toFlushItem` encodes the response into an `Envelope`. Its body is a Netty `ByteBuf` from `CBUtil.allocator`, a `PooledByteBufAllocator(true)`, so it is direct (`CBUtil.java:60`, `Message.java:367,392`). It is wrapped in a `FlushItem.Framed` along with the connection's `payloadAllocator` (`CQLMessageHandler.java:480-497`). `Dispatcher.flush` enqueues it on the event loop's `Flusher`. The default is `ImmediateFlusher` (`Dispatcher.java:467-480`, `native_transport_flush_in_batches_legacy: false`, `Config.java:291`).
3. **Large-message path** (`Flusher.java:152-155`): if `envelopeSize >= K`, `flushLargeMessage` runs (`Flusher.java:163-199`). It loops **while body bytes remain** (`Flusher.java:170`). Each pass:
   - asks the allocator for `min(remaining, K)` bytes (`:172-173`);
   - for the CRC codec, `Payload` takes `getAtLeast(K + 6 + 4)` from the networking pool (`FrameEncoderCrc.java:40-41`, `FrameEncoder.java:59-68`). The stock value is 131070 bytes, which is ≤ `NORMAL_CHUNK_SIZE`, so it is served from a pooled chunk rounded up to a 2 KiB unit = 131072;
   - clamps the buffer's **absolute** limit to K (`:183-184`). Since the position already sits after the 6-byte header, a full CRC frame carries K − 6 data bytes;
   - copies body bytes and calls `writeAndFlush` (`:197`, `:201-206`). `finish()` returns the unused tail to the pool (`FrameEncoder.java:79-85`, `BufferPool.java:877-892`). `FrameEncoderCrc.encode` wraps the buffer as a `ByteBuf` that goes back to the pool only when Netty has written it (`FrameEncoderCrc.java:66-96`).

   **Every frame is produced in one go.** There is no check of `channel.isWritable()`. `PipelineConfigurator.java:139` sets `WriteBufferWaterMark(8 KiB, 32 KiB)`, but no class under `transport/` reads writability (a grep for `isWritable`/`channelWritabilityChanged` finds nothing). For a response of N bytes, about `ceil((N+9)/(K−6))` frame buffers of `roundUp(K+4)` bytes each sit in Netty's outbound buffer until the peer reads them. Once flushed, the source envelope body is released (`Flusher.java:249-250`, `CQLMessageHandler.java:500-505`).
4. **Small-message path** (`:156-160`, `FlushBuffer.finish` `:294-314`): envelopes below K are grouped per channel into buffers of `min(remaining, K)`. A new buffer is started whenever the next envelope does not fit (`:303-307`). The number of buffers is not bounded either.
5. **When the "limit" is reached:** nothing is refused. The message is split into more frames. Everything is sent.
6. **Overshoot and bypass:**
   - **(a) LZ4 path.** The LZ4 payload allocator adds no header room (`FrameEncoder.java:114,118-121`). `FrameEncoderLZ4.encode` then allocates a *second* buffer of `12 + maxCompressedLength(K) = 12 + 131060 + 513 + 16 = 131601` bytes (`FrameEncoderLZ4.java:76-77`). That is larger than `NORMAL_CHUNK_SIZE`, so `BufferPool.LocalPool.get` misses and allocates it unpooled with `ByteBuffer.allocateDirect`, counted as overflow (`BufferPool.java:904-923, 940-943, 233-239`). So the `NORMAL_CHUNK_SIZE` operand on the given line does **not** keep compressed frames inside the pool.
   - **(b) Pool cap.** Pooled allocations stop at `networking_cache_size`. Beyond that, `allocateMoreChunks` returns null (`BufferPool.java:443-450`) and buffers become unpooled overflow, still with no total limit.
   - **(c) Pre-v5 connections.** v3/v4 connections take the unframed path (`Flusher.java:143-147`) and never use K.

**A4. Other consumers.** Outside this constant's control, the networking pool also serves:
- inbound frame decoding through `GlobalBufferPoolAllocator`, the channel allocator set at `PipelineConfigurator.java:282-283`;
- internode messaging frame encoders and decoders (`FrameEncoder.bufferPool`, `FrameEncoder.java:32`);
- the LZ4 output frames from A3.6a.

Netty's own `PooledByteBufAllocator` (`CBUtil.allocator`) holds the response envelope bodies until flush, and the arenas keep their memory after the bodies are released. The heap holds the result rows. The chunk-cache `BufferPool` (`BufferPools.java:38-39`) is separate. The inbound limits (`native_transport_max_request_data_in_flight[_per_ip]`, `native_transport_receive_queue_capacity`) cover request bytes and are released once the response is flushed (`CQLMessageHandler.java:500-511`). They do not cover response frames still queued.

**A5. Evidence beyond the source.**
- `doc/native_protocol_v5.spec:102` and `:141` state "The max size for the payload is 128KiB", for uncompressed and compressed frames. This is the origin of `Payload.MAX_SIZE`.
- `CHANGES.txt:1344` lists "Improve checksumming and compression in protocol V5 (CASSANDRA-15299)": https://issues.apache.org/jira/browse/CASSANDRA-15299
- Tests use the constant as a frame-split size, not a memory limit: `test/unit/org/apache/cassandra/transport/CQLConnectionTest.java:241,257` ("make sure we send 2 frame and no more"), and as the client's large-message threshold: `SimpleClient.java:733`.
- Git history was not available in the copy (no `.git`).

## B. Verification solution

**B1. Claim under test** (negative). Outbound off-heap memory held for pending CQL v5 responses grows in proportion to (number of pending responses × response size) and is **not** bounded by `MAX_FRAMED_PAYLOAD_SIZE` (K). Lowering K does not lower that usage. It raises it slightly, by the ratio `roundUp(K+4)/(K−6)` from the 2 KiB pool unit. The constant only bounds the size of each single frame buffer (≤ `roundUp(K+4)` bytes).

### Shared test patch (both tiers)

Apply this to the **local copy**, never to a shared tree. It replaces `Flusher.java:46-49`:

```java
    @VisibleForTesting
    public static final int MAX_FRAMED_PAYLOAD_SIZE =
        Math.min(Integer.getInteger("cassandra.test.max_framed_payload_size", Integer.MAX_VALUE),
                 Math.min(BufferPool.NORMAL_CHUNK_SIZE,
                          FrameEncoder.Payload.MAX_SIZE - Math.max(FrameEncoderCrc.HEADER_AND_TRAILER_LENGTH, FrameEncoderLZ4.HEADER_AND_TRAILER_LENGTH)));
    static { logger.info("MAX_FRAMED_PAYLOAD_SIZE={}", MAX_FRAMED_PAYLOAD_SIZE); }
```

- With the property unset, K = 131060, the same as stock.
- The property can only lower K.
- Valid test values are 4096 to 131060.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- Set `W=/local/disk/workdir` (local disk with ≥ 5 GiB free). Copy the source with `rsync -a <source>/ $W/src/`, apply the patch, then run `cd $W/src && ant -Dno-checkstyle=true jar`.
- Get the runtime classpath with `export CASSANDRA_HOME=$W/src; . $W/src/bin/cassandra.in.sh; echo "$CLASSPATH"`.
- Client JVM options: `CJ="$(grep -hv '^\s*#' $W/src/conf/jvm-clients.options $W/src/conf/jvm11-clients.options | grep -v '^\s*$' | tr '\n' ' ') -XX:MaxDirectMemorySize=2g -Dio.netty.tryReflectionSetAccessible=true"`.
- Probe source: `$W/probe/src/org/apache/cassandra/transport/FlusherProbe.java`. It goes in the same package, to reach the package-private `Flusher`, `Flusher.immediate`, `FlushItem.Framed` and `CBUtil`:

```java
package org.apache.cassandra.transport;

import java.lang.reflect.Field;
import java.util.*;
import io.netty.buffer.ByteBuf;
import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.*;
import org.apache.cassandra.net.*;
import org.apache.cassandra.utils.memory.*;

public class FlusherProbe
{
    public static void main(String[] a) throws Exception
    {
        int n = Integer.parseInt(a[0]);                 // response body bytes
        String codec = a.length > 1 ? a[1] : "crc";      // crc | lz4
        int cacheMiB = Integer.getInteger("probe.cache_mib", 512);
        DatabaseDescriptor.clientInitialization(true, () -> {
            Config c = new Config();
            c.networking_cache_size = new DataStorageSpec.IntMebibytesBound(cacheMiB + "MiB");
            return c; });
        FrameEncoder enc;
        if (codec.equals("lz4")) {
            Field f = Class.forName("org.apache.cassandra.net.FrameEncoderLZ4").getField("fastInstance");
            f.setAccessible(true); enc = (FrameEncoder) f.get(null);
        } else enc = FrameEncoderCrc.instance;
        BufferPool pool = BufferPools.forNetworking();
        EmbeddedChannel ch = new EmbeddedChannel(enc);   // nothing reads outbound: a stalled client
        long u0 = pool.usedSizeInBytes(), o0 = pool.overflowMemoryInBytes(), s0 = pool.sizeInBytes();

        ByteBuf body = CBUtil.allocator.directBuffer(n, n);
        byte[] chunk = new byte[65536]; Random r = new Random(42);   // incompressible
        while (body.writableBytes() > 0) { r.nextBytes(chunk); body.writeBytes(chunk, 0, Math.min(chunk.length, body.writableBytes())); }
        EnumSet<Envelope.Header.Flag> none = EnumSet.noneOf(Envelope.Header.Flag.class);
        Envelope resp = Envelope.create(Message.Type.RESULT, 1, ProtocolVersion.V5, none, body);
        Envelope req  = Envelope.create(Message.Type.QUERY, 1, ProtocolVersion.V5, none, CBUtil.allocator.directBuffer(16, 16).writeZero(16));

        Flusher fl = Flusher.immediate(ch.eventLoop());
        fl.enqueue(new Flusher.FlushItem.Framed(ch, resp, req, enc.allocator(),
                   it -> { it.requestEnvelope.release(); it.responseEnvelope.release(); }));
        fl.start();
        ch.runPendingTasks();

        int frames = ch.outboundMessages().size(); long wire = 0; int maxFrame = 0;
        for (Object o : ch.outboundMessages()) { int b = ((ByteBuf) o).readableBytes(); wire += b; maxFrame = Math.max(maxFrame, b); }
        long du = pool.usedSizeInBytes() - u0, dov = pool.overflowMemoryInBytes() - o0, ds = pool.sizeInBytes() - s0;
        System.out.printf("RESULT,K=%d,codec=%s,n=%d,frames=%d,maxFrame=%d,wire=%d,dUsed=%d,dOverflow=%d,dSize=%d,cacheMiB=%d%n",
                          Flusher.MAX_FRAMED_PAYLOAD_SIZE, codec, n, frames, maxFrame, wire, du, dov, ds, cacheMiB);
        ch.finishAndReleaseAll();
        System.out.printf("AFTER_RELEASE,dUsed=%d%n", pool.usedSizeInBytes() - u0);
        System.exit(0);
    }
}
```

Compile with `javac -cp "$CLASSPATH" -d $W/probe/classes $W/probe/src/org/apache/cassandra/transport/FlusherProbe.java`.

**B2b. Knobs.**

| Knob | Values | Why |
|---|---|---|
| K, via `-Dcassandra.test.max_framed_payload_size` | unset (131060, stock), 65536, 16384, 4096 | spans 32× |
| N, the response body size | 1048576, 4194304, 16777216 | to see whether usage tracks N or K |
| codec | `crc` for all cells; `lz4` for K = stock and K = 16384 at N = 4194304 | shows the A3.6a overflow |
| `-Dprobe.cache_mib` | 512 (default); 4 for the positive control | |

**B2c. Workload.**
- One response envelope of N incompressible bytes goes through the real `Flusher.flushLargeMessage` → `FrameEncoder.write` path into an `EmbeddedChannel` whose outbound queue is never read. Every frame stays held, as for a client that has not read yet.
- N ≥ 1 MiB ≫ K, so the large-message branch (`Flusher.java:152`) is always taken.
- Frame count: `F = ceil((N+9)/(K−6))` for crc and `ceil((N+9)/K)` for lz4.

**B2d. Observables and instruments.**
- `BufferPool.usedSizeInBytes()`: pooled bytes in use plus overflow (`BufferPool.java:282-285`).
- `overflowMemoryInBytes()` and `sizeInBytes()`: pooled bytes allocated plus overflow.
- Frame count, maximum frame wire size and total wire bytes, read from `EmbeddedChannel.outboundMessages()`.
- All sampled once, after `runPendingTasks()` and before release; then once more after `finishAndReleaseAll()`.
- Not observed: the Netty arena memory behind the body `ByteBuf`. It is released before sampling (the release callback runs in `flushWrittenChannels`), and it is outside `BufferPool` anyway.

**B2e. Procedure.**
1. `cd $W/src`. For each K, N and codec cell in B2b, run 3 repetitions, each in a fresh JVM, because the class is initialised once:
   `java $CJ -cp "$W/probe/classes:$CLASSPATH" ${K:+-Dcassandra.test.max_framed_payload_size=$K} -Dprobe.cache_mib=512 org.apache.cassandra.transport.FlusherProbe $N crc | grep -E 'RESULT|AFTER' >> $W/unit.csv`
2. Positive control: K unset, N = 16777216, crc, `-Dprobe.cache_mib=4`.
3. LZ4 cells: K unset and K = 16384, N = 4194304, `lz4`.
4. Check that each run's `RESULT` line reports the intended K, which comes from `Flusher.MAX_FRAMED_PAYLOAD_SIZE` itself.

**B2f. Predictions** (crc, cache 512 MiB). Per full frame, in-use bytes are `roundUp(K+4)`: 2 KiB units above 1 KiB, 32 B units below (`BufferPool.java:1600-1605`, `:1394-1400`). `dUsed ≈ (F−1)·roundUp(K+4) + roundUp(last frame)`, within ±1 allocation unit.

| K | maxFrame (wire) | F at N = 4 MiB | dUsed / N | dUsed at 1 / 4 / 16 MiB |
|---|---|---|---|---|
| 131060 | 131064 | 33 | ≈1.000 | ≈1.0 / 4.0 / 16.0 MiB |
| 65536 | 65540 | 65 | ≈1.031 | ≈1.03 / 4.13 / 16.5 MiB |
| 16384 | 16388 | 257 | ≈1.125 | ≈1.13 / 4.50 / 18.0 MiB |
| 4096 | 4100 | 1026 | ≈1.50 | ≈1.50 / 6.0 / 24.0 MiB |

- `wire = N + 9 + 10·F` exactly.
- `AFTER_RELEASE dUsed = 0` (±32 B).
- For every K, dUsed is linear in N (doubling N doubles dUsed within 1%). It is never ≤ a small multiple of K.
- **LZ4, K = 131060:** F = 33, every frame is unpooled, `dOverflow ≈ F·(K+12) ≈ 4.0 MiB`, `dSize − dOverflow ≈ 0` for frames.
- **LZ4, K = 16384:** request 16476 ≤ 128 KiB, so frames are pooled, `dOverflow ≈ 0`, `dUsed ≈ 4.5 MiB`.
- **Positive control (cache 4 MiB, N = 16 MiB):** `dSize − dOverflow ≤ 4 MiB`, because the pooled part is capped by `networking_cache_size`. `dOverflow ≥ 12 MiB`. `dUsed ≈ 16 MiB`, the same total as with 512 MiB.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| dUsed ≈ N·roundUp(K+4)/(K−6) for all K; linear in N; maxFrame = K+4 | Claim confirmed: K sets only the per-frame size; usage follows N, not K |
| dUsed stays ≤ ~2·K (or any bound set by K) as N grows from 1 to 16 MiB | Claim refuted: K would bound usage (some flow control not found in the trace) |
| dUsed falls in proportion to K (e.g. K/32 gives ≤ 1/2 the usage) | Claim refuted: usage follows the constant |
| dUsed flat across K, **and** the positive control moves (pooled part pinned at 4 MiB, overflow takes the rest) and dUsed doubles when N doubles | Claim confirmed (usage flat w.r.t. K while the instruments are shown to move) |
| frames/maxFrame do not change with K, or dUsed does not move with N | Not confirmed: patch not effective or instrument broken; fix and rerun |
| positive control: `dSize − dOverflow` > 4 MiB | Not confirmed: pool cap or instrument misread |
| `AFTER_RELEASE dUsed` ≠ 0 | Leak in the probe harness; the run is invalid |

**B2h. Controls.**
- K unset on the patched build reports 131060, identical to stock.
- N is varied at fixed K. This separates "follows response size" from "follows K".
- The `networking_cache_size` positive control shows a cap that really binds, read by the same instruments.
- The release check rules out leftover buffers.
- Each run uses a fresh JVM, so the static K and the pool start empty.
- Random data, so LZ4 frames are not shrunk by compression.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, the same `$W` build as in B2a (patched).
- Edit `$W/src/conf/cassandra.yaml`:
  - `data_file_directories: [$W/data/data]`, `commitlog_directory: $W/data/commitlog`, `saved_caches_directory: $W/data/saved_caches`, `hints_directory: $W/data/hints`, `cdc_raw_directory: $W/data/cdc`;
  - `networking_cache_size: 512MiB`;
  - `native_transport_port`: 9042, or a free port; check with `ss -ltn`. Keep the other ports at their defaults if free, otherwise move `storage_port` and `JMX_PORT` (in `cassandra-env.sh`).
- Before starting: `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` and `export JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=1g -XX:NativeMemoryTracking=summary ${K:+-Dcassandra.test.max_framed_payload_size=$K}"`.
- Write the probe `$W/probe/ClusterProbe.java` (default package) and compile it with `javac -cp "$CLASSPATH" -d $W/probe/classes`:

```java
import java.nio.ByteBuffer; import java.nio.file.*; import java.util.*;
import javax.management.*; import javax.management.remote.*;
import org.apache.cassandra.config.DatabaseDescriptor; import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.ConsistencyLevel; import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.transport.*; import org.apache.cassandra.transport.messages.*;

public class ClusterProbe {
  static MBeanServerConnection mbs;
  static long v(String on, String attr) throws Exception { return ((Number) mbs.getAttribute(new ObjectName(on), attr)).longValue(); }
  static void sample(String tag) throws Exception {
    String bp = "org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=";
    System.out.printf("SAMPLE,%s,used=%d,size=%d,overflow=%d,nioDirect=%d%n", tag,
      v(bp+"UsedSize","Value"), v(bp+"Size","Value"), v(bp+"OverflowSize","Value"),
      v("java.nio:type=BufferPool,name=direct","MemoryUsed"));
  }
  public static void main(String[] a) throws Exception {
    DatabaseDescriptor.clientInitialization();
    String mode = a[0]; int port = Integer.parseInt(a[1]); int m = Integer.parseInt(a[2]); int b = Integer.parseInt(a[3]);
    if (mode.equals("load")) {
      SimpleClient c = new SimpleClient("127.0.0.1", port, ProtocolVersion.V5).connect(false);
      c.execute("CREATE KEYSPACE IF NOT EXISTS probe WITH replication = {'class':'SimpleStrategy','replication_factor':1}", ConsistencyLevel.ONE);
      c.execute("CREATE TABLE IF NOT EXISTS probe.blobs (k int PRIMARY KEY, v blob)", ConsistencyLevel.ONE);
      ResultMessage.Prepared p = c.prepare("INSERT INTO probe.blobs (k, v) VALUES (?, ?)");
      Random r = new Random(7);
      for (int k = 0; k < m; k++) { byte[] v = new byte[b]; r.nextBytes(v);
        c.executePrepared(p, List.of(Int32Type.instance.decompose(k), ByteBuffer.wrap(v)), ConsistencyLevel.ONE); }
      c.close(); System.exit(0);
    }
    // mode read: a[4]=jmxPort a[5]=pauseFile a[6]=holdMillis ; port = proxy port
    mbs = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[4] + "/jmxrmi")).getMBeanServerConnection();
    Path pause = Paths.get(a[5]); long hold = Long.parseLong(a[6]);
    SimpleClient c = new SimpleClient("127.0.0.1", port, ProtocolVersion.V5).connect(false);   // no compression -> CRC frames
    c.execute("SELECT v FROM probe.blobs WHERE k = 0", ConsistencyLevel.ONE);                  // warm-up
    Thread.sleep(1000); sample("baseline");
    Files.createFile(pause); Thread.sleep(200);
    List<Message.Request> reqs = new ArrayList<>();
    for (int k = 0; k < m; k++) reqs.add(new QueryMessage("SELECT v FROM probe.blobs WHERE k = " + k, QueryOptions.forInternalCalls(ConsistencyLevel.ONE, List.of())));
    final Object[] res = new Object[1];
    Thread t = new Thread(() -> { try { res[0] = c.execute(reqs); } catch (Throwable e) { res[0] = e; } }); t.start();
    Thread.sleep(hold); sample("held");
    Files.delete(pause); t.join();
    System.out.println("RESULT," + (res[0] instanceof Map ? "ok,responses=" + ((Map<?,?>) res[0]).size() : "error," + res[0]));
    Thread.sleep(3000); sample("after");
    c.close(); System.exit(0);
  }
}
```

- Write a pausing TCP proxy `$W/probe/pause-proxy.py` (stdlib only). While the flag file exists, it stops reading the server→client direction, so the node sees a stalled reader. Client→server traffic keeps flowing.

```python
import os, socket, sys, threading, time
LISTEN, TARGET, FLAG = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
def pump(src, dst, gated):
    try:
        while True:
            while gated and os.path.exists(FLAG): time.sleep(0.02)
            d = src.recv(65536)
            if not d: break
            dst.sendall(d)
    except OSError: pass
    finally:
        for s in (src, dst):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass
ls = socket.socket(); ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
ls.bind(('127.0.0.1', LISTEN)); ls.listen(16)
while True:
    c, _ = ls.accept()
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536); s.connect(('127.0.0.1', TARGET))
    threading.Thread(target=pump, args=(c, s, False), daemon=True).start()
    threading.Thread(target=pump, args=(s, c, True), daemon=True).start()
```

**B3b. Knobs.**
- **K**, via `JVM_EXTRA_OPTS`: unset (131060), 65536, 16384, 4096. Each value needs a node restart. Confirm it in `logs/system.log` by grepping `MAX_FRAMED_PAYLOAD_SIZE=`. The line appears on the first response.
- **Pending responses M:** 32 (main). 64 for positive control 1.
- **Blob size B:** 4194304 bytes.
- **`networking_cache_size`:** 512MiB (main); 32MiB for positive control 2, at K unset and M = 32.
- **Hold window:** 5000 ms. It must stay below the 10 s timeout of `SimpleClient` (`SimpleClient.java:67`).

**B3c. Workload.**
- Load 64 rows of 4 MiB once. That is 256 MiB of data, below the 16 MiB per-mutation and message limits (`DatabaseDescriptor.java:3237-3245`).
- Then, through the paused proxy, pipeline M single-row `SELECT`s on one v5 connection. Each response envelope is about B + 100 bytes, far above K, so every one takes `flushLargeMessage`.
- Total response bytes: M = 32 gives ≈ 128 MiB; M = 64 gives ≈ 256 MiB. Both are below `MaxDirectMemorySize` = 1 GiB and the 512 MiB pool.
- At most about `tcp_wmem[max]` (usually 4 MiB) + 128 KiB drains into the kernel socket buffers. Record it with `sysctl net.ipv4.tcp_wmem`. The rest must stay in node memory.
- One read phase lasts about 10 s. Each cell runs 3 repetitions.

**B3d. Observables and instruments.**
- From the probe, over JMX at 3 points (baseline, held, after):
  - networking `BufferPool` `UsedSize` (in use, including overflow) — the main reading;
  - `Size` (allocated) and `OverflowSize`;
  - `java.nio:type=BufferPool,name=direct MemoryUsed`. This tracks `Size`, since pooled 1 MiB chunks are never freed.
- Supporting readings, taken in the held window from a second shell:
  - `ss -tmi '( sport = :9042 )'`: the server socket's Send-Q, the bytes in kernel buffers;
  - `jcmd $(cat $W/cassandra.pid) VM.native_memory summary | grep -A2 -E 'Other|Internal'`;
  - `grep VmRSS /proc/$(cat $W/cassandra.pid)/status`.
- Not directly observable: the Netty arena memory for response bodies (`CBUtil.allocator`, no JMX metric; NMT "Other" includes it only roughly) and heap for result rows. Neither depends on K.

**B3e. Procedure.**
1. Build and configure as in B3a. Start the node with K unset: `cd $W/src && bin/cassandra -p $W/cassandra.pid > $W/out.log 2>&1`. Wait for `Starting listening for CQL clients` in `logs/system.log`.
2. Load once: `java $CJ -cp "$W/probe/classes:$CLASSPATH" ClusterProbe load 9042 64 4194304`, then `bin/nodetool flush probe`.
3. Start the proxy: `python3 $W/probe/pause-proxy.py 19042 9042 $W/pause.flag & echo $! > $W/proxy.pid`.
4. Read phase, 3 times: `java $CJ -cp "$W/probe/classes:$CLASSPATH" ClusterProbe read 19042 32 4194304 7199 $W/pause.flag 5000 | tee -a $W/cluster-K$K.csv`. In the held window (about 2–4 s after start), take the `ss`, `jcmd` and RSS readings.
5. Stop the node with `kill $(cat $W/cassandra.pid)` and wait for the process to exit. Restart with `JVM_EXTRA_OPTS` carrying the next K. Confirm `MAX_FRAMED_PAYLOAD_SIZE=<K>` in `system.log` after the first read. Repeat step 4 for K = 65536, 16384, 4096. The data persists across restarts.
6. Positive control 1: K unset, M = 64.
7. Positive control 2: K unset, `networking_cache_size: 32MiB`, M = 32.
8. Unpaused control: K unset, M = 32. Use a variant run with the pause file never created: delete it right after creation, or add the argument `holdMillis=0` and skip `Files.createFile`.

**B3f. Predictions.** Let held − baseline `UsedSize` = Δ. Let D be the kernel drain measured by `ss`, at most about 4.2 MiB.

| Run | Δ predicted |
|---|---|
| K = 131060, M = 32 | ≈ 32 × 4.0 MiB − D ≈ 124–128 MiB |
| K = 65536 | ≈ 1.031 × that ≈ 128–132 MiB |
| K = 16384 | ≈ 1.125 × that ≈ 140–144 MiB |
| K = 4096 | ≈ 1.50 × that ≈ 186–192 MiB |
| Positive control 1 (M = 64) | Δ ≈ 2 × (K = 131060, M = 32) ≈ 250–256 MiB |
| Positive control 2 (cache 32 MiB) | (`Size` − `OverflowSize`) ≤ 32 MiB at held; `OverflowSize` ≥ 90 MiB; Δ still ≈ 124–128 MiB |
| Unpaused control | Δ at held ≈ 0–8 MiB (frames drain as produced) |

- `after` − `baseline` `UsedSize` ≈ 0 in all runs (± 1 MiB).
- `RESULT,ok,responses=M` in all runs.
- No Δ is ≤ a few × K (≈ 0.5 MiB at stock).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Δ ≈ M·B·roundUp(K+4)/(K−6) − D at every K; Δ does not fall when K falls | Claim confirmed |
| Δ bounded near a few frames (≤ ~2 MiB) regardless of M, or Δ shrinks ∝ K | Claim refuted: K caps outbound usage (flow control exists that the trace missed) |
| Δ flat across K, and positive control 1 doubles Δ and positive control 2 pins the pooled part at 32 MiB | Claim confirmed, with instruments shown to move where a cap binds |
| Δ ≈ 0 in the held window even at stock, or `ss` shows most bytes in Send-Q | Not confirmed: proxy did not stall the reader, or the kernel absorbed the load; lower `SO_RCVBUF`, raise M |
| positive control 1 does not double, or positive control 2 not pinned | Not confirmed: instruments or settings wrong |
| `system.log` shows a K other than intended | Run invalid; redo |
| `RESULT,error,timeout` | Hold window too long or node too slow; shorten hold to 3000 ms and rerun |

**B3h. Controls.**
- The patched build with K unset is the stock baseline.
- The unpaused run separates "held because of a stalled reader" from "allocated at all".
- `ss` Send-Q accounts for bytes moved into kernel buffers.
- Positive control 1 (M = 64) shows sensitivity to load.
- Positive control 2 shows a binding cap (`networking_cache_size`) read by the same metrics.
- One client connection only, and no other clients, so internode traffic on a single node is nil.
- Fresh restart per K.
- Random blobs, so nothing is compressible (no compression is negotiated anyway).

**B4. Risks and cleanup.**
- **Disk:** about 0.6 GiB (data + commit log) and about 1 GiB for the build, all under `$W` on local disk. Never on shared storage, never in the shared source tree.
- **Memory:** the node needs about 2 GiB heap + ≤ 1 GiB direct; the unit probe ≤ 2 GiB direct. Pick a node with ≥ 6 GiB free.
- **Ports:** check for and avoid used ports before starting.
- **Cleanup:**
  1. Stop the node with `kill $(cat $W/cassandra.pid)` and the proxy with `kill $(cat $W/proxy.pid)`; `rm -f $W/pause.flag`.
  2. Check that nothing is left: `pgrep -af CassandraDaemon`, `pgrep -af pause-proxy`, `pgrep -af ClusterProbe`, `pgrep -af FlusherProbe` must all print nothing.
  3. Remove the data with `rm -rf $W/data`. Remove the rest of `$W` when stage 4 no longer needs the build.

## C. Sources read

```
src/java/org/apache/cassandra/transport/Flusher.java
src/java/org/apache/cassandra/utils/memory/BufferPool.java
src/java/org/apache/cassandra/utils/memory/BufferPools.java
src/java/org/apache/cassandra/net/FrameEncoder.java
src/java/org/apache/cassandra/net/FrameEncoderCrc.java
src/java/org/apache/cassandra/net/FrameEncoderLZ4.java
src/java/org/apache/cassandra/transport/PipelineConfigurator.java
src/java/org/apache/cassandra/transport/CQLMessageHandler.java
src/java/org/apache/cassandra/transport/Dispatcher.java
src/java/org/apache/cassandra/transport/Envelope.java
src/java/org/apache/cassandra/transport/Message.java (encode, lines 323-402)
src/java/org/apache/cassandra/transport/CBUtil.java
src/java/org/apache/cassandra/transport/SimpleClient.java
src/java/org/apache/cassandra/transport/ProtocolVersion.java
src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/config/DataStorageSpec.java
test/unit/org/apache/cassandra/transport/CQLConnectionTest.java
conf/cassandra.yaml
conf/jvm-server.options, conf/jvm11-server.options, conf/jvm17-server.options
doc/native_protocol_v5.spec
CHANGES.txt
https://issues.apache.org/jira/browse/CASSANDRA-15299 (cited from CHANGES.txt; not fetched)
```

## D. Stage-4 feedback

none yet
