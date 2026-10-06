# column_index_cache_size — row index entry (IndexedEntry vs ShallowIndexedEntry)

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | COLUMN_INDEX_CACHE_SIZE-INDEXSAMPLES-CACHESIZETHRESHOLD |
| **Constraint** | `column_index_cache_size` — a **configuration entry** ([`Config.java:328`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L328), default `2KiB`, formerly `column_index_cache_size_in_kb`). Present and uncommented in the shipped [`conf/cassandra.yaml:1200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L1200). |
| **Enforcement pattern** | **(b)** at the primary site — the comparison returns a list-or-`null` that a separate decision point in another class reads. **One of the three check sites is (a)**; see the check-site table below and §11. |
| **Capacity check** | [`BigFormatPartitionWriter.indexSamples():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L113) — `indexSamplesSerializedSize + columnIndexCount * TypeSizes.sizeof(0) <= cacheSizeThreshold`. **Two further sites**, both on the same constraint: [`BigFormatPartitionWriter.addIndexBlock():171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L171) (same expression, `>`, switches the writer to byte-buffer mode) and [`RowIndexEntry$Serializer.deserialize():360`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L360) (`size <= DatabaseDescriptor.getColumnIndexCacheSize()`, on the **read** path). |
| **Decision point** | [`RowIndexEntry.create():227-238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L227-L238) — `indexSamples != null && indexSamples.size() > 1` selects `IndexedEntry`, otherwise `ShallowIndexedEntry`. For the read-path site the decision point is the `if` itself, [`RowIndexEntry.java:360-372`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L360-L372). |
| **Allocation site** | [`RowIndexEntry.create():228-230`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L228-L230) — `new IndexedEntry(..., indexSamples.toArray(new IndexInfo[indexSamples.size()]), ...)`, which retains the whole `IndexInfo[]` on heap. The disallow counterpart is [`:235-237`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L235-L237), `new ShallowIndexedEntry(...)`, which retains only a file position. Read-path counterparts: [`:362`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L362) and [`:369`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L369). |
| **Related cases** | none — first case in the `sstable_index` module and the first where **both** outcomes allocate an object (see §5). |

```java
// BigFormatPartitionWriter.indexSamples():111-118 — the capacity check (primary site).
// Neither arm allocates; the return value IS the verdict.
public List<IndexInfo> indexSamples()
{
    if (indexSamplesSerializedSize + columnIndexCount * TypeSizes.sizeof(0) <= cacheSizeThreshold)
    {
        return indexSamples;                      // <-- allow verdict, :115
    }

    return null;                                  // <-- disallow verdict, :117
}
```

```java
// RowIndexEntry.create():216-239 — the decision point. Reads the verdict; the two
// arms create different objects with very different heap footprints.
public static RowIndexEntry create(long dataFilePosition, long indexFilePosition,
                                   DeletionTime deletionTime, long headerLength, int columnIndexCount,
                                   int indexedPartSize,
                                   List<IndexInfo> indexSamples, int[] offsets,
                                   ISerializer<IndexInfo> idxInfoSerializer,
                                   Version version)
{
    if (indexSamples != null && indexSamples.size() > 1)
        return new IndexedEntry(dataFilePosition, deletionTime, headerLength,
                                indexSamples.toArray(new IndexInfo[indexSamples.size()]), offsets,
                                indexedPartSize, idxInfoSerializer, version);   // <-- ALLOW, :228
    if (columnIndexCount > 1)
        return new ShallowIndexedEntry(dataFilePosition, indexFilePosition,
                                       deletionTime, headerLength, columnIndexCount,
                                       indexedPartSize, idxInfoSerializer, version); // <-- DISALLOW, :235
    return new RowIndexEntry(dataFilePosition);   // <-- neither: single-block partition, :239
}
```

```java
// RowIndexEntry$Serializer.deserialize():360-372 — the third site, and the one that
// governs steady-state heap. This one IS pattern (a): the if branches straight to the
// two allocations.
if (size <= DatabaseDescriptor.getColumnIndexCacheSize())
{
    return new IndexedEntry(position, in, deletionTime, headerLength, columnsIndexCount,
                            idxInfoSerializer, indexedPartSize, version);
}
else
{
    in.skipBytes(indexedPartSize);
    return new ShallowIndexedEntry(position, indexFilePosition,
                                   deletionTime, headerLength, columnsIndexCount,
                                   indexedPartSize, idxInfoSerializer, version);
}
```

## 2. Context

When a Cassandra partition is large, the storage engine does not scan it from
the start on every read. It divides the partition into blocks and records,
for each block, where in the data file that block begins — a small index that
lives beside the partition. Reading one of these indexes from disk on every
lookup would be slow, so Cassandra would like to keep them in memory. But a
partition can have arbitrarily many blocks, so keeping every index in memory
is unbounded: a handful of very wide partitions could occupy an arbitrary
amount of heap.

This check is the bound on that. It compares the serialized size of one
partition's block index against a configured threshold, and the answer
decides **which of two representations** is built. Below the threshold, the
index is held in memory as an array of block descriptors, so lookups are
resolved without touching disk. Above it, only the partition's file position
is kept, and the block index is read back from disk whenever it is needed.
The constraint therefore does not refuse anything — nothing fails and nothing
blocks — it silently chooses the cheap-in-memory-expensive-on-disk
representation instead of the other way round. That makes the per-entry heap
cost bounded by the threshold rather than by the data.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `sstable_index` — on-disk index entries and the key cache that holds them (`io/sstable/format/big`, with the cache in `cache` and `service/CacheService`) |
| **One-line role** | The BIG SSTable format indexes wide partitions by block; `RowIndexEntry` is the in-memory handle to one partition's index, and the key cache keeps recently used handles on heap so reads can skip the primary index file. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes** — it compares the accumulated serialized size of one partition's `IndexInfo` samples against a configured byte threshold, and the outcome determines whether that data is retained on heap. |
| **Usage-side operand** | `indexSamplesSerializedSize + columnIndexCount * TypeSizes.sizeof(0)` — the running serialized size of the `IndexInfo` samples collected so far ([`:54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L54), accumulated at [`:170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L170)) plus 4 bytes per block for the offsets array. On the read-path site the operand is `size`, the serialized entry size read off the index file at [`:345`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L345). |
| **Limit-side operand** | `cacheSizeThreshold` — the final field at [`:65`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L65), assigned at [`:85`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L85). |
| **Limit type** | **Configuration entry**, used raw (converted KiB → bytes). |

**Limit initialization path.**

1. [`Config.column_index_cache_size:328`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L328) — declared, `volatile DataStorageSpec.IntKibibytesBound`, default `2KiB`.
2. [`DatabaseDescriptor.applyConfig()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L630) — `checkValidForByteConversion(conf.column_index_cache_size, "column_index_cache_size")` at startup.
3. [`DatabaseDescriptor.getColumnIndexCacheSize():2044-2047`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2044-L2047) — `conf.column_index_cache_size.toBytes()`.
4. [`BigFormatPartitionWriter`'s convenience constructor, `:73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L73) — read **once per partition writer** and passed into the full constructor, which stores it as `cacheSizeThreshold` at [`:85`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L85). The single production construction site is [`BigTableWriter.java:419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L419).
5. Read at the comparison, [`:113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L113) and [`:171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L171). The read-path site at [`RowIndexEntry.java:360`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L360) skips steps 4–5 and calls `DatabaseDescriptor.getColumnIndexCacheSize()` **live at every deserialization**.

**The two sites read the value at different times, and that matters.** The
config field is `volatile` and has a live JMX setter, so a runtime change
takes effect immediately on the read path but only for *newly constructed*
partition writers on the write path. §9 depends on this: changing the knob
without restarting changes what is deserialized from existing SSTables right
away, without rewriting a single byte.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`RowIndexEntry.create():227-238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L227-L238) |
| **Verdict** | Pattern (b): the verdict is the **return value of `indexSamples()`** — the `List<IndexInfo>` itself when the comparison holds, `null` when it does not. Set at [`BigFormatPartitionWriter.java:115`/`:117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L111-L118), passed by the caller at [`BigTableWriter.createRowIndexEntry():108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L108), and read at `RowIndexEntry.java:227`. |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `samplesSize <= cacheSizeThreshold` (and more than one block) | `new IndexedEntry(...)` holding `indexSamples.toArray(new IndexInfo[...])` — the full block index retained on heap. |
| **Disallow** | `samplesSize > cacheSizeThreshold` (and more than one block) | `new ShallowIndexedEntry(...)` — no `IndexInfo` array; only a file position, to be re-read from the index file on demand. |
| *(neither)* | one block or fewer | `new RowIndexEntry(dataFilePosition)` at [`:239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L239) — no index at all. Outside the check's reach. |

```java
// allow — the retained array is the resource
return new IndexedEntry(dataFilePosition, deletionTime, headerLength,
                        indexSamples.toArray(new IndexInfo[indexSamples.size()]), offsets,
                        indexedPartSize, idxInfoSerializer, version);
```

```java
// disallow — same partition, a constant-size handle instead
return new ShallowIndexedEntry(dataFilePosition, indexFilePosition,
                               deletionTime, headerLength, columnIndexCount,
                               indexedPartSize, idxInfoSerializer, version);
```

### Both outcomes allocate — Rule 3 is satisfied on *size*, not on existence

Every other case in this folder has a disallow branch that creates nothing:
it blocks, throws, or returns `null`. Here **both** branches create an object,
and the divergence is in what that object retains. Rule 3 asks whether the
branches diverge on memory-significant object creation, and they do — the
classes' own heap accounting says so directly:

| | `IndexedEntry` | `ShallowIndexedEntry` |
|---|---|---|
| `unsharedHeapSize()` | `BASE_SIZE + Σ idx.unsharedHeapSize() + sizeOfReferenceArray(columnsIndex.length)` ([`:613-620`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L613-L620)) | `BASE_SIZE` ([`:767-770`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L767-L770)) |
| Grows with partition width? | **yes**, linearly in block count | **no**, constant |
| Index lookup | in memory | re-read from the index file |

That `unsharedHeapSize()` is not decorative: it is the **key cache weigher**
([`CaffeineCache.create():61-70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/CaffeineCache.java#L61-L70)),
so the two outcomes are charged differently against the cache's byte budget.
See §8 — this is what makes the constraint's effect on the ceiling indirect.

### The write-path pair are one mechanism, not two checks

[`:171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L171)
is the same expression with the comparison inverted. As blocks accumulate,
the first time the running size crosses the threshold the writer allocates a
`DataOutputBuffer` ([`reuseOrAllocateBuffer():193-205`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L193-L205),
sized `cacheSizeThreshold * 2`), serializes the samples collected so far into
it, and stops adding to the `indexSamples` list. By the time `indexSamples()`
is called at the end of the partition, the two sites necessarily agree. `:113`
is filed as the primary site because it is the one whose value reaches the
decision point; `:171` is the same threshold enforced eagerly, and is listed
in §1 rather than filed separately (README §6.1, "one case, several check
sites").

## 6. Code path

### 6a. Allow path → object creation

1. [`BigFormatPartitionWriter.addIndexBlock():128-190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L128-L190) — called once per index block as the partition is written; [`:170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L170) accumulates `indexSamplesSerializedSize`, and [`:181`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L181) appends to `indexSamples` while the threshold at `:171` is not crossed.
2. [`BigTableWriter.createRowIndexEntry():96-111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L96-L111) — end of partition; calls `partitionWriter.indexSamples()` at [`:108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L108).
3. [`BigFormatPartitionWriter.indexSamples():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L113) — comparison holds; returns the list.
4. [`RowIndexEntry.create():227`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L227) — `indexSamples != null && size() > 1`.
5. [`:228-230`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L228-L230) — **object creation**: `new IndexedEntry(...)` with `indexSamples.toArray(new IndexInfo[indexSamples.size()])`. The array and every `IndexInfo` in it are now retained by the entry.
6. [`BigTableWriter.java:113-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L113-L125) — the entry is appended to the index writer and, if key-cache migration applies, put into `cachedKeys`, from where it reaches the key cache and is charged its `unsharedHeapSize()`.

**Read path (third site), which is where the steady-state heap actually comes from:**

1. [`RowIndexEntry$Serializer.deserialize():341-374`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L341-L374) — called when a read resolves a partition through the primary index.
2. [`:360`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L360) — `size <= getColumnIndexCacheSize()` read **live** from config.
3. [`:362`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L362) — **object creation**: `new IndexedEntry(position, in, ...)`, deserializing the whole `IndexInfo` array onto heap. The entry is then eligible for the key cache.

### 6b. Disallow path effect

**Not a rejection — a representation switch, and the work is displaced, not refused.**

1. [`indexSamples():117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L117) — returns `null`. Nothing is logged, no counter moves, no exception. The partition is written normally; only the in-memory handle differs.
2. [`RowIndexEntry.create():234-237`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L234-L237) — `new ShallowIndexedEntry(...)`, constant heap size.
3. On the read path, [`:367`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L367) `in.skipBytes(indexedPartSize)` — the index bytes are read past rather than materialized.
4. **The cost reappears as I/O.** A `ShallowIndexedEntry` resolves a block lookup by opening a reader on the index file ([`:754-764`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L754-L764)), so the disallow outcome trades heap for disk reads on every access. This is the closest thing this case has to a "disallow effect": there is nothing to count as a rejection, and the only externally visible consequence is more index-file reads.

**No escape hatch, and no way to switch the check off.** Unlike the compaction
disk guard, there is no flag that skips the comparison — the only way to make
every entry take the allow branch is to raise the threshold above every
partition's index size. The nearest thing to a bypass is a *format* choice:
the check is specific to the BIG SSTable format (`RowIndexEntry` lives under
`format/big`, and the yaml comment says "only relevant to SSTable formats that
use key cache, e.g. BIG"), so a table on the BTI format does not go through it
at all.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `IndexedEntry` (allow) or `ShallowIndexedEntry` (disallow), both nested in [`RowIndexEntry`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L484) / [`:671`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L671). The memory-significant part of the allow object is the `IndexInfo[] columnsIndex`. |
| **Resource consumed** | **On-heap bytes**, charged explicitly: `unsharedHeapSize()` is the key cache's weigher, so these objects are metered against `key_cache_size`. |
| **Rough sizing** | Allow: `BASE_SIZE + Σ IndexInfo.unsharedHeapSize() + sizeOfReferenceArray(n)` for `n` blocks. Bounded above by the check at roughly `cacheSizeThreshold` worth of *serialized* index, whose heap expansion is larger (each `IndexInfo` carries two `Clustering` objects and a `DeletionTime`; see the overhead calculation at [`:414-416`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L414-L416)). Disallow: `BASE_SIZE`, constant. Also transient during writing: the `indexSamples` `ArrayList` and, once the threshold is crossed, a `DataOutputBuffer` of `cacheSizeThreshold * 2` bytes ([`:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L204)). |
| **Lifetime / release** | Write-path entries are short-lived unless they enter the key cache. Cached entries live until evicted by the key cache's own byte budget (`key_cache_size`, [`CacheService.initKeyCache():119-135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java#L119-L135)) or the SSTable is dropped. |

## 8. Maximum memory bound

`column_index_cache_size` bounds the heap cost of **one** row index entry. Its
effect on the node's ceiling is therefore real but indirect, and stating it
carelessly would overclaim:

- **Direct effect — per entry.** Raising the threshold raises the largest
  block index that may be held on heap; lowering it forces wider partitions
  onto the shallow representation. At `0`, every multi-block partition becomes
  a `ShallowIndexedEntry` and per-entry heap is constant. There is no upper
  bound in the other direction beyond the config type's own range: a very
  large value lets an arbitrarily wide partition's whole index be resident.
- **Indirect effect — the total is capped elsewhere.** Cached entries are
  charged their `unsharedHeapSize()` against the key cache's byte capacity, so
  raising this threshold does **not** raise total key-cache heap. It changes
  the *mix*: fewer, fatter entries rather than more, thinner ones. Expect
  `KeyCache.Size` to stay near capacity either way while `KeyCache.Entries`
  falls as the threshold rises. This is the single most important thing to
  know before designing an experiment on it (§9a, "Why the entry class and not the node's heap").
- **Where it does move the ceiling.** Outside the key cache — entries held
  transiently during flush and compaction, and the `DataOutputBuffer` of
  `cacheSizeThreshold * 2` allocated per partition writer once the threshold
  is crossed. Both scale with the threshold and are **not** charged against
  any cache budget. With `C` concurrent writers (flush + compaction threads),
  the buffer term alone is up to `C × 2 × column_index_cache_size`.
- **Mechanism.** Not refusal: the constraint selects a representation. Heap is
  bounded because the expensive representation is only chosen for data small
  enough to make it cheap.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test sets `column_index_cache_size` live, reads partitions whose block indexes are
of known sizes, and checks that each entry is built as the array (`IndexedEntry`) or the
file position (`ShallowIndexedEntry`) exactly where the threshold falls, and what that
does to the key cache and the heap. **Run so far:** none. Converted to this layout
2026-10-06.

### 9a. Procedure and conclusions

**Testability:** config, **live-settable** — the `Config` field is `volatile`; the JMX
operation `StorageService.setColumnIndexCacheSizeInKiB(int)` (**KiB**, no `nodetool`
subcommand; `SetColumnIndexSize` in `nodetool` is the different knob `column_index_size`)
takes effect on the **read** path at the next deserialization, and on the **write** path
only for partition writers built afterwards (§4). One node lifetime runs the whole sweep.

**Claim under test:** `column_index_cache_size` selects, per partition, which object holds
its block index: when the serialized index (plus 4 bytes per block) is at most the
threshold the entry is an `IndexedEntry` retaining an `IndexInfo[]` on the heap, otherwise a
`ShallowIndexedEntry` retaining a file position; nothing is rejected, the cost reappears as
index-file reads. The ceiling is per entry (cached entries are charged their
`unsharedHeapSize()` against `key_cache_size`), so the node-wide effect is indirect (§8).

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** the entry class flips at the threshold, the flip changes the retained
  bytes by the `IndexInfo[]`, and the key cache re-caps the total.
- **Test:** four partition classes with block indexes of about 1, 8, 64 and 512 KiB, read
  at thresholds of 0, 2, 16 and 256 KiB, with the key cache small and fixed; read the class
  of each cached entry (heap histogram), the key cache's `Entries` and `Size`, and the
  index-file reads.
- **Logic:** (1) each class's index size must sit where intended against the thresholds, or
  the run is invalid. (2) At each threshold, the classes whose index is at most it are
  `IndexedEntry` and the others `ShallowIndexedEntry`: the decision **stops the retained
  bytes at the threshold** per entry. (3) The number of `IndexedEntry` instances follows
  the threshold: usage **follows the constraint**. (4) The flip is the only difference
  between the arms; the read-path site follows a live change with no rewrite. (5) `Entries`
  rises as `Size` falls when entries go shallow, and `Size` stays near the cache capacity
  when they are indexed and demand exceeds it (§8's re-cap).
- **Refuted if:** the entry class does not change where the threshold crosses the
  index size; or the cached weights do not differ as the two `unsharedHeapSize()`
  implementations say (rows of the Conclusions table). A flat node heap does not refute it
  (§8).

**Procedure:**

1. **Unit tier** — (a) run upstream `RowIndexEntryTest` (the two ends of the sweep,
   thresholds 99999 and 0). (b) Run the harness test `ColumnIndexThresholdTest` (9c): the
   write-path entry and the read-path entry at thresholds of 0, 2, 16 and 256 KiB and at
   the boundary, with asserted classes and `unsharedHeapSize()`.
2. **Cluster tier** — one node, BIG format, four partition classes loaded once; the
   threshold changed over JMX between reads, no restart.
3. **At each value:** idle control → **A**, a class whose index is **below** the threshold
   → **B**, a class **above** it. No scenario C: no bypass is recorded (the check cannot be
   switched off; a table on BTI never reaches it, which is a setup condition here).
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *T* = the threshold in bytes; for a partition with *n* blocks,
`S(n)` = `indexSamplesSerializedSize + 4 n` (the check's operand, §4); the classes C1 to C4
have `S` ≈ 1, 8, 64 and 512 KiB (to be measured at step 1; see 9c); an entry is indexed iff
`S(n) ≤ T`, and `n > 1`.

- **Class by threshold:** at *T* = 0: C1–C4 shallow. At 2 KiB: C1 indexed, C2–C4 shallow.
  At 16 KiB: C1, C2 indexed. At 256 KiB: C1–C3 indexed, C4 shallow (C4 is never indexed
  at any tested value: the never-allow control).
- **Entry weights:** `IndexedEntry.unsharedHeapSize()` grows linearly with *n* (about
  a few hundred bytes per block); `ShallowIndexedEntry.unsharedHeapSize()` is the constant
  `BASE_SIZE`, independent of *n*.
- **Key cache, per class read in full (cache capacity `K` = 8 MiB, enough partitions that the
  indexed weights exceed `K`):** indexed: `Size` ≈ `K` (the weigher caps it) and `Entries`
  low; shallow: `Size` well below `K`, `Entries` = the partitions read. So across the
  sweep for a class, `Entries` falls and `Size` rises as it goes from shallow to indexed.
- **Heap histogram:** instances of `RowIndexEntry$IndexedEntry` and `IndexInfo` appear
  for the indexed classes and not for the shallow ones; instances of
  `RowIndexEntry$ShallowIndexedEntry` appear for the shallow ones.
- **Live read path:** after the threshold is lowered over JMX **without** rewriting
  anything, re-reading the same SSTables yields shallow entries for the classes now above
  it; no new SSTable is written.
- **Total heap** barely moves across the sweep once the key cache is warm (the cache
  re-caps it), moving only by the uncapped terms (the per-writer `DataOutputBuffer` of
  `2 T`, transient flush entries).

**Conclusions:**

| Result | Conclusion |
|---|---|
| Entry class follows `S ≤ T` for every class and threshold (unit and cluster); `unsharedHeapSize()` is linear in *n* for indexed and constant for shallow; `Entries` and `Size` move as predicted; the live JMX change re-flips read-path entries with no rewrite | **Confirmed** — the check selects the representation as traced; the node-wide ceiling is re-capped by the key cache (§8). |
| Entry class follows the threshold, but `Size` does not stay near `K` for indexed entries with demand above `K` | **Refuted** for §8's re-cap — the weigher is not applied as §5 says; chase it. |
| Entry class does not change at the predicted *T* for any class | **Refuted** — the same representation is produced either side; or the table is not on BIG or the partitions are single-block (`:239`): check those first (they make it an **Invalid run**). |
| Read-path entries follow a live change but write-path entries (new SSTables) lag it | **Confirmed, as §4 says** — the write path reads the value at writer construction; record the lag (not a refutation). |
| Entry class follows the threshold but `Entries` does not rise when shallow | **Not confirmed** — the cache budget is not the binding term (the shallow weights are too small to matter, or `key_cache_size` is too large); lower `K` and re-run. |
| Total node heap is flat across the sweep | **Expected, not a refutation** (§8). Report it as the key cache's budget. |
| Index-file reads do not rise when entries go shallow | **Not confirmed** — §6b's displaced cost is not shown; read the reader metrics before concluding. |
| `S` of the classes is not within a factor of 2 of 1, 8, 64, 512 KiB, or `tablestats` shows another SSTable format | **Invalid run** — rebuild the dataset (9c) or fix the format (9b). |

**Why the entry class and not the node's heap:** the node's heap is dominated by other
things and the key cache re-caps the total, so it can stay flat for reasons unrelated to
this check; only the class of each entry, which the comparison alone decides, ties a
reading to it.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `column_index_cache_size` in `cassandra.yaml` ([shipped at `conf/cassandra.yaml:1200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L1200), default `2KiB`). Live: `bin/nodetool sjk mx -ms -b 'org.apache.cassandra.db:type=StorageService' -f ColumnIndexCacheSizeInKiB -v <KiB>` (`StorageServiceMBean.setColumnIndexCacheSizeInKiB(int)`; **KiB**). Unit tier: `DatabaseDescriptor.setColumnIndexCacheSize(int kib)` ([`:2054-2057`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2054-L2057)). |
| **Confirm it took effect** | `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.db:type=StorageService' -f ColumnIndexCacheSizeInKiB` after every change; the unit test asserts `DatabaseDescriptor.getColumnIndexCacheSize()` in bytes. |
| **Capacity values** | `0KiB`, `2KiB` (default), `16KiB`, `256KiB`, plus the boundary pair around one class's `S` (9e). |
| **Scope** | **Per row-index entry** (per partition per SSTable). The node-wide effect is capped by `key_cache_size`; the uncapped terms are the per-writer `DataOutputBuffer` of `2 T` and transient flush entries (§8). |
| **Level** | Both. Unit: upstream `RowIndexEntryTest` (`Assume.assumeTrue(BigFormat.isSelected())`), `KeyCacheTest`; harness `ColumnIndexThresholdTest`. Cluster: the key cache and the heap histogram. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| SSTable format | BIG (`sstable.selected_format` default) | The check is not reached on BTI; confirm with `bin/nodetool tablestats` / the file names (`nb-…-big-Data.db`). |
| `column_index_size` | `4KiB` | Block granularity sets the block count, hence `S`: with 1 KiB rows it makes about 4 rows a block, so `S` ≈ 8 bytes a row (an estimate). Set it before loading; it is also `volatile`, so do not change it afterwards. |
| `key_cache_size` | `8MiB` (`K`) | Small, so the indexed classes exceed it and the re-cap shows; the default (5 % of heap, at most 100 MiB) would hide it. |
| `-Xms4G -Xmx4G` | fixed | Heap readings are compared across values. |
| Table `ks1.t`, autocompaction | `(pk bigint, ck bigint, v blob, PRIMARY KEY (pk, ck))`, `'enabled': 'false'` | A compaction or flush rewrites entries with the *then-current* write-path threshold and mixes the arms. |
| Payload | 1 KiB random blob per row | Fixed, so block counts are known from row counts. |
| `row_cache_size` | `0` (default) | Row cache would answer reads without the index. |

**Controls:**

- **Idle run** — data loaded, no reads: the heap and key-cache floors.
- **Key-cache-off arm** — `nodetool setcachecapacity 0 0 0` at one threshold: the capping removed (the cross-check of §8).
- **Read-before-write check** — one threshold change over JMX followed by re-reading the same SSTables, without any flush: shows the live read path.

**Reset between runs:** to repeat an arm: `bin/nodetool invalidatekeycache`, then the same reads; do not restart (the key cache is saved and restored across restarts by `AutoSavingCache`). A new sweep: `invalidatekeycache`, set the next value, read.

### 9c. Workload

The usage operand is one partition's serialized block index, which grows with the
partition's width. Load four classes of partitions once, then read each class at each
threshold.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/column_index_cache_size-indexSamples-cacheSizeThreshold`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `ColumnIndexThresholdTest.java` | Unit tier. Package `org.apache.cassandra.io.sstable.format.big`; modelled on `RowIndexEntryTest.DoubleSerializer` (which writes 100 KiB of fake bytes per row so each row becomes an `IndexInfo`); see 9e. |
| `load-classes.sh` | Cluster tier. Loads the four classes (below) with a small CQL client or `cassandra-stress` user profile, flushes after each class, and prints `tablestats` and the table's `du -sb`. |
| `read-class.sh` | Cluster tier. For one class, issues one point read per partition at a mid-range `ck`, with one pass, and prints the elapsed time. |
| `entry-census.sh` | Cluster tier. `jcmd <pid> GC.class_histogram`, filtered to `RowIndexEntry$IndexedEntry`, `RowIndexEntry$ShallowIndexedEntry` and `IndexInfo`, with a timestamp. |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.io.sstable.format.big.RowIndexEntryTest
cp <harness>/ColumnIndexThresholdTest.java test/unit/org/apache/cassandra/io/sstable/format/big/
ant testsome -Dtest.name=org.apache.cassandra.io.sstable.format.big.ColumnIndexThresholdTest

# cluster tier: schema once, load once, then per threshold
bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE ks1.t (pk bigint, ck bigint, v blob, PRIMARY KEY (pk, ck)) WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};"
<harness>/load-classes.sh
bin/nodetool sjk mx -ms -b 'org.apache.cassandra.db:type=StorageService' -f ColumnIndexCacheSizeInKiB -v <KiB>
bin/nodetool invalidatekeycache
<harness>/read-class.sh <C1|C2|C3|C4>; <harness>/entry-census.sh
```

**Starting values.** Estimates, not measurements:

| Class | Partitions × rows | Partition size | `S` (estimate, ≈ 8 B per row) |
|---|---|---|---|
| C1 | 2,000 × 120 | 120 KiB | ≈ 1 KiB |
| C2 | 500 × 1,000 | 1 MiB | ≈ 8 KiB |
| C3 | 100 × 8,000 | 8 MiB | ≈ 64 KiB |
| C4 | 16 × 64,000 | 64 MiB | ≈ 512 KiB |

About 2.5 GB in all. **Step 1 measures `S` per class** (the unit test prints `S(n)` for the same row shape; the cluster tier cross-checks it from the key cache `Size` of one class read at `0` against a very large value, the difference being that class's `IndexInfo` cost, as the case's single-shot form says), and the thresholds are then kept as 0, 2, 16, 256 KiB with the classes' row counts rescaled if an `S` is outside a factor of 2 of its target.

**If the classes straddle the thresholds poorly** (for example C2's `S` above 16 KiB): scale its row count by the ratio and rebuild that class only; record it.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — `S`, the index size per partition | Unit: `partitionWriter.indexInfoSerializedSize()` and `getColumnIndexCount()` (the check's operands, [`BigFormatPartitionWriter.java:113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L113)). Cluster: not exposed (no log line, no gauge); `KeyCache.Size` at `0` against a large value for one class read in full, divided by the entries. | Step 1, and when a class is rebuilt | The cluster figure is the weight, not the serialized size; the unit test gives the exact `S`. |
| **Disallow evidence** — the entry class | `entry-census.sh`: counts and bytes of `RowIndexEntry$IndexedEntry`, `RowIndexEntry$ShallowIndexedEntry`, `IndexInfo` after a read pass; unit: `entry instanceof IndexedEntry`. | After each read pass | `GC.class_histogram` forces a full collection and is the only direct census: take it after the pass, before the cache is invalidated. The disallow path logs nothing and no counter moves (§6b): do not wait for one. |
| **Key cache** | `org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=Entries` and `…name=Size` and `…name=Capacity` ([`CacheMetrics.java:69-71`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/CacheMetrics.java#L69-L71)); `bin/nodetool sjk mx -mg -b '<name>' -f Value`. | Before and after each read pass | `Size` is the weighted size (the weigher is the entries' `unsharedHeapSize()`, §5); `invalidatekeycache` first, or the previous threshold's entries remain. The cache is also filled by flushes and compactions: autocompaction is off. |
| **Displaced cost** — index-file reads | The elapsed time of `read-class.sh`; the table's index-file reader activity (`nodetool tablestats` local read latency, or `iostat`) for the shallow arms. | Per read pass | Page cache hides the extra reads on a small dataset; compare shallow and indexed passes on the same class and take the ratio, and read `iostat` for the device. |
| **Real resource** — heap | `jcmd <pid> GC.run` then `jcmd <pid> GC.heap_info` (the census already forces a collection); the heap after the pass minus the idle floor and the young generation (as the memtable cases do). | Idle control; after each pass | Flat across the sweep is expected (§8). Never use RSS. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Record pass or fail and the asserted values.

1. Run `RowIndexEntryTest` (upstream). Record pass or fail.
2. Run `ColumnIndexThresholdTest`. With the 100 KiB-per-row builder of
   `RowIndexEntryTest.DoubleSerializer` (one `IndexInfo` per row), for *n* in 2, 10, 34, 270
   and 2,200 rows and for each threshold in 0, 2, 16 and 256 KiB:
   1. builds the partition and prints `S(n)` (`indexInfoSerializedSize() + 4 n`);
   2. asserts the write-path entry from `RowIndexEntry.create(...)` is an `IndexedEntry` iff
      `S(n) ≤ T` and `n > 1`, else a `ShallowIndexedEntry`;
   3. serializes it and deserializes it at **each** of the four thresholds (a live change):
      asserts the class of the deserialized entry follows `size ≤ getColumnIndexCacheSize()`
      ([`RowIndexEntry.java:360`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L360)) whatever the write-time threshold was;
   4. asserts `unsharedHeapSize()`: for `IndexedEntry` linear in *n*, for `ShallowIndexedEntry`
      equal to the same constant for every *n*;
   5. at the boundary: finds the *n* where `S(n)` crosses 2 KiB (the threshold's unit is KiB, so
      the boundary is on the 2,048-byte line) and asserts the class flips between *n* and *n* + 1.

   Record pass or fail and, per row, the printed `S(n)`, class and `unsharedHeapSize()`.

**Before the cluster tier.**

1. **Dataset check.** `tablestats` shows the table on BIG and the four classes' SSTables; step 1's `S` per class is within a factor of 2 of its target (9c).
2. **Instrument check.** Read one C1 partition at `2KiB`, run `entry-census.sh`: it must show at least one `IndexedEntry` and non-zero `IndexInfo` bytes; then lower the threshold to `0` without a flush, `invalidatekeycache`, read again: `ShallowIndexedEntry` instead. A census that never shows either stops the run.

**Cluster tier, for each threshold:**

1. **Control run** — with the data loaded and autocompaction off, take the idle heap and key-cache readings and a census.
2. **Scenario A (a class with `S ≤ T`)** — set the threshold, `invalidatekeycache`, read that class once through, record `Entries`, `Size`, the census, the elapsed time, and the heap.
3. **Scenario B (a class with `S > T`)** — the same for a class above the threshold; also the C4 class at every value (never indexed).
4. **Live-flip check** — at `256KiB` read C3 (indexed), then lower to `16KiB` **without** a flush or restart, `invalidatekeycache`, read C3 again: the entries are now shallow with no new SSTable (`ls` shows no new `*-Data.db`).
5. **Key-cache-off arm** — at `256KiB`, `nodetool setcachecapacity 0 0 0`, read C3, take the heap: the retained bytes then track the entries without the cache's cap (restore the capacity afterwards).

Stop when each scenario's records are taken; a run where the classes do not straddle the thresholds is invalid (9a).

**Record for stage 4:** the `cassandra.yaml` diff (`column_index_size`, `key_cache_size`) and JVM options in force, the exact commands and thresholds, each class's `S`, the census, the key-cache readings, the elapsed times and the heap readings, per threshold and class.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — found 2026-09-22 by the capacity-word pass reading the source directly. Judged as a qualifying pattern-(b) candidate and parked in `deferred.md` §1c ("strong") under the then-current (a)-only scope; unparked 2026-09-25; written up 2026-09-28. |
| **Filed by / Date** | Claude (`claude-opus-5`) session, 2026-09-28 |
| **Line numbers checked** | 2026-09-28 against the local `cassandra-5.0.9` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). All line numbers carried from `deferred.md` §1c (`:113`, `:171`, `:227`) confirmed unchanged. |
| **Escape hatch / Target-3 note** | **No flag-style escape hatch** — the check cannot be switched off, only moved. Two adjacent observations for Target 3: (1) the constraint is **format-scoped**, so a table on the BTI format bypasses it entirely; (2) the read-path site reads the config **live per deserialization**, so a JMX change takes effect on already-written SSTables with no rewrite — an unusually cheap way to change a memory characteristic at runtime, in either direction. |
| **Stage-4 feedback** | none yet. **§9 converted to the new layout 2026-10-06** (9a to 9e) from the old §9; not yet audited (stage-4 README, step 0) and not yet run. The new §9 lists its harness as work for step 1. |
| **Notes** | The third check site (`RowIndexEntry.java:360`) was **not** recorded in `deferred.md` §1c, which listed only the two write-path sites. It is the site that governs steady-state heap, and it is pattern (a) rather than (b). Found while tracing the decision point for this write-up. |

---

## 11. Notes

- **Why `indexSamples` is the primary site although `:360` is the cleaner
  check.** The naming rule takes the primary *check site*, and the three sites
  are not equal in kind: `:113` and `:171` decide what is *written* into the
  entry's representation, and `:360` decides how an already-written entry is
  *loaded*. The write-path site is the origin of the constraint's effect and
  is the row that was queued in `deferred.md`, so it names the case. But for
  anyone reading this case to understand the memory behaviour, `:360` is the
  site that matters, and §9 is designed around it. If a later pass prefers to
  split them, the natural split is by path (write vs read), not by class.

- **This case's pattern is mixed, which the format does not have a field
  for.** §1 records (b) because that is the primary site. The read-path site
  is unambiguously (a). Recorded here rather than forcing a single label;
  worth watching whether other multi-site cases hit the same thing.

- **First case where the disallow branch allocates.** Every previously filed
  case has a disallow branch that blocks, throws, or returns nothing, so
  "diverge on object creation" has so far meant "one branch creates, the other
  does not". Here both create, and the divergence is in retained size. Rule 3
  is satisfied either way — it asks whether the branches diverge on
  memory-significant object creation, not whether one branch creates nothing —
  but it is the first case that tests the distinction, and the band-A pass
  should expect more of this shape (representation switches, not rejections).

- **The `DataOutputBuffer` sized `cacheSizeThreshold * 2`**
  ([`:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L204))
  is a second, smaller allocation gated by the same constant, on the
  *disallow* side. It is noted in §7/§8 rather than filed as its own case:
  same constraint, same method, and it is a consequence of crossing the
  threshold rather than a separate decision.
