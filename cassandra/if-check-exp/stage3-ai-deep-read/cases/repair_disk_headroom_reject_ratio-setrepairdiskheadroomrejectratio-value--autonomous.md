# repair_disk_headroom_reject_ratio setter range check — verification solution  <!-- file: cases/repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:5347`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L5347) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: the check only validates that a ratio handed to a setter lies in [0.0, 1.0]; it caps no memory or disk object. The disk-headroom cap is enforced elsewhere (`ActiveRepairService.java:653-655`). |
| Ground | The check bounds the argument's numeric range, not any stored data; a bad value is rejected before anything is held. The ratio it admits is applied by a different check that reads disk usage. |

**Type:** non-config (hard-coded constant: numeric literals `0.0` and `1.0` in the comparison; the validated value is a JMX/setter argument for the yaml entry `repair_disk_headroom_reject_ratio`, but the literals make the row non-config by the constant rule)

> Link rule applied: the declaration and the if statement are linked.

## A. Constraint trace

**A1. The constraint.** No resource constraint: the check is an argument validation. Compared operands: `value` (the `double` parameter of `setRepairDiskHeadroomRejectRatio`, [`DatabaseDescriptor.java:5345`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L5345)) against the numeric literals `0.0` and `1.0` (no declared constant; literals at `DatabaseDescriptor.java:5347`). The value it protects, the yaml entry `repair_disk_headroom_reject_ratio`, is declared at [`Config.java:352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L352) (`public volatile double ... = 0.0`; unit: fraction of disk; default 0.0 = disabled on 5.0; settable in yaml with restart, and at runtime through JMX `ActiveRepairServiceMBean.setIncrementalRepairDiskHeadroomRejectRatio`, `ActiveRepairServiceMBean.java:80`, `ActiveRepairService.java:1087-1090`). Yaml documentation: `conf/cassandra.yaml:2326-2331`.

**A2. What it caps.** Nothing held in memory or on disk. The comparison bounds only the numeric argument of a setter. The ratio it admits, once stored, is used by `verifyDiskHeadroomThreshold` to reject new repairs when disk usage is too high (a disk-protection check in its own right, a different if statement).

**A3. Mechanism.** Enclosing method: `DatabaseDescriptor.setRepairDiskHeadroomRejectRatio(double)` (`DatabaseDescriptor.java:5345-5352`). The if statement: [`DatabaseDescriptor.java:5347`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L5347) `if (value < 0.0 || value > 1.0)`.
- True: throws `IllegalArgumentException("Value must be >= 0 and <= 1 ...")` (`:5349`); `conf.repair_disk_headroom_reject_ratio` is unchanged.
- False: assigns `conf.repair_disk_headroom_reject_ratio = value` (`:5351`).
Callers: `ActiveRepairService.setIncrementalRepairDiskHeadroomRejectRatio` (`ActiveRepairService.java:1087-1089`, JMX) and `ActiveRepairServiceTest.java:142,534,544`. The yaml value is loaded straight into the `Config` field and does not pass through this setter (no other reference to the field in `src/`; see A4/A5), so the check does not even validate the startup value.
Downstream use: `ActiveRepairService.verifyDiskHeadroomThreshold` (`:649-662`) rejects a repair when `diskUsage + rejectRatio > 1` (`:655`), called from `prepareForRepair` (`:665-666`). That is the real disk-headroom check, not this target.

**A4. Other consumers.** Searched `src/`, `conf/`, `doc/`, `test/` for `repair_disk_headroom_reject_ratio` and `RepairDiskHeadroomRejectRatio`: only `Config.java:352`, the getter/setter at `DatabaseDescriptor.java:5340-5352`, the MBean and `ActiveRepairService` wrappers (`ActiveRepairService.java:653,1082-1090`), the two yaml files, `auto_repair.adoc:338`, and `ActiveRepairServiceTest`. Nothing else consumes the validated value.

**A5. Evidence beyond the source.** `ActiveRepairServiceTest.java:529-547` exercises 1.0 and 0.0 (the boundary values, both accepted). No test passes an out-of-range value. Docs: `doc/modules/cassandra/pages/managing/operating/auto_repair.adoc:338-341`. The source copy has no git history, so none was consulted.

## B. Verification solution

**B1. Claim under test.** The range check at `DatabaseDescriptor.java:5347` does not cap memory or disk usage: it only accepts or rejects a number, and no resource reading changes with the accepted or rejected value at this point.

### B2. Unit tier

n/a: no constraint, the check bounds a setter argument and holds no resource. Evidence in A answers the question instead: A3 shows both outcomes (exception, or one field assignment of 8 bytes) and A2 shows nothing else is held. Optional check: call `setRepairDiskHeadroomRejectRatio` with -0.1, 0.0, 1.0, 1.1 in a test (as `ActiveRepairServiceTest` does) and observe that -0.1 and 1.1 throw and leave the field unchanged.

### B3. Cluster tier

n/a: no constraint, there is no resource quantity at this check to push to a boundary; a node would show only that JMX `setIncrementalRepairDiskHeadroomRejectRatio(1.5)` returns an `IllegalArgumentException` and `getIncrementalRepairDiskHeadroomRejectRatio` stays unchanged. Resource behavior belongs to `verifyDiskHeadroomThreshold` (A3), which is a different target.

**B4. Risks and cleanup.** None; nothing is built or run.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (5325-5352)
- src/java/org/apache/cassandra/config/Config.java (345-353)
- src/java/org/apache/cassandra/service/ActiveRepairService.java (630-700)
- src/java/org/apache/cassandra/service/ActiveRepairServiceMBean.java (grep)
- conf/cassandra.yaml (2318-2332)
- doc/modules/cassandra/pages/managing/operating/auto_repair.adoc (325-345)
- test/unit/org/apache/cassandra/service/ActiveRepairServiceTest.java (525-547, grep)

## D. Stage-4 feedback

`none yet`
