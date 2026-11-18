# B12 — paxos_cache_size: the Paxos state cache weigher omits the partition key  <!-- file: cassandra/cases/paxos_cache_size--weigher-omits-partition-key/paxos_cache_size--weigher-omits-partition-key.md -->

| Field | Value |
|---|---|
| Case ID | `B12` (B = bypass, README "ID prefixes") |
| From | `OC-14` of the [phase 1 OOM candidate list](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md) |
| Phase-1 case file | [`paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9; repo HEAD `b037b4fb` at design time); on `ms0611` the built copy `/mydata/s4/b11-w1/cassandra-base` (B11's, local git `5efb50e`, `git diff` empty, `conf/cassandra.yaml` md5 `714ee9bf…`, the same as the repo's) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5, workflow subagent), 2026-11-18 03:00–03:40 America/New_York |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (Claude Opus 5.5, fresh workflow subagent), 2026-11-18 03:15–05:30 America/New_York, `ms0611` (aarch64) |
| Verdict | **true positive** · `verified-OOM · deployment` (bypass, accounting omission) |

## Summary

- **Conclusion (stage 2): true positive, `verified-OOM · deployment`.** At a 2 GiB heap with all defaults, v1 `SERIAL` reads on
  distinct absent partitions with 60 KiB keys ran out of heap (`Java heap space`) in 3/3 runs after ≈ 26,400 reads; the same at
  4 GiB (3/3, ≈ 47,400 reads) and with 16 KiB keys at 2 GiB (≈ 93,500 reads). The control (consistency ONE) stayed at ≈ 58 MB 3/3;
  the patched weigher held the cache at 340 entries and survived 3/3. Dumps put 68–76 % of the heap in cached keys. 4 KiB and 16 B
  keys plateau at 37× and 5× the cap without an OOM.
- **Design (stage 1):** a heap OOM at a 2 GiB heap with every capacity setting at its 5.0.9 default. A client sends
  `SERIAL` reads (the default Paxos `v1` path) on many distinct, absent partitions whose `blob` partition key is 60 KiB
  (legal: the limit is 65,535 B). Each read leaves one entry in the Paxos state cache `PaxosState.RECENT`. The cache
  weighs that entry at 128 B, but the entry keeps the 60 KiB key on the heap. The auto cap (20 MiB at a 2 GiB heap)
  therefore admits 163,840 entries, about 10 GB of keys, and the heap fills after about 20,000–34,000 reads.
- **Root cause (claimed at design, confirmed by stage 2):** the `RECENT` weigher (`PaxosState.java:74`) counts only the `unsharedHeapSize()` of the
  stored accepted/committed updates. The partition key (and the entry's shells) are never charged. This is an
  accounting omission (U ≫ C, K ≤ C), the same class of defect that CASSANDRA-4315 fixed for the key cache in 1.2.
  Phase 1 measured the shell part (≈ 4–7× for empty updates). The key part grows with the key size and is unbounded
  up to the 64 KiB protocol limit.

## 1. Candidate

**Candidate row (quoted from the phase-1 list, 2026-11-12):**

> | OC-14 | 2026-11-12 | `paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous` | legacy | [L2; lead list, blind, E1; bypass-leads §2] The Paxos state cache weigher counts only the stored updates (`PaxosState.java:73-74`); non-applying CAS and v1 SERIAL reads stash empty updates weighing ≈ 64–128 B but holding ≈ 500 B, so the default 50 MiB cap keeps 400–800 K entries ≈ 200–350 MB (4–7×), modest at heaps ≥ 5 GiB. | CP-1 | picked: B12 |

**Phase-1 constraint and check.** `paxos_cache_size` (`Config.java:485`, default `null` = auto). Auto =
`min(max(1, (int)(totalMemory × 0.01 / 2^20)), 50)` MiB (`DatabaseDescriptor.java:849-852`). The value is the
`maximumWeight` of `PaxosState.RECENT` (`PaxosState.java:72-76`), a Caffeine map that keeps the last `Snapshot` of every
quiescent Paxos partition. The weigher is
`(k, v) -> saturatedCast((v.accepted != null ? v.accepted.update.unsharedHeapSize() : 0) + v.committed.update.unsharedHeapSize())`.
It does not read the key `k`.

**Phase-1 stage 4** ([results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous.md),
2026-10-25, advisor's laptop, arm64 macOS, JDK 11, 2 GiB heap): **Confirmed — caps**. The test used applying LWTs with
4 KiB values and 4-byte `int` keys. The retained `PaxosState$Snapshot` count was exactly ⌊C·2^20 / 4,352 B⌋ (481 · 7,710 ·
4,818 at 2 · 32 · auto = 20 MiB). The live heap was 1.11 × the weight, and the unweighed part was ≈ 440 B per entry (`Snapshot`, `Key`,
`Committed`, `PartitionUpdate`/`BTreePartitionData` shells, `PreHashedDecoratedKey` 40 B, `LongToken`, Caffeine and
CHM nodes). Unit-tier control (b) measured an empty update at **64 B** of weight (1,344 − 1,280). The 2026-11-16 recheck
(E1) found the empty-update case (≈ 4–7×) that became OC-14. Neither phase-1 run varied the partition key size. The key
was 4 bytes in both.

**What this design adds (read from the source, 2026-11-18).** The uncounted ≈ 440 B includes the partition key. For a
`blob` key, the entry holds the whole key array. A v1 `SERIAL` read on partition key `k` decorates
`ByteBufferUtil.clone(k)`, a fresh exact-length `byte[]` (`SelectStatement.java:732-733`, `ByteBufferUtil.java:265-273`).
`legacyReadWithPaxos` (`StorageProxy.java:1906-1933`; `Paxos.isLinearizable()` is true for `v1`, `Paxos.java:1226-1233`)
runs `doPaxos` with an empty proposal. The local replica runs `legacyPrepare` and `legacyPropose` with the coordinator's
objects (`StorageProxy.java:705-716`; `PaxosState.java:720-806`). The empty update is not committed (`StorageProxy.java:529-534`).
The new `PaxosState.Key` keeps that `DecoratedKey` (`PaxosState.java:131-140`, `:371-382`). A fresh key loads
`Committed.none(key)` (`SystemKeyspace.java:1329-1336`, `Commit.java:188-190`), and `close()` stashes the `Snapshot` into
`RECENT` (`PaxosState.java:514-527`). The weight of that entry is 64 B (`accepted` = empty update:
`EMPTY_STATIC_ROW` 40 + `MutableDeletionInfo` 24, `PartitionUpdate.java:101-106, 357-361`) + 64 B (`committed` = none) =
**128 B**, whatever the key size. The key may be up to 65,535 B (`QueryProcessor.java:259-262`). No guardrail limits
partition-key size in 5.0.9. So the real per-entry heap is ≈ K + 600 B for a weight of 128 B.

**JIRA prior art** (read only; nothing posted):
- Survey CSV (`jira-oom-survey.csv`, 604 rows), filtered for paxos/LWT/CAS/serial/weigher/partition key:
  **CASSANDRA-4315** "Use EntryWeigher instead of Weigher to Measuring the cache" (Fixed 1.2.0 beta 1; survey:
  `bypass:accounting-mismatch`, "cache weigher ignored key overhead; long row keys can OOM"). This is the same defect class
  in the key cache, fixed there by measuring key + value. No survey row concerns the Paxos state cache. CASSANDRA-17530 and
  CASSANDRA-18047 are Paxos correctness/test issues (excluded).
- JIRA REST (issues.apache.org, 2026-11-18, `project = CASSANDRA AND …`):
  `text ~ "paxos_cache_size"` (41 hits: config plumbing such as 17737/17738/17797/20249; none on sizing),
  `text ~ "PaxosState" AND text ~ "RECENT"` (8: 17164 CEP-14, which introduced the cache in 4.1; 19617, 12126, 21893
  correctness), `text ~ "paxos" AND text ~ "OutOfMemoryError"` (8, none on the cache), `text ~ "paxos" AND text ~ "weigher"`
  (2, unrelated), `text ~ "paxos cache"` (55, none on its accounting), `summary ~ "paxos" AND summary ~ "memory"` (0),
  `text ~ "weigher" AND text ~ "key"` (10: 4315 as above, 9738, 3143, 4150, 19703; none on Paxos).
- **Verdict: `new`.** No issue reports the `RECENT` weigher omitting the key or the shells. The analogous key-cache
  defect is known-fixed (4315), so this is not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

The Paxos state cache `PaxosState.RECENT` (`PaxosState.java:72-76`) is bounded by `paxos_cache_size` in weight units.
The weigher counts only the stored updates' `unsharedHeapSize()`. Each entry also holds its `PaxosState.Key`, whose
`DecoratedKey` keeps the partition key bytes (one `byte[K]` per distinct key, cloned at `SelectStatement.java:733`), plus ≈
450–600 B of shells and nodes, all uncounted. A v1 `SERIAL` read on an absent partition leaves an entry of weight 128 B
(§1). With K = 61,440 B (60 KiB) each entry holds ≈ 62.0 KB, **≈ 484× its weight**. At a 2 GiB heap the auto cap is 20 MiB
= 163,840 such entries ≈ 10.2 GB of heap, 5× the whole heap. Nothing else bounds the cache. There is no time-based expiry,
and the only removal is weight eviction or a later access (`RECENT.remove` on reuse, `:371-382`). So distinct-key
`SERIAL` reads fill the heap and stay there. **Direction: bypass, accounting omission** (U > C with K ≤ C: at the predicted
OOM point K ≈ 28,000 × 128 B ≈ 3.4 MB ≤ C = 20 MiB, U ≈ 1.7 GB). Interpretation: suspected implementation defect (the
CASSANDRA-4315 class). Technique note: [`bypass-playbook.md`](../../../bypass-playbook.md) (protected path vs suspect
path on matched payload; intervention restores the accounting).

### 2.2 Protection map (fixed before the run)

| Domain | Holder / allocation | Counter (K) | Limit at defaults, 2 GiB heap | At the limit | Covers the key bytes? |
|---|---|---|---|---|---|
| **Paxos state cache** (the claim) | `PaxosState.RECENT` (static Caffeine map, strong keys/values; one per node); entry = `Key` → `DecoratedKey` → `byte[K]`, `Snapshot`, `Accepted`/`Committed`, 2 empty `PartitionUpdate`s, Caffeine + CHM nodes; released only by weight eviction (on the writing thread, `ImmediateExecutor`) or reuse of the key | Caffeine weighted size = Σ updates' `unsharedHeapSize()` = 128 B per entry here | `paxos_cache_size` auto = min(max(1, ⌊2,147,483,648 × 0.01 / 2^20⌋), 50) = **20 MiB** (163,840 entries of 128 B) | evict least-valuable entries | **no** (accounting omission) |
| Paxos in-flight map | `PaxosState.ACTIVE` (unbounded `ConcurrentHashMap`, `:71`) | none | none; bounded by requests in flight (32) | — | holds only in-flight keys (≤ 32) |
| `system.paxos` memtable | promise and proposal rows; each holds a copy of the key (row_key) and the serialized empty proposal (≈ K + 100 B, also carrying the key) in `heap_buffers` slab regions | memtable pool (owns) | `memtable_heap_space` = maxMemory/4 = **512 MiB**; cleanup threshold 1/(1+2) = 0.333 → flush at ≈ 171 MiB | flush; writes block at the limit | yes (charged; bounded and flushed) |
| Native request intake | decoded EXECUTE frames, bound values (`byte[K]` per request, `CBUtil.java:443-450`) | in-flight bytes | heap/10 = 204.8 MiB global, heap/40 = 51.2 MiB per IP | pause reading | yes (32 × ≈ 61.5 KB ≈ 2 MB) |
| Key cache | `KeyCacheKey` for sstable reads of `system.paxos` / `b12.t` | Caffeine weigher (B7 gap) | min(5 % heap, 100 MiB) = 100 MiB | evict | not populated: absent keys miss the bloom filter. Checked by `nodetool info` "Key Cache" entries |
| Heap budget | all of the above + baseline | — | **2 GiB** (`-Xms2G -Xmx2G`, G1) | `OutOfMemoryError` → `-XX:OnOutOfMemoryError=kill -9 %p` | — |
| Direct budget | Netty, chunk cache, index summaries, bloom filters | — | `MaxDirectMemorySize` as `cassandra-env.sh` resolves it (record from `VM.flags`) | not part of the claim | — |

### 2.3 Configuration and budget audit

- **Constraints (V6), all at shipped 5.0.9 defaults, resolved at the planned heaps:** `paxos_cache_size` unset (auto) →
  20 MiB at 2 GiB, 40 MiB at 4 GiB (`totalMemory` = `-Xms`). Stage 2 reads it back: `system_views.settings` shows `null`,
  and the resolved value is 1 % of the committed heap from `jcmd VM.flags`/`GC.heap_info`. `paxos_variant` v1
  (`Config.java:1051`; shipped yaml line `:1602` commented). `paxos_state_purging` legacy. `paxos_repair_enabled` true.
  `memtable_heap_space` auto (512 / 1,024 MiB), `memtable_allocation_type: heap_buffers`, `memtable_flush_writers` 2 →
  cleanup 0.333. `native_transport_max_request_data_in_flight` heap/10, per IP heap/40. Key/counter cache auto.
  `commitlog_total_space` auto (min(8,192 MiB, ¼ of the 39 GiB `/mydata` volume) = 8,192 MiB). The only config file is the
  shipped `conf/cassandra.yaml` (md5 `714ee9bf58b3bc1710377ac16bcbba03`), unmodified, data under the tree's `data/`. The
  one constraint change in the whole design is in the optional fallback intervention arm (`paxos_cache_size: 0MiB`, §2.8),
  which V6 allows.
- **Supporting settings:** none changed. No raised timeouts, no Byteman. The only non-default runtime choice is
  environment: `systemd-run --user --scope -p MemorySwapMax=0` (swap off for the victim), heap dumps to `/dev/shm`
  (instrument location only).
- **Budgets (V7):** heap **2 GiB** (the ideal budget; `MAX_HEAP_SIZE=2G`, so `cassandra-env.sh` sets `-Xms2G -Xmx2G`, G1)
  for the counted arms. Upward search: **4 GiB** (`MAX_HEAP_SIZE=4G`). `MaxDirectMemorySize` is left to
  `cassandra-env.sh` (record the resolved value; B11 recorded 15,872 MiB on this node). No container memory limit is
  the budget. The scope only sets `MemorySwapMax=0`. What the system resolves for the node: 64,249 MB RAM, 8 cores →
  `cassandra-env.sh` heap min(½ RAM, 15,872 MiB) = 15,872 MiB. Both budgets are ≥ 512 MiB, so V7 is met by the standing
  rule without per-case review.
- **Workload legality (not a constraint):** the partition key is 61,440 B, below the 65,535 B protocol limit, under the
  default authenticator, with no guardrail on key size. Keys this large are unusual. §2.6 therefore adds a key-size dial
  (16 KiB, 4 KiB, 16 B) that places the boundary. By arithmetic, any K ≳ 10 KiB OOMs a heap ≤ 5 GiB (the cap is 1 % of heap
  there, so the ratio (K + 600)/128 must exceed ≈ 80 = usable heap / cap). At heaps ≥ 5 GiB the cap is a fixed 50 MiB
  (409,600 entries), so an H-GiB heap needs K ≳ H × 2.1 KiB (≈ 17 KiB at 8 GiB, ≈ 33 KiB at the 15.5 GiB auto heap).

### 2.4 Ceiling arithmetic at defaults (2 GiB heap)

Contract capacities on the heap: `RECENT` 20 MiB + memtables 512 MiB + native in-flight 204.8 MiB + key cache 100 MiB +
counter cache min(2.5 %, 50 MiB) = 50 MiB + baseline (≈ 50–90 MB live after start, stage 4: 45.7 MB) ≈ **0.96 GiB < 2
GiB**. Convergence of the contracts cannot OOM this heap, so an OOM needs U > C in some domain. Claimed domain: `RECENT`
at K = 61,440 B wants up to 163,840 × ≈ 62.0 KB ≈ **10.2 GB** (≈ 500× C). At 4 GiB: cap 40 MiB = 327,680 entries ≈
20.3 GB.

Per-entry heap, predicted for K = 61,440 (JDK 11, compressed oops, from the stage-4 measured shallow sizes):
`byte[61,440]` 61,456 + `HeapByteBuffer` 48 + `PreHashedDecoratedKey` 40 + `LongToken` 24 + `PaxosState$Key` 24 +
`Snapshot` 32 + `Ballot` 32 + `AcceptedWithTTL` (the proposal) ≈ 40 + `Accepted` 24 + `Committed` 24 + 2 × (`PartitionUpdate`
32 + `BTreePartitionData` 32 + `MutableDeletionInfo` 24) + Caffeine node 40 + CHM node 32 + table/sketch ≈ 12 ≈ **62,000 B
(band 61,700–62,700)**. The weight is 128 B. Predicted OOM point at 2 GiB: usable ≈ 0.95 × 2,048 MiB, minus baseline
(50–90 MB), minus the `system.paxos` memtable (0–340 MiB: one active plus one flushing), divided by 62.0 KB →
**N\* ≈ 20,000–34,000 completed reads (centre ≈ 28,000)**.

### 2.5 Workload and environment

- **Node:** `ms0611` only (Utah m400, **aarch64** X-Gene, 8 cores, 64,249 MB RAM, 8 GiB swap present but unused,
  Ubuntu 22.04, kernel 5.15, cgroup v2, OpenJDK 11.0.33, Ant 1.10.12, Python 3.10.12). Checked read-only at 03:07 EST
  on 2026-11-18: idle (no `java`, no `CassandraDaemon`), `/mydata` 39 G, **27 G free**, `/dev/shm` 32 G free,
  B11's `/mydata/s4/b11-w1/` (8.3 G incl. `runs/` 7.2 G) present. **Do not modify or delete anything under
  `/mydata/s4/b11-w1/`, `/mydata/s2r2`, `/mydata/u1r2`.** The victim and the client run on the same node, as in B11.
  The platform is aarch64, so these runs are never pooled with x86 runs. Re-check `ps -eo cmd | grep '[C]assandraDaemon'`
  before every run.
- **Work directory:** `/mydata/s4/b12/` (new). `sudo loginctl enable-linger jason92` at start, `disable-linger` at
  the end (B11 practice for `systemd-run --user`).
- **Builds:**
  - Base: `cp -a /mydata/s4/b11-w1/cassandra-base /mydata/s4/b12/cassandra-base` (read-only reuse of B11's built tree, 538 MB),
    then `rm -rf /mydata/s4/b12/cassandra-base/{data,logs}` (B11's leftovers in the copy only). Check `git diff` is
    empty, `git describe --tags` = `cassandra-5.0.9`, the yaml md5, and that `build/apache-cassandra-5.0.9-SNAPSHOT.jar`
    exists.
  - Intervention: `cp -a /mydata/s4/b12/cassandra-base /mydata/s4/b12/cassandra-iv`, apply `harness/iv.patch` (§2.8), then
    `rm -f build/classes/main/org/apache/cassandra/service/paxos/PaxosState*.class`, then `ant jar` (B11's incremental
    build took 35 s). Check with `javap -p -c -classpath build/apache-cassandra-5.0.9-SNAPSHOT.jar
    org.apache.cassandra.service.paxos.PaxosState | grep -c "ByteBuffer.remaining"`, which must be greater in iv than
    in base. Never run `ant` in a tree a node runs from.
- **Schema** (each run, after CQL is up): `CREATE KEYSPACE b12 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE b12.t (k blob PRIMARY KEY, v int)`. The table stays empty, so every read targets an absent partition.
- **Client** `harness/client.py` (Python 3 standard library, raw native protocol **v4**, after B11's `client.py`):
  C = 32 connections to 127.0.0.1:9042, one request outstanding each (closed loop, one thread per connection), STARTUP,
  PREPARE `SELECT v FROM b12.t WHERE k = ?`, then EXECUTE with one bound blob value. Consistency is `SERIAL` (0x0008)
  in the test arms and `ONE` (0x0001) in the control arm, and that is the only difference. Key i (i = 0, 1, …, each
  used once) = 8-byte big-endian i ‖ a fixed pad of K − 8 bytes from `random.Random(12)` (the same pad in every run
  and arm; distinctness comes from the prefix). Per-request timeout 30 s. An error is counted and the next key is used,
  with no retry. Logs: `client.txt` every second (t, issued, completed OK, errors by code, outstanding),
  `errors.txt` (first 50 error messages). **Milestones:** at every M completed keys (§2.6), stop issuing, wait for
  outstanding = 0 (≤ 60 s), create `$R/ms-<n>.req`, wait for `$R/ms-<n>.done` (≤ 180 s), then resume. Stop at N_max
  issued keys or when the socket dies (daemon gone). Protocol v4 avoids the native-v5 large-frame retention seen in
  earlier cases. A 61.5 KB request is below `LARGE_MESSAGE_THRESHOLD` (131,071 B) in any case.
- **Run driver** `harness/run.sh <run-id> <base|iv> <heap> <K> <SERIAL|ONE> <N_max> <M> [cap0]`, after B11's `run.sh`:
  1. Preflight: no daemon, ports 7000/7199/9042 free, `/mydata` free ≥ the arm's disk need (§2.9), `/dev/shm` free ≥
     heap + 1 GiB.
  2. Wipe `<tree>/data`, `<tree>/logs`.
  3. Start `( ulimit -n 100000; cd <tree>; MAX_HEAP_SIZE=<heap> CASSANDRA_HEAPDUMP_DIR=/dev/shm/b12/<run-id> exec systemd-run --user --scope -p MemorySwapMax=0 --unit=b12-<run-id> -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &`.
     Wait for "Starting listening for CQL clients" (≤ 300 s).
  4. Record `jcmd VM.flags`, `VM.command_line`, and read back `system_views.settings` for `paxos_cache_size`,
     `paxos_variant`, `paxos_state_purging`, `memtable_heap_space`.
  5. DDL, then the baseline live histogram `histo-0.txt`.
  6. Start `monitor.sh`, then the client.
  7. Serve milestone requests. For each: `timeout 120 jcmd <pid> GC.class_histogram > $R/histo-<n>.txt`, then
     `nodetool tablestats system.paxos b12.t` (memtable on-heap size, "Memtable data size") and
     `nodetool info | grep -i "key cache"`, then write `.done`.
  8. On client end with the daemon alive: hold 60 s, take a final live histogram `histo-end.txt`, `nodetool tablestats`,
     then stop the daemon (`kill`, `kill -9` after 60 s).
  9. On daemon death: record the end and the first OOM line.
  10. Copy `system.log`, `debug.log`, `gc.log*` to `$R`. Run `summarize.py`.
  11. Wipe `<tree>/data` (frees the disk for the next run).
- **Monitor** `harness/monitor.sh` (identical in every arm): every 2 s `jcmd GC.heap_info` + `RssAnon` + the scope's
  `memory.current`. Every 10 s, `nodetool sjk mx` for `org.apache.cassandra.metrics:type=ClientRequest,scope=CASRead,name=Latency`
  `Count` and `…scope=Read,name=Latency` `Count`, and the table metrics `CasPrepareLatency`/`CasProposeLatency` `Count`
  of `b12.t`. G1 GC logging is the shipped default (`gc.log`).
- **No intrusive instrument during load** besides the milestone live histograms, taken during a client pause. The
  claimed holder is a standing strong-reference pool, so a full GC cannot change it.

### 2.6 Arms, order and predictions

All arms use base build, defaults, and 32 connections unless stated. M = milestone step, in completed keys.

| # | Arm | Build | Heap | K (B) | CL | N_max | M | Runs | Predicted endpoint |
|---|---|---|---|---|---|---|---|---|---|
| 0 | **Shakedown** (not a reading) | base | 2G | 61,440 | SERIAL | 2,000 | 1,000 | 1 | alive. Path check (below) |
| 1 | **T** test | base | 2G | 61,440 | SERIAL | 50,000 | 4,000 | 3 | **heap OOM** at N\* ∈ [20,000, 34,000] |
| 2 | **C** control (protected path, matched payload) | base | 2G | 61,440 | ONE | 50,000 | 4,000 | 3 | alive |
| 3 | **I** intervention (weigher counts the key) | iv | 2G | 61,440 | SERIAL | 50,000 | 4,000 | 3 | alive, `RECENT` plateau 340 |
| 4 | **B4** budget search | base | 4G | 61,440 | SERIAL | 90,000 | 8,000 | 1 (→ 3 if time) | heap OOM at N\* ∈ [45,000, 70,000] |
| 5 | **D4** key-size dial (nearest surviving) | base | 2G | 4,096 | SERIAL | 200,000 | 25,000 | 1 | alive. Eviction plateau 163,840 entries ≈ 37× C |
| 6 | **M** phase-1 claim (small key) | base | 2G | 16 | SERIAL | 200,000 | 25,000 | 1 | alive. Plateau 163,840 entries ≈ 4.5–5× C |
| 7 | **D16** key-size dial | base | 2G | 16,384 | SERIAL | 160,000 | 16,000 | 1 | heap OOM at N\* ∈ [90,000, 120,000] |

**Shakedown checks (stop and fix the harness if any fails; record harness fixes as defects, not amendments):**
- read-back shows `paxos_variant` v1 and `paxos_cache_size` null.
- 2,000 reads complete with 0 errors.
- `CASRead` count ≥ 2,000. `b12.t` `CasPrepareLatency` and `CasProposeLatency` counts ≥ 2,000 (the v1 path ran).
- `histo` deltas from `histo-0`: `PaxosState$Snapshot` +2,000 (± 32), `PaxosState$Key` +2,000 (± 32), and `[B`
  ≥ +2,000 × 61,456 B.
- `PaxosState` (ACTIVE) ≤ 32.
- `ks` throughput printed. If < 30 reads/s, re-plan the time (§2.10) before run 1.

**Predicted readings per arm (frozen):**
- **T (×3):**
  - Each run ends in `java.lang.OutOfMemoryError: Java heap space` (stdout/`system.log`, then `kill -9` by
    `OnOutOfMemoryError`), with a heap dump in `/dev/shm/b12/<run>/`.
  - OOM at N\* (completed OK + errored-after-propose) ∈ **[20,000, 34,000]**.
  - At every milestone before the OOM: `Snapshot` count = completed keys + 32 at most (no eviction: the weight is
    128 × N ≤ 4.4 MB < 20 MiB).
  - Live-heap slope ΔTotal / ΔSnapshot between the first and the last milestone, after subtracting the `system.paxos`
    memtable on-heap size from `tablestats` at each, ∈ **[61,700, 62,700] B** per entry.
  - At the last milestone, `Snapshot` count × 62,000 B ≥ 60 % of the 2 GiB heap.
  - In the dump (V5): `byte[61440]` arrays reachable from GC roots ≥ 0.95 × the last `Snapshot` count and ≥ 1.2 GiB in
    total, with the referrer chain `byte[] ← HeapByteBuffer ← PreHashedDecoratedKey ← PaxosState$Key ← Caffeine node`.
  - `PaxosState` (ACTIVE) ≤ 64 at every histogram.
- **C (×3):**
  - The daemon is alive at 50,000 reads.
  - 0 % `Snapshot`; `CASRead` count 0.
  - Live `Total` at `histo-end` ≤ `histo-0` + 150 MB.
  - Max heap after a G1 cycle ≤ 30 % of the heap.
- **I (×3):**
  - The daemon is alive at 50,000 reads.
  - `Snapshot` count plateaus at ⌊20 × 2^20 / (128 + 61,440)⌋ = **340** (± 1, + 32 in flight) from the first milestone on.
  - Live `Total` at `histo-end` ≤ `histo-0` + memtable on-heap + 150 MB.
  - The same `system.paxos` write load as T: `CasPrepare` count ≥ 50,000. Record the reads/s and compare with T's
    first 20,000 (recorded, not a pass criterion).
- **B4:** heap OOM at N\* ∈ [45,000, 70,000]. `Snapshot` = completed (cap 40 MiB → no eviction).
- **D4:**
  - The daemon is alive.
  - `Snapshot` count rises to 163,840 (± 1, + 32), then stays there.
  - Live `Total` at the plateau ≈ `histo-0` + 163,840 × (4,112 + 600) B ≈ + 0.77 GB (± 15 %), plus the memtable.
  - U/C ≈ 37.
- **M:**
  - The daemon is alive. Plateau at 163,840.
  - ΔTotal ≈ 163,840 × (≈ 620) B ≈ 100 MB (± 25 %), so U/C ≈ 4.5–5.5. This tests OC-14's literal "4–7×".
- **D16:**
  - Heap OOM at N\* ∈ [90,000, 120,000] (163,840 × ≈ 17,000 B = 2.8 GB wanted).
  - If alive at N_max, record the plateau.

**Readings → meaning (decided now):**

| Observation | Meaning |
|---|---|
| T OOMs 3/3 in the band, C 0/3, I 0/3, dump attributes ≥ 60 % of the heap to `RECENT` keys | claim holds: **verified-OOM · deployment** (bypass), if V1–V7 hold |
| T OOMs outside the N\* band, but slope and dump as predicted | claim holds; the arithmetic of §2.4 is off (note it) |
| T `Snapshot` count < completed keys (eviction) before the OOM | the weigher counts more than derived; re-derive. The OOM may still stand if the dump attributes it |
| T alive at 50,000 with `Snapshot` = 50,000 and heap < 2 GiB | per-entry footprint smaller than derived (e.g. the key not retained); retry with a larger N_max, or false positive if the dump shows no key arrays |
| T ≥ 90 % of 60 s in GC without an OOM by the stop budget | `verified-gap · service-loss` → **retry** (state the criterion: protocol default) |
| C OOMs, or C live heap grows with keys | the payload itself, not `RECENT`, holds memory: attribution fails (V2) |
| I OOMs, or the I plateau ≠ 340 | the patch does not bound the holder: attribution fails (V4); check the patched class |
| B4 OOMs | the largest failing budget is ≥ 4 GiB (report n/N) |
| `/mydata` free < 2 GiB during a run | invalid (disk), not a reading. Free space and repeat at a lower N_max |

### 2.7 Instruments: U independently of K

- **K (the control's counter)** is not exported. It is derived as `Snapshot` count × 128 B. This uses the weigher formula
  and the stage-4 measured empty-update weight of 64 B. It is confirmed by the absence of eviction (`Snapshot` =
  completed keys). In arm I the counter is directly visible as the 340-entry plateau.
- **U (physical)** comes from three sources:
  - live class histograms at milestones: `PaxosState$Snapshot`, `PaxosState$Key`, `PaxosState`,
    `PreHashedDecoratedKey`, `[B` bytes, `java.nio.HeapByteBuffer`, `Total`;
  - the system.paxos memtable on-heap size from `tablestats`, subtracted;
  - the OOM heap dump: `bigarrays.py <dump> 61440` (count, bytes and reachability of `byte[61440]`) and
    `retainers.py <dump> byte 61440 8` (the referrer chain to `RECENT`), copied from B11's harness
    (`../ExecuteMessage_literal_1000--traced-render-outside-inflight/harness/`).
- **Timeline:** the 2 s `GC.heap_info`/`RssAnon` series and `gc.log` (heap after each GC, pause shares for the
  service-loss criterion).
- **Load:** client per-second completions and errors, and the `CASRead`/`Read` and `CasPrepare`/`CasPropose` counts
  (actual work, not client threads).

### 2.8 Controls and intervention

- **Matched control C (V2, ≥ 3 runs):** the same build, heap, key bytes, key count, connections and client, with
  consistency `ONE` instead of `SERIAL`. The request path, key decoding and read are the same. Only the Paxos round (and
  hence `RECENT`) is absent. The payload alone is predicted to stay near the baseline.
- **Intervention I (V4, ≥ 3 runs):** a separate build that only makes the weigher charge the key bytes
  (`harness/iv.patch`; save the exact diff):

  ```diff
  --- a/src/java/org/apache/cassandra/service/paxos/PaxosState.java
  +++ b/src/java/org/apache/cassandra/service/paxos/PaxosState.java
  @@ -74 +74 @@
  -                                                            .<Key, Snapshot>weigher((k, v) -> Ints.saturatedCast((v.accepted != null ? v.accepted.update.unsharedHeapSize() : 0L) + v.committed.update.unsharedHeapSize()))
  +                                                            .<Key, Snapshot>weigher((k, v) -> Ints.saturatedCast((v.accepted != null ? v.accepted.update.unsharedHeapSize() : 0L) + v.committed.update.unsharedHeapSize() + k.partitionKey.getKey().remaining()))
  ```

  The patch keeps the cap and the workload (the same `system.paxos` writes, memtables and flushes as T) and restores only
  the omitted accounting. It does not use `ObjectSizes.sizeOnHeapOf`, which asserts on read-only buffers. Stage 2
  writes it with the exact whitespace of line 74 (`git diff` must show one changed line). The original failure must
  reproduce on the unmodified base build (arm T).
- **Fallback intervention**, only if the iv build fails: base build with `paxos_cache_size: 0MiB` appended to a copy of the
  yaml (a constraint change in an intervention arm, allowed by V6). `RECENT` keeps nothing (stage 4 showed `0MiB` keeps 0
  entries and LWTs still apply). Predicted: alive, `Snapshot` ≈ 0. This removes the consumer and is weaker attribution
  than the patch. Label it as the fallback.

### 2.9 Disk, time and stopping budget

- **Disk per run** (key bytes on disk ≈ 4 K per SERIAL key: the `system.paxos` Data row key and proposal blob, the
  Index.db key, and the uncommitted-tracker file, plus up to 2 GB of commit log and compaction slack):
  - T ≈ 30,000 × 240 KB ≈ 7 GB + 3 GB;
  - I ≈ 50,000 × 240 KB ≈ 12 GB + 3 GB;
  - B4 ≈ 70,000 × 240 KB ≈ 17 GB + 3 GB;
  - C writes nothing to `system.paxos`;
  - D4 ≈ 200,000 × 17 KB ≈ 3.4 GB; M < 1 GB; D16 ≈ 110,000 × 66 KB ≈ 7 GB.
  - Heap dumps go to `/dev/shm/b12/<run>/` (RAM-backed, 32 G).
  - Wipe `<tree>/data` after every run.
  - After analysing a dump (`hprof_oome_thread.py`, `bigarrays.py`, `retainers.py`; outputs to `$R` and `logs/`),
    delete it. Keep at most the T-1 dump, moved to `/mydata/s4/b12/runs/T-1/` only if `/mydata` keeps ≥ 10 G free.
  - B4 starts only with ≥ 22 G free.
- **Stopping budget per run:** load ends at the first of these: daemon death, N_max issued and drained, or **15 min** of
  load. Then a 60 s hold if alive. No escalation after an OOM. No arm is repeated beyond its planned count, except to
  replace an invalid run (≤ 1 replacement per arm).
- **Wall-time plan** (deadline 07:30 America/New_York on 2026-11-18; stage 2 assumed to start ≈ 03:45). A run is ≈ 2 min
  start + ≤ 4 min load + ≈ 2 min dump/stop/wipe ≈ 8 min (B4 ≈ 14 min).

| Step | Planned duration | Must be done by (EST) |
|---|---|---|
| Node check, copies, iv build, harness, shakedown | 35 min | 04:25 (gate A: if not, stop and file `retry`) |
| T × 3 | 25 min | 04:50 |
| C × 3 | 20 min | 05:10 |
| I × 3 | 25 min | 05:40 (gate B: if T×3, C×3, I×3 not done, skip arms 4–7) |
| B4 × 1 | 15 min | 06:00 |
| D4 × 1, M × 1 | 20 min | 06:20 |
| B4 × 2 more, then D16 (only while a run can finish by 06:55) | ≤ 35 min | 06:55 |
| Dump analyses, §3/§4, write-backs, cleanup | 30 min | 07:25 |

  No new run starts after 06:45. Priority order if time is short: 0 → 1 → 2 → 3 → 4 (one run) → 5 → 6 → 4 (repeats) → 7.

### 2.10 Cleanup and what may stay

Stop every daemon, client and monitor started (by PID; `pgrep -f CassandraDaemon` must be empty at the end), stop the
`b12-*` scopes, run `disable-linger`, wipe `/dev/shm/b12/`, and wipe the trees' `data/`. Keep `/mydata/s4/b12/{cassandra-base,cassandra-iv,harness,runs}`
(logs; at most one dump) and record the size. Do not touch B11's or other cases' directories. Small excerpts go to
`logs/` in this folder (one file per run, plus `dump-analyses.txt`). The harness goes in `harness/`.

`sha256 of §1–§2 at freeze: 32e503705615ee8ee49e9a70083a5e97feb66af84c5e1aff2e97e626ab286301` (sha256sum of lines from `## 1. Candidate` through the blank line before this one, UTF-8, LF) · amendments after the freeze: none at freeze time; stage 2 added one (work directory path, §3.0).

## 3. Runs (stage 2)

Stage 2 was run by a fresh OOM-agent session (Claude Opus 5.5, workflow subagent) on 2026-11-18, 03:15–05:30 America/New_York
(the node clock is MST, EST − 2 h; Cassandra's `system.log`/stdout stamps are UTC).

### 3.0 Freeze check, node, amendments

- **Freeze hash:** `sha256sum` of the lines from `## 1. Candidate` through the blank line before the hash line =
  `32e50370…ab286301`, equal to the recorded value. §1–§2 were not edited.
- **Node:** `ms0611` (node3.jason92-326377, Utah m400), **aarch64**, 8 cores, 62 GiB RAM, Ubuntu 22.04, kernel 5.15.0, cgroup v2,
  OpenJDK 11.0.33, Ant 1.10.12, Python 3.10.12. At 03:16 EST: no `java` / `CassandraDaemon` running, `/mydata` 27 G free,
  `/dev/shm` 32 G free. B11's `/mydata/s4/b11-w1/` was only read (its `cassandra-base` copied); nothing under it was changed.
- **Builds:** `cassandra-base` = `cp -a /mydata/s4/b11-w1/cassandra-base`, then `data/` and `logs/` removed in the copy;
  `git describe --tags` = `cassandra-5.0.9`, `git status` clean, `conf/cassandra.yaml` md5 `714ee9bf58b3bc1710377ac16bcbba03`,
  `build/apache-cassandra-5.0.9-SNAPSHOT.jar` present. `cassandra-iv` = copy of base + [`harness/iv.patch`](harness/iv.patch)
  (exactly one changed line, line 74, the weigher adds `k.partitionKey.getKey().remaining()`), `PaxosState*.class` removed,
  `ant jar` (BUILD SUCCESSFUL, 36 s). Check: `javap -p -c … PaxosState | grep -c ByteBuffer.remaining` = 0 (base), 1 (iv).
- **Resolved JVM values** (`jcmd VM.flags`, every run): `MaxHeapSize` 2,147,483,648 (2 GiB arms) / 4,294,967,296 (B4),
  G1, **`MaxDirectMemorySize` = 16,642,998,272 B = 15,872 MiB** (from `cassandra-env.sh`, ¼ RAM capped), `-XX:OnOutOfMemoryError=kill -9 %p`,
  `-XX:+HeapDumpOnOutOfMemoryError`. Every daemon ran in `systemd-run --user --scope -p MemorySwapMax=0` (no MemoryMax).
- **Settings read-back** (`system_views.settings`, every run, e.g. [`logs/S0.txt`](logs/S0.txt)): `paxos_cache_size` = null (auto),
  `paxos_variant` v1, `paxos_state_purging` legacy, `paxos_repair_enabled` true, `memtable_heap_space` 512MiB (1024MiB at 4 GiB),
  `memtable_allocation_type` heap_buffers, `memtable_cleanup_threshold` 0.333, `native_transport_max_request_data_in_flight`
  214,748,364 B (heap/10), per IP 53,687,091 B, `key_cache_size` 100MiB, `counter_cache_size` 50MiB, `commitlog_total_space` 8192MiB.
  The resolved `paxos_cache_size` is not exported; it is confirmed by the plateaus: 163,840 entries of 128 B (D4, M) = 20 MiB, and
  340 = ⌊20 MiB / 61,568 B⌋ in arm I.
- **Amendment 1 (2026-11-18 03:17 EST, before any reading; environment/path only).** The work directory is
  `/mydata/s4/b12-w2/` instead of `/mydata/s4/b12/`, and heap dumps go to `/dev/shm/b12-w2/<run>/`. Reason: the stage-2 task
  named that directory. Nothing else changes.
- **Instrument details (not design changes):** (a) at each milestone the `system.paxos` memtable on-heap size is read both from
  `nodetool tablestats` and from the table metrics `MemtableOnHeapDataSize` / `AllMemtablesOnHeapDataSize` (via `nodetool sjk mx`);
  the slope uses `AllMemtablesOnHeapDataSize`. (b) The monitor's 10-s metric loop makes four sequential `nodetool sjk mx` calls,
  then sleeps 10 s, so the effective period is ≈ 20–25 s (the same in every arm). (c) `retainers.py` follows at most three
  referrers per object per level (as in B11).
- **Harness defect (fixed after the shakedown, before run 1):** the client labelled a normal N_max end as `all-threads-ended`.
  It was fixed for the path where threads are still alive; a second exit path still prints that label when every thread has
  already left at N_max (I runs). Those ends are N_max ends (`issued=50000`, `out=0`). No reading depends on the label.
- **Unexpected reading (protection map):** the map expected the key cache to stay empty. It fills slowly with `system.paxos`
  keys (`KeyCacheKey` → `byte[61440]`): 341–357 entries (≈ 21 MiB) at the T OOMs, 1,705 entries (≈ 100 MiB, about its 100 MiB cap)
  at the end of the I runs. It is a separate, capped domain; it is counted where it matters below (I criterion 3).

### 3.1 Harness and run order

[`harness/`](harness/): `client.py` (raw native protocol v4, 32 closed-loop connections, keys = 8-byte index ‖ fixed pad from
`random.Random(12)`, consistency SERIAL or ONE, milestones), `run.sh` (preflight, start in the scope, read-back, DDL, `histo-0`,
monitor, milestone service, stop, logs, `summarize.py`, wipe `data/`), `monitor.sh`, `summarize.py`, `series.sh` with
`spec1.txt` (arms 0–3) and `spec2.txt` (arms 4–7 in the frozen priority order), `excerpt.sh`, `analyze.sh`, the dump tools
`hprof_oome_thread.py`, `bigarrays.py`, `retainers.py` (copied from B11; `bigarrays.py` tail made generic), `iv.patch`.
One measured daemon at a time; the client runs on the same node (as designed). Dump analyses ran between series, with no daemon running.

| Time (EST) | Run(s) |
|---|---|
| 03:20–03:23 | S0 shakedown |
| 03:24–04:34 | series 1: T-1, T-2, T-3, C-1, C-2, C-3, I-1, I-2, I-3 (gate A met at 03:24, gate B at 04:34) |
| 04:34–04:40 | dump analyses T-1…T-3 (then T-2, T-3 dumps deleted) |
| 04:40–05:21 | series 2: B4-1, D4-1, M-1, B4-2, B4-3, D16-1 |
| 05:21–05:26 | dump analyses B4-1…B4-3, D16-1; cleanup 05:26–05:27 |

### 3.2 Shakedown (arm 0, S0, not a reading)

All checks passed ([`logs/S0.txt`](logs/S0.txt)): read-back v1 / null; 2,000 / 2,000 reads OK, 0 errors; `CASRead` 2,000,
`b12.t` `CasPrepareLatency` 2,000 and `CasProposeLatency` 2,000 (the v1 path ran); `histo-end` − `histo-0`: `PaxosState$Snapshot`
+2,000, `PaxosState$Key` +2,000, `[B` +194.7 MB (≥ 2,000 × 61,456 B = 122.9 MB); `PaxosState` (ACTIVE) 0; throughput ≈ 250–330
reads/s while loading (≥ 30, no re-plan).

### 3.3 Runs

N\* = keys issued before the daemon died (completed OK + errored); the errors are `0x1200` read timeouts plus the 32 connection
resets at the kill. "Snap" = live `PaxosState$Snapshot` count at the last milestone before the end. Heap = live `Total` from
`GC.class_histogram`. Logs: [`logs/<run>.txt`](logs/); full logs `/mydata/s4/b12-w2/runs/<run>/` on ms0611.

| Run | Build | Heap | K (B) | CL | Endpoint | N\* issued (OK / err) | Snap at last milestone | Notes |
|---|---|---|---|---|---|---|---|---|
| T-1 | base | 2G | 61,440 | SERIAL | **heap OOM** (`Java heap space`, dump, `kill -9`) | 26,597 (25,973 / 624) | 24,000 at 24,000 drained | load 138 s |
| T-2 | base | 2G | 61,440 | SERIAL | **heap OOM** | 26,360 (25,816 / 544) | 24,000 at 24,000 | load 132 s |
| T-3 | base | 2G | 61,440 | SERIAL | **heap OOM** | 26,425 (25,963 / 462) | 23,998 at 24,000 | load 127 s |
| C-1 | base | 2G | 61,440 | ONE | alive at 50,000; stopped | 50,000 (50,000 / 0) | 0 | `CASRead` 0 |
| C-2 | base | 2G | 61,440 | ONE | alive | 50,000 (50,000 / 0) | 0 | |
| C-3 | base | 2G | 61,440 | ONE | alive | 50,000 (50,000 / 0) | 0 | |
| I-1 | iv | 2G | 61,440 | SERIAL | alive at 50,000; stopped | 50,000 (49,116 / 884) | 340 | `CasPrepare` 50,460 |
| I-2 | iv | 2G | 61,440 | SERIAL | alive | 50,000 (49,364 / 636) | 340 | `CasPrepare` 50,301 |
| I-3 | iv | 2G | 61,440 | SERIAL | alive | 50,000 (49,363 / 637) | 342 | `CasPrepare` 50,362 |
| B4-1 | base | 4G | 61,440 | SERIAL | **heap OOM** | 47,438 (46,404 / 1,034) | 40,000 at 40,000 | load 208 s |
| D4-1 | base | 2G | 4,096 | SERIAL | alive at 200,000 | 200,000 (200,000 / 0) | 163,840 (from 175,000 on) | |
| M-1 | base | 2G | 16 | SERIAL | alive at 200,000 | 200,000 (200,000 / 0) | 163,840 (from 175,000 on) | |
| B4-2 | base | 4G | 61,440 | SERIAL | **heap OOM** | 47,211 (46,127 / 1,084) | 40,000 at 40,000 | load 205 s |
| B4-3 | base | 4G | 61,440 | SERIAL | **heap OOM** | 47,564 (46,472 / 1,092) | 40,000 at 40,000 | load 210 s |
| D16-1 | base | 2G | 16,384 | SERIAL | **heap OOM** | 93,496 (92,965 / 531) | 80,000 at 80,000 | STW 92 % of the last 60 s before the OOM |

**Milestone series, T and I** (live `Total` MB / `AllMemtablesOnHeapDataSize` MB / Snapshot), from `summary.txt`:

| ms (drained) | T-1 | T-2 | T-3 | I-1 | I-2 | I-3 |
|---|---|---|---|---|---|---|
| 0 | 46.3 / 0 / 0 | 46.3 / 0 / 0 | 46.3 / 0 / 0 | 46.3 / 0 / 0 | 46.3 / 0 / 0 | 46.3 / 0 / 0 |
| 4,000 | 811.8 / 136.8 / 4,000 | 813.9 / 137.2 / 4,000 | 813.0 / 137.7 / 4,000 | 586.1 / 137.8 / 340 | 586.3 / 137.6 / 340 | 587.5 / 138.2 / 340 |
| 8,000 | 844.7 / 87.6 / 8,000 | 843.4 / 88.2 / 8,000 | 832.7 / 90.3 / 8,000 | 360.3 / 90.6 / 340 | 360.3 / 91.9 / 340 | 359.6 / 90.8 / 340 |
| 12,000 | 1,034.6 / 35.3 / 12,000 | 1,036.1 / 38.5 / 12,000 | 1,035.4 / 42.7 / 12,000 | 322.5 / 41.4 / 340 | 315.2 / 42.0 / 340 | 502.5 / 41.6 / 340 |
| 16,000 | 1,603.2 / 173.3 / 16,000 | 1,607.4 / 176.4 / 16,000 | 1,613.2 / 0.0 / 16,015 | 649.2 / 178.6 / 605 | 1,429.3 / 0.0 / 1,982 | 641.8 / 177.6 / 353 |
| 20,000 | 1,636.7 / 124.9 / 20,000 | 1,629.2 / 129.1 / 20,000 | 1,820.0 / 137.4 / 20,000 | 408.5 / 128.2 / 340 | 602.9 / 137.8 / 340 | 414.1 / 129.5 / 340 |
| 24,000 | 1,821.9 / 50.4 / 24,000 | 1,823.5 / 69.6 / 24,000 | 1,837.9 / 77.0 / 23,998 | 373.8 / 79.4 / 340 | 386.4 / 88.5 / 446 | 557.9 / 82.5 / 340 |
| 28,000–48,000 | (OOM) | (OOM) | (OOM) | 331–728 / 29–178 / 340–644 | 446–1,924 / 10.5–177 / 340–986 | 427–1,239 / 2.5–141 / 340–348 |
| end (+60 s) | — | — | — | 316.3 / 111.6 / 340 | 312.1 / 108.0 / 340 | 326.4 / 120.6 / 340 |

In the I runs a Snapshot count above 340 appears when Paxos operations are still active on the server at the milestone
(`PaxosState` ACTIVE 9–521 at those points: client requests timed out, server work continued), once (I-2 at 24,000: 446
Snapshots, 399 Keys, ACTIVE 0) as eviction lag, and falls back to 340 at the next milestone in every case. The highest I live heap, 1,923.5 MB (I-2 at 36,000), held 986 Snapshots and 51 live `SlabAllocator`s
(26 `system.paxos` sstables, 184 ACTIVE): a memtable/flush backlog transient, not `RECENT`; it passed without an OOM.

### 3.4 Readings against the frozen predictions

**T (×3)** — predicted heap OOM at N\* ∈ [20,000, 34,000]:
- Endpoint: `java.lang.OutOfMemoryError: Java heap space` in **3/3**, each with a heap dump and `kill -9` by `OnOutOfMemoryError`. **Met.**
- N\* = 26,597 / 26,360 / 26,425 issued (25,973 / 25,816 / 25,963 OK). **In the band** (centre predicted 28,000).
- Snapshot count = drained keys at every milestone (4,000 … 24,000; T-3: 16,015 with 26 ACTIVE, 23,998 at 24,000): no eviction. **Met.**
- Slope ΔTotal/ΔSnapshot (Total − `AllMemtablesOnHeapDataSize`), first → last milestone: **54,826 / 53,859 / 54,280 B: below
  the band [61,700, 62,700]. Not met as frozen.** Cause: the 4,000-key milestone carries ≈ 170 MB more non-`RECENT` heap than the
  later ones (flushed-memtable / sstable transient that the memtable metric does not count), which lowers the first point. From
  the 8,000-key milestone to the last, the slope is 63,400 / 62,419 / 63,664 B, and the dump measures the key part directly (§3.5).
  Per the frozen "readings → meaning" table this is the "arithmetic off, dump as predicted" case.
- Snapshot × 62,000 B at the last milestone = 24,000 × 62,000 = 1.49 GB = 69 % of the heap (≥ 60 %). **Met.**
- Dump (V5): reachable `byte[61440]` = 27,086 / 26,832 / 26,896 (≥ 0.95 × 24,000), total 1,595 / 1,573 / 1,577 MiB (≥ 1.2 GiB);
  referrer chain `byte[] ← HeapByteBuffer.hb ← PreHashedDecoratedKey.key ← PaxosState$Key.partitionKey ← Caffeine PSMW.key`
  (the `RECENT` node) for 26,524 / 26,322 / 26,333 arrays. **Met.**
- `PaxosState` (ACTIVE) ≤ 64 at every histogram (max 26). **Met.**
- GC: STW share over the last 60 s of the GC log 48–49 %, 161–192 full GCs, heap after GC ≈ 2,024–2,039 MiB at the end.

**C (×3)** — predicted alive:
- Alive at 50,000 reads in **3/3**, 0 errors. **Met.**
- Snapshot 0 and `CASRead` 0 in every run. **Met.**
- `histo-end` Total 58.3 / 57.5 / 58.0 MB ≤ 46.3 + 150 MB. **Met.**
- Max heap after a GC: 80 / 73 / 80 MiB (≤ 4 % of the heap; ≤ 30 %). **Met.**

**I (×3)** — predicted alive with a plateau of 340:
- Alive at 50,000 reads in **3/3**. **Met.**
- Snapshot = **340** at every quiet milestone from the first on (exactly ⌊20 × 2^20 / 61,568⌋), transiently higher only with
  ACTIVE operations (above). **Met as a plateau**; the frozen "± 1, + 32 in flight" allowance is exceeded at 5 of 36 milestones
  (I-1 at 16,000 and 36,000; I-2 at 16,000, 24,000 and 36,000; 446–1,982 Snapshots), each back to 340 at the next milestone and
  at the end of every run.
- `histo-end` Total ≤ `histo-0` + memtable + 150 MB: 316.3 vs 307.9, 312.1 vs 304.3, 326.4 vs 316.9 MB. **Missed by 8.4 / 7.8 /
  9.5 MB.** The 150 MB allowance did not include the key cache, which held 1,705 entries of `byte[61440]` ≈ 100 MiB at the end
  of every I run (§3.0). `RECENT` itself held 340 × ≈ 62 KB ≈ 21 MB.
- Same `system.paxos` write load: `CasPrepare` 50,460 / 50,301 / 50,362 ≥ 50,000. **Met.** Load rate over the first ~30 s:
  127–128 reads/s (T: 126–127 reads/s).

**B4** — predicted heap OOM at N\* ∈ [45,000, 70,000], Snapshot = completed:
- B4-1: heap OOM at 47,438 issued (46,404 OK); Snapshot = drained at every milestone (8,000 … 40,000). **Met.**
- B4-2: heap OOM at 47,211 (46,127 OK); B4-3: heap OOM at 47,564 (46,472 OK); Snapshot = drained at every milestone in both.
  **B4 = 3/3 heap OOMs at 4 GiB**, all in the band. Dumps: `RECENT` keys 2,763–2,782 MiB = 68.0–68.5 % of 4,036–4,090 MiB (§3.5).
  The frozen upward search stops at 4 GiB (arm 4); 8 GiB was not in the design and was not run.

**D4** — predicted alive, plateau 163,840, ΔTotal ≈ +0.77 GB (± 15 %), U/C ≈ 37:
- Alive at 200,000; Snapshot 163,840 exactly from the 175,000 milestone to the end. **Met.**
- At the end: Total 859.8 − memtable 36.5 − `histo-0` 46.3 = **777 MB** (+0.77 GB predicted). U/C = 777 MB / 20.97 MB ≈ **37**. **Met.**
  Slope 25,000 → 150,000: 4,654 B per entry (predicted 4,112 + ≈ 600).

**M** — predicted alive, plateau 163,840, ΔTotal ≈ 100 MB (± 25 %), U/C ≈ 4.5–5.5:
- Alive at 200,000; Snapshot 163,840 from 175,000 on. **Met.**
- At the end: Total 171.9 − memtable 15.0 − 46.3 = **110.6 MB**, U/C ≈ **5.3**. **Met.** This confirms OC-14's literal
  "4–7×" for 16-byte keys (≈ 675 B held per 128 B of weight).

**D16** — predicted heap OOM at N\* ∈ [90,000, 120,000]:
- D16-1: **heap OOM** at 93,496 issued (92,965 OK); predicted [90,000, 120,000]. **Met.** Snapshot = drained at every milestone
  (16,000 … 80,000; 15,955 with 32 ACTIVE at the first). The last 60 s before the OOM were 92 % stop-the-world GC.
  Dump: 93,451 `byte[16384]` keys in `RECENT` = 1,461.6 MiB = 70.7 % of the heap (§3.5). So a 16 KiB key is enough at 2 GiB
  (by the §2.3 arithmetic the threshold at a ≤ 5 GiB heap is K ≳ 10 KiB; the 4 KiB dial stays alive).

### 3.5 Dump analyses (V5)

From [`logs/dump-analyses.txt`](logs/dump-analyses.txt) (`hprof_oome_thread.py`, `bigarrays.py <dump> 61440`,
`retainers.py <dump> byte 61440 8`):

| Run | Dump (shallow) | `byte[61440]` count / live / MiB / % of dump | In `RECENT` (`PaxosState$Key` chain) | Next pool | Key cache keys | OOM-throwing thread |
|---|---|---|---|---|---|---|
| T-1 | 2,048.1 MiB | 27,212 / 27,086 / 1,594.9 / 77.9 % | **26,524 = 1,554.5 MiB = 75.9 %** | 362 × `byte[1048576]` = 362 MiB (memtable slab regions) | 357 | `MonitoringTask.logSlowOperations` → `DecoratedKey.toCQLString` → `Hex.bytesToHex` |
| T-2 | 2,032.1 MiB | 26,832 / 26,832 / 1,572.6 / 77.4 % | **26,322 = 1,542.7 MiB = 75.9 %** | 350 MiB slab regions | 340 | read stage, `BigTableReader.getRowIndexEntry` → `ByteBufferUtil.read` |
| T-3 | 2,039.7 MiB | 26,905 / 26,896 / 1,576.9 / 77.3 % | **26,333 = 1,543.4 MiB = 75.7 %** | 365 MiB slab regions | 343 | `MonitoringTask` → `DecoratedKey.toCQLString` → `String.format` |
| B4-1 | 4,060.9 MiB | 47,891 / 47,891 / 2,806.8 / 69.1 % | **47,390 = 2,777.5 MiB = 68.4 %** | 1,104 × 1 MiB = 1,104 MiB | 294 | logback `PatternLayout` → `StringBuilder.append` |
| B4-2 | 4,035.7 MiB | 47,715 / 47,715 / 2,796.5 / 69.3 % | **47,153 = 2,763.6 MiB = 68.5 %** | 1,083 MiB | 337 | logback `PatternLayout` → `StringBuilder.append` |
| B4-3 | 4,090.1 MiB | 48,444 / 48,053 / 2,839.3 / 69.4 % | **47,469 = 2,782.1 MiB = 68.0 %** | 1,120 MiB | 340 | `Mutation$MutationSerializer.serialization` → `DataOutputBuffer.toByteArray` |
| D16-1 | 2,066.3 MiB | `byte[16384]`: 93,945 / 93,930 / 1,469.3 / 71.1 % | **93,451 × 16,400 B = 1,461.6 MiB = 70.7 %** | 441 MiB | 326 | `SEPWorker.selfAssign` |

Level 4 of every chain is `com.github.benmanes.caffeine.cache.PSMW.key` for the same count as `PaxosState$Key.partitionKey`
at level 3 (26,524 / 26,322 / 26,333 / 47,390 / 47,153 / 47,468 / 93,451). `PSMW` is Caffeine's strong-key, strong-value,
maximum-weight node, the node class of `RECENT`; no other cache in the process is keyed by `PaxosState$Key`. U/C for the keys alone
at the OOM: 77–78× (2 GiB, C = 20 MiB), 69–70× (4 GiB, C = 40 MiB), 73× (D16). K at the OOM = Snapshot count × 128 B = 3.4 MB
(2 GiB), 6.1 MB (4 GiB), 12.0 MB (D16), all ≤ C. At 4 GiB the 1 MiB arrays (1,083–1,120 MiB; memtable slab regions plus
retired regions not yet freed) are near the 1,024 MiB memtable pool; that domain is not part of the claim.

The throwing threads differ (slow-query logging of a 60 KiB key, an sstable index read): they are the last allocations into a
heap that `RECENT` had filled. At level 3 of the referrer chains each array is also referenced twice by
`PartitionUpdate.partitionKey` (52,535 in T-1): the two empty updates of the same `Snapshot` share the entry's `DecoratedKey`.
The memtable slabs (350–365 MiB) are within their 512 MiB contract.

### 3.6 Logs and what is left

- **Committed excerpts** ([`logs/`](logs/)): one file per run (`S0`, `T-1…3`, `C-1…3`, `I-1…3`, `B4-1…3`, `D4-1`, `M-1`,
  `D16-1`: summary, driver, errors, metrics, milestone memtable/key-cache lines, OOM lines, resolved flags, OOM thread),
  `dump-analyses.txt` (all seven dumps), `series.log`.
- **On ms0611** (`/mydata/s4/b12-w2/`, 4.0 G): `cassandra-base` (507 M, `data/` wiped), `cassandra-iv` (564 M, `data/` wiped),
  `harness/` (76 K), `runs/` (2.9 G: full logs, histograms, `gc.log*`, `system.log`, `debug.log` for every run, plus **one dump**
  `runs/T-1/cassandra-1794990241-pid131458.hprof`, 2.1 G; /mydata kept 23 G free), `build-iv.log`, `series.log`,
  `no-new-run-after`. The other six dumps were deleted after analysis; `/dev/shm/b12-w2` removed.
- **Stopped:** every daemon died by `kill -9` (OOM) or was stopped by the driver; monitors, clients, series and analysis
  processes have exited; `pgrep -af CassandraDaemon` is empty; no `b12-*` scope is active; `loginctl disable-linger jason92` done
  (Linger=no). B11's `/mydata/s4/b11-w1/` is unchanged.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`** (bypass, accounting omission), aarch64 (ms0611).

**Result phrase.** At a 2 GiB heap with every capacity setting at its Cassandra 5.0.9 default, v1 `SERIAL` reads on distinct,
absent partitions with a 60 KiB `blob` key end in `java.lang.OutOfMemoryError: Java heap space` in 3/3 runs after ≈ 26,400
reads, because the Paxos state cache `PaxosState.RECENT` keeps every key while its weigher charges 128 B per entry. The same
holds at 4 GiB (3/3, ≈ 47,400 reads) and with 16 KiB keys at 2 GiB (1/1, ≈ 93,500 reads).

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 Repetition | endpoint in ≥ 3 clean runs | T-1, T-2, T-3: heap OOM 3/3 at 26,360–26,597 issued keys (2 GiB); also B4-1…3 3/3 (4 GiB) | yes |
| V2 Matched control | nearest surviving control ≥ 3 runs, same build/budget | C-1…3 (same build, heap, key bytes, key count, connections; consistency ONE): alive 3/3, Snapshot 0, live heap ≤ 58 MB | yes |
| V3 Measurement | U independent of K | U: live histograms (Snapshot = keys, 4,000…24,000; slope 62.4–63.7 KB/entry from 8,000 on) and seven dumps (`byte[K]` in the `PaxosState$Key ← PSMW` chain = 68–76 % of the heap). K = Snapshot × 128 B = 3.4 MB ≤ C = 20 MiB; the 128 B weight and the 20 MiB cap confirmed by the plateaus of D4/M (163,840) and I (340) | yes |
| V4 Intervention | removes the endpoint ≥ 3 runs at matched load | I-1…3 (`iv.patch`, the weigher also charges the key bytes; same writes, `CasPrepare` ≥ 50,000, 127–128 reads/s as T): alive 3/3, plateau 340; the original failure reproduces on the unmodified build (T) | yes |
| V5 Initiating failure | first error + histogram/dump at failure | the OOM-throwing thread from each dump (§3.5; the last allocation varies: slow-query key rendering, sstable index read, logging, mutation serialization), the `Java heap space` line in stdout, and the dump attributing 76 % (2 GiB) of the heap to `RECENT` keys | yes |
| V6 Default constraints | every constraint at its shipped default, resolved | `paxos_cache_size` unset → 20 MiB (40 MiB at 4 GiB), memtable 512 MiB heap_buffers, native in-flight heap/10, key cache 100 MiB, `paxos_variant` v1; shipped yaml (md5 `714ee9bf…`) unmodified; only the I arm differs (patched weigher) | yes |
| V7 Acceptable budget | ≥ 512 MiB heap/direct; search upward | 2 GiB heap (the ideal budget), direct 15,872 MiB as resolved, no container limit; largest failing budget tested **4 GiB, 3/3**; 8 GiB was outside the frozen design | yes |

**Reason.** The `RECENT` weigher (`PaxosState.java:74`) charges only the two stored updates' `unsharedHeapSize()` (64 + 64 =
128 B for a v1 `SERIAL` read of an absent partition) and never the key, so the 20 MiB auto cap at a 2 GiB heap admits 163,840
entries, whatever the key size. With a legal 61,440 B key each entry holds ≈ 62–63 KB (≈ 490× its weight). The test arm kept every
key (Snapshot = completed keys at every milestone, no eviction) and died of `Java heap space` at 26,597 / 26,360 / 26,425 issued
keys, when the counter stood at ≈ 3.4 MB of its 20 MiB. The dumps attribute 1,543–1,555 MiB (75.7–75.9 % of the heap, 77–78× C)
to `byte[61440]` keys reached through `PaxosState$Key.partitionKey ← Caffeine PSMW.key`. The matched control (consistency ONE,
same payloads) stayed at ≤ 58 MB of live heap, and the intervention build (same load, the weigher also charges the key) held
`RECENT` at exactly 340 entries and survived 50,000 reads in 3/3. The 4 GiB budget fails the same way (3/3 at ≈ 47,400 keys,
68 % of the heap in `RECENT` keys), and so do 16 KiB keys at 2 GiB (93,496 keys). 4 KiB keys plateau at 163,840 entries
(≈ 777 MB, 37× C) and 16 B keys at ≈ 111 MB (5.3× C, OC-14's original "4–7×"), both alive.

**Classification.** Bypass, accounting omission: U > C with K ≤ C, per entry U/K ≈ 490 at K = 60 KiB. Interpretation: suspected
implementation defect, the CASSANDRA-4315 class (that fix made the key cache weigh key + value). The cache is not documented as
excluding keys: `paxos_cache_size` is not in the shipped `cassandra.yaml` at all (`Config.java:485`, default null = auto).
The other heap domains stayed within their contracts at the OOM (memtable slabs 350–365 MiB of 512 MiB; key cache ≈ 21 MiB of
100 MiB); they move the OOM point but are not needed for it, since `RECENT` alone would grow to ≈ 10 GB at this cap.

**Limits.**
- The failure needs large partition keys: legal (≤ 65,535 B, no guardrail in 5.0.9) but unusual. At 2 GiB the boundary is between
  4 KiB (alive, 37× C) and 16 KiB (OOM); the §2.3 arithmetic puts it near 10 KiB for heaps ≤ 5 GiB and ≈ H × 2.1 KiB above that
  (≈ 33 KiB at the 15.5 GiB auto heap). Small keys (16 B) give only the 5× overshoot of OC-14, about 111 MB.
- The workload is v1 `SERIAL` reads (the 5.0.9 default `paxos_variant`). LWT writes and the v2 path were not run.
- aarch64 only (ms0611), one node, client on the same node. Not pooled with x86 results.
- Frozen predictions missed, with cause: the T slope first → last milestone (53.9–54.8 KB, band 61.7–62.7 KB) is pulled down by
  a non-`RECENT` transient at the first milestone (62.4–63.7 KB from the second); the I arm's end-heap bound (+150 MB) was
  exceeded by 7.8–9.5 MB, because the key cache filled to its ≈ 100 MiB cap with `system.paxos` keys, which the protection map
  did not expect. Neither changes the attribution.
- The I arm also showed a transient non-`RECENT` live heap of up to 1.92 GB (I-2, memtable/flush backlog during a stall), without
  an OOM in 3/3. This workload therefore has a second, transient consumer near a 2 GiB heap. It is not what fills the heap in T (the dumps).
- The intervention charges the key's `remaining()` bytes only (not the ≈ 600 B of shells); it is an attribution patch, not a
  proposed fix.

**Retry:** not applicable. **New clue pattern:** none needed; the shape is CP-1 ("counted unit ≠ held memory": a cache weigher that
omits the key, as in CASSANDRA-4315 and B7).
