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

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test sets `max_space_usable_for_compactions_in_percentage` so that the
compaction budget straddles the size of a known set of SSTables, runs one major
compaction at each value, and counts how the node shrinks, runs or aborts it; a
second variant adds a compaction already in flight. **Run so far:** none. Converted
to this layout 2026-10-06.

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
  table's disk use over time; then repeat once with a second, slowed compaction in flight.
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
  shows the check ran; the kept inputs do not follow `B`; or the in-flight term does not
  move the boundary (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) run upstream `DirectoriesTest` and `CompactionsBytemanTest` (the
   arithmetic against a mocked `FileStore`; the three disallow outcomes forced by Byteman).
   (b) Run the harness test `CompactionBudgetTest` (9c): the static
   `Directories.hasDiskSpaceForCompactionsAndStreams(...)` with a stubbed `FileStore`, at
   `pct` 0.95, 0.5, 0.1 and 0.01, at the boundary and one byte past it, with and without an
   in-flight term, and the second knob `min_free_space_per_drive`.
2. **Cluster tier** — one node, one data directory on a dedicated 4 GiB loop-mounted
   filesystem, restarted per value of `pct`.
3. **At each value:** idle control → **A**, `B` above the inputs' total (admitted) → **B**,
   `B` below it → **C**, the same trigger with the JMX escape hatch set on the table. An
   extra arm adds a slowed compaction on a second table (9e).
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
- **Escape hatch:** the same trigger at 0.1 with the check disabled on the table: the info
  line `Compaction space check is disabled - trying to compact all sstables`, no debug
  line, the compaction runs in full (output `8 s`), whatever `pct`.
- **In flight:** with a second compaction writing on the same store, with `R` bytes
  remaining by the estimator, the first compaction's requested figure is `8 s + R` in the
  debug line; at a `pct` where `8 s ≤ B < 8 s + R` it is admitted alone and shed when the
  other runs.
- **Second knob:** with `pct = 0.95`, raising `min_free_space_per_drive` by *d* moves `B`
  by `0.95 d`, a constant offset independent of *U*; a change of `pct` moves it by
  `(U − 50 MiB) × Δpct`.

**Conclusions:**

| Result | Conclusion |
|---|---|
| The ladder follows the arithmetic at each value (n = 0, 2, 5, abort at 0.1); the debug line shows `available = B` and `requested` as predicted; the in-flight arm refuses what the alone arm admitted; the escape-hatch arm runs in full | **Confirmed** — the check enforces as traced; the disallow is a negotiation, abort only at its end. |
| As above, but one value is off by one shed input and the debug line explains it (the estimate counts a different size than *s*) | **Confirmed, with an estimator offset** — record the offset; the ceiling is as traced. |
| A compaction runs unreduced with inputs above `B` and the debug line shows the check was evaluated | **Refuted** — the budget does not gate admission. |
| Compactions run in full at every `pct` with no `Reducing scope` and no debug line | **Not confirmed** — the escape hatch is on (the info line) or the task type has no ladder (`partialCompactionsAcceptable()` false) or the check is not reached; read the info line at `CompactionTask.java:388` first. |
| *n* does not change across values 0.8 and 0.4 while the debug line shows `available` changing | **Refuted** — the ladder does not follow the budget; re-read §6b. |
| The in-flight arm admits the compaction at a `pct` that the arithmetic refuses | **Refuted** for the in-flight term — `estimatedRemainingWriteToDiskBytes` does not reach the check; re-read §4. |
| The table's final disk use is lower at lower `pct` | **Not confirmed** — a refusal should leave inputs in place, so disk use should be higher or equal; check that the abort did not delete inputs. |
| Escape-hatch arm: the debug line still appears | **Not confirmed** — the hatch did not take (it applies only to `OperationType.COMPACTION` and per table); check the table and the operation type. |
| Free space drifted so `B / total` is outside the intended band (the debug line's `available` differs from the computed `B` by more than 1 MiB) | **Invalid run** — recompute `pct` from the current *U* and re-run (9c). |
| The inputs are not 8 equal SSTables of about 64 MiB (`tablestats` shows another count) | **Invalid run** — rebuild the dataset (9c). |

**Why the debug line and not `du`:** `du` moves for other reasons and, here, in the
opposite direction to the other cases' (a refusal keeps more on disk). Only the line
that prints `available` and `requested` ties a reading to this comparison
([`Directories.java:550`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L550)).

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `max_space_usable_for_compactions_in_percentage` in `cassandra.yaml` (a fraction, `0` to `1`; the default is `.95`, [`Config.java:344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L344)); restart-only at the cluster tier. Unit tier: `DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive(double)`. **Second knob** for the cross-check: `min_free_space_per_drive` (default `50MiB`, [`Config.java:339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L339); unit: `setMinFreeSpacePerDriveInMebibytes`). |
| **Confirm it took effect** | The debug line's `has <available> bytes available` equals `round((U − 50 MiB) × pct)` for the `df` figure read just before the trigger, to within 1 MiB (drift) — it is read-back and instrument check in one. Unit: an assertion on the getter. |
| **Capacity values** | `pct` computed per run, `pct = f × 8 s / (U − 50 MiB)` with `f` = 1.5, 0.8, 0.4, 0.1 (so `B / total` = *f*), and the default `0.95` as its own arm. Record *U*, `df` and the resolved `pct` for each. |
| **Scope** | **Per file store, node-wide across tables**; the in-flight term shares one budget among concurrent compactions on the device. One data directory on one device, so N = 1 and the per-store split ([`Directories.java:528-536`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L528-L536)) does not apply. |
| **Level** | Both. Unit: upstream `DirectoriesTest`, `CompactionsBytemanTest`, `PartialCompactionsTest`; harness `CompactionBudgetTest`. Cluster: the real sizes, the ladder and the in-flight term. |

**Cluster layout.** The data directory sits on a **dedicated 4 GiB filesystem**, so that
`(U − 50 MiB) × pct` can reach the size of a few SSTables at ordinary `pct`:

```bash
truncate -s 4G ~/stage4-data.img && mkfs.ext4 -q ~/stage4-data.img
sudo mkdir -p /mnt/stage4-data && sudo mount -o loop ~/stage4-data.img /mnt/stage4-data && sudo chown $USER /mnt/stage4-data
```

and `data_file_directories: [/mnt/stage4-data]` in `cassandra.yaml` (the commit log, hints
and saved caches stay on the node's local disk, never `/proj`).

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| Table `ks1.t` | `compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}`, compression default | Autocompaction off, so SSTables accumulate and only the test triggers a compaction. |
| `compaction_throughput` | `64MiB/s` (default) for the main arms; `nodetool setcompactionthroughput 4` for the slowed compaction in the in-flight arm only | A slow second compaction stays in flight long enough to be counted. |
| `concurrent_compactors` | default | Two compactions must be able to run at once in the in-flight arm. |
| Other tables | none besides `system*` | The in-flight term sums every compaction on the store. |
| `-Xms4G -Xmx4G` | fixed | Not the resource, held for repeatability. |
| Logging | `bin/nodetool setlogginglevel org.apache.cassandra.db.Directories DEBUG` after start | The debug line is the operand; it is off by default. |

**Controls:**

- **Idle run** — dataset written, no `nodetool compact`: the baseline disk figure and `df`.
- **Default arm** — `pct = 0.95`, with `8 s` far below `B`: must run unreduced.
- **Escape-hatch control** — the 0.1 trigger once with `compactionDiskSpaceCheck(false)` (9e).

**Reset between runs:** stop the node, empty `/mnt/stage4-data` and rebuild the 8 SSTables (9c), confirm `df` returns to the baseline, edit `pct`, start. Record `df` at the start of every run.

### 9c. Workload

The usage side is compaction output bytes. Build the inputs once per run, then issue one
major compaction.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `CompactionBudgetTest.java` | Unit tier. Package `org.apache.cassandra.db`; calls the `@VisibleForTesting` static `Directories.hasDiskSpaceForCompactionsAndStreams(Map<File,Long>, Map<File,Long>, Function<File,FileStore>)` with a stub `FileStore` (`getUsableSpace()` returns *U*); see 9e. |
| `build-inputs.sh` | Cluster tier. Writes the 8 equal SSTables of 9c, flushing after each, and prints `tablestats` and `du -sb` of the table directory. |
| `compaction-sampler.sh` | Cluster tier. Every 500 ms prints a timestamp, `du -sb` of the table directory, `df` of the filesystem, and `nodetool compactionstats` lines. |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.db.DirectoriesTest
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.CompactionsBytemanTest
cp <harness>/CompactionBudgetTest.java test/unit/org/apache/cassandra/db/
ant testsome -Dtest.name=org.apache.cassandra.db.CompactionBudgetTest

# cluster tier: schema (once), inputs (every run), trigger
bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE ks1.t (pk int PRIMARY KEY, v blob) WITH compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};"
<harness>/build-inputs.sh                 # 8 flushes of about 64 MiB each
df -B1 /mnt/stage4-data                   # U = the 'Available' column; compute pct = f * 8s / (U - 52428800)
bin/nodetool compact ks1 t                # the trigger
```

**Starting values.** Estimates, not measurements:

| Setting | Value | Why |
|---|---|---|
| SSTable size *s* | about 64 MiB, 8 of them (about 512 MiB total) | The ladder has room to show 0, 2 and 5 drops and an abort; `B / total` of 1.5 needs `B` ≈ 768 MiB, within the 4 GiB filesystem's free space (about 3.5 GiB). |
| Writer | `build-inputs.sh`: eight times a batch of 12,800 rows of one 5 KiB blob (distinct keys per SSTable), then `nodetool flush ks1 t` | Distinct keys keep the SSTables disjoint, so the output is about the inputs' sum. Check the sizes in `tablestats`. |
| In-flight arm | table `ks1.big`: 16 SSTables of 64 MiB (1 GiB), `nodetool setcompactionthroughput 4`, `nodetool compact ks1 big` first; then trigger `ks1.t` | At 4 MiB/s the second compaction stays in flight about 4 minutes; its output reaches 1 GiB, within the 4 GiB filesystem. |
| `pct` at 0.95 | default | `8 s` ≪ *B*. |

**If the sizes drift** (the 8 SSTables are not within 10 % of each other or of 64 MiB): drop the table and rebuild; if `tablestats` shows fewer than 8 SSTables, an automatic compaction ran: check that autocompaction is off. Record each rebuild.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter and limit** — the operand and the budget, per evaluation | `logs/debug.log`: `FileStore <store> has <available> bytes available, checking if we can write <requested> bytes` ([`Directories.java:550`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L550)), one per pass; it needs the `DEBUG` level on `org.apache.cassandra.db.Directories`. `available` is the limit *B*, `requested` is the usage (new output plus in-flight remaining). | During each trigger | Off by default; set it after start. Each pass of the ladder prints one line: count them. The log goes to `debug.log`, not `system.log`. |
| **Disallow evidence** | `logs/system.log` `WARN`: `FileStore … has only <x> available, but <y> is needed` ([`Directories.java:552-556`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L552-L556)) and `Not enough space for compaction <id>, <n>MiB estimated. Reducing scope.` (one per dropped input); counters `org.apache.cassandra.metrics:type=Compaction,name=CompactionsReduced`, `…name=SSTablesDroppedFromCompaction`, `…name=CompactionsAborted` (`nodetool sjk mx -mg -b '<name>' -f Count`). | Before and after each trigger | The counters are node-wide and cumulative: read the difference. `CompactionsReduced` and `SSTablesDroppedFromCompaction` increase only when the loop ends with at least one drop; an abort leaves them unchanged. |
| **Bypass volume** | The escape-hatch arm's info line `Compaction space check is disabled - trying to compact all sstables` ([`CompactionTask.java:388`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L388)), no debug line, and the output size. | In that arm | Per table, not persisted, and `OperationType.COMPACTION` only (§6b). |
| **Real resource** — disk | `compaction-sampler.sh`: `du -sb` of `/mnt/stage4-data/.../ks1/t-*` every 500 ms; peak and final per trigger; `df` at the start and end. | Throughout | Peak is inputs plus output for a running compaction; the final figure of a refused compaction is **higher** than a completed one's. Do not read the whole directory (the `system*` keyspaces move). |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Record pass or fail and the asserted values.

1. Run `DirectoriesTest` and `CompactionsBytemanTest` (upstream). Record pass or fail.
2. Run `CompactionBudgetTest`, with a stub `FileStore` whose `getUsableSpace()` returns
   *U* = 1,000,000,000 and `min_free_space_per_drive` = 50 MiB:
   1. at `pct` = 0.95, 0.5, 0.1 and 0.01: asserts `getAvailableSpaceForCompactions(store)` equals `round((U − 52428800) × pct)`;
   2. for each, a request of exactly that figure: `true`; one byte more: `false` (the comparison is `available < toWrite`, [`Directories.java:551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L551));
   3. an in-flight term *R*: `hasDiskSpaceForCompactionsAndStreams({f: w}, {f: R}, mapper)` is `true` iff `w + R ≤ B`;
   4. two files mapped to two stores: the verdict is `false` if either fails (aggregation);
   5. the second knob: `min_free_space_per_drive` raised by *d*: *B* falls by `pct × d`, whatever *U*.

   Record pass or fail and, per step, the asserted numbers.

**Before the cluster tier.**

1. **Instrument check.** With `DEBUG` set, run one `nodetool compact` on a throw-away table and confirm one `FileStore … has … bytes available` line in `debug.log` whose `available` equals the computed *B*; set `compactionDiskSpaceCheck(false)` on that table over JMX and confirm the info line instead. A missing debug line stops the run.
2. **Dataset check.** `bin/nodetool tablestats ks1.t` shows 8 SSTables; their `du -sb` sum is within 10 % of 512 MiB.

**Cluster tier, for each value of `pct`:**

1. **Control run** — format and mount (9b), start the node with the knob set, set `DEBUG`, build the 8 inputs (9c), record `df`, the table's `du -sb` and the three counters, and with no compaction take 30 s of the sampler (idle).
2. **Scenario A (B/total = 1.5, and the 0.95 arm)** — start `compaction-sampler.sh`, `bin/nodetool compact ks1 t`, wait for it to finish; record the debug lines, the counters' deltas and the sampler peak and final.
3. **Scenario B (B/total = 0.8, 0.4)** — the same; record every `Reducing scope` warning and the debug line per pass (`requested` falls by one *s* each time).
4. **Scenario C (B/total = 0.1)** — the same; record the abort and `RuntimeException` text, that no output SSTable exists (`ls`), and that the 8 inputs are untouched.
5. **Escape-hatch arm** — at the 0.1 value, before the trigger run the JMX operation `compactionDiskSpaceCheck(false)` on `org.apache.cassandra.db:type=Tables,keyspace=ks1,table=t` (`nodetool sjk mx -mc -b '<name>' -op compactionDiskSpaceCheck -a false`), then trigger; record the info line and the output size.
6. **In-flight arm** — at a `pct` with `B ≈ 8 s + R/2` (read *R* from the first `requested` of the slowed compaction's debug line), build `ks1.big`, slow the throughput, start its compaction, wait until `compactionstats` shows it running, then trigger `ks1.t`: record the debug lines (`requested = 8 s + R`), the warnings, the counters.
7. **Stop** — `bin/nodetool stopdaemon`, check nothing is left, unmount and keep the logs.

Stop when each scenario's records are taken; a run where the debug line is missing is invalid (9a).

**Record for stage 4:** the `cassandra.yaml` diff and JVM options in force, the exact commands and `pct` values with their *U* and `df` figures, the debug and warning lines, the counters' deltas, the sampler output, the `ls` of the table directory after each trigger, and the dataset checks, per value.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — surfaced 2026-09-22 by the first stage-2 batch (helper rows inside the four already-triaged subtrees), via `buildCompactionCandidatesForAvailableDiskSpace()`. The row's *reported* comparisons (`size() > 0`, `sstablesRemoved > 0`) are both noise; the method name pointed the read in the right direction and the real check was two calls further in. Judged and parked in `deferred.md` §1b on 2026-09-22 because it is pattern (b); unparked 2026-09-25; written up 2026-09-28. |
| **Filed by / Date** | Claude (`claude-opus-5`) session, 2026-09-28 |
| **Line numbers checked** | 2026-09-28 against the local `cassandra-5.0.9` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). **Two corrections to `deferred.md` §1b**, which had the decision point at `:411` and the throw at `:441`: the `if` is at **412** (its `break` at 413) and the `throw` at **442**. |
| **Escape hatch / Target-3 note** | **Yes, two.** (1) The check is skipped outright when `compactionDiskSpaceCheck` is `false` for the table *and* the operation is `OperationType.COMPACTION` ([`CompactionTask.java:386-390`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L386-L390)); the flag is per table, not persisted, and flipped over JMX. (2) An **exception in the estimation block is treated as allow**: the `catch` at [`:414-419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L414-L419) logs the error and `break`s out of the loop, so a failure to *compute* the check admits the compaction. `getAvailableSpaceForCompactions` throws `FSReadError` when `getUsableSpace` fails, which reaches this catch. Fail-open, not fail-closed. Flagged for Target 3; not pursued here. |
| **Stage-4 feedback** | none yet. **§9 converted to the new layout 2026-10-06** (9a to 9e) from the old §9; not yet audited (stage-4 README, step 0) and not yet run. The new §9 lists its harness as work for step 1. |
| **Notes** | The sibling case's `estimatedWriteSize` and this case's `writeSize` come from the same accessor, `getExpectedCompactedFileSize`. They are not the same quantity at the comparison, though: this case adds the in-flight term and divides by output directory count. **Found while converting §9 (2026-10-06):** the old §9 called the knob "live-settable"; the only setter is `DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive`, which no MBean or `nodetool` command calls, so a node needs a restart per value (corrected in §9a). |

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
