# rows-per-partition-hasEnoughLiveData-rowLimit--autonomous — stage-4 results  <!-- file: results/rows-per-partition-hasEnoughLiveData-rowLimit--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`rows-per-partition-hasEnoughLiveData-rowLimit--autonomous`](../../stage3-ai-deep-read/cases/rows-per-partition-hasEnoughLiveData-rowLimit--autonomous.md)
>
> **Status:** run 1 done and self-checked (2026-10-27); verdict filed; no run 2
>
> **Outcome class:** true positive (estimate positive, effect caps; the per-partition row cap and the byte cap both held, the LIMIT at line 417 moved no memory)
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
| **Case-file version** | The case file at repository HEAD `93d6365` (untracked there) plus the audit amendments of 2026-10-27 (case file section D1; the orchestrator commits). sha256 of the whole file after the amendments (frozen before any reading): `940180fd2d1f2069f7fb3d3848fad97844ee0769b632d764fd19e5a2c5396b83`. sha256 of the unit prediction and conclusions text (`awk` from the line starting `**B2f.` to the line before `**B2h.`): `90b604ff6c2161a0ea571371a54978a61a283d0d73f961a6ba4a4fdbe6e9a989`; of the cluster text (from `**B3f.` to the line before `**B3h.`): `a6041ddb3efdcf6a87bb2326a83fcf62dd1d63723f88ea8955481cf97ccb6a81`. The case file changes after run 1 only in section D (feedback); its sha256 then is recorded in §8. |
| **Harness** | `harness/rows-per-partition-hasEnoughLiveData-rowLimit--autonomous/` (written after this freeze and before run 1; listed in its README; not committed by this agent). |
| **Tiers and values** | Unit (B2): `rows_per_partition` N in {5, 50, ALL, NONE}, LIMIT L in {1, 4, 5, 6, 49, 50, 51, 1000} on one 200-row partition; variants TTL, TOMB, NOCK. Cluster (B3): `ks.t` 20,000 partitions x 200 rows x 100 B, `row_cache_size` 256 MiB, arms n5, n50, nall, none (control), t5 (`ks.t2`, tombstones); passes P1 LIMIT 1, P2 LIMIT 100, P3 LIMIT 1. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-27 (amendments are in the case file's section D1; no reading existed when they were made). |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: off-heap OHC bytes of the row cache; the per-partition knob is a row count with a derivable size (about 150 B per 100-character row). The entry line (417) itself is declared not a cap (Estimate, A3 step 5). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b N in {5, 50, ALL, NONE (the default)}, B3b the same; the LIMIT (the operand at line 417) is varied over 8 values in the unit tier and 1 / 100 / 1 in the cluster. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly, fixed | B3d measures `RssAnon` and the OHC gauges; the unit tier cannot see native bytes (serialized size and `memUsed` are proxies; gap named in B2d). Amended: the RSS rule is net of the NONE arm and decidable (B3g). |
| A. Core question | usage driven to the limit and past it | Met after amendment | The row cap binds (200-row partitions above N=5 and 50); the byte cap binds only in nall (20,000 x about 30 KB = 600 MB > 256 MiB). The filed 64 MiB made N=50 bind the byte cap too (about 156 MB), which would confound the LIMIT comparison there; amended to 256 MiB. |
| B. Logic | each step says what it establishes | Met | B2e / B3e numbered steps; B1 splits the claim into (i) and (ii). |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | The filed B2f covered N=5 only and B3f was in 'about' terms with an arithmetic error at N=50; rewritten with exact values and tolerances. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after amendment | Added rows for LIMIT-dependent memory, N not moving usage, a differing hit pattern, setup error. Uncovered outcomes fall to Not confirmed (no matching row). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after amendment | Ceiling = entry rows / bytes per entry follow N and Size <= Capacity; disallow evidence = the out-of-range counter (+20,000 at P2 for n5, n50; unit: out of range for L > N) with unchanged Size. |
| B. Logic | alternative explanations and their controls | Met | NONE arm; N=5 / 50 / ALL as the N-moves-usage control; t5 for dead rows; RSS net of NONE. Positive-claim file (the memory is capped), so the negative-claim positive control is not required; claim (i) is "LIMIT does not move usage" and its control is N. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly, fixed | B2e/B3e omitted the passes, the per-L protocol, the tombstone table and the hit/out-of-range expectations; amended. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly, fixed | Dataset, passes, sampling (5 s, checkpoints), tolerances and the first-trigger check made exact (B3b-B3f). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc12 has JDK 11.0.32.1, Ant 1.10.12 and `~/cassandra-run1` (not used: `copy-source.sh` trees `~/s4-b11-p75-u`, `~/s4-b11-p75-n`); the Python driver is unzipped from `lib/cassandra-driver-internal-only-3.29.0.zip`; the Jmx reader, loader and run script are adapted from the earlier row-cache harness (`harness/rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous/`). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | 4 M rows x about 150 B = about 0.6 GB on a tmpfs (126 GiB free on `/dev/shm`); the node heap is 2 GiB; nall reaches 256 MiB with 20,000 x about 30 KB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked 2026-10-27: `DataLimits.java:349,407-431` (`:414`, `:417`), `ColumnFamilyStore.java:1920-1941,3259-3262`, `SinglePartitionReadCommand.java:491,528-539,546-558,575-598`, `CachedBTreePartition.java:86-115` (`rowsWithNonExpiringCells`), `ClusteringIndexSliceFilter.java:76-90`, `OHCProvider.java:40-43,97-100`, `CacheService.java:327`, `Config.java:473-474`, `test/conf/cassandra.yaml:44-45`. Corrected: `CachingParams.java` ALL at `:55`/`:143`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B2a: no row-cache setup in the unit test; `copy-source.sh` tree | Applied 2026-10-27 (B2a) | The setter is a no-op after `CacheService` initialised; the unit yaml already enables OHC. |
| 2 | B2b-B2f: per-L protocol, exact predictions for N = 5, 50, ALL, NONE, TTL, TOMB, NOCK | Applied 2026-10-27 (B2b-B2g) | Filed text only covered N=5; the re-count branch of `hasEnoughLiveData` needs rows with expiring or dead cells. |
| 3 | B3a/B3b: `row_cache_size` 256 MiB, tmpfs, N in {5, 50, ALL, NONE} | Applied 2026-10-27 (B3a, B3b) | 64 MiB binds at N=50 (about 156 MB) and confounds the LIMIT comparison; local disk is shared. |
| 4 | B3c/B3e: passes P1-P3, one node lifetime per arm, unprepared reads, separate tombstone table, no 10-minute duration | Applied 2026-10-27 (B3c, B3e) | Exactness; earlier case found stale prepared statements and allocator carry-over. |
| 5 | B3f/B3g: numbers, exact counters, decidable RSS rule | Applied 2026-10-27 (B3f, B3g) | Arithmetic error at N=50; RSS row was not decidable. |
| 6 | B3h/B4: controls and cleanup commands | Applied 2026-10-27 (B3h, B4) | Consistency. |
| 7 | Citation correction `CachingParams.java:55/:143` | Applied 2026-10-27 (A1) | Line drift only. |
| 8 | Estimate wording and an A3 note on `RowCacheHitOutOfRange` | Left for stage 3 | Does not change the claim or the run. |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-27 (unit 00:49 MDT, load 00:49-00:54, arms 00:55-01:03, all MDT) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876...`), 40 cores, 251 GiB; port slot 5 (127.0.5.1) | not done |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | unit `~/s4-b11-p75-u` (`ant build-test`, 1 min 11 s) and node `~/s4-b11-p75-n` (`ant jar`, 1 min 16 s), both `copy-source.sh` of `cassandra-5.0.9` at repository commit `93d6365` (`git status` of `cassandra/cassandra-5.0.9` empty); local baseline commits `d984198` and `71397c6` | |
| Case-file commit / harness commit | case file untracked at `93d6365`, sha256 in §1; harness not committed by this agent | |
| Storage for node data | tmpfs `/dev/shm/s4-b11-p75` (460 MiB uncompressed load, 545 MB used); unit-test data in the test's temporary directory under the unit tree | |
| Full logs (path, outside the repo) | `~/s4-b11-p75-logs/run1/{unit,cluster}/` and `~/s4-b11-p75-logs/run1-chain.out` on `pc12` (shakedowns in `~/s4-b11-p75-logs/shake-*`, not used) | |

## 3. Runbook defects

None found in the audited text after the amendments (changes made at the audit are in §1.1 and the case file's section D1). No harness defect appeared in the shakedowns. One defect in the **self-check script** (not a reading): its first version compared `nodetool info`'s cache-level "hits" with the table's `RowCacheHit` alone and failed for n5 and n50 (40,000 vs 20,000); the cache-level figure counts every lookup that found the key, that is hits plus out-of-range hits (20,000 + 20,000). The check was corrected to that rule; no reading or analyzer was changed.

## 4. Run 1

**Scope:** unit tier (B2) at full scale (200-row partition; N in 5, 50, ALL, NONE; L in 1, 4, 5, 6, 49, 50, 51, 1000; variants TTL, TOMB, NOCK) and cluster tier (B3): `ks.t` 20,000 x 200 x 100 chars, `ks.t2` 2,000 x 200 with ck 0-99 deleted; arms n5, n50, nall, none, t5, each its own node lifetime, `row_cache_size` 256 MiB; passes P1 LIMIT 1, P2 LIMIT 100, P3 LIMIT 1; n50 then the informational `setcachecapacity 0 8 0`. **Command log:** `rows-per-partition-hasEnoughLiveData-rowLimit--autonomous/run1/` (`unit/session-excerpt.txt`, `cluster/session-excerpt.txt`, `run1-chain.out`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/unit.txt`; analyzer `run1/unit/summary.txt`: 105 of 105 primary checks ok, class "claim holds"; ant: 1 test, 0 failures)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| first trigger: N=5 leaves an entry after the populate read | OK | `unit/unit.txt` `firsttrigger=OK` |
| `rowCount` = `cachedLiveRows` for N = 5, 50, ALL | 5/5, 50/50, 200/200 (partition of 200 live rows) | `unit/unit.txt` `5.populate.*`, `50.populate.*`, `ALL.populate.*` |
| `hasEnoughLiveData(L)` and `isFilterFullyCoveredBy(L)` for N=5 | true for L = 1, 4, 5; false for L = 6, 49, 50, 51, 1000 | `unit/unit.txt` `5.L*.hasEnough`, `5.L*.covered` |
| same for N=50 | true for L <= 50; false for 51, 1000 | `unit/unit.txt` `50.L*` |
| same for N=ALL | covered true for every L; `hasEnoughLiveData` true for L <= 200, false for 1000 | `unit/unit.txt` `ALL.L*` |
| read with LIMIT L: counter deltas | N=5: hit for L <= 5, `HitOutOfRange` for L >= 6, never a miss; N=50: threshold 50; ALL: hit for all L | `unit/unit.txt` `*.L*.dHit/dOut/dMiss` |
| entry shape, `size()`, `weightedSize()` before vs after the L reads | identical in all arms (N=5: 597 B, `memUsed` 694; N=50: 5,550 B, 6,341; ALL: 22,184 B, 28,622) | `unit/unit.txt` `*.populate.*` vs `*.after.*` |
| serialized size vs N | 597, 5,550, 22,184 B; size(50)/size(5) = 9.30 | `unit/unit.txt` |
| `NONE` | no entry; hit = miss = outOfRange = 0; `isRowCacheEnabled` false | `unit/unit.txt` `NONE.*` |
| TTL variant (N=5) | `rowCount` 5, `rowsWithNonExpiringCells` 0; `hasEnough` true for L = 1, 5 (re-count), false for 6 | `unit/unit.txt` `TTL.*` |
| TOMB variant (N=5, ck 0-49 deleted) | `cachedLiveRows` 5, `rowCount` 55; `hasEnough` true for L = 1, 5, false for 6 | `unit/unit.txt` `TOMB.*` |
| NOCK (no clustering columns, N=5) | `cachedLiveRows` = `rowCount` = 1 | `unit/unit.txt` `NOCK.*` |

**Cluster tier** (`run1/cluster/<arm>/ckpt.jsonl`, `jmx.csv`; analyzer `run1/cluster/summary.txt`: 23 of 25 primary checks ok; the 2 mismatches are the `RssAnon` rows of n5 and n50). Sizes are the OHC `Size` gauge in bytes; MB are 10^6.

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| N=5, 256 MiB | n5 | Size, Entries after P1; bytes/entry | 14,099,113 B, 20,000 entries; 705 B/entry | `n5/ckpt.jsonl` |
| N=5 | n5 | Size and Entries after P2 and P3 | identical to P1 (14,099,113 B, 20,000) | `n5/ckpt.jsonl` |
| N=5 | n5 | table counters from `baseline` | P1 miss +20,000; P2 `HitOutOfRange` +20,000, hit +0; P3 hit +20,000 | `n5/ckpt.jsonl` |
| N=50 | n50 | Size, Entries; bytes/entry | 114,891,148 B, 20,000 entries; 5,745 B/entry (8.15 x e(5)); unchanged after P2 and P3 | `n50/ckpt.jsonl` |
| N=50 | n50 | table counters | same pattern as n5 (miss +20,000; out of range +20,000, hit +0; hit +20,000) | `n50/ckpt.jsonl` |
| N=ALL | nall | Size, Entries; bytes/entry | 268,370,182 B (cap 268,435,456), 11,904 entries of 20,000; 22,545 B/entry (3.92 x e(50)); max Size at any poll 268,370,382 | `nall/ckpt.jsonl`, `nall/jmx.csv` |
| N=ALL | nall | table counters | P2 and P3: hit +0, out of range +0, miss +20,000 each (a sequential scan of 20,000 keys through 11,904 slots) | `nall/ckpt.jsonl` |
| N=5 on `ks.t2` (ck 0-99 deleted), 2,000 partitions | t5 | bytes/entry | 3,816,988 B, 2,000 entries; 1,908 B/entry, 1,204 B above n5 | `t5/ckpt.jsonl` |
| `NONE` | none | Entries, Size, counters | 0, 0; hit = miss = outOfRange = 0 after P3 | `none/ckpt.jsonl` |
| all arms | | maximum Size over all `jmx.csv` polls | n5 14.1 MB, n50 114.9 MB, nall 268.37 MB, none 0, t5 3.8 MB; none above 268,435,456 | `*/jmx.csv` |
| all arms | | `RssAnon` at P3 minus `baseline`, against Size | n5 +402.7 MB (Size 14.1), n50 +272.6 (114.9), nall +245.4 (268.4), none +47.1 (0). Net of none: 355.6, 225.5, 198.3 MB. The rise is in P1: n5 +369 MB in P1, +13 in P2, +2 in P3; none +28 in P1; t5 (2,000 partitions) +70 | `*/ckpt.jsonl` (`RssAnon_kb`) |
| n50, informational | n50 | `setcachecapacity 0 8 0`, then checkpoints at +5 s, +60 s and after one more LIMIT 1 pass | `Capacity` 8,388,608 but Size 114,891,148 and Entries 20,000 unchanged at all three | `n50/ckpt.jsonl` (`shrunk5s`, `shrunk60s`, `shrunk_p4`) |
| all arms | | no `ERROR` in `system.log`; node stopped by `nodetool drain` and SIGTERM, no daemon left | `*/system.log.warn-error.txt`, `cluster/session-excerpt.txt` ("daemons left: []") |

### 4.2 Conclusion and logic

1. **Validity** - valid. The limits were reached: the row cap binds because the partition (200 live rows) has more rows than N=5 and N=50 [observed: `unit/unit.txt` `5.populate.rowCount=5`, `50.populate.rowCount=50`]; the byte cap (256 MiB) binds in nall (Size 268.37 MB of 268.44 MB, 11,904 entries of the 20,000 read) [observed: `nall/ckpt.jsonl`]. "Hold fixed" settings: dataset and queries identical in every arm, 20,000 rows returned per LIMIT 1 pass and 2,000,000 per LIMIT 100 pass [observed: `*/ckpt.jsonl` `rows_returned`]; each arm a cold JVM with the heap pre-touched and `baseline` entries 0 [observed: `*/ckpt.jsonl`]; `row_cache_size` 256 MiB [observed: `cluster/session-excerpt.txt` "Initializing row cache with capacity of 256 MiBs", `cassandra.yaml.n5`]; the table's `rows_per_partition` set by `ALTER TABLE` and read back [observed: `cluster/session-excerpt.txt` "schema caching ="]. First-trigger checks passed in the unit tier and in every arm [observed: `unit/unit.txt`, `cluster/session-excerpt.txt` "FIRST-TRIGGER CHECK ok"].
2. **Readings** - unusual: (a) `RssAnon` rose 0.2 to 0.4 GB in n5, n50 and nall, far above the cache bytes in n5 (402.7 MB against 14.1 MB) and falling as the cache grew (net 355.6, 225.5, 198.3 MB), the rise occurring in P1 [observed: `*/ckpt.jsonl`]; (b) nall had no hits in P2 and P3 (a 20,000-key sequential scan through a cache of 11,904) [observed: `nall/ckpt.jsonl`]; (c) after the runtime shrink to 8 MiB, Size stayed at 114.9 MB with 20,000 entries for at least 60 s and across a hit-only pass [observed: `n50/ckpt.jsonl`].
3. **Matched row** - unit B2g row 1, "entry shape, `size()` and `weightedSize()` after the L reads equal those after the populate read, for every N; `rowCount` == N (5, 50) and 200 for ALL | claim (i) and the per-partition cap (ii) hold in the unit tier": [observed: `unit/unit.txt` populate vs after lines; `rowCount` 5, 50, 200]. With it, "`rowCount` > N only by the number of dead rows (TOMB: 55)" [observed: `unit/unit.txt` `TOMB.populate.rowCount=55`]. Cluster B3g row 1, "Size <= Capacity at every poll; n5/n50 Size and Entries unchanged by P2 and P3; counters as in B3f; e(N) rises with N | claim (i) and (ii) hold at the cluster tier": max Size 268,370,382 B <= 268,435,456, n5 and n50 unchanged, counters 20,000 / 20,000 / 0 / 20,000, e = 705, 5,745, 22,545 B [observed: `*/jmx.csv`, `*/ckpt.jsonl`]. Not matched as predicted: B3f's "`RssAnon` delta net of none <= 1.5 x Size + 16 MiB" holds for nall (198.3 MB against 419.3 MB) and fails for n5 (355.6 against 37.9) and n50 (225.5 against 189.1); that is the B3g row "above the B3f bound but not above 1.5 x Capacity (402.7 MB) | memory outside the cache accompanying the reads; reported as an overshoot, the Size-based rows still decide" [observed: `cluster/summary.txt`].
4. **Excluded rows** - "`rowCount` > N by many live rows": excluded, `cachedLiveRows` = N for N = 5, 50 [observed: `unit/unit.txt`]. "entry, `size()` or `weightedSize()` differs after the L reads": excluded, equal in all arms [observed: `unit/unit.txt`]. "`weightedSize` and `serializedSize` flat across N": excluded, 694 < 6,341 < 28,622 and 597 < 5,550 < 22,184 [observed: `unit/unit.txt`]. "hit / out-of-range pattern differs from B2f": excluded, every L of every arm matches [observed: `unit/unit.txt`, 105 of 105]. "no entry after the populate read": excluded. Cluster: "Size or Entries of n5 or n50 differ after P2 or P3": excluded [observed: `n5/ckpt.jsonl`, `n50/ckpt.jsonl`]. "Size > Capacity": excluded, maximum 268,370,382 B at the 256 MiB capacity [observed: `nall/jmx.csv`; the n50 shrink phase is informational and discussed in 6]. "e(N) flat across N": excluded, 705 -> 5,745 -> 22,545 B [observed: `*/ckpt.jsonl`]. "RSS net of none > 1.5 x Capacity (402.7 MB)": excluded for all three arms (355.6, 225.5, 198.3 MB), n5 being 47 MB below the line [observed: `cluster/summary.txt`, `selfcheck.txt`]. "counters differ from B3f", "nall Size < 0.85 x Capacity", "t5 e(t5) <= e(5) + 500 B", "first trigger fails": excluded [observed: `cluster/summary.txt`].
5. **Observed vs. inferred** - Inferred: (i) that the entry's row count in the cluster is `cachedLiveRows` = min(N, 200), from bytes/entry rising with N by 8.15x and 3.92x, not from reading the entries [inferred: only the unit tier reads entries; the cluster has Size/Entries]; (ii) that line 417 is the decision point behind the P2 out-of-range count [inferred: the unit tier calls `hasEnoughLiveData` directly and gets false at L > N, and the cluster counters give out of range for every key at LIMIT 100 > N; the cluster cannot see which line returned false]; (iii) that the extra `RssAnon` is the read path of whole-partition reads and the allocator, not the cache [inferred: it arises in P1 (n5 +369 MB, none +28 MB, t5 with 2,000 partitions +70 MB, about 18 to 35 KB per partition read in full), not in P2 and P3 when the cache is unchanged, and it is larger for n5 (14 MB of cache) than for nall (268 MB); the buffer or arena that holds it was not isolated]; (iv) the reason the shrink did not reduce Size [inferred: no evictions occur without puts (the passes after it were hits), consistent with OHC evicting on insert; not tested with a put pass].
6. **Deviations and gaps** - the audit amendments are in §1.1 and the case file's D1. The unit tier measures no native bytes (serialized size and `memUsed` are the proxies named in B2d). The cluster tier reads `RssAnon`, and the `RssAnon` rise is unexplained beyond the inference in part 5. The B3e step "setcachecapacity while loaded" (informational) showed that `Capacity` changes at once but Size does not fall without further inserts; it is outside the frozen predictions and was not followed up with a put pass, so it is reported as an open point rather than a finding on the claim. The `n50` poll maxima in the "Size <= Capacity" check use the 256 MiB capacity; the post-shrink polls (114.9 MB) are above the new 8 MiB capacity and are not counted there. The timing log has two `cluster-run end` lines (the chain's and a duplicate appended by this agent). No run 2.
7. **Core question** - Yes: the constraint caps usage and usage follows it, and the LIMIT at line 417 does not. In the unit tier an entry never holds more live rows than N (5, 50), the LIMIT changes only whether a read is a hit or an out-of-range read (hit iff L <= N), and the entry, its serialized size and the cache's `memUsed` are the same before and after reads at eight LIMITs; in the cluster the bytes per entry follow N (705, 5,745, 22,545 B), Size is equal after LIMIT 1, LIMIT 100 and LIMIT 1 passes in the arms with no eviction, the out-of-range counter rises by exactly the 20,000 keys read at LIMIT 100 > N, and Size never exceeds the 256 MiB capacity (268.37 MB with 11,904 entries in nall). The caps are soft in three ways: dead rows before the live ones are stored too (55 rows for 5 live), `ALL` stores whole partitions (22.5 KB each), and process memory (`RssAnon`) rose 0.2 to 0.4 GB with the reads, not tied to the cache's bytes.

**Conclusion (one line):** unit B2g "entry shape, `size()` and `weightedSize()` equal after the L reads; `rowCount` == N | claim (i) and (ii) hold" and cluster B3g "Size <= Capacity; n5/n50 unchanged by P2 and P3; counters as in B3f; e(N) rises with N | claim (i) and (ii) hold" - confirmed, with the recorded overshoots (dead rows, ALL) and the `RssAnon` overshoot as the unmatched part of B3f.

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/rows-per-partition-hasEnoughLiveData-rowLimit--autonomous/selfcheck.py` re-parsed the raw files without the analyzers (unit: the test's own `STAGE4` echo lines in `ant.log` against `unit.txt`, with the hit / out-of-range / `hasEnoughLiveData` rules re-derived from the B2f text; cluster: the CKPT lines of `session.log`, every 5-second `jmx.csv` poll, the `nodetool info` Row Cache line of each arm (entries, size, hits, requests), `rss.csv` samples and `system.log` segments): 124 checks, 0 FAIL (`run1/selfcheck.txt`). Its first version had one wrong rule (the cache-level hits include out-of-range hits, §3) that failed 2 checks; the rule was corrected and no reading or analyzer was changed.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster/session-excerpt.txt`: every arm shows "FIRST-TRIGGER CHECK ok", the schema read-back, one node lifetime and "daemons left: []"; `*/ckpt.jsonl` baselines have `entries` 0; the row-cache capacity of each arm's start-up line is 256 MiB |
| 2. Readings | yes | the `RssAnon` rows re-read from `*/ckpt.jsonl` and `*/rss.csv` (n5: baseline 2718 MB, P1 3087, P2 3100, P3 3102); `nodetool info` entries, size, hits and requests agree with the gauges for all 5 arms; the shrink-phase values re-read from `n50/ckpt.jsonl` |
| 3. Matched row | yes | unit: all 105 primary checks ok in `summary.txt`, and 61 unit rules re-derived in `selfcheck.txt`; cluster: the e(N) ratios recomputed (8.15, 3.92), the counter deltas 20,000 / 20,000 / 0 / 20,000 recomputed from the checkpoints, equal Size and Entries across P1-P3 recomputed |
| 4. Excluded rows | yes | each excluded row re-checked against the number cited in 4.2 part 4 (max poll 268,370,382 B; net RSS 355.6 / 225.5 / 198.3 MB below 402.7 MB) |
| 5. Observed vs. inferred | yes, with a caveat | the four inferred statements are those that the core question does not rest on alone: (i) and (ii) are supported by two independent readings each; (iii) the cause of the `RssAnon` rise is not isolated, so the conclusion does not claim that the cache explains it; (iv) is not tested |
| 6. Deviations and gaps | yes | the shrink step and the RSS gap are recorded, and the claim does not depend on them |
| 7. Core question - the steps from reading to answer follow the audited logic | yes | B1 (i): LIMIT changes hit vs out of range only (unit direct calls, cluster counters, unchanged Size); B1 (ii): cap per partition (unit `rowCount`) and Size <= Capacity (cluster polls) |

### 5.2 Run 2?

**No** - 2026-10-27. The conclusion rests on direct observations for both parts of the claim (entry contents and exact counters in the unit tier, equal Size / Entries and exact counters in the cluster); the one inferred statement it would need to settle (the `RssAnon` rise) is not part of the claim's rows and a repeat would not isolate it; the result confirms the file's own claim and refutes nothing. Open for the user: whether to follow up the shrink observation (a put pass after `setcachecapacity`) and the `RssAnon` rise.

## 6. Run 2 - fresh AI session (optional)

Not done (see 5.2).

## 7. Comparison - only if run 2 was done

Not applicable.

## 8. Verdict - AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (for the real constraint behind this site, `caching.rows_per_partition` bounded by `row_cache_size`; the entry line itself is not a cap). **Outcome class:** true positive (positive, caps).

**Claim tested:** B1: (i) line 417 is a read-side shortcut: changing the query `LIMIT` changes cache-served vs disk-served reads but never the number of rows held in the row cache; (ii) the number of live rows held per cached partition is at most `rows_per_partition` (plus non-live rows read before the cutoff), and total row-cache bytes never exceed `row_cache_size`.
"Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed - B2g "entry shape, `size()` and `weightedSize()` after the L reads equal those after the populate read; `rowCount` == N (5, 50), 200 for ALL" (dead-row overshoot 55 recorded) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed - B3g "Size <= Capacity at every poll; n5/n50 Size and Entries unchanged by P2 and P3; counters as in B3f; e(N) rises with N" (`RssAnon` overshoot recorded as the unmatched part of B3f) | caps | run 1 + self-check | 2026-10-27 |

**Positive control** (a negative-estimate file only): not applicable (positive estimate). For claim (i), which says the LIMIT moves no memory, the control that the instruments can see memory move is N: bytes per entry rose 705 -> 5,745 -> 22,545 B and `memUsed` 694 -> 6,341 -> 28,622 under the same workload and instruments.

**Case file sha256 after the feedback (section D only changed since the freeze; the B2f-B2g and B3f-B3g texts hash to the frozen values):** `cf0256dcf6126a14ad1d9e4348c5481c0ae7d1c6544544363460a40b3e721a3b`.

**Feedback filed:** the case file's section D "Stage-4 feedback" (below the audit amendments D1) updated; the amendments D1 were made before run 1. Upstream and doc candidates: (1) `nodetool setcachecapacity 0 8 0` on a row cache holding 114.9 MB left Size at 114.9 MB with Capacity 8 MiB for at least 60 s (OHC does not evict on a capacity change in this run; not retested with new inserts), so the runtime shrink of `row_cache_size` does not release memory at once; check JIRA before filing. (2) A read with LIMIT above `rows_per_partition` is a `RowCacheHitOutOfRange` that never re-populates, which is worth one sentence in the caching docs.

**Leftovers on the node:** work trees `~/s4-b11-p75-u`, `~/s4-b11-p75-n`, the driver `~/s4-b11-p75-drv`, logs `~/s4-b11-p75-logs`, (the tmpfs node data `/dev/shm/s4-b11-p75`, 545 MB, was deleted after the run); no Cassandra process of this run is running.
