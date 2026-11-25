# FrameEncoder.Payload.MAX_SIZE — verification solution  <!-- file: cases/frameencoder_payload_max_size-payload-max_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity-set place: the constant is set here), **linked**: [`FrameEncoder.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoder.java#L41) `public static final int MAX_SIZE = 1 << 17;` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. `MAX_SIZE` sets the largest size of **one** native-protocol-v5 frame (128 KiB). It does not limit how many frames are held at once. A response of S bytes becomes ceil(S / ~128 KiB) frame buffers. `Flusher` allocates all of them in one loop and queues them without checking channel writability. Total off-heap use therefore follows response size × number of responses in flight, not `MAX_SIZE`. |
| Ground | (1) Its job is wire format. The v5 frame header holds the payload length in 17 bits ([`FrameDecoderCrc.java:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameDecoderCrc.java#L79) `& 0x1FFFF`; `doc/native_protocol_v5.spec:100-107`). (2) It bounds a 128 KiB buffer, which is not memory-significant by itself. The only place it shapes server memory is `Flusher`, and there it sets frame granularity, not a total ([`Flusher.java:170-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L170-L197)). No transport code consults `isWritable`. (3) The server's inbound CQL side passes `MAX_SIZE - 1` as `largeThreshold`, but the CQL handler never reads it. Only `InboundMessageHandler` (internode) reads `largeThreshold`, and internode uses a different threshold (`OTCP_LARGE_MESSAGE_THRESHOLD`, 64 KiB). (4) It cannot be configured. It is a `static final` compile-time constant inlined into other classes, so a "knob" exists only by recompiling. |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). For this capacity-set unit, "the if statement" means the given line,
> `FrameEncoder.java:41`. The checks that compare against the value are also linked in A3.

## A. Constraint trace

**A1. The constraint.**
- **Name:** `org.apache.cassandra.net.FrameEncoder.Payload.MAX_SIZE`.
- **Kind:** constant (a `public static final int`, a compile-time constant).
- **Declared at:** [`FrameEncoder.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoder.java#L41), `public static final int MAX_SIZE = 1 << 17;`.
- **Unit:** bytes.
- **Default:** 131072 (128 KiB). It is a literal, not derived. It matches the 17-bit length field of the v5 frame header (`doc/native_protocol_v5.spec:100-107, 141-145`). It also equals `BufferPool.NORMAL_CHUNK_SIZE = 128 << 10` (`utils/memory/BufferPool.java:128`).
- **How it is set:** it cannot be set. There is no yaml key, `-D` property or JMX attribute. javac inlines it into every class that uses it: `transport/Flusher.java:47-49`, `transport/CQLMessageHandler.java:83`, `transport/SimpleClient.java:99,177`, and the tests `AuthMessageSizeLimitTest`, `MessageSizeLimitTest`, `NativeProtocolLimitsTestBase`. Changing it therefore means editing line 41 and doing a **clean** rebuild (`ant clean jar`), not just recompiling `FrameEncoder`.
- **Related literal:** the encoders enforce the same 128 KiB with a separate literal `1 << 17`, not with `MAX_SIZE` (`FrameEncoderCrc.java:71`, `FrameEncoderLZ4.java:73`). Editing line 41 does not move those checks.

**A2. What it caps.**
- **Resource:** off-heap memory, as buffers from the networking `BufferPool` (`BufferPools.forNetworking()`, `FrameEncoder.java:31`, `BufferPools.java:43-44`). Frame buffers above 128 KiB, or allocated when the pool is exhausted, come from `ByteBuffer.allocateDirect` as overflow (`BufferPool.java:233-238`, `:906-924`).
- **Quantity compared with the limit:** the size of one outbound CQL v5 frame.
  - In `Flusher`, the operand is the response envelope size `envelopeSize(header) = 9 + bodySize` (`CQLMessageHandler.java:745-747`). It is compared with the derived `MAX_FRAMED_PAYLOAD_SIZE = min(NORMAL_CHUNK_SIZE, MAX_SIZE - max(10, 12)) = 131060` (`Flusher.java:47-49`). The result selects the large-message path, and per frame it bounds `payloadSize` and the buffer limit.
  - The total held across frames, responses and connections is **not** compared with anything derived from `MAX_SIZE`.

**A3. Mechanism.**
1. **Where the value is set:** [`FrameEncoder.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoder.java#L41). `Payload`'s constructor never reads `MAX_SIZE`. It asks the networking pool for `getAtLeast(payloadCapacity + header + trailer)` off-heap (`FrameEncoder.java:64`). Whatever capacity the caller asks for is allocated.
2. **Derived limit:** [`Flusher.java:47-49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L47-L49). `MAX_FRAMED_PAYLOAD_SIZE = min(131072, MAX_SIZE − 12) = 131060` at the default value.
3. **The check that uses it** (server outbound, v5 only): [`Flusher.java:152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L152), `if (envelopeSize(outbound.header) >= MAX_FRAMED_PAYLOAD_SIZE)`.
   - **True (large response):** `flushLargeMessage` (`Flusher.java:163-199`) loops `while (body.readableBytes() > 0 || firstFrame)` (`:170`). Each pass does the following:
     - allocates `payloadSize = min(remaining body, 131060)` (`:172-173`);
     - clamps the buffer limit at 131060 ([`Flusher.java:183-184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L183-L184));
     - copies a slice of the body into the buffer;
     - calls `writeAndFlush` (`:197`, `:202-206`).

     Nothing in the loop waits for the channel to drain. `grep isWritable src/java/org/apache/cassandra/transport` finds nothing. The channel's `WriteBufferWaterMark(8 KiB, 32 KiB)` (`PipelineConfigurator.java:139`) only flips a writability flag that nobody reads. As a result, for a response of S bytes, ceil((S+9)/(131060 − header)) frame buffers are allocated back to back. All of them that the socket has not yet taken stay in Netty's outbound buffer.
   - **False (small responses):** they are batched per channel into `FlushBuffer`. A frame is at most 131060 bytes (`Flusher.java:278-283`). A new frame is started when the next envelope does not fit (`:295-300`).
4. **Encoder hard check:** [`FrameEncoderCrc.java:71-72`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoderCrc.java#L71-L72) (`dataLength >= 1 << 17` throws `IllegalArgumentException("Maximum payload size is 128KiB")`, and the frame is returned to the pool at `:92`), plus [`FrameEncoderLZ4.java:73-74`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoderLZ4.java#L73-L74). These are protocol-validity checks, not memory checks. They use the literal, not `MAX_SIZE`.
5. **When the limit is reached:** it never refuses or delays memory. It only splits the work into more frames. In the encoders, an oversized single frame fails that write.
6. **Paths that bypass or overshoot it:**
   - (a) The whole response body is already in memory before framing (`Message.java:366`, from `CBUtil.allocator`, a Netty pooled allocator, not the networking pool). For a moment the body and its frames coexist, about 2·S.
   - (b) Many concurrent large responses on one or many connections each add about S.
   - (c) Inbound CQL: `CQLMessageHandler` passes `LARGE_MESSAGE_THRESHOLD = MAX_SIZE − 1` (`CQLMessageHandler.java:83, 133`) to `AbstractMessageHandler`, which stores it (`AbstractMessageHandler.java:183`). Only `InboundMessageHandler.java:148` (internode) reads `largeThreshold`. On the CQL side, the large-message path is chosen by the frame's self-contained flag (`AbstractMessageHandler.java:224-229`). Inbound memory is bounded by `native_transport_max_message_size` (`CQLMessageHandler.java:551`, `:799`) and the in-flight reserves, not by `MAX_SIZE`.
   - (d) Internode messaging frames at `OutboundConnections.LARGE_MESSAGE_THRESHOLD`, derived from `-Dcassandra.otcp_large_message_threshold` (default 64 KiB; `CassandraRelevantProperties.java:388`, `OutboundConnections.java:69-70`, `OutboundConnection.java:766, 782`). It does not use `MAX_SIZE`.
   - (e) Pre-v5 connections are unframed (`Flusher.java:139-143`), so `MAX_SIZE` plays no part.

**A4. Other consumers.** The same off-heap resource is also used by:
- **Networking `BufferPool`:** inbound frame decoding through `GlobalBufferPoolAllocator` (`PipelineConfigurator.java:282-287`), internode messaging buffers, and streaming. The pooled part is capped by `networking_cache_size` (default `min(128 MiB, heap/16)`, `DatabaseDescriptor.java:573-574`; enforced at `BufferPool.java:441-452`). Allocations beyond that go to overflow, which has no cap.
- **Netty pooled allocator (`CBUtil.allocator`):** response and request bodies.
- **Chunk-cache `BufferPool`:** `file_cache_size`.
- Memtables (off-heap modes), bloom filters, compression metadata, index summaries, and direct buffers in general.

**A5. Evidence beyond the source.**
- `doc/native_protocol_v5.spec` §2.1–2.2, lines 70–145 in the tree: "The max size for the payload is 128KiB"; payload length is 17 bits.
- Protocol v5 framing was introduced by CASSANDRA-15299 (https://issues.apache.org/jira/browse/CASSANDRA-15299). This is cited for background only; nothing below depends on it.
- No git history was available in the copy.

## B. Verification solution

**B1. Claim under test (negative).** Changing `FrameEncoder.Payload.MAX_SIZE` (131072 → 65536 → 32768, recompiled) changes the size and number of the outbound v5 frame buffers for a large CQL response. It does **not** change the total off-heap memory those buffers occupy. That total stays about equal to the response bytes in flight, within ±1% in the unit tier and ±5% in the cluster tier, at every value. If total frame-buffer usage scales with `MAX_SIZE`, or stays near (number of responses × `MAX_SIZE`), the claim is refuted.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11), Apache Ant ≥ 1.10, and network access to Maven Central for the first build.
- **Work directory on local disk:** `export WORK=/mydata/o124-s3` (any local-disk directory with ≥ 15 GiB free; check with `df -h $WORK`).
- **Copy of the source:** `rsync -a --exclude build ~/cassandra-5.0.9/ $WORK/src/`. All edits, builds and data stay under `$WORK`. Never build in the shared tree.
  - *Amendment 2026-11-25 (stage-4 audit, A1; environment only, B2f/B2g unchanged):* on the stage-4 nodes the work directory is `WORK=/mydata/jingsong-cass-s4/o124` and the copy is `cp -a /mydata/s4/cassandra-base $WORK/src` (the built `copy-source.sh` copy of the repository's `systems/cassandra/source/`, `cassandra-5.0.9`), per `cassandra/stage4-runtime-verification/environment.md`.
- **Test source:** `$WORK/src/test/unit/org/apache/cassandra/transport/FrameMaxSizeProbeTest.java` (text in B2e). It must be in package `org.apache.cassandra.transport`, because `Flusher`, `Flusher.immediate` and `FlushItem.Framed` are package-private.
- **JVM:** whatever `ant testsome` uses (test config `test/conf/cassandra.yaml`, test heap from `build.xml`). No extra options.

**B2b. Knobs.**

| Run | Line 41 | `MAX_FRAMED_PAYLOAD_SIZE` (F) | Data bytes per full Crc frame (F − 6) |
|---|---|---|---|
| M17 | `1 << 17` (default) | 131060 | 131054 |
| M16 | `1 << 16` | 65524 | 65518 |
| M15 | `1 << 15` | 32756 | 32750 |

- **Why these values:** values above `1 << 17` are not valid. The 17-bit length field and the literal checks in the encoders allow at most 131071 bytes of data per frame, and F is also capped by `NORMAL_CHUNK_SIZE`. Halving twice gives a 4× spread in frame size, which a "usage follows `MAX_SIZE`" reading could not hide.
- **How each value is set:** `sed -i '41s/1 << 17/1 << 16/' $WORK/src/src/java/org/apache/cassandra/net/FrameEncoder.java` (or `1 << 15`), check with `sed -n 41p`, then `ant clean`. A clean build is required because the constant is inlined into `Flusher`.
- **Second variable (control):** response body size S = 4 MiB and S = 8 MiB in every run.

**B2c. Workload.**
- One RESULT envelope (protocol V5, stream 1) with a heap body of S bytes (`Unpooled.wrappedBuffer(new byte[S])`). Because the body is on the heap, it is outside the networking pool.
- The envelope is pushed through the real `Flusher.immediate(...)` → `flushLargeMessage` → `FrameEncoderCrc` on a Netty `EmbeddedChannel`.
- `EmbeddedChannel` keeps every outbound frame until the test reads it. This is the worst case of a client that does not read, so every frame is alive at the same time.
- **Arithmetic for S = 8 MiB:** envelope size = 8,388,617 bytes, which is ≫ F at every value, so the `>= MAX_FRAMED_PAYLOAD_SIZE` branch is always taken. Frame counts are 65 (M17), 129 (M16) and 257 (M15).
- **Extra sub-case (hard check):** one payload of 131072 data bytes and one of 131071 bytes are written straight through `FrameEncoderCrc`. This shows where the literal 128 KiB check binds.

**B2d. Observables and instruments.**
- `BufferPools.forNetworking().usedSizeInBytes()` (pooled in-use + overflow; `BufferPool.java:282-285`). Read before the flush, after it with all frames held, and after the frames are released.
- Frame count, largest frame on the wire (`readableBytes`), largest data per frame (wire − 10), and the sum of wire bytes. These come from `EmbeddedChannel.readOutbound()`.
- `Flusher.MAX_FRAMED_PAYLOAD_SIZE`, printed to confirm the rebuilt constant.
- Each reading is a single instantaneous value. The loop runs synchronously in the test thread, so there is no sampling race.
- **Not observable here:** real socket draining, and memory of the Netty body allocator.

**B2e. Procedure.**
1. Write the test:
```java
package org.apache.cassandra.transport;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.net.FrameEncoder;
import org.apache.cassandra.net.FrameEncoderCrc;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

public class FrameMaxSizeProbeTest
{
    @BeforeClass
    public static void init() { DatabaseDescriptor.daemonInitialization(); }

    @Test
    public void probe()
    {
        System.out.printf("PROBE MAX_SIZE=%d MAX_FRAMED_PAYLOAD_SIZE=%d%n",
                          FrameEncoder.Payload.MAX_SIZE, Flusher.MAX_FRAMED_PAYLOAD_SIZE);
        for (int s : new int[]{ 4 << 20, 8 << 20, 8 << 20 })   // 8 MiB twice: repeatability
            runOnce(s);
        hardCheck(131071);
        hardCheck(131072);
    }

    private static void runOnce(int bodySize)
    {
        BufferPool pool = BufferPools.forNetworking();
        EmbeddedChannel ch = new EmbeddedChannel(FrameEncoderCrc.instance);
        long before = pool.usedSizeInBytes();
        Envelope env = Envelope.create(Message.Type.RESULT, 1, ProtocolVersion.V5,
                                       EnumSet.noneOf(Envelope.Header.Flag.class),
                                       Unpooled.wrappedBuffer(new byte[bodySize]));
        Flusher f = Flusher.immediate(ch.eventLoop());
        f.enqueue(new Flusher.FlushItem.Framed(ch, env, null, FrameEncoderCrc.instance.allocator(),
                                               item -> item.responseEnvelope.release()));
        f.start();
        ch.runPendingTasks();
        List<ByteBuf> frames = new ArrayList<>();
        ByteBuf b;
        while ((b = ch.readOutbound()) != null) frames.add(b);
        long held = pool.usedSizeInBytes() - before;
        int maxWire = 0; long sumWire = 0;
        for (ByteBuf fr : frames) { maxWire = Math.max(maxWire, fr.readableBytes()); sumWire += fr.readableBytes(); }
        frames.forEach(ByteBuf::release);
        ch.finishAndReleaseAll();
        long after = pool.usedSizeInBytes() - before;
        System.out.printf("PROBE body=%d envelope=%d frames=%d maxWire=%d maxData=%d sumWire=%d heldDelta=%d releasedDelta=%d%n",
                          bodySize, bodySize + 9, frames.size(), maxWire, maxWire - 10, sumWire, held, after);
    }

    private static void hardCheck(int dataLen)
    {
        EmbeddedChannel ch = new EmbeddedChannel(FrameEncoderCrc.instance);
        FrameEncoder.Payload p = FrameEncoderCrc.instance.allocator().allocate(true, dataLen);
        p.buffer.position(p.buffer.position() + dataLen);
        p.finish();
        try { ch.writeOutbound(p); System.out.printf("PROBE hardCheck data=%d accepted%n", dataLen); }
        catch (IllegalArgumentException e) { System.out.printf("PROBE hardCheck data=%d rejected: %s%n", dataLen, e.getMessage()); }
        ch.finishAndReleaseAll();
    }
}
```
2. **Run M17.** `cd $WORK/src && sed -n 41p src/java/org/apache/cassandra/net/FrameEncoder.java` (must show `1 << 17`). Then `ant clean && ant testsome -Dtest.name=org.apache.cassandra.transport.FrameMaxSizeProbeTest`. Then `grep -o 'PROBE[^<]*' build/test/output/TEST-org.apache.cassandra.transport.FrameMaxSizeProbeTest.xml | tee $WORK/unit-M17.txt`.
   - *Amendment 2026-11-25 (stage-4 runbook defect D1; B2f/B2g unchanged):* the `ant testsome` JVM routes `System.out` through a logger (`SubstituteLogger`), one log line per `printf` fragment, and the JUnit XML carries no stdout, so the `grep … TEST-*.xml` step finds nothing. Capture the ant output (`ant testsome … > $WORK/logs/unit-M17-testsome.log 2>&1`) and rebuild the PROBE lines from it: `grep -F SubstituteLogger.java <log> | sed 's/.*SubstituteLogger\.java:[0-9]* - //' | tr -d '\n' | sed 's/PROBE /\nPROBE /g' | grep '^PROBE' > $WORK/unit-M17.txt` (the same in steps 3 and 4).
3. **Run M16.** `sed -i '41s/1 << 17/1 << 16/' src/java/org/apache/cassandra/net/FrameEncoder.java`, then repeat the `ant clean && ant testsome …` and grep steps, writing to `$WORK/unit-M16.txt`.
4. **Run M15.** `sed -i '41s/1 << 16/1 << 15/' …`, then repeat, writing to `$WORK/unit-M15.txt`.
5. **Restore.** `sed -i '41s/1 << 15/1 << 17/' …`, then `ant clean jar` so the copy is back at the default for the cluster tier's M17 run.
6. Check that no test JVM is left: `pgrep -f FrameMaxSizeProbeTest` returns nothing.

**B2f. Predictions** (S = 8 MiB, envelope 8,388,617 B; Crc frames; ±1% on byte totals because of `BufferPool` 2 KiB rounding).

| Run | `MAX_FRAMED_PAYLOAD_SIZE` | frames | maxData | maxWire | sumWire | heldDelta |
|---|---|---|---|---|---|---|
| M17 | 131060 | 65 | 131054 | 131064 | 8,388,617 + 650 = 8,389,267 | ≈ 8,390,656 (64×131072 + 2048), within [8.39 MB, 8.47 MB] |
| M16 | 65524 | 129 | 65518 | 65528 | 8,388,617 + 1290 = 8,389,907 | ≈ 8,392,704 (128×65536 + 4096), same band |
| M15 | 32756 | 257 | 32750 | 32760 | 8,388,617 + 2570 = 8,391,187 | ≈ 8,394,752 (256×32768 + 6144), same band |

- **S = 4 MiB:** frames are 33, 65 and 129 for M17, M16 and M15. heldDelta ≈ 4.19–4.20 MB at all three, which is half the 8 MiB value.
- **releasedDelta** is 0 (± one 2 KiB unit) in every run.
- **hardCheck:** 131071 is accepted and 131072 is rejected ("Maximum payload size is 128KiB") in **all three** runs. This shows the encoder's limit is the literal and is unaffected by line 41.
- **Summary:** maxData scales 4:2:1 with `MAX_SIZE`; heldDelta changes by < 0.1% across `MAX_SIZE` and by 2× across S.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| maxData follows F (131054 / 65518 / 32750) and frame count doubles per halving | The constant binds its own operand, frame granularity, as traced (mechanism confirmed) |
| heldDelta ≈ envelope size (±1%) at all three `MAX_SIZE` values, and doubles from S = 4 to 8 MiB | **Claim confirmed:** usage is flat across the constraint while the control (S) moves it |
| heldDelta scales with `MAX_SIZE` (for example M15 ≤ 0.6 × M17), or stays near one frame (≤ 2 × `MAX_SIZE`) | **Claim refuted:** total usage follows the constraint |
| heldDelta does not move between S = 4 and 8 MiB, or frames = 1 | Limit never reached, or instrument/control failed: **not confirmed**. Check that the test is the patched build (printed `MAX_FRAMED_PAYLOAD_SIZE`) |
| `MAX_FRAMED_PAYLOAD_SIZE` printed ≠ the table value | Stale inlined constant: rerun with `ant clean` |
| releasedDelta ≫ 0 | Leak in the probe; the heldDelta reading is still valid but note it |

**B2h. Controls.**
- **Positive control:** S varies at a fixed `MAX_SIZE`. It must move heldDelta proportionally, which shows the instrument sees frame memory.
- **Mechanism control:** maxData must follow F. This shows the edit took effect.
- **Constant check:** the printed `MAX_SIZE` and `MAX_FRAMED_PAYLOAD_SIZE` rule out a stale build.
- **Isolation:** the body sits on the heap, so the networking-pool delta contains frames only.
- **Repeatability:** the 8 MiB case runs twice; the two readings must agree within one 2 KiB unit per frame.

### B3. Cluster tier

**B3a. Environment and build.**
- **Node:** one Linux node, JDK 11, run from `$WORK/src`, which is built once per `MAX_SIZE` value as in B2 (`ant clean jar`). Run one node at a time.
- **Data:** commit log, hints and saved caches go under `$WORK/src/data` (the default when `cassandra.yaml` leaves the directories unset). Logs go to `$WORK/src/logs`. Needs ≥ 2 GiB free.
- **Ports:** 9042 (native), 7000 (storage) and 7199 (JMX) must be free (`ss -ltn | grep -E ':(9042|7000|7199|19042) '`). If a port is taken, change `native_transport_port` / `storage_port` in `conf/cassandra.yaml` and `JMX_PORT` in `conf/cassandra-env.sh`, and carry the new value through every command below.
- **Environment before start:**
  - `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`
  - `export JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary"`
  - *Amendment 2026-11-25 (stage-4 audit, A2; environment only, B3f/B3g unchanged):* scope `JVM_EXTRA_OPTS`, `MAX_HEAP_SIZE` and `HEAP_NEWSIZE` to the `bin/cassandra` command instead of exporting them (environment.md §6), and run `ulimit -n 100000` first (the stage-4 nodes default to a soft limit of 1024). `HEAP_NEWSIZE` is ignored under G1 (the node prints a warning); harmless.
- **`conf/cassandra.yaml` edits in `$WORK/src`:**
  - `networking_cache_size: 128MiB` (equal to the default at a 2 GiB heap; written out for clarity);
  - everything else stays at the default. In particular `native_transport_max_message_size` is unset; its default is min(max_mutation_size 16 MiB, in-flight limits) = 16 MiB, so an 8 MiB write is accepted.
- **Client:** Python ≥ 3.8 with the driver bundled in the tree:
  - `export PYTHONPATH=$WORK/src/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0`
  - add `pure_sasl` / `wcwidth` / `pyasyncore` zips if present in `lib/`, as `bin/cqlsh.py:46-64` does.
  - Protocol v5, `compression=False`, so the server uses `FrameEncoderCrc` (`PipelineConfigurator.java:379-384`).

**B3b. Knobs.**
- **Main knob:** `MAX_SIZE` at M17, M16 and M15 (rebuild between runs, as in B2b).
- **Positive control:** `networking_cache_size: 16MiB` at M17. This is a cap known to bind on the same pool: pooled `Size − OverflowSize ≤ 16 MiB`, see `BufferPool.java:441-452`.
- **Workload control:** K = 4 and K = 8 concurrent responses at M17.

**B3c. Workload.**
- **Pausable proxy.** A local TCP proxy on 127.0.0.1:19042 forwards to 127.0.0.1:9042. It always forwards client → server. Server → client forwarding stops while the file `$WORK/pause` exists. Stopping the read makes the server's socket fill, so Netty must hold every remaining frame, which is the "client slow to read" case.
- **Data.** Keyspace `o124` (SimpleStrategy, RF 1), table `t (k int PRIMARY KEY, v blob)`, 8 rows of 8 MiB (`os.urandom`): 64 MiB in total, then `nodetool flush`.
- **Probe.** One driver session goes through the proxy. It warms up by reading each row once unpaused. Then it creates the pause file, issues K `execute_async("SELECT v FROM o124.t WHERE k=%s")` for k = 0..K−1 with timeout 120 s, holds the pause 20 s, removes the pause file, and checks that each result is 8,388,608 bytes.
- **Arithmetic.** Responses in flight = K × (8,388,608 + about 40 bytes of row/metadata) ≈ 67.1 MB at K = 8. The kernel can absorb at most B_k = server-socket Send-Q + proxy-socket Recv-Q. On a default Linux that is ≤ `tcp_wmem[2]` + `tcp_rmem[2]` ≈ 4 + 6 MiB; it is read live with `ss`. So ≥ ~56 MB must stay in Netty frame buffers. This is far above one frame (128 KiB) and above any "K × `MAX_SIZE`" figure (1 MiB).
- **Duration.** About 2 minutes per run, plus about 1 minute of node start.

**B3d. Observables and instruments.**
- **Primary:** networking pool `UsedSize`, plus `Size` and `OverflowSize`. MBean `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=<X>` (`BufferPoolMetrics.java:52-64`), read with `bin/nodetool sjk mx -b "<bean>" -mg -f Value`.
- **Secondary:** NMT `jcmd <pid> VM.native_memory summary`, line `Other (reserved=…, committed=…)`. This is where JDK 11 counts direct and `Unsafe` memory, including Netty no-cleaner buffers.
- **Kernel queue:** `ss -tmn '( sport = :9042 )'` (Send-Q) and `ss -tmn '( sport = :19042 or dport = :9042 )'` (proxy Recv-Q) give B_k.
- **Sampling:** each instrument is read once before the pause, every 2 s during the 20 s pause, and once 10 s after release.
- **Not observable here:** individual frame sizes (covered by the unit tier) and the Netty `CBUtil` body arenas (they show only inside NMT Other).

**B3e. Procedure.**
1. **Proxy:** write `$WORK/proxy.py`.
```python
import os, socket, sys, threading, time
PAUSE = sys.argv[1]; LISTEN = ('127.0.0.1', 19042); UP = ('127.0.0.1', 9042)
def pump(src, dst, pausable):
    try:
        while True:
            while pausable and os.path.exists(PAUSE):
                time.sleep(0.01)
            d = src.recv(65536)
            if not d: break
            dst.sendall(d)
    except OSError: pass
    finally:
        for s in (src, dst):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(LISTEN); srv.listen(16)
while True:
    c, _ = srv.accept(); u = socket.create_connection(UP)
    threading.Thread(target=pump, args=(c, u, False), daemon=True).start()
    threading.Thread(target=pump, args=(u, c, True), daemon=True).start()
```
2. **Client:** write `$WORK/probe.py`.
```python
import os, sys, time, subprocess
from cassandra.cluster import Cluster
mode, K, WORK = sys.argv[1], int(sys.argv[2]), os.environ['WORK']
c = Cluster(['127.0.0.1'], port=19042, protocol_version=5, compression=False, idle_heartbeat_interval=0)
s = c.connect()
if mode == 'setup':
    s.execute("CREATE KEYSPACE IF NOT EXISTS o124 WITH replication={'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS o124.t (k int PRIMARY KEY, v blob)")
    ins = s.prepare("INSERT INTO o124.t (k, v) VALUES (?, ?)")
    for k in range(8): s.execute(ins, (k, os.urandom(8 << 20)), timeout=60)
    print('setup done'); c.shutdown(); sys.exit(0)
print('pool hosts:', [str(h.endpoint) for h in s.get_pool_state()])   # must be 127.0.0.1:19042 only
for k in range(K): assert len(s.execute("SELECT v FROM o124.t WHERE k=%s", (k,), timeout=60).one().v) == 8 << 20
sample = lambda tag: subprocess.run([os.path.join(WORK, 'sample.sh'), tag], check=False)
sample('baseline')
open(os.path.join(WORK, 'pause'), 'w').close()
futs = [s.execute_async("SELECT v FROM o124.t WHERE k=%s", (k,), timeout=120) for k in range(K)]
for i in range(10): time.sleep(2); sample('paused-%02d' % i)
os.remove(os.path.join(WORK, 'pause'))
sizes = [len(f.result().one().v) for f in futs]; print('result sizes', sizes)
time.sleep(10); sample('released'); c.shutdown()
```
3. **Sampler:** write `$WORK/sample.sh` and make it executable (`chmod +x`).
```bash
#!/bin/bash
cd $WORK/src; b="org.apache.cassandra.metrics:type=BufferPool,scope=networking"
echo "== $1 $(date +%s.%N)"
for n in UsedSize Size OverflowSize; do echo "$n $(bin/nodetool sjk mx -b "$b,name=$n" -mg -f Value 2>/dev/null | tail -1)"; done
jcmd $(cat $WORK/cassandra.pid) VM.native_memory summary | grep -E '^-? *Other'
ss -tmn '( sport = :9042 )' | awk 'NR>1{print "srvSendQ", $3}'
ss -tmn '( dport = :9042 )' | awk 'NR>1{print "proxyRecvQ", $2}'
```
4. **Run M17, K = 8.**
   - Start: `cd $WORK/src && bin/cassandra -p $WORK/cassandra.pid > $WORK/node.out 2>&1`. Wait until `bin/nodetool status` shows `UN`.
   - Start the proxy: `python3 $WORK/proxy.py $WORK/pause & echo $! > $WORK/proxy.pid`.
   - Load data: `python3 $WORK/probe.py setup 8`, then `bin/nodetool flush o124`.
   - Probe: `python3 $WORK/probe.py probe 8 | tee $WORK/cluster-M17-K8.txt`.
   - Check that `system.log` contains `Global buffer pool limit is 128.000MiB for networking` (`BufferPools.java:48-52`).
5. **Workload control (M17, K = 4):** `python3 $WORK/probe.py probe 4 | tee $WORK/cluster-M17-K4.txt`.
6. **Stop the node and proxy:** `kill $(cat $WORK/cassandra.pid)`; wait for exit (`while kill -0 $(cat $WORK/cassandra.pid) 2>/dev/null; do sleep 1; done`); `kill $(cat $WORK/proxy.pid)`.
   - *Amendment 2026-11-25 (stage-4 runbook defect D2; B3f/B3g unchanged):* the JVM deletes the pidfile (`deleteOnExit`) at the **start** of shutdown, so `while kill -0 $(cat $WORK/cassandra.pid)` ends at once while the node is still shutting down and the next start finds ports 7000/7199 busy. Read the pid once after start (`cp $WORK/cassandra.pid $WORK/node.pid`) and wait on that copy: `NP=$(cat $WORK/node.pid); kill $NP; while kill -0 $NP 2>/dev/null; do sleep 1; done`. The same applies to steps 7 to 9 and B4.
7. **Positive control (M17, cap 16 MiB):** set `networking_cache_size: 16MiB`, restart node and proxy, and run probe 8 into `$WORK/cluster-M17-cache16.txt`. The data is still on disk, so setup is not needed. Stop the node and proxy, then set `networking_cache_size` back to `128MiB`.
8. **M16:** stop everything, edit line 41 to `1 << 16`, `ant clean jar` (the data directory survives `ant clean`), restart node and proxy, probe 8 into `$WORK/cluster-M16-K8.txt`, stop.
9. **M15:** do the same with `1 << 15`, into `$WORK/cluster-M15-K8.txt`, then stop.
10. **Cleanup:** see B4.

**B3f. Predictions.**
- Let ΔU = peak paused `UsedSize` − baseline `UsedSize`, and B_k = srvSendQ + proxyRecvQ at that sample. Let R = K × 8,388,617 (67,108,936 at K = 8).

| Run | Prediction |
|---|---|
| M17, K = 8 | ΔU ≈ R − B_k, within ±5%, ≥ 50 MB; plateau flat across the paused samples (±2%) |
| M16, K = 8 | ΔU within ±5% of the M17 value |
| M15, K = 8 | ΔU within ±5% of the M17 value |
| M17, K = 4 | ΔU ≈ ½ × (M17 K = 8) + (B_k difference), i.e. ≈ 33.5 MB − B_k |
| M17, cache 16 MiB | `Size − OverflowSize` ≤ 16,777,216 throughout; `OverflowSize` rises by ≈ ΔU − 16 MiB; ΔU itself still ≈ R − B_k |
| All | after release, `UsedSize` back to baseline ± 1 MiB; all `result sizes` = 8,388,608 |

- NMT `Other committed` rises by at least ΔU during the pause and is similar across M17/M16/M15 (±10%; Netty arenas add noise).
- **What would show the claim wrong:**
  - ΔU(M15) ≤ 0.6 × ΔU(M17), or ΔU proportional to `MAX_SIZE`;
  - ΔU ≈ K × `MAX_SIZE` (~1 MiB), meaning the server only ever holds one frame per response.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| ΔU ≈ R − B_k and equal (±5%) at M17/M16/M15; ΔU halves at K = 4; the cache-16 MiB run caps pooled `Size` at 16 MiB | **Claim confirmed:** usage is flat across the constraint while the positive controls move it |
| ΔU scales with `MAX_SIZE`, or stays ≈ K × `MAX_SIZE` | **Claim refuted:** the constant bounds real off-heap usage |
| ΔU ≈ 0 at all runs, or K = 4 vs K = 8 gives no change | Workload did not hold frames (proxy not in path, or the kernel absorbed everything): **not confirmed**. Check `pool hosts` and B_k |
| cache-16 MiB run shows pooled `Size` > 16 MiB | Instrument or config problem (wrong yaml, wrong MBean): **not confirmed** until fixed |
| Results ≠ 8 MiB, or timeouts | Run invalid; repeat with a shorter pause |

**B3h. Controls.**
- **Path checks:** the `pool hosts` line must show only `127.0.0.1:19042`, so the driver went through the proxy. `ss` must show a single client connection on 9042, from the proxy.
  - *Amendment 2026-11-25 (stage-4 audit, A3; B3g unchanged):* the driver's control connection also goes through the proxy, so `ss` shows **two** server-side connections on 9042, both from the proxy (control connection and the one pool connection). B_k is summed over both.
- **Baseline:** taken after warm-up, so chunk-cache and pool warming are excluded.
- **Kernel buffer:** B_k is measured, not assumed, and subtracted.
- **Positive controls:** K = 4 vs K = 8 (usage follows load), and `networking_cache_size` 16 MiB (a known cap binds on the same pool).
- **Same everything else:** data, heap, yaml and workload are identical across M values; only line 41 changes.
- **Stale-build check:** `unzip -p $WORK/src/build/apache-cassandra-5.0.9-SNAPSHOT.jar org/apache/cassandra/transport/Flusher.class | strings` is not reliable, so rerun the B2 test after each `ant clean jar` and check that `MAX_FRAMED_PAYLOAD_SIZE` is printed (adjust the jar name to whatever `ls build/*.jar` shows).

**B4. Risks and cleanup.**
- **Disk:** the source copy and build take about 2 GiB in `$WORK` (local disk); data is about 70 MiB plus the commit log (≤ 2 × 32 MiB segments). Nothing goes to shared storage.
- **Processes:** after each tier run:
  - `pgrep -f CassandraDaemon`, `pgrep -f proxy.py` and `pgrep -f FrameMaxSizeProbeTest` must return nothing;
  - stop anything left with `kill $(cat $WORK/cassandra.pid) $(cat $WORK/proxy.pid)` and, if needed, `kill -9` on the remaining pids;
  - `ss -ltn` must show 9042/7000/7199/19042 free.
- **Temporary files:** remove `$WORK/pause` if a run aborted. Otherwise the next proxy run starts paused.
- **Removal:** when done, `rm -rf $WORK` after copying the `*.txt` readings out. Never edit or build in `~/cassandra-5.0.9`, which stays pristine.

## C. Sources read

- src/java/org/apache/cassandra/net/FrameEncoder.java
- src/java/org/apache/cassandra/net/FrameEncoderCrc.java
- src/java/org/apache/cassandra/net/FrameEncoderLZ4.java
- src/java/org/apache/cassandra/net/FrameEncoderUnprotected.java (grep)
- src/java/org/apache/cassandra/net/FrameDecoderCrc.java (grep)
- src/java/org/apache/cassandra/net/FrameDecoderLZ4.java (grep)
- src/java/org/apache/cassandra/net/AbstractMessageHandler.java
- src/java/org/apache/cassandra/net/InboundMessageHandler.java (grep)
- src/java/org/apache/cassandra/net/OutboundConnection.java
- src/java/org/apache/cassandra/net/OutboundConnections.java
- src/java/org/apache/cassandra/transport/Flusher.java
- src/java/org/apache/cassandra/transport/CQLMessageHandler.java
- src/java/org/apache/cassandra/transport/SimpleClient.java (grep)
- src/java/org/apache/cassandra/transport/Envelope.java
- src/java/org/apache/cassandra/transport/Message.java
- src/java/org/apache/cassandra/transport/CBUtil.java (grep)
- src/java/org/apache/cassandra/transport/PipelineConfigurator.java (grep)
- src/java/org/apache/cassandra/utils/memory/BufferPool.java
- src/java/org/apache/cassandra/utils/memory/BufferPools.java
- src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/Config.java (grep)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep)
- conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm11-server.options (grep)
- bin/cqlsh.py
- build.xml (grep)
- doc/native_protocol_v5.spec
- test/unit/org/apache/cassandra/transport/ (file list, grep for MAX_SIZE uses)
- https://issues.apache.org/jira/browse/CASSANDRA-15299 (background only)

## D. Stage-4 feedback

**2026-11-25, stage 4 run 1 (Jingsong; node `pc72`, x86_64; results `results/frameencoder_payload_max_size-payload-max_size--autonomous.md`).**
- **Unit tier: Confirmed — does not cap.** At `MAX_SIZE` = 131072 / 65536 / 32768 an 8 MiB response became 65 / 129 / 257 frames
  (maxData 131054 / 65518 / 32750, as B2f), while the networking-pool delta with every frame held was 8,390,656 / 8,392,704 /
  8,394,752 B (0.05% spread; every B2f figure matched exactly). S = 4 MiB halved it (4,194,912 / 4,196,352 / 4,198,400 B).
  releasedDelta 0; the literal 128 KiB check rejected 131072 and accepted 131071 at all three values.
- **Cluster tier: Confirmed — does not cap.** With the client paused, K = 8 × 8 MiB responses held ΔU = 57,948,160 /
  57,438,208 / 57,878,528 B of networking-pool memory at M17 / M16 / M15 (M16 and M15 are 0.991 and 0.999 of M17), each within
  0.06% of R − B_k. K = 4: ΔU = 23,861,248 B (1.003 × R − B_k). With `networking_cache_size: 16MiB` the pooled part stopped at
  exactly 16,777,216 B and the remainder went to overflow (+44,823,888 B), with ΔU unchanged (1.001 × R − B_k). Gap: NMT `Other`
  rose by ≈ ΔU in the M16/M15 runs but not in the M17 K = 8 run, which followed the 64 MiB data load in the same JVM (see results §4.2).
- **Outcome class: true negative.** Runbook defects D1 (B2e PROBE extraction) and D2 (B3e step 6 pidfile wait) were fixed by the
  dated amendments above; audit amendments A1–A3 are environment-only. B2f/B2g/B3f/B3g are unchanged.
- **Side observation, outside this constraint:** after 8 inbound 8 MiB INSERTs the networking pool's `OverflowSize` stayed at
  67,113,472 B (64 MiB + 4.5 KiB) for the rest of the JVM's life, and once read −2,052 B after release in the 16 MiB run; this
  looks like an overflow-accounting mismatch on the inbound large-message path, and may be worth a case of its own.
