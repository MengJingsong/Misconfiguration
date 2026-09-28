# cdc_total_space — allocation

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | CDC_TOTAL_SPACE-PROCESSNEWSEGMENT-ALLOWANCE |
| **Constraint** | `cdc_total_space` — configuration entry (`Config.java`) |
| **Enforcement pattern** | (b) — the capacity check sets a verdict (the segment's `CDCState`: `FORBIDDEN` / `PERMITTED`), and a separate decision point reads it |
| **Capacity check** | [`CDCSizeTracker.processNewSegment():335-337`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L335-L337) — a ternary, not an `if`: `segment.setCDCState(blocking && segmentSize + sizeInProgress.get() > allowance ? FORBIDDEN : PERMITTED)`, where `allowance = DatabaseDescriptor.getCDCTotalSpace()` (line 329). **Second check site, same verdict:** [`permitSegmentMaybe():200-201`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L200-L201) — `!getCDCBlockWrites() \|\| sizeInProgress + segmentSize < getCDCTotalSpace()` — re-evaluates a `FORBIDDEN` segment and can flip it back to `PERMITTED`. |
| **Decision point** | [`throwIfForbidden():214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L214) — `if (mutation.trackedByCDC() && segment.getCDCState() == CDCState.FORBIDDEN)` → throws `CDCWriteException` at [line 226](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L226) |
| **Allocation site** | [`CommitLogSegment.allocate():201-217`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L201-L217) — the `Allocation` for the mutation, reached only if `throwIfForbidden()` returns normally |
| **Related cases** | none |

**Verdict propagation (pattern (b)).** The verdict is the segment's `cdcState`
field, written by `processNewSegment()` when a segment is created (line 335)
and by `permitSegmentMaybe()` on every write attempt (line 203), and read by
`throwIfForbidden()`. `CommitLogSegment.setCDCState()`
([`CommitLogSegment.java:681-694`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L681-L694))
only allows `FORBIDDEN` → `PERMITTED`, never the reverse, so a segment that
was marked `FORBIDDEN` at creation stays so until `permitSegmentMaybe()` finds
room.

The decision point, `throwIfForbidden()`:

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

The capacity check that sets the verdict, `processNewSegment()` (called when a
segment is created, see
[`CommitLogSegmentManagerCDC.java:241`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L241)):

```java
long allowance = DatabaseDescriptor.getCDCTotalSpace();
boolean blocking = DatabaseDescriptor.getCDCBlockWrites();
synchronized (segment.cdcStateLock)
{
    segment.setCDCState(blocking && segmentSize + sizeInProgress.get() > allowance
                        ? CDCState.FORBIDDEN
                        : CDCState.PERMITTED);
    if (segment.getCDCState() == CDCState.PERMITTED)
        addSize(segmentSize);
}
```

and its re-evaluation twin, `permitSegmentMaybe()`
([`:195-210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L195-L210)):

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

On every mutation write attempt, `allocate()`
([`:169-188`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L169-L188)) calls `permitSegmentMaybe()` (possibly flipping the
state) and then `throwIfForbidden()` (acting on it). One case covers both check
sites because they compute the same verdict for the same decision point; the
case is named after the primary one, `processNewSegment()`, where a segment's
verdict is first set.

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

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | Yes — `processNewSegment()` (and, on re-evaluation, `permitSegmentMaybe()`) compares a running total of un-consumed CDC segment bytes plus one more segment's worth against a configured ceiling and records the result as the segment's `CDCState`; `throwIfForbidden()` then acts on that state to reject or admit each mutation. |
| **Usage-side operand** | `cdcSizeTracker.sizeInProgress` — a `volatile`-read `AtomicLong` on `CommitLogSegmentManagerCDC.CDCSizeTracker`, tracking total bytes of CDC-hard-linked segment files currently retained on disk (incremented in `permitSegmentMaybe()`/`processNewSegment()`, decremented as consumed segments are deleted). |
| **Limit-side operand** | `allowance` in `processNewSegment()` (a local variable holding `DatabaseDescriptor.getCDCTotalSpace()`, i.e. the `cdc_total_space` `Config` field converted to bytes); `permitSegmentMaybe()` reads `getCDCTotalSpace()` directly. |
| **Limit type** | Configuration (`cdc_total_space`, defaults to 0 which triggers an auto-derived value — see below). |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:418-419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L418-L419) — declared: `cdc_total_space` (`DataStorageSpec.IntMebibytesBound`, default `"0MiB"`).
2. [`DatabaseDescriptor.java:684-694`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L684-L694) — derived if left at 0 and `cdc_enabled` is true: `calculateDefaultSpaceInMiB(..., 1, 8)` sizes it to 1/8th of the `cdc_raw_directory` filesystem's total space (capped at a 4096 MiB preferred default).
3. [`DatabaseDescriptor.java:4370-4372`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4370-L4372) — read/converted: `getCDCTotalSpace()` returns `conf.cdc_total_space.toBytesInLong()`.
4. [`CommitLogSegmentManagerCDC.java:329`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L329) — read into the local `allowance` at the primary comparison in `processNewSegment()` (line 335); also read directly at [`:200-201`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L200-L201) inside `permitSegmentMaybe()`.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`throwIfForbidden():214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L214) — `if (mutation.trackedByCDC() && segment.getCDCState() == CDCState.FORBIDDEN)` → throws `CDCWriteException` at [line 226](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L226) |
| **Verdict** | the segment's `CDCState` (`FORBIDDEN` / `PERMITTED`), set in `processNewSegment():335` (re-evaluated by `permitSegmentMaybe()`), read in `throwIfForbidden():214`. |

The verdict is the segment's `CDCState`. The table gives the decision point's two outcomes (`throwIfForbidden()` at line 214).

| Outcome | Condition | Effect |
|---------|-----------|--------|
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

### 6a. Allow path → object creation

0. **Verdict.** [`processNewSegment():335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L335) marks the segment `PERMITTED` (or [`permitSegmentMaybe():203`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L203) flips it there); the state is stored on the `CommitLogSegment` and read at the decision point below.

1. [`CassandraKeyspaceWriteHandler.addToCommitLog():99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CassandraKeyspaceWriteHandler.java#L99) — every durable write calls `CommitLog.instance.add(mutation)`.
2. [`CommitLog.add():311`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L311) — calls `segmentManager.allocate(mutation, totalSize)`.
3. [`CommitLogSegmentManagerCDC.allocate():175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L175) — `throwIfForbidden()` returns normally (allow branch), execution continues.
4. [`CommitLogSegmentManagerCDC.allocate():174`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L174) — `segment.allocate(mutation, size)` is called on the underlying `CommitLogSegment`.
5. [`CommitLogSegment.allocate():201-217`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L201-L217) — reserves `size` bytes within the segment's already-mapped buffer (`allocate(size)` at line 206, a lock-free position bump), then **object creation**: `return new Allocation(this, opGroup, position, (ByteBuffer) buffer.duplicate()...)` (line 216) — an `Allocation` wrapping a live view into the segment's buffer at the reserved offset.
6. The mutation's serialized bytes are then written into that buffer view (in `CommitLog.add()`, around [`CommitLog.java:311-329`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L311-L329)), occupying real bytes of the segment's memory-mapped (or, for compressed/encrypted/direct-IO segments, off-heap-buffered) region — see §7 for the nuance that the segment's buffer itself is allocated once at segment creation, independent of this check.

### 6b. Disallow path effect

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


## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** Method and pitfalls:
[README.md §8](../../README.md#8-designing-a-test-for-a-case). Where stage 4's
numbers go: [`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).

**Best-scaffolded case in the folder.** `CommitLogSegmentManagerCDCTest`
already contains a capacity-sweep helper —
[`testWithCDCSpaceInMb(int size, Testable test)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java#L428-L440),
which sets `cdc_total_space`, runs a body, and restores the original — plus
tests for the write failure, segment flagging in both modes, steady disk usage
in non-blocking mode, and mode switching. Very little needs writing.

**A correction to the escape hatch, found while designing this.**
§10 and the index say `cdc_block_writes = false` "bypasses the check entirely".
That undersells it: in non-blocking mode the tracker **deletes the oldest CDC
hard links** to get back under the allowance
([`processNewSegment():345-355`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L345-L355)).
So `cdc_total_space` still bounds on-disk bytes in that mode — it just enforces
the bound by **discarding un-consumed CDC data** instead of rejecting writes.
That is a different failure mode, not an absence of one, and it makes the
non-blocking arm a real experiment rather than a control. **Note:** that line
`:345` is one of the open items listed in `HANDOFF.md` as still needing its own
stage-3 judgement; this note is design input, not that judgement.

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable.** `Config.cdc_total_space` is not `volatile` but `getCDCTotalSpace()` is read **live at every check** ([`:329`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L329) and [`:201`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L201)), so `DatabaseDescriptor.setCDCTotalSpaceInMiB(int)` takes effect without a restart at the unit tier. **There is no JMX setter for it**, so a cluster arm needs a restart per value. `cdc_block_writes` **is** hot-settable over JMX ([`CommitLogMBean.setCDCBlockWrites(boolean)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogMBean.java#L94)). Checked 2026-09-28. |
| **Constraint knob** | `cdc_total_space` in `cassandra.yaml` (MiB). **Prerequisite:** `cdc_enabled: true` ([`Config.java:410`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L410), default `false`) and a table created `WITH cdc = true`, or the check is never reached. **Mode knob:** `cdc_block_writes` ([`Config.java:413`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L413), default `true`), over JMX. Unit tier: `DatabaseDescriptor.setCDCTotalSpaceInMiB(int)` ([`:4375-4379`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4375-L4379), `@VisibleForTesting`). |
| **Capacity values to test** | `cdc_total_space` ∈ {`64MiB`, `128MiB`, `256MiB`, `512MiB`}, i.e. 2 / 4 / 8 / 16 segments at the default 32MiB `commitlog_segment_size`. **Do not leave it at the default**: when set to 0 with `cdc_enabled` true it is auto-derived to 1/8th of the `cdc_raw_directory` filesystem's total space, capped at 4096MiB ([`DatabaseDescriptor.java:684-694`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L684-L694)) — a machine-dependent figure that would make arms incomparable. Set it explicitly everywhere and record the resolved value from the startup log. Use values that are whole multiples of the segment size, since §8 notes the comparison works in whole-segment units. |
| **Usage-side observable** | `cdcSizeTracker.sizeInProgress` — an `AtomicLong` of bytes of CDC-hard-linked segment files currently retained. |
| **Instrument** | **No CDC metric exists** — `metrics/CommitLogMetrics.java` has nothing CDC-related (checked 2026-09-28). But this case has the best *external* instrument in the folder, because the resource is files on disk: **`du -sb` on `cdc_raw_directory`, and a file count**, which together are a near-exact reading of `sizeInProgress` (each retained link is one `commitlog_segment_size` file). Sample over time, not once at the end — segment deletion erases the evidence (README §8.3). Secondary: the `logger.debug` at [`:352-355`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L352-L355) prints released and remaining bytes in non-blocking mode, and the `CDCWriteException` message at [`:220`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L220) carries `sizeInProgress` — both print the operand itself. At the unit tier read `sizeInProgress` directly. |
| **Scope of the limit** | **Node-wide, one tracker per node.** Not per table or per keyspace: every CDC-enabled table's writes share `sizeInProgress`. `N = 1`, no multiplier — the simplest scope of any case here. But note the resource is **shared with the commit log**: CDC links are hard links to commit log segments, so `commitlog_segment_size` and commit log activity move the same files. |
| **Suggested level** | **Both, unit first — almost nothing to write.** `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java`: `testCDCWriteFailure()` ([`:80-108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java#L80-L108)) isolates the blocking-mode boundary; `testSegmentFlaggingOnCreation()` and `testSegmentFlaggingWithNonblockingOnCreation()` ([`:109-120`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java#L109-L120)) cover the `FORBIDDEN`/`PERMITTED` verdict in each mode; `testNonblockingShouldMaintainSteadyDiskUsage()` ([`:121-141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java#L121-L141)) is the reclaim behaviour noted above; `testSwitchingCDCWriteModes()` ([`:142-154`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java#L142-L154)) switches blocking → non-blocking → blocking. Wrap them in `testWithCDCSpaceInMb` at the four capacity values and assert `sizeInProgress` at each — that is the whole unit tier. Run: `ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDCTest`. Then the cluster tier for the `du` curve. |

### 9a. Workload — driving the usage operand

The operand grows when CDC segments are retained **un-consumed**, so the
workload's essential feature is the *absence* of a consumer.

- Single node, `cdc_enabled: true`, `cdc_raw_directory` on a known filesystem with ample free space (so the filesystem never becomes the binding limit instead of the config).
- One table created `WITH cdc = true`.
- **Run no CDC consumer at all.** This is the whole trick: in production an external process reads and deletes the hard links from `cdc_raw_directory`, which decrements `sizeInProgress`. With no consumer the backlog grows monotonically to the allowance, which is exactly the boundary under test, and it does so deterministically.
- Write with `cassandra-stress` or a CQL client until the segments roll. `createTableAndBulkWrite` in the existing test uses a payload of `commitlog_segment_size / 3`, which rolls segments quickly — a good model.

**Deterministic single-shot form:** set `cdc_total_space` to two segments
(64MiB at the default segment size), then write enough to fill three. The
boundary is crossed on a known segment with no race against a consumer or a
flush — which is why this case suits README §8.2 rule 2 better than most.

### 9b. Scenario A — just reach capacity

Write until `sizeInProgress` is one segment below the allowance, then stop.

Expect: `du -sb` on `cdc_raw_directory` ≈ `cdc_total_space − commitlog_segment_size`,
with a file count of `(allowance / segment_size) − 1`; all segments
`PERMITTED`; **no `CDCWriteException`**; writes succeeding normally. The plateau
should move with the knob across the four values. Per §8 the practical ceiling
is always within one segment size of the configured value and never below it —
so check that the plateau sits just *under* the config value, not exactly on it.

### 9c. Scenario B — try to exceed capacity

Keep writing. **Here the two modes genuinely differ**, and neither is a
no-op:

| Mode | Expected, from §6b and `:345-355` | Evidence |
|---|---|---|
| **`cdc_block_writes = true`** (default) | The segment is flagged `FORBIDDEN` and `throwIfForbidden()` **throws `CDCWriteException`** — a clean write rejection, unlike the block-and-wait of the memtable/hints/net cases. The mutation is never appended. | The client sees the write fail; the exception message at [`:220`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L220) carries `sizeInProgress`. `du` plateaus at the allowance and **stops**. |
| **`cdc_block_writes = false`** | Writes **succeed**, and the tracker instead **deletes the oldest CDC hard links** to get back under the allowance. On-disk size still plateaus, but un-consumed CDC data is **silently lost**. | The `logger.debug` at [`:352-355`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L352-L355) reports released and remaining bytes. `du` plateaus at roughly the same value as blocking mode, but the **file set churns** — so record file *names* over time, not just the total, or the two modes look identical. |

Recording the file-name churn is the single most important measurement in the
non-blocking arm; the totals alone cannot distinguish "bounded by rejection"
from "bounded by deletion".

### 9d. Expected dose-response

If the traced path is the binding limit:

- **`du` plateau is linear in `cdc_total_space`** in **both** modes, landing within one `commitlog_segment_size` below the configured value. This is a sharp prediction because the units are whole 32MiB segments.
- **Blocking mode:** time-to-first-`CDCWriteException` rises with the allowance at constant write rate; total CDC-tracked writes accepted before failure rises proportionally.
- **Non-blocking mode:** no write ever fails; instead the **rate of link deletion** rises as the allowance falls. Quantify it as deleted bytes per unit of written bytes — that ratio is the data-loss rate, and it is a number nobody has.
- **Cross-check on `commitlog_segment_size`:** halving it (16MiB) at fixed `cdc_total_space` should roughly halve the gap between the plateau and the config value, since the ceiling is quantised in segments. If the plateau does not move, the quantisation claim in §8 is wrong.
- **Non-CDC writes should be entirely unaffected** in both modes, at every value. §8 says the check only gates `mutation.trackedByCDC()`; a second table without `cdc = true` is the control that proves it.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| Blocking: `du` plateaus within one segment of the allowance and `CDCWriteException` fires; non-blocking: same plateau with link churn in the debug log | The check enforces as traced, in both modes. |
| `du` climbs past the allowance in either mode | The tracker is not seeing files it should, or `sizeInProgress` has drifted from reality — note `processNewSegment` counts new segments "aggressively" by estimate at [`:340-341`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L340-L341) and resyncs from disk elsewhere, so a drift is plausible. Target-3 material; §8's ceiling claim needs qualifying. |
| Non-blocking mode plateaus **without** any link deletion | Either no consumer-free backlog was built, or the reclaim branch at `:345` did not fire. Check the debug log before concluding — this is the branch that still needs its own judgement. |
| `du` flat across all four values | The traced path is not the binding limit. Check first that `cdc_enabled` is true, the table has `cdc = true`, and no consumer is draining the directory. |
| Non-CDC writes also fail | Something other than this check is rejecting writes — commit log disk failure policy, or the commit log's own space limit. Not this case. |

### 9f. What would refute this case

The case claims the `cdc_total_space` comparison sets a per-segment `CDCState`
that `throwIfForbidden()` acts on, bounding total retained un-consumed CDC
bytes. It is refuted if, with no consumer running and `cdc_block_writes = true`,
the size of `cdc_raw_directory` **grows past `cdc_total_space`** without any
`CDCWriteException`, or if the plateau does not move when the knob is swept.

**Two results that would not refute it but would change the case file:**
non-blocking mode bounding disk by deleting links rather than by doing nothing
(this §9 already predicts it, and §10's "bypasses the check entirely" wording
should be corrected when stage 4 confirms it); and a plateau that overshoots by
*more* than one segment size, which would qualify rather than overturn §8's
quantisation claim.

### 9g. Confounders and controls

- **A CDC consumer draining the directory** is the single confounder that would silently invalidate every arm, because it decrements the operand. Confirm nothing is reading `cdc_raw_directory` — no external tooling, no test harness leftover.
- **The auto-derived default.** `cdc_total_space: 0` resolves to 1/8th of the filesystem's total space, so an arm that forgets to set it explicitly gets a machine-specific value. Set it in every arm and read the resolved figure from the startup log.
- **`commitlog_segment_size`** sets the quantisation unit and therefore the plateau's offset from the config value. Hold it fixed except in the deliberate cross-check arm.
- **Filesystem free space on `cdc_raw_directory`** must comfortably exceed the largest `cdc_total_space` tested, or the filesystem binds first and the run measures the wrong limit.
- **Commit log activity from non-CDC tables** shares the underlying segments. Keep the node otherwise quiet, and use a non-CDC table only as the deliberate control.
- **Sample `du` over time.** The final size is not the peak, and in non-blocking mode deletion actively erases the evidence (README §8.3).
- **Mode switching mid-run** is supported (`testSwitchingCDCWriteModes` exercises it) but makes a curve uninterpretable. One mode per arm.
- **Baseline** at a fixed explicit `cdc_total_space` with a consumer running, so the backlog stays near zero; **idle control** with `cdc_enabled` true and no writes, for the directory's floor.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | `cdc_block_writes = false` makes `permitSegmentMaybe()` always permit CDC writes, bypassing the check (see Notes). |
| **Stage-4 feedback** | none yet |

---

## 11. Notes

- **Escape hatch found:** `cdc_block_writes = false` (default `true`) makes
  `permitSegmentMaybe()` always permit CDC writes regardless of
  `sizeInProgress`, bypassing this check entirely — same shape as the
  memtable cases' `markBlocking()`. Flagged for Target 3.
- **Pattern (b), two check sites:** the capacity check
  (`processNewSegment():335`, re-evaluated by `permitSegmentMaybe():200`)
  and the decision point (`throwIfForbidden():214`) are separate methods
  connected through the segment's `CDCState` field. Re-anchored on the
  capacity check on 2026-09-20 (the case was first drafted on the decision
  point). Both check sites are kept in one case file because they compute
  the same verdict for the same decision point (see §1).
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
