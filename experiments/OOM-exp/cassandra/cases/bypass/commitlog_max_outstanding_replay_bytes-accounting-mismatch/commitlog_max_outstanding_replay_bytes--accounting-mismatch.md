# B8 — commit-log replay bound counts serialized bytes; at defaults the replayed tail is capped by the memtable pool

IDs used here: **B8** = campaign bypass investigation 8 (B = bypass); **N4** / **N3** = new leads 4 / 3 from
the capacity-enforcement bypass notes (N = new lead; N3 = cached serialized copy per mutation, measured as a
term); **B6** = bypass case 6 (internode queues), whose tiny-cell payload and client are reused; **S2** =
combo case 2 (local-write backlog); **L7** = OOM lead 7 (L = pattern-leads list).

**Direction:** bypass · accounting mismatch (+ exempt path). **Lead source:** `source: N4` (bypass leads §3;
pattern-leads L7). **Regime:** default capacities. **Source:** Cassandra 5.0.9, the ms0625 smoke-test build
(`/mydata/oom-smoke/cassandra-run1`, from `systems/cassandra/source/` at repo `01bed5a7`) copied to
`/mydata/b8/cassandra`, unmodified (Byteman agents only in labelled diagnostic arms). **Node:** `ms0625`
(Utah m400, **aarch64**, 8 cores, 62 GiB, kernel 5.15, cgroup v2; victim in a `systemd-run --user` scope with
`MemoryMax` = 2 × heap and `MemorySwapMax=0`; linger enabled). **Run:** B8 run 1, 2026-11-16 19:15–22:05 MST (35 arms).
**Design:** [`design/B8-design.md`](design/B8-design.md), written before readings; amendments 1–2 dated
before the arms they add. **Statuses (researcher's review 2026-11-17: accepted as proposed; S is `verified-OOM ·
diagnostic`, the case stays in `bypass/`):**

| Condition | Status |
|---|---|
| **A** — defaults; tiny-cell map writes (≈ 10 / 64 / 256 KiB serialized) until the memtable pool is full, `kill -9`, restart at the same heap and container; 512 MiB–2 GiB | **`negative · deployment`**: replay started **10/10** (P64 at 2 GiB 3/3); 0 Full GCs during any replay at ≥ 1 GiB. The **runtime load** is the failing phase: heap OOM 2/2 at 512 MiB, after which replay started 2/2 |
| **X** — A + restore emulation (the table's sstables removed before restart, so the whole retained log replays: 3,344 P64 mutations ≈ 3 GiB of memtable charge) | **`negative · diagnostic`** (restore emulated): started **4/4** (2 GiB 3/3, 1 GiB 1/1); 1 live `Mutation` in every mid-replay histogram |
| **S** — X + a 10 s stall on every flush during the restart (Byteman, standing in for a data-disk stall), 1 GiB heap | **`verified-OOM · diagnostic`** (supporting deviations: sstables removed, injected flush stall): heap OOM in replay **3/3**; blob 0/3; replay count 64 0/3; 2 GiB starts (1/1), so the largest failing heap is 1 GiB |
| **L** — ledger: replay queue held at its bound (Byteman delay on every replay task), 2 and 8 GiB | measurement (`diagnostic`): **U ≈ 947 MiB vs K ≈ 63 MiB** (1,015 P64 mutations, 15.0×); blob 143 MiB (2.2×); count 64 → 76 MiB; node started 4/4 |

**Filing.** Researcher's review 2026-11-17: S accepted as a verified diagnostic condition, so the case stays in
`bypass/`. As filed: in `bypass/` because condition S meets V1–V7 as `verified-OOM · diagnostic` (protocol folder
rule). The deployment condition A, which answers the brief's hypothesis, is `negative`. If the researcher does
not accept S's two supporting deviations as a verified condition, the case belongs in `negatives/` as
`negative · deployment`.

## Summary

- **Conclusion:** the N4 accounting mismatch is real and measured: the replay bound charges a 5,900-cell map
  mutation its serialized ≈ 63.7 KiB, while the deserialized mutation holds ≈ 0.93 MiB (15.0×, including
  the N3 cached copy at 1.0× of the counted size). A queue at its bound (1,024 / 64 MiB) holds ≈ 0.95 GiB.
  But the hypothesis — replay of a tiny-cell log OOMs a node at an acceptable heap that served the same
  writes — is **refuted at defaults on this node**. Two things keep the queue from filling:
  (1) what is left to replay is what the memtable pool held at the kill: the memtable charge re-flushed during
  replay was 506–570 MiB at 2 GiB (pool 512 MiB) for every payload; (2) one reader thread deserializes
  ≈ 130–170 P64 mutations/s, and 32 appliers plus replay-time flushes keep up, even when the replay volume is
  6× the pool (X). The queue only fills when the appliers stall (S): then a 1 GiB node OOMs in replay
  **3/3** (blob 0/3, replay count 64 0/3) after serving the same writes at 1 GiB (degraded: 61–71 Full GCs
  in the load) and restarting cleanly without the stall; 2 GiB survives the stall at 70 % live.
- **Root cause of the remaining gap:** `CommitLogReplayer.handleMutation` counts serialized bytes, the
  committed form of CASSANDRA-8639 (which proposed `cell.unsharedHeapSize()`), so its bound admits
  ≈ 15× its nominal 64 MiB for tiny-cell data. At defaults it is not the binding control; runtime flushing
  and reader-bound replay are. It binds only if replay volume exceeds the pool *and* the apply side stalls.
- **Operational note:** at every tested heap the runtime write load was harder on the heap than its replay;
  at 512 MiB the load OOMed (S2 / B6 write-path picture) and the node then restarted without trouble.

## 1. Constraint, contract, protection map

| Field | Evidence |
|---|---|
| Control | `CommitLogReplayer.handleMutation` (`db/commitlog/CommitLogReplayer.java:513–531`): `pendingMutationBytes += size` (serialized entry size); future submitted to `Stage.MUTATION`; drains while `futures.size() > 1024` or `pendingMutationBytes > 64 MiB` (`config/CassandraRelevantProperties.java:114–115`, JVM properties `cassandra.commitlog_max_outstanding_replay_count` / `_bytes`), or the head future is done. |
| Contract | Not in `cassandra.yaml`; JVM properties named in bytes and count. CASSANDRA-8639 ("Can OOM on CL replay with dense mutations", Fixed 3.2) proposed bounding by `cell.unsharedHeapSize()`; the committed fix counts serialized size (64 KiB raised to 64 MiB in review). JIRA check in campaign-plan row B8 (2026-11-16); no open issue on the unit. Stage 4 (`capacity-enforcement-exp`, [`commitlog_max_outstanding_replay_bytes` result](../../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md)): the byte limit caps the backlog (true positive, caps), backlog heap ≈ 2 × L for 60 KB blobs; built with `memtable_cleanup_threshold: 0.99`, a 3 GiB load pool and `concurrent_writes: 2`. |
| Allocation / ownership | The reader (`main`) deserializes every entry after the global replay position (`CommitLogReader.readMutation`, `:417–478`, `DeserializationHelper.Flag.LOCAL` → `ArrayCell`s), validates it, then hands it over. `Mutation.serializer.deserialize` tees the input into a cached serialized copy for mutations < 1,000,000 B (`Mutation.java:493`, N3). The task (`MutationInitiator`, `:282–332`) drops tables already persisted (`shouldReplay`) and applies the rest with `writeCommitLog=false`. Entries already covered by sstables are also deserialized and queued; they are skipped only when their task runs. |
| Uncovered memory | Held vs counted per P64 mutation: 0.93 MiB vs 63.7 KiB (15.0×); blob 65,200 B: ≈ 2.2× (§3.4). |
| Other controls on the path | `memtable_heap_space` (heap/4) and cleanup threshold 1/3 cap what runtime leaves unflushed, i.e. what replay re-applies; replay-time flushes; `concurrent_writes` 32 appliers; one reader thread. |
| Budget | Java heap; container = 2 × heap, swap 0; direct memory auto (¼ RAM, capped by the container). |

C = 64 MiB serialized / 1,024 futures. K = live replay `Mutation`s × 63.7 KiB (serialized size, from B6's
calibration of 10.80 KiB per 1,000 entries; not re-measured). U = heap held by queued replay mutations
(`ArrayCell` + cell paths + their buffers + `byte[]`, from class histograms; GC-log live as the upper bound).

**Settings that decide what remains to replay** (all shipped defaults, V6): `commitlog_segment_size` 32 MiB;
`commitlog_total_space` default (8 GiB here); `commitlog_sync: periodic`, 10 s; `memtable_allocation_type:
heap_buffers`; `memtable_heap_space` heap/4; cleanup threshold 1/(1 + 2 flush writers); `concurrent_writes`
32; `num_tokens` 16. Load phase: same JVM and settings as the restart (no agent).

## 2. Verification design

- **Load** (`harness/arm.sh`; client `harness/B8Load.java` = B6's `B6Load` reduced to one node, keyspace
  `b8`, SimpleStrategy RF 1, CL ONE): `map<int,int>` with 930 / 5,900 / 23,700 entries (P10 / P64 / P256), or a
  65,200-byte blob (matched control); 16–256 in flight, 150 s, then `kill -9` while writes still arrive (write
  timeouts in every load show the pool was full: writers blocked on the memtable allocator).
- **Restart** at the same heap/container. Outcome: `Starting listening for CQL clients` (started), JVM death
  (heap OOM, dump via the shipped `-XX:+HeapDumpOnOutOfMemoryError`), or 15 min timeout. GC log summarized by
  `harness/gcsum.py` (service loss = ≥ 90 % STW over ≥ 60 s); `memory.current` per second (`memory.peak`
  absent on 5.15).
- **Tail:** `Log replay complete, N replayed mutations` plus the memtable charge of every flush of the `b8`
  table during replay (`harness/summ.py`).
- **X** (`harness/arm3.sh`, `DROP_SSTABLES=1`): the table's sstables are removed between kill and restart.
- **S** (X + `harness/flush-stall.btm`, 10 s at the start of every `b8` flush, loaded only for the restart).
- **L** (`harness/arm2.sh` + `harness/replay-delay.btm`, 1 s at the start of every replay task):
  `GC.class_histogram` at fixed times after the `Replaying` line.
- Per the brief, controls not run on A and X: same-log-smaller-volume and intervention (no failure to remove);
  upward heap search (2 GiB already starts with ≥ 70 % headroom).

## 3. Results

### 3.1 Condition A — defaults, restart at the same budget

| Run | Heap / container | Payload | Runtime load (acks; Full GCs; STW %; live after Full GC) | Replayed | Tail memtable charge | Restart | Replay: Full GCs; after-GC peak |
|---|---|---|---|---|---|---|---|
| cal1 (r1) | 2 / 4 GiB | P64 | 11,403; 23; 23 %; 684 MiB | 649 | 541 MiB | started, 43 s | 0; 414 MiB |
| p64-2g-r2 | 2 / 4 GiB | P64 | 12,595; 26; 25 %; 706 MiB | 649 | 541 MiB | started, 43 s | 0; 617 MiB |
| p64-2g-r3 | 2 / 4 GiB | P64 | 12,447; 26; 25 %; 695 MiB | 657 | 541 MiB | started, 41 s | 0; 628 MiB |
| p10-2g-r1 | 2 / 4 GiB | P10 | 88,822; 22; 23 %; 614 MiB | 3,595 | 516 MiB | started, 42 s | 0; 456 MiB |
| p256-2g-r1 | 2 / 4 GiB | P256 | 2,736; 25; 25 %; 696 MiB | 219 | 570 MiB | started, 38 s | 0; 399 MiB |
| blob64-2g-r1 | 2 / 4 GiB | blob | 89,629; 8; 2 %; 532 MiB | 8,268 | 514 MiB | started, 31 s | 0; 620 MiB |
| p64-1g-r1 | 1 / 2 GiB | P64 | 8,575; 62; 31 %; 477 MiB | 193 | 108 MiB | started, 46 s | 0; 172 MiB |
| p256-1g-r1 | 1 / 2 GiB | P256 | 2,270; 66; 35 %; 465 MiB | 150 | 283 MiB | started, 39 s | 0; 289 MiB |
| p64-512m-r1 | 512 MiB / 1 GiB | P64 | **heap OOM at t ≈ 98 s** (37 acks; 96 % STW, worst 60 s) | 216 | 157 MiB | started, 22 s | 0; 195 MiB |
| p256-512m-r1 | 512 MiB / 1 GiB | P256 | **heap OOM** (31 acks; ≈ 100 % STW, worst 60 s) | 113 | 246 MiB | started, 27 s | 1; 55 MiB after Full GC |

- Replay failed **0/10**, from 512 MiB to 2 GiB, for every payload. There is no failing heap ≥ 512 MiB.
- Tail ≈ pool: 506–570 MiB of memtable charge at 2 GiB (pool 512 MiB), whatever the payload, so the replay
  bound never meets more than one pool's worth: 649 P64 mutations (< 1,024), ≈ 40 MiB serialized (< 64 MiB).
- The 512 MiB runtime OOMs: dumps hold 2.1–2.2 M cells (`BufferCell` + `HeapByteBuffer` +
  `SingleItemCellPath`, ≈ 360 P64 mutations' worth) of memtable and in-flight writes: the S2 / B6 write path,
  not replay.

### 3.2 Condition X — restore emulation (diagnostic), defaults otherwise

| Run | Heap | Sstables removed | Replayed | Tail memtable charge (flushes) | Mid-replay live `Mutation`s / live heap | Restart | Max live after any replay Full GC |
|---|---|---|---|---|---|---|---|
| x-p64-2g-drop-r1 | 2 GiB | 55 | 3,344 | 3,043 MiB (18) | (+25 s: replay over) / 39 MiB | started, 45 s | 280 MiB |
| x-p64-2g-drop-r2 | 2 GiB | 56 | 3,538 | 3,224 MiB (19) | 1 / 273 MiB (+8 s); 1 / 217 MiB (+16 s) | started, 48 s | 272 MiB |
| x-p64-2g-drop-r3 | 2 GiB | 56 | 3,371 | 3,068 MiB (18) | 1 / 168; 1 / 267 MiB | started, 46 s | 266 MiB |
| x-p64-1g-drop-r1 | 1 GiB | 78 | 3,794 | 3,431 MiB (40) | 1 / 154; 1 / 178 MiB | started, 51 s | 189 MiB |

Replay ran at ≈ 125–130 P64 mutations/s (≈ 106 MiB/s of memtable charge); each flush was enqueued at 33 %
of the pool and completed in ≈ 1.2 s, so the pool never filled and the queue never grew.

### 3.3 Condition S — X + 10 s flush stall during the restart (diagnostic), 1 GiB

| Run | Payload / replay setting | Restart | Evidence |
|---|---|---|---|
| s-p64-1g-r1 | P64, defaults | **heap OOM after 127 s** (59 % STW; live after Full GC up to 1,011 MiB) | dump (1.4 GB): 4.33 M `ArrayCell` (replay-deserialized; ≈ 733 queued P64 mutations, 231 MiB + paths/buffers) next to 1.71 M `BufferCell` (memtable); thread dump at +20 s: `main` in `Cell$Serializer.deserialize`, `MutationStage` threads parked in `MemtableAllocator$SubAllocator.allocate` |
| s-int64-1g-r1 | P64, `commitlog_max_outstanding_replay_count=64` | started after 214 s | +20 s: 65 live `Mutation`s, 383 MiB live |
| s-blob-1g-r1 | blob 65,200 B | started after 58 s (8,084 replayed) | +20 s: 1,025 live `Mutation`s (queue at its bound), 437 MiB live |
| s-p64-1g-r2 | P64, defaults (no dump) | **heap OOM after 40 s** (43 % STW; 1,010 MiB live after Full GC) | `# java.lang.OutOfMemoryError: Java heap space`, `OnOutOfMemoryError` kill |
| s-int64-1g-r2 | P64, count 64 | started after 175 s (3,178 replayed) | 351 MiB max live after Full GC |
| s-blob-1g-r2 | blob | started after 57 s (6,242 replayed) | 0 Full GCs |
| s-p64-1g-r3 | P64, defaults (no dump) | **heap OOM after 40 s** (43 % STW; 1,014 MiB live after Full GC) | `# java.lang.OutOfMemoryError: Java heap space` |
| s-int64-1g-r3 | P64, count 64 | started after 173 s (3,198 replayed) | 311 MiB max live after Full GC |
| s-blob-1g-r3 | blob | started after 57 s (7,784 replayed) | 54 MiB live after its one Full GC |
| s-p64-2g-r1 | P64, **2 GiB** (no dump) | started after 115 s (3,140 replayed) | 9 Full GCs, up to 1,434 MiB (70 %) live after Full GC; worst 60 s 37 % STW |

S at 1 GiB: **heap OOM 3/3** in replay (40–127 s after start); blob **0/3**; replay count 64 **0/3**. At 2 GiB
the same stall leaves 70 % live and the node starts (1/1): largest failing heap **1 GiB** (1–2 GiB not
searched). The thread dump in r1 shows all 32 `MutationStage` threads parked in the memtable allocator while
`main` keeps deserializing ([`logs/s-p64-1g-r1-threads.txt`](logs/s-p64-1g-r1-threads.txt)). The
intervention costs start-up time (173–214 s with the stall, vs ≈ 45–51 s for X without it) but replays every
mutation; nothing is rejected. The runtime load at 1 GiB served writes in all 12 load phases (8 with P64)
before the kill.

### 3.4 Ledger L — queue held at its bound (diagnostic)

| Run | Live `Mutation`s | K (× 63.7 KiB) | U (replay cells, paths, buffers, `byte[]`) | Total live | Restart |
|---|---|---|---|---|---|
| d-p64-2g-bm (+15 s / +30 s) | 1,015 / 1,004 | 63.1 / 62.5 MiB | **947 / 928 MiB** (5.99 M `ArrayCell` 228 MiB, `HeapByteBuffer` 274 MiB, `SingleItemCellPath` 91 MiB, `byte[]` 353 MiB incl. ≈ 63 MiB N3 copies) | 1,004 / 985 MiB | started, 159 s (4 Full GCs, ≤ 1,003 MiB live) |
| d-p64-8g-bm (+20 s) | 1,025 | 63.8 MiB | 955 MiB | 1,012 MiB | started, 89 s |
| d-int64-2g-bm (count 64) | 65 | 4.0 MiB | 76 MiB | 106 MiB | started, 129 s |
| d-blob-2g-bm | 1,025 | 63.8 MiB | 143 MiB (`byte[]`: value + N3 copy) | 173 MiB | started |

Per P64 mutation: 0.93 MiB held vs 63.7 KiB counted (**15.0×**; ≈ 155 B per tiny cell plus the N3 copy at
1.0× K, 7 % of U). Blob: 2.2×. The memtable charges ≈ 0.83 MiB for the same P64 mutation, so a queued
mutation holds ≈ 1.13× its later memtable charge.

Raw data: `ms0625:/mydata/b8/runs/<run>/` (`arm.log`; `load/` and `replay/` with `system.log`, `gc.log`,
`stdout.txt`, `memcur.txt`, `histo-*.txt`; `dumps/hist-*.txt`; the first S OOM dump kept). Excerpts:
[`logs/`](logs/).

## 4. Conclusion and limits

**Promotion rule** (protocol *Verification status*):

| Condition | V1 repetition | V2 matched control | V3 U apart from K | V4 intervention | V5 initiating failure | V6 defaults | V7 budget | Proposed status |
|---|---|---|---|---|---|---|---|---|
| A | replay started 10/10 (P64 at 2 GiB 3/3; 1 GiB 2/2; 512 MiB 2/2) | blob 1/1 started | GC-log live during replay; tail charge from flush lines; ledger L | n/a (no failure) | n/a | yes | 512 MiB–2 GiB, container 2 × heap | **`negative · deployment`** (range: single node, one table, 150 s loads, heaps 512 MiB–2 GiB, aarch64) |
| X | started 4/4 | — | mid-replay histograms: 1 live `Mutation` | n/a | n/a | yes | 1–2 GiB | **`negative · diagnostic`** (sstables removed) |
| S | heap OOM 3/3 at 1 GiB | blob 0/3 (started 3/3; queue at its 1,025 bound, 437 MiB live) | dump: 4.33 M replay `ArrayCell`s ≈ 733 queued mutations vs memtable `BufferCell`s; ledger L | count 64: 0/3 (started 3/3) | `OutOfMemoryError: Java heap space` + dump + thread dump (r1) | yes | 1 GiB (the runtime load at 1 GiB served writes 12/12) | **`verified-OOM · diagnostic`** (largest failing heap 1 GiB; 2 GiB starts) |

**Interpretation.**

1. *Accounting:* the replay bound counts serialized bytes and therefore admits ≈ 15× its nominal 64 MiB for
   tiny-cell data (0.95 GiB at 1,024 P64 mutations), ≈ 2.2× for blobs. This is the unit CASSANDRA-8639's
   committed fix chose instead of the proposed `unsharedHeapSize()`; it is an incomplete fix in that sense,
   not a regression. N3 (cached serialized copy) adds 1.0× the counted size, 7 % of U for tiny cells.
2. *Reachability at defaults:* the queue does not fill. What remains to replay is capped by the memtable
   pool (runtime flushing discards covered segments), the reader is a single thread, and replay-time flushes
   keep up on this node. A same-heap restart therefore replays at most one pool of data, never more than
   ≈ 1.13 × heap/4 of deserialized mutations in flight even if the appliers stalled. The 1,024 / 64 MiB
   bound is not the binding control; runtime flushing is.
3. *Where it bites:* only when the replay volume exceeds the pool (here: sstables removed, as in a restore that
   replays archived segments) **and** the appliers stall (here: an injected 10 s flush stall), the queue fills
   to its bound and a 1 GiB node OOMs during start-up, a node that served the same writes at 1 GiB. Counting
   replay mutations by heap size (or `count=64`) removes it. At 2 GiB the same stall leaves 70 % live and the node starts.
4. *Operational consequence observed:* in S the node cannot restart at 1 GiB until the stall clears or the
   property is lowered (`-Dcassandra.commitlog_max_outstanding_replay_count`); at defaults, a node that OOMed
   at runtime (512 MiB) restarted cleanly every time.

**Limits.**
- One node, one table, aarch64 m400 (slow cores: reader ≈ 130–170 P64 mutations/s). A faster reader relative
  to flush, or slower disks, could build a backlog without injection; X shows no backlog here even at 6× the
  pool, so this is untested rather than excluded.
- The restore path is emulated by deleting sstables, not by `commitlog_archiving.properties` restore; the
  flush stall is Byteman, not a real disk stall (B6 condition A used dm-delay).
- K uses B6's serialized-size calibration (10.80 KiB per 1,000 entries); the count bound (1,024) is the one
  read directly. Load-phase acks include write timeouts (the pool was full by design).
- Not run: same-log-smaller-volume control and upward heap search for A (no failure); a diagnostic build
  charging heap size (the count intervention stands in for it); multi-table retention shapes.

**Back-link:** if S is accepted as `verified-OOM · diagnostic`, run `backlink-playbook.md`: phase 1
(stage 4 of `commitlog_max_outstanding_replay_bytes`) held the clue (backlog heap ≈ 2 × L for blobs, built
only with `memtable_cleanup_threshold: 0.99` and a load pool larger than the replay pool).

**Next (if wanted):** a real archived-segment restore (`commitlog_archiving.properties`, `restore_directories`)
with a dm-delay data-disk stall at 1–2 GiB; an x86 node to see whether a faster reader outpaces flushing
without injection; a patch charging `unsharedHeapSize()` as the V4 intervention for an upstream report.
