# max_compaction_flush_memory_in_mb — verification solution  <!-- file: cases/max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`IndexMode.java:190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java#L190) ([`src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java:190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java#L190)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `positive`: the option sets the threshold at which the SASI index writer flushes its in-memory term builder to an on-disk segment for every non-FLUSH operation (compaction, index build), so builder memory per index per writer is bounded by roughly that value plus one add. The bound is on a hand-coded size estimate, not on measured heap, so the real heap/limit ratio is what stage 4 must check. The entry line itself (190) is only a 100 GiB sanity cap and is not the enforcement point. |
| Ground | — |

> **Link rule.** The constraint's declaration (A1) and the if statement (Entry pointer row and A3) are links at tag `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `max_compaction_flush_memory_in_mb`; kind: per-index SASI option (a key in the index options map given in `CREATE CUSTOM INDEX ... WITH OPTIONS`), not a cassandra.yaml entry and not a JVM property. Declared as the string constant `INDEX_MAX_FLUSH_MEMORY_OPTION` at [`IndexMode.java:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java#L58). Unit: MiB as written by the user; `getMode` multiplies by `1048576L` into bytes (`IndexMode.java:186-188`) and the result is stored in the public field `maxCompactionFlushMemoryInBytes` (field `IndexMode.java:65`, assigned in the constructor at `IndexMode.java:73`, constructed at `IndexMode.java:195`). Default when the option is absent: `DEFAULT_MAX_MEM_BYTES` (`IndexMode.java:60`) = `(long)(1073741824 * 0.15)` where 0.15 is `INDEX_MAX_FLUSH_DEFAULT_MULTIPLIER` (`IndexMode.java:59`), i.e. 161061273 bytes (0.15 GiB). The trailing comment on line 60 ("1G default") and the log text at `IndexMode.java:192` ("reverting to default 1GB") disagree with that arithmetic; the code value is 0.15 GiB. `IndexMode.NOT_INDEXED` uses 0 (`IndexMode.java:46`) but a NOT_INDEXED mode has no index writer (`ColumnIndex.java:211`). How it is set: only through the index options map when the index is created (`IndexMode.getMode` reads it at `IndexMode.java:186`, called from `ColumnIndex.java:79` and from `SASIIndex.validateOptions` at `SASIIndex.java:174`). No yaml key, `-D` property or JMX setter for it exists (grep of `src/java` for the string found only `IndexMode.java`). `ColumnIndex.mode` is a final field (`ColumnIndex.java:67`), so changing it requires dropping and recreating the index (or an ALTER that re-instantiates the index; not verified). SASI creation itself needs `sasi_indexes_enabled: true` in cassandra.yaml (`Config.java:606`, default false; check in `CreateIndexStatement.java:122`; yaml line `conf/cassandra.yaml:1992`), which needs a restart. The option is parsed with `Long.parseLong` with no lower bound check (`IndexMode.java:188`): a non-numeric value throws NumberFormatException, a negative or overflowing value is not rejected (the only check is the upper bound at line 190).

**A2. What it caps.** On-heap memory (Java objects), with a derived effect on disk: the term/token-tree builder `OnDiskIndexBuilder` that a SASI `PerSSTableIndexWriter.Index` accumulates before writing a segment file. The quantity compared is `currentBuilder.estimatedMemoryUse()`, a running sum of fixed per-term and per-add constants (`OnDiskIndexBuilder.java:182` adds `64 + 48 + term.remaining()` for each new term; `OnDiskIndexBuilder.java:194` adds `60 + 40 + 8` for each add; getter `OnDiskIndexBuilder.java:199-201`). It is compared with `maxMemorySize`, the per-Index copy of the limit (`PerSSTableIndexWriter.java:187`, `:201`).

**A3. Mechanism.**
1. `getMode` computes `maxMemBytes` from the option or the default (`IndexMode.java:186-188`).
2. The entry check: [`if (maxMemBytes > 100L * 1073741824)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java#L190) (100 GiB). When true, it logs an error and resets to `DEFAULT_MAX_MEM_BYTES` (`IndexMode.java:192-193`); when false the value is kept. It is a sanity cap only: any value up to 100 GiB passes, so it does not bound memory in practice. Integer overflow of `1048576L * parsed` can wrap to a negative number that also passes (not exercised; reasoning only).
3. Enforcement: `PerSSTableIndexWriter.maxMemorySize` returns the hard-coded `1073741824L` (1 GiB) when `source == OperationType.FLUSH`, otherwise `columnIndex.getMode().maxCompactionFlushMemoryInBytes` (`PerSSTableIndexWriter.java:368`); it is called from the `Index` constructor (`PerSSTableIndexWriter.java:201`).
4. Per added term: `Index.add` adds the token to `currentBuilder` (`PerSSTableIndexWriter.java:243`; terms of 1024 bytes or more are rejected at `PerSSTableIndexWriter.java:218`, `MAX_TERM_SIZE` = 1024 at `OnDiskIndexBuilder.java:128`), then the check [`currentBuilder.estimatedMemoryUse() < maxMemorySize`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java#L247) at `PerSSTableIndexWriter.java:247`.
5. Outcomes: below the limit (or nothing added) the method returns and the builder keeps growing; at or above it, `scheduleSegmentFlush(false)` is submitted to the executor (`PerSSTableIndexWriter.java:250`), which swaps in a fresh builder immediately (`currentBuilder = newIndexBuilder()` inside `scheduleSegmentFlush`, `PerSSTableIndexWriter.java:257`) and writes the old one to a `_N` segment file in the background; at completion the segments are merged into the final index file (`Index.complete` at `PerSSTableIndexWriter.java:281`; `:302-303` handles the last in-memory part).
6. Which operations use the option: compaction (index writers are created per compaction output) and `SASIIndexBuilder` index builds, which pass `OperationType.COMPACTION` (`SASIIndexBuilder.java:85`); memtable flushes use the fixed 1 GiB (`PerSSTableIndexWriter.java:368`) and ignore the option.
Bypasses and overshoot: (a) the check runs only after a term was added, so the builder exceeds the limit by up to one add's worth before flushing; (b) the compared value is a constant-based estimate (comments at `OnDiskIndexBuilder.java:178-180` and `:191-193` say the sizes come from jol; the estimate ignores TreeMap/array overhead growth and the real size of the `LongOpenHashSet` as it grows with many keys per term); (c) the swapped-out builder stays on heap until its flush task on the executor completes (pool of 8 threads per executor, `PerSSTableIndexWriter.java:63`, `:69-73`), and the executor queue is unbounded as far as this code shows (not verified), so with a fast producer several full builders can be alive at once; (d) the limit is per index per writer, so N indexed columns, or several concurrent compactions or index builds, multiply it; (e) the FLUSH path ignores it (step 6); (f) with the option set to 0 or a negative value the check is always false-to-flush, producing one segment per add (disk and CPU cost, not a memory bound problem).


The check itself is the if statement at [`IndexMode.java:190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java#L190).

**A4. Other consumers.** Heap: the memtable's own SASI in-memory index (`TrieMemIndex`, `TrieMemIndex.java:59`) which is sized by the memtable limits, not this option; the on-disk indexes opened as `OnDiskIndex` (mmapped, off-heap) after the segments are written; the segment merge in `complete` (`Index.complete`, `PerSSTableIndexWriter.java:281`, not read in full); compaction buffers and chunk cache; the node's other memtables, key cache, etc. Disk: the segment files `_N` plus the final index and the SSTable being written.

**A5. Evidence beyond the source.** `none` beyond the code read. (The Cassandra docs describe SASI index options; not consulted, so no claim relies on them.)

## B. Verification solution

**B1. Claim under test.** For a SASI index created with `max_compaction_flush_memory_in_mb = M` (1 <= M <= 100*1024), a compaction or index-build writer flushes its in-memory builder to a segment whenever the builder's estimate reaches `M * 1048576`, so the live builder's estimated size, and the on-heap size of live `OnDiskIndexBuilder` data, stays near or below `M MiB` (plus one add) while the number of segment files rises as M falls; the FLUSH path is unaffected by M. Evidence that the claim is wrong: builder estimate or heap grows past M * 1 MiB by more than one add, or segment count does not depend on M.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, a copy of the tag on local disk (`rsync -a /users/jason92/cassandra-5.0.9/ /local/work/c509/`, never build in the shared tree). `ant jar` in the copy. Put a JUnit test (or a `main` class on the built classpath, `build/classes/main` + `lib/*.jar`) in the copy under `test/unit/org/apache/cassandra/index/sasi/disk/`. JVM options: `-Xmx512m -Dcassandra.config=file:///local/work/c509/test/conf/cassandra.yaml`, with `DatabaseDescriptor.daemonInitialization()` (or `clientInitialization`) called first (not verified which the test harness needs). Test hooks: `PerSSTableIndexWriter.Index` and `newIndex` are `@VisibleForTesting` and protected (`PerSSTableIndexWriter.java:180` and `:174`), so a subclass in the same package can read `segments`.

**B2b. Knobs.** `max_compaction_flush_memory_in_mb` in the options map passed to `IndexMode.getMode(column, Map)` (public static, `IndexMode.java:126`): `"1"`, `"8"`, `"64"`, absent (default, 161061273 bytes), `"0"`, and `"102401"` (above 100 GiB, expects reset to default). Why: 1 and 8 give small thresholds reachable with few terms; 64 and absent show the larger tail; 0 shows the lower edge; 102401 exercises the entry line 190. Also `OperationType`: `COMPACTION` vs `FLUSH`.

**B2c. Workload.** Build a `ColumnIndex` (or directly a `PerSSTableIndexWriter` with a one-column map) for a text column and feed N rows with unique 16-byte terms and one key each. Per unique term the estimate grows by 64+48+16 plus 60+40+8 = 236 (`OnDiskIndexBuilder.java:182`, `:194`). For M = 1 (1048576 bytes) the first flush is expected after ceil(1048576/236) = 4443 terms; for M = 8 after 35545 terms. Use N = 200000 terms so M = 1 gives about 45 segments, M = 8 about 5, M = 64 none until the final flush, default none. For the FLUSH control, use the same N with `OperationType.FLUSH` (threshold 1 GiB, about 4.5 million terms, so zero intermediate segments).

**B2d. Observables and instruments.** (1) `Index.segments.size()` after the adds and before `complete`; (2) `currentBuilder.estimatedMemoryUse()` sampled after every add through reflection or a subclass (field `currentBuilder` is private at `PerSSTableIndexWriter.java:193`; via reflection); (3) `maxMemorySize` read by reflection (`PerSSTableIndexWriter.java:187`); (4) `IndexMode.maxCompactionFlushMemoryInBytes` (public, `IndexMode.java:65`); (5) optional heap check: `Runtime.totalMemory()-freeMemory()` after `System.gc()` or a JFR/`jcmd GC.class_histogram` count of `OnDiskIndexBuilder`. Not observable directly: the true retained size of the builder (only the estimate; the histogram approximates it).

**B2e. Procedure.**
1. Copy the tree and build: `cd /local/work/c509 && ant jar`.
2. For each M in the list, call `IndexMode.getMode(column, Map.of("mode","CONTAINS"/"PREFIX","max_compaction_flush_memory_in_mb", M))` and assert `maxCompactionFlushMemoryInBytes`.
3. Construct the writer with `OperationType.COMPACTION`, call `startPartition` per row and `nextUnfilteredCluster` (or `Index.add(term, key, pos)` directly), recording max observed estimate and `segments.size()`.
4. Repeat with `OperationType.FLUSH` for the control.
5. Run with `ant testsome -Dtest.name=<class>` or `java -cp ... <MainClass>`.
6. Stop the JVM and remove temp output.

**B2f. Predictions** (stated before any run). `getMode` returns 1048576, 8388608, 67108864, 161061273, 0 and 161061273 for the six inputs (the last because 102401 MiB = 107374182400 > 100 GiB = 107374182400? note: 100 GiB equals 107374182400 and 102400 MiB equals exactly that, so 102400 would pass and 102401 is rejected by the strict `>`). Max observed estimate for COMPACTION stays below M * 1048576 + 236 for each M. Segment counts about floor(N*236/limit): M=1 about 45, M=8 about 5, M=64 and default 0. M=0 yields one segment per add. FLUSH yields 0 intermediate segments for every M.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Max estimate stays under `M*1048576 + one add`; segment count falls as M rises; FLUSH shows none | claim confirmed for the mechanism |
| Max estimate exceeds the limit by far more than one add before a segment appears | mechanism does not cap as traced; claim wrong |
| Segment count identical across M values | option is not effective in this path; claim wrong |
| M=102401 shows the limit not reset to default | line 190 logic wrong |
| FLUSH segment count changes with M | A3 step 6 wrong |
| Limit never reached (segments = 0 for all M) | N too small; not confirmed, rerun with a larger N |

**B2h. Controls.** The FLUSH run with the same data (limit fixed at 1 GiB, `PerSSTableIndexWriter.java:368`); the default-value run; two runs of the same M for variance; constant term length so the arithmetic is predictable; same JVM heap for all runs.

### B3. Cluster tier

**B3a. Environment and build.** One node, Linux, JDK 11, Ant, built from a local copy (`ant jar` in `/local/work/c509`). Data, commitlog, hints and saved caches on a local disk of known free size (at least 20 GiB free). cassandra.yaml: `sasi_indexes_enabled: true` (`Config.java:606`); JVM `-Xms2G -Xmx2G` (via `conf/jvm11-server.options`/`jvm-server.options`, names not verified), G1; `compaction_throughput` unthrottled (`nodetool setcompactionthroughput 0`) for speed.

**B3b. Knobs.** The index option `max_compaction_flush_memory_in_mb` set at index creation: `1`, `16`, `128`, and absent (default 161061273 bytes), one fresh table/index per value (the option cannot be changed in place, A1). Reason: 1 and 16 force many segments; 128 and default exceed what a modest load reaches. Fixed: heap 2 GiB.

**B3c. Workload.** Table `ks.t(id bigint primary key, v text)`, one SASI index `... USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'CONTAINS','max_compaction_flush_memory_in_mb':'M'}`. Load 3,000,000 rows with unique 16-character `v` values (for example via `cassandra-stress` user profile or a `cqlsh COPY`) in several flushes so that SSTables exist, then trigger the build with `nodetool rebuild_index ks t <index>` (runs SASIIndexBuilder with `OperationType.COMPACTION`, `SASIIndexBuilder.java:85`) and also `nodetool compact ks t`. Estimate per unique term is 236 + len adjustments (A3); the full SSTable is about 3,000,000 * 236 = 708,000,000 bytes of estimate, so M=1 should produce about 675 segments, M=16 about 42, M=128 about 5, default about 4 (the 161061273-byte limit), more if CONTAINS mode adds several terms per value (analysis of CONTAINS tokenization not verified; use `mode PREFIX` to keep one term per value if the count is off). Duration: one rebuild per value, minutes each.

**B3d. Observables and instruments.** (1) `system.log` lines "Flushed index segment ... took N ms" (`PerSSTableIndexWriter.java:276`) counted per run; (2) the `_N` segment files appearing and disappearing in the data directory, sampled each second with `ls`/`inotifywait`; (3) heap: `jcmd <pid> GC.class_histogram` every 5 s during the build, reading instances and bytes of `OnDiskIndexBuilder`, `DynamicTokenTreeBuilder` and `it.unimi.dsi.fastutil.longs.LongOpenHashSet` (class name not verified); (4) `jstat -gc <pid> 1000` for old gen occupancy; (5) final index file size on disk. Not directly observable: the builder estimate (only inferable from segment count).

**B3e. Procedure.**
1. Copy and build the tree; set yaml; start the node; confirm `nodetool status`.
2. For each M: create keyspace/table/index with the option; load data; `nodetool flush`.
3. Start sampling (histogram, jstat, ls), run `nodetool rebuild_index`, wait for completion (`nodetool compactionstats` empty), stop sampling.
4. Count segment log lines; record peak histogram bytes of the builder classes.
5. Drop the table before the next M.
6. Stop the node, check no process remains (`pgrep -u $USER -f CassandraDaemon`), delete the data directories.

**B3f. Predictions.** Segment-log count falls roughly inversely with M (about 675, 42, 5, 4 as in B3c, given one term per row); peak live bytes of builder classes rise with M and stay on the order of M MiB times a small factor (the estimate understates; factor not predicted) plus at most the builders awaiting flush; for M=1 the peak builder memory is about two orders of magnitude below the default run. A flush (memtable) of the same table, for the control, produces no mid-flush segments for any M (limit 1 GiB).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Segment count and peak builder bytes both scale with M as predicted | claim confirmed: option caps builder memory in compaction/index build |
| Segment count scales with M but peak builder bytes do not, or exceed M by a large multiple | the estimate does not track real heap (overshoot in A3b/c); claim refuted for actual usage |
| Segment count independent of M | option is not effective; claim refuted |
| Memtable flush segment count changes with M | A3 step 6 wrong |
| No segments for any M | load too small or the build did not run SASI; not confirmed |
| Peak builder bytes grow with the number of concurrent builds | per-writer multiplication (A3d) confirmed |

**B3h. Controls.** The memtable flush path (hard-coded 1 GiB); the default-option run; the same data and heap for all runs; a run with a non-SASI table for baseline heap; repeat M=1 twice for variance; `-Xmx` kept constant.

**B4. Risks and cleanup.** Unit tier: a temp directory for segment files, a few hundred MB at most; delete it afterwards. Cluster tier: M=1 can write hundreds of small segment files and the data set is several GiB, so keep all directories on the local disk of known size and watch free space; never use shared storage; M=0 or a negative M can create one file per add, so do not run it on the cluster tier. Stop Cassandra and every sampling process (`jstat`, `jcmd` loops, `inotifywait`), verify with `pgrep`, and delete the node's data, commitlog, hints and the copied source tree.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/156.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/SASIIndex.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/SASIIndexBuilder.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java, DatabaseDescriptor.java (grep and short excerpts)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep only)

## D. Stage-4 feedback

`none yet`
