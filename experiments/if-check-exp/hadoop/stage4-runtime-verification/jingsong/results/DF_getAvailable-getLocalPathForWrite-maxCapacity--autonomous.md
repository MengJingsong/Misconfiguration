# DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous — stage-4 results  <!-- file: results/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md -->

> **Case:** [`DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.md)
>
> **Status:** **verdict filed 2026-11-06** — unit **Confirmed** (does not cap), cluster **Confirmed** (does not cap). Claim tested: the comparison `capacity > maxCapacity` at `LocalDirAllocator.java:528` does not limit local-disk usage; it only feeds the number in the failure message. Removing it changed no allocation outcome, placement or written byte count on either tier; only the message number went from the max free space to 0. The adjacent gate `capacity > size` (line 531) refused every request above the free space (positive control). Two cluster runbook defects fixed by dated amendments (A14, A15), cluster tier restarted. One run 1 per tier, no run 2.
>
> **Outcome class:** **true negative** — stage-3 estimate `negative` against the stage-4 effect `does not cap` on both tiers ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

**Layout.** Hadoop, Jingsong's share: this file is in `hadoop/stage4-runtime-verification/jingsong/results/`; the case file is in
`hadoop/stage3-ai-deep-read/jingsong/cases/`; the harness is in `../harness/<stem>/`; the protocol is
[`../../../../stage4-runtime-verification/README.md`](../../../../stage4-runtime-verification/README.md#the-run-protocol);
the node is described in [`../environment.md`](../environment.md). `<stem>` = `DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous`;
`$RUN` = `/mydata/jingsong-s4/DF_getAvailable-getLocalPathForWrite-maxCapacity-run1` on `pc41`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository HEAD `38acb6bf` plus the uncommitted case file (untracked at audit time). sha256 as filed (queue order 1): `91fee9d40d5324f3db89bf95b3a9c97dd9eb361f660ee294cd75b9d93ebecfa9` (checked before the audit). After the audit's amendments D1 (A1–A13), 2026-11-06 ~14:05 EST, before any harness run or reading: whole-file sha256 **`bb46249b9cc14bb5ec2f88281de2e0c69eead97d6aaa731c71937a913191a05d`** (frozen version). Frozen prediction and conclusions tables (sha256 of the lines from `**B2f.` up to, not including, the `**B2h.` line; likewise B3f–B3g): unit **`089648134b43e8ca2cbe69ef65fba8a7310b27745b91f667e7c8399d9aaf703b`**, cluster **`08b055ea6fd2f1124d9217f7ee5671a0c54e797c4947ed5f66ec795144cca5a2`** (`sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' <file> \| head -n -1 \| sha256sum`). Section D takes the feedback after the runs, so the whole-file hash changes then; the two table hashes must not. |
| **Harness** | `../harness/<stem>/` (written after this freeze, before run 1; see its README). Uncommitted at run time (the parent session commits); md5 of each file in `run1/cluster/cluster-run.log` and `run1/unit/unit-run.log`. |
| **Later amendments (runbook defects, §3)** | A14 (B3e) and A15 (B3d) → whole-file sha256 `8bd5cc94b71a30bc43f3ce3bb2d96d8bb49607d379bb127ab32a59d87ca61293` (the version the counted cluster run used; the unit tier ran against `bb46249b…`, and A14/A15 touch only B3). The B2f–B2g and B3f–B3g hashes above are unchanged (re-computed). Section D2 was added after the runs: sha256 now `9993691fc54ccdc95398197b72c9746351b7faea1b3638ed67b7bf81653d0df3`. |
| **Tiers and values** | Unit (B2): baseline vs ablated (lines 528-530 removed); dir0 on a 256M ext4 loop fs, dir1 on a 512M one; K3 `{dir0}`, `{dir0,dir1}`; K2 = 1024, min−64 MiB, max−64 MiB, max+64 MiB, `Long.MAX_VALUE−1` over the set; 200 calls per block; two repeats per variant. Cluster (B3): pseudo-distributed on `pc41`, one NM local dir on a 1 GiB ext4 loop fs; free levels L900 / L300 / L60; teraSort of 1,000,000 rows, 1 map, 1 reduce; baseline and ablated `hadoop-common` jar. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-06 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A1/A2/B1: local-disk free bytes (`DF.getAvailable()` = `getUsableSpace()`), and bytes written to the allocated path. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The "limit" is a runtime reading with no default (A1); the design varies its operand (free space: two volume sizes and five request sizes in B2b; three free levels in B3b) **and** removes the check (ablation, K1) — a two-arm design that isolates line 528 from line 531, as the README allows for a knob that cannot be set. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: `getUsableSpace()`/`df` before and after, `Files.size`, `du -sb` of the dirs/usercache; the internal `capacity` at line 527 is named as not directly observable and bracketed. |
| A. Core question | usage driven to the limit and past it | Met | B2c: `size` above every directory's free space (max+64 MiB, `Long.MAX_VALUE−1`); B3c: L60 below the map's first spill request. Positive control (negative estimate): the adjacent gate `capacity > size` (line 531) refuses the allocation with the same workload and instruments (B1, B2g row 3, B3g row 4). |
| B. Logic | each step says what it establishes | Met | B2h/B3h: ablation isolates line 528; before/after samples rule out drift; loop fs rules out other writers; health checker disabled. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f/B3f give relations (N = max avail, N = 0 ablated, same outcomes), but the drift tolerance, the χ² definition, "a few MiB", the 5 % peak rule's measurement and "no spill file" were undefined, and B3f's S ≈ 95-100 MiB is wrong by the source (first spill ≈ 69 MiB). **Amended** (A5, A9, A12). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows had no verdict words for some cases, and lacked: a wrong message number with equal outcomes, disagreeing repeats, failed writes, a failed jar swap, an unexpected S, other job failures. **Rows added** (A6, A13). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For this negative file: the line-531 refusal is observed directly (the exception and its message, with N), and the ablated arm shows line 528's own effect. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h (drift, other writers, randomised start index, NM health checker, more than one map). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, Ground, A3 steps 1-5, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Filed paths (`~/hadoop-3.4.2`, `/mnt/ldA*`, tarball build), `-am install` of an ablated jar into the shared `~/.m2`, `start-dfs.sh` (no SSH to localhost on this node), implicit MR-on-YARN settings. **Amended** (A1, A7, A11). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | K2 bands for `{dir0}` wrong, write rule cannot fit (200 large writes), free levels without tolerance, no timeouts or first-trigger stop, ablated cluster arm "optional" though B3g row 1 needs it. **Amended** (A2, A3, A4, A8, A10, A11). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Test class and scripts are step-1 work; JDK 8, Maven, built distribution (`/mydata/jingsong-s4/hadoop-base`, 19 YARN jars) and `sudo` for loop mounts exist on `pc41`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Unit: fine. Cluster: S was mis-estimated (A9) but L60 < S1 ≈ 69 MiB still reaches the gate, and L300 > ≈ 200 MiB peak. NM 4096 MB fits AM 1536 + map 1024 + reduce 1024. `/mydata` 697 GB free. **Amended** (A9). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | At `rel/release-3.4.2` (`systems/hadoop/source/`, clean): `LocalDirAllocator.java:429` (`maxCapacity = 0`), `:518` (note), `:521-527`, `:528-530` (the check), `:531` (gate), `:560-572` (message, throw); `grep -n maxCapacity` → 429, 528, 529, 566 only; `:150-172` (entry); `:291-298` (`getAndIncrDirNumLastAccessed`); `DF.java:95-97` (`getUsableSpace`); `MapTask.java:985-1022, 1619-1628, 1727-1734, 1864-1903`; `DirectoryCollection.java:565-572` (100.0 % cutoff never trips unless full). All as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A1, A7) | Node paths under `$RUN`, `copy-source.sh`, no ablated install into `~/.m2`, `--daemon` starts, implicit MR-on-YARN settings | Applied 2026-11-06 (uncommitted; frozen sha256 above) | filed paths and commands do not work on the node |
| R2 (A2, A3, A4, A5) | Unit bands over the K3 set; exact write rule; run order; tolerances | Applied 2026-11-06 | wrong `{dir0}` prediction; writes would not fit |
| R3 (A9, A12) | Correct the first spill request (≈ 69 MiB, not 95-100) and its prediction | Applied 2026-11-06 | source arithmetic (80 % spill threshold, 16 B metadata) |
| R4 (A6, A13) | Verdict per row; rows for uncovered outcomes | Applied 2026-11-06 | every plausible outcome needs a row before any reading |
| R5 (A8, A10, A11) | Level tolerances, 0.5-s sampling, timeouts, first-trigger stop, required ablated arm | Applied 2026-11-06 | stop conditions missing; B3g row 1 needs the ablated arm |
| R6 | A cluster workload with a request size close to the free space on two dirs (placement shift) | Left for stage 3 | not needed: the unit tier covers placement |

**Agreement criteria** — only if run 2 is chosen (see 5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-06 (unit 14:09–14:13 EST; cluster attempt 1 14:15–14:18, stopped at defect 1; counted cluster run 14:19–14:25) | not done |
| Node | `pc41` = `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (the local node), 40 cores, 251 GiB; no Hadoop daemon running and all default ports free before the cluster run (the parallel MAX_KEY_SIZE case used non-default ports) | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | — |
| JDK (`java -version`) | openjdk `1.8.0_504` (`/usr/lib/jvm/java-8-openjdk-amd64`, build, tests and daemons) | — |
| Build tool | Apache Maven 3.6.3, offline (`-o`), other 3.4.2 modules from the node's `~/.m2`; nothing installed | — |
| Local source copies | `$RUN/src-baseline`, `$RUN/src-ablated`, made by `../copy-source.sh` from `systems/hadoop/source/` at HEAD `38acb6bf` (clean), tag `rel/release-3.4.2`; ablated copy: `LocalDirAllocator.java` lines 528-530 deleted (`git diff --numstat` 0/3); both: the harness test class added | — |
| Cluster distribution | `$RUN/hadoop` = copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2`; ablated arm: `share/hadoop/common/hadoop-common-3.4.2.jar` replaced (md5 `08ee88e6…` → `b35f6e32…`, built by `mvn -o package` in `src-ablated`) | — |
| Case-file commit / harness commit | `38acb6bf` + the uncommitted case file at sha256 `bb46249b…` (unit) / `8bd5cc94…` (cluster) / uncommitted; harness md5: `TestLdaMaxCapacity.java` 67f558ea, `unit-run.sh` efcc4567, `cluster-run.py` 9739c79e (counted run), `unit-analyze.py` bac1f875 (after the fix in §4.2 part 6), `selfcheck.py` f4c544e8 (final) | — |
| Storage | unit: ext4 loop filesystems of 256M (dir0, 215,781,376 B usable) and 512M (dir1, 473,268,224 B) from images in `$RUN/ldA/`; cluster: NM local dir on a 1 GiB ext4 loop fs (`$RUN/ldc/nmlocal.img`, 950,190,080 B usable empty), HDFS and logs on `/mydata` (`/dev/mapper/emulab-node0--bs`); nothing on `/proj`. Images deleted after the self-check. | — |
| Full logs (path, outside the repo) | `$RUN/logs/unit/` (four runs: `mvn-test.log`, surefire output and XML, CSVs; `unit-run.log`, `unit-summary.txt`), `$RUN/logs/cluster/` (counted run: `cluster-run.log`, per job `*-client.log`, `*-samples.csv`, `*-applog/` full container logs, `*-map-keylines.txt`), `$RUN/logs/cluster-attempt1/` (defects 1-2), `$RUN/logs/daemons/`, `$RUN/logs/selfcheck.txt` | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1, cluster | B3e step 4 (A11): restart the daemons for the ablated arm, then repeat step 3 | The first ablated job failed after 4 s: `SafeModeException: Cannot create file/ts-ablated-L900/_partition.lst. Name node is in safe mode … In safe mode extension. Safe mode will be turned off automatically in 21 seconds` (`run1/cluster/attempt1-defects.txt`). The "cluster up" check (1 live DataNode) passes before the 30-s safe-mode extension ends. | A14: `hdfs dfsadmin -safemode wait` after every daemon start. B3f/B3g unchanged; cluster tier restarted from the beginning (fresh loop fs, distribution, format). | Amendment, 2026-11-06 | uncommitted; sha256 `8bd5cc94…` |
| 2 | 1, cluster | B3d (A10): read task syslogs from `yarn.nodemanager.log-dirs` | After the restart the NodeManager had deleted the non-aggregated container logs of the baseline jobs (`$RUN/logs/cluster-attempt1/` keeps only the extracted key lines), so the raw syslogs could not be re-read. Also, attempt 1 counted the AM as a second map container at L60 (its syslog quotes `org.apache.hadoop.mapred.MapTask` in the failed task's stack trace); the job counter said `Launched map tasks=1`. | A15: copy each application's log dir after its job; find the map container by the `MapTask` logger prefix and check it against the counter. Same restart as defect 1. | Amendment, 2026-11-06 | uncommitted; sha256 `8bd5cc94…` |

Readings of the baseline arm of attempt 1 (same values as the counted run: L60 refused 72,511,848 B; L900/L300 succeeded) existed when A14 and A15 were written. Both depend only on the failures (a daemon wait and log retention), not on any value, and change no prediction or conclusions row; the counted cluster run is the restarted one. The unit tier was not affected.

## 4. Run 1

**Scope:** unit tier, 10 blocks × 200 calls, baseline and ablated, two repeats each; cluster tier, L900 / L300 / L60 × baseline and ablated jar, one pass. **Command logs:** `<stem>/run1/unit/unit-run.log`, `<stem>/run1/cluster/cluster-run.log`.

### 4.1 Readings

**Unit tier** (identical in both repeats; `run1/unit/unit-summary.txt`). dir0 usable 215,781,376 B, dir1 473,268,224 B at every block start.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `{dir0}` 1024 B; A0 − 64 MiB (148,672,512) twice | 200/200 succeed in dir0, baseline and ablated | `run1/unit/unit-summary.txt` |
| `{dir0}` A0 + 64 MiB (282,890,240); `Long.MAX_VALUE − 1` | 200/200 `DiskErrorException`, both variants; N = 215,781,376 (baseline, deviation from the max before-call sample 0 B), N = 0 (ablated) | same |
| `{dir0,dir1}` 1024 B; min − 64 MiB (148,672,512) | 200/200 succeed, 100 dir0 / 100 dir1, both variants (χ² p = 1) | same |
| `{dir0,dir1}` max − 64 MiB (406,159,360) | 200/200 succeed, all in dir1, both variants | same |
| `{dir0,dir1}` max + 64 MiB (540,377,088); `Long.MAX_VALUE − 1` | 200/200 fail, both variants; N = 473,268,224 (baseline, deviation 0 B), 0 (ablated) | same |
| Baseline vs ablated, all 10 blocks × 2 repeats | success/failure counts and histograms equal; repeats agree | same |
| Written files | 404 per run (400 × 2048 B for size 1024; 4 large: 182,226,944 B for size 148,672,512, 439,713,792 B for 406,159,360); each file as large as written, > size; 0 write failures | same; `run1/selfcheck.txt` |
| Surefire | 1 test, 0 failures, 0 errors, each of 4 runs | `run1/unit/unit-run.log`, `run1/selfcheck.txt` |

**Cluster tier** (`run1/cluster/*-samples.csv`, 0.5-s samples; `*-client.log`; `*-map-keylines.txt`):

| Capacity value (free before job) | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| L900: 950,190,080 B (906.2 MiB) | baseline | outcome; map known-size requests; peak `du` usercache | SUCCEEDED, 1 map; 72,511,848 / 29,488,452 / 104,000,162 / 24 B; **208,971,148 B (199.3 MiB)** | `baseline-L900-*` |
| L300: 314,568,704 B (300.0 MiB) | baseline | same | SUCCEEDED, 1 map; same requests; **208,971,148 B**; min avail 105,431,040 B | `baseline-L300-*` |
| L60: 62,910,464 B (60.0 MiB) | baseline | outcome; message S, N; peak `du` | FAILED, map failed (1 launched); "requested size **72511848** … is **61792256**"; last `df` sample before it 62,189,568 B (Δ 0.38 MiB); peak `du` 958,646 B | `baseline-L60-*` |
| L900: 950,202,368 B | ablated | as L900 | SUCCEEDED, 1 map; same four requests; **208,971,140 B** | `ablated-L900-*` |
| L300: 314,568,704 B | ablated | as L300 | SUCCEEDED, 1 map; **208,971,139 B** | `ablated-L300-*` |
| L60: 62,910,464 B | ablated | as L60 | FAILED, map failed; "requested size **72511848** … is **0**"; peak `du` 958,637 B | `ablated-L60-*` |

### 4.2 Conclusion and logic

1. **Validity** — valid on both tiers. Unit: 4 runs, surefire 1/0/0 each [observed: `run1/selfcheck.txt`]; the request sizes reached and passed the free space of every directory (blocks 4, 5, 9, 10) [observed: `run1/unit/unit-summary.txt`]; loop filesystems idle (the before/after samples are constant within each failing block; deviation 0 B) [observed: same]; the ablated build was the one tested (N = 0 in every ablated failure) [observed: same]. Cluster: exactly 1 map per job (counter and container) [observed: `run1/selfcheck.txt`]; the free levels were 906.2 / 300.0 / 60.0 MiB, inside the A8 tolerances [observed: `run1/cluster/cluster-run.log`]; the NM health checker did not mark the dir bad (the L60 map ran and failed in the allocator itself) [observed: `run1/cluster/baseline-L60-map-keylines.txt`]; the ablated jar was loaded by the task (N = 0) [observed: `run1/cluster/ablated-L60-map-keylines.txt`]; the known-size branch was reached (first-trigger check: "Requested file size is" in the L900 map syslog) [observed: `run1/cluster/baseline-L900-map-keylines.txt`].
2. **Readings** — nothing unusual. The map's first request was exactly the A9 estimate (72,511,848 B); the second "Requested file size" line at L60 is the history the allocator logs after its error (no timestamp), not a second call [observed: `run1/cluster/baseline-L60-map-keylines.txt`]. In the unit tier the `{dir0}` max−64M block equals the min−64M block, as A2 states.
3. **Matched row** — Unit, B2g row 1 ("outcomes and histograms equal between baseline and ablated; only the message number differs (max avail vs 0)") and row 3 ("allocation fails when `size > max avail`, in both variants … and baseline number ≈ max avail"): every block equal, N = max avail (Δ 0 B) vs 0; every block above the free space failed 200/200 in both [observed: `run1/unit/unit-summary.txt`]; files written past `size` (A6's Confirmed condition) [observed: same]. Cluster, B3g row 1 ("success/failure depends only on free vs S, and the ablated jar shows the same pattern with N = 0"), row 2 ("usage peak at 900 MiB free ≈ usage peak at 300 MiB free (within 5 %)": 208,971,148 = 208,971,148 B baseline; 208,971,140 vs 208,971,139 B ablated) and row 4 ("at 60 MiB free the map fails with the expected message"; S = 72,511,848 > N = 61,792,256 and S ∈ (60, 100] MiB) [observed: `run1/cluster/*`].
4. **Excluded rows** — Unit: *refuted, an outcome or placement differs between variants* — 0 differences in 20 block pairs [observed]; *not confirmed, size > max avail succeeds* — 0 successes in those blocks [observed]; *investigate, written bytes capped near size* — every file as large as written (the large ones exactly 32 MiB past size) [observed]; A6a *N ≠ max avail or ablated N ≠ 0* — Δ 0 B, ablated 0 [observed]; A6b *repeats disagree* — agree [observed]; A6c *a write fails* — 0 [observed]. Cluster: *refuted (row 3, A13), the ablated arm differs, or the L300 peak is pinned below the L900 peak* — same pattern; peaks equal to the byte (and 199.3 MiB is far below the 300 MiB free) [observed]; *not confirmed (row 5), L60 succeeds or the NM marks the dir bad* — L60 failed in `LocalDirAllocator` [observed]; A13a *peaks differ > 5 %* — 0 % [observed]; A13b *L900/L300 job fails* — both succeeded in both arms [observed]; A13c *ablated N ≠ 0 or baseline N not within 4 MiB of `df`* — 0; 0.38 MiB [observed]; A13d *S ≤ N or S outside (60, 100] MiB* — S = 69.15 MiB > N [observed]; A13e *more than one map* — 1 in every job [observed].
5. **Observed vs. inferred** — The conclusion rests on observed readings. Inferred: (a) that the line-531 gate is what refused the allocations — the message is built only after the loop has found no directory with `capacity > size` (`LocalDirAllocator.java:526-566`), and it is the same with line 528 removed [inferred from the source + observed equality of the two builds]; (b) that the cluster peak `du` of `usercache` is the job's whole local-disk usage — the only NM local dir is the loop fs and the `df` avail moved by the same amount (950,190,080 − 741,052,416 = 209,137,664 B ≈ peak `du` + 0.2 MiB of filecache/metadata) [observed: `run1/cluster/baseline-L900-samples.csv`].
6. **Deviations and gaps** — (i) the allocator's DEBUG notes (B2d, line 471/518) did not appear in the unit runs: `Logger.setLevel(DEBUG)` in the test had no effect under the module's test logging; the per-call directory comes from the returned path (CSV), and the failing calls' history (ERROR level) gives the allocator's own "bytes available" values, which the self-check matched against N. The cluster tier has the DEBUG notes (`-Dmapreduce.map.log.level=DEBUG`). (ii) `unit-analyze.py` crashed on a Python name error after the four runs had finished; it was fixed and re-run on the same CSVs (a post-processing script, not a runbook step). The run log's display of the failure messages was cut at 400 characters, which shows the two-directory message's N as "47" — the CSV and the surefire output have the full 473268224. (iii) The self-check script was corrected three times before its final pass (the error line precedes its history; 404, not 406, written files; the logger name ends in `$AllocatorPerContext`) — script errors, not reading changes. (iv) The cluster tier was restarted after defects 1-2 (§3). (v) The cluster shows the gate binding at one level (L60) only; free space is a runtime reading, not a setting, so there is no default value to run.
7. **Core question** — Usage did not follow the check at line 528. Removing it left every outcome, placement and written byte count unchanged (part 3), and the only number it feeds, the "max capacity" in the failure message, went from the largest free space (to the byte) to 0 (parts 1, 3). Usage followed the workload: the same 199.3 MiB peak at 906 and 300 MiB free, files written well past the requested `size` (part 3). The adjacent gate `capacity > size` did refuse allocations when the free space was below the request, in both builds, so the workload and instruments could show a refusal (positive control, parts 3-4); line 528 is not one.

**Conclusion (one line):** Unit: B2g rows 1 + 3 — confirmed. Cluster: B3g rows 1, 2 + 4 — confirmed.

## 5. Self-check of run 1 — AI

`../harness/<stem>/selfcheck.py` re-parses the raw files without the run scripts' summaries (surefire XML; the allocator's ERROR lines and logged histories in each surefire output file; the copied container syslogs, client logs and sample CSVs of the cluster). Output `run1/selfcheck.txt`: **0 FAIL** (after the script fixes in §4.2 part 6 iii).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: surefire 0/0 ×4; 800 failures per unit run in each variant; 1 map container and `Launched map tasks=1` per job; `*-samples.csv` first rows 906.2 / 300.0 / 60.0 MiB |
| 2. Readings | yes | `baseline-L60-map-keylines.txt`: one timestamped request (14:22:03,460) and the untimestamped history copy |
| 3. Matched row | yes | `selfcheck.txt`: allocator-logged failures carry N = the max "bytes available" of the same call (0 bad), ablated N all 0; cluster S = 72,511,848 > N = 61,792,256, within 4 MiB of `df` (62,189,568); peaks equal; ablated L60 N = 0 |
| 4. Excluded rows | yes | each condition re-checked above (equal counts, write sizes, peaks, S range, map count) |
| 5. Observed vs. inferred | yes | (a) source lines 526-566 re-read: the message is built only after no directory passed `capacity > size`; (b) `baseline-L900-samples.csv`: `df` drop 209,137,664 B vs peak `du` 208,971,148 B |
| 6. Deviations and gaps | yes | none touches the measured path; the unit placement comes from returned paths, failures are cross-checked against the allocator's own logs |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B2h/B3h: ablation isolates line 528 (no change but the message), the line-531 gate binds with the same workload (change), free-space levels leave usage unchanged |

### 5.2 Run 2?

**No** — decided 2026-11-06. The conclusion rests on observed, exact readings (identical outcome counts across 20 block pairs and two repeats; peaks equal to the byte; the message number exact); the two inferred statements are settled from run 1's raw files and the source; the result confirms the stage-3 estimate rather than refuting it or confirming a bypass; the positive control moved on both tiers.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** — estimate `negative`, effect `does not cap` on both tiers.

**Claim tested:** the comparison `capacity > maxCapacity` at `LocalDirAllocator.java:528` does **not** limit local-disk usage: which directory is chosen, whether allocation succeeds, and how many bytes end up on disk are the same whether or not the check runs; its only effect is the "max capacity" number in the failure message, which equals the largest `getUsableSpace()` seen (B1).
"Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g rows 1 + 3 (10 blocks × 200 calls equal between baseline and ablated, both repeats; N = max avail vs 0; files written past `size`) | does not cap | run 1 + self-check | 2026-11-06 |
| Cluster | **Confirmed** — B3g rows 1, 2 + 4 (L900/L300 succeed with the same 208,971,148 B peak, L60 refuses the 72,511,848 B spill, in both jars; N = 61,792,256 vs 0) | does not cap | run 1 + self-check | 2026-11-06 |

**Positive control:** the adjacent gate `capacity > size` (line 531), same workload and instruments: unit, every request above the free space (282,890,240 B on 215,781,376 B free; 540,377,088 B on 473,268,224 B; `Long.MAX_VALUE − 1`) refused 200/200 in both builds; cluster, at 60 MiB free the map's 72,511,848 B spill request refused, the job failed and local usage stayed at 0.9 MiB, against 199.3 MiB at 300 and 906 MiB free.

**Feedback filed:** the case file's section D2 "Stage-4 result" (2026-11-06, uncommitted); amendments A1–A13 (audit, before any reading) and A14–A15 (runbook defects) in the sections they change and in D1. `_INDEX.md`, `queue.csv` and `case-notes.md` not edited (the parent session's job). Not committed.

**What stays on `pc41`:** `$RUN` (≈ 1.9 GB): `src-baseline/`, `src-ablated/` (with build output), `hadoop/` (distribution copy, ablated `hadoop-common` jar installed in it) and `hadoop-common-3.4.2.jar.orig`, `conf/`, `ldc/` (HDFS name/data dirs, NM log dir), `logs/`, empty `mnt/` and `ldA/`. No loop mount, no image file, no daemon, container, MR task or test JVM of this run (checked with `mount`, `ps`, `jps` at 14:27). Undo: `rm -rf $RUN`.
