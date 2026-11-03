# MAXIMUM_MAXIMUM_NODE_CONNECTIONS (SAI vector `maximum_node_connections` upper bound): verification solution  <!-- file: cases/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`IndexWriterConfig.java:132`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java#L132) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, autonomous stage-3 agent, 2026-10-26 |
| Estimate | `positive`. The check rejects any index whose `maximum_node_connections` (M) is above 512. M is passed to jvector as the graph's maximum degree (`OnHeapGraph.java:114`). The on-disk graph (`TermsData`) stores a fixed-width neighbour list of `maxDegree` ints per vector, and the on-heap graph sizes each node's neighbour set by M. So the cap bounds graph bytes per vector, on heap and on disk. It does not bound the total, which grows with the number of vectors. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `IndexWriterConfig.MAXIMUM_MAXIMUM_NODE_CONNECTIONS = 512`.
- Kind: a hard-coded Java constant ([`IndexWriterConfig.java:38`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java#L38)). It is not settable.
- What it caps: the user-settable per-index option `maximum_node_connections`.
  - Option name: [`IndexWriterConfig.java:37`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java#L37).
  - Default 16: [`IndexWriterConfig.java:39`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java#L39).
  - Set via `CREATE CUSTOM INDEX ... USING 'StorageAttachedIndex' WITH OPTIONS = {'maximum_node_connections': '<n>'}`.
- The option is accepted only when the JVM property `-Dcassandra.sai.vector.allow_custom_parameters=true` is set ([`CassandraRelevantProperties.java:465`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L465), default `false`). The check is at [`IndexWriterConfig.java:120-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java#L120-L121).
- Changing the property needs a restart. The option itself is fixed at index creation.
- Unit: neighbours (graph edges) per vector node.


**Limit type (2026-10-29).** non-config: hard-coded constant. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** The operand is `maximumNodeConnections`, the parsed option value (`IndexWriterConfig.java:125`). It becomes the jvector `GraphIndexBuilder` M (max degree) at `vector/OnHeapGraph.java:110-117`. That M then sizes three things:
- **Heap.** Each graph node's neighbour set during the memtable's life. `builder.addGraphNode` returns the bytes this adds, and `OnHeapGraph.add` counts them into the memtable index's usage (`OnHeapGraph.java:190`).
- **Disk.** The `TermsData` component that `OnDiskGraphIndex.write` produces (`OnHeapGraph.java:346-349`). The file is named `<sstable>-SAI+<ver>+<index>+TermsData.db` (`disk/format/Version.java:138-152`, `IndexComponent.java:51`).
- **Search CPU and heap.** `VectorIndexSegmentSearcher.java:356`.

**A3. Mechanism.**
1. At `CREATE INDEX`, `StorageAttachedIndex.validateOptions` ([`StorageAttachedIndex.java:278`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L278)) calls `IndexWriterConfig.fromOptions`. The same call runs when the index is constructed ([`StorageAttachedIndex.java:200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L200)).
2. `fromOptions` does three things:
   - It rejects vector options on non-vector columns (`:115-116`).
   - It requires the allow-custom property (`:120-121`).
   - It parses the integer (`:125`).
3. At `:132`, the check `maximumNodeConnections <= 0 || maximumNodeConnections > 512` throws `InvalidRequestException` (`:133`), so the index is never created. Occurrence #1 (`<= 0`) is a validity floor. Occurrence #2 (`> 512`) is the cap under test.
4. An accepted M goes into `new GraphIndexBuilder<>(..., M, beamWidth, 1.2f, 1.4f)` ([`OnHeapGraph.java:110-117`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/OnHeapGraph.java#L110-L117)). In jvector 1.0.2:
   - The graph's `maxDegree()` is M.
   - The neighbour overflow factor 1.2 lets a node hold up to about 1.2·M neighbours temporarily during construction.
   - `builder.complete()` ([`OnHeapGraph.java:345`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/OnHeapGraph.java#L345)) prunes back to M.
5. `OnDiskGraphIndex.write` (jvector 1.0.2) writes a header (size, dimension, entry node, maxDegree: 4 ints). Each node record is `ordinal(int) + vector(dim floats) + neighbourCount(int) + maxDegree ints`, with unused slots padded with `-1`. So `TermsData` graph bytes = 16 + N·(8 + 4·dim + 4·M), plus the SAI header and footer (`SAICodecUtils.writeHeader/writeFooter`). This is from memory of the jvector source; **stage 4 must confirm it** with `javap`/sources of `jvector-1.0.2.jar`, see B2e step 1.
6. Bypass and overshoot:
   - The check runs only on new index options. Indexes keep their options from the schema.
   - During construction a node may briefly hold about 1.2·M neighbours (heap only).
   - Compaction rebuilds the graph with the same config, `OnHeapGraph(..., memtable=null)` ([`OnHeapGraph.java:96-99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/OnHeapGraph.java#L96-L99)).

**A4. Other consumers.** Several things use the same heap and disk outside this cap:
- the vectors themselves (4·dim bytes each, on heap in `ConcurrentVectorValues` and on disk in `TermsData`)
- the PQ codebook and codes (`CompressedVectors`)
- posting lists (`PostingLists`)
- the `postingsMap` and `vectorsByKey` maps (`OnHeapGraph.java:105-107`)
- the SSTable itself

The total number of vectors is bounded only by memtable flush thresholds and data size.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/index/sai/cql/VectorTypeTest.java:279-300` (`changingOptionsTest`): options are rejected without the property and accepted with it.
- jvector 1.0.2 is the dependency (`.build/parent-pom-template.xml:1239-1241`).
- The jvector on-disk format is from memory of https://github.com/jbellis/jvector (tag 1.0.2, `jvector-base/.../disk/OnDiskGraphIndex.java`). It was not fetchable in this session and must be confirmed.

## B. Verification solution

**B1. Claim under test.**
- (a) `maximum_node_connections` > 512 is rejected, so no index can be built with M > 512.
- (b) Graph bytes per vector follow M up to that bound: on disk, `TermsData` ≈ N·(8 + 4·dim + 4·M) + constant. So the cap limits per-vector graph disk to 8 + 4·dim + 2048 bytes, and heap per graph node likewise.

The claim is wrong in either of these cases:
- an M > 512 index is created
- `TermsData` size does not grow with M at fixed N, dimension and data

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11 and Ant.
- Set up a local copy of the source: `git clone /Users/yangwang/cassandra-src /tmp/c509 && cd /tmp/c509 && git checkout cassandra-5.0.9`. On the Linux host, use the shared clone path; never build in the shared clone.
- Build with `ant jar build-test`.
- Put the test at `/tmp/c509/test/unit/org/apache/cassandra/index/sai/disk/v1/MaxNodeConnectionsCapTest.java`.
- Run it with `ant testsome -Dtest.name=org.apache.cassandra.index.sai.disk.v1.MaxNodeConnectionsCapTest -Dtest.jvm.args="-Dcassandra.sai.vector.allow_custom_parameters=true"`. If `test.jvm.args` is not honoured, call `System.setProperty` in a `@BeforeClass` before the `IndexWriterConfig` class loads.

> **Amendment B2a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine (`environment-advisor.md`; macOS arm64,
> JDK 11, Ant 1.10.18):
> - The clone is `$W/cassandra-run39` (`W=~/Library/Caches/stage4`), a fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`,
>   built with `ant -Dlocal.repository=$W/m2 build-test` (which includes the jar). `/tmp/c509` is not used.
> - The test is `harness/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/MaxNodeConnectionsCapTest.java`
>   (one `CQLTester` subclass holding Test A and Test B in one `@Test` method, A first). `unit-run.sh` in the same folder copies it to
>   the filed path, runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.index.sai.disk.v1.MaxNodeConnectionsCapTest`
>   (no `-Dtest.jvm.args`), keeps the logs under `$W/logs/<stem>/unit/`, and removes the test and its classes, leaving the clone clean.
> - The property is set by the filed fallback, `System.setProperty("cassandra.sai.vector.allow_custom_parameters", "true")` in a static
>   block. `SAI_VECTOR_ALLOW_CUSTOM_PARAMETERS.getBoolean()` is read on every `fromOptions` call (`IndexWriterConfig.java:120`), not
>   cached, so class-load order does not matter. The first output line reads the property back.

**B2b. Knobs.** M ∈ {16, 64, 256, 512} (accepted), plus 513 and 1024 (expected rejected). 16 is the default and 512 is the boundary.

**B2c. Workload.**
- N = 5000 random float vectors, dim = 8, fixed seed 42, normalised (COSINE needs non-zero vectors).
- With N ≫ M+1, nodes can fill their degree, although padding makes disk size independent of fill.
- Expected graph bytes: 16 + 5000·(8 + 32 + 4M):
  - M=16: 520,016
  - M=64: 1,480,016
  - M=256: 5,320,016
  - M=512: 10,440,016

> **Amendment B2c (2026-10-26, stage-4 audit, before any reading).** Exact workload:
> - Vectors: `new java.util.Random(42)`; each of the 8 components is `nextFloat() * 2 - 1`; each vector is scaled to unit L2 length.
>   The same list (one generation, printed with a checksum) is used for every case.
> - Test B cases (M, `construction_beam_width`): (16, 100), (64, 100), (256, 100), (512, 100), and (16, 400) for the B2h negative
>   control. The graph is built on one thread, `addGraphNode(i, ravv)` for i = 0..4999 in order.
> - Test A: a fresh table per M, so every `CREATE INDEX` is the first index on its column.

**B2d. Observables and instruments.**
- (1) Whether `IndexWriterConfig.fromOptions(name, IndexTermType.create(vectorColumn...), Map.of("maximum_node_connections", "<M>"))` throws `InvalidRequestException`. A simpler way to get a vector term type is a CQL-level `createIndex` in a `SAITester`/`CQLTester` subclass, which also covers the path. Prefer the `CQLTester` route.
- (2) Bytes written by `OnDiskGraphIndex.write(graph, vectors, out)` to a temp file (`Files.size`).
- (3) The sum of the `long` values returned by `GraphIndexBuilder.addGraphNode` over all inserts, which is the heap estimate.
- Not observable here: real heap retained (see B3).

> **Amendment B2d (2026-10-26, stage-4 audit, before any reading).** Output: one stdout line per reading, starting `PROBE `, in
> `build/test/logs/**/TEST-<class>.log`:
> - `PROBE PROP allow_custom_parameters=<bool> MAXIMUM_MAXIMUM_NODE_CONNECTIONS=<int> DEFAULT_MAXIMUM_NODE_CONNECTIONS=<int> N=<n> dim=8`
> - `PROBE A M=<M> result=accepted index=<name>` or `PROBE A M=<M> result=rejected outer=<class> root=<class> msg=<root cause message>`
>   (`CQLTester.schemaChange` wraps the server's `InvalidRequestException` in another one, `CQLTester.java:1503-1508`, so the root cause
>   holds the check's message).
> - `PROBE VECTORS n=<n> checksum=<long>`
> - `PROBE B M=<M> beam=<b> n=<n> dim=8 graphSize=<int> maxDegree=<int> sumAddBytes=<long> fileBytes=<long>
>   maxNeighboursAfterComplete=<int> meanNeighbours=<x> tmpDeleted=<bool>`
> - `PROBE END`
> The test does not assert on readings; the self-check judges them. **Gap:** the heap side in this tier is only jvector's own estimate
> (`sumAddBytes`); retained heap is read in the cluster tier (amendment B3d).

**B2e. Procedure.**
1. `unzip -l ~/.m2/repository/io/github/jbellis/jvector/1.0.2/jvector-1.0.2.jar` (or `build/lib/jars`). Then run `javap -cp <jar> io.github.jbellis.jvector.disk.OnDiskGraphIndex io.github.jbellis.jvector.graph.GraphIndexBuilder` to confirm the signatures `write(GraphIndex, RandomAccessVectorValues, DataOutput)`, `addGraphNode(int, RandomAccessVectorValues)` and `complete()`. If the sources jar is available, confirm the padding to `maxDegree`. Adapt the test calls if the signatures differ.
2. Test A, a `CQLTester` subclass. For each M in {16, 64, 256, 512, 513, 1024}:
   - `createTable("CREATE TABLE %s (pk int PRIMARY KEY, v vector<float, 8>)")`
   - try `createIndex("CREATE CUSTOM INDEX ON %s(v) USING 'StorageAttachedIndex' WITH OPTIONS = {'maximum_node_connections':'" + M + "'}")`
   - record accepted or rejected
3. Test B, plain JUnit. For each accepted M:
   - build `ListRandomAccessVectorValues` of the 5000 vectors
   - `new GraphIndexBuilder<>(ravv, VectorEncoding.FLOAT32, VectorSimilarityFunction.COSINE, M, 100, 1.2f, 1.4f)`
   - for i in 0..4999, sum `addGraphNode(i, ravv)`
   - call `complete()`
   - write with `OnDiskGraphIndex.write(builder.getGraph(), ravv, new DataOutputStream(new FileOutputStream(tmp)))`
   - print `M, sumAddBytes, Files.size(tmp), graph.maxDegree()`
4. Delete the temp files.

> **Amendment B2e (2026-10-26, stage-4 audit, before any reading).** Step 1 was done at the audit with `javap -c -p` on
> `build/lib/jars/jvector-1.0.2.jar` of the run clone (no sources jar is available). The signatures are as filed. The bytecode
> re-trace (A3.4, A3.5 and A5 asked for it) gives four facts:
> - `OnHeapGraphIndex(int M, BiFunction)` stores `nsize0 = 2 * M`, and `maxDegree()` returns `nsize0`. The builder passes the option
>   M to it unchanged. So **the graph's `maxDegree()` is 2·M, not M**.
> - `addNode(node)` creates each node's `ConcurrentNeighborSet` with `maxDegree()` (2·M) as its `maxConnections`, and its first
>   `ConcurrentNeighborArray(2·M)` allocates an `int[2M]` and a `float[2M]` (`NeighborArray(int)`). Later inserts replace that array:
>   `mergeNeighbors` allocates one sized by the two inputs' actual sizes. So retained neighbour arrays follow the actual degree, at most
>   about 2·M (this last sentence was added 2026-10-26 before the freeze, after the cluster shakedown's class histograms showed far less
>   than 16·M B per node; the bytecode confirms it).
> - `OnDiskGraphIndex.write` writes four header ints (size, dimension, entry node, `maxDegree()`), then per node: ordinal (int),
>   the vector (dim floats), the neighbour count (int), the neighbours, and `-1` up to `maxDegree()`. So the graph bytes are
>   **16 + N·(8 + 4·dim + 4·2M)**.
> - `addGraphNode` returns `graph.ramBytesUsedOneNode(0)` = a constant + `neighborsRamUsed(maxDegree())`, and `neighborsRamUsed(d)` =
>   a constant + 8·d. So each added node counts a constant + **16·M** bytes.
> Steps 2 and 3 run in one JVM, by `unit-run.sh` (amendment B2a); step 4 is in the test (`tmpDeleted`).

**B2f. Predictions.**
- Test A: 16, 64, 256 and 512 are accepted. 513 and 1024 are rejected, with the message "cannot be <= 0 or > 512".
- Test B: `maxDegree()` == M. File size equals 16 + 5000·(40 + 4M) exactly (±0). `sumAddBytes` is strictly increasing in M and roughly linear, at a slope of at least 4 bytes per M per node.

> **Amendment B2f (2026-10-26, stage-4 audit, before any reading).** The filed predictions above stay as stage 3's and are judged as
> written. Added, from the bytecode re-trace of amendment B2e (no reading involved), the **re-traced expectations**, which B2g uses to
> name the row:
> - Test A: the rejection's root cause is `InvalidRequestException` with the text `Maximum number of connections for index <name>
>   cannot be <= 0 or > 512, was <M>` (`IndexWriterConfig.java:133`) for M = 513 and 1024. The name is the literal `null`: `CREATE INDEX` validates through
>   `StorageAttachedIndex.validateOptions`, which calls `fromOptions(null, …)` (`StorageAttachedIndex.java:278`). (Corrected 2026-10-26
>   before the freeze and before run 1: this amendment first said "the generated index name"; the unit shakedown printed `null`, and the
>   source line confirms it.)
>   M = 16, 64, 256, 512 are accepted.
> - Test B: `graphSize` = 5000 and `maxDegree()` = 2·M (32, 128, 512, 1024) in every case.
> - `fileBytes` = 16 + 5000·(40 + 8·M) exactly: M=16 **840,016**; M=64 **2,760,016**; M=256 **10,440,016**; M=512 **20,680,016**;
>   (16, 400) **840,016**. So each unit of M adds 40,000 bytes (8·N), not the filed 20,000 (4·N).
> - `sumAddBytes` differences are exactly 5000·16·ΔM: 64 − 16 → **3,840,000**; 256 − 64 → **15,360,000**; 512 − 256 → **20,480,000**.
>   This meets the filed "at least 4 bytes per M per node" (it is 16).
> - `maxNeighboursAfterComplete` ≤ `maxDegree()` (reported).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| 513 rejected, file size matches the formula, increasing in M | Claim confirmed: the cap bounds per-vector graph bytes at the M=512 value |
| 513 or 1024 accepted | Claim wrong: the cap does not bind |
| File size constant across M | Graph disk does not follow M. Claim (b) wrong; the cap is irrelevant to disk |
| Size grows with M but not by 4·N per unit M | Format differs from the trace. Report the actual slope; the claim holds if it is monotone |
| `maxDegree()` ≠ M | The mapping in A3.4 is wrong. Re-trace |

> **Amendment B2g (2026-10-26, stage-4 audit, before any reading).** Verdict words for the rows above, and added rows:
> - Row 1 is **Confirmed**: 16, 64, 256, 512 accepted; 513 and 1024 rejected with the text of amended B2f; `fileBytes` equal to the
>   filed formula; strictly increasing in M.
> - Row 4 is **Confirmed** as well (the filed meaning: "the claim holds if it is monotone"), when 513 and 1024 are rejected as in row 1
>   and `fileBytes` is strictly increasing in M and linear (each step's bytes per unit M equal) at a slope other than 4·N. The results
>   report the slope and whether it is the re-traced 8·N.
> - Rows 2 and 3 are **Refuted**. Row 3 means `fileBytes` at M=512 equals `fileBytes` at M=16.
> - Row 5: the re-trace is the step-0 one of amendment B2e. `maxDegree()` = 2·M, with `fileBytes` at the re-traced value, is part of
>   row 4 and does not by itself change the verdict. `maxDegree()` neither M nor 2·M gives **Not confirmed** (the mapping is unknown).
> - Added, **Not confirmed**: `fileBytes` varies with M but not monotonically, or a step is not linear; or a rejection message other
>   than the check's; or `sumAddBytes` not strictly increasing in M (the heap side of B1(b)).
> - Added, **Invalid**: the property not read back `true`; `graphSize` ≠ 5000; the (16, 400) case differs from (16, 100) in `fileBytes`
>   (the instrument then sees something other than M, B2h); the test errors outside the readings; a probe line missing.
> - **Effect rule:** Confirmed gives **caps** (no index can have M > 512, and graph bytes per vector follow M up to that bound).
>   Refuted gives **does not cap**. Not confirmed and Invalid give **undetermined**.

**B2h. Controls.**
- Same vectors and seed for every M.
- Positive control: going from M=16 to M=512 must move the file size, which shows the instrument sees M.
- Negative control: changing `construction_beam_width` (100 vs 400) at M=16 should not change file size.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, from a build of the local clone (`ant jar`).
- `conf/cassandra.yaml`: `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` under `/tmp/c509-node/` on local disk with at least 5 GB free.
- `conf/jvm-server.options`: add `-Dcassandra.sai.vector.allow_custom_parameters=true`. Keep the heap at the default or set `-Xmx2G`.
- Start with `bin/cassandra -p /tmp/c509-node/pid`.

> **Amendment B3a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine (macOS arm64, not Linux;
> `environment-advisor.md`):
> - The node runs from `$W/cassandra-run39` (amendment B2a; its `build-test` includes the jar, and no test is left in it). Its directory
>   is `$W/node-mnc/{data,commitlog,hints,saved_caches,cdc_raw,logs}` on the internal SSD (not `/tmp/c509-node`), with its own copy of
>   `conf/` (`CASSANDRA_CONF`); `listen_address` and `rpc_address` 127.0.0.1.
> - Heap: `MAX_HEAP_SIZE=2G` (the filed option; the default here would be 16 GiB with `AlwaysPreTouch`). With a 2 GiB heap the default
>   `memtable_heap_space` is 512 MiB and the flush threshold 1/3 of it (`conf/cassandra.yaml:797, 811`), about 171 MiB. The t_512
>   memtable alone is charged about 20,000 × (16·512 + a constant) ≈ 165 MB of graph (`StorageAttachedIndex.java:1007`, amendment
>   B2e), so a flush could split it mid-load. `memtable_heap_space: 1024MiB` is set to keep each table in one memtable.
> - `-Dcassandra.sai.vector.allow_custom_parameters=true` and a GC log are appended to the copy's `jvm-server.options`, and read back
>   from the daemon's command line and the `JVM Arguments` line of `system.log`.
> - There is no `setsid` and `-p` is not used: the node is a tracked background `bin/cassandra -f`, stopped with `nodetool stopdaemon`
>   (then `kill`), and `pgrep` must find no daemon afterwards.

**B3b. Knobs.** One table per M ∈ {16, 128, 512}, plus an attempt at 513.

**B3c. Workload.**
- Keyspace: `CREATE KEYSPACE k WITH replication={'class':'SimpleStrategy','replication_factor':1}`.
- For each M: `CREATE TABLE k.t_M (pk int PRIMARY KEY, v vector<float,8>)`, then the index with `WITH OPTIONS={'maximum_node_connections':'M'}`.
- Insert N = 20,000 rows with random normalised vectors. Use a Python cassandra-driver script with prepared statements, seed 42, and identical data for every table.
- Run `nodetool flush k`. Then run `nodetool compact k` once and measure again.
- Expected `TermsData` ≈ 20,000·(40 + 4M):
  - M=16: 2.08 MB
  - M=128: 11.04 MB
  - M=512: 41.76 MB
- Duration: a few minutes.

> **Amendment B3c (2026-10-26, stage-4 audit, before any reading).**
> - Client: `harness/<stem>/probe.py`, the bundled driver (`lib/cassandra-driver-internal-only-*.zip`), protocol 5,
>   `DCAwareRoundRobinPolicy`, token and schema metadata off.
> - Tables (`pk int PRIMARY KEY, v vector<float,8>`), each with `CREATE CUSTOM INDEX idx_<s> ON k.t_<s>(v) USING 'StorageAttachedIndex'
>   WITH OPTIONS = {...}`: `t_16`, `t_128`, `t_512` (`maximum_node_connections` 16, 128, 512); `t_16b400` (16, with
>   `construction_beam_width` 400; the B3h negative control, which the filed knobs did not include); `t_513` (513, the rejected attempt;
>   it gets no data).
> - Data: for every table the same 20,000 rows, pk 0..19,999; v = 8 values `random.Random(42).uniform(-1, 1)`, scaled to unit length
>   (re-seeded per table). Prepared INSERT, concurrency 8: jvector's builder pool allows `availableProcessors() + 1` = 11 concurrent
>   memtable inserts on this 10-core host (`PoolingSupport$ThreadPooling`, read with `javap`), and the filed text gives no concurrency.
> - Order, per loaded table in the order t_16, t_128, t_512, t_16b400: class histogram, load, class histogram, `count(*)`, tablestats,
>   `nodetool flush k <table>`, file sizes. The filed single `nodetool flush k` after all loads becomes one flush per table, so each
>   table's memtable is measured alone and is one SSTable. Then `nodetool compact k`, a wait until `compactionstats` shows no pending
>   or active task, and the file sizes again.
> - Arithmetic, re-traced (amendment B3f): TermsData 3.4, 21.3 and 82.7 MB; all data well under 1 GB; heap 2 GiB.

**B3d. Observables and instruments.**
- `ls -l /tmp/c509-node/data/k/t_*/*TermsData.db` after each flush and after compaction.
- `nodetool tablestats k` for SSTable and space used (also the memtable off/on-heap size before the flush).
- cqlsh output of the 513 attempt.
- Heap: `jcmd <pid> GC.class_histogram` before the flush. Optional; graph neighbour arrays are hard to attribute.

> **Amendment B3d (2026-10-26, stage-4 audit, before any reading).**
> - File sizes: `harness/<stem>/files.py` sums `os.stat` sizes per SAI component (`<sstable>-SAI+<ver>+idx_<s>+<Component>.db`)
>   over the table's live SSTables, and prints the SSTable count, the generations and each SSTable's TermsData size.
> - tablestats lines: SSTable count, Space used (live), Memtable cell count, Memtable data size, Memtable off heap memory used.
> - The 513 attempt: the driver's exception text (cqlsh is not used). Accepted options are read back from `system_schema.indexes`.
> - Heap: `jcmd <pid> GC.class_histogram` (a full GC; live objects only) before and after each table's load. Reported: the `Total`
>   bytes and the `[I` and `[F` bytes, with their change over the load. Not a verdict condition. For context: the memtable is
>   charged 16·M B per node for the neighbour set (`addGraphNode`, amendment B2e), but the arrays retained follow the actual degree,
>   at most about 2·M (amendment B2e), so no heap floor in M is derived. (Corrected 2026-10-26 before the freeze: this amendment first
>   gave a floor of 20,000 × 16·M B, which the cluster shakedown's histograms and the `mergeNeighbors` bytecode contradict.)

**B3e. Procedure.**
1. Start the node and wait for `nodetool status` to show UN.
2. Create the keyspace, the tables and the indexes. Record whether the M=513 index is rejected.
3. Load the data, run `nodetool flush k`, and record the file sizes.
4. Run `nodetool compact k` and record again.
5. Optionally, restart without the `-D` property and confirm that `'maximum_node_connections':'16'` is now rejected.

> **Amendment B3e (2026-10-26, stage-4 audit, before any reading).** One script, `harness/<stem>/cluster-run.sh`, runs steps 1–4 in the
> order of amendment B3c in one node lifetime, logs every command to `$W/logs/<stem>/cluster/commands.log` and writes `summary.txt`.
> It wipes `$W/node-mnc` before and after. Optional step 5 is not run: on a restart without the property, the existing indexes would
> go through `IndexWriterConfig.fromOptions` again in the `StorageAttachedIndex` constructor (`StorageAttachedIndex.java:200`), which
> asks a different question (left for stage 3).

**B3f. Predictions.**
- The M=513 `CREATE INDEX` fails with `InvalidRequest` ... "cannot be <= 0 or > 512".
- `TermsData` sizes are within ±1% of 20,000·(40 + 4M) plus less than 1 KB of header and footer, with the ordering M16 < M128 < M512.
- Other SAI components (`PostingLists`, `CompressedVectors`) are about the same across M (within ±5%).

> **Amendment B3f (2026-10-26, stage-4 audit, before any reading).** The filed predictions stay as stage 3's and are judged as written
> (sizes from the after-flush listing; the after-compaction listing is judged the same way). Added, from the re-trace of amendment B2e
> (no reading involved), the **re-traced expectations**:
> - idx_513: the driver raises `InvalidRequest` with `Maximum number of connections for index null cannot be <= 0 or > 512, was 513`
>   (`IndexWriterConfig.java:133`, with `null` from `StorageAttachedIndex.java:278`; corrected before the freeze, see amendment B2f). idx_16, idx_128, idx_512 and idx_16b400 are created, and `system_schema.indexes` shows their options.
> - Each loaded table: load 20,000 ok, `count(*)` 20,000, one SSTable after its flush.
> - TermsData per table, one segment = SAI header 7 B (`CODEC_MAGIC` + `writeString("aa")`) + graph 16 + 20,000·(40 + 8·M) + footer 16 B
>   (`SAICodecUtils.java:47-58, 261-269`): t_16 **3,360,039**; t_128 **21,280,039**; t_512 **82,720,039**; t_16b400 **3,360,039**
>   (equal to t_16). The step per unit M is 160,000 B (8·N), not the filed 80,000 B (4·N). After compaction the same values (one segment:
>   the default `segment_write_buffer_size` is 1024 MiB, `StorageAttachedIndexOptions.java:26`).
> - PostingLists and CompressedVectors of t_128, t_512 and t_16b400 within ±5% of t_16's.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| 513 rejected; `TermsData` scales as 4·N·M | Confirmed: per-vector graph disk is capped at the M=512 level |
| 513 accepted | Claim wrong |
| `TermsData` the same across M | Disk does not follow M. Claim wrong |
| Sizes differ but not linearly | Format differs. Report it; the claim holds if monotone and bounded at 512 |

> **Amendment B3g (2026-10-26, stage-4 audit, before any reading).** Verdict words for the rows above, and added rows, judged on the
> after-flush listing and again on the after-compaction listing (both must give the same row):
> - Row 1 is **Confirmed**: idx_513 rejected with the check's message; the four other indexes created; TermsData within the filed ±1%
>   of 20,000·(40 + 4M) plus < 1 KB, ordered t_16 < t_128 < t_512.
> - Row 4 is **Confirmed** as well (the filed meaning: "the claim holds if monotone and bounded at 512"), when idx_513 is rejected as in
>   row 1 and TermsData is strictly increasing t_16 < t_128 < t_512 but off the filed formula. This also covers sizes that are linear
>   in M at a slope other than 4·N (a format that differs from the trace). The results report the slope per unit M and whether the
>   sizes equal the re-traced values of amendment B3f.
> - Rows 2 and 3 are **Refuted**. Row 3 means t_512's TermsData within 1% of t_16's.
> - Added, **Not confirmed**: TermsData not monotone in M; t_16b400's TermsData more than 1% from t_16's (B3h's control: then beam
>   width, not only M, moves the file); PostingLists or CompressedVectors of a table more than 5% from t_16's (the data or the other
>   consumers differ between tables, so the sweep is not clean); the after-flush and after-compaction listings giving different rows.
> - Added, **Invalid**: the property not read back; a load with failures or a `count(*)` other than 20,000; a table with no TermsData;
>   the node dying, or an `OutOfMemoryError`.
> - **Effect rule:** Confirmed gives **caps**; Refuted gives **does not cap**; Not confirmed and Invalid give **undetermined**.

The positive control is the M sweep itself, together with the PostingLists and CompressedVectors components staying flat.

**B3h. Controls.**
- Identical data and seed for every table.
- The single flush gives one segment per table. If there are several SSTables, sum the files.
- Compare the files after compaction too.
- Varying beam width only (negative control) should not change `TermsData`.

> **Amendment B3h (2026-10-26, stage-4 audit, before any reading).** The beam-width control is table `t_16b400` (amendment B3c),
> loaded with the same rows and judged in B3g. Each table is flushed alone after its load (amendment B3c), so the "several SSTables"
> case should not arise; if it does, the sizes are summed as filed and the count is reported.

**B4. Risks and cleanup.**
- Total disk is under 1 GB.
- All paths are under `/tmp/c509*` on local disk.
- Stop the node with `kill $(cat /tmp/c509-node/pid)` and confirm with `pgrep -f CassandraDaemon` (no output).
- Remove `/tmp/c509-node`, and `/tmp/c509` when done.
- The unit tier leaves only temp files, deleted in step 4.

> **Amendment B4 (2026-10-26, stage-4 audit, before any reading).** Paths on this host: node `$W/node-mnc` (wiped by the script before
> and after), clone `$W/cassandra-run39` (left in place, `git status` clean), logs `$W/logs/<stem>/`. Stop and check as in amendment B3a
> (`pgrep -f` for the daemon class, no output). The unit tier's temporary graph files are deleted by the test (`tmpDeleted`), and
> `unit-run.sh` counts any left.

## C. Sources read

- src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java
- src/java/org/apache/cassandra/index/sai/disk/v1/vector/OnHeapGraph.java (90-200, 300-360)
- src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java (grep: 200, 278)
- src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java:356 (grep)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:465, 479
- src/java/org/apache/cassandra/index/sai/disk/format/IndexComponent.java, Version.java (grep)
- test/unit/org/apache/cassandra/index/sai/cql/VectorTypeTest.java:270-300
- .build/parent-pom-template.xml:1235-1245
- https://github.com/jbellis/jvector/tree/1.0.2 (not fetched; recalled, to be confirmed in stage 4)

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1** (Claude Opus 5.5, claude-opus-5-5[1m], on the advisor's machine; results
[`../../stage4-runtime-verification/results/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous.md`](../../stage4-runtime-verification/results/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous.md);
frozen at sha256 `f60348fb…336d` after fourteen audit amendments; uncommitted):
- **Unit: Confirmed — caps** (B2g row 4). M = 513 and 1024 refused with `Maximum number of connections for index null cannot be <= 0
  or > 512, was <M>`; jvector graph file 840,016 / 2,760,016 / 10,440,016 / 20,680,016 B at M = 16 / 64 / 256 / 512 (N = 5000, dim 8),
  linear at 8·N per unit M; beam 400 unchanged.
- **Cluster: Confirmed — caps** (B3g row 4). idx_513 refused; TermsData 3,360,039 / 21,280,039 / 82,720,039 B at M = 16 / 128 / 512
  (20,000 vectors), the same after a major compaction; the beam-400 table, PostingLists and CompressedVectors unchanged.
- **For stage 3:** A3.4/A3.5 and B1 have the degree wrong by a factor of 2. jvector 1.0.2's `OnHeapGraphIndex` sets `maxDegree()` =
  2·M (`nsize0 = 2 * M`), so `TermsData` = 16 + N·(8 + 4·dim + 8·M) plus the SAI header and footer (23 B), and the per-vector graph
  disk bound at M = 512 is 8 + 4·dim + 4096 B, not + 2048. The filed row 4 ("the claim holds if monotone") named this outcome.
- **Heap:** B1(b)'s "heap per graph node likewise" holds only as a bound. Retained neighbour arrays are re-sized to the actual degree
  (`ConcurrentNeighborSet.mergeNeighbors`), which for these data stopped growing above M ≈ 128 (class histograms: 10.2, 33.8, 36.2 MB
  of `int[]` + `float[]` for 20,000 nodes at M = 16, 128, 512), while the memtable is charged 16·M B per node (`addGraphNode`).
  The rejection message names the index `null` (`StorageAttachedIndex.java:278`). Not tested: the 1.2·M construction overflow, and a
  restart without the property (B3e step 5).
