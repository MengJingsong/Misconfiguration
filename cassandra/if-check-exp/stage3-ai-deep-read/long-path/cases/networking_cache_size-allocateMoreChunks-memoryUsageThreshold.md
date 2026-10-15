# networking_cache_size — buffer pool macro chunk (networking pool)

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | NETWORKING_CACHE_SIZE-ALLOCATEMORECHUNKS-MEMORYUSAGETHRESHOLD |
| **Constraint** | `networking_cache_size` — a **configuration entry** ([`Config.java:493-494`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L493-L494), `DataStorageSpec.IntMebibytesBound`, no default in the field; auto-sized when unset to `min(128MiB, maxMemory/16)`, [`DatabaseDescriptor.java:573-574`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L573-L574)). **Restart-only.** It is the threshold of the **`networking`** `BufferPool`; the same check on the `chunk-cache` pool takes `file_cache_size` and is the filed sibling. |
| **Enforcement pattern** | **(a)** — the `if` is the decision: one arm returns `null`, the other falls through to the allocation. Same statement as the sibling. |
| **Capacity check** | [`BufferPool$GlobalPool.allocateMoreChunks():443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443) — `cur + MACRO_CHUNK_SIZE > memoryUsageThreshold`, on the instance built at [`BufferPools.java:44-45`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L44-L45). |
| **Decision point** | The same statement — [`:443-453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443-L453): the disallow arm logs and `return null`; the allow arm CASes `memoryAllocated` and breaks out to the allocation. |
| **Allocation site** | [`:460`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L460) — `chunk = new Chunk(null, allocateDirectAligned(MACRO_CHUNK_SIZE))`, an **8 MiB** aligned direct `ByteBuffer`. |
| **Related cases** | [`file_cache_size-allocateMoreChunks-memoryUsageThreshold.md`](file_cache_size-allocateMoreChunks-memoryUsageThreshold.md) — **the sibling: same check, same code path; read it for §5–§7, this file records only what differs** (closed at stage 4, 2026-10-14). [`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md`](internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md) — its delivery's frames come from this pool and are outside its byte count (its §7). [`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md`](native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md) and [`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md`](internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md) — the inbound frames they admit arrive in this pool's buffers. |

```java
// BufferPools:41-45 — the networking instance: its own threshold, and recyclePartially = false.
/**
 * Used by client-server or inter-node requests, buffers should be released immediately after use.
 */
private static final long NETWORKING_MEMORY_USAGE_THRESHOLD = DatabaseDescriptor.getNetworkingCacheSizeInMiB() * 1024L * 1024L;
private static final BufferPool NETWORKING_POOL = new BufferPool("networking", NETWORKING_MEMORY_USAGE_THRESHOLD, false);

// BufferPool$GlobalPool.allocateMoreChunks():440-460 — the check (shared with the chunk-cache pool).
long cur = memoryAllocated.get();
if (cur + MACRO_CHUNK_SIZE > memoryUsageThreshold)          // <-- capacity check, :443
{
    if (memoryUsageThreshold > 0)
        noSpamLogger.info("Maximum memory usage reached ({}) for {} buffer pool, cannot allocate chunk of {}", ...);
    return null;                                            // <-- DISALLOW, :450
}
if (memoryAllocated.compareAndSet(cur, cur + MACRO_CHUNK_SIZE))
    break;                                                  // <-- ALLOW, :452-453
...
chunk = new Chunk(null, allocateDirectAligned(MACRO_CHUNK_SIZE));   // <-- allocation, :460
```

## 2. Context

Every byte Cassandra sends or receives over the network — between nodes, and to
clients on the current protocol version — passes through short-lived off-heap
buffers: socket reads, partly received frames, frames being encoded for the wire,
streaming chunks. Rather than ask the operating system for each one, the node
keeps a second buffer pool for this traffic, separate from the one used for file
reads. It reserves large slabs of direct memory and hands out slices.

This check is the ceiling on how large that networking pool may grow: before
carving out another slab, it refuses if the slabs already reserved plus the new
one would exceed `networking_cache_size`. As with the file-read pool, refusal is
not an error — the buffer is simply allocated from the operating system outside
the pool. Two things differ from the file-read pool and shape the test: this pool
takes back a slab only when *all* of its slices are returned (so it grows with
the traffic's peak instead of filling to its limit), and its demand is set by how
many bytes are waiting to go out or come in, which a slow reader at the other end
of a connection can make arbitrarily large.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `buffer_pool` — off-heap buffer pooling for file reads and networking (`utils/memory/BufferPool`, `utils/memory/BufferPools`); the callers of this instance are in `net` (internode framing, streaming) and `transport` (native protocol v5 framing). |
| **One-line role** | `BufferPool` reserves large aligned slabs of direct memory and sub-allocates them so short-lived off-heap buffers are recycled; the `networking` instance serves internode messaging, streaming and the native-protocol-v5 frame codec. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes** — the pool's reserved off-heap bytes (`memoryAllocated`) plus the next slab, against a configured byte ceiling; identical to the sibling. |
| **Usage-side operand** | `memoryAllocated` of the `networking` instance ([`BufferPool.java:159`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L159)): bytes **reserved** as macro chunks, never decremented (macro chunks "are never released", [`:378`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L378)). |
| **Limit-side operand** | `memoryUsageThreshold` ([`:143`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L143)), set once in the constructor ([`:190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L190)). |
| **Limit type** | **Configuration entry**, heap-derived when unset, converted MiB → bytes at class initialization. |

**Limit initialization path.**

1. [`Config.networking_cache_size:493-494`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L493-L494) — declared (old name `networking_cache_size_in_mb`), no default in the field.
2. [`DatabaseDescriptor.applySimpleConfig():573-574`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L573-L574) (method at [`:478`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L478)) — when unset, `min(128, maxMemory / 16 MiB)` MiB: **128 MiB at any heap of 2 GiB or more**, smaller below. The shipped yaml documents the same default, commented out ([`conf/cassandra.yaml:729-738`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L729-L738)).
3. [`DatabaseDescriptor.getNetworkingCacheSizeInMiB():3796-3805`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3796-L3805) — read in MiB; in client mode an unset value returns **0**.
4. [`BufferPools.NETWORKING_MEMORY_USAGE_THRESHOLD:44`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L44) — `× 1024L × 1024L`, `private static final long`.
5. [`BufferPools.NETWORKING_POOL:45`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L45) — `new BufferPool("networking", …, false)`, `static final`, returned by `forNetworking()` ([`:67-70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L67-L70)).
6. [`BufferPool` constructor `:187-196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L187-L196) — stored as the `final memoryUsageThreshold` read at `:443`; `recyclePartially = false` stored at `:194`.

**Restart-only.** Every step is `static final` or `final`; the only other reader
of the config field is the getter in step 3, and no setter or JMX operation exists
(grep of `src/java` for `networking_cache_size`, `NetworkingCacheSize`). The resolved
value is logged once at startup by
[`BufferPools.java:47-55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L47-L55)
("Global buffer pool limit is X for chunk-cache and Y for networking") and published
as the `Capacity` gauge of scope `networking`
([`BufferPoolMetrics.java:50-65`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java#L50-L65)).

**Values below one macro chunk pool nothing.** Because the comparison adds a whole
8 MiB slab, any value from 1 to 7 MiB refuses the first slab, and `0MiB` does too
without the INFO line (the log is guarded by `memoryUsageThreshold > 0`, `:445`):
every networking buffer is then an unpooled `allocateDirect`. That is an escape
value of the knob, not a bypass of the check.

**Naming.** README §6.1 names a configuration-entry limit after the entry, so this is
the `networking_cache_size` case and the file differs from the sibling only in its
first part (no collision).

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`BufferPool$GlobalPool.allocateMoreChunks():443-453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443-L453) — the check is the decision. |
| **Verdict** | n/a — pattern (a). |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `memoryAllocated + 8 MiB <= memoryUsageThreshold` | CAS bumps `memoryAllocated`, then [`:460`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L460) allocates the 8 MiB slab, cut into 64 normal chunks of 128 KiB ([`:471-482`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L471-L482)). |
| **Disallow** | `memoryAllocated + 8 MiB > memoryUsageThreshold` | INFO through the `NoSpamLogger`, `return null`; no `Chunk`, no bump. |

**Re-checked for this pool (each fact the sibling records, against the networking callers):**

- **The refusal is absorbed and the caller still gets its buffer** — same chain as the sibling's §5:
  [`getInternal():417-432`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L417-L432)
  returns `null` (the networking pool's `partiallyFreedChunks` queue is always empty, see the
  third point), then
  [`LocalPool.get():904-924`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L904-L924)
  returns `allocate(size, OFF_HEAP)` ([`:233-239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L233-L239)),
  counted in `overflowMemoryUsage`, which has no ceiling.
- **No networking caller sees the refusal.** Every caller uses `get` or `getAtLeast`; the
  `tryGet`/`tryGetAtLeast` entry points ([`:222-231`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L222-L231))
  have **no production caller in either pool** (grep of `src/java`, 2026-10-15), so the
  sibling's open question about `tryGet` callers is closed: every refusal becomes an
  overflow buffer.
- **Recycling differs: `recyclePartially` is `false`.** A normal chunk evicted from a
  thread's local queue while some of its buffers are out is recycled only when the last one
  comes back ([`tryRecycle():1240-1265`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L1240-L1265)
  takes `tryRecycleFully()` at [`:1261-1264`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L1261-L1264),
  whose CAS of `freeSlots` from −1 succeeds only on a fully free chunk,
  [`:1283-1290`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L1283-L1290)),
  and it then goes to the high-priority `chunks` queue ([`recycle():486-491`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L486-L491)),
  which `getInternal()` polls **before** it asks for a new slab. The sibling's stage-4
  mechanism — an evicted chunk recycled *partially* is no longer `EVICTED`, is never
  recycled fully, and sits in `partiallyFreedChunks`, which is polled only after a refusal
  ([`:1272-1281`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L1272-L1281),
  [`:1244-1245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L1244-L1245))
  — **cannot happen in this pool**. Derived from reading: the networking pool should grow to
  its peak concurrent demand, not to its limit. Unit step U3 and cluster scenario M test it.
- **The INFO line is shared.** The `NoSpamLogger` is static to `BufferPool`
  ([`:135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L135))
  and keys a statement by its format string
  ([`NoSpamLogger.java:270-286`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/NoSpamLogger.java#L270-L286)),
  which both pools use: **one line per 15 minutes per JVM across both pools**, so a
  chunk-cache refusal can hide the networking one.
- **Metrics exist per pool**: `Capacity`, `Size`, `UsedSize`, `OverflowSize`, `Hits`,
  `Misses` under scope `networking` (`BufferPoolMetrics.java:50-65`).

## 6. Code path

### 6a. Allow path → object creation

The pool-side steps are the sibling's §6a (thread-local `LocalPool` →
`GlobalPool.getInternal()` → `allocateMoreChunks()` → CAS → `:460`). What is
particular to this instance is **who asks**:

| Caller | What it takes | Where |
|---|---|---|
| Netty `ByteBufAllocator` for internode channels and native-v5 channels: `BufferPoolAllocator.newDirectBuffer()` → `getAtLeast` (socket read buffers, any `ByteBuf` the pipeline allocates; resizes re-take and put back) | read-sized buffers (Netty's adaptive guess, at most 64 KiB; no `RCVBUF_ALLOCATOR` is set anywhere in `src/java`) | [`BufferPoolAllocator.java:40`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L40), [`:61-76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L61-L76), [`:119-131`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L119-L131); set at [`InboundConnectionInitiator.java:108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundConnectionInitiator.java#L108), [`:169`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundConnectionInitiator.java#L169), [`OutboundConnectionInitiator.java:192`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnectionInitiator.java#L192), [`PipelineConfigurator.java:282-283`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L282-L283) |
| Internode large-message inbound channels: a channel-owned `LocalPool` | as above | [`LocalBufferPoolAllocator.java:38-42`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/LocalBufferPoolAllocator.java#L38-L42), [`InboundConnectionInitiator.java:474-480`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundConnectionInitiator.java#L474-L480) |
| Frame decoders: a partly received frame is stashed in a buffer of the full frame length | up to 128 KiB + 10 B | [`FrameDecoder.stash():334-340`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameDecoder.java#L334-L340), [`ensureCapacity():391-401`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameDecoder.java#L391-L401), [`FrameDecoderWith8bHeader.java:89-90`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameDecoderWith8bHeader.java#L89-L90), [`:128-133`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameDecoderWith8bHeader.java#L128-L133) |
| Frame encoders: every outgoing v5/internode frame is a `FrameEncoder.Payload` | payload + header + trailer, ≤ 128 KiB | [`FrameEncoder.java:32`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoder.java#L32), [`:64`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoder.java#L64); internode small/urgent delivery [`OutboundConnection.java:782`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L782), large delivery 32 KiB [`AsyncMessageOutputPlus.java:80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncMessageOutputPlus.java#L80); native responses [`Flusher.java:163-199`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L163-L199), [`:276-292`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L276-L292) |
| LZ4 frame encoder: a second buffer for the compressed frame | `maxCompressedLength` + 12 B (above 128 KiB for a full frame) | [`FrameEncoderLZ4.java:76-77`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoderLZ4.java#L76-L77) |
| Streaming and handshake | 8 KiB and up; handshake messages | [`AsyncStreamingOutputPlus.java:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java#L58), [`:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java#L75), [`:125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java#L125); [`CassandraStreamWriter.java:149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraStreamWriter.java#L149); [`HandshakeProtocol.java:125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/HandshakeProtocol.java#L125) |

**Not this pool:** native protocol **v4 and older**. Their channels allocate with
`CBUtil.allocator`, a Netty `PooledByteBufAllocator`
([`CBUtil.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CBUtil.java#L60),
[`PipelineConfigurator.java:138`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L138));
only the v5 pipeline swaps in `GlobalBufferPoolAllocator` and the v5 frame codec
(`:282-289`). A response body is also built with `CBUtil.allocator` before it is copied
into v5 frames.

**One full native-v5 response frame is one normal chunk.** `Flusher` cuts a large
response into payloads of `MAX_FRAMED_PAYLOAD_SIZE` = 131,072 − 12 = 131,060 B
([`Flusher.java:47-49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L47-L49),
[`:172-173`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L172-L173));
the CRC encoder's `Payload` asks for 131,060 + 6 + 4 = 131,070 B
([`FrameEncoderCrc.java:35-41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoderCrc.java#L35-L41)),
which `getAtLeast` rounds to the whole 131,072-B chunk (64 units of 2 KiB). `Flusher`
then caps the buffer's limit at the absolute position 131,060
([`:183-184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L183-L184)),
so a frame carries 131,054 B of the response; a 1 MiB value's response is **8 full
frames plus one small remainder** (from the tiny pool).

### 6b. Disallow path effect

**Not a rejection — a downgrade to unpooled allocation**, exactly as the sibling's §6b:

1. [`:443-450`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443-L450) — INFO (shared, rate-limited; §5), `return null`.
2. [`getInternal():428-431`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L428-L431) — one more `chunks.poll()`; `partiallyFreedChunks` is empty for this pool; `null`.
3. [`LocalPool.get():923`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L923) — `allocate(size, OFF_HEAP)`: a direct buffer of **exactly** the requested size (131,070 B for a full CRC frame), counted in `overflowMemoryUsage`; `Misses` ticks ([`:952-955`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L952-L955)).
4. When the buffer is put back it is freed at once (`FileUtils.clean`) and the overflow count drops ([`LocalPool.put():816-820`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L816-L820)). For a frame that is when Netty has written it to the socket and releases the wrapping `ByteBuf` ([`BufferPoolAllocator.java:147-152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L147-L152), wrapped at [`FrameEncoderCrc.java:89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoderCrc.java#L89)).

The OOM fallback (`:462-468`) is the sibling's; it leaves `memoryAllocated` bumped
(the CAS at `:452` precedes `:460`), as that case's stage-4 audit noted.

**Two accounting quirks of this pool's callers** (derived from reading):

- **`OverflowSize` drifts down for trimmed overflow buffers.** `Payload.finish()` and the
  LZ4 encoder call `putUnusedPortion()` ([`FrameEncoder.java:97-104`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoder.java#L97-L104),
  [`FrameEncoderLZ4.java:104`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoderLZ4.java#L104)).
  For an overflow buffer that subtracts `capacity − limit` without shrinking it
  ([`LocalPool.putUnusedPortion():877-887`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L877-L887)),
  and the later `put` subtracts the full capacity again (`:819`). A full native frame in an
  overflow buffer (capacity 131,070, limit 131,064 after `finish()`) leaves **−6 B** per frame
  in the gauge. The chunk-cache pool has no `putUnusedPortion` caller, so this is particular
  to the networking pool.
- **Large native-v5 requests: their frame buffers are never returned** (see §10, Target-3
  note). A request of 128 KiB or more is accumulated as `ShareableBytes` slices of its frames
  ([`AbstractMessageHandler.java:565-579`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L565-L579))
  and assembled into an envelope that wraps them without taking ownership
  ([`CQLMessageHandler.java:762-771`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L762-L771));
  on the success path `onComplete()` processes it and never calls `releaseBuffers()`
  ([`:821-835`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L821-L835);
  `releaseBuffers()`, [`AbstractMessageHandler.java:593-596`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L593-L596),
  is reached only on abort, corruption or expiry), and releasing the flushed request
  envelope releases only Netty's wrapper ([`:500-505`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L500-L505)).
  The internode twin does release them, in `deserialize()`
  ([`InboundMessageHandler.java:358-360`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L358-L360)
  through [`ChunkedInputPlus.close():72-75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/ChunkedInputPlus.java#L72-L75),
  and [`:508`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L508)).
  So each such request's last count on its frame buffers is never dropped
  ([`ShareableBytes.java:127-140`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/ShareableBytes.java#L127-L140)):
  a pooled stash pins its slots (and, with no partial recycling, its normal chunk) for the
  JVM's life, and an overflow-sized stash is freed by the garbage collector but stays in
  `OverflowSize`. Arm L of §9 tests it.

**Escape hatch: the overflow path**, unbounded, as in the sibling. See §8.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `BufferPool$Chunk` wrapping an aligned direct `ByteBuffer` of `MACRO_CHUNK_SIZE` — identical to the sibling. |
| **Resource consumed** | **Off-heap (direct) bytes**, 8 MiB + one page per slab ([`allocateDirectAligned():1095-1117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L1095-L1117)). |
| **Rough sizing** | `MACRO_CHUNK_SIZE` = 64 × 128 KiB = **8 MiB** ([`:385`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L385), stale "1 MiB" comment at `:384`, as the sibling records). The ceiling is quantised: ⌊*T* / 8 MiB⌋ × 8 MiB. One full native-v5 frame = one 128 KiB normal chunk (§6a), so the pool holds ⌊*T* / 8 MiB⌋ × 64 such frames. Requests above 128 KiB (`size > NORMAL_CHUNK_SIZE`, [`:940-944`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L940-L944)) always bypass the pool: every **full LZ4 frame** (`maxCompressedLength(131,060)` + 12 B), and every stash of a **client driver's** full frame (the bundled Python driver writes 131,071-B payloads, `cassandra/segment.py` `MAX_PAYLOAD_LENGTH`, so its frames are 131,081 B). |
| **Lifetime / release** | Slabs are never released. A normal chunk goes back to the global queue only when fully free (`recyclePartially = false`, §5). On internode event-loop threads `recycleWhenFree` is turned off ([`InboundConnectionInitiator.java:445`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundConnectionInitiator.java#L445), [`:474`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundConnectionInitiator.java#L474), [`OutboundConnectionInitiator.java:385`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnectionInitiator.java#L385)), so a fully freed chunk stays in that thread's three-slot local queue ([`LocalPool.put():839-858`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L839-L858)). The buffers handed out live until written (outbound) or decoded (inbound). |

## 8. Maximum memory bound

`networking_cache_size` bounds the **pooled** reservation of the `networking` pool,
and, as in the sibling, not the node's networking off-heap memory:

- **What it bounds.** `memoryAllocated` ≤ ⌊*T* / 8 MiB⌋ × 8 MiB; raising the knob raises it in
  8 MiB steps; any value below 8 MiB pools nothing.
- **What it does not bound.** Past the ceiling every buffer is a direct allocation counted as
  overflow, with no limit. The demand on this pool is the bytes waiting in its buffers:
  frames not yet written to a socket and frames not yet decoded. The internode senders cap
  their own in-flight frames per link with flush water marks
  ([`OutboundConnection.java:854-858`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L854-L858)),
  and the inbound handlers cap undecoded bytes with the receive-queue limits (the filed net
  cases). **The native-v5 response path has no such cap:** `Flusher` writes every frame of
  every response as soon as it is framed ([`:197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L197),
  [`:201-206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L201-L206)),
  no class in `org.apache.cassandra.transport` reads the channel's writability (grep,
  2026-10-15), and the request's in-flight byte permits are returned once its response is
  framed, before it is written ([`CQLMessageHandler.java:71-72`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L71-L72),
  [`Flusher.java:249-250`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L249-L250)).
  A client that sends requests and stops reading makes the server hold all their responses in
  this pool and, past it, in overflow — bounded by nothing but `-XX:MaxDirectMemorySize`.
  This is what §9's cluster tier uses to drive the pool.
- **How it differs from the sibling (derived).** With full-only recycling, a burst of demand
  *D* takes min(⌊*T*/8 MiB⌋ × 8 MiB, *D* rounded up to slabs) pooled and the rest as overflow, so
  **during the burst the node's direct memory for it is ≈ *D* whatever *T* is**. The overflow is
  freed as the buffers come back, but the slabs are kept, so **after the burst the node retains
  min(⌊*T*/8 MiB⌋ × 8 MiB, peak *D*) for the rest of its life**. The knob therefore bounds the
  networking pool's *retained* memory, not its peak. The sibling's chunk-cache pool, by
  contrast, fills to its limit under churn (its stage-4 finding); this pool should not.
- **Mechanism.** Refusal to reserve another slab, not refusal to allocate. The real backstop
  is the JVM's `-XX:MaxDirectMemorySize`, which the OOM handler names (`:464-467`).

**Consequence for Target 2.** Lowering `networking_cache_size` lowers what the node keeps
reserved after traffic peaks, and costs allocation churn under load; it does not cap the
off-heap memory a burst of networking traffic — or one slow-reading client — can take.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test sets `networking_cache_size`, makes one client send requests whose responses are
1 MiB each and then stop reading, so the server must hold the responses' frames in the
networking pool, and reads the pooled bytes, the overflow and the node's direct memory
during and after the stall; a separate arm checks the large-request release path. The design
reuses the sibling's stage-4 harness (sampler, Byteman counters, `made` lines). **Run so far:** none.

*Amended 2026-10-15 (stage-4 step-0 audit, before any reading; results file §1.1).* (1) **Held frames count frame-sized
buffers only:** `BufferPoolAllocator$Wrapped` also wraps Netty's inbound read buffers, whose deallocations would be counted by
an unfiltered `freed` rule, so `encoded` counts `FrameEncoderCrc.encode` calls whose payload capacity is at least 131,070 and
`freed` counts `Wrapped.deallocate()` calls whose `wrapped` buffer has capacity at least 131,070; held frames = the difference.
(2) The JIRA check that ruling (5) asked for was made (2026-10-15, Apache JIRA search API): no ticket describes native-v5
large-request frame buffers left unreleased; the nearest, CASSANDRA-20753 (`BufferPoolAllocator$Wrapped.capacity` leak on
the internode decoder), is fixed in 5.0.7, which 5.0.9 contains, and is a different path. Arm L stands as designed. (3) The run
uses its own clone `~/cassandra-run3` (the shared `~/cassandra-run1` is in use by another case's runs). Nothing in §9a changes.

### 9a. Procedure and conclusions

**Testability:** config, **restart-only** — the limit path is `static final` (§4): no setter,
no JMX. Each value costs a restart.

**Claim under test:** `networking_cache_size` caps the `networking` pool's reserved direct
memory at ⌊*T* / 8 MiB⌋ × 8 MiB; past it every buffer is allocated outside the pool with no
ceiling, so during a burst the node's direct memory follows the demand and not the knob,
while the memory retained after the burst follows the knob; and, unlike the chunk-cache
pool, a demand below the limit does not fill the pool to the limit.

**How this verifies the hypothesis** (a restatement of the claim, procedure, prediction and
conclusions in this section; it adds none):

- **Hypothesis:** pooled bytes stop at the quantised limit and the overflow takes the rest;
  the burst's direct memory is set by the demand, the post-burst retained memory by the knob;
  below the limit the pool grows only to the demand.
- **Test:** unit tier: the check on pools built like the networking one (`recyclePartially =
  false`), the recycle contrast with a chunk-cache-like pool, and the real config path with
  real frame payloads. Cluster tier: one node, `networking_cache_size` 16, 32, 64, 100 MiB and
  the default (128 MiB); a stalled native-v5 client holding 4, 48 and 192 one-MiB responses.
- **Logic:** (1) at 192 MiB the demand exceeds every value, or the run is invalid. (2) Pooled
  bytes stop at ⌊*T* / 8 MiB⌋ × 8 MiB while overflow allocations are counted: usage **stops at
  the limit** and the **disallow branch fired**. (3) The plateau moves with *T* in 8 MiB steps:
  usage **follows the constraint**. (4) The direct-memory rise during the stall is flat across
  *T*; after the client closes, the overflow returns to zero and the retained rise follows *T*:
  §8. (5) At 48 MiB with *T* ≥ 64 MiB the pool stops near 48 MiB, not at *T*: the recycling
  difference. (6) Arm L: whether large requests leave buffers unreturned.
- **Refuted if:** pooled bytes pass the threshold or do not move with *T*; the stall's direct
  memory falls with *T*; the pool fills to *T* below the limit; or the client's stall does not
  hold the frames (rows below).

**Procedure:**

1. **Unit tier** — U1 upstream `BufferPoolTest` and `BufferPoolAllocatorTest`; U2 the ceiling on
   `recyclePartially = false` pools with frame-sized requests; U3 the recycle contrast; U4 the
   config path with real `FrameEncoder.Payload`s (9e).
2. **Cluster tier** — one node, restarted per value, the stalled client of 9c.
3. **At each value:** idle control → **scenario A**, 4 responses held (below every pool) →
   **scenario M**, 48 held (just past 16 and 32 MiB, below 64 MiB and up) → **scenario B**, 192
   held (past every value) → after-B floor. Then, once, **arm L** in its own lifetime at the
   default: 64 large requests, and the residual accounting.
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *T* = `networking_cache_size` in bytes; *T*′ = ⌊*T* / 8 MiB⌋ × 8 MiB =
16 · 32 · 64 · 96 · 128 MiB at 16 · 32 · 64 · 100 · 128 MiB; *R* = responses held; each 1 MiB
response is 8 full frames of one 128 KiB normal chunk (§6a), so the demand *D* = *R* MiB; *S* = the
bytes the kernel has already taken (server send queue plus client receive queue, read with
`ss`, expected ≤ 4.2 MiB); `P` = 8 MiB × the Byteman `made` lines of the `networking` pool
(cumulative from start-up); `O` = `OverflowSize` of scope `networking`; *n*ₒ = overflow allocations
of 131,070 B.

- **Capacity:** the `Capacity` gauge = *T*; the startup line names `<T as x.000MiB> for networking`.
- **Idle:** `P` = 8 MiB (one slab; the sibling's run 1 read the networking `Size` at 8 MiB and
  `OverflowSize` 0 in every sample, idle and under 200 concurrent protocol-5 reads), `O` = 0.
- **A (*D* = 4 MiB), every value:** `P` unchanged from idle (≤ 16 MiB), `O` = 0, no refusal; the
  Byteman held-frame count = 32 − *S* / 131,064 (A may sit wholly in the kernel buffers; it is the
  below-pool control, not a demand reading).
- **M (*D* = 48 MiB):** at 16 and 32 MiB, `P` = *T*′ at every sample after the first overflow
  allocation and `P + O_peak` within [*D* − *S* − 1 MiB, *D* + 1 MiB]; at 64, 100 and 128 MiB,
  `P` after M within **[48, 56] MiB** (64 at most), `O` = 0, no refusal — **not *T*′**.
- **B (*D* = 192 MiB), every value:** `P` = *T*′ exactly at every sample after the first overflow
  allocation, never above; `O_peak` = 131,070 × *n*ₒ (outstanding) + < 1 KiB per response (the
  small remainders); `P + O_peak` within [*D* − *S* − 1 MiB, *D* + 1 MiB] = [186.8, 193] MiB at
  *S* ≤ 4.2 MiB, so `O_peak` ≈ 176 · 160 · 128 · 96 · 64 MiB − *S*; refusals > 0; `Misses` ≥ *n*ₒ;
  the INFO line at most once per lifetime (shared statement).
- **After B (client closed, 15 s), every value:** held frames 0; `P` unchanged; `O` =
  −6 B × (full frames allocated as overflow in this lifetime) — exactly, by the drift of §6b — so
  within a few KiB of zero; `UsedSize − OverflowSize` back to its idle value.
- **Real resource** (`java.nio` direct `MemoryUsed` minus the `chunk-cache` pool's `Size`, rise
  over the idle median): during B, within [*D* − *S* − 10 MiB, *D* + 10 MiB] = [178, 202] MiB at
  every value and spread across the five values ≤ 12 MiB (flat); after B, *T*′ − `P_idle` (=
  8 · 24 · 56 · 88 · 120 MiB at `P_idle` = 8 MiB), each ± 2 MiB (follows the knob); after M at 100
  and 128 MiB, `P` − `P_idle` ± 2 MiB (40–48 MiB, not 88 or 120).
- **Arm L** (derived, §6b: large-request buffers never returned). 64 prepared INSERTs of a
  1,000,000-B value, protocol v5, one at a time, then the connection closed: each request is
  7 driver frames of 131,081 B (stashed as overflow, > 128 KiB) and one of about 82,578 B
  (stashed pooled, 41 units = 83,968 B). Residuals after close and 30 s: **`OverflowSize`
  58,724,288 B** (64 × 7 × 131,081, exact) and **`UsedSize − OverflowSize` 5,373,952 B**
  (64 × 83,968, ± 64 × 2,048); the Byteman overflow-subtracted bytes short of the added bytes by
  the same 58,724,288 B; `java.nio` direct falls back towards idle after `jcmd GC.run` (the
  overflow stashes are freed by their cleaners) while `OverflowSize` does not. If the buffers
  are released after all, both residuals return to idle within one frame.

**Conclusions:**

| Result | Conclusion |
|---|---|
| B: `P` = *T*′ at every value, moving in 8 MiB steps, refusals and overflow allocations counted, `Capacity` = *T*; the stall's direct rise flat across *T*; after B the overflow returns to ≈ 0 and the retained rise follows *T*′ − `P_idle`; M leaves `P` in [48, 64] MiB at *T* ≥ 64 MiB | **Confirmed**, including §8: the limit caps the pool and its retained reservation, not the burst. Report the pooled/overflow split per value. |
| As above, but M at 100 and 128 MiB fills `P` to *T*′ | **Confirmed for the pool; §8's recycling claim refuted** — the networking pool fills to its limit like the chunk-cache pool; check U3 and re-read the recycle path (§5). |
| As above, but the stall's direct rise falls as *T* falls (beyond the 12 MiB band) | **Confirmed for the pool; §8 refuted** — the overflow is not taking the excess (check whether frames are dropped or written earlier: `ss`, held frames). |
| `P` passes *T*′ in any lifetime | **Refuted** — the CAS accounting does not hold, or a slab is allocated outside `allocateMoreChunks()`. |
| `P` does not move with *T* across 16–128 MiB in B | **Refuted** — not the binding limit; check the startup line, then re-read, do not re-run. |
| `O` > 0 while `P` < *T*′, or overflow bytes ≠ 131,070 × *n*ₒ (+ remainders) | **Not confirmed** — another overflow cause (an oversize or LZ4 frame, §7; the OOM fallback): read the allocation sizes in the trace. |
| After B, `O` stays well above zero or held frames > 0 | **Not confirmed** for the release path — frames of a closed connection are not returned; record the residual (Target-3 material). |
| Held frames stay near zero during B's stall, or `P` and `O` do not move in B | **Invalid run** — the client read its socket or *S* absorbed the responses; check `stall-client.py` and `ss`, and re-run. |
| No refusal at 128 MiB in B | **Invalid run** — the demand did not exceed the pool; raise *R* (9c). |
| `failed to allocate chunk` in the log | **Invalid run** — native memory ran out first; raise `-XX:MaxDirectMemorySize`. |
| Arm L: residuals ≈ 58.7 MB `OverflowSize` and ≈ 5.4 MB `UsedSize − OverflowSize`, subtracted bytes short by the same | **Leak as derived** — Target-3 and upstream material (§10); the pool's accounting and its slots are lost per large request. |
| Arm L: both residuals back at idle | **No leak** — the release happens on a path §6b missed; the §10 note is withdrawn. |
| Arm L: residuals present but not at the predicted figures | **Not confirmed** — read the stash and overflow counts per request before concluding. |
| Unit: any U2–U4 assertion fails | As the same rows above, at unit level (U3's false-pool growth = the second row). |

**Why not `Size` alone:** `Size` includes the overflow, and the sibling's run found the
sampler's `Size − OverflowSize` unreliable under load (two attribute reads apart), so `P` is
taken from the `made` lines and the sampler figure is a cross-check.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `networking_cache_size: <n>MiB` in `cassandra.yaml`; absent for the default ([`DatabaseDescriptor.java:573-574`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L573-L574)). Restart-only. Unit tier: `new BufferPool(name, bytes, false)` ([`BufferPool.java:187`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L187)), or for the real instance the raw config before `BufferPools` loads, as upstream `BufferPoolAllocatorTest` does ([`BufferPoolAllocatorTest.java:39-46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/net/BufferPoolAllocatorTest.java#L39-L46)). |
| **Confirm it took effect** | `logs/system.log`: `Global buffer pool limit is 512.000MiB for chunk-cache and <n>.000MiB for networking` ([`BufferPools.java:47-55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L47-L55)); gauge `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=Capacity`. |
| **Capacity values** | `16MiB`, `32MiB`, `64MiB`, `100MiB` (not a multiple of 8 MiB: 96 MiB expected), and unset (128 MiB at `MAX_HEAP_SIZE=4G`; record the resolved value). |
| **Scope** | **Per pool, node-wide.** One `networking` pool per JVM, shared by every connection; N = 1. The demand is one client connection's held responses. |
| **Level** | Both. Unit: upstream `BufferPoolTest` ([`:159-164`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/utils/memory/BufferPoolTest.java#L159-L164) already builds a `recyclePartially = false` pool below one slab) and `BufferPoolAllocatorTest` (the networking instance through `GlobalBufferPoolAllocator`, [`:209-213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/net/BufferPoolAllocatorTest.java#L209-L213)), plus the harness tests (9c). Cluster: for the demand curve and direct memory. |

**What drives the pool, and why a stalled client.** A single node has no internode traffic,
so its networking pool serves only native-v5 connections (§6a). Ordinary traffic barely moves
it: the sibling's run kept it at one slab under 200 concurrent reads, because each response
frame is written and returned within microseconds. A held response frame is one that Netty
cannot write: the client stops reading, the kernel buffers fill (*S*), and every further frame
waits in Netty's outbound buffer, still in its pool or overflow buffer, until the connection
closes ([`Flusher.java:201-206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Flusher.java#L201-L206),
nothing caps it, §8). The demand is then set by the request count, not by timing. Closing the
connection fails the queued writes and Netty releases each frame's `ByteBuf`, which puts the
buffer back ([`BufferPoolAllocator.java:147-152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/BufferPoolAllocator.java#L147-L152)).
No request is held, so the 12 s `native_transport_timeout` trap of earlier runs does not apply:
each request completes at once and only its response waits.

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| JVM | `MAX_HEAP_SIZE=4G`; `JVM_EXTRA_OPTS` = `-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=8G` + the Byteman agent (scoped to the `bin/cassandra` command) | The default derives from the heap; the JVM backstop must not bind; HotSpot takes the last of the two `MaxDirectMemorySize` flags (sibling §1.2). |
| Node | one node, no peers, loopback | No internode or streaming use of the pool. |
| `file_cache_size` | default (512 MiB) | The other pool; its INFO line shares the statement (§5); its `Size` is subtracted from the direct reading. |
| `native_transport_idle_timeout` | `0ms` (default) | A non-zero value would close the stalled connection. |
| `native_transport_max_threads`, `concurrent_reads` | defaults (128, 32) | 192 requests of an in-memory-sized read finish in well under a second at the defaults; the stall is on the response side. |
| Client compression | none (CRC frames) | A full LZ4 frame never fits the pool (§7). |
| Protocol | v5 for the stall client and arm L; v4 for the dataset load | v4 does not use this pool (§6a), so loading 1 MiB values does not touch it. |
| Table | `ks1.t (pk int PRIMARY KEY, v blob)`, default compression, RF 1; 8 rows, `pk` 0–7, `v` 1,048,576 random bytes; built once and flushed | The responses; read through the chunk-cache pool, which the direct reading subtracts. |
| `memtable_allocation_type` | `heap_buffers` (default; start from `conf/cassandra.yaml`) | Off-heap memtables also allocate direct memory. |
| Kernel | record `sysctl net.ipv4.tcp_wmem net.ipv4.tcp_rmem`; the client sets `SO_RCVBUF` 65,536 before connecting | Bounds *S*. |

**Controls:** the idle floor of every lifetime; scenario A (below every pool) at every value;
scenario M at 64–128 MiB (below the pool: the recycling control); the after-B floor.

**Reset between runs:** stop the node (`bin/nodetool stopdaemon`), check no `CassandraDaemon` is
left, move `logs/` aside, edit `networking_cache_size`, start. Keep the data directory. Arm L
runs last, in its own lifetime (its residuals persist until restart).

### 9c. Workload

**Harness.** `<harness>` =
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/networking_cache_size-allocateMoreChunks-memoryUsageThreshold`.
Work for step 1; copy what fits from the sibling's harness folder.

| File | What it is |
|---|---|
| `NetworkingPoolCeilingTest.java` | Unit U2–U3, package `org.apache.cassandra.utils.memory` (9e). |
| `NetworkingPoolConfigTest.java` | Unit U4, package `org.apache.cassandra.net` (its own JVM: `BufferPools` is static). |
| `unit-run.sh` | Runs U1–U4. |
| `PoolSampler.java` | The sibling's sampler with scopes swapped: every second, in one pass, `Capacity`, `Size`, `UsedSize`, `OverflowSize`, `Hits`, `Misses` of `networking`, `Size` and `OverflowSize` of `chunk-cache`, and `java.nio` direct `MemoryUsed` and `Count`. |
| `net.btm` | Byteman, copying the sibling's `hold.btm` style (counting rule + conditional trace rule; no `if` blocks): `made`, `refuse`, `overflow` (count and bytes, `BufferPool.allocate`) filtered on `name.equals("networking")`; `ovfsub`: bytes subtracted at `BufferPool.updateOverflowMemoryUsage(int)` when `$1 < 0` (networking); `payload`: `FrameEncoder$Payload.<init>(boolean,int,int,int)` at exit, counted as full (capacity ≥ 131,070) or small; `encoded`: `FrameEncoderCrc.encode` exits for payloads of capacity ≥ 131,070; `freed`: `BufferPoolAllocator$Wrapped.deallocate()` entries with `$0.wrapped != null` and `$0.wrapped.capacity() >= 131070` (held frames = encoded − freed; amended 2026-10-15); a `dump` line on `StorageService.getReleaseVersion()`. |
| `stall-client.py <R> <stop-file>` | Raw socket, `SO_RCVBUF` 65,536 then connect; STARTUP/READY at protocol v5 (unframed), then *R* `QUERY` messages `SELECT v FROM ks1.t WHERE pk = <i mod 8>`, each in its own self-contained CRC frame, encoded with the bundled driver's `cassandra.protocol` and `cassandra.segment.SegmentCodec` (`lib/cassandra-driver-internal-only-3.29.0.zip`); written in one burst, **never reads after READY**; closes with `SO_LINGER` 0 when the stop file appears. Prints the bytes written. |
| `send-cql.py` | Bundled driver: `probe`; `build` (protocol 4: schema and the 8 rows, then `nodetool flush ks1 t`); `big-insert <N>` (protocol 5, prepared `INSERT INTO ks1.t (pk, v) VALUES (?, ?)`, `pk` 1000 + *i*, 1,000,000 random bytes, one at a time, then `cluster.shutdown()`). |
| `make-node-yaml.sh <MiB\|default>` | The tag's yaml plus the `networking_cache_size` line. |
| `cluster-run.py build\|instrument\|value <v>\|leak` | The lifetimes of 9e; logs `session.log`, `summary.txt` (`EXPECTED:` lines), `samples.csv`, `phases.csv`, `ss/`, `nmt/`, `bm.trace`. Stops on a failed instrument check; stops the node on any exit. |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.utils.memory.BufferPoolTest
ant testsome -Dtest.name=org.apache.cassandra.net.BufferPoolAllocatorTest
cp <harness>/NetworkingPoolCeilingTest.java test/unit/org/apache/cassandra/utils/memory/
cp <harness>/NetworkingPoolConfigTest.java test/unit/org/apache/cassandra/net/
ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NetworkingPoolCeilingTest
ant testsome -Dtest.name=org.apache.cassandra.net.NetworkingPoolConfigTest

# cluster tier
<harness>/cluster-run.py build              # once, default yaml
<harness>/cluster-run.py instrument         # shakedown at 16 MiB, not a reading
for v in 16 32 64 100 default; do <harness>/cluster-run.py value $v; done   # each its own background job
<harness>/cluster-run.py leak               # arm L, default
```

| Item | Value |
|---|---|
| Demand | *R* = 4 (A), 48 (M), 192 (B) responses of 8 full frames: *D* = 4, 48, 192 MiB. 192 MiB exceeds the largest value (128 MiB) by 64 MiB, far more than *S* (≤ 4.2 MiB). |
| Hold | Each scenario: start the client, wait until the Byteman `payload` full count has risen by 8 *R* (all responses framed; the run script reads `ReleaseVersion` once a second to trigger `dump` lines; expect under 2 s, and a wait over 30 s is a runbook defect), sample 20 s (A 10 s), touch the stop file, wait 10 s. |
| Per value | One lifetime: start, `probe`, idle 30 s, A, M, B, after-B 15 s, stop. About 3 minutes. |
| Arm L | One lifetime at the default: idle 30 s, `send-cql.py big-insert 64` (about 64 MB written to the memtable and commit log), 30 s, `jcmd <pid> GC.run`, 10 s, stop. |
| Memory | Peak direct ≈ 200 MiB pool + overflow at B, plus Netty's own arenas for response bodies (1 MiB each, transient); 8 GiB direct limit, 4 GiB heap. |

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — pooled reservation `P` | 8 MiB × the `made` lines of `net.btm` (`networking` only); cross-check `Size − OverflowSize` of scope `networking` from `PoolSampler` ([`BufferPoolMetrics.java:50-65`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java#L50-L65)). | Each `made` line; sampler 1 s | `made` is cumulative from start-up (the idle slab included). The sampler's difference is approximate under load (sibling §1.2). Scope `networking`, not `chunk-cache`. |
| **Disallow evidence** | `refuse` count (null exit of `allocateMoreChunks`, networking); `overflow` count and bytes (131,070 per full frame); `Misses` rising; the INFO line `Maximum memory usage reached (<T>) for networking buffer pool, cannot allocate chunk of 8.000MiB`. | `dump` at each phase edge | The INFO line is one per 15 min per JVM **across both pools** (§5): presence confirms, absence does not refute. `Misses` also ticks for oversize requests (`:940-944`), which this workload does not make. |
| **Bypass volume** — overflow | `OverflowSize` peak per scenario; the `overflow` rule's bytes per allocation show what was served around the pool: 131,070 B per full frame, the rest small remainders under 1 KiB. | 1 s | A gauge of bytes outstanding. It **drifts −6 B per overflowed full frame** (§6b), so it ends slightly negative after B. |
| **Demand evidence** | `payload` full count (8 per response), held frames = `encoded` − `freed`; *S* from `ss -tnmi '( sport = :9042 )'` (server `Send-Q`) and the client's `Recv-Q`. | At each scenario's peak; after close | If held frames ≈ 0 the client is reading: invalid (9a). |
| **Real resource** | `java.nio:type=BufferPool,name=direct` `MemoryUsed` (sampler) minus the `chunk-cache` `Size`, as a rise over the idle median; NMT `Other` at idle, at B's peak and after B, recorded only. | 1 s; NMT 3 times per lifetime | `allocateDirect` (slabs + one page, overflow buffers) is in the `java.nio` count; Netty's no-cleaner arenas, which hold the response bodies, are not, but are in NMT `Other` (sibling's supplementary run), so NMT is not this pool's measure. Never RSS. |
| **Arm L residuals** | `OverflowSize`, `UsedSize − OverflowSize` (scope `networking`) at idle and 30 s after the connection closed; `overflow` bytes added vs `ovfsub` bytes; `java.nio` direct before and after `jcmd GC.run`. | Phase edges of arm L | Only arm L sends requests of 128 KiB or more; no other scenario does. |

### 9e. Running the scenarios

**Unit tier.** Commands in 9c. Record pass or fail and every printed figure.

1. **U1** — upstream `BufferPoolTest` and `BufferPoolAllocatorTest`: record pass or fail.
2. **U2, the ceiling** (`NetworkingPoolCeilingTest`): for *T* in {0, 4, 16, 20, 64, 100} MiB,
   `new BufferPool("stage4-net", T, false)`, one thread:
   1. `getAtLeast(131070, OFF_HEAP)` repeatedly, holding every buffer, until the first one whose
      capacity is not 131,072: assert pooled (`sizeInBytes() − overflowMemoryInBytes()`) =
      *T*′ (0, 0, 16, 16, 64, 96 MiB), pooled buffers = 64 × *T*′ / 8 MiB (0, 0, 128, 128, 512, 768),
      each of capacity 131,072, and that first other buffer of capacity exactly 131,070 with
      overflow = 131,070;
   2. five more: each non-null, capacity 131,070, overflow = 6 × 131,070 = 786,420 B,
      `Misses` +5, pooled unchanged;
   3. `tryGetAtLeast(131070)` returns `null`;
   4. put the six overflow buffers back: overflow 0;
   5. put all back, then take the same count again: served with pooled unchanged and overflow 0
      (fully free chunks are reused, no new slab).
3. **U3, the recycle contrast** (same class): pools of 64 MiB with `recyclePartially` `false` and
   `true`, each with a `Debug` hook (`bufferPool.debug(...)`, same package) counting
   `recycleNormal` and `recyclePartial`. One thread, 64 KiB buffers (two per normal chunk),
   20,000 steps of: `get` one buffer, append it to a FIFO of 8, and when the FIFO holds 9, put the
   oldest. With three chunks per local queue and four or more chunks spanned by the FIFO, chunks
   are evicted while some of their buffers are out. Predict (derived, §5): **`false`**:
   `recyclePartial` = 0, pooled = 8 MiB at the end, overflow 0; **`true`**: `recyclePartial` > 0
   and pooled above 8 MiB (expected to reach 64 MiB, the sibling's mechanism). If the `true` pool
   shows `recyclePartial` = 0, the pattern did not evict a part-used chunk: change the FIFO length
   and record it; that is not a result.
4. **U4, the real instance** (`NetworkingPoolConfigTest`): `@BeforeClass`
   `DatabaseDescriptor.clientInitialization()` and raw `networking_cache_size` = 16 MiB (as
   `BufferPoolAllocatorTest`). Assert `BufferPools.forNetworking().memoryUsageThreshold()` =
   16,777,216; take `FrameEncoderCrc.instance.allocator().allocate(false,
   Flusher.MAX_FRAMED_PAYLOAD_SIZE)` and hold: payloads 1–128 have buffer capacity 131,072 and the
   pool's pooled figure reaches 16 MiB; payload 129 has capacity 131,070 and `OverflowSize` =
   131,070. Fill each as `Flusher` does (`buffer.limit(Flusher.MAX_FRAMED_PAYLOAD_SIZE)`, then
   write bytes up to the limit), then `finish()` and `release()`: overflow ends at −6 (the drift of
   §6b, one overflowed full frame; an unfilled payload would leave −131,060 instead) and pooled
   stays 16 MiB.

**Before the cluster tier.** `cluster-run.py build`: schema, the 8 rows over protocol 4, flush,
check one `-Data.db` for `ks1.t` and `SELECT pk FROM ks1.t` returns 8 rows. Then
`cluster-run.py instrument` at 16 MiB, a shakedown: startup line and `Capacity`; one sampler row;
`stall-client.py 8`: the `payload` full count rises by 64, held frames ≈ 64 − *S* / 131,064,
`ss` shows the server's `Send-Q` > 0 and the connection established; after the stop file, held
frames return to 0 and `O` to ≈ 0. Stop on any failure.

**Cluster tier, for each value** (`cluster-run.py value <v>`, *v* = 16, 32, 64, 100, default, in
that order, each its own lifetime and background job):

1. **Control** — start with the JVM options of 9b; record the startup line, `Capacity`, the
   `sysctl` values; `probe`; idle 30 s: floors of `P`, `O`, `UsedSize`, direct, NMT.
2. **Scenario A** — `stall-client.py 4`; at the peak record `P`, `O`, held frames, `ss`; stop file.
3. **Scenario M** — `stall-client.py 48`; as A, 20 s; stop file; 10 s.
4. **Scenario B** — `stall-client.py 192`; as A, 20 s, with NMT once at the peak; `dump`; stop file.
5. **After B** — 15 s: `P`, `O`, `UsedSize`, held frames, direct, NMT; grep the INFO line; stop the
   node; check nothing is left.

**Arm L** (`cluster-run.py leak`, default yaml, its own lifetime): control as above; `dump`;
`send-cql.py big-insert 64`; record that every insert was acknowledged; 30 s; `dump` and the
residuals of 9d; `jcmd <pid> GC.run`; 10 s; direct again; stop.

**Record for stage 4:** the yaml diff and JVM options in force, the `sysctl` values, the exact
commands, the shakedown, every reading of 9d per scenario and value, and the unit tier's printed
figures.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — found 2026-09-22 by the capacity-word pass as the second instance of `BufferPool_memoryUsageThreshold` (`pending.md`, "From the capacity-word pass"); when that candidate was filed as `file_cache_size` on 2026-09-28, this instance stayed open and became write-up queue item 10. No stage-2 row. Written up 2026-10-15. |
| **Filed by / Date** | Claude (`claude-opus-5-5`, AI long path), 2026-10-15. |
| **Line numbers checked** | 2026-10-15, every cited line against the local clone `/home/user/cassandra-src` at `cassandra-5.0.9` (`git describe --tags`), by a script that printed each cited line. |
| **Escape hatch / Target-3 note** | **The overflow path**, unbounded, as in the sibling: the limit bounds the pool, not the buffers. Three notes particular to this pool: (1) **a native-v5 client that stops reading makes the server hold every response frame** in this pool and past it in overflow; nothing in `transport` caps the backlog (§8). (2) **Large native-v5 requests (128 KiB and up) never return their frame buffers**, derived from reading (§6b): pooled stashes pin their slots and chunks for the JVM's life, overflow stashes are freed by the garbage collector but stay counted in `OverflowSize`; the internode path does release them; no upstream JIRA ticket found (2026-10-15); **observed at stage 4 (arm L, 2026-10-15)**. (3) Every full LZ4 frame, and every stash of a driver's full frame, is larger than a normal chunk and always overflows (§7). |
| **Stage-4 feedback** | **Closed 2026-10-15: unit Confirmed; cluster Confirmed (§9a row 1, including §8); arm L leak as derived; no run 2** ([results](../../../stage4-runtime-verification/long-path/results/networking_cache_size-allocateMoreChunks-memoryUsageThreshold.md); uncommitted). Step-0 audit Ready after amendments (§9 `f322bcbc…`, §9a `1d1fbf68…` unchanged; held frames counted on frame-sized buffers only; the JIRA check of ruling (5): no ticket for this path, CASSANDRA-20753 is a different leak fixed in 5.0.7). Run 1 on `pc57`: with 192 MiB of held response frames `P` = 16 · 32 · 64 · 96 · 128 MiB exactly at 16 · 32 · 64 · 100 MiB and unset, the rest as overflow (1,390–494 refusals), the stall's direct rise 182.8–183.3 MiB at every value (flat), the retained rise after it 9.6 · 25.2 · 57.0 · 89.0 · 121.1 MiB (= *T*′ − 8 MiB, within 1.7 MB), `OverflowSize` −6 B per overflowed frame exactly; 48 MiB of demand left the pool at 48 MiB at 64 MiB and up (§8's recycling difference observed; unit U3: 8 MiB vs 64 MiB for the chunk-cache-like pool). **Arm L: 64 one-MB INSERTs over v5 leave `OverflowSize` +58,724,288 B and 5,373,952 B of pooled slots that are never returned** (overflow bytes added 58,724,288, subtracted 0) — the derived leak of §6b is observed; candidate for an upstream report. |
| **Notes** | **Corrections to the queue note** (`pending.md` item 10): it is the same check, but not the same pool behaviour — `recyclePartially = false`, so the sibling's stage-4 finding that the pool fills to its limit should not carry over (§5, §8; tested by U3 and M); and the frames of `FrameEncoder.Payload` (`FrameEncoder.java:32`, `:64`, correct as cited) are one caller among several (§6a: Netty read buffers on internode and native-v5 channels, frame stashes, LZ4 frames, streaming). The send-queue case's §7 says the delivery's frames are "bounded elsewhere (the networking pool …)": the pool does not bound them, it only decides how many are pooled; the flush water marks bound them. **Also found:** the deprecated `buffer_pool_use_heap_if_exhausted` ([`Config.java:512-514`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L512-L514)) is still documented in the yaml but read by nothing: overflow is always off-heap, for both pools. |

---

## 11. Notes

- **Reused from the sibling's stage 4, re-checked here:** the disallow path allocates
  directly and the limit bounds the pool, not the memory (holds: same chain, and no networking
  caller uses `tryGet`); `P` read from the Byteman `made` lines rather than `Size −
  OverflowSize` (adopted); start-up reservation (one networking slab, from the sibling's
  samples, so the idle `P` is 8 MiB); the INFO line once per lifetime (holds, and the statement
  is shared with the chunk-cache pool); NMT `Other` not the pool's measure (adopted: the
  decision uses `java.nio` direct). **Not carried over:** partial recycling before reuse, which
  filled the chunk-cache pool to its limit; this pool has `recyclePartially = false`.
- **Why not an internode workload.** A two-node loopback ring would exercise the internode
  callers, but their demand is capped by other mechanisms before it reaches this pool's
  ceiling: per-link flush water marks on the outbound side, and the receive-queue capacities
  (4 MiB per connection, the reserves behind it; filed cases) on the inbound side. The run
  would measure those limits, not this one. The native-v5 stall has no such cap (§8) and needs
  only one node.
- **Pre-v5 clients do not touch this pool.** A cluster whose clients speak protocol v4 keeps
  its networking pool idle on a single node; the pool's size then reflects internode and
  streaming traffic only.
- **The `-6 B` drift** (§6b) is harmless in size but makes `OverflowSize` an imperfect
  counter for this pool; the prediction uses it as an exactness check, not as a measurement.
