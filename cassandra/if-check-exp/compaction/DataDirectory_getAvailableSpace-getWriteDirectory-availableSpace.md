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
guard that the default configuration skips — is recorded in §9 as a
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

## 9. Verification

| Field | Content |
|--------|---------|
| **Status** | `pending` |
| **Verified By / Date** | — (behavioral verification deferred by decision, 2026-09-22; see README §7.5) |
| **Line numbers checked** | 2026-09-22, against the local clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). All `file:line` references in this file were read directly from that clone. |
| **Trigger method** | Not run. When verification resumes, the natural unit-level trigger is to construct a `CompactionAwareWriter` on a table whose partitioner has no splitter (so `diskBoundaries == null` and the guard is actually reached), point it at a data directory with little free space, and drive `maybeSwitchWriter()` with an `estimatedWriteSize` larger than `getAvailableSpace()`. Per README §8's methodology, prefer asserting on the thrown `RuntimeException` at `:283` over observing a failed compaction. **Note the trigger must control the partitioner** — under the default `Murmur3Partitioner` the guard is never reached, so a naive test would pass without ever executing the check. Check `test/unit/.../db/compaction/` for existing `CompactionAwareWriter` scaffolding before writing a new harness. Raising `min_free_space_per_drive` is the cleanest way to shrink `availableSpace` without physically filling a disk. |
| **Evidence** | None yet. |
| **Escape hatch / Target-3 note** | **Yes — significant.** The guard is bypassed entirely on the `diskBoundaries != null` path (§5), which is the **default** configuration (`Murmur3Partitioner`, node owning ranges): compaction output is then written to a boundary-selected directory with no free-space check at all. This is a stronger default-mode gap than the memtable cases' `markBlocking()` escape hatch or the native-transport `throw_on_overload=false` gap, because the check is not overridden — it is never executed. Flagged for Target 3; not pursued here. A second, milder observation: `estimatedWriteSize` is an estimate, so even on the guarded path an under-estimate admits a compaction that can still exhaust the drive mid-write. |
| **Notes** | Discovered via the CodeQL `db/compaction/` batch (2026-09-18) and initially rejected as out-of-scope when this folder was memory-only; reclassified as a live candidate the same day once disk entered scope; written up 2026-09-22 using discovery **method 1** (direct AI source reading), which is what surfaced the non-domination finding — the stage-1 CSV row alone shows only the comparison at `:282`. |

---

## 10. Notes

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
