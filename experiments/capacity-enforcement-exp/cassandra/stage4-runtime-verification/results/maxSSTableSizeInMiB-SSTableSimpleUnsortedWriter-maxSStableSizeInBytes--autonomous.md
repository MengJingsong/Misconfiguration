# maxSSTableSizeInMiB-SSTableSimpleUnsortedWriter-maxSStableSizeInBytes--autonomous — stage-4 results

> **Case:** `experiments/capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/maxSSTableSizeInMiB-SSTableSimpleUnsortedWriter-maxSStableSizeInBytes--autonomous.md` (extension set, `writeup-set-ext.csv` order 116)
>
> **Status:** verdict filed (run 1 + self-check; no run 2), 2026-11-25, Jingsong (AI session). Not filed in the repository: this file, the harness and the amended case file are outside the repo (`~/writeup-ext/out/o116/`).
>
> **Outcome class:** **undetermined** (direction: caps) — estimate `positive`; unit tier **Partly confirmed — caps** (one heap sample 0.16 MiB over its frozen two-buffer bound), cluster tier **Not confirmed (no matching row)**. The weak-class rule needs a unit tier that is Confirmed or Refuted, so the case stays undetermined; see §8 for the two override paths.
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit), B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.
>
> **Attempt.** This is the second attempt. The first (2026-11-25, node `pc99`, x86_64) did the audit (S4-A1–A3) and wrote the
> harness but never ran: the `pc99` lock was stale (its stub is kept as `harness/prev-session/results-blocked-stub.md`). This
> attempt runs on **`ms0640` (Utah m400, aarch64)**, not `pc99`. The earlier audit and harness were re-reviewed before any
> reading; S4-A4 adds the node and runbook fixes. Nothing in this file outside §1 and §2 was written before the readings existed.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed version: repository commit `bef6bc8a6` (repo HEAD `8bd1dfb31`; the repo copy is unchanged since), sha256 `1299399de7b8a1bf8f790f6d02693f64e16f6417ca3086dd5cb238014373173b` (= `harness/case-as-filed.md`). Amended working copy `case-amended.md` with S4-A1–A3 (first session) and S4-A4 (this session), all dated 2026-11-25 and made before any reading: **frozen sha256 `06b37859a59b43e4ac631788f1e709b716753604db2b704a1bb1a3a9632d486d`**. Frozen predictions and conclusions tables (B2f, B2g, B2h, B3f, B3g, B3h and the verdict labels S4-A1–A3), extracted verbatim to `harness/freeze-pred.txt`: **sha256 `8871e3e867fa7910e65353cd16ecc3c9dab2fe03ce2a27551c1b04b66004f29e`** (unchanged from the first session's freeze; S4-A4 touches no prediction or conclusion). Both in `harness/freeze.sha256`. Section D will take the feedback after the run, so the file's hash changes then; the freeze is the value above. |
| **Harness** | `~/writeup-ext/out/o116/harness/` (outside the repo, not committed): `MaxSSTableSizeProbeTest.java` (B2a + S4-A1(b)(c); `.filed.java` is the verbatim B2a listing), `BulkProbe.java` (B3a verbatim), `setup.sh`, `node-commands.sh` (lock, launch, cleanup as run), `unit-all.sh` (B2e + S4-A4(b)), `cluster-all.sh` (B3e + B4 stop + S4-A1(d), S4-A4(c)(d)(e)), `analyze.py` (S4-A2/A3 criteria, evaluated mechanically), `md5.txt`. Previous session's lock script and hashes in `harness/prev-session/`. |
| **Tiers and values** | Unit (B2): U1, U4, U16, U64 (knob 1/4/16/64 MiB), Udef (unset), U0 (0), Uinf (1024), S16/S64 (sorted control), Ubig (one-row overshoot), Udel (DELETE bypass); 147,456 × 1 KiB rows. Cluster (B3, client-process tier): BulkProbe 524,288 × 1 KiB rows at knob 16/64/unset(128)/256 with `-Xmx2g`, OOM pair 16 and 256 at `-Xmx256m`, then `sstableloader` of the m16 output into one real node. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 (S4-A1–A3 of the first session kept after review; S4-A4 added). |

### 1.1 Design audit

Re-done critically in this session against the case text (`case-amended.md`) and the repo source.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | client JVM heap held by the unsorted buffer, and bytes per `Data.db` (A2, B1) |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | unit 1/4/16/64/unset/0/1024; cluster 16/64/unset/256 (B2b, B3b) |
| A. Core question | real resource measured, not only the counter (gap named) | Met | counter `currentSize` by reflection **and** retained heap after GC, `Data.db` lengths (B2d); GC log post-GC heap, RSS, OOM exit, files (B3d). Gap named in B3d: young-pause "after" figures include old-region garbage. |
| A. Core question | usage driven to the limit and past it | Met | ~146 MiB unit / ~520 MiB cluster serialized; 0–146 hand-offs; Uinf/OOM pair as positive controls (B2c, B3c) |
| B. Logic | each step says what it establishes | Met | B2g/B3g rows state each reading's meaning |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f exact limits, hand-off/file ranges, size bands, heap ratios; S4-A2/A3 make every band a mechanical check |
| B. Logic | every plausible outcome has a conclusions row | Partly | exceed-limit, flat, counter-vs-heap, limit-never-reached, bypass rows present; some mixed outcomes (e.g. file count out of range alone) have no row and fall to "Not confirmed (no matching row)" — acceptable |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | `sync=` hand-offs (disallow branch, :110 → `sync()`) plus heap/file sizes following L (S4-A2 core criteria) |
| B. Logic | alternative explanations and their controls | Met | sorted writer (no buffer), Uinf/x256 (workload can exceed), compression off, fresh blob per row (B2h, B3h) |
| C. Specific | a human can follow it from the intro and B1 | Met | |
| C. Specific | an AI can run B2e/B3e without re-deriving | Met | full listings and commands |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after S4-A1/A4 | Ubig sync detection and Uinf heap sampling were not observable as filed (S4-A1(b)(c)); no stop/timeout for an OOM JVM held by the non-daemon `DiskWriter` (S4-A4(c)) |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ms0640:/mydata/s4/cassandra-base` complete and built; JDK 11.0.33, Ant 1.10.12, python3 3.10.12 |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | unit ≤ ~150 MiB per run (deleted per run); cluster ≤ ~560 MiB per run + ~1.1 GB for the load; 17 GB free on `/mydata`; heaps ≤ 2 GiB on a 62 GiB node |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `SSTableSimpleUnsortedWriter.java:68` (`newBlockingQueue(0)`), `:74` (limit), `:85-91` (header counted, no check), `:103`, `:108-111` (check → `sync()`), `:126-131`, `:153-161` (`sync` resets `currentSize = 0`), `:206-237` (`DiskWriter`, a non-daemon `FastThreadLocalThread`); `CQLSSTableWriter.java:131-138` (client init), `:395`, `:407`, `:536-546` (non-positive warning), `:677-680` (default 128 unsorted / −1 sorted), `:738-740`; `BlockingQueues.java:43-47` (`SynchronousQueue`); `build.xml` `testsome` `maxmemory="1024m"`, `test.timeout` 480000, `${test.jvm.args}` — all read in the repo source, files md5-identical on the node |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Paths on the node, cp of the built base (S4-A1(a)) | Applied (S4-A1, first session; S4-A4(a) node `ms0640`) | B2a's `rsync` + `ant jar` would rebuild what is already built |
| 2 | Ubig sync detection: `now == 0` after a hand-off when the previous sample was also 0 (S4-A1(b)) | Applied (S4-A1) | as filed Ubig would print 0 `sync=` lines although B2f predicts 5 — an instrument fault, not a reading |
| 3 | Quarter-point heap samples in unsorted runs so Uinf's heap is observable (S4-A1(c)) | Applied (S4-A1) | the B2f/B2g Uinf cells were unobservable as filed |
| 4 | Node start safety: `ulimit -n`, capped `UN` wait (S4-A1(d)) | Applied (S4-A1) | soft limit is 1024 on `ms0640` too |
| 5 | Verdict labels mapping B2g/B3g rows to Confirmed / Partly / Refuted / Bypass / Not confirmed (S4-A2, S4-A3) | Applied (first session), reviewed and kept | the filed tables give meanings, not verdict words |
| 6 | `-Dtest.timeout=1800000` for `testsome` (S4-A4(b)) | Applied | 480 s default could kill a run on the slower m400 core |
| 7 | Watchdog for client JVMs: kill > 1800 s, or 60 s after `OutOfMemoryError` while alive (S4-A4(c)) | Applied | `DiskWriter` is non-daemon (`:206`), so an OOM in `main` might never exit |
| 8 | `logback-tools.xml` for BulkProbe (S4-A4(d)) | Applied | without a config logback logs DEBUG to stdout; logging only |
| 9 | `storage_compatibility_mode: NONE` on the load node; stop if the loader streams nothing (S4-A4(e)) | Applied | environment.md §6 (2026-11-25): `oa` files may be silently rejected at `CASSANDRA_4` |
| 10 | B3's "peak post-GC heap" takes young-pause figures, which include old-region garbage under G1 at `-Xmx2g`; the ladder may track GC heuristics rather than the buffer. A forced-GC live-heap sample (as in orders 114/115) would measure the buffer directly | left for stage 3 | changing the observable would change B3f/B3g; the OOM pair (x16/x256) remains the decisive reading, as B3d says |
| 11 | B3f gives per-file bands and the x16/x256 split but no row for "file counts out of range, all else as predicted" | left for stage 3 | such an outcome is "Not confirmed (no matching row)" |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 |
| Node | `ms0640` = `node1.jason92-326377.misconfiguration-pg0.utah.cloudlab.us` (Utah m400), **aarch64**, 8 cores, 62 GiB RAM |
| OS / kernel | Ubuntu 22.04.1 LTS / `5.15.0-191-generic` |
| JDK / Ant | OpenJDK 11.0.33 (2026-10-20) / Ant 1.10.12 |
| Local source copy | `/mydata/jingsong-cass-s4/o116/src` = `cp -a /mydata/s4/cassandra-base` (built 5.0.9 copy); cited files md5-identical to repo `systems/cassandra/source/` at `8bd1dfb31` |
| Case-file commit / harness | `bef6bc8a6` + S4-A1–A4 (frozen sha256 `06b37859…486d`) / harness outside the repo, not committed |
| Storage for run data | local `/mydata` (`/dev/mapper/emulab-node1--bs`, 39 GB, 17 GB free at start), `/mydata/jingsong-cass-s4/o116/` |
| Full logs | `~/writeup-ext/out/o116/run1/` (`setup.log`, `unit-CHK-driver.log`, `unit/`, `cluster/`, `analysis/`); on the node `/mydata/jingsong-cass-s4/o116/{logs,harness,run/u,run/p}` (836 KB, small files only) |
| Node lock | `/mydata/s4/NODE-LOCK` on `ms0640` acquired 2026-11-25 10:00:04 MST, released 10:16:43 MST; detached drivers' PIDs in `/mydata/s4/DRIVER-jingsong-c116.pid` (unit 732007, cluster 733296), both exited by themselves, file removed |
| Run times | setup 17:02–17:05Z (build-test exit 0); CHK 17:05Z; unit 17:06–17:10Z; cluster 17:10–17:14Z |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D0 | before run 1 | harness, carried over from the `pc99` attempt | staged the harness through `/tmp/o116-harness/`; no timeout for `testsome` on the slower m400; no watchdog for an OOM client JVM; no `storage_compatibility_mode` for the load node | S4-A4 (a)–(e) | 2026-11-25, before any reading | S4-A4 in `case-amended.md` (frozen sha256 `06b37859…486d`) |
| D1 | run 1, cluster load step | S4-A4(e) check line in `cluster-all.sh` | `sstableloader --no-progress` prints no summary, so the check's grep printed `LOADER-STREAMED-NOTHING` although streaming worked (the line only echoes; it stops nothing) | none needed: the loader log lists all 33 `Data.db` files streamed (`run1/cluster/loader.log`), and the node shows 34 SSTables, 548,463,566 B live, `count(*)` = 16 for k = 0 and k = 32767 (`node-tablestats.txt`, `node-cqlsh.txt`). Recorded, not re-run | 2026-11-25; B3f/B3g unchanged; row 7 concerns the load step only | harness only |

Instrument check (before run 1, `run1/unit-CHK-driver.log`): `-Dprobe.mib=1 -Dprobe.rows=4096` → `limitBytes=1048576`, 4 `sync=` lines (each `preSyncSample` 1,047,843–1,047,869, `maxIncrement` 1,067, i.e. at the first crossing), 5 `Data.db` — the known answer. `BulkProbe` compiled (`setup.log`, `javac exit=0`).

## 4. Run 1

**Scope:** all of B2 (11 runs) and B3 (6 client runs + m16 rerun + load step), as frozen. Command logs (`set -x`): `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`. Mechanical evaluation of the frozen S4-A2/A3 criteria: `run1/analysis/analyze-all.out` (59 PASS, 6 FAIL).

### 4.1 Readings

**Unit tier** (`run1/unit/<run>.probe.txt`; every test `Tests run: 1, Failures: 0, Errors: 0`, `<run>.test.xml`)

| Run | limitBytes | `sync=` | files | `preSyncSample` min–max / `maxCurrentSize` | non-last `Data.db` | retained heap (samples) |
|---|---|---|---|---|---|---|
| U1 | 1,048,576 | 146 | 147 | 1,047,843–1,047,869 / 1,047,869 | 1,050,957–1,050,968 (1.0023 L) | not judged |
| U4 | 4,194,304 | 36 | 37 | 4,193,454–4,193,480 / 4,193,480 | 4,202,784–4,202,795 (1.0020 L) | 4.6 / 14.4 / 14.6 MiB; r = 1.152 |
| U16 | 16,777,216 | 9 | 10 | 16,776,887–16,776,913 / 16,776,913 | 16,811,114–16,811,125 (1.0020 L) | 19.9 / 45.1 / 20.5 MiB; r = 1.244 |
| U64 | 67,108,864 | 2 | 3 | 67,108,563–67,108,589 / 67,108,589 | 67,242,357–67,242,368 (1.0020 L) | 79.2 / **166.6** MiB (bound 2 r L + 8 MiB = 166.4); r = 1.238 |
| Udef | 134,217,728 | 1 | 2 | — / 134,217,126 | 134,483,670 | 158.3 MiB |
| U0 | 134,217,728 | 1 | 2 | — / 134,217,126 | 134,483,670 | 158.2 MiB |
| Uinf | 1,073,741,824 | 0 | 1 | — / 153,741,312 | (one file) 154,045,440 | quarters 47.7 / 95.4 / 143.2 MiB |
| S16 / S64 | (sorted writer) | — | 10 / 3 | — | 16,781,860 / 67,110,725 | `sortedHeap` 3.4–3.7 MiB both |
| Ubig | 1,048,576 | 5 | 5 | — / 0 | 5 × 3,145,763 (3.0 L) | not judged |
| Udel | 1,048,576 | 0 | 1 | — / 13,000,000 (12.40 L); `maxIncrement` 26 | 11,500,000 | not judged |

`maxIncrement` 1,067 B in every 1 KiB-row run; `maxCurrentSize` ≤ L in every INSERT run with a limit.

**Cluster tier — client process** (`run1/cluster/<name>.out`, `data-<name>.txt`, `peak-<name>.txt`, `gc-<name>.log`, `rss-<name>.txt`; m16 = the first run, `*-m16-first.*`)

| Run | -Xmx | exit | files | non-last `Data.db` | peak post-GC (pause) | `du -sb` | RSS max |
|---|---|---|---|---|---|---|---|
| m16 | 2g | 0, `BULK done` 17.7 s | 33 | 16,811,114–16,811,125 (16.03 MiB) | **382 MiB** (Young Normal, 625M→382M) | 548,521,159 | 780 MiB |
| m64 | 2g | 0, 14.8 s | 9 | 67,242,368 (64.13 MiB) | 543 MiB (Young Concurrent Start, humongous) | 548,383,212 | 875 MiB |
| mdef | 2g | 0, 15.0 s | 5 | 134,483,681 (128.25 MiB) | 544 MiB (same) | 548,307,612 | 874 MiB |
| m256 | 2g | 0, 17.1 s | 3 | 268,967,340 (256.51 MiB) | 709 MiB (same) | 548,286,903 | 1,039 MiB |
| x16 | 256m | **0**, `BULK done` 17.4 s | 33 | as m16 | 168 MiB | 548,521,157 | 378 MiB |
| x256 | 256m | **1**, `java.lang.OutOfMemoryError thrown from the UncaughtExceptionHandler in thread "main"`, 30 Full GCs | 0 | — | 256 MiB | 12,288 | 385 MiB |
| m16 rerun | 2g | 0, 17.3 s | 33 | as m16 | 296 MiB | 548,521,163 | 733 MiB |

No Full GC in any 2g run; the heap never grew past 1,004 MiB committed. Watchdog never fired. Load step: `storage_compatibility_mode: NONE` set (`cluster-run.log`, `subs 1 1 1 1 1 1 1 1`), node up, `sstableloader` exit 0 streaming the 33 `Data.db` files (`loader.log`), `tablestats`: SSTable count 34, Space used (live) 548,463,566, partitions (estimate) 33,250; `count(*)` = 16 for k = 0 and k = 32767 (`node-cqlsh.txt`); 0 `ERROR` lines in `node-system.log`.

### 4.2 Conclusion and logic

1. **Validity.** Valid. The limit was crossed 146/36/9/2/1 times in U1–Udef and 33/8/4/2 times on the client tier [observed: `*.probe.txt`, `data-*.txt`]; same rows, seed and schema in every run (identical total `Data.db` 154,045,440 B in Uinf/S16/S64 and `du` within 0.043 %) [observed]; compression off (schema in the harness); instrument check exact [observed: `unit-CHK-driver.log`].
2. **Readings.** (a) U64 heap sample 2 = 174,659,712 B, 164,512 B over 2 r L + 8 MiB = 174,495,200 B [observed: `U64.probe.txt`]. (b) Every `Data.db` is 1.0020–1.0023 × its buffer's operand, in the unit and client tiers alike, and also in Uinf with no hand-off at all (154,045,440 B on disk for an operand of 153,741,312 B, +0.198 %) [observed: `U*.probe.txt`, `data-*.txt`]. (c) peak(m16) = 382 MiB vs < 150 predicted; the identical rerun gave 296 MiB; x16 completed the same workload in a 256 MiB heap with a peak of 168 MiB [observed: `peak-*.txt`, `gc-*.log`]. (d) m64 and mdef peaks differ by 1 MiB (543 / 544).
3. **Matched row.**
   - *Unit:* S4-A2 core criteria: every count/file criterion holds (limit = L; `sync=` 146/36/9/2 in range; files = syncs + 1; every `preSyncSample` ≤ L < `preSyncSample` + 1,067; `maxCurrentSize` ≤ L; non-last files 1.0020–1.0023 L); r(U4) = 1.152 ∈ [1.1, 2.0]; r(U16), r(U64) within 8 % of r(U4); retained(U64) − retained(U4) = 74.6 MiB ≥ 8; controls hold (S16/S64 `sortedHeap` 3.4–3.7 MiB, means 3.5 vs 3.6; Uinf quarters 47.7 < 95.4 < 143.2 MiB, 143.2 > 79.2). One sample 2–3 exceeds 2 r L + 8 MiB (U64 sample 2). → S4-A2 **Partly confirmed — caps** (B2g row "more than two buffers live, or another consumer grows with the knob" fires numerically). Sub-findings, all as predicted: B2g row 2 (Udef/U0 `limitBytes` 134,217,728, 1 hand-off, 2 files); Ubig row (5 hand-offs, five 3,145,763 B files > L); Udel row (0 hand-offs, 1 file, `maxCurrentSize` 12.40 L) → **DELETE bypass confirmed**.
   - *Cluster:* S4-A3 core criteria hold except two: "no Data.db above L + 1,152 B" (every non-last file is 0.2 % above L) and "peak(m16) < 150 MiB" (382). The rest holds: file counts 33/9/5/3 in range; size bands; peak strictly increasing 382 < 543 < 544 < 709; peak(m256) ≥ 256; `du` spread 0.043 %; x16 exit 0 with `BULK done`; x256 exit 1 with `OutOfMemoryError`. Two labels fire numerically: **Bypass** (B3g row 6, "Any Data.db larger than the knob plus one row → check bypassed for INSERTs: claim wrong") and the conditions of **Partly confirmed — caps** (OOM split and per-file bands hold, Δpeak = 327 MiB ≥ 100, a B3f peak cell missed). Neither matches cleanly. Row 6's evidence (b) is present, but its meaning (rows counted without a check) is contradicted by direct operand readings of the same row shape: `maxCurrentSize` ≤ L and every hand-off at the first crossing in every unit INSERT run, and the same 0.2 % excess with no hand-off at all (Uinf). So the excess is the on-disk encoding versus the serialized count, not a bypass. Partly confirmed's list of allowed misses does not include the file-size criterion. → **Not confirmed (no matching row)**, direction caps.
4. **Excluded rows.** Unit: row 3 (hand-offs flat across the knob, or `preSyncSample` > L): no, 146 → 2 and all ≤ L. Row 4 (`maxCurrentSize` > L in an INSERT run): no, all ≤ L. Row 5 (U64 heap not above U4): no, +74.6 MiB. Row "Udel shows hand-offs": no, 0. Cluster: row 2 (x256 completes): no, OOM. Row 3 (x16 OOMs): no, exit 0. Row 4 (flat, Δpeak < 32 MiB): no, 327. Row 5 (total `du` changes with the knob): no, 0.043 %. Row 6 (Data.db > L + one row): fires numerically; its meaning is excluded by (b), as in part 3. Row 7 (load fails or counts differ): no, counts 16 / 16.
5. **Observed vs. inferred.** (i) The Data.db excess is encoding, not unchecked rows [inferred from observed (b) plus unit `maxCurrentSize` ≤ L; it decides that cluster row 6 cannot be the verdict]. (ii) The U64 sample-2 excess is two buffers plus ≈ 8.2 MiB of other writer state (the `DiskWriter`'s `SSTableTxnWriter`, A4), not a third buffer [inferred: 166.6 ≈ 2 × 79.2 + 8.2; a third buffer would need ≥ 237 MiB]; not used to change the label. (iii) peak(m16) = 382 is mostly uncollected garbage in old regions after young pauses (the gap B3d names) [inferred from observed (c): no Full GC; 296 on the identical rerun; 168 at `-Xmx256m`]; not used to change the label.
6. **Deviations and gaps.** None from the frozen runbook (S4-A4 applied before reading). D1: the S4-A4(e) check line was wrong, but streaming is shown by the loader log and the node. B3's heap observable (young-pause figures) cannot separate the buffer from garbage; the OOM pair is the decisive heap reading.
7. **Core question.** The check at `SSTableSimpleUnsortedWriter.java:110` uses the line-74 value exactly as traced. The operand never passes L, a hand-off fires at the first row that crosses it, the number of hand-offs and the size of each file follow the knob over 1–1024 MiB, and the default and 0 both give 128 MiB (parts 3, 4). Buffer heap follows the knob linearly (r ≈ 1.15–1.24 per buffer; Uinf grows with rows while U64 stays bounded), and at a fixed 256 MiB heap the knob alone decides whether the same bulk load completes (x16) or dies of OOM (x256). So the knob caps the writer's heap and each SSTable's size, with a soft overshoot of one row (Ubig) and an unbounded bypass for partition-DELETE-only workloads (Udel). The formal verdicts fall short of Confirmed only because of the frozen heap and file-size thresholds noted in part 2.

**Conclusion (one line):** unit — S4-A2 **Partly confirmed — caps** (DELETE bypass confirmed; default/overshoot sub-findings as predicted); cluster — **Not confirmed (no matching row)** (Bypass row 6 fires on a 0.2 % encoding excess that the operand readings show is not a bypass; peak(m16) 382 vs < 150 MiB), direction caps.

## 5. Self-check of run 1

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit-run.log` (11 × `ant exit=0`, `Tests run: 1, Failures: 0`), `unit-CHK-driver.log`, `cluster-run.log` (`CLUSTER-DONE`, no watchdog line), totals in `Uinf/S16/S64.probe.txt` (154,045,440) |
| 2. Readings | yes | `U64.probe.txt`: `heapSample=2 … retained=174659712`, sample 1 83,053,296 → bound 174,495,200 recomputed by hand; `Uinf.probe.txt` `endCurrentSize=153741312`, `data oa-2-big-Data.db 154045440`; `data-m16-first.txt` 16,811,114/16,811,125; `gc-m16-first.log` GC(12) `625M->382M`, `gc-m16.log` `554M->296M`, `gc-x16.log` max `172M->168M(256M)`, `Pause Full` count 0 in all 2g logs |
| 3. Matched row | yes, after one correction | Unit: re-read S4-A2. A sample 2–3 above 2 r L + 8 MiB is named there as a Partly-confirmed condition, so Partly confirmed — caps holds. Cluster: the first mechanical reading would have been "Bypass" (row 6). Checked against the audited logic, row 6's inference (Data.db > L + one row ⇒ rows counted without the check) does not hold, because the unit operand readings and Uinf contradict it. That part does not hold, so per the protocol the conclusion is downgraded, not fixed: **Not confirmed (no matching row)**. Partly confirmed was not substituted, because its allowed misses do not include the file-size criterion |
| 4. Excluded rows | yes | every B2g/B3g row addressed in 4.2 part 4 |
| 5. Observed vs. inferred | yes | inferred (i) is used only to exclude row 6, which leads to the more conservative verdict; (ii) and (iii) are not used for any label |
| 6. Deviations and gaps | yes | D1 re-checked against `loader.log` (33 `Data.db` names) and `node-tablestats.txt`, `node-cqlsh.txt` |
| 7. Core question | yes | the unit and cluster directions agree (caps); nothing contradicts the unit effect, so no "(cluster disagrees)" |

### 5.2 Run 2?

**No** (2026-11-25). The deciding readings are deterministic (counts, limits, file sizes, exit codes, the OOM split), and the misses are frozen thresholds that a repeat would not change. The one GC-dependent reading (peak) varies between identical runs (382 / 296 MiB), which a run 2 cannot settle either.

## 6. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **undetermined** (direction caps).

**Claim tested (B1):** for the unsorted `CQLSSTableWriter`, the value set at line 74 bounds the buffered data: every buffer hand-off happens when the serialized count first exceeds `knob × 2^20` bytes (so each SSTable's `Data.db` is at most the knob plus one row), and the heap retained by buffered rows grows linearly with the knob and stays within two buffers' worth; conversely, a partition-DELETE-only workload is not bounded by it.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Partly confirmed — caps** (S4-A2; B2g row 1 except one heap sample 0.16 MiB over the two-buffer bound; sub-findings B2g row 2, Ubig and Udel rows confirmed) | **caps (bypass recorded: partition-DELETE-only workloads)** | run 1 + self-check | 2026-11-25 |
| Cluster | **Not confirmed (no matching row)** (S4-A3: row 6 fires on a 0.2 % encoding excess that the operand readings show is not a bypass; peak(m16) 382 vs < 150 MiB; OOM split, file counts and sizes, ladder and totals as predicted) | undetermined (direction: caps) | run 1 + self-check | 2026-11-25 |

**Outcome class reason:** the weak-class rule (2026-10-29) applies only when the unit tier is Confirmed or Refuted; here it is Partly confirmed, and the cluster tier did not settle, so the case is **undetermined**. Override paths for the owner: (1) reading the unit tier's "Partly confirmed — caps" as settling the effect (its label carries Effect caps) gives **weak true positive**; (2) also reading the cluster tier as Partly confirmed — caps (its Bypass trigger is the encoding excess) gives **true positive**. This session takes neither, because the thresholds were frozen before any reading.

**Findings worth carrying forward:**
- **DELETE bypass confirmed at runtime:** 500,000 partition deletes buffered 13.0 MB of counted size (12.4 × a 1 MiB limit) with 0 hand-offs and one SSTable. `getUpdateFor` (`:85-91`) counts the partition but never calls `maybeSync()`. A DELETE-only bulk load holds the whole input in one buffer until `close()`: a heap-exhaustion (OOM) candidate for bulk-loading deletes.
- **Memory holder:** the unsorted buffer takes ≈ 1.15–1.24 × the knob in heap per buffer, and up to two buffers plus ≈ 8 MiB are live at once. At the default 128 MiB that is ≈ 158 MiB per buffer (Udef), ≈ 325 MiB at the hand-off, so the javadoc's "reasonable for a 1 GiB heap" holds, but `-Xmx256m` with a 256 MiB knob dies (x256).
- `withMaxSSTableSizeInMiB(0)` logs that it "disables the size limiting", but the unsorted writer applies 128 MiB (U0 = Udef).
- One row larger than the limit makes one SSTable of that row's size (Ubig: 3 MiB files at a 1 MiB limit): a soft cap.
- Each `Data.db` is ≈ 0.2 % larger than the counted serialized size (on-disk encoding). Any per-file bound stated as "knob + one row" in on-disk bytes is off by this amount.

**Feedback filed:** section D of `~/writeup-ext/out/o116/case-amended.md` (stage-4 feedback, 2026-11-25). Recommendations left for stage 3: §1 items 10–11, plus "state per-file bounds as a ratio (≈ 1.002 L), not L + one row". Not committed (this session does not edit the repo).

## Cleanup

All JVMs, ant runs, the Cassandra node and both detached drivers ended; `ps` on `ms0640` showed no process of this run (checked 10:16 MST), and none on this machine. Deleted on the node: `o116/src` (the `cassandra-base` copy with build output), `run/p/out-*` (SSTables), `run/node`, `run/conf`, the per-run SSTable dirs, the PID file. **Kept on `ms0640`, `/mydata/jingsong-cass-s4/o116/` (836 KB):** `harness/` (8 files), `logs/` (`build-test.log`, `unit-run.log`, `cluster-run.log`), `run/u/` (`*.probe.txt`, `*.ant.log`, `*.test.xml` for the 11 unit runs), `run/p/` (`BulkProbe.java`, `*.out`, `data-*.txt`, `peak-*.txt`, `gc-*.log`, `rss-*.txt`, `loader.log`, `node-system.log`, `node-tablestats.txt`, `node-cqlsh.txt`). `/mydata` free space back to 17 GB. Node lock released.
