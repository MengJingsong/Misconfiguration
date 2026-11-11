# SASI per-SSTable index writer in-memory segment cap (max_compaction_flush_memory_in_mb / 1 GiB flush constant) — verification solution  <!-- file: cases/sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:247` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not exposed to the agent), 2026-10-25 |
| Estimate | `positive` (with a stated looseness): the heap held by one writer's active `OnDiskIndexBuilder` is bounded by the limit plus one value's worth of tokens, as measured by the builder's own estimate; segments are cut when the estimate reaches the limit. The estimate is a hand-coded approximation (jol-derived constants), so actual heap tracks the limit only proportionally, not exactly. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** Two related limits feed the one comparison at line 247 (`maxMemorySize`, field set at `PerSSTableIndexWriter.java:201`, defined at `:365-369`):
- Flush (`source == OperationType.FLUSH`): the literal constant `1073741824L` (1 GiB) in `PerSSTableIndexWriter.java:368`. Not settable; changing it needs a code change and rebuild.
- Every other operation (compaction, index build): the per-index CQL option `max_compaction_flush_memory_in_mb`, declared at `src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java:58`, stored as `IndexMode.maxCompactionFlushMemoryInBytes` (`IndexMode.java:65`, assigned `:73`).
- Unit: bytes (option is in MiB, converted with `1048576L * Long.parseLong(...)` at `IndexMode.java:186-188`).
- Default (option absent): `DEFAULT_MAX_MEM_BYTES = (long)(1073741824 * 0.15)` = 161061273 bytes (about 153.6 MiB) (`IndexMode.java:59-60`). The comment "1G default for memtable" at `:60` and the log text "reverting to default 1GB" at `:192` are stale; the real default is 0.15 GiB.
- Sanity bound: a value above 100 GiB is replaced by the default with an error log (`IndexMode.java:190-194`).
- Set: `CREATE CUSTOM INDEX ... USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'max_compaction_flush_memory_in_mb': 'N'}`; stored in index metadata, so changing it means dropping and recreating the index (no yaml key, no JMX). Prerequisite: `sasi_indexes_enabled: true` in cassandra.yaml (`conf/cassandra.yaml:1992`, `Config.java:606`; enforced at `CreateIndexStatement.java:122`), which needs a restart.
- The option is not rejected for being non-numeric by any validation I found other than `Long.parseLong` throwing at `IndexMode.java:188` (not checked further).

**A2. What it caps.** Heap. The compared quantity is `currentBuilder.estimatedMemoryUse()` (`PerSSTableIndexWriter.java:247`), which returns `OnDiskIndexBuilder.estimatedBytes` (`OnDiskIndexBuilder.java:148`, `:199-202`). That is the sum of the in-memory `terms` map entries (`OnDiskIndexBuilder.java:143`): per new term `64 + 48 + term.remaining()` (`:182`), and per `add` call `60 + 40 + 8` = 108 (`:194`). The constants are jol-based hand estimates (comments at `:180-181`, `:191-193`). The on-disk segment files and the final merged index are not counted.

**A3. Mechanism.**
1. `PerSSTableIndexWriter.Index` is created per indexed column per SSTable writer; its constructor reads `maxMemorySize(columnIndex)` once (`:195-203`, `:201`) and makes a fresh `OnDiskIndexBuilder` (`:202`, `:354-357`).
2. `nextUnfilteredCluster` (`:121-138`) pulls the column value and calls `Index.add` (`:136`).
3. `Index.add` (`:205-251`) runs the analyzer; each token of size >= `MAX_TERM_SIZE` (1024, `OnDiskIndexBuilder.java:128`) is rejected (`:218-227`); invalid tokens are dropped unless upcastable (`:229-241`); accepted tokens go to `currentBuilder.add` (`:243`), which re-checks the 1024 limit (`OnDiskIndexBuilder.java:167-173`), puts the term in the map and adds to `estimatedBytes` (`:175-194`).
4. After all tokens of the value: if nothing was added or `estimatedMemoryUse() < maxMemorySize`, return (`:247-248`). Otherwise (estimate >= limit) a segment flush is submitted: `scheduleSegmentFlush(false)` swaps `currentBuilder` for a new empty builder (`:256-257`) and returns a callable that calls `builder.finish(segmentFile)` (`:261-266`), executed on `SASI-Memtable` (flush) or `SASI-General` (all else) pool, each fixed at `POOL_SIZE = 8` (`:63-73`, `:349-352`). The future is stored in `segments` (`:250`). Segment files are `<outputFile>_<n>` (`:359-362`). A log line "Flushed index segment" is written per segment (`:276`).
5. `complete()` (`:140-161`, `Index.complete` `:281-347`): with no prior segments, the whole index is built from memory (`:293-297`); otherwise the remaining builder is flushed inline (`:300-304`) and all segments are merged with `CombinedTermIterator` into the final file (`:320-323`); segment files are deleted at `:334-342`.
6. Where `source` comes from: `SASIIndex.getFlushObserver` passes `tracker.opType()` (`SASIIndex.java:332-335`, `newWriter` at `:374-380`). Memtable flush gives FLUSH; initial index build/rebuild goes through `SASIIndexBuilder`, which hard-codes `OperationType.COMPACTION` (`SASIIndexBuilder.java:85`).

Outcomes at the limit: the only action is to cut a segment and start a new builder (heap released after the async write completes). Nothing fails or blocks.
Overshoot/bypass paths:
- The check runs after a whole value is analyzed, so the builder can exceed the limit by the tokens of one value (an analyzed text value can yield many tokens; each is below 1024 bytes).
- Submitted builders live until the executor writes them; the executor (8 threads) has a queue and the writer never waits on it (`:250`), so several full-size builders can be alive at once if disk is slower than ingestion. I did not confirm whether the pool queue is bounded (`executorFactory().pooled(...)`, `:69-73`) and treat it as unbounded until read.
- `estimatedBytes` is only an estimate (no ByteBuffer/HashMap-node overhead, and a fixed 108 bytes added on every add even when the token and term already exist, which overestimates repeat terms).
- The flush path ignores the option (`:368`).
- Cap is per column-index per writer, not per node: N indexed columns and K concurrent writers multiply it.

**A4. Other consumers.** SASI in-memory memtable index (`src/java/org/apache/cassandra/index/sasi/memory/TrieMemIndex.java:49`, size-estimating trie factory `:245`) on the same heap, governed by memtable settings and not by this option; the `OnDiskIndex` objects and their mmapped/off-heap file access for reads; the base-table memtable, key/row caches, compaction itself, and the final merge in `complete()` (`:320-323`).

**A5. Evidence beyond the source.** None consulted online (design done from the tree only). In-tree evidence: `test/unit/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriterTest.java:84-177` drives the writer, forces segment flushes by hand (`:133`) and checks segment files appear and disappear (`:138-147`); it does not exercise the limit comparison itself (no match for `maxMemorySize` or `estimatedMemoryUse` under `test/`).

## B. Verification solution

**B1. Claim under test.** The writer cuts a new on-disk segment whenever the active builder's estimate reaches `maxMemorySize`, so the number of segments and the live heap of the active builder scale with the limit as `ceil(limit / per-entry-estimate)` entries per segment (unit tier), and the actual heap used by an index build on a node follows `max_compaction_flush_memory_in_mb` (cluster tier). It is falsified if the segment count does not change with the option, if the builder estimate exceeds limit by more than one value, or if live heap during an index build does not drop when the option is lowered.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk: `rsync -a ~/cassandra-5.0.9/ /local/$USER/c509/`; `cd /local/$USER/c509 && ant jar` (not in the shared copy). Add the test in `test/unit/org/apache/cassandra/index/sasi/disk/PerSSTableIndexLimitTest.java` (same package as `PerSSTableIndexWriterTest`, so the protected `Index.segments` and `indexes` are visible; model it on `PerSSTableIndexWriterTest.java:68-177`, including its `SchemaLoader` setup). Run: `ant testsome -Dtest.name=PerSSTableIndexLimitTest -Dtest.methods=...`. JVM: default test options plus `-Xmx2g`.

**B2b. Knobs.** `max_compaction_flush_memory_in_mb` in the table's SASI index options, values 1, 4, 16 and absent (default 161061273 bytes). Created via a table per value in the test schema (one keyspace, four tables, one `Int32Type` column `age` with a custom SASI index and the option). Writer built with `sasi.getFlushObserver(descriptor, LifecycleTransaction.offline(OperationType.COMPACTION))` (as at `PerSSTableIndexWriterTest.java:97` but with COMPACTION). Second configuration: `OperationType.FLUSH` with the same four tables, expecting the option to be ignored (limit 1 GiB).

**B2c. Workload.** 100000 rows, unique `Int32` values 0..99999 and unique partition keys (`"key%06d"` as at `:87`), each fed via `startPartition` then `nextUnfilteredCluster` (as at `:126-128`). Per-entry estimate for a unique 4-byte term: `64+48+4` (`OnDiskIndexBuilder.java:182`) + `60+40+8` (`:194`) = 224 bytes. Entries until estimate >= limit (first count n with 224n >= L):
- 1 MiB (1048576): n = 4682 (4681*224 = 1048544 < L; 4682*224 = 1048768).
- 4 MiB (4194304): n = 18725.
- 16 MiB (16777216): n = 74899.
- default (161061273): n = 719024, which is above 100000.
- FLUSH (1073741824): n = 4793491, above 100000.
Segments cut during the 100000 adds: 1 MiB -> 21 (21*4682 = 98322, 22*4682 = 103004 > 100000 [Amended 2026-10-26, B5.1: was 102998]); 4 MiB -> 5 (5*18725 = 93625); 16 MiB -> 1; default -> 0; FLUSH -> 0.

**B2d. Observables and instruments.**
- `index.segments.size()` after the adds and before `complete()` (field `PerSSTableIndexWriter.java:190`), after waiting on each future to avoid races (iterate `segments`, `get()`).
- Segment files `<outputFile>_<n>` on disk in the table's data directory (`file()` at `:359-362`), listed before `complete()`.
- The builder's estimate: reflectively read `currentBuilder` (private, `:193`) then `estimatedMemoryUse()` (`OnDiskIndexBuilder.java:199`) after every add; record the max seen and the value just before each segment is cut. Alternative without reflection: subclass `PerSSTableIndexWriter` is not enough (the `Index` class is protected, `newIndex` is overridable at `:173-177`), so reflection is the plan.
- Optional heap cross-check: with the 16 MiB table only, after the adds run `System.gc()` twice and compare `Runtime.totalMemory()-freeMemory()` before the load and with the writer still referenced; report ratio only (the estimate is approximate). Not observable directly: true retained size of the builder without a heap dump (use `jcmd <pid> GC.heap_dump` in a separate run if needed).

**B2e. Procedure.**
1. Build as in B2a; write the test with a helper `run(tableName, opType)` returning (segments, maxEstimate, estimateAtCut[]).
2. For each of the four tables with COMPACTION: run the workload, wait for segment futures, record observables, then call `indexWriter.complete()` and verify segment files are gone and the final index has all 100000 terms (reuse the check at `PerSSTableIndexWriterTest.java:149-176`).
3. Repeat with FLUSH on the 1 MiB table.
4. Cleanup: the test harness removes its data directory; verify `ls` of the data dir is empty of `*_N` files.

**B2f. Predictions (before any run).**
| Config | Segments cut before `complete()` | Estimate at each cut | Max estimate seen |
|---|---|---|---|
| COMPACTION, 1 MiB | 21 | 1048768 (= 4682*224) | 1048768, i.e. limit + at most 224 |
| COMPACTION, 4 MiB | 5 | 4194400 | 4194400 |
| COMPACTION, 16 MiB | 1 | 16777376 (= 74899*224) | 16777376 |
| COMPACTION, default | 0 (one final segment from `complete()` at `:293-297`) | n/a | 22400000 (100000*224) |
| FLUSH, 1 MiB option | 0 | n/a | 22400000 (option ignored) |
Estimate never exceeds limit by more than one add (224 bytes here, since one token per value).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| Segment counts and cut estimates match the table | Mechanism works as traced; limit governs the builder's estimate |
| Segment count identical across 1/4/16 MiB | Option not applied (claim wrong); check `IndexMode.java:186-188` path |
| FLUSH run with 1 MiB option cuts 21 segments | Flush path uses the option, contradicting `:368` |
| Max estimate well above limit + one value | Check bypassed or async path leaks; claim wrong |
| Estimate matches but `Runtime` heap ratio vs estimate far from 1 (e.g. 3x) | Mechanism works on the estimate but the estimate understates real heap; report as looseness (does not by itself refute the claim) |
| Counts off by a few (not by 2x) | Constant differences in the estimator; recompute per-entry bytes from observed cuts |

**B2h. Controls.** Default table (no option) is the no-cap control at this workload size. FLUSH vs COMPACTION on the same table separates the two limit sources. Run each table in a fresh JVM-invocation (or fresh keyspace) so executor state and heap are not shared; fix the key set so only the option varies.

### B3. Cluster tier

**B3a. Environment and build.** One node, local build from the same local copy (`ant jar`), run from `/local/$USER/c509` with data, commitlog, hints and saved_caches on local disk of known size (>= 20 GB free, directories set in cassandra.yaml). JDK 11. `cassandra.yaml`: `sasi_indexes_enabled: true`, `num_tokens: 1`, `concurrent_compactors: 1`, `memtable_heap_space: 256MiB`. `conf/jvm11-server.options`/`jvm-server.options`: `-Xms2G -Xmx2G`, G1, `-XX:+HeapDumpOnOutOfMemoryError` to a local path. Enable JMX locally only.

**B3b. Knobs.** `max_compaction_flush_memory_in_mb` = 8, 32, 128 (three separate index builds, each on a fresh index) and a no-cap run with 1024 (1 GiB; below the 100 GiB sanity bound at `IndexMode.java:190`). Set through `CREATE CUSTOM INDEX`. The flush-path constant (`PerSSTableIndexWriter.java:368`) is not tunable at runtime, so the flush path is only checked in the unit tier.

**B3c. Workload.** Table `ks.t (id bigint primary key, v int)`; load 3,000,000 rows with unique `v` values (cqlsh `COPY` or a small Java/Python driver script from the same host), then `nodetool flush ks t` and `nodetool disableautocompaction ks t` so there is no SASI index when the data is written. Estimated total builder footprint if never cut: 3,000,000 * 224 B (unique 4-byte term) = 672,000,000 B (about 641 MiB), below the 2 GiB heap so the no-cap run is safe. Index build via `CREATE CUSTOM INDEX t_v ON ks.t(v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'SPARSE','max_compaction_flush_memory_in_mb':'N'}` (SPARSE suits int columns; set mode identically for all runs), which uses the `SASIIndexBuilder` COMPACTION-typed writer (`SASIIndexBuilder.java:85`). Entries per segment = ceil(N MiB / 224): 8 MiB -> 37450, 32 MiB -> 149797, 128 MiB -> 599187, so segments cut: floor(3,000,000/n) = 80, 20, 5; 1024 MiB -> 0. Duration: the build runs minutes; sample for its full length.

**B3d. Observables and instruments.**
- Log: count of `Flushed index segment` lines in `system.log` (`PerSSTableIndexWriter.java:276`) per run, and the `Index flush to ... took` line (`:332`) for end time.
- Heap: `jcmd <pid> GC.heap_info` every 2 s and `jcmd <pid> GC.class_histogram` every 10 s; track instance bytes of `org.apache.cassandra.index.sasi.disk.DynamicTokenTreeBuilder` plus `it.unimi.dsi.fastutil.longs.LongOpenHashSet` (names via the histogram) as the builder's live footprint; peak GC-log "heap after GC" (`-Xlog:gc*:file=/local/$USER/gc.log`).
- Disk: `du -sb` on the data directory every 5 s (segment files `*_N` appear and disappear).
- Not observable directly: the builder's own `estimatedBytes`; use the unit tier for that.

**B3e. Procedure.**
1. Copy source, build, configure as B3a; start the node; confirm `nodetool status`.
2. Create keyspace/table; load rows; `nodetool flush`; `nodetool disableautocompaction ks t`.
3. For N in 8, 32, 128, 1024: start samplers; create the index with the option; wait for `nodetool compactionstats` to show no index build; record; `DROP INDEX ks.t_v`; `nodetool clearsnapshot`; wait for the samplers' idle baseline; next N.
4. Optional second pass in a different order (1024 first) to rule out order effects.
5. Stop the node (`nodetool drain`; kill the JVM), stop samplers, `pgrep -u $USER -f 'CassandraDaemon|jcmd'` to confirm none left, delete the local data directories.

**B3f. Predictions (before any run).**
- `Flushed index segment` counts: about 80 (8 MiB), 20 (32 MiB), 5 (128 MiB), 0 (1024 MiB), each within +-1. **[Amended 2026-10-26, B5.3: the log line is also written for the tail builder flushed inline by `complete()` (`PerSSTableIndexWriter.java:300-304`, logged at `:276`), so with one sstable the counts are cuts + 1: 81 (8 MiB), 21 (32 MiB), 6 (128 MiB), 0 (1024 MiB; the all-in-memory path `:293-297` is final and logs nothing), and 5 (default, 4 cuts + tail), each within +-1. Segments cut remain 80/20/5/0/4.]**
- Peak live bytes in builder objects (histogram) per run: approximately proportional to N while the build runs: smallest at 8 MiB, largest at 1024 MiB. A 128x ratio in N should give a ratio well above 5x in peak builder bytes between 8 and 1024 MiB; the 1024 MiB run's peak should be near the whole-index footprint (about 641 MiB estimated, actual different by a constant factor).
- Peak heap after GC is monotone in N and the 8 MiB run stays near the idle baseline plus the other consumers.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| Segment counts near 80/20/5/0 and peak builder bytes ordered by N | The option governs actual heap during index build; claim confirmed |
| Segment counts match but peak heap after GC flat across N | Cap cuts files but heap is dominated by something else (executor-queued builders, memtable); claim not confirmed for actual heap; look at queued builders (A3 bypass) |
| Counts do not change with N | Option not effective; claim wrong |
| 1024 MiB run peaks at about the same as 8 MiB | Estimate not tied to real memory; claim wrong |
| Peak builder bytes in 8 MiB run far above 8 MiB * k with many builder instances alive at once | Queued/in-flight segments bypass the cap (executor lag); report overshoot factor |
| A run's peak never rises (e.g. rebuild finishes too fast) | Limit not reached, not confirmed; increase rows |
| The 1024 MiB arm dies with OutOfMemoryError while the smaller caps complete **[added 2026-10-26, B5.5]** | Uncapped builder outgrows the heap: consistent with heap following the cap, but no peak numbers; the arm is repeated with a larger heap before the verdict, else Not confirmed |

**B3h. Controls.** The 1024 MiB run is the no-effective-cap control on identical data; run it first and last. Same data, same JVM options, same machine; disable autocompaction and keep memtable settings fixed so only the index build uses heap beyond baseline; take an idle baseline before each run; keep the key/row caches at defaults but unused (no reads). Because the 128 MiB value is close to the default (153.6 MiB), a run without the option (default) can be added as a cross-check expecting 3,000,000/719024 = 4 segments.

**B4. Risks and cleanup.** Disk: data (about 3M rows, under 1 GB) plus segment files (up to about the index size) on local disk with >= 20 GB free; do not use shared storage. Heap dumps only if OOM, on local disk, delete after. Processes: the node, samplers, any driver scripts; verify with `pgrep` and `jps`. Cleanup: `DROP INDEX`, drop keyspace, delete data/commitlog/hints/gc.log, remove `/local/$USER/c509`. Unit tier test data is under the build tree's `build/test/cassandra`; `ant clean` after.

### B5. Step-0 audit amendments (stage 4, 2026-10-26; reasons independent of any reading)

1. Arithmetic: `22*4682 = 103004`, not 102998 (B2c). All other B2c/B3c per-entry arithmetic (224 B; n = 4682, 18725, 74899, 719024, 4793491, 37450, 149797, 599187; cuts 21/5/1/0/0 and 80/20/5/4) re-computed and correct. Every line cite in A1-A5 re-read against `cassandra-5.0.9`; no wrong cite found (`TrieMemIndex.java:49,:245`, `PerSSTableIndexWriterTest.java:97,:133,:138-147` included).
2. Unit tier construction: the test is `CapProbeTest` (package `org.apache.cassandra.index.sasi.disk`), copied into a `copy-source.sh` tree (`~/s4-pm`); it builds the `PerSSTableIndexWriter` directly with the public constructor and a `ColumnIndex` carrying the option (Int32 column, PREFIX), instead of four schema tables through `getFlushObserver`; the `tracker.opType()` wiring (`SASIIndex.java:332-335`) is exercised only in the cluster tier (COMPACTION). Arms: COMPACTION 1/4/16 MiB and default, FLUSH with 1 MiB option and FLUSH default. `ant testsome` forks a 1 GiB JVM (no `-Xmx2g`). The heap cross-check is taken in every arm (active builder only, after waiting on the segment futures). Also recorded: estimate at every cut, `Flushed index segment` log count (cuts + 1 when any cut), final index term count.
3. B3f log counts: see the inline amendment (cuts + 1 per sstable). The cluster arithmetic is per sstable, so after the load the table is flushed and major-compacted to exactly one sstable (before any index exists, autocompaction then disabled).
4. Queued builders (A3 unchecked item): the executor queue is unbounded, `ThreadPoolExecutorBuilder.newQueue()` gives `Integer.MAX_VALUE` when no limit is set (`ThreadPoolExecutorBuilder.java:160-168`), and the writer never waits (`PerSSTableIndexWriter.java:250`); so the cap on live builders is not bounded by the design, only by how fast 8 threads drain. Observed by the SASI-General pending-task count over JMX (250 ms) and `OnDiskIndexBuilder` instance counts in class histograms (taken back to back, each forces a full GC so reads live bytes).
5. Heap: 2 GiB is too tight by the unit-tier ratio expectation (real heap about 1.7x the estimate: the 672 MB estimate for 3M entries is about 1.2 GB live, plus the merge in `finish`). Instrument shakedown (300,000 rows then 3,000,000 rows, not readings) showed the uncapped build peaking within 0.2 GiB of 2 GiB, so the cluster node uses `-Xms3G -Xmx3G`. Added B3g row for an OOM at 1024 MiB.
6. Stale text confirmed: `IndexMode.java:60` comment "1G default for memtable" and `:192` "reverting to default 1GB" while the default is 0.15 GiB (161,061,273 B). `PerSSTableIndexWriter.java:367` ("1G for memtable and configuration for compaction") is correct. Reported as a note for stage 3, no effect on the claim.
7. Cluster details: index mode SPARSE, ports JMX 7332 / native 9354 / storage 7032 / loopback 127.0.32.1; arm order 1024, 8, 32, 128, default, 1024 (control first and last, default cross-check added), one node, one load; 3,000,000 rows (`id bigint`, `v int` = id).

## C. Sources read

- `~/writeup-A/playbook-autonomous.md`
- `~/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java`
- `src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java` (lines 120-205)
- `src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java` (lines 52-80, 100-200)
- `src/java/org/apache/cassandra/index/sasi/SASIIndex.java` (lines 328-380)
- `src/java/org/apache/cassandra/index/sasi/SASIIndexBuilder.java` (lines 50-100)
- `src/java/org/apache/cassandra/index/sasi/memory/TrieMemIndex.java` (grep only)
- `src/java/org/apache/cassandra/config/Config.java`, `DatabaseDescriptor.java` (grep only)
- `src/java/org/apache/cassandra/cql3/statements/schema/CreateIndexStatement.java` (grep only)
- `conf/cassandra.yaml` (lines 1985-1993)
- `test/unit/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriterTest.java` (lines 68-178)

## D. Stage-4 feedback

**2026-10-26, stage 4 ([results](../../stage4-runtime-verification/results/sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous.md)).** Unit tier: Confirmed, caps (segments 21/5/1/0 at 1/4/16 MiB/default, estimate at every cut exactly n*224; FLUSH ignores the option). Cluster tier: Confirmed, caps (3M rows, one sstable: `Flushed index segment` 81/21/6/5/0 at 8/32/128/default/1024 MiB; peak live heap 77/305/1012/1171/about 1500 MB). Outcome class: true positive. Looseness found: real heap is about 1.8x the estimate (about 400 B per entry vs 224) and up to 5 builders are alive at once (peak 4 to 5 times one builder); queue unbounded by source but never pending here. Notes for stage 3: log lines are cuts + 1 (tail flush logs too); 2 GiB heap was too tight for the uncapped 3M-row build; stale 1G text at `IndexMode.java:60,:192`.
