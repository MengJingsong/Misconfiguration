# max_offset-createentry-offset--autonomous — stage-4 results  <!-- file: results/max_offset-createentry-offset--autonomous.md -->

> **Case:** [`max_offset-createentry-offset--autonomous`](../../stage3-ai-deep-read/cases/max_offset-createentry-offset--autonomous.md)
>
> **Status:** **Self-checked 2026-10-29 — unit Confirmed (does not cap), cluster Confirmed (does not cap); no run 2.** Sub-predictions missed: SI file linear in rows (x 2.93 for x 4), the 64 MiB commit-log control of p1 (192-288 MiB, served by the 1024 MiB cap of s16)
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (U1-U4 in B2, C1-C5 in B3 or as listed, dated 2026-10-28), recorded before any reading: `096191d1a19f07596322a8e2b2923c91c31fa35510a4743754b1adf6fbd0ce76` (unchanged by the runs until section D was filled). Repository HEAD of this session `b68711e` (working tree; case file, harness and results uncommitted). The frozen text is everything above section D. |
| **Harness** | `harness/max_offset-createentry-offset--autonomous/` (see its README), uncommitted; written after the freeze. |
| **Tiers and values** | Unit (B2): single offset 0, 1, Integer.MAX_VALUE, +1, MAX_OFFSET-1, MAX_OFFSET, +1, Long.MAX_VALUE; two and three offsets with one at MAX_OFFSET+1 / Long.MAX_VALUE; size controls 1/248/249 tokens; overflow-cap control (9 offsets). Cluster (B3): 1M / 4M / 16M rows of 1000-byte payload with a SASI index on a short text (`s1`, `s4`, `s16`; the 16M step behind the disk guard), controls `n1` (no index), `b1` (bti), `h1` (-Xmx4G), `p1` (commitlog_total_space 64MiB). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Partly | A2: the constant bounds a file position (48-bit field), not a byte quantity; the design measures disk bytes of the SASI/Index/Data files and heap, and says the limit is unreachable (about 8000 x the largest run). |
| A | knob varied, 3 values incl. default, or another approach with the reason | Met | B2b/B3b: the constant cannot be set; boundary values of the offset (5 values) and data volumes 1/4/16 GiB are the substitute, with the reason. |
| A | real resource measured, not only the counter | Met | B2d bytes written; B3d du, heap, commit log. |
| A | usage driven to the limit and past it | Met | unit: arithmetic reaches MAX_OFFSET and beyond; cluster cannot reach it and says so (B3c). |
| A | positive control (negative file) | Met | B2h overflow cap + size vs token count; B3h/C4: commit-log cap `p1` and the no-index and data-volume controls. |
| B | prediction in numbers | Partly | B2f gave "a fixed block size" for the serialized length: it is 80 bytes (single block, unaligned); numbers added (U3). |
| B | every outcome has a row | Met | B2g/B3g cover throw/no throw, size growth, control not moving, limit never reached. |
| B | confirmation needs the disallow branch | Met | the AssertionError at MAX_OFFSET+1 (unit) is the disallow branch; the cluster tier shows its absence at feasible sizes. |
| C | knob, values, workload, commands, stop conditions exact | Partly | B3c "1 KiB values" collides with MAX_TERM_SIZE (1024); sizes/guard/arms not exact: C1-C5. |
| D | harness and prerequisites exist or are listed | Partly | written in step 1 (this session). |
| D | workload arithmetic reaches the limit | Partly | unit yes; cluster: 16 GiB single-sstable compaction needs about 35 GB of the 47 GB free: guard in C2. |
| D | load-bearing citations spot-checked | Met | Checked in `cassandra/cassandra-5.0.9`: `TokenTreeBuilder.java:35-37`, `AbstractTokenTreeBuilder.java:288-313`, `:94`, `:109`, `PerSSTableIndexWriter.java:107-111`, `:136`, `:243`, `BigTableWriter.java:88-92`, `SortedTableWriter.java:263`, `Config.java:606`, `cassandra.yaml:1171-1172`; two line numbers corrected (U1). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Citation fixes, numbers for B2f, launcher (U1-U4) | Applied 2026-10-28 | not runnable as filed / arithmetic |
| R2 | Indexed value below 1024 bytes, sizes, disk guard, controls, node settings (C1-C5) | Applied | B3c invalid as filed |
| R3 | For stage 3: in BIG the checked quantity is an Index.db position, so the claim "file position of the data file" in the head of the file only holds for BTI | left for stage 3 | A2 already says so; the Entry/Ground lines do not |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | unit 2026-10-28 (node clock UTC 23:4x-23:5x); cluster 2026-10-29 (UTC 00:14 to 01:04) |
| Node | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-b34/c` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e` (`copy-source.sh`; `git describe` = `cassandra-5.0.9`), `ant build-test` BUILD SUCCESSFUL (1 min 7 s) |
| Case-file / harness commit | uncommitted (working tree of `b68711e`); hash in section 1; harness md5s in `run1/harness.md5` |
| Storage for node data | `~/s4-b34/node-mo` on local `/dev/sda3` (47 GB free at the start; removed after each arm); nothing under `/proj` |
| Full logs (outside the repo) | `pc29:~/stage4-logs/b34/maxoffset/run1/{unit,cluster/<arm>,cluster-aborted}/` (per arm: `system.log`, `gc.log`, `heap.csv` 500 ms, `disk.csv` 2 s, `stress.txt`, `cmdlog.txt`) |

## 3. Runbook defects and harness defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | unit, first execution | harness | the summary line printed the Java array `passing` instead of the count (a variable shadowed the counter); the 21 expectations all passed | variable renamed; unit tier run again from its beginning | before the cluster tier (instrument only) |
| D2 | cluster `b1` (bti), attempt 1 | B3a/C4 | the node refused to start: "Selected sstable format 'bti' is not available when in storage compatibility mode 'CASSANDRA_4'" | `storage_compatibility_mode: NONE` added for this arm; run again (attempt 1 kept under `run1/cluster-aborted/`) | 2026-10-29; control arm only, claim unchanged |
| D3 | cluster `s16`, attempt 1 | run script | the script was edited (`sed -i`, for D2) while it ran from the NFS checkout: bash died with "Stale file handle" during the load; the node and two samplers were left running and were stopped by hand; the data directory was removed | the run scripts now run from a local copy of the harness folder (`~/s4-b34/h-mo`); `s16` run again from its start | 2026-10-29; no reading from attempt 1 is used |
| D4 | cluster `p1`, analyzer | analyzer | the first check compared the data directory at mid-run and at the end of the run, but the directory shrinks in the final compaction | window-limited version added (load window from `cmdlog.txt`); the unmodified commit-log check still FAILs and is reported as it is | after the first p1 reading, disclosed |

Shakedowns before run 1 of a tier: none apart from the first executions listed above. No reading was used to change a prediction.

## 4. Run 1

**Scope:** every B2 value and the B3 arms `s1`, `s4`, `s16`, `n1`, `b1`, `h1`, `p1` (all seven ran; the disk guard of C2 passed for `s16`: 49.2 GB free, 42.4 GB needed). **Command logs:** `max_offset-createentry-offset--autonomous/run1/` (`unit/unit.out`, `cluster/<arm>/{cmdlog-head.txt,sizes.txt,tablestats.txt,system-log-excerpt.txt,...}`, `cluster-analysis.txt`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/unit.out`; "bytes" = bytes `write` produced; the entry type is the short at byte 64 of the written block)

| Case | Result |
|---|---|
| single offset 1, 2147483647 | no exception; 80 bytes; SIMPLE |
| single offset 2147483648, 140737488355326, 140737488355327 (`MAX_OFFSET`) | no exception; 80 bytes; FACTORED |
| single offset 0 (extra) | 80 bytes; SIMPLE |
| single offset 140737488355328 (`MAX_OFFSET + 1`) | `AssertionError: offset 140737488355328 cannot be greater than 140737488355327` |
| single offset `Long.MAX_VALUE` | `AssertionError: offset 9223372036854775807 cannot be greater than 140737488355327` |
| two offsets {5, `MAX_OFFSET + 1`}; {5, `Long.MAX_VALUE`} | no exception; OVERFLOW, 2 slots, 96 bytes |
| three offsets {5, 6, `MAX_OFFSET + 1`} | no exception; 3 slots, 104 bytes |
| two small offsets {6, 7} | PACKED, 80 bytes |
| 1 / 248 / 249 / 1000 tokens, one small offset | 80 / 4032 / 12288 (`numBlocks` 3) / 28672 (`numBlocks` 7) bytes |
| 8 offsets / 9 offsets on one token | 144 bytes, 8 slots / `AssertionError: cannot have more than 8 overflow collisions per leaf` |
| heap context | 20.2 MB before, 20.5 MB after (`System.gc()`; context only) |

**Cluster tier** (`run1/cluster/<arm>/`, `cluster-analysis.txt`; sizes in bytes after `nodetool compact` to one sstable; heap `-Xmx2G` except `h1`)

| Arm | Rows | `Data.db` | `Index.db` | `SI_t_v.db` | data directory | max commit log (MiB) | max post-collection heap (MiB) | log |
|---|---|---|---|---|---|---|---|---|
| `s1` | 1,000,000 | 1,040,312,341 | 15,742,303 | 24,981,192 | 1,083,306,729 | 352 | 2028 | no assertion |
| `s4` | 4,000,000 | 4,160,412,330 | 63,742,101 | 73,227,976 | 4,305,362,204 | 640 | 2028 | no assertion |
| `s16` | 16,000,000 | 16,677,053,861 | 255,723,314 | 265,297,608 | 17,229,163,002 | 1056 | 1945 | no assertion |
| `n1` (no index) | 1,000,000 | 1,040,152,733 | 15,742,291 | none | 1,058,143,037 | 448 | 2028 | - |
| `b1` (bti) | 1,000,000 | 1,039,663,317 (`da-17-bti-`) | `Partitions.db` 8,469,563 | 24,981,192 | 1,075,224,123 | 352 | 2028 | - |
| `h1` (`-Xmx4G`) | 1,000,000 | 1,040,077,514 | 15,742,304 | 24,981,192 | 1,083,071,877 | 640 | 4076 (sampled used 3307) | - |
| `p1` (commit log cap 64 MiB) | 1,000,000 | 1,040,347,318 | 15,742,307 | 24,981,192 | 1,083,372,193 | 288 | 2028 | - |

Ratios for rows x 4: `Data.db` 4.00 (`s4/s1`) and 4.01 (`s16/s4`); `Index.db` 4.05 and 4.01; `SI` 2.93 and 3.62. Commit log: `s16` reaches 1056 MiB (59 of 519 samples at 900 MiB or more) against a 1024 MiB cap while the data directory grows to 17.2 GB; `s4` stays at or below 640 MiB; `p1` (cap 64 MiB) runs between 192 and 288 MiB during the load and falls to 64 MiB after it. Stress: 0 errors in every arm; 31,610 / 27,601 / 23,232 inserts/s for `s1` / `s4` / `s16`. `grep -c "cannot be greater than"` and `AssertionError` in every `system.log`: 0.

### 4.2 Conclusion and logic

1. **Validity.** Valid. The boundary values of the offset were reached at the unit level (`MAX_OFFSET + 1` throws) [observed: `unit.out`]. At the cluster level the limit itself is not reachable (stated in B3c): the largest checked quantity was an index-file position of 255,723,314 (BIG) or a data-file position of 16,677,053,861 (BTI), 5.5 x 10^5 and 8.4 x 10^3 times below `MAX_OFFSET` [derived from `sizes.txt`]. The heap, commit-log and yaml settings were those of C2-C4 [observed: `proc-args.txt`, `yaml-lines.txt` in each arm]. No daemon was left [observed: `daemons left: 0` in each `cmdlog-head.txt`; `ps` after the chain: 0].
2. **Readings.** (a) Unit: all B2f/U3 numbers held [observed]. (b) Cluster: `Data.db` and `Index.db` follow the rows exactly (x 4.00, x 4.01), no assertion in any arm, heap bounded by `-Xmx` (post-collection 2028 MiB of 2048 for `s1`/`s4`, 1945 for `s16`; 4076 of 4096 for `h1`) [observed]. (c) Missed sub-predictions of B3f / amendment C4: the SI file grows less than linearly (x 2.93 for x 4 rows, x 3.62 for the next x 4; [inferred: the indexed text has only 100,000 distinct values, so the term count is fixed and only the token trees grow with the rows]); the 64 MiB commit log of `p1` does not stop near 64 MiB (192 to 288 MiB during the load) [observed]. (d) The positive control that did work: the 1024 MiB commit-log cap of `s16` (max 1056 MiB, `s4` max 640 MiB) while the data directory kept growing; and `-Xmx` (`h1` 4076 vs `s1` 2028 MiB post-collection) [observed].
3. **Matched row.** Unit B2g row 5 "Size flat while the positive control (B2h) moves -> claim confirmed at the unit level": size 80 bytes for every passing offset from 1 to `MAX_OFFSET`, throw only at `MAX_OFFSET + 1` with one offset (row 1), the control (tokens: 80, 4032, 12288 bytes; 9 offsets: throw) moved [observed]. Cluster B3g row 1 "Disk grows with data, heap unrelated, no assertion -> usage does not follow the constant (claim confirmed)" [observed]. The row "Positive-control commitlog plateaus near its cap" is matched by `s16` (cap 1024 MiB), not by `p1` (cap 64 MiB); `p1` alone would be the row "Control did not plateau" [observed].
4. **Excluded rows.** "No throw at `MAX_OFFSET + 1` with one offset", "throw at a value <= `MAX_OFFSET`", "size or heap grows as the offset approaches the limit": none occurred (80 bytes at every passing value) [observed]. "AssertionError mentioning offset in the log": 0 lines in 7 arms [observed]. "Disk or heap plateaus as file size grows with no other cap set": the heap sits at its `-Xmx` (a cap that is set; `h1` shows it moves with `-Xmx`), the disk does not plateau [observed]. "Collisions"/"runs too small": the 16 GiB step ran (guard passed).
5. **Observed vs. inferred.** Inferred: the reason the SI file grows less than linearly (part 2c); the offsets' magnitudes in part 1 come from file sizes, not from a probe of the builder (B3d: "not observable"). Neither enters the verdict, which rests on the unit boundary and the absence of any effect of file position up to 16 GiB.
6. **Deviations and gaps.** The constant cannot be varied, so the cluster tier shows only that nothing changes in a range 5.5 x 10^5 (BIG) or 8.4 x 10^3 (BTI) below it; the unit tier is the only place the boundary is crossed, and only by arithmetic on the offset passed to the builder. The index value is a 10-character text (C1), not "1 KiB values"; the `p1` control did not behave as filed; the heap reading is saturated at `-Xmx` in `s1`/`s4`, so "heap unrelated to the file position" is shown by `s16` being no larger (1945 vs 2028), not by a trend; one run per arm; `b1` ran with `storage_compatibility_mode: NONE`. The offset values seen by `createEntry` in the cluster were not read (no per-call trace, to avoid millions of calls).
7. **Core question.** `MAX_OFFSET` does not cap memory or disk usage. It makes the builder reject (by `AssertionError`) a single-offset token whose offset is above 2^47 - 1; below it every offset is written in the same 80-byte entry block, and multi-offset tokens are not checked at all. On a node, data, index and SI bytes follow the row count up to 16 GiB of data in one sstable with no effect of the file position, and the heap is set by `-Xmx` and the memtable and compaction settings.

**Conclusion (one line):** Unit B2g row 5 (with row 1) - confirmed (does not cap); Cluster B3g row 1 - confirmed (does not cap), with the 64 MiB commit-log control of `p1` and the linear-SI sub-prediction missed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-29: `unit/unit.out` and every cluster arm's raw files re-parsed by `harness/.../selfcheck.py` (`run1/selfcheck.txt`: 45 PASS, 0 FAIL; its expectations are recomputed from the constants and the raw lines, not copied from the harness's `EXPECTED` lines) and, by hand, `cluster/s16/disk-decimated.csv` and the raw `disk.csv` (commit-log series of `s16`, `s4`, `p1`), `cluster/h1/gc-pauses-summary.txt`, `cluster/b1/ls-sstable-dir.txt`, `cluster/s16/sizes.txt`, and `ps` on the node.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `s16/sizes.txt` (Data 16,677,053,861; Index 255,723,314); `yaml-lines.txt`; 0 daemons. |
| 2. Readings | yes | `selfcheck.txt` size ratios; the SI ratios 2.93 / 3.62 recomputed from `sizes.txt`; commit-log maxima recomputed from `disk.csv`. |
| 3. Matched row | yes, with the control caveat | the 1024 MiB cap binds in `s16` (59 of 519 samples >= 900 MiB, max 1056) and not in `s4` (max 640); `p1` alone would not bind. |
| 4. Excluded rows | yes | 0 "cannot be greater than" lines in 7 `system.log` files. |
| 5. Observed vs. inferred | yes | the two inferences are outside the verdict. |
| 6. Deviations and gaps | yes | listed, including D1-D4. |
| 7. Core question: the steps follow the audited logic | yes | boundary by arithmetic (unit) -> size independent of the offset -> linear disk with rows to 16 GiB -> controls (`n1`, `h1`, commit log, `b1`) -> no assertion. |

### 5.2 Run 2?

**No** (2026-10-29). The unit readings are exact byte counts and messages; the cluster tier cannot reach the limit, so a second run would repeat the same absence; the two missed sub-predictions are about secondary quantities.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): `MAX_OFFSET` is a format-width ceiling on a file position (48 bits) that rejects an unencodable single offset; it bounds no heap, off-heap or disk quantity.

**Claim tested (B1):** `MAX_OFFSET` does not cap memory or disk: no workload that stays under about 128 TiB of file position changes how much heap, off-heap or disk the node uses because of this constant, and the only effect of the constant is to make serialization of a single-offset token with `offset > MAX_OFFSET` throw.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 5 with row 1: 80 bytes for every passing offset, `AssertionError` only at `MAX_OFFSET + 1` with one offset, multi-offset tokens unchecked, the control moved) | does not cap | run 1 + self-check | 2026-10-29 |
| Cluster | Confirmed (B3g row 1: disk x 4.00 per x 4 rows to 16.7 GB in one sstable, heap bounded by `-Xmx`, no assertion); the `p1` commit-log control missed (the `s16` cap of 1024 MiB served as the control) | does not cap | run 1 + self-check | 2026-10-29 |

**Feedback filed:** the case file's section D filled (no commit by this session); amendments U1-U4 (B2) and C1-C5 (B3), dated 2026-10-28.
