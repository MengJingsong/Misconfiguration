# Integer_MAX_VALUE — index summary entries (the BIG format's sampled key index)

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | INTEGER_MAX_VALUE-MAYBEADDENTRY-INTEGER_MAX_VALUE |
| **Constraint** | `Integer_MAX_VALUE` — a **type bound**: the JDK constant `java.lang.Integer.MAX_VALUE` (2^31 − 1 = 2,147,483,647), written literally at both check sites. No Cassandra variable declares it, and no configuration entry, system property or JMX attribute reaches it. It is there because the summary stores each entry's position as a 32-bit `int` ([`IndexSummaryBuilder.java:206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L206), read back by [`IndexSummary.getPositionInSummary():159-163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L159-L163)). The naming judgement (README §6.1) is in §4. |
| **Enforcement pattern** | **(a)** at both sites — each comparison is the `if` whose branches diverge. |
| **Capacity check** | [`IndexSummaryBuilder.maybeAddEntry():204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L204) — `(entries.length() + getEntrySize(decoratedKey)) <= Integer.MAX_VALUE`, the hard stop per sampled entry (primary). **Second site**, on the same constraint: [`IndexSummaryBuilder.<init>():108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L108) — `maxExpectedEntriesSize > Integer.MAX_VALUE`, the up-front clamp on an **estimate** (README §6.1, "one case, several check sites"). |
| **Decision point** | The same lines: [`:204-216`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L204-L216) and, for the second site, [`:108-122`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L108-L122). |
| **Allocation site** | [`:206-208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L206-L208) — the entry (key bytes + 8-byte index position) appended to the off-heap `entries` region and its 4-byte offset to `offsets`; when the region is full the write grows it through [`SafeMemoryWriter.expandToFit():45-48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L45-L48) → [`resizeTo():50-67`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L50-L67), a new native block. Second site: [`:126-127`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L126-L127), the two `SafeMemoryWriter`s sized from the (possibly clamped) estimate. |
| **Related cases** | [`column_index_cache_size-indexSamples-cacheSizeThreshold.md`](column_index_cache_size-indexSamples-cacheSizeThreshold--guided.md) — same module and format (BIG only), the other case whose limit decides how much of an SSTable's index is held in memory, and whose disallow cost reappears as index-file reads. [`repair_session_space-split-maxsize.md`](repair_session_space-split-maxsize--guided.md) — its split path draws key samples from this summary ([`BigTableReader.getKeySamples():465-467`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L465-L467)). Not a site of this case: [`IndexSummaryRedistribution.java:341`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java#L341) and [`:258`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java#L258), the `index_summary_capacity` pool (`undetermined.md` §5, §11 below). |

```java
// IndexSummaryBuilder.maybeAddEntry():200-228 — the capacity check (primary site) and decision point.
public IndexSummaryBuilder maybeAddEntry(DecoratedKey decoratedKey, long indexStart, long indexEnd, long dataEnd) throws IOException
{
    if (keysWritten == nextSamplePosition)              // only the keys chosen for sampling reach the check
    {
        if ((entries.length() + getEntrySize(decoratedKey)) <= Integer.MAX_VALUE)   // <-- :204
        {
            offsets.writeInt((int) entries.length());   // ALLOW: 4-byte offset, :206
            entries.write(decoratedKey.getKey());        //        key bytes, :207
            entries.writeLong(indexStart);               //        8-byte index position, :208
            setNextSamplePosition(keysWritten);          //        choose the next key to sample, :209
        }
        else
        {
            // DISALLOW: nothing written, nextSamplePosition NOT advanced
            logger.error("Memory capacity of index summary exceeded (2GiB), index summary will not cover full sstable, " +
                         "you should increase min_sampling_level");                   // :214-215
        }
    }
    else if (dataEnd != 0 && keysWritten + 1 == nextSamplePosition)
    {   ... readable boundary for early open ... }
    keysWritten++;
    return this;
}
```

```java
// IndexSummaryBuilder.<init>():100-127 — the second site: a clamp on the expected size.
long expectedEntrySize = getEntrySize(defaultExpectedKeySize);          // property, default 64 B, + 8
long maxExpectedEntries = expectedKeys / minIndexInterval;
long maxExpectedEntriesSize = maxExpectedEntries * expectedEntrySize;
if (maxExpectedEntriesSize > Integer.MAX_VALUE)                         // <-- :108
{
    int effectiveMinInterval = (int) Math.ceil((double)(expectedKeys * expectedEntrySize) / Integer.MAX_VALUE);
    maxExpectedEntries = expectedKeys / effectiveMinInterval;
    ...
    logger.warn("min_index_interval of {} is too low for {} expected keys of avg size {}; using interval of {} instead", ...);
    this.minIndexInterval = effectiveMinInterval;                       // sample more sparsely
}
else
    this.minIndexInterval = minIndexInterval;
maxExpectedEntries = Math.max(1, (maxExpectedEntries * samplingLevel) / BASE_SAMPLING_LEVEL);
offsets = new SafeMemoryWriter(4 * maxExpectedEntries)...;              // :126
entries = new SafeMemoryWriter(expectedEntrySize * maxExpectedEntries)...; // :127 — the up-front native reservation
```

## 2. Context

A Cassandra node in the default (BIG) SSTable format keeps, for every data file
on disk, a small in-memory sample of that file's partition keys: every *n*th key
together with where its entry sits in the file's on-disk key index. A read
binary-searches this sample to find the nearest sampled key, then scans only a
few entries of the on-disk index from there. This "index summary" lives outside
the Java heap, and it grows with the number and size of the keys in the file.

The summary records each entry's position as a 32-bit integer, so its key area
cannot pass 2 GiB. Two checks keep it under that bound. When the summary is
created, the builder estimates its final size from the expected key count and a
typical key size; if the estimate exceeds 2 GiB, it samples more sparsely from
the start and reserves less memory. Then, as keys are sampled, every entry is
checked against the bound itself; the first entry that would cross it is
refused, an error is logged, and no further key of that file is sampled.
Nothing fails: the file is written and readable, but a read of a key past the
last sample must scan the on-disk index linearly from that sample, so the memory
not spent comes back as disk reads. The bound is a property of the data type,
not a setting; no configuration moves it.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `sstable_index` — the BIG format's per-SSTable key indexes: the index summary (`io/sstable/indexsummary`), the row index entries and the key cache (`io/sstable/format/big`) |
| **One-line role** | The BIG SSTable format locates a partition through its on-disk primary index; the index summary is the off-heap sample of that index that a read binary-searches first, rebuilt and resized by `IndexSummaryManager`. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes** — the bytes already written into the summary's `entries` region plus the next entry's size, against a byte ceiling, gating the write of that entry. At the second site, an estimate of the whole summary's size against the same ceiling, gating how densely keys are sampled and how much memory is reserved. |
| **Usage-side operand** | `entries.length() + getEntrySize(decoratedKey)` — the summary's written length ([`SafeMemoryWriter.length():84-87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L84-L87)) plus the key's length + 8 ([`getEntrySize():137-149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L137-L149)). The 4-byte offsets are a separate region and are **not** counted. Second site: `maxExpectedEntriesSize` = `expectedKeys / minIndexInterval × (defaultExpectedKeySize + 8)` ([`:105-107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L105-L107)). |
| **Limit-side operand** | `Integer.MAX_VALUE`, literal at [`:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L204), [`:108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L108) and [`:111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L111). A compile-time constant, so `javac` folds it into the bytecode as the number 2,147,483,647: nothing reads a field at run time. |
| **Limit type** | **Hardcoded constant — a type bound** (README §8.3, "limits that cannot be varied by config"). |

**Limit initialization path** (short, as for any hardcoded limit):

1. `java.lang.Integer.MAX_VALUE` — declared in the JDK (outside the pinned source; no link).
2. Why it binds here: [`:206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L206) stores `(int) entries.length()` as the entry's offset, and every reader of the summary takes it back as an `int` ([`IndexSummary.getPositionInSummary():159-163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L159-L163), used by `binarySearch()` through `fillTemporaryKey()`, [`:174-179`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L174-L179)). The backing writer can itself grow past 2 GiB ([`SafeMemoryWriter.java:101-117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L101-L117) keeps a window on the tail), so the offsets' type, not the buffer, is the bound.
3. Read at [`:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L204) for every sampled key, and at [`:108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L108) / [`:111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L111) once per builder.

**What a user can tune is the usage side.** Three inputs decide whether, and
where, the bound is reached; none moves it:

- **`min_index_interval`** — a table option, default 128
  ([`TableParams.java:364`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L364)),
  at least 1 ([`:185-186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L185-L186));
  read when each builder is made ([`BigTableWriter.java:255`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L255)),
  so `ALTER TABLE` applies to SSTables written afterwards. At full sampling the
  summary holds every `min_index_interval`th key, so `:204` is reached when one
  SSTable's sampled key bytes, about `keys / min_index_interval × (key size + 8)`,
  pass 2 GiB: at the default 128, about 256 GiB of partition-key bytes in one
  SSTable; at 1, about 2 GiB.
- **The key size** — up to 65,535 bytes per partition key
  ([`Validation.java:51-56`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Validation.java#L51-L56)).
- **`cassandra.index_summary_expected_key_size`** — a JVM system property,
  default 64 ([`CassandraRelevantProperties.java:283`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L283)),
  read once into the static `defaultExpectedKeySize`
  ([`IndexSummaryBuilder.java:42`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L42),
  not `final`; upstream tests assign it). It enters **only** the second site's
  estimate: raising it makes the clamp fire on fewer keys and inflates the
  up-front reservation; real keys larger than it leave `:204` to bind.

**Naming (README §6.1) — the judgement the queue asked for.** §6.1 names a
constraint after the variable first declared on the limit's path. Here that
path has one step, a JDK constant, so the rows of §6.1 were weighed in turn:
"configuration entry" and "JVM system property" do not apply (the limit is
neither); "runtime-queried limit with no declared variable → the accessor"
does not apply (nothing is queried; the number is folded in at compile time);
"derived from several sources → the one a user would tune" does not apply
either, because `min_index_interval`, the key size and the expected-key-size
property are all usage-side inputs, and naming the case after one of them would
name a usage factor as the limit (the queue's alternative). That leaves
"constant → the declaring variable's name, qualified with its class only if the
bare name is ambiguous". The declaring variable is `MAX_VALUE` in
`java.lang.Integer`; the bare name is ambiguous (`Long.MAX_VALUE`,
`Short.MAX_VALUE`, `Byte.MAX_VALUE`), so it is qualified, and the
dot becomes `_` as in the folder's other class-qualified names
(`DataDirectory_getAvailableSpace`, `ExecutorPlus_DEFAULT_QUEUE_CAPACITY`):
**`Integer_MAX_VALUE`**. The function is `maybeAddEntry`, the method enclosing
the primary site; `:204` is primary because it binds for every key size and is
the line the capacity-word pass queued, while `:108` acts only through the
64-byte estimate (§5). The operand is written `Integer.MAX_VALUE` at the check,
rendered the same way, as `CACHEABLE_MUTATION_SIZE_LIMIT` repeats its
constraint as its operand. Stem: `Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE`.
The cost of this choice: any later case on another `Integer.MAX_VALUE` check
shares the constraint name `Integer_MAX_VALUE` and is told apart only by its
function (and, if the stem is identical, by §6.1's `-2`); the `Object` column
of `_INDEX.md` then carries the distinction.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`IndexSummaryBuilder.maybeAddEntry():204-216`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L204-L216); second site [`IndexSummaryBuilder.<init>():108-122`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L108-L122). |
| **Verdict** | n/a — the check is the decision at both sites. |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** (`:204`) | `entries.length() + key length + 8 <= 2^31 − 1` | The entry is written: offset, key, position; `entries` grows if full; the next sample position is chosen. |
| **Disallow** (`:204`) | `> 2^31 − 1` | Nothing is written and nothing grows; one `ERROR` line; `nextSamplePosition` stays where it is, so **no later key reaches the check again** and the summary ends at the last accepted entry. |
| **Allow** (`:108`) | `expectedKeys / min_index_interval × (E + 8) <= 2^31 − 1`, *E* the property | Sampling interval = `min_index_interval`; reservation `(E + 8) × expectedKeys / min_index_interval` bytes. |
| **Disallow** (`:108`) | `> 2^31 − 1` | Interval raised to *e* = `ceil(expectedKeys × (E + 8) / (2^31 − 1))`; reservation `(E + 8) × floor(expectedKeys / e)` ≤ 2^31 − 1; one `WARN` line; the raised interval is **stored in the summary** ([`:117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L117), passed to `IndexSummary` at [`:275-277`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L275-L277)). |

```java
// allow (:204): IndexSummaryBuilder.java:206-209
offsets.writeInt((int) entries.length());
entries.write(decoratedKey.getKey());
entries.writeLong(indexStart);
setNextSamplePosition(keysWritten);
```

```java
// disallow (:204): IndexSummaryBuilder.java:214-215 — the only statement in the branch
logger.error("Memory capacity of index summary exceeded (2GiB), index summary will not cover full sstable, " +
             "you should increase min_sampling_level");
```

**The refusal is final for the builder.** `setNextSamplePosition()` is only
called on allow ([`:209`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L209)),
and `keysWritten` keeps rising ([`:226`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L226)),
so `keysWritten == nextSamplePosition` is never true again: exactly one refusal
and one `ERROR` line per summary, and a later, smaller key that would still fit
is not sampled either. With fixed-size keys of *K* bytes at interval 1, the
summary keeps *n*\* = `floor((2^31 − 1) / (K + 8))` entries and the refusal falls
on the key with `keysWritten` = *n*\*. The readable-boundary branch
([`:218-224`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L218-L224))
stops for the same reason, so an SSTable being written can no longer be opened
early past that point (derived; not tested here).

**Rule 3 at each site.** At `:204` the disallow withholds the entry: nothing is
written, no block is grown. At `:108` both branches build the builder, and the
divergence is in **how much is reserved and how many keys are sampled**, as in
`column_index_cache_size` (retained size, not existence).

**The two sites and how they meet.** `:108` sees only an estimate: the
writer's expected key count and the property's 64-byte key. When that estimate
is right or high, the clamp keeps the summary under the bound and `:204` never
fires. `:204` binds when the real keys are larger than the estimate *E* or more
numerous than expected: for example a table with `min_index_interval` 1 and 60,000-byte
keys passes 2 GiB at about 35,800 keys, where the estimate is 2.6 MB. The
upstream tests drive one site each (§9b).

**Three production builders reach both sites**, all in the BIG format:

| Builder | When | Expected keys | Trimmed after sampling? |
|---|---|---|---|
| [`BigTableWriter$IndexWriter.<init>():255`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L255), entries from [`append():289`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L289) | every new SSTable: flush (the flush set's exact partition count, [`Flushing.java:113-117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/Flushing.java#L113-L117)), compaction, streaming, upgrade | the writer's key count | **yes**, [`doPrepare():320`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L320) |
| [`BigTableReader.buildSummaryAtLevel():631`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L631), entries from [`:636`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L636) | index-summary redistribution rebuilds a summary from the index file ([`:602-604`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L602-L604)) | `estimatedKeys()` | **no** |
| [`BigSSTableReaderLoadingBuilder.java:209`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java#L209), entries from [`:220`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java#L220) | an SSTable opened without a usable `Summary.db` (missing, corrupt, or saved at another `min_index_interval`) | estimated from the first 10 MB of the index | **no** |

The BTI format has no index summary, so a table on BTI never reaches either site.

## 6. Code path

### 6a. Allow path → object creation

1. [`BigTableWriter$IndexWriter.append():267-289`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L267-L289) — writes the key and its row index entry to `Index.db`, then calls `summary.maybeAddEntry(key, indexStart, indexEnd, dataEnd)`.
2. [`IndexSummaryBuilder.maybeAddEntry():202-204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L202-L204) — the key is the next to sample, and the comparison holds.
3. [`:206-208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L206-L208) — **object creation**: 4 bytes into `offsets`, `K` + 8 bytes into `entries`.
4. When `entries` is full, the write calls [`DataOutputBuffer.doFlush():136-139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L136-L139) → [`SafeMemoryWriter.expandToFit():45-48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L45-L48): the new capacity is twice the old below 64 MiB and 1.5 times above ([`DataOutputBuffer.calculateNewSize():158-172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L158-L172)); [`resizeTo():50-67`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L50-L67) copies into a new block ([`SafeMemory.copy():70-75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemory.java#L70-L75)) and frees the old one. The block comes from [`MemoryUtil.allocate():81-84`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemoryUtil.java#L81-L84), JNA `Native.malloc`.
5. [`BigTableWriter$IndexWriter.doPrepare():320-323`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L320-L323) — `prepareToCommit()` trims both regions to their length ([`IndexSummaryBuilder.java:246-252`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L246-L252), [`SafeMemoryWriter.trim():69-72`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L69-L72)); `build()` wraps them in an `IndexSummary` ([`:261-278`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L261-L278)), which is saved as `Summary.db` ([`IndexSummaryComponent.save():118-128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/IndexSummaryComponent.java#L118-L128)) and kept by the SSTable reader for the SSTable's life.

**Second site.** [`BigTableWriter.java:255`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java#L255)
→ [`IndexSummaryBuilder.<init>():105-108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L105-L108),
estimate at most the bound → [`:121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L121)
keeps the table's interval → [`:125-127`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L125-L127)
**object creation**: `new SafeMemoryWriter(...)` twice, the reservation allocated at once ([`SafeMemoryWriter.java:28-31`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java#L28-L31) → [`SafeMemory.java:30-34`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/SafeMemory.java#L30-L34) → [`Memory.java:60-65`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/Memory.java#L60-L65)).

### 6b. Disallow path effect

**Not a rejection: the summary stops growing, and the cost moves to index reads.**

1. [`:214-215`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L214-L215) — one `ERROR` line; no byte is written and no block grows. The SSTable itself is written in full: `Data.db` and `Index.db` hold every key.
2. Every later key of the builder skips the check (§5). `build()` uses the entries written ([`:265-266`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L265-L266)) but still records the full key count: `sizeAtFullSampling` is computed from `keysWritten` ([`:273`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L273)), so the SSTable's estimated key count stays right.
3. **A read past the last sample still finds its key.** [`BigTableReader.getRowIndexEntry():277-281`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L277-L281) binary-searches the summary, lands on the last entry, and scans `Index.db` from there ([`:291-351`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L291-L351)). After the first `effectiveInterval` entries it compares decorated keys ([`:304-320`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L304-L320)); for an equality lookup `Operator.EQ.apply()` returns `−comparison` ([`SSTableReader.java:1213-1219`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java#L1213-L1219)), which is positive while the index key is smaller, so the scan **continues** until it reaches the key or passes it. A point read of the key at token rank *r* ≥ *n*\* (0-based, *n*\* entries at interval 1) therefore skips *r* − *n*\* + 1 index entries ([`RowIndexEntry.Serializer.skip():443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L443), called at [`BigTableReader.java:349`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L349)) before the match. **Memory is traded for index reads**, as in `column_index_cache_size`, and the trade grows with the number of uncovered keys. Nothing is lost.
4. Smaller effects (derived from reading, not tested): range-ownership estimates built from the summary's samples (`estimatedKeysForRanges`, [`BigTableReader.java:445-450`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L445-L450)) and key samples for repair splitting see no key past the last sample.

**Second site's disallow.** The raised interval is stored in the summary and in
`Summary.db`, and then disagrees with the table's `min_index_interval`
(derived from reading, tested by arm E in §9): on the next start
`IndexSummary.deserialize()` refuses the file ("Cannot read index summary
because min_index_interval changed from …",
[`IndexSummary.java:426-430`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L426-L430)),
the file is deleted ([`IndexSummaryComponent.loadOrDeleteCorrupted():102-113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/IndexSummaryComponent.java#L102-L113)),
and the summary is rebuilt from the whole index file and saved again
([`BigSSTableReaderLoadingBuilder.java:110-127`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java#L110-L127)),
through the same clamp, so with the same inputs **every restart rebuilds it**.
Redistribution likewise always takes the rebuild path for such an SSTable
([`BigTableReader.java:602`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L602)).

**No escape hatch.** Nothing switches the comparison off or raises the limit.
Two situations make the summary's real cost differ from the check's count:
the offsets region (4 bytes per entry) is outside the comparison, and the two
rebuild paths keep the untrimmed block (§7).

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | One summary entry: the key's bytes and an 8-byte position in the `entries` region, and a 4-byte offset in `offsets` ([`:206-208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L206-L208)); in the end the `IndexSummary` ([`IndexSummary.java:96-110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L96-L110)) that holds both regions. Second site: the two regions' initial blocks. |
| **Resource consumed** | **Native (off-heap) memory** from JNA `Native.malloc` ([`MemoryUtil.java:81-84`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemoryUtil.java#L81-L84)): not a direct `ByteBuffer`, so neither the `direct` buffer pool MXBean nor JVM Native Memory Tracking sees it (the trap found on `memtable_offheap_space`). The same bytes go to disk in `Summary.db` (§9d gives its exact size). |
| **Rough sizing** | Entry = key length + 8 bytes; offset = 4 bytes. After trimming, a summary of *n* entries of *K*-byte keys holds exactly *n* (*K* + 12) bytes, which is what the table gauge `IndexSummaryOffHeapMemoryUsed` reports (`offsetCount × 4 + entriesLength`, [`IndexSummary.getOffHeapSize():259-262`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L259-L262); gauge [`IndexSummaryMetrics.java:40-43`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryMetrics.java#L40-L43)). `:204` caps the entries at 2^31 − 1 bytes; the offsets add 4 / (*K* + 8) on top, up to 4/9 for 1-byte keys (a key may not be empty, [`Validation.java:47-48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Validation.java#L47-L48)), a quarter for 8-byte keys. **During the build**, each growth copies the region, so the old and the new block coexist: the peak is about 2.5 times the length at the last growth (from the 1.5× rule, §6a), before trimming. **Second site**: the reservation is `(E + 8) × floor(expectedKeys / e)` for `entries` and 4 bytes per expected entry for `offsets`, made at once whether or not it is used. |
| **Lifetime / release** | The SSTable reader holds the summary until the SSTable is dropped (compacted away, truncated) or its summary replaced by redistribution. **The two rebuild paths do not trim** (`buildSummaryAtLevel()` and the loading builder call `build()` without `prepareToCommit()`, [`BigTableReader.java:631-640`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L631-L640), [`BigSSTableReaderLoadingBuilder.java:229-230`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java#L229-L230)), so a rebuilt summary keeps its whole block, reservation or grown capacity, while the gauge counts only the length (derived from reading; arm E measures one instance). Linux makes only written pages resident, so an unused reservation is address space more than RSS. |

## 8. Maximum memory bound

- **Per SSTable, a hard ceiling on the entries.** Whatever the data, one
  summary's entries region never passes 2^31 − 1 bytes; with offsets, a trimmed
  summary holds at most `2^31 − 1 + 4 n*` bytes, `n*` the entries kept. The
  check counts written bytes against the bound directly, so the ceiling is exact
  to within one entry: `n* (K + 8)` lies in `(2^31 − 1 − (K + 8), 2^31 − 1]`.
- **Not node-wide.** Each SSTable has its own summary, so the node's summary
  memory is the sum over SSTables; the node total is the business of
  `index_summary_capacity` and its periodic redistribution, which works after
  the fact by downsampling or rebuilding summaries (`undetermined.md` §5). This
  check is what stops one summary at write time, before any redistribution, and
  it also bounds every summary a redistribution rebuilds (the rebuild goes
  through the same builder).
- **When it binds.** Only when one SSTable's sampled key bytes pass 2 GiB:
  at full sampling `keys / min_index_interval × (K + 8)` — about 256 GiB of
  partition keys in one SSTable at the default interval of 128, about 2 GiB at
  interval 1 (§4). Below that, the check never fires and the summary's size is
  set by the keys and the interval alone.
- **The direction it can move.** The bound can only be **lowered** by a patched
  build: above 2^31 − 1 the `int` offsets (§4 step 2) would wrap and the summary
  would be corrupt. Lowered to *L*, the retained entries fall one-for-one with
  *L* (`n* = floor(L / (K + 8))`), and each read of an uncovered key pays a
  longer scan of `Index.db` (§6b); §9 simulates this.
- **The second site** caps the **up-front reservation** at 2^31 − 1 bytes for
  the estimated key size, and samples more sparsely so the expected summary
  fits. Without it a writer expecting 100 million keys at interval 1 would
  reserve 7.2 GB before writing a key. It does not bound the final summary
  when real keys are larger than the estimate; `:204` does.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
The test fills one SSTable's summary to the bound with keys of known size and
checks that it stops at the predicted entry, with the limit moved by a Byteman
rule to 8, 32 and 128 MiB and at the real 2 GiB, then reads the keys past the
last sample. **Run so far:** none.

*Amended 2026-10-15 (stage-4 step-0 audit, before any reading; results file §1.1).* (1) `load-keys.py` writes no key file:
both scripts regenerate a table's keys from its seed, *N* and *K* (a `big` key file would be 2.4 GB). (2) The stage-4 run uses
its own clone `~/cassandra-run3` at `cassandra-5.0.9` (the shared `~/cassandra-run1` is in use by another case's runs); every
path below that starts with `build/` or `bin/` is relative to that clone. Nothing in §9a changes.

### 9a. Procedure and conclusions

**Testability:** **needs patched build** to move the limit: `Integer.MAX_VALUE`
is folded into the bytecode at `:204` and `:108`, and no configuration,
property or JMX attribute reaches it; it can only be lowered (§8). **Stage 4
uses a Byteman rule instead of a patched build:** it adds `2^31 − 1 − L` to the
value `getEntrySize(DecoratedKey)` returns, whose only caller is `:204`, so the
comparison becomes `entries.length() + K + 8 ≤ L` and nothing that is written
changes; the rule is loaded and unloaded on the live node. The real limit is
reached unpatched in the unit tier and in one cluster arm. The usage-side
inputs are `min_index_interval` (table option, applies to new SSTables), the
key size (the workload) and `cassandra.index_summary_expected_key_size` (JVM
property, restart; second site only).

**Claim under test:** one SSTable's summary keeps the largest number *n*\* of
sampled entries whose total (key + 8 bytes each) is at most the limit; the next
sample is refused with one `ERROR` line, nothing is written, no later key is
sampled, and a read of a key past the last sample finds it by scanning the index
file from there; separately, when the expected summary exceeds the limit, the
builder samples every *e*-th key, *e* = `ceil(expected bytes / (2^31 − 1))`,
and reserves at most the limit.

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** the summary's entries, and so its native memory and its
  `Summary.db`, stop at *n*\* (*K* + 8) ≤ the limit, the disallow branch is what
  stops them, and the cost moves to index-file reads.
- **Test:** unit tier at the real limit (keys of 3,000, 30,000 and 65,535 bytes,
  interval 1 and 2, the boundary pair) and with the moved limit; the second
  site at its boundary. Cluster tier: one node, BIG, `min_index_interval` 1,
  1,000-byte keys at moved limits of 8, 32 and 128 MiB and 60,000-byte keys at
  the real 2 GiB; each table loaded and flushed once into one SSTable, with
  1.25 *n*\* keys (and *n*\*, *n*\* + 1, 2.5 *n*\* at 32 MiB); read the summary's
  count and length, the table gauge, the `Summary.db` size and the refusal
  trace; then read keys past the last sample. Arm E sets the property and
  reads the second site.
- **Logic:** (1) a refusal appears where *N* > *n*\* and none where *N* ≤ *n*\*:
  the limit is reached (else the run is invalid). (2) The summary holds exactly
  *n*\* entries whatever *N* beyond it: usage **stops at the limit**. (3) *n*\*
  and the retained bytes scale 1 : 4 : 16 across 8, 32, 128 MiB, and equal the
  formula at 2 GiB: usage **follows the constraint**. (4) The refusal trace
  falls on `keysWritten` = *n*\*, with the unique `ERROR` line, and the control
  without the rule covers every key: the **disallow branch** stops it.
  (5) The gauge and `Summary.db` equal *n*\* (*K* + 12) and the file formula:
  the **real** native and disk bytes follow. (6) Reads past the last sample
  return their row after *r* − *n*\* + 1 skipped index entries: the cost is
  displaced, not lost. (7) Arm E: interval and reservation flip at the
  predicted boundary.
- **Refuted if:** a summary keeps more than *n*\* entries or more than *L*
  bytes of entries; *n*\* does not follow *L*; the gauge or the file grows past
  *n*\* (*K* + 12) while the count stops; a read past the last sample returns
  nothing (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — U0 upstream `IndexSummaryTest`; U1 `:204` at the real limit;
   U2 `:108` at its boundary; U3 the moved limit (the Byteman rule the cluster
   tier uses, checked against U1's formula). 9c, 9e.
2. **Cluster tier** — one node on `pc57`; lifetime 1: control, the real-limit
   arm and the moved-limit arm; lifetimes 2–4: arm E (second site). 9b, 9e.
3. **At each value:** control (the same data without the rule, all keys
   sampled) → **scenario A**, *N* = *n*\* (no refusal) and *N* = *n*\* + 1 (one
   refusal, on the last key) → **scenario B**, *N* = 1.25 *n*\* and 2.5 *n*\*:
   the summary does not grow. No scenario C: no path exceeds the cap (§6b).
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *L* = the limit in force (2^31 − 1 = 2,147,483,647
without the rule); *K* = key size in bytes; *N* = keys in the SSTable;
*n*\* = `floor(L / (K + 8))`; at interval 1 the summary keeps
min(*N*, *n*\*) entries.

| Table | *L* | *K* | *N* | Entries kept | `entriesLength` (B) | Gauge = `Summary.db` − 24 − 2 (*K* + 4) (B) | `Summary.db` (B) | Refusal at `keysWritten` | `ERROR` lines | Max skips per read |
|---|---|---|---|---|---|---|---|---|---|---|
| `c32` (control) | 2^31 − 1 | 1,000 | 41,610 | 41,610 | 41,942,880 | 42,109,320 | 42,111,352 | — | 0 | 0 |
| `t8` | 8 MiB | 1,000 | 10,403 | 8,322 | 8,388,576 | 8,421,864 | 8,423,896 | 8,322 | 1 | 2,081 |
| `t32` | 32 MiB | 1,000 | 41,610 | 33,288 | 33,554,304 | 33,687,456 | 33,689,488 | 33,288 | 1 | 8,322 |
| `t32a` (A) | 32 MiB | 1,000 | 33,288 | 33,288 | 33,554,304 | 33,687,456 | 33,689,488 | — | 0 | 0 |
| `t32b` (A) | 32 MiB | 1,000 | 33,289 | 33,288 | 33,554,304 | 33,687,456 | 33,689,488 | 33,288 | 1 | 1 |
| `t32c` (B) | 32 MiB | 1,000 | 83,220 | 33,288 | 33,554,304 | 33,687,456 | 33,689,488 | 33,288 | 1 | 49,932 |
| `t128` | 128 MiB | 1,000 | 166,440 | 133,152 | 134,217,216 | 134,749,824 | 134,751,856 | 133,152 | 1 | 33,288 |
| `big` (real limit) | 2^31 − 1 | 60,000 | 40,000 | 35,786 | 2,147,446,288 | 2,147,589,432 | 2,147,709,464 | 35,786 | 1 | 4,214 |

- **Exact relations** (the table's numbers follow from them): entries kept =
  min(*N*, *n*\*); `entriesLength` = kept × (*K* + 8) ≤ *L*; gauge = kept ×
  (*K* + 12); `Summary.db` = 24 + gauge + 2 (*K* + 4) (header of 24 bytes, then
  offsets and entries, then the SSTable's first and last keys with 4-byte
  lengths, [`IndexSummary.java:399-421`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L399-L421),
  [`IndexSummaryComponent.java:125-127`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/IndexSummaryComponent.java#L125-L127));
  the `built` trace's `entries` capacity = `entriesLength` (trimmed).
  Tolerance: none; every reading is an integer from the code.
- **Dose-response:** across *L* = 8, 32, 128 MiB, *n*\* = 8,322 · 33,288 ·
  133,152, which is 1 : 4.000 : 16.000 to within one entry, and the gauge
  follows it.
- **Reads:** with keys sorted by Murmur3 token, a point read of the key of rank
  *r* (0-based) skips 0 entries for *r* < *n*\* and *r* − *n*\* + 1 for
  *r* ≥ *n*\*; every read returns its row. The last column is the read of the
  highest-ranked key.
- **Real-limit arm, supporting:** the node's `RssAnon` rises by at least
  2.0 GiB at `big`'s flush and does not fall while the SSTable is open; the peak
  during the flush may be higher (growth copies, §7). Support, not a deciding
  reading.
- **Real-limit arm, restart:** after a restart `big`'s summary loads from
  `Summary.db` without a rebuild (no "Index summary file is corrupted" line for
  it), with the same gauge. (Its last stored offset, 2,147,529,424 with the
  offsets' base added, passes 2^31 − 1 on disk and must wrap back on load,
  [`IndexSummary.java:411`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L411),
  [`:475`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L475);
  derived, this step tests it.)
- **Arm E (second site)**, `cassandra.index_summary_expected_key_size` =
  65,536, so the estimate per key is 65,544 bytes; 1,000-byte keys:
  - `e41`, *N* = 41,610: 41,610 × 65,544 = 2,727,285,840 > 2^31 − 1, so *e* = 2;
    one `WARN` line ending `using interval of 2 instead`; reservation
    65,544 × 20,805 = 1,363,642,920 B for `entries`; kept 20,805 entries
    (keys 0, 2, 4, …), `entriesLength` 20,971,440, gauge 21,054,660,
    `Summary.db` 21,056,692; JMX `IndexIntervals` 2 for its SSTable.
  - `e30`, *N* = 30,000: 1,966,320,000 ≤ 2^31 − 1, so interval 1; no `WARN`;
    reservation 1,966,320,000 B; kept 30,000, gauge 30,360,000, `Summary.db`
    30,362,032; `IndexIntervals` 1.
  - **Restart with the property:** `e41`'s `Summary.db` is refused (debug line
    "Index summary file is corrupted", cause "min_index_interval changed from 2
    to 1") and rebuilt; the `init` trace's `expectedKeys` is the loader's
    estimate *Ñ*, and the clamp gives *e* = `ceil(Ñ × 65,544 / (2^31 − 1))`
    (2 for *Ñ* between 32,765 and 65,528), one `WARN`, and a `built` line whose
    `entries` capacity is the **untrimmed** reservation 65,544 × floor(*Ñ* / *e*)
    while `entriesLength` is 20,971,440 (derived, §7). `e30` loads without a
    rebuild.
  - **Restart without the property:** `e41` is refused again and rebuilt at
    interval 1, no `WARN`; kept 41,610, `entriesLength` 41,942,880; the next
    restart loads it without a rebuild.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Every table keeps min(*N*, *n*\*) entries with `entriesLength`, gauge and `Summary.db` as tabulated; one refusal line and one `ERROR` line exactly where *N* > *n*\*, at `keysWritten` = *n*\*; none in the control; *n*\* follows *L* 1 : 4 : 16 and the real-limit arm matches the formula; every read returns its row with the predicted skips | **Confirmed** — the type bound caps one summary's entries as traced, and the disallow displaces the cost to index reads. |
| A table keeps more than *n*\* entries, or `entriesLength` > *L* | **Refuted** — the check does not cap the summary. |
| The count stops at *n*\* but the gauge, the `built` capacity on the writer path or `Summary.db` exceed *n*\* (*K* + 12) (or its file formula) | **Refuted** for §7/§8 — the check's count does not track the memory; chase the trim. |
| *n*\* is the same at every *L* while *N* exceeds it | **Refuted** — not the binding limit; first confirm the rule was in force (the submit client's listing, the instrument check), else **Invalid run**. |
| The count stops below *n*\* with no refusal line, or with a refusal at another `keysWritten` | **Not confirmed** — something else ends sampling (a second SSTable, a sampling level below 128); re-read. |
| A refusal line without the `ERROR` line, or more than one `ERROR` per SSTable | **Not confirmed** for §5's "final for the builder"; re-read. |
| A read of a key past the last sample returns no row | **Refuted** for §6b — the disallow loses data (Target-3 material); record which ranks. |
| Reads return their rows but the skips differ from *r* − *n*\* + 1 | **Not confirmed** for §6b's scan; record the counts against the ranks. |
| No refusal where *N* > *n*\*, or a table flushed into more than one SSTable | **Invalid run** — the limit was not reached in one summary; fix 9b/9c and repeat that table. |
| Arm E: `e41` at interval 1 or `e30` at interval 2 | **Refuted** for the second site's boundary. |
| Arm E: interval and counts as predicted, but the restart rebuild or the untrimmed capacity is not seen | **Not confirmed** for those derived sub-predictions (§6b, §7); the verdict on the cap stands. |
| An instrument is silent: no `writer`/`init`/`built` line for a flushed `ks` table, or no `scan` line for a read | **Invalid run** for that reading; fix the harness and repeat. |

**Why the summary's own count and not the node's memory alone:** the summary
is a small part of the node's native memory and is invisible to NMT; only its
entry count, its bytes (gauge, file, trace) and the refusal line tie a reading
to this check.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | None in configuration (Testability). Moved limit: `moved-limit-<L>.btm` (9c), loaded and removed on the live node with Byteman's submit client (`build/lib/jars/byteman-submit-*.jar`, `-l` / `-u`, port 9091), one at a time. Real limit: no rule. Second site: `-Dcassandra.index_summary_expected_key_size=65536` in `JVM_EXTRA_OPTS` of the `bin/cassandra` command (restart). |
| **Confirm it took effect** | The submit client's `-l` listing (no file argument) shows exactly the intended rule before each table's flush; the instrument check (9e) shows the rule moves the refusal. Arm E: the `init` trace's `effective` and `entriesCapacity` for a probe flush. |
| **Capacity values** | *L* = 8, 32, 128 MiB (moved) and 2^31 − 1 (real, the "default"). Second site: the property at 65,536 against the default 64. |
| **Scope** | **Per SSTable** (one summary per SSTable). Each table here is one SSTable, so *N* = 1. |
| **Level** | Both. Unit: upstream [`IndexSummaryTest.testLargeIndexSummary():128-155`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryTest.java#L128-L155) (reaches `:204`: 1,000,000 keys of 3,000 bytes, but asserts only that a summary exists) and [`testLargeIndexSummaryWithExpectedSizeMatching():162-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryTest.java#L162-L197) (reaches `:108`: interval 2); harness `IndexSummaryCapTest`, `IndexSummaryMovedLimitTest`. The unit configuration's partitioner is `ByteOrderedPartitioner` ([`test/conf/cassandra.yaml:18`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/conf/cassandra.yaml#L18)), so keys whose first 8 bytes are a big-endian counter are in summary order. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `sstable.selected_format` | `big` (the default, [`Config.java:373`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L373)) | BTI has no summary. Check `nb-*-big-Data.db` names. |
| `index_summary_resize_interval` | empty (null: redistribution off, [`DatabaseDescriptor.java:4136-4142`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4136-L4142), [`IndexSummaryManager.java:135-139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java#L135-L139)) | Redistribution would downsample or rebuild the summaries after the flush (shipped `60m`, [`conf/cassandra.yaml:941-947`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L941-L947)). Confirm `ResizeIntervalInMinutes` = −1 on `org.apache.cassandra.db:type=IndexSummaries`. |
| Table options | `min_index_interval = 1`, `caching = {'keys': 'NONE', 'rows_per_partition': 'NONE'}`, compaction `'enabled': 'false'` | Interval 1 makes 2 GiB reachable; a key-cache hit would skip the index scan ([`BigTableReader.java:266-275`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java#L266-L275)); a compaction would rebuild the SSTable. |
| `MAX_HEAP_SIZE`, `memtable_heap_space` | `24G`, `12GiB` | `big` holds 2.4 GB of keys in one memtable; the flush threshold (a third of the space, [`conf/cassandra.yaml:811`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L811)) is 4 GiB, so each table is one flush. |
| `commitlog_total_space` | `8192MiB` | A full commit log forces a flush mid-load. |
| `read_request_timeout`, `native_transport_timeout` | `60000ms`, `120000ms` | A read past `big`'s last sample scans up to 4,214 × 60 KB = 253 MB of index; the coordinator waits for the nearer of the two (the 2026-10-14 trap). |
| Byteman | agent `-javaagent:build/lib/jars/byteman-<ver>.jar=script:<harness>/summary-trace.btm,listener:true,port:9091` in `JVM_EXTRA_OPTS` of the `bin/cassandra` command, not exported | The deciding traces; the moved-limit rules are submitted on top. |
| Keys | exactly *K* random bytes from a seeded RNG (seed per table), `v int` = the row's index | Ranks are reproducible from the seed. |
| Clients | the harness only | Another table's flush would add `writer` lines; they are filtered by path. |

**Controls:** the idle node (gauge of the empty `ks` tables, `RssAnon`); table
`c32`, the `t32` data flushed with **no** rule (every key sampled, no `ERROR`);
`e30` for arm E.

**Reset between runs:** none between tables (each is its own SSTable, loaded,
flushed and read in turn). Between lifetimes 1 and 2: stop the node and wipe
`data/`, `commitlog/`, `saved_caches/`. Lifetimes 2 → 3 → 4 keep the data.

**Disk and memory.** `big`: `Data.db` and `Index.db` about 2.4 GB each,
`Summary.db` 2.15 GB, commit log 2.4 GB; the rest under 1 GB; about 10 GB in
all on `pc57`'s 57 GB. Native: about 2 GiB retained and a peak near 5.5 GB
during `big`'s flush; `pc57` has 251 GiB.

### 9c. Workload

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `IndexSummaryCapTest.java` | Unit tier U1, U2. Package `org.apache.cassandra.io.sstable.indexsummary` (to reach the package-private `defaultExpectedKeySize`, `getEntriesLength()`, `getEntries()`, `getOffsets()`), modelled on `IndexSummaryTest`. Reuses one *K*-byte array per run with the key index in its first 8 bytes (big-endian), so no 2 GB of random keys is generated; reads `entries` and `minIndexInterval` by reflection; captures the builder's log lines with a logback `ListAppender`. |
| `IndexSummaryMovedLimitTest.java` | Unit tier U3. `@RunWith(BMUnitRunner.class)` (as `HintServiceBytemanTest`), one test method per *L* with a method-level `@BMRule` carrying that *L*'s offset. |
| `summary-trace.btm` | Byteman, observing only: `writer` — `BigTableWriter$IndexWriter.<init>` at exit: `id=<System.identityHashCode($0.summary)> path=<$0.writer.getPath()>`; `init` — `IndexSummaryBuilder.<init>` at exit: `id`, `expectedKeys=$1`, `minIndexInterval=$2`, `effective=$0.minIndexInterval`, `entriesCapacity=$0.entries.capacity()`; `refused` — `IndexSummaryBuilder.maybeAddEntry(DecoratedKey,long,long,long)` `AT LINE 214`: `id`, `keysWritten`, `length=$0.entries.length()`, `entry=$1.getKey().remaining() + 8`; `built` — `IndexSummaryBuilder.build(IPartitioner,ReadableBoundary)` at exit: `id`, `count=$!.size()`, `entriesLength=$0.entries.length()`, `capacity=$0.entries.capacity()`, `minIndexInterval=$0.minIndexInterval`, `keysWritten`; `scan` — a per-thread counter reset at entry of `BigTableReader.getRowIndexEntry(PartitionPosition,Operator,boolean,SSTableReadsListener)`, incremented by `RowIndexEntry$Serializer.skip(DataInputPlus,Version)` when `callerEquals("getRowIndexEntry")`, printed at exit for keyspace `ks`/`ks2`: `file`, `skips`, `found=($! != null)`. |
| `moved-limit-8.btm`, `-32.btm`, `-128.btm` | `RULE moved limit <L>` / `CLASS org.apache.cassandra.io.sstable.indexsummary.IndexSummaryBuilder` / `METHOD getEntrySize(org.apache.cassandra.db.DecoratedKey)` / `AT EXIT` / `IF true` / `DO return $! + <offset>L`, with offset = 2,147,483,647 − *L*: 2,139,095,039 (8 MiB), 2,113,929,215 (32 MiB), 2,013,265,919 (128 MiB). |
| `load-keys.py` | Python driver: `load-keys.py <table> <N> <K> <seed>`, prepared `INSERT INTO ks.<table> (k, v) VALUES (?, ?)`, 32 concurrent; ~~writes `<table>.keys` (the keys in insertion order) for the read script~~ (*amended 2026-10-15:* key *i* is regenerated from the seed, so no key file is written). |
| `read-keys.py` | Regenerates the table's keys from its seed (amended 2026-10-15), computes each key's Murmur3 token (the driver's `cassandra.murmur3.murmur3`), sorts, and reads by rank: 5 ranks below *n*\* (0, *n*\*/2, *n*\* − 1, and two more) and the 5 highest ranks; `SELECT v FROM ks.<table> WHERE k = ?`; prints rank, found, `v`. |
| `cluster-run.py`, `unit-run.sh`, `Jmx.java` | The scripted cluster tier (one label per lifetime and table, `EXPECTED:` lines into `summary.txt`), the unit runner, and the JMX get client (reuse the `repair_session_space` harness's `Jmx.java`). |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.IndexSummaryTest
cp <harness>/IndexSummaryCapTest.java <harness>/IndexSummaryMovedLimitTest.java test/unit/org/apache/cassandra/io/sstable/indexsummary/
ant testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.IndexSummaryCapTest
ant testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.IndexSummaryMovedLimitTest

# cluster tier, per table <t> with <N> keys of <K> bytes (rule <L> submitted first, or none)
bin/cqlsh -e "CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE ks.<t> (k blob PRIMARY KEY, v int) WITH min_index_interval = 1 AND caching = {'keys': 'NONE', 'rows_per_partition': 'NONE'} AND compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};"
java -cp build/lib/jars/byteman-submit-<ver>.jar org.jboss.byteman.agent.submit.Submit -p 9091 -l <harness>/moved-limit-<L>.btm   # moved arm only
python3 <harness>/load-keys.py <t> <N> <K> <seed>
bin/nodetool flush ks <t>
bin/nodetool tablestats ks.<t>        # "Index summary off heap memory used", SSTable count
python3 <harness>/read-keys.py <t>
java -cp build/lib/jars/byteman-submit-<ver>.jar org.jboss.byteman.agent.submit.Submit -p 9091 -u <harness>/moved-limit-<L>.btm   # moved arm only
```

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — entries kept and `entriesLength` | `built` line of `summary-trace.btm` (joined to the table by `id` → `writer` path); unit: `summary.size()`, `getEntriesLength()`. | After each flush | Filter on the table's directory: system-table flushes write their own lines. |
| **Disallow evidence** | `grep -c 'Memory capacity of index summary exceeded' logs/system.log` (only [`IndexSummaryBuilder.java:214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L214) writes it; grep of `src/java` checked), counted before and after each flush; and the `refused` line with `keysWritten` and `length`. | Each flush | The text says "(2GiB)" also under a moved rule; the `refused` line's `length` gives the real figure. |
| **Real resource, native** | Table gauge `IndexSummaryOffHeapMemoryUsed` (`org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=<t>,name=IndexSummaryOffHeapMemoryUsed`, or `tablestats`); the `built` line's `capacity` (the allocated block). Real-limit arm: `grep RssAnon /proc/<pid>/status` idle, after the flush, and 5 min later. | After each flush | NMT and the `direct` pool MXBean cannot see `Native.malloc` (§7); `RssAnon` moves with the heap too, so it is support only. |
| **Real resource, disk** | `stat -c %s data/data/ks/<t>-*/nb-*-big-Summary.db` | After each flush | Exactly one SSTable per table (`ls … *-Data.db` count = 1), else the run is invalid for that table. |
| **Displaced cost** | `scan` lines: `skips` and `found` per read, joined to `read-keys.py`'s rank and result. | Each read | A key-cache hit gives `skips=0` for any rank: caching must be `NONE`. |
| **Second site** (arm E) | `grep 'is too low for' logs/system.log`; the `init` line (`effective`, `entriesCapacity`); JMX `IndexIntervals` on `org.apache.cassandra.db:type=IndexSummaries` ([`IndexSummaryManager.getIndexIntervals():165-173`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java#L165-L173)); at restart `grep 'Index summary file is corrupted' logs/debug.log` ([`BigSSTableReaderLoadingBuilder.java:262`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java#L262), `DEBUG`, on in the shipped `logback.xml`). | Each flush and start | The rebuild at start runs before the node serves clients; read the logs after `nodetool status` shows `UN`. |

### 9e. Running the scenarios

**Unit tier.** Commands in 9c. Run the values one at a time in one JVM and close
each builder before the next (each holds up to about 2 GiB of native memory, with
a peak near 5.5 GB). Record every assertion and printed value.

1. **U0** — upstream `IndexSummaryTest`, all methods. Record pass or fail (the
   two large tests are skipped when `CIRCLECI` is set; it must not be).
2. **U1, `:204` at the real limit** (interval 1, level 128, *N* keys of *K*
   bytes, then `prepareToCommit()` and `build()`): (*K*, *N*) = (3,000,
   1,000,000) as upstream, (30,000, 80,000), (65,535, 40,000); boundary pair
   (30,000, 71,563) and (30,000, 71,564); interval 2 with (30,000, 160,000).
   Predicted *n*\* = 713,924 · 71,563 · 32,764; the pair: 71,563 entries and no
   `ERROR`, then 71,563 entries and one `ERROR`; interval 2: 71,563 entries,
   refusal at `keysWritten` = 143,126. Assert: `size()` = min(*N*, *n*\*);
   `getEntriesLength()` = `size()` × (*K* + 8); after the trim
   `getEntries().size()` = `getEntriesLength()` and `getOffsets().size()` =
   4 × `size()`; `getMaxNumberOfEntries()` = `ceil(N / interval)`; exactly one
   `ERROR` event iff *N* exceeds the coverage; `entries.length()` and
   `entries.capacity()` unchanged across the first refused call and the next
   one; `getKey(size() − 1)` = the last accepted key; `binarySearch()` of the
   last key returns `−(size() + 1)`, i.e. the scan starts at the last entry.
3. **U2, `:108` at its boundary** (constructor only, no keys, then one key and
   `build()` for the interval): at the default *E* = 64, `expectedKeys` =
   29,826,161 → interval 1, `entries.capacity()` = 2,147,483,592, no `WARN`;
   29,826,162 → interval 2, capacity 1,073,741,832, one `WARN`. With *E* = 3,000
   (as upstream) and 1,000,000 → interval 2, capacity 1,504,000,000. Restore
   `defaultExpectedKeySize` after each.
4. **U3, the moved limit** (`IndexSummaryMovedLimitTest`, 1,000-byte keys,
   interval 1): with the rule at *L* = 8, 32, 128 MiB and *N* = 1.25 *n*\*,
   assert *n*\* = 8,322 · 33,288 · 133,152, `entriesLength` ≤ *L*, one `ERROR`;
   with offset 0, *N* = 41,610: all 41,610 kept, no `ERROR` (the rule changes
   nothing else).

**Before the cluster tier.**

1. Node yaml = the tag's plus the Hold-fixed lines; Byteman agent with
   `summary-trace.btm`; start; `nodetool status` `UN`, `statusbinary`
   `running`; `ResizeIntervalInMinutes` = −1.
2. **Instrument check** (not a reading): create `probe`, load 9,000 keys of
   1,000 bytes, submit `moved-limit-8.btm`, flush: one `writer`, `init`,
   `refused` (`keysWritten` 8,322) and `built` line with the probe's path,
   one `ERROR`; one read with a `scan` line. Unload the rule and drop `probe`. A
   silent instrument stops the run.

**Cluster tier, lifetime 1** (one node lifetime; tables in this order, each:
create, rule or none, load, flush, readings of 9d, reads, unload):

1. **Control** — idle readings; then `c32` with no rule.
2. **Real limit** — `big`, no rule: load 40,000 keys of 60,000 bytes (the load
   must write 2.4 GB; check `nodetool tablestats` shows no flush before the
   manual one), flush, readings, `RssAnon` three times, reads (5 below, 5 above).
3. **Moved limit** — `t8`, `t32`, `t32a`, `t32b`, `t32c`, `t128` with their rules
   (scenario A: `t32a`, `t32b`; scenario B: `t32`, `t32c`, and `t8`, `t128` at
   1.25 *n*\*).
4. **Restart check** — stop, start with the same yaml, read the debug log and
   `big`'s gauge, one read below `big`'s *n*\*. Stop.

**Cluster tier, arm E** (wipe; property set):

1. **Lifetime 2** — start with `-Dcassandra.index_summary_expected_key_size=65536`;
   keyspace `ks2`, tables `e41` (41,610 keys) and `e30` (30,000 keys) of 1,000
   bytes, same options, no moved rule; flush each; readings, `IndexIntervals`.
   Stop.
2. **Lifetime 3** — start with the property again; read the logs and traces of
   the start-up rebuild, `IndexIntervals`, gauges. Stop.
3. **Lifetime 4** — start **without** the property; the same readings. Stop,
   start once more, check `e41` loads without a rebuild. Stop and leave the node
   clean.

**Record for stage 4:** the yaml diff and JVM options of each lifetime, the
rule in force per table, the exact commands, and for every table the raw `writer`,
`init`, `refused`, `built` and `scan` lines, the `ERROR`/`WARN` counts, the gauge,
the `Summary.db` size and the `RssAnon` readings.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — found 2026-09-22 by the capacity-word pass reading the source directly and recorded in `predicted-positive.md` as `Integer_MAX_VALUE (index summary)` (`maybeAddEntry():204`); stage 1/2 also surfaced the line as band-A2 row `IndexSummaryBuilder.java:204#1`, cited as already recorded by the band-A2 pass. The second site, band-A2 row `IndexSummaryBuilder.java:108#1` (feed `3a`), was joined to it by that pass (2026-09-29, `predicted-negative.md` batch "band A2"). Write-up queue item 9. |
| **Filed by / Date** | Claude (AI long path), 2026-10-15. |
| **Line numbers checked** | 2026-10-15, every cited line against the local clone at `cassandra-5.0.9` (`git describe --tags`), by a script that printed each cited line. |
| **Escape hatch / Target-3 note** | No path lets a summary pass the bound, and the disallow loses no data (§6b). Target-3 notes: (1) **format-scoped**: a BIG-only structure, so BTI tables never reach it; (2) the second site's raised interval is **persisted** and disagrees with the table's, so every restart rebuilds that summary from the whole index file (derived; arm E tests it); (3) the rebuild paths **keep the untrimmed block** while the gauge and the redistribution's accounting count only the length (derived, §7); (4) the `ERROR` line advises a setting that does not exist (`min_sampling_level`; §11). |
| **Stage-4 feedback** | **Closed 2026-10-15: unit Confirmed; cluster Confirmed (§9a row 1); no run 2** ([results](../../stage4-runtime-verification/results/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE--guided.md); uncommitted). Step-0 audit Ready after amendments (§9 `82abfe04…`, §9a `568eb613…` unchanged; keys regenerated from seeds, a private clone). Run 1 on `pc57`: every figure of §9a's table observed exactly — `big` at the real limit 35,786 entries, `entriesLength` 2,147,446,288, gauge 2,147,589,432, `Summary.db` 2,147,709,464, `RssAnon` +2.17 GB; moved limits 8,322 · 33,288 · 133,152; one refusal and one `ERROR` at `keysWritten` = *n*\*; reads past the last sample found after *r* − *n*\* + 1 skips; `big` reloads after a restart without a rebuild (the offsets past 2^31 − 1 wrap back correctly); arm E: interval 2 and a 1,363,642,920-B reservation at 41,610 expected keys, interval 1 at 30,000. **Notes for stage 3 (not applied):** (1) a summary rebuilt at start-up keeps the loader's **untrimmed** reservation (`BigSSTableReaderLoadingBuilder` builds without `prepareToCommit()`): 1,364,888,256 B of capacity for 20,971,440 B of entries with the property, 47,979,648 B for 41,942,880 B without — §7's derived note is observed, and its size can be 65× the summary; (2) the builder's `build()` runs twice per flush (two identical results); (3) ruling (3): this run moved the limit with a Byteman offset on `getEntrySize(DecoratedKey)` and checked it against the real limit at the unit tier (U3 vs U1); one runbook defect (load client's token hashing), fixed in the harness. |
| **Notes** | **Corrections to the queue notes (`predicted-positive.md` item 9 and its "Notes on these four"):** (1) the second site's writers are at `:126-127`, not `:125-126` (`:125` scales the estimate by the sampling level); (2) "both branches build the builder; the divergence is retained size" holds for `:108` only — at `:204` the disallow writes nothing, and because the next sample position is not advanced, **no later key is sampled**: one refusal per summary, and the rest of the SSTable is uncovered; (3) the uncovered keys stay readable through a linear scan of the index file from the last sample (§6b), so the disallow trades memory for reads, as in `column_index_cache_size`; (4) the raised interval of `:108` is stored in the summary, with the restart-rebuild consequence above. Naming: §4 (a type bound has no declared Cassandra variable; the JDK constant is qualified as `Integer_MAX_VALUE`). Not settled here: `IndexSummaryRedistribution.java:341` (+ `:258`), `undetermined.md` §5 (§11). |

---

## 11. Notes

- **Why a type bound passes Rule 2 here when three others were refused.** The
  band-A2 batch refused [`NativeCell.java:100`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/NativeCell.java#L100), [`OffHeapBitSet.java:43`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java#L43) and
  [`DataOutputBuffer.java:152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L152) as per-item type bounds: each guards one
  allocation and throws. This one caps a structure that grows with the data
  (keys per SSTable), and its disallow withholds further growth and continues,
  so the maximum bytes a summary can hold is set by the bound (`predicted-negative.md`
  records the same contrast).
- **The `ERROR` line's advice is wrong for 5.0.9.** It says "you should
  increase min_sampling_level", but no setting of that name exists; a grep of
  `src/java` and `conf` finds it only in this string. The setting that makes
  the summary sparser is the table's `min_index_interval` (raise it).
- **`undetermined.md` §5 item 1 ([`IndexSummaryRedistribution.java:341`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java#L341), with
  [`:258`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java#L258)) is a different constraint**, `index_summary_capacity`: the pool that
  bounds the total over all SSTables, enforced by periodic redistribution. It is
  not a site of this case and is not settled here. One observation for whoever
  settles it: the redistribution acts only on summaries already built, by
  downsampling them or rebuilding them through `IndexSummaryBuilder`
  (`cloneWithNewSummarySamplingLevel()`,
  [`IndexSummaryRedistribution.java:285`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java#L285)),
  so a rebuilt summary also passes this case's check; and its budget arithmetic
  uses `getOffHeapSize()`, which omits an untrimmed block's spare capacity (§7).
- **The 32-bit wrap on disk is reversible** (derived). `Summary.db` stores each
  offset plus the offsets' total size as an `int`
  ([`IndexSummary.java:411`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L411)),
  which can pass 2^31 − 1 for a summary near the bound; the load subtracts the
  same total and casts back to `int`
  ([`:475`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L475)),
  which undoes the wrap. The real-limit arm's restart step tests it.
- **With interval 1 there are no early-open boundaries at all** (derived): the
  readable-boundary branch needs a key that is not sampled
  (`keysWritten + 1 == nextSamplePosition`, [`:218`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L218)), and at interval 1 every
  key is. Irrelevant to the cap; noted because §5 mentions the boundaries.
