# parent_repair_status_cache_size-ActiveRepairService-repairStatusByCmd--autonomous — stage-4 results  <!-- file: results/parent_repair_status_cache_size-ActiveRepairService-repairStatusByCmd--autonomous.md -->

> **Case:** [`parent_repair_status_cache_size-ActiveRepairService-repairStatusByCmd--autonomous`](../../stage3-ai-deep-read/cases/parent_repair_status_cache_size-ActiveRepairService-repairStatusByCmd--autonomous.md) (stage-3 order o127, writeup-set-ext.csv, band B; amended working copy `~/writeup-ext/out/o127/case-amended.md`, outside the repo)
>
> **Status:** self-checked, verdict filed by the stage-4 session (2026-11-25); run 2 not chosen
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**)
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the case
> file's feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `cd9e1cded`; the case file is committed (`bef6bc8a6`). Filing sha256 `5693e35191f8f4510997d0cc58da3d7c8293f5b0bb43631cf2936b2bc59e58e0` (equal to `_INDEX.md` §4; copy `harness/case-as-filed.md`). Audit amendments S4-A1 to S4-A5 in section D (2026-11-25, frozen 08:00 UTC before the unit sweep: `2d6ce52b…`; a wording fix to S4-A4's control line, same threshold, at 08:02:34 while the sweep ran and before any value was read: `0cc48bc3…`). S4-A6 (runbook, after the cluster shakedowns, before the cluster sweep; its timestamp text corrected at 08:08 before any reading was looked at): **frozen sha256 `0babc6686db2aff169504c769b5d4f83cb444540def1740a035b5f42d6d000a9`**; frozen text (B2f–B2h, B3f–B3h, amendments; `harness/freeze-pred.txt`) `dc3df795fa36551791ee21b7e3dbe7b15b40a8fd49088f604f74b69800a927e7`. Sections A–C, B2f, B3f and the B2g/B3g tables are byte-identical to the filed version (diff). Final file sha256 after the section-D result paragraph: `ef66c061457f4e380a93488ba1668c579998dc8d6de2dca6dda686b12b47aeaa`. |
| **Harness** | `~/writeup-ext/out/o127/harness/` (to become `harness/parent_repair_status_cache_size-ActiveRepairService-repairStatusByCmd--autonomous/`): `ParentRepairStatusCapTest.java` (verbatim B2a), `unit-run.sh`, `unit-all.sh`, `Drive-as-filed.java`, `Drive.java` (S4-A3), `mkconf.py`, `cluster-run.sh`, `cluster-all.sh`, `analyze.py`, `README.md`, `md5.txt`. Not committed by this session. |
| **Tiers and values** | Unit (B2): `-Dcassandra.parent_repair_status_cache_size` N ∈ {0, 1, 1000, 10000, unset = 100000}, m = 50000, len = 1000; entry-size sweep N = 1000, len ∈ {100, 10000}; invalid edge N = −1. Cluster (B3): one node, 2 GiB heap, `num_tokens: 256`, `repair_state_size: 10`, keyspace `o127` NTS RF 2, 30,000 `repairAsync` skip-path repairs (`ignoreUnreplicatedKeyspaces`) in batches of 500; N ∈ {100, 10000, unset}; one fresh node per value. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 (S4-A1 to S4-A6 in the case file's section D) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: a count of cache entries with a derivable heap size; B2d jamm deep size, B3d live-heap histogram. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b five values incl. default; B3b three incl. default. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit `measureDeep` of the cache graph; cluster `GC.class_histogram` Total and `[B`; the gap (cache bytes not separable from other live objects without MAT) named in B3d; S4-A5 adds the `LocalCache$StrongAccessWriteEntry` count. |
| A. Core question | usage driven to the limit and past it | Met | Unit m = 50000 ≥ 5N for binding N; cluster M = 30000 vs N = 100 / 10000. |
| A. Core question | positive control | Met | The default (non-binding) value in both tiers, same workload and instruments. |
| B. Logic | each step says what it establishes | Met | B2d/B2h, B3d/B3h. |
| B. Logic | prediction in numbers | Met | B2f exact sizes and MB ranges; B3f `present`, ΔTotal ranges and ratio ≈ 3. |
| B. Logic | every plausible outcome has a row | Partly → Met after S4-A4, S4-A5 | No verdict labels; "flat", "≈ ×35", "roughly the same", "far below" undefined; B2f len rows had no range; B3g had no threshold between row 1 and row 6. Added before any reading. |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met | Exact `size` = N with older cmds evicted (`present` vs `presentInLastN`, `getParentRepairStatus` returning null for evicted cmds). |
| B. Logic | alternative explanations and controls | Met | `cap=` echo / JVM args, `cleanUp()`, distinct strings, `repair_state_size: 10`, fresh node per N; S4-A5 names a JMX notification buffer as a possible offset (counted: 0). |
| C. Specific | understandable from the intro and B1 | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run the runbook without re-deriving | Partly → Met after S4-A1, S4-A2, S4-A3 | Paths/build on this node; readings are in the test log, not the XML; batch wait can hang at small N. |
| C. Specific | values, commands, observables exact | Met | B2e, B3e in full. |
| D. Runnable | prerequisites exist | Met | JDK 11.0.33, Ant 1.10.12, built 5.0.9 copy `/mydata/s4/cassandra-base` (md5 of `ActiveRepairService.java`, `RepairCoordinator.java`, `CassandraRelevantProperties.java`, `StorageService.java`, `build.xml` equal to the repository's source). |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit ≤ 60 MB in a test JVM; cluster ≤ 400 MB in a 2 GiB heap; 656 GB free on `/mydata`. |
| D. Runnable | citations spot-checked | Met | `ActiveRepairService.java:173-182` (Holder), `:226`, `:242-248` (builder, `maximumSize` at :247), `:525-528` (`recordRepairStatus`), `:532-535`; `StorageService.java:4797-4801`, `:4969-4974`; `RepairCoordinator.java:208-209`, `:236-237`, `:293`, `:384-408`; `RepairOption.java:53` (`ignoreUnreplicatedKeyspaces`). All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | Built copy, paths under `/mydata/jingsong-cass-s4/o127/`, `ulimit -n 100000`, stop by PID | applied 2026-11-25 | runnable on this node |
| S4-A2 | Read the `O127` lines from the test log | applied 2026-11-25 (after the shakedown) | the logger does not write them to the XML |
| S4-A3 | Driver: pool-idle fallback wait, `probe`, `pool`, `count` by status | applied 2026-11-25, before any reading | a small N can evict the batch's last cmd before the poll; B3g row 6 needs the message length |
| S4-A4 | B2g thresholds, labels, ranges for the len rows | applied 2026-11-25, before any reading | undefined words |
| S4-A5 | B3g thresholds and labels; per-entry e from the measured message length; extra histogram rows | applied 2026-11-25, before any reading | no threshold between row 1 and row 6 |
| S4-A6 | D1 driver classpath (Guava); `nodetool flush` before each histogram | applied 2026-11-25, after the shakedowns, before the sweep | D1 broke the driver; memtable rows added ~8 MB between samples |
| R-a | Use a weigher or document the entry-size dependence (A3.6): the ~100 B assumption in the code comment is off by ×115 on the skip path | left for stage 3 / doc note | not a design defect |
| R-b | B3a: say that the driver needs Guava on its classpath | left for stage 3 (fixed here as D1) | — |

**Agreement criteria** — run 2 not planned.

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-25 UTC: unit shakedown 07:59:18–07:59:38, unit sweep 08:00:23–08:03:01; cluster shakedowns 08:03:43–08:05:23 (D1) and 08:05:45–08:07:28; cluster sweep 08:08:16–08:20:42 | not done |
| Node | `pc82` (`node1.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`), **x86_64**, 40 cores, 125 GiB RAM, `/mydata` 753 GB (656 GB free); held under `/mydata/s4/NODE-LOCK` for the whole run | |
| OS / kernel | Ubuntu 22.04 / `5.15.0-203-generic` (experiment `jason92-326665`) | |
| JDK / Ant | openjdk 11.0.33 (2026-10-20) / Ant 1.10.12 | |
| Local source copy | `cp -a /mydata/s4/cassandra-base` → `/mydata/jingsong-cass-s4/o127/c509` (both tiers); 5.0.9, md5-checked against repo `systems/cassandra/source` (repo HEAD `cd9e1cded`, source clean) | |
| Storage | unit: the tree's `build/test`; cluster: `/mydata/jingsong-cass-s4/o127/node/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, wiped per value — tree and node directory removed after the run | |
| Logs | node `pc82:/mydata/jingsong-cass-s4/o127/{unit,cluster,logs,harness}` (9.6 MB kept); copies here: `run1/unit/{shakedown,run1}/` (`run-<label>.log`, `testlog-<label>.log`, `TEST-<label>.xml`), `run1/cluster/<label>/` (`session.txt`, `hist-{base,after,after60}.txt`, `heapinfo-*.txt`, `drive.txt`, `probe.txt`, `count.txt`, `tpstats.txt`, `jvm-args.txt`, `repair_admin.txt`, `system.log`, `cassandra.out`), `run1/driver-logs/`, `run1/analysis.txt` | |

No partial `o127` folder from earlier attempts existed on `pc82`. An earlier unmodified copy of the case file in `~/writeup-ext/out/o127/` was moved to `prior-draft/` and not used.

## 3. Runbook defects

| # | Step | Problem | Fix | §9a changed? |
|---|---|---|---|---|
| D1 | B3a driver, B3e.7/10 | `getParentRepairStatus` returns a Guava `ImmutableList`; the driver (plain `java Drive.java`) fails with `ClassNotFoundException: com.google.common.collect.ImmutableList$SerializedForm` at the first batch wait (`run1/cluster/shake1-D1-N100-M1000/`) | run the driver with `-cp <tree>/build/lib/jars/guava-32.0.1-jre.jar` (S4-A6) | no |

Found in the cluster shakedown (N = 100, M = 1000), not in run 1. The second shakedown passed: 1000 repairs in 5.2 s, `present=100`, message 11,308 chars (`run1/cluster/shake2-N100-M1000/`). Unit shakedown N = 10, m = 200: final `size=10 present=10` (`run1/unit/shakedown/`).

## 4. Run 1

**Scope:** unit tier B2 as amended (8 JVMs); cluster tier B3 as amended (3 values, one fresh node each). **Command log:** `run1/unit/run1/run-<label>.log`, `run1/cluster/<label>/session.txt`, `run1/driver-logs/{unit-all,cluster-all}.out`. **Analyzer:** `harness/analyze.py` → `run1/analysis.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/run1/testlog-*.log`, `TEST-*.xml`; each 1 test, 0 failures, 0 errors except N = −1)

| N | len | final `size` | `present` | `presentInLastN` | B0 | `deep` − B0 | per entry | checkpoints |
|---|---|---|---|---|---|---|---|---|
| 0 | 1000 | 0 | 0 | 0 | 528 B | 0 | — | size 0 at every checkpoint |
| 1 | 1000 | 1 | 1 | 1 | 528 B | 1.2 KB | — | size 1 from i = 5000 |
| 1000 | 1000 | 1000 | 1000 | 995 | 1456 B | **1.196 MB** | 1196 B | 1000 from i = 5000; deep +0.29 % from i = 5000 to final |
| 10000 | 1000 | 10000 | 10000 | 9974 | 1456 B | **11.909 MB** | 1191 B | 5000, **9937** (i = 10000), then 10000; +0.03 % from i = 20000 |
| default | 1000 | **50000** | 50000 | 50000 | 1456 B | **59.728 MB** | 1195 B | rises 5000 per checkpoint, deep 5.95 → 59.73 MB |
| 1000 | 100 | 1000 | 1000 | 995 | 1456 B | 0.300 MB | 300 B | flat |
| 1000 | 10000 | 1000 | 1000 | 995 | 1456 B | 10.196 MB | 10.2 KB | flat |
| −1 | — | — | — | — | — | — | — | `ExceptionInInitializerError` at `ActiveRepairService.instance()`, caused by `IllegalArgumentException: maximum size must not be negative` |

The `O127 cap=` header echoed each N (`default` for the unset run).

**Cluster tier** (`run1/cluster/<label>/`; 30,000 repairs each, 0 cmd = 0, 0 fallback waits, Repair-Task Completed 30000 / Active 0 / Pending 0, `repair_admin list`: no sessions, 0 `^ERROR` lines)

| N (JVM args) | drive time | probe (cmd 30000) | `present` (COMPLETED) | `StrongAccessWriteEntry` (after) | Total base → after → after+60s | ΔTotal | Δ`[B` | notifications |
|---|---|---|---|---|---|---|---|---|
| 100 (`-D…=100`) | 133 s | COMPLETED, 11,330 chars | **100** (100) | 110 | 64.1 → 75.5 → 75.5 MB | **+11.4 MB** | +4.9 MB | 0 |
| 10000 (`-D…=10000`) | 139 s | COMPLETED, 11,306 chars | **10000** (10000) | 10010 | 63.8 → 189.0 → 189.0 MB | **+125.2 MB** | +117.1 MB | 0 |
| default (no `-D`) | 144 s | COMPLETED, 11,292 chars | **30000** (30000) | 30010 | 63.9 → 418.6 → 418.6 MB | **+354.7 MB** | +343.2 MB | 0 |

The `+10` entries are the `repairs` cache pinned by `repair_state_size: 10`. `GC.heap_info` used follows the Total (73.8 / 184.6 / 408.8 MB after).

### 4.2 Conclusion and logic

1. **Validity** — Valid. Unit: every JVM echoed the intended N and ran 50000 `recordRepairStatus` calls [observed: `testlog-*.log`]. Cluster: each node carried the intended JVM args (`jvm-args.txt`), every one of the 30,000 commands got a non-zero cmd and completed through the skip path (`COMPLETED`, ~11.3 K-char "Nothing to repair for [...]" message; `count.txt` has 0 in-progress / failed), the pool drained [observed: `drive.txt`, `probe.txt`, `tpstats.txt`].
2. **Readings** — Unusual: none material. N = 10000 reads 9937 at i = 10000 (per-segment eviction before the total reaches N), as B2f predicts. ΔTotal includes a one-time ~10 MB rise unrelated to the cache (12,000 JMX `ObjectName`s / `HashMap`s, the same after 500 or 1000 repairs in the shakedowns) [observed: shakedown histograms].
3. **Matched row** — Unit B2g row 1 with S4-A4 thresholds: final `size` = `present` = min(N, 50000) for all five N, no checkpoint above N, flat after 2N (+0.29 %, +0.03 %), positive control 59.728 MB = 5.02 × the N = 10000 value; count-not-bytes ratio 34.0 ∈ [20, 50]; all B2f byte ranges met [observed: `analysis.txt`]. Cluster B3g row 1 with S4-A5 thresholds: `present` = min(N, 30000) exactly; ΔTotal(100) = 11.4 MB < 30 MB; ratio default / 10000 = 2.83 ∈ [2.4, 3.6]; e = 12,521 / 11,823 B per entry within [0.8, 1.4] × (11,292 + 200) and within 6 % of each other; incremental e 11,494 B (100 → 10000) and 11,474 B (10000 → default); after / after+60s within 0.1 %; B3f ranges 100–140 and 300–400 MB met [observed].
4. **Excluded rows** — Unit row 2 (size > N): never [observed]. Unit row 3 (50000 at binding N): 1000 / 10000 [observed]. Control-failed row: default reached 50000 [observed]. Row 7 (deep same for both lengths): ×34 [observed]. Row 8 (N = 0 retains entries): 0 [observed]. Cluster row 2 (both capped runs ≈ +350 MB or `present` = 30000): 11.4 / 125.2 MB, `present` 100 / 10000 [observed]. Row 3 (`present` = N but ΔTotal ≈ +350 MB at N = 100): 11.4 MB [observed]. Control-failed row: +354.7 MB [observed]. Row 6 (far below prediction): inside B3f ranges [observed].
5. **Observed vs. inferred** — Inferred: (i) that the cluster ΔTotal is the status cache. Supported by: the only setting that differs between runs is N; the live `StrongAccessWriteEntry` count equals `present` + 10; Δ`[B` ≈ `present` × 11.3 K chars (Latin-1); the incremental per-entry heap (11.47–11.49 KB) equals message length + ~200 B; `repair_state_size: 10` pins the other holder of the same strings [inferred from observed numbers; no heap dump / MAT was taken]. (ii) That evicted cmds are dropped, not rejected: `getParentRepairStatus` returns null for them (`present` < issued) while every repair completed [observed].
6. **Deviations and gaps** — S4-A1 to S4-A6 (section 1). The optional MAT attribution and the optional N = 0 cluster run were not done. Run on x86_64 (`pc82`); timings are not comparable to aarch64 m400 runs of other cases, which this design does not depend on.
7. **Core question** — The constraint caps usage and usage follows it. The unit tier shows the cache holds exactly min(N, issued) entries and its deep size is flat at N × ~1.19 KB once N is reached, while the non-binding default grows to 50000 entries / 59.7 MB on the same workload. The cluster tier shows the real resource follows: live heap rises +11.4 / +125.2 / +354.7 MB for N = 100 / 10000 / default with 30,000 repair commands each. The cap counts entries, not bytes: per-entry heap scales with the message (×34 between 100- and 10000-char messages at a fixed N), and on the skip path with 256 vnodes one entry is ~11.5 KB, about 115 × the "~100 bytes" assumed in the source comment, so the default 100,000 can hold ~1.15 GB of such statuses.

**Conclusion (one line):** Unit B2g row 1, cluster B3g row 1 — claim confirmed: `cassandra.parent_repair_status_cache_size` caps the parent-repair status cache at N entries and the heap it retains follows N (effect: caps; a count cap whose bytes scale with message size).

## 5. Self-check of run 1 — AI

Re-read by hand, not from the analyzer: the `O127` lines of all eight unit test logs and the `<testsuite>` / `<error>` tags of the XML; for each cluster value `jvm-args.txt`, the `Total`, `[B` and `StrongAccessWriteEntry` lines of `hist-{base,after,after60}.txt`, `count.txt`, `probe.txt`, `tpstats.txt`, the number of `DRIVE issued` lines (60) and `wait=pool-idle` lines (0), `repair_admin.txt`, and the `parent_repair_status_cache_size` count in `system.log` (1 / 1 / 0).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | JVM args and `cap=` echoes match the intended values; all 30,000 cmds completed per value. |
| 2. Readings | yes | 9937 at i = 10000 re-read; one-time rise re-read in the shakedown histograms. |
| 3. Matched row | yes | Every number of both rows re-read in the raw files. |
| 4. Excluded rows | yes | Each exclusion cites a re-read number. |
| 5. Observed vs. inferred | yes | (i) rests on four independent consistent numbers (entry count, Δ`[B`, incremental e, ratio); stated as inferred. |
| 6. Deviations and gaps | yes | Amendments, D1, no MAT, no N = 0 cluster run stated. |
| 7. Core question | yes | B1 → B2/B3 runbooks → B2f/B3f → B2g/B3g row 1, with the positive controls moving. |

### 5.2 Run 2?

**No** (2026-11-25). Both tiers give exact counts and byte figures inside the predicted ranges, the positive controls move as predicted, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — not done. ## 7. Comparison — not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps): both tiers Confirmed with effect `caps`.

**Claim tested:** (B1) On a node started with `-Dcassandra.parent_repair_status_cache_size=N`, the parent-repair status cache holds min(N, repair commands issued within the expiry window) entries; the heap it retains is about that count × the per-entry size (it follows N, not the number of repairs); at a fixed N the retained heap scales with the message size, because the cap counts entries rather than bytes.

| Tier | Verdict | Effect | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: **Confirmed** — final size 0 / 1 / 1000 / 10000 / 50000 for N = 0 / 1 / 1000 / 10000 / default; deep +1.196 / +11.909 / +59.728 MB; ×34.0 between len 100 and 10000 at N = 1000; N = −1 rejected at construction | caps | run 1 + self-check | 2026-11-25 |
| Cluster | B3g row 1: **Confirmed** — `present` 100 / 10000 / 30000; live heap +11.4 / +125.2 / +354.7 MB; ~11.5 KB per entry (11.3 K-char skip message) | caps | run 1 + self-check | 2026-11-25 |

**Positive control:** default (non-binding) value — unit 50000 entries / 59.7 MB; cluster 30000 entries / +354.7 MB.

**Feedback filed:** the amended case file's section D (`~/writeup-ext/out/o127/case-amended.md`: amendments S4-A1 to S4-A6 and the stage-4 result paragraph). No section of the trace was refuted. **Doc note:** the cap is a count; one status entry on the `--ignore-unreplicated-keyspaces` skip path with 256 vnodes holds ~11.5 KB, so the default 100,000 entries can retain on the order of 1 GB for a day (the expiry), against the ~10 MB the source comment's 100-byte assumption implies. **Leftovers on pc82:** nothing running (no CassandraDaemon, driver, Ant or test JVM; ports 7000/7199/9042/9091 free); source tree and node data removed; kept `/mydata/jingsong-cass-s4/o127/{unit,cluster,logs,harness}` (9.6 MB). Driver PID file removed; node lock released at the end.
