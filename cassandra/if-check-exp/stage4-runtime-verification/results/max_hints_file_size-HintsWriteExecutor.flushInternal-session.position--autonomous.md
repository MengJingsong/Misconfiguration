# max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous — stage-4 results  <!-- file: results/max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous`](../../stage3-ai-deep-read/cases/max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous.md)
>
> **Status:** verdict filed 2026-10-26 - **unit: Confirmed (does not cap); cluster: Confirmed (does not cap)**; self-check 106 of 106 parts hold; no run 2
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap`)
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
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
| **Case-file version** | Repository commit `1ae567d` (HEAD at the audit; the case file was untracked, so no commit holds it yet). Original sha256 `0ab0fdefb2ca98c4fd06d92a298e8b7fb7b5f3480a5186a91432e5498ab3e349`. **After the step-0 amendments: sha256 `9f1e11e39b09936b7569fa173013a891c3de2c10e3f922397cdaf8e2aa0e9828`.** Frozen prediction and conclusion tables (B2f, B2g, B3f, B3g text, concatenated, copy in `results/max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous/run1/frozen-tables.txt`): sha256 **`d34b677b0a5b411afc485cb4aeed309d161afd60234b647878eab52e7e7cbb95`** (B2f `5927f8b2`, B2g `9c80a134`, B3f `4dd1082f`, B3g `8433ef19`). Recorded 2026-10-26 before any reading (no node had been started for this case). |
| **Harness** | `../harness/max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous/` (written after the freeze; listed in §1.2); uncommitted (the orchestrator commits). |
| **Tiers and values** | Unit: `HintsFileSizeLimitTest` through the real `HintsService.instance`, L = 1, 4, 16, 128 MiB x 3 (64 MiB of 16 KiB hints), 1 KiB-hint run at L = 1, control = real `StorageProxy.shouldHint` with `max_hints_size_per_host` 16 MiB. Cluster: two nodes on pc12 (loopback 127.0.23.1/2), fresh ring per run, L = 1, 16, 128 MiB, control L = 128 + `max_hints_size_per_host` 100 MiB; 400,000 rows x 2 KiB at 1,000 rows/s with node B down. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Disk bytes of ONE hints file (`session.position()` vs `max_hints_file_size`); B1/A2. The claim is that it is not a cap on total hint bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | Unit 1/4/16/128 MiB, cluster 1/16/128 MiB; 128 MiB is the default (Config.java:447). Yaml-only knob, so a ring per value (amended B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | File lengths (`File.length`, `du -sb`), direct `MemoryUsed` and `RssAnon`; the counter (`position()`) is read through the Byteman `roll` line. Gap: `position()` counts pre-compression bytes; runs are uncompressed (B2h). |
| A. Core question | usage driven to the limit and past it | Met after amendment | The knob is a per-file roll threshold: it is reached ~5 to ~840 times per run. Unit arithmetic fixed (counts 64/17/5/1, B2c amendment); cluster 840 MiB of hints vs 128 MiB gives 7 files at the default. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each name their observable; B1 states claim and refuted-if. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met after amendment | File counts were wrong (omitted entry overhead) and the memory tolerances unrealistic; replaced by the relation N in [T/(L+e), T/L+1], closed files in [L, L+e), T equal within 1%, control T in (cap, cap+8 MiB] (B2f/B3f amendments). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g rows: total follows L (refuted), flat (confirmed), wrong trace, limit never reached, control failed, memory moves; "counter capped but resource grows" is the memory row. Added: the confirmation needs Byteman roll lines. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly -> Met after amendment | Only file totals were required; amended to also require roll count = files with length >= L and the positive control (B2g/B3g). |
| B. Logic | alternative explanations and their controls | Met after amendment | Other caps (per-host, window) are ruled out by the control and the unset knob; the unit control was a hand-written predicate, now the real `shouldHint` (B2h); cluster B stays down so no dispatch deletes files (B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Entry table, Ground and B1 are consistent with A3. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly -> Met after amendment | B2c named private slabs and a bare executor; the harness uses `HintsService.instance`, same `flushInternal` path (A3 note). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met after amendment | Writer, rate, row count, ports, wipe/restart, sampling interval were open (B3a-B3e amendments). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Test class, Byteman rules, writer, yaml builder, JMX client, run scripts listed in §1.2 as step-1 work; JDK/Ant/Byteman jars/driver present on pc12 (environment.md). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | Unit 64 MiB x 16 runs, <= 1.1 GB of disk, minutes; cluster 840 MiB hints + data per run, 400 s per run at 1,000 rows/s (the "10-20 min" was an overestimate), pc12 has 46 GB free, 251 GiB RAM. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-read in `cassandra/cassandra-5.0.9/`: HintsWriteExecutor.java:50,60,222-231,237-257; HintsWriter.java:68-95,136-141,174-192,202,269-275; HintsStore.java:259-272,295-330; HintsService.java:79,110-122,161-169,253-258; Config.java:446-448; DatabaseDescriptor.java:3718-3721; StorageProxy.java:2442-2501; cassandra.yaml:104-115. Off by lines: `flushBuffer` (:83-86 not :100-103), `HintsBuffer.create` (:75-78), `openWriter` (:307-320), `Session.close` (:269-275), setter (:3590-3593); arithmetic wrong: unit file counts. Chain checked: `flush` -> `flushInternal` -> :247 `>=` -> `return false` -> `closeWriter` (:228-229). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Unit counts: 64/17/5/1 and the relation N in [T/(L+e), T/L+1] instead of 64/16/4/1 | Applied 2026-10-26 (B2c, B2f); case file uncommitted | 4096 entries of 16 KiB + framing exceed 64 MiB |
| 2 | Drive the unit tier through `HintsService.instance`; control = real `StorageProxy.shouldHint` | Applied 2026-10-26 (B2c, B2h) | The control must read the same catalog; same `flushInternal` path |
| 3 | Direct-memory protocol: warm-up run, difference before/after, 1 MiB tolerance | Applied 2026-10-26 (B2d, B2f) | Slabs are allocated on first use and freed only by GC |
| 4 | Confirmation also needs Byteman roll count = files >= L | Applied 2026-10-26 (B2f, B2g, B3f, B3g) | Direct evidence that the :247 branch fired |
| 5 | Cluster: fresh ring per value, fixed writer/rate/row count, my ports and directories, sampler 1 s | Applied 2026-10-26 (B3a-B3e) | Restarting A with B already down replays the commit log; writer was unspecified |
| 6 | Cluster tolerances: T equal within 1%; control overshoot <= 8 MiB; RssAnon 128 MiB, direct pool 10 MiB | Applied 2026-10-26 (B3f) | Flush period 1 s x ~2.1 MB/s; heap noise |
| 7 | Citation fixes (five lines) | Applied 2026-10-26 (A3 note) | Accuracy |
| 8 | A3(d) compression/encryption path counts pre-compression bytes (`bytesWritten` += `hint.remaining()`): not tested here | Left for stage 3 | Default is uncompressed; `hints-CompressedHintsWriter-*` cases cover it |

### 1.2 Harness and instrument checks (not readings)

Harness folder: `../harness/max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous/` (README there). Node `pc12`, tree `~/s4-mh` (copy-source.sh from repository commit `1ae567d`, `ant build-test` BUILD SUCCESSFUL in 1 min 9 s). Written after the freeze above; the shakedowns below ran the same files and are not readings (their output was not used to change any prediction or conclusion row).

- **Unit shakedown** (`unit-run.sh ... instrument`, 2026-10-25 19:46 MDT, `~/s4-mh-logs/unit-shakedown1/`): compiled and ran on the first try, Byteman attached, 320 `roll` lines, 375 `sessclose`, 38 `decide`, no rule error. One harness defect: the excluded warm-up run also asserted the direct-memory delta, which fails by design (it allocates the slabs); the check now applies only to counted runs (harness edit only; no case-file text changed).
- **Cluster shakedown** (`cluster-run.py arm shake1 1`, `MH_ROWS=20000`, 2026-10-25 19:49-19:52 MDT, `~/s4-mh-logs/shake/shake1/`): ring up in 21 s, the node log reports `max_hints_file_size=1MiB`, the five Byteman rules listed over port 9323, B down (DN on A) in 2 s, 20,000 rows at 999.98 rows/s with 0 failures, 41 files, 40 `roll` lines, 0 ERROR lines on A, both nodes stopped (nothing from `~/s4-mh-run` left). One defect found and fixed in the harness: the writer connected to port 9042 (`write-load.py` now takes `MH_PORT`, default 9345).
- **md5 of the harness files** (12 hex): `cluster-run.py` `3921e6f1`, `HintsFileSizeLimitTest.java` `fea60a12`, `Jmx.java` `46dc9f56`, `make-node-yaml.sh` `b95f7f7c`, `mh.btm` `5ddf216a`, `unit-run.sh` `23860538`, `write-load.py` `c2cdf634` (plus `selfcheck.py`, written for the self-check).

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 19:52 to 20:25 MDT (2026-10-26 01:52 to 02:25 UTC): unit 19:52:58, cluster arms L16 19:53, L1 20:02, L128 20:10, CTRL 20:17 | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876`, 198.22.255.22), 40 cores, 251 GiB | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-mh` by `copy-source.sh` from repository commit `1ae567d` (`git describe` = `cassandra-5.0.9`); `HintsFileSizeLimitTest.java` copied into `test/unit/org/apache/cassandra/hints/` | |
| Case-file commit / harness commit | case file untracked at `1ae567d`; frozen sha256 `9f1e11e3...9828` / harness uncommitted (md5s in section 1.2) | |
| Storage for node data | local `/dev/sda3` (`~/s4-mh-run/{A,B}`, removed after the run; 43 GB free afterwards), hints dir of the unit tier `~/s4-mh/build/test/cassandra/hints` (removed) | |
| Full logs (path, outside the repo) | `pc12:~/s4-mh-logs/run1/` (`unit/`, `L1/`, `L16/`, `L128/`, `CTRL/`: `mh.trace` 30 MB each, `keys.csv`, `du.csv`, `mem.csv`, `files.txt`, node logs; `selfcheck.txt`); shakedowns `~/s4-mh-logs/unit-shakedown1/`, `~/s4-mh-logs/shake/` | |

Ports used (all free before each start, `ss -ltn`): storage 7023 and 7024, JMX 7323 and 7324, Byteman 9323, native 9345 and 9346, loopback 127.0.23.1 and 127.0.23.2. Wall-clock timing is in `timing/set-A-batch-6.log`.

## 3. Runbook defects

None in run 1: every step of the amended B2/B3 ran as written. The harness defects found in the shakedowns (warm-up asserted a direct-memory delta; the writer used port 9042) are in section 1.2; neither touches the case's claim, prediction or conclusions. Two self-check script errors (a 60 s "no growth" check applied to arms whose writer was still running, and `TotalHints == 400000` applied to the control, which stores only the permitted hints) were fixed in `selfcheck.py` after the first self-check run, and the self-check was re-run; they changed no reading.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| - | - | - | none | - | - | - |

## 4. Run 1

**Scope:** unit tier (one test class, 14 runs of 64 MiB plus the control); cluster tier, four fresh two-node rings on `pc12`: L = 16, 1, 128 MiB with no per-host cap, then L = 128 MiB with `max_hints_size_per_host` = 100 MiB, 400,000 rows x 2 KiB at 1,000 rows/s with node B down. **Command log:** `max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous/run1/unit/summary.txt`, `max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous/run1/cluster/<arm>/summary.txt` (the `EXPECTED:` lines) and `max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous/run1/selfcheck.txt`. Excerpts of every raw file the conclusion cites are under `max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous/run1/`; the full logs stay on the node.

### 4.1 Readings

**Unit tier** (`unit/harness.out`, `unit/mh.trace`; every run: 4,096 hints x 16,384 B, entry e = 16,460 B, fresh host id)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `HintsFileSizeLimitTest` (111 checks), with Byteman | 1 test, 0 failures; 111 checks, 0 mismatches | `unit/summary.txt` |
| L = 1 MiB, 3 reps | 64 files, T = 67,422,848 B; every closed file 1,053,482 B (L + 4,906); `roll` lines 64 = files >= L | `unit/harness.out` (`run name=rep* L=1`), `unit/mh.trace` |
| L = 4 MiB, 3 reps | 17 files, T = 67,420,874 B; closed 4,197,342 B (L + 3,038), last 263,402 B; `roll` 16 | same |
| L = 16 MiB, 3 reps | 5 files, T = 67,420,370 B; closed 16,789,242 B (L + 12,026), last 263,402 B; `roll` 4 | same |
| L = 128 MiB (default), 3 reps | 1 file, T = 67,420,202 B; no closed file; `roll` 0 | same |
| totals across the 12 runs | min 67,420,202, max 67,422,848 B: spread 2,646 B = 0.004% (headers of the extra files) | `unit/harness.out` |
| 1 KiB hints (65,536), L = 1 | 69 files, T = 72,026,962 B; closed files 1,049,587 B (L + 1,011); `roll` 68 | same |
| direct `MemoryUsed` before/after each counted run | 0 B in all 13 counted runs (297,709 B before the excluded warm-up, then 67,668,850 B constant) | `unit/harness.out` |
| Control: real `StorageProxy.shouldHint`, cap 16 MiB, L = 128 | 16 batches written; at the 17th check `shouldHint` = `false` with operand 16,855,082 B (77,866 B over the cap); `decide` lines: 16 `true` (operands up to 15,801,642), 21 `false` (every one with checked > 16,777,216); 20 more checks all `false`, T unchanged; allowed again at cap 0 | `unit/harness.out` (`control`), `unit/mh.trace` |

**Cluster tier** - T = `du` bytes of A's hints directory at the end (sampler = `files.txt`); `roll` = Byteman lines at HintsWriteExecutor.java:248; hints stored = `TotalHints`.

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| L = 1 MiB | L1 | files, T, roll | 807 files, T = 846,833,894 B, 806 `roll` lines = 806 files >= L; every closed file 1,050,074 B (L + 1,498), last 474,250 B; hints stored 400,000 (e = 2,117.1 B) | `cluster/L1/{summary.txt,files-excerpt.txt,mh-trace-excerpt.txt,counters.txt}` |
| L = 16 MiB | L16 | same | 51 files, T = 846,802,142 B, 50 `roll` = 50 files >= L; closed 16,777,267 B (L + 51), last 7,938,792 B | `cluster/L16/...` |
| L = 128 MiB (default) | L128 | same | 7 files, T = 846,800,294 B, 6 `roll`; closed 134,217,842 B (L + 114), last 41,493,242 B | `cluster/L128/...` |
| L = 128 MiB + `max_hints_size_per_host` 100 MiB | CTRL | files, T, decide | 1 file, T = 106,902,191 B = 100 MiB + 2,044,591 B; hints stored 50,497 of 400,000 writes (all 400,000 writes succeeded); `decide` 50,497 `true` (checked <= 104,857,600) and 349,503 `false` (checked 106,883,138 and up, limit 104,857,600); 0 `roll`; no growth over the last 60 s | `cluster/CTRL/...` |
| all three L | L1, L16, L128 | direct pool `MemoryUsed`, sampled every 5 s | maximum 93,987,778 / 93,818,154 / 93,736,665 B (spread 0.25 MB); minimum 58.6 MB in every arm | `cluster/*/mem.csv` |
| all three L | same | `RssAnon` at the end | 1,781,964,800 / 1,784,016,896 / 1,777,827,840 B (spread 6.2 MB); CTRL 1,812,430,848 B | `cluster/*/mem.csv`, `summary.txt` |
| all four | writers | rows | 400,000 ok, 0 failed, 1,000.00 rows/s, 405 s wall; ERROR lines in the node logs: 0 | `cluster/*/writer.out`, `A-warn-excerpt.txt` |

### 4.2 Conclusion and logic

1. **Validity** - the run was valid. The limit was reached on every arm: `roll` lines show the :247 comparison returned true 320 times in the unit tier and 806 / 50 / 6 times in the cluster arms **[observed: `unit/summary.txt`, `cluster/*/mh-trace-excerpt.txt`]**. The knob took effect: node A's start-up configuration line reports `max_hints_file_size=1MiB`, `16MiB`, `128MiB`, `128MiB` and the JMX read-back of `MaxHintsSizePerHostInMiB` is 0, 0, 0, 100 **[observed: `cluster/*/summary.txt` KNOB lines]**; the unit knob read-backs are checks in `harness.out`. Hold-fixed settings: same rows, rate and payload in every arm (`writer.out`), node B down for the whole run (DN on A before the first row; its own hints directory was never written, and no file was deleted: the sampler's maximum equals the final value) **[observed: `summary.txt`, `selfcheck.txt`]**, compression and encryption off (checks in `harness.out`), `auto_hints_cleanup_enabled: false` and `max_hint_window: 6h` (yaml tails). Unit control and cluster control both bound the bytes, so the instruments can see a cap.
2. **Readings** - nothing unusual: closed files overshoot L by 51 B to 12,026 B, always less than one entry; the superseded B3f figures "~55" and "~880" files were arithmetic slips (an entry is 2,117 B and T is 846.8 MB, giving 51 and 807), and the amended relation held; the control overshoot is 2.0 MiB (a flush period of hints at 2.1 MB/s), inside the 8 MiB bound.
3. **Matched row** - unit B2g row 1, "Total bytes identical across L (within 0.1%), file count scales ~1/L: Claim confirmed", with the amendments' two extra conditions: (i) `roll` count = files with length >= L in every run **[observed: `selfcheck.txt`]** and (ii) the control stops at ~16 MiB (T = 16,855,082 B) **[observed]**. Cluster B3g row 1, "Total `du` same for L = 1, 16, 128 (within a few %), file count ~ total/L": T spread 0.004%, files 807 / 51 / 7, `roll` = files >= L, direct memory flat **[observed]**; plus the control row, "total ~100 MiB + small overshoot while L = 128 runs untouched": 106.9 MB, L = 128, 0 rolls **[observed]**.
4. **Excluded rows** - "Total bytes shrinks or stops at L" and "grows with L": T equals the same value for every L (and for L = 128 the file holds all 64 MiB at once, 67.4 MB > 1 MiB) **[observed]**. "Closed file lengths < L or > L + one hint": all closed files are in [L, L + e) **[observed]**. "All L give 1 file" / "File counts equal": 64 / 17 / 5 / 1 and 807 / 51 / 7 **[observed]**. "Another cap binding" / "Total hits a ceiling at the same value": none; only the CTRL arm stops, and only with the per-host cap set **[observed]**. "Control does not bound": it bound at 16 MiB (unit) and 100 MiB (cluster) **[observed]**. "Direct memory / RSS scales with L": 0 B (unit) and 0.25 MB spread in the maximum (cluster), RssAnon spread 6 MB **[observed]**. No Refuted row applies.
5. **Observed vs. inferred** - inferred: that the periodic flush path and `flushAndFsyncBlockingly` reach the same `flushInternal` as the write path in a node (the unit tier goes through `HintsService.instance`, the cluster uses the node's own flushes; the `roll` lines in both tiers are at :248 inside `flushInternal`), and that `RssAnon` differences below 128 MiB are not informative about a per-file effect (the direct pool, the memory observable that could move, is flat).
6. **Deviations and gaps** - the unit tier drives `HintsService.instance` rather than a bare `HintsWriteExecutor` (audit amendment, B2c); the warm-up run is excluded from the memory reading by design; one repetition per cluster L (the unit tier has three); the compression and encryption path (A3(d)) is not tested; the control's cap is the per-host cap, the "known binding" condition the design names. Hints were never dispatched (B down), so a dispatch interplay is not covered.
7. **Core question** - usage did not follow the constraint. 64 MiB of hints in the unit tier and 846.8 MB in the cluster occupy the same bytes at L = 1, 4 or 16, 128 MiB; only the number of files changes (64 to 1, 807 to 7), so `max_hints_file_size` does not cap the disk used by hints (steps 1 to 3: files per L, total per L, `roll` = files >= L), and it does not move direct or resident memory (step 4). The per-host cap, by contrast, stopped the same workload at 100 MiB + 2 MiB (step 5, the positive control).

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (with the control row) - confirmed: `max_hints_file_size` is a per-file roll threshold and does not cap hints disk or memory.

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous/selfcheck.py` re-parses the raw logs (`harness.out`, `mh.trace`, `files.txt`, `du.csv`, `mem.csv`, `keys.csv`, `counters.txt`) on the node and recomputes the relations without using the run scripts' `EXPECTED:` lines: **106 ok, 0 NO** (`run1/selfcheck.txt`). Its first run flagged 4 NO, all errors of the script itself (see section 3); fixed and re-run.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster/*/summary.txt` KNOB lines (1MiB / 16MiB / 128MiB / 128MiB and cap 0 / 0 / 0 / 100); `writer.out` rows 400,000 ok; `selfcheck.txt` sampler maximum = final (nothing deleted); node ERROR lines 0; no daemon and none of the seven ports left (checked after the last arm and at the end). |
| 2. Readings | yes | Re-derived e = T / TotalHints = 2,117.0 B and the file counts from T and L; the old "~55 / ~880" are 51 / 807 by that arithmetic. |
| 3. Matched row | yes | `selfcheck.txt`: roll = files >= L in all unit runs and cluster arms; control Tstop in (cap, cap + one batch]; CTRL T in (100 MiB, 108 MiB], first-false operand 106,883,138 B > cap, no `true` after the first `false`. |
| 4. Excluded rows | yes | Closed files in [L, L + 4 KiB) in all arms; T spread 0.004%; file counts fall with L; direct max spread 0.25 MB; RssAnon spread 6.2 MB. |
| 5. Observed vs. inferred | yes | The one inference (same `flushInternal` for periodic and write-triggered flushes) is read from HintsWriteExecutor.java:217-231 and :237-257; both tiers' `roll` lines come from :248, so the branch that was exercised is the one in the claim. |
| 6. Deviations and gaps | yes | Listed in 4.2 part 6; none changes a row. |
| 7. Core question - the steps from reading to answer follow the audited logic | yes | B1 "refuted if the total moves with the knob": it did not; the control moved the total under a binding cap with the same instruments. |

### 5.2 Run 2?

**No** (2026-10-26). The conclusion rests on observed values that agree between the unit and cluster tiers and between three unit repetitions (identical file counts and sizes), the self-check recomputed them from raw files, and the result neither refutes the case nor confirms a bypass. The one inferred statement is covered by the source read. A run 2 would add no independent evidence.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 7. Comparison - only if run 2 was done

Not applicable.

## 8. Verdict - AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** changing `max_hints_file_size` changes only how many hint files the same hints are split into (each file within [limit, limit + one hint]); it does not change the total hint bytes on disk for a host, nor direct-memory use. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed - B2g row 1 (total bytes identical across L, file count scales with 1/L; roll = files >= L; control bound at 16 MiB) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed - B3g row 1 and the control row (T equal across L = 1, 16, 128; 807 / 51 / 7 files; control stopped at 100 MiB + 2 MiB with L = 128) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): unit - the real `StorageProxy.shouldHint` with `max_hints_size_per_host` = 16 MiB and the same hints stopped the host's bytes at 16,855,082 B (limit + 77,866 B) while `max_hints_file_size` was 128 MiB (`unit/harness.out`, `control` line); cluster - `max_hints_size_per_host` = 100 MiB with L = 128 MiB stopped the hints at 106,902,191 B of the 846.8 MB the same workload stores without the cap, 349,503 writes refused (`cluster/CTRL/summary.txt`, `mh-trace-excerpt.txt`).

**Feedback filed:** the case file's section D updated (run feedback and the audit amendments; case file untracked, so no commit yet); amendments in A3, B2a-B2d, B2f-B2h, B3a-B3g, B4 as dated bracketed notes. Frozen sha256 `9f1e11e39b09936b7569fa173013a891c3de2c10e3f922397cdaf8e2aa0e9828`; after the section-D feedback `df0246d33ad2245f184df32c050a686d695f6befe6f1a33c83012286906933cb`. Findings for stage 3 (not applied): A3(d) compression path untested here; the citations the write-up got wrong are noted in A3; the knob has no memory effect (confirms the Ground); `max_hints_file_size` behaves as a per-file roll-over, never a cap.

**Leftovers on `pc12`** (nothing running, no port held): tree `~/s4-mh` (471 MB, untracked test file in `test/unit/.../hints/`), `~/s4-mh-harness/`, `~/s4-mh-logs/` (162 MB: run1, shakedowns, build log, excerpts). `~/s4-mh-run` and the unit hints directory were removed.
