# file_cache_size — Pair 02 · Full Code Path

> **Summary:** [file_cache_size-02-summary.md](file_cache_size-02-summary.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Pair:** file_cache_size-02 (`BufferPool` hard memory threshold — with an unpooled, unbounded fallback bypass)
**Entry Point Location:** [`Config.java:496-497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L496-L497)
**Restriction Enforcement:** [`BufferPool.GlobalPool.allocateMoreChunks():438-452`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L438-L452)

---

## Complete Continuous Code Trace

### Stage 1: Declaration and Load (shared prefix with Pair 01)

**File:** `src/java/org/apache/cassandra/config/Config.java`
**Lines:** 496-499

```java
@Replaces(oldName = "file_cache_size_in_mb", converter = Converters.MEBIBYTES_DATA_STORAGE_INT, deprecated = true)
public DataStorageSpec.IntMebibytesBound file_cache_size;

public boolean file_cache_enabled = FILE_CACHE_ENABLED.getBoolean();
```

**File:** `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
**Lines:** 576-577

```java
if (conf.file_cache_size == null)
    conf.file_cache_size = new DataStorageSpec.IntMebibytesBound(Math.min(512, (int) (Runtime.getRuntime().maxMemory() / (4 * 1048576))));
```

**Result:** Same as Pair 01 — `conf.file_cache_size` is non-null after startup (auto-sized to `min(512 MiB, maxHeap/4)` if unset).

---

### Stage 2: Getter / Read

**File:** `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
**Lines:** 3784-3793

```java
public static int getFileCacheSizeInMiB()
{
    if (conf.file_cache_size == null)
    {
        assert DatabaseDescriptor.isClientInitialized();
        return 0;
    }
    return conf.file_cache_size.toMebibytes();
}
```

**Result:** Returns the configured/auto-sized MiB value.

---

### Stage 3: Derivation and Pool Construction — the Un-Reduced Threshold

**File:** `src/java/org/apache/cassandra/utils/memory/BufferPools.java`
**Lines:** 38-39

```java
private static final long FILE_MEMORY_USAGE_THRESHOLD = DatabaseDescriptor.getFileCacheSizeInMiB() * 1024L * 1024L;
private static final BufferPool CHUNK_CACHE_POOL = new BufferPool("chunk-cache", FILE_MEMORY_USAGE_THRESHOLD, true);
```

**What Happens:**
- Unlike `ChunkCache.cacheSize` (Pair 01), this threshold is the **raw** `file_cache_size` in bytes — no 32 MiB `RESERVED_POOL_SPACE_IN_MiB` subtraction.
- `FILE_MEMORY_USAGE_THRESHOLD` and `CHUNK_CACHE_POOL` are both `static final`, computed once at class-load.
- `recyclePartially = true` is passed — this pool allows reuse of partially-freed chunks (relevant to fragmentation, not to the threshold itself).

**Store (constructor):**

**File:** `src/java/org/apache/cassandra/utils/memory/BufferPool.java`
**Lines:** 187-197

```java
public BufferPool(String name, long memoryUsageThreshold, boolean recyclePartially)
{
    this.name = name;
    this.memoryUsageThreshold = memoryUsageThreshold;
    this.readableMemoryUsageThreshold = prettyPrintMemory(memoryUsageThreshold);
    this.globalPool = new GlobalPool();
    this.metrics = new BufferPoolMetrics(name, this);
    this.recyclePartially = recyclePartially;
    this.localPoolCleaner = executorFactory().infiniteLoop("LocalPool-Cleaner-" + name, this::cleanupOneReference, UNSAFE);
}
```

**Result:** `memoryUsageThreshold` is stored as a `final` instance field on the `CHUNK_CACHE_POOL` singleton — immutable for the process lifetime.

---

### Stage 4: Submission — Buffer Request Enters the Pool

**File:** `src/java/org/apache/cassandra/cache/ChunkCache.java`
**Lines:** 163 (calling code, for context — see Pair 01 Stage 6)

```java
ByteBuffer buffer = bufferPool.get(key.file.chunkSize(), key.file.preferredBufferType());
```

**File:** `src/java/org/apache/cassandra/utils/memory/BufferPool.java`
**Lines:** 206-211

```java
public ByteBuffer get(int size, BufferType bufferType)
{
    if (bufferType == BufferType.ON_HEAP)
        return allocate(size, bufferType);
    else
        return localPool.get().get(size);
}
```

**Result:** Off-heap requests (the common case for chunk cache) route to the calling thread's `LocalPool.get(size)`.

---

### Stage 5: Local Pool → Global Pool Escalation

**File:** `src/java/org/apache/cassandra/utils/memory/BufferPool.java`
**Lines:** 894-960

```java
public ByteBuffer get(int size)
{
    return get(size, false);
}

private ByteBuffer get(int size, boolean sizeIsLowerBound)
{
    ByteBuffer ret = tryGet(size, sizeIsLowerBound);
    if (ret != null)
        return ret;
    // ... trace logging omitted ...
    return allocate(size, BufferType.OFF_HEAP);
}
```

```java
private ByteBuffer tryGet(int size, boolean sizeIsLowerBound)
{
    LocalPool pool = this;
    if (size <= tinyLimit) { /* ... route to tiny pool ... */ }
    else if (size > NORMAL_CHUNK_SIZE)
    {
        metrics.misses.mark();
        return null;
    }
    ByteBuffer ret = pool.tryGetInternal(size, sizeIsLowerBound);
    // ...
    return ret;
}
```

```java
@Inline
private ByteBuffer tryGetInternal(int size, boolean sizeIsLowerBound)
{
    ByteBuffer reuse = this.reuseObjects.poll();
    ByteBuffer buffer = chunks.get(size, sizeIsLowerBound, reuse);
    if (buffer != null)
        return buffer;

    // else ask the global pool
    Chunk chunk = addChunkFromParent();
    if (chunk != null)
    {
        ByteBuffer result = chunk.get(size, sizeIsLowerBound, reuse);
        if (result != null)
            return result;
    }

    if (reuse != null)
        this.reuseObjects.add(reuse);
    return null;
}
```

**Code Path Execution:**

**Step 1: Try locally-owned chunks first**
```
LocalPool.tryGetInternal()
  → checks its own MicroQueueOfChunks (up to 3 chunks) for free space
  → if found: return slice, done (no global-pool interaction)
```

**Step 2: Escalate to GlobalPool on local miss**
```
→ addChunkFromParent() calls GlobalPool.get() (Stage 6 below)
  → if GlobalPool returns a chunk: slice from it, return
  → if GlobalPool returns null: tryGetInternal() returns null
```

**Step 3: Total failure → unpooled fallback (Stage 7)**
```
→ LocalPool.get() sees tryGet() returned null
  → calls allocate(size, BufferType.OFF_HEAP)   // bypasses the pool entirely
```

**Result:** Three-tier escalation — local chunk → global pool (macro-chunk allocation, threshold-checked) → raw unpooled allocation (NOT threshold-checked).

---

### Stage 6: Enforcement Check — `GlobalPool.allocateMoreChunks()`

**File:** `src/java/org/apache/cassandra/utils/memory/BufferPool.java`
**Lines:** 417-452

```java
private Chunk getInternal()
{
    Chunk chunk = chunks.poll();
    if (chunk != null)
        return chunk;

    chunk = allocateMoreChunks();
    if (chunk != null)
        return chunk;

    // another thread may have just allocated last macro chunk, so make one final attempt before returning null
    chunk = chunks.poll();

    // try to use partially freed chunk if there is no more fully freed chunk.
    return chunk == null ? partiallyFreedChunks.poll() : chunk;
}

private Chunk allocateMoreChunks()
{
    while (true)
    {
        long cur = memoryAllocated.get();
        if (cur + MACRO_CHUNK_SIZE > memoryUsageThreshold)
        {
            if (memoryUsageThreshold > 0)
            {
                noSpamLogger.info("Maximum memory usage reached ({}) for {} buffer pool, cannot allocate chunk of {}",
                                  readableMemoryUsageThreshold, name, READABLE_MACRO_CHUNK_SIZE);
            }
            return null;
        }
        if (memoryAllocated.compareAndSet(cur, cur + MACRO_CHUNK_SIZE))
            break;
    }
    // allocate a large (1 MiB) macro-chunk via allocateDirectAligned(), or return null on OutOfMemoryError
    ...
}
```

**Critical Behavior:**
```java
if (cur + MACRO_CHUNK_SIZE > memoryUsageThreshold)
    return null;   // no exception, no block — just refuses
```
This is the **only** hard comparison against `file_cache_size` (via `memoryUsageThreshold`) anywhere in the allocation path. It gates only the acquisition of a new 1 MiB macro-chunk into the pool — it does not gate the eventual fallback allocation.

**Result:** Once `memoryAllocated` (the pool's own macro-chunk accounting) would exceed the threshold, `GlobalPool` refuses to grow further. Existing chunks already in circulation (fully-freed or partially-freed queues) can still be served without touching this check, but once those are exhausted too, `getInternal()` returns `null` all the way up.

---

### Stage 7: Action on Breach — Unpooled, Unbounded Fallback

**File:** `src/java/org/apache/cassandra/utils/memory/BufferPool.java`
**Lines:** 233-238, 261-264

```java
private ByteBuffer allocate(int size, BufferType bufferType)
{
    updateOverflowMemoryUsage(size);
    return bufferType == BufferType.ON_HEAP
           ? ByteBuffer.allocate(size)
           : ByteBuffer.allocateDirect(size);
}
```

```java
private void updateOverflowMemoryUsage(int size)
{
    overflowMemoryUsage.add(size);
}
```

**Critical Behavior:**
`allocate()` performs a **direct JVM allocation** (`ByteBuffer.allocateDirect(size)` for off-heap) with no comparison to `memoryUsageThreshold` at all — the only bookkeeping is an unbounded `LongAdder` (`overflowMemoryUsage`) that is purely observational.

**Timing Snapshot:**
```
Steady state (pool not saturated):
  memoryAllocated ≈ pooled bytes in use, bounded by memoryUsageThreshold (= file_cache_size, un-reduced)
  overflowMemoryUsage ≈ 0

Pool saturated (memoryAllocated ~= memoryUsageThreshold, no free/partial chunks available):
  every further off-heap request of a size the pool would normally serve
    → falls to allocate(size, OFF_HEAP)
    → overflowMemoryUsage keeps growing, unbounded
    → sizeInBytes() = memoryAllocated + overflowMemoryUsage  now exceeds file_cache_size,
      with no ceiling other than -XX:MaxDirectMemorySize / physical RAM
```

**Implication:** The constraint (`file_cache_size` → `memoryUsageThreshold`) behaves as a hard cap only for the pooled allocation path. Under sustained pool saturation it degrades into an advisory limit — actual off-heap usage for this subsystem is effectively unbounded.

---

## Path Continuity Notes

- **Threshold value differs from Pair 01:** this pool's `memoryUsageThreshold` is the raw `file_cache_size` (no 32 MiB reservation), while `ChunkCache`'s own Caffeine weight target (Pair 01) is `file_cache_size - 32 MiB`. In principle this gives the pool ~32 MiB of headroom over the logical cache's target, which is presumably *why* the reservation exists — but it does not change the fact that once genuinely exhausted, the pool's response is an unbounded fallback rather than backpressure.
- **`ON_HEAP` requests bypass pooling/threshold entirely:** `BufferPool.get()` (Stage 4) routes `BufferType.ON_HEAP` requests straight to `allocate()`, which is also untracked against `memoryUsageThreshold` — this is a separate, narrower path than the off-heap exhaustion case documented above, not independently traced here since `ChunkCache` chunks are off-heap in the normal (non-JVM-heap-buffer) configuration.
- **Unpooled buffers do not return through the pool on release:** `BufferPool.put()` (`BufferPool.java:240-247`) checks `Chunk.getParentChunk(buffer)`; for an unpooled buffer this is `null`, so `put()` calls `FileUtils.clean(buffer)` and `updateOverflowMemoryUsage(-size)` — the memory is freed correctly, but this confirms the fallback buffers never become part of the pooled/reusable chunk set, and every fallback allocation is a fresh direct-memory allocation, not amortized like pooled chunks.

## Key Code References

| Stage | File | Lines | What | Purpose |
|-------|------|-------|------|---------|
| 1-2 | [`Config.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L496-L499) / [`DatabaseDescriptor.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3784-L3793) | 496-499 / 3784-3793 | Declaration + getter | shared with Pair 01 |
| 3 | [`BufferPools.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L38-L39) | 38-39 | Derive + construct | `FILE_MEMORY_USAGE_THRESHOLD`, `CHUNK_CACHE_POOL` |
| 3 | [`BufferPool.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L187-L197) | 187-197 | Store | constructor sets `memoryUsageThreshold` |
| 4-5 | [`BufferPool.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L206-L211) / [894-984](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L894-L984) | 206-211, 894-984 | Submission / escalation | `get()` → `LocalPool.get()` → `tryGetInternal()` |
| 6 | [`BufferPool.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L417-L452) | 417-452 | **Check/enforcement** | `GlobalPool.getInternal()` / `allocateMoreChunks()` |
| 7 | [`BufferPool.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L233-L238) | 233-238 | **Action on breach (bypass)** | `allocate()` — unpooled, unbounded `ByteBuffer.allocateDirect()` |

---

## Memory/Resource Impact Summary

- Pooled macro-chunks (1 MiB each) are allocated on demand up to `memoryUsageThreshold` and never released back to the OS (`macroChunks` queue is permanent for process lifetime) — normal chunk-level recycling happens within that fixed footprint.
- Once the pooled footprint is saturated and no reclaimable (fully/partially freed) chunk is available, every further request degrades to an **unpooled direct allocation** — allocated fresh and freed individually via `FileUtils.clean()`, with no relationship to `memoryUsageThreshold`.
- This is a genuine overshoot vector: `file_cache_size` is meant to bound the chunk-cache subsystem's off-heap footprint, but `sizeInBytes()` (`memoryAllocated + overflowMemoryUsage`) can exceed it indefinitely under sustained pool pressure — the only actual backstop at that point is `-XX:MaxDirectMemorySize` (a JVM-wide setting, not specific to this subsystem) or the OOM killer.
- Directly compounds with Pair 01: since eviction in `ChunkCache` only returns buffers to *this* pool, and does so post-hoc, a workload that keeps the pool saturated will keep routing new misses through the unpooled path regardless of how aggressively Pair 01's eviction is running.

---

## Notes

- Cassandra module: `org.apache.cassandra.utils.memory` (BufferPool, GlobalPool, LocalPool, Chunk) — the physical off-heap allocator underlying the `ChunkCache` documented in Pair 01.
- `BufferPoolMetrics` (`metrics.misses` / `metrics.hits`) would surface the miss pattern that precedes fallback allocation, but does not itself distinguish "served from global pool" misses from "fell through to unpooled allocation" — worth flagging as an observability gap alongside the rate-limited log message.
