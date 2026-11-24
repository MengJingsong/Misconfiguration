# highWaterMark (per-writer in-flight flush bound of `AsyncChannelOutputPlus`): verification solution  <!-- file: cases/highWaterMark-waitForSpace-flushing--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity-set place, not an `if`), **linked**: [`AsyncChannelOutputPlus.java:140`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncChannelOutputPlus.java#L140), `waitUntilFlushed(max(lowWaterMark, wakeUpWhenFlushing), lowWaterMark);` in `waitForSpace`. The comparison it sets up is [`AsyncChannelOutputPlus.java:156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncChannelOutputPlus.java#L156) `if (flushed < wakeUpWhenFlushed)`. |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`. Before a writer hands a buffer to Netty, `waitForSpace` blocks it until the bytes it has handed over but Netty has not yet completed (`flushing - flushed`) are at most `max(lowWaterMark, highWaterMark - bytesToWrite)`. After the write, the in-flight bytes are therefore at most `max(highWaterMark, lowWaterMark + bytesToWrite)`. On the streaming path the off-heap buffer is taken from the networking `BufferPool` only after this check passes (`AsyncStreamingOutputPlus.java:123-125`), so a slow or stalled peer pins about 64 KiB of off-heap memory per stream (Netty default marks, 64 KiB chunks). Without the check it could pin a whole SSTable section. |
| Ground | — |

> Scope note. The bound applies per output stream (one writer thread per `AsyncChannelOutputPlus`). Nothing bounds the node-wide total. It is the number of concurrent streams and large-message deliveries times the per-stream bound. The verification tests the per-stream bound and how that bound shows up in the node's networking pool usage.

## A. Constraint trace

**A1. The constraint.**
- **Name:** `highWaterMark`, with its partner `lowWaterMark`. These are the parameters of `waitForSpace(long bytesToWrite, long lowWaterMark, long highWaterMark)` ([`AsyncChannelOutputPlus.java:134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncChannelOutputPlus.java#L134)), passed through from `beginFlush` (`AsyncChannelOutputPlus.java:95-97`).
- **Kind:** an effective constant. It is not a Cassandra configuration entry. Each caller takes the value from one of these sources:
  - **Streaming, `writeToChannel` (the main memory-carrying path):** the Netty channel's `WriteBufferWaterMark`, copied into fields in the constructor. The fields are first declared at [`AsyncStreamingOutputPlus.java:60-61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java#L60-L61) (`final int defaultLowWaterMark; final int defaultHighWaterMark;`) and assigned at `AsyncStreamingOutputPlus.java:66-68`. They are used at `:124`.
  - **Large internode messages:** the same channel `WriteBufferWaterMark`, read into [`AsyncMessageOutputPlus.java:57-58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncMessageOutputPlus.java#L57-L58) at `:69-71` and used at `:100`.
  - **Throttled zero-copy streaming:** hard-coded `lowWaterMark = 1 << 20`, `highWaterMark = 2 << 20` with 1 MiB batches (`AsyncStreamingOutputPlus.java:165`, used at `:242`).
  - **Unthrottled zero-copy streaming:** `beginFlush(length, 0, length)` (`:221`). The whole file is one flush.
  - **Streaming `doFlush` of the small 8 KiB staging buffer:** `beginFlush(byteCount, 0, Integer.MAX_VALUE)` (`:91`). There is effectively no bound.
- **Default and how it is derived:** neither the outbound internode bootstrap (`OutboundConnectionInitiator.java:192-201`) nor the inbound one (`InboundConnectionInitiator.java:108-111,168-175`) sets `ChannelOption.WRITE_BUFFER_WATER_MARK`. Those channels, which also carry streaming, keep Netty's `DefaultChannelConfig` default `WriteBufferWaterMark.DEFAULT`, which is **low = 32 KiB and high = 64 KiB** in Netty 4.1.130.Final (`.build/parent-pom-template.xml:749`). The one place Cassandra sets the option is the native-transport server (`PipelineConfigurator.java:139`, 8 KiB/32 KiB). That is a different channel type and does not reach these classes.
- **Unit:** bytes.
- **How it can be set:** it cannot be set by an operator. There is no yaml key, `-D` property or JMX attribute. `OutboundConnectionSettings.withNettyBufferBounds(WriteBufferWaterMark)` (`OutboundConnectionSettings.java:252-259`) ignores its argument, so it is a no-op. The similarly named `flushLowWaterMark`/`flushHighWaterMark` (`1 << 15`, `1 << 16`, `OutboundConnectionSettings.java:104`) belong to the event-loop small-message delivery (`OutboundConnection.java:854,871`), not to this class. Changing the value needs a code change (setting the channel option, or the patch in B3a) and a restart.

**A2. What it caps.**
- **Quantity compared:** the writer's bytes in flight, `flushing - flushed`. `flushing` is the bytes the writer has begun flushing (`AsyncChannelOutputPlus.java:63`, advanced at `:141`). `flushed` is the bytes whose Netty promise has completed, successfully or not (`:65`, advanced by the event loop in `releaseSpace`, `:184-187`). The operand named in the stem is `flushing`.
- **Resource:** off-heap memory. On the streaming `writeToChannel` path each in-flight chunk is a direct `ByteBuffer` from `BufferPools.forNetworking()` (`AsyncStreamingOutputPlus.java:58,125`). It is held in Netty's `ChannelOutboundBuffer` until the socket accepts it, and the promise completes at that point. The pool is off-heap, sized by `networking_cache_size` (default 128 MiB, `BufferPools.java:44-45`); past that size it falls back to unpooled `allocateDirect` (`BufferPool.java:233-239`). On the large-message path each in-flight chunk is a `FrameEncoder.Payload` of up to 32 KiB (`OutboundConnection.java:939,977`; `AsyncMessageOutputPlus.java:73,80`). On the zero-copy paths the in-flight objects are `FileRegion`s, which are file references with no Java memory behind them.
- **Not capped:** kernel socket buffers, which count as "flushed" once Netty has written into them. The receiving side is also outside this bound.

**A3. Mechanism.**
1. A writer that wants to send `b` bytes calls `beginFlush(b, low, high)` (`AsyncChannelOutputPlus.java:95`), which first calls `waitForSpace` (`:97`).
2. `waitForSpace` computes `wakeUpWhenFlushing = high - b` (`:139`). Then, at **the given line** [`AsyncChannelOutputPlus.java:140`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncChannelOutputPlus.java#L140), it calls `waitUntilFlushed(max(low, high - b), low)`. This is where the capacity is set: the writer may continue once at most `max(low, high - b)` bytes are still in flight.
3. `waitUntilFlushed` turns that into a target count, `wakeUpWhenFlushed = flushing - max(low, high - b)` (`:155`), and checks [`if (flushed < wakeUpWhenFlushed)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncChannelOutputPlus.java#L156) (`:156`).
   - **Limit reached** (in flight > `max(low, high - b)`): `parkUntilFlushed` (`:157`, `:167-177`) registers the thread and its signal point `flushing - low`, then calls `LockSupport.park()` in a loop until `flushed >= wakeUpWhenFlushed` (`:174-175`). The event loop's `releaseSpace` unparks the thread once `flushed >= signalWhenFlushed` (`:189-191`), that is, once in flight has drained to `low`. The writer then rechecks the wake-up condition.
   - **Under the limit:** the writer does not wait.
   - **Both outcomes:** `propagateFailedFlush` (`:158`, `:194-203`) throws `FlushException` if an earlier flush failed. Then `flushing += b` (`:141`). Only after `beginFlush` returns does the streaming path take the buffer from the pool (`AsyncStreamingOutputPlus.java:124-125`) and write it (`:143`).
4. **Resulting bound:** after the increment, in flight is at most `max(low, high - b) + b = max(high, low + b)`. With equal chunks of size `b`, in flight is always a multiple of `b`. The peak reached during a stall is therefore exactly `P = b * (floor(max(low, high - b) / b) + 1)`. The class comment at `:136-138` says callers should keep `b <= high - low` but the code must work when they do not; the `low + b` term is that overshoot.
5. **Release:** the listener installed in `beginFlush` (`:99-120`) calls `releaseSpace(b)` on success (`:103`). On failure it records `flushFailed` and releases everything outstanding (`:113-114`), so a failed channel never leaves the writer parked.
6. **Bypasses and overshoots:**
   - Streaming `doFlush` uses `(0, Integer.MAX_VALUE)` (`AsyncStreamingOutputPlus.java:91`). The small staging buffers (8 KiB, `:75`, used for headers and `write()` calls) are never throttled, but their bytes do count in `flushing`, so they delay the next `writeToChannel`. At most one such buffer is outstanding before a chunk's check, so it adds at most 8 KiB.
   - Unthrottled zero-copy (`:221`) puts the whole file in flight at once. These are `FileRegion`s, with no Java memory involved.
   - Large messages: `AsyncMessageOutputPlus` fills its 32 KiB payload before `doFlush` calls `beginFlush` (`AsyncMessageOutputPlus.java:85-102`), so one more filled buffer is held beyond the bound. That is at most `max(64K, 32K+32K) + 32K = 96 KiB` per message stream.
   - The bound is per instance. N concurrent streams or large-message deliveries hold N times the bound.

**A4. Other consumers.** Other users of the same off-heap networking pool fall outside this constraint:
- the inbound frame decoders and receive-side streaming (`AsyncStreamingInputPlus`);
- the small-message internode path, which is bounded separately by the `flushLowWaterMark`/`flushHighWaterMark` settings (`OutboundConnection.java:854,871`) and the application send queues (`internode_application_send_queue_*`);
- the 8 KiB streaming staging buffers;
- `CassandraStreamWriter`'s read buffer (`CassandraStreamWriter.java:155`).

Outside the pool, the kernel socket send and receive buffers hold data the writer already counts as flushed. On the zero-copy paths, page cache holds file data.

**A5. Evidence beyond the source.**
- Netty `WriteBufferWaterMark` API docs (default 32 KiB low / 64 KiB high): https://netty.io/4.1/api/io/netty/channel/WriteBufferWaterMark.html
- CASSANDRA-15066 (the internode messaging rewrite that introduced `AsyncChannelOutputPlus`): https://issues.apache.org/jira/browse/CASSANDRA-15066. The source copy has no `.git`, so the history was not checked locally.
- Existing tests, `test/unit/org/apache/cassandra/net/AsyncStreamingOutputPlusTest.java` and `AsyncMessageOutputPlusTest.java`, use an `EmbeddedChannel`. Its event loop is the writer thread, and the tests write only tens of bytes, so they never reach the parking branch. No existing test covers the bound.

## B. Verification solution

**B1. Claim under test.** For one `AsyncChannelOutputPlus` writer sending equal chunks of `b` bytes to a peer that has stopped reading, the in-flight byte count `flushing - flushed` and the networking-pool off-heap memory it pins stop growing at `P = b * (floor(max(low, high - b) / b) + 1)` (≤ `max(high, low + b)`, plus at most one 8 KiB staging buffer). With default marks and 64 KiB chunks, P = 64 KiB. The plateau scales with `high` (and `low`) and not with the amount of data offered. The claim is wrong if the plateau exceeds that bound, or tracks the offered volume, while the knob is finite.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` must report 11) and Apache Ant 1.10+.
- Copy the source to local disk; never build in the shared tree:
  ```
  WORK=/mydata/$USER-s4/o180     # any local disk with >= 10 GiB free
  mkdir -p $WORK && rsync -a ~/cassandra-5.0.9/ $WORK/src/
  cd $WORK/src && ant jar build-test
  ```
- Test source: `$WORK/src/test/unit/org/apache/cassandra/net/S4WaterMarkCapTest.java` (B2e). It is placed in package `org.apache.cassandra.net` so it can construct `AsyncStreamingOutputPlus` and read `AsyncChannelOutputPlus.flushed` through reflection.
- JVM options: those from `ant testsome` (the `build.xml` defaults). No extra options are needed.

**B2b. Knobs.**
- The client channel's `ChannelOption.WRITE_BUFFER_WATER_MARK = new WriteBufferWaterMark(low, high)`. `AsyncStreamingOutputPlus` reads it in its constructor (`:66-68`).
- The chunk size `b`.
- All are set in the test code, with these values:

| id | low | high | b | why | predicted P |
|---|---|---|---|---|---|
| W1 | 8 KiB | 16 KiB | 64 KiB | marks below one chunk | 64 KiB |
| W2 | 32 KiB | 64 KiB | 64 KiB | **production default** | 64 KiB |
| W3 | 256 KiB | 512 KiB | 64 KiB | high branch | 512 KiB |
| W4 | 1 MiB | 2 MiB | 64 KiB | the zero-copy-throttled constants | 2 MiB |
| W5 | 4 MiB | 16 MiB | 64 KiB | large | 16 MiB |
| W6 | 96 KiB | 104 KiB | 16 KiB | low branch (low ≥ high − b), overshoots high | 112 KiB |
| C | 0 | 2147483647 | 64 KiB | **positive control:** no effective bound | ≈ 64 MiB (all offered) |

**B2c. Workload.**
- Each run writes N = 64 MiB through `out.writeToChannel(...)`: 1024 chunks of 64 KiB, or 4096 chunks of 16 KiB for W6. A no-op rate limiter is used (`isRateLimited() == false`). Each chunk is taken with `alloc.get(b)` and filled to `b`, which uses the real pool path at `:123-125`.
- The peer is a Netty `NioServerSocketChannel` on `127.0.0.1:0` with `option(SO_RCVBUF, 4096)` and `childOption(AUTO_READ, false)`, so it never reads. The client uses `SO_SNDBUF = 4096`. Together the kernel absorbs at most about 20–40 KiB.
- Arithmetic: N = 64 MiB is 4× the largest finite P (16 MiB), so every finite knob is driven past its bound. The control would grow to about 64 MiB with no bound.

**B2d. Observables and instruments.** A sampler thread in the test polls every 1 ms:
- `inflight = out.flushed() - flushedField.getLong(out)`. `out.flushed()` returns `flushing` (`:210-214`). `flushedField` is the private volatile `AsyncChannelOutputPlus.flushed`, read through reflection. This is the check's own operand.
- `pool = BufferPools.forNetworking().usedSizeInBytes()` (`BufferPool.java:282-285`), as a delta from a baseline taken before the run.
- The writer thread's `Thread.State` and whether its stack contains `parkUntilFlushed`.
- `out.flushed()`, to tell when the writer is making progress.

Peaks of `inflight` and of `pool − baseline` are recorded. The kernel-buffered bytes cannot be observed directly, but they count as flushed and are bounded by the small socket buffers.

**B2e. Procedure.**
1. Create the test file with this behaviour (complete code is left to the executor; every element is listed):
   - `static { DatabaseDescriptor.daemonInitialization(); }`
   - `run(low, high, b, N)`:
     - Create `NioEventLoopGroup(2)`.
     - Server: `ServerBootstrap` with `NioServerSocketChannel`, `.option(SO_RCVBUF, 4096)`, `.childOption(AUTO_READ, false)`, and a child handler that stores the accepted channel in an `AtomicReference` and releases any message it reads (`ReferenceCountUtil.release(msg)`). Bind to `127.0.0.1:0`.
     - Client: `Bootstrap` with `NioSocketChannel`, `.option(WRITE_BUFFER_WATER_MARK, new WriteBufferWaterMark(low, high))`, `.option(SO_SNDBUF, 4096)`, `.option(TCP_NODELAY, true)` and an empty handler. `connect().sync()`.
     - `out = new AsyncStreamingOutputPlus(clientChannel)`.
     - Writer thread: `for i < N/b: out.writeToChannel(alloc -> { ByteBuffer bb = alloc.get(b); bb.position(b); bb.flip(); }, NO_LIMIT)`.
     - Main thread: sample as in B2d until either (a) the writer has finished (control), or (b) the writer is `WAITING` in `parkUntilFlushed` and `out.flushed()` has not changed for 500 ms. Time out after 60 s. Record `peakInflight` and `peakPoolDelta`.
     - Release the peer with `child.config().setAutoRead(true)`, join the writer, call `out.close()`, close both channels, and `group.shutdownGracefully().sync()`.
     - Print one line: `S4UNIT id low high b N peakInflight peakPoolDelta writerParked(yes/no)`.
   - One `@Test` per row of B2b, each calling `run` and then asserting the predictions of B2f.
2. `cd $WORK/src && ant testsome -Dtest.name=org.apache.cassandra.net.S4WaterMarkCapTest`
3. Collect the `S4UNIT` lines from `build/test/output/TEST-org.apache.cassandra.net.S4WaterMarkCapTest.xml` (system-out) into `$WORK/unit-results.txt`.
4. Repeat the whole test three times, to check that peaks are deterministic (they should be identical).

**B2f. Predictions** (stated before any run):
- W1 to W6 (`peakInflight`):
  - `P ≤ peakInflight ≤ P + 8 KiB`, with P from the B2b table: 64 KiB, 64 KiB, 512 KiB, 2 MiB, 16 MiB and 112 KiB. The + 8 KiB is only possible if a staging buffer is outstanding; in this workload it should be exactly P.
  - The writer is parked at the plateau.
  - `peakPoolDelta` is within `P ± 128 KiB`; the pool rounds up to 2 KiB allocation units, and one 128 KiB chunk of slack is allowed.
  - Peaks rise monotonically from W2 through W3, W4 and W5.
- C: `peakInflight ≥ 63 MiB`, `peakPoolDelta ≥ 63 MiB`, and the writer is never parked (it finishes all 1024 writes while the peer reads nothing).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| W1–W6 plateau at P (≤ P + 8 KiB) with the writer parked, the pool delta ≈ P, and C reaches ≈ 64 MiB | Claim confirmed: the check bounds in-flight bytes and the pooled memory they pin, and the bound follows `high`/`low`. |
| Any of W1–W6 has `peakInflight > max(high, low + b) + 8 KiB`, or grows toward 64 MiB | **Claim wrong:** the check does not bound the operand. |
| `peakInflight` is within the bound but `peakPoolDelta` ≫ P (for example ≥ 4 × P + 1 MiB) | The check bounds its operand, but memory is held elsewhere (buffers not returned on completion): the memory claim fails. |
| W3, W4 and W5 all plateau at the same value | The plateau comes from something else (for example kernel buffers), not the knob: the claim is not confirmed. |
| C stays small (< 63 MiB) or the writer parks in C | The stall is not effective (the peer is reading, or buffers are large), so the bound was never tested: not confirmed. |
| W6 plateaus at 96 KiB instead of 112 KiB | The low-branch overshoot is not as traced: correct A3 step 4. |

**B2h. Controls.**
- **C (positive control):** the same workload, peer and stall with no effective bound. It shows the stall really makes usage grow with the offered data.
- **Parked writer:** confirming the writer is parked in `parkUntilFlushed` ties each plateau to this check rather than to the producer stopping.
- **Pool baseline:** measured per run after `daemonInitialization` and before connecting.
- **Repeats:** three repeats rule out timing flukes.
- **Small socket buffers:** the fixed `SO_SNDBUF`/`SO_RCVBUF` keep the kernel's share to tens of KiB, so it cannot mask a 64 KiB bound.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host with JDK 11 and Ant, running two nodes on `127.0.0.1` and `127.0.0.2`. Loopback aliases work by default on Linux. All data lives under `$WORK` on local disk with ≥ 10 GiB free.
- Patch the local copy `$WORK/src`, never the shared tree, because the value cannot be set otherwise (A1):
  1. Make the knob settable. In `AsyncStreamingOutputPlus` constructor lines 67-68, replace the assignments with:
     ```java
     this.defaultLowWaterMark  = Integer.getInteger("s4.stream.lowWaterMark",  waterMark.low());
     this.defaultHighWaterMark = Integer.getInteger("s4.stream.highWaterMark", waterMark.high());
     ```
  2. Add the operand instrument in `AsyncChannelOutputPlus`. Add the fields `protected long s4PeakInFlight, s4PoolUsedAtPeak;` (written only by the writer). In `waitForSpace` after line 141 add:
     ```java
     long s4 = flushing - flushed;
     if (s4 > s4PeakInFlight) { s4PeakInFlight = s4; s4PoolUsedAtPeak = org.apache.cassandra.utils.memory.BufferPools.forNetworking().usedSizeInBytes(); }
     ```
  3. In `AsyncStreamingOutputPlus` override `close()`:
     ```java
     @Override public void close() throws IOException {
         try { super.close(); }
         finally { logger.info("S4 stream out to {} low={} high={} peakInFlight={} poolUsedAtPeak={}",
                               channel.remoteAddress(), defaultLowWaterMark, defaultHighWaterMark, s4PeakInFlight, s4PoolUsedAtPeak); }
     }
     ```
     The anonymous subclass in `NettyStreamingChannel.java:132-146` calls `super.close()`, so this runs once per file sent (`StreamingMultiplexedChannel.java:318`).
- Build with `cd $WORK/src && ant jar`. Make two node directories: `rsync -a $WORK/src/ $WORK/n1/` and `$WORK/n2/` (or run both nodes from one build, each with its own `CASSANDRA_CONF`).
- `cassandra.yaml` for each node (the second value is for n2):
  - `cluster_name: s4`, `num_tokens: 16`
  - `listen_address` / `rpc_address`: `127.0.0.1` / `127.0.0.2`
  - `seed_provider` seeds: `127.0.0.1`
  - `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory`: under `$WORK/nX/data/...`
  - `stream_entire_sstables: false` (forces `CassandraCompressedStreamWriter` to use `writeToChannel` with 64 KiB chunks: `CassandraCompressedStreamWriter.java:43,89`)
  - `stream_throughput_outbound: 24MiB/s` (the default, kept explicit; it sets the producer rate in the control)
  - `phi_convict_threshold: 12` (so a 6 s stall does not convict the peer)
  - `auto_snapshot: false`
- `cassandra-env.sh` for each node: `JMX_PORT=7199` / `7299`. Set `MAX_HEAP_SIZE=2G` and `HEAP_NEWSIZE=400M`; `MaxDirectMemorySize` then defaults to 2 GiB, room for the control.

**B3b. Knobs.** The `-Ds4.stream.lowWaterMark` and `-Ds4.stream.highWaterMark` properties, passed through `JVM_EXTRA_OPTS` when starting both nodes. Each change needs a restart.

| id | low | high | why | predicted per-stream peak P (b = 64 KiB) |
|---|---|---|---|---|
| K0 | unset (32 KiB) | unset (64 KiB) | production default | 64 KiB (≤ 72 KiB) |
| K1 | 1048576 | 4194304 | moderate | 4 MiB (≤ 4 MiB + 8 KiB) |
| K2 | 8388608 | 33554432 | large, clearly visible in the pool | 32 MiB (≤ 32 MiB + 8 KiB) |
| C | 0 | 2147483647 | **positive control:** no bound | ≈ rate × stall ≈ 24 MiB/s × 6 s ≈ 144 MiB, minus ≤ 10 MiB of kernel buffers |

**B3c. Workload.**
- Keyspace `s4`, `SimpleStrategy` with RF 2. Load it with `cassandra-stress` against node 1:
  ```
  tools/bin/cassandra-stress write n=1000000 -col size=FIXED(1024) n=FIXED(1) -schema "replication(factor=2)" keyspace=s4 -rate threads=32 -node 127.0.0.1
  ```
  This gives about 1 GiB per node. Then `nodetool flush` on both nodes.
- Streaming is driven by `nodetool -p 7299 rebuild -ks s4 datacenter1` on node 2. Node 2 then pulls all its ranges for `s4` from node 1, so node 1 is the sender.
- Arithmetic: about 1 GiB at 24 MiB/s is about 43 s of streaming. A 6 s stall (`SIGSTOP` of node 2) offers about 144 MiB to the sender, which is above every finite P (largest 32 MiB) and below the 2 GiB direct-memory limit.
- Each run takes about 2 min. After each run, `nodetool -p 7299 compact s4` folds the duplicated data on node 2 back down.

**B3d. Observables and instruments.**
- **Operand:** the `S4 stream out` log lines in node 1's `$WORK/n1/logs/system.log`. Take the max `peakInFlight` and `poolUsedAtPeak` per run.
- **Actual resource:** the node 1 networking-pool off-heap usage, metric `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize`. Sample it about every 1 s:
  ```
  nodetool -p 7199 sjk mx -b org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize -mg -f Value
  ```
  `OverflowSize` (same bean pattern, `name=OverflowSize`) shows any spill past the 128 MiB pool. As a cross-check, sample `java.nio:type=BufferPool,name=direct` `MemoryUsed` the same way.
- **Writer state:** `jstack <node1 pid>` 4 s into the stall. Look for the `Stream-Out`/streaming thread in `AsyncChannelOutputPlus.parkUntilFlushed`.
- **Progress:** `nodetool -p 7199 netstats`, which shows bytes sent.
- Not observable directly: kernel socket buffer occupancy (`ss -tmi` on the streaming port gives an approximate `skmem`; record it once per run).

**B3e. Procedure.** For each knob in the order K0, K1, K2, C, then K0 again:
1. Start the nodes: `JVM_EXTRA_OPTS="<-D props or empty>" CASSANDRA_CONF=$WORK/nX/conf $WORK/nX/bin/cassandra -p $WORK/nX.pid`. Start node 1, wait for `nodetool -p 7199 status` to show UN, then start node 2 and wait for both to show UN. On the first run only, load the data (B3c).
2. Take a baseline: three `UsedSize` samples on node 1, 1 s apart. Record their median.
3. Start `nodetool -p 7299 rebuild -ks s4 datacenter1 &`. Poll `nodetool -p 7199 netstats` until the bytes sent increase (streaming has started), then wait a further 3 s.
4. `kill -STOP $(cat $WORK/n2.pid)`. Sample node 1's `UsedSize` and `OverflowSize` every 1 s for 6 s, and run `jstack` at t = 4 s. Then `kill -CONT $(cat $WORK/n2.pid)` (**always**, also on any script error, via `trap`).
5. Wait for the rebuild to finish. Collect the `S4 stream out` lines from node 1's log.
6. Run `nodetool -p 7299 compact s4`. Stop both nodes (`kill $(cat $WORK/nX.pid)`) and confirm with `pgrep -f CassandraDaemon` that none is left.

**B3f. Predictions** (before any run):
- **K0:**
  - Max `peakInFlight` is 64 KiB (≤ 72 KiB).
  - `UsedSize` during the stall exceeds the baseline by less than 4 MiB; this is noise from other pool users, A4.
  - `jstack` shows the stream writer in `parkUntilFlushed`.
- **K1:** max `peakInFlight` is 4 MiB (≤ 4 MiB + 8 KiB). The `UsedSize` rise is ≤ 8 MiB.
- **K2:**
  - Max `peakInFlight` is 32 MiB (≤ 32 MiB + 8 KiB).
  - The `UsedSize` rise is between 28 MiB and 40 MiB.
  - The writer is parked.
- **C:**
  - Max `peakInFlight` is ≥ 100 MiB, about 134–144 MiB.
  - The `UsedSize` rise is ≥ 100 MiB. `OverflowSize` > 0 is likely, because the 128 MiB pool is exceeded.
  - The writer is not parked in `parkUntilFlushed`; if it waits at all, it waits in the rate limiter.
- **Overall:** the `UsedSize` rise orders as K0 ≤ K1 < K2 < C, and the second K0 run repeats the first.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peaks match P for K0/K1/K2, the `UsedSize` rise tracks P, C rises ≥ 100 MiB, and the writer is parked under the K values | Claim confirmed on a real node: the per-stream off-heap usage follows the marks. |
| Under K0 or K2, `peakInFlight` or the `UsedSize` rise approaches the C value (≫ P + 8 KiB) | **Claim wrong:** the bound does not govern real usage. |
| `peakInFlight` ≤ P but the `UsedSize` rise under K0 ≥ 20 MiB, repeatably | The operand is bounded but other pool users dominate (A4): the cap holds per stream but does not determine the node's usage. Report it as such. |
| C does not rise (≤ 20 MiB) | The stall did not take hold (streaming had finished, entire-SSTable streaming was used, or node 2 was not stopped): not confirmed; repeat the run. |
| No `S4 stream out` lines | The `writeToChannel` path was not used (check `stream_entire_sstables: false`) or the patch is missing: invalid run. |

**B3h. Controls.**
- **C:** the same workload and stall without a bound; this is the positive control.
- **K0 run twice:** rules out drift.
- **Baseline before each stall:** removes steady pool use by gossip and messaging.
- **`jstack` evidence:** ties each plateau to `parkUntilFlushed`.
- **Fixed producer rate:** `stream_throughput_outbound` fixes the producer rate, so the offered volume during the stall is the same in every run.
- **Only the knob changes:** the build, data and yaml are the same in every run.

**B4. Risks and cleanup.**
- **Disk:** about 1 GiB per node, plus up to 1 GiB of duplicates on node 2 per rebuild until it is compacted. Keep everything under `$WORK` on local disk and check `df -h $WORK` stays below 80 %. Nothing goes to shared storage.
- **Processes:**
  - Unit tier: the test shuts down its event loop group, and the forked JUnit JVM exits.
  - Cluster tier: always send `SIGCONT` to node 2 (use a `trap`), stop both nodes after each run and at the end, and run `pgrep -fa CassandraDaemon`, `pgrep -fa cassandra-stress` and `pgrep -fa NodeTool` to confirm nothing remains.
- **Memory:** in the control run, node 1 holds up to about 150 MiB of direct memory, well within 2 GiB.
- **Network:** both nodes use loopback addresses and default ports 7000/9042/7199/7299. Check those ports are free first, and do not run on a host where another Cassandra uses them.
- **Cleanup:** `rm -rf $WORK` at the end, once the results are copied out.

## C. Sources read

- `src/java/org/apache/cassandra/net/AsyncChannelOutputPlus.java`
- `src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java`
- `src/java/org/apache/cassandra/net/AsyncMessageOutputPlus.java`
- `src/java/org/apache/cassandra/net/OutboundConnectionSettings.java` (lines 80-110, 248-262)
- `src/java/org/apache/cassandra/net/OutboundConnection.java` (lines 854-871, 930-995)
- `src/java/org/apache/cassandra/net/OutboundConnectionInitiator.java` (bootstrap options, 192-201)
- `src/java/org/apache/cassandra/net/InboundConnectionInitiator.java` (options, 108-111, 168-175)
- `src/java/org/apache/cassandra/transport/PipelineConfigurator.java` (130-142)
- `src/java/org/apache/cassandra/streaming/async/NettyStreamingChannel.java` (120-150)
- `src/java/org/apache/cassandra/streaming/async/StreamingMultiplexedChannel.java` (318)
- `src/java/org/apache/cassandra/streaming/StreamingDataOutputPlus.java`
- `src/java/org/apache/cassandra/streaming/StreamManager.java` (125-145, 200-216)
- `src/java/org/apache/cassandra/db/streaming/CassandraCompressedStreamWriter.java` (43, 70-120)
- `src/java/org/apache/cassandra/db/streaming/CassandraStreamWriter.java` (50, 85, 140-170)
- `src/java/org/apache/cassandra/db/streaming/CassandraEntireSSTableStreamWriter.java` (85-96)
- `src/java/org/apache/cassandra/utils/memory/BufferPool.java` (128-132, 200-300, 384-480)
- `src/java/org/apache/cassandra/utils/memory/BufferPools.java`
- `src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java`
- `src/java/org/apache/cassandra/service/StorageService.java` (rebuild, 1505-1530)
- `src/java/org/apache/cassandra/tools/nodetool/Sjk.java`
- `test/unit/org/apache/cassandra/net/AsyncStreamingOutputPlusTest.java`
- `test/unit/org/apache/cassandra/net/AsyncMessageOutputPlusTest.java`
- `test/unit/org/apache/cassandra/net/TestChannel.java`
- `conf/cassandra.yaml` (networking_cache_size, streaming section)
- `.build/parent-pom-template.xml` (Netty version), `.build/cassandra-deps-template.xml`, `build.xml` (targets)
- `CHANGES.txt` (searched)
- https://netty.io/4.1/api/io/netty/channel/WriteBufferWaterMark.html
- https://issues.apache.org/jira/browse/CASSANDRA-15066

## D. Stage-4 feedback

none yet
