# C6 — memtable_heap_space / SlabAllocator region: one uncharged 1 MiB heap region per written table, table count uncapped  <!-- file: cassandra/cases/memtable_heap_space-slab-region--written-table-multiplicity/memtable_heap_space-slab-region--written-table-multiplicity.md -->

| Field | Value |
|---|---|
| Case ID | `C6` (C = convergence case, the ID assigned with the pick; README "ID prefixes". By the protocol's measurement table the predicted class is **bypass, accounting omission**, tagged **mixed** if the per-table schema heap is also needed — see §2.1; stage 2 labels it from the readings) |
| From | `OC-7` of the phase 1 OOM candidate list |
| Phase-1 case file | [`slab-region-size-region-allocate-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/slab-region-size-region-allocate-capacity--autonomous.md) (also [`memtable_heap_space-tryAllocate-limit--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/memtable_heap_space-tryAllocate-limit--guided.md), [`memtable_heap_space-needsCleaning-nextClean--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/memtable_heap_space-needsCleaning-nextClean--autonomous.md)); stage-4 evidence: [recheck 2026-11-17](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/slab-region-size-region-allocate-capacity--autonomous--recheck-2026-11-17.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9; on pc91 `/mydata/s4/cassandra-base`, `git describe` = `cassandra-5.0.9`, jar `apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `960c9a00…2708d66`), OpenJDK 11.0.33 |
| Stage 1 (design) | OOM-agent stage-1 session (workflow), 2026-11-18 ~03:00–03:40 America/New_York; nothing run (read-only node check of pc91 only) |
| Stage 2 (verify) | OOM-agent stage-2 session (workflow, fresh), 2026-11-18 03:13–05:00 America/New_York, pc91, run directory `/mydata/s4/c6-w2` |
| Verdict | **true positive** — `verified-OOM · deployment` (mechanism **mixed**: bypass by accounting omission in D1 + unprotected D2) |

## Summary

- **Conclusion:** a stock Cassandra 5.0.9 node with a 2 GiB heap, every capacity setting at its shipped default and
  2,500 tables in its schema, died with `java.lang.OutOfMemoryError: Java heap space` in **3/3** runs after one 1 KiB row
  had been written into ≈ 1,040 tables (N_OOM 1,044 / 1,040 / 1,041). The heap dumps held **1,071–1,074 live 1 MiB slab
  regions** (2.1 × the 512 MiB `memtable_heap_space` limit), while the pool counter K was 82 MiB and the pool never blocked
  or flushed. The same rows written into one table (control, 3/3) or with `unslabbed_heap_buffers` (intervention, 3/3)
  added only 4.4 MiB of live heap. The OOM also happened at a **4 GiB** heap (4,500 tables, N_OOM 2,333, 2,379 regions;
  1/1 recorded). The thrower's stack in the dump is `SlabAllocator$Region.<init>` ← `SlabAllocator.getRegion` ←
  `SkipListMemtable.put` on a mutation thread. The rest of the planned runs (4 GiB T-2/T-3, C, I and the optional 8 GiB step)
  were cut off by a site outage: every UMass node stopped answering at ≈ 04:04.
- **Root cause:** with the shipped `memtable_allocation_type: heap_buffers`, every memtable that has received a
  write since its last flush holds one 1 MiB on-heap slab region, but the memtable pool (`memtable_heap_space`, heap/4) is
  charged only the bytes written (≈ 1.5 KiB for a 1 KiB row). The pool's flush trigger sees only those counted bytes, no
  age-based flush runs by default, the commit-log trigger is 8 GiB away, and the table-count guardrail ships disabled, so
  N lightly written tables pin ≈ N MiB of heap that no control counts. The per-table schema and metrics heap (≈ 0.32 MiB per
  loaded table, no default cap) makes up the rest of the heap, so the OOM needs both (mixed).
- **Design in one line:** restore a pre-built schema of M empty tables onto a fresh node with a 2 GiB heap (then 4 GiB), write
  one 1 KiB row into each table in turn, and expect a Java heap OOM after ≈ (heap − schema baseline) / 1 MiB tables, 3/3;
  matched control = the same rows into one table (no OOM); intervention = `unslabbed_heap_buffers` (no OOM).

## 1. Candidate

**Candidate row (quoted from `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`):**

> | OC-7 | 2026-11-12 | `slab-region-size-region-allocate-capacity--autonomous` | legacy | [N11; lead list ×4 (blind, E1/E3): `memtable_heap_space-tryAllocate-limit--guided`, `max-cloned-size-allocate-size`, `memtable_heap_space-needsCleaning-nextClean`, `slab-region-size-region-allocate-capacity` (stage-4 measured)] Under the default `heap_buffers` each memtable written since its last flush pins a whole 1 MiB on-heap slab region while the pool counts only bytes written (plus up to 12.5 % region-tail waste), and table count is uncapped: the stage-4 recheck measured ≈ 1 MiB per written table vs 1.49 KiB counted, 400 tables = 400 MiB, 6.25 × a 64 MiB limit with no flush. | CP-1, CP-7 | picked: C6 |

**Phase-1 constraint and check.** The phase-1 entry is `REGION_SIZE` (1 MiB, `SlabAllocator.java:51`) checked at
`Region.allocate` (`:197-206`, the fit test at `:201`): a per-region fit test, not a node cap. The node's memtable cap is
`memtable_heap_space` (default heap/4, `DatabaseDescriptor.java:586-587`), enforced by `MemtablePool.SubPool.tryAllocate`
(`MemtablePool.java:151-161`, refuse when `allocated + size > limit`) and the flush trigger `needsCleaning`/`maybeClean`
(`:125-143`, threshold `memtable_cleanup_threshold` = 1/(1 + 2 flush writers) = 1/3). `SlabAllocator.allocate` charges the
pool the requested `size` (`:89`) and takes a whole `ByteBuffer.allocate(REGION_SIZE)` for the first clone of a memtable
(`:139`); one allocator per memtable (`AbstractAllocatorMemtable.java:118`). The recheck's E3 flag: one live region per table
(and per legacy 2i table) written since its last flush, uncounted beyond the bytes written, multiplied by an uncapped table
count (`tables_warn_threshold`/`tables_fail_threshold` = −1, `Config.java:865-866`).

**What stage 4 measured** (recheck 2026-11-17, run 1b, pc91, 8 GiB heap, verdict **Confirmed — does not cap**): per table
given one 1 KiB write, `[B` heap +0.9999 MiB (1,048,514–1,048,522 B) against +1.492 KiB counted
(`AllMemtablesOnHeapDataSize`); N = 200: 199.95 MiB real vs 0.291 MiB counted; flat across `memtable_heap_space`
64 / 256 / 2048 MiB; 987 B per table under `unslabbed_heap_buffers`; 400 rows into one table cost 2.0 MiB; at a 64 MiB
limit, 400 tables held 399.95 MiB (6.25 × the limit) with no flush of the small tables, while the limit flushed only the
table it counted as large (`ks.t0`, three `MEMTABLE_LIMIT` flushes). Schema of 401 tables created in 19.9 s; live heap
after the schema (no writes, before the JMX warm-up) 201.4 MB histogram total. No OOM was attempted (8 GiB heap, ≤ 0.42 GiB
of growth).

**JIRA prior art** (read only; nothing posted). Sources: `jira-oom-survey.csv` rows CASSANDRA-20298, 3163, 11026, 5982, 2006,
21659; JIRA REST searches on 2026-11-18 (`project=CASSANDRA AND text ~ "slab" AND text ~ "tables"` 33 hits;
`text ~ "SlabAllocator" AND text ~ "region"` 22 hits; `summary ~ "many tables" AND text ~ "memory"` 3 hits) and issue reads:

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-5935 "Allow disabling slab allocation" | Fixed 1.2.10 / 2.0.1 | States the mechanism: "you have a minimum of 1MB of heap per table"; added the opt-in `unslabbed_heap_buffers` (our intervention). The default stayed `heap_buffers`. |
| CASSANDRA-6794 "Optimise slab allocator to enable higher number of column families" | **Open** since 2014 | "the slab allocator allocates 1MB per column family … makes it more difficult to have large numbers of column families"; proposes ramping region size from 8 KB. Unfixed. |
| CASSANDRA-7882 "Memtable slab allocation should scale logarithmically" | Fixed 2.1.3 | Done for the off-heap `NativeAllocator` only (8 KiB → 1 MiB regions); `SlabAllocator` (`heap_buffers`, `offheap_buffers`) keeps the fixed 1 MiB region in 5.0.9 (`SlabAllocator.java:51`). |
| CASSANDRA-7884 "Allow setting region size" | Won't Fix | Region size stays a constant. |
| CASSANDRA-20298 (test failure `CommitLogCQLTest.testSwitchMemtable`) | Fixed 5.0.4 (test-only) | A Java heap OOM in 5.0 with ~849 memtables each holding a 1 MiB region; maintainer: the allocator accounting "consumed a bit but in reality we have a lot of memory used by slabs", "probably can be observed when we have a lot of tables". Only the test was changed. |
| CASSANDRA-3163, CASSANDRA-11026 | Fixed | Earlier slab-pinning release defects (index summary / sstable min-max slices kept regions alive after flush); different holder (post-flush), not this one. |
| CASSANDRA-5982 "OOM when writing … to a very large number of tables" | Fixed 1.2.10 / 2.0.1 | 2,000 tables, pre-`MemtablePool` era (MeteredFlusher lag); different mechanism. |
| CASSANDRA-21659 / 21664 | Duplicate / Patch Available (6.0) | Schema changes cost O(whole schema); creating 10k tables takes 28 min (6.0). Not the holder, but a cost for building our schema (handled by the template, §2.5). |

**Verdict: `known-open`** (CASSANDRA-6794 open; the per-table 1 MiB cost is acknowledged upstream as an anti-pattern cost since
2013, with `unslabbed_heap_buffers` as an opt-in workaround; 5.0.9's `cassandra.yaml` documents neither the per-table cost nor
that `memtable_heap_space` excludes it — its comment says Cassandra "will stop accepting writes when the limit is exceeded").
Not `known-fixed`, so not a positive-control pick. It is not documented as by design in the shipped configuration.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

Write path: `Keyspace.apply` → `SkipListMemtable.put` clones the partition key and cells through the memtable's allocator
(`SkipListMemtable.java:115`, `:124-125`; `BTreePartitionUpdater.java:182`). Under the default `heap_buffers`
(`conf/cassandra.yaml:825`) the pool is `SlabPool(heapLimit, 0, …)` (`AbstractAllocatorMemtable.java:100-102`) and each
memtable gets its own `SlabAllocator` (`:118`). The allocator first charges the pool `size` (`SlabAllocator.java:89`,
`MemtableAllocator.java:169-197` → `MemtablePool.tryAllocate`), then, on the first clone of that memtable, allocates one
`ByteBuffer.allocate(1 MiB)` region (`:126-153`, `:139`) and carves the clone from it. So a table with one 1 KiB row holds
≈ 1 MiB of heap and is charged ≈ 1.5 KiB (stage 4: 1,528 B). Nothing reclaims the region until the memtable is flushed and
discarded. The triggers that could flush a small memtable at defaults all miss it:

- the pool cleaner (`maybeClean` → `flushLargestMemtable`, `AbstractAllocatorMemtable.java:84`, `:249`) fires at counted
  bytes > limit × 1/3 and flushes the **largest counted** memtable; N small tables count N × 1.5 KiB;
- `memtable_flush_period_in_ms` defaults to 0 (`TableParams.java:363`), no age flush;
- the commit-log trigger (`AbstractCommitLogSegmentManager.maybeFlushToReclaim`, `:245-263`) fires only past
  `commitlog_total_space` (default min(8192 MiB, ¼ of the commit-log volume) = 8192 MiB on pc91); the workload writes
  ≤ 5 MB of commit log;
- the table-count guardrail is off (`Config.java:865-866`, checked only in `CreateTableStatement.java:138-145`).

When the heap fills, the first allocation that cannot be satisfied after a full GC throws `OutOfMemoryError: Java heap
space` (most likely the 1 MiB `ByteBuffer.allocate` in `SlabAllocator.getRegion` on a `MutationStage` thread);
`JVMStabilityInspector.inspectThrowable` (`:105-131`) handles it, the shipped `-XX:+HeapDumpOnOutOfMemoryError`
(`jvm-server.options:120`) writes a dump, and the shipped `-XX:OnOutOfMemoryError="kill -9 %p"` (`cassandra-env.sh:209`)
kills the JVM.

**Direction.** Two heap domains are involved (protection map below). In the memtable domain the claimed holder is outside
its contract with the counter inside it: predicted U ≈ N × 1 MiB ≫ C = `memtable_heap_space` while K ≤ 0.02 C →
**bypass, accounting omission** (protocol table, U > C, K ≤ C). The schema/metrics heap of M loaded tables (domain 2) has no
applicable control (guardrail −1: **unprotected configuration**). If the OOM needs domain 2's share as well (predicted: it
does, ≈ 0.3 × heap at 2 GiB), the label is **mixed**. The ID prefix C was assigned with the pick and is kept; stage 2 states
the measured class. Technique notes: [`bypass-playbook.md`](../../../bypass-playbook.md) ("accounting mismatch": fixed
charged usage, varying object shape — here one table vs many) and [`combo-playbook.md`](../../../combo-playbook.md)
(multiplicity → stack).

### 2.2 Protection map

| Domain | Allocation and ownership | Local contract (counter K, limit C) | Scope and multiplicity | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|---|
| D1 memtable slab regions (**claimed holder**) | `SlabAllocator.getRegion` `ByteBuffer.allocate(1 MiB)` (`:139`); owner = the table's live memtable; released when the memtable is flushed and discarded (on-heap: at the next GC) | K = pool `allocated` = Σ requested clone sizes (`:89`); C = `memtable_heap_space` = heap/4 (512 MiB at 2 GiB, 1024 MiB at 4 GiB); hard refuse at C (`MemtablePool.java:156`), cleaner at C/3 | one live region per table/2i memtable with ≥ 1 write since its last flush (+ regions of memtables being flushed, + `RACE_ALLOCATED` stash, `:55,151`); multiplicity = written tables, bounded by nothing (guardrail −1) | none: the cleaner, period flush and commit-log trigger all miss small memtables (§2.1) | standing until flush | Java heap (`-Xmx`) |
| D1' memtable row objects | partition/row/BTree objects of the written rows (`SkipListMemtable`, `BTreePartitionUpdater.java:182`) | charged to the same K (stage 4: ≈ 1.5 KiB per 1 KiB row incl. clone) | per row | same pool | until flush | heap |
| D2 per-table schema and metrics heap | `TableMetadata`, `ColumnFamilyStore`, `TableMetrics` (≈ 100 metrics + histograms per table, JMX MBeans), keyspace/schema maps — created per table at CREATE or at startup load | **no control** (`tables_fail_threshold` −1) | per table loaded (M) | none | standing for the node's life | heap |
| D3 node baseline | system keyspaces' memtables (≈ 2.1 MiB counted at idle, stage 4) and their regions, caches (key cache `min(5% heap, 100 MiB)`, counter cache, prepared statements), Netty/JMX | each cache its own heap-derived cap | per node | separate caps | standing | heap |
| D4 direct / native | Netty buffers, `BufferPool` chunks, commit-log segments | `MaxDirectMemorySize` (auto 15,872 MiB on pc91), networking pool, chunk cache | per node | separate | — | direct; not expected to move (recorded, not a claimed domain) |

**Scope decision (fixed before any run):** U of D1 is compared against `memtable_heap_space`, the control whose documented
contract ("Total permitted memory to use for memtables", `cassandra.yaml:792-799`) claims to cover memtable memory. D2 is
recorded as an unprotected contributor, measured as L0 (§2.6).

### 2.3 Configuration and budget audit

- **Build:** stock 5.0.9 tree copied from `/mydata/s4/cassandra-base` (built; jar sha256 `960c9a004c2dbf9c5318bdc61ddfb3394facc1a889076a9f2bc383e8a2708d66`), no patches, no Byteman, no agents.
- **Node:** pc91 (`node0.jason92-326528`), x86_64, 32 cores, 125 GiB RAM, Ubuntu 22.04, kernel 5.15.0-203-generic, cgroup v2,
  8 GiB swap present (kept at 0 for the measured JVM), `/mydata` 753 GiB ext4 with 712 GiB free (checked read-only 2026-11-18
  01:07 node time; no `CassandraDaemon` running; `/mydata/s4/r8-w1` belongs to R8 and is not touched).
- **Capacity constraints (V6), all at shipped defaults, resolved per heap:**

| Constraint | Shipped default | Resolved at 2 GiB heap | at 4 GiB heap | Label |
|---|---|---|---|---|
| `memtable_allocation_type` | `heap_buffers` (`cassandra.yaml:825`) | `heap_buffers` | same | default (intervention arm: `unslabbed_heap_buffers`) |
| `memtable_heap_space` | heap/4 (`DatabaseDescriptor.java:586-587`) | 512 MiB | 1024 MiB | default, heap-derived |
| `memtable_offheap_space` | heap/4 | 512 MiB (unused by `heap_buffers`) | 1024 MiB | default |
| `memtable_flush_writers` | 2 (one data dir, `:753-755`) | 2 | 2 | default |
| `memtable_cleanup_threshold` | 1/(1+writers) (`:761-763`) | 0.33333334 → cleaner at 170.7 MiB counted | 341.3 MiB | default |
| `commitlog_total_space` | min(8192 MiB, ¼ volume) | 8192 MiB | 8192 MiB | default |
| `memtable_flush_period_in_ms` (table) | 0 (`TableParams.java:363`) | 0 | 0 | default |
| `tables_warn_threshold` / `tables_fail_threshold` | −1 (`Config.java:865-866`) | disabled | disabled | default (unprotected) |
| `REGION_SIZE`, `MAX_CLONED_SIZE` | 1 MiB, 128 KiB (constants, `SlabAllocator.java:51-52`) | — | — | compile-time |
| key / counter / prepared-statement caches, `num_tokens` 16, write timeouts | shipped | resolved values read back and recorded | | default |

- **Budget (V7):** the budget is the Java heap. **2 GiB** (ideal; it is what `cassandra-env.sh` resolves by itself on a
  4 GiB-RAM host, min(RAM/2, 31,744 MiB)) and **4 GiB** (what it resolves on an 8 GiB-RAM host) — both ≥ 512 MiB, so V7 is met
  by the standing rule; set with `MAX_HEAP_SIZE` (G1: `HEAP_NEWSIZE` unset). On pc91 the script would resolve 31,744 MiB;
  the smaller heaps are an explicit deployment budget, recorded as such. `MaxDirectMemorySize` is left to `cassandra-env.sh`,
  which sizes it from RAM even with a hand-set heap (expected 15,872 MiB; read back from the JVM command line and recorded).
  Process/container: the JVM runs in `systemd-run --user --scope -p MemoryMax=<heap+6G> -p MemorySwapMax=0` as a **safety
  guard only** (8G at 2 GiB, 10G at 4 GiB, 14G for the 8 GiB build/diagnostic lifetimes); it must not bind
  (`memory.events` `oom_kill` 0 is a validity check). No container limit is part of the budget, so no owner review is needed.
- **Shipped JVM options kept:** `jvm11-server.options` (G1, `-XX:G1HeapRegionSize=16m` so a 1 MiB array is not humongous,
  `-XX:G1NewSizePercent=50`, `MaxTenuringThreshold=2`), `jvm-server.options` (`-XX:+AlwaysPreTouch`,
  `-XX:+HeapDumpOnOutOfMemoryError`), `cassandra-env.sh` (`-XX:OnOutOfMemoryError="kill -9 %p"`, GC log
  `-Xlog:gc=info,heap*=trace,…:file=${CASSANDRA_LOG_DIR}/gc.log`, `MALLOC_ARENA_MAX=4`). `CASSANDRA_HEAPDUMP_DIR` points at
  the lifetime's directory on `/mydata` (environment, not a JVM option change).
- **Config diff against the shipped `conf/` (every lifetime; environment deviations, each disclosed):** `cluster_name: c6`;
  `listen_address`, `rpc_address`, seeds `127.0.9.1`; `data_file_directories`, `commitlog_directory`, `hints_directory`,
  `saved_caches_directory`, `cdc_raw_directory` under the lifetime directory; `JMX_PORT="7196"` in `cassandra-env.sh`;
  `MAX_HEAP_SIZE` per arm. Intervention arm only: `memtable_allocation_type: unslabbed_heap_buffers` (a capacity setting
  changed in an intervention arm, allowed by V6). Nothing else. Save `yaml.diff` and `env.diff` per lifetime.
- **Authentication:** shipped `AllowAllAuthenticator` (no guardrail would fire anyway; the table guardrail is disabled).

### 2.4 Ceiling arithmetic

Live heap of a test lifetime with M tables loaded and N of them written:
`live(N) ≈ L0(M) + N × r`, with r ≈ 1.0 MiB per written table (stage 4: 1,048,5xx B of region + ≈ 1.5 KiB of row objects)
and L0(M) = B0 + M × b (B0 = idle node, b = schema + metrics heap per loaded table). From stage 4: 401 tables gave a
201.4 MB histogram total; with B0 ≈ 100–150 MiB this suggests b ≈ 0.1–0.25 MiB (stage 2 measures B0 and b, §2.5 step B).

- **Contract capacities:** D1 + D1' C = 512 MiB (2 GiB heap); D3's caps sum to ≲ 150 MiB at 2 GiB (key cache 100 MiB cap,
  counter cache ≤ 50 MiB, prepared statements ≈ 10 MiB; all nearly empty in this workload); D2 has no cap.
  Σ contracts + B0 ≈ 512 + 150 + 150 ≈ 0.8 GiB < 2 GiB: with every control honoured, the heap cannot fill. An OOM therefore
  needs D1 past its contract (bypass) plus D2.
- **Predicted endpoint at 2 GiB, M = 2,500:** L0 ≈ 150 + 2,500 × 0.2 ≈ 650 MiB (range 400–775), so the heap is exhausted
  after N_OOM ≈ (0.70…1.00 × 2,048 − L0) / 1 MiB ≈ 800–1,650 written tables, below M − 1 = 2,499. At the OOM, U(D1) ≈
  N_OOM MiB = 1.6–3.2 × C, K ≈ 2.2 MiB (system tables) + N_OOM × 1.5 KiB ≈ 3.5–4.7 MiB ≤ 0.01 C.
- **At 4 GiB, M = 4,500:** L0 ≈ 150 + 4,500 × 0.2 ≈ 1,050 MiB (range 600–1,275); N_OOM ≈ 1,800–3,500 < 4,499;
  U(D1) ≈ 1.8–3.4 × C (1024 MiB).
- **Controls:** the same M − 1 rows in one table use one or two regions (stage 4: 400 rows = 2.0 MiB; 2,499 rows ≈ 4 MiB of
  regions + rows, K ≈ 3.8 MiB): live ≈ L0 + 5 MiB ≈ 0.3–0.4 × heap, a ≥ 30 % margin. Unslabbed: live ≈ L0 + 2,499 × ≈ 1 KiB.
- **Gate (from the template build, before any arm):** proceed with M if L0(M) ≤ 0.60 × heap (control margin) **and**
  L0(M) + (M − 1) × 1 MiB ≥ 1.10 × heap (the test can run the heap out before the tables run out). Feasible for any
  b ≤ ≈ 1 MiB. If the measured L0 breaks either bound, stage 2 picks M from the build's 500-table checkpoints (§2.5 B) by a
  dated amendment before any arm reading.

### 2.5 Workload and environment (pc91 only)

**Directories (pc91, all local `/mydata`, never NFS):** `/mydata/c6/cassandra` (= `cp -a /mydata/s4/cassandra-base`; check
`git describe` = `cassandra-5.0.9` and the jar sha256 above; never build or run `ant` there), `/mydata/c6/harness/`
(synced from this case folder's `harness/`), `/mydata/c6/tmpl/T2500/`, `/mydata/c6/tmpl/T4500/` (schema templates),
`/mydata/c6/run/` (the current lifetime: `conf/`, `data/`, `commitlog/`, `hints/`, `saved_caches/`, `cdc_raw/`, `logs/`,
`dump/`; recreated per lifetime), `/mydata/c6/logs/<label>/` (kept). Do not touch `/mydata/s4/` except to copy
`cassandra-base`. Address `127.0.9.1`, native 9042, storage 7000, JMX 7196 (check all free before each start).

**Co-tenancy.** Before every lifetime: `ps -eo pid,cmd | grep '[C]assandraDaemon'`, `MemAvailable`. Another experiment's
node (e.g. R8) on pc91 is recorded with its PID and heap; this case proceeds only if `MemAvailable` ≥ 30 GiB and its ports are
free. The endpoint is a per-JVM heap limit, which co-tenancy does not change (it can change timing only); record it as an
environment note.

**Harness to build in stage 2** (`harness/`; base it on the stage-4 recheck harness
`capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/slab-region-size-region-allocate-capacity--autonomous--recheck-2026-11-17/`,
`client.py`, `run.py`, `Jmx.java`):

- `client.py` — bundled Python driver from `$CASSANDRA_HOME/lib` (as the stage-4 `client.py`), protocol 4, CL ONE,
  `WhiteListRoundRobinPolicy(['127.0.9.1'])`, **`schema_metadata_enabled=False`, `token_metadata_enabled=False`** (with
  thousands of tables the driver would otherwise refetch the whole schema per DDL), request timeout 120 s, **unprepared**
  statements in every arm (no prepared-statement cache growth tied to the table count). Commands:
  `schema <first> <last>` (`CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}`,
  then `CREATE TABLE IF NOT EXISTS ks.t<i> (k int PRIMARY KEY, v blob)` with shipped table options, one at a time; logs
  seconds per 100 tables); `spread <first> <last> <rate> <inflight>` (one row `k = 1`, `v` = 1,024 random bytes, into each
  of `ks.t<first>..ks.t<last>` in order); `fill <table> <k0> <n> <rate> <inflight>` (n rows `k = k0..`, same value size,
  into one table). `spread` and `fill` write a progress line every second to `client.csv`
  (epoch ms, last index sent, ok, err, timeouts) and, after the pass, **retry each failed row** in further passes
  (at most 5 passes) — a client retrying failed writes is ordinary behaviour, and it keeps load shedding (expired
  mutations dropped in `MutationStage`) from silently lowering N. They stop at the end, or after 60 s with no successful
  write and no connection. Rate 100 rows/s, at most 8 in flight, in every arm.
- `Sampler.java` — one long-lived local JMX client (port 7196, fixed ObjectNames only, **no pattern queries**: the stage-4
  recheck found a per-table pattern query left ≈ 21 MB of live heap at 401 tables), every 1 s to `sampler.csv`: epoch ms;
  `java.lang:type=Memory` `HeapMemoryUsage.used`; `java.lang:type=MemoryPool,name=G1 Old Gen` `Usage.used` and
  `CollectionUsage.used`; `java.lang:type=GarbageCollector,name=G1 Young Generation` / `G1 Old Generation`
  `CollectionCount`/`CollectionTime`; **K** = `org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize`
  `Value`; `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation` `Count`;
  `org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=CompletedTasks` and `PendingTasks`
  `Value`; `org.apache.cassandra.metrics:type=DroppedMessage,scope=MUTATION_REQ,name=Dropped` `Count` (if that scope name is
  absent, list the `DroppedMessage` scopes once at `s0` before the histograms and use the mutation one). A shell/Python loop
  samples `RssAnon` from `/proc/<pid>/status` every 1 s to `rss.csv`.
- `hprof_scan.py` — reads an HPROF 1.0.2 dump sequentially (heap-dump segments, PRIMITIVE ARRAY DUMP records), prints the
  count and bytes of `byte[]` arrays of length exactly 1,048,576, the total `byte[]` bytes and count, and the total bytes of
  all instance + array records. Run with `python3 -I`.
- `HoldRegions.java` + `instrument-check.sh` — known-answer check before any lifetime: a JVM holding 40 × `byte[1048576]`
  (plus 40 × `byte[1048575]`), `jcmd GC.heap_dump`, scan: must print exactly 40 arrays of 1 MiB (else fix the scanner;
  not a reading). Also check `Sampler.java` against one running node (shakedown, not a reading).
- `run.py <label> <arm> <heap> <template>` — one lifetime, scripted and logged with epoch ms per command, `EXPECTED:` lines
  (read-back, flags, cgroup), node stopped on any exit, no foreground sleeps longer than the step needs; launch with
  `( setsid nohup … < /dev/null > /dev/null 2>&1 & )` and poll in bounded waits. Kill by PID (`-Dcassandra-pidfile` or
  `/proc/*/cmdline` match of the `/mydata/c6/` directory), never `pkill -f`.
- `analyze.py` — per lifetime and per arm: the readings of §2.6 and the checks of §2.7 from `client.csv`, `sampler.csv`,
  `rss.csv`, histograms, scans, `system.log`, `stdout.txt`, `gc.log`.

**Step A — tree and checks (not readings).** `cp -a /mydata/s4/cassandra-base /mydata/c6/cassandra`; versions; instrument
check; a shakedown start/stop with no user tables (verifies ports, scope, read-back; its numbers are not readings but its
idle histogram total is kept as an informative B0).

**Step B — schema templates (one lifetime each; not measured arms).** Heap 8 GiB (`MAX_HEAP_SIZE=8G`, scope `MemoryMax=14G`),
shipped config otherwise, fresh `/mydata/c6/run/`.
1. `B-T2500`: start; 20 s idle; two `jcmd GC.class_histogram` (B0 = total of the second); `client.py schema 0 2499` in five
   chunks of 500, each followed by two histograms (L0 checkpoints at 500, 1,000, 1,500, 2,000, 2,500 tables; b = slope).
   Then `nodetool -h 127.0.0.1 -p 7196 drain`, stop the node by PID, check that `commitlog/` holds no unflushed segment
   needing replay and that `data/ks/` has 2,500 table directories with no sstables; `cp -a /mydata/c6/run/{data,commitlog,hints,saved_caches,cdc_raw} /mydata/c6/tmpl/T2500/`
   (plus the `conf/cassandra.yaml` used, for reference). Apply the gate of §2.4 to M = 2,500 at 2 GiB.
2. `B-T4500` (after the 2 GiB arms and the diagnostic): restore T2500, start (8 GiB), `client.py schema 2500 4499` in four
   chunks of 500 with histograms, drain, stop, copy to `/mydata/c6/tmpl/T4500/`. Gate at 4 GiB.
Every later lifetime uses the same `cluster_name`, address and `num_tokens` as the build (the node identity is in
`system.local`).

**Step C — measured lifetimes.** Each: `rm -rf /mydata/c6/run && mkdir`; write conf (§2.3 diff, the arm's settings);
`cp -a` the template's directories into `run/`; start under the scope; wait until 9042 answers (≤ 600 s); read back
`system_views.settings` (`memtable_allocation_type`, `memtable_heap_space`, `memtable_offheap_space`,
`memtable_cleanup_threshold`, `memtable_flush_writers`, `commitlog_total_space`, `num_tokens`), the table count
(`SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'ks'`, count = M), the JVM command line
(`-Xmx`, `-XX:MaxDirectMemorySize`, G1 flags, `AlwaysPreTouch`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError`),
the scope's `memory.max`/`memory.swap.max`. Then:
- `s0`: 20 s idle, start `Sampler` and the RSS loop, 10 s, two `jcmd GC.class_histogram` (**L0** = total of the second;
  `[B` bytes and instances), 10 s.
- **Workload** (the only difference between arms):
  - **T (test)**, `heap_buffers`: `client.py spread 1 M−1 100 8` (M − 1 rows, one per table `t1..t(M−1)`).
  - **C (matched control)**, `heap_buffers`: `client.py fill t0 1 M−1 100 8` (the same M − 1 rows, same size, rate and
    concurrency, all into `ks.t0`).
  - **I (intervention)**, `unslabbed_heap_buffers`: `client.py spread 1 M−1 100 8` (the T workload).
- **End of a surviving lifetime** (C, I, or a T that does not OOM): 10 s idle; two `jcmd GC.class_histogram`
  (**U_end** = total, `[B`); in the first lifetime of each arm also `jcmd <pid> GC.heap_dump /mydata/c6/run/dump/end.hprof`
  and `hprof_scan.py` (1 MiB-array count); then stop the node by PID.
- **On OOM:** wait (bounded, ≤ 180 s) for `Heap dump file created` in `stdout.txt` and the JVM to exit (shipped
  `kill -9 %p`); scan the dump (`hprof_scan.py`), keep the scan output, `gzip` nothing, delete the `.hprof` after the scan
  (disk); copy `system.log`, `debug.log`, `gc.log*`, `stdout.txt`, `client.csv`, `sampler.csv`, `rss.csv`, histograms,
  `memory.events` to `/mydata/c6/logs/<label>/`.
- After each lifetime: no process left (`ps`), `rm -rf /mydata/c6/run`.

**Lifetimes and order** (labels `<heap>-<arm>-<n>`):
1. `H2-T-1`, `H2-C-1`, `H2-I-1`, `H2-T-2`, `H2-C-2`, `H2-I-2`, `H2-T-3`, `H2-C-3`, `H2-I-3` — heap 2 GiB, template T2500
   (M = 2,500), scope `MemoryMax=8G`.
2. `D8` (diagnostic, U-vs-K calibration): heap 8 GiB, T2500, `heap_buffers`; after `s0`, `spread` in four steps
   `1..500`, `501..1000`, `1001..2000`, `2001..2499`, each followed by 10 s idle and two histograms; per step K and
   `[B`. Gives slope_R (`[B` per written table) and slope_K (K per written table) at M = 2,500, no OOM expected
   (live ≈ L0 + 2.5 GiB < 8 GiB).
3. `B-T4500` (Step B.2).
4. `H4-T-1`, `H4-T-2`, `H4-T-3`, then `H4-C-1`, `H4-I-1` — heap 4 GiB, template T4500 (M = 4,500), scope `MemoryMax=10G`.
   (Budget search upward from the ideal 2 GiB; 8 GiB is **not planned**: it needs a ≈ 8,500-table template, about 30–60 min
   of DDL on top of the plan; stage 2 runs it only if all of the above is done before 06:00 and states it otherwise.)

### 2.6 Instruments and readings (U measured independently of K)

| Reading | Source | When | Meaning |
|---|---|---|---|
| L0 | histogram total (2nd of two `GC.class_histogram`) | `s0` of each lifetime | live heap with M tables, no user writes: B0 + D2 |
| B0, b | histogram totals in `B-T2500` at 0, 500, …, 2,500 tables | Step B | idle baseline; per-table schema/metrics heap (least squares) |
| **U(D1) at OOM** | `hprof_scan.py` on the OOM dump: count × 1,048,592 B of `byte[1048576]` | T arms | the regions; independent of K |
| N_OOM | `client.csv`: tables acknowledged (and sent) at the first `OutOfMemoryError` time | T arms | multiplicity at the endpoint |
| U trajectory | `sampler.csv` old-gen `CollectionUsage.used` and `gc.log` post-GC heap vs tables written | T, C, I | live growth per written table (slope ≈ 1 MiB in T, ≈ 0 in C, I) |
| U_end | histogram total and `[B` after the workload; dump scan in the first C and I lifetime | C, I (and a T that survives) | live heap after M − 1 rows |
| slope_R, slope_K | `D8` histograms and K | D8 | the stage-4 per-table relation at M = 2,500 |
| **K** | `AllMemtablesOnHeapDataSize` (sum of every table's memtable `onHeap().owns()`, system tables included; equals pool `allocated` when no flush is in progress) | 1 s | the control's counter |
| control activity | `BlockedOnAllocation` count; `Enqueuing flush of ks.` lines with reason in `system.log`; `DroppedMessage` mutation count | 1 s / per lifetime | whether the pool or anything else acted |
| first error | first `OutOfMemoryError` in `system.log` (thread name, stack, `JVMStabilityInspector` lines) and `stdout.txt` (`java.lang.OutOfMemoryError: Java heap space`, `Dumping heap to …`, `Heap dump file created`), JVM exit status/`kill -9`, `memory.events` | T arms | V5 |
| process | `RssAnon`, cgroup `memory.current`, `memory.events` | 1 s / end | the scope did not bind |
| GC | `gc.log` (shipped) | continuous | service-loss criterion if no OOM |

Sampling at 1 s is shorter than the growth window (≈ 1 MiB per 10 ms at 100 rows/s → ≈ 100 MiB per sample; the OOM
window is ≈ 10–20 s at 2 GiB). Intrusive instruments (histograms, dumps) are used only at `s0` (before the workload), at
the end of surviving lifetimes, at D8's steps (separate diagnostic lifetime) and at the OOM (the shipped dump); retention,
not timing, is the mechanism, so a full GC at those points does not change it. Overhead check: the Sampler's own live heap
is visible as the `s0` histogram minus the shakedown's idle total.

### 2.7 Predicted response, outcome rows and stopping budget

**Predictions (frozen):**
- **P1 (T, 2 GiB):** each `H2-T-n` ends in `java.lang.OutOfMemoryError: Java heap space` with a heap dump and the JVM killed by
  the shipped `OnOutOfMemoryError`, 3/3, before all 2,499 tables are written.
- **P2 (T):** L0 + N_OOM × 1 MiB in [0.70, 1.02] × heap (2,048 MiB) per run; N_OOM spread across the three runs ≤ 15 %.
- **P3 (T, U vs K):** in the OOM dump, the count of `byte[1048576]` is in [0.90, 1.10] × N_OOM + at most 100 (system-table
  regions + stash); their bytes > 1.5 × C (768 MiB); K at the last sample before the OOM ≤ 0.02 × C (≤ 10.24 MiB);
  `BlockedOnAllocation` unchanged from `s0`; no `Enqueuing flush of ks.` line before the OOM.
- **P4 (C, 2 GiB):** 3/3 survive with all 2,499 rows acknowledged, err 0 after retries; U_end ≤ L0 + 50 MiB and ≤ 0.70 × heap;
  K growth (end − `s0`) in [2, 8] MiB; `byte[1048576]` count in the end dump ≤ 100.
- **P5 (I, 2 GiB):** 3/3 survive with all 2,499 rows acknowledged; U_end ≤ L0 + 50 MiB; old-gen post-GC slope ≤ 16 KiB per
  written table; `byte[1048576]` count in the end dump ≤ 30 (no slab regions: `HeapPool`).
- **P6 (D8):** slope_R in [0.95, 1.10] MiB per written table; slope_K in [1.0, 3.0] KiB per written table; no flush of `ks.`
  tables; no OOM.
- **P7 (T, 4 GiB):** as P1–P3 with heap 4,096 MiB and C = 1,024 MiB (3/3 if time allows the three runs; otherwise report n/N);
  `H4-C-1`, `H4-I-1` survive as P4/P5.
- **Validity (every lifetime):** read-back equals the arm; JVM flags as §2.3; table count = M; scope `memory.max` as set and
  `oom_kill` 0; `-Xmx` as the arm; the workload started (first-trigger check: ≥ 50 rows acknowledged in the first 10 s);
  no `ks.` flush before the endpoint; no `ERROR` in `system.log` before the endpoint other than the OOM's.

**Outcome rows:**

| Readings | Verdict direction |
|---|---|
| P1–P5 hold (and P6) | **true positive** candidate: `verified-OOM · deployment`, mechanism bypass (accounting omission, D1) — tagged **mixed** if L0 − B0 is needed (N_OOM × 1 MiB < heap − B0 with OOM) |
| T reaches OOM, but C or I also reach OOM | **retry**: not attributed to the regions (D2 or something else dominates); report L0 and the dumps |
| T does not OOM but meets the service-loss criterion (≥ 90 % of wall time in stop-the-world GC over ≥ 60 s, `gc.log`) with K ≤ 0.02 C | **retry** (`verified-gap · service-loss` at best); name what a better design should change (e.g. faster write rate or a pool fill stacked on top) |
| T writes all M − 1 tables without OOM or service loss | **false positive** only if U(D1) grew ≈ 1 MiB per table and the ceiling at this M and heap is shown unreachable; else **retry** (raise M) |
| U(D1) slope ≪ 1 MiB per table (P3/P6 fail) | **false positive** for this holder (the regions are not retained at 5.0.9 defaults as measured in stage 4) unless an instrument fault is found |
| Validity fails | **invalid** lifetime; rerun once if time allows, else retry |

**Stopping budget (finite):** per lifetime: node must serve within 600 s (else stop, invalid); the workload phase is limited
to 15 min; after the client stalls (60 s with no success), wait ≤ 300 s for an OOM, then classify (GC log), take one
histogram if the JVM answers within 120 s, and kill the JVM. At most one rerun per invalid lifetime. **No new lifetime is
started after 06:50 America/New_York on 2026-11-18**; no arbitrary escalation after an OOM (the 4 GiB step is the planned
budget search, not an escalation).

**Time plan (America/New_York, 2026-11-18; stage 2 assumed to start by 03:45; hard end 07:30):**

| Window | Work | Est. |
|---|---|---|
| 03:45–04:15 | Step A: copy tree, harness, instrument check, shakedown | 30 min |
| 04:15–04:35 | `B-T2500` (≈ 2,500 DDL at ≈ 50–150 ms each ≈ 2–6 min, plus histograms, drain, copy); gate | 20 min |
| 04:35–05:20 | nine 2 GiB lifetimes (start with 2,500 tables ≈ 1.5–2 min, `s0` 1 min, 25 s of writes, OOM + 2 GiB dump ≈ 0.5 min, scan ≈ 1 min) ≈ 5 min each | 45 min |
| 05:20–05:30 | `D8` | 10 min |
| 05:30–05:55 | `B-T4500` (2,000 more DDL at a larger schema, ≈ 5–10 min) | 25 min |
| 05:55–06:40 | `H4-T-1..3`, `H4-C-1`, `H4-I-1` (≈ 8 min each) | 45 min |
| 06:40–06:50 | buffer; last lifetime start 06:50 | 10 min |
| 06:50–07:30 | analysis, §3–§4, write-back, cleanup | 40 min |

Priority if late: the nine 2 GiB lifetimes (V1, V2, V4) first, then `D8`, then `H4-T-*`, then `H4-C-1`/`H4-I-1`.
Resource fit: largest JVM 8 GiB heap (+ ≈ 1 GiB non-heap) in a 14 GiB scope against 125 GiB RAM; 32 cores; disk per
lifetime ≤ 5 GiB transient (dump deleted after scanning), templates < 1 GiB, logs < 2 GiB in total, against 712 GiB free.

### 2.8 Controls and intervention

- **Matched control (V2), `C`, ≥ 3 runs at the same heap/build/template/config:** the same M − 1 rows of the same size, the
  same rate, concurrency and client path, into one table (`ks.t0`), so the bytes, request count and schema (D2) match and
  only the number of memtables holding a region differs (1 instead of M − 1). This is the protected path: there the rows
  are charged and fill one region after another. Predicted margin: U_end ≤ 0.70 × heap.
- **Causal intervention (V4), `I`, ≥ 3 runs:** `memtable_allocation_type: unslabbed_heap_buffers` (the documented
  opt-in of CASSANDRA-5935; `HeapPool`, no regions), the T workload unchanged. Removes exactly the claimed holder (D1's
  regions) and keeps D2, D1' and the workload. Throughput check: rows acknowledged per second and err count reported, so
  an intervention that stops work is not mistaken for protection.
- **Calibration:** `D8` gives the per-table slope of real vs counted at M = 2,500 (stage-4 relation at scale);
  `B-T2500`/`B-T4500` give B0 and b (D2's share).
- **Not used (and why):** a Byteman/patched build (not needed: the intervention is a shipped setting); legacy 2i tables
  (each index has its own memtable and region, the same mechanism with fewer CREATE statements per region but also a
  per-index CFS cost — kept as a variant for a retry); stacking a counted pool fill on one table (adds ≤ C/3 = 170 MiB at
  2 GiB; would raise the largest failing budget but blurs attribution — a variant for a retry).

**Cleanup and leftovers.** Stop every JVM this case started (by PID); `rm -rf /mydata/c6/run`; keep `/mydata/c6/logs/`,
`/mydata/c6/tmpl/` and `/mydata/c6/cassandra` and say so in §3; delete scanned `.hprof` files. Commit small excerpts
(`client.csv` heads/tails, `sampler.csv` around the OOM, scan outputs, histogram heads, first-error lines, `analyze.py`
output) to `logs/` in this folder.

`sha256 of §1–§2 at freeze: 2a16e1e2cc0b477a130ab3095089d3ab30ded4b7d6915e4105d08104a1807e7d` (computed as `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-18) · amendments after the freeze: none in §1–§2; stage-2 amendments A1–A6 are in §3.2.

## 3. Runs (stage 2)

### 3.1 Environment and checks (2026-11-18)

- **Freeze check:** the §1–§2 hash recomputed at the start of stage 2 (03:13) =
  `2a16e1e2cc0b477a130ab3095089d3ab30ded4b7d6915e4105d08104a1807e7d`, equal to the frozen value.
- **Node:** pc91 (`node0.jason92-326528`), x86_64, 32 cores, 125 GiB RAM, Ubuntu 22.04.2, kernel 5.15.0-203-generic, cgroup v2,
  8 GiB swap present (0 for the JVM: scope `memory.swap.max` 0, read back each lifetime), `/mydata` 753 GiB with 711 GiB free.
  No `CassandraDaemon` ran before or between our lifetimes (co-tenancy check every lifetime: `none`, `MemAvailable` ≈ 127 GB).
  `/mydata/s4/r8-w1` (R8) was not touched.
- **Build:** `/mydata/s4/c6-w2/cassandra` = `cp -a /mydata/s4/cassandra-base`; `git describe --tags` = `cassandra-5.0.9`, jar sha256
  `960c9a00…2708d66` (as §2.3). OpenJDK 11.0.33. No patch, agent or Byteman.
- **JVM (every lifetime, read back from `/proc/<pid>/cmdline`):** `-Xms`=`-Xmx` = the arm's heap, G1 with
  `G1HeapRegionSize=16m`, `G1NewSizePercent=50`, `MaxTenuringThreshold=2`, `AlwaysPreTouch`, `HeapDumpOnOutOfMemoryError`,
  `-XX:OnOutOfMemoryError=kill -9 %p`; **resolved `-XX:MaxDirectMemorySize=15872M`** (from RAM, as predicted).
- **Read-back (`system_views.settings`, every lifetime):** `memtable_allocation_type` = `heap_buffers` (I arms:
  `unslabbed_heap_buffers`), `memtable_heap_space` = `memtable_offheap_space` = 512 MiB at 2 GiB / 1024 MiB at 4 GiB /
  2048 MiB at 8 GiB, `memtable_cleanup_threshold` 0.33333334, `memtable_flush_writers` 2, `commitlog_total_space` 8192MiB,
  `num_tokens` 16, `key_cache_size` 100MiB, `counter_cache_size` 50MiB, `prepared_statements_cache_size` 10MiB at 2 GiB
  (32MiB at 8 GiB), `tables_warn_threshold` = `tables_fail_threshold` = −1. All shipped defaults resolved per heap (V6).
- **Config diff (every lifetime, `yaml.diff`, `env.diff`):** `cluster_name: c6`; `listen_address`/`rpc_address`/seeds
  `127.0.9.1`; the five directories under `/mydata/s4/c6-w2/run/`; `JMX_PORT="7196"`; I arms only
  `memtable_allocation_type: unslabbed_heap_buffers`. Heap via `MAX_HEAP_SIZE`; `CASSANDRA_HEAPDUMP_DIR=/mydata/s4/c6-w2/run/dump`.
- **Scope:** `systemd-run --user --scope -p MemoryMax=8G|10G|14G -p MemorySwapMax=0` (2/4/8 GiB heaps); `memory.max` read back
  equal every lifetime; cgroup `oom_kill` 0 in every lifetime (the scope never bound; RssAnon peak 2.76 GiB at 2 GiB,
  4.98 GiB at 4 GiB).
- **Instrument check (not a reading):** `instrument-check.sh` (a JVM holding 40 × `byte[1048576]` + 40 × `byte[1048575]`,
  `jcmd GC.heap_dump`, `hprof_scan.py`): `region_arrays` 40, `near_region_arrays` 40 — **ok** (repeated after the A3 change: ok).
- **Shakedown (not a reading):** 8 GiB, no user tables; all checks passed; idle histogram total 65,037,816 B (**B0 ≈ 62.0 MiB**);
  every sampler column populated.

### 3.2 Amendments after the freeze (dated 2026-11-18, stage 2; none changes an arm, a setting, a budget or a prediction)

| # | Time | Change | Reason |
|---|---|---|---|
| A1 | 03:14 | All paths under `/mydata/s4/c6-w2/` (`cassandra/`, `harness/`, `tmpl/`, `run/`, `logs/`) instead of `/mydata/c6/` | the stage-2 assignment names `/mydata/s4/c6-w2` as the run directory; environment only |
| A2 | 03:16 | The `Sampler` is the `poll` mode of the stage-4 `Jmx.java` (one JVM, one JMX connection, fixed ObjectNames, 1 s), not a new `Sampler.java`; the RSS/cgroup loop is a thread in `run.py` | same readings, existing reviewed code. `Jmx.java` writes `,` + `,ERR` for a failed attribute; `analyze.py` normalises it. The JMX poll stops answering once the JVM is in back-to-back full GCs, so "K at the last sample before the OOM" is the last valid sample (14–33 s before the dump) |
| A3 | 03:35 | `hprof_scan.py` also reads the HPROF STACK TRACE/FRAME records and prints the traces that contain `SlabAllocator`, `MemtableAllocator` or `OutOfMemory` | V5: the shipped `OnOutOfMemoryError="kill -9 %p"` kills the JVM before Cassandra logs the error, so `system.log` has no OOM line or stack; the dump's thread traces give the thrower. Effective from H2-T-2 (H2-T-1's dump was already scanned and deleted) |
| A4 | 03:35 | After D8's readings: one JMX pattern query per system keyspace for per-table `MemtableOnHeapDataSize` | to attribute the unexpected 82 MiB of K at `s0` (P3 miss). It runs after the last D8 step histogram, so it touches no reading; D8's `U_end` (not a reading) is inflated by it (+367 MB, the stage-4 "pattern query" effect) |
| A5 | 03:30 / 03:36 | The 4 GiB set and the optional 8 GiB step (template `T8500`, M = 8,500, `H8-T-1..3`, `H8-C-1`, `H8-I-1`, scope 14G) queued to run back-to-back after the 2 GiB set | §2.5 allows the 8 GiB step if the plan is done before 06:00; M chosen so the §2.4 gate holds (L0 ≈ 2.9 GiB ≤ 0.6 × 8 GiB). **Not run** (outage) |
| A6 | 03:28 | **N_OOM** = rows acknowledged at or before the heap-dump file's birth time (`stat %W`, 1 s resolution) | no timestamped OOM line exists (A3); the dump starts right after the error |

### 3.3 Schema templates (Step B)

| Template | Tables | Build | Histogram total (MiB) at 0 / 500 / 1,000 / 1,500 / 2,000 / 2,500 tables | b | Gate |
|---|---|---|---|---|---|
| `B-T2500` (8 GiB, from empty) | 2,500 | DDL ≈ 2.9 min with histograms (49 → 88 ms per table) | 61.8 / 221.4 / 379.2 / 536.3 / 695.7 / 851.9 | **0.316 MiB per table** (least squares) | L0 ≤ 0.60 × 2,048 ✓ (852 build, 923 measured); L0 + 2,499 ≥ 1.10 × 2,048 ✓ |
| `B-T4500` (8 GiB, from T2500) | 4,500 | DDL 4.3 min (112 → 142 ms per table) | 2,500: 879.5 → 3,000: 1,072.3 → 3,500: 1,232.2 → 4,000: 1,404.7 → 4,500: 1,563.3 | 0.342 MiB per table | L0 ≤ 0.60 × 4,096 ✓ (1,614 measured); L0 + 4,499 ≥ 1.10 × 4,096 ✓ |

Both templates: `nodetool drain`, 2,500 / 4,500 `ks` table directories, 0 sstables; the next start replayed 0 mutations.
`T8500` was never built (outage).

### 3.4 Lifetimes and readings

Logs on pc91: `/mydata/s4/c6-w2/logs/<label>/` (`session.log`, `summary.json`, `client.csv`, `acks.csv`, `sampler.csv`,
`rss.csv`, `hist-*.txt`, `scan-*.json`, `system.log`, `debug.log`, `gc.log*`, `stdout.txt`, `yaml.diff`, `env.diff`,
`jvm-cmdline.txt`); per-lifetime excerpts were built in `/mydata/s4/c6-w2/excerpts/<label>/`. Readings below are the
`analyze.py` output recorded in this session (see §3.6 for what was copied to `logs/`). All lifetimes passed the validity
checks of §2.7 (read-back, flags, table count = M, scope, `oom_kill` 0, ≥ 50 rows acknowledged in the first 10 s: 968–1,002),
and no `Enqueuing flush of ks.` line appeared in any lifetime.

**2 GiB heap, M = 2,500 (C = 512 MiB), node up in 27 s every time:**

| Lifetime | L0 (MiB) | Workload result | N_OOM | U(D1) at endpoint: `byte[1048576]` in dump | K at last valid sample | `BlockedOnAllocation` Δ | Outcome |
|---|---|---|---|---|---|---|---|
| H2-T-1 | 923.4 | 1,044 ok, then connection closed | **1,044** | **1,074** (1,074 MiB = 2.10 C) | 85,931,745 B (82.0 MiB = 0.160 C), 24 s before the dump | 0 | **OOM** (`Java heap space`, dump 2.34 GB, `kill -9`) |
| H2-T-2 | 923.4 | 1,043 ok | **1,040** | **1,071** (2.09 C) | 86,020,377 B (0.160 C), 14 s before | 0 | **OOM** (dump 2.34 GB) |
| H2-T-3 | 923.4 | 1,041 ok | **1,041** | **1,072** (2.09 C) | 85,989,813 B (0.160 C) | 0 | **OOM** |
| H2-C-1 | 923.4 | 2,499/2,499 ok, err 0, 1 pass, 26.1 s | — | 26 (end dump) | K growth 3.64 MiB | 0 | survived; U_end 927.8 MiB (L0 + 4.4) |
| H2-C-2 | 923.4 | 2,499/2,499 ok | — | — | K growth 3.64 MiB | 0 | survived; L0 + 4.5 MiB |
| H2-C-3 | 923.4 | 2,499/2,499 ok | — | — | K growth 3.64 MiB | 0 | survived; L0 + 4.4 MiB |
| H2-I-1 | 922.0 | 2,499/2,499 ok, err 0, 26.1 s | — | **0** (end dump) | K growth 3.72 MiB | 0 | survived; U_end 926.3 MiB (L0 + 4.4) |
| H2-I-2 | 922.0 | 2,499/2,499 ok | — | — | K growth 3.72 MiB | 0 | survived; L0 + 4.4 MiB |
| H2-I-3 | 922.0 | 2,499/2,499 ok | — | — | K growth 3.72 MiB | 0 | survived; L0 + 4.5 MiB |

T-arm detail: first acknowledgement to dump 33.6 s (T-1), 24.5 s (T-2); writes went at the set 100 rows/s for ≈ 10 s,
then the heap was full: from 80 s uptime (≈ the start of the workload + 10 s) the GC log shows back-to-back
`Pause Full (G1 Evacuation Pause) 1972M->1972M(2048M)` of 290–380 ms each (104 / 87 / 53 such pauses) until the OOM at
123.7 / 121.2 / 107.5 s uptime; largest share of wall time in pauses over 60 s 0.586 / 0.539 / – (below the 90 % service-loss
criterion; the endpoint is the OOM). `stdout.txt` of each: `java.lang.OutOfMemoryError: Java heap space`,
`Dumping heap to …`, `Heap dump file created [2344359189 bytes in 16.706 secs]` (T-1), `# -XX:OnOutOfMemoryError="kill -9 %p"`,
`Killed`. Mutations dropped: 0. Retry passes re-sent the unacknowledged rows to the dead node (≈ 1,455 per pass) and the client
stopped after 60 s without success, as designed. Dump totals: 2.20 GB of shallow objects, of which `byte[]` 1.27 GB (T-1).

**Initiating failure (V5), from the dump's thread traces (A3):** H2-T-2 — the thread whose stack starts with
`OutOfMemoryError.<init>:48` is `SlabAllocator$Region.<init>:179` ← `SlabAllocator.getRegion:139` ← `SlabAllocator.allocate:104`
← `MemtableBufferAllocator$1.allocate:40` ← `ByteBufferCloner.clone` ← `SkipListMemtable.put:115` ← `ColumnFamilyStore.apply:1477`
← `Keyspace.apply:510` ← `Mutation.apply` ← `StorageProxy$LocalMutationRunnable.run:2661`; a second mutation thread was inside
`SlabAllocator$Region.<init>` at the same moment. That is the 1 MiB `ByteBuffer.allocate(REGION_SIZE)` for a newly written
table's first region, as predicted in §2.1.

**D8 (diagnostic, 8 GiB heap, M = 2,500, C = 2,048 MiB):** histogram total / `[B` / K after N written tables:

| N | total (MiB) | `[B` (MiB) | K (B) |
|---|---|---|---|
| 0 | 923.8 | 164.3 | 84,501,537 |
| 500 | 1,424.4 | 664.3 | 85,265,537 |
| 1,000 | 1,925.0 | 1,164.3 | 86,029,537 |
| 2,000 | 2,926.0 | 2,164.3 | 87,557,537 |
| 2,499 | 3,425.6 | 2,663.3 | 88,320,009 |

**slope_R = 1.000 MiB of `[B` per written table** (total 1.001 MiB), **slope_K = 1.492 KiB per written table**; no flush of
`ks.` tables, `BlockedOnAllocation` Δ 0, no OOM; end dump 2,522 `byte[1048576]` (2,522 MiB = 1.23 × C at 8 GiB) for
2,499 written tables. A4: the counted on-heap bytes of the system tables at the end were `system.table_estimates`
54,970,130 B, `system.size_estimates` 24,230,927 B, `system.compaction_history` 4,959,566 B, `system_schema.*` ≈ 0.34 MB,
others < 2 KB: the 84.5 MB of K at `s0` is the size-estimates recorder writing estimates for every table ≈ 30 s after start
(`B-T2500`, which started with no user tables, ended with K = 13.9 MB; `B-T4500`, restored with 2,500 tables, already
showed 63.0 MB at its first histogram). That memory is counted, and
in the C-1 end dump it occupied only 26 slab regions (it is mostly per-cell object overhead, which the allocator charges).

**4 GiB heap, M = 4,500 (C = 1,024 MiB), node up in 37 s:**

| Lifetime | L0 (MiB) | Workload result | N_OOM | U(D1) at OOM | K at last valid sample | Outcome |
|---|---|---|---|---|---|---|
| H4-T-1 | 1,614.3 | 2,333 ok; 12 timeouts, 1 dropped mutation during the GC thrash | **2,333** | **2,379** `byte[1048576]` (2,379 MiB = 2.32 C) | 155,025,012 B (147.8 MiB = 0.144 C), 33 s before | **OOM** (`Java heap space`, dump 4.65 GB in 22.6 s, `kill -9`); first ack to dump 55.7 s; 114 full GCs; peak 60 s pause share 0.581 |
| H4-T-2, H4-T-3, H4-C-1, H4-I-1 | — | — | — | — | — | **not completed / readings lost**: H4-T-2 had started at 04:02:42 when every UMass node stopped answering (§3.5) |

H4-T-1's dump held 5 matching traces: the thrower was `OutOfMemoryError.<init>` ← `Constants$Literal.prepare:266` (parsing the
blob literal of an unprepared INSERT on a native-transport thread), and three other threads were in `SlabAllocator.getRegion:139`
← `SlabAllocator.allocate:104` ← `MemtableBufferAllocator$1.allocate:40`. The failing allocation is whichever comes next once
the heap is full; the dump shows what fills it (2,379 MiB of regions in a 4,096 MiB heap with L0 = 1,614 MiB).

**8 GiB step:** queued (A5), not started.

### 3.5 Deviation: site outage

At 04:04 the ssh session to pc91 was closed by the remote host, then refused; from ≈ 04:14 pc91, pc84, pc72, pc99 and pc75
(the whole `jason92-326528` UMass set) answered neither ping nor ssh. Last state known from pc91: the 2 GiB set, D8 and
`B-T4500` complete, H4-T-1 complete (OOM), H4-T-2 running, the 8 GiB plan queued. Not caused by this case: every JVM ran in a
capped scope (`oom_kill` 0, RssAnon ≤ 5 GiB of 125 GiB) and the controller node was unaffected. A background poll for pc91
ran from 04:15 to 05:00: pc91 (and pc84) still answered neither ping nor ssh at 04:59, so nothing on the node could be
checked, copied or stopped after 04:04.

### 3.6 Leftovers and logs

- On pc91 (if the node and `/mydata` survive): `/mydata/s4/c6-w2/` — `cassandra/` (tree), `harness/`, `tmpl/T2500`, `tmpl/T4500`,
  `logs/` (all lifetimes), `excerpts/`, `jmxcls/`; possibly `run/` and a running H4/H8 lifetime of the queued plans
  (`plan.sh` processes 39272/41646/43338 lineage), which could not be stopped because the node is unreachable. All scanned
  `.hprof` files were deleted by the harness after each scan (a dump of a lifetime still running at the outage, if any, would
  remain in `run/dump/`). **To do when pc91 is back:** `pkill`-free cleanup by PID — stop the `plan.sh` chain and any
  `run.py`/CassandraDaemon whose command line contains `/mydata/s4/c6-w2/` (or `python3 -I harness/run.py down`), copy
  `/mydata/s4/c6-w2/excerpts/` (re-run `harness/excerpts.sh` for the H4 labels) into `logs/`, and remove `run/`.
- In this case folder: `harness/` (`run.py`, `client.py`, `hprof_scan.py`, `HoldRegions.java`, `instrument-check.sh`,
  `Jmx.java`, `analyze.py`, `plan.sh`, `excerpts.sh`). `logs/`: see the note at the end of §4.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`**, direction **mixed** (D1: bypass by accounting
omission; D2: unprotected configuration, table guardrail −1 by default). Interpretation: an accounting gap known upstream
(CASSANDRA-5935 / CASSANDRA-6794, open) — `memtable_heap_space` is documented as the total permitted memtable memory but
excludes the slab slack of each memtable — with a configuration-sizing gap (no default bound on the table count).

**Reason.** At a 2 GiB heap with every capacity setting at its shipped default (`heap_buffers`, `memtable_heap_space` = 512 MiB,
cleanup 1/3, flush period 0, `commitlog_total_space` 8 GiB, guardrails −1), writing one 1 KiB row into each of 2,499 tables of a
2,500-table schema at 100 rows/s ended in `java.lang.OutOfMemoryError: Java heap space` in **3/3** runs after **1,044 / 1,040 /
1,041** tables (spread 0.4 %; (L0 + N_OOM × 1 MiB)/heap = 0.96). Each OOM dump held **1,071–1,074 live 1 MiB slab regions =
2.09–2.10 × C**, while the pool's own counter K stayed at **82 MiB (0.16 C)**, `BlockedOnAllocation` never moved and no `ks.`
table was flushed: U > C with K ≤ C. The matched control (the same 2,499 rows, same rate and client, into one table) survived
**3/3** with live heap L0 + 4.4 MiB; the intervention (`unslabbed_heap_buffers`, the T workload) survived **3/3** with L0 + 4.4 MiB
and 0 regions — removing only the regions removed the endpoint at the same throughput (2,499 rows in 26 s, no errors). The
8 GiB calibration gives exactly **1.000 MiB of `byte[]` per written table against 1.49 KiB counted** (686 : 1). The thrower's
stack is the 1 MiB `ByteBuffer.allocate` in `SlabAllocator$Region.<init>` under `SkipListMemtable.put`. At **4 GiB** (4,500
tables) the endpoint was reached again (N_OOM 2,333, 2,379 regions = 2.32 C, K = 0.14 C; 1/1 recorded). Mixed, not a pure
bypass: N_OOM × 1 MiB = 1,044 MiB < heap − B0 = 1,986 MiB, so the OOM also needs the ≈ 861 MiB of per-table schema and metrics
heap (0.32 MiB per loaded table) that no default control bounds.

| Requirement | Met | Evidence |
|---|---|---|
| V1 Repetition | yes | H2-T-1..3: 3/3 OOM, N_OOM 1,040–1,044 (and H4-T-1 at 4 GiB) |
| V2 Matched control | yes | H2-C-1..3: 3/3 survive, U_end = L0 + 4.4–4.5 MiB (0.45 × heap ≤ 0.70) |
| V3 Measurement | yes | U(D1) from the dump scan (count of `byte[1048576]`), independent of K (JMX `AllMemtablesOnHeapDataSize`); D8 histogram slope |
| V4 Intervention | yes | H2-I-1..3 (`unslabbed_heap_buffers`): 3/3 survive at matched load and throughput, 0 regions |
| V5 Initiating failure | yes | `stdout.txt` OOM + shipped heap dump per T run; thrower stack in the dump (H2-T-2) in `SlabAllocator.getRegion`; dump shows the holder (1,071–1,074 regions) |
| V6 Default constraints | yes | all memtable, commit-log and guardrail settings at shipped defaults, read back resolved per heap (§3.1) |
| V7 Acceptable budget | yes | 2 GiB heap (the ideal of the standing rule) and 4 GiB; `MaxDirectMemorySize` 15,872 M resolved; scope a non-binding guard |

**Predictions.** P1 ✓ (3/3). P2 ✓ (0.959–0.961). P3: regions in [0.90, 1.10] × N_OOM + 100 ✓, bytes > 1.5 C ✓, `BlockedOnAllocation`
unchanged ✓, no `ks.` flush ✓, **K ≤ 0.02 C ✗** — K was 0.16 C because the size-estimates recorder's rows for 2,500 tables
(`system.table_estimates` + `system.size_estimates`, 79 MB) are counted in the same pool; that is counted memory well inside C and
does not change the class (K ≤ C), but the frozen threshold missed it. P4 ✓ (3/3; K growth 3.64 MiB; 26 regions). P5 ✓ (3/3;
live slope 1.8 KiB per row ≤ 16 KiB; 0 regions). P6 ✓ (1.000 MiB, 1.49 KiB, no flush, no OOM). P7: partly — H4-T-1 as P1–P3
(K 0.14 C, same P3 miss); H4-T-2/3, H4-C-1, H4-I-1 lost to the outage.

**Largest budget that reached the endpoint:** 4 GiB (1/1 recorded). 8 GiB was not tried; by the measured relation
(L0 ≈ 62 MiB + 0.32–0.34 MiB × M tables, + 1 MiB per written table) it needs M with 0.34 M + (M − 1) ≳ 0.96 × 8,192 MiB,
i.e. ≳ 5,900 tables loaded (roughly M ≈ 0.72 × heap in MiB).

**Limits.** The endpoint needs a schema in the thousands of tables (≈ 2,500 at 2 GiB, ≈ 4,500 at 4 GiB) and writes to about
40–50 % of them before any flush. 5.0.9 ships the table-count guardrail disabled (`tables_warn_threshold` −1; the 4.0
`table_count_warn_threshold` it replaced is deprecated, NEWS.txt / CASSANDRA-17195), and thousands of tables are treated
upstream as an anti-pattern whose per-table cost is acknowledged (CASSANDRA-5935, 6794). The write pattern is one
small row per table, the least favourable for the counter; real workloads with more rows per table fill the counted pool and
flush sooner. Single node, RF 1. The 4 GiB step has 1/1, not 3/3, and no 4 GiB control or intervention.

**Retry change:** none needed for the verdict. To complete the budget search: rerun `H4-T-2/3`, `H4-C-1`, `H4-I-1` from
`T4500`, and the 8 GiB step with a ≈ 6,500–8,500-table template.

**Logs in this folder:** see `logs/README.md` (what was copied before or after the outage).
