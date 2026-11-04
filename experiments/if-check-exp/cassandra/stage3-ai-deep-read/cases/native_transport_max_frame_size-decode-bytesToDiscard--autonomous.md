# native_transport_max_frame_size — verification solution  <!-- file: cases/native_transport_max_frame_size-decode-bytesToDiscard--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`Envelope.java:349`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L349) and `src/java/org/apache/cassandra/transport/Envelope.java:436#1` (both `if (bytesToDiscard <= 0)`; one constraint, one case) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code CLI, 2026-10-26 (Band D triage) |
| Estimate | `positive`. Both lines sit in the discard path of `Envelope.Decoder`, which is how `native_transport_max_frame_size` keeps the per-connection inbound buffer from holding a frame above the limit. A frame that declares more than the limit is skipped as it arrives instead of being collected, so the bytes each connection holds before a frame is complete stay at or below about one max frame. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `native_transport_max_frame_size`, a configuration entry
(`DataStorageSpec.IntMebibytesBound`). It is declared at
[`Config.java:285`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L285) with a default of `16MiB`.
The old name `native_transport_max_frame_size_in_mb` still works through `@Replaces`
([`Config.java:284`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L284)). `conf/cassandra.yaml:1044` documents it but leaves it commented
out. Startup validation requires `0 <= bytes <= Integer.MAX_VALUE-1`
([`DatabaseDescriptor.java:619-625`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L619-L625)). The getter is `DatabaseDescriptor.getNativeTransportMaxFrameSize()`,
which returns bytes ([`DatabaseDescriptor.java:3153-3156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3153-L3156)). The decoder copies the value
once into `private static final int MAX_TOTAL_LENGTH` ([`Envelope.java:197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L197)) when the
class loads, so **a change needs a restart**. The setter
`DatabaseDescriptor.setNativeTransportMaxFrameSize(int bytes)` (`:3158-3161`) has no
callers in `src/java` and would not reach the static anyway. It also passes a byte
count to the `IntMebibytesBound(long mebibytes)` constructor, which is a latent unit
mix-up but does not matter here. No JMX or nodetool path sets it.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** The resource is off-heap (Netty direct) memory, or heap if
`-Dcassandra.netty_use_heap_allocator=true`. The limit applies to the cumulation buffer
that a `ByteToMessageDecoder` keeps per connection while it waits for a complete CQL
envelope on the unframed path. That path is the initial handshake path for every
connection, and the whole session for protocol v3/v4. The allocator is `CBUtil.allocator`,
a `PooledByteBufAllocator(preferDirect=true)` (`CBUtil.java:60`), set as the child
allocator in `PipelineConfigurator.java:138`. The quantity compared is
`totalLength = bodyLength + Header.LENGTH`, where `bodyLength` is the length the client
declares in the header (`Envelope.java:424-429`). The entry lines compare
`bytesToDiscard`, the part of an oversized frame that has not yet been skipped, against 0.

**A3. Mechanism.**
1. Every new connection gets `InitialConnectionHandler(new Envelope.Decoder(), ...)`
   ([`PipelineConfigurator.java:265`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L265)). It is a `ByteToMessageDecoder`
   ([`InitialConnectionHandler.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/InitialConnectionHandler.java#L52)) whose `decode` calls `decoder.decode(buffer)` on
   its cumulation ([`InitialConnectionHandler.java:66-70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/InitialConnectionHandler.java#L66-L70)). After a pre-V5 STARTUP,
   `configureLegacyPipeline` installs a fresh `Envelope.Decoder` as `ENVELOPE_DECODER`
   ([`PipelineConfigurator.java:388-391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L388-L391)), and that decoder handles the rest of the session.
2. `decode` reads the header, then `bodyLength = buffer.getUnsignedInt(idx)` ([`Envelope.java:424`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L424)).
3. If `totalLength > MAX_TOTAL_LENGTH` (`:429`), the decoder enters discard mode
   (`:432-435`). `discard()` skips `min(remaining, readable)` bytes (`:493-498`).
   **Entry line 436:** if the whole oversized frame was already in the buffer,
   `bytesToDiscard <= 0` and `fail()` throws `InvalidRequestException("Request is too big ...")`
   wrapped with the stream id (`:478-486`). Otherwise it returns `null` and stays in
   discard mode.
4. On later reads, while `discardingTooLongMessage` is set (`:345`), the decoder skips
   the new bytes. **Entry line 349:** once the oversized frame has been skipped in full,
   it calls `fail()`, which resets the state and raises the error. Until then it returns
   `null` and holds nothing. Because the bytes are skipped, `ByteToMessageDecoder` can
   release or compact its cumulation, so it does not grow.
5. If the frame is within the limit, the decoder returns `null` until
   `buffer.readableBytes() >= totalLength` (`:441-442`). The cumulation therefore grows
   to the full frame size, which is at most `MAX_TOTAL_LENGTH`. Then it slices and retains
   the body (`:448-449`).

Outcome at the limit: the connection stays open. An error response goes to the client's
stream id, and the oversized bytes are never buffered.

Bypasses and overshoot:
- Below the limit, each connection may hold up to one frame's worth of cumulation, plus
  Netty's expansion slack (MERGE_CUMULATOR grows capacity, so capacity can exceed readable
  bytes by up to one growth step). The number of connections is not bounded by this
  constraint.
- Protocol v5 after negotiation does not use this decoder. Message bodies are framed by
  `FrameDecoder` and limited by `native_transport_max_message_size` and
  `native_transport_receive_queue_capacity` (`configureModernPipeline`,
  `PipelineConfigurator.java:276-`).
- `extractHeader` ([`Envelope.java:219-270`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L219-L270), the v5 path) does not check `MAX_TOTAL_LENGTH`.

**A4. Other consumers.** Netty pooled arenas and thread caches. Decoded request envelopes,
which are counted by `native_transport_max_request_data_in_flight[_per_ip]` once a frame
is complete (`PreV5Handlers.java:180-187`). Response buffers and the `Flusher`.
`GlobalBufferPoolAllocator` for v5 framing (`PipelineConfigurator.java:282`). The rest of
the node: memtables, chunk cache, internode messaging.

**A5. Evidence beyond the source.** `test/unit/org/apache/cassandra/transport/ProtocolErrorTest.java:241-264`
(`testBodyLengthOverLimit`, which declares a 256 MiB body and expects "Request is too big").
`conf/cassandra.yaml:1040-1044`.

## B. Verification solution

**B1. Claim under test.** On the unframed CQL path, a connection never holds more than
about `native_transport_max_frame_size` (plus one Netty growth step) of buffered bytes for
an incomplete frame. A frame that declares more than the limit is skipped as it arrives,
so its bytes are not retained. Lowering the limit below the declared frame size therefore
turns per-connection retained memory from about the frame size into about zero.

### B2. Unit tier

**B2a. Environment and build.** JDK 11 and Ant on Linux. Copy the clone to local disk:
`git clone --branch cassandra-5.0.9 <shared-clone> /local/c509 && cd /local/c509 && ant jar build-test`.
Put the test at `test/unit/org/apache/cassandra/transport/FrameSizeDiscardProbeTest.java`
in the local copy only. JVM options are the Ant test defaults.

> **Amendment U1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2a on this host (the advisor's Mac, `environment-advisor.md`): there is no `/local`; the run clone is
> `$W/cassandra-run54` (`W=~/Library/Caches/stage4`, `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run54`,
> `ant -Dlocal.repository=$W/m2 build-test`, every ant call with `-Dlocal.repository=$W/m2`). The test class is kept in
> `stage4-runtime-verification/harness/<stem>/FrameSizeDiscardProbeTest.java`, copied into the clone's
> `test/unit/org/apache/cassandra/transport/` only for the run and removed afterwards (`harness/<stem>/unit-run.sh`).

**B2b. Knobs.** Set `native_transport_max_frame_size` to `4MiB` and to `16MiB`. Because
`MAX_TOTAL_LENGTH` is a static final, each value needs its own JVM. Set it in
`@BeforeClass` with
`DatabaseDescriptor.daemonInitialization(() -> { Config c = DatabaseDescriptor.loadConfig(); c.native_transport_max_frame_size = new DataStorageSpec.IntMebibytesBound(System.getProperty("probe.mfs", "4MiB")); return c; });`
Run once with `-Dprobe.mfs=4MiB` and once with `-Dprobe.mfs=16MiB`. If ant does not pass
the property through, use two copies of the test class with the value hard-coded.

> **Amendment U2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2b: a third value, **`8MiB`** (8,388,608 bytes), is added, so the tier has three values including the
> default (`4MiB`, `8MiB`, `16MiB`); each value is its own `ant testsome` JVM. Ant passes a `-D` property to the forked test JVM
> only through `test.jvm.args` (`build.xml:94, 1192`), so the property is given as `-Dtest.jvm.args=-Dprobe.mfs=<value>`; the
> fallback of two hard-coded copies is not used. The test reads back `DatabaseDescriptor.getNativeTransportMaxFrameSize()` and the
> decoder's static `MAX_TOTAL_LENGTH` (reflection) and prints both before any feed; both must equal the value's bytes (4,194,304,
> 8,388,608 or 16,777,216).

**B2c. Workload.** Build a v4 header: byte 0 = `0x04`, flags `0x00`, stream `0x0001`,
opcode `0x05` (OPTIONS), and body length `L = 8 MiB = 8388608`. Feed the header and then
the body to one `Envelope.Decoder` (`decode(ByteBuf)`, which is `@VisibleForTesting` and
package-visible) as a cumulative `Unpooled.buffer()`, adding 64 KiB per call. After each
call, call `buf.discardReadBytes()` to mimic `ByteToMessageDecoder`. Stop at `L - 1` body
bytes, then send the final byte. With `4MiB`, `L + 9 > 4194304`, so the decoder discards.
With `16MiB`, `L + 9 < 16777216`, so it buffers.

> **Amendment U3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2c, exact feed schedule. Each sub-run uses a fresh `Envelope.Decoder` and a fresh `Unpooled.buffer()`.
> Call 0 feeds only the 9-byte header (`04 00 00 01 05` + `L` as a big-endian unsigned int). The body (zero bytes) follows in
> `n = ceil((L-1)/65536)` calls of 65,536 bytes, the last of them carrying the remainder so that exactly `L-1` body bytes are fed by
> call `n`; call `n+1` feeds the final body byte. After every call that returns normally or throws, `buf.discardReadBytes()` is
> called. Sub-runs per JVM (all with stream 1, OPTIONS, v4):
> - every value: **MAIN**, `L = 8,388,608` (`n = 128`: 127 calls of 65,536 and one of 65,535);
> - `4MiB` only: **CTRL1M** (the B2h control), `L = 1,048,576` (`n = 16`: 15 × 65,536 + 65,535), and **C436**, the whole frame
>   (`L = 8,388,608`, 8,388,617 bytes) fed in one call, which exercises entry line 436 with the frame already complete;
> - `8MiB` only: **EDGE**, `L = 8,388,599`, so `totalLength = L + 9 = 8,388,608 = MAX_TOTAL_LENGTH` exactly (`n = 128`: 127 × 65,536
>   + 65,526); `:429` is `>`, so this frame is buffered.

**B2d. Observables and instruments.** After each call, record `buf.readableBytes()`
(bytes retained) and the decoder's private `bytesToDiscard` and `discardingTooLongMessage`
(read by reflection). Also record whether `decode` returned an `Envelope` or threw
`ErrorMessage.WrappedException`. All of these values are exact.

> **Amendment U4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2d: one line per call, `PROBE,<mfs>,<subrun>,<call>,<fed>,<readableBefore>,<readableAfter>,<capacity>,<bytesToDiscard>,<discarding>,<outcome>`,
> where `readableBefore` is `buf.readableBytes()` just before `decode`, `readableAfter` just after `decode` (before
> `discardReadBytes()`), `capacity` is `buf.capacity()` after `discardReadBytes()`, and `outcome` is `null`, `ENVELOPE(type,stream,bodySizeInBytes)`
> or `WRAPPED(stream,<cause message>)`. The CSV of B2e step 3 is this line. One `CONFIG,<mfs>,<getter>,<MAX_TOTAL_LENGTH>` line per JVM.

**B2e. Procedure.**
1. `ant testsome -Dtest.name=org.apache.cassandra.transport.FrameSizeDiscardProbeTest -Dprobe.mfs=4MiB`
2. Repeat with `-Dprobe.mfs=16MiB`.
3. Have the test print one CSV line per chunk: `chunk,readable,bytesToDiscard,discarding`.

> **Amendment U5 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2e: the commands are
> `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.transport.FrameSizeDiscardProbeTest -Dtest.jvm.args=-Dprobe.mfs=<v>`
> for `v` = `4MiB`, `8MiB`, `16MiB`, in that order, from `harness/<stem>/unit-run.sh`, which logs each command and copies the test's
> stdout (`build/test/logs/**/TEST-org.apache.cassandra.transport.FrameSizeDiscardProbeTest.log`, one line per `System.out` write)
> after each JVM, before the next overwrites it. The test itself does not assert the predictions (it always passes unless it
> crashes); the readings are judged from the `PROBE` lines by the self-check script. Stop condition: a JVM whose `CONFIG` line is
> missing or wrong ends the tier as Invalid.

**B2f. Predictions.**
- `4MiB`: after the header chunk, `discarding=true`. `readable` is 0 after every call.
  `bytesToDiscard` falls by 65536 per chunk from `L+9-firstChunkBody`. On the call that
  completes the frame it reaches 0, line 349 is true, `WrappedException` ("Request is too
  big", stream 1) is thrown, and `discarding=false`. The maximum of `readable` stays below
  65536 + 9.
- `16MiB`: `discarding` stays false and `readable` grows linearly to `L+9 = 8388617`. The
  last byte yields an `Envelope` with `bodySizeInBytes = 8388608`.

> **Amendment U6 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2f, exact values from the source (`Envelope.java:345-350, 424-442, 478-498`). This corrects the start value,
> which the filed text gives as `L+9-firstChunkBody`: `discard(buffer, totalLength)` at `:434` is called with the reader index still at
> the frame start (`idx` is a local), so the 9 header bytes are discarded too and, with call 0 feeding only the header,
> `bytesToDiscard = L + 9 - 9 = L` after call 0. A correction from the source, not from a reading.
> - **4MiB MAIN** and **8MiB MAIN** (`L + 9 = 8,388,617 > MAX`): call 0: `discarding=true`, `bytesToDiscard = 8,388,608`; call `k`
>   (1..127): `bytesToDiscard = 8,388,608 - 65,536·k`; call 128: `bytesToDiscard = 1`; call 129: `WRAPPED(1, "Request is too big: length
>   8388617 exceeds maximum allowed length <MAX>.")`, `discarding=false`, `bytesToDiscard = 0`. `readableAfter = 0` after every call;
>   `max readableBefore = 65,536` (call 0: 9); capacity never above 65,536 + 9.
> - **4MiB C436**: call 0 (all 8,388,617 bytes) throws `WRAPPED(1, "Request is too big: length 8388617 exceeds maximum allowed length 4194304.")`,
>   `readableAfter = 0`, `discarding=false`, `bytesToDiscard = 0`.
> - **4MiB CTRL1M** (`L + 9 = 1,048,585 ≤ 4,194,304`): `discarding=false` throughout, `bytesToDiscard = 0`; calls 0..16 return `null` with
>   `readableAfter = 9 + 65,536·k` for `k ≤ 15` and `1,048,584` after call 16; call 17: `readableBefore = 1,048,585`, `ENVELOPE(OPTIONS,1,1048576)`,
>   `readableAfter = 0`.
> - **8MiB EDGE** (`L + 9 = 8,388,608 = MAX`): `discarding=false` throughout; `readableAfter = 9 + 65,536·k` for `k ≤ 127`, `8,388,607` after call 128;
>   call 129: `readableBefore = 8,388,608`, `ENVELOPE(OPTIONS,1,8388599)`.
> - **16MiB MAIN**: `discarding=false` throughout; `readableAfter = 9 + 65,536·k` for `k ≤ 127`, `8,388,616` after call 128 (the filed
>   "grows linearly to `L+9 = 8388617`" is `readableBefore` of call 129); call 129: `ENVELOPE(OPTIONS,1,8388608)`, `readableAfter = 0`.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| 4MiB: readable stays near 0 and the error comes after the last byte; 16MiB: readable reaches about 8 MiB | Claim supported: the limit decides between retaining and skipping |
| 4MiB: readable grows past 4 MiB | Claim wrong: the limit does not stop buffering |
| 4MiB: error thrown before the frame is fully sent | The line-349 timing differs from the trace (a shorter frame would desync the stream). Record it; the memory claim still holds if readable stays near 0 |
| 16MiB: readable does not grow | The workload did not reach the buffering path; the run is invalid |

> **Amendment U7 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2g, rows with verdicts (Effect in brackets). Checked in this order; the first matching row is the result.
> | # | Observation | Verdict |
> |---|---|---|
> | g0 | a `CONFIG` line missing or not equal to the value's bytes, or 16MiB MAIN `readableAfter` never above 65,536 + 9 (the filed "16MiB: readable does not grow") | **Invalid** |
> | g1 | 4MiB MAIN or 8MiB MAIN: `readableAfter` > 65,545 at any call, or `ENVELOPE` returned | **Refuted** (does not cap): the limit does not stop buffering |
> | g2 | 4MiB MAIN or 8MiB MAIN: `WRAPPED` thrown before call 129 (the filed "error thrown before the frame is fully sent") | **Not confirmed** (undetermined): line-349 timing differs; record whether readable stayed near 0 |
> | g3 | CTRL1M or EDGE does not end in its `ENVELOPE` with the predicted `readableBefore` | **Not confirmed** (undetermined): the size relation, not the value, does not decide as traced |
> | g4 | every U6 value holds for all six sub-runs (MAIN at the three values, C436, CTRL1M, EDGE) | **Confirmed** (caps): retained bytes follow the limit, ≈ 0 above it and the full frame at or below it; lines 349 (MAIN) and 436 (C436) fire |
> | g5 | g1–g3 do not match but some U6 value differs (e.g. a `bytesToDiscard` step) | **Not confirmed** (undetermined): record the difference |

**B2h. Controls.** The 16MiB run is the positive control: the same bytes, retained.
Running the same frame with `L = 1 MiB` under the 4MiB setting must also buffer, which
shows that the size relation, not the config load, decides the outcome.

### B3. Cluster tier

> **Amendment U8 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2h: the controls are run as U3 says (CTRL1M in the 4MiB JVM; EDGE, the boundary `totalLength = MAX`, in the 8MiB JVM).

**B3a. Environment and build.** One Linux node, built from `/local/c509` (`ant jar`).
Copy `conf/` to `/local/c509-conf`. In `cassandra.yaml` set `data_file_directories`,
`commitlog_directory`, `hints_directory` and `saved_caches_directory` to `/local/c509-data/...`
on local disk with at least 5 GB free, and leave `native_transport_port: 9042`. Set the
environment:
`export CASSANDRA_CONF=/local/c509-conf MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2G"`.

> **Amendment C1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3a on this host: macOS, no `/local`, no `/proc`. Clone `$W/cassandra-run54` (already built with `build-test`, which
> includes the jar). Node files under `$W/node-ntfs` (`conf/` copied from the clone, `data/`, `commitlog/`, `hints/`, `saved_caches/`,
> `cdc_raw/`, `logs/`), fresh for each value and removed at the end; internal APFS SSD (≈120 GiB free). Node:
> `CASSANDRA_CONF=$W/node-ntfs/conf CASSANDRA_LOG_DIR=$W/node-ntfs/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M`
> `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2G -javaagent:<clone>/build/lib/jars/byteman-4.0.20.jar=script:<harness>/ntfs.btm"`,
> started as a tracked background process `bin/cassandra -f > node-stdout.log 2>&1 < /dev/null` (no `-p`; the script records the PID).
> `JVM_EXTRA_OPTS` is appended after `cassandra-env.sh`'s own `MaxDirectMemorySize` (`conf/cassandra-env.sh:158, 307`), so the 2G flag wins.
> Up = `nodetool statusbinary` prints `running` and `Starting listening for CQL clients` is in `system.log`.

**B3b. Knobs.** `native_transport_max_frame_size: 16MiB` (run A, the default) and
`native_transport_max_frame_size: 4MiB` (run B). Each value needs a restart.
`native_transport_idle_timeout` stays at its default of 0, so idle connections are not
closed.

> **Amendment C2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3b: a third value, **`8MiB`** (run C), is added (three values including the default); order A (16MiB), B (4MiB),
> C (8MiB), a fresh node and node directory per value. With `L = 8 MiB` the frame's `totalLength` is 8,388,617 > 8,388,608, so run C is
> on the discard side by 9 bytes (the header counts, `Envelope.java:428-429`).

**B3c. Workload.** Save this as `/local/tools/hold_frames.py` (python3, raw sockets, run
outside the clone):
```python
import socket, struct, sys, time
host, port, K, L, hold = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
socks = []
for i in range(K):
    s = socket.create_connection((host, port))
    s.sendall(struct.pack('>BBhBI', 0x04, 0, 1, 0x05, L))  # v4 request, stream 1, OPTIONS, body length L
    sent, chunk = 0, b'\0' * 65536
    while sent < L - 1:
        n = min(65536, L - 1 - sent); s.sendall(chunk[:n]); sent += n
    socks.append(s)
print("holding", len(socks), flush=True); time.sleep(hold)
for s in socks: s.close()
```
Use K = 32 connections and L = 8 MiB (8388608), with the final byte withheld. The
retained target is 32 × 8 MiB = 256 MiB of direct memory in run A, which is below the
2 GiB `MaxDirectMemorySize`. In run B every frame exceeds 4 MiB and should be discarded.
Hold each connection for 120 s.

> **Amendment C3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3c: the client is `harness/<stem>/hold_frames.py`: the filed script verbatim up to and including
> `time.sleep(hold)`, then, before closing, it sends the withheld final byte on each socket and reads one response per socket (9-byte
> header, then the body; 10 s timeout), printing `resp i=<i> ver=<byte0> stream=<s> opcode=<op> len=<n> [code=<c> msg=<message>]`.
> This adds the disallow evidence the filed design lacked (line 349 at runtime): with the final byte the 4MiB/8MiB decoders reach
> `bytesToDiscard <= 0` and answer `ERROR` (opcode 0) "Request is too big: length 8388617 exceeds maximum allowed length <MAX>."; the 16MiB
> decoder completes the envelope and `InitialConnectionHandler` answers `SUPPORTED` (opcode 6, `InitialConnectionHandler.java:77-95`).
> The holding window, where memory is read, is unchanged. Run as `python3 hold_frames.py 127.0.0.1 9042 32 8388608 120`.

**B3d. Observables and instruments.**
- `jcmd <pid> VM.native_memory summary`, the `Other` category, which holds Netty's
  `Unsafe.allocateMemory`/direct buffers on JDK 11. Take it as a baseline after a
  `VM.native_memory baseline`, then use `summary.diff`.
- `VmRSS` from `/proc/<pid>/status`, sampled every 5 s.
- The server log: run A should show no "Request is too big". In run B the error is sent
  to the client only after the full frame arrives, so it does not appear while the last
  byte is withheld.

The decoder's own state cannot be observed on a live node.

> **Amendment C4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3d on this host. (i) NMT: `jcmd <pid> VM.native_memory baseline`, then `VM.native_memory summary.diff`; the
> reading is the **committed** delta of the `Other` line, in KiB (JDK 11 charges `Unsafe.allocateMemory`, which backs Netty's direct
> buffers, to `Other`). (ii) RSS: `ps -o rss= -p <pid>` (KiB) in place of `/proc/<pid>/status`, every 5 s by a background sampler;
> **RSS is context only** (the filed "RSS grows by a similar amount" has no number and no row uses it). (iii) Byteman, observe-only
> (`harness/<stem>/ntfs.btm`, type-checked with `TestScript` before the run): `NTFDISCARD` — one line each time a decoder enters
> discard mode (after the write of `tooLongTotalLength` in `Envelope$Decoder.decode(ByteBuf)`, `:433`), with `tooLongTotalLength`;
> `NTFFAIL` — one line per `fail()` call (the true branch of `:349`/`:436`); `NTFMEM` — on every `nodetool version`, the
> native-transport allocator's `metric().usedDirectMemory()` (`CBUtil.allocator`, `CBUtil.java:60`) and a count of `Envelope.discard`
> calls; supplementary to NMT, not a row condition except the counts below. (iv) Client responses (C3). (v) `system.log` lines with
> "Request is too big", context.
> Expected from source (context for the band, not a new band): in run A each held connection's cumulation holds 9 + 8,388,607 =
> 8,388,616 bytes; Netty 4.1.130 `AbstractByteBufAllocator.calculateNewCapacity` grows a buffer above 4 MiB in 4 MiB steps
> (`min/4MiB·4MiB + 4MiB`), so the capacity is 12,582,912 bytes and 32 connections hold about 384 MiB, inside B3f's band.

> **Runbook fix D1 (2026-10-27, stage 4, found at the cluster shakedown before run 1; claim, bands and B3g rows unchanged).** With the
> default pooled `CBUtil.allocator`, neither NMT `Other` nor the allocator metric can see the bytes a connection holds: the node runs with
> `-Dio.netty.allocator.maxOrder=11` (`conf/jvm11-server.options:145`), so each direct arena commits memory in 16 MiB chunks
> (8 KiB pages `<< 11`) on its first allocation and keeps them, and every connection's read buffers (up to 64 KiB) touch its event loop's
> arena. The shakedown (4 connections, 2 MiB frames, `1MiB` node, every frame discarded) read `Other` +65,536 KiB and `usedDirectMemory`
> 67,108,864 (4 chunks) at the samples and after close, the same as on the buffering node. Fix: every node of this tier runs with
> `-Dcassandra.netty_use_heap_allocator=true` added to `JVM_EXTRA_OPTS` (C1). `CBUtil.allocator` is then an
> `UnpooledByteBufAllocator(false)` (`CBUtil.java:59-60`); the channel's read buffers come from its `ioBuffer()`, which returns a direct
> buffer whenever Unsafe is available (`AbstractByteBufAllocator.ioBuffer`), unpooled (`UnpooledByteBufAllocator.newDirectBuffer`:
> `InstrumentedUnpooledUnsafeNoCleanerDirectByteBuf`), and the merge cumulator grows the first read buffer in place by
> `calculateNewCapacity` with an exact-size reallocation. So the cumulation is still direct memory charged to NMT `Other`, now with no
> chunk granularity: a discarding connection's read buffers are freed after each read, and a buffering connection holds exactly its
> cumulation (12,582,912 bytes at `9 + L - 1` bytes, C4). `NTFMEM` reads the `UnpooledByteBufAllocator`'s metric. The decoder path
> (`Envelope.Decoder`, `:345-449`) does not depend on the allocator. This is not the heap retry of h1 (it does not move anything to the
> heap; heap is not measured). The unit tier is unchanged.

**B3e. Procedure.**
1. Start the node: `bin/cassandra -p /local/c509-run/pid`, then wait for
   `nodetool status` to show UN. Let it idle for 60 s.
2. Run `jcmd $(cat /local/c509-run/pid) VM.native_memory baseline` and record VmRSS.
3. Run `python3 /local/tools/hold_frames.py 127.0.0.1 9042 32 8388608 120 &`. Once it
   prints "holding", wait 10 s, then run
   `jcmd <pid> VM.native_memory summary.diff | grep -A2 Other` and record VmRSS. Repeat
   three times, 20 s apart.
4. Wait for the script to exit, sleep 15 s, and take the diff again (release check).
5. Stop the node with `kill $(cat /local/c509-run/pid)`. Change the knob to 4MiB, then
   repeat steps 1-4.

> **Amendment C5 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3e, exact procedure (`harness/<stem>/cluster-run.sh`, logged), per value: (1) fresh node directory, start, wait
> until up (stop condition: not up in 300 s or the daemon dies → Invalid); record the effective value from `system.log`'s config line;
> idle 60 s. (2) `VM.native_memory baseline`; RSS; `NTFMEM` (base). (3) **Drift control** (B3h's idle baseline): wait 50 s,
> `summary.diff` → `D0`. (4) start `hold_frames.py` in the background; when it prints `holding` (stop condition: none within 120 s →
> Invalid), wait 10 s, then three samples 20 s apart (S1 at +10 s, S2 at +30 s, S3 at +50 s): `summary.diff` (Other committed delta),
> RSS, `NTFMEM`. (5) wait for the client to exit (it sends the final bytes after its 120 s hold, reads the responses, closes), sleep 15 s,
> `summary.diff` → `R` (release check), `NTFMEM`. (6) copy logs, stop the node (`nodetool stopdaemon`, then kill if still alive after 60 s),
> and check no daemon is left. Values in the order 16MiB, 4MiB, 8MiB.

**B3f. Predictions.**
- Run A (16MiB): `Other` grows by at least 0.9 × 256 MiB, about 230 MiB, and by at most
  about 2 × 256 MiB (growth slack). RSS grows by a similar amount. Both fall back within
  about 50 MiB of baseline after the connections close.
- Run B (4MiB): the growth in `Other` is at most 32 MiB, which covers per-connection
  setup and pool chunks.

> **Amendment C6 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3f: "flat" for runs B and C means ΔOther ≤ 32 MiB (32,768 KiB) at each of S1–S3; run A's band is
> 0.9 × 256 MiB = 235,929.6 KiB ≤ ΔOther ≤ 512 MiB = 524,288 KiB at each of S1–S3 (the filed "about 230 MiB" is taken as 0.9 × 256 MiB);
> release: run A's `R` ≤ 50 MiB (51,200 KiB). RSS is context (C4).

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| A grows by about 256 MiB or more; B stays flat | Claim supported: the limit governs retained memory for incomplete frames |
| B grows by about 256 MiB like A | Claim wrong: frames over the limit are still buffered |
| A also flat | Positive control failed (the workload did not buffer, or the instrument missed Netty memory). Retry with `-Dcassandra.netty_use_heap_allocator=true` and measure heap after `jcmd GC.run` |
| Both grow, B much less but more than 32 MiB | Partial: some buffering before the discard decision. Report the size per connection |

> **Amendment C7 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3g, rows with verdicts (Effect in brackets); first matching row in this order is the result.
> | # | Observation | Verdict |
> |---|---|---|
> | h0 | a node's effective value is wrong, the client never prints `holding`, or any node's `\|D0\|` > 32 MiB | **Invalid** |
> | h1 | run A ΔOther < 235,929.6 KiB at any of S1–S3 (the filed "A also flat": positive control failed) | **Not confirmed** (undetermined). The filed retry with `-Dcassandra.netty_use_heap_allocator=true` is not run in run 1: by source the read buffers come from `ioBuffer()`, which is direct whenever Unsafe is available, so the flag does not move the cumulation to the heap; a retry would be a different experiment |
> | h2 | run B or run C ΔOther ≥ 235,929.6 KiB at any sample (the filed "B grows like A") | **Refuted** (does not cap) |
> | h3 | run B or run C ΔOther in (32,768, 235,929.6) KiB at any sample, A in band (the filed "Partial") | **Not confirmed** (undetermined): report the size per connection |
> | h4 | B and C ≤ 32,768 KiB at S1–S3; A in band at S1–S3; A's `R` ≤ 51,200 KiB; disallow evidence: 32 `NTFDISCARD` lines with `tooLongTotalLength=8388617` in each of B and C and 0 in A; 32 `ERROR` "Request is too big" responses (and 32 `NTFFAIL`) in each of B and C, 32 `SUPPORTED` responses and 0 `NTFFAIL` in A | **Confirmed** (caps) |
> | h5 | as h4 for memory, but A above 524,288 KiB, A's `R` above 51,200 KiB, or the disallow evidence differs | **Not confirmed** (undetermined): record which part failed |
> | h6 | none of the above | **Not confirmed**; feedback to stage 3 (the table missed an outcome) |

**B3h. Controls.** Run A is the positive control with the same workload. The release check
in step 4 ties the growth to the held connections. Running the idle baseline for the same
length of time rules out drift.

> **Amendment C8 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3h: the drift control is step (3) of C5 and its bound is in h0; the release check is `R` in h4.

**B4. Risks and cleanup.** Write nothing to the shared clone. Data, logs and the PID file
live under `/local/c509-*`. After each run, `kill` the node, then confirm with
`pgrep -f CassandraDaemon` that nothing is left, and kill any `hold_frames.py` with
`pkill -f hold_frames.py`. `rm -rf /local/c509-data /local/c509-run` when done. Direct
memory stays capped at 2 GiB, so there is no host OOM risk.

> **Amendment C9 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B4 on this host: node files in `$W/node-ntfs` (removed at the end); logs in
> `$W/logs/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/`; after each value the script stops the node and counts
> `ps -eo command | grep -c 'org.apache.cassandra.service.Cassandra[D]aemon'` (must be 0) and kills any `hold_frames.py`; the test class is
> removed from the clone after the unit tier and `git -C $W/cassandra-run54 status --short` must be empty at the end.

## C. Sources read

src/java/org/apache/cassandra/transport/Envelope.java
src/java/org/apache/cassandra/transport/InitialConnectionHandler.java
src/java/org/apache/cassandra/transport/PipelineConfigurator.java
src/java/org/apache/cassandra/transport/PreV5Handlers.java
src/java/org/apache/cassandra/transport/CBUtil.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/DataStorageSpec.java
conf/cassandra.yaml
conf/cassandra-env.sh
test/unit/org/apache/cassandra/transport/ProtocolErrorTest.java
build.xml

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1 on the advisor's Mac** ([results](../../stage4-runtime-verification/results/native_transport_max_frame_size-decode-bytesToDiscard--autonomous.md);
frozen at sha256 `9118745e…2715` after amendments U1–U8 and C1–C9, run at `b7591e0c…6067` after runbook fix D1; uncommitted).
- **Unit: Confirmed — caps** (B2g row g4). Every predicted value held over 539 decode calls at 4/8/16 MiB: above the limit the
  cumulation's readable bytes were 0 after every call and the frame failed with "Request is too big" exactly on its last byte (line 349)
  or at once when complete (line 436); at 16 MiB, at the 1 MiB control and at the `totalLength = MAX` edge the frame was buffered whole.
- **Cluster: Confirmed — caps** (B3g row h4). 32 connections each holding an incomplete 8 MiB frame: NMT `Other` +393,216 KiB at
  16 MiB (32 × 12 MiB cumulation capacity), 0 at 4 MiB and 8 MiB, release +5 KiB; 32 discard-mode entries and 32 "Request is too big"
  responses at 4/8 MiB, none and 32 `SUPPORTED` at 16 MiB.
- Runbook fix D1: with the default pooled allocator (`maxOrder=11`, 16 MiB arena chunks kept after first use) NMT cannot see
  per-connection bytes; the cluster tier ran with `-Dcassandra.netty_use_heap_allocator=true` (unpooled direct buffers).
- For stage 3: the filed discard start value was off by the 9 header bytes (`discard` counts from the frame start); state where a
  counter starts and the feed schedule before writing exact numbers, and check allocator chunk granularity when reading direct memory.
