# file_cache_size — buffer pool macro chunk

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | FILE_CACHE_SIZE-ALLOCATEMORECHUNKS-MEMORYUSAGETHRESHOLD |
| **Constraint** | `file_cache_size` — a **configuration entry** ([`Config.java:496-497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L496-L497), `DataStorageSpec.IntMebibytesBound`, auto-sized when unset to `min(512MiB, maxMemory/4)`). It is the threshold for the **`chunk-cache`** `BufferPool`; the same check on the **`networking`** pool takes its threshold from `networking_cache_size` — see §11, that is a sibling case, not this one. |
| **Enforcement pattern** | **(a)** — the `if` is itself the decision: one arm returns `null`, the other falls through to the allocation. |
| **Capacity check** | [`BufferPool$GlobalPool.allocateMoreChunks():443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443) — `cur + MACRO_CHUNK_SIZE > memoryUsageThreshold`. |
| **Decision point** | The same statement — [`:443-450`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443-L450): the disallow arm logs and `return null`; the allow arm CASes `memoryAllocated` and breaks out of the loop to the allocation. |
| **Allocation site** | [`:460`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L460) — `chunk = new Chunk(null, allocateDirectAligned(MACRO_CHUNK_SIZE))`, an **8 MiB** aligned direct `ByteBuffer` (see §7 on the stale comment). |
| **Related cases** | [`memtable_offheap_space-tryAllocate-limit.md`](memtable_offheap_space-tryAllocate-limit.md) — the other off-heap byte ceiling in the folder, and a useful contrast: that one's accounting is decoupled from the physical allocation, this one's is not. Sibling not yet filed: the `networking_cache_size` instantiation of this same check (§11). |

```java
// BufferPool$GlobalPool.allocateMoreChunks():438-470 — the check and the allocation.
private Chunk allocateMoreChunks()
{
    while (true)
    {
        long cur = memoryAllocated.get();
        if (cur + MACRO_CHUNK_SIZE > memoryUsageThreshold)          // <-- capacity check, :443
        {
            if (memoryUsageThreshold > 0)
            {
                noSpamLogger.info("Maximum memory usage reached ({}) for {} buffer pool, cannot allocate chunk of {}",
                                  readableMemoryUsageThreshold, name, READABLE_MACRO_CHUNK_SIZE);
            }
            return null;                                            // <-- DISALLOW, :449
        }
        if (memoryAllocated.compareAndSet(cur, cur + MACRO_CHUNK_SIZE))
            break;                                                  // <-- ALLOW, :452-453
    }

    // allocate a large chunk
    Chunk chunk;
    try
    {
        chunk = new Chunk(null, allocateDirectAligned(MACRO_CHUNK_SIZE));   // <-- allocation, :460
    }
    catch (OutOfMemoryError oom)
    {
        noSpamLogger.error("{} buffer pool failed to allocate chunk of {}, current size {} ({}). "
                         + "Attempting to continue; buffers will be allocated in on-heap memory which can degrade performance. ...", ...);
        return null;
    }
```

```java
// BufferPool$LocalPool.get():904-924 — what the caller does with a null chunk.
// This is the escape hatch: the pool limit is not a ceiling on the buffer, only on the pool.
ByteBuffer ret = tryGet(size, sizeIsLowerBound);
if (ret != null)
    return ret;

// ... trace logging only ...

return allocate(size, BufferType.OFF_HEAP);     // ByteBuffer.allocateDirect(size), counted as OVERFLOW
```

## 2. Context

Cassandra reads compressed data off disk and has to hold the decompressed form
somewhere while it is used. Allocating a fresh off-heap buffer for every such
read and releasing it immediately would churn native memory badly, so instead
the node keeps a pool: it reserves large slabs of direct memory up front and
hands out slices of them, recycling each slice when the reader is done. The
chunk cache — which keeps decompressed file data around in case it is read
again — is the pool's main customer, and its buffers can be held for arbitrary
periods.

This check is the ceiling on how large that pool may grow. Before carving out
another slab, it adds the slab's size to the bytes already reserved and refuses
if the total would exceed a configured limit. The refusal is not an error: the
caller simply allocates its buffer directly from the operating system instead,
outside the pool. So the limit governs how much memory the node manages *as a
pool*, not how much off-heap memory it can end up using — a distinction that
matters a great deal when reading a memory graph, and one this case's §8
spends most of its time on.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `buffer_pool` — off-heap buffer pooling for file reads and networking (`utils/memory/BufferPool`, `utils/memory/BufferPools`, with the chunk cache in `cache/ChunkCache`) |
| **One-line role** | `BufferPool` reserves large aligned slabs of direct memory and sub-allocates them to callers so that short-lived off-heap buffers are recycled instead of repeatedly allocated; two pool instances exist, one for the chunk cache and one for networking. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes** — a running total of reserved off-heap bytes (`memoryAllocated`) plus the next slab's size, compared against a configured byte ceiling. |
| **Usage-side operand** | `memoryAllocated` — the pool's `AtomicLong` of bytes reserved as macro chunks, read into `cur` at [`:442`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L442) and CASed at [`:452`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L452). Note it counts **reserved** bytes, not bytes in use — `usedSizeInBytes()` is a separate figure. |
| **Limit-side operand** | `memoryUsageThreshold` — `private final long` on `BufferPool` ([`:143`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L143)), assigned once in the constructor at [`:190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L190). |
| **Limit type** | **Configuration entry**, converted MiB → bytes at pool construction. |

**Limit initialization path.**

1. [`Config.file_cache_size:496-497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L496-L497) — declared, `DataStorageSpec.IntMebibytesBound`, **no default in the field**.
2. [`DatabaseDescriptor.applyConfig():576-577`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L576-L577) — when unset, auto-sized to `min(512MiB, maxMemory / 4)`. **Heap-derived**, so the default moves with `-Xmx`.
3. [`DatabaseDescriptor.getFileCacheSizeInMiB():3784`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3784) — read in MiB.
4. [`BufferPools.FILE_MEMORY_USAGE_THRESHOLD:38`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L38) — `getFileCacheSizeInMiB() * 1024L * 1024L`, a `private static final long`.
5. [`BufferPools.CHUNK_CACHE_POOL:39`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L39) — `new BufferPool("chunk-cache", FILE_MEMORY_USAGE_THRESHOLD, true)`, also `static final`.
6. [`BufferPool` constructor `:187-191`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L187-L191) — stored as the `final memoryUsageThreshold` the check at `:443` reads.

**Everything on that path is `static final`**, so the limit is fixed for the
JVM's lifetime: there is no setter, no JMX operation and no live re-read. A
change costs a restart. The value is logged at startup by the static
initializer at [`BufferPools.java:47-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L47-L53)
("Global buffer pool limit is X for chunk-cache and Y for networking"), which
is the cheapest way for stage 4 to confirm the resolved figure.

**Naming note (Target 1).** The limit-side operand `memoryUsageThreshold` is a
constructor parameter with **two** config sources, one per pool instance.
README §6.1's rule for a configuration entry names the case after the config,
so this is the `file_cache_size` case and the `networking` pool's is a separate
one — exactly the precedent set by `memtable_heap_space` /
`memtable_offheap_space`, which are two cases over one `tryAllocate()` check.
This resolves the open naming question `pending.md` recorded for this candidate
on 2026-09-22.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`BufferPool$GlobalPool.allocateMoreChunks():443-453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443-L453) — the check is the decision. |
| **Verdict** | n/a — pattern (a). |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `memoryAllocated + MACRO_CHUNK_SIZE <= memoryUsageThreshold` | CAS bumps `memoryAllocated` by `MACRO_CHUNK_SIZE`, loop breaks, and [`:460`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L460) allocates an 8 MiB aligned direct buffer wrapped in a new `Chunk`. |
| **Disallow** | `memoryAllocated + MACRO_CHUNK_SIZE > memoryUsageThreshold` | Logs at INFO through a `NoSpamLogger` and returns `null`. **No `Chunk` is created and `memoryAllocated` is not bumped** — the accounting and the allocation stay consistent, unlike the off-heap memtable case. |

```java
// allow: reserve, then create the chunk
if (memoryAllocated.compareAndSet(cur, cur + MACRO_CHUNK_SIZE))
    break;
...
chunk = new Chunk(null, allocateDirectAligned(MACRO_CHUNK_SIZE));
```

```java
// disallow: log and refuse — nothing is created, nothing is counted
noSpamLogger.info("Maximum memory usage reached ({}) for {} buffer pool, cannot allocate chunk of {}",
                  readableMemoryUsageThreshold, name, READABLE_MACRO_CHUNK_SIZE);
return null;
```

### The refusal is absorbed one level up, and the memory is still allocated

Rule 3 is satisfied at the check — the `Chunk` genuinely is withheld — but
tracing the caller is what makes this case useful, and it is the first pitfall
in the playbook:

1. [`GlobalPool.getInternal():417-431`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L417-L431) — on `null`, retries `chunks.poll()` once more, then falls back to `partiallyFreedChunks.poll()`, and may still return `null`.
2. [`LocalPool.get():904-924`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L904-L924) — when `tryGet` comes back `null`, it logs at TRACE and **returns `allocate(size, BufferType.OFF_HEAP)`**.
3. [`BufferPool.allocate():233-238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L233-L238) — `updateOverflowMemoryUsage(size)` then `ByteBuffer.allocateDirect(size)`.

**So the caller always gets its buffer.** What the limit decides is whether
that buffer comes from the pool or straight from the OS. Cassandra is candid
about this: the bytes allocated outside the pool are tracked separately as
`overflowMemoryUsage` ([`:149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L149)),
exposed as its own metric, and added back in by `sizeInBytes()` at
[`:276`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L276).
The overflow has **no ceiling of its own**.

The `tryGet` / `tryGetAtLeast` entry points at
[`:224-230`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L224-L230)
are the exception — their contract is explicitly "returns null if the pool is
exhausted", so callers using those do see the refusal. Which callers use which
entry point was not enumerated here; §9e leaves it as the question a null
result would raise.

## 6. Code path

### 6a. Allow path → object creation

1. A reader needs an off-heap buffer: [`BufferPool.get(size, bufferType):206-211`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L206-L211) → `localPool.get().get(size)`.
2. [`LocalPool.tryGet():926-...`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L926) — no local chunk has room, so it asks the global pool.
3. [`GlobalPool.getInternal():419-423`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L419-L423) — the recycled-chunk queue is empty, so `allocateMoreChunks()`.
4. [`:442-443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L442-L443) — check passes.
5. [`:452`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L452) — `memoryAllocated` CASed up by `MACRO_CHUNK_SIZE`.
6. [`:460`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L460) — **object creation**: `allocateDirectAligned(MACRO_CHUNK_SIZE)` reserves 8 MiB of direct memory; `new Chunk(...)` wraps it.
7. The chunk is sub-divided into normal chunks and slices, which is what the caller actually receives; the 8 MiB stays reserved until the pool releases it.

### 6b. Disallow path effect

**Not a rejection — a downgrade to unpooled allocation.**

1. [`:443-450`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443-L450) — `noSpamLogger.info("Maximum memory usage reached ...")`, `return null`. Note the log is suppressed when `memoryUsageThreshold <= 0`, and `NoSpamLogger` rate-limits it, so it is a weak signal under sustained pressure.
2. [`getInternal():425-431`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L425-L431) — one more `chunks.poll()`, then `partiallyFreedChunks.poll()`; may return `null`.
3. [`LocalPool.get():923`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L923) — **`return allocate(size, BufferType.OFF_HEAP)`**: the buffer is allocated directly from the OS, counted in `overflowMemoryUsage`, and handed to the caller as if nothing happened. The only trace is a TRACE-level log line.
4. `Misses` on `BufferPoolMetrics` ticks; `OverflowSize` rises.

**A second, distinct fallback on OOM.** If `allocateDirectAligned` itself
throws `OutOfMemoryError` at [`:462-468`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L462-L468),
the pool logs an ERROR naming `-XX:MaxDirectMemorySize` and also returns
`null` — so a genuine native-memory exhaustion is funnelled into the same
overflow path. Worth knowing when reading a run: a `null` from this method does
not distinguish "over the configured limit" from "out of native memory", and
only the log level tells them apart.

**Escape hatch: the overflow path itself**, and it is unbounded. See §8.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `BufferPool$Chunk`, wrapping an aligned direct `ByteBuffer` of `MACRO_CHUNK_SIZE`. |
| **Resource consumed** | **Off-heap (direct) bytes.** |
| **Rough sizing** | `MACRO_CHUNK_SIZE = 64 * NORMAL_CHUNK_SIZE` ([`:385`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L385)) with `NORMAL_CHUNK_SIZE = 128 << 10` ([`:128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L128)) — i.e. **8 MiB**, fixed. **The comment above `MACRO_CHUNK_SIZE` says "1 MiB" and is stale**; the arithmetic gives 8 MiB. This matters for the test design, because the ceiling is quantised in 8 MiB steps (§9d). |
| **Lifetime / release** | A macro chunk is held by the pool and recycled between callers rather than freed per use; `memoryAllocated` is decremented only when the pool actually releases a chunk. For the `chunk-cache` pool, `recyclePartially` is `true`, so partially-freed chunks are reused before new ones are taken. |

## 8. Maximum memory bound

`file_cache_size` bounds the **pooled** off-heap bytes of the `chunk-cache`
pool, and that is a narrower claim than the config name suggests:

- **What it bounds exactly.** `memoryAllocated` cannot exceed `memoryUsageThreshold`, and because the comparison is `cur + MACRO_CHUNK_SIZE > threshold` the pool stops one whole chunk short: the effective ceiling is `floor(threshold / 8MiB) × 8MiB`. Raising the config raises that ceiling proportionally, in 8 MiB steps.
- **What it does not bound.** Once the pool is at its ceiling, callers do not fail and do not wait — they allocate directly from the OS and the bytes land in `overflowMemoryUsage`, which **has no limit at all**. So the node's total direct memory for file reads is `pooled (≤ file_cache_size) + overflow (unbounded)`. Lowering `file_cache_size` does not lower the node's off-heap usage under a given workload; it moves bytes from the pooled column to the overflow column, and costs recycling efficiency in doing so.
- **The real backstop is elsewhere.** What actually stops unbounded direct allocation is the JVM's `-XX:MaxDirectMemorySize`, which the pool's own OOM handler names when it fails. That is a JVM flag, not a Cassandra constraint, and it is not this case.
- **Mechanism.** Refusal to reserve another slab — not refusal to allocate. This is the cleanest example in the folder of a limit that bounds a *managed pool* rather than a *resource*, and the distinction is directly measurable because Cassandra exposes both columns as metrics (§9).

**Consequence for Target 2.** An operator lowering `file_cache_size` to cap
off-heap memory will not get what they expect. The honest statement of this
constraint's effect is: it bounds how much of the node's off-heap read memory
is *pooled and recycled*, and thereby the node's allocation churn — not its
off-heap footprint.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** Method and pitfalls:
[README.md §8](../../../README.md#8-designing-a-test-for-a-case). Where stage 4's
numbers go: [`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).

**The best-instrumented case in this folder.** `BufferPoolMetrics` exposes the
limit, the operand **and** the escape hatch as gauges, per pool. No proxies are
needed, which is unusual here and makes this the case whose §8 claim can be
settled most cleanly: the prediction is literally "`Size` plateaus at
`Capacity` while `OverflowSize` grows", and both numbers are readable.

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable, restart-only.** Every step of the limit path is `static final` (§4): no setter, no JMX. Each capacity value costs a node restart. |
| **Constraint knob** | `file_cache_size` in `cassandra.yaml` (MiB). **Pin `-Xmx` across the sweep** — when unset the value is auto-sized to `min(512MiB, maxMemory/4)` ([`DatabaseDescriptor.java:576-577`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L576-L577)), so an unpinned heap moves the default arm. Confirm the resolved value from the startup line "Global buffer pool limit is ..." ([`BufferPools.java:47-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L47-L53)). |
| **Capacity values to test** | `file_cache_size` ∈ {`64MiB`, `128MiB`, `256MiB`, **default**}. All are whole multiples of the 8 MiB macro chunk, so the quantisation in §8 does not blur the curve. Record the resolved default rather than assuming 512MiB — it is `min(512MiB, maxMemory/4)` and a small heap changes it. |
| **Usage-side observable** | `memoryAllocated` — pooled bytes reserved. |
| **Instrument** | **Direct, no proxy.** [`BufferPoolMetrics`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java#L54-L64) registers, scoped by pool name (use **`chunk-cache`**, not `networking`): `Capacity` → `memoryUsageThreshold` (the limit itself), `Size` → `sizeInBytes()` = **pooled + overflow**, `UsedSize` → `usedSizeInBytes()`, **`OverflowSize`** → `overflowMemoryInBytes()` (the escape hatch), plus `Hits` / `Misses` meters. **`Size` already includes overflow** ([`BufferPool.java:276`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L276)) — so the pooled figure is `Size − OverflowSize`, and plotting `Size` alone will **hide the very effect this case is about**. Cross-check with JVM Native Memory Tracking (`-XX:NativeMemoryTracking=summary`, then `jcmd <pid> VM.native_memory summary`). |
| **Scope of the limit** | **Per pool, node-wide.** One `chunk-cache` pool per JVM, `static final`, shared by every table and every read. `N = 1`, no multiplier — but also no isolation, so any read on any table moves the operand. |
| **Suggested level** | **Both.** Unit: `test/unit/org/apache/cassandra/utils/memory/BufferPoolTest.java` constructs pools directly and is the natural home for an assertion that `allocateMoreChunks()` returns `null` at the boundary and that the caller still gets a buffer via overflow — the latter is the escape hatch expressed as a test, and is the cheapest way to establish §5's claim. `test/unit/org/apache/cassandra/net/BufferPoolAllocatorTest.java` is also relevant. Cluster: needed for the dose-response and the NMT cross-check. |

### 9a. Workload — driving the usage operand

The operand grows when readers need off-heap buffers faster than the pool
recycles them, so the workload is **read-heavy over compressed SSTables**.

- Single node, dedicated, `-Xmx` pinned, NMT enabled at JVM start.
- One table with compression enabled (the default `LZ4Compressor`) — the chunk cache holds *decompressed* data, so an uncompressed table under-exercises the pool.
- Load a dataset several times larger than `file_cache_size` so reads cannot all be served from cache, then run a **random-read** workload with `cassandra-stress` at high concurrency. Random access maximises chunk-cache misses and therefore buffer demand.
- Keep `memtable_allocation_type: heap_buffers` so the memtable pools do not also move native memory (§9g).

**Deterministic single-shot form:** set `file_cache_size` to a small multiple
of 8 MiB (say 64MiB = 8 chunks), then issue enough concurrent random reads that
demand exceeds 8 chunks. The pool fills to exactly its ceiling within seconds
and every further request goes to overflow — the boundary is reached on the
first burst, with no throughput race.

### 9b. Scenario A — just reach capacity

Drive read concurrency so pooled bytes approach but do not reach the ceiling.

Expect at each value: `Size − OverflowSize` climbing toward `Capacity` and
plateauing just below it; `OverflowSize` **at or near zero**; `Hits` high
relative to `Misses`; no "Maximum memory usage reached" line in the log. The
zero overflow is what makes this the control.

### 9c. Scenario B — try to exceed capacity

Push read concurrency past what the pool can serve. **Nothing fails and
nothing blocks** (§6b):

| Expected | Evidence |
|---|---|
| Pooled bytes (`Size − OverflowSize`) **plateau at `floor(Capacity / 8MiB) × 8MiB`** | The core prediction, and the quantisation is testable: expect the plateau one macro chunk short of `Capacity` when `Capacity` is not a multiple of 8 MiB. |
| **`OverflowSize` rises** and keeps rising under sustained load | The escape hatch, directly measured. This is the headline number. |
| `Misses` rises relative to `Hits` | Secondary confirmation that the pool stopped serving. |
| The `NoSpamLogger` INFO line "Maximum memory usage reached (...) for chunk-cache buffer pool" appears | Direct evidence the check fired — but **rate-limited**, so treat its presence as confirmation and its absence as inconclusive. |
| **Total direct memory (NMT) keeps growing past `file_cache_size`** | The §8 claim, cross-checked outside Cassandra's own accounting. |
| No exception, no stall, no client-visible effect | Distinguishes this from `cdc_total_space` and the hints case. |

### 9d. Expected dose-response

If the traced path is the binding limit:

- **Pooled bytes plateau linearly in `file_cache_size`**, in 8 MiB steps, across 64 / 128 / 256 MiB. A plateau that is not a multiple of 8 MiB would mean §7's chunk size is wrong — worth checking, since the source comment claims 1 MiB and the arithmetic says 8 MiB.
- **`OverflowSize` at saturation rises as `file_cache_size` falls**, at fixed offered load. Ideally the sum `pooled + overflow` is roughly *constant* across the sweep — that is the sharpest statement of §8: the knob moves bytes between two columns rather than changing the total.
- **Total NMT direct memory should be roughly flat across the sweep.** This is the prediction that matters, and it is the opposite of what an operator expects from a config called "cache size".
- **`Misses` rises as the knob falls**, quantifying the recycling cost.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| Pooled bytes plateau at the quantised ceiling; `OverflowSize` grows; total direct memory roughly flat across the sweep | **The case is confirmed, including §8** — the limit bounds the pool, not the memory. Report the pooled/overflow split at each value. |
| Pooled bytes plateau **and** `OverflowSize` stays at zero, with clients blocking or erroring | Some caller uses `tryGet`/`tryGetAtLeast` (§5) rather than `get`, and does see the refusal. Identify which — that would mean the constraint is a real ceiling on *that* path, and §8 needs qualifying per caller. |
| Pooled bytes climb past `Capacity` | The CAS accounting is not holding, or another path allocates chunks without passing `allocateMoreChunks()`. A real finding; chase it. |
| Total direct memory **falls** as `file_cache_size` falls | §8 is wrong: the knob does bound the node's off-heap usage after all. That would be a better outcome for operators and a correction to this case. |
| Nothing moves at any value | The workload never exercised the pool. Confirm table compression is on and reads are missing the cache before concluding — `Hits`/`Misses` settles it. |

### 9f. What would refute this case

The case claims the comparison at `allocateMoreChunks():443` gates creation of
the pool's 8 MiB macro chunks, so **pooled** off-heap bytes for the
`chunk-cache` pool are bounded by `file_cache_size`. It is refuted if
`Size − OverflowSize` grows materially past `Capacity` under sustained load,
or does not move when `file_cache_size` is swept.

**`OverflowSize` growing does not refute the case** — §5, §6b and §8 all state
that the caller falls back to unpooled direct allocation, and measuring how
much is the most valuable thing stage 4 can do here. The claim that *is*
independently falsifiable, and worth stating separately, is §8's: that total
off-heap memory for file reads is roughly invariant under the knob. If NMT
shows total direct memory tracking `file_cache_size` proportionally, §8 is
wrong and this constraint is a genuine memory ceiling after all.

### 9g. Confounders and controls

- **Other direct-memory consumers dominate an NMT total**: the `networking` `BufferPool` (its own instance, its own config), Netty's pooled buffers, and the memtable pools if `memtable_allocation_type` is off-heap. Set `memtable_allocation_type: heap_buffers`, scope every Cassandra metric to **`chunk-cache`**, and use NMT's category breakdown with an idle-node baseline subtracted.
- **`-Xmx` changes the default `file_cache_size`.** Pin it; record the resolved limit from the startup log in every arm, including the default arm.
- **Table compression must be on.** The chunk cache holds decompressed data; an uncompressed table exercises the pool far less.
- **The dataset must exceed the cache.** If it fits, `Hits` stays high, the pool never saturates and every arm looks identical.
- **`Size` includes overflow.** Plotting it alone hides the effect. Always plot `Size − OverflowSize` and `OverflowSize` separately.
- **The INFO log is rate-limited** by `NoSpamLogger` — absence is not evidence the check did not fire.
- **Distinguish the two `null` returns.** An `OutOfMemoryError` from `allocateDirectAligned` also yields `null` (§6b) and would look identical in the metrics. Check for the ERROR line naming `-XX:MaxDirectMemorySize`, and set `-XX:MaxDirectMemorySize` comfortably above every tested value so native exhaustion is never the binding constraint.
- **Baseline** at the default with a light read load; **idle control** with the node up and no reads, for the pooled and overflow floors.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — found 2026-09-22 by the capacity-word pass reading the source directly, and recorded in `pending.md` as `BufferPool_memoryUsageThreshold`, the strongest of that pass's four candidates. Also independently surfaced by stage 1/2 as band-A1 row `BufferPool.java:443#1`. Written up 2026-09-28. |
| **Filed by / Date** | Claude (`claude-opus-5`) session, 2026-09-28 |
| **Line numbers checked** | 2026-09-28 against the local `cassandra-5.0.9` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). |
| **Escape hatch / Target-3 note** | **Yes, and it is the point of the case.** The disallow branch withholds the `Chunk`, but [`LocalPool.get():923`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L923) then allocates the buffer directly from the OS via `ByteBuffer.allocateDirect`, tracked as `overflowMemoryUsage` with **no ceiling of its own**. So `file_cache_size` bounds the pool, not the node's off-heap memory. Unlike the memtable `markBlocking()` hatch this is not a special caller state and unlike the compaction guard it is not a skipped path — it is the ordinary, always-taken fallback. Two milder observations: an `OutOfMemoryError` in the allocation is funnelled into the same `null`/overflow path, so native exhaustion is indistinguishable from configured refusal in the metrics; and the `tryGet`/`tryGetAtLeast` entry points do propagate the refusal, so the hatch may not apply to every caller. |
| **Stage-4 feedback** | none yet |
| **Notes** | **Stale comment in the source**: [`BufferPool.java:384`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L384) documents `MACRO_CHUNK_SIZE` as "1 MiB", but `64 * (128 << 10)` is **8 MiB**. §7 and §9d use 8 MiB. Worth an upstream report. |

---

## 11. Notes

- **The `networking_cache_size` sibling is not filed.** The same check, on the
  second `BufferPool` instance created at
  [`BufferPools.java:44-45`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L44-L45),
  whose threshold comes from `networking_cache_size`
  ([`Config.java:493-494`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L493-L494),
  default `min(128MiB, maxMemory/16)`). It is a separate case by §6.1, exactly
  as `memtable_offheap_space` is separate from `memtable_heap_space`, and is
  recorded in [`../pending.md`](../pending.md). The interesting difference to
  write up is lifetime, not code: the class comments say chunk-cache buffers
  "may be held for arbitrary period" while networking buffers "should be
  released immediately after use", so the two pools should saturate under
  completely different workloads.

- **This is the folder's clearest example of a pool limit versus a resource
  limit.** Three filed cases now have a disallow branch that does not withhold
  the resource: the memtable pair (overshoot via `markBlocking()`), the
  native-transport case (decodes anyway by default), and this one (allocates
  outside the pool). This one is the cleanest of the three, because Cassandra
  itself distinguishes the two columns and publishes both — which is why §9
  can settle it rather than merely predict it.

- **Accounting and allocation stay consistent here**, unlike the off-heap
  memtable case. The CAS at `:452` happens *before* the allocation at `:460`,
  and a failed allocation returns without having bumped the counter. So
  `memoryAllocated` is a truthful figure for pooled bytes — which is what makes
  `Size − OverflowSize` a valid measurement in §9.

- **Two config entries, one check, two cases.** The naming question
  `pending.md` left open on 2026-09-22 — "trace `memoryUsageThreshold` to its
  config source" — has two answers, not one, because the field is a
  constructor parameter. §6.1's configuration-entry rule resolves it by
  filing one case per config, which also matches how the two memtable pools
  were handled.
