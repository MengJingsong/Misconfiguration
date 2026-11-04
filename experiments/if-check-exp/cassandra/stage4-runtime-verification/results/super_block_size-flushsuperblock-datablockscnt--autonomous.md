# super_block_size-flushsuperblock-datablockscnt--autonomous — stage-4 results  <!-- file: results/super_block_size-flushsuperblock-datablockscnt--autonomous.md -->

> **Case:** [`super_block_size-flushsuperblock-datablockscnt--autonomous`](../../stage3-ai-deep-read/cases/super_block_size-flushsuperblock-datablockscnt--autonomous.md)
>
> **Status:** **Self-checked 2026-10-29 — unit Confirmed (does not cap), cluster Not confirmed (no matching B3g row; effect undetermined); no run 2.** Sub-predictions missed: live heap within 10 percent over the constants (13.1 percent), post-collection heap peaks separating the option from the constant
>
> **Outcome class:** undetermined — stage-3 estimate `negative`; the unit tier gives `does not cap`, the cluster tier could not settle the effect (Not confirmed) ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (U1-U4 in B2, C1-C5 in B3 or as listed, dated 2026-10-28), recorded before any reading: `eef62cc3d3b5720cf100e725329416d87d662c779697c266a44b5104a6f18d18` (unchanged by the runs until section D was filled). Repository HEAD of this session `b68711e` (working tree; case file, harness and results uncommitted). The frozen text is everything above section D. |
| **Harness** | `harness/super_block_size-flushsuperblock-datablockscnt--autonomous/` (see its README), uncommitted; written after the freeze. |
| **Tiers and values** | Unit (B2): constant 16 / 64 / 256 (overlay classes) x N = 50,000 / 200,000 / 400,000 SPARSE Int32 terms (plus 2,000 terms and PREFIX mode at 64; -Xmx2g and -Xmx64m at 200,000). Cluster (B3): option 8 / 64 / 512 at constant 64; constant 16 / 256 at option 64; PREFIX control; 5,000,000 rows. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2: tokens held in one in-heap super-block tree and layout padding; heap and file bytes are measured. |
| A | knob varied, 3 values incl. default | Met | 16/64/256 by recompiling the two classes (U2); the real cap option 8/64/512 as the contrast. |
| A | real resource measured | Partly | B2d(3) wall heap noise; live heap after System.gc() at the largest tree added (U2/U3); cluster: post-GC occupancy. |
| A | usage driven to the limit and past it | Met | 740 data blocks are many times 64; 5M terms cross the option. |
| A | positive control (negative file) | Partly | B2e(5) "-Xmx2g vs 64m" does not move usage with the data; N sweep added (U4); cluster: the option is the known cap. |
| B | prediction in numbers | Partly | "about 4x", "a few percent": numbers added (U3). |
| B | every outcome has a row | Met | B2g/B3g. |
| B | confirmation needs the disallow branch | Met | the true branch of line 497 counted (patched print + file tail). |
| C | knob, values, workload, commands exact | Partly | "default option" in B3e step 3 ambiguous; memtable settings; arms: C1-C3. |
| D | harness and prerequisites exist or are listed | Partly | written in step 1. |
| D | workload arithmetic reaches the limit | Met | U3: 740 blocks; cluster 5M rows, about 1 GB estimated per the file. |
| D | load-bearing citations spot-checked | Met | Checked in `cassandra/cassandra-5.0.9`: `OnDiskIndexBuilder.java:127-129`, `:165-195`, `:238-300`, `:410-519`, `:521-571`, `:575`, `:598`, `OnDiskIndex.java:346-375`, `PerSSTableIndexWriter.java:240-345`, `:365-369`, `IndexMode.java:58-60`, `:186-192`, `Config.java:606`; `MAX_KEYS_SPARSE` = 5 now verified. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Overlay classes for the constant, numbers, controls (U1-U4) | Applied 2026-10-28 | file asks for rebuilds; arithmetic |
| R2 | Memtable settings, arms, workload (C1-C3) | Applied | flush path ignores the option |
| R3 | For stage 3: the "default option" is 153.6 MiB (161,061,273 bytes) | left for stage 3 | IndexMode.java:60 |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | unit 2026-10-28 (node clock UTC 23:48-23:52); cluster 2026-10-29 (UTC 01:05 to 01:35, local MDT in `gc.log`) |
| Node | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-b34/c` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e` (`copy-source.sh`; `git describe` = `cassandra-5.0.9`), `ant build-test` BUILD SUCCESSFUL (1 min 7 s). The constant variants are overlay classes in `~/s4-b34/ov/` compiled from copies of `OnDiskIndexBuilder.java` / `OnDiskIndex.java` (line 129 changed; `javap -constants` in `~/s4-b34/ov/javap-*.txt`); the run copy's sources were not modified |
| Case-file / harness commit | uncommitted (working tree of `b68711e`); hash in section 1; harness md5s in `run1/harness.md5` |
| Storage for node data | `~/s4-b34/node-sb` on local `/dev/sda3` (removed after each arm); unit temp files in `~/s4-b34/tmp`; nothing under `/proj` |
| Full logs (outside the repo) | `pc29:~/stage4-logs/b34/superblock/run1/{unit,cluster/<arm>}/` (per arm: `system.log`, `gc.log`, `heap.csv` 200 ms, `disk.csv`, `classload.log` excerpt, `stress.txt`, `cmdlog.txt`) |

## 3. Runbook defects and harness defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | unit, one instrument check before the tier (N = 2,000, `ov64p`; output deleted) | harness | the file-tail parser read the super-block count but did not skip the offsets, so its `parsedToEnd` flag was false (8 bytes short) | `skipBytes` added; the check run again (`parsedToEnd=true`), then the whole unit tier run once | before run 1; no reading used |
| D2 | cluster analyzer | analyzer | `analyze.py` counted the words `OutOfMemoryError` in `system.log`, which also occur in the JVM-arguments line (`-XX:+HeapDumpOnOutOfMemoryError`), so the first arm showed "bad=2" | pattern changed to `java.lang.OutOfMemoryError` and `AssertionError`; the raw `log-errors.txt` was empty throughout | after the `o64c64` reading, disclosed |
| D3 | cluster self-check | harness | the first `selfcheck.py` looked for a "compact start" line the script does not print and expected `build/classes/` for the build's class (it is the jar) | the window is checked against the "flush done" line; the jar path accepted | 2026-10-29 (instrument only) |
| D4 | B3e step 3 / C3 | ambiguity | "at the default option" in the file; the middle value 64 was used for the constant arms | stated in amendment C3 before the freeze | 2026-10-28 |

No runbook defect stopped a tier. Shakedowns before run 1: only D1.

## 4. Run 1

**Scope:** all of B2 (constants 16/64/256 x N 50,000/200,000/400,000, repeats, 2,000 terms, PREFIX, unpatched controls, `-Xmx2g`/`-Xmx64m`) and the six B3 arms. **Command logs:** `super_block_size-flushsuperblock-datablockscnt--autonomous/run1/` (`unit/*.out`, `unit-summary.txt`, `cluster/<arm>/{cmdlog-head.txt,system-log-excerpt.txt,sizes.txt,classload-ondiskindex.txt,...}`, `cluster-analysis.txt`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/*.out`, `unit-summary.txt`; 512 MB heap, serial GC, N distinct Int32 terms, one key each; "live heap" = heap used after `System.gc()` at the largest super-block flush, printed by the patched overlay)

| Run | Data blocks | Super blocks (file tail; formula; prints) | Largest tree (tokens / bytes) | File bytes | Live heap at largest flush |
|---|---|---|---|---|---|
| constant 16, N = 200,000 (3 repeats) | 736 | 46 (46; 46) | 4,352 / 81,920 | 21,858,468 | 120.3 MB (all three within 0.01 MB) |
| constant 64, N = 200,000 (3 repeats) | 736 | 12 (12; 12) | 17,408 / 299,008 | 21,534,612 | 124.6 / 125.4 / 125.4 MB |
| constant 256, N = 200,000 (3 repeats) | 736 | 3 (3; 3) | 69,632 / 1,167,360 | 21,440,332 | 136.1 / 136.1 / 136.9 MB |
| constant 16 / 64 / 256, N = 50,000 | 184 | 12 / 3 / 1 | 4,352 / 17,408 / 50,000 | 5,461,568 / 5,375,480 / 5,350,888 | 46.0 / 48.9 / 52.0 MB |
| constant 16 / 64 / 256, N = 400,000 | 1471 | 92 / 23 / 6 | 4,352 / 17,408 / 69,632 | 43,700,508 / 43,040,500 / 42,876,524 | 218.4 / 224.5 / 241.2 MB |
| constant 64, N = 2,000 | 8 | 1 (only the forced final flush) | 2,000 / 45,056 | 233,576 | 21.6 MB |
| PREFIX mode, constant 64, N = 200,000 | 540 | no super blocks (-1; 0 prints) | - | 19,898,640 | - |
| patched overlay, unpatched overlay, pristine build, constant 64, N = 200,000 | 736 | 12 | - | 21,534,612 in all three | md5 `4fbcaa56c227309caeb3e1bac2b5e776` in all three |
| constant 64, N = 200,000, `-Xmx2g` / `-Xmx64m` (information) | 736 / - | 12 / run died with `OutOfMemoryError` | 17,408 | 21,534,612 / - | 125.2 MB / - |

Other: the class loaded for each run is the overlay (`PROBE ... source=file:/users/jason92/s4-b34/ov/ovNp/`) or the build's (`pristine`), and `SUPER_BLOCK_SIZE` read by reflection equals 16 / 64 / 256; the file-tail parse reached `fileLength - 8` exactly; super blocks = floor((data blocks - 1) / constant) + 1 in every SPARSE run.

**Cluster tier** (`run1/cluster/<arm>/`, `cluster-analysis.txt`; 5,000,000 rows, `-Xmx2G`, window = `nodetool compact` of 23 sstables into one; post-collection heap = the number after `->` of the G1 pause lines inside the window, parsed again by hand with a second script)

| Arm | Option (MiB) | Constant | Mode | Window (s) | Index segments in window | Post-collection heap in window: max (median) MiB | Sampled max heap used MiB | `Data.db` | `SI_t_v.db` | Class loaded from |
|---|---|---|---|---|---|---|---|---|---|---|
| `o8c64` | 8 | 64 | SPARSE | 116 | 137 | 844 (843) | 1846 | 84,384,923 | 537,376,860 | build jar |
| `o64c64` | 64 | 64 | SPARSE | 107 | 18 | 800 (799) | 1913 | 84,483,550 | 537,376,860 | build jar |
| `o512c64` | 512 | 64 | SPARSE | 123 | 3 | 1941 (76) | 1911 | 84,479,628 | 537,376,860 | build jar |
| `o64c16` | 64 | 16 | SPARSE | 105 | 17 | 327 (326) | 1909 | 84,460,231 | 545,616,708 | overlay in node conf |
| `o64c256` | 64 | 256 | SPARSE | 111 | 18 | 375 (370) | 1874 | 84,507,545 | 535,376,292 | overlay in node conf |
| `pfx64` | 64 | 64 | PREFIX | 94 | 18 | 1952 (399) | 1890 | 84,439,839 | 496,465,360 | build jar |

Stress: 0 errors, 75,708 to 88,696 inserts/s; no `AssertionError` or `java.lang.OutOfMemoryError` in any `system.log`; every arm ended with one sstable and no daemon.

### 4.2 Conclusion and logic

1. **Validity.** Valid for the structure and for the segment counts. The constant reached the node as intended in every arm [observed: `classload-ondiskindex.txt`: `OnDiskIndexBuilder` from the node's `conf/` for 16 and 256, from the build jar for 64]; the node settings were those of C1-C3 [observed: `yaml-lines.txt`: `memtable_heap_space`/`memtable_offheap_space` 256MiB, `compaction_throughput: 0MiB/s`; `proc-args.txt`: `-Xmx2G`]; the unit overlays gave the loaded `SUPER_BLOCK_SIZE` 16 / 64 / 256 [observed: `unit/*.out`]; no leftover daemon [observed]. The heap reading is **not** valid as a separator (part 6): one run per arm.
2. **Readings.** Unit: (a) super blocks = floor((736 - 1) / constant) + 1 = 46 / 12 / 3 exactly, read from the file tail and from the patched print; the largest tree holds 4,352 / 17,408 / 69,632 tokens (constant x about 272 terms per block) and 81,920 / 299,008 / 1,167,360 bytes [observed]. (b) File bytes differ by 1.95 percent across the constants (21,858,468 / 21,534,612 / 21,440,332) and are byte-identical between repeats [observed]. (c) The live heap at the largest super-block flush is 120.3 / 124.6 / 136.1 MB: a spread of 13.1 percent against the 10 percent of U3 [observed: **sub-prediction missed**]; the 15.8 MB difference between constants 16 and 256 is 242 bytes for each of the 65,280 extra tokens of the larger tree [derived from `unit-summary.txt`; the per-token cost is the quotient, not a separate measurement], and it rises with N at every constant (46 to 52 MB at 50,000 terms, 218 to 241 MB at 400,000) [observed]. Cluster: (d) the option sets the number of index segments in the compaction: 137 / 18 / 3 for 8 / 64 / 512 MiB [observed]; the constant does not: 17 / 18 / 18 for 16 / 64 / 256 [observed]. (e) `SI_t_v.db` bytes are identical (537,376,860) for the three options and differ by 1.5 percent / -0.4 percent for constants 16 / 256 (padding of more or fewer super blocks) [observed]; `Data.db` is 84.4 to 84.5 MB in all arms. (f) The post-collection heap in the window is 844 / 800 / 1941 MiB for 8 / 64 / 512 MiB and 327 / 800 / 375 MiB for constants 16 / 64 / 256; the `pfx64` arm (no super blocks, option 64) reaches 1952 MiB. Within an arm the post-collection occupancy is nearly constant (median 843, 799, 326, 370 MiB), except where the build briefly holds a large builder (`o512c64`: median 76, 90th percentile 1897; `pfx64`: median 399, 90th percentile 912) [observed]. [inferred: the retained heap differs by 300 to 500 MiB between runs of the same option for reasons unrelated to the knobs (GC sizing, memtable remnants), which is larger than the 8 to 64 MiB step in the option, so one post-collection peak per arm cannot separate the option from the constant except at 512 MiB.]
3. **Matched row.** Unit B2g row 1 "Super block count scales inversely with the constant, heap peak and file size nearly flat -> claim confirmed" (46 / 12 / 3; file 1.95 percent; live heap 13 percent over a 16 x range), with row 3 "Heap peak and file size rise with N at every constant -> positive control moved" [observed]. Cluster: **no row of B3g is matched** by the heap readings. The first row needs "peak heap moves with the option and not with the constant"; the option moved the segment count (137 / 18 / 3) but the heap peak only at 512 MiB (844 vs 800 at 8 vs 64 MiB, and the constant arms 327 / 375 against 800 are as far from the base as the options are), so the rule written before the cluster tier ("range over the constants < 0.25 x range over the options") fails (473 vs 0.25 x 1141) [observed]. "Heap peak moves with the constant" is excluded (327, 800, 375: not monotone). The reading is therefore **Not confirmed (no matching row)** for the cluster tier.
4. **Excluded rows.** Unit: "Heap peak falls about in proportion when the constant falls": no (13 percent over 16 x); "super block count does not change with the constant": no; "heap peak not measurable above GC noise at N = 200,000": the live-heap reading is after `System.gc()`, so it is measurable (the three repeats differ by under 1 MB) [observed]. Cluster: "peak heap moves with the constant": no; "index size differs by more than padding across constants": no (1.9 percent) [observed].
5. **Observed vs. inferred.** Inferred: the cause of the run-to-run level of the retained heap (part 2f), and that the constant's tree is the whole of the heap difference between constants in the unit tier (the per-token cost is a quotient of that same difference, not an independent measurement). The unit verdict does not depend on either; the cluster "Not confirmed" does depend on the heap reading being too coarse.
6. **Deviations and gaps.** The constant was varied by overlay classes, not by `ant jar` (U2); the cluster arms use the constant-only overlay (no print), so super-block counts are not observed on the node (B3d says they cannot be); the heap is a single post-collection maximum per arm and a 200 ms sampled maximum that sits at the heap cap in every arm (1846 to 1913 MiB), so neither separates the option from noise at 8 vs 64 MiB; one run per arm; the flush path of the index uses a fixed 1 GiB budget, and memtables were set to 256 MiB (C1) to keep it small; the SPARSE index on a random int has one key per term, so the super-block trees hold at most about 272 x constant tokens. No second run was made (the protocol allows one).
7. **Core question.** The unit tier shows the constant sets only the grouping: the number of super blocks falls as 1 / constant, the transient in-heap token tree holds about 272 x constant tokens (serialized 0.08 / 0.3 / 1.2 MB; in the heap about 1 / 4 / 17 MB at 242 bytes per token) and is released after each flush, the file size moves by under 2 percent, and the live heap tracks N (the terms map), not the constant. The cluster tier agrees on every deterministic observable (segments follow the option and not the constant; index bytes within 1.9 percent over the constants; no failure) but its heap-peak reading does not meet the frozen row, so the cluster tier does not settle the question on its own.

**Conclusion (one line):** Unit B2g row 1 (with row 3) - confirmed (does not cap; the 10-percent live-heap sub-prediction missed at 13.1 percent); Cluster B3g - Not confirmed (no matching row: post-collection heap peaks are not separable from run-to-run level; segments and index bytes agree with the claim).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-29: `unit/*.out` and `*.log` and every cluster arm's raw files re-parsed by `harness/.../selfcheck.py` (`run1/selfcheck.txt`: 53 PASS, 0 FAIL; it recomputes the super-block formula, the printed-flush counts and the md5 comparisons from the raw files; its one heap check is deliberately loose, "spread under 25 percent", and states that the 10 percent of U3 is not met) and, by hand, the six `gc.log` files (second script: per-arm maxima 844 / 800 / 1941 / 327 / 375 / 1952 MiB confirmed, with medians), `cluster/*/classload-ondiskindex.txt`, `cluster/o8c64/system-log-excerpt.txt` (segment lines) and `ps` on the node.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes for structure and counts; the heap reading is not a separator | class sources; `yaml-lines.txt`; 0 daemons. |
| 2. Readings | yes | `selfcheck.txt`; the 13.1 percent recomputed from `sp16/64/256-n200000-r1.log` `SBFLUSH liveHeap` maxima; segments recounted from `system.log` with a second parser (137 / 18 / 3 / 17 / 18 / 18). |
| 3. Matched row | yes | unit rows 1 and 3; cluster "no matching row" because the pre-registered rule fails. |
| 4. Excluded rows | yes | constants 327 / 800 / 375 not monotone; SI spread 1.9 percent. |
| 5. Observed vs. inferred | yes | two inferences, the second affects only the cluster downgrade. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question: the steps follow the audited logic | yes | constant -> super-block count and tree size (unit) -> controls (N sweep, PREFIX, md5 of overlays) -> option as the known cap -> constants at fixed option; the last step does not resolve on heap. |

### 5.2 Run 2?

**No** (2026-10-29): the run limit of this session is one run per tier. A run 2 would be worth its cost here: it would need a heap reading that separates the option (for example repeated arms, or a heap histogram of the builder at the largest segment) before it could confirm the cluster tier.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** undetermined (the unit tier says negative / does not cap, the cluster tier could not settle the effect: Not confirmed). The deterministic cluster observables point the same way as the unit tier, so the weight of the evidence is a true negative, but the class is not filed as one.

**Claim tested (B1):** memory and disk usage of SASI index building do not follow `SUPER_BLOCK_SIZE`: the number of tokens held in one `superBlockTree` scales with the data (keys per block) while its block count tops out at the constant, and process heap during an index flush tracks the index-flush memory threshold, not the constant.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1 with row 3: super blocks 46 / 12 / 3 for 16 / 64 / 256, file bytes within 1.95 percent, live heap within 13 percent over a 16 x range and rising with N); the 10 percent live-heap sub-prediction of U3 missed | does not cap (the constant bounds only the transient tree: about 1 MB at 16 to 17 MB at 256 in the heap, against a live heap of 120 to 136 MB) | run 1 + self-check | 2026-10-29 |
| Cluster | Not confirmed (no matching B3g row: heap peaks 844 / 800 / 1941 MiB over options 8 / 64 / 512 and 327 / 800 / 375 over constants 16 / 64 / 256; segments 137 / 18 / 3 follow the option, 17 / 18 / 18 do not follow the constant; SI bytes within 1.9 percent) | undetermined | run 1 + self-check | 2026-10-29 |

**Feedback filed:** the case file's section D filled (no commit by this session); amendments U1-U4 (B2) and C1-C3 (B3), dated 2026-10-28.
