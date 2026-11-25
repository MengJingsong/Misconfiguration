# MAX_KEY_SIZE-write-limit-2--autonomous — stage-4 results  <!-- file: results/MAX_KEY_SIZE-write-limit-2--autonomous.md -->

> **Case:** [`MAX_KEY_SIZE-write-limit-2--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/MAX_KEY_SIZE-write-limit-2--autonomous.md) (Jingsong's queue, order 6; `BoundedByteArrayOutputStream.java:91`)
>
> **Status:** verdict filed (run 1 + self-check; no run 2) — 2026-11-25, node `pc91` (second attempt; the first, on `pc99`, was blocked)
>
> **Outcome class:** **true negative** — estimate `negative`, effect `does not cap` on both tiers (cluster tier: disk only, A10)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback field is section D.

Written outside the repository (stage-4 worker for Jingsong). Paths below are relative to `~/writeup-hadoop/out/o6/`:
`run1/` holds the small logs copied off the node, `harness/` the instruments, `case-amended.md` the case file with the
dated amendments and section D, `attempt1/` the blocked first attempt's results file.

## 0. Attempt history

- **Attempt 1 (2026-11-25, 04:02–05:03 EST, node `pc99`): blocked, nothing ran.** That session did the audit
  (amendments A1–A8) and wrote the harness, then waited 60 min for `pc99`'s node lock (`jingsong-o70-stage4`, stale);
  it never got the lock, created no run folder and started no process. No reading existed.
- **Attempt 2 (this one, 2026-11-25, from 12:02 EST): runs on `pc91`, not `pc99`.** The lock `/mydata/s4/NODE-LOCK` on
  `pc91` was free and taken at 12:02:41 EST (10:02:41 MST, owner `jingsong-h6-stage4`). Before any reading this session
  re-checked attempt 1's audit and harness against `systems/hadoop/source` (section 1.1, last row and "Harness review")
  and added amendments A9–A10.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `8bd1dfb31`; the case file was last changed in `bef6bc8a6`; as filed, sha256 `8f77da5cb43dd88ca24c19657eb2c491dde45acf58bb8f42a5479b8dd0597649` (= `_INDEX.md` §4). After attempt 1's amendments A1–A8: `2da7b37f…feff37db3`. **Frozen version (after A9–A10, 2026-11-25 12:03 EST, before any reading): `case-amended.md`, sha256 `67f24da704242c141ee8cc41b474227941893883b184f9c725b3c91c4e28b054`** (unit tier and cluster attempt 0 ran on it). After runbook-defect fix A11 (cluster tier restarted on it): **`8d9cd92e2e0fc7082506acaaa5a327f54edf44d2a4f2d18c8efade9c4a3a722b`** — the frozen version for `_INDEX.md`. Section D2 was added after that (feedback only): `ea83df0e…6900b949`. |
| **Frozen tables** | sha256 of `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' case-amended.md` (unit predictions B2f + conclusions B2g with A3, A4): **`99017a035e1c4451daebbebd26cf9edfb235cd46d9c44c954aff5c17e8433910`**. Of `sed -n '/^\*\*B3f\./,/^\*\*B3h\./p'` (cluster predictions B3f + conclusions B3g with A8): **`b13ee3e9fe7310c015e03a085e18f258386ef18f9cea3166fddc662bf8202334`**. Both equal attempt 1's (A9–A10 lie outside these ranges). No row is changed after this point. |
| **Harness** | `harness/`: `TestBoundedLimitMemory.java` (U0 instrument, U1–U5), `unit-run.sh`, `cluster-run.sh`, `selfcheck.py` (attempt 1, reviewed and kept unchanged), `driver.sh` (this attempt: runs the steps in order on the node), `driver-cluster-restart.sh` (the restart after defect 1), `acquire-lock.sh` (attempt 1, `pc99`; not used). Not committed (this run does not edit the repository); to go under `hadoop/stage4-runtime-verification/jingsong/harness/MAX_KEY_SIZE-write-limit-2--autonomous/` when filed. Instrument check = step 1 of run 1 (`unit-run.sh --compile-only`, then U0's known-answer line). |
| **Tiers and values** | Unit: U1 `limit` 1024 / 32768 / 65536 at capacity 64 KiB; U2 `limit` 1 KiB / 512 KiB / 1 MiB at capacity 1 MiB; U3 capacity 64 KiB / 1 MiB / 16 MiB (`limit` = capacity); U3b `ByteArrayOutputStream`, 200 × 1 KiB; U4 TFile key via `prepareAppendKey(-1)` (1 KiB writes until EOF) and `prepareAppendKey(65537)`; U5 TFile of N = 1 / 10 / 100 records with 64 KiB keys. Cluster: DistributedShell, 2 containers × stdout N = 1 / 16 / 64 MiB, logs aggregated in TFile; positive control N = 64 MiB under a 32 MiB HDFS space quota on `/tmp/logs` (A7: earlier A-run logs removed first); workload B, wordcount with memory-to-memory merge. `MAX_KEY_SIZE` stays 65,536 (constant). |
| **Audit bottom line** | **Ready after amendments** (A1–A8, 2026-11-25 attempt 1; A9–A10, 2026-11-25 attempt 2) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: heap bytes of the stream's `byte[]` (thread-allocated bytes) and disk bytes (TFile length; aggregated HDFS bytes). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | `MAX_KEY_SIZE` is `private static final` (`TFile.java:155`). Unit varies the stream's own `limit` (1 KiB / 32 KiB / 64 KiB = default; and 1 KiB / 512 KiB / 1 MiB at 1 MiB capacity) on the same code; cluster varies data volume, reason stated in the B3 intro. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d thread-allocated bytes (real allocation; retention inferred, named); U5 file length; B3d `hdfs dfs -du`. Gap named: line 91's execution in the NM is inferred (A8). |
| A. Core question | usage driven to the limit and past it | Partly | Unit: every arm writes until the `EOFException` (U1, U2, U4). Cluster: data volume ≫ 64 KiB, but the keys (tens of bytes) never reach the limit, so the check cannot fire there; named in A10, the disallow evidence is the unit tier's. |
| A. Core question | positive control (negative estimate) | Met | Unit: U3 (allocation follows capacity, the size that does bind heap) and U3b (unbounded stream grows with bytes written). Cluster: the HDFS space quota on the same workload (B3h, A7, A8). |
| B. Logic | each step says what it establishes | Met | B2b "Why" column; B2h, B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f (counts, byte bounds; U5 per A3), B3f with A8's numeric "linear" and "caps". |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met (after A4, A8) | B2g: flat (confirm), follows limit / grows with bytes (refute), instrument blind / limit never reached / other mechanism / intermediate / errors (A4). B3g: linear (confirm), held near 64 KiB or message (refute), control fails / no aggregation (not confirmed), B rows. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For this negative claim: flat across `limit` with U3/U3b moving, plus the `EOFException` at `write:92` in U1/U2/U4 (A2, A4). |
| B. Logic | alternative explanations and their controls | Met | Instrument blindness → U3/U3b; JIT/class loading → warm-up (A2); loss elsewhere in aggregation → local `du -sb` and read-back; prior apps in the quota → A7. |
| C. Specific | a human can follow it from the intro and §9a | Met | B1 + B2f/B2g + B3f/B3g. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met (after A1, A5, A6, A9) | Node paths, build, daemon start, DS command, bucket path. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met (after A2, A6) | U4 warm-up and frame; DS quoting and read-back. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `pc91`: `/mydata/jingsong-s4/hadoop-base/.../hadoop-3.4.2/bin/hadoop` present; JDK 8, Maven 3.6.3, `~/.m2` 3.4.2 (environment.md §1, §3); 703 GB free on `/mydata`; ports 9000/9870/9864-9868/8088/8030-8033/8040/8042/13562 free; no Java process (checked 12:02 EST). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: loops run to `EOFException` by construction; 25 × 16 MiB arrays in a 2 GiB heap. Cluster: ≈ 0.5 GB of HDFS data, NM 4096 MB for 2 × 256 MB containers + AM; the control's 128 MiB of stdout exceeds the 32 MiB quota 4× (with 1 MiB blocks; A7 empties `/tmp/logs/$USER` first). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source` (clean). Attempt 1's list, plus re-checked in attempt 2: `BoundedByteArrayOutputStream.java:55-56` (alloc), `:91-92` (check, message "Reach the limit of the buffer"), `:103-114` (`reset`); `TFile.java:289-290` (two `MAX_KEY_SIZE` buffers), `:308-312` (close in a non-READY state → `IllegalStateException`, as the U4 harness expects), `:393-409` (`append`), `:452-454` (first key), `:527-536`, `:653-666` (`finishDataBlock` adds an index entry with the last key for every block, sorted or not), `:2250-2252`, `:2272-2289` (index writes the first key and every entry) — so A3's (2N+1) × 64 KiB holds; `BCFile.java:119-137, 152-173` and `Compression.java:242-250` (NONE: no downstream buffer; `getCompressedSize` counts the buffered bytes, so every 64 KiB record closes its block); `LogAggregationUtils.java:160-165` (bucket dir); `LogAggregationFileController.java:499-550` (`createAppDir` recreates missing parents per app, no cache, so A7's delete is safe); `AppLogAggregatorImpl.java:329, 477-481, 529, 668` and `LogAggregationTFileController.java:152` (failures are logged with the exception, so a `DSQuotaExceededException` would be named in the NM log, as A8 needs); `MergeManagerImpl.java:202, 341-342, 411, 426` (merge trigger and log strings); `hadoop-project/pom.xml:39, 172-187, 2469`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Node paths, no `-am install`, surefire options | A1 (attempt 1); node corrected to `pc91` by A9 | Shared `~/.m2` must not be overwritten. |
| 2 | U4 warm-up; record the top frame | A2 | B2h requires post-warm-up medians. |
| 3 | U5 arithmetic: the index stores each block's last key | A3 (re-verified in attempt 2) | Source-only mistake; prediction corrected before any reading. |
| 4 | Missing B2g rows | A4 | Every outcome needs a row. |
| 5 | Cluster setup with `--daemon`, distribution copy | A5; node per A9 | No SSH to localhost on the nodes. |
| 6 | DS command without `tr`, NUL read-back, bucket path | A6 | Quoting not exact; 3.4.2 path. |
| 7 | Empty `/tmp/logs/$USER` before the quota control | A7 | Otherwise the quota is exceeded before the control writes. |
| 8 | Numbers for B3g row 1; B's role; inferred line-91 path | A8 | "Linear" and "caps" need thresholds. |
| 9 | Node `pc91`; JPMS flags left out of the argLine | A9 (attempt 2) | `pc99` was blocked; the flags mean nothing on JDK 8. |
| 10 | Name the cluster tier's scope (keys never near 64 KiB; disk only) | A10 (attempt 2) | Group A "past the limit" is only partly met on the cluster; the gap must be visible. |
| 11 | A cluster-side probe that counts line-91 executions in the NM (e.g. Byteman) | Left for stage 3 | The path is short and fixed (`LogKey.write` → `writeUTF` → `write(byte[],int,int)`); its absence is named (A8). |

**Harness review (attempt 2, before any reading).** `TestBoundedLimitMemory.java` matches B2c/B2d with A2 (warm-up 20,
median of 5, probe baseline subtracted, frames recorded); U4 closes each writer expecting `IllegalStateException`
(`TFile.java:308-312`); U5 uses `minBlockSize` 64 KiB and `COMPRESSION_NONE` as B2c. `unit-run.sh`: argLine per A1/A9,
reads surefire counts, stops on errors, runs B2e step 4. `cluster-run.sh`: B3a/B3e with A5–A7; its EXIT trap clears the
quota and stops every daemon; container IDs `container_<ts>_<n>_01_00000{2,3}`. `selfcheck.py` parses the raw surefire
output and the `IFCHK` lines of the cluster log against B2f/B2g (A3, A4) and B3f/B3g (A8); a few of its checks (U5
ranges, agg ≥ local − 64 KiB, U2 frame) are stricter than the tables and are informative only. No change was needed;
all four are reused unchanged. `driver.sh` is new (sequencing and the PID file only). After run 1's runbook defect 1, `cluster-run.sh` also fetches `syslog.shuffle` (A11; md5 `35994760` → `d6b4d34e`).

**Agreement criteria** — not applicable unless §5.2 chooses run 2.


## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (node clock MST; session clock EST = MST + 2 h). Freeze 12:03 EST. Unit 10:05:07–10:06:19 MST (12:05–12:06 EST). Cluster attempt 0 (defect 1, not evidence) 10:06:19–10:11:04 MST. Cluster restart 10:13:17–10:18:16 MST (12:13–12:18 EST). Lock held 10:02:41–10:18:48 MST. |
| Node | **`pc91`** (`node0.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`), 32 cores, 125 GiB RAM; **not `pc99`** (attempt 1's node, blocked by its lock) |
| OS and kernel | Ubuntu 22.04, `5.15.0-203-generic` |
| JDK | OpenJDK `1.8.0_514` (build, surefire and all daemons; `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`) |
| Build tool | Maven 3.6.3; `mvn -B test` in `hadoop-common` against `~/.m2` 3.4.2 (A1) |
| Local source copy | `copy-source.sh` from `systems/hadoop/source` (`git status` empty) at repository HEAD `8bd1dfb31` → `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-2-run1/src` (`rel/release-3.4.2`) |
| Distribution (cluster) | `cp -a` of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (built 2026-11-24, BUILD SUCCESS) |
| Case-file commit / harness | `bef6bc8a6` (+ amendments in `case-amended.md`) / harness outside the repo (`harness/`), md5 `TestBoundedLimitMemory.java` `bbd0f97b`, `unit-run.sh` `ca0965a5`, `cluster-run.sh` `d6b4d34e` (restart; `35994760` in attempt 0), `selfcheck.py` `70120f3d`, `driver.sh` `ae9cbdc5`, `driver-cluster-restart.sh` `cd53b7b8` |
| Storage | `/mydata` (local, 703 GB free); nothing on `/proj` |
| Full logs | `run1/` here (1.3 MB). On the node only `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-2-run1/{logs,conf,harness}` (1.5 MB) remain; `src/`, `hadoop/`, `nn/`, `dn/`, `tmp/`, `nm-local/`, `nm-logs/`, `in/`, `pids/` were deleted |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | Run 1, cluster attempt 0 | B3d / B3e step 5 (workload B) | The merge lines were read from the reducer's `syslog`; in 3.4.2 the `org.apache.hadoop.mapreduce.task.reduce` loggers write to `syslog.shuffle` (`container-log4j.properties:16, 47-56`, `MRApps.java:662`). Attempt 0's `B.merge-lines.txt` was empty, without even the `MergerManager: memoryLimit` line every reducer logs (`run1/attempt0-runbook-defect/cluster/`). | A11: read `syslog` and `syslog.shuffle`; `cluster-run.sh` fetches both. | Cluster tier restarted from B3e step 1 on a fresh format and fresh state (2026-11-25). Attempt 0 is kept under `run1/attempt0-runbook-defect/` and is not evidence. B3f/B3g unchanged (hash `b13ee3e9…` before and after). | `8d9cd92e…a722b` |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** `run1/driver.log`; unit `run1/unit/unit-run.log`,
`run1/unit/mvn-test-ifchk.log`, `run1/unit/mvn-test-existing.log`; cluster `run1/cluster/cluster-run.log`. Raw readings:
`run1/unit/org.apache.hadoop.io.TestBoundedLimitMemory-output.txt` (IFCHK lines), `run1/cluster/ifchk-cluster.csv`.

### 4.1 Readings

**Unit tier** (all medians of 5 after 20 warm-ups; the 5 raw values were identical in every row)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| U0 instrument | supported, enabled; probe baseline 0 B; known answer `new byte[1 MiB]` = 1,048,592 B; max heap 2,024,275,968 B (= `-Xmx2048m`), Parallel GC, JDK 1.8.0_514 | `TestBoundedLimitMemory-output.txt` `IFCHK,instr` |
| U1 cap 65,536, lim 1,024 / 32,768 / 65,536 | writes 1 / 32 / 65; size at EOF 1,000 / 32,000 / 65,000; `limit` 1,024 / 32,768 / 65,536; buffer length 65,536 in all; "Reach the limit of the buffer" at `BoundedByteArrayOutputStream.write:92` | `IFCHK,U1` |
| U2 cap 1 MiB, lim 1,024 / 524,288 / 1,048,576 | `ctorAlloc` 1,048,624 / 1,048,624 / 1,048,624 B (spread 0); `writeAlloc` 3,920 / 3,920 / 3,920 B; writes 1 / 524 / 1,048 (size 1,000 / 524,000 / 1,048,000); frame `write:92` | `IFCHK,U2` |
| U3 cap = lim = 65,536 / 1,048,576 / 16,777,216 | `ctorAlloc` 65,584 / 1,048,624 / 16,777,232 B; `writeAlloc` 3,920 B in each | `IFCHK,U3` |
| U3b `ByteArrayOutputStream`, 200 × 1,024 B | allocation 523,480 B | `IFCHK,U3b` |
| U4 `prepareAppendKey(-1)` | 64 writes of 1,024 B succeed, the 65th throws "Reach the limit of the buffer" at `write:92`; `TFile.Writer` `ctorAlloc` 131,576 B; `writeAlloc` 3,920 B | `IFCHK,U4,keyPrepare=-1` |
| U4 `prepareAppendKey(65537)` | `java.lang.IndexOutOfBoundsException: Limit exceeds buffer size` | `IFCHK,U4,keyPrepare=65537` |
| U5 N = 1 / 10 / 100 records, 64 KiB key | file length 196,774 / 1,376,603 / 13,174,973 B; per-record slopes 131,092.1 and 131,093.0 B | `IFCHK,U5`; `run1/selfcheck.txt` |
| Surefire | `TestBoundedLimitMemory` 6 run, 0 failures, 0 errors; existing `TestBoundedByteArrayOutputStream` 2/0/0, `TestTFileStreams` 19/0/0 | `run1/unit/*.txt`, `mvn-test-*.log` |

**Cluster tier** (restart after defect 1; NM pid 1211079, apps `application_1795626807835_000{1..5}`)

| Value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| N = 1 MiB | A | final / aggregation | SUCCEEDED / SUCCEEDED | `ifchk-cluster.csv` A1M, `ds-A1M.status.txt` |
| | | aggregated bytes (HDFS) / local raw logs | 2,124,024 B / 2,139,532 B | `ifchk-cluster.csv`, `ds-A1M.hdfs-ls.txt`, `ds-A1M.local-ls.txt` |
| | | stdout read-back (NUL bytes), containers 2 and 3 | 1,048,576 / 1,048,576 | `ifchk-cluster.csv` |
| | | "Reach the limit of the buffer" (NM log / `yarn logs`) | 0 / 0 | `ifchk-cluster.csv` |
| N = 16 MiB | A | final / aggregation; agg / local; read-back; limit msg | SUCCEEDED / SUCCEEDED; 33,581,369 / 33,596,814 B; 16,777,216 ×2; 0 / 0 | `ifchk-cluster.csv` A16M |
| N = 64 MiB | A | final / aggregation; agg / local; read-back; limit msg | SUCCEEDED / SUCCEEDED; 134,245,028 / 134,260,110 B; 67,108,864 ×2; 0 / 0 | `ifchk-cluster.csv` A64M, `ds-A64M.hdfs-ls.txt` |
| slopes | A | (agg16 − agg1)/15 MiB; (agg64 − agg16)/48 MiB | 2.000004; 2.000007 (agg − 2N = 26,872 / 26,937 / 27,300 B) | computed from `ifchk-cluster.csv` |
| N = 64 MiB, quota 32 MiB | control | `hdfs dfs -count -q /tmp/logs` | before A7 delete 169,950,421 B used; after delete 0; quota set 33,554,432, remaining 33,554,432; after control 33,554,432 used, remaining 0 | `cluster-run.log` |
| | | final / aggregation | SUCCEEDED / **FAILED** | `ifchk-cluster.csv` CTRL64M, `ds-CTRL64M.status.txt` |
| | | aggregated bytes | 33,554,432 B, one file `pc91.cloudlab.umass.edu_41265.tmp` (never renamed) | `ds-CTRL64M.hdfs-ls.txt` |
| | | NM `DSQuotaExceededException` lines | 12 ("quota = 33554432 B = 32 MB but diskspace consumed = 34603008 B = 33 MB") | `ifchk-cluster.csv` ctrlquota, `ctrl-nm-quota-lines.txt` |
| | | read-back; limit msg | 0 / 0 (nothing readable); 0 | `ifchk-cluster.csv` |
| B | wordcount, memtomem on, threshold 5 | job; merges | SUCCEEDED, `_SUCCESS` present; 8 "Initiating Memory-to-Memory merge with 5 segments", 8 completed (memoryLimit 535,088,320, 40 maps) | `ifchk-cluster.csv` clusterB, `B.merge-lines.txt`, `B.client.log` |
| | | limit msg (reducer syslog + syslog.shuffle / NM log) | 0 / 0 | `ifchk-cluster.csv` |
| all | | "Reach the limit of the buffer" in NN, DN, RM, NM logs | 0 in each | `run1/daemons/*.log.gz` |
| N = 64 MiB | A (record only) | NM `jstat -gc` | old gen used ≤ 23.7 MB, 3 full GCs; heap not near 1 GiB | `jstat-nm-A64M.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Unit: the instrument is exact (known answer 1,048,592 B for `new byte[1 MiB]`, baseline 0) [observed:
   `IFCHK,instr`]; every arm wrote until the `EOFException` from `write:92` (U1, U2, U4), so the limit was reached and
   passed by one attempt [observed: `IFCHK,U1/U2/U4`]; surefire 6/0/0 and the existing tests 21/0/0 [observed:
   `run1/unit/*.txt`]; heap 2 GiB as A1 [observed: maxHeap]. Cluster: four daemons up (`jps`), all A apps SUCCEEDED with
   aggregation SUCCEEDED, so the TFile path ran [observed: `cluster-run.log`, `ds-*.status.txt`]; each app measured in its
   own directory [observed: `ds-*.hdfs-ls.txt`]; the quota was applied to an empty `/tmp/logs` (A7) [observed:
   `count -q` lines]. The key limit is not reached on the cluster by design (A10). Valid.
2. **Readings.** No outlier: every median's 5 raw values are identical. `writeAlloc` is 3,920 B in every arm of U2, U3
   and U4, whatever the bytes written (1,000 to 16,777,000) — the cost of one `EOFException` with its stack trace
   [inferred: constant across 1,000× more writes, same in U3 where `limit` = capacity]. At lim = 1,024 it exceeds the
   1,000 bytes written, which `selfcheck.py`'s extra check flags; that check is not a B2g row (see part 4). The control's
   aggregated file stayed as a `.tmp` of exactly 32 MiB [observed: `ds-CTRL64M.hdfs-ls.txt`].
3. **Matched row.** Unit, B2g row 1: "U2 `ctorAlloc` flat across limits, U3 `ctorAlloc` follows capacity, `writeAlloc`
   ≈ 0 — claim confirmed", with A4's conditions: U2 within B2f (1,048,624 B ∈ ≈ 1,048,576 + ~50, spread 0 ≤ 1 KiB;
   `writeAlloc` 3,920 < 4,096), U3 within ±1 KiB of capacity, U3b 523,480 ≥ 204,800, U1/U4 at the predicted indices
   with `write:92`, U5 linear per A3 (slopes 131,092.1 vs 131,093.0, within 5 %; len(100) 13,174,973 ≥ 6,553,600) —
   also B2g "U5 linear in N — disk follows data volume" [observed: IFCHK lines]. Cluster, B3g row 1: "Aggregated size
   linear in N, ≫ 64 KiB, limit message 0, control caps at ≤ 32 MiB", with A8's numbers: slopes 2.000004 and 2.000007 ∈
   [1.9, 2.1]; agg ≥ 2N for every N; read-back = N exactly for both workers; control agg 33,554,432 ≤ 33,554,432,
   aggregation FAILED, 12 `DSQuotaExceededException` lines [observed: `ifchk-cluster.csv`, `ctrl-nm-quota-lines.txt`].
4. **Excluded rows.** Unit: "U2 `ctorAlloc` or `writeAlloc` rises with `limit` (≥ 512 KiB difference)" (Refuted) — spread
   0 B for both. "`writeAlloc` grows with bytes written before the EOF (≳ size at EOF)" (Refuted) — `writeAlloc` is 3,920 B
   at 1,000, 524,000 and 1,048,000 bytes written, so it does not grow with them; at 1,000 bytes it is above the size only
   because the exception costs more than the data, and it is under B2f's < 4 KiB bound. "U5 capped near 64 KiB" (Refuted)
   — 13,174,973 B at N = 100. "U3/U3b do not move" (Not confirmed) — they move with size. "U1/U4 never throw" — they
   throw. A4: other index / exception / frame — none; intermediate spread — none; errors — none. Cluster: "held near
   64 KiB or limit message appears" (Refuted) — 134 MB aggregated, 0 messages in all logs. "Control does not cap" (Not
   confirmed) — it capped at exactly 32 MiB. "Aggregation not SUCCEEDED in A runs" — all SUCCEEDED. B: "no merge lines" —
   8 merges after A11; "limit message / EOFException in B" — 0, job SUCCEEDED.
5. **Observed vs. inferred.** (a) The 3,920 B `writeAlloc` is the exception, not buffer growth (inferred from its
   constancy across arms; strong). (b) Retention equals allocation, since the array is the stream's only buffer (B2d,
   inferred; not measured). (c) Line 91 executes for every key the NM aggregates (`LogKey.write` → `writeUTF` →
   `write(byte[],int,int)`), inferred from the code path, as A8 names; the cluster tier does not depend on it for its
   claim (disk not bounded by the check), only for relevance.
6. **Deviations and gaps.** A1/A5 prebuilt artifacts and distribution; A9 node `pc91`; cluster tier restarted once after
   defect 1 (attempt 0's A/control readings agree with the restart's to within 56 B per app, but only the restart is
   evidence). Not tested: the A3 step 5 behaviour (an `EOFException` in `TFile.append` leaves an unreadable file) and the
   streaming path past the limit inside the NM — production keys never reach 64 KiB (A10). Workload B shows the shuffle
   caller's `write` path ran without hitting the limit; it does not measure reducer heap.
7. **Core question.** Usage does not follow the constraint. The heap of a `BoundedByteArrayOutputStream` is fixed by its
   capacity at construction (1,048,624 B for three limits, while capacity itself moves it 65 KB → 16.8 MB), and writing
   up to and past the limit allocates nothing but the exception (parts 3, 4); disk on the TFile path grows linearly with
   the data (×2 per worker byte, 134 MB at 64 MiB per container) and is not held near 64 KiB, while a real cap — the
   HDFS space quota — does bind the same workload at 32 MiB (parts 1, 3). So the line-91 check (`MAX_KEY_SIZE`)
   only bounds a write position inside a pre-allocated buffer; it caps neither heap nor disk.

**Conclusion (one line):** Unit — B2g row 1 (+ U5 linear row) — **Confirmed** (does not cap). Cluster — B3g row 1 —
**Confirmed** (does not cap; disk only, A10).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`python3 -I harness/selfcheck.py run1` re-parsed the raw surefire output and the cluster log's IFCHK lines:
60 PASS, 1 FAIL (`run1/selfcheck.txt`). The FAIL is the script's own extra check "U2 lim=1024 writeAlloc < size at
EOF" (3,920 vs 1,000), which is stricter than B2g; handled in part 4. Then the raw files were re-opened by hand:

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `TestBoundedLimitMemory-output.txt` (instr line; frames `write:92` in U1, U2, U4); `org.apache.hadoop.io.TestBoundedLimitMemory.txt` 6/0/0; `cluster-run.log` (`jps` four daemons; `count -q` sequence 169,950,421 → 0 → quota 33,554,432 → used 33,554,432); `ds-*.status.txt`. |
| 2. Readings | yes | All five raw values equal in every median row (`ctorRaw`/`writeRaw`); 3,920 B in U2, U3, U4 alike. |
| 3. Matched row | yes | Every number in part 3 re-read from the IFCHK lines and `ds-*.hdfs-ls.txt`; slopes recomputed by hand (2.0000041, 2.0000072). |
| 4. Excluded rows | yes | `grep -c "Reach the limit of the buffer"` = 0 in all four daemon logs (`run1/daemons/`); `B.merge-lines.txt` has 8 "Initiating" and 8 completed lines; `ds-CTRL64M.status.txt` "Log Aggregation Status : FAILED". |
| 5. Observed vs. inferred | yes | (a) constancy re-checked across 9 arms; (b), (c) are named inferences, not load-bearing for "does not cap". |
| 6. Deviations and gaps | yes | Attempt 0 kept under `run1/attempt0-runbook-defect/`, labelled not evidence; A10 gap stated. |
| 7. Core question | yes | Follows B1: heap flat in `limit` with the capacity control moving; disk linear in data with the quota control binding. |

### 5.2 Run 2?

**No** — 2026-11-25. Both tiers rest on direct observations (exact allocation counts, file lengths, HDFS byte counts,
quota exceptions), every self-check part holds, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — not done

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap on both tiers).

**Claim tested (B1):** The limit checked at `BoundedByteArrayOutputStream.java:91` (for TFile, `MAX_KEY_SIZE` = 64 KiB)
does **not** govern memory or disk usage: the heap taken by a `BoundedByteArrayOutputStream` equals its construction
`capacity` and does not change with `limit` or with the bytes written up to and past the limit, and the disk written
through the TFile path (YARN aggregated logs) follows the data volume, not the 64 KiB limit.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 + U5 linear row (`ctorAlloc` 1,048,624 B at `limit` 1 KiB / 512 KiB / 1 MiB; `writeAlloc` flat 3,920 B; U3 65,584 / 1,048,624 / 16,777,232 B; EOF at `write:92`; U5 131,092 B per record) | does not cap | run 1 + self-check | 2026-11-25 |
| Cluster | Confirmed — B3g row 1, disk only (A10) (aggregated 2,124,024 / 33,581,369 / 134,245,028 B for N = 1 / 16 / 64 MiB, slope 2.00; 0 limit messages; quota control held at 33,554,432 B, FAILED, 12 `DSQuotaExceededException`) | does not cap | run 1 + self-check (after one restart for runbook defect 1) | 2026-11-25 |

**Positive control:** unit — U3 (allocation follows capacity: 65,584 → 16,777,232 B) and U3b (an unbounded stream
allocates 523,480 B for 204,800 written); cluster — the 32 MiB HDFS space quota on the same workload held the
aggregated file at exactly 33,554,432 B (vs 134,245,028 B without it).

**Feedback filed:** `case-amended.md` — amendments A9, A10 (audit, attempt 2), A11 (runbook defect 1) and section D
(D1a, D1b, D2). Not written to the repository (this run was told not to edit it); to file: copy `case-amended.md` over
the case file, this file to `hadoop/stage4-runtime-verification/jingsong/results/MAX_KEY_SIZE-write-limit-2--autonomous.md`,
`run1/` to `results/MAX_KEY_SIZE-write-limit-2--autonomous/run1/`, `harness/` to
`harness/MAX_KEY_SIZE-write-limit-2--autonomous/`; update the `_INDEX.md` row (stage 4: Confirmed — does not cap, unit +
cluster, TN; sha256 `8d9cd92e…`), `queue.csv` order 6, `FLOWCHART.md` counts, and `case-notes.md` (lesson: MapReduce
shuffle/merge logging is in `syslog.shuffle`).

**Notable findings.**
- TFile disk amplification with large keys: with `minBlockSize` ≤ the record size every record closes a block and the
  index stores that block's last key, so a file of 64 KiB keys is about twice the key bytes (U5: 131,092 B per
  65,536-byte key; `TFile.java:653-666`, `:2272-2289`). Not a capacity-check issue; a doc/upstream note at most.
- Log aggregation under a space quota leaves the partial `<node>.tmp` file (here exactly the 32 MiB quota) in HDFS and
  reports FAILED (`ds-CTRL64M.hdfs-ls.txt`); the quota is consumed by an unreadable file until retention removes it.
- Memory holders worth an OOM look: none from this check — the two 64 KiB key buffers per `TFile.Writer` are fixed; the
  NM's old generation stayed ≤ 23.7 MB while aggregating 134 MB (`jstat-nm-A64M.txt`).

**Left on the node `pc91`:** `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-2-run1/` with `logs/` (unit, cluster,
gzipped daemon logs, attempt-0 logs), `conf/` and `harness/` — 1.5 MB in all. No process running (checked at release);
the PID file `/mydata/s4/DRIVER-jingsong-h6.pid` removed; the lock `/mydata/s4/NODE-LOCK` released at 10:18:48 MST.
