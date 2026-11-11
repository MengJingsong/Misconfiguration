# yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous — stage-4 results  <!-- file: results/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md -->

> **Case:** [`yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous`](../../../stage3-ai-deep-read/yang/cases/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous.md)
>
> **Status:** **verdict filed 2026-11-06** — unit **Confirmed** (does not cap), cluster **Confirmed** (does not cap). Claim tested: the container memory an auto-created leaf queue is allocated and holds resident does not follow the check at `GuaranteedOrZeroCapacityOverTimePolicy.java:719` or the parent's `capacity`. The check fired as traced (u3 got guarantee 0 at P = 20 and 40, the template guarantee when T = 25), and u3's memory was identical in all three arms (41984 MB unit; 7168 MB allocated and ~3648 MiB RSS cluster), while the template maximum (positive control) held the same workload at 25600 MB / 3072 MB. Two runbook defects fixed by dated amendments (A9, A10), each tier restarted. One run 1 per tier, no run 2.
>
> **Outcome class:** **true negative** — stage-3 estimate `negative` against the stage-4 effect `does not cap` on both tiers ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Hadoop, Yang's share: this file is in `hadoop/stage4-runtime-verification/yang/results/`; the case file is in
`hadoop/stage3-ai-deep-read/yang/cases/`; the harness is in `../harness/<stem>/`; the protocol is
[`../../../../stage4-runtime-verification/README.md`](../../../../stage4-runtime-verification/README.md#the-run-protocol);
the node is described in [`../environment.md`](../environment.md).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository HEAD `bd784dba` plus the uncommitted case file (untracked at audit time). sha256 at filing (`_INDEX.md` §4): `f1ba76bb888db0e1d41a2d81267e2ee6d80ef755edeb76da8176a40d0931f781`. After the audit's amendments D1 (A1–A8), 2026-11-06 11:46 EST, before any harness run or reading: whole-file sha256 **`660ebeee5c7cfb63e41c1e051a567c3bd4e134cf17c80057dead0c81682d8273`** (frozen version). Frozen prediction and conclusion tables: sha256 of the text from `**B2f.` up to `**B2h.` `5db8f2cf20244c4980438d5ef79984667ef3beb17262bcfc0f313e8d02c84c77`; from `**B3f.` up to `**B3h.` `91d9021ecf8490cbf11a8e35569a6ed97ab9a36094cf88bde9f809c92c20b56c`. Section D takes the feedback after this freeze, so the whole-file hash changes then; the two table hashes do not. |
| **Harness** | `../harness/yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous/` (written after this freeze, before run 1; see its README). Uncommitted at run time (commit only when asked); md5 of each file in the run's `summary.txt`. |
| **Later amendments (runbook defects, §3)** | A9 (B2e step 1) → whole-file sha256 `7b2dfe1c47520183006423f32d2981a39a2a0083d8f586c8b5b98db052ee73eb`; A10 (B3a) → `1afc50c92ada184b083f1c6a176db4665ae5a04c8cfdc20dd530e0c09126280a` (the version both counted tiers ran against). The B2f–B2g and B3f–B3g text hashes above are unchanged by both (re-computed after each). Section D2 was added after the runs. |
| **Tiers and values** | Unit (B2): MockRM, one 102400 MB MockNM; (P, T, M) = U1 (20, 50, 100), U2 (20, 25, 100), U3 (40, 50, 100), U4 control (20, 50, 25); u3 asks 40 × 1024 MB; three repeats. Cluster (B3): one node, NodeManager 12288 MB; C1–C4 with the same (P, T, M); u1 and u2 2048 MB each, u3 7168 MB (6 × ~600 MiB hog containers). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-06 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the leaf's guaranteed share of cluster container memory (a fraction with a derivable size in MB: abs cap × cluster MB), and the container memory the leaf actually gets (scheduler MB; RSS in the cluster tier). The file says honestly the check limits a sum of guarantees, not usage. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | B2b/B3b: P ∈ {20, 40} and T ∈ {50, 25}, three arrangements of the check (u3 zero at limit 0.2, u3 activated, u3 zero at limit 0.4). The knob's default (unset → 0, `CapacitySchedulerConfiguration.java:602-606`) is not run; at P = 0 the template guarantee is also 0, so the check passes trivially (0.001 ≥ 0). Left for stage 3 (R1): predicting it needs a source reading of zero-capacity managed parents. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: scheduler-allocated MB only, gap named in B2d. Cluster: `ps` RSS of the tagged hog processes (B3d); the AM's RSS is not separated (named in B3d). |
| A. Core question | usage driven to the limit and past it | Met | B2c: u3 demand 41984 MB vs guarantees 0–10240 MB; B3c: 7168 MB vs 0–2457.6 MB; in both, below the leaf max (102400 / 12288 MB) except the controls. |
| A. Core question | positive control (negative estimate) | Met | U4/C4: same workload, `leaf-queue-template.maximum-capacity` = 25 → a known binding max on the same resource (25600 / 3072 MB), enforced at `AbstractCSQueue.java:788-802,831-857`. |
| B. Logic | each step says what it establishes | Met | B2h/B3h: U2 vs U1 isolates the check's outcome, U3 vs U1 the limit, U4 the control; effMax and `avail` printed to show the template and operand. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f/B3f give exact numbers (41984, 7168, 3650 MiB, ≤ 25600/3072), but "≈" and "steady-state" were undefined. **Amended** (A3a, A8). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B2g/B3g lacked: a U1/U3-vs-U2 difference of another shape (B2f says it refutes), a partly binding control, allocated vs resident disagreement (the "counter vs real" row), non-deterministic repeats; the trace-mismatch rows gave no verdict. **Rows added** (A3, A7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For this negative file: the disallow branch's firing is printed directly (u3 abs cap 0, `active=false`, activated sum unchanged — B2d; `absoluteCapacity` 0 in C1/C3 — B3d), and the control shows a ceiling that follows a knob. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: cluster size above demand, u1/u2 not asking, fresh MockRM / RM restart, `root.default` idle, user-limit-factor 100. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, Ground, A3 steps 1–7, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | B2a/B3a paths (`~/hadoop-3.4.2`, `$SCRATCH/m2`, tarball build) do not exist here; `jq` absent; distributed-shell jar not in `share/`; `yarn node -list` prints no memory. **Amended** (A1, A4–A6). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B2e outline omits the app-state print B2d lists; B3e had no wait timeouts or first-trigger stop; window start undefined. **Amended** (A2, A6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Test class and run scripts are step-1 work. Found at audit: the base distribution (`hadoop-dist/target/hadoop-3.4.2`) has **no YARN module jars** in `share/hadoop/yarn/` (its `lib/` has 45 jars; RM/NM jars only in `tools/lib`), `jq` is not installed. **Amended** (A4: copy the YARN module jars from `~/.m2` into the per-case copy; python filter). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 11264 MB of containers ≤ 12288 MB NodeManager; node 247 GiB available, 706 GB free on `/mydata`; unit cluster 102400 MB simulated, demand 41984 MB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked at `rel/release-3.4.2` (repository `systems/hadoop/source/`): `GuaranteedOrZeroCapacityOverTimePolicy.java:715-720` (operand and check), `:735-742` (zero branch keeps template max), `:744-754`, `:632-642` (activate), `:518` `isActive`, `:775` `getAbsoluteActivatedChildQueueCapacity`; `ManagedParentQueue.java:298-344`; `UsersManager.java:714, 790-798` (zero capacity → user limit = effective max); `AbstractLeafQueue.java:812-814, 876-883`; `CSQueueUtils.java:33, 319-323`; test helpers `MockRM.registerNode(String,int,int)` `:526`, `launchAndRegisterAM` `:956`, `MockAM.allocate(String,int,int,List)` `:190`, `MockRMAppSubmissionData.Builder` `:220-281`. All as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Add an arm at the knob's default (P unset = 0) | Left for stage 3 | Not needed for a valid run; its prediction needs a source reading of zero-capacity managed parents |
| R2 (A1, A4, A5) | Node paths: `/mydata` scratch, `copy-source.sh`, `~/.m2`, copied distribution completed with the YARN jars, DS jar from `~/.m2`, python REST filter | Applied 2026-11-06 (uncommitted; frozen sha256 above) | filed paths and tools do not exist on the node |
| R3 (A2) | Print u3's app state, u4/u5 usage; derive U4's unsatisfied requests | Applied 2026-11-06 | B2d lists them; the outline omits them |
| R4 (A3, A7, A8) | Define "≈" and "steady-state"; verdicts for the trace rows; rows for uncovered outcomes | Applied 2026-11-06 | every plausible outcome needs a row before any reading |
| R5 (A6) | Wait timeouts, first-trigger stop, RM-only restart, node memory from REST, window start | Applied 2026-11-06 | stop conditions were missing |
| R6 | Separate the distributed-shell AM's RSS from the hog RSS | Left for stage 3 | named as a gap in B3d; not needed for the claim |

**Agreement criteria** — only if run 2 is chosen (see 5.2).
Not chosen (see 5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-06 (unit attempt 1 11:48–11:58 EST, counted unit run 12:00–12:02; cluster attempt 1 12:02, counted cluster run 12:03–12:16) | not done |
| Node | `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (the local node), 40 cores, 251 GiB (247 GiB available at start); no other Hadoop daemon running, all listed ports free before the cluster run | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | — |
| JDK (`java -version`) | openjdk `1.8.0_504` (`/usr/lib/jvm/java-8-openjdk-amd64`, for the build, test and daemons) | — |
| Build tool | Apache Maven 3.6.3 (unit tier; artifacts from the node's `~/.m2`, built 2026-11-06 from repository commit `bd784dba`) | — |
| Local source copy | `/mydata/yang-s4/<stem>-run1/src`, made by `../copy-source.sh` from the repository's `systems/hadoop/source/` at HEAD `bd784dba` (clean), local tag `rel/release-3.4.2`; only the harness test class added | — |
| Cluster distribution | `/mydata/yang-s4/<stem>-run1/hadoop`: copy of `/mydata/yang-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` plus 17 YARN module jars from `~/.m2` into `share/hadoop/yarn/` (A4) and `hadoop-yarn-server-timelineservice-3.4.2.jar` into `share/hadoop/yarn/timelineservice/` (its standard place; see §4.2 part 6) | — |
| Case-file commit / harness commit | `bd784dba` + the uncommitted case file at sha256 `1afc50c9…` (A1–A10) / uncommitted; harness md5: `TestIfCheckAutoQueueGuaranteeVsUsage.java` e04e66f2, `unit-run.sh` 34acb727, `cluster-run.py` 0cb2a294, `hog.py` 954d1d8c, `selfcheck.py` 2931db63 | — |
| Storage for node data | `/mydata/yang-s4/<stem>-run1/data` (local disk `/dev/mapper/emulab-node0--bs`); nothing on `/proj` | — |
| Full logs (path, outside the repo) | `/mydata/yang-s4/<stem>-run1/logs/`: `unit/rep{1,2,3}/` (counted), `unit-attempt1/` (defect 1), `cluster/` (counted), `cluster-attempt1/` (defect 2), daemon logs `hadoop-jason92-*.log`, `selfcheck.txt` | — |

`<stem>` = `yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous`.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1, unit | B2e step 1 (`MockRM.launchAndRegisterAM(u3App, rm, nm)`) | All four tests failed in all three repeats: "Attempt state is not correct (timeout). expected:<ALLOCATED> but was:<SCHEDULED>" (`run1/unit/attempt1-failure.txt`). `MockRM.launchAM` (`MockRM.java:915-927`) sends exactly two heartbeats; one container is assigned per heartbeat, and those two went to u1's and u2's AMs (attempt-1 output lines 1329 and 1415), so u3's attempt never got one — also in U2, where u3 was activated, so the failure is not caused by the check. The script did not stop on it because the module build ignores test failures (Maven rc 0). | A9: heartbeat until u3's attempt is ALLOCATED (≤ 20; 3 were needed in every arm), then `sendAMLaunched`, `registerAppAttempt`, wait RUNNING. `unit-run.sh` now stops on the surefire failure count. B1/B2f/B2g unchanged; unit tier restarted from the beginning. | Amendment, 2026-11-06 | uncommitted; sha256 `7b2dfe1c…` |
| 2 | 1, cluster | B3a (`cp $HADOOP_HOME/etc/hadoop/* $SCRATCH/conf/`) | Exits 1: "-r not specified; omitting directory … shellprofile.d" (`run1/cluster/attempt1-defect2.log`). The run stopped in setup; no daemon had started. | A10: `cp -r`. B1/B3f/B3g unchanged; cluster tier restarted from the beginning. | Amendment, 2026-11-06 | uncommitted; sha256 `1afc50c9…` |

The readings of the unit tier's failed attempt (the `create` lines, `run1/unit/attempt1-ifchk-rep1.tsv`) existed when A9 was written. A9 depends only on the failure (an AM-launch helper), not on any value, and changes no prediction or conclusions row; the counted run is the restarted one.

## 4. Run 1

**Scope:** unit tier U1–U4, three repeats; cluster tier C1–C4, one pass. **Command logs:**
`yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous/run1/unit/unit-run.log`, `…/run1/cluster/cluster-run-commands.log` (full: `/mydata/…-run1/logs/cluster/cluster-run.log`).

### 4.1 Readings

**Unit tier** (all three repeats byte-identical, 134 `IFCHK` lines each; values from `run1/unit/ifchk-rep1.tsv`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| U1 `avail` before u1, u2, u3 | 0.2010, 0.1010, 0.0010 (predicted 0.201, 0.101, 0.001) | `run1/unit/ifchk-rep1.tsv` |
| U1 u3 abs cap / active / activated sum / effMax | 0.0000 / false / 0.2000 / 102400 MB (as predicted) | same |
| U1 u3 used after 80 heartbeats | **41984 MB**; u1, u2 1024 each; u3 app RUNNING | same |
| U2 `avail` before u1..u5 | 0.2010, 0.1510, 0.1010, 0.0510, 0.0010 (as predicted) | same |
| U2 u3 / u5 abs cap, active; activated sum after u3 / u5 | u3 0.0500 true; u5 0.0000 false; 0.1500 / 0.2000 (as predicted) | same |
| U2 u3 used | **41984 MB**; u1, u2, u4, u5 1024 each | same |
| U3 `avail`; u3 abs cap / active / sum | 0.4010, 0.2010, 0.0010; 0.0000 / false / 0.4000 (as predicted) | same |
| U3 u3 used | **41984 MB** | same |
| U4 (control) `avail`; u3 abs cap / active / sum; effMax | 0.2010, 0.1010, 0.0010; 0.0000 / false / 0.2000; **25600 MB** (as predicted) | same |
| U4 u3 used | **25600 MB** (AM + 24 containers); 40 − 24 = 16 requests unsatisfied | same |
| Surefire | 4 run, 0 failures, 0 errors, each repeat | `run1/selfcheck.txt` |

**Cluster tier** — u3 in each run (median of 61 samples over 120 s; min = max in every case), from `run1/cluster/run-C*.tsv`:

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| P 20, T 50, M 100 | C1 | u3 `absoluteCapacity` / `absoluteMaxCapacity` | 0 / 100 (constant) | `run1/cluster/run-C1.tsv` |
| | C1 | u3 `resourcesUsed.memory`; hog count; hog RSS | **7168 MB**; 6; **3648.0 MiB** | same |
| P 20, T 25, M 100 | C2 | u3 abs / abs max | 5 / 100 | `run1/cluster/run-C2.tsv` |
| | C2 | u3 used; hogs; RSS | **7168 MB**; 6; **3647.9 MiB** | same |
| P 40, T 50, M 100 | C3 | u3 abs / abs max | 0 / 100 | `run1/cluster/run-C3.tsv` |
| | C3 | u3 used; hogs; RSS | **7168 MB**; 6; **3647.5 MiB** | same |
| P 20, T 50, M 25 | C4 (control) | u3 abs / abs max | 0 / 25 | `run1/cluster/run-C4.tsv` |
| | C4 | u3 used; hogs; RSS | **3072 MB**; 2; **1215.8 MiB** | same |
| all | C1–C4 | u1, u2 used; hogs; RSS | 2048 MB each, 1 hog each, 607.9–608.0 MiB; u1/u2 abs 10/10, 5/5, 20/20, 10/10 (as listed in B3e 2.7) | `run1/cluster/run-C*.tsv` |
| all | C1–C4 | policy's own `availableCapacity` during the window (RM DEBUG, `DeactivatedLeafQueuesByLabel` form) | C1 0.001 (activated 0.2), C2 0.051 (0.15), C3 0.001 (0.4), C4 0.001 (0.2); no other value inside any window | `run1/cluster/apps-and-policy.txt`, `run1/selfcheck.txt` |
| all | C1–C4 | apps (REST, end of window) | all RUNNING in `root.parent.<user>`, started u1 < u2 < u3; u3 allocatedMB 7168 / 7168 / 7168 / 3072 | `run1/cluster/apps-and-policy.txt` |
| all | — | NodeManager log, "beyond physical memory" | 0 | `run1/selfcheck.txt` |
| instrument | — | standalone `hog.py` RSS (known answer) | 1 process, 607.9 MiB | `run1/cluster/cluster-run-key-lines.txt` |

### 4.2 Conclusion and logic

1. **Validity** — valid on both tiers. Unit: 4/4 tests passed in 3 repeats [observed: `run1/selfcheck.txt`]; the demand passed every guarantee involved (u3 41984 MB against 0 / 5120 MB) [observed: `run1/unit/ifchk-rep1.tsv`]; fixed settings confirmed by the printed effMax (102400, 25600 under M = 25) and u1/u2 at 1024 MB [observed: same]. Cluster: the node registered 12288 MB, `root.parent` read P each run, u1/u2 held 2048 MB, `root.default` had no apps, no pmem kill, the leaves were created in order u1 < u2 < u3 [observed: `run1/cluster/cluster-run-key-lines.txt`, `run1/cluster/apps-and-policy.txt`, `run1/selfcheck.txt`]; u3's demand of 7168 MB passed every guarantee (0, 614.4, 1228.8, 2457.6 MB) [observed: `run1/cluster/run-C*.tsv`].
2. **Readings** — nothing unusual inside the windows: every sampled value was constant over its 61 samples [observed: `run1/cluster/summary.txt`]. Outside the windows the policy log shows non-zero `deactivatedCapacity` right after the kills (e.g. 12:06:28 after C1's window ended 12:06:23), as expected when a leaf loses its last app [observed: `run1/cluster/apps-and-policy.txt`].
3. **Matched row** — Unit, B2g row 1: "`avail`/abs cap/activated sum as predicted; u3 used ≈ 41984 MB in U1, U2 and U3; U4 ≤ 26624 MB" — every `avail`, abs cap, `active`, activated sum and effMax as in B2f; u3 41984 / 41984 / 41984 MB; U4 25600 MB [observed: `run1/unit/ifchk-rep1.tsv`]. Cluster, B3g row 1: "C1 ≈ C2 ≈ C3 ≈ 7168 MB and ≈ 3650 MiB RSS for u3; C4 ≤ 3072 MB" — 7168 / 7168 / 7168 MB, 3648.0 / 3647.9 / 3647.5 MiB; C4 3072 MB [observed: `run1/cluster/run-C*.tsv`].
4. **Excluded rows** — Unit: *refuted, U1/U3 ≈ 1024 or 0* — U1, U3 41984 [observed]; *refuted, near a guarantee-derived value (≈ 10240)* — 41984, 31744 MB above it [observed]; *refuted (A3c), U1/U3 differ from U2 by > 1024* — difference 0 [observed]; *not confirmed, U4 also ≈ 41984* — 25600 and effMax 25600 [observed]; *not confirmed (A3d), U4 between 26625 and 41983* — 25600 [observed]; *not confirmed, low in all runs* — 41984 [observed]; *trace differs (A3b)* — all values as B2f [observed]; *repeats disagree (A3e)* — identical [observed: `run1/selfcheck.txt`]. Cluster: *refuted, C1/C3 ACCEPTED or ≤ 1024* — RUNNING, 7168 [observed]; *refuted, plateau below 7168 with pending requests* — 7168 with 6 hogs, the full demand [observed]; *refuted (A7c), C1/C3 vs C2 > 1024 MB or > 10 % RSS* — 0 MB, < 0.02 % [observed]; *not confirmed, C1–C3 all low* — 7168 [observed]; *not confirmed (A7d), allocation and RSS disagree* — 6 hogs, 3648 MiB in each [observed]; *not confirmed, C4 ≈ 7168* / *(A7e) C4 between 3073 and 7167* — 3072, abs max 25 [observed]; *`absoluteCapacity` not as listed* — 0 / 5 / 0 / 0 as listed [observed]; B3h discard rule — u3 `absoluteCapacity` constant in every window [observed].
5. **Observed vs. inferred** — The conclusion rests on observed readings. Inferred: (a) that the unit `avail` value is the one the check compared — the test recomputes `:715-717` from the same objects just before the creation, not inside the method [inferred: same expression, nothing else changes the two operands between the print and the call; the `active` flag and abs cap after the call, observed, are the check's outcome]; (b) that in the cluster the RM's `availableCapacity` at creation was the predicted one — observed only through the monitor policy's DEBUG line, which adds `deactivatedCapacity` (0 in every window) [inferred: same terms as `:715-717` when nothing is deactivated]; (c) that the AM's resident memory is not part of the hog RSS (named gap; it is included in the allocated MB).
6. **Deviations and gaps** — (i) the cluster copy also got `hadoop-yarn-server-timelineservice-3.4.2.jar` in `share/hadoop/yarn/timelineservice/`, beyond A4's list: its standard place, on the RM classpath, used only with timeline v2 (off) — no effect on scheduling; (ii) the RM-log DEBUG option of B3d was enabled (it is listed as optional); (iii) the window started 18 s (C1–C3) and 12 s (C4) after RUNNING, when the allocation had been stable 10 s (A6d); (iv) the default value of the knob (P unset) is not run (R1); (v) the unit tier observes only scheduler-allocated memory (named in B2d), the cluster tier observes RSS.
7. **Core question** — Usage did not follow the constraint. The check fired as traced: with P = 20 and 40 u3 got guarantee 0 and was not activated, with T = 25 it got the template guarantee (parts 3, 5a–b). In all three arms u3 received its whole demand — 41984 MB in the unit tier, 7168 MB allocated and ~3648 MiB resident in the cluster — identical across a zero guarantee, a 5 % guarantee and a doubled parent capacity (part 3). The same workload was held at 25600 MB / 3072 MB when the template's maximum capacity was 25 % (positive control, part 3), so the instruments and workload can show a cap; the check's limit is not one.

**Conclusion (one line):** Unit: B2g row 1 — confirmed. Cluster: B3g row 1 — confirmed.

## 5. Self-check of run 1 — AI

`../harness/<stem>/selfcheck.py` re-parses the raw files (surefire output and reports, the 2-s TSVs, REST snapshots, the RM log's policy lines, the NodeManager log, client logs) without the run scripts' summaries; output `run1/selfcheck.txt`: 0 FAIL. Its first version sliced the policy log over 125 s and so caught the post-kill lines (4 FAIL); the slice was corrected to the 120 s window, which is the window B3c defines — a self-check script error, not a reading change.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: surefire 4/0/0 ×3; u1/u2 1024 (unit) and 2048 MB, 1 hog (cluster); 61 samples per leaf; no pmem kill; apps in `root.parent.<u>`, created in order |
| 2. Readings | yes | `run-C*.tsv` min = max for every leaf; the non-window policy values are after the kills (`apps-and-policy.txt` timestamps vs. `cluster-run-key-lines.txt` window starts) |
| 3. Matched row | yes | `ifchk-rep1.tsv` all create lines equal B2f to 4 decimals; u3 41984 ×3, U4 25600; cluster 7168 ×3, RSS 3647.5–3648.0, C4 3072 |
| 4. Excluded rows | yes | each excluded row's condition re-checked in `selfcheck.txt` (differences 0 MB, C4 abs max 25, `absoluteCapacity` constant) |
| 5. Observed vs. inferred | yes | (a) the `active=false`/abs cap 0 after the call are observed, so the branch is direct; (b) the policy log's `deactivatedCapacity` is 0 inside every window (`apps-and-policy.txt`), so its `availableCapacity` equals the check's form; (c) named gap only |
| 6. Deviations and gaps | yes | none touches the measured path; the timelineservice jar is not loaded with timeline v2 off |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B2h/B3h logic: U2/C2 vs U1/C1 flips only the check's outcome → no change; U3/C3 vs U1/C1 changes only the limit → no change; U4/C4 binding max → change. Matches B1's refuted-if (not met) |

### 5.2 Run 2?

**No** — decided 2026-11-06. The conclusion rests on observed, exact readings (equal to the MB across arms, byte-identical unit repeats, constant cluster samples); the inferred statements are settled from run 1's raw files (§5.1 part 5); the result confirms the stage-3 estimate rather than refuting it or confirming a bypass; and the positive control moved on both tiers.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** — estimate `negative`, effect `does not cap` on both tiers.

**Claim tested:** how much container memory an auto-created leaf queue is allocated, and how much its containers actually hold resident, does **not** follow the check at `GuaranteedOrZeroCapacityOverTimePolicy.java:719` or its limit (the parent's `capacity`); the peak is set by the demand and the template max (B1).
"Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (u3 41984 MB in U1/U2/U3 with guarantee 0 / 0.05 / 0 and limit 0.2 / 0.2 / 0.4; U4 25600 MB) | does not cap | run 1 + self-check | 2026-11-06 |
| Cluster | **Confirmed** — B3g row 1 (u3 7168 MB, ~3648 MiB RSS in C1/C2/C3; C4 3072 MB) | does not cap | run 1 + self-check | 2026-11-06 |

**Positive control:** `leaf-queue-template.maximum-capacity` = 25 with the same workload: unit u3 held at 25600 MB (effMax 25600, 16 of 40 requests unsatisfied) against 41984 MB; cluster u3 held at 3072 MB, 2 hogs, 1215.8 MiB RSS against 7168 MB, 6 hogs, ~3648 MiB.

**Feedback filed:** the case file's section D2 "Stage-4 result" (2026-11-06, uncommitted); amendments A1–A8 (audit, before any reading) and A9–A10 (runbook defects) in the sections they change and in D1; `_INDEX.md` §1 (Stage 4, Outcome class) and §4 (sha256 lines); `queue.csv` order 2 `stage4` = `true negative`. Not committed (commit only when asked).
