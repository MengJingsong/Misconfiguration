# B15 — commitlog_max_outstanding_replay_bytes: a restart at a smaller heap replays the writer's memtable pool  <!-- file: cassandra/cases/commitlog_max_outstanding_replay_bytes--smaller-heap-restart/commitlog_max_outstanding_replay_bytes--smaller-heap-restart.md -->

| Field | Value |
|---|---|
| Case ID | `B15` (B = bypass; README "ID prefixes") |
| From | `OC-59` of the phase 1 OOM candidate list (Cassandra) |
| Phase-1 case file | [`commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9, last source commit `afcc4348`; repo HEAD `8bf51cc1` at design time); on `ms0611` the built tree `/mydata/s4/b12-w2/cassandra-base` (its `conf/` is identical to the repo's shipped `conf/` except the build-generated `hotspot_compiler`, checked 2026-11-18 08:15 EST) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5, workflow subagent), 2026-11-18 ≈ 08:00–08:40 America/New_York |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (Claude Opus 5.5, fresh workflow subagent), 2026-11-18 08:09–09:45 America/New_York, `ms0611` |
| Verdict | **true positive** — `verified-OOM · deployment` (proposed; `diagnostic` if the researcher does not accept §2.3 (a)/(b)) |

IDs used here: **B15** = this case; **B8** = bypass case 8 (same replay bound, verified at diagnostic conditions:
restore emulation + injected flush stall); **B6** = bypass case 6 (internode queues; its condition A used a
dm-delay **external storage stall** that the researcher accepted as `deployment`); **S2** = combo case 2
(local-write backlog, same dm-delay helper); **OC-59** / **OC-5** = rows of the phase-1 OOM candidate list;
**CP-10** = clue pattern 10 ("a path that skips the limit"); **N3** = the cached serialized copy each
deserialized mutation keeps (`Mutation.java:493`).

## Summary

- **Conclusion (stage 2):** **true positive.** A node whose commit log was written at an 8 GiB heap and that
  restarts at a 1 GiB heap while its data disk stalls dies of `java.lang.OutOfMemoryError: Java heap space`
  during commit-log replay in **3/3** valid runs (4/4 counting one run invalid by a gate), with every capacity
  setting at its default. The same restart from a log written at 1 GiB starts 3/3; the same restart with the
  replay queue bounded to 64 mutations starts 3/3 and replays every mutation. Largest failing heap 1,280 MiB
  (1/1); 1,536 MiB starts (1/1, 92 % live).
- **Root cause:** the replay queue's bound (1,024 mutations / 64 MiB) counts serialized bytes; the queued,
  deserialized P64 mutations hold ≈ 0.9 MiB each (≈ 14× their count). At 1 GiB the heap is gone at
  741–773 queued mutations (K ≈ 46–48 MiB ≤ C = 64 MiB, U ≈ 0.67 GiB), before the bound ever blocks the
  reader. The volume that reaches the queue is set by the writer's memtable pool (≈ 2.08 GiB of replayed
  memtable charge from the 8 GiB writer), not by anything of the replaying JVM.
- **Claim under test:** what commit-log replay re-applies after a crash is bounded by the memtable pool of the
  JVM that *wrote* the log (heap_w/4), not by anything of the replaying JVM. A node restarted at a smaller
  heap (restore onto a smaller node, VM or container downsized) is offered several of its own pools'
  worth of replay without any sstable being removed; if the data disk stalls during the restart, the
  appliers block on the full memtable pool, the reader fills the replay queue to its 1,024 / 64 MiB bound,
  and because that bound counts serialized bytes (≈ 15× under-count for tiny cells, B8) the queued
  mutations plus the pool exceed a 1 GiB heap. B8 needed sstable deletion and a Byteman flush stall for
  the same endpoint; B15 replaces both with a heap change between writer and replayer and an external
  storage stall.

## 1. Candidate

**Row (quoted from `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`, Status as
of 2026-11-18 08:00 EST; not changed by this stage):**

> | OC-59 | 2026-11-17 | `commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous` | legacy | [lead list, back-link, E3, new] The volume replay applies is bounded by the memtable pool of the JVM that wrote the log (heap_w/4), not the replaying one, so a restart at a smaller heap (after an OOM, or a restore onto a smaller node) is offered more than one pool without deleting sstables; the queue fills only if the apply side stalls (inferred). | CP-10 | picked: B15 |

**Phase-1 case.** Constraint `commitlog_max_outstanding_replay_bytes` (JVM property
`cassandra.commitlog_max_outstanding_replay_bytes`, default 64 MiB, with the companion
`cassandra.commitlog_max_outstanding_replay_count`, default 1,024; `config/CassandraRelevantProperties.java:114-115`).
Check: `CommitLogReplayer.handleMutation` (`db/commitlog/CommitLogReplayer.java:513-531`) adds the entry's
**serialized** size to `pendingMutationBytes` (`:517`), submits the apply task to `Stage.MUTATION` (`:518`,
`:331`), and the reader (`main`) waits for the oldest future while `futures.size() > 1024` or
`pendingMutationBytes > 64 MiB` (`:525-529`). Stage-3 estimate `positive` (the bound caps the backlog).

**Stage 4** ([result](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md),
verdict 2026-11-11): **true positive, caps** at unit and cluster tier; backlog heap ≈ 2 × the byte limit for
60 KB blobs (N3 copy). Its cluster tier already used the OC-59 shape, but with custom settings: a **3 GiB load
pool** (`memtable_heap_space: 3072MiB`) replayed into a **256 MiB replay pool** with `concurrent_writes: 1` and
`memtable_cleanup_threshold: 0.99`; 1.5 GiB of replay was offered and the backlog stayed at the limit.

**B8** (the verified case on the same bound, [`bypass/commitlog_max_outstanding_replay_bytes-accounting-mismatch`](../bypass/commitlog_max_outstanding_replay_bytes-accounting-mismatch/commitlog_max_outstanding_replay_bytes--accounting-mismatch.md),
`verified-OOM · diagnostic`, true positive) measured on `ms0625` (aarch64 m400, same hardware as `ms0611`):

- a P64 mutation (`map<int,int>` of 5,900 entries, 63.7 KiB serialized) holds **0.93 MiB** queued (15.0×; ledger L:
  1,015 queued = **947 MiB U vs 63 MiB K**); its memtable charge is ≈ 0.83 MiB; blobs 2.2×;
- condition A (same-heap restart, 512 MiB–2 GiB): the replayed tail was ≈ one pool (506–570 MiB at 2 GiB) and replay
  started 10/10 — the reason OC-59 exists;
- condition X (sstables removed so ≈ 6 pools replay): started 4/4 — reader-bound at ≈ 125–170 P64 mutations/s,
  flushes keep up, the queue never grows;
- condition S (X + 10 s Byteman stall on every flush, 1 GiB): **heap OOM 3/3**, blob 0/3, `count=64` 0/3; 2 GiB
  started at 70 % live after Full GC.

So the bound is a bypass by accounting mismatch (U > C, K ≤ C) once the queue is full; B8 left open whether
the two diagnostic deviations (sstable removal, injected stall) can be replaced by deployment conditions.
OC-59 names the first replacement (a smaller replaying heap). This design adds the second: an external
storage stall (dm-delay), the fault B6 condition A used and the researcher accepted as `deployment`.

**JIRA prior art** (read only, 2026-11-18; nothing posted). Local survey
`capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (grep `replay|commitlog`) and
Apache JIRA REST search, queries: `project=CASSANDRA AND summary ~ "replay" AND (summary ~ "OOM" OR summary ~
"memory" OR description ~ "OutOfMemoryError")` (4 hits), `text ~ "commit log replay" AND text ~ "OOM"` (19),
`text ~ "replay" AND text ~ "smaller heap"` (8), `text ~ "commitlog_max_outstanding_replay"` (3).

| Issue | What | Resolution | Relation |
|---|---|---|---|
| CASSANDRA-609 | replay ignored memtable limits (`Table.applyNow`) | Fixed 0.5 | replay now goes through the memtable pool; not this |
| CASSANDRA-885 | OOM on replay: unbounded ROW-MUTATION-STAGE queue (2.6 GB) | Fixed 0.6 | introduced the outstanding-replay bound this case tests |
| CASSANDRA-6087 | replay OOM: MeteredFlusher started only after replay | Fixed 1.2.11 / 2.0.2 | flushing during replay works in 5.0.9 (B8 X) |
| CASSANDRA-7533 | make `MAX_OUTSTANDING_REPLAY_COUNT` configurable | Fixed 2.0.15 / 2.1.5 | the count property used as the intervention here |
| CASSANDRA-8639 | OOM on replay with dense mutations; proposed charging `unsharedHeapSize()` | Fixed 3.2 (committed form counts serialized bytes) | the accounting mismatch B8 measured; incomplete fix, not a regression |
| CASSANDRA-20084 | flushes stuck (lost wakeup) → memtable pool exhausted → OOM (4.1.1) | Fixed 4.1.9 / 5.0.4 | a different cause of a stalled apply side; fixed in 5.0.9 |
| CASSANDRA-1967 | "replay shouldn't end with a flush" | Not A Problem | mentions oversized memtable thresholds only in passing |

No issue states that the replay volume is bounded by the **writer's** pool, or reports a replay OOM after a
heap reduction. **Verdict: `new`** for the OC-59 shape (the underlying under-count is `known-fixed` in the
CASSANDRA-8639 sense, but its committed fix is what still admits ≈ 15× its nominal bytes; B8 is the in-house
positive).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

Direction **bypass · accounting mismatch** (U > C, K ≤ C, as B8), reached through an **unbounded replay
volume** (OC-59: nothing ties the replay volume to the replaying JVM). Technique note:
[`bypass-playbook.md`](../../../bypass-playbook.md) (protected path vs suspect path, U measured apart from K).

1. *Writer.* At runtime the memtable pool (`memtable_heap_space` default = heap/4,
   `config/DatabaseDescriptor.java:586-587`) and flushing at the cleanup threshold 1/(1 + 2 flush writers)
   decide what is unflushed at a crash; flushed segments are discarded. A writer at heap_w = 8 GiB
   (pool 2,048 MiB) killed with a full pool leaves ≈ 2 GiB of memtable charge ≈ 2,400 P64 mutations
   (≈ 150 MiB serialized) after the global replay position.
2. *Replayer.* On restart at heap_r (1 GiB: pool 256 MiB), `CommitLogReplayer.construct` computes the global
   replay position from the sstables' persisted intervals (`CommitLogReplayer.java:154`, `:184`,
   `firstNotCovered` `:376`); every entry after it is deserialized by `main`
   (`CommitLogReader.readMutation`, into `ArrayCell`s plus the N3 cached copy) and queued; nothing scales
   with heap_r except the pool.
3. *Stall.* The data disk becomes slow (dm-delay, 30 s per write I/O) when replay starts. Replay-time flushes
   cannot complete their `fsync`, so the 256 MiB pool fills; all 32 `MutationStage` appliers park in
   `MemtableAllocator.SubAllocator.allocate` (`utils/memory/MemtableAllocator.java:169-195`); covered entries
   cannot be skipped either, because their tasks also wait for a free applier.
4. *Bound.* The reader keeps deserializing until `futures.size() > 1024` (`CommitLogReplayer.java:525`): the
   count binds at ≈ 1,024 P64 mutations = 63.7 MiB serialized (just under the 64 MiB byte bound), which hold
   ≈ 0.95 GiB of heap (B8 ledger). Pool 256 MiB + queue ≈ 950 MiB + baseline ≈ 120 MiB ≈ 1.33 GiB > 1 GiB →
   **Java heap OOM during start-up**, on a node that is not otherwise loaded.
5. *Why the smaller heap is necessary.* A same-heap restart offers ≤ ≈ one pool (B8 A); at 1 GiB that is
   ≈ 300 P64 mutations, so with the same stall the queue holds ≤ ≈ 300 × 0.93 MiB beside a ≤ 256 MiB pool:
   no OOM is predicted. The heap change alone (no stall) is not enough either (B8 X: replay is reader-bound).

### 2.2 Protection map

| Domain | Holder (allocation → release) | Counter K | Limit C (contract) | At the limit | Scope / multiplicity |
|---|---|---|---|---|---|
| D1 replay queue (claimed) | `CommitLogReader.readMutation` deserializes each entry on `main` (`ArrayCell`, `CellPath`, `HeapByteBuffer`, `byte[]` incl. N3 copy) → released when its `MUTATION`-stage task completes and the future is polled | `pendingMutationBytes` (serialized bytes) and `futures.size()` | 64 MiB serialized / 1,024 futures (`CassandraRelevantProperties.java:114-115`); contract: "bytes" of outstanding replay | reader blocks on the oldest future (`:525-529`) | one per process (one reader thread); covered entries included |
| D2 memtable pool | `Memtable` cells (`BufferCell` etc.) allocated by appliers → released when the flush of that memtable completes | pool `allocated` (on-heap charge) | heap_r/4 (256 MiB at 1 GiB), flush at 1/3 | appliers block in `SubAllocator.allocate` until a flush frees | per process |
| D3 replay volume (OC-59) | entries after the global replay position | none | none tied to the replayer; implicitly the writer's pool heap_w/4 (and `commitlog_total_space`) | — | per restart |
| D4 baseline | schema, sstable readers, caches, buffers | — | key cache etc. at defaults (small) | — | per process |

Budget: the replayer's Java heap (`-Xmx` = heap_r). Direct memory (resolved 7,936 MiB from RAM) is not
involved. A per-run cgroup scope (MemoryMax = heap + 4,096 MiB, swap 0) is an **isolation guard only, not a
budget**: a guard kill (`memory.events` `oom_kill` > 0 without a Java `OutOfMemoryError`) makes the arm
invalid.

### 2.3 Configuration and budget audit

- **Build:** `/mydata/s4/b12-w2/cassandra-base` (5.0.9-SNAPSHOT jar built from the repo source) copied to
  `/mydata/b15/cassandra` (B12's tree is not modified). Before use: `conf/` compared with the repo's
  `systems/cassandra/source/conf/` (only `hotspot_compiler` may differ; copy any other differing file from the
  repo over it and record it). No patches, no Byteman in any arm.
- **Node:** `ms0611` (Utah m400, **aarch64** X-Gene, 8 cores, 62 GiB RAM, 8 GiB swap present, Ubuntu 22.04,
  kernel 5.15, cgroup v2, JDK 11.0.33, passwordless sudo; `/mydata` 23 GiB free at design time; idle, no
  Java process, 2026-11-18 08:00 EST). `dm-delay` module available (`modprobe -n dm-delay` OK).
- **Constraints, all shipped defaults (V6), resolved per JVM:**

| Setting | Default | Writer (8 GiB) | Replayer (1 GiB / 1.5 GiB / 2 GiB) |
|---|---|---|---|
| `cassandra.commitlog_max_outstanding_replay_count` / `_bytes` | 1,024 / 64 MiB | — | 1,024 / 64 MiB (intervention arm only: count 64) |
| `memtable_heap_space` | heap/4 | 2,048 MiB | 256 / 384 / 512 MiB |
| `memtable_allocation_type` | `heap_buffers` | same | same |
| `memtable_flush_writers` / cleanup threshold | 2 / 1/3 | same | same |
| `concurrent_writes` | 32 | same | same |
| `commitlog_segment_size` / `commitlog_sync` | 32 MiB / periodic 10 s | same | same |
| `commitlog_disk_access_mode` | `legacy` | same | same |
| `commitlog_total_space` | min(8,192 MiB, ¼ of the commit-log volume) | ≈ 3,000 MiB on the 12 GiB data volume (record the logged value) | same |
| `max_mutation_size` | ½ segment = 16 MiB | P64 = 64 KiB, far below | — |
| `num_tokens`, auth | 16, AllowAll | same | same |
| heap / MaxDirectMemorySize | env: min(½ RAM, 15,872 MiB) / RAM/4 or 7,936 MiB | `MAX_HEAP_SIZE=8192M` (resolution for a 16 GiB node); direct 7,936 MiB as resolved here | `MAX_HEAP_SIZE=1024M` (resolution for a 2 GiB node; search 1,536 / 2,048); direct 7,936 MiB |

- **Budget (V7):** heap_r 1 GiB is ≥ 512 MiB (standing rule; no per-case review needed); the upward search goes to
  2 GiB (ideal). The node size the result claims to represent: a node whose own resolution is heap_r
  (2–4 GiB RAM) receiving the data directory of a node with ≥ 16 GiB RAM, or the same node after its RAM/
  container was reduced — the heap is left to `cassandra-env.sh`'s formula, i.e. no hand-tightening beyond
  what the smaller node resolves. **For the researcher's review (labels, not readiness):** (a) the heap change
  between writer and replayer is a deployment event (restore / downsizing), (b) the storage stall
  (30 s write latency for 120 s from the start of replay) follows B6 condition A's accepted external fault.
- **Environment deviations (disclosed):** data, commit log, hints and saved caches live on a dm-delay device
  over a 12 GiB sparse loop file on `/mydata` (needed for the external fault; read delay 0 always, write delay
  0 except in the stall window); logs, GC logs and heap dumps on `/mydata` proper; client on the same node;
  single node, RF 1; cgroup guard as in 2.2.

### 2.4 Ceiling arithmetic

At heap_r = 1 GiB by contract: D1 64 MiB + D2 256 MiB + baseline ≈ 150 MiB = **≈ 470 MiB < 1,024 MiB** → by the
contracts no OOM is possible. Physical prediction with the B8 ledger: D1 ≈ 1,024 × 0.93 MiB = **952 MiB**
(U/K ≈ 15) + D2 256 MiB + baseline ≈ 120 MiB ≈ **1,330 MiB** → OOM at 1 GiB; at 1.5 GiB: 952 + 384 + 120 ≈
1,456 MiB (95 %, borderline: OOM or GC service loss); at 2 GiB: 952 + 512 + 120 ≈ 1,584 MiB (77 %; B8 S at 2 GiB
started at 70 %) → start predicted. Required replay volume for the queue to fill at 1 GiB: pool 256 MiB +
1,024 queued ≈ 1,100 MiB of memtable charge ≈ 1,330 P64 mutations; the writer at 8 GiB leaves ≈ 2,400. A
writer at 1 GiB leaves ≤ ≈ 300 (control).

### 2.5 Workload and environment

Work dir `/mydata/b15` on `ms0611` only (`harness/`, `cassandra/`, `vol/`, `img/`, `runs/`). Never touch
`/mydata/s4/b11-w1`, `/mydata/s4/b12-w2`, `/mydata/s2r2`, `/mydata/u1r2`.

**Setup (S0):**
1. `cp -a /mydata/s4/b12-w2/cassandra-base /mydata/b15/cassandra`; remove its `logs/`, `data/` (if any);
   conf check as 2.3; record `sha256sum build/apache-cassandra-5.0.9-SNAPSHOT.jar`.
2. Harness under this case's `harness/`, synced to `/mydata/b15/harness/`: copy from B8's `harness/`
   `B8Load.java`, `load.sh`, `logback-load.xml`, `gcsum.py`, `hprofhist.py`, `summ.py` (paths `/mydata/b8` →
   `/mydata/b15`; keyspace/table names `b8.t_map` kept); compile with `load.sh --compile`; copy S2's
   `convergence/coordinator-local-write-backlog--combo/harness/slowdisk.sh` as `slowdisk.sh` with name
   `b15slow`, image `/mydata/b15/slowdisk.img` **12G** (sparse), mount point `/mydata/b15/vol`, mount option
   `-o discard`; `slowdisk.sh setup`, then `ln -s /mydata/b15/vol/data /mydata/b15/cassandra/data`
   (`mkdir -p /mydata/b15/vol/data`). Check `set 30000` / `set 0` once with a timed `dd … conv=fsync` of 4 MiB
   on the volume (expect ≥ 30 s, then < 1 s); restore 0.
3. Two scripts (new; B8's `arm3.sh` is the model — reuse its `start_node` with `systemd-run --user --scope
   -p MemoryMax=$((HEAP+4096))M -p MemorySwapMax=0`, `CASSANDRA_HEAPDUMP_DIR`, `JVM_EXTRA_OPTS`, the
   `memory.current` sampler, `stop_node`, the outcome loop and the closing log lines). Both abort if any
   `CassandraDaemon` runs, never `rm` the `data` symlink (only its contents), and leave nothing running.
   - **`mkimg.sh <img> <heapMiB>`** — writer phase. Empty `vol/data/*`; start the node at `<heapMiB>`;
     `load.sh schema`; `load.sh run map 5900 64 400 0 127.0.0.1` (P64, 64 in flight, no rate cap). Every 5 s
     log t, `nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=Table,keyspace=b8,scope=t_map,name=AllMemtablesHeapSize' -f Value`
     (on-heap charge of all memtables of the table, flushing ones included), `nodetool tpstats`
     (`MemtableFlushWriter`, `MutationStage`), commit-log MiB. **Kill rule:** `kill -9` the daemon at the
     first sample with t ≥ 60 s and AllMemtablesHeapSize ≥ 0.75 × heap/4 (8 GiB writer: ≥ 1,536 MiB; 1 GiB
     writer: ≥ 192 MiB), or at t = 270 s (cap); log the value at the kill. If `sjk` fails on the first
     image, fall back to `tablestats` "Memtable data size" plus `MemtableFlushWriter` Active, and record the
     fallback as an amendment. Then stop the client, `cp -a --sparse=always vol/data img/<img>`, keep the
     load-phase `system.log`, `gc.log`, client log and stats in `runs/mk-<img>/`.
   - **`replay.sh <run> <img> <heapMiB> <fault 0|1> [JVM opts]`** — replayer phase. `slowdisk.sh set 0`;
     empty `vol/data/*`; `cp -a img/<img>/. vol/data/`; `sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'`;
     start the node at `<heapMiB>`. Poll `system.log` each second for `CommitLog.java:206 - Replaying` (T_r).
     If fault = 1: `slowdisk.sh set 30000` at T_r; `slowdisk.sh set 0` at T_r + 120 s or as soon as the JVM
     is gone, whichever is first (also in an `EXIT` trap). At T_r + 12 s and T_r + 30 s: `jcmd <pid>
     Thread.print`; at T_r + 15 s and T_r + 45 s: `jcmd <pid> GC.class_histogram` (every arm, same times).
     Outcome: `started` (`Starting listening for CQL clients`), `died` (with `java.lang.OutOfMemoryError` in
     `stdout.txt` → heap OOM; guard kill per 2.2 → invalid), or `timeout` at 600 s after JVM start. Then
     `stop_node`, copy logs, `gcsum.py`, `summ.py` (replayed mutations, b8 flush charge during replay),
     `memory.events`. Dumps: run `hprofhist.py` on the **first** OOM dump and keep that dump only if
     `/mydata` keeps ≥ 8 GiB free; delete every other dump unread (their histogram at +15 s stands in).
4. Stop rule for disk: no new arm when `/mydata` has < 5 GiB free; delete used `K` images first.

**Arms** (P64 payload everywhere; writer images L = 8 GiB writer, K = 1 GiB writer):

| Run | Image | heap_r | Fault | Replay opts | Role |
|---|---|---|---|---|---|
| mk-L1, mk-L2, mk-L3 | — | (writer 8,192) | — | — | three independent crash images from an 8 GiB writer |
| mk-K1, mk-K2, mk-K3 | — | (writer 1,024) | — | — | three crash images from a 1 GiB writer |
| N1 (N2, N3 optional) | L1 (L2, L3) | 1,024 | no | — | heap change alone (OC-59 as stated); measures the L tail |
| T1, T2, T3 | L1, L2, L3 | 1,024 | yes | — | **test** |
| C1, C2, C3 | K1, K2, K3 | 1,024 | yes | — | **matched control** (same budget, fault, payload, build; same-heap tail) |
| I1, I2, I3 | L1, L2, L3 | 1,024 | yes | `-Dcassandra.commitlog_max_outstanding_replay_count=64` | **intervention** (bound the queue by count) |
| U1… | L1, then L2, L3 | 1,536 → 2,048 or 1,280 | yes | — | upward budget search (2.7) |

**Order** (one arm at a time): S0 → mk-L1 → N1 → T1 → mk-K1 → C1 → I1 → mk-L2 → T2 → mk-K2 → C2 → I2 →
mk-L3 → T3 → mk-K3 → C3 → I3 → U-search → N2, N3 if time. Launch each script detached
(`( setsid nohup bash … < /dev/null > … 2>&1 & )`) and wait with bounded background polls.

**Validity gates** (decided from the arm's own logs before it counts):
- G1 (load reached): the L image's tail is ≥ 1,450 replayed P64 mutations (≈ 1.2 GiB charge), read from N1 or
  from the same image's I arm (`Log replay complete, N replayed mutations`), and the kill-time
  AllMemtablesHeapSize is logged. A T arm on an image failing G1 is `invalid (load not reached)`; remake the
  image once with the cap raised to 400 s (dated amendment).
- G2 (fault engaged): in every fault arm the T_r + 30 s thread dump shows at least one `MemtableFlushWriter`
  thread in `FileChannel.force` / `fsync` (or blocked in the flush) **and** `MutationStage` threads parked
  in `MemtableAllocator$SubAllocator.allocate`; otherwise the arm is `invalid (fault not engaged)`.
- G3 (control tail): C arms' tails ≤ 450 replayed mutations; otherwise the control is not the same-heap
  shape and is reported as such.

### 2.6 Instruments

- **U (D1, independent of K):** class histograms at T_r + 15 / + 45 s and the OOM dump: replay-deserialized
  `ArrayCell` + `SingleItemCellPath`/`CellPath` + `HeapByteBuffer` + `byte[]` (as B8 §3.4), with
  `org.apache.cassandra.db.Mutation` instance count; D2 from `BufferCell` (memtable cells) and the pool's
  flush lines. **K:** live `Mutation` count × 63.7 KiB (serialized size of one P64 entry, B6/B8 calibration)
  and the count against 1,024.
- **Heap:** GC log (`gcsum.py`: Full GCs, max live after Full GC, worst-60 s STW share); `memory.current` each
  second (guard only).
- **Tail / volume:** `summ.py` (replayed count, flush charge during replay); writer-side AllMemtablesHeapSize
  at kill; commit-log size at kill.
- **Fault:** `dmsetup table b15slow` before/after each switch logged with timestamps; thread dumps (G2).
- **Throughput for the intervention:** start-up duration and replayed count (I replays everything, rejects
  nothing).
- Endpoint evidence (V5): first `java.lang.OutOfMemoryError` line with thread (stdout / `system.log`), the
  dump histogram (T1), the T_r + 12 / 30 s thread dumps.

### 2.7 Predicted response, stopping budget, search

| Arm | Predicted outcome | Predicted readings |
|---|---|---|
| N (L, 1 GiB, no fault) | started, ≤ 90 s after JVM start | 0–1 Full GC in replay; live `Mutation`s ≤ 20 at +15 s; tail 1,450–2,600 mutations (1.2–2.2 GiB charge) |
| T (L, 1 GiB, fault) | **heap OOM in replay 3/3**, within ≈ 20–120 s of T_r | histogram before death: ≈ 1,000–1,030 live `Mutation`s (K ≈ 62–64 MiB) and U ≈ 0.85–0.95 GiB, D2 ≈ 256 MiB; GC live after Full GC → ≥ 95 % before the error |
| C (K, 1 GiB, fault) | started 3/3 (after the stall clears) | tail ≤ 450; live `Mutation`s ≤ 450 at +15 s; max live after Full GC ≤ 75 % |
| I (L, 1 GiB, fault, count 64) | started 3/3, slower (≈ 3–5 min) | live `Mutation`s ≤ 65; U ≤ 70 MiB; every mutation replayed |
| U 1,536 | OOM or GC service loss (borderline) | — |
| U 2,048 | started (≈ 77 % live) | — |

**Upward search** (after the triples): T at 1,536 MiB on L1. If it OOMs → T at 2,048 on L2; if 2,048 also OOMs →
2,048 again on L3 (n/N reported). If 1,536 starts → T at 1,280 on L2. The largest failing heap is reported with
its n/N; a heap where replay starts is the boundary, not a negative for the case.

**Stopping budget:** each replay arm ≤ 600 s from JVM start (then stop the JVM and record `timeout` with the
GC service-loss criterion: ≥ 90 % STW over ≥ 60 s); each image ≤ 270 s of load (400 s after a G1 amendment);
no escalation after an OOM (no larger loads, no other payloads). **Time plan (America/New_York,
2026-11-18):** stage 2 is assumed to start by ≈ 08:45. S0 ≈ 20 min (→ 09:05); per triple ≈ 25 min (mk-L ≈ 6,
T ≈ 3, mk-K ≈ 4, C ≈ 5, I ≈ 5, N1 2 in the first) → 09:05–10:20 for all three; U-search ≈ 10 min. **No arm
starts after 10:20**; all processes stopped, `slowdisk.sh set 0`, the dm device removed (`slowdisk.sh
teardown`, which also removes the loop file), images deleted, by **10:35**; §3/§4 and write-back by **10:55**.
If behind schedule, drop in this order: N2/N3, U-search beyond 1,536, U-search entirely; then reuse images
(C2/C3 on K1, T/I on L1–L2) and record the reuse — never drop the T/C/I triples' third run silently (report
n/N as run).

### 2.8 Controls and intervention

- **Matched control (V2), ≥ 3 runs:** C1–C3 — same build, budget (1 GiB), fault, payload and harness; only the
  writer's heap differs (1 GiB = heap_r), so the replay volume is ≤ one replay pool. Predicted to start: shows
  that the offered volume (OC-59) is what lets the queue fill. N1 is the second contrast (heap change without
  a stall; expected to start, per B8 X).
- **Causal intervention (V4), ≥ 3 runs:** I1–I3 — the test condition with
  `-Dcassandra.commitlog_max_outstanding_replay_count=64` (a non-default constraint in the intervention arm
  only, allowed by V6): the queue holds ≤ 64 mutations ≈ 60 MiB, so the endpoint should disappear while every
  mutation is still replayed (record start-up time). This attributes the OOM to the queued replay mutations
  admitted by the 1,024 / 64 MiB bound (B8 used the same intervention).
- **Classification to record:** per 2.2 — D1 U vs C (64 MiB) and K; D2 at its cap; D3 volume vs heap_r. If T
  OOMs with D1 at its count bound and U ≫ C while K ≤ C: bypass · accounting mismatch, with OC-59 as the reach
  condition. The conditions label is proposed as `deployment` only if the researcher accepts 2.3 (a) and (b);
  otherwise `diagnostic` (no other supporting deviation is planned).

`sha256 of §1–§2 at freeze: be36c76ae1c0f08c5b084a4bd8f5be094e920b49668797096d16e095ab3355d6` (bytes from the line `## 1. Candidate` up to, not including, this line; check: `awk '/^## 1\. Candidate/{p=1} /^.sha256 of §1–§2 at freeze/{p=0} p' <file> | sha256sum`) · frozen 2026-11-18 by stage 1 · amendments after the freeze: dated, with reason.

## 3. Runs (stage 2)

Freeze hash checked before any run (2026-11-18 08:09 EST): `be36c76a…3355d6`, matches §2's last line.

### 3.1 Environment and configuration as run

- **Node** `ms0611` (`node3`, Utah m400): **aarch64**, 8 cores, 62.7 GiB RAM, 8 GiB swap partition present (every
  measured JVM in a `systemd-run --user --scope -p MemoryMax=<heap+4096>M -p MemorySwapMax=0` guard scope), Ubuntu
  22.04.1, kernel **5.15.0-191-generic**, cgroup v2, OpenJDK **11.0.33**, G1 (the shipped `jvm11-server.options`).
  Idle before the first arm (`pgrep -af CassandraDaemon`: nothing; no loop or dm device of other cases). One arm at
  a time; client (`B8Load`) on the same node during writer phases only.
- **Build:** `/mydata/s4/b12-w2/cassandra-base` copied to `/mydata/s4/b15-w3/cassandra` (B12's tree untouched); jar
  `apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `e2147f53ac015e9a8ce05a5f057aa7ea85a0f7ca3baea09365539341701e8c37`;
  `conf/` compared file by file (sha256) with the repo's `systems/cassandra/source/conf/`: identical except the
  build-generated `hotspot_compiler`. No patches, no Byteman, no config edits in any arm.
- **Resolved values (logged):** `commitlog_total_space` **2,997 MiB** ("Small commitlog volume detected", the 12 GiB
  volume); `-XX:MaxDirectMemorySize=15872M` as resolved by the shipped `cassandra-env.sh` on this 62 GiB node (the
  design expected 7,936 MiB; direct memory is not the budget here and is not involved); `-Xms=-Xmx` = 8,192 M
  (writers L), 1,024 M (writers K, replayers T/C/I/N), 1,280 / 1,536 M (U); `memtable_heap_space` = heap/4 (pool
  256 MiB at 1 GiB: flushes enqueued at "85.4 MiB (33 %)"), `concurrent_writes` 32 (32 `MutationStage` threads seen),
  2 flush writers, replay count/bytes 1,024 / 64 MiB except in the I arms (count 64).
- **Storage:** data, commit log, hints, saved caches on `/dev/mapper/b15slow` (dm-delay over a 12 GiB sparse loop
  file, ext4 `-o discard`, mounted at `/mydata/s4/b15-w3/vol`; `cassandra/data` → `vol/data`). Check: a 4 MiB
  `dd … conv=fsync` took **154.9 s** at write delay 30,000 ms (≥ 30 s as required; several sequential delayed
  I/Os) and **0.068 s** at 0 ms. Logs, GC logs, dumps on `/mydata` proper.
- **Harness:** [`harness/`](harness/) (synced to `/mydata/s4/b15-w3/harness/`): B8's `B8Load.java`, `load.sh`,
  `logback-load.xml`, `gcsum.py`, `hprofhist.py`, `summ.py`; S2's `slowdisk.sh` (renamed); new `common.sh`
  (B8 `arm3.sh`'s `start_node`/`stop_node`/sampler), `mkimg.sh`, `replay.sh`, `series.sh` (the §2.5 order with the
  10:20 cut-off and the 5 GiB disk stop). Full logs: `/mydata/s4/b15-w3/runs/<arm>/` on `ms0611`.

### 3.2 Amendments and deviations (dated; none changes a constraint, the budget, the payload or the fault)

- **A1 (2026-11-18 08:13 EST, before any run) — paths.** The stage-2 task fixed the work directory as
  `/mydata/s4/b15-w3` (design: `/mydata/b15`); dm name `b15slow`, image `/mydata/s4/b15-w3/slowdisk.img`, mount
  `/mydata/s4/b15-w3/vol`. `slowdisk.sh teardown` detaches only its own loop device (S2's fallback `losetup -D`
  would detach every loop on the node). Paths only.
- **A2 (2026-11-18 08:30 EST, after T1, before mk-K1) — later thread dumps.** T1's T_r + 30 s dump was taken 1 s
  after the first replay flush was enqueued: with the larger L log the reader spent ≈ 30 s in entries already
  covered by sstables (only 5 `MutationStage` threads existed, none parked in the allocator), so G2 could not be
  read at + 30 s. Added `jcmd Thread.print` at T_r + 60 s and + 90 s in every later arm (the + 12 / + 30 s dumps
  and the + 15 / + 45 s histograms unchanged). G2 is read on the + 30 s dump where it shows the stall, otherwise on
  the first later dump taken while the JVM was alive. T1 itself stays **invalid (fault not engaged at + 30 s by
  the letter of G2)**.
- **A3 (2026-11-18 09:38 EST, after the series) — T1 replacement.** `T1r` = T1 repeated on image L1 (same
  script, same settings) so that the test has three runs that pass every gate; started 09:38, before the 10:20
  cut-off.
- **Deviation D1 — writer sample cadence and kill time.** Each 5 s sample ran three `nodetool` JVMs on a loaded
  8-core aarch64 node and took ≈ 40–50 s, so samples came every ≈ 45 s. The kill rule's threshold
  (AllMemtablesHeapSize ≥ 0.75 × heap/4) was **never reached** by any writer (8 GiB writers: 552–671 MiB, i.e.
  ≈ one cleanup threshold of the 2 GiB pool; 1 GiB writers: 0–59 MiB), so every image was killed by the time
  cap, at the first sample at or after 270 s: t = 310–346 s. The tail is set by what is unflushed and not
  covered by sstables, which N1/I arms measured directly (G1 below), not by the kill-time sample.
- **Deviation D2 — instrument intrusiveness.** `GC.class_histogram` forces a Full GC ("Heap Inspection Initiated
  GC") at + 15 / + 45 s in every arm (as designed and as in B8); in T1/T2 the + 45 s histogram failed (attach
  EOF while the JVM was in back-to-back Full GCs), in T1r it returned the rows but no total line.
- **Not run / changed:** nothing else. The U-search took the "1,536 starts → 1,280 on L2" branch. Dumps: only
  T1's dump was kept (moved to `/mydata/s4/b15-w3/dumps-keep/T1.hprof`, histogram built off-node with
  `hprofhist.py`); the T2, T3, T1r, U1280 dumps were deleted unread, as designed.

### 3.3 Writer images

| Image | Writer heap | Kill (t) | AllMemtablesHeapSize at kill | Commit log at kill | Image | Replay tail measured (arm) |
|---|---|---|---|---|---|---|
| L1 | 8,192 M | 346 s (cap) | 643 MiB | 425 MiB, 15 files | 2,108 MiB | **2,351** mutations; t_map flush charge during replay **2,077 MiB** (25 flushes) (N1, I1, U1536) |
| L2 | 8,192 M | 319 s (cap) | 643 MiB | 361 MiB, 13 | 1,818 MiB | 2,350; 2,077 MiB (I2, N2) |
| L3 | 8,192 M | 337 s (cap) | 635 MiB | 358 MiB, 13 | 1,930 MiB | 2,350; 2,076 MiB (I3, N3) |
| K1 | 1,024 M | 310 s (cap) | 2 MiB | 441 MiB, 15 | 1,513 MiB | 513; **284 MiB** (3 flushes) (C1) |
| K2 | 1,024 M | 328 s (cap) | 46 MiB | 532 MiB, 18 | 1,593 MiB | 568; 284 MiB (C2) |
| K3 | 1,024 M | 328 s (cap) | 56 MiB | 428 MiB, 15 | 1,516 MiB | 564; 284 MiB (C3) |

The replayed b8 memtable charge is **≈ the writer's pool**: 2,077 MiB from an 8 GiB writer (pool 2,048 MiB) and
284 MiB from a 1 GiB writer (pool 256 MiB) — OC-59's claim, measured. "Replayed mutations" counts every
replayed partition update, including system tables (`sstable_activity`, `local`, `compaction_history`, …); the
1 GiB writers flushed ≈ 180 times, so ≈ 200–250 of C's 513–568 are system-table updates and ≈ 320 are P64
mutations (284 MiB / ≈ 0.88 MiB charge each).

**Gates.** **G1 met** for L1–L3 (2,350–2,351 ≥ 1,450 replayed; 2.08 GiB ≥ 1.2 GiB charge; kill-time value
logged). **G3 by its count: not met** (513–568 > 450); by charge the C tails are ≈ 1.1 replay pools (284 MiB vs
256 MiB), i.e. the same-heap shape, and the excess count is system-table updates — reported as such. **G2:** see
3.4.

Excerpts: [`logs/writer-images.txt`](logs/writer-images.txt) (arm logs and samples).

### 3.4 Replay arms (heap 1,024 M unless stated; fault = 30 s write delay from T_r to T_r + 120 s)

T_r came 17–18 s after JVM start in every arm. Outcome "died" = `java.lang.OutOfMemoryError: Java heap space` in
`stdout.txt`, heap dump, `-XX:OnOutOfMemoryError="kill -9 %p"`; cgroup `memory.events` `oom_kill 0` in every arm
(guard never fired; peak `memory.current` 2.2–4.2 GB, the T peaks include the dump being written).

| Run | Image | Fault / opts | Outcome | OOM ≈ (T_r +) | Live `Mutation`s / live heap at + 45 s | Max live after Full GC; worst-60 s STW | Replayed | G2 (dump) |
|---|---|---|---|---|---|---|---|---|
| N1 | L1 | none | started, 70 s | — | 1 / 183 MiB | 195 MiB; 7 % | 2,351 | n/a |
| N2 | L2 | none | started, 64 s | — | 0 / 58 MiB | 195 MiB; 7 % | 2,350 | n/a |
| N3 | L3 | none | started, 64 s | — | 0 / 40 MiB | 204 MiB; 7 % | 2,350 | n/a |
| **T1** | L1 | stall | **died**, 138 s | ≈ 85 s | (histogram failed) | 1,008 MiB; 45 % | — | **not met at + 30 s** (5 appliers, flush 1 s old) → **invalid** |
| **T2** | L2 | stall | **died**, 125 s | ≈ 59 s | (histogram failed) | 1,012 MiB; 51 % | — | met at + 30 s: 2 flush writers blocked in the flush I/O (`FileUtils.appendAndSync` → `open0`; `File.exists`), 32/32 `MutationStage` in `SubAllocator.allocate` |
| **T3** | L3 | stall | **died**, 162 s | ≈ 79 s | **741 / 1,010 MiB** | 1,009 MiB; 75 % | — | met at + 30 s (2 flush writers in the flush, 32/32 appliers parked) |
| **T1r** | L1 | stall | **died**, 138 s | ≈ 66 s | 773 / (no total) | 1,011 MiB; 56 % | — | met at + 30 s (2 flush writers, 32/32 appliers parked) |
| C1 | K1 | stall | started, 145 s | — | 31 / 343 MiB | 343 MiB; 2 % | 513 | met at + 60 / + 90 s (2 flush writers in `FileChannelImpl.force`, 31/31 appliers parked); + 30 s: reader still in covered entries |
| C2 | K2 | stall | started, 146 s | — | 1 / 48 MiB | 47 MiB; 1 % | 568 | met at + 60 / + 90 s (same) |
| C3 | K3 | stall | started, 145 s | — | 31 / 342 MiB | 342 MiB; 2 % | 564 | met at + 60 / + 90 s (same) |
| I1 | L1 | stall, count 64 | started, 161 s | — | 66 / 375 MiB | 374 MiB; 7 % | 2,351 | met at + 30 s (32/32 parked) and + 60 / + 90 s (2 in `force`) |
| I2 | L2 | stall, count 64 | started, 163 s | — | 97 / 375 MiB | 375 MiB; 7 % | 2,350 | met at + 30 s, + 60 s, + 90 s |
| I3 | L3 | stall, count 64 | started, 163 s | — | 97 / 375 MiB | 374 MiB; 7 % | 2,350 | met at + 30 s, + 60 s, + 90 s |
| U1536 | L1 | stall, heap 1,536 M | started, 162 s | — | **1,026** / 1,408 MiB (92 %) | 1,407 MiB; 16 % | 2,351 | met at + 60 s |
| U1280 | L2 | stall, heap 1,280 M | **died**, 138 s | ≈ 76 s | 943 / 1,263 MiB | 1,263 MiB; 32 % | — | met at + 30 s |

OOM times are the outcome time minus the logged heap-dump time (35–66 s); every OOM fell inside the stall window
(before T_r + 120 s). No T or U1280 arm logged `Log replay complete` or a completed `t_map` flush: each enqueued
two flushes at 85.4 MiB (33 %) at T_r + 30–32 s, and none finished. The thread dumps at + 30 s (T2, T3, T1r) show
`main` deserializing (`UnfilteredSerializer.readComplexColumn`, `AbstractType.read`) while all 32 appliers are
parked in `MemtableAllocator$SubAllocator.allocate`; in the C and I arms `main` is parked (it has read the whole
log and waits for the futures). Gate summary: **T valid 3/3 (T2, T3, T1r), all OOM; T1 invalid but also OOM;
C 3/3 valid by G2 (after A2), G3 by count not met; I 3/3 valid.**

Excerpts: [`logs/replay-arms.txt`](logs/replay-arms.txt), [`logs/thread-dumps-excerpt.txt`](logs/thread-dumps-excerpt.txt)
(T2 + 30 s, T1r + 30 s, C1 + 60 s, T1 + 30 s), [`logs/series.txt`](logs/series.txt).

### 3.5 Ledger — U (D1) measured apart from K

Exact live sizes from the + 45 s class histograms (`jcmd GC.class_histogram`, after its Full GC;
[`logs/T3-histogram-plus45s.txt`](logs/T3-histogram-plus45s.txt), [`logs/histograms-plus45s.txt`](logs/histograms-plus45s.txt)).
D1 objects are those deserialized by the reader: `ArrayCell` (only replay creates them), one `SingleItemCellPath`
and one 48 B `HeapByteBuffer` per `ArrayCell`, and the replay share of `byte[]` (total minus the memtable's ≈ 45 MiB
seen in C1 at a full pool, incl. the N3 copies). D2 = `BufferCell`s with their paths and two `HeapByteBuffer`s each.

| Run (+ 45 s) | Live `Mutation`s | K = n × 63.7 KiB | `ArrayCell` | D1 U (cells + paths + buffers + `byte[]`) | U/K | D2 (`BufferCell` …) | Total live / heap |
|---|---|---|---|---|---|---|---|
| T3 (OOM ≈ 34 s later) | 741 | **46.1 MiB** | 4.36 M, 166.5 MiB | 166.5 + 66.6 + 199.8 + ≈ 233 ≈ **666 MiB** | ≈ 14 | 1.65 M cells, ≈ 284 MiB | 1,010 / 1,024 MiB |
| U1536 (started) | 1,026 (count bound) | 63.8 MiB | 6.05 M, 230.7 MiB | 230.7 + 92.3 + 276.8 + ≈ 312 ≈ **912 MiB** | ≈ 14 | 2.44 M cells, ≈ 420 MiB | 1,408 / 1,536 MiB |
| U1280 (OOM ≈ 31 s later) | 943 | 58.7 MiB | 5.56 M, 211.9 MiB | ≈ 211.9 + 84.8 + 254.3 + ≈ 290 ≈ **841 MiB** | ≈ 14 | 2.05 M cells | 1,263 / 1,280 MiB |
| C1 (started) | 31 | 1.9 MiB | 0.18 M, 7.0 MiB | ≈ 30 MiB | — | 1.64 M cells (pool full) | 343 / 1,024 MiB |
| I1 (started) | 66 | 4.1 MiB | 0.38 M, 14.6 MiB | ≈ 50 MiB | — | 1.65 M cells (pool full) | 375 / 1,024 MiB |

T1's OOM dump (1,394 MiB, `hprofhist.py`, shallow sizes approximate): **770** `Mutation`s, 4.36 M `ArrayCell`, 6.0 M
`SingleItemCellPath`, 7.65 M `HeapByteBuffer`, 1.65 M `BufferCell` ([`logs/T1-oom-dump-histogram.txt`](logs/T1-oom-dump-histogram.txt)):
the same composition as T3 at + 45 s and as B8 `s-p64-1g-r1` (4.33 M `ArrayCell`). Per queued P64 mutation
U ≈ 0.89–0.90 MiB (B8: 0.93 MiB). The bound's counters stayed below their limits at 1 GiB (741–773 < 1,024
futures; 46–48 MiB < 64 MiB): the heap ran out **before the bound ever blocked the reader**. At 1,536 MiB the
count bound engaged (1,026 futures, K = 63.8 MiB) with U ≈ 0.9 GiB.

### 3.6 Upward budget search

| Heap | Image | Outcome | n/N |
|---|---|---|---|
| 1,024 M | L1, L2, L3 | heap OOM in replay | **3/3** (valid; T1 also OOM: 4/4) |
| 1,280 M | L2 | heap OOM in replay (≈ T_r + 76 s; 943 live `Mutation`s, 1,263 MiB live at + 45 s) | 1/1 |
| 1,536 M | L1 | started after the stall (queue at its 1,026 bound; 92 % live after Full GC, worst-60 s STW 16 %) | 0/1 |

Largest failing heap **1,280 MiB** (1/1); boundary between 1,280 and 1,536 MiB. 2 GiB not run (the 1,536 start
ended the search per §2.7).

### 3.7 Clean-up (2026-11-18 09:42 EST)

No `CassandraDaemon`, `B8Load`, harness script or `b15` scope left; write delay set to 0, `slowdisk.sh teardown`
(unmounted, `b15slow` removed, `/dev/loop0` detached, `slowdisk.img` deleted), `img/` deleted, `cassandra/data`
symlink removed. Left on `ms0611`: `/mydata/s4/b15-w3/` with `runs/` (109 MiB of logs, GC logs, histograms, thread
dumps), `dumps-keep/T1.hprof` (1.4 GiB; `/mydata` keeps 21 GiB free), `cassandra/` (471 MiB build copy),
`harness/`, `loadcls/`, `series.log`. `/mydata/s4/b11-w1`, `/mydata/s4/b12-w2`, `/mydata/s2r2`, `/mydata/u1r2`
not touched.

## 4. Conclusion (stage 2)

> **Owner review (2026-11-18): accepted.** The owner accepted both §2.3 assumptions: (a) a heap change between
> the writing and the replaying JVM is a deployment event, and (b) the dm-delay storage stall is an acceptable
> external fault. The verdict is final: **true positive**, `verified-OOM · deployment`.

**Verdict: true positive.** Protocol status **`verified-OOM · deployment`** as proposed in §2.8, **pending the
researcher's review** of §2.3 (a) the heap change between writer and replayer as a deployment event and (b) the
dm-delay storage stall as an external fault (B6 condition A precedent); if either is not accepted the label is
`verified-OOM · diagnostic` — the verdict is the same. Direction **bypass · accounting mismatch** (U > C, K ≤ C),
reached through OC-59's unbounded replay volume.

**Reason.** On `ms0611` (aarch64), with every capacity setting at its default and a 1 GiB replaying heap, a node
restarted from a commit log written at an 8 GiB heap while its data disk stalls (30 s per write for 120 s from the
start of replay) dies of `java.lang.OutOfMemoryError: Java heap space` during replay in **3/3** valid runs (T2, T3,
T1r; T1, invalid by gate G2's timing, also OOMed), 59–85 s after replay starts. The replayed volume is the
writer's pool (2,077 MiB of memtable charge, 2,350–2,351 mutations, measured without the stall in N1–N3 and in
I1–I3), against a 256 MiB replay pool. With flushes blocked, all 32 appliers park in the memtable allocator and
the reader keeps queueing deserialized mutations: at + 45 s T3 holds 741 live `Mutation`s, counted by the bound as
**K = 46 MiB (≤ C = 64 MiB, 741 < 1,024)** but holding **U ≈ 666 MiB** (≈ 14× K; 4.36 M `ArrayCell`s) next to
≈ 284 MiB of memtable, 1,010 of 1,024 MiB live. The matched control (same build, heap, fault, payload; log
written at 1 GiB so the replayed charge is ≈ one replay pool, 284 MiB) starts **3/3** with at most 31 queued
mutations and ≤ 343 MiB live; the intervention (`commitlog_max_outstanding_replay_count=64`) starts **3/3**
with ≤ 97 queued mutations and ≤ 375 MiB live and replays every mutation (2,350–2,351), rejecting nothing; start-up takes 161–163 s (C: 145–146 s, both
including the 120 s stall; no stall: 64–70 s). Without the stall the heap change alone starts 3/3 (N1–N3, 64–70 s).
The largest failing heap is **1,280 MiB** (1/1); at 1,536 MiB the count bound engages (1,026 futures, U ≈ 0.9 GiB)
and the node starts at 92 % live.

| | Evidence | Met |
|---|---|---|
| V1 Repetition | T2, T3, T1r: heap OOM in replay 3/3 (T1 4th, invalid by G2 timing, also OOM) | yes |
| V2 Matched control | C1–C3 started 3/3 (same build, 1 GiB, fault, payload); G2 met at + 60/90 s after A2; G3 by count not met (513–568 incl. system-table updates), by charge ≈ one pool (284 MiB) | yes (G3 caveat stated) |
| V3 Measurement | U from class histograms (+ 45 s, T1 OOM dump) by object type, independent of K (`Mutation` count × 63.7 KiB) | yes |
| V4 Intervention | I1–I3 (count 64) started 3/3, 66–97 queued, every mutation replayed | yes |
| V5 Initiating failure | `java.lang.OutOfMemoryError: Java heap space` + dump + `OnOutOfMemoryError` kill in each T arm; T1 dump histogram and T3 + 45 s histogram show the queued replay cells; + 30 s thread dumps show `main` deserializing and 32/32 appliers parked. The throwing thread is not printed (HotSpot's dump message names none; the kill follows at once) | yes (no thread name, as B8) |
| V6 Default constraints | replay count/bytes 1,024 / 64 MiB, `memtable_heap_space` heap/4 (256 MiB at 1 GiB), `concurrent_writes` 32, 2 flush writers, commit-log settings, `commitlog_total_space` 2,997 MiB resolved; only I arms change the count | yes |
| V7 Acceptable budget | 1 GiB heap ≥ 512 MiB (standing rule); largest failing 1,280 MiB; 1,536 MiB starts | yes |

**Limits of attribution.** One node type (aarch64 m400, slow reader); a faster reader would queue faster but the
appliers also run faster once the stall clears. The stall is 30 s per write for 120 s; a shorter stall can end
before the heap fills (U1536 survived because the stall lifted at T_r + 120 s with the queue at its bound). The
budget boundary (1,280 fails, 1,536 starts) is 1/1 per point. The D1 `byte[]` share is estimated (memtable share
taken from C1); the other D1 components are exact. The writer kill rule never fired on its threshold (D1); the
tails were measured directly, so this does not affect the comparison.
