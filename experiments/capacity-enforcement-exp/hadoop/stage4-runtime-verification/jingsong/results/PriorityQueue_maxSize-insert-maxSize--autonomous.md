# PriorityQueue_maxSize-insert-maxSize--autonomous — stage-4 results  <!-- file: results/PriorityQueue_maxSize-insert-maxSize--autonomous.md -->

> **Case:** [`PriorityQueue_maxSize-insert-maxSize--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/PriorityQueue_maxSize-insert-maxSize--autonomous.md) (queue order 9)
>
> **Status:** **verdict filed 2026-11-25** (outside the repository) — unit **Confirmed — does not cap**, cluster **Confirmed — does not cap**. Unit: `allocCtor` = exactly 16+4·(k+1)+24 B (48 … 262,192 B) while 200,000 inserts past the limit allocated 0 B and left `heap.length` = k+1 (k = 1 … 65,536, 3 repeats); `insert` reached 0 times in 4 real-caller merges under jdb (`initialize` 20 / 1 / 12 / 3); 0 call sites in a static scan. Cluster: `insert` 0 times in a terasort reducer (f = 2 / 10 / 100: `initialize` 15 / 9 / 9 = logged merge passes) and a DistCp client (f = 2 / 100: 18 / 2); 0 call sites in 536,463 distribution classes. One cluster runbook defect (A10), tier restarted. One run 1, no run 2.
>
> **Outcome class:** **true negative** — stage-3 estimate `negative` against the stage-4 effect `does not cap` (both tiers) ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Written outside the repository by the stage-4 agent of 2026-11-25 (`~/writeup-hadoop/out/o9/`): this file,
`case-amended.md` (the filed case file plus amendment A9 and the section-D feedback), `harness/` (the instruments) and
`run1/` (small raw files copied from the node). For filing, this file goes to
`hadoop/stage4-runtime-verification/jingsong/results/`, the harness to `../harness/PriorityQueue_maxSize-insert-maxSize--autonomous/`
and the raw excerpts to `results/PriorityQueue_maxSize-insert-maxSize--autonomous/run1/`. Paths `run1/...` below are relative to
`~/writeup-hadoop/out/o9/`; full logs on the node: `pc75:/mydata/jingsong-s4/PriorityQueue_maxSize-insert-maxSize-run1/{unit,cluster,logs}/`.

**History.** A first stage-4 attempt (2026-11-24, `pc91`) audited the file (A1–A7), recorded one cluster-tier runbook defect
(A8) and was interrupted (API usage limit, then the nodes were reserved). Its partial run folder and draft harness are not used:
this run 1 starts clean on `pc75` (no partial folder for this case existed there), with a harness rewritten from the amendments
(the interrupted drafts are set aside as `harness.draft-2026-11-24-ignored/` and `draft-2026-11-24-ignored.case.md`, unread).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed version, repository commit `cd9e1cded` (HEAD at run time; the file is unchanged since `bef6bc8a6`): sha256 `05d3e7c4c7a3bd3f1a5ba6a6146af3009d874de54b4e4d65b89410886fd3fb7a` (checked = `_INDEX.md` §4 row "filed with … A1–A8"). This audit added **A9** (2026-11-25 04:21 EST = 02:21 MST node time, before any reading): `case-amended.md` sha256 **`972e2a93e53c241aa1325d4889ec80a3cb6a8f3c9cbefbf09c8d69f1fc44feda`** = frozen version. Frozen prediction text: from `**B2f.` to `**B2h.` sha256 `ca6e8c3765a895f26580444098b1114ee1c8061a4749ad9af6522b7d5a288440`; from `**B3f.` to `**B3h.` `c662e57cf18af7a1600e2b71bbba799bc664b04e95a3cb8e4874aa7458f4081e`. Section D takes the feedback after the run, so the whole-file hash changes then; these two text hashes do not. |
| **After the run** | A10 (cluster runbook defect, §3) added after cluster attempt 1: sha256 `68d606a2dd447070e42fbf3b422e90c9b5d92a6d434f3f5db93db50f53ffb176`; section D1 added after the verdict: `211177205f36bc82cddbb0da7c73f5f797f046d1a124c2505dc053afa65adb33` (= `case-amended.md` as delivered). The B2f–B2h and B3f–B3h text hashes are unchanged by both. |
| **Harness** | `harness/` (outside the repo; not committed — this agent does not edit the repository): `TestPriorityQueueInsertCap.java` md5 `f41380b5`, `TestSequenceFileSorterMerge.java` `0fcd1998`, `jdbcount.sh` `6c78bc9c`, `scan_insert.py` `7610a486`, `unit-run.sh` `30edeffc`, `cluster-run.sh` v1 `015169f7` (written after the freeze and the unit run, before any cluster reading; attempt 1) and v2 `8ca9d26e` (A10; attempt 2, the counted cluster run; v1 kept in the session scratchpad only). Instrument checks, all inside run 1 before the readings they guard: allocation known answer `new Object[1024]` = 4112 B (A2 iv); jdb known answer `insert=5 initialize=1 attached=yes` (A2 vi); scanner known answer: 1 HIT in `hadoop-common/target/test-classes` (the harness's own `insert` call) and the two production subclasses found (A3). |
| **Tiers and values** | Unit (B2): k ∈ {1, 16, 1024, 65536} × N ∈ {200000, k/2 (k ≥ 16)}, 3 repeats; `put` control per k; real callers `TestSequenceFileSorterMerge` at `seq.io.sort.factor` 2 and 100, `TestMerger`, `TestSequenceFileMergeProgress` under jdb; static scan of `target/classes`. Cluster (B3): terasort reducer under jdb at `mapreduce.task.io.sort.factor` 2, 10, 100; DistCp client under jdb at factor 2 and 100 (A8 keys); static scan of every jar in the distribution. |
| **Audit bottom line** | **Ready after amendments** (A1–A8 as filed, plus A9) — 2026-11-25 |

### 1.1 Design audit

Audit of the filed version (with A1–A8), made afresh by this agent; ratings are for the file as it stood at the freeze.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: element count of the heap array, with its byte size derived (`16 + 4·(k+1)`, A4); the real resource is the array allocated by `initialize` and anything allocated per insert. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | `maxSize` is not a configuration value (A1) and has no default; B2b varies the operand k over 4 values directly; the user-facing factors that reach it are varied in the reachability runs (unit 2/100; cluster 2/10 (default)/100, B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d: thread-allocated bytes (exact with TLAB off) and `heap.length` by reflection besides `size()`; the gap (no retained-heap tool) is named. |
| A. Core question | usage driven to the limit and past it | Met | N = 200000 ≥ 3k for every k: the false branch of `:74` runs ≥ 134464 times per row (B2c). |
| A. Core question | positive control (negative estimate) | Met | B2h: `allocCtor` follows k with the same instrument (the binding allocation in `initialize`); `put` past k throws; `initialize` hits in every real-caller run and f = 2 > f = 100 in the cluster (A7). |
| B. Logic | each step says what it establishes | Met | B2c Part 1 (mechanism), Part 2 (reachability), static scan (paths not exercised); B3 ties debugger hits to logged merge passes (A6). |
| B. Logic | prediction stated in numbers or a clear relation | Met | A4 (exact bytes, ≤ 4096 B, exact counts), B3f with A6/A7. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g with A5 (rows 1–10), B3g with A7 (incl. pass-count mismatch, failed job, no attach). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For this negative file: the disallow branch's firing is observed directly (`falses`, `size == k`), and allocation follows `initialize(k)` not N. |
| B. Logic | alternative explanations and their controls | Met | Instrument broken (known answers A2 iv, vi; scanner known answer A3); merge not exercised (`initialize` hits; log pass count A6); element creation (pre-allocated items); JIT/GC (warm-up, three repeats). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, Ground, A3 steps 1–4, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | A1, A3, A6, A8 give commands, keys and paths; A9 fixes the instruments' exact acceptance strings. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | The scanner's matching rule, jdb's attach evidence and the exact log patterns of the pass count were stated only in prose. **Amended** (A9). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness is step-1 work (A1, A3); JDK 8 with `jdb`, Maven 3.6.3, `~/.m2` 3.4.2 artifacts and the base distribution present on `pc75` (`environment.md` §1, §3; checked 02:17 MST). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: 50,000 × ~116 B ≈ 5.8 MB against a 256 KiB run limit (≈ 20 runs); Part 1 ≤ 2 × 262 KB arrays. Cluster: ≈ 3 GB on `/mydata` (700 GB free); 6 GiB NM memory on a 125 GiB node. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source/` (clean): `PriorityQueue.java:30-32, 48-53, 61-65, 73-85`; `Merger.java:607` ("Merging N sorted segments"), `:676` `initialize(segmentsToMerge.size())`, `:678-680` `put`, `:706-713` intermediate-pass log; `SequenceFile.java:2957-2971` (deprecated keys first), `:3018-3021`, `:3079`, `:3664-3667`; `ConfigUtil.java:173-176`; `DistCpUtils.java:469-480`; `CopyListing.java:155`; `MergeManagerImpl.java:179, 358`. A tree-wide grep finds no `.insert(` on a queue of this class. All as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A9) | Restart run 1 clean on `pc75` with a rewritten harness; fix the scanner rule, jdb attach evidence and the exact pass-count patterns | Applied 2026-11-25 (`case-amended.md`; not committed) | instruments must have an exact acceptance before readings |
| R2 | The file calls the reachability "unreachable in a 3.4.2 build"; third-party subclasses of this `@Private` class are out of scope and stated so (A3 step 4). No change. | Left as is | not load-bearing |

**Agreement criteria** — not needed (no run 2; §5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 02:21–02:50 MST (node clock; session clock EST = node + 2 h) |
| Node (CloudLab name and type) | `pc75` = `node3.jason92-326665` (40 cores, 125 GiB RAM) |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK (`java -version`) | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`, with `jdb`) |
| Build tool | Maven 3.6.3; no install build (A1): modules from `~/.m2` (node base build 2026-11-24) |
| Local source copy | `/mydata/jingsong-s4/PriorityQueue_maxSize-insert-maxSize-run1/src` by `copy-source.sh`, from `systems/hadoop/source/` at repository commit `cd9e1cded` (tag `rel/release-3.4.2`) |
| Distribution (cluster) | `cp -a` of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` → `<run>/hadoop` (`Hadoop 3.4.2`) |
| Case-file commit / harness | case file at `cd9e1cded` + A9 (frozen sha256 above) / `harness/` md5s in §1 (uncommitted) |
| Storage for node data | local `/mydata` (753 GB, 700 GB free) |
| Full logs (outside the repo) | `pc75:/mydata/jingsong-s4/PriorityQueue_maxSize-insert-maxSize-run1/{unit,cluster,logs}/`; copies in `run1/` |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1, cluster attempt 1 | B3e step 4 / A6 pass count, as fixed by A9 (iii) | The harness took the reducer log as "the first container `syslog` naming `_r_000000`", which is the AM's; and the reducer's `Merger`/`MergeManagerImpl` lines go to `syslog.shuffle` (`yarn.app.mapreduce.shuffle.log.separate=true` by default). Attempt 1 printed `PASSCOUNT … total=0` for f = 2 and 10 although the reducer had merged (`run1/cluster-attempt1/cluster-run.log`). Readings of attempt 1 (jdb counts) are kept as supplementary only. | **A10**: reducer = the container whose `syslog` holds `Task:attempt_…_r_000000_0 is done`; count over `syslog` + `syslog.shuffle`; copy each application's logs when it ends (`cluster-run.sh` v2, md5 `8ca9d26e`). Claim, predictions and conclusions unchanged. | Cluster tier restarted from its beginning (fresh format) as attempt 2 — 2026-11-25 | not committed (`case-amended.md`, A10) |

## 4. Run 1

**Scope:** unit tier complete (Part 1, put control, jdb known answer, four real-caller runs, static scan); cluster tier
attempt 2 (after defect 1) complete — see 4.1. **Command logs:** `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`
(attempt 2), `run1/cluster-attempt1/cluster-run.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/`, 2026-11-25 02:21–02:24 MST)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| JVM as specified (A1) | JDK `1.8.0_514` HotSpot, max heap 491 MiB (`-Xmx512m`), `UseTLAB=false`, `UseCompressedOops=true`, thread allocation counter supported and enabled | `part1-readings.txt` (`PQCAP env`) |
| Allocation known answer (A2 iv) | `new Object[1024]` = **4112 B** (expect 4112–4176); empty-window baseline 0 | `part1-readings.txt` (`PQCAP instr`) |
| Part 1, `allocCtor` (A4: P(k) … P(k)+64) | k = 1 / 16 / 1024 / 65536 → **48 / 112 / 4,144 / 262,192 B** in every row (both N, all 3 repeats) = P(k) exactly | `part1-readings.txt` (`PQCAP row`) |
| Part 1, `allocInsertLoop` (A4: ≤ 4,096 B, flat) | **0 B** in all 21 rows (k = 1…65536; N = 200,000 and k/2) | same |
| Part 1, `heap.length` before = after; `maxSize` | k+1 = 2 / 17 / 1025 / 65537 before and after in every row; `maxSize` = k | same |
| Part 1, full rows (N = 200,000) | `size` = k; trues + falses = 200,000; trues = 8 / 163 / 6,329 / 138,981 (≥ k); falses = 199,992 / 199,837 / 193,671 / 61,019 — the disallow branch (`size < maxSize` false, element rejected or replacing the root) ran in every row | same |
| Part 1, half rows (N = k/2) | `size` = k/2 (8 / 512 / 32,768); falses = 0; `heap.length` = k+1 | same |
| Part 1, repeats | the three repeats are identical in every column (spread 0 B < 10 % of P(65536)) | same |
| `put` control (B2h) | `ArrayIndexOutOfBoundsException` at put **k+1** for k = 1, 16, 1024, 65536 (2 / 17 / 1025 / 65537) | same (`PQCAP put`) |
| Part 1 surefire | 3 tests, 0 failures, 0 errors, 1 skipped (the jdb-only test) | `mvn-part1.log` |
| jdb known answer (A2 vi, A9 ii) | **insert = 5, initialize = 1, attached = yes**; test passed | `count-jdbcheck.txt`, `jdb-jdbcheck.log` |
| Sorter f = 2 (`TestSequenceFileSorterMerge`) | Sorter read memory = 1,048,576 B, factor = 2; 5,801,214 B input; output 50,000 records, sorted; test passed. jdb: **insert = 0, initialize = 20** (A4: ≥ 10) | `count-sorter-f2.txt`, `sorter-f2-readings.txt`, `mvn-sorter-f2.log` |
| Sorter f = 100 | factor = 100; 50,000 sorted records; passed. jdb: **insert = 0, initialize = 1** (A4: exactly 1) | `count-sorter-f100.txt`, `sorter-f100-readings.txt` |
| `TestMerger` (mapreduce-client-core) | 4 tests, 0 failures/errors. jdb: **insert = 0, initialize = 12** (≥ 1) | `count-TestMerger.txt`, `mvn-TestMerger.log` |
| `TestSequenceFileMergeProgress` (jobclient) | 3 tests, 0 failures/errors. jdb: **insert = 0, initialize = 3** (≥ 1) | `count-TestSequenceFileMergeProgress.txt`, `mvn-TestSequenceFileMergeProgress.log` |
| Scanner known answer (A3) | `hadoop-common/target/test-classes` (1,899 classes): subclass `TestPriorityQueueInsertCap$LongQ`, **1 HIT** (the harness's own call) | `scan-known-answer.txt` |
| Static scan, `target/classes` of hadoop-common + mapreduce-client-core | 3,617 classes; `PriorityQueue` seen; subclasses `SequenceFile$Sorter$MergeQueue`, `Merger$MergeQueue`; **0 HIT** | `scan-main.txt` |

**Cluster tier** — attempt 2 (the counted run, after defect 1; `run1/cluster/`, 2026-11-25 02:36–02:49 MST). One reducer
(`Launched reduce tasks=1`, `maxattempts=1`), 24 maps, 2,000,000 records in and out of the reducer in every terasort; each
DistCp copied 20,000 files and 101 directories.

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| — | static scan | `insert` call sites in every jar under `hadoop/share` (nested jars included) | 536,463 classes; `PriorityQueue` seen in 2 jars; subclasses `SequenceFile$Sorter$MergeQueue`, `Merger$MergeQueue`; **0 HIT** | `run1/cluster/scan-dist.txt` |
| `mapreduce.task.io.sort.factor` = 2 | A (terasort reducer) | jdb hits | **insert = 0**, initialize = **15** (8 in `InMemoryMerger`, 4 in `OnDiskMerger`, 3 in `main`) | `count-terasort-f2.txt`, `jdb-terasort-f2.log` |
| 2 | A | reducer log pass count (A6, A10) | `ioSortFactor=2`; 13 "sorted segments" + 2 "intermediate segments" lines = **15** = initialize hits; final merge of 4 on-disk files in 3 passes | `reducer-syslog-f2.txt` |
| 2 | A | job | completed successfully | `terasort-f2.log` |
| 10 (default) | A | jdb / log / job | **insert = 0**, initialize = **9** (8 `InMemoryMerger`, 1 `main`); 9 + 0 lines = **9**; success | `count-terasort-f10.txt`, `reducer-syslog-f10.txt`, `terasort-f10.log` |
| 100 | A | jdb / log / job | **insert = 0**, initialize = **9** (8 `InMemoryMerger`, 1 `main`); 9 + 0 lines = **9**; success | `count-terasort-f100.txt`, `reducer-syslog-f100.txt`, `terasort-f100.log` |
| `seq.io.sort.factor` / `mapreduce.task.io.sort.factor` = 2 (A8) | B (DistCp client) | jdb hits / job | **insert = 0**, initialize = **18** (all `main`); job successful, 20,000 files copied | `count-distcp-f2.txt`, `distcp-f2.log` |
| 100 | B | jdb hits / job | **insert = 0**, initialize = **2** (all `main`); job successful, 20,000 files copied | `count-distcp-f100.txt`, `distcp-f100.log` |

Supplementary (attempt 1, before defect 1's fix; not used for the verdict): the same jdb counts in all five runs
(terasort 15 / 9 / 9, DistCp 18 / 2, insert 0 everywhere, distribution scan 0 HIT), and the reducer pass counts re-read
afterwards from the copied container logs with A10's rule also equal 15 / 9 / 9 (`run1/cluster-attempt1/`).

### 4.2 Conclusion and logic

1. **Validity.** Unit: the JVM ran with the specified options [observed: `run1/unit/part1-readings.txt`, `PQCAP env`]; the
   allocation instrument read the known array exactly [observed: same, `PQCAP instr` = 4112]; the debugger counted a known
   5 + 1 exactly [observed: `run1/unit/count-jdbcheck.txt`]; the scanner found the one known call site
   [observed: `run1/unit/scan-known-answer.txt`]; the limit was reached and passed in every full row (`size == k`,
   falses ≥ 61,019) [observed: `part1-readings.txt`]; the merges ran as designed (50,000 sorted records, factor read back
   as set, all real-caller tests passed) [observed: `sorter-f*-readings.txt`, `mvn-*.log`]. Cluster: every job succeeded
   [observed: `run1/cluster/terasort-f*.log`, `distcp-f*.log`]; one reducer, factor read back by the reducer
   (`ioSortFactor=2/10/100`) [observed: `reducer-syslog-f*.txt`]; jdb attached in every run [observed: `count-*.txt`,
   `attached=yes`]. Valid.
2. **Readings.** Nothing unusual in the unit tier: all three repeats identical; the empty-window baseline was 0 B.
   Cluster: f = 10 and f = 100 give the same count (9): the on-disk merger triggers at `2·f − 1` = 19 or 199 outputs and
   24 map outputs never reach it, so only in-memory merges and one final pass remain [inferred: `MergeManagerImpl.java:358`;
   the logs show no `OnDiskMerger` line at f = 10, 100]. DistCp f = 100 gave 2 `initialize` hits, not 1 (B3f's "1 at f = 100"
   is stated with A7's acceptance `f = 2 > f = 100 ≥ 1`, which holds); the second hit is not explained by a log line
   (the client has no merge log, A6) [inferred: a second Sorter pass or sort in the client; not load-bearing].
3. **Matched row.** Unit, B2g row 1: "`insert` hits = 0 in all runs, `initialize` hits > 0, no static `HIT`, and Part 1 shows
   `heap.length` fixed at k+1 with `allocInsertLoop` flat across k while `allocCtor` scales with k" — insert 0 in the four
   real-caller runs, initialize 20 / 1 / 12 / 3, scan 0 HIT, `heap.length` = k+1 before and after, `allocInsertLoop` = 0 B
   everywhere, `allocCtor` = P(k) exactly; with every A4 number met (A5 → **Confirmed — does not cap**). Cluster, B3g row 1
   with A7: insert 0 in all five runs, 0 static HIT, initialize > 0 in every run, reducer initialize = log pass count at each
   f (15 = 15, 9 = 9, 9 = 9), f = 2 > f = 100 in both workloads (15 > 9; 18 > 2), every job successful → **Confirmed — does
   not cap**.
4. **Excluded rows.** Unit: row 2 (refuted on reachability) — insert hits 0 and no HIT; row 3 (refuted on mechanism) —
   `allocInsertLoop` 0 B for every k and N, `heap.length` unchanged; row 4 (check broken) — `size` never exceeds k; row 5
   (merge not exercised) — initialize > 0 in every run; row 6 (instrument flat) — `allocCtor` 48 → 262,192 B with k;
   row 7 (known answers fail) — all three passed; row 8 (test failed / output wrong) — all passed, 50,000 sorted;
   row 9 (layout differs) — not needed, exact; row 10 (insert-loop noise) — 0 B. Cluster: row 2 (refuted) — insert 0, no
   HIT; row 3 (initialize flat at 0) — 15/9/9/18/2; row 4 (no attach) — all attached; A7 added rows (pass-count mismatch,
   failed job) — counts equal, all jobs successful; row 5 (RSS) — not a verdict row, RSS not recorded (A6).
5. **Observed vs. inferred.** The conclusion rests on observed readings only. Inferred and not load-bearing: the reason
   f = 10 and f = 100 coincide (part 2), and the source of DistCp's second hit at f = 100 (part 2). The claim's "no
   workload reaches `insert`" is inferred from 0 hits in 9 debugged runs plus a whole-distribution static scan, which covers
   paths the workloads did not run (map-side merges, other tools); third-party subclasses on a user classpath are out of
   scope (A3 step 4).
6. **Deviations and gaps.** Cluster defect 1 (§3) — fixed by A10, tier restarted. The `initialize` argument values were
   not recorded (A2 vii). RSS not recorded (A6; no prediction). Thread-allocated bytes measure allocation, not retained heap;
   the reflection reading of `heap.length` stands in for retained heap (B2d gap). Harness not committed (this agent
   does not edit the repository).
7. **Core question.** Usage does not follow the check: the queue's memory is exactly the array `initialize(k)` allocates
   (P(k), linear in k) and inserting 200,000 elements past the limit allocates 0 bytes and leaves the array length at k+1
   (parts 1, 3). The check `size < maxSize` at `PriorityQueue.java:74` is on no runtime path: no production class calls
   `insert`, and real merges in unit tests, a MapReduce reducer and a DistCp client call `initialize` 1–20 times per run
   and `insert` never (parts 1, 3, 4). The constraint therefore caps nothing; what bounds merge memory is the merge factor
   through `initialize`/`put`.

**Conclusion (one line):** unit B2g row 1 — **Confirmed — does not cap**; cluster B3g row 1 (A7) — **Confirmed — does not cap**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `part1-readings.txt` (env line: `UseTLAB=false`, `maxHeapMiB=491`; instr 4112), `count-jdbcheck.txt` + `jdb-jdbcheck.log` (1 initialize at line 49, 5 insert at line 74, "The application exited"), `scan-known-answer.txt` (1 HIT), `mvn-*.log` (BUILD SUCCESS, failures 0), cluster `terasort-f*.log` / `distcp-f*.log` ("completed successfully", "Files Copied=20000"), `reducer-syslog-f*.txt` (`ioSortFactor=` 2/10/100). |
| 2. Readings | yes | The two oddities (f = 10 = f = 100; DistCp f = 100 = 2) were re-checked against the raw files and the acceptance in A7; neither touches a verdict row. |
| 3. Matched row | yes | Each A4 number re-compared row by row in `part1-readings.txt` (21 rows × 3 repeats: allocCtor 48/112/4144/262192, allocInsertLoop 0, heap k+1, size, trues+falses = 200,000); cluster equality of jdb `initialize` and log pass count re-counted locally (13+2, 9+0, 9+0) and by thread (8 InMemoryMerger + 4 OnDiskMerger + 3 main = 15). |
| 4. Excluded rows | yes | Every Refuted row of B2g/B3g addressed with a reading (part 4). |
| 5. Observed vs. inferred | yes | No inferred statement carries the verdict. |
| 6. Deviations and gaps | yes | Defect 1 fixed and tier restarted; attempt-1 readings agree but are not used. |
| 7. Core question | yes | Steps follow B1's logic: mechanism (Part 1) → reachability (jdb, scan) → cluster (jdb tied to logged passes). |

### 5.2 Run 2?

**No** — 2026-11-25. The conclusion rests on observed readings with exact known-answer checks, every prediction was met
exactly, it confirms (does not refute) the stage-3 estimate and confirms no bypass; the cluster tier's attempt 1 gave the
same counts independently.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap; both tiers Confirmed).

**Claim tested:** "In Hadoop 3.4.2 no workload reaches `PriorityQueue.insert`, so the check `size < maxSize` at
`PriorityQueue.java:74` is never evaluated, and the memory of a `PriorityQueue` (its heap array) is set by the
`initialize(n)` argument alone: whatever is inserted, the array length stays `n+1` and no allocation follows the number of
inserts." (B1) — usage does **not** follow the constraint. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 (A5) — **Confirmed — does not cap** | does not cap | run 1 + self-check | 2026-11-25 |
| Cluster | B3g row 1 (A7) — **Confirmed — does not cap** | does not cap | run 1 (attempt 2, after defect 1) + self-check | 2026-11-25 |

**Positive control:** (unit) the same allocation instrument moved with k where the bound binds — `allocCtor` 48 → 262,192 B
(exactly P(k)) — and `put` past k threw at put k+1 for every k; the same debugger counted a known 5 + 1 and counted
`initialize` in every real merge. (Cluster) `initialize` hits moved with the merge factor (terasort 15 at f = 2 vs 9 at
f = 100; DistCp 18 vs 2) and equalled the reducer's logged merge passes.

**Feedback filed:** section D of the case file updated in `case-amended.md` (outside the repository; not committed); amendments
A9 (before the run) and A10 (cluster runbook defect) are in the same file. Repository files (case file, `_INDEX.md`, queue,
HANDOFF) were not edited by this agent.
