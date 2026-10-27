# cql-row-limit-hasEnoughLiveData-rowLimit--autonomous — stage-4 results  <!-- file: results/cql-row-limit-hasEnoughLiveData-rowLimit--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`cql-row-limit-hasEnoughLiveData-rowLimit--autonomous`](../../stage3-ai-deep-read/cases/cql-row-limit-hasEnoughLiveData-rowLimit--autonomous.md)
>
> **Status:** run 1 done and self-checked (2026-10-27); verdict filed; no run 2
>
> **Outcome class:** true negative (estimate negative, effect does not cap)
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
| **Case-file version** | The case file at repository HEAD `93d6365` (untracked there) plus the audit amendments of 2026-10-27 (the orchestrator commits). sha256 of the whole file after the amendments (frozen before any reading): `4ccc43036a193fd568fe0de579352d08f459a7685f07db45b2347f1b6d466d0c`. sha256 of the unit prediction and conclusions text (`awk` from the line starting `**B2f.` to the line before `**B2h.`): `82e5a4e0fc7508cab46ecd233d80553db14ac6f950111254f258fb621c2c36ac`; of the cluster text (from `**B3f.` to the line before `**B3h.`): `f07077a38ba729acc4eb75576e93fe543ba65df288e81b4f1537d153d935306c`. The case file changes after run 1 only in section D (feedback). |
| **Harness** | `harness/cql-row-limit-hasEnoughLiveData-rowLimit--autonomous/` (written after the audit and before run 1; not committed by this agent; file list in its README). |
| **Tiers and values** | Unit (B2): R in {100, ALL, 500}, L in {1, 50, 100, 101, 1000, 1000000, no limit}. Cluster (B3): 11 arms of one node lifetime each: R=100 / S=64 MiB with L in {1000, 10, 100, 100000, none}; R=ALL / S=64 MiB with L in {100, none}; positive control R=ALL, L=100 at S=64 MiB (`a100`) against S=256 MiB (`s256`); cache off with L in {10, 1000, none}. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-27 (amendments in the case file's section D; no reading existed when they were made). |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the limit is a row count of the *result*, not a memory or disk quantity. The quantity the claim is about (B1) is the off-heap row-cache bytes and the process memory; both are named and measurable. Accepted: it is a negative-estimate case whose point is that the knob does not bound them. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b 7 values of L incl. no limit (the default); B3b 5 values. |
| A. Core question | real resource measured, not only the counter (gap named) | Met after amendment | B2d `weightedSize`, heap; B3d Size gauge, `RssAnon`, heap. Gap named: RSS carries the result pages; amended with cache-off arms so the cache-attributable part can be separated. |
| A. Core question | usage driven to the limit and past it | Met after amendment | The limit under test is a row count compared with 100 cached rows: L below, at (100) and above (101+) the boundary. The byte cap of the cache is reached only by the control (`a100`, `s256`); R=100 holds about 4 MB. |
| B. Logic | each step says what it establishes | Met | B2e / B3e numbered steps, B2g / B3g meanings. |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f / B3f were partly qualitative ("about 5x", "< few MiB"); numbers and tolerances added. R='ALL' rows added (see below). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g / B3g: flat, grows, no flip, control fails; others fall to "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The "ceiling" is the cap that does bind (`rows_per_partition`, `row_cache_size`: R=500 and S=8 MiB arms); the branch evidence is the hit / out-of-range flip at L=101 and the direct call's return value. |
| B. Logic | alternative explanations and their controls | Met after amendment | Positive controls: R=500 (unit), `a100` (S=64 MiB) against `s256` (S=256 MiB) (cluster; originally "lower S to 8 MiB with R=100", which cannot bind: 200 x 100 rows is about 4 MB; and R=ALL at 8 MiB stores nothing, found at the instrument check: OHC segments are smaller than one 428 KB entry). Cache-off arms and a `setRowCacheCapacityInMB(0)` negative control added. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly, fixed | The 200,000-read / 5-min windows and the unspecified control were replaced by exact windows and arms. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly, fixed | Amended (B2e-f, B3b-f). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc12: JDK 11, Ant, Python driver from the earlier row-cache harnesses (copied to the work dir); the harness is copied and adapted from `rows_per_partition-isFilterFullyCoveredBy-...--autonomous`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | 80 MB of data on tmpfs; 11 arms x about 5 min. The original `/local/scratch` and 200,000 reads x 5 L x 5 min were not affordable. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after correction | Verified: `DataLimits.java:349,365-370,407-431` (target `:414`, `:417`); `ColumnFamilyStore.java:1931` (cited `:1930`, corrected), `:1938`; `SinglePartitionReadCommand.java:566,586,604`; `CachedBTreePartition.java:87-109,140`; `CachingParams.java:81`; `PartitionRangeReadCommand.java` call to `isFilterFullyCoveredBy`. **Two findings not in the file, amended:** `rows_per_partition='ALL'` short-circuits at `:1931`, so `hasEnoughLiveData` is never called for it; "no limit" is `DataLimits.NONE`, which overrides `hasEnoughLiveData` to return false (`DataLimits.java:50-56`) and never reaches `:414`; a paged query with a limit above the page size runs with `forPaging(5000)`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Citation `:1930` -> `:1931`; R='ALL' bypasses the check | Applied 2026-10-27 (A3 step 3) | Without it, the R='ALL' arm would be predicted as flipping at L=101. |
| 2 | "No limit" is `DataLimits.NONE` and paging replaces the limit by the page size | Applied 2026-10-27 (A1, B2b, B3b) | The effective limit at `:414` is not the value typed in the query for L above 5000. |
| 3 | B2f numeric: per-R direct-call table, exact `weightedSize`, heap < 8 MiB, R=500 ratio 4.5-5.5, negative control | Applied 2026-10-27 (B2e, B2f) | Predictions were qualitative. |
| 4 | B3 arms, data, window, numbers, `a100` / `s256` control, cache-off arms | Applied 2026-10-27 (B3a-B3h) | See audit rows above. |
| 5 | Instrument check on small data: the 8 MiB control with R='ALL' cached nothing (OHC segments); ALL arms cache only part of the set. Control (now 256 MiB: about 128 OHC segments, so 128 MiB would store about 68 MB against the 64 MiB arm's 43 MB, too close) and ALL predictions amended (still before any run reading) | Applied 2026-10-27 (B3b, B3f, B3h, section D item 5) | Found by a shakedown, not a reading. |
| 6 | The case's Ground says the row cache is "bounded by `row_cache_size` ... and `rows_per_partition`"; both are caps on entry size; no change needed | No change | Consistent with B1. |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-27 (unit 00:57 MDT, cluster 00:58-01:31 MDT) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876...`), 40 cores, 251 GiB; port slot 4 (127.0.4.1, JMX 7140) | not done |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | unit `~/s4-b11-c74` (`ant build-test`) and node `~/s4-b11-c74-n` (`ant jar`), both `copy-source.sh` of `cassandra-5.0.9` at repository commit `93d6365` (the repository's `cassandra/cassandra-5.0.9/` was clean); local baselines `0800015` and `02e3fe2` | |
| Case-file commit / harness commit | case file untracked at `93d6365`, sha256 in §1; harness not committed by this agent. `selfcheck.py` was changed once after run 1 (one check rewritten, §5) | |
| Storage for node data | tmpfs `/dev/shm/s4-b11-c74` (about 200 MB of data); unit-test data in the test's temporary directory under the unit tree | |
| Full logs (path, outside the repo) | `~/s4-b11-c74-logs/run1/{unit,cluster}/` on `pc12` (shakedowns in `~/s4-b11-c74-logs/shake-*`, the discarded first unit pass in `~/s4-b11-c74-logs/run0-defective/`; none used as readings) | |

## 3. Runbook defects

Found at the instrument check (shakedown on small data, before run 1; fixed in the case file with dated amendments, the tier had not started): (1) the B3b control "lower S to 8 MiB" cannot bind with R=100 (about 4 MB cached) and with R='ALL' stores nothing, because the OHC row cache splits its capacity into segments and an entry (428 KB) larger than a segment is not stored; the control is now R='ALL', L=100 at 64 MiB (`a100`) against 256 MiB (`s256`). (2) The B3f prediction "RowCacheHit +10,000" for the ALL arms ignores that part of the set is not cached; now Hit + Miss = 10,000, out-of-range 0. The claim and the meaning of the readings did not change.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown | B3b / B3h / B3e | control at 8 MiB cannot bind or stores nothing | arms `a100` and `s256` | 2026-10-27 | orchestrator commits |
| 2 | shakedown | B3f | ALL arms: Hit = all reads is wrong | Hit + Miss = reads, out-of-range 0 | 2026-10-27 | orchestrator commits |
| 3 | first unit pass (discarded) | B2e (6) | The test did not remove the entries of earlier arms' tables, so `weightedSize` (the whole cache) was cumulative: base 11,215 (R=100), 122,322 (ALL), 177,864 (R=500) and the control ratio read 15.9. Every other check of that pass held (1 mismatch of 454; `results/.../run0-defective-unit/excerpt.txt`). Harness fix only (the arm now invalidates all earlier tables' entries and records `pre.size` = 0, checked by the analyzer); no prediction, row or knob changed; the unit tier was run again from the start. Disclosure: the defect was found by reading that pass's output, so the discarded pass is a reading; the prediction text (frozen hashes in §1) was not touched. | 2026-10-27 | n/a (harness only) |

## 4. Run 1

**Scope:** unit tier (B2) at full scale (1000-row partition; R in 100, ALL, 500; L in 1, 50, 100, 101, 1000, 1000000, none; three shuffled rounds; cache-off control) and cluster tier (B3): `ks.t` 200 partitions x 2000 rows x 200 B, 11 arms of one node lifetime each (l1000, l10, l100, l100k, lnone, a100, anone, s256, off10, off1000, offnone), 10,000 random reads per window. **Command log:** `cql-row-limit-hasEnoughLiveData-rowLimit--autonomous/run1/` (`unit/session.log`, `cluster/session.log`, `run1-chain.out`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/raw/unit.txt`; analyzer `run1/unit/summary.txt`: 457 of 457 checks ok, class "claim holds")

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| first trigger: R=100 leaves a 100-row entry and the direct call for L=100 is true | OK (`cachedLiveRows` 100, `rowCount` 100) | `unit.txt` `firsttrigger=OK`, `R100.entry.*` |
| cache empty before each arm | `pre.size` 0 in all three arms | `unit.txt` `R*.pre.size` |
| R=100, direct `hasEnoughLiveData`, 3 rounds | true for L = 1, 50, 100; false for 101, 1000, 1000000, none | `unit.txt` `R100.r*.L*.direct` |
| R=100, CQL read counters | L = 1, 50, 100: `rowCacheHit` +1; L = 101, 1000, 1000000, none: `rowCacheHitOutOfRange` +1; `rowCacheMiss` 0 | `unit.txt` `R100.r*.L*.hit/oor/miss` |
| R=ALL (1000 rows cached) | direct true for L <= 1000, false for 1000000 and none; the read is a hit for every L (the `:1931` short-circuit) | `unit.txt` `RALL.r*.L*.*` |
| R=500 | direct true for L <= 500, false above; read hit for L <= 500, out-of-range above | `unit.txt` `R500.r*.L*.*` |
| `weightedSize` and `size()` after each of the 63 reads (3 arms x 3 rounds x 7 L) | equal to the arm's base value on every read: 11,213 (R=100), 111,108 (ALL), 55,538 (R=500) | `unit.txt` `*.weighted`, `*.size` |
| used heap after `System.gc()` | spread over all reads of an arm: 2.10 MB (R=100), 0.34 MB (ALL), 0.77 MB (R=500), limit 8 MiB | `summary.txt` |
| positive control R=500 / R=100 `weightedSize` | 55,538 / 11,213 = 4.953 (limit 4.5-5.5) | `summary.txt` |
| negative control, capacity 0 | cache disabled, counters 0, no entry | `unit.txt` `NEG.*` |
| information: thread-allocated bytes per read | 59 KB to 856 KB, rising with the number of rows returned (e.g. R=100: L=50 about 60-190 KB, L=1000 856 KB) | `unit.txt` `*.allocBytes` |

**Cluster tier** (`run1/cluster/<arm>/ckpt.jsonl`; analyzer `run1/cluster/summary.txt`: 67 of 67 checks ok). Sizes are the OHC `Size` gauge in bytes; counters are window deltas (10,000 reads).

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| R=100, S=64 MiB, L = 10 / 100 | l10, l100 | Size, Entries; Hit / OutOfRange / Miss | 4,286,517 B, 200 entries; 10,000 / 0 / 0 | `l10/ckpt.jsonl`, `l100/ckpt.jsonl` |
| R=100, S=64 MiB, L = 1000 / 100000 / none | l1000, l100k, lnone | same | 4,286,517 B, 200 entries in all three; 0 / 10,000 / 0 | `l1000`, `l100k`, `lnone` `/ckpt.jsonl` |
| R=100, all five L | | Size spread | 0 (identical to the byte), and unchanged from `populated` to `window` and `idle` | `*/ckpt.jsonl`, `*/jmx.csv` |
| R=ALL, S=64 MiB, L = 100 / none | a100, anone | Size, Entries; Hit / OutOfRange / Miss | 44.7 MB (44,725,190 and 44,721,120), 105 entries; 5163 / 0 / 4837 and 5232 / 0 / 4768 | `a100`, `anone` `/ckpt.jsonl` |
| R=ALL, S=256 MiB, L = 100 (positive control) | s256 | Size, Entries; Hit / OutOfRange / Miss | 84,336,535 B, 198 entries (against 44.7 MB and 105 at 64 MiB); 9912 / 0 / 88 | `s256/ckpt.jsonl` |
| cache off (S=0), L = 10 / 1000 / none | off10, off1000, offnone | Size, Entries, counters | 0, 0, all counters 0 | `off*/ckpt.jsonl` |
| first trigger | l1000 | after populate / after first window | Entries 200; OutOfRange 10,000 | `cluster/session.log` "FIRST-TRIGGER CHECK" |
| `RssAnon` idle minus baseline (MiB), on-arm / cache-off arm | | | l10 104 / off10 126; l100 76 / off10 126; l1000 118 / off1000 106; l100k 177 / offnone 222; lnone 207 / offnone 222; a100 149; anone 284; s256 177. Attributable (on minus off, same L class): -21.5, -49.9, +12.3, -44.8, -15.2 MiB, spread 62.3 MiB | `summary.txt`, `*/ckpt.jsonl` |
| all arms | | node log, shutdown | no `ERROR` line in any arm's `system.log` segment; start-up row-cache capacity 64, 256 or absent as configured; node stopped by `nodetool drain` and SIGTERM, "daemons left: []" | `*/system.log.segment`, `cluster/session.log` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit under test was crossed in both directions: L = 100 against 100 cached rows gives a true return and a hit, L = 101 gives false and an out-of-range read, in the direct call and the CQL read [observed: `unit/raw/unit.txt` `R100.r*.L100/L101.*`]; in the cluster L <= 100 gave 10,000 hits and L >= 1000 gave 10,000 out-of-range reads, so the check ran on every window read [observed: `l10`, `l100`, `l1000`, `l100k`, `lnone` `ckpt.jsonl`]. "Hold fixed" settings: same data and read keys in every arm (seed 74, 10,000 reads, 4 clients) [observed: `cluster/session.log` CLIENT_DONE lines, selfcheck]; one cold node lifetime per arm with a pre-touched heap and the cache empty at `baseline` [observed: `*/ckpt.jsonl`, `cluster/session.log`]; R as set on the table and read back from `system_schema.tables` [observed: `cluster/session.log` "schema caching ="]; S as configured [observed: `*/system.log.segment` "Initializing row cache"]. First-trigger checks passed in every arm [observed: `cluster/session.log`; unit `firsttrigger=OK`]. The control moved: R=500 stored 4.953x the bytes of R=100, and S=256 MiB stored 84.3 MB where 64 MiB stored 44.7 MB [observed: `unit/summary.txt`, `a100`, `s256` `ckpt.jsonl`].
2. **Readings** — unusual: (a) at 64 MiB with R='ALL' only 105 of 200 entries (44.7 MB of about 86 MB) are stored, and at 256 MiB 198; the cap is per OHC segment, so a partial fill is normal and the hit/miss split follows it [observed: `a100`, `anone`, `s256`]; (b) raw `RssAnon` rose 76 to 284 MiB between `baseline` and `idle` in the on-arms, and 106 to 222 MiB in the cache-off arms, with the larger rises at the larger result sizes (L=1000, 100000, none) [observed: `*/ckpt.jsonl`]; (c) the attributable part (on minus off) is within -50 and +12 MiB and the cache itself is 4.1 MiB, so the rise is the result pages, not the cache [inferred: the cache-off arms rise as much; they hold no cache]; (d) the attributable spread, 62.3 MiB, is close to the 64 MiB tolerance of the secondary check and is noise between separate JVM lifetimes (negative values show it) [inferred]; (e) the original B3f clause "RSS/heap differ by < 10% between L values" is not what was measured: it was replaced before the run by the attributable criterion (§1, case file B3f).
3. **Matched row** — unit B2g row 1, "`weightedSize` constant across L; flips from hit to out-of-range at L = 101; control R = 500 raises `weightedSize` ~5x | Claim confirmed": constant on all 63 reads, flip between 100 and 101, ratio 4.953 [observed: `unit.txt`, `summary.txt`]. Cluster B3g row 1, "Row cache size and RSS plateau independent of L; out-of-range counter rises for L > R; ... | Claim confirmed (control moves, L does not)": Size 4,286,517 B and 200 entries for all five L, out-of-range 10,000 for L >= 1000 and 0 for L <= 100, control `s256` moves Size from 44.7 to 84.3 MB, attributable RSS within 12.3 MiB above zero [observed: `*/ckpt.jsonl`, `summary.txt`]. The B2f R='ALL' rows and the B3f ALL rows (no out-of-range, Hit + Miss = 10,000) also hold.
4. **Excluded rows** — B2g "`weightedSize` or retained heap grows with L": excluded, constant on every read and heap spread at most 2.1 MB [observed: `unit.txt`, `summary.txt`]. "No flip at L = 101": excluded, direct false at 101, true at 100, in all rounds [observed: `unit.txt`]. "Control does not move `weightedSize`, or cache never populated": excluded, ratio 4.953 and entries present [observed: `unit.txt`]. B3g "Row cache size or RSS grows monotonically with L": excluded, Size identical across L and the attributable RSS does not rise with L (-21.5, -49.9, +12.3, -44.8, -15.2 MiB for L = 10, 100, 1000, 100000, none) [observed: `summary.txt`]. "S change does not move cache size, or cache stays empty": excluded, 44.7 -> 84.3 MB and 105 -> 198 entries [observed: `a100`, `s256`]. "Hit ratio unchanged across L": excluded, it changes from 100 % to 0 % at L > 100, as predicted for a 2000-row partition with R=100 [observed: `l100`, `l1000`].
5. **Observed vs. inferred** — Inferred: (i) that the cluster's row limit at `:414` is `L` for L <= 1000 and 5000 for L = 100000 and none (paging): the counters only show that the read took the out-of-range path [inferred: source, `SelectStatement.java:338`, `SinglePartitionPager.java:90`]; (ii) that the cap comes from `rows_per_partition` and `row_cache_size` and not from `rowLimit` [inferred: the control arms move Size, L does not]; (iii) that the extra `RssAnon` in the large-L arms is the result pages [inferred: the cache-off arms with the same L show the same rise].
6. **Deviations and gaps** — the audit amendments and the shakedown findings (§1, §3); the first unit pass was discarded and the unit tier re-run from the start after a harness defect (§3, defect 3); the unit tier measures no `RssAnon` and the cluster tier does not read individual entries (only the unit tier reads `cachedLiveRows`); `RssAnon` is a noisy reading between JVM lifetimes (negative attributable values); no run 2. The R=100 cache holds 4.3 MB, so the 64 MiB cap is not reached by R=100; the byte cap is shown only with R='ALL'.
7. **Core question** — No: the per-query `LIMIT` does not cap, and usage does not follow it. In the unit tier the cache's `weightedSize` is the same after every one of 63 reads with L from 1 to none, while L = 101 flips the read from a cache hit to an out-of-range read, and `rows_per_partition` (R=500) multiplies the bytes by 4.95. In the cluster the row cache holds 4,286,517 B in 200 entries for every L, the out-of-range counter follows L exactly, and the caps that do bind (`row_cache_size`: 44.7 MB at 64 MiB, 84.3 MB at 256 MiB) move the plateau. The check at `:414` only decides whether the cached partition may answer the query.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 — Confirmed (the `LIMIT` does not cap memory; the real caps are `rows_per_partition` and `row_cache_size`).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed the raw files without the analyzers (unit: the test's own `STAGE4` echo lines in `ant.log` against `unit.txt`, and the direct/hit/out-of-range rule re-derived from `DataLimits.java:414-417` for all 63 reads; cluster: the CKPT lines of `session.log` against `ckpt.jsonl`, the 5-second `jmx.csv` and `rss.csv` samples, each arm's start-up capacity line, error lines, client counts and returned rows): 122 checks, 0 FAIL (`run1/selfcheck.txt`). Its first version had one check that compared a 5-second sample taken inside a fast window (3 arms) with the checkpoint taken after it and failed (3 FAIL, `run1/selfcheck-v1.txt`); the check was rewritten to compare the quiet samples after the window with the checkpoint, and no reading or analyzer was changed.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster/session.log`: first-trigger checks ok in all arms, schema read-back, one node lifetime each; `selfcheck.txt` confirms capacity lines (64, 256, none), 4 clients and 10,000 ok reads per window, "daemons left: []" |
| 2. Readings | yes | `*/ckpt.jsonl` re-read: Size 4,286,517 in all five R=100 arms; RSS numbers recomputed in `summary.txt` and by hand from `idle` and `baseline` |
| 3. Matched row | yes | `unit.txt` 63 reads, rule recomputed independently in `selfcheck.txt`; cluster counters from `ckpt.jsonl` and 5 quiet `jmx.csv` samples per arm |
| 4. Excluded rows | yes | the constant Size and the control arms re-read; attributable RSS values re-derived |
| 5. Observed vs. inferred | yes | the three inferred statements are inferences; none is needed for the Confirmed row except (ii), which the control arms support |
| 6. Deviations and gaps | yes | defect log in §3 matches the harness README |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 -> flat Size across L, flip at 101, control moves -> B2g/B3g row 1 |

### 5.2 Run 2?

**No**, 2026-10-27. Both tiers matched the confirmed row without an unmatched part that bears on the claim; the one soft reading (raw `RssAnon` rising with L) is explained by the cache-off arms, which were part of the design. A second run would not change the verdict.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2). §7 is left out.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1 — memory used by the row cache (and the node) does not follow the per-query `LIMIT` value evaluated at `DataLimits.java:414`: varying `LIMIT` over a fixed cached partition changes only hit vs hit-out-of-range counters, not cache weight or heap/off-heap. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: `weightedSize` constant across L, flips to out-of-range at L = 101, control R=500 raises it 4.95x — **Confirmed** | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | B3g row 1: Size and attributable RSS independent of L, out-of-range follows L, control (capacity 64 -> 256 MiB) moves Size 44.7 -> 84.3 MB — **Confirmed** | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control:** unit, `rows_per_partition` 500 against 100 on the same workload and instruments: `weightedSize` 55,538 against 11,213 B (4.953x). Cluster, R='ALL' with `row_cache_size` 64 MiB against 256 MiB: Size 44.7 against 84.3 MB and 105 against 198 entries. Cache-off arms gave Size 0 and zero counters.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (the orchestrator commits). Items for stage 3: `rows_per_partition='ALL'` never reaches `:414`; "no limit" is `DataLimits.NONE`; the OHC row cache splits its capacity into segments and stores no entry larger than a segment (an 8 MiB cache with 428 KB entries stored nothing; 64 MiB stored 105 of 200). No upstream bug found.

Case-file sha256 after the section D feedback (2026-10-27): `48896caa44422d530ea324416bc8c0300fe1a053b494febc84d572e15b417719` (only section D differs from the frozen version in §1). Timing log note: the first `unit-run` / `cluster-run` start lines (06:55) belong to the discarded first pass (§3, defect 3).
