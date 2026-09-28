# max_space_usable_for_compactions_in_percentage — compaction task admission

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MAX_SPACE_USABLE_FOR_COMPACTIONS_IN_PERCENTAGE-HASDISKSPACEFORCOMPACTIONSANDSTREAMS-AVAILABLEFORCOMPACTION |
| **Constraint** | `max_space_usable_for_compactions_in_percentage` — a **configuration entry** ([`Config.java:344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L344), default `.95`). The limit is **derived from three sources** (device usable bytes, `min_free_space_per_drive`, and this percentage); README §6.1's "derived from several sources → name it after the one a user would tune" selects this one, because it is the only term that exists specifically to bound compactions. See §4's naming note. |
| **Enforcement pattern** | **(b)** — the comparison assigns a local `hasSpace = false` and the loop continues; the decision is made by a separate `if` in another class that reads the returned boolean. |
| **Capacity check** | [`Directories.hasDiskSpaceForCompactionsAndStreams():551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L551) — `availableForCompaction < toWrite.getValue()`, evaluated once per `FileStore`. |
| **Decision point** | [`CompactionTask.buildCompactionCandidatesForAvailableDiskSpace():412-413`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L412-L413) — `if (...hasDiskSpaceForCompactionsAndStreams(...)) break;`. The disallow side diverges again at [`:421`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L421) (shrink the compaction) and [`:442`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L442) (`throw new RuntimeException`). |
| **Allocation site** | [`CompactionTask.runMayThrow():213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L213) — `getCompactionAwareWriter(...)`, which at [`:308`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L308) creates the `DefaultCompactionWriter` that in turn opens the output `SSTableWriter`. |
| **Related cases** | [`DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`](DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md) — the *other* compaction disk guard. Same resource, different limit, different scope and different disallow effect; see §11 for why these are two cases and not one. |

```java
// Directories.hasDiskSpaceForCompactionsAndStreams():544-561 — the capacity check.
// Note it sets a flag and keeps looping; it does not branch to or away from an allocation.
public static boolean hasDiskSpaceForCompactionsAndStreams(Map<FileStore, Long> totalToWrite)
{
    boolean hasSpace = true;
    for (Map.Entry<FileStore, Long> toWrite : totalToWrite.entrySet())
    {
        long availableForCompaction = getAvailableSpaceForCompactions(toWrite.getKey());
        logger.debug("FileStore {} has {} bytes available, checking if we can write {} bytes", toWrite.getKey(), availableForCompaction, toWrite.getValue());
        if (availableForCompaction < toWrite.getValue())        // <-- capacity check, :551
        {
            logger.warn("FileStore {} has only {} available, but {} is needed",
                        toWrite.getKey(),
                        FileUtils.stringifyFileSize(availableForCompaction),
                        FileUtils.stringifyFileSize((long) toWrite.getValue()));
            hasSpace = false;                                   // <-- the verdict, :557
        }
    }
    return hasSpace;
}
```

```java
// CompactionTask.buildCompactionCandidatesForAvailableDiskSpace():386-447 — the decision point.
// The verdict returned above is read at :412.
if(!cfs.isCompactionDiskSpaceCheckEnabled() && compactionType == OperationType.COMPACTION)
{
    logger.info("Compaction space check is disabled - trying to compact all sstables");
    return true;                                                // <-- ESCAPE HATCH, :386-390
}

final Set<SSTableReader> nonExpiredSSTables = Sets.difference(transaction.originals(), fullyExpiredSSTables);
CompactionStrategyManager strategy = cfs.getCompactionStrategyManager();
int sstablesRemoved = 0;

while(!nonExpiredSSTables.isEmpty())
{
    long writeSize;
    try
    {
        writeSize = cfs.getExpectedCompactedFileSize(nonExpiredSSTables, compactionType);
        // ... build expectedNewWriteSize per output directory ...
        Map<File, Long> expectedWriteSize = CompactionManager.instance.active.estimatedRemainingWriteToDiskBytes();

        // todo: abort streams if they block compactions
        if (cfs.getDirectories().hasDiskSpaceForCompactionsAndStreams(expectedNewWriteSize, expectedWriteSize))
            break;                                              // <-- ALLOW, :412-413
    }
    catch (Exception e) { logger.error(...); break; }            // <-- see §11: errors allow

    if (!reduceScopeForLimitedSpace(nonExpiredSSTables, writeSize))   // <-- DISALLOW step 1, :421
    {
        if(partialCompactionsAcceptable() && fullyExpiredSSTables.size() > 0 )
        {
            assert transaction.originals().equals(fullyExpiredSSTables);
            break;                                              // expired-only compaction still runs
        }
        String msg = String.format("Not enough space for compaction (%s) of %s.%s, ...", ...);
        logger.warn(msg);
        CompactionManager.instance.incrementAborted();
        throw new RuntimeException(msg);                        // <-- DISALLOW step 2, :442
    }
    sstablesRemoved++;
    logger.warn("Not enough space for compaction {}, {}MiB estimated. Reducing scope.", ...);
}
```

## 2. Context

Cassandra periodically merges several of its on-disk data files into one, a
background process called compaction. A compaction is expensive and, while it
runs, both the inputs and the growing output occupy the disk at the same
time — so a node can be driven out of space by its own housekeeping. This
check is the admission gate that runs *before* a compaction task starts: it
adds up how much every compaction currently in flight still has left to write,
adds the size of the one being proposed, and compares that total against how
much room the underlying storage device has left. If the device cannot hold
it, the task is not simply refused — Cassandra first tries to shrink it, by
dropping the largest input file from the merge and asking again, repeatedly,
until either the smaller job fits or there is nothing left to drop. Only then
does it give up and abort.

Two things make this gate distinctive. It is **whole-device and
whole-workload**: it accounts for other running compactions, not just the
proposed one, so admitting a task is a decision about the node's total
in-flight write load. And it reserves a **configurable fraction** of the
drive — by default a compaction may only use 95% of what is free after a
fixed floor is subtracted — so it refuses while the disk still has genuine
room, on the theory that a node with a completely full data drive is far
harder to recover than one that merely stopped compacting.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `compaction` — compaction task admission and disk accounting (`db/compaction`, with the space accounting in `db/Directories`) |
| **One-line role** | Compaction merges and rewrites SSTables in the background to reclaim space and bound read amplification; `CompactionTask` is the unit of that work, and this gate decides how large a unit the node's disks can currently accept. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes** — it compares total pending compaction output bytes against the bytes the file store makes available for compaction, per file store, and the result decides whether the write is allowed to start. |
| **Usage-side operand** | `toWrite.getValue()` — per `FileStore`, the sum of (i) this compaction's expected output, `cfs.getExpectedCompactedFileSize(nonExpiredSSTables, compactionType)` from [`ColumnFamilyStore.java:1698`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1698), divided across its output directories, and (ii) the remaining write of every compaction already running, from [`ActiveCompactions.estimatedRemainingWriteToDiskBytes():59-76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/ActiveCompactions.java#L59-L76). Summed per file store at [`Directories.java:531-536`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L531-L536). |
| **Limit-side operand** | `availableForCompaction` — [`Directories.getAvailableSpaceForCompactions():563-569`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L563-L569). |
| **Limit type** | **Derived** — computed per call from a runtime-queried device figure and two configuration entries: `max(0, round((usableSpace − min_free_space_per_drive) × max_space_usable_for_compactions_in_percentage))`. |

**Limit initialization path.** Three terms meet at the comparison:

1. [`Config.max_space_usable_for_compactions_in_percentage:344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L344) — declared, `volatile Double`, default `.95`. Commented in place as "fraction of free disk space available for compaction after min free space is subtracted".
2. [`Config.min_free_space_per_drive:339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L339) — declared, default `50MiB` (formerly `min_free_space_per_drive_in_mb`). The flat floor, subtracted first.
3. [`FileStore::getUsableSpace`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L566) via `FileStoreUtils.tryGetSpace` — the **dominant term**, queried live from the OS per call. Not declared in Cassandra; a property of the deployed device.
4. [`DatabaseDescriptor.getMinFreeSpacePerDriveInBytes():2567-2570`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2567-L2570) and [`getMaxSpaceForCompactionsPerDrive():2579-2582`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2579-L2582) — read at computation time.
5. [`Directories.getAvailableSpaceForCompactions():565-568`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L565-L568) — combined, floored at 0, and returned into the comparison at [`:551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L551).

**Naming note (Target 1).** The sibling case
`DataDirectory_getAvailableSpace` is named after its accessor because its only
config term is a flat 50MiB floor that is incidental to it. Here the
percentage term is different in kind: it exists *only* for this check, it is
the parameter an operator would move to change this check's behaviour, and it
scales with the device rather than offsetting it by a constant. §6.1's rule
for a derived limit — name it after the one a user would tune — therefore
selects `max_space_usable_for_compactions_in_percentage`. `min_free_space_per_drive`
sits on the same path and is recorded above; the device figure dominates the
magnitude but is undeclared and untunable.

**Neither config entry appears in `conf/cassandra.yaml`.** Verified by grep
against the pinned clone, 2026-09-28. Both are settable in YAML regardless —
`Config` fields bind by name — but an operator reading the shipped file will
not discover either one. Worth knowing before stage 4 goes looking for the
knob.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`CompactionTask.buildCompactionCandidatesForAvailableDiskSpace():412-413`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L412-L413) |
| **Verdict** | Pattern (b): the verdict is the **boolean return value** of `hasDiskSpaceForCompactionsAndStreams`. It is set as the local `hasSpace = false` at [`Directories.java:557`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L557) — inside the comparison's own `if`, which has **no else branch and no allocation in either arm** — returned at [`:560`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L560) through two overloads ([`:537`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L537), [`:520`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L520)), and read at `CompactionTask.java:412`. |

Note the verdict is **aggregated before it is read**: one `false` from any
file store in the loop condemns the whole task, and which file store failed
is not carried out of the method — only the `logger.warn` at
[`Directories.java:552-556`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L552-L556) records it.

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | every file store has `availableForCompaction >= toWrite` | `break` out of the shrink loop; the method returns and `runMayThrow()` proceeds to create the `CompactionAwareWriter` and its output SSTable. |
| **Disallow** | any file store has `availableForCompaction < toWrite` | **Shrink, then re-check.** `reduceScopeForLimitedSpace()` cancels the largest input SSTable from the transaction and the loop repeats with a smaller `writeSize`. When nothing more can be dropped, either an expired-only compaction proceeds, or `CompactionsAborted` is incremented and `RuntimeException` is thrown. |

```java
// allow: leave the loop; runMayThrow() continues to the writer
if (cfs.getDirectories().hasDiskSpaceForCompactionsAndStreams(expectedNewWriteSize, expectedWriteSize))
    break;
```

```java
// disallow step 1 — CompactionTask.reduceScopeForLimitedSpace():98-114
// Degrade rather than refuse: drop the largest input and try again.
public boolean reduceScopeForLimitedSpace(Set<SSTableReader> nonExpiredSSTables, long expectedSize)
{
    if (partialCompactionsAcceptable() && transaction.originals().size() > 1)
    {
        SSTableReader removedSSTable = cfs.getMaxSizeFile(nonExpiredSSTables);
        logger.warn("insufficient space to compact all requested files. ...");
        transaction.cancel(removedSSTable);
        return true;
    }
    return false;
}
```

```java
// disallow step 2 — nothing left to drop: abort the task
CompactionManager.instance.incrementAborted();
throw new RuntimeException(msg);
```

### The graceful-degradation loop is the point

Unlike every other case filed in this folder, the disallow outcome here is
not a single event — it is a **negotiation**. Each failed check removes the
largest input SSTable and re-evaluates, so a node under disk pressure does
not stop compacting; it compacts in progressively smaller units. Three
consequences matter for Target 2, and for the test design in §9:

- The observable effect of the constraint is **not primarily a rejection
  count**. It is the *size* of the compactions that run, visible as
  `CompactionsReduced` and `SSTablesDroppedFromCompaction`
  ([`CompactionMetrics.java:154-155`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/CompactionMetrics.java#L154-L155)).
  `CompactionsAborted` ([`:156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/CompactionMetrics.java#L156)) only moves at the very end of the ladder.
- `partialCompactionsAcceptable()` gates the shrink. It is overridden per task
  type, so for some compaction types the ladder does not exist and the first
  failure aborts.
- Because each retry lowers `writeSize`, the check is eventually satisfied by
  a single-SSTable compaction in almost every case — the loop exits at
  `transaction.originals().size() > 1` failing, not at the disk check passing.

## 6. Code path

### 6a. Allow path → object creation

1. [`CompactionTask.runMayThrow():148`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L148) — calls `buildCompactionCandidatesForAvailableDiskSpace(fullyExpiredSSTables, taskId)` before anything is written.
2. [`buildCompactionCandidatesForAvailableDiskSpace():409`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L409) — collects in-flight remaining write bytes, then calls the check at [`:412`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L412).
3. [`Directories.hasDiskSpaceForCompactionsAndStreams():524-537`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L524-L537) — maps directories to file stores and sums; delegates to the overload at [`:544`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L544).
4. [`:551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L551) — comparison holds for every file store; `hasSpace` stays `true` and is returned.
5. [`CompactionTask.java:413`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L413) — `break`; the method returns `true` (or `false` if sstables were dropped earlier, which only triggers `controller.refreshOverlaps()` at [`:152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L152)).
6. [`runMayThrow():213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L213) — **object creation**: `getCompactionAwareWriter(cfs, getDirectories(), transaction, actuallyCompact)` → [`:308`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L308) `new DefaultCompactionWriter(...)`, which opens the output `SSTableWriter` and begins writing on-disk bytes.

### 6b. Disallow path effect

**Not a clean reject — a shrink-and-retry ladder, and only then an abort.**

1. [`CompactionTask.java:421`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L421) — `reduceScopeForLimitedSpace(nonExpiredSSTables, writeSize)`. If partial compactions are acceptable and more than one SSTable remains, [`:103-111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L103-L111) cancels the largest input from the `LifecycleTransaction` and returns `true`.
2. [`:445-447`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L445-L447) — `sstablesRemoved++`, a warning is logged, and the `while` loop re-runs the whole check with the smaller set. **This repeats**, each pass shedding the then-largest SSTable.
3. When `reduceScopeForLimitedSpace` returns `false` (only expired SSTables left, or partial compactions not acceptable for this task type): if there are fully-expired SSTables and partial compaction is acceptable, [`:428-431`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L428-L431) `break`s and the expired-only compaction **still runs** — expiry reclaims space without writing much.
4. Otherwise [`:441-442`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L441-L442) — `CompactionManager.instance.incrementAborted()` then `throw new RuntimeException(msg)`. The transaction unwinds, inputs are left in place, and no output SSTable exists.
5. If any SSTable was dropped, [`:450-454`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L450-L454) increments `CompactionsReduced` and `SSTablesDroppedFromCompaction` and returns `false`, so the caller refreshes overlaps and **the (smaller) compaction proceeds**.

**Escape hatch — the check can be switched off entirely.**
[`CompactionTask.java:386-390`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L386-L390)
returns `true` without evaluating anything when
`!cfs.isCompactionDiskSpaceCheckEnabled() && compactionType == OperationType.COMPACTION`.
The flag is the per-table field
[`ColumnFamilyStore.compactionSpaceCheck:334`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L334)
(default `true`), flipped through the JMX operation
[`ColumnFamilyStoreMBean.compactionDiskSpaceCheck(boolean):317`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStoreMBean.java#L317)
→ [`ColumnFamilyStore.java:2088-2091`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2088-L2091).
Note its scope: it is per table, it is not persisted, and it applies **only**
to `OperationType.COMPACTION` — so the check still runs for other operation
types even when disabled. Not reachable from `nodetool` in 5.0.9 (grep of
`tools/` finds no subcommand); it requires a JMX client.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `DefaultCompactionWriter` (a `CompactionAwareWriter`) and, through it, the output SSTable's `SSTableWriter` and component files. |
| **Resource consumed** | **On-disk bytes** — the compaction output SSTable, written into the data directory while the inputs are still present. |
| **Rough sizing** | The gated quantity is `writeSize` = `getExpectedCompactedFileSize(nonExpiredSSTables, compactionType)`. For an ordinary `COMPACTION` that resolves to `SSTableReader.getTotalBytes(sstables)` ([`ColumnFamilyStore.java:1700-1703`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1700-L1703)) — i.e. **the sum of the inputs**, not a prediction of the merged result. Since compaction normally shrinks data, this is a deliberate over-estimate. |
| **Lifetime / release** | The output persists until a later compaction supersedes it. The inputs are released when the `LifecycleTransaction` commits — so the transient peak is inputs + output simultaneously, which is exactly what the over-estimate above budgets for. |

## 8. Maximum disk bound

`max_space_usable_for_compactions_in_percentage` scales the whole budget, so
its effect on the ceiling is multiplicative rather than an offset:

- **What it bounds.** `availableForCompaction = (usable − minFree) × pct`. The
  check refuses to start any compaction whose output, plus all in-flight
  compaction output on that file store, exceeds that figure. So it caps the
  node's **total concurrent compaction write commitment per device**, not the
  size of a single SSTable and not the dataset's size.
- **Lowering it** shrinks the budget proportionally. Compactions are refused
  earlier, the shrink ladder fires sooner, and the node settles on smaller
  compaction units — leaving more SSTables live, which costs read
  amplification but reserves a larger unused fraction of the drive. At `pct`
  small enough that even a one-SSTable compaction cannot be admitted,
  compaction stops and disk usage then grows without bound from writes alone.
- **Raising it toward 1.0** lets compaction commit essentially all the free
  space above the `min_free_space_per_drive` floor, so peak on-disk bytes can
  approach device capacity minus 50MiB.
- **Mechanism.** The bound is enforced by *not creating the writer at all* —
  the bytes are never written, rather than being written and then reclaimed.
  Because the usage side over-estimates (§7), the effective ceiling is
  conservative: real peak usage is typically below what the comparison
  budgets.

**Two caveats on this ceiling**, both from §6b. It is per file store and per
admission, so nothing prevents the sum across devices from being larger than
any one device's budget. And the escape hatch removes it entirely for
`OperationType.COMPACTION` on any table where JMX has disabled the check.

## 9. Test design (guidance for stage 4)

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable**, and unusually well served by existing unit scaffolding. `max_space_usable_for_compactions_in_percentage` is a `volatile Double` with a live setter, so it can be changed without a restart. |
| **Constraint knob** | `max_space_usable_for_compactions_in_percentage` in `cassandra.yaml` (the entry is **not** in the shipped file — add it), or at runtime via `DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(double)` ([`DatabaseDescriptor.java:2584-2587`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2584-L2587)). Secondary knob for a cross-check: `min_free_space_per_drive` (`DatabaseDescriptor.setMinFreeSpacePerDriveInMebibytes(long)`, [`:2573-2577`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2573-L2577)). |
| **Capacity values to test** | `pct` ∈ {**0.95** (default), 0.50, 0.10, 0.01}. Capacity produced is `(usableSpace − 50MiB) × pct`, so the values are only meaningful once the device's free space is known and held fixed — record `df` for the data directory's file store at the start of each run. Four values, not three: the response is expected to be linear in `pct` and a fourth point makes a departure from linearity visible. |
| **Usage-side observable** | `toWrite.getValue()` per file store — total pending compaction output bytes. Its two components are `SSTableReader.getTotalBytes(sstables)` for the proposed task and `ActiveCompactions.estimatedRemainingWriteToDiskBytes()` for in-flight ones. |
| **Instrument** | **The real operand is not exposed as a metric** — grep of `src/java/org/apache/cassandra/metrics/` finds no gauge for either component (checked 2026-09-28). Three usable substitutes, in order of directness: (1) the `logger.debug` at [`Directories.java:550`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L550) prints the exact available and requested bytes at every evaluation — enable `DEBUG` for `org.apache.cassandra.db.Directories` and this *is* the operand, not a proxy; (2) the `logger.warn` at [`:552-556`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L552-L556) fires on every disallow; (3) `du -sb` on the data directory, sampled over time, for the external disk figure. Use (1) as the measurement and (3) as the cross-check — they answer different questions and should agree in trend, not in value. |
| **Scope of the limit** | **Per file store, node-wide across tables.** Not per table and not per compaction: the in-flight term makes every concurrent compaction on the same device share one budget. Multiplier: with `N` file stores (distinct devices under `data_file_directories`), total commitment is up to `N × budget`. **Use a single data directory on a dedicated device** so `N = 1`, otherwise the per-store split at [`Directories.java:528-536`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L528-L536) divides the write estimate and confuses the dose-response. |
| **Suggested level** | **Both, and the unit tier first — it is already written.** `test/unit/org/apache/cassandra/db/DirectoriesTest.java` exercises `getAvailableSpaceForCompactions` (lines 913-917) and `hasDiskSpaceForCompactionsAndStreams` (lines 998-1016, 1078-1098) against a mocked `FileStore`, which is the cheapest way to confirm the arithmetic of the limit at several `pct` values. `test/unit/org/apache/cassandra/db/compaction/PartialCompactionsTest.java:211-221` already overrides the method and reverses the `getAvailableSpaceForCompactions` computation — read it before writing anything new. `test/unit/org/apache/cassandra/db/compaction/CompactionsBytemanTest.java:55-115` forces the disallow path with Byteman and asserts each of the three §6b outcomes. Run: `ant testsome -Dtest.name=org.apache.cassandra.db.DirectoriesTest` and `-Dtest.name=org.apache.cassandra.db.compaction.CompactionsBytemanTest`. |

### 9a. Workload — driving the usage operand

The usage side is **compaction output bytes**, so the workload must produce
several sizeable SSTables and then force them to merge.

- Single-node instance, one data directory on a dedicated device, so the
  budget is not split and background traffic cannot move the observable.
- One table, `compaction = {'class': 'SizeTieredCompactionStrategy',
  'enabled': 'false'}` — autocompaction off, so SSTables accumulate and the
  test controls when the check runs.
- Write with `cassandra-stress` (`tools/bin/cassandra-stress`, present in the
  pinned clone) and `nodetool flush` between batches to produce, say, 6–10
  SSTables of roughly equal known size. Record `SSTableReader.getTotalBytes`
  equivalently as the on-disk size of the table directory.
- Trigger with `nodetool compact <ks> <table>` (a major compaction), which
  routes through `CompactionTask.runMayThrow()`.

**Prefer the deterministic single-shot form**, per README §8.2 rule 2: rather
than racing writes against compaction, set `pct` so that the budget is known
to be just above or just below the *total* size of the accumulated SSTables,
then issue one `nodetool compact`. The first evaluation then lands exactly
where intended. Nothing releases capacity concurrently as long as
autocompaction stays off.

**What makes this case's workload distinctive:** the in-flight term. To
exercise it, a second variant should start a large compaction on another
table on the same device and issue `nodetool compact` on the first *while it
runs* — the proposed task should then be refused at a `pct` that would have
admitted it in isolation.

### 9b. Scenario A — just reach capacity

Set `pct` so that `(usable − 50MiB) × pct` is slightly **above** the total
bytes of the accumulated SSTables, then run one major compaction.

Expect at each `pct`: the compaction is admitted on the first evaluation, the
`Directories` debug line shows `available ≳ requested`, `CompactionsReduced`
and `CompactionsAborted` do not move, and the output is a single SSTable.
Peak disk usage for the table ≈ inputs + output, since both coexist until the
transaction commits. This scenario is the control — it establishes that the
knob moves the admission boundary at all, and gives the baseline peak against
which scenario B is read.

### 9c. Scenario B — try to exceed capacity

Set `pct` so the budget is **below** the total input size, then run the same
major compaction. **Do not expect an exception** — §6b says the first
disallow does not abort:

| `pct` relative to input size | Expected, from §6b |
|---|---|
| Budget slightly below total | One or two shrink iterations. `CompactionsReduced` +1, `SSTablesDroppedFromCompaction` +k, a "Reducing scope" warning per iteration, and the compaction **still runs** on a reduced set. Output smaller than scenario A's. |
| Budget below the largest single SSTable | The ladder runs to exhaustion: `reduceScopeForLimitedSpace` returns `false` at `transaction.originals().size() > 1`. With no expired SSTables, `CompactionsAborted` +1 and a `RuntimeException` logged with "Not enough space for compaction". No output SSTable; inputs untouched. |
| Any of the above, with the JMX escape hatch set | `compactionDiskSpaceCheck(false)` on that table → the "Compaction space check is disabled" info line, no evaluation, compaction runs in full regardless of `pct`. |

Record the **count of shrink iterations** at each `pct`, not just whether an
abort happened. That count is the case's real dose-response signal.

### 9d. Expected dose-response

If the traced path is the binding limit:

- **Admission boundary is linear in `pct`.** The largest total input size that
  is admitted without shrinking should track `(usable − 50MiB) × pct`
  proportionally across 0.95 / 0.50 / 0.10 / 0.01. A plot of "largest
  compaction admitted unreduced" against `pct` should be a straight line
  through the origin-ish, offset by the 50MiB floor.
- **Shrink count rises as `pct` falls**, for a fixed set of input SSTables:
  more iterations are needed before the residual set fits.
- **Peak on-disk bytes for the table fall with `pct`**, because the compaction
  that actually runs is smaller, so inputs + output coexist in a smaller
  total.
- **Cross-check with the second knob:** holding `pct` at 0.95 and instead
  raising `min_free_space_per_drive` to a large value should move the boundary
  by a *constant* offset rather than proportionally. If both knobs move it
  proportionally, or both by a constant, the limit arithmetic in §4 has been
  misread.

If instead the escape hatch dominates (table has `compactionDiskSpaceCheck`
disabled), every `pct` behaves identically and peak usage is flat — which is
also what a misread would look like, hence the control in §9g.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| Shrink iterations and `CompactionsReduced` rise as `pct` falls; admitted compaction size tracks the budget; aborts only at the bottom of the ladder | The check enforces as traced. |
| Compactions run in full at every `pct`, with no "Reducing scope" warnings | The escape hatch is on, or `partialCompactionsAcceptable()` is false for this task type and the ladder does not exist — check the info line at [`CompactionTask.java:388`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L388) before concluding anything. Target-3 material; §8's ceiling claim needs amending. |
| Peak disk usage flat across every `pct` while the metrics *do* move | The check fires but does not govern the ceiling — plausible here, since compaction *reclaims* space and a refused compaction leaves more on disk, not less. See §9f. |
| No effect at any `pct` and no log lines from `Directories` at all | The traced path is not the binding limit, or the check is never reached on this workload. Stage 3 misread it; re-read rather than re-run. |

### 9f. What would refute this case

The case claims that `max_space_usable_for_compactions_in_percentage` bounds
on-disk bytes **by preventing the output SSTable from being created**. It is
refuted if, across the `pct` sweep, the compaction is admitted unreduced at a
total input size materially larger than `(usable − 50MiB) × pct` — i.e. the
budget does not gate admission — while the `Directories` debug line confirms
the check was evaluated.

**A subtler refutation, specific to this case and worth stating plainly:**
lowering `pct` reduces compaction, and less compaction means *more* data on
disk, not less. So if the intended reading of "the constraint limits disk
usage" is taken naively, a correct enforcement will produce a dose-response
in the **opposite** direction to the other cases in this folder. The claim in
§8 is about the *compaction write commitment*, not about total table size,
and stage 4 should classify on the shrink/abort metrics and the admitted
compaction size, not on `du` alone. If `du` rises as `pct` falls, that is the
check working, not failing.

### 9g. Confounders and controls

- **Background compaction** — the single largest confounder. Disable
  autocompaction on the test table (`ALTER TABLE ... WITH compaction = {...
  'enabled': 'false'}` or `nodetool disableautocompaction`), and confirm with
  `nodetool compactionstats` that nothing is in flight before each trigger.
  Otherwise the in-flight term moves on its own.
- **Other tables and system keyspaces on the same file store** contribute to
  the in-flight term. A dedicated single-node instance with no other traffic.
- **Free space drifting between runs** — the budget is computed from live
  `getUsableSpace()`, so a run that leaves data behind changes the next run's
  capacity. Truncate the table and confirm `df` returns to baseline between
  runs, and record `df` at the start of every run.
- **The escape-hatch control**: run one scenario-B case with
  `compactionDiskSpaceCheck(false)` set via JMX. It should show the info line
  and no enforcement — this both proves the instrument can see the difference
  and rules out "the check never ran" as an explanation of a null result.
- **Baseline** at default `pct = 0.95` with an input total far below the
  budget; **idle control** with the workload written but no `nodetool compact`
  issued, to separate write-driven disk growth from compaction-driven growth.
- **Estimate vs. reality** — §7 notes the usage side is the *sum of inputs*,
  a deliberate over-estimate. Expect the admission boundary to sit below what
  actual output sizes would suggest; that gap is the over-estimate, not
  measurement error.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — surfaced 2026-09-22 by the first stage-2 batch (helper rows inside the four already-triaged subtrees), via `buildCompactionCandidatesForAvailableDiskSpace()`. The row's *reported* comparisons (`size() > 0`, `sstablesRemoved > 0`) are both noise; the method name pointed the read in the right direction and the real check was two calls further in. Judged and parked in `deferred.md` §1b on 2026-09-22 because it is pattern (b); unparked 2026-09-25; written up 2026-09-28. |
| **Filed by / Date** | Claude (`claude-opus-5`) session, 2026-09-28 |
| **Line numbers checked** | 2026-09-28 against the local `cassandra-5.0.9` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). **Two corrections to `deferred.md` §1b**, which had the decision point at `:411` and the throw at `:441`: the `if` is at **412** (its `break` at 413) and the `throw` at **442**. |
| **Escape hatch / Target-3 note** | **Yes, two.** (1) The check is skipped outright when `compactionDiskSpaceCheck` is `false` for the table *and* the operation is `OperationType.COMPACTION` ([`CompactionTask.java:386-390`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L386-L390)); the flag is per table, not persisted, and flipped over JMX. (2) An **exception in the estimation block is treated as allow**: the `catch` at [`:414-419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L414-L419) logs the error and `break`s out of the loop, so a failure to *compute* the check admits the compaction. `getAvailableSpaceForCompactions` throws `FSReadError` when `getUsableSpace` fails, which reaches this catch. Fail-open, not fail-closed. Flagged for Target 3; not pursued here. |
| **Stage-4 feedback** | none yet |
| **Notes** | The sibling case's `estimatedWriteSize` and this case's `writeSize` come from the same accessor, `getExpectedCompactedFileSize`. They are not the same quantity at the comparison, though: this case adds the in-flight term and divides by output directory count. |

---

## 11. Notes

- **Why this is a separate case from `DataDirectory_getAvailableSpace`.** Both
  guard compaction output against free disk, so the question is fair. They
  differ on every axis the format cares about:

  | | This case | `DataDirectory_getAvailableSpace` |
  |---|---|---|
  | Limit | `(usable − 50MiB) × pct`, per **file store** | `usable − 50MiB`, per **chosen directory** |
  | Usage | this compaction **+ all in-flight compactions** | this compaction only |
  | When | **before** the task starts, at admission | at writer setup, after the task has begun |
  | Disallow | shrink-and-retry ladder, then abort | immediate `RuntimeException` |
  | Runs by default? | yes | **no** — skipped on the default `diskBoundaries != null` path |
  | Tunable | `max_space_usable_for_compactions_in_percentage` | only the flat floor |

  Different limit, different scope, different effect: two cases, cross-linked
  in §1.

- **The over-estimate is load-bearing, not sloppiness.** `getExpectedCompactedFileSize`
  returns the sum of the *inputs* for an ordinary compaction. Since inputs and
  output coexist on disk until the transaction commits, budgeting the input
  size is approximately budgeting the transient peak. Reading it as "a bad
  estimate of the output" misses the point.

- **Fail-open on estimation error** (recorded in §10) is worth carrying into
  other (b) cases: when the verdict is computed in a `try`, check what the
  `catch` does with it. Here an `FSReadError` from the device query produces an
  *allow*.

- **The third `Directories` overload is test-facing.** [`:524-537`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L524-L537)
  takes a `Function<File, FileStore>` and is `@VisibleForTesting`; the
  production path goes through [`:517-521`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L517-L521),
  which supplies `Directories::getFileStore`. That injection point is why the
  unit scaffolding in §9 is as good as it is.
