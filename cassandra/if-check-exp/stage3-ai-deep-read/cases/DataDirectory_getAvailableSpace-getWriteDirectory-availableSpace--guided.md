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

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
The test runs the same compaction of eight equal SSTables on a nearly full filesystem under two
partitioners — the default `Murmur3Partitioner`, where §5 says the guard never runs,
and `ByteOrderedPartitioner`, where it does — and compares what each does. **Run so
far:** none. Converted to this layout 2026-10-06.

**Step-0 amendments (stage-4 audit, 2026-10-15; results file §1.1 lists them with the reasons).** Made before any
reading of this case existed:
(1) **the trigger is a background compaction** (`nodetool enableautocompaction ks1 t` with the sibling check switched off
over JMX), not `nodetool compact`: a major compaction is `MAJOR_COMPACTION`, which the switch does not cover
(`CompactionTask.java:386`), and the sibling's budget `round(max(0, U − m) × pct)` with `pct ≤ 1`
(`DatabaseDescriptor.java:1016-1017`) is never above the guard's `U − m`, so a major compaction sheds inputs until the
guard admits and can never reach the guard's disallow;
(2) *T* is the sum of the inputs' `Data.db` lengths (`SSTableReader.getTotalBytes()` sums `onDiskLength()`,
`SSTableReader.java:541-546`), not `du` of every component;
(3) arm A's prediction is split by free space: at `d` = −16 MiB the filesystem still holds the output (`U` = *T* + 34 MiB),
so arm A completes while free space dips below *m* (the reserve the guard keeps); only `d` = −256 MiB fills the filesystem;
(4) on arm B **every memtable flush is space-checked too** (`positions == null` sends `Flushing.flushRunnable()` to
`getWriteableLocationAsFile(estimatedSize)`, `Flushing.java:106-111`, i.e. the second check site `Directories.java:453`), so
an `m` that clamps the available space to 0 makes every flush fail with `FSDiskFullWriteError` before any compaction:
the cluster `m` sweep becomes 50 · 240 · 272 · 512 MiB at `U` = *T* + 256 MiB (a ±16 MiB pair around the boundary) and the
clamp at 0 moves to the unit tier, which also shows the flush site;
(5) a Byteman observation rule prints the guard's two operands exactly and which path created each writer (9c, 9d);
(6) a unit JVM owns no token ranges, so `positions` is null under `Murmur3Partitioner` too until the test registers a
local token (as `DiskBoundaryManagerTest` does); and `prettyPrintMemory(1)` renders `1B`, not `1 byte`;
(7) layout: one node on `pc57`, `num_tokens: 1` with an `initial_token` on both arms (the shipped token allocator is not
used), every directory but the data directory on local disk.

### 9a. Procedure and conclusions

**Testability:** partly config, partly not. *(Trigger amended 2026-10-15: a background compaction, see the amendments above.)* The limit's dominant term, the device's
usable bytes, is queried live from the OS ([`Directories.java:781-785`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L781-L785)):
it is varied by **provisioning a small filesystem and a ballast file**, not by
configuration. The tunable term `min_free_space_per_drive` is config, restart-only (no
`volatile`, no JMX setter); at the unit tier `DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(long)`
sets it. The path selector, `partitioner`, is fixed when a cluster is initialised, so
the two arms are **two clusters**, not a restart.

**Two jobs.** (1) Where the guard runs (`diskBoundaries == null`), confirm that it
refuses a compaction whose estimated output exceeds `usable − min_free_space_per_drive`
before any file is made. (2) Where it does not (the default `Murmur3Partitioner` on a node
that owns ranges), confirm that **no space check of this guard runs** and see what the
compaction does instead. A run that only does (1) measures a path the default
configuration never takes and overstates the constraint.

**Claim under test:** the comparison at `CompactionAwareWriter.getWriteDirectory():282`
throws `RuntimeException` before any output `SSTableWriter` is created when the target
directory's available bytes are below the compaction's estimated output (the sum of the
inputs, §7); nothing is created, the inputs stay. It is reached only when
`diskBoundaries == null` (§5): under `Murmur3Partitioner` the writer is created without
any check (§5, §8's caveat).

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** the guard refuses at `usable − min_free` on the guarded path, and does
  not run on the default one.
- **Test:** the same 8-SSTable table and the same background compaction of all eight
  (`OperationType.COMPACTION`, amended 2026-10-15) on two clusters
  (`ByteOrderedPartitioner` and `Murmur3Partitioner`), with free space set by ballast
  above and below the inputs' total, and `min_free_space_per_drive` swept at a fixed
  device; the sibling admission check is switched off so it cannot refuse first.
- **Logic:** (1) at a free space above the total both arms compact; if not, the run is
  invalid. (2) Below it, arm B throws the guard's exception before any output file exists:
  usage **stops at the limit**; its message and the trace carry both operands, and every
  trace line obeys "refused iff available < estimate". (3) The boundary moves
  with free space and with `min_free_space_per_drive` by exactly the change: usage
  **follows the constraint**. (4) Arm A prints no guard line and throws no guard exception:
  just below the boundary it completes and eats into the `m` reserve, far below it it writes
  until the filesystem is full: the guard is not what bounds it (**non-domination**).
- **Refuted if:** arm B compacts with the estimate above the limit, or its boundary does
  not follow the two terms; or arm A refuses at the guard's boundary with the guard's
  message, or prints a guard trace line (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) run upstream `CompactionAwareWriterTest` (the writers on a roomy
   directory, `Murmur3Partitioner`). (b) Run the harness test `WriteDirectoryGuardTest` (9c)
   once per partitioner: with the directory's available space stubbed to the estimate it
   admits, one byte less is refused with the guard's message and creates no file (the exact
   boundary); the default path (a local token registered, `positions` non-null) throws
   nothing at a stub of 1 B and creates the writer; an `m` above the device clamps the
   available space to 0 and the guard refuses with `(0B available)`; with the stub at 1 B a
   flush fails with `FSDiskFullWriteError` on the guarded path only. *(Amended 2026-10-15.)*
2. **Cluster tier** — two single-node clusters (arm B: `ByteOrderedPartitioner`; arm A:
   `Murmur3Partitioner`), each with its data directory on a dedicated 4 GiB filesystem
   (9b), one fresh filesystem and dataset per value (a label).
3. **At each value:** idle control → **A**, free space above the inputs' total → **B**, free
   space below it. No scenario C: the non-domination is arm A's reading in B, not a bypass
   arm. The trigger is the background compaction of all eight inputs (amended 2026-10-15).
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *T* = the sum of the 8 inputs' `Data.db` lengths, the estimate exactly (amended
2026-10-15; 8 × about 64 MiB = 512 MiB);
*U* = `getUsableSpace()` of the data filesystem at the trigger (`df` "Available" for the
user that runs Cassandra); *m* = `min_free_space_per_drive`; the guard compares
`max(0, U − m)` with *T* (`availableSpace < estimatedWriteSize` refuses).

- **A (`U − m ≥ T`), both arms:** the compaction completes, one output of about *T*,
  no exception; peak disk use of the table about `2 T`, final about *T*.
- **B, arm B (`U − m < T`):** `RuntimeException: Not enough space to write <T> to <dir> (<U − m>
  available)` from `getWriteDirectory`, **before** any new file appears in the table
  directory; the 8 inputs untouched; `du` of the table unchanged; no `SSTableWriter`.
  Boundary: `U − m = T` is admitted, one byte less is refused.
- **Every guard trace line (arm B, amended 2026-10-15):** `estimate` = *T* exactly; `available` = the `df`
  Available at the trigger minus *m*, within 1 MiB (system-table flushes between the reading and the check);
  refused iff `available < estimate`, with no exception: the sign of the comparison is the whole claim.
- **B, arm A (amended 2026-10-15):** no such exception and **no guard trace line**; every writer is created on the
  boundary path (`positions` non-null in the trace). At `d` = −16 MiB (`U` = *T* + 34 MiB, enough for the output,
  about *T* plus a few MiB of other components): the compaction **completes**, and the minimum `df` Available during it
  falls **below *m*** (the reserve the guard would have kept), above 0. At `d` = −256 MiB (`U` = *T* − 206 MiB): the
  output grows until the filesystem is full, then the write fails with a filesystem error
  (`No space left on device`, as an `FSWriteError`), the transaction aborts and the inputs stay; whether the partial
  output is removed is read, not assumed (the abort writes to the full filesystem too). `du` of the table peaks at about
  `T + U` (the filesystem's free space) before the failure. What the node does next follows
  `disk_failure_policy` (the shipped file says `stop`, which stops the client transports,
  `DefaultFSErrorHandler.java:68-74`): read it, do not assume.
- **Boundary shifts (amended 2026-10-15):** at a fixed *U* = `T + 256 MiB`, `m` = 50 MiB and 240 MiB admit,
  `m` = 272 MiB and 512 MiB refuse (arm B): the boundary sits at `U − T` = 256 MiB here and at 50 MiB in the device
  sweep, so the refusal point moves by exactly the change in *m*. The clamp at 0 (`m` above the device) is shown at the
  unit tier: on arm B a clamped node cannot flush at all (amendment 4).
- **Flush site (arm B, amended 2026-10-15):** on the guarded path every flush calls `getWriteableLocation(estimatedSize)`
  (second check site, `Directories.java:453`), so flushes of `ks1.t` and of system tables print `writeable` trace lines on
  arm B and none on arm A; at the unit tier a flush with the stub at 1 B fails with `FSDiskFullWriteError` on the guarded
  path only.
- **Sibling control (arm B, `d` = −256 MiB, check left on):** the sibling sheds inputs (`Reducing scope`) until their sum
  is at most `round(0.95 × (U − m))`, then the guard admits the reduced estimate: no guard exception.
- **Estimator margin:** the figure printed is *T* (the sum of the inputs), not the size of
  the merged output; with incompressible, disjoint rows the output is about *T*, so the
  guard refuses a compaction that is about to need about *T*, no over-refusal.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Arm B refuses at `U − m < T` before any file, every trace line obeys "refused iff available < estimate", the boundary follows *U* and *m* exactly; arm A prints no guard line, throws no guard message at the same *U*, completes into the `m` reserve at `d` = −16 MiB and fails later on a full filesystem at `d` = −256 MiB | **Confirmed**, including §5's non-domination: the guard runs only on the guarded path. |
| Arm B as above; arm A refuses with the guard's message at the same boundary, or prints a guard trace line | **§5 refuted** — some path does consult the guard under `Murmur3Partitioner` (first rule out the sibling admission check by its message); rewrite §5, §8's caveat and §10. |
| A guard trace line whose outcome disagrees with `available < estimate`, or whose estimate is not *T* | **Refuted** in part — §4's operands are misread (added 2026-10-15). |
| Arm A at `d` = −16 MiB fails on a full filesystem, or its minimum free space stays at or above *m* | **Not confirmed** for the reserve breach — the output was larger, or smaller, than *T* plus a few MiB: read the output's component sizes (added 2026-10-15). |
| The background task holds fewer than the 8 inputs (no single task of all eight) | **Invalid run** — STCS bucketing differed; the estimate is not *T*: rebuild (added 2026-10-15). |
| Arm B compacts with `T > U − m` and no exception | **Refuted** for the guard — or the guarded path was not taken: check the partitioner and the `diskBoundaries` debug line first. |
| Arm B refuses at a boundary that does not move with *m* by the change in *m* | **Refuted** in part — §4's limit arithmetic is misread. |
| Arm B refuses but a file of the output exists in the table directory | **Refuted** for "before any file" — read §6b. |
| Arm A completes although the filesystem cannot hold the output | **Not confirmed** for the failure mode — the estimate overstated; the output was smaller than the free space: lower the free space (ballast) and re-run. |
| A run other than the sibling control prints the **sibling's** message (`Not enough space for compaction … Reducing scope`) | **Invalid run** — the admission check was not switched off (9b) or the task was not a `COMPACTION`; fix and re-run. |
| `df` free space at the trigger differs from the intended *U* by more than 16 MiB | **Invalid run** — drift; recompute the ballast (9c) and re-run. |

**Why the exception text and `df`, not `du`:** no metric or log line exposes the
comparison on this path (only a `trace` line on success); the exception carries both
operands, and `df` plus the inputs' `du` are the independent figures.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knobs** | (1) The device's free space: the data directory on a dedicated filesystem, varied by a **ballast** file. (2) `min_free_space_per_drive` in `cassandra.yaml` (default `50MiB`, [`Config.java:339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L339)); restart-only; unit tier `DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(long)`. (3) **The path selector**, `partitioner` in `cassandra.yaml`, set at cluster initialisation: `org.apache.cassandra.dht.ByteOrderedPartitioner` (no splitter, so `positions` is null, [`DiskBoundaryManager.java:46-47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/DiskBoundaryManager.java#L46-L47), [`IPartitioner.java:148-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/dht/IPartitioner.java#L148-L151)) or `Murmur3Partitioner` (has one, [`:435`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/dht/Murmur3Partitioner.java#L435)). |
| **Confirm it took effect** | `df -B1` of the data filesystem before each trigger (*U*); `bin/nodetool describecluster` prints the partitioner; the `Refreshing disk boundary cache for ks1.t` / `Updating boundaries` debug lines appear only on arm A (`DiskBoundaryManager`, `DEBUG` is on for `org.apache.cassandra` in the shipped `logback.xml`), and **never** on arm B; the trace's `switch` lines print `positions=null` on arm B and a list on arm A (amended 2026-10-15). |
| **Capacity values** | *(Amended 2026-10-15.)* Device sweep at `m` = 50 MiB, both arms, one label each: *U* = `T + 50 MiB + d` with `d` = +256 MiB and +16 MiB (admitted), −16 MiB and −256 MiB (refused on arm B). `m` sweep, arm B, at `U` = `T + 256 MiB`: `m` = `50MiB`, `240MiB` (admitted), `272MiB`, `512MiB` (refused). The clamp at 0 is unit-tier only (amendment 4). Plus the sibling control (arm B, `d` = −256 MiB, check on). Labels: `b_p256 b_p16 b_m16 b_m256 b_mm050 b_mm240 b_mm272 b_mm512 b_sib a_p256 a_p16 a_m16 a_m256`. |
| **Scope** | **Per compaction attempt, per chosen directory** — one compaction's output against one directory's free space, no account of other compactions. One data directory and `concurrent_compactors: 1`, so *N* = 1 and the fallback `getWriteableLocation()` (the second check site) is not reached **by the compaction**; it is reached by every flush on arm B (amendment 4), which the trace records. |
| **Level** | Both. Unit: the harness `WriteDirectoryGuardTest` and upstream `CompactionAwareWriterTest`; `CompactionsBytemanTest` shows the Byteman idiom. Cluster: both arms. |

**Cluster layout.** Each cluster's data directory sits on a **dedicated 4 GiB loop
filesystem** (the ballast makes free space exact), re-made for every label (amended 2026-10-15: names, one node on
`pc57`):

```bash
truncate -s 4G ~/stage4-dds.img && mkfs.ext4 -q -F ~/stage4-dds.img
sudo mkdir -p /mnt/stage4-dds && sudo mount -o loop ~/stage4-dds.img /mnt/stage4-dds && sudo mkdir /mnt/stage4-dds/data && sudo chown $USER /mnt/stage4-dds/data
```

`data_file_directories: [/mnt/stage4-dds/data]`; the ballast is `/mnt/stage4-dds/ballast` (same filesystem, outside the
data directory); the commit log, hints, saved caches, CDC directory, configuration and logs are under `~/stage4-dds/`
on local disk, never `/proj`. The two arms are two fresh clusters with the same
yaml except `partitioner`, `initial_token` and `cluster_name`: `num_tokens: 1`, `initial_token` `00` (arm B) or `0`
(arm A), `concurrent_compactors: 1`, `min_free_space_per_drive` per label; heap 4 GiB.

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `concurrent_compactors` | `1` | Another compaction's output would move free space under the test. |
| Table `ks1.t` | `SizeTieredCompactionStrategy`, `'enabled': 'false'`, `compression = {'enabled': false}` | Autocompaction off; no compression, so the output is about the inputs' sum and the estimate is not an over-estimate. |
| Admission check | switched off per table before each trigger: JMX `compactionDiskSpaceCheck(false)` on `org.apache.cassandra.db:type=Tables,keyspace=ks1,table=t` | The sibling `max_space_usable_for_compactions…` check gates the same compaction earlier on both arms and would refuse first; the switch applies **only** to `OperationType.COMPACTION` ([`CompactionTask.java:386-390`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L386-L390)), so the trigger must be a background compaction (amended 2026-10-15). |
| Trigger | `bin/nodetool enableautocompaction ks1 t` (STCS buckets the eight equal inputs into one task), then `bin/nodetool disableautocompaction ks1 t` once the task has ended | A background task is a `COMPACTION`; a refused task is not resubmitted (`CompactionManager.java:353-383`), and disabling stops a later flush from submitting it again (added 2026-10-15). |
| `disk_failure_policy` | as shipped (`stop`) | Arm A ends in a disk-write error; record the node's state after it. |
| Data directories | exactly one | More activate the fallback (§6b). |
| Payload | incompressible, distinct keys per SSTable | The estimate is the input sum; compressible or overlapping data shrinks the output and hides the refusal's accuracy. |

**Controls:**

- **Idle run** — dataset built, no `nodetool compact`: `df` stable over 30 s.
- **Ample-space run** — *U* far above *T*, both arms: both must compact (the control for "the setup works").
- **Sibling check on** — once on arm B, with the admission check left on: its message differs from the guard's, which shows the instrument can tell them apart.

**Reset between runs:** stop the node, empty `/mnt/stage4-data`, rebuild the 8 inputs, recompute and write the ballast, confirm `df`, start. A new cluster for each arm (separate data, yaml, `cluster_name`).

### 9c. Workload

The operand is one compaction's estimated output: build SSTables of a known total,
set the free space with a ballast file, and issue one major compaction.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `WriteDirectoryGuardTest.java` | Unit tier. Package `org.apache.cassandra.db.compaction.writers`, modelled on `CompactionAwareWriterTest`; the partitioner comes from `-Dstage4.partitioner` (`Murmur3Partitioner` or `ByteOrderedPartitioner`), set before the server is prepared, as `MemtableSizeTestBase.setup(…, partitioner)` does (`StorageService.instance.setPartitionerUnsafe(partitioner)` then `CQLTester.prepareServer()`). Under `Murmur3Partitioner` it registers one local token so `positions` is non-null (amended 2026-10-15). The stub is a `@BMRule` on `Directories$DataDirectory.getAvailableSpace` that returns a static field of the test when it is ≥ 0. See 9e. |
| `guard-trace.btm` | Observation rules (change no behaviour), added 2026-10-15: `guard est=<estimatedWriteSize> avail=<getAvailableSpace() as returned> refused=<avail < est>` after the call at `getWriteDirectory():281`; `switch positions=<null or size> dir=<location>` at `switchCompactionWriter()` entry; `writeable size=<writeSize> table=<ks.t> avail=<the directory's available space>` at `Directories.getWriteableLocation()` entry. Lines go to `-Dstage4.trace`. |
| `cluster-run.py <label>` | Cluster tier, one label per call (amended 2026-10-15; replaces `build-inputs.sh` and `set-ballast.sh`): fresh loop filesystem, node yaml, start with the Byteman agent, the 8 inputs (12,800 rows of 5 KiB random blob per flush, distinct keys) and the dataset check, the ballast (`fallocate`, re-read until `df` is within 1 MiB of *U*), JMX switch, 30 s idle control, the trigger, the 0.5 s `du`/`df` sampler, the outcome checks with `EXPECTED:` lines, the node's state, stop. Writes `summary.txt`, `samples.csv`, `session.log`, the trace and the logs to `~/stage4-logs/dds/<label>/`. |
| `make-node-yaml.sh`, `Jmx.java`, `unit-run.sh` | The yaml builder (tag's file plus the layout lines of 9b), the JMX client (`compactionDiskSpaceCheck(false)`), and the unit runner (added 2026-10-15). |

```bash
# unit tier — one JVM per partitioner
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.CompactionAwareWriterTest
cp <harness>/WriteDirectoryGuardTest.java test/unit/org/apache/cassandra/db/compaction/writers/
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.WriteDirectoryGuardTest \
  -Dtest.jvm.args="-Dstage4.partitioner=ByteOrderedPartitioner"
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.WriteDirectoryGuardTest \
  -Dtest.jvm.args="-Dstage4.partitioner=Murmur3Partitioner"

# cluster tier: one label per call (amended 2026-10-15); inside, per label:
#   CREATE KEYSPACE ks1 ... ; CREATE TABLE ks1.t (pk int PRIMARY KEY, v blob) WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'} AND compression = {'enabled': false};
#   8 x (12,800 rows, nodetool flush ks1 t); ballast to U; JMX compactionDiskSpaceCheck(false) on ks1.t (not for b_sib)
#   bin/nodetool enableautocompaction ks1 t ; wait for the task to end ; bin/nodetool disableautocompaction ks1 t
<harness>/cluster-run.py <label>
```

**Starting values.** Estimates, not measurements:

| Setting | Value | Why |
|---|---|---|
| Inputs | 8 SSTables of about 64 MiB (*T* about 512 MiB) | Output about *T* at no compression; the 4 GiB filesystem holds inputs, output and ballast with room. |
| Payload | batches of 12,800 rows of one 5 KiB random blob, distinct keys per batch, then `nodetool flush ks1 t` | Disjoint, incompressible. |
| Ballast | exact, from `df` at the trigger | Free space must be within 16 MiB of the intended *U*. |
| Trigger | `bin/nodetool enableautocompaction ks1 t` (amended 2026-10-15; was `nodetool compact`, a `MAJOR_COMPACTION` the switch does not cover) | Routes through `CompactionTask` as `OperationType.COMPACTION`; `compactionstats` empty beforehand. |

**If sizes drift:** a `tablestats` count other than 8, or a `Data.db` length more than 10 % off 64 MiB, means an automatic compaction ran or the payload changed: rebuild. Record each rebuild.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — the estimate *T* | The sum of the 8 `Data.db` lengths before the trigger (the estimate is the sum of the inputs' `onDiskLength()`, [`ColumnFamilyStore.java:1700-1703`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1700-L1703), `SSTableReader.java:541-546`; amended 2026-10-15, was `du` of all components); the trace's `est=` prints it exactly; the exception text prints it rounded. | Before each trigger | The exception rounds with `prettyPrintMemory`; the trace is exact. |
| **Limit** — `U − m` | `df -B1` Available of `/mnt/stage4-data`, minus `m`; the exception text prints it as `(<n> available)`. | Immediately before each trigger | `getUsableSpace()` excludes the filesystem's reserved blocks, as `df`'s Available does; do not use `Free`. |
| **Disallow evidence** | `logs/system.log`: `RuntimeException: Not enough space to write <T> to <dir> (<x> available)` from `CompactionAwareWriter.getWriteDirectory` ([`:283-286`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L283-L286)); the trace's `guard … refused=true` line and no `switch` line after it; `ls` of the table directory after the trigger: no new `*-Data.db`; `du` unchanged. | After each trigger | The sibling's text is `Not enough space for compaction <id> of ks.t, estimated sstables = …` and a `Reducing scope` warning: **different**. The guard's message is the one with `to <dir>`. A background task's exception is logged as `ERROR … Exception in thread …` with the `RuntimeException` on the next line: pair the lines. |
| **Path evidence** (added 2026-10-15) | The trace: `guard` lines (arm B only), `switch positions=…` per writer, `writeable` lines per flush (arm B only). | Whole lifetime | The trace file is append-only per label; filter on `table=ks1.t` for the flush lines. |
| **Bypass volume** — arm A's failure | The error in `system.log` (`FSWriteError` / `No space left on device`), `du -sb` of the table directory sampled each second (peak), `df` Available falling to about 0, the files left after the abort, `nodetool statusbinary` and `nodetool status` afterwards. | Throughout the trigger | Read the node's state **before** stopping it: `disk_failure_policy` may already have stopped gossip and the native transport. |
| **Real resource** — disk | The same `du`/`df` samples. | Throughout | The inputs and the partial output coexist until the transaction aborts or commits. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Record pass or fail and the asserted values.

1. Run upstream `CompactionAwareWriterTest`. Record pass or fail.
2. Run `WriteDirectoryGuardTest` twice (9c). In each JVM it creates a table, writes and
   flushes a few SSTables, takes a `LifecycleTransaction` over them
   (`OperationType.COMPACTION`) and builds a `DefaultCompactionWriter`, as
   `CompactionAwareWriterTest.testDefaultCompactionWriter` does, with a `@BMRule` on
   `Directories$DataDirectory.getAvailableSpace` returning the test's stub value when it is ≥ 0 (the test runs under
   `BMUnitRunner`, as `StorageProxyTest` does). *(Amended 2026-10-15: exact boundary, clamp, flush site, local token,
   `prettyPrintMemory` text.)* Under `Murmur3Partitioner` the test first prints `positions` (null: a unit JVM owns no
   ranges), then registers one local token, invalidates the boundaries and prints them again (non-null).
   1. `ByteOrderedPartitioner`: with the stub at *T* − 1 (*T* = the inputs' `onDiskLength()` sum), appending the first
      row throws `RuntimeException` whose message is exactly `Not enough space to write <prettyPrintMemory(T)> to <dir>
      (<prettyPrintMemory(T − 1)> available)`; no new file exists in the table directory, the inputs are unchanged after
      the abort; with the stub at *T* the first append creates the writer (a new `*-Data.db`), and the transaction is
      aborted; with the stub at 1 the message ends `(1B available)`;
   2. `ByteOrderedPartitioner`, clamp: with the stub off and `min_free_space_per_drive` set above the device's usable
      space, `getAvailableSpace()` returns 0 and the guard's message ends `(0B available)`; `m` is restored;
   3. `Murmur3Partitioner`: with the stub at 1, appending the first row throws nothing; a `*-Data.db` for the
      output exists (the writer was created without the check); the transaction is
      aborted at the end of the step;
   4. both: with the stub off, the compaction completes (one output, the rows all present);
   5. flush site, last: with the stub at 1 and a non-empty memtable of a second table, a flush fails with
      `FSDiskFullWriteError` under `ByteOrderedPartitioner` and succeeds under `Murmur3Partitioner`.

   Record pass or fail and, per step, the asserted values, and print `cfs.getDiskBoundaries().positions`
   (null on arm B, non-null on arm A) to show which path ran.

**Before the cluster tier.**

1. **Instrument check.** On each arm, with ample space, build a small table, run
   `nodetool compact`, and confirm it completes; then set the ballast to leave less than
   the inputs' total and, on arm B only, confirm the guard's message appears. A message of
   the sibling's form stops the run (9b).
2. **Dataset check.** `bin/nodetool tablestats ks1.t` shows 8 SSTables of about 64 MiB.

**Cluster tier, for each arm and each value (9b; amended 2026-10-15: one label per value, a fresh filesystem and
dataset each, the background trigger, the `m` values):**

1. **Control run** — fresh filesystem (9b), node yaml with the label's `m` and partitioner, start with the trace agent, build the 8 inputs, set the JMX `compactionDiskSpaceCheck(false)` on `ks1.t` (not for `b_sib`), set the ballast to *U*, record `df`, the `Data.db` lengths, `du -sb` and the partitioner, and take 30 s of idle samples.
2. **Scenario A (`d` = +256 MiB and +16 MiB; `b_mm050`, `b_mm240`)** — start the `du`/`df` sampler, `bin/nodetool enableautocompaction ks1 t`, wait for the task to end, `disableautocompaction`; record that it completes, the output size and the peak.
3. **Scenario B (`d` = −16 MiB and −256 MiB; `b_mm272`, `b_mm512`)** — the same; record the exception text and the trace (arm B), or on arm A the growth of `du`, the minimum free space, the error at the full filesystem, the files left, and the node's state.
4. **Stop** — `bin/nodetool stopdaemon` if the node still runs, check nothing is left, unmount, keep the logs.

**Sibling-check control (9b)** — once on arm B with the admission check left on: record the message form.

Stop when each scenario's records are taken; a run where the ballast leaves *U* outside the intended band is invalid (9a).

**Record for stage 4:** the `cassandra.yaml` diff (partitioner, `min_free_space_per_drive`) and JVM options in force, the exact commands, `df` and `du` at each trigger, the `nodetool describecluster` output, the exception texts and error lines, the trace, the files left in the table directory, the node's state after arm A's failure, per arm and value.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source. (Stage 1/2 had surfaced this line as a row, but the case was made from the source, not the row.) |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | **Yes — significant.** The guard is bypassed entirely on the `diskBoundaries != null` path (§5), which is the **default** configuration (`Murmur3Partitioner`, node owning ranges): compaction output is then written to a boundary-selected directory with no free-space check at all. This is a stronger default-mode gap than the memtable cases' `markBlocking()` escape hatch or the native-transport `throw_on_overload=false` gap, because the check is not overridden — it is never executed. Flagged for Target 3; not pursued here. A second, milder observation: `estimatedWriteSize` is an estimate, so even on the guarded path an under-estimate admits a compaction that can still exhaust the drive mid-write. |
| **Stage-4 feedback** | **Closed 2026-10-15: unit Confirmed; cluster Confirmed (§9a row 1, including §5's non-domination); no run 2** ([results](../../stage4-runtime-verification/results/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace--guided.md); uncommitted). Step-0 audit Ready after amendments (§9 `ee1b30c6…`, §9a `4c82f05a…`): the trigger became a background compaction (`nodetool compact` is a `MAJOR_COMPACTION`, which the JMX switch does not cover, and the sibling check's budget is never above `U − m`, so a major compaction can never reach this guard's disallow); *T* is the sum of `Data.db` lengths; arm A's −16 MiB prediction; the `m` sweep. Run 1 on `pc57`: under `ByteOrderedPartitioner` the guard refused at `U − m − T` = −16.8 MB and −268 MB and admitted at +16.8 MB and above, at `m` = 50 MiB and at `m` = 240/272 MiB, `est` = *T* and `avail` = `U − m` to the byte, no file on a refusal; under `Murmur3Partitioner` no guard line in any lifetime, the compaction completed at −16 MiB with free space down to 34.4 MB (the 50 MiB reserve breached by 18 MB) and at −256 MiB wrote until `FSWriteError: No space left on device`, after which `disk_failure_policy: stop` stopped the native transport and gossip, the partial output was removed and the inputs stayed. **Notes for stage 3 (not applied):** (1) the second check site (`Directories.getWriteableLocation():453`) guards **every memtable flush** on the null-boundary path (`Flushing.java:106-111`), and on any partitioner during start-up, before the node owns token ranges (observed: 24 system-table flushes per arm-A lifetime, all before NORMAL); §5/§6b say it is reached only when inputs span directories; (2) with `min_free_space_per_drive` above the device the guarded path cannot flush at all (`FSDiskFullWriteError`; unit tier); (3) §6b step 2: a failed background task is not resubmitted (`CompactionManager.java:374-383`), a later flush or `enableautocompaction` submits it again. Sub-predictions missed: arm A's start-up flushes pass the second site; the −256 MiB sampler bands (0.5 s sampling). |

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
