# B8 design — commit-log replay bound counts serialized bytes (written 2026-11-16, 19:40 MST, before readings)

IDs: **B8** = campaign bypass investigation 8 (B = bypass); **N4** = new lead 4 from the
capacity-enforcement bypass notes (N = new lead); **N3** = the cached-serialized-copy lead (amplifier);
**B6** = the internode-queue bypass case whose payload and client are reused.

## Claim under test

`CommitLogReplayer.handleMutation` (5.0.9, `CommitLogReplayer.java:513–531`) charges each replayed mutation
by its **serialized** size and drains the future queue only when > 64 MiB or > 1,024 futures are
outstanding (`CassandraRelevantProperties.java:114–115`) or the head future is done. Each mutation is
fully deserialized (`CommitLogReader.readMutation`, `:417–478`) before it is charged, and each one under
1,000,000 B also keeps a cached serialized copy (`Mutation.java:493`, N3). Tiny-cell map mutations
are ≈ 17–20× larger on heap than serialized (B6). Hypothesis: **startup replay of a commit log of
tiny-cell mutations OOMs a node at an acceptable heap that served the same writes at runtime.**

## Protection map (replay)

| Control | Bounds | Unit |
|---|---|---|
| `commitlog_max_outstanding_replay_bytes` (64 MiB, JVM property) | queued + executing replay mutations | serialized bytes |
| `commitlog_max_outstanding_replay_count` (1,024) | same | futures |
| `memtable_heap_space` (default heap/4) | memtable contents during replay; mutation-stage threads block on allocation when full | memtable-charged bytes |
| `concurrent_writes` (32) | mutation-stage threads applying replay mutations | threads |
| `commitlog_total_space` (8 GiB here: min(8 GiB, ¼ of the 39 GiB volume)), `commitlog_segment_size` 32 MiB, periodic sync 10 s | how much log can exist; data after the last sync marker is not replayed | bytes on disk |

Counted ceiling C = 64 MiB serialized / 1,024 mutations. Measured U = heap held by replay-queued
`Mutation`s (dump/histogram at OOM; GC-log live at peak).

## Predicted trajectory (before readings)

What remains to replay is limited by runtime flushing: with one table, all commit-log data not covered by
an sstable is at most what the memtable pool held at the kill (≤ `memtable_heap_space`, heap/4 =
512 MiB charged at 2 GiB heap, cleanup threshold 1/3). At the 64 KiB shape this is a few hundred
mutations, i.e. **fewer than the 1,024-count bound**, so the replay queue may hold the whole remaining log
only when the mutation stage is blocked (memtable full and flushing). Predicted replay peak ≈ baseline
(≈ 0.2–0.3 GiB) + memtable (≤ 0.5 GiB) + queued mutations (≤ min(remaining log, 1,024 or 64 MiB serialized)
× ≈ 17–20). If memtable charge per cell is close to the deserialized heap per cell, this is ≈ 2× the
runtime memtable footprint, and **2 GiB is predicted to survive**; the OOM needs the queue term
(≤ ≈ 1.1–1.3 GiB) to exceed the free heap left by memtable + baseline. The first calibration measures
exactly these three terms; if the prediction holds, the expected verdict is a bounded overshoot (U > C)
without OOM, or a negative.

Settings that affect what remains to replay, all left at shipped defaults (V6): `commitlog_segment_size`
32 MiB, `commitlog_total_space` default, periodic sync 10 s, `memtable_heap_space` default, flush writers 2,
`memtable_allocation_type: heap_buffers`, `concurrent_writes` 32. Accumulation comes from workload shape
only (write rate vs flush speed on this node's disk; kill while flushes are pending). Any non-default
(e.g. a larger memtable to accumulate more log) is a labelled supporting deviation → `diagnostic`.

## Budget (V7), argued before readings

- Node `ms0625`, aarch64 (Utah m400), 8 cores, 62 GiB; swap 0 inside the victim scope.
- **Heap 2 GiB (ideal per the standing rule), searched upward (3, 4, 6 GiB) and downward to 512 MiB** for
  the largest failing heap. Container (systemd scope, `MemorySwapMax=0`) = 2 × heap, which matches the 5.0.9
  documentation's "heap ≤ ½ of RAM" (R1-V re-review rule). Direct memory: shipped auto (¼ of RAM,
  15.5 GiB, capped in practice by the container). Every heap ≥ 512 MiB meets V7 without per-case review.
- The **same budget** is used for the load phase and the restart, so "runtime survives" is a like-for-like
  claim.

## Arms

| Arm | Payload (serialized ≈) | Purpose | n |
|---|---|---|---|
| P64 | map, 5,900 entries (≈ 64 KiB; both bounds bind together) | suspect | ≥ 3 at the failing heap |
| P10 / P256 | map, 930 / 23,700 entries (≈ 10 / 256 KiB) | sweep: count-bound vs bytes-bound shape | 1 each, more if they fail |
| BLOB | blob of the same serialized size as P64 (≈ 2.2× expansion) | matched control | 3 |
| SMALL | P64 payload, same log shape but a smaller written volume (shorter load) | smaller-log control | 3 |
| INT | P64 with `-Dcassandra.commitlog_max_outstanding_replay_count=…` / `_bytes=…` lowered at restart | intervention | 3 |

Load: B6's tiny-cell map client (`B8Load.java`, derived from `B6Load`), CL=ONE, single node, RF 1,
in-flight 64 (raised if the node is not write-saturated), 120–240 s; `kill -9` at the end of the load window
while writes are still arriving; restart at the same budget with `-XX:+HeapDumpOnOutOfMemoryError`
(shipped) to `/mydata/b8/runs/<run>/dumps/`.

Outcome per restart: **heap OOM** (JVM `OutOfMemoryError`, dump), **GC service loss** (≥ 90 % of wall
time in STW pauses over ≥ 60 s, node not started within 15 min), **cgroup kill** (`memory.events`), or
**started** (`Starting listening for CQL clients`, with `Log replay complete, N replayed mutations`).

Stop conditions: ≈ 4 h wall; no arbitrary escalation after an OOM; every process stopped after each arm.

## Amendment 1 (2026-11-16 ≈ 19:55 MST, after the 2 GiB defaults arms, before any reading of the arms it adds)

**Why.** The first five 2 GiB arms confirmed the predicted bound: the replayed tail is the unflushed memtable
contents at the kill (memtable charge flushed during replay 516–570 MiB ≈ the 512 MiB pool, for 219–3,595
mutations), and the replay never builds a backlog (0 Full GCs, after-GC peak ≤ 628 MiB). The 1,024 / 64 MiB
bound is not the binding control at defaults: runtime flushing is. Stage 4 of
`commitlog_max_outstanding_replay_bytes` needed `memtable_cleanup_threshold: 0.99` and a 3 GiB pool (load)
replayed into a 256 MiB pool to build a backlog.

**Added arms (all labelled).**
1. **Diagnostic ledger (`d-*`)**: Byteman (`replay-delay.btm`) sleeps 1 s at the start of every replay task,
   so the outstanding queue fills to its bound; mid-replay `GC.class_histogram` gives U (live `Mutation`s
   and their cells) against C (1,024 / 64 MiB). 2 GiB and 8 GiB (8 GiB: tail > 1,024 mutations; container
   16 GiB), intervention `commitlog_max_outstanding_replay_count=64`, blob. Byteman alters timing →
   `diagnostic`; these arms measure the ledger, they are not a reachability claim.
2. **Restore emulation (`x-*`)**: after the `kill -9`, remove the table's sstables, so every retained log
   entry must be replayed (what a point-in-time restore from archived commit-log segments, or any replay
   not covered by sstables, does). This is the one shape found where the replay volume is not bounded by
   the memtable pool. Removing sstables is a supporting deviation (it emulates a restore procedure) →
   `diagnostic`. Prediction: if the reader outpaces flushing, the backlog reaches the bound and the peak is
   ≈ baseline + memtable pool + ≈ 1.1 GiB (P64) → heap OOM or GC service loss at 2 GiB; if flushing keeps
   up (as in the defaults arms' tails), it starts.

## Amendment 2 (2026-11-16 ≈ 20:40 MST, after x-p64-2g-drop-r1, before any reading of the arms it adds)

**Why.** Restore emulation r1 replayed 3,344 P64 mutations (3.0 GiB of memtable charge through a 512 MiB
pool) and started: flushes (≈ 1.2 s each, every ≈ 1.4 s) kept up with the single reader, so no backlog.
A backlog needs the apply side to stall while the reader continues.

**Added arms.** X repeated (r2, r3 at 2 GiB; r1 at 1 GiB). **S (diagnostic):** X + Byteman
`flush-stall.btm` loaded at the restart only, sleeping 10 s at the start of each flush of keyspace `b8`
(stands in for a data-disk stall during start-up; B6 condition A used a real 30 s dm-delay stall). At 1 GiB:
pool 256 MiB fills in ≈ 2–3 s, appliers block, the queue should fill to its bound (≈ 0.95 GiB of P64
mutations) → predicted heap OOM. Controls: intervention `commitlog_max_outstanding_replay_count=64`
(queue ≈ 60 MiB, predicted to start), blob of the same serialized size (64 MiB byte bound × ≈ 2.2 ≈
140 MiB, predicted to start). One run each first; repeat ×3 only if S OOMs. Label: `diagnostic` (sstables
removed + injected flush stall).
