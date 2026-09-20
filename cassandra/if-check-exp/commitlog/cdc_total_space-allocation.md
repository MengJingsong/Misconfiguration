# cdc_total_space — allocation

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | CDC_TOTAL_SPACE-ALLOCATION |
| **If-statement** | [`CommitLogSegmentManagerCDC.throwIfForbidden():214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L214) |

```java
private void throwIfForbidden(Mutation mutation, CommitLogSegment segment) throws CDCWriteException
{
    if (mutation.trackedByCDC() && segment.getCDCState() == CDCState.FORBIDDEN)
    {
        cdcSizeTracker.submitOverflowSizeRecalculation();
        String logMsg = String.format("Rejecting mutation to keyspace %s. Free up space in %s by processing CDC logs. " +
                                      "Total CDC bytes on disk is %s.",
                                      mutation.getKeyspaceName(), DatabaseDescriptor.getCDCLogLocation(),
                                      cdcSizeTracker.sizeInProgress.get());
        NoSpamLogger.log(logger, NoSpamLogger.Level.WARN, 10, TimeUnit.SECONDS, logMsg);
        throw new CDCWriteException(logMsg);
    }
}
```

The `CDCState.FORBIDDEN`/`PERMITTED` flag itself is set by a sibling check,
[`permitSegmentMaybe():192-209`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L192-L209),
which is where the actual byte-count comparison against `cdc_total_space`
happens:

```java
private void permitSegmentMaybe(CommitLogSegment segment)
{
    if (segment.getCDCState() != CDCState.FORBIDDEN)
        return;

    if (!DatabaseDescriptor.getCDCBlockWrites()
        || cdcSizeTracker.sizeInProgress.get() + DatabaseDescriptor.getCommitLogSegmentSize() < DatabaseDescriptor.getCDCTotalSpace())
    {
        CDCState oldState = segment.setCDCState(CDCState.PERMITTED);
        if (oldState == CDCState.FORBIDDEN)
        {
            FileUtils.createHardLink(segment.logFile, segment.getCDCFile());
            cdcSizeTracker.addSize(DatabaseDescriptor.getCommitLogSegmentSize());
        }
    }
}
```

Both are called together, in order, from
[`allocate():169-188`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L169-L188),
on every mutation write attempt — `permitSegmentMaybe()` re-evaluates and
possibly flips the segment's state (in case CDC consumers freed up space
since it was last marked forbidden), then `throwIfForbidden()` reads that
state and decides whether *this* mutation may proceed. This case treats the
pair as one logical capacity check: §4 traces the byte-count comparison
(inside `permitSegmentMaybe`), while §1/§5/§6 focus on `throwIfForbidden`,
which is the actual branch point that diverges on object creation.

## 2. Context

Change Data Capture (CDC) lets external consumers tail a copy of a table's
write stream by hard-linking each commit log segment that contains
CDC-flagged mutations into a separate CDC directory, where it stays until a
consumer has finished reading and deletes it. If consumers fall behind,
these hard-linked segments accumulate — since deleting the original commit
log segment doesn't free the disk/mmap'd space still referenced by its CDC
hard-link. Without a cap, a slow or stalled CDC consumer would let this
retained segment data grow without bound as writes keep flowing in. This
if-check is the enforcement point: before a CDC-tracked mutation is allowed
to write into the currently-active commit log segment, the system checks
whether the total size of not-yet-consumed CDC segment data is already at
its configured ceiling — if so, the write is rejected outright rather than
being accepted and further inflating that backlog.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | storage engine — commit log (`db/commitlog`) |
| **One-line role** | Durability log that every write is appended to before being applied to memtables; the CDC variant additionally retains a hard-linked copy of segments containing CDC-tracked mutations for external consumption. |

## 4. Capacity-overflow check

| Field | Content |
|-------|---------|
| **Is this a capacity/overflow check?** | Yes — `permitSegmentMaybe()` compares a running total of un-consumed CDC segment bytes plus one more segment's worth against a configured ceiling, and `throwIfForbidden()` acts on the resulting state to reject or admit the individual mutation. |
| **Usage-side operand** | `cdcSizeTracker.sizeInProgress` — a `volatile`-read `AtomicLong` on `CommitLogSegmentManagerCDC.CDCSizeTracker`, tracking total bytes of CDC-hard-linked segment files currently retained on disk (incremented in `permitSegmentMaybe()`/`processNewSegment()`, decremented as consumed segments are deleted). |
| **Limit-side operand** | `cdc_total_space` (read via `DatabaseDescriptor.getCDCTotalSpace()`) — a `Config` field, mebibytes converted to bytes. |
| **Limit type** | Configuration (`cdc_total_space`, defaults to 0 which triggers an auto-derived value — see below). |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:418-419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L418-L419) — declared: `cdc_total_space` (`DataStorageSpec.IntMebibytesBound`, default `"0MiB"`).
2. [`DatabaseDescriptor.java:684-694`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L684-L694) — derived if left at 0 and `cdc_enabled` is true: `calculateDefaultSpaceInMiB(..., 1, 8)` sizes it to 1/8th of the `cdc_raw_directory` filesystem's total space (capped at a 4096 MiB preferred default).
3. [`DatabaseDescriptor.java:4370-4372`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4370-L4372) — read/converted: `getCDCTotalSpace()` returns `conf.cdc_total_space.toBytesInLong()`.
4. [`CommitLogSegmentManagerCDC.java:200-201`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L200-L201) — read at the point of comparison, inside `permitSegmentMaybe()`.

## 5. Branch semantics

| Branch | Condition | Effect |
|--------|-----------|--------|
| **Allow** | `mutation.trackedByCDC()` is false, **or** the segment's `CDCState` is not `FORBIDDEN` (i.e. `permitSegmentMaybe()` found `sizeInProgress + segmentSize < cdc_total_space`, or `cdc_block_writes` is disabled) | `throwIfForbidden()` returns normally; `allocate()` proceeds to reserve space in the segment and serialize the mutation into it. |
| **Disallow** | `mutation.trackedByCDC()` is true **and** the segment's `CDCState` is `FORBIDDEN` (i.e. `sizeInProgress + segmentSize >= cdc_total_space` and `cdc_block_writes` is enabled) | Throws `CDCWriteException` — the mutation is never appended to the commit log. |

```java
// allow path: throwIfForbidden() falls through (no exception), back in allocate():
while ( null == (alloc = segment.allocate(mutation, size)) )
{
    advanceAllocatingFrom(segment);
    segment = allocatingFrom();
    permitSegmentMaybe(segment);
    throwIfForbidden(mutation, segment);
}
if (mutation.trackedByCDC())
    segment.setCDCState(CDCState.CONTAINS);
return alloc;
```

```java
// disallow path (throwIfForbidden body, quoted in full in §1)
throw new CDCWriteException(logMsg);
```

## 6. Code path

### 6a. Allow branch → object creation

1. [`CassandraKeyspaceWriteHandler.addToCommitLog():99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L99) — every durable write calls `CommitLog.instance.add(mutation)`.
2. [`CommitLog.add():311`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L311) — calls `segmentManager.allocate(mutation, totalSize)`.
3. [`CommitLogSegmentManagerCDC.allocate():175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L175) — `throwIfForbidden()` returns normally (allow branch), execution continues.
4. [`CommitLogSegmentManagerCDC.allocate():174`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L174) — `segment.allocate(mutation, size)` is called on the underlying `CommitLogSegment`.
5. [`CommitLogSegment.allocate():201-217`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L201-L217) — reserves `size` bytes within the segment's already-mapped buffer (`allocate(size)` at line 206, a lock-free position bump), then **object creation**: `return new Allocation(this, opGroup, position, (ByteBuffer) buffer.duplicate()...)` (line 216) — an `Allocation` wrapping a live view into the segment's buffer at the reserved offset.
6. The mutation's serialized bytes are then written into that buffer view (in `CommitLog.add()`, around [`CommitLog.java:311-329`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L311-L329)), occupying real bytes of the segment's memory-mapped (or, for compressed/encrypted/direct-IO segments, off-heap-buffered) region — see §7 for the nuance that the segment's buffer itself is allocated once at segment creation, independent of this check.

### 6b. Disallow branch effect

**A clean reject, not a block or defer** — unlike this folder's other net/hints
cases, no backpressure or wait queue is involved here.

1. [`CommitLogSegmentManagerCDC.throwIfForbidden():226`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L226) — `throw new CDCWriteException(logMsg)`, a `RequestExecutionException` subtype (mapped to CQL protocol error code `CDC_WRITE_FAILURE`).
2. This propagates unhandled up through `allocate()` → `CommitLog.add()` → `CassandraKeyspaceWriteHandler.addToCommitLog()`/`beginWrite()` → the write path's caller — the mutation is **never appended to the commit log and never applied to memtables**: `CDCWriteException` is thrown before `Keyspace.writeOrder` work proceeds, so no partial state is left behind. The client-visible effect is a failed write (comparable to a timeout/overload response), which the application must retry.
3. **Escape hatch:** setting `cdc_block_writes` (config, live-mutable via `DatabaseDescriptor.setCDCBlockWrites()`/JMX) to `false` makes `permitSegmentMaybe()` always mark the segment `PERMITTED` regardless of `sizeInProgress`, so `throwIfForbidden()` never fires — CDC-tracked writes are then let through unconditionally, growing the retained CDC backlog past `cdc_total_space` instead of being rejected (flagged for Target 3, not pursued here — same shape as the memtable cases' `markBlocking()`).

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `CommitLogSegment.Allocation` (a view into the segment's already-allocated buffer) — but the memory-significant object this check is actually gating retention of is the **CDC hard-linked commit log segment** itself, which stays resident (via `FileUtils.createHardLink`) until consumed. |
| **Resource consumed** | Off-heap/mapped memory: the default `MemoryMappedSegment` backs each commit log segment with a memory-mapped file of `commitlog_segment_size` bytes (compressed/encrypted/direct-IO variants use direct `ByteBuffer`s instead); the CDC hard-link keeps that segment's on-disk file (and therefore its mappable/cached content) from being reclaimed after the original commit log has rotated past it. |
| **Rough sizing** | Each retained CDC segment is a fixed `commitlog_segment_size` (default 32MiB) block; total bytes retained = `sizeInProgress`, tracked directly by `CDCSizeTracker`. |
| **Lifetime / release** | A CDC hard-link is released when an external consumer finishes reading it and it is deleted (`processDiscardedSegment()` / `deleteOldLinkedCDCCommitLogSegment()`), which decrements `sizeInProgress` and can flip a `FORBIDDEN` segment back to `PERMITTED` on the next `permitSegmentMaybe()` call. |

## 8. Maximum memory bound

`cdc_total_space` directly caps the total bytes of CDC-hard-linked commit
log segments the node will retain unconsumed at any time: `permitSegmentMaybe()`
only keeps admitting new CDC-tracked writes into a segment while
`sizeInProgress + one segment's size < cdc_total_space`; once that ceiling is
reached, every further CDC-tracked mutation is rejected via
`throwIfForbidden()` rather than being written and further growing the
backlog. Raising `cdc_total_space` raises how large this retained-but-unconsumed
segment backlog is allowed to grow before writes to CDC-enabled tables start
failing; lowering it makes CDC writes start failing sooner under the same
consumer lag, trading write availability for a tighter memory/disk ceiling.
Because the limit is compared in units of whole `commitlog_segment_size`
blocks (`sizeInProgress + segmentSize < limit`, not a byte-exact check), the
practical ceiling is always within one segment size of the configured value,
never below it. Non-CDC-tracked mutations are entirely unaffected — the
check only gates `mutation.trackedByCDC()` writes.

## Verification

See [README.md § Verifying a case](../README.md#verifying-a-case-triggering-the-disallow-branch)
before setting `Status: verified` — line-number checking alone is not enough;
a designed experiment must have actually driven execution into the disallow
branch with recorded evidence.

| Field | Content |
|--------|---------|
| **Status** | pending |
| **Verified By / Date** | — |
| **Trigger method** | Not yet run. An existing test, `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java`, already targets this exact check: its `testWithCDCSpaceInMb(size, ...)` helper (around line 428) sets `cdc_total_space` to a small value via `DatabaseDescriptor.setCDCTotalSpaceInMiB(size)`, then `bulkWrite()` (around line 452) writes CDC-tracked mutations in a loop and asserts a `CDCWriteException` is thrown once `cdc_block_writes` is enabled and the space is exhausted (`Assert.fail("Expected CDCWriteException from full CDC but did not receive it.")` if it's *not* thrown). Several `@Test` methods (e.g. around lines 80, 109, 115, 121, 142) already exercise this via `testWithCDCSpaceInMb`. Reuse as-is via `ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDCTest` — check which specific `@Test` method most directly isolates the `cdc_total_space` boundary (vs. the `cdc_block_writes`-toggle tests) before citing one as primary evidence. |
| **Evidence** | Not yet captured — expected: `BUILD SUCCESSFUL`, the relevant `@Test` passes, confirming a `CDCWriteException` was thrown and caught exactly where `bulkWrite()` expects it once CDC space is exhausted. |
| **Notes** | Line numbers checked against the local pinned-tag clone (`/cassandra-cassandra-5.0.9/cassandra-cassandra-5.0.9`, confirmed `5.0.9` via `build.xml`/`CHANGES.txt`) on 2026-09-17. Behavioral trigger not yet run. |

---

## Notes

- **Escape hatch found:** `cdc_block_writes = false` (default `true`) makes
  `permitSegmentMaybe()` always permit CDC writes regardless of
  `sizeInProgress`, bypassing this check entirely — same shape as the
  memtable cases' `markBlocking()`. Flagged for Target 3.
- **Two-tier check:** unlike the memtable/net/hints cases where a single
  comparison gates a single divergence, this case is a pair —
  `permitSegmentMaybe()` computes and caches the segment's admit/forbid
  state (the byte-count comparison against `cdc_total_space`), and
  `throwIfForbidden()` (this case's primary citation) is the actual
  per-mutation branch point that acts on that cached state. Both were kept
  in one case file rather than split, since they're inseparable parts of
  one mechanism reached together on every write attempt (see §1 note).
- **Object creation nuance:** the segment's underlying buffer
  (`MemoryMappedSegment`/`CompressedSegment`/etc.) is allocated once at
  segment creation regardless of CDC — this check doesn't gate *that*
  allocation, only whether a specific CDC-tracked mutation's bytes are
  permitted to be written into it and whether the CDC hard-link keeps that
  segment's data retained past when it would otherwise be discarded. This
  is a softer fit for Rule 2 than the memtable/hints cases' fresh
  `ByteBuffer.allocate()`-per-limit-increment pattern — worth a second look
  if the filter rules are tightened further, but the check clearly
  determines the total bytes of segment data the node keeps resident
  unconsumed, which is the substance Rule 2 asks for.
