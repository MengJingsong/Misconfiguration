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
entry point was not enumerated here; §9a's Conclusions table leaves it as the question a null
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
| **Rough sizing** | `MACRO_CHUNK_SIZE = 64 * NORMAL_CHUNK_SIZE` ([`:385`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L385)) with `NORMAL_CHUNK_SIZE = 128 << 10` ([`:128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L128)) — i.e. **8 MiB**, fixed. **The comment above `MACRO_CHUNK_SIZE` says "1 MiB" and is stale**; the arithmetic gives 8 MiB. This matters for the test design, because the ceiling is quantised in 8 MiB steps (§9a, Prediction). |
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

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test sets `file_cache_size`, drives concurrent reads so that the `chunk-cache`
pool wants more memory than the limit allows, and reads three things side by side:
the bytes the pool reserved, the bytes handed out around the pool, and the
node's real direct memory. **Run so far:** none. Converted to this layout 2026-10-06.

### 9a. Procedure and conclusions

**Testability:** config, **restart-only** — every step of the limit path is
`static final` (§4): no setter and no JMX. Each capacity value costs a restart.

**Claim under test:** `file_cache_size` bounds the **pooled** direct memory of the
`chunk-cache` buffer pool: `memoryAllocated` never exceeds the threshold, and the
pool stops one whole 8 MiB macro chunk short, at `⌊threshold / 8 MiB⌋ × 8 MiB`. When
the pool is at its ceiling nothing fails and nothing waits: the caller allocates its
buffer straight from the OS, counted as overflow with **no ceiling of its own**. So the
node's off-heap memory for these reads is pooled plus overflow, and §8 claims that
total does not move with the knob.

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** pooled bytes are capped at the quantised limit; past it the
  overflow takes the demand; the total is set by the demand, not by the knob.
- **Test:** vary `file_cache_size` (16, 64, 100, 128 MiB and the default), apply the
  same concurrent read load at each, and read the pool's `Capacity`, `Size`,
  `OverflowSize`, `Hits` and `Misses`, and the JVM's native memory.
- **Logic:** (1) at each value the load must exceed the pool, or the run is invalid.
  (2) Pooled bytes (`Size − OverflowSize`) stop at the quantised limit while
  `OverflowSize` rises: usage **stops at the limit** and the disallow branch fired.
  (3) The plateau moves with the knob in 8 MiB steps: usage **follows the constraint**.
  (4) The pooled-plus-overflow total and the native-memory rise stay (nearly) flat
  across the sweep: §8's claim that the limit bounds the pool, not the memory.
- **Refuted if:** pooled bytes pass the threshold or do not move with the knob; the
  native-memory rise follows the knob (§8 refuted); or a caller sees the refusal
  instead of overflowing (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) run upstream `BufferPoolTest` (pool of 8 MiB; `testMaxMemoryExceeded*`
   request double the maximum). (b) Run the harness test `BufferPoolCeilingTest` (9c):
   pools of 16, 20 and 64 MiB, driven with 128 KiB requests to the ceiling and one past
   it, asserting the quantised ceiling, a non-null buffer at the next request, a rising
   `overflowMemoryInBytes()`, `tryGet` returning `null`, and the overflow returning to
   zero when the buffers are put back.
2. **Cluster tier** — one node, restarted per value; the same read load at each.
3. **At each value:** idle control → **A**, a load below the pool → **B**, a load far
   above it. No scenario C: the overflow is the escape hatch and is read in B.
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *T* = `file_cache_size` in bytes; *M* = 8 MiB (the macro
chunk, §7); `P` = `Size − OverflowSize` (the pooled reservation); `O` = `OverflowSize`;
`D` = the demand: the direct bytes the readers want at once, the same at every value.

- **Capacity:** the `Capacity` gauge equals *T* at every value; the startup line reads
  `Global buffer pool limit is <T> for chunk-cache`.
- **A (`D` < pool):** `P` rises to about `D` rounded up to chunks, `O = 0`, `Misses`
  small against `Hits`, no `Maximum memory usage reached` line.
- **B (`D` > pool):** `P` plateaus at `⌊T / M⌋ × M`: 16, 64, 96 (for 100 MiB: one chunk
  short of the limit) and 128 MiB. `O` is positive and rises with `D − P`. `Misses`
  rises.
- **Total:** `P + O ≈ D` at every value above the saturation point, so it varies
  across the sweep by much less than `P` does. Stated as a relation (estimate): from
  16 to 128 MiB `P` changes by 112 MiB; the total and the native-memory rise over idle
  change by at most 25 % of that (28 MiB).
- **Default:** *T* = `min(512 MiB, maxMemory / 4)` = 512 MiB at `-Xmx4G`; if `D` is below
  512 MiB the default arm is at A's shape (`O = 0`), which is the control that the
  knob does nothing when the pool is not exhausted.

**Conclusions:**

| Result | Conclusion |
|---|---|
| `P` plateaus at `⌊T / M⌋ × M` at the saturated values and moves with *T* in 8 MiB steps, `O` rises, `Capacity` = *T*, and the total (and native memory over idle) is nearly flat across the sweep | **Confirmed**, including §8: the limit bounds the pool, not the memory. Report the pooled/overflow split at each value. |
| `P` and the ceiling as above, but native memory over idle falls as *T* falls (beyond the 25 % band) | **Confirmed for the pool; §8 refuted** — the knob does bound the node's direct memory for these reads (check that the overflow is not being released earlier). |
| `P` passes the threshold by more than one chunk | **Refuted** — the CAS accounting does not hold, or another path allocates chunks without passing `allocateMoreChunks()`. |
| `P` does not move with *T* across the saturated values | **Refuted** — not the binding limit. Re-read, do not re-run (check that the startup line shows the value). |
| `P` plateaus and `O` stays zero while readers block or error | **Not confirmed** — a caller uses `tryGet` / `tryGetAtLeast` (§5) and sees the refusal: identify it; §8 is then true per caller. |
| `O` is positive but `P` is below the quantised ceiling | **Not confirmed** — the overflow has another cause (an oversize request, `size > NORMAL_CHUNK_SIZE`, `BufferPool.java:910`, or an `OutOfMemoryError` fallback, §6b): read the ERROR log and the request sizes. |
| `P` never reaches the ceiling at any value (`O = 0` throughout) | **Invalid run** — the load never exhausted the pool; raise `D` (9c) and re-run. |
| The log shows `failed to allocate chunk` (an `OutOfMemoryError`) | **Invalid run** — native memory ran out first; raise `-XX:MaxDirectMemorySize` (9b) and re-run. |

**Why `Size` alone is not enough:** `Size` already includes the overflow
([`BufferPool.java:276`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L276)),
so it hides the effect; only `Size − OverflowSize` is the pooled reservation.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `file_cache_size` in `cassandra.yaml` (MiB); unset means `min(512MiB, maxMemory / 4)` ([`DatabaseDescriptor.java:576-577`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L576-L577)). Restart-only. Unit tier: the pool takes the threshold in its constructor, `new BufferPool(name, bytes, recyclePartially)` ([`:187`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L187)). |
| **Confirm it took effect** | `logs/system.log`: `Global buffer pool limit is <T> for chunk-cache and <N> for networking` ([`BufferPools.java:47-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L47-L53)); and the gauge `org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Capacity` (bytes). |
| **Capacity values** | `16MiB`, `64MiB`, `100MiB` (not a multiple of 8 MiB: the quantisation), `128MiB`, and unset. Record the resolved default. |
| **Scope** | **Per pool, node-wide.** One `chunk-cache` pool per JVM, shared by every table and every read. N = 1. |
| **Level** | Both. Unit: `BufferPoolTest` (upstream) and the harness `BufferPoolCeilingTest`; `BufferPoolAllocatorTest` (`net`) is the networking instance, not this one. Cluster: for the demand-driven curve and the native-memory read. |

**What drives the pool.** With the chunk cache **off** (the default:
`cassandra.file_cache_enabled` is false; `ChunkCache` is built only when it is true,
[`ChunkCache.java:51-54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L51-L54)),
the pool's users are the per-reader buffers of `BufferManagingRebufferer`
([`:45`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java#L45)),
one per open reader, returned when the reader closes, plus compressed hint reads. So
`D` is the number of concurrently open readers times their chunk size. The first run
**confirms** that the load moves `Size` at all (control below); if not, set
`disk_access_mode: standard` (the mmapped paths do not use the pool) and re-check.

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `-Xms4G -Xmx4G` | fixed | The default limit derives from the heap size. |
| `-XX:MaxDirectMemorySize` | `8G` | The JVM's own backstop (§8) must not bind: native exhaustion makes the pool return `null` for another reason (§6b). |
| `-XX:NativeMemoryTracking=summary` | every arm | Must be set at JVM start; every arm has it, the idle control included. |
| `networking_cache_size` | default | A separate pool and case; it also books native memory (read in the idle floor). |
| `cassandra.file_cache_enabled` | `false` (default) | The cache would hold buffers and change `D`; the case is about the pool. |
| `memtable_allocation_type` | `heap_buffers` (default) | Off-heap memtables also allocate native memory. Start from `conf/cassandra.yaml`, not `cassandra_latest.yaml`. |
| Table | one table, `compression` default (`LZ4Compressor`, `chunk_length_in_kb` 16), `RF = 1` | Compressed reads go through the rebufferer. |
| Dataset | built once and reused at every value | See 9c. |
| Traffic | reads only during A and B; no writes, no repair | Flushes and compactions open readers too and move `D`. |

**Controls:**

- **Idle run** — node up, no reads: the pooled and overflow floors and the native-memory floor.
- **Reader-demand check** — once, at the default, a short read load: `Size` must rise above its idle value; otherwise the load does not use the pool (9a, Invalid run).
- **Default arm** — the same load at the unset value: usually A's shape.

**Reset between runs:** stop the node (`bin/nodetool stopdaemon`), check nothing is left, move `logs/` aside, edit `file_cache_size`, start it again. **Keep the data directory** (the dataset is reused); do not run compactions.

### 9c. Workload

`D` must exceed the largest tested pool, so many readers must be open at once. A read
of one partition opens a reader per SSTable that may hold it, so the dataset is built
from **many overlapping SSTables** and read at high concurrency.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/file_cache_size-allocateMoreChunks-memoryUsageThreshold`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `BufferPoolCeilingTest.java` | Unit tier. Package `org.apache.cassandra.utils.memory`; modelled on `BufferPoolTest`; see 9e. |
| `pool-sampler.sh` | Cluster tier. Every 5 s prints, with a timestamp, `Capacity`, `Size`, `UsedSize`, `OverflowSize`, `Hits`, `Misses` (scope `chunk-cache`) and NMT `Other` (`jcmd <pid> VM.native_memory summary`). |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.utils.memory.BufferPoolTest
cp <harness>/BufferPoolCeilingTest.java test/unit/org/apache/cassandra/utils/memory/
ant testsome -Dtest.name=org.apache.cassandra.utils.memory.BufferPoolCeilingTest

# cluster tier — build the dataset once (default file_cache_size is fine), with compaction off
bin/cqlsh -e "CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};"
bin/nodetool disableautocompaction
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do   # same 200,000 keys each pass, new SSTable each time
  tools/bin/cassandra-stress write n=200000 no-warmup -pop seq=1..200000 -rate threads=32; bin/nodetool flush keyspace1; done
# per value: the read load
tools/bin/cassandra-stress read n=3000000 no-warmup -pop dist=UNIFORM\(1..200000\) -rate threads=512
```

**Starting values.** Estimates, not measurements:

| Setting | Value | Why |
|---|---|---|
| SSTables | 20, each holding all 200,000 keys (about 40 MB each: stress's default is five 34-byte columns) | A read of one key may open a reader on up to 20 SSTables (bloom filters pass for all); 512 threads × up to 20 readers × one 16 KiB buffer ≈ 160 MiB wanted at once at most, above the 128 MiB value; a lower real overlap would make `D` smaller. |
| Read threads | `threads=512` | Maximum overlap of open readers. |
| Reads | `n=3000000` | Several minutes of sustained load at one value. |
| Time in B | 120 s after the first sample with `O > 0` | Several samples. |

**If the load does not exhaust the pool** (`O` stays zero at 16 MiB under the reads): stop; raise `threads` to 1,024; then set `disk_access_mode: standard`; then lower the limit to `8MiB`. Record each step. If none works, the run is invalid (9a).

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — pooled reservation, `P` | `Size − OverflowSize` of `org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache` ([`BufferPoolMetrics.java:54-64`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java#L54-L64)); `bin/nodetool sjk mx -mg -b '<name>' -f Value` per gauge. `pool-sampler.sh` does it. | Every 5 s | **`Size` includes `OverflowSize`**: subtract it. Read the two gauges within one second of each other, or `P` is a difference of two moments. The pool counts **reserved** bytes, not bytes in use (`UsedSize`). Use scope `chunk-cache`, not `networking`. |
| **Disallow evidence** | The INFO line `Maximum memory usage reached (…) for chunk-cache buffer pool, cannot allocate chunk of 8MiB` in `logs/system.log` (grep); `Misses` rising against `Hits`; `OverflowSize` > 0. | Throughout | The line goes through a `NoSpamLogger` (rate-limited): its presence confirms, its absence does not refute. It is logged only when the threshold is above zero. |
| **Bypass volume** — the overflow | `OverflowSize` (bytes currently outstanding outside the pool; it falls when those buffers are put back, [`BufferPool.java:246`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L246)), peak per scenario. | Every 5 s | It is a gauge of bytes outstanding, not a cumulative count: take the peak. It also holds legitimately oversize requests (`size > 128 KiB` go straight to `allocate`, `:910`); the load's 16 KiB buffers do not. |
| **Real resource** — native memory | `jcmd <pid> VM.native_memory summary`, category `Other` (`allocateDirect` is booked there on this JDK; confirm on the idle run); cross-check `java.nio:type=BufferPool,name=direct` `MemoryUsed`. | Idle control; every 5 s in B | Rise **over the idle control**. The networking pool, Netty and other direct users also move `Other`: hold them fixed (9b). `allocateDirectAligned` reserves 8 MiB per macro chunk, so `Other` moves in 8 MiB steps with `P`. Each `jcmd` is a JVM start (1–2 s): time-stamp every reading. Never use RSS. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Record pass or fail and the asserted values.

1. Run upstream `BufferPoolTest`. Record pass or fail.
2. Run `BufferPoolCeilingTest`. For each pool size (16 MiB, 20 MiB, 64 MiB), construct
   `new BufferPool("stage4", <bytes>, true)` and:
   1. request 128 KiB direct buffers (`get(128 << 10, BufferType.OFF_HEAP)`) from one
      thread until `sizeInBytes()` stops rising by whole chunks: asserts
      `sizeInBytes() − overflowMemoryInBytes()` equals `⌊bytes / 8 MiB⌋ × 8 MiB`
      (16, 16 and 64 MiB) and `overflowMemoryInBytes()` is 0;
   2. requests five more buffers: each returns **non-null**; `overflowMemoryInBytes()`
      is up by 5 × 128 KiB; the pooled figure is unchanged (the refusal is absorbed);
   3. `tryGet(128 << 10)` returns `null` (the refusal is visible on the `try` entry
      point only);
   4. puts the five overflow buffers back: `overflowMemoryInBytes()` returns to 0;
   5. puts everything back: the pooled reservation stays (the pool recycles chunks).

   Record pass or fail and, per pool size, the printed figures.

**Before the cluster tier.** Build the dataset once, with the default limit, and check
it: `bin/nodetool tablestats keyspace1.standard1` shows 20 SSTables. Run the
**reader-demand check** (9b) and record `Size` against the idle floor.

**Cluster tier, for each capacity value:**

1. **Control run** — set `file_cache_size`, reset (9b), start with
   `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=8G"` and
   `MAX_HEAP_SIZE=4G`, grep the startup line, read `Capacity`, and with no reads take
   the idle floor of every observable (9d) after 60 s.
2. **Scenario A — below the pool** — start `pool-sampler.sh` and a light read load
   (`threads=16`, `n=100000`): record `P`, `O`, `Misses` and native memory when `P` has
   settled. Expect `O = 0`. (At 16 MiB, skip A and record why: the pool is exhausted by
   any load.)
3. **Scenario B — far above it** — start `threads=512`, note the time; sample for 120
   s after `O > 0` first appears; grep the log for the INFO line; stop the load; wait
   30 s and record the floor again (the overflow returns to 0, the reservation stays).
4. **Stop** — `bin/nodetool stopdaemon`, check nothing is left, and keep the sampler
   output and the log.

**Default arm (9b)** — once, B only.

Stop when each scenario's records are taken; a run where `O` stays zero at 16 MiB is invalid (9a).

**Record for stage 4:** the `cassandra.yaml` diff and JVM options in force, the exact commands, the dataset check, the sampler output, the startup and INFO log lines, every reading above, per capacity value.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — found 2026-09-22 by the capacity-word pass reading the source directly, and recorded in `pending.md` as `BufferPool_memoryUsageThreshold`, the strongest of that pass's four candidates. Also independently surfaced by stage 1/2 as band-A1 row `BufferPool.java:443#1`. Written up 2026-09-28. |
| **Filed by / Date** | Claude (`claude-opus-5`) session, 2026-09-28 |
| **Line numbers checked** | 2026-09-28 against the local `cassandra-5.0.9` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). |
| **Escape hatch / Target-3 note** | **Yes, and it is the point of the case.** The disallow branch withholds the `Chunk`, but [`LocalPool.get():923`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L923) then allocates the buffer directly from the OS via `ByteBuffer.allocateDirect`, tracked as `overflowMemoryUsage` with **no ceiling of its own**. So `file_cache_size` bounds the pool, not the node's off-heap memory. Unlike the memtable `markBlocking()` hatch this is not a special caller state and unlike the compaction guard it is not a skipped path — it is the ordinary, always-taken fallback. Two milder observations: an `OutOfMemoryError` in the allocation is funnelled into the same `null`/overflow path, so native exhaustion is indistinguishable from configured refusal in the metrics; and the `tryGet`/`tryGetAtLeast` entry points do propagate the refusal, so the hatch may not apply to every caller. |
| **Stage-4 feedback** | none yet. **§9 converted to the new layout 2026-10-06** (9a to 9e) from the old §9; not yet audited (stage-4 README, step 0) and not yet run. The new §9 lists its harness as work for step 1. |
| **Notes** | **Stale comment in the source**: [`BufferPool.java:384`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L384) documents `MACRO_CHUNK_SIZE` as "1 MiB", but `64 * (128 << 10)` is **8 MiB**. §7 and §9a use 8 MiB. Worth an upstream report. **Found while converting §9 (2026-10-06):** the chunk cache is off by default (`cassandra.file_cache_enabled`), so the `chunk-cache` pool's users are the per-reader buffers of `BufferManagingRebufferer`; the old §9 assumed the cache held the buffers. The case's claims are unchanged; §9b records the consequence for the workload. |

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
