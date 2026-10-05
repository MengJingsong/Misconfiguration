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
  know before designing an experiment on it (§9f).
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

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable, and hot-settable** — the field is `volatile` with a JMX setter, and the read-path site reads it live at every deserialization. This is the easiest case in the folder to sweep: no restart, no rebuild, no cluster strictly required. |
| **Constraint knob** | `column_index_cache_size` in `cassandra.yaml` ([shipped at line 1200](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L1200), default `2KiB`). At runtime: JMX `StorageServiceMBean.setColumnIndexCacheSizeInKiB(int)` ([`StorageService.java:6815-6826`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L6815-L6826)); the older `setColumnIndexCacheSize` is deprecated in 5.0 but still present. In a unit test: `DatabaseDescriptor.setColumnIndexCacheSize(int kib)` ([`DatabaseDescriptor.java:2054-2057`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2054-L2057)). **No `nodetool` subcommand** — `tools/nodetool/` has `SetColumnIndexSize`, which is the *different* knob `column_index_size`; JMX directly is required. |
| **Capacity values to test** | `column_index_cache_size` ∈ {`0KiB`, **`2KiB`** (default), `16KiB`, `256KiB`}. Four values spanning three decades, because the interesting transition is where it crosses a typical partition's index size, and that size is workload-dependent. `0KiB` is the degenerate control: every multi-block partition must go shallow. |
| **Usage-side observable** | `indexSamplesSerializedSize + columnIndexCount * 4` on the write path; `size` on the read path. **What stage 4 can actually see is the outcome, not the operand**: the ratio of `IndexedEntry` to `ShallowIndexedEntry`. |
| **Instrument** | **The operand is not exposed and there is no log line** — unlike the compaction case, neither site logs anything (checked 2026-09-28). Measure the *effect* instead, via three instruments: (1) **`KeyCache.Entries` and `KeyCache.Size`** gauges ([`CacheMetrics.java:69-71`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/CacheMetrics.java#L69-L71), over JMX or `nodetool info`) — at a fixed workload and fixed `key_cache_size`, `Entries` falling as the threshold rises is the signature of more partitions taking the allow branch; (2) **heap after a forced full GC** (`jcmd <pid> GC.heap_info`) for the absolute figure; (3) at the unit tier, call `unsharedHeapSize()` on the constructed entry directly and assert its class — this measures the operand's consequence exactly and is the only tier that can do so. |
| **Scope of the limit** | **Per row index entry** — i.e. per partition, per SSTable. Node-wide effect is `threshold × N` where `N` is the number of resident entries, but `N` is not free: the key cache caps the product (§8). For the uncapped terms, the multiplier is the number of concurrent partition writers `C` for the `2 × threshold` buffer. Hold `key_cache_size`, `column_index_size` (block granularity, default **64KiB** for BIG via [`BigFormatPartitionWriter.DEFAULT_GRANULARITY:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L49)) and the partition width fixed across the sweep — all three move the same observable. |
| **Suggested level** | **Unit first — scaffolding exists and already sweeps this exact knob.** [`test/unit/org/apache/cassandra/io/sstable/format/big/RowIndexEntryTest.java:106-118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/format/big/RowIndexEntryTest.java#L106-L118) has `testC11206AgainstPreviousArray` (`setColumnIndexCacheSize(99999)`) and `testC11206AgainstPreviousShallow` (`setColumnIndexCacheSize(0)`) — the two ends of the sweep, already written, differing only in this knob. Extend that pattern to assert the entry's **class and `unsharedHeapSize()`** at each of the four values. Also relevant: `test/unit/org/apache/cassandra/io/sstable/keycache/KeyCacheTest.java` and `test/unit/org/apache/cassandra/cql3/KeyCacheCqlTest.java`. Run: `ant testsome -Dtest.name=org.apache.cassandra.io.sstable.format.big.RowIndexEntryTest`. Then the cluster tier for the heap figure. |

### 9a. Workload — driving the usage operand

The usage operand is **one partition's serialized block index**, which grows
with partition width. So the workload is: build partitions wide enough that
their index crosses the threshold, and read them.

- Single node. `CREATE TABLE ... (pk bigint, ck bigint, v blob, PRIMARY KEY (pk, ck))`, **BIG format explicitly** (`sstable_format`/table option) — the check does not exist for BTI.
- Write a small number of **very wide** partitions: a few hundred MiB across a handful of `pk` values, so each partition spans many 64KiB blocks and its index is kilobytes. `cassandra-stress` with a narrow partition-key distribution, or a small CQL client with an exact row count, which is preferable here because the index size must be predictable.
- `nodetool flush`, then `nodetool invalidatekeycache` before each measurement so the cache refills under the threshold being tested.
- Read the partitions back (point reads on `pk` with a mid-range `ck`) to force `deserialize()` and populate the key cache.

**Deterministic single-shot form:** rather than sweeping until something
changes, compute one partition's index size first — write it, then read
`KeyCache.Size / Entries` at `column_index_cache_size = 0` versus a very large
value; the difference is that partition's `IndexInfo` array cost. Then set the
threshold just above and just below that figure. The transition is then a step
at a known point, not a search.

### 9b. Scenario A — just reach capacity

Set the threshold **just above** the measured index size of the test
partitions, invalidate the key cache, and read them.

Expect at each value: entries deserialize as `IndexedEntry`; `KeyCache.Size`
per entry is high and `KeyCache.Entries` correspondingly low for a fixed
`key_cache_size`; index-file reads after the first are avoided. At the unit
tier, assert `entry instanceof IndexedEntry` and that `unsharedHeapSize()`
scales with block count.

### 9c. Scenario B — try to exceed capacity

Set the threshold **just below** the same index size, invalidate the key
cache, read again. **Nothing is rejected** — §6b — so the expected
observations are all indirect:

| Expected | Why, from §6b |
|---|---|
| Entries deserialize as `ShallowIndexedEntry`; `unsharedHeapSize()` constant | `:367-372` skips the index bytes |
| `KeyCache.Entries` rises at constant `KeyCache.Size` | each entry is cheaper, so more fit in the same budget |
| More index-file reads per query; read latency for these partitions rises | the block index is re-read on each access |
| **No** error, log line, exception or counter | the disallow path is silent |

The absence of any rejection signal is the defining feature of this case, and
stage 4 should not wait for one.

### 9d. Expected dose-response

If the traced path is the binding limit, across `0KiB → 2KiB → 16KiB → 256KiB`
at a **fixed** workload, fixed `key_cache_size` and fixed partition width:

- **A step, not a ramp.** The `IndexedEntry` fraction goes from 0 to 1 as the
  threshold crosses the partitions' index size. With uniform partitions the
  transition is sharp; with a spread of widths it smears into an S-curve whose
  shape is the partition-width distribution. Either is consistent with the
  case; a *linear* response is not.
- **`KeyCache.Entries` falls as the threshold rises**, while `KeyCache.Size`
  stays pinned near `key_cache_size`. This is the key prediction, and it is
  the opposite direction to a naive "bigger limit = more memory" expectation.
- **Total heap is roughly flat** across the sweep once the key cache is warm,
  moving only by the uncapped terms in §8 (per-writer buffers, transient
  flush/compaction entries).
- **Cross-check:** with the key cache disabled (`key_cache_size: 0`), heap
  attributable to these entries should track the threshold much more directly,
  because the capping mechanism is removed. If it does not, the §8 reading is
  wrong.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| Entry class flips to `ShallowIndexedEntry` at the predicted threshold; `KeyCache.Entries` rises; index-file reads rise | The check enforces as traced. |
| Entry class never changes at any threshold | Either the table is not on the BIG format (the check does not exist for BTI — verify first), or partitions are single-block and hit [`:239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L239) instead. Fix the workload, not the case. |
| Entry class flips as predicted but total heap is unchanged | **Expected, not a refutation** — see §8 and §9f. The key cache caps the total; report it and move on. |
| `KeyCache.Size` grows past `key_cache_size` as the threshold rises | The weigher is not being applied as §5 claims. That *would* refute part of §8, and is worth chasing. |

### 9f. What would refute this case

The case claims the comparison at `:113`/`:360` **determines which of two
objects is created**, and that the chosen object's heap cost differs by the
retained `IndexInfo[]`. It is refuted if, across the threshold sweep with the
partition index size held fixed and known, the created entry's class does not
change at the predicted point — i.e. the same representation is produced on
both sides of the threshold.

**What would *not* refute it, and must be said plainly:** finding that total
node heap barely moves across the sweep. §8 predicts exactly that, because the
key cache re-caps the total. A stage-4 run that concludes "the constraint does
not limit memory" from a flat heap curve has measured the key cache's budget,
not this check. The falsifiable claim is about **per-entry** cost and **entry
class**, which is why the unit tier — where both are directly observable — is
the primary tier for this case rather than a supplement.

### 9g. Confounders and controls

- **`key_cache_size` is the dominant confounder** (§8). Hold it fixed across
  the sweep, and run one arm with it set to `0` as the control that separates
  the per-entry effect from the cache's capping.
- **`column_index_size` (block granularity, default 64KiB for BIG)** sets how
  many blocks a partition has, hence its index size. Changing it moves the
  transition point and would be mistaken for the knob under test. Hold fixed
  and record it.
- **Partition width distribution** is effectively the independent variable in
  disguise. Use a fixed, known set of partitions; do not let a stress profile
  vary widths between runs.
- **SSTable format** — confirm BIG. On BTI this code is not reached at all.
- **Key cache warmth** — `nodetool invalidatekeycache` before each
  measurement, and allow the same number of reads to warm it, or `Entries`
  comparisons are meaningless. Note the cache is also **saved and restored
  across restarts** (`AutoSavingCache`), so a restart does not clear it.
- **Compaction and flush** rewrite entries with the *then-current* threshold
  on the write path, while the read path uses the live value — so a run that
  changes the knob and then triggers compaction is measuring a mixture.
  Disable autocompaction and avoid flushing mid-sweep.
- **Baseline** at default `2KiB` with the standard workload; **idle control**
  with the data loaded but no reads issued, to separate cache-driven heap from
  everything else.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — found 2026-09-22 by the capacity-word pass reading the source directly. Judged as a qualifying pattern-(b) candidate and parked in `deferred.md` §1c ("strong") under the then-current (a)-only scope; unparked 2026-09-25; written up 2026-09-28. |
| **Filed by / Date** | Claude (`claude-opus-5`) session, 2026-09-28 |
| **Line numbers checked** | 2026-09-28 against the local `cassandra-5.0.9` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). All line numbers carried from `deferred.md` §1c (`:113`, `:171`, `:227`) confirmed unchanged. |
| **Escape hatch / Target-3 note** | **No flag-style escape hatch** — the check cannot be switched off, only moved. Two adjacent observations for Target 3: (1) the constraint is **format-scoped**, so a table on the BTI format bypasses it entirely; (2) the read-path site reads the config **live per deserialization**, so a JMX change takes effect on already-written SSTables with no rewrite — an unusually cheap way to change a memory characteristic at runtime, in either direction. |
| **Stage-4 feedback** | none yet |
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
