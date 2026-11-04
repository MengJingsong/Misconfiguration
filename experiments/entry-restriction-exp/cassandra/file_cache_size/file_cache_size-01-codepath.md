# file_cache_size — Pair 01 · Full Code Path

> **Summary:** [file_cache_size-01-summary.md](file_cache_size-01-summary.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Pair:** file_cache_size-01 (Caffeine `maximumWeight` — soft, post-hoc eviction on the logical `ChunkCache`)
**Entry Point Location:** [`Config.java:496-497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L496-L497)
**Restriction Enforcement:** [`ChunkCache.<init>():151-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L151-L157)

---

## Complete Continuous Code Trace

### Stage 1: Declaration

**File:** `src/java/org/apache/cassandra/config/Config.java`
**Lines:** 496-499

```java
@Replaces(oldName = "file_cache_size_in_mb", converter = Converters.MEBIBYTES_DATA_STORAGE_INT, deprecated = true)
public DataStorageSpec.IntMebibytesBound file_cache_size;

public boolean file_cache_enabled = FILE_CACHE_ENABLED.getBoolean();
```

**What Happens:**
- `file_cache_size` starts `null` — it is unset until `DatabaseDescriptor` applies a default.
- `file_cache_enabled` defaults from the `cassandra.file_cache_enabled` system property (`FILE_CACHE_ENABLED`, default `true`).

**Result:** Two independent config surfaces (`file_cache_size`, `file_cache_enabled`) exist before any load/validation pass.

---

### Stage 2: Load / Default Application

**File:** `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
**Lines:** 576-577

```java
if (conf.file_cache_size == null)
    conf.file_cache_size = new DataStorageSpec.IntMebibytesBound(Math.min(512, (int) (Runtime.getRuntime().maxMemory() / (4 * 1048576))));
```

**Code Path Execution:**

**Step 1: Auto-sizing on unset config**
```
if cassandra.yaml did not set file_cache_size:
  file_cache_size = min(512 MiB, maxHeap / 4)
  → e.g. an 8 GiB heap yields min(512, 2048) = 512 MiB
  → a 1 GiB heap yields min(512, 256) = 256 MiB
```

**Result:** `conf.file_cache_size` is always non-null after `DatabaseDescriptor` initialization, in server mode.

---

### Stage 3: Getter / Read

**File:** `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
**Lines:** 3784-3793

```java
public static int getFileCacheSizeInMiB()
{
    if (conf.file_cache_size == null)
    {
        // In client mode the value is not set.
        assert DatabaseDescriptor.isClientInitialized();
        return 0;
    }
    return conf.file_cache_size.toMebibytes();
}
```

**Result:** Returns the configured (or auto-sized) MiB value; `0` only in client-tool mode where server config was never loaded.

---

### Stage 4: Derivation — Effective Cache Weight

**File:** `src/java/org/apache/cassandra/cache/ChunkCache.java`
**Lines:** 49-53

```java
public static final int RESERVED_POOL_SPACE_IN_MiB = 32;
public static final long cacheSize = 1024L * 1024L * Math.max(0, DatabaseDescriptor.getFileCacheSizeInMiB() - RESERVED_POOL_SPACE_IN_MiB);
public static final boolean roundUp = DatabaseDescriptor.getFileCacheRoundUp();

private static boolean enabled = DatabaseDescriptor.getFileCacheEnabled() && cacheSize > 0;
public static final ChunkCache instance = enabled ? new ChunkCache(BufferPools.forChunkCache()) : null;
```

**What Happens:**
- `cacheSize` (bytes) is computed once, as a static field, at class-load time: `(file_cache_size - 32 MiB)`, floored at 0.
- The cache is only instantiated (`enabled == true`) if `file_cache_enabled` is true **and** the derived `cacheSize` is positive — a `file_cache_size` of 32 MiB or less silently disables the chunk cache entirely.
- `instance` is a process-wide singleton; there is exactly one `ChunkCache` per node.

**Result:** The effective enforced weight limit is 32 MiB less than the configured/auto-sized `file_cache_size` — this offset reserves headroom in the underlying `BufferPool` for transient allocations outside the cache's own accounting.

---

### Stage 5: Enforcement Configuration — Caffeine `maximumWeight`

**File:** `src/java/org/apache/cassandra/cache/ChunkCache.java`
**Lines:** 147-158

```java
private ChunkCache(BufferPool pool)
{
    bufferPool = pool;
    metrics = new ChunkCacheMetrics(this);
    cache = Caffeine.newBuilder()
                    .maximumWeight(cacheSize)
                    .executor(ImmediateExecutor.INSTANCE)
                    .weigher((key, buffer) -> ((Buffer) buffer).buffer.capacity())
                    .removalListener(this)
                    .recordStats(() -> metrics)
                    .build(this);
}
```

**Critical Behavior:**
```java
.weigher((key, buffer) -> ((Buffer) buffer).buffer.capacity())
```
Weight per entry = the buffer's raw byte capacity (the chunk size, typically the SSTable's compression chunk length). `maximumWeight(cacheSize)` tells Caffeine to evict when the *sum* of entry weights exceeds `cacheSize`.

**Result:** The cache is bounded not by entry count but by total buffer bytes held — a direct-ish proxy for the memory the cache holds, though it does not include `BufferPool` chunk/slab overhead.

---

### Stage 6: Load Path — Unconditional Allocation on Miss

**File:** `src/java/org/apache/cassandra/cache/ChunkCache.java`
**Lines:** 160-175, 233-253

```java
@Override
public Buffer load(Key key)
{
    ByteBuffer buffer = bufferPool.get(key.file.chunkSize(), key.file.preferredBufferType());
    assert buffer != null;
    try
    {
        key.file.readChunk(key.position, buffer);
        return new Buffer(buffer, key.position);
    }
    catch (Throwable t)
    {
        bufferPool.put(buffer);
        throw t;
    }
}
```

```java
public Buffer rebuffer(long position)
{
    long pageAlignedPos = position & alignmentMask;
    Buffer buf;
    do
        buf = cache.get(new Key(source, pageAlignedPos)).reference();
    while (buf == null);
    return buf;
}
```

**Code Path Execution:**

**Step 1: Cache miss triggers `load()`**
```
CachingRebufferer.rebuffer(position)
  → cache.get(key)   // Caffeine LoadingCache
  → on miss: calls load(key) synchronously (single-flight per key)
  → load() unconditionally requests a buffer from bufferPool.get(...) and reads the chunk from disk
  → no check against cacheSize happens before this allocation
```

**Result:** Every distinct cache miss allocates a new buffer from the `BufferPool` **before** any weight check — the constraint has no admission gate.

---

### Stage 7: Post-Hoc Eviction and Release

**File:** `src/java/org/apache/cassandra/cache/ChunkCache.java`
**Lines:** 177-181

```java
@Override
public void onRemoval(Key key, Buffer buffer, RemovalCause cause)
{
    buffer.release();
}
```

**Timing Snapshot:**
```
t0: cache.get(key) misses → load() allocates buffer, reads chunk, inserts into cache
    → weighted size now exceeds maximumWeight (possibly)
t1 (same call, ImmediateExecutor runs eviction inline after the write):
    → Caffeine evicts approx-LRU entries until weighted size <= maximumWeight
    → onRemoval() fires per evicted entry → Buffer.release() → bufferPool.put(buffer)
```

**Implication:** Because `ImmediateExecutor` runs eviction synchronously on the same thread right after the cache write, steady-state overshoot is bounded to roughly one insertion's worth per thread — but under many concurrent threads missing simultaneously, each can insert before any of their evictions run, so aggregate overshoot scales with concurrent miss count.

---

## Path Continuity Notes

- **Reserved space offset not enforced elsewhere:** the 32 MiB `RESERVED_POOL_SPACE_IN_MiB` subtraction only affects this cache's own Caffeine weight target — it does not change the underlying `BufferPool`'s threshold (see [[file_cache_size-02]]), which uses the full, un-reduced `file_cache_size`.
- **Static singleton:** `cacheSize`, `enabled`, and `instance` are all `static final`/`static`, computed once at class-load (JVM startup). `file_cache_size` cannot be changed at runtime — `ChunkCache.setCapacity()` explicitly throws `UnsupportedOperationException` (`ChunkCache.java:311-314`).
- **Concurrent-miss overshoot:** not independently verified under load in this pass; flagged as a bypass hypothesis (see summary) rather than measured.

## Key Code References

| Stage | File | Lines | What | Purpose |
|-------|------|-------|------|---------|
| 1 | [`Config.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L496-L499) | 496-499 | Declaration | `file_cache_size`, `file_cache_enabled` fields |
| 2 | [`DatabaseDescriptor.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L576-L577) | 576-577 | Auto-sizing default | `min(512 MiB, maxHeap/4)` |
| 3 | [`DatabaseDescriptor.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3784-L3793) | 3784-3793 | Getter | `getFileCacheSizeInMiB()` |
| 4 | [`ChunkCache.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L49-L54) | 49-54 | Derive + gate | `cacheSize`, `enabled`, singleton `instance` |
| 5 | [`ChunkCache.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L151-L157) | 151-157 | Enforcement config | Caffeine `maximumWeight` + `weigher` |
| 6 | [`ChunkCache.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L160-L175) | 160-175 | Unconditional allocation | `load(Key)` on cache miss |
| 7 | [`ChunkCache.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L177-L181) | 177-181 | Action on breach | `onRemoval()` → `Buffer.release()` |

---

## Memory/Resource Impact Summary

- Resource allocated on every cache miss, *before* any weight check (Stage 6); released only when Caffeine evicts an entry (Stage 7) or the cache is explicitly invalidated.
- Release is synchronous with respect to eviction (`ImmediateExecutor`), but eviction itself is triggered post-write, so the cache can transiently hold more than `cacheSize` bytes, especially under concurrent misses.
- Downstream: released buffers return to the `chunk-cache` named `BufferPool` (see [[file_cache_size-02]]), which has its own, separately-thresholded hard cap — that pool, not this cache's weight limit, is the actual backstop against unbounded off-heap growth.

---

## Notes

- Cassandra module: `org.apache.cassandra.cache` (chunk/file cache), layered on `org.apache.cassandra.utils.memory` (`BufferPool`).
- `file_cache_round_up` affects only chunk-size rounding for spinning disks, not this pair's enforcement.
