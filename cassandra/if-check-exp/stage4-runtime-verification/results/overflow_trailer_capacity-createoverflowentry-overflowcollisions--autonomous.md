# overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous — stage-4 results  <!-- file: results/overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous.md -->

> **Case:** [`overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous`](../../stage3-ai-deep-read/cases/overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous.md)
>
> **Status:** **Self-checked 2026-10-29 — unit Confirmed (does not cap), cluster Confirmed (does not cap); no run 2.** Sub-predictions: all held; the heap control reads the post-collection peak (401 vs 927 MiB), not the sampled maximum (881 vs 847 MiB)
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (U1-U4 in B2, C1-C5 in B3 or as listed, dated 2026-10-28), recorded before any reading: `eb609accdfd903a2bc721187a348b5a3edff26ef8e522da788cbb6f55bd366a7` (unchanged by the runs until section D was filled). Repository HEAD of this session `b68711e` (working tree; case file, harness and results uncommitted). The frozen text is everything above section D. |
| **Harness** | `harness/overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous/` (see its README), uncommitted; written after the freeze. |
| **Tiers and values** | Unit (B2): C1-C8 as filed (slot counts 0, 4x2=8, 10, 8 offsets, 9 offsets, 248/249/600 tokens, 16 slots over two leaves, packed, estimatedMemoryUse at 1000/10000 terms). Cluster (B3): g x t = 8 and 9 colliding partitions in one SASI term (`g8`, `g9`), 1e5 and 1e6 clean rows (`r1e5`, `r1e6`), `max_compaction_flush_memory_in_mb` 1 and 100 (`m1`, `m100`). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Partly | A2: a count of 8-byte slots in a 64-byte trailer of a 4096-byte block; derivable bytes (64), so Partly. |
| A | knob varied, 3 values incl. default, or another approach with the reason | Met | B2b/B3b: the constant is not settable; the inputs (slots 0/8/9/10, tokens 248/249/600, g x t 8/9) are varied. |
| A | real resource measured | Met | bytes written; SI file bytes, commit log, heap. |
| A | usage driven to the limit and past it | Met | C2/C4 and g9 exceed 8 slots. |
| A | positive control (negative file) | Met | C5 (token count adds blocks) and C8; cluster: row-count disk growth and the max_compaction_flush_memory_in_mb cap. |
| B | prediction in numbers | Partly | C8 arithmetic slip (about 112 vs 220 + term bytes) and block counts: numbers added (U3). |
| B | every outcome has a row | Partly | B3g has no row for "assertion does not reach the log"; C3 explains that the source does not settle it; evidence added by Byteman; the row stays "not confirmed" if neither shows the throw. |
| B | confirmation needs the disallow branch | Met | C2/C4 throw (unit), g9 (cluster). |
| C | knob, values, workload, commands exact | Partly | collision-key method "not verified" and pk text: C1; filler: C2; sizes C4. |
| D | harness and prerequisites exist or are listed | Partly | written in step 1. |
| D | workload arithmetic reaches the limit | Met | slots by arithmetic in the unit tier; g9 = 9 offsets; 1e6 rows are small. |
| D | load-bearing citations spot-checked | Met | Checked in `cassandra/cassandra-5.0.9`: `TokenTreeBuilder.java:30-36`, `AbstractTokenTreeBuilder.java:65-73`, `:254-329`, `DynamicTokenTreeBuilder.java:101-160`, `OnDiskIndexBuilder.java:165-195`, `PerSSTableIndexWriter.java:240-345`, `MurmurHash.java:303`, `Murmur3Partitioner.java:238-247`; `:29` corrected to `:30` and the offset-position statement amended (U1). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Numbers for B2f, citation, launcher (U1-U4) | Applied 2026-10-28 | arithmetic / citation |
| R2 | Collision keys by `inv_hash3_x64_128`, blob pk, no filler, Byteman evidence, sizes (C1-C4) | Applied | B3a/B3c not runnable as filed |
| R3 | For stage 3: an AssertionError in a SASI segment flush is not caught by the catch clauses, so the failure may be silent; a conclusions row for it would help | left for stage 3 | C3 |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28/29 (node clock UTC: unit 23:5x on 10-28, cluster 23:54 to 00:55) |
| Node | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-b34/c` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e` (`copy-source.sh`; `git describe` = `cassandra-5.0.9`), `ant build-test` BUILD SUCCESSFUL (1 min 7 s); never built in the repository tree |
| Case-file / harness commit | uncommitted (working tree of `b68711e`); the case-file hash is in section 1; harness md5s in `run1/harness.md5` |
| Storage for node data | `~/s4-b34/node-ov` on local `/dev/sda3` (removed after each arm); nothing under `/proj` |
| Full logs (outside the repo) | `pc29:~/stage4-logs/b34/overflow/run1/{unit,cluster/<arm>}/` (per arm: `system.log`, `gc.log`, `heap.csv` 500 ms, `disk.csv` 2 s, `byteman.txt`, `stdout.txt`, `cmdlog.txt`) |

## 3. Runbook defects and harness defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | unit, first execution | harness | the harness's own `EXPECTED C6 total slots` line used a greedy regex that read the last leaf's `slots=0` (the `READ` line itself said `slots=16`); 12 PASS, 1 FAIL | regex made non-greedy; unit tier run again from its beginning | before the cluster tier (instrument, not a case defect) |
| D2 | cluster `g8`, attempt 1 | B3d, Byteman trace | the daemon closes standard output, so `traceln` lines went nowhere (0 trace lines; the arm otherwise gave the same files as the rerun: SI 12312 bytes) | rules write with `traceOpen` to `$T/logs/byteman.txt`; `g8` run again; attempt 1 kept under `run1/cluster/g8-attempt1-byteman-to-stdout/` | 2026-10-28; claim, prediction and table unchanged |
| D3 | cluster `g9` | analyzer | the first `analyze.py` check for "no complete SI component" required zero SI bytes; the node leaves a truncated 4110-byte `SI_t_v.db` that it then cannot open | check changed to "no file, or a file the node cannot open" (log line `Can't open index file`); B3f's wording ("no complete SI component") is unchanged | after the first `g9` reading, disclosed; the verdict uses the raw log lines |
| D4 | cluster | B3h | the 0-slot comparator for B3g's "SI size at 8 slots" row was not among the arms of C4 | extra arm `g0` (108 ordinary rows, no collisions) run after the chain | 2026-10-29; an addition, no change to frozen text |

Shakedowns before run 1 of a tier: none apart from the first executions listed above (the first unit execution, `g8` attempt 1). No reading was used to change a prediction.

## 4. Run 1

**Scope:** every B2 case (C1-C8 with the controls) and the B3 arms `g8`, `g9`, `g0`, `r1e5`, `r1e6`, `m1`, `m100`. **Command logs:** `overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous/run1/` (`unit/unit.out`, `cluster/<arm>/{cmdlog-head.txt,system-log-excerpt.txt,byteman.txt,sizes.txt,ls-sstable-dir.txt,...}`, `cluster-analysis.txt`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/unit.out`; "bytes" = bytes `write` produced; slots = (bytes - 64 - 16 x tokens) / 8)

| Case | Result |
|---|---|
| C1 4 tokens x 2 large offsets + 20 single | no exception; 512 bytes; 8 slots; 4 OVERFLOW entries; `serializedSize()` before `write` = 448 (omits the trailer) |
| C2 5 tokens x 2 large offsets | `AssertionError: cannot have more than 8 overflow collisions per leaf` |
| C3 / C4 one token, 8 / 9 offsets | 144 bytes, 8 slots / the same `AssertionError` |
| C5 248 / 249 tokens, one small offset | 4032 bytes, `numBlocks` 1 / 12288 bytes, `numBlocks` 3 (leaves of 248 and 1 tokens) |
| C6 600 tokens, 4 + 4 two-large-offset tokens in the first two leaves | no exception; 20480 bytes, `numBlocks` 5; 16 slots, 8 in each of leaf 1 and leaf 2; the same 600 tokens without overflow: 20480 bytes, `numBlocks` 5 |
| C7 248 tokens x 2 small offsets | PACKED, 0 slots, 4032 bytes |
| extra: 249 tokens, 8 slots in the full first leaf | 12288 bytes, `numBlocks` 3 (a full leaf carries its 8 slots inside the 4096-byte block) |
| C8 `estimatedMemoryUse()` | 228,000 at 1000 terms, 2,280,000 at 10,000 (8-byte terms; 220 + 8 per term) |

**Cluster tier** (`run1/cluster/<arm>/`)

| Arm | Reading |
|---|---|
| `g8` (2 tokens x 4 keys = 8 slots) | keys checked offline (0 mismatches) and on the node (`token(pk)` groups 4 + 4); flush succeeded; `nb-1-big-SI_t_v.db` 12312 bytes, `Data.db` 2780; Byteman: `createOverflowEntry` entered twice (4 offsets, 0 slots so far; 4 offsets, 4 slots so far), no throw; no assertion in `system.log` |
| `g9` (3 tokens x 3 keys = 9 slots) | Byteman: three entries (3 offsets at 0, 3 and 6 slots so far) and one `BM-OVF-THROW`; `system.log`: `ERROR [SASI-Memtable:1] ... JVMStabilityInspector ... Exception in thread` followed by `java.lang.AssertionError: cannot have more than 8 overflow collisions per leaf`, then `ERROR [MemtableFlushWriter:2] ... Can't open index file ... nb-1-big-SI_t_v.db, skipping.` and a `LEAK DETECTED` error; the flush itself finished (`Data.db` 2795 bytes) and a truncated `SI_t_v.db` of 4110 bytes was left; `SELECT pk ... WHERE v = 'x'` returns 0 rows; commit log directory 67,112,960 bytes at every one of 68 samples (no growth) over the 2 minutes after the flush |
| `g0` (108 ordinary rows, no collisions) | `SI_t_v.db` 12312 bytes = `g8`'s; `Data.db` 2784 |
| `r1e5` / `r1e6` (clean rows, one term) | `SI_t_v.db` 1,683,480 / 16,609,304 bytes (x 9.87); `Data.db` 1,691,320 / 16,485,081 (x 9.75); one sstable each |
| `m1` / `m100` (option 1 / 100 MiB; 1e6 rows in 4 flushes, then `nodetool compact`, 14 s window each) | "Flushed index segment" lines in the window: 112 / 2; maximum post-collection heap in the window: 401 / 927 MiB; sampled maximum heap used 881 / 847 MiB; `SI_t_v.db` 16,605,208 bytes in both; `Data.db` 17,049,859 / 17,049,341 |

### 4.2 Conclusion and logic

1. **Validity.** Valid. The limit was reached in both tiers [observed: C2, C4 throw; `g9` Byteman `BM-OVF-THROW`]. The node had the settings of C4 [observed: `proc-args.txt` `-Xmx1G`, `yaml-lines.txt` `commitlog_total_space: 256MiB`, `sasi_indexes_enabled: true`]; Byteman was loaded in the collision arms [observed: `proc-args.txt`]; every arm ended with no daemon left [observed: `daemons left: 0` in each `cmdlog-head.txt`; `ps` after the chain: 0].
2. **Readings.** (a) The unit numbers all equal the amended B2f/U3 numbers, including the per-leaf scope of the cap (C6) and the omission of the trailer by `serializedSize()` before `write` [observed]. (b) Cluster `g8` succeeds, `g9` fails with the assertion text; B3f's "assertion message appears in the log" held: the message is logged by `JVMStabilityInspector` from the SASI thread, although the flush's own INFO line ("Index flush ... took 36 ms") and the base-table flush complete [observed]. (c) B3f's "no complete SI component" held in the form: a truncated `SI_t_v.db` remains and the node cannot open it [observed; see D3]. (d) The heap control moved by post-collection occupancy and by segment count (401 vs 927 MiB; 112 vs 2) but not by the sampled maximum heap used (881 vs 847 MiB) [observed; [inferred: with a 1 GiB heap the sampled maximum includes uncollected garbage]].
3. **Matched row.** Unit B2g row 4 "Block bytes constant at 4096 while slots vary; size grows only with token count (C5) -> Claim confirmed" together with row 1 (C2/C4 throw, C1/C3 do not) and the C6 row: C6 does not throw, so the cap is per leaf [observed]. Cluster B3g row 1 "9 slots fail with the assertion, 8 succeed, disk/heap otherwise unchanged -> error boundary, not a usage cap" (`g8` = `g0` in SI bytes, 12312) and row 5 "SI size scales with rows while slot count is fixed; peak heap moves with `max_compaction_flush_memory_in_mb`" (x 9.87 for x 10 rows; 112 vs 2 segments, post-GC peak 401 vs 927 MiB) [observed]. Row 3 of B3g (a failed flush leaves commit-log usage growing) did not occur: the commit log stayed at 67,112,960 bytes [observed].
4. **Excluded rows.** "C2/C4 do not throw / size clamped at 8 slots": no, they throw [observed]. "Block bytes differ between 0 and 8 slots in multi-block output": no, 20480 vs 20480 [observed]. "C6 throws": no. "C5 does not add a block at 249 / C8 does not grow": no, the controls moved [observed]. "9 slots succeed with the file clamped": no. "Collisions could not be produced": no (inverted keys, checked offline and on the node).
5. **Observed vs. inferred.** Inferred: the reason the sampled heap maximum does not move in the heap control (part 2d). It does not enter the verdict, which rests on the byte counts, the Byteman and log lines, and the segment counts.
6. **Deviations and gaps.** Cluster `g8`/`g9`/`g0` were separate fresh nodes, not one node with a `TRUNCATE` between (the filed step 5); the keys were `blob`, not `text`; the filler was dropped (C2); `g0` was added. The unit tier measures bytes from `write`, not a node file; in the cluster tier the disk reading for the disallow case is the 4110-byte stump and a failed query, not a byte count of a "bounded" result. The positive control "heap moves with the option" is read from post-collection occupancy, which depends on GC timing (one run per arm). The node-wide consequences of the `AssertionError` beyond the index (the `LEAK DETECTED` error, the unusable index) were recorded but not explored.
7. **Core question.** The constant does not bound memory or disk use. Exceeding 8 overflow offsets in one leaf does not clamp or truncate anything: it raises an `AssertionError` (unit) and, on a node, fails the SASI segment build with an ERROR in the log and an index the node cannot open, while the base table's flush succeeds and the commit log does not grow. Below the limit a leaf block is 4096 bytes whether it holds 0 or 8 slots; index bytes follow the token count and the row count, and the heap follows the index option. The check is a format-validity assertion, not a usage cap.

**Conclusion (one line):** Unit B2g row 4 (with rows 1 and the C6 row) - confirmed (does not cap); Cluster B3g rows 1 and 5 - confirmed (does not cap; the exceeded limit fails the index build instead of limiting usage).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-29: `unit/unit.out` and every cluster arm's raw files re-parsed by `harness/.../selfcheck.py` (`run1/selfcheck.txt`: 30 PASS, 0 FAIL; its expectations are recomputed from the constants and the raw `READ` lines, not copied from the harness's `EXPECTED` lines) and, by hand, `cluster/g9/system-log-excerpt.txt`, `cluster/g9/byteman.txt`, `cluster/g9/ls-sstable-dir.txt`, `cluster/g8/byteman.txt`, `cluster/m1/windows.txt`, `ps` on the node.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `proc-args.txt` (Byteman agent in `g8`/`g9`/`g0`), `byteman.txt` entry lines, 0 daemons. |
| 2. Readings | yes | `unit.out` C1-C8 lines; `g9/system-log-excerpt.txt` the assertion; `cluster-analysis.txt` 401 vs 927 MiB recomputed from `gc.log` windows. |
| 3. Matched row | yes | `g8`/`g0` SI bytes both 12312; `r1e5`/`r1e6` ratio 9.87; segments 112 vs 2. |
| 4. Excluded rows | yes | C6 and its control equal 20480 bytes; C2/C4 throw. |
| 5. Observed vs. inferred | yes | one inference, outside the verdict. |
| 6. Deviations and gaps | yes | listed, including D1-D4. |
| 7. Core question: the steps follow the audited logic | yes | knob substitute (inputs) -> boundary at 8/9 slots -> per-leaf scope -> size drivers (tokens, rows) -> heap control -> node consequences. |

### 5.2 Run 2?

**No** (2026-10-29). Unit readings are exact byte counts and messages; the cluster claim rests on a throw seen three ways (Byteman, log, truncated file) and a size comparison; the only soft reading (post-collection heap) is not needed for the effect on the constraint.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): the constant sizes a 64-byte trailer inside a fixed 4096-byte leaf block; exceeding it raises an `AssertionError` (a failed index build on a node) rather than bounding usage.

**Claim tested (B1):** `OVERFLOW_TRAILER_CAPACITY` does not cap memory or disk use: a leaf block occupies the same fixed 4096 bytes whatever its overflow-slot count from 0 to 8, total index size follows the token count, and exceeding 8 slots in one leaf produces an `AssertionError` instead of a bounded or truncated result.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 4 with rows 1 and C6: throws only at the 9th slot, per leaf; size 4096 per block at 0 and 8 slots, grows with tokens) | does not cap | run 1 + self-check | 2026-10-29 |
| Cluster | Confirmed (B3g rows 1 and 5: `g8` works, `g9` throws and leaves an unopenable partial SI file, SI bytes follow rows, heap follows the option) | does not cap | run 1 + self-check | 2026-10-29 |

**Feedback filed:** the case file's section D filled (no commit by this session); amendments U1-U4 (B2) and C1-C4 (B3), dated 2026-10-28.
