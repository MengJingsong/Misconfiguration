# max_region_size-tryswapregion-minsize--autonomous — stage-4 results  <!-- file: results/max_region_size-tryswapregion-minsize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max_region_size-tryswapregion-minsize--autonomous`](../../stage3-ai-deep-read/cases/max_region_size-tryswapregion-minsize--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit and cluster Confirmed (does not cap); no run 2
>
> **Outcome class:** true negative (stage-3 estimate `negative`, stage-4 effect `does not cap`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 after the audit's amendments, taken before any reading: `6af2c9d16c4bb883ec092e2410cdcdba8bf0dc9bf367c7778524d0cc31046f5e`. File committed at `b68711e5` (HEAD); the amendments of 2026-10-28 are uncommitted. After run 1, section D (stage-4 feedback) was filled; claim, predictions and rows unchanged: final sha256 `51f462dd0e2057ad64acf0b5b7ea493e08bc075216717b549c5a50da9f676dff`. |
| **Harness** | `harness/max_region_size-tryswapregion-minsize--autonomous/` (uncommitted; README there) |
| **Tiers and values** | Unit: C1, C2, C3 (4 sizes), C4 (A = 1, 10, 100), P1, zero-slack control, in arms R1024 (default build) and R256 (rebuilt), 3 repetitions each in a fresh JVM. Cluster: one node, `offheap_objects`: R-big T = 1, 50, 150 (+4 MiB row), R-small T = 150, H (`heap_buffers`) T = 150, idle drift I. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note |
|---|---|---|---|
| A | quantity is memory or disk bytes | Met | off-heap (`malloc`) bytes of memtable regions (A2). |
| A | knob varied (>= 3 values incl. default) or other approach | Partly -> Met | The constant is hard-coded (A1). B2b made the rebuild "optional"; amended (B2b) into a required second arm R256, with the allocation size, pool limit and allocator count varied as well. The cluster tier varies T and `memtable_offheap_space` instead (the constant is fixed in the jar); stated in B3b. |
| A | real resource measured | Partly -> Met | Unit tier measures reserved region capacity (reflection), not page residency, and says so (B2d). Cluster tier adds an exact region-capacity ledger (Byteman on the `Region` constructor, B3d amendment) beside `VmData`/`RssAnon`, which are noisy. |
| A | driven to the limit and past it | Met | C2 sits exactly at `L`; P1 reaches `L` and blocks; R-small (150 tables x 1.3 MiB against 32 MiB) exceeds the pool limit about 6x. |
| A | positive control (negative claim) | Met | P1 (pool limit blocks writers) and R-small (cluster) are a known-binding cap on the same resource and instruments; zero-slack control and the heap_buffers run guard the measurement. |
| B | steps establish; prediction stated numerically; rows for every outcome; disallow evidence | Met | B2f/B2g/B3f/B3g give numbers. Checked the arithmetic by hand: C2 (81 x 100 B fit in 8192; 163 in 16384; 100 calls -> regions 8192 + 16384), C3 (`highestOneBit(102400) << 3` = 524288; `131072 << 3` = 1048576), C4 (6400 of 8192). Row for "workload not driven" exists. |
| B | alternatives and controls | Met | RACE_ALLOCATED stash, idle drift, heap-fix pretouch, heap_buffers control. Amendment: one JVM per case and repetition so the static stash is empty. |
| C | human / AI can follow; values exact | Partly -> Met | B3c named "cqlsh COPY, a python-driver script, or cassandra-stress": pinned to the bundled python driver (amendment). B3e run list written out (amendment). |
| D | harness exists | Met | Written in step 1; `~/s4-mrs` (default build) and a second copy for R256 built on `pc32`. |
| D | workload reaches the limit | Met | Under 1 GiB written; 251 GiB RAM, 53 GB local disk free on `pc32`. |
| D | citations | Met | `NativeAllocator.java:46-48, 141, 144-145, 154, 164-168, 171-176, 180-183, 186-198, 200-206, 212`, `MemtablePool.java:151-160`, `MemtableAllocator.java:169-197`, `NativePool.java:28-32`, `AbstractAllocatorMemtable.java:106-108`, `DatabaseDescriptor.java:583-584` match the pinned source (the `memtable_cleanup_threshold <= 0.99` check is at 769-770, not 770-773, harmless). The constructor `NativeAllocator(NativePool)` is `protected` (visible from the same package, as B2a says). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Make the 256 KiB rebuild a required arm; run each case in a fresh JVM x 3 | Applied (B2b, B2f amendment 2026-10-28) | Only way to vary a hard-coded constant; the B2g first row depends on it |
| R2 | Exact region-capacity ledger (Byteman) in the cluster tier | Applied (B3d amendment) | `VmData` includes JVM noise; ledger makes "reserved capacity" exact |
| R3 | Pin the writer to the bundled python driver; write the run list | Applied (B3c, B3e amendment) | Group C |
| R4 | A5/B2c: `NativeAllocatorTest` passes a blocking cleaner; P1 must use a no-op cleaner and release with `adjust(-n)` rather than `setDiscarded` (a blocked writer woken after the regions are freed would allocate in a discarded allocator) | Left for stage 3 (harness detail, recorded in the harness README) | Understanding |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (chain started 14:16 UTC, finished 14:42 UTC) |
| Node | `pc32` (`node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-mrs` (arm R1024 and the whole cluster tier; `copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `b68711e5`, `ant build-test` 1 min 8 s) and `~/s4-mrs256` (arm R256, same copy with `NativeAllocator.java:46` changed to `256 * 1024`, `run1/arm-R256.patch`, `ant jar` 1 min 10 s) |
| Case-file / harness commit | `b68711e5` with the uncommitted amendments (sha256 in §1) / uncommitted |
| Node data | local disk `~/stage4-tmp/mrs/node` (removed after each start; `/` had 52 GB free) |
| Full logs | `pc32:~/stage4-logs/mrs/` (`run1/unit/`, `run1/cluster/<arm>/`, `run1/chain.log`; `chk/` and `pilot/` hold the instrument checks below) |

**Instrument checks before run 1** (recorded because they produced readings before the run): (1) the unit launcher was first run once in full into `~/stage4-logs/mrs/chk/` (arm R1024), which showed the harness works and its numbers equal the frozen B2f figures; (2) the cluster script was piloted twice with T = 3 tables (`pilot/`): the first pilot showed the Byteman ledger silent after start-up (see defect 1). Neither is part of run 1. The case file was not edited after these.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | pilot (before run 1) | B3a / B3d (instrument) | `bin/cassandra` daemon mode closes `System.out` after start-up (`CassandraDaemon.java:738`), so the Byteman ledger line stopped after the 36 start-up regions | the harness starts the node with `bin/cassandra -f` in the background | harness-only change; B3a says "`bin/cassandra -f`", so this is the file's own wording; case file unchanged | none |
| 2 | run 1 | B3d | the JMX switch-count read (`MemtableSwitchCount`, attribute `Value`) returned 0 for all arms, including R-small where flushes certainly happened | flushes are counted from `Enqueuing flush of ks.` lines in `system.log` (B3d lists "memtable switch count" only as one option); the JMX figure is not used | harness reading; no change to rows | none |
| 3 | run 1 | B3c arithmetic | the file's "about 1.3 MiB charged per table" is off: the measured charge is about 3.1 MiB per table (cell and row overhead), so R-big T = 150 charged 470 MiB against the 507 MiB flush line (0.99 x 512 MiB), a thin margin | none needed (no flush occurred); recommendation for stage 3 | left for stage 3 | none |

## 4. Run 1

**Scope:** unit tier, arms R1024 and R256, 11 cases x 3 repetitions each (66 JVMs, all exit 0); cluster tier, six node starts. **Command log:** `max_region_size-tryswapregion-minsize--autonomous/run1/chain.log`, `run1/unit/<arm>.out`, `run1/cluster/<arm>/cmdlog-head.txt`; checker `harness/.../selfcheck.py`, output `run1/selfcheck.out` (50 PASS, 0 FAIL).

### 4.1 Readings

**Unit tier** (identical in the 3 repetitions of each arm; `run1/unit/R1024.out`, `R256.out`). `owns` = charged bytes (`offHeap().owns()`, equal to `pool.offHeap.used()`), `cap` = sum of region capacities by reflection.

| Case | R1024 (default 1 MiB) | R256 (patched 256 KiB) |
|---|---|---|
| C1 20000 x 64 B | owns 1,280,000; regions 8192 ... 524288, 1048576; capMax 1,048,576; capTotal 2,088,960 | owns 1,280,000; capMax 262,144; capTotal 1,302,528 |
| C2 L = 10000, 100 x 100 B | owns = used = 10,000 = L; caps [8192, 16384], capTotal 24,576; `tryAllocate(1)` false | same |
| C3 102400 B | owns 102,400; one region 524,288 | one region 262,144 |
| C3 131072 B | owns 131,072; one region 1,048,576 | one region 262,144 |
| C3 131073 B | one region 131,073 (oversize) | same |
| C3 4194304 B | one region 4,194,304 (> 1 MiB) | same |
| C4 A = 1 / 10 / 100 x (100 x 64 B) | owns 6,400 x A; capTotal 8,192 x A; slack 1,792 x A | same |
| Z 8192 B once | slack 0 | slack 0 |
| P1 L = 2 MiB, 64 B calls | 32,768 calls reach used = L = 2,097,152 (capTotal 3,137,536 > L); writer WAITING, 32,769th call not returned after 1.5 s; after `adjust(-6400)` writer TERMINATED | same |

**Cluster tier** (`run1/cluster/<arm>/snaps.jsonl`; deltas `end` - `base`, `end` = 30 s after the writes; charged = sum of `MemtableOffHeapSize` over all tables; ledger = sum of `REGION` lines (every region constructed, cumulative, system tables included); flushes = `Enqueuing flush of ks.` lines in `system.log`):

| Arm (alloc, `memtable_offheap_space`, T) | Writes | ks flushes | Charged | Ledger (regions constructed) | Ledger - charged | dRssAnon | dVmData | 
|---|---|---|---|---|---|---|---|
| R-big T = 1 (offheap_objects, 512 MiB) | 1200 rows, 0 errors | 0 | 2.95 MB | 8.73 MB | 5.78 MB | 12.5 MB | 412 MB |
| R-big T = 50 | 60,000 rows | 0 | 156.1 MB | 197.3 MB | 41.2 MB | 172 MB | 639 MB |
| R-big T = 150 | 180,000 rows | 0 | 493.0 MB (470 MiB) | 613.0 MB (585 MiB) | 119.9 MB | 471 MB (449 MiB) | 1035 MB |
| R-small T = 150 (32 MiB, no threshold override) | 180,000 rows (67 s vs 34 s) | 147, all `MEMTABLE_LIMIT` | max sampled 11.18 MB (288 samples at 1 Hz) | 552.9 MB (cumulative; regions freed at each flush) | n/a | 101 MB | 570 MB |
| H heap_buffers T = 150 (512 MiB) | 180,000 rows | 0 | 0 | 0 (no region constructed) | 0 | 124 MB | 579 MB |
| I idle, 30 s | none | n/a | 0 | 0 | 0 | 1.1 MB | 1.0 MB |
| 4 MiB blob row (after R-big T = 1 / 50 / 150) | 1 row | n/a | +4,194,480 / +4,195,729 / +4,195,665 | +4,235,285 each; largest single region 4,194,325 | | | +33.8 / +38.1 / +64.8 MB |

### 4.2 Conclusion and logic

1. **Validity.** The accounting limit was reached where the file needs it: C2 sits exactly at L (owns = 10,000 = L, `tryAllocate(1)` false) and P1 reaches L = 2 MiB and blocks [observed: `unit/R1024.out`, `R256.out`]; R-small enforced a 32 MiB pool with 147 `MEMTABLE_LIMIT` flushes of `ks` tables [observed: `cluster/small150/flush-ks-count.txt`, `yaml-lines.txt`]. "Hold fixed" settings: `memtable_allocation_type=offheap_objects` with `memtable_offheap_space` 512 MiB (R-big) or 32 MiB (R-small) and `memtable_cleanup_threshold` 0.99 (R-big) / unset (R-small) [observed: `cluster/*/yaml-lines.txt`]; heap `-Xms2G -Xmx2G -XX:+AlwaysPreTouch`, G1 [observed: `cluster/*/proc-args.txt`]; R-big had no flush of any `ks` table [observed: `flush-ks-count.txt` 0 in big1/big50/big150]; heap_buffers control built no region (ledger 0) [observed: `heap150/snaps.jsonl`]. Valid.
2. **Readings.** (a) The cluster R-big `charged` per table (3.1 MiB) is 2.4 times the file's 1.3 MiB estimate (defect 3). (b) `dVmData` is large and mostly not region memory: heap150, which constructs no region, shows dVmData 579 MB with 0 B of regions (R-small, which holds little charged memory, shows 570 MB); so `dVmData - dCharged` (390 / 460 / 517 MiB at T = 1 / 50 / 150) rises with T as B3g's first row says, but the heap_buffers control shows the same order of magnitude without a single region, so the VmData leg alone is not diagnostic; the ledger leg is [observed: `snaps.jsonl` of big1/big50/big150/heap150]. (c) The 4 MiB row's dVmData (34 to 65 MB) is not "about 4 MiB" as B3f predicted; the ledger shows one region of 4,194,325 B, which is the oversize path [observed: `cluster/big150/ledger-histogram.txt`]. (d) The JMX switch counter read 0 everywhere (defect 2).
3. **Matched row.**
   Unit B2g row 1, "Charged flat across region-size variants (R256 rebuild) while capacity follows the constant; C2 capacity > L with `tryAllocate` false; C3 oversize region > 1 MiB; P1 blocks at charged = L": owns identical between R1024 and R256 for every case while capMax is 1,048,576 vs 262,144 in C1 and 524,288 / 1,048,576 vs 262,144 in C3 [observed: `selfcheck.out` lines "owns identical between R1024 and R256", "capMax follows the constant"]; C2 capTotal 24,576 > L = 10,000 with `tryAllocate(1)` false [observed]; C3 4 MiB gives a 4,194,304-byte region [observed]; P1 blocks at used = L [observed].
   Cluster B3g row 1, "R-big: Δ(VmData) − Δ(charged) grows with T; no flush; R-small: charged bounded near 32 MiB with flushes": Δ(VmData) − Δ(charged) = 390 / 460 / 517 MiB at T = 1 / 50 / 150; no `ks` flush; R-small charged max 11.18 MB (< 32 MiB) with 147 flushes [observed]. The row's claim "reserved native capacity is not bounded by the region constant or the accounted limit; `memtable_offheap_space` governs charged bytes only" is carried by the ledger: ledger minus charged is 5.8 / 41.2 / 119.9 MB at T = 1 / 50 / 150 (about 0.8 MB per table beyond the first, within the file's 0 to 1 MiB x T), the cumulative region capacity at T = 150 is 585 MiB against a 512 MiB pool limit that charged bytes (470 MiB) stayed under, and RssAnon follows charged bytes (449 MiB vs 470 MiB) [observed: `snaps.jsonl`]. Row 1 is matched; the VmData leg is confounded as in 2(b).
4. **Excluded rows.** B2g "charged change when the constant changes or equal region capacity": owns identical across arms and owns < capTotal in C1, C2, C4 [observed]. "Max capacity always <= 1 MiB incl. 4 MiB": C3 4 MiB region is 4,194,304 [observed]. "C1 never reaches 1 MiB / P1 does not block": C1 reached 1,048,576 and P1 blocked [observed]. B3g "VmData − charged about 0 for all T": 390 to 517 MiB, and ledger − charged 5.8 to 119.9 MB [observed]. "R-small charged bytes grow past the limit without flushes or stalls": 11.18 MB max, 147 flushes [observed]. "R-big flushes occurred / RSS dominated by other growth": no flush [observed]; RssAnon 449 MiB vs charged 470 MiB [observed]. "4 MiB row shows no virtual growth of about 4 MiB": it grew 34 to 65 MB and the ledger holds a 4,194,325-byte region [observed]. No Refuted row applies.
5. **Observed vs. inferred.** Inferred: that the slack in the ledger is the unfilled and abandoned region tails **[inferred: unit C1 and C4 show exactly that mechanism; the cluster ledger is cumulative and includes system-table regions, about 5 MB, estimated from T = 1]**; that the cumulative ledger of R-small (553 MB) is mostly freed memory **[inferred: 147 flushes each discard an allocator; not measured]**. The verdict does not rest on either.
6. **Deviations and gaps.** `VmData` is a noisy proxy (heap150 control), so the cluster verdict leans on the Byteman ledger, an instrument added at the audit. Live (not cumulative) native capacity was not measured in R-small; page residency of unfilled region tails was not measured (no `bpftrace`; RssAnon only). The 1 Hz sample of charged bytes in R-small can miss short peaks; the pool limit itself bounds them. Stalls of writers in R-small were not measured directly (the run took 67 s against 34 s). One run per arm; the unit tier repeated 3 times. The frozen B3f envelopes for `dVmData - dCharged` (0 to 1 MiB x T) and for the 4 MiB row's `dVmData` (about 4 MiB) were not met, and §9a was not edited.
7. **Core question.** Usage did not follow the constant: with the constant divided by four, charged bytes were identical in every case and only region capacity moved, a single allocation over 128 KiB made a 4 MiB region, and 150 tables built about 585 MiB of regions under a 512 MiB pool whose charged bytes stayed at 470 MiB. What caps the memtable's off-heap use is the pool limit (P1 blocks at L; R-small flushed 147 times and held charged bytes near 11 MB), not the region size. So `MAX_REGION_SIZE` does not cap off-heap usage.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 — Confirmed (does not cap; positive control moved).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit/R1024.out`, `unit/R256.out`, `cluster/*/snaps.jsonl`, `samples.csv`, `stdout.txt` and `system.log` (on the node) and re-tests each number of 4.1: 50 PASS, 0 FAIL (`run1/selfcheck.out`). The JMX switch counter is deliberately not used (defect 2).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Flush counts, yaml lines and the heap_buffers ledger re-read from `system.log` and `stdout.txt` by the script. |
| 2. Readings | yes | The VmData confound (2b) was re-derived from `snaps.jsonl` of heap150 and is stated in the conclusion. |
| 3. Matched row | yes | Unit row by 20 PASS lines; cluster row's three parts re-tested; the VmData leg is flagged as non-diagnostic, the ledger and RSS legs carry it. |
| 4. Excluded rows | yes | Same script. |
| 5. Observed vs. inferred | yes | The two inferences do not carry the verdict. |
| 6. Deviations and gaps | yes | Listed above and in §3. |
| 7. Core question | yes | Follows B1: dose-response on the constant (R1024 vs R256), the oversize path, slack linear in A and T, and the pool-limit control. |

### 5.2 Run 2?

No — 2026-10-28. The unit tier is exact and repeated 3 times in fresh JVMs; the cluster verdict rests on exact ledger numbers and a flush count, and the only inferred statements do not carry it.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative.

**Claim tested:** native memory held by `NativeAllocator` is not bounded by `MAX_REGION_SIZE`: (i) the sum of region capacities exceeds the bytes charged to the off-heap limit, by slack that grows with the number of live allocators; (ii) a single allocation above 128 KiB gets a region larger than 1 MiB; and `memtable_offheap_space` (charged bytes) is what binds.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (row 1: charged identical across the 1 MiB and 256 KiB builds; capacity follows the constant; oversize region 4 MiB; P1 blocks at the limit) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (row 1: no flush in R-big, ledger slack grows with T, R-small bounded with 147 flushes; VmData leg confounded, ledger carries it) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** P1 (unit): `memtable_offheap_space`-style pool limit L = 2 MiB makes the writer block at charged = L (WAITING, call not returned) and releasing 6400 B wakes it; R-small (cluster): a 32 MiB pool held charged bytes at most 11.18 MB with 147 `MEMTABLE_LIMIT` flushes, RssAnon +101 MB against +471 MB in R-big. A zero-slack control (8192 B once, slack 0) and the heap_buffers run (ledger 0) show the instruments do not invent slack or regions.

**Feedback filed:** section D of the case file (uncommitted); the audit's amendments (B2b, B2f, B2g wording, B3c, B3d, B3e; 2026-10-28, uncommitted) are in the case file, new sha256 in the final report and `_INDEX.md` is for the orchestrator.
