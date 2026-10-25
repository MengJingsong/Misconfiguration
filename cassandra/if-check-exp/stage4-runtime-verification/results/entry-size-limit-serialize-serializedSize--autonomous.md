# entry-size-limit-serialize-serializedSize--autonomous — stage-4 results  <!-- file: results/entry-size-limit-serialize-serializedSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`entry-size-limit-serialize-serializedSize--autonomous`](../../stage3-ai-deep-read/cases/entry-size-limit-serialize-serializedSize--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `627b1ec`; the case file is **untracked** in the working tree (no commit holds it). **sha256 of the whole file after the audit's amendments (B2i and B3i, dated 2026-10-25): `96dc8b5fd51b75873017d78fc2c30dc9c471232106761ca628fae1ef15d53797`**, written to `~/s4-es/logs/freeze.sha` and to this file at 2026-10-25 00:42:48 EDT, before the harness existed and before any reading. B2f, B2g, B3f, B3g (with B2i, B3i) are frozen at this hash. Section D (the feedback) was filled afterwards; the file's sha256 with D filled is in section 8. |
| **Harness** | `harness/entry-size-limit-serialize-serializedSize--autonomous/`: `SerializingCacheLimitTest.java`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md`; written after the freeze; not committed (md5s at the start of each run and at the end: `entry-size-limit-serialize-serializedSize--autonomous/run1/harness.md5.{unit-start,cluster-start,final}`). `cluster-run.py` was edited once after the main cluster run (two phase names added for the added controls, `startswith('big')`); the run-1 copy is `run1/cluster-run.py.as-run1`. |
| **Tiers and values** | **Unit (B2):** C in {64, 128, 256} MiB with 1024 x 1 MiB entries, C = 3072 MiB with 4096 x 1 MiB (B2i.3), guard sizes 2^31-1, 2^31, 2^31+4096, single 512 MiB entry, 8 x 256 MiB and 8 x 512 MiB in flight at C = 64 MiB, shrink 256 to 128 MiB, no-cache control, repeat, `clear()` probe. **Cluster (B3):** `row_cache_size` in {0 (control), 64, 256, 1024} MiB on 16,384 x 64 KiB partitions, two read passes each; 8 x 64 MiB and 1 x 256 MiB partitions at 64 MiB; runtime shrink 256 to 32 MiB; two added controls (`c0b` repeat of the cache-off phase, `bigctl` large-entry reads with the cache off). The optional 2.1 GiB partition arm is not run (B3i.3). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate: **negative** (the :94 guard bounds one entry, not the cache's total). Audited against `cassandra/cassandra-5.0.9/` (`git status` of it clean at `627b1ec`; `build.xml` `base.version` 5.0.9). Citations re-read in the pinned source: `SerializingCache.java:40-272`, `SerializingCacheProvider.java:29-68`, `RefCountedMemory.java`, `Memory.java:50-100`, `MemoryUtil.java:75-90`, `FBUtilities.java:924-945`, `SinglePartitionReadCommand.java:535-641`, `CacheService.java:120-175, 318-336`, `Config.java:470-478`, `DatabaseDescriptor.java:3910-3925`, `conf/cassandra.yaml:540-582`, `CacheProviderTest.java:135-175`, `build.xml` test targets (`check-test-names`, the junit fork's `maxmemory="1024m"`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: off-heap native memory of the row cache (`malloc` through `Memory`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The :94 constant cannot be varied (no config, A1); the design varies the aggregate knob `row_cache_size` (64/128/256 unit, 64/256/1024 cluster, default 0 as the control) and drives the guard directly with a fake `serializedSize` at, just over and past 2^31-1 (B2b). The reason and the substitute are stated. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | B2d(c)/B3d(a) read resident anonymous memory; the filed "RSS minus heap minus NMT" recipe is replaced by `RssAnon` with a pre-touched heap (B3i.1) and `VmRSS` by `RssAnon` (B2i.2). Gap named: page rounding and malloc headers. |
| A. Core question | usage driven to the limit and past it | Partly → Met | The guard is driven to 2^31-1 and past it (W1); the filed workload never put total native use above 2 GiB, so the falsifier "bounded by the 2 GiB limit" could not fire; W2big (3 GiB cache) and W3b (4 GiB in flight) added (B2i.3). |
| A. Core question | positive control for a negative estimate | Met | B2h/B3h: the same workload and sampler with the capacity varied (the known-binding cap on the same resource) and a no-cache control. |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f/B3f were relations ("up to C + 2 GiB", "~one-for-one"); thresholds supplied in B2i.6 and B3i.4 from the source and arithmetic, before any reading. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | Missing rows added: B2i.7 (above the guard / limit never reached / sampler not specific), B3i.5 (reading outside every row). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For a "does not cap" claim: usage follows `row_cache_size` and not the guard, the disallow branch is read directly (the `IllegalArgumentException` and its message, B2g row 1) and the eviction branch by `weightedSize()`/`Size`. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h plus the no-cache control; the source fact that `clear()` does not free (B2i.4) removes a leak confound by emptying with `remove()`. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3 and B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | `byte[]` values do not fit the test JVM's heap, how to hold eight allocations in flight, how to read a large partition without paging, the loopback/port setup: supplied in B2i.1-3, B3i.1-2. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Sampling interval, baseline definition, table schemas, read statements, round counts supplied (B2i.2, B3i.1-2). Paths `/local/work/...` do not exist here (environment deviation). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ant build-test` tree, bundled Python driver, `nodetool`, `jcmd`; unit test, driver and analysers are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: at most 4 GiB resident on a 251 GiB node. Cluster: 1.8 GiB of data on a 42 GB-free local disk; the 1024 MiB cache is filled by 1 GiB of partitions. The 2.1 GiB partition would need a heap above 2.1 GiB before :94 is reached: arm not run (B3i.3). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (3 line numbers off) | All re-read; `Memory.java:60-61` is :62-63, the `finally` at `SinglePartitionReadCommand.java:629-632` is :632-636, `CacheService.initRowCache` :141-170 and `setRowCacheCapacityInMB` :327-334 (B2i.8). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Value type `Blob` with a chunked serializer instead of `byte[]` | Applied, B2i.1, 2026-10-25 | A 256 to 512 MiB `byte[]` does not fit the 1 GiB test JVM. |
| 2 | `RssAnon`, allocator variables, per-arm baseline | Applied, B2i.2 and B3i.1 | `free()` must return pages for resident memory to track live bytes; heap is pre-touched. |
| 3 | Add W2big (3 GiB cache), W3b (8 x 512 MiB), barrier for in-flight allocations, `nocache`, repeat | Applied, B2i.3 | Total usage above 2^31-1 is needed to test the "bounded by the guard" falsifier; the in-flight peak must not depend on thread timing. |
| 4 | Empty the cache by `remove(key)`, not `clear()` | Applied, B2i.4 and B2i.5 | `clear()` does not free (source :54-58, :144-147); extra prediction recorded. |
| 5 | Numeric thresholds for B2f and B3f | Applied, B2i.6 and B3i.4 | Relations alone cannot be contradicted by a reading. |
| 6 | Tables, read statement, rounds, pre-touched heap, loopback node for B3 | Applied, B3i.1-2 | Unspecified; the node shares its host with other runs. |
| 7 | Optional 2.1 GiB partition arm | Declared not runnable, B3i.3 | `OutOfMemoryError` on the heap precedes :94. |
| 8 | Fix three line numbers; the paths in B2a/B3a/B4 | Noted B2i.8 / left for stage 3 | Cosmetic. |

**Agreement criteria** — not applicable (run 2 not chosen, §5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (unit 00:46 EDT, cluster 00:52 to 01:06 EDT, added controls 01:06 to 01:10 EDT) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB, shared with two other runs (tags `kc`, `rc`) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-es/cassandra` made by `copy-source.sh` from repository commit `627b1ec` (local baseline tag `cassandra-5.0.9`), `ant build-test` (1 min 17 s); the unit probe was added there only. The node ran from `~/s4-es/node-tree`, a `cp -a` of the built copy (head `7b2f8cf`), in which `ant` was never run. Nothing built in the repository's `cassandra/cassandra-5.0.9/`. | |
| Case-file commit / harness commit | case file untracked at `627b1ec` (sha256 `96dc8b5f…3797`, §1); harness uncommitted (md5s in `run1/harness.md5.*`) | |
| Storage for node data | `/dev/sda3`, ext3, 63 GB (42 to 46 GB free); node data under `~/s4-es/node1` (removed afterwards) | |
| Full logs (path, outside the repo) | `pc07:~/s4-es/run1/{unit,cluster,cluster2}/` (full `ant.log`, 10 ms and 100/20 ms samples, per-phase `system.log` start-up lines, `phase-*.json`, `session.log`), `~/s4-es/logs/`; excerpts in `entry-size-limit-serialize-serializedSize--autonomous/run1/` | |

**Environment deviations (none changes B1):** (1) filed paths (`/local/work/...`) replaced by `~/s4-es/...`. (2) The cluster load and reads are a Python driver script, not `cassandra-stress` or `cqlsh COPY`. (3) The node listens on `127.0.0.77` with storage 7077, native 9077, JMX 7277 (shared host); `nodetool` is called with `-p 7277`. (4) `read_request_timeout`, `write_request_timeout` and `native_transport_timeout` were raised to 60 s so that a 256 MiB partition read is not cut off. (5) The live command line carries both Cassandra's default `-XX:MaxDirectMemorySize=15872M` and the harness's `256m`; the JVM takes the last (`run1/cluster/evidence-*/cmdline.txt`). (6) B3c's "10 min" of read passes became two passes per phase, each reading every partition once (13 to 29 s).

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2c/B2d | `byte[]` values of 256 to 512 MiB cannot be held by the 1 GiB test JVM. | `Blob` value with a chunked serializer: B2i.1. | 2026-10-25, before the freeze | none (case file untracked) |
| 2 | audit | B2e steps 2, 3, 6 | `cache.clear()` does not free the native memory (EXPLICIT removal cause, listener frees only evictions), so the "return to baseline" check would fail and arms would contaminate each other. | Empty with `remove(key)`; extra prediction for `clear()`: B2i.4, B2i.5. | 2026-10-25, before the freeze | none |
| 3 | audit | B3d(a) | "RSS minus heap minus NMT" is not a stable measure (heap not resident from the start). | `RssAnon` with `-XX:+AlwaysPreTouch`, control subtraction: B3i.1. | 2026-10-25, before the freeze | none |
| 4 | audit | B3c/B3e (optional 2.1 GiB partition) | Cannot reach :94 with a 2 GiB heap. | Declared not run: B3i.3. | 2026-10-25, before the freeze | none |
| 5 | step 1 (instrument) | harness | The first draft of the unit test class was named `SerializingCacheLimitProbe`; `ant testsome` stops in `check-test-names` ("methods annotated with org.junit.Test should have names that match .*Test$"). | Renamed `SerializingCacheLimitTest`; the stale class file and copy were deleted. | 2026-10-25, before run 1, no reading existed | n/a (harness only) |

## 4. Run 1

**Scope:** unit tier, all arms; cluster tier, phases c0 (and its load), c64, c256, c1024, big; added controls c0b and bigctl. **Command log:** `entry-size-limit-serialize-serializedSize--autonomous/run1/unit/session.log`, `…/cluster/session.log`, `…/cluster2/session.log`.

### 4.1 Readings

Peak and end values are `RssAnon` minus the arm's baseline, in MiB. Unit tier: `unit/results.csv` (14 RESULT lines, also in `unit/ant.log.RESULT-lines`); predictions are checked by `analyze_unit.out` (38 pass, 3 fail).

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| W1 `serializedSize` = 2^31-1 | no exception; `weightedSize()` 0 (evicted at once); peak 0 MiB | `unit/results.csv` arm `guard_2147483647` |
| W1 `serializedSize` = 2^31 | `IllegalArgumentException`, message "Unable to allocate 2.000GiB"; `weightedSize()` 0; peak 0 | arm `guard_2147483648` |
| W1 `serializedSize` = 2^31+4096 | same exception and message; peak 0 | arm `guard_2147487744` |
| W2 C = 64 MiB, 1024 x 1 MiB offered | `weightedSize()` 64.0 MiB, `size()` 64; peak 59, end after `remove` 0; repeat: peak 59 | arms `agg64`, `agg64_repeat` |
| W2 C = 128 MiB | `weightedSize()` 128.0, `size()` 128; peak 121 | arm `agg128` |
| W2 C = 256 MiB | `weightedSize()` 256.0, `size()` 256; peak 249; slope of peak against C (64 to 256) 0.990 | arm `agg256`, `analyze_unit.out` |
| W2big C = 3072 MiB, 4096 x 1 MiB offered | `weightedSize()` 3072.0 MiB, `size()` 3072; peak 3077 (above 2048) | arm `agg3072` |
| W3 one 512 MiB entry, C = 64 MiB | `weightedSize()` 0, `size()` 0; peak 496; end 0 | arm `over1_512MiB` |
| W3a 8 x 256 MiB in flight, C = 64 MiB | `weightedSize()` 0; peak 2041; end 0 | arm `over8x256MiB` |
| W3b 8 x 512 MiB in flight, C = 64 MiB | `weightedSize()` 0; peak 4058 (above 2048); end 0 | arm `over8x512MiB` |
| Shrink 256 to 128 MiB | `weightedSize()` 256.0 then 128.0 MiB; `RssAnon` rise 249 then 128 | arm `shrink256to128` |
| `nocache` control (same loop, discarding stream) | peak 0 | arm `nocache` |
| Heap flat | `Runtime.totalMemory()` 1007 MiB before and after every arm | `unit/results.csv` |
| `clear()` probe, C = 64 MiB | `size()` 0, `weightedSize()` 0 after `clear()`; `RssAnon` rise 57.4 MiB before and after (not freed) | arm `clear_probe64` |
| Test class | `Tests run: 1, Failures: 0, Errors: 0` | `unit/ant.log.tail` |

**Frozen numeric predictions that missed (B2i.6, `analyze_unit.out`):** W2 "peak between 0.95 C and C + 16" at C = 64 (59, bound 60.8), the repeat (59) and C = 128 (121, bound 121.6). The other 38 checks pass.

**Cluster tier** — phase summaries in `cluster/phase-*.json`, `cluster/info-*.csv`, `cluster/samples-*.csv`; checks in `analyze_cluster.out` (31 pass, 1 fail). D = peak `RssAnon` rise over the two read passes (large-entry phases: per round or read).

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 0 MiB | control `c0` | row-cache capacity, `RefCountedMemory` instances | capacity 0; 0 instances; D0 = 128.2 MiB; 16,384 + 16,384 rows returned, 0 errors | `cluster/phase-c0.json`, `histogram-c0.txt` |
| 0 MiB | control repeat `c0b` | D | D0b = 94.4 MiB (baseline 2577 MiB) | `cluster2/phase-c0b.json`, `analyze_cluster2.out` |
| 64 MiB | A `c64` | `Size`, entries, `RefCountedMemory`; D | `Size` 63.9 MiB (never above capacity at any of 8 samples), 1022 entries, 1022 instances, no OHC classes; D = 167.3 | `cluster/info-c64.csv`, `phase-c64.json`, `histogram-c64.txt` |
| 256 MiB | B `c256` | same | `Size` 255.9 MiB, 4091 entries, 4091 instances; D = 368.1 | `info-c256.csv`, `phase-c256.json` |
| 1024 MiB | C `c1024` | same | `Size` 1024.0 MiB, 16,367 entries (of 16,384; the data serializes to slightly over 1 GiB), 16,367 instances; D = 1118.7; hits 16,145 of 32,768 requests | `info-c1024.csv`, `phase-c1024.json` |
| 64 to 1024 | slopes | D differences | D(256) - D(64) = 200.8 (expect 192); D(1024) - D(256) = 750.6 (expect 768) | `analyze_cluster.out` |
| 256 to 32 MiB | B, after pass 2 | `Size`, `RssAnon` | `nodetool setcachecapacity 0 32 0`: `Size` 32.0 MiB (511 entries) at every poll from the first (2 s); rise minus D0 = 6.0 MiB | `phase-c256.json` (`shrink_polls`), `analyze_cluster.out` |
| 64 MiB | `big`, 8 partitions of ~64 MiB, 20 rounds, 8 concurrent | `Size`, entries; per-round peak rise | end `Size` 0, 0 entries, `Size` 0 at every sample; 160 of 160 reads returned; round peaks 263 to 422 MiB | `phase-big.json`, `info-big.csv`, `analyze_cluster.out` |
| 64 MiB | `big`, one ~256 MiB partition, 5 reads | per-read peak rise; end | peaks 274, 266, 269, 276, 274 MiB; `Size` 0; end rise 26.3 MiB | same |
| 0 MiB | control `bigctl`, same reads, cache off | per-round and per-read peak rise | big8 rounds 36 to 42 MiB (160 of 160 reads), big256 reads 41 MiB; 0 instances | `cluster2/phase-bigctl.json`, `analyze_cluster2.out` |

Provider and settings evidence per phase: `cluster/evidence-<phase>/{cmdline.txt,environ.txt,yaml-keys.txt,system.log.startup}` (start-up line "Initializing row cache with capacity of N MiBs", `-Xms2G -Xmx2G -XX:+AlwaysPreTouch`, `MALLOC_*`, `row_cache_class_name: …SerializingCacheProvider`). `RefCountedMemory` equals `entries` exactly in every phase, and no `org.caffinitas` class appears.

**Frozen numeric prediction that missed (B3i.4):** "D(C) minus D0 between 0.8 C and 1.25 C + 64 MiB" at C = 64: 167.3 - 128.2 = 39.1 (bound 51.2). It holds at 256 (239.9) and 1024 (990.5). All other cluster checks pass. With the repeated control D0b = 94.4 the same difference would be 72.9 (inside the bound); that is an observation about control noise (34 MiB between two cache-off phases), not a repair of the prediction.

**Added controls (c0b, bigctl):** their purposes and expected outcomes (a repeat of D0 within 40 MiB of the first; the cache-off large reads at or below 128 MiB) were fixed when they were launched, after the main cluster run had shown D(C) at 64 MiB and the large-entry peaks, and before their readings; they were written into this file only afterwards. They are controls added on seeing the main run, not part of the frozen design.

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached: the guard was driven to and past 2^31-1 [observed: `unit/results.csv` guard arms]; the cache was filled to its capacity at every tested value (unit `weightedSize()` = C; cluster `Size` ≥ 0.999 C at 64/256/1024 MiB) [observed: `unit/results.csv`, `cluster/info-*.csv`]; eviction engaged (offered 1 GiB against 64 to 256 MiB; the 1024 MiB phase holds 16,367 of 16,384 entries). Hold-fixed settings confirmed: heap flat in the unit tier (1007 MiB before/after every arm) and `-Xms2G -Xmx2G -XX:+AlwaysPreTouch` on the live node [observed: `unit/results.csv`, `cluster/evidence-*/cmdline.txt`]; allocator variables in the live environment [observed: `evidence-*/environ.txt`]; capacity and provider per phase [observed: `evidence-*/yaml-keys.txt`, `system.log.startup`, `histogram-*.txt`]; no ERROR line in any phase's `system.log` [observed: `phase-*.json` `errors_in_log`]. The no-cache controls rose 0 MiB (unit) and 94 to 128 MiB (cluster, reads without a cache), so the samplers are not specific to the cache by themselves; that part of the cluster rise is subtracted or compared by differences.
2. **Readings** — (a) the unit W2 peaks sit 5 to 7 MiB under the capacity (59 against 64, 121 against 128, 249 against 256) and the three frozen lower bounds missed; the sign is constant, so it is an offset, not a trend [observed: `unit/results.csv`]; its cause is not identified (inferred: other anonymous memory in the test JVM, such as compiler arenas, shrank while the cache grew; the no-cache arm showed no such shrink in the same period). (b) The cluster c64 difference to the control (39 MiB) is below the frozen bound; the non-cache part of the rise varies by about 35 MiB between phases (128 and 94 MiB in two cache-off phases; 116 to 130 MiB steady in c0 against 123 to 143 MiB steady in c64) [observed: `cluster/samples-c0.csv`, `samples-c64.csv`, `cluster2/phase-c0b.json`]. (c) At C = 256 the second pass hit 5 of 16,384 requests and at 64 MiB 632: a one-pass sequential scan over a cache smaller than the data barely hits (observed in `phase-*.json` `info_end`); it does not affect the size readings. (d) The `clear()` probe did not free (see part 6).
3. **Matched row** — unit: B2g "W1: 2^31 throws, 2^31-1 passes — the guard works as traced at :94 (per-entry only)" [observed: guard arms]; "W2: weightedSize <= C and RSS delta tracks C (slope ~1) while offered is 1 GiB — usage follows `row_cache_size`, not the :94 limit (claim confirmed)" [observed: `weightedSize()` = C for C = 64, 128, 256 with 1024 MiB offered; peaks 59, 121, 249; slope 0.990]; "W3: peak RSS delta >> C while `weightedSize()` <= C — allocation precedes admission: transient overshoot confirmed" [observed: 496 / 2041 / 4058 MiB against C = 64 MiB with `weightedSize()` 0]; B2i.7(a) "peak above 2048 MiB while every entry is within the :94 limit" [observed: agg3072 3077 MiB, over8x512MiB 4058 MiB]. Positive control: the capacity moved usage 59 to 121 to 249 MiB while the no-cache loop rose 0 [observed: `unit/results.csv`]. Cluster: B3g "RSS-derived usage rises with `row_cache_size` (64 -> 256 -> 1024 MiB) and `Size` <= capacity — usage follows `row_cache_size`: the real cap, and the positive control moved" [observed: D 167.3, 368.1, 1118.7 MiB; `Size` 63.9, 255.9, 1024.0 MiB; differences 200.8 and 750.6 against 192 and 768]; "Large-entry run: RSS-derived peak > `row_cache_size` + baseline while `Size` <= capacity — pre-admission allocation overshoot confirmed" [observed: 8 x 64 MiB rounds 263 to 422 MiB and the 256 MiB partition 266 to 276 MiB with `Size` 0, against 36 to 42 MiB with the cache off]. The 2.1 GiB row of B3g was not run (§1, B3i.3).
4. **Excluded rows** — unit "W1: 2^31 does not throw": ruled out, both oversize sizes threw [observed]. "W2: RSS delta flat at ~1 GiB regardless of C": ruled out, 59/121/249 [observed]. "W3: peak RSS delta <= C + small — no overshoot": ruled out, 496 to 4058 MiB against 64 [observed]. "RSS delta in W2 identical for C = 64/128/256 while the control moves — refutes the follow-the-knob half": ruled out, the deltas differ 1:2:4 [observed]. "Sampler shows no RSS rise at all": ruled out, the pages were written and the rise is 59 to 4058 MiB [observed]. B2i.7(b) "limit never reached": ruled out, agg3072 and over8x512MiB exceeded 2048 MiB [observed]. B2i.7(c) "`nocache` peak above 32 MiB": ruled out, 0 [observed]. Cluster "usage flat across `row_cache_size` although `Size` changes": ruled out, D rises 167 to 1119 [observed]. "Usage flat and `Size` flat/zero (cache never filled)": ruled out, `Size` filled to capacity and `RefCountedMemory` instances equal entries in all phases [observed]. "Large-entry peak <= `row_cache_size` + baseline": ruled out [observed]. B3i.5 "a reading outside every row": the c64 difference to the control (39.1 against a bound of 51.2) is a miss of a numeric threshold, not a reading that fits no B3g row; it is recorded in part 2 and §4.1 and is why the cluster verdict carries a flag (part 6). No **Refuted** row applies.
5. **Observed vs. inferred** — the conclusion depends on these inferred statements: (i) that `RssAnon` rise in the unit tier is the cache's native memory (inferred from the no-cache control at 0, flat heap, and `end_clean` back to 0 after `remove`); (ii) that the cluster rise above the cache-off control is the cache's native memory (inferred from `Size`, the `RefCountedMemory` count and the dose-response; the control varies by about 35 MiB, so single differences at 64 MiB are weak and the slopes carry the argument); (iii) that the cluster large-entry peaks are the pre-admission allocation (inferred from `Size` 0 throughout and the cache-off control at 36 to 42 MiB); (iv) that `free` returns pages at once so that resident memory tracks live bytes (inferred from `end_clean` 0 in every unit arm and the shrink arm, `rise minus D0` 6 MiB in the cluster shrink); (v) the unexplained 5 to 7 MiB unit offset.
6. **Deviations and gaps** — the optional 2.1 GiB partition arm was not run (B3i.3); the per-phase cluster samples of `Size` are every 5 s (1 s in the large-entry phases), so "never above capacity" is read at those instants only (the unit `weightedSize()` is read at the end of each arm); the `clear()` leak was seen only in a unit probe, not on a live node; no cluster arm drives the guard (W1 does, in the unit tier); only one repeat of the control and none of the cache phases, and no run 2; the added controls were launched after the main run (§4.1). The cluster reads are one request per partition, so entry sizes are the serialized partition (65,5xx bytes), not varied.
7. **Core question** — Total native memory used by the row cache follows `row_cache_size` (the Caffeine maximum weight) and not the 2^31-1 guard: it rose 1:2:4 with the capacity at the unit tier and 167:368:1119 MiB with 64:256:1024 MiB on a real node, and exceeded 2048 MiB (the guard's value) with every entry within the guard (parts 3 and 5). The guard acts only on one value: an entry over 2^31-1 is refused before any allocation (W1, the disallow branch read directly), an entry just under it is allocated in full and then evicted by the capacity, and allocations in flight are outside both limits, so peak use reaches several times the capacity (496 to 4058 MiB at C = 64 MiB; 263 to 422 MiB on the node) [parts 3, 4]. So the constraint at :94 does not cap the cache's total usage: the claim holds.

**Conclusion (one line):** unit: B2g W1 / W2 / W3 rows — Confirmed, does not cap; cluster: B3g rows "usage rises with `row_cache_size` and `Size` <= capacity" and "large-entry peak > `row_cache_size` + baseline" — Confirmed, does not cap (flag: the c64 cache-minus-control difference missed its frozen lower bound; the unit W2 lower bound missed by 1 to 2 MiB at 64 and 128 MiB; neither is a B2g/B3g row).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/…/selfcheck.py` re-parsed the raw files without using the analysers (`run1/selfcheck.out`: 51 OK, 1 BAD, the BAD being the same c64 difference as above). Raw files re-opened: `unit/ant.log.RESULT-lines` (identical to `results.csv`), each `unit/series-<arm>.csv` (peak recomputed from the 10 ms samples, agrees within 1 MiB for all 14 arms), `cluster/samples-*.csv` and `info-*.csv` (D, `Size` recomputed by a different loop: c0 126.4, c64 166.3, c256 367.0, c1024 1118.2 MiB against 128.2, 167.3, 368.1, 1118.7; the 1 to 2 MiB difference is the baseline window), `cluster/evidence-*/*`, `histogram-*.txt`, `phase-*.json`, `cluster2/*`.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `evidence-*` shows the pre-touched 2 GiB heap, allocator variables, capacity and provider for all five phases; `unit/results.csv` shows the flat heap; no ERROR lines. |
| 2. Readings | yes | The 5 to 7 MiB unit offset and the 39 MiB c64 difference are as described; `unit/series-agg64.csv` shows the plateau at 59 MiB from 0.3 s to the end of the fill (1.2 s), so the offset is steady, not a transient. Its cause stays inferred. |
| 3. Matched row | yes | Each quoted row's readings re-derived from the raw files (`selfcheck.out`): guard messages, `weightedSize()` = C, slope 0.990, overshoot peaks, 3077 and 4058 MiB above 2048, cluster differences. |
| 4. Excluded rows | yes | Each exclusion cites a number that `selfcheck.out` reproduces; no Refuted row applies. |
| 5. Observed vs. inferred | yes | The list is complete; (ii) is the weakest because of the cache-off control spread (128, 94 MiB), which is why the slopes and the exact `Size`/instance counts are used. |
| 6. Deviations and gaps | yes | The harness edit after the main run and the late controls are recorded; nothing else was skipped. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 (i) and (ii) map to the follow-the-capacity readings and the overshoot readings; the "bounded by 2 GiB" falsifier is answered by 3077 and 4058 MiB (B2i.7a). |

### 5.2 Run 2?

**No** — decided 2026-10-25. The claim is the negative estimate's expected outcome, the conclusion rests on counters read directly (`weightedSize()`, `Size`, instance counts, the exception) together with resident-memory differences that agree at both tiers, and no part of §5.1 is unsettled. The weakest point (the 64 MiB difference to a noisy control) is covered by the slopes and by the exact counters.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested:** (B1) The `Integer.MAX_VALUE` check at `SerializingCache.java:94` does not cap the total off-heap memory used by a `SerializingCache`: (i) the total is governed by `row_cache_size` (Caffeine weight), and (ii) it can transiently exceed `row_cache_size` because each entry is allocated before admission. "Confirmed" below means this held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**: B2g W1 (2^31 throws, 2^31-1 passes), W2 (`weightedSize()` <= C, peak tracks C, slope 0.990), W3 (peak 496 to 4058 MiB against C = 64 MiB, `weightedSize()` 0), B2i.7(a) (3077 and 4058 MiB above the 2048 MiB guard). Flag: three frozen lower bounds of W2 missed by 1 to 2 MiB. | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed**: B3g "usage rises with `row_cache_size` and `Size` <= capacity" (D 167 / 368 / 1119 MiB; `Size` 63.9 / 255.9 / 1024.0 MiB) and "large-entry peak > `row_cache_size` + baseline while `Size` <= capacity" (263 to 422 MiB and 266 to 276 MiB with `Size` 0; 36 to 42 MiB with the cache off). Flag: the frozen lower bound on D(64) - D0 missed (39.1 against 51.2); the optional 2.1 GiB arm was not run. | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control:** the capacity of the same cache, a cap known to bind on the same resource: unit peak 59 / 121 / 249 MiB at C = 64 / 128 / 256 MiB (the no-cache loop 0); cluster D 167 / 368 / 1119 MiB at 64 / 256 / 1024 MiB with `Size` at capacity, against a cache-off rise of 128 (94 on repeat) MiB. Without a guard-level variation (the constant cannot be varied) the guard itself is tested directly in W1: it refuses one oversize value and has no effect on the total.

**Nuance:** the guard does bound each single allocation to just under 2 GiB (W1, no allocation above it); "does not cap" is about the total.

**Feedback filed:** the case file's section D "Stage-4 feedback" filled (case file untracked, no commit; sha256 of the file with D filled: `6fb190c6ab8df41c492444012b8375e0b6d2b8bc22598e56a2531dd38bc0fd7d`; the frozen hash above is of the file before D). Sections amended: B2i and B3i (the audit amendments, dated 2026-10-25, before the freeze). No change to B1, B2f, B2g, B3f, B3g.

**Other findings:** `SerializingCache.clear()` leaves native memory allocated (unit probe; not tested on a live node), an upstream bug candidate with a JIRA check first.

**Left on the node (`pc07`):** nothing running (no `CassandraDaemon`, no ant JVM of this run; ports 7077, 9077, 7277 free). Files: `~/s4-es/{cassandra,node-tree,driver,run1,logs}` (about 0.9 GB, build trees and logs; the node data directory `~/s4-es/node1` and the shakedown outputs were removed).
