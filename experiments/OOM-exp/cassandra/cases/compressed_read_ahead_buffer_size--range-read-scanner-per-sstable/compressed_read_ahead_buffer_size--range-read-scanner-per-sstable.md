# C9 — compressed_read_ahead_buffer_size: one 256 KiB direct read-ahead buffer per sstable per range-read command  <!-- file: cassandra/cases/compressed_read_ahead_buffer_size--range-read-scanner-per-sstable/compressed_read_ahead_buffer_size--range-read-scanner-per-sstable.md -->

| Field | Value |
|---|---|
| Case ID | `C9` (convergence: multiplicity of a fixed-size per-scanner allocation) |
| From | `OC-303` of the phase 1 OOM candidate list (cluster of one row; primary OC-303) |
| Phase-1 case file | [`max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, repository commit `411b6a8f`); node build `pc99:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1, wave 4, 2026-11-18 (13:38–14:30 ET) |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (fresh session), wave 4, 2026-11-18 13:52–14:50 ET, pc99 |
| Verdict | **true positive** — `verified-OOM` · convergence by multiplicity · `diagnostic` |

**Summary:**
- **Conclusion:** at every shipped capacity default and a 4 GiB heap / 2 GiB direct budget, 40 concurrent
  paged full scans of a table with 2,000 sstables killed Cassandra 5.0.9 with `OutOfMemoryError: Direct
  buffer memory` in 3/3 runs (6–17 s). The budget pc99 resolves by itself (15.5 GiB heap / 7,936 MiB
  direct) also failed 3/3, and so did 4 GiB direct (1/1). One scan at a time survived (0/3, 51 % of the
  limit), and disabling the read-ahead buffer (`0KiB`) at the same load survived (0/3). A 16 GiB direct
  limit survived while touching it. The result is `diagnostic` only because compaction was paused on
  the table to hold the 2,000-sstable count; re-enabling compaction at load start did not prevent it (RC).
- **Root cause:** every range command opens a scanner on each intersecting sstable at once, and each
  scanner allocates a 256 KiB direct read-ahead buffer (`ThreadLocalReadAheadBuffer.getBlock`) that no
  pool or counter charges. Concurrent range commands (≤ `concurrent_reads` 32) × sstable count (uncapped)
  × 256 KiB is bounded only by `MaxDirectMemorySize`, which `cassandra-env.sh` sizes without room for it.

## 1. Candidate

### 1.1 The cluster row (quoted)

The cluster has one row, OC-303 (also the primary). From
[`phase1-oom-candidates.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md):

> | OC-303 | 2026-11-18 | `max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous` | guided | Per-sstable 256 KiB read-ahead buffer for every open scanner, multiplied by an sstable count that nothing caps. [details](runs/wave2.md#oc-303) | CP-7, CP-6, CP-8 | picked: C9 |

Full text from [`runs/wave2.md#oc-303`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-303):

> Per-sstable 256 KiB read-ahead buffer for every open scanner, multiplied by an sstable count that nothing caps. Holder: ThreadLocalReadAheadBuffer.Block.buffer, a plain ByteBuffer.allocateDirect of compressed_read_ahead_buffer_size (default 256 KiB, Config.java:341; LZ4 prefers OFF_HEAP, so it is direct). It is allocated eagerly when a scanner opens (SSTableScanner ctor -> openDataReaderForScan -> CompressedChunkReader.forScan -> allocateResources), and each scanner also takes one 16 KiB chunk from the chunk-cache BufferPool. Why nothing stops it: (1) a partition-range read opens one scanner on every sstable that intersects the range, all at once (PartitionRangeReadCommand.java:331-340). LCS compaction opens all L0 inputs at once, STCS opens up to max_threshold, and a major compaction opens every sstable. (2) The number of sstables has no cap: stage 4 measured 211 L0 sstables (6.5x MAX_COMPACTING_L0) with nothing refused, raising min_threshold lets more sstables pile up, and max_threshold accepts any positive value. (3) The buffer is outside the file_cache_size BufferPool budget, so the only limit is MaxDirectMemorySize, which this memory shares with the chunk-cache pool (512 MiB) and the networking pool (128 MiB). The pinned cassandra-env.sh sets that limit to min(RAM/4, 15.5 GiB), so 8 GiB on a 32 GiB host. Size at defaults: about 272 KiB per intersecting sstable per in-flight range-read page. 211 L0 sstables = 56 MiB per page, and 32 concurrent_reads = 1.8 GiB. A 1 TB LCS table (about 6,400 sstables of 160 MiB) = 1.7 GiB per full-range page, so about 5 concurrent full scans pass an 8 GiB direct limit. If a scanner is opened on one thread and closed on another, the opener's 256 KiB stays referenced in its thread-local map. Also relevant to compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous and max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous (count of simultaneously open scanners).
>
> **Where:** src/java/org/apache/cassandra/io/util/ThreadLocalReadAheadBuffer.java:84; io/util/CompressedChunkReader.java:236-245; io/sstable/format/SSTableScanner.java:78; db/PartitionRangeReadCommand.java:331-340; config/Config.java:341; db/compaction/LeveledManifest.java:306

Triage ([`runs/triage-2026-11-18.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/triage-2026-11-18.md), rank 11 of the top 20):

> | 11 | OC-303 | yes | single ARM node | A partition-range read opens a scanner on every intersecting sstable at once, and each scanner eagerly allocates a 256 KiB compressed read-ahead direct buffer plus a 16 KiB chunk, outside the file_cache_size pool. About 1,000 sstables (an L0 backlog, or STCS falling behind or paused) is about 265 MiB of direct memory per range read, so 4-8 concurrent range reads pass a 1-2 GiB direct limit. | Shares the direct budget with S1 and with the legacy OC-28 (chunk-cache overflow). Duplicates OC-300 and OC-207. OC-304 (thread-local map growth) is the same holder but too slow (about 220 MB a day). |

**What this design covers of the row.** Covered: the range-read path (one scanner per intersecting
sstable, all opened at once), the eager 256 KiB direct read-ahead buffer per scanner plus the 16 KiB
chunk-cache buffer per scanner, the uncapped sstable count, the buffer being outside the
`file_cache_size` pool, `MaxDirectMemorySize` as the only limit, and `concurrent_reads` (32) as the
command multiplicity. Not covered: (a) the compaction paths (LCS opening all L0 inputs, STCS up to
`max_threshold`, a major compaction opening every sstable); compaction is paused in the test so the
sstable count stays fixed, and a major compaction appears only as the fallback intervention I2b;
(b) the cross-thread close retention ("opened on one thread and closed on another"), which is the
OC-304 / OC-471..474 / OC-482..483 holder (per-thread `blockMap`), a different lifetime; (c) a
natural LCS L0 backlog or a 1 TB LCS table as the source of the sstable count: the design builds the
count by flushing with compaction paused (see §2.4, label question); the per-sstable buffer does not
depend on sstable size (`ThreadLocalReadAheadBuffer.java:84` allocates `bufferSize` whatever the file
length), so the count, not the data volume, is the dial. Related open rows outside the cluster (not
changed here): OC-300 (same holder, range reads), OC-207 (one open reader per L0 sstable),
OC-28 (chunk-cache overflow, a second direct domain this design measures as a component).

### 1.2 Phase-1 case and stage 4

The phase-1 constraint is `LeveledManifest.MAX_COMPACTING_L0 = 32` (a literal), checked in
`getSTCSInL0CompactionCandidate()` against the L0 sstable count. Stage 4
([results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md),
2026-10-26, pc12) closed as **true negative — does not cap**: with compaction slower than flush
(1 MiB/s, one compactor) L0 reached 211 sstables (6.5× the constant), 211 with autocompaction off and
209 with `disable_stcs_in_l0`, with no write refused; memory was not measured (the claim was about
count and disk). What it gives this design: the sstable count that a range read multiplies is
bounded by nothing in the compaction code; 32 only selects an STCS-in-L0 candidate.

### 1.3 JIRA prior art (read only; nothing posted)

Local survey [`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv)
(grep: read-ahead, scanner, many sstables, sstable count, L0, 15452) and JIRA REST search on
2026-11-18 (`text ~ "ThreadLocalReadAheadBuffer"` 8 hits, `text ~ "compressed_read_ahead_buffer_size"`
11 hits, `text ~ "read ahead" AND text ~ "direct buffer memory"` 19 hits; relevant ones below):

| Issue | Status | Relation |
|---|---|---|
| CASSANDRA-15452 Improve disk access patterns during compaction and range reads | Fixed 5.0.4 | Introduced the read-ahead buffer. During review a 31 GB-heap node hit `Direct buffer memory` with 15K `ThreadLocalReadAheadBuffer` instances (buffers retained after scans); fixed by deallocating after each scan. Retention fixed; the simultaneous per-command multiplicity remains (this case). |
| CASSANDRA-20551 TLRAB shouldn't allocate on close | Fixed 5.0.5 | close() path allocation; not this mechanism. |
| CASSANDRA-21671 Fix compressed scan read-ahead buffer Block leak and chunk-cache pollution | Fixed 5.0.10 | Removes the per-thread Block cache (`blockMap`); comment: "The buffers are allocated once per input sstable". Fixes the OC-304 retention, not the per-sstable allocation per scan. |
| CASSANDRA-21684 Unbounded per-thread cache of read-ahead buffers can cause slow heap leak | Fixed (superseded by 21671) | OC-304 holder; not this mechanism. |
| CASSANDRA-21522 Allow setCompressedReadAheadBufferSizeInKb(0) to disable RAB | Fixed 5.0.10 | 0 disables the buffer (yaml accepts 0 in 5.0.9: `DatabaseDescriptor.java:960-961`); used as the intervention. |
| CASSANDRA-21529 Direct buffer memory OOM (5.0.6, chunk cache + networking) | Unresolved | Same budget (`MaxDirectMemorySize`), different holder (pool overflow); "read-ahead buffers 15452" named as an unpooled direct user. |
| CASSANDRA-3171, -3535, -4142, -5222, -436 | Fixed / Won't Fix (old versions) | The same shape in older code: one buffer per sstable scanner × uncapped sstable count (1 MB compaction buffers; compressed reader buffers in repair with 5,757 / 12k sstables). 5222 closed Won't Fix: "out-of-control L0 is a terrible plan". |

**Verdict: `new`** for the 5.0.9 mechanism (simultaneous per-command multiplicity of the 256 KiB
direct read-ahead buffer); adjacent retention bugs are known-fixed (15452, 21671/21684) and not
claimed here. The historical family (3171/4142/5222) shows the project treated per-sstable scanner
buffers × sstable count as a real OOM source before; 5222 records a by-design stance on an
out-of-control L0 backlog, which bears on the label question in §2.4.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

A partition-range read (`SELECT ... FROM t` with paging, one page = one `PartitionRangeReadCommand`)
runs on a ReadStage thread (`RangeCommandIterator.java:207`, `Stage.READ.execute(LocalReadRunnable)`;
ReadStage has `concurrent_reads` = 32 permits, `Config.java:179`). `PartitionRangeReadCommand.queryStorage`
(`PartitionRangeReadCommand.java:316-345`) loops over every live sstable of the view and, for each
one that intersects the key range, calls `sstable.partitionIterator(...)`, which constructs a scanner
immediately: `SSTableScanner.<init>` → `sstable.openDataReaderForScan()` (`SSTableScanner.java:78`,
`SSTableReader.java:1383-1386`) → `FileHandle.createReaderForScan` → `CompressedChunkReader.instantiateRebufferer(true)`
(`CompressedChunkReader.java:93-96`), which (1) builds a `BufferManagingRebufferer` that takes one
chunk-length buffer (16 KiB at the default `chunk_length_in_kb`) from `BufferPools.forChunkCache()`
(`BufferManagingRebufferer.java:45`) and (2) calls `Standard.forScan()` → `ScanCompressedReader.allocateResources()`
→ `ThreadLocalReadAheadBuffer.allocateBuffer()` → `getBlock()`, which allocates
`bufferType.allocate(bufferSize)` = `ByteBuffer.allocateDirect(256 KiB)` (`ThreadLocalReadAheadBuffer.java:79-88`;
LZ4's preferred buffer type is OFF_HEAP; `CompressedChunkReader.java:236-245` creates the scan reader whenever
`compressed_read_ahead_buffer_size` (256 KiB, `Config.java:341`) is larger than the chunk length).
The buffer is freed only when the scanner closes (`closeReader` → `releaseUnderlyingResources` →
`clear(true)` → `FileUtils.clean`, `ThreadLocalReadAheadBuffer.java:132-150`), at the end of the
command. All scanners of a command are opened before the merge starts, so one command holds
N × (256 + 16) KiB of direct memory, where N is the number of sstables intersecting the range, and
up to 32 commands run at once. Nothing caps N, the read-ahead buffers are charged to no pool, and
the only limit is the JVM direct-memory limit. With every sstable spanning the token ring (random
partition keys), every page of a full scan intersects all N. **Direction:** convergence by
multiplicity (each buffer is within its fixed 256 KiB local size; per-command count × concurrent
commands exceeds the shared `MaxDirectMemorySize`); technique notes:
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) and the multiplicity
step of [`combo-playbook.md`](../../../combo-playbook.md). **Interpretation:** configuration-sizing /
validation gap (no aggregate accounting of read-ahead buffers against `MaxDirectMemorySize`, which
`cassandra-env.sh` sizes at heap/2 or RAM/4 without room for them); suspected design defect, not an
intentional soft limit.

### 2.2 Protection map

| Domain | Allocation and owner; release | Local contract (C) | Scope and multiplicity | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|---|
| D1 read-ahead buffers (claimed holder) | `ThreadLocalReadAheadBuffer.getBlock:84`, `allocateDirect(256 KiB)`, one per (thread, sstable file) for each open scanner; freed at scanner close (`clear(true)`, `:147`) | 256 KiB per buffer (`compressed_read_ahead_buffer_size`, hard, fixed) | per scanner = per (command × intersecting sstable); N per command (no cap), ≤ 32 commands (ReadStage permits) | none: not in any `BufferPool`; no counter | transient, whole command (open → close) | JVM direct limit |
| D2 scanner chunk buffers (component, OC-28 domain) | `BufferManagingRebufferer:45`, `BufferPools.forChunkCache().get(16 KiB)`; returned at `closeReader` | pool size `file_cache_size` = min(512 MiB, heap/4) = 512 MiB at every planned heap; above it `allocateDirect` overflow, uncapped | per scanner, same multiplicity as D1 | pool counters `BufferPool` chunk-cache `Size`/`UsedSize`/`OverflowSize` (K) | transient, whole command | JVM direct limit |
| D3 command multiplicity (count control) | ReadStage `SEPExecutor` permits | `concurrent_reads` = 32 (count of executing commands) | per node | K = ReadStage `ActiveTasks`; excess commands queue (`PendingTasks`), not allocated | — | — |
| D4 networking pool | `BufferPools.forNetworking()` (native response frames; pages of 1,000 bigint keys ≈ 10 KB) | `networking_cache_size` = min(128 MiB, heap/16) = 128 MiB | per connection | pool counters | per frame | JVM direct limit |
| D5 baseline direct | thread-local compressed holders (`ThreadLocalByteBufferHolder`, one per thread), Netty, other | — | ≤ threads | none | standing | JVM direct limit; measured at idle |
| D6 heap (not claimed) | scanner and iterator objects (≈ 3–6 KB per scanner, estimate) | heap | 32 × N | — | transient | heap; must not be the first failure |

Index files are memory-mapped at the default `disk_access_mode: mmap_index_only` (`Config.java:122`),
so the index reader adds no direct buffer; the chunk cache itself is off at the default
`file_cache_enabled: false`, but D2's pool is still used by the rebufferer.

### 2.3 Configuration and budget audit

- **Capacity constraints (V6), all at shipped defaults, none set in the yaml:**
  `compressed_read_ahead_buffer_size` 256 KiB (`Config.java:341`; not in the shipped yaml);
  `concurrent_reads` 32 (`cassandra.yaml:722`); `file_cache_size` unset → min(512, heap/4) = 512 MiB
  (`DatabaseDescriptor.java:576-577`); `file_cache_enabled` false; `networking_cache_size` unset →
  min(128, heap/16) = 128 MiB (`:573-574`); `disk_access_mode` mmap_index_only; table compression
  default (LZ4, `chunk_length_in_kb` 16); `min_threshold` 4 / `max_threshold` 32 and
  `MAX_COMPACTING_L0` 32 unchanged (stage 4: they do not cap the count); `range_request_timeout`
  10 s, `native_transport_*` defaults. Only arm I2 sets `compressed_read_ahead_buffer_size: 0KiB`
  (the documented disable value) as the intervention.
- **Budgets (V7: heap and direct ≥ 512 MiB; set with `MAX_HEAP_SIZE` / `MAX_DIRECT_MEMORY_SIZE`,
  as `cassandra-env.sh:51-67` would resolve them for a node of the stated RAM; no cgroup memory limit,
  only `MemorySwapMax=0`):**

  | Label | Heap | Direct limit | Node it represents (`cassandra-env.sh` resolution) |
  |---|---|---|---|
  | B2 (ideal; primary V1–V5 condition) | 4096 MiB | 2048 MiB | 8 GiB RAM: heap ½ RAM, direct ¼ RAM |
  | B4 | 8192 MiB | 4096 MiB | 16 GiB RAM |
  | B8 | 15872 MiB | 7936 MiB | ≥ 32 GiB RAM: what pc99 (125 GiB) resolves by itself |
  | B16 (boundary search above the defaults) | 15872 MiB | 16384 MiB | explicit operator `MAX_DIRECT_MEMORY_SIZE` on a large node |

- **Environment (disclosed):** single node pc99 (x86_64, 32 cores, 125 GiB, swap 8 GiB kept at 0
  for the JVM, HDD-backed `/mydata` 714 GiB free, Ubuntu 22.04, kernel 5.15, OpenJDK 11.0.33, G1);
  node pinned to CPUs 0–19 and the client to 20–31 with `taskset` (record that availableProcessors is
  20); `ulimit -n 100000` in the launch shell (2,000 sstables need about 6,000 fds; hard limit
  1,048,576); data, commitlog, logs and dumps under `/mydata/c9/`; yaml changes only the five
  directory paths. JVM option `-Dcassandra.printHeapHistogramOnOutOfMemoryError=true` (acts only
  after an OOM). Heap dump on OOM stays at the shipped default (`-XX:+HeapDumpOnOutOfMemoryError`).
- **Supporting deviation (label question):** the table is created with
  `compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}`: the default strategy,
  with automatic compaction paused (the documented table option, the persisted form of
  `nodetool disableautocompaction`). It holds N = 2,000 sstables fixed for the run; it changes no
  capacity constraint. Stage 2 records the result as `diagnostic` (a disabled subsystem holds the
  precondition) unless the owner rules that a paused-compaction / backlog state is a deployment state.
  The deployment states it stands for: a bulk load with compaction paused, an L0/STCS backlog
  (stage 4: 211 L0 sstables at 6.5×, nothing refused), and a large LCS table at the default 160 MiB
  sstable size, where a full-range read intersects every sstable (2,000 sstables ≈ 320 GB).

### 2.4 Ceiling arithmetic

Per scanner: D1 256 KiB + D2 16 KiB = 272 KiB. Per command at N = 2,000: 544,000 KiB = **531 MiB**.
Baseline direct B0 (D4 + D5 at idle, measured): predicted ≤ 150 MiB.
Peak ≈ B0 + A × 531 MiB, with A = commands executing at once (≤ 32).

| Budget | Direct limit | A at which the limit is passed | A = 32 total | Feasible to exceed? |
|---|---|---|---|---|
| B2 | 2048 MiB | 4 (3 → 1,744 MiB = 85 %) | 17.1 GiB | yes |
| B4 | 4096 MiB | 8 | 17.1 GiB | yes |
| B8 | 7936 MiB | 15 | 17.1 GiB | yes |
| B16 | 16384 MiB | 31 | 17.1 GiB | marginal (needs 31 of 32 commands overlapping at full allocation): predicted boundary |

Control K2 (A ≤ 2): ≤ 150 + 2 × 531 = 1,212 MiB = 59 % of B2 (margin 41 % ≥ 30 %).
Intervention I2 (D1 removed): A = 32 → 32 × 2,000 × 16 KiB = 1,000 MiB (512 MiB in the pool, the rest
overflow) + 150 = 1,150 MiB = 56 % of B2.
Heap (D6, not claimed): 32 × 2,000 × ≈ 6 KB ≈ 0.4 GB transient, under every planned heap.

### 2.5 Workload and environment

**Node and build.** pc99 only (victim and client; one experiment on the node at a time). Before
anything: `ps -eo pid,cmd | grep '[C]assandraDaemon'` must be empty; `free -g`, `df -h /mydata`,
`ulimit -Hn`, `systemd-run --user --scope -p MemorySwapMax=0 true` works (if not, use
`sudo systemd-run --scope --uid=jason92 -p MemorySwapMax=0`; record). Build: run from
`/mydata/s4/cassandra-base` unchanged (never `ant` in it). Per-run instance directories under
`/mydata/c9/runs/<run-id>/`. Reuse the C8 harness shapes where they fit
([`../segment_write_buffer_size--fixed-1GiB-index-build-small-heap/harness/`](../segment_write_buffer_size--fixed-1GiB-index-build-small-heap/harness/):
`c8.py` launcher/yaml/`wait_up`/`stop_node`, `C8Sampler.java` JMX sampler, `hprofhist.py`). Harness for
this case goes in `harness/` here.

**Golden data set G (built once, ≈ 20 min).**
1. Start an instance (B2 budget; directories under `/mydata/c9/golden-build/`).
2. `CREATE KEYSPACE c9 WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
   `CREATE TABLE c9.t (pk bigint PRIMARY KEY, v blob) WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};`
   (all other table options default; save `DESCRIBE TABLE c9.t`).
3. Writer (`harness/c9_build.py`, bundled driver `lib/cassandra-driver-internal-only-3.29.0.zip`,
   protocol 4, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`): 2,000 rounds; each round
   inserts 1,000 rows with `pk` = uniform random signed 64-bit and `v` = 300 random bytes
   (`execute_concurrent_with_args`, concurrency 128), then one flush of `c9.t` through a persistent
   JMX helper (`harness/C9Jmx.java`, `StorageService.forceKeyspaceFlush("c9","t")`; `nodetool flush`
   only as a slow fallback). Each sstable ≈ 330 KB (larger than the 256 KiB buffer), spanning the
   ring. Every 100 rounds log `LiveSSTableCount` (must equal the rounds done).
4. Checks: `nodetool tablestats c9.t` SSTable count 2000; `Data.db` files = 2000; `tools/bin/sstablemetadata`
   on 3 sstables: first/last token within 1 % of the ring ends.
5. `nodetool drain`; stop; `cp -a` data/commitlog/saved_caches/hints to `/mydata/c9/golden/`; record
   `du -sh` and the sorted file list's sha256.

**Per-run procedure (every arm).**
1. Restore: `rm -rf <inst>`; `cp -a /mydata/c9/golden/. <inst>/` (clean start, identical state).
2. Conf: copy `cassandra-base/conf`; yaml additions: `data_file_directories`, `commitlog_directory`,
   `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` (environment); arm I2 adds
   `compressed_read_ahead_buffer_size: 0KiB`. Save `yaml.diff`.
3. Launch: `( setsid nohup env -u HEAP_NEWSIZE CASSANDRA_CONF=<inst>/conf CASSANDRA_LOG_DIR=<inst>/logs
   CASSANDRA_HEAPDUMP_DIR=<inst>/dumps MAX_HEAP_SIZE=<heap>M MAX_DIRECT_MEMORY_SIZE=<direct>M
   JVM_EXTRA_OPTS=-Dcassandra.printHeapHistogramOnOutOfMemoryError=true bash -c 'ulimit -n 100000; exec
   systemd-run --user --scope -p MemorySwapMax=0 --unit c9-<run-id> taskset -c 0-19
   /mydata/s4/cassandra-base/bin/cassandra -f' < /dev/null > <inst>/logs/launch.log 2>&1 & )`. Save the
   JVM command line (`ps -o args`) showing `-Xmx`, `-XX:MaxDirectMemorySize`.
4. Up when `nodetool statusbinary` prints the whole word `running` (≤ 180 s). **Validity gate:**
   `LiveSSTableCount` of `c9.t` = 2000 (no commitlog-replay flush), compaction disabled
   (`nodetool compactionstats` 0 pending for c9.t). Start the samplers; 20 s idle → B0.
5. Load: `harness/c9_scan.py --streams C --fetch 1000 --duration D` on CPUs 20–31: C worker
   processes, each its own `Cluster`/`Session` (protocol 4), each looping full scans
   `SELECT pk FROM c9.t` (fetch size 1000; each page is one range command over (last key, end]) and
   logging per page: wall time, worker, rows, latency, error class. Streams start together.
6. End: the endpoint (JVM gone and an `OutOfMemoryError` in `system.log`) or `D` elapsed → stop the
   client, `nodetool stopdaemon` or kill by PID, stop samplers. Collect excerpts to `logs/<run-id>/`:
   the first `OutOfMemoryError` with its thread and full stack (and the next lines, not only `^ERROR`),
   the heap-histogram lines for `java.nio.DirectByteBuffer`, `ThreadLocalReadAheadBuffer$Block`,
   `BigTableScanner`, the last 15 s and the peak rows of `samples.csv`, the client summary (pages ok,
   errors by class, per worker), `gc.log` tail, `journalctl -k`/`dmesg` grep for oom-kill (expected
   none). Keep the first heap dump per budget (note size), delete later ones; delete `<inst>/data`
   after the run, keep logs.

### 2.6 Instruments

| Quantity | How | Interval |
|---|---|---|
| U (direct, total) | JMX `java.nio:type=BufferPool,name=direct` `MemoryUsed`, `TotalCapacity`, **`Count`** (number of live direct buffers: D1 shows as ≈ +N per executing command, independent of any Cassandra counter) | 200 ms (`C9Jmx poll`) |
| D2 / D4 pool counters (K) | `org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Size/UsedSize/OverflowSize` and `scope=networking` (confirm names by listing the MBeans) | 200 ms |
| D3 multiplicity A (K) | `org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=ReadStage,name=ActiveTasks` and `PendingTasks` | 200 ms |
| sstable count | `type=Table,keyspace=c9,scope=t,name=LiveSSTableCount` | 200 ms |
| heap | `java.lang:type=Memory` `HeapMemoryUsage.used`; G1 `gc.log` (shipped) | 200 ms; log |
| process | `/proc/<pid>/status` `RssAnon` | 1 s |
| work done | client per-page log (pages/s, latency, errors) | per page |
| initiating failure | `system.log`/`debug.log`; histogram printed on OOM; heap dump (`hprofhist.py`) | at failure |

U for D1 is derived as (Count − Count_idle − D2 buffers in overflow) and checked against
(MemoryUsed − MemoryUsed_idle − Δpool) ≈ ΔCount × 256 KiB; I2 gives the same load without D1.
Overhead: the poller makes about 10 JMX reads per 200 ms; no histogram or forced GC during a run.

### 2.7 Arms, predicted response and stopping budget

N = 2,000 in every arm. A = ReadStage `ActiveTasks` (commands executing).

| Arm | Budget | Change | Client C, duration D | Runs | Predicted |
|---|---|---|---|---|---|
| R0 reachability and calibration (not a reading for V1–V4) | B2 | — | before load: one traced page (`TRACING ON; SELECT pk FROM c9.t LIMIT 10`) must show `Executing seq scan across 2000 sstables`; then C steps 1, 2, 3, 4, 6, 8 (45 s each, adding workers) | 1 | per executing command ΔCount ≈ +2,000 (1,800–2,200) and ΔMemoryUsed ≈ 500–560 MiB; plateaus ≈ 0.65 / 1.2 / 1.7 GiB at C = 1 / 2 / 3; direct OOM at C = 4 (or 6 at the latest) |
| **T2 test** | B2 | — | C = 40, D ≤ 300 s | 3 | `OutOfMemoryError: Direct buffer memory` within 60 s of load start, on a ReadStage thread, stack through `ThreadLocalReadAheadBuffer.getBlock` ← `ScanCompressedReader.allocateResources` ← `CompressedChunkReader$Standard.forScan` ← … ← `SSTableScanner.<init>` ← `PartitionRangeReadCommand.queryStorage`; last sample MemoryUsed ≥ 1.8 GiB, Count ≥ idle + 6,000, A ≥ 4; then Cassandra's forced heap OOM, heap dump, `kill -9` |
| **K2 control** | B2 | — | C = 2, D = 180 s | 3 | no OOM; peak MemoryUsed ≤ 1.3 GiB; Count ≤ idle + 4,400; pages complete steadily |
| **I2 intervention** | B2 | `compressed_read_ahead_buffer_size: 0KiB` | C = 40, D = 180 s | 3 | no OOM; A reaches 32; peak MemoryUsed ≤ 1.3 GiB; Count does not grow by ≈ 2,000 per command (D2 buffers come from the pool; overflow buffers counted); pages/s per worker ≥ 50 % of K2's (useful work continues) |
| T4 budget search | B4 | — | C = 40, D ≤ 300 s | 1 | direct OOM; A ≥ 8 |
| T8 budget search | B8 | — | C = 40, D ≤ 300 s | 3 | direct OOM 3/3; A ≥ 15 |
| T16 boundary | B16 | — | C = 40, D ≤ 300 s | 1 (2 if it fails) | survives or marginal OOM; peak ≈ B0 + A × 531 MiB with A ≤ 32 |
| K32 (optional low-N control) | B2 | golden copy with all but the first 32 sstable generations removed offline | C = 40, D = 120 s | 1 | no OOM; peak ≤ 0.6 GiB (32 × 32 × 272 KiB = 272 MiB + B0) |
| RC (optional, compaction on) | B2 | after startup `ALTER TABLE c9.t WITH compaction = {'class':'SizeTieredCompactionStrategy'}`, load starts at once | C = 40, D ≤ 300 s | 1 | record `LiveSSTableCount` vs time and whether OOM precedes the count falling below ≈ 250 (32 × 250 × 272 KiB ≈ 2.1 GiB) |
| I2b (only if I2 does not survive) | B2 | `nodetool compact c9 t` before load (N → 1) | C = 40, D = 180 s | 3 | no OOM |

**Pre-declared amendment rule (from R0, before any K2 reading):** if R0's per-command ΔMemoryUsed
is above 650 MiB, so that K2 at C = 2 would be above 70 % of B2, K2 uses C = 1; record it as a dated
amendment. R0 may also replace the predicted A thresholds in the table with measured ones; it may
not change the arms, budgets, N or C of T/I arms.

**Run validity.** Node started with `LiveSSTableCount` 2000 and the arm's yaml diff and JVM
arguments; all C workers completed at least one page (T arms: before the endpoint) or reported a
server error; for T arms A reached the predicted threshold or the run ended in OOM. A run that fails
validity is invalid (not a reading); at most 2 invalid restarts per arm.

**Outcome reading.**

| Readings | Stage-2 reading |
|---|---|
| T2 3/3 direct OOM with the D1 stack (or another first stack while ΔCount ≈ A × 2,000 at failure), K2 0/3, I2 0/3 | convergence OOM (V1–V5); with V6–V7 met → `verified-OOM` · `diagnostic` (or `deployment` on the owner's ruling, §2.3) → true positive |
| T2 OOMs but ΔCount per command ≪ 2,000 | the claimed holder is wrong; read the stack and histogram; retry with the right holder |
| T2 no OOM, A ≥ 4 reached, ΔCount ≈ A × 2,000 | arithmetic wrong (buffers smaller or shorter-lived); false positive only if T8/T16 arithmetic also cannot reach the limit |
| T2 no OOM, A < 4 | load not reached: retry (client or ReadStage path) |
| I2 OOMs (stack in `BufferPool`) | D2 alone suffices (mixed with OC-28); run I2b for attribution of the multiplicity |
| GC service loss without OOM | record per the protocol default criterion; retry |

**Stopping budget and time plan (wall time must end before 18:07 ET, 2026-11-18).** Each T arm stops
at the endpoint or 300 s of load; survival arms at 180 s (K32 120 s). Per run ≈ 4 min (failing) /
≈ 6 min (surviving) including restore, startup with 2,000 sstables and teardown. With stage 2
starting at S (planned ≈ 14:40 ET):

| From | To | Step |
|---|---|---|
| S | S+0:40 | node checks, harness (`C9Jmx.java`, `c9_build.py`, `c9_scan.py`, launcher from C8) |
| S+0:40 | S+1:00 | golden G |
| S+1:00 | S+1:10 | R0 |
| S+1:10 | S+2:00 | T2, K2, I2 interleaved (T2a K2a I2a T2b K2b I2b T2c K2c I2c) |
| S+2:00 | S+2:20 | T8 × 3 |
| S+2:20 | S+2:30 | T16 |
| S+2:30 | S+2:40 | T4, then K32 / RC if time |
| S+2:40 | S+3:10 | stop everything, excerpts, §3–§4, write-back |

Hard limits: no new run starts after 17:30 ET; all processes stopped by 17:40 ET; case file done by
18:05 ET. If S is later than 14:50, drop K32, RC and T4; later than 15:10, also T16 and run T8 × 2.
The V1–V5 core (T2/K2/I2 × 3) is never cut.

**Resources.** RAM peak per run ≤ 15.5 GiB heap + 16 GiB direct + ≈ 2 GiB other + 40 client
processes × ≈ 60 MB ≈ 36 GiB of 125 GiB. Disk: golden ≈ 1 GB, one run copy at a time ≈ 1 GB, heap
dumps ≤ 4 kept (≤ 16 GB); well under 714 GiB. CPUs: node 20, client 12.

### 2.8 Controls and intervention

- **Matched control (V2):** K2, same build, budget B2, data (golden G, N = 2,000) and client; only the
  number of concurrent scans differs (2 vs 40), so A ≤ 2. Margin 41 % predicted (§2.4).
- **Causal intervention (V4):** I2, identical to T2 except `compressed_read_ahead_buffer_size: 0KiB`,
  which removes D1 (`CompressedChunkReader.java:236-238`: no scan reader when the size is not above the
  chunk length) while the scans, A and N stay. Fallback I2b bounds the multiplicity instead (N → 1).
- **Optional:** K32 (normal sstable count at full concurrency), RC (compaction left on).

`sha256 of §1–§2 at freeze: ed7f8ff30caf3e60fa76ff0afa3e01000083f254d451dec3d203ad5c8c0c2df1` (sha256 of the bytes from the line `## 1. Candidate` up to and
including the newline before this line) · amendments after the freeze: none.

## 3. Runs (stage 2)

Freeze hash checked at stage-2 start (2026-11-18 13:52 ET): `ed7f8ff3…2df1` recomputed over §1–§2, matches.

### 3.0 Amendments (dated, recorded before the readings they affect)

- **A1 (2026-11-18 13:55 ET, environment, before any run).** Instance, golden and run directories are
  under `/mydata/s4/c9-w4/` (the session's task names that directory) instead of the design's `/mydata/c9/`.
  Same disk (`/mydata`, local). No other change.
- **A2 (2026-11-18 14:07 ET, from R0, before any K2 reading; the design's pre-declared amendment rule).**
  R0 measured one executing command at ΔMemoryUsed = 962 MiB over idle (median of 235 samples at A = 1;
  it includes the one-time fill of the chunk-cache pool to its 512 MiB cap, which the design's B0
  prediction did not include) and A = 2 at up to 1,576 MiB over idle (B0 + that = 1,652 MiB = 81 % of B2).
  Both pass the rule's threshold (> 650 MiB per command; K2 at C = 2 above 70 % of B2), so **K2 uses
  C = 1** (harness arm `K1`, run IDs `K1-n`). Arms, budgets, N and the C of T/I arms are unchanged.

No other deviation. All design arms ran (R0, T2 × 3, K2 → K1 × 3, I2 × 3, T4, T8 × 3, T16, K32, RC); I2b
was not needed (I2 survived); T16 ran once (it did not fail). Stage 2 ran 13:52–14:47 ET plus the write-up,
well inside the plan's limits.

### 3.1 Environment (as run)

| Item | Value |
|---|---|
| Node | pc99 (CloudLab `jason92-326665`), x86_64, 32 cores, 125 GiB RAM, swap 8 GiB (kept at 0 for the JVM by `MemorySwapMax=0`), `/mydata` local 753 GB (714 GiB free at start), Ubuntu 22.04, kernel 5.15.0, OpenJDK 11.0.33, G1. No other `CassandraDaemon` before or during the runs (checked before every run by the harness). |
| Build | `/mydata/s4/cassandra-base` unchanged (Cassandra 5.0.9-SNAPSHOT jar, as filed in the header); default ports, JMX 7199 local. |
| Launch | `( setsid nohup env -u HEAP_NEWSIZE CASSANDRA_CONF=… MAX_HEAP_SIZE=<h>M MAX_DIRECT_MEMORY_SIZE=<d>M JVM_EXTRA_OPTS=-Dcassandra.printHeapHistogramOnOutOfMemoryError=true bash -c 'cd <inst>; ulimit -n 100000; exec systemd-run --user --scope -p MemorySwapMax=0 --unit c9-<run> taskset -c 0-19 …/bin/cassandra -f' … & )`. The JVM command line of every run (`runs/<run>/jvmargs.txt`) shows `-Xms/-Xmx<h>M`, `-XX:MaxDirectMemorySize=<d>M` (resolved = requested), `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:OnOutOfMemoryError=kill -9 %p`, the GC log; `availableProcessors` 20 (taskset 0–19); client, sampler on CPUs 20–31. |
| yaml diff | only the five directory keys (`yaml.diff` per run); I2 runs add `compressed_read_ahead_buffer_size: 0KiB`. Every capacity constraint at its shipped default: `compressed_read_ahead_buffer_size` 256 KiB, `concurrent_reads` 32, `file_cache_size` → 512 MiB ("Global buffer pool limit is 512.000MiB for chunk-cache and 128.000MiB for networking", system.log), `file_cache_enabled` false, `disk_access_mode` mmap_index_only, LZ4 16 KiB chunks. |
| Data G | `runs/golden/`: `DESCRIBE TABLE c9.t` = defaults + `compaction = {STCS, 'enabled': 'false'}`; 2,000 rounds × 1,000 rows (random signed 64-bit `pk`, 300 random bytes) + flush in 359 s; tablestats SSTable count 2000; 2,000 `nb-<gen>-big-Data.db` of ≈ 322–325 KB; `sstablemetadata` of generations 1, 19 and 999: first token −9.18e18 … −9.22e18, last token 9.20e18 … 9.22e18 (each spans the ring). `golden/` 705 MB. K32: `golden32/` = G with generations > 32 removed offline (32 Data.db). |
| Validity gate | every run: node up in 9–16 s, `LiveSSTableCount` = 2000 (32 for K32) right after startup, 0 pending compactions. R0 trace: `Executing seq scan across 2000 sstables for (min(-9223372036854775808), min(-9223372036854775808)]`. |
| Instruments | `harness/C9Jmx.java poll` every 200 ms (java.nio direct `Count/MemoryUsed/TotalCapacity`, chunk-cache and networking `BufferPool` Size/UsedSize/OverflowSize, ReadStage Active/Pending/Completed, `LiveSSTableCount`, heap, G1 counts), `/proc/<pid>/status` RssAnon every 1 s, per-page client CSV per worker, system/debug/gc logs, the heap histogram Cassandra prints on OOM, the first heap dump per budget. |
| Harness | [`harness/`](harness/): `c9.py` (launcher, golden, runs, queue), `C9Jmx.java` (sampler, flush helper), `c9_scan.py` (client), `c9_sum.py` (per-run summary), `c9_d1.py` (D1 attribution), `excerpts.sh`. |
| Logs | full logs on `pc99:/mydata/s4/c9-w4/runs/<run>/` (system.log, debug.log, gc.log, samples.csv, rss.csv, client/w*.csv, summary.txt); heap dumps kept: `pc99:/mydata/s4/c9-w4/dumps-kept/B2/R0-…hprof` (0.16 GB), `B4/T4-1-…hprof` (0.17 GB), `B8/T8-1-…hprof` (4.5 GB). Excerpts: [`logs/<run>/`](logs/) (summary with the first OOM stack and histogram rows, meta, last samples, gc tail, kernel grep) and [`logs/d1-attribution.txt`](logs/d1-attribution.txt). |

### 3.2 Runs

B0 (idle, 10 s before load, every B2/B4/B8/B16 run): direct Count 99–113, MemoryUsed 52–76 MiB,
chunk-cache pool 16–32 MiB. "Gone" = JVM exited (load-relative). D1 = ΔMemoryUsed − Δ(chunk-cache pool size)
at the direct peak, independent of any Cassandra counter (none covers D1).

| Run (ET start) | Budget heap / direct | C | Outcome | Peak MemoryUsed / ΔCount | D1 at peak | A (Active / Pending) | Client |
|---|---|---|---|---|---|---|---|
| R0 (14:03) | 4096 / 2048 | ramp 1,2,3,4 (,6,8 not reached) | **direct OOM**, gone at 139.6 s (4th worker started at 135 s) | 2,048 MiB / +6,039 | 1,492 MiB = 5,967 × 256 KiB | 3–4 / 0 | 675 pages, 4 workers |
| T2-1 (14:07) | 4096 / 2048 | 40 | **direct OOM**, gone at 17.3 s | 2,048 / +7,176 | 1,772 MiB = 7,087 × 256 KiB | 32 / 8 | 0 pages; 40/40 server errors (37 ReadTimeout, 3 ReadFailure) |
| K1-1 (14:08) | 4096 / 2048 | 1 | no OOM (180 s) | 1,048 (51 %) / +2,067 | 500 MiB = 2,001 × 256 KiB | 1 / 0 | 469 pages, 0 errors |
| I2-1 (14:12) | 4096 / 2048, RAB 0 | 40 | no OOM (180 s) | 1,039 (51 %) / +31,462 | 2 MiB (pool +985 MiB, overflow 489 MiB) | 32 / 8 | 32,574 pages, 0 errors |
| T2-2 (14:15) | 4096 / 2048 | 40 | **direct OOM**, gone at 8.9 s | 2,048 / +7,222 | 1,788 MiB = 7,151 × 256 KiB | 32 / 8 | 0 pages; 8 ReadFailure, 32 connection closed at JVM exit |
| K1-2 (14:16) | 4096 / 2048 | 1 | no OOM | 1,048 (51 %) / +2,066 | 500 MiB | 1 / 0 | 524 pages, 0 errors |
| I2-2 (14:20) | 4096 / 2048, RAB 0 | 40 | no OOM | 1,039 (51 %) / +31,459 | 2 MiB (overflow 489 MiB) | 32 / 7 | 32,966 pages, 0 errors |
| T2-3 (14:24) | 4096 / 2048 | 40 | **direct OOM**, gone at 6.3 s | 2,048 / +7,225 | 1,788 MiB = 7,151 × 256 KiB | 32 / 8 | 0 pages; 24 ReadFailure, 16 connection closed |
| K1-3 (14:25) | 4096 / 2048 | 1 | no OOM | 1,048 (51 %) / +2,067 | 500 MiB | 1 / 0 | 623 pages, 0 errors |
| I2-3 (14:29) | 4096 / 2048, RAB 0 | 40 | no OOM | 1,039 (51 %) / +31,459 | 2 MiB (overflow 489 MiB) | 32 / 7 | 30,623 pages, 0 errors |
| T8-1 (14:32) | 15872 / 7936 | 40 | **direct OOM**, gone at 25.0 s | 7,936 / +29,656 | 7,388 MiB = 29,551 × 256 KiB | 32 / 8 | 0 pages; 38 ReadTimeout, 2 ReadFailure |
| T8-2 (14:34) | 15872 / 7936 | 40 | **direct OOM**, gone at 16.8 s | 7,936 / +29,654 | 7,388 MiB | 32 / 8 | 0 pages; 4 ReadFailure, rest connection closed |
| T8-3 (14:35) | 15872 / 7936 | 40 | **direct OOM**, gone at 32.6 s | 7,936 / +29,748 | 7,388 MiB | 32 / 48 | 0 pages; 40 ReadTimeout |
| T16-1 (14:36) | 15872 / 16384 | 40 | no OOM (300 s); MemoryUsed at the limit in 36 of 1,584 samples; 120 Full GCs (11.8 s total, ≈ 4 % of wall time; `Bits.reserveMemory` retries succeeded) | 16,384 (100 %) / +90,486 | 15,386 MiB = 61,543 × 256 KiB (pool 962 MiB, overflow 450 MiB) | 32 / 8 | 7,565 pages (median 1.5 s, p99 2.6 s); 32 ReadFailure = `QueryCancelledException` (> 5 s) in the first burst, 2 ReadTimeout |
| T4-1 (14:42) | 8192 / 4096 | 40 | **direct OOM**, gone at 11.5 s | 4,096 / +14,761 | 3,668 MiB = 14,671 × 256 KiB | 32 / 8 | 0 pages; 3 ReadFailure, rest connection closed |
| K32-1 (14:43) | 4096 / 2048, N = 32 | 40 | no OOM (120 s) | 802 (39 %) / +1,173 | 254 MiB = 1,016 × 256 KiB | 32 / 3 | 86,295 pages, 2,596 full scans, 0 errors |
| RC-1 (14:46) | 4096 / 2048, compaction re-enabled before load | 40 | **direct OOM**, gone at 10.5 s; `LiveSSTableCount` 2000 throughout (no c9.t compaction started) | 2,048 / +7,134 | — | 32 / 8 | 0 pages |

**Initiating failure (every OOM run, 10 of 10).** The first error is
`ERROR [ReadStage-NN] JVMStabilityInspector.java:70 - Exception in thread …` /
`java.lang.OutOfMemoryError: Direct buffer memory` at `Bits.reserveMemory` ← `ByteBuffer.allocateDirect` ←
`BufferType$2.allocate` ← **`ThreadLocalReadAheadBuffer.getBlock(:84)`** ← `allocateBuffer(:76)` ←
`CompressedChunkReader$ScanCompressedReader.allocateResources(:204)` ← `CompressedChunkReader$Standard.forScan(:244)` ←
`instantiateRebufferer` ← `FileHandle.createReaderForScan` ← `SSTableReader.openDataReaderForScan(:1385)` ←
`SSTableScanner.<init>(:78)` ← `BigTableScanner.<init>` ← `BigTableReader.partitionIterator` ←
**`PartitionRangeReadCommand.queryStorage(:340)`** ← `ReadCommand.executeLocally` ← `StorageProxy$LocalReadRunnable`
(threads ReadStage-63/44/68 in T2, 46/67/53 in T8, 42 in T4, 69 in RC, 4 in R0). Then Cassandra logs
`Force heap space OutOfMemoryError in the presence of` the direct OOM, the JVM's
`java.lang.OutOfMemoryError: Java heap space`, the heap dump, and `-XX:OnOutOfMemoryError="kill -9 %p"`.
The kernel log has no oom-kill (`logs/<run>/kernel-oom-grep.txt` empty). Heap histogram printed on the
first OOM (excerpts in `logs/<run>/summary.txt`): T2-1/2/3 `BigTableScanner` 7,109 / 7,179 / 7,158 live,
`java.nio.DirectByteBuffer` 16,515 / 16,449 / 16,407 (allocated buffers plus slices); T8-1/2/3
`BigTableScanner` 29,991 / 29,554 / 30,094; T4-1 14,698. The scanner counts match ΔCount (7,176–7,225;
29,654–29,748; 14,761) and D1 / 256 KiB, so the direct memory at failure is the scanners' read-ahead buffers.

**Readings against the predictions (§2.7).**
- R0: per executing command ΔCount 2,005 (median at A = 1; predicted 1,800–2,200) and +482 MiB of D1
  over the pool (predicted 500–560 MiB with D2); but the chunk-cache pool filled to its 512 MiB cap on the
  first command and stayed there, so B0 + pool ≈ 0.55 GiB is a standing base (the design's B0 ≤ 150 MiB
  missed it). Plateaus 0.96 / 1.35 (max 1.58) / 1.75 (max 1.97) GiB at A = 1 / 2 / 3; direct OOM when the
  fourth worker started (C = 4), as predicted. → amendment A2.
- T2: predicted OOM within 60 s with MemoryUsed ≥ 1.8 GiB, Count ≥ idle + 6,000, A ≥ 4: observed at
  6–17 s, 2,048 MiB, +7,176 to +7,225, A = 32 (+8 pending). One difference: all 32 commands open scanners
  at once, so at failure each command holds ≈ 220 of its 2,000 buffers (ΔCount/A), not a full 531 MiB.
  The outcome row "ΔCount per command ≪ 2,000 → holder is wrong" does not apply: the summed ΔCount and
  D1 (7,087–7,151 × 256 KiB) are the read-ahead buffers of 7,109–7,179 live scanners, and the stack is the
  D1 stack. The limit is reached by the sum over concurrent commands, which is the claimed multiplicity.
- K2 (as K1, A2): no OOM 3/3, peak 1,048 MiB = 51 % of B2 (margin 49 %), A = 1, 469–623 pages.
- I2: no OOM 3/3 at A = 32 (+7–8 pending) on the same data; D1 ≈ 0 (2 MiB); direct peak 1,039 MiB = the
  chunk-cache pool at 512 MiB plus 489 MiB pool overflow (`OverflowSize`, the OC-28 / D2 domain; the
  design predicted ≈ 1,000 MiB of D2 at A = 32, 56 % of B2). Useful work continued: 4.3–4.6 pages/s per
  worker (30,623–32,966 pages / 40 workers / 180 s) vs 2.6–3.5 pages/s in K1, ≥ 50 % of K2's as required.
- Budget search: T4 OOM 1/1 (4,096 MiB direct), T8 OOM 3/3 (7,936 MiB direct, 15.5 GiB heap: what pc99
  resolves by itself), T16 survived 0/1 at 16,384 MiB direct while touching the limit (the predicted
  boundary: 32 × 2,000 × 272 KiB ≈ 16.6 GiB with the pool, but commands finish and free buffers while
  others open, and `Bits.reserveMemory` waits on GC-driven frees before throwing).
- K32 (normal sstable count, A = 32): no OOM, 802 MiB = B0 + 512 MiB pool + 254 MiB D1 (predicted 272 MiB
  D1 + B0; the design missed the pool fill).
- RC: with compaction enabled at load start, the OOM came at 10.5 s with `LiveSSTableCount` still 2,000 (32
  × 2,000 × 256 KiB far above 2 GiB long before STCS could merge 2,000 sstables 32 at a time).

**Run validity.** All runs passed the gate. For T runs, "every worker completed a page or reported a server
error": every worker's first request was sent at load start (`client/w*.csv`), and ReadStage held
Active 32 + Pending 8 = 40 commands in 5–17 samples per run, so all 40 commands were on the server. Each
ended with a server error (ReadTimeout 1200 / ReadFailure 1300) or with its connection closed when the
JVM was killed (`NoHostAvailable … ConnectionShutdown`). That is the server failing the request, and the
runs count as valid. A was ≥ 4 (32) in every T run.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Status (detail): **`verified-OOM` · convergence by multiplicity · `diagnostic`**
(`deployment` if the owner rules that a paused-compaction / sstable-backlog state is a deployment state, §2.3).

| | Evidence |
|---|---|
| V1 Repetition | T2: direct OOM 3/3 from clean golden copies (also T8 3/3, T4 1/1, RC 1/1, R0) |
| V2 Matched control | K2 at C = 1 (A2): 0/3, peak 1,048 MiB = 51 % of B2, same build, budget, data and client |
| V3 Measurement | U(D1) from the JVM's own direct-buffer pool (`Count`, `MemoryUsed`), minus the chunk-cache pool size: 1,772–1,788 MiB = 7,087–7,151 × 256 KiB at T2's peak, 7,388 MiB at T8; no Cassandra counter covers D1 (K = none). D2 measured with the pool metrics. Heap histogram at failure: 7,109–7,179 live `BigTableScanner` (T2) |
| V4 Intervention | I2 (`compressed_read_ahead_buffer_size: 0KiB`, the documented disable value): 0/3 at A = 32 and the same load, D1 ≈ 0, 4.3–4.6 pages/s per worker |
| V5 Initiating failure | first error `OutOfMemoryError: Direct buffer memory` on a ReadStage thread through `ThreadLocalReadAheadBuffer.getBlock` ← … ← `PartitionRangeReadCommand.queryStorage`, in all 10 OOM runs; histogram printed on OOM; heap dumps kept (B2, B4, B8) |
| V6 Default constraints | every capacity at its shipped default (`compressed_read_ahead_buffer_size` 256 KiB, `concurrent_reads` 32, `file_cache_size` 512 MiB resolved, `networking_cache_size` 128 MiB, chunk 16 KiB); yaml diff = directories only |
| V7 Acceptable budget | B2 = 4 GiB heap / 2 GiB direct (≥ 512 MiB standing rule; 2 GiB the ideal); also B8 = 15.5 GiB / 7,936 MiB, which `cassandra-env.sh` resolves for pc99 itself, 3/3. **Largest direct budget reaching the endpoint: 7,936 MiB (3/3); 16 GiB survived (0/1, at the limit)** |

**Reason.** A paged full-table read (`SELECT pk FROM t`, 1,000 rows per page) runs one
`PartitionRangeReadCommand` per page. That command opens a scanner on every sstable that intersects the
range, all at once, and each scanner eagerly allocates a 256 KiB direct read-ahead buffer
(`ThreadLocalReadAheadBuffer.getBlock`). The buffer belongs to no `BufferPool` and no Cassandra counter, so
`MaxDirectMemorySize` is its only limit. With 2,000 sstables spanning the ring and every capacity at its
default, one command took +2,005 direct buffers (≈ 500 MiB). Forty concurrent scan clients (ReadStage 32
executing) drove direct memory to its limit and killed the node with `OutOfMemoryError: Direct buffer
memory` through that frame: 3/3 at 4 GiB heap / 2 GiB direct (6–17 s, 7,087–7,151 × 256 KiB of D1), 3/3 at
the 15.5 GiB / 7,936 MiB that pc99 resolves by itself, and 1/1 at 4 GiB direct. One scan at a time survived
(1,048 MiB, 51 % of the limit, 0/3). Disabling the buffer (`0KiB`) at the same 32-way load survived 0/3 at
1,039 MiB with work continuing. A 16 GiB direct limit survived while touching it, which is the boundary of
32 × 2,000 × 256 KiB. **Root cause:** the per-scanner read-ahead buffer is fixed in size, but its count is
(range commands in flight, up to `concurrent_reads` = 32) × (intersecting sstables, uncapped), and no
aggregate control or reservation sees it. CP-7 (per-owner allocation × unbounded owners) plus CP-6 (the
JVM's direct-memory error is the only enforcement).

**Limits of attribution and conditions.** (1) The sstable count was held at 2,000 by the table option
`compaction = {'enabled': 'false'}` (a supporting deviation, hence `diagnostic`). RC shows that
re-enabling compaction does not prevent the OOM when the backlog exists at load time. The natural
backlog sources (stage 4: 211 L0 sstables with nothing refused; a large LCS table) were not reproduced.
At 211 sstables the arithmetic is 32 × 211 × 256 KiB ≈ 1.65 GiB of D1, plus up to 512 MiB of pool and
≈ 50 MiB of B0: about 2.2 GiB, right at a 2 GiB limit. That count was not tested. (2) At 32 sstables (K32, A = 32)
D1 was 254 MiB: the failure needs a large intersecting-sstable count. (3) A second direct domain
appeared that the design did not price. The chunk-cache `BufferPool` fills to its 512 MiB cap on the first
range read and keeps it, and with D1 disabled its overflow reached 489 MiB at A = 32 (OC-28's domain). It
added ≈ 0.2–0.5 GiB to the T peaks but is not needed for the OOM (I2: 1,039 MiB, no OOM). (4) Single
node, RF 1, the client on the same host (CPU-pinned apart). (5) Cross-thread retention (OC-304) and
compaction-path multiplicity were not tested. **Classification by measurement:** each buffer is within its
fixed 256 KiB local size (U ≤ C per buffer). The aggregate has no control besides the implicit
`concurrent_reads` × N, so it is convergence by multiplicity of an unprotected aggregate. Interpretation:
configuration-sizing / validation gap (`cassandra-env.sh` sizes the direct limit without room for
N × 256 KiB per range command).

**Retry:** not applicable.
