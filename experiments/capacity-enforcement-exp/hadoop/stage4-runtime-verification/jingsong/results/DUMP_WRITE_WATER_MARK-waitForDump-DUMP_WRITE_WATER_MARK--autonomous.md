# DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous — stage-4 results  <!-- file: results/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous.md -->

> **Case:** [`DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous.md) (Jingsong's queue order 14; check `OpenFileCtx.java:278`)
>
> **Status:** verdict filed (run 1 + self-check; no run 2) — 2026-11-25
>
> **Outcome class:** **true positive** — estimate `positive`, effect `caps` in both tiers (the dump-failure path stalls the writer instead of letting heap grow; scope caveats in §8).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is D.

Drafted outside the repository (`~/writeup-hadoop/out/o14/`); paths marked `run1/…` are relative to that folder.
Harness: `~/writeup-hadoop/out/o14/harness/`. Amended case file: `~/writeup-hadoop/out/o14/case-amended.md`.

**Node change.** An earlier attempt (2026-11-25 05:35–06:35 EST) was to run on `pc99` and was blocked by a stale node lock;
nothing ran there (its stub: `run1/results-blocked-stub-pc99.md`, `run1/lock-poll.log`). This attempt runs on **`pc82`**
(lock `/mydata/s4/NODE-LOCK` taken 2026-11-25 10:00:56 MST). The audit and harness of that attempt were reviewed and reused
with the fixes listed in §1.1 (recommendations 4 and 8).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository file at commit `bef6bc8a6` (sha256 `65bb6724…b33355d`). After the audit's seven dated amendments A1–A7 (2026-11-25): sha256 `dcbc9aa5…ed32e3` (frozen 12:04:04 EST = 10:04:04 MST, before any run). After the A2 correction of runbook defect 1 (no reading existed): sha256 **`cf7d8ac5d1c7981d6f985a06bbd19827c9c248210e5d8b5e4cb8d71ac9ba25aa`** (re-frozen 12:05:52 EST = 10:05:52 MST; the unit run that produced readings started 10:05:59 MST). Frozen tables, identical in all three versions (repository, A1–A7, A1–A7 + correction): B2f `d25ce0b3…1bb473`, B2g `33590dd2…cecddf`, B3f `c0064821…45929b`, B3g `3937d1da…cce47` (`run1/frozen-sha256.txt`). Section D feedback was added after the run and is not part of the frozen version. |
| **Harness** | `harness/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous/`: `TestDumpWaterMark.java`, `unit-run.sh`, `check-unit.py`, `cluster-run.sh`, `ooo_write.py`, `analyze.py` (staged at `~/writeup-hadoop/out/o14/harness/`; not committed: no commit asked for) |
| **Tiers and values** | Unit: W = 256 KiB, 1 MiB (stock), 4 MiB by reflection; controls `dumpDisabled`, `dumpDirMissing`; optional `concurrent4`. Cluster: arms A (1 MiB stock, 1,500 writes), B (64 MiB jar, 1,500), A′ (1 MiB, `-Xmx384m`, 8,192), C (`Long.MAX_VALUE` jar, `-Xmx384m`, 8,192), D (stock, `nfs.file.dump=false`, 64) |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: gateway heap held by one open file's out-of-order WRITE payloads (`nonSequentialWriteInMemory`, bytes) |
| A | knob varied, ≥ 3 values incl. default — or another approach | Met | hard-coded constant (A1): B2b 256 KiB / 1 MiB / 4 MiB by reflection (field not `final`); B3b 1 MiB / 64 MiB / `Long.MAX_VALUE` by patched jar |
| A | real resource measured, not only the counter | Met (unit Partly) | B3d: live `[B` from `GC.class_histogram` (forced full GC) and the dump-dir size; unit B2d measures the counter and the `ALLOW_DUMP` sum (gap named: "JVM heap not observed"); amendment A2 adds the referenced payload bytes `HB` |
| A | usage driven to the limit and past it | Met | B2c 16,384,000 B = 15.6 × stock mark (62/15/3 crossings); B3c 93.75 MiB and 512 MiB out of order |
| B | each step says what it establishes | Met | B2g/B3g rows; B2h/B3h controls |
| B | prediction in numbers | Met | B2f and B3f give exact counter, peak, dump bytes and rounds per case/arm |
| B | every plausible outcome has a row | Met | over-limit, same-for-all-W, accounting mismatch, partial spill, control flat, failure-path bypass, no out-of-order WRITEs, no dumping |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Met | three W values; the disallow effect is the held WRITE plus the dump file growing in rounds |
| B | alternative explanations and controls | Met | `dumpDisabled` / arm C positive controls; arm B (bound moves with W, not heap or `nfs.wtmax`); `javap` + log peak for the knob |
| C | a human can follow it | Met | estimate, B1, B2f/B3f |
| C | an AI can run it without re-deriving the path | Partly | B2e "interrupt" cannot free the writer (A3); B3c hold exceeds `nfs.stream.timeout` (A5); B3a build/jar check do not fit the nodes (A4) |
| C | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | no client time limit for arms A–C (A5); HDFS-length moment ambiguous (A6) |
| D | harness and environment prerequisites | Partly | harness listed as work (done in step 1); environment differences (A1, A4, A7) |
| D | workload arithmetic reaches the limit | Met | unit 16 MB payload in a 1 GiB surefire heap; cluster ≤ 512 MiB in the dump dir and in HDFS, `/mydata` has 658 GB free; gateway heap 384–512 MiB |
| D | load-bearing citations spot-checked | Met | `OpenFileCtx.java:73` (declaration), `:179/:248` (counter, not final), `:211-220` (update + DEBUG line), `:251` (`enabledDump`), `:272-302` (`waitForDump`; interrupt swallowed at `:297`), `:306-373` (dump; "Create dump file" `:309`, failure `:318-330`), `:376-406` (Dumper), `:190-192`, `:939-956` + `OpenFileCtxCache.java:148-183` (stream timeout), `:1218-1273` (cleanup); `FSDirStatAndListingOp.java:449-451` (length of a file under construction) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: `copy-source.sh`, no `-am install`, `mvn -o test` with the surefire argLine property | Applied, A1 (2026-11-25) | environment.md §2–3, case-notes lesson 1; no change to B2f/B2g |
| 2 | B2d: add referenced payload bytes `HB`, an instrumented peak counter and the saved log capture | Applied, A2 | gives a direct reading for the named "real heap" gap; instruments only |
| 3 | B2e `dumpDirMissing`: free the writer by counter = 0 + `notifyAll()` under the context lock (interrupt is swallowed, `:294-299`) | Applied, A3 | runbook step not executable as written; done after the readings, no prediction change |
| 4 | B3a: dist copy instead of a full build; jars built offline in the one copy; `javap -constants` + `grep -B1 putstatic` (the earlier harness's `grep 'static {}' \| ldc` would have printed the logger's class literal) | Applied, A4 | environment; jar-check fix found in this review |
| 5 | B3c: hold 40 s (< `nfs.stream.timeout` 60 s) in every arm; client time limits per arm | Applied, A5 | the monitor would close the idle context and fail pending writes during a 60–120 s hold |
| 6 | B3d: read the `(N+1) × C` HDFS length after the stream is closed | Applied, A6 | NameNode excludes the last under-construction block while the gateway keeps the stream open |
| 7 | B3e step 2: try the system `rpcbind` first, fall back to the Hadoop portmap as written | Applied, A7 | `pc82` runs `rpcbind`; order 15 on `pc72` registered with it |
| 8 | Harness review: hold-time log copy restricted to the current arm (`tail -n +l0`), histogram top + `WriteCtx` count kept per reading, `HDFS_PORTMAP_USER=root` in the fallback, teardown on any exit | Applied (harness only) | evidence quality and cleanup; not a design change |
| 9 | Stage 3: B2f `concurrent4` "M < 1 MiB when each WRITE returns" cannot be read race-free with 4 threads (another thread can add before the read); only the peak bound has a B2g row | Left for stage 3 | wording only |
| 10 | Stage 3: name the "Before dump == / After dump ==" DEBUG lines (`OpenFileCtx.java:345`, `:371`) as the per-round evidence in B3d | Left for stage 3 | used here as extra evidence |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (node clock MST; session clock EST) |
| Node | `pc82` (`node1.jason92-326665`, CloudLab UMass, 40 cores, 125 GiB RAM) |
| OS / kernel | Ubuntu 22.04.2 LTS / `5.15.0-203-generic` |
| JDK | OpenJDK 1.8.0_514 (`/usr/lib/jvm/java-8-openjdk-amd64`); Maven 3.6.3 |
| Local source copy | `copy-source.sh` from `systems/hadoop/source/` at repository commit `8bd1dfb3` → `/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-run1/src` (`rel/release-3.4.2`) |
| Distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (node build of 2026-11-24) |
| Case-file commit / harness | `bef6bc8a6` + amendments A1–A7 (sha256 above) / not committed |
| Storage | `/mydata` local LVM (753 GB, 658 GB free); dump dir, NN/DN data under the run folder |
| Node state before the run | `rpcbind` and `rpcbind.socket` active (portmapper on 111 only), `nfs-server` inactive, no Hadoop or user Java process, no NFS mount other than `/proj` and `/share` |

| Portmapper | system `rpcbind`; the gateway (as `jason92`) registered `mountd` and `nfs` with it in every arm, the Hadoop-portmap fallback was not used (`run1/cluster/cluster-run.log`: 0 "falling back" lines) and the registrations were gone after the gateway stopped |
| Full logs | node: `/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-run1/logs/` (large files gzipped); local excerpts: `~/writeup-hadoop/out/o14/run1/` |
| Timing | unit 10:05:59–10:06:33 MST; cluster driver 10:06:50–10:21:24 MST (jars, setup, arms A 10:07, B 10:10, A′ 10:12, C 10:15, D 10:18, teardown 10:20) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Commit |
|---|---|---|---|---|---|---|
| 0 | audit | B2a, B2e, B3a, B3c, B3d, B3e | see §1.1 recommendations 1–7 | amendments A1–A7 | 2026-11-25, before run 1 | not committed |
| 1 | run 1 (unit, first attempt 10:05:18 MST) | B2d instrument (amendment A2) | the `AtomicLong` subclass overriding `addAndGet` does not compile (`final` on JDK 8); `testCompile` failed, no test ran, no reading existed (`run1/unit/unit-run-attempt1-compilefail.log`, `mvn-unit-attempt1.log`) | instrument removed; peak from the DEBUG log as in B2d; dated correction under A2; unit tier restarted from its beginning | 2026-11-25 10:06 MST | not committed |
| 2 | run 1 (cluster, arm D teardown) | harness `stop_gateway` | `mountpoint -q` failed on the soft mount while the gateway had a WRITE stuck, so the mount was not unmounted and the teardown printed "mount gone" although `localhost:/` was still mounted | found by the post-run check; `sudo umount -f -l` + `rmdir` by hand at 10:22 MST; no reading affected (arm D's readings were all taken before) | 2026-11-25 | harness note only |

## 4. Run 1

**Scope:** both tiers, all values and arms (A, B, A′, C, D). **Command logs:** `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`
(= `cluster-driver.out`).

### 4.1 Readings

**Unit tier** (`mvn -B -o test -Dtest=TestDumpWaterMark`: Tests run 6, Failures 0, Errors 0 — `run1/unit/surefire/org.apache.hadoop.hdfs.nfs.nfs3.TestDumpWaterMark.txt`; per-row check `run1/unit/check-unit.txt`; 1,015 `ROW` lines in `run1/unit/readings.csv`)

| Test or assertion | Result | Evidence |
|---|---|---|
| wm256k: M = (i mod 4)·C, D = (i − i mod 4)·C, `ALLOW_DUMP` sum = HB = M, `DUMPED` = D/C, M + D = i·C for all 250 rows | 0 mismatches; max M after return 196,608 < 262,144; dump steps {262,144}; final M 131,072, D 16,252,928; log peak 262,144; 62 rounds; 1 "Create dump file" | `check-unit.txt`, `readings.csv` `SUMMARY,wm256k` |
| wm1m (stock): same with m = 16 | 0 mismatches; max 983,040; steps {1,048,576}; final M 655,360, D 15,728,640; peak 1,048,576; 15 rounds; 1 create | same, `SUMMARY,wm1m` |
| wm4m: same with m = 64 | 0 mismatches; max 4,128,768; steps {4,194,304}; final M 3,801,088, D 12,582,912; peak 4,194,304; 3 rounds; 1 create | same, `SUMMARY,wm4m` |
| dumper's own lines per round | "Before dump == W" 62/15/3 times, "After dump == 0" 62/15/3 times, "Asking dumper" 62/15/3 | `run1/unit/wm*-openfilectx.log` |
| dump file removed by `cleanup()` | yes in all three | `CLEANUP` rows |
| dumpDisabled (null path, W = 1 MiB) | M = i·C every row, final 16,384,000 = HB; no dump file; 0 create lines | `SUMMARY,dumpDisabled` |
| dumpDirMissing (W = 1 MiB) | writes 1–15 return (M ≤ 983,040, D = 0); **write 16 does not return in 10 s**: M = 1,048,576, HB = 1,048,576, no dump file; thread `WAITING` in `Object.wait` ← `OpenFileCtx.waitForDump(OpenFileCtx.java:296)` ← `receivedNewWriteInternal(:659)`; "Create dump file: …/no-such-dir/1" then "Got failure when creating dump stream" | `BLOCKED`, `BLOCKSTACK`, `SUMMARY,dumpDirMissing` rows; `dumpDirMissing-openfilectx.log` |
| concurrent4 (optional, 4 writers, W = 1 MiB) | all 250 writes return; log peak **1,245,184** (= W + 3·C, the predicted bound, not above it); final M 0, D 16,384,000 | `SUMMARY,concurrent4`; `concurrent4-openfilectx.log` ("Before dump" 1,048,576 ×3, 1,179,648 ×10, 1,245,184 ×1) |

**Cluster tier** (one file per arm; O_DIRECT 64 KiB `pwrite`s at offsets N·C down to C, hold 40 s, then offset 0; `run1/cluster/analyze.txt`, per-arm folders `run1/cluster/arm-*/`)

| Value | Arm | Observable | Reading | B3f prediction | Evidence |
|---|---|---|---|---|---|
| all | — | jar constant (`javap`, `putstatic` operand) | stock/A/A′/D `1048576`, B `67108864`, C `9223372036854775807` | as designed | `arm-*/jar-const.txt`, `javap-*.txt` |
| all | — | WRITE order and type | A, B: 1,501 requests, offsets 98,304,000 … 65,536 then 0; A′: 8,193, offsets 536,870,912 … 0; every out-of-order request a positive "Update … by 65536" | out of order, one WRITE per `pwrite` | `arm-*/log-stats.txt` |
| 1 MiB | A | counter at hold / log peak | **786,432** / **1,048,576** | 786,432 / 1,048,576 | `arm-A/counter-at-hold.txt`, `log-stats.txt` |
| 1 MiB | A | dump rounds | 93 ("Before dump == 1,048,576" ×93, "After dump == 0" ×93) | 93 | `arm-A/log-stats.txt` |
| 1 MiB | A | dump dir at hold | 97,521,664 B = 97,517,568 (one file) + 4,096 (directory) | 97,517,568 B | `arm-A/dump-hold.txt` |
| 1 MiB | A | Δ live `[B` (H1 − H0) | **−2,577,800 B** (H0 20,499,952 → H1 17,922,152); `WriteCtx` instances 1,500 | ≈ 0.75 MiB, "allow a few MiB of noise" | `arm-A/H0.txt`, `H1.txt`, `histo-H1.txt` |
| 64 MiB | B | counter at hold / log peak | **31,195,136** / **67,108,864** | 31,195,136 / 67,108,864 | `arm-B/counter-at-hold.txt`, `log-stats.txt` |
| 64 MiB | B | dump rounds / dump dir at hold | 1 / 67,112,960 B = 67,108,864 + 4,096 | 1 / 67,108,864 B | `arm-B/log-stats.txt`, `dump-hold.txt` |
| 64 MiB | B | Δ live `[B` | **+27,822,400 B** (20,528,816 → 48,351,216) | ≈ 29.75 MiB (31,195,136 B) | `arm-B/H0.txt`, `H1.txt` |
| — | B − A | Δ difference | **30,400,200 B** | B − A ≈ 29 MiB (31,195,136 − 786,432 = 30,408,704 B) | computed from the four H files |
| 1 MiB, 384 MiB heap | A′ | counter at hold / peak / rounds | **0** / 1,048,576 / 512 | 0 / 1,048,576 / — | `arm-Aprime/counter-at-hold.txt`, `log-stats.txt` |
| 1 MiB, 384 MiB heap | A′ | dump dir at hold | 536,875,008 B = 536,870,912 + 4,096 | 536,870,912 B | `arm-Aprime/dump-hold.txt` |
| 1 MiB, 384 MiB heap | A′ | Δ live `[B` | −587,624 B | ≈ 0 | `arm-Aprime/H0.txt`, `H1.txt` |
| 1 MiB, 384 MiB heap | A′ | old gen `OU` | 28,583–29,588 KB for all 8,192 writes and the hold (jstat samples 1–~70); rises to 113,272 KB only after `DONE` (write-back reading the 512 MiB back) | flat | `arm-Aprime/jstat.txt`, `client.txt` (DONE at 70.2 s) |
| 1 MiB, 384 MiB heap | A′ | OOM / client | 0 / all 8,193 writes succeed | no OOM | `arm-Aprime/oom-count.txt`, `client.txt` |
| ∞, 384 MiB heap | C | counter | 4,341 positive updates, 0 negative, last value **284,491,776** (= 4,341 × C); 0 "Create dump file" | grows by C per WRITE | `arm-C/log-stats.txt` |
| ∞, 384 MiB heap | C | heap | `OU` 28,508 KB → 262,142 KB (old gen full) within ~25 s; `OutOfMemoryError: Java heap space` at 17:15:37 UTC in `XDR.readFixedOpaque` ← `WRITE3Request.deserialize` ← `RpcProgramNfs3.write`, then "GC overhead limit exceeded" | toward the heap limit; OOM or GC thrash before ~6,000 WRITEs | `arm-C/jstat.txt`, `oom-excerpt.txt`, `oom-count.txt` (4 in the log, 2 in `.out`) |
| ∞, 384 MiB heap | C | client / dump dir | `pwrite` → `EIO` (soft-mount timeout) after write 4,341, no `HOLD`; dump dir empty (4,096) | WRITEs fail or time out; 0 B | `arm-C/client.txt`, `dump-after.txt` |
| 1 MiB, `nfs.file.dump=false` | D | counter / dump | 16 positive updates, peak **1,048,576**, "Asking dumper" 1, "Create dump file: null/16391", "Got failure when creating dump stream null/16391"; gateway cwd `$RUN` (no `null/` there) | stuck at 1,048,576; creation fails | `arm-D/nfs3-excerpt.txt`, `cluster-run.log` (`readlink`) |
| 1 MiB, `nfs.file.dump=false` | D | client | 15 WRITEs answered (15 "change stable write" replies, 15 COMMIT_SPECIAL_SUCCESS); the 16th (offset 3,211,264 = 49·C) never answered; `pwrite` → `EIO` (timeo=100, retrans=2); 16 `WriteCtx` held at the end | the 16th `pwrite` does not complete (soft-mount timeout / EIO) | `arm-D/client.txt`, `log-stats.txt`, `histo-H1-end.txt` |
| — | A, B, A′ | dump dir after `nfs.stream.timeout` + 10 s | 4,096 (empty) in all three | gone | `arm-*/dump-after-timeout.txt` |
| — | A, B, A′ | HDFS length (A6: after the stream closed) | 98,369,536 = 1,501·C; 98,369,536; 536,936,448 = 8,193·C (right after `DONE`: 65,536 / 65,536 / 536,870,912) | (N+1)·C | `arm-*/hdfs-stat.txt` |
| — | A, B, A′ | OOM | 0 | 0 | `arm-*/oom-count.txt` |

### 4.2 Conclusion and logic

1. **Validity.** The mark was crossed in every capped case: unit 62/15/3 rounds, cluster 93 (A), 1 (B), 512 (A′) rounds
   [observed: `check-unit.txt`, `arm-*/log-stats.txt`]. Knob reached the code: unit `KNOB` lines and peak = W; cluster `javap`
   operand per arm and log peak = W [observed: `readings.csv`, `jar-const.txt`]. Hold-fixed settings: `nfs.dump.dir` on
   `/mydata`, `nfs.stream.timeout=60000`, `nfs.wtmax=1048576`, `nfs.file.dump=true` (false only in D) [observed: `cluster-run.log`
   hdfs-site dumps]; request size 65,536 and the descending order [observed: `log-stats.txt`]; dump dir empty at each arm's start
   [observed: `dump-start.txt`]; gateway heap per arm [observed: `cluster-run.log` "cmdline Xmx"]. The hold (40 s) kept the
   context alive: no "stream can be closed" or "Fail pending write" in A/B/A′ before `DONE`, and the hole-filling WRITE succeeded
   (HDFS length (N+1)·C) [observed: `hdfs-stat.txt`]. Valid.
2. **Readings.** The `[B` deltas of A and B are both about 3.37 MB below the counter (A −3,364,232 B, B −3,372,736 B): the H0
   baseline of each fresh gateway carries ~3.4 MB of `[B` that is gone by H1 (H0 `[B` 20.5 MB in the 512 MiB arms vs 17.9 MB at
   A's H1 with 1,500 `WriteCtx` held) [observed: `histo-H0.txt`/`histo-H1.txt`]; the difference B − A (30,400,200 B) cancels it
   and matches the predicted 30,408,704 B to 8.5 KB [inferred: same offset in two arms]. The A′ old-gen jump after `DONE` is the
   write-back reading dumped data back (`WriteCtx.loadData`), after the measured window [inferred: timing, `client.txt` DONE at
   70.2 s vs the `jstat` step at ~70 s]. In C the heap dropped back to 27 MB at ~17:16:5x UTC, after "stream can be closed" at
   17:16:37 (the idle context removed by the monitor) [observed: `oom-excerpt.txt`, `jstat.txt`].
3. **Matched rows.**
   - Unit B2g row 1, "M < W after every WRITE, peak = W, final M and D as in the table, for all three W → Claim confirmed": max M
     after return < W, peak = W, final M/D exactly B2f, 0 mismatches over 750 rows, for 256 KiB, 1 MiB, 4 MiB [observed:
     `check-unit.txt`]. Control rows: "`dumpDisabled` M grows to 16,384,000 → expected control" [observed: `SUMMARY,dumpDisabled`];
     "`dumpDirMissing` WRITE 16 blocks, thread WAITING in `waitForDump` → A3 failure-path trace confirmed" [observed: `BLOCKED`,
     `BLOCKSTACK`].
   - Cluster B3g row 1, "A: log peak = 1,048,576, counter at hold 786,432, Δ ≈ 0.75 MiB, dump ≈ 97.5 MB; B: peak 67,108,864,
     Δ ≈ 29.75 MiB → Claim confirmed in the real daemon": peaks and counters exact, dump 97,517,568 B, Δ_A −2.46 MiB and
     Δ_B +26.53 MiB, each within B3f's "a few MiB of noise" (3.2 MiB from the point value, the same offset in both) and B − A =
     28.99 MiB as B3f states [observed: §4.1]. B3g row 2, "A′ survives with flat old gen while C runs out of heap on the same
     workload → the constant is what keeps actual gateway heap from following the out-of-order volume": A′ 0 OOM, `OU` flat during
     writes and hold, 512 MiB spilled; C old gen full and `OutOfMemoryError` after 4,341 writes (271 MiB buffered) [observed:
     `arm-Aprime/*`, `arm-C/*`]. B3g row 8 second part, "D: the 16th write hangs → A3's failure-path trace confirmed" [observed:
     `arm-D/*`].
4. **Excluded rows.** Unit: "M ≥ W after a WRITE has returned, or peak > W + C − 1" — max after return 0.94·W at most, peak = W;
   "same for all W" — 196,608 / 983,040 / 4,128,768 differ; "M + D ≠ i·C or M ≠ `ALLOW_DUMP` sum" — 0 mismatches; "partial
   spill" — every "After dump" = 0 in single-writer cases; "`dumpDisabled` M stays < 1 MiB" — no; "`dumpDirMissing` WRITE 16
   returns and M keeps growing" — no, blocked; "concurrent4 peak > 1,245,184" — peak = 1,245,184 [observed: `check-unit.txt`,
   `readings.csv`, `*-openfilectx.log`]. Cluster: "A: Δ well above ~4 MiB, or counter > 1,048,576 + 65,536" — Δ negative, peak
   1,048,576; "A and B give the same Δ and counter" — 30.4 MB apart; "C does not grow and does not OOM" — grew and OOM'd; "no
   positive Update lines" — 1,500/1,500/8,192/4,341/16; "dump dir 0 in A/A′" — 97.5 MB / 536.9 MB; "D: writes keep succeeding
   and counter grows past 1 MiB" — no, the 16th hangs [observed: `arm-*/log-stats.txt`, `dump-hold.txt`, `client.txt`].
5. **Observed vs. inferred.** The conclusion rests on observed values. Inferred: (a) the ~3.37 MB baseline offset in A/B is noise
   of the first histogram after gateway start, not payload — supported by the equal offset in two arms, by A′'s −0.59 MB, and by
   B − A matching to 8.5 KB; (b) in the cluster the held WRITE is held at `:294-299` — supported by "Asking dumper" (true branch
   of `:284`) once per round and by the unit stack trace at `OpenFileCtx.java:296`.
6. **Deviations and gaps.** Amendments A1–A7 and the A2 correction (environment, instruments, hold 40 s, stop conditions). The
   momentary per-WRITE heap peak is only seen through the log counter. Arm C has no hold reading (the client never reached
   `HOLD`), as B3f allows. The A′ "flat old gen" reading is bounded to the out-of-order phase; after `DONE` old gen rises with
   the write-back (not part of the claim). The unit `concurrent4` after-return value (1,048,576) is a racy read (recommendation 9)
   and is not used. Arm D's leftover mount (defect 2) was removed after its readings.
7. **Core question.** Yes. The heap held by one file's out-of-order WRITEs rises to the mark and is spilled at each crossing, so
   after each WRITE it stays below the mark (parts 3, 4); the bound moves with the constant (256 KiB → 4 MiB in the unit tier;
   1 MiB → 64 MiB in the gateway, B − A = 29 MiB of real `[B`), and with the cap removed the same workload fills the heap and
   OOMs the gateway while the stock mark keeps it flat (part 3, B3g row 2). The excess goes to the dump file, which nothing caps
   (512 MiB for one file in A′).

**Conclusion:** unit B2g row 1 (with both control rows as predicted) — **confirmed**; cluster B3g rows 1 and 2 (and arm D's
failure-path row) — **confirmed**.

## 5. Self-check of run 1 — AI

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | re-read `jar-const.txt` ×5, `javap-*.txt`, the hdfs-site block and "cmdline Xmx" lines in `cluster-run.log`, `dump-start.txt` ×5, `hdfs-stat.txt` ×3 |
| 2. Readings | yes | re-read `H0.txt`/`H1.txt` ×5 and recomputed the offsets (−3,364,232 / −3,372,736) and B − A (30,400,200 vs 30,408,704); `histo-H1.txt` (A: 1,500 `WriteCtx`); `jstat.txt` A′/C column `OU` |
| 3. Matched row | yes | re-ran `check-unit.py` on `readings.csv` (identical output to `check-unit.txt`); `counter-at-hold.txt` A/B/A′ last lines 786,432 / 31,195,136 / 0; `log-stats.txt` round counts 93/1/512 |
| 4. Excluded rows | yes | each B2g/B3g row checked against `SUMMARY` rows and `log-stats.txt`; concurrent4 peak equals, not exceeds, the bound |
| 5. Observed vs. inferred | yes | (a) A′ offset −0.59 MB and equal A/B offsets re-read from the H files; (b) `BLOCKSTACK` line shows `waitForDump(OpenFileCtx.java:296)` |
| 6. Deviations and gaps | yes | amendments dated before readings: `frozen-sha256.txt` re-freeze 12:05:52 EST = 10:05:52 MST, unit run with readings started 10:05:59 MST (`unit-run.log`); first attempt failed at `testCompile` (no `ROW` line in `mvn-unit-attempt1.log`) |
| 7. Core question | yes | hypothesis (B1) → dose (W) → ceiling + spill → positive controls (`dumpDisabled`, C) → failure path (dumpDirMissing, D) follows the audited logic |

The one judgement call: B3g row 1 names point values (Δ ≈ 0.75 MiB / ≈ 29.75 MiB) while B3f allows "a few MiB of noise"; the
readings are 3.2 MiB off each point value in the same direction and the refuting row needs "well above ~4 MiB". Read strictly
(no noise allowance), row 1 would be unmatched and the cluster tier Not confirmed; with the frozen allowance and the B − A check
that B3f itself names, it is matched. Kept as Confirmed, noted for Jingsong.

### 5.2 Run 2?

**No** — 2026-11-25. Every load-bearing statement is observed, counters and dump sizes match B2f/B3f to the byte, and the result
confirms the claim rather than refuting it or adding a bypass row.

## 6. Run 2 — not done

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps; both tiers).

**Claim tested (B1):** with dumping enabled, after any out-of-order WRITE to one open file is acknowledged, the NFS gateway holds
less than `DUMP_WRITE_WATER_MARK` bytes of that file's out-of-order data in heap (momentarily at most `mark − 1 + count`), the
rest being in the dump file; changing the constant moves this bound with it.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1; controls `dumpDisabled` (grows to 16,384,000) and `dumpDirMissing` (write 16 held in `waitForDump`) as predicted; `concurrent4` peak = W + 3·C | caps | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1 (A/B, Δ within the frozen noise allowance, B − A = 28.99 MiB) and row 2 (A′ flat, C `OutOfMemoryError`); arm D: 16th WRITE hangs | caps | run 1 + self-check | 2026-11-25 |

**Scope of the cap (from the readings, for the OOM work):** per open file only (the gateway-wide in-heap total can reach about
`nfs.max.open.files` (256) × (mark + overshoot)); one extra WRITE per concurrent writer (`concurrent4` peak W + 3·C); the dump
file has no cap (512 MiB for one file in A′, deleted only at stream close); a dump-file creation failure (missing dir, or
`nfs.file.dump=false`, which still builds the CREATE path `null/<fileId>`) turns the throttle into a permanent stall of that
WRITE — heap does not grow, but the client gets `EIO` on a soft mount (and would hang on a hard one). With the cap removed
(arm C) the gateway OOMs at ~271 MiB buffered in a 384 MiB heap in `WRITE3Request.deserialize`, keeps running, and loses the
file's data.

**Feedback filed:** section D of the amended case file (`~/writeup-hadoop/out/o14/case-amended.md`); not written to the
repository (task rule).

## Left on the node (`pc82`)

- `/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-run1/` (5.1 MB): `logs/` (unit and cluster logs,
  large files gzipped), `harness/`, `conf/`, `jars/` (stock, 64 MiB, ∞ `hadoop-hdfs-nfs` jars, 352 KB). Deleted: `hadoop/`
  (distribution copy), `src/` (source copy), `nn/`, `dn/`, `dump/`, `tmp/`, `pids/`.
- No process of this run (no Java, `jstat`, Python or driver), no mount (`/mnt/hdfs-nfs-jason92` removed), `rpcbind` and
  `rpcbind.socket` active with only the portmapper registered (as before the run); `/mydata/s4/DRIVER-jingsong-h14.pid` removed;
  node lock released at the end.
