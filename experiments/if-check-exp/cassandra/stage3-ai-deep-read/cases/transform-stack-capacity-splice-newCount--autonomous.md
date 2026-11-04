# Transformation-stack capacity (no configured constraint) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/transform/Stack.java:94` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not exposed), 2026-10-25 |
| Estimate | `negative`: line 94 is a grow-if-needed array capacity check (`newCount > keep.length`), not a limit; there is no configuration entry, property or constant behind it. |
| Ground | The "limit" is the current length of an internal array that is grown on demand with no ceiling. Its size is set by how many `Transformation`/`MoreContents` objects the read path stacks on one iterator (a code-fixed handful, plus a few per short-read extension), and each entry is a pointer in a per-iterator array. It is not a memory- or disk-significant object and no operator knob caps it. |

## A. Constraint trace

**A1. The constraint.** There is no named constraint. The compared value `keep.length` is the capacity of the `Transformation[]` (`Stack.stack`, line 31) or `MoreContentsHolder[]` (`Stack.moreContents`, line 33) array. The initial capacity is zero (`EMPTY_TRANSFORMATIONS`/`EMPTY_MORE_CONTENTS_HOLDERS`, lines 27-28, 49-50). Kind: internal data-structure capacity (neither configuration, property nor constant). Declared at `Stack.java:27-33`. Unit: array elements. "Default": 0, then 5 on the first `resize` (line 75), then doubling. Settable: not settable, and no restart applies (it is code).

**A2. What it caps.** Nothing. `splice` (lines 90-101) computes `newCount = prefixCount + keepCount` (line 93), the number of entries needed after a refill. If that exceeds the current capacity, line 94-95 reallocates a larger array with `Arrays.copyOf(keep, newCount)`. The check protects against `ArrayIndexOutOfBounds`/truncation, not against use. The resource touched is on-heap pointer arrays (8 bytes or 4 bytes with compressed oops, per entry).

**A3. Mechanism.**
1. `Transformation.apply(...)` / `Transformation.add` (`Transformation.java:195-206`) call `Stack.add(Transformation)` (`Stack.java:60-65`). When `length == stack.length` it calls `resize` (line 73-77), which gives capacity 5, then doubles.
2. `Stack.add(MoreContents)` (lines 67-71) grows `moreContents` by exactly one each time (`Arrays.copyOf(..., length+1)`).
3. When a `MoreContents` yields new contents, `BaseIterator.tryGetMoreContents` (`BaseIterator.java:136-169`) calls `refill(prefix, holder, i)` (`Stack.java:80-88`), which calls `splice` twice (lines 84-85). `splice` at line 94 grows `keep` only if `prefixCount + keepCount` exceeds its length. Outcomes: when `newCount <= keep.length` the arrays are reused and shifted in place via `System.arraycopy` (line 97); when `newCount > keep.length` a larger array is allocated and the old one is garbage. There is no rejection or failure outcome at the boundary.
4. Producers of MoreContents: `ShortReadProtection.java:74-76` (range reads, `MorePartitions.extend`) and `ShortReadPartitionsProtection`; plus `RepairedDataInfo.java:278`, `UnfilteredRowIterators.java:252`, `UnfilteredPartitionIterators.java:108`, `PartitionIterators.java:68`, `RTBoundCloser.java:91`.
Bypass/overshoot: none to speak of. Growth is bounded only by the number of transformations the code stacks, which is structural (a fixed number of `Transformation.apply` calls in the read/compaction pipeline, e.g. `ShortReadProtection.java:77-78`), not data-dependent. A refill replaces the prior suffix, so the stack does not grow once per partition.

**A4. Other consumers.** The arrays are tiny compared with the data the iterators produce (rows, cells, buffers, off-heap `ByteBuffer`s). Those are governed by other limits (e.g. paging, `-Xmx`, `max_value_size`), which are outside this line.

**A5. Evidence beyond the source.** none.

## B. Verification solution

**B1. Claim under test.** The size of the `Stack` arrays (`stack.length`, `moreContents.length`) and the number of `splice` reallocations at line 94 are determined only by the number of stacked transformations / refills and are not capped by, nor scale with, any configuration limit; and process memory/disk use under a read workload does not follow `Stack` capacity (it follows data volume). It would be refuted if the capacity was seen to be bounded at a fixed value regardless of inputs, or if heap use tracked stack length.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/tmp/c509/`), `cd /local/tmp/c509 && ant jar` (never build in the shared tree). Put the test in package `org.apache.cassandra.db.transform` (e.g. `test/unit/org/apache/cassandra/db/transform/StackSpliceCapacityTest.java`, in the local copy only) so the package-private `Stack` fields `stack`, `length`, `moreContents` are readable. Run: `ant testsome -Dtest.name=org.apache.cassandra.db.transform.StackSpliceCapacityTest`, JVM option `-Xmx512m`.

**B2b. Knobs.** (i) K = number of `Transformation`s applied before the extension (0, 3, 5, 6, 40); (ii) P = number of transformations in the prefix iterator supplied by `moreContents()` (0, 1, 5, 40); (iii) R = number of consecutive refills (1, 10, 1000). These are chosen to straddle the first capacity 5 (line 75) and doubling points (5, 10, 20, 40, 80). Set directly in the test code.

**B2c. Workload.** Build a `BasePartitions`/`UnfilteredPartitionIterator` over an in-memory list of few partitions (e.g. via `UnfilteredPartitionIterators` wrappers over `EmptyIterators`/simple test iterators from `test/unit`), apply K no-op `Transformation`s with `Transformation.apply`, attach a `MorePartitions.extend` provider returning an iterator that itself carries P transformations, then drain it so `tryGetMoreContents` runs `refill` R times. Arithmetic: `splice` line 94 triggers a copy iff `P + (length - holder.length) > current capacity`; e.g. K=5 (capacity exactly 5), holder.length=0, P=6 gives `newCount=11 > 5`.

**B2d. Observables and instruments.** After each refill read, by reflection or same-package access: `it.stack.length`, `it.length`, `it.moreContents.length`; count line-94 hits with a counting wrapper test via `System.identityHashCode(stack)` before and after (a changed identity means reallocation). Heap: `Runtime.totalMemory()-freeMemory()` after `System.gc()` before and after, only coarse; cannot observe line-94 branch directly without a debugger/coverage (alternatively JaCoCo or a temporary log line in the local copy).

**B2e. Procedure.** 1. Build (B2a). 2. For each (K, P, R) triple construct the iterator, record initial `stack.length`, `length`. 3. Drain, recording after each refill the three values and the identity of `stack`. 4. Repeat with K=40, R=1000 and record the maximum `stack.length`. 5. Write results as CSV in `/local/tmp/out/`.

**B2f. Predictions (before any run).**
- K=0, P=0: `stack.length` stays 0, no reallocation.
- K=3: capacity 5 after adds; P=1: `newCount` small, array identity unchanged (line 94 false).
- K=5, P=6: `stack.length` becomes `newCount` (11 minus any dropped prefix), identity changes (line 94 true).
- R=1000 with a P-entry prefix: `stack.length` plateaus (does not grow linearly with R), since each refill replaces the suffix. Max `stack.length` is roughly max(K, P) + small, with no ceiling imposed at any value.
- Increasing K or P to 40 gives capacity of at least 40 with no failure; no configuration value changes any of this.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `stack.length` grows only to about max(K, P)+small, reallocations only when `newCount > capacity`, no upper bound hit | Claim confirmed: line 94 is an on-demand growth check, not a cap |
| `stack.length` increases linearly with R | Claim refuted in the sense that stack growth is data-dependent; investigate leak per refill |
| A fixed maximum is observed independent of K, P | Claim refuted: some implicit ceiling exists |
| Heap delta tracks `stack.length` materially (more than pointer-array size, K*8 bytes) | Claim refuted for memory significance |
| Positive control (B2h) moves heap while `stack.length` stays flat | Confirms usage follows data, not stack capacity |
| Limit never reached / control did not move | Not confirmed; rerun with larger sizes |

**B2h. Controls.** Positive control: the same iterator pipeline over N rows with N = 1e5 vs 1e6 (each row a fresh `BufferCell` with a 1 KiB value) holding a list of materialized rows: heap should rise about 100 MiB to 1 GiB-scale proportional to N (bound by a cap known to bind: `-Xmx512m` produces `OutOfMemoryError` at the larger N) while `stack.length` stays constant. Another control: a run with the line-94 branch never taken (K=3, P=1) versus taken, to show the same heap outcome.

**B2i. Audit amendments to B2 (2026-10-25, stage-4 step 0; made before any reading).**

1. *Arithmetic fixed (B2c, B2f).* `splice` computes `newCount = prefixCount + (keepTo - keepFrom)`. For the stack array `keepFrom = holder.length` (the number K of transformations applied before the extension) and `keepTo = length` (K + M, where M is the number applied after it), so `newCount = P + M`, not `P + K`. The filed example "K=5, P=6 gives newCount 11" is wrong; with M = 0 it gives 6. Define cap(n) = 0 for n = 0, else the smallest 5 * 2^j >= n (the `add` growth, lines 62-63 and 73-77). `splice` grows to exactly `newCount` (line 95), not to a power of two. After the first refill `holder.length = P` (line 87), so every later refill again has `newCount = P + M`: growth cannot repeat with R.
2. *Knobs (B2b).* K in {0, 1, 3, 5, 6, 10, 11, 20, 21, 40, 41, 1000, 100000} (M = 0) for the build-up arm; refill grid (K, M, P, Q) in {(5,0,6,0), (3,0,1,0), (5,0,5,0), (0,5,6,0), (0,5,0,0), (40,0,41,0), (1000,0,100000,0), (5,0,6,1), (0,0,0,1)} with R in {1, 10, 1000} each. Q is the number of `MoreContents` attached to the replacement iterator (0 or 1; it makes `prefix.moreContents.length` non-zero and so exercises the second `splice` call, line 84). One shared no-op `Transformation` instance is added K times, so memory arms measure the array only.
3. *Environment (B2a).* The class is `org.apache.cassandra.db.transform.StackSpliceCapacityTest` (name must end in `Test`). `ant testsome` forks a 1 GiB JVM and `maxmemory` overrides `-Xmx`, so the test is run with `java -Xmx512m` and `org.junit.runner.JUnitCore` on the `ant build-test` classpath (the build tree is never one a node runs from). Paths `/local/tmp` do not exist here: the tree is `~/s4-st/cassandra`, output `~/s4-st/out`.
4. *Direct evidence of the check (B2d).* The test counts reallocations by array identity (`stack` and `moreContents` before and after each refill) and counts refills. The same JVM is run once more with a Byteman agent whose rules count entries at `Stack.java:94` (every `splice` call) and at `Stack.java:95` (calls that grow); the totals must equal 2 x (refills) and (identity changes). That cross-checks the instrument and shows the check was reached.
5. *Heap observable (B2d).* Retained heap = `MemoryMXBean` heap used after three `System.gc()` calls. Reference size is measured with a control `Object[]` of the same length.
6. *Numeric predictions (replace B2f; frozen).*
   - U1 build-up: after K adds with no refill, `stack.length == cap(K)` for every K listed, exactly.
   - U2 refill: after R refills, `stack.length == P + M` if `P + M > cap(K + M)`, else `cap(K + M)`; the number of distinct `stack` arrays seen after the first refill is 1 if `P + M > cap(K + M)`, else 0, for each R in {1, 10, 1000}; `moreContents.length == 1 + Q` after each refill count; its identity changes are Q. In particular (K,M,P) = (5,0,6) goes 5 to 6 with one change, (3,0,1) stays 5 with none, (5,0,5) stays 5 with none, (0,5,6) goes 5 to 11, (40,0,41) goes 40 to 41, (1000,0,100000) goes 1280 to exactly 100000 (not a power of two) with no failure.
   - U3 R-independence: `stack.length` at R = 1000 equals that at R = 1 for every row of the grid.
   - U4 memory: for K = 1,000,000 (cap 1,310,720) the retained-heap delta of the iterator lies within [0.8, 1.25] x the delta of an `Object[1310720]`; i.e. heap tracks only the pointer array.
   - U5 positive control: holding N rows of 1 KiB cells, N in {20000, 80000, 160000}, through the same pipeline (K = 5, M = 0, P = 6, R = 1), retained heap delta lies in [0.9, 2.0] x N x 1024 B, increasing with N, while `stack.length` is 6 in all three; `ctl_cap` (hold rows until `OutOfMemoryError` at `-Xmx512m`) holds between 200 and 512 MiB of rows with `stack.length` still 5 (the source is never exhausted, so no refill runs; corrected 2026-10-25 before any reading).
7. *Conclusion rows added (B2g).* (a) U1-U3 hold exactly and U4, U5 hold: **Confirmed** (the claim, "does not cap"): the grow branch fired (identity changed where predicted) with no ceiling and no failure, up to 100000 entries. (b) A U1-U3 value differs from its closed form but is still R-independent and unbounded: **Not confirmed** (the model of the code was wrong; the arithmetic in item 1 is the audit's, not the claim's). (c) `stack.length` grows with R, or reaches a fixed maximum independent of K and P: **Refuted**. (d) U4 outside its interval with the delta much larger than the array: **Refuted** for memory significance; U4 much smaller than the array (dead code removal by the JIT is the only way): **Not confirmed**. (e) The positive control (U5 or `ctl_cap`) does not move or does not reach OOM: **Not confirmed**, never Confirmed. (f) Byteman totals disagree with the test's counts: instrument invalid, **Invalid**.
8. *Citations.* `Stack.java`, `BaseIterator.java:136-169` and `Transformation.java:195-206` re-read in the pinned source: line numbers hold (`BaseIterator.tryGetMoreContents` is lines 136-171; `refill` call at 163).

### B3. Cluster tier

n/a as filed (superseded by B3i, 2026-10-25: a cluster arm without a knob is run): there is no configuration knob that sets or limits this array, so a cluster cannot push "the configuration to the boundary". Alternative that answers the same question: run a single node and check that real resource use does not follow stack capacity.

**B3a (alternative). Environment.** One node, JDK 11, local copy built with `ant jar`; data, commitlog, hints under `/local/tmp/node1/` on local disk of known size (>= 10 GiB free); `-Xms1g -Xmx1g`; default `cassandra.yaml` otherwise, with `num_tokens: 1`.

**B3b. Knobs.** Query shape only: range scans without partition key (so `ShortReadProtection.java:74-76` registers `MorePartitions.extend`), with `LIMIT` 10, 1000, 100000 and `PAGE SIZE` via cqlsh `PAGING`. Control knob: `key_cache_size` (a binding cap on heap) at 0 vs 100MiB.

**B3c. Workload.** `cassandra-stress write n=2000000` (about 1 KiB rows), `nodetool flush`, then `cassandra-stress read`/cqlsh range scans `SELECT * FROM keyspace1.standard1 LIMIT <L>` with CL=ALL on 1 node only so short reads can occur (use RF=1, so short-read protection may not retry; use a 2-node RF=2 setup with one node holding stale data if short reads must be forced). Duration: 10 minutes per L.

**B3d. Observables and instruments.** `jcmd <pid> GC.class_histogram` every 30 s, watching `[Lorg.apache.cassandra.db.transform.Transformation;` and `[Lorg.apache.cassandra.db.transform.Stack$MoreContentsHolder;` instance counts and bytes; `jstat -gc`; `nodetool info` heap; `du -s /local/tmp/node1`. Cannot observe per-iterator stack length directly.

**B3e. Procedure.** 1. Build and start the node. 2. Load data. 3. For each L, run the scans while sampling histograms. 4. Repeat with `key_cache_size` change and a read workload that hits the key cache. 5. Stop the node (`nodetool drain`; kill the process), verify with `pgrep -f CassandraDaemon`, `rm -rf /local/tmp/node1`.

**B3f. Predictions.** Total bytes of `Transformation[]` plus `MoreContentsHolder[]` stay under about 1 MiB at all L (few live iterators times tens of bytes) and are independent of L; heap used and GC pressure scale with L and row size, not with these arrays. Changing `key_cache_size` changes heap by roughly the configured amount once filled.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Array bytes flat and negligible while heap/GC grows with L | Claim confirmed |
| Array bytes grow with L or dominate the histogram | Claim refuted |
| Heap flat in the positive control (`key_cache_size`) | Control did not move; result not confirmed |
| Heap moves with `key_cache_size` and arrays stay flat | Claim confirmed with a working positive control |
| Short reads never occurred (no `ShortReadPartitionsProtection` log/metric increase, check `nodetool tablestats` / `ReadRepair` metrics) | Limit path not reached; not confirmed |

**B3h. Controls.** Same scans with `LIMIT` 10 as baseline; the `key_cache_size` positive control; a pre-load histogram baseline; GC forced (`jcmd GC.run`) before each sample to remove garbage from reallocated arrays.

**B3i. Audit amendments to B3 (2026-10-25, stage-4 step 0; made before any reading).**

1. *Decision: a meaningful cluster arm exists, but not the one filed.* There is no knob, so a dose-response is impossible, and the claim cannot be pushed to a boundary. What a node can still show is (a) that real read traffic, including forced short reads, reaches `Stack.splice`, (b) how often the grow branch (line 95) fires there, (c) that the live bytes of the `Transformation[]` and `MoreContentsHolder[]` arrays are negligible next to the heap, and independent of the read size, while the heap follows the data volume. The source shows the grow branch is probably **unreachable** on a node: in `BaseIterator.tryGetMoreContents` the prefix is non-empty only when the new contents is itself a `BaseIterator` (lines 149-158), but `ShortReadPartitionsProtection.executeReadCommand` (lines 179-198) returns `ReadResponse.makeIterator`, a deserialised `AbstractUnfilteredPartitionIterator` (`UnfilteredPartitionIterators.java:350`), and `RepairedDataInfo`/`RTBoundCloser` refills return plain iterators; with `prefix = EMPTY`, `newCount = M <= length <= capacity`. The cluster tier therefore cannot drive the check "to its limit"; it records how often the check is reached and that its true branch does not fire. That is stated, not forced.
2. *Setup (replaces B3a-B3c).* Two nodes on one host, loopback addresses 127.54.0.1 and 127.54.0.2 (storage 7054, native 9054, JMX 7154 and 7155, Byteman 9154 and 9155), JDK 11, `-Xmx1G`, `ant jar` tree copy per node run, data on the local disk under `~/s4-st/node1` and `node2`, `hinted_handoff_enabled: false`, `num_tokens: 1`. Table `st.t (id int PRIMARY KEY, v blob) WITH read_repair = 'NONE'`, RF = 2 (SimpleStrategy), 80,000 rows of 1 KiB written at CL ALL; then node 2 is stopped, every even `id` is deleted at CL ONE through node 1 (40,000 live rows remain on node 1, 80,000 on node 2), node 2 restarted. Reads: `SELECT * FROM st.t LIMIT L` at CL ALL through node 1, one page (fetch size L + 1), L in {10, 2000, 40000}, repeated in a loop for 40 s per L. Because node 2 still holds the deleted rows, node 1's merged result is short and `ShortReadPartitionsProtection` fetches more (log line "Requesting N extra rows ... for short read protection").
3. *Instruments (B3d).* Byteman on node 1 and node 2: rules at `Stack.java:94` (every `splice` call, logs `newCount`, `keep.length`), `Stack.java:95` (grow branch) and at the entry of `ShortReadPartitionsProtection.moreContents`; `jcmd <pid> GC.class_histogram` (live objects after a full GC) every 2 s for the byte totals of `[Lorg.apache.cassandra.db.transform.Transformation;`, `[Lorg.apache.cassandra.db.transform.Stack$MoreContentsHolder;`, `Stack$MoreContentsHolder` and the histogram's total; `RssAnon`.
4. *Positive control (replaces the `key_cache_size` restart).* On node 1, point reads `SELECT v FROM st.t WHERE id = ?` over all 80,000 ids at CL ALL, twice, with `nodetool setcachecapacity 0 0 0` (key cache off) and then `64 0 0`: the live bytes of `org.apache.cassandra.cache.KeyCacheKey` and `nodetool info` key-cache entries move from zero to a positive value (a cap known to bind on the same heap resource), measured with the same sampler.
5. *Numeric predictions (replace B3f; frozen).* C1: the splice-entry count S is at least 1 in every L arm, and the short-read rule counts at least 1 for L in {2000, 40000} (the check is reached on a node). C2: the grow-branch count G is 0 for all L (probably unreachable, item 1); G above 0 is recorded as a finding and does not by itself refute the claim. C3: in every sample the live bytes of the three array classes total under 1 MiB and under 0.5% of the histogram total. C4: the maximum histogram total over the L = 40000 arm exceeds the L = 10 arm's by at least 20 MiB while the array bytes do not grow with L (the L = 40000 maximum is below 4 x the L = 10 maximum plus 64 KiB). C5: the control moves: `KeyCacheKey` live bytes at 64 MiB capacity exceed those at 0 by at least 2 MiB, and are below 0.5 MiB at 0.
6. *Conclusion rows added (B3g).* (a) C1-C5 hold, G = 0: **Confirmed** ("does not cap" as filed): the check is reached, its grow branch does not fire on a node, the array bytes are negligible and flat, heap follows data, control moves; the unit tier supplies the branch behaviour. (b) S = 0 or no short-read rule hits: the path was not reached: **Not confirmed**. (c) C3 fails (arrays above 1 MiB or growing with L): **Refuted**. (d) G above 0 with C3 holding: Confirmed with a recorded note (the branch is reachable on a node; arrays still negligible). (e) Control does not move: **Not confirmed**. (f) The nodes fail to diverge (no "Requesting ... extra rows" log line): **Not confirmed**, not Invalid.
7. *Cleanup.* Stop both nodes by PID, verify with `ps -eo pid,cmd | grep '[C]assandraDaemon'` for the st directories, delete `~/s4-st/node1`, `node2`.

**B4. Risks and cleanup.** Disk: node data under `/local/tmp` only; 2e6 rows at about 1 KiB is about 2-3 GiB plus commitlog. Do not write into the shared source tree or shared storage. Kill all JVMs started (`pgrep -f 'CassandraDaemon|cassandra-stress|surefire|junit'`), then delete `/local/tmp/c509`, `/local/tmp/node1`, `/local/tmp/out`.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/transform/Stack.java
- src/java/org/apache/cassandra/db/transform/BaseIterator.java (lines 128-172, grep)
- src/java/org/apache/cassandra/db/transform/Transformation.java (lines 195-215, grep)
- src/java/org/apache/cassandra/service/reads/ShortReadProtection.java (lines 60-80)
- src/java/org/apache/cassandra/service/reads/ShortReadPartitionsProtection.java (grep)
- grep results over src/java/org/apache/cassandra for `MoreContents`

## D. Stage-4 feedback

Stage 4 ran this file on 2026-10-25 (node pc07, tag `st`); results: `stage4-runtime-verification/results/transform-stack-capacity-splice-newCount--autonomous.md`, harness `stage4-runtime-verification/harness/transform-stack-capacity-splice-newCount--autonomous/`. Nothing committed.

- **Verdict: Confirmed at both tiers, effect "does not cap"; outcome class true negative** (estimate `negative`, effect `does not cap`). Unit: `stack.length` followed the closed forms of B2i.6 exactly in 27 refill runs (grows only when `P + M > cap(K + M)`, to exactly `newCount`, up to 100000, independent of R in {1, 10, 1000}); retained heap equals the pointer array (ratio 1.00); the positive control moved heap (up to 192 MB for 160000 rows; `OutOfMemoryError` at the 512 MiB cap) with `stack.length` flat. Cluster: on two diverged loopback nodes `splice` ran 55,102 times (27,551 short-read refills), the grow branch (line 95) fired 0 times, array bytes never exceeded 680 B in any histogram sample, node-1 live heap rose from 72.6 to 178.2 MiB with L = 10 to 40000, and the key-cache control moved from 0 to 2.56 MB.
- **Amendments made at the audit (dated 2026-10-25, before any reading):** the filed arithmetic (`newCount = P + K`, example "K=5, P=6 gives 11") was wrong, the code gives `newCount = P + M` where M is the number of transformations applied after the extension (B2i.1); numbers and closed forms added (B2i.6); a cluster arm was added although no knob exists (B3i), after reading in the source that the grow branch cannot fire on a node (a short-read replacement is a deserialised plain iterator, so `prefix = EMPTY`; `ShortReadPartitionsProtection.java:179-198`, `BaseIterator.java:149-158`). The filed B3 fallback (RF=1 or a hedged 2-node setup) would not have forced short reads.
- **What stage 3 could improve:** (1) for a line that only grows an array, the ground "no knob, internal capacity" was right; the stage-4 value is in the closed form and in showing the branch is unreachable in a live node, which source reading can decide (check who supplies the replacement iterator). (2) B2h asked for `-Xmx512m` through `ant testsome`; testsome fixes the fork heap at 1 GiB. (3) The histogram of transient arrays is a weak sampler; a Byteman rule on the check is the sharper cluster instrument.
- **Not confirmed / gaps:** the grow branch was not reached on a node, so the cluster tier shows that the check is reached and does not grow, not that growth is harmless there; the unit tier covers growth. No run 2.

