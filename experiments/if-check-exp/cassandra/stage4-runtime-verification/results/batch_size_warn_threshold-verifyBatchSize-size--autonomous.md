# batch_size_warn_threshold-verifyBatchSize-size--autonomous — stage-4 results  <!-- file: results/batch_size_warn_threshold-verifyBatchSize-size--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`batch_size_warn_threshold-verifyBatchSize-size--autonomous`](../../stage3-ai-deep-read/cases/batch_size_warn_threshold-verifyBatchSize-size--autonomous.md)
>
> **Status:** **verdict filed 2026-10-26** — unit **Refuted** (does not cap), cluster **Not confirmed** (no matching row for the unit/cluster allocation step; does not cap). Claim tested: the warn threshold does not change the memory or disk a batch uses. Acceptance, rows, disk bytes and write counts are identical at warn 5 KiB and 90000 KiB; the one difference is a step in the coordinator's allocation (+14 % to +20 %) when the warn branch runs. One run 1 per tier, no run 2.
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository HEAD `93d6365` plus the uncommitted file. After the audit's amendments D1 (A1–A9), 2026-10-26, before any harness run or reading: whole file sha256 `e3e5cb792c3a9c2b3b170d7557697408252919abb75aaae0cf92d1cf9cf49c52`. Frozen prediction and conclusion tables, sha256 of the text of B2f–B2g (from `**B2f.` up to `**B2h.`) `6a1af9b22b8215411383474b0590e2de13cdb9579d03ad9ca9835238b947a1c7`, of B3f–B3g (`**B3f.` up to `**B3h.`) `ff3884b93f93617698fa70edb6ed0c4a336476f2f0b24add1bffaafad5190185`. The file's section D2 takes the feedback after the run, so the whole-file hash changes then (after the feedback was filed, 2026-10-26: `488ef5375752cbb2b7c54f2dc5e7245ec83741ea0e36eaecdfb6ecec6df8a541`); the table hashes were re-computed then and are unchanged. |
| **Harness** | `harness/batch_size_warn_threshold-verifyBatchSize-size--autonomous/` (written after this freeze, before run 1; see its README). Uncommitted at run time (the orchestrator commits); its md5 is in each `summary.txt`. |
| **Tiers and values** | Unit: warn 1 · 5 · 1024 · 65536 KiB × LOGGED batches of 20 and 200 partitions (1 KiB each), single-partition control, fail-threshold control, inversion arm. Cluster: one node, 2 GiB heap, warn 5 KiB vs 90000 KiB (two lifetimes), W1 = 2000 LOGGED 50 KiB batches and W2 = 20 UNLOGGED 20 MiB batches, each twice; fail 20 KiB control lifetime and inversion arm. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the batch's coordinator heap and, once applied, memtable and commit-log bytes; honest that the check caps nothing. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b {1, 5, 1024, 65536} KiB, B3b {5, 90000} KiB plus a live change; the cluster has 2 values + the default is one of them (5 KiB), the unit tier has 4. Both limits of the knob are covered. |
| A. Core question | real resource measured, not only the counter | Partly | B2d/B3d named heap after GC and GC log; both are noisy for a per-request cost. **Amended** (A2, A7): thread allocation per request (`bst`), data-directory bytes after flush, write count, post-GC occupancy. The gap (total JVM allocation is not read) is named. |
| A. Core question | usage driven to the limit and past it | Met | batches of 20 KiB to 20 MiB against 5 KiB; dataSize read by the `siz` rule. The "limit" is a size threshold; the row that tied it to heap fill was **amended** (A7). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps are numbered and each ties to a row. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | warn counts, rows, "identical" were exact; "heap within noise" and "peak heap ±10 %" were not defined. **Amended** (A2, A7). |
| B. Logic | every plausible outcome has a conclusions row | Partly | missing: 10–25 % difference, the warn>fail inversion. **Rows added** (A3, A7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | for a negative file: acceptance of a batch past the warn value is the disallow-branch-absent evidence (rows written, no throw) plus the fail control that shows the instruments see a cap. |
| B. Logic | alternative explanations and their controls | Partly | the fail control is valid only with warn < fail (A4, **amended**); the CAS control was invalid (A5, **dropped**). |
| C. Specific | a human can follow it from the intro and prediction/conclusions | Met | the claim and the A3 mechanism are clear. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Not met → fixed | B2e step 2 sends the batch through `CQLTester.execute`, which does not reach `verifyBatchSize` (A1). B3 large run would be discarded by the 16 MiB message limit or fail at `max_mutation_size` as a LOGGED batch (A6). Both **amended**. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | paths (`/local/scratch`), client count, tolerances and the lifetimes were loose; fixed in A6–A8. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | a client, Byteman rules and a runner are step-1 work; the closed `batch_size_fail_threshold` harness (SimpleClient, `stage4.Alloc`, `Jmx`, yaml builder) is reused. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | W1 4 × ~100 MB, W2 4 × 400 MB on tmpfs (126 GiB free); 20 MiB UNLOGGED batches need about 60 MiB transient at a 2 GiB heap. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | all re-read, two nits (A9). Also checked: `Config.java:330` default, `DatabaseDescriptor.java:631`, `:2084`, `StorageService.java:6868`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 (A1) | Unit tier through the in-process native server, not `CQLTester.execute` | Applied 2026-10-26 | the local path skips the check |
| R2 (A2, A7) | Read per-request allocation, data bytes after flush, post-GC occupancy, write count | Applied 2026-10-26 | noisy heap readings cannot show a flat result |
| R3 (A3) | Scope the claim to warn ≤ fail; add the inversion arm | Applied 2026-10-26 | `:340` gates `:352` |
| R4 (A4) | Control keeps warn below fail | Applied 2026-10-26 | otherwise the control cannot move |
| R5 (A5) | Drop the CAS step | Applied 2026-10-26 | cannot discriminate |
| R6 (A6) | 20 MiB batches UNLOGGED, protocol v4, message and frame limits | Applied 2026-10-26 | otherwise discarded or rejected for another reason |
| R7 (A8) | Paths, lifetimes, single client | Applied 2026-10-26 | environment |
| R8 | The CAS and virtual-table bypasses (A3a/b of the file) are source statements only | Left for stage 3 | not testable without a design of their own |

**Agreement criteria** — only if run 2 is chosen; not chosen (see 5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 19:22 EDT; cluster 19:29–19:39 EDT) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; port slot 1 (127.0.1.1, JMX 7110, Byteman 19110); other sessions ran on the node at the same time | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 | — |
| Ant (`ant -version`) | Apache Ant 1.10.12 | — |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | two copies from `copy-source.sh` at repository HEAD `93d6365` (local baseline `d90a4e7`, tag `cassandra-5.0.9`): `~/s4-b9-bs-u` (`ant build-test`, 1 min 11 s; unit tier) and `~/s4-b9-bs-n` (`ant jar`, 1 min 12 s; node) | — |
| Case-file commit / harness commit | `93d6365` + the uncommitted amendments D1 (file sha256 in §1) / uncommitted; md5 in each `summary.txt`. Unit run 1: `WarnBatches.java` 5c0fb0adb0ea (zero-filled values); cluster run 1: `WarnBatches.java` ee590fd7a9c1 (adds `--random`, used by the cluster only; the unit behaviour is unchanged by default), `cluster-run.py` 9b9b23bee118, `analyze.py` 219422f7a0fa both tiers | — |
| Storage for node data | `/dev/shm/s4-b9-bs` (tmpfs); nothing on `/proj` | — |
| Full logs (path, outside the repo) | `~/s4-b9-bs-logs/run1/{unit,cluster}/` (node `pc07`); shakedowns in `~/s4-b9-bs-logs/shake/` and `shake-unit.out` (plumbing only, not readings) | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | audit | B2e step 2 | `CQLTester.execute` takes `executeLocally`, which never calls `verifyBatchSize` | amendment A1 (native server, v4 client) | 2026-10-26, before any run | uncommitted (orchestrator) |
| D2 | audit | B3c | 20 MiB batch: discarded by the derived 16 MiB message limit, or (LOGGED) over `max_mutation_size` | amendment A6 | 2026-10-26, before any run | uncommitted |
| D3 | shakedown | harness | `phases.csv` was not flushed, so the first cluster analysis had 0 phases; zero-filled values compress 25:1 (disk bytes not a data measure) | flush after each row; `--random` values in the cluster tier | 2026-10-26, before run 1; no prediction touched | harness only |
| D4 | self-check | harness | the first self-check joined Byteman lines to requests by 1 ms intervals and double-counted lines on shared milliseconds | pair by order and check counts and intervals | 2026-10-26; analyzer unchanged | harness only |

No run was restarted for a defect after run 1 began.

## 4. Run 1

**Scope:** both tiers in full. **Command log:** `batch_size_warn_threshold-verifyBatchSize-size--autonomous/run1/` (`unit/summary.txt`, `unit/analysis.txt`, `cluster/summary.txt`, `cluster/phases.csv`; per-request lines stay on the node).

### 4.1 Readings

**Unit tier** (20 LOGGED batches per arm, 1 KiB values, fail 100000 KiB; `unit/analysis.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| instrument: `TestScript` 10 rules; `Alloc` known answer 8,396,728 B | ok | `unit/summary.txt` |
| every request reached `verifyBatchSize` (one `siz` line each), knob bytes seen by the check equal the set values, dataSize 21,960 B (20 partitions) and 219,600 B (200) | yes | `unit/analysis.txt` V1–V6 |
| warn 1 and 5 KiB, 20 and 200 partitions: client warning on 20/20 batches, no throw, rows 400 / 4000 | as predicted | P1 |
| warn 1024 and 65536 KiB: no warning, no throw, rows 400 / 4000 | as predicted | P2 |
| dataSize identical across the four warn values; size in the warning equals the check operand | yes | P3, P3b |
| coordinator allocation (`bst`), 20 partitions: median 195,656 / 193,416 (warn 1 / 5) vs 154,672 / 154,864 (1024 / 65536) | **outside the 10 % / 16 KiB band**: +39.8 KB (20.4 %) | P4 NO; `selfcheck-unit.txt` |
| coordinator allocation, 200 partitions: 1,643,024 / 1,625,988 vs 1,321,744 / 1,321,140 | **outside the band**: +313 KB (19.2 %) | P4 NO |
| single-partition control `sp-w1` (warn 1 KiB): no warning, rows 400, `siz n=1` | as predicted | P5 |
| positive control `fc` (warn 5, fail 10 KiB): 20/20 `Batch too large`, 20 `rej` lines, 0 rows | control moved | C1 |
| inversion arm `inv` (warn 200, fail 10 KiB): 20/20 accepted, no warning, no `rej`, 400 rows | accepted | I1 |

**Cluster tier** (`cluster/summary.txt`, `cluster/phases.csv`; data-directory bytes are cumulative inside a lifetime)

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| yaml warn 5 KiB (L1) | W1a, W1b (2000 LOGGED, 53.6 KiB) | client warnings / rows / alloc median | 2000, 2000 / 100,000 each / 369,380; 367,864 | summary V1, P1 |
| yaml warn 5 KiB | W2a, W2b (20 UNLOGGED, 21.4 MiB) | the same | 20, 20 / 409,600 each / 164,474,032; 164,436,812 | P1 |
| L1 system.log | all four phases | WARN "Batch for [ks.t] is of size" | 4040 (= 2 × (2000 + 20)) | P2, `selfcheck-cluster.txt` |
| yaml warn 90000 KiB (L2) | W1a, W1b, W2a, W2b | client warnings / rows / alloc median | 0 in all / same rows / 296,120; 294,584; 141,129,984; 141,009,576 | P1, P3 |
| L2 system.log | — | WARN lines | 0 | P2 |
| L1 then warn set live to 90000 KiB over JMX | L1live-W1, -W2 | warnings / alloc median | 0, 0 / 290,520; 140,153,612 | P6 |
| L1 vs L2 | each of the four phases | data-directory bytes after flush | 106,223,596 vs 106,195,468; 212,468,518 vs 212,412,324; 646,137,448 vs 646,095,135; 1,079,851,696 vs 1,079,800,228 (all within 0.03 %) | P4 |
| L1 vs L2 | each of the four phases | writes (`WriteLatency` count) | equal: 100,000 / 100,000 / 409,600 / 409,600 | P5 |
| L1 vs L2 | each | coordinator allocation, L1 minus L2 | +73,260 B (19.8 %), +73,280 B (19.9 %), +23.34 MB (14.2 %), +23.43 MB (14.2 %) = 1.47 KB, 1.47 KB, 1.14 KB, 1.14 KB per mutation | P3 NO; `selfcheck-cluster.txt` |
| L1 vs L2 | W2a, W2b | largest post-collection occupancy | 2028 vs 2028 MiB; 1995 vs 1550 MiB (22 %); W1 phases 252/240 and 487/445 MiB | INFO lines |
| L3: yaml warn 5, fail 20 KiB | L3-ctl (2000 LOGGED) | outcomes / writes / data bytes / ERROR lines | 2000 `Batch too large`, 2000 `rej` / 0 / 100 B / 2000 | C1, C2 |
| L3, warn set live to 200 KiB | L3-inv (200 LOGGED) | outcomes / writes | 200 accepted, 0 warnings, 0 `rej` / 10,000 | I1 |

### 4.2 Conclusion and logic

1. **Validity** — **[observed: `cluster/summary.txt`]** every request reached `verifyBatchSize` (V1), the check saw the intended warn and fail bytes in every phase (V2: warn 5120 / 92,160,000 / 204,800, fail 102,400,000 / 20,480), the dataSize of every batch (54,900 B and 22,487,040 B) is above the lowest warn value (V3); the heap was `-Xms2G -Xmx2G` and 10 Byteman rules loaded at every start; idle controls showed no trace line. **[observed: `unit/summary.txt`]** the same for the unit arms and the `Alloc` known answer. The run is valid.
2. **Readings** — **[observed]** unit P4 and cluster P3 (coordinator allocation) differ between warned and silent arms; everything else in the prediction matches. In the cluster the post-GC maximum is not usable for W1 (0 to 3 collections in the window) and varies 0 % to 22 % in W2 (one phase, 1995 vs 1550 MiB, the heap near its 2 GiB limit and 11 vs 4 collections); the 100 ms heap poll hits the 2 GiB limit in W2 in both lifetimes. Zero-filled test data compress, so the unit tier gives no disk reading (the cluster used incompressible values).
3. **Matched row** — Unit, B2g (added row, A2): "Allocation medians for one batch size differ by more than the B2f band, tracking the warn value → **Claim refuted (usage follows the knob)**": 20.4 % / 19.2 % against a band of max(10 %, 16 KiB) **[observed: `selfcheck-unit.txt`]**. The first row ("warning present below threshold, rows all written, dataSize equal") also holds, but it is the allocation clause of B2f that decides. Cluster, B3g (added row, A7): "Allocation, disk or post-GC occupancy differ between the lifetimes by 10 to 25 % → **Not confirmed (no matching row)**": allocation +14.2 % to +19.9 % **[observed: `selfcheck-cluster.txt`]**; disk, rows and writes are equal.
4. **Excluded rows** — Cluster "WARN lines only differ; heap, disk, rows within noise → Confirmed": excluded, allocation is outside the noise band (the L1live phases equal L2 within 2 %, and the two repeats agree within 0.5 %, so it is not noise **[observed]**). "Differs by more than 25 % → Refuted": excluded, the largest difference is 19.9 % (allocation) and 22 % (one post-GC maximum). "Batches rejected at warn 5 KiB → Refuted": excluded, 0 rejections in L1 (P1). "Fail control also accepts everything → Not confirmed": excluded, 2000/2000 rejected (C1). "Limit never reached → Not confirmed": excluded, the dataSize is 10× to 4400× the warn value (V3). Unit: "Exception at a warn-only value": excluded (P1); "Row count or dataSize varies with warn": excluded (P2, P3); "Fail=10 KiB does not reject": excluded (C1); "dataSize never exceeds the smaller thresholds": excluded (V6).
5. **Observed vs. inferred** — Inferred: (a) the allocation step comes from work the warn branch does, per mutation: `BatchStatement.java:342-346` calls `update.metadata().toString()` for each mutation, and `TableMetadata.toString()` is a `String.format` (`TableMetadata.java:793`). **[inferred: the cost per mutation is steady at 1.1 to 2.0 KB across 20, 50, 200 and 20,480 mutations; not isolated — the rejected arm `fc` also runs that loop and reads 155,456 B, the same as the silent arms, because it also skips the mutation write]**. (b) "does not cap" for disk and memory rests on equal acceptance, rows, data bytes and the absence of any reduction of allocation or occupancy at the low threshold. (c) The coordinator thread's allocation stands for the memory a batch costs; JVM-wide allocation and the replica-side work were not read.
6. **Deviations and gaps** — the amendments A1–A8 (§1). One client connection, one batch in flight (A8), so concurrency was not tested. The unit tier used zero-filled values (the cluster random ones). The heap approached its 2 GiB limit in W2 in both lifetimes, so the post-GC maximum is a weak comparison there. The CAS and virtual-table bypasses were not measured (A5). Another session's unit test and node ran on the host at the same time; the allocation reading is per thread and does not depend on that.
7. **Core question** — The warn threshold does not cap memory or disk: at warn 5 KiB, 40 batches of 22 MiB and 4000 batches of 53.6 KiB were accepted in full (rows, writes and 1.08 GB of data identical to the run with warn 90000 KiB), and the only thing the threshold changed was a WARN line, a client warning, and a step of 14 % to 20 % **more** coordinator allocation when it fires (step 3, 5a). So usage does follow the knob in one sense that the claim as written excluded — it rises, it does not fall — and no sense of a cap. The fail threshold is a control that binds only when the warn gate is passed: it rejected 2000/2000 batches with 0 rows and 100 B on disk (steps 1, 3).

**Conclusion (one line):** unit — "allocation medians differ by more than the band" (**Refuted**, does not cap); cluster — "10 to 25 % difference" (**Not confirmed, no matching row for a systematic step**, does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-parsed with `harness/.../selfcheck.py`, which pairs Byteman lines to requests by order and checks counts and intervals (not by arm window), counts WARN/ERROR with regexes over the raw `system-*.log` and re-reads the GC logs (`run1/selfcheck-unit.txt`, `run1/selfcheck-cluster.txt`).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | counts of `bst`, `siz` pair with the requests in every arm and phase; `rej` equals the number of errors (20 in `fc`, 2000 in `L3-ctl`); 4040 / 0 / 0 WARN and 0 / 0 / 2000 ERROR lines in `system-L1/L2/L3.log`; "OutOfMemory" in the logs is only the JVM flag text; no OOM |
| 2. Readings | yes | the self-check medians equal the analyzer's within 0.1 % (369,380; 296,120; 164,474,032; 141,129,984 …) |
| 3. Matched row | yes | the step is +39.8 KB / +313 KB (unit) and +73 KB / +23.4 MB (cluster) against bands fixed before the run; the unit band is exceeded, the cluster step is in the 10–25 % row |
| 4. Excluded rows | yes | L1live vs L2 −1.9 % / −0.7 %: the step follows the warn value in force, not the lifetime; repeats agree to 0.5 % |
| 5. Observed vs. inferred | yes | (a) is marked inferred and not isolated; the verdict does not depend on it |
| 6. Deviations and gaps | yes | listed above; none changes a row |
| 7. Core question | yes | the steps follow the audited logic: warn fires, batch accepted in full, disk/rows/writes equal, control rejects |

One wording point the user may overrule: the frozen added rows call the 10–25 % case "noise too large, rerun". The self-check shows it is a stable, systematic step, so a rerun would not change it; the cluster verdict stays "Not confirmed" because no row names a stable step below 25 %.

### 5.2 Run 2?

**No** (2026-10-26). The difference is reproduced in both tiers, in two repeats per lifetime and by the live switch; disk, rows and writes are exactly equal; a second run would not change either tier's row. The one open item is the cause of the allocation step (inferred), which is a micro-diagnosis and not needed for the verdict.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative estimate, effect `does not cap`). The allocation step makes the claim as worded ("does not change the memory a batch uses") fail in the unit tier; the effect on the constraint is still not a cap.

**Claim tested:** (B1) raising or lowering `batch_size_warn_threshold` does not change the memory or disk a multi-partition batch uses: a batch larger than the threshold is still fully executed (only a WARN and a client warning appear), and usage for a given workload is the same for warn = 5 KiB and a very large value. "Confirmed" below means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Refuted** — allocation medians differ by more than the band (+20 % at 20 partitions, +19 % at 200); acceptance, rows and dataSize as predicted | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Not confirmed** (no matching row for a stable step) — allocation +14 % to +20 % between warn 5 KiB and 90000 KiB; rows, writes, disk bytes equal; 4040 vs 0 WARN lines; live change takes effect without restart | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** the fail threshold, with warn kept below it. Unit `fc`: 20/20 batches rejected, 0 rows. Cluster `L3-ctl`: 2000/2000 rejected, 0 writes, 100 B on disk, against 106 MB for the same workload accepted. The control moved disk and rows; it did not move coordinator allocation (the batch is built before the check), as the file's A4 predicted.

**Extra finding (not a verdict row):** the inversion arm. With warn above fail (unit: warn 200, fail 10 KiB; cluster: warn 200, fail 20 KiB) a batch over the fail threshold is **accepted with no warning and no rejection** (unit 20/20, cluster 200/200 with 10,000 writes), because `verifyBatchSize` enters the fail check only inside `if (size > warnThreshold)` (`BatchStatement.java:340-352`). A warn value above fail silently disables the fail threshold; nothing in `DatabaseDescriptor` cross-validates the two (case file A3). That is a bypass of the fail cap by the warn knob, to be carried to Target 3.

**Feedback filed:** the case file's section D1 (amendments A1–A9) and D2 (result) — uncommitted, for the orchestrator; nothing else amended. Leftovers on `pc07`: `~/s4-b9-bs-u`, `~/s4-b9-bs-n`, `~/s4-b9-bs-node`, `~/s4-b9-bs-logs`; `/dev/shm/s4-b9-bs` removed; no process left (checked with `ps`).
