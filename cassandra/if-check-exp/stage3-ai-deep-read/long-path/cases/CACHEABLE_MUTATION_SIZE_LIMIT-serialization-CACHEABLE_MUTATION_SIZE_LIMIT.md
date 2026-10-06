# CACHEABLE_MUTATION_SIZE_LIMIT — serialized copy of a mutation (CachedSerialization vs SizeOnlyCacheableSerialization)

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | CACHEABLE_MUTATION_SIZE_LIMIT-SERIALIZATION-CACHEABLE_MUTATION_SIZE_LIMIT |
| **Constraint** | `CACHEABLE_MUTATION_SIZE_LIMIT` — a **JVM system property**, `cassandra.cacheable_mutation_size_limit_bytes`, declared in [`CassandraRelevantProperties.java:80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L80) with a default of 1,000,000 bytes. It is **not** a `cassandra.yaml` entry and has no setter or JMX operation. **Restart-only**: the value is captured once into a `static final` of `Mutation` (§4). |
| **Enforcement pattern** | **(a)** at the primary site: the `if` is the decision, and its allow branch holds the allocation. **The second site is split.** The tee's comparison is itself the decision for each write into a scratch buffer (a), and it also sets a flag, `limitReached`, that [`Mutation$MutationSerializer.deserialize():518`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L518) reads to decide whether the cached copy is created at all (b). **Both outcomes allocate something**, as in `column_index_cache_size`: what the check withholds is a retained copy, and the divergence is in retained size (§5, §7). |
| **Capacity check** | [`Mutation$MutationSerializer.serialization():451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451) — `serializedSize < CACHEABLE_MUTATION_SIZE_LIMIT`. **Second site, same constraint:** [`TeeDataInputPlus.maybeWrite():58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L58) — `limit <= 0 \|\| (!limitReached && (teeBuffer.position() + length) < limit)`, whose `limit` is the same constant, passed in at [`Mutation$MutationSerializer.deserialize():493`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L493). |
| **Decision point** | Serialize side: [`Mutation$MutationSerializer.serialization():451-463`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451-L463) — the `if` and the store that follows it. Receive side: [`TeeDataInputPlus.maybeWrite():58-61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L58-L61) for each mirrored write, and [`Mutation$MutationSerializer.deserialize():518-519`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L518-L519) for the copy. |
| **Allocation site** | Serialize side: [`serialization():453-456`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L453-L456) takes the thread-local scratch buffer, serializes the mutation into it and **creates the copy**, `new CachedSerialization(dob.toByteArray())` — a heap `byte[]` of exactly the serialized size ([`DataOutputBuffer.toByteArray():285-291`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L285-L291)). Receive side: [`deserialize():519`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L519), the same construction from the bytes the tee mirrored. These are the only two places a `CachedSerialization` is built. |
| **Related cases** | [`max_mutation_size-validateSize-MAX_MUTATION_SIZE.md`](max_mutation_size-validateSize-MAX_MUTATION_SIZE.md) — `Mutation.validateSize()` measures a mutation by calling `serializedSize()`, which reaches this check first: below the limit, **measuring the size builds the copy** (§5). That case's §10 asks that this one cite it. [`column_index_cache_size-indexSamples-cacheSizeThreshold.md`](column_index_cache_size-indexSamples-cacheSizeThreshold.md) — the other case where both outcomes allocate; it differs in that a key cache caps its total (§8). [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md`](MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md) — hint writes reach this check through [`Hint$Serializer.serializedSize():163-168`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/Hint.java#L163-L168); that case's stage-4 harness already met the scratch buffer this case's allow branch takes. [`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md`](native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md), [`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md`](internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md) — in-flight request caps that count request bytes and do not count this copy (§8). |

```java
// Mutation$MutationSerializer.serialization():439-467 — the capacity check, the decision and the allocation (primary site)
private Serialization serialization(Mutation mutation, int version)
{
    int versionOrdinal = MessagingService.getVersionOrdinal(version);
    // Retrieves the cached version, or build+cache it if it's not cached already.
    Serialization serialization = mutation.cachedSerializations[versionOrdinal];
    if (serialization == null)
    {
        serialization = new SizeOnlyCacheableSerialization();                                              // :446
        long serializedSize = serialization.serializedSize(PartitionUpdate.serializer, mutation, version); // usage side, :447

        // Excessively large mutation objects cause GC pressure and huge allocations when serialized.
        // so we only cache serialized mutations when they are below the defined limit.
        if (serializedSize < CACHEABLE_MUTATION_SIZE_LIMIT)                                                // <-- capacity check and decision, :451
        {
            try (DataOutputBuffer dob = DataOutputBuffer.scratchBuffer.get())                              // allow: thread-local scratch buffer, :453
            {
                serializeInternal(PartitionUpdate.serializer, mutation, dob, version);                     // :455
                serialization = new CachedSerialization(dob.toByteArray());                                // <-- allocation, :456
            }
            catch (IOException e)
            {
                throw new RuntimeException(e);
            }
        }
        mutation.cachedSerializations[versionOrdinal] = serialization;                                     // :463, either object is stored
    }

    return serialization;
}
```

```java
// TeeDataInputPlus.maybeWrite():56-62 — second check site, one call per read the deserializer makes
private void maybeWrite(int length, Throwables.DiscreteAction<IOException> writeAction) throws IOException
{
    if (limit <= 0 || (!limitReached && (teeBuffer.position() + length) < limit))   // <-- capacity check, :58
        writeAction.perform();                                                       // allow: mirror the bytes just read
    else
        limitReached = true;                                                         // disallow: stop mirroring, for good, :61
}
```

```java
// Mutation$MutationSerializer.deserialize():491-493 and :517-519 — where the limit is passed in and where the flag is read
try (DataOutputBuffer dob = DataOutputBuffer.scratchBuffer.get())
{
    teeIn = new TeeDataInputPlus(in, dob, CACHEABLE_MUTATION_SIZE_LIMIT);            // :493
    ...
    //Only cache serializations that don't hit the limit
    if (!teeIn.isLimitReached())                                                      // <-- decision point, receive side, :518
        m.cachedSerializations[MessagingService.getVersionOrdinal(version)] = new CachedSerialization(dob.toByteArray());   // :519
```

## 2. Context

A write the node handles is held as a mutation object, and the same mutation has to be turned into bytes several times: once to be sent to each replica, once to be appended to the commit log, once to be stored as a hint, and once more just to learn its size for the limits that are applied to it. To avoid redoing that work, the node keeps the serialized bytes next to the object the first time they exist: when it serializes the mutation itself, and when a mutation arrives already serialized (from the network, from the commit log on a restart, from a stored hint), it keeps a copy of the bytes it just read. This check decides whether that copy is kept. Below a byte threshold the copy is kept for as long as the mutation lives. At or above it, only the mutation's size is remembered and the bytes are regenerated every time they are needed, so the node spends CPU instead of memory. The source gives the reason in a comment: very large serialized mutations strain the garbage collector with huge allocations. Without the check every in-flight write, however large, would carry a second copy of itself.

The check bounds the **copy**, not the mutation: the mutation's own in-memory form exists in either case, and the threshold decides only whether a second, serialized form is kept beside it. The threshold is a per-mutation value, not a total.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `mutation` — the write object and its serialization (`db/Mutation`, `io/util/TeeDataInputPlus`) |
| **One-line role** | A mutation is the unit of write that a node applies, logs, sends to replicas and stores as a hint; this module turns it into bytes for each of those and keeps the bytes when it is cheap enough to. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes — per item, as a retention threshold.** It compares the serialized size of one mutation with a byte threshold and keeps a heap copy only below it. It keeps no running total, so what it bounds is the size of each copy; the node-wide effect needs a multiplier (§8). |
| **Usage-side operand** | Serialize side: `serializedSize`, a `long` computed at [`serialization():447`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L447) by walking the partition updates without writing a byte ([`SizeOnlyCacheableSerialization.serializedSize():587-598`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L587-L598)). Receive side: `teeBuffer.position() + length`, the bytes mirrored so far plus the next read ([`TeeDataInputPlus.java:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L58)). Both measure the mutation's serialized size *T* at the messaging version in use; the copy is kept iff *T* < limit at both (§5). |
| **Limit-side operand** | `CACHEABLE_MUTATION_SIZE_LIMIT`, the `private static final long` of [`Mutation.java:81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L81); at the second site the constructor argument `limit` ([`TeeDataInputPlus.java:47-54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L47-L54)). |
| **Limit type** | **JVM system property**, default 1,000,000 bytes. No `cassandra.yaml` key, setter, JMX operation or documentation entry: a search of `src`, `conf`, `doc`, `test`, `CHANGES.txt` and `NEWS.txt` finds the constant and the property name only in `Mutation.java` and `CassandraRelevantProperties.java` (the changelog entry, `CHANGES.txt:540`, names the feature, not the property). Read **once**, when `Mutation` is initialized. |

**Limit initialization path** (declare → parse → store → read):

1. [`CassandraRelevantProperties.CACHEABLE_MUTATION_SIZE_LIMIT:80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L80) — declared: key `cassandra.cacheable_mutation_size_limit_bytes`, default `1_000_000`; the comment above it says "the maximum size (in bytes) of a serialized mutation that can be cached".
2. [`CassandraRelevantProperties.getLong():806-812`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L806-L812) with [`LONG_CONVERTER:986-996`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L986-L996) — parsed with `Long.decode`; a value that is not a number throws `ConfigurationException`, here inside `Mutation`'s static initializer (so a bad value would stop the node at its first use of `Mutation`; derived from the source, not run).
3. [`Mutation.CACHEABLE_MUTATION_SIZE_LIMIT:81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L81) — stored in a `private static final long`, **fixed when `Mutation` is initialized**. Nothing changes it afterwards.
4. [`serialization():451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451) — read at the comparison; and [`deserialize():493`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L493) — passed to the tee, stored in its `limit` field ([`TeeDataInputPlus.java:39`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L39)) and read at `:58`.

**Naming note (Target 1).** The constraint is named after the first-declared variable on this path, the `CassandraRelevantProperties` constant; the stem's `serialization` is the method that encloses the primary comparison, and `CACHEABLE_MUTATION_SIZE_LIMIT` appears again as the operand as written there (`Mutation`'s own field has the same name), so the stem repeats it (README §6.1). The Javadoc at [`Mutation.java:536-540`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L536-L540) says mutations "up to 2MB" are kept; the property's default is 1,000,000 bytes and the code governs (§11).

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | Serialize side: [`Mutation$MutationSerializer.serialization():451-463`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451-L463). Receive side: [`TeeDataInputPlus.maybeWrite():58-61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L58-L61) and [`Mutation$MutationSerializer.deserialize():518-519`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L518-L519). |
| **Verdict** | Serialize side, pattern (a): none; the `if` is the decision, and what it leaves is **which object sits in the mutation's slot**, `cachedSerializations[versionOrdinal]` ([`Mutation.java:78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L78)): a `CachedSerialization` (the bytes) or a `SizeOnlyCacheableSerialization` (the size). Receive side: the boolean `limitReached`, set at [`TeeDataInputPlus.java:61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L61), read through [`isLimitReached():221-224`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L221-L224) at `Mutation.deserialize():518`; once set it is never cleared, and the tee stops mirroring from that read on. |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow (serialize)** | `serializedSize < CACHEABLE_MUTATION_SIZE_LIMIT` | the mutation is serialized into the thread-local scratch buffer and copied into a new `byte[]` of exactly `serializedSize` bytes, which a `CachedSerialization` holds in the slot; later `serialize()` is `out.write(serialized)` and `serializedSize()` is `serialized.length` ([`Mutation.java:563`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L563), [`:569`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L569)) |
| **Disallow (serialize)** | `serializedSize >= CACHEABLE_MUTATION_SIZE_LIMIT` | no scratch buffer, no `byte[]`; the slot keeps the `SizeOnlyCacheableSerialization` created at `:446`, a small object (about 24 bytes, inferred) holding the size; later `serialize()` walks the partition updates again into the destination ([`:581-584`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L581-L584)) |
| **Allow (receive)** | `limit <= 0`, or every read so far has satisfied `position + length < limit` | each read is mirrored into the scratch buffer; at the end `deserialize()` copies it into a new `byte[]` and stores a `CachedSerialization` at the slot of the wire version |
| **Disallow (receive)** | `limit > 0` and some read has `position + length >= limit` | `limitReached` is set; no further read is mirrored; the buffer stops growing; no `byte[]` is made and the slot stays **null** (a later `serialization()` call fills it with the size-only object) |

```java
// allow, serialize side: Mutation.serialization():453-456
try (DataOutputBuffer dob = DataOutputBuffer.scratchBuffer.get())
{
    serializeInternal(PartitionUpdate.serializer, mutation, dob, version);
    serialization = new CachedSerialization(dob.toByteArray());
}
```

```java
// disallow, serialize side: nothing runs; the SizeOnlyCacheableSerialization built at :446 is stored at :463 and keeps its size
//   Mutation$SizeOnlyCacheableSerialization.serialize():581-584 and serializedSize():586-598
void serialize(...) { MutationSerializer.serializeInternal(serializer, mutation, out, version); }
long serializedSize(...) { /* computed once, kept in a volatile long */ }
```

**The two sites agree on the boundary: a copy is kept iff *T* < limit.** On the receive side every read is mirrored only while `position + length < limit`, where `position` is the bytes mirrored so far; the last read brings the total to *T*, so all reads pass iff *T* < limit, and a failed read at any point means *T* ≥ limit. On the serialize side the comparison is `<` outright. So a mutation of exactly `limit` bytes is **not** cached by either, and one of `limit − 1` bytes is. (The upstream test shows the same strictness for the tee: a limit of 40 mirrors 39 bytes, §9b.)

**The two sites read a limit of 0 (or less) in opposite senses.** On the serialize side `serializedSize < 0` is never true, so **nothing is cached**. On the receive side `limit <= 0` is the *unbounded* case (the two-argument constructor passes 0, [`TeeDataInputPlus.java:42-45`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L42-L45)), so **everything is mirrored and cached, whatever its size**. A property value of 0 therefore turns the copy off for the mutations a node serializes and removes the bound for the mutations it deserializes (§10, §9).

### Does the check dominate the allocation?

**For the copy, yes.** `CachedSerialization` is a private nested class, constructed in exactly two places, [`Mutation.java:456`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L456) (under the `if` at `:451`) and [`:519`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L519) (under `if (!teeIn.isLimitReached())`). No other path creates one. What the check does **not** gate:

- **The mutation's own heap.** The `PartitionUpdate` objects exist before either check; the copy is a second form beside them. The check withholds only the copy.
- **The receive-side scratch buffer when the limit is 0 or less**, as above.
- **Other copies of the same bytes**, which belong to other objects: `CommitLog.add()` serializes into the scratch buffer again ([`CommitLog.java:306-308`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L306-L308); with a cached copy that is `out.write(serialized)`), and network and hint buffers hold their own.

### Where the check is reached

**Serialize side** — the first call for a mutation and version builds the slot; every later call reads it:

| # | Call | Reached by |
|---|---|---|
| 1 | [`Mutation.validateSize():171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L171) → [`Mutation.serializedSize(int):326-342`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L326-L342) → [`MutationSerializer.serializedSize():530-533`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L530-L533) | the **coordinator**, for every CQL write: [`SingleTableUpdatesCollector.toMutations():112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java#L112), [`BatchUpdatesCollector.toMutations():149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchUpdatesCollector.java#L149); a replica's [`MutationVerbHandler.doVerb():54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/MutationVerbHandler.java#L54); [`CommitLog.add():304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304). **Measuring a mutation's size below the limit builds its copy.** |
| 2 | [`MutationSerializer.prepareSerializedBuffer():423-426`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L423-L426) | the coordinator, once, before sending: [`StorageProxy.sendToHintedReplicas():1501`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1501), so that concurrent senders find the slot full |
| 3 | `Message.serializedSize()` → [`MutationSerializer.serializedSize():530-533`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L530-L533) | each message to a peer, at [`OutboundConnection.enqueue():330`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L330) through [`canonicalSize():1045-1048`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L1045-L1048) (always at `current_version`) |
| 4 | [`MutationSerializer.serialize():412-415`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L412-L415) | the commit log ([`CommitLog.java:308`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L308)), hints ([`Hint.java:175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/Hint.java#L175)), the batchlog ([`Batch.java:133`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/Batch.java#L133), [`BatchlogManager.java:148`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/BatchlogManager.java#L148)), counter mutations ([`CounterMutation.java:368`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L368)), schema pulls ([`SchemaMutationsSerializer.java:40`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaMutationsSerializer.java#L40)) |

**Receive side** — every call of `Mutation.serializer.deserialize()` goes through the tee:

| # | Call | Reached by |
|---|---|---|
| 5 | [`Verb.java:116`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/Verb.java#L116) (`MUTATION_REQ`; also `READ_REPAIR_REQ` at [`:120`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/Verb.java#L120) and `PAXOS2_COMMIT_REMOTE_REQ` at [`:186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/Verb.java#L186)) → [`InboundMessageHandler.processSmallMessage():166`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L166) and [`InboundMessageHandler$LargeMessage.deserialize():362`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L362) → [`Message$Serializer.deserialize():761`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/Message.java#L761) | a replica receiving a mutation from the network |
| 6 | [`CommitLogReader.readMutation():431`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReader.java#L431) | commit-log **replay** at start-up |
| 7 | [`Hint.java:182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/Hint.java#L182), [`:206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/Hint.java#L206); [`Batch.java:170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/Batch.java#L170); [`BatchlogManager.java:400`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/BatchlogManager.java#L400); [`CounterMutation.java:374`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L374); [`SchemaMutationsSerializer.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaMutationsSerializer.java#L50) | hint, batchlog, counter and schema reads |

At a replica, the copy made while deserializing is what rows 1 and 4 later find in the slot (when the wire version is the node's own), so the mutation's partition updates need **no second walk** to be measured, logged or forwarded while the copy exists. A mutation whose copy was withheld has a null slot until the first call of `serialization()` (row 1 at the replica's `doVerb()`), which builds the size-only object.

## 6. Code path

### 6a. Allow path → object creation

**Serialize side (coordinator):**

1. [`ModificationStatement.getMutations():750`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java#L750) → [`SingleTableUpdatesCollector.toMutations():112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java#L112) → [`Mutation.validateSize():171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L171) → `serializedSize(version)` → [`serialization():439`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L439).
2. [`serialization():443-447`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L443-L447) — the slot is empty; a `SizeOnlyCacheableSerialization` is created and asked for the size, which it computes by walking the partition updates.
3. [`serialization():451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451) — `serializedSize < limit`: allow.
4. [`serialization():453-455`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L453-L455) — the thread-local `DataOutputBuffer` (direct by default, [`DataOutputBuffer.java:55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L55); starts at 128 bytes, [`:57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L57)) receives the serialized mutation, growing as needed ([`calculateNewSize():158-172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L158-L172)).
5. [`serialization():456`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L456) — **object creation**: `dob.toByteArray()` allocates `new byte[buffer.remaining()]` on the heap and copies the bytes in; a `CachedSerialization` wraps it. The scratch buffer is closed on leaving the `try` ([`DataOutputBuffer.java:71-82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L71-L82): kept if its capacity is at most 1 MiB, replaced by a 128-byte one otherwise).
6. [`serialization():463`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L463) — stored in the mutation's slot. **Nothing ever clears it**: the comment at [`Mutation.java:75-77`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L75-L77) says so on purpose. Later calls (the coordinator's [`StorageProxy.java:1501`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1501), each message's size at [`OutboundConnection.java:330`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L330), the commit log at [`CommitLog.java:308`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L308)) read it.

**Receive side (a replica, replay, a hint):**

1. A caller of row 5, 6 or 7 above reaches [`MutationSerializer.deserialize():487`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L487).
2. [`deserialize():491-493`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L491-L493) — takes the thread-local scratch buffer and wraps the input in a `TeeDataInputPlus` with the limit.
3. [`deserialize():495-515`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L495-L515) — every read of the partition updates passes through the tee; for each, [`maybeWrite():58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L58) allows the mirror write, for example [`readFully():67-68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L67-L68), which reads from the source first and mirrors second.
4. [`deserialize():518-519`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L518-L519) — the flag is clear: **object creation**, `new CachedSerialization(dob.toByteArray())`, stored at the slot of the wire version.
5. The mutation is returned. At a replica, [`MutationVerbHandler.doVerb():54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/MutationVerbHandler.java#L54) measures it from the copy, [`:57-59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/MutationVerbHandler.java#L57-L59) forwards the same message to other nodes, and [`:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/MutationVerbHandler.java#L75) applies it; the copy (when the wire version is the node's own) serves the commit-log entry on the way.

### 6b. Disallow path effect

1. **Serialize side.** [`serialization():451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451) is false: the block at `:453-461` does not run, so **no scratch buffer is taken and no `byte[]` is made**. [`:463`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L463) stores the size-only object, which keeps the size (`:578`, `:589-596`). The mutation is **not refused, blocked or retried**: it goes on to be sent, logged and applied as any other.
2. **What it costs instead.** Every later `serialize()` of that mutation re-walks its partition updates ([`:581-584`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L581-L584)): once per replica message, once for the commit log, once per hint, once per batchlog entry. The check trades memory for CPU.
3. **Receive side.** [`maybeWrite():58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L58) is false: [`:61`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L61) sets `limitReached`, and because the `!limitReached` term is then false, every later read is also not mirrored, so the scratch buffer stops growing at its current content (less than the limit). The reads themselves are unaffected: the source is read first (`:67`), so deserialization completes normally. [`deserialize():518`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L518) is false: no `byte[]`, the slot stays null.
4. **A null slot is filled on first use.** At a replica the next call (`doVerb():54`, via `validateSize()`) finds the null slot and runs the serialize-side path above, which, for a size at or above the limit, ends in a size-only object. That call walks the object but allocates no copy.
5. **If the check were absent** every mutation would keep its copy for its whole life, the largest ones included; the source's own comment ([`Mutation.java:449-450`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L449-L450) and the Javadoc at [`:536-540`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L536-L540)) names the garbage-collection cost of such objects as the reason for the threshold. Derived from the source; §9 does not run it.
6. **Limit 0 or less.** Serialize side: step 1 for every mutation. Receive side: [`maybeWrite():58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L58) is true on its first term for every read; `limitReached` is never set; step 4 of 6a runs for every mutation of every size.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `Mutation$CachedSerialization`, which holds a `byte[]` of exactly the mutation's serialized size and sits in the mutation's `cachedSerializations` slot; and, transiently, the thread-local scratch `DataOutputBuffer` it is built through. The disallow counterpart is `Mutation$SizeOnlyCacheableSerialization`, a few words and one `long`. |
| **Resource consumed** | **Heap bytes:** the retained `byte[]`. **Off-heap bytes:** the scratch buffer, a direct buffer by default ([`DataOutputBuffer.java:55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L55)), per thread, transient or recycled. |
| **Rough sizing** | The copy is *T* bytes, *T* < limit, plus an array header and the wrapper (about 32 bytes under compressed object pointers; inferred, JVM-dependent). The slot array has one place per `MessagingService.Version` ([`Mutation.java:74`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L74), four values at [`MessagingService.java:212-222`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/MessagingService.java#L212-L222), of which `serializedSize()` accepts only 4.0 and 5.0), so a mutation can hold a copy per version in use: **one** in a steady cluster, two while peers use another messaging version. The scratch buffer grows by doubling, or by `capacity + count` for a single large write, so its capacity ends between *T* and about twice *T* (inferred, as in `max_mutation_size`); after use it is kept if at most 1 MiB ([`DOB_MAX_RECYCLE_BYTES`, `CassandraRelevantProperties.java:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L204)) and replaced by a 128-byte one otherwise. |
| **Lifetime / release** | **As long as the `Mutation` is reachable.** Nothing removes a copy (`Mutation.java:75-77`). Holders found in the source, not traced to the end: at the coordinator the write response handler keeps the mutation for the request, because `Mutation.hintOnFailure()` returns `this` ([`Mutation.java:158-161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L158-L161), stored at [`AbstractWriteResponseHandler.java:81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java#L81) and [`:107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java#L107), used for a hint at [`:309-310`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java#L309-L310)); each outbound or inbound `Message` holds its payload until it is sent or handled; the local apply task holds it; during replay the task's closure holds the deserialized mutation ([`CommitLogReplayer.java:284-297`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L284-L297)) until the rebuilt one is applied at [`:326`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L326). The memtable does not keep the mutation; it copies the cells (not traced here). The scratch buffer lives as long as its thread. |

## 8. Maximum memory/disk bound

`CACHEABLE_MUTATION_SIZE_LIMIT` caps **the size of the serialized copy one mutation keeps on the heap**, not the mutation and not their sum. A mutation whose serialized size is below it keeps one `byte[]` of exactly that size per messaging version in use; one at or above it keeps none. So the largest copy the node retains is `limit − 1` bytes (about `limit + 32` with its header and wrapper), and raising or lowering the limit moves that one for one, up to the largest mutation that can reach the code. With the defaults that is 16 MiB, the `max_mutation_size`, which is above the 1,000,000-byte limit, so a mutation between the two is accepted but never copied.

It bounds **none of the totals.** The node-wide extra heap is about `(limit − 1 + 32) × N`, where *N* is the number of live mutations whose serialized size is just under the limit: writes in flight at a coordinator (held by the response handler for the request), messages waiting in outbound queues, mutations being applied, hints being written, and, during a restart, the mutations replay has outstanding (up to 1,024 or 64 MiB of them, [`CommitLogReplayer.java:75-79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L75-L79)). *N* is not bounded by this check. The in-flight request caps count request bytes, not this copy, so the copy is **in addition** to what they bound; `concurrent_writes` ([`Config.java:180`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L180), wired at [`Stage.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/Stage.java#L46)) bounds only the mutations applied at the same instant. As arithmetic, not a measurement: a thousand live mutations of just under 1,000,000 bytes retain about 1 GB of copies at the default, and none at a limit of 1.

The copy is **on top of** the mutation's own heap, which the limit does not touch: a mutation at or above the limit costs its own heap only. What the limit moves is the copy's share and the CPU spent regenerating the bytes (§6b).

**Off-heap:** the receive side's scratch buffer holds less than `limit` bytes of content (its capacity, after growth, up to about twice that), and the serialize side's scratch buffer is used only for mutations below the limit. A scratch buffer above 1 MiB is not kept ([`DataOutputBuffer.java:71-82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L71-L82)), so a limit above about 1 MiB turns each copy of a larger mutation into a direct allocation that is freed at once, where a limit below it leaves up to about 1 MiB per thread allocated for good. Inferred from the source; §9 records the scratch capacity, not a conclusion.

**A limit of 0 or less inverts the receive side** (§5): the serialize side then keeps nothing, and the receive side keeps every deserialized mutation whole, so the copy of an incoming mutation is bounded by the mutation (and by the transport, replay and hint limits that bound it), not by this knob. The limit has no derived limits and derives from none.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test finds, at several values of the property, which mutations keep a serialized copy on the heap: the largest one just under the limit and the first one at it
(unit tier), and three sizes spread across the limit (node), at both places the check is made. The serialize side is reached by live writes; the receive side is
reached on a node by commit-log replay. One arm sets the property to 0, which the two sides read in opposite senses. **Run so far:** none. Written in this layout on
2026-10-06; not yet audited (stage-4 README, step 0).

### 9a. Procedure and conclusions

**Testability:** **JVM system property, restart-only.** `-Dcassandra.cacheable_mutation_size_limit_bytes=<bytes>`; no yaml key, setter or JMX operation exists, and the value is
captured once into a `static final` of `Mutation` (§4). Unit tier: one JVM per value, passed with `-Dtest.jvm.args`. Cluster tier: one node start per value and phase.
No patched build is needed; the unit tier reads `Mutation`'s private fields by reflection, and the cluster tier needs Byteman rules (9c) because no metric or log line
reports the decision.

**Claim under test:** `CACHEABLE_MUTATION_SIZE_LIMIT` bounds the on-heap serialized copy a mutation keeps. A mutation of serialized size *T* < the limit keeps a `byte[]` of
exactly *T* bytes in its slot; one with *T* ≥ the limit keeps only its size (serialize side) or nothing yet (receive side), and is neither refused nor delayed. So the largest
copy is `limit − 1` bytes and the knob moves it one for one; the limit is per copy, so the node-wide extra heap is `limit × N` (§6b, §8). A value of 0 keeps nothing on the
serialize side and keeps every deserialized mutation whole on the receive side (§5).

**How this verifies the hypothesis** (a restatement of the claim, procedure, prediction and conclusions in this section; it adds none):

- **Hypothesis:** the constraint caps the heap bytes of the serialized copy of each mutation, at both places the copy is made, and a mutation at or above the limit is
  left without one and still applied.
- **Test:** vary the property over three values in the unit tier and the node tier (100,000, the default 1,000,000 and 4,000,000), plus a reference value that turns the copy off
  (1) and the escape value (0). At each value, unit tier: build the largest mutation under the limit and the first one at it, and read the slot's class and array length, the
  bytes the thread allocated and the scratch buffer. Node tier: hold 24 writes of three sizes in memory with a Byteman delay, count the live copies and read the heap's byte
  arrays with a class histogram, then kill the node and do the same during commit-log replay of the same writes.
- **Logic:** (1) the limit read back equals the value set, else the run is invalid. (2) A mutation of *limit* − 1 bytes has a copy of exactly that length and one of *limit*
  bytes has none, at both sites: usage **stops at the limit**. (3) On the node the number of live copies and the byte arrays' excess over the no-copy reference follow
  which sizes are under the limit, across the three values: usage **follows the constraint**. (4) The mutation with no copy has the size-only object (serialize) or a null
  slot (receive), the trace says so, and the mutation is applied: the disallow branch, not something else, withholds the copy. (5) At 0 the receive side holds a copy of every
  replayed mutation, including the 2 MB ones, and the serialize side none: the recorded escape.
- **Refuted if:** a mutation at or above the limit (limit ≥ 1) has a copy; one below it has none; the copy's length is not *T*; or the live copies and the heap do not follow
  the knob (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) run the upstream `TeeDataInputPlusTest` once; (b) run the harness test `CacheableMutationSizeTest` (9c) in one JVM per value: 100,000, 1,000,000,
   4,000,000, 1 and 0.
2. **Cluster tier** — set up as in 9b. At each value run **Phase 1** (live writes, the serialize site), then kill the node and run **Phase 2** (restart and commit-log
   replay of the same writes, the receive site). The five values are the unit tier's.
3. **At each value:** idle control → **scenario A**, sizes below the limit (the copy exists) → **scenario B**, sizes at or above it (the copy is withheld) → **scenario C**,
   the bypass arm: the value 0, whose receive side is unbounded. Value 1 is the reference in which every size is in B. The three sizes are written in one step, so A and B
   are read together at each value; the exact boundary is the unit tier's.
4. **Compare** with the prediction below and read the result in the table.

**Prediction** (stated before any run, in numbers). Notation: *L* = the limit in force, in bytes; *v* = `MessagingService.current_version` (4.0 under the shipped
`storage_compatibility_mode: CASSANDRA_4`, [`conf/cassandra.yaml:2320`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L2320); the harness prints it); *slot* =
`mutation.cachedSerializations[MessagingService.getVersionOrdinal(v)]`; *T* = a mutation's serialized size at *v*, the check's operand, read with
`Mutation.serializer.serializedSize(m, v)`; *P* = a write's payload bytes, so that *T* = *P* + *k*, with *k* constant inside a vint size class (tens of bytes; calibrated).
The check keeps a copy iff *T* < *L*, at both sites.

*Unit tier*, at *L* = 100,000 · 1,000,000 · 4,000,000 (the default is 1,000,000), then the reference *L* = 1 and the escape *L* = 0:

- **Read-back:** the private `Mutation.CACHEABLE_MUTATION_SIZE_LIMIT` and `CassandraRelevantProperties.CACHEABLE_MUTATION_SIZE_LIMIT.getLong()` both equal *L*.
- **Calibration** (*L* ≥ 100,000): there is a payload *p\** with *T*(*p\**) = *L* − 1 and *T*(*p\** + 1) = *L*. (Inside one vint class *T* rises by 1 per payload byte; at 4,000,000 the
  class is the one starting at 2,097,152. If a class boundary skips a value, *T*(*p\**) = *L* − 2; the harness records it.)
- **Serialize site:** after `Mutation.serializer.serializedSize(m, v)`, a fresh `m(1,024)` and a fresh `m(p*)` each have in their slot a `CachedSerialization` whose array length
  is *T* (*L* − 1 for `m(p*)`); a fresh `m(p*+1)` (*T* = *L*), a fresh `m` of about 1.01 *L* and one of about 2 *L* each have a `SizeOnlyCacheableSerialization`.
- **Heap allocated** (`getThreadAllocatedBytes`, after a warm-up): the call on `m(p*)` allocates between *T* and *T* + 64 KiB more than the call on `m(p*+1)`.
- **Scratch buffer** (recorded, not concluded): after the call on `m(p*)` the thread's scratch capacity is at least *T* (kept, if it was at most 1,048,576) or exactly 128 (replaced
  at close, if it was larger); after the call on `m(p*+1)` it is unchanged from before the call.
- **Receive site:** deserializing the wire bytes *W* of `m(p*)` gives a mutation whose slot holds a `CachedSerialization` with array length *L* − 1 and contents equal to *W*;
  deserializing those of `m(p*+1)`, of about 1.01 *L* and of about 2 *L* gives a slot that is **null**, and after a `serializedSize` call on it the slot holds a
  `SizeOnlyCacheableSerialization`.
- **Tee alone:** `readFully` of *L* − 1 bytes leaves `isLimitReached()` false with *L* − 1 bytes mirrored; a fresh tee reading *L* bytes sets it, with 0 mirrored.
- ***L* = 1 (the reference):** every size above, at both sites: no copy (a null slot at the receive site; the size-only object at the serialize site).
- ***L* = 0 (the escape):** serialize site, every size, including 1,024 bytes: no copy. Receive site, every size, including 3,000,000 bytes: a copy of the whole length,
  `isLimitReached()` false.
- **Upstream:** `TeeDataInputPlusTest` passes.

*Cluster tier*, one node, RF 1, three payloads *P*₁ = 90,000 · *P*₂ = 500,000 · *P*₃ = 2,000,000 bytes, so *T*₁ ≈ 90,000 + *k*, *T*₂ ≈ 500,000 + *k*, *T*₃ ≈ 2,000,000 + *k* (the trace
gives the exact values), *n* = 8 writes of each size held at once (24 in all). Let *c*(*L*) = the number of sizes with *T*ᵢ < *L*: *c*(100,000) = 1, *c*(1,000,000) = 2,
*c*(4,000,000) = 3, *c*(1) = 0. Phase 1 reads the serialize site, Phase 2 the receive site; the live counts are those of a class histogram taken while the writes are held,
less the node's own histogram with nothing held (the idle one in Phase 1, the one after the hold in Phase 2). The counts are exact; the spread between two histograms of the same
quiet node (the idle control, expected 0) is their tolerance.

- **Phase 1** (live writes): `Mutation$CachedSerialization` +8 *c*(*L*) and `Mutation$SizeOnlyCacheableSerialization` +8 (3 − *c*(*L*)); the trace has 24 `serialize` lines, with
  `cached=CachedSerialization` on those with *T* < *L* and `cached=SizeOnlyCacheableSerialization` on the rest. At *L* = 0 the counts equal those at *L* = 1 (*c* = 0): no
  copy at all.
- **Phase 2** (replay): `Mutation$CachedSerialization` +8 *c*′(*L*), with *c*′ = *c* for *L* ≥ 1 and ***c*′(0) = 3**; the trace has 24 `deserialize` lines, `cached=true` with `teeLen` = *T*ᵢ
  on 8 *c*′(*L*) of them, and `cached=false` on the rest. The `SizeOnly…` count is unchanged (recorded: nothing in the replay path asks the mutation's size, so the slot stays null).
- **Heap:** the `[B` bytes held at value *L*, less those at the reference *L* = 1 in the same phase, equal 8 × Σ over the cached sizes of (*T*ᵢ + 16), that is about **0.72 MB · 4.72 MB ·
  20.72 MB** at 100,000 · 1,000,000 · 4,000,000, to within the larger of 10 % and three times the **cross-run spread** *S*_B, the difference between the `[B` bytes of the two Phase 1 runs that are predicted equal (*L* = 0 and
  *L* = 1); an excess below 3 *S*_B (expected at 100,000) is recorded, not read. Dose-response: the excess at 4,000,000 is about 4.4 times the excess at 1,000,000.
- **Largest copy:** at every positive value the longest `serialize` and `deserialize` trace line with `cached` true is shorter than *L* (*T*₃ < 4,000,000, *T*₂ < 1,000,000, *T*₁ < 100,000).
- **Release:** after the writes return (Phase 1) or the replay ends (Phase 2), both counts are back within the idle baseline.
- **Scenario C** (*L* = 0): Phase 1 as the reference; **Phase 2 holds 24 copies, 8 of them of the 2 MB mutations** (*T*₃ > 1,000,000, so the default would have withheld them): the bypass
  volume is 8 × (*T*₃ + 16), about 16 MB.

**Conclusions.** Adapt the wording to what the readings show; the **Refuted** rows are what stage 4's feedback settles.

| Result | Conclusion |
|---|---|
| Unit: at every value the boundary is exactly *T* = *L* − 1 cached and *T* = *L* not, at both sites, with the array length *T* (receive: equal to the wire bytes), and *L* = 1 caches nothing. Cluster: the live counts and the byte arrays follow *c*(*L*) at both phases, the trace names the branch of each write, and every written mutation is applied | **Confirmed** — the check enforces as traced, per mutation, at both sites. |
| At *L* = 0 the serialize side holds nothing and the receive side holds a copy of every mutation, the 2 MB ones included (unit, and Phase 2) | **Bypass as recorded** — `limit <= 0` is unbounded on the receive side (§5); expected, not a refutation. Record the bytes (Target-3 material). |
| A mutation with *T* ≥ *L* (*L* ≥ 1) has a copy at either site, by slot or by the trace or count, and no recorded bypass explains it | **Refuted** — the check does not withhold the copy. |
| A mutation with *T* < *L* has no copy, or the boundary is off by one (*T* = *L* is cached, or *T* = *L* − 1 is not) | **Refuted in part** — §5's strict boundary or §6a's allow path is wrong. Re-read. |
| The copy's length is not *T*, or on the receive side its bytes differ from the wire bytes | **Refuted in part** — §7's object, or the tee's mirror, is not as traced. |
| The live counts follow *c*(*L*) but the byte arrays' excess is below a third of the prediction at 1,000,000 and at 4,000,000 | **Not confirmed** — the counted copies are not retained as §7 says (or something releases them early); re-read §7's lifetime, do not re-run. |
| The counts, the trace and the byte arrays are the same at every value | **Refuted** — not the binding limit, or the property did not reach `Mutation`. Re-read 9b's read-back first. |
| A written mutation is refused, delayed past the hold or lost because of the branch taken | **Refuted** — the disallow branch is not the pure retention choice §6b says. |
| The limit read back differs from the value set; fewer than 24 `held` lines in 60 s (Phase 1) or 120 s (Phase 2); a Byteman rule fails its `TestScript`; the histogram cannot be parsed; the small control write shows no `serialize` line; `isThreadAllocatedMemorySupported()` is false; the upstream `TeeDataInputPlusTest` is not green | **Invalid run** — fix the setup (9b, 9c) and re-run. |

Two rules behind this table:

- **A confirmation needs both** the ceiling following the knob **and** direct evidence that the disallow branch fired: here the slot's class (unit) and the trace's `cached=`
  field with the live `SizeOnly…` count (node). A curve of `[B` bytes alone could come from anything that holds byte arrays.
- **The receive-side overshoot is attributed** by an arm in which the bypass cannot fire: the same 24 mutations are replayed under 100,000 and 1,000,000 (the 2 MB ones have no copy)
  and under 0 (they have), so "the check does not cap" and "0 removes the receive-side bound" are told apart.

**Why a class histogram and traces, not RSS or `du`:** the copy is a `byte[]` on the Java heap. Process RSS cannot show it (`-Xms` pre-commits the heap, GC timing hides
the live set). `jcmd <pid> GC.class_histogram` collects garbage first, so it counts what is *retained*, and it names the two classes; the trace gives each mutation's operand and
branch. The unit tier reads the slot itself, which is exact. The histogram's `[B` row also counts every other byte array on the node (including the held writes' own payloads),
so only differences between runs with the same held writes isolate the copies.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | The JVM system property `cassandra.cacheable_mutation_size_limit_bytes`, named as §4's path names it. **Restart-only.** Unit tier: `-Dtest.jvm.args="-Dcassandra.cacheable_mutation_size_limit_bytes=<L> …"`, the mechanism `build.xml` offers ([`build.xml:94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/build.xml#L94), applied at [`:1192`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/build.xml#L1192)). Cluster tier: the same `-D` in `JVM_EXTRA_OPTS`, **scoped to the `bin/cassandra` command** (`VAR=… bin/cassandra`, not exported), next to the Byteman agent. |
| **Confirm it took effect** | Unit: the harness test reads the private field by reflection and asserts it equals `-Dstage4.expect_limit`. Cluster: `jcmd <pid> VM.system_properties \| grep cacheable_mutation` shows the value the JVM started with; the constant has no accessor, so the **boundary in the trace** (which sizes were cached) is the second read. |
| **Capacity values** | **Unit and cluster:** 100,000 B, 1,000,000 B (the default) and 4,000,000 B; the reference **1**; the escape **0**. Any positive value is read by `Long.decode`, so write plain decimals. |
| **Scope** | Per mutation per messaging version. **Unit:** *N* = 1. **Cluster:** *N* = 8 mutations of each size held at once; §8's `limit × N` claim is read as the excess over the reference being 8 × the cached sizes, and *N* is **not** varied. One node: one slot per mutation (a copy per version in use is not tested; the mixed-version case is not reachable on one node). |
| **Level** | Both. **Unit:** the upstream `TeeDataInputPlusTest` ([`TeeDataInputPlusTest.java:35-140`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/utils/TeeDataInputPlusTest.java#L35-L140)) and the harness `CacheableMutationSizeTest`. No upstream test reads `cachedSerializations` or calls `Mutation.serializer.deserialize()` to check the cache (searched `test/` for `cachedSerializations`, `CachedSerialization` and `CACHEABLE_MUTATION`: none). **Cluster:** one node. |

**What the upstream test does and does not show.** `TeeDataInputPlusTest.testTeeBuffer()` was added with the feature (CASSANDRA-17998, commit `227409d920`). It reads a mix of types through an
unlimited tee and through one with `LIMITED_SIZE = 40` ([`:67`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/utils/TeeDataInputPlusTest.java#L67),
[`:73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/utils/TeeDataInputPlusTest.java#L73)) and asserts that the limited one is `isLimitReached()` and holds exactly the first 39
bytes ([`:138-139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/utils/TeeDataInputPlusTest.java#L138-L139)). It shows the tee's strict boundary. It does **not** show the
`Mutation`-level decision at either site, the slot, the version ordinal, the `limit <= 0` case through a mutation, the real property, or a node.

**Hold fixed — unit tier:**

| Setting | Value | Why |
|---|---|---|
| Unit yaml | `test/conf/cassandra.yaml`, unchanged | no commit log or node is used; the harness prints `MessagingService.current_version` |
| Table | the `STANDARD1` table that `CommitLogTest.beforeClass()` creates, built with `SchemaLoader` | the payload arithmetic is the upstream helper's ([`CommitLogTest.java:467-489`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/commitlog/CommitLogTest.java#L467-L489)): measure a one-byte mutation, then derive the payload that makes *T* exact |
| Scratch buffer | defaults: direct, recycle limit 1 MiB (`cassandra.dob.allocate_type`, `cassandra.dob_max_recycle_bytes` unset) | the allocated-bytes and capacity readings depend on them |
| Thread | one test thread, warmed up before any reading | `getThreadAllocatedBytes` counts per thread, and the first call loads classes |
| Fresh mutation per probe | every probe builds a new `Mutation` | the slot is filled by the first call and never cleared; reusing a mutation would read the previous probe |

**Hold fixed — cluster tier:**

| Setting | Value | Why |
|---|---|---|
| `commitlog_sync` | `batch`, with the `commitlog_sync_period` line removed ([`DatabaseDescriptor.java:503-507`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L503-L507)) | a write is synced before it is acknowledged, so the kill between the phases leaves it in the log for replay |
| `write_request_timeout` | `120000ms` (shipped `2000ms`, [`conf/cassandra.yaml:1330`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L1330)) | a write held 45 s must not time out and be read as a failure |
| Hold | `stage4.hold.ms` = 45000 | long enough for two histograms of a few seconds each |
| `concurrent_writes` | `32` (shipped, [`conf/cassandra.yaml:723`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L723)) | 24 writes are held on mutation-stage threads; 8 stay free for the node's own writes |
| Heap | `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE` unset | the histogram's full collection stays short, and the heap is the same at every value |
| `memtable_allocation_type` | `heap_buffers` (shipped, [`conf/cassandra.yaml:825`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L825)) | unchanged; the held writes are not yet in a memtable |
| `max_mutation_size`, `native_transport_max_frame_size` | shipped (16 MiB each) | every write here is about 2 MB at most; neither refuses one |
| **No flush, no snapshot** | `nodetool flush` is never run; no other setting forces one | the replay phase needs the writes **in the commit log, not in an SSTable** |
| Client | protocol 4, pinned in `send-mutation.py`; request timeout 180 s | one framing path; a held write outlasts the default |
| Table | `ks1.t (pk int PRIMARY KEY, v blob)`, compression off | exact payload sizes; the hold rule matches keyspace `ks1` only |
| Replication, durability | `SimpleStrategy`, RF 1, one node; `durable_writes` true (default) | no peers, no hints; the commit log is on the path |
| Byteman | the agent from `build/lib/jars/byteman-4.0.20.jar` with `listener:true` ([`environment.md`](../../../stage4-runtime-verification/environment.md)) | the rules of 9c; ports 7000, 7199, 9042, 9091 must be free |

**Controls:**

- **Idle run (both phases)** — two class histograms 10 s apart with nothing held: the live counts of the two classes (the baseline) and how far the `[B` row moves on its own within one run.
- **Small write (cluster)** — one unheld 1,024 B write: the trace shows a `serialize` line with *T* just above 1,024 and `cached=CachedSerialization` at 100,000 and above, and
  `cached=SizeOnlyCacheableSerialization` at 1 and 0. It shows the rule fires and the branch is readable.
- **Reference value (both tiers)** — *L* = 1: no copy at either site.
- **Equal runs (cluster)** — Phase 1 at *L* = 0 and at *L* = 1 are predicted equal; their difference is the cross-run spread *S*_B the `[B` rows are read against.
- **Release control (cluster)** — a histogram after the hold: the two counts return to the baseline.
- **Upstream suite (unit)** — `TeeDataInputPlusTest` is green.

**Reset between runs:** unit — each `ant testsome` is a fresh JVM. Cluster — between values: stop the node, check `ps -eo cmd | grep '[C]assandraDaemon'` is empty, delete the clone's
`data/`, `commitlog/` and `logs/`, restore `conf/cassandra.yaml` from `conf/cassandra.yaml.orig`. **Between a value's Phase 1 and Phase 2 do not wipe anything**: the kill and restart
are the point.

### 9c. Workload

The operand is one mutation's serialized size. Write mutations sized to the byte, hold them in memory, and read the heap and the trace while they are held.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT`.
Work for step 1, before run 1 (none of it exists yet):

| File | What it is |
|---|---|
| `CacheableMutationSizeTest.java` | Unit tier. Package `org.apache.cassandra.db` (it reads private fields by reflection). System properties: `stage4.expect_limit` (bytes, required) and `stage4.out` (a file that also receives the `STAGE4` lines). Calls `DatabaseDescriptor.daemonInitialization()`, creates the table with `SchemaLoader`, reads `Mutation.cachedSerializations` and `DataOutputBuffer.capacity()` by reflection, measures with `com.sun.management.ThreadMXBean.getThreadAllocatedBytes()` (and stops as Invalid if `isThreadAllocatedMemorySupported()` is false). Records `check MISMATCH` and goes on, failing at the end. Steps in 9e. |
| `unit-run.sh` | Runs the upstream class, then the harness test over the five values, printing one summary line each. |
| `cache-trace.btm` | Byteman rules, observation only, loaded at node start. One at [`Mutation$MutationSerializer.serialization()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L463), `AT LINE 463`: prints `serialize T=<$serializedSize> cached=<$serialization.getClass().getSimpleName()> ks=<keyspace>` for keyspace `ks1`. One at [`deserialize()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L518), `AT LINE 518`, for keyspace `ks1`: prints `deserialize cached=<!$teeIn.isLimitReached()> teeLen=<$dob.getLength()>`. Local-variable names need the class files' variable table, which the build writes ([`build.xml:33`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/build.xml#L33), `debuglevel` `source,lines,vars`). Parse with `TestScript` first; fall back to `AT EXIT` of `CachedSerialization.<init>` if a line trigger does not resolve. |
| `hold.btm` | Byteman rule, the trigger: at the entry of [`Keyspace.applyInternal()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Keyspace.java#L523) for keyspace `ks1`, appends a `held` line to `stage4.hold.out` and calls `delay(stage4.hold.ms)`. Every apply path passes there: the local apply of a coordinator write (`Mutation.apply()`), a replica's `applyFuture()`, and the rebuilt mutation of a replay ([`CommitLogReplayer.java:326`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L326)); the held thread keeps the mutation reachable. Same form as `hold-flush.btm` of `MAX_HINT_BUFFERS`. |
| `make-node-yaml.sh <label>` | From `conf/cassandra.yaml.orig` writes `conf/cassandra.yaml` with the hold-fixed settings of 9b. |
| `send-mutation.py` | Cluster tier. A Python client on the driver bundled in `lib/cassandra-driver-internal-only-3.29.0.zip`, loaded as `bin/cqlsh.py` loads it, protocol version 4, request timeout 180 s. Modes: `probe`; `insert <pk> <bytes>`; `many <first-pk> <n> <bytes>` (*n* concurrent inserts, one thread each); `readback <pk>`. Prints `OK …` or `ERR <class> <message>`; exit 0 or 1. |
| `histo.sh <out>` | `jcmd <pid> GC.class_histogram` (default: live objects only, which forces a full collection), then writes one `key=value` line: `[B` instances and bytes, and instances and bytes of `org.apache.cassandra.db.Mutation$CachedSerialization` and `…$SizeOnlyCacheableSerialization`. |
| `cluster-run.sh` | One run script for the case (stage 4 writes it): modes `instrument`, `value <label>` (both phases). Logs every command to `~/stage4-logs/cms/<label>/session.log`, writes `summary.txt` and `readings.csv`, exits at the first failed check and stops the node on any failure. |

```bash
# unit tier — in the local clone (never the shared cassandra-src); once:
ant build-test
cp <harness>/CacheableMutationSizeTest.java test/unit/org/apache/cassandra/db/
ant testsome -Dtest.name=org.apache.cassandra.utils.TeeDataInputPlusTest                       # upstream

# one JVM per value; <L> is 100000, 1000000, 4000000, 1, 0
ant testsome -Dtest.name=org.apache.cassandra.db.CacheableMutationSizeTest \
  -Dtest.jvm.args="-Dcassandra.cacheable_mutation_size_limit_bytes=<L> -Dstage4.expect_limit=<L> -Dstage4.out=$HOME/stage4-logs/cms/unit/<L>.out"

# cluster tier — per value; <logs> is ~/stage4-logs/cms/<label>
<harness>/make-node-yaml.sh <label>
JVM_EXTRA_OPTS="-Dcassandra.cacheable_mutation_size_limit_bytes=<L> -Dstage4.hold.ms=45000 -Dstage4.hold.out=<logs>/hold.txt -javaagent:build/lib/jars/byteman-4.0.20.jar=script:<harness>/cache-trace.btm,script:<harness>/hold.btm,listener:true" \
  MAX_HEAP_SIZE=4G bin/cassandra -p <logs>/cassandra.pid > <logs>/startup.log 2>&1
bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE ks1.t (pk int PRIMARY KEY, v blob) WITH compression = {'enabled': false};"
<harness>/send-mutation.py many 100 8 90000 &            # three of these at once: this, then `many 108 8 500000` and `many 116 8 2000000`
<harness>/histo.sh <logs>/histo-held-1.txt               # 5 s after the 24th held line, again 15 s after
kill -9 "$(cat <logs>/cassandra.pid)"                    # between the phases only
```

**Starting values.** Estimates, not measurements:

| Quantity | Value | Why |
|---|---|---|
| Payloads | 90,000 · 500,000 · 2,000,000 B (`bytes(n)`, zero bytes) | each size is under one value and over the next: *T*₁ < 100,000 < *T*₂ < 1,000,000 < *T*₃ < 4,000,000, with at least a 10 % margin on every comparison, so *k* does not matter |
| Held writes | 8 of each, 24 in all | 24 < 32 mutation-stage threads; the largest held total, about 20.7 MB, stays far below the node's in-flight caps and below one commit-log segment (32 MiB) |
| Hold | 45 s | the node needs 24 `held` lines (seconds), then two histograms of 2 to 5 s each |
| Small control write | 1,024 B | resolves the trace line |
| Cross-run spread *S*_B | measured by the two runs predicted equal (Phase 1 at *L* = 0 and *L* = 1) | the `[B` excesses are read only where the prediction exceeds three times it |

**If sizes drift:** the payload length is variable-length encoded, so *k* changes by one byte at payloads of 16,384, 2,097,152 and 268,435,456. The three node payloads are all in one class (16,384 to 2,097,151); none sits near a boundary. The unit tier calibrates *T* exactly at each value (at 4,000,000 its mutation is in the next class).

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — the check's operand *T* and the limit *L* | Unit: `Mutation.serializer.serializedSize(m, v)` (public), and the private `CACHEABLE_MUTATION_SIZE_LIMIT` by reflection. Cluster: the `serialize` trace line's `T=` (printed for every branch), and the `deserialize` line's `teeLen`. | Unit: at every probe. Cluster: after the 24th `held` line, from `<logs>/trace.txt`. | On the receive side with the limit reached `teeLen` is **cropped** (below *L*) and does not show *T*: take *T* for that size from the Phase 1 line of the same value. The `serialize` rule fires once per mutation and version, when the slot is empty. |
| **Disallow evidence** — a signal only the disallow path produces | (1) Unit: the slot's class (`SizeOnlyCacheableSerialization`, or null on the receive side) and the scratch capacity unchanged across the call. (2) Cluster: the trace's `cached=SizeOnlyCacheableSerialization` (serialize) or `cached=false` (receive); the live `…$SizeOnlyCacheableSerialization` count in the histogram. | After each probe (unit); with the held writes (cluster). | A `SizeOnlyCacheableSerialization` is built for **every** mutation at `:446` and replaced at `:456` for the cached ones, so only the **live** count after a collection counts (the histogram collects first). Before relying on the trace, confirm from the source that nothing else prints it: only the two rules of 9c do. System-keyspace writes also create these objects; the idle baseline absorbs them and the rules match `ks1` only. |
| **Bypass volume** — what the receive side kept at 0 | Phase 2 at *L* = 0: the live `…$CachedSerialization` count and the `deserialize` lines with `teeLen` above 1,000,000. | During the replay hold. | The replay must have run: confirm `grep -n -i replay logs/system.log` shows a replayed segment, and 24 `deserialize` lines. A graceful stop would flush the writes and leave nothing to replay; the kill must be `-9`. |
| **Real resource** — heap bytes of the copies | (1) `histo.sh`: the `[B` row (instances, bytes), and the live counts of the two classes, from `jcmd <pid> GC.class_histogram` (live objects only). (2) Unit: the slot's array length (retained, exact) and the thread's allocated bytes across the call (allocation, not retention); the scratch buffer's capacity, by reflection on `DataOutputBuffer.capacity()` (package-private). | Cluster: twice during each hold (5 s and 15 s after the 24th `held` line), once after the release, twice idle. Unit: around every probe. | **`[B` counts every byte array on the heap**, among them the held writes' payloads, so read only differences between runs with identical held writes (the reference, *L* = 1) and never an absolute value. The histogram runs a full collection: a few seconds, and the node is quiet while it runs. `getThreadAllocatedBytes` counts heap allocation, **not** the direct scratch buffer. Off-heap bytes are not measured at the node (no NMT): the scratch buffer is read only in the unit tier. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Each check is printed as `STAGE4 check <name> <expected> <actual> ok|MISMATCH`; record pass or fail and the values.

1. **Upstream suite.** Run `TeeDataInputPlusTest` (9c). Record pass or fail.
2. **Harness test, one JVM per value** (`100000`, `1000000`, `4000000`, `1`, `0`). In each JVM:
   1. *Setup:* print `MessagingService.current_version` and the slot ordinal; stop as Invalid if `isThreadAllocatedMemorySupported()` is false.
   2. *Read-back:* the private field and `getLong()` equal `-Dstage4.expect_limit`.
   3. *Calibrate* (*L* ≥ 100,000): build `m(p)` as `CommitLogTest.getMaxRecordDataSize()` does (`new RowUpdateBuilder(cfs.metadata(), 0, "k").clustering("bytes").add("val", ByteBuffer.allocate(p)).build()`);
      find *p\** = the largest payload with *T*(*p*) < *L* (start at *L* − 200 and walk, on fresh mutations); record *T*(*p\**), *T*(*p\** + 1), *k*.
   4. *Serialize site:* for the sizes *m*(1,024), *m*(*p\**), *m*(*p\** + 1), about 1.01 *L* and about 2 *L* (for *L* ≤ 1: 1,024, 100,000 and 3,000,000): warm up on a throw-away mutation of the same size; build a fresh `m`; read the scratch capacity *C*0 and
      the allocated bytes *A*0; call `Mutation.serializer.serializedSize(m, v)`; read *A*1 and the scratch capacity *C*1; read the slot (class, and for a `CachedSerialization` its `serialized.length`). Record Δ = *A*1 − *A*0 per size.
   5. *Receive site:* for the same sizes: serialize a fresh `m` into a plain `new DataOutputBuffer()` (not the scratch one) and keep its bytes *W*; deserialize a `DataInputBuffer(W)` with `Mutation.serializer.deserialize(in, v)`;
      read the slot (null, or a `CachedSerialization` with its length and `Arrays.equals(serialized, W)`); then call `serializedSize` on the result and read the slot again.
   6. *Tee alone:* with a source of 2 *L* bytes (3,000,000 for *L* ≤ 1) and a limit *L*: a tee reading *L* − 1 bytes in one `readFully` (skip for *L* ≤ 1) → `isLimitReached()` false and *L* − 1 bytes mirrored; a fresh tee reading *L* bytes (1 byte for *L* = 1) → true and 0 mirrored; for *L* = 0 a tee reading 3,000,000 bytes → false and 3,000,000 mirrored.
   7. *Idle:* the scratch capacity and the allocated bytes unchanged over 2 s with no call.

**Before the cluster tier:**

1. **Instrument check.** On the node, at *L* = 1,000,000 with the agent: (i) `TestScript` accepts both `.btm` files against `build/classes/main`; (ii) `histo.sh` prints the five figures; (iii) the idle control, two histograms 10 s apart; (iv) an unheld 1,024 B write prints a `serialize` line with `cached=CachedSerialization`; (v) `send-mutation.py many 100 24 90000` produces 24 `held` lines within 60 s, a histogram while they are held shows `…$CachedSerialization` +24, and all 24 return `OK` after the hold; (vi) `kill -9`, restart, and 24 `held` and 24 `deserialize` lines appear within 120 s. Any failure stops the run.
2. **Dataset check.** None: each value starts from an empty data directory.

**Cluster tier, for each value** (`4000000`, `1000000`, `100000`, `1`, `0`, in that order):

1. **Phase 1, control.** Fresh `data/`, `commitlog/` and `logs/`; `make-node-yaml.sh`; start the node with the property, the hold and the agent; wait for `UN` and for `bin/nodetool statusbinary` to print `running`; create the schema; check `jcmd <pid> VM.system_properties` shows the value. Two idle histograms 10 s apart. One unheld 1,024 B write; record its trace line.
2. **Phase 1, scenarios A and B.** Start the three `many` writers at once (8 × 90,000, 8 × 500,000, 8 × 2,000,000 bytes, primary keys 100 to 123). Wait for 24 lines in `hold.txt` (60 s at most). `histo.sh` 5 s and 15 s after the 24th. Record the counts, the `[B` row and the 24 `serialize` lines.
3. **Release.** Wait until all 24 writers have returned (45 s after their `held` lines at the latest); record each client line (all `OK` expected). `histo.sh` once more, 10 s after the last. `bin/nodetool` is not needed.
4. **Kill.** `kill -9` the node; check no `CassandraDaemon` is left. Keep `data/` and `commitlog/`.
5. **Phase 2, replay.** Start the node again with the same yaml, property, hold and agent, and **no wipe**. Wait for 24 lines in `hold.txt` (120 s at most). `histo.sh` 5 s and 15 s after the 24th. Record the counts, the `[B` row and the 24 `deserialize` lines. (Scenario C is this step at value `0`.)
6. **Release.** Wait for the replay to end and for `UN`; `histo.sh` once more. `grep -n -i replay logs/system.log` for a replayed segment.
7. **Stop.** `bin/nodetool stopdaemon`, check no daemon is left, copy `logs/system.log`, `hold.txt`, the trace and the histogram files to `~/stage4-logs/cms/<label>/`.

**Record for stage 4:** the `cassandra.yaml` diff against the shipped file and the JVM options in force, the exact commands, the node, OS, JDK, Ant and Byteman versions and the clone's commit, and the raw readings of 9d for every run: the trace files, the histogram lines, the client lines and the `system.log` excerpts. Keep the full logs on the node and a small excerpt per value in the results folder.

**Budget.** Unit: about 2.5 minutes to build; the upstream class takes seconds; the harness JVMs about 1 to 2 minutes each, so about 10 minutes. Cluster: about 90 s to start a node, about 2 minutes of holds and histograms per phase, so about 8 minutes per value and about 45 minutes for the five values with the instrument check. The largest write is 2 MB and the held total about 21 MB; the commit log and heap stay far below the node's limits (125 GiB of memory, 63 GB of local disk).

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — from [`../../../stage2-ai-preprocessing/bands.md`](../../../stage2-ai-preprocessing/bands.md)'s **band A1** list, rows `Mutation.java:451#1` ("serialized mutation size against the cacheable size limit, gating whether it is cached"; ranked in stage-2 batch 18, `bands.csv`, 2026-09-24) and, as its second site, `TeeDataInputPlus.java:58#1` ("tee buffer position plus length against the configured byte limit"; ranked in the stage-2 anchors pass, 2026-09-24; first recorded as `TeeDataInputPlus_limit` in the capacity-word pass of 2026-09-22). Judged in the band-A1 pass on 2026-09-28 and recorded in `pending.md`; written up 2026-10-06. |
| **Filed by / Date** | Claude (`claude-sonnet-5-5`) session, 2026-10-06 |
| **Line numbers checked** | 2026-10-06 against the local `cassandra-5.0.9` clone at `~/repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`, `HEAD` `b5f2a54210`). All 139 GitHub links in this file were checked by a script that opens each cited file, confirms the range exists, and finds the code the link is cited for inside it (the two links to the `if` at `serialization():451` were checked by reading). The plain `:NN` references in the text (`:446`, `:453-461`, `:578`, `:589-596`, `:67`, `:61`) and the Javadoc and call-site claims were checked by reading the lines; the history claims (CASSANDRA-17998, the two commits that touch the property's line) were read with `git log -G` and `git show`. |
| **Escape hatch / Target-3 note** | **A value of 0 (or less) turns the copy off on one side and removes its bound on the other** (§5, §6b step 6): the serialize side then caches nothing, and the receive side — the replica, replay, hint and batchlog readers — mirrors and caches every deserialized mutation whole, so its heap per mutation is the mutation, not the knob. It is a JVM property read at start-up, so it needs operator access to the node's command line; the unit tier and Phase 2 at value 0 measure it. Other observations, none of them a bypass of the disallow branch: (1) **the limit does not bound the mutation's own heap**, which exists in both outcomes (§2, §8); a client that sends many mutations just at or above the limit costs their own heap and CPU, and one that sends many just under it costs a copy more per mutation. (2) **Nothing counts the copy**: the in-flight request caps count request bytes, so the extra heap is outside every cap (§8). (3) **No live control**: no setter or JMX; a bad value stops the node at start-up (§4, derived, not run). (4) **Measuring builds the copy**: `validateSize()` reaches this check, so a coordinator caches below the limit even for a mutation it then refuses at `max_mutation_size`, if the cacheable limit were set above that one; at the defaults it is not (§5). (5) **Two copies in a mixed-version cluster**: the slots are per messaging version (§7). (6) The first computation is unsynchronized, so concurrent first callers may each build a copy and keep one; the coordinator's `prepareSerializedBuffer()` makes the first call single-threaded (`Mutation.java:428-437`, `StorageProxy.java:1495-1501`). |
| **Stage-4 feedback** | none yet. §9 was written in the new layout on 2026-10-06 (9a to 9e), not converted from an older §9; it is not yet audited (stage-4 README, step 0) and not yet run. It lists its harness as work for step 1. |
| **Notes** | **Found while writing this up (2026-10-06), for stage 3 to judge; `rejected.md` is not rewritten, and `pending.md` is updated only to strike the entry.** *The pattern is mixed, not (a) throughout:* `pending.md` records (a); the serialize site is (a), the receive site decides the buffer writes by (a) and the copy by a flag it sets (b) (§1, §5). *`TeeDataInputPlus_limit` is settled:* its `limit` is this constant, so it is a real constraint, as `pending.md` guessed, and its second site is part of this case; it adds the `limit <= 0` case that makes 0 an escape value (§5). *The check is reached from many more places than the write path:* the receive side from the inbound message handler, commit-log replay, hints, the batchlog, counter mutations and schema pulls, and the serialize side from every place a mutation is sized or written (§5, rows 1 to 7). *Outbound sizing uses the node's own version:* `OutboundConnection` sizes every message at `current_version` whatever the peer's version is (`OutboundConnection.java:1045-1048`), so a copy at a peer's different version, if there is one, is made later, when the message is serialized for that peer (inferred). *`max_mutation_size`'s §10 note is confirmed:* measuring a mutation below the limit serializes it into the scratch buffer and caches a `byte[]` (§5, row 1). |

---

## 11. Notes

- **Why one case for two check sites.** `serialization()` and `TeeDataInputPlus.maybeWrite()` read the same constant and decide the same thing (whether the mutation keeps a
  serialized copy), on the two ways a mutation comes to be serialized: by the node, and from bytes it received. README §6.1's "one case, several check sites" applies and the case is
  named after the primary site (`serialization():451`), with the tee listed in §1. The two are not the same pattern (§1), which `column_index_cache_size` also records.
- **Why this qualifies when `QueryProcessor.java:825` and `Message.java:817` were refused.** `rejected.md` refuses a per-item bound when something else holds the total, because
  "raising the limit alone moves no maximum". `QueryProcessor.java:825` only declines to cache an item larger than the whole cache, whose own capacity binds the heap, and
  `Message.java:817` bounds one message while a queue cap binds the bytes queued. Here nothing else bounds the copy: it sits on the mutation, not in a bounded cache, and no in-flight cap
  counts it. Raising this limit directly raises the largest copy a mutation keeps. What it does not move is a total, and §8 says so: the playbook's rule that a per-object limit needs a
  multiplier before it says anything about the node.
- **Why it is not refused as post hoc.** The mutation's own heap is spent before either check, as it is before `max_mutation_size`'s coordinator-side sites. This case does not rest
  on that heap: the object the check gates is the **copy**, and the copy is created only after the check (§5, "Does the check dominate the allocation?").
- **Both outcomes allocate.** The allow branch makes a scratch buffer's growth and a `byte[]`; the disallow branch makes a size-only object of a few words (and the scratch buffer is
  untouched). As in `column_index_cache_size`, the divergence is in **retained size**, not in whether anything is created, which is why the unit tier reads the slot's class and
  length rather than looking for an allocation.
- **The Javadoc and the default disagree.** [`Mutation.java:539`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L539) says serialized mutations "up to 2MB are
  kept on-heap"; the property declares 1,000,000 bytes ([`CassandraRelevantProperties.java:79-80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L79-L80)).
  This case uses the code's value. The feature is from CASSANDRA-17998 (`CHANGES.txt:540`, commit `227409d920`, 2022-12-19), which wrote the "2MB" Javadoc and the 1,000,000 default
  together; the one later commit that touches the property's line (`f650908648`, 2023-05-03, a refactor of how system properties are declared) keeps the value.
- **What this design does not cover.** The replica reached **over the wire** (it needs two nodes; the same `deserialize()` is exercised by replay, and the network path adds the inbound
  message handler and `Message$Serializer.deserialize()` in front of the same call); *N* varied; mixed messaging versions (two copies per mutation); counter mutations, hints' and the batchlog's own copies;
  the collector's behaviour under humongous objects, which is the source's stated reason for the threshold and is not measured; the CPU cost of regenerating bytes above the limit; a
  non-numeric property value (derived, destructive to run); and values of the property that a run cannot parse (`Long.decode` also accepts `0x…` and octal forms). Each is recorded from the
  source in §5, §6b or §8.
- **The replay arm is the receive site on a real node, not the network path.** Replay deserializes with the same call and the same tee, holds the deserialized mutation in a task's
  closure until the rebuilt one is applied ([`CommitLogReplayer.java:284-297`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L284-L297),
  [`:326`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L326)), and needs no second node; it is chosen for that reason, and the
  difference from the network path is recorded here so that a stage-4 reader does not read Phase 2 as a test of `MutationVerbHandler`.
- **The unit yaml is not the node's.** The unit yaml sets no `storage_compatibility_mode`; the shipped one sets `CASSANDRA_4`, so a node's `current_version` is 4.0. The harness prints it
  and reads the slot of that version, and nothing in this design depends on which it is.
- **Nothing here was run.** No measured number appears in this file; every figure in §9 is derived from the source and is a prediction.
