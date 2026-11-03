# sai_vector_term_size_fail_threshold — verification solution  <!-- file: cases/sai_vector_term_size_fail_threshold-add-value--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`VectorMemoryIndex.java:90`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L90) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (1M), Claude Code CLI (stage-3 autonomous subagent, band D triage), 2026-10-26 |
| Estimate | `positive`: a vector term larger than `sai_vector_term_size_fail_threshold` is never added to the memtable's on-heap vector graph on the insert path, so the graph's heap does not grow with oversized vectors. Caveat: it is a per-term cap, not an aggregate cap, and the vector update path (`VectorMemoryIndex.update`) skips the check (see A3). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `sai_vector_term_size_fail_threshold` (paired with
`sai_vector_term_size_warn_threshold`); a guardrail configuration entry.
- Declared: [`Config.java:946`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L946) (`DataStorageSpec.LongBytesBound`, default `"32KiB"`); warn at [`Config.java:945`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L945) (default `"16KiB"`).
- Guardrail object: `Guardrails.saiVectorTermSize`, [`Guardrails.java:544-551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java#L544-L551) (a `MaxThreshold`; `compare` is `value > threshold`, [`MaxThreshold.java:50-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java#L50-L53); a value of `<= 0` means disabled (`Long.MAX_VALUE`), [`MaxThreshold.java:56-60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java#L56-L60)).
- Unit: bytes of the serialized vector term (`ByteBuffer.remaining()`); for `vector<float, d>` that is `4*d`.
- Set by: `cassandra.yaml` keys `sai_vector_term_size_warn_threshold` / `sai_vector_term_size_fail_threshold` (commented example at `conf/cassandra.yaml:2253-2255`); JMX `GuardrailsMBean.setSaiVectorTermSizeThreshold(warn, fail)` ([`GuardrailsMBean.java:872`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/GuardrailsMBean.java#L872), [`Guardrails.java:1367-1370`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java#L1367-L1370), validated by [`GuardrailsOptions.java:1034-1045`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/GuardrailsOptions.java#L1034-L1045), warn must be <= fail); `nodetool setguardrailsconfig` (`tools/nodetool/GuardrailsConfigCommand.java`). The fields are `volatile` and read on each check, so no restart is needed.
- The guardrail chosen for a SAI index depends on the term type: vector → `saiVectorTermSize`, frozen → `saiFrozenTermSize`, else `saiStringTermSize` ([`StorageAttachedIndex.java:207-210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L207-L210)).


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap of the memtable-attached SAI vector index (`OnHeapGraph`
held by `VectorMemoryIndex`, `VectorMemoryIndex.java:72,83`). The compared quantity is
the size in bytes of one vector term (`term.remaining()`), compared with the fail
threshold (`StorageAttachedIndex.java:823`). It does not limit the number of terms or
the total graph size; it decides per term whether the term enters the graph at all.
Because a vector column has a fixed dimension, in practice it is all-or-nothing per
column: if `4*d > fail`, no vector of that column is indexed on the insert path.

**A3. Mechanism.**
1. Write → memtable partition update → `BTreePartitionUpdater` calls `indexer.onInserted` for a new row (`db/partitions/BTreePartitionUpdater.java:129`) → `StorageAttachedIndex.UpdateIndexer.insertRow` ([`StorageAttachedIndex.java:989-993`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L989-L993)) → `MemtableIndexManager.index` (`memory/MemtableIndexManager.java:69-98`) → `MemtableIndex.index` (`memory/MemtableIndex.java:90-99`) → `VectorMemoryIndex.add` (`memory/VectorMemoryIndex.java:88-96`).
2. Line 90: `if (value == null || value.remaining() == 0 || !index.validateTermSize(key, value, false, null)) return 0;`
3. `validateTermSize(..., isClientMutation=false, state=null)` ([`StorageAttachedIndex.java:815-833`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L815-L833)): `maxTermSizeGuardrail.failsOn(term.remaining(), null)`; `failsOn` = `enabled(null) && value > fail` ([`Threshold.java:111-114`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Threshold.java#L111-L114)); `enabled(null)` = `DatabaseDescriptor.isDaemonInitialized()` ([`Guardrail.java:93-96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrail.java#L93-L96)), so on a running node it applies to everybody, superusers included. On failure it logs `TERM_OVERSIZE_MESSAGE` (no-spam) and returns false.
4. Outcome at the limit: `add` returns 0 bytes; `graph.add` ([`VectorMemoryIndex.java:100`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L100), `disk/v1/vector/OnHeapGraph.java:133-205`, which stores the `float[]` and adds a graph node) is not called; the row itself is still written to the memtable/commit log; `MemtableIndex.index` still increments `writeCount` and adds 0 to `estimatedMemoryUsed` ([`MemtableIndex.java:95-97`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/MemtableIndex.java#L95-L97)); `adjustMemtableSize(0)` ([`StorageAttachedIndex.java:1002-1007`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L1002-L1007)).
5. Below the limit: `graph.add` returns the estimated bytes (vector `float[]`, postings, graph node), which flow into `MemtableIndex.estimatedMemoryUsed` (gauge `MemtableIndexBytes`, `metrics/IndexMetrics.java:58`) and into memtable on-heap ownership via `markExtraOnHeapUsed`.
6. Client-side front door (not the target, same constraint): for CQL client mutations `validateIndexedColumns` (`cql3/statements/SingleTableUpdatesCollector.java:111`, `db/IMutation.java:42-45`) → `StorageAttachedIndex.validate` (`:521-530`) → `validateTermSize(..., true, state)` → `guard(...)` (`:817-821`), which throws `GuardrailViolatedException` only for ordinary users. `enabled(state)` is false for superusers and internal calls (`ClientState.isOrdinaryUser`, `service/ClientState.java:594-597`), and with the default `AllowAllAuthenticator` everybody is a superuser (`ClientState.isSuper`, `:602-605`). So on a default node the write is accepted and line 90 is the only enforcement.
7. **Bypass:** `VectorMemoryIndex.update` ([`VectorMemoryIndex.java:107-147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java#L107-L147)), reached when the row already exists in the same memtable ([`BTreePartitionUpdater.java:139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java#L139) → [`SecondaryIndexManager.java:1552-1590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/SecondaryIndexManager.java#L1552-L1590) → `UpdateIndexer.updateRow` → `MemtableIndexManager.update`, `:98-111`), calls `graph.add(newValue, ...)` at line 134 with **no** `validateTermSize` check. Overwriting an existing key in the same memtable therefore indexes an oversized vector. `MemtableIndex.update` ([`MemtableIndex.java:101-104`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/memory/MemtableIndex.java#L101-L104)) also does not add those bytes to `estimatedMemoryUsed`, so `MemtableIndexBytes` under-reports them (the memtable ownership still sees them via `adjustMemtableSize`).

**A4. Other consumers.** The base memtable row (the raw vector bytes, same size) is
stored whatever the guardrail decides; commit log; the flushed SSTable data. The
SSTable-attached index writer applies the same check at flush/build
(`disk/v1/SSTableIndexWriter.java:207`), so oversized terms are also kept out of the
on-disk vector index; compaction-time graphs (`CompactionVectorValues`). Query-time
structures (ANN search, `MAX_TOP_K`, materialized keys) are separate constraints.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/db/guardrails/GuardrailSaiVectorTermSizeTest.java`: client insert above fail fails (ordinary user); `testFailingVectorOnBuild` shows an oversized vector is stored but not returned by ANN after index build.
- `conf/cassandra.yaml:2253-2255`.

## B. Verification solution

**B1. Claim under test.** For a `vector<float, 2048>` SAI-indexed column (8192-byte
terms) written by a superuser/internal path, setting `sai_vector_term_size_fail_threshold`
below 8192 B keeps the memtable vector index heap at about zero (no `float[2048]`
retained, `MemtableIndexBytes` = 0), while at the default 32KiB the same workload grows
it by at least 8192 B per row. Secondary claim: overwriting the same keys within one
memtable bypasses the cap (update path), and the graph grows anyway.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. `git clone --branch cassandra-5.0.9 /Users/yangwang/cassandra-src /local/disk/c509` (local disk, never the shared clone); `cd /local/disk/c509 && ant jar build-test`. Test source: `test/unit/org/apache/cassandra/index/sai/cql/VectorTermSizeCapTest.java` (new, in the local clone only), extending `org.apache.cassandra.index.sai.SAITester` (which brings `CQLTester`, `daemonInitialization()` so guardrails are enabled). Default test JVM options from `build.xml`.

> **Amendment B2a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine (`environment-advisor.md`; macOS arm64,
> no `/local`): the clone is `$W/cassandra-run40` (`W=~/Library/Caches/stage4`), a fresh `git clone --branch cassandra-5.0.9
> ~/cassandra-src $W/cassandra-run40`, built with `ant -Dlocal.repository=$W/m2 build-test` (`ant jar` alone builds no test classes).
> The test is kept in `harness/sai_vector_term_size_fail_threshold-add-value--autonomous/VectorTermSizeCapTest.java`; `unit-run.sh` in
> the same folder copies it into the clone, runs one `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.index.sai.cql.VectorTermSizeCapTest`
> JVM, keeps the logs and deletes the test and its classes. The test turns read thresholds off in `@Before`
> (`DatabaseDescriptor.setReadThresholdsEnabled(false)`, `DatabaseDescriptor.java:4857`), because the unit yaml enables them
> (`test/conf/cassandra.yaml:63-69`) and the ANN and `count(*)` read-backs must not be refused by them. The unit yaml's memtable
> allocation is `heap_buffers` (`test/conf/cassandra.yaml:6`), so base rows are on-heap slab bytes (`byte[]`), not `float[]`.

**B2b. Knobs.** `fail` threshold via `DatabaseDescriptor.getGuardrailsConfig().setSaiVectorTermSizeThreshold(warn, fail)` per test, values:
- A (control, default): warn `16KiB`, fail `32KiB` (8192 < 32768 → indexed).
- B (boundary, at): warn `4KiB`, fail `8KiB` (8192 is not `> 8192` → indexed; checks the strict `>`).
- C (below): warn `2KiB`, fail `8191B` → not indexed.
- D (bypass): config C, each key written twice with different vectors.

> **Amendment B2b (2026-10-26, stage-4 audit, before any reading).** Added control arm **D0**: config C, the same two-pass workload as
> D, on a table **without** the SAI index. Reason (from source, no reading): with `heap_buffers` the second pass clones the new cell
> into the memtable allocator and the first cell's slab bytes are not returned (`BTreePartitionUpdater.java:136-141`), so D's
> `ownsOnHeap` grows by about 500 × 8 KiB of base data even if the update path were guarded. D − D0 removes that term; B2c's
> "same N/dimension for every arm" holds. D0 has no ANN query (no index) and no SAI counters.

**B2c. Workload.** `CREATE TABLE %s (k int PRIMARY KEY, v vector<float, 2048>)`;
`CREATE INDEX ON %s(v) USING 'sai' WITH OPTIONS = {'similarity_function':'euclidean'}`;
`disableCompaction()`; N = 500 inserts via `execute("INSERT INTO %s (k, v) VALUES (?, ?)", k, vec)`
(internal client state → client guard skipped, memtable check active), `vec` = 2048 random floats in [0.1, 1.0) (non-zero). Each term 8192 B, so N terms = 4,096,000 B ≥ the 1 MiB scale where accounting noise is negligible. No flush during the test (assert sstable count 0).

> **Amendment B2c (2026-10-26, stage-4 audit, before any reading).** Exact data: each arm uses `new java.util.Random(42)`; component
> = `0.1f + 0.9f * nextFloat()`; D's and D0's second pass continues the same generator (so its vectors differ from the first pass).
> ANN query vector: `new Random(7)`, same formula. Writes are `execute(...)` (internal, sequential), so jvector's builder pool
> limit (`availableProcessors()+1`, see amendment B3c) is never approached. The test never fails on a reading: it prints and
> the self-check judges.

**B2d. Observables and instruments.**
- `StorageAttachedIndex sai = (StorageAttachedIndex) getCurrentColumnFamilyStore().indexManager.getIndexByName(indexName)`; `sai.memtableIndexManager().estimatedMemIndexMemoryUsed()` (the check's own downstream operand: bytes the graph reported) and `liveMemtableWriteCount()`.
- `Memtable.getMemoryUsage(cfs.getTracker().getView().getCurrentMemtable()).ownsOnHeap` before/after (captures update-path bytes too).
- `sai.validateTermSize(key, term, false, null)` return value for one 8192-B term.
- Functional: `SELECT k FROM %s ORDER BY v ANN OF ? LIMIT 10` row count.
- Not observable directly: real retained heap; the estimate is the code's own.

> **Amendment B2d (2026-10-26, stage-4 audit, before any reading).** Real retained heap **is** observable in-process, so it is
> added: live `float[]` bytes from the JVM's own class histogram, read through the `com.sun.management:type=DiagnosticCommand`
> MBean operation `gcClassHistogram` (the same command as `jcmd GC.class_histogram`; it forces a full GC, so the reading is
> post-GC live bytes), before the inserts and after them. The graph stores each vector as a `float[2048]` (16 + 8192 = 8,208 B;
> `OnHeapGraph.java:137,186-188`, `ConcurrentVectorValues.java:51-55`); base rows are `byte[]` slabs. Instrument check: a
> known-answer probe (`KA`) retains 500 × `new float[2048]` in a static list and must read a `float[]` delta of at least
> 4,104,000 B and less than 4,104,000 + 1,000,000 B. Output: one stdout line per arm starting `PROBE arm=<X>` with
> `failBytes`, `validateTermSize`, `memtableIndexBytes`, `writeCount`, `ownsBefore`, `ownsAfter`, `ownsDelta`, `floatBefore`,
> `floatAfter`, `floatDelta`, `ann`, `sstables`, `rows` (`SELECT count(*)`). `validateTermSize` is called on an 8,192-byte buffer
> (the check reads only `remaining()`, `StorageAttachedIndex.java:823`) **after** the post-insert readings, so its no-spam log line
> does not enter them.

**B2e. Procedure.** One `@Test` per arm (A, B, C, D), each: set thresholds; create table/index; record baseline; insert (D: insert all keys, then insert all keys again with new vectors); read observables; reset thresholds to default in `@After`. Run: `ant testsome -Dtest.name=org.apache.cassandra.index.sai.cql.VectorTermSizeCapTest`. Delete the test file afterwards.

> **Amendment B2e (2026-10-26, stage-4 audit, before any reading).** Five `@Test` methods (A, B, C, D, D0) plus the `KA` probe in
> one JVM, run by `unit-run.sh` (amendment B2a). Per arm, in order: set thresholds; create table (and index, except D0);
> `disableCompaction()`; baseline `float[]` (class histogram) and `ownsOnHeap`; inserts (D, D0: two passes); `ownsOnHeap`, then
> `float[]` (class histogram); SAI counters; `validateTermSize`; ANN (not D0); `count(*)`; sstable count; print. `@After` restores
> warn 16KiB / fail 32KiB. Arms run in JUnit's method order; each arm reads deltas inside its own window, and earlier arms'
> memtables stay live and unchanged during later windows (no flush: `sstables` is printed per arm).

**B2f. Predictions.**
| Arm | validateTermSize | MemtableIndexBytes | ownsOnHeap delta minus arm C delta | ANN rows |
|---|---|---|---|---|
| A 32KiB | true | ≥ 500×8192 = 4,096,000 | ≥ 4,096,000 | 10 |
| B 8KiB (=) | true | ≥ 4,096,000 | ≥ 4,096,000 | 10 |
| C 8191B | false | exactly 0 | 0 (baseline) | 0 |
| D bypass | false | 0 (update bytes not counted) | ≥ 4,096,000 | 10 |
`liveMemtableWriteCount` = 500 in A, B, C (it counts skipped terms too), 500 in D (updates do not increment it).

> **Amendment B2f (2026-10-26, stage-4 audit, before any reading).** The filed predictions above stay and are judged as written.
> Added, for the observables of amendments B2b and B2d (derived from source, no reading):
>
> | Arm | `floatDelta` (live `float[]`, B) | other |
> |---|---|---|
> | A, B | ≥ 4,096,000 (500 × 8,208 = 4,104,000 for the vectors alone) | `rows` = 500, `sstables` = 0 |
> | C | < 1,000,000 (no vector enters the graph) | `rows` = 500, `sstables` = 0 |
> | D | ≥ 4,096,000 (the second pass's 500 vectors enter the graph) | `rows` = 500, `sstables` = 0; **D − D0 `ownsDelta` ≥ 4,096,000** |
> | D0 | < 1,000,000 (no index) | `rows` = 500, `sstables` = 0 |
> | KA | 4,104,000 ≤ delta < 5,104,000 | — |
>
> ANN rows in D are not predicted: `update()` does not add the key to `primaryKeys` (`VectorMemoryIndex.java:108-146`, against
> `:102`), and a sub-range query searches only `primaryKeys` (`:170-194`); a full-ring query searches the graph (`:195-201`).
> Which applies depends on the read path, so D's ANN count is reported, not a verdict condition.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| C: bytes 0, ANN 0; A: bytes ≥ 4.1 MB, ANN 10 | claim confirmed for the insert path |
| C: bytes > 0 or ANN > 0 | claim wrong: the cap does not keep terms out |
| B: bytes 0 | boundary is `>=`, not `>` (contradicts the trace) |
| A: bytes ≈ 0 | positive control failed (index not attached / instrument wrong); no conclusion |
| D: ownsOnHeap grows ≥ 4.1 MB, ANN 10 | bypass confirmed |
| D: ownsOnHeap flat, ANN 0 | update path is guarded somewhere not traced; bypass refuted |

> **Amendment B2g (2026-10-26, stage-4 audit, before any reading).** Verdict words and the rows needed to close the table. "Insert
> path holds" means: C `validateTermSize` false, `memtableIndexBytes` 0, ANN 0 and `floatDelta` < 1,000,000; A and B
> `validateTermSize` true, `memtableIndexBytes` ≥ 4,096,000, ANN 10 and `floatDelta` ≥ 4,096,000. "Bypass holds" means D
> `floatDelta` ≥ 4,096,000 and D − D0 `ownsDelta` ≥ 4,096,000 (ANN in D is reported only, amendment B2f; the filed D rows are read
> with this measure in place of D's raw `ownsOnHeap`, which carries D0's base-data term). "Bypass refuted" means D `floatDelta`
> < 1,000,000 and D − D0 `ownsDelta` < 409,600.
>
> | Readings | Verdict | Effect |
> |---|---|---|
> | insert path holds and bypass holds (rows 1 and 5) | **Confirmed** | caps only on some paths (bypass) |
> | insert path holds and bypass refuted (rows 1 and 6) | **Refuted** (B1's secondary claim) | caps |
> | C indexed: `memtableIndexBytes` > 0, ANN > 0 or `floatDelta` ≥ 1,000,000 (row 2) | **Refuted** | does not cap |
> | B `memtableIndexBytes` 0, everything else as "insert path holds" (row 3) | **Refuted** (boundary is `>=`), insert path otherwise as traced | caps |
> | A `memtableIndexBytes` ≈ 0 or `floatDelta` < 4,096,000 (row 4); or `sstables` > 0, `rows` ≠ 500 in any arm, a test error, or KA outside its band | **Invalid** — no conclusion | undetermined |
> | any other combination (for example D between the two bands) | **Not confirmed** | undetermined |

**B2h. Controls.** Arm A as the positive control on the identical workload; sstable count 0 rules out flush resetting the memtable index; same N/dimension for every arm; ANN result count cross-checks the byte estimate.

> **Amendment B2h (2026-10-26, stage-4 audit, before any reading).** Added: arm D0 (amendment B2b) removes the overwrite's base-data
> bytes from D; the live `float[]` reading (amendment B2d) checks the code's estimate against real retained heap, and the KA probe
> checks that instrument; `rows` = 500 shows the rows themselves are written in every arm (the cap drops the index entry, not the
> row).

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, JDK 11, built from the local clone (`ant jar`). `conf/jvm11-server.options` / env: `-Xms4G -Xmx4G`, G1. `cassandra.yaml`: `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` on local disk (≥ 5 GB free); `memtable_heap_space: 2048MiB`; `memtable_allocation_type: heap_buffers` (default); `authenticator: AllowAllAuthenticator` (default; makes the client a superuser so line 90 is the only enforcement); `concurrent_compactors` default, compaction disabled on the table. Client: Python 3 venv on local disk with `pip install cassandra-driver`.

> **Amendment B3a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine (macOS arm64, not Linux): the node runs
> from `$W/cassandra-run40` (amendment B2a; `build-test` includes the jar; no test file is left in it), with its own `conf/` copy and
> data, commit log, hints, saved caches, CDC and logs under `$W/node-vts/` on the internal SSD, wiped before and after each arm.
> `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M` (G1 is the default in `conf/jvm11-server.options:63`), plus `-Xlog:gc*` to a file. No
> `setsid` here, so the node is a tracked background `bin/cassandra -f`. Listen and RPC address `127.0.0.1`. Client: the driver
> bundled in the clone (`lib/cassandra-driver-internal-only-*.zip`, which has the vector type), Python 3.8, no venv and no `pip`;
> `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, heartbeat off, request timeout 120 s, reconnect on connect failure.
> Flush arithmetic: `memtable_flush_writers` = 2 for one data directory (`DatabaseDescriptor.java:753-756`), so the cleanup
> threshold is 2048 MiB / 3 ≈ 683 MiB; the largest arm (D) owns about 2 × 82 MB of base slabs + about 90 MB of graph ≈ 260 MB.

**B3b. Knobs.** In `cassandra.yaml`, restart between arms (wipe data dirs between arms):
- A: `sai_vector_term_size_warn_threshold: 16KiB`, `sai_vector_term_size_fail_threshold: 32KiB` (default).
- C: `sai_vector_term_size_warn_threshold: 2KiB`, `sai_vector_term_size_fail_threshold: 4KiB`.
- D: as C, workload with overwrite.
- E (front door, optional): as C plus `authenticator: PasswordAuthenticator`, client logged in as an ordinary role with `MODIFY` on the keyspace.

> **Amendment B3b (2026-10-26, stage-4 audit, before any reading).** Arm E is run. To grant `MODIFY` the authorizer must support
> grants, so E also sets `authorizer: CassandraAuthorizer` (with `AllowAllAuthorizer`, `GRANT` is refused, `AllowAllAuthorizer.java:38`). The schema is created
> by the default superuser `cassandra` (created about 10 s after start, `CassandraRelevantProperties.java:538`; the script retries
> the login), which then runs `CREATE ROLE vt_writer WITH PASSWORD = 'vt_writer' AND LOGIN = true AND SUPERUSER = false` and
> `GRANT MODIFY ON KEYSPACE vt TO vt_writer`, `GRANT SELECT ON KEYSPACE vt TO vt_writer`; the load and the ANN query run as
> `vt_writer`. Arm order: A, C, D, E, one node lifetime each.

**B3c. Workload.** `CREATE KEYSPACE vt WITH replication={'class':'SimpleStrategy','replication_factor':1}`;
`CREATE TABLE vt.t (k int PRIMARY KEY, v vector<float, 2048>) WITH compaction={'class':'SizeTieredCompactionStrategy','enabled':'false'}`;
`CREATE INDEX t_v_idx ON vt.t(v) USING 'sai' WITH OPTIONS={'similarity_function':'euclidean'}`.
Python script: prepared `INSERT INTO vt.t (k, v) VALUES (?, ?)`, k = 0..9999, `v = [random.uniform(0.1,1.0) for _ in range(2048)]`, concurrency 16 (`execute_concurrent_with_args`). Arm D: run the same loop twice with fresh random vectors. Arithmetic: 10,000 × 8192 B = 81.9 MB raw; with index ≈ 82 MB of `float[]` + graph overhead; total memtable ownership ≈ 170-200 MB, below the flush trigger (`memtable_cleanup_threshold` default 1/(1+flush writers) of 2048 MiB ≥ 680 MB), so everything stays in one memtable. Duration a few minutes.

> **Amendment B3c (2026-10-26, stage-4 audit, before any reading).** Load concurrency **8**, not 16: jvector 1.0.2's builder pool
> throws `IllegalStateException` when more than `availableProcessors()+1` = 11 graph inserts run at once
> (`PoolingSupport$ThreadPooling.get`, read with `javap -c -p` at the audit), so 16 in-flight writes could fail in arms A and D for
> a reason unrelated to the cap. Data: `random.Random(42)`, component `uniform(0.1, 1.0)`; D's second pass continues the same
> generator. ANN query vector: `random.Random(7)`, same formula, `LIMIT 10`, via the driver (prepared, vector bound). The schema
> statements are the filed ones (E: run by `cassandra`, amendment B3b).

**B3d. Observables and instruments.**
- `nodetool sjk mx -b "org.apache.cassandra.metrics:type=StorageAttachedIndex,keyspace=vt,table=t,index=t_v_idx,scope=IndexMetrics,name=MemtableIndexBytes" -f Value -mg` (also `name=LiveMemtableIndexWriteCount`), before and after the load.
- `jcmd <pid> GC.class_histogram | grep ' \[F$'` (live `float[]` bytes, forces a full GC): the graph is the only holder of `float[2048]` on the write path (base memtable holds `byte[]`/`ByteBuffer`).
- `jcmd <pid> GC.heap_info` after `jcmd <pid> GC.run`: heap used.
- `nodetool tablestats vt.t`: SSTable count must stay 0; "Memtable data size".
- `grep "too large and cannot be indexed" logs/system.log` (no-spam logger, at least one line expected in C).
- `cqlsh -e "SELECT k FROM vt.t ORDER BY v ANN OF [<2048 floats>] LIMIT 10"` (generate via the script): rows returned.

> **Amendment B3d (2026-10-26, stage-4 audit, before any reading).** Instruments on this host:
> - `MemtableIndexBytes` and `LiveMemtableIndexWriteCount` are read with a small JMX client,
>   `harness/<stem>/JmxGet.java` (attribute `Value`, `localhost:7199`), not `nodetool sjk mx` (which exits 0 on failure here).
>   The MBean names are as filed (`AbstractMetrics.java:84-95`).
> - Live `float[]` bytes: `jcmd <pid> GC.class_histogram`, line `[F`, before and after the load (it forces a full GC).
> - **Heap used** is the same histogram's `Total` bytes (post-full-GC live heap), not `GC.heap_info` after `GC.run` (that pair
>   failed a known-answer check on this host in an earlier run). Instrument check before run 1: the cluster shakedown must show
>   `[F` Total moving by at least the vector bytes in arm A.
> - Each reading is one line in `summary.txt`: `ARM`, `READBACK` (thresholds and authenticator from `system.log`), `JMX`,
>   `HISTO`, `LOAD` (ok/failed/first error), `ANN`, `COUNT` (`SELECT count(*)` as the loading user), `STATS` (tablestats),
>   `LOGLINES` (count of `too large and cannot be indexed` in `system.log`).

**B3e. Procedure.** For each arm: (1) wipe local data dirs, set yaml, `bin/cassandra -p /tmp/c.pid`; wait for `nodetool status` UN. (2) create schema. (3) baseline readings (sjk, class histogram, heap_info). (4) run loader (D: twice). (5) readings again; ANN query; tablestats; log grep. (6) `nodetool drain; kill $(cat /tmp/c.pid)`; check `pgrep -f CassandraDaemon` empty.

> **Amendment B3e (2026-10-26, stage-4 audit, before any reading).** One script, `harness/<stem>/cluster-run.sh`, runs the four arms
> in order A, C, D, E, each in its own node lifetime: (1) wipe `$W/node-vts`, write the yaml, start the tracked node, wait for
> `UN` and `statusbinary running`; (2) schema (E: superuser, role, grants); (3) baseline JMX and histogram; (4) load (D: twice);
> (5) JMX, histogram, ANN, `count(*)`, tablestats, log grep; (6) `nodetool drain`, `nodetool stopdaemon`, wait for the process to
> exit, check that no daemon is left (the pattern is split so the script never matches itself), copy logs, wipe. The heap reading
> after the load is taken before the ANN and `count(*)` queries.

**B3f. Predictions.**
| Arm | MemtableIndexBytes | `[F` live bytes delta | heap used delta vs C | ANN rows | log line |
|---|---|---|---|---|---|
| A | ≥ 81.9 MB | ≥ 81.9 MB | ≥ +80 MB | 10 | no |
| C | 0 | < 2 MB | 0 (reference) | 0 | yes |
| D | ≈ 0 (updates uncounted) | ≥ 81.9 MB | ≥ +80 MB | 10 | yes (first pass) |
| E | 0; client writes fail with `Value of column 'v' has size ... failure threshold` | < 2 MB | below C (rows rejected) | 0 | no |

> **Amendment B3f (2026-10-26, stage-4 audit, before any reading).** The filed predictions stay and are judged as written. Reading
> rules: MB = 10^6 B, so "≥ 81.9 MB" is ≥ 81,920,000 B (10,000 × 8,192) and "< 2 MB" is < 2,000,000 B; "heap used delta" is the
> histogram `Total` delta (amendment B3d); "heap used delta vs C" is (arm's delta − C's delta). D's heap delta also carries a
> second copy of the base rows in the memtable slabs (amendment B2b), so it is reported but D is judged on `[F`. ANN rows in D are
> reported, not a verdict condition (amendment B2f: `update()` does not fill `primaryKeys`, and a driver query reaches the
> memtable index through the coordinator's range split). Arm E's `COUNT` and ANN run as `vt_writer`.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| C ≈ 0 on `[F` and MemtableIndexBytes, A ≥ 82 MB | the threshold caps the memtable vector index heap (confirmed) |
| C `[F` delta ≥ 80 MB or ANN returns rows | claim wrong: oversized vectors reach the graph on the insert path |
| A ≈ 0 | positive control failed (index missing, flush happened); repeat |
| SSTable count > 0 in any arm | memtable flushed; readings invalid, lower N |
| D grows like A | update-path bypass confirmed; the cap is not a hard bound |
| D flat | bypass refuted |

> **Amendment B3g (2026-10-26, stage-4 audit, before any reading).** Verdict words and closing rows. "Insert path holds": C `[F`
> delta < 2,000,000, `MemtableIndexBytes` 0, ANN 0, at least one log line; A `MemtableIndexBytes` ≥ 81,920,000, `[F` delta
> ≥ 81,920,000, ANN 10. "Bypass holds" ("D grows like A"): D `[F` delta ≥ 81,920,000. "Bypass refuted" ("D flat"): D `[F` delta
> < 2,000,000. Every arm needs `LOAD` ok = 10,000 per pass (E: failed = 10,000 is its prediction), `COUNT` = 10,000 (E: 0) and
> SSTable count 0. Arm E is judged against its own B3f row and reported; it tests the client front door (A3.6), not B1, so it
> does not change the B1 verdict.
>
> | Readings | Verdict | Effect |
> |---|---|---|
> | insert path holds and bypass holds (rows 1 and 5) | **Confirmed** | caps only on some paths (bypass) |
> | insert path holds and bypass refuted (rows 1 and 6) | **Refuted** (B1's secondary claim) | caps |
> | C `[F` delta ≥ 80,000,000 or ANN > 0 (row 2) | **Refuted** | does not cap |
> | A ≈ 0 (row 3), SSTable count > 0 (row 4), a load failure in A, C or D, or a node error that stops an arm | **Invalid** — repeat | undetermined |
> | any other combination | **Not confirmed** | undetermined |

**B3h. Controls.** Arm A is the positive control (same workload, cap not binding, usage moves); fresh data dir per arm; no flush (SSTable count 0); `float[]` histogram isolates the graph from the base memtable; ANN count is a functional cross-check independent of the byte estimate.

**B4. Risks and cleanup.** Build and test only in the local clone; data, commit log and hints on local disk (< 1 GB used); the unit test writes under the clone's `build/test`. After each arm: `nodetool drain`, kill the pid, `pgrep -f CassandraDaemon` must be empty, `rm -rf` the local data dirs; remove the venv and the test file when done.

> **Amendment B4 (2026-10-26, stage-4 audit, before any reading).** Host paths: clone `$W/cassandra-run40`, node data `$W/node-vts`
> (wiped by the script), full logs `$W/logs/sai_vector_term_size_fail_threshold-add-value--autonomous/`. No venv (bundled driver).
> The daemon check is `pgrep -f` with a split pattern; `git -C $W/cassandra-run40 status` must be clean at the end.

## C. Sources read

src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java
src/java/org/apache/cassandra/index/sai/memory/MemtableIndex.java
src/java/org/apache/cassandra/index/sai/memory/MemtableIndexManager.java
src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java
src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java
src/java/org/apache/cassandra/index/sai/disk/v1/vector/OnHeapGraph.java
src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java
src/java/org/apache/cassandra/index/sai/metrics/IndexMetrics.java
src/java/org/apache/cassandra/index/sai/metrics/AbstractMetrics.java
src/java/org/apache/cassandra/index/SecondaryIndexManager.java
src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java
src/java/org/apache/cassandra/db/memtable/Memtable.java
src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
src/java/org/apache/cassandra/db/guardrails/Guardrails.java
src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java
src/java/org/apache/cassandra/db/guardrails/Threshold.java
src/java/org/apache/cassandra/db/guardrails/Guardrail.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/GuardrailsOptions.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/service/ClientState.java
src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java
src/java/org/apache/cassandra/db/IMutation.java
src/java/org/apache/cassandra/db/marshal/VectorType.java
conf/cassandra.yaml
test/unit/org/apache/cassandra/db/guardrails/GuardrailSaiVectorTermSizeTest.java

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1** (Claude Opus 5.5, claude-opus-5-5[1m], on the advisor's machine; results
[`../../stage4-runtime-verification/results/sai_vector_term_size_fail_threshold-add-value--autonomous.md`](../../stage4-runtime-verification/results/sai_vector_term_size_fail_threshold-add-value--autonomous.md);
frozen at sha256 `c1b87bd8…f1c0` after sixteen dated audit amendments; uncommitted).

- **Unit: Confirmed — caps only on some paths (bypass)** (B2g rows 1 and 5). Fail 8191 B: `validateTermSize` false, `MemtableIndexBytes`
  0, ANN 0, live `float[]` +0 B. 32 KiB and 8 KiB (strict `>`): 4,404,500 B estimate, +4,218,672 B live `float[]`, ANN 10. Overwrite
  under 8191 B: +4,216,208 B live `float[]`; D − D0 memtable ownership 4,404,500 B; `MemtableIndexBytes` 0.
- **Cluster: Confirmed — caps only on some paths (bypass)** (B3g rows 1 and 5). Fail 4 KiB: `[F` +0 B, `MemtableIndexBytes` 0, ANN 0,
  10,000 "too large" lines. 32 KiB: `MemtableIndexBytes` 90,010,000, `[F` +84,883,192 B, ANN 10. Overwrite under 4 KiB: `[F`
  +84,894,168 B with `MemtableIndexBytes` 0. Arm E (ordinary role): all writes refused with the guardrail text.
- For stage 3:
  - (1) A3.7: `update()` also skips `primaryKeys.add` (`VectorMemoryIndex.java:102` vs `:108-146`). Whether bypassed keys come back from
    ANN therefore depends on the range path (`:170-201`); both tiers returned 10 here.
  - (2) The bypass needs only an upsert of a key whose row is still in the current memtable, so "caps" holds for first writes only.
  - (3) B2d's "real retained heap not observable" was not so: the class histogram is readable in-process.
  - (4) B3c's concurrency 16 exceeds jvector 1.0.2's 11-insert builder pool, which throws.
