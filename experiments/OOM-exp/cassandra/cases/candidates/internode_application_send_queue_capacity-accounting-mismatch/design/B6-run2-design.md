# B6 run 2 design — remove the run-1 supporting deviations (2026-11-10)

Run 1 reproduced the accounting mismatch but needed a Byteman-slowed replica and 60 s write and
native-transport deadlines. Run 2 replaces both with a realistic trigger and targets the replica.

## Why a *stall* instead of a *slow* replica

A received message is dropped for expiry only when a `MutationStage` thread picks it up
(`InboundMessageHandler.ProcessMessage.run`, `InboundMessageHandler.java:408–423`). Run 1's slow
replica kept its threads running, so expired messages were drained and the deadline bounded the
queue. If the write threads are **blocked**, nothing is dequeued: deserialized mutations stay on heap
regardless of the deadline, until the receive counters reach their limit (per sender 4 + 128 MiB,
in total ≤ N·4 + 512 MiB). Real causes: commit-log sync lagging past
`periodic_commitlog_sync_lag_block` on a slow disk, memtable space exhausted while flushes cannot
complete (`MemtablePool` `BlockedOnAllocation`), long GC pauses.

## Changes from run 1

| Item | Run 1 | Run 2 |
|---|---|---|
| Replica slowness | Byteman 100 ms per mutation, `concurrent_writes: 2` | **Disk stall:** V's data/commitlog/hints on a dm-delay device (`/mydata/b6/slow`, loop file on `/mydata`); write delay 0 → **30 s** from t = 20 s to t = 150 s (`harness-run2/slowdisk.sh`). Default `concurrent_writes` (32). |
| Deadlines | 60 s write + native | **defaults** (2 s write, 12 s native) |
| Coordinators | 1 | **4** (S1–S4, 127.0.0.13–16, dc=c, 8 GiB each), so the global receive reserve G can fill |
| Client | Python, ≈ 700 map inserts/s | **Java driver 3.12 async**, value serialized once (`setBytesUnsafe`), 256 in flight per coordinator |
| Measured instance | S or V at 2 GiB | **V at 8 GiB** (deployment-like) and 6 GiB |

Unchanged: fast co-replica F (dc=f), `NetworkTopologyStrategy {v:1, f:1}`, CL=ONE, hints off,
key/counter cache 0, payloads (1000-entry `map<int,int>` 10.80 KiB on-wire; matched 11 000-byte blob).

Prediction (R from run 1): V's receive ceiling with 4 senders ≈ 4·4 + 512 = 528 MiB on-wire →
≈ 17 × 528 MiB ≈ 9 GiB of waiting mutations, plus memtable heap and baseline: above an 8 GiB heap
for map, ≈ 1.2 GiB for blob.

## Arms (`harness-run2/arm.sh`, clean start each)

Load 150 s; stall from t = 20 s to t = 150 s; observe V 60 s after the stall clears.
Outcome per protocol, recorded separately: heap OOM (`ReportJavaOutOfMemory`), GC-driven service loss
(Full GCs with > 95% of heap live still running at the end), or survived.

- map vs blob at V 8 GiB (×3 each; the probe P1 is reported separately);
- map at V 6 GiB (×3), blob at V 6 GiB (×1);
- no-stall control (map, V 8 GiB);
- intervention: receive endpoint reserve 8 MiB (map, V 8 GiB, stall).

Probe P1 (2026-11-10 22:00, V 8 GiB, map, stall at t = 20 s): `MutationStage` 32 active / 30 411
pending 20 s into the stall; V reached 8 141 of 8 192 MiB live and ran back-to-back Full GCs (≈ 1.3 s
each) for more than 3 minutes after the stall and the load ended, without throwing
`OutOfMemoryError`. Live histogram in the spiral: 37 217 `Mutation`s (37.2 M `ArrayCell`s) waiting,
i.e. ≈ 393 MiB on-wire — below the 528 MiB receive ceiling.
