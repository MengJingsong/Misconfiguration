# partition-key-max-size-descend-data-length--autonomous — stage-4 results  <!-- file: results/partition-key-max-size-descend-data-length--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`partition-key-max-size-descend-data-length--autonomous`](../../stage3-ai-deep-read/cases/partition-key-max-size-descend-data-length--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. "§9a" below means B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `25b4a70`; the case file is **untracked** in the working tree (no commit holds it). **sha256 of the whole file after the audit's amendments (B2i and B3i, dated 2026-10-25): `9d1302196118cf4278e5e3a0dab1fd687585097c7ebcfff9492ead0cf08ab3ec`**, frozen at 2026-10-25 13:54:42 EDT, before the harness existed and before any reading. B2f, B2g, B3f, B3g (with B2i, B3i) are frozen at this hash. Section D (the feedback) is filled afterwards; the file's sha256 with D filled is in section 8. |
| **Harness** | `harness/partition-key-max-size-descend-data-length--autonomous/`: `PkStackTest.java`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md`; written after the freeze; not committed (md5s at the start of the unit run, the start of the cluster run and at the end: `partition-key-max-size-descend-data-length--autonomous/run1/harness.md5.{unit-start,cluster-start,final}`). Between the cluster run and the self-check only `selfcheck.py` was written and edited (it is not in the start lists; it reads raw files only). |
| **Tiers and values** | **Unit (B2):** L in {15, 16, 127, 128, 1024, 16384, 65535, 65536, 65545} bytes, ON_HEAP and OFF_HEAP, apply path versus recursive control, 1M short keys, `row_overhead_size=1` JVM. **Cluster (B3):** K in {32, 100, 127, 128, 200, 1000, 16000, 60000, 65535} bytes at `memtable_heap_space` 64 MiB and 256 MiB, N=5 partitions (N=1 at 60000 and 65535), positive control with 100 KB values at 16 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate: **negative** (the stack is not counted by the allocator). Audited against `cassandra/cassandra-5.0.9/` (clean, `build.xml` `base.version` 5.0.9). Citations re-read: `InMemoryTrie.java:50-100, 540-730, 800-900, 940-985`, `TrieMemtable.java:98, 440-500`, `AbstractShardedMemtable.java:45-75`, `MemtableParams.java:98-215`, `CassandraRelevantProperties.java:350-360, 794-888`, `SkipListMemtable.java:70-80`, `Validation.java:51-55`, `FBUtilities.java:158`, `DecoratedKey.java:105-133`, `Config.java:184-190`, `TableMetrics.java:493`.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-heap `int[]` of the trie's `ApplyState`, bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The key-size limit (65535) and the 128 cutoff are constants (A1); the design varies the key length (a depth proxy) at 6+ values and the aggregate caps (`memtable_heap_space`, `row_overhead_size`) as the knobs that should not matter. Reason stated. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | Unit: `data.length`, `measureDeep`; cluster: `GC.class_histogram` `int[]` total (noisy, other `int[]`s) — B3i.3 adds a K=32 control arm, repeated, to subtract drift. |
| A. Core question | usage driven to the limit and past it | Met | Key length is driven to 65535 and (unit) 65545; the memtable cap is not the thing being driven (the claim is that it does not bind). |
| A. Core question | positive control for a negative estimate | Partly → Met | B2g/B3g controls exist; B3i.5 makes the cluster one exact (16 MiB heap space, MEMTABLE_LIMIT flush read in the log). |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f had a wrong number (L=16 -> 80; true 160) and a loose accounting test; K=200 "1-4 KB" is 5,120 B; B2i.1-2 and B3i.3-4 give exact lengths and thresholds from the doubling rule before any reading. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B2g/B3g rows exist for confirmed, accounted, capped, wrong path, harness error; there is no row for "int[] rises with K but the memtable-size rise matches the stack" other than "refuted", and none for "readings outside every row"; the generic rule (Not confirmed, no matching row) applies. Left for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For a "does not cap" claim: the stack length follows depth (not the cap), the accounted size does not carry it (differential check B2i.2, N=1 contrast B3i.4). |
| B. Logic | alternative explanations and their controls | Met | Recursive overload, short-key arms, two heap-space values, repeated K=32 control. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3 and B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | The inline `memtable = {...}` syntax is not valid in 5.0.9 (B3i.1); accounted-size observable was the wrong metric (B3i.4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | N, the key alphabet, the baseline definition, metric names supplied (B3i.2, B3i.4). Paths `/tmp/c509`, `/tmp/node1` replaced by `~/s4-pk/`. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Build tree, bundled Python driver, `nodetool`, `jcmd`; the unit class and drivers are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Not met → Met | 2000 x 60000 B = 120 MB exceeded a 64 MiB memtable (the "no flush" premise was false); fixed in B3i.2 (N=5, under 0.4 MB per arm). Unit: 1M short keys on a 2 GiB heap. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (2 off) | Verified: `InMemoryTrie.java:577,580,670-671,974-981`, `TrieMemtable.java:98,483,485`, `Validation.java:51-55`, `FBUtilities.java:158`. Corrected: `putRecursive` is :895, the shard count is `AbstractShardedMemtable.java:46,63-65`, not `TrieMemtable:660-662`. Stack lengths quoted in A2 (up to 2.6 MB) hold only at depth above 65535 (K=65535 plus prefix) and are 1.31 MB at K=60000. |

**Side finding (checked in the audit, does not change the claim).** The trie size threshold is read from `cassandra.memtable.row_overhead_size` (`InMemoryTrie.java:63`; range 1..2047 MB, default 2048*10/11 = 1861 MB), a property that `SkipListMemtable.java:75` also reads, as a byte count. `CassandraRelevantProperties.MEMTABLE_TRIE_SIZE_LIMIT` (`cassandra.trie_size_limit_mb`, :358) has no reference anywhere in `src/`, `test/` or `conf/`: the documented-looking knob is unused. The B2 positive control exercises the live property.

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Exact length rule and numbers (B2i.1), add L=65536/65545 | Applied, B2i.1, 2026-10-25 | L=16 prediction was wrong; the 2.6 MB figure needs depth above 65535. |
| 2 | Differential accounting check apply versus recursive (B2i.2) | Applied | Gives the accounting test a number. |
| 3 | Measure D(K) of a database key (B2i.3) | Applied | Needed for B3 numbers. |
| 4 | Valid table syntax (B3i.1) | Applied | Inline options rejected in 5.0.9. |
| 5 | N=5 partitions, K list incl. 127/128/65535, control repeated (B3i.2) | Applied | 120 MB would flush a 64 MiB memtable. |
| 6 | Exact stack numbers and observable (B3i.3, B3i.4) | Applied | `tablestats` shows live data size, not the allocator charge. |
| 7 | Exact positive control (B3i.5) | Applied | Was qualitative. |
| 8 | Extra conclusions rows (int[] rises and memtable-size rises equally -> already Refuted; reading outside every row) | Left for stage 3 | Covered by existing rows and the no-matching-row rule. |

**Agreement criteria** — not applicable (run 2 not planned).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (unit 18:03 UTC, cluster 18:03 to 18:11 UTC) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876...`, 40 cores, 251 GiB), shared with another stage-4 agent (tag `ci`) whose nodes ran on `/dev/shm` at the same time | not done |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12; `ant build-test` once, 1 min 9 s, before any run; no `ant` while a node ran | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-pk/src` by `copy-source.sh`, repository commit `25b4a70` (tag `cassandra-5.0.9`, local baseline) | |
| Case-file commit / harness commit | the case file is untracked (sha256 in section 1); harness uncommitted | |
| Storage for node data | local `/dev/sda3` (63 GB, 47 GB free after): `~/s4-pk/cluster-run1/<label>/{data,commitlog,hints,saved_caches,logs}`; each node under 0.2 GB | |
| Full logs (path, outside the repo) | on `pc12`: `~/s4-pk/unit-run1/`, `~/s4-pk/cluster-run1/{h64,h256,pc}/` (`command.log`, `logs/system.log`, `hist-*.txt`, `arms.csv`); node settings: JDK 11, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G`, G1), `ulimit -n 100000`, one-node ring on 127.0.31.1 (storage 7131, native 9131, JMX 7331), `memtable_allocation_type: heap_buffers`, trie memtable with `shards: 1`, `memtable_heap_space` 64 / 256 / 16 MiB | |

## 3. Runbook defects

The audit found rows 1 to 5 before run 1 and fixed them as amendments (B2i, B3i of 2026-10-25), which is why no step stopped in run 1; they are listed here for stage 3.

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2f | L=16 predicted to leave `data.length` at 80; the rule gives 160 (80 only below 16) | exact rule and table, B2i.1 | 2026-10-25 | untracked file (sha256 in section 1) |
| 2 | audit | B3b | `WITH memtable = {'class': ..., 'shards': '1'}` is not valid in 5.0.9 (`MemtableParams.get` takes a configuration key) | yaml `parameters: {shards: 1}`, B3i.1 | 2026-10-25 | same |
| 3 | audit | B3c | 2000 x 60000 B = 120 MB exceeds `memtable_heap_space: 64MiB`; the "no flush" premise was false | N=5 per arm (and N=1 arms), B3i.2 | 2026-10-25 | same |
| 4 | audit | B3d | `tablestats` "Memtable data size" is the live data size, not the allocator charge | JMX `MemtableOnHeapDataSize`, B3i.4 | 2026-10-25 | same |
| 5 | audit | B3f | K=200 stack "1-4 KB" (true value 5,120 B); K=65535 gives 2.6 MB, K=60000 1.31 MB | exact table, B3i.3 | 2026-10-25 | same |
| 6 | run 1 | analysis | The cluster analyser's heap-space check compared control-subtracted excesses within 10 %; at K=1000 it failed (20,236 versus 17,732 B) because the h256 first control arm read 5,024 B (versus 168 B for its last control and 16 / 168 B on h64), a one-off warm-up of unrelated `int[]`s. The raw deltas are identical (20,328 B on both). The frozen text only says the stack size must not depend on the heap space, which the raw deltas and the flush drops (19,680 B on both) show. No change to the case file; recorded as an instrument-noise limit. | none | 2026-10-25 | n/a |

## 4. Run 1

**Scope:** unit tier, all L, both buffer types, three repeats, the `row_overhead_size=1` JVM, the 1M-key bulk runs, key-depth measurement; cluster tier, nine K values at two `memtable_heap_space` values (64, 256 MiB) plus N=1 arms, and the positive control at 16 MiB. **Command logs:** `partition-key-max-size-descend-data-length--autonomous/run1/unit/command.log`, `partition-key-max-size-descend-data-length--autonomous/run1/cluster/*/command.log.head` (first 6 KB; full logs on the node). The unit tier's quick and full shakedown runs (`~/s4-pk/unit-shake*`) and the cluster quick runs (`~/s4-pk/cl-shake`) checked the instruments before this run and showed the same numbers, so run 1's numbers are not independent of what the author had already seen (the predictions were frozen before any of them; see 4.2 part 6).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, from `analyze_unit.py`, 19 checks PASS, 0 FAIL)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `data.length` after one L-byte key, apply path, ON_HEAP and OFF_HEAP, 3 repeats | L=15 80; 16 160; 127 640; 128 1280; 1024 10240; 16384 163840; 65535 327680; 65536 655360; 65545 655360. Equal to the `80*2^k` rule in all 54 rows | `unit/lengths.tsv`, `unit/summary.txt` |
| recursive control `data.length` | 80 in all 54 rows, status ok (no stack overflow at 1 GiB thread stack, up to L=65545) | `unit/lengths.tsv` |
| `sizeOnHeap` delta, apply versus recursive, ON_HEAP | identical at every L (36, 36, 164, 164, 1252, 18948, 75172, 75172, 75172 B): the stack growth (0 to 2,621,120 B) adds 0 to the accounted size | `unit/lengths.tsv` |
| `ObjectSizes.measureDeep(trie)`, apply minus recursive | equals `4*(len-80)` exactly (L=65535: 1,310,400 B; L=65536: 2,621,120 B) | `unit/lengths.tsv` |
| `-Dcassandra.memtable.row_overhead_size=1`, L in {16, 1024, 65535} | same `data.length` as the default JVM | `unit/lengths-ro1.tsv` |
| 1M random 16-byte keys, fresh trie | `data.length` 80 -> 160 (first key) and unchanged by the other 999,999; `sizeOnHeap` 632 -> 74,954,200 B | `unit/bulk-default.tsv` |
| same after a 65535-byte key | `data.length` 327,680 before and after; `sizeOnHeap` 75,804 -> 75,029,116 B | `unit/bulk-default.tsv` |
| positive control: threshold flip | `reachedAllocatedSizeThreshold()` false -> true with `row_overhead_size=1` (74.95 MB allocated, 1 MB threshold), false with the default (1861 MB) | `unit/bulk-ro1.tsv`, `unit/bulk-default.tsv` |
| DecoratedKey depth | `D(K) = K + 12` bytes for K from 32 to 65535 | `unit/depth.tsv` |
| side finding, extra run | `-Dcassandra.trie_size_limit_mb=1`: threshold stays false at 74.95 MB allocated, so the property has no effect | `unit/bulk-trie_size_limit_mb1.tsv` |

**Cluster tier** — for each K: `int[]` delta = bytes of `[I` in `GC.class_histogram` (full GC) after the writes minus before; "excess" subtracts the mean of the two K=32 control arms of that node; "memtable" is the delta of `MemtableOnHeapDataSize`; "flush drop" is the `int[]` fall at the explicit flush (`run1/cluster/<label>/arms.csv`, `hist-*.txt`; `h64` / `h256` = `memtable_heap_space` 64 / 256 MiB).

| K (N) | Predicted stack (B3i.3) | int[] delta h64 | excess h64 | int[] delta h256 | memtable delta (both) | flush drop h64 / h256 |
|---|---|---|---|---|---|---|
| 32 (5), first / last control | 320 B | 16 / 168 | n/a | 5,024 / 168 | 2,136 | n/a |
| 100, 127 | 320 B | 168 | 76 | 168 | 2,456 / 2,648 | n/a |
| 128 | 5,120 B | 4,912 | 4,820 (pred 4,800) | 4,952 | 2,648 | 4,320 / 4,320 |
| 200 | 5,120 B | 4,968 | 4,876 (pred 4,800) | 4,968 | 3,128 | 4,320 / 4,320 |
| 1000 | 20,480 B | 20,328 | 20,236 (pred 20,160) | 20,328 | 7,832 | 19,680 / 19,680 |
| 16000 | 327,680 B | 327,488 | 327,396 (pred 327,360) | 327,528 | 93,560 | 326,880 / 326,880 |
| 60000 (5) | 1,310,720 B | 1,310,528 | 1,310,436 (pred 1,310,400) | 1,310,528 | 345,176 | 1,309,920 / 1,309,920 |
| 60000 (1) | 1,310,720 B | 1,310,408 | 1,310,316 | 1,310,408 | 69,208 | 1,309,920 / 1,309,920 |
| 65535 (5) | 2,621,440 B | 2,621,248 | 2,621,156 (pred 2,621,120) | 2,621,248 | 376,664 | 2,620,640 / 2,620,640 |
| 65535 (1) | 2,621,440 B | 2,621,128 | 2,621,036 | 2,621,128 | 75,512 | 2,620,640 / 2,620,640 |

Other cluster readings: no memtable flush was logged before the explicit one in any arm (`system.log.flush-lines` shows only `USER_FORCED`), no `ERROR` in either `system.log`; the `InMemoryTrie$ApplyState` instance count in the histogram rose by one per table. The analyser reported FAIL for one of its checks (heap-space equality at K=1000, section 3 row 6) and PASS for all others (`run1/cluster/summary.txt`).

**Positive control (cluster)** (`run1/cluster/pc/`): K=32 keys, 100 KB values, `memtable_heap_space` and `memtable_offheap_space` 16 MiB: `MemtableOnHeapDataSize` rose 1.03 MB per 10 writes (5,141,576 B at 50 writes); at write 60 the log shows `Enqueuing flush of ks.pc, Reason: MEMTABLE_LIMIT, Usage: 5.394MiB (34%) on-heap`; `int[]` bytes before and after: 15,923,920 and 15,929,960 (+6,040 B, the size of the controls' noise).

### 4.2 Conclusion and logic

1. **Validity.** The key depth reached the claim's maximum: L and K were driven to 65535 (unit also 65545); a database key of 65535 bytes has depth 65547, above 65536, so the stack doubles once more [observed: `unit/depth.tsv`, `cluster/h64/arms.csv`]. Fixed settings held: `heap_buffers`, `shards: 1` (one `ApplyState` per table), `-Xmx2G`, same JVM flags in all runs [observed: `cluster/*/java.cmdline`, `cluster/h64/command.log.head`]; fresh table per arm; full GC forced by the histogram before every read [observed: `hist-*.txt`]; short-key controls at K=32 / 100 / 127 (recursive path) and the recursive twin in the unit tier [observed: `unit/lengths.tsv`]. No flush happened before the explicit one in any arm [observed: `system.log.flush-lines`]. Valid.
2. **Readings.** One outlier: the first K=32 control on `h256` read 5,024 B (others 16 to 168 B). It widens the h256 control spread, so the tolerance of the small-K rows on that node is wider, and it breaks the analyser's own 10 % comparison of excesses at K=1000; raw deltas and flush drops are identical between the two nodes (section 3, row 6) [observed: `cluster/h256/arms.csv`, `cluster/summary.txt`].
3. **Matched row.** Unit B2g row 1: "`data.length` grows with L, `sizeOnHeap` has no matching term, threshold knob has no effect -> Claim confirmed". `data.length` follows the depth exactly (80 -> 327,680 -> 655,360 ints) [observed: `unit/lengths.tsv`]; `sizeOnHeap` of the apply path equals the recursive path's at every L, so the accounted term for the stack is 0 B, while `measureDeep` shows the stack is held (+1,310,400 B at L=65535) [observed: same file]; `row_overhead_size=1` leaves every length unchanged [observed: `unit/lengths-ro1.tsv`]. Cluster B3g row 1: "`int[]` total rises with K above 128 by about the predicted 20-40 B x K; memtable size shows no matching rise; same for both heap-space values -> Claim confirmed": the `int[]` step is 4,912 / 4,968 / 20,328 / 327,488 / 1,310,528 / 2,621,248 B at K=128 / 200 / 1000 / 16000 / 60000 / 65535, within 1 % of `4*len-320` for K>=1000 [observed: `arms.csv`]; the memtable charge for one 65535-byte partition is 75,512 B against a 2,621,128 B step, and between 1 and 5 partitions the step is the same while the charge scales [observed: `arms.csv`]; 64 and 256 MiB give the same raw steps [observed: `arms.csv` of both]. The stack disappears with the discarded memtable (flush drop within 1 % of the step) [observed: `arms.csv`].
4. **Excluded rows.** Unit "`sizeOnHeap` delta includes about 4*(newLen-oldLen) -> Refuted": the apply and recursive deltas are equal [observed]. "`data.length` shrinks or is capped below 5*L -> Refuted": the length equals the rule and is never below 5*L [observed]. "stays 80 at L=65535 -> wrong path": 327,680 [observed]. "Recursive control not 80 -> harness error": 80 in all rows [observed]. Cluster "Memtable size rises by the same amount -> Refuted": 75,512 B versus 2,621,128 B at N=1 [observed]. "`int[]` flat at large K -> Not confirmed": it steps [observed]. "Stack size differs between 64 and 256 MiB -> Refuted": the raw steps are equal [observed].
5. **Observed vs. inferred.** [inferred: the `int[]` step in the cluster histogram is `ApplyState.data`.] The cluster tier reads only the total of all `int[]`; the identification rests on the unit tier, where the same key sizes give exactly this array length, on the match of the step to `4*len-320` at nine K values, on the step being independent of N and of the heap space, and on its disappearing at the flush. No heap dump of `ApplyState` was taken. [inferred: "does not cap" for any cap value.] The caps tested were `memtable_heap_space` 64 / 256 MiB (16 MiB in the control) with one shard; the stack is at most 2.6 MB per shard against a 64 MiB cap, so the cap was never near binding because of the stack. With the default shard count (40 on this node) the unaccounted total would be up to 40 times larger; that was not run. [inferred: the positive control shows that the accounted structures bind.] The 16 MiB node flushed by `MEMTABLE_LIMIT` at an on-heap charge of 5.39 MiB while the `int[]` total moved 6 KB [observed: `cluster/pc/`], and in the unit tier `reachedAllocatedSizeThreshold()` flipped for a trie whose stack did not move [observed: `unit/bulk-ro1.tsv`].
6. **Deviations and gaps.** (a) The shakedowns (a quick and a full unit run, two quick cluster runs) showed the same numbers before run 1, so run 1 is a repeat of a design whose outcome the author had seen; the predictions were frozen first, and the analysers were not edited afterwards except the fresh-trie `data.length` check (expect 160 after the first key, per B2i.1; before it the check wrongly expected 80). (b) `memtable_offheap_space` was left unset in the arm nodes (B3a says 0 MiB). (c) One cluster analyser check failed because of control noise (section 3, row 6). (d) The default shard count and a heap dump were not run. (e) K=128 / 200 on `h256` pass the 25 % tolerance only because the inflated control spread widens it; their raw steps (4,952 / 4,968 B) match the prediction.
7. **Core question.** The constraint named by the claim (the memtable caps `memtable_heap_space` / `memtable_offheap_space` and the trie size threshold) does not bound `ApplyState.data`: its size follows the key depth by a fixed doubling rule (part 3), is charged to neither `sizeOnHeap()` nor `MemtableOnHeapDataSize` (part 3: equal deltas in the unit tier, N=1 contrast in the cluster tier), and is unchanged by the cap values and by `row_overhead_size` (part 3), while the same instruments see the caps bind on accounted data (positive control, part 5). The amount is small (at most 2.6 MB per shard) but unaccounted.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 — confirmed (the claim: usage does not follow the memtable cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/partition-key-max-size-descend-data-length--autonomous/selfcheck.py` re-parses the raw files (`lengths.tsv` with a closed-form formula instead of the analyser's loop; `hist-*-pre/post.txt`; the JMX values in `command.log`; `system.log`), not the CSVs; output `run1/selfcheck.out`: 44 parts hold, 1 does not (the control-subtracted heap-space comparison at K=1000, section 3 row 6).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: only `USER_FORCED` flushes (12 per node), no `ERROR`, `-Xmx2G` in both `java.cmdline`; the key list reached 65535; no node of the run left. |
| 2. Readings | yes | The 5,024 B control on `h256` is in `hist-c32-first-*.txt`; raw deltas equal on both nodes. |
| 3. Matched row | yes | Raw `[I` deltas recomputed from the histogram files (4,912 ... 2,621,248 B); memtable deltas recomputed from `command.log` (75,512 B at K=65535 N=1); unit equal-accounting and `measureDeep` gaps recomputed. |
| 4. Excluded rows | yes | Same files; the only part that does not hold is the analyser's 10 % comparison of excesses at K=1000; the raw comparison, which is the claim's wording, holds. |
| 5. Observed vs. inferred | yes | The inferred identification of the `int[]` step is supported by agreement at nine K values on two nodes; the raw files hold nothing stronger. |
| 6. Deviations and gaps | yes | Listed in 4.2 part 6; the author had seen shakedown numbers. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's three statements (grows with depth, not charged, independent of the knobs) map to the three clauses of part 7; the positive control answers whether the workload could have shown a cap. |

### 5.2 Run 2?

**No** (2026-10-25). Both tiers agree, the measured values match the doubling rule to under 1 %, and the one inferred statement (that the `int[]` step is the stack) is backed by the unit tier. A run 2 would add little beyond the gaps listed (default shard count, heap dump).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested:** (B1) memory held by `InMemoryTrie.ApplyState.data` is not bounded by, nor charged to, the memtable cap; it grows with the maximum key depth (about 20 B per depth level, doubled) regardless of those knobs; `sizeOnHeap()` stays flat while the real retained size grows after a long-key write. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1, Confirmed | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | B3g row 1, Confirmed | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control:** unit: 1M short keys raised `sizeOnHeap` from 632 B to 74.95 MB and flipped `reachedAllocatedSizeThreshold()` to true at `row_overhead_size=1`, with `data.length` unmoved (`unit/bulk-ro1.tsv`); cluster: 100 KB values at `memtable_heap_space` 16 MiB were flushed by `MEMTABLE_LIMIT` at 5.39 MiB on-heap while the `int[]` total moved 6 KB (`cluster/pc/`). Both show the instruments see a cap that binds on accounted data.

**Side finding (audit, plus a run-time check):** the trie size threshold is read from `cassandra.memtable.row_overhead_size`; `cassandra.trie_size_limit_mb` (`MEMTABLE_TRIE_SIZE_LIMIT`) is unused (no reference in `src/`, `test/`, `conf/`; setting it to 1 left the threshold false at 74.95 MB allocated, `unit/bulk-trie_size_limit_mb1.tsv`).

**Feedback filed:** the case file's section D (sha256 of the file with D filled: `217420ecd5fa0fceddf35dcada075f040b588025670c280e9adb863ea6aab3ac`; the frozen version of section 1 is `9d1302196118cf4278e5e3a0dab1fd687585097c7ebcfff9492ead0cf08ab3ec`) and the amendments B2i and B3i; nothing else amended. `_INDEX.md` and the CSVs were not touched (instructed).

## 9. Leftovers and time spent

**Leftovers on `pc12`:** no process of this run (`ps` shows no `CassandraDaemon` or `PkStackTest` with `s4-pk`); files under `~/s4-pk/` (505 MB: `src`, `unit-shake*`, `unit-run1`, `cl-shake`, `cluster-run1`, `logs`); nothing under `/tmp`; no `iptables` change; the repository's `cassandra/cassandra-5.0.9/` untouched.

**Time spent** (UTC, from `/proj/misconfiguration-PG0/git-repos/timing-batch4.log`):

| Step | Start | End | Minutes | Remarks |
|---|---|---|---|---|
| audit | 17:51:02 | 17:54:45 | 3.7 | amendments, freeze, results skeleton; `copy-source.sh` and `ant build-test` (1 min 9 s) ran in the background during it |
| harness | 17:54:45 | 18:03:06 | 8.4 | unit class and analyser, cluster driver and analyser, two unit shakedowns, two cluster shakedowns (the first cluster one failed on the driver zip path and was rerun) |
| unit-run | 18:03:14 | 18:03:24 | 0.2 | the full unit run takes 9 s |
| cluster-run | 18:03:31 | 18:11:47 | 8.3 | three node starts in sequence (about 3, 3 and 1.5 min); `selfcheck.py` was written while the nodes ran |
| selfcheck | 18:12:07 | 18:12:29 | 0.4 | run of `selfcheck.py`, copy of excerpts, one extra unit run for the side finding |
| report | 18:13 | 18:15:17 | 2.3 | results file and case-file section D |
