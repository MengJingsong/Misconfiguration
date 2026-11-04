# SASI MAX_TERM_SIZE (per-term size limit) — verification solution  <!-- file: cases/sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:167` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude (Sonnet 5.5), Claude Code CLI, 2026-10-25 |
| Estimate | `negative`: the limit bounds the size of one term (< 1024 bytes), not the total memory or disk of an index builder or index file; those totals are governed by the segment-flush threshold and grow with the number of distinct terms. |
| Ground | `MAX_TERM_SIZE` is a compile-time per-item filter. Total builder memory is the sum over distinct terms and postings, and is capped only by a separate, later check (`estimatedMemoryUse() < maxMemorySize`, PerSSTableIndexWriter.java:247). Total on-disk size is unbounded (more segments). Memtable-side SASI memory (TrieMemIndex) has no cap from this constant at all. |

## A. Constraint trace

**A1. The constraint.** `OnDiskIndexBuilder.MAX_TERM_SIZE`, kind: constant (`public static final int`), first declared at `OnDiskIndexBuilder.java:128` (`= 1024`). Unit: bytes (`ByteBuffer.remaining()` of one analyzed term). Default 1024, hard-coded, no derivation. Not settable by yaml, `-D` or JMX; changing it needs a source edit and rebuild. (Related but different: SASI use is gated by `sasi_indexes_enabled`, `Config.java:606`, default false, `conf/cassandra.yaml:1992`; it must be `true` to create the index.) The value is also referenced at `PerSSTableIndexWriter.java:218` and `memory/TrieMemIndex.java:84`.

**A2. What it caps.** Heap (on-heap `OnDiskIndexBuilder.terms` map, declared at `OnDiskIndexBuilder.java:143`, HashMap created at line 159) and, indirectly, disk (term bytes in the `.db` SASI component). The compared quantity is `term.remaining()` of a single term, `>= 1024` means rejected (strictly, terms of 1024 bytes or more; max accepted is 1023). It does not compare any cumulative quantity.

**A3. Mechanism.**
1. Flush/compaction write path: `PerSSTableIndexWriter.java:136` calls `Index.add(value, key, pos)`; `Index.add` (line 205) runs the analyzer over the value and for each token checks `token.remaining() >= OnDiskIndexBuilder.MAX_TERM_SIZE` at `PerSSTableIndexWriter.java:218`; if so logs at info (220) and `continue`s (226), so the token is skipped.
2. Accepted tokens go to `currentBuilder.add` (line 243), `OnDiskIndexBuilder.add` at `OnDiskIndexBuilder.java:165`. The check at line 167 is a second, defensive copy of the same test: on hit it logs `logger.error` (169) and returns without adding (172). Note the message prints `Short.MAX_VALUE` as the "maximum size" (line 171) although the real limit is 1024: a cosmetic inconsistency.
3. If the term passes, memory estimate grows: new term adds `64 + 48 + term.remaining()` (`OnDiskIndexBuilder.java:182`, comment 180-181); every (term,key) adds `60 + 40 + 8` (line 194, comment 191-193). So one term's contribution is at most 1023 + 112 bytes, and each posting 108 bytes, regardless of the limit.
4. After the loop, `PerSSTableIndexWriter.java:247` compares `estimatedMemoryUse()` (`OnDiskIndexBuilder.java:199-202`) with `maxMemorySize` and flushes a segment (250). `maxMemorySize` (`PerSSTableIndexWriter.java:365-369`) is 1073741824 for `OperationType.FLUSH`, else `IndexMode.maxCompactionFlushMemoryInBytes`, default `(long)(1073741824*0.15)` = 161061273 (`conf/IndexMode.java:59-60`), settable by index option `max_compaction_flush_memory_in_mb` (`IndexMode.java:58, 186-188`; values over 100 GiB revert, 190-193).
5. Memtable path: `memory/TrieMemIndex.java:84` applies the same filter (skip, info log at 86-90) before `size += index.add(...)` (line 94); no memory cap from this constant.
Bypass/overshoot: the flush check runs only after a whole value is analyzed, so one value can overshoot `maxMemorySize` by all its tokens; the estimate is jol-derived and approximate (comment at 180), so real heap differs. Number of distinct terms and postings per term is unbounded by this constant.

**A4. Other consumers.** Memtable heap/off-heap (MemtableAllocator, separate limits `memtable_heap_space`/`memtable_offheap_space`); SASI `IndexMemtable`/`TrieMemIndex` structures; analyzer (e.g. tokenizing) transient buffers; `OnDiskIndexBuilder` finish-time structures (levels, `MutableLevel` buffers sized by `BLOCK_SIZE`=4096, declared at line 127); segment files on disk; the OS page cache; the multi-segment merge in `Index.complete` (PerSSTableIndexWriter.java:281).

**A5. Evidence beyond the source.** none (no external docs relied on).

## B. Verification solution

**B1. Claim under test.** Usage (builder heap estimate, real heap, index file size) does NOT follow `MAX_TERM_SIZE`: the constant only rejects individual terms of >= 1024 bytes, and total usage scales with distinct term count and is capped only by `maxMemorySize`. Specifically: (i) terms of 1023 bytes are accepted and 1024 rejected (boundary), (ii) with terms all under the limit, `estimatedMemoryUse()` grows without any dependence on the 1024 limit until `maxMemorySize` is reached, (iii) rejected terms add 0 to the estimate and 0 to the file.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy tree to local disk: `rsync -a ~/cassandra-5.0.9/ /local/tmp/c509/` ; `cd /local/tmp/c509 && ant jar`. [Amended 2026-10-25, B5.5: the copy is made by `copy-source.sh` to `~/s4-od`, not rsync to /local/tmp; `ant testsome` forks a 1024 MB JVM, so `-Xmx512m` is not applied.] Put a JUnit test (new file, in the copy only) at `test/unit/org/apache/cassandra/index/sasi/disk/MaxTermSizeProbeTest.java`, modelled on the existing `OnDiskIndexTest`. Run `ant testsome -Dtest.name=MaxTermSizeProbeTest`. JVM opts: `-Xmx512m`, `-Dcassandra.config=file:///local/tmp/c509/test/conf/cassandra.yaml`; `DatabaseDescriptor.daemonInitialization()` in the test.

**B2b. Knobs.** The constant cannot be varied at runtime, so the varied quantity is the term size: 1, 512, 1023, 1024, 1025, 4096 bytes. Second knob (positive control): `maxMemorySize` via a `PerSSTableIndexWriter` for `OperationType.COMPACTION` with index option `max_compaction_flush_memory_in_mb` = 1, 4, 16.

**B2c. Workload.** Direct calls: `new OnDiskIndexBuilder(UTF8Type.instance, UTF8Type.instance, OnDiskIndexBuilder.Mode.CONTAINS /*or PREFIX*/)` then `add(term, key, pos)` N=100,000 times with distinct terms of the size under test (random bytes encoded as ascii so UTF8 valid), **mode PREFIX only [amended 2026-10-25, B5.1]**, one key each with distinct partition keys/tokens. Arithmetic: per accepted distinct term the estimate rises by 64+48+size+108 = 220+size; at size 1023 that is 1243 bytes, so 100,000 terms give 124.3 MB and reach a 1 MiB..16 MiB compaction cap after about 843..13,500 terms.

**B2d. Observables and instruments.** `builder.estimatedMemoryUse()` after each add; `builder.isEmpty()`; the finished file size from `builder.finish(File)`; test-side count of accepted terms (return of `isEmpty` / OnDiskIndex term iteration); log capture (logback appender) to count "Rejecting value" lines; for the writer test, `Index.segments.size()` (`@VisibleForTesting` field, PerSSTableIndexWriter.java:189-190). Heap measured via `Runtime` after `System.gc()`, indicative only. Not directly observable: exact heap of the HashMap/TreeMaps (use the estimate and a heap histogram `jcmd <pid> GC.class_histogram`).

**B2e. Procedure.**
1. Build per B2a.
2. For each term size S in {1,512,1023,1024,1025,4096}: fresh builder; add 100,000 distinct terms; record `estimatedMemoryUse()` at 10k steps, accepted count, log count, and after `finish` the file length.
3. Compaction-writer run: for cap C in {1,4,16} MB with S=512, feed terms until 10x C worth of estimate would have been produced; record segments count and max estimate seen.
4. Repeat step 2 with S=1023 vs 1024 to isolate the boundary.
5. Delete `/local/tmp/c509` temp output when done.

**B2f. Predictions (before any run).**
- S=1023: all accepted; estimate ~ 100,000*(220+1023) = ~124.3e6 (exact: 112+1023+108 = 1243 per term).
- S=1024 and 4096: 0 accepted, estimate 0, file not created (finish returns false for empty), 100,000 error logs; **[amended 2026-10-25, B5.2: `finish` returns false but creates a zero-length file (`OnDiskIndexBuilder.java:247-251`), it does not leave no file]**; i.e. a step at 1024, not a proportional relation.
- S=1,512: estimate = 100,000*(220+S) (= 22.1e6, 73.2e6), linear in S and N, nothing 1024-related. **[Amended 2026-10-25, B5.6: for S=1 only 62 distinct alphanumeric terms exist, so the estimate is 62*(112+1) + 100,000*108 = 10,807,006, not 22.1e6; the S=512 value 73.2e6 stands.]**
- Writer test: segments ~ ceil(total estimate / C); each segment's estimate at flush lies in [C, C + one value's tokens]; shows that `maxMemorySize` is what binds.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| Estimate step from ~1.2e3 per term at 1023 to exactly 0 at 1024; linear in N elsewhere | Claim confirmed: limit is a per-term filter only. |
| Estimate for S=1023 is capped near or below some function of 1024 independent of N | Claim refuted: something bounds total (not expected). |
| Estimate grows past 1024*k for any k with S<1024 (e.g. 124 MB at N=100k) | Claim confirmed (usage does not follow the constant). |
| Writer: segments count rises as C falls, estimate per segment ~C | Positive control works: a real cap binds; contrast confirms. |
| Writer: segments count insensitive to C, or estimate never reaches C | Control did not move: not confirmed; check workload size. |
| S=1024 accepted | Claim wrong (off-by-one in analysis of line 167). |

**B2h. Controls.** (a) Positive control: the compaction `maxMemorySize` cap (above), same terms, usage moves with C. (b) Same N with S=1 shows the estimate formula without size effect. (c) Fixed seeds, distinct terms, to avoid dedup in the `terms` map (equal terms add only 108 bytes). (d) Run with and without the analyzer path (call `OnDiskIndexBuilder.add` directly vs through `PerSSTableIndexWriter.Index.add`) to separate the two copies of the check (PerSSTableIndexWriter.java:218 vs OnDiskIndexBuilder.java:167).

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from local copy (`ant jar` in `/local/tmp/c509`). Data, commitlog, hints dirs on local disk of known free size (>= 20 GB): `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` set to `/local/tmp/node1/...`. cassandra.yaml: `sasi_indexes_enabled: true`, `num_tokens: 1`, `listen_address`/`rpc_address` localhost. JVM: `-Xms1G -Xmx1G` **[amended 2026-10-25, B5.4: -Xms2G -Xmx2G]** (in `conf/jvm11-server.options`, in the local copy), `-XX:+HeapDumpOnOutOfMemoryError` to `/local/tmp`.

**B3b. Knobs.** Value size of the indexed column: 1000, 1023, 1024, 2000 bytes (client side). Index option `max_compaction_flush_memory_in_mb` (positive control) = 1 vs 64 on compaction. Memtable flush forced with `nodetool flush`.

**B3c. Workload.** Table `ks.t (id uuid primary key, v text)`; `CREATE CUSTOM INDEX ON ks.t (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'PREFIX' /* amended 2026-10-25, B5.1: CONTAINS not run */, 'max_compaction_flush_memory_in_mb':'N'}`. Insert 200,000 rows per run with `cassandra-stress` user profile or a python driver loop, each row a distinct v of the chosen size (random alphanumerics, each distinct). Arithmetic: at 1023 bytes, 200,000 rows give about 205 MB of term bytes plus postings ~ 250 MB estimate; at 1024 and above every term is rejected (log "Rejecting value"), so the index file is empty. Duration: ~10-20 min per run.

**B3d. Observables and instruments.** `nodetool flush ks t`; SASI component files `*SI_*.db` size via `ls -l`/`du` in the data dir; `jcmd <pid> GC.heap_info` and `GC.class_histogram` sampled every 5 s during flush/compaction; JMX heap (`jstat -gc <pid> 5s`); log greps for "Rejecting value", "Flushed index segment"; `nodetool compact ks t` for the compaction path. Not observable: the builder's own estimate (use class histogram of `OnDiskIndexBuilder`, `DynamicTokenTreeBuilder`).

**B3e. Procedure.**
1. Build, configure, start node (`bin/cassandra -f` in background with PID file).
2. Create schema (above). For each size in B3b and each cap: truncate, insert workload, `nodetool flush`, record index file sizes and the peak heap during flush; then `nodetool compact` and record again.
3. Grep logs for rejection counts.
4. Stop node (`kill $(cat pid)`), check with `pgrep -f CassandraDaemon`; remove `/local/tmp/node1`.

**B3f. Predictions.**
- Sizes 1000 and 1023: SASI file size ~ proportional to size*rows (~ rows*(size+~100)); heap peak during flush rises with row count, up to ~the 1 GiB flush cap (flush) ; far above 1024*k.
- Size 1024 and 2000: rejection log count = 200,000, SASI term data ~ 0 (file has header only, or the component is absent/empty), while the base table SSTable still grows (the value is stored in the table; the limit does not limit the table).
- **[B5.3, 2026-10-25: the control is judged on segment count ("Flushed index segment" lines); peak heap is indicative only.]** Control: compaction with cap 1 MB yields >= ~ (total estimate/1 MB) segments and lower peak heap than cap 64 MB; the 1023-byte case segmented flushes appear in log as "Flushed index segment".

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| Index size/heap scale with rows at 1023, drop to ~0 at 1024 | Confirms per-term filter only; usage does not follow it as a total cap. |
| Index size and heap bounded by something independent of rows at size < 1024 | Claim refuted (a cap related to the limit exists). |
| Peak heap for compaction lower with cap 1 MB than 64 MB, same data | Positive control works. |
| Cap 1 vs 64 gives same peak heap and same segment count | Control did not move or limit never reached: not confirmed; raise rows. |
| 1024-byte values accepted into index | Claim wrong at the code-trace level. |

**B3h. Controls.** Same workload with the cap control; base table size unchanged by index acceptance (shows table data is not governed by it); repeat runs 3x for GC noise; identical schema with `sasi_indexes_enabled` enabled in all runs; take heap numbers at the same phase (flush vs steady state).

**B4. Risks and cleanup.** Disk: node data up to a few GB on local `/local/tmp/node1` only; verify `df` before. Heap: 1 GiB node may OOM at large counts, which is a reading in itself (dump goes to local /tmp, delete it). Never build in the shared tree. After runs: kill node, `pgrep -f 'CassandraDaemon|ant'` shows none, `rm -rf /local/tmp/node1 /local/tmp/c509`. Unit-tier JUnit leaves temp files under `build/test` in the local copy only.

### B5. Step-0 audit amendments (stage 4, 2026-10-25; reasons independent of any reading)

All line cites in A1-A4 and B2d were re-read against `cassandra-5.0.9` and hold (OnDiskIndexBuilder 128, 143, 159, 165-173, 182, 194, 199-202; PerSSTableIndexWriter 136, 189-190, 205, 218-226, 243, 247, 250, 281, 365-369; TrieMemIndex 84-94; IndexMode 58-60, 186-193; Config 606; DatabaseDescriptor 4240; yaml 1992). The arithmetic (220+size per term, 1243 at 1023, 124.3e6 at N=100,000, 22.1e6 and 73.2e6 at sizes 1 and 512, `(long)(1073741824*0.15)` = 161061273) holds.
1. **Mode PREFIX only.** `finish` splits a text term into suffixes in CONTAINS mode (`OnDiskIndexBuilder.java:254-255`, `SuffixSA.java`: `long[charCount]`, one sorted entry per character). At S=1023, N=100,000 that is 102.3e6 suffix entries (0.82 GB of longs, over the 1 GiB test JVM with the terms) and a file of about S^2/2 = 0.52 MB per term (about 52 GB), so the CONTAINS file size and finish-time heap are not the "size + ~100" the B3f prediction assumes. `estimatedMemoryUse()` and the rejection check do not depend on the mode, so the claim, prediction rows and conclusions rows are unchanged. B2c and B3c use `PREFIX` (also the default, `IndexMode.java:135-137`). CONTAINS is not run (recorded as a deviation).
2. **Empty builder.** `finish(File)` on an empty builder returns false and creates a zero-length file (`OnDiskIndexBuilder.java:247-251`); B2f's "file not created" reads "file length 0". The B3f "header only, or absent/empty" is read as a zero-length index component.
3. **Logs and the control observable.** At the cluster tier the writer's own filter fires first and logs at INFO `Rejecting value (size ...` (`PerSSTableIndexWriter.java:220`), and the memtable path logs INFO `Can't add term` (`TrieMemIndex.java:86`); the ERROR `Rejecting value (value size ...` at `OnDiskIndexBuilder.java:169` is reached only by direct `add` calls (unit tier, B2h(d)). Counts are taken per string. A flush uses `maxMemorySize` 1 GiB (`:368`), which 200,000 rows (about 249 MB of estimate at 1243 B per row, so at least 863,831 rows would be needed) never reach: the "up to ~the 1 GiB flush cap" clause in B3f is not reachable at this workload and is not part of any conclusions row. The cap control (B3g row 3 and 4) is judged on the count of `Flushed index segment` lines from a `nodetool compact` (MAJOR_COMPACTION is not FLUSH, so `:368` takes the index option); peak heap is reported but indicative.
4. **Cluster heap 2 GiB.** The memtable holds each indexed value twice (cell and trie string) while the builder holds about 1.2 KB per row at flush; at 200,000 rows that is near 1 GiB live, so a 1 GiB heap would die by OOM before the quantity of interest is read. Heap is set to 2 GiB; the claim does not depend on it.
6. **S=1 cannot have 100,000 distinct terms.** A duplicate term adds only the 108-byte posting (`OnDiskIndexBuilder.java:175-194`), so D distinct terms and N postings give D*(112+S) + N*108. S=1 (62 alphanumeric terms) gives 10,807,006; all other sizes use 100,000 distinct terms (an 8-character counter prefix, then padding). B2h(b) already reads S=1 as a check of the formula, so the claim and conclusions rows are unchanged.
5. **Environment.** Working tree `~/s4-od` (copy-source.sh), data/commitlog/hints/saved caches under `~/s4-od-data`, ports JMX 7326, Byteman 9326 (not used), native 9348, storage 7026, loopback 127.0.26.1; unit JVM is 1024 MB (Ant `maxmemory`).

## C. Sources read

- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java
- src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java
- src/java/org/apache/cassandra/index/sasi/memory/TrieMemIndex.java
- src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java
- src/java/org/apache/cassandra/config/Config.java (line 606), DatabaseDescriptor.java (4240)
- conf/cassandra.yaml (1990-1992)

## D. Stage-4 feedback

**2026-10-25, stage 4 ([results](../../stage4-runtime-verification/results/sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous.md)).** Unit tier: Confirmed, does not cap (estimate 124.3e6 at S=1023, exactly 0 at S=1024/1025/4096; writer segments 159/39/9 at caps 1/4/16 MB). Cluster tier: Confirmed, does not cap (index 683 MB at 1023 bytes, 0 bytes at 1024 and 2000 with 200,000 rejections each; control 237 vs 4 segments at 1 vs 64 MB). Outcome class: true negative. Amendments before run 1 are in B5 (PREFIX mode only, zero-length file at S>=1024, S=1 value, control read on segment count, 2 GiB heap). Notes for stage 3: the index file is a step function of 4 KiB block packing (2,392 B per row at 1000 bytes, 3,417 B at 1023), not "size + ~100"; the cap that binds a flush is 1 GiB of estimate and was not reachable in 200,000 rows; `OnDiskIndexBuilder.java:171` prints `Short.MAX_VALUE` as the maximum size.
