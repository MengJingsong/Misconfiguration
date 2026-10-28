# monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous — stage-4 results  <!-- file: results/monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous`](../../stage3-ai-deep-read/cases/monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit Confirmed (caps); cluster Confirmed (caps) with three numeric predictions missed (recorded in §4.2); no run 2
>
> **Outcome class:** true positive (stage-3 estimate `positive`, stage-4 effect `caps`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 after the audit's amendments, taken before the accepted unit run and cluster starts: `12b563da4d6d156a90f763271734cc2db439a2e0e620a3a4c2251359863e3c04`. File committed at `6e6cf92`; amendments uncommitted. Section D was filled afterwards (final hash differs, only section D changed). |
| **Harness** | `harness/monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous/` (uncommitted): `MonitoringQueueCapTest.java`, `unit-run.sh`, `cluster-run.py`, `chain.sh`, `make-node-yaml.sh`, `Jmx.java` (copied from the sibling harness). |
| **Tiers and values** | Unit: N = 0, 1, 50, 1000, -1, M = 10000 per queue x 3 repetitions, plus M = 100000 for N = 50, 1000, -1. Cluster: N = 0, 50, 5000, -1 (50 and -1 twice), 240 s of `cassandra-stress read` at 1024 threads, `-Xmx1G`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note |
|---|---|---|---|
| A | quantity is memory | Met | A2: heap pinned by queued Operations and their Monitorables (`ReadCommand`); counted by instances, bytes read from histograms. |
| A | knob varied, >= 3 values incl. default | Met | N = 0, 1, 50 (default), 1000, -1 unit; 0, 50, 5000, -1 cluster. The literal `0` is exercised by N = 0 vs 1 (no patched copy needed). |
| A | real resource measured | Partly -> Met | B2d/B3d counted instances; amended to class histograms (full GC) plus live-heap deltas and total live bytes. |
| A | driven to the limit and past it | Partly -> Met | Unit M = 10 to 100 x N. Cluster B3c's workload (unique 2 KiB IN-lists, 200k reads, 64 concurrency) was not shown to reach the queue: the cancellation check runs only in `applyToRow`, so reads of absent partitions never reach it; replaced after a calibration (below). |
| A | positive control | n/a | Positive estimate; N = -1 (unbounded) is the uncapped control in both tiers. |
| B | prediction in numbers | Partly -> Met | B3f's "tens/hundreds of MiB" did not follow from the reachable rate; replaced by instance counts per sample. Rows added for drain and not-reached. |
| B | rows for every outcome | Partly -> Met | As above. |
| C | exact commands | Partly -> Met | Same-package test, `ant build-test`, stress command, yaml and JVM options stated. |
| D | harness / arithmetic | Met after amendment | Calibration probes (below) fixed 240 s x 1024 threads so that the 5000 cap on the Slow queue is reached (measured 80 s). Seed data 83 MB on local disk. |
| D | citations | Met | `MonitoringTask.java:65, 77, 96-99, 194, 209-210, 219-226, 235`, `MonitorableImpl.java:101, 115`, `CassandraRelevantProperties.java:361, 363`, `ReadCommand.java:770-790`, `StorageProxy.java:2205` match the pinned source. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Test in package `org.apache.cassandra.db.monitoring`, `ant build-test` | Applied | Package-private API |
| R2 | Cluster workload that iterates rows: stress `read` over the seeded 200,000 partitions, 1024 threads, 1 ms read and slow timeouts | Applied (amendment B3a-c) | Reach the queue |
| R3 | Replace unreachable byte predictions by instance-count predictions per sample | Applied | Group B |
| R4 | Both queues are offered the same N; totals are 2N | Applied (B1 reading in the amendment) | Clarity |
| R5 | Failed operations are far rarer than slow ones under this workload; a Failed-queue cap above a few thousand needs a longer run | Left for stage 3 | Design note |

**Calibration probes (before the freeze, reading no cap-related quantity)**: three 30 s starts at N = -1 (`run1/calibration/probe1`: 256 threads, default population: 955k stress errors, 38 coordinator timeouts, the reads were of absent keys; `probe2`: 256 threads, population 1..200000: 517 failed, 5259 slow; `probe`: 1024 threads: 1089 failed, 8962 slow). They fixed the stress options and the 240 s duration. They are not part of the readings.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit about 21:15 MDT, cluster chain ended 22:03) |
| Node | `pc29` (`node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-base` from `copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `6e6cf92`, no source modification |
| Case-file / harness commit | `6e6cf92` (uncommitted amendments) / uncommitted |
| Node data | local disk `~/s4-mon` (removed) |
| Full logs | `pc29:~/stage4-logs/mon/` (accepted), `pc29:~/stage4-logs/mon-probes/` (calibration) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | audit | B3c | filed workload does not reach the queue (reads of absent keys never run the cancellation check; no timeouts at default population) | stress `read` with `-pop "dist=UNIFORM(1..200000)"`, 1024 threads, 240 s | applied before the freeze | uncommitted |
| 2 | audit | B2a | `ant jar` does not build the test classes | `ant build-test` | applied before the freeze | uncommitted |

No defect during the accepted tiers.

## 4. Run 1

**Scope:** both tiers, all values above. **Command log:** `run1/unit/summary.txt`, `run1/cluster/<start>/summary.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/run.out`; 18 cells; the three repetitions agree except for the live-heap column). Per queue (the test fills both identically; Stub = 2 x per-queue count).

| N | M | Failed = Slow = queue size | dropped (each queue) | live heap delta (bytes) |
|---|---|---|---|---|
| 0 | 10000 | 0 | 0 | 41,336 to 41,944 |
| 1 | 10000 | 1 | 9999 | 1,398,848 to 1,399,688 (outlier, see part 2) |
| 50 | 10000 / 100000 | 50 | 9950 / 99,950 | 121,880 to 122,016 |
| 1000 | 10000 / 100000 | 1000 | 9000 / 99,000 | 2,432,000 (M = 10000) |
| -1 | 10000 / 100000 | 10000 / 100000 | 0 | 24,320,000 (M = 10000) |

**Cluster tier** (`run1/cluster/<start>/summary.txt`; instances after a full GC at 80 s / 160 s / 243 s; N and both timeouts read back in each start, no drain line in any log).

| N | Failed instances | Slow instances | `SinglePartitionReadCommand` at the end | live bytes at the end (baseline 76.3 MB) |
|---|---|---|---|---|
| 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 | 133,862,816 |
| 50 (r1, r2) | 50 / 50 / 50 both | 50 / 50 / 50 both | 92, 93 | 133,348,896; 133,107,736 |
| 5000 | 1564 / 2346 / 3130 | 5000 / 5000 / 5000 | 8119 | 136,993,120 |
| -1 (r1) | 1486 / 2246 / 3148 | 13,796 / 21,349 / 29,895 | 33,031 | 148,246,840 |
| -1 (r2) | 1620 / 2351 / 3943 | 16,270 / 23,400 / 42,033 | 45,967 | 154,122,256 |

### 4.2 Conclusion and logic

1. **Validity.** The property, the log line `Scheduling monitoring task ... max operations N` and the 1 ms timeouts were read back in every start, and no drain line appeared **[observed: `cluster/*/summary.txt`, `selfcheck.out`]**. The limit was reached: unit queues full for N > 0 and M > N; cluster Slow queue saturated at 50 and at 5000, Failed queue saturated at 50 **[observed]**. Failed queue at N = 5000 was not reached (3130 at the end) **[observed]**. Valid for the unit tier and for the saturated cells.
2. **Readings.** Unit N = 1 live-heap delta (1.4 MB for two 1 KiB stubs) is a baseline artifact (the baseline follows a JIT/GC state change after N = 0); it is not used, the instance counts are exact **[observed: `run.out`]**; N = 1000 and -1 deltas match 2 x N x 1.2 KiB (2.43 MB, 24.3 MB). Cluster N = 0 shows 56 and 40 in-flight `SinglePartitionReadCommand` at the 80 s and 160 s samples and none of the Operation classes **[observed]**.
3. **Matched row.** Unit B2g: *Instances = N (N > 0) / 0 (N = 0), heap delta scales with N* — Confirmed; N = -1 retains M (control) **[observed: all 18 cells, `selfcheck.out` 46 PASS]**; the cap does not move with M (100000 offers: 50 and 1000 retained). Cluster B3g: *Instances capped at N, N = 0 shows none, N = -1 grows while N > 0 is flat* — Confirmed for N = 0 (0 at all samples), N = 50 (50 and 50 from 80 s, two repetitions) and for the Slow queue at N = 5000 (5000 flat from 80 s while N = -1 reaches 29,895 and 42,033, 6 to 8 times the cap); retained bytes follow: live bytes at the end 133.1 to 133.9 MB for N = 0 and 50, 137.0 MB for 5000 (+3.7 MB), 148.2 and 154.1 MB for -1 (+15 and +21 MB) **[observed]**.
4. **Excluded rows.** *Instances exceed N* and *N = 0 retains*: excluded by every cell. *Failed at N = 5000 below 5000*: this row applies (3130 < 5000), so that queue's 5000 limit is **not reached**; the Failed queue's cap is shown at N = 50 only, with N = -1 holding 3148 and 3943 (63 to 79 times the cap of 50) **[observed]**.
5. **Observed vs. inferred.** Inferred: that the bytes pinned scale with the instance count (the per-instance retention) **[inferred: live-byte differences of 3.7 MB for 5000 + 3130 Operations' worth and 15 to 21 MB for -1 are consistent with the pinned `ReadCommand`s, but were not attributed by a heap dump]**.
6. **Deviations and gaps.** **Three numeric predictions of B3f missed:** (a) Failed at N = 5000 "rising towards 5000": it rose to 3130, not 5000 (offered Failed rate in the 243 s runs was 13 to 16 per second, against about 36 per second in the 30 s calibration); (b) N = -1 Failed "above 5000 at the end": 3148 and 3943; (c) N = -1 Slow "above 40,000 at the end": 29,895 (r1, missed) and 42,033 (r2, met). They are not edited; they concern how much the workload offered, not the cap. The "never above N" and "equal to N once saturated" predictions held in every cell. The unit prediction for M = 100000 at N = -1 held. A flush or drain was not exercised (the interval is 600 s).
7. **Core question.** Retention of queued Operations follows N: 0 for N = 0, exactly N per queue for N = 50 (both queues), 1000 and 5000 (Slow queue), and unbounded for N = -1, where the same offered load keeps 6 to 8 times (Slow) or 63 to 79 times (Failed, vs N = 50) more instances and 15 to 21 MB more heap (unit steps 1-3 above and cluster part 3). The disallow branch is seen directly in the unit tier as the dropped counters (M - N).

**Conclusion (one line):** unit: Confirmed — the queue holds at most N Operations per queue and 0 for N = 0; cluster: Confirmed — caps (Slow at 50 and 5000, Failed at 50; Failed at 5000 not reached), three numeric predictions missed as listed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (output `run1/selfcheck.out`): 46 PASS, 0 FAIL; the three missed predictions are printed as INFO.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Read-backs and no-drain checked by the script; Failed N = 5000 "not reached" stated. |
| 2. Readings | yes | N = 1 live-heap outlier stated and not used. |
| 3. Matched row | yes | Saturation values and growth re-parsed from the raw summaries. |
| 4. Excluded rows | yes | The not-reached row applies and is stated. |
| 5. Observed vs. inferred | yes | Only the bytes-per-instance inference. |
| 6. Deviations and gaps | yes | Three prediction misses recorded, not tuned. |
| 7. Core question | yes | Follows B1: cap per queue follows N, N = -1 is the control. |

### 5.2 Run 2?

No — 2026-10-28. The unit tier is exact; the cluster shows the same saturation values in two repetitions; the inferred statement does not carry the verdict.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive.

**Claim tested:** with `cassandra.monitoring_max_operations = N >= 0` the heap retained by queued failed/slow Operations between reports never exceeds about 2 x N Operation objects plus their Monitorables; N = 0 retains none; with N < 0 retention is unbounded.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (instances = N, 0 for N = 0, -1 unbounded) | caps | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (Slow saturates at 50 and 5000, Failed at 50, N = 0 none, N = -1 grows); Failed at 5000 not reached; three numeric predictions missed | caps | run 1 + self-check | 2026-10-28 |

**Positive control:** not required (positive estimate); N = -1 is the uncapped control: 10000 / 100000 retained in the unit tier, 29,895 and 42,033 Slow and 15 to 21 MB more heap on the node.

**Feedback filed:** section D of the case file and the B2/B3 amendments (uncommitted).
