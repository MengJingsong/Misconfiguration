# C5 — hints_compression compressionBuffer: one retained buffer per hinted destination  <!-- file: cassandra/cases/hints_compression-compressionBuffer--per-destination-writers/hints_compression-compressionBuffer--per-destination-writers.md -->

| Field | Value |
|---|---|
| Case ID | `C5` (convergence · multiplicity; campaign row C5 / P2) |
| From | `OC-61` of the phase 1 OOM candidate list |
| Phase-1 case file | [`hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`) |
| Stage 1 (design) | OOM-agent session (Claude Opus 5.5, workflow subagent), 2026-11-17 22:44–23:30 EST |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

**Summary** (stage 1; the conclusion is filled by stage 2)

- **Conclusion:** pending. Estimated positive: a direct-buffer OOM of the coordinator at heap 2 GiB and
  `MaxDirectMemorySize` up to 1,024 MiB (the value `cassandra-env.sh` resolves for a 4 GiB node) when
  hints with LZ4 hint compression pile up for 64 unreachable nodes of a remote DC.
- **Root cause (hypothesis):** every open `CompressedHintsWriter` keeps its own grow-only direct
  `compressionBuffer`, sized to the largest hint it ever compressed (≤ 16.06 MiB). One writer is open per
  unreachable destination, and nothing bounds the sum: no hints setting, no `BufferPool` and no reservation
  covers it. Only `MaxDirectMemorySize` does. The executor's own comment says this buffer was meant to be
  shared (`HintsWriteExecutor.java:43-44`).

## 1. Candidate

**Candidate row (quoted from the phase 1 OOM candidate list, 2026-11-17):**

> | OC-61 | 2026-11-17 | `hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous` | legacy | [campaign C5 / P2, never run; stage-4 evidence] Each open compressed-hints destination writer keeps its compression buffer (stage 4: 8.04 MiB for one destination, 16.07 MiB for two, beyond the hint slabs), multiplying with the number of hinted destinations; reachability at defaults unverified | CP-7, CP-14 | picked: C5 |

**Campaign row (quoted, `campaign-plan.md`):** "C5 / P2 | convergence · multiplicity | New candidate.
Compressed hints buffers retained per open destination writer. With LZ4 enabled and fixed hint size, vary
the number of destinations whose writers simultaneously retain buffers. | Stage 4 measured 8.04 MiB for one
destination and 16.07 MiB for two after accounting for slabs. Verify reachable writer count, replica
placement, writer closure and other admission bounds. Separate compression buffers from shared hint slabs,
compare with uncompressed controls, and measure direct-memory headroom before testing OOM."

**Phase-1 constraint and check.** No capacity constraint covers the buffer. `CompressedHintsWriter.java:53`
is a grow-only capacity test (`compressionBuffer == null || compressionBuffer.capacity() < estimatedSize`),
followed by `compressor.preferredBufferType().allocate(estimatedSize)` (`:55`). For LZ4 that is a direct
buffer (`LZ4Compressor.java:240-243`) of `4 + maxCompressedLength(S) + 8` = `S + ⌊S/255⌋ + 28` bytes, where S
is the record handed to `writeBuffer`. The buffer is an instance field (`:39`), so there is one per writer,
and it never shrinks. The largest record is `max(max_mutation_size, 16 MiB)` = 16,777,216 B (half the
32 MiB `HintsBuffer` slab, `HintsBuffer.java:150-152`, `HintsService.java:110`), giving a 16,843,037 B
(16.06 MiB) buffer. `max_hints_file_size` (128 MiB) and `max_hints_size_per_host` (0 = off) limit disk, not
this buffer.

**Stage-4 result** ([results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.md),
pc07, x86, 2026-10-25; outcome class true negative, "does not cap"):

- **Unit tier:** the buffer equals `4 + (S + S/255 + 16) + 8` exactly for S = 100 B to 16 MiB. It never
  shrinks. N writers hold N × the buffer (N = 1, 4, 16; ratio 1.0000).
- **Cluster tier, two nodes with B down, 200 × 8 MiB hints:** 8,421,599 B per writer, X = 8.04 MiB.
  With two peers down (`P2`) the two live writers hold 16.07 MiB.
- **`F1` (`max_hints_file_size: 1MiB`):** each writer is closed after one hint, so the post-GC increment is
  0. The peak direct delta was 362 MiB, from churn of closed writers' buffers.

Not tested: more than two destinations, and any budget below 2 GiB direct.

**JIRA prior art** (read only, 2026-11-17, `issues.apache.org/jira/rest/api/2/search`; nothing posted):

| Query | Hits | Relevant |
|---|---|---|
| `project = CASSANDRA AND text ~ "CompressedHintsWriter"` | 1 | 11678 (*cassandra crush when enable hints_compression*, Duplicate of 12728): corrupt-file dispatch error, not memory |
| `project = CASSANDRA AND text ~ "hints_compression"` | 115 | **9428** (*Implement hints compression*, Fixed 3.0.3/3.2): introduced `CompressedHintsWriter`. The executor comment from the hints rewrite (6230) said the compression buffer would be shared, but 9428 made it per writer. 21657 (*hints write buffer not released when the write executor shuts down*, Fixed 5.0.10): the shared 256 KiB write buffer at service restart, a different buffer. 15006 (*Possible java.nio.DirectByteBuffer leak*, Open, 3.11.3, ≈ 15 MiB/day): cause not found, no hints link |
| `project = CASSANDRA AND text ~ "hint" AND text ~ "compression buffer"` | 64 | none on the per-writer hints compression buffer |
| `project = CASSANDRA AND (summary ~ hint OR summary ~ hints) AND (text ~ "direct memory" OR text ~ "Direct buffer memory" OR text ~ "off-heap")` | 6 | 6230, 21657, 13191, 12685, 9573, 2034: none on this buffer |

**Survey CSV** (`stage5-oom-clue-find/jira-oom-survey.csv`), hint rows 2652, 3440, 3624, 5746, 8269, 8285,
9092, 9573, 10972, 11881: heap OOMs from hint delivery paging, hint backlog without backpressure (10972) and
the old `system.hints` table. None involves compression buffers. 20491 (*Document offheap memory used by
Cassandra*, Open) is generic.

**Verdict: `new`.** It is not known-fixed, so it is not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

The case is **convergence · multiplicity**, shaped by
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (multiplicity of a standing
per-owner holder at default capacities). Each holder is bounded on its own, and the aggregate is left to
`MaxDirectMemorySize`. Stage 2 decides the label by measurement: per-writer U ≤ the implicit 16.06 MiB
bound with ΣU + baseline > budget is convergence; the protocol's alternative label, unprotected
accumulation, applies if stage 2 judges the per-hint cap not to be a control of this buffer.

How the memory builds up:

1. A coordinator stores a hint for every replica that is down, within `max_hint_window`
   (`StorageProxy.java:2442-2482`, `shouldHint`).
2. `HintsWriteExecutor` (one thread) moves the hints from the 32 MiB slabs into one `HintsStore` writer per
   destination host ID (`HintsWriteExecutor.java:217-231`, `HintsStore.getOrOpenWriter`).
3. With `hints_compression` set, each writer is a `CompressedHintsWriter`, created at
   `HintsWriter.java:88-89`.
4. A hint larger than the 256 KiB aggregation buffer is passed to `writeBuffer` whole
   (`HintsWriter.java:200-222`). The writer then grows its own direct `compressionBuffer` to the LZ4 bound
   of that record (`CompressedHintsWriter.java:51-56`) and keeps it.

When the writer of an unreachable destination is closed:

- **File roll:** when its file reaches `max_hints_file_size` (`HintsWriteExecutor.java:228-229,247-248`).
- **Dispatch:** when the destination is live again (`HintsDispatchTrigger.java:57-71`, filtered by
  `HintsStore::isLive`).
- **Orphan cleanup:** off by default (`auto_hints_cleanup_enabled: false`, `HintsCleanupTrigger.java:49-50`).
- **Shutdown.**

So while D nodes are unreachable and their files are below 128 MiB, D buffers of up to 16.06 MiB each stay
live in direct memory. They are not part of the `BufferPool` and are not charged anywhere.

What happens at the limit: `Bits.reserveMemory` runs `System.gc()` (no `-XX:+DisableExplicitGC` in
`conf/jvm*.options`), which frees only closed writers' garbage buffers, then throws
`OutOfMemoryError: Direct buffer memory`. The task fails into `FutureTask.run` → `ExecutionFailure.handle`
(`concurrent/FutureTask.java:73-87`) → `JVMStabilityInspector.inspectThrowable`, which logs
"OutOfMemory error letting the JVM handle the error". `forceHeapSpaceOomMaybe` then forces a heap OOM
(`JVMStabilityInspector.java:105-131,193-200`), which triggers `-XX:+HeapDumpOnOutOfMemoryError`
(`jvm-server.options:120`) and `-XX:OnOutOfMemoryError="kill -9 %p"` (`cassandra-env.sh:209`).

**Realistic fault: a remote-DC outage or partition.** The coordinator's own DC is healthy and clients
write at `LOCAL_ONE`, which succeeds locally. Every write is then hinted to its three replicas in the
unreachable DC (the default `hinted_handoff_disabled_datacenters` is empty). The number of destinations is
the number of nodes in that DC. Large hints come from large but legal mutations (a 15 MiB blob, below the
16 MiB `max_mutation_size` and the native message size).

### 2.2 Protection map

One row per allocation domain in the JVM direct budget (`Bits`, `java.nio:type=BufferPool,name=direct`)
unless stated otherwise.

| Domain | Allocation, owner, release | Local contract | Scope and multiplicity | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|---|
| **Hints compression buffer** (claimed holder) | `CompressedHintsWriter.java:55` `allocateDirect(S + ⌊S/255⌋ + 28)`, field `compressionBuffer` (`:39`); freed only when the writer object is unreachable and GC runs its `Cleaner` | none declared; implicit per writer ≤ 16,843,037 B (16.06 MiB), from the per-hint cap | one per open writer = one per hinted destination with an open file; bounded by the number of endpoints in the ring, not by a memory limit | **none** (not in `BufferPool`, no reservation, no hints setting) | standing while the destination is down and its file < 128 MiB; grow-only | JVM direct |
| Hint slabs | `HintsBuffer.create` (`HintsBuffer.java:75-77`), `HintsBufferPool.java:133` | 32 MiB each (`max(2·max_mutation_size, 32 MiB)`), at most 3 (`MAX_HINT_BUFFERS`, `CassandraRelevantProperties.java:351`) | per node | count cap, 96 MiB | standing once created (recycled, not freed) | JVM direct |
| Hints write buffer | `HintsWriteExecutor.java:60` | 256 KiB | one | fixed | standing | JVM direct |
| Chunk cache, networking pools | `BufferPool` | `file_cache_size` = min(512 MiB, heap/4) = 512 MiB; `networking_cache_size` = min(128 MiB, heap/16) = 128 MiB (`DatabaseDescriptor.java:573-577`), at heap 2 GiB | per node | pool caps (overflow is OC-28's subject) | idle here: no reads, no internode traffic, native protocol v4 | JVM direct |
| Commit-log scratch for one 15 MiB mutation | `CommitLog.add` DOB fill (U1's domain) | recycle cap 1 MiB is checked only at close (OC-29) | one write in flight (client keeps one), ≈ 2 × 15 MiB transient | none | transient | JVM direct |
| Native request frames | Netty pooled allocator (protocol v4) | `native_transport_max_message_size` = 16 MiB (default, `DatabaseDescriptor.java:903-905,3237-3240`); in-flight heap/10, per IP heap/40 | one in flight | Netty's own direct counter, **not** `Bits` (B9) | per request | Netty counter (separate) |
| Memtables, decoded mutations | heap | `memtable_heap_space` heap/4 = 512 MiB | per node | flush | flushes | heap 2 GiB (monitored, not the claimed domain) |

### 2.3 Configuration and budget audit

All runs are on one victim JVM, **A**, on `ms0604`.

**Capacity constraints, all at shipped defaults (V6), resolved at heap 2,048 MiB:**

| Constraint | Value |
|---|---|
| `hinted_handoff_enabled` | true |
| `max_hint_window` | 3 h |
| `hints_flush_period` | 10 s |
| `max_hints_file_size` | 128 MiB |
| `max_hints_size_per_host` | 0 (off) |
| `auto_hints_cleanup_enabled` | false |
| `hint_window_persistent_enabled` | default |
| `commitlog_segment_size` | 32 MiB → `max_mutation_size` 16 MiB → slab 32 MiB, per-hint cap 16,777,216 B |
| `MAX_HINT_BUFFERS` | 3 |
| `file_cache_size` | 512 MiB |
| `networking_cache_size` | 128 MiB |
| `native_transport_max_message_size` | default (16 MiB) |
| native in-flight limits | 204.8 / 51.2 MiB |
| `memtable_heap_space` | 512 MiB |
| `concurrent_writes` | 32 |
| every timeout | default |

**Supporting setting, a documented non-default:** `hints_compression: [{class_name: LZ4Compressor}]`.
- `cassandra.yaml:122-127` documents it ("If omitted, hints files will be written uncompressed. LZ4, Snappy,
  and Deflate compressors are supported").
- It is a feature switch, not a capacity constraint. It is the only setting that creates the holder.
- The shipped default is uncompressed, so the result claims "deployments that enable hint compression".
  The Summary of §4 must say so.
- Under the conditions label it is an "accepted, documented value", so `deployment` stays available.

**Environment and topology (disclosed, not capacity):**
- Two DCs with `GossipingPropertyFileSnitch`: `dc1` = A, `dc2` = 64 nodes, all `rack1`.
- `num_tokens: 1` with explicit `initial_token` on every node, instead of 16 with the allocator, so that
  replica placement is computable.
- `dc2` nodes join with `auto_bootstrap: false` (the cluster is empty) and `start_native_transport: false`.
- All instances run on one host at loopback addresses `127.0.5.x`, with distinct JMX ports.
- The `dc2` instances are killed before any reading, so they do not run during measurement.
- Swap is 0 for A (`systemd-run --user --scope -p MemorySwapMax=0`).
- No `MemoryMax`: no container limit is a budget here.

**Budgets (V7, standing rule):**
- Heap: `MAX_HEAP_SIZE=2048M` (G1; 2 GiB is the ideal value).
- Direct: `MAX_DIRECT_MEMORY_SIZE` = D, from the set {512, 640, 768, 896, 1024, 1152, 2048} MiB as
  §2.6 assigns. Every value is ≥ 512 MiB, so V7 is met without a per-case review.
- No container limit, so no owner review is needed.
- Resolved defaults to record:
  - On `ms0604` (64,249 MiB in `free -m`) `cassandra-env.sh` would resolve heap 31,744 MiB and direct
    15,872 MiB (G1 heap limit 31,744; `cassandra-env.sh:51-68`).
  - The claimed node is a **4 GiB node**: `cassandra-env.sh` resolves heap 2,048 MiB and direct
    1,024 MiB there. So D = 1,024 at heap 2,048 is exactly that node's own resolution, and lower D values
    match a 2–3.5 GiB node.
- Stage 2 records `jcmd <pid> VM.flags` (MaxHeapSize, MaxDirectMemorySize, UseG1GC) for every run.

**Build:**
- JDK 11.0.33 (Ubuntu, aarch64), Ant 1.10.12.
- Source: the repository's `systems/cassandra/source/` (5.0.9), copied with
  `experiments/capacity-enforcement-exp/cassandra/stage4-runtime-verification/copy-source.sh` and built with
  `ant jar` at `ms0604:/mydata/s4/cassandra-base` (no build there yet; about 5–6 min on an m400).
- **Unpatched for every arm except I** (§2.7). Record the repository HEAD, `uname -r` and
  `java -version` in §3.

### 2.4 Ceiling arithmetic

The LZ4 buffer for a record of S bytes is `S + ⌊S/255⌋ + 28` B (stage-4 unit tier, exact).
- The workload's hint record holds a 15,728,640 B blob plus a few tens of bytes of mutation and hint
  framing: S ≈ 15,728,7xx B.
- That gives a buffer of **≈ 15,790,4xx B = 15.06 MiB** per destination. Stage 2 takes the exact value from
  the trace.
- Per-writer contract bound: 16.06 MiB.

**Contract sum (feasibility).**
- Fixed pools: chunk 512 + networking 128 + slabs 96 + write buffer 0.25 ≈ 736 MiB.
- Hints buffers: N × 16.06 MiB, with no cap on N except ring size.
- With every pool full, the defaults pass 1,024 MiB at N ≥ 18.
- Convergence is feasible at every D in the plan.

**Expected live demand in this workload** (pools idle):
`U(N) = B0 + slabs (≤ 96) + 0.25 + 15.06 · N` MiB, where B0 is the post-GC direct baseline after start
(measured, expected tens of MiB). Transient on top, at the moment of the next allocation:
- one new 15.06 MiB buffer;
- ≤ 32 MiB for a slab, if not all three are created yet;
- ≈ 30 MiB of commit-log scratch.

| N (destinations) | 15.06 · N | U(N) with 3 slabs, B0 = 30 | Fails at D = 512 / 768 / 1024? |
|---|---|---|---|
| 8 | 120 | 246 | no / no / no |
| 24 | 361 | 487 | at the margin / no / no |
| 37 | 557 | 683 | yes / no / no |
| 48 | 723 | 849 | yes / yes / no |
| 64 | 964 | 1,090 | yes / yes / yes |

So N = 64 should exhaust D = 1,024 MiB at heap 2 GiB. B0 and the slab count only move the boundary by
tens of MiB, and the calibration run fixes them (§2.6).

### 2.5 Workload and environment

**Node:** `ms0604` (Utah m400, **aarch64**, APM X-Gene, 8 cores, 64,249 MiB RAM, 8 GiB swap,
Ubuntu 22.04, kernel `5.15.0-191-generic`, JDK 11.0.33, Ant 1.10.12, Python 3.10.12). Checked read-only
2026-11-17 22:50 EST:

| Check | Reading |
|---|---|
| Java processes | none running |
| Listening ports | 22, 111 and 16505 only |
| `/mydata` | 39 GiB LV, **30 GiB free** |
| Other cases' directories | `s2r2` (6.7 GiB) and `u1r2` (218 MiB), **do not touch** |
| Linger | off |
| `/proj` | not mounted |

Never mix with x86 arms. Everything for this case lives under:
- `/mydata/s4/cassandra-base`: the build;
- `/mydata/c5/`: run data, `inst/`, `template/`, `runs/<run>/`, `dumps/`.

**Topology (built once, before any reading):**

| Instance | Address | JMX port | Token | Role |
|---|---|---|---|---|
| A | `127.0.5.1` | 7299 | `initial_token: 1`, `dc1` | seed, victim, native port 9042, the only live node during readings |
| `dc2` node j (j = 0…63) | `127.0.5.(100+j)` | 7300 + j | T_j = −9,223,372,036,854,775,808 + j · 288,230,376,151,711,744 + 144,115,188,075,855,872 (64 evenly spaced tokens, 2^58 apart, offset 2^57) | seed list `127.0.5.1`, storage port 7000, `auto_bootstrap: false`, `start_native_transport: false`, `MAX_HEAP_SIZE=384M`, `MAX_DIRECT_MEMORY_SIZE=256M` |

**Build the ring:**

1. Start A (heap 2 GiB, direct 2 GiB, no compression).
2. Start the `dc2` nodes in batches of 8. Raise to 16 per batch if the first batch is `UN` within 3 min.
   Wait until A's `nodetool status` shows the batch `UN`, with a 6 min cap per batch; on a cap, read the
   instance logs.
3. Then `kill -9` the batch's PIDs (an outage, not a drain), wait until A shows them `DN`, and delete their
   data, commit-log and hints directories (keep their logs).
4. With all 64 nodes `DN`, create the schema on A with the Java client:
   `CREATE KEYSPACE c5 WITH replication = {'class':'NetworkTopologyStrategy','dc1':1,'dc2':3}` and
   `CREATE TABLE c5.t (k int PRIMARY KEY, v blob)` (default table options).
5. `nodetool drain` A, stop it by PID, and copy its `data/`, `commitlog/` and `saved_caches/` to
   `/mydata/c5/template/` (`hints/` is empty).

A restart from this template brings the 64 peers back from `system.peers`:
- `Gossiper.addSavedEndpoint` marks them dead, and their downtime counts from the restart
  (`Gossiper.java:541-548,2216-2243`), well inside `max_hint_window`.
- `GossipingPropertyFileSnitch` takes their DC from the saved peers (`GossipingPropertyFileSnitch.java:86-106`).

**Clean start of every run:**
1. Remove A's `data/`, `commitlog/`, `hints/` and `saved_caches/`, then `cp -a` the template.
2. Start A with the arm's conf directory (its own `cassandra.yaml`, `cassandra-env.sh` and
   `cassandra-rackdc.properties` for `dc1`) under `systemd-run --user --scope -p MemorySwapMax=0`.
3. Enable linger for the session (`sudo loginctl enable-linger jason92`) and disable it at cleanup.
4. Launch with `( setsid nohup … < /dev/null > /dev/null 2>&1 & )` and kill by PID (root HANDOFF "Lessons").

**Keys** (computed once, by a Java helper `C5Keys` that calls `Murmur3Partitioner` on the build's classes):
- For each `dc2` range j = (T_{j−1}, T_j] (j = 0 wraps), pick the smallest int key k ≥ 0 whose token lies
  in the range.
- Its `dc2` replicas are nodes j, j+1 and j+2 (mod 64): NTS walks `dc2` tokens clockwise, and A's token is
  skipped as `dc1`.
- Writing ranges 0…k−1 reaches the destinations {0…k+1}, so **N = k + 2**.
- In the shakedown, check 3 keys with `nodetool getendpoints c5 t <key>`. It must list A and the predicted
  3 `dc2` addresses.

**Client** (`C5Load`, Java, the build's `cassandra-driver-core-3.12.1-shaded.jar`, as in U1's
`harness-run2`):
- Contact point `127.0.5.1`, `DCAwareRoundRobinPolicy(dc1)`, **protocol V4** (root HANDOFF lessons: v5
  large requests leave direct buffers), CL **LOCAL_ONE**, one request in flight, synchronous.
- Each write is `INSERT INTO c5.t (k, v) VALUES (?, ?)` with a fresh 15,728,640 B random (incompressible)
  blob from `new Random(seed + i)`.
- **W = 62 writes per run**, in range order 0, 1, …, (k−1), cycling.
- Per write it logs the epoch ms, write index, range, key, latency and outcome (ok, timeout, error).
- It keeps going after a `WriteTimeout` (the hints are submitted at the coordinator either way). It stops
  on `NoHostAvailable` (A dead).
- After the last write it waits 15 s (one `hints_flush_period` plus margin).

**Disk per run** (wiped after each run; logs, trace, samples and selected dumps are kept):
- hints ≈ 3 × 62 × 15 MiB ≈ 2.8 GiB;
- data ≈ 0.9 GiB;
- commit log ≈ 1 GiB;
- a dump on OOM ≈ 2 GiB (the forced heap OOM fills the heap).

**Instruments** (sampling must be faster than the growth: one destination per write, about 1–2 s):

1. **JMX sampler** `C5Sample` (Java, 1 s), reading A on JMX 7299. Per sample: epoch ms, plus
   - `java.nio:type=BufferPool,name=direct` `MemoryUsed`, `Count`, `TotalCapacity` (the real resource for
     the claimed domain, `Bits`);
   - heap used;
   - `org.apache.cassandra.metrics:type=Storage,name=TotalHints` count;
   - `org.apache.cassandra.metrics:type=HintsService,*` counts where present.
   A bash loop writes `RssAnon` from `/proc/<pid>/status` once a second.
2. **Byteman trace** (observation only; agent `build/lib/jars/byteman-4.0.20.jar`, `boot:` mode,
   `-Dorg.jboss.byteman.transform.all=true`, trace to a file in the run directory), adapted from the stage-4
   [`hw.btm`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous/hw.btm).
   Rules:
   - `opened`: writer identity, `descriptor.hostId`;
   - `cbuf` at the exit of `CompressedHintsWriter.writeBuffer`: identity, `in`, `cap`, and
     **`buf = identityHashCode($0.compressionBuffer)`** (counts distinct buffers);
   - `closed` at `HintsWriter.close`;
   - `created` at `HintsBufferPool.createBuffer`, the slab count;
   - `direct size ≥ 1 MiB` with stack at `ByteBuffer.allocateDirect(int)` entry.

   This gives U for the holder exactly: the sum of `cap` over open writers' distinct buffers. The trace
   writes about 190 lines per run; it does not change the mechanism, which is a standing sum, not a timing
   race. Run T0 (§2.6) checks that.
3. **Marks:**
   - **M0 (baseline):** A `UN` and `nodetool status` showing 64 `DN` in `dc2`, then 30 s, `jcmd GC.run`,
     10 s, `jcmd GC.run`, 10 s, read `MemoryUsed` = **B0**.
   - **M1 (plateau, surviving runs):** 15 s after the last write, two `GC.run` 10 s apart, read
     `MemoryUsed` = **U_plateau**, the trace's open-writer buffer sum = **U_cbuf**, and the slabs created.
4. **Heap dumps** (`hprof_direct.py`, from U1's
   [`harness-run2`](../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/harness-run2/hprof_direct.py),
   attributes direct bytes to holders):
   - On OOM, `HeapDumpOnOutOfMemoryError` writes one to `-XX:HeapDumpPath` (set to
     `/mydata/c5/runs/<run>/`).
   - In surviving runs, `jcmd <pid> GC.heap_dump` after M1, only in Cal, the first L and the first I runs.
   - Analyse each with maxHops 3, on the node after the matrix or on the local node after copying. Expect
     DirectByteBuffer owners of ≈ 15,790,4xx B each, held by `CompressedHintsWriter.compressionBuffer`.
   - Keep the first T dump and the Cal dump. Delete the others once their attribution line is recorded
     (disk).
5. **Logs:** A's `system.log`, `debug.log`, `gc.log*`, the launch log, `hs_err*`, `jcmd VM.flags`,
   `/proc/<pid>/cmdline`, the client log and the yaml diff against the shipped `conf/cassandra.yaml`.
   Per run, a `summary.txt` with `EXPECTED:` lines (root HANDOFF stage-4 recipe).

**Endpoint (fixed before readings).** The run counts as a **JVM direct-buffer OOM** when A's `system.log`
has "OutOfMemory error letting the JVM handle the error" with `java.lang.OutOfMemoryError: Direct buffer
memory` (first such error: thread and stack kept) **and** the A process ends.

Other outcomes are recorded as such:
- a heap OOM first;
- Netty `OutOfDirectMemoryError` (a different counter);
- an `FSWriteError`;
- no failure.

### 2.6 Arms, predicted response and stopping budget

N = 64 means k = 62 ranges and W = 62 writes. Every arm uses the same build, heap and timeouts, and the
same 62 writes of 15 MiB. Byteman is on in all arms except T0.

| Run | Arm | D (MiB) | N | Compression | Prediction (fixed now) |
|---|---|---|---|---|---|
| Shake | shakedown (not a reading) | 2,048 | 3 | LZ4 | template restore works: 64 `DN` in `dc2`; 2 writes of 15 MiB to range 0 → `TotalHints` +6, 3 `opened` and 3 distinct `buf`, `getendpoints` as predicted for 3 keys. **If not, stop and amend** (fallback: rebuild the ring inside every run, cut arms per the order below) |
| Cal | calibration, LZ4 | 2,048 | 64 | LZ4 | no OOM. All 62 writes acked. 64 open writers, 64 distinct buffers, each `cap` ≈ 15,790,4xx B (one value). U_cbuf = 64 × cap ≈ 964 MiB (± 1 MiB). U_plateau − B0 = U_cbuf + slabs (≤ 96) + ≤ 4 MiB |
| T1–T3 | test | D* | 64 | LZ4 | direct-buffer OOM 3/3, at a write index w_OOM in [w_pred − 6, 62], with w_pred = ⌈(D* − B0 − slabs − 30)/15.06⌉ − 2. At failure: open-writer buffer sum ≥ D* − B0 − 96 − 64 MiB. Dump: DirectByteBuffers held by `CompressedHintsWriter` ≥ 0.8 × (D* − B0 − 96) |
| L1–L3 | matched control, low multiplicity | D* | N_low | LZ4 | survive 3/3. All 62 writes acked. U_plateau ≤ 0.7 · D*. Open writers = N_low |
| I1–I3 | intervention (§2.7) | D* | 64 | LZ4 + shared-buffer patch | survive 3/3. All 62 writes acked. `TotalHints` +186 (same useful work as Cal). Trace: 64 writers, **1** distinct `buf`. U_plateau − B0 ≤ 96 + 16 + 4 MiB |
| T0 | test without Byteman | D* | 64 | LZ4 | as T (OOM), so the trace does not create the endpoint |
| Bd | upward boundary | D* + 128 | 64 | LZ4 | OOM if U_plateau(Cal) + 30 > D* + 128, else survive; either way it is the boundary reading |

**Pre-registered choices from Cal** (stage 2 computes them before any T run and writes them into §3):

- **D\*** = the largest value in {1,024, 896, 768, 640, 512} MiB with D* ≤ U_plateau(Cal) − 32 MiB.
  - Expected: 1,024 (U_plateau ≈ 1,060–1,090).
  - If even 512 fails the rule, run T at 512 once, then stop the T/L/I matrix. The verdict is then `retry`
    ("more destinations needed"), and §3 records U_cbuf per destination.
- **N_low** = the largest N with B0(Cal) + 96 + 32 + 15.06 · N ≤ 0.7 · D* (minimum 3). Then
  k_low = N_low − 2, and the 62 writes cycle over ranges 0…k_low−1.
  - Expected for D* = 1,024 and B0 ≈ 30: N_low = 37.
  - Each destination then receives ≈ 5 hints (≈ 80 MiB < 128 MiB, no file roll). The bytes written match
    T's.
- **w_pred** as in the T row.

**Order of runs and time plan** (stage-2 wall time must end **before 02:30 EST, 2026-11-18**). Planned
durations: about 7 min per surviving run and about 6 min per OOM run, including restore, start (≈ 1 min on
an m400), marks and stop.

| Step | Work | Planned duration | Latest finish (if stage 2 starts by 23:40) |
|---|---|---|---|
| P0 | node check (`ps`, `ss`, `df`), `copy-source.sh` to the local scratch, then rsync to `/mydata/s4/cassandra-base`, `ant jar` | 15 min | 23:55 |
| P1 | harness under `harness/` (conf generator, `ctl.sh`, `C5Keys`, `C5Load`, `C5Sample`, `c5.btm`, `summary.py`); compile the patched class for I | 25 min | 00:20 |
| P2 | ring build (8 batches × ≈ 3 min), schema, drain, template | 30 min | 00:50 |
| P3 | Shake | 8 min | 00:58 |
| P4 | Cal, then choose D*, N_low, w_pred | 8 min | 01:06 |
| P5 | T1–T3 | 18 min | 01:24 |
| P6 | L1–L3 | 21 min | 01:45 |
| P7 | I1–I3 | 21 min | 02:06 |
| P8 | T0, then Bd, only if they can finish by 02:20 | 13 min | 02:19 |
| P9 | stop and cleanup (below), summary | 6 min | 02:25 |

**Cuts, in this order, when behind:**
1. Drop Bd.
2. Drop T0.
3. If P2 is not done by 00:55, stop adding nodes. Use the M_eff ≥ 48 nodes already joined (tokens as
   planned for those j), with N = M_eff, and re-derive D* by the same rule (expected 768).
4. Never cut T, L or I below 3 runs. If they cannot all fit, run T ×3 and L ×3, record I as not run, and the
   status carries `(no intervention)` (V4).

**Hard stops:** no run starts after 02:12, and every process this case started is gone by 02:25.

**Per-run limit:** 12 min from the A start; on overrun, stop A by PID and record the run as invalid.

**Stopping budget:** the planned endpoint per run is either the first direct OOM (A exits) or the M1
plateau. The run matrix is at most 13 runs. Nothing escalates after an OOM.

### 2.7 Controls and intervention

**V2 matched control (L).** The nearest surviving condition is low multiplicity: the same holder at the
same budget, build, hint size and total bytes, with fewer destinations (N_low) and a 30 % margin.

The uncompressed arm (`hints_compression` absent, no holder) is **not** in the matrix. It is optional,
after T0 and Bd, if time remains: one run at D* with N = 64, predicting U_plateau − B0 ≤ 96 + 4 MiB and
0 `opened` lines.

**V4 intervention (I): one shared compression buffer**, as the `HintsWriteExecutor` comment intends
("will also share a compression buffer", `HintsWriteExecutor.java:43-44`). It is a diagnostic patch, not a
fix proposal. It changes only `CompressedHintsWriter.writeBuffer`:

```java
// C5 diagnostic patch (arm I only): all writers share one compression buffer.
// HintsWriteExecutor is single-threaded; the class lock makes that explicit.
private static ByteBuffer sharedCompressionBuffer = null;   // guarded by CompressedHintsWriter.class

protected void writeBuffer(ByteBuffer bb) throws IOException
{
    synchronized (CompressedHintsWriter.class)
    {
        int originalSize = bb.remaining();
        int estimatedSize = compressor.initialCompressedBufferLength(originalSize) + METADATA_SIZE;
        if (sharedCompressionBuffer == null || sharedCompressionBuffer.capacity() < estimatedSize)
            sharedCompressionBuffer = compressor.preferredBufferType().allocate(estimatedSize);
        compressionBuffer = sharedCompressionBuffer;   // instance field kept as an alias (trace reads it)
        // ... the original lines 57-68 unchanged ...
    }
}
```

Build and use:
- Compile it with `javac -cp "build/classes/main:build/lib/jars/*:lib/*"` into
  `/mydata/c5/patch/classes/`, then copy the class tree into **arm I's own conf directory**.
  `cassandra.in.sh:27` puts `$CASSANDRA_CONF` first on the class path, so the patched class shadows the
  jar's.
- The jar and the tree stay unmodified. The unmodified build runs every other arm, so the original failure
  is reproduced on it.
- Save the exact `diff -u` against the pinned source in `harness/intervention.diff`.
- Check before I1: `javap -p -cp <I conf dir> org.apache.cassandra.hints.CompressedHintsWriter` shows
  `sharedCompressionBuffer`, and in I1 the trace shows one distinct `buf` across writers.

A useful-work check makes sure the intervention does not just stop useful work: I must ack all 62 writes
and add the same hints (+186) as Cal.

### 2.8 Analysis rules and how they map to V1–V7 (fixed now)

| Item | Rule |
|---|---|
| V1 | T1–T3 reach the endpoint of §2.5 (n/N reported) |
| V2 | L1–L3 do not |
| V3 | U_cbuf from the trace (sum of `cap` of open writers' distinct buffers) and from the dumps, against the pool delta U_plateau − B0 or the last sample before the OOM. **K:** no control counts these bytes (K undefined), and §4 says so |
| V4 | I1–I3 do not reach the endpoint at matched load |
| V5 | first-error thread and stack from `system.log`; T1's dump attribution (`hprof_direct.py`); the pre-OOM sampler rows |
| V6 | §2.3 constraints unchanged in T (yaml diff = `hints_compression` plus topology lines only) |
| V7 | D* and heap ≥ 512 MiB |

**Valid run:** the 64 (or N) `dc2` nodes are `DN` at M0, compression shows in the trace (or is absent in an
uncompressed arm), and the client acked every write before an OOM.

**Direction from measurement:**
- per-writer `cap` ≤ 16,843,037 B and the sum + baseline > D → **convergence**;
- if stage 2 finds per-writer U above the per-hint bound → **bypass** (not expected).

**Verdict mapping** (oom-agent playbook):

| Result | Verdict |
|---|---|
| V1–V7 met | true positive (`verified-OOM · deployment`; `diagnostic` only if T0 shows the endpoint needs Byteman) |
| T survives 3/3 at a D* the rule chose, with Cal valid and all 62 writes acked | false positive only if the ceiling arithmetic of §2.4 is also refuted by the measured U_cbuf. Otherwise retry, naming what to change (more destinations, or a budget/hint size the run missed) |
| Endpoint only at a D below the rule's choice, or only with the trace on | retry (or `reproduced-OOM · diagnostic` detail) |

**Cleanup at the end of stage 2:**
- Stop A and any helper by PID. Confirm with `ps -eo pid,cmd | grep '[C]assandraDaemon'` that no process
  under `/mydata/c5` is left, and stop the `--user` scopes.
- `sudo loginctl disable-linger jason92`.
- Delete A's data, commit-log and hints directories and the `dc2` instance directories.
- Keep `/mydata/c5/runs/` (logs, samples, traces, kept dumps), `/mydata/c5/template/` (small) and
  `/mydata/s4/cassandra-base` until the owner accepts the results, and say so in §3.
- Never touch `/mydata/s2r2` or `/mydata/u1r2`.

`sha256 of §1–§2 at freeze: 713e4e4fe3a23987a8b61576fbc8004d4b73cba47a2d8110a0fbf8f45aa18b49 (lines 24–507 of this file: from the `## 1. Candidate` heading up to the line before this one, `sed -n '24,507p' | sha256sum`, 2026-11-17)` · amendments after the freeze: none.

## 3. Runs (stage 2)

*Stage 2 by a fresh OOM-agent session (Claude Opus 5.5, workflow subagent), 2026-11-17 22:55 EST onward.
Freeze hash checked first: `sed -n '24,507p' | sha256sum` = `713e4e4f…aa18b49`, matches §2.*

### 3.0 Pre-registered choices from Cal (written 2026-11-17 23:32 EST, before any T run)

From Cal (§3.3): B0 = 50.3 MiB, U_plateau = 1,048.1 MiB, U_cbuf = 963.77 MiB (64 × 15,790,416 B), slabs 3.

- **D\*** = largest of {1,024, 896, 768, 640, 512} with D* ≤ 1,048.1 − 32 = 1,016.1 → **896 MiB** (1,024 fails
  the rule by 7.9 MiB; the design expected 1,024).
- **N_low** = largest N with 50.3 + 96 + 32 + 15.06·N ≤ 0.7 × 896 = 627.2 → **N_low = 29**, k_low = 27.
- **w_pred** = ⌈(896 − 50.3 − 96 − 30)/15.06⌉ − 2 = ⌈47.8⌉ − 2 = **46**; T predicts the OOM at write index in [40, 62].
- **Bd** = D* + 128 = **1,024 MiB**; U_plateau(Cal) + 30 = 1,078 > 1,024, so Bd predicts OOM.
- Run order: T1–T3, L1–L3, I1–I3, T0, Bd, then the optional uncompressed arm U0 if time remains.

(pending: the rest of §3)

## 4. Conclusion (stage 2)

pending
