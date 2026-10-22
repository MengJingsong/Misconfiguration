# coordinator_read_size_fail_threshold — coordinator result set (one `SELECT` request's `ResultSet`)

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | COORDINATOR_READ_SIZE_FAIL_THRESHOLD-SHOULDREJECT-THRESHOLDBYTES |
| **Constraint** | `coordinator_read_size_fail_threshold` — a **configuration entry** ([`Config.java:528`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L528), `volatile LongBytesBound`, default `null`, which switches the check off). The shipped yaml carries it only as a comment ([`conf/cassandra.yaml:2012-2022`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L2012-L2022)), so it is **off by default**. It also needs the master switch `read_thresholds_enabled` ([`Config.java:526`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L526), default `false`), shared with the replica-side sibling; the unit-test yaml turns the switch on and sets this threshold to 4096 KiB ([`test/conf/cassandra.yaml:63-65`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/conf/cassandra.yaml#L63-L65)). **Live-settable** over JMX (§4). It is **not** a `Guardrail` object: no superuser or internal-client exemption applies (§5). |
| **Enforcement pattern** | **(b)** — the comparison is in `ResultSetBuilder.shouldReject()`, which **returns a boolean**; `SelectStatement.maybeFail()` reads it and throws. The decision point is a guard that throws, so the gated allocations (the next rows of the result set and the response frame) are its fall-through, and domination is checked as for (c) (§5): **it runs after the row that crosses the limit has been added, and the last row of a result is never checked.** |
| **Capacity check** | [`ResultSetBuilder.shouldReject():97`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L97) — `thresholdBytes != -1 && size > thresholdBytes`. One check site. Its warn twin, `shouldWarn()` ([`ResultSetBuilder.java:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L87)), is called only after the result is built and only warns (refused, [`predicted-negative.md`](../predicted-negative.md) band B, group 1). |
| **Decision point** | [`SelectStatement.maybeFail():1061-1079`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1061-L1079) — the `if` that reads the verdict and the `throw` at `:1079`. It is called from [`SelectStatement.processPartition()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1089-L1092) at `:1092` (start of each partition), [`:1104`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1104) (a static-only partition) and [`:1132`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1132) (each row), the last being the one that fires on an ordinary read. |
| **Allocation site** | (1) The next row of the CQL result: [`ResultSetBuilder.newRow():135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L135) adds the output row to the `ResultSet` ([`ResultSet.addRow():72-75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L72-L75)), and the row it holds was deserialized from the replica response when the loop asked for it ([`SelectStatement.java:1125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1125)), each value copied into a new `byte[]` ([`UnfilteredSerializer.java:652`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L652) → [`ByteArrayAccessor.read():100-105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/ByteArrayAccessor.java#L100-L105)). (2) The client response frame: [`Message.encode():367`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Message.java#L367), a pooled **direct** buffer of the encoded result's size ([`CBUtil.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CBUtil.java#L60)). |
| **Related cases** | [`local_read_size_fail_threshold-addSize-failBytes.md`](local_read_size_fail_threshold-addSize-failBytes--guided.md) — the **replica-side sibling**: same master switch, same `READ_SIZE` failure code; it bounds what one replica command pulls from storage, this bounds what the coordinator turns into the client's result. [`row_index_read_size_fail_threshold-checkSize-failThreshold.md`](row_index_read_size_fail_threshold-checkSize-failThreshold--guided.md) — the third guard of the family. |

```java
// ResultSetBuilder.java:60, :76-83, :95-98 — the counter and the comparison
private long size = 0;
private void addSize(List<ByteBuffer> row)                       // called from getOutputRow():176, i.e. when a row is added
{
    for (int i=0, isize=row.size(); i<isize; i++)
    {
        ByteBuffer value = row.get(i);
        size += value != null ? value.remaining() : 0;            // :81 — value bytes only
    }
}
public boolean shouldReject(long thresholdBytes)
{
    return thresholdBytes != -1 && size > thresholdBytes;         // <-- capacity check, :97
}

// SelectStatement.maybeFail():1057-1081 — the decision point
private void maybeFail(ResultSetBuilder result, QueryOptions options)
{
    if (!options.isReadThresholdsEnabled())                        // :1059 — master switch, captured per request
        return;
    if (result.shouldReject(options.getCoordinatorReadSizeAbortThresholdBytes()))   // :1061 — reads the verdict
    {
        String msg = String.format("Read on table %s has exceeded the size failure threshold of %,d bytes", ...);
        ClientWarn.instance.warn(clientMsg);                       // :1066
        logger.warn("{} with query {}", msg, asCQL(options, state));   // :1067
        store.metric.coordinatorReadSizeAborts.mark();             // :1071
        store.metric.coordinatorReadSize.update(result.getSize()); // :1072
        ReadSizeAbortException exception = new ReadSizeAbortException(clientMsg, options.getConsistency(), 0, 1, true,
                ImmutableMap.of(FBUtilities.getBroadcastAddressAndPort(), RequestFailureReason.READ_SIZE));
        StorageProxy.recordReadRegularAbort(options.getConsistency(), exception);   // :1078
        throw exception;                                           // <-- disallow, :1079
    }
}

// SelectStatement.processPartition():1123-1132 — where it fires
while (partition.hasNext())
{
    Row row = partition.next();                                    // :1125 — row j deserialized
    result.newRow(protocolVersion, partition.partitionKey(), row.clustering(), selection.getColumns());  // :1126 — row j-1 added, size updated
    maybeFail(result, options);                                    // :1132
    // ... row j's values copied into the builder's input row
}
```

## 2. Context

When a client sends a `SELECT`, the node it talks to (the coordinator) collects the replicas' answers, turns the rows into the CQL result the client asked for, and encodes that result into one response message. The result is held in memory, row by row, until it has been encoded and sent. Nothing else on the coordinator caps how big one such result can grow: a query over a wide partition, a large scan or a big page builds a correspondingly big result. This guardrail adds up the bytes of the column values placed in the result and, once the total has passed a configured limit, stops building the result and fails the query with a "read size" error instead of answering.

It is a **guardrail that is off until an operator turns it on**: the limit has no default and a separate master switch, shared with the replica-side read guards, must also be on. It runs **after** the replicas have answered, so it does not stop the replicas' work or the coordinator from receiving their answers; what it stops is the coordinator's own copy of the result and the response message, and, on a scan, the requests for the ranges not yet asked for.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `read_path` — the coordinator-side end of the read (`cql3/statements/SelectStatement`, `cql3/selection/ResultSetBuilder`), and its reporting (`exceptions/ReadSizeAbortException`, `metrics/TableMetrics`, `metrics/ClientRequestMetrics`) |
| **One-line role** | `SelectStatement` runs a client read through `StorageProxy`, then builds the CQL `ResultSet` from the merged rows; the guard watches that build. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes, on the result rather than on the read.** It compares a **running total of the value bytes placed in one request's `ResultSet`** with a byte limit. The total is per **request** (one `ResultSetBuilder` per `process()` call, [`SelectStatement.java:1004`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1004)), so for a paged query it is per **page**, reset on every page. Unlike the replica sibling's flow counter, it measures something that is **resident**: the rows it counts stay in the result set until it is encoded. |
| **Usage-side operand** | `size` ([`ResultSetBuilder.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L60)), the sum of `remaining()` of every value of every output row added so far ([`addSize():76-83`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L76-L83), called from [`getOutputRow():173-178`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L173-L178)). Value bytes only: the partition-key and clustering values a row repeats are counted, the object headers of the row list and the `ByteBuffer` wrappers are not. For an aggregate or `GROUP BY` query only the **output** rows are counted, not the rows read to compute them. |
| **Limit-side operand** | `thresholdBytes`, the parameter of `shouldReject()`, passed as `options.getCoordinatorReadSizeAbortThresholdBytes()` ([`SelectStatement.java:1061`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1061)); `-1` when the entry is `null` or the master switch is off. |
| **Limit type** | **Configuration entry**, used raw (no derivation), default `null` = off, **live-settable**. |

**Limit initialization path** (declare → validate → store → read):

1. [`Config.coordinator_read_size_fail_threshold:528`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L528) — declared, `volatile DataStorageSpec.LongBytesBound`, default `null`.
2. [`DatabaseDescriptor.applySimpleConfig():785`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L785) → [`applyReadThresholdsValidations():1092-1104`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1092-L1104) — the only startup check: when both are set, `fail` must be at least `warn`. No range, no derivation.
3. [`DatabaseDescriptor.getCoordinatorReadSizeFailThreshold()/setCoordinatorReadSizeFailThreshold():4878-4888`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4878-L4888) — read and written **live**; the setter logs `updating  coordinator_read_size_fail_threshold to <value>` (two spaces in the source). Exposed as the **String** JMX attribute `CoordinatorLargeReadAbortThreshold` of `org.apache.cassandra.db:type=StorageService` ([`StorageService.java:7298-7307`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L7298-L7307), parsed by `new DataStorageSpec.LongBytesBound(String)` at [`:7368-7373`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L7368-L7373)); the master switch is the attribute `ReadThresholdsEnabled` ([`:7274-7283`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L7274-L7283)). No `nodetool` command wraps either.
4. [`QueryOptions.ReadThresholds.create():275-281`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L275-L281) — **captured once per options object**: if the daemon is initialized and the switch is on, a `DefaultReadThresholds` stores the limit in bytes, `-1` for `null` ([`:312-316`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L312-L316)); otherwise `DisabledReadThresholds` ([`:284-305`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L284-L305)) answers `false` and `-1`. `create()` is the initializer of a field of `DefaultQueryOptions` ([`:346`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L346)), built for every client request **and every internal query** (`QueryOptions.forInternalCalls()`, [`:62-75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L62-L75)). So a change applies to requests decoded afterwards.
5. [`QueryOptions.getCoordinatorReadSizeAbortThresholdBytes():257-260`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L257-L260) — read in `maybeFail()` ([`SelectStatement.java:1061`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1061)) and compared at [`ResultSetBuilder.java:97`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L97).

**Naming note (Target 1).** The constraint is the first-declared variable on the path, the configuration entry; `shouldReject` encloses the comparison and `thresholdBytes` is the operand as written there (README §6.1). The config key says `fail`; the getter on `QueryOptions` and the JMX attribute say `Abort`/`LargeRead`: the same value.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`SelectStatement.maybeFail():1061-1079`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1061-L1079) |
| **Verdict** | Pattern (b): `shouldReject()` returns `true` (disallow) or `false` (allow); nothing stores it. It is written nowhere and read only by `maybeFail()`; `size` only grows, so once `true` it stays `true` for that builder. `maybeFail()` turns `true` into a `ReadSizeAbortException` ([`ReadSizeAbortException.java:25-31`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/exceptions/ReadSizeAbortException.java#L25-L31), a `ReadAbortException`, itself a `ReadFailureException`). |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `size <= thresholdBytes`, or `thresholdBytes == -1`, or the switch is off (`maybeFail()` returns at `:1059-1060`) | the loop copies the current row's values into the builder's input row; the next iteration deserializes the next row and adds this one to the result; at the end the result is built, encoded and sent |
| **Disallow** | `size > thresholdBytes` | WARN log line, client warning, two meters and the histogram, the client-request abort meters, then `ReadSizeAbortException`: no further row is deserialized or added, no `ResultMessage.Rows` is built, the client receives an error |

```java
// allow — SelectStatement.processPartition():1134-1152 then the next iteration
for (ColumnMetadata def : selection.getColumns()) { ... result.add(...) ... }   // row j's values referenced by the input row
// next iteration: partition.next() deserializes row j+1; newRow() adds row j via ResultSet.addRow()
```

```java
// disallow — SelectStatement.maybeFail():1076-1079
ReadSizeAbortException exception = new ReadSizeAbortException(clientMsg, options.getConsistency(), 0, 1, true,
                                                              ImmutableMap.of(FBUtilities.getBroadcastAddressAndPort(), RequestFailureReason.READ_SIZE));
StorageProxy.recordReadRegularAbort(options.getConsistency(), exception);
throw exception;
```

### When it runs, and what it has already let through

- **After the row that crosses the limit has been added.** In iteration *j* the loop first deserializes row *j* (`:1125`), then `newRow()` adds row *j*−1 to the result and adds its values to `size` (`:1126` → [`newRow():135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L135)), and only then checks (`:1132`). When it fires, the result holds rows 0 … *j*−1, whose total has just passed the limit, and row *j* has been deserialized but not added. The upstream comment at [`:1128-1131`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1128-L1131) states this is deliberate ("slightly more permissive to avoid cases where a row can never be read").
- **The last row is never checked.** The loop's last row is added by [`ResultSetBuilder.build():157-163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L157-L163) after the loop, and `process()` calls only `maybeWarn()` after that ([`SelectStatement.java:1014-1015`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1014-L1015)). So a read of *n* rows of *s* value bytes each **completes iff (*n* − 1)·*s* ≤ limit** (`>` is strict); the largest completed read has *n\** = ⌊limit/*s*⌋ + 1 rows, holding *n\**·*s* bytes, which is above the limit by less than one row. A read of more rows aborts in iteration *n\**, with exactly those *n\** rows in the result and `size` = *n\**·*s*. A one-row result can never be refused.
- **`:1092` adds nothing.** At the start of a partition nothing has been added since the last check (the previous partition's last row is still in the input row and is added at the next `newRow()`), so the check at `:1092` sees the size the previous check saw (derived from the code).
- **Per request, per page.** `process()` makes a new builder each call ([`:1004`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1004)); a paged query runs one `process()` per page ([`SelectStatement.java:542-545`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L542-L545)). Drivers page by default (the bundled Python driver's `default_fetch_size` is 5,000 rows), so a query whose every page stays under the limit is never refused, however much it returns in total.
- **Counted before ordering and the user `LIMIT` trim** ([`:1017-1019`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1017-L1019)), after the replica-side row filter and limits.

### What is already resident when it runs (the post-hoc part)

The guard is in the coordinator's result loop, which consumes a `PartitionIterator` the read path has already produced:

- **Single-partition reads (and `IN` groups): every replica answer is in memory first.** [`StorageProxy.fetchRows():2106-2176`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2106-L2176) sends every command, waits for `blockFor` responses of each ([`:2148`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2148)), and only then returns iterators over them ([`:2170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2170)). A data response is one serialized buffer of the whole command's rows ([`ReadResponse.LocalDataResponse.build():197-203`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadResponse.java#L197-L203) for the coordinator's own replica; a remote one arrives as such a buffer), and the rows are deserialized from it **lazily** as `process()` asks for them ([`DataResponse.makeIterator():248-262`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadResponse.java#L248-L262) via [`DigestResolver.getData():77-83`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/DigestResolver.java#L77-L83)). The guard therefore does **not** withhold the response buffers; their size is set by the data, the page size and the replica-side `local_read_size_fail_threshold`, not by this limit. This is the half of Rule 3 that is post hoc, as `BatchStatement.java:352` is in full.
- **Range reads: the remaining ranges are not yet asked for.** [`RangeCommandIterator.computeNext():102-123`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java#L102-L123) sends the next batch of sub-range requests only when the consumer has drained the current one ([`sendNextRequests():223-257`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java#L223-L257)); after the throw, `close()` ([`:259-277`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java#L259-L277)) closes the current batch and nothing further is sent. Within the current batch the responses are resident as above. (Derived; on one node all ranges merge into one sub-range command, so this is not exercised by §9.)

### Why it passes Rule 3, and how it differs from `BatchStatement.java:352`

`BatchStatement.java:352` was refused because every mutation of the batch exists before the comparison runs ([`predicted-negative.md`](../predicted-negative.md), first table). Here the comparison runs **inside** the loop that builds the result and stops it: rows not yet reached are never deserialized out of the response buffer, never added to the `ResultSet`, never encoded into the response frame; on a scan, later range requests are never sent. Changing the limit moves the most value bytes the result can hold (`limit` + one row) one for one, and the frame with it (§8). What it cannot withhold, the replica answers already received, is recorded above, not counted as gated.

### Does the guard dominate the allocation?

For every row of a result after the crossing row, yes: `processPartition()` is the only place rows enter a `SelectStatement` result, and each iteration passes `:1132` before the next row is pulled. Paths that reach the allocation without a refusal:

- **The last row** of every result (above), and therefore **any one-row result**.
- **Each page separately** (above).
- **Aggregates and `GROUP BY`:** only output rows are counted; the input rows are read in internal sub-pages ([`AggregationQueryPager.java:34-38`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java#L34-L38)) and are transient, not part of the result, so this is scope rather than an escape.
- **Master switch off or limit `null`** (the defaults): `maybeFail()` returns at `:1059`.
- **Not exempt:** system keyspaces (there is no keyspace test in `maybeFail()`, unlike the replica sibling), internal queries (`QueryProcessor.executeInternal()`, [`QueryProcessor.java:474-477`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L474-L477), builds options whose `ReadThresholds` are captured the same way and ends in the same `process()` through [`executeInternal():579-623`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L579-L623)), superusers, and the two other callers of `processPartition()`: a CAS that is not applied, which reports the current values through it ([`ModificationStatement.java:672-674`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java#L672-L674), reached from `:619` only when `success` is false), and the replica-query helper at [`QueryProcessor.java:516-532`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L516-L532). The upstream dtest notes that a small limit "causes driver to fail while loading metadata" ([`CoordinatorReadSizeWarningTest.java:43-48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/distributed/org/apache/cassandra/distributed/test/thresholds/CoordinatorReadSizeWarningTest.java#L43-L48)): a driver's reads of `system_schema` are client `SELECT`s and are refused like any other.

## 6. Code path

### 6a. Allow path → object creation

1. [`SelectStatement.execute():280`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L280) — a client `SELECT`; [`:334-335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L334-L335) also sets `trackWarnings` on the query when the switch is on (that is what arms the replica-side guards), and [`:338-356`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L338-L356) picks the unpaged or the paged route.
2. [`SelectStatement.execute(ReadQuery …):427-429`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L427-L429) (unpaged) or [`:542-545`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L542-L545) (one page) — `query.execute()` returns the coordinator's `PartitionIterator` (single partition: after every replica answer is in, §5; scan: lazily), and [`processResults():561-571`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L561-L571) calls `process()`.
3. [`SelectStatement.process():994-1022`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L994-L1022) — a new `ResultSetBuilder` (`:1004`; its `ResultSet` is created at [`ResultSetBuilder.java:70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L70)); `processPartition()` for each partition (`:1006-1012`).
4. [`SelectStatement.processPartition():1123-1153`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1123-L1153) — `partition.next()` **deserializes row *j*** (values copied out of the response buffer, [`UnfilteredSerializer.java:652`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L652)); `newRow()` adds row *j*−1; `maybeFail()` returns (allow); the selected values of row *j* go into the input row by reference ([`Selector.java:393`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/Selector.java#L393), [`:451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/Selector.java#L451): `c.buffer()`, a wrapper over the copied array, [`ByteArrayAccessor.java:132-137`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/ByteArrayAccessor.java#L132-L137)).
5. [`ResultSetBuilder.newRow():126-152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L126-L152) at the next iteration — **`resultSet.addRow(getOutputRow())`** (`:135`): the output row list (for a plain column, the selector hands back the same buffer, [`SimpleSelector.getOutput():162-164`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/SimpleSelector.java#L162-L164)) is appended to `ResultSet.rows`, so the copied values stay reachable; `addSize()` counts them.
6. [`ResultSetBuilder.build():157-171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java#L157-L171) adds the last row; `processResults()` wraps the set in `new ResultMessage.Rows(rset)` (`:571`).
7. [`CQLMessageHandler.java:488`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L488) → [`Message.encode():338`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Message.java#L338) computes the size, [`ResultSet.Codec.encodedSize():177-186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L177-L186) (metadata + 4 + Σ (4 + value length)), and **`CBUtil.allocator.buffer(messageSize)`** at [`:367`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Message.java#L367) allocates the frame body, pooled direct memory unless the heap-allocator property is set ([`CBUtil.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CBUtil.java#L60)).

### 6b. Disallow path effect

1. [`maybeFail():1063-1073`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1063-L1073) — formats `Read on table <ks>.<t> has exceeded the size failure threshold of <limit, with thousands separators> bytes`, adds `… with <tokens>` as a **client warning** (`:1066`) and logs `… with query <CQL>` at **WARN** (`:1067`); marks the table meter `CoordinatorReadSizeAborts` (`:1071`, [`TableMetrics.java:859`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L859), also rolled up per keyspace, [`KeyspaceMetrics.java:282`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/KeyspaceMetrics.java#L282)) and records `size` in the `CoordinatorReadSize` histogram (`:1072`, bucketed). The message prints the **limit, not `size`**: no log line carries the counter. A virtual table has no `ColumnFamilyStore`, so no meter (`:1069`).
2. [`maybeFail():1076-1079`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1076-L1079) — builds `ReadSizeAbortException(received 0, blockFor 1, dataPresent true, {this node: READ_SIZE})`, marks the client-request `Read` meters `Aborts` and `ReadSizeAborts` ([`StorageProxy.recordReadRegularAbort():2061-2065`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2061-L2065) → [`ClientRequestMetrics.markAbort():57-69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/ClientRequestMetrics.java#L57-L69); the regular-read meters even for a scan) and throws.
3. **What stops.** The exception leaves `processPartition()`, `process()` and `processResults()`; the try-with-resources at `:427` (or `:542`) closes the `PartitionIterator`. No further row is deserialized from the response buffers, no further row is added, `build()` is never called, no `ResultMessage.Rows` exists, so no result frame is allocated. The builder and the rows it held become garbage at once. On a scan, no later range batch is sent (§5). Already-received replica responses are dropped with the iterator; a read repair started before `process()` still completes in the iterator's `close()` ([`StorageProxy.concatAndBlockOnRepair():2067-2093`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2067-L2093)).
4. **What the client gets.** [`Dispatcher.processRequest():444`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L444) turns the exception into an error response and attaches the client warning (`:449`); [`ErrorMessage.java:211-226`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/ErrorMessage.java#L211-L226) writes `READ_FAILURE` with received 0, blockFor 1 and, **from native protocol 5**, the failure map `{coordinator: 4}` ([`RequestFailureReason.java:37`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/exceptions/RequestFailureReason.java#L37)); earlier protocols carry only the count. Unlike the replica sibling there is **no replica to spare**: the coordinator itself is the failed response, so RF and the consistency level do not turn this into a warning.
5. **Not a block, a retry or a degrade.** The request fails; the client decides.
6. **If the check were absent.** The loop would build the whole page or result and encode it. No other coordinator-side bound is in byte units: the page size counts rows, `native_transport_max_frame_size` is read only by the inbound frame decoder ([`Envelope.java:197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L197)), not for responses, and the replica-side guards bound what each replica builds, not the coordinator's copy.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | The rows of the CQL `ResultSet` (`List<ByteBuffer>` per row, each value a wrapper over a `byte[]` copied out of the replica response), then the encoded response frame (`ByteBuf`, `ResultMessage.Rows`). |
| **Resource consumed** | **Heap bytes** for the result set (resident from the row's addition until the frame has been encoded); **direct bytes** for the frame (pooled, until it has been written to the socket). |
| **Rough sizing** | Result set: the counted `size` (value bytes) plus per-row and per-value object overhead the counter ignores (the row list, one wrapper and one array header per value); for rows of large blobs the overhead is small, for rows of small columns it dominates (not measured here). Frame: exactly `metadata + 4 + Σ (4 + value length)` for the rows ([`ResultSet.java:177-186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L177-L186)) plus the message header and any warnings. |
| **Lifetime / release** | The result set is garbage once the frame is encoded (or at once, on an abort); the frame's buffer goes back to Netty's pool after the write. |

## 8. Maximum memory/disk bound

`coordinator_read_size_fail_threshold` bounds **the value bytes one request's result set can hold**: a result that completes holds at most `limit` + one row (the unchecked last row), and an aborted one holds the same at the moment of the abort, plus one deserialized row not yet added. The response frame built from a completed result is bounded with it, at `limit` + one row + 4 bytes per value + metadata. Raising or lowering the limit moves both ceilings **one for one**.

It is **per request and per page, not node-wide**: the coordinator admits up to `limit × N` at once, *N* being the read requests in `process()` at the same time (bounded by the native-transport request threads, `native_transport_max_threads`, 128 by default, [`Config.java:283`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L283), wired at [`Dispatcher.java:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L58); an upper bound the guard allows, not measured here), and frames waiting to be written outlive their thread. A paged query is bounded per page only.

It does **not** bound: the replica response buffers the coordinator holds while it builds the result (they are in memory before the first check, and are sized by the data, the page size and `local_read_size_fail_threshold`); the replicas' own work; the input rows of an aggregate; anything when the switch is off or the limit unset (the defaults). In heap terms, the result set can cost noticeably more than the limit when rows are made of small values, since the counter sees value bytes only (inferred from the code).

**Other limits interact with it**, which matters to a sweep (§9b holds them fixed): `read_thresholds_enabled` arms this guard **and** the replica-side ones; `local_read_size_*` and `row_index_read_size_*` fail a read with the same `READ_SIZE` code and would be read as this guard if they fired; the page size decides how much one `process()` sees.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
The test reads one wide partition of identical rows at several values of the limit and checks that the coordinator refuses exactly the reads whose rows before the last exceed it, with the counter at the abort equal to the predicted value, that the bytes the coordinator allocates while building the result stop growing there, and that the replica's response is built in full regardless. **Run so far:** none.

*Amended 2026-10-15 (stage-4 step-0 audit, before any reading; results file §1.1).* (1) **The unit tier's absolute
allocation fit is replaced by a slope fit.** An abort costs a fixed amount that no completed read has: `maybeFail()` formats
the message twice, renders the query (`asCQL`), writes a WARN line, adds a client warning and builds an exception with its stack
trace (`SelectStatement.java:1063-1079`), so Δ0 from completed reads underestimates every abort by the same constant. The
prediction is now: the slope of the three aborted reads, (Δ(1,048,576) − Δ(65,536)) / (1,042 − 67), equals *a* within 15 %
(fixed now, not set from the spread), and the increment ratio stays 0.25 ± 0.03. (2) **One client session for the whole
cluster lifetime:** the sibling's `send-read.py` opens a new connection per call, and every new connection's metadata refresh
reads `system_schema` with client `SELECT`s, which the guard refuses at a small limit (at 1 B every multi-row read); so the run
script loads the bundled driver itself and keeps one `Session`, opened before any limit is set (9b's "one connection" made
exact). (3) **Unit table name:** the `CQLTester` table is created by `createTable()` in `cql_test_keyspace` with a generated
name; *s* is unchanged (1,008). (4) **The 1 B window (C4) refuses the node's own multi-row internal reads too** (no
exemption, §5): the limit is set to 1 B, the one read is made and 16 MiB is set straight after; WARN lines of other
keyspaces in that window are recorded, not counted as C4.

### 9a. Procedure and conclusions

**Testability:** config, **live-settable**. The unit tier calls `DatabaseDescriptor.setCoordinatorReadSizeFailThreshold()` and builds new `QueryOptions` after each change (they capture the limit, §4); the cluster tier sets the String JMX attribute `CoordinatorLargeReadAbortThreshold` on one running node, so every value runs in one node lifetime and the driver's metadata reads at connect happen before any limit is set. The master switch `read_thresholds_enabled` must be on. No patched build; the cluster tier's counter and allocation readings are Byteman observation rules (harness work, 9c).

**Claim under test:** with the master switch on, `coordinator_read_size_fail_threshold` caps the value bytes one request's result set can hold. A read of *n* identical rows of *s* value bytes completes iff (*n* − 1)·*s* ≤ the limit; any longer read aborts in iteration *n\** = ⌊limit/*s*⌋ + 1 with `size` = *n\**·*s*, having deserialized *n\** + 1 rows from the replica response and built no result frame, and the client gets `READ_FAILURE` with code 4. The replica's response is built and held in full whatever the limit; the limit is per request (per page) and does not exempt system keyspaces or internal queries (§5, §6b, §8).

**How this verifies the hypothesis** (a restatement of the claim, procedure, prediction and conclusions in this section; it adds none):

- **Hypothesis:** the constraint caps the result set the coordinator builds for one request, and a read that passes it stops building.
- **Test:** vary the limit over three values per tier, plus one above the data and unset. At each, read one partition of identical rows in one request: the largest read that should complete, one row more, and the whole partition. Read the check's counter (unit: the builder; cluster: Byteman), the rows built, the coordinator's allocated bytes while building, the encoded result size, and the replica's allocated bytes. Then the arms that should not be refused or that test the exemptions: paging, `count(*)`, switch off, a system-keyspace read, an internal query.
- **Logic:** (1) a completed read's counter equals *n*·*s* exactly (known answer), else the run is invalid. (2) Reads of *n\** rows complete and reads of *n\** + 1 rows abort with `size` = *n\**·*s*; the boundary pair shows `>`: usage **stops at the limit**. (3) *n\**, the abort counter and the coordinator's allocation follow the limit (increments 1 : 4): usage **follows the constraint**. (4) Every abort carries the WARN line, the meters and code 4, and no result frame: the guard, not something else, enforces it. (5) The whole-partition abort allocates what the (*n\** + 1)-row abort allocates, while the replica's allocation is the same at every limit: the guard withholds the result, not the replica answer.
- **Refuted if:** a read with (*n* − 1)·*s* above the limit completes; an abort's counter differs from *n\**·*s* or depends on the partition's size; the coordinator's allocation for an aborted read grows with the partition; a result frame is encoded for an aborted read; or *n\** does not move with the limit (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — set up as in 9b; run the harness test `CoordinatorReadSizeGuardTest` (9c) in one JVM over all values.
2. **Cluster tier** — set up as in 9b; start one node, load one partition, flush, then for each value set it live and run the reads of 9e.
3. **At each value:** control (unset) → **scenario A**, reach the limit (*n\** rows) → **scenario B**, try to exceed it (*n\** + 1 rows, the whole partition) → **scenario C**, the arms (paging, `count(*)`, switch off, system keyspace, internal query, scan).
4. **Compare** with the prediction below and read the result in the table.

**Prediction** (stated before any run, in numbers). Notation: *F* = the limit in bytes; *s* = value bytes per row of `SELECT *` on `ks.t (pk int, ck int, v blob)` with 1,000-byte blobs = 4 + 4 + 1,000 = **1,008** (exact, from the schema; no calibration); *n\**(*F*) = ⌊*F*/1,008⌋ + 1; *X*(*F*) = *n\**·1,008, the counter at an abort.

| *F* (B) | *n\** | *X* = *n\**·*s* (B) | *X* − *F* |
|---|---|---|---|
| 65,536 (unit) | 66 | 66,528 | 992 |
| 262,144 | 261 | 263,088 | 944 |
| 1,048,576 | 1,041 | 1,049,328 | 752 |
| 4,194,304 (cluster; the unit yaml's value, above the unit data) | 4,162 | 4,195,296 | 992 |

*Unit tier*, *N* = 2,000 rows (total 2,016,000 B), one flushed SSTable, at *F* = 65,536 · 262,144 · 1,048,576 · 4,194,304 (above the data) and unset:

- **Read-back:** `getCoordinatorReadSizeFailThreshold().toBytes()` equals *F*, and new options answer `getCoordinatorReadSizeAbortThresholdBytes()` = *F* (−1 when unset).
- **Known answer:** a completed read of *n* rows leaves `getSize()` = 1,008·*n* exactly, for *n* = 100, 1,000, 2,000.
- **Stop:** at each *F* below the data, the white-box loop over the whole partition aborts with `getSize()` = *X*(*F*) and exactly *n\** + 1 rows pulled from the iterator (67 · 262 · 1,042); `ck < n*` completes with *n\** rows and `getSize()` = *X*(*F*), which exceeds *F*.
- **Boundary (`>`):** at *F* = 100,800 (= 100·*s*) `ck < 101` completes (101 rows, `getSize()` 101,808) and `ck < 102` aborts with 101,808; at *F* = 100,799 `ck < 100` completes (100,800) and `ck < 101` aborts with 100,800.
- **Above the data and off:** at 4,194,304 and unset the whole partition completes with `getSize()` = 2,016,000; unset leaves the `CoordinatorReadSizeAborts` count unchanged.
- **Client path (native protocol 5):** `ck < n*` returns *n\** rows; `ck < n*+1` and the whole partition raise the driver's `ReadFailureException` with failure-map value 4; each abort adds exactly 1 to the table's `CoordinatorReadSizeAborts` and to the client-request `ReadSizeAborts`.
- **Frame:** the encoded size of completed results (`ResultMessage.codec.encodedSize(rows, V5)`) rises by exactly **1,020 B per row** (1,008 + 3 × 4): `ck < 200` minus `ck < 100` = 102,000 B.
- **Allocation (coordinator):** the bytes the thread allocates across the white-box loop grow with the rows pulled at the completed reads' slope: (Δ(1,048,576) − Δ(65,536)) / (1,042 − 67) = *a* within 15 %, *a* from completed unlimited reads of 100 and 2,000 rows (*amended 2026-10-15*: was Δ(*F*) = Δ0 + *a*·(*n\** + 1), which omits the abort's fixed cost); the increments (Δ(262,144) − Δ(65,536)) : (Δ(1,048,576) − Δ(262,144)) = 195 : 780 = **0.25 ± 0.03**.
- **Replica response (not withheld):** the serialized response built for the whole partition is byte-for-byte the same size at every *F*, including unset.
- **Arms:** paging 100 rows at *F* = 262,144 delivers all 2,000 rows with no abort, paging 1,000 aborts on the first page; `SELECT count(*)` at 65,536 returns 2,000 with no abort; with the switch off the whole partition completes at 65,536 and no meter moves; at *F* = 1 B, `SELECT keyspace_name FROM system_schema.keyspaces` (at least five rows) aborts with code 4; `QueryProcessor.executeInternal()` of the whole partition at 65,536 throws `ReadSizeAbortException`.

*Cluster tier*, one node, RF 1, *N* = 8,000 rows (total 8,064,000 B; the run is **invalid** if the whole-partition read at unset reports another total), at *F* = 262,144 · 1,048,576 · 4,194,304 · 16,777,216 (above the data) and unset:

- **Read-back:** the JMX attribute reads back `<F>B` after each set, and the node logs `updating  coordinator_read_size_fail_threshold to <F>B`.
- **Scenario A:** `… WHERE pk = 1 AND ck < n*` completes with *n\** = 261 · 1,041 · 4,162 rows; the Byteman `result` line shows `size` = *X*(*F*) and `rows` = *n\**; ratio of *n\** increments 780 : 3,121 = **1 : 4**.
- **Scenario B:** `ck < n*+1` and the whole partition both abort; each gives one `guard-fail` line with `size` = *X*(*F*) and `limit` = *F*, so **the counter at the abort does not depend on the rows asked for**.
- **Evidence:** each abort gives a client `ReadFailure` with failure-map code 4 and the client warning `Read on table ks1.t has exceeded the size failure threshold of <F> bytes with …`, one WARN line of the same text in `system.log`, +1 on `CoordinatorReadSizeAborts` (table) and on the client-request `ReadSizeAborts`, and **no `frame` line** for that request.
- **Real resource (coordinator):** the `coord-alloc` bytes of the whole-partition abort equal those of the (*n\** + 1)-row abort within 5 % at each *F* (the same rows are built); between values their increments are in the ratio (1,042 − 262) : (4,163 − 1,042) = **0.25 ± 0.03**; at 262,144 the abort allocates below 10 % of the unset whole-partition read (262/8,000 of the rows, plus Δ0).
- **Real resource (frame):** `frame` lines of completed reads follow `bytes` = *B0* + 1,020·*rows* exactly, *B0* from the unset reads.
- **Replica (not withheld):** the `read-alloc` bytes of the whole-partition read are the same within 5 % at every *F* and unset.
- **Arms at 262,144:** `fetch_size` 100 (100,800 B per page) delivers all 8,000 rows with no `guard-fail`; `fetch_size` 1,000 aborts on its first page; `count(*)` returns 8,000; switch off (`ReadThresholdsEnabled` false) completes the whole partition with no `guard-fail`; a scan `SELECT * FROM ks1.t` aborts with the same `size` as the whole-partition read. At *F* = 1 B, the `system_schema.keyspaces` read aborts with code 4.

**Conclusions.**

| Result | Conclusion |
|---|---|
| Unit: completed counters are *n*·1,008 exactly; each abort has `getSize()` = *X*(*F*) and *n\** + 1 rows pulled; the boundary pair behaves as `>`; the allocation follows *n\**. Cluster: *n\**, *X* and `coord-alloc` follow the knob (1 : 4); every abort has the WARN line, the meters, code 4 and no frame; *X* does not depend on the rows asked for | **Confirmed** — the check enforces as traced, per request. |
| Paging delivers the whole partition although its total is far above *F*; `count(*)` completes; the switch-off read completes; completed reads hold up to one row above *F* | **Bypass as recorded** — expected, not a refutation (§5). Record the volume (rows delivered over all pages). |
| The replica's allocation for the whole-partition read is the same at every *F* | **As recorded** — the replica answer is not withheld (§5); this is the post-hoc half, not a refutation. |
| A read with (*n* − 1)·*s* > *F* completes, or an abort reports a counter other than *X*(*F*) | **Refuted** — the guard does not stop where traced (§5). Re-read. |
| The whole-partition abort allocates more than the (*n\** + 1)-row abort beyond 5 %, or a `frame` line appears for an aborted request | **Refuted** — the abort does not stop the result being built or encoded (§6b). |
| The replica's allocation falls with *F* | **Not as recorded** — something withholds the replica answer too; amend §5 (not a refutation of the guard). |
| *X* depends on the rows asked for, or *n\** is the same at every value | **Refuted** — not the binding limit. Re-read, do not re-run. |
| *n\** moves with the knob but an abort lacks this guard's WARN text or meter (another `READ_SIZE` source) | **Not confirmed** — a replica-side guard binds instead; check the hold-fixed settings (9b). |
| The system-keyspace read or the internal query completes at the small limit | **Refuted in part** — an exemption exists that §5 missed. |
| The read-back differs from the value set; a completed counter is not *n*·1,008; the unset whole-partition total is not 8,064,000; `getThreadAllocatedBytes` unsupported; a read fails for a reason other than the guard | **Invalid run** — fix the setup (9b, 9c) and re-run. |

Two rules behind this table:

- **A confirmation needs both** the ceiling moving with the knob **and** direct evidence that this guard fired: the `guard-fail` line (unit: the exception from `maybeFail()` with `getSize()`), the WARN text naming `size failure threshold` and the `CoordinatorReadSizeAborts` meter. Code 4 alone is shared with the replica-side guards.
- **The escapes are attributed** by arms in which they cannot fire: paging at a page size above *n\** aborts on the first page, and the switch-off read is the same read with only the switch changed.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `coordinator_read_size_fail_threshold` (§4) with `read_thresholds_enabled: true`. **Live-settable.** Unit: `DatabaseDescriptor.setCoordinatorReadSizeFailThreshold(new DataStorageSpec.LongBytesBound(<bytes>, BYTES))` (or `null`), then new `QueryOptions`. Cluster: `read_thresholds_enabled: true` in the node yaml, the limit left unset there, and set live with the JMX attribute `org.apache.cassandra.db:type=StorageService` / `CoordinatorLargeReadAbortThreshold`, a String such as `262144B` ("unset" is the start-up state, run first; *amended 2026-10-15:* a JMX write of a `null` value restores it, used once after the warm-up of 9e). |
| **Confirm it took effect** | Unit: the test asserts the getter and the options' value. Cluster: `Jmx.java get` reads the attribute back; `grep 'updating  coordinator_read_size_fail_threshold' logs/system.log` (two spaces); the first abort's text shows *F* with thousands separators. |
| **Capacity values** | **Unit:** 65,536 · 262,144 · 1,048,576 · 4,194,304 B (above the data) and unset; boundary 100,800 and 100,799. **Cluster:** 262,144 · 1,048,576 · 4,194,304 · 16,777,216 B (above the data) and unset (the default), 1 B for arm C4 only. |
| **Scope** | **Per request (per page)** (§5). One request at a time, so *N* = 1 in every run; §8's `limit × N` is **not tested**. One node, RF 1: one replica, which is the coordinator. |
| **Level** | Both. **Unit:** harness test `CoordinatorReadSizeGuardTest` (a `CQLTester`); no upstream unit test reaches this check. **Related upstream, optional:** `CoordinatorReadSizeWarningTest` ([`CoordinatorReadSizeWarningTest.java:36-88`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/distributed/org/apache/cassandra/distributed/test/thresholds/CoordinatorReadSizeWarningTest.java#L36-L88), on [`AbstractClientSizeWarning.java:59-298`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/distributed/org/apache/cassandra/distributed/test/thresholds/AbstractClientSizeWarning.java#L59-L298)): `ant test-jvm-dtest-some -Dtest.name=org.apache.cassandra.distributed.test.thresholds.CoordinatorReadSizeWarningTest` (three in-JVM nodes, heavy). |

**What the upstream test does and does not show.** Three nodes, warn 1 KiB and fail 2 KiB set **after** start-up "to avoid driver issues loading" metadata; five rows of 512-byte blobs (2,600 value bytes) on the same `(pk, ck, v)` table; for a point read and a scan it checks the warning text, that the abort raises `ReadSizeAbortException` with the failure text, that the Java driver gets `ReadFailureException` with `READ_SIZE` in the failure map, the keyspace meters and histogram, and that with the switch off nothing is counted. It does not show any other value, the boundary, the rows built before the abort, the allocation, paging, aggregates or the exemptions. The harness adds those.

**Hold fixed — unit tier:**

| Setting | Value | Why |
|---|---|---|
| `read_thresholds_enabled` | `true` (the unit yaml's) except the switch-off arm | master switch |
| `coordinator_read_size_warn_threshold` | `null` (setter) | the unit yaml's 1024 KiB adds a warning to large completed reads; harmless to the counter but noise |
| `local_read_size_*`, `row_index_read_size_*` | `null` (the four setters) | the unit yaml sets them; they would be a second `READ_SIZE` source |
| Table | `ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`, compression off, one flushed SSTable, 2,000 rows of 1,000-byte `v` in `pk = 1` | *s* = 1,008 exactly |
| Driver session | opened (one probe `executeNet` at unset) and the schema created **before** any small limit | the driver's metadata reads are `SELECT`s and are not exempt |

**Hold fixed — cluster tier:**

| Setting | Value | Why |
|---|---|---|
| `read_thresholds_enabled` | `true` in the yaml | master switch |
| `coordinator_read_size_*`, `local_read_size_*`, `row_index_read_size_*` | unset in the yaml (shipped) | only the fail limit is set, live |
| Heap | `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE` unset | an 8 MB result and its copies fit |
| Table | `ks1.t` as above, compression off, compaction off, one flushed SSTable, 8,000 rows | exact *s*, one SSTable |
| Replication | `SimpleStrategy`, RF 1, one node | the coordinator is the only replica |
| Client | the bundled Python driver, **protocol 5**, `fetch_size=None` except in arm C1, request timeout 120 s; one connection for the whole run | failure map only from protocol 5 ([`ErrorMessage.java:221-226`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/ErrorMessage.java#L221-L226)); no reconnect means no metadata read under a small limit |
| `native_transport_timeout`, `read_request_timeout` | default (12 s, 5 s) | no read is held; an 8,000-row read takes well under a second |

**Controls:** the unset value (no `guard-fail`, meters unchanged) at the start; an idle 10 s with no `ks1` Byteman lines; the switch-off read (arm C3); the replica `read-alloc` line as the not-withheld control.

**Reset between runs:** unit — each `ant testsome` is a fresh JVM, the test recreates the table. Cluster — one node lifetime covers every value; stop with `bin/nodetool stopdaemon`, check no `CassandraDaemon` is left, delete `data/` and `logs/`, restore `conf/cassandra.yaml` from `conf/cassandra.yaml.orig`.

### 9c. Workload

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes`.
Work for step 1, before run 1 (none of it exists yet); reuse from the sibling's harness (`…/harness/local_read_size_fail_threshold-addSize-failBytes/`) and from `column_index_cache_size`'s where marked:

| File | What it is |
|---|---|
| `CoordinatorReadSizeGuardTest.java` | Unit tier, package `org.apache.cassandra.cql3`, `extends CQLTester`, `requireNetwork()` in `@BeforeClass`. System property `stage4.out`. Prints `STAGE4 check <name> <expected> <actual> ok\|MISMATCH`, records a mismatch and goes on, fails at the end. **White-box loop** (mirrors `process()` `:1004-1014` without the warn, order and trim): parse `SELECT * FROM <ks>.t WHERE pk = 1 [AND ck < ?]` with `QueryProcessor.getStatement()`; options from `QueryOptions.forInternalCalls(ConsistencyLevel.ONE, values)` **built after** the limit is set; take the `SinglePartitionReadCommand` from `stmt.getQuery(options, nowInSec)`; build the replica answer as the coordinator receives it, `cmd.createResponse(cmd.executeLocally(controller), controller.getRepairedDataInfo())`, and record `ReadResponse.serializer.serializedSize(rsp, MessagingService.current_version)`; then iterate `UnfilteredPartitionIterators.filter(rsp.makeIterator(cmd), cmd.nowInSec())` through a counting `Transformation` and feed each partition to `stmt.processPartition(partition, options, builder, nowInSec)` with `builder = new ResultSetBuilder(stmt.getResultMetadata(), stmt.getSelection().newSelectors(options), false)`; on `ReadSizeAbortException` record `builder.getSize()` and the rows pulled (do not call `build()` after an abort), else `build()` and record `getSize()` and the row count; Δ = `getThreadAllocatedBytes` around the loop only (median of five after two warm-ups). **Client path:** `executeNet(ProtocolVersion.V5, …)` and `executeNetWithPaging(…)`; if V5 cannot be negotiated, use V4 and identify the abort by the exception and the meter, and record it. **Frame:** `ResultMessage.codec.encodedSize(new ResultMessage.Rows(rs), ProtocolVersion.V5)` of `stmt.execute(QueryState.forInternalCalls(), options, Dispatcher.RequestTime.forImmediateExecution())` results. Meters: `getCurrentColumnFamilyStore().metric.coordinatorReadSizeAborts.getCount()` and `ClientRequestsMetricsHolder.readMetrics.readSizeAborts.getCount()`. |
| `unit-run.sh` | Copies the test into `test/unit/org/apache/cassandra/cql3/` of the run clone and runs it; optionally the upstream dtest. |
| `make-node-yaml.sh` | From `conf/cassandra.yaml.orig`: `read_thresholds_enabled: true`, nothing else changed. |
| `coord-read.btm` | Byteman observation rules (no behaviour change), output to `-Dstage4.byteman.out`: **`guard-fail`** at `SelectStatement.maybeFail` `AT THROW`: `guard-fail ks=<$0.keyspace()> size=<$1.getSize()> limit=<$2.getCoordinatorReadSizeAbortThresholdBytes()> ms=<epoch>` (all keyspaces, for arm C4); **`result`** at `ResultSetBuilder.build` `AT EXIT` when `$!.metadata.toString()` contains `(ks1, t)` (`ResultMetadata.toString()`, [`ResultSet.java:347-367`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L347-L367), prints each column's keyspace and table): `result size=<$0.getSize()> rows=<$!.size()>`; **`coord-alloc`** at entry, exit and exceptional exit of the 8-argument `SelectStatement.process(PartitionIterator, QueryOptions, Selectors, long, int, AggregationSpecification, boolean, ClientState)` when `$0.keyspace()` is `ks1`: the bytes the thread allocated inside it, through a helper `stage4.CoordAlloc` (a copy of the sibling's `Alloc.java` with its own `ThreadLocal` and the prefix `coord-alloc`); **`frame`** at `ResultSet$Codec.encode` `AT ENTRY` when `$1.metadata.toString()` contains `(ks1, t)`: `frame rows=<$1.size()> bytes=<$0.encodedSize($1, $3)>`. Helpers go in a jar on the boot class path and may name JDK classes only (the trap the sibling's run recorded); filter in the rule, not in the helper. Parse-check with `TestScript` before run 1. |
| `read-alloc.btm`, `Alloc.java` | The sibling's files unchanged: one `read-alloc` line per local read command on `ks1` (the replica's response building). |
| `send-read.py` | The sibling's client (protocol 5, modes `probe`, `load`, `read [--fetch-size n]`), plus printing the first value of a one-row result (for `count(*)`) and the client warnings of an error. *Amended 2026-10-15:* used for `probe` and `load` only (before any limit); the reads go through one `Session` held by `cluster-run.py` for the whole lifetime (amendment (2) above). |
| `Jmx.java` | From `column_index_cache_size`'s harness: `set <bean> <attr> str:<value>` (and read back), `get`. |
| `cluster-run.py` | One run script (Python, as the earlier cases): instrument checks, then the 9e sequence in one node lifetime; logs every command to `~/stage4-logs/crs/session.log`, writes `summary.txt` with `EXPECTED:` lines and `readings.csv`, stops the node on any exit, stops at a failed instrument check. |

```bash
# unit tier — in the run clone (copy-source.sh; never the repository's cassandra/cassandra-5.0.9/)
ant build-test
cp <harness>/CoordinatorReadSizeGuardTest.java test/unit/org/apache/cassandra/cql3/
mkdir -p $HOME/stage4-logs/crs/unit
ant testsome -Dtest.name=org.apache.cassandra.cql3.CoordinatorReadSizeGuardTest \
  -Dtest.jvm.args="-Dstage4.out=$HOME/stage4-logs/crs/unit/run.out"

# cluster tier — one node lifetime
<harness>/make-node-yaml.sh
MAX_HEAP_SIZE=4G JVM_EXTRA_OPTS="-Xbootclasspath/a:<harness>/stage4-helpers.jar -javaagent:build/lib/jars/byteman-4.0.20.jar=script:<harness>/coord-read.btm,script:<harness>/read-alloc.btm,listener:true -Dstage4.byteman.out=$HOME/stage4-logs/crs/trace.txt" \
  bin/cassandra -p $HOME/stage4-logs/crs/cassandra.pid > $HOME/stage4-logs/crs/startup.log 2>&1
<harness>/send-read.py probe
bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE ks1.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled': false} AND compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};"
<harness>/send-read.py load 8000 1000
bin/nodetool flush ks1 t
java -cp <harness> Jmx set org.apache.cassandra.db:type=StorageService CoordinatorLargeReadAbortThreshold str:262144B
<harness>/send-read.py read "SELECT * FROM ks1.t WHERE pk = 1 AND ck < 261"
<harness>/send-read.py read "SELECT * FROM ks1.t WHERE pk = 1"
```

**Starting values.**

| Quantity | Value | Why |
|---|---|---|
| Rows, payload | 8,000 × 1,000 B (cluster), 2,000 × 1,000 B (unit) | totals 8,064,000 and 2,016,000 B, above the three limits and below the top value |
| *s* | 1,008 B | exact from the schema |
| Page sizes | 100 and 1,000 rows | 100,800 B (below 262,144) and 1,008,000 B (above) per page |
| Allocation spread | 15 % (slope fits), 5 % (equal-rows pairs) | fixed at the audit (2026-10-15), before any reading |

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — `size` and *F* | Unit: `builder.getSize()` (abort and completion). Cluster: `guard-fail size=<X> limit=<F>` (abort) and `result size=<…> rows=<…>` (completion). | every read | No log line prints `size`: the WARN text prints *F* only, the `CoordinatorReadSize` histogram is bucketed. |
| **Disallow evidence** | (1) the client's `ReadFailure` with failure-map code 4; (2) the WARN line `grep -c 'size failure threshold' logs/system.log`; (3) `CoordinatorReadSizeAborts` `Count` (`org.apache.cassandra.metrics:type=Table,keyspace=ks1,scope=t,name=CoordinatorReadSizeAborts`) and `org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=ReadSizeAborts`; (4) `guard-fail`; (5) no `frame` line for the request | after each read | Code 4 is also the replica-side guards' (unset here); the client-request meter is the regular-read one even for a scan. The WARN number has thousands separators (`262,144`). |
| **Bypass volume** | C1: rows delivered over all pages against *F*; C2: the `count(*)` value; C3: rows of the switch-off read | with each arm | Paging is per page: the abort in the `fetch_size` 1,000 arm is on page 1. |
| **Real resource** | (1) coordinator: unit Δ around the white-box loop, cluster `coord-alloc` bytes; (2) frame: unit `encodedSize`, cluster `frame bytes`; (3) replica, not withheld: unit `serializedSize` of the response, cluster `read-alloc` bytes | per read | Allocated, not retained bytes: the result set is short-lived and a post-GC heap reading would not see it; the allocation is the observable, and the gap is that retention is inferred. In the scan arm the local range read can run on the same thread inside `process()` (`Stage.READ.maybeExecuteImmediately()`, [`AbstractReadExecutor.java:165`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/AbstractReadExecutor.java#L165) and the range path), so its `coord-alloc` includes replica work and is not used for a figure. |

### 9e. Running the scenarios

**Unit tier.** Commands in 9c.

1. **Setup.** Create `t`, write 2,000 rows (`ck` 0 to 1,999, 1,000-byte `v`), flush, assert one SSTable; set the hold-fixed `null`s; open the driver session with one probe read.
2. **Known answer.** Limit unset; white-box loop for `ck < 100`, `ck < 1000`, whole: `getSize()` = 100,800 · 1,008,000 · 2,016,000; record Δ (for *a*, Δ0) and the response's serialized size.
3. **For each *F* in 65,536, 262,144, 1,048,576:** set, read back, new options; white-box `ck < n*` (completes, *X*), `ck < n*+1` and whole (abort, `getSize()` = *X*, rows pulled *n\** + 1, Δ five times); response serialized size; client path `ck < n*` (rows) and whole (`ReadFailureException`, code 4, meters +1).
4. **Boundary.** *F* = 100,800 and 100,799 with the four reads of the prediction.
5. **Above the data, unset.** 4,194,304: whole completes, 2,016,000. Unset: same, meters unchanged.
6. **Frame.** At unset, `encodedSize` of `ck < 100` and `ck < 200`: difference 102,000.
7. **Arms.** At 262,144: `executeNetWithPaging` 100 (2,000 rows) and 1,000 (abort). At 65,536: `count(*)` (2,000); switch off with new options (whole completes, meters unchanged), switch back on; `QueryProcessor.executeInternal()` of the whole partition (`ReadSizeAbortException`). At 1 B: `executeNet(V5, "SELECT keyspace_name FROM system_schema.keyspaces")` (code 4); then unset.
8. **Upstream (optional).** `CoordinatorReadSizeWarningTest` once; record pass or fail.

**Before the cluster tier — instrument check** (any failure stops the run): `probe` connects at protocol 5; `Jmx.java get` reads `CoordinatorLargeReadAbortThreshold` (null) and `ReadThresholdsEnabled` (true); the rules load (`TestScript` passed), a read of `ks1.t` writes one `coord-alloc`, one `result`, one `frame` and one `read-alloc` line, a `system.local` read writes none of them; 10 s idle writes nothing; after the load and flush one `-Data.db` file exists.

**Cluster tier** (one node lifetime, in this order):

0. **Warm-up** (*runbook fix 2026-10-15 after shakedown 1, §9a unchanged; results §3*). Set 262,144 B, read `ck < 300` (aborts; **not a reading**), then write the limit back to `null` over JMX (`Jmx.java set … null:`, read back `null`): the first abort of a node lifetime carries one-off costs (class initialisation, first formatting and logging) that would otherwise land in the first scenario-B reading.
1. **Control (unset).** Read `ck < 1000`, `ck < 2000` and the whole partition: `result size` = 1,008,000 · 2,016,000 · 8,064,000 (else **Invalid**), `frame` slope 1,020 B per row, `coord-alloc` gives *a* and Δ0, `read-alloc` gives the replica baseline; meters read.
2. **For each *F* in 262,144, 1,048,576, 4,194,304, 16,777,216:** `Jmx set … str:<F>B`, read back. **Scenario A:** `ck < n*` (skip at 16 MiB): `OK n*`, `result`, `frame`. **Scenario B:** `ck < n*+1`, then the whole partition: `ERR` with code 4, `guard-fail size=X`, meters +1 each, no `frame`; record `coord-alloc` and `read-alloc` of each. At 16,777,216 the whole partition completes (8,064,000).
3. **Scenario C at 262,144.** (C1) `read --fetch-size 100` and `--fetch-size 1000` of the whole partition; (C2) `SELECT count(*) FROM ks1.t WHERE pk = 1`; (C3) `Jmx set … ReadThresholdsEnabled` false (a boolean attribute: the `Jmx.java` value type must be added, harness work), whole partition, then true; (C5) `SELECT * FROM ks1.t`. (C4) set `1B`, `SELECT keyspace_name FROM system_schema.keyspaces`, then set `16777216B` (the String setter cannot restore `null`).
4. **Stop.** `bin/nodetool stopdaemon`; copy `logs/system.log` and `trace.txt` to `~/stage4-logs/crs/`; `grep -c 'size failure threshold' logs/system.log` equals the number of aborts.

**Record for stage 4:** the yaml diff and JVM options, the exact commands, node, OS, JDK, Ant and clone commit; per read the client line, the Byteman lines, the meters before and after and the `system.log` excerpt; the unit tier's `STAGE4` lines. Full logs on the node, a small excerpt in the results folder.

**Budget.** Unit: about 3 minutes to build, a few minutes for the test. Cluster: one start (about 90 s), load and flush (about 20 s), about 40 reads and 12 JMX calls (each about 2 s), so about 6 minutes. The largest result is about 8 MB; heap 4 GiB.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — found by reading `SelectStatement` while writing up the replica-side sibling (2026-10-06) and queued as [`predicted-positive.md`](../predicted-positive.md) item 11, **unjudged**. Judged and written up 2026-10-15. Stage 1 did produce the helper row `helper:org.apache.cassandra.cql3.selection.ResultSetBuilder.shouldReject()`, which stage 2 put in **band D** (`bands.csv`, batch 35, "helper predicates for emptiness, ordering and protocol flags"): a stage-2 miss, not an absent row. |
| **Filed by / Date** | Claude (`claude-opus-5-5`) session, 2026-10-15. |
| **Line numbers checked** | 2026-10-15, against the local clone `cassandra-src` at `cassandra-5.0.9` (`git describe --tags`; `HEAD` `b5f2a54`). Every link in this file was checked by a script (file exists, cited range within the file) and the load-bearing ones also against an expected snippet of code; the load-bearing ones were read in context. |
| **Escape hatch / Target-3 note** | (1) **Off by default** (limit `null`, switch `false`). (2) **Per page:** a paged query is never refused if each page stays under the limit (arm C1); drivers page by default. (3) **The last row is never checked**, so every completed result can exceed the limit by one row, and a one-row result is never refused (§5). (4) **Post hoc for the replica answers:** the coordinator already holds every replica response for the request when the first check runs; the limit does not bound them (§5). (5) **No exemption** for system keyspaces, internal queries, superusers or driver metadata reads: a small limit breaks `system_schema` reads (the upstream test's own comment) and internal reads that go through `SelectStatement` (derived; arm C4 and the unit internal-query arm test two of these). (6) **Live-settable** over JMX by anyone with JMX access; the master switch also arms the replica-side guards. (7) **Counts value bytes only**, so the heap of a result of small values can be well above the limit (§8, inferred). |
| **Stage-4 feedback** | **2026-10-15, run 1 on `pc57`, no run 2 — unit Confirmed; cluster Confirmed (§9a row 1); bypass and replica rows as recorded.** Results: [`../../../stage4-runtime-verification/long-path/results/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes.md`](../../stage4-runtime-verification/results/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md). Step-0 audit Ready after amendments (§9a frozen `d563a86e…`; the unit allocation fit became a slope fit, one driver session for the lifetime). Cluster, 8,000 × 1,008 B: *n\** = 261 · 1,041 · 4,162 rows completed and the next row aborted at 262,144 · 1,048,576 · 4,194,304 B, the counter at every abort *X* = 263,088 · 1,049,328 · 4,195,296 for both `ck < n*+1` and the whole partition; no frame or result for any abort; coordinator allocation of an abort = that of the (*n\**+1)-row read (within 3.1 %), increments 0.2484; the replica's answer (28.09 MB allocated) built at every value. Paging 100 delivered all 8,000 rows at 262,144 B; `count(*)`, switch off complete; `system_schema.keyspaces` refused at 1 B (no exemption). Unit: 101/101 checks incl. the `>` boundary pair and the internal query refused. **Runbook defect (shakedown, before run 1):** the first abort of a node lifetime allocates about 400 KB of one-off costs, so 9e step 0 (a warm-up abort, then a JMX `null` write) was added; §9a unchanged. Nothing in §5–§8 is refuted or amended. |
| **Notes** | **Corrections to the queue note** (`predicted-positive.md` item 11, not rewritten here): (a) "`maybeFail()` runs after each row is added to the result (`:1126-1132`)" — it runs after the **previous** row is added (`newRow()` adds row *j*−1 while row *j* is being processed), and the result's **last** row is added by `build()` with no check after it (§5); (b) "not surfaced by stage 2" — the helper `shouldReject()` is a stage-2 row, banded D (above); (c) the queue's "may be post hoc, as `BatchStatement:352` was" — **half**: the replica answers are resident first, the result set, the frame and later range requests are not (§5); judged as passing Rule 3 on the second half. **Warn twin:** `ResultSetBuilder.java:87` (`shouldWarn()`, 2 units) was refused in `predicted-negative.md`'s band-B batch, group 1, Rule 3; it is also post hoc, called once after `build()` (`SelectStatement.java:1015`). **Sibling's §10** describes this check correctly (sum of selected value lengths, `>`). |

---

## 11. Notes

- **Why (b) and not (c).** The comparison returns a boolean from `shouldReject()` and a different method, `maybeFail()`, branches on it (README §3.2 (b)), as `max_hints_size_per_host`'s `shouldHint()` does. The decision point then behaves as a (c) guard: it throws and the allocations are the fall-through, so domination was checked as for (c) (§5).
- **Why it qualifies when `BatchStatement.java:352` and `PartitionDenylist.java:419` were refused as post hoc.** Those compare a finished object. Here the comparison runs row by row inside the loop that builds the result, and its throw prevents the rest of the result, the frame and, on a scan, later replica requests; Rule 2's test (does the value move the maximum bytes of the gated object?) holds one for one. The part that is post hoc, the replica answers, is recorded as not gated (§5, §8, arm "replica" in §9a), not hidden.
- **Contrast with the replica-side sibling.** The sibling counts heap sizes of rows streaming past (a flow), aborts with `>=`, is swallowed by the replica and decided by the coordinator, and exempts system keyspaces. This counts value bytes of rows that stay (a resident total), aborts with `>`, fails the request directly with no replica to spare, and exempts nothing. Both are per command/request and off by default under the same switch.
- **The unit yaml is not the node's.** `test/conf/cassandra.yaml:63-65` turns this guard on at 4096 KiB in every unit test; the shipped node has it off.
- **What this design does not cover.** `limit × N`; RF above 1 and remote replicas (the coordinator's guard does not depend on them, but the resident response sizes do); the range-batch withholding on a multi-node ring (§5, derived); the CAS-not-applied and `QueryProcessor.java:516` callers; virtual tables (no meter); collection or UDT columns (their output values are serialized for the protocol, so *s* is not the stored size).
- **Nothing here was run.** No measured number appears in this file; every figure in §9 is derived from the source and is a prediction.
