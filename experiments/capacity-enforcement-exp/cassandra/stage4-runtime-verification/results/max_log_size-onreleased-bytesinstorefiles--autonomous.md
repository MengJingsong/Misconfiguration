# max_log_size-onreleased-bytesinstorefiles--autonomous — stage-4 results  <!-- file: results/max_log_size-onreleased-bytesinstorefiles--autonomous.md -->

> **Case:** [`max_log_size-onreleased-bytesinstorefiles--autonomous`](../../stage3-ai-deep-read/cases/max_log_size-onreleased-bytesinstorefiles--autonomous.md) (extension set, order 72, band A)
>
> **Status:** self-checked; verdict filed in this results file and in the amended case file (outside the repo, not committed; the repository was not edited)
>
> **Outcome class:** **weak true positive**: estimate `positive`; unit Confirmed — caps; cluster Not confirmed (the on-disk upper bound held, but length drift made the archiver over-delete, so no B3g row matched cleanly)
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the
> feedback field is section D. Run by a fresh stage-4 agent working as Jingsong, 2026-11-24/25. The earlier
> interrupted attempt (node `ms0611`, its drafts and any readings) was discarded unread; this run started clean.
> Everything here lives outside the repository: `~/writeup-ext/out/o72/` (this file, `harness/`, `run1/`,
> `case-amended.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed at repository commit `cd9e1cded` with sha256 `f8ebfdaa…a5677` (carries the interrupted run's audit amendments M1–M8 and defect D1). This run's amendments (M9, the node change; D2, the unit steady-window fix) are in `~/writeup-ext/out/o72/case-amended.md`, which is not committed. The frozen version is sha256 **`69e6625a6d5f9992996869ebd51e4b2858179668edcf055420db2c63299cfce9`** (after M9 and D2). The unit tier's concluded pass and the whole cluster tier ran on this version. The cluster tier started on the M9-only version `c27eae16…`; D2 touches only B2 text. After section D was filled, the file's sha256 is `3fa69806745b647649d58a4e12f6264d96c723eaff8876523d052ec1b3147416`. |
| **Harness** | `~/writeup-ext/out/o72/harness/`, not committed (the run is outside the repo by instruction). Files: `DeletingArchiverBoundTest.java` (B2a, verbatim), `unit-run.sh`, `extract_o72.py`, `analyze_unit.py`, `cluster-setup.py`, `cluster-run.sh`, `analyze_cluster.py`, `case-file-as-filed.md`, `frozen-sha256.txt`. |
| **Tiers and values** | Unit: Test A at `maxLogSize` = 512 KiB, 3.5 MiB and 10 MiB, plus A4 (an undeletable file, 3.5 MiB); Test B with a real `BinLog` (`TEST_SECONDLY`): B0 = 1 TiB (M2), B1 = 2.5·F', B2 = 5.5·F'. Cluster (one node, FQL `MINUTELY`): C1 = 16 GiB (default), K1 = 314572800, K2 = 692060160, C2 = 314572800 with `--archive-command "/bin/true %path"`. P (optional) was not run. |
| **Audit bottom line** | **Ready after amendments**, 2026-11-25. M9 (node `ms0625`, fresh `copy-source.sh` build) was applied before any reading. D2 was found at the first unit analysis; the unit tier was re-run in full. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Apparent bytes of rolled `*.cq4` segments, i.e. disk (A2, B1). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | Unit: 3 synthetic limits, plus B0/B1/B2. Cluster: 16 GiB (the default) plus two binding values; C2 is a mechanism control (B2b, B3b). |
| A. Core question | real resource measured, not only the counter | Met | `du -B1` and on-disk apparent sizes beside the operand (B2d, B3d). The gap is named: apparent vs. allocated bytes for sparse files, and the operand is visible only in deletion log lines (B3d). |
| A. Core question | usage driven to the limit and past it | Met | Unit B: 120 s for about 120 releases against a limit of 2–5 segments. Cluster: about 20 segments against limits of 2–4 (B2c, B3c). |
| B. Logic | each step says what it establishes | Met | B2h/B3h controls. |
| B. Logic | prediction stated in numbers or a clear relation | Met | Exact A numbers; `floor(M/F')` and ratio windows (B2f, B3f, M4, M8). |
| B. Logic | every plausible outcome has a conclusions row | Met | B2g/B3g cover exceeds, flat (≈), no rolls, archive bypass and drift. "Counter capped but disk grows" is covered by row 5/row 2 through `rolledOnDisk`. |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Partly | The ceiling-follows-knob test is explicit. The disallow evidence (deletion lines) is used in M8, and in M4 only after D2. |
| B. Logic | alternative explanations and their controls | Met | B0/C1 (cap not binding grows), C2 (the bound comes from `DeletingArchiver`), fresh directories (A3(b)). |
| C. Specific | a human can follow it from the intro and B1 | Met | |
| C. Specific | an AI can run B2e/B3e without re-deriving the code path | Partly | Readings went to the console, not the XML (B2e step 2 allows the console; M3 named the XML). `nodetool truncate` does not exist (D1). The M4 steady window could not open (D2). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | |
| D. Runnable | harness and environment prerequisites | Partly | On `ms0625`, `/mydata/s4/cassandra-base` has no `src/` or `test/`. The source was copied fresh with `copy-source.sh` and built (M9). |
| D. Runnable | workload arithmetic reaches the limit | Met | Disk: about 25 GiB free on `/mydata`, checked to be ≥ 15 GiB before each run. |
| D. Runnable | load-bearing citations spot-checked | Met | `DeletingArchiver.java:41-80` (operand, `while` at `:60`, INFO at `:73-74`), `BinLog.java:449` (archiver choice), `:377-473` (Builder, `start()`), `StorageService.java:7138-7145`, and `BinLogTest.record` at `:469` checked in the `ms0625` copy. One finding: the INFO line at `:73-74` logs `file.getPath()` (the file just released), not `toDelete`, so it names the wrong file. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Run on `ms0625` with a fresh `copy-source.sh` build, because the base copy lacks the sources | Applied as M9 (2026-11-25), before any reading | The test cannot compile otherwise |
| 2 | Read the `O72*` records from the `ant` console log, reassembled from the per-fragment logger lines (`extract_o72.py`) | Harness only; B2e step 2 already allows "the console" | The test JVM routes `System.out` through a logger that logs each `printf` fragment as its own line, and the XML holds none of it |
| 3 | M4 steady window: replace "after the first decrease of the operand" with "after at least one deletion line" | Applied as D2 (2026-11-25); unit tier re-run in full | The window can never open (see §3) |
| 4 | Stage 3: say that Chronicle pre-sizes segments (80 MiB for `TEST_SECONDLY`; 144 MiB at release for a 120 MiB `MINUTELY` segment) and shrinks them after release, so A3(d) drift is the normal case, not a corner case | Left for stage 3 | The case file left the question open (A3(d)) |
| 5 | Stage 3: note the log bug at `DeletingArchiver.java:73-74` (the INFO line names the released file, not the deleted one) | Left for stage 3 | Affects anyone reading deletion logs |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-24 21:56 MST to 2026-11-25 (node clock MST; Cassandra logs UTC) |
| Node | `ms0625` = `node0.jason92-326377.misconfiguration-pg0.utah.cloudlab.us` (Utah m400), **aarch64**, 8 cores, 62 GiB |
| OS and kernel | Ubuntu 22.04.1 LTS, `5.15.0-191-generic` |
| JDK | OpenJDK 11.0.33 (`11.0.33+9-post-1ubuntu1-22.04.1`) |
| Ant | 1.10.12 |
| Local source copy | `copy-source.sh` from repository `systems/cassandra/source/` at commit `cd9e1cded` → `/mydata/jingsong-cass-s4/o72/build-copy` (`git describe` = `cassandra-5.0.9`); `ant build-test` BUILD SUCCESSFUL in 4 min 32 s. Unit `$W/src` and cluster `$RUN/src` are `cp -a` copies of it. |
| Case-file commit / harness commit | `cd9e1cded` (as filed) plus the uncommitted amended copy; harness not committed (outside the repo) |
| Storage for node data | `/mydata` (LVM `emulab-node0--bs`, 39 GB, local) under `/mydata/jingsong-cass-s4/o72/` |
| Full logs | Node: `/mydata/jingsong-cass-s4/o72/{logs,unit,cluster}` (bulk data deleted, small logs kept). Here: `~/writeup-ext/out/o72/run1/` |
| Node lock | `/mydata/s4/NODE-LOCK` held from 21:56 MST for the whole run |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | interrupted run (`ms0611`) | B3e 3.9 | `nodetool truncate` does not exist in 5.0.9 | `cqlsh -e "TRUNCATE keyspace1.standard1"` | already in the filed file | `cd9e1cded` |
| — | unit attempt 0 | B2e step 2 / M3 | The `O72*` lines are not in the XML. The test JVM logs `System.out` through `SubstituteLogger`, one line per `printf` fragment, and the driver stopped after B0 with no `F'` | Harness fix only: `extract_o72.py` reassembles the records from the console log, which B2e step 2 allows; the tier restarted from Test A | 2026-11-25 | none (harness) |
| D2 | unit attempt 1 | M4 *steady* | "After the first decrease of the operand" can never be observed: `onReleased` is synchronized and returns with the operand ≤ M, and with equal release lengths it sits at `k·F'` at every sample | *Steady* = from the first sample with `tracked ≥ floor(M/F')`, provided there is ≥ 1 deletion line; B2f/B2g unchanged. Attempt 1 kept as evidence, not concluded on; the tier re-run in full (run 1, final pass) | 2026-11-25 | `case-amended.md` (uncommitted) |

## 4. Run 1

**Scope:** both tiers. Unit: A (3 limits), A4, B0, B1, B2. Cluster: C1, K1, K2, C2; P not run (optional, 3 h cap).
**Command logs:** unit `run1/unit/logs/unit-driver.log` (+ `ant-<tag>.log` per test), cluster
`run1/cluster/cluster-driver.log`. Paths below are relative to `~/writeup-ext/out/o72/`. The unit tier's concluded pass is the
third (`run1/unit/`, 2026-11-24 23:56 to 2026-11-25 00:02 MST): attempt 0 (`run1/unit/attempt0/`, extraction failure) and attempt 1
(`run1/unit/attempt1/`, D2) are kept and not concluded on. The final pass ran after the cluster tier, with the Cassandra node
stopped first.

### 4.1 Readings

**Unit tier** (F' = median `lenAtFirstSeen` of B0 = **83886080 B = 80 MiB**, so B1/B2 ran 120 s; `run1/unit/fprime.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| A, 512 KiB: every step `operand=0 onDisk=0 files=0` | 20/20 rows match | `run1/unit/A-readings.txt`, `unit-analysis.txt` |
| A, 3.5 MiB: steps 0–2 grow by 1 MiB, then `operand=3145728 onDisk=3145728 files=3` | 20/20 rows match | same |
| A, 10 MiB: grows to `operand=10485760 files=10` at step 9 and stays (equality does not delete) | 20/20 rows match | same |
| A4: g00 undeletable; one ERROR, operand stuck 1 MiB high, then `operand=3145728 tracked=2 onDiskOk=2097152 onDiskRo=1048576` | 12/12 rows match; one `Failed to delete chronicle store file: …/A4-ro/g00.cq4 … bytes in store files: 4194304` | `A-readings.txt`, `A-errorlines.txt` (from `logs/ant-A.log`) |
| B0 (1 TiB): grows, no deletion | 0 deletion lines; operand never decreases; max operand 3355443200 (40 × F'); final rolledOnDisk 911645480 (10.87 F'); 40 rolled files | `B0-readings.txt`, `B0-deletions.txt` |
| B0 shrink (A3(d)) | 30 of 40 tracked files shrank from 83886080 to 1.3–2.5 MB; the 10 newest (≤ ~10 s after release) were still 83886080 | `B0-readings.txt` (`O72B-LEN`) |
| B1 (M = 209715200 = 2.5 F') | 593 samples; operand ≤ M at every sample (max 167772160); rolledOnDisk max 167772160, never > M + F'; steady median 167772160 = 2 F', mode `tracked` = 2; 119 deletion lines; max total 251658240 ≤ M + 2F'; max allocated (`du`) 5.7 MiB | `B1-readings.txt`, `B1-deletions.txt`, `du-B1.txt` |
| B2 (M = 461373440 = 5.5 F') | 593 samples; operand ≤ M at every sample (max 419430400); rolledOnDisk max 419430400; steady median 419430400 = 5 F', mode `tracked` = 5; 116 deletion lines; max total 503316480; max allocated 11.3 MiB | `B2-readings.txt`, `B2-deletions.txt`, `du-B2.txt` |
| Knob follow | B2/B1 steady median = **2.50** (window [1.8, 2.8]) | `unit-analysis.txt` |
| Tracked files in B1/B2 at end | 0 shrunk (deleted 2–5 s after release, before Chronicle shrinks them) | `B1/B2-readings.txt` (`O72B-LEN`) |

**Cluster tier** (one node; FQL `MINUTELY`, 400 writes/s for 20 min per run, 480000 ops, 0 errors, 400 op/s in every
run; `F'` = median DEBUG `rolled file size` = **150994944 B = 144 MiB**, 20 % from 120 MiB, so no rescale under M6;
`scale.txt`). Segments are released at 144 MiB and shrink to 127521048 B (121.6 MiB) afterwards.

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 17179869184 (default) | C1 (positive control) | releases / deletions | 22 / **0** | `run1/cluster/archiver-C1.txt`, `cluster-driver.log` |
| | | rolled apparent bytes, final | 2816084204 (2685.6 MiB), 21 rolled segments, ≥ 0.8·21·F' → grows | `sample-C1.txt` |
| 314572800 | K1 | releases / deletions | 22 / 21; first deletion 36 s after stress start (the first segment, 352321536 B, is larger than M alone and is deleted at release) | `archiver-K1.txt` |
| | | rolled apparent bytes | max **278515988 (265.6 MiB) < M**; never > M + F'. Retained 1 segment (121.6 MiB) to ~8 min, then **0** to the end; steady median **0** | `sample-K1.txt` |
| | | total directory | max 406037036 (387.2 MiB) = rolled + the current segment (pre-sized 80–144 MiB) | `sample-K1.txt` |
| | | logged `bytes in store files` | 0, **325463788**, 197942740, 221437884, …, 291838324, **315312220**, then 164317276 ×13. The two values above M are mid-loop, in one `onReleased` call (the next deletion follows 53 ms / 1 ms later, same thread, no release between) | `archiver-K1.txt` |
| | | drift | each deletion subtracts the shrunk length (≈127.5 MB) where the release added 150994944: +23.47 MB stays in the operand per deletion. After 8 deletions the operand is stuck at 164317276, and every new segment (+150994944 → 315312220 > M) is deleted at its own release | `archiver-K1.txt` |
| 692060160 | K2 | releases / deletions | 23 / 23; first deletion 200 s after stress start | `archiver-K2.txt` |
| | | rolled apparent bytes | max **541421280 (516.3 MiB) < M**; retained 3→4→3→2 segments over the run (drift); steady median **255042096 (243.2 MiB, 1.69 F')**, median 2 segments; all files deleted by the final roll | `sample-K2.txt`, `ls-K2.txt` |
| | | total directory | max 668942328 (638.0 MiB) < M | `sample-K2.txt` |
| | | logged `bytes in store files` | rises ≈ 23.47 MB per deletion from 565874976. The three values above M (706718356, 696566792, 723881680) are each followed by a second deletion in the same call (06:20:00,057→,111; 06:25:00,058→,114; 06:31:38,064→,064); the last value per call is ≤ M | `archiver-K2.txt` |
| 314572800 + `archive_command "/bin/true %path"` | C2 (mechanism control) | config | `archive_command /bin/true %path`, `max_log_size 314572800` | `conf-C2.txt` |
| | | deletions / rolled bytes | **0** archiver lines; final rolled 2816127308 (2685.7 MiB), 22 rolled segments → grows like C1 (F' from C1) | `archiver-C2.txt`, `sample-C2.txt` |
| all | | allocated ≤ apparent | yes for every sample with a segment; the only exceptions are the empty directory before enable (8 KiB of directory blocks) | `sample-*.txt` |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — Valid. B0 grew to 40 rolled files with no deletion, so the workload and roll cycle worked [observed:
   `B0-readings.txt`, `B0-deletions.txt`]. Each B run used a fresh directory [observed: `unit-driver.log`, `B-<limit>` dirs
   created and removed]. The run was non-root, and A4's read-only directory refused the delete [observed: `A-errorlines.txt`].
2. **Readings** — B0's tracked files shrink from 80 MiB to ≈2.4 MB about 10 s after release [observed: `B0-readings.txt`
   `O72B-LEN`]. In B1/B2 the oldest file is deleted 2–5 s after release, before it shrinks, so no drift shows at this tier
   [observed: `B1/B2-deletions.txt` "store file size: 83886080"; inferred: retention of 2–5 one-second segments is shorter
   than the shrink delay].
3. **Matched row** — B2g row 4, "B1/B2 `operand ≤ M` always, `rolledOnDisk` plateaus near `floor(M/F')·F'`, B2 plateau ≈ 2.2× B1,
   while B0 grows linearly". Read by M4 as amended by D2: A rows match exactly [observed: `unit-analysis.txt`]. B0 grows (final
   10.87 F' ≥ 10 F', no operand decrease) [observed]. B1 and B2 are bounded: 0 samples with operand > M, 0 runs of
   rolledOnDisk > M + F' [observed]. Plateaus: B1 median 2.00 F', mode 2; B2 median 5.00 F', mode 5 [observed]. Knob follow:
   2.50 ∈ [1.8, 2.8] [observed]. Direct disallow evidence: 119 and 116 `Deleted chronicle store file` lines [observed:
   `B1/B2-deletions.txt`]. Row 1 (A exact, strict `>`) and row 3 (A4 as traced) also hold. Row 7 is recorded beside them:
   B0 files shrink (`lenNow < lenAtFirstSeen` for 30 files), but `tracked` does not drop toward 0 in B1/B2.
4. **Excluded rows** — Row 2 (A keeps 4 files or operand > limit): no; A 3.5 MiB keeps 3 files with operand 3145728. Row 5
   (claim wrong): no sample breaks *bounded*, and B1/B2 final rolled (2 F', 5 F') is < 0.5 × B0 final (10.87 F'). Row 6
   (no rolls): B0 has 40 rolled files.
5. **Observed vs. inferred** — The only inference is that B1/B2 see no drift because deletion precedes the shrink. It does not
   affect the matched row.
6. **Deviations and gaps** — D2 (steady window) was applied before this pass. Readings come from the console log, not the
   XML (allowed by B2e step 2). The A4 ERROR line is taken from this pass's console log, because the per-class file under
   `build/test/logs` appends across passes and held attempt 1's line as well (`A-errorlines-buildtestlog-appended.txt`).
7. **Core question** — Yes, at the unit tier. The loop at `:60` holds the tracked sum at or below `max_log_size`, both
   synthetic and with a real Chronicle queue. Retained rolled bytes plateau at exactly `floor(M/F')·F'` and move with the knob
   (2 → 5 segments, ratio 2.5). Under an unreachable limit they grow without bound.

**Conclusion (one line):** B2g row 4 — **confirmed** (rows 1 and 3 hold; row 7 recorded: Chronicle shrinks released segments).

**Cluster tier**

1. **Validity** — Valid. C1 rolled 22 segments with no deletion and grew to 2.62 GiB [observed: `sample-C1.txt`,
   `archiver-C1.txt`]. Stress ran at 400 op/s with 0 errors in every run [observed: `stress-*.log`]. `getfullquerylog`
   pins each run's limit and archiver [observed: `conf-*.txt`]. Each run had a fresh path [observed: driver log].
2. **Readings** — Strong length drift (A3(d)). Segments are counted at 150994944 B when released and subtracted at about
   127.5 MB when deleted a minute or more later [observed: `archiver-K1.txt`, `archiver-K2.txt`]. The operand gains about
   23.47 MB per deletion, so retention falls over the run: K1 2 → 1 → 0 segments, K2 4 → 3 → 2 [observed: `sample-K1/K2.txt`].
   Logged operand values above M occur only mid-loop, as the first of two deletions in one call [observed: timestamps and
   thread in `archiver-K1/K2.txt`].
3. **Matched row** — **none cleanly.** Read literally, M8 makes K1 and K2 fail *bounded*, because some logged `bytes in store
   files` values exceed M. That would be row 2 ("claim wrong"). Row 1 fails in any case: neither K run is *at plateau* (K1
   median 0 against the window [273.6, 453.6] MiB; K2 median 243.2 MiB against [547.2, 756.0] MiB), and *follows the knob* cannot be
   computed (K1 plateau 0). The self-check (§5) finds that the row-2 trigger does not show what row 2 means. The over-M values
   are intermediate values within one synchronized `onReleased` call, and the same call goes on to delete. On disk, rolled
   bytes never exceeded M (K1 max 265.6 MiB < 300 MiB; K2 max 516.3 MiB < 660 MiB) and were never above M + F'. So the
   conclusion is downgraded to **Not confirmed (no matching row)**. Recorded beside it: **row 6 (drift)**, "plateau well below
   `floor(M/F')·F'` and logged `bytes in store files` > on-disk rolled bytes → over-deletion; upper-bound claim still holds"
   (K1: logged 164317276 against 0 B on disk); and **row 8** (total directory > M only by the current segment: K1 387.2 MiB).
4. **Excluded rows** — Row 3 (K1 ≈ K2): the plateaus differ (0 against 243.2 MiB); the ratio cannot be computed, and it is not ≤ 1.25 in
   any sense. Row 4 (C1 invalid): C1 has 21 rolled segments. Row 5 (C2 bounded): C2 has 0 deletion lines and grows to 2.62
   GiB. Row 7 (P): not run. Row 2 by growth: K1/K2 final rolled 0 < 0.5 × C1.
5. **Observed vs. inferred** — Inferred: the over-M logged values are mid-loop. The evidence is that the next deletion
   follows on the same thread 1–54 ms later with no release line between, and that `:73-74` logs inside the `while` loop (source).
   Inferred: the drift is the release-time length minus the shrunk length (the per-deletion step of 23,473,896 ≈
   150994944 − 127521048 matches).
6. **Deviations and gaps** — P not run. C2's F' is taken from C1 (C2 has no `DeletingArchiver` lines). The driver's exit trap
   hung after the last run had logged `CLUSTER-RUNS-DONE` (an empty-PID `wait` on the `tee`); it was killed and fixed, and no
   reading is affected. The first segment of every run is larger (285–352 MB at release), probably because it covers the
   enable and the stress warm-up; it is either deleted at once (K1) or counted at its length, and does not change the reading.
7. **Core question** — On disk, `max_log_size` capped the rolled FQL segments at every sample in both K runs. Without the cap
   (C1) or with `archive_command` (C2), rolled bytes grew to 2.6 GiB. But usage does not settle at a level set by the knob: the
   length drift of A3(d) makes the archiver over-delete, until K1 keeps no rolled segment at all and K2 keeps about half of
   what its limit allows. The frozen reading rules do not cover this outcome cleanly, so the tier is Not confirmed. The
   upper bound holds.

**Conclusion (one line):** no B3g row matches cleanly — **not confirmed** (literal row 2 rejected by the self-check; rows 6
and 8 recorded; the on-disk upper bound held in K1 and K2).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| Unit 1. Validity | yes | `B0-deletions.txt` is empty; `B0-readings.txt` ends with `files=41`; `A-errorlines.txt` holds one g00 line dated 06:55:41 UTC (this pass) |
| Unit 2. Readings | yes | `O72B-LEN` lines in B0 show 83886080 → 1311432…2491728 for the first 30 files; in B1/B2 every deletion line says `store file size: 83886080` |
| Unit 3. Matched row | yes | `unit-analysis.txt` recomputed from the raw readings: A exact, B1 2.00 F' mode 2, B2 5.00 F' mode 5, ratio 2.50 |
| Unit 4. Excluded rows | yes | |
| Unit 5. Observed vs. inferred | yes | The one inference does not carry the matched row |
| Unit 6. Deviations | yes | D2 applied before this pass; the attempts are kept separate |
| Unit 7. Core question | yes | |
| Cluster 1. Validity | yes | `conf-*.txt` re-read: `max_log_size` 17179869184 / 314572800 / 692060160 / 314572800, and `archive_command /bin/true %path` only in C2 |
| Cluster 2. Readings | yes | `archiver-K1.txt` 05:51:00,083 (325463788) → 05:51:00,136 (197942740), and 05:56:00,063 (315312220) → 05:56:00,064 (164317276), all on `Binary Log thread:1`; K2 06:20:00,057 → 06:20:00,111 and 06:31:38,064 ×2 |
| Cluster 3. Matched row | **no, as literally read** | The row-2 trigger (a logged value > M) does not show that usage exceeded the limit: the values are mid-loop, and on-disk rolled bytes stayed < M. Per the README, a part that does not hold downgrades the conclusion to *Not confirmed*. The prediction B3f "logged `bytes in store files` is always ≤ M" missed calls with more than one deletion; it is recorded as feedback for stage 3, not amended (the 3 h cap leaves no time to restart the tier) |
| Cluster 4. Excluded rows | yes | |
| Cluster 5. Observed vs. inferred | yes | The mid-loop inference rests on the timestamps, the thread names and the source |
| Cluster 6. Deviations | yes | |
| Cluster 7. Core question | yes, as stated | Upper bound observed; the knob-following plateau not observed, because of drift |

### 5.2 Run 2?

**No** (2026-11-25). The unit conclusion rests on observed numbers that match exactly. For the cluster tier, a run 2 with the
same frozen rules would hit the same literal row-2 trigger, so it would not settle the tier. What would settle it is a stage-3
amendment to B3f/B3g: read the operand after each call, and give drift its own outcome row. A new cluster run would then be
needed, which does not fit the 3 h cap.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **weak true positive.** The unit tier is Confirmed — caps; the cluster
tier is Not confirmed, so the case is classed from its unit tier alone (rule of 2026-10-29). The cluster tier does not
disagree on the upper bound: disk never exceeded M.

**Claim tested (B1):** while FQL uses the built-in `DeletingArchiver`, the total apparent size of its rolled `*.cq4`
segments stays at or below `max_log_size` (beyond it only transiently, by at most one rolled-but-unreleased segment) and
plateaus at a level that moves with `max_log_size`; with the limit unbounded, or with `archive_command` set, rolled bytes
grow linearly.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 4 (rows 1 and 3 hold; row 7 recorded) | caps | run 1 (third pass) + self-check | 2026-11-25 |
| Cluster | **Not confirmed** (no matching row; the literal row 2 was rejected by the self-check; rows 6 and 8 recorded) | undetermined (observed: the on-disk upper bound held in K1 and K2; the cap over-enforces through length drift) | run 1 + self-check | 2026-11-25 |

**Findings worth carrying forward**
- **Length drift is the normal case on a real node (A3(d)).** Chronicle 5.23.37 pre-sizes segments (80 MiB for
  `TEST_SECONDLY`; 144 MiB at release for about 120 MiB of `MINUTELY` content) and shrinks them after release. `onReleased`
  adds the pre-size length; the deletion subtracts the shrunk length. Each deletion leaves the difference (23.47 MB here) in
  `bytesInStoreFiles`. Once the stuck amount plus one segment exceeds `max_log_size`, every new segment is deleted at its
  own release. K1 (300 MiB) reached that state after 8 deletions and kept **no rolled FQL segment at all** for the rest of the
  run. K2 (660 MiB) fell from 4 retained segments to 2, and to 0 at the final roll. The cap over-enforces, which costs FQL
  data, not disk. This looks like a variant of the bug in the CASSANDRA-16526 comment (`BinLogTest.testTruncationReleasesLogSpace`).
- **Log bug:** the INFO line `Deleted chronicle store file: {}` at `DeletingArchiver.java:73-74` logs `file.getPath()` (the
  segment just released), not `toDelete.getPath()`.
- **Intermediate logged operands exceed `max_log_size`** whenever one release triggers more than one deletion. Reading rules
  must use the value after the call, i.e. the last line per release.

**Feedback filed:** in `~/writeup-ext/out/o72/case-amended.md` (not committed, by instruction): amendment M9 (B2a and
B3a), defect D2 (after M4), and section D, "Stage-4 feedback". Nothing in the repository was changed.
