# dfs.journalnode.edit-cache-size.bytes — verification solution  <!-- file: cases/dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`JournaledEditsCache.java:283`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/server/JournaledEditsCache.java#L283) — `if (inputData.length > capacity)` in `JournaledEditsCache.storeEdits`; it works together with the eviction loop one block above it, [`JournaledEditsCache.java:278`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/server/JournaledEditsCache.java#L278) `while ((totalSize + inputData.length) > capacity && !dataMap.isEmpty())`, which is the main cumulative enforcement point (same method, same operand) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — the JournalNode's in-memory edits cache (one per journal ID) keeps the sum of the cached `byte[]` payload lengths at or below `capacity`: oldest batches are evicted first (`:278`), and a batch larger than `capacity` empties the cache and is not stored (`:283`). Caveats that stage 4 should test: per-entry object overhead is not counted, each journal ID gets its own full `capacity`, and when `capacity` is at or near `Integer.MAX_VALUE` (the default on a JournalNode heap above about 4 GiB) the `int` sum at `:278` overflows and eviction stops. |
| Ground | — |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Other citations are plain `file:line`, relative to the source root.

Naming: constraint `dfs.journalnode.edit-cache-size.bytes` (the key that sets the limit when it is set; the fraction key is the other source, see A1); function `storeEdits` (directly encloses `:283`); operand `capacity` (the limit-side operand at `:283`, written exactly that way).

## A. Constraint trace

**A1. The constraint.**

- **Name:** `dfs.journalnode.edit-cache-size.bytes`. **Kind:** configuration key (HDFS, read by the JournalNode).
- **Declared:** [`DFSConfigKeys.java:1469-1470`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L1469-L1470) (`DFS_JOURNALNODE_EDIT_CACHE_SIZE_KEY`). No Java default constant exists for it.
- **Second source (derived default):** `dfs.journalnode.edit-cache-size.fraction`, [`DFSConfigKeys.java:1472-1474`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L1472-L1474), Java default `0.5f`; `hdfs-default.xml:5062-5076`, value `0.5f` (same).
- **`hdfs-default.xml` entry:** `hdfs-default.xml:5050-5060`, `<value></value>` (empty). Its description says "the default of 1MB can store around 5000 transactions"; that text is stale. An empty `<value>` is not stored as a property (`Configuration.java:3382-3385` sets `confValue` only when the token is non-empty), so `conf.getInt` sees `null` and uses the code default. `ObserverNameNode.md:184-195` shows `1048576` as an example value, not as the default.
- **Unit:** bytes (`int`).
- **Default and how it is derived:** `JournaledEditsCache.java:125-132`: `fraction = conf.getFloat(fraction key, 0.5f)`, checked `0 < fraction < 1` (`:127`, startup fails otherwise); `capacity = conf.getInt(bytes key, (int)(Runtime.getRuntime().maxMemory() * fraction))`. If the bytes key is set it wins and the fraction is ignored, except that the fraction is still range-checked. If it is not set, `capacity = (int)(maxMemory × 0.5)`. `long * float` is a `float`, and a narrowing cast of a float above `Integer.MAX_VALUE` gives `Integer.MAX_VALUE` (JLS §5.1.3). So on a JournalNode whose `maxMemory()` is above about 4 GiB, the default capacity is `2147483647` (see A3, overflow). The bytes key is parsed with `Integer.parseInt` (`Configuration.java:1546-1554`), so it cannot be set above `2147483647`. A value of 0 or a negative value is accepted, and then every non-empty batch is rejected at `:283`.
- **Sanity check, warning only:** `JournaledEditsCache.java:133-138` logs a WARN if `capacity > 0.9 × maxMemory`, but does not refuse or clamp it.
- **How it can be set:** `hdfs-site.xml` on each JournalNode host (or `-D` on the JournalNode command line). The cache exists only if `dfs.ha.tail-edits.in-progress=true` in the **JournalNode's** configuration (`Journal.java:180-187`, default `false` at `DFSConfigKeys.java:1350-1352`). Otherwise `cache == null` and nothing is cached (`Journal.java:432-434`). JournalNode has no reconfiguration hook (`JournalNode.java` has no reconfigurable properties), so a change needs a **JournalNode restart**. The cache is built in the `Journal` constructor (`Journal.java:170`) and again on `format` (`Journal.java:258`).
- **Who reads it:** the JournalNode daemon (`org.apache.hadoop.hdfs.qjournal.server.JournalNode`), once per journal ID (`JournalNode.java:98-109`, `journalsById`).

**A2. What it caps.** It caps JournalNode **heap**: the serialized edit batches held in `JournaledEditsCache.dataMap` (`TreeMap<Long, byte[]>`, `JournaledEditsCache.java:100`). They are kept so Standby or Observer NameNodes can tail in-progress edits over RPC (`Journal.getJournaledEdits`, `Journal.java:746-791`). The quantity compared with the limit is `totalSize`, the sum of `inputData.length` over cached batches (`:120`, `:281`, `:303`). For the incoming batch, `:278` uses `totalSize + inputData.length` and `:283` uses `inputData.length` alone. The `byte[]` is the array built for each `journal` RPC (`QJournalProtocolServerSideTranslatorPB.java:166`, `req.getRecords().toByteArray()`), and the cache holds it by reference. So the array body is exactly `inputData.length` bytes. The array header, the `TreeMap.Entry` and the boxed `Long` key are not counted.

**A3. Mechanism.**

1. NameNode → JournalNode `journal` RPC → `Journal.journal(...)`. After the segment and txid checks, `Journal.java:432-434` calls `cache.storeEdits(records, firstTxnId, lastTxnId, curSegmentLayoutVersion)` when the cache is enabled. This happens on every JournalNode in the quorum, before the fsync decision.
2. `storeEdits` (`JournaledEditsCache.java:247-305`): it rejects bad txids (`:249-254`) and takes the write lock (`:255`). Three cases reset the cache to start at `newStartTxn` (`initialize`, `:366-372`): a new layout version (`:256-264`), an empty cache (`:265-268`), and a non-contiguous batch (`:269-276`).
3. **Cumulative cap**, [`:278-282`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/server/JournaledEditsCache.java#L278-L282): while `totalSize + inputData.length > capacity` and the map is not empty, it removes the lowest-txid batch and subtracts its length.
4. **Single-batch cap (the target)**, [`:283`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/server/JournaledEditsCache.java#L283) `if (inputData.length > capacity)`:
   - **true:** the loop at `:278` has already emptied the map. `initialize(INVALID_TXN_ID)` clears it and marks it empty (`:284`), a WARN "A single batch of edits was too large to fit into the cache ... Cache is now empty." is logged (`:285-292`), and the method returns without storing. The next contiguous batch re-initializes the cache (`:265-268`). Until then, any `retrieveEdits` throws `CacheMissException` "Cache is empty" (`:178-179`, `:389-391`). The NameNode client falls back to streaming the edit files (`QuorumJournalManager.java:519-532`, WARN "falling back to streaming").
   - **false:** it sets `lowestTxnId` (`:295-299`), stores the batch (`:301`), and does `totalSize += inputData.length` (`:303`).
   - The comparison is strict `>`, so a batch of exactly `capacity` bytes is stored and fills the cache.
5. After a normal store the invariant is `totalSize ≤ capacity`.

**Bypasses and overshoots.**

- **(a) Uncounted object overhead.** Each cached batch also costs about 16 B of `byte[]` header, about 40 B for the `TreeMap.Entry` and 16 B for the `Long` key (compressed oops, 64-bit JVM). That is roughly 70 B per entry outside `totalSize`. With one-transaction batches of about 60–150 B, retained heap can be about 1.5–2× `capacity`. With batches of about 100 KB the overhead is negligible.
- **(b) One cache per journal ID.** `JournalNode.java:98-109` creates one `Journal`, and so one cache with its own full `capacity`, per journal ID (nameservice). A JournalNode that serves N nameservices can hold N × `capacity`. With the default fraction of 0.5, two journals can already claim the whole heap.
- **(c) `int` overflow at `:278`.** `totalSize`, `inputData.length` and `capacity` are all `int`. If `capacity == Integer.MAX_VALUE`, the condition `totalSize + len > capacity` can never be true without overflow. When the cache reaches about 2 GiB, `totalSize + len` wraps negative, the loop does not evict, `:283` is false, the batch is stored, and `totalSize` becomes negative (`:303`). After that the cache grows by roughly another 4 GiB before the sum exceeds `capacity` again. In practice eviction stops and the cache grows until the heap runs out. This happens with the **default** configuration whenever `maxMemory() × 0.5 > 2^31−1`, that is on a JournalNode heap above about 4 GiB (see A1). It also happens whenever `capacity` is within one batch length of `Integer.MAX_VALUE`.
- **(d) Limit set above the heap.** `:133-138` only warns, so a `capacity` above the heap is accepted and the cache can run the JournalNode out of memory.
- **(e) Transient copies.** `retrieveEdits` and `getJournaledEdits` copy the cached bytes into a `ByteString` for each response (`Journal.java:773-787`). The copy is transient and outside the cap. Each response is bounded by `maxTxns` (the client's `dfs.ha.tail-edits.qjm.rpc.max-txns`, `QuorumJournalManager.java:77`).

**A4. Other consumers.** Other JournalNode heap use the key does not control:

- IPC request buffers: each `journal` call's `byte[]` is up to `ipc.maximum.data.length` (default 128 MiB, `CommonConfigurationKeys.java:83-85`), plus the protobuf copy before the cache keeps a reference.
- Response `ByteString` copies (A3 e).
- JournalNodeSyncer, HTTP edit-segment serving, metrics and RPC handler state.

The edit log files under `dfs.journalnode.edits.dir` are **disk**, written and fsynced regardless of the cache. Nothing here bounds them; old segments are purged only when the NameNode tells the JournalNode to. On the NameNode side, `dfs.qjournal.queued-edits.limit.mb` (`DFSConfigKeys.java:1477`) bounds the client-side queue, which is a different constraint.

**A5. Evidence beyond the source.**

- In-tree documentation: `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/ObserverNameNode.md:137-214` (fast tailing, the cache and both keys; published as https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/ObserverNameNode.html) and `hdfs-default.xml:5050-5076`.
- Tests: `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/server/TestJournaledEditsCache.java`. `testCacheAboveCapacity` covers eviction, `testCacheSingleAdditionAboveCapacity` covers the `:283` branch and its log text, and `testCacheSizeConfigs` covers the bytes-versus-fraction precedence. The tests cover the counter logic only; there are no heap measurements and no case near `Integer.MAX_VALUE`.
- The class Javadoc (`JournaledEditsCache.java:63-72`) states the design: evict oldest first, about 200 B per transaction, watch `RpcRequestCacheMissAmount`.
- JIRA: from memory, not opened in this session, so nothing above depends on them: HDFS-13607 (the cache was added in the fast-tailing work) and HDFS-16550 (the fraction key).

## B. Verification solution

**B1. Claim under test.** On a JournalNode with `dfs.ha.tail-edits.in-progress=true`, the heap held by one journal's edits cache follows `dfs.journalnode.edit-cache-size.bytes` (or `fraction × maxMemory` when the bytes key is unset):

- The cached payload never exceeds `capacity`. Once the written edits exceed `capacity`, live cache bytes plateau at about `capacity`, and they scale with the knob.
- A single batch larger than `capacity` leaves the cache empty.

Sub-claim, expected to show the cap failing: with `capacity = Integer.MAX_VALUE`, the cache does **not** plateau at 2 GiB. It keeps growing past it.

### B2. Unit tier

**B2a. Environment and build.**

- JDK 8, Maven 3.3+, on a host with at least 8 GB free RAM for U4.
- Copy the tree to local disk, outside every shared or repository path: `rsync -a ~/hadoop-3.4.2/ /mydata/<you>/hadoop-u/`, then `cd` into it.
- Build once: `mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- New test file, in the same package so it can reach the package-private class: `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/server/TestJournaledEditsCacheCap.java`.
- Helpers it uses: `QJMTestUtil.createTxnData(int start, int n)` for real serialized MkdirOps, `NameNodeLayoutVersion.CURRENT_LAYOUT_VERSION`, and reflection on the private fields `totalSize` (int) and `dataMap` (`NavigableMap<Long, byte[]>`).
- JVM options: the default surefire `-Xmx2048m` for U1–U3. U4 needs `-Dmaven-surefire-plugin.argLine="-Xmx5g -XX:+HeapDumpOnOutOfMemoryError"` (property defined at `hadoop-project/pom.xml:187`).

**B2b. Knobs.**

| Test | Knob value | Why |
|---|---|---|
| U1 | `dfs.journalnode.edit-cache-size.bytes` (`conf.setInt`) = 4096, 65536, 1048576 | Three decades; shows the plateau scales with the knob. |
| U2 | `capacity = L` and `capacity = L − 1`, where `L = createTxnData(1, 200).length` (computed in the test) | The exact `:283` boundary, `>` against `≥`. |
| U3 | bytes key unset; `fraction` = 0.1 and 0.5 | The derived default: `getCapacity()` equals `(int)(Runtime.getRuntime().maxMemory() × f)`, and U1's plateau check passes against that value (run with 2 000 batches of about 1 KB, so it does not try to fill hundreds of MB; asserts only `totalSize ≤ capacity`). |
| U4 | bytes = `2147483647` (overflow probe) against control bytes = `1073741824` (1 GiB) | Probes the A3 (c) overflow; the control is the same workload with a reachable cap. |

**B2c. Workload.**

- **U1:** batches of 10 transactions, `createTxnData(start, 10)`, with contiguous txids and `start += 10` each time. Each transaction is a short MkdirOp of a few tens of bytes, so a batch is a few hundred bytes; the test computes the exact size `b`. The test stores batches until the cumulative bytes stored are ≥ 10 × `capacity` (for 1 MiB at about 500 B per batch, that is about 21 000 calls). The arithmetic: once the stored bytes exceed `capacity`, every further call must evict.
- **U2:**
  - With `capacity = L`: store one batch of exactly `L` bytes (txns 1–200), then store txns 201–210.
  - With `capacity = L − 1`: store the same `L`-byte batch.
- **U4:** zero-filled `new byte[1 << 20]` batches (1 MiB). `storeEdits` does not parse its input, and retrieval is not exercised. Each covers 1000 txids, contiguous, with `CURRENT_LAYOUT_VERSION`. Store 2600 batches (about 2.54 GiB).
  - With the 1 GiB control, 1024 batches fill it exactly. After that each store evicts one batch.
  - With `Integer.MAX_VALUE`: after 2047 batches `totalSize = 2047 × 2^20 = 2 146 435 072`. Batch 2048 gives `totalSize + 2^20 = 2^31`, which wraps to −2^31, so nothing is evicted.

**B2d. Observables and instruments.** After every `storeEdits` call, read by reflection:

- `totalSize`;
- `dataMap.size()`;
- `Σ dataMap.values().length`, which should equal `totalSize` (a cross-check);
- `getCapacity()`.

Keep the maximum `totalSize` seen and the final values. Capture the `:283` WARN with `GenericTestUtils.LogCapturer.captureLogs(Journal.LOG)`. For the actual retained heap, optional for U1 at 1 MiB and U4: pause the test (`Thread.sleep` behind a system property) and run `jcmd <surefire-pid> GC.class_histogram`. Read the bytes in `[B`, the instance count of `java.util.TreeMap$Entry`, and the bytes in `java.lang.Long`. Not observable here: the IPC and protobuf copies, because there is no RPC in this tier.

**B2e. Procedure.**

1. Write `TestJournaledEditsCacheCap` with four `@Test` methods, `testCumulativeCap`, `testSingleBatchBoundary`, `testDerivedDefault` and `testIntOverflowAtMaxCapacity`, as in B2b and B2c. Print one line per sample at a 1-in-100 stride, plus the final state: `capacity, calls, totalSize, entries, sumLen, maxTotalSize`.
2. Run U1–U3: `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestJournaledEditsCacheCap#testCumulativeCap+testSingleBatchBoundary+testDerivedDefault`.
3. Run U4 on its own with the larger heap: `mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestJournaledEditsCacheCap#testIntOverflowAtMaxCapacity -Dmaven-surefire-plugin.argLine="-Xmx5g"`. The test runs the 1 GiB control first, discards that cache, calls `System.gc()`, then runs `Integer.MAX_VALUE`.
4. Run the existing `TestJournaledEditsCache` as a regression baseline: `-Dtest=TestJournaledEditsCache`.
5. Collect the output from `hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports/`.

**B2f. Predictions, stated before running.**

- **U1, for each C in {4096, 65536, 1048576}:**
  - `maxTotalSize ≤ C` at every sample.
  - Final `totalSize` is in `(C − b, C]`.
  - `entries ≈ ⌊C / b⌋`.
  - `sumLen == totalSize` always.
  - `retrieveEdits(lowestTxnId, …)` succeeds, and `retrieveEdits(1, …)` throws `CacheMissException`.
  - Optional histogram at C = 1 MiB: `[B` above baseline is about 1 MiB plus about 16 B × entries; there are about `entries` `TreeMap$Entry` instances.
- **U2:**
  - With `capacity = L`: after the first store, `totalSize == L` and entries = 1. The second store (txns 201–210) evicts it, leaving `totalSize = size(201–210)` and entries = 1.
  - With `capacity = L − 1`: after the store, `totalSize == 0` and entries = 0. The log contains "A single batch of edits was too large", and `retrieveEdits(1, 1, …)` throws `CacheMissException` "Cache is empty".
- **U3:** `getCapacity() == (int)(maxMemory × f)` for f = 0.1 and 0.5, and `totalSize ≤ capacity` throughout.
- **U4:**
  - Control (1 GiB): entries plateau at 1024, and `totalSize == 1073741824` from call 1024 on.
  - `Integer.MAX_VALUE`:
    - entries = 2047 after call 2047;
    - **after call 2048, `totalSize == −2147483648` and entries == 2048 (no eviction)**;
    - entries == 2600 at the end, and `totalSize` stays negative to the end;
    - `[B` live bytes in the histogram are about 2.54 GiB.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1: `maxTotalSize ≤ C` for all three C, and the plateau scales about 16× and 256× | Mechanism works as traced; **supports** the claim. |
| U1: `totalSize > C` at any sample, or `sumLen ≠ totalSize` | Eviction or accounting is broken; **claim wrong** at the unit level. |
| U1: plateau far below C (for example less than C/2) for all C | Cap is not the binding factor (for example the cache resets for another reason); the trace is incomplete. |
| U2: `L` stored at `capacity = L` and rejected at `L − 1`, with the WARN | `:283` boundary confirmed (strict `>`). |
| U2: batch stored at `L − 1`, or no WARN | `:283` does not behave as traced; **claim wrong** for the single-batch part. |
| U3: `getCapacity()` ≠ `(int)(maxMemory × f)` | Derived default traced wrongly. |
| U4: `totalSize` goes negative at call 2048 and entries keep rising to 2600 | Overflow bypass **confirmed**: the cap does not bind at `Integer.MAX_VALUE`. |
| U4: entries plateau near 2047–2048 with `totalSize ≤ MAX_VALUE` | Overflow analysis **wrong**; the cap holds at its maximum. |
| U4: OOM before call 2048, or the control does not plateau at 1024 | Not conclusive; give more heap or recheck the control. |

**B2h. Controls.**

- `sumLen == totalSize` rules out a counter that drifts away from what is actually held.
- U2's 1-byte boundary shows the branch is caused by the knob and not by the data.
- U4's 1 GiB control runs the same workload, so the U4 difference comes from the value of `capacity` alone.
- The existing `TestJournaledEditsCache` passing shows the copy of the tree is unmodified.

### B3. Cluster tier

**B3a. Environment and build.**

- One Linux host with at least 16 GB RAM (at least 24 GB for the optional K6) and at least 15 GB of free **local** disk under `/mydata/<you>/s4/`.
- JDK 8, from a local copy of the tag: `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`. Unpack `hadoop-dist/target/hadoop-3.4.2` to `/mydata/<you>/s4/hadoop`.
- Daemons: an HA pair of NameNodes and one JournalNode, all on 127.0.0.1. No DataNode is needed, because the workload is metadata only (mkdir and delete).
  - **JN:** RPC 127.0.0.1:8485, HTTP 127.0.0.1:8480.
  - **nn1** (active): RPC 127.0.0.1:8020, HTTP 127.0.0.1:9870.
  - **nn2** (standby, tails edits from the JN over RPC): RPC 127.0.0.1:8021, HTTP 127.0.0.1:9871.

**Configuration directories.** Use two configuration directories, `conf-nn1/` and `conf-nn2/`. They are identical except for `dfs.ha.namenode.id` (`nn1` or `nn2`), which is needed because both NameNode addresses are local. The JN and the clients use `conf-nn1`.

**`core-site.xml`:**

- `fs.defaultFS=hdfs://ns1`
- `hadoop.tmp.dir=/mydata/<you>/s4/tmp`

**`hdfs-site.xml`, HA and JournalNode settings:**

- `dfs.nameservices=ns1`
- `dfs.ha.namenodes.ns1=nn1,nn2`
- `dfs.namenode.rpc-address.ns1.nn1=127.0.0.1:8020`
- `dfs.namenode.rpc-address.ns1.nn2=127.0.0.1:8021`
- `dfs.namenode.http-address.ns1.nn1=127.0.0.1:9870`
- `dfs.namenode.http-address.ns1.nn2=127.0.0.1:9871`
- `dfs.namenode.name.dir.ns1.nn1=/mydata/<you>/s4/nn1`
- `dfs.namenode.name.dir.ns1.nn2=/mydata/<you>/s4/nn2`
- `dfs.namenode.shared.edits.dir=qjournal://127.0.0.1:8485/ns1`
- `dfs.journalnode.edits.dir=/mydata/<you>/s4/jn`
- `dfs.journalnode.rpc-address=127.0.0.1:8485`
- `dfs.journalnode.http-address=127.0.0.1:8480`
- `dfs.client.failover.proxy.provider.ns1=org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider`
- `dfs.ha.fencing.methods=shell(/bin/true)`

**`hdfs-site.xml`, tailing settings:**

- `dfs.ha.tail-edits.in-progress=true`
- `dfs.ha.tail-edits.period=1s`
- `dfs.ha.tail-edits.period.backoff-max=10s`
- `dfs.namenode.checkpoint.txns=10000000`, so no standby checkpoint during a run.
- `dfs.permissions.enabled=false`
- The knob under test (B3b) goes only in the JN's `hdfs-site.xml`.

**Environment variables:**

- `HDFS_JOURNALNODE_OPTS="-Xmx1g -XX:+UseParallelGC"` (K6: `-Xmx6g`)
- `HDFS_NAMENODE_OPTS="-Xmx2g"`
- `HADOOP_LOG_DIR=/mydata/<you>/s4/logs/<daemon>`
- `HADOOP_PID_DIR=/mydata/<you>/s4/pid/<daemon>`, separate per daemon because both NameNodes would otherwise share one pid file.

**B3b. Knobs.** All in the JN's `hdfs-site.xml`, with `-Xmx1g` unless stated. Each knob value needs a **JN restart**. To start clean, also reformat: stop all, wipe `jn`, `nn1` and `nn2`, then format.

| Run | `dfs.journalnode.edit-cache-size.bytes` | Purpose |
|---|---|---|
| K0 | — and `dfs.ha.tail-edits.in-progress=false` on the JN | Negative control (no cache). |
| K1 | 65536 | Below one deep-mkdir batch (about 100 KB), so `:283` fires. |
| K2 | 8388608 (8 MiB) | Low plateau. |
| K3 | 67108864 (64 MiB) | 8× K2. |
| K4 | 268435456 (256 MiB) | 32× K2. |
| K5 | unset (fraction 0.5) | Derived default ≈ 0.5 × maxMemory; read the exact value from the JN log line "Enabling the journaled edits cache with a capacity of bytes: N" (`JournaledEditsCache.java:139-140`). |
| K6 (optional) | 2147483647, JN `-Xmx6g` | Overflow bypass (A3 c). The same as the default on a heap above about 4 GiB. Control: 1073741824 with the same heap and workload. |
| K7 (optional) | 8388608 with shallow one-transaction batches | Per-entry overhead (A3 a). |

**B3c. Workload.** Everything goes through the normal client path (`hdfs dfs`) against `ns1`.

Deep-path batches give large, predictable batches. Let `A=$(printf 'a%.0s' {1..250})`, a 250-character component; `max-component-length` is 255. Path `j` is `/w/p$j` followed by 28 levels of `/$A`, about 7 040 characters, below the 8 000 limit (`HdfsServerConstants.java:54`). One `-mkdir -p` of such a path makes one mkdirs RPC that logs about 30 MkdirOps whose paths grow by about 251 characters per level. The arithmetic: Σ (≈ 7 + 251k) for k = 1..28, plus about 50 B of op overhead each, is about **100–105 KB per batch**, all in one `logSync`.

One round is two commands:

```
hdfs --config conf-nn1 dfs -mkdir -p $(for j in $(seq 1 50); do printf "/w/p$j"; for k in $(seq 28); do printf "/$A"; done; printf ' '; done)
hdfs --config conf-nn1 dfs -rm -r -skipTrash /w
```

That is 50 batches, or about 5 MB of edits per round, and the namespace is empty again after each round.

| Run | Rounds | Edits written | Why that many |
|---|---|---|---|
| K1–K4 | 120 | ≈ 600 MB | ≥ 2.3× K4's 256 MiB |
| K5 | 250 | ≈ 1.25 GB | ≥ 2× the ≈ 480 MB default |
| K6 | 750 | ≈ 3.7 GB | Past 2 GiB by 1.6 GiB |
| K0 | 120 | ≈ 600 MB | Same as K1–K4 |

For the shallow-batch run (K7), each round is `hdfs dfs -mkdir /s/d{1..2000}` (2 000 RPCs of one transaction each, about 60–100 B per batch), then `-rm -r -skipTrash /s`. Run 60 rounds, about 120 000 entries, well above the 8 MiB / ~80 B ≈ 100 000 entries the cap allows.

Expected time is about 3–5 s per round (two JVM launches), so about 10 min for 120 rounds and about 1 h for K6.

**B3d. Observables and instruments.**

- **Retained cache bytes:**
  - Every 10 rounds, and at the end, run `jcmd <JN pid> GC.class_histogram`. It forces a full GC, so it reports live objects. From it, record:
    - the `[B` bytes;
    - the `java.util.TreeMap$Entry` instance count (the cache map is the JN's dominant TreeMap);
    - the `java.lang.Long` count.
  - Also record `jcmd <JN pid> GC.heap_info` and `jstat -gc <pid>` old-gen used after that full GC.
  - Baseline: one histogram after format and startup, before round 1. The cache value is `Δ[B` = `[B` minus the baseline.
- **Batch size and volume:** read `http://127.0.0.1:8480/jmx?qry=Hadoop:service=JournalNode,name=Journal-ns1` for `BytesWritten`, `BatchesWritten` and `TxnsWritten`. `BytesWritten / BatchesWritten` is the mean batch size.
- **Cache misses:** from the same bean, `RpcRequestCacheMissAmountNumOps` and the average.
- **Logs:**
  - JN log: the capacity line and the count of "A single batch of edits was too large".
  - nn2 log: the count of "falling back to streaming".
- **Process memory (secondary):** `VmRSS` and `VmHWM` from `/proc/<JN pid>/status`.
- **Disk (sanity):** `du -sb /mydata/<you>/s4/jn`.

Not directly observable: which `byte[]` objects belong to the cache. `Δ[B` is the proxy, and the `TreeMap$Entry` count cross-checks it. To attribute exactly, take an optional `jcmd <pid> GC.heap_dump` at the end of K3 and inspect the retained size of `JournaledEditsCache.dataMap` with Eclipse MAT.

**B3e. Procedure (per run).**

1. Write both configuration directories as in B3a, with the run's knob in the JN's `hdfs-site.xml`. Remove and recreate `/mydata/<you>/s4/{jn,nn1,nn2,tmp,logs,pid}`.
2. `hdfs --config conf-nn1 --daemon start journalnode`. Check the JN log for "Enabling the journaled edits cache with a capacity of bytes: N" and record N. K0 has no such line.
3. `hdfs --config conf-nn1 namenode -format -clusterId s4ce -force`, then `hdfs --config conf-nn1 --daemon start namenode`.
4. `hdfs --config conf-nn2 namenode -bootstrapStandby -force`, then `hdfs --config conf-nn2 --daemon start namenode`.
5. `hdfs --config conf-nn1 haadmin -transitionToActive nn1 --forcemanual`. Wait for `hdfs dfsadmin -safemode get` to report OFF.
6. Take the baseline histogram and the JMX readings (B3d).
7. Run the rounds (B3c), with a sample every 10 rounds. Afterwards, wait 30 s and take the final sample.
8. Check correctness: `hdfs --config conf-nn2 haadmin -getServiceState nn2` reports `standby`, and the nn2 web UI shows the last applied txid equal to the JN's `LastWrittenTxId`.
9. Stop and clean up as in B4. Next run.

**B3f. Predictions, stated before running.**

The batch size `b` from JMX is about 100–105 KB.

| Run | Final `Δ[B` and entries | Tolerance | Other |
|---|---|---|---|
| K0 | `Δ[B` ≈ 0, no growth trend across samples | within the ± few MB noise of IPC buffers | `getJournaledEdits` RPCs fail, so nn2 logs fallback to streaming |
| K1 | ≈ 0; `TreeMap$Entry` ≈ 0 for the cache | — | JN WARN "too large" count ≈ number of deep batches (6 000); nn2 fallbacks > 0; `RpcRequestCacheMissAmountNumOps` > 0 |
| K2 | ≈ 8 MiB, about 80 entries | − 1 batch, + per-entry and IPC noise (≤ 2 MB) | — |
| K3 | ≈ 64 MiB, about 640 entries | same | — |
| K4 | ≈ 256 MiB, about 2 560 entries | same | — |
| K5 | ≈ N bytes, with N ≈ 0.5 × maxMemory ≈ 470–500 MiB at `-Xmx1g` | same | — |
| K6 control (1 GiB) | ≈ 1 GiB | — | — |
| K6 (2147483647) | **no plateau**; keeps rising past 2 GiB to about 3.7 GB | — | — |
| K7 (8 MiB) | ≈ 8 MiB of payload, about 100 000 entries | — | The `TreeMap$Entry` and `Long` totals add a further ≈ 5–7 MiB, so total cache heap ≈ 1.6–1.9× the cap |

For K2–K5, `Δ[B` grows linearly while edits written < N and then stays flat, within ± one batch, for the rest of the run.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| K2–K5 plateau at ≈ their N, scaling 8× / 32×, flat after N is reached | **Claim supported**: the key caps JN cache heap. |
| A plateau well above N (for example more than 1.2 × N with ~100 KB batches) | **Claim wrong**: the cap does not bound retained heap. |
| No plateau in K2–K5 (growth tracks edits written) | **Claim wrong**: the cap is not enforced on the real path. |
| Plateaus equal across K2–K4 | The cache is bounded by something else, not this knob; **claim wrong**. |
| K1 shows growth, or no "too large" WARN | `:283` does not act on the real path as traced. |
| K0 shows the same growth as K2–K4 | `Δ[B` is not the cache (instrument wrong); results inconclusive. |
| K6: growth past 2 GiB with no plateau, the control plateaus at 1 GiB | Overflow bypass **confirmed** on a real JN. |
| K6: plateau at ≈ 2 GiB | Overflow analysis wrong; the cap holds at the maximum. |
| K7 total cache heap ≫ 2× the cap | Overhead larger than estimated; note it as an overshoot. |

**B3h. Controls.**

- K0 (cache off) separates cache growth from JN baseline and IPC noise.
- Three cap values with the same workload show the plateau follows the knob and not the workload.
- JMX `BytesWritten` shows the workload did exceed each cap.
- The `TreeMap$Entry` count cross-checks `Δ[B` against `Δ[B / b`.
- The K6 1 GiB control isolates the effect of the `capacity` value at the same heap.
- One JN process and one journal ID (`ns1`) avoids the per-journal multiplication (A3 b), so it does not confound the readings.

**B4. Risks and cleanup.**

- **Disk:** edits go to `/mydata/<you>/s4/{jn,nn1}`. Expect about 1.3 GB per K run, and K6 about 4 GB each on `jn` and `nn1`. Check `df -h /mydata` first, and wipe between runs.
- **Memory:** K6 needs a 6 GB JN heap plus 2 × 2 GB for the NameNodes. On this kind of host that fits, but check `free -g`.
- **Ports:** 8020, 8021, 8480, 8485, 9870 and 9871 must be free (`ss -ltn`). If not, shift all of them consistently.
- **No shared storage:** never use the shared source tree or repository paths; build in a local copy only.
- **Stop:**
  - `hdfs --config conf-nn2 --daemon stop namenode; hdfs --config conf-nn1 --daemon stop namenode; hdfs --config conf-nn1 --daemon stop journalnode`.
  - Then run `jps`. No `NameNode`, `JournalNode` or surefire `ForkedBooter` should remain; kill any leftover with its PID.
  - Remove `/mydata/<you>/s4/{jn,nn1,nn2,tmp,pid}` after saving the logs and histograms.
- **Unit tier:** U4 can hit an OOM if the heap is under 4 GB. The heap-dump flag writes `java_pid*.hprof` into the module directory; delete it.

## C. Sources read

- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/server/JournaledEditsCache.java`
- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/server/Journal.java` (135-190, 250-262, 395-440, 740-800)
- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/server/JournalMetrics.java`
- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/server/JournalNode.java` (journalsById, getOrCreateJournal)
- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/protocolPB/QJournalProtocolServerSideTranslatorPB.java` (160-170)
- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/client/QuorumJournalManager.java` (77, 108, 505-535)
- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java` (1348-1353, 1466-1477, 620)
- `hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml` (5049-5076)
- `hadoop-hdfs-project/hadoop-hdfs/src/site/markdown/ObserverNameNode.md` (130-214)
- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirMkdirOp.java` (mkdir logging per created component)
- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/common/HdfsServerConstants.java` (54-55)
- `hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeRpcServer.java` (1040-1056)
- `hadoop-hdfs-project/hadoop-hdfs/src/main/bin/hdfs` (journalnode subcommand)
- `hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/conf/Configuration.java` (1320-1330, 1546-1556, 3375-3390, 3505-3535)
- `hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/CommonConfigurationKeys.java` (83-85)
- `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/server/TestJournaledEditsCache.java`
- `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/QJMTestUtil.java` (createTxnData)
- `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/NNThroughputBenchmark.java` (1581-1670; considered as a workload, not used)
- `hadoop-project/pom.xml` (187)
- `hadoop-hdfs-project/hadoop-hdfs/pom.xml` (478)
- JLS §5.1.3, narrowing primitive conversion (float to int saturates), from memory

## D. Stage-4 feedback

none yet
