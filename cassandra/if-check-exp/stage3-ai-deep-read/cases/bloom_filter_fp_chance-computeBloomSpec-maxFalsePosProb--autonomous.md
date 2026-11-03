# bloom_filter_fp_chance (bits-per-key selection in computeBloomSpec) — verification solution  <!-- file: cases/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BloomCalculations.java:147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L147) and `src/java/org/apache/cassandra/utils/BloomCalculations.java:151#1` (shared constraint) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-26 |
| Estimate | `positive`: the per-table `bloom_filter_fp_chance` is mapped by `computeBloomSpec` to a bits-per-key value in [2, 20] (147 sets the 2-bit floor, 151 rejects values that would need more than the 20-bit ceiling), and the off-heap bloom filter (and its on-disk `Filter.db`) is allocated as exactly `ceil((keys*bpk+20)/64)*8` bytes, so off-heap and disk usage per key follow the knob. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `bloom_filter_fp_chance`, a per-table schema option
(CQL `CREATE/ALTER TABLE ... WITH bloom_filter_fp_chance = x`). Field
`TableParams.bloomFilterFpChance` ([`TableParams.java:76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L76));
default derived from compaction strategy at [`TableParams.java:99-101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L99-L101) via
`CompactionParams.defaultBloomFilterFbChance()` ([`CompactionParams.java:261-264`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CompactionParams.java#L261-L264)):
0.1 for LCS, 0.01 otherwise. Unit: probability (dimensionless). Valid range enforced
at [`TableParams.java:160-167`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L160-L167): `> probs[20][14] = 6.71e-05` and `<= 1.0`, using
`BloomCalculations.minSupportedBloomFilterFpChance()` ([`BloomCalculations.java:193-198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L193-L198)).
No restart needed; takes effect for sstables written after the ALTER (flush, compaction,
`upgradesstables -a`), existing filters are not rebuilt
(`doc/modules/cassandra/pages/managing/operating/bloom_filters.adoc`, "Changing").
Associated hard ceilings (constants, not settable): 20 buckets per element
(`probs.length - 1`, [`BloomCalculations.java:43-66`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L43-L66), applied at `:187`) and
`BITSET_EXCESS = 20` bits ([`FilterFactory.java:35`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FilterFactory.java#L35)).


**Limit type (2026-10-29).** non-config: per-table/per-index option. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Off-heap native memory of each sstable's bloom filter
(`OffHeapBitSet` via `Memory.allocate`, `src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java:39-53`)
and the same number of bytes on disk in the `Filter.db` component. The compared
quantity at 147/151 is the requested `maxFalsePosProb` against the false positive
table `probs[buckets][k]`; the result is `bucketsPerElement` (bits per key), which
multiplies the key count.

**A3. Mechanism.**
1. Writer creates a filter for each new sstable: [`SortedTableWriter.java:445`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java#L445)
   `FilterFactory.getFilter(b.getKeyCount(), params.bloomFilterFpChance)`; also on load
   when the filter is rebuilt ([`BigSSTableReaderLoadingBuilder.java:206-207`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java#L206-L207),
   [`BtiTableReaderLoadingBuilder.java:156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/bti/BtiTableReaderLoadingBuilder.java#L156)).
2. `FilterFactory.getFilter(long, double)` ([`FilterFactory.java:60-68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FilterFactory.java#L60-L68)): fp == 1.0 ->
   `AlwaysPresent` (0 bytes, `:63-64`, `offHeapSize()` 0 at `:117-120`); otherwise
   `maxBucketsPerElement(numElements)` ([`BloomCalculations.java:180-188`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L180-L188), = 20 for
   any realistic key count) and `computeBloomSpec`.
3. `computeBloomSpec` ([`BloomCalculations.java:140-172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/BloomCalculations.java#L140-L172)):
   - line 147: if fp >= `probs[2][1]` = 0.393, return 2 bits per key, K=1 (floor).
   - line 151: if fp < `probs[maxBuckets][maxK]` (6.71e-05 at 20 buckets), throw
     `UnsupportedOperationException` (ceiling). Normally pre-empted by schema validation
     ([`TableParams.java:161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableParams.java#L161)), so the ceiling is enforced at ALTER/CREATE time.
   - lines 157-170: smallest bucket count whose optimal-K probability is <= fp, then relax K.
4. `createFilter` ([`FilterFactory.java:70-75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FilterFactory.java#L70-L75)): `numBits = numElements*bpk + 20`,
   `new OffHeapBitSet(numBits)` allocates `ceil(numBits/64)*8` bytes
   ([`OffHeapBitSet.java:41-47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java#L41-L47); >16 GB rejected at `:42-43`).
5. Outcomes at the limit: fp high -> floor 2 bits/key; fp too low -> query rejected
   by validation (or exception at 151 if reached directly).
   Overshoot paths: the key count is an estimate (`getKeyCount()` at flush/compaction,
   `estimateRowsFromIndex` on rebuild), so memory scales with the estimate, not the
   true count; the knob bounds bytes **per key**, not total bytes (total grows with
   partitions and sstable count, overlapping sstables duplicate keys).

**A4. Other consumers.** Other off-heap structures: index summaries (BIG format),
memtables with offheap allocation, chunk cache, compression metadata, BTI partition
index; direct buffers for networking. On disk: Data/Index/Partitions files dwarf
Filter.db. None of these is controlled by `bloom_filter_fp_chance`.

**A5. Evidence beyond the source.**
`doc/modules/cassandra/pages/managing/operating/bloom_filters.adoc` (memory rises as
fp falls; 0.01 is ~3x of 0.1); `doc/cql3/CQL.textile:361` (filters are sized to the
probability, affecting in-memory and on-disk size);
`test/unit/org/apache/cassandra/utils/BloomFilterTest.java` (existing harness pattern).

## B. Verification solution

**B1. Claim under test.** For a fixed number of partitions N, the bloom filter
off-heap bytes (and Filter.db bytes) of an sstable equal `ceil((N_est*bpk(fp)+20)/64)*8`,
with bpk(fp) = 2 for fp >= 0.393, 5 for fp = 0.1, 10 for 0.01, 15 for 0.001, 20 for
0.0001, 0 bytes for fp = 1.0; and fp below 6.71e-05 is rejected.

### B2. Unit tier

**B2a. Environment and build.** Clone the tag to local disk:
`git clone --branch cassandra-5.0.9 --depth 1 /Users/yangwang/cassandra-src /local/c509 && cd /local/c509 && ant jar build-test` (JDK 11).
Add `test/unit/org/apache/cassandra/utils/BloomFpChanceMemoryTest.java` in the local clone.
Run with `ant testsome -Dtest.name=org.apache.cassandra.utils.BloomFpChanceMemoryTest`.
Default test JVM options are fine (filters are off-heap; largest is 2.5 MB).

> **Amendment U1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2a, B2e and B4 on this host (the advisor's Mac, `stage4-runtime-verification/environment-advisor.md`).
> There is no `/local`. The run clone is `$W/cassandra-run58` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9
> ~/cassandra-src $W/cassandra-run58`, then `ant -Dlocal.repository=$W/m2 build-test`, JDK 11). The test source lives in the harness
> (`stage4-runtime-verification/harness/<stem>/BloomFpChanceMemoryTest.java`); `unit-run.sh` copies it into
> `test/unit/org/apache/cassandra/utils/` of the clone, runs `ant -Dlocal.repository=$W/m2 testsome
> -Dtest.name=org.apache.cassandra.utils.BloomFpChanceMemoryTest`, copies `build/test/logs/**/TEST-*.log` (the test's stdout, one line per
> write) and the JUnit XML to `$W/logs/<stem>/unit-<label>/`, and removes the copied source (clone `git status` clean). A shakedown
> (`BFM_SHAKE=1` in the environment: N = 10 000 and 20 000, 100 000 absent keys; not judged) runs first.

**B2b. Knobs.** fp in {1.0, 0.5, 0.393, 0.2, 0.1, 0.01, 0.001, 0.0001, 0.0000672, 0.0000671}:
covers the AlwaysPresent case, the 147 floor on both sides of 0.393, interior values,
the 20-bit ceiling and the 151 throw just below it. Set as the argument to
`FilterFactory.getFilter(N, fp)` and `BloomCalculations.computeBloomSpec(20, fp)`.

**B2c. Workload.** N in {1,000,000, 2,000,000}. For each (N, fp): create filter,
add N distinct keys (`FilterTestHelper`-style `FilterKey` from `ByteBufferUtil.bytes(i)`
hashed via `Murmur3Partitioner`'s token, or `BloomFilterTest.key()` pattern),
read `offHeapSize()` and `serializedSize(false)`, measure empirical FP rate on 1,000,000
absent keys, then `close()`.

**B2d. Observables and instruments.** `BloomSpecification.bucketsPerElement` and `K`;
`IFilter.offHeapSize()` (bytes of native memory); `serializedSize(false)` (Filter.db
bytes); empirical FP rate. Native allocation itself is not observed separately in
this tier (it is `Memory.allocate(byteCount)` with byteCount = offHeapSize).

**B2e. Procedure.** 1) Write the test with a parametrised loop printing
`fp, N, bpk, K, offHeapSize, serializedSize, fpRate`. 2) Assert expected values from B2f.
3) `assertThrows(UnsupportedOperationException.class, () -> computeBloomSpec(20, 0.0000671))`.
4) Run; save output.

> **Amendment U2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2b–B2e, exact. Present keys: `new BufferDecoratedKey(new LongToken(0L), ByteBufferUtil.bytes(i))` for int
> i in [0, N) (the `FilterTestHelper.wrap` pattern of `BloomFilterTest`); absent keys: the same with int i in [1 000 000 000,
> 1 000 000 000 + M), M = 1 000 000 (disjoint from every present key). One test method, one JVM. First, for each fp of B2b in its order
> plus **fp = 0.00006** (added by this audit: a value strictly below `probs[20][14]`, the value B3b already uses, so the unit tier has
> a direct test of the line-151 throw whatever 0.0000671 does), `BloomCalculations.computeBloomSpec(20, fp)` prints
> `BFSPEC fp=<fp> bpe=<bucketsPerElement> K=<K>` or `BFSPEC fp=<fp> THROWS <class>: <message>`. Then for rep = 1, 2 (B2h's repeat,
> in the same JVM), for N = 1 000 000 then 2 000 000, for each fp of B2b in its order: `FilterFactory.getFilter(N, fp)` (an exception
> prints `BFP rep=<r> N=<N> fp=<fp> THROWS <class>: <message>` and the loop goes on), add the N present keys, count `isPresent` over
> the M absent keys, read `offHeapSize()` and `serializedSize(false)` and the hash count (`BloomFilter.hashCount`, `-` for the
> AlwaysPresent filter), print `BFP rep=<r> N=<N> fp=<fp> class=<simple class name> K=<k> offheap=<bytes> serialized=<bytes>
> fpcount=<count> absent=<M>`, then `close()`. Last line `END bfspec=11 bfp=40`. B2e step 3's `assertThrows` becomes the recorded
> `BFSPEC fp=6.71E-5 …` line: the test makes no assertions, so a mismatch does not stop the remaining cells; `selfcheck.py` judges every
> line against B2f.

**B2f. Predictions.**

| fp | bpk | K | offHeapSize N=1M | N=2M |
|---|---|---|---|---|
| 1.0 | — | — | 0 | 0 |
| 0.5, 0.393 | 2 | 1 | 250,008 | 500,008 |
| 0.2 | 4 (row 3 best 0.237 > 0.2; row 4 best 0.147) | 2 (relaxed: probs[4][2]=0.155 <= 0.2) | 500,008 | 1,000,008 |
| 0.1 | 5 | 3 | 625,008 | 1,250,008 |
| 0.01 | 10 | 5 | 1,250,008 | 2,500,008 |
| 0.001 | 15 | 7 | 1,875,008 | 3,750,008 |
| 0.0001, 0.0000672 | 20 | 10 for 0.0001, 14 for 0.0000672 | 2,500,008 | 5,000,008 |
| 0.0000671 | throws at line 151 | | | |

Empirical FP rate <= fp (within sampling error) for every row. serializedSize = offHeapSize plus a fixed small header (constant across fp; record it).

> **Amendment U3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2f, exact where it said "within sampling error" or "record it"; no filed value is changed.
> (a) `serialized` = `offheap` + 8 for every fp < 1.0 (a 4-byte hash count, `BloomFilterSerializer.java:65-70`, plus a 4-byte word
> count, `OffHeapBitSet.java:139-142`), and 0 for fp = 1.0 (`FilterFactory.java:110`). (b) "Empirical FP rate <= fp (within sampling
> error)" means `fpcount` ≤ M·fp + 3·√(M·fp·(1−fp)) with M = 1 000 000; for fp = 1.0 the AlwaysPresent filter answers every key
> (`fpcount` = M, rate 1 = fp). (c) The `BFSPEC` lines carry the table's bpk and K (for 0.0000671: throws `UnsupportedOperationException`
> with "Unable to satisfy 6.71E-5 with 20 buckets per element", `BloomCalculations.java:151-155`); `BFSPEC fp=6.0E-5` throws the same
> class with "Unable to satisfy 6.0E-5 with 20 buckets per element". (d) The `BFP` hash count K equals the table's K where it states
> one; the 0.0000671 `BFP` cells throw. (e) "Doubles with N": offheap(2M) − 8 = 2·(offheap(1M) − 8), as the table's values are.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| offHeapSize matches table, doubles with N | claim confirmed at unit level |
| Bytes differ from formula, or not monotone non-increasing in fp | mechanism mis-traced; claim wrong |
| 0.393 and 0.5 give different sizes | line 147 floor not as traced |
| 0.0000671 does not throw | line 151 ceiling not as traced |
| FP rate >> fp | memory saved at accuracy cost; mapping wrong |

> **Amendment U4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2g, verdicts (Effect follows below), checked in this order. **I (Invalid; fix and rerun):** fewer than 11
> `BFSPEC` or 40 `BFP` lines, no `END` line, or a rep-1 and rep-2 cell differ in `offheap`, `serialized` or `fpcount` (B2h's
> determinism). **Refuted** if any of the filed rows 2–5 holds, naming each part that holds: **R1** (filed row 2) an `offheap` differs
> from the B2f table or is not monotone non-increasing in fp; **R2** (filed row 3) 0.393 and 0.5 give different `offheap`; **R3**
> (filed row 4) `BFSPEC fp=6.71E-5` does not throw, or (added with U2) `BFSPEC fp=6.0E-5` does not throw; **R4** (filed row 5) an
> `fpcount` above the U3 (b) bound. **C (Confirmed, filed row 1):** none of I, R1–R4, every `offheap` matches the table and doubles with
> N as U3 (e), every `BFSPEC` and K as U3 (c)–(d), `serialized` as U3 (a). **N (Not confirmed):** no row fits (e.g. only U3 (a) or (d)
> misses). **Effect:** `caps` if `offheap` per N is a non-increasing step function of fp that is constant over the largest accepted
> values (the floor), largest and constant over the smallest accepted values (the ceiling of bits per key), and a value below the
> smallest accepted one throws; `does not cap` if `offheap` is the same for every fp < 1.0; otherwise `undetermined`.

**B2h. Controls.** Same N and keys across fp values; fp=1.0 gives the zero baseline;
N doubling confirms linear-in-keys term; repeat run to confirm determinism.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, JDK 11, built from the local clone
(`ant jar`). In `conf/cassandra.yaml`: `data_file_directories`, `commitlog_directory`,
`hints_directory`, `saved_caches_directory` on local disk with ≥ 20 GB free;
`auto_snapshot: false`. `conf/jvm-server.options`: add
`-XX:NativeMemoryTracking=summary`. Heap `-Xms2G -Xmx2G`. Start `bin/cassandra -f -p /tmp/c509.pid` (background).

> **Amendment C1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3a and B4 on this host. No Linux, `/local` or `setsid`. The node runs from `$W/cassandra-run58` (U1; no `ant`
> while a node runs) with its conf in `$W/node-bfcs/conf` (the clone's `conf/` with this node's yaml lines appended by the harness's
> `make-node-conf.sh`: `cluster_name: bfcs`, listen/rpc 127.0.0.1, data, commitlog, hints, saved_caches and cdc_raw under
> `$W/node-bfcs/`, `auto_snapshot: false`); 119 GiB free on the internal SSD. Heap by `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (gives
> `-Xms2G -Xmx2G`). `-XX:NativeMemoryTracking=summary` and the Byteman agent of C3 (4) go in `JVM_EXTRA_OPTS` on the node command only
> (not in `jvm-server.options`). Start: `CASSANDRA_CONF=$W/node-bfcs/conf bin/cassandra -f > node.out 2>&1 < /dev/null &` as a tracked
> background process, PID = `$!` (no `-p`); up = `nodetool status` `UN 127.0.0.1` and `nodetool statusbinary` `running`. Stop (B3e 7, B4):
> `nodetool drain`, `kill <PID>`, then `ps -eo command | grep '[C]assandra''Daemon'` and `pgrep -f '[S]tress'` empty, then
> `rm -rf $W/node-bfcs`. Script and logs: harness `cluster-run.sh`, `$W/logs/<stem>/cluster-<label>/`. A shakedown (N = 200 000, not
> judged) runs first.

**B3b. Knobs.** `bloom_filter_fp_chance` on `keyspace1.standard1` in {1.0, 0.5, 0.1, 0.01, 0.001, 0.0001};
also attempt 0.00006 (expect rejection). Set by
`bin/cqlsh -e "ALTER TABLE keyspace1.standard1 WITH bloom_filter_fp_chance = X"`.

**B3c. Workload.** `tools/bin/cassandra-stress write n=10000000 no-warmup cl=ONE -col n=FIXED\(1\) size=FIXED\(16\) -rate threads=50 -node 127.0.0.1`
(10M partitions, ~1-2 GB on disk). Then `bin/nodetool flush && bin/nodetool compact keyspace1 standard1`
to get one sstable. For each fp value: ALTER, then
`bin/nodetool upgradesstables -a keyspace1 standard1` (rewrites the sstable, new filter).
At fp=0.0001: expected filter 25,000,008 bytes; at 0.5: 2,500,008, a 10x range, well above noise.

> **Amendment C2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3c, exact. Stress as filed (keys `seq=1..10000000`, the write default), output to a file; `Total errors` must
> be 0. Then `nodetool flush keyspace1 standard1`, `nodetool compact keyspace1 standard1`, and wait until `nodetool compactionstats`
> shows `pending tasks: 0` and tablestats `SSTable count: 1`. The table is the one stress creates (STCS, so fp 0.01 at the start;
> read back from `system_schema.tables`). After each ALTER the value is read back from `system_schema.tables`; after each
> `upgradesstables -a` the same idle wait, then 5 s, then the sample.

**B3d. Observables and instruments.** (1) `nodetool tablestats keyspace1.standard1`:
"Bloom filter off heap memory used", "Bloom filter space used", "Number of partitions (estimate)", "SSTable count".
(2) `ls -l <data>/keyspace1/standard1-*/*-Filter.db`. (3) `jcmd $(cat /tmp/c509.pid) VM.native_memory summary`
before and after each rewrite (category `Other`/`Internal` holds Unsafe allocations; take diffs with `VM.native_memory baseline` then `summary.diff`).
Sample once after each upgradesstables completes and `nodetool compactionstats` shows no pending tasks.
Cannot observe: per-allocation attribution in NMT (other off-heap users share the category).

> **Amendment C3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3d on this host, and the real-memory instrument. (1) tablestats as filed, raw bytes (no `-H`). (2) `stat -f %z`
> of each `*-Filter.db` (no file = 0 bytes) instead of `ls -l`, and the `Data.db` file name (generation) to tell that a rewrite happened.
> (3) NMT as filed (`VM.native_memory baseline` after the load, `summary.diff` at each sample) is kept **for information only**: the
> filter is allocated with JNA `Native.malloc` (`OffHeapBitSet.java:47` → `Memory.java:65` → `MemoryUtil.java:81-84`), which NMT does not
> track, so NMT cannot show it (A3/B3d's "Unsafe allocations" is a mis-trace of the instrument, not of the claim). (4) Added, to see the
> real allocation: Byteman observe-only rules (harness `bf.btm`, agent `build/lib/jars/byteman-4.0.20.jar`) print to `node.out` each
> `MemoryUtil.allocate(size)` (size and returned address), each `MemoryUtil.free(address)`, each `OffHeapBitSet(long)` constructed (byte
> count) and each `OffHeapBitSet.close()` (byte count). At a sample, the harness records `node.out`'s byte offset; **Lmal** = the sum of
> the sizes of the addresses allocated and not freed up to that offset (all native bytes the process holds through `MemoryUtil`), and
> **Lbf** = the bit-set bytes constructed minus closed. These see what the process asks of libc; an OS reading is not available here
> (`vmmap` cannot attach to the JVM on this Mac and RSS does not fall when a large malloc is freed — known-answer check of 2026-10-27),
> a gap named. (5) `tools/bin/sstablemetadata` of the `Data.db`: `totalRows`, the limit-reached check.

**B3e. Procedure.** 1) Start node, wait for `nodetool status` UN. 2) Run stress, flush, compact.
3) `jcmd <pid> VM.native_memory baseline`. 4) For fp in the B3b order: ALTER; upgradesstables -a;
wait idle; record tablestats, Filter.db size, `VM.native_memory summary.diff`. 5) Attempt fp=0.00006, record error.
6) Positive control: with fp=0.01, run a second stress `n=10000000` with a different key range
(`-pop seq=10000001..20000000`), flush, compact; record filter bytes (should double).
7) Stop: `kill $(cat /tmp/c509.pid)`; confirm with `pgrep -f CassandraDaemon` empty.

> **Amendment C4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3e, exact. (1) Make the conf, start (C1). (2) Stress, flush, compact, idle wait (C2); sample **LOAD**.
> (3) `jcmd <PID> VM.native_memory baseline`; sample **B0** (its `node.out` offset is the baseline mark for Lmal and Lbf). (4) For fp in
> 1.0, 0.5, 0.1, 0.01, 0.001, 0.0001: ALTER, read back, `upgradesstables -a`, idle wait, sample **F<fp>**. (5) ALTER to 0.00006: record the
> cqlsh output and exit status and read back the value. (6) ALTER to 0.01 (the current value is 0.0001 after step 4), read back, stress
> `n=10000000 -pop seq=10000001..20000000` (otherwise as B3c), flush, compact, idle wait, sample **CTRL**. (7) Stop (C1). A sample =
> tablestats, `Filter.db` and `Data.db` names and sizes, sstablemetadata, NMT `summary.diff` (from step 3 on), `node.out` offset,
> process RSS (information only).

**B3f. Predictions.** With N_est ≈ 10M (estimate within a few %):
filter off-heap bytes ≈ 0, 2.5 MB, 6.25 MB, 12.5 MB, 18.75 MB, 25 MB for fp = 1.0, 0.5, 0.1, 0.01, 0.001, 0.0001,
each within ±5% of `ceil((N_est*bpk+20)/64)*8` using tablestats' partition estimate.
Filter.db size ≈ same bytes. NMT Other/Internal diff tracks the filter difference within ±2 MB.
fp=0.00006 rejected with "bloom_filter_fp_chance must be larger than 6.71E-5". Control: 20M keys at 0.01 -> ≈ 25 MB.

> **Amendment C5 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3f, exact; no filed value or band is changed except the instrument of the NMT sentence. N_est = tablestats
> "Number of partitions (estimate)" of the same sample; bpk as B1; F(fp) = ceil((N_est·bpk+20)/64)·8. At each F<fp> sample, tablestats
> "Bloom filter off heap memory used" and the `Filter.db` bytes are each within ±5% of F(fp) (fp = 1.0: 0 and no file). **The NMT
> sentence is replaced** (C3 (3)): Lmal(sample) − Lmal(B0) is within ±2 MB (2 000 000 bytes) of the tablestats off-heap difference
> between the sample and B0; Lbf(sample) − Lbf(B0) is within 64 KiB of the same difference (Lbf also counts other tables' filters,
> e.g. system tables flushed between samples); and each rewrite at fp < 1.0 prints a `BMBF BA` line, between the previous sample's offset and
> this one's, equal to the sample's tablestats off-heap figure. The rejection text is the prefix
> "bloom_filter_fp_chance must be larger than 6.71E-5" (`TableParams.java:161-167`); the read-back stays 0.0001. CTRL: within ±5% of
> F(0.01) at the CTRL N_est (≈ 20M, ≈ 25 MB), i.e. about twice the F0.01 sample.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Filter bytes follow the table across fp values | claim confirmed: knob governs off-heap and disk filter usage |
| Filter bytes unchanged after ALTER+upgradesstables | rewrite did not pick up knob, or claim wrong; check sstable generation changed |
| Bytes scale with fp but deviate > 5% from formula | key-count estimate overshoot (A3), note magnitude |
| NMT does not move while tablestats moves | metric not reflecting real allocation; claim wrong for actual memory |
| Control (2x keys) does not double bytes | workload did not reach the filter; run inconclusive |
| fp=0.00006 accepted | validation ceiling missing |

> **Amendment C6 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3g, verdicts, checked in this order; the first matching group decides. **I1 (Invalid):** after the load
> `totalRows` ≠ 10 000 000, N_est outside ±5% of 10 000 000, stress errors > 0, or a sample with SSTable count ≠ 1. **I2 (Invalid,**
> filed row 2 with the generation unchanged**):** a rewrite did not happen. **I3 (Invalid,** filed row 5**):** CTRL bytes not within ±5%
> of F(0.01) at the CTRL N_est, or CTRL `totalRows` ≠ 20 000 000. **Refuted**, naming each part that holds: **R1** (filed row 2 with the
> generation changed) filter bytes unchanged after a rewrite at a new fp; **R2** (filed row 4, instrument per C3/C5) Lmal does not track
> the tablestats difference within ±2 MB, or the Lbf difference or the `BMBF BA` line is not as C5; **R3** (filed row 6) 0.00006 accepted; **R4** (added) the bytes
> at one or more fp values deviate by more than 5% from F(fp) while the other values are within ±5% at the same N_est (bpk at those
> values is not as traced). **N1 (Not confirmed,** filed row 3**):** every value deviates by more than 5% in the same direction (estimate
> overshoot; magnitude noted). **C (Confirmed,** filed row 1**):** none of the above, every F<fp> as C5, R2's tracking holds, the
> rejection as C5, CTRL as C5. **N0 (Not confirmed):** no row fits. **Effect:** `caps` if filter bytes rise as fp falls across the six
> values, are largest at 0.0001 and 0.00006 is refused; `does not cap` if the bytes are the same at every fp < 1.0; otherwise
> `undetermined`. NMT readings (C3 (3)) are not a row condition.

> **Amendment 2026-10-27 (after run 1, authorised by the user) — B3g C6 I1 and I3 (the `totalRows` clauses).** **This amendment follows
> run 1's readings.** Run 1's cluster tier was Invalid under I1 and I3 only because the sstable held `totalRows` 9 999 195 after the load and
> 19 997 026 at CTRL, against the exact 10 000 000 / 20 000 000 that C6 required, with 0 stress errors. C6 had assumed that 10 000 000 stress
> writes give 10 000 000 distinct partitions; the stress source does not say that. **What the source determines** (cassandra-5.0.9,
> `tools/stress/src/org/apache/cassandra/stress/`): (i) the legacy write's partition key is `HexBytes("key", GeneratorConfig("randomstrkey",
> null, fixed(10), null))` (`settings/SettingsCommandPreDefined.java:77-82`, keysize 10 at `:108`), whose identity distribution is the default
> `uniform(1..100B)` (`generate/values/Generator.java:59-62`; "B" = 10^9, `settings/OptionDistribution.java:181-196`), a commons-math
> `UniformRealDistribution` over a `JDKRandomGenerator` (`OptionDistribution.java:489-502`, `generate/DistributionBoundApache.java:40-59`),
> reseeded per partition with `seed ^ salt`, salt = murmur3 of "randomstrkey" (`Generator.java:51-55`, `GeneratorConfig.java:39-48`); the key
> is 10 characters, one per 4 bits of one draw (`'0'`–`'9'`, `'K'`–`'P'`, `generate/values/HexBytes.java:39-55`), after a first draw used for
> the size; (ii) one key per seed: `PartitionIterator.setSeed` (`generate/PartitionIterator.java:87-101`), a single-row iterator for a table
> without clustering columns (`:71-77`) whose `reset` always succeeds (`:140-146`), one partition per operation
> (`operations/predefined/PredefinedOperation.java:49`); (iii) the seeds: `-pop seq=a..b` gives a `SeriesGenerator` with seed
> `(start + (next % totalCount)) * multiplier` for next = 0, 1, … (`generate/SeedManager.java:57-69, 156-182`), multiplier = 1 +
> round(10^(22 − log10 sampleSize)) = 10^16 + 1 for the default revisit distribution `uniform(1..1M)` (`SeedManager.java:46-54`,
> `settings/SettingsInsert.java:62`); `n=` gives exactly n permits, each taking one seed (`WorkManager.java:31-55`,
> `operations/PartitionOperation.java:89-119`), and with `visits` fixed(1) (`SettingsInsert.java:61`) no revisit sample is used
> (`SeedManager.java:81, 95-111, 124-129`). So the keys of a load over seq=a..b are the fixed set {key((i·(10^16+1)) ^ salt) : a ≤ i ≤ b}:
> **the number of distinct partitions is a deterministic function of the source, not a random variable**, and the tolerance the distribution
> gives is **zero**. (For independent uniform draws over D = 10^11 values one would expect about n²/2D = 500 lost keys at n = 10^7 and 2 000 at
> 2·10^7; the source does not give independent draws — the java.util.Random states of consecutive seeds form an arithmetic progression
> modulo 2^48 — so that model is not what the source determines and is not used.) **Expected counts**, computed by running stress's own
> generator classes from the run clone, outside any node (harness `StressKeyCount.java`; output
> `stage4-runtime-verification/results/<stem>/run1b-cluster/stress-key-count.txt`): **E(1..10 000 000) = 9 999 195** distinct keys
> (805 lost), **E(1..20 000 000) = 19 997 026** (the LOAD and CTRL seeds together, 2 974 lost); for the shakedown (N = 200 000, not judged)
> E(1..200 000) = 200 000 and E(1..400 000) = 400 000. **I1 now reads:** after the load `totalRows` ≠ E(1..N) (9 999 195 for N = 10 000 000),
> N_est outside ±5% of 10 000 000, stress errors > 0, stress `Total partitions` ≠ N for either load, or a sample with SSTable count ≠ 1.
> **I3 now reads:** CTRL bytes not within ±5% of F(0.01) at the CTRL N_est, or CTRL `totalRows` ≠ E(1..2N) (19 997 026). B3c's "10M
> partitions" means 10 000 000 stress writes (seq 1..10 000 000), as filed. Nothing else changes: B1, B3f/C5 (every size relation already uses
> N_est, not the exact N), I2, R1–R4, N1, C, N0, the Effect rule and the unit tier are as frozen. Choice between the two ways the user offered:
> (a), the exact expected count, because the source determines it exactly; (b) (measured `totalRows` as N within a fraction of n) would need a
> fraction the source does not supply, and the size predictions already take N from the sample. **What was known of run 1 when this was
> written:** all of run 1's results (its results file §4–§5, including `totalRows` 9 999 195 and 19 997 026, the −50% at fp 0.5 and the other
> readings). The expected counts were computed after that and **equal run 1's readings exactly**; this was not arranged — the count comes from
> the generator alone, and the first program version, with a key-decoding error, printed other numbers before it was fixed on the key format
> (`HexBytes.java:49-50`), not on a reading (run1b-cluster/stress-key-count-v0-encoding-bug.txt). **Run 1 under this amendment** would pass
> I1 and I3 (every other validity condition held in run 1) and match **R4** (fp 0.5 at −50.0% while the other values are within ±5%), i.e.
> Refuted — caps.

**B3h. Controls.** Same data across all fp values (only the knob changes); single sstable
so no duplicates; `nodetool compactionstats` idle before sampling; NMT baseline taken after
the initial load so memtable/other allocations are excluded; 2x-keys control.

**B4. Risks and cleanup.** Data ~2-4 GB on local disk only; `auto_snapshot: false` so
no snapshots accumulate (check `nodetool listsnapshots`, `nodetool clearsnapshot --all`).
Never build in the shared clone. After run: kill the node and stress, check
`pgrep -f 'CassandraDaemon|cassandra-stress'` empty, `rm -rf` the local data/commitlog/hints dirs.
Unit tier: filters closed in the test; no files written.

## C. Sources read

src/java/org/apache/cassandra/utils/BloomCalculations.java
src/java/org/apache/cassandra/utils/FilterFactory.java
src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java
src/java/org/apache/cassandra/utils/BloomFilter.java
src/java/org/apache/cassandra/schema/TableParams.java
src/java/org/apache/cassandra/schema/CompactionParams.java
src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java
src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java
src/java/org/apache/cassandra/io/sstable/format/bti/BtiTableReaderLoadingBuilder.java
src/java/org/apache/cassandra/io/sstable/filter/BloomFilterMetrics.java
src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsHolder.java
doc/modules/cassandra/pages/managing/operating/bloom_filters.adoc
doc/cql3/CQL.textile
test/unit/org/apache/cassandra/utils/BloomFilterTest.java

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1** (advisor's Mac; frozen sha256 `8bc80c38…` after amendments U1–U4, C1–C6;
results [`../../stage4-runtime-verification/results/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous.md`](../../stage4-runtime-verification/results/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous.md); uncommitted).
**Unit: Refuted — caps** (B2g rows 2, 4, 5): the line-147 floor gives **1 bit per key with K = 2** (offheap 125 008 / 250 008 B at
N = 1 M / 2 M; empirical FP rate 0.747, above the requested 0.5 or 0.393), because line 149 passes `(2, optKPerBuckets[2])` to the
`(k, bucketsPerElement)` constructor (`BloomCalculations.java:114`); and `computeBloomSpec(20, 6.71E-5)` does **not** throw (line 151 uses `<`
and 6.71e-05 is `probs[20][14]`; the minimum is refused by `TableParams.java:161`'s `<=`); 6.0E-5 throws. Every interior value (0.2 … 0.0000672)
matched B2f exactly. **Cluster: Invalid — undetermined** (C6 I1, I3): stress's legacy keys collide (`totalRows` 9 999 195 of 10 M, 19 997 026
of 20 M); for information, the readings show the same 1-bit floor at fp 0.5 (−50%), every other value equal to F to the byte, the native
allocation (Byteman Lmal) tracking tablestats within 74 B, and 0.00006 refused. A3/B3d's NMT "Unsafe" instrument cannot see the filter
(JNA `Native.malloc`). B1, B2f and B3f are left as filed. A cluster re-run needs a user-authorised re-freeze of C6 I1/I3.

**2026-10-27, stage 4 cluster re-run "run 1b"** (advisor's Mac, fresh clone `$W/cassandra-run69`; re-frozen sha256 `c8b73fda…` after the
user-authorised `Amendment 2026-10-27 (after run 1, authorised by the user) — B3g C6 I1 and I3`; same results file, §7; uncommitted).
**Cluster: Refuted — caps** (C6 R4, fp 0.5 only): `totalRows` 9 999 195 / 19 997 026 equal the distinct-key counts the stress source determines
(computed with stress's own generator, so the run is valid); fp 0.5 gives 1 237 704 B, −50.0% from F (the 1-bit floor of line 149, as in the
unit tier), every other value equals F at N_est to the byte, the Byteman native ledger tracks tablestats within 74 B, CTRL doubles, 0.00006 is
refused. Every reading is identical to run 1's. Run 1's cluster verdict (Invalid) is kept in the results file. B1, B3f and the unit tier are left
as filed. For stage 3: the legacy cassandra-stress write's keys collide deterministically (805 of 10 M), so a design needing an exact partition
count must compute it from the stress source or avoid that key generator.
