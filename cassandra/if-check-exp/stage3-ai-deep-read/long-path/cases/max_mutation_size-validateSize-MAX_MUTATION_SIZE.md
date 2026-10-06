# max_mutation_size — commit log entry

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MAX_MUTATION_SIZE-VALIDATESIZE-MAX_MUTATION_SIZE |
| **Constraint** | `max_mutation_size` — a **configuration entry** ([`Config.java:407`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L407), `IntKibibytesBound`, no value of its own). When it is unset the effective value is **derived**: half of `commitlog_segment_size`, 16 MiB at the shipped 32 MiB. The shipped [`conf/cassandra.yaml:652-660`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L652-L660) mentions it in a comment only; there is no `max_mutation_size:` line to uncomment. **Restart-only**: the value is captured once into the interface constant `IMutation.MAX_MUTATION_SIZE` (§4). |
| **Enforcement pattern** | **(c)** — a guard clause that throws before the allocation, which is the fall-through and not inside a branch. **The guard does dominate that allocation** (§5). The same verdict is read at four other call sites (§5): two earlier on the write path, one in read repair that turns the throw into a drop, and a no-op for virtual tables. |
| **Capacity check** | [`Mutation.validateSize():172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L172) — `totalSize > MAX_MUTATION_SIZE`, where `totalSize = serializedSize(version) + overhead` ([`:171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L171)). **Second check site, same constraint:** [`CounterMutation.validateSize():94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L94) — the same comparison for counter mutations, on a size that also counts the consistency-level name (§4). |
| **Decision point** | [`CommitLog.add():304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304) — the guard clause; a throw leaves `add()` before anything else in it runs. The throw itself is at [`Mutation.validateSize():174-175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L174-L175) (counters: [`CounterMutation.validateSize():96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L96)). Four other call sites read the same verdict — see §5. |
| **Allocation site** | [`CommitLog.add():311`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L311) reserves `totalSize` bytes in a commit-log segment: [`CommitLogSegmentManagerStandard.allocate():47-58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java#L47-L58) → [`CommitLogSegment.allocate():201-223`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L201-L223), which creates the `Allocation`. Just before it, [`CommitLog.add():306-308`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L306-L308) takes a thread-local **off-heap** buffer and serializes the mutation into it. |
| **Related cases** | [`cdc_total_space-processNewSegment-allowance.md`](cdc_total_space-processNewSegment-allowance.md) — same module and same entry point: `CommitLog.add()` ends in `segmentManager.allocate()`, and for CDC-enabled tables the CDC manager's [`CommitLogSegmentManagerCDC.allocate():169`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L169) adds its own guard after this one. [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md`](MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md) — the hints buffer size is derived from this limit above a floor (§8), so sweeping this knob moves that case's ceiling. [`memtable_heap_space-tryAllocate-limit.md`](memtable_heap_space-tryAllocate-limit.md) and [`memtable_offheap_space-tryAllocate-limit.md`](memtable_offheap_space-tryAllocate-limit.md) — the memtable insertion that follows this guard ([`Keyspace.applyInternal():653`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Keyspace.java#L653)) is what those cases gate. |

```java
// Mutation.validateSize():169-177 — the capacity check and the guard's two outcomes
public void validateSize(int version, int overhead)
{
    long totalSize = serializedSize(version) + overhead;           // usage side, :171
    if(totalSize > MAX_MUTATION_SIZE)                              // <-- capacity check, :172
    {
        CommitLog.instance.metrics.oversizedMutations.mark();      // the only metric on this path, :174
        throw new MutationExceededMaxSizeException(this, version, totalSize);   // disallow, :175
    }
}                                                                  // allow: returns, control falls through
```

```java
// CounterMutation.validateSize():91-98 — second check site: the same comparison, no metric
public void validateSize(int version, int overhead)
{
    long totalSize = serializedSize(version) + overhead;           // includes the consistency-level name
    if(totalSize > MAX_MUTATION_SIZE)                              // :94
    {
        throw new MutationExceededMaxSizeException(this, version, totalSize);
    }
}
```

```java
// CommitLog.add():300-311 — the guard clause (decision point) and the allocation it dominates
public CommitLogPosition add(Mutation mutation) throws CDCWriteException
{
    assert mutation != null;

    mutation.validateSize(MessagingService.current_version, ENTRY_OVERHEAD_SIZE);   // <-- guard clause, :304

    try (DataOutputBuffer dob = DataOutputBuffer.scratchBuffer.get())               // off-heap buffer, :306
    {
        Mutation.serializer.serialize(mutation, dob, MessagingService.current_version);
        int size = dob.getLength();
        int totalSize = size + ENTRY_OVERHEAD_SIZE;
        Allocation alloc = segmentManager.allocate(mutation, totalSize);            // <-- allocation, :311
        // ... the entry is copied into the segment buffer and marked written
```

## 2. Context

Every write a node accepts is first appended to a write-ahead log, the commit log, so that it survives a crash; only then is it applied to memory. The log is a series of fixed-size files (segments), and each write becomes one entry in one of them. Before an entry is written, the write is serialized into a temporary buffer and room for it is reserved in the current segment. This check is the size gate on that step: it measures the write's serialized size, plus a small fixed per-entry header, against a configured maximum and rejects the write if it is larger. The problem it solves is that one oversized write would otherwise be copied into a transient buffer as large as itself, claim an unbounded share of a segment and, if it were larger than a whole empty segment, never fit anywhere, so the log would keep opening new segments looking for room. The default maximum is half a segment, which guarantees that anything admitted fits in a fresh one.

The same test is applied earlier on the way in — when a client's statement is turned into writes, and when a replica receives one — so most oversized writes are refused before they reach the log. The limit is on **one write** (the updates to one partition key in one keyspace), not on a statement or a batch as a whole.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `commitlog` — storage engine, write-ahead log (`db/commitlog`); the size test itself lives with the write objects in `db/` (`Mutation`, `CounterMutation`, `IMutation`) |
| **One-line role** | The commit log makes each write durable by appending it to segment files before it is applied to the memtable, and replays those files after a crash. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes — per item, not cumulative.** It compares the bytes of one mutation, as it would be serialized, against a configured byte ceiling and refuses the mutation when it is larger. It keeps no running total, so what it bounds is the size of each entry; the node-wide effect needs a multiplier (§8). |
| **Usage-side operand** | `totalSize = serializedSize(version) + overhead` ([`Mutation.validateSize():171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L171)). `overhead` is the 12-byte entry header, [`CommitLogSegment.java:93`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L93), at every call site except read repair, which passes 0 (§5). `serializedSize()` sums the serialized parts without writing them ([`Mutation.serializedSize():326-341`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L326-L341), cached in an `int` field). For a `CounterMutation` the size adds the consistency-level name ([`CounterMutation.java:379-382`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L379-L382): 2 + its length, so 5 for `ONE`). |
| **Limit-side operand** | `MAX_MUTATION_SIZE`, the interface constant [`IMutation.java:31`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/IMutation.java#L31). |
| **Limit type** | **Configuration entry**, **derived** when unset (half of `commitlog_segment_size`) and validated against it. Read **once**, when `IMutation` is first initialized, so a change needs a restart. |

**Limit initialization path** (declare → derive and validate → store → read):

1. [`Config.max_mutation_size:407`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L407) — declared (`IntKibibytesBound`, renamed from `max_mutation_size_in_kb`, no value of its own). It derives from [`Config.commitlog_segment_size:397`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L397), default 32 MiB, whose own range (positive, below 2048 MiB) is checked first at [`DatabaseDescriptor.applySimpleConfig():891-896`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L891-L896).
2. [`DatabaseDescriptor.applySimpleConfig():898-901`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L898-L901) — **derived**: unset becomes `commitlog_segment_size / 2`. **Validated**: if set, `commitlog_segment_size` must be at least twice it, else startup fails with a `ConfigurationException`.
3. [`DatabaseDescriptor.getMaxMutationSize():2827-2830`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2827-L2830) — returned in bytes, as an `int`.
4. [`IMutation.MAX_MUTATION_SIZE:31`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/IMutation.java#L31) — stored in a `static final` field of the interface, so it is **fixed when `IMutation` is first initialized**: at the latest when `Mutation` or `CounterMutation` is initialized, since the interface declares a default method ([`IMutation.java:42-46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/IMutation.java#L42-L46)). A search of `src/java` for `max_mutation_size`, `MaxMutationSize` and `MAX_MUTATION_SIZE` finds no setter, JMX operation or command that changes it after startup.
5. [`Mutation.validateSize():172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L172) and [`CounterMutation.validateSize():94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L94) — read at the comparison.

**Naming note (Target 1).** The constraint is named after the first-declared variable on this path, the configuration entry `max_mutation_size`; the stem's `validateSize` is the method that encloses the comparison and `MAX_MUTATION_SIZE` is the operand as written there (README §6.1). The limit also derives from `commitlog_segment_size`, but `max_mutation_size` is the one an operator tunes.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`CommitLog.add():304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304) |
| **Verdict** | Pattern (c): the guard is the call `mutation.validateSize(...)`; there is no flag or enum. When the comparison holds, `Mutation.validateSize()` marks the `OverSizedMutations` meter and throws `MutationExceededMaxSizeException`, an `InvalidRequestException` ([`MutationExceededMaxSizeException.java:32`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/MutationExceededMaxSizeException.java#L32)); otherwise it returns and control falls through. |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `serializedSize + overhead <= MAX_MUTATION_SIZE` | `validateSize()` returns; `add()` takes the thread-local buffer, serializes the mutation and reserves `totalSize` bytes in the current segment |
| **Disallow** | `serializedSize + overhead > MAX_MUTATION_SIZE` | the meter is marked and the exception leaves `add()` from its first statement: no buffer taken, no bytes reserved, no state changed except the meter |

```java
// allow: validateSize() returns and add() continues (CommitLog.add():306-311)
try (DataOutputBuffer dob = DataOutputBuffer.scratchBuffer.get())
{
    Mutation.serializer.serialize(mutation, dob, MessagingService.current_version);
    int size = dob.getLength();
    int totalSize = size + ENTRY_OVERHEAD_SIZE;
    Allocation alloc = segmentManager.allocate(mutation, totalSize);
```

```java
// disallow: Mutation.validateSize():174-175
CommitLog.instance.metrics.oversizedMutations.mark();
throw new MutationExceededMaxSizeException(this, version, totalSize);
```

### One verdict, five call sites

`validateSize()` is called from five places. They differ in how much has already been built when the check runs and in what a refusal does.

| # | Call site | Reached by | `overhead` | What the disallow does there |
|---|---|---|---|---|
| 1 | [`SingleTableUpdatesCollector.toMutations():112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java#L112), [`BatchUpdatesCollector.toMutations():149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchUpdatesCollector.java#L149) | the **coordinator**, for every CQL write and batch (called from [`ModificationStatement.getMutations():750`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java#L750) and [`BatchStatement.getMutations():323`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L323)) | 12 | the exception leaves the statement's execution and reaches the client as `InvalidRequestException` (error code `INVALID`), before anything is sent or applied |
| 2 | [`MutationVerbHandler.doVerb():54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/MutationVerbHandler.java#L54) | a **replica** receiving a `Mutation` | 12 | thrown out of `doVerb` before forwarding and applying; [`InboundSink.accept():93-110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundSink.java#L93-L110) sends the coordinator a failure response (`RequestFailureReason.UNKNOWN`, [`RequestFailureReason.forException():82-91`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/exceptions/RequestFailureReason.java#L82-L91)) and rethrows |
| 3 | **[`CommitLog.add():304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304)** — this case's decision point | every write that is made durable, from [`CassandraKeyspaceWriteHandler.addToCommitLog():99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L99), the only caller of `add()` in `src/java` | 12 | §6b |
| 4 | [`BlockingReadRepairs.createRepairMutation():60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/repair/BlockingReadRepairs.java#L60) | **read repair** | **0** | caught at [`:63-93`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/repair/BlockingReadRepairs.java#L63-L93): the repair mutation is **dropped** (`null` is returned), logged at debug or warn, and unless suppressed the read times out (`:90`) |
| 5 | [`VirtualMutation.validateSize():122-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/VirtualMutation.java#L122-L125) | virtual tables | — | **no-op**; virtual tables hold no commit-log or memtable bytes |

### Does the guard dominate the allocation?

**For the allocation this case names, yes.** `CommitLog.add()` has one caller in `src/java`; `segmentManager.allocate()` has one caller, `CommitLog.add():311` (the abstract [`AbstractCommitLogSegmentManager.allocate():269`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L269) is implemented only by the standard and CDC managers, both reached from there); and the guard is the first statement of `add()` after the null assert ([`CommitLog.add():302-304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L302-L304)). Every path to the serialization buffer and to the segment reservation passes it.

What it does **not** dominate is the storage of the same bytes by paths that never call `add()`:

- **`durable_writes = false`.** `Mutation.apply()` passes the keyspace's durability flag ([`Mutation.apply():269`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L269)) and [`CassandraKeyspaceWriteHandler.beginWrite():51-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L51-L53) skips the commit log when it is false; the memtable insert at `Keyspace.applyInternal():653` then runs without this site. Sites 1 and 2 still apply on client and replica paths.
- **Tables that skip the commit log.** [`addToCommitLog():74-92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L74-L92) drops the tables whose memtable factory returns true from `writesShouldSkipCommitLog()`. The interface default is false ([`Memtable.java:95`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/Memtable.java#L95)) and nothing in `src/java` overrides it.
- **Commit-log replay.** [`CommitLogReader.readCommitLogSegment():324`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReader.java#L324) reads each entry's length from the file, accepts anything of 10 bytes or more ([`:337`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReader.java#L337)), allocates a heap buffer of 1.2 × that length ([`:365-366`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReader.java#L365-L366)) and [`CommitLogReplayer.handleMutation():512`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L512) applies the entry. Nothing compares the length with `MAX_MUTATION_SIZE`: entries were checked when they were written, under whichever limit was then in force, so lowering the limit does not shrink what a restart replays.
- Bytes that arrive as **SSTables** (streaming, bulk load) are not mutations and never meet this check.

Sites 1, 2 and 4 are **post hoc** for the in-memory mutation: the coordinator has already built the `PartitionUpdate`, and the replica has already deserialized the message, when they run. What they withhold is later work — sending to replicas, the log entry, the memtable insert, a hint. That is the shape `rejected.md` refuses for `BatchStatement.java:352`, so this case **rests on site 3**, where the serialization buffer and the log entry are created *after* the guard. Sites 1, 2 and 4 are recorded because they read the same verdict and move the rejection earlier.

## 6. Code path

### 6a. Allow path → object creation

1. [`ModificationStatement.getMutations():750`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java#L750) → [`SingleTableUpdatesCollector.toMutations():112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java#L112) — site 1, allowed: returns. (Batches: `BatchStatement.getMutations():323` → `BatchUpdatesCollector.toMutations():149`, once per mutation.)
2. [`StorageProxy.sendToHintedReplicas():1569`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1569) → [`StorageProxy.performLocally():1674-1692`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1674-L1692) — the local replica applies the mutation. (A remote replica goes through `MutationVerbHandler.doVerb():54`, site 2, then `applyFuture()`.)
3. [`Mutation.apply():266-270`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L266-L270) → [`Keyspace.applyInternal():625`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Keyspace.java#L625) → [`CassandraKeyspaceWriteHandler.beginWrite():51-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L51-L53) → [`addToCommitLog():99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L99).
4. [`CommitLog.add():304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304) — site 3, guard not taken: falls through.
5. [`CommitLog.add():306-310`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L306-L310) — takes the thread-local `DataOutputBuffer` (direct by default, [`DataOutputBuffer.java:55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L55), allocated at [`:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L87)) and serializes the mutation into it, growing it with [`expandToFit():174`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L174) as needed.
6. [`CommitLog.add():311`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L311) → [`CommitLogSegmentManagerStandard.allocate():47-58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java#L47-L58) — `segment.allocate(mutation, size)`; when the segment is full, [`advanceAllocatingFrom():296`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L296) moves to the next one and the loop retries.
7. [`CommitLogSegment.allocate():201-223`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L201-L223) — advances `allocatePosition` with a CAS ([`CommitLogSegment.allocate(int):240-255`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L240-L255)) and **creates the `Allocation`** at `:216`, a window of `totalSize` bytes of the segment buffer.
8. [`CommitLog.add():313-334`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L313-L334) — the entry (length, checksum, mutation bytes, checksum) is copied into the segment and marked written. Back in `Keyspace.applyInternal():653` the memtable insert follows.

### 6b. Disallow path effect

1. [`Mutation.validateSize():174-175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L174-L175) marks the meter and throws. **Nothing else changes:** the serialization buffer is not taken (`CommitLog.add():306` is after the throw), no segment space is reserved (`:311`) and no dirty mark is set (that happens inside `CommitLogSegment.allocate()`, [`:213-214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L213-L214)).
2. What the caller does depends on the site (§5):
   - **CQL write (site 1):** the exception reaches the client unchanged, an `InvalidRequestException` carrying `Rejected an oversized mutation (<T>/<M>) for keyspace: <ks>. Top keys are: <table.key>, …` ([`MutationExceededMaxSizeException.java:56-60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/MutationExceededMaxSizeException.java#L56-L60)).
   - **A write that reaches the commit log (site 3):** [`CassandraKeyspaceWriteHandler.beginWrite():61-63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L61-L63) closes the op-order group and rethrows, so `Keyspace.applyInternal()` is abandoned before any memtable write (`:625` precedes `:653`). When the caller is `StorageProxy.performLocally()`, [`:1688-1689`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1688-L1689) logs `Failed to apply mutation locally` at **ERROR** with the stack and reports the failure to the write's response handler, whose [`AbstractWriteResponseHandler.get():129-136`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java#L129-L136) throws `WriteFailureException` to the client. For a **logged batch**, the batchlog entry is written through this site ([`BatchlogManager.store():164`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/BatchlogManager.java#L164), called from [`StorageProxy.syncWriteToBatchlog():1301`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1301)), so a batch whose mutations each fit but whose batchlog entry does not fails here, as a write failure, after sites 1 passed ([`StorageProxy.mutateAtomically():1242-1248`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1242-L1248)).
   - **Replica (site 2):** a failure response to the coordinator (§5).
3. **Not a block, a retry or a hint.** No site waits, retries or hints; a refusal is permanent for that write. A refused CQL write is not hinted, because nothing was sent.
4. **If the check were absent.** [`CommitLogSegmentManagerStandard.allocate():52-56`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java#L52-L56) retries until a segment accepts the entry, and [`CommitLogSegment.allocate(int):246`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L246) refuses any size that does not fit below the end of the buffer: an entry larger than an empty segment would never be placed, and the loop would keep advancing to new segments. The guard, together with the startup rule that `commitlog_segment_size` be at least twice the limit (`DatabaseDescriptor.java:900-901`), is what keeps that unreachable. Derived from the source; §9 does not run it.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | The commit-log `Allocation` — a window of `serializedSize + 12` bytes in the active segment's buffer — and, before it, the serialized copy of the mutation in the thread-local `DataOutputBuffer`. |
| **Resource consumed** | **On-disk bytes:** the entry in a segment file, plus an 8-byte sync marker per sync ([`CommitLogSegment.java:96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L96)). **Off-heap bytes:** the serialization buffer, transient. Downstream, and not gated by this check alone, the memtable bytes for the same mutation. |
| **Rough sizing** | Entry = `serializedSize + 12`, at most `max_mutation_size`. The buffer's capacity is at least the serialized size; it grows by doubling, or by `capacity + count` for one large write, until 64 MiB and by half thereafter ([`DataOutputBuffer.calculateNewSize():158-170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L158-L170)), so it can end up to about twice the entry (inferred, not measured). After use, a buffer of up to 1 MiB is kept per thread and a larger one is replaced by a 128-byte one ([`DataOutputBuffer.java:73-79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L73-L79), default set at [`CassandraRelevantProperties.java:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L204)). |
| **Lifetime / release** | The buffer is released when the try-with-resources in `add()` closes. The entry stays in its segment until every table with data in it has been flushed (`CommitLog.discardCompletedSegments()`); the segment is then archived, recycled or deleted. |

## 8. Maximum disk and memory bound

`max_mutation_size` caps **each commit-log entry**, not their sum. A mutation whose serialized size plus 12 bytes is above it is refused before any commit-log space is reserved, so the largest entry on disk is the limit, and raising or lowering the limit moves it **one for one**. The same figure bounds the largest serialization buffer `CommitLog.add()` can take (at least the entry, and up to about twice it; off-heap and transient) and the largest single mutation inserted into a memtable.

It bounds **none of the totals.** The commit log's total size is held by `commitlog_total_space`, memtables by `memtable_heap_space` and `memtable_offheap_space`, and requests in flight by `native_transport_max_request_data_in_flight*` and `internode_application_receive_queue_*`. So the transient memory this check admits is `max_mutation_size × N`, N being the mutations applied at once (the mutation stage has `concurrent_writes` threads, [`Config.java:180`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L180), wired at [`Stage.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/Stage.java#L46): 32 × 16 MiB = 512 MiB at the defaults), or the in-flight request caps if they are smaller. A statement is not bounded either: a batch of several mutations that each fit writes their sum.

Through the commit log the limit also moves **how much disk a stream of large writes uses**. When an entry does not fit in the rest of a segment, the rest is abandoned ([`advanceAllocatingFrom():330`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L330)), so up to one entry (less than `max_mutation_size`) is lost per segment switch.

The value also **derives other limits**, which matters to anyone sweeping it (§9b holds them fixed):

- **The native-transport message cap**, when `native_transport_max_message_size` is unset: `min(max_mutation_size, in-flight caps)` ([`DatabaseDescriptor.calculateDefaultNativeTransportMaxMessageSizeInBytes():3237-3245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3237-L3245), applied at [`:905`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L905) and enforced at [`CQLMessageHandler.java:551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L551)). Protocol v4 has its own cap, `native_transport_max_frame_size`, default 16 MiB ([`Config.java:285`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L285), enforced at [`Envelope.java:429`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L429)), which equals the default limit. At stock settings a CQL client's message is therefore refused at about the size where this guard would refuse its mutation, and the guard sees such a write only in the few tens of bytes between the two thresholds.
- **The hints buffers:** `max(2 × max_mutation_size, 32 MiB)` each ([`HintsService.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L110), floor at [`:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L79)), and up to `MAX_HINT_BUFFERS` (3) of them off-heap. At the default 16 MiB the floor applies, so lowering the limit shrinks nothing, and raising it above 16 MiB grows each buffer to twice the limit.
- **Its own upper bound:** at most `commitlog_segment_size / 2` (§4).

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test finds, at several values of `max_mutation_size`, the largest mutation that is accepted and one just past it, and checks that the
accepted one lands in the commit log as an entry no larger than the limit while the refused one leaves nothing behind. One arm reaches the
commit-log check on its own (a logged batch) and one runs the unguarded replay path. **Run so far:** none. Written in this layout on
2026-10-06; not yet audited (stage-4 README, step 0).

### 9a. Procedure and conclusions

**Testability:** config, **restart-only**. `max_mutation_size` in `cassandra.yaml`; no setter, JMX operation or `nodetool` command exists, and
the value is captured once into `IMutation.MAX_MUTATION_SIZE` (§4). Unit tier: one JVM per value, using a copy of the unit yaml. Cluster tier:
one node start per value. No patched build is needed. The limit cannot exceed half of `commitlog_segment_size`, so the unit yaml (5 MiB
segments) allows at most 2.5 MiB and a node (32 MiB) at most 16 MiB; the **derived default differs by tier** for that reason.

**Claim under test:** `max_mutation_size` bounds each commit-log entry. `CommitLog.add()` throws `MutationExceededMaxSizeException` — before it
takes a serialization buffer or reserves segment space — when a mutation's serialized size plus 12 bytes exceeds the limit, so the largest entry
the node writes is the limit and the knob moves it one for one. The limit is per entry, not per statement: a batch whose mutations each fit
writes their sum (§6b, §8).

**How this verifies the hypothesis** (a restatement of the claim, procedure, prediction and conclusions in this section; it adds none):

- **Hypothesis:** the constraint caps the disk bytes of every commit-log entry, and of the off-heap buffer built from it, and a mutation over
  the limit is refused without allocating either.
- **Test:** vary `max_mutation_size` over four values in the unit tier and three on a node, each set including the derived default. At each,
  find the largest accepted mutation and the one after it. Read the check's own operand and the log's allocation counter (unit); read the
  commit log's content size, the refusal counter and what is left after a flush (node). Also send a logged batch whose mutations each fit but
  whose batchlog entry does not — it reaches the commit-log check, not the earlier ones — and restart under a lower limit to see the replay path.
- **Logic:** (1) the limit read back from the first refusal equals the value set, else the run is invalid. (2) A mutation of exactly the limit is
  accepted and one byte more is refused, with the guard's message and counter, and the refused one reserves nothing: usage **stops at the limit**.
  (3) The largest accepted entry is 1 : 4 : 16 across the node values: usage **follows the constraint**. (4) The logged-batch refusal names
  `system.batches`, and the same two mutations sent unlogged are accepted although their sum exceeds the limit: the guard, not something else,
  is what refuses, and it refuses per entry. (5) A row written under a high limit survives a restart under a low one: the recorded bypass.
- **Refuted if:** a write over the limit leaves an entry or a row; a refused write moves the commit log; the largest accepted entry does not
  move with the knob; or the refusal is not the guard's (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) run the upstream `GroupCommitLogTest` once; (b) run the harness test `MaxMutationSizeGuardTest` (9c) in one JVM per value,
   and once more with the knob above its allowed range.
2. **Cluster tier** — set up as in 9b. At each value run **Phase 1** (the limit, with plain writes) and **Phase 2** (the commit-log site, with
   a logged and an unlogged batch). At the default value also run the **derived-cap control** and the **replay arm**.
3. **At each value:** idle control → **scenario A**, reach the limit (a write of exactly the limit) → **scenario B**, try to exceed it (one byte
   over, well over, and the logged batch) → **scenario C**, the bypass arm (replay; default value only).
4. **Compare** with the prediction below and read the result in the table.

**Prediction** (stated before any run, in numbers). Notation: *M* = the limit in force; *T* = a mutation's `serializedSize + 12`, the check's
operand, which the check refuses iff *T* > *M*; *k* = *T* − payload bytes for the harness table and key, constant within a size class;
*S* = `commitlog_segment_size`.

*Unit tier*, at *M* = 262,144 · 1,048,576 · 2,097,152 · 2,621,440 (the last is the derived default, 5 MiB / 2):

- **Read-back:** `DatabaseDescriptor.getMaxMutationSize()` and `IMutation.MAX_MUTATION_SIZE` both equal *M*.
- **Boundary:** a mutation with *T* = *M* is accepted; *T* = *M* + 1 is refused with `mutationSize` = *M* + 1 and a message containing
  `(<M+1>/<M>)`, for example `(2621441/2621440)` at the derived default.
- **At `CommitLog.add()`:** the accepted entry advances the segment's allocation position by *M*, or by *M* + 8 if a sync marker is allocated in
  between; the refused one advances it by **0**, creates no segment and marks `OverSizedMutations` once. The accepted one marks it 0 times.
- **Counters:** a `CounterMutation` is refused iff *T* + 2 + len(name) > *M*, that is *T* + 5 > *M* for `ONE`, and refusing it does **not** mark
  `OverSizedMutations`.
- **Range:** with `max_mutation_size` = 3 MiB and 5 MiB segments, the JVM fails to start with `commitlog_segment_size must be at least twice the
  size of max_mutation_size / 1024`.
- **Upstream:** `GroupCommitLogTest` passes, including `testEqualRecordLimit`, `testExceedRecordLimit` and `testExceedRecordLimitWithMultiplePartitions`.

*Cluster tier*, one node, RF 1, *S* = 32 MiB, *M* = 1,048,576 · 4,194,304 · 16,777,216 (the last is the derived default):

- **Read-back:** the first refusal prints `(<T>/<M>)` with *M* equal to the value set.
- **Phase 1, scenario A:** a write with *T* = *M* is accepted; the commit log's content size rises by *M* + 8 (the entry and one 8-byte sync
  marker), plus at most 64 KiB of background writes and further markers; reading the row back returns *M* − *k* bytes.
- **Phase 1, scenario B:** writes with *T* = *M* + 1, about *M* + 8 KiB and about *M* + 1 MiB are each refused with `InvalidRequest` and the
  guard's message, each raises `OverSizedMutations` by one, and each leaves the content size within 64 KiB of where it was (an entry would add
  at least *M*). After a flush the table's `Data.db` holds the accepted row and the 1 KiB control row, about *M* − *k* + 1,024 bytes plus under
  8 KiB, and none of the refused rows exist.
- **Dose-response:** the largest accepted entry (the content-size rise less the 8-byte marker) is *M*, so across the three values it is in
  the ratio **1 : 4 : 16**.
- **Phase 2:** two partitions of ⌊0.55 *M*⌋ payload bytes each. **Unlogged:** both accepted; the content size rises by about 1.1 *M*, **more
  than *M***, and both rows read back. **Logged:** each mutation passes the earlier sites, the batchlog entry (about 1.1 *M*) does not: the client gets a
  `WriteFailure` (not `InvalidRequest`); `system.log` has `Failed to apply mutation locally` with a `MutationExceededMaxSizeException` naming
  keyspace `system` and table `batches`; `OverSizedMutations` rises by one; the content size stays within 64 KiB; neither row exists.
- **Derived-cap control** (default value, transport caps left at their defaults): a write of about *M* + 8 KiB is refused with
  `Request is too big: length <n> exceeds maximum allowed length 16777216.` and `OverSizedMutations` does not move.
- **Scenario C (replay):** after a kill and a restart with *M* = 1,048,576, the row written under the 16 MiB default is still readable with
  its full length *M*₁₆ − *k*, while a new write of the same size is refused with `(<T>/1048576)`. The size of that row is the bypass volume.

**Conclusions.**

| Result | Conclusion |
|---|---|
| Unit: at every value the boundary is exactly as predicted, and a refused `CommitLog.add()` leaves the position unchanged and marks the meter once. Cluster: the largest accepted entry follows the knob (1 : 4 : 16), every over-limit write is refused with the guard's message and counter and leaves no entry or row, and the logged batch is refused at the commit-log site | **Confirmed** — the check enforces as traced, per entry. |
| An over-limit write is accepted (an entry larger than the limit in the log, or its row readable) and no recorded bypass explains it | **Refuted** — the check does not cap usage. |
| After the restart under the lower limit the large row is readable (scenario C) | **Bypass as recorded** — replay does not compare entries with the limit (§5); expected, not a refutation. Record the size of the row (Target-3 material). |
| At the default value with the transport caps at their defaults, the refusal carries the transport's message and `OverSizedMutations` does not move | **Shadowed as recorded** — at stock settings the transport refuses first (§8); expected, not a refutation. Record it as a default-mode observation. |
| A refused write moves the commit log: the unit position moves, or the node's content size rises by 64 KiB or more above the idle control | **Refuted** — the guard does not precede the allocation (§6b is wrong). Re-read. |
| The largest accepted entry is the same at every value | **Refuted** — not the binding limit (look at the transport caps in 9b first). Re-read, do not re-run. |
| The largest accepted entry moves with the knob, but a refusal lacks the guard's message and counter (the transport's message appears instead) | **Not confirmed** — something else derived from the same limit binds (§8). Check the hold-fixed settings (9b). |
| The logged batch is accepted, or is refused with `InvalidRequest`, or its message names a table other than `system.batches` | **Not confirmed** for the commit-log site — it is not reached as traced (§5). Re-read §5. |
| The counter boundary is not *T* + 2 + len(name), or the meter moves for a counter refusal | **Refuted in part** — §4's counter arithmetic or the metric claim is wrong. |
| A limit above half the segment size starts the node | **Refuted** for the validation in §4. |
| The limit read back differs from the value set; the idle control moves 64 KiB or more in 30 s; the 1 KiB write's content-size rise is outside 1,044 to 1,536 bytes; the exact-boundary write is refused by the transport or times out; or the upstream `GroupCommitLogTest` is not green at the derived default | **Invalid run** — fix the setup (9b, 9c) and re-run. |

Two rules behind this table:

- **A confirmation needs both** the ceiling moving with the knob **and** direct evidence that the disallow branch fired: here the refusal's
  message, which prints both operands, and the `OverSizedMutations` count. A curve alone could come from the transport caps, which derive from
  the same limit (§8).
- **The replay overshoot is attributed** by an arm in which the bypass cannot fire: under the 1 MiB limit a new write of the same size is
  refused with the guard's message, while after a restart under that limit the old row is readable. The two together separate "the check does
  not cap" from "replay does not check".

**Why the content size and the message, not `du`:** a commit-log segment is a mapped file of fixed size (`TotalCommitLogSize` counts a whole
segment each), so file sizes do not show an entry. `ActiveContentSize` counts the synced bytes in the active segments, and a refusal prints both
of the check's operands. The unit tier reads the log's own allocation counter, which is exact.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `max_mutation_size` in `cassandra.yaml`, named as §4's path names it (the old name `max_mutation_size_in_kb` is also read). **Restart-only.** Unit tier: a copy of `test/conf/cassandra.yaml` with `max_mutation_size: <value>` appended, selected with `-Dcassandra.config=file:///<path>` — the mechanism `build.xml` uses for its own compression and CDC variants ([`build.xml:1266-1277`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/build.xml#L1266-L1277), [`:1288-1297`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/build.xml#L1288-L1297)). Cluster tier: the same line in the run clone's `conf/cassandra.yaml`. |
| **Confirm it took effect** | Unit: the harness test prints and asserts `DatabaseDescriptor.getMaxMutationSize()` and `IMutation.MAX_MUTATION_SIZE`. Cluster: the first refusal prints `(<T>/<M>)`, and `M` there is the constant itself, so no other read is needed. A secondary read to try at the instrument check: `SELECT name, value FROM system_views.settings WHERE name = 'max_mutation_size'`. |
| **Capacity values** | **Unit** (`commitlog_segment_size` 5 MiB): 256 KiB (262,144 B), 1 MiB (1,048,576), 2 MiB (2,097,152) and unset, which derives 2,621,440 B; plus a range control at 3 MiB. **Cluster** (`commitlog_segment_size` 32 MiB): 1 MiB (1,048,576 B), 4 MiB (4,194,304) and unset, which derives 16,777,216; the replay arm restarts with 1 MiB. An explicit value must stay at or below half of `commitlog_segment_size`. |
| **Scope** | Per mutation (the updates to one partition key in one keyspace). One request at a time, so *N* = 1 in every run; §8's `limit × N` claim is **not tested**, and the unlogged-batch arm shows the per-entry scope directly. One node, RF 1: no replica-side site, no hints, no internode path. |
| **Level** | Both. **Unit:** the upstream `GroupCommitLogTest` (the abstract `CommitLogTest`, run under six compression and encryption settings) and the harness `MaxMutationSizeGuardTest`. **Related upstream, not run:** `OversizedMutationTest` ([`OversizedMutationTest.java:31-44`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/distributed/org/apache/cassandra/distributed/test/OversizedMutationTest.java#L31-L44)), an in-JVM dtest of the coordinator path at one value, which shows refusals only; `MutationExceededMaxSizeExceptionTest`, which checks message formatting only. **Cluster:** one node. |

**What the upstream tests do and do not show.** `GroupCommitLogTest` inherits `CommitLogTest.testEqualRecordLimit` ([`CommitLogTest.java:498-506`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/commitlog/CommitLogTest.java#L498-L506)), `testExceedRecordLimit` ([`:508-528`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/commitlog/CommitLogTest.java#L508-L528)) and `testExceedRecordLimitWithMultiplePartitions` ([`:531-570`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/commitlog/CommitLogTest.java#L531-L570)). At **one** value (the derived 2,621,440 B) they show that `CommitLog.add()` accepts a mutation of exactly the limit, refuses one byte more, raises `OverSizedMutations` by one, and prints the sizes and the top keys. They do **not** show any other value, that a refused add reserves nothing, the counter site, any call site but the commit log, or a real node. The harness test and the cluster tier add those.

**Hold fixed — unit tier:**

| Setting | Value | Why |
|---|---|---|
| `commitlog_segment_size` | `5MiB`, the unit yaml's ([`test/conf/cassandra.yaml:10`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/conf/cassandra.yaml#L10)) | the derived default and the upper bound of explicit values depend on it |
| `KeyspaceParams.DEFAULT_LOCAL_DURABLE_WRITES` | `false`, as `CommitLogTest.beforeClass()` sets it | system-keyspace writes must not enter the log and move the position |
| Commit-log sync | the unit yaml's `periodic`, 10 s | the test calls `CommitLog.instance.sync(true)` before every position read, so a background sync can add at most one 8-byte marker |
| Table | the `STANDARD1` table that `CommitLogTest.beforeClass()` creates | exact payload arithmetic with the upstream helper `getMaxRecordDataSize()` |

**Hold fixed — cluster tier:**

| Setting | Value | Why |
|---|---|---|
| `commitlog_segment_size` | `32MiB` (shipped) | the default value derives from it, and every explicit value must be at most half of it |
| `commitlog_sync` | `batch`, with the `commitlog_sync_period` line removed ([`DatabaseDescriptor.java:503-507`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L503-L507)) | a write is synced before it is acknowledged, so the content size includes it when the client returns |
| `native_transport_max_frame_size` | `64MiB` | protocol v4's cap defaults to 16 MiB, equal to the default limit, and would refuse over-limit writes before the guard (§8) |
| `native_transport_max_message_size` | `64MiB` | the protocol-v5 cap derives from the limit when unset (§8); an explicit value must not exceed the in-flight caps, about 102 MiB per client address at a 4 GiB heap ([`DatabaseDescriptor.java:911-916`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L911-L916)) |
| `write_request_timeout` | `10000ms` | the default 2 s ([`Config.java:151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L151)) could time out a 16 MiB write that is synced to disk before it is acknowledged, which would be read as a refusal |
| `batch_size_fail_threshold` | `64MiB` | the default 50 KiB refuses a multi-partition batch before it reaches the batchlog ([`BatchStatement.java:352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L352)), which Phase 2 needs |
| Heap | `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE` unset | fixes the in-flight caps (heap / 10 and heap / 40, [`DatabaseDescriptor.java:651`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L651), [`:656`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L656)) that the transport caps must stay under |
| Client protocol | 4, pinned in `send-mutation.py` | one framing path |
| Table | `ks1.t (pk int PRIMARY KEY, v blob)`, compression off, autocompaction off | exact payload sizes; the flush shows the row's size |
| Replication | `SimpleStrategy`, RF 1, one node | no replica-side site, no hints |
| `durable_writes` | default `true` | the commit-log site must be on the path |
| Everything else | as shipped (`concurrent_writes` 32, `memtable_allocation_type` `heap_buffers`) | nothing else moves |

**Controls:**

- **Idle run (both tiers)** — no writes: the unit position, and the node's `ActiveContentSize` over 30 s, stay put (the node's background writes set the noise bound).
- **Small write (cluster)** — 1,024 B: the content size rises by 1,044 to 1,536 bytes. It shows the instrument resolves one write.
- **Upstream suite (unit)** — `GroupCommitLogTest` is green at the derived default.
- **Range control (unit)** — 3 MiB with 5 MiB segments does not start.
- **Derived-cap control (cluster)** — the default value with the transport caps at their defaults: shows which check refuses at stock settings.
- **Unlogged twin (cluster)** — the logged batch's two mutations sent unlogged: shows the limit is per entry.

**Reset between runs:** unit — each `ant testsome` is a fresh JVM, and the test calls `CommitLog.instance.resetUnsafe(true)` first. Cluster — stop the node (`bin/nodetool stopdaemon`, or `kill -9` for the replay arm), check `ps -eo cmd | grep '[C]assandraDaemon'` is empty, delete the clone's `data/` and `logs/`, restore `conf/cassandra.yaml` from `conf/cassandra.yaml.orig`, then write the next value's yaml. A fresh start means a fresh commit-log segment.

### 9c. Workload

The operand is one mutation's serialized size. Send writes sized to the byte, one at a time, and read the commit log before and after each.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/max_mutation_size-validateSize-MAX_MUTATION_SIZE`.
Work for step 1, before run 1 (none of it exists yet):

| File | What it is |
|---|---|
| `MaxMutationSizeGuardTest.java` | Unit tier. Package `org.apache.cassandra.db.commitlog` (it reads `CommitLog.instance.segmentManager`), modelled on `CommitLogTest`. System properties: `stage4.expect_mms` (bytes, required) and `stage4.out` (a file that also receives the `STAGE4` lines). Records `check MISMATCH` and goes on, failing at the end. Steps in 9e. |
| `make-unit-yaml.sh <label> <value\|none>` | Copies `test/conf/cassandra.yaml` to `build/test/mms-<label>.yaml` and appends `max_mutation_size: <value>` (nothing for `none`). |
| `unit-run.sh` | Runs the upstream class, then the harness test over the four values and the range control; one summary line each. |
| `make-node-yaml.sh <label> <value\|none> [default-transport]` | From `conf/cassandra.yaml.orig` writes `conf/cassandra.yaml` with the hold-fixed settings of 9b and the knob; `default-transport` leaves the two transport caps at their defaults. |
| `send-mutation.py` | Cluster tier. A Python client on the driver bundled in `lib/cassandra-driver-internal-only-3.29.0.zip`, loaded as `bin/cqlsh.py` loads it ([`bin/cqlsh.py:47-56`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/bin/cqlsh.py#L47-L56)), protocol version 4, request timeout 120 s. Modes: `probe`, `insert <pk> <bytes>`, `batch logged\|unlogged <pk1> <pk2> <bytes-each>`, `readback <pk>`. Prints `OK …` or `ERR <class> <message>`; exit 0 or 1. |
| `jmx.sh <bean> <attribute>` | `bin/nodetool sjk mx -mg -b <bean> -f <attribute>`: one attribute per call, each call a JVM start (about 1 to 2 s). |
| `cluster-run.sh` | One run script for the case (stage 4 writes it): modes `instrument`, `value <label>` (Phase 1), `batch <label>` (Phase 2), `derived`, `replay`. Logs every command to `~/stage4-logs/mms/<label>/session.log`, writes `summary.txt` and `readings.csv`, exits at the first failed check and stops the node on any failure. |

```bash
# unit tier — in the local clone (never the shared cassandra-src); once:
ant build-test
cp <harness>/MaxMutationSizeGuardTest.java test/unit/org/apache/cassandra/db/commitlog/
ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.GroupCommitLogTest      # upstream, derived 2,621,440

# one JVM per value; <label> is 256k, 1m, 2m, default, range; <bytes> the value in bytes
<harness>/make-unit-yaml.sh <label> <value|none>
ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.MaxMutationSizeGuardTest \
  -Dtest.jvm.args="-Dcassandra.config=file://$PWD/build/test/mms-<label>.yaml -Dstage4.expect_mms=<bytes> -Dstage4.out=$HOME/stage4-logs/mms/unit/<label>.out"

# cluster tier — per value: yaml, start, schema (once per start), then the writes and reads
<harness>/make-node-yaml.sh <label> <value|none>
MAX_HEAP_SIZE=4G bin/cassandra -p $HOME/stage4-logs/mms/<label>/cassandra.pid > $HOME/stage4-logs/mms/<label>/startup.log 2>&1
bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE ks1.t (pk int PRIMARY KEY, v blob) WITH compression = {'enabled': false} AND compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};"
<harness>/send-mutation.py insert <pk> <bytes>
<harness>/send-mutation.py batch logged <pk1> <pk2> <bytes-each>
<harness>/jmx.sh org.apache.cassandra.db:type=Commitlog ActiveContentSize
<harness>/jmx.sh org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations Count
```

**Starting values.** Estimates, not measurements:

| Quantity | Value | Why |
|---|---|---|
| Payload | `bytes(n)`, zero bytes | compression is off in the table and in the log, so content does not change the size |
| Small control write | 1,024 B | resolves one write's overhead |
| Calibration write | *M* + 8,192 B | refused; its message gives *T* and *M*, hence *k* = *T* − payload |
| Exact-boundary write | *M* − *k* B | *T* = *M* |
| One byte over | *M* − *k* + 1 B | *T* = *M* + 1 |
| Well over | *M* + 1 MiB | the far side: 17 MiB at the default, below the 64 MiB transport caps |
| Batch partitions | ⌊0.55 *M*⌋ B each, two partitions | each *T* is about 0.55 *M*, the sum about 1.1 *M* |
| Background bound | 64 KiB | 6.25 % of the smallest *M*; the idle control measures the real figure |

**If sizes drift:** *k* must be the same for the calibration and the exact-boundary writes. The payload length is variable-length encoded, so *k* changes by one byte at payloads of 16,384, 2,097,152 and 268,435,456; the harness checks that the two payloads are in the same class and stops the run otherwise. At the three node values they are. Record every recalibration.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — the check's operand *T* and the limit *M* | Unit: `m.serializedSize(MessagingService.current_version) + 12` and `IMutation.MAX_MUTATION_SIZE`. Cluster: the refusal's message, `Rejected an oversized mutation (<T>/<M>) for keyspace: <ks>. Top keys are: …`, which prints both; parse it with `\((\d+)/(\d+)\)`. | Unit: at each check. Cluster: at every refusal. | Only a refusal prints them; for an accepted write *T* is the payload plus *k*. |
| **Disallow evidence** — a signal only the disallow path produces | (1) The message above, with `InvalidRequest` (site 1). (2) `OverSizedMutations` `Count` (`jmx.sh org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations Count`). (3) The logged batch (site 3): the client's `WriteFailure`, and in `logs/system.log` `grep -n -A 3 'Failed to apply mutation locally'` showing a `MutationExceededMaxSizeException … keyspace: system … batches.` with `CommitLog.add` in its stack. (4) Unit: the exception, its `mutationSize`, and the position unchanged. | After each write. | The meter is marked only by `Mutation.validateSize()` ([`Mutation.java:174`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L174)), so **counter refusals do not count**. One refused CQL write marks it once; a logged batch once. The transport's refusal ([`Envelope.java:484`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L484)) marks nothing and has a different text: before relying on a signal, confirm from the source that no other path produces it. |
| **Bypass volume** — what replay let through | Scenario C: `send-mutation.py readback <pk>` returns the row's length after the restart under the lower limit. | After the restart, once `bin/nodetool statusbinary` prints `running`. | The row must have been written under the higher limit and the node **killed**, not stopped: a graceful stop drains, flushes it and deletes the segment, so nothing is replayed. Confirm in `logs/system.log` that a segment was replayed. |
| **Real resource** — the commit log's bytes, and the data left on disk | (1) `jmx.sh org.apache.cassandra.db:type=Commitlog ActiveContentSize`: the synced bytes in the active segments. (2) After `bin/nodetool flush ks1 t`: `ls -l data/data/ks1/t-*/*-Data.db`, and `readback`. (3) Unit: `CommitLog.instance.getCurrentPosition()`, the segment's allocation position. | (1) Immediately before and after every write, and at 0, 10, 20 and 30 s with no writes (the idle control). (2) Once per phase, after the last write. | **A closed segment counts as its whole capacity** ([`CommitLogSegment.java:337`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L337), [`:365`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L365)), so a write that makes the log switch segments inflates (1) by the unused tail: keep each phase's accepted writes inside one 32 MiB segment (9e). **Background writes** to system tables add to (1); the idle control sets the noise, and readings are differences, never absolute values. `du` of the commit-log directory shows whole segments and cannot see an entry. Heap and off-heap bytes are **not measured**; the buffer's size is inferred from §7. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Each check is printed as `STAGE4 check <name> <expected> <actual> ok|MISMATCH`; record pass or fail and the values.

1. **Upstream suite.** Run `GroupCommitLogTest` (9c). Record pass or fail, and for the three `*RecordLimit*` methods their result under each of the six settings. (Whether `-Dtest.methods` matches the parameterised names is untested; run the whole class.)
2. **Harness test, one JVM per value** (`256k`, `1m`, `2m`, `default`). In each JVM, after `CommitLog.instance.resetUnsafe(true)`:
   1. *Read-back:* `getMaxMutationSize()` and `IMutation.MAX_MUTATION_SIZE` equal `-Dstage4.expect_mms`; print `commitlog_segment_size`.
   2. *Calibrate:* build `m(p)` as `CommitLogTest.getMaxRecordDataSize()` does (`RowUpdateBuilder(cfs.metadata(), 0, "k").clustering("bytes").add("val", ByteBuffer.allocate(p)).build()`); find *p\** = the largest payload with *T*(p) ≤ *M*; record *T*(*p\**), *T*(*p\** + 1) and *k*, and whether *T*(*p\**) = *M*.
   3. *Boundary at the check:* `m(p*).validateSize(MessagingService.current_version, 12)` returns and leaves `OverSizedMutations` unchanged; `m(p*+1).validateSize(…)` throws `MutationExceededMaxSizeException` with `mutationSize` = *T*(*p\** + 1) and a message containing `(<T>/<M>)`, and raises the meter by one.
   4. *At the commit log:* call `CommitLog.instance.sync(true)`; read the position *P*0; `add(m(p*))` returns; read *P*1 at once (expect *P*1 − *P*0 = *M*, or *M* + 8). Call `sync(true)`; read the position *P*, the active segment count *s*, the content size *c* and the meter *n*. `add(m(p*+1))` throws; read the position again (expect *P*), the segment count (expect *s*) and the meter (expect *n* + 1); call `sync(true)` and read the content size (expect *c*).
   5. *Counter site:* `new CounterMutation(m(p* − 5), ConsistencyLevel.ONE).validateSize(…)` returns; `new CounterMutation(m(p* − 4), ConsistencyLevel.ONE).validateSize(…)` throws. Record whether the meter moved (expect: no) and `CounterMutation.serializedSize` against *T* + 5. (A standard-table mutation wrapped in a `CounterMutation`: `validateSize()` only measures serialized bytes.)
   6. *Idle:* `sync(true)`, read the position, wait 2 s, read it again (expect equal).
3. **Range control (one JVM).** Run the harness command with label `range` (3 MiB). Record the first lines containing `ConfigurationException` (expect the message of 9a's prediction) and that no test method ran.

**Before the cluster tier:**

1. **Instrument check.** On the node, with the 1 MiB yaml: (i) `send-mutation.py probe` connects over protocol 4 and prints `release_version`; (ii) `jmx.sh` reads `ActiveContentSize` and `OverSizedMutations` `Count`; (iii) a 1,024 B insert raises `ActiveContentSize` by 1,044 to 1,536; (iv) a logged batch of two 1,024 B rows succeeds, so logged batches work on one node; (v) a write of *M* + 8,192 B is refused with the guard's message and `(<T>/<M>)` parses; (vi) the idle control: 30 s with no writes moves `ActiveContentSize` by less than 64 KiB; (vii) `system_views.settings` shows `max_mutation_size` (secondary read; its absence is not a failure). Any failure of (i) to (vi) stops the run.
2. **Dataset check.** None: the table starts empty at every start.

**Cluster tier, for each value** (`1m`, `4m`, `default`). Phase 1 and Phase 2 are separate node starts so that no phase's accepted writes cross a segment boundary:

1. **Control run — Phase 1.** Fresh `data/` and `logs/`, `make-node-yaml.sh`, start the node, wait for `UN` and for `statusbinary` to print `running`, create the schema. Read `ActiveContentSize` and `OverSizedMutations` `Count` at 0, 10, 20 and 30 s (idle). `insert 0 1024` with a read before and after.
2. **Calibration.** `insert 1 <M + 8192>` → expect `ERR … Rejected an oversized mutation (<T>/<M>)`. Parse *T* and *M*; check *M* is the value set (else Invalid); *k* = *T* − (*M* + 8192); check the payload-length class of *M* + 8192 and *M* − *k* is the same. Read before and after.
3. **Scenario A — reach the limit.** `insert 2 <M − k>` → expect `OK`. Read before and after (expect +*M* + 8). `readback 2` → length *M* − *k*.
4. **Scenario B — try to exceed the limit.** `insert 3 <M − k + 1>`, `insert 4 <M + 8192>`, `insert 5 <M + 1048576>`: each `ERR` with the guard's message and *T* = payload + *k*. Read before and after each; expect `OverSizedMutations` +1 each and the content size unchanged to within 64 KiB.
5. **Flush and read back.** `bin/nodetool flush ks1 t`; `ls -l data/data/ks1/t-*/*-Data.db`; `readback 0` (1,024), `readback 2` (*M* − *k*); `readback 1`, `3`, `4`, `5` (no row).
6. **Stop.** `bin/nodetool stopdaemon`, check no `CassandraDaemon` is left, copy `logs/system.log` to `~/stage4-logs/mms/<label>/`; `grep -c '^ERROR'` it (expect none from the refusals above: a refusal at site 1 is a `TransportException`, which [`ErrorMessage.fromException():465-473`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/ErrorMessage.java#L465-L473) returns to the client without logging).
7. **Phase 2 — the commit-log site.** Fresh start of the same value (the start and schema of step 1; idle reads for 10 s). `batch unlogged 10 11 <⌊0.55 M⌋>` with a read before and after → expect `OK` and a rise of about 1.1 *M*; `readback 10`, `11`. `batch logged 12 13 <⌊0.55 M⌋>` with a read before and after → expect `ERR WriteFailure`, the meter +1 and the content size unchanged to within 64 KiB; `readback 12`, `13` → no row; `grep -n -A 3 'Failed to apply mutation locally' logs/system.log`. Stop as in step 6.

**Derived-cap control (default value only).** `make-node-yaml.sh default none default-transport`, start, schema, idle reads for 10 s, `insert 20 <M + 8192>` → expect `ERR … Request is too big: length <n> exceeds maximum allowed length 16777216.` with the meter and the content size unchanged; `insert 21 1024` → `OK` (the node still serves). Stop.

**Scenario C — replay (default value only).** Fresh start at the default value (yaml as Phase 1), schema, `insert 30 <M − k>` → `OK`. Confirm a segment file in `data/commitlog/`. `kill -9` the `CassandraDaemon` process (a graceful stop would drain it away). Check no daemon is left. `make-node-yaml.sh replay 1MiB` **without** wiping `data/`, start, wait for `UN` and `running`. `grep -i 'replay' logs/system.log` (expect a replay of the segment). `readback 30` → expect length *M* − *k*, the 16 MiB row, although the limit is now 1 MiB. `insert 31 <M − k>` with *M* the old default → expect `ERR … (<T>/1048576)`. Stop.

**Record for stage 4:** the `cassandra.yaml` diff against the shipped file and the JVM options in force, the exact commands, the node, OS, JDK and Ant versions and the clone's commit, and the raw readings of 9d for every write: the client's line, the three JMX readings before and after, the segment listing, the `Data.db` sizes, and the `system.log` excerpts. Keep the full logs on the node and a small excerpt per value in the results folder.

**Budget.** Unit: about 2.5 minutes to build; the upstream class runs the whole `CommitLogTest` under six settings, so allow up to a quarter of an hour; about one minute per harness JVM. Cluster: about 90 s to start a node, about 3 minutes per Phase 1 and 2 per Phase 2, so about 5 minutes per value and about 25 minutes for the whole tier with the control and the replay arm. The largest write is 17 MiB; the commit log and flush stay under 100 MiB per value; the node has 125 GiB of memory and 63 GB of local disk, so none of this is near a limit.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — from [`../../../stage2-ai-preprocessing/bands.md`](../../../stage2-ai-preprocessing/bands.md)'s **band A1** list, rows `Mutation.java:172#1` ("mutation total size against the max mutation size, rejecting the mutation") and, as its second site, `CounterMutation.java:94#1` ("counter mutation total size against the max mutation size, rejecting the mutation"); both ranked in stage-2 batch 18 (`bands.csv`, 2026-09-24). Judged in the band-A1 pass on 2026-09-28 and recorded in `pending.md`; written up 2026-10-06. |
| **Filed by / Date** | Claude (`claude-sonnet-5-5`) session, 2026-10-06 |
| **Line numbers checked** | 2026-10-06 against the local `cassandra-5.0.9` clone at `~/repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`, `HEAD` `b5f2a54210`). Every cited line was checked by a script that finds an expected snippet of code inside the cited range and that label and anchor agree; the load-bearing ones were also read in context. |
| **Escape hatch / Target-3 note** | **No flag or setting turns the check off**, but it is not the only thing that decides what a client can write, and several paths do not meet it. (1) **Stock settings shadow it for CQL writes:** the transport caps are derived from, or equal to, the default limit (§8), so at defaults a client's message is refused at about the size where this guard would refuse its mutation, and the guard sees such a write only in a window of a few tens of bytes; the derived-cap control measures the shadow, the window is source-derived and not measured. Raising `max_mutation_size` alone does not let a CQL client write more, since protocol v4's frame cap stays at 16 MiB. (2) **Replay is unguarded** (§5): a lower limit does not bound what a restart replays. (3) **Read repair drops** an oversized repair mutation with only a debug or warn line (and possibly a read timeout), and passes `overhead` 0, so a repair mutation whose size lies in (limit − 12, limit] passes there and is refused by the replica's `MutationVerbHandler`, which passes 12. (4) **Counter refusals are not metered**, and a counter's size counts the consistency-level name, so its boundary differs from a plain mutation's by `2 + len(name)` bytes. (5) **Per entry, not per statement:** a batch's total can exceed the limit; only a logged batch's batchlog entry is bounded as a whole. (6) **Node-local:** the value is not exchanged or compared between nodes, so a replica with a lower limit refuses what the coordinator accepted (source-derived, not run). (7) **`durable_writes = false`** skips the commit-log site (§5). (8) **Size arithmetic:** `Mutation.serializedSize()` casts a `long` to `int` ([`Mutation.java:332`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L332), [`:336`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L336)), so a mutation of 2 GiB or more would wrap negative and pass the comparison; not reachable through the stock CQL path, whose transport caps refuse far below that; not chased. |
| **Stage-4 feedback** | none yet. §9 was written in the new layout on 2026-10-06 (9a to 9e), not converted from an older §9; it is not yet audited (stage-4 README, step 0) and not yet run. It lists its harness as work for step 1. |
| **Notes** | **Found while writing this up (2026-10-06), for stage 3 to judge; `pending.md` and `rejected.md` are not rewritten.** *Five call sites, not one:* the earlier notes name `CommitLog.add():304`; four more read the same verdict (§5), and the case rests on the commit-log site because the others are post hoc. *"The hints buffer scales with it" holds only above 16 MiB:* `rejected.md`'s A1 lesson gives it as a reason this limit moves a maximum, but the hints buffer is `max(2 × limit, 32 MiB)` (§8), so at the default and below it does not move; the commit-log entry and the serialization buffer do, and they are what this case rests on. *The limit is fixed at class initialization,* which the earlier notes do not say (§4). *The check is not allocation-free:* below `CACHEABLE_MUTATION_SIZE_LIMIT` (default 1,000,000 bytes, [`CassandraRelevantProperties.java:80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L80)) measuring the size serializes the mutation into the scratch buffer and caches a `byte[]` copy on it ([`Mutation.serialization():439-466`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L439-L466), reached from `validateSize()` through `serializedSize()`); this is bounded, and is the check's own measuring step rather than the commit-log allocation it guards, but it ties this case to `pending.md` item 3 (`CACHEABLE_MUTATION_SIZE_LIMIT`), which should cite it. **(2026-10-06, documentation only: item 3 is now filed as [`CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT.md`](CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT.md), and cites this case.)** |

---

## 11. Notes

- **Why one case for two comparison sites and five call sites.** `Mutation.validateSize()` and `CounterMutation.validateSize()` are the same
  comparison on two `IMutation` types: they read the same constant and feed the same decision, so README §6.1's "one case, several check sites"
  applies and the case is named after the primary site (`Mutation:172`), with `CounterMutation:94` listed in §1. The five *call* sites of §5 are a
  different thing: they read the verdict, they are not separate comparisons.
- **Why this qualifies when `internode_max_message_size` was refused.** `rejected.md` refuses per-item bounds whose total is held elsewhere:
  for `Message.java:817` and its three siblings, "the queue cap still binds" and raising the limit alone moves no maximum. Here nothing else bounds the
  size of one commit-log entry or of the buffer built for it, so the limit moves those maxima directly. What it does not move is any total,
  and §8 says so; that is the playbook's rule that a per-object limit needs a multiplier before it says anything about the node.
- **Contrast with `BatchStatement.java:352`.** That check was refused as post hoc: it runs after the batch is built. Sites 1, 2 and 4 here
  have the same shape and are not what qualifies the case; site 3, which runs before the buffer and the entry exist, is.
- **The unit yaml is not the node's.** The unit yaml's 5 MiB segments make the derived default 2.5 MiB (2,621,440 B); a node's 32 MiB makes it
  16 MiB. This is the trap `cdc_total_space`'s stage-4 run hit for the same setting; do not assume the unit default is the node's.
- **A logged batch is the client-reachable way to the commit-log site.** A plain CQL write over the limit is refused at site 1, so the
  commit-log guard never sees it; a logged batch of several partitions passes site 1 per mutation and is written to the batchlog as one mutation,
  which only the commit-log site bounds. Phase 2 of §9 exists for that reason. It needs `batch_size_fail_threshold` raised above the batch,
  because the default 50 KiB refuses a multi-partition batch first.
- **What this design does not cover.** The replica-side site (it needs two nodes with different limits); the read-repair site; *N* > 1, the
  multiplier; the hints buffer's growth above 16 MiB (that belongs with `MAX_HINT_BUFFERS`); `durable_writes = false`; the protocol-v5 derived
  message cap (the derived-cap control uses v4); and the loop that would never end without the guard (§6b, derived from the source and
  destructive to run). Each is recorded from the source in §5, §6b or §8.
- **Nothing here was run.** No measured number appears in this file; every figure in §9 is derived from the source and is a prediction.
