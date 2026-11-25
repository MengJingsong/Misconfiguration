# DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous — stage-4 results  <!-- file: results/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous.md -->

> **Case:** [`DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous.md) (queue order 16)
>
> **Status:** **verdict filed 2026-11-25** — unit **Confirmed** (caps only on some paths (bypass): the U7 dump-failure bypass was observed), cluster **Confirmed** (caps, per open file). Claim tested (B1): for one open file on the NFS gateway, heap bytes held by out-of-order WRITE data never exceed `DUMP_WRITE_WATER_MARK` plus one request; the excess goes to `nfs.dump.dir/<fileId>`. The counter peaked exactly at the mark at every mark value (unit 256 KiB–16 MiB; daemon 1 MiB, and 64 MiB in a patched jar), each dump round drained it to 0 and the dump file took the rest; 768 MiB of out-of-order data went through a 256 MiB gateway with live `byte[]` flat within 1.4 MB, while 32 open files held +30.4 MiB and the 64 MiB patched mark held +64.4 MiB. One run 1, no run 2.
>
> **Outcome class:** **true positive** — stage-3 estimate `positive` against the stage-4 effect `caps` (both tiers; the unit tier's recorded bypass counts as `caps`) ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Hadoop, Jingsong's share. Written at run time **outside the repository** (the run was told not to edit the
repo): this file is `~/writeup-hadoop/out/o16/results.md`, the amended case file `~/writeup-hadoop/out/o16/case-amended.md`,
the harness `~/writeup-hadoop/out/o16/harness/`, the run logs `~/writeup-hadoop/out/o16/run1/`. When filed, they belong in
`hadoop/stage4-runtime-verification/jingsong/results/` and `../harness/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous/`;
the protocol is [`../../../../stage4-runtime-verification/README.md`](../../../../stage4-runtime-verification/README.md#the-run-protocol);
the node is described in [`../environment.md`](../environment.md).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file at repository commit `bef6bc8a6` (HEAD `cd9e1cded`); sha256 at filing `5111c98e846261dd2b5e43518bcb0320d0e4847749bf1b793b7adaac20a359c4` (checked against `_INDEX.md` §4 before the audit). After the audit's amendments A1–A8 (section D1), 2026-11-25 04:05:00 MST (06:05 EST), before any harness run or reading: whole-file sha256 **`db33a5d809589a61ffde0f2bc1778c61f39eabdb325c8b17fee93723b6860690`** (frozen version, `run1/frozen.txt`). Frozen text hashes (sha256): `**B1.` up to `**B2a.` `8bf2ce786384d4008049aca829e1bbc863e22973cbbb4a110ffca16ab388a25c`; `**B2f.` up to `**B2h.` (B2f + B2g with A7) `cd4a833621bebe10b3f304bdf80feb5130ae233f7366e52844358caebf67f03a`; `**B3f.` up to `**B3h.` (B3f + B3g with A8) `5d7ef2c27ae3a5ad092f755c60f3da33e4fb66ff580d7935d7d057048bff0d72`. |
| **After the run** | A9 (runbook defect, side observable only, in B3e step 7) and section D2 added after run 1: whole-file sha256 `55bfc210fad3b339857d7b349920090ad96e49ed6192a59d41c16b9f550678ce`; the three text hashes above re-computed and unchanged. |
| **Harness** | `harness/`: `TestDumpWaterMark.java` (the B2a class verbatim, extracted from the frozen file), `unit-run.sh`, `ooo_write.py` (the B3a driver verbatim), `NoRegNfs3.java` (A4 launcher; compiled, not needed in the end), `cluster-run.sh` (setup, jars, C1–C5, teardown), `cluster-run2.sh` (= `cluster-run.sh` plus C2b, written after C2, see §3), `analyze.py` (counter readings from the gateway log). Instrument checks: `unit-run.sh --compile-only` BUILD SUCCESS 04:05 (`run1/unit/unit-run.log`); jar constants by `javap`: `nfs-m1.jar` `ldc2_w … long 1048576l`, `nfs-m64.jar` `… long 67108864l` (`run1/cluster/cluster-run.log`, and `obs/<run>/jar-const.txt` per run); C3 (the smallest run) first, as an end-to-end check of gateway, mount, samplers and driver. |
| **Tiers and values** | Unit (B2): M ∈ {262,144; 1,048,576 (default); 4,194,304; 16,777,216; 134,217,728 (never binds)}, plus U6 (null dump path) and U7 (dump file cannot be created), 1,024 × 64 KiB out-of-order writes each. Cluster (B3): C1 (1 file, 12,288 × 64 KiB, 256 MiB heap), C2 (32 files × 256 × 64 KiB, 512 MiB), C3 (1 file, 16 × 64 KiB), C4 (1 file, 768 × 1 MiB, wsize 1 MiB), C5 (patched mark 64 MiB, as C1 in 512 MiB; run per A5). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: JVM heap held by `ALLOW_DUMP` write payloads per `OpenFileCtx`; the check's operand `nonSequentialWriteInMemory` is named, and the disk the excess goes to (`nfs.dump.dir`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly → Met | A1: a non-final static with no key. Unit varies it by reflection over 5 values incl. the default (B2b). Cluster varied only workload, request size and file count; C5 (the mark itself) was optional. **Amended** (A5: C5 is run). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d: `maxInHeap` from `WriteCtx` states and `heapDelta`; B3d: live `byte[]` from `GC.class_histogram`, `jstat`, completion in a heap smaller than the workload; gaps named (sampler misses peaks, no file id in DEBUG lines). |
| A. Core question | usage driven to the limit and past it | Met | B2c 64 MiB = 4–256 × M; B3c C1 768 MiB = 767 rounds through a 256 MiB heap. |
| A. Core question | positive control (negative estimate) | Met (not required) | Positive estimate; controls anyway: U5/U6 (cap out of play), C2 (instrument resolves 1 MiB per file), C5. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f and B3f give exact counters, rounds, dump lengths and heap bands. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g/B3g rows had meanings but no verdict labels, and no "limit never reached" row for the unit tier. **Amended** (A7, A8). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Ceiling: counter peaks at M for each M (unit) and at 1 MiB / 64 MiB (cluster). Disallow evidence: dump rounds (counter drained), dump file length, DEBUG `Asking dumper to dump...`, `Start dump`. |
| B. Logic | alternative explanations and their controls | Met | U2 vs U5 differ only in M; C3 vs C1 differ only in size; C2 for the heap instrument; the sequential-write baseline (optional, not run). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A3 steps 1–5, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | B2a/B3a paths (`~/hadoop-3.4.2`) and `start-dfs.sh` do not work on the node; `-D` on the Maven line does not reach the surefire JVM in this build. **Amended** (A1, A2). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | `nfs.stream.timeout = 60000` equals the driver's 60 s PAUSE and the stream monitor does not check pending writes: the stream could be closed mid-pause. **Amended** (A3: 180 s, wait 200 s). Portmap choice on a node with a system rpcbind. **Amended** (A4). Per-run heap baseline added (A6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Test class, driver and launcher are step-1 work; JDK 8, Maven 3.6.3, `~/.m2` 3.4.2, the built distribution, `mount.nfs`, `rpcinfo`, passwordless `sudo` present on `pc91` (checked 04:01). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≤ 0.8 GiB dump + 0.8 GiB HDFS per run against 702 GB free; gateway ≤ 512 MiB, NN/DN 1 GiB, surefire 2 GiB against 125 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source/` (clean): `OpenFileCtx.java:73` (constant), `:178-179`, `:211-218` (counter and its DEBUG line), `:222-251` (constructor, `enabledDump`), `:271-300` (`waitForDump`), `:306-373` (`dump`, `enabledDump=false` on `IOException`), `:375-405` (`Dumper.run`, check at `:379`), `:426-470`, `:515-587`, `:642-690`, `:939-957`, `:1218-1282` (`cleanup`), `:1285`; `OpenFileCtxCache.java:148-170, 240-261`; `WRITE3Request.java:36-43` (payload copied into a heap `byte[]`); `Nfs3Utils.java:140-145` (null channel); `Nfs3.java:38-58`; `NfsConfigKeys.java:24-62`; `hadoop-project/pom.xml:187, 2469`. All as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A1) | Node paths, `copy-source.sh`, no install build, surefire options via `maven-surefire-plugin.argLine`, read surefire counts | Applied 2026-11-25 (outside the repo; frozen sha256 above) | filed paths do not exist; `-D` does not reach the forked JVM |
| R2 (A2) | Node distribution copy, `hdfs --daemon` instead of `start-dfs.sh`, JDK 8 tools | Applied 2026-11-25 | `ssh localhost` does not work on the nodes; default `jcmd` is JDK 11 |
| R3 (A3) | Stream timeout 180 s, wait 200 s after `DONE` | Applied 2026-11-25 | 60 s timeout = 60 s PAUSE, and the monitor closes streams with pending writes |
| R4 (A4) | System rpcbind kept; try `hdfs --daemon start nfs3`, fall back to a no-registration launcher | Applied 2026-11-25 | shared node; the daemon registered with the system rpcbind, so the launcher was not needed |
| R5 (A5) | Run C5 | Applied 2026-11-25 | only run that varies the mark in the daemon |
| R6 (A6) | Per-run heap baseline and post-`DONE` histograms | Applied 2026-11-25 | lets C2 be read within one gateway instance |
| R7 (A7, A8) | Verdict labels for B2g and B3g, "limit never reached" row | Applied 2026-11-25 | every plausible outcome needs a verdict before any reading |
| R8 | Print the index of the stuck call in U7 and give the test a log4j configuration so the dump-failure log line is captured | Left for stage 3 | not needed for the verdict (stuck = 1 and the counter reaching 64 MiB are read directly) |
| R9 | Run the optional sequential-write baseline of B3h | Left for stage 3 (not run) | not part of B3g's verdict rows |

**Agreement criteria** — not needed (no run 2, see 5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 04:01–04:49 MST (node clock; gateway log timestamps are UTC, +7 h) |
| Node (CloudLab name and type) | `pc91` = `node0.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (in the `environment.md` Node table), 32 cores, 125 GiB RAM; node lock `/mydata/s4/NODE-LOCK` held 04:01–04:49 |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK (`java -version`) | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) for build, tests, NN, DN and gateway |
| Build tool | Maven 3.6.3 (offline, `~/.m2` 3.4.2 artifacts) |
| Local source copy | `copy-source.sh` of `systems/hadoop/source/` (clean) at repository commit `cd9e1cded`, tag `rel/release-3.4.2`, into `/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous-run1/src` |
| Case-file commit / harness commit | `bef6bc8a6` + amendments outside the repo (frozen sha256 above) / harness uncommitted (`~/writeup-hadoop/out/o16/harness/`) |
| Cluster | distribution copied from `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2`; NN + DN (`-Xmx1g`) + `nfs3` gateway via `hdfs --daemon`; gateway registered with the node's system `rpcbind` (100003/100005 listed); kernel NFSv3 client mount `vers=3,proto=tcp,nolock,noacl,sync,soft,timeo=600,retrans=2,wsize=<run>` (`rsize=1048576` negotiated) |
| Storage for node data | `/mydata` (local, 702 GB free) under the run folder; nothing on `/proj` |
| Full logs (path, outside the repo) | `~/writeup-hadoop/out/o16/run1/` (unit: `unit/`; cluster: `cluster/run-C*.out`, `cluster/obs/<run>/` incl. the per-run gateway log slice `nfs3.log.gz`); on the node, `…-run1/logs/` (gzipped) and `…-run1/obs/` were kept, bulk data deleted |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1, C2 | B3e step 7 / B3d "End state" read-back | 200 s after `DONE` only 6 of the 32 C2 streams had been closed (the monitor closes them one after another, ~3.4 s each, after the 180 s timeout: `obs/C2/analyze.txt` cleanups from 11:32:33 at 3.4 s steps); `f000` was still open (listed 65,536 B) and its read-back md5 did not match (`obs/C2/md5.txt`). | A9: before the read-back, wait until the dump directory is empty (all streams closed), at most 900 s, and compare every file. Run as C2b (`cluster-run2.sh run C2b`): same workload, then all 32 files compared. | 2026-11-25: the read-back is a side observable outside B1 and B3g's verdict rows, and no claim reading of C2 depends on the wait, so the tier was not restarted; C2b repeated C2 in full and its heap/counter readings agree with C2. | outside the repo (`case-amended.md` A9) |

## 4. Run 1

**Scope:** unit U1–U7; cluster C3, C1, C4, C2, C5 (in that order), and C2b (C2 repeated with the A9 read-back). **Command
log:** `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`, `run1/cluster/run-<run>.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/readings.txt`; surefire `Tests run: 1, Failures: 0, Errors: 0`, 35.1 s, `run1/unit/surefire/`; C = 65,536)

| Run | M | maxAfterReturn | maxSampled | maxInHeap | final | rounds | stuck | dumpFileLen | heapDelta (B) | vs B2f |
|---|---|---|---|---|---|---|---|---|---|---|
| U1 | 262,144 | 196,608 | 262,144 | 196,608 | 0 | 256 | 0 | 67,108,864 | −14,603,040 | all as predicted |
| U2 | 1,048,576 | 983,040 | 1,048,576 | 983,040 | 0 | 64 | 0 | 67,108,864 | 157,528 | all as predicted |
| U3 | 4,194,304 | 4,128,768 | 4,194,304 | 4,128,768 | 0 | 16 | 0 | 67,108,864 | 169,792 | all as predicted |
| U4 | 16,777,216 | 16,711,680 | 16,777,216 | 16,711,680 | 0 | 4 | 0 | 67,108,864 | 10,724,272 (< 24 MiB) | all as predicted |
| U5 | 134,217,728 | 67,108,864 | 67,108,864 | 67,108,864 | 67,108,864 | 0 | 0 | −1 | 67,326,808 (64.2 MiB) | all as predicted |
| U6 (null path) | 1,048,576 | 67,108,864 | 67,108,864 | 67,108,864 | 67,108,864 | 0 | 0 | −1 | 77,897,400 (74.3 MiB) | all as predicted |
| U7 (bad dir) | 1,048,576 | 67,108,864 | 67,108,864 | 67,108,864 | 67,108,864 | 0 | **1** | −1 | 67,329,704 (64.2 MiB) | as predicted (stuck call index not printed) |

`maxInHeap` is sampled after each call returns, so it reads M − C (the M-th byte is drained before the call returns);
`maxSampled` (the concurrent sampler) saw exactly M in U1–U4.

**Cluster tier** (mark 1,048,576 unless noted; `byte[]` = live `[B` bytes from `jcmd GC.class_histogram` (full GC);
counter readings from the gateway's DEBUG lines via `analyze.py`)

| Run | Observable (B3d) | Reading | B3f prediction | Evidence (file) |
|---|---|---|---|---|
| C1 | max counter / times at mark | 1,048,576 / 767; no increment above the mark; all increments 65,536 | 1,048,576 / 767 | `obs/C1/analyze.txt` |
| C1 | counter at PAUSE | 983,040 | 983,040 | `obs/C1/analyze.txt` |
| C1 | dump file at PAUSE | 804,257,792 B (grew 201 / 403 / 604 / 804 MB at 25/50/75 %/PAUSE) | 804,257,792 | `obs/C1/checkpoints.txt`, `run-C1.out` |
| C1 | live `byte[]` at 25 / 50 / 75 % / PAUSE | 14,066,376 / 14,213,832 / 14,361,288 / 15,491,976 (PAUSE − 25 % = +1.36 MiB); 5-s samples 13.89–15.49 MB over the whole run (69 samples) | within ±8 MiB, flat | `obs/C1/checkpoints.txt`, `obs/C1/histo-5s.log` |
| C1 | process health / end state | OOM 0, dump errors 0, driver `DONE`; HDFS file 805,306,368 B, md5 = expected; dump file gone 200 s after `DONE` (stream closed 11:20:40 UTC, 0 pending writes) | completes, no OOM, 805,306,368 B, dump deleted | `obs/C1/counter-summary.txt`, `md5.txt`, `analyze.txt` |
| C2 | max counter / times at mark | 1,048,576 / 480 (= 32 × 15) | ≤ 1,048,576 per update | `obs/C2/analyze.txt` |
| C2 | dump files at PAUSE | 32 files × 15,728,640 B (dir total 503,320,576 incl. 4,096 for the dir) | 32 × 15,728,640 | `run-C2.out`, `obs/C2/checkpoints.txt` |
| C2 | live `byte[]` at PAUSE | 45,949,088: +31,882,712 B (+30.4 MiB) over C1@25 %, +31,917,112 B over C2's own baseline; back to 16,218,544 right after `DONE` | +25 to +40 MiB over C1@25 %, back down after `DONE` | `obs/C2/checkpoints.txt` |
| C2 | read-back | `f000` open at the check (65,536 B listed), md5 ≠ expected — see §3 defect 1 | — | `obs/C2/md5.txt`, `run-C2.out` |
| C2b | as C2, then A9 read-back | max 1,048,576, 480 at mark; PAUSE `byte[]` 45,953,080; all 32 streams closed 90 s after the 200 s wait; **32 of 32 files md5 = expected** | — | `obs/C2b/`, `run-C2b.out` |
| C3 | max counter / dump | 983,040; 0 at mark; no `Create dump file` line; dump dir empty throughout | 983,040; 0; no dump file | `obs/C3/analyze.txt`, `obs/C3/checkpoints.txt` |
| C3 | live `byte[]` at PAUSE | 14,922,584 (+0.82 MiB over C1@25 %) | about baseline | `obs/C3/checkpoints.txt` |
| C3 | end state | 1,048,576 B HDFS file, md5 = expected | completes | `obs/C3/md5.txt` |
| C4 | max counter / times at mark / counter at PAUSE | 1,048,576 / 767 (every increment is 1,048,576) / 0 | 1,048,576 / 767 / 0 | `obs/C4/analyze.txt` |
| C4 | dump file / `byte[]` at PAUSE | 804,257,792 B / 13,955,064 (−0.11 MiB vs C1@25 %) | 804,257,792 / ±8 MiB | `obs/C4/checkpoints.txt`, `run-C4.out` |
| C4 | end state | OOM 0; 805,306,368 B, md5 = expected | completes, no OOM | `obs/C4/counter-summary.txt`, `md5.txt` |
| C5 (patched, M = 67,108,864) | jar constant | `ldc2_w … long 67108864l` | — | `obs/C5/jar-const.txt` |
| C5 | max counter / times at mark / counter at PAUSE | 67,108,864 / 11 / 67,043,328 | 67,108,864 / 11 / 67,043,328 | `obs/C5/analyze.txt` |
| C5 | dump file at PAUSE | 738,197,504 B | 738,197,504 | `run-C5.out` |
| C5 | live `byte[]` | PAUSE 81,568,608 (+67,502,232 B = +64.4 MiB over C1@25 %); 5-s samples show the sawtooth 14 → 34 / 37 / 77 / 62 / 33 / 43 / 82 MB; the three checkpoints fall just after a dump round (3,072 chunks = 3 × 1,024), so they read 14.08–14.36 MB | about +64 MiB, sawtooth | `obs/C5/checkpoints.txt`, `obs/C5/histo-5s.log` |
| C5 | end state | OOM 0; 805,306,368 B, md5 = expected | completes in 512m | `obs/C5/counter-summary.txt`, `md5.txt` |

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached in every binding run: unit rounds = 64 MiB / M (U1–U4) [observed:
   `unit/readings.txt`]; daemon counter at the mark 767 (C1, C4), 480 (C2), 11 (C5) times [observed: `obs/*/analyze.txt`].
   Held fixed: the loaded jar's constant in every run [observed: `obs/*/jar-const.txt`]; gateway heap from `HDFS_NFS3_OPTS`
   (`-Xms256m -Xmx256m` in C1) [observed: `run-C3.out` `ps` line, same script for all runs]; mount `wsize` [observed:
   `/proc/mounts` lines in `run-*.out`]; the dump path on local disk [observed: `cluster/conf/hdfs-site.xml`]. M restored
   after each unit run [inferred: the test's `finally`-less `wm.setLong(null, saved)` runs at the end of each `run`, and
   no run threw]. Valid.
2. **Readings.** No outlier in the claim readings. Unusual: U1 `heapDelta` negative (GC noise, below the bound); the
   live `byte[]` right after `DONE` rises by 4–6 MB in C1 and C4 (the write-back's reload buffers and DFS packets; inferred) and is
   back to baseline at +200 s [observed: `checkpoints.txt`]; C2's read-back mismatch is a timing defect (§3), repaired by
   C2b.
3. **Matched rows.** Unit, A7 row 1 + row 4 + row 6: "U1–U4 counter and in-heap bytes stay ≤ M, rounds = 64 MiB/M, dump
   file = 64 MiB, heapDelta small" — maxSampled = M, maxInHeap ≤ M − C, rounds 256/64/16/4, dump 67,108,864, heapDelta ≤
   10.7 MB [observed: `unit/readings.txt`]; "U5/U6 heap and counter reach 64 MiB while U1–U4 stay flat" — 67,108,864 and
   64–74 MiB [observed]; "U7 stuck = 1 and counter → 64 MiB" [observed]. Cluster, A8 row 1: C1 completes in 256 MiB,
   `byte[]` flat (+1.36 MiB 25 % → PAUSE), dump 804,257,792 B, max counter 1,048,576; C3 no dump; C4 counter 0 at PAUSE,
   no OOM; C5 counter to 67,108,864 and +64.4 MiB [observed: `obs/*`]; C2 +30.4 MiB at PAUSE, back after `DONE` (B3g
   "positive control" row) [observed].
4. **Excluded rows.** Unit row 2 (**Refuted**): maxInHeap ≤ 16,711,680 and heapDelta ≤ 10.7 MB in U1–U4, far below
   60 MiB. Row 3: rounds and dump length exact. Row 5 (Invalid): U5/U6 reached 64 MiB. "Limit never reached": rounds > 0.
   Row 7: U7 stuck = 1. Cluster "C1 `byte[]` rises / OOM / counter > M + C" (**Refuted**): +1.36 MiB, OOM 0, no increment
   above the mark. C5 refutation row: the counter did follow the patched mark. "Dump file does not reach 767 MiB": it
   did (804,257,792 B). "Run cannot complete": every driver printed `DONE`; no dump error line. "C2 shows no heap
   difference": +30.4 MiB.
5. **Observed vs. inferred.** The conclusion rests on observed readings. Inferred: (a) the C1 heap is the gateway's
   only significant holder of WRITE payloads, so a flat `byte[]` means the payloads left the heap — supported by
   `WRITE3Request.java:41` (payload copied into a `byte[]`) and by C2/C5 showing the instrument sees 1 MiB per file and
   64 MiB held; (b) the DEBUG counter lines in C2 interleave 32 files, so per-file values are inferred from the
   increments (all 65,536) and 480 hits = 32 × 15; (c) U7's stuck call is the 16th (predicted k = 1009), not printed.
6. **Deviations and gaps.** A4's fallback was not needed (the daemon registered with the system rpcbind). C2's
   read-back was premature (§3) and repeated as C2b. The optional sequential-write baseline was not run. The unit test
   has no log4j configuration, so its dump log lines are absent. The exact peak between increment and dump is not
   observable in the daemon (the DEBUG line gives the value after each update, which is enough for the maximum).
   None of these touches a verdict row.
7. **Core question.** Usage follows the constraint: the in-heap out-of-order data peaks at exactly the mark for every
   mark value tried — 256 KiB, 1, 4, 16 MiB in the unit tier (part 3) and 1 MiB and 64 MiB in the daemon (C1, C5) — and
   each time the dump drains it to zero while the dump file takes the rest (parts 1, 3). The constraint caps usage per
   open file: 768 MiB passes through a 256 MiB gateway with flat live `byte[]` (C1), and the held amount scales with the
   number of open files (C2, +30 MiB for 32 files) — the A4 per-gateway gap. The cap is lost when the dump file cannot be
   created: the waiting writer is never released and later writes grow the counter to the full workload (U7, part 3).

**Conclusion (one line):** unit A7 row 1 (+ row 6 bypass) — confirmed, bypass as recorded; cluster A8 row 1 — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `unit/readings.txt` (rounds), `obs/*/analyze.txt` (hits), `obs/*/jar-const.txt` (m1: 1048576l in C1–C4, C2b; m64: 67108864l in C5), `run-C3.out` (`-Xms256m -Xmx256m`), `/proc/mounts` lines (`wsize=65536`; C4 run log `wsize=1048576`). |
| 2. Readings | yes | Re-read `obs/C1|C4|C5/checkpoints.txt` (AFTER-DONE 19.55 / 20.33 / 15.47 MB, +200 s 13.89 / 13.89 / 13.90 MB); `obs/C2/md5.txt` and `run-C2.out` (`f000` 65,536 B). |
| 3. Matched row | yes | Each number in part 3 re-read from the cited file; C2 PAUSE − C1@25 % recomputed: 45,949,088 − 14,066,376 = 31,882,712 B = 30.41 MiB; C5: 81,568,608 − 14,066,376 = 67,502,232 B = 64.37 MiB; C1: 15,491,976 − 14,066,376 = 1,425,600 B = 1.36 MiB. |
| 4. Excluded rows | yes | Both Refuted rows addressed with readings; `analyze.py` "increments above mark 0" in C1, C2, C4, C5. |
| 5. Observed vs. inferred | yes | (a) checked against `WRITE3Request.java:36-43`; (b) `analyze.txt` C2 "increment sizes [65536]"; (c) left as a gap (R8). |
| 6. Deviations and gaps | yes | C2b output re-read: `files matching: 32 listed, 32 match` (`run-C2b.out`). |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's logic: counter capped at M for several M (unit + C1/C5), real heap flat when the cap binds (C1, U1–U4 heapDelta) and growing when it does not (U5/U6, C5 at 64 MiB), disallow evidence (dump rounds, dump file length), instrument control (C2). |

### 5.2 Run 2?

**No** — decided 2026-11-25. Every verdict row rests on observed readings that match B2f/B3f exactly, both tiers agree,
and the one bypass (U7) is a direct reading of the unit test, not an inference. The result neither refutes the case nor
relies on a part of §5.1 that run 1 could not settle.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps).

**Claim tested:** for one open file on the NFS gateway, heap bytes held by out-of-order WRITE data
(`nonSequentialWriteInMemory`, and the `byte[]` behind it) never exceed `DUMP_WRITE_WATER_MARK` plus one request; once
the mark is reached the excess is moved to `nfs.dump.dir/<fileId>`, so heap use stays flat while the dump file grows;
with the mark above the workload, or dumping off, held heap grows with the workload. "Confirmed" below means this
claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — A7 row 1 with row 4 (control) and row 6 (U7: dump-failure bypass observed, one writer stuck, counter → 64 MiB) | caps only on some paths (bypass) | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — A8 row 1 (C1, C3, C4, C5), with B3g's C2 positive-control row | caps (per open file) | run 1 + self-check | 2026-11-25 |

Feedback filed in the case file's section D2 (`case-amended.md`), with the A9 runbook fix. The stage-3 index row and
HANDOFF are not edited by this run (the run was told not to edit the repository); suggested index cell: "Confirmed —
caps (unit: bypass on dump failure) / Confirmed — caps; true positive".
