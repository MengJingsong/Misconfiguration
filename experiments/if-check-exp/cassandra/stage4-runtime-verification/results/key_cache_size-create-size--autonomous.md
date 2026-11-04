# key_cache_size-create-size--autonomous — stage-4 results  <!-- file: results/key_cache_size-create-size--autonomous.md -->

> **Case:** [`key_cache_size-create-size--autonomous`](../../stage3-ai-deep-read/cases/key_cache_size-create-size--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true positive** (estimate `positive`, effect `caps`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `627b1ec` (the case file is **untracked** at this date). **sha256 of the whole file after the audit's amendments (section "B-audit", B2i and B3i, dated 2026-10-25): `12353fd1a0573b6c8fbfa5cea274d40f6a1b2541952648783b305e1ac84bbf42`** (file as filed, before the amendments: `a366f301d70ed9c3dc092fed41c3dcbe16a8422841551117722426c5d391ef4a`). Recorded 2026-10-25 before any reading; B2f, B2g, B3f and B3g are frozen at this hash. Only section D (feedback) is changed after it. |
| **Harness** | `harness/key_cache_size-create-size--autonomous/`: `CaffeineCacheWeightTest.java`, `unit-run.sh`, `kc.yaml`, `cluster-run.py`, `analyze_unit.py`, `analyze_cluster.py`, `selfcheck.py`; written after the freeze; uncommitted (final md5s: `key_cache_size-create-size--autonomous/run1/harness.md5.final`; md5s at the start of the unit run and of the cluster run: `run1/harness.md5.start`, `run1/harness.md5.cluster-start`) |
| **Tiers and values** | Unit: capacity 1, 8, 64 MiB (1 and 8 threads), shrink 64 -> 8 MiB, guard weights around `Integer.MAX_VALUE`, controls. Cluster: `key_cache_size` 0, 4, 16, 64, 512 MiB, a repeat of 16, and a runtime `setcachecapacity 16 0 0` from 64. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate **positive** (the `maximumWeight` bound on the key cache; line 65 itself is a per-entry guard and is tested as a separate, unit-tier claim 2). Not a negative-estimate file, so no positive control is required; B2h/B3h carry their own controls (weight 0, constant weigher, cap 0, non-binding 512 MiB). Citations re-read in `cassandra/cassandra-5.0.9/` (`git status` of it clean): `CaffeineCache.java:53-57, 61-70 (the check is line 65), 72-95, 107-120`; `CacheService.java:123,128,176,179,336-350`; `DatabaseDescriptor.java:814-817, 819-820, 834-839`; `Config.java:467-468, 479-480`; `KeyCacheKey.java:59-62`; `RowIndexEntry.java:200-203`; `CacheMetrics.java:69-71` (Size = `weightedSize`, Entries = `size`); `BigTableReader.java:255-300, 343, 393` (the exact-match lookup caches via `KeyCacheSupport.cacheKey` -> `getKeyCache().put` -> the weigher; the bloom filter is checked first); `SetCacheCapacity.java` (arguments key, row, counter). All hold. Trigger check: a stress read of a partition on a single sstable reaches `getRowIndexEntry` with `Operator.EQ`, misses the cache, scans the index and calls `cacheKey` -> `CaffeineCache.put` -> the weigher on line 64-68.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: on-heap bytes of the key cache (weight of entries; real heap via the class histogram). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B3b: 0, 4, 16, 64, 512 MiB (default is `min(max(1,5 % of totalMemory),100)`, `DatabaseDescriptor.java:814-817`; the 64 and 512 values bracket it); B2b: 1, 8, 64 MiB. |
| A. Core question | real resource measured, not only the counter | Met | B3d histogram of live instances and Caffeine node classes; the gap (histogram cannot attribute `byte[]`) is named and handled in B3i.3. |
| A. Core question | usage driven to the limit and past it | Partly → Met | B3c arithmetic assumed 150-250 B per entry; real weight is calibrated in the unit tier (B2i.3, B3i.5) and a cap that is not below 1,000,000 x weight is read as non-binding. |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f (`weightedSize <= C`, size = C/1 KiB) and B3f (`Size <= Capacity`, ratio 1 : 4 : 16, factor 1.0 to 2.5 within ±25 %). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g (not capped, factor grows, cap 0 shows entries, 512 plateaus early, runtime change). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | the disallow branch is the eviction (Size at the cap with Entries x weight ~ Size, while 6,000,000 reads touch far more keys than fit) and the guard throw (unit). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | the load/read tool, the table, how entries are stubbed and how the histogram is attributed were not exact; supplied in B2i/B3i. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | `/tmp` paths replaced by the node's own directories; two read passes; saved caches emptied (B3i.1, B3i.2, B3i.4). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | build-test tree, stress, nodetool, `jcmd`; unit test, run scripts and analyzers are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit | Met | 1,000,000 keys x ~100 B (to be calibrated) = ~95 MiB total key-cache weight; caps 4, 16, 64 are below it; 512 is not; data ~1 GB; 6M reads at tens of thousands per second is minutes. |
| D. Runnable | load-bearing citations spot-checked | Met | list above. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Stub entries, `get` instead of `containsKey`, guard values and post-reject put | Applied, B2i.1-2, 2026-10-25 (case file untracked; sha256 above) | The text was ambiguous about the key weight and used a method that does not exist. |
| 2 | Real-class calibration | Applied, B2i.3 | Per-entry weight decides whether 64 MiB binds. |
| 3 | Concrete stress profile, single compacted sstable, saved caches emptied, two read passes | Applied, B3i.1-2 | B3c named a table that stress cannot create without a profile; saved caches would preload; coverage. |
| 4 | Histogram attribution of `byte[]` | Applied, B3i.3 | A class histogram sums all `byte[]`. |
| 5 | Ports/addresses/directories of this node | Applied, B3i.4 | Three agents share the node. |
| 6 | B3c's per-entry estimate (150-250 B) may be high | Applied, B3i.5 | The binding check is made from the measured weight. |
| 7 | `/tmp/c509`, `/tmp/node1` paths and the sources list (`/users/jason92/writeup-A/...`) | Left for stage 3 | Cosmetic. |

**Agreement criteria** — not applicable (no run 2 unless §5.2 chooses it).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (unit 00:46 EDT; cluster 00:49 to 01:09 EDT) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB (shared with two other stage-4 sessions, tags rc and es) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1; the node JVM ran G1 (`-XX:+UseG1GC`), `-XX:InitialHeapSize=MaxHeapSize=2147483648` (`jcmd VM.flags`, in `cluster/*/summary.json`) | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-kc/cassandra` made by `copy-source.sh` from repository commit `627b1ec` (local baseline `85e0c6a`, `git describe` = `cassandra-5.0.9`); `ant build-test` 1 min 18 s. The unit test was added under `test/unit/org/apache/cassandra/cache/`; the node ran from this tree's `build/`; the tree's `cassandra-env.sh` was not edited (the node's own `conf/` copy sets `JMX_PORT=7491`). Nothing was built in the repository's `cassandra/cassandra-5.0.9/` (`git status` of it empty). | |
| Case-file commit / harness commit | case file untracked at `627b1ec` (sha256 `12353fd1…bf42`, §1); harness uncommitted | |
| Storage for node data | `/dev/sda3`, 63 GB local; node data under `~/s4-kc/node` (removed afterwards); about 90 MB of sstable, 1 file | |
| Full logs (path, outside the repo) | `pc07:~/s4-kc/run1/{unit,cluster}/` (full `ant.log`, per-arm `system.log.full`, all histograms `hist-*.txt`, stress outputs); `~/s4-kc/logs/build-test.log`; excerpts in `key_cache_size-create-size--autonomous/run1/` | |

**Own-tag isolation (tag `kc`):** loopback address `127.31.7.1` (listen and rpc), JMX port 7491, native 9042 and storage 7000 only on that address, no Byteman. Other sessions' directories and processes were not touched; every kill was by PID.

**Environment deviations (none changes B1):** (1) the filed `/tmp/c509` and `/tmp/node1` paths are replaced by `~/s4-kc/...` (local disk). (2) `key_cache_size` is written in the yaml as `<n>MiB`; `commitlog_total_space: 1024MiB`. (3) The key cache is read from `system_views.caches` every 10 s (the same `CacheMetrics` gauges as the JMX beans, `CachesTable.java`; one JMX read per arm cross-checks it: `jmx.txt`). (4) A shakedown of both tiers ran before run 1 (unit: same code, identical output; cluster: 30,000 keys, arms `load k4 k0`); its output was deleted and is not a reading.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2c, B2f | `containsKey` does not exist on `CaffeineCache`; guard key weight unspecified | B2i.1-2 | 2026-10-25, before the freeze | none (untracked) |
| 2 | audit | B3c | no stress profile for `ks.t`; saved key cache would preload a restart; `byte[]` cannot be attributed from a histogram | B3i.1-3 | 2026-10-25, before the freeze | none |
| 3 | run 1, cluster, load step | harness (B3i.1), not the case file | the first launch of the cluster run stopped in its load step: my `SELECT count(*) FROM ks.t` over 1,000,000 partitions hit the 5 s read timeout (`ReadTimeout`). No cache reading existed. The check was replaced by `nodetool tablestats` "Number of partitions (estimate)" (1,008,170) and the stress load's `Total partitions 1,000,000`, `Total errors 0`; the cluster tier was restarted from its load step (first attempt kept at `pc07:~/s4-kc/old-run1/`). | harness change only; B3f/B3g unchanged | 2026-10-25 | none |

Selfcheck instrument bug (not a run defect): the first `selfcheck.py` run flagged `rt` because it compared the capacity of the `rt` arm at the end (16 MiB, after `setcachecapacity`) with the arm's starting knob (64); the check was corrected to expect 16 for `rt` and re-run (`run1/selfcheck.out`, 0 fails).

## 4. Run 1

**Scope:** unit tier, 6 fill arms (1, 8, 64 MiB x 1 and 8 threads), the 64 -> 8 MiB shrink, six guard puts, two controls, real-class calibration; cluster tier, `key_cache_size` 0, 4, 16, 64, 512, a repeat of 16, and a runtime change 64 -> 16, each with 2 x 3,000,000 uniform reads over 1,000,000 keys. **Command log:** `key_cache_size-create-size--autonomous/run1/unit/session.log`, `run1/cluster/session.log`; analyzer output `run1/analyze_unit.out`, `run1/analyze_cluster.out`; independent self-check `run1/selfcheck.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/unit.txt`, `run1/analyze_unit.out`; JUnit `BUILD SUCCESSFUL`, `run1/unit/ant-tail.log`).

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Fill with 4 x capacity of 1 KiB entries, C = 1, 8, 64 MiB, 1 and 8 threads | settled `weightedSize` = C exactly (1,048,576; 8,388,608; 67,108,864); `size` 1,024 / 8,192 / 65,536 (= C/1 KiB); highest `weightedSize` seen by a sampler thread during the puts = C, never above | `unit.txt` lines `fill ...` |
| Shrink: 64 MiB cache, `setCapacity(8 MiB)` | `weightedSize` 67,108,864 -> 8,388,608 and `size` 65,536 -> 8,192, already at the first read after the call | `unit.txt` `shrink ...` |
| Guard (capacity 64 MiB) | key+value weight 2,147,483,646 / 2,147,483,647 (key 16 or 0): no exception, entry not retained (weight above capacity, evicted at once); 2,147,483,648 (key 16 or 0) and 3 x MAX: `IllegalArgumentException: Serialized size cannot be more than 2GiB/Integer.MAX_VALUE`, entry absent; a normal put afterwards succeeds | `unit.txt` `guard ...` |
| Control: weight 0 stub, 100,000 puts into a 1 MiB cache | `weightedSize` 0, `size` 100,000 (no eviction) | `unit.txt` |
| Control: constant weigher 1, capacity 1,000, 10,000 puts of 1 KiB | `size` 1,000, `weightedSize` 1,000 (bounds the count, not bytes) | `unit.txt` |
| Calibration: real `KeyCacheKey` (24-byte key) + BIG `RowIndexEntry` | 72 + 24 = 96 B per entry; 200,000 puts into a 1 MiB cache: `weightedSize` 1,048,512, `size` 10,922 | `unit.txt` `real ...` |

**Cluster tier** (`run1/cluster/<arm>/samples.csv`, `jmx.txt`, `hist-*.excerpt.txt`, `run1/analyze_cluster.out`). Data: 1,000,000 partitions (stress load, 0 errors; `nodetool tablestats` partitions estimate 1,008,170), one sstable of about 90.4 MB after `nodetool compact`; node heap 2 GiB G1; each arm 2 x 3,000,000 reads, 0 stress errors (`stress-pass*.results`; 56,000 to 83,000 reads/s).

| `key_cache_size` | Observable (B3d) | Reading (end of pass 2 unless stated) | Evidence (file) |
|---|---|---|---|
| 0 | `Size`, `Entries`, `KeyCacheKey` instances | 0, 0, 0 at every sample and every histogram (6,000,000 reads done) | `k0/samples.csv`, `k0/hist-*` |
| 4 | `Capacity`; `Size` pass 1 -> pass 2; `Entries`; max(`Size` - `Capacity`) over 16 samples | 4,194,304; 4,194,240 -> 4,194,240; 43,690; -64 | `k4/samples.csv` |
| 16 | same (14 samples) | 16,777,216; 16,777,152 -> 16,777,152; 174,762; -64 | `k16/samples.csv` |
| 64 | same (16 samples) | 67,108,864; 67,108,800 -> 67,108,800; 699,050; -64 | `k64/samples.csv` |
| 512 | `Size` pass 1 -> pass 2; `Entries` | 91,233,880 -> 95,767,576 (17.8 % of the 536,870,912 cap, still growing); 950,355 -> 997,581 (distinct keys read) | `k512/samples.csv` |
| 16 (repeat) | same as 16 | identical to the first 16 MiB run (16,777,152; 174,762) | `k16b/samples.csv` |
| 64 then `setcachecapacity 16 0 0` | `Capacity`, `Size`, `Entries` before / after | 67,108,800 / 699,050 before; 16,777,216 cap, 16,777,152 / 174,762 within 30 s and at the end | `rt/samples.csv` |

Heap, from the live class histogram (`jcmd GC.class_histogram`, forces a full GC; sum of `KeyCacheKey` + BIG `RowIndexEntry` + Caffeine node classes + `Entries` x 40 B for the key array, B3i.3):

| `key_cache_size` | Key-cache heap bytes (pass 1 / pass 2) | Divided by `Size` | `KeyCacheKey` instances (pass 2) |
|---|---|---|---|
| 4 | 5,945,584 / 5,945,584 | 1.418 | 43,690 |
| 16 | 23,771,376 / 23,771,376 | 1.417 | 174,762 |
| 64 | 95,074,544 / 95,074,544 | 1.417 | 699,050 |
| 512 | 129,252,024 / 135,674,760 | 1.417 | 997,581 |
| 16 (repeat) | 23,771,376 / 23,771,376 | 1.417 | 174,762 |
| rt, after 64 -> 16 | 95,074,544 (before) / 23,771,376 (after, and at end) | 1.417 | 699,050 -> 174,762 |

Supplementary (observed, not part of a conclusions row): the histogram's total live heap is 87.2 MB at cap 0 and 95.2 / 119.1 / 224.3 / 271.7 MB at 4 / 16 / 64 / 512, so the whole-heap increase over cap 0 is 1.9, 1.9, 2.0 and 1.9 times `Size` (the rest of the per-entry cost is the `ConcurrentHashMap$Node` (32 B each), the table array and the other Caffeine structures, none counted by the weigher). After the runtime shrink the counted classes fell to the 16 MiB figures, but the total live heap (137.1 MB) stayed 17.3 MB above a fresh 16 MiB-cap run (119.8 MB): the `int[]`, `long[]` and `ConcurrentHashMap$Node[]` rows were larger by 8.4, 6.2 and 3.1 MB (`rt/hist-end-pass2.txt` against `k16b/hist-end-pass2.txt`, full logs on the node). [inferred: Caffeine's tables sized for the 64 MiB cap are not shrunk by `setMaximum`; the arrays are generic, so their owner is not proven.]

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached: in every capped arm `Size` stopped within one entry (64 B) of the cap after 3,000,000 reads while 1,000,000 distinct keys (about 95.8 MB of weight) were available, so the cap, not the workload, ended the growth [observed: `k4`, `k16`, `k64` `samples.csv`; `k512` shows the weight of all keys]. Hold-fixed settings: the knob applied in each arm (`Initializing key cache with capacity of N MiBs` in each `system.log.full`, and `Capacity` = N x 1,048,576 at every sample) [observed: `init-log.txt`, `samples.csv`]; the same data, one sstable, no compaction and an emptied `saved_caches` in each arm [observed: `load/tablestats.txt`; `cluster-run.py` removes `saved_caches` at every start; `t0` `Entries` is 0 in every arm]; row and counter caches 0 MiB [observed: `cassandra.yaml.k4`]; heap 2 GiB G1 in every arm [observed: `summary.json` `jvm_flags`]; no `ERROR` in any `system.log` [observed: `summary.json` `errors_in_log`]. The `Size` metric is the one the check's weigher feeds (96 B per entry = 72 + 24, equal to the unit-tier calibration) [observed: `unit.txt`, `samples.csv`: 4,194,240 / 43,690 = 96.0].
2. **Readings** — nothing contradicts another. `Entries` x 96 B = `Size` exactly in every capped arm (in the 512 arm the two gauges were read a moment apart and differ by 200 B); the virtual-table values equal the JMX values read at the end (`jmx.txt`); `KeyCacheKey` instances in the histogram equal `Entries`. The `Size` is 64 B under the cap in every capped arm (the next 96-byte entry does not fit). The weight per entry (96 B) is below the case's 150 to 250 B estimate, which does not change any row (the caps still lie below 1,000,000 x 96 B = 91.6 MiB).
3. **Matched row** — unit B2g rows 1 to 3 and 4: "weightedSize <= C after maintenance and size ~= C/w for all three C | Mechanism works as traced (claim 1, unit level)"; "`setCapacity` lowers weightedSize | Runtime change is effective"; "exception only at weight > MAX_VALUE | Line 65 guard behaves as read" [observed: `unit.txt`, all arms]. Cluster B3g row 1: "`Size` plateaus at <= cap and histogram bytes scale ~linearly with cap with a stable factor | Cap governs actual heap (claim confirmed), with factor = uncounted overhead" [observed: Size 4,194,240 / 16,777,152 / 67,108,800 with histogram bytes 5.95 / 23.8 / 95.1 MB, ratio 1 : 4.00 : 15.99, factor 1.417 to 1.418 in all four capped runs]; the row "Runtime `setcachecapacity 16` lowers `Size` and histogram bytes | Dynamic path effective" also applies [observed: `rt`]; "Cap=0" and "512" rows were checked as controls below.
4. **Excluded rows** — "weightedSize > C persistently": no, never above C in 6 unit arms (sampler thread included) or any cluster sample (k4 16, k16 14, k64 16, k16b 13, k512 13). "Histogram bytes grow after `Size` plateaus; claim refuted": no, pass 2 equals pass 1 in the four capped arms (the numbers repeat to the byte because both passes end with a full cache). "Factor differs a lot between 4 and 64": no, 1.418 and 1.417. "Cap=0 still shows entries": no, 0 entries, 0 `KeyCacheKey`. "512 run plateaus before 512 MiB": no, `Size` 95.8 MB and still rising from pass 1 to 2, `Entries` 997,581 of 1,000,000 keys, so it ended because the keys ran out, not at a cap. "exception at or below MAX_VALUE, or none above it": no. "weightedSize much below C with size < C/w": no. No Refuted row applies.
5. **Observed vs. inferred** — inferred: that the histogram's four chosen row groups are the key cache's retained heap (the `ConcurrentHashMap$Node` and table rows are left out of the figure by the B3i.3 definition, so the figure is a lower bound on cache heap; the whole-heap increase over cap 0 is 1.9 to 2.0 times `Size`, which also lies in [1.0, 2.5] and is also stable); and that the Caffeine tables sized for 64 MiB were what stayed after the runtime shrink. Everything else is observed.
6. **Deviations and gaps** — (a) The cache grows as `Entries` x 96 B only because every entry is the same size; wide partitions (large `IndexedEntry`, whose `int[] offsets` the weigher does not count, A3) were not tested, so "the factor does not grow with the data" is shown for 24-byte keys and small partitions only. (b) The guard (line 65) is unreachable by the cluster workload (as B3h says), so claim 2 is shown at the unit tier only. (c) Counter cache was not run (a variation per A1). (d) Each arm ran once, except 16 MiB, which repeated identically. (e) The first launch of the cluster run stopped in the load step (§3 defect 3). (f) `Size` was sampled every 10 s, so a transient overshoot shorter than that is not excluded in the cluster; the unit tier's sampler thread covers it for the class itself.
7. **Core question** — usage followed the constraint: with `key_cache_size` 4, 16, 64 MiB the key cache's `Size` stopped at the cap (to within 64 B, one entry) after 6,000,000 reads over 1,000,000 keys, entries were in the ratio 1 : 4 : 16 and the live heap of the cache's classes followed with a constant factor (1.417; 1.9 to 2.0 counting the whole heap increase); with a cap that exceeds the key set (512) the cache did not stop at the cap but at the key set, and with 0 it held nothing (parts 1 to 4). The unit tier shows the mechanism and the weigher as the operand (weight 0 never evicts; a constant weigher bounds the count) and the line-65 guard throwing only above `Integer.MAX_VALUE`. The constraint caps the cache's on-heap use, with the overshoot of the uncounted per-entry overhead (about 1.4x of the weight for the four counted classes, 1.9 to 2.0x for the whole increase).

**Conclusion (one line):** unit B2g rows 1 to 4 and cluster B3g row 1 (cap governs actual heap, factor 1.417) — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.out` re-derives the facts by a route independent of `analyze_*.py` (unit lines split by token; cluster values from `session.log` dictionaries, `system.log.full` init lines, `stress-*.out` totals, `hist-*.txt` re-parsed with a different parser, `jmx.txt`): 54 checks hold, 0 fail (one initial false alarm in the check itself, §3).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: every arm's `system.log.full` shows the knob; 14 stress passes read 3,000,000 partitions with 0 errors; `Size` within 1 % of the cap in `k4`, `k16`, `k64`, `k16b` |
| 2. Readings | yes | `Entries` x 96 = `Size` (capped arms); histogram `KeyCacheKey` instances equal JMX `Entries` in every arm; JMX Size <= Capacity |
| 3. Matched row | yes | heap bytes 5,945,584 : 23,771,376 : 95,074,544 = 1 : 3.998 : 15.99 recomputed from the histograms by the second parser |
| 4. Excluded rows | yes | `k0` 0/0; `k512` 95.8 MB vs cap 536.9 MB with `Entries` 997,581 >= 0.95 P; unit guard throws iff sum > `Integer.MAX_VALUE` in all six puts |
| 5. Observed vs. inferred | yes | the inferred statements are limited to the retained-structures remark after a shrink and the completeness of the four row groups; neither is needed for the row |
| 6. Deviations and gaps | yes | listed in §4.2 part 6; none changes a count or a size |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | knob varied (0, 4, 16, 64, 512, runtime change), usage measured as the weigher's sum and as live heap, controls moved as predicted |

### 5.2 Run 2?

**No** (2026-10-25). A positive estimate was confirmed, every numeric prediction matched exactly in both tiers, and the self-check re-derived the numbers by a separate parser. The conclusion rests on no inference except the scope remarks in part 5.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (the `maximumWeight` cap of the key cache; line 65 itself is a per-entry guard, not a usable cap). **Outcome class:** **true positive** (positive, caps).

**Claim tested:** B1: (1) with `key_cache_size = S MiB` the key cache's weighted size never settles above S MiB and the real on-heap bytes attributable to cached entries stay within a constant factor of the weighted size, independent of how many distinct partitions are read; (2) the per-entry check at line 65 triggers only when one entry's key+value `unsharedHeapSize` exceeds `Integer.MAX_VALUE`, and then `put` throws `IllegalArgumentException` instead of caching. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g rows 1 to 4 (weightedSize <= C, size = C/w, runtime change effective, guard only above `Integer.MAX_VALUE`) | caps (the weigher's sum is bounded exactly at C; the line-65 guard throws only above 2^31 - 1) | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed** — B3g row 1 (`Size` plateaus at the cap; heap bytes scale 1 : 4 : 16 with a stable factor of 1.417) | caps (on-heap use of the key cache follows `key_cache_size` with a constant overhead factor; claim 2 unreachable at this tier) | run 1 + self-check | 2026-10-25 |

**Positive control** (not required for a positive estimate; the controls moved as predicted): weight-0 entries never evicted and a constant weigher bounded the count (unit); cap 0 held nothing, and the 512 MiB cap (above the key set) did not plateau at the cap (cluster).

**What stays on `pc07`:** `~/s4-kc/` (about 490 MB: the source tree with `build/`, `run1/` full logs and histograms, `logs/`, `old-run1/` (the aborted load attempt), `driver/`, chain scripts, `*.out`). The node data directories and the shakedown outputs were removed. No `CassandraDaemon`, `cassandra-stress`, `ant` or other process of tag `kc` is left (`ps` checked 2026-10-25 after the last arm); ports 7491 and 9042 on 127.31.7.1 are free.

**Feedback filed:** the case file's section D is filled, together with the dated audit amendments "B-audit" (B2i, B3i) in the file (sha256 in §1 is of the file before section D). `_INDEX.md`, the CSV and `predicted-negative.md` are left to the human.
