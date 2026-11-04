# paxos_cache_size — verification solution  <!-- file: cases/paxos_cache_size-close-active--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`PaxosState.java:520`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/paxos/PaxosState.java#L520) (`if (--cur.active > 0)` in `PaxosState.close()`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5[1m]`), Claude Code CLI (version not queried), 2026-10-26, autonomous agent, Band D triage |
| Estimate | `positive`. The check is a reference count. When it reaches zero, the per-partition Paxos `Snapshot` leaves the unbounded `ACTIVE` map and goes into `RECENT`, a Caffeine map whose total weight is capped at `paxos_cache_size` MiB. So the heap held by idle Paxos state follows the knob. One caveat: the weigher counts only the row payload, so the real heap can exceed the cap by a per-entry overhead factor. That factor is large when values are tiny. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `paxos_cache_size`. It is a configuration entry, declared at
[`Config.java:485`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L485)
(`DataStorageSpec.LongMebibytesBound paxos_cache_size = null`). Unit: MiB. Default: `null`,
which means "auto". In that case [`DatabaseDescriptor.java:850-852`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L850-L852) sets
`paxosCacheSizeInMiB = min(max(1, (int)(Runtime.totalMemory() * 0.01 / 1MiB)), 50)`, i.e.
1% of the heap committed at startup (with `-Xms` = `-Xmx` this is the whole heap), clamped
to [1, 50] MiB. A negative value is rejected ([`DatabaseDescriptor.java:854-860`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L854-L860)). Getter:
`DatabaseDescriptor.getPaxosCacheSizeInMiB()` (`:3942`). How to set it: the yaml key
`paxos_cache_size: <n>MiB`, which is **not** listed in `conf/cassandra.yaml`. There is no
JMX setter. The value is read once, when `PaxosState` is class-initialized
([`PaxosState.java:72-76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/paxos/PaxosState.java#L72-L76), a static final field), so changing it **needs a restart**.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap. It caps the total *weight* of `PaxosState.RECENT`. The weight
of one entry is `accepted.update.unsharedHeapSize() + committed.update.unsharedHeapSize()`,
saturated to int (`PaxosState.java:74`). `PartitionUpdate.unsharedHeapSize()` is the sum of
row heap sizes plus the static row plus the deletion info (`PartitionUpdate.java:357-361`).
Each row adds its cells (`BTreeRow.java:532-541`), and each cell counts the backing array of
its value (`BufferCell.java:141-144`, `ObjectSizes.java:155-175`).

**A3. Mechanism.**
1. Every replica-side Paxos operation takes a `PaxosState` from `ACTIVE`, an unbounded
   `ConcurrentHashMap` ([`PaxosState.java:71`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/paxos/PaxosState.java#L71)), and increments `active`. If the entry is
   missing, it creates one, seeding it with `RECENT.remove(key)`. See `getUnsafe`
   (`:371-383`), `tryGetUnsafe` (`:355-369`) and `lock` (`:396-401`). The v1 handlers use
   this through `legacyPrepare` / `legacyPropose` (`:720-800`, try-with-resources). v2 uses
   it through `PaxosState.get` (`:349-353`).
2. `close()` (`:514-528`) decrements `active`. **Target check `:520`:** if other users
   remain, the entry stays in `ACTIVE`. Otherwise it is removed from `ACTIVE`, and its
   `current` Snapshot is put into `RECENT` (`:523-525`), but only if its runtime class is
   exactly `Snapshot` (an `UnsafeSnapshot`, i.e. state never loaded from disk, is dropped).
3. `RECENT` is built with `.maximumWeight(paxosCacheSizeInMiB << 20)`, the weigher above,
   and `.executor(ImmediateExecutor.INSTANCE)` (`:72-76`). Caffeine therefore runs eviction
   maintenance on the calling thread. After each write, the total weight is brought back to
   the maximum or below by evicting entries.
4. On a cache miss the state is reloaded from `system.paxos`
   (`maybeLoad`, `:424-449`, `SystemKeyspace.loadPaxosState`). So eviction costs only a
   read, never correctness.

Outcomes when the limit is reached: an insert at `:525` triggers synchronous eviction of
other entries. An entry heavier than the whole maximum is evicted at once. With
`paxos_cache_size: 0MiB` nothing is retained.

Bypasses and overshoot:
- (a) `ACTIVE` is unbounded. It holds every partition with an in-flight Paxos operation.
  That is bounded only by concurrency, not by this knob.
- (b) The weigher omits the `Key` (`DecoratedKey`: token, key buffer), the `Snapshot`, two
  `Ballot`s, the `Accepted`/`Committed` wrappers, the `PartitionUpdate` shell and holder,
  and Caffeine's node and hash-table overhead. With tiny values, the real heap per entry can
  be several times its weight.
- (c) Values backed by direct buffers are counted at a fixed `DIRECT_BUFFER_DEEP_SIZE`
  ([`ObjectSizes.java:171-172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ObjectSizes.java#L171-L172)), an undercount.
- (d) A heap value that is a slice of a larger array is counted at the whole array's size
  ([`ObjectSizes.java:174`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ObjectSizes.java#L174)), an overcount, so fewer entries are retained.

**A4. Other consumers.** Other heap users the knob does not control:
- `ACTIVE`.
- The `system.paxos` memtable and its sstables (each operation is also persisted, e.g.
  `SystemKeyspace.savePaxosProposal`, `PaxosState.java:661`).
- Coordinator-side Paxos objects and `PaxosRepair` instances (`PaxosRepair.java:165-172`).
- The uncommitted-key tracker (`PaxosState.uncommittedTracker()`).
- The general memtables of the user table that the commit applies to (`PaxosState.java:694-697`).

**A5. Evidence beyond the source.**
- `test/distributed/org/apache/cassandra/distributed/test/CasWriteTest.java:95` and
  `test/distributed/org/apache/cassandra/distributed/test/PaxosRepairTest.java:383` set
  `paxos_cache_size` to `0MiB` to force reloads from disk. That shows the knob governs
  retention.
- `test/unit/org/apache/cassandra/service/paxos/PaxosStateTest.java` calls
  `PaxosState.RECENT.clear()` (lines 122, 166, 217, 245) for the same reason.
- The `RECENT` cache came with Paxos v2, CASSANDRA-17164 (https://issues.apache.org/jira/browse/CASSANDRA-17164).
- Caffeine `maximumWeight` semantics: https://github.com/ben-manes/caffeine/wiki/Eviction#size-based.

## B. Verification solution

**B1. Claim under test.** After Paxos operations on many distinct partitions, the heap held by
`PaxosState.RECENT` stays bounded and scales with `paxos_cache_size`. The summed weigher
value never exceeds `paxos_cache_size × 2^20` bytes. For values of 8 KiB the actual retained
heap stays within 1.3× the cap. If the retained heap keeps growing with the number of
distinct partitions once it is past the cap, or does not change when the knob changes, the
claim is wrong.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- `git clone --branch cassandra-5.0.9 --depth 1 /Users/yangwang/cassandra-src /local/c509`
  (or clone from GitHub onto local disk), then `cd /local/c509 && ant jar build-test`.
- New test class `test/unit/org/apache/cassandra/service/paxos/PaxosCacheBoundTest.java`
  in the local clone. Run it with
  `ant testsome -Dtest.name=org.apache.cassandra.service.paxos.PaxosCacheBoundTest -Dpaxos.cap=<MiB> -Dpaxos.v=<bytes>`.
  The build already attaches the jamm agent (`build.xml:1159`).
- Add `-Dtest.jvm.args` only if needed. The default test heap is enough for a cap of 64 MiB
  or less.

> **Amendment U1 (2026-10-27, stage-4 audit; replaces the paths and the command above).** Host: the advisor's Mac
> (`environment-advisor.md`). Clone: `W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run49`
> (full clone, no `/local`), then `cd $W/cassandra-run49 && ant -Dlocal.repository=$W/m2 build-test`. The test class is kept in
> `cassandra/stage4-runtime-verification/harness/paxos_cache_size-close-active--autonomous/PaxosCacheBoundTest.java` and copied into the clone
> only for the run (removed afterwards). **`-Dpaxos.cap` / `-Dpaxos.v` on the `ant` command line do not reach the test**: the forked
> test JVM gets only the `testmacro` jvmargs and `${test.jvm.args}` (`build.xml:1153-1192`), so the command is
> `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.service.paxos.PaxosCacheBoundTest -Dtest.jvm.args="-Dpaxos.cap=<MiB|auto> -Dpaxos.v=<bytes> -Dpaxos.n=<N>"`
> (`-Dno-build-test=true` added after the first run has compiled the class). The test heap is `maxmemory="1024m"` (`build.xml:1153`);
> no other JVM option is added. `paxos.cap=auto` leaves `paxos_cache_size` null (the default).

**B2b. Knobs.** `paxos_cache_size` ∈ {0, 1, 4, 16, 64} MiB: zero as the control, then a
geometric spread. It must be set **before** `PaxosState` loads. In `@BeforeClass`, first call
`DatabaseDescriptor.daemonInitialization(() -> { Config c = DatabaseDescriptor.loadConfig(); c.paxos_cache_size = new DataStorageSpec.LongMebibytesBound(Long.getLong("paxos.cap") + "MiB"); return c; });`.
Then call `SchemaLoader.loadSchema(); SchemaLoader.schemaDefinition("PaxosCacheBoundTest");`.
The later `daemonInitialization()` inside `SchemaLoader` returns early
(`DatabaseDescriptor.java:258-259`). Each cap is a separate JVM run, because the cap is a
static final field. A second knob, the value size V ∈ {16 B, 8192 B}, exposes the overhead
factor.

> **Amendment U2 (2026-10-27, stage-4 audit).** (i) The grid adds the **default**: `paxos.cap=auto` leaves `c.paxos_cache_size`
> null, so the effective cap is `min(max(1, (int)(totalMemory·0.01/2^20)), 50)` MiB (`DatabaseDescriptor.java:850-852`); the test
> prints the effective value and the relations of B2f use it as P. (ii) Grid: V = 8192 at P ∈ {0, 1, 4, 16, 64, auto}; V = 16 at
> P ∈ {0, 1, 4, 16} only. P = 64 with V = 16 is left out because 200,000 × w(16) is not shown from source to exceed 64 MiB (the run
> would land in the "never exceeded" row). (iii) Every (P, V) is run twice (B2h), each in its own JVM, with `build/test/cassandra`
> removed before each run. (iv) `SchemaLoader.schemaDefinition("PaxosCacheBoundTest")` creates the keyspace
> `PaxosCacheBoundTestKeyspace1` (`SchemaLoader.java:99`), not `PaxosStateTestKeyspace1`; B2c's table is therefore
> `PaxosCacheBoundTestKeyspace1.Standard1` (partition key `key`, clustering `name`, regular column `val`, all `AsciiType`,
> `SchemaLoader.java:377-386`). (v) `@AfterClass` stops the Gossiper, as `PaxosStateTest` does.

**B2c. Workload.**
- For i in 0..N-1, build a `PartitionUpdate` for key `"k"+i` on
  `PaxosStateTestKeyspace1.Standard1` with one row: clustering `"a"`, column `val`, a value
  of V random bytes. Use `RowUpdateBuilder`, as in `PaxosStateTest.java:76-79`.
- Call `PaxosState.legacyPropose(new Commit.Accepted(Ballot.atUnixMicrosWithLsb(nowMicros+i, 0, Ballot.Flag.GLOBAL), update))`.
  Each call goes through `getUnsafe` → `close()` → `:520` false → `RECENT.put` with
  `accepted` = the update.
- Per-entry weight w ≈ V + about 150 B of cell and row overhead (≈ 8.3 KiB for V = 8 KiB).
- N = 40,000 × (V = 8 KiB) ≈ 330 MiB of offered weight, more than 5× the largest cap.
  With V = 16 B, N = 200,000 offers about 30 MiB, more than 1.8× a 16 MiB cap.
- The `system.paxos` writes go to the test data dir under `build/test/cassandra`, on local
  disk. They amount to about 330 MiB for the large-V runs.

> **Amendment U3 (2026-10-27, stage-4 audit).** Exact workload: N = 40,000 for V = 8192 and N = 200,000 for V = 16
> (`-Dpaxos.n`). Proposal i (0-based) uses key `"k"+i`, clustering `"a"`, and a value of V bytes drawn from `java.util.Random(42)`
> mapped into printable ASCII (0x20–0x7e), so the `AsciiType` column holds valid text; the value length, and hence the weight, is
> unchanged. The ballot is `Ballot.atUnixMicrosWithLsb(base + i, 0, Ballot.Flag.GLOBAL)` with `base` = `FBUtilities.timestampMicros()`
> at test start; the update is built with `RowUpdateBuilder(metadata, base + i, "k"+i)`. Every `legacyPropose` must return `true`
> (counted; a `false` fails the run). Keys are distinct, so the only path that removes an entry from `RECENT` is eviction
> (`getUnsafe`'s `RECENT.remove(key)` only touches the key being proposed, which was never inserted before; `PaxosState.java:371-383`).

**B2d. Observables and instruments.** After every 1,000 proposals, record:
- `W = PaxosState.RECENT.values().stream().mapToLong(s -> (s.accepted != null ? s.accepted.update.unsharedHeapSize() : 0) + s.committed.update.unsharedHeapSize()).sum()`,
  the check's operand;
- `n = RECENT.size()`;
- `D = ObjectSizes.measureDeep(PaxosState.RECENT)`, minus `D1`, the value measured when
  exactly one entry was present. `D1` also covers the shared `TableMetadata` reached through
  that entry;
- `PaxosState.ACTIVE.size()`, which should be 0.

Write them to stdout as CSV `i,W,n,D,active`. `W` is the cache's own accounting.
Caffeine's internal `weightedSize()` is not exposed through `asMap()`, so it is recomputed
as above.

> **Amendment U4 (2026-10-27, stage-4 audit).** Samples are taken after proposal 1 (this sample gives `D1` when `n = 1`), after
> every 1,000th proposal, and after the last. Each sample is one stdout line
> `PCB,<i>,<W>,<n>,<D>,<active>,<wmin>,<wmax>` where `wmin`/`wmax` are the smallest and largest per-entry weight (the weigher
> expression applied to each entry; `-1` when `n = 0`). One line `PCB-START,cap_mib=<getPaxosCacheSizeInMiB()>,max_bytes=<cap·2^20>,v=<V>,n=<N>,variant=<paxos_variant>,purging=<paxosStatePurging()>`
> precedes the samples; one line `PCB-END,proposed=<N>,accepted=<count of true>,d1=<D1 or -1>` follows them. Test stdout lands in
> `build/test/logs/**/TEST-org.apache.cassandra.service.paxos.PaxosCacheBoundTest.log`; it is copied per run to
> `$W/logs/paxos_cache_size-close-active/unit-<label>/P<P>-V<V>-r<rep>.log`.

**B2e. Procedure.**
1. Clone and build (B2a).
2. Add the test class with the `@BeforeClass` from B2b and a single `@Test` running B2c/B2d.
3. For each cap in {0, 1, 4, 16, 64} and each V in {8192, 16}, run
   `ant testsome -Dtest.name=org.apache.cassandra.service.paxos.PaxosCacheBoundTest -Dpaxos.cap=$cap -Dpaxos.v=$V | tee /local/out/unit-$cap-$V.log`.
4. Between runs, `rm -rf build/test/cassandra`.
5. Extract the CSV lines.

> **Amendment U5 (2026-10-27, stage-4 audit; replaces steps 1–5 above).** `harness/paxos_cache_size-close-active--autonomous/unit-run.sh <label>`
> does, logging every command and its output to `$W/logs/paxos_cache_size-close-active/unit-<label>/commands.log`: copy the test
> class into the clone; for each (P, V) of U2 (ii) and rep ∈ {1, 2}: `rm -rf build/test/cassandra`, run the U1 command, copy the
> TEST log and JUnit XML; then remove the test class and its compiled classes from the clone. A failed JUnit run is recorded and the
> script goes on. Raw files are not edited after capture.

**B2f. Predictions.**
- cap 0: `n = 0` and `W = 0` throughout.
- cap P > 0:
  - `W ≤ P·2^20` at every sample.
  - Once offered weight exceeds `P·2^20`, `W` plateaus in [0.95, 1.0]·`P·2^20` and
    `n` ≈ `P·2^20 / w`. For V = 8192: n ≈ 126·P (≈ 126, 505, 2,020, 8,080).
  - For V = 8192, `D − D1` plateaus within [0.9, 1.3]·`P·2^20`.
  - For V = 16, `D − D1` plateaus at a constant multiple k·`P·2^20` with 2 ≤ k ≤ 8 (the
    overhead factor of A3 bypass (b)). It stays flat as N grows and scales linearly in P.
- `ACTIVE.size()` = 0 at every sample.

> **Amendment U6 (2026-10-27, stage-4 audit; makes the predictions above exact, derived from source, before any reading).**
> Let M = P·2^20 and w = the per-entry weight.
> (a) **w is constant within a run** (`wmin = wmax` at every sample with n > 0): every entry has the same shape (one row, clustering
> `"a"`, one cell of V bytes, plus the empty committed update), and the key is not weighed (`PaxosState.java:74`).
> (b) **Source bound on w for V = 8192:** 8,208 ≤ w ≤ 9,232 B — the value's backing array alone is 16 + 8,192 B
> (`ObjectSizes.sizeOnHeapOf`, `ObjectSizes.java:155-175`), and the remaining objects counted by the weigher (row, clustering and its
> buffer, liveness, B-tree array, cell, cell buffer, two static rows, two deletion infos; `PartitionUpdate.java:357-361`,
> `BTreeRow.java:532-541`, `BufferCell.java:141-144`) are at most 16 objects of ≤ 64 B each (≤ 1,024 B). Hence the plateau n lies in
> [⌊M/9,232⌋, ⌊M/8,208⌋]: P = 1: [113, 127]; 4: [454, 511]; 16: [1,817, 2,044]; 64: [7,269, 8,176].
> (c) **Exact cap relation (P > 0):** `W ≤ M` at every sample; at every sample with i·w ≤ M, n = i (nothing evicted); at every sample
> with i·w > M, n = ⌊M/w⌋ and W = n·w. Reason: Caffeine evicts while `weightedSize > maximum`, one entry at a time, synchronously on
> the writing thread (`.executor(ImmediateExecutor.INSTANCE)`, `PaxosState.java:75`), so with equal weights it stops at ⌊M/w⌋.
> (d) **Disallow evidence (P > 0):** the final sample has n < i (= N); by U3 only eviction removes entries.
> (e) **Ordering:** the plateau n for P = 1, 4, 16, 64 follows (c), so it grows ≈ ×4 per step.
> (f) **Repeats:** the two runs of each (P, V) give the same final n and W (both are fixed by (c)); the D − D1 plateaus agree
> within 5% (B2h).
> (g) **V = 16, "flat as N grows":** over all samples with i·w > 2·M, max(D − D1) / min(D − D1) ≤ 1.05; k = (D − D1)/M at the final
> sample. The k band [2, 8] above is unchanged.
> (h) cap 0: n = 0 and W = 0 at every sample (as above). auto: (a)–(d) with P = the printed `cap_mib`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `W` and `D` plateau, and the plateau scales with P (×4 per step) | claim confirmed: the knob caps RECENT |
| `W` exceeds `P·2^20` after maintenance | claim refuted: the weight bound is not enforced |
| `D` keeps rising linearly with N past the cap | claim refuted: retained heap is not bounded (e.g. an untracked leak or `ACTIVE` growth) |
| Plateau the same for all P | claim refuted: the knob is not applied (e.g. set after class init) |
| V = 16: `D` ≫ `P·2^20` but flat, linear in P | confirmed with overshoot: bounded, but the weigher undercounts. Report k. |
| cap 0 retains entries | weigher or cap broken; claim refuted for 0 |
| offered weight never exceeded the cap | not confirmed: raise N |

> **Amendment U7 (2026-10-27, stage-4 audit; rows added and row 1 sharpened before any reading).**
> - Row 1 ("claim confirmed") requires, for V = 8192 at every P > 0 of the grid: U6 (a), (c), (d), (f); D − D1 at the final sample
>   in [0.9, 1.3]·M (B2f); and cap 0 per U6 (h). (b) is a check on the weigher's size, not on the cap: a w outside (b) is recorded
>   as a missed sub-prediction and does not by itself change the row.
> - **`W ≤ M` and n follows (c), but D − D1 for V = 8192 is above 1.3·M** → claim refuted in bytes (B1's 1.3× bound fails while the
>   weight cap holds); Effect still `caps` if D − D1 is flat.
> - **D − D1 for V = 8192 below 0.9·M while (c) holds** → not confirmed: the instrument does not see what the weigher counts.
> - **V = 16 flat (U6 (g)) and linear in P, but k outside [2, 8]** → B1's verdict is unaffected (B1 bounds only 8 KiB values);
>   recorded as a missed sub-prediction, with k.
> - **The two repeats of a (P, V) disagree beyond U6 (f)** → not confirmed.
> - **`cap_mib` printed ≠ the intended P, or a `legacyPropose` returned false, or `ACTIVE.size()` ≠ 0** → invalid run for that (P, V).
> - **n < i never happens for some P > 0 although i·w > M** (no eviction) → claim refuted (the cap is not enforced).

**B2h. Controls.**
- cap 0 as the zero point.
- `ACTIVE.size()` = 0 rules out entries being held outside the cache.
- `D1` subtraction removes shared schema objects.
- Run each cap twice and check that the plateaus agree within 5%.
- Check that `DatabaseDescriptor.getPaxosCacheSizeInMiB()` printed at test start equals the
  intended cap.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node built from the same local clone (`ant jar`).
- Run from `/local/c509` with `bin/cassandra -f`.
- `conf/jvm-server.options` / `jvm11-server.options`: `-Xms4G -Xmx4G`, G1 (default).
- `cassandra.yaml`: `data_file_directories`, `commitlog_directory`, `hints_directory` and
  `saved_caches_directory` under `/local/node1` (local disk with ≥ 20 GB free).
- `paxos_variant: v1` (the default). Optional repeat with `v2`.
- Cluster name `pcache`, listening on 127.0.0.1.

> **Amendment C1 (2026-10-27, stage-4 audit; replaces the paths above).** Host: the advisor's Mac (`environment-advisor.md`). The
> node runs from the unit tier's clone `$W/cassandra-run49` (built by `build-test`; no `ant` runs in it while a node is up) with
> `bin/cassandra -f > <log> 2>&1 < /dev/null` started as a tracked background process (no `setsid` here). Per round, a fresh
> directory `$W/node-pcca/` holds `conf/` (a copy of the clone's `conf/`, passed as `CASSANDRA_CONF`), `data/`, `commitlog/`,
> `hints/`, `saved_caches/`, `cdc_raw/` and `logs/` (`CASSANDRA_LOG_DIR`); it is removed after the round. Heap: `MAX_HEAP_SIZE=4G
> HEAP_NEWSIZE=800M` (`cassandra-env.sh` then sets `-Xms4G -Xmx4G`), G1 from `jvm11-server.options`. `cluster_name: pcache`,
> listen/rpc 127.0.0.1, `paxos_variant` left at the default `v1` (`Config.java:1051`). The optional `v2` repeat is not run.
> `JVM_EXTRA_OPTS` (scoped to the `bin/cassandra` command) adds the Byteman agent of C4 (3):
> `-javaagent:build/lib/jars/byteman-4.0.20.jar=script:<harness>/pcca.btm,sys:<helper jar> -Dpcca.out=<round dir>/probe.txt`.

**B3b. Knobs.** `paxos_cache_size` ∈ {0MiB, 8MiB, 32MiB, 128MiB}, plus the positive control
`1024MiB`. Add a line `paxos_cache_size: <v>` to `cassandra.yaml` and restart for each value.
Confirm the value took effect with
`cqlsh -e "select * from system_views.settings where name='paxos_cache_size'"`.

> **Amendment C2 (2026-10-27, stage-4 audit).** The grid adds the **default** (no `paxos_cache_size` line): the effective cap is
> `min(max(1, (int)(totalMemory·0.01/2^20)), 50)` MiB (`DatabaseDescriptor.java:850-852`); with `-Xms4G` `totalMemory` is the 4 GiB
> committed heap, so the default is **40 MiB** (any `totalMemory` between 4,000 and 4,096 MiB also gives 40). Rounds, in order:
> 0MiB, 8MiB, 32MiB, default, 128MiB, 1024MiB, each on a fresh node directory. The settings table shows the configured value (`null`
> for the default); the **effective** cap is read back from `DatabaseDescriptor.getPaxosCacheSizeInMiB()` in every probe line of
> C4 (3) (`cap_mib=`), and that read-back is the knob check. The settings table is read with the bundled Python driver
> (`harness/…/pcca-client.py settings`), not `cqlsh`.

**B3c. Workload.**
- `CREATE KEYSPACE pk WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE pk.t (k int PRIMARY KEY, v blob);`
- 50,000 statements `INSERT INTO pk.t (k,v) VALUES (?, ?) IF NOT EXISTS` with distinct k and
  an 8,192-byte random blob. Drive them with the cassandra-stress user profile
  (`tools/bin/cassandra-stress user profile=/local/pcache.yaml ops\(ins=1\) n=50000 -rate threads=16`),
  where the profile's `ins` query is the LWT above (`serial-consistency` SERIAL), or with
  a small Python driver loop.
- Each LWT leaves one Snapshot whose committed update weighs ≈ 8.3 KiB:
  50,000 × 8.3 KiB ≈ 405 MiB offered, more than 3× the largest capped value and less than
  the 1024 MiB control.
- Duration: a few minutes per run.

> **Amendment C3 (2026-10-27, stage-4 audit).** The Python-driver loop is used (`harness/…/pcca-client.py`, the bundled driver
> `lib/cassandra-driver-internal-only-*.zip`, protocol 5, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`): prepared
> `INSERT INTO pk.t (k, v) VALUES (?, ?) IF NOT EXISTS`, v = `os.urandom(8192)`, commit consistency `ONE`, serial consistency
> `SERIAL`, 32 requests in flight, request timeout 60 s. The 50,000 statements run in five chunks k ∈ [0, 10,000), …, [40,000,
> 50,000); each chunk returns only when all its requests have completed, and the B3d readings are taken between chunks (this is
> the "every 10,000 statements" sampling, at a moment with no request in flight). Every statement must come back `[applied] = True`
> with 0 errors. The value is copied into an exact-length heap array on the server (`CBUtil.readBoundValue`, `CBUtil.java:466-481`),
> so bypasses (c) and (d) of A3 do not arise. The schema is created by the same client (`schema` mode).

**B3d. Observables and instruments.**
- (1) After the load ends and a 30 s idle: `jcmd <pid> GC.run`, then
  `jcmd <pid> GC.class_histogram | grep -E 'PaxosState\$Snapshot |PaxosState\$Key '`.
  This gives the instance counts `n_S`, `n_K`.
- (2) `jcmd <pid> GC.heap_info` and `nodetool info` (Heap Memory used) after GC, giving
  `H`.
- (3) Optional: `jcmd <pid> GC.heap_dump /local/out/h-<cap>.hprof`, opened in Eclipse MAT.
  Take the retained heap of the static field `org.apache.cassandra.service.paxos.PaxosState.RECENT`
  (`R`).
- Sample (1) and (2) also every 10,000 statements during load.
- What cannot be observed directly: the weigher sum. Infer it as `n_S × w`.

> **Amendment C4 (2026-10-27, stage-4 audit; replaces (1)–(3) and the last bullet).** (1) `jcmd <pid> GC.class_histogram` (it
> collects before counting, so no separate `GC.run`); `n_S` and `n_K` are the instance columns of the rows whose class column is
> exactly `org.apache.cassandra.service.paxos.PaxosState$Snapshot` and `…PaxosState$Key`. (2) `H` = the histogram's `Total` bytes;
> `GC.heap_info` and `nodetool info` are dropped (`GC.heap_info` after a GC failed a known-answer check on this host). `H` is taken
> once more after the final `nodetool flush`, and is **informational only** (no row depends on it; other heap users, A4, are not
> controlled). (3) **MAT is not installed here**, so the retained heap of `RECENT` is measured in-process instead: a Byteman rule
> (`harness/…/pcca.btm`, observe-only) on `StorageService.getConcurrentViewBuilders()` (called only from JMX, via
> `nodetool getconcurrentviewbuilders`; `StorageService.java:2031-2034`) calls the helper `stage4.pcca.PcacheProbe.report()`
> (helper jar on the system class path through Byteman's `sys:`), which appends one line
> `PROBE,epoch_ms,cap_mib,n,W,wmin,wmax,D,Mtm,active` to `probe.txt`: `cap_mib` = `getPaxosCacheSizeInMiB()`, `n` = `RECENT.size()`,
> `W` = the weigher sum (the weigher expression of `PaxosState.java:74` over every entry), `wmin`/`wmax` the per-entry extremes
> (`-1` when empty), `D` = `ObjectSizes.measureDeep(PaxosState.RECENT)`, `Mtm` = `ObjectSizes.measureDeep` of one entry's
> `TableMetadata` (`committed.update.metadata()`, shared by all entries; 0 when empty), `active` = `ACTIVE.size()`. A baseline probe
> is taken after the schema exists and before any LWT (`D_empty`). **R := D − D_empty − Mtm** (0 when n = 0). The weigher sum is now
> observed, not inferred. Readings are taken after the schema (baseline), after each of the five chunks, and after the 30 s idle
> (final), each as: probe, then histogram.

**B3e. Procedure.**
1. Build. Write the yaml with the first cap. Start the node and wait for `nodetool status` UN.
2. Create the schema.
3. Run the workload, sampling as in B3d.
4. Idle 30 s, then take the final readings (1), (2) and (3).
5. `nodetool stopdaemon`; `pgrep -f CassandraDaemon` must return nothing.
6. `rm -rf /local/node1/*`.
7. Repeat for each cap, then for 1024MiB.

> **Amendment C5 (2026-10-27, stage-4 audit; replaces steps 1–7).** `harness/…/cluster-run.sh <label> <cap…>` per round: make
> `$W/node-pcca/` and its yaml (C1, C2; `git diff`-style record of the yaml changes kept); start the node; wait for `UN` and
> `statusbinary` = `running` (fail at once if the process dies); read the settings table; create the schema; baseline probe; five
> chunks, each followed by probe + histogram; idle 30 s; final probe + histogram; `nodetool flush`; histogram (`H` after flush);
> `nodetool stopdaemon`; wait until `ps` shows no Cassandra daemon (kill it if still there after 60 s, and record that); remove
> `$W/node-pcca/`. Logs and raw files go to `$W/logs/paxos_cache_size-close-active/cluster-<label>/C<cap>/`. A failed step is
> recorded and the round is stopped; the script goes on to the next round.

**B3f. Predictions.** For V = 8 KiB, the expected number of retained Snapshots is
`n_S` ≈ 126 × cap(MiB):

| cap | `n_S` | `R` |
|---|---|---|
| 0 | ≈ 0 | — |
| 8 MiB | ≈ 1,000 | 8–10.5 MiB |
| 32 MiB | ≈ 4,000 | 32–42 MiB |
| 128 MiB | ≈ 16,000 | 128–166 MiB |

- `n_S` is flat after the first ≈ `n_S` statements.
- Positive control 1024MiB: `n_S` ≈ 50,000 and `R` ≈ 410–530 MiB, still rising until the
  load ends.
- `H` after GC differs between caps by about the cap difference, plus noise from other heap
  users (A4).

> **Amendment C6 (2026-10-27, stage-4 audit; exact predictions derived from source, before any reading).** Let M = C·2^20 for the
> effective cap C, w the per-entry weight, i the number of statements done at a sample.
> (a) **w constant** at every probe with n > 0 (`wmin = wmax`): after its commit, each key's Snapshot holds `accepted = null`
> (`Snapshot.merge`, `PaxosState.java:222-232`: the accepted ballot equals the commit's, so it is dropped) and a committed update of
> one row with no clustering and one 8,192-byte cell; the key is not weighed. **Bound:** 8,208 ≤ w ≤ 9,232 B (the 16 + 8,192 B value
> array, plus at most 16 further objects of ≤ 64 B: row, liveness, B-tree array, cell, cell buffer, static row, deletion info).
> (b) **Cap relation (C > 0, C ≠ 1024):** `W ≤ M` at every probe; at a probe with i·w ≤ M, n = i; at a probe with i·w > M,
> ⌊M/w⌋ − 1 ≤ n ≤ ⌊M/w⌋ (eviction stops as soon as `weightedSize ≤ maximum`; one entry of slack allows for the prepare and propose
> snapshots of the 32 in-flight keys, whose weights differ from w by the 64-B empty committed update, being replaced at commit).
> With (a)'s bound, the final n lies in [⌊M/9,232⌋ − 1, ⌊M/8,208⌋]: C = 8: [907, 1,022]; 32: [3,633, 4,088]; 40 (default):
> [4,542, 5,110]; 128: [14,537, 16,352]. For C ≤ 40 every probe after a chunk has i·w > M; for C = 128 the 10,000 probe has
> i·w ≤ M (n = 10,000) and the later ones are capped.
> (c) **Disallow evidence (C > 0, C ≠ 1024):** the final n < 50,000 (only eviction removes a finished key's entry; an evicted key
> whose commit arrives later is not re-created, `tryGetUnsafe`, `PaxosState.java:355-369`).
> (d) **cap 0:** n = 0 and W = 0 at every probe; `n_S` = 0.
> (e) **Positive control 1024MiB:** n = i at every probe (50,000 × 9,232 B < 2^30, so nothing is evicted); final n = 50,000;
> W = 50,000·w.
> (f) **Histogram agrees with the probe:** `n_S` = n at every sample (taken right after the probe, nothing in flight).
> (g) **R** (C4 (3)) at the final probe lies in the table's band: 8 MiB: [8, 10.5] MiB; 32: [32, 42]; 40 (default): [40, 52];
> 128: [128, 166]; control: [410, 530] MiB.
> (h) `active` = 0 at every probe.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `n_S`/`R` plateau at ≈ cap/w and scale with cap, while the 1024MiB control reaches ≈ 50,000 | claim confirmed |
| `n_S` ≈ 50,000 at all caps | claim refuted: the cap does not bind |
| Plateau ≫ 1.3 × cap with 8 KiB values | claim refuted in bytes: overshoot beyond the predicted overhead |
| Control also stays low | not confirmed: the workload does not populate RECENT (check `paxos_variant` and the path), so the result says nothing |
| `n_S` the same for every cap | knob not applied: check the settings virtual table |

> **Amendment C7 (2026-10-27, stage-4 audit; rows added and row 1 sharpened before any reading).**
> - Row 1 ("claim confirmed") requires C6 (a) constancy, (b), (c), (d), (e), (f), (h) and (g) for every capped round. The (a)
>   bound on w is a check on the weigher's size; a w outside it is recorded as a missed sub-prediction and does not by itself
>   change the row.
> - **(b) and (c) hold but R above the (g) band for some capped round** → row 3 (claim refuted in bytes); Effect `caps` if R is
>   flat from chunk to chunk.
> - **R below the (g) band while (b) holds** → not confirmed: the instrument does not see what the weigher counts.
> - **`n_S` ≠ n at some sample** → not confirmed for that round: the two instruments disagree (Snapshots held outside `RECENT`, or
>   a probe defect).
> - **effective `cap_mib` ≠ the intended value, client errors or a statement not applied, or `active` ≠ 0** → invalid round.
> - **W > M at a probe of a capped round** → claim refuted (the weight bound is not enforced).

**B3h. Controls.**
- The 1024MiB positive control shows the workload fills the cache when it is unbounded.
- cap 0 gives the zero point and absorbs Snapshot instances alive for other reasons
  (in-flight operations, `ACTIVE`).
- Histogram counts are taken after full GC and idle, so transient Snapshots are gone.
- The settings virtual table confirms the effective cap.
- Use the same heap and the same workload across runs.

**B4. Risks and cleanup.**
- Clone and build only on local disk, never in the shared clone.
- Node data, commit log and heap dumps go under `/local`. Heap dumps are 4 GB each: delete
  them after MAT.
- `system.paxos` grows by about 0.5 GB per cluster run: wipe it between runs.
- After every run, `nodetool stopdaemon` and kill any leftover `CassandraDaemon` and
  cassandra-stress processes (`pgrep -f` must be empty).
- Unit runs: delete `build/test/cassandra` between runs.

> **Amendment C8 (2026-10-27, stage-4 audit; replaces the `/local` paths and the heap-dump lines).** Everything lives under
> `W=~/Library/Caches/stage4`: the clone `$W/cassandra-run49`, node files `$W/node-pcca/` (removed after every round), logs
> `$W/logs/paxos_cache_size-close-active/`. No heap dump is taken (C4 (3)). After every round `ps -eo command | grep '[C]assandraDaemon'`
> must be empty; the test class and its compiled classes are removed from the clone after the unit tier, and `git status` of the
> clone must be clean at the end.

## C. Sources read

- src/java/org/apache/cassandra/service/paxos/PaxosState.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java
- src/java/org/apache/cassandra/db/rows/BTreeRow.java
- src/java/org/apache/cassandra/db/rows/BufferCell.java
- src/java/org/apache/cassandra/utils/ObjectSizes.java
- src/java/org/apache/cassandra/service/paxos/Ballot.java
- src/java/org/apache/cassandra/service/paxos/Commit.java
- src/java/org/apache/cassandra/service/paxos/PaxosRepair.java
- src/java/org/apache/cassandra/transport/CBUtil.java
- src/java/org/apache/cassandra/cql3/QueryOptions.java
- test/unit/org/apache/cassandra/service/paxos/PaxosStateTest.java
- test/unit/org/apache/cassandra/SchemaLoader.java
- test/distributed/org/apache/cassandra/distributed/test/CasWriteTest.java
- test/distributed/org/apache/cassandra/distributed/test/PaxosRepairTest.java
- conf/cassandra.yaml
- build.xml
- https://issues.apache.org/jira/browse/CASSANDRA-17164
- https://github.com/ben-manes/caffeine/wiki/Eviction

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1 (advisor's Mac; Claude Opus 5.5, claude-opus-5-5): unit Confirmed — caps; cluster Confirmed — caps.**
Results: [`../../stage4-runtime-verification/results/paxos_cache_size-close-active--autonomous.md`](../../stage4-runtime-verification/results/paxos_cache_size-close-active--autonomous.md)
(harness `cassandra/stage4-runtime-verification/harness/paxos_cache_size-close-active--autonomous/`; not committed at the time of writing).
Frozen version: sha256 `9f892ab93b5a3df642ebc4b4f6f06516eb4b928babf673e52b15d594ce2ae321` after the fifteen dated audit amendments
(U1–U7, C1–C8) above; no runbook defect. Unit (B2g row 1): the entry count stops at exactly ⌊M/w⌋ (w = 8,632 B for V = 8,192;
121 / 485 / 1,943 / 7,774 entries at 1 / 4 / 16 / 64 MiB; auto = 4 MiB in the 1-GiB test JVM), W ≤ M, real heap 1.05–1.06 × M,
nothing retained at 0 MiB; V = 16 B is bounded with overshoot k ≈ 2.19 (bypass (b) of A3). Cluster (B3g row 1, Paxos v1): w = 8,448 B;
992 / 3,971 / 4,964 / 15,887 Snapshots at 8 / 32 / 40 (default) / 128 MiB, the real heap of `RECENT` 1.058 × its weight, 0 at 0 MiB,
and all 50,000 (426 MiB) under the 1024 MiB control. Not changed by the run, left for stage 3: `TableMetadata` is `@Unmetered`
(`TableMetadata.java:82`), so `measureDeep` of `RECENT` never includes the schema; the filed per-entry estimate (≈ 8.3 KiB,
"≈ 126·P") is ≈ 4 % low in the unit tier.
