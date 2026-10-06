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
3. **Escape hatch (corrected 2026-10-01 from stage 4, [results file](../../../stage4-runtime-verification/long-path/results/cdc_total_space-processNewSegment-allowance.md) §4 and §8):** setting `cdc_block_writes` (config, live-mutable via `DatabaseDescriptor.setCDCBlockWrites()`/JMX) to `false` makes `processNewSegment()` always mark a new segment `PERMITTED` and `permitSegmentMaybe()` always permit a forbidden one, so `throwIfForbidden()` never fires and no CDC-tracked write is rejected. **It does not remove the bound.** `processNewSegment():345-354` then deletes the oldest CDC hard links (`deleteOldLinkedCDCCommitLogSegment()`, `:91-131`) until the counter is back under `cdc_total_space`, so the links in `cdc_raw` stay at `⌊limit / segmentSize⌋` or one more (measured at both tiers: 116 segments written at `cdc_total_space: 144MiB` left between 3 and 5 links), and the un-consumed CDC data is lost instead of the write being rejected. The first draft of this item said the backlog then grows past the limit; it does not. Flagged for Target 3 as a loss of data, not as an unbounded resource.

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
Non-CDC-tracked mutations are entirely unaffected — the
check only gates `mutation.trackedByCDC()` writes.

**Amended 2026-10-01 (stage 4, [results file](../../../stage4-runtime-verification/long-path/results/cdc_total_space-processNewSegment-allowance.md) §4 and §8), replacing this paragraph's earlier sentence that the ceiling is "always within one segment size of the configured value, never below it".** The verdict is made once per segment, when the segment is created: `processNewSegment():335-337` forbids it when `segmentSize + sizeInProgress > limit`. With no consumer the node therefore keeps `⌊limit / segmentSize⌋` hard links of `segmentSize` bytes each, **plus one when the counter is stale at that moment**: the directory walk that refreshes it is submitted inside `processNewSegment()` (`:357`) and often finishes before the new segment's link exists (`:246`), so the counter is one segment low. Measured with one fast writer: the counter was low at 45 % of segment creations in the unit tier and 23 % in the cluster tier, by at most one segment, and the node kept `⌊limit/segmentSize⌋ + 1` links at 3 of 5 and at 2 of 4 values whose limit is not a multiple of the segment size, never more. So the ceiling is `⌊limit/segmentSize⌋ × segmentSize` and, in a large share of runs, one segment more: **at most `limit + segmentSize`**, which can be above the limit (160 MiB held at a limit of 144 MiB). At an exact multiple of the segment size the few bytes of the `_cdc.idx` files, once a walk has summed them, tip the last segment over: the node kept `limit/segmentSize − 1` links (127 links at the derived default of 4096 MiB). In non-blocking mode the same bytes are bounded by deleting the oldest links (§6b item 3).


## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test sets `cdc_total_space`, writes CDC-tracked rows with nothing consuming
`cdc_raw`, and checks that the hard links in `cdc_raw` stop at the number of whole
segments the limit allows while further CDC writes are rejected (blocking mode)
or the oldest links are deleted (non-blocking mode). **Converted to the new layout
and audited 2026-10-01 (stage-4 step 0, before any run); the old plateau figures
were corrected from the source, see the results file §1.1. Run so far:** both tiers, 2026-10-01 (results file §4.2, §4.3, §8).

### 9a. Procedure and conclusions

**Testability:** config. `cdc_total_space` is read live at every check, but only the
unit tier can change it without a restart (`DatabaseDescriptor.setCDCTotalSpaceInMiB`);
at the cluster tier it is **restart-only** (no JMX setter). `cdc_block_writes` can be set
over JMX, but each arm sets it in `cassandra.yaml` at start instead. No patched build.

**Terms** (used in every subsection). *S* = `commitlog_segment_size` (32 MiB at the
default). *A* = `cdc_total_space`, in bytes. *k* = ⌊*A* / *S*⌋. A **link** is a
`CommitLog-*.log` file in `cdc_raw_directory`, a hard link to a commit-log segment;
each is *S* bytes long from the moment it is created. *L* = the number of links.
The **idle floor** is *L* on a node with no writes. A **rejection** is a
`CDCWriteException` thrown by the check. A **consumer** is a process that deletes
finished links; none runs, except in the release step and the consumer control.

**Claim under test:** with no consumer, `cdc_total_space` caps the commit-log segments
the node keeps in `cdc_raw` at *k* links, which is `k × S` bytes and never more than
*A*. Once *k* links exist, every CDC-tracked write is rejected with `CDCWriteException`
(an error to the client; it is not blocked and not dropped silently) until a consumer
frees space; writes to tables without `cdc = true` are not affected. With
`cdc_block_writes: false` nothing is rejected: the tracker deletes the oldest links to
stay under *A*, so un-consumed CDC data is lost instead of the write. (§8 says the
ceiling is "within one segment size of the configured value, never below it"; from the
source it is at or below *A* in blocking mode, and in non-blocking mode it can briefly
be one segment above. The prediction below is the precise form.)

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** with no CDC consumer, `cdc_total_space` caps the bytes of commit-log
  segments retained in `cdc_raw` at `k × S`; in blocking mode the rejection of CDC
  writes is what enforces it, in non-blocking mode the deletion of the oldest links.
- **Test:** vary *A* (unit tier 16, 48, 80, 128, 144, 272 MiB; cluster tier 144, 272,
  528 MiB and the default, which resolves to 4096 MiB on these nodes), plus a second
  knob (*S* = 16 MiB at *A* = 280 MiB) and a non-blocking arm. Write 1 MiB CDC rows
  until writes are rejected, then keep trying (ten more tries at the unit tier, 60 s at
  the cluster tier). Measure the real resource, the
  files in `cdc_raw` (count, bytes, names), 20 times a second, and the check's counter at
  every segment creation from a trace.
- **Logic:** (1) the limit is reached: a rejection occurs, or the run is invalid.
  (2) At the first rejection *L* = *k*, and it stays *k*, with the bytes flat, while
  writes keep being rejected: usage **stops at the limit**. (3) *L* follows ⌊*A*/*S*⌋
  across the values, the step between values is the difference in *k*, and changing *S*
  at fixed *A* moves the byte ceiling as the arithmetic says: usage **follows the
  constraint**. (4) The rejection is the disallow branch: the only producer of the
  `Rejecting mutation` message is the check, the creation trace shows a segment
  forbidden exactly when `S + counter > A`, deleting links releases the writer with no
  restart, and non-CDC writes are not rejected. (5) Non-blocking: no rejection, *L*
  never above *k* + 1, the oldest names disappear.
- **Refuted if:** *L* at the plateau exceeds *k* + 1; bytes keep rising while writes are
  rejected; the plateau is flat across *A*; or the counter is capped while the files are
  not (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) run the upstream `CommitLogSegmentManagerCDCTest` unchanged, as a
   baseline for the environment (its assertions are loose: the non-blocking test's bound
   is three times the limit, so it settles nothing about the cap). (b) Run a harness
   test, one JVM per value, that writes CDC rows until the first rejection and asserts
   *L*, the size of every link and the counter printed in the rejection message; tries
   ten more writes and asserts nothing changed and a non-CDC write still succeeds; then
   deletes the links and asserts the writer resumes. A non-blocking variant asserts no
   rejection, *L* ≤ *k* + 1 throughout, and that the oldest link is deleted.
2. **Cluster tier** — one node with `cdc_enabled: true`, restarted once per capacity
   value (9b), written with `cassandra-stress`.
3. **At each capacity value:** control run (idle) → **A**, write until the first
   rejection → **B**, keep trying for 60 s while a non-CDC table is written too →
   **release**, delete the finished links as a consumer would and write again.
   **Scenario C** is the non-blocking arm (`cdc_block_writes: false`), the setting that
   turns the rejection off. A **consumer control** runs a deleting loop throughout.
4. **Compare** with the prediction below and read the result in the table.

**Prediction** (derived from the source before any run; `processNewSegment`,
`permitSegmentMaybe`, `throwIfForbidden` and the segment manager):

*Blocking mode, A not a multiple of S* (*k* = 4, 8, 16 at 144, 272, 528 MiB; *k* = 17
at *A* = 280 MiB, *S* = 16 MiB):

- **Plateau.** When the first rejection happens, and for as long as writes keep being
  rejected, *L* = *k* or *k* + 1 and the links hold `L × S` bytes, so at most `A + S`.
  The idle floor is min(*k*, 2) links: the segment being written and the one prepared
  ahead, both made at start-up; at *k* = 1 the floor can therefore be 2 links, one above *k*.
  For *A* < *S* (*k* = 0) the first segment is forbidden, every CDC write is rejected
  from the first one, and `cdc_raw` stays empty.
- **A segment is forbidden when it is created exactly when `S + counter > A`.** The
  counter adds *S* for each permitted segment, plus the few bytes of `_cdc.idx` files once
  a directory walk has run. So *k* + 1 links exist exactly when the counter was stale (one
  segment low) when the (*k* + 1)-th segment was created. The directory walk that refreshes the
  counter is submitted inside `processNewSegment` and often finishes before the new segment's
  hard link exists, so this is expected at a large share of creations (a fifth to a half), not
  a rare race. It is not a deviation: the creation trace (counter against the links that existed)
  is how each extra link is attributed.
- **Step.** Between values the plateau moves by the difference in *k*: 4, 8, 16 links.
- **Second knob.** At *A* = 280 MiB and *S* = 16 MiB, *L* = 17 (272 MiB), against 8
  links (256 MiB) at *S* = 32 MiB: the byte ceiling moves by 16 MiB with *S* alone.
- **The counter** printed in the rejection message (`Total CDC bytes on disk is N`) is
  the file bytes plus the `_cdc.idx` files: `L × S ≤ N ≤ L × S + 64 × L`.
- **Release.** After a consumer deletes the finished links, CDC writes are accepted again
  within a few seconds with no restart (`permitSegmentMaybe` re-evaluates the forbidden
  segment on every write, once a directory walk has refreshed the counter).
- **Non-CDC writes** are accepted throughout.

*A an exact multiple of S* (128 MiB at the unit tier; the default, 4096 MiB = 128 × *S*,
at the cluster tier): *L* is *k* − 1 or *k*. The check forbids when `S + counter > A`, and
the `_cdc.idx` bytes in the counter tip the last segment over once a directory walk has run
since the previous link was made. Both outcomes are allowed; *k* − 1 is the likely one for
*k* > 2.

*Non-blocking mode* (scenario C): no rejection at all. After each segment is created the
oldest links are deleted until the counter is back under *A*, so *L* ≤ *k* + 1 at every
instant (*k* + 1 only between a creation and the next directory walk), the oldest names
disappear in ascending order, and the bytes written are far above the bytes retained.

*Consumer control* (blocking, *A* = 272 MiB, a loop deleting finished links five times a
second, the writer held to 100 rows a second): no rejection while at least 3 × *A* bytes are
written, and *L* ≤ *k* at every sample.

**Reading rule.** *L* is read from the 20 Hz listing of `cdc_raw`. The **plateau** is the
value held at the end of B (the median of its last 20 s); the **peak** is the maximum over the
run. The apparent bytes of the links must equal *L* × *S* exactly (every link is *S* bytes);
the allocated bytes are reported. The "*k* ± 1" statements above are the only tolerances;
there is no byte band. If a plateau is outside them, the creation trace and the step between
values decide, not an absolute size.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Blocking arms: a rejection occurs at every value; the plateau is *k* or *k* + 1 links (for *A* an exact multiple: *k* − 1 or *k*) and never above *k* + 1, each extra link attributed by the creation trace to a stale counter; the bytes stay flat through B; the creation trace shows a segment forbidden exactly when `S + counter > A`; the step between values follows ⌊*A*/*S*⌋ and the *S* = 16 arm lands at its own ⌊*A*/*S*⌋; deleting the links releases the writer; non-CDC writes succeed | **Confirmed** — the check enforces as traced; §8's ceiling is `⌊A/S⌋ × S`, plus one segment when the counter is stale: at most `A + S`. |
| A plateau or peak of *k* + 1 links at some value, and the trace shows a counter lower than the files on disk when the extra segment was created | **Confirmed, with a one-segment overshoot** — the counter was stale; this is the expected form of the first row, not a deviation. Record how often. |
| A plateau or peak of *k* + 1 links with no stale counter in the trace, or more than *k* + 1 links | **Refuted** — something other than the traced check admitted the segment. |
| Non-blocking arms: no rejection, *L* never above *k* + 1, the oldest names disappear, the trace shows the deletion (`bytesToFree`, `remaining`), bytes written far above bytes retained | **Bypass as recorded, bounded by deletion** — `cdc_block_writes: false` turns off the rejection, not the cap: the cap is kept by deleting un-consumed links. Target-3 material: correct §10's "bypassing the check entirely" and record the loss ratio. |
| Non-blocking arm: no rejection and *L* grows past *k* + 1 | **Refuted** for the non-blocking path — the deletion branch does not hold the cap. |
| Blocking: the plateau exceeds *k* + 1; or it is *k* + 1 and the trace does not show a counter lower than the files when the extra segment was created; or the bytes keep rising while writes are rejected | **Refuted** — the check does not cap usage, and no recorded mechanism accounts for the excess. |
| The counter (trace, rejection message) stays at or under *A*, but the files in `cdc_raw` exceed `L × S` or *A* by more than the `_cdc.idx` bytes plus one segment | **Refuted** — the counter does not track the resource; §8's ceiling claim is wrong. |
| The plateau is the same at every value of *A* | **Refuted** — not the binding limit. Re-read, do not re-run. |
| The plateau follows *A*, but no rejection occurs (blocking) | **Not confirmed** — something else derived from `cdc_total_space` may be binding. Re-read. |
| A rejection occurs while *L* is below *k* (for an exact multiple, below *k* − 1) | **Not confirmed** — the arithmetic is not the traced one (for example the segment prepared ahead is counted differently). Re-read the creation trace. |
| Non-CDC writes also fail during B | **Not confirmed** — something other than this check is rejecting writes (the commit log's failure policy, a full disk). Re-read. |
| After the links are deleted the writer does not resume (blocking) | **Not confirmed** — the verdict is not driven by the counter against the limit as traced. Re-read. |
| The consumer control is rejected although the loop keeps *L* below *k* | **Not confirmed** — the rejection is not driven by the backlog. Re-read. |
| No rejection within the timeout (blocking), or fewer than *k* + 8 segments created (non-blocking), or the sampler has a gap over 1 s | **Invalid run** — fix the setup (9b, 9c) and re-run. |

Two rules behind this table:

- **A confirmation needs both** the plateau moving with the knob **and** direct evidence that the
  disallow branch fired: the `Rejecting mutation` WARN (the only code that logs it is
  `throwIfForbidden`) and the creation trace's forbidden verdict. A curve alone can come from
  another mechanism derived from the same limit, and non-blocking mode is exactly such a case.
- **How an overshoot is attributed.** Past *A* only the stale counter (trace: counter lower than the
  files when the segment was created) or the non-blocking deletion can explain it; without one of
  those it is the **Refuted** row.

**Why the files, not only the counter:** the counter is an estimate, overwritten by a directory
walk, so it can lag the disk. Only the bytes in `cdc_raw` are the resource; the counter and the
creation trace say why they stop.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `cdc_total_space` in `cassandra.yaml` (whole MiB; `Config.java:418-419`). Unit tier: `DatabaseDescriptor.setCDCTotalSpaceInMiB(int)` (`:4375-4379`, `@VisibleForTesting`), set by the harness test from `-Dstage4.cdc.totalSpaceMiB` before the commit log starts. Restart-only at the cluster tier. **Mode knob:** `cdc_block_writes` (`Config.java:413`, default `true`), set in `cassandra.yaml` per arm. **Second knob:** `commitlog_segment_size` (`cassandra.yaml:660`), set per arm. **Prerequisites:** `cdc_enabled: true` (default `false`, `cassandra.yaml:413`), and a table created `WITH cdc = true`; without either the check is never reached. |
| **Confirm it took effect** | Cluster: `bin/cqlsh -e "SELECT name, value FROM system_views.settings WHERE name IN ('cdc_enabled','cdc_total_space','cdc_block_writes','commitlog_segment_size','cdc_raw_directory')"` once the node is up (the virtual table reads the live `Config`, so a derived default shows as its resolved value). Unit tier: the test asserts `DatabaseDescriptor.getCDCTotalSpace()`, `getCommitLogSegmentSize()` and `getCDCBlockWrites()` before it writes. |
| **Capacity values** | **Unit tier**, with *S* = 32 MiB: *A* = 16 (*k* = 0), 48 (1), 80 (2), 128 (4, an exact multiple), 144 (4), 272 (8) MiB; second knob *A* = 280 MiB with *S* = 16 MiB (*k* = 17); non-blocking at 80 and 144. **Cluster tier:** blocking at 144 (*k* = 4), 272 (8), 528 (16) MiB and the **default** (`cdc_total_space` left unset, so `DatabaseDescriptor.java:684-694` derives it as the smaller of 4096 MiB and one eighth of the `cdc_raw` filesystem, `:1147-1161`: **4096 MiB** on a 63 GB disk, *k* = 128, an exact multiple; read the resolved value back and take *k* from it); second knob *A* = 280 MiB, *S* = 16 MiB (*k* = 17); non-blocking at 144 and 528 MiB; consumer control at 272 MiB. Values other than the default are chosen **not** to be multiples of *S*, so the prediction is one integer. |
| **Scope** | Node-wide, one tracker per node: every CDC table shares the counter. *N* = 1, no multiplier. The resource is shared with the commit log (links are hard links of its segments), so `commitlog_segment_size` moves both. |
| **Level** | Both, unit first. Existing test: `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java` (baseline only, see 9a). The harness test is `CdcTotalSpaceCeilingTest` (new, package `org.apache.cassandra.db.commitlog` because it uses package-private `awaitManagementTasksCompletion()`). |

**Hold fixed** — every setting that must not change across the sweep:

| Setting | Value | Why |
|---|---|---|
| `cdc_enabled`, table option | `true`, `cdc = true` on the written table | the standard segment manager does no check; only CDC-tracked mutations are checked |
| `commitlog_segment_size` | 32 MiB (the node default), 16 MiB only in the second-knob arm. **At the unit tier the harness sets 32 MiB itself**: the unit yaml has 5 MiB (`test/conf/cassandra.yaml:10`) | *S* is the quantisation unit and the size of each link; the unit and cluster tiers must share *k* for each *A* |
| `cdc_raw_directory` | the default, `data/cdc_raw` in the clone, on the local disk; unit tier `build/test/cassandra/cdc_raw` | free space must exceed the largest *A* (4096 MiB) many times over; the shared NFS is never written |
| Consumer | none, except the release step and the consumer control | a consumer lowers the counter |
| `cdc_free_space_check_interval` | 250 ms (default) | the directory walk that refreshes the counter runs at most four times a second |
| `commitlog_sync`, period | `periodic`, 10000 ms (defaults) | `_cdc.idx` files are written at syncs |
| `max_mutation_size` | default (half of *S*) | rows are 1 MiB; the unit yaml's value is 2.5 MiB, still above that |
| Mode | one per run; never switched mid-run | a mode switch makes a curve uninterpretable |
| Row | 1 MiB payload, written with `cassandra-stress` (cluster) or `RowUpdateBuilder` (unit) | about 31 rows fill a segment, so the segment count is read from the files, not from the row count |
| JVM options, heap | defaults; the Byteman agent only | not under test; recorded |

**Controls:** the idle run at the start of every cluster run (the idle floor); non-CDC
writes during B; the release step; the default-capacity arm; the consumer control; the
upstream test as a baseline.

**Reset between runs:** `bin/nodetool stopdaemon`; check `pgrep -f org.apache.cassandra.service.CassandraDaemon`
prints nothing; remove `data/` and move `logs/` aside (this deletes the commit log and `cdc_raw`);
restore `conf/cassandra.yaml` from the tag (`git checkout conf/cassandra.yaml`) and apply the arm's
edits (9e). The unit test's `@After` deletes the commit log and `cdc_raw` itself.

### 9c. Workload

The usage side grows when finished segments are kept un-consumed, so the workload is
CDC-tracked writes and **no reader**. The trigger is deterministic: each segment holds about 31
rows, so *k* + 1 segments are needed to reach the limit whatever the write rate (9a).

**Arithmetic.** Reaching the limit takes (*k* + 2) × *S* of writes: 0.2 GB at 144 MiB, 0.6 GB at
528 MiB, about 4.2 GB for the default (130 segments). At 50 MB/s or more that is under 90 s;
the stop condition is the first rejection, with a timeout (9e). B then attempts
100 MiB/s for 60 s, which is rejected, not stored. Disk: `cdc_raw` ≤ 4 GiB, the commit log ≤ 8 GiB
(`commitlog_total_space`, default 8192 MiB), SSTables ≤ about 5 GiB (the default arm), against 55 GB free
on the 63 GB local disk (checked at preflight). Non-blocking B stores what it writes, about 3 GiB in 30 s.

```bash
# unit tier — one JVM per (A, S, mode); never reuse a JVM across values
ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CdcTotalSpaceCeilingTest \
  -Dtest.jvm.args="-Dstage4.cdc.totalSpaceMiB=<A> -Dstage4.cdc.segmentMiB=<S> -Dstage4.cdc.mode=<blocking|nonblocking> -Dstage4.unit.out=<out>/readings.txt -javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/cdc-verdict.btm -Dstage4.byteman.out=<out>/cdc-verdict.txt"

# cluster tier — fill (A): unthrottled, killed at the first rejection
tools/bin/cassandra-stress user profile=<harness>/cdc-rows.yaml "ops(insert=1)" n=1000000000 no-warmup \
  -rate threads=16 -errors retries=0 ignore -node 127.0.0.1
# B: the same with `-rate threads=16 throttle=100/s`, for 60 s, and at the same time the non-CDC control:
tools/bin/cassandra-stress user profile=<harness>/plain-rows.yaml "ops(insert=1)" n=1000000000 no-warmup \
  -rate threads=2 throttle=10/s -errors retries=0 ignore -node 127.0.0.1
```

`cdc-rows.yaml` writes 1 MiB rows to `stage4cdc.cdc_rows` (`WITH cdc = true`); `plain-rows.yaml` writes 64 KiB
rows to `stage4cdc.plain_rows` (`WITH cdc = false`). Stress is killed by the runner, so `n` is only a ceiling.
Each rejected write also logs an `ERROR` with a stack (`StorageProxy`), about 3 KB, so B is throttled to keep
`system.log` near 20 MB.

### 9d. Observables

| Observable | How to read it (command) | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — §4's `sizeInProgress` | (1) the creation trace: `cdc-verdict.btm` writes a `pre` line (counter, allowance, *S*, mode) and a `post` line (verdict, counter) for every segment created, to `-Dstage4.byteman.out`; (2) *N* in the WARN `Rejecting mutation to keyspace … Total CDC bytes on disk is N.` in `logs/system.log`; unit tier also reads the field by reflection | trace: every creation; message: at each rejection, at most one per 10 s for the same *N* | It is an estimate: *S* is added when a segment is created and the directory walk (`calculateSize`, `:407-419`) overwrites it, so it can lag the files by one segment; it includes `_cdc.idx` bytes only after a walk. A cross-check on the files, not the resource. |
| **Disallow evidence** — only the disallow path produces it | the WARN above (`grep -c '^WARN.*Rejecting mutation to keyspace' logs/system.log`; the text is built only at `CommitLogSegmentManagerCDC.java:217`, and it also heads the stack of the `ERROR … Failed to apply mutation locally` entry that each rejected write logs, `grep -c '^org.apache.cassandra.exceptions.CDCWriteException' logs/system.log`, which counts the rejected writes); the trace's `state=FORBIDDEN`; the JMX count `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Failures' -f Count`; the stress client's `Total errors`; unit tier: the `CDCWriteException` | A end, B end, release | Client errors alone are not evidence (a stress client can fail for other reasons); the WARN and the trace are. |
| **Bypass volume** — what the non-blocking deletion removes | the trace's `deleteOld` lines (`bytesToFree`, `remaining`); the removed names in the sampler's `.events` file; the DEBUG `Freed up … bytes after deleting the oldest CDC commit log segments` lines (default `logback.xml` sends `org.apache.cassandra` DEBUG to `logs/debug.log`); bytes written (stress) against bytes in `cdc_raw` | B | Totals cannot tell "bounded by rejection" from "bounded by deletion"; the names can. |
| **Real resource** — disk bytes in `cdc_raw` | `<harness>/cdc-sampler.py data/cdc_raw <out>` lists the directory every 50 ms: count and apparent bytes of `CommitLog-*.log`, allocated bytes (`st_blocks × 512`), the `_cdc.idx` files, and one line per file that appears or disappears | from node start to stop | The final size is not the peak, and deletion erases evidence (README §8.3), so sample over time and log names. Apparent bytes are what the counter tracks; allocated bytes are lower while a segment is sparse (the one prepared ahead has almost none). `du -s` counts blocks, not apparent bytes: do not use it for the ceiling. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c; one JVM per value.

1. Run the upstream `CommitLogSegmentManagerCDCTest` unchanged. Record pass or fail.
2. Copy the harness test into the clone and run it at each value (9b). The test:
   1. asserts the settings took effect (9b), starts the commit log afresh with the new *S* (`stopUnsafe(true)`, `start()`), creates a CDC table and a non-CDC table, waits for the segment prepared ahead (`awaitManagementTasksCompletion()`) and records the idle floor, which must be min(*k*, 2);
   2. writes 1 MiB CDC rows one at a time until a `CDCWriteException`, or fails the run as invalid after (*k* + 4) × 40 rows;
   3. at the first rejection records *L*, the size of every link, the counter (reflection and *N* from the message), the segment's state (must be `FORBIDDEN`) and the rows accepted, and checks *L* is *k* (*k* − 1 or *k* for an exact multiple) and every link is *S* bytes;
   4. tries ten more CDC rows, waits one second, and checks every one was rejected and *L* and the bytes are unchanged; writes one non-CDC row and checks it is accepted;
   5. deletes every file in `cdc_raw`, retries a CDC row every 100 ms for up to 10 s, and checks it is accepted (skipped at *k* = 0, where nothing can resume); records the time and *L*.
   Non-blocking variant: writes until at least *k* + 10 distinct links have been seen; checks no rejection, maximum *L* ≤ *k* + 1, the first link name gone, and the final *L* ≤ *k* + 1.
   A 5 ms background sampler runs from the start in both modes and logs every link that appears or disappears (`linkEvent`) and the link count at each change (`linkCount`). **A check that does not hold is recorded as `check MISMATCH` and the test goes on, so every later step still gives its readings; the test fails at the end if any check was a mismatch** (amended 2026-10-01, runbook defect 1: the first version stopped at the first mismatch). Only a setting that did not take effect, or no rejection at all, stops it at once.
   Record pass or fail and, per value, every printed line. Then run `<harness>/cdc-analyze.py --trace <out>/cdc-verdict.txt --events <out>/readings.txt --format unit`: it checks that every segment was forbidden exactly when `S + counter > A`, and sets the counter against the links that existed just before each creation (a counter lower than the files is the stale counter of 9a).

**Before the cluster tier.**

1. **Instrument checks**, none of them readings: Byteman's `TestScript` parses and type-checks `cdc-verdict.btm` against `build/classes/main`; the sampler passes a known-answer test (files created and removed in a temporary directory appear in its output with the right sizes and names); the consumer script deletes only `COMPLETED` links; the unit test runs with the trace attached and the trace shows one `pre` and one `post` line per segment.
2. **Preflight**, every run: no `CassandraDaemon` running, ports 7199, 9042, 9091 free, at least 20 GB free on the local disk, the clone at `cassandra-5.0.9`, the harness copy matching its `SHA256SUMS`.
3. **Start the node the same way for every run.** `cassandra.yaml` is the tag's file plus these edits (the run records `git diff -U0 conf/cassandra.yaml`):

   ```
   cdc_enabled: true
   cdc_total_space: <A>MiB          # appended; omitted in the default arm
   cdc_block_writes: false          # non-blocking arms only
   commitlog_segment_size: 16MiB    # second-knob arm only (replaces the existing 32MiB line)
   ```

   ```bash
   mkdir -p ~/stage4-logs/cdc/<label>
   JVM_EXTRA_OPTS="-Dstage4.byteman.out=$HOME/stage4-logs/cdc/<label>/cdc-verdict.txt -javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/cdc-verdict.btm,listener:true" \
     bin/cassandra -p cassandra.pid > ~/stage4-logs/cdc/<label>/stdout.txt 2>&1
   ```

   Wait until `bin/nodetool status` shows `UN` **and** `bin/nodetool statusbinary` prints `running`. Then `java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l` must list triggers on `CDCSizeTracker.processNewSegment`, `deleteOldLinkedCDCCommitLogSegment` and `CDCWriteException.<init>`; if it does not, stop: an empty trace would mean nothing. Read the settings back (9b) and start the sampler in the background.

**Cluster tier, for each blocking value:**

1. **Control run** — 15 s after the node is up, with no writes, record *L*, the bytes, `Failures` and the counter from the trace. Expect *L* = min(*k*, 2).
2. **Scenario A — reach the limit.** Create the keyspace and both tables with `cqlsh` while the node is idle (the DDL is in `cluster-run.sh`; the profiles' definitions are `IF NOT EXISTS`, so stress does not mind; amended 2026-10-01, runbook defect 4). Start the unthrottled CDC stress in the background and note the time. Poll `logs/system.log` every 0.5 s for `Rejecting mutation to keyspace`; at the first match, kill the stress and record the time, *L*, the bytes, `Failures` and the counter. Timeout 120 s (600 s for the default); no match is an invalid run.
3. **Settle, then scenario B — try to exceed the limit.** *Settle first* (amended 2026-10-01, runbook defects 4 and 6): once a second, for up to 240 s, run `bin/cqlsh --request-timeout=5 -e "INSERT INTO stage4cdc.plain_rows (id, payload) VALUES (<n>, 0xdeadbeef)"`, and go on to B when **15 in a row** were accepted in under 4 s (the streak restarts at any slow or failed probe); record the wait. After a large A the first periodic commit-log sync after the bulk write can stall every write that has to be logged for 10 to 15 s (the sync period is 10 s, hence 15 probes), and a rejected CDC write never reaches the log, so only a non-CDC write notices; one prompt probe is not enough, because the sync can begin just after it. The cap, and the rejection of CDC writes, are unchanged by the wait. Then, for 60 s, run the throttled CDC stress and the non-CDC control together. Every 5 s record *L*, the bytes and `Failures`. At the end kill both, record the non-CDC stress's `Total errors` (must be 0) and its row count.
4. **Release.** Run `<harness>/cdc-consumer.sh data/cdc_raw once`; note the time and the number of links it deleted. Then probe once every 200 ms, for up to 30 s, with a tiny CDC write (the check gates every CDC-tracked mutation whatever its size):

   ```bash
   bin/cqlsh -e "INSERT INTO stage4cdc.cdc_rows (id, payload) VALUES (<n>, 0xdeadbeef)"
   ```

   Record each attempt's time and exit status. The first accepted write is the release: record the time since the consumer ran (a rejected attempt triggers the directory walk that refreshes the counter, so a few attempts fail first) and *L* afterwards. No accepted write within 30 s is the "writer does not resume" row.
5. **Stop and read.** Kill the sampler; `bin/nodetool stopdaemon` (after 180 s, `kill -9`; the data is discarded); check no daemon is left; copy `logs/system.log` and `logs/debug.log` to the run's folder; then

   ```bash
   T=~/stage4-logs/cdc/<label>
   grep -c '^pre ' $T/cdc-verdict.txt                          # segments created
   grep -c 'state=FORBIDDEN' $T/cdc-verdict.txt                # segments created forbidden
   grep -c '^WARN.*Rejecting mutation to keyspace' $T/system.log          # rate-limited WARN entries
   grep -c '^org.apache.cassandra.exceptions.CDCWriteException' $T/system.log   # rejected writes logged
   <harness>/cdc-analyze.py --trace $T/cdc-verdict.txt --events $T/sampler.events --format sampler --csv $T/sampler.csv --phases $T/phases.csv
   ```

   The last command (the runner makes it) checks every creation against `S + counter > A`, sets the counter against the files that existed at each creation, and prints the links at each phase, the plateau and the peak.

**Scenario C — non-blocking** (`cdc_block_writes: false`): steps 1, 2 and 3 as above, except that A ends when the trace holds *k* + 8 `pre` lines (timeout as above; a rejection would be a finding), B runs 30 s, there is no release, and the sampler's `.events` file is the record of which links were deleted. Record `Total errors` for the CDC stress (expected 0).

**Consumer control** (blocking, 272 MiB): start `<harness>/cdc-consumer.sh data/cdc_raw loop 0.2` in the background, run the CDC stress throttled to 100 rows a second for 30 s (3 GiB, about 11 × *A*), and record the WARN count (expected 0), the peak *L* and `Total errors`. Kill the consumer afterwards.

**Second-knob arm** (blocking, 280 MiB, *S* = 16 MiB): steps 1 to 5 with the `commitlog_segment_size: 16MiB` edit.

Stop when each scenario's records are taken; a run where no rejection occurs is invalid
(9a), so fix the workload and repeat it.

**Record for stage 4:** the `cassandra.yaml` diff and JVM options in force, the exact commands, every
reading in 9d (the sampler's files, the trace, the WARN lines, `Failures`, the stress summaries), the
`Submit -l` output and the settings read back, per capacity value.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). §9 rewritten 2026-10-01; every citation in it checked against the pinned tag (results file §1.1). |
| **Escape hatch / Target-3 note** | `cdc_block_writes = false` turns off the **rejection**, not the **cap**: `processNewSegment():345-354` deletes the oldest un-consumed CDC links to stay under the allowance, so data is lost instead of writes failing (stage 4, 2026-10-01; see §6b item 3 and Notes). A **second unguarded path**, not exercised by stage 4: start-up replay hard-links replayed segments into `cdc_raw` and adds their size without consulting the allowance (`CommitLogReplayer.handleCDCReplayCompletion`, `:216-227`). |
| **Stage-4 feedback** | Design audit 2026-10-01 (stage-4 README, step 0): **Ready after amendments**; see [results §1.1](../../../stage4-runtime-verification/long-path/results/cdc_total_space-processNewSegment-allowance.md). The case was in the old §9 layout and was converted first (new 9a to 9e); the old plateau prediction was corrected from the source (rows B2 and B3 there). Amended in §9 before any run (all dated 2026-10-01): the prediction as integers with its tolerances, capacity values that are not multiples of *S*, the derived default added at the cluster tier, *S* = 32 MiB set by the unit harness (the unit yaml has 5 MiB), the creation trace, the non-CDC control, the release step and the consumer control, 14 conclusions rows. **Instrument checks, 2026-10-01 (not readings; results §1.2):** the harness test stopped at its first mismatch (runbook defect 1) and was changed to record and go on; the same check at *A* = 144 MiB showed the node keeping 5 links, one above *k* = 4, and the creation trace showed the check's counter one segment low (`S + counter <= A` while `S + files > A`): the frozen second conclusions row covers it, but 9a's wording that this is "rare, a few microseconds wide" is wrong about frequency (left as frozen, recommendation 1 in results §8). **Unit tier, run 1, 2026-10-01 (`pc80`): Confirmed, with a one-segment overshoot (blocking); bypass as recorded, bounded by deletion (non-blocking)** (results §4.2, §8). *L* at the first rejection was 0, 2, 2, 4, 5, 9, 17 for *A* = 16, 48, 80, 128, 144, 272 MiB (*S* = 32 MiB) and 280 MiB (*S* = 16 MiB), against ⌊*A*/*S*⌋ = 0, 1, 2, 4, 4, 8, 17; each extra link was made under a stale counter in the trace; ten more rejected writes changed nothing; the writer resumed 115 to 147 ms after the links were deleted; non-blocking: no rejection, at most *k* + 1 links, the oldest deleted in order. **Cluster tier, 2026-10-01 (`pc80`, one node): the same** (results §4.3, §8). Plateaus 5, 9, 16, 127, 17 for *A* = 144, 272, 528 MiB, the default (resolved 4096 MiB, an exact multiple: *k* − 1) and 280 MiB with *S* = 16 MiB; 6,015 of 6,015 CDC writes rejected in each 60 s of B while the non-CDC control wrote 602 rows with no error; the same plateaus in a second pass; non-blocking: 116 and 124 segments written, 3 to 5 and 16 to 17 links kept; the consumer control was never rejected. **Amended after the runs, documentation only (§9a and §9b byte-identical to the freeze):** 9c to 9e for six runbook defects (results §3) and the "Run so far" sentence. **Amended as feedback:** §6b item 3, §8, §11 and the Target-3 field above. |

---

## 11. Notes

- **Escape hatch found (corrected 2026-10-01 from stage 4):** `cdc_block_writes = false`
  (default `true`) turns off the rejection, **not the bound**: every new segment is
  `PERMITTED`, no CDC-tracked write is rejected, and
  `processNewSegment():345-354` deletes the oldest CDC hard links until the counter is
  back under `cdc_total_space`, so un-consumed CDC data is lost instead of writes
  failing (measured at both tiers; §6b item 3). The first draft here said the check is
  bypassed entirely and the backlog grows past the limit; neither holds. Flagged for
  Target 3 as data loss. The deletion site, `:345`, still needs its own stage-3
  judgement as a third check site (`HANDOFF.md`).
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
