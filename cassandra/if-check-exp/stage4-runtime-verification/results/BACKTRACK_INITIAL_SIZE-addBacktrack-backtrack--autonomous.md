# BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous — stage-4 results  <!-- file: results/BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous`](../../stage3-ai-deep-read/cases/BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster), both with the amendments B2i and B3i; "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `25b4a70`; the case file is **untracked** in the working tree. The file as filed had sha256 `d9ec6f6b8cda7fe19ecc04fcd4befb4842996adaa60b47bba00875320fc6e4ef`. **sha256 after the audit's amendments (B2i and B3i, dated 2026-10-25): `2cf32d77b6978345728e27581ba515b7cc9b842234a7e32f45c9e2daefa40725`**, written to `~/s4-bt/logs/freeze.sha` at 2026-10-25 17:58:59Z and to this file, before any harness existed and before any reading. B2f, B2g, B3f, B3g with B2i and B3i are frozen at this hash. **Re-freeze:** a clarification (B3i.9, a harness step: flush the residual filler before writing the comb; no prediction or row changed) was added after the cluster instrument shakedown and before run 1 of either tier; the file's sha256 is then **`619b02fa34f0e1b50d80b6e81fe4e746a3d3dc1f78cfe9551e24e85e5bda1c83`** (also in `~/s4-bt/logs/freeze.sha`), which is the version both tiers' runs use. The unit tier's run 1 started before this clarification (unit text unchanged by it). Section D (the feedback) is filled afterwards; the sha256 with D filled is in section 8. |
| **Harness** | `harness/BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous/`: `BacktrackSizeTest.java`, `BtHelper.java`, `bt.btm`, `unit-run.sh`, `compile-helper.sh`, `instrument-check.sh`, `cluster-run.py`, `analyze_unit.py`, `analyze_cluster.py`, `selfcheck.py`; written after the first freeze; not committed (md5s: `BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous/run1/unit/harness.md5` at the unit run, `.../cluster/harness.md5` at the cluster run; `cluster-run.py` and `bt.btm`/`BtHelper.java` changed during the cluster shakedowns, before either md5 file for the cluster run) |
| **Tiers and values** | **Unit (B2):** chain / sparse / split combs at D = 8, 64, 1024, 65535, ON_HEAP and OFF_HEAP, filler F = 0, 1e5, 1e6, putSingleton cross-check, fresh vs reused cursor, positive control with the trie size threshold T = 8, 16, 32 MiB (three fresh JVMs). **Cluster (B3):** labels hb64, hb256, hb512, oo64 (ByteOrderedPartitioner, trie memtable, comb D = 1000), m3 (Murmur3 control, filed workload), sl (skiplist contrast). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate: **negative** (the doubling check at `InMemoryReadTrie.java:501` is a growth rule, not a cap). Audited against `cassandra/cassandra-5.0.9/` (`git status` of it clean; `build.xml` `base.version` 5.0.9). Re-read in the pinned source: `InMemoryReadTrie.java:157-163, 218-219, 485-506, 540-616, 625-783`, `InMemoryTrie.java:40-135, 270-355, 418-450, 695-900, 940-980`, `TrieMemtable.java:94, 123-215, 296-300, 350-354, 440-490`, `DecoratedKey.java:105-133`, `ColumnFamilyStore.java:1558-1579`, `IPartitioner.java:148`, `AbstractShardedMemtable.java:53-86`, `MemtableParams.java:99-135`, `TableAttributes.java:124-125`, `CassandraRelevantProperties.java:356`, `DatabaseDescriptor.java:753-763`, `FBUtilities.java:158`, `QueryProcessor.java:259`, `conf/cassandra.yaml:389, 783-799, 825`.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-heap `int[]` scratch of each trie cursor (bytes = 16 + 4 L). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly → Met | The constant cannot be varied (A1). The design varies what the claim says it follows: trie shape and depth (four depths, three shapes), and what it should not follow: buffer type, trie byte size (filler, B2i.5a) and `memtable_heap_space` 64/256 (default)/512 MiB plus an off-heap label (B3i.3). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | The array's real length is read by reflection (unit) and by a Byteman rule on the growth statement (cluster, B3i.5). `measureDeep(cursor)` was invalid (B2i.2). Gap named: live count of cursors at an instant is not observed (inferred bound, B3i.6d); no heap dump. |
| A. Core question | usage driven to the limit and past it | Partly → Met | Unit: past 16 entries by depth up to 65535. Cluster: the filed Murmur3 workload cannot reach the growth statement (B3i.2); a ByteOrderedPartitioner comb is added, and Murmur3 stays as a control. |
| A. Core question | positive control for a negative estimate | Partly → Met | The filed unit step 7 needed a 2 GiB trie; replaced by the trie's own allocated-size threshold (B2i.5c). Cluster: first limit-driven flush size scales with `memtable_heap_space` (B3i.6f). |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f/B3f were relations with loose figures (for example "6144 at most"); exact table in B2i.6 and numbers in B3i.6, derived from `:501-506` and the sparse/split node rules. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | Rows added: B2i.7 and B3i.7 (numeric miss, control failed, invalid, no match). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For this "does not cap" claim: there is no disallow branch (the check always grows); the evidence is the direct reading of the array at all knob values and the accounted size. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h plus chain control, filler, `m3`, `sl`. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3 and B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | Table syntax resolved (`WITH memtable = 'trie'`, B3i.1), comb definitions and workloads spelled out (B2i.4, B3i.4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Per label settings (B3i.3), scan statement, durations, ports (B3i.8). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ant build-test` tree built here (1 min 11 s); Byteman 4.0.20 jar in `build/lib/jars`; test, helper class, driver are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: D = 65535 in O(D) with the generator (about 3 MB arrays, trie under 10 MB). Cluster: 400,000 x ~1.2 KB reaches the first flush at 1/3 of 512 MiB (about 171 MiB); 0.5 GB per label on 40+ GB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | All re-read; no line numbers off except `InMemoryTrie.java:91` (comment; constructor :88). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Resolve the table syntax: `WITH memtable = 'trie'`, no yaml edit | Applied, B3i.1, 2026-10-25 | The filed map form is not accepted by `TableAttributes.java:125`. |
| 2 | Use ByteOrderedPartitioner for the cluster comb; keep Murmur3 as a control | Applied, B3i.2-3, 2026-10-25 | Under Murmur3 the trie never branches deeper than about 3 bytes, so `:502` cannot run. |
| 3 | Replace `measureDeep(cursor)` by the array size | Applied, B2i.2 | It follows `this$0` into the whole trie. |
| 4 | Build combs by one `apply` of a generated trie | Applied, B2i.3 | D^2/2 byte steps at D = 65535 otherwise. |
| 5 | Exact predictions for E and L; extra rows | Applied, B2i.6-7, B3i.6-7 | Relations cannot be contradicted. |
| 6 | Positive controls (trie threshold; first-flush size vs `memtable_heap_space`) | Applied, B2i.5c, B3i.6f | Filed unit step 7 was not runnable; filed cluster control had no numbers. |
| 7 | Byteman instrument instead of a heap dump | Applied, B3i.5 | No analyser; the rule reads every cursor's array exactly. |
| 8 | Filler arm for trie byte size at fixed shape; skiplist contrast label | Applied, B2i.5a, B3i.3 | B2g row 2 and B3h had no arm for them. |
| 9 | Fix `InMemoryTrie.java:91` to :88 (constructor) | Left for stage 3 | Cosmetic. |

**Agreement criteria** — not applicable (run 2 not chosen unless §5.2 says so).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (unit 14:02 EDT; cluster 14:17 to 14:41 EDT) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB, shared with two other runs (tags `nc`, `st`) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-bt/cassandra` made by `copy-source.sh` at repository commit `25b4a70`; `ant build-test` 1 min 11 s; the unit test ran there (`ant testsome`). The node ran from `~/s4-bt/node-tree`, a `cp -a` of the built copy, in which `ant` was never run. Nothing built in the repository's `cassandra/cassandra-5.0.9/`. | |
| Case-file commit / harness commit | case file untracked at `25b4a70`, sha256 in §1; harness uncommitted | |
| Storage for node data | `/dev/sda3`, ext3, 63 GB (41 to 43 GB free); node data under `~/s4-bt/node1` (data and commit log removed after each label) | |
| Full logs (path, outside the repo) | `pc07:~/s4-bt/run1/{unit,cluster}/` (full `ant.log`, `system.log` per label, `bt-stats.txt`, `result.json`, `session.log`); excerpts in `BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous/run1/` | |

**Environment deviations (none changes B1):** (1) `/tmp/c509` replaced by `~/s4-bt/cassandra`. (2) The cluster load and scans are a Python driver script (bundled driver 3.29.0), not `cassandra-stress`. (3) The node listens on `127.0.0.88` with storage 7088, native 9088, JMX 7288 (shared host); `nodetool` is called with `-p 7288`. (4) `read_request_timeout`, `write_request_timeout`, `native_transport_timeout` were raised to 60 s (no effect seen). (5) The live command line carries Cassandra's default `-XX:MaxDirectMemorySize=15872M`. (6) The scan phase is 90 s per label (as amended, B3i.4), the filled B3c's 5 minutes shortened; B3c's "10 min per configuration" became about 4 min per label. (7) Heap dump and dominator analysis dropped (B3i.5). (8) Every amendment is in the case file's B2i and B3i, dated 2026-10-25.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2d | `ObjectSizes.measureDeep(cursor)` follows the inner class's `this$0` into the whole trie. | Array bytes = 16 + 4 L from reflection: B2i.2. | 2026-10-25, before the freeze | none (case file untracked) |
| 2 | audit | B2c/B2e | One `putSingleton` per key costs D^2/2 steps at D = 65535. | Linear-time generator trie applied by one `apply`; one arm also built by `putSingleton`: B2i.3. | 2026-10-25, before the freeze | none |
| 3 | audit | B2e step 7 | "Insert until `SpaceExhaustedException`" needs a 2 GiB trie. | The trie's own size threshold as the cap that binds: B2i.5c. | 2026-10-25, before the freeze | none |
| 4 | audit | B3c | Under Murmur3 a TrieMemtable's trie cannot branch deeper than about 3 bytes, so the growth statement never runs. | ByteOrderedPartitioner comb labels, Murmur3 kept as a control: B3i.2-4. | 2026-10-25, before the freeze | none |
| 5 | audit | B3a/B3c | `WITH memtable = {'class': 'TrieMemtable'}` is not accepted; the option is a configuration key. | `WITH memtable = 'trie'`: B3i.1. | 2026-10-25, before the freeze | none |
| 6 | instrument shakedown | B3a (harness) | First node start with ByteOrderedPartitioner failed: `Token type BytesToken does not support token allocation` (default `num_tokens: 16` with `allocate_tokens_for_local_replication_factor: 3`). | Harness sets `num_tokens: 1` and removes the allocation setting for BOP labels (noted in B3i.9). | 2026-10-25, before run 1 | none |
| 7 | instrument shakedown | B3c (ii)-(iii) | With a small filler a limit flush caught the half-written comb (two flush cursors grew only to 768 ints). | `nodetool flush ks t` after the wait, before the comb: B3i.9; case file re-hashed (§1). | 2026-10-25, before run 1 of the cluster tier | none |
| 8 | instrument shakedown | B3i.5 | The helper class is loaded by the first rule that fires, so a label with no cursors (`sl`) would have had no stats file. | Third rule `bt init` on `CassandraDaemon.setup` calls `BtHelper.init()`. | 2026-10-25, before run 1 | none (harness only) |

## 4. Run 1

**Scope:** unit tier, all arms in three fresh JVMs (T = 8, 16, 32 MiB); cluster tier, labels hb64, hb256, hb512, oo64, m3, sl. **Command log:** `BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous/run1/unit/session.log`, `.../cluster/session-noacct.log`. Checks of the frozen numbers: `.../unit/analyze_unit.out` (517 pass, 0 fail) and `.../cluster/analyze_cluster.out` (36 pass, 0 fail). Instrument check (not a reading): `.../cluster/instrument-check-bt-stats.txt` (sparse D = 64 under the Byteman rules: 1 cursor, grow48 = 1, grow96 = 1).

### 4.1 Readings

**Unit tier** (E = maximum `backtrackDepth` over the walk, L = final `backtrack.length` in ints; identical in all three JVMs and for ON_HEAP and OFF_HEAP; `unit/results-T8.csv`, `-T16.csv`, `-T32.csv`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Fresh cursor on every trie | L0 = 48 in all 105 rows | `unit/results-T*.csv` column L0 |
| chain, D = 8, 64, 1024, 65535 | E = 0, L = 48 | same, arms `chain_*` |
| sparse comb, D = 8 / 64 / 1024 / 65535 | E = 8 / 64 / 1024 / 65535; L = 48 / 192 / 3072 / 196608 (array 16 + 4L = 208 B / 784 B / 12,304 B / 786,448 B) | arms `sparse_*` |
| split comb, D = 8 / 64 / 1024 / 65535 | E = 24 / 192 / 3072 / 196605; L = 96 / 768 / 12288 / 786432 | arms `split_*` |
| sparse D = 64 + filler F = 0 / 100,000 / 1,000,000 | E = 64, L = 192 each; `sizeOnHeap()` 5,180 / 5,221,980 / 76,822,204 B (ON_HEAP, T8) | arms `fill_*` |
| sparse D = 1024 built by 1025 `putSingleton` calls | E = 1024, L = 3072 (same as the generator-built arm) | arm `put1024` |
| Generator known answer | content nodes visited = keys inserted in every arm (for example 65, 1025, 6145, 65536, 393211, 1,000,065) | column `contentNodes` = `expectedContent` |
| Cursor does not change the accounted size | `sizeOnHeap()` and `sizeOffHeap()` equal before the cursor and after the walk in every arm | columns `sizeOnBefore`..`sizeOffAfter` |
| Fresh vs reused cursor | the walked cursor keeps L = 192; a new cursor on the same trie has L = 48 | arm `reuse` |
| Positive control, T = 8 / 16 / 32 MiB | `ALLOCATED_SIZE_THRESHOLD` = 8,388,608 / 16,777,216 / 33,554,432; `reachedAllocatedSizeThreshold()` false at T-1 MiB, true at T MiB; `sizeOffHeap()` = allocated position (32,505,856 then 33,554,432 for T = 32); the D = 1024 comb in that trie still gives L = 3072 | arm `thr` |
| Test class | `Tests run: 1, Failures: 0, Errors: 0` in each JVM | `unit/ant-T*.tests` |

**Cluster tier** (`cluster/<label>/bt-stats.txt`, `summary.json`; N = count of each growth event; the largest array is 2 x the largest old length)

| Label | Run | Observable (B3i.5) | Reading | Evidence (file) |
|---|---|---|---|---|
| hb64 | BOP, trie, heap_buffers, `memtable_heap_space` 64MiB | grow events by old length; cursors; largest array | 48, 96, 192, 384, 768, 1536 each N = 10,673; cursors 10,729; no event at 3072; largest array 3072 ints = 12,304 B | `hb64/bt-stats.txt` |
| hb256 | 256MiB (default) | same | each N = 10,459; cursors 10,473; largest 3072 ints | `hb256/bt-stats.txt` |
| hb512 | 512MiB | same | each N = 10,565; cursors 10,573; largest 3072 ints | `hb512/bt-stats.txt` |
| oo64 | `offheap_objects`, heap 64MiB + off-heap 64MiB | same | each N = 10,212; cursors 10,252; largest 3072 ints | `oo64/bt-stats.txt` |
| m3 | Murmur3, filed workload | same | cursors 212,600; no grow event | `m3/bt-stats.txt` |
| sl | BOP, skiplist | same | cursors 0; no grow event | `sl/bt-stats.txt` |
| hb64 / hb256 / hb512 / oo64 | accounting around the scan phase (`MemtableOnHeapDataSize`, `MemtableOffHeapDataSize`, bytes) | before scan = after scan | on-heap 1,094,764 / 1,094,284 / 1,095,116 / 300,812; off-heap 0 / 0 / 0 / 686,932; each equal before and after about 10,000 scans; 0 after the final flush | `cluster/acct.log` |
| hb64 / hb256 / hb512 | positive control: usage at the first `MEMTABLE_LIMIT` flush of `ks.t` (on-heap) | scales with `memtable_heap_space` | 21.333 / 85.340 / 170.596 MiB (33 % of 64 / 256 / 512); ratios 4.00 and 8.00; 27 / 6 / 3 such flushes | `<label>/first-limit-flushes.txt`, `analyze_cluster.out` |
| oo64 | same | off-heap usage at the first limit flush | 21.355 MiB off-heap (33 % of 64) and 5.736 MiB on-heap | `oo64/first-limit-flushes.txt` |
| all | scan phase | scans, errors, rows per scan | 10,671 / 10,457 / 10,563 / 10,210 / 253 (m3, full scans) / 10,946 (sl) scans; 0 errors; each BOP scan returned 1001 rows | `<label>/summary.json` |
| all | context: `GC.class_histogram` row of `int[]` during the scan phase (this forces a full collection, so live arrays only) | live `int[]` bytes | 16.2 to 16.5 MB (hb64 16.3, hb256 16.2, hb512 16.2, oo64 16.3, m3 17.2, sl 16.2): the label without any trie memtable holds as much | `<label>/summary.json` `int_array_class_histogram_rows` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The check was reached and its growth branch executed: unit L went from 48 to 196,608 / 786,432 ints and the cluster's cursors grew through six doublings [observed: `unit/results-T8.csv`, `hb64/bt-stats.txt`]. Hold-fixed settings: each label's live command line has `-Xms1G -Xmx1G` and the Byteman agent, its yaml has the label's partitioner, allocation type and spaces, and its table has `memtable = 'trie'` (`sl`: none) [observed: `<label>/cmdline.txt`, `yaml-keys.txt`, `schema.txt`]; no `ERROR` line in any `system.log`, no client error, every BOP scan returned exactly 1001 rows [observed: `<label>/summary.json`, `selfcheck.out`]; the comb entered an empty memtable (flush before the comb, B3i.9) [observed: `cluster/session-noacct.log`]. The unit generator is a known-answer instrument: content nodes visited equal the keys inserted in all arms, and the `putSingleton`-built D = 1024 arm gives the same E and L [observed: `unit/results-T8.csv`].
2. **Readings** — nothing unusual: all 517 unit checks and 36 cluster checks of the frozen numbers pass [observed: `unit/analyze_unit.out`, `cluster/analyze_cluster.out`]. In hb64 the cursor count exceeds the grown-cursor count by 56 (the flushes of the filler: 28 flushes x 2 cursors) [inferred: from 29 flush lines of `ks.t` and the stack trace of a shakedown showing two flush cursors per flush]. The accounting reading "equal before and after the scan phase" is weak by itself because the accounted size changes only on writes and none were made; the unit reading (`sizeOnHeap()` unchanged by the cursor) and the code (`InMemoryTrie.java:975-980` has no term for cursors) carry that point.
3. **Matched row** — unit B2g row 1 as amended (B2i.7a): "Every L and E equals the table, ON_HEAP = OFF_HEAP, L independent of F and of T, sizes unchanged by the cursor, positive-control flags as predicted — Confirmed, does not cap" [observed: `unit/results-T*.csv`: L tracks only shape and depth, 48 x 2^k with E <= 16 x 2^k; same at ON_HEAP and OFF_HEAP; F from 0 to 1,000,000 (trie from 5 KB to 77 MB) leaves L = 192; T = 8, 16, 32 MiB leaves L = 3072; `sizeOnHeap()` unchanged; the control flags false/false/true at each T]. Cluster B3g row 1 as amended (B3i.7a): the rows (a)-(e) of the predictions hold [observed: hb64/hb256/hb512/oo64 all with the same six growth counts and a largest array of 3072 ints; `m3` zero growth with 212,600 cursors; `sl` zero cursors; accounting equal across the scan phase], and the control (f) moved [observed: first limit-flush usage 21.3 / 85.3 / 170.6 MiB, ratios 4.00 and 8.00; oo64 off-heap 21.4 MiB].
4. **Excluded rows** — unit (c) "L depends on buffer type, F or T": ruled out, L equal for ON/OFF and for every F and T [observed]. (d) "threshold flags do not flip": ruled out, they flipped at every T [observed]. (e) "arm throws / cannot run": ruled out, `Failures: 0, Errors: 0` in three JVMs [observed]. (b) "numeric prediction missed": ruled out, no prediction missed [observed: `analyze_unit.out`]. Original B2g "sizeOnHeap() rises when the cursor grows its array": ruled out [observed]. "Comb never gets past 48 ints": ruled out [observed]. Cluster (b) "largest array differs with `memtable_heap_space` or allocation type": ruled out, 3072 in all four [observed]. (c) "accounting changes with cursors": ruled out for the scan phase [observed; weak, see part 2]. (d) "arrays equal but a different size": ruled out, the size is the predicted 3072 [observed]. (e) "`m3` shows growth": ruled out, zero events [observed]. (f) "no growth / no scan / control did not move": ruled out [observed]. (g) "cursor counter absent / node died": ruled out, counters nonzero and `sl` readable at 0 [observed]. Original B3g "scales with `memtable_heap_space` or trie byte size" is the same as (b).
5. **Observed vs. inferred** — inferred statements the conclusion depends on: (i) the live bytes held by cursor arrays are small — a bound from the number of concurrent readers (16 scan threads and one flush, at most two cursors each: 34 x 12,304 B = 418 KB) and from the `int[]` class histogram being 16.2 to 16.5 MB in every label including `sl`, not from observing the live cursors; (ii) the arrays are not part of the memtable's accounted size — from the code (`InMemoryTrie.sizeOnHeap()/sizeOffHeap()` use `contentCount`, `allocatedPos` and the buffer type only) and the unit equality, with the cluster equality being weak; (iii) that `m3` does not grow because its trie branches only in the first bytes — the reach analysis behind B3i.2 is inferred from `DecoratedKey.java:105-114`; the zero-growth reading agrees but does not show why; (iv) the cause of the 56 non-growing cursors in hb64 (flush cursors on the shallow filler).
6. **Deviations and gaps** — the filed Murmur3 workload cannot reach the growth statement, so the cluster tier measures the claim on a ByteOrderedPartitioner comb (B3i.2); the cluster shape is one comb of depth 1000, not the deepest key (65,535 bytes) which the unit tier covers; no heap dump (the Byteman rule reads every array exactly instead); the live number of cursors at an instant is not observed; each cluster label ran once and each unit arm in three JVMs, no cluster repeat and no run 2; `GC.class_histogram` is context only. Unit run 1 started before the B3i.9 clarification, which does not touch the unit text.
7. **Core question** — Cursor scratch memory does not follow any cap: its length is set by the number of branching ancestors on the walked path (E) alone, doubling from 48 ints, and is identical at ON_HEAP and OFF_HEAP, at trie sizes from 5 KB to 77 MB, at `memtable_heap_space` 64 / 256 / 512 MiB and with `offheap_objects` [parts 3, 4]. A cap that does bind on the same memory (the trie's allocated bytes: the size threshold at the unit tier, the limit-driven flush at one third of `memtable_heap_space` on the node) moved exactly as its knob while the array did not [part 3]. The array is at most 786 KB per cursor at the 65,535-byte key limit and 12 KB at the cluster's 1000-byte keys, and the accounted size has no term for it [parts 3, 5]. So the constant at `:501` is an initial size, not a cap: the claim holds.

**Conclusion (one line):** unit: B2g row 1 as amended — Confirmed, does not cap; cluster: B3g row 1 as amended — Confirmed, does not cap (flags: the accounting-equal reading is weak; live cursor count not observed; filed Murmur3 workload could not reach the growth, replaced by a ByteOrderedPartitioner comb).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/…/selfcheck.py` re-parsed the raw files without the analysers: for the unit tier it derives L from E by the doubling rule and E from the shape rule (not the analyser's table) and compares `results.csv` with the `RESULT` lines in each `ant.log`; for the cluster tier it re-reads each label's `bt-stats.txt`, `system.log` (flush lines), `cmdline.txt`, `yaml-keys.txt`, `schema.txt` and `session.log` (accounting records). Result: `run1/selfcheck.out`, **204 OK, 0 BAD**. Raw files re-opened by hand: `hb512/first-limit-flushes.txt`, `m3/bt-stats.txt`, `sl/bt-stats.txt`, `acct.log`, `unit/results-T8.csv`.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cmdline.txt` shows `-Xms1G -Xmx1G` and the Byteman agent for all six labels; `yaml-keys.txt` the partitioner, allocation type and spaces; `selfcheck.out` found no `ERROR` in six `system.log` files; `session-noacct.log` shows `nodetool flush` before the comb. |
| 2. Readings | yes | The 29 `Enqueuing flush of ks.t` lines of hb64 (27 limit-driven) and 2 x 28 non-growing cursors agree with `cursors 10729 - grow 10673 = 56`. |
| 3. Matched row | yes | L re-derived from E for 105 unit rows; E re-derived from the shape rule; the six growth counts re-read from `bt-stats.txt`; control ratios 4.00 and 8.00 re-computed from `system.log`. |
| 4. Excluded rows | yes | Each exclusion cites a number that `selfcheck.out` reproduces; no Refuted row applies. |
| 5. Observed vs. inferred | yes | The list is complete; (i) and (ii) are the weakest and are named as bounds and code reading. The `int[]` class histogram of `sl` (no trie cursors) is as large as the trie labels' (16.2 MB), which supports (i). |
| 6. Deviations and gaps | yes | The Murmur3 replacement, the single comb depth and the unobserved live count are recorded; the re-freeze is in §1. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1: array length independent of caps (unit rows, three labels), unaccounted (code + unit sizes), small (bound); refuted-if conditions (length grows with the space limits; counted in `sizeOnHeap()`) were both excluded. |

### 5.2 Run 2?

**No** — decided 2026-10-25. The unit tier is deterministic code read exactly (E and L by reflection, three fresh JVMs agree on every arm), the cluster tier reads every cursor's array through a rule that was checked on a known answer, and the claim is the negative estimate's expected outcome. The weakest points (the accounting-equality reading and the unobserved live cursor count) would not be settled by a second run of the same design.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested:** (B1) The cursor backtrack array's size does not follow any configured cap: it is driven by trie shape and depth alone (at most about 3 ints per branching level, doubling from 48 ints), independent of `memtable_heap_space`, `memtable_offheap_space` and the trie's accounted size, and stays small relative to the trie data. It is refuted if the array length grows with the memtable space limits or is counted in `sizeOnHeap()`. "Confirmed" below means this held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**: B2g row 1 as amended (B2i.7a): E and L equal the exact table in 105 rows, ON_HEAP = OFF_HEAP, independent of filler (trie 5 KB to 77 MB) and of the size threshold (8, 16, 32 MiB), `sizeOnHeap()` unchanged by the cursor, control flags false/false/true | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed**: B3g row 1 as amended (B3i.7a): largest array 3072 ints (12,304 B) in hb64, hb256, hb512 and oo64 alike, six growth counts equal in each, `m3` zero growth, `sl` zero cursors, accounting equal across the scan phase, control moved (first limit flush 21.3 / 85.3 / 170.6 MiB; oo64 off-heap 21.4 MiB). Flags: accounting-equal reading is weak; live cursor count not observed | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control:** a cap that binds on the same memory (trie bytes), with the same instruments: unit, `InMemoryTrie`'s size threshold flips from false (T-1 MiB) to true (T MiB) with `sizeOffHeap()` equal to the allocated position, at three values of T, while L of the comb in the same trie stays 3072; cluster, the first limit-driven flush happens at 21.3 / 85.3 / 170.6 MiB for `memtable_heap_space` 64 / 256 / 512 MiB (one third of the space), while the largest cursor array stays 12,304 B.

**Nuance:** the array does grow, by doubling, with the depth of the walked path (up to 786,432 ints = 3 MB for a split comb at the 65,535-byte key limit, per cursor); "does not cap" says no configured limit bounds or accounts for it. In practice the Murmur3 default produces no growth at all (cursors stay at 48 ints, m3).

**Feedback filed:** the case file's section D "Stage-4 feedback" filled (case file untracked, no commit; sha256 of the file with D filled: `3e7e5f0f6032984398ba58e0d8a21d64b4a2806f004256a3dedfdea59b96fc34`), and the audit amendments B2i, B3i (B3i.9 after the shakedown) dated 2026-10-25; no change to B1, B2f, B2g, B3f, B3g text.

**Other findings:** with ByteOrderedPartitioner a TrieMemtable has one shard and the partition-key trie is as deep as the key; Murmur3 hides the deep-key case. `InMemoryTrie.java:91` citation is the comment, the constructor is :88 (cosmetic).

**Left on the node (`pc07`):** nothing running (no `CassandraDaemon` of this run; ports 7088, 9088, 7288 free). Files: `~/s4-bt/{cassandra,node-tree,driver,helper,check,node1,run1,logs}` (about 0.95 GB: two build trees, logs, class files; node data and commit log removed).

## Time spent (UTC, 2026-10-25; from `timing-batch4.log`)

| Step | Start | End | Minutes | Remarks |
|---|---|---|---|---|
| audit | 17:51:01 | 17:59:30 | 8.5 | Step-0 audit, amendments B2i/B3i, freeze; includes `copy-source.sh` and `ant build-test` (1 min 11 s, started in the background during the audit) |
| harness | 17:59:30 | 18:01:51 | 2.4 | unit test, generator trie, helper class, Byteman rules, instrument check (known answer: 1 cursor, grow 48 and 96 once each) |
| unit-run | 18:01:51 | 18:02:44 | 0.9 | three `ant testsome` runs of about 15 s each; no rerun |
| harness2 | 18:03:21 | 18:17:21 | 14.0 | cluster driver; four short node shakedowns (found defects 6 to 8, B3i.9 and re-freeze); not in the order of the steps: it ran after the unit run |
| cluster-run | 18:17:21 | 18:40:53 | 23.5 | six labels back to back, about 4 min each (filler 104 s, scan phase 90 s, node start 19 s, 61 s for Murmur3); no rerun |
| selfcheck | 18:40:59 | 18:41:12 | 0.2 | script run only; `selfcheck.py` itself was written during the cluster run (counted in cluster-run) |
| report | 18:41:12 | 18:43:14 | 2.0 | results file, excerpts to `run1/`, case file section D |

Total wall time from the start of the audit to the end of the report: **52 minutes** (17:51:01 to 18:43:14). Steps are sequential except that `ant build-test` ran in the background during the audit and `selfcheck.py` was written during the cluster run.
