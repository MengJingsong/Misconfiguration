# R23 — commitlog_max_outstanding_replay_bytes: a point-in-time restore from archived segments onto a slow data volume  <!-- file: cassandra/cases/commitlog_max_outstanding_replay_bytes--archive-restore-slow-disk-replay/commitlog_max_outstanding_replay_bytes--archive-restore-slow-disk-replay.md -->

| Field | Value |
|---|---|
| Case ID | `R23` (R = a new attempt at an earlier case; README "ID prefixes") |
| From | retry of `B8` (Cassandra phase-2 retry list row "B8 … added for a deployment-level OOM, owner 2026-11-23"; B8 came from the mechanism of `OC-5`) |
| Phase-1 case file | [`commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9, last source commit `afcc4348`; repo HEAD `8f76f239` at design time); on `pc91` the built tree `/mydata/s4/cassandra-base` (jar sha256 prefix `570b5249d9b9a43f`, the same on all five x86 nodes, checked 2026-11-24 05:47 EST) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5, workflow subagent), owner-approved batch of 2026-11-24, ≈ 05:30–06:15 America/New_York |
| Stage 2 (verify) | pending (a fresh agent session) |
| Verdict | `pending` |

IDs used here: **R23** = this case; **B8** = bypass case 8 (same replay bound; `verified-OOM · diagnostic` with restore
emulation by deleting sstables (X) and a Byteman flush stall (S)); **B15** = bypass case 15 (same bound; `verified-OOM ·
deployment` by a heap change between writer and replayer plus a 30 s × 120 s dm-delay stall timed to replay start);
**B6** / **S2** = earlier cases whose dm-delay storage fault the researcher accepted as an external fault; **OC-5** /
**OC-59** = rows of the phase-1 OOM candidate list; **N3** = the cached serialized copy each deserialized mutation
keeps (`Mutation.java:493`); **P64** = the B8 payload, one `map<int,int>` of 5,900 entries (63.7 KiB serialized);
**PIT** = `restore_point_in_time`.

## Summary

- **Conclusion:** pending (stage 2).
- **Root cause:** pending (stage 2). Hypothesis: the replay queue's bound (1,024 mutations / 64 MiB) counts serialized
  bytes, so for tiny-cell mutations it admits ≈ 0.9 MiB of heap per counted 63.7 KiB (≈ 14–15×, B8 / B15 ledgers).
  A documented point-in-time restore replays every archived segment written after the restored snapshot — many
  memtable pools' worth on a node of the **same** heap — and when the data volume is slow, the appliers park on a
  full memtable pool while the single reader keeps deserializing, so the queue's held heap exceeds a 1 GiB heap before
  the bound blocks the reader.
- **Claim under test:** the B8 endpoint (heap OOM in commit-log replay) is reached **without** B8's two diagnostic aids
  and **without** B15's heap change: the large replay volume comes from the shipped commit-log archiving feature
  (`conf/commitlog_archiving.properties`, snapshot + archived segments + `restore_point_in_time`), the apply stall
  comes from a data volume that is slow for the whole restart (constant write latency, not a stall timed to replay),
  writer and restored node run the same heap, and every capacity constraint stays at its shipped default.

## 1. Candidate

**Retry row (quoted from [`../../phase2-retry-list.md`](../../phase2-retry-list.md), Status `open` when the batch of 2026-11-24 started; the
coordinator set it to `picked again: R23`):**

> | [B8](cases/bypass/commitlog_max_outstanding_replay_bytes-accounting-mismatch/commitlog_max_outstanding_replay_bytes--accounting-mismatch.md) (true positive; added for a deployment-level OOM, owner 2026-11-23) | 2026-11-17 | Verdict stays **true positive** (`verified-OOM · diagnostic`): heap OOM in commit-log replay 3/3 at 1 GiB, queue at its bound holds 15× its serialized-byte count (947 vs 63 MiB). But the OOM needed two diagnostic aids: the table's sstables removed before restart (restore emulation, X) and a Byteman 10 s stall on every flush (S). Plain defaults (A) were `negative · deployment` 0/10. Stage 3: `known-fixed (incomplete)` (CASSANDRA-8639's bound counts serialized bytes) | Reach the replay OOM at **deployment** level, without removing sstables or injecting stalls: a real point-in-time restore from a commit-log archive (`commitlog_archiving.properties` restore of archived segments) so a large log replays legitimately; a genuinely slow data disk (throttled block device or slow volume, not Byteman) so flushes lag replay; dense tiny-cell mutations as in S; heap search from 1 GiB up | open |

**Phase-1 case.** Constraint `commitlog_max_outstanding_replay_bytes` (JVM property
`cassandra.commitlog_max_outstanding_replay_bytes`, default 64 MiB, with `cassandra.commitlog_max_outstanding_replay_count`,
default 1,024; `config/CassandraRelevantProperties.java:114-115`). Check: `CommitLogReplayer.handleMutation`
(`db/commitlog/CommitLogReplayer.java:513-531`) adds the entry's **serialized** size to `pendingMutationBytes`
(`:517`), submits the apply task to `Stage.MUTATION` (`:518`, `:331`), and the reader (`main`) waits for the oldest
future while `futures.size() > 1024` or `pendingMutationBytes > 64 MiB` (`:525-529`). Stage-3 estimate `positive`.
**Stage 4** ([result](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md),
2026-11-11): true positive, caps; backlog heap ≈ 2 × the byte limit for 60 KB blobs; built with custom settings
(3 GiB load pool, `concurrent_writes: 1`, cleanup threshold 0.99).

**What the earlier cases established (aarch64 m400, P64 payload):**

| Case | Replay volume came from | Apply stall came from | Heap writer → replayer | Result |
|---|---|---|---|---|
| B8 A | crash tail (≈ one pool) | none | same | started 10/10 (`negative · deployment`) |
| B8 X | sstables deleted (≈ 6 pools) | none | same | started 4/4: reader-bound at ≈ 125–170 P64/s, flushes (≈ 1.2 s each) keep up |
| B8 S | sstables deleted | Byteman 10 s per flush | 1 → 1 GiB | heap OOM 3/3; blob 0/3; count 64 0/3 (`verified-OOM · diagnostic`) |
| B15 | writer pool (8 GiB writer: 2,077 MiB of charge) | dm-delay 30 s per write, T_r → T_r + 120 s | 8 → 1 GiB | heap OOM 3/3 (741–773 queued `Mutation`s, U ≈ 0.67 GiB, K ≈ 46–48 MiB); 1,280 MiB OOM 1/1; 1,536 MiB started at 92 % live once the stall lifted (`verified-OOM · deployment`, owner 2026-11-18) |

R23 replaces B8's sstable deletion by a real archive restore, B8's Byteman stall and B15's timed 30 s stall by a
persistently slow data volume, and drops B15's heap change; it also moves to an **x86** node (B8's "Limits" left the
faster-reader case untested).

**JIRA prior art** (read only, 2026-11-24 ≈ 05:55 EST; nothing posted). Reused: B8's stage-3 file
[`../../stage3-jira-check/B8.md`](../../stage3-jira-check/B8.md) (11 queries on the replay bound; closest exact issue
CASSANDRA-8639) and B15 §1 (CASSANDRA-609, 885, 6087, 7533, 8639, 20084, 1967). New queries for the restore shape
(`project = CASSANDRA AND (…)`, REST API, ≥ 2 s apart):

| # | JQL | Hits |
|---|---|---|
| 1 | `text ~ "commitlog_archiving" AND (text ~ "OutOfMemoryError" OR text ~ "OOM" OR text ~ "heap")` | 18 |
| 2 | `text ~ "restore_point_in_time"` | 40 |
| 3 | `text ~ "point in time" AND text ~ "replay" AND (text ~ "OOM" OR text ~ "OutOfMemoryError" OR text ~ "heap")` | 35 |
| 4 | `text ~ "restore_directories"` | 55 |
| 5 | `text ~ "commitlog" AND text ~ "restore" AND text ~ "OutOfMemoryError"` | 3 |
| 6 | `text ~ "replay" AND text ~ "slow disk" AND (text ~ "OOM" OR text ~ "heap")` | 26 |

| Issue | What | Resolution | Relation |
|---|---|---|---|
| CASSANDRA-8639 | OOM on replay with dense mutations; proposed charging `unsharedHeapSize()` | Fixed 3.2 (committed form counts serialized bytes) | the under-count tested here (B8 stage 3: `known-fixed (incomplete)`) |
| CASSANDRA-6974 | replaying archived commit logs replayed only 2 mutations | Fixed 2.1 rc1 | restore correctness, no memory |
| CASSANDRA-9195 | PITR replay only replays every other time | Fixed 2.0.15 / 2.1.5 | restore correctness |
| CASSANDRA-19448 | `restore_point_in_time` granularity only seconds | Fixed 4.0.14 / 4.1.7 / 5.0.1 | the ms format used here; its "OutOfMemoryError" hit is an unrelated CI note |
| CASSANDRA-7232 | live (online) commit-log replay for PITR | Open | no memory content |

No issue reports an OOM during a point-in-time or archive restore, or that `restore_point_in_time` is applied in the
apply task (`CommitLogReplayer.java:296`) after the mutation was deserialized and queued. **Verdict: `new`** for the
restore shape; the underlying under-count is `known-fixed (incomplete)` (CASSANDRA-8639), so this case is not a
positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

Direction **bypass · accounting mismatch** (U > C, K ≤ C, as B8 / B15), reached through an **unprotected replay volume**
(nothing ties the volume a restore replays to the replaying JVM). Technique note:
[`bypass-playbook.md`](../../../bypass-playbook.md) (suspect path vs matched path, U measured apart from K).

1. *Archive.* With `archive_command` set, every commit-log segment is archived when the writer switches to the next
   segment (`AbstractCommitLogSegmentManager.java:327`), and a segment is discarded only after its archive command
   finished (`:406-413`), so the archive holds every write since archiving began, whatever was flushed.
2. *Restore (documented procedure).* The operator stops the node, puts the table's snapshot sstables back, sets
   `restore_command`, `restore_directories` and `restore_point_in_time` and starts the node. At start-up Cassandra
   archives the segments still in the commit-log directory (`CommitLog.java:184-190`, CASSANDRA-6904), copies every
   archived segment that is not already there into the commit-log directory (`CommitLogArchiver.maybeRestoreArchive`,
   `CommitLogArchiver.java:270-330`), and replays them all (`CommitLog.java:194-210`). The replay position of the table
   is its snapshot sstables' persisted interval (`CommitLogReplayer.java:154`, `:184`, `firstNotCovered` `:376`), so
   every write after the snapshot is deserialized and replayed: many memtable pools' worth on a node of the same heap.
3. *Point in time.* `pointInTimeExceeded` is checked inside the apply task (`CommitLogReplayer.java:296`, `:502-510`),
   not by the reader: mutations after the PIT are still deserialized and queued; their tasks return without applying.
4. *Slow data volume.* The restored node's data directory sits on a volume with a constant write latency of D* ms for
   the whole restart (§2.5); the commit log and the archive sit on a separate, fast disk (the placement
   `conf/cassandra.yaml:405-408` and `doc/…/operating/hardware.adoc:64-72` recommend). Replay-time flushes
   (`memtable_heap_space` = heap/4, flush at 1/3) then complete slower than the reader produces memtable charge; the
   pool fills and all 32 `MutationStage` appliers park in `MemtableAllocator$SubAllocator.allocate`
   (`utils/memory/MemtableAllocator.java:169-195`).
5. *Bound.* `main` keeps deserializing (`CommitLogReader.readMutation`, `ArrayCell`s plus the N3 copy) until
   `futures.size() > 1024` (`CommitLogReplayer.java:525`). 1,024 P64 mutations = 63.7 MiB counted but ≈ 0.9 GiB held
   (B8 ledger 0.93 MiB, B15 0.89–0.90 MiB per mutation). Pool 256 MiB + queue + baseline > 1 GiB → **Java heap OOM in
   start-up replay** (B15 at 1 GiB: at 741–773 queued mutations, before the bound blocked the reader).
6. *What is new against B8 / B15:* no sstable is deleted outside the documented restore, no injection, no heap change
   (writer and restored node both 1 GiB; budget-search arms restore onto a **larger** heap only), and the slow volume is
   a property of the restore target, not a stall switched on at replay start.

### 2.2 Protection map

| Domain | Holder (allocation → release) | Counter K | Limit C (contract) | At the limit | Scope / multiplicity |
|---|---|---|---|---|---|
| D1 replay queue (claimed) | `CommitLogReader.readMutation` on `main` (`ArrayCell`, `SingleItemCellPath`, `HeapByteBuffer`, `byte[]` incl. N3 copy) → released when its `MUTATION` task completes and the future is polled | `pendingMutationBytes` (serialized bytes), `futures.size()` | 64 MiB / 1,024 futures (`CassandraRelevantProperties.java:114-115`) | reader blocks on the oldest future (`CommitLogReplayer.java:525-529`) | one per process (one reader); includes covered and post-PIT entries |
| D2 memtable pool | memtable cells (`BufferCell` …) allocated by appliers → released when that memtable's flush completes | pool `allocated` (on-heap) | heap/4 (256 MiB at 1 GiB), flush at 1/3 | appliers block in `SubAllocator.allocate` | per process |
| D3 replay volume | archived + live segments after the snapshot's persisted position, up to the PIT | none | none tied to the replayer; set by the archive's span and the PIT | — | per restore |
| D4 restore copies | `restore_command` copies segments to the commit-log directory (disk, not heap) | — | — | — | not a memory domain; listed so it is not mistaken for one |
| D5 baseline | schema, sstable readers, key cache, buffers | — | key cache etc. at defaults (small) | — | per process |

Budget: the restored node's Java heap (`-Xmx`). Direct memory is not involved (record the value `cassandra-env.sh`
resolves on `pc91`). A per-run cgroup scope (`MemoryMax` = heap + 4,096 MiB, swap 0) is an **isolation guard, not a
budget**: a guard kill (`memory.events` `oom_kill` > 0 without a Java `OutOfMemoryError`) makes the arm invalid.

### 2.3 Configuration and budget audit

- **Build:** `pc91:/mydata/s4/cassandra-base` copied to `/mydata/s4/r23/cassandra` (the base is not modified). Before
  use compare its `conf/` file by file (sha256) with the repo's `systems/cassandra/source/conf/` (only the
  build-generated `hotspot_compiler` may differ; copy any other differing file from the repo and record it); record the
  jar's sha256. No patches, no Byteman, no `cassandra.yaml` edit in any arm.
- **Node:** `pc91` (Emulab UMass `node0.jason92-326665`): **x86_64**, Xeon E5-2667 v2 3.3 GHz, 32 hardware threads,
  125 GiB RAM, 8 GiB swap, Ubuntu 22.04, kernel 5.15.0-203, cgroup v2, OpenJDK 11.0.33, passwordless sudo; `/mydata`
  on a rotational PERC H710P RAID volume, 706 GiB free; `dm-delay` available (`modprobe -n` OK). State at design time
  (2026-11-24 05:47 EST): no `CassandraDaemon`, no loop or extra dm device, load 0.00; `/mydata/s4/NODE-LOCK/owner` reads
  `phase1-hadoop o9 Mon Nov 23 11:12:13 PM MST 2026` (a phase-1 run's lock from the night before; stage 2 checks that no
  process of it remains and follows the lock convention before starting). Nothing else under `/mydata/s4` is touched.
- **Constraints, all shipped defaults (V6), resolved per JVM:**

| Setting | Default | Writer (1,024 M) | Restored node (1,024 M; search 1,280–3,072 M) |
|---|---|---|---|
| `cassandra.commitlog_max_outstanding_replay_count` / `_bytes` | 1,024 / 64 MiB | — | 1,024 / 64 MiB (intervention arm only: count 64) |
| `memtable_heap_space` / `memtable_allocation_type` | heap/4 / `heap_buffers` | 256 MiB | 256 MiB (320 / 384 / 512 / 768 MiB in the search) |
| `memtable_flush_writers` / cleanup threshold | 2 / 1/3 (record the resolved values) | same | same |
| `concurrent_writes` | 32 | same | same |
| `commitlog_segment_size` / `commitlog_sync` / `commitlog_disk_access_mode` | 32 MiB / periodic 10 s / legacy | same | same |
| `commitlog_total_space` | min(8,192 MiB, ¼ of the commit-log volume) | 8,192 MiB expected (commit log on `/mydata`); record | same |
| `max_mutation_size` | ½ segment = 16 MiB | P64 64 KiB, far below | — |
| `num_tokens`, authenticator, memtable implementation | 16, AllowAll, shipped default | same | same |
| heap / `MaxDirectMemorySize` | env: min(½ RAM, 15,872 MiB) / resolved from RAM | `MAX_HEAP_SIZE=1024M`; direct as resolved (record) | `MAX_HEAP_SIZE` per arm; direct as resolved |

- **Non-capacity deployment choices (labelled; not constraints):**
  (a) **commit-log archiving and point-in-time restore**, the shipped feature, configured as its own documentation
  shows (`conf/commitlog_archiving.properties` comments; `doc/…/configuration/cass_cl_archive_file.adoc`): writer
  `archive_command=/bin/ln %path /mydata/s4/r23/archive/%name`; restored node additionally
  `restore_command=/bin/cp -f %from %to`, `restore_directories=/mydata/s4/r23/archive`,
  `restore_point_in_time=<PIT>` (millisecond format, GMT), `precision=MICROSECONDS` (default). The file is read from the
  classpath (`CommitLogArchiver.java:104`, `conf/` is on `CLASSPATH`). (b) **Directory placement:** commit log, hints,
  saved caches and the archive on `/mydata` (fast local disk); the data directory on the slow volume, by symlink
  (`cassandra/data/data → /mydata/s4/r23/vol/data`), so `cassandra.yaml` stays unchanged. (c) **Restore procedure:**
  `nodetool drain` and stop the writer; replace the table's live sstables with its snapshot's (the documented
  snapshot restore); start.
- **The slow data volume (external fault, for the researcher's review):** dm-delay over a 12 GiB sparse loop file on
  `/mydata`, ext4 `-o discard`, read delay 0, **write delay D\* ms constant from before the restored JVM starts until it
  is gone** (D = 0 during writer phases). D\* is chosen by the pre-registered ladder in §2.5 (100 → 300 → 1,000 ms) and
  characterized in deployment terms by S0's calibration (fsync latency of a 4 KiB write, seconds per 64 MiB written
  with `conv=fsync`). It stands for a restore target whose data volume is degraded or capped (a network block volume
  at its provisioned IOPS/throughput limit, a RAID set rebuilding, a failing disk). Milder and less targeted than B15's
  accepted 30 s × 120 s stall: it is not timed to replay and affects every data-volume write of the restart.
- **Budget (V7):** heap 1,024 MiB for the main triples (≥ 512 MiB standing rule; the retry row asks to search up from
  1 GiB); upward search to 2,048 MiB (ideal) and beyond if 2,048 still fails (§2.7). Writer heap is 1,024 MiB for every
  image; restoring onto an equal or larger heap is what a deployment that resizes nodes would do, and cannot add
  replay volume (D3 comes from the archive, not from any pool).
- **Environment deviations (disclosed):** single node, RF 1, client on the same node during writer phases only;
  data on a loop-backed dm device; logs, GC logs and dumps on `/mydata`; cgroup guard as in 2.2.

### 2.4 Ceiling arithmetic

By contract at 1,024 MiB: D1 64 MiB + D2 256 MiB + baseline ≈ 150 MiB ≈ **470 MiB < 1,024 MiB**: no OOM is possible
by the contracts. Physical prediction (B8 / B15 ledgers, ≈ 0.90 MiB per queued P64 mutation):

| Heap | Pool | Queue at the count bound (1,024 × 0.90) | Baseline | Sum | Prediction |
|---|---|---|---|---|---|
| 1,024 | 256 | 922 | ≈ 100 | ≈ 1,280 (125 %) | OOM before the bound (B15: at 741–773 queued) |
| 1,280 | 320 | 922 | ≈ 100 | ≈ 1,340 (105 %) | OOM (B15 1/1) |
| 1,536 | 384 | 922 | ≈ 100 | ≈ 1,410 (92 %) | borderline: B15 started because its stall lifted at T_r + 120 s; with a persistent slow volume the queue stays at its bound while flushes crawl → OOM or GC service loss |
| 2,048 | 512 | 922 | ≈ 100 | ≈ 1,530 (75 %) | start predicted |

Replay volume needed for the queue to fill at 1 GiB: pool ≈ 300 P64 + ≈ 770 queued; at 2 GiB pool ≈ 600 + 1,024. The
images carry 2,400 P64 mutations after the snapshot (≈ 2.0 GiB of memtable charge, ≈ 8 pools at 1 GiB), plus the
covered and post-PIT entries the reader also queues. Required flush lag: on x86 the reader is expected to be faster
than B8's 125–170 P64/s; with 2 flush writers each freeing ≈ 100 P64 mutations per flush of 85 MiB, the queue grows
whenever a flush takes longer than ≈ 200 / reader-rate seconds (≈ 1 s at 200 P64/s).

### 2.5 Workload and environment

Work directory `pc91:/mydata/s4/r23` (`harness/`, `cassandra/`, `vol/`, `archive/`, `img/`, `runs/`, `dumps-keep/`).
Never touch other folders of `/mydata/s4` or `/mydata/jingsong-s4`. One arm at a time; nothing else runs on `pc91`
during the series.

**S0 — setup.**
1. `cp -a /mydata/s4/cassandra-base /mydata/s4/r23/cassandra`; remove its `logs/`, `data/` (if any); conf check (2.3);
   record the jar sha256. `mkdir -p cassandra/data/{commitlog,hints,saved_caches} archive img runs dumps-keep`.
2. Harness under this case's `harness/`, synced to `/mydata/s4/r23/harness/`: from B15's
   [`harness/`](../commitlog_max_outstanding_replay_bytes--smaller-heap-restart/harness/) copy `B8Load.java`,
   `load.sh`, `logback-load.xml`, `gcsum.py`, `hprofhist.py`, `summ.py`, `common.sh`, `slowdisk.sh` with paths
   `/mydata/s4/b15-w3` → `/mydata/s4/r23` and dm name `r23slow`; compile with `load.sh --compile`;
   `slowdisk.sh setup` (12 GiB sparse image, mount `/mydata/s4/r23/vol`), `mkdir -p vol/data`,
   `ln -s /mydata/s4/r23/vol/data /mydata/s4/r23/cassandra/data/data`.
3. **Disk calibration** (recorded, uncounted): for D ∈ {0, 100, 300, 1,000} ms: `dd if=/dev/zero of=vol/cal bs=1M
   count=64 conv=fsync` (seconds; MiB/s) and ten `dd bs=4k count=1 conv=fsync` writes to fresh files (mean and max
   latency); then D = 0, `rm vol/cal*`.
4. Archive properties: two files under `harness/` — `archiving-writer.properties` (archive_command only) and
   `archiving-restore.properties.in` (archive_command + restore_command + restore_directories + `restore_point_in_time=@PIT@`
   + precision); scripts copy the right one to `cassandra/conf/commitlog_archiving.properties` before each start and
   log its content.

**Writer image — `mkimg.sh <img>`** (D = 0; heap 1,024 M; same guard scope as B15's `start_node`):
1. Abort if a `CassandraDaemon` runs. Empty `vol/data/*`, `cassandra/data/{commitlog,hints,saved_caches}/*`,
   `archive/*`. Writer properties in place. Start the node; wait for `Starting listening for CQL clients`; log the
   resolved `commitlog_total_space`, `memtable_heap_space`, `MaxDirectMemorySize`.
2. `load.sh schema 127.0.0.1` (keyspace `b8`, SimpleStrategy RF 1, table `b8.t_map (pk int PRIMARY KEY, m map<int,int>)`).
3. W0: `load.sh run map 5900 16 6 0 127.0.0.1 50` (≈ 300 P64, 50/s, 16 in flight).
4. `nodetool snapshot -t r23base b8` (flushes `t_map`); log its UTC time.
5. `sleep 2`; B1: `load.sh run map 5900 16 3 100000 127.0.0.1 50` (≈ 150 P64); `sleep 2`; record
   `PIT_C = date -u` minus 1 s (format `yyyy:MM:dd HH:mm:ss.SSS`); `sleep 1`.
6. B2: `load.sh run map 5900 16 45 200000 127.0.0.1 50` (≈ 2,250 P64); `sleep 2`; record `PIT_T` the same way.
7. `nodetool drain`; stop the node (SIGTERM, then the B15 `stop_node` fallback). Log commit-log and archive file lists
   and sizes.
8. Save `img/<img>/` = `vol/data` (with the snapshot), `cassandra/data/commitlog`, `archive/`, `pit.env` (`PIT_C`,
   `PIT_T`), client logs (`cp -a --sparse=always`).
- **Image gate G0:** B1 acked 140–160 and B2 acked ≥ 2,150 with < 1 % client errors; the writer did not die; the
  archive holds ≥ 3 segments. If the writer dies or errs ≥ 1 %, remake the image once at 30/s with durations scaled to
  the same counts (dated amendment).

**Restore arm — `restore.sh <run> <img> <heapMiB> <D ms> <T|C> [JVM opts]`:**
1. Abort if a daemon runs. D = 0. Empty and refill `vol/data`, `cassandra/data/commitlog`, `archive/` from `img/<img>`;
   empty hints and saved caches.
2. **Operator restore of the table:** in `vol/data/b8/t_map-*/` delete the regular files directly in the table
   directory (live sstable components, transaction logs; not `snapshots/`), copy
   `snapshots/r23base/*` except `manifest.json` and `schema.cql` into it; log both listings.
3. Write `commitlog_archiving.properties` from the restore template with `PIT_T` (arm kind T) or `PIT_C` (kind C).
4. `sync; echo 3 > /proc/sys/vm/drop_caches`; `slowdisk.sh set <D>` (log the table), then start the node at `<heapMiB>`
   with `[JVM opts]`; an `EXIT` trap and the end of the arm set D = 0 only **after** the JVM is gone.
5. T_r = first `Replaying /` line of `system.log`. Thread dumps (`jcmd Thread.print`) at T_r + 8, 12, 20, 30, 60, 90 s;
   class histograms (`jcmd GC.class_histogram`) at T_r + 5, 15, 45 s — the same times in every arm.
6. Outcome: `started` (`Starting listening for CQL clients`), `died` (`java.lang.OutOfMemoryError` in `stdout.txt` →
   heap OOM; guard kill → invalid), or `timeout` at **900 s** after JVM start (stop the JVM; apply the GC service-loss
   criterion to the GC log).
7. After: `stop_node`; copy `system.log`, `debug.log`, GC logs; `gcsum.py`; `summ.py` (replayed count, `t_map` flush
   charge during replay); `memory.events`; restore-phase lines (`Skipping restore`, number of restored segment files,
   the `Replaying` file list). Keep the **first** OOM dump of the T series (analyse with `hprofhist.py`), delete other
   dumps unread.

**D\* ladder (pre-registered, uncounted arms K, run once before the counted arms):** K100 = `restore.sh K100 A1 1024
100 T`. If its dumps between T_r + 8 and + 90 s show (G2) at least one `MemtableFlushWriter` in flush I/O
(`FileChannelImpl.force`/`fsync`/write/`open0`) **and** ≥ 24 of 32 `MutationStage` threads in
`SubAllocator.allocate` at one dump, D\* = 100 ms. Otherwise K300 (300 ms), then K1000 (1,000 ms), same rule. If none
meets G2, stop the series: the finding is that this volume class does not lag replay on `pc91` (report the K readings;
no fallback to a stall timed to replay, which B15 already covered). The K arms' outcomes are reported but do not count
toward V1–V4. D\* then stays fixed for every counted arm.

**Counted arms** (images A1, A2, A3 = three independent writer runs, identical procedure):

| Run | Image | Heap | Write delay | PIT | JVM opts | Role |
|---|---|---|---|---|---|---|
| mk-A1, mk-A2, mk-A3 | — | 1,024 (writer) | 0 | — | — | images |
| K100 (K300, K1000) | A1 | 1,024 | ladder | T | — | D\* calibration (uncounted) |
| T1, T2, T3 | A1, A2, A3 | 1,024 | D\* | T | — | **test** |
| C1, C2, C3 | A1, A2, A3 | 1,024 | D\* | C | — | **matched control**: same archive, same deserialized input, applied volume ≈ 150 P64 (≈ 0.5 pool) |
| I1, I2, I3 | A1, A2, A3 | 1,024 | D\* | T | `-Dcassandra.commitlog_max_outstanding_replay_count=64` | **intervention** |
| N1 (N2, N3) | A1 (A2, A3) | 1,024 | 0 | T | — | restore on the plain disk (no slow volume): N2, N3 only if N1 OOMs |
| U… | A1, A2, A3 | 1,280–3,072 | D\* | T | — | upward budget search (2.7) |

**Order:** S0 → mk-A1 → K-ladder → T1 → C1 → I1 → N1 → mk-A2 → T2 → C2 → I2 → mk-A3 → T3 → C3 → I3 → U-search →
N2, N3 (if N1 OOMed). Launch each script detached (`setsid nohup … &`), poll with bounded waits.

**Validity gates** (decided from the arm's own logs before it counts):
- **G1 (volume reached):** in the arm's restore, the `Replaying` list includes the restored archive segments; for T,
  I and N the `t_map` replay reaches ≥ 2,250 applied P64 mutations when it completes (I, N: from `Log replay complete`
  and the `t_map` flush charge ≥ 1.7 GiB); for T, which is expected to die, G1 is read from the same image's I arm.
- **G2 (slow volume engaged):** as in the ladder, on any dump of the arm while the JVM is alive (T, C at the time
  their first flush runs, I). For C, G2 requires only the flush writer in I/O (its pool is not expected to fill).
- **G3 (control volume):** C's `t_map` flush charge during replay ≤ 200 MiB (< the 256 MiB pool) and its replayed
  count ≤ 400 (P64 plus system-table updates).

### 2.6 Instruments

- **U (D1), independent of K:** class histograms at T_r + 5 / 15 / 45 s and the first T OOM dump: replay-deserialized
  `ArrayCell` (only replay creates them) + one `SingleItemCellPath` and one 48 B `HeapByteBuffer` per `ArrayCell` + the
  replay share of `byte[]` (total minus the memtable share seen in C at the same pool fill), as B8 §3.4 / B15 §3.5;
  `org.apache.cassandra.db.Mutation` instance count. D2 from `BufferCell` counts and the pool's flush lines.
- **K:** live `Mutation` count × 63.7 KiB (P64 serialized size, B6/B8 calibration) and the count against 1,024.
- **Heap:** GC log (`gcsum.py`: Full GCs, max live after Full GC, worst-60 s STW share); `memory.current` each second
  (guard only).
- **Volume and restore:** restored segment count and bytes, `Replaying` list, `Log replay complete` count, `t_map`
  flush charge during replay, B1/B2 acked counts and the PITs.
- **Fault:** `dmsetup table r23slow` with timestamps at each switch; thread dumps (G2); S0 calibration.
- **Reader and apply rates (x86):** live `Mutation` counts between histograms; in N and I arms, replayed P64 per
  second from `Log replay complete` time.
- **Intervention throughput:** start-up duration and replayed count (I replays everything, rejects nothing).
- **Endpoint (V5):** the first `java.lang.OutOfMemoryError` line with its thread if printed, the dump histogram, the
  thread dumps before death.

### 2.7 Predicted response, stopping budget, search

| Arm | Predicted outcome | Predicted readings |
|---|---|---|
| T (1 GiB, D\*) | **heap OOM in replay 3/3**, within ≈ 10–120 s of T_r | before death ≈ 700–800 live `Mutation`s (K ≈ 44–50 MiB ≤ 64 MiB), U ≈ 0.6–0.7 GiB, D2 ≈ 256 MiB; ≥ 24/32 appliers parked; `main` in deserialization |
| C (1 GiB, D\*) | started 3/3 | ≤ 50 live `Mutation`s at every histogram, max live after Full GC ≤ 50 % of heap; replay ends after its last flush crawls through the slow volume |
| I (1 GiB, D\*, count 64) | started 3/3, slower than C | ≤ 66 live `Mutation`s (U ≤ 70 MiB); every post-snapshot mutation replayed |
| N (1 GiB, no delay) | started (as B8 X) — or, if the x86 reader outpaces flushes on the plain RAID volume, OOM (then N2, N3 run and the slow volume is not needed; reported as its own condition) | — |
| U 1,536 | OOM or GC service loss | queue at 1,024 bound, ≥ 92 % live |
| U 2,048 | started (≈ 75 % live) | — |

**Upward search** (after the triples, D\* and PIT_T): T at 1,536 M on A1. If it OOMs → 2,048 on A2; if 2,048 OOMs →
2,048 on A3, then 3,072 on A1 once. If 1,536 does not OOM → 1,280 on A2. Report the largest failing heap with its n/N;
a heap where the node starts is the boundary, not a negative.

**Stopping budget:** each restore arm ≤ 900 s from JVM start; each writer image ≤ 10 min; the whole series ≤ **5 h**
from the start of S0 (stage 2 records the clock). Drop order if behind: N2/N3, U beyond 2,048, U entirely; then image
reuse (C and I on A1–A2), recorded — never drop a third T, C or I run silently (report n/N as run). No escalation after an
OOM (no larger archives, no other payloads, no change of D\* after the ladder). **Clean-up:** stop every JVM and client,
D = 0, `slowdisk.sh teardown` (unmount, remove `r23slow`, detach only its loop, delete the image file), delete `img/`
and `archive/`; keep `runs/`, `harness/`, the kept dump; leave nothing running.

### 2.8 Controls and intervention

- **Matched control (V2), ≥ 3 runs:** C1–C3 — same build, heap, slow volume, archive, snapshot and restore procedure;
  the reader deserializes the same segments. Only the PIT differs: C restores to just after B1 (≈ 150 P64, under half a
  pool), so the pool never fills, the appliers never park, and the post-PIT entries' tasks return at once. Predicted to
  start: shows that the endpoint needs applied volume beyond the pool, not the deserialization of a large archive by
  itself. N1 is the second contrast (same restore, plain disk), as B8 X / B15 N.
- **Causal intervention (V4), ≥ 3 runs:** I1–I3 — the test condition with
  `-Dcassandra.commitlog_max_outstanding_replay_count=64` (a non-default constraint in the intervention arm only, V6
  exception): the queue holds ≤ 64 mutations ≈ 60 MiB, so the endpoint should disappear while every mutation is
  replayed (record start-up time). Same intervention as B8 and B15.
- **Classification to record:** D1 U vs C (64 MiB) and K; D2 at its cap; D3 volume vs the restored heap. T OOM with
  K ≤ C and U ≫ C → bypass · accounting mismatch, reached through the unprotected restore volume. Conditions label
  proposed `deployment` if the researcher accepts §2.3 (a) the archive restore and (c) its procedure as deployment
  events and the persistent slow data volume (D\*) as an external fault; otherwise `diagnostic`. No other supporting
  deviation is planned.

`sha256 of §1–§2 at freeze: 0348c9d480d39f7ab353e9c951ed119709344a3ec2a1d48519b5d812715ecca7` (bytes from the line `## 1. Candidate` up to, not including, this line; check: `awk '/^## 1\. Candidate/{p=1} /^.sha256 of §1–§2 at freeze/{p=0} p' <file> | sha256sum`) · frozen 2026-11-24 by stage 1 · amendments after the freeze: dated, with reason.

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
