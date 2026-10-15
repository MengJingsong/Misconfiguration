# repair_disk_headroom_reject_ratio — repair admission on data-disk usage

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | REPAIR_DISK_HEADROOM_REJECT_RATIO-VERIFYDISKHEADROOMTHRESHOLD-REJECTRATIO |
| **Constraint** | `repair_disk_headroom_reject_ratio` — a **configuration entry** ([`Config.java:352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L352), `volatile double`, default `0.0`, commented "disabled by default on 5.0 for backward-compatibility"), **live-settable over JMX only** (no `nodetool` command). The limit at the check is derived from it and the node's data-disk usage ratio, whose denominator `data_disk_usage_max_disk_size` can cap (§4). |
| **Enforcement pattern** | **(b)** — the comparison returns a boolean verdict; two separate decision points read it, one on the coordinator and one on each participant, and both withhold the whole repair. |
| **Capacity check** | [`ActiveRepairService.verifyDiskHeadroomThreshold():655`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L655) — `diskUsage + rejectRatio > 1`, with `diskUsage = DiskUsageMonitor.instance.getDiskUsage()` read at [`:652`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L652). One check site, two callers (grep of the whole tree, 2026-10-15). |
| **Decision point** | (1) **Coordinator:** [`ActiveRepairService.prepareForRepair():667-668`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L667-L668) — `failRepair(...)` throws before the parent session is registered or any `PREPARE_MSG` is sent. (2) **Participant:** [`RepairMessageVerbHandler.doVerb():117-123`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L117-L123) — on `PREPARE_MSG`, fails its participate state and answers with a failure response before registering the parent session. |
| **Allocation site** | Far downstream, reached only after every node admitted: the stream receivers that write the SSTables a repair sends, [`CassandraEntireSSTableStreamReader.read():109`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraEntireSSTableStreamReader.java#L109) (whole-SSTable copy) and [`CassandraStreamReader.read():135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraStreamReader.java#L135) (rebuilt SSTable); for an incremental repair also the anticompaction writer, [`CompactionManager.doAntiCompaction():1748`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L1748). |
| **Related cases** | [`max_space_usable_for_compactions_in_percentage-…`](max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md) — the sibling disk admission check; its second decision point, the stream-receive check ([`StreamSession.java:937`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L937), recorded in `rejected.md` band B), is what an admitted repair meets next (§6a). [`repair_session_space-split-maxsize`](repair_session_space-split-maxsize.md) — same module; its Merkle leaf count sets how much an admitted repair over-streams (§7). The pending-compactions check beside this one ([`:641`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L641)) is refused (count, `rejected.md` band B group 7), not re-judged here. |

```java
// ActiveRepairService.verifyDiskHeadroomThreshold():650-663 — the capacity check.
public boolean verifyDiskHeadroomThreshold(TimeUUID parentRepairSession, PreviewKind previewKind)
{
    double diskUsage = DiskUsageMonitor.instance.getDiskUsage();          // :652, computed now (§4)
    double rejectRatio = getIncrementalRepairDiskHeadroomRejectRatio();   // :653, the knob

    if (diskUsage + rejectRatio > 1)                                      // <-- capacity check, :655
    {
        logger.error("[{}] Rejecting incoming repair, disk usage ({}%) above threshold ({}%)",
                     previewKind.logPrefix(parentRepairSession), String.format("%.2f", diskUsage * 100), String.format("%.2f", (1 - rejectRatio) * 100));
        return false;                                                     // the verdict
    }
    return true;
}
```

```java
// Decision point 1 — ActiveRepairService.prepareForRepair():665-674 (coordinator)
if (!verifyDiskHeadroomThreshold(parentRepairSession, options.getPreviewKind()))
    failRepair(parentRepairSession, "Rejecting incoming repair, disk usage above threshold"); // throws
if (!verifyCompactionsPendingThreshold(parentRepairSession, options.getPreviewKind()))
    failRepair(parentRepairSession, "Rejecting incoming repair, pending compactions above threshold");
long repairedAt = getRepairedAt(options, isForcedRepair);
registerParentRepairSession(...);                                          // :674, only if admitted
// ... then PREPARE_MSG to every live neighbour (:683-689)

// Decision point 2 — RepairMessageVerbHandler.doVerb(), case PREPARE_MSG, :111-123 (participant)
ParticipateState state = new ParticipateState(ctx.clock(), message.from(), prepareMessage);
if (!ctx.repair().register(state)) { replyDedup(...); return; }          // a retry is answered from the state
if (!ctx.repair().verifyDiskHeadroomThreshold(prepareMessage.parentRepairSession, prepareMessage.previewKind))
{
    state.phase.fail("Not enough disk headroom to perform repair");
    sendFailureResponse(message);                                          // FAILURE_RSP, reason UNKNOWN
    return;                                                                // nothing registered
}
```

## 2. Context

Repair makes replicas agree by comparing them and copying over whatever one
of them is missing. Those copies land on disk as new data files, and an
incremental repair also rewrites existing files to separate repaired from
unrepaired data; for a while both versions sit on disk. A node that is
already nearly full can therefore be pushed over the edge by the repair meant
to fix it. This check is the admission gate at the very start of a repair:
each node involved computes what fraction of its data disk is in use
(counting data not yet flushed from memory as if it were on disk) and refuses
to take part if that fraction plus a configured headroom fraction would
exceed the whole. The node that started the repair checks itself before
asking anyone else; every other node checks itself when asked to join. One
refusal anywhere fails the whole repair before anything is compared, copied
or rewritten.

Three things qualify that picture. It is an **admission** check only: once a
repair is admitted nothing looks again, so the repair's own writes can take
the disk past the headroom it was supposed to keep. Its default, `0.0`, is
described as "disabled", but the comparison still runs and refuses when the
measured usage is **above 100 %**, which happens when a configured cap on the
disk size is smaller than the data. And although its JMX name says
"incremental", it guards **every** kind of repair, including previews that
write nothing.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `repair` — repair coordination and participation (`repair/`, `service/ActiveRepairService`), with the usage figure from `service/disk/usage/DiskUsageMonitor` |
| **One-line role** | Repair compares replicas' Merkle trees and streams the ranges that differ; `RepairCoordinator` runs one repair command, `ActiveRepairService` prepares it on the coordinator, and `RepairMessageVerbHandler` answers the coordinator's messages on each participant. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes** — the node's data-disk usage, as a fraction of its data-disk total, against `1 − ratio`; the verdict decides whether the repair, and every byte it would write, starts at all. |
| **Usage-side operand** | `diskUsage` — [`DiskUsageMonitor.getDiskUsage():138-170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L138-L170), recomputed at every call: `(used + memtables) / min(used + usable, cap)`, rounded **up** to 5 decimals (`:169`). |
| **Limit-side operand** | `rejectRatio` — [`ActiveRepairService.java:653`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L653), from `getIncrementalRepairDiskHeadroomRejectRatio()` ([`:1082-1085`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L1082-L1085)). The comparison is written `diskUsage + rejectRatio > 1`, i.e. `diskUsage > 1 − rejectRatio`; the literal `1` is the normalised total (the usage is already a fraction of it), so `rejectRatio` is the only limit term written at the check and names the file (§6.1). |
| **Limit type** | **Configuration entry**, read raw at every check; its effect in bytes is derived: refuse iff `used + memtables > (1 − ratio) × T`, `T = min(used + usable, data_disk_usage_max_disk_size)` (up to the 5-decimal rounding). |

**Limit initialization path.**

1. [`Config.repair_disk_headroom_reject_ratio:352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L352) — declared, `volatile double`, `0.0`. The shipped `cassandra.yaml` has it commented out with "Ratio of disk that must be unused to run repair … Set to 0.0 to disable this check" ([`conf/cassandra.yaml:2327-2331`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L2327-L2331)).
2. **No startup validation.** The only references in `src/` are the getter and setter ([`DatabaseDescriptor.java:5340-5352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L5340-L5352)); the range check `value < 0.0 || value > 1.0` → `IllegalArgumentException` ([`:5347-5350`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L5347-L5350)) is in the **setter only**. A `cassandra.yaml` value is bound to the `Config` field directly and never passes it, so `1.5` or `-0.5` start without complaint (derived from reading; §9 arm V).
3. Live setter: `setIncrementalRepairDiskHeadroomRejectRatio(double)` ([`ActiveRepairService.java:1087-1090`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L1087-L1090)), exposed as the attribute `IncrementalRepairDiskHeadroomRejectRatio` of `org.apache.cassandra.db:type=RepairService` ([`ActiveRepairServiceMBean.java:27`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairServiceMBean.java#L27), [`:78-80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairServiceMBean.java#L78-L80)); it does apply the range check. No `nodetool` command reads or sets it (grep of `src/java/org/apache/cassandra/tools/`, 2026-10-15).
4. Read raw at [`:653`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L653) at every check, so a JMX change applies to the next repair, on that node only.

**The usage operand, exactly** ([`DiskUsageMonitor.java:131-170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L131-L170)):

- **Which directories.** `Directories.dataDirectories.getAllDirectories()` ([`Directories.java:865-871`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L865-L871)): every `data_file_directories` entry plus the local-system directory (`local_system_data_file_directory`, or the first data directory, [`DatabaseDescriptor.java:2748-2765`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2748-L2765)), de-duplicated, grouped by file store ([`DiskUsageMonitor.java:203-219`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L203-L219)). **Not counted:** the commit log, hints, saved caches and `cdc_raw` directories, unless they sit inside a data directory (the yaml's guardrail comment says the same, [`conf/cassandra.yaml:2191-2198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L2191-L2198)). On a shared file system they still shrink `usable`, and so the uncapped total.
- **`used`** — per directory `getRawSize()` = `FileUtils.folderSize(location)` ([`Directories.java:787-790`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L787-L790)), a recursive walk summing each regular file's **apparent** size (`attrs.size()`, [`FileUtils.java:497-529`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileUtils.java#L497-L529)). So it counts snapshots and incremental backups (hard links, **once per link**), sparse or preallocated files at their full length, temporary files of streams and compactions in progress, and any foreign file in a data directory. A walk error other than a vanished file stops the walk and returns the partial sum after an `ERROR` log ([`:515-527`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileUtils.java#L515-L527)).
- **`usable`** — `FileStore.getUsableSpace()` once per file store ([`DiskUsageMonitor.java:146`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L146), [`:247-258`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L247-L258)).
- **`total`** = `used + usable` ([`:154`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L154)), **capped** by the guardrail key `data_disk_usage_max_disk_size` when set ([`:157-159`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L157-L159); [`Config.java:928`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L928), default `null`; at least 1 B and at most the data file stores' total size, [`GuardrailsOptions.java:1248-1261`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/GuardrailsOptions.java#L1248-L1261); live over JMX as `DataDiskUsageMaxDiskSize` of `org.apache.cassandra.db:type=Guardrails`, [`Guardrails.java:1205-1214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java#L1205-L1214)). That cap is what makes the limit reachable on a large disk (§9).
- **Memtables** — `getAllMemtableSize()`, the live data size of every memtable of every table, system tables included ([`:172-186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L172-L186)), added to the numerator **after** the cap ([`:162`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L162)). **The ratio can therefore exceed 1**: when the cap is below `used + memtables`, or when memtables exceed the free space. The upstream test asserts 5.0 for 5 GiB of data under a 1 GiB cap ([`GuardrailDiskUsageTest.java:346-348`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/guardrails/GuardrailDiskUsageTest.java#L346-L348)).
- **Rounding** — `BigDecimal.divide(total, 5, RoundingMode.UP)` ([`:169`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L169)): any non-zero usage is at least `0.00001`, and anything above the total is at least `1.00001`.
- **Never `-1` or `NaN`, and never stale.** The value does not depend on the disk-usage guardrail being enabled or the monitor being started: the monitor's scheduled task ([`:79-96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L79-L96), every 30 s, [`CassandraRelevantProperties.java:200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L200)) only refreshes the guardrail's `localState`, and only while the guardrail's thresholds are set (both default `-1`, [`Config.java:926-927`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L926-L927)). The repair check ignores `localState` and calls `getDiskUsage()` itself, which walks the data directories and queries the file stores at that moment, on the calling thread. A file-store `IOException` becomes a `RuntimeException` ([`:254-257`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L254-L257)) that escapes the check (§10).
- **Node-wide, not per disk.** `used` and `usable` are summed across all data directories and file stores, so with several disks one full disk is averaged with the others.

**The default.** At `0.0` the comparison is `diskUsage > 1`. It is off for any node whose data and memtables fit its (capped) total, and **refuses every repair** once they do not; the upstream test `testPrepareForRepairThrowsExceptionForInsufficientDisk` relies on exactly this, at the default ratio with a usage of 1.5 ([`ActiveRepairServiceTest.java:549-556`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/service/ActiveRepairServiceTest.java#L549-L556)). At the setter's maximum, `1.0`, every repair is refused (any data gives `diskUsage ≥ 0.00001`).

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | (1) [`ActiveRepairService.prepareForRepair():667-668`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L667-L668), on the coordinator, for its own disk; (2) [`RepairMessageVerbHandler.doVerb():117-123`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L117-L123), on each participant, for its own disk. |
| **Verdict** | Pattern (b): the boolean return of `verifyDiskHeadroomThreshold()`, `false` at [`:659`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L659) after the `ERROR` log, `true` at [`:662`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L662). Nothing stores or resets it; each caller reads it once, immediately. |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `diskUsage + rejectRatio ≤ 1` on this node | Coordinator: goes on to the pending-compactions check ([`:670-671`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L670-L671)), registers the parent session ([`:674`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L674)) and sends `PREPARE_MSG` to every live neighbour ([`:683-689`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L683-L689)). Participant: pending-compactions check, then registers the parent session and acks ([`RepairMessageVerbHandler.java:147-156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L147-L156)). |
| **Disallow** | `diskUsage + rejectRatio > 1` on this node | `ERROR` `[[repair #<id>]] Rejecting incoming repair, disk usage (<u>%) above threshold (<1−r>%)` on that node. Coordinator: `RuntimeException("Rejecting incoming repair, disk usage above threshold")`, nothing registered, no message sent. Participant: participate state failed with `Not enough disk headroom to perform repair`, `FAILURE_RSP` to the coordinator, nothing registered; the coordinator fails the repair with `Got negative replies from endpoints [...]`. |

**Every repair kind reaches decision point 1.** All repairs are run by a
`RepairCoordinator`, and it is constructed in two places only:
`StorageService.createRepairTask()` ([`StorageService.java:4862`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L4862)),
behind the JMX `repairAsync` that `nodetool repair` calls
([`:4766-4802`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L4766-L4802);
`StorageServiceMBean` has no other repair entry point at this tag,
[`StorageServiceMBean.java:476`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageServiceMBean.java#L476)),
and the auto-repair scheduler ([`AutoRepairState.java:109-112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/autorepair/AutoRepairState.java#L109-L112)).
`RepairCoordinator.runMayThrow()` calls `prepare()` → `prepareForRepair()` before it
chooses the task ([`RepairCoordinator.java:308-309`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L308-L309),
[`:445-456`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L445-L456)),
and the choice of preview, incremental or full is made only afterwards
([`:458-476`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L458-L476)).
Neither decision point tests the repair's kind; the `previewKind` argument only
picks the log prefix (`[repair #…]` or `[preview repair #…]`,
[`PreviewKind.java:66-74`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/PreviewKind.java#L66-L74)).

| `nodetool repair` form (5.0.9) | What it is ([`Repair.java:111-123`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tools/nodetool/Repair.java#L111-L123), [`:168-178`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tools/nodetool/Repair.java#L168-L178)) | Checked? |
|---|---|---|
| `repair <ks> <t>` | incremental (the default since `-full` is off), parallel | **yes**, coordinator and participants |
| `repair -full`, `-full -pr`, `-st/-et`, `-seq`, `-dcpar`, `-force` | full, the given ranges and parallelism | **yes** |
| `repair --preview` / `--preview -full` / `--validate` | preview `UNREPAIRED` / `ALL` / `REPAIRED`: compares only, streams nothing | **yes** — a repair that would write nothing is refused too |
| `repair --paxos-only` | Paxos state only, no table data | **yes** |
| auto repair | same coordinator | **yes** |
| keyspace with RF < 2, or no ranges | `repair()` returns command 0 without a coordinator ([`StorageService.java:4798-4799`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L4798-L4799)) | **not reached** (nothing to repair) |
| empty keyspace; a range with no neighbours | `SkipRepairException` / `Nothing to repair … - aborting` before `prepare()` ([`RepairCoordinator.java:334-341`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L334-L341), [`:387-397`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L387-L397)) | **not reached** |

No older repair code path at this tag bypasses `prepareForRepair()`. Streaming that
is not repair (bootstrap, rebuild, decommission, hints) never meets this check.

**Two asymmetries worth knowing.** Each node judges only **its own** disk: the
coordinator's check refuses a repair even when every byte would land on the
other replicas, and the coordinator never checks the participants' disks for
them. And a participant's refusal arrives after the coordinator has already
registered its own parent session and participate state ([`:674`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L674), [`:684`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L684)) and, with more than two replicas, after other participants may have accepted; both are bookkeeping only, removed on failure.

## 6. Code path

### 6a. Allow path → object creation

1. [`RepairCoordinator.run():273-288`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L273-L288) → `runMayThrow()`: for a non-preview repair it first writes the parent row to `system_distributed.parent_repair_history` ([`:306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L306), [`:421-427`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L421-L427)), then `prepare(...)` ([`:308`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L308)).
2. [`ActiveRepairService.prepareForRepair():667`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L667) — the coordinator's check admits; [`:674`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L674) registers the parent session; [`:685-689`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L685-L689) sends `PREPARE_MSG` with retries.
3. Each participant, [`RepairMessageVerbHandler.doVerb():117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L117) — its check admits; [`:147-156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L147-L156) accepts, registers the parent session, acks.
4. Coordinator, [`ActiveRepairService.java:750-757`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L750-L757) — the last ack completes the prepare promise; [`RepairCoordinator.java:309`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L309) `flatMap(repair(...))` → [`:458-476`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L458-L476) builds the `PreviewRepairTask`, `IncrementalRepairTask` or `NormalRepairTask`.
5. Validation and sync: each `RepairJob` snapshots the replicas for a non-parallel, non-incremental repair ([`RepairJob.java:162-189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairJob.java#L162-L189)), validates, and syncs the ranges whose trees differ ([`:197-198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairJob.java#L197-L198)); a local sync builds a `StreamPlan(StreamOperation.REPAIR, …)` ([`LocalSyncTask.createStreamPlan():81-85`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/LocalSyncTask.java#L81-L85)).
6. The receiving node, [`StreamSession.prepareAsync():797-798`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L797-L798) — the **other** disk check, `max_space_usable_for_compactions_in_percentage` on the real free space ([`:856-873`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L856-L873), [`:937`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L937)); when it passes it logs `Accepting incoming files newStreamTotalSSTables=… newStreamTotalBytes=…` ([`:999-1004`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L999-L1004)), the bytes about to be written. A preview session does this exchange and stops ([`:814-819`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L814-L819)).
7. **Object creation:** [`CassandraEntireSSTableStreamReader.read():109`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraEntireSSTableStreamReader.java#L109) → `createWriter` ([`:170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraEntireSSTableStreamReader.java#L170)), a zero-copy writer of the sender's components, used when the streamed sections cover the whole SSTable ([`CassandraOutgoingFile.java:181-202`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraOutgoingFile.java#L181-L202)); otherwise [`CassandraStreamReader.read():135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraStreamReader.java#L135) → `createWriter` ([`:176`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraStreamReader.java#L176)), which rebuilds an SSTable. **Incremental repair** also anticompacts on each participant after `PREPARE_CONSISTENT_REQ` ([`LocalSessions.handlePrepareMessage():853`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/consistent/LocalSessions.java#L853), [`:885-886`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/consistent/LocalSessions.java#L885-L886) → [`CompactionManager.doAntiCompaction():1688`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L1688), writer location at [`:1748`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L1748)).

**Nothing on this path re-reads the verdict or the knob.** `verifyDiskHeadroomThreshold()`
has exactly the two callers of §5 (grep, 2026-10-15); validation, sync, streaming and
anticompaction never consult it. The check is **admission only**.

### 6b. Disallow path effect

**A clean refusal of the whole repair, before any validation, snapshot, stream or anticompaction.**

*Coordinator refuses (decision point 1):*

1. [`ActiveRepairService.java:668`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L668) → `failRepair()` ([`:812-822`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L812-L822)): `participateFailed` and `removeParentRepairSession` find nothing (nothing was registered yet), and `RuntimeException("Rejecting incoming repair, disk usage above threshold")` is thrown synchronously out of `prepare()`.
2. [`RepairCoordinator.run():283-287`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L283-L287) catches it: `notifyError()` logs `ERROR … Repair <id> failed:` with the stack trace, increments `StorageMetrics.RepairExceptions` and fires the JMX event `Repair command #<n> failed with error Rejecting incoming repair, disk usage above threshold` ([`:164-184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L164-L184)); `fail()` sends `FAILED_SESSION_MSG` to the participants (which never saw a `PREPARE_MSG`), records the status as `FAILED` and completes with `Repair command #<n> finished with error` ([`:213-240`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L213-L240)).
3. `nodetool` prints both events and fails with `Repair job has failed with the error message: Repair command #<n> failed with error Rejecting incoming repair, disk usage above threshold. Check the logs on the repair participants for further details` ([`RepairRunner.java:126-140`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tools/RepairRunner.java#L126-L140)).

*A participant refuses (decision point 2):*

1. [`RepairMessageVerbHandler.java:120-122`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L120-L122): the participate state, registered at [`:111-116`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L111-L116), fails with `Not enough disk headroom to perform repair` (visible as `failure_cause` in `system_views.repair_participates`, [`LocalRepairTables.java:271-288`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/LocalRepairTables.java#L271-L288)); `sendFailureResponse` sends `FAILURE_RSP` with `RequestFailureReason.UNKNOWN` ([`RepairMessage.java:302-306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/messages/RepairMessage.java#L302-L306), [`Message.java:298-306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/Message.java#L298-L306)). The parent session is not registered, so no later message of this repair can run there.
2. Coordinator: the retry wrapper retries only a `TIMEOUT` ([`RepairMessage.java:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/messages/RepairMessage.java#L204)), so the failure goes straight to [`ActiveRepairService.java:736-747`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L736-L747) (`failedNodes.add`, `ack()`); when all have answered, [`:758-761`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L758-L761) fails the promise with `Got negative replies from endpoints [/<ip>:<port>]` and removes the coordinator's parent session. A retried `PREPARE_MSG` with the same id is answered from the failed state without a new check ([`RepairMessageVerbHandler.java:112-116`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L112-L116)).
3. [`RepairCoordinator.java:310-315`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L310-L315): `notifyError` and `fail` as above, with that message; `nodetool` prints it. The negative-reply text is shared with every other prepare failure, so the participant's own `Rejecting incoming repair, disk usage` line is what identifies this check.

*What has happened before the refusal.* The JMX start notification and, for a
non-preview repair, the `parent_repair_history` row (§6a step 1). Nothing that
writes table data: validation, the repair snapshot, sync streams and
anticompaction all hang off the prepare future
([`RepairCoordinator.java:308-309`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairCoordinator.java#L308-L309)).

**No escape hatch skips the check**, but four things make it weaker than its
yaml comment suggests (§8, §10): admission only; the default refuses above
100 %; the yaml value is not range-checked; the usage counts apparent bytes.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | The SSTables a repair writes on each node that receives differences (whole-SSTable copies or rebuilt SSTables, §6a step 7); for incremental repair the anticompaction outputs; for a sequential full repair the snapshot hard links. Withheld entirely on refusal. |
| **Resource consumed** | **On-disk bytes** in the data directories of the receiving replicas (and transiently of every anticompacting participant). |
| **Rough sizing** | Not derivable from the check, which looks only at present usage. A full repair writes, on each replica, about the bytes of every Merkle leaf range in which it differs from a peer, so a single differing partition costs its whole leaf (over-streaming; the leaf count is `repair_session_space`'s case). A node missing a write-heavy outage receives about the data written meanwhile. Anticompaction of a partly repaired SSTable rewrites it, so up to that SSTable's size is held twice until the originals go. A snapshot costs no blocks but **counts in full** in the next check's `used` (apparent size per link, §4) until it is cleared at session end ([`ActiveRepairService.java:874-895`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L874-L895)). |
| **Lifetime / release** | Streamed SSTables are permanent table data (later compactions may shrink them); anticompaction inputs are released when it commits; repair snapshots are cleared when the parent session is removed. |

## 8. Maximum disk bound

The ratio sets **the usage above which no new repair starts on a node**, not the
usage a repair can reach:

- **What it bounds.** A repair is admitted only while `used + memtables ≤ (1 − r) × T`
  on the coordinator and on every participant, `T = min(used + usable,
  data_disk_usage_max_disk_size)`. Raising `r` lowers that line proportionally;
  lowering it raises the line, and at `0.0` the line is `T` itself.
- **Admission only.** Nothing re-checks an admitted repair (§6a), and the usage side
  does not include the repair's own writes (unlike the compaction sibling, whose check
  adds the proposed write). So the usage a repair can produce is
  `(1 − r) × T + W`, where `W` is what the admitted repairs write: the received
  differences, the anticompaction copies, and, for repairs admitted at the same time,
  the sum of all of them (each is judged against the usage before any of them writes).
  The headroom the yaml calls "must be unused to run repair" is a precondition, not a
  reservation: §9's overshoot arm predicts how far past it one repair goes.
- **Per node.** Each node keeps its own line with its own setting; a repair needs every
  involved node below its line. The bytes go to the replicas that are missing data,
  which are usually not the most loaded ones, so the coordinator's check can refuse a
  repair that would write nothing on the coordinator.
- **The default `0.0`** refuses only when the data directories plus memtables exceed
  `T` — a configured cap below the data, or memtables larger than the free space. A
  node at 99.9 % of a disk with flushed memtables is admitted.
- **What the bytes are.** Apparent sizes of everything under the data directories
  (snapshots, backups, sparse or foreign files, each hard link), summed over all disks,
  plus memtables; not the commit log or hints. The line moves with all of them.
- **Rule 2, in the admission form.** The bound is enforced by not starting the repair, so
  a refused repair writes none of its bytes, and changing `r` changes the usage at which
  repair stops adding data; it does not cap the bytes an admitted repair adds. This is the
  sense in which the band-B pass qualified the check (same shape as the compaction
  admission case); the overshoot arm measures the gap.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test caps each node's data-disk total at 1 GiB with `data_disk_usage_max_disk_size`,
sets the node's usage with a sparse pad file in its data directory, sweeps the ratio over
JMX on a two-node ring, and reads each check's operand, verdict and log line; then it
runs one admitted repair that streams about 256 MiB onto a node just below its line and
measures how far past the line it goes. **Run so far:** none.

### 9a. Procedure and conclusions

**Testability:** config, **live-settable over JMX** (`IncrementalRepairDiskHeadroomRejectRatio`
on `org.apache.cassandra.db:type=RepairService`, range-checked [0, 1]; read at every check,
per node); no `nodetool` command. A yaml value is restart-only and **not range-checked**.
The denominator's cap `data_disk_usage_max_disk_size` is yaml or live JMX (`Guardrails`).

**Claim under test:** a repair starts only if, on the coordinator and on every participant,
`diskUsage + ratio ≤ 1`, with `diskUsage = ⌈(data-directory apparent bytes + memtables) /
min(used + usable, cap)⌉₅`; a refusal withholds every validation, stream and anticompaction
(§6b); an admitted repair is never checked again, so its writes can take usage past `1 −
ratio` (§8); the default `0.0` still refuses above 100 %; and every repair kind is checked.

**How this verifies the hypothesis** (a restatement of the claim, procedure, prediction and
conclusions in this section; it adds none):

- **Hypothesis:** the usage at which a node stops admitting repairs is `(1 − r) × C`; the
  refusing node logs the line and nothing of the repair runs; usage after an admitted repair
  exceeds that line by what the repair streamed.
- **Test:** unit tier: the verdict at the exact boundary for five ratios, the operand on real
  files, both decision points. Cluster tier: two nodes, RF 2, cap `C` = 1 GiB on both; for
  `r` = 0.0 (default), 0.2, 0.5, 0.8 on the participant (arm P) and on the coordinator (arm K),
  one full repair with usage 4 MiB below `(1 − r) C` and one 4 MiB above; six repair kinds above
  the line; a yaml value of 1.5; then the overshoot arm O.
- **Logic:** (1) the Byteman operand line shows the usage the pad set, else the run is invalid;
  (2) below the line the repair is admitted and completes: the limit is **reached** without a
  refusal; (3) above it the refusing node's `Rejecting incoming repair, disk usage` line and no
  validation or stream line for that repair: the **disallow branch** stops it before any write;
  (4) the admitted/refused boundary sits at `(1 − r) C` at all four ratios on both nodes: usage
  **follows the constraint**; (5) arm O: admitted at 4 MiB below the line, the node's data
  directory grows by the streamed bytes and ends above the line with no further check: the
  **admission-only** gap, sized; a second attempt at the same ratio is refused.
- **Refuted if:** a repair above the line is admitted while the operand line shows `u + r > 1`;
  one below is refused by this check; a refused repair validates or streams; the boundary does
  not move with `r`; arm O's admitted repair is stopped or re-checked mid-stream (rows of the
  Conclusions table).

**Procedure:**

1. **Unit tier** — upstream `ActiveRepairServiceTest` (four headroom tests) and
   `GuardrailDiskUsageTest` (the operand); harness tests U1–U4 (9c, 9e).
2. **Cluster tier** — two nodes on one host (9b); phase S (sweep, table empty), phase T (repair
   kinds), arm V (yaml 1.5), then phase O (overshoot).
3. **At each ratio and arm:** control (ratio 0, no pad: admitted) → **scenario A**, usage 4 MiB
   below `(1 − r) C`: admitted → **scenario B**, 4 MiB above: refused → **scenario C**, arm O at
   `r` = 0.5 (admission only) and arm V (the unvalidated yaml).
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: `C` = 1,073,741,824 B (the cap); `δ` = 4,194,304 B (4 MiB);
`L(r) = (1 − r) C`; `U0` = the node's data-directory apparent bytes (pad included) plus its
memtables at the trigger; `u` = the operand the Byteman line prints; `S` = the
`newStreamTotalBytes` of the receiving node's `Accepting incoming files` line.

- **Operand.** `u = ⌈U0 / C⌉₅` within ±0.0005 (about 537 KB of drift in system tables and
  memtables between the harness's measurement and the check). Planned values (`U0 = L ∓ δ`):

  | `r` | `L(r)` (B) | A: `U0 = L − δ`, `u` | B: `U0 = L + δ`, `u` | B's `ERROR` line percentages |
  |---|---|---|---|---|
  | 0.0 (default) | 1,073,741,824 | 0.99610 → admit | 1.00391 → **refuse** | `(100.39%)` above `(100.00%)` |
  | 0.2 | 858,993,459 | 0.79610 → admit | 0.80391 → refuse | `(80.39%)` above `(80.00%)` |
  | 0.5 | 536,870,912 | 0.49610 → admit | 0.50391 → refuse | `(50.39%)` above `(50.00%)` |
  | 0.8 | 214,748,365 | 0.19610 → admit | 0.20391 → refuse | `(20.39%)` above `(20.00%)` |

  The same table for arm P (the knob and pad on node 2, the participant) and arm K (node 1, the
  coordinator); the other node at `r` = 0 with no pad (`u` < 0.01) always admits.
- **Verdict and evidence per refused trigger.** Arm P: one `HDR usage` line on each node (node 1
  admits, node 2 refuses), node 2's `ERROR [[repair #<id>]] Rejecting incoming repair, disk usage
  (…%) above threshold (…%)`, `failure_cause = 'Not enough disk headroom to perform repair'` in
  node 2's `system_views.repair_participates`, `nodetool` exits non-zero with `Got negative
  replies from endpoints [/127.0.0.3:7010]`. Arm K: **one** `HDR usage` line, on node 1 only
  (node 2 is never asked), node 1's `ERROR` line, `nodetool` fails with `Rejecting incoming repair,
  disk usage above threshold`. Both: no `Created … merkle trees`, `Prepared AEService`, `[Stream #`
  or snapshot line carrying that repair's id, and the table directory unchanged.
- **Admitted triggers:** two `HDR usage` lines with `admit=true`, `Repair command #<n> finished`,
  no `Rejecting` line.
- **Phase T (repair kinds)**, node 2 at `r` = 0.5 with `U0 = L + δ` (then node 1 likewise): `repair
  hdr t` (incremental), `repair -full -pr hdr t`, `repair --preview -full hdr t`, `repair --preview
  hdr t`, `repair --validate hdr t`, `repair --paxos-only hdr t` — **all six refused**, the log
  prefix `[[preview repair #` for the three previews and `[[repair #` for the others; no
  anticompaction line (`PendingAntiCompaction`, `Starting anticompaction`) for the incremental one.
- **Arm V:** node 2 started with `repair_disk_headroom_reject_ratio: 1.5` in its yaml **starts
  normally**; the JMX read returns 1.5; a full repair with no pad is refused, the `ERROR` line
  printing a threshold of `(-50.00%)`; a JMX write of 1.5 fails with `Value must be >= 0 and <= 1
  for repair_disk_headroom_reject_ratio`; a JMX write of 0.0 restores admission.
- **Arm O (overshoot).** 4,096 rows of 65,536 random bytes written at `ONE` with node 2 down
  (`compression` off): node 1's table holds 268.4 to 269.5 MB (payload 268,435,456 B plus 0 to
  0.4 % of per-row and index overhead); node 2's holds nothing. A preview at `r` = 0 reports it out
  of sync and node 2 logs `Accepting … newStreamTotalBytes=S_prv`, `S_prv` in that range. Then
  node 2 at `r` = 0.5 with `U0 = L − δ` = 532,676,608 B: **admitted** (`u` = 0.49610 ± 0.0005);
  node 2 logs `Accepting … newStreamTotalBytes=S`, `S = S_prv`; node 2's data directory grows by
  `S` ± 1 MiB and ends at `U1 = U0 + S` ≈ 801.1 to 802.2 MB, `u1` = 0.7461 to 0.7471 (in the
  plan, before any reading); **overshoot past the line `U1 − L = S − δ` ≈ 264.2 to 265.3 MB**
  (0.246 C, 49 % of `L`); the sampler shows usage crossing `L` while streaming with **no** third
  `HDR` line and no abort; node 1's data directory changes by < 1 MiB. Afterwards the same repair
  at `r` = 0.5 is **refused** (`ERROR` `(74.6x%) above threshold (50.00%)`) and at `r` = 0.2 admitted
  (`u1 + 0.2 < 1`).

**Conclusions:**

| Result | Conclusion |
|---|---|
| Every trigger's verdict matches the table on both arms (A admitted, B refused, at 0.0, 0.2, 0.5, 0.8); each refusal has the refusing node's `ERROR` line with the predicted percentages and no validation or stream line; the operand lines are within ±0.0005; phase T refuses all six kinds | **Confirmed** — the check gates admission as traced, on both decision points, for every repair kind. |
| Arm O admitted at `u` ≈ 0.4961, the receiving node grew by `S` ± 1 MiB to above `L` with no further check, and the re-check is refused at 0.5 and admitted at 0.2 | **Admission only, as recorded** — record `U1 − L` (Target-3 material). |
| `r` = 0.0, scenario B refused with `(100.39%)` | **Default refuses above 100 %, as recorded** — the "disabled" default is not off. |
| Arm V starts, reads 1.5 and refuses every repair; the JMX write of 1.5 fails | **Unvalidated yaml, as recorded.** |
| A scenario-B trigger admitted while its operand line shows `u + r > 1` | **Refuted** — the verdict does not reach the decision point; re-read §5. |
| A scenario-A trigger refused with this check's `ERROR` line | **Refuted** for the operand — `getDiskUsage()` does not compute what §4 says; compare the line's `u` with the measured `U0 / C`. |
| A refused repair logs validation, a snapshot, a stream or an anticompaction for its id, or its table directory changes | **Refuted** — the refusal is not before the writes (§6b). |
| The admitted/refused boundary does not move with `r` (the same `U0` gives the same verdict at 0.2 and 0.8) | **Refuted** — not the binding limit; re-read, do not re-run. |
| The operand lines differ from `U0 / C` by more than 0.0005 at most triggers while the verdicts follow them | **Not confirmed** for §4's operand — record the difference (e.g. a directory or file kind §4 left out); the gate itself works. |
| A phase-T kind is admitted above the line | **Refuted** for "every repair kind" — record which kind and its path. |
| Arm O: a third `HDR usage` line during the stream, or the stream aborts with `Rejecting incoming repair` | **Refuted** for "admission only". |
| Arm O: node 2 grows by more than `S` + 1 MiB + 2 % or less than `S` − 1 MiB | **Not confirmed** for the overshoot attribution — record the difference and what wrote it (compaction, a second stream, system tables). |
| A refusal with another message (`pending compactions`, `Endpoint not alive`, `Did not get replies`) | **Not this check** — fix the set-up (9b) and repeat the trigger. |
| `df` free space on the nodes' file system below 2 GiB, the cap read-back not `1073741824B`, the ratio read-back not the value set, an operand or verdict line missing, or node 2 already holding `hdr.t` data before arm O's repair (hints, read repair) | **Invalid run** — fix and repeat that trigger or arm. |

**Why the operand line and the log, not `du` alone:** the pad and the cap make the "disk" partly
virtual (the pad is sparse), so the real-resource reading is the data directory's apparent bytes
(what the check counts), checked against `du -sb`; the operand line ties each reading to this
comparison, and the `ERROR` line is produced by this check alone ([`ActiveRepairService.java:657-658`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L657-L658); the pending-compactions refusal at [`:643-644`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L643-L644) says `pending compactions`). In arm O the blocks are real: `du -sB1` of the table directory follows `S`.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `IncrementalRepairDiskHeadroomRejectRatio` (double) on `org.apache.cassandra.db:type=RepairService`, set per node with the harness `Jmx.java setdouble <port> …`; live. Arm V: `repair_disk_headroom_reject_ratio: 1.5` in node 2's yaml (restart). |
| **Confirm it took effect** | `Jmx.java get` of the attribute after every write; the operand line's `ratio=` field at the check. |
| **Capacity values** | `r` = 0.0 (default), 0.2, 0.5, 0.8; with `C` = 1 GiB these put the line at 1,073,741,824 · 858,993,459 · 536,870,912 · 214,748,365 B (9a's table). Arm V: 1.5. Arm O: 0.5, then 0.2. |
| **Scope** | Per node, node-wide over all keyspaces and data directories. Two nodes; each judged by itself (arm P: node 2, arm K: node 1). |
| **Level** | Both. Unit: upstream [`ActiveRepairServiceTest.java:523-556`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/service/ActiveRepairServiceTest.java#L523-L556) (default, full disk, sufficient disk, `prepareForRepair` throws), [`GuardrailDiskUsageTest.java:201-230`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/guardrails/GuardrailDiskUsageTest.java#L201-L230) (memtables counted), [`:319-384`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/guardrails/GuardrailDiskUsageTest.java#L319-L384) (the cap, ratios above 1); harness U1–U4. No upstream test drives the participant's decision point. |

**Cluster layout.** Both nodes on one host (`pc57`), on loopback addresses as the
`repair_session_space` harness ran them
([`harness/repair_session_space-split-maxsize/`](../../../stage4-runtime-verification/long-path/harness/repair_session_space-split-maxsize/README.md)):
node 1 `127.0.0.2` (JMX 7102, runs every repair), node 2 `127.0.0.3` (JMX 7103), `num_tokens: 1`,
`initial_token` `-9223372036854775808` and `0`, Murmur3, each with its own `conf/`, data, commit
log, hints and log directories under `~/stage4-hdr/N1|N2/` on the host's local disk. The data
directory is `~/stage4-hdr/N<i>/data` — a subdirectory, never a file-system root (an unreadable
`lost+found` would stop `folderSize`'s walk, §4). Keyspace `hdr` with `SimpleStrategy`,
`replication_factor` 2; table `hdr.t (pk int PRIMARY KEY, v blob) WITH compression = {'enabled':
'false'} AND compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}`.

**The cap and the pad.** With `data_disk_usage_max_disk_size: 1GiB` and more than 1 GiB free,
`T` = `C` exactly, independent of the other node, the commit logs and anything else on the file
system. The usage is set with a **sparse pad file** `~/stage4-hdr/N<i>/data/hdr-pad.bin`
(`truncate -s <bytes>`): `folderSize` counts its apparent length, it uses no blocks, and the
compaction and stream checks (which read real free space) do not see it. The pad is created only
while the node runs (it is not an SSTable component; nothing reads it) and removed before a stop.
Pad length for a target `U0`: `U0 − D`, where `D` is the data directory's apparent bytes without
the pad, measured just before the trigger with the harness walk (sum of `st_size` of every regular
file under the directory, no symlinks followed: `folderSize`'s rule), after `nodetool flush` on
that node.

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `data_disk_usage_max_disk_size` | `1GiB` on both | Fixes `T` = `C`; validated against the file store's size at start ([`GuardrailsOptions.java:86-87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/GuardrailsOptions.java#L86-L87)). |
| `data_disk_usage_percentage_warn/fail_threshold` | `-1` (default) | The guardrail stays off, so the node keeps accepting writes and its monitor never runs. |
| `hinted_handoff_enabled` | `false` ([`Config.java:112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L112), default `true`) | Otherwise node 1 hands arm O's writes to node 2 when it returns, and the repair finds nothing to stream. |
| `reject_repair_compaction_threshold` | default (`Integer.MAX_VALUE`, [`Config.java:347`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L347)) | The neighbouring check never refuses. |
| `max_space_usable_for_compactions_in_percentage`, `skip_stream_disk_space_check` | defaults (0.95, `false`, [`Config.java:701`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L701)) | The stream check passes on the real free space; its `Accepting` line is arm O's byte count. |
| `stream_entire_sstables` | `true` (default, [`Config.java:699`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L699)) | Either stream path is fine (9a's tolerance); recorded, not varied. |
| Repair command | `bin/nodetool -p 7102 repair -full hdr t` (parallel: no snapshot) unless phase T says otherwise | `-seq` snapshots every replica ([`RepairJob.java:162-189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairJob.java#L162-L189)) and the links would count in the next check (§7). |
| `MAX_HEAP_SIZE` | `2G` each | Repeatability. |
| Reads of `hdr.t` | none before arm O's repair | A read at more than `ONE` could read-repair node 2. |

**Controls:** an idle 30 s with both nodes up, ratio 0, no pad: no `HDR` line; before every
ratio, a full repair at ratio 0 with no pad (admitted); arm K is the control for arm P (the same
values on the other decision point); arm O's preview at ratio 0 is the control for its stream size.

**Reset between triggers:** set the ratio back to 0.0 on both nodes, remove the pad, flush both.
Between phases nothing else; between arm V and phase O restart node 2 with the yaml line removed.
After the run: stop both nodes, keep `logs/`, remove `~/stage4-hdr/`.

### 9c. Workload

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `RepairHeadroomCheckTest.java` | Unit, package `org.apache.cassandra.service`, set-up as `ActiveRepairServiceTest` (`SchemaLoader.prepareServer()`, a Mockito `DiskUsageMonitor` assigned to `DiskUsageMonitor.instance`, restored in `@After`): U1, U2, U4a (9e). |
| `RepairHeadroomVerbTest.java` | Unit, package `org.apache.cassandra.repair`, set-up as [`RepairMessageVerbHandlerOutOfRangeTest.java:81-89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/repair/RepairMessageVerbHandlerOutOfRangeTest.java#L81-L89) and its `tryPrepareExpectingSuccess` ([`:224-242`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/repair/RepairMessageVerbHandlerOutOfRangeTest.java#L224-L242)): U4b. |
| `DiskUsageOperandTest.java` | Unit, package `org.apache.cassandra.service.disk.usage`: U3, a real `DiskUsageMonitor` over a temporary directory through its test constructor ([`DiskUsageMonitor.java:70-74`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L70-L74)). |
| `headroom.btm` | Byteman, observation only, written to `-Dstage4.trace=<N>/hdr.trace`: (1) `AFTER INVOKE getDiskUsage` in `ActiveRepairService.verifyDiskHeadroomThreshold`: `HDR usage session=<$1> usage=<$!> ratio=<DatabaseDescriptor.getRepairDiskHeadroomRejectRatio()> ms=<time>`; (2) `AT EXIT` of the same method: `HDR verdict session=<$1> admit=<$!>`; (3) `AT INVOKE verifyDiskHeadroomThreshold` in `ActiveRepairService.prepareForRepair`: `HDR caller=coordinator`; (4) the same in `RepairMessageVerbHandler.doVerb`: `HDR caller=participant`. Loaded at each node's start (`-javaagent:…byteman-4.0.20.jar=script:…`, no listener, `JVM_EXTRA_OPTS` scoped to the `bin/cassandra` command). |
| `Jmx.java` | The `repair_session_space` harness's client plus `setdouble` and `setstring` (with read-back), and a `get` of several attributes per JVM start. |
| `make-node-yaml.sh <N1\|N2> [k=v …]` | Per-node `conf/` (loopback address, JMX port, token, directories, the 9b hold-fixed lines), adapted from the `repair_session_space` harness. |
| `cluster-run.py <label>` | Labels `setup`, `idle`, `sweep-p`, `sweep-k`, `types`, `valid`, `load`, `overshoot`, `down`. Per trigger: flush, walk, pad, ratio write and read-back, `nodetool` with exit code, log and trace segments between byte offsets, `repair_participates` rows, the table directories' listing; `EXPECTED:` lines in `~/stage4-logs/hdr/<label>/summary.txt`, `triggers.csv`, `samples.csv`, `session.log`; stops both nodes on a failed instrument check. Keeps each label's raw logs (the `repair_session_space` run lost arm M's raw files to the next label's wipe). |
| `unit-run.sh` | Runs the two upstream classes and the three harness classes; logs to `~/stage4-logs/hdr/unit/`. |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.service.ActiveRepairServiceTest
ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.GuardrailDiskUsageTest
cp <harness>/RepairHeadroomCheckTest.java test/unit/org/apache/cassandra/service/
cp <harness>/RepairHeadroomVerbTest.java test/unit/org/apache/cassandra/repair/
cp <harness>/DiskUsageOperandTest.java test/unit/org/apache/cassandra/service/disk/usage/
ant testsome -Dtest.name=org.apache.cassandra.service.RepairHeadroomCheckTest
ant testsome -Dtest.name=org.apache.cassandra.repair.RepairHeadroomVerbTest
ant testsome -Dtest.name=org.apache.cassandra.service.disk.usage.DiskUsageOperandTest

# cluster tier, one trigger (cluster-run.py does all of it; arm P, r = 0.5, scenario B shown)
bin/nodetool -p 7103 flush
java -cp <harness> Jmx setdouble 7103 'org.apache.cassandra.db:type=RepairService' IncrementalRepairDiskHeadroomRejectRatio 0.5
truncate -s $(( 536870912 + 4194304 - <D of node 2> )) ~/stage4-hdr/N2/data/hdr-pad.bin
bin/nodetool -p 7102 repair -full hdr t; echo "exit=$?"
```

**Arm O data.** With node 2 stopped (`bin/nodetool -p 7103 stopdaemon`, then `nodetool -p 7102
status` shows it `DN`), `cluster-run.py load` writes `pk` 0…4095, each `v` = 65,536 bytes from
`random.Random(42).randbytes`, through the bundled Python driver (protocol 5, a white-list policy
on `127.0.0.2`, `ConsistencyLevel.ONE`, prepared insert), then `bin/nodetool -p 7102 flush hdr t`,
starts node 2 and waits for `UN` on both and `statusbinary` `running`.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — the check's `diskUsage` and ratio | `HDR usage … usage= ratio=` in `<N>/hdr.trace`, one per check on that node | Each trigger | The only caller of `getDiskUsage()` while the guardrail is off is this check (§4), but the rule is placed inside `verifyDiskHeadroomThreshold` anyway. Compare with the walk: `(D + pad)/C`, memtables included only in the line. |
| **Verdict and caller** | `HDR verdict … admit=` and `HDR caller=` | Each trigger | A coordinator refusal has no participant lines (node 2 is never asked). |
| **Disallow evidence** | `grep 'Rejecting incoming repair, disk usage' <N>/logs/system.log` (`ERROR`, one line, [`ActiveRepairService.java:657-658`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L657-L658)); node 2: `SELECT id, preview_kind, failure_cause FROM system_views.repair_participates`; `nodetool` output and exit code | Each trigger | The log prefix is doubled (`[[repair #<id>]]`). The coordinator's `Repair <id> failed:` is followed by a stack trace: pair lines, do not grep the message on the `ERROR` line. `Got negative replies` is shared by every prepare failure; only the participant's own line identifies this check. |
| **Nothing started** | For each refused repair id: no `Created .* merkle trees`, `Prepared AEService`, `[Stream #`, `snapshot`, `anticompaction` in either node's `debug.log`; `ls -l` of `data/hdr/t-*/` before and after | Each refused trigger | Read `debug.log` between byte offsets taken around the trigger. |
| **Streamed bytes (arm O)** | Node 2's `Accepting incoming files newStreamTotalSSTables=<n> newStreamTotalBytes=<S>` ([`StreamSession.java:999-1004`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L999-L1004)); the preview's `Total estimated streaming: …` ([`SyncStatSummary.java:267`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/consistent/SyncStatSummary.java#L267), rounded) | Preview and repair | Logged by the receiver before it writes; a preview logs it too and stops. |
| **Real resource** — data-directory bytes | The harness walk (apparent bytes, `folderSize`'s rule) of each node's data directory, plus `du -sb` and `du -sB1` of `data/hdr/`, every 1 s during arm O and before/after every trigger; `df -B1 --output=avail` of the file system | Throughout arm O; around each trigger | Read 8 s after `Repair command #<n> finished` (obsolete files go asynchronously). `du -sb` counts a hard link once, the walk once per link; with no snapshots they agree. The pad is sparse: `du -sB1` excludes it. |

### 9e. Running the scenarios

**Unit tier.** Commands in 9c. Record each assertion and printed value.

1. Upstream `ActiveRepairServiceTest` and `GuardrailDiskUsageTest`: pass or fail.
2. **U1, the boundary** (`RepairHeadroomCheckTest`): with the mocked usage `u` and
   `DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(r)`, `verifyDiskHeadroomThreshold` for
   `r` ∈ {0.0, 0.2, 0.5, 0.8, 1.0} and `u` ∈ {`1 − r − 0.00001`, `1 − r`, `1 − r + 0.00001`},
   each `u` written as a 5-decimal literal (e.g. 0.79999, 0.8, 0.80001 for `r` = 0.2), as
   `getDiskUsage()` produces it: `true`, `true`, `false` (at the boundary these doubles sum to
   exactly 1.0; checked with IEEE doubles for `r` = 0.1 to 0.9); `r` = 1.0 with `u` = 0.00001: `false`; `r` = 0.0 with `u` = 1.0:
   `true`, with 1.00001 and 5.0: `false` (the default refuses above 100 %). Each `false` logs the
   `ERROR` line with the predicted percentages (captured from the logger).
3. **U2, the knob's range:** the setter and the MBean method with −0.01 and 1.01 throw
   `IllegalArgumentException` and leave the value unchanged; 0.0 and 1.0 are accepted; a direct
   write of 1.5 to `DatabaseDescriptor.getRawConfig().repair_disk_headroom_reject_ratio` (what YAML
   binding does) is accepted and makes the check refuse at `u` = 0.00001.
4. **U3, the operand** (`DiskUsageOperandTest`): a temporary directory as the only data directory,
   memtables stubbed to 0 (spy, as `GuardrailDiskUsageTest`), cap 1,048,576 B
   (`Guardrails.instance.setDataDiskUsageMaxDiskSize("1048576B")`): empty → 0.0; a 1-byte file →
   0.00001 (rounding up); a sparse file of 524,288 B apparent → 0.50001 with the 1-byte file;
   a hard link to the sparse file → 1.00001 (counted twice); a file of 1,000 B under
   `snapshots/x/` → 1.00096 (1,049,577 / 1,048,576 rounded up); cap removed → `used / (used + usable)` with `usable` from the real file
   store, within one rounding step of the same figure computed in the test.
5. **U4a, the coordinator** (`RepairHeadroomCheckTest`): `prepareForRepair` with `r` = 0.5 and
   `u` = 0.50001, for `PreviewKind.NONE` and `ALL`, incremental `true` and `false`: throws
   `RuntimeException("Rejecting incoming repair, disk usage above threshold")`, and
   `getParentRepairSession(id)` then throws `NoSuchRepairSessionException` (nothing registered,
   [`ActiveRepairService.java:856-863`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L856-L863)); with `u` = 0.5, one real table and an empty endpoint set, the parent
   session is registered (then removed by the test).
6. **U4b, the participant** (`RepairHeadroomVerbTest`): `RepairMessageVerbHandler.doVerb` on a
   `PREPARE_MSG` (as [`:244-251`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/repair/RepairMessageVerbHandlerOutOfRangeTest.java#L244-L251)) with `r` = 0.5: at `u` = 0.50001, for `PreviewKind.NONE` and
   `ALL`, incremental `true` and `false`, the captured reply is `FAILURE_RSP` with
   `RequestFailureReason.UNKNOWN`, the participate state's failure is `Not enough disk headroom to
   perform repair`, and `getParentRepairSession(id)` throws; a second delivery of the same message
   gets `FAILURE_RSP` with no second `ERROR` line (the dedup path); at `u` = 0.5 the reply is
   `REPAIR_RSP` and the session is registered.

**Before the cluster tier — instrument checks, every run.** Both nodes `UN` and `statusbinary`
`running`; `Jmx.java get` returns the ratio (0.0) and `DataDiskUsageMaxDiskSize` (`1073741824B`)
on both; `df` avail of the file system ≥ 2 GiB; one admitted control repair produces exactly two
`HDR usage` lines (one per node, `admit=true`) whose `usage` is within ±0.0005 of the walk's
`D / C`; the stop rule: a missing trace line or a read-back mismatch stops the run.

**Cluster tier.**

1. **Control** (`setup`, `idle`) — build both `conf/`s, start node 1 then node 2, create the
   keyspace and table, run the instrument checks; 30 s idle: no `HDR` line.
2. **Phase S, arm P** (`sweep-p`) — for `r` = 0.0, 0.2, 0.5, 0.8: control (ratio 0 both, no pad,
   one repair: admitted); set `r` on node 2; scenario A (`U0 = L − δ` on node 2), one repair;
   scenario B (`U0 = L + δ`), one repair; record per trigger the walk `D`, the pad length, the
   read-back, the trace lines, the `ERROR` line, `repair_participates`, `nodetool` output and exit
   code, the table directories; reset (9b).
3. **Phase S, arm K** (`sweep-k`) — the same with the ratio and pad on node 1.
4. **Phase T** (`types`) — node 2 at `r` = 0.5, `U0 = L + δ`: the six commands of 9a; then node 1
   likewise; record as in step 2 plus any anticompaction line.
5. **Arm V** (`valid`) — stop node 2, add `repair_disk_headroom_reject_ratio: 1.5` to its yaml,
   start; read the attribute; one repair (no pad); `Jmx.java setdouble 7103 … 1.5` (expect the
   exception text), then `setdouble … 0.0` and one repair (admitted); stop, remove the line, start.
6. **Arm O** (`load`, `overshoot`) — the arm O data (9c); check node 2's `data/hdr/t-*/` holds no
   `Data.db` and node 1's holds 268.4 to 269.5 MB; preview `repair --preview -full hdr t` at ratio 0
   (record `S_prv`); set node 2 to `r` = 0.5, pad to `U0 = 532,676,608` B; start the sampler; `repair
   -full hdr t`; wait for `finished`, then 8 s; record the trace lines, `S`, the sampler series, the
   final walk and `du` of both nodes; then the same repair at `r` = 0.5 (refused) and at `r` = 0.2
   (admitted).
7. **Stop** (`down`) — remove the pads, `stopdaemon` both, copy the logs.

**Record for stage 4:** both yamls' tails and the JVM options, every command with its exit code,
per trigger the planned `U0`, `D`, pad, read-backs, trace lines, log lines and directory listings,
and arm O's sampler series and stream lines.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — band B, rows `ActiveRepairService.java:655#1` and helper `ActiveRepairService.verifyDiskHeadroomThreshold()` of `stage2-ai-preprocessing/bands.csv` (batches 29 and 37, 2026-09-24), judged qualifying in the band-B pass (2026-10-13, `rejected.md` batch "band B") and queued as `pending.md` item 12. |
| **Filed by / Date** | Claude (AI long path), 2026-10-15. |
| **Line numbers checked** | 2026-10-15, every cited line against the local clone at `cassandra-5.0.9` (`git describe --tags`), by script (each link's file and line range exists, and the key lines' text matches what this file says they hold). |
| **Escape hatch / Target-3 note** | No switch skips the check. Five Target-3 notes: (1) **admission only** — an admitted repair's writes are not counted and nothing re-checks, so usage passes `1 − ratio` by what the repair writes, more with concurrent repairs (§8; arm O sizes it); (2) **the "disabled" default refuses above 100 %** — at `0.0` every repair is refused once data plus memtables exceed the total, e.g. after `data_disk_usage_max_disk_size` is set below the data, a guardrail key whose side effect on repair is not documented (§4); (3) **the yaml value is not range-checked** — `≥ 1` refuses every repair, `< 0` makes refusal need more than 100 % usage (§4, arm V); (4) **apparent-size accounting** — snapshots (e.g. a `-seq` repair's), incremental backups and any hard link count once per link, sparse and foreign files in full, all disks are averaged; (5) **error handling** — a walk error under-counts (fail-open, `FileUtils.java:524-527`), a file-store `IOException` throws out of the check: on the coordinator the repair fails; on a participant it escapes `doVerb` ([`RepairMessageVerbHandler.java:358-369`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L358-L369)) with no reply, so the coordinator waits for its timeout (derived, not traced further). |
| **Stage-4 feedback** | none yet |
| **Notes** | **Corrections to the queue note (`pending.md` item 12), from re-reading the source:** (1) "default `0.0`, i.e. **off**" — not off: the comparison still runs and refuses when `diskUsage > 1`, which `getDiskUsage()` can return (memtables added after the cap; the upstream test uses 1.5 at the default ratio); (2) "range [0, 1] (`DatabaseDescriptor.java:5347`)" — enforced only by the setter (JMX); a yaml value is never validated; (3) "the total capped by `data_disk_usage_max_disk_size` (`:158`)" — the cap is `:157-159` (the `min` is `:159`), and memtables are added to the numerator only, after it; (4) the check is not stale: `getDiskUsage()` walks the data directories at every call, independently of the monitor's 30-s guardrail task and of whether the guardrail is enabled; it never returns `-1` or `NaN`; (5) commit log, hints and saved caches are not counted, snapshots and backups are; (6) "two decision points read it before any streaming or anticompaction" holds, with two additions: a non-preview repair writes its `parent_repair_history` row before the coordinator's check, and a participant's refusal comes after the coordinator registered its own session; (7) confirmed: "admission only" (two callers, grep), the check runs for every repair kind including preview, validate and paxos-only, and RF < 2 or empty keyspaces never reach it. The pending-compactions check beside it (`:641`) is cited from `rejected.md` (band B, group 7), not re-judged. **Naming:** the comparison is `diskUsage + rejectRatio > 1`; the file takes `rejectRatio` as the limit-side operand (the literal `1` is the normalised total). |

---

## 11. Notes

- **Why the cap, not a small file system.** The compaction sibling used a 4 GiB loop mount
  because its limit reads real free space. This check's denominator can be capped
  (`data_disk_usage_max_disk_size`) and its numerator counts apparent sizes, so a capped total
  and a sparse pad set the usage exactly on any large disk, without root, and without the
  stream check (real free space) seeing either. Arm O's streamed bytes are real.
- **The JMX name is historical.** `IncrementalRepairDiskHeadroomRejectRatio` was named for the
  anticompaction space incremental repair needs (the yaml comment still says so), but neither
  decision point tests the repair's kind.
- **A participant on another version** is judged by its own code; a mixed-version ring was not
  considered.
- **Not the band-B refusals in the same file.** `ActiveRepairService.java:641` (pending
  compactions, a count) is in `rejected.md` band B group 7; its streaming twin
  `StreamSession.java:989` is in the same group.
