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

**Superseded 2026-10-27 by Amendments U1-U6 below (the tier is run).** Original text: n/a: no constraint, the check bounds a setter argument and holds no resource. Evidence in A answers the question instead: A3 shows both outcomes (exception, or one field assignment of 8 bytes) and A2 shows nothing else is held. Optional check: call `setRepairDiskHeadroomRejectRatio` with -0.1, 0.0, 1.0, 1.1 in a test (as `ActiveRepairServiceTest` does) and observe that -0.1 and 1.1 throw and leave the field unchanged.

### B3. Cluster tier

**Superseded 2026-10-27 by Amendments C1-C6 below (the tier is run).** Original text: n/a: no constraint, there is no resource quantity at this check to push to a boundary; a node would show only that JMX `setIncrementalRepairDiskHeadroomRejectRatio(1.5)` returns an `IllegalArgumentException` and `getIncrementalRepairDiskHeadroomRejectRatio` stays unchanged. Resource behavior belongs to `verifyDiskHeadroomThreshold` (A3), which is a different target.

> **Amendment U1 (2026-10-27, stage-4 audit), why both tiers are run.** The claim (B1) is that the range check changes no resource reading. That is testable: the setter's outcomes, and what the stored value does to the real disk-headroom check (`ActiveRepairService.verifyDiskHeadroomThreshold`, the downstream cap named in A3). A negative claim needs a positive control on the same knob (README, group A), and the closed case `repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided` (both tiers Confirmed) supplies one with its harness: the admission boundary follows the stored ratio to 5 decimals, and a real two-node ring refuses repairs at it. Both tiers are therefore run, reusing that harness for the control. The audit also found a gap in B1's reading of the check: `value < 0.0 || value > 1.0` is false for `NaN`, so `NaN` is accepted (the closed U2 did not test it); the test adds it as a recorded observation.
>
> **Amendment U2 (unit tier, B2a to B2e).** JDK 11, local clone `~/cassandra-run4` (`ant build-test`), tests copied into the clone and run with `ant testsome`: new `HeadroomSetterRangeTest` (harness folder, package `org.apache.cassandra.service`) for the claim; closed `RepairHeadroomCheckTest`, `RepairHeadroomVerbTest`, `DiskUsageOperandTest` (positive control and the real `DiskUsageMonitor`) and upstream `ActiveRepairServiceTest`, `GuardrailDiskUsageTest` (known answers), re-run unchanged. Knob = the setter argument: rejected set {-0.1, 1.1, 1.0000001, `+Infinity`, `-Infinity`, -1e300}; accepted set {0.0, -0.0, 0.5, 1.0, `NaN`}.
>
> **Amendment U3 (unit tier, observables and steps).** S1: store 0.3, then for each value call `DatabaseDescriptor.setRepairDiskHeadroomRejectRatio` and the MBean wrapper `ActiveRepairService.setIncrementalRepairDiskHeadroomRejectRatio`; record exception type and message, the getter, and the thread-allocated bytes of each call. S2: with a mocked `DiskUsageMonitor` returning a chosen usage `u` (as the closed test does), call the real `verifyDiskHeadroomThreshold` at the boundary of the stored ratio: for stored 0.5, `u` = 0.50000 and 0.50001; again after rejected writes of 1.1 and -0.1; for stored `NaN`, `u` = 0.99999 and 5.0. The real resource is not touched in this tier: the check holds no resource, and the control moves the verdict (an admission decision on disk usage), which the cluster tier turns into a real refusal; the gap is named.
>
> **Amendment U4 (unit tier, B2f predictions, stated before any run, from the source).** S1: every rejected value throws `IllegalArgumentException("Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio")` from the setter and from the MBean wrapper, and the getter keeps 0.3; every accepted value is stored exactly (`-0.0` compares equal to 0.0; `NaN` is stored: `NaN < 0.0` and `NaN > 1.0` are both false, `DatabaseDescriptor.java:5347`). The allocation of a call does not depend on the value (a few KiB at most). S2: stored 0.5 admits at `u` = 0.50000 and refuses at 0.50001 with the one `ERROR` line (`ActiveRepairService.java:655-658`); after rejected writes the boundary is unchanged; stored `NaN` admits at both `u` (`u + NaN > 1` is false) with no `ERROR` line. Closed tests: all checks `ok`, 0 mismatches.
>
> **Amendment U5 (unit tier, B2g rows).** (1) All of U4 holds and the closed control passes: **Confirmed** (the check is argument validation; the stored value is the downstream cap). (2) A rejected value changes the getter or the boundary: **Refuted**. (3) An out-of-range value is accepted by the setter (other than `NaN`, which the source predicts is accepted): **Refuted** (re-trace). (4) The control boundary does not move with the stored ratio, or a closed check mismatches: **Not confirmed** (control did not move). (5) `NaN` is rejected: **Not confirmed** (the traced comparison differs from the source). The `NaN` result is an observation about the check, not a verdict row.
>
> **Amendment U6 (unit tier, verdict wording).** Effect on the constraint: **does not cap** (the check); the ratio, once stored, caps through `verifyDiskHeadroomThreshold` (positive control), which the claim already says.
>
> **Amendment C1 (cluster tier, B3).** The tier is the closed two-node ring (loopback 127.0.0.2/.3, JMX 7102/7103, RF 2, `data_disk_usage_max_disk_size: 1073741824B` on both, sparse pad file sets the usage, Byteman trace of the operand and verdict, `~/cassandra-run1` unmodified) with one new label `range`. Labels run, in order: `setup`, `sweep-p` (positive control: ratios 0.0, 0.2, 0.5, 0.8, each with a control repair, an admitted trigger at `U0 = L - 4 MiB` and a refused one at `L + 4 MiB`, ratio on the participant), `range`, `valid`, `down`. Node data on local `/` of `pc32`, never `/proj`; no real data volume is needed (pads are sparse).
>
> **Amendment C2 (cluster tier, new label `range`, B3e).** For the ratio holder N2 (participant) and then N1 (coordinator): store 0.5 through JMX, then attempt writes of -0.1, 1.1 and 1.0000001 (each must fail with `Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio` and read back 0.5), then run the admitted trigger (`U0 = L(0.5) - 4 MiB`) and the refused trigger (`U0 = L(0.5) + 4 MiB`) exactly as the sweep does. Last, on N2, write `NaN` (accepted, read back NaN) and run the trigger at `U0 = L(0.5) + 4 MiB`.
>
> **Amendment C3 (cluster tier, B3f predictions, from the source).** Sweep (closed): at every ratio the trigger below `L` is admitted on both nodes (two `HDR verdict admit=true`, `nodetool repair` exit 0) and the one above `L` is refused by the ratio holder only (`Rejecting incoming repair, disk usage (u%) above threshold ((1-r)%)`, nothing started). Range arm: after the rejected writes the two triggers behave as at 0.5 in the sweep (below admitted, above refused by the holder, for the holder N2 and for N1). `NaN` arm: the trigger above `L(0.5)` is admitted (no `ERROR` line; the stored `NaN` never rejects). `valid` (closed, yaml 1.5): the node starts, JMX reads 1.5, a repair with no pad is refused with threshold (-50.00%), a JMX write of 1.5 fails with the range text and leaves 1.5. No resource changes: the data directories are unchanged by a rejected write (the closed trigger records `dir_changed`).
>
> **Amendment C4 (cluster tier, B3g rows).** (1) All of C3 holds: **Confirmed - does not cap** (the check; the ratio is the downstream, soft, admission cap). (2) A rejected write changes the read-back or the later verdicts: **Refuted**. (3) The sweep boundary does not move with the ratio, or the refusal is not the check's own `ERROR` line: **Not confirmed** (control did not move) / **Invalid** (instrument silent). (4) `NaN` is refused by the setter: **Not confirmed**. (5) An out-of-range write is accepted over JMX: **Refuted**.
>
> **Amendment C5 (cluster tier, controls and cleanup).** Control: the closed `setup` instrument control repair (usage matches the walk) and the per-trigger ratio-0 control. One repair at a time. Stop both nodes with `down`, remove the node folders, and check `ps -eo cmd | grep '[C]assandraDaemon'` on `pc32`.
>
> **Amendment C6 (verdict wording).** Both tiers: effect **does not cap** if Confirmed.

**B4. Risks and cleanup.** None for the original design; see the amendments above for the run (local disk only, nodes stopped and checked).

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
