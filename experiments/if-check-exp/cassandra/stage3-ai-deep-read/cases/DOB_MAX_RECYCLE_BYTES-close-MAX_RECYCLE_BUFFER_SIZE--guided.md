# DOB_MAX_RECYCLE_BYTES — the thread-local scratch buffer kept between uses

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | DOB_MAX_RECYCLE_BYTES-CLOSE-MAX_RECYCLE_BUFFER_SIZE |
| **Constraint** | `DOB_MAX_RECYCLE_BYTES` — a **JVM system property**, `cassandra.dob_max_recycle_bytes`, default 1,048,576 bytes ([`CassandraRelevantProperties.java:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L204)), copied once into a `static final` at class initialization ([`DataOutputBuffer.java:53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L53)), so **restart-only**; no `cassandra.yaml` key, no JMX or `nodetool` setter. A second property, `cassandra.dob.allocate_type` ([`CassandraRelevantProperties.java:183`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L183)), decides whether the buffer is direct (the default, [`DataOutputBuffer.java:55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L55)) or on the heap; it changes the resource, not the limit (§4). |
| **Enforcement pattern** | **(a)** — the comparison is the `if` of the scratch buffer's `close()`. **Neither branch withholds creation:** the buffer was already grown, unconditionally, while it was in use; what the branches differ in is whether that buffer **stays resident** on the thread until its next use (allow) or is freed at once and replaced by a 128-byte one (disallow). Rule 3 is passed on README §3.6's failing condition ("zero observable effect"), not on withheld creation; see §5 and §11. |
| **Capacity check** | [`DataOutputBuffer$1$1.close():73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L73) — `buffer != null && buffer.capacity() <= MAX_RECYCLE_BUFFER_SIZE`, in the anonymous `DataOutputBuffer` that the anonymous `FastThreadLocal` `scratchBuffer` creates per thread ([`:63-92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L63-L92)). Being an anonymous class inside an anonymous class, its binary name is `DataOutputBuffer$1$1` (javac's naming; confirm with `ls build/classes/main/org/apache/cassandra/io/util/DataOutputBuffer\$1\$1.class` before writing a Byteman rule). **The only check site:** `MAX_RECYCLE_BUFFER_SIZE` has no other reader in the tree (§10). |
| **Decision point** | The same `if`, [`DataOutputBuffer.java:73-80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L73-L80): allow `buffer.clear()` ([`:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L75)), disallow `setBuffer(allocate(DEFAULT_INITIAL_BUFFER_SIZE))` ([`:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L79)). |
| **Allocation site** | The retained object is the thread's buffer, created by [`allocate():84-89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L84-L89) — `ByteBuffer.allocateDirect(size)` at [`:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L87) (`ByteBuffer.allocate(size)` at [`:88`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L88) in heap mode) — first at 128 bytes when the thread's instance is built ([`:68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L68) → [`BufferedDataOutputStreamPlus.java:72`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L72)), then at each growth in [`expandToFit():178`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L178). The disallow branch's own 128-byte replacement is allocated at the same [`:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L87), and the buffer it drops is freed at [`setBuffer():186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L186). |
| **Related cases** | [`max_mutation_size-validateSize-MAX_MUTATION_SIZE.md`](max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) — its §6a step 5 and §7 "Rough sizing" describe this recycle at `CommitLog.add()`, the busiest user; its limit bounds the commit-log item and so the buffer's in-use size at that site (§7 here). [`CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT.md`](CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md) — its §6a step 5, §7 and §8 describe the same recycle at the two mutation users; its limit decides whether the serialize side touches the scratch buffer at all and caps what the receive side mirrors into it, so the two properties together set what a write leaves behind (§11); its stage-4 unit tier recorded the scratch capacity after a copy. [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md`](MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md) — its stage-4 run met these buffers in the same JDK direct pool (+1 buffer, +128 bytes per new thread) and traced their allocations by thread. [`file_cache_size-allocateMoreChunks-memoryUsageThreshold.md`](file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) — another consumer of the same direct pool; its stage-4 run found NMT `Other` inflated by Netty's arenas, which is why §9 here reads the pool bean and a ledger, not NMT. |

```java
// DataOutputBuffer.java:50-92 — the limit, the allocation type and the per-thread scratch buffer.
/*
 * Only recycle OutputBuffers up to 1Mb. Larger buffers will be trimmed back to this size.   // :50-52 (the comment is wrong: §10)
 */
private static final int MAX_RECYCLE_BUFFER_SIZE = DOB_MAX_RECYCLE_BYTES.getInt();          // :53, read once
private enum AllocationType { DIRECT, ONHEAP }
private static final AllocationType ALLOCATION_TYPE = DATA_OUTPUT_BUFFER_ALLOCATE_TYPE.getEnum(AllocationType.DIRECT); // :55
private static final int DEFAULT_INITIAL_BUFFER_SIZE = 128;                                 // :57

public static final FastThreadLocal<DataOutputBuffer> scratchBuffer = new FastThreadLocal<DataOutputBuffer>()  // :63, DataOutputBuffer$1
{
    @Override
    protected DataOutputBuffer initialValue()
    {
        return new DataOutputBuffer()                                                        // :68, DataOutputBuffer$1$1, 128 bytes
        {
            @Override
            public void close()
            {
                if (buffer != null && buffer.capacity() <= MAX_RECYCLE_BUFFER_SIZE)       // <-- capacity check, :73
                {
                    buffer.clear();                                                        // ALLOW: keep it, :75
                }
                else
                {
                    setBuffer(allocate(DEFAULT_INITIAL_BUFFER_SIZE));                     // DISALLOW: free it, 128 B instead, :79
                }
            }

            @Override
            protected ByteBuffer allocate(int size)
            {
                return ALLOCATION_TYPE == AllocationType.DIRECT ?
                       ByteBuffer.allocateDirect(size) :                                    // :87
                       ByteBuffer.allocate(size);                                           // :88
            }
        };
    }
};
```

## 2. Context

Cassandra serializes many things into an in-memory buffer before copying them
somewhere else: every durable write is serialized before it is appended to the
commit log, rows are serialized before they are written to an SSTable, and
mutations are serialized to cache or forward them. Instead of allocating a fresh
buffer each time, each thread keeps one reusable "scratch" buffer, which grows
to fit the largest thing written into it. This check runs when a user hands the
buffer back: if it has grown to no more than a configured size (1 MiB by
default) the thread keeps it for next time, otherwise it is freed and replaced by
a tiny one. The check exists so that one large write does not leave a large
block of off-heap memory parked on a thread for as long as the thread lives.
It does not limit how large the buffer grows while in use; it limits only what
each thread retains between uses, so the node-wide amount it bounds is that size
multiplied by the number of threads that have used a scratch buffer.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `io_buffers` — reusable serialization buffers (`io/util/DataOutputBuffer` and its thread-local scratch instance), proposed as a new module (§10); the users are the commit log, mutation serialization, SSTable row writing and hints |
| **One-line role** | Gives each thread a growable in-memory output buffer to serialize into, reused across calls so that serialization does not allocate per item. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes, a per-thread retention cap.** It compares the byte capacity of one thread's buffer with a byte limit, at the moment the buffer goes idle. It does not see, and does not bound, the buffer's size while in use. |
| **Usage-side operand** | `buffer.capacity()` — the capacity, in bytes, of the calling thread's scratch buffer after the user has finished with it. |
| **Limit-side operand** | `MAX_RECYCLE_BUFFER_SIZE` ([`DataOutputBuffer.java:53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L53)), an `int` in bytes. |
| **Limit type** | JVM system property, read once into a `static final` (restart-only). |

**Limit initialization path:**

1. [`CassandraRelevantProperties.java:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L204) — declared: `DOB_MAX_RECYCLE_BYTES("cassandra.dob_max_recycle_bytes", convertToString(1024 * 1024))`.
2. [`CassandraRelevantProperties.getInt():794-800`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L794-L800) with [`INTEGER_CONVERTER:973-984`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L973-L984) — configured: `Integer.decode()` of the property, else the default. **No range check and no unit suffix:** a negative value, 0, or anything below 128 is accepted (every `close()` then replaces even a 128-byte buffer, §6b), a value of `MAX_ARRAY_SIZE` or more disables the trim (§8), and text such as `1MiB` throws `ConfigurationException` when `DataOutputBuffer` is first initialized.
3. [`DataOutputBuffer.java:53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L53) — stored: `private static final int MAX_RECYCLE_BUFFER_SIZE`, at class initialization. Setting the property after the class is loaded has no effect.
4. [`DataOutputBuffer.java:73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L73) — read at the comparison, on every `close()` of every thread's scratch buffer.

**The allocation type, which changes the resource:** `cassandra.dob.allocate_type` has no default value
([`CassandraRelevantProperties.java:182-183`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L182-L183));
[`getEnum(DIRECT)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L919-L922)
returns `DIRECT` when it is unset and otherwise `Enum.valueOf` of the upper-cased text
([`:932-938`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L932-L938)),
so `direct` and `onheap` are accepted in any case and any other value (`heap`, say) fails class
initialization; stored at [`DataOutputBuffer.java:55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L55).
It applies only to the scratch instance: a plain `new DataOutputBuffer()` uses the base class's heap
`allocate()` ([`BufferedDataOutputStreamPlus.java:75-78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L75-L78)).

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`DataOutputBuffer$1$1.close():73-80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L73-L80) — same as the capacity check |
| **Verdict** | n/a — the check is the decision (pattern (a)) |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow (keep)** | `buffer != null && buffer.capacity() <= MAX_RECYCLE_BUFFER_SIZE` | `buffer.clear()`: position 0, limit = capacity. Nothing is allocated or freed; the same buffer, at its grown capacity, stays referenced by the thread's instance, which the `FastThreadLocal` holds for the thread's life. The thread's next item reuses it and allocates nothing until it needs more than that capacity. |
| **Disallow (free)** | `buffer == null`, or `buffer.capacity() > MAX_RECYCLE_BUFFER_SIZE` | `allocate(128)` builds a new 128-byte buffer, then `setBuffer()` frees the old one at once (`FileUtils.clean()`, a direct buffer's cleaner; nothing for a heap buffer, which waits for GC) and installs the new one. No exception, log line or metric. The thread's next large item grows the buffer again. |

```java
// allow — DataOutputBuffer.java:75
buffer.clear();
```

```java
// disallow — DataOutputBuffer.java:79, then setBuffer():184-188
setBuffer(allocate(DEFAULT_INITIAL_BUFFER_SIZE));   // allocate(128) first, at :87
...
protected void setBuffer(ByteBuffer newBuffer)
{
    FileUtils.clean(buffer); // free if direct        // :186
    buffer = newBuffer;
}
```

**Rule 3, the reading this case rests on (flagged).** The disallow branch is the one that
**allocates** (128 bytes) and the allow branch allocates nothing; the large buffer was created by
the growth that happened while the user wrote into it, before the check and whatever its verdict.
So the check withholds no creation in the sense of README §3.6's opening sentence. It passes on that
section's failing condition: a check fails only if it has "zero observable effect … no difference in
state, timing, or accounting", and here the bytes resident on the thread after the check differ by
the buffer's capacity minus 128, at once and for as long as the thread lives (§6b, §8). This is the
reading the band-C pass recorded when it qualified the line, and the same weaker form of Rule 3 the
filed send-queue case states for itself ("retention rather than creation",
[`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md`](internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md)).
If Jingsong reads Rule 3 strictly (creation withheld), this case fails it and belongs in `predicted-negative.md`.

**The `buffer != null` term** is a null guard, not capacity: `buffer` is null only after
`buffer(false)` hands the buffer away ([`:232-239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L232-L239)),
which no scratch user calls (its only callers are plain buffers in `PagingState`), so on the
scratch instance the verdict is the capacity comparison alone.

### Who reaches the check — every production user of `scratchBuffer`

A grep of the whole tree for `scratchBuffer` finds six production sites and four test sites. Every
production site uses try-with-resources, so `close()` runs at the end of each use, and every one copies
the content out before closing:

| # | Site | When | Thread(s) | Item size (what the buffer grows to) |
|---|---|---|---|---|
| 1 | [`CommitLog.add():306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L306) | **every durable write**, after `validateSize()` at [`:304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304); copied into the segment at [`:323`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L323) | the applying thread: a `MutationStage` (or counter/view stage) worker, or the client's request thread when the local apply runs inline (below); also any thread that applies a system-table write directly | the serialized mutation, *S* ≤ `max_mutation_size` − 12 (§7) |
| 2 | [`Mutation.serialization():453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L453) | the first sizing or serialization of a mutation whose size is below `CACHEABLE_MUTATION_SIZE_LIMIT` ([`:451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451)); reached from `validateSize()` through `serializedSize()` ([`:530-533`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L530-L533)), e.g. on the request thread at [`SingleTableUpdatesCollector.java:112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java#L112), and from [`StorageProxy.java:1501`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1501) | coordinator request threads; hint writers; outbound serialization of uncached mutations | the serialized mutation, below the cacheable limit (default 1,000,000) |
| 3 | [`Mutation.deserialize():491`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L491) | every mutation deserialization, as the tee target of [`:493`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L493) | inbound internode (small messages on the messaging event loops, large ones on the verb's stage, [`InboundMessageHandler.java:52-54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L52-L54)); commit-log replay; hint dispatch; batchlog replay (the list is the `CACHEABLE_MUTATION_SIZE_LIMIT` case's §5) | what the tee mirrors: less than the cacheable limit, or the whole mutation if that limit is 0 or less ([`TeeDataInputPlus.java:56-62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L56-L62)) |
| 4 | [`UnfilteredSerializer.serialize():195`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L195) | every row written to an SSTable (`header.isForSSTable()`, [`:193`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L193)); copied out at [`:203`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L203) | memtable flush writers, compaction executors, and any other SSTable writer (streaming receive, imports, index and view builds) | one row body — **not** bounded by `max_mutation_size`, since a row can accumulate cells from many writes |
| 5 | [`HintsWriter.create():77`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java#L77) | each new hints file's descriptor | `HintsWriteExecutor` (one thread) | a few hundred bytes |
| 6 | [`SystemKeyspace.truncationAsMapEntry():774`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L774) | a truncation record | the truncating thread | about 20 bytes |

Test-only users ([`MessageTest.java:234`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/net/MessageTest.java#L234), [`GossipShutdownTest.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/gms/GossipShutdownTest.java#L60), [`FuzzTestBase.java:1375`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/repair/FuzzTestBase.java#L1375), [`AbstractTypeTest.java:636`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/marshal/AbstractTypeTest.java#L636)) are
not on any production path. **No site nests:** `CommitLog.add()` calls `validateSize()` first, which caches or
sizes the mutation before [`:306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L306) takes the buffer, so the serialization at [`:308`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L308) does not re-enter site 2 on
the same instance (it writes the cached bytes or walks the partition updates).

## 6. Code path

### 6a. Allow path → object creation

The allow branch creates nothing. The object whose residency it decides is created earlier, in the
same use, by the growth below; the allow branch then keeps it.

1. [`DataOutputBuffer.java:63-68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L63-L68) — the first `scratchBuffer.get()` on a thread calls `initialValue()`, which builds the thread's instance; its constructor ([`:94-97`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L94-L97) → [`BufferedDataOutputStreamPlus.java:70-73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L70-L73)) calls the overridden `allocate(128)` → `allocateDirect(128)` at [`:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L87). **One instance per thread:** every later `get()` on that thread returns the same instance; another thread gets its own.
2. [`BufferedDataOutputStreamPlus.write(byte[],int,int):87-117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L87-L117), [`write(ByteBuffer):124-138`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L124-L138), [`write(int):142-147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L142-L147) — a write that does not fit fills what remains, then calls `doFlush(count)` with the bytes still to write ([`:112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L112), [`:135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L135), [`:146`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L146)), which `DataOutputBuffer` turns into [`expandToFit(count)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L136-L139).
3. [`calculateNewSize():158-172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L158-L172) — the grow policy: `newSize = max(2 × capacity, capacity + count)` while `capacity ≤ 64 MiB` (`cassandra.DOB_DOUBLING_THRESHOLD_MB`, default 64, [`:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L48)), else `max(1.5 × capacity, capacity + count)` ([`:166-169`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L166-L169)); saturated at `MAX_ARRAY_SIZE` = `Integer.MAX_VALUE − 8` ([`:118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L118), [`:121-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L121-L125)), and `validateReallocation()` throws `BufferOverflowException` when that is no larger than the current capacity ([`:149-155`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L149-L155); recorded as a per-item type bound in `predicted-negative.md`, band A2).
4. [`expandToFit():174-182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L174-L182) — **object creation**: `allocate(newSize)` at [`:178`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L178) → `allocateDirect` at [`:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L87); the content is copied; `setBuffer()` at [`:181`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L181) frees the old buffer ([`:186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L186)). The old and new buffers coexist during the copy.
5. The user copies the content out (§5's table) and leaves its `try`; `close()` runs; at [`:73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L73) the capacity is at most the limit; [`:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L75) clears it. **The grown buffer stays resident** on the thread until a later use grows it again (step 4 frees it then) or the thread dies (§7, "Lifetime").

### 6b. Disallow path effect

1. [`DataOutputBuffer.java:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L79) — `allocate(128)`: a new 128-byte direct buffer ([`:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L87)).
2. [`setBuffer():184-188`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L184-L188) → [`FileUtils.clean():362-387`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileUtils.java#L362-L387) — invokes the direct buffer's cleaner, so the native memory is returned **at once**, not at the next GC (a heap buffer returns at [`:364-365`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileUtils.java#L364-L365) and is left to GC). The JDK direct pool's `MemoryUsed` falls by the old capacity minus 128 and its `Count` is unchanged.
3. **Nothing else happens.** The user has already copied its content out; no exception, log line or metric marks the branch; the caller does not learn which branch ran. The cost moves to the thread's next large item, which grows the buffer again from 128 bytes (two or more `allocateDirect` calls and as many frees, step 3–4 of §6a): a rate, not a byte, effect.
4. **Below 128.** With a limit under 128 (0 or negative included), every `close()` takes this branch, even for an untouched 128-byte buffer: each use of the scratch buffer then costs one 128-byte allocation and one free, and the thread retains 128 bytes (derived from [`:73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L73), [`:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L79)).

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | The thread's buffer: a `java.nio.DirectByteBuffer` (default) or a `HeapByteBuffer` over a `byte[]` (`cassandra.dob.allocate_type=onheap`), held in the `buffer` field ([`BufferedDataOutputStreamPlus.java:43`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L43)) of the thread's `DataOutputBuffer$1$1` instance. |
| **Resource consumed** | **Off-heap (native) memory**, through `ByteBuffer.allocateDirect`: counted in the JDK's direct buffer pool (`java.nio:type=BufferPool,name=direct`, `MemoryUsed` and `Count`) and against `-XX:MaxDirectMemorySize` (commented out in [`conf/jvm-server.options:174`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/jvm-server.options#L174)). In heap mode, heap bytes. |
| **Rough sizing** | **Idle (what the check bounds):** 128 bytes, or the capacity the last use grew it to if that is at most the limit, so at most `max(limit, 128)` per thread. **In use (what it does not bound):** from a capacity *c*0, an item of *S* bytes leaves a capacity *C* with `max(c0, S) ≤ C ≤ max(c0, 2(S − 1))` while below 64 MiB (each growth is to `max(2c, c + count)`, and doubling happens only when at least one more byte follows a full buffer). The two ends are both reached on the write path: **(i)** a single-cell mutation serialized field by field (site 1 when the mutation is not cached, or site 2), whose last byte (the end-of-partition marker, [`UnfilteredSerializer.java:413-416`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L413-L416), [`UnfilteredRowIteratorSerializer.java:153`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredRowIteratorSerializer.java#L153)) follows a value written in one call ([`ValueAccessor.java:171-175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/ValueAccessor.java#L171-L175), [`ByteBufferAccessor.java:61-64`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/ByteBufferAccessor.java#L61-L64)), ends at **exactly *C* = 2(*S* − 1)** whenever *c*0 ≤ (*S* − 1)/2: the value's write grows the buffer to exactly *S* − 1 (`capacity + count`), and the final byte doubles it. During that last copy the old buffer is still live, so **the thread's transient peak is 3(*S* − 1)**. **(ii)** A mutation whose serialization is already cached is written in one call ([`Mutation.java:563`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L563)), so site 1 ends at **exactly *C* = max(2*c*0, *S*)** for *c*0 < *S*, i.e. *S* from a 128-byte buffer (*S* > 256). At site 1 the item is bounded by `max_mutation_size`: `validateSize()` refuses *S* + 12 above it ([`CommitLogSegment.java:93`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L93) gives the 12), so ***C* ≤ 2(*M* − 13)** there, about 32 MiB at the default *M* = 16 MiB. Site 4's item is one row body and has no such bound; above 64 MiB of capacity it grows by half. **Consistent with a stage-4 recording of another case** (cited, not measured here): the `CACHEABLE_MUTATION_SIZE_LIMIT` unit tier recorded the scratch capacity after a 99,999-byte copy at site 2 as 199,996 = 2(99,999 − 1), and after a 999,999-byte copy as 128 (grown past 1 MiB, replaced) ([results §4.1, row "Scratch (recorded)"](../../stage4-runtime-verification/results/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md)). |
| **Lifetime / release** | **As long as the thread lives**, unless a later use grows it (the old buffer is freed at the growth) or finds it above the limit at `close()` (freed at once). Nothing outside the thread can reach it: no registry, no metric, no shrink on idle, and nothing in the tree calls `scratchBuffer.remove()` or `FastThreadLocal.removeAll()`. **The threads that hold one mostly never die:** the shared-pool workers (below) park when idle and leave only at shutdown or on an unexpected throwable ([`SEPWorker.java:102-103`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L102-L103), [`:116-118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L116-L118), [`:177-206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L177-L206)), and single-threaded executors keep their thread ([`ThreadPoolExecutorBuilder.java:97-101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java#L97-L101)). Pooled executors (memtable flush [`ColumnFamilyStore.java:207`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L207), compaction [`CompactionManager.java:2032-2038`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L2032-L2038), hint dispatch [`HintsDispatchExecutor.java:68-72`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsDispatchExecutor.java#L68-L72)) let even core threads die after one idle minute ([`ThreadPoolExecutorBuilder.java:73-75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java#L73-L75)). When such a thread dies, its instance becomes unreachable and its direct buffer is freed **only when a GC runs the buffer's cleaner**: Cassandra's threads are `FastThreadLocalThread`s ([`NamedThreadFactory.java:162`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/NamedThreadFactory.java#L162), [`SEPWorker.java:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L58)), whose exit hook in Netty (4.1.130.Final, [`.build/parent-pom-template.xml:749`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/.build/parent-pom-template.xml#L749)) drops the thread-local values without a removal callback here (`scratchBuffer` overrides none) — inferred from Netty's API, not read in this clone; unit step U5 records it. |

**Which threads hold one, and how many (write-up question 2).** The queue note counts "mutation, read, hints,
transport stages"; in 5.0 most of those are **one pool**. `ReadStage`, `MutationStage`, `CounterMutationStage`,
`ViewMutationStage` and `RequestResponseStage` are executors of the shared pool
([`Stage.java:45-48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/Stage.java#L45-L48),
[`:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/Stage.java#L50),
[`:228-234`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/Stage.java#L228-L234)),
and so is `Native-Transport-Requests`
([`Dispatcher.java:58-61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L58-L61)).
Their tasks run on the same worker threads, which take the executor's name while running its task
([`SEPWorker.java:124-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L124-L125));
a new worker is made only when no spinning or parked one can take the work
([`SharedExecutorPool.schedule():101-117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java#L101-L117)).
A coordinator's local write runs **inline on the request thread** when the mutation stage has a free work permit
([`StorageProxy.java:1569`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1569)
→ [`:1674-1676`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1674-L1676)
→ [`SEPExecutor.maybeExecuteImmediately():218-239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L218-L239)),
and on another worker otherwise. Read tasks do not use the scratch buffer, but a worker that once served a write
keeps its buffer while it serves reads. So the threads holding a scratch buffer are: **(1)** the shared-pool
workers that have ever run a write-side task — at most about the peak number of simultaneously busy shared-pool
tasks, whose ceiling at the defaults is `concurrent_reads` + `concurrent_writes` + `concurrent_counter_writes` +
`concurrent_materialized_view_writes` (32 each, [`Config.java:179-182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L179-L182))
+ `native_transport_max_threads` (128, [`:283`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L283))
+ `native_transport_max_auth_threads` (4, [`:287`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L287))
+ one `RequestResponseStage` slot per core (inferred from `schedule()`; not a configured bound); **(2)** the messaging
event-loop threads that deserialize small inbound mutations (site 3); **(3)** flush and compaction threads (site 4)
while alive; **(4)** hint dispatch threads (`max_hints_delivery_threads`, 2, [`Config.java:443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L443)),
`HintsWriteExecutor`, the batchlog and replay threads, and any thread that applies a system-table write. On a
32-core node at the defaults group (1) alone is up to 292 threads, so 292 MiB of idle direct memory at the default
limit (an upper bound, inferred; reaching it needs every worker's last kept capacity to be close to 1 MiB).

## 8. Maximum memory bound

**The limit caps idle retention per thread, and only that.** After any `close()`, a thread's scratch buffer
holds the capacity its last use grew it to if that is at most the limit, else 128 bytes; so each thread retains
at most `max(L, 128)` bytes between uses, and the node retains at most **T × max(L, 128)**, *T* being the live
threads that have used a scratch buffer (§7). Raising *L* raises that ceiling linearly; lowering it lowers it,
down to the floor of 128 bytes per thread.

**What it does not bound.** While a thread is using its buffer, the buffer grows to fit the item, whatever *L*
is: at the commit-log site up to 2(*S* − 1) with a transient 3(*S* − 1) for a mutation of *S* bytes, at most
about 2 × `max_mutation_size`; at the SSTable writer, one row body, with no bound here (§7). So the node's
instantaneous peak is the in-use buffers of the threads busy at that moment plus the idle retention of the
rest, and *L* moves only the second term. **Above the largest capacity any thread's buffer reaches, the check
never fires** and every thread keeps its high-water mark: about 2(*M* − 13) per thread that applies a large
write (32 MiB at the defaults), and as much as the largest row for flush and compaction threads (Target-3
material, §10). **Below the common item sizes**, retention falls to 128 bytes per thread and each large item
re-grows its buffer: allocation churn, not bytes.

**It is per thread, so it scales with thread counts it does not see.** Node-wide idle retention moves with
`native_transport_max_threads`, the `concurrent_*` stage sizes and the internode event-loop count as much as with
*L*. Retention also outlives the load that caused it: the shared-pool workers never time out, so a burst of
writes just under *L* leaves up to *L* on every worker it touched for the life of the process (§7).

**With `cassandra.dob.allocate_type=onheap`** the same bound applies to heap bytes: a freed buffer is not
cleaned (`FileUtils.clean()` ignores heap buffers) but becomes garbage, so idle retention is still at most
`max(L, 128)` per thread of *live* heap, and the direct pool is not used.

## 9. Test design (guidance for stage 4)

The unit tier drives one thread's scratch buffer to the limit and one byte past it, and checks the grow
policy, the thread mechanics and the property's edge values; the cluster tier holds *N* writes of known size
on *N* distinct threads of a node, lets them go idle, and reads the retained direct bytes with a Byteman ledger
of every scratch buffer and the JDK direct pool. Not yet run.

*Amended 2026-10-15 (stage-4 step-0 audit, before any reading; results file §1.1).* (1) **The cluster client uses native protocol 4, not 5.** A v5 request larger than one frame (131,060 B of payload) is assembled from frame stashes that are never returned (`CQLMessageHandler.java:755-840`, `LargeMessage.assembleFrame()` wraps them and `onComplete()` does not release them); the `networking_cache_size` stage-4 run of 2026-10-15 measured it (arm L: 64 one-MB INSERTs over v5 left `java.nio` direct 16.8 MB above idle **after** a forced GC, and 5,373,952 B of pooled slots never returned). That is per request, so the twin warm-up cannot absorb it, and it would put several MB per batch into ΔMemoryUsed that no scratch buffer accounts for (B2 and B3 send 16 requests of 0.45 and 1.9 MB). Protocol 4 decodes requests through Netty's pooled allocator (`CBUtil.java:60`, `PooledByteBufAllocator(true)`), whose arenas are warmed by the twin and are not part of this frame path; the server-side write path (`CommitLog.add()`, the scratch buffer) is the same for both protocols. (2) Checked and unchanged: the value is written in one `write(ByteBuffer)` call (`BufferedDataOutputStreamPlus.java:124-138`), so from a 128-byte buffer with *P* bytes in it the growth is to exactly *V* + *P* (`max(256, 128 + V − 128 + P)`), and exactly one byte follows it (`UnfilteredSerializer.writeEndOfPartition()`, `UnfilteredRowIteratorSerializer.java:153`), so *C* = 2(*V* + *P*) and *S* = *V* + *P* + 1 as §9a states; `memtable_allocation_type` defaults to `heap_buffers` (`conf/cassandra.yaml:825`), so the memtable adds no direct bytes.

### 9a. Procedure and conclusions

**Testability:** **JVM system property, restart-only** (`-Dcassandra.dob_max_recycle_bytes=<bytes>`, read once
into a `static final`). No yaml key, JMX or `nodetool` setter, and no log line prints it: read it back from the
JVM's system properties and from the ledger's `L=` field (9d). The unit tier needs a fresh JVM per value.

**Claim under test:** at `close()`, a thread's scratch buffer of capacity *C* is kept iff *C* ≤ *L* and is
otherwise freed at once and replaced by a 128-byte buffer, so each thread retains at most `max(L, 128)` direct
bytes between uses and *N* threads retain *N* × (*C* or 128); the buffer's size in use is set by the grow
policy, not by *L* (§5, §6b, §7, §8).

**How this verifies the hypothesis** (a restatement of the claim, procedure, prediction and conclusions in
this section; it adds none):

- **Hypothesis:** `cassandra.dob_max_recycle_bytes` caps the direct bytes each thread's scratch buffer keeps
  between uses; above it the buffer is freed at `close()` and replaced by 128 bytes.
- **Test:** unit tier — one buffer per fresh thread, written to capacity *L* and *L* + 1 at *L* = 256 KiB,
  1 MiB (default) and 4 MiB, plus the grow policy, thread death, *N* threads, *L* = 64 and heap mode. Cluster
  tier — one node, the same three values; per node start, 16 writes of one size held 5 s each on 16 distinct
  threads, at sizes whose buffers end below, at, and above each *L*; retained bytes read from a ledger of every
  scratch buffer and from the JDK direct pool, after a forced GC, with an un-logged twin keyspace as control.
- **Logic:** (1) each held write ran on its own thread and its buffer reached the predicted capacity *C*
  = 2(*V* + *P*) (else the run is invalid); (2) a buffer with *C* ≤ *L* is kept and one with *C* > *L* is
  replaced, at the boundary pair *C* = *L* / *L* + 2 too: the **disallow branch** acts at the limit; (3) the
  same write size is kept at one *L* and replaced at a smaller one (the staircase): retention **follows the
  constraint**; (4) retained bytes are *N* × *C* or *N* × 128 and scale with *N*: the bound is per thread;
  (5) the direct pool agrees with the ledger: the counter is the resource; (6) the in-use peak is the same at
  every *L*: the limit bounds idle retention only.
- **Refuted if:** a buffer above *L* is kept or one at or below *L* is freed; retention does not move with *L*
  across the staircase; the direct pool keeps more than the ledger accounts for; or the in-use capacity is not
  the grow policy's (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — harness test `DobRecycleTest` (9c), U1–U10, one JVM per value; plus upstream
   `DataOutputTest`. The instrument check (the same test under the ledger rules, 9e step 0) comes first.
2. **Cluster tier** — one node (9b), `cassandra.cacheable_mutation_size_limit_bytes=1` held fixed, at
   *L* = 262,144, 1,048,576 (default) and 4,194,304.
3. **At each value**, one fresh node start per batch: calibration write → twin warm-up (control) → idle
   control window → **scenario A** (batch BA, *C* = *L*: just reach) → **scenario B** (batch BB, *C* = *L* + 2;
   and the staircase batches B1, B2, B3: try to exceed) → readings after idle. At the default only: batch BN
   (*N* = 4) and the 70-second persistence reading. **Scenario C**, settings that turn the check off or make
   it fire on every close: *L* = 2,147,483,647 and *L* = 64. **Arm H**, heap mode, at the default.
4. **Compare** with the prediction below and read the result in the table.

**Prediction.** Notation: *V* = the blob's length in bytes; *P* = the bytes of the serialized mutation before
the blob's content, constant for this schema while *V* < 2,097,152 (3-byte length), **measured by the calibration
write of each node start** as *P* = *S*0 − 20,001 (*S*0 from the ledger, 9e) and expected in [20, 127];
*S* = *V* + *P* + 1, the serialized size; *C* = **2(*V* + *P*)** = 2(*S* − 1); *N* = 16 held writes unless stated.
The precondition of the formula is that the thread's capacity before the write is at most (*V* + *P*)/2, which
holds for a fresh or 128-byte buffer and for the calibration's thread (about 40,100 bytes) at every *V* used here.

*Unit tier* (exact):

- U3: a fresh buffer after `write(new byte[L])` has capacity *L* and after `close()` is the **same** buffer
  object at capacity *L*, position 0; after `write(new byte[L + 1])` and `close()` it is a **new** buffer of
  capacity 128. Direct pool, after the thread's first `get()`: +*L* − 128 for the first, +0 for the second
  (`Count` +0 in both; the growth freed the 128-byte buffer, the replacement freed the *L* + 1 one).
- U4 grow policy from a fresh buffer: *n* single bytes give 128 × 2^⌈log2(*n*/128)⌉ (*n* = 129 → 256,
  256 → 256, 257 → 512, 100,000 → 131,072, 1,048,577 → 2,097,152); a 50-byte prefix, one
  `write(ByteBuffer)` of *V* and one byte give 2(*V* + 50) (*V* = 1,000 → 2,100; 100,000 → 200,100;
  524,238 → 1,048,576, kept at the default; 524,239 → 1,048,578, replaced at the default); one `write(byte[] S)`
  gives max(256, *S*) (1,000 → 1,000; 999,999 → 999,999); `calculateNewSize(1)` on a spy that overrides `capacity()` (as
  upstream's `DataOutputBufferSpy`) gives 128 MiB at 64 MiB and (3 × (64 MiB + 2))/2 at 64 MiB + 2.
- U5: a parked thread's retained buffer survives `System.gc()` (pool unchanged); after a thread that kept a
  262,144-byte buffer ends, the pool still holds it until a `System.gc()`, after which `MemoryUsed` falls by
  262,144 and `Count` by 1 within 5 s.
- U6: 8 parked threads after `write(new byte[L])` + `close()` → pool +8(*L* − 128) over their first-`get()`
  baseline; after `write(new byte[L + 1])` → +0.
- U7 (*L* = 64): every `close()` replaces, even untouched: the buffer object changes at each close and the
  capacity stays 128. U8: `buffer(false)` then `close()` gives a new 128-byte buffer, no exception. U9 (heap
  mode, default *L*): `isDirect()` false, direct pool unchanged across get/grow/close, same keep/replace rule
  on `array().length`. U10: `-Dcassandra.dob_max_recycle_bytes=1MiB` and `-Dcassandra.dob.allocate_type=heap`
  each make the first touch of `DataOutputBuffer` fail with `ExceptionInInitializerError` (recorded, not a
  conclusion).

*Cluster tier* — the ks1 threads' capacity after `close()` (*C* if kept, 128 if replaced):

| Batch | *V* | *C* | *L* = 262,144 | *L* = 1,048,576 (default) | *L* = 4,194,304 |
|---|---|---|---|---|---|
| B1 | 100,000 | 200,000 + 2*P* | kept | kept | kept |
| B2 | 450,000 | 900,000 + 2*P* | **replaced** | kept | kept |
| B3 | 1,900,000 | 3,800,000 + 2*P* | **replaced** | **replaced** | kept |
| BA (scenario A) | *L*/2 − *P* | *L* exactly | kept | kept | kept |
| BB (scenario B) | *L*/2 − *P* + 1 | *L* + 2 | **replaced** | **replaced** | **replaced** |

- **Per write (ledger):** exactly 16 distinct thread ids hold a ks1 write; each of their `close` lines shows
  capacity *C* and `limit` = *S*; the branch line is `kept` iff *C* ≤ *L*; the thread's capacity after the
  close is *C* or 128; the write's buffer is grown by exactly two allocations, *V* + *P* then 2(*V* + *P*), plus
  128 for a replacement (and 128 at creation for a thread that had no scratch buffer).
- **Retained (ledger):** the 16 ks1 threads end with 16*C* (kept) or 2,048 bytes (replaced), e.g. B2 at the
  default 14,400,000 + 32*P*, B3 at 4 MiB 60,800,000 + 32*P*; ΔR, the change of the ledger's total over all
  scratch buffers between the before and after readings, equals the sum over those threads of (final −
  initial capacity) exactly, and no other scratch buffer changes.
- **Real resource:** |ΔMemoryUsed − ΔR| ≤ τ = 262,144 bytes at every batch (direct pool, after a forced GC),
  and ΔCount equals the ledger's change in live scratch buffers (new instances only).
- **Staircase:** for B2 and B3 the retained bytes jump from 2,048 to 16*C* exactly between the values the table
  marks; flat across *L* for B1, BA and BB.
- **×N:** BN (*N* = 4, *V* = 450,000, default) retains 4*C*: one quarter of B2 by the ledger, and
  ΔMemoryUsed(B2) − 4 × ΔMemoryUsed(BN) within 4τ of 0.
- **Persistence (B2, default):** 70 s after release (past the pooled executors' one-minute keep-alive) and a
  forced GC, MemoryUsed is within τ of the after-idle reading: the shared-pool workers keep their buffers.
- **In use:** each ks1 write's transient peak in the ledger is 3(*V* + *P*) at every *L* (identical across the
  three values for the same *V*).
- **Scenario C:** *L* = 2,147,483,647, B3 → kept, 16*C* (60,800,000 + 32*P*) retained (nothing else trims);
  *L* = 64, B1 → every scratch `close()` on the node is `replaced`, including 128-byte buffers, and the ks1
  threads retain 2,048 bytes.
- **Arm H** (heap mode, default *L*): every ledger allocation `direct=false`, |ΔMemoryUsed| ≤ τ for B2 and B3;
  live `[B` bytes after a full GC, compared with the same batch in direct mode at the default (identical memtable
  content): higher by 16*C*2 (14,400,000 + 32*P*) ± 2 MB after B2, within ± 2 MB after B3 (replaced, garbage).

**Conclusions.**

| Result | Conclusion |
|---|---|
| Every ks1 buffer with *C* ≤ *L* kept and every one with *C* > *L* replaced, including the boundary pair; retained bytes = 16*C* or 2,048 per batch; the staircase moves as tabled; ΔMemoryUsed within τ of ΔR; ×N and persistence hold | **Confirmed** — the check caps each thread's idle retention at *L*, and node-wide retention is *N* × that. |
| Scenario C at 2,147,483,647 retains 16*C*3 where the default retains 2,048 | **Bypass as recorded** — no other mechanism trims the buffer; record the bytes (Target-3 material). |
| A buffer above *L* is kept, or one at or below *L* is replaced | **Refuted** — the branch is not decided as traced in §5 (or *L* is not what is in force: check the read-back first). |
| Retained bytes do not change across *L* for B2 or B3 | **Refuted** — not the binding mechanism. Re-read, do not re-run. |
| The ledger's total is capped as predicted but ΔMemoryUsed exceeds ΔR + τ, repeatably and not explained by the twin control | **Refuted** for §8's resource claim — something else keeps direct memory per write; §8 needs amending. |
| The ks1 buffers' capacity is not 2(*V* + *P*), or the in-use peak differs across *L* | **Not confirmed (sizing)** — §7's grow-policy derivation is wrong; the keep/replace reading can still stand if it follows *C* as observed. |
| Retained bytes move with *L* but no `kept`/`replaced` branch line appears | **Not confirmed** — the rule did not fire; fix the instrument and re-run the tier. |
| Fewer than 16 distinct thread ids held ks1 writes, or a twin (ks0) write changed any scratch buffer, or the read-back *L* differs, or *P* is outside [20, 127] | **Invalid run** — *N* not held, the cacheable pin not in force, the wrong value, or the formula's precondition broken; fix 9b/9c and re-run the batch. |
| No batch reached *C* > *L* (or *C* = *L*) | **Invalid run** — the limit was never reached; check *P* and the sizes. |

A confirmation needs both the retained bytes following *L* (staircase) and the `kept`/`replaced` branch lines
for the same writes. The bypass row is attributed by its own arm, in which the check cannot
fire for the sizes used.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `-Dcassandra.dob_max_recycle_bytes=<bytes>` on the JVM command line (cluster: in `JVM_EXTRA_OPTS` for the `bin/cassandra` command only; unit: in `-Dtest.jvm.args`). Restart (new JVM) per value. The default arm omits it. |
| **Confirm it took effect** | `jcmd <pid> VM.system_properties \| grep -E 'dob_max_recycle_bytes\|dob.allocate_type\|cacheable_mutation'`; the ledger's `L=` field on every `close` line (the `static final` itself); unit U1 reads the field by reflection. |
| **Capacity values** | 262,144 · **1,048,576 (default)** · 4,194,304 bytes; scenario C 2,147,483,647 and 64; unit U10 `1MiB` (invalid). |
| **Scope** | **Per thread.** Node-wide retention is *N* × the per-thread value, *N* = threads that used a scratch buffer. *N* is held at 16 (4 in BN) by holding each ks1 write 5 s after its commit-log append, so the 16 writes are in flight on 16 distinct threads at once, and is counted from the hold trace. |
| **Level** | Both. Upstream `DataOutputTest` (`test/unit/org/apache/cassandra/io/util/`) covers the grow policy and the `MAX_ARRAY_SIZE` cap with a spy that overrides `capacity()` ([`DataOutputTest.java:126-167`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/util/DataOutputTest.java#L126-L167), [`:170-190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/util/DataOutputTest.java#L170-L190), [`:220-250`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/util/DataOutputTest.java#L220-L250)); **no upstream test reaches `scratchBuffer.close()`**. |

**Hold fixed** (cluster):

| Setting | Value | Why |
|---|---|---|
| `cassandra.cacheable_mutation_size_limit_bytes` | `1` (JVM property) | Removes site 2 and the tee from the write path ([`Mutation.java:451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451): no size is below 1), so `CommitLog.add()` is the only scratch user per write and it walks the mutation (*C* = 2(*V* + *P*)). At the default the request thread would also grow a buffer to 2(*S* − 1), and the commit-log write would be a one-shot write of *S* (§7 (ii), §11). |
| `cassandra.dob.allocate_type` | unset (direct); `onheap` in arm H only | the resource read |
| heap | `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE=800M` | the per-IP in-flight request reserve is heap/40 ([`DatabaseDescriptor.java:654-656`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L654-L656)), about 102 MiB, above 16 × 2.1 MB in flight |
| `write_request_timeout` / `native_transport_timeout` | `30000ms` / `30s` | the 5 s hold is longer than the 2 s write timeout; the client must not give up |
| `concurrent_writes` / `native_transport_max_threads` | `32` / `128` (defaults) | ≥ 16, so all 16 held writes run at once on distinct threads |
| `max_mutation_size`, `commitlog_segment_size` | defaults (16 MiB, 32 MiB) | *S* + 12 ≤ 16 MiB for every *V* used |
| keyspaces | `ks1` (`durable_writes = true`), `ks0` (`durable_writes = false`), both SimpleStrategy RF 1, table `t (k int PRIMARY KEY, v blob)` | ks0 writes skip `CommitLog.add()` ([`Mutation.java:266-270`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L266-L270), [`CassandraKeyspaceWriteHandler.java:51-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L51-L53)), so they exercise the network and memtable path with no scratch use |
| memtables, compaction | defaults; at most about 70 MB written per start | no flush in a start, so no flush thread joins site 4 during a batch |
| NMT | `-XX:NativeMemoryTracking=summary` | reported only (Netty arenas inflate `Other`) |
| node | `pc57`, single node on loopback, Byteman 4.0.20 agent with `dob-ledger.btm` and `hold.btm` | as the earlier long-path harnesses |

**Controls:** (1) the **twin warm-up**: the batch's 16 writes sent to ks0 before the baseline — absorbs the
network path's direct allocations (networking buffer-pool chunks, Netty) and must leave every scratch buffer
unchanged in the ledger; (2) the **idle window**: 20 s with no client writes before the baseline, ledger and
pool drift recorded; (3) the default *L* and the staircase as the knob's own control.

**Reset between batches:** stop the node; delete `data/`, `commitlog/`, `saved_caches/`, `hints/`; start fresh
(every batch begins with no ks1-grown scratch buffer on any thread).

### 9c. Workload

**Unit tier.** New harness test `test/unit/org/apache/cassandra/io/util/DobRecycleTest.java` (package-private
access to `capacity()` and the `buffer` field). Every probe runs on its own `io.netty.util.concurrent.FastThreadLocalThread`,
which parks on a latch after its last step so the pool can be read while it is alive; the direct pool is read
with `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` (`name = "direct"`), as a delta from just
after the thread's first `get()`. Lines `STAGE4 <step> <field>=<value>` go to `-Dstage4.out`. Steps U1–U10 as
in 9a's unit prediction (U1: read-back of `MAX_RECYCLE_BUFFER_SIZE` and `ALLOCATION_TYPE` by reflection; U2:
first `get()` gives capacity 128, direct; a second `get()` on the thread returns the same instance, another
thread a different one).

```bash
ant testsome -Dtest.name=org.apache.cassandra.io.util.DataOutputTest
for L in 262144 4194304 64; do
  ant testsome -Dtest.name=org.apache.cassandra.io.util.DobRecycleTest \
    "-Dtest.jvm.args=-Dcassandra.dob_max_recycle_bytes=$L -XX:MaxDirectMemorySize=1g -Dstage4.out=<logs>/unit-$L.out"
done
ant testsome -Dtest.name=org.apache.cassandra.io.util.DobRecycleTest \
  "-Dtest.jvm.args=-XX:MaxDirectMemorySize=1g -Dstage4.out=<logs>/unit-default.out"
ant testsome -Dtest.name=org.apache.cassandra.io.util.DobRecycleTest \
  "-Dtest.jvm.args=-Dcassandra.dob.allocate_type=onheap -XX:MaxDirectMemorySize=1g -Dstage4.out=<logs>/unit-onheap.out"
# U10, two runs expected to fail at class initialization (record the exception):
#   -Dcassandra.dob_max_recycle_bytes=1MiB   and   -Dcassandra.dob.allocate_type=heap
```

U3 and U6 need *L* ≥ 256 (a one-shot write gives max(256, *n*)); at *L* = 64 the test runs U1, U2, U7, U8.

**Cluster tier.** A small client `dob-writes.py` (bundled Python driver, protocol 4 (*amended 2026-10-15*, (1)), request timeout 60 s, as
the `CACHEABLE_MUTATION_SIZE_LIMIT` harness's `send-mutation.py`): prepared `INSERT INTO <ks>.t (k, v) VALUES (?, ?)`,
sends *n* writes with keys `first..first+n-1` and a blob of *V* zero bytes all at once (`execute_async`), waits
for all, prints `acked=<n> ms=<elapsed>`. Per batch: calibration (ks1, *n* = 1, *V* = 20,000, key −1), twin
warm-up (ks0, *n* = *N*, the batch's *V*), batch (ks1, *n* = *N*, *V*). Each ks1 write is held 5 s at the exit of
`CommitLog.add()` (after its scratch `close()`), so the batch's writes are in flight together on distinct threads.

```bash
python3 <H>/dob-writes.py --ks ks1 --n 1  --value 20000 --first -1        # calibration → P
python3 <H>/dob-writes.py --ks ks0 --n 16 --value <V>   --first 0         # twin warm-up (control)
python3 <H>/dob-writes.py --ks ks1 --n 16 --value <V>   --first 0         # batch
```

*V* per batch: B1 100,000; B2 450,000; B3 1,900,000; BA *L*/2 − *P*; BB *L*/2 − *P* + 1 (computed from the
start's calibration); BN as B2 with `--n 4`. Data per start under 70 MB; one start takes about 90 s, about
20 starts in all (15 for the three values × five batches, BN, two scenario-C starts, two arm-H starts with B2
and B3).

### 9d. Observables

| Observable | How to read it (command) | When to sample | Trap |
|---|---|---|---|
| **Usage operand and disallow evidence** — the ledger, `dob-ledger.btm` | Byteman rules on Cassandra classes, all lines with `tid=<Thread.getId()>`, `name=`, `dob=<identityHashCode of the instance>`, `ms=`: **new** `DataOutputBuffer$1.initialValue` AT EXIT (`cap` of `$!`); **alloc** `DataOutputBuffer$1$1.allocate(int)` AT EXIT (`size=$1`, `direct=$!.isDirect()`); **grow-free** `DataOutputBuffer.expandToFit` AT INVOKE `setBuffer`, if `$0`'s class is `…DataOutputBuffer$1$1` (old `cap`); **close** `DataOutputBuffer$1$1.close` AT ENTRY (`cap`, `pos`, `limit` of `$0.buffer`, and `L=` the static `MAX_RECYCLE_BUFFER_SIZE`); **kept** AT LINE 75; **replaced** AT LINE 79 (old `cap`); **closed** AT EXIT (`cap`). `ledger.py` replays alloc/free per `dob` to give each buffer's live bytes over time, the total *R*, per-write peaks and each thread's capacity after its last close. | continuous to `-Dstage4.ledger.out`; the script marks the file offset at each reading | **Key by thread id, not name:** shared-pool workers rename themselves per task (`Native-Transport-Requests-7`, then `MutationStage-7`). The item size is `limit` for flipped users (commit log, SSTable rows, hints) and `pos` for the others. Parse-check with Byteman's `TestScript`; if the type checker refuses the private static field, print it by reflection. |
| **Hold trace** — `hold.btm` | `CommitLog.add` AT EXIT, if `$1.getKeyspaceName().equals("ks1")`: line `held tid= name= ms=`, then `delay(stage4.hold.ms)` (5,000) | each ks1 write | Count distinct `tid`: 16 (4 in BN) or the batch is invalid. The calibration write is held too. |
| **Real resource** — JDK direct pool | `bin/nodetool sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed` and `-f Count` (one attribute per call), each preceded by `jcmd <pid> GC.run` and 2 s | before the batch (after the idle window), during the hold (3 s after the 16th `held`), 10 s after the last ack; B2 at the default also 70 s later | Counts every JDK direct buffer (buffer-pool chunks, read-ahead buffers, some Netty buffers), not only scratch buffers: read differences across the batch only, after the twin warm-up, and attribute with the ledger. The forced GC removes unreachable direct buffers that wait for their cleaner; scratch frees are explicit and need none. |
| **Heap (arm H only)** | `jcmd <pid> GC.class_histogram \| grep -E ' \[B$'` (live bytes; runs a full GC) | 10 s after the last ack, in arm H and in the default-*L* B2 and B3 starts | `[B` moves about 1 MB in 10 s on an idle node (the `CACHEABLE_MUTATION_SIZE_LIMIT` run), and the memtable holds the written values: compare arm H with the direct-mode start of the **same** batch, never B2 with B3 and never absolute |
| **NMT** | `jcmd <pid> VM.native_memory summary` | with the pool readings | reported only: Netty's arenas inflate `Other` (the `file_cache_size` run) |
| **Calibration** | the ledger `close` line of the key −1 write: `limit` = *S*0 | after the calibration write | *P* = *S*0 − 20,001; outside [20, 127] → stop (Invalid) |

No metric or log line marks either branch, so the `kept`/`replaced` lines are the only direct evidence; only
these two rules print them.

### 9e. Running the scenarios

0. **Instrument check** (stage-4 step 1, before run 1): run `DobRecycleTest` at the default with
   `-javaagent:<BM>/byteman-4.0.20.jar=script:<H>/dob-ledger.btm -Dstage4.ledger.out=<logs>/instrument.txt` in
   `-Dtest.jvm.args`. Known answer for the U4 probe *V* = 100,000 after a 50-byte prefix: one `new` (cap 128),
   `alloc size=100050`, `grow-free cap=128`, `alloc size=200100`, `grow-free cap=100050`, `close cap=200100`,
   `kept`, `closed cap=200100`; `ledger.py` peak 300,150 for that `dob`; and for the *L* + 1 probe a `replaced`
   line with `cap=1048577` followed by `alloc size=128`. A mismatch stops the run.
1. **Unit tier** — 9c's commands; record every `STAGE4` line; upstream `DataOutputTest` must pass.
2. **Per cluster batch** (values × batches of 9c; scenario C and arm H the same with their settings):
   1. Stop, wipe (9b), write the yaml rows of 9b, start with
      `JVM_EXTRA_OPTS="-Dcassandra.dob_max_recycle_bytes=<L> -Dcassandra.cacheable_mutation_size_limit_bytes=1 -XX:NativeMemoryTracking=summary -javaagent:<BM>/byteman-4.0.20.jar=script:<H>/dob-ledger.btm,script:<H>/hold.btm -Dstage4.ledger.out=<D>/ledger.txt -Dstage4.hold.out=<D>/hold.txt -Dstage4.hold.ms=5000" bin/cassandra -p <D>/pid`
      (omit the first property for the default; add `-Dcassandra.dob.allocate_type=onheap` for arm H); wait for
      `nodetool status` `UN` and `nodetool statusbinary` `running`.
   2. Read back (9b); create ks1, ks0 and the tables; one probe read (`SELECT * FROM ks1.t LIMIT 1`) to warm the client.
   3. Calibration write; compute *P*; for BA/BB compute *V*.
   4. Twin warm-up; wait for all acks.
   5. Idle 20 s; reading **before** (GC, MemoryUsed, Count, NMT, ledger offset).
   6. Batch; 3 s after the 16th `held` line, reading **hold**; wait for all acks.
   7. Idle 10 s; reading **after**. B2 at the default: wait 70 s more; reading **persist**.
   8. Stop the node; keep `ledger.txt`, `hold.txt`, the readings and the client output under `<D>/raw/`.
3. **Scenario C** — *L* = 2,147,483,647 with B3; *L* = 64 with B1 (also count `replaced` lines on non-ks1
   threads during the idle window: every close there replaces).
4. **Arm H** — default *L*, `onheap`, B2 then B3 in separate starts; add the histogram reading at step 7 (also
   taken in the default-*L* B2 and B3 starts of step 2, for the comparison).

**Record for stage 4:** the JVM command line and yaml in force, *P* per start, each batch's *V* and *N*, the
16 thread ids, the ledger lines of the ks1 writes, *R* and the pool readings at before/hold/after(/persist),
and the unit `STAGE4` lines.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — [`../../../stage2-ai-preprocessing/bands.csv`](../../stage2-ai-preprocessing/bands.csv) row `src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:73#1` (band **C**, "buffer recycling decision against a max recycle size", batch-26, 2026-09-24). Qualified by the band-C pass on 2026-10-13 (`predicted-negative.md`, batch "band C"), to which the band-A3 pass pointed ("What A3 taught", the one cap on retained high-water buffers); `predicted-positive.md` write-up queue item 13. |
| **Filed by / Date** | Claude (`claude-opus-5-5`) session, 2026-10-15 |
| **Line numbers checked** | 2026-10-15, against the local clone `/home/user/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). Every cited `file:line` and range was checked by a script that resolves each GitHub link to the clone, confirms the range is inside the file, and finds an expected code snippet in the cited lines. |
| **Escape hatch / Target-3 note** | **(1) A large value turns the trim off:** with `cassandra.dob_max_recycle_bytes` at or above the largest capacity a thread reaches, every thread keeps its high-water mark — up to 2(*M* − 13) (about 32 MiB at the default `max_mutation_size`) per thread that applies a large write, and up to the largest row for flush and compaction threads — and nothing else trims it (scenario C). **(2) Thread count is the multiplier and is not limited here:** the same limit retains more as `native_transport_max_threads` and the `concurrent_*` sizes grow (§7, §8). **(3) Dead pooled threads' buffers wait for a GC** (§7). **(4) A value below 128** makes every use allocate and free a 128-byte buffer (churn, no retention gain). **(5) No range check:** invalid text or an unknown allocation type stops `DataOutputBuffer` initializing. |
| **Stage-4 feedback** | **2026-10-15, run 1 on `pc57`, no run 2 — unit Confirmed; cluster Confirmed (§9a row 1), one sub-prediction missed (ΔCount); scenario C at 2³¹ − 1 bypass as recorded.** Results: [`../../../stage4-runtime-verification/long-path/results/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE.md`](../../stage4-runtime-verification/results/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md). Step-0 audit Ready after amendments (§9a frozen `634e47fc…`, unchanged; the client moved to native protocol 4 because large v5 requests leave unreturned frame stashes in direct memory, as the `networking_cache_size` run measured). 20 node starts, *P* = 42 in each: every one of 308 held writes grew its scratch buffer to exactly 2(*V* + *P*) with a transient peak of 3(*V* + *P*) at every *L*, and was kept iff *C* ≤ *L* — boundary pairs *C* = *L* kept / *L* + 2 replaced at 262,144 · 1,048,576 · 4,194,304; 16 threads retained 16*C* or 2,048 B exactly (ledger), the JDK direct pool agreeing within 43 KB; staircase B2 2,048 → 14,401,344 B, B3 2,048 → 60,801,344 B; ×N (¼ for 4 threads); persistence after 70 s; *L* = 64 replaces every close; heap mode the same rule on `[B` (+14.4 MB kept, ≈ 0 replaced). **Missed:** the pool's `Count` rose 2–4 more than the new scratch instances in every start — a supplementary traced lifetime showed two Netty `IovArray` direct buffers of 16 KiB per batch (one per newly used epoll event loop of the client's new connections) and small read-path holders; a note for 9d, not a refutation. **Sized for Target 3:** at *L* = 2³¹ − 1, 16 threads keep 60.8 MB after 1.9 MB writes. Unit: 205/205 checks plus upstream `DataOutputTest` 15/15; `1MiB` and `heap` fail class initialization as §4 says. Nothing in §5–§8 is refuted or amended. |
| **Notes** | **Corrections to the queue note (`predicted-positive.md` item 13), found on re-reading the source; `predicted-positive.md` is not rewritten.** *(a) The class:* the check is in `DataOutputBuffer$1$1.close()` (the anonymous buffer inside the anonymous `FastThreadLocal`), not `$1`; a Byteman rule on `$1.close` would never fire. *(b) "max_mutation_size §5":* that case's §5 only quotes the scratch `try`; the recycle is described in its §6a step 5 and §7 "Rough sizing". *(c) "Up to about twice max_mutation_size" (A3's growth rows):* exact at the commit-log site: 2(*S* − 1) for a mutation walked field by field from a small buffer (transient 3(*S* − 1)), but *S* for a cached mutation written in one call, and in general between max(*c*0, *S*) and max(*c*0, 2(*S* − 1)); bounded by 2(*M* − 13) only at the commit-log site — the SSTable row site has no such bound (§7). *(d) The thread count:* "mutation, read, hints, transport stages" are, except hints, executors of one shared pool whose workers rename per task and never time out; reads do not use the buffer themselves; the count is shared-pool workers ever used for a write-side task, plus event loops, flush/compaction (while alive), hints, batchlog and replay threads (§7). *(e) "Every write":* every **durable** write; `durable_writes = false` and memtables that skip the commit log do not reach site 1 ([`CassandraKeyspaceWriteHandler.java:66-96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L66-L96)). *(f) Measurement:* the direct `BufferPoolMXBean` is right but not isolating (it counts every JDK direct buffer); the design reads it as a difference after a twin warm-up and attributes it with a Byteman ledger. The queue note's other claims (the check, the 128-byte replacement and the clean at [`:186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L186), the property and default at [`:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L204), direct unless [`:183`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L183) says otherwise, the six users) hold. **Also found:** the code comment at [`DataOutputBuffer.java:50-52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L50-L52) says larger buffers are "trimmed back to this size"; they are replaced by 128 bytes. **No second recycle site:** `MAX_RECYCLE_BUFFER_SIZE` has one reader; the subclasses `DataOutputBufferFixed` (throws instead of growing, [`DataOutputBufferFixed.java:50-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBufferFixed.java#L50-L53)), `SafeMemoryWriter` ([`SafeMemoryWriter.java:24`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L24)) and `StreamingDataOutputPlusFixed` are not thread-local and are not recycled; `BigFormatPartitionWriter` keeps its own per-writer buffer of twice `column_index_cache_size` and its comment names this recycler ("only recycles up to 1MB", [`BigFormatPartitionWriter.java:193-205`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L193-L205)); there is no `RecyclableDataOutputBuffer` in 5.0.9. **Module:** `io_buffers` is new (`_INDEX.md` §3); `mutation` was the alternative, but two of the six users are not mutation code. |

---

## 11. Notes

- **Rule 3 is the judgement to confirm.** §5 states the reading: the check withholds no creation (the
  disallow branch is the one that allocates), and passes only because what stays resident differs. If the
  stricter reading is preferred, the refusal entry for `predicted-negative.md` would be: *[`DataOutputBuffer.java:73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L73)
  — Rule 3, retention not creation: the buffer is grown before the check whatever its verdict; the check
  decides only whether it stays on the thread between uses (128 bytes otherwise).*
- **Interplay with `CACHEABLE_MUTATION_SIZE_LIMIT` at stock settings** (inferred from §7's sizing; the cluster
  tier pins that property to 1 to avoid it). For a single-node coordinator's single-cell write of *S* bytes,
  at the defaults (cacheable limit 1,000,000, *L* = 1,048,576): **(i)** *S* ≤ 524,289 — the request thread's
  serialization at site 2 grows its buffer to 2(*S* − 1) ≤ *L* and keeps it; the commit-log write then needs no
  growth if it runs inline on that thread, or leaves *S* on a mutation-stage thread; **(ii)** 524,289 < *S* <
  1,000,000 — site 2's buffer (2(*S* − 1) > *L*) is replaced, and the commit-log write, a one-shot copy of the
  cached bytes, leaves exactly *S* (≤ *L*) on whichever thread applied it; **(iii)** *S* ≥ 1,000,000 — no
  site-2 use; the commit-log walk ends at 2(*S* − 1) > *L* and is replaced. So at the defaults a write leaves at
  most about 1 MiB on at most two threads, and writes of 1,000,000 bytes or more leave nothing.
- **Heap mode** changes the resource, not the rule; the replaced heap buffer is garbage, not freed, so the
  live heap obeys the same bound while the allocation rate does not.
- **Unit tier note:** `DataOutputBuffer`'s statics are fixed at class initialization, so each value needs its
  own JVM; the test must not set the property in code.
