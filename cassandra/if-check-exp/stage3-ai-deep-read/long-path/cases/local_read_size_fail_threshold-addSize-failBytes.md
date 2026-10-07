# local_read_size_fail_threshold — local read (one `ReadCommand` on one replica)

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | LOCAL_READ_SIZE_FAIL_THRESHOLD-ADDSIZE-FAILBYTES |
| **Constraint** | `local_read_size_fail_threshold` — a **configuration entry** ([`Config.java:530`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L530), `volatile LongBytesBound`, default `null`, which switches the check off). The shipped yaml carries it only as a comment, [`conf/cassandra.yaml:2023-2026`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L2023-L2026), so it is **off by default**. It also needs the master switch `read_thresholds_enabled` ([`Config.java:526`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L526), default `false`); the unit-test yaml turns the switch on and sets this threshold to 8 MiB ([`test/conf/cassandra.yaml:63-69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/conf/cassandra.yaml#L63-L69)). **Live-settable** (§4). |
| **Enforcement pattern** | **(c)** — `addSize()` is a guard that throws before the *next* row is pulled; that row's creation is the fall-through, not a branch. **The guard does not dominate every path to the allocation** (§5): it runs after the row that crosses the limit has been built, after the rows of a names-filter point read have been materialized, and not at all for a read that does not set `trackWarnings` or that touches a system keyspace. |
| **Capacity check** | [`ReadCommand.QuerySizeTracking.addSize():715`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L715) — the usage-vs-limit comparison. One check site. Its warn twin, [`:724`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L724), only records a parameter (refused, [`rejected.md`](../rejected.md)). |
| **Decision point** | [`ReadCommand.QuerySizeTracking.addSize():722`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L722) — the throw. It leaves through `applyToRow():694`, `applyToMarker():701` or `applyToDeletion():708` into [`BaseRows.hasNext():133-148`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/transform/BaseRows.java#L133-L148), the loop that pulls the next row from the source, so no later row is pulled. |
| **Allocation site** | The next row of the merged iterator, built when [`BaseRows.hasNext():135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/transform/BaseRows.java#L135) asks the source for it (from an SSTable: [`UnfilteredSerializer.deserializeRowBody():635`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L635)), and then the serialized copy of every row that is let through, written into a **heap** `new DataOutputBuffer()` at [`ReadResponse.LocalDataResponse.build():199-201`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadResponse.java#L199-L201). |
| **Related cases** | [`row_index_read_size_fail_threshold-checkSize-failThreshold.md`](row_index_read_size_fail_threshold-checkSize-failThreshold.md) — the sibling: same master switch, same reporting channel, same `RejectException` handling; it guards the index entry a read opens, this guards the rows it takes from the data. [`column_index_cache_size-indexSamples-cacheSizeThreshold.md`](column_index_cache_size-indexSamples-cacheSizeThreshold.md) — what makes the sibling's object heavy or light. [`max_value_size-read-maxValueSize.md`](max_value_size-read-maxValueSize.md) — a per-value bound on the same data path. The coordinator-side `coordinator_read_size_fail_threshold` is a **different check** and is not judged here (§10). |

```java
// ReadCommand.withQuerySizeTracking():663-728 — the wrap and the check (QuerySizeTracking is a local class)
private UnfilteredPartitionIterator withQuerySizeTracking(UnfilteredPartitionIterator iterator)
{
    DataStorageSpec.LongBytesBound warnThreshold = DatabaseDescriptor.getLocalReadSizeWarnThreshold();
    DataStorageSpec.LongBytesBound failThreshold = DatabaseDescriptor.getLocalReadSizeFailThreshold();   // :666
    if (!shouldTrackSize(warnThreshold, failThreshold))       // :667 — trackWarnings && !system keyspace && a threshold is set
        return iterator;                                      // not wrapped: nothing is counted
    final long warnBytes = warnThreshold == null ? -1 : warnThreshold.toBytes();
    final long failBytes = failThreshold == null ? -1 : failThreshold.toBytes();                         // :670
    class QuerySizeTracking extends Transformation<UnfilteredRowIterator>
    {
        private long sizeInBytes = 0;                                                                    // :673
        // applyToPartition():676-680 adds sizeOnHeapOf(partition key) with no check
        // applyToRow() / applyToMarker() / applyToDeletion() call addSize(x.unsharedHeapSize())
        private void addSize(long size)
        {
            this.sizeInBytes += size;
            if (failBytes != -1 && this.sizeInBytes >= failBytes)                                        // <-- capacity check, :715
            {
                String msg = String.format("Query %s attempted to read %d bytes but max allowed is %s; query aborted  (see local_read_size_fail_threshold)", ...);
                Tracing.trace(msg);                                                                      // :719
                MessageParams.remove(ParamType.LOCAL_READ_SIZE_WARN);
                MessageParams.add(ParamType.LOCAL_READ_SIZE_FAIL, this.sizeInBytes);                     // :721
                throw new LocalReadSizeTooLargeException(msg);                                           // <-- disallow, :722
            }
            else if (warnBytes != -1 && this.sizeInBytes >= warnBytes)                                   // warn twin, :724
                MessageParams.add(ParamType.LOCAL_READ_SIZE_WARN, this.sizeInBytes);
        }                                                                                                // allow: returns, the row is passed on
    }
    iterator = Transformation.apply(iterator, new QuerySizeTracking());                                  // :739
    return iterator;
}
```

## 2. Context

A replica answers a read by pulling rows out of its memtables and SSTables, merging them, and writing the survivors into a response that it holds in memory until it is sent. A single read can ask for a very wide partition or a large scan, and nothing in the read path otherwise caps how much one such request makes a replica build. This guardrail adds up the in-memory size of everything the storage layer hands to one local read — each row, each range-tombstone marker, each deletion and each partition key — and stops the read as soon as the running total reaches a configured byte limit. The aim is that one bad query cannot, by itself, exhaust a node's heap.

It is a **guardrail that is off until an operator turns it on**: the limit has no default value and a separate master switch must also be on. When it fires, the replica does not fail the way a write does; it sends the coordinator an **empty answer with a note attached**, and the coordinator turns the notes it collects into the client's error (or into a warning, if enough other replicas answered).

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `read_path` — the replica-side read (`db/ReadCommand`, `db/transform`, `db/rows`), and the reporting of its guardrails to the client (`service/reads/thresholds`, `net/ParamType`) |
| **One-line role** | `ReadCommand.executeLocally()` turns a read request into a stream of merged rows; the guardrails wrap that stream and report what they saw back to the coordinator. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes, with a scope that is narrower than its name.** It compares a **running total of the heap size of what one local read has pulled from storage** with a byte limit. The total is a *flow*, not a gauge of what is resident at once (rows are not retained after they are serialized), and it is **per command**: each page of a paged query, and each partition of a multi-partition read, is a separate `ReadCommand` with its own counter (§5). |
| **Usage-side operand** | `this.sizeInBytes` ([`ReadCommand.java:673`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L673)), the sum of `ObjectSizes.sizeOnHeapOf(partitionKey)` ([`:678`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L678), added **without** a check) and of `unsharedHeapSize()` of every static row, row, marker and partition-level deletion that passes ([`:694`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L694), [`:701`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L701), [`:708`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L708)). For a row that is [`BTreeRow.unsharedHeapSize():532-541`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/BTreeRow.java#L532-L541): the row object, its clustering, liveness and deletion, the BTree skeleton and every cell, a cell being [`BufferCell.unsharedHeapSize():141-144`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/BufferCell.java#L141-L144) — object header plus the value's bytes. It is neither the serialized size nor the bytes sent to the client. |
| **Limit-side operand** | `failBytes`, a `final long` local of `withQuerySizeTracking()` ([`:670`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L670)); `-1` when the entry is `null`. It is captured **once when a command's iterator is wrapped**, so a change applies to commands that start afterwards, not to one already running. |
| **Limit type** | **Configuration entry**, used raw (no derivation), default `null` = off, **live-settable**. |

**Limit initialization path** (declare → validate → store → read):

1. [`Config.local_read_size_fail_threshold:530`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L530) — declared, `volatile DataStorageSpec.LongBytesBound`, default `null`.
2. [`DatabaseDescriptor.applySimpleConfig():785`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L785) → [`applyReadThresholdsValidations():1092-1105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1092-L1105) — the only startup check: when both are set, `fail` must be at least `warn`, else `ConfigurationException`. No range, no derivation.
3. [`DatabaseDescriptor.getLocalReadSizeFailThreshold()/setLocalReadSizeFailThreshold():4903-4912`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4903-L4912) — the field is read and written **live**; the setter logs `updating local_read_size_fail_threshold`. The same pair is exposed as the JMX attribute `LocalReadTooLargeAbortThreshold` on `StorageService` ([`StorageService.java:7322-7331`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L7322-L7331)); no `nodetool` command wraps it.
4. [`ReadCommand.withQuerySizeTracking():665-670`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L665-L670) — read at the wrap; compared at [`:715`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L715).
5. **The gate before the check.** [`ReadCommand.shouldTrackSize():656-661`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L656-L661) wraps the iterator only if the command `trackWarnings`, its keyspace is not a system keyspace ([`SchemaConstants.isSystemKeyspace():144-148`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/SchemaConstants.java#L144-L148)) and at least one of the two thresholds is set. `trackWarnings` is set in exactly three places: [`SelectStatement.execute():334-335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L334-L335) for a client `SELECT` when `options.isReadThresholdsEnabled()`; [`ReadCommandVerbHandler.doVerb():88-89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommandVerbHandler.java#L88-L89) on a replica, from a flag in the message that [`ReadCommand.createMessage():837-838`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L837-L838) sets; and [`SinglePartitionReadCommand.forPaging():468-469`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java#L468-L469), which copies the flag onto the next page. The master switch is read **per request**: [`QueryOptions.ReadThresholds.create():275-281`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L275-L281) is the initializer of a field ([`:346`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L346)) of the options object built for each client request.

**Naming note (Target 1).** The constraint is named after the first-declared variable on the path, the configuration entry; `addSize` is the method that encloses the comparison and `failBytes` is the operand as written there (README §6.1).

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`ReadCommand.QuerySizeTracking.addSize():722`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L722) |
| **Verdict** | Pattern (c): the guard is the `throw`; there is no flag or enum. The exception is a `RejectException` ([`LocalReadSizeTooLargeException.java:23`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/filter/LocalReadSizeTooLargeException.java#L23)), a `RuntimeException`. **The verdict also travels as a parameter:** `addSize()` puts `LOCAL_READ_SIZE_FAIL` and the total into the thread's `MessageParams` ([`:721`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L721)), which the replica attaches to its reply (§6b). |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `sizeInBytes < failBytes`, or `failBytes == -1` | `addSize()` returns (after recording the warn parameter if the warn threshold is set and reached); `BaseRows.hasNext()` hands the row on and the consumer serializes it into the response buffer |
| **Disallow** | `sizeInBytes >= failBytes` | the message is traced, the fail parameter is set and `LocalReadSizeTooLargeException` leaves `hasNext()`: **no further row is pulled** and no response is built |

```java
// allow — BaseRows.hasNext():133-157: the source builds the row, the transformation counts it, the row is passed on
Unfiltered next = input.next();                          // :135 — the row exists from here
...  row = fs[i].applyToRow(row);                        // :141 — QuerySizeTracking.applyToRow() -> addSize()
if (next != null) { this.next = next; return true; }     // :154-157 — the consumer receives it
```

```java
// disallow — ReadCommand.addSize():717-722
Tracing.trace(msg);
MessageParams.remove(ParamType.LOCAL_READ_SIZE_WARN);
MessageParams.add(ParamType.LOCAL_READ_SIZE_FAIL, this.sizeInBytes);
throw new LocalReadSizeTooLargeException(msg);
```

### What the total counts, and where it counts it

- **After the merge, before the filter, the purge and the limit.** [`ReadCommand.executeLocally():457`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L457) is applied to the merged storage iterator; the row filter ([`:473`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L473)), the purge of expired tombstones and the limit ([`:491`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L491)) come after. So it counts what storage yields, **not what is returned**: rows later dropped by `ALLOW FILTERING` are counted, and so are purgeable tombstones. A `LIMIT` still stops the pulling and so ends the count.
- **`>=`.** A read whose total reaches the limit exactly is aborted.
- **One row of overshoot.** The row that brings the total to the limit has already been built when `addSize()` sees it (`BaseRows.hasNext():135` precedes `:141`); it is never delivered, but its allocation was not prevented. The most the guard lets one command build is `limit + one row` (or marker) in heap-size units.
- **The partition key is counted but never trips the check** (`:678` adds it directly): the check runs at the next row, marker or deletion.
- **Per command, not per query.** The counter lives in the `QuerySizeTracking` instance created for one `executeLocally()`. A paged query is one command per page (the next page is built by `forPaging()`), and a multi-partition `IN` read is one command per partition, so the config text's "query" means a *command*. A query paged into pieces that each stay under the limit is never aborted however much it reads in total.
- **Not counted:** the SSTable read buffers, the index entries (the sibling's object), the caches, the response buffer's own growth slack, and the coordinator's merge of the replies.

### Does the guard dominate the allocation?

**For the rows that follow the crossing row on a streamed read, yes.** Every row of a read that is wrapped passes `addSize()` before it reaches the consumer and before the next one is pulled: `BaseRows.hasNext()` is the only way rows leave a wrapped partition. The guard is not on every path, though:

- **Names-filter point reads materialize first.** For a single-partition read whose filter is a `ClusteringIndexNamesFilter` (`WHERE pk = ? AND ck IN (...)` or `ck = ?`) on a table with no counters and no non-frozen collections, and not tracking repaired status, [`SinglePartitionReadCommand.queryMemtableAndDiskInternal():700-707`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java#L700-L707) takes [`SinglePartitionReadCommand.queryMemtableAndSSTablesInTimestampOrder():951-957`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java#L951-L957), which reads the requested rows from each source into an `ImmutableBTreePartition` through [`add():1062-1075`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java#L1062-L1075), `maxRows` being the number of requested rows. All of them are built **before** `withQuerySizeTracking()` has wrapped anything, so for this path the guard is post hoc: it sees the rows when the finished partition is iterated. The cost is bounded by the number of rows asked for, not by the limit.
- **A read that does not set `trackWarnings`** is not wrapped (§4, step 5): every read that is not a client `SELECT` through `SelectStatement.execute()` — the internal path [`SelectStatement.executeLocally():574-576`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L574-L576) sets nothing — and every read when the coordinator's `read_thresholds_enabled` is off.
- **System keyspaces** are exempt (§4, step 5).
- **A cached partition** is already materialized: when the table's row cache is enabled the read goes through [`getThroughCache()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java#L491-L493) first. The row cache is off by default: it needs a `row_cache_size` above zero ([`Config.java:474`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L474)) and a table that opts in ([`ColumnFamilyStore.isRowCacheEnabled():3259-3262`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3259-L3262)); this design does not exercise it.
- **Rows already in a memtable** are counted by `unsharedHeapSize()` like any other, although they are the memtable's own objects and the read does not newly allocate them (inferred from the iterator code, not verified). The designed runs flush first so that every counted row is built by the SSTable deserializer.

## 6. Code path

### 6a. Allow path → object creation

1. [`SelectStatement.execute():334-335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L334-L335) — a client `SELECT` sets `trackWarnings` on its `ReadQuery` when the master switch is on. The flag reaches a remote replica as a message flag ([`ReadCommand.createMessage():837-838`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L837-L838) → [`ReadCommandVerbHandler.doVerb():88-89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommandVerbHandler.java#L88-L89)); a local replica uses the command object itself.
2. [`StorageProxy.LocalReadRunnable.runMayThrow():2208-2212`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2208-L2212) (local) or `ReadCommandVerbHandler.doVerb()` (remote) → [`ReadCommand.executeLocally():426`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L426) builds the storage iterator and wraps it at `:457`; `shouldTrackSize()` is true, so `QuerySizeTracking` is attached at `:739`.
3. [`ReadCommand.withQuerySizeTracking():739`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L739) returns the wrapped iterator; `executeLocally()` adds the purge, the metrics, the row filter and the limit above it and returns. The wrapped storage iterator is **lazy**: nothing has been counted yet.
4. [`ReadCommand.createResponse():366-374`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L366-L374) — the caller (`ReadCommandVerbHandler.doVerb():94-95`, `LocalReadRunnable.runMayThrow():2208-2211`) hands the lazy iterator to `createResponse()`. A **data** response drains it into a buffer, [`ReadResponse.LocalDataResponse.build():197-203`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadResponse.java#L197-L203); a **digest** response (the other replicas of a multi-replica read) hashes the rows instead and keeps no buffer, so for a digest read the guard gates only the rows' creation, not a retained buffer.
5. [`BaseRows.hasNext():133-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/transform/BaseRows.java#L133-L157) — the loop asks the source for the next unfiltered (**the row is built here**: for SSTable data by [`UnfilteredSerializer.deserializeRowBody():564-635`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L564-L635)), runs it through `QuerySizeTracking.applyToRow()` and, if `addSize()` returns, makes it the `next` element and returns `true`.
6. [`ReadCommand.addSize():712-714`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L712-L714) adds the row's `unsharedHeapSize()`; `:715` is false; `:724` records the warn parameter if the warn limit is set and reached; the row is serialized into the response buffer, which is **grown** when full by [`DataOutputBuffer.expandToFit():174-182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L174-L182) (doubling, or ×1.5 above the doubling threshold, [`calculateNewSize():158-170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L158-L170)). The buffer is on the **heap**: this `DataOutputBuffer` is the no-argument one, whose buffer comes from [`BufferedDataOutputStreamPlus.allocate():75-78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/BufferedDataOutputStreamPlus.java#L75-L78), not the direct scratch buffer of the commit log.

### 6b. Disallow path effect

1. [`addSize():715-722`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L715-L722) traces the message, replaces the warn parameter by the fail parameter and throws. **Nothing is rolled back and nothing else is prevented at that point:** the crossing row exists and is dropped; `hasNext()` leaves by the exception, so the loop never asks the source for another row; the exception passes through `LocalDataResponse.build()` (it catches `IOException` only, [`:204-208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadResponse.java#L204-L208)), the try-with-resources closes the buffer and its content becomes garbage, so **no response is built**. The caller's try-with-resources closes the iterators; [`onClose():731-736`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L731-L736) records the total in the `LocalReadSize` histogram (bucketed, so not an exact reading).
2. **The replica swallows the exception and answers empty.** Remote replica: [`ReadCommandVerbHandler.doVerb():97-110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommandVerbHandler.java#L97-L110) — because `command.isTrackingWarnings()` is true whenever this guard ran, the `RejectException` is caught, logged at **ERROR** (`:103`), replaced by `createEmptyResponse()` ([`:377-384`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L377-L384)) and sent with the thread's `MessageParams` attached. Local replica (the coordinator reading its own data): [`StorageProxy.LocalReadRunnable.runMayThrow():2213-2220`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2213-L2220) — the same replacement, no log line, then `handler.response(response)` (`:2230`), which attaches the parameters at [`ReadCallback.response():227-233`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/ReadCallback.java#L227-L233).
3. **The coordinator decides.** [`ReadCallback.onResponse():192-199`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/ReadCallback.java#L192-L199) → [`WarningContext.updateCounters():46-80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/thresholds/WarningContext.java#L46-L80) maps `LOCAL_READ_SIZE_FAIL` to `READ_SIZE` ([`RequestFailureReason.java:37`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/exceptions/RequestFailureReason.java#L37), code 4) and records the abort, and the replica counts as a failed response. In [`awaitResults():128-178`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/ReadCallback.java#L128-L178) the snapshot is merged into the coordinator's state at `:155-156` **before** the early return for a satisfied read at `:158`; when the failures leave fewer than `blockFor` data responses, [`WarningsSnapshot.maybeAbort():107-115`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/thresholds/WarningsSnapshot.java#L107-L115) throws `ReadSizeAbortException` and the client receives a read failure whose failure map holds `READ_SIZE` (the map is sent from native protocol 5; earlier protocols carry only the count). [`CoordinatorWarnings.done():79-102`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/thresholds/CoordinatorWarnings.java#L79-L102), called from [`Dispatcher.processRequest():419` and `:441`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L419), logs `<n> nodes loaded over <X> bytes and aborted the query … (see local_read_size_fail_threshold)` at WARN, adds it to the client's warnings and marks the table meter `LocalReadSizeAborts` ([`:94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/thresholds/CoordinatorWarnings.java#L94)). **When other replicas answer enough** (RF above 1 and the consistency level met without the aborting one), the read succeeds and only that warning and the meter record the abort: the guard bounds a replica's work, not the query's success (derived from the source, not run).
4. **Not a block, a retry or a hint.** The aborted command is not retried or speculated; the client sees the failure and decides.
5. **If the check were absent.** The command would keep pulling rows until the source is exhausted, the limit of the query is reached or the read times out. No other replica-side bound is in byte units: `max_value_size` is per value, the tombstone thresholds count tombstones, and the coordinator-side guardrail is a different check (§10). Derived from the source, not run.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | Each row the source builds for the command (a `BTreeRow` with its cells) and, for a data response, the serialized copy of every row that is let through, in a heap `DataOutputBuffer`. |
| **Resource consumed** | **Heap bytes.** The rows are transient (garbage once serialized); the response buffer is retained until the reply has been sent. |
| **Rough sizing** | A row costs its `unsharedHeapSize()` (§4): the object headers of the row, clustering, liveness, BTree and cells plus the value bytes. A row with a 1,000-byte blob costs 1,000 bytes plus that overhead; the overhead is not measured here (§9 measures it). The response buffer holds the **serialized** rows, which are smaller than their heap size; its capacity can be up to twice its content (doubling), or 1.5 times above the doubling threshold (inferred from `calculateNewSize()`). |
| **Lifetime / release** | A row is garbage after it has been serialized. The buffer is released when the reply message has been serialized for sending (a local reply when the coordinator has consumed it). |

## 8. Maximum memory/disk bound

`local_read_size_fail_threshold` bounds **what one local read command can build**: the running total of the heap sizes of what the storage layer yields to it. A read stops at the first row whose total reaches the limit, so the rows it has built are at most `limit` plus one row, and the response buffer built from the rows it let through holds at most about `limit` in serialized form (serialized rows are smaller than their heap size; inferred). Raising or lowering the limit moves that ceiling **one for one**.

It is **not a node-wide ceiling.** The counter belongs to one command, so the memory this admits is `limit × N`, *N* being the commands being executed at once. The Read stage has `concurrent_reads` threads ([`Config.java:179`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L179), 32; wired at [`Stage.java:45`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/Stage.java#L45)), so at stock thread counts the guard admits up to 32 × `limit` of freshly built row heap at once (an upper bound the guard allows, not a figure measured here), and reply buffers that are waiting to be sent outlive their thread. A query is not bounded either: it can be paged into commands that each stay below the limit, and a multi-partition `IN` read runs one command per partition.

It bounds **none** of: the row-index entries a read opens (the sibling case), the SSTable read buffers and the caches, the coordinator's own merge and result set (`coordinator_read_size_*`, a different guardrail), the rows of a names-filter read, which are built before the guard sees them (§5), or anything when the master switch is off (the default).

**Other limits interact with it,** which matters to a sweep (§9b holds them fixed): `read_thresholds_enabled` is the master switch for the whole family; `coordinator_read_size_*`, `row_index_read_size_*` and the tombstone thresholds abort a read in the same reporting channel and would be read as this guard if they fired; `read_request_timeout` ends a read that is slow rather than large.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test builds one wide partition of identical rows and reads it as one command at several values of `local_read_size_fail_threshold`. It checks that the read stops at the first row whose running total reaches the limit — the unit tier by exact arithmetic on the check's own counter, the cluster tier through the numbers the node reports — and that the bytes the replica thread allocates stop growing there. Three arms run the paths that should escape the guard. **Run so far:** none. Written in this layout on 2026-10-06; not yet audited (stage-4 README, step 0).

### 9a. Procedure and conclusions

**Testability:** config, **live-settable**. The unit tier calls `DatabaseDescriptor.setLocalReadSizeFailThreshold()` and changes the value inside one JVM; the cluster tier starts the node once per value (the JMX attribute `LocalReadTooLargeAbortThreshold` could change it live, but the exact `nodetool sjk mx` call to set it has not been checked, so it is not relied on). The master switch `read_thresholds_enabled` must be on and the command must carry `trackWarnings` (§4). No patched build is needed; the cluster tier's allocation reading is a Byteman observation rule (harness work, 9c).

**Claim under test:** with the master switch on, `local_read_size_fail_threshold` caps what one local read command can pull from storage. When the running total of the heap sizes of the partition key, rows, markers and deletions it has taken reaches the limit (`>=`), `addSize()` throws `LocalReadSizeTooLargeException`, so the command has built at most one row beyond the limit, builds no response, and the replica answers empty; the coordinator turns that into a `READ_SIZE` read failure. The limit is per command, counts what storage yields before any filtering, and does not cover a names-filter point read, whose rows are built before the guard (§5, §6b, §8).

**How this verifies the hypothesis** (a restatement of the claim, procedure, prediction and conclusions in this section; it adds none):

- **Hypothesis:** the constraint caps the heap one local read can build, and a read that reaches the cap stops without building more.
- **Test:** vary the limit over three values per tier, plus a value above the data and the default (unset). At each, read one partition of identical rows in one command. Unit tier: mirror the check's arithmetic from the rows' own `unsharedHeapSize()`, count the rows delivered before the abort, and measure the bytes the thread allocates. Cluster tier: read the check's operand from the numbers the node prints, find the largest read that completes, and read the bytes the replica thread allocates (Byteman). Then run the arms that should escape it: a names-filter read, a paged read and a filtered read.
- **Logic:** (1) the mirror reproduces the check's counter exactly (a known answer), else the run is invalid. (2) The read delivers exactly *i\** − 1 rows and the counter at the abort is *T*(*i\**), where *i\** is the first row whose running total reaches the limit; a total of exactly the limit aborts: usage **stops at the limit**. (3) The largest completed read, the abort counter and the bytes allocated follow the limit in the ratio 1 : 4 : 16: usage **follows the constraint**. (4) The abort carries the guard's message, the `READ_SIZE` failure and the `LocalReadSizeAborts` meter: the guard, not something else, enforces it. (5) The three arms show where it does not bind.
- **Refuted if:** a read completes with a total at or above the limit; an aborted read keeps allocating as the partition grows; the counter at the abort depends on the partition's size; or the largest completed read does not move with the knob (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — set up as in 9b; run the harness test `LocalReadSizeGuardTest` (9c) in one JVM over all values.
2. **Cluster tier** — set up as in 9b; for each value start a node, load one partition, flush, and run the reads of 9e.
3. **At each value:** idle control → **scenario A**, reach the limit (the largest read that completes) → **scenario B**, try to exceed it (one row more, the whole partition) → **scenario C**, the bypass arms (names filter, paging, filter that matches nothing).
4. **Compare** with the prediction below and read the result in the table.

**Prediction** (stated before any run, in numbers). Notation: *F* = the limit in bytes; *b0* = `sizeOnHeapOf(partition key)` plus the partition-level deletion's `unsharedHeapSize()` (0 for a live partition, [`DeletionTime.java:183-188`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/DeletionTime.java#L183-L188)); *h* = one row's `unsharedHeapSize()`, equal for all rows by construction and **measured**, not assumed; *N* = rows in the partition; *T*(*i*) = *b0* + *i*·*h*, the counter after row *i*; *i\**(*F*) = the least *i* with *T*(*i*) ≥ *F*, that is ⌈(*F* − *b0*)/*h*⌉.

*Unit tier*, *N* = 2,000 rows of 1,000-byte blobs, one flushed SSTable, at *F* = 65,536 · 262,144 · 1,048,576 · 8,388,608 (the unit yaml's own value, above the data) and unset:

- **Read-back:** `getLocalReadSizeFailThreshold().toBytes()` equals *F* after each set.
- **Known answer:** a read with only the warn limit set (1 B) completes, and `MessageParams.get(LOCAL_READ_SIZE_WARN)` equals the mirror's *T*(*N*) exactly.
- **Stop:** at each *F* below *T*(*N*) the read delivers exactly *i\**(*F*) − 1 rows and throws `LocalReadSizeTooLargeException` whose message contains `attempted to read <X> bytes`, with *X* = `MessageParams.get(LOCAL_READ_SIZE_FAIL)` = *T*(*i\**) and *F* ≤ *X* < *F* + *h*.
- **Boundary (`>=`):** at *F* = *T*(100) the read delivers 99 rows and aborts; at *F* = *T*(100) + 1 it delivers 100 and aborts at row 101.
- **Above the data and off:** at 8,388,608 (> *T*(*N*) for any *h* < 4,000) the read delivers all *N* rows with no exception and no fail parameter; with both limits unset, nothing is counted at all (no parameters).
- **Allocation:** across `createResponse()`, the thread's allocated bytes are Δ(*F*) = Δ0 + *a*·*i\**(*F*), Δ0 being the cost of a read of one row and *a* the per-row allocation measured from the unlimited read; so Δ(*F*) − Δ0 is in the ratio 1 : 4 : 16 over the three values, within the spread of the repeated runs (stage 4 sets the tolerance; 15 % is the starting guess).
- **Arm C1, names filter:** for a `ClusteringIndexNamesFilter` of *M* = 1,000 rows at *F* = 65,536 the read aborts (*T*(*M*) ≥ *F*), but Δ is within 10 % of Δ for the same filter with the limit unset, because the rows are built first; a slice read of the same 1,000 rows at the same *F* allocates about *i\**/*M* of that (about 5 % if *h* is about 1.3 KB) plus Δ0.
- **Arm C2, paging:** *N*/*p* commands of *p* = 100 rows (`forPaging()`) at *F* = 262,144 all complete — each total is *b0* + 100·*h* < *F* — and deliver all 2,000 rows although the sum of their totals is far above *F*; at *F* = 65,536 the first command aborts.
- **Arm C3, filter:** a `RowFilter` that matches no row delivers 0 rows and still aborts at *i\**(*F*) when *F* < *T*(*N*); with the limit unset it completes with 0 rows.
- **Control, no flag:** the same read without `trackWarnings()` at *F* = 65,536 completes, delivers all rows and sets no parameter.
- **Control, warn twin:** with warn = 65,536 and fail unset the read completes and the warn parameter is *T*(*N*).

*Cluster tier*, one node, RF 1, *N* = 8,000 rows of 1,000-byte blobs (*T*(*N*) is about 10 MB if *h* is about 1.3 KB; the run is **invalid** if *T*(*N*) ≥ 16 MiB), at *F* = 262,144 · 1,048,576 · 4,194,304 · 16,777,216 (above the data) and unset. *b0* and *h* come from the calibration reads at the 16 MiB value: *h* = (*T*(*N*) − *T*(100))/(*N* − 100), *b0* = *T*(100) − 100·*h*.

- **Read-back:** the abort message's `max allowed is` shows *F*.
- **Scenario A:** `SELECT … WHERE pk = 1 AND ck < p*` with *p\** = *i\**(*F*) − 1 completes, with warn-text *X* = *T*(*p\**) < *F*; it is the largest read that does. *p\** is about 200 · 800 · 3,200 at the three values: **1 : 4 : 16**.
- **Scenario B:** `ck < p*+1` aborts with *X* = *T*(*i\**) ≥ *F*; **the whole partition (8,000 rows) aborts with the same *X***: the counter does not depend on *N*.
- **Evidence:** each abort gives a client `ReadFailure` whose failure map has code 4, one more `LocalReadSizeAborts` on the table, the trace event with *X* and *F*, and the coordinator's WARN line `1 nodes loaded over <X> bytes and aborted the query`.
- **Real resource:** the replica thread's allocated bytes for the whole-partition read at *F* equal, within the spread, those for the read of exactly *i\** rows at *F*, and the increments between values are in the ratio (1,048,576 − 262,144) : (4,194,304 − 1,048,576) = **1 : 4**; at the 16 MiB and unset values the whole-partition read completes and allocates about *N*/*i\** times more.
- **Arm C1:** `ck IN (0 … 1999)` (*M* = 2,000) aborts at 262,144 and 1,048,576 and completes at 4,194,304 (*T*(*M*) < *F*), and at 262,144 its allocated bytes are within 10 % of the same read with the limit unset, while the slice `ck < 2000` at 262,144 allocates about *i\**/*M* of that.
- **Arm C2:** `fetch_size` 100 (about 130 KB per command) completes at 262,144 and delivers all 8,000 rows; `fetch_size` 1,000 aborts at 262,144 and 1,048,576 on its first page and completes at 4,194,304.
- **Arm C3:** `… WHERE pk = 1 AND v = 0x<no match> ALLOW FILTERING` returns 0 rows and aborts at 262,144, 1,048,576 and 4,194,304, and completes at 16 MiB and unset.

**Conclusions.**

| Result | Conclusion |
|---|---|
| Unit: the mirror equals the check's counter, each read delivers exactly *i\**−1 rows and aborts with *X* = *T*(*i\**), the boundary pair behaves as `>=` predicts, and the allocation follows *i\**. Cluster: *p\**, *X* and the allocation follow the knob (1 : 4 : 16), every abort carries the guard's message, the failure code and the meter, and *X* does not depend on *N* | **Confirmed** — the check enforces as traced, per command. |
| A names-filter read allocates as much with the limit as without (C1); a paged read of the same partition completes although its total is far above *F* (C2); a read without the flag, in a system keyspace or with the master switch off is not counted | **Bypass as recorded** — expected, not a refutation (§5). Record the volume: Δ of the names read, the rows of the paged read. |
| A read completes with a counter at or above *F*, or a read delivers *i\**+1 or more rows | **Refuted** — the guard does not stop at the limit (§6b is wrong). Re-read. |
| An aborted read's allocation keeps growing with the partition (the whole-partition read allocates more than the *i\**-row read, beyond the spread) | **Refuted** — the abort does not prevent later rows from being built, or the response is built anyway. Re-read §6b. |
| *X* depends on *N*, or *p\** is the same at every value | **Refuted** — not the binding limit. Re-read, do not re-run. |
| *p\** and the allocation move with the knob, but an abort lacks the guard's message or the failure code 4 (a different read-failure reason appears) | **Not confirmed** — something else in the same reporting channel binds (`row_index_read_size_*`, `coordinator_read_size_*`, a tombstone limit; §8). Check the hold-fixed settings (9b). |
| A filtered read that returns nothing is not aborted (C3) | **Refuted in part** — the guard sits after the filter, not before it (§5). |
| The mirror differs from the check's counter; the limit read back differs from the value set; *T*(*N*) ≥ the largest value; `getThreadAllocatedBytes` is unsupported; the rows are not read from an SSTable; the read fails for a reason other than the guard's | **Invalid run** — fix the setup (9b, 9c) and re-run. |

Two rules behind this table:

- **A confirmation needs both** the ceiling moving with the knob **and** direct evidence that the guard fired: here the message that prints both operands (*X* and *F*), the `READ_SIZE` code and the meter. A curve alone could come from the sibling guardrails, which report through the same channel.
- **The escapes are attributed** by arms in which the bypass cannot fire: the slice read of the same rows (C1) is guarded and the names read is not, the first page of a paged read aborts when it alone reaches *F* (C2), and the same read without the flag is not counted. Without them "bypass" and "does not cap" look the same.

**Why the message and the warn text, not the histogram:** the `LocalReadSize` histogram is a bucketed estimate and cannot resolve a boundary of one row; the abort message and the warn text print `sizeInBytes` itself.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `local_read_size_fail_threshold` in `cassandra.yaml` (the entry as §4's path names it), with `read_thresholds_enabled: true`. **Live-settable.** Unit tier: `DatabaseDescriptor.setLocalReadSizeFailThreshold(new DataStorageSpec.LongBytesBound(<bytes>, BYTES))` before each step; no yaml copy is needed because the setter is the knob. Cluster tier: the two lines in the run clone's `conf/cassandra.yaml`, one node start per value. |
| **Confirm it took effect** | Unit: the harness test prints and asserts `getLocalReadSizeFailThreshold().toBytes()` after each set. Cluster: the first abort prints `but max allowed is <F>` (the spec as a string, for example `256KiB`) and `X` there is the counter; a secondary read to try at the instrument check: `SELECT name, value FROM system_views.settings WHERE name = 'local_read_size_fail_threshold'` (its absence is not a failure). |
| **Capacity values** | **Unit:** 65,536 B, 262,144 B, 1,048,576 B, 8,388,608 B (above the data) and unset. **Cluster:** 262,144 B (256 KiB), 1,048,576 B (1 MiB), 4,194,304 B (4 MiB), 16,777,216 B (16 MiB, above the data) and unset (the default). There is no derived value; the default is "off". |
| **Scope** | **Per command** (§5). One request at a time, so *N* = 1 command in every run; §8's `limit × N` claim is **not tested**, and arm C2 shows the per-command scope directly. One node, RF 1: no remote replica, no digest read, no replica to spare. |
| **Level** | Both. **Unit:** the harness test `LocalReadSizeGuardTest`; no upstream unit test reaches this check. **Related upstream, optional:** `LocalReadSizeWarningTest` ([`LocalReadSizeWarningTest.java:32-52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/distributed/org/apache/cassandra/distributed/test/thresholds/LocalReadSizeWarningTest.java#L32-L52)), an in-JVM dtest on three nodes at one pair of limits (1 KiB warn, 2 KiB fail) with 512-byte rows, run with `ant test-jvm-dtest-some -Dtest.name=org.apache.cassandra.distributed.test.thresholds.LocalReadSizeWarningTest` (heavy: three in-JVM nodes, `-Xmx8G`). **Cluster:** one node. |

**What the upstream test does and does not show.** It builds a three-node in-JVM cluster, sets warn at 1 KiB and fail at 2 KiB, and checks for a point read and a scan that a read under the limits has no warnings, one over the warn limit gets the client warning, one over the fail limit raises `ReadSizeAbortException` with `READ_SIZE` in the failure map, and the table meters `LocalReadSizeWarnings` and `LocalReadSizeAborts` and the client-request abort meter move; with the master switch off the same reads are not counted. It does **not** show any other value, the exact boundary, how many rows were delivered or allocated before the abort, the names-filter, paged or filtered reads, a real node, or anything about memory. The harness test and the cluster tier add those.

**Hold fixed — unit tier:**

| Setting | Value | Why |
|---|---|---|
| `read_thresholds_enabled` | `true`, the unit yaml's ([`test/conf/cassandra.yaml:63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/conf/cassandra.yaml#L63)) | the master switch |
| `local_read_size_warn_threshold` | unset (`setLocalReadSizeWarnThreshold(null)`) except in the known-answer and warn-twin steps | the unit yaml sets 4096 KiB, which would add a warn parameter to every read |
| `row_index_read_size_warn_threshold`, `row_index_read_size_fail_threshold` | unset by the harness (the two setters with `null`) | the unit yaml sets them to 4096/8192 KiB; the sibling guard would otherwise be a second abort source |
| `coordinator_read_size_*` | not on this path | the unit read does not go through `SelectStatement` |
| Table | `ks1.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`, compression off, one flushed SSTable, no static column, no tombstones | the rows come from the SSTable deserializer, identical, and the partition deletion is live |
| `trackWarnings` | `command.trackWarnings()` in every run except the no-flag control | stands in for the flag the coordinator sets |
| JVM | the unit-test JVM's flags; record `UseCompressedOops` | `ObjectSizes` depends on them, and so does *h* |

**Hold fixed — cluster tier:**

| Setting | Value | Why |
|---|---|---|
| `read_thresholds_enabled` | `true` | the master switch |
| `local_read_size_warn_threshold` | `1B` at every value except the default control | makes every completed read print its total (*X*) in the client warning; it does not change the abort |
| `coordinator_read_size_warn_threshold`, `coordinator_read_size_fail_threshold`, `row_index_read_size_warn_threshold`, `row_index_read_size_fail_threshold` | unset (the defaults) | sibling guardrails in the same channel; the unit yaml sets them, the shipped yaml does not |
| Heap | `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE` unset | the response of the largest completed read (about 10 MB) and the coordinator's result fit comfortably |
| `read_request_timeout` | default (5 s) | a read of 8,000 rows takes well under a second; the arms would show a timeout as a different error |
| Table | `ks1.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`, compression off, compaction off, default caching, one flushed SSTable | exact sizes; no row-cache path |
| Replication | `SimpleStrategy`, RF 1, one node | no remote replica; the abort fails the read |
| Client | the bundled Python driver, **protocol 5**, `fetch_size=None` except in arm C2, request timeout 120 s | one command per read; the per-replica failure code (`READ_SIZE`) is sent to the client only from protocol 5 ([`ErrorMessage.java:219-226`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/ErrorMessage.java#L219-L226)) |
| Everything else | as shipped | nothing else moves |

**Controls:**

- **Idle run (both tiers)** — a read with the limit unset: unit, nothing is counted (no `MessageParams`); cluster, `LocalReadSizeAborts` does not move.
- **Known answer (unit)** — the mirror equals the check's counter on a completed read (above).
- **Calibration (cluster)** — at the 16 MiB value, two completed reads (`ck < 100` and the whole partition) give *b0* and *h*; the run is invalid if the whole read's *T*(*N*) is not below 16,777,216.
- **No flag (unit)** — no abort without `trackWarnings()`.
- **Master switch off (cluster, optional)** — the same read with `read_thresholds_enabled: false` at 262,144 completes with no warning (the upstream test covers this at one value).

**Reset between runs:** unit — each `ant testsome` is a fresh JVM, and the harness drops and recreates the table first. Cluster — stop the node (`bin/nodetool stopdaemon`), check `ps -eo cmd | grep '[C]assandraDaemon'` is empty, delete the clone's `data/` and `logs/`, restore `conf/cassandra.yaml` from `conf/cassandra.yaml.orig`, then write the next value's yaml.

### 9c. Workload

The operand is the running total of heap sizes, so the workload is **one wide partition of identical rows** and reads that stop at chosen row counts. Read it unpaged and in one command; the cluster tier flushes first so every counted row is built by the SSTable deserializer.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/local_read_size_fail_threshold-addSize-failBytes`.
Work for step 1, before run 1 (none of it exists yet):

| File | What it is |
|---|---|
| `LocalReadSizeGuardTest.java` | Unit tier. Package `org.apache.cassandra.db`. System property `stage4.out` (a file that also receives the `STAGE4` lines). Creates the table with `SchemaLoader`, writes the rows with `RowUpdateBuilder`, flushes with `Util.flush()` ([`Util.java:1229`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/Util.java#L1229)), builds the commands with `SinglePartitionReadCommand` and `ClusteringIndexSliceFilter` / `ClusteringIndexNamesFilter`, runs them through `executeLocally()` and `createResponse()`, mirrors the check's arithmetic from `row.unsharedHeapSize()`, and measures *Δ* with `com.sun.management.ThreadMXBean.getThreadAllocatedBytes()` (and stops as Invalid if `isThreadAllocatedMemorySupported()` is false). Records `check MISMATCH` and goes on, failing at the end. Steps in 9e. |
| `unit-run.sh` | Runs the harness test; optionally the upstream dtest. |
| `make-node-yaml.sh <label> <value\|none>` | From `conf/cassandra.yaml.orig` writes `conf/cassandra.yaml` with the hold-fixed settings of 9b and the knob (nothing for `none`, which also leaves the warn limit unset). |
| `read-alloc.btm` | Byteman observation rules, no behaviour change. At the entry of `StorageProxy$LocalReadRunnable.runMayThrow()`, when the command's keyspace is `ks1`, store `getThreadAllocatedBytes()` of the thread; at its exit (normal and exceptional) write `read-alloc thread=<name> bytes=<delta> ms=<epoch>` to the file named by `stage4.byteman.out`. The instrumented class is Cassandra's, so no `boot:` is needed (the rule only *calls* the JDK's `ThreadMXBean`; see [`environment.md`](../../../stage4-runtime-verification/environment.md)). Parse-check it with Byteman's `TestScript` against `build/classes/main` before run 1, as the earlier harnesses did. |
| `send-read.py` | Cluster tier. A Python client on the driver bundled in `lib/cassandra-driver-internal-only-3.29.0.zip`, loaded as `bin/cqlsh.py` loads it ([`bin/cqlsh.py:47-56`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/bin/cqlsh.py#L47-L56)), **protocol 5** (the failure code is sent only from there; if the driver cannot negotiate it, the failure code is not observable and an abort is identified by the message and the meter alone; record that), request timeout 120 s. Modes: `probe`, `load <rows> <payload>`, `read [--fetch-size n] [--trace] "<cql>"`. Prints `OK <rows>` or `ERR <class> <message> <failure map>`, then one `WARN <text>` per client warning and, with `--trace`, the trace events that contain `attempted to read`; exit 0 or 1. |
| `jmx.sh <bean> <attribute>` | `bin/nodetool sjk mx -mg -b <bean> -f <attribute>`: one attribute per call, each call a JVM start (about 1 to 2 s). |
| `cluster-run.sh` | One run script for the case (stage 4 writes it): modes `instrument`, `value <label>`, `calibrate`. Logs every command to `~/stage4-logs/lrs/<label>/session.log`, writes `summary.txt` and `readings.csv`, exits at the first failed check and stops the node on any failure. |

```bash
# unit tier — in the local clone (never the shared cassandra-src); once:
ant build-test
cp <harness>/LocalReadSizeGuardTest.java test/unit/org/apache/cassandra/db/
mkdir -p $HOME/stage4-logs/lrs/unit
ant testsome -Dtest.name=org.apache.cassandra.db.LocalReadSizeGuardTest \
  -Dtest.jvm.args="-Dstage4.out=$HOME/stage4-logs/lrs/unit/run.out"

# cluster tier — per value; <label> is 16m (first, calibration), 256k, 1m, 4m, none
<harness>/make-node-yaml.sh <label> <bytes|none>
MAX_HEAP_SIZE=4G JVM_EXTRA_OPTS="-javaagent:build/lib/jars/byteman-4.0.20.jar=script:<harness>/read-alloc.btm,listener:true -Dstage4.byteman.out=$HOME/stage4-logs/lrs/<label>/alloc.trace" \
  bin/cassandra -p $HOME/stage4-logs/lrs/<label>/cassandra.pid > $HOME/stage4-logs/lrs/<label>/startup.log 2>&1
bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE ks1.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled': false} AND compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};"
<harness>/send-read.py load 8000 1000
bin/nodetool flush ks1 t
<harness>/send-read.py read --trace "SELECT * FROM ks1.t WHERE pk = 1 AND ck < <p>"
<harness>/send-read.py read --trace "SELECT * FROM ks1.t WHERE pk = 1"
<harness>/jmx.sh org.apache.cassandra.metrics:type=Table,keyspace=ks1,scope=t,name=LocalReadSizeAborts Count
```

**Starting values.** Estimates, not measurements:

| Quantity | Value | Why |
|---|---|---|
| Rows, payload | 8,000 × 1,000 B (cluster); 2,000 × 1,000 B (unit) | at about 1.3 KB per row the limits stop the read after about 200, 800 and 3,200 rows, all below *N* |
| *h* | about 1.3 KB | the value bytes plus the row, cell and clustering overhead; measured at calibration |
| Calibration reads | `ck < 100` and the whole partition | two totals give *h* and *b0* |
| Names-filter rows | *M* = 1,000 (unit) and 2,000 (cluster) | *T*(*M*) is above the smallest limits and below 4 MiB |
| Page sizes | 100 and 1,000 rows | about 130 KB and 1.3 MB per command |
| Allocation spread | 15 % | a guess; the repeated runs measure the real figure |

**If sizes drift:** *h* is measured per run and the predictions are recomputed from it; the unit harness asserts that every row has the same *h* and stops the run otherwise. If *T*(*N*) is not below the largest limit, lower *N* and record it.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — `sizeInBytes` and the limit *F* | Unit: the mirror's *T*(*i*), and `MessageParams.get(ParamType.LOCAL_READ_SIZE_WARN)` (completed read) or `…LOCAL_READ_SIZE_FAIL` (abort), which are the check's own counter. Cluster: the number *X* in the client warning `<n> nodes loaded over <X> bytes …` of a completed read (the warn limit is 1 B), and in the trace event `attempted to read <X> bytes but max allowed is <F>` of an abort. | Unit: after every read. Cluster: with every read. | The `LocalReadSize` histogram is **bucketed**, not exact. A completed read prints its total only if the warn limit is set, and the warn parameter is replaced by the fail parameter on an abort. |
| **Disallow evidence** — a signal only the guard produces | (1) The client's `ReadFailure` with failure-map code 4 (`READ_SIZE`). (2) `LocalReadSizeAborts` `Count` (`jmx.sh org.apache.cassandra.metrics:type=Table,keyspace=ks1,scope=t,name=LocalReadSizeAborts Count`). (3) The trace event above. (4) `grep -n 'aborted the query' logs/system.log` for the coordinator's WARN line. (5) Unit: the exception and its message. | After each read. | The meter is marked **by the coordinator** when it collects the abort (`CoordinatorWarnings.done()`), once per read. The replica's ERROR line ([`ReadCommandVerbHandler.java:103`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommandVerbHandler.java#L103)) is written only for a **remote** replica: on one node it does not appear, so do not wait for it. The row-index and coordinator guardrails use the same failure code and a different message and meter: before relying on a signal, confirm the message names `local_read_size_fail_threshold`. |
| **Bypass volume** — what went through each escape | C1: Δ of the names read at a limit below *T*(*M*), against the same read unlimited. C2: rows delivered over all pages against *F*. C3: the rows returned (0) against the abort. | With each arm. | The names read must be a single-partition read with a `ClusteringIndexNamesFilter` (`ck IN (…)`), on this table (no counters, no collections), or it takes the streamed path. |
| **Real resource** — heap bytes the read builds | (1) Unit: *Δ*, the thread's allocated bytes across `createResponse()`, from `getThreadAllocatedBytes(Thread.currentThread().getId())` before and after, median of five runs after two warm-ups. (2) Cluster: the `read-alloc` lines of `alloc.trace`, one per read command on `ks1`, in the order the client issued them. (3) The serialized size of a completed response, `ReadResponse.serializer.serializedSize()` (unit). | (1) around each recorded call. (2) after each read, by order and time. | Allocated bytes are **not retained bytes**: rows are garbage once serialized, so the figure shows what the read builds, not what stays. The Byteman line covers the replica thread only, not the coordinator's merge or the client's result. The `ReadStage` thread may also serve `system_*` reads: the rule filters on `ks1`. |

If a figure cannot be read, name the gap rather than substituting a proxy: the per-command allocation on a node is read only through the Byteman rule, and it is harness work that has to pass its parse check and an instrument check before the node runs count.

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Each check is printed as `STAGE4 check <name> <expected> <actual> ok|MISMATCH`; record pass or fail and the values.

1. **Setup.** `DatabaseDescriptor.daemonInitialization()`; create `ks1.t`; write 2,000 rows (`ck` 0 to 1,999, 1,000-byte `v`); flush; assert one SSTable. Print `UseCompressedOops`.
2. **Mirror and known answer.** Run the unlimited, unflagged slice read, iterating the rows, to collect every row's `unsharedHeapSize()` and the key's `sizeOnHeapOf`; assert all rows have the same *h*; compute *b0*, *T*(*i*) and *i\**(*F*) for each value. Then set warn 1 B, fail unset, flag the command, run the read to the end and assert `MessageParams.get(LOCAL_READ_SIZE_WARN)` = *T*(2,000).
3. **For each *F* in 65,536, 262,144, 1,048,576** (after `MessageParams.reset()`): set the limit and read it back; (a) **iterating read** — flag the command, run `executeLocally()` and pull rows one at a time, counting delivered rows, until the exception; record the count (expect *i\**−1), the message's *X*, `LOCAL_READ_SIZE_FAIL` (expect *T*(*i\**), *F* ≤ *X* < *F* + *h*); (b) **response read** — two warm-ups, then five runs of `createResponse()`, recording Δ for each and the exception; (c) at *F* = 65,536 only, the **boundary pair**: set *F* = *T*(100) and *T*(100) + 1 and repeat (a), expecting 99 and 100 delivered rows.
4. **Above the data and off.** *F* = 8,388,608: the response read completes; record Δ and the response's serialized size; assert no fail parameter. Both limits unset: assert `MessageParams` stays empty. These two give the unlimited Δ and hence *a* = (Δ − Δ0)/*N*, with Δ0 from a read of one row (`ck = 0`).
5. **Scenario C.** (C1) names filter over `ck` 0 to 999 at *F* = 65,536, and the same with the limit unset; and a slice read of `ck < 1000` at *F* = 65,536: record Δ for each (median of five) and the exception. (C2) at *F* = 262,144 run 20 commands of 100 rows, each built from the last returned clustering with `forPaging()`, and record the rows delivered, the exceptions and each command's `MessageParams`; repeat at *F* = 65,536. (C3) a `RowFilter` on `v` that matches no row at *F* = 262,144 and unset: record rows delivered and the exception.
6. **Controls.** The same read at *F* = 65,536 without `command.trackWarnings()`: assert no exception, all rows, no parameter. Warn 65,536 and fail unset with the flag: assert completion and `LOCAL_READ_SIZE_WARN` = *T*(2,000).
7. **Upstream (optional).** Run `LocalReadSizeWarningTest` once with the `ant test-jvm-dtest-some` command of 9b and record pass or fail.

**Before the cluster tier:**

1. **Instrument check.** On the node at the 16 MiB value: (i) `send-read.py probe` connects over protocol 5 and prints `release_version` and the protocol version in use; (ii) `jmx.sh` reads `LocalReadSizeAborts` `Count`; (iii) `read-alloc.btm` loads (the parse check passed) and a read of `ks1.t` writes one `read-alloc` line while a `system_views` read writes none; (iv) the **calibration**: after loading and flushing, `read "… ck < 100"` and the whole-partition read both complete with the client warning `loaded over <X> bytes`, giving *T*(100) and *T*(*N*); compute *h* and *b0*; stop the run if *T*(*N*) ≥ 16,777,216; (v) the idle control: ten seconds with no reads write no `read-alloc` line. Any failure stops the run.
2. **Dataset check.** `nodetool flush ks1 t`; `ls data/data/ks1/t-*/*-Data.db` shows one file; the row count comes from the load's own output. Do not count by reading at a value with a limit set: `SELECT count(*)` pulls every row through the same guard and would abort. At the `16m` start, where nothing aborts, the whole-partition calibration read returns all 8,000 rows and confirms the count.

**Cluster tier, for each value** (`16m`, then `256k`, `1m`, `4m`, `none`):

1. **Control run.** Fresh `data/` and `logs/`, `make-node-yaml.sh`, start the node with the agent, wait for `UN` and for `statusbinary` to print `running`, create the schema, load, flush, run the dataset check. Read `LocalReadSizeAborts` `Count`; idle for 10 s and confirm no `read-alloc` line.
2. **Scenario A — reach the limit.** Compute *i\**(*F*) from *b0*, *h*; `read --trace "… ck < <p*>"` with *p\** = *i\** − 1: expect `OK`, the warn text with *X* = *T*(*p\**) < *F*, no meter change; record the `read-alloc` line. (Skipped at `16m` and `none`, where nothing is limited; at `none` there is no warn text.)
3. **Scenario B — try to exceed the limit.** `read --trace "… ck < <p*+1>"`: expect `ERR` with failure code 4, the trace event with *X* = *T*(*i\**) ≥ *F*, the meter +1, the coordinator's WARN line; then `read --trace "SELECT * FROM ks1.t WHERE pk = 1"` (the whole partition): expect the same *X* and the meter +1. Record each `read-alloc` line. At `16m` and `none` the whole-partition read completes: record its `read-alloc` line.
4. **Scenario C — escapes.** (C1) `read --trace "… ck IN (<0 … 1999>)"` and `read --trace "… ck < 2000"`; record the outcome, *X* and the `read-alloc` line of each. (C2) `read --fetch-size 100 "SELECT * FROM ks1.t WHERE pk = 1"` and `--fetch-size 1000`: record the outcome, the rows delivered and the meter. (C3) `read "… AND v = 0xdeadbeefdeadbeef ALLOW FILTERING"`: record the outcome and the rows returned.
5. **Stop.** `bin/nodetool stopdaemon`, check no `CassandraDaemon` is left, copy `logs/system.log` and `alloc.trace` to `~/stage4-logs/lrs/<label>/`; `grep -c 'aborted the query' logs/system.log`.

**Record for stage 4:** the `cassandra.yaml` diff against the shipped file and the JVM options in force (with `UseCompressedOops`), the exact commands, the node, OS, JDK and Ant versions and the clone's commit, and the raw readings of 9d for every read: the client's lines, the trace events, the meter before and after, the `read-alloc` lines and the `system.log` excerpts; for the unit tier the `STAGE4` lines. Keep the full logs on the node and a small excerpt per value in the results folder.

**Budget.** Unit: about 2.5 minutes to build and a few minutes for the harness (five runs of about twenty reads). Cluster: about 90 s to start a node, about 20 s to load and flush, under a minute of reads, so about 3 minutes per value and about 15 minutes for the tier. The largest read is about 10 MB; the node has 125 GiB of memory and 63 GB of local disk.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — from [`../../../stage2-ai-preprocessing/bands.md`](../../../stage2-ai-preprocessing/bands.md)'s **band A1** list, row `ReadCommand.java:715#2` ("query size in bytes against the configured fail threshold, aborting the read"), ranked in stage-2 batch 18 (`bands.csv`, 2026-09-24). The same condition appears as two earlier band-B rows (`:715#1`, batch 03, "only tests whether the threshold is enabled": the `failBytes != -1` half) and its warn twin as `:724#1` (B, batch 03) and `:724#2` (B, batch 18). Judged in the band-A1 pass on 2026-09-28 and recorded in `pending.md` (item 4); written up 2026-10-06. |
| **Filed by / Date** | Claude (`claude-sonnet-5-5`) session, 2026-10-06 |
| **Line numbers checked** | 2026-10-06 against the local `cassandra-5.0.9` clone at `~/repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`, `HEAD` `b5f2a54210`). Every link in this file was produced from a citation that a script checks: the cited range must exist and, for the load-bearing ones, contain an expected snippet of code; the load-bearing ones were also read in context. |
| **Escape hatch / Target-3 note** | **The guard is off in every stock configuration** (the threshold is `null` and the master switch is `false`), and it is not the only thing that decides how much a read builds; several paths do not meet it. (1) **Off by default:** the shipped yaml has no value and the switch is false, so a default node bounds nothing here. (2) **Per command, not per query:** a query paged into commands that each stay under the limit, or a multi-partition read, is never aborted however much it reads in total (arm C2). (3) **Names-filter point reads materialize first** (§5, arm C1): the rows of `ck IN (…)` are built into an `ImmutableBTreePartition` before the guard wraps anything. (4) **A read without `trackWarnings` is not wrapped:** everything that is not a client `SELECT` through `SelectStatement.execute()` (the internal paths, derived from the three call sites in §4) and every read in a system keyspace. (5) **The coordinator's switch decides, the replica's thresholds apply:** `shouldTrackSize()` reads the replica's own limits but not its own master switch, so mixed settings across nodes enforce on some replicas only (derived, not run). (6) **One row of overshoot** (§5). (7) **Live-settable:** anyone with JMX access can raise or clear the limit at runtime. (8) **A replica to spare turns the abort into a warning:** with RF above 1 and the consistency level met by other replicas, the read succeeds (§6b, derived, not run). (9) **It counts before the filter:** a filtered read that returns little is aborted for what it scanned (arm C3), so it is also a way to refuse a legitimate query. (10) **Memtable rows are counted** though the read does not allocate them (§5, unverified). |
| **Stage-4 feedback** | none yet. §9 was written in the new layout on 2026-10-06 (9a to 9e); it is not yet audited (stage-4 README, step 0) and not yet run. It lists its harness as work for step 1. |
| **Notes** | **Found while writing this up (2026-10-06), for stage 3 to judge; `pending.md` is not rewritten except as noted.** *Per command, not per query:* `pending.md` calls it "a running total per query" and groups it with the row-index guard as "per-query heap ceilings"; the counter belongs to one `ReadCommand` (§5). *"No further rows are materialized" holds from the row after the crossing one:* the crossing row is built first, and a names-filter point read builds all its rows before the guard (§5). *It counts what storage yields, not what is returned,* which `pending.md` does not say. *The disallow is not a plain throw to the client:* the replica swallows it and answers empty with a note, and the coordinator decides whether the query fails (§6b). *The warn twin:* `pending.md` says it "is already rejected (Rule 3)", but `rejected.md` recorded only the row-index twin, `RowIndexEntry:403`; the local-read twin, `ReadCommand:724`, is recorded there now. *Stage 2's `715#1` and `715#2`* are the two operands of one condition, not two checks. *A sibling not judged:* `coordinator_read_size_fail_threshold` is checked in `SelectStatement.maybeFail()` ([`SelectStatement.java:1057-1080`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1057-L1080)), called after each row is added to the result builder (`:1092`, `:1104`, `:1132`), on `ResultSetBuilder`'s sum of selected value lengths ([`ResultSetBuilder.java:76-83`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L76-L83), [`shouldReject():95-98`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L95-L98), a `>` comparison); it is recorded as an unjudged candidate in `pending.md` (item 11). |

---

## 11. Notes

- **Why one check site and one case.** `addSize()` is the only comparison against the fail limit; the warn twin at `:724` only records a parameter and is refused in `rejected.md` (Rule 3, the same judgement as `RowIndexEntry:403`). The abort reaches the client by a separate route (§6b) that this case describes but does not treat as another check site.
- **Why this qualifies when `BatchStatement.java:352` was refused as post hoc.** That check runs after the whole batch is built, so everything it could withhold already exists. Here the guard runs after *one* row and withholds every later one and the response built from them, so the maximum the command can build is bounded by the limit plus a row: Rule 2's test (does changing the value move the maximum bytes the command builds?) holds, one for one. The exception is the names-filter read, where the guard really is post hoc, and that is recorded as the bypass it is.
- **Contrast with `max_mutation_size`.** That guard is the first statement before the allocation and dominates it; this one is a transformation inside a lazy pipeline, so it dominates the *later* rows and not the first one that crosses. Both are per-item bounds with a node-wide `limit × N`.
- **The unit yaml is not the node's.** `test/conf/cassandra.yaml:63-69` turns the whole family on (switch true, fail 8 MiB, warn 4 MiB, plus the coordinator and row-index pairs); a shipped node has none of it. The same trap as in [`max_mutation_size`](max_mutation_size-validateSize-MAX_MUTATION_SIZE.md) §11: the unit yaml's values are not the node's. The cluster tier writes the two lines it needs and leaves the sibling guardrails unset.
- **What this design does not cover.** RF above 1 (the abort as a warning, the digest reads); the remote-replica path (its ERROR line, and the message flag); `N` > 1, the multiplier; memtable-resident rows and the row cache; live setting over JMX; the coordinator-side guardrail; the first `addSize()` of a partition being its partition-level deletion, which counts 0 for a live one (a limit at or below the key's size would abort before any row). Each is recorded from the source in §5, §6b or §8.
- **Nothing here was run.** No measured number appears in this file; every figure in §9 is derived from the source and is a prediction.
