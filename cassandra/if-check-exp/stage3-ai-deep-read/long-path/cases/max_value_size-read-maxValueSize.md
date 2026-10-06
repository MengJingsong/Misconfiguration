# max_value_size — deserialized value

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MAX_VALUE_SIZE-READ-MAXVALUESIZE |
| **Constraint** | `max_value_size` — a **configuration entry** ([`Config.max_value_size:310`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L310), `IntMebibytesBound`, default `256MiB`; renamed from `max_value_size_in_mb`, which is still read, [`Config.java:309`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L309)). The shipped [`conf/cassandra.yaml:1864`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L1864) has it commented out. `DatabaseDescriptor.getMaxValueSize()` computes the value **on every call** from the config object, so nothing is frozen at start-up; but no code on a running node calls the setter (§4), so a change is **restart-only** in practice. |
| **Enforcement pattern** | **(c)** — a guard clause that throws before an allocation that is not inside a branch. **It dominates that allocation for every production caller of `AbstractType.read()`**: all four call sites pass the configured limit, and the one overload that passes `Integer.MAX_VALUE` has no caller outside tests (§5). **It does not dominate the same kind of allocation made by sibling read primitives**, which have no limit at all (§5), and it is a **read-side check only**: nothing compares a value with it when the value is written. |
| **Capacity check** | [`AbstractType.read():594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L594) — `l > maxValueSize`, where `l` is the length decoded from the stream at [`:590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L590) and `maxValueSize` is the method's argument. There is no second comparison: the four call sites of §5 all pass the same limit into this one line. |
| **Decision point** | the same statement: the `if` at `:594` and its throw at [`AbstractType.read():595-597`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L595-L597); the allow outcome falls through to the allocation. Pattern (c): there is no flag or return value. |
| **Allocation site** | [`AbstractType.read():599`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L599) → [`ByteArrayAccessor.read():100-105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/ByteArrayAccessor.java#L100-L105) (cells are read with this accessor, `new byte[length]` at `:102`) or [`ByteBufferAccessor.read():100-103`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/ByteBufferAccessor.java#L100-L103) → [`ByteBufferUtil.read():444-452`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ByteBufferUtil.java#L444-L452) (`new byte[length]` at `:449`). **The array is allocated at its full size before any byte is read**, then filled by `readFully`. |
| **Related cases** | [`max_mutation_size-validateSize-MAX_MUTATION_SIZE.md`](max_mutation_size-validateSize-MAX_MUTATION_SIZE.md) — the write-side per-entry cap. At stock settings it (16 MiB) and the protocol-v4 frame cap (16 MiB) are far below this limit's 256 MiB, so a client write is refused there long before this check could see it (§8); the two bound the same bytes from opposite sides and disagree when `max_value_size` is the smaller. **Not filed:** the `column_value_size_warn_threshold` and `column_value_size_fail_threshold` guardrails, a write-time CQL check on a related quantity, off by default; the yaml says the two differ ([`conf/cassandra.yaml:2143-2146`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L2143-L2146)). |

```java
// AbstractType.read():582-601 — the capacity check, its two outcomes and the allocation it guards
public <V> V read(ValueAccessor<V> accessor, DataInputPlus in, int maxValueSize) throws IOException
{
    int length = valueLengthIfFixed();

    if (length >= 0)
        return accessor.read(in, length);                        // fixed-length type: no comparison, :586-587
    else
    {
        int l = in.readUnsignedVInt32();                         // usage side: a length decoded from the data, :590
        if (l < 0)
            throw new IOException("Corrupt (negative) value length encountered");

        if (l > maxValueSize)                                    // <-- capacity check, :594
            throw new IOException(String.format("Corrupt value length %d encountered, as it exceeds the maximum of %d, " +
                                                "which is set via max_value_size in cassandra.yaml",
                                                l, maxValueSize));   // disallow, :595-597

        return accessor.read(in, l);                             // allow: allocates l bytes, :599
    }
}
```

```java
// Cell.Serializer.deserialize():339 — the hot call site; the limit is read from config at every cell
value = header.getType(column).read(accessor, in, DatabaseDescriptor.getMaxValueSize());
```

```java
// ByteBufferUtil.read():444-452 — reached from :599; the array is made before the bytes are read
byte[] buff = new byte[length];
in.readFully(buff);
return ByteBuffer.wrap(buff);
```

## 2. Context

Cassandra stores and ships values as length-prefixed byte strings: in an SSTable, in a commit-log entry and in an internode message, a value is written as its length followed by its bytes. To read one back, the code decodes the length, allocates an array of that size and then reads the bytes into it. The length comes from the data, so when the data is damaged (a flipped bit in an SSTable, a torn commit-log tail, a peer sending garbage) the decoded length can be anything up to about two billion, and the node would try to allocate that much heap before it found out that the bytes are not there. This check is the sanity bound on that step: when the decoded length is larger than a configured maximum, the read is abandoned with an exception before the array is allocated. The default maximum is 256 MiB, deliberately large; the configuration file calls it a "safety measure to detect SSTable corruption early", not a limit on what clients may store. Two consequences, worked out below: the check sits on the **read side only**, so a value above the limit can still be written, acknowledged and held in memory; and its refusal is handled by the callers traced below as "this data is corrupt", not as "this request is too big".

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `marshal` — type system and value (de)serialization (`db/marshal`); the deserializers that call it are in `db/rows`, `db` and `db/commitlog` |
| **One-line role** | The `db/marshal` package defines Cassandra's data types and how each type's values are compared, validated and read from or written to a byte stream. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes — per item, not cumulative.** It compares the length of one value, decoded from the stream, against a configured byte ceiling and refuses the read when the length is larger. It keeps no running total, so it bounds the **size of one array**; any node-wide effect needs a multiplier (§8). The usage side is a number read from data, not a measured consumption. |
| **Usage-side operand** | `l`, [`AbstractType.read():590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L590). The decoder returns an `int` and throws the unchecked `VIntOutOfRangeException` for anything that does not fit ([`VIntCoding.readUnsignedVInt32():269-272`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/vint/VIntCoding.java#L269-L272), [`checkedCast():542-547`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/vint/VIntCoding.java#L542-L547)), so `l` lies in 0 to 2³¹−1 or is negative, and a negative one is refused first ([`:591-592`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L591-L592)). Only **variable-length** types reach this line: a type whose [`valueLengthIfFixed()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L490-L493) is not negative takes the fixed branch at `:586-587`, sized by the type (for example 4 bytes for `int`; a vector of fixed-length elements, [`VectorType.java:94-96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/VectorType.java#L94-L96), is sized by its schema), with no comparison. |
| **Limit-side operand** | the parameter `maxValueSize` ([`AbstractType.read():582`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L582)), supplied by the caller (§5). |
| **Limit type** | **Configuration entry**, in whole mebibytes, validated to 1–2047 MiB, read live on every call. |

**Limit initialization path** (declare → validate → read → pass → compare):

1. [`Config.max_value_size:310`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L310) — declared, default `256MiB` (the entry is `@Replaces` of `max_value_size_in_mb`, [`:309`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L309)).
2. [`DatabaseDescriptor.applySimpleConfig():944-948`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L944-L948) — **validated**: zero MiB fails start-up with `max_value_size must be positive`, and 2048 MiB or more with `max_value_size must be smaller than 2048, but was …`.
3. [`DatabaseDescriptor.getMaxValueSize():1928-1931`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1928-L1931) — returns `conf.max_value_size` in bytes as an `int`, **computed at each call**; nothing caches it. The setter [`setMaxValueSize():1933-1937`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1933-L1937) exists (whole mebibytes only), and a search of `src/java` for `setMaxValueSize` finds only its definition: the three upstream test classes that call it are the only callers (§9b), and no JMX operation, `nodetool` command or other path reaches it. On a running node the value is therefore fixed by the yaml, and a change needs a restart.
4. The four call sites of §5 pass `DatabaseDescriptor.getMaxValueSize()` as the argument — the limit is read **at the moment each value is decoded**.
5. [`AbstractType.read():594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L594) — compared.

**Naming note (Target 1).** The constraint is named after the configuration entry; the stem's `read` is the method that encloses the comparison and `maxValueSize` is the operand as written there (README §6.1). The message the check throws names the same entry.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`AbstractType.read():594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L594) |
| **Verdict** | Pattern (c): the guard is the `if` and its `throw`; there is no flag, enum or return value. When `l > maxValueSize` it throws a plain `IOException` whose message prints both operands (below); otherwise control falls through to the allocation. |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `0 <= l <= maxValueSize` | `accessor.read(in, l)` allocates `l` bytes and reads them |
| **Disallow** | `l > maxValueSize` | `IOException`; **no array is allocated, nothing is counted or logged here, and the stream is left just after the length** |

```java
// allow: AbstractType.read():599
return accessor.read(in, l);
```

```java
// disallow: AbstractType.read():595-597
throw new IOException(String.format("Corrupt value length %d encountered, as it exceeds the maximum of %d, " +
                                    "which is set via max_value_size in cassandra.yaml",
                                    l, maxValueSize));
```

### Who calls it, and with which limit

`AbstractType.read()` is reached through three public entry points: [`read()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L582-L601) itself, [`readBuffer(in, maxValueSize):572-575`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L572-L575) and [`readArray(in, maxValueSize):577-580`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L577-L580). Every call in `src/java` passes `DatabaseDescriptor.getMaxValueSize()`:

| # | Call site | What it reads | Reached by | Can a client write a value there above 1 MiB (the smallest limit)? |
|---|---|---|---|---|
| 1 | [`Cell.Serializer.deserialize():339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/Cell.java#L339) | a **cell's value** | every cell materialized from an SSTable, from a mutation (internode, commit-log replay, hints), from a read response or from a stream; its only two callers are [`UnfilteredSerializer.readSimpleColumn():652`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L652) and [`readComplexColumn():685`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L685) | **Yes** — a cell value can be as large as the write-side caps allow (§8). **The only site a client can drive past the smallest limit.** |
| 2 | [`ClusteringPrefix.Serializer.deserializeValuesWithoutSize():517`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L517) | a clustering value or a slice bound's value | [`Clustering.java:177`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Clustering.java#L177) and [`ClusteringBoundOrBoundary.java:138`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringBoundOrBoundary.java#L138): rows in mutations and responses, slices, names filters, paging state | No for a row write: each clustering value is limited to 65,535 bytes, in total too ([`ClusteringPrefix.validate():272-288`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L272-L288), called at [`ModificationStatement.java:815`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java#L815)); not traced for range-delete bounds |
| 3 | [`ClusteringPrefix.Deserializer.deserializeOne():674`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ClusteringPrefix.java#L674) | a clustering value | the SSTable scan: [`UnfilteredDeserializer.java:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/UnfilteredDeserializer.java#L58) | No (as 2) |
| 4 | [`SinglePartitionReadCommand.Deserializer.deserialize():1352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java#L1352) | the **partition key** of an inbound single-partition read command | deserializing an inbound read command ([`ReadCommand.java:1190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L1190)) | No: a partition key is limited to 65,535 bytes ([`Validation.validateKey():51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Validation.java#L51), called at [`ModificationStatement.java:781`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java#L781) and [`:802`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java#L802)) |
| — | [`AbstractType.readBuffer(in):567-570`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L567-L570) — the overload that passes `Integer.MAX_VALUE` | any | **no caller in `src/java`**; callers are [`AbstractTypeTest.java:641`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/marshal/AbstractTypeTest.java#L641) and [`EmptyTypeTest.java:67`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/marshal/EmptyTypeTest.java#L67) | — |

So for any limit a node can be configured with (1 MiB or more), **only the cell-value site can fire on data a client legitimately wrote**; sites 2 to 4 fire only on damaged or crafted input, because the write path already refuses keys, and the clustering values of row writes, above 64 KiB.

**Skipped, not read.** When a column is not fetched, [`UnfilteredSerializer.readSimpleColumn():658`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L658) (and [`:727`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L727) for complex columns) calls [`Cell.Serializer.skip():378-403`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/Cell.java#L378-L403), which passes over the value with [`AbstractType.skipValue():603-610`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L603-L610) and allocates nothing; a column that is fetched but not queried takes the same step inside [`Cell.deserialize():331-334`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/Cell.java#L331-L334). Neither compares the length with the limit, which is consistent: **the check guards the array, not the byte stream.** A query that skips a column therefore succeeds where one that reads it fails.

### Does the guard dominate the allocation?

**For `AbstractType.read()` and every production caller, yes.** The allocation at `:599` is reachable only after `:594`, and the four call sites above pass the configured limit. (The pending note's reading that `readBuffer(in)` "disables the guard for its callers" is true of the overload and false of production: it has no production caller. See §10.)

What the guard does **not** dominate:

- **The same allocation made by sibling primitives.** `ByteBufferUtil` has three more ways to turn a length field into an array, with the same shape (decode a length, `new byte[length]`, `readFully`) and **no limit**: [`readWithVIntLength():382-389`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ByteBufferUtil.java#L382-L389) (24 call sites in `src/java`), [`readWithLength():371-379`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ByteBufferUtil.java#L371-L379) (5 call sites; a 32-bit length) and [`readWithShortLength():423-426`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ByteBufferUtil.java#L423-L426) (a 16-bit length, so at most 64 KiB). All of them end in the same [`ByteBufferUtil.read():444-452`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ByteBufferUtil.java#L444-L452). A sample of the unguarded call sites, found by search and not complete:

  | Call site | What it reads | Note |
  |---|---|---|
  | [`UnfilteredRowIteratorSerializer.deserializeHeader():199`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredRowIteratorSerializer.java#L199) | the **partition key** of every partition in a mutation or read response | the same object is guarded at site 4 above |
  | [`CollectionType.CollectionPathSerializer.deserialize():370`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/CollectionType.java#L370) | the **cell path** (a map key or set element) of the cell whose value site 1 guards | |
  | [`ReadResponse.deserialize():338`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadResponse.java#L338) | a replica's whole serialized read-response payload | bounded in practice by the internode message size |
  | [`Batch.readEncodedMutations():157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/Batch.java#L157) | each serialized mutation of a batchlog entry | |
  | [`StatsMetadata.java:648-649`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/metadata/StatsMetadata.java#L648-L649) | the first and last key in an SSTable's stats component | |
  | [`IndexSummary.java:494-495`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java#L494-L495) | the first and last key in an index summary (`readWithLength`, 32-bit length) | |
  | [`CacheService.java:408`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java#L408) | a key in a saved row-cache file (`readWithLength`) | |

  A damaged length in any of these allocates up to 2 GiB with no comparison. They are not the check's concern, but they decide what "this limit bounds the array allocated from a length field" is worth: it bounds **four** of the thirty-odd places that do it.
- **The write side.** [`DatabaseDescriptor.getMaxValueSize()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1928-L1931) has no caller outside the four deserializers above; nothing compares a value with it when it is written. A value above the limit is accepted by CQL (the transport copies a bound value into a heap array of its own size, [`CBUtil.readValue():443-450`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CBUtil.java#L443-L450); it first checks the length against the bytes actually in the frame, [`CBUtil.readRawBytes():664-670`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CBUtil.java#L664-L670), and never against this limit), applied to the memtable, written to the commit log and flushed to an SSTable (the upstream `SSTableWriterTest.testValueTooBigCorruption` relies on exactly this: its writer accepts a value above the limit, §9b). The guard meets it **only when it is read back** from disk, from a message or from the commit log. A read served from the memtable never deserializes a value, so it never meets the guard.

## 6. Code path

### 6a. Allow path → object creation

1. [`UnfilteredSerializer.readSimpleColumn():647-655`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L647-L655) — a consumer reads a row and, for a fetched column, calls `Cell.serializer.deserialize()` (`:652`). (Complex columns: [`readComplexColumn():662-690`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L662-L690).)
2. [`Cell.Serializer.deserialize():307-348`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/Cell.java#L307-L348) — reads the flags, timestamp and path; at `:331` skips the value when only liveness is needed, otherwise
3. [`Cell.deserialize():339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/Cell.java#L339) — calls `read(accessor, in, DatabaseDescriptor.getMaxValueSize())`; the limit is read here, from config ([`getMaxValueSize():1928-1931`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1928-L1931)).
4. [`AbstractType.read():584-590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L584-L590) — `valueLengthIfFixed()` is negative for a variable-length type such as `blob` or `text`; the length `l` is decoded.
5. [`AbstractType.read():591-594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L591-L594) — `l` is not negative and not above the limit: the guard is not taken.
6. [`AbstractType.read():599`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L599) → [`ByteArrayAccessor.read():100-105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/ByteArrayAccessor.java#L100-L105) — **object creation:** `new byte[l]` (`:102`), then `readFully`. (Through `ByteBufferAccessor`: [`ByteBufferUtil.read():444-452`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ByteBufferUtil.java#L444-L452), `new byte[length]` at `:449`.)
7. [`Cell.deserialize():348`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/Cell.java#L348) — the cell is built around the array and handed to the row builder.

The other sites differ only in what surrounds the call: `readArray()` for a clustering value (a `byte[]` directly) and `readBuffer()` for the partition key (a `ByteBuffer` wrapping the array).

### 6b. Disallow path effect

1. [`AbstractType.read():595-597`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L595-L597) throws `IOException`. **Nothing else changes:** no array is allocated (`:599` is after the throw), no metric moves and no log line is written at the check (a search of `src/java` for the message text finds only this throw). The message, which prints both operands, is the only evidence.
2. **What the caller does depends on the consumer; each consumer traced here reads the exception as corruption:**
   - **SSTable reads** — client reads, scans and compaction. [`UnfilteredSerializer.deserializeRowBody():627-632`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L627-L632) unwraps the exception to an `IOException` intact. The iterator turns it into a `CorruptSSTableException` and calls `sstable.markSuspect()`: single-partition reads in [`AbstractSSTableIterator.hasNext():394-411`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/AbstractSSTableIterator.java#L394-L411) and [`next():415-433`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/AbstractSSTableIterator.java#L415-L433), scans in [`SSTableSimpleIterator.computeNext():88-98`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleIterator.java#L88-L98) (an `IOError`) caught at [`SSTableIdentityIterator.hasNext():171-195`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableIdentityIterator.java#L171-L195). Three effects follow.
     1. **The read fails.** [`StorageProxy.LocalReadRunnable.runMayThrow():2243-2253`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2243-L2253) reports `RequestFailureReason.UNKNOWN` to the response handler (the client sees a `ReadFailure`) and rethrows. When the task runs on an executor, the exception reaches the executor's default handler, [`JVMStabilityInspector.uncaughtException()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutionFailure.java#L66-L67), which calls [`inspectDiskError():97-103`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/JVMStabilityInspector.java#L97-L103) → [`DefaultFSErrorHandler.handleCorruptSSTable():44-58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/DefaultFSErrorHandler.java#L44-L58): under `disk_failure_policy` `die` or `stop_paranoid` the node **stops its transports**; under `stop` (the shipped yaml, [`conf/cassandra.yaml:471`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L471)) or `ignore` (the [`Config.java:124`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L124) default) nothing more happens.
     2. **The SSTable is marked suspect** ([`SSTableReader.markSuspect():1031-1037`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java#L1031-L1037)) and the compaction strategies drop suspect SSTables from their candidates ([`filterSuspectSSTables():235-244`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/AbstractCompactionStrategy.java#L235-L244); for example [`SizeTieredCompactionStrategy.getMaximalTask():207`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java#L207)), and so does [`ColumnFamilyStore.withAllSSTables():2975`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2975), the entry point of whole-table SSTable operations. So **the file is not compacted again**: its bytes, and any tombstones or shadowed data in it, stay on disk. The flag lives in memory, and the only method that clears it is [`unmarkSuspect():1040-1043`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java#L1040-L1043), which nothing in `src/java` calls; a restart builds a new reader without it, and the next compaction that reads the value fails again. A compaction that reads the value before the flag is set fails the same way as a read.
     3. **Other partitions in the same SSTable stay readable.** A search of `src/java` finds `isMarkedSuspect()` and `filterSuspectSSTables()` called only from the compaction code and from `ColumnFamilyStore.withAllSSTables()`; no read path consults the flag, although the trace message at [`:1034`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java#L1034) says "excluded from reads". Source-derived; §9 checks it.
   - **Inbound message** (an internode mutation, or a read command carrying a key). [`InboundMessageHandler.processSmallMessage():156-198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L156-L198) catches `Throwable` at [`:176-181`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L176-L181): it calls `JVMStabilityInspector.inspectThrowable()` and `callbacks.onFailedDeserialize()`, logs `unexpected exception caught while deserializing a message` at ERROR, releases the capacity, and carries on with the next message: **the message is dropped and the connection stays open**. [`InboundMessageHandlers.onFailedDeserialize():247-256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandlers.java#L247-L256) counts the error and [`InboundSink.fail():81-91`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundSink.java#L81-L91) sends the sender a failure response (reason `UNKNOWN`) when the message's header asks for a failure callback, so a coordinator hears of it at once instead of timing out. Large messages take the same catch ([`:373-377`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L373-L377)).
   - **Commit-log replay at start-up.** [`CommitLogReader.readMutation():431`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReader.java#L431) deserializes each entry, so a cell above the limit throws here. The catch at [`:452-473`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReader.java#L452-L473) saves the entry to a temporary file and reports an **unrecoverable** error (`permissible = false`) to [`CommitLogReplayer.shouldSkipSegmentOnError():533-546`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L533-L546). Unless `-Dcassandra.commitlog.ignorereplayerrors=true`, [`CommitLog.handleCommitError():576-596`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L576-L596) applies `commit_failure_policy`; under `stop`, which is both the shipped value ([`conf/cassandra.yaml:488`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L488)) and the default ([`Config.java:125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L125)) it stops the transports and returns false, so replay throws `CommitLogReplayException`. [`CassandraDaemon.setup():343-350`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CassandraDaemon.java#L343-L350) wraps it and [`activate():746-759`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CassandraDaemon.java#L746-L759) ends in `exitOrFail(3, "Exception encountered during startup", e)`: **the node does not start.** With the override flag the entry is skipped and replay goes on, so its data is **lost**. **Replay is guarded**, unlike `max_mutation_size`'s: a value written under a higher limit, and still in the commit log after a crash, blocks a restart under a lower one.
   - **Hints replay, streaming, batchlog replay and read repair** reach `Cell.deserialize()` too; what each does with the exception is **not traced**.
3. **Not a block, a retry or a hint.** No consumer waits, retries with a larger limit or hints; a value above the limit is refused every time it is read. A write is never refused: the guard is not on its path (§5).
4. **If the check were absent.** `ByteBufferUtil.read()` and `ByteArrayAccessor.read()` allocate `new byte[l]` **before** reading (`:449`, `:102`), so a damaged length of up to 2³¹−1 would be allocated at full size before the short read is noticed; whether that ends in an `OutOfMemoryError` depends on the heap. Derived from the source; §9 shows the allocation with an unguarded sibling primitive (the same step) and does not run the unguarded `AbstractType` case.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | a heap `byte[]` of `l` bytes (`ByteArrayAccessor`), or a heap `ByteBuffer` wrapping one (`ByteBufferAccessor`); then the cell, clustering or key built around it. |
| **Resource consumed** | **Heap bytes**, `l` plus the array header, about 16 bytes (not measured, inferred). Transient for a read, retained while the cell lives (until a read response is sent or a compaction has written the row). |
| **Rough sizing** | `l`, at most `max_value_size`: 256 MiB at the default, 2047 MiB at the largest setting. |
| **Lifetime / release** | garbage collection once the cell is no longer referenced; nothing in this path releases it explicitly. |

## 8. Maximum memory/disk bound

`max_value_size` caps **the heap array made for each variable-length value that a deserializer reads**, and nothing else. A length above it is refused before the array exists, so the largest `byte[]` that can come out of a length field at the four guarded sites is the limit (plus the array header), and raising or lowering the limit moves that maximum **one for one**, anywhere from 1 MiB to 2047 MiB. A value above the limit is not truncated: the read that meets it fails as a whole (§6b).

It bounds none of the totals, and not the storage of the same bytes:

- **Per value, not per row or request.** A row of several large cells, or a read that materializes many rows, allocates their sum. The transient heap this path admits is `max_value_size × N`, N being the values deserialized at once (read-stage, mutation-stage and compaction threads, and every large cell of a row), or the transport and queue caps if they are smaller. Not tested; §9 uses one value at a time.
- **Not the write path.** The transport copies a bound value into a heap array of its own size ([`CBUtil.readValue():443-450`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CBUtil.java#L443-L450)), the memtable holds it, the commit log serializes it and a flush writes it, whatever the limit (§5). The caps that act on a write are `max_mutation_size`, the transport's frame and message caps, and the in-flight request caps. So the limit does **not** bound the heap one large value occupies in a memtable; it bounds what **re-reading** it can allocate.
- **At stock settings a client cannot reach it.** The default 256 MiB is above `max_mutation_size` (16 MiB at the shipped 32 MiB segments) and above the protocol-v4 frame cap ([`Config.native_transport_max_frame_size:285`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L285), 16 MiB), so no client write can be large enough to meet it, and at the default it can fire only on damaged data. That is what the yaml says it is for ([`conf/cassandra.yaml:1860-1864`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L1860-L1864)). The yaml's note on the frame cap, "you may want to adjust max_value_size accordingly" ([`conf/cassandra.yaml:1042`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L1042)), is the operator-facing consequence: raise the write-side caps above this limit and clients can write what the node cannot read back.
- **Lowering it below what is stored makes stored data unreadable.** Each consumer traced in §6b treats a value above the limit as corruption. A read of that value fails, an SSTable that holds it is marked suspect and is not compacted again (its disk bytes stay), and a commit-log entry that holds it stops the node from starting. So the limit also moves **how much disk is held by data that can no longer be compacted away**, and whether a restart succeeds. These are source-derived effects (§6b); §9 checks the read, the compaction and the replay.

The limit derives from nothing and nothing derives from it: a search of `src/java` finds no other limit computed from `getMaxValueSize()`.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test finds, at several values of `max_value_size`, the largest variable-length value that can be read back and the first one that cannot, and checks that the refused one allocates no array. The unit tier calls `AbstractType.read()` and the real deserializers directly and measures the bytes the thread allocates; the cluster tier writes values around the limit to a node, flushes, and reads them back, with the array sizes requested at the allocation site traced by Byteman. Three arms check effects §6b derives from the source: a failed read leaves other values readable, a compaction of the SSTable fails and leaves the file, and a replay under a lower limit stops the node starting. **Run so far:** none. Written in this layout on 2026-10-06; not yet audited (stage-4 README, step 0).

### 9a. Procedure and conclusions

**Testability:** config, **restart-only on a node** — `max_value_size` in `cassandra.yaml`; no setter, JMX operation or `nodetool` command reaches it on a running node (§4). **Live-settable in a unit JVM:** `DatabaseDescriptor.setMaxValueSize(int)`, whole mebibytes only, so the unit tier needs one JVM, not one per value. No patched build is needed. The valid range is 1 to 2047 MiB. A client can write a value above the limit only when the limit is below the write-side caps: at a node's stock settings (16 MiB `max_mutation_size`, 16 MiB protocol-v4 frame cap) that means limits below about 15 MiB. **The default of 256 MiB can be exercised only by the unit tier**; on a node it is a control that shows a client cannot reach it.

**Claim under test:** `max_value_size` bounds the heap array allocated for each variable-length value a deserializer reads. `AbstractType.read()` throws `IOException` (`Corrupt value length …`) before it allocates when the decoded length exceeds the limit, so the largest value that can be read back from disk, a message or the commit log is the limit, and the knob moves it one for one. It does not bound what is stored: a value above the limit is accepted on write and held in the memtable (§5, §8). The refusal is handled as corruption: the read fails, the SSTable is marked suspect and not compacted again, and a commit-log replay stops the node starting (§6b).

**How this verifies the hypothesis** (a restatement of the claim, procedure, prediction and conclusions in this section; it adds none):

- **Hypothesis:** the constraint caps the heap array of each deserialized value, and a value over the limit is refused before the array is allocated; the refusal is a read-time failure, not a write-time one.
- **Test:** vary `max_value_size` over four values in the unit tier (1, 4, 8 MiB and the default 256 MiB) and three on a node (1, 4 and 8 MiB; the default only as a control). At each, find the largest accepted length and the one after it. Read the bytes the thread allocates (unit) or the array sizes requested at the allocation site (node), the guard's message, and what a client gets after a flush.
- **Logic:** (1) the limit read back from the first refusal equals the value set, else the run is invalid. (2) A length of exactly the limit passes the guard and allocates its array; one byte more is refused with the guard's message and allocates nothing: usage **stops at the limit**. (3) On the node the largest value read back after the flush is in the ratio 1 : 4 : 8 across the three values: usage **follows the constraint**. (4) The same over-limit values are readable before the flush, and an unguarded sibling primitive allocates for the same over-limit length: the guard is on the deserializing read only, which is the recorded bypass. (5) After a failed read the other value is still readable, a compaction of the SSTable fails and leaves the file, and a replay under a lower limit stops the node starting: the guard's refusal acts as corruption.
- **Refuted if:** a refused length allocates an array; the exact limit is refused; the largest readable value does not move with the knob; or the refusal is not the guard's (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) run the harness test `MaxValueSizeGuardTest` (9c) once; it sets each limit live and checks the guard at the check, at two real deserializers and at the controls; (b) run it twice more on a yaml whose limit is out of range; (c) run the upstream `SSTableWriterTest` once as a baseline; its `testValueTooBigCorruption` is the in-JVM twin of scenario B.
2. **Cluster tier** — set up as in 9b. At each of `1m`, `4m`, `8m` and `default` run **Phase 1**. At `1m` also run the **compaction arm**, and at `4m` the **replay arm**.
3. **At each value:** control → **scenario A**, reach the limit (a value of exactly the limit, read after the flush) → **scenario B**, try to exceed it (one byte over, and 64 KiB over) → **scenario C**, the bypass arm (the same over-limit values read *before* the flush).
4. **Compare** with the prediction below and read the result in the table. The node run takes the scenarios in this order: control, then C (before the flush), then the flush, then A and B (9e).

**Prediction** (stated before any run, in numbers). Notation: *M* = the limit in force; *l* = the decoded length (for a `blob` cell, the payload length); *Δ* = bytes allocated by the calling thread across one call; *ε* = 65,536.

*Unit tier*, at *M* = 1,048,576 · 4,194,304 · 8,388,608 · 268,435,456 (the last is the default):

- **Read-back:** `DatabaseDescriptor.getMaxValueSize()` equals *M* after each `setMaxValueSize`; before any set, with no yaml line, it equals 268,435,456.
- **At the check,** `BytesType.instance.readBuffer(in, M)` on a vint length followed by 16 bytes: *l* = *M* → `EOFException` (the guard passed, the array was allocated, the input ran out), *Δ* from *M* to *M* + ε. *l* = *M* + 1 → `IOException` with the message `Corrupt value length <M+1> encountered, as it exceeds the maximum of <M>, which is set via max_value_size in cassandra.yaml`, *Δ* < ε. *l* = 2,147,483,647: the same form of message, *Δ* < ε. *l* = 2,147,483,648: `VIntOutOfRangeException`, an unchecked exception that is not an `IOException`, *Δ* < ε. The vint 2⁶⁴−1: `IOException` with `Corrupt (negative) value length encountered`, *Δ* < ε.
- **`readArray(in, M)`** (the `ByteArrayAccessor` path, the one cells use) gives the same outcomes for *l* = *M* and *M* + 1.
- **Clustering site:** `Clustering.serializer.deserialize(in, MessagingService.current_version, List.of(BytesType.instance))` on a header byte 0, a vint length *l* and 16 bytes: *l* = *M* + 1 → the guard's `IOException` with `<M+1>` and `<M>`, *Δ* < ε; *l* = *M* → `EOFException`, *Δ* from *M* to *M* + ε. It reads the live limit from config.
- **Fixed-length control:** `Int32Type.instance.read(ByteBufferAccessor.instance, in, 0)` on 4 bytes returns them (no comparison; the limit is ignored), while `BytesType` with limit 0 and *l* = 1 is refused.
- **Skip control:** `BytesType.instance.skipValue(in)` with *l* = *M* + 1 does not produce the guard's message and has *Δ* < ε (it ends in an `EOFException`, the input being shorter).
- **Sibling control (the non-domination):** `ByteBufferUtil.readWithVIntLength(in)` with *l* = *M* + 1 on the same kind of input → `EOFException`, not the guard's message, with *Δ* from *M* + 1 to *M* + 1 + ε.
- **Real deserializer** (at 1, 4 and 8 MiB): a `Mutation` holding a `blob` of *M* bytes, serialized with `Mutation.serializer` and deserialized again, returns a cell of *M* bytes with *Δ* ≥ *M*; with *M* + 1 bytes it throws the guard's `IOException` (message with `<M+1>` and `<M>`) with *Δ* < ε. **Live change:** the same serialized 2 MiB mutation is refused under 1 MiB and accepted after `setMaxValueSize(4 MiB)`, with no restart.
- **Range:** a yaml with `max_value_size: 2048MiB` fails start-up with a `ConfigurationException` whose message begins `max_value_size must be smaller than 2048, but was` (the source appends the value as written), and one with `0MiB` with `max_value_size must be positive`.
- **Upstream:** `SSTableWriterTest` passes, `testValueTooBigCorruption` included.

*Cluster tier*, one node, RF 1, protocol 4, one `blob` column, *M* = 1,048,576 · 4,194,304 · 8,388,608 and the default 268,435,456. Rows at each *M*: control 1,024 bytes; known-answer 307,200 bytes (below every *M*); **A** *M* bytes; **B1** *M* + 1; **B2** *M* + 65,536.

- **Read-back:** the first refusal's log line contains `maximum of <M>`, *M* being the value set.
- **Control:** after the first flush the 1,024-byte and the 307,200-byte rows read back at their lengths; the trace has one or more `alloc` lines of length 307,200 and none of length 1,024 (it is below the trace's 262,144 threshold).
- **Scenario C (before the second flush):** A, B1 and B2 are each acknowledged and read back at their **full** lengths, and the trace has **no** line of those lengths yet: neither the write nor a memtable read deserializes a value.
- **Scenario A (after `nodetool flush`):** `readback` of A returns *M* bytes, and the trace has one or more `alloc` lines of length *M* (class `ByteArrayAccessor`) and no other new large length.
- **Scenario B:** `readback` of B1 and of B2 each fail with `ReadFailure`; `logs/system.log` has, for each, `Corrupt value length <l> encountered, as it exceeds the maximum of <M>` inside a `CorruptSSTableException`; the trace has **no** line of length *M* + 1 or *M* + 65,536 at any time. A second `readback` of A afterwards still returns *M* bytes.
- **Dose-response:** the largest payload read back after the flush is *M*: **1 : 4 : 8** across the three values; the same kinds of rows are acknowledged at all three.
- **Default arm:** a row of 15,728,640 bytes (15 MiB, below both stock write-side caps) is acknowledged, flushed and read back whole; the trace has a line of that length; `system.log` has no `Corrupt value length`. A client cannot reach the default limit.
- **Compaction arm** (1 MiB; table `ks1.t` holding A and B1, table `ks1.ok` holding a 1,024-byte row, both flushed): `nodetool compact ks1 ok` replaces its SSTable with one of a new generation. `nodetool compact ks1 t` fails: `system.log` has the guard's message inside a `CorruptSSTableException` with a compaction class in its stack, the `Data.db` generation of `t` is unchanged and no `tmp-` file is left behind. A second `nodetool compact ks1 t` starts no task (no new error, generation unchanged) because the SSTable is suspect. `readback` of A on `t` still returns *M* bytes.
- **Replay arm** (4 MiB, then 1 MiB): a 2 MiB row (2,097,152 bytes) is acknowledged and read back, the node is killed with `kill -9` before any flush, and restarted under 1 MiB: the node does not reach `UN`, the process exits within the start-up window, and `system.log` has `Corrupt value length 2097152 encountered, as it exceeds the maximum of 1048576` and `Replay stopped. If you wish to override this error`. A restart of the same data under 4 MiB starts, replays the entry, and `readback` returns 2,097,152 bytes.

**Conclusions.**

| Result | Conclusion |
|---|---|
| Unit: at every value the boundary is as predicted (the exact limit passes the guard and allocates, one byte more is refused with the message and allocates under ε), at the check and at both real deserializers, and the live change takes effect. Cluster: the largest value read back after the flush is *M* at 1, 4 and 8 MiB (1 : 4 : 8), each refused value has the guard's message in `system.log` and no `alloc` line of its length, each accepted one has `alloc` lines of its length only | **Confirmed** — the check enforces as traced, per value. |
| Values above the limit are acknowledged and read back whole before the flush (scenario C), and fail only after it | **Bypass as recorded** — the write side and the memtable do not meet the limit (§5, §8); expected, not a refutation. Record the size of the largest value held (Target-3 material). |
| The sibling primitive allocates for the over-limit length (unit) | **Bypass as recorded** — the non-domination of §5; expected. |
| A refused length allocates an array: unit *Δ* ≥ *M*, or an `alloc` line of the refused length | **Refuted** — the guard does not precede the allocation (§5 and §6b are wrong). Re-read. |
| The exact limit is refused, or the largest value read back is below *M* | **Refuted** — an off-by-one, or a different limit binds (§4). Re-read. |
| The largest value read back is the same at every *M* | **Refuted** — not the binding limit. Re-read, do not re-run. |
| The largest value read back follows the knob, but a refusal lacks the guard's message, or the log shows another exception | **Not confirmed** — something else binds (a timeout, a frame cap). Check the hold-fixed settings (9b). |
| The sibling primitive is refused with the guard's message, or the fixed-length or skip control is refused | **Refuted in part** — §5's description of what the guard covers is wrong. |
| After the failed read of B the row A is unreadable, or an acknowledged value above the limit is refused at write | **Refuted in part** — §6b item 2.3 or §5's write-side claim is wrong. |
| `nodetool compact ks1 t` succeeds, or the second one fails again with the guard's message | **Not confirmed** for the compaction effect — §6b item 2.2 needs re-reading; the verdict on the claim stands on the other rows. |
| After the restart under the lower limit the node starts and `readback 30` returns the row | **Refuted in part** — §6b's replay effect is wrong (replay is not guarded, or the entry was not replayed). Check the segment was present. |
| After the restart under the lower limit the node does not start and the log shows the message | **Refusal as traced** — record it (Target-3 material: a lowered limit blocks recovery). |
| The limit read back differs from the value set; the known-answer row leaves no `alloc` line; the trace is empty after A is read; the control row is not read back; the compaction control on `ks1.ok` writes no new generation; `ThreadMXBean` reports allocated-bytes measurement unsupported; the upstream `SSTableWriterTest` is not green | **Invalid run** — fix the setup (9b, 9c) and re-run. |

Two rules behind this table:

- **A confirmation needs both** the ceiling moving with the knob **and** direct evidence that the disallow branch fired: here the guard's message, which prints both operands and is produced by one throw in the source (§6b item 1). A curve alone could come from a frame cap or a timeout.
- **The over-limit values are attributed to the recorded bypass** by an arm in which the bypass cannot fire: the same value, once flushed, is refused, while before the flush it is readable. The two together separate "the check does not cap" from "the write side does not check".

**Why bytes allocated, not heap used:** the array is transient and the collector hides it, so the node's heap size says nothing about it. The unit tier reads the bytes the thread allocates, which is exact; the node tier reads the array sizes requested at the allocation site, which is the same operand seen from outside. The node's own heap bytes are **not measured**; that gap is named in 9d.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `max_value_size` in `cassandra.yaml`, named as §4's path names it (`max_value_size_in_mb` is also read). **Restart-only** on a node. Unit tier: `DatabaseDescriptor.setMaxValueSize(<bytes>)`, live, a multiple of 1 MiB; and, for the range controls only, a copy of `test/conf/cassandra.yaml` with `max_value_size: <value>` appended, selected with `-Dcassandra.config=file:///<path>` (the mechanism `build.xml` uses for its own variants, [`build.xml:1266-1277`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/build.xml#L1266-L1277)). Cluster tier: the same line in the run clone's `conf/cassandra.yaml`. |
| **Confirm it took effect** | Unit: the test asserts `getMaxValueSize()` after each set. Cluster: the first refusal's log line prints `maximum of <M>`. A secondary read to try at the instrument check: `SELECT name, value FROM system_views.settings WHERE name = 'max_value_size'` (its absence is not a failure). |
| **Capacity values** | **Unit:** 1 MiB (1,048,576 bytes), 4 MiB (4,194,304), 8 MiB (8,388,608) and the default 256 MiB (268,435,456); plus range controls at 0 and 2048 MiB. **Cluster:** 1 MiB, 4 MiB, 8 MiB and the unset default (268,435,456, a control). Every explicit cluster value is below the write-side caps, so a client can write values around it. |
| **Scope** | Per value (one array). One value is read at a time, so *N* = 1 in every run; §8's `max_value_size × N` is **not tested**. One node, RF 1: no inbound-message path, no hints, no streaming. |
| **Level** | Both. **Unit:** the harness `MaxValueSizeGuardTest`; the upstream `SSTableWriterTest` as a baseline. **Cluster:** one node. |

**What the upstream tests do and do not show.** Three upstream classes set the limit to 1 MiB through `setMaxValueSize()` in a `@BeforeClass`: [`SSTableCorruptionDetectionTest.java:106-107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/SSTableCorruptionDetectionTest.java#L106-L107), [`CorruptedSSTablesCompactionsTest.java:96-97`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/compaction/CorruptedSSTablesCompactionsTest.java#L96-L97) and [`SSTableWriterTestBase.java:76-77`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/SSTableWriterTestBase.java#L76-L77). Only one of them asserts the guard's effect. **`SSTableWriterTest.testValueTooBigCorruption()`** ([`SSTableWriterTest.java:203-244`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/SSTableWriterTest.java#L203-L244)) writes one 2 MiB `blob` value through `SSTableWriter` ([`:215`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/SSTableWriterTest.java#L215)) under the base class's 1 MiB limit, reads the partition back with `SSTableReader.rowIterator()` and expects a `CorruptSSTableException` ([`:235-239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/SSTableWriterTest.java#L235-L239)). At one value it shows two halves of §5 and §6b at the SSTable level: **the writer accepts a value above the limit, and the read refuses it as corruption.** The other two classes set the limit only so that the damaged lengths their random corruption produces cannot allocate gigabytes. `SSTableCorruptionDetectionTest` writes 1,000 partitions with two 512 KiB `blob` cells each ([`:70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/SSTableCorruptionDetectionTest.java#L70)), overwrites random stretches of the file and asserts only that **at least one** of 100 runs raised `CorruptSSTableException` ([`:198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/io/sstable/SSTableCorruptionDetectionTest.java#L198)); it does not say which check raised it. `CorruptedSSTablesCompactionsTest` uses fixed-length types only ([`:102-106`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/compaction/CorruptedSSTablesCompactionsTest.java#L102-L106)), which never reach the comparison (§4). `AbstractTypeTest` and `EmptyTypeTest` call the unguarded one-argument overload (§5). **They do not show** the boundary (a value of exactly the limit against one byte more), the message, that a refused length allocates nothing, the live change, any call site but the cell one, the suspect mark and its effect on compaction, replay, or the write side on a real node. The harness test and the cluster tier add those.

**Hold fixed — unit tier:**

| Setting | Value | Why |
|---|---|---|
| JVM heap | the build's own test heap, `-Xmx4G` on the build's default ([`build.xml:1245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/build.xml#L1245), [`:1255`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/build.xml#L1255)) | the 256 MiB steps allocate a few 256 MiB arrays in one thread |
| Table | `ks.t (pk int PRIMARY KEY, v blob)`, created by the test with `SchemaLoader` | exact payload sizes for the real-deserializer step |
| Warm-up | one accepted and one refused call of each kind before any recorded one | class loading and JIT compilation allocate; *ε* is set for what remains |
| Everything else | the unit yaml as shipped | nothing else moves |

**Hold fixed — cluster tier:**

| Setting | Value | Why |
|---|---|---|
| `commitlog_sync` | `batch`, with the `commitlog_sync_period` line removed ([`DatabaseDescriptor.java:503-507`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L503-L507)) | a write is synced before it is acknowledged, so the replay arm's `kill -9` cannot lose it |
| `write_request_timeout`, `read_request_timeout` | `10000ms` | the defaults (2 s and 5 s) could time out a 15 MiB write or read, which would be read as a refusal |
| `disk_failure_policy`, `commit_failure_policy` | `stop`, as shipped | under `die` or `stop_paranoid` the first refused read stops the node's transports (§6b) and confounds every later reading; the replay arm's outcome is defined for `stop` |
| `max_mutation_size`, `commitlog_segment_size`, `native_transport_max_frame_size` | as shipped (derived 16 MiB, 32 MiB, 16 MiB) | every row below is under them: the largest write is 15,728,640 bytes |
| Heap | `MAX_HEAP_SIZE=4G` | the in-flight request caps derive from it and are far above 15 MiB |
| Client protocol | 4, pinned in `send-value.py` | one framing path |
| Tables | `ks1.t (pk int PRIMARY KEY, v blob)`, and `ks1.ok` of the same shape for the compaction arm; compression off, autocompaction off | exact payload sizes; the only compaction is the one the compaction arm runs. A user-requested compaction does not consult the `enabled` flag ([`CompactionManager.submitMaximal():996-1030`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L996-L1030)); only the background path does ([`CompactionStrategyManager.getNextBackgroundTask():203`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionStrategyManager.java#L203)) |
| Replication | `SimpleStrategy`, RF 1, one node | no replica-side path, no hints |
| Everything else | as shipped | nothing else moves |

**Controls:**

- **Idle run (cluster)** — no traffic for 10 s: the trace has no `alloc` line.
- **Small and known-answer rows (cluster)** — 1,024 B and 307,200 B, flushed and read: the second one proves the trace records an allocation the first one is too small to show.
- **Fixed-length, skip and sibling controls (unit)** — separate the guard from the other ways a value is read (§5).
- **Default arm (cluster)** — shows a client cannot reach the default.
- **Compaction control (cluster)** — `ks1.ok`, whose small row compacts normally: shows compaction works on this node at this limit, so the failure of `ks1.t` is the value's.
- **Replay control (cluster)** — the same data restarted under the original 4 MiB: shows the failure is the lowered limit's.
- **Upstream baseline (unit)** — `SSTableWriterTest` green.
- **Range controls (unit)** — 0 and 2048 MiB do not start.

**Reset between runs:** unit — each `ant testsome` is a fresh JVM and the test restores the limit it found. Cluster — stop the node (`bin/nodetool stopdaemon`, or `kill -9` for the replay arm), check `ps -eo cmd | grep '[C]assandraDaemon'` is empty, delete the clone's `data/` and `logs/`, restore `conf/cassandra.yaml` from `conf/cassandra.yaml.orig`, then write the next value's yaml. **The replay arm does not wipe `data/` between its two starts.**

### 9c. Workload

The operand is one value's length. Send values sized to the byte, one at a time, flush, and read each back.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/max_value_size-read-maxValueSize`.
Work for step 1, before run 1 (**none of it exists yet**):

| File | What it is |
|---|---|
| `MaxValueSizeGuardTest.java` | Unit tier. Package `org.apache.cassandra.db.marshal`. System property `stage4.out` (a file that also receives the `STAGE4` lines). Calls `DatabaseDescriptor.daemonInitialization()`, creates the table with `SchemaLoader`, measures *Δ* with `com.sun.management.ThreadMXBean.getThreadAllocatedBytes()` (and stops as Invalid if `isThreadAllocatedMemorySupported()` is false). Records `check MISMATCH` and goes on, failing at the end. Steps in 9e. |
| `make-unit-yaml.sh <label> <value>` | Copies `test/conf/cassandra.yaml` to `build/test/mvs-<label>.yaml` and appends `max_value_size: <value>`. |
| `unit-run.sh` | Runs the harness test, the two range controls and the upstream baseline; one summary line each. |
| `make-node-yaml.sh <label> <value\|none>` | From `conf/cassandra.yaml.orig` writes `conf/cassandra.yaml` with the hold-fixed settings of 9b and the knob (nothing for `none`). |
| `value-alloc.btm` | Byteman observation rules, no behaviour change. At the entry of `ByteArrayAccessor.read(DataInputPlus, int)` and of `ByteBufferUtil.read(DataInput, int)`, when `length >= 262144`, write `alloc class=<class> length=<n> thread=<name> ms=<epoch>` to the file named by `stage4.byteman.out`. Both are Cassandra classes, so no `boot:` is needed (see [`environment.md`](../../../stage4-runtime-verification/environment.md)). Parse-check it with Byteman's `TestScript` against `build/classes/main` before run 1, as the earlier harnesses did. |
| `send-value.py` | Cluster tier. A Python client on the driver bundled in `lib/cassandra-driver-internal-only-3.29.0.zip`, loaded as `bin/cqlsh.py` loads it ([`bin/cqlsh.py:47-56`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/bin/cqlsh.py#L47-L56)), protocol 4, request timeout 120 s. Modes: `probe`, `insert [--table <t>] <pk> <bytes>`, `readback [--table <t>] <pk>`. Prints `OK <length>` or `ERR <class> <message>`; exit 0 or 1. |
| `cluster-run.sh` | One run script for the case (stage 4 writes it): modes `instrument`, `value <label>` (Phase 1), `compaction`, `replay`. Logs every command to `~/stage4-logs/mvs/<label>/session.log`, writes `summary.txt`, exits at the first failed check and stops the node on any failure. |

```bash
# unit tier — in the local clone (never the shared cassandra-src); once:
ant build-test
cp <harness>/MaxValueSizeGuardTest.java test/unit/org/apache/cassandra/db/marshal/
mkdir -p $HOME/stage4-logs/mvs/unit

# the limits are set live inside the test: one JVM
ant testsome -Dtest.name=org.apache.cassandra.db.marshal.MaxValueSizeGuardTest \
  -Dtest.jvm.args="-Dstage4.out=$HOME/stage4-logs/mvs/unit/guard.out"

# range controls: <label> range-hi with 2048MiB, range-zero with 0MiB
<harness>/make-unit-yaml.sh <label> <value>
ant testsome -Dtest.name=org.apache.cassandra.db.marshal.MaxValueSizeGuardTest \
  -Dtest.jvm.args="-Dcassandra.config=file://$PWD/build/test/mvs-<label>.yaml -Dstage4.out=$HOME/stage4-logs/mvs/unit/<label>.out"

# upstream baseline
ant testsome -Dtest.name=org.apache.cassandra.io.sstable.SSTableWriterTest

# cluster tier — per value: yaml, start with the trace, schema, then writes, flushes and reads
<harness>/make-node-yaml.sh <label> <value|none>
JVM_EXTRA_OPTS="-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/value-alloc.btm,listener:true -Dstage4.byteman.out=$HOME/stage4-logs/mvs/<label>/alloc.trace" \
  MAX_HEAP_SIZE=4G bin/cassandra -p $HOME/stage4-logs/mvs/<label>/cassandra.pid > $HOME/stage4-logs/mvs/<label>/startup.log 2>&1
bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE ks1.t (pk int PRIMARY KEY, v blob) WITH compression = {'enabled': false} AND compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};"
<harness>/send-value.py insert <pk> <bytes>
<harness>/send-value.py readback <pk>
bin/nodetool flush ks1 t
```

`JVM_EXTRA_OPTS` is set on the `bin/cassandra` command only, never exported. The replay arm's second and third starts omit it (they need no trace).

**Starting values.** Estimates, not measurements:

| Quantity | Value | Why |
|---|---|---|
| Unit input after the length | 16 zero bytes | shorter than any tested *l* ≥ 1 MiB, so an allowed length ends in `EOFException` after its allocation and no large input buffer is needed |
| Tolerance *ε* | 65,536 B | the message formatting and the exception, its stack trace included, allocate a few kilobytes; the margin is above that and one sixteenth of the smallest *M* |
| Cluster rows per *M* | control 1,024; known-answer 307,200; A = *M*; B1 = *M* + 1; B2 = *M* + 65,536 | the payload length of a `blob` cell is the decoded length, so the boundary is exact |
| Primary keys | control 0, known-answer 99, A 1, B1 2, B2 3, default-arm row 1, replay row 30 | one row per size, so a length in the trace names its row |
| Default-arm row | 15,728,640 B | the largest round size under the stock 16 MiB caps, with room for the statement and the row's overhead |
| Trace threshold | 262,144 B | ignores the small reads of system tables; a length is read only by its exact value |

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — the operand *l* and the limit *M* | Not exposed as a metric. Unit: the test's own *l*, and the message, which prints both. Cluster: the refusal's log line, `Corrupt value length <l> encountered, as it exceeds the maximum of <M>`; for an accepted value *l* is its payload length. | At every refusal. | Only a refusal prints them. |
| **Disallow evidence** — a signal only the disallow path produces | (1) Unit: the exception's type and exact message. (2) Cluster: the client's `ERR ReadFailure` and `grep -n 'Corrupt value length' logs/system.log`, which must show *l* and *M*. (3) Compaction arm: the same line with a compaction class in the stack. (4) Replay arm: the same line and `Replay stopped`. | After each read. | The text is produced by **one throw** in the source (`AbstractType.java:595`, §6b item 1). One failure may log the line more than once (the executor and the handler), so count lines as "one or more". A level starts the log line: use `grep '^ERROR'`, not `grep ' ERROR '`. |
| **Bypass volume** — what the write side let through | Scenario C: the length `readback` returns for B1 and B2 before the flush. | Before the second flush. | The values must be read **before** the flush: after it they are refused. |
| **Real resource — array bytes** | (1) Unit: *Δ*, the thread's allocated bytes across the call, from `getThreadAllocatedBytes(Thread.currentThread().getId())` before and after. (2) Cluster: the lines of `alloc.trace`, each the size of an array requested at the allocation site. | (1) Around every recorded call, after the warm-up. (2) After each read, by exact length. | The trace also records **other** readers of large lengths (`ByteBufferUtil.read` is shared with the sibling primitives and `CacheService`): read it only by the exact lengths of this run's rows. **The node's heap bytes are not measured**: the array is transient and the collector hides it, so the trace is the proxy and its gap is that it shows requests, not residency. |
| **Disk effect** — what a failed compaction leaves | `ls -l data/data/ks1/t-*/*-Data.db` and `ls data/data/ks1/t-*/` before and after each `nodetool compact`: the generation number in the file name and any `tmp-` file. | Before and after each compaction. | A successful compaction of one SSTable writes a **new generation** and deletes the old file, so "unchanged" is a name comparison, not a size one. |
| **Start-up outcome** — the replay arm | `ps -eo cmd \| grep '[C]assandraDaemon'`, `bin/nodetool status`, `bin/nodetool statusbinary`, and `logs/system.log`. | Every 5 s for up to 180 s after the start. | A node that exits leaves no process and no `UN` line; a node that is still replaying has the process and no `UN` line: wait for one or the other. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Each check is printed as `STAGE4 check <name> <expected> <actual> ok|MISMATCH`; record pass or fail and the values.

1. **Harness test, one JVM.** After the warm-up, and for each *M* in 1,048,576 · 4,194,304 · 8,388,608 · 268,435,456, in that order, with `DatabaseDescriptor.setMaxValueSize(M)` (the first read-back, before any set, expects 268,435,456):
   1. *Read-back:* `getMaxValueSize()` equals *M*.
   2. *At the check:* build the input with a `DataOutputBuffer` (`writeUnsignedVInt32(l)` then 16 zero bytes), wrap it in a `DataInputBuffer`, and call `BytesType.instance.readBuffer(in, M)` for *l* = *M*, *M* + 1 and 2,147,483,647, and with `writeUnsignedVInt(2147483648L)` and `writeUnsignedVInt(-1L)`. Record the exception type, its message and *Δ* for each.
   3. *Array path:* `BytesType.instance.readArray(in, M)` for *l* = *M* and *M* + 1.
   4. *Clustering site:* `Clustering.serializer.deserialize(in, MessagingService.current_version, List.of(BytesType.instance))` on `writeUnsignedVInt(0L)`, `writeUnsignedVInt32(l)` and 16 zero bytes, for *l* = *M* and *M* + 1.
   5. *Controls:* `Int32Type.instance.read(ByteBufferAccessor.instance, in, 0)` on 4 bytes; `BytesType.instance.readBuffer(in, 0)` on *l* = 1; `BytesType.instance.skipValue(in)` for *l* = *M* + 1; `ByteBufferUtil.readWithVIntLength(in)` for *l* = *M* + 1.
   6. *Real deserializer* (not at 256 MiB, where it would build three 256 MiB copies; the crafted-input steps cover that value): build a `Mutation` for `ks.t` with a `blob` of *M* bytes with `RowUpdateBuilder`, serialize it with `Mutation.serializer.serialize(m, dob, MessagingService.current_version)`, and deserialize with `Mutation.serializer.deserialize(new DataInputBuffer(bytes), MessagingService.current_version)` (the input is built before *Δ* is read). Repeat with *M* + 1 bytes. Record the result, the cell's length and *Δ*.
   7. *Live change (once, in the 1 MiB pass):* serialize a mutation of 2,097,152 bytes; deserialize it under 1 MiB (expect the refusal), call `setMaxValueSize(4194304)`, deserialize the **same bytes** again (expect success). Restore the limit found at the start.
2. **Range controls.** Run the commands of 9c with `range-hi` (2048MiB) and `range-zero` (0MiB). Record the first line containing `ConfigurationException` in each and that no test method ran.
3. **Upstream baseline.** Run `SSTableWriterTest`; record green or red and, if red, the failing method.

**Before the cluster tier:**

1. **Instrument check.** On the node, at 1 MiB: (i) `send-value.py probe` connects over protocol 4 and prints `release_version`; (ii) `value-alloc.btm` passes `TestScript`, and an idle 10 s leaves no `alloc` line (the trace file may not exist yet); (iii) `insert 0 1024`, `insert 99 307200`, `nodetool flush ks1 t`, `readback 0` and `readback 99` return their lengths, the trace has an `alloc` line of length 307,200 and none of 1,024; (iv) the secondary `system_views.settings` read (its absence is not a failure). A failure of (i) to (iii) stops the run.
2. **Dataset check.** None: the tables start empty at every start.

**Cluster tier, Phase 1, for each value** (`1m`, `4m`, `8m`, `default`):

1. **Control run.** Fresh `data/` and `logs/`; `make-node-yaml.sh <label> <value|none>`; start the node with the trace; wait for `UN` and for `statusbinary` to print `running`; create the schema. Idle for 10 s. `insert 0 1024`, `insert 99 307200`, `nodetool flush ks1 t`, `readback 0`, `readback 99`. Expect the control rows read back at their lengths, `alloc` lines of length 307,200 and none of 1,024.
2. **Write.** For `1m`, `4m` and `8m`: `insert 1 <M>`, `insert 2 <M+1>`, `insert 3 <M+65536>` — each `OK`. For `default`: `insert 1 15728640` — `OK`.
3. **Scenario C — before the flush.** `readback 1`, `readback 2`, `readback 3` (for `default`: `readback 1`): each `OK` with its full length. Check the trace has no new line of those lengths.
4. **Flush.** `bin/nodetool flush ks1 t`; `ls -l data/data/ks1/t-*/*-Data.db`.
5. **Scenario A — reach the limit.** `readback 1`: `OK` with length *M* (for `default`, 15,728,640). The trace gains `alloc` lines of that length.
6. **Scenario B — try to exceed the limit** (not for `default`). `readback 2` and `readback 3`: each `ERR ReadFailure`. `grep -n 'Corrupt value length' logs/system.log` shows *l* and *M* for each. The trace has no line of length *M* + 1 or *M* + 65,536.
7. **Separation.** `readback 1` again: `OK`, length *M*.
8. **Stop.** `bin/nodetool stopdaemon`, check no `CassandraDaemon` is left, copy `logs/system.log` and `alloc.trace` to `~/stage4-logs/mvs/<label>/`; `grep -c '^ERROR'` the log.

**Compaction arm (1 MiB only).** Fresh start at `1m` as in step 1, then create `ks1.ok` with the same definition as `ks1.t`. `insert --table ks1.ok 0 1024`; `insert 1 <M>`; `insert 2 <M+1>`; `bin/nodetool flush ks1`. `ls data/data/ks1/t-*/ data/data/ks1/ok-*/` and record the generations. `bin/nodetool compact ks1 ok` and list again (expect a new generation). `bin/nodetool compact ks1 t`: record the exit code and output, list again, `grep -n 'Corrupt value length' logs/system.log` and the stack of the first hit. Run `bin/nodetool compact ks1 t` a second time and compare the listing and the log with the first. `readback 1`. Stop as in step 8.

**Replay arm (4 MiB, then 1 MiB).** Fresh start at `4m` as in step 1, create the schema. `insert 30 2097152`; `readback 30` (length 2,097,152). Confirm a segment file in `data/commitlog/`. `kill -9` the `CassandraDaemon` process (a graceful stop would flush it away); check none is left. `make-node-yaml.sh replay 1m` **without** wiping `data/`, start (no trace), and poll every 5 s for up to 180 s for either `UN` with `statusbinary` `running` or the process disappearing. Record which, then `grep -n 'Corrupt value length\|Replay stopped\|encountered during startup' logs/system.log`. Then `make-node-yaml.sh replay-ctl 4m`, start, wait for `UN` and `running`, `grep -i 'replay' logs/system.log`, `readback 30`. Stop.

**Record for stage 4:** the `cassandra.yaml` diff against the shipped file and the JVM options in force, the exact commands, the node, OS, JDK and Ant versions and the clone's commit, and the raw readings of 9d for every step: the client's line, the trace excerpt by length, the listings, and the `system.log` excerpts. Keep the full logs on the node and a small excerpt per value in the results folder.

**Budget.** Unit: about 2.5 minutes to build; about 1 to 2 minutes for the harness JVM (a few 256 MiB arrays); the upstream baseline, `SSTableWriterTest`, is a small class (allow a few minutes; not measured). Cluster: about 90 s to start a node and about 1 to 2 minutes of operations per value, so about 3 minutes per value and about 12 minutes for Phase 1; the compaction arm about 4 minutes; the replay arm about 6 (two starts and up to 3 minutes' wait for the failed one): about 25 minutes for the tier. The largest write is 15 MiB; the commit log and the flush stay under 100 MiB per value; the node has 125 GiB of memory and 63 GB of local disk, so none of this is near a limit.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — from [`../../../stage2-ai-preprocessing/bands.md`](../../../stage2-ai-preprocessing/bands.md)'s **band A1** list, row `AbstractType.java:594#1` ("deserialized value length against the configured max value size, rejecting the value"), ranked in stage-2 `batch-19.txt` (`bands.csv`, 2026-09-24). Judged in the band-A1 pass on 2026-09-28 and recorded in `pending.md`; written up 2026-10-06. |
| **Filed by / Date** | Claude (`claude-sonnet-5-5`) session, 2026-10-06 |
| **Line numbers checked** | 2026-10-06 against the local `cassandra-5.0.9` clone at `~/repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`, `HEAD` `b5f2a54210`). Every cited line was checked by a script that finds an expected snippet of code inside the cited range and that label and anchor agree; the load-bearing ones were also read in context. |
| **Escape hatch / Target-3 note** | **No flag or setting turns the check off**, but it covers less than its name suggests. (1) **The write side is unguarded** (§5, §8): a value above the limit is accepted, held in the memtable and flushed, and only fails when read back; the heap it occupies there is not bounded by this limit. (2) **Unguarded siblings** (§5): 24 call sites of `readWithVIntLength` and 5 of `readWithLength` allocate from a length field with no limit, including the partition key of every inbound partition and the cell path of every collection cell. (3) **Fixed-length types** skip the comparison (§4); a skipped column allocates nothing (§5). (4) **Stock settings shadow it for clients** (§8): the write-side caps are an order of magnitude below the default, so it fires on damaged data only. (5) **Lowering it is destructive** (§6b): values already stored above the new limit cannot be read, an SSTable that holds one is never compacted again, and a commit log that holds one stops the node starting; the override flag `-Dcassandra.commitlog.ignorereplayerrors=true` skips the entry and loses its data. (6) **Node-local:** the value is not exchanged between nodes, so a replica with a lower limit refuses an inbound mutation that the coordinator accepted and sent (source-derived, not run). (7) **At the top of its range** (2047 MiB) it is within 1 MiB of the largest length the decoder can return, so it bounds almost nothing. |
| **Stage-4 feedback** | none yet. §9 was written in the new layout on 2026-10-06 (9a to 9e); it is not yet audited (stage-4 README, step 0) and not yet run. It lists its harness as work for step 1. |
| **Notes** | **Found while writing this up (2026-10-06), for stage 3 to judge; `pending.md` and `rejected.md` are not rewritten.** *The non-domination is not where the earlier note put it:* it says `readBuffer(in)` passes `Integer.MAX_VALUE` and disables the guard for its callers; the overload has **no production caller** (§5), and the real non-domination is the sibling primitives and the write side. *The class comment is stale:* [`Config.java:304-308`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L304-L308) says the default is "the same as the native protocol frame limit: 256MiB", but the frame cap's default is 16 MiB ([`Config.java:285`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L285)). *The trace message is misleading:* [`SSTableReader.markSuspect():1034`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java#L1034) says the SSTable is "excluded from reads", but only compaction consults the flag (§6b item 2.3). *One upstream test does assert the effect:* `SSTableWriterTest.testValueTooBigCorruption` (§9b) writes a 2 MiB value under a 1 MiB limit and expects a `CorruptSSTableException` on read; the other two classes that set the limit do so only to bound allocations while fuzzing corruption. |

---

## 11. Notes

- **Why one case for four call sites.** The four call sites of §5 pass the same limit into one comparison, so README §6.1's "one case, several check sites" does not even apply: there is one check site and four callers. The case is named after the check (`AbstractType.read():594`).
- **Why this qualifies when per-item sanity bounds were refused.** `rejected.md` refuses per-item bounds whose total is held elsewhere (for `internode_max_message_size`, "the queue cap still binds", so raising the limit alone moves no maximum). Here nothing else bounds the size of one array made from a length field at these four sites, so the limit moves that maximum directly; what it does not move is any total, and §8 says so. That is the playbook's rule that a per-object limit needs a multiplier before it says anything about the node.
- **Contrast with `max_mutation_size`.** That check refuses cleanly, as a client error, **before** the allocation, and replay does **not** meet it. This one refuses as *corruption*, after the value has been stored, and replay **does** meet it. They bound the same bytes from opposite sides, and at stock settings the write-side one fires first (§8). A limit set below the write-side caps lets clients store what the node then cannot read.
- **Why the node tier uses limits of 1 to 8 MiB, not the default.** A client cannot write a value of 256 MiB at stock settings, so the default's boundary is exercised only by the unit tier; raising the write-side caps and the heap far enough to write one (a 1 GiB commit-log segment, a 512 MiB mutation cap and frame cap, and a heap whose per-client in-flight cap exceeds 257 MiB) is possible but heavy, and is left out. The default arm shows instead that a stock client cannot reach it.
- **The unit yaml is not the node's.** `max_value_size` has no unit-yaml override, so both start at 256 MiB; but the unit yaml's `max_mutation_size` is derived from its 5 MiB segments (2.5 MiB), which does not matter here because the unit tier never calls `CommitLog.add()`.
- **What this design does not cover.** The inbound-message consumer (it needs two nodes with different limits); the hints, streaming, batchlog and read-repair consumers; sites 3 and 4 of §5 (the SSTable scan's clustering values and the partition key of a read command; site 2 is covered at the unit tier and they have the same shape); range-delete bounds; *N* > 1, the multiplier; the unguarded `AbstractType` case that would allocate up to 2 GiB (§6b item 4); and the other unguarded read sites of §5, which the sibling control samples with one primitive. Each is recorded from the source in §5 or §6b.
- **Nothing here was run.** No measured number appears in this file; every figure in §9 is derived from the source and is a prediction.
