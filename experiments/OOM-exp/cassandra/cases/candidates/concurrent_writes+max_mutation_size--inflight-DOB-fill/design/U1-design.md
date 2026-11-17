# U1 design — in-flight `DataOutputBuffer` fill of large mutations in `CommitLog.add` (standalone)

**Written 2026-11-16 21:25 EST, before any reading of this case.** Campaign row U1 (U = unprotected-accumulation
lead, memory with no applicable control). Lead source: side finding of R6-V (R = recheck of a pre-protocol
convergence OOM; -V = re-test at defaults and an acceptable budget), corroborated by C3 run 1 (C = convergence
investigation) and stage 3 of S1 (S = stacked combo case). Node: `pc96` only (32 cores, 125 GiB, HDD RAID
`PERC H710P` under `/mydata`, measured 200 MB/s `dd oflag=direct`), OpenJDK 11.0.33, G1.
Build: read-only reuse of `/mydata/b6/cassandra` (cassandra-5.0.9 `f2de6956`; `src/` identical to the pinned
`systems/cassandra/source/src/` except generated files; same build as S1 and C1 run 4).

## 1. Mechanism (source check, pinned 5.0.9)

| Step | Source | What it does |
|---|---|---|
| Size check | `CommitLog.java:304` → `Mutation.validateSize` (`Mutation.java:169–172`) | rejects a mutation > `max_mutation_size` (default `commitlog_segment_size` / 2 = 16 MiB, `DatabaseDescriptor.java:898–899`). Per mutation only. |
| Scratch buffer | `CommitLog.java:306` `DataOutputBuffer.scratchBuffer.get()` | thread-local `DataOutputBuffer`; `allocate()` = `ByteBuffer.allocateDirect` because `cassandra.dob.allocate_type` defaults to `DIRECT` (`DataOutputBuffer.java:55,84–88`, CASSANDRA-16471). Counted by the JDK `Bits` counter (`MaxDirectMemorySize`). |
| Fill | `CommitLog.java:308` `Mutation.serializer.serialize` → `BufferedDataOutputStreamPlus.write` → `DataOutputBuffer.expandToFit` (`:174–182`) | grows to `capacity + count` for a large write, then ×2 below 64 MiB (`calculateNewSize`, `DOB_DOUBLING_THRESHOLD_MB` 64). The old buffer is freed at once (`setBuffer` → `FileUtils.clean`, `:184–188`), so a transient old + new overlap of ≈ S + 2S exists during the copy. Observed in S1/R6-V dumps: S + 43 B and 2 (S + 43) B buffers. Mutations > 1,000,000 B have no cached on-heap serialization (`Mutation.java:451`, `CACHEABLE_MUTATION_SIZE_LIMIT`), so every large mutation is serialized in full here. |
| Hold | `CommitLog.java:309–337` | the buffer stays filled across `segmentManager.allocate` (may block in `awaitAvailableSegment`, `AbstractCommitLogSegmentManager.java:337–343`, waiting for a new 32 MiB segment: a 15 MiB mutation fills half a segment), the copy into the mmap'd segment, and `executor.finishWriteFor` → `PeriodicCommitLogService.maybeWaitForSync` (blocks when the periodic sync lags > 1.5 × 10 s). |
| Release | `CommitLog.java:306` try-with-resources → `scratchBuffer` `close()` (`DataOutputBuffer.java:71–81`) | `DOB_MAX_RECYCLE_BYTES` (1 MiB): a larger buffer is replaced by a 128 B one and freed. **The cap acts only after use**; nothing bounds the size while the buffer is being filled or held. |
| Concurrent holders | `MutationStage` threads (`concurrent_writes`, default 32) run `Mutation.apply` → `Keyspace.applyInternal` → `CommitLog.add` | the only bound on simultaneous holders. Other admission: `native_transport_max_request_data_in_flight` (heap/10 = 204.8 MiB at 2 GiB) and `_per_ip` (heap/40 = 51.2 MiB) bound **request bytes until the response is sent**; a write that times out (2 s) releases them while its `MutationStage` task may still run, and an expired local mutation is resubmitted as a hint runnable on the same unbounded stage (`StorageProxy.java:2634–2660`; S2 finding). So native admission does not bound the `MutationStage` holders. |

Per-holder footprint ≈ 2S (S = serialized mutation size), transient up to 3S. Ceiling at defaults:
32 × 2S = 960 MiB at S = 15 MiB (transient up to 1,440 MiB) + baseline. No Cassandra counter (K) covers it;
U = JMX `java.nio:type=BufferPool,name=direct` `MemoryUsed` (JDK `Bits`), split by heap dump at failure.

**Classification target:** unprotected accumulation (no control applies in flight; implicit bound
`concurrent_writes` × ≈ 2 × mutation size, not enforced as a memory limit). Workload must stay within the
documented limits: mutation ≤ `max_mutation_size` (16 MiB), CQL frame ≤ `native_transport_max_frame_size` (16 MiB).

## 2. Protection map (fixed before readings)

| Domain | Allocation / release | Contract C | Multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| U1 in-flight DOB | `DataOutputBuffer$1$1.buffer` (thread-local) grown in `expandToFit` under `CommitLog.add`; freed at `close()` if > 1 MiB | **none in flight**; per-mutation `max_mutation_size` 16 MiB (bounds S, not the sum) | ≤ `concurrent_writes` = 32 `MutationStage` threads | none (not reconciled with `MaxDirectMemorySize`) | serialize → segment allocate → copy → sync wait |
| D kept DOB | same buffer after `close()` | ≤ 1 MiB per thread (`DOB_MAX_RECYCLE_BYTES`) | all threads that serialized | none | standing |
| Other direct (baseline) | networking `BufferPool` (128 MiB cap; little used by native v4), Netty epoll arrays, compaction / flush writer buffers, hints buffers if any | per-pool caps | — | none | standing / transient |
| Netty direct (separate counter, S1 §1.1) | native v4 request frames (15 MiB each, Netty pooled arena) | `native_transport_max_request_data_in_flight` 204.8 MiB (bytes until response) | client connections | its own `MaxDirectMemorySize`-sized limit | until response |
| Heap (reported) | decoded mutations (≈ S each), `MutationStage` queue (unbounded, S2), memtable (`memtable_heap_space` = heap/4 = 512 MiB) | memtable 512 MiB | — | flush | — |

## 3. Configuration and budget

| Setting | Class | Value |
|---|---|---|
| `concurrent_writes`, `max_mutation_size`, `commitlog_segment_size`, `DOB_MAX_RECYCLE_BYTES`, `cassandra.dob.allocate_type`, memtable, native in-flight limits, timeouts, commit log sync | **default** (absent from yaml / no `-D`) | 32, 16 MiB, 32 MiB, 1 MiB, DIRECT, heap_buffers 512 MiB, 204.8 / 51.2 MiB, 2 s, periodic 10 s |
| `cluster_name`, addresses (127.0.0.71), seeds, data/commitlog/hints/saved_caches/cdc directories, JMX port 7271 | environment | yaml diff kept per arm |
| storage | environment | local HDD RAID (`/mydata/u1/node`), **not tmpfs** (avoids S1 amendment 1: tmpfs ENOSPC, and tmpfs pages charged to the scope) |
| heap | budget | `MAX_HEAP_SIZE=2048M` (ideal); 4 GiB only by a dated amendment if 2 GiB always ends in a heap OOM first |
| `MaxDirectMemorySize` | budget (dial) | first arm **auto**: not passed by the harness; `cassandra-env.sh` resolves it. On pc96 (½ RAM > 15,872 MiB) `CALCULATED_MAX_DIRECT_MEMORY_SIZE` = `heap_limit / 2` = **7,936 MiB**, also with an explicit 2 GiB heap (J1 side finding: ¼ RAM or heap_limit/2, not "half the heap"). Then 1,024 → 768 → 640 → 512, refine. |
| safety scope | environment (non-binding) | `systemd-run --user --scope -p MemoryMax=44G -p MemorySwapMax=0` (S1 after amendment 4: the 12 GiB scope killed V); `oom_kill` must stay 0 |
| CPU | environment | V on cores 0–15; client and sampler on 24–31 (colocated, pinned, as S1/C1) |
| client | workload | `U1Load` (from S1Load), driver 3.12.1, protocol v4, prepared `INSERT INTO u1.t (pk int, b blob)`, CL ONE, RF 1 (`SimpleStrategy`), zero-filled blobs, keys mod 200 (overwrite). "Writers" = client connections, each bound to its own loopback source IP (127.0.0.101…), so the per-client-IP limit applies per writer as with separate application hosts; each keeps ≤ `INFL` requests outstanding; one shared rate limiter caps the total offered rate. No driver retries. |

### V7 argument (written before readings; researcher reviews afterwards)

The result claims to represent a node whose Cassandra memory is sized as `cassandra-env.sh` sizes it for a
**4 GiB-RAM node** (automatic heap ½ RAM = 2,048 MiB, automatic direct ¼ RAM = 1,024 MiB), or equivalently a
larger node where the operator sets a 2 GiB heap explicitly (as Cassandra's docs allow) — on such a node the
script resolves direct to ¼ RAM (≤ 7,936 MiB). The heap is 2 GiB in every arm (the standing rule's ideal).
The direct limit is the dial: first the value `cassandra-env.sh` resolves on pc96 for the explicit 2 GiB heap
(7,936 MiB), then the 4 GiB-node value (1,024 MiB), then downward to the standing-rule floor (512 MiB). Every
value ≥ 512 MiB meets V7 by the standing rule without a per-case review; values below the resolved ones are
reported as such (a direct limit below ¼ RAM needs the operator to set `MAX_DIRECT_MEMORY_SIZE`, which
`cassandra-env.sh` offers as a documented override, or a smaller node). The safety scope is non-binding (44 GiB).
The largest failing direct budget is the reported boundary.

## 4. Predictions (before readings)

- **Ceiling sheet.** U_max = B0 (10–40 MiB) + H × 2S (+ up to H × S transient), H ≤ 32. At S = 15 MiB: ≤ 1.0 GiB
  standing, ≤ 1.45 GiB transient. **At auto 7,936 MiB a direct OOM is infeasible by arithmetic** (prediction:
  no direct OOM; a heap OOM is possible — R6-V L arms ended in heap OOM at 1,024 and 2,048 with a 2 GiB heap;
  P(heap OOM in 90 s) ≈ 50 %).
- **Reachable H.** Only threads still inside `CommitLog.add` hold. On a 200 MB/s HDD the commit log absorbs
  ≈ 10–13 × 15 MiB mutations/s while 32 writers × 4 in flight offer more, so the sync lags and segment
  allocation waits: predict H = 12–24 (R6-V 16–20; S1 7–14 large buffers in dumps) → U_peak 400–800 MiB.
- **Budget search.** 1,024 MiB: survive (H would need ≥ 33 at 2S) — predict 0/1, possibly heap OOM. 768 MiB:
  ≈ 50 %. 512 MiB: fail ≥ 2/3 (R6-V 4/5 with a heap OOM in the fifth). **Predicted largest failing budget:
  512–768 MiB.**
- **Size sweep** (same offered bytes/s): 4 MiB → H × 8 MiB ≤ 256 MiB, survive; 8 MiB → ≤ 512 MiB, borderline at
  512 MiB; 15 MiB fails. **Writers sweep** (15 MiB): 1 writer (per-IP 51 MiB ⇒ ≤ 3–4 requests admitted at a
  time, but timed-out writes keep running) → fewer holders, survive likely; 2, 8, 16 writers → more holders.
- **Matched control** (512 KiB mutations, same offered bytes/s and writers): DOB ≤ 1 MiB per thread → U ≤
  B0 + 32–64 MiB, survive 3/3 with ≥ 30 % headroom.
- **Intervention** (`concurrent_writes: 8`, same workload): H ≤ 8 → ≤ 240 MiB, survive 3/3 at similar
  delivered MiB/s (the disk is the bottleneck either way). Secondary: `max_mutation_size: 4MiB` rejects every
  15 MiB write (no useful work; reported, not counted as protection); `-Dcassandra.dob.allocate_type=ONHEAP`
  (JVM property, 4.x behaviour) moves the fill to the heap → no direct OOM (heap may suffer).
- **Initiating failure.** `OutOfMemoryError: Direct buffer memory` on a `MutationStage` thread in
  `Bits.reserveMemory` ← `DataOutputBuffer.expandToFit` ← `Mutation.serializer.serialize` ←
  `CommitLog.add(CommitLog.java:308)`; dump: DOB scratch ≥ 50 % of JDK-accounted direct.

## 5. Arms, repetitions, stopping budget

Each arm: clean node (directories regenerated), schema, 5 s idle, **90 s load**, 20 s observation, stop. Samplers:
JMX 1 s (`U1Sample`: direct used/count, heap, MutationStage active/pending/completed, native-transport pool,
commit-log waits, dropped mutations, write timeouts, memtable size), cgroup 1 s, and in diagnostic arms only
`jcmd Thread.print` every 5 s (MutationStage threads classified: in `CommitLog.add` / `expandToFit` /
segment wait / sync wait / memtable wait). Heap dump at failure (Cassandra's forced heap OOM,
`-XX:+HeapDumpOnOutOfMemoryError` from the shipped `jvm-server.options`), attributed by `hprof_direct.py` (C1/S1).

Endpoint workload E: S = 15,728,640 B (15 MiB, as S1), 8 writers × 4 in flight, 40/s offered (600 MiB/s).

1. Reachability: E at auto (7,936) ×1 with `jcmd` sampling (also calibrates H).
2. Budget search E: 1,024 → 768 → 640 → 512 (n = 1 each, geometric then refine); then the largest failing
   budget ×3 (V1) and the next surviving one ×2 more.
3. At the largest failing budget X*: size sweep 4, 8 MiB (n = 1); writers sweep 1, 2, 16 (n = 1).
4. Matched control at X*: 524,288 B × 1,200/s offered (600 MiB/s), 8 writers × 4 in flight, ×3 (V2).
5. Intervention at X*: `concurrent_writes: 8` ×3 (V4); `max_mutation_size: 4MiB` ×1; `dob.allocate_type=ONHEAP` ×1–3 if time allows.

Stop: ≤ 35 arms or 01:00 EST, whichever comes first; no escalation of workload after an OOM. Victim-side
4 GiB heap only by amendment if every 2 GiB arm ends in a heap OOM before a direct reading.
Data: `pc96:/mydata/u1/runs/<arm>/`.

## Amendment 1 — 2026-11-16 21:31 EST (after arm `A_auto_r1`, before the budget search)

- **Auto direct on pc96 is 15,872 MiB, not 7,936.** `cassandra-env.sh` sets `heap_limit` = 15,872 only when
  `USING_CMS` is 0 (CMS found); with the shipped G1 options `USING_CMS` = 1, so `heap_limit` = 31,744 and
  `CALCULATED_MAX_DIRECT_MEMORY_SIZE` = 31,744 / 2 = **15,872 MiB** (JVM flag read back: 16,642,998,272 B). The
  4 GiB-node claim of §3 is unchanged (¼ RAM = 1,024 MiB).
- `A_auto_r1` (jcmd sampling on): no OOM; U_peak 752 MiB; at most 21 `MutationStage` threads active (not 32);
  21 writes/s delivered (314 MiB/s), 0 timeouts; heap peak 1,955 MiB, 9 Full GCs. Thread dumps: most of the time
  the writers wait in memtable allocation (after `CommitLog.add`, DOB already trimmed); after each release up to
  10 threads are inside `CommitLog.add` at once, giving U spikes of 420–752 MiB. The holder count is set by this
  burst, not by a commit-log stall.
- Search plan unchanged: 1,024 → 768 → 640 → 512 (n = 1 each), then refine.

## Amendment 2 — 2026-11-16 21:47 EST (after `B_d1024/768/640/512_r1`, before further budget arms)

- Readings: 1,024 survive (U_peak 632, 32 writers active, 200 write timeouts), 768 survive (695; 7 `System.gc()`
  from `Bits.reserveMemory`), 640 survive **touching the cap** (633; 79 forced GCs — the JDK retry loop waits
  ≈ 0.5 s for other writers to free their scratch, as above 768 in S1), 512 **died, but not of U1**: Netty's own
  counter threw `OutOfDirectMemoryError` (16 MiB, used 504 of 512 MiB) in the native v4 frame decoder
  (`ByteToMessageDecoder.cumulate`) 4.6 s into the load, with JDK U at 269 MiB and no `CommitLog.add` frame.
  The client's 32 outstanding 15 MiB requests are decoded into 16 MiB Netty chunks before the native
  in-flight limits are checked (they only pause reading afterwards), so ≈ 32 × 16 MiB sit on Netty's
  counter at the load start. This is a separate domain (Netty counter, native request frames; S1 §1.1) and is
  recorded as a side result / lead, not as the U1 endpoint.
- Changes for the next readings: (i) E at **576** MiB (Netty needs ≈ 520 MiB for E, so the JDK side can be read);
  (ii) workload **E3** = E with 3 in flight per writer (24 outstanding, ≈ 384 MiB of Netty frames) at 512 and 576,
  to read the U1 (JDK) endpoint at the floor without the Netty endpoint. The U1 boundary is the largest budget
  with a JDK `Direct buffer memory` OOM whose first stack is in `CommitLog.add`.

## Amendment 3 — 2026-11-16 22:10 EST (after `B_d576_r1`, `E3_d512_r1`, `E3_d576_r1`, `B_d608_r1`, `B_d640_r2`)

- Readings: **576 fails with the U1 stack** (E 1/1, 31 s into the load; E3 1/1, 20 s): first error
  `OutOfMemoryError: Direct buffer memory` on `MutationStage-42` in `Bits.reserveMemory` ← `expandToFit` ←
  `Mutation.serializer.serialize` ← `CommitLog.add(CommitLog.java:308)`. E3 at 512 again ended on Netty's
  counter (23 s in), so the floor cannot be read with this client shape. 608 survives touching the cap
  (U_peak 603, 130 forced GCs); 640 survives 2/2 (632–633).
- Condition fixed for V1–V4: **E at 576 MiB direct, 2 GiB heap**. Endpoint ×2 more (V1). Matched control G
  (V2): 524,288 B mutations (below the 1 MiB recycle cap after doubling), 8 writers × 16 in flight, 1,200/s
  offered (600 MiB/s, the same offered bytes/s as E). Intervention (V4): `concurrent_writes: 8` with E, ×3.
  Then size sweep (4, 8 MiB), writers sweep (1, 2, 4 writers × 4), `max_mutation_size: 4MiB` ×1 and
  `-Dcassandra.dob.allocate_type=ONHEAP` at 576.

## Amendment 4 — 2026-11-16 22:31 EST (after `B_d576_r2/r3`, `G_ctl512k_d576_r1/r2`, `I_cw8_d576_r1/r2`)

- E at 576: r2 survived touching the cap (575), r3 ended on **Netty's counter** again (frames of the client's
  outstanding requests). E at 576 is thus U1 1/3, Netty 1/3, survive 1/3: the two counters share the
  `MaxDirectMemorySize` value and both sit near it with this client shape. Control G (U 127) and
  `concurrent_writes: 8` (U 393–408, 274–321 MiB/s delivered) survive so far.
- Probes before fixing the V1 condition (n = 1 unless stated): E3 at 576 ×2 more; **E2** = 8 writers × 2 in
  flight (16 outstanding ⇒ fewer Netty frames) at 512 and 544; E3 at 544. The V1 condition is the
  largest budget / client shape with a U1 (JDK, `CommitLog.add`) OOM in ≥ 2 of its first runs and no Netty
  endpoint; control G and intervention `concurrent_writes: 8` are then repeated ×3 at that condition (the
  576/E arms stay as reported readings).

## Amendment 5 — 2026-11-16 23:03 EST (after the amendment-4 probes; before the V1–V4 set)

- Readings: E3 at 576 r2, r3 survive touching the cap (574–575; 153–250 forced GCs); E2 at 512 (U 500) and 544
  (543), E3 at 544 (544) survive, all touching the cap. So with 90 s loads the U1 endpoint is **stochastic**:
  at 576 MiB U1 2/6 (E 1/3, E3 1/3), Netty 1/6 (E only), survive 3/6; between 512 and 608 every arm reaches
  the cap and `Bits.reserveMemory`'s retry loop (forced GC, then ≈ 0.5 s of backoff) usually lets another
  writer free its scratch first. The OOM happens when a burst of writers holds past that window.
- **V1–V4 condition (fixed now): E3 (15 MiB, 8 writers × 3 in flight, 40/s offered) at 576 MiB direct,
  2 GiB heap, 240 s load** (longer exposure to the same burst process; no other change). E3 keeps the Netty
  counter below its limit at 576 (0/3 Netty endpoints). Interleaved by repetition ×3: endpoint `L_E3`, control
  `L_G` (524,288 B, 8 × 16 in flight, 1,200/s, 240 s), intervention `L_cw8` (E3 + `concurrent_writes: 8`, 240 s).
  Prediction: endpoint ≥ 2/3; control 0/3 (U ≈ 130); intervention 0/3 (U ≈ 400) at ≥ E3's delivered MiB/s.
- Then (90 s, n = 1, at 576): size 4 MiB and 8 MiB (E3 shape, same offered MiB/s: 150/s, 75/s); writers 1 × 3
  and 4 × 3; `max_mutation_size: 4MiB` with E3; `-Dcassandra.dob.allocate_type=ONHEAP` with E3.

## Amendment 6 — 2026-11-16 23:24 EST (after `L_E3_d576_r1/r2`, `L_G_d576_r1`, `L_cw8_d576_r1`)

- Readings: the 240 s endpoint arms survive 0/2 (U at the cap 574–575 for 22–37 s each, 554–616 forced GCs);
  L control U 127, L intervention U 439 (both survive). Every OOM so far came **early** (U1 at 20 and 31 s,
  Netty at 6, 17, 23 s after load start): the hazard is concentrated in the first ≈ 30 s (fresh commit log,
  first memtable flushes), so a longer load does not raise the per-run rate; more clean starts do.
- Change: the remaining L arms are cancelled after `L_G_d576_r2`. The V1–V4 condition reverts to
  **E3 at 576 MiB, 90 s** (the shape of `E3_d576_r1..r3`, 1/3 so far): endpoint repetitions r4–r9 (stop early
  once the U1 count reaches 3 and the run count is ≥ 6), intervention `concurrent_writes: 8` with E3 ×3 (90 s),
  control = G at 576 (90 s ×3 done, plus L_G 240 s). Then the size and writers sweeps and the two extra
  interventions of amendment 5, as time allows (stop 01:00).

## Closing note — 2026-11-17 00:35 EST (no new design; record only)

- Amendment-6 queue ran to the end: E3 @ 576 r4–r9 (U1 0/6 more, Netty 1/6), `concurrent_writes: 8` with E3 ×3,
  sweeps and the two extra interventions. `W_4x3_d576_r1` first aborted at start (the harness found a foreign
  process whose command line contained `CassandraDaemon`: another session's ssh tooling; kept as
  `runs/ABORTED_W_4x3_d576_r1_foreign-pgrep`) and was rerun at 00:27 unchanged.
- Prediction fit: ceiling and holders ✓ (H 21–32 active; U 632–752 at ≥ 1,024); auto/1,024 no direct OOM ✓; heap OOM
  at auto ✗ (none at any budget); largest failing budget 512–768 ✓ (576) but the endpoint rate is far below the
  predicted ≥ 2/3 ✗ (`Bits.reserveMemory`'s retry loop rescues most cap touches); control ✓; intervention ✓;
  Netty-counter endpoint not predicted.
