# cdc_total_space-applySimpleConfig-cdc_total_space--autonomous — stage-4 results  <!-- file: results/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous.md -->

> **Case:** [`cdc_total_space-applySimpleConfig-cdc_total_space--autonomous`](../../stage3-ai-deep-read/cases/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — caps** (run 1). **Cluster: Confirmed — caps** (cluster re-run
> "run 1b" of 2026-10-24/25 at the re-frozen version `ad11ccdc…5cb2`, after the user-authorised amendment of B3h (a); §7, §8).
> The run-1 cluster verdict below (Invalid) stays on record as filed.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/`](../harness/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/).
>
> **Run-1 status (as filed 2026-10-24):** verdict filed, 2026-10-24. **Unit: Confirmed — caps. Cluster: Invalid — undetermined** (all six arms matched
> B3g row 1; the frozen control (a) expectation "≤ 2 links 30 s after `nodetool flush ks`" did not hold, 6 links, so the
> amended row 9 makes the tier Invalid; §4.3, §8). The cluster tier stays open.
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-24, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `f361777` (sha256 `60f786b8…6dcc`). Frozen after the step-0 audit's twelve amendments (2026-10-24, before any reading): sha256 **`cfaee9a0799667f6b2431a63f2f3f37807f28b341ef262b02ab6aa7ce9f182e5`** (new row in `_INDEX.md` §4). Both tiers ran at this version; no runbook fix was needed after the freeze. Section D was filled after the hash. Nothing is committed (no commit was asked for); base commit `41d8938`. |
| **Harness** | [`../harness/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/`](../harness/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/) (uncommitted): `CDCAllowanceTest.java` and `unit-run.sh` (unit); `cdc.yaml`, `plain.yaml` (stress profiles), `cdc-sampler.py` (0.25 s listing of `cdc_raw`), `logscan.py` (log evidence, rotated `.zip` included), `cluster-run.sh` (cluster); `unit-readings.py`, `cluster-readings.py` (tables and row matching), `selfcheck.py` (independent self-check). sha256 prefixes at run 1: test `18e08264`, unit-run `ac8101cc`, cluster-run `c6f1861b`, sampler `2158b5d0`, logscan `e017cb9c`, cdc.yaml `6c0f1ff6`, plain.yaml `3b0a431f`. Checks: §1.2 |
| **Tiers and values** | **Unit** (S = 1 MiB): s = 8, 16, 32 MiB blocking and non-blocking; controls `cdc=false` (s = 8) and s = 1024 with 128 MiB; default helper at 4 GiB and 100 GiB. **Cluster** (one node, S = 32 MiB): `cdc_total_space` 256MiB, 1024MiB, 0MiB (resolved 4096 MiB) × blocking / non-blocking; controls (a) `cdc=false` table, (b) `cdc_enabled: false`, (c) start-up `cdc_enabled: false` with 0MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`git describe --tags`; same commit `b5f2a54` as the run clone).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: bytes of commit-log hard links in `cdc_raw` (disk). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | B3b 256, 1024, 0 (default): met. B2b only 8 and 32; the default cannot be set at the unit tier (covered by the helper); 16 added (amendment B2a/B2b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d measure the files (`folderSize`, `du -sb`), with the counter as a cross-check. Amended to separate link bytes from index bytes and to record allocated bytes (APFS sparse files: allocated ≤ apparent). |
| A. Core question | usage driven to the limit and past it | Partly → Met after amendment | 3.2 GB against 1024 MiB: met; the default (4096 MiB here) needed N raised, as B3f says; N = 320,000 (5.2 GB) set (B3b/B3c). |
| B. Logic | each step says what it establishes | Partly | B3e is a sequence without purposes; the rows say what each reading means. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≤ knob + 32 MiB" exact; "≈ s MiB written", "≈ knob of data" not numbers. Windows derived from the source (B2f, B3f amendments): accepted bytes in [A − 4S, A + S], links ≤ A + S. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | No row for overshoot between one and two segments, a cap below the knob, non-blocking failures, no deletion, or a failed control. Rows 4–9 added (B2g, B3g) with a tier rule. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Blocking: B3g row 3 already demanded failures. Non-blocking had no disallow observable: deletion evidence (`Freed up` lines, deleted link names) added and required. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | B2h/B3h controls named, but "cdc_raw stays empty / ≈ 0" contradicts the source: every PERMITTED segment is hard-linked at creation whatever it holds (`CommitLogSegmentManagerCDC.java:241-247`), and the link is deleted on discard of a segment without CDC data (`:75-80`). Expectations corrected (B2h, B3h). The corrected cluster expectation was itself incomplete (§4.3). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1 read on their own. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Unit: how S is set, how the package-private helper is reached, and what "reset" means were open (B2a/B2b). B2c's `forceRecycleAllSegments()` "so segments are linked" rests on a premise the source does not have (links are made at creation, `:236-249`); dropped, `sync(true)` per row (B2c). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | No stress profile, error mode or N for the default; `du -sb` and `df -B1` are GNU-only (B3d: Python sampler, `statvfs`); stop conditions added (B2c). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | B2a/B3a list clone, build, test, node; mapped to this host (B3a amendment): clone `$W/cassandra-run6`, node under `$W/node-cdc`. |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit ≤ 128 MiB per JVM. Cluster: ≤ 5.2 GB per arm at 2,000 rows/s (≤ 160 s); at most about 5 GB of sstables plus 4 GB of links per arm against 156 GiB free (free disk was ≥ 155 GiB after every arm, `run1/cluster/summary.txt`); 2 GiB heap on 32 GiB RAM. Log volume (measured in the shakedown): about 2.9 KB per rejected write per log file, ≤ 184 k rejected writes per arm. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `DatabaseDescriptor.java:677-697` (gate at 677, default at 684-695), `:1147-1162` (helper; integer MiB, `/8`, WARN when smaller than 4096), `:4370-4379` (getter/setter), `:2887`; `CommitLogSegmentManagerCDC.java:168-190` (`allocate`), `:195-210`, `:212-228` (WARN via NoSpamLogger, 10 s, `:220-224`; throw `:226`), `:236-249` (`createSegment`, link after `processNewSegment`), `:326-358` (`processNewSegment`; non-blocking deletion `:345-354`, `Freed up` debug line `:351`), `:360-383`, `:407-419`. All hold. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Unit test build: package `db.commitlog`, one JVM per scenario, S set by `setCommitLogSegmentSize(1)` + commit-log restart, helper by reflection; add s = 16 | Applied 2026-10-24, B2a/B2b | Not runnable as written; group A asks for three values |
| 2 | Drop `forceRecycleAllSegments()` from the workload, `sync(true)` per row; stop conditions | Applied, B2c | Premise not in this source; "periodically" not exact |
| 3 | Sample after every row, link and index bytes separately, deleted names | Applied, B2d | Index bytes would otherwise tip the bound; non-blocking needs a disallow observable |
| 4 | Numeric windows from the source (B2f, B3f) | Applied | "≈" cannot be contradicted |
| 5 | Conclusion rows 4–9 and the tier rule (B2g, B3g) | Applied | Outcomes between confirm and refute had no row |
| 6 | Control expectations corrected from the source (B2h, B3h) | Applied | "cdc_raw stays empty/≈ 0" contradicts `:241-247`, `:75-80` |
| 7 | This host's paths and heap pair (B3a); exact stress command, profile, error mode, throttle, N (B3b/B3c); macOS sampler and `statvfs` (B3d) | Applied | Not runnable as written here |
| 8 | Exercise the `/8` branch of the default at the cluster tier with `cdc_raw` **and the commit log** (hard links cannot cross file systems) on a fixed-size volume, e.g. 2.5 GiB → 319 MiB | **Not applied: environment limit** (below) | This host cannot give the session a writable fixed-size volume; the branch is covered only by the unit helper here |
| 9 | B3h (a): the post-flush expectation should flush **all** keyspaces (or allow the links of segments pinned by dirty system tables) | Left for stage 3 (found after the reading; §9a frozen) | §4.3: `nodetool flush ks` leaves segments pinned by system tables; 6 links remained |
| 10 | B3e: say what each step establishes | Left for stage 3 | Documentation |

**Environment limit (step E, 2026-10-24).** `hdiutil create … -fs HFS+` fails with `Operation not permitted` (also in `/tmp` and
with `-type SPARSE`); `diskutil image create blank --fs APFS` creates an image and `diskutil image attach` mounts it at
`/Volumes/s4probe`, but every write to the mounted volume (`mkdir`, `touch`, `python3 open(…,'w')`) fails with `Operation not
permitted`. A probe image of 64 MB (64,000,000 bytes, `df -k` 62,460 KiB total) was created, mounted, ejected and deleted; no image
remains. This blocks only recommendation 8; the case's design puts `cdc_raw` on local disk, which this host has.

**Agreement criteria** — not filled (no run 2).

### 1.2 Instrument checks

| Check | Result |
|---|---|
| `unit-run.sh instrument`: `ant build-test` with the test in the clone | `BUILD SUCCESSFUL` ([`run1/unit-instrument/summary.txt`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1/unit-instrument/summary.txt)) |
| Upstream `CommitLogSegmentManagerCDCTest` (known answer: passes) | 10 tests, 0 failures, 0 errors |
| `CDCAllowanceTest` helper (known answer 512, 4096) | 512 and 4096 |
| `CDCAllowanceTest` block, s = 4 (not a case value) | ran every step; first rejection after 45 rows with 3 links. Showed a harness fault: the maxima did not include the sample taken at the rejection (index bytes 48 there, max 38). Fixed before run 1 (harness defect H1, §3) |
| `cdc-sampler.py` known answer (temp dir: one link with index, a second link, the first removed) | states (1 link, 1000 B, idx 2 B) → (2, 4000) → (1, 3000); events `+`,`+`,`-` with the right names and sizes; gaps 254–261 ms ([`instrument-sampler/`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/instrument-sampler/)) |
| `logscan.py` known answer (plain and zipped `system.log`, `debug.log`) | counted WARN, ERROR, exception headers, `Freed up` in both copies |
| Cluster shakedown (`cluster-run.sh shake shake startup-cdcoff-0`: 64MiB blocking, N = 8,000; start-up control) | ran end to end: read-backs, sampler, stress (3,926 errors of 8,000), count 4,074, log scan, drain, stop, wipe; no process left ([`shakedown/summary.txt`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/shakedown/summary.txt)). Showed harness defect H2 (§3). Not a reading of the case. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-24. Unit tier 21:45:05–21:52:15 EDT (2026-10-25 01:45–01:52 UTC). Cluster tier 21:56:14–22:17:50 EDT. |
| Node | `yangwang-mbp` (the advisor's laptop), one host; Apple T6000, 10 cores, 32 GiB RAM |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Local clone commit | `$W/cassandra-run6` (`W=~/Library/Caches/stage4`), `b5f2a54210d541339c2e7c17a794195cac0e67c2`, tag `cassandra-5.0.9`, cloned from `~/cassandra-src` and built with `ant -Dlocal.repository=$W/m2 build-test` (51 s); only change: the untracked test |
| Case-file commit / harness commit | base `41d8938`; case file, harness and this file uncommitted; frozen case sha256 `cfaee9a0…82e5` |
| Storage for node data | internal SSD, APFS `/dev/disk3s1`; `statvfs` total 494,384,795,648 B (471,482 MiB) → default min(4096, 58,935) = 4096 MiB; free 156 GiB before, 155 GiB after; node directories `$W/node-cdc` (wiped before and after every arm); no disk image used (environment limit, §1) |
| Loopback / ports | `lo0` has 127.0.0.1–.3 (only .1 used); 7000, 7199, 9042, 9091 free before and after; no `CassandraDaemon` before or after |
| Full logs (outside the repo) | `$W/logs/cdc_total_space-applySimpleConfig/`: `build-test.log`, `unit-instrument/`, `unit/` (ant logs, `*.stage4.out`), `instrument-sampler/`, `cluster-shake/`, `cluster-run1/` (988 MB: node logs per arm with rotated zips, stress logs, sampler files) |

## 3. Runbook defects

No step of the frozen file failed to run; no runbook fix after the freeze. Harness defects found by the instrument checks, fixed
before run 1 (harness only; the case file is unchanged):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| H1 | instrument check, unit block s = 4 | B2d | maxima omitted the sample taken at the first rejection | maxima include it | AI, 2026-10-24 | n/a (harness) |
| H2 | cluster shakedown | B3d | `logscan.py` timestamp pattern expected a space; the node writes `2026-10-25T01:54:18,159` | pattern `[ T]` | AI, 2026-10-24 | n/a (harness) |
| R1 | cluster run 1 (reading, not a runbook defect) | B3h (a) | control (a)'s frozen post-flush expectation (≤ 2 links 30 s after `nodetool flush ks`) was wrong: 6 links; the cluster tier was Invalid (§4.3) | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-24:** dated amendment `Amendment 2026-10-24 (after run 1, authorised by the user) — B3h (a)` (flush **all** keyspaces with `nodetool flush`; post-flush count = max links from flush return + 30 s; expectation ≤ 2 re-derived from the source); new sha256 `ad11ccdc…5cb2` as a new row in `_INDEX.md` §4; the whole cluster tier re-run from its beginning (§7). B1, B2, B3f, B3g and the other controls unchanged | user, 2026-10-24 | uncommitted (no commit asked for) |
| H3 | cluster re-run | B3h (a), B3a paths | the harness flushed only `ks`, and its clone and node paths were fixed to run 1's | `cluster-run.sh`: `CDC_CLONE`, `CDC_NODE`, `CDC_CTL_FLUSH=all` (`nodetool flush` with no keyspace, writes `ctl-plain/flush.txt` with start/end ms and exit; port 9091 added to the pre-check); `cluster-readings.py` and `selfcheck.py` read the post-flush window from `flush.txt` (selfcheck also cross-checks it with `commands.log`; `-` skips the unit part). Defaults reproduce run 1 (re-checked: `cluster-readings.py` on run 1's logs prints the same table, `selfcheck.py` on run 1's logs reproduces `run1/selfcheck.out` byte for byte) | AI, 2026-10-24 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** unit [`run1/unit/commands.log`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1/unit/commands.log)
and [`run1/unit/summary.txt`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1/unit/summary.txt), raw STAGE4 lines `run1/unit/<jvm>.stage4.out`;
cluster [`run1/cluster/commands.log`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1/cluster/commands.log) and
[`run1/cluster/summary.txt`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1/cluster/summary.txt), per arm `run1/cluster/<arm>/`
(`settings.txt`, `statvfs.txt`, `sampler.csv`, `sampler.events`, `stress-results.txt`, `count.txt`, `logscan.txt`, `system-log-lines.txt`,
`debug-freed-up.txt`). Tables made by `unit-readings.py` and `cluster-readings.py` from those files ([`run1/unit-readings.md`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1/unit-readings.md),
[`run1/cluster-readings.md`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1/cluster-readings.md)).

### 4.1 Readings

**Unit tier** (S = 1 MiB = 1,048,576 B; rows of 64 KiB)

| JVM | s MiB | mode | rows accepted | accepted MiB | rejected | at first rejection: links / link bytes / counter in message | max links | max link bytes | max idx bytes | links deleted | B2f window | B2g row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| block-s8 | 8 | blocking | 105 | 6.56 | 1 | 7 / 7,340,032 / 7,340,134 | 7 | 7.00 MiB | 112 | 0 | [4, 9] MiB accepted; max ≤ 9 MiB | 1 |
| block-s16 | 16 | blocking | 225 | 14.06 | 1 | 15 / 15,728,640 / 15,728,870 | 15 | 15.00 MiB | 240 | 0 | [12, 17]; ≤ 17 | 1 |
| block-s32 | 32 | blocking | 465 | 29.06 | 1 | 31 / 32,505,856 / 32,506,342 | 31 | 31.00 MiB | 496 | 0 | [28, 33]; ≤ 33 | 1 |
| nonblock-s8 | 8 | non-blocking | 512 (32 MiB) | 32.00 | 0 | — | 8 | 8.00 MiB | 102 | 29 | no exception; ≤ 9; ≥ 1 deleted | 1 |
| nonblock-s16 | 16 | non-blocking | 1,024 | 64.00 | 0 | — | 16 | 16.00 MiB | 245 | 55 | ≤ 17 | 1 |
| nonblock-s32 | 32 | non-blocking | 2,048 | 128.00 | 0 | — | 32 | 32.00 MiB | 501 | 107 | ≤ 33 | 1 |
| ctl-plain (`cdc=false`) | 8 | blocking | 512 | 32.00 | 0 | — | 8 | 8.00 MiB | 0 | 0 | no exception; ≤ 2 links after recycle | holds (0 links after recycle) |
| ctl-1024 | 1024 | blocking | 2,048 | 128.00 | 0 | — | 138 | 138.00 MiB | 2,182 | 0 | no exception with 128 MiB | holds |

Helper: `calculateDefaultSpaceInMiB(…, 4096, 4 GiB, 1, 8)` = **512**; with 100 GiB = **4096** (both exact). JUnit: every JVM 1 test, 0 failures.

**Cluster tier** (S = 32 MiB; rows of 16 KiB; stress at 2,000 rows/s, 16 threads)

| arm | yaml | read-back | stress errors / partitions | rows in table | accepted MiB | WARN `Rejecting` / ERROR entries | `Freed up` lines | max link bytes | max links | max idx B | links deleted | B3f window | B3g row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b256 | 256MiB, block | 256MiB | 183,692 / 200,000 | 16,308 | 254.8 | 12 / 183,692 | 0 | 256.00 MiB | 8 | 144 | 0 | errors, WARN; [128, 288]; ≤ 288 | 1 |
| b1024 | 1024MiB, block | 1024MiB | 134,757 / 200,000 | 65,243 | 1,019.4 | 9 / 134,757 | 0 | 1,024.00 MiB | 32 | 576 | 0 | [896, 1056]; ≤ 1056 | 1 |
| bdef | 0MiB, block | **4096MiB** (statvfs → 4096) | 59,013 / 320,000 | 260,977 | 4,077.8 | 5 / 59,013 | 0 | 4,096.00 MiB | 128 | 2,304 | 0 | [3968, 4128]; ≤ 4128 | 1 |
| n256 | 256MiB, non-block | 256MiB | 0 / 200,000 | 199,996 | 3,124.9 | 0 / 0 | 74 | 256.00 MiB | 8 | 115 | 92 | 0 errors; deletion; ≤ 288 | 1 |
| n1024 | 1024MiB, non-block | 1024MiB | 0 / 200,000 | 199,996 | 3,124.9 | 0 / 0 | 55 | 1,024.00 MiB | 32 | 547 | 68 | ≤ 1056 | 1 |
| ndef | 0MiB, non-block | **4096MiB** | 0 / 320,000 | 319,984 | 4,999.8 | 0 / 0 | 27 | 4,096.00 MiB | 128 | 2,275 | 31 | ≤ 4128 | 1 |

Controls: **(a)** `cdc=false` table, 256MiB blocking: 0 errors of 200,000, 0 WARN; max link bytes 288.0 MiB (9 links; bound 288 MiB);
links at the last sample (about 34 s after `nodetool flush ks`) **6** (expected ≤ 2) → **fails**. **(b)** `cdc_enabled: false`, 256MiB
blocking: read-back `cdc_enabled false`, `cdc_total_space 256MiB`; 0 errors of 200,000; 0 links at every sample → holds. **(c)** start-up
`cdc_enabled: false`, 0MiB: read-back `0MiB`, no "Small cdc volume" line → holds.

### 4.2 Unit tier — conclusion and logic

1. **Validity.** Every setting took effect (the test asserts S = 1 MiB, A = s MiB, the mode and the CDC segment manager before writing)
   [observed: `run1/unit/<jvm>.stage4.out`, `config` lines; JUnit 0 failures]. The limit was reached and passed: blocking JVMs were
   rejected; non-blocking JVMs wrote 4·s MiB and deleted 29–107 links [observed: `run1/unit/summary.txt`]. Valid.
2. **Readings.** Nothing unusual. The plateau is k − 1 links at every value (all values are exact multiples of S), the case the source
   predicts when index bytes tip the counter: the counter in the message is the link bytes plus the index bytes (e.g. 7,340,134 =
   7 MiB + 102) [observed: `block-s8.stage4.out`]. Non-blocking never exceeded k links [observed].
3. **Matched row.** B2g row 1 for all six scenarios: "sizes ≤ s + segment, rejection/deletion near s" with the amended windows —
   accepted 6.56 / 14.06 / 29.06 MiB in [s − 4, s + 1]; max link bytes s − 1 MiB (blocking) and s MiB (non-blocking) ≤ s + 1; rejection
   (blocking) and deleted links (non-blocking) present [observed: `unit-readings.md`]. Helper exact (row 3 not matched). Controls hold.
4. **Excluded rows.** Row 2 (grows past s + 2): max ≤ s. Row 3: helper exact. Rows 4–5: no overshoot, accepted bytes inside the window.
   Row 6: rejection present. Row 7: 0 exceptions in non-blocking. Row 8: links deleted. Row 9: both controls hold [observed].
5. **Observed vs. inferred.** The only inference: that the k − 1 plateau comes from index bytes tipping the counter at an exact multiple
   [inferred: counter in message − link bytes = index bytes, e.g. 7,340,134 − 7,340,032 = 102]. The verdict does not depend on it (the
   window allows k − 1).
6. **Deviations and gaps.** `updateCDCTotalSize()` (a test hook that can re-run `processNewSegment` on a forbidden segment) is called
   every 16 rows as B2d says; it can only re-permit when the counter has dropped, which it did not in blocking mode. Real resource:
   apparent bytes of the files (the same quantity the check counts).
7. **Core question.** Usage followed the knob: blocking plateaus 7, 15, 31 MiB for s = 8, 16, 32; non-blocking 8, 16, 32 MiB under
   4·s MiB of writes (parts 1, 3). The disallow branch fired directly (exception; link deletion) (part 3), and the default derivation
   returns min(4096, total/8) (part 3). The constraint caps `cdc_raw` disk usage at the unit tier.

**Conclusion (one line):** B2g row 1 — confirmed.

### 4.3 Cluster tier — conclusion and logic

1. **Validity.** Each arm's yaml and read-back match (`settings.txt`); the default resolved to 4096 MiB = min(4096, ⌊471,482/8⌋)
   [observed: `bdef/settings.txt`, `bdef/statvfs.txt`]. The limit was passed in every arm (blocking: 59 k–184 k rejected writes;
   non-blocking: 27–74 `Freed up` lines, 31–92 links deleted) [observed]. Hold-fixed settings (S = 32 MiB, 250 ms interval) read back.
   One control (a) failed its frozen expectation (below) — by the frozen tier rule this makes the tier **Invalid**.
2. **Readings.** (i) Control (a): during the run links rose to 9 = 288 MiB (the bound, exactly) and, after `nodetool flush ks`, fell
   to 5 and then 6, not ≤ 2 [observed: `ctl-plain/sampler.csv`]. (ii) `count(*)` is 4 rows short of 200,000 in every non-failing
   200,000-row arm and 16 short at 320,000, the same in every arm: duplicate keys from the stress `seq` → `uuid` generator, not lost
   writes (stress reports 0 errors) [inferred: identical shortfall across arms; b256 and b1024 count + errors = 200,000 exactly]. It does not
   affect any window. (iii) `logscan.txt` ran before drain and counts one `Freed up` line fewer than the full log (74 vs 75 etc.); both ≥ 1.
3. **Matched row.** All six arms: B3g row 1 ("`du` plateaus at ≈ knob (+1 segment)") with the amended windows — blocking: failures,
   `Rejecting mutation` WARN, accepted 254.8 / 1,019.4 / 4,077.8 MiB in [A − 128, A + 32], max link bytes exactly A (8, 32, 128 links);
   non-blocking: 0 failures, deletion present, max exactly A [observed: `cluster-readings.md`]. Default read-back 4096 = predicted
   (row 4 not matched). **Tier:** control (a) failed → amended row 9 → **Invalid**.
4. **Excluded rows.** Row 2: max = A, never past A + 2S. Row 3: failures present in every blocking arm. Row 4: default exact.
   Rows 5–6: no overshoot, accepted inside windows. Row 7: 0 failures and 0 WARN in non-blocking. Row 8: deletion present. Row 9:
   **matched** by control (a).
5. **Observed vs. inferred.** Why control (a) failed [inferred: segments still holding unflushed **system** table writes are not
   discarded by `nodetool flush ks`, so their links stay; supported by `debug.log` at drain flushing `system.local`,
   `system.sstable_activity` etc. with non-zero usage, and by the unit control, whose `forceRecycleAllSegments()` flushes every table and
   left 0 links]. The verdict does not rest on this inference; it rests on the observed 6.
6. **Deviations and gaps.** The `/8` branch of the default is not exercised at the cluster tier on this host (environment limit, §1);
   the cluster default arm tests the 4096 branch only. Sampling every 0.25 s (amended) — a sub-250 ms overshoot could be missed; the
   unit tier, sampling after every row, saw none.
7. **Core question.** In every arm `cdc_raw` stopped at exactly the knob (256, 1024, 4096 MiB) and the disallow branch fired
   (rejections; deletions), so usage followed the constraint (parts 1, 3). But the frozen tier rule requires every control to hold, and
   control (a)'s post-flush expectation, written at the audit, was wrong in a way found only by this reading; it cannot be edited now.
   The tier is therefore Invalid and the cluster-tier answer stays formally undetermined.

**Conclusion (one line):** B3g row 9 (control fails) — invalid run; the six arms individually match row 1.

## 5. Self-check of run 1 — AI

`selfcheck.py` re-derives every number from the raw files without using the RESULT lines, `logscan.txt`, the summaries or the readings
scripts (per-row STAGE4 lines; `sampler.csv`/`.events`, `stress.log`, `count.txt`, `settings.txt`, `statvfs.txt`, full `system.log*` and
`debug.log*` with rotated zips) and tests each against the amended windows. Output: [`run1/selfcheck.out`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1/selfcheck.out) —
24 checks, **1 failed: `cluster ctl-plain`** (6 links at the last sample), the same finding as §4.3. Raw files re-opened by hand:
`block-s8.stage4.out` (firstReject line), `n256/debug-freed-up.txt` (first `Freed up` line: 100,663,410 bytes freed, total 201,326,592,
allowed 268,435,456), `b256/first-error-entry.txt` (one `ERROR … Failed to apply mutation locally` with `CDCWriteException` per rejected
write), `ctl-plain/sampler.csv` (5 → 6 links after the flush at 22:14:27 EDT).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes (unit); yes, with the control failure stated (cluster) | read-backs and `statvfs` re-read; self-check reproduces them |
| 2. Readings | yes | `Freed up` counts differ by one between `logscan.txt` (before drain) and the full log; stated |
| 3. Matched row | yes | all six unit scenarios and six cluster arms pass the independent windows |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | the two inferences (index tip; system-table pinning) are labelled and carry no verdict |
| 6. Deviations and gaps | yes | `/8` branch gap stated |
| 7. Core question | yes | unit: caps; cluster: tier rule applied as frozen |

### 5.2 Run 2?

**No** — 2026-10-24. The unit verdict rests on observed readings that the self-check reproduces. The cluster verdict is Invalid by the
frozen rule; a run 2 of the same frozen file would meet the same control expectation. Re-opening the cluster tier needs a corrected
control (recommendation 9) as a new frozen version, which is for stage 3 / a later stage-4 session to decide.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Cluster re-run ("run 1b") after the B3h (a) amendment — 2026-10-24/25

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-24, **authorised by the user (Yang, the advisor) on 2026-10-24**.
Sections 1–6 above are run 1 as filed and are not changed; run 1's excerpts under `run1/` are untouched. The unit tier is closed and
was not re-run.

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's control (a) missed its frozen expectation (§4.3), so the cluster tier was Invalid. README: a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised the amendment and a re-run of the whole cluster tier on 2026-10-24. |
| **Amendment** | `Amendment 2026-10-24 (after run 1, authorised by the user) — B3h (a)`, placed under the B3h amendment in the case file. It changes only control (a)'s post-flush step and its expected value: `nodetool flush` with **no keyspace argument** (every keyspace, local system keyspaces included: `Flush.java:38-45`, `NodeTool.java:471-488`, `StorageService.java:6231-6234`, `Schema.java:353-356`), then 30 s; post-flush count = the **largest** link count of every sample from 30 s after the flush returns until the sampler stops; **expected ≤ 2**, derived from the source: the flush returns after each table's commit-log discard (`StorageService.java:4743-4749`, `ColumnFamilyStore.java:1114-1116`, `:1147-1152`); a discard removes every active segment that has become unused, never the one being allocated (`CommitLog.java:361-382`, `CommitLogSegment.java:421-424`, `:611-619`); the link of a discarded segment without CDC data is deleted (`CommitLogSegmentManagerCDC.java:66-83`, `:186-187`); the only links left are those of the allocating segment (`:195-210`, `:236-249`) and the segment prepared ahead, which is not in `activeSegments` (`AbstractCommitLogSegmentManager.java:189`, `:307-312`). Paths only: clone `$W/cassandra-run9`, node `$W/node-cdc2`. B1, B2, B3f, B3g and the other controls unchanged. |
| **Case-file version** | sha256 **`ad11ccdcda91abaf537e419585a535f3afe0fc0a663a43a94899f52929295cb2`** (new row in `_INDEX.md` §4, "re-frozen after run 1 for cluster re-run (B3h (a)), authorised by the user"); earlier rows (`60f786b8…`, `cfaee9a0…`) kept. Hashed before any re-run reading; section D was filled afterwards. Base commit `0d66108`; nothing committed. |
| **Harness** | Run 1's harness with change H3 (§3) only. sha256 prefixes at the re-run: `cluster-run.sh` `83fb6b2c`, `cluster-readings.py` `0f1d0bf3`, `selfcheck.py` `98bccbe2`; unchanged: `cdc-sampler.py` `2158b5d0`, `logscan.py` `e017cb9c`, `cdc.yaml` `6c0f1ff6`, `plain.yaml` `3b0a431f`. Command: `CDC_CLONE=$W/cassandra-run9 CDC_NODE=$W/node-cdc2 CDC_CTL_FLUSH=all cluster-run.sh run2` (all nine arms in the frozen order). |

### 7.2 Environment

Same host and storage as run 1 (§2). Cluster tier 2026-10-24 23:38:41 – 2026-10-25 00:00:17 EDT. Fresh clone `$W/cassandra-run9` from
`~/cassandra-src`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change, `ant -Dlocal.repository=$W/m2
build-test` `BUILD SUCCESSFUL` in 50 s. `statvfs` total 494,384,795,648 B (471,482 MiB) → default 4096 MiB; free disk 153 GiB before, 151 GiB
after. Pre-check: no `CassandraDaemon`, ports 7000/7199/9042/9091 free; at the end no `CassandraDaemon` or `cassandra-stress`, the four ports
free, `$W/node-cdc2` wiped. Full logs (903 MB): `$W/logs/cdc_total_space-applySimpleConfig/cluster-run2/` (clone and build logs in
`cluster-run2-build/`, driver output `cluster-run2-driver.out`). Excerpts: [`run1b-cluster/`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1b-cluster/)
(`cluster/commands.log`, `cluster/summary.txt`, per arm as run 1 plus `ctl-plain/flush.txt`; `cluster-readings.md`; `selfcheck.out`).

### 7.3 Readings

Made by `cluster-readings.py` from the raw files ([`run1b-cluster/cluster-readings.md`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1b-cluster/cluster-readings.md)).
S = 32 MiB; rows of 16 KiB; stress at 2,000 rows/s, 16 threads.

| arm | yaml | read-back | stress errors / partitions | rows in table | accepted MiB | WARN `Rejecting` / ERROR entries | `Freed up` lines | max link bytes | max links | max idx B | links deleted | B3f window | B3g row |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b256 | 256MiB, block | 256MiB | 183,692 / 200,000 | 16,308 | 254.8 | 12 / 183,692 | 0 | 256.00 MiB | 8 | 144 | 0 | errors, WARN; [128, 288]; ≤ 288 | 1 |
| b1024 | 1024MiB, block | 1024MiB | 134,757 / 200,000 | 65,243 | 1,019.4 | 9 / 134,757 | 0 | 1,024.00 MiB | 32 | 576 | 0 | [896, 1056]; ≤ 1056 | 1 |
| bdef | 0MiB, block | **4096MiB** (statvfs → 4096) | 61,052 / 320,000 | 258,938 | 4,045.9 | 6 / 61,052 | 0 | 4,064.00 MiB | 127 | 2,286 | 0 | [3968, 4128]; ≤ 4128 | 1 |
| n256 | 256MiB, non-block | 256MiB | 0 / 200,000 | 199,996 | 3,124.9 | 0 / 0 | 74 | 256.00 MiB | 8 | 115 | 92 | 0 errors; deletion; ≤ 288 | 1 |
| n1024 | 1024MiB, non-block | 1024MiB | 0 / 200,000 | 199,996 | 3,124.9 | 0 / 0 | 55 | 1,024.00 MiB | 32 | 547 | 68 | ≤ 1056 | 1 |
| ndef | 0MiB, non-block | **4096MiB** | 0 / 320,000 | 319,984 | 4,999.8 | 0 / 0 | 26 | 4,096.00 MiB | 128 | 2,276 | 30 | ≤ 4128 | 1 |

Controls: **(a)** `cdc=false` table (`ks.p`), 256MiB blocking: 0 errors of 200,000, 0 WARN; max link bytes 288.0 MiB (9 links; bound
A + S = 288 MiB). `nodetool flush` (no keyspace) ran 23:56:55.907–23:56:58.041 EDT (2,134 ms, exit 0; `ctl-plain/flush.txt`), flushing
50 tables in all six schema keyspaces (`debug.log` `Forcing flush on keyspace`: `system` 23, `system_schema` 11, `system_auth` 8,
`system_distributed` 4, `system_traces` 2, `ks` 2). Links 9 → 5 → 4 → **0** at 23:56:58.229, then **1** from 23:57:25.8 to the end; 21
samples from 30 s after the return (23:57:28.0) to the sampler's stop, **max 1** (expected ≤ 2) → **holds**. **(b)** `cdc_enabled: false`,
256MiB blocking: read-back `cdc_enabled false`, `cdc_total_space 256MiB`; 0 errors of 200,000; 0 links at every sample → holds. **(c)** start-up
`cdc_enabled: false`, 0MiB: read-back `0MiB`, no `Small cdc volume` line → holds.

### 7.4 Cluster re-run — conclusion and logic

1. **Validity.** The re-run used the re-frozen version (`ad11ccdc…`) and ran every arm and control of B3 from the beginning in the frozen
   order [observed: `run1b-cluster/cluster/summary.txt`, first line: arms, runner hash, clone, node, `ctl-plain flush all`]. Each arm's yaml
   and read-back match; the default resolved to 4096 MiB = min(4096, ⌊471,482/8⌋) [observed: `bdef/settings.txt`, `bdef/statvfs.txt`].
   The limit was passed in every arm (blocking: 61 k–184 k rejected writes; non-blocking: 26–74 `Freed up` lines, 30–92 links deleted)
   [observed]. All three controls hold. Valid.
2. **Readings.** (i) bdef plateaued at 127 links (4,064 MiB = A − S), run 1 at 128; both inside the window, which allows k − 1 at an exact
   multiple (index bytes tip the counter, B3f amendment) [observed: `bdef/sampler.csv`]. (ii) Control (a)'s count fell to **0** right
   after the flush and then rose to 1: the allocating segment was forbidden (no link) at the flush and was linked when the next write
   re-permitted it [inferred: `permitSegmentMaybe`, `CommitLogSegmentManagerCDC.java:195-210`; observed: the `+` event at 23:57:25.8 in
   `ctl-plain/sampler.events`]. Either value is within ≤ 2. (iii) The b256 and b1024 error counts equal run 1's exactly (183,692 and
   134,757); with a 2,000/s throttle and deterministic keys, rejection begins at the same row count. (iv) `count(*)` shortfalls of 4 / 16 rows
   are the same as in run 1 (duplicate stress keys, §4.3 (ii)).
3. **Matched row.** All six arms: B3g row 1 with the amended windows. Blocking: failures, `Rejecting mutation` WARN, accepted 254.8 / 1,019.4
   / 4,045.9 MiB in [A − 128, A + 32], max link bytes 256 / 1,024 / 4,064 MiB ≤ A + 32. Non-blocking: 0 failures, `Freed up` lines and
   deleted links present, max exactly A [observed: `cluster-readings.md`]. Default read back 4096 = predicted (row 4 not matched).
   Controls hold (row 9 not matched). **Tier rule: Confirmed.**
4. **Excluded rows.** Row 2: max ≤ A, never past A + 2S. Row 3: failures in every blocking arm. Row 4: default exact. Row 5: no overshoot
   past A + S. Row 6: accepted bytes inside every window. Row 7: 0 failures and 0 WARN in non-blocking arms. Row 8: deletion present in
   every non-blocking arm. Row 9: controls (a), (b), (c) hold [observed].
5. **Observed vs. inferred.** Inferred: the 0 → 1 step in control (a) comes from re-permission of the allocating segment (part 2 (ii)); the
   verdict does not rest on it (any count ≤ 2 holds). Everything the verdict uses is observed.
6. **Deviations and gaps.** None against the re-frozen runbook. As in run 1: the `/8` branch of the default is not exercised at the cluster
   tier on this host (no fixed-size writable volume; the volume/8 arm stays `not run`), so the cluster default arm tests the 4096 branch only;
   0.25 s sampling could miss a sub-250 ms overshoot.
7. **Core question.** In every arm `cdc_raw` stopped at the knob (256, 1024, 4096 MiB, or one segment below at the default) while 3.1–5.0 GB
   were written, and the disallow branch fired directly (rejected writes in blocking mode, deleted links in non-blocking mode); the
   `cdc=false` and `cdc_enabled: false` controls show the bound comes from CDC tracking and the allowance. The constraint caps `cdc_raw`
   disk usage at the cluster tier, and usage follows it (parts 1, 3).

**Conclusion (one line):** B3g row 1 — confirmed (all six arms row 1, default exact, controls hold).

### 7.5 Self-check of the cluster re-run — AI

`selfcheck.py - <cluster-run2>` (unit part skipped; ctl-plain checked against the amended B3h (a)) re-derives every number from the raw files
(`sampler.csv`/`.events`, `stress.log`, `count.txt`, `settings.txt`, `statvfs.txt`, full `system.log*`/`debug.log*` with rotated zips,
`flush.txt` cross-checked against the `+ nt flush` / `exit=0` lines of `commands.log`), without the readings script, `logscan.txt` or the
summary. Output: [`run1b-cluster/selfcheck.out`](cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/run1b-cluster/selfcheck.out) —
15 checks, **0 failed**. (Its `Freed up` counts read the full logs after drain, 75 / 56 / 27, one more than `logscan.txt` before drain,
as in run 1.) Raw files re-opened by hand: `ctl-plain/sampler.csv` (9 links at the end of the stress, 0 at 23:56:58.229, 1 until the last
row), the node's `debug.log` (50 `Forcing flush on keyspace` lines in six keyspaces), `ctl-plain/flush.txt` (exit 0), `b256/first-error-entry.txt`
(`CDCWriteException: Rejecting mutation to keyspace ks`), `n256/debug-freed-up.txt` (first line: freed 100,663,410 bytes, allowed 268,435,456),
`bdef/settings.txt` and `ndef/settings.txt` (`4096MiB`).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | re-frozen hash recorded before the run; read-backs and `statvfs` reproduced |
| 2. Readings | yes | bdef k − 1 plateau and control (a)'s 0 → 1 step re-read in the sampler files |
| 3. Matched row | yes | six arms pass the independent windows; three controls hold |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | the one inference (re-permission) is labelled and carries no verdict |
| 6. Deviations and gaps | yes | `/8` branch gap stated |
| 7. Core question | yes | caps; usage follows the knob |

**Run 2?** No — 2026-10-25. The verdict rests on observed readings that the self-check reproduces, and the six arms repeat run 1's
readings (run 1 is an independent repeat of the arms, at the earlier frozen version).

### 7.6 Verdict of the cluster re-run

**Confirmed — caps** (B3g row 1; tier rule: all six arms row 1, default read back 4096 MiB as predicted, controls (a), (b), (c) hold).
Filed in §8 as a new cluster row; the run-1 cluster row (Invalid) is kept.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** with `cdc_enabled: true`, total bytes in `cdc_raw` stay ≤ `cdc_total_space` + one commit-log segment; in blocking
mode writes to a CDC table are then rejected, in non-blocking mode old CDC files are deleted; with `cdc_total_space: 0MiB` the effective
allowance equals `min(4096 MiB, cdc_raw volume size / 8)`.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1, all six scenarios; helper exact; controls hold) | caps | run 1 + self-check | 2026-10-24 |
| Cluster | **Invalid** (B3g row 9: control (a) failed its post-flush expectation; the six arms each matched row 1 and the default read back 4096 MiB) | undetermined | run 1 + self-check | 2026-10-24 |
| Cluster (re-run at `ad11ccdc…`, after the user-authorised B3h (a) amendment) | **Confirmed** (B3g row 1: all six arms row 1; default read back 4096 MiB; controls (a) — max 1 link after `nodetool flush` + 30 s, ≤ 2 expected — (b), (c) hold) | caps | cluster re-run (§7) + self-check | 2026-10-25 |

**Feedback filed:** the case file's section D (2026-10-24, uncommitted); the twelve audit amendments in B2–B3 (dated); `_INDEX.md`
§1 Stage 4 column, §2 new sha256 row, §3 coverage line. No refutation, so no other case section is amended.

**Feedback filed for the cluster re-run (2026-10-25):** the amendment `Amendment 2026-10-24 (after run 1, authorised by the user) — B3h (a)`
in the case file; a new `_INDEX.md` §4 row (`ad11ccdc…`); the case file's section D (new entry); the §1 Stage 4 column (now closed:
unit and cluster Confirmed — caps); §3 coverage line (7 / 0). No refutation, so no other case section is amended.
