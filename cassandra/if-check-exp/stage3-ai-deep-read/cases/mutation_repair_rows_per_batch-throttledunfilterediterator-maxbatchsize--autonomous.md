# Mutation-repair rows-per-batch opt-out (maxBatchSize == 0) — verification solution  <!-- file: cases/mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ThrottledUnfilteredIterator.java:234`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java#L234) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI (Agent SDK), 2026-10-27 |
| Estimate | `positive`: with a non-zero value the heap held per streamed Mutation is capped at about N unfiltereds per partition slice; 0 removes the cap, so one whole partition becomes one Mutation. |
| Ground | — |

**Type:** non-config (hard-coded constant: the literal `0` in the comparison; the compared value `maxBatchSize` also comes from the JVM property `cassandra.repair.mutation_repair_rows_per_batch`, so both are named)

## A. Constraint trace

**A1. The constraint.** `maxBatchSize` (rows/unfiltereds per batch), passed from `CassandraStreamReceiver`. Declared as JVM property [`REPAIR_MUTATION_REPAIR_ROWS_PER_BATCH`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L410) (`cassandra.repair.mutation_repair_rows_per_batch`, default `"100"`), read once into the static final `MAX_ROWS_PER_BATCH` at `CassandraStreamReceiver.java:63`. Unit: unfiltereds (rows and range tombstone markers). Settable only with `-D` at JVM start (static final, needs restart); not in yaml, not JMX. The check also involves the numeric literal `0` (constant rule): `0` means "no throttle", the check is `maxBatchSize == 0`. Non-zero values must be greater than 1 (assert at `ThrottledUnfilteredIterator.java:64`; with assertions off, 1 or a negative value would misbehave, since `count < throttle` is never true after the first element or at all).

**A2. What it caps.** Heap. The number of Unfilteds from one partition that are put into one `PartitionUpdate`/`Mutation` (`CassandraStreamReceiver.java:212-222`) when received sstables go through the write path (CDC, MV, or `streamToMemtable`). The compared quantity is the per-batch `count` against `throttle` (`:148`).

**A3. Mechanism.** Enclosing method: static `throttle(UnfilteredPartitionIterator, int)` at [`ThrottledUnfilteredIterator.java:232`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java#L232); the check is [`:234`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java#L234).
- True (`0`): returns the raw `partitionIterator` (`:235`); each partition is returned whole, so `PartitionUpdate.fromIterator` (`CassandraStreamReceiver.java:218`) materializes the entire partition in heap as one Mutation.
- False: wraps each partition in `ThrottledUnfilteredIterator` (`:251`), which yields sub-iterators of at most `throttle` Unfilteds (`withinLimit`, `:146-149`), plus one extra close marker when a range tombstone is open at the boundary (`:139-143`, `:108`), so a batch can reach throttle+1 elements. Each batch becomes a separate Mutation applied via `ks.apply` (`CassandraStreamReceiver.java:218-221`).
- Only caller: `CassandraStreamReceiver.sendThroughWritePath` (`:212`), reached from `finished()` only when `requiresWritePath` (`:197-212` region: CDC-on-repair, `streamToMemtable`, or MV on repair). Plain sstable streaming never goes through it.
- Bypass/overshoot: the cap is per partition slice, not per stream; wide cells/large rows in a batch still make a batch big in bytes (limit counts rows, not bytes); the +1 close marker; whole-sstable streaming (no write path) is not covered.

**A4. Other consumers.** Memtable memory after `ks.apply` (memtable_heap_space/offheap), commit log, and the scanner/reader buffers and the partition-index/key cache for the sstable being scanned are outside this cap.

**A5. Evidence beyond the source.** Code comment at `CassandraStreamReceiver.java:209-211` ("avoid OOMing and generating heap pressure"); unit test `test/unit/org/apache/cassandra/db/rows/ThrottledUnfilteredIteratorTest.java:121-170` exercises `throttle(scanner, 100)` and `throttle(scanner, 0)`. No other sources consulted.

## B. Verification solution

**B1. Claim under test.** With `maxBatchSize` = N > 1, no Mutation built by the streaming write path holds more than about N+1 Unfilteds of a partition (heap per Mutation bounded by N); with `maxBatchSize` = 0, one Mutation holds the whole partition, and peak heap grows with partition size.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to a private directory (e.g. `~/w/cass-unit`), `ant jar` there; write a CQLTester-style test beside `ThrottledUnfilteredIteratorTest` in the copy (never in the shared tree). Run `ant testsome -Dtest.name=org.apache.cassandra.db.rows.ThrottledUnfilteredIteratorTest` with `-Xmx1g`.

**B2b. Knobs.** The `maxBatchSize` argument: 0, 2, 100, 1000 (direct call to `throttle`; the property itself is static final, so the argument is the knob here).

**B2c. Workload.** Table `(pk int, ck int, v text, PRIMARY KEY(pk, ck))`; insert 1 partition with 100000 rows of 100-byte values; flush; get a scanner on the sstable (`reader.getScanner()`).

**B2d. Observables and instruments.** For each batch returned: count Unfilteds iterated (the batch size); max over batches; number of batches. Heap per Mutation: `PartitionUpdate.fromIterator(...).dataSize()` / `unsharedHeapSize()`. Peak heap is not measured here.

**B2e. Procedure.** For each N: open scanner; `throttle(scanner, N)`; loop `next()`, build `PartitionUpdate.fromIterator(it, ColumnFilter.all(metadata))`, record `update.rowCount()` and `unsharedHeapSize()`; close.

**B2f. Predictions.** N=0: 1 batch, 100000 rows, size ~ whole partition (about 10 MB data). N=2: max rows per batch 2 or 3, ~50000 batches. N=100: max 100 (101 only if a tombstone is open; none here), 1000 batches. N=1000: max 1000, 100 batches. Max batch rows follows N; unsharedHeapSize per batch scales linearly with N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| max rows per batch <= N+1 for N>1, and 1 batch with all rows for N=0 | claim confirmed |
| a batch with more than N+1 Unfilteds for N>1 | claim wrong (cap leaks) |
| N=0 still produces several batches | opt-out not working, claim wrong |
| Heap per batch not growing with N | row count not a proxy for heap here; check row size |

**B2h. Controls.** Same data and sstable for all N; repeat with rows of 10 B and 1000 B values to show bytes scale with rows x size; add a variant with an open range tombstone at the boundary to see the N+1 case.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes (RF=2) built from a private copy of the tag with `ant jar`; JDK 11; `-Xmx2g -Xms2g`, G1. Enable the write path: `cdc_enabled: true` with `cdc_on_repair_enabled: true` (default) on a table with `cdc = true`, or use a table with a materialized view and `materialized_views_on_repair_enabled: true`. Property `-Dcassandra.repair.mutation_repair_rows_per_batch=<N>` in `jvm11-server.options` of node 2 (the receiver).

**B3b. Knobs.** N = 0, 100, 10000, each on a fresh node-2 start (static final).

**B3c. Workload.** Node 1 only up (node 2 down while writing) is not needed: write with node 2 stopped via `cassandra-stress` or CQL: one wide partition of 2,000,000 rows, 200-byte values (~400 MB raw, far above the 2 GB heap's young gen), then flush node 1; start node 2 and run `nodetool repair -full <ks>` on node 2 so node 2 receives the stream. Duration: until repair finishes.

**B3d. Observables and instruments.** Node 2: `jstat -gc <pid> 1000` (heap used/GC), `jcmd <pid> GC.class_histogram` at the midpoint for `PartitionUpdate`/`BTree` instances, GC log (`-Xlog:gc*`), repair duration; logs for OOM. Not directly observable: per-Mutation size (use histogram instead).

**B3e. Procedure.** 1) Start both nodes, create keyspace RF=2 and table with `cdc=true`. 2) Stop node 2. 3) Load data on node 1; `nodetool flush`. 4) Stop node 1's writes, start node 2 with the N under test. 5) Run repair; sample as above. 6) Stop both nodes, wipe the private data dirs, repeat for next N.

**B3f. Predictions.** N=100 and N=10000: peak old/live heap during the stream stays roughly flat and low (batch <= ~20 KB for 100, ~2 MB for 10000, plus memtable); N=0: a single ~400 MB Mutation, heap peak exceeds the other runs by a few hundred MB and can OOM at -Xmx2g. Peak heap rises with N.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| peak live heap(N=0) >> peak(N=100), and rising with N | claim confirmed |
| peak heap equal across N | cap not binding on this path (check that write path was actually taken: log/histogram shows `PartitionUpdate`) or claim wrong |
| N=0 OOM, N=100 completes | strong confirmation |
| repair did not stream or did not use write path | not confirmed; fix setup |

**B3h. Controls.** Same data, JVM and sstable layout for each N; confirm the write path was taken by checking CDC commit log segments / MV updates; run once with plain table (no CDC) as negative control, where N should not change heap since the write path is not used.

**B4. Risks and cleanup.** ~1 GB disk per node for data plus commit log/cdc_raw; use a private scratch directory, not shared storage. Stop both Cassandra JVMs, `pgrep -f CassandraDaemon` must be empty; delete data, commitlog, cdc_raw and logs afterwards.

## C. Sources read

- src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java
- src/java/org/apache/cassandra/db/streaming/CassandraStreamReceiver.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 410, 794-800, 881-888)
- test/unit/org/apache/cassandra/db/rows/ThrottledUnfilteredIteratorTest.java (grep only)

## D. Stage-4 feedback

`none yet`
