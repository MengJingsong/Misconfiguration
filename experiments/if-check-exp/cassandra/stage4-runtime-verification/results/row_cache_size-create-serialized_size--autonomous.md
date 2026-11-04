# row_cache_size-create-serialized_size--autonomous — stage-4 results  <!-- file: results/row_cache_size-create-serialized_size--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`row_cache_size-create-serialized_size--autonomous`](../../stage3-ai-deep-read/cases/row_cache_size-create-serialized_size--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true positive** (estimate `positive`, effect `caps`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D, not §10.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `627b1ec`; the case file is **untracked** in the working tree at this date, so no commit holds it. **sha256 of the whole file after the audit's amendments (A3 citation fixes, B2i and B3i, dated 2026-10-25): `23f4b160fd23a0326d41136393916e0b652fac8d54c9023483e6c8c21e1bb9cd`.** Recorded 2026-10-25 before any reading of the run; the prediction and conclusions tables (B2f, B2g, B3f, B3g; B2g gained two side-arm rows in the amendment) are frozen at this hash. The hash covers the file as it stood before section D (the stage-4 feedback) was filled; D is the only later change. Earlier shakedown hashes of the same file, from before the last two B2i/B3i edits, were `9e71ac05…1156` and `e1174c26…0985` (instrument checks only). |
| **Harness** | `harness/row_cache_size-create-serialized_size--autonomous/`: `SerializingCacheCapTest.java`, `unit-run.sh`, `analyze_unit.py`, `Jmx.java`, `loader.py`, `cluster-run.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md`; not committed (md5s at the start of run 1: `run1/unit/harness.md5`; final: `run1/harness.md5.final`). `cluster-run.py` gained the post-hoc `t1024` label after the first six arms (md5 at the start of the cluster tier `0851c9a2…`, final `ebcdd10e…`); `analyze_*.py` and `selfcheck.py` were written while run 1 ran, `SerializingCacheDiag.java` and `diag-run.sh` after its unit tier. |
| **Tiers and values** | **Unit (B2):** `SerializingCache.create(C, serializer)` with C in {16, 64, 256} MiB x entry size S in {4 KiB, 256 KiB, 4 MiB}, three repetitions each, a fresh JVM per point; control group (singleton weigher, C = 0, one 2^31-byte entry); side arm `clear()` at C = 64 MiB, S = 256 KiB. **Cluster (B3):** `row_cache_size` in {0 (control), 128, 512, 1024} MiB (`SerializingCacheProvider`), data 32,768 partitions x 16 rows x 4 KiB; controls `rows_per_partition = NONE` at 128 MiB and a repeat of 128 MiB; live `setcachecapacity` 256 / 64 / 1024 on the 1024 MiB arm. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate: **positive** (the cap is approximate: malloc and map overhead and in-flight entries are outside the weight). It is not a negative-estimate file, so group A does not require a positive control; B2h/B3h carry their own controls (singleton weigher, C = 0, 0 MiB and `rows_per_partition NONE` arms). Audited against `cassandra/cassandra-5.0.9/` (`git status` of it empty at `627b1ec`; `build.xml` `base.version` 5.0.9). Citations re-read in the pinned source: `SerializingCache.java:40-257` (constructor `:46-60`, `create` `:62-76`, weigher guard `:71`, `serialize` `:91-117` including the 2^31 check `:94-95` and the OOM null `:102-105`, `capacity` `:119-122`, `setCapacity` `:124-127`, `weightedSize` `:139-142`, `clear` `:144-147`, `put` `:166-185`, `putIfAbsent` `:187-207`, `replace` `:209-250`, `remove` `:251-257`), `SerializingCacheProvider.java:31-34`, `RefCountedMemory.java`, `CacheService.java:141-169` and `:327-333`, `Config.java:472-474`, `Memory.java:60-66`, `MemoryUtil.java:78-85`, `ColumnFamilyStore.java:3259-3265`, `SinglePartitionReadCommand.java:491-610` (cache read, sentinel `putIfAbsent`, `replace`), `CacheMetrics.java:60-63`, `NodeProbe.java:1088-1092`, `SetCacheCapacity.java:43`, `conf/cassandra.yaml:547-566`. All hold except the line numbers of `put`, `putIfAbsent`, `replace` and `remove` in A3 (the case cited 107-148 and 162-183, the true ranges are above): amended.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: off-heap (`Native.malloc`) bytes of cached partitions. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: 16/64/256 MiB; B3b: 0 (the default, row cache off), 128, 512, 1024 MiB plus a live change. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | B2d reads `RssAnon`; B3d reads `RssAnon`. B3d's NMT subtraction does not work (NMT "committed" is not resident: it rose by 1 GiB with the cache off while `RssAnon` did not) and the unit tier's shared-JVM RSS delta is polluted by allocator retention; replaced by control-arm differences (B3i.3) and a fresh JVM per point (B2i.8). |
| A. Core question | usage driven to the limit and past it | Partly → Met | B2c offers 4C per point: met. B3c's 8192 partitions (about 520 MiB) would not reach the 512 or 1024 MiB caps; raised to 32,768 partitions (about 2.1 GiB), B3i.1. |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f/B3f have numbers; the "malloc slack" in B2f was undefined (fixed at 64 MiB, B2i.3) and B3f's estimate formula was unusable (B3i.3). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover over-cap, flat, leak, instrument failure and setup errors. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | `weightedSize <= C` with `size()` far below the offered count is direct eviction evidence; the ceiling follows C across three values. |
| B. Logic | alternative explanations and their controls | Met | Singleton weigher, C = 0, 0 MiB and NONE arms, provider check (B3i.3: `RefCountedMemory` count). |
| C. Specific | a human can follow it from the intro and B1 | Met | A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | Loader, JMX reading, ports, arm list and phase lengths were not exact; supplied in B2i/B3i. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Same. `/local/scratch/...` paths do not exist here (environment deviation, §2). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Build tree, bundled Python driver 3.29.0 (unzipped from `lib/`), `nodetool`, `jcmd`, JMX client: step-1 work, done. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met | See group A; 2.2 GB on disk, 45 GB free; node at 2 GiB heap plus at most about 1.1 GiB cache on a 251 GiB host. |
| D. Runnable | load-bearing citations spot-checked | Met | List above; four ranges corrected. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Correct the line ranges of `put`/`putIfAbsent`/`replace`/`remove` in A3 | Applied, A3 inline, 2026-10-25 | The cited ranges (107-148, 162-183) are the middle of `serialize`/`capacity`/`weightedSize`/`clear` instead. |
| 2 | Add the `clear()` finding (EXPLICIT removal is not `wasEvicted()`, so no `unreference()`): a side arm | Applied, A3 note, B2i.6-7, B2g rows | Source reading shows `invalidateAll()` cannot free the blocks; not part of B1, recorded as an accounting bypass. |
| 3 | Use `RssAnon`, fixed slack, exact points | Applied, B2i.2-4 | `VmRSS` counts file-backed pages; undefined slack. |
| 4 | Fresh JVM per unit point | Applied, B2i.8 | Instrument check: freed blocks are reused by the next point inside one JVM. |
| 5 | Data volume 32,768 partitions; random phase 180 s; arms and repeat; ports | Applied, B3i.1-2, 4-6 | 512 and 1024 MiB would not be reached by 8192 partitions; shared node. |
| 6 | Estimate = `RssAnon` difference to the 0 MiB arm; NMT diagnostic only; provider check by `GC.class_histogram` | Applied, B3i.3 | NMT "committed" is not resident memory. |
| 7 | `/local/scratch/...` paths; JMX reading by `nodetool info` rounding | Left for stage 3 | Cosmetic; the amended sections give the real paths. |

**Agreement criteria** — not applicable unless run 2 is chosen (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (unit 00:53–01:03 EDT, cluster tier 01:03–01:33 and a rerun 01:34–01:44; node clock is EDT, Cassandra logs are UTC) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; shared with two other stage-4 sessions (tags `kc`, `es`; their trees, ports and data were not touched) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 (`ant build-test` 1 min 17 s) | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-rc/cassandra` made by `copy-source.sh` from repository commit `627b1ec` (local baseline `7b2f8cf`); nothing changed in it besides `build/`; the unit class is compiled outside it (`~/s4-rc/run1/unit/classes`); the node ran from its `build/` and `conf/` copy. `git status` of the repository's `cassandra/cassandra-5.0.9/` printed nothing after the runs. | |
| Case-file commit / harness commit | case file untracked at `627b1ec` (sha256 `23f4b160fd23a0326d41136393916e0b652fac8d54c9023483e6c8c21e1bb9cd`, §1); harness uncommitted (md5s in `run1/unit/harness.md5` and `run1/harness.md5.final`) | |
| Storage for node data | `/dev/sda3`, ext3, 63 GB (45 GB free); node data under `~/s4-rc/node` (2.16 GB, removed afterwards) | |
| Full logs (path, outside the repo) | `pc07:~/s4-rc/run1/` (`unit/{obs.txt,stdout.log,session.log}`, `diag/`, `cluster/<arm>/{ckpt.jsonl,jmx.csv,rss.csv,nmt-*.txt,heapinfo-*.txt,system.log.segment,class_histogram.top.txt}`, `cluster-load.out`, `cluster-arms.out`, `cluster-arms-first-pass.out`, `cluster-arms2.out`); excerpts in `row_cache_size-create-serialized_size--autonomous/run1/` | |

**Environment deviations (none changes B1):** (1) the filed `/local/scratch/...` paths do not exist; everything is under `~/s4-rc/`. (2) The cluster client is a Python driver script (protocol 4), not `cassandra-stress`. (3) The random phase is 180 s (B3i.2), not 10 min. (4) `ulimit -n` 100000 set in the scripts. (5) The node shares `pc07` with two other sessions: own ports (7390, 7391, 9390, JMX 7399), loopback 127.0.9.1, own trees. (6) The unit class ran concurrently with the cluster load (not with any cluster reading); the 16-thread phases and the load shared the 40 cores. (7) Shakedowns before the freeze: scaled unit sequence, `clear` arm once at full scale, a 2,048-partition cluster sequence of arms `c0` and `c128`; not used (`pc07:~/s4-rc/shake-*`, removed except `shake-cl.out`).

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | A3 | The line ranges cited for `put`, `putIfAbsent`, `replace`, `remove` were wrong (107-148, 162-183). | Corrected inline. | 2026-10-25, before the freeze | none (untracked) |
| 2 | audit | B3c | 8192 partitions (about 520 MiB) cannot reach the 512 or 1024 MiB caps. | 32,768 partitions, B3i.1. | 2026-10-25, before the freeze | none |
| 3 | audit | B3d, B3f | The estimate `RssAnon - (heap + NMT)` double counts the heap and NMT "committed" is not resident (it rose 1 GiB with the cache off). | Difference to the 0 MiB arm, B3i.3. | 2026-10-25, before the freeze | none |
| 4 | audit | B2d, B2e | A shared JVM lets a later point reuse blocks freed by an earlier one. | One JVM per point, B2i.8. | 2026-10-25, before the freeze | none |
| 5 | run 1, cluster | arm `c128b` (B3i.4) | `n128` ran `ALTER TABLE ... rows_per_partition NONE` and Cassandra re-prepares the persisted prepared statements at start-up against the schema it loads. The next lifetime (`c128b`) started with the table at NONE, re-prepared the client's `SELECT` with NONE, and the later `ALTER ... ALL` did not reach that statement: the cache was consulted (674,153 requests) but never populated (0 entries). The same ordering did not affect `n128` itself (the table option NONE is what disables the cache there). | The attempt is kept as invalid (`run1/cluster/c128b-invalid-stale-prepared/`); `c128b` was rerun alone, with the table already at ALL, in a second invocation (`cluster-arms2.out`, same script). The case file is unchanged: B3i.4 lists `c128b` as a repeat and the rerun does the same thing. | 2026-10-25 | none |

No other step failed to run as written.

## 4. Run 1

**Scope:** unit tier: 27 points (C in {16, 64, 256} MiB x S in {4 KiB, 256 KiB, 4 MiB}) x 3 reps, controls x 3, side arm `clear` x 3, each in a fresh JVM; a post-hoc diagnostic (`diag/`). Cluster tier: arms `c0`, `c128`, `c512`, `c1024` (with live changes), `n128`, `c128b` (second attempt), and a post-hoc arm `t1024` (malloc_trim). **Command log:** `row_cache_size-create-serialized_size--autonomous/run1/` (`unit/session.log`, `cluster/session.log`).

### 4.1 Readings

**Unit tier** (`run1/unit/obs.txt`, analysed by `run1/analyze_unit.out`; 205 of 234 criteria pass, the 29 that fail are listed below; values are min–max over three reps)

| C (MiB) | S | `weightedSize` after fill (MiB) / `size()` | fill-phase `RssAnon` delta (MiB), delta - C | concurrent: max sampled `weightedSize` <= C | concurrent peak `RssAnon` delta (MiB) (x C), B2f limit C+16(S+4)+64 | Evidence |
|---|---|---|---|---|---|---|
| 16 | 4 KiB | 16.00 / 4092 | 59.1–65.5 (43–50) | yes | 475–496 (29.7–31.0 x C), limit 80 | `unit/obs.txt` |
| 16 | 256 KiB | 15.75 / 63 | 38.6–43.7 (23–28) | yes | 261–298 (16–19 x C), limit 84 | same |
| 16 | 4 MiB | 12.00 / 3 | 38.3–42.0 (22–26) | yes | 367–403 (23–25 x C), limit 144 | same |
| 64 | 4 KiB | 64.00 / 16368 | 101.9–107.1 (38–43) | yes | 704–787 (11–12 x C), limit 128 | same |
| 64 | 256 KiB | 63.75 / 255 | 91.0–95.7 (27–32) | yes | 322–655 (5.0–10.2 x C), limit 132 | same |
| 64 | 4 MiB | 60.00 / 15 | 87.6–89.5 (24–26) | yes | 553–752 (8.6–11.8 x C), limit 192 | same |
| 256 | 4 KiB | 256.00 / 65472 | 316.6–325.3 (61–69) | yes | 1260–1412 (4.9–5.5 x C), limit 320 | same |
| 256 | 256 KiB | 255.75 / 1023 | 280.9–283.3 (25–27) | yes | 728–1287 (2.8–5.0 x C), limit 324 | same |
| 256 | 4 MiB | 252.00 / 63 | 278.6–284.0 (23–28) | yes | 883–969 (3.5–3.8 x C), limit 384 | same |

Other unit readings: after the fill `weightedSize` is within one entry of C at all 27 points (`>= C - S - 4`) and `size()` equals `floor(C/(S+4))`; after 20 s of 16 threads the final `weightedSize` is still `<= C` and the maximum sampled over 10 ms ticks is `<= C` at all 27 points; `setCapacity(C/2)` leaves `weightedSize <= C/2` immediately at all 27 points; `get` hits equal `size()`. Controls (3 reps each): singleton weigher holds exactly 4 entries for S = 4 KiB and 256 KiB; C = 0 keeps nothing; an entry whose `serializedSize` is 2^31 throws `IllegalArgumentException: Unable to allocate 2.000GiB` and leaves `size() == 0`. Median fill-phase delta rises with C at each S (S = 4 KiB: 63.5, 105.5, 318.9 MiB; 256 KiB: 41.2, 91.9, 281.1; 4 MiB: 39.7, 89.1, 282.7). B2f criteria that failed: the fill-phase delta of two points (C = 16 / S = 4 KiB rep 1: 65.5 against an upper bound of 64.0; C = 256 / S = 4 KiB rep 2: 325.3 against 320.0), and the concurrent-peak bound at all 27 points.

Side arm `clear()` (C = 64 MiB, S = 256 KiB, `unit/obs.txt` `clear` lines): after `clear()` `weightedSize() == 0` and `size() == 0` at all 3 reps, `RssAnon` did not fall (fill 1: 86–94 MiB over baseline; after clear: 87–95), and the second fill peaked at 151–159 MiB over baseline = 2.36–2.48 x C (threshold for a leak: 1.7 x C = 108.8 MiB; threshold for no leak: C + 64 MiB = 128 MiB).

Post-hoc diagnostic (`run1/diag/diag-summary.txt`, 20 s, C = 64 MiB; written after seeing the concurrent peaks; not a B2f reading): with 1 thread `RssAnon` ends at 1.6–1.8 x C before and 1.0–1.3 x C after `malloc_trim(0)`; with 16 threads the largest `size() * (S + 4)` seen (entries present, including ones awaiting eviction) was 1.7 x C (S = 4 KiB, default arenas), 1.6 x C (S = 4 KiB, `MALLOC_ARENA_MAX=1`), 1.5 x C (S = 256 KiB, default), 3.3 x C (S = 256 KiB, `MALLOC_ARENA_MAX=1`); `RssAnon` before the trim was 9.6, 2.2, 2.9 and 3.5 x C respectively and after the trim 2.0, 1.4, 1.9 and 1.0 x C.

**Cluster tier** (`run1/cluster/<arm>/ckpt.jsonl`, `jmx.csv`; analysed by `run1/analyze_cluster.out`). Data: 32,768 partitions, 7 sstables, 2.157 GB live (`cluster/load-summary.txt`). `Size`, `Capacity` in MiB; `est` = `RssAnon(arm) - RssAnon(c0)` at the same checkpoint (`rand`).

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 0 MiB | `c0` control | `Size`, `Capacity`, `Entries` at all checkpoints | 0, 0, 0 | `c0/ckpt.jsonl` |
| 0 MiB | `c0` | `RssAnon` idle -> after random phase | 2623.8 -> 2823.9 MiB (+200.1; prediction was under 100) | `c0/ckpt.jsonl` |
| 128 MiB | `c128` | `Size` / `Entries` after pass 1, pass 2, random phase | 128.00 MiB (134,217,720 B) / 2040; 128.00 / 2040; 128.00 (134,216,456 B) / 2040 | `c128/ckpt.jsonl` |
| 128 MiB | `c128` | `est` at `rand` | 128.6 MiB (band 115.2–230.4) | `c128/ckpt.jsonl`, `c0/ckpt.jsonl` |
| 128 MiB | `c128b` (second attempt) | `Size` / `Entries`; `est` at `rand` | 128.00 / 2040; 104.2 MiB (band 115.2–230.4: **below** the band) | `c128b/ckpt.jsonl` |
| 128 MiB, `rows_per_partition NONE` | `n128` | `Size`, `Entries` | 0, 0 at all checkpoints; `est` -32.9 MiB | `n128/ckpt.jsonl` |
| 512 MiB | `c512` | `Size` / `Entries` after pass 1, pass 2, random | 512.00 MiB / 8160 at all three | `c512/ckpt.jsonl` |
| 512 MiB | `c512` | `est` at `rand` | 447.8 MiB (band 460.8–729.6: **below** the band) | same |
| 1024 MiB | `c1024` | `Size` / `Entries` | 1023.99 MiB (1,073,731,055 B) / 16320 at all three | `c1024/ckpt.jsonl` |
| 1024 MiB | `c1024` | `est` at `rand` | 1003.2 MiB (band 921.6–1395.2) | same |
| all cache-on arms | | every polled sample (49 per arm, 5 s) `Size <= Capacity` | yes (max `Size`/`Capacity` = 1.0000; the closest `Size` is at most about 11 kB below `Capacity`) | `<arm>/jmx.csv` |
| all cache-on arms | | `RssAnon` pass 2 -> random phase (Size flat) | +6.5 (128), +13.2 (128b), +14.9 (512), +37.8 (1024) MiB; `c0` itself +55 MiB over the same span | `ckpt.jsonl` |
| all cache-on arms | | `GC.class_histogram`: `RefCountedMemory` instances | 2040 (128), 8160 (512), 16320 (1024); equals `Entries`; the class exists only under `SerializingCacheProvider` | `<arm>/class_histogram.top.txt` |
| 1024 MiB, live | `c1024` | `Size` after `setcachecapacity 0 256 0`, `0 64 0`, `0 1024 0` (30 s each) | 256.00 MiB / 4080; 64.00 / 1020; 64.00 (Capacity 1024) / 1020 | `c1024/ckpt.jsonl` |
| 1024 MiB, live | `c1024` | `RssAnon` at `rand`, `set256`, `set64`, `set1024`, after 60 s of reads | 3827.1, 3827.2, 3827.2, 3827.4, 3831.7 MiB (no fall); after the reads `Size` is back to 1023.99 MiB | same |
| 1024 MiB, post-hoc | `t1024` | `RssAnon` at `rand`, after `malloc_trim(0)` (full cache), after `setcachecapacity 0 64 0` (`Size` 64 MiB), after a second trim | 3842.6, 3702.6, 3702.9, 2850.2 MiB | `t1024/ckpt.jsonl` |

### 4.2 Conclusion and logic

**Unit tier.**

1. **Validity** — valid. The limit was reached and passed at every point (4C offered; `weightedSize` within one entry of C) [observed: `unit/obs.txt` `phase=fill`]. The heap was fixed and pre-touched (`maxMemory=536870912`, `-XX:+AlwaysPreTouch`) and each point had its own JVM [observed: `unit/obs.txt` `start` lines, `unit/session.log`]. The singleton-weigher, C = 0 and 2^31 controls behaved as predicted in all 3 reps [observed: `unit/obs.txt` `control=` lines], so the harness is sound.
2. **Readings** — (a) the concurrent-phase `RssAnon` peak is far above the B2f bound at every point (2.8 to 31 x C); the post-hoc diagnostic shows most of it is freed-but-retained glibc arena memory (it falls to 1.0–2.0 x C after `malloc_trim(0)`), plus a transient live excess of present entries of up to 1.5–3.3 x C that appears while 16 writers outrun Caffeine's eviction. (b) Two fill-phase deltas exceed the B2f range by 1.5 and 5.3 MiB. (c) At C = 64 MiB the fill-phase delta at S = 4 KiB (102–107 MiB) is above the 1.5 C line of the third B2g row (96 MiB); the excess over C is the same 23–69 MiB at every C (C = 16: 43–50; 64: 38–43; 256: 61–69 for S = 4 KiB; 22–32 for the larger S), so it is a constant process overhead, not growth with C or N.
3. **Matched row** — B2g row 1, "`weightedSize <= C` after quiescence and RSS delta tracks C across the three capacities → Claim holds: the weigher cap binds the native bytes": `weightedSize <= C` at all 27 points (fill, concurrent maximum, final, after `setCapacity`) [observed: `unit/obs.txt`]; the fill-phase delta rises with C (medians above) and equals C plus a constant 22–69 MiB [observed]. Row "Concurrent peak much above C + 16*S → record it as a finding" also applies: finding (a) above. The side arm matches the "`clear()` leaves `weightedSize()` 0 but ... at least 1.7 C" row: second-fill peak 2.36–2.48 x C [observed: `unit/obs.txt`].
4. **Excluded rows** — "`weightedSize > C + S` at rest" (Refuted): the largest value over all points is C itself [observed]. "`weightedSize <= C` but RSS delta keeps growing with N (more than 1.5 C at C = 64 MiB)": the 1.5 C line is crossed at C = 64 / S = 4 KiB only (1.59–1.67 C), by the constant overhead of 2(c); the N-dependence is absent in the fill phase and the diagnostic with 1 thread (20 s of continuous churn) ends at 1.6–1.8 x C before and 1.0–1.3 x C after the trim [observed: `diag-summary.txt`]. The leak the row names (evicted blocks not freed) is excluded for the cluster tier by `t1024` (a trim returns 853 MiB after an eviction by shrinking), and for evictions at the unit tier by the 1 to 1.3 x C figure after a trim [inferred from the trim]. "RSS delta flat across C": no, it rises 63.5 -> 105.5 -> 318.9 MiB. "Singleton control holds more or fewer than 4": no.
5. **Observed vs. inferred** — Inferred: (i) that the 27 concurrent-phase excesses are glibc retention plus a transient in-flight excess, from the post-hoc diagnostic on C = 64 MiB only, not from the 27 points themselves; (ii) that the constant 22–69 MiB over C is JVM/JNA/arena overhead, from its independence of C (no direct attribution); (iii) that the `clear()` growth is a leak and not allocator retention, from the second fill failing to reuse the cleared memory (a shared-JVM shakedown showed freed memory being reused) and from the source (`wasEvicted()` false for EXPLICIT).
6. **Deviations and gaps** — the delta includes a constant overhead, so "tracks C" is shown by the rise with C and the constant excess, not by a ratio near 1 at C = 16 (2.4–4.1 x C). No byte-exact native allocation count was available (the malloc accounting is by difference). The concurrent phase measures a synthetic maximum-rate storm; no cluster workload reached it.
7. **Core question** — Usage follows the constraint: with the default weigher the bytes counted never exceed `C`, eviction fires (4C offered, `size()` stays at `C/(S+4)`) and the process's anonymous memory rises with C as C plus a constant (steps 1–3, parts 1 and 3). The cap is soft: under 16 concurrent writers the present entries transiently reached 1.5–3.3 x C and the process peak was far higher, mostly allocator retention (part 2), and `clear()` frees nothing (part 3, side arm). The constraint caps usage at rest and in the single-writer and read paths.

**Cluster tier.**

1. **Validity** — valid for `c0`, `c128`, `c512`, `c1024`, `n128`, `t1024` and the second `c128b`. The limit was reached and passed: 2.157 GB offered against 128, 512 and 1024 MiB, `Size` at 99.99–100% of `Capacity` at every checkpoint [observed: `ckpt.jsonl`]. Fixed settings confirmed: yaml `row_cache_size` appears once with the arm's value and `SerializingCacheProvider` [observed: `cassandra.yaml.<arm>`], the startup log says "Initializing row cache with capacity of N MiBs" [observed: `<arm>/init-row-cache.log`], `RefCountedMemory` instances equal `Entries` [observed: `class_histogram.top.txt`], `key_cache_size`/`counter_cache_size` 0, `file_cache_size` 64MiB, heap 2 GiB pre-touched [observed: yaml files, node `system.log` argument line]. The first `c128b` is invalid (runbook defect 5) and not used.
2. **Readings** — (a) `c0` `RssAnon` grew 200 MiB over the read phases (prediction: under 100); the cache arms' growth minus their `Size` is 198 MiB (128), 133 (512), 157 (1024), so the same read-path growth appears with the cache off. (b) `est` is 128.6 and 104.2 MiB at 128 MiB, 447.8 at 512 and 1003.2 at 1024: two of four are below the band's lower bound (0.9 `Size`) by 11 and 13 MiB, none above the upper bound. (c) After shrinking, `RssAnon` did not fall until `malloc_trim(0)` ran (`t1024`).
3. **Matched row** — B3g row 1, "`Size <= Capacity` at rest and the native-memory estimate scales with the capacity across 128/512/1024 → Claim holds for the real resource": `Size <= Capacity` in all 49 polled samples of each cache-on arm and at all checkpoints, `Entries` 2040 / 8160 / 16320 (below the 2048 / 8192 / 16384 bounds) [observed: `jmx.csv`, `ckpt.jsonl`]; `est` rises 128.6 (104.2) -> 447.8 -> 1003.2 MiB against `Size` 128 -> 512 -> 1024 [observed]; it never exceeds 1.3 `Size` + 64 MiB and stays below 230 MiB at 128 MiB [observed]. The live-change rows: `Size` followed the JMX capacity at once (256 -> 64 MiB), the native memory did not fall until the allocator was trimmed (3702.9 -> 2850.2 MiB, 853 MiB) [observed: `t1024/ckpt.jsonl`].
4. **Excluded rows** — "native estimate above 1.3 Capacity + 64 MiB or growing with Size flat": no, growth pass 2 -> random phase is +6.5 to +37.8 MiB with `Size` flat, against +55 MiB for `c0`. "`Size > Capacity`": no sample. "Native estimate does not rise between 128 and 1024": it rises 128.6 -> 1003.2. "0 MiB or NONE run has `Entries > 0`": no (`c0`, `n128` all 0). "`Size` does not move on the live `setcachecapacity`": it moves at once; the provider is `SerializingCache` (class histogram). The retained memory after shrinking is released by a trim, so the evicted blocks are freed.
5. **Observed vs. inferred** — Inferred: (i) that the read-path growth of the cache-on arms (133–198 MiB) is the same background as `c0`'s 200 MiB (it is not measured separately); (ii) that the non-fall of `RssAnon` after `setcachecapacity` is allocator retention (supported by the `t1024` trim, one run); (iii) that the cap holds under the workload only: one reader process set, no write-heavy concurrency.
6. **Deviations and gaps** — the random phase is 180 s and each capacity value ran once (128 MiB twice); the NMT figures are diagnostic only (their committed total rose 1 GiB with the cache off); `est` has about +-25 MiB of arm-to-arm noise (the two 128 MiB runs differ by 24 MiB); the `c128b` first attempt and its cause are in §3; no `pmap` reading was taken.
7. **Core question** — Usage follows the constraint: the weighed size sits at the capacity for all three values with 4x to 16x more data offered, the entry count scales with it (2040 / 8160 / 16320) and the process's anonymous memory rises by about the capacity (129 / 448 / 1003 MiB over the cache-off node) and does not grow while reads continue (steps 1–3). The constraint caps the row cache's usage; the cap is approximate (the memory above the cache-off node was 0.81 to 1.00 x `Size` here, and the allocator holds evicted memory until it is trimmed).

**Conclusion (one line):** unit: B2g row 1 (weigher cap binds the native bytes), with the concurrent-overshoot finding and the `clear()` leak recorded — confirmed; cluster: B3g row 1 (`Size <= Capacity`, estimate scales with capacity) — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/row_cache_size-create-serialized_size--autonomous/selfcheck.py` re-parses the raw files (`unit/obs.txt`, `unit/stdout.log`, each arm's `jmx.csv`, `rss.csv`, `nmt-*.txt`, `ckpt.jsonl`, `class_histogram.top.txt`, `system.log.segment`, `cassandra.yaml.<arm>`) and recomputes the facts; output `run1/selfcheck.out`, `BAD CHECKS: []`. Its first version had two false alarms that were corrected in the check, not in the data: it treated the control's designed `IllegalArgumentException` text as an error, and it matched each checkpoint to the nearest rather than to the last earlier `rss.csv` sample (the idle checkpoint precedes the first client by 1–2 s).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: yaml, startup log and `RefCountedMemory` count agree for every cache arm; NMT totals re-parsed equal the checkpoints; no `ERROR` line in any arm's log segment; controls in `obs.txt`. |
| 2. Readings | yes | Fill-phase deltas outside the B2f range: exactly the two points listed (65.5 and 325.3 MiB); concurrent peak / C: min 2.85, median 10.23, max 31.01 (re-derived from `obs.txt`); `est` re-derived from the `rss.csv` medians within 2.2 MiB of the checkpoint-based value (`selfcheck.out`: 128.6 / 129.3, 447.8 / 448.2, 1003.2 / 1003.8, 104.2 / 106.4). |
| 3. Matched row | yes | `weightedSize <= C` re-checked at the 27 points in four places; `Size <= Capacity` in every polled sample of every cache-on arm; the unit and cluster rows quoted in §4.2 are the audited ones. |
| 4. Excluded rows | yes | The 1.5 C trigger is addressed rather than ignored: it is crossed at one (C, S) cell, and the constant-offset argument is checked against the three C values in `obs.txt`; the `clear()` figures re-derived (2.42, 2.36, 2.48 x C). |
| 5. Observed vs. inferred | yes, with limits | The inferred items rest on one post-hoc diagnostic at C = 64 MiB (unit) and one `t1024` run (cluster); they are tagged and neither decides the row. |
| 6. Deviations and gaps | yes | The prediction misses (c0 growth, two `est` lower bounds, two fill-phase deltas, the concurrent peak) are listed in §4.1 and §4.2; nothing was edited to fit them. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 asks that `weightedSize` stay at or below the capacity once writers are quiescent and that real native memory grow with the capacity and then stay flat: both hold in both tiers; the soft-cap findings are outside "once writers are quiescent" or are retention, and are recorded. |

### 5.2 Run 2?

**No** (2026-10-25). The effect `caps` rests on direct readings (`Size`, `Entries`, class histogram, `RssAnon` rising with capacity) that agree across 27 unit points and four cluster values with the two 128 MiB runs 24 MiB apart; the inferred items (allocator retention, constant overhead) do not change the row. The `clear()` leak and the concurrent overshoot are side findings with several reps. A run 2 would be worth it if someone wants the 1.5 C trigger or the `est` band lower bound settled on a quieter node.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** with `SerializingCacheProvider` selected, the bytes held by the row cache never settle above `row_cache_size` (plus a small bounded overshoot): `weightedSize()` is at most the capacity once writers are quiescent, and the real native memory of the process grows with the capacity until the cache fills and then stays flat at about the capacity, however much more data is read (B1). "Confirmed" means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (`weightedSize <= C` at rest; fill-phase RSS delta tracks C as C plus a constant). Recorded findings: concurrent-writer overshoot (B2g "concurrent peak much above" row) and the `clear()` leak (B2g side-arm row). | caps (soft: transient excess under concurrent writers; `clear()` leaks the blocks of the cleared entries) | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed** — B3g row 1 (`Size <= Capacity`, estimate scales with the capacity across 128 / 512 / 1024). Misses of B3f: `c0` read-phase growth 200 MiB (under 100 predicted); `est` below the lower band at `c512` (447.8 against 460.8) and the repeat `c128b` (104.2 against 115.2). | caps | run 1 + self-check | 2026-10-25 |

**Positive control** (a negative-estimate file only): not applicable (positive estimate). The file's own controls moved as expected: the cache-off arm (`c0`) and the `rows_per_partition NONE` arm (`n128`) hold 0 entries and add no memory, the singleton weigher holds 4 entries, and the 2^31 entry is rejected.

**Feedback filed:** the case file's section D updated (not committed; no commit was asked for); A3 line ranges corrected inline and B2i / B3i added (dated 2026-10-25, before any reading) — see §1. Findings to carry back to stage 3 (not applied to the estimate): (1) `SerializingCache.clear()` does not free the native blocks of the entries it drops, so `nodetool invalidaterowcache` on a `SerializingCacheProvider` cache leaks up to `row_cache_size` bytes each time; (2) under many concurrent writers the entries present transiently exceeded the weight (1.5–3.3 x C measured), because eviction runs behind the writes; (3) after the cap is lowered or entries are evicted, `RssAnon` stays high until the allocator is trimmed, so process memory cannot be read off the cache gauge; (4) the case's NMT-based native-memory estimate does not work (NMT committed is not resident memory).

**Leftovers on the node (`pc07`):** no process of this session is running (`ps` for `s4-rc` shows none; no `CassandraDaemon` of this tree). Files kept: `~/s4-rc/cassandra` (source copy with `build/`, 0.4 GB), `~/s4-rc/driver`, `~/s4-rc/logs`, `~/s4-rc/run1` (full logs; the unit classes), `~/s4-rc/shake-cl.out`. Removed: `~/s4-rc/node` (2.2 GB of data), the shakedown directories.
