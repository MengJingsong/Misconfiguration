# DataDirectory_getAvailableSpace — compaction output SSTable

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | DATADIRECTORY_GETAVAILABLESPACE-GETWRITEDIRECTORY-AVAILABLESPACE |
| **Constraint** | `DataDirectory_getAvailableSpace` — a **runtime-queried accessor** (README §6.1): the target data directory's free space, read fresh at call time. It is not a single declared limit variable; it is derived from the device's usable bytes minus the configurable floor `min_free_space_per_drive` (see §4). |
| **Enforcement pattern** | **(c)** — a guard clause that throws before the allocation, which is not itself inside a branch. **See §5: the guard does *not* dominate the allocation** — the default configuration reaches the allocation without passing it. |
| **Capacity check** | [`CompactionAwareWriter.getWriteDirectory():282`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L282) — `availableSpace < estimatedWriteSize`. Second check site feeding the same method's fallback path: [`Directories.getWriteableLocation():453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L453) — `candidate.availableSpace < writeSize`, per candidate directory. |
| **Decision point** | [`CompactionAwareWriter.getWriteDirectory():283-286`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L283-L286) — `throw new RuntimeException(...)`. Fallback path's decision point: [`Directories.getWriteableLocation():463-468`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L463-L468) — `throw new FSDiskFullWriteError(...)`. |
| **Allocation site** | [`CompactionAwareWriter.sstableWriter():235`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L235) — `.build(txn, cfs)` creates the `SSTableWriter`, reached via [`switchCompactionWriter():223`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L223). |
| **Related cases** | none — first disk-scoped case and first pattern-(c) case in this folder. |

```java
// CompactionAwareWriter.getWriteDirectory():278-295 — the guard and its fallback
Directories.DataDirectory d = getDirectories().getDataDirectoryForFile(descriptor);
if (d != null)
{
    long availableSpace = d.getAvailableSpace();
    if (availableSpace < estimatedWriteSize)                       // <-- capacity check, :282
        throw new RuntimeException(String.format("Not enough space to write %s to %s (%s available)",
                                                 FBUtilities.prettyPrintMemory(estimatedWriteSize),
                                                 d.location,
                                                 FBUtilities.prettyPrintMemory(availableSpace)));
    logger.trace("putting compaction results in {}", descriptor.directory);
    return d;
}
d = getDirectories().getWriteableLocation(estimatedWriteSize);     // <-- fallback, second check inside
if (d == null)
    throw new RuntimeException(String.format("Not enough disk space to store %s",
                                             FBUtilities.prettyPrintMemory(estimatedWriteSize)));
return d;
```

```java
// CompactionAwareWriter.maybeSwitchLocation():179-204 — the caller. Note the two paths:
// only the diskBoundaries == null path consults getWriteDirectory() at all.
protected boolean maybeSwitchLocation(DecoratedKey key)
{
    if (diskBoundaries == null)
    {
        if (locationIndex < 0)
        {
            Directories.DataDirectory defaultLocation = getWriteDirectory(nonExpiredSSTables, getExpectedWriteSize());
            switchCompactionWriter(defaultLocation, key);          // guarded allocation
            locationIndex = 0;
            return true;
        }
        return false;
    }
    // ... boundary-based selection ...
    Directories.DataDirectory newLocation = locations.get(locationIndex);
    if (prevIdx >= 0)
        logger.debug("Switching write location from {} to {}", locations.get(prevIdx), newLocation);
    switchCompactionWriter(newLocation, key);                      // UNGUARDED allocation — no space check
    return true;
}
```

## 2. Context

When Cassandra compacts data, it merges several existing on-disk data files
into new ones, which means it must first choose a directory on disk to write
the output into. This check is the sanity gate on that choice: before the
compaction starts writing, it asks the chosen directory how much free space
it currently has and refuses to begin if that is less than the compaction's
own estimate of how much it is about to write. The problem it solves is that
a compaction which runs out of space halfway through is far more damaging
than one that never starts — the node has already spent the I/O, and a full
data disk can take the node out of service entirely. Failing fast, before any
output file exists, keeps the failure cheap and recoverable.

The check also reserves a configurable safety margin: "free space" here means
the device's free bytes *minus* a reserved floor, so a compaction is refused
while the disk still has some genuinely unused room, rather than at the point
of true exhaustion.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | storage engine — compaction output writers (`db/compaction/writers`, with the space accounting in `db/Directories`) |
| **One-line role** | Compaction merges and rewrites SSTables in the background to reclaim space and bound read amplification; the `CompactionAwareWriter` family decides which data directory each output SSTable is written to and manages writer switching as the output grows. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes** — it compares the bytes a pending compaction is estimated to write against the bytes currently available on the target device, and refuses the write when usage would exceed capacity. |
| **Usage-side operand** | `estimatedWriteSize` — the caller's estimate of the compaction output's total size, from [`getExpectedWriteSize():303-306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L303-L306) → `cfs.getExpectedCompactedFileSize(nonExpiredSSTables, txn.opType())`. |
| **Limit-side operand** | `availableSpace` — the value returned by [`DataDirectory.getAvailableSpace():781-785`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L781-L785). |
| **Limit type** | **Runtime-queried (accessor method)**, partly config-derived: physical free bytes, reduced by the configuration entry `min_free_space_per_drive` and floored at 0. |

**Limit initialization path.** Unlike a config-derived limit such as
`memtable_heap_space`, this one has no single declaration — it is computed
per call from two sources:

1. [`PathUtils.tryGetSpace(location.toPath(), FileStore::getUsableSpace)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L783) — the **dominant term**: the filesystem's usable bytes for the directory, queried live from the OS. Not declared anywhere in Cassandra; it is a property of the deployed device.
2. [`Config.min_free_space_per_drive:339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L339) — declared, default `50MiB` (formerly `min_free_space_per_drive_in_mb`). This is the **tunable** term.
3. [`DatabaseDescriptor.getMinFreeSpacePerDriveInBytes():2567-2570`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2567-L2570) — read as bytes.
4. [`DataDirectory.getAvailableSpace():783-784`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L783-L784) — combined as `usableSpace − minFreeSpace`, clamped to `>= 0`, and returned to the comparison at `:282`.

**Naming note (Target 1).** README §6.1 says a runtime-queried limit with no
declared variable is named after its accessor, and that a limit derived from
several sources is named after the primary one. These pull in different
directions here: the accessor is `getAvailableSpace`, the dominant term is
the device (undeclared), and the only *tunable* term is
`min_free_space_per_drive`. The accessor name is used, since the device's
capacity — not the 50MiB margin — is what actually bounds the write; the
config entry is recorded here as the operator-facing knob on the same path.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`CompactionAwareWriter.getWriteDirectory():283-286`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L283-L286) |
| **Verdict** | Pattern (c): the guard is the comparison at `:282`; when it holds it throws `RuntimeException`, otherwise control falls through to `return d` at `:288` and the caller allocates. There is no flag or enum — the "verdict" is simply whether the method returns or throws. |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `availableSpace >= estimatedWriteSize` | Falls through, returns the `DataDirectory`; the caller proceeds to create the `SSTableWriter` and begins writing. |
| **Disallow** | `availableSpace < estimatedWriteSize` | Throws `RuntimeException` before any output file is created. Clean reject — no partial writer, no deferral, no retry at this level. |

```java
// allow: fall through
logger.trace("putting compaction results in {}", descriptor.directory);
return d;
```

```java
// disallow: clean throw, no object created
throw new RuntimeException(String.format("Not enough space to write %s to %s (%s available)",
                                         FBUtilities.prettyPrintMemory(estimatedWriteSize),
                                         d.location,
                                         FBUtilities.prettyPrintMemory(availableSpace)));
```

### The guard does **not** dominate the allocation

Pattern (c) requires showing that every path to the allocation passes the
guard, and recording any path that does not. **Here a bypassing path exists,
and it is the default one.**

`getWriteDirectory()` has exactly one caller,
[`maybeSwitchLocation():179-204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L179-L204),
which branches on whether the table has **disk boundaries**:

- **`diskBoundaries == null`** → calls `getWriteDirectory()` at [`:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L185), so the guard runs. **Guarded.**
- **`diskBoundaries != null`** → selects `locations.get(locationIndex)` by key range and calls `switchCompactionWriter(newLocation, key)` at [`:202`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L202) directly. `getWriteDirectory()` is never called and **no disk-space check of any kind runs.** **Unguarded.**

`diskBoundaries` is `db.positions` from
[`cfs.getDiskBoundaries()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L90-L93),
and per
[`DiskBoundaryManager:46-47,117-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/DiskBoundaryManager.java#L117-L121)
`positions` is null only when the partitioner has no splitter (e.g.
`ByteOrderedPartitioner`, `LocalPartitioner`) or when the node's local ranges
are null/empty. **Under the default `Murmur3Partitioner` on a node that owns
ranges, `positions` is non-null** — so the ordinary production path is the
*unguarded* one, and this check does not run at all.

The case still satisfies Rule 3: where the guard *is* reached, its two
outcomes differ unambiguously on object creation. But its coverage is far
narrower than the method reads at first glance, and that gap — a disk-space
guard that the default configuration skips — is recorded in §10 as a
Target-3-relevant observation rather than pursued here.

## 6. Code path

### 6a. Allow path → object creation

1. [`maybeSwitchWriter():166-173`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L166-L173) — called before the first `realAppend`.
2. [`maybeSwitchLocation():181-190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L181-L190) — `diskBoundaries == null` and `locationIndex < 0`, so it calls `getWriteDirectory(nonExpiredSSTables, getExpectedWriteSize())`.
3. [`getWriteDirectory():278-288`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L278-L288) — guard at `:282` not taken; returns the `DataDirectory`.
4. [`switchCompactionWriter():220-224`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L220-L224) — sets `currentDirectory`, calls `sstableWriter.switchWriter(sstableWriter(directory, nextKey))`.
5. [`sstableWriter():226-236`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L226-L236) — builds a `Descriptor` for a new file in that directory and **creates the object**: `.build(txn, cfs)` at [`:235`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L235).
6. [`SSTableRewriter.switchWriter():241-247`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableRewriter.java#L241-L247) — registers the new writer; subsequent `realAppend` calls stream rows into it, producing on-disk bytes.

### 6b. Disallow path effect

1. [`getWriteDirectory():283-286`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L283-L286) — throws `RuntimeException` carrying the requested and available sizes. No `Descriptor`, no `SSTableWriter`, no file: the throw precedes every allocation step in 6a.
2. The exception propagates out of `maybeSwitchLocation()` → `maybeSwitchWriter()` and aborts the compaction task. The `LifecycleTransaction` unwinds, so the input SSTables remain in place and untouched.
3. **No retry, no deferral, no alternate directory** on this path — unlike the fallback path below, this branch does not attempt another location. A clean, permanent reject for this compaction attempt; the strategy may of course reschedule a compaction later.

**Fallback path (second check site).** When `getDataDirectoryForFile(descriptor)`
returns `null` — the sstables span directories, so no single directory was
pinned — the method instead calls
[`getWriteableLocation(estimatedWriteSize):436`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L436).
That method applies the *same* comparison per candidate directory at
[`:453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L453)
(`candidate.availableSpace < writeSize`, with `availableSpace` from the same
`getAvailableSpace()` accessor), excluding any directory that is too small.
If every directory is excluded it throws
[`FSDiskFullWriteError`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L466)
(or `FSNoDiskAvailableForWriteError` when the exclusions were for
disallow-listing rather than size). This is the same underlying constraint
reached a different way — it is treated as a second check site of this case,
not a separate case, per README §6.1's "one case, several check sites". Note
it never returns `null`, so the `if (d == null)` throw at
[`:291-293`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L291-L293)
is effectively dead code in 5.0.9.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `SSTableWriter` (via `newWriterBuilder(descriptor)...build(txn, cfs)`), plus the output SSTable's component files it opens in the chosen directory. |
| **Resource consumed** | **On-disk bytes** — the compaction output SSTable (Data, Index, Summary, Filter, Statistics, etc. components). Secondarily some heap for the writer's buffers, but the bytes this check bounds are on disk. |
| **Rough sizing** | Not fixed per object: the gated quantity is `estimatedWriteSize` = `cfs.getExpectedCompactedFileSize(nonExpiredSSTables, txn.opType())`, i.e. the projected total size of the merged output, which scales with the input SSTables being compacted. |
| **Lifetime / release** | The output SSTable persists until a later compaction supersedes it or it is dropped; the input SSTables are released when the `LifecycleTransaction` commits, which is what actually reclaims the space. Note the transient peak: both inputs and outputs are on disk simultaneously until the transaction commits. |

## 8. Maximum disk bound

This limit is not a configured ceiling that caps total bytes; it is the
device's live remaining capacity, so its effect on the maximum is
per-operation rather than cumulative. Raising or lowering it changes **which
compactions are permitted to start**, and thereby the point at which the
node stops adding compaction output to that drive:

- **The dominant term, physical free space,** falls as data accumulates. As it
  approaches the size of a pending compaction's output, that compaction is
  refused — so the check enforces "never begin a write that the drive cannot
  hold," bounding on-disk bytes at the drive's capacity rather than at any
  Cassandra-configured number.
- **The tunable term, `min_free_space_per_drive` (default 50MiB),** shifts that
  cut-off by its own value: raising it makes `getAvailableSpace()` return less,
  so compactions are refused sooner and the effective ceiling on how full the
  drive gets is lowered by exactly that many bytes. It is a reserve carved out
  of the device, not a cap on Cassandra's data.
- **Mechanism:** refusal is per compaction attempt and prevents the output
  SSTable from being created at all, so the bytes are never written. Because
  the comparison uses an *estimate* (`getExpectedCompactedFileSize`), the bound
  is approximate in both directions — an under-estimate can admit a compaction
  that still fills the drive mid-write.

**Caveat carried from §5:** this bound only holds on the path where the guard
actually runs. On the default `diskBoundaries != null` path no space check is
performed, so compaction output is written to the selected directory
regardless of its free space, and this ceiling does not apply.


## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** Method and pitfalls:
[README.md §8](../../../README.md#8-designing-a-test-for-a-case). Where stage 4's
numbers go: [`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).

**This case's design is dominated by §5: the guard does not run by default.**
On the default `diskBoundaries != null` path — `Murmur3Partitioner`, node
owning ranges — `getWriteDirectory()` is never called and no disk-space check
happens at all. So the experiment has **two distinct jobs**, and the second is
the more valuable:

1. **Confirm the non-domination**, by running the default configuration and
   showing the guard never fires however little space is available. This is a
   Target-3 result and the strongest default-mode gap recorded in this folder.
2. **Measure the guard where it does run**, by forcing `diskBoundaries == null`
   and sweeping the one tunable term on the limit path.

A run that only does (2) has measured a code path the default configuration
never takes, and would overstate the constraint badly. Do both, and report
them as one result.

**How to force the guarded path.** `DiskBoundaryManager.getDiskBoundaries()`
short-circuits at [`:46-47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/DiskBoundaryManager.java#L46-L47)
when the partitioner has no splitter, returning boundaries with null
`positions`. `IPartitioner.splitter()` defaults to `Optional.empty()`
([`IPartitioner.java:148-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/dht/IPartitioner.java#L148-L151))
and **`ByteOrderedPartitioner` and `LocalPartitioner` do not override it**,
while `Murmur3Partitioner` ([`:435`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/dht/Murmur3Partitioner.java#L435))
and `RandomPartitioner` do. Verified against the pinned clone 2026-09-28. So
`partitioner: ByteOrderedPartitioner` in `cassandra.yaml` is the switch — note
it is fixed at cluster initialization and cannot be changed on a cluster that
already holds data, so the two arms need **separate clusters**, not a restart.
The other route to null `positions` — empty local ranges
([`:116-117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/DiskBoundaryManager.java#L116-L117)) —
is not usable, because a node owning no ranges receives no writes to compact.

| Field | Content |
|-------|---------|
| **Testability** | **Partly config-testable, partly not.** The dominant term — the device's usable bytes — is **not settable at all**; it is queried live from the OS ([`Directories.java:783`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L783)), so it is varied by **provisioning a small filesystem**, not by configuration. The tunable term `min_free_space_per_drive` is config-only (not `volatile`, no JMX setter → restart per value). The path selector `partitioner` is fixed at cluster init. Checked 2026-09-28. |
| **Constraint knob** | Two, of different kinds. (1) **`min_free_space_per_drive`** in `cassandra.yaml` (default `50MiB`, [`Config.java:339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L339)); at the unit tier `DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(long)` ([`:2573-2577`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2573-L2577), `@VisibleForTesting`). (2) **the device's free space**, varied by putting the data directory on a small dedicated filesystem — a loopback-mounted image or a small LVM volume — and by pre-filling it with ballast. The second is the honest way to move the real limit, and it is what makes this case awkward on shared CloudLab storage. |
| **Capacity values to test** | Sweep the device: a data-directory filesystem of **1 / 2 / 4 / 8 GiB**, with a fixed compaction input size chosen so the guard's boundary falls inside that range. Cross-sweep `min_free_space_per_drive` ∈ {`50MiB` (default), `512MiB`, `2GiB`} at a fixed device size — since `availableSpace = usable − minFree`, raising the floor should shift the refusal point by exactly that many bytes, which is a sharper and much cheaper test than re-provisioning filesystems. |
| **Usage-side observable** | `estimatedWriteSize` — `cfs.getExpectedCompactedFileSize(nonExpiredSSTables, txn.opType())`. For an ordinary compaction that is the **sum of the input SSTables' bytes**, so it is directly measurable as the on-disk size of the inputs. |
| **Instrument** | **Neither operand is exposed as a metric**, and unlike the sibling admission case there is **no log line at the comparison** — `getWriteDirectory()` logs only a `trace` on the success path ([`:287`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L287)). So the instruments are: (1) the **`RuntimeException` message itself**, which carries both operands — "Not enough space to write X to Y (Z available)" ([`:283-286`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L283-L286)); (2) `df` on the data directory's filesystem for the limit side, and `du -sb` on the input SSTables for the usage side, both recorded before each compaction; (3) `nodetool compactionstats` and the compaction log for whether the task ran at all. |
| **Scope of the limit** | **Per compaction attempt, per chosen directory.** Not node-wide and not cumulative: it asks only whether *this* compaction's output fits in *one* directory's free space, with no account taken of other compactions in flight — which is precisely what the sibling admission case adds. `N` = concurrent compactions, and this check does nothing to bound their sum. **Set `concurrent_compactors: 1`** so the arms are interpretable. |
| **Suggested level** | **Unit tier strongly preferred for the guard itself; cluster tier for the non-domination.** `test/unit/org/apache/cassandra/db/compaction/writers/CompactionAwareWriterTest.java` ([`:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/compaction/writers/CompactionAwareWriterTest.java#L58), a `CQLTester`) already constructs each `CompactionAwareWriter` subtype and drives compactions through them — the natural place to add a test that stubs `DataDirectory.getAvailableSpace()` low and asserts the `RuntimeException`, and a second asserting that on the boundary-based path **no exception is thrown however low the space**. That second test is the non-domination finding expressed as an assertion, and it is worth more than any cluster measurement. `CompactionsBytemanTest` shows the Byteman idiom for forcing a space check's outcome. Run: `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.CompactionAwareWriterTest`. |

### 9a. Workload — driving the usage operand

The operand is one compaction's estimated output, so the workload is: build
SSTables of a known total size, constrain the device, and trigger a compaction.

- Single node, **one data directory on a small dedicated filesystem** (loopback image or LVM volume), `concurrent_compactors: 1`.
- **Arm A (default path):** `partitioner: Murmur3Partitioner`, ordinary cluster. **Arm B (guarded path):** a separate cluster initialized with `partitioner: ByteOrderedPartitioner`.
- One table, `SizeTieredCompactionStrategy` with `'enabled': 'false'` so SSTables accumulate under the test's control.
- Write and `nodetool flush` to produce a known number of SSTables of known total size; record `du -sb` on the table directory.
- Add **ballast** — a plain file of known size on the same filesystem — to bring free space to the intended value. This is the cheap way to sweep the limit without re-provisioning: one filesystem, several ballast sizes.
- Trigger with `nodetool compact <ks> <table>`.

**Deterministic single-shot form:** size the ballast so that
`usable − min_free_space_per_drive` sits just below the total input size, then
issue one `nodetool compact`. The guard's boundary is crossed on the first
evaluation, with no dependence on write throughput.

### 9b. Scenario A — just reach capacity

Ballast set so free space is slightly **above** the input total, in both arms.

Expect in both: the compaction runs, output written, no exception. Peak disk
usage ≈ inputs + output while the transaction is open, falling back when it
commits. This is the control, and it should be indistinguishable between the
two arms — the arms diverge only when space runs short.

### 9c. Scenario B — try to exceed capacity

Ballast set so free space is **below** the input total. **The two arms should
now behave completely differently**, which is the experiment:

| Arm | Expected, from §5/§6b | Evidence |
|---|---|---|
| **B (`ByteOrderedPartitioner`, guarded)** | `getWriteDirectory()` throws `RuntimeException` **before any output file exists**. Clean reject: no `Descriptor`, no `SSTableWriter`, no partial file, no retry and no alternate directory on this path. Input SSTables untouched. | The exception message, carrying both operands. No new files in the table directory. `du` unchanged. |
| **A (`Murmur3Partitioner`, default)** | **No space check runs at all.** The compaction proceeds, `switchCompactionWriter()` is called directly, and the writer begins producing output on a filesystem that cannot hold it — expect the compaction to fail *later*, mid-write, with a filesystem-level error, having already consumed I/O and left a partial output file for the transaction to clean up. | Absence of the `getWriteDirectory` exception; presence of a mid-write failure with a different signature. `du` rising before the failure. |

**Arm A's result is the headline.** Capture the failure mode precisely — what
exception, at what point, how much was written first, what state the data
directory is left in. §5 predicts the gap; nobody has observed what it costs.

### 9d. Expected dose-response

- **Arm B:** the refusal boundary should sit at `usable − min_free_space_per_drive` exactly. Sweeping ballast, the largest input total that still compacts should track free space linearly with slope 1; sweeping `min_free_space_per_drive` at fixed ballast should shift that boundary by exactly the change in the floor. The `min_free_space_per_drive` cross-sweep is the sharper of the two and much cheaper to run.
- **Arm A:** **flat.** No boundary at any free-space value — compactions are always attempted, and fail only when the filesystem actually fills. A flat curve here is the **expected and correct** result, not a null finding, and it is what §5 claims.
- **The contrast between the two curves is the deliverable.** Plot them together: one with a knee at the predicted point, one with none.
- **The estimate is conservative** (§7/§11): `getExpectedCompactedFileSize` returns the sum of the *inputs*, while compaction normally shrinks data — so in Arm B expect refusals at input totals that would in fact have fitted. Quantify that over-refusal margin if the data is compressible.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| Arm B refuses at `usable − minFree`, cleanly, before any file is created; Arm A does not refuse at all | **Both halves of the case confirmed**, including the non-domination. This is the expected result. |
| Arm A **also** refuses, at the same boundary | §5 is wrong — some path does consult the guard under `Murmur3Partitioner`, or another disk check intervenes. Check whether the refusal came from `getWriteDirectory` or from the sibling admission case's `hasDiskSpaceForCompactionsAndStreams`, which **does** run by default and would produce a different message. A genuine correction to §5 if it really is this guard. |
| Arm B does not refuse at any ballast level | Either the boundary path was not actually taken (confirm `ByteOrderedPartitioner` is in effect and `positions` is null), or the fallback path via `getWriteableLocation()` found another directory — with a single data directory it cannot. Check the partitioner first. |
| Arm B refuses at a boundary that does not move with `min_free_space_per_drive` | §4's limit arithmetic is misread. That would refute part of the case. |

### 9f. What would refute this case

The case claims the comparison at `getWriteDirectory():282` refuses to create
the compaction output `SSTableWriter` when the target directory's free space
(device usable bytes minus `min_free_space_per_drive`) is below the
compaction's estimated output. It is refuted if, **on the guarded path**, a
compaction whose estimated output exceeds that figure proceeds to create a
writer — i.e. no `RuntimeException` — or if the refusal boundary does not shift
with `min_free_space_per_drive`.

**§5's non-domination claim is refuted separately, and in the opposite
direction:** if Arm A (default `Murmur3Partitioner`) *does* refuse at this
guard, then the guard does dominate after all and §5, §8's caveat and the
Target-3 note in §10 all need rewriting. Of the two, that is the more
consequential result, because the non-domination is what this case is chiefly
known for in the index.

### 9g. Confounders and controls

- **The sibling admission check runs on both arms and will confuse the result.** [`max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction`](max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md) gates the same compaction earlier, by default, and its refusal message and shrink-ladder warnings are different from this guard's. **Disable it for these arms** via JMX `compactionDiskSpaceCheck(false)` on the table (it applies to `OperationType.COMPACTION`), or the sibling will refuse the compaction before this guard is ever reached — in which case Arm B measures the sibling, not this case.
- **The partitioner is fixed at cluster init.** Arms A and B are separate clusters; do not attempt to switch one.
- **Multiple data directories** activate the `getWriteableLocation()` fallback and its second check site, which changes the disallow behaviour from "throw" to "try another directory". Use exactly one data directory.
- **`concurrent_compactors`** must be 1, or another compaction's output moves free space under the test.
- **Autocompaction** must be off, and `nodetool compactionstats` checked before each trigger.
- **Free space drifts** as data is written and compacted. Record `df` immediately before each trigger, and reset ballast between runs.
- **The estimate is the input sum, not the output size** — an arm using highly compressible data will see refusals that a byte-accurate check would not have made. Use incompressible payloads unless measuring that margin deliberately.
- **Baseline** with ample free space on both arms; **idle control** with the node up and no compaction, to confirm `df` is stable.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source. (Stage 1/2 had surfaced this line as a row, but the case was made from the source, not the row.) |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | **Yes — significant.** The guard is bypassed entirely on the `diskBoundaries != null` path (§5), which is the **default** configuration (`Murmur3Partitioner`, node owning ranges): compaction output is then written to a boundary-selected directory with no free-space check at all. This is a stronger default-mode gap than the memtable cases' `markBlocking()` escape hatch or the native-transport `throw_on_overload=false` gap, because the check is not overridden — it is never executed. Flagged for Target 3; not pursued here. A second, milder observation: `estimatedWriteSize` is an estimate, so even on the guarded path an under-estimate admits a compaction that can still exhaust the drive mid-write. |
| **Stage-4 feedback** | none yet |

---

## 11. Notes

- **Why this is filed as one case, not two.** `getWriteDirectory()` contains
  two disk-capacity checks — the direct guard at `:282` and the per-candidate
  comparison inside `getWriteableLocation():453` — on mutually exclusive paths
  of the same method, both reading the same `getAvailableSpace()` accessor and
  both gating the same allocation. README §6.1's "one case, several check
  sites" applies: the case is named after the primary site (`:282`) and the
  second is recorded in §1 and §6b.
- **Dead branch.** `getWriteableLocation()` throws rather than returning
  `null`, so `if (d == null)` at `:291` cannot fire in 5.0.9. Recorded because
  it makes the method look like it has a third rejection path when it does
  not.
- **First of its kind in this folder** — first disk-scoped case (scope
  extended 2026-09-18) and first pattern-(c) case. It is also the first case
  where the pattern's domination requirement actually *failed*, which is worth
  keeping in mind when patterns (b)/(c) triage resumes: non-domination is a
  finding to record, not grounds for rejection under Rule 3.
