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

*(Amended 2026-10-07, stage-4 run 1, [results §4](../../../stage4-runtime-verification/long-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md);
the numbers are there.)* Observed on a node with the check switched off on the table
over JMX, at `B` = 52,953,514 B and 8 inputs of 529,529,271 B in all: a **background**
compaction (`nodetool enableautocompaction`, type `COMPACTION`) ran in full — 529,539,178 B
written, 10.0 times the budget, the info line `Compaction space check is disabled` once
and no pass line — while a **major** compaction (`nodetool compact`, type
`MAJOR_COMPACTION`) was refused exactly as with the check on (8 passes, 7 `Reducing scope`,
the abort, nothing written). So the removal above holds for background compactions and
does not reach `nodetool compact` or `compact -s`; the list of operation types that count
as `COMPACTION` is left to stage 3 (§10 Notes).

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test sets `max_space_usable_for_compactions_in_percentage` so that the
compaction budget straddles the size of a known set of SSTables, runs one major
compaction at each value, and counts how the node shrinks, runs or aborts it; a
second variant adds a compaction already in flight. **Run so far:** run 1, unit and cluster
tiers, 2026-10-07, **Confirmed** (H1 as predicted, H2 bypass as recorded;
[results](../../../stage4-runtime-verification/long-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md)). Converted
to this layout 2026-10-06. **Audited 2026-10-07 (stage-4 step 0): Ready after
amendments** ([results §1.1](../../../stage4-runtime-verification/long-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md));
the amendments are marked *(amended 2026-10-07 …)* in 9a to 9e and listed in §10
"Stage-4 feedback". All were made from the source, before any run.

### 9a. Procedure and conclusions

**Testability:** config, **restart-only at the cluster tier**. The `Config` field is
`volatile`, but the only setter is `DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive`
([`:2584-2587`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2584-L2587)),
which no MBean or `nodetool` command calls (grep, 2026-10-06): a node needs a restart
per value, a unit test can set it live. The entry is not in the shipped
`conf/cassandra.yaml`; add it. The escape hatch is separate and live: the JMX operation
`compactionDiskSpaceCheck(boolean)` per table (§6b).

**Claim under test:** before a compaction writes anything, the node refuses to commit
more output than `(usable − min_free_space_per_drive) × pct` on a file store, counting
every compaction already in flight there. A refusal is a **negotiation** (§5): the
largest input is dropped and the check repeats, the compaction runs on the smaller
set, and only when one SSTable still does not fit does the task abort with a
`RuntimeException`. The bound is the compaction write commitment, not the size of a
table; and **lowering `pct` leaves more data on disk, not less**.

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** the admitted compaction size follows the budget `B = (U − 50 MiB) × pct`;
  when `B` is below the inputs' total the node sheds inputs one at a time until the rest
  fits, or aborts; in-flight compactions use up the same budget.
- **Test:** build 8 equal SSTables on a small dedicated filesystem; at each value of
  `pct` (set so `B / total` = 1.5, 0.8, 0.4 and 0.1, plus the default 0.95) run one major
  compaction and read the check's own debug line, the three compaction counters and the
  table's disk use over time; then, at 0.1, switch the check off on the table and trigger a
  major and a background compaction; then compare the same compaction alone and with a
  second, slowed compaction in flight *(both added 2026-10-07)*.
- **Logic:** (1) at the value with `B` above the total, the compaction must run
  unreduced; if it does not the run is invalid. (2) Below it, `CompactionsReduced` and
  `SSTablesDroppedFromCompaction` rise by the arithmetic of the ladder: the decision
  **stops the commitment at the budget**. (3) The number of inputs kept follows `B`:
  usage **follows the constraint**. (4) The debug line prints the exact operand and
  limit at every pass, and the log shows `Reducing scope`: the **disallow branch**
  fired, as opposed to the escape hatch. (5) With another compaction in flight the same
  `pct` refuses what it admitted alone: the in-flight term. (6) Disk use is read as
  *peak* and *final*, because a refusal leaves more on disk.
- **Refuted if:** a compaction runs unreduced with inputs above `B` while the debug line
  shows the check ran; the kept inputs do not follow `B`; the in-flight term does not
  move the boundary; or the hatch lets a major compaction through (rows of the Conclusions
  table).

**Procedure:**

1. **Unit tier** — (a) run upstream `DirectoriesTest`, `CompactionsBytemanTest` and
   `PartialCompactionsTest` (the arithmetic against a mocked `FileStore`; the three disallow
   outcomes forced by Byteman; one real ladder step against a stubbed store).
   (b) Run the harness test `CompactionBudgetTest` (9c): the static
   `Directories.hasDiskSpaceForCompactionsAndStreams(...)` with a stubbed `FileStore`, at
   `pct` 0.95, 0.5, 0.1 and 0.01, at the boundary and one byte past it, with and without an
   in-flight term, and the second knob `min_free_space_per_drive`.
   (c) *(added 2026-10-07)* Run the harness test `CompactionLadderTest` (9c): a real
   `CompactionTask` on 8 real SSTables, the stubbed `FileStore` fixed at a known *U*, at
   `B / total` = 1.5, 0.8, 0.4 and 0.1. (b) drives the check alone; nothing upstream drives the
   decision point and the counters with real sizes, and (c) does, with no disk drift.
2. **Cluster tier** — one node, one data directory on a dedicated 4 GiB loop-mounted
   filesystem. *(Amended 2026-10-07: two node starts per value, because `pct` depends on the
   inputs' measured size and the knob is restart-only — a first start at the default builds
   the inputs, a second carries the value; 9b.)*
3. **At each value:** idle control → **A**, `B` above the inputs' total (admitted) → **B**,
   `B` below it → **C**. *(Amended 2026-10-07: the old text said "the same trigger with the
   JMX escape hatch set on the table"; that trigger cannot reach the hatch, see the
   prediction.)* At the 0.1 value, after C and on the same inputs: **H1** — the hatch set
   on the table, trigger `nodetool compact` again — and **H2** — the hatch still set, trigger
   `nodetool enableautocompaction ks1 t`. An extra arm **I** adds a slowed compaction on a
   second table (9e).
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *s* = one input SSTable's on-disk size (about 64 MiB, equal for
all 8; the estimate used by the check is the sum of the inputs' on-disk lengths, §7, so the
total is `8 s`); *U* = `getUsableSpace()` of the store at the moment of the trigger;
`B = round((U − 50 MiB) × pct)`; *n* = SSTables dropped; *k* = `8 − n` kept.

- **`B ≥ 8 s` (B/total = 1.5, and the default 0.95):** one evaluation, `requested = 8 s` and
  `available = B` in the debug line; no `Reducing scope`; `CompactionsReduced` and
  `CompactionsAborted` unchanged; one output SSTable of about `8 s`; peak disk use of the
  table about `8 s` (inputs) + `8 s` (output).
- **`B < 8 s` and `B ≥ s` (0.8 and 0.4):** the check repeats once per dropped input:
  *n* = `⌈(8 s − B) / s⌉` — **2 at 0.8** (B = 6.4 s: 6 kept), **5 at 0.4** (B = 3.2 s: 3
  kept). `Reducing scope` warnings = *n*; `CompactionsReduced` +1 and
  `SSTablesDroppedFromCompaction` +*n*; the output is about `k s`; the dropped SSTables
  stay as they were. (The largest is dropped each time; with equal sizes the choice does
  not matter.)
- **`B < s` (0.1: B = 0.8 s):** the ladder runs down to one SSTable, which still does not
  fit: `CompactionsAborted` +1, a `RuntimeException` logged with `Not enough space for
  compaction`, no output, no input removed; `SSTablesDroppedFromCompaction` and
  `CompactionsReduced` unchanged (the counters move only after the loop exits normally,
  [`CompactionTask.java:450-454`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L450-L454)).
- **Escape hatch** *(rewritten 2026-10-07, from the source, before any run; the old bullet
  said "the same trigger at 0.1 with the check disabled: the info line, no debug line, the
  compaction runs in full")*. The hatch tests `compactionType == OperationType.COMPACTION`
  ([`CompactionTask.java:386`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L386)),
  and **`nodetool compact` does not produce that type**: it goes
  `ColumnFamilyStore.forceMajorCompaction`
  ([`:2518-2521`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2518-L2521))
  → `CompactionManager.performMaximal`
  ([`:986-989`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L986-L989))
  → `submitMaximal(..., OperationType.MAJOR_COMPACTION)`
  ([`:993`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L993)),
  and `getMaximalTasks` overwrites the task's type with it
  ([`CompactionStrategyManager.java:1091`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionStrategyManager.java#L1091);
  the task's own default is `COMPACTION`,
  [`AbstractCompactionTask.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/AbstractCompactionTask.java#L50)).
  A background task keeps the default type. So at the 0.1 value, with the check disabled on
  the table: **H1** — `nodetool compact` is **still refused exactly as in scenario C**
  (8 debug lines, the abort, `CompactionsAborted` +1, no info line) — the hatch does not
  cover a major compaction; **H2** — `nodetool enableautocompaction ks1 t` (it sets the
  strategy's flag unconditionally and submits a background check,
  [`CompactionStrategyManager.java:932-939`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionStrategyManager.java#L932-L939),
  [`ColumnFamilyStore.java:3013-3019`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3013-L3019))
  makes the strategy take the 8 inputs as one `COMPACTION` task: the info line `Compaction
  space check is disabled - trying to compact all sstables`, **no debug line from that
  task**, the compaction runs in full (output about `8 s`), whatever `pct`.
- **In flight** *(rewritten 2026-10-07, before any run; the old bullet said "at a `pct`
  where `8 s ≤ B < 8 s + R` it is admitted alone and shed when the other runs", with a
  second table of 16 SSTables and `B ≈ 8 s + R/2`, which makes `R ≈ 16 s` and every pass
  fail — the task would abort, not be shed — and had no run of the same compaction alone at
  that `pct`)*. Three equal tables `ks1.t`, `ks1.t2`, `ks1.slow` (8 SSTables each), one
  node start, one `pct` with **`B = R₀ + 3.2 s`** at plan time (`R₀` = the Data.db total of
  `ks1.slow`, about `8 s`, so `B ≈ 11.2 s`):
  (I1) `ks1.t` alone is admitted whole — one pass, `requested = 8 s ≤ B`, *n* = 0;
  (I2) with `ks1.slow` running at `compaction_throughput` 4 MiB/s, a major compaction of
  `ks1.t2` prints a first pass `requested = 8 s + R`, where `R` is the estimator's
  remaining write of the slow task, `total_compressed × (1 − completion_ratio)` of its row in
  `system_views.sstable_tasks`
  ([`CompactionInfo.java:196-205`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionInfo.java#L196-L205),
  [`ActiveCompactions.java:59-76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/ActiveCompactions.java#L59-L76)),
  and keeps `k = ⌊(B − R) / s⌋ = 3`, so **n = 5** (`Reducing scope` ×5, `CompactionsReduced`
  +1, `SSTablesDroppedFromCompaction` +5): the same compaction, admitted whole alone, is
  shed by the in-flight term. As the slow task runs, `R` falls and `U` falls with it, so
  `B − R` rises by about `(1 − pct)` of the slow task's progress (about `0.04 s` per second
  at 4 MiB/s): *n* = 5 holds while `ks1.t2` is triggered within about 15 s of the slow
  task's start; the passes' own `available` and `requested` decide the exact figure.
- **Second knob:** with `pct = 0.95`, raising `min_free_space_per_drive` by *d* moves `B`
  by `0.95 d`, a constant offset independent of *U*; a change of `pct` moves it by
  `(U − 50 MiB) × Δpct`.

**Conclusions:**

| Result | Conclusion |
|---|---|
| The ladder follows the arithmetic at each value (n = 0, 2, 5, abort at 0.1); the debug line shows `available = B` and `requested` as predicted; the in-flight arm sheds what the alone arm admitted whole (n = 5 against 0); H1 is refused and H2 runs in full *(amended 2026-10-07)* | **Confirmed** — the check enforces as traced; the disallow is a negotiation, abort only at its end. |
| As above, but one value is off by one shed input and the debug line explains it (the estimate counts a different size than *s*) | **Confirmed, with an estimator offset** — record the offset; the ceiling is as traced. |
| A compaction runs unreduced with inputs above `B` and the debug line shows the check was evaluated | **Refuted** — the budget does not gate admission. |
| Compactions run in full at every `pct` with no `Reducing scope` and no debug line | **Not confirmed** — the escape hatch is on (the info line) or the task type has no ladder (`partialCompactionsAcceptable()` false) or the check is not reached; read the info line at `CompactionTask.java:388` first. |
| *n* does not change across values 0.8 and 0.4 while the debug line shows `available` changing | **Refuted** — the ladder does not follow the budget; re-read §6b. |
| I2 admits `ks1.t2` whole (*n* = 0, first pass `requested = 8 s`) while `ks1.slow` is in flight and shown running in `sstable_tasks` | **Refuted** for the in-flight term — `estimatedRemainingWriteToDiskBytes` does not reach the check; re-read §4. *(Reworded 2026-10-07; the old row said "the in-flight arm admits the compaction at a `pct` that the arithmetic refuses".)* |
| I2's first pass shows `requested − 8 s` that differs from `R` (the slow task's row in `sstable_tasks`, taken at the debug line's time) by more than 16 MiB, but *n* still follows `available` and `requested` | **Not confirmed** for the estimator — record the offset; the term reaches the check but is not the remaining write the case traced. *(Added 2026-10-07.)* |
| The table's final disk use is lower at lower `pct` | **Not confirmed** — a refusal should leave inputs in place, so disk use should be higher or equal; check that the abort did not delete inputs. |
| H1: `nodetool compact` with the check disabled prints the debug lines and aborts as in C | **As predicted** — the hatch does not cover `MAJOR_COMPACTION`; record it as a limit on the bypass, not a failure. *(Added 2026-10-07; this was the old "Not confirmed" row's situation.)* |
| H1: `nodetool compact` with the check disabled prints the info line, no debug line, and runs in full | **Refuted** for the type restriction — the hatch covers a major compaction; re-read `CompactionTask.java:386` and the call chain in 9a. |
| H2: the info line, no debug line from that task, the compaction runs in full (output about the inputs' total) at the 0.1 value | **Bypass as recorded** — with the check disabled on the table, a background compaction ignores the budget. The bound is removed for `OperationType.COMPACTION`; record the output size. |
| H2: the debug lines or a ladder still appear for that task | **Not confirmed** — the hatch did not take; check that the JMX call went to `ks1.t` (bean name, `Tables`), that the task was a background one (`Compacting (…` with no major-compaction trigger) and that no `nodetool compact` ran in the window. |
| Free space drifted so `B / total` is outside the intended band (the debug line's `available` differs from the computed `B` by more than 1 MiB) | **Invalid run** — recompute `pct` from the current *U* and re-run (9c). |
| The inputs are not 8 equal SSTables of about 64 MiB (`tablestats` shows another count) | **Invalid run** — rebuild the dataset (9c). *(Amended 2026-10-07: "equal" is read on the Data.db lengths, 8 files per table, the largest at most 1.10 times the smallest and each within 10 % of 64 MiB; in the in-flight arm all three tables.)* |
| The planned band does not hold at the trigger: the ladder simulated from the Data.db lengths and the debug line's own `available` gives another *n* than the planned 0, 2, 5 or abort *(added 2026-10-07)* | **Invalid run** — the free space moved between plan and trigger by more than the band allows; re-plan from the current *U* and re-run. |

**Why the debug line and not `du`:** `du` moves for other reasons and, here, in the
opposite direction to the other cases' (a refusal keeps more on disk). Only the line
that prints `available` and `requested` ties a reading to this comparison
([`Directories.java:550`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L550)).

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `max_space_usable_for_compactions_in_percentage` in `cassandra.yaml` (a fraction, `0` to `1`; the default is `.95`, [`Config.java:344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L344)); restart-only at the cluster tier. Unit tier: `DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(double)`. **Second knob** for the cross-check: `min_free_space_per_drive` (default `50MiB`, [`Config.java:339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L339); unit: `setMinFreeSpacePerDriveInMebibytes`). |
| **Confirm it took effect** | The debug line's `has <available> bytes available` equals `round((U − 50 MiB) × pct)` for the `df` figure read just before the trigger, to within 1 MiB (drift) — it is read-back and instrument check in one. Unit: an assertion on the getter. |
| **Capacity values** | `pct` computed per run, `pct = f × total / (U − 50 MiB)` with `f` = 1.5, 0.8, 0.4, 0.1 (so `B / total` = *f*), and the default `0.95` as its own arm (the entry left out of the yaml). Record *U*, `df` and the resolved `pct` for each. *(Amended 2026-10-07: definitions.)* `total` is the **sum of the inputs' `*-Data.db` file lengths**, which is what the check counts (`getExpectedCompactedFileSize` → `SSTableReader.getTotalBytes` → `onDiskLength()`: [`SSTableReader.java:541-547`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java#L541-L547), [`:983-986`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java#L983-L986); for a compressed table the handle's length is the compressed file's length, [`FileHandle.java:397`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java#L397), [`:434`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java#L434)) — not `tablestats`' "Space used" and not `du`, which count every component; *s* = `total / 8`; *U* = `df -B1 --output=avail` of the mount (`getUsableSpace()` is `f_bavail × f_frsize`, the same figure). In the in-flight arm `pct = (R₀ + 3.2 s) / (U − 50 MiB)` (9a). |
| **Order within a run** *(added 2026-10-07)* | `pct` needs the inputs' measured size and the knob is restart-only, so each cluster run has **two node starts**: (1) at the default `pct`: format and mount, start, create the schema, build the inputs, check the dataset, `nodetool drain`, stop; (2) with the node stopped read the Data.db lengths and *U*, compute `pct`, write it to the yaml, start again, set `DEBUG`, wait for the node to settle, read `df` once more (this *U* gives the expected *B*), then trigger. The expected *B* and the simulated ladder use the second *U* and the measured lengths. |
| **Scope** | **Per file store, node-wide across tables**; the in-flight term shares one budget among concurrent compactions on the device. One data directory on one device, so N = 1 and the per-store split ([`Directories.java:528-536`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L528-L536)) does not apply. |
| **Level** | Both. Unit: upstream `DirectoriesTest`, `CompactionsBytemanTest`, `PartialCompactionsTest`; harness `CompactionBudgetTest` (the check) and `CompactionLadderTest` (the decision point; *added 2026-10-07*). Cluster: the real sizes, the ladder, the in-flight term and the hatch. |

**Cluster layout.** The data directory sits on a **dedicated 4 GiB filesystem**, so that
`(U − 50 MiB) × pct` can reach the size of a few SSTables at ordinary `pct`:

```bash
truncate -s 4G ~/stage4-data.img && mkfs.ext4 -q -F ~/stage4-data.img
sudo mkdir -p /mnt/stage4-data && sudo mount -o loop ~/stage4-data.img /mnt/stage4-data
sudo mkdir /mnt/stage4-data/data && sudo chown $USER: /mnt/stage4-data/data
```

and `data_file_directories: [/mnt/stage4-data/data]` in `cassandra.yaml` (the commit log,
hints and saved caches stay on the node's local disk, never `/proj`). *(Amended 2026-10-07:
a subdirectory, because a new ext4 filesystem has a `lost+found` at its root, and `-F` so
that `mkfs` cannot stop to ask about a regular file. `df` and the check read the whole
filesystem, so nothing else changes.)*

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| Table `ks1.t` | `compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}`, compression default, `pk int PRIMARY KEY, v blob`; in the in-flight arm also `ks1.t2` and `ks1.slow`, identical | Autocompaction off, so SSTables accumulate and only the test triggers a compaction. |
| Blob content | random bytes from a seeded generator, 5,120 per row *(added 2026-10-07)* | Incompressible, so the SSTable sizes follow the payload whatever the table's compression is. |
| `compaction_throughput` | `64MiB/s` (default) for the main arms; `nodetool setcompactionthroughput 4` for the slowed compaction in the in-flight arm only, back to 64 once the second compaction's passes are logged *(amended 2026-10-07)* | A slow second compaction stays in flight long enough to be counted. The limiter is shared by all compactions, so the second one is slowed too. |
| `concurrent_compactors` | default | Two compactions must be able to run at once in the in-flight arm. |
| Other tables | none besides `system*` | The in-flight term sums every compaction on the store. |
| `-Xms4G -Xmx4G` | fixed | Not the resource, held for repeatability. |
| Logging | `bin/nodetool setlogginglevel org.apache.cassandra.db.Directories DEBUG` after start, then `getlogginglevels` | The debug line is the operand. *(Amended 2026-10-07: it is **not** off by default at this tag — the shipped `conf/logback.xml` sets `org.apache.cassandra` to DEBUG ([`:132`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/logback.xml#L132)) and its async `debug.log` appender never discards ([`:69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/logback.xml#L69)). The explicit call stays so that the run does not rest on that file; the level read back is recorded.)* |

**Controls:**

- **Idle run** — dataset written, no `nodetool compact`: the baseline disk figure and `df`, and 30 s of the sampler and of `debug.log` with no `FileStore` line from a compaction of `ks1`.
- **Default arm** — `pct = 0.95`, with `8 s` far below `B`: must run unreduced.
- **Escape-hatch controls** *(amended 2026-10-07)* — at 0.1, scenario C is the control for H1 (the same trigger, the check enabled), and H1 is the control for H2 (the same inputs, the same hatch setting, a different task type).
- **Alone control for the in-flight arm** — I1, the same `pct`, nothing in flight.

**Reset between runs:** stop the node, remove `data`, `logs` and `saved_caches` of the clone, unmount and re-create the filesystem (above), then the two starts of "Order within a run". Record `df` at the start of every run. *(Amended 2026-10-07: a fresh filesystem per run instead of emptying it, so `df` starts from the same baseline; the system keyspaces are rebuilt each time.)*

### 9c. Workload

The usage side is compaction output bytes. Build the inputs once per run, then issue one
major compaction.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `CompactionBudgetTest.java` | Unit tier. Package `org.apache.cassandra.db`; calls the `@VisibleForTesting` static `Directories.hasDiskSpaceForCompactionsAndStreams(Map<File,Long>, Map<File,Long>, Function<File,FileStore>)` with a stub `FileStore` (`getUsableSpace()` returns *U*); see 9e. |
| `CompactionLadderTest.java` | *(Added 2026-10-07.)* Unit tier. Package `org.apache.cassandra.db.compaction`; builds 8 real SSTables, wraps the table's `Directories` so that the admission check reads a stub `FileStore` of fixed *U* (the technique of upstream `PartialCompactionsTest`), runs a major compaction at each `B / total`, and compares the debug lines, the counters and the live SSTables with a ladder simulated from the measured lengths; see 9e. |
| `unit-run.sh` | Copies both harness tests into the clone and runs the five unit test classes; logs to `~/stage4-logs/mscp/unit/`. |
| `cluster-run.py <label>` | Cluster tier, labels `d95 f15 f08 f04 f01 inflight`. **Replaces `build-inputs.sh` and `compaction-sampler.sh`** *(amended 2026-10-07)*: formats and mounts the filesystem, runs the two starts of 9b, builds the inputs, samples (every 500 ms: `du -sb` of each table directory, `df`, the rows of `system_views.sstable_tasks`) while the trigger runs, parses `debug.log` between byte offsets, reads the counters, writes `summary.txt` (`EXPECTED:` lines), `passes.csv`, `triggers.csv`, `samples.csv`. It writes the rows itself with the bundled Python driver (protocol 5), 12,800 rows of one seeded random 5 KiB blob per SSTable. |
| `Jmx.java` | A small JMX client (`get` several attributes in one JVM start, `invoke` an operation with a boolean): the counters and `compactionDiskSpaceCheck(false)`. Replaces `nodetool sjk mx`, which starts a JVM per attribute. |
| `make-node-yaml.sh <pct\|default>` | Rebuilds `conf/cassandra.yaml` from the tag plus the data directory and, unless `default`, the knob. |

```bash
# unit tier (on the measured node; unit-run.sh does all of it)
ant testsome -Dtest.name=org.apache.cassandra.db.DirectoriesTest
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.CompactionsBytemanTest
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.PartialCompactionsTest
cp <harness>/CompactionBudgetTest.java test/unit/org/apache/cassandra/db/
cp <harness>/CompactionLadderTest.java test/unit/org/apache/cassandra/db/compaction/
ant testsome -Dtest.name=org.apache.cassandra.db.CompactionBudgetTest
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.CompactionLadderTest

# cluster tier: one script per label, from the clone root (it does the schema, the inputs, the pct, the trigger)
<harness>/cluster-run.py f08
```

*(Amended 2026-10-07, documentation only for the commands: the schema is created by the script, `pct` is computed by it from the Data.db lengths and `df` with the node stopped (9b), and the trigger is `bin/nodetool compact ks1 t`, then for H2 `bin/nodetool enableautocompaction ks1 t`.)*

**Starting values.** Estimates, not measurements:

| Setting | Value | Why |
|---|---|---|
| SSTable size *s* | about 64 MiB, 8 of them (about 512 MiB total) | The ladder has room to show 0, 2 and 5 drops and an abort; `B / total` of 1.5 needs `B` ≈ 768 MiB, within the 4 GiB filesystem's free space (about 3.5 GiB). |
| Writer | `cluster-run.py`: eight times a batch of 12,800 rows of one 5 KiB random blob (distinct keys per SSTable: `pk = 1,000,000 × i + row`), then `nodetool flush ks1 <table>` | Distinct keys keep the SSTables disjoint, so the output is about the inputs' sum. Read the sizes from the Data.db files (9b), and check `nodetool tablestats` for the count. |
| In-flight arm *(rewritten 2026-10-07; the old row was a 16-SSTable `ks1.big`)* | tables `ks1.t`, `ks1.t2`, `ks1.slow`, 8 SSTables of about 64 MiB each (1.5 GiB in all); order: I1 `nodetool compact ks1 t` alone; then `nodetool setcompactionthroughput 4`, `nodetool compact ks1 slow` in the background, wait until its row in `system_views.sstable_tasks` shows progress, then `nodetool compact ks1 t2`; once the second compaction's passes are in `debug.log`, `setcompactionthroughput 64` and wait for both | At 4 MiB/s the slow task needs about 130 s, so it is in flight when `ks1.t2`'s check runs, about 2 s later; its output stays far below the free space (peak about 2.2 GiB of the 3.5 GiB). |
| `pct` at 0.95 | default | `8 s` ≪ *B*. |

**If the sizes drift** (the 8 SSTables are not within 10 % of each other or of 64 MiB, on the Data.db lengths): the script stops; drop the table and rebuild. If there are fewer than 8 Data.db files, an automatic compaction ran: check that autocompaction is off. Record each rebuild.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter and limit** — the operand and the budget, per evaluation | `logs/debug.log`: `FileStore <store> has <available> bytes available, checking if we can write <requested> bytes` ([`Directories.java:550`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L550)), one per pass; it needs the `DEBUG` level on `org.apache.cassandra.db.Directories`. `available` is the limit *B*, `requested` is the usage (new output plus in-flight remaining). | During each trigger | *(Amended 2026-10-07: on by default at this tag — see 9b "Logging"; the harness still sets and reads back the level.)* Each pass of the ladder prints one line: count them. The line names no table and no task, and a background compaction of a `system*` table prints the same line, so the harness reads `debug.log` between byte offsets taken around each trigger and keeps the lines whose `requested` is at least 1 MiB. The log goes to `debug.log`, not `system.log`. |
| **Disallow evidence** | `logs/system.log` `WARN` *(the harness reads the same lines from `debug.log`)*: `FileStore … has only <x> available, but <y> is needed` ([`Directories.java:552-556`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L552-L556)) and `Not enough space for compaction <id>, <n>MiB estimated. Reducing scope.` (one per dropped input); counters `org.apache.cassandra.metrics:type=Compaction,name=CompactionsReduced`, `…name=SSTablesDroppedFromCompaction`, `…name=CompactionsAborted` (attribute `Count`, read with `Jmx.java get`; amended 2026-10-07 from `nodetool sjk mx`, one JVM per attribute). | Before and after each trigger | The counters are node-wide and cumulative: read the difference. `CompactionsReduced` and `SSTablesDroppedFromCompaction` increase only when the loop ends with at least one drop; an abort leaves them unchanged. *(Added 2026-10-07, from the unit instrument run:)* the `WARN` line prints **rounded** sizes (`has only 451.84 MiB available, but 451.84 MiB is needed` for a refusal by a few bytes), so take exact figures from the `DEBUG` line only. |
| **Bypass volume** | H2's info line `Compaction space check is disabled - trying to compact all sstables` ([`CompactionTask.java:388`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L388)), no debug line from that task, and the output size (the Data.db length of the one SSTable left). H1's absence of the info line is the other half. | In H1 and H2 | Per table, not persisted, and `OperationType.COMPACTION` only (§6b): H1 is a major compaction and is not covered. |
| **Real resource** — disk | `cluster-run.py`'s sampler *(amended 2026-10-07 from `compaction-sampler.sh`)*: `du -sb` of each table directory under `/mnt/stage4-data/data/ks1/` every 500 ms; peak and final per trigger; `df` (`statvfs`, `f_bavail × f_frsize`) at the start and end. | Throughout | Peak is inputs plus output for a running compaction; the final figure of a refused compaction is **higher** than a completed one's. Do not read the whole directory (the `system*` keyspaces move). Final figures are read 8 s after the trigger returns: the obsolete inputs are deleted asynchronously. |
| **In-flight remaining** *(added 2026-10-07)* | The same sampler reads `system_views.sstable_tasks` (`table_name`, `kind`, `progress`, `total`, `total_compressed`, `completion_ratio`) every 500 ms; the estimator's `R` is `total_compressed × (1 − progress / total)` of the slow task's row, interpolated to the debug line's timestamp. | I2 | A virtual-table read of the node's own tasks; it is not a `Directories` call and prints no `FileStore` line. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Record pass or fail and the asserted values.

1. Run `DirectoriesTest`, `CompactionsBytemanTest` and `PartialCompactionsTest` (upstream). Record pass or fail.
2. Run `CompactionBudgetTest`, with a stub `FileStore` whose `getUsableSpace()` returns
   *U* = 1,000,000,000 and `min_free_space_per_drive` = 50 MiB:
   1. at `pct` = 0.95, 0.5, 0.1 and 0.01: asserts `getAvailableSpaceForCompactions(store)` equals `round((U − 52428800) × pct)`;
   2. for each, a request of exactly that figure: `true`; one byte more: `false` (the comparison is `available < toWrite`, [`Directories.java:551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L551));
   3. an in-flight term *R*: `hasDiskSpaceForCompactionsAndStreams({f: w}, {f: R}, mapper)` is `true` iff `w + R ≤ B`;
   4. two files mapped to two stores: the verdict is `false` if either fails (aggregation);
   5. the second knob: `min_free_space_per_drive` raised by *d*: *B* falls by `pct × d`, whatever *U*;
   6. *(added 2026-10-07)* the floor: with *U* below `min_free_space_per_drive`, *B* is 0, a request of 0 is `true` and of 1 is `false` ([`Directories.java:568`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L568));
   7. *(added 2026-10-07)* the lines the check logs, captured from the `Directories` logger, read `has <B> bytes available, checking if we can write <w + R> bytes` — the pattern the cluster tier parses — and a refusal adds the `WARN` line.

   Record pass or fail and, per step, the asserted numbers.
3. *(Added 2026-10-07.)* Run `CompactionLadderTest`: the table's `Directories` reads a stub store of fixed *U* = 4 GiB; 8 SSTables of equal row count are written and flushed; `total` and the lengths are read from the readers' `onDiskLength()`; `pct = f × total / (U − 50 MiB)` for `f` = 1.5, 0.8, 0.4, 0.1; the expected ladder is **simulated from the lengths** (drop the largest while the rest exceeds *B*; abort at one); then `submitMaximal` runs and the test asserts, per `f`: (i) the debug lines, in order, carry `available = B` and the simulated `requested`, and there are as many as simulated; (ii) `CompactionsReduced` +1 and `SSTablesDroppedFromCompaction` +*n*, or `CompactionsAborted` +1 with neither of the others; (iii) `Reducing scope` warnings = *n* (7 at the abort); (iv) live SSTables afterwards: 1 for *n* = 0, 1 + *n* otherwise, 8 and the same files at the abort; (v) the simulated *n* equals the planned 0, 2, 5, abort. A mismatch is recorded as `MISMATCH` and the test goes on; it fails at the end.

**Before the cluster tier.** *(Rewritten 2026-10-07: the old step 1 set the hatch on a throw-away table and ran `nodetool compact`, which cannot reach the hatch — 9a.)*

1. **Instrument check, every run.** `Jmx.java get` returns the three counters (the JMX path works); `nodetool getlogginglevels` shows `DEBUG` for `org.apache.cassandra.db.Directories` after the explicit call; the **first trigger** of the run is its own check: the run stops unless its first pass line has `available` within 1 MiB of the *B* computed from the `df` read just before the trigger, and the number of lines with `requested ≥ 1 MiB` in its window equals the simulated number of passes. A missing debug line stops the run. On the 0.1 run the `invoke` of `compactionDiskSpaceCheck(false)` must return without an exception; its effect is read from H2.
2. **Dataset check.** Per table: 8 `*-Data.db` files, the largest at most 1.10 times the smallest, each within 10 % of 64 MiB; `bin/nodetool tablestats` shows 8 SSTables; the `du -sb` of the directory is recorded.

**Cluster tier, for each value of `pct`** (one script run per label: `d95`, `f15`, `f08`, `f04`, `f01`, `inflight`):

1. **Control run** — format and mount (9b), first start at the default, schema, build the inputs (9c), dataset check, drain, stop; read the lengths and *U*, compute `pct`, second start with the knob, `DEBUG`, settle; record `df`, the table's `du -sb` and the three counters, and with no compaction take 30 s of the sampler (idle) and read `debug.log` over the same 30 s.
2. **Scenario A (B/total = 1.5, and the 0.95 arm)** — start the sampler, `bin/nodetool compact ks1 t`, wait for it to finish; record the debug lines, the counters' deltas, the Data.db files afterwards (one, about `8 s`) and the sampler peak and final.
3. **Scenario B (B/total = 0.8, 0.4)** — the same; record every `Reducing scope` warning and the debug line per pass (`requested` falls by one *s* each time).
4. **Scenario C (B/total = 0.1)** — the same; record the abort and `RuntimeException` text, that no output SSTable exists (`ls`), and that the 8 inputs are untouched.
5. **Escape-hatch arms (0.1 only; amended 2026-10-07)** — after C, on the same inputs: `Jmx.java invoke org.apache.cassandra.db:type=Tables,keyspace=ks1,table=t compactionDiskSpaceCheck false`. **H1:** `bin/nodetool compact ks1 t` again; record the debug lines, the abort, the counters and that no info line appears. **H2:** `bin/nodetool enableautocompaction ks1 t`; wait until `ks1/t` holds one Data.db file and `sstable_tasks` shows no task of it (at most 180 s); record the info line, that no debug line with `requested ≥ 1 MiB` came from that task, the output's length and the counters.
6. **In-flight arm (label `inflight`; rewritten 2026-10-07)** — `pct` from 9c's formula. **I1:** `bin/nodetool compact ks1 t`, wait; record the pass (n = 0). **I2:** `bin/nodetool setcompactionthroughput 4`; start `bin/nodetool compact ks1 slow` in the background; read the sampler's `sstable_tasks` rows until the slow task's row shows progress above 0 (every 0.2 s; stop the run after 60 s); read the row; at once `bin/nodetool compact ks1 t2`; poll `debug.log` every 0.5 s until the `Compacting (` line of `ks1/t2` has been written, which follows the passes (stop after 90 s); `bin/nodetool setcompactionthroughput 64`; wait for both. Record the passes of `ks1.t2` (`requested`, `available`), `R` from the sampler at the first pass's time, the warnings, the counters' deltas, the Data.db files of the three tables afterwards.
7. **Stop** — `bin/nodetool stopdaemon`, check nothing is left, keep the mount until the logs are copied (the next run re-creates it).

Stop when each scenario's records are taken; a run where the debug line is missing is invalid (9a).

**Record for stage 4:** the `cassandra.yaml` diff and JVM options in force, the exact commands and `pct` values with their *U* and `df` figures, the debug and warning lines, the counters' deltas, the sampler output, the `ls` of the table directory after each trigger, and the dataset checks, per value.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — surfaced 2026-09-22 by the first stage-2 batch (helper rows inside the four already-triaged subtrees), via `buildCompactionCandidatesForAvailableDiskSpace()`. The row's *reported* comparisons (`size() > 0`, `sstablesRemoved > 0`) are both noise; the method name pointed the read in the right direction and the real check was two calls further in. Judged and parked in `deferred.md` §1b on 2026-09-22 because it is pattern (b); unparked 2026-09-25; written up 2026-09-28. |
| **Filed by / Date** | Claude (`claude-opus-5`) session, 2026-09-28 |
| **Line numbers checked** | 2026-09-28 against the local `cassandra-5.0.9` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). **Two corrections to `deferred.md` §1b**, which had the decision point at `:411` and the throw at `:441`: the `if` is at **412** (its `break` at 413) and the `throw` at **442**. |
| **Escape hatch / Target-3 note** | **Yes, two.** (1) The check is skipped outright when `compactionDiskSpaceCheck` is `false` for the table *and* the operation is `OperationType.COMPACTION` ([`CompactionTask.java:386-390`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L386-L390)); the flag is per table, not persisted, and flipped over JMX. (2) An **exception in the estimation block is treated as allow**: the `catch` at [`:414-419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L414-L419) logs the error and `break`s out of the loop, so a failure to *compute* the check admits the compaction. `getAvailableSpaceForCompactions` throws `FSReadError` when `getUsableSpace` fails, which reaches this catch. Fail-open, not fail-closed. Flagged for Target 3; not pursued here. *(Stage-4 run 1, 2026-10-07: the first hatch behaves as traced for a background compaction and does not reach a major compaction — observed, see the amendment at the end of §8. The second hatch, the `catch` at `:414-419`, was not exercised.)* |
| **Stage-4 feedback** | **§9 converted to the new layout 2026-10-06** (9a to 9e) from the old §9. **Design audit 2026-10-07** (stage-4 README, step 0): **Ready after amendments**; see [results §1.1](../../../stage4-runtime-verification/long-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md). Amended in §9, all dated 2026-10-07 and made from the source before any run: (1) **the escape-hatch arm** (9a procedure, prediction, conclusions, 9d, 9e): `nodetool compact` runs as `MAJOR_COMPACTION` and the hatch covers only `COMPACTION`, so the single arm became **H1** (hatch off + `nodetool compact`: still refused) and **H2** (hatch off + `nodetool enableautocompaction ks1 t`: runs in full); (2) **the in-flight arm** (9a, 9c, 9e): the old sizes (a 16-SSTable second table, `B ≈ 8 s + R/2`) make every pass fail, so the task would abort instead of being shed; now three equal tables, `B = R₀ + 3.2 s`, I1 alone then I2 with the slow task in flight, `R` read from `system_views.sstable_tasks`, n = 5; (3) two node starts per run and the definitions of `total` (Σ Data.db lengths), *s* and *U* (9a, 9b); (4) a unit step 3, `CompactionLadderTest`, and steps 2.6 and 2.7 of `CompactionBudgetTest` (9a, 9c, 9e); (5) documentation (9b to 9e): the `Directories` debug line is on by default at this tag, the sampler reads `sstable_tasks`, `cluster-run.py` replaces two shell scripts, the data directory is a subdirectory, the blobs are random, the `WARN` line prints rounded sizes. **Instrument checks, 2026-10-07 (`pc66`; not readings, §9a frozen before the first cluster one, hash in the results file):** one harness defect in the unit tier (`CompactionLadderTest` left auto-compaction on; fixed, results §3); the cluster script was shaken down once per code path (`f08` scenario B, `f01` scenario C with H1 and H2, `inflight` I1 and I2): every `EXPECTED:` line held, and the first trigger of each run met its own instrument check. Those runs are kept on the node as shakedowns and **run 1 repeats every tier from the beginning**. **Run 1 (2026-10-07, long path, run 1 and self-check, no run 2): both tiers Confirmed** ([results](../../../stage4-runtime-verification/long-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md)) — the first row of 9a's Conclusions table; §9a's hash `f17dad5a37c09c67cd9b61f61d6de22108f881e4` re-computed after the run, unchanged. **Unit:** the three upstream classes and the two harness tests pass (198 harness checks, 0 `MISMATCH`); the ladder at `B / total` 1.5 · 0.8 · 0.4 · 0.1 makes 1 · 3 · 6 · 8 passes (n = 0 · 2 · 5 · abort). **Cluster** (`pc66`, a fresh 4 GiB loop-mounted ext4 per run, two starts, `pct` resolved from the measured sizes): the debug line's `available` equals `round((U − 50 MiB) × pct)` to the byte and its `requested` equals the ladder simulated from the Data.db lengths; n = 0 at the default (B = 5.97 × total) and at 1.5, **2 at 0.8 and 5 at 0.4** (`CompactionsReduced` +1, `SSTablesDroppedFromCompaction` +2 and +5), and at 0.1 eight passes, seven `Reducing scope`, one abort (`CompactionsAborted` +1, nothing written, the eight inputs untouched). The kept inputs set what is written (397.2 MB at 0.8 and 198.6 MB at 0.4, against budgets of 423.6 and 211.8 MB); the table's transient peak above its baseline falls with `pct` (530.7 · 398.0 · 196.1 · 0 MB) and its final disk use stays at the baseline, because these inputs do not shrink when merged. **In flight:** the compaction of `ks1.t` that is admitted whole alone (n = 0) is shed to 3 of its 8 inputs (n = 5) while `ks1.slow` runs at 4 MiB/s, the first pass's `requested − total` = 518,152,293 B against the slow task's remaining write 518,273,295 B read from `system_views.sstable_tasks` (0.02 % apart). **Escape hatch:** H1 (check off over JMX, `nodetool compact`) is refused exactly as with the check on, so the hatch does not cover `MAJOR_COMPACTION`; H2 (check off, `nodetool enableautocompaction ks1 t`) runs in full — the info line once, no pass line, 529,539,178 B written against a budget of 52,953,514 B (10.0 ×): **bypass as recorded**. **Feedback filed:** the amendment at the end of §8 and the Target-3 note (the hatch's reach), the "Run so far" line of §9, and the Notes below; recommendation 8 of the audit is settled by these observations and §6b is not changed. |
| **Notes** | The sibling case's `estimatedWriteSize` and this case's `writeSize` come from the same accessor, `getExpectedCompactedFileSize`. They are not the same quantity at the comparison, though: this case adds the in-flight term and divides by output directory count. **Found while converting §9 (2026-10-06):** the old §9 called the knob "live-settable"; the only setter is `DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive`, which no MBean or `nodetool` command calls, so a node needs a restart per value (corrected in §9a). **Found at the stage-4 audit (2026-10-07), for stage 3 to judge; §5 to §8 are not changed:** §6b and §8 say the hatch "applies only to `OperationType.COMPACTION`"; the consequence is that a **major compaction** (`nodetool compact`, `compact -s`: `MAJOR_COMPACTION`, `CompactionManager.java:993`, `CompactionStrategyManager.java:1091`) **always runs the check, hatch or not**; the hatch bypasses background compactions (the case the instrument run exercised, H2) and, **derived from the source and not run**, user-defined ones, which have no ladder (`partialCompactionsAcceptable()` is `!isUserDefined`, `CompactionTask.java:469-472`) — a refusal there is an abort at the first pass. The ceiling claim in §8 ("the escape hatch removes it entirely for `OperationType.COMPACTION` on any table where JMX has disabled the check") is therefore narrower than it reads for an operator who runs `nodetool compact` after switching the check off. Also: the `WARN` line of a refusal prints rounded sizes, so only the `DEBUG` line carries the exact operands (9d). **Found at stage-4 run 1 (2026-10-07), for stage 3 to judge; §5 to §7 are not changed:** (a) the audit's point above is now observed, not only derived — a major compaction is checked with the hatch off (H1) and a background one is not (H2); user-defined compactions are still derived only. (b) §7 and §11 call the inputs' total a deliberate over-estimate, "since compaction normally shrinks data"; on disjoint, incompressible keys it is not one — the output's Data.db was 9 to 10 KB (0.002 %) **larger** than the inputs' (529,539,300 B against 529,529,016 B at the default), so the figure the gate compares under-counts the output slightly there. No row of 9a depends on it (the output stayed below `B` in every run that wrote, by 6 % to 10 %), but the margin the over-estimate buys depends on the workload, and the "a refusal leaves more on disk" half of the claim could not show in bytes with inputs that do not shrink. (c) An aborted compaction is logged as a `WARN` at `CompactionTask.java:440`, then `ERROR … JVMStabilityInspector.java:70 - Exception in thread …` with the `RuntimeException: Not enough space for compaction` on the **next** line; a `grep` for the message on the `ERROR` line finds nothing. |

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
