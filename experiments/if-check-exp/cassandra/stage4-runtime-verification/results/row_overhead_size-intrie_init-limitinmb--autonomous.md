# row_overhead_size-intrie_init-limitinmb--autonomous — stage-4 results  <!-- file: results/row_overhead_size-intrie_init-limitinmb--autonomous.md -->

> **Case:** [`row_overhead_size-intrie_init-limitinmb--autonomous`](../../stage3-ai-deep-read/cases/row_overhead_size-intrie_init-limitinmb--autonomous.md)
>
> **Status:** **Self-checked 2026-10-28 — unit Confirmed (caps, soft), cluster Confirmed (caps, soft); sub-predictions missed: the "10 percent more keys stay under 1.1 x threshold" bound (N = 16: 1.163; N = 1861 and 2047: the continuation hit the hard limit), the sampled peak of the N = 16 arm (0.9975 x threshold at 100 ms), the direct-pool window at a second signal, and "CREATE TABLE with N = 2048 leaves no table" (the schema entry stays); no run 2**
>
> **Outcome class:** true positive — stage-3 estimate `positive` against the stage-4 effect `caps` (soft: the owner must switch the trie, which `TrieMemtable` does) ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (U1-U5 in B2, C1-C7 in B3, dated 2026-10-27): unit attempt 1 on `35153c77fad81752d8c21451266dc5d06cadeee314110cc2528a5599d2f9722f` (before the runbook-defect amendment U5); unit attempt 2 and the whole cluster tier on `ea9f3271275a346f6ec83c2ca535d82eb04a4b9940a44cb365b705498279937f` (U5 adds the dated defect note only; unchanged until section D was filled). Repository HEAD of this session `6e6cf92`; case file, harness and results uncommitted. The frozen text is everything above section D. |
| **Harness** | [`harness/row_overhead_size-intrie_init-limitinmb--autonomous/`](../harness/row_overhead_size-intrie_init-limitinmb--autonomous/README.md), uncommitted: `RowOverheadThresholdProbeTest.java`, `unit-run.sh`, `unit-all.sh` (B2); `make-node.sh`, `trie.yaml`, `Jmx.java`, `cluster-run.sh`, `chain.sh`, `analyze.py`, `selfcheck.py` (B3); adapted from the closed trie case's `make-node.sh`/`trie.yaml`/`Jmx.java`, whose conclusions were not used. **Instrument checks (not readings):** `javac` of the probe against the build; a shakedown of the unit probe (N = 1 with real keys; 0 and 2048 threshold-only; the skip-list read), seen before the freeze (U3a): it showed the unwrapped `AssertionError`, the missing `DatabaseDescriptor` initialisation and JDK 11 flags (fixed); a one-arm shakedown of `cluster-run.sh` (N = 16, 20,000 inserts, discarded: 2 signals, flush usage 16.014 MiB, peak 0.976 x threshold). |
| **Tiers and values** | Unit (B2): knob unset, 1, 16, 64, 512, 2047 on `OFF_HEAP` and 16, 64 on `ON_HEAP` with real random-key writes up to the flip and 10 percent more keys; invalid 0, 2048, -5, -1, `abc`; controls `cassandra.trie_size_limit_mb=64`, and the skip-list memtable's row overhead with the property unset and 64. Cluster (B3): single node, 16 GB heap, `-D` N = 16 (`a16`), 64 (`a64`), unset (`adef`), 2048 (`a2048`), N = 16 on `heap_buffers` (`h16`), N = 16 at the default 40 shards (`s16`), and a skip-list table with N = 64 (`c64`); 60,000 / 240,000 / 1,000,000 / 1,000 / 60,000 / 600,000 / 240,000 inserts of 2000-byte keys. Both tiers kept. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes of one trie's buffers; the claim is the threshold set by the guarded value (A1, B1). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: unset, 1, 64, 2047 and invalid values; B3b: 16, 64, default and the invalid 2048. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d/B3d named `allocatedPos`/`sizeOffHeap` and "tablestats"; the table metric `MemtableOffHeapSize` is `allocatedPos` (a proxy); added the direct pool, the `Enqueuing flush ... Usage` lines and operations per flush (C4); the heap_buffers arm (C1). |
| A. Core question | usage driven to the limit and past it | Met | unit: real keys until the flip (up to 47 million keys for 2047) and beyond; cluster: 5 to 9 flush intervals per arm. |
| B. Logic | each step says what it establishes | Met | B2e/B3e numbered. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f's unset threshold `1951432704` is an arithmetic slip (correct: 1951399936); "one block of growth per write" ambiguous; "ExceptionInInitializerError" wrong for an `Error` thrown by a static initialiser; numbers added (U3). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | no row for the 10 percent allowance, the heap_buffers equivalence or the controls: added (U4, C6). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | flip at N x 1048576 for every N (ceiling follows the knob); the disallow branch is the `TrieMemtable` signal and flush (cluster) and the `AssertionError` for the guard. |
| B. Logic | alternative explanations and their controls | Partly | memtable-wide cleaner firing first (set out of the way, C1); skip-list control with the same `-D` (B3h, arm `c64`); `trie_size_limit_mb` (unit control). |
| C. Specific | a human can follow it from the intro and B1/B2g/B3g | Met | A1-A4, B1. |
| C. Specific | an AI can run B2a-B2e / B3a-B3e without re-deriving the code path | Partly | launcher and flags (U1), the node settings and workload (C1-C3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | "1-2 million keys", "S shards" not exact: replaced (U2, C2, C3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | written in step 1 (this session). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | unit 2047/unset: 47 and 43 million keys in about 42 s each at 10 GB heap / 6 GB direct; cluster: 2.3 KB of trie per insert, 7157 inserts per 16 MiB, `adef` 1,000,000 inserts in 3 min, local disk 0.2-1 GB per arm. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `cassandra/cassandra-5.0.9`: `InMemoryTrie.java:58-68` (threshold and guard; the javadoc about 2GB is at `:46`, not `:43`), `:140-159`, `:945-953`, `:971-981`; `TrieMemtable.java:192-196`, `:202-204`; `SkipListMemtable.java:72-80`; `CassandraRelevantProperties.java:356-358`; `AbstractShardedMemtable.java:46` (default shard count = processors). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Correct thresholds and the exception form (U3) | Applied 2026-10-27 | arithmetic slip; JLS 12.4.2 |
| R2 | Real-key flip test and controls (U2) | Applied | the filed unit tier named no loop bound |
| R3 | Node settings, shard count and allocation type, workload sizes (C1-C3) | Applied | not runnable as filed |
| R4 | Arms `h16`, `s16`, `c64`, `a2048` and numeric predictions (C2, C5) | Applied | B3b/B3h/B3f needed numbers |
| R5 | For stage 3: the 10 percent allowance of the javadoc is not an invariant of the writes (see 4.2 part 2) | left for stage 3 | observed in the unit tier |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | unit 2026-10-27/28 (node clock UTC 2026-10-28 03:55-04:05, attempt 2 right after attempt 1); cluster 2026-10-28 (node clock UTC 12:05-12:21) |
| Node | `pc41` = `node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 (2026-08-18) |
| Ant | Apache Ant 1.10.12 |
| Local source copy | `~/c4-ros` from `cassandra/cassandra-5.0.9/` at repository commit `6e6cf92` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL |
| Case-file / harness commit | uncommitted (working tree of `6e6cf92`); hashes in section 1; harness md5s in `run1/harness-unit.md5` and `run1/harness-cluster.md5` |
| Storage for node data | `~/stage4-ros/node` on local `/dev/sda3`, removed after each arm; nothing under `/proj` |
| Full logs (outside the repo) | `pc41:~/stage4-logs/ros/run1/{unit,unit-attempt1-no-exhausted-catch,cluster}/` (per arm: `samples.csv` at 100 ms, `system.log`, `stress.txt`, `tablestats.txt`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | unit shakedown | B2a, skip-list control | `SkipListMemtable` initialiser needs the config loaded; `DatabaseDescriptor` needs the JDK 11 module flags | `daemonInitialization()` in the probe; flags from `jvm11-server.options` in `unit-run.sh` | before the freeze (U3a) |
| D2 | unit attempt 1 | B2c, the 10 percent continuation | `SpaceExhaustedException` not caught: for 1861 and 2047 the JUnit method failed after the flip and `END10` was not written | catch and record `EXHAUSTED`; unit tier run again from its beginning; case-file U5 (dated) | 2026-10-27/28, claim, prediction and table unchanged |
| D3 | cluster | B3d, the 100 ms sampler | a 16 MiB trie fills in 1.2 s; the peak sample may fall short of the threshold | none needed; the flush lines' `Usage` is the exact reading | recorded |

## 4. Run 1

**Scope:** every B2 and B3 value of section 1. **Command logs:** `row_overhead_size-intrie_init-limitinmb--autonomous/run1/` (`unit/*.out`, `cluster/<arm>/{analysis.txt,system-log-excerpt.txt,cmdlog-head.txt,...}`, `selfcheck.txt`). T = the threshold N x 1048576.

### 4.1 Readings

**Unit tier** (`run1/unit/`)

| Test or assertion | Result | Evidence |
|---|---|---|
| `ALLOCATED_SIZE_THRESHOLD` | unset 1951399936 (1861 MiB); 1 -> 1048576; 16 -> 16777216; 64 -> 67108864; 512 -> 536870912; 2047 -> 2146435072; exactly N x 1048576 | `off-*.out` `THRESHOLD` |
| first `reachedAllocatedSizeThreshold()` flip (real keys), `OFF_HEAP` | `allocatedPos` at the flip = T + 32 (1), + 224 (16), + 32 (64), + 0 (512), + 0 (unset), + 256 (2047); keys at the flip 20,902 / 306,756 / 932,063 / 11,675,257 / 43,132,055 / 46,985,513; `sizeOffHeap == allocatedPos` | `FLIP` lines |
| `ON_HEAP` (16, 64) | same keys and `allocatedPos` as `OFF_HEAP`; `sizeOffHeap` 0; `sizeOnHeap` 18.0 / 70.8 MB (>= `allocatedPos`) | `on-16.out`, `on-64.out` |
| 10 percent more keys after the flip | `allocatedPos` / T = 1.0835 (1), **1.1626 (16, both buffer types)**, 1.0781 (64), 1.0945 (512); for unset and 2047 the writes reached the hard limit before 10 percent more keys: `SpaceExhaustedException` at `allocatedPos` 2147483392, 3,873,449 keys (9.0 percent) after the flip for unset and 19,991 keys after it for 2047 | `END10` / `EXHAUSTED` lines |
| invalid 0, 2048, -5, -1 | first use raises `java.lang.AssertionError` "cassandra.memtable.row_overhead_size must be within 1 and 2047" (not wrapped); 1 and 2047 load | `bad-*.out` |
| `abc` (observation) | `ExceptionInInitializerError` with root `ConfigurationException` "expected integer value but got 'abc'" | `bad-abc.out` |
| `cassandra.trie_size_limit_mb=64`, knob unset | threshold stays 1951399936 | `ctl-triesize64.out` |
| skip-list memtable, same JVM | `ROW_OVERHEAD_HEAP_SIZE` 64 with `-D` 64 (trie threshold 67108864 in the same JVM); 2048 with 2048 (trie guard failed in the same JVM); 172/173 estimated when unset | `ctl-skiplist-*.out`, `bad-2048.out` |

**Cluster tier** (`run1/cluster/<arm>/analysis.txt`; `Usage` from the `Enqueuing flush of ks.t, Reason: MEMTABLE_LIMIT` lines)

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| 16 MiB | `a16`, 60,000 inserts | signals; usage; ops per flush | 8 signals and 8 `MEMTABLE_LIMIT` flushes at 16.013-16.016 MiB off-heap; 7156-7160 ops each (last, `DRAIN`, 2739) | `system-log-excerpt.txt` |
| | | sampled `MemtableOffHeapSize` max | 16,734,477 = 0.9975 T (100 ms samples; the peaks before the signals 0.927-0.9975 T) | `analysis.txt` |
| 64 MiB | `a64`, 240,000 inserts | signals; usage; ops | 8 signals/flushes at 64.032-64.035 MiB; 28750-28760 ops each; sampled max 1.0004 T | same |
| unset (1861) | `adef`, 1,000,000 inserts | signal; usage; ops | 1 signal, flush at 1.818 GiB (1861.6 MiB) off-heap, 827,631 ops; sampled max 1.0004 T | same |
| 2048 | `a2048` | node start; `CREATE TABLE ... memtable = 'trie'`; inserts | node starts; `CREATE TABLE` returns the server error "java.lang.AssertionError: cassandra.memtable.row_overhead_size must be within 1 and 2047"; `DESCRIBE` afterwards still shows `ks.t` with `memtable = 'trie'`; inserts fail with `IllegalArgumentException: Unknown CF` (595 in `system.log`), the stress tool reports 12 ops/s and 0 errors (it retries); no `NoClassDefFoundError` line | `schema.txt`, `system-log-excerpt.txt`, `stress-summary.txt` |
| 16 MiB, `heap_buffers` | `h16` | signals; usage; ops | 8 signals; flush lines "18.165 MiB on-heap, 0B off-heap"; 7157-7164 ops each | same |
| 16 MiB, 40 shards | `s16`, 600,000 inserts | first flush | `MEMTABLE_LIMIT` at 623.9 MiB off-heap (39.0 x 16), 280,708 ops (39.2 x one `a16` flush); sampled max 39.1 T | same |
| skip-list table, N = 64 | `c64`, 240,000 inserts | signal lines; flushes | no trie-size line, no `MEMTABLE_LIMIT` flush (only the `DRAIN`), no "Estimated SkipListMemtable row overhead" line; memtable off-heap max 480 MB = 7.2 x 64 MiB | `system-log-excerpt.txt`, `analysis.txt` |
| direct pool at the first signals (delta over the start) | `a16`, `a64`, `adef` | MiB | 19.3 (16), 67.3 and 131.4 (64; the second signal with two tries alive), 2051 (1861) | computed from `samples.csv` on the node |

### 4.2 Conclusion and logic

1. **Validity.** Valid. The threshold was reached by every valid value in both tiers [observed: `FLIP` lines; signals in `a16`, `a64`, `adef`, `h16`, `s16`]. Held-fixed settings: the property reached the process [observed: `proc-args.txt`: `-Dcassandra.memtable.row_overhead_size=` 16 / 64 / (none) / 2048 / 16 / 16 / 64] and the shard count [observed: `-Dcassandra.memtable.shard.count=1`, absent for `s16`]; heap 16 GB and direct 10 GB [observed: `vmflags.txt`]; the memtable-wide cleaner did not fire [observed: no `MEMTABLE_LIMIT` flush except the ones with the trie-size line before them, signal count = flush count in every arm; `c64` shows no cleaner flush at 458 MiB]; no leftover daemon [observed: `daemons left: 0` in each `cmdlog-head.txt`; `ps` after the chain: 0].
2. **Readings.** (a) The "10 percent more keys stay under 1.1 x T" sub-prediction (U3b) missed: 1.1626 T for N = 16 on both buffer types, and for unset and 2047 the continuation reached the hard limit before 10 percent more keys [observed]. [inferred: random 16-byte keys allocate more per key in some stretches of the key count than in others, so the allowance of the javadoc ("up to 10% growth above this threshold") is a sizing assumption, not a bound; at 1861 MiB the allowance is the whole of the 196 MB left under the hard limit]. (b) The sampled peak of `a16` is 0.9975 T, below T, although the flush line shows 16.014 MiB: sampling resolution (a sample every 100 ms, 11 MB per second) [inferred; the flush lines are exact]. (c) The direct pool delta at the second signal of `a64` is 131.4 MiB, above the predicted 2 x 64 [observed]; [inferred: two tries alive during the flush, 64 MiB written and flushing plus the new one filling]. (d) `a2048`: the guard fires where the case says (first use of the trie class) and the client sees its message, but the schema change is already applied: the table is in the schema and unusable ("Unknown CF"), so the predicted "no trie table exists afterwards" missed [observed]. (e) The other numeric predictions held: thresholds, flip window, `sizeOffHeap`/`sizeOnHeap`, exception form, controls, flush usage in [N, 1.02 N], ops ratio a64/a16 = 4.017, h16 within 0.1 percent of a16, at least 5 flushes, `s16` first flush in window, `c64` empty of trie lines [observed: `selfcheck.txt`, 48 PASS].
3. **Matched row.** Unit B2g row 1 "Flip at size ~ N MB for every valid N -> claim confirmed": flip at T to T + 256 bytes for 1, 16, 64, 512, 1861, 2047 [observed: `FLIP` lines]; the invalid-value rows ("N=0 or 2048 loads without error", "N=1 or 2047 throws") did not occur: 0, 2048, -5, -1 raise the AssertionError and 1 and 2047 load [observed]. Cluster B3g row 1 "Flush interval scales with N -> claim confirmed": ops per `MEMTABLE_LIMIT` flush 7157 (16), 28752 (64) = 4.017 x, flush usage 16.01 / 64.03 / 1861.6 MiB for N = 16 / 64 / 1861, signal lines = flushes [observed: `selfcheck.txt`].
4. **Excluded rows.** "Flip size independent of N" (B2g row 2), "same flush interval for N=16 and N=64" (B3g row 2): no [observed]; "memtable size far above 1.1 N per shard with no flush message": no, the one-shard arms peak at 1.0004 T [observed]; "no flush message before a heap-pressure flush": no, no other flush reason occurred before the signals [observed]; "flip never reached": no [observed]. The `s16` arm is consistent with a per-shard threshold (39 x 16 MiB in the first flush with 40 shards) [observed].
5. **Observed vs. inferred.** Inferred: the causes in part 2 (a), (b), (c). None enters the verdict, which rests on the flip window, the flush `Usage` and ops-per-flush readings.
6. **Deviations and gaps.** Shard count held at 1 except `s16`; the table metric is a proxy for `allocatedPos` (the flush `Usage` and the unit `allocatedPos` agree to 0.02 percent); the `heap_buffers` arm shows the same ops per flush as `offheap_buffers` (the cap is the same number of trie bytes) but its on-heap metric (18.2 MiB at 16 MiB of trie plus content objects) is not equal to the threshold; the cluster tier cannot drive the trie to the hard limit (the signal switches the memtable first); SAI tries (no soft guard) were not tested. One run per arm.
7. **Core question.** The guarded value sets a per-trie ceiling: with N = 1..2047 the trie's `allocatedPos` flips the owner's signal at N MiB (T to T + 256 B) and the memtable is switched there, in 7 to 8 consecutive flushes of identical size (7157 ops at N = 16, 28752 at N = 64), so trie memory per shard follows N; values outside 1..2047 make the class fail with the AssertionError, and the node then cannot use a trie table (parts 3 and 4). The cap is soft: writes beyond the flip continue (up to 16 percent above T for N = 16 in 10 percent more keys, and the hard limit is reached within 10 percent more keys for N >= 1861), and the node total is not bounded (two tries alive during a flush, and `s16`'s 39 x N).

**Conclusion (one line):** Unit B2g row 1 — confirmed (caps, soft); Cluster B3g row 1 — confirmed (caps, soft), with the 10-percent-overshoot bound, the N = 16 sampled peak and "no table after N = 2048" missed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-28: all `unit/*.out` and the cluster excerpts re-parsed by `harness/.../selfcheck.py` (`run1/selfcheck.txt`: 48 PASS, 0 FAIL, "ALL PASS", plus NOTE lines for the missed sub-predictions), and by hand `cluster/a2048/schema.txt`, `cluster/a2048/system-log-excerpt.txt`, `cluster/c64/system-log-excerpt.txt`, `cluster/a16/analysis.txt`, `unit/off-default.out`, `unit/off-2047.out`, and `ps` on the node.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `proc-args.txt` of the seven arms; `vmflags.txt`; flush lines all `MEMTABLE_LIMIT` with a preceding signal; 0 daemons. |
| 2. Readings | yes | `off-default.out` `EXHAUSTED ... keysAfterFlip=3873449`; `off-2047.out` `keysAfterFlip=19991`; `a16/analysis.txt` 0.9975; the a64 direct delta 131.4 MiB recomputed from `samples.csv`. |
| 3. Matched row | yes | `selfcheck.txt` flip windows and ratios (4.017, 1.001). |
| 4. Excluded rows | yes | `bad-*.out` all AssertionError; `off-1.out` and `off-2047.out` load. |
| 5. Observed vs. inferred | yes | inferences limited to causes of misses. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question — the steps follow the audited logic | yes | knob -> threshold (unit) -> flip window -> flush interval (cluster) -> controls (`c64`, `h16`, `s16`) -> guard failure (`bad-*`, `a2048`). |

### 5.2 Run 2?

**No** (2026-10-28). The unit readings are exact values in 16 independent JVMs, and the cluster readings repeat in 8 consecutive flushes per arm; the sub-prediction misses are about secondary bounds. A run 2 could sample the metric faster than 100 ms.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps): the guarded value becomes `ALLOCATED_SIZE_THRESHOLD`, the memtable is switched when the trie's allocated bytes reach it, and trie memory per shard follows it; the cap is soft.

**Claim tested (B1):** with `-Dcassandra.memtable.row_overhead_size=N` (1 <= N <= 2047), a TrieMemtable shard requests flush when its trie reaches about N MB of allocated bytes, so trie memory per shard stays near N MB (plus up to ~10% overshoot); values outside 1..2047 make `InMemoryTrie` fail to initialize.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1: flip at N x 1048576 for every valid N; invalid values fail with the AssertionError); the 10 percent overshoot sub-prediction missed (16 percent at N = 16; the hard limit reached within 10 percent more keys at N >= 1861) | caps (soft, per trie) | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (B3g row 1: flush interval scales with N, 4.017 x for 4 x N; usage at the flush equals N); N = 2048 fails at the first use but leaves an unusable table in the schema; skip-list control shows no trie behaviour | caps (soft; node total not bounded) | run 1 + self-check | 2026-10-28 |

**Feedback filed:** the case file's section D updated (no commit by this session); amendments U1-U5 (B2) and C1-C7 (B3), dated 2026-10-27.
