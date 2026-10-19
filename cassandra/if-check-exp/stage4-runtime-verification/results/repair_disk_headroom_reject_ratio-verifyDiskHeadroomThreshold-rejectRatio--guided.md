# repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio — stage-4 results  <!-- file: long-path/results/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio.md -->

> **Case:** [`repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio`](../../stage3-ai-deep-read/cases/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided.md)
>
> **Status:** **Closed 2026-10-19 — all tiers verified at stage 4 (verdicts below).** verdict filed (2026-10-15) — **unit: Confirmed; cluster: Confirmed** (§9a row 1): at `r` = 0.0 · 0.2 · 0.5 · 0.8 a repair was admitted with the usage 4 MiB below `(1 − r) × 1 GiB` and refused 4 MiB above it, on the participant (arm P) and on the coordinator (arm K), the check's operand equal to the plan to the fifth decimal (0.9961 / 1.00391 … 0.1961 / 0.20391) and nothing validated, snapshotted or streamed for a refused repair; all six repair kinds refused; **default refuses above 100 %, as recorded** (`(100.39%) above threshold (100.00%)`); **unvalidated yaml, as recorded** (1.5 starts, refuses at 0.02 %, JMX refuses 1.5); **admission only, as recorded** (arm O: admitted at 0.4961, node 2 then grew by exactly the streamed 268,649,724 B to 0.746 of the cap, 264,455,420 B past the line, with no further check); no run 2
>
> **Path:** long. One results file per path, each in its path's folder.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `d47b932` (the last commit touching the case file) plus the step-0 amendments of 2026-10-15 (uncommitted at freeze). §9 hash before the amendments `3a3aefa2f3575896eb55a617a0d2f9d705a1f43c`, §9a `f04a15be5d9fc2a2bd36f929a0455cdd3401b69d`; **after the amendments §9 `02afe6f03b5414ecd41d93c6cae59cec701107f0`, §9a `f04a15be5d9fc2a2bd36f929a0455cdd3401b69d` (unchanged)**. §9a is frozen at this version. Recorded 2026-10-15 09:07 EDT, before any reading of this case existed (no `hdr` folder under `pc57:~/stage4-logs/`, no `~/stage4-hdr/`). |
| **Harness** | `../harness/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio/`, written after the freeze (§1.2). Node copy `pc57:~/stage4-harness-run/hdr/`. |
| **Tiers and values** | Unit: upstream `ActiveRepairServiceTest`, `GuardrailDiskUsageTest`; harness U1–U4 (`r` 0.0 · 0.2 · 0.5 · 0.8 · 1.0). Cluster (two nodes on `pc57`, loopback 127.0.0.2/.3, RF 2, cap 1 GiB): `r` = 0.0 (default) · 0.2 · 0.5 · 0.8 on the participant (arm P) and the coordinator (arm K), six repair kinds at 0.5 (phase T), yaml 1.5 (arm V), overshoot at 0.5 then 0.2 (arm O). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-15 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Data-directory apparent bytes plus memtables against `(1 − r) × T` (§4); arm O's streamed SSTable bytes are real blocks. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 0.0 (default), 0.2, 0.5, 0.8 on both decision points (9b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | The sweep sets usage with a **sparse** pad (apparent bytes, what the check counts, no blocks); the gap is named (9a "Why the operand line and the log, not `du` alone"). Arm O measures real bytes (`du -sB1`, walk). An admission check gates a future write, so the sweep's resource is the line itself; arm O is the real-byte reading. |
| A. Core question | usage driven to the limit and past it | Met | `U0 = L ± δ` at every ratio; arm O crosses `L` with real data. |
| B. Logic | each step says what it establishes | Met | 9a Logic (1)–(5). |
| B. Logic | prediction stated in numbers or a clear relation | Met | `u` per trigger to 5 decimals (table), `ERROR` percentages, arm O's `U1 − L = S − δ` band. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | 14 rows incl. *usage exceeds the limit* (B admitted), *flat* (boundary not moving), *counter capped but resource grows* (arm O growth beyond `S`), *another refusal source*, invalid. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Boundary per `r` and the refusing node's own `ERROR` line plus `HDR verdict admit=false`. |
| B. Logic | alternative explanations and their controls | Met | Pending-compactions refusal (different text), `Endpoint not alive` / `Did not get replies` rows; arm K as control for arm P; ratio-0 control repair before each ratio. |
| C. Specific | a human can follow it from the intro and §9a | Met | — |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Layout, pad rule, commands, reset and the Byteman rules are given. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after recs. 1–4 | U1 at `r` = 1.0 asked for a negative usage (rec. 1); U4a's admitted case would race the RPC-timeout task (rec. 2); the walk's rule for non-regular files was implicit (rec. 3); arm O's `S_prv` source if the preview logs no `Accepting` line (rec. 4). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Listed as step-1 work (9c); `~/cassandra-run1` at `b5f2a54` is built; the `repair_session_space` two-node harness exists to adapt. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Pads are sparse (no blocks); arm O writes 4,096 × 65,536 B ≈ 268 MB per node, about 0.6 GB real in all; `pc57` `/` has 48 GB free; two 2 GiB heaps; about 45 repairs, ≈ 30 min. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `ActiveRepairService.java:636-662` (both checks, `ERROR` text and percentages), `:665-716` (coordinator: check, `failRepair`, registration at `:674`, `PREPARE_MSG`, RPC-timeout task `:706-714`), `:720-765` (`Got negative replies from endpoints …`), `:856-863`, `:1082-1090`; `DatabaseDescriptor.java:5340-5352` (range check in the setter only; `repair_disk_headroom_reject_ratio` appears nowhere else in `src/`); `RepairMessageVerbHandler.java:100-160` (participant: register, check, `Not enough disk headroom to perform repair`, `sendFailureResponse`); `RepairCoordinator.java:295-460` (`getColumnFamilies()` skips only a keyspace with **no tables**, so the empty table of phase S does reach `prepare()`; `notifyStarting`, `maybeStoreParentRepairStart` before `prepare`; no kind test before it); `DiskUsageMonitor.java:58-186`, `:203-258` (walk, file-store usable, cap `min`, memtables after the cap, `RoundingMode.UP`, 5 decimals); `FileUtils.java:497-529`; `Directories.java:787-790`, `:865-871`; `GuardrailsOptions.java:86-87`, `:1250-1261`; `StreamSession.java:795-821`, `:878-1004` (`Accepting incoming files … newStreamTotalBytes` at INFO on the receiver, from the summaries' `totalSize`); `LocalSyncTask.java:81-85` (`StreamOperation.REPAIR`, also for previews); `LocalRepairTables.java:419`, `:486` (`failure_cause`); nodetool `Repair.java:102-106`, `:178`, `:188` (paxos-only). Arithmetic of 9a's table re-done (`L ± δ` over `C`, rounded up): all eight `u` values hold. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | U1 at `r` = 1.0: test `u` = 0.0 (`true`) and 0.00001 (`false`) instead of the triple. | Applied 2026-10-15 (9 intro amendment (1), 9e unit step 2); uncommitted | `1 − r − 0.00001` is negative at `r` = 1.0, a value the operand never takes. |
| 2 | U4a's admitted case: check registration at once after `prepareForRepair`. | Applied 2026-10-15 (amendment (2), 9e unit step 5) | With no endpoints only the RPC-timeout task completes the promise, and it fails it. |
| 3 | State the walk rule for non-regular files: `lstat` size of every non-directory entry, no symlink followed. | Applied 2026-10-15 (amendment (3)) | Matches `visitFile`; no symlinks are expected, but the rule is now exact. |
| 4 | Arm O: a fallback source for `S_prv` if a preview logs no `Accepting` line. | Applied 2026-10-15 (amendment (4)) | `checkAvailableDiskSpaceAndCompactions` runs for `StreamOperation.REPAIR`, which previews use too, so the line is expected; the fallback avoids a stop if it is not there. |
| 5 | Measure the participant decision point with more than one participant (RF 3), where others may accept first (§5). | Left for stage 3 | Bookkeeping only (§5); not needed for the core question. |

**Agreement criteria** — not filled (run 2 not chosen yet).

### 1.2 Instrument checks (not readings)

- **Unit instrument runs** (`~/cassandra-run3`): first (09:12) upstream `ActiveRepairServiceTest` 16/16 and `GuardrailDiskUsageTest`
  13/13; harness U1/U2/U4a 92 checks with 11 MISMATCH and U3 not compiled. All were harness defects: the expected `ERROR` text
  lacked the doubled prefix (`[[repair #…]]`, as §5 and 9d say), and U3's package directory did not exist in the clone. Fixed;
  second run (09:14) 92 + 36 + 7 checks, 0 MISMATCH.
- **Byteman:** `headroom.btm` type-checks (`TestScript: no errors`, logged by `setup`).
- **Cluster shakedown 1** (`~/stage4-logs/hdr/shakedown1/`, 09:21–09:28, `HDR_RATIOS=0.5`, so not a reading): every label ran;
  one harness defect: on a **coordinator** refusal the `ERROR` filter `Rejecting incoming repair, disk usage` also matched
  `RepairCoordinator`'s `Repair <id> failed: … disk usage above threshold` line, so arm K's and phase T's node-1 triggers counted
  two lines (7 NO). The filter became `disk usage (` (the check's own text); checked on the shakedown's node logs: node 1 then
  counts 7 lines (1 sweep-K refusal + 6 phase-T), node 2 counts 9. §9 unchanged.
- Harness copy `~/stage4-harness-run/hdr/` identical to the repository by `md5sum` (`~/stage4-harness-run/hdr.md5`) before run 1.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-15, 09:30–09:42 EDT |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu`), 32 cores, 251 GiB RAM |
| OS and kernel (`uname -r`) | Ubuntu, 5.15.0-187-generic |
| JDK (`java -version`) | OpenJDK 11.0.32.1 |
| Ant (`ant -version`) | 1.10.12 |
| Local `cassandra-src` clone commit | unit tier `~/cassandra-run3`, cluster tier `~/cassandra-run1`, both `b5f2a54` (`cassandra-5.0.9`) |
| Case-file commit / harness commit | `d47b932` + uncommitted amendments (§1) / harness uncommitted, md5 list `~/stage4-harness-run/hdr.md5` |
| Storage for node data | local disk `/dev/sda3` (`~/stage4-hdr/N1`, `N2`), 51 GB free at `setup`; the pads are sparse |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/hdr/` (`instrument*/`, `shakedown1/`, `run1-aborted-0929/`, `run1/` with `unit/` and one folder per label; node logs and yamls in `run1/down/`) |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1, unit tier (09:29) | 9e unit step 1 | The two upstream classes failed to **compile**: another case's harness test (`DobRecycleTest.java`, being written at the same time) had a compile error and had been copied into the same clone's test tree. Not this case's design. | The other test fixed; the chain stopped before its cluster tier and run 1 restarted from the unit tier (09:30); the aborted logs kept as `run1-aborted-0929/`. | 2026-10-15 09:30 | none needed (environment) |

## 4. Run 1

**Scope:** unit tier (upstream 2 classes, harness U1–U4) and the whole cluster tier of 9e (`setup`, `idle`, `sweep-p`, `sweep-k`,
`types`, `valid`, `load`, `overshoot`, `down`) in one chain, 09:30–09:42 EDT. **Command log:** `run1/chain-head.txt`, each
label's `run1/cluster/<label>/summary.txt` (every trigger's plan, Byteman lines, `ERROR` lines and `nodetool` tail);
`triggers.csv`; full `session.log` on the node. Raw excerpts: `run1/cluster/N1-hdr.trace`, `N2-hdr.trace` (the whole Byteman
traces), `N1-log.txt`, `N2-log.txt` (every check, coordinator, stream, validation and snapshot line of `system.log`, plus the
DEBUG lines of `debug.log`), `overshoot/samples.csv`, the yaml tails.

### 4.1 Readings

**Unit tier** (`run1/unit/*.out`): upstream `ActiveRepairServiceTest` 16/16, `GuardrailDiskUsageTest` 13/13; harness **135
checks, 0 MISMATCH**:

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| U1: `u` = 1 − r − 0.00001 / 1 − r / 1 − r + 0.00001 at r = 0.0 · 0.2 · 0.5 · 0.8 | `true` / `true` / `false` each; each `false` logs `[[repair #<id>]] Rejecting incoming repair, disk usage (…%) above threshold (…%)` with `%.2f` of `u` and `1 − r` | `U1-U2-U4a.out` |
| U1: r = 1.0 (u 0.0 / 0.00001); default (u 1.0 / 1.00001 / 5.0); IEEE `(1 − r) + r == 1.0` for r = 0.1 … 0.9 | `true` / `false`; `true` / `false` / `false`; all nine sums exactly 1.0 and admitted at the boundary | same |
| U2: setter and MBean reject −0.01 and 1.01 (text `Value must be >= 0 and <= 1 …`), value unchanged; accept 0.0, 1.0; raw config 1.5 refuses at u = 0.00001 with `(-50.00%)` | as predicted | same |
| U4a: `prepareForRepair` at u = 0.50001, r = 0.5, `NONE`/`ALL` × incremental: `RuntimeException("Rejecting incoming repair, disk usage above threshold")`, nothing registered, prefix per kind; at 0.5 registered | as predicted (all four) | same |
| U4b: `PREPARE_MSG` at 0.50001 → `FAILURE_RSP` `UNKNOWN`, failure cause `Not enough disk headroom to perform repair`, nothing registered, one `ERROR`; the same message again → `FAILURE_RSP`, no second `ERROR`; at 0.5 → `REPAIR_RSP`, registered | as predicted (all four kinds) | `U4b.out` |
| U3: empty 0.0; 1 B → 0.00001; + sparse 524,288 B → 0.50001; + hard link → 1.00001; + 1,000 B under `snapshots/x/` → 1.00096; uncapped within one rounding step | as predicted | `U3.out` |

**Cluster tier** — *C* = 1 GiB on both nodes (`data_disk_usage_max_disk_size: 1073741824B`, read back over JMX); `u` from the
`HDR usage` line of the knob node; all from `run1/cluster/*`:

| `r` | Arm | Scenario (planned `U0`) | `u` (plan) | Verdict, evidence | Evidence (file) |
|---|---|---|---|---|---|
| 0.0 | P (node 2) | A 1,069,547,520 / B 1,077,936,128 | 0.9961 / 1.00391 (0.9961 / 1.00391) | A admitted (both nodes `admit=true`, rc 0, `finished`); B refused on node 2: `(100.39%) above threshold (100.00%)`, `failure_cause` `Not enough disk headroom to perform repair`, rc 2 `Got negative replies from endpoints [/127.0.0.3:7010]`, node 1 admitted, no merkle/stream/snapshot line, table directories unchanged | `sweep-p/summary.txt`, `N2-hdr.trace`, `N2-log.txt` |
| 0.2 | P | 854,799,155 / 863,187,763 | 0.7961 / 0.80391 | A admitted; B refused `(80.39%)` / `(80.00%)`, as above | same |
| 0.5 | P | 532,676,608 / 541,065,216 | 0.4961 / 0.50391 | A admitted; B refused `(50.39%)` / `(50.00%)` | same |
| 0.8 | P | 210,554,061 / 218,942,669 | 0.1961 / 0.20391 | A admitted; B refused `(20.39%)` / `(20.00%)` | same |
| 0.0 · 0.2 · 0.5 · 0.8 | K (node 1) | the same `U0` on node 1 | the same `u` to the fifth decimal | A admitted; B refused **on the coordinator**: one `HDR usage` line on node 1 only (node 2 never asked), node 1's `ERROR` with the same percentages, rc 2 `Rejecting incoming repair, disk usage above threshold`, nothing started | `sweep-k/summary.txt`, `N1-hdr.trace`, `N1-log.txt` |
| — | controls | ratio 0, no pad, before every ratio; idle 30 s | `u` 0.00015–0.0002 | 8 controls admitted on both nodes; no `HDR` line in 30 s idle | `sweep-*/summary.txt`, `idle/summary.txt` |
| 0.5 | T, node 2 then node 1 | B (541,065,216) | 0.50391 | `repair` (incremental), `-full -pr`, `--preview -full`, `--preview`, `--validate`, `--paxos-only`: **all 12 refused**, prefix `[[preview repair #` for the three previews (`repair_participates.preview_kind` ALL · UNREPAIRED · REPAIRED) and `[[repair #` for the others; no anticompaction line | `types/summary.txt`, `N*-log.txt` |
| 1.5 (yaml) | V, node 2 | no pad | 0.0002 | node 2 starts, JMX reads 1.5; the repair refused `(0.02%) above threshold (-50.00%)`; JMX write of 1.5 → `IllegalArgumentException: Value must be >= 0 and <= 1 for repair_disk_headroom_reject_ratio`; after a JMX write of 0.0 admitted; restart without the line reads 0.0 | `valid/summary.txt`, `N2-log.txt` |
| 0 | O, load | 4,096 × 65,536 random B at ONE, node 2 down | — | node 1 `hdr` 268,658,076 B (`du -sb`); node 2 no `Data.db` before and after its restart | `load/summary.txt` |
| 0 | O, preview | — | — | node 2 `Accepting … newStreamTotalBytes=268,649,724`; `Total estimated streaming: 2 ranges, 14 sstables, 256.204MiB` | `overshoot/summary.txt`, `N2-log.txt` |
| 0.5 | O, repair | `U0` 532,676,608 (pad on node 2) | 0.4961 (0.49610) | **admitted**; node 2 `Accepting … 268,649,724` (= the preview's); walk 532,676,608 → **801,326,332** (growth = *S* exactly; *u*1 = 0.74629); **264,455,420 B past `L`** (= *S* − 4 MiB); 21 samples at 1 s, first above `L` 3.0 s after the start, **no further `HDR usage` line**; node 1's walk unchanged (268,867,707) | `overshoot/summary.txt`, `samples.csv`, `N2-hdr.trace` |
| 0.5 / 0.2 | O, re-checks | the same pad | 0.74631 | at 0.5 refused `(74.63%) above threshold (50.00%)`; at 0.2 admitted | same |

### 4.2 Conclusion and logic

1. **Validity** — valid. Free space 51 GB (≥ 2 GiB) [observed: `setup/summary.txt`]; cap and ratio read back `1073741824B` /
   `0.0` on both nodes [observed]; every ratio write read back [observed: `KNOB` lines]; the instrument repair's operand equals
   the walk's `D/C` (0.00014 vs 0.000135, 0.00012 vs 0.000119) [observed]; node 2 held no `hdr.t` data before arm O's repair
   [observed: `load/summary.txt`]; no refusal with another message [observed: `N*-log.txt` has only this check's text and the
   coordinator's derived `Repair … failed` lines]. Hinted handoff off (yaml tail).
2. **Readings** — nothing contradicts another. The operand matched the plan to the fifth decimal in all 24 sweep triggers
   and all 12 phase-T triggers (memtables and system-table drift stayed below 0.00001 of the cap). The `u` of the 0.5/0.2 re-checks
   (0.74631) is 0.00002 above *u*1 = 0.74629: the coordinator's and the earlier repairs' system rows in memtables.
3. **Matched row** — "Every trigger's verdict matches the table on both arms (A admitted, B refused, at 0.0, 0.2, 0.5, 0.8); each
   refusal has the refusing node's `ERROR` line with the predicted percentages and no validation or stream line; the operand
   lines are within ±0.0005; phase T refuses all six kinds" → **Confirmed** [observed: §4.1 rows P, K, T]. Also matched:
   "Arm O admitted at `u` ≈ 0.4961, the receiving node grew by `S` ± 1 MiB to above `L` with no further check, and the re-check
   is refused at 0.5 and admitted at 0.2" → **Admission only, as recorded** (`U1 − L` = 264,455,420 B, 0.246 *C*); "`r` = 0.0,
   scenario B refused with `(100.39%)`" → **Default refuses above 100 %, as recorded**; "Arm V starts, reads 1.5 and refuses
   every repair; the JMX write of 1.5 fails" → **Unvalidated yaml, as recorded** [observed].
4. **Excluded rows** — *B admitted with `u + r > 1`*: none (every B verdict `false`). *A refused by this check*: none. *A refused
   repair logs validation/snapshot/stream/anticompaction, or its directory changes*: no such line in the 3 s after any of the 20
   refusals on either node, directories unchanged [observed]. *Boundary not moving with `r`*: it moves exactly with `(1 − r) C`.
   *Operand off by > 0.0005*: largest difference 0.00000. *A kind admitted*: none. *Arm O third `HDR` line or abort*: none.
   *Arm O growth outside `S` ± 1 MiB + 2 %*: growth = *S* to the byte. *Another refusal message*: none. *Invalid*: excluded by
   part 1.
5. **Observed vs. inferred** — All load-bearing statements are observed. Inferred: that the sparse pad stands for real data in
   the sweep (the check reads apparent bytes, §4; arm O shows the same decision with real blocks) [inferred: §4 and arm O].
6. **Deviations and gaps** — The unit tier restarted once for an environment defect (§3). RF 3 (other participants accepting
   first) and concurrent repairs (the sum `W` of §8) are not tested (scope). The sweep's pad is virtual by design.
7. **Core question** — Following 9a's logic: (1) the operand line shows the usage the pad set (part 2); (2) below `(1 − r) C`
   every repair is admitted and completes (part 3); (3) above it the refusing node's own `ERROR` line and nothing started (part
   3, 4); (4) the boundary sits at `(1 − r) C` at all four ratios on both decision points (part 3); (5) an admitted repair is not
   re-checked and its writes take the node past the line by exactly what it streamed, while a later repair is refused (arm O).
   So the ratio caps the **usage at which a repair may start** on each node, and usage follows it; it does **not** cap the usage
   a started repair produces.

**Conclusion (one line):** §9a row 1 — **confirmed**, both tiers; rows "Admission only", "Default refuses above 100 %" and
"Unvalidated yaml" — **as recorded**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

An independent script, `run1/selfcheck.py`, re-parses both nodes' Byteman traces and log excerpts, takes from `summary.txt` only
each trigger's name, plan and repair id, recomputes `ceil5(U0/C)`, the verdict `u + r > 1`, the `ERROR` text and the 3-second
"nothing started" window per refusal, arm O from `samples.csv` and the `Accepting` lines, and the unit counts. It exited 0:
**231 ok, 0 fail** (`run1/selfcheck.txt`). Two defects in the self-check itself were fixed before that result (the log excerpt
first concatenated `system.log` with `debug.log`, which repeats every INFO/ERROR line; two selectors used names without the
phase prefix and caught the sweep's own r = 0.2 lines) — neither touched a reading.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `setup/summary.txt` (read-backs, df, instrument repair), `load/summary.txt`, yaml tails. |
| 2. Readings | yes | Operands re-derived from `N*-hdr.trace` for all 37 sweep/types/setup triggers (selfcheck "operand … within 0.0005"). |
| 3. Matched row | yes | Verdict recomputed from each line; `ERROR` text rebuilt from `u` and `r`; coordinator refusals have no node-2 line; arm O figures re-derived from `samples.csv` and `N2-log.txt`. |
| 4. Excluded rows | yes | The 3-s windows after all 20 refusals hold no merkle/AEService/stream/snapshot/anticompaction line. |
| 5. Observed vs. inferred | yes | The one inference (pad as data) is the design's stated gap; arm O covers it with real bytes. |
| 6. Deviations and gaps | yes | §3 defect is environmental and before any counted reading of this case. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | 9a Logic (1)–(5) each map to observed rows. |

### 5.2 Run 2?

**No** (2026-10-15). Every load-bearing reading is exact and observed (operands to the fifth decimal, verdict and `ERROR` lines,
byte-exact growth in arm O), the self-check holds in every part, and the recorded escapes (admission only, default above 100 %,
unvalidated yaml) were predicted and found as predicted; nothing refutes the case.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** (row 1): the boundary `u + r > 1` exact at five ratios, both decision points refuse and register nothing, the operand on real files (rounding up, apparent sizes, links counted per link); unvalidated raw value as recorded | run 1 + self-check | 2026-10-15 |
| Cluster | **Confirmed** (row 1); **Admission only, as recorded** (arm O: +268,649,724 B after admission, 264,455,420 B past the line); **Default refuses above 100 %, as recorded**; **Unvalidated yaml, as recorded** | run 1 + self-check | 2026-10-15 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" updated (2026-10-15, uncommitted); the §9 intro amendments are in the case
file (uncommitted). No refutation; §8's admission-only claim is now measured (Target-3 note (1) sized).
