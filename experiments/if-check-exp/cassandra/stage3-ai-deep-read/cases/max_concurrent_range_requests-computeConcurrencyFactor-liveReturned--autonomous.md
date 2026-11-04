# cassandra.max_concurrent_range_requests — verification solution  <!-- file: cases/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`RangeCommandIterator.java:162`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java#L162) (`if (liveReturned == 0)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (Claude Code CLI, stage-3 autonomous agent, Band D triage), 2026-10-26 |
| Estimate | `positive`. When no rows have come back yet, the target branch jumps the range-read batch size straight to `maxConcurrencyFactor = min(ranges, cassandra.max_concurrent_range_requests)`. Every sub-range response in a batch is buffered whole on the coordinator heap, and each can hold up to the full page limit, so the property caps peak coordinator heap per range read at about cap x page-limit rows. The cap is in requests, not bytes, and the property was added to limit load, so this is a moderate-confidence positive. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `cassandra.max_concurrent_range_requests`; JVM system property.
Declared at [`CassandraRelevantProperties.java:350`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L350)
(no default in the enum). Read once into a `static final` at
[`RangeCommands.java:54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommands.java#L54):
`Math.max(1, MAX_CONCURRENT_RANGE_REQUESTS.getInt(FBUtilities.getAvailableProcessors() * 10))`.
Unit: number of sub-range (vnode-range) requests per batch. Default 10 x available
processors, minimum 1. Set with `-Dcassandra.max_concurrent_range_requests=N` (JVM_OPTS /
`conf/jvm-server.options`); needs a restart (static final, read at class init). Not in yaml or JMX.


**Limit type (2026-10-29).** config: JVM property. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Coordinator heap: the number of sub-range read requests in flight
together, hence the number of `ReadResponse` messages (one per contacted replica per
sub-range) buffered in `ReadCallback`/`DataResolver` until the batch is iterated.
Compared quantity: `concurrencyFactor`, the loop bound in `sendNextRequests`.

**A3. Mechanism.**
1. `RangeCommands.rangeCommandIterator` ([`RangeCommands.java:69-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommands.java#L69-L121)):
   `maxConcurrencyFactor = min(replicaPlans.size(), MAX_CONCURRENT_RANGE_REQUESTS)` (`:84`);
   initial `concurrencyFactor` = 1 if the local estimate of rows per range is 0, else
   `min(max, ceil(limit / resultsPerRange))` (`:86-97`). The estimate uses local sstables only
   (`estimateResultsPerRange` `:125-135`; [`DataLimits.java:456-462`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/filter/DataLimits.java#L456-L462), `cfs.estimateKeys()`).
2. `RangeCommandIterator.sendNextRequests` ([`RangeCommandIterator.java:223-252`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java#L223-L252)): loop
   `for (i = 0; i < concurrencyFactor && replicaPlans.hasNext(); )`, one `query()` per merged
   replica plan, `i += replicaPlan.vnodeCount()` (`:229-236`). Each `query()` sends the
   sub-range command to every contact (`:211-218`) with the full command limit
   (`forSubRange`, `:190`; "honor the command limit for each range, but will not enforce it
   globally", [`RangeCommands.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommands.java#L60)). Responses are concatenated ([`StorageProxy.java:2067-2092`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2067-L2092));
   `SingleRangeResponse` blocks and resolves lazily per range ([`SingleRangeResponse.java:58-59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/SingleRangeResponse.java#L58-L59)),
   so later ranges' responses sit in heap while earlier ones are consumed.
3. After a batch is exhausted, `updateConcurrencyFactor` (`:148-153`) ->
   `computeConcurrencyFactor` (`:156-176`): capped at `min(max, remaining ranges)` (`:158`);
   **target `:162`**: if `liveReturned == 0` return that max directly; otherwise
   `min(max, round(remainingRows / rowsPerRange))` (`:170-172`).
   - At the limit: the batch is simply truncated at `max` requests; no error.
   - Overshoot/bypass: the cap counts vnodes, and a merged plan counts all its vnodes, so
     requests per batch <= cap (no overshoot in requests). Bytes are not capped: each response
     holds up to the command limit (page size, or the CQL LIMIT if unpaged) rows of any size.
     Top-K (SAI ANN) queries use `ScanAllRangesCommandIterator` and ignore the cap
     ([`RangeCommands.java:81-82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommands.java#L81-L82)). The cap is per query; concurrent range queries multiply.

**A4. Other consumers.** Internode inbound buffers (bounded separately by the
`internode_application_receive_queue_*` reserves); the CQL response page; read-size
guardrails (`local_read_size_*`, `coordinator_read_size_*`) which abort on bytes; replica-side
memory to serve each sub-range; other queries, memtables, caches.

**A5. Evidence beyond the source.** Javadoc at `RangeCommands.java:47-53` (motivation:
avoid a burst of range requests with many vnodes, i.e. load, not memory);
`test/unit/org/apache/cassandra/service/reads/range/RangeCommandsTest.java` (sets the
property with `WithProperties` in `@BeforeClass`, `:56-60`, checks concurrency factors);
`RangeCommandIteratorTest.java`. Related issue: CASSANDRA-15752 (range read concurrency factor), not opened.

## B. Verification solution

**B1. Claim under test.** For a range read whose first batch returns no rows, the next
batch issues at most `min(cap, remaining ranges)` sub-range requests, and the coordinator's
peak heap for that read rises in proportion to min(cap, dense ranges) x page-limit x row size;
lowering the cap lowers the peak.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. `git clone --branch cassandra-5.0.9 /Users/yangwang/cassandra-src /local/c509-rng` (local disk). Add three test classes
`test/unit/org/apache/cassandra/service/reads/range/RangeCapProbe{1,4,16}Test.java`
(identical except the constant), each extending `CQLTester` and, like
`RangeCommandsTest.java:56-60`, setting `MAX_CONCURRENT_RANGE_REQUESTS` with `WithProperties`
in `@BeforeClass` (one class per value because the field is static final; `ant testsome`
forks per class). Build `ant jar build-test`; run `ant testsome -Dtest.name=org.apache.cassandra.service.reads.range.RangeCapProbe4Test` etc.

> **Amendment U1 (2026-10-27, stage-4 audit; replaces the paths and commands above).** Host: the advisor's Mac
> (`environment-advisor.md`); there is no `/local`. Clone: `W=~/Library/Caches/stage4`;
> `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run51`, then `ant -Dlocal.repository=$W/m2 build-test`
> (compiles everything `testsome` needs; no `ant jar`). **Four** classes, `RangeCapProbe1Test`, `RangeCapProbe4Test`,
> `RangeCapProbe16Test`, `RangeCapProbeDefaultTest` (U2), kept in
> `cassandra/stage4-runtime-verification/harness/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous/` and copied
> into the clone's `test/unit/org/apache/cassandra/service/reads/range/` only for the run (removed afterwards, with their compiled
> classes). Each is run once: `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.service.reads.range.RangeCapProbe<V>Test`
> (one forked JVM per class, so the `static final` field is initialised once per value). The run script is `harness/…/unit-run.sh <label>`.
> Every reading is one stdout line starting `RNGU,` (in `build/test/logs/**/TEST-<class>.log`, or the ant console if absent).

**B2b. Knobs.** cap C in {1, 4, 16}; 32 ranges in the ring so 16 < ranges.

> **Amendment U2 (2026-10-27, stage-4 audit; group A: the default was missing).** C ∈ {1, 4, 16, **default**}. The default class sets no
> property, so the field is `max(1, 10 × FBUtilities.getAvailableProcessors())` (`RangeCommands.java:54`); with no
> `cassandra.available_processors` property and no `available_processors` in `test/conf/cassandra.yaml`, that is 10 × 10 = **100** on this
> 10-core host (`FBUtilities.java:135,150`). Each class reads the field `RangeCommands.MAX_CONCURRENT_RANGE_REQUESTS` back by reflection
> and prints it (the knob read-back). Note on "32 ranges": the ring of B2c(b) has 32 tokens, which the full-ring scan splits into **33**
> sub-ranges (`ReplicaPlanIterator` splits at the minimum token; `RangeCommandsTest.java:71-86`: 4 tokens → 5 ranges). The pure-function
> calls of B2c(a) keep `totalRangeCount = 32` as filed.

**B2c. Workload.** (a) Pure function: call `RangeCommandIterator.computeConcurrencyFactor(32, 1, C, 5000, 0)`
(package-private static, test in same package) - liveReturned=0 hits `:162`. Also
`(32, 1, C, 5000, 100)` for the non-zero branch. (b) Iterator: `new TokenUpdater()` with 16
tokens on `127.0.0.1` and 16 on `127.0.0.2`, interleaved (as `RangeCommandsTest.java:71-73`),
table `CREATE TABLE %s (k int PRIMARY KEY, v int)` empty, build a `PartitionRangeReadCommand`
over all data with limit 5000 and call `RangeCommands.rangeCommandIterator(cmd, ONE, RequestTime.forImmediateExecution())`
without iterating (the fake second node would not answer).

> **Amendment U3 (2026-10-27, stage-4 audit; makes B2c/B2e exact).** One `@Test` per class. (a) Print and keep
> `cf0 = computeConcurrencyFactor(32, 1, C, 5000, 0)` and `cf100 = computeConcurrencyFactor(32, 1, C, 5000, 100)`, with C the read-back
> field value. (b) `new TokenUpdater().withTokens("127.0.0.1", 10, 30, …, 310).withTokens("127.0.0.2", 20, 40, …, 320).update()` (16 tokens
> each, interleaved); `createTable("CREATE TABLE %s (k int PRIMARY KEY, v int)")` (empty); `cmd = (PartitionRangeReadCommand) Util.cmd(cfs).build()`
> then `cmd.withUpdatedLimit(DataLimits.cqlLimits(5000))`; open `RangeCommands.rangeCommandIterator(cmd, ONE, Dispatcher.RequestTime.forImmediateExecution())`
> and `new ReplicaPlanIterator(cmd.dataRange().keyRange(), cmd.indexQueryPlan(), keyspace, ONE)` in try-with-resources, read
> `maxConcurrencyFactor()`, `concurrencyFactor()` and `ranges.size()`, close without iterating. Print one line
> `RNGU,<label>,cap=<field>,cf0=<..>,cf100=<..>,max=<..>,cf=<..>,ranges=<..>` **before** any assertion; then assert the U4 values.

**B2d. Observables and instruments.** Return value of `computeConcurrencyFactor`;
`maxConcurrencyFactor()` and `concurrencyFactor()` of the built iterator (`@VisibleForTesting`
accessors `RangeCommandIterator.java:292-301`). Heap and actual request count are not
observed here.

**B2e. Procedure.** Run each class; assert and print the values.

**B2f. Predictions.** (a) liveReturned=0: returns C for C in {1,4,16} (min(C, 31)). liveReturned=100,
rangesQueried=1: rowsPerRange=100, remaining=4900 -> round(49) -> min(C,49) = C.
(b) `maxConcurrencyFactor()` = min(32, C) = C; `concurrencyFactor()` = 1 (empty table -> estimate 0, `RangeCommands.java:94-95`).

> **Amendment U4 (2026-10-27, stage-4 audit; exact predictions for every class, derived from `RangeCommandIterator.java:159-177` and
> `RangeCommands.java:84-96` before any reading).**
>
> | Class | cap (read-back) | cf0 | cf100 | max | cf | ranges |
> |---|---|---|---|---|---|---|
> | `1` | 1 | 1 | 1 | 1 | 1 | 33 |
> | `4` | 4 | 4 | 4 | 4 | 1 | 33 |
> | `16` | 16 | 16 | 16 | 16 | 1 | 33 |
> | `Default` | 100 | 31 | 31 | 33 | 1 | 33 |
>
> cf0 = max(1, min(C, 32 − 1)); cf100: rowsPerRange = 100, remaining = 4900, round(49.0) = 49, so min(min(C, 31), 49); max = min(33, C);
> cf = 1 because the empty table's estimate is 0 (`:94-95`). For the default the range bound (31, 33) binds instead of the cap.

> **Amendment D1 (2026-10-27, stage-4 runbook defect found at the unit shakedown, before run 1; corrects the default row of U2/U4 only).**
> The forked unit-test JVM runs with `-XX:ActiveProcessorCount=${cassandra.test.processorCount}` = 2 (`build.xml:136,1170`), so in the
> unit tier the default is 10 × 2 = **20**, not 100 (the shakedown line printed `procs=2`). The `Default` row of U4 is therefore: cap 20,
> cf0 20, cf100 20, max 20, cf 1, ranges 33 (the cap binds; no class of the unit tier is uncapped, and C = 1 vs 16 vs 20 still moves the
> operand). The class's assertion constant is changed to 20. Rows 1 and 2 of U5 read against this row; nothing else changes. The node's
> default (C3, 100) is unaffected: no node option sets the processor count (`conf/` has only the commented `jvm-server.options:41`).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| All values equal C as predicted | mechanism caps batch size as traced |
| Any value > C | claim wrong: cap does not bound the batch |
| (b) concurrencyFactor != 1 | estimate path differs from trace; re-check B3 workload design (not a refutation) |

> **Amendment U5 (2026-10-27, stage-4 audit; rows read against U4, rows added before any reading).** Row 1 reads "every printed value
> equals U4 for the four classes (C for C ∈ {1, 4, 16}; the range bound 31 / 33 for the default)". Row 2 reads "any value above U4's".
> Added: (a) the read-back `cap` ≠ the class's value → **invalid run** (the property did not reach the field; not a refutation);
> (b) `ranges` ≠ 33 → the ring differs from U3; **invalid run**; (c) no `RNGU` line for a class (error before the print) → **runbook
> defect**, the tier stops; (d) a value below U4's for C ∈ {1, 4, 16} (other than cf, covered by row 3) → **not confirmed**: the operand is
> not the traced one.

**B2h. Controls.** C=16 vs 1 shows the knob moves the operand; the 32-range ring keeps
`remaining ranges` from being the binding term.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, three nodes on 127.0.0.1/2/3, each from its
own copy of the locally built tree (`/local/c509-n{1,2,3}`), JMX ports 7199/7299/7399.
Per-node yaml: `seeds: 127.0.0.1`, data/commitlog/hints/saved_caches under
`/local/c509-nX/var` (needs ~2 GB per node), `allocate_tokens_for_local_replication_factor` unset,
explicit `initial_token` so the ring is deterministic:
node1 `num_tokens: 1`, `initial_token: -9223372036854775000` (owns the tiny first range only);
node2 and node3 `num_tokens: 24`, tokens evenly spaced over the rest of the ring, alternating
node2/node3 (generate: t_j = -9223372036854775000 + (j+1) * floor(2^64/49) for j=0..47; even j -> node2, odd j -> node3).
Node1 JVM: `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`, G1, `-Xlog:gc*:file=/local/c509-n1/gc.log:time,uptime`,
and `-Dcassandra.max_concurrent_range_requests=C` in `conf/jvm-server.options`.

> **Amendment C1 (2026-10-27, stage-4 audit; replaces the host, paths and heap settings above).** Host: the advisor's Mac
> (`environment-advisor.md`); no `/local`, no Linux. Three nodes from **one** clone `$W/cassandra-run51` (the U1 clone; no `ant` runs
> while a node is up), each with its own `CASSANDRA_CONF` copy and files under `$W/node-rng<N>/` (`conf`, `data`, `commitlog`, `hints`,
> `saved_caches`, `cdc_raw`, `logs`), listen and rpc address `127.0.0.<N>`, JMX 7199 / 7299 / 7399 (`JMX_PORT` in each copy of
> `cassandra-env.sh`), `cluster_name: 'rng'`, `seeds: "127.0.0.1:7000"`, **`auto_bootstrap: false`** (bootstrap streaming fails on this host;
> with explicit tokens nothing needs streaming), `allocate_tokens_for_local_replication_factor` removed, `num_tokens`/`initial_token` as C2.
> Nodes start as tracked background processes (`bin/cassandra -f > log 2>&1 < /dev/null`; no `setsid`). Node 1: `MAX_HEAP_SIZE=4G
> HEAP_NEWSIZE=800M` (G1 from `jvm11-server.options:63`), `JVM_EXTRA_OPTS` scoped to its command with
> `-Xlog:gc*:file=$W/node-rng1/gc-b3.log:time,uptime` and the C5 Byteman agent; the property `-Dcassandra.max_concurrent_range_requests=C`
> is appended to node 1's copy of `conf/jvm-server.options` (and absent for the default). Nodes 2 and 3: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`
> (not measured; left unset, `cassandra-env.sh` would give each 8 GiB, pre-touched, beside node 1's 4 GiB on a 32 GiB host).

> **Amendment 2026-10-27 (after run 1, authorised by the user) — B3a.** This amendment and the four below (B3c, B3f, B3g, B3h) **follow run 1's
> cluster readings** (results §4: the uncapped controls were bounded by the replicas' outbound queues to node 1, and P4's L band was exceeded).
> The user (Yang, the advisor) authorised them and a re-run of the whole cluster tier on 2026-10-27. The re-run uses a **fresh clone**
> `$W/cassandra-run68` (`git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run68`, `ant -Dlocal.repository=$W/m2 build-test`) in
> place of `$W/cassandra-run51`; node files, ports, heaps, ring, Byteman probe and the other C1 settings are unchanged. Raw logs go to
> `$W/logs/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned/cluster-run2/` (shakedown `cluster-run2-shake/`).


> **Amendment C2 (2026-10-27, stage-4 audit; the filed ring gives node 1 data).** The range that wraps past the largest token belongs to
> the owner of the first token, and the full-ring scan's last sub-range (t_47, MIN] is served by node 1. With
> t_j = n1 + (j+1)·⌊2^64/49⌋, t_47 = n1 + 48·⌊2^64/49⌋, so node 1 would own about 1/49 of the ring (≈ 5,900 of the 288,000 rows): its
> local estimate would not be 0 (`RangeCommands.java:90-96`), the first batch would not be a single empty range, and B3c's chain to
> `:162` breaks. **Fix:** node 1 `num_tokens: 1`, `initial_token: -9223372036854775000` (as filed); node 2 and node 3 `num_tokens: 24`,
> t_j = n1 + (j+1)·s for j = 0..47 with s = ⌊((2^63 − 1 − 808) − n1)/48⌋ = 384307168202282291 (even j → node 2, odd j → node 3), so
> t_47 = 9223372036854774968. Node 1 owns only (MIN, n1] (808 tokens) and (t_47, MIN] (839 tokens); the expected number of the 288,000
> keys in them is ≈ 2.5·10^-11. The full scan has **50** sub-ranges: empty (node 1, local), 48 dense (alternating node 2 / node 3, so RF 1
> plans never share an endpoint and `ReplicaPlans.maybeMerge` cannot merge them, `ReplicaPlans.java:774-793`), empty (node 1). Each
> dense range expects 288,000/48 = 6,000 keys (σ ≈ 77), more than the 5,000-row page.

**B3b. Knobs.** C in {1, 4, 16, 48} on node1 only (coordinator); restart node1 between values.
48 >= the 48 dense ranges = effectively uncapped (control).

> **Amendment C3 (2026-10-27, stage-4 audit; group A: the default was missing).** C ∈ {1, 4, 16, 48, **default**}, in that order, one
> node-1 lifetime per value. Default = property absent = 10 × 10 processors = **100** (`RangeCommands.java:54`, `FBUtilities.java:135,150`;
> `conf/jvm-server.options:41` leaves `cassandra.available_processors` commented). C = 48 and the default are both uncapped controls (48
> ≥ the 48 dense ranges; 100 ≥ 49 remaining sub-ranges). The knob is read back per query by the C5 probe (reflection on the field). The
> B3h `fetch_size=500` re-run is done in the C = 48 lifetime, after its main queries. The optional B3e step 3 (512 MB heap stress) is
> **not run**: it is optional and no B3g row reads it.

**B3c. Workload.** Keyspace `rng` with SimpleStrategy RF=1; `CREATE TABLE rng.t (k bigint PRIMARY KEY, pad blob)`.
Load with the Python driver: 288,000 rows (k random 64-bit, `pad` 2 KiB random), CL ONE.
Keys land ~6000 per node2/node3 range; node1's range (~800 tokens wide) gets ~0. Disk ~600 MB total.
`nodetool flush` on node2/3. Node1 has no sstables -> estimate 0 -> first batch = 1 range =
node1's empty range -> `liveReturned==0` -> next batch = min(C, 48) ranges (target `:162`).
With RF=1, adjacent ranges have disjoint replicas so the merger does not combine them
(`ReplicaPlans.java:774-793`). Query: driver pinned to 127.0.0.1 (`WhiteListRoundRobinPolicy`),
`SELECT * FROM rng.t` at CL ONE, `fetch_size=5000`, read only the first page, then discard.
Per dense response: 5000 rows x ~2 KiB = ~10 MB. Expected buffered in the burst batch:
min(C,48) x ~10 MB (C=48 -> ~480 MB). Run the first-page query 20 times per C, serially, 2 s apart.

> **Amendment C4 (2026-10-27, stage-4 audit; exact workload and client).** Client: the bundled Python driver
> (`lib/cassandra-driver-internal-only-*.zip`), protocol 5, `WhiteListRoundRobinPolicy(['127.0.0.1'])`, `token_metadata_enabled=False`,
> heartbeat off, `FallthroughRetryPolicy`, request timeout 60 s, connection retried on ENOBUFS. Schema as filed. Load: 288,000 distinct
> keys from `random.Random(20261027).getrandbits(64) − 2^63`, `pad = os.urandom(2048)`, prepared INSERT at CL ONE, concurrency 64, six
> chunks of 48,000; 0 errors required. Then `nodetool flush rng` on all three nodes; node 1's `tablestats rng.t` must show SSTable count 0
> (validity: node 1 holds none of the data). Query: `SimpleStatement("SELECT * FROM rng.t", fetch_size=5000)` at CL ONE; only the first
> page is read (`ResultSet.current_rows`, which must hold exactly 5,000 rows; 500 for the B3h control); no second page is fetched.
> Per value: one traced query, then 20 plain queries 2 s apart, then 3 GC-mode queries (C5); for C = 48 then 20 queries at `fetch_size=500`.

> **Amendment 2026-10-27 (after run 1, authorised by the user) — B3c (page size).** Follows a run-1 reading: at C = 48 and the default each
> replica dropped every response beyond about 13 ("overloaded; dropping 9.908MiB message"), so the uncapped controls showed the replicas'
> queue limit, not the knob. **`fetch_size=5000` becomes F = `1000`** (traced, plain and GC-mode queries) and the B3h control's 500 becomes
> **100**; each first page must hold exactly 1,000 (100) rows. N, keys, rows, ring, values and the C6 sequence are unchanged. Derivation, from
> source only:
> (i) *Replica queue.* A replica enqueues each response on its connection to node 1 (`OutboundConnection.enqueue`, `OutboundConnection.java:325-347`);
> `acquireCapacity` (`:383-440`) admits it within the connection's 4 MiB (`internode_application_send_queue_capacity`, `Config.java:250`) plus the
> endpoint reserve of 128 MiB (`…_send_queue_reserve_endpoint_capacity`, `Config.java:252`; global reserve 512 MiB, `:254`; `conf/cassandra.yaml:1386-1388`
> leaves all three at their defaults) and otherwise drops it (`onOverloaded`, `:344`, `:456-468`). A message larger than `LARGE_MESSAGE_THRESHOLD`
> = 65,536 − 21 = 65,515 B (`OutboundConnections.java:61-70`, `CassandraRelevantProperties.java:388`) goes on the large-message connection
> (`OutboundConnections.java:215-228`), whose delivery takes one message at a time (`LargeMessageDelivery.doRun`, `OutboundConnection.java:966-970`)
> and releases its capacity only after the whole message is written (`:991`). So a replica can hold at most Q = 4 MiB + 128 MiB = 138,412,032 B
> queued for node 1, and in the worst case all of one batch's responses from that replica are queued at the same time.
> (ii) *Requests per replica.* In the C2 ring the 48 dense sub-ranges alternate node 2 / node 3, so an uncapped batch (C = 48, default) sends 24
> requests to each replica (the default's 49th sub-range is node 1's empty local range).
> (iii) *Response size.* One dense response is at most r_max = F × 2,200 B (C7) plus its ReadResponse framing (two vint-length buffers and a
> boolean, `ReadResponse.java:324-340`) and message header, bounded here by 1,024 B. Requiring that 24 queued responses use at most half of Q —
> the margin that keeps the uncapped control well under the limit — gives 24 × (2,200 F + 1,024) ≤ 69,206,016 B, i.e. F ≤ 1,310. **F = 1,000**:
> 24 × 2,201,024 = 52,824,576 B = 38 % of Q per replica, 105.6 MB over both replicas, below each replica's 512 MiB global reserve and below
> node 1's inbound limits (4 MiB + 128 MiB per peer, 512 MiB global, `Config.java:257-261`, `AbstractMessageHandler.java:420-450`), so the
> coordinator's inbound side cannot hold a replica's queue full either.
> (iv) *Same path otherwise.* Each dense sub-range expects 6,000 keys (σ ≈ 77, C2), far above 1,000, so every dense response holds exactly F rows
> (the command limit per sub-range, `RangeCommands.java:60`). The control's responses (≥ 100 × 2,048 = 204,800 B) stay above 65,515 B, so main
> and control responses use the same large-message connection. A response array of at most 2,200,016 B (with its 16-B header) is below half
> of node 1's 16 MiB G1 region (`conf/jvm11-server.options:66`), so it is not a humongous object (B3f amendment).
> The decision to change the page follows the run-1 drops; the value 1,000 comes from (i)–(iii), not from any run-1 count.

**B3d. Observables and instruments.** Node1: (1) live heap peak per query from
`jstat -gc <pid1> 50` (max of EU+S0U+S1U+OU minus idle baseline) and gc.log pause-before
sizes; (2) old-gen promoted bytes per run from gc.log; (3) internode received bytes:
JMX `org.apache.cassandra.metrics:type=InternodeInbound,scope=127.0.0.2_7000,name=ReceivedBytes`
(and .3) before/after each run; (4) with `TRACING ON` in cqlsh for one run per C, the line
"Submitted N concurrent range requests" (`RangeCommandIterator.java:250`) for the second batch.
Not directly observable: retained bytes per response; (1) is an upper envelope including garbage.

> **Amendment C5 (2026-10-27, stage-4 audit; instruments that can see the quantity).** (1) `jstat` cannot attach on this host (the node
> runs with `-XX:+PerfDisableSharedMem`, `jvm-server.options:137`), and a 50-ms heap envelope under G1 with a young generation of at
> least half the heap (`jvm11-server.options:70`) sums all allocation since the last young GC, not a per-query peak. **Replaced** by an
> observe-only Byteman probe on node 1 (`rng.btm` + helper `stage4/rng/RngProbe.java` on the system class path), per query of table
> `rng.t`: a `BATCH` line per `sendNextRequests` (at entry: `concurrencyFactor`, `maxConcurrencyFactor`, `rangesQueried`,
> `liveReturned`, `totalRangeCount`; the number of `query()` calls and their vnode count; `rangesQueried` at exit); a `RESP` line per
> `ReadCallback.onResponse` (sender, and the length of the heap array behind the response's `data` buffer — the serialized rows the
> resolver holds, `ReadResponse.java:228`, a fresh array per response, `ByteBufferUtil.java:444-451`; whether it arrived before or after
> the read's `close()`); a `CLOSE` line at `RangeCommandIterator.close()` with **H** = bytes of the responses delivered before close
> (still referenced through the batch's `SingleRangeResponse`/`DataResolver` list at that point), and the knob read back. **R_total** =
> bytes of all responses of the query. **GC mode** (a flag file; 3 queries per value): at the query's first `sendNextRequests` and at
> `close()` the helper takes an in-process `GC.class_histogram` (DiagnosticCommand; a full GC, live objects only) and records its total:
> **L** = live(close) − live(start); `H_end` = H when the second histogram returns. (2) gc.log promotion: kept as a file only (not a row).
> (3) The inbound MBean is `org.apache.cassandra.metrics:type=InboundConnection,scope=127.0.0.<2|3>_7000,name=ReceivedBytes`
> (`InternodeInboundMetrics.java:53,65`; not `type=InternodeInbound`), attribute `Value`, read with a small JMX client before and after the
> 20 plain queries; on nodes 2 and 3 `type=Connection,scope=127.0.0.1_7000,name=LargeMessageDroppedTasks` before and after each value
> (a replica's outbound reserve drops an over-capacity message, `OutboundConnection.java:335-344`). (4) The trace is taken with the
> driver (`trace=True`, same `fetch_size`; cqlsh pages at 100 rows), events from `system_traces.events`: "Didn't get any response rows;
> new concurrent requests: N" (`:165`, the target branch) and "Submitted N concurrent range requests" (`:250`).

**B3e. Procedure.** 1) start nodes in order, wait `nodetool status` UN x3, load, flush.
2) For each C: set the property, restart node1, wait UN; record idle baseline (jstat 30 s);
run one traced query; start jstat and run 20 first-page queries; record (1)-(3); stop jstat.
3) Optional stress for binding: node1 `MAX_HEAP_SIZE=512M`, run 8 concurrent first-page queries
for C=4 and C=48; record GC time and any `OutOfMemoryError`/read timeouts. 4) Shut down (B4).

> **Amendment C6 (2026-10-27, stage-4 audit; exact sequence).** 1) Checks: no Cassandra daemon, ports 7000, 7199, 7299, 7399, 9042, 9091
> free, `127.0.0.2`/`.3` on `lo0`; Byteman rules type-checked with `TestScript`. Start node 1, then 2, then 3; wait for 3 × `UN` and binary
> running; schema; load; flush; node-1 tablestats check. 2) For each value of C3: stop node 1 (`nodetool stopdaemon`), set or remove the
> property, start it, wait for 3 × `UN` from node 1 and binary running, sleep 10 s; the traced query (events read after 5 s); dropped-task
> counters on nodes 2/3; ReceivedBytes; 20 plain queries 2 s apart; 2 s; ReceivedBytes; 3 GC-mode queries 5 s apart; dropped-task counters;
> (C = 48: ReceivedBytes, 20 queries at `fetch_size=500`, ReceivedBytes). 3) Collect logs, stop nodes 3, 2, 1, check no daemon, record and
> remove `$W/node-rng*`. The run script is `harness/…/cluster-run.sh <label>`.

**B3f. Predictions.** Trace: second batch "Submitted min(C,48) concurrent range requests" (C=1:1,
4:4, 16:16, 48:48). ReceivedBytes per query ~ min(C,48) x 10 MB (+ the empty first range). Peak
heap above baseline per query: C=1 ~10-30 MB, C=4 ~40-100 MB, C=16 ~160-400 MB, C=48 ~480 MB-1.2 GB
(factor 1-2.5 for deserialization/copies); monotone in C. Stress at 512 MB heap: C=4 completes,
C=48 shows heavy GC or OOM/timeouts.

> **Amendment C7 (2026-10-27, stage-4 audit; predictions in the C5 instruments' units, derived from source before any reading; replace the
> heap bands above, which were for the jstat envelope).** Let r_min = 5000 × 2048 = 10,240,000 B and r_max = 5000 × 2200 = 11,000,000 B
> bound one dense response's data array (5,000 single-row partitions with a 2,048-B `pad` and well under 152 B of key, header, row and cell
> framing each); empty local responses are ≤ 4,096 B. With 50 sub-ranges and an empty first batch (C2), every query has **exactly two
> batches**: batch 1 with `concurrencyFactor` 1, one request, `liveReturned` 0; batch 2 with `concurrencyFactor` = requests = n2 and
> remaining sub-ranges 49 − n2 after it:
>
> | C | `maxConcurrencyFactor` | n2 (requests in batch 2) | remaining after batch 2 | responses per query | dense responses |
> |---|---|---|---|---|---|
> | 1 | 1 | 1 | 48 | 2 | 1 |
> | 4 | 4 | 4 | 45 | 5 | 4 |
> | 16 | 16 | 16 | 33 | 17 | 16 |
> | 48 | 48 | 48 | 1 | 49 | 48 |
> | default (100) | 50 | 49 | 0 | 50 | 48 |
> | 48, `fetch_size=500` | 48 | 48 | 1 | 49 | 48 (each 500 rows) |
>
> **(P1)** Trace of the traced query: "Didn't get any response rows; new concurrent requests: n2" and "Submitted n2 concurrent range
> requests" for batch 2 (and "Submitted 1" for batch 1). **(P2)** Every dense response's array ∈ [r_min, r_max] (control: [r_min/10, r_max/10]),
> so R_total per query ∈ dense × [r_min, r_max] + ≤ 2 × 4,096 B. **(P3)** ReceivedBytes per plain query (sum over peers .2 and .3, Δ/20)
> ∈ [R_remote, 1.01 × R_remote + 65,536 B], with R_remote the probe's mean remote bytes per query (message framing and gossip). **(P4)**
> Retained: r_min ≤ H ≤ dense × r_max + 8,192 B in every query; for C = 48 and the default, the largest H of the 20 plain queries exceeds
> 16 × r_max = 176,000,000 B (retained beyond anything a C = 16 batch can hold); in each GC-mode query H − 16 MiB ≤ L ≤ H_end + 32 MiB (the
> 5,000-row page built from the first response, ≤ 5000 × 2.5 KiB, and the G1 reading slack). **(P5)** Control: R_total(500)/R_total(5000)
> at C = 48 ∈ [r_min/(10 r_max), r_max/(10 r_min)] = [0.0931, 0.1074]. **(P6)** No dropped large message on nodes 2/3 and 1 + n2
> responses delivered per query. The filed heap bands (C = 1 ~10–30 MB … C = 48 ~480 MB–1.2 GB) are kept only as an informational
> comparison with R_total, not as a row condition.

> **Amendment 2026-10-27 (after run 1, authorised by the user) — B3f (C7 numbers with F = 1,000; P4's L band).** Follows run-1 readings: P5
> failed through the drops, and in GC mode L exceeded H_end + 32 MiB in 8 of 15 reads.
> (1) *Numbers with F = 1,000 (B3c amendment).* r_min = 1,000 × 2,048 = 2,048,000 B and r_max = 1,000 × 2,200 = 2,200,000 B; control
> (`fetch_size=100`) [204,800, 220,000] B. The n2 table, P1, P2's and P4's per-query relations, P3 and P6 are unchanged in form; P4's "largest H
> of the 20 plain queries at C = 48 and the default exceeds 16 × r_max" now reads > 35,200,000 B; P5's band is unchanged, [0.0931, 0.1074]. The
> informational comparison with the filed heap bands (which assumed 5,000-row pages) is dropped.
> (2) *P4's L band, restated from what the source determines about the heap a response holds.* (a) A response that has arrived but whose
> sub-range the iterator has not reached is held **serialized**: node 1 deserializes the message once, copying the payload's data into a fresh
> array of exactly its length (`ReadResponse.java:338`, `ByteBufferUtil.java:382-388,444-451`); the inbound frames it is read from are off-heap
> networking-pool buffers (`BufferPoolAllocator.java:70-75`, `AbstractMessageHandler.java:572`, `InboundMessageHandler.java:358-362`);
> `ReadCallback.onResponse` only adds the message to the resolver (`ReadCallback.java:187-211`, `ResponseResolver.java:60-68`), and nothing
> deserializes it before the iterator reaches its sub-range (`SingleRangeResponse.java:58-59`, `ReadResponse.java:248-257`). (b) The one
> consumed response is in addition **deserialized** into the page: each cell value is copied (`AbstractType.java:587`, `ByteBufferAccessor.java:102`)
> and kept in the CQL `ResultSet` until the read returns (`ResultSetBuilder.java:70,126-175`, `ResultSet.java:49,72`): at most F × 2.5 KiB =
> 2,560,000 B (2,064 B for the 2,048-B value array, 24 B for the key array, two 48-B buffers and a two-element row list per row), inside C7's
> 32 MiB. (c) What one `byte[]` adds to the class-histogram total depends on node 1's G1 region size R = 16 MiB (`conf/jvm11-server.options:66`;
> node 1's gc log prints it): an array whose align8(16 + len) lies in [R/2, R] is a humongous object alone in a region, and the histogram counts
> that region's unused tail too, so it adds R; a smaller array adds align8(16 + len). This is the instrument's known answer outside Cassandra
> with node 1's G1 options (`harness/…/HumongousKnownAnswer.java`; `results/…/run1b-cluster/instrument/humongous-known-answer.txt`: a
> 10,389,262-B array adds 16,786,657 B, a 2,200,000-B array 2,209,478 B, per array of eight). Let A(len) be that footprint, H* = Σ A(len) over
> the responses delivered before close and H*_end the same over the first `nend` responses (C5). **Amended P4 (L band):** in each GC-mode query
> H* − 16 MiB ≤ L ≤ H*_end + 32 MiB. With F = 1,000 no response is humongous, so A(len) = align8(16 + len) and the band equals C7's to within
> 16 B per response. The other parts of P4 are unchanged.
> *What was known of run 1 when this was written:* all of results §4–§5 (among them L ≈ 12.4 MB + 1.585 × H_end over the 15 GC-mode reads,
> and the 523 / 524 drops); while looking for the cause of the L excess, the re-run session also read run 1's raw `probe-gc.txt` CLOSE lines
> (each further delivered 10.39-MB response added about 16.8–17.1 MB of L) and node 1's gc log (`Heap region size: 16M`, and the
> `Heap Inspection Initiated GC` full collections). Rule (c) was found because of that reading; its terms come from `jvm11-server.options:66`
> and the known answer, not from run 1's numbers. *Would run 1 pass?* Its 15 GC-mode L readings lie inside the amended L band (its 10.39-MB
> responses count as 16 MiB each), but run 1 would still match C8 row (b) through its drops (P6, P2 and P5 fail at C = 48 and the default), and
> its page size is not the amended F (`results/…/run1b-cluster/selfcheck-known-answer-run1-*.out`).

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| Requests, received bytes and heap peak scale with min(C,48) | claim confirmed: the property governs coordinator heap for range reads |
| Trace shows > C requests in a batch | claim refuted at mechanism level |
| Requests follow C but heap peak flat across C while C=48 control is high only in bytes received | buffering is not on heap (or streamed); cap does not govern heap |
| C=48 control shows no rise vs C=1 | workload did not reach the burst (first range not empty, or merge happened); not confirmed |

> **Amendment C8 (2026-10-27, stage-4 audit; rows read with the C5 instruments, rows added before any reading).** Row 1 ("claim
> confirmed") reads: P1, P2, P3, P4 and P6 hold for every value and P5 for the control, i.e. requests per batch = min(C, 49) exactly,
> response bytes brought into the coordinator heap ∝ the number of dense requests, and the retained peak bounded by C × r_max for each capped
> C while the uncapped controls retain more than any C = 16 read can. Row 2 ("refuted at mechanism level") reads: any batch with more
> requests than n2, or R_total / H above dense × r_max for a capped C. Row 3 is read as: requests and R_total follow C, but in GC mode L
> < H − 16 MiB at C = 48 / default (delivered responses are not retained on heap) → the cap does not govern retained heap: **refuted** for
> the heap part of B1. Row 4 is read as: batch 1 not a single empty request, or n2 at C = 48 ≠ 48 (first range not empty, or a merge) →
> **not confirmed** (workload did not reach the burst). Added: (a) requests, R_total, P3 and L consistent, but the largest H at C = 48
> and at the default ≤ 16 × r_max (the responses arrived after the batch was released) → **not confirmed**: retention not driven past the
> C = 16 level (the cap still bounds the bytes received); (b) a dropped large message or fewer than 1 + n2 responses for a value (P6) →
> another bound (the replica's outbound reserve, A4) acted; that value is **not confirmed**; (c) node 1 holds sstables of `rng.t`, a load
> error, a page ≠ 5,000 (500) rows, or the knob read-back ≠ C → **invalid run**; (d) a probe or JMX error, or a missing `CLOSE` line →
> **instrument failure**, the tier stops (runbook defect); (e) P3 fails while P1/P2 hold → the internode counter disagrees with the probe:
> **not confirmed** until explained.

> **Amendment 2026-10-27 (after run 1, authorised by the user) — B3g (reading order).** No row is changed; the rows are read with the amended
> B3f (row 3's condition is now L < H* − 16 MiB at C = 48 / default). Run 1's conclusion applied the rows without a stated order; the re-run
> reads them in this order and takes the first that applies: (d) instrument failure; (c) invalid (a page ≠ F rows is (c) unless it is a read
> timeout at a value with dropped messages, which belongs to (b)); row 2; row 4; row 3; (b); (a); (e); row 1 (P1–P6 hold for every value and P5
> for the control). If none applies, row 1 is not met and the tier is **not confirmed**.

**B3h. Controls.** C=48 is the positive control (uncapped burst). Re-run C=48 with
`fetch_size=500` to show peak scales with page limit too (confirms per-response size term).
Same data, same coordinator, serial queries, idle baseline per restart.

> **Amendment 2026-10-27 (after run 1, authorised by the user) — B3h.** The control queries use `fetch_size=100` (B3c amendment), still a
> factor 10 below the main page, so P5's band is unchanged; the rest of B3h and C3's placement of the control in the C = 48 lifetime are unchanged.

**B4. Risks and cleanup.** ~2 GB per node on local disk only; delete `/local/c509-*`.
Stop with `nodetool -p <port> stopdaemon` for each node; `pgrep -f CassandraDaemon` and
`pgrep jstat` must be empty. The unit tests start an embedded node inside the test JVM only;
check `pgrep -f RangeCapProbe` afterwards. Nothing added to the shared clone.

> **Amendment C9 (2026-10-27, stage-4 audit; cleanup on this host).** Delete `$W/node-rng*` (sizes recorded first); stop with
> `nodetool -p <port> stopdaemon`; `pgrep -f 'Cassandra[D]aemon'` must be empty; after the unit tier `pgrep -f RangeCapProbe` must be empty
> and the clone's `git status` clean. No `jstat` is started.

## C. Sources read

- src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java
- src/java/org/apache/cassandra/service/reads/range/RangeCommands.java
- src/java/org/apache/cassandra/service/reads/range/ReplicaPlanMerger.java
- src/java/org/apache/cassandra/service/reads/range/ScanAllRangesCommandIterator.java (header)
- src/java/org/apache/cassandra/service/reads/range/SingleRangeResponse.java
- src/java/org/apache/cassandra/locator/ReplicaPlans.java (774-793)
- src/java/org/apache/cassandra/locator/AbstractEndpointSnitch.java (43-55)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (350)
- src/java/org/apache/cassandra/db/filter/DataLimits.java (456-462)
- src/java/org/apache/cassandra/service/StorageProxy.java (2067-2092)
- test/unit/org/apache/cassandra/service/reads/range/RangeCommandsTest.java
- build.xml (testsome target)

## D. Stage-4 feedback

**2026-10-27, advisor-run stage 4 (Claude Opus 5.5, on the advisor's Mac), run 1 at sha256 `4c8138c9…89fb2`:**
unit **Confirmed (B2g row 1, U5/D1) — caps**; cluster **Not confirmed (C8 row (b)) — caps** (requests and response bytes per read for
C ≤ 16). Results:
[`../../stage4-runtime-verification/results/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.md`](../../stage4-runtime-verification/results/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.md).
Unit: `computeConcurrencyFactor(32, 1, C, 5000, 0)` returns C (1 / 4 / 16; the default is 20 in the test JVM, which runs with
`-XX:ActiveProcessorCount=2`). Cluster (3 nodes, node 1 one empty range, 48 dense ranges on nodes 2/3): on the target branch (trace
"Didn't get any response rows; new concurrent requests: N") batch 2 issues exactly C requests (1 / 4 / 16 / 48; 49 at the default 100) and
brings C × 10.39 MB into the coordinator heap (10.4 / 41.6 / 166.2 MB per read for C = 1 / 4 / 16; internode ReceivedBytes agrees); the
bytes held at the read's close never exceed C × 11 MB. The uncapped controls (48, default) did not show an unbounded burst: each replica's
outbound queue to the coordinator (4 MiB + 128 MiB endpoint reserve) dropped every 9.9 MiB response beyond about 13 ("overloaded;
dropping"), 523 / 524 drops and 3 + 2 read timeouts, so on this ring any C above about 26 is bounded by those reserves, not by the knob.
The post-GC live-heap cross-check (P4's L band) was exceeded: about 1.6 bytes of live heap per held response byte. Amendments before
run 1: U1–U5, C1–C9 (default added; the filed ring gave node 1 the wrapping range, fixed; Byteman probe of requests, response bytes and
held bytes plus an in-process post-GC live delta instead of jstat; `InboundConnection` MBean; driver trace) and runbook fix D1. For
stage 3: (1) an uncapped control needs requests per replica × response size below the 132 MiB outbound reserve; (2) the "peak heap" of a
first-page read is timing-dependent (responses arriving after the page is complete are dropped at once), so the cap bounds it from above
rather than fixing it; (3) `liveReturned` is incremented twice per batch (`RangeCommandIterator.java:115` and `:153`), which affects only
the non-zero branch. Commits: none yet (uncommitted on `advisor-run`, after `fa4dc0c`).

**2026-10-27, advisor-run stage 4, cluster re-run (Claude Opus 5.5, on the advisor's Mac), authorised by the user (Yang, the advisor), at
re-frozen sha256 `d0bf9c41…3779`:** cluster **Confirmed (B3g row 1; C8 with the amended B3f, B3g) — caps**. After run 1, five dated
amendments (B3a, B3c, B3f, B3g, B3h) changed the page to 1,000 rows (derived from the replicas' outbound queue, 4 MiB + 128 MiB, so 24
queued responses per replica use 38 % of it), the control page to 100, and restated P4's live-heap band on JVM footprints (responses held
serialized; the consumed one also deserialized; an 8–16 MiB array fills a whole 16 MiB G1 region, `conf/jvm11-server.options:66`, which
explains run 1's ≈ 1.6 B of live heap per held byte). Re-run in a fresh clone (`$W/cassandra-run68`): batch 2 issued exactly C requests on
the target branch (1 / 4 / 16 / 48; 49 at the default), each bringing a 2.078-MB response into node 1's heap (2.08 / 8.31 / 33.25 / 99.74 /
99.74 MB per read; ReceivedBytes agreeing); no message dropped, the uncapped controls received all 48 responses and held up to 51.9 / 41.6 MB
at close (> 35.2 MB, beyond any C = 16 read); L inside the amended band in every GC-mode read; page control ratio 0.1000. Self-check 2,427
checks, 0 failed. Results:
[`../../stage4-runtime-verification/results/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.md`](../../stage4-runtime-verification/results/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.md)
§7. Run 1's verdict and findings (replica queue drops at 10-MB responses; the `liveReturned` double count) are kept. For stage 3: an
uncapped control needs requests per replica × response size under the replica's outbound queue; byte-array heap bands must use the JVM's
footprint (humongous regions under `G1HeapRegionSize=16m`). Commits: none yet (uncommitted on `advisor-run`, after `942f128`).
