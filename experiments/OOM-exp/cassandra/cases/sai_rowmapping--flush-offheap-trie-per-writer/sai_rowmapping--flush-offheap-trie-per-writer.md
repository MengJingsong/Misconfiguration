# U13 (OC-383) — SAI RowMapping: off-heap flush trie per flush writer  <!-- file: cassandra/cases/sai_rowmapping--flush-offheap-trie-per-writer/sai_rowmapping--flush-offheap-trie-per-writer.md -->

| Field | Value |
|---|---|
| Case ID | `U13` (U = unprotected accumulation: memory that no capacity control covers; README "ID prefixes") |
| From | `OC-383` of the phase 1 OOM candidate list (Cassandra); duplicates `OC-326`, `OC-328`, `OC-329`, `OC-341` |
| Phase-1 case file | [`capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source`, `build.xml:36` `base.version 5.0.9`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 subagent (Claude Code), 2026-11-21 |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (a fresh Claude Code session), 2026-11-21 08:13–09:55 EST on ms0617 (aarch64); all runs ended 09:52 EST |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected accumulation); the direct limit of every failing condition is explicit and below what `cassandra-env.sh` resolves (§4, for the owner to weigh) |

**Summary** (stage 2 conclusion)

- **Conclusion:** at shipped defaults, a write-heavy SAI table with long clustering keys ends in `OutOfMemoryError: Direct buffer memory` in a memtable flush thread. 8 GiB heap / 1 GiB direct: OOM **3/3** (81–89 s of load); matched control (same bytes in a non-key column) 0/3; intervention (same writes, no SAI index) 0/3 at 3× the throughput. Also 4 GiB / 512 MiB 3/3 and 15,872 MiB / 2 GiB 1/1 (largest failing direct limit found); 4 GiB / 768 MiB, 2 GiB / 512 MiB and the env.sh pairings (4 GiB / 2 GiB, 8 GiB / 4 GiB, 15,872 / 7,936 MiB) survive. The dump at failure attributes 768 of 813 MiB of live direct memory to two `RowMapping` tries.
- **Root cause:** every SAI memtable flush builds an off-heap `InMemoryTrie` (`RowMapping`) with one full primary key per flushed row. No control charges it (not the memtable pool, not the SAI segment limiter, no direct-memory budget); its whole-buffer doubling makes one flush hold 2^⌈log2(used)⌉ bytes, and its buffers are freed only by the GC. Its size follows the heap-derived flush size (≈ heap/12 of memtable, r ≈ 0.57 for 1,000-character keys), and two flush writers run at once because the flush is slower than the load, so the live total is ≈ 2 × capacity + 44 MiB. That stays under the direct limit `cassandra-env.sh` pairs with the heap (≥ heap/2) but exceeds an explicit `MaxDirectMemorySize` below ≈ heap/4.
- **Budget caveat (owner):** every failing condition sets `MaxDirectMemorySize` explicitly (≥ 512 MiB, so V7 holds by the standing rule) at 1/8 to 1/4 of what `cassandra-env.sh` would resolve for that heap (§4 table).

## 1. Candidate

**The row (phase-1 candidate list, `phase1-oom-candidates.md:392`), quoted:**

> | OC-383 | 2026-11-18 | `trie_2gb_hard_limit-allocateblock-leadbit--autonomous` | autonomous | The SAI RowMapping off-heap trie built at every memtable flush of an SAI table is charged to nothing, and its direct buffers are never cleaned explicitly. [details](runs/wave2.md#oc-383) | — | picked: U13 (2026-11-21) |

Full text (`runs/wave2.md`, OC-383):

> The SAI RowMapping off-heap trie built at every memtable flush of an SAI table is charged to nothing, and its direct buffers are never cleaned explicitly. Holder: RowMapping.rowMapping, an InMemoryTrie<Long>(OFF_HEAP) with one PrimaryKey -> row-id entry for each row written by the flush, plus boxed Long content on heap. Why nothing stops it: no limit or soft guard is applied. Unlike TrieMemtable (discardBuffers at TrieMemtable.java:173), the direct buffers are not freed; they go only when GC collects the DirectByteBuffers. Memory is also counted as allocatedPos while capacity doubles. Rough size at defaults: about 40-60 B off-heap (up to 2x with doubling slack) plus about 20 B heap per flushed row. A 4.5M-row flush (about 680 MB memtable at 8 GiB heap) is about 250-450 MB direct per flushing SSTable, times memtable_flush_writers (2). This counts against MaxDirectMemorySize = RAM/4 (cassandra-env.sh), which is shared with other direct buffers.
>
> **Where:** src/java/org/apache/cassandra/index/sai/disk/RowMapping.java:75,85-90,155-159; src/java/org/apache/cassandra/index/sai/disk/StorageAttachedIndexWriter.java:86,208,280; src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:186-196; conf/cassandra-env.sh:59,66

Triage (`runs/triage-2026-11-18.md`, rank 19):

> | 19 | OC-383 | yes | single ARM node | Every memtable flush of a table with an SAI index builds an off-heap InMemoryTrie RowMapping (about 40-100 B direct plus about 20 B heap per flushed row, doubling buffers). It is charged to nothing and its direct buffers are freed only by GC. A flush of a few million small rows holds hundreds of MiB of direct memory per flush writer (2 by default), against a direct limit of about 1 GiB at a 2 GiB heap shared with the chunk-cache and networking pools. | Shares the direct budget with S1. Next to C8 (SAI segment limiter), which does not cover flush. Duplicates OC-326, OC-328, OC-329 and OC-341. |

**Duplicates named by the triage** (full text in `runs/wave2.md`), and what this design covers:

> **OC-326** (`block_size-add-blockindex--autonomous`): Memtable-flush RowMapping is not charged to anything. For every OperationType.FLUSH, StorageAttachedIndexWriter builds an InMemoryTrie<Long> with one entry per flushed row: off-heap node buffers that grow by doubling up to the ~2 GB trie limit, plus a boxed Long and a content-array slot per row on heap. It lives until the index flush completes, alongside the memtable that is still held. It is not charged to the memtable pool, the SAI segment limiter or any other budget. Rough size is about 40-80 B per row (up to 2x from buffer doubling): a flush of 3-10M small rows (a 0.7-2.5 GiB memtable) holds about 0.2-0.8 GB of extra native/heap memory, times memtable_flush_writers concurrent flushes.

> **OC-328** (`max_array_length-checkmaxleafnodecount-numleaves--autonomous`): Memory used while flushing a memtable SAI segment is not charged to anything. The memtable-flush path (MemtableIndexWriter -> NumericIndexWriter/BlockBalancedTreeWriter) writes the whole memtable index as one segment and is not under the segment-build limiter. Alongside it, StorageAttachedIndexWriter fills a RowMapping InMemoryTrie<Long> with one entry per flushed row: off-heap buffers that double up to about 2 GB, plus a boxed Long per row on heap. That memory is charged to neither the memtable pool nor the segment limiter, and it is held until the flush finishes, while the memtable is still live. Rough size is about 40-80 B per row: about 0.2-0.8 GB for a 3-10M-row flush (stage 4 saw an 8e6-row single flush at 2.5 GiB of memtable), per concurrent flush writer. The checkMaxLeafNodeCount guard itself is unreachable (it needs about 9e10 points per segment).

> **OC-329** (`max_points_in_leaf_node-add-leafvaluecount--autonomous`): Same uncharged flush-time structures on the numeric SAI memtable-flush path. The RowMapping trie (one off-heap trie entry plus one boxed Long per flushed row, doubling buffers up to about 2 GB) is held for the whole flush and charged to neither the memtable pool nor the SAI segment limiter. NumericIndexWriter.LeafCallback also keeps a PackedLongValues per leaf (140-224 B per leaf plus the packed row ids) for the whole segment, and on the flush path that segment is the entire memtable. Rough size is about 40-80 B per row for RowMapping, plus a few bytes per row for leafPostings: about 0.2-0.8 GB per flush of 3-10M rows, per concurrent flush writer.

> **OC-341** (`max_array_length-checkmaxleafnodecount-numleaves--autonomous`, guided): Holder: the SAI RowMapping built on every memtable flush of a table with SAI indexes. It is an InMemoryTrie(BufferType.OFF_HEAP) mapping each flushed row's PrimaryKey to an sstable row id, with a boxed Long per row as on-heap content. It is held until the memtable index segments are written. Why nothing stops it: this memory is charged to neither the memtable pool (it is created after the memtable is switched out) nor the SAI segment limiter, which covers only non-flush builds. The only bound is the trie's 2 GiB hard limit, which fails the flush with SpaceExhaustedException. Rough size: about 50-100 B of direct memory plus about 20 B of heap per flushed row. A flushed memtable of a few million small rows gives hundreds of MiB. Concurrent flushes (memtable_flush_writers, default 2, across tables) multiply it, and it shares MaxDirectMemorySize with the chunk cache and network buffers.

| Row | Covered by U13? |
|---|---|
| OC-383 | yes: the holder (RowMapping off-heap trie) and its multiplicity (flush writers) |
| OC-326 | yes: the same holder; its "native/heap" size is measured as direct (buffers) and estimated as heap (boxed Longs) |
| OC-328 | RowMapping part yes. The memtable-segment writer memory (`MemtableIndexWriter` → `NumericIndexWriter`/`BlockBalancedTreeWriter`, heap) is present in the run (the indexed column is numeric) but not claimed or measured separately |
| OC-329 | RowMapping part yes. `NumericIndexWriter.LeafCallback` leaf postings (heap, a few B per row) present but not claimed |
| OC-341 | yes, fully (same holder, multiplicity, direct budget) |

**Phase-1 case file:** [`trie_2gb_hard_limit-allocateblock-leadbit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md). Constraint: the hard 2 GB limit of one `InMemoryTrie` (`InMemoryTrie.java:148`, `if (leadBit + BUF_START_SHIFT == 31)` → `SpaceExhaustedException`). Estimate `positive` per trie, with the caveat that it bounds one trie only, not the node total.

**Phase-1 stage-4 result:** [`results/trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md), 2026-10-27, pc41: true positive (caps). Unit tier: one trie stops at `allocatedPos` = 2^31 − 256 for every soft threshold and buffer type. Cluster tier (TrieMemtable, 16 GiB heap / 10 GiB direct): the soft guard switched the memtable before the hard limit, but the node's `direct` pool reached 3.29 GB because two tries coexisted during a flush (the old one is held while flushing). The SAI tries were named as untested ("the SAI tries, which have no soft guard, are not tested"). Relevance here: it measured that direct buffer memory follows the trie's whole-buffer doubling (`direct` increase = whole buffers), which is the step this design predicts. It did not measure RowMapping.

**JIRA prior art** (read only; nothing posted):
- `jira-oom-survey.csv`: `grep -i "RowMapping|InMemoryTrie|StorageAttached|SAI.*flush"`: no row about RowMapping or SAI flush-time direct memory. Nearest: CASSANDRA-20752 (SAI segment builder held across switched sstable writers in sharded compaction, fixed 5.0.6, heap, compaction path; already in 5.0.9 and the C8 family), CASSANDRA-11383 / 11159 / 12662 (SASI, a different index).
- JIRA REST (reachable, 2026-11-21): `text ~ "RowMapping"` → CASSANDRA-18216 (sharding of the SAI in-memory index, 6.0-alpha3; mentions `RowMapping#merge()` only for test coverage), CASSANDRA-19367, CASSANDRA-19018: none about memory. `component = "Feature/SAI" AND text ~ "flush" AND text ~ "direct memory"` → CASSANDRA-20567, CASSANDRA-18216: neither about RowMapping memory. `text ~ "InMemoryTrie" AND text ~ "OFF_HEAP"` → CASSANDRA-17240, 18673, 19661, 21894: none. `component = "Feature/SAI" AND (OutOfMemory OR OOM)` → CASSANDRA-20752, 18673.
- **Verdict: `new`** (no report of the RowMapping's flush-time direct memory; not documented as by design).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

Direction: **unprotected accumulation** (no control applies to the holder; the only bound is the implicit one, rows per flush × bytes per row, and the multiplicity is `memtable_flush_writers`). Technique note: [`combo-playbook.md`](../../../combo-playbook.md) step 1 (multiplicity) only; no stacking is needed for the main condition.

A memtable flush creates one `StorageAttachedIndexWriter` per flushed SSTable through the SAI group's flush observer (`StorageAttachedIndexGroup.java:204-209`). Its constructor builds `RowMapping.create(lifecycleNewTracker.opType())` (`StorageAttachedIndexWriter.java:86`), which for `OperationType.FLUSH` returns a new `RowMapping` (`RowMapping.java:85-90`) holding `new InMemoryTrie<>(BufferType.OFF_HEAP)` (`RowMapping.java:75`). Each flushed row adds its full `PrimaryKey` byte-comparable form (token, partition key, clustering: `PrimaryKey.java:395-401`) with `putSingleton` (`StorageAttachedIndexWriter.java:275-280` → `RowMapping.java:155-158`). The trie allocates 32-byte blocks (`InMemoryReadTrie.java:127`); a chain block holds 28 key bytes (`CHAIN_MAX_OFFSET = BLOCK_SIZE − 5`, `InMemoryReadTrie.java:147`), so a distinct key suffix of K bytes costs ≈ 32·⌈K/28⌉ B plus ≈ 32–64 B of content and branch nodes. Buffers are allocated whole, buffer *i* is 256·2^i bytes (`BUF_START_SHIFT = 8`, `InMemoryReadTrie.java:207`; `allocateBlock`, `InMemoryTrie.java:140-159`) by `ByteBuffer.allocateDirect` (`BufferType.java:33-35`), so after `allocatedPos` crosses 2^n the trie holds 2^(n+1) − 256 bytes of direct capacity: the reservation jumps by 2^n at once. Heap content: one boxed `Long` per row in `AtomicReferenceArray` chunks (`InMemoryTrie.java:162-177`), ≈ 20 B per row. The mapping lives until `complete()` has written every per-column index (`StorageAttachedIndexWriter.java:187-213`); nothing calls `discardBuffers()` on it (the only caller is `TrieMemtable.java:173`), so the buffers are released when GC clears the `DirectByteBuffer`s (or when `java.nio.Bits.reserveMemory` calls `System.gc()` on a failed reservation: `-XX:+DisableExplicitGC` is not in `conf/`). Nothing charges the trie: not the memtable pool (the memtable is already switched out), not the SAI segment limiter (C8; non-flush builds only), not any direct-memory budget. Rows per flush are bounded only by the memtable flush trigger: `memtable_heap_space` = heap/4 (`DatabaseDescriptor.java:586-587`), `memtable_cleanup_threshold` = 1/(1 + `memtable_flush_writers`) = 1/3 (`DatabaseDescriptor.java:753-763`), and the cleaner flushes the largest memtable when the non-reclaiming use exceeds `reclaiming + limit × threshold` (`MemtablePool.java:136-147`). So a flushed memtable is ≈ heap/12, and with long clustering keys the RowMapping costs about as many bytes as the memtable it flushes. Up to `memtable_flush_writers` = 2 flushes run at once (`ColumnFamilyStore.java:207`, `MemtableFlushWriter`). A failed reservation throws `OutOfMemoryError: Direct buffer memory` in the flush thread; `JVMStabilityInspector.inspectThrowable` logs it and forces a heap OOM (`JVMStabilityInspector.java:105-131`, `:193-201`), so stage 2 must keep the first (initiating) error.

### 2.2 Protection map

| Domain (allocation) | Holder, scope, multiplicity | Counter (K) | Limit / contract (C) | At the limit | Lifetime |
|---|---|---|---|---|---|
| RowMapping trie buffers, direct (`RowMapping.java:75`, `InMemoryTrie.java:151`) | one per flushing SSTable writer (`StorageAttachedIndexWriter.java:86`); ≤ `memtable_flush_writers` = 2 at once (one data directory, STCS: one flush runnable per memtable, `Flushing.java:57-70`) | **none** | **none** as memory; only the per-trie hard limit 2^31 − 256 B (`InMemoryTrie.java:148`) | `SpaceExhaustedException` fails the flush (never reached here: predicted ≤ 1.6 GiB) | first row → end of `complete()`; freed by GC / `System.gc()` from `Bits` |
| RowMapping content, heap (`InMemoryTrie.java:162-177`) | same | none | none | — | same |
| Memtable, heap (`memtable_allocation_type: heap_buffers`, `SkipListMemtable`; `cassandra.yaml:783-825`) | per table; switched at ≈ limit/3 | memtable pool on-heap `used` | `memtable_heap_space` = heap/4, hard (writes block); cleaner at 1/3 (`MemtablePool.java:136-147`) | flush of the largest memtable; writes wait | until its flush completes |
| SAI memtable index, heap (`TrieMemoryIndex.java:81`, `TrieMemtable.BUFFER_TYPE` = on-heap under `heap_buffers`) | per memtable × index | charged partly to the memtable (OC-8) | as memtable | as memtable | as memtable |
| BufferPool `chunk-cache` (reader buffers), direct (`BufferPools.java:39`) | per node | pool `used` | `file_cache_size` = min(512 MiB, heap/4) (`DatabaseDescriptor.java:576-577`); chunk cache **off** by default (`file_cache_enabled` false, `Config.java:499`, `ChunkCache.java:53-54`) | allocate on demand outside the pool | transient reader buffers; pool chunks retained |
| BufferPool `networking`, direct (`BufferPools.java:44-45`) | per node | pool `used` | `networking_cache_size` = min(128 MiB, heap/16) (`DatabaseDescriptor.java:573-574`) | allocate on demand | retained chunks |
| JVM direct budget | process | `java.nio` `Bits` reserved | `MaxDirectMemorySize` (budget) | `OutOfMemoryError: Direct buffer memory` after one `System.gc()` and retries | — |

Scope: U (RowMapping direct capacity) is compared with **no** contract; the classification is unprotected accumulation. The memtable pool is the implicit bound (rows per flush); it is not a contract on this memory (the trie is outside its counter).

### 2.3 Configuration and budget audit

- **Build:** `/mydata/s4/cassandra-base` on ms0617 (Cassandra 5.0.9 from `systems/cassandra/source`, JDK 11.0.33, aarch64). Checked read-only 2026-11-21 08:30 EST: host `node4…utah.cloudlab.us`, 8 cores, 62 GiB RAM (54 free), `/mydata` 36 GiB free, no `CassandraDaemon` running, `bin/` and `tools/bin/cassandra-stress` present. Run data under `/mydata/s4/U13/<run>/`; never touch `/mydata/s2r2` or `/mydata/u1r2`.
- **Constraints, all at shipped defaults (V6):** `memtable_heap_space` and `memtable_offheap_space` unset (heap/4), `memtable_cleanup_threshold` unset (1/3), `memtable_flush_writers` unset (2 for one data directory), `memtable_allocation_type: heap_buffers`, memtable `SkipListMemtable`, `file_cache_enabled` unset (false), `file_cache_size` unset (min(512, heap/4)), `networking_cache_size` unset (min(128, heap/16)), default compaction (STCS), table compression default (LZ4), JVM options from `conf/jvm11-server.options` (G1, `MaxTenuringThreshold=2`, `G1NewSizePercent=50`, `MaxGCPauseMillis=300`) and `conf/jvm-server.options` (`HeapDumpOnOutOfMemoryError`, `AlwaysPreTouch`).
- **Environment deviations (disclosed):** paths (`data_file_directories`, `commitlog_directory`, `saved_caches_directory`, `hints_directory`, `cdc_raw_directory` → `/mydata/s4/U13/<run>/`), `-XX:HeapDumpPath`, GC log path, `-XX:NativeMemoryTracking=summary` (instrument), JMX local port. Nothing else in `cassandra.yaml` changes.
- **Budget (set through `cassandra-env.sh`'s own variables):** `MAX_HEAP_SIZE` and `MAX_DIRECT_MEMORY_SIZE` per arm (§2.8). No container/cgroup limit (the victim runs with the node's 62 GiB; the endpoint is the JVM direct limit).
- **Resolved values per heap H** (recorded again from `nodetool`/vmflags in stage 2):

| H | memtable_heap_space | flush trigger (≈ H/12) | file_cache_size | networking_cache_size | env.sh direct for the node with that heap (RAM = 2H) |
|---|---|---|---|---|---|
| 2 GiB | 512 MiB | ≈ 171 MiB | 512 MiB (cache off) | 128 MiB | 1 GiB |
| 4 GiB | 1024 MiB | ≈ 341 MiB | 512 MiB (cache off) | 128 MiB | 2 GiB |
| 8 GiB | 2048 MiB | ≈ 683 MiB | 512 MiB (cache off) | 128 MiB | 4 GiB |
| 15872 MiB | 3968 MiB | ≈ 1323 MiB | 512 MiB (cache off) | 128 MiB | 7936 MiB |

- **V7 argument.** Every OOM arm uses heap ≥ 2 GiB and an explicit `MaxDirectMemorySize` ≥ 512 MiB, which meets V7 by the standing rule (2026-11-11) without a per-case review. The node claimed for the main condition is an 8 GiB node running a 4 GiB heap with the direct limit set to 512 MiB (`MAX_DIRECT_MEMORY_SIZE=512M`, the variable `cassandra-env.sh:120` documents). This is **below** env.sh's own resolution for that node (2 GiB). The arithmetic (§2.4) says the endpoint is out of reach at env.sh's pairing (direct = heap/2); arm C0 measures this. The owner may want to weigh this when reading the verdict; it is not a container budget.

### 2.4 Ceiling arithmetic and predicted response

Workload rows: partition key `bigint`, clustering `ck text` of 1,000 random characters (distinct), one `int` column `v` with an SAI index; ≈ 1,000 rows per partition.

- **Memtable charge per row** ≈ 1,000 B (cloned clustering) + ≈ 150–250 B (row, cell, B-tree, SAI memtable index share) ≈ 1.2 KB (± 15 %).
- **RowMapping per row:** suffix ≈ 1,003 B (clustering plus terminators; the token and partition key prefix are shared within a partition) → 36 chain blocks = 1,152 B, plus ≈ 32–64 B content/branch ≈ 1.2 KB. Ratio r = RowMapping bytes / memtable bytes ≈ 1.0 (0.85–1.2).
- **Per flush** at H: rows ≈ (H/12)/1.2 KB; `allocatedPos` ≈ r·H/12; direct capacity = next power of two above `allocatedPos` (minus 256 B), reached when `allocatedPos` crosses the previous power of two (at ≈ 75 % of the flush's rows for r·H/12 ≈ 1.33 × 2^n).

| H | rows/flush | allocatedPos (range) | RowMapping capacity per flush | heap content |
|---|---|---|---|---|
| 2 GiB | ≈ 149 k | ≈ 171 MiB (145–205) | 256 MiB (jump 128 → 256 at ≈ 75 %) | ≈ 3 MiB |
| 4 GiB | ≈ 298 k | ≈ 341 MiB (290–410) | **512 MiB** (jump 256 → 512 at ≈ 75 %) | ≈ 6 MiB |
| 8 GiB | ≈ 597 k | ≈ 683 MiB (580–820) | **1 GiB** (jump 512 → 1024) | ≈ 12 MiB |
| 15872 MiB | ≈ 1.16 M | ≈ 1.3 GiB (1.1–1.6) | **2 GiB − 256 B** (jump 1 → 2 GiB; under the 2 GiB hard limit) | ≈ 23 MiB |

- **Other direct (B0):** pool chunks for reader buffers, networking pool, flush writer and compression buffers, startup buffers. Not filled by this workload (chunk cache off, one node, client protocol v4 through Netty's own allocator). Predicted 10–60 MiB; measured in C0. Contract sum of the bounded direct pools at full use: 512 + 128 = 640 MiB, not expected to fill.
- **Peak live direct** ≈ B0 + capacity(flush 1) + capacity(flush 2 if it overlaps). Dead RowMappings of finished flushes do not count: a failed reservation calls `System.gc()` (full G1 GC) and retries first.
- **Prediction per condition:**
  - **M (4 GiB / 512 MiB):** the first flush, at ≈ 75 % of its rows, asks for a 256 MiB buffer while it holds 256 MiB − 256 B and B0 > 256 B → `OutOfMemoryError: Direct buffer memory`, stack `Bits.reserveMemory` ← `ByteBuffer.allocateDirect` ← `BufferType$2.allocate` ← `InMemoryTrie.allocateBlock` ← … ← `RowMapping.add` ← `StorageAttachedIndexWriter.addRow`, thread `MemtableFlushWriter:*`. Expected **3/3**, ≈ 30–90 s after load start (≈ 341 MiB written plus 75 % of the flush). One System.gc() (full GC) in the GC log just before.
  - **C0 (4 GiB / 2 GiB, env.sh pairing; calibration and survival reading):** no OOM; `direct` shows a +256 MiB step during each flush, from ≈ B0 + 256 MiB to ≈ B0 + 512 MiB per flush (two flushes ≤ ≈ 1 GiB + B0 < 2 GiB).
  - **CTL (matched payload, 4 GiB / 512 MiB):** same memtable bytes, RowMapping ≈ 50–70 B/row → ≈ 15–20 MiB per flush (capacity 32 MiB) → no OOM in ≥ 4 flushes. Expected 0/3.
  - **INT (no SAI index, 4 GiB / 512 MiB):** no RowMapping → no OOM in ≥ 4 flushes; flush throughput equal or higher. Expected 0/3.
  - **8 GiB / 1 GiB:** same single-flush jump (512 → 1024 MiB + B0 > 1 GiB). Expected 3/3, first flush.
  - **4 GiB / 768 MiB:** needs flush 2's mapping ≥ 128 MiB (capacity 256 MiB) while flush 1 holds 512 MiB. Timing-dependent: predict 0–3/3; report n/N.
  - **2 GiB / 512 MiB (ideal heap):** single flush ≤ 256 MiB; needs both writers past 128 MiB used at once. Predict 0–1/3 (boundary).
  - **15872 MiB / 2 GiB (largest-budget step, optional):** single-flush jump 1 → 2 GiB. Predict OOM 1/1 if `allocatedPos` > 1 GiB (range 1.1–1.6 GiB). Below 1 GiB used, no OOM: the boundary.
- **General law to check:** OOM at the first big flush iff 2^⌈log2(r·H/12)⌉ + B0 > D (one writer), or about twice that with overlapping writers. Since 2·2^⌈log2(r·H/12)⌉ ≤ r·H/3 < H/2 for r < 1.5, env.sh's pairing (D = H/2) is predicted safe at defaults with this key shape.

### 2.5 Workload and environment

- **Node:** ms0617 alone (victim and client; the client is light next to the flush and is recorded with `top`). One measured experiment at a time. Clean start per run: new data, commitlog, hints, saved-caches directories under `/mydata/s4/U13/<run>/`; fresh JVM.
- **Schema (test arm, M/C0/budget arms):**
  ```
  CREATE KEYSPACE u13 WITH replication = {'class':'SimpleStrategy','replication_factor':1};
  CREATE TABLE u13.t (pk bigint, ck text, v int, PRIMARY KEY (pk, ck));
  CREATE INDEX t_v ON u13.t (v) USING 'sai';
  ```
  CTL: `CREATE TABLE u13.t (pk bigint, ck bigint, pad text, v int, PRIMARY KEY (pk, ck))` with the same SAI index on `v` and `pad` = 1,000 random characters (same bytes per row, short key). INT: the M table without the index.
- **Load:** inserts only, every row new (no overwrites): `pk` sequential blocks of 1,000 rows, `ck` 1,000 random alphanumeric characters (`pad` likewise in CTL), `v` uniform 1..1,000,000. Tool: `cassandra-stress user` from the build (profile in `harness/u13.yaml`, `cluster: fixed(1000)`, `size: fixed(1000)` for `ck`/`pad`, unlogged single-partition batches of ≈ 10 rows, `-rate threads=64`), or, if the profile cannot give distinct 1,000-character keys and sequential partitions, a small Java driver using the build's bundled driver jar (`harness/Load.java`), same row shape. Target ≥ 15 MiB/s of rows; stage 2 records the rate. No reads, no repair, no other tables written (system tables only).
- **Multiplicity:** whatever the default flush machinery gives (2 writers); it is measured (flush start/end times per `MemtableFlushWriter` thread), not forced.

### 2.6 Instruments (U independent of K; there is no K for the holder)

1. **`direct` pool** (`java.nio:type=BufferPool,name=direct`: `MemoryUsed`, `TotalCapacity`, `Count`) via a JMX sampler at **5 Hz** to `samples.csv`, with heap used and memtable pool on-heap use (`org.apache.cassandra.metrics:type=MemtablePool,name=*`) in the same row. U = the step increments during a flush; their sizes must be whole trie buffers (128 MiB, 256 MiB, 512 MiB…).
2. **NMT** (`-XX:NativeMemoryTracking=summary`): `jcmd <pid> VM.native_memory summary` every 5 s; category "Other" (direct buffers) as the second, independent reading.
3. **Flush log:** `system.log` `Writing Memtable-t@… (… serialized bytes, N ops, x%/y% of on/off-heap limit)` and `Completed flushing …` (`Flushing.java:153`, `:179`); `debug.log` SAI lines "Completed partition iteration for index flush" / "Completed per-index writes" (`StorageAttachedIndexWriter.java:193-215`) with thread names. Gives rows per flush, the flush window and writer overlap.
4. **GC log** (`-Xlog:gc*` to the run folder): `System.gc()` full GCs before an OOM; old-gen use.
5. **At failure:** the first `OutOfMemoryError` with thread and stack from `system.log`/stdout (preserve it if the forced heap OOM follows); the `.hprof` written by `HeapDumpOnOutOfMemoryError`; from the dump, a list of `java.nio.DirectByteBuffer` instances ≥ 1 MiB with `capacity` and, if time allows, the referrer chain to `InMemoryTrie` → `RowMapping` (a small HPROF scan in `harness/`; drop item 9).
6. **Workload completion:** rows written, rate, client errors; `nodetool tablestats u13.t` after a surviving run.
7. **Instrument checks before the first measured run (C0):** the sampler reads `direct` within 1 % of NMT "Other"; the step sizes match whole buffers; the rate is recorded.

### 2.7 Stopping budget

- Per run: stop at the endpoint (OOM; the JVM exits or is killed after the dump), or after **6 completed flushes** of ≥ 0.9 × the predicted flush size, or **12 min** of load, whichever first. A surviving test arm must have completed ≥ 4 flushes of ≥ 0.9 × predicted size to count as a valid survive.
- No escalation past the planned arms. No run starts after **13:15 EST**; every process stopped and the case file written by **14:00 EST**.
- Disk: ≤ 3 GiB of data per run, deleted after the logs are copied; dumps (≤ heap size each) kept only for the first OOM of each condition, the rest deleted after the stack is recorded. Keep `/mydata` free space ≥ 15 GiB.

### 2.8 Arms, controls and intervention (V1–V4), and budget search

| # | Arm | Heap / direct | Table | Runs | Role |
|---|---|---|---|---|---|
| 1 | C0 calibration | 4 GiB / 2 GiB (env.sh pairing) | M | 1 | instruments, B0, r, rows/flush, step sizes; survival at env.sh pairing |
| 2 | **M** test | **4 GiB / 512 MiB** | M | **3** | V1, V5, V6, V7 |
| 3 | **CTL** matched payload | 4 GiB / 512 MiB | CTL (key bytes moved to `pad`) | **3** | V2 (nearest surviving control: same memtable bytes per flush, same index, small mapping) |
| 4 | **INT** intervention | 4 GiB / 512 MiB | M without the SAI index | **3** | V4 (remove the holder; record rows/s and flush count) |
| 5 | budget step | 8 GiB / 1 GiB | M | 3 | larger budget, same single-flush jump |
| 6 | direct ladder | 4 GiB / 768 MiB | M | 3 | two-writer overlap; boundary between 512 MiB and 1 GiB at 4 GiB heap |
| 7 | ideal heap | 2 GiB / 512 MiB | M | 3 | 2 GiB-heap boundary |
| 8 | largest budget | 15872 MiB / 2 GiB | M | 1 | largest failing budget (optional) |
| 9 | dump attribution | — | — | — | HPROF scan of the first M dump (analysis only) |

Budget search order: 512 MiB → 1 GiB (with 8 GiB heap) → 2 GiB (15872 MiB heap), stepping the direct limit geometrically with the heap that makes the single-flush jump reach it; 768 MiB at 4 GiB refines the two-writer boundary. The verdict condition is M; the largest failing (heap, direct) with n/N is reported.

**Diagnostic intervention not planned:** a patched build that allocates the RowMapping on heap or discards its buffers would only move or shorten the memory; the no-index arm removes the holder with the same writes, which is the cleaner attribution.

### 2.9 Time plan (2026-11-21, EST)

| Time | Step |
|---|---|
| 09:00–09:25 | freeze check, harness (`conf/` copy, `env` overrides, sampler, profile or `Load.java`, cleanup script), smoke start/stop |
| 09:25–09:40 | arm 1 C0 (1 run); go/no-go: `allocatedPos`-step to 512 MiB capacity seen? rows/flush within range? |
| 09:40–10:10 | arm 2 M × 3 (≈ 8–10 min each incl. start and cleanup) |
| 10:10–10:45 | arm 3 CTL × 3 |
| 10:45–11:20 | arm 4 INT × 3 |
| 11:20–11:55 | arm 5 8 GiB / 1 GiB × 3 |
| 11:55–12:30 | arm 6 4 GiB / 768 MiB × 3 |
| 12:30–13:00 | arm 7 2 GiB / 512 MiB × 3 |
| 13:00–13:15 | arm 8 (start by 13:15 at the latest) |
| 13:15–14:00 | stop all, item 9, §3/§4, write-back, cleanup |

**If C0 shows the prediction is off:** if C0's mapping per flush stays below 256 MiB used (r lower than predicted), stage 2 records a dated amendment before any M reading: raise `ck` to 2,000 characters (r rises slightly; rows per flush halve, so the mapping per flush stays near the memtable size) or, if r < 0.75, move M to the 8 GiB / 1 GiB condition (arm 5 becomes the verdict condition) — both keep every constraint at its default.

**Drop order** (first dropped first): arm 8 → arm 9 → arm 7 cut to 1 run → arm 6 cut to 1 run → arm 5 cut to 1 run. Arms 1–4 are never dropped (V1, V2, V4).

`sha256 of §1–§2 at freeze: 000b11cb1c03cffb264c9ed11356c74fabba8ee17e16775f9756524089547fa3` · computed over the lines from `## 1. Candidate` up to, not including, this line (`sha256sum` of that byte range). Amendments after the freeze: dated, with reason.

## 3. Runs (stage 2)

*Stage 2: a fresh phase-2 OOM-agent session (Claude Code), 2026-11-21, ms0617. Freeze hash checked at 08:13 EST: the §1–§2 byte range hashes to `000b11cb…7fa3`, as recorded.*

### 3.0 Amendments (dated, each before the readings it affects)

- **A0 (2026-11-21 08:15 EST, environment only).** Run folders are `/mydata/s4/u13/<run>/` (lower-case `u13`, the folder the session was told to use) instead of `/mydata/s4/U13/<run>/`. The `gc.log` is the one `cassandra-env.sh` adds by itself (`-Xlog:gc=info,heap*=trace,…` to `$CASSANDRA_LOG_DIR/gc.log`), so no GC-log option was added. `-Dcassandra.printHeapHistogramOnOutOfMemoryError=true` (instrument: prints the heap histogram at the first OOM) is added through `JVM_EXTRA_OPTS`. Default ports (7000/9042/7199) are used. The load driver is `harness/Load.java` (Java driver 3.12.1 from `lib/`; `cassandra-stress` was not used). No memory-relevant change.
- **A1 (2026-11-21 08:21 EST, harness fix, before any M reading).** The first C0 attempt (`c0-aborted`, 08:17–08:20) ended after 68 s because `Load.java` quit on 200 consecutive write timeouts: the writes block at the memtable pool limit (heap/4) while two flushes run, and the default 2 s write timeout fires. The driver now counts timeouts and keeps loading; it stops only after 120 s with no successful batch. The aborted attempt is kept as a calibration reading (below); C0 was rerun as `c0`.
- **A2 (2026-11-21 08:24 EST, the design's own C0 rule, before any M reading).** C0 (attempt `c0-aborted`) measured **r ≈ 0.57**, below the 0.75 threshold of §2.9 "If C0 shows the prediction is off":
  - the memtable is charged ≈ **2.1 KB per row**, not ≈ 1.2 KB: flushes of 341.6 / 341.4 / 341.6 MiB on-heap (33 % of the 1 GiB limit) held 166,310 / 169,800 / 190,850 rows (`Writing Memtable-t@…` lines);
  - the RowMapping per flush (≈ 166–191 k rows × ≈ 1.2 KB ≈ 195–225 MiB used) reached a **256 MiB capacity**, not 512 MiB: the `direct` pool rose in whole-buffer steps of 64 → 128 → 128 MiB (13:19:03 → :07 → :13 → :18 UTC) to **557.0 MiB** with both flush writers active (flushes 1 and 2 overlapped 13:18:52–13:19:24), i.e. 2 × 256 MiB + B0 ≈ 45 MiB.
  
  Per §2.9 (r < 0.75), **the verdict condition M moves to 8 GiB / 1 GiB** (arm 5 becomes the verdict condition, 3 runs). To keep V2 and V4 under the same budget as the verdict condition, **CTL and INT run at 8 GiB / 1 GiB** (3 runs each). The former arm 2 (4 GiB / 512 MiB) stays as a budget-ladder arm (3 runs). Revised prediction, from the measured 2.1 KB/row and r ≈ 0.57: at 8 GiB a flush is ≈ 683 MiB of memtable ≈ 333 k rows ≈ 390 MiB `allocatedPos` → **512 MiB capacity per flush**; one flush alone (512 + B0) stays under 1 GiB, so the OOM needs **the two flush writers overlapping** (C0 shows they do: the flush is slower than the load), 2 × 512 MiB + B0 > 1 GiB → `OutOfMemoryError: Direct buffer memory` in a `PerDiskMemtableFlushWriter` thread at flush 2's 256 → 512 MiB step. Predicted 3/3 (timing-dependent; report n/N). 4 GiB / 512 MiB: same two-writer shape (2 × 256 + B0 > 512, already seen as 557 MiB live in C0) → predicted 3/3. CTL and INT at 8 GiB / 1 GiB: predicted 0/3. 4 GiB / 768 MiB (arm 6): 2 × 256 + B0 ≈ 557 < 768 → predicted 0/3 (boundary). 2 GiB / 512 MiB (arm 7): ≈ 83 k rows per flush ≈ 97 MiB used → 128 MiB capacity per flush, 2 × 128 + B0 < 512 → predicted 0/3. 15872 MiB / 2 GiB (arm 8): ≈ 645 k rows ≈ 760 MiB used → 1 GiB capacity per flush, 2 × 1 GiB + B0 > 2 GiB with overlap → predicted OOM 1/1. Thread names are `PerDiskMemtableFlushWriter_0:N` (not `MemtableFlushWriter:*`). Arms and order otherwise unchanged; drop order unchanged (with arm 5 now never dropped, arm 2 takes its place in the drop order).

- **A3 (2026-11-21 08:38 EST, calibration readings added, before those readings).** A2 moved the verdict condition to an 8 GiB heap, but C0's env.sh-pairing survival reading (§2.8 arm 1) is at 4 GiB. Two survival readings are added after the planned arms (one run each, no OOM predicted, not an escalation): **C0-8** = 8 GiB / 4 GiB (what `cassandra-env.sh` resolves for a 16 GiB node, whose own heap is 8 GiB) and **C0-16** = 15872 MiB / 7936 MiB (what `cassandra-env.sh` resolves on ms0617 itself, 62 GiB RAM, with nothing set). Prediction: C0-8 peak live ≈ 2 × 512 MiB + B0 ≈ 1.07 GiB < 4 GiB; C0-16 ≈ 2 × 1 GiB + B0 ≈ 2.05 GiB < 7936 MiB (dead mappings of finished flushes are freed by the GC; a failed reservation would call `System.gc()` first). Both: no OOM.

Run order actually used: plan 1 (`harness/plan1.txt`): M, CTL, INT at 8 GiB / 1 GiB interleaved ×3; plan 2 (`harness/plan2.txt`): 4 GiB / 512 MiB ×3, 4 GiB / 768 MiB ×3, 2 GiB / 512 MiB ×3, 15872 MiB / 2 GiB ×1, C0-8, C0-16. A run is one `harness/run.sh` call from a clean start (new data/commitlog directories, fresh JVM); `harness/queue.sh` runs a plan in order and starts nothing at or after 13:15 EST.

### 3.1 Environment

- **Node:** ms0617 = `node4.jason92-326377…utah.cloudlab.us` (Utah m400), **aarch64**, 8 cores, 62 GiB RAM (`free -m`: 64,249 MB), kernel 5.15.0-191-generic, Ubuntu 22.04, swap 8 GiB present (the measured JVM ran in `systemd-run --user --scope -p MemorySwapMax=0`), cgroup v2, no container limit. No other `CassandraDaemon` at 08:13 or at any run start (checked by `run.sh`); `/mydata/s2r2` and `/mydata/u1r2` untouched. `/mydata` 36 GiB free at the start, ≥ 33 GiB throughout.
- **Build:** `/mydata/s4/cassandra-base`, `build/apache-cassandra-5.0.9-SNAPSHOT.jar` (log: `Cassandra version: 5.0.9-SNAPSHOT`), OpenJDK 11.0.33+9 (Ubuntu), G1 with the shipped `jvm11-server.options`; `bin/cassandra` adds `-XX:OnOutOfMemoryError=kill -9 %p`.
- **Config diff** (`logs/conf.diff` on the node, every run identical): `cassandra.yaml` only `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` → the run folder; `jvm-server.options` + `-XX:NativeMemoryTracking=summary`. Budget through `MAX_HEAP_SIZE` / `MAX_DIRECT_MEMORY_SIZE`; resolved values read back from `jcmd VM.flags` every run (table below). Every capacity setting of §2.3 at its default; table `u13.t` with default STCS and LZ4.
- **What `cassandra-env.sh` resolves on ms0617** (RAM 64,249 MB, half > 15872): heap **15872 MiB**, `MaxDirectMemorySize` **7936 MiB**; with only `MAX_HEAP_SIZE` set, the direct limit is still 7936 MiB (it is computed from RAM, `cassandra-env.sh:59-66,139-140`).
- **Harness** (`harness/`): `run.sh` (one run: config, start, sampler, NMT, load, stop rule, cleanup), `queue.sh` + `plan1.txt` / `plan2.txt`, `Poll.java` (JMX at 5 Hz: `direct` pool, heap, `u13.t` memtable/flush metrics, BufferPool metrics, GC counts), `Load.java` (load driver, §2.5 rows, 64 batches of 10 rows in flight, CL ONE, protocol V4), `flushes.py`, `analyze.py`, `excerpt.sh`, `hprof_direct.py` (dump attribution, from C1's scanner). Full logs on the node in `/mydata/s4/u13/<run>/logs/` (and `nmt/`); per-run excerpts in `logs/<run>.txt`.
- **Instrument checks (C0 and every run):** (1) the `direct` pool moves in whole trie buffers: every step during an M flush is 8, 16, 32, 64, 128 or 256 MiB (= 256 B · 2^i), sums of two when two buffers land between samples (e.g. +192 = 128 + 64). (2) NMT "Other" = `direct` pool + 176 MiB in every 5 s sample once Netty has started (m8-1: 220 vs 44, 605 vs 429, 733 vs 557, 989 vs 813 MiB); the 176 MiB are Netty's own pooled arenas (11 × 16 MiB `PoolChunk`s in the m8-1 dump, allocated outside `java.nio.Bits`). So the §2.6 item 7 "within 1 %" check holds for the deltas, not the absolute value; recorded as a deviation of the check, not of the run. (3) Load rate recorded per run (below). (4) Client cost on the shared 8-core node (`top` every 10 s, `logs/top.log`): the load driver 0.9–2.8 cores, the JMX sampler 0.06–1.4 cores (highest in its first 20 s); same harness in every arm.

### 3.2 Runs

Times are the node's log times (UTC; EST = UTC − 5). "Load" = rows acknowledged, rows/s over the load window, write timeouts (the writes wait at the memtable pool limit while two flushes run; timeouts are counted, never retried). "Flushes" = `u13.t` flushes started / completed and rows per flush (`Writing Memtable-t@…`); every full-size flush was 33 % of the on-heap limit (H/12: 171 / 341 / 683 / 1,323 MiB at 2 / 4 / 8 / 15.5 GiB). B0 = `direct` pool just before the first `u13.t` flush. Peak = highest `direct` `MemoryUsed` sample (5 Hz). Excerpts: `logs/<run>.txt`.

| Run | Arm | Heap / direct (resolved) | Load: rows, rows/s, timeouts | Flushes; rows per flush | B0 / peak direct (MiB) | Outcome |
|---|---|---|---|---|---|---|
| c0-aborted | C0 (1st attempt) | 4096 / 2048 MiB | 526,580; 7,785; driver quit after 68 s (A1) | 4 / 4; 166,310 – 190,850 | 44.4 / 588.6 (557.0 with both flushes live) | not a valid survive (load stopped); calibration for A2 |
| c0 | C0 | 4096 / 2048 MiB | 1,224,350; 6,669; 3,061 | 8 / 7; 164,260 – 187,140 | 43.9 / 629.1 | **no OOM** (7 full flushes; valid survive) |
| m8-1 | **M** (verdict) | 8192 / 1024 MiB | 1,032,480; 9,354; 660 | 2 / 0; 356,700, 359,630 | 43.8 / 813.0 | **OOM** `Direct buffer memory`, load + 83 s, `PerDiskMemtableFlushWriter_0:1` 13:28:52.008; `Pause Full (System.gc())` 4668M→3425M 1.73 s just before |
| m8-2 | **M** | 8192 / 1024 MiB | 1,053,270; 9,474; 697 | 2 / 0; 359,030, 349,660 | 44.3 / 813.1 | **OOM**, + 89 s, `_0:1` 13:39:28.203; System.gc() 4796M→3452M |
| m8-3 | **M** | 8192 / 1024 MiB | 1,008,630; 9,184; 686 | 2 / 0; 342,270, 355,740 | 44.4 / 813.0 | **OOM**, + 81 s, `_0:1` 13:49:47.245; System.gc() 4762M→3397M |
| ctl8-1 | **CTL** | 8192 / 1024 MiB | 2,636,990; 22,002; 4 | 8 / 8; 355,510 – 391,260 | 44.1 / 118.1 | no OOM (7 full flushes) |
| ctl8-2 | **CTL** | 8192 / 1024 MiB | 2,748,590; 23,241; 4 | 8 / 8; 338,950 – 393,640 | 44.0 / 124.7 | no OOM (7 full flushes) |
| ctl8-3 | **CTL** | 8192 / 1024 MiB | 2,738,470; 23,294; 19 | 8 / 8; 346,520 – 400,550 | 44.4 / 117.9 | no OOM (7 full flushes) |
| int8-1 | **INT** | 8192 / 1024 MiB | 3,465,070; 28,220; 0 | 8 / 8; 460,190 – 529,310 | 43.0 / 44.5 | no OOM (7 full flushes) |
| int8-2 | **INT** | 8192 / 1024 MiB | 3,181,580; 28,382; 0 | 7 / 7; 440,160 – 521,470 | 43.0 / 44.5 | no OOM (6 full flushes) |
| int8-3 | **INT** | 8192 / 1024 MiB | 3,246,730; 28,805; 0 | 7 / 7; 443,580 – 521,040 | 43.1 / 44.5 | no OOM (6 full flushes) |
| m4-512-1 | ladder (old arm 2) | 4096 / 512 MiB | 541,190; 7,495; 396 | 2 / 0; 174,390, 180,990 | 44.0 / 429.1 | **OOM**, + 55 s, `_0:1` 13:59:52.923; System.gc() 2760M→1778M |
| m4-512-2 | ladder | 4096 / 512 MiB | 539,240; 7,563; 441 | 2 / 0; 176,580, 179,880 | 44.4 / 429.1 | **OOM**, + 55 s, `_0:1` 14:02:24.235 |
| m4-512-3 | ladder | 4096 / 512 MiB | 533,670; 7,605; 416 | 2 / 0; 174,600, 181,320 | 44.4 / 429.1 | **OOM**, + 54 s, `_0:1` 14:04:56.496 |
| m4-768-1 | arm 6 | 4096 / 768 MiB | 1,217,900; 6,772; 2,324 | 8 / 7; 163,850 – 191,910 | 44.0 / 629.1 | no OOM (no System.gc()) |
| m4-768-2 | arm 6 | 4096 / 768 MiB | 1,223,600; 7,073; 2,189 | 8 / 7; 155,600 – 192,800 | 44.0 / 637.1 | no OOM |
| m4-768-3 | arm 6 | 4096 / 768 MiB | 1,182,230; 6,591; 2,678 | 8 / 7; 155,080 – 187,340 | 44.0 / 637.1 | no OOM |
| m2-512-1 | arm 7 | 2048 / 512 MiB | 600,890; 5,640; 1,322 | 8 / 8; 80,960 – 95,160 | 44.1 / 316.6 | no OOM |
| m2-512-2 | arm 7 | 2048 / 512 MiB | 604,250; 5,741; 1,349 | 8 / 8; 79,120 – 95,890 | 43.9 / 316.6 | no OOM |
| m2-512-3 | arm 7 | 2048 / 512 MiB | 624,420; 6,018; 1,606 | 8 / 8; 85,060 – 98,210 | 44.2 / 334.2 | no OOM |
| m16-2g-1 | arm 8 | 15872 / 2048 MiB | 1,875,210; 11,799; 1,678 | 2 / 0; 641,830, 627,750 | 44.3 / 1581.1 | **OOM**, + 156 s, `PerDiskMemtableFlushWriter_0:3` 14:34:38.181; System.gc() 7824M→6387M 2.95 s |
| c0-8g-4g | C0-8 (A3) | 8192 / 4096 MiB | 2,473,630; 8,313; 3,833 | 8 / 7; 317,160 – 381,430 | 44.0 / 1261.2 | no OOM |
| c0-16g-env | C0-16 (A3) | 15872 / 7936 MiB (= env.sh on ms0617) | 4,526,970; 10,117; 6,803 | 8 / 6; 605,040 – 694,390 | 44.0 / 2413.1 | no OOM |

**What the readings show, per step of the mechanism:**

- **The holder and its size (U, measured without any K).** In every M-table run the `direct` pool climbs during each flush in whole trie buffers (8 → 16 → 32 → 64 → 128 → 256 → 512 MiB), and only while a `u13.t` flush runs. Capacity per flush: 128 MiB at 2 GiB heap, 256 MiB at 4 GiB, 512 MiB at 8 GiB, 1 GiB at 15.5 GiB (A2's revised prediction, from r ≈ 0.57 and ≈ 2.0 KB of memtable per row: 342–360 k rows per 683 MiB flush at 8 GiB). Nothing in Cassandra counts it: the memtable metrics count only memtables (`AllMemtablesOnHeapDataSize` ≈ 715 MB while the mapping grows to 768 MiB in m8-1), and the Cassandra BufferPools do not move (chunk-cache pool 0 used / 8 MiB size, networking pool 0, in every sample).
- **The endpoint needs the two flush writers.** The flush is slower than the load (M: a 683 MiB flush had not finished 55 s after it started; CTL and INT finish one in 8–17 s), so flush 2 starts 10–22 s after flush 1 and both mappings are live together. The OOM is always the second writer's next doubling: 8 GiB / 1 GiB: 44 + 512 (flush 1) + 256 (flush 2) = 813 MiB, flush 2 asks for 256 MiB → 1,069 > 1,024; 4 GiB / 512 MiB: 44 + 256 + 128 = 429, asks 128 → 557 > 512; 15.5 GiB / 2 GiB: 44 + 1024 + 512 = 1,581, asks 512 → 2,093 > 2,048. In each OOM run the JVM first ran one `Pause Full (System.gc())` (the `Bits.reserveMemory` retry) and the reservation still failed: the bytes were live, not uncollected garbage.
- **Initiating failure (V5):** the first error in `system.log` is, in all 7 OOM runs, `ERROR [PerDiskMemtableFlushWriter_0:N] … StorageAttachedIndexWriter.java:143 - [u13.t.*] Failed to record a row during an index build` / `java.lang.OutOfMemoryError: Direct buffer memory` at `Bits.reserveMemory` ← `ByteBuffer.allocateDirect` ← `BufferType$2.allocate(BufferType.java:35)` ← `InMemoryTrie.allocateBlock(InMemoryTrie.java:151)` ← … ← `InMemoryTrie.putSingleton(:866)` ← `RowMapping.add(RowMapping.java:158)` ← `StorageAttachedIndexWriter.addRow(:280)` ← `SortedTableWriter.append` ← `Flushing$FlushRunnable.writeSortedContents(Flushing.java:171)` (full stack in `logs/m8-*.txt`). `JVMStabilityInspector` then forces a heap OOM (`Force heap space OutOfMemoryError in the presence of …`), the heap dump is written and `-XX:OnOutOfMemoryError=kill -9 %p` ends the JVM.
- **Dump at failure (item 9, m8-1, 4.04 GB HPROF, `logs/m8-1-hprof-direct.txt`):** 221 `allocateDirect` owners = **813.0 MiB** (equal to the sampled pool); **768.0 MiB (94.5 %) are `RowMapping` trie buffers**, referrer chain `DirectByteBuffer` ← `UnsafeBuffer.byteBuffer` ← `UnsafeBuffer[]` ← `InMemoryTrie.buffers` ← `RowMapping.rowMapping` (= 512 + 256 MiB: the two flushes' mappings); the rest is hints buffers 32.2 MiB, BufferPool 8 MiB, Netty/NIO 2.3 MiB, scratch and I/O buffers 2.5 MiB. Netty's 11 × 16 MiB arenas are outside the `Bits` limit.
- **Lifetime: freed only by the GC.** Finished flushes leave their mapping buffers in the `direct` pool until an old-generation collection: C0 peaks at 629 MiB with both live mappings (557) plus finished ones, then drops by 184 + 192 + 128 MiB at a full GC (13:23:49–51); c0-8g-4g peaks at 1,261 MiB for the same reason. Under a tight limit the `System.gc()` retry clears these, so they are not what fails the M runs.
- **Matched control (V2):** CTL moves the 1,000 key bytes into a non-key column: the same 683 MiB memtables (339–401 k rows per flush, as M), the same SAI index, 3 × 7 full flushes at 8 GiB / 1 GiB with the `direct` pool at 118–125 MiB peak (mapping ≈ 16 MiB per flush: steps of 8 MiB) — 0/3.
- **Intervention (V4):** INT, the same M rows without the SAI index: 3 runs, 6–7 full flushes each, `direct` flat at 43–44.5 MiB — 0/3; throughput **28.2–28.8 k rows/s, 0 timeouts** vs M's 9.2–9.5 k rows/s with 660–697 timeouts before the OOM, so the intervention did not avoid the endpoint by doing less work.
- **Budget ladder:** at 4 GiB heap the boundary is between 512 MiB (3/3 OOM) and 768 MiB (0/3; peak 629–637 MiB, no `System.gc()` needed); at 2 GiB heap, 512 MiB survives (0/3; peak 317–334 MiB, two 128 MiB mappings); at 15.5 GiB heap, 2 GiB fails (1/1). **The largest failing direct limit found is 2 GiB (heap 15,872 MiB), 1/1;** the verdict condition 8 GiB / 1 GiB is 3/3. Every failing condition needs `MaxDirectMemorySize` < 2 × (mapping capacity per flush) + B0 ≈ 0.13–0.25 × heap with this key shape; the env.sh pairings tested (4 GiB / 2 GiB, 8 GiB / 4 GiB, 15,872 MiB / 7,936 MiB) did not fail.
- **Deviations from the design:** A0–A3 above; the §2.6 item 7 NMT check holds on deltas only (§3.1); no run started after 13:15 (the last started at 09:42 EST); no other deviation.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status (detail): **`verified-OOM · deployment`**, terminal outcome JVM direct-buffer OOM; direction **unprotected accumulation** (no control applies to the holder; the only bound is implicit: rows per flush × bytes per row × concurrent flush writers). Interpretation: a sizing/accounting gap, suspected implementation defect — an uncharged off-heap structure whose size follows the heap-derived flush threshold rather than the direct budget, with buffers released only by the GC. Not documented as by design (JIRA: no report, §1).

**Reason.** At 8 GiB heap with a 1 GiB direct limit and every capacity at its default, inserting 1,000-character-clustering-key rows into a table with one SAI index ended in `OutOfMemoryError: Direct buffer memory` in 3/3 runs, 81–89 s into the load, each time in a `PerDiskMemtableFlushWriter` thread at `RowMapping.add` → `InMemoryTrie.allocateBlock`, after one `System.gc()` retry. The `direct` pool, read independently of any Cassandra counter, rose in whole trie buffers to 813 MiB = 44 MiB baseline + 512 MiB (flush 1's mapping, 342–360 k rows) + 256 MiB (flush 2's), and flush 2's next 256 MiB doubling crossed 1,024 MiB; the dump at failure attributes 768.0 of the 813.0 MiB of live direct memory to `RowMapping.rowMapping` → `InMemoryTrie.buffers`. The matched control (same 683 MiB memtables and index, key bytes moved to a non-key column) peaked at 118–125 MiB in 3/3 runs with 7 full flushes each, and removing the SAI index removed the growth (direct flat at 44.5 MiB, 3/3) while tripling throughput (28.2–28.8 k vs 9.2–9.5 k rows/s). The same two-writer shape fails at 4 GiB / 512 MiB (3/3: 44 + 256 + 128 MiB, then a 128 MiB request) and at 15,872 MiB / 2 GiB (1/1: 44 + 1,024 + 512 MiB, then a 512 MiB request), and survives at 4 GiB / 768 MiB, 2 GiB / 512 MiB and at the direct limits `cassandra-env.sh` pairs with each heap, which is where the owner's weighing below comes in.

**V1–V7 (verdict condition: 8 GiB heap / 1 GiB direct, M table, defaults, build `cassandra-base` on ms0617):**

| | Met? | Evidence |
|---|---|---|
| V1 Repetition | yes, 3/3 | m8-1, m8-2, m8-3 (§3.2), each from a clean start |
| V2 Matched control | yes, 0/3 | ctl8-1..3: same budget, build, memtable bytes per flush, index; 7 full flushes each; peak 118–125 MiB |
| V3 Measurement | yes | U = `java.nio` `direct` pool at 5 Hz (whole-buffer steps), NMT "Other" (same deltas, + 176 MiB Netty arenas), HPROF attribution; there is no K for this holder (unprotected) |
| V4 Intervention | yes, 0/3 | int8-1..3 (no SAI index): direct flat at 44.5 MiB, 6–7 full flushes, 3.0× the M throughput, 0 timeouts |
| V5 Initiating failure | yes | first error `ERROR [PerDiskMemtableFlushWriter_0:1] StorageAttachedIndexWriter.java:143 … OutOfMemoryError: Direct buffer memory` with the `RowMapping.add` stack in all 3 (`logs/m8-*.txt`); dump of m8-1 at failure: 768.0 / 813.0 MiB in `RowMapping` tries (`logs/m8-1-hprof-direct.txt`) |
| V6 Default constraints | yes | `memtable_heap_space` (heap/4), `memtable_cleanup_threshold` (1/3), `memtable_flush_writers` (2), `memtable_allocation_type` (`heap_buffers`), `file_cache_*`, `networking_cache_size`, compaction, compression all unset/default; config diff = directories + NMT only (§3.1) |
| V7 Acceptable budget | yes by the standing rule (heap 8 GiB and direct 1 GiB ≥ 512 MiB); **below env.sh's own resolution — see the table** | no container limit; swap off for the JVM |

**Per-condition status** (same build, M table unless noted):

| Condition (heap / direct) | n/N OOM | Status |
|---|---|---|
| 8 GiB / 1 GiB (verdict) | 3/3 | `verified-OOM · deployment` (with CTL 0/3, INT 0/3) |
| 4 GiB / 512 MiB | 3/3 | OOM, same shape (no matched control at this budget; supports the law) |
| 15,872 MiB / 2 GiB | 1/1 | OOM (largest failing direct limit found; one run, as planned) |
| 4 GiB / 768 MiB | 0/3 | boundary (survives) |
| 2 GiB / 512 MiB | 0/3 | survives (two 128 MiB mappings) |
| 4 GiB / 2 GiB, 8 GiB / 4 GiB, 15,872 / 7,936 MiB (env.sh pairings) | 0/1 each | survive (peaks 629, 1,261, 2,413 MiB) |

**Each OOM budget against what `cassandra-env.sh` resolves** (for the owner; env.sh sets heap = min(RAM/2, 15,872 MiB) and `MaxDirectMemorySize` = RAM/4, or 7,936 MiB above that cap, even when only the heap is set by hand):

| OOM condition | Direct limit used | env.sh on ms0617 (62 GiB) with this heap set | env.sh on the node whose own heap this is | Ratio used / env.sh | Same heap at env.sh's pairing, measured |
|---|---|---|---|---|---|
| 8 GiB heap | 1,024 MiB | 7,936 MiB | 4,096 MiB (16 GiB RAM) | 1/7.75 (ms0617), 1/4 (16 GiB node) | 8 GiB / 4 GiB: no OOM, peak 1,261 MiB |
| 4 GiB heap | 512 MiB | 7,936 MiB | 2,048 MiB (8 GiB RAM) | 1/15.5, 1/4 | 4 GiB / 2 GiB: no OOM, peak 629 MiB |
| 15,872 MiB heap | 2,048 MiB | 7,936 MiB (this is ms0617's full default) | 7,936 MiB (any node ≥ 31 GiB RAM) | 1/3.9 | 15,872 / 7,936 MiB: no OOM, peak 2,413 MiB |

So the endpoint is reached only with an explicitly set `MaxDirectMemorySize` of about heap/4 or less (fail iff direct < 2 × 2^⌈log2(≈ 0.57 · heap/12)⌉ + ≈ 44 MiB with this key shape); at the pairing env.sh computes by itself it is not reached (peak ≈ 0.3 of the limit, including uncollected mappings of finished flushes). The case meets V7 by the standing ≥ 512 MiB rule; whether a deliberately set 1 GiB direct limit beside an 8 GiB heap counts as `deployment` or `diagnostic` is the owner's call.

**Limits of attribution.**
- One node, aarch64 (m400), one disk; the second writer overlaps because the flush is slower than the load here (a 683 MiB flush with long keys takes > 55 s on this disk). A faster flush could shorten the overlap; with one writer the 8 GiB / 1 GiB arithmetic (44 + 512 + 256 at the last doubling) stays under 1 GiB.
- r (mapping bytes per memtable byte) depends on the key shape: ≈ 0.57 for 1,000-character clustering keys, ≈ 0.02 for the CTL's 8-byte keys. Short-key tables need a much smaller direct limit to fail.
- Multiplicity was what the default flush machinery gives (2 writers, one data directory, one table); more data directories (more writers) or several SAI tables flushing together were not tried and would raise the total.
- The CTL also flushes faster (8–17 s vs > 55 s), so it differs in overlap time as well as mapping size; INT removes the holder with the same rows and is the cleaner attribution.
- The heap ran near full in CTL, INT and C0 (G1 full collections at 4 and 8 GiB); this is the memtable/flush heap load, not claimed here, and no heap OOM occurred.
- Covered duplicates: OC-326, OC-341 (fully); OC-328, OC-329 (the RowMapping part; their heap-side segment writers were present but not measured).

**Clue pattern:** covered by CP-10 (the flush path builds index memory outside the SAI segment-build limiter and outside the memtable pool), with CP-14 (buffers released only by the GC) and CP-8 (direct budget); no new pattern needed. **New holder:** none beyond the design's (the dump's other direct holders are hints buffers, 32 MiB, and pool/Netty buffers).

**Write-back** (candidate list OC-383 row, `_INDEX.md`, retry list): left to the session, per the stage-2 instructions of 2026-11-21 (this agent edited only the case folder).

**Left on the nodes:** ms0617 `/mydata/s4/u13/` 94 MB (per-run `logs/`, `nmt/`, `conf/`, `classes/`, `harness/`, `queue.log`; all data, commitlog and heap dumps deleted; no process running). pc96 (local) `/mydata/u13-dump/` 4.04 GB: the one representative dump (m8-1) and its scan output.
