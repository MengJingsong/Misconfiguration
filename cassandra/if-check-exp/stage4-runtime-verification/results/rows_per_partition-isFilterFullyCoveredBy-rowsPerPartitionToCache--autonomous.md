# rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous — stage-4 results  <!-- file: results/rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous`](../../stage3-ai-deep-read/cases/rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous.md)
>
> **Status:** run 1 done and self-checked (2026-10-26); verdict filed; no run 2
>
> **Outcome class:** true positive (estimate positive, effect caps)
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
| **Case-file version** | The case file at repository HEAD `93d6365` (untracked there) plus the audit amendments of 2026-10-26 (the orchestrator commits). sha256 of the whole file after the amendments (frozen before any reading): `3ead238dc6f36e7e8046119b28c11c12f2a7a553964013a079cde89de24ed98e`. sha256 of the unit prediction and conclusions text (`awk` from the line starting `**B2f.` to the line before `**B2h.`): `81b975909e65899258ad4995f7e78cc22deb53717151a4ea759cfaf58d9f40cf`; of the cluster text (from `**B3f.` to the line before `**B3h.`): `46d357fcd104f80c1674f22d862cc7bf2f276a9876e0642e8209e1b24551d8e8`. The case file changes after run 1 only in section D (feedback); its sha256 then is recorded in §8. |
| **Harness** | `harness/rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous/` (`RowsPerPartitionTest.java`, `unit-run.sh`, `analyze_unit.py`, `mk-known-answer.py`, `Jmx.java`, `loader.py`, `cluster-run.py`, `analyze_cluster.py`, `run1-chain.sh`, `selfcheck.py`, `shake-cluster.sh`, `README.md`; written after the audit and before run 1; not committed by this agent). **Instrument checks before run 1 (shakedowns, not readings, discarded; details in the harness README):** (1) analyzer on a synthetic good file: 0 primary mismatches; on a bad copy (N=10 caches 15 rows): flags it, class "claim wrong". (2) Unit test at 300 rows per partition: first trigger OK, `cachedLiveRows` follows N. (3) Cluster chain on 400 + 80 partitions: all seven arms ran. Two harness defects found and fixed: (a) prepared SELECT statements keep the table's old `rows_per_partition` after `ALTER TABLE` and a node restart (entries kept the old N; the 32 MiB arm cached nothing): the scan now uses unprepared statements; (b) one-off native memory of the first whole-partition reads sat in the `RssAnon` delta: a warm-up on the other table now precedes the `baseline` checkpoint (the `cold` checkpoint is kept). |
| **Tiers and values** | Unit (B2): `rows_per_partition` N in {1, 10, 100, ALL, 2000, NONE} on `(pk, ck, v text)` with one 1000-row partition; plus the tombstone variants (N=10) and the no-clustering table. Cluster (B3): one node lifetime per arm, `row_cache_size` 256 MiB, N in {1, 10, 100, ALL} on `ks.t` (10,000 partitions x 300 rows x 1 KiB), tombstone arm on `ks.t2`, negative control `NONE`, positive control `c32` (N=100, `row_cache_size` 32 MiB). |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 (amendments are recorded in the case file's section D; no reading existed when they were made). |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: off-heap OHC bytes of a row-cache entry (serialized size); count unit is live rows per partition with a derivable size (about 1.05 KiB per row). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b N in {1, 10, 100, ALL, 2000, NONE}; B3b {1, 10, 100, ALL}. The default is 0 = NONE (the negative control). |
| A. Core question | real resource measured, not only the counter (gap named) | Met after amendment | B2d measures the serialized size by the serializer (not heap); B3d uses the OHC gauges and `RssAnon`. Gap named: the unit tier measures no heap, and RSS carries allocator retention. Amended: heap pre-touched, one node lifetime per N, tolerance 20% or 16 MiB. |
| A. Core question | usage driven to the limit and past it | Met after amendment | The cap is on rows: partition (1000 / 300 rows) larger than every finite N. The byte cap (256 MiB) is reached for N=100 and ALL (B3f arithmetic). Data volume reduced 20 GB to 3.1 GB (B3b amended). |
| B. Logic | each step says what it establishes | Met | B2e / B3e numbered steps; the B1 claim is split by A3 steps 4-6. |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f numbers are exact; B3f was in loose 'about' terms and a ratio for ALL based on the 20 GB dataset; recomputed with fixed tolerances. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover cap holds, cap wrong, bytes not following, overshoot (tombstones, ALL, no clustering), setup error, limit not reached. Uncovered cases fall to 'Not confirmed (no matching row)'. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Ceiling = `cachedLiveRows` / bytes per entry follow N; disallow evidence = the entry stops at N rows while the partition holds more (`rowsCounted < rowsToCache` stops `hasNext`, `SinglePartitionReadCommand.java:586`) and `isFilterFullyCoveredBy` false at `cachedLiveRows == N`. |
| B. Logic | alternative explanations and their controls | Met after amendment | B2h N=2000 and NONE; B3h NONE and the 32 MiB byte-cap control. Positive file, so the negative-claim control is not required. The control was rewritten as its own arm. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly, fixed | B2a asked for a row-cache setup the test does not need; B3c/B3e left the passes, the tombstone phase and hit-rate expectations loose (the LIMIT 5 / N=1 sentence was garbled). Amended. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly, fixed | Dataset, passes, tolerances, the second table for the tombstone phase and the metric names were not exact; amended (B3b, B3c, B3e, B3f). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11 / Ant on pc07; trees `~/s4-b9-rp` (`ant build-test`) and `~/s4-b9-rp-n` (`ant jar`) built 2026-10-26; Python driver, loader and JMX reader are reusable from the `row_cache_size` harness (copied, step 1). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | Original 20 GB load did not fit the 29 GB shared local disk; amended to 3.1 GB on `/dev/shm` (126 GiB). N=100 needs 10,000 x 105 KiB = 1.05 GB of reads against a 256 MiB cache. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Verified: `ColumnFamilyStore.java:1931` and `:3259-3265`; `SinglePartitionReadCommand.java:491,506,528,547-549,558,575-598,604,617`; `CachedBTreePartition.java:create/serializedSize`; `DataLimits.java:407-429`; `ClusteringIndexSliceFilter.java:76-90`; `CacheService.java:143-151,411-424`; `OHCProvider.java:40,43`; `Config.java:473-474`. Corrected: `CachingParams.java` default at `:51` (not `:55`) and `rowsPerPartitionFromString` at `:140`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B2a: no row-cache setup in the unit test (the test yaml has OHC 16 MiB) | Applied 2026-10-26 (B2a) | Avoids a no-op `setRowCacheSizeInMiB` that would not create a cache after `CacheService` initialised. |
| 2 | B2f: range-tombstone markers are not rows; row-deletion variant predicts `rowCount` 60, range-tombstone arm 10 | Applied 2026-10-26 (B2f) | `AbstractBTreePartition.build` puts markers into `deletionInfo`, so the stated '10 rows plus 2 markers' could not be read from `rowCount`. |
| 3 | B3a/B3b/B3c: tmpfs; 10,000 x 300 rows; `ks.t2` for the tombstone phase; pre-touched heap | Applied 2026-10-26 (B3a, B3b, B3c) | The 20 GB dataset does not fit the shared 29 GB local disk and is far larger than the question needs. |
| 4 | B3e: one node lifetime per N; JMX table counters | Applied 2026-10-26 (B3e) | glibc keeps freed memory; `RssAnon` would carry the previous arm. |
| 5 | B3f: numbers and tolerances recomputed; hit-rate claims limited to N=1 and N=10; B3g two rows | Applied 2026-10-26 (B3f, B3g) | Fixed before any reading; the original hit-rate sentence was garbled and a sequential scan of a cache smaller than the scan gives no hit-rate expectation for N=100/ALL. |
| 6 | B3h: positive control as its own arm with a 32 MiB `row_cache_size` | Applied 2026-10-26 (B3h) | Same reason as 4. |
| 7 | Citation corrections `CachingParams.java:51`, `:140` | Applied 2026-10-26 (A1) | Line drift only. |
| 8 | The line-1931 check is a coverage test, not a limit; the cap is at population (`:586`). Case file already says so (Estimate field). | No change | Consistent with the file's own caveats. |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 19:52 EDT, cluster 19:53-20:06 EDT) | not done |
| Node (CloudLab name and type) | `pc07` (`node0.jason92-320876...`), 40 cores, 251 GiB; port slot 2 (127.0.2.1) | not done |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | unit `~/s4-b9-rp` and node `~/s4-b9-rp-n`, both `copy-source.sh` of `cassandra-5.0.9` at repository commit `93d6365` (the repository's `cassandra/cassandra-5.0.9/` was clean); unit tree `ant build-test` 1 min 20 s, node tree `ant jar`; local baseline commits `43cb41d` and `0ffa4f3` | |
| Case-file commit / harness commit | case file untracked at `93d6365`, sha256 in §1; harness not committed by this agent | |
| Storage for node data | tmpfs `/dev/shm/s4-b9-rp` (3.75 GB of data after the load); unit-test data in the test's temporary directory under the unit tree | |
| Full logs (path, outside the repo) | `~/s4-b9-rp-logs/run1/{unit,cluster}/` on `pc07` (shakedowns in `~/s4-b9-rp-logs/shake-*`, not used) | |

## 3. Runbook defects

None found in the audited text after the amendments (the changes made at the audit are listed in §1.1 and in the case file's section D). Two **harness** defects were found by the shakedowns (not run 1) and fixed before run 1; both are in the harness README: a prepared SELECT keeps the table's old `rows_per_partition` after `ALTER TABLE` (reads are now unprepared), and the one-off native memory of the first whole-partition reads sat in the `RssAnon` delta (a warm-up on the other table now precedes the `baseline` checkpoint; `cold` is kept).

## 4. Run 1

**Scope:** unit tier (B2) at full scale (1000-row partition; N in 10, 1, 100, ALL, 2000, NONE; both tombstone variants; no-clustering table) and cluster tier (B3): `ks.t` 10,000 x 300 rows x 1 KiB, `ks.t2` 2,000 x 300 rows with ck 0-199 deleted, arms n10, n1, n100, nall, t10, none and c32, each its own node lifetime. **Command log:** `rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous/run1/` (`unit/session.log`, `cluster/session.log`, `run1-chain.out`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/unit.txt`; analyzer `run1/unit/summary.txt`: 41 of 41 primary checks ok, class "claim holds")

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| first trigger: N=10 leaves an entry after the first read | OK (`cachedLiveRows` 10) | `unit/unit.txt` `firsttrigger=OK` |
| `cachedLiveRows` / `rowCount` for N = 1, 10, 100, ALL, 2000 (partition of 1000 live rows) | 1/1, 10/10, 100/100, 1000/1000, 1000/1000 | `unit/unit.txt` `N*.cachedLiveRows`, `N*.rowCount` |
| serialized size of the entry | 157, 1147, 11047, 110811, 110794 B for N = 1, 10, 100, ALL, 2000; size(100)/size(10) = 9.63 | `unit/unit.txt` `N*.serializedSize` |
| `isFilterFullyCoveredBy`, full-slice filter | false for N = 1, 10, 100; true for ALL, 2000 | `unit/unit.txt` `N*.coveredFullSlice` |
| `isFilterFullyCoveredBy`, head filter with LIMIT 5 | false for N=1; true for N = 10, 100, ALL, 2000 | `unit/unit.txt` `N*.coveredHead5` |
| table counters (information, not a B2f row) | N=10 and 100: miss 1, then hit 1; N=1: miss 1, then `HitOutOfRange` 1; NONE: all 0 | `unit/unit.txt` `N*.after1/after2.*` |
| `rows_per_partition='NONE'` | no entry | `unit/unit.txt` `NNONE.entry=absent` |
| tombstone variant, row deletions (N=10, ck 0-49 deleted) | `cachedLiveRows` 10, `rowCount` 60 | `unit/unit.txt` `TOMBROWS.*` |
| tombstone variant, range tombstone (N=10) | `cachedLiveRows` 10, `rowCount` 10, 1 range tombstone in `deletionInfo` | `unit/unit.txt` `TOMBRANGE.*` |
| no-clustering table | `cachedLiveRows` 1, `rowCount` 1 for N=1 and N=5; size 152 B for both at v = 100 B, 5053 B at v = 5000 B (+4901 B) | `unit/unit.txt` `NOCK_*` |

**Cluster tier** (`run1/cluster/<arm>/ckpt.jsonl`; analyzer `run1/cluster/summary.txt`: 13 of 16 primary checks ok; the 3 mismatches are the `RssAnon` rows). Sizes are the OHC `Size` gauge in bytes; MB are 10^6.

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| N=1, 256 MiB | n1 | Size, Entries after pass 1; bytes/entry | 11,819,841 B, 10,000 entries; 1182 B/entry (1.10 x N x 1.05 KiB) | `n1/ckpt.jsonl` |
| N=1 | n1 | table counters | pass 1: miss 10,000; pass 2: hit 0, `HitOutOfRange` 10,000 | `n1/ckpt.jsonl` |
| N=10 | n10 | Size, Entries; bytes/entry | 105,148,419 B, 10,000 entries; 10,515 B/entry (0.98) | `n10/ckpt.jsonl` |
| N=10 | n10 | table counters | pass 2: hit 10,000 (100%), `HitOutOfRange` 0 | `n10/ckpt.jsonl` |
| N=100 | n100 | Size, Entries; bytes/entry | 265,840,999 B (cap 268,435,456), 2,560 entries of 10,000; 103,844 B/entry (0.97); Size 265,841,609 B at the highest poll | `n100/ckpt.jsonl`, `n100/jmx.csv` |
| N=ALL | nall | Size, Entries; bytes/entry | 239,036,928 B, 768 entries of 10,000; 311,246 B/entry (304 KiB; 3.00 x the N=100 entry) | `nall/ckpt.jsonl` |
| N=10 on `ks.t2` (ck 0-199 deleted), 2,000 partitions | t10 | bytes/entry | 25,838,240 B, 2,000 entries; 12,919 B/entry, 2,404 B above n10 | `t10/ckpt.jsonl` |
| `NONE` | none | Entries, Size, counters | 0, 0; hit 0, miss 0 after both passes | `none/ckpt.jsonl` |
| N=100, `row_cache_size` 32 MiB (positive control for a binding byte cap) | c32 | Size, Entries | 26,584,320 B (cap 33,554,432), 256 entries of 10,000; 103,845 B/entry | `c32/ckpt.jsonl` |
| all arms | | `RssAnon` after pass 1 minus the `baseline` checkpoint, against Size | n1 +26.4 MB (Size 11.8); n10 +666.7 MB (105.1); n100 +708.6 MB (265.8); nall +304.5 MB (239.0); t10 +114 MB (25.8); none +22 MB (0); c32 +421 MB (26.6). Against the `cold` checkpoint (before the warm-up): +131, +747, +760, +407, +280, +97, +522 MB | `*/ckpt.jsonl` (`RssAnon_kb`) |
| all arms | | no `ERROR` in `system.log`; node stopped by `nodetool drain` and SIGTERM, no daemon left | `*/system.log.warn-error.txt`, `cluster/session.log` ("daemons left: []") |

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached: for N=1, 10 and 100 the partition (300 live rows in the cluster, 1000 in the unit tier) has more rows than N, so the row cap binds [observed: `unit/unit.txt` N1/N10/N100 `cachedLiveRows` = N; `n1`, `n10`, `n100` bytes/entry follow N]; for N=100 and ALL the byte cap (256 MiB) is reached too (Size 265.8 MB of 268.4 MB, 2,560 and 768 entries, fewer than the 10,000 partitions read) [observed: `n100/ckpt.jsonl`, `nall/ckpt.jsonl`]. "Hold fixed" settings: dataset and queries identical in every arm [observed: `cluster/session.log` rows returned 50,000 per pass for 10,000 reads, `*/ckpt.jsonl rows_returned`]; each arm a cold JVM with the heap pre-touched and the cache invalidated [observed: `cluster/session.log` "stopping node"/"node up", `*/ckpt.jsonl` baseline `entries` 0]; `row_cache_size` 256 MiB, or 32 MiB for c32 [observed: `*/system.log.warn-error.txt` is empty; "Initializing row cache with capacity of ..." lines in `cluster/session.log`]; the table's `rows_per_partition` set by `ALTER TABLE` and read back from `system_schema.tables` before each arm [observed: `cluster/session.log` "schema caching ="]. First-trigger check passed in every arm [observed: `cluster/session.log` "FIRST-TRIGGER CHECK ok"].
2. **Readings** — unusual: (a) N=ALL stored 768 entries, under the predicted bound of 850 [observed: `nall/ckpt.jsonl`]; (b) `RssAnon` rose 0.3 to 0.7 GB in the n10, n100, nall and c32 arms, far more than the cache Size, and by 421 MB in c32 where the cache holds only 26.6 MB [observed: `*/ckpt.jsonl`]; the n1 and none arms rose by 26 and 22 MB; (c) pass 2 of n100, nall and c32 had no hits (the cache is smaller than the sequential scan, so no hit-rate claim was made for them) [observed: `n100/ckpt.jsonl` etc.].
3. **Matched row** — unit B2g row 1, "`cachedLiveRows` = N for N below 1000, 1000 for ALL/2000 | Claim holds: population honours the cap": N=1, 10, 100 gave 1, 10, 100 and ALL and 2000 gave 1000 [observed: `unit/unit.txt`]. With it, B2g "size grows about linearly with N" (9.63x from N=10 to N=100) and "`rowCount` > N only in tombstone variant" (60 rows for the row-deletion variant) [observed: `unit/unit.txt`]. Cluster B3g row 1, "bytes/entry about proportional to N below the byte cap; Size <= 256 MiB | Claim holds": bytes/entry 1182, 10,515, 103,844 for N = 1, 10, 100 (0.97 to 1.10 of N x 1.05 KiB), Size never above the capacity at any of the 11 polls per arm [observed: `*/ckpt.jsonl`, `*/jmx.csv`, `selfcheck.txt`]. Also matched: "N=ALL entries about whole partitions" (304 KiB, 300 rows x r) and "tombstone phase bytes/entry above N x row size" (12,919 B against 10,515 B, +2,404 B) [observed: `nall/ckpt.jsonl`, `t10/ckpt.jsonl`]. Not matched as predicted: B3f's "RssAnon delta equals Size within 20% or 16 MiB" holds for n1 (+26.4 MB against 11.8 MB, tolerance 16.8 MB) and nall (+304.5 MB against 239.0 MB, tolerance 47.8 MB) and fails for n10, n100 (and was not predicted for c32); that is the B3g row "`RssAnon` delta above Size by more than 20% and 16 MiB | memory outside the cache: report as overshoot" [observed: `cluster/summary.txt`].
4. **Excluded rows** — "`cachedLiveRows` > N for any N below 1000 | claim wrong": excluded, `cachedLiveRows` <= N in every arm [observed: `unit/unit.txt`]. "size flat across N while `cachedLiveRows` rises": excluded, size rises 157 -> 1147 -> 11047 -> 110811 B [observed: `unit/unit.txt`]. "`isFilterFullyCoveredBy` true for the full slice at N below 1000": excluded, false for N = 1, 10, 100 [observed: `unit/unit.txt`]. "entry absent after the first read (setup error)": excluded, N=10 present, NONE absent as the NONE control predicts [observed: `unit/unit.txt`]. Cluster "bytes/entry independent of N | claim wrong": excluded, 1182 -> 10,515 -> 103,844 B [observed: `*/ckpt.jsonl`]. "Size exceeds `row_cache_size`": excluded, maximum 265,841,609 B of 268,435,456 (256 MiB) and 26,585,354 B of 33,554,432 (32 MiB) [observed: `n100/jmx.csv`, `c32/jmx.csv`]. "Cache Size and RSS both flat across N while the positive control moves": excluded, Size follows N [observed: `*/ckpt.jsonl`]. "Size flat but control also flat, or limit never reached | not confirmed": excluded, the control moved (Size capped at 26.6 MB, 256 entries, against 2,560 entries at 256 MiB) and the byte cap was reached for N=100 and ALL [observed: `c32/ckpt.jsonl`, `n100/ckpt.jsonl`].
5. **Observed vs. inferred** — Inferred: (i) that the entry's row count is `cachedLiveRows` = min(N, live rows) in the cluster, from bytes/entry = N x 1.05 KiB, not from reading the entries [inferred: only the unit tier reads entries; the cluster has Size/Entries]; (ii) that line 1931 is a coverage test and the cap is applied at population (`SinglePartitionReadCommand.java:586`) [inferred: source reading; the unit tier shows `isFilterFullyCoveredBy` false at `cachedLiveRows` == N and the entry holding exactly N rows]; (iii) that the extra `RssAnon` in n10, n100 and c32 is memory used by reads and the allocator, not by the cache [inferred: n1 and none rise only 22 to 26 MB, and c32 rises 421 MB with a 26.6 MB cache, so the extra does not follow Size; the cause (transient read buffers kept by glibc, or the chunk cache) was not isolated]. (iv) that the byte cap and the row cap are independent constraints [inferred: n100 and c32 have the same bytes/entry, 103.8 KB, at 256 and 32 MiB, and different Entries].
6. **Deviations and gaps** — the audit amendments and the harness changes (unprepared reads, warm-up) are listed in §1 and §3. The warm-up reads 1,000 partitions of the other table before `baseline`; with it, RSS deltas are against the post-warm-up value, and the `cold` deltas are larger. Heap use was not measured by the unit tier and the cluster tier only recorded `GC.heap_info` (used heap 85 to 90 MB at the pass-1 checkpoint, `*/heapinfo-pass1.txt`), so heap copies of cached entries are not quantified. The unit and cluster tiers use 1000 and 300 rows per partition, as amended. No run 2. A prepared `SELECT` was found to keep the old caching options (§3); it is a note for stage 3, not part of this verdict.
7. **Core question** — Yes, the constraint caps usage of the quantity it names, and usage follows it: in the unit tier an entry never holds more live rows than N (1, 10, 100) and the serialized size follows N (157 to 11,047 B); in the cluster the bytes per entry follow N (1182, 10,515, 103,844 B) and the cache never exceeds `row_cache_size`, the 32 MiB control showing the byte cap binding when it is the smaller one. The cap is on live rows only, so it is soft: dead rows before the live ones are stored too (60 rows for 10 live), `ALL` stores whole partitions (304 KiB each) and a table without clustering columns stores its single row whole [observed: `unit/unit.txt`, `nall/ckpt.jsonl`], and the process grew far more than the cache Size in the n10 and n100 arms (§4.2 part 2, not resolved).

**Conclusion (one line):** unit B2g "`cachedLiveRows` = N for N below 1000, 1000 for ALL/2000 | Claim holds" and cluster B3g "bytes/entry about proportional to N below the byte cap; Size <= 256 MiB | Claim holds" — confirmed, with the recorded overshoots (dead rows, ALL, no clustering columns) and with the `RssAnon` overshoot as an unmatched part of B3f.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed the raw files without the analyzers (unit: the test's own `STAGE4` echo lines in `ant.log` against `unit.txt`; cluster: the CKPT lines of `session.log`, the 5-second `jmx.csv` and `rss.csv` samples, the `nodetool info` Row Cache line of each arm, and `system.log` segments): 78 checks, 0 FAIL (`run1/selfcheck.txt`). Its first two versions had checks that compared samples of different instants and failed (9, then 7 FAIL lines: a poll taken inside a pass, an RSS sample taken after the next pass had started); the checks were rewritten to compare like with like (the last poll with the last checkpoint; no poll above the capacity) and no reading or analyzer was changed. I also re-opened the raw files by hand for the points below.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster/session.log`: every arm shows "FIRST-TRIGGER CHECK ok", the schema read-back, one node lifetime and "daemons left: []"; `ckpt.jsonl` baselines have `entries` 0; `selfcheck.txt` confirms the row-cache capacity of each arm's start-up line (256 MiB, 32 MiB for c32) |
| 2. Readings | yes | the `RssAnon` rows re-read from `*/ckpt.jsonl` and `*/rss.csv` (n10 3.35 GB at the first sample after the baseline, 3.51 GB at the end); `nodetool info` equals the gauges for all 7 arms |
| 3. Matched row | yes | unit: all 41 primary checks ok in `summary.txt` and `unit.txt` (e.g. `N10.cachedLiveRows=10`, `TOMBROWS.rowCount=60`); cluster: the e(N) ratios recomputed in `selfcheck.py` (1.099, 0.978, 0.966; ALL 311,246 B) |
| 4. Excluded rows | yes | each exclusion above re-read in `unit.txt`, `ckpt.jsonl`, `jmx.csv`; the maximum poll is below the capacity in every arm (`selfcheck.txt`) |
| 5. Observed vs. inferred | yes | (iii) is the weakest inference: the cause of the extra process memory is not isolated; it does not change the verdict, which concerns the cache entries |
| 6. Deviations and gaps | yes | harness defects and amendments listed; heap copies not quantified |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 -> unit (population cap, coverage test) -> cluster (bytes/entry follow N, byte cap, control) -> answer; the claim's own bypasses are rows the tiers also confirm |

### 5.2 Run 2?

**No** — decided 2026-10-26. The claim is confirmed by both tiers on direct readings (`cachedLiveRows`, bytes per entry, Size against the capacity); the one open point (the `RssAnon` excess) is not part of the claim and would need a different experiment (allocator diagnostics), not a repeat of run 1.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (from the case file; `positive` with caveats). **Outcome class:** true positive (positive, caps).

**Claim tested:** (B1) For a table with clustering columns, the number of live rows stored in a row-cache entry never exceeds `rows_per_partition` (N), so the entry's off-heap size grows with N until the partition has fewer than N live rows, and total row-cache bytes stay under `row_cache_size`. The cap is on live rows only: a partition whose head is dead rows can exceed N stored rows, and `ALL` and no-clustering tables store the whole partition. "Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g: `cachedLiveRows` = N for N below 1000, 1000 for ALL/2000 - **Confirmed** (with the predicted overshoots: dead rows, ALL, no clustering) | caps (soft: live rows only, with the bypasses B1 lists) | run 1 + self-check | 2026-10-26 |
| Cluster | B3g: bytes/entry about proportional to N below the byte cap; Size <= 256 MiB - **Confirmed**; `RssAnon` delta above Size by more than 20% and 16 MiB in n10 and n100 recorded as overshoot (cause not isolated) | caps (bytes per entry follow N; cache never above `row_cache_size`) | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): not required (positive estimate). The known-binding byte cap was still run as arm c32: Size stopped at 26.6 MB under 32 MiB with 256 entries, against 2,560 entries at 256 MiB.

**Feedback filed:** the case file's section D "Stage-4 feedback" field updated (the orchestrator commits); amendments of the audit are listed in the same section D; sha256 of the case file after the feedback: `afa48eb9e59a31af36ad06be1d2c1c312350946db61a68a32689422e10a47eef` (the prediction and conclusions text of B2 and B3 is unchanged: hashes in §1 re-computed and equal).
