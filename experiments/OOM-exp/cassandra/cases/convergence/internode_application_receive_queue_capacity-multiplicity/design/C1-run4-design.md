# C1 run 4 — design (2026-11-12, written before any run-4 reading)

**Case:** C1, internode receive-queue multiplicity (convergence · multiplicity), aimed at *verified* (V1–V7)
under [`verification-protocol.md`](../../../../../verification-protocol.md) (standing budget rule 2026-11-11),
[`custom-convergence-playbook.md`](../../../../../custom-convergence-playbook.md) and
[`default-convergence-playbook.md`](../../../../../default-convergence-playbook.md).
Continues [run 3](../internode_application_receive_queue_capacity--multiplicity--run3-fastcoreplica.md)
(calibrated 1 MiB LARGE-message path, fast co-replica, open-loop load).
**Node:** `pc96` only (32 cores, 125 GiB, HDD `/mydata`, cgroup v2, swap 8 GiB present). Victim, fast
co-replica, 8 coordinators and the client are colocated on loopback addresses (documented topology choice).
**Build:** read-only reuse of `/mydata/b6/cassandra` (cassandra-5.0.9, tag commit `f2de6956`, `git status`
clean, no patches; JDK 11.0.33, G1). Run data under `/mydata/c1r4/`; instance data/commitlogs on a
dedicated tmpfs `/mydata/c1r4/shm` (24 GiB, mounted for this run, unmounted at the end).

## 1. Mechanism and protection map

`AbstractMessageHandler.acquireCapacity` (`net/AbstractMessageHandler.java:411–455`) admits each inbound
message against the connection's exclusive allowance **Q** first, the overflow against the global
reserve **G**, then the endpoint reserve **E**. LARGE messages (> one 128 KiB frame) keep their **raw
frames** (`LargeMessage.buffers`, `ShareableBytes` slices of `BufferPool` direct buffers,
`AbstractMessageHandler.java:522–600`) until the `MutationStage` task deserializes them just in time
(`InboundMessageHandler.java:358–383`, `ProcessMessage.run :404–444`); capacity and buffers are released in
its `finally`. Hence queued-but-unprocessed LARGE mutations are **direct memory**, charged in on-wire bytes.

Admission ceiling with k=1 LARGE connection per peer: **K_max(N) = N·Q + min(G, N·E)**.
At defaults Q=4, E=128, G=512 MiB: **N=1: 132, N=2: 264, N=4: 528, N=8: 544 MiB.**

| Domain | Allocation / owner / release | Local contract | Multiplicity | Aggregate coverage | Lifetime | Budget metric |
|---|---|---|---|---|---|---|
| R: inbound LARGE frames queued for MutationStage (victim) | `FrameDecoder` reads into `BufferPool` (networking pool, 128 MiB cap; overflow `allocateDirect`); frames pinned by `LargeMessage.buffers` until deserialized on the stage | per connection Q=4 MiB (hard, bytes on wire), per endpoint E=128 MiB, global G=512 MiB | per active peer connection (N loaded coordinators) | G caps the **reserve** part only; N·Q is outside G by contract | standing while queued (until processed or expired at dequeue) | JVM direct (`-XX:MaxDirectMemorySize`); measured by `java.nio:BufferPool=direct` MemoryUsed |
| P: networking BufferPool slack | chunk/slab granularity of the pool; a frame slice pins its whole read buffer | pool cap 128 MiB (`networking_cache_size`), beyond that overflow allocations | per event-loop thread | none in bytes beyond the pool cap | as R | direct |
| H: deserialized `Mutation` being applied (victim) | `MutationStage`, `concurrent_writes`=32 | count bound 32 × ~1 MiB | 32 threads | executor size | transient | heap |
| M: memtable (victim) | `heap_buffers`, `memtable_heap_space` = heap/4 | 512 MiB at 2 GiB heap | per table | flush | standing until flush | heap |

The claimed domain is **R (+P)**; H and M are heap and are reported, not claimed.
Classification rule fixed before the run (*Classification by measurement*): per connection U ≤ Q+E
and global reserve ≤ G ⇒ local controls hold; **if U_direct(R+P) − baseline ≤ K and K ≤ K_max but
K_max + baseline > direct budget ⇒ convergence (multiplicity)**. If U − baseline exceeds K by more than
the pool slack explains ⇒ report the excess as a candidate bypass (accounting mismatch), not convergence.

**Feasibility (Σ contract + baseline vs budget):** baseline direct after startup (expected 10–70 MiB, to be
measured) + K_max(8)=544 > 512 MiB ⇒ convergence feasible at the minimum acceptable direct budget for
N ≥ 4; not for N ≤ 2 (132/264 + baseline < 512). At 1 GiB direct, infeasible for any N ≤ 8 at default Q
(would need N·Q ≳ 450 MiB, i.e. N ≳ 110 peers).

## 2. Configuration and budget audit

| Setting | Class | Value |
|---|---|---|
| Q / E / G (`internode_application_receive_queue_*`) | **tested capacity, default** (left unset in yaml) | 4 / 128 / 512 MiB |
| send-queue Q/E/G on coordinators | capacity, default (unset) | 4 / 128 / 512 MiB |
| `networking_cache_size`, `file_cache_size`, `memtable_*`, `concurrent_writes` | default (unset) | 128 MiB / min(512, heap/4)=512 MiB / heap/4 / 32 |
| victim heap `-Xmx/-Xms` | **budget** | 2048 MiB (ideal per standing rule), fixed in all arms |
| victim `-XX:MaxDirectMemorySize` | **budget, the dial** | 2048 MiB in calibration; search 512 → upward in the OOM stage |
| victim container | budget (safety only) | `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0`; argued as a non-binding outer limit; `memory.events` recorded, must show 0 oom_kill for a direct-OOM endpoint |
| resolved defaults on pc96 (`cassandra-env.sh`) | reference | heap min(½·125 GiB, 15872) = 15872 MiB, direct 15872/2 = 7936 MiB |
| `write_request_timeout` | default 2000 ms on **all** instances (verified in system.log) | open item from run 3, see §3 |
| `hinted_handoff_enabled` | **supporting deviation** (all instances, false) | as in run 3: coordinators would write hints for every timed-out victim write (≈ offered rate × arm time, tens of GB) |
| Byteman `MutationVerbHandler.doVerb` sleep on victim | **supporting deviation** (diagnostic) | used only if the natural-drain probe (§4 A0) cannot fill the queue; value fixed after A1, frozen thereafter |
| storage | environment | all instances on tmpfs; `commitlog_total_space: 2048MiB` (disk cap, environment, keeps tmpfs bounded) |
| snitch/dc/tokens/NTS {v:1,f:1}, `num_tokens: 1`, `initial_token`, key/counter cache unchanged default | environment | loopback 127.0.0.21 (V), .22 (F), .31–.38 (C1–C8) |
| CPU pinning (`taskset`) | environment | V 0–7, F 8–11, C 12–23, client+sampler 24–31 |
| client | workload | Java driver 3.x (B6Load derivative `C1Load`), INSERT 1 MiB blob, CL=ONE, keys mod 2000 (overwrite, bounded data), total offered rate R shared by N sessions (one per active coordinator), matched across N |

## 3. Timeout check (run-3 open item) and prediction

The sender sets `expiresAt` = creation + `write_request_timeout` T. A message still queued at the victim
when it reaches the head after T is released as expired at dequeue (cheap). With drain rate D < arrival
rate λ, occupancy ≈ min(K_max, ≈ λ·T + backlog not yet expired). **Requirement:** λ·T ≥ K_max(N), i.e.
with T = 2 s (default) λ ≥ 272 MiB/s for N=8. Plan: measure D and λ_arrived (`received`, `processed`,
`expired` deltas) in A1; keep **T at default** if peaks reach ≥ 95 % of K_max at the chosen R; otherwise
record that default T caps occupancy below K_max (that would itself be a protective response).

**Prediction (before readings).** Direct U_peak ≈ baseline_direct + K(N)·(1+s), s = pool slack (0–20 %).
With R ≥ 300/s and a slow victim: K ≈ 132/264/528/544 MiB for N=1/2/4/8. At direct budget 512 MiB:
**N=8 and N=4 fail with `OutOfMemoryError: Direct buffer memory`** on the inbound `BufferPool`/frame path;
N=1, N=2 survive. Largest failing direct budget predicted ≈ 544 + baseline + slack ≈ 580–700 MiB; at
≥ 768 MiB (and the ideal 2 GiB) no failure for N ≤ 8 (protection within range).
Heap 2 GiB: no heap OOM predicted (H ≤ 32 MiB, M ≤ 512 MiB).

## 4. Arms (all from a clean ring: every instance regenerated, tmpfs wiped)

Each arm: ring up (≈ 2–3 min) → 20 s warm-up at R → load window W=90 s → 30 s observe → stop.
Foreign load (`uptime`, non-run java/heavy processes) recorded before each arm; an arm is not started when
1-min load average > 16 from foreign processes (wait ≤ 10 min, then record and proceed or skip).

| Stage | Arms | Purpose |
|---|---|---|
| A0 | N=8, no Byteman, R = max sustainable (≤ 500/s), direct 2 GiB, ×1 | natural drain: does the queue fill without injected delay? |
| A1 | N=8, Byteman delay d (start 100 ms, cw=32 ⇒ D≈320/s; raise to 500 ms if not filling), direct 2 GiB, ×1–2 | measure D, λ, expiry; fix d and R |
| S (sweep) | N = 1/2/4/8 at the same R, direct 2 GiB, ×3 each | K(N) vs U(N), per-connection exclusive, reserve, throttling, expiry |
| O (OOM stage) | N=8 at direct 512 MiB ×3; then budget search 768/640/… (geometric then bisect, ×3 at the largest failing, ×1–2 elsewhere) | endpoint n/N per budget |
| Ctrl (V2) | N=1 at the failing budget ×3 | low multiplicity alone survives |
| Int (V4) | N=2 at the failing budget, same total R ×3 (reduced N); if time, G=256 MiB at N=8 ×3 (bounded aggregate) | intervention removes endpoint, throughput recorded |

If A0 fills the queue to ≥ 95 % K_max at N=8 without Byteman, all later stages run **without** Byteman
(label could then be `deployment` apart from hints-off); otherwise all later stages use the frozen Byteman
delay (label `diagnostic`).

## 5. Measurement

`C1Sample` (JMX + CQL, 1 s): direct pool MemoryUsed/Count (U), heap used, `MutationStage` pending/active,
Cassandra `BufferPool` metrics (networking/chunk-cache size, overflow), sum over peers of `using_bytes`,
`using_reserve_bytes` (K), max per-peer using, peers with using > 0 (active N), throttled/received/
processed/expired counts. Victim GC log (unified, default), system.log, `memory.events` of the scope.
Client: offered/acked per 5 s. NMT is **not** enabled (overhead). Heap dumps not needed for a direct OOM;
on direct OOM the first error + stack from system.log is kept. One `jcmd VM.native_memory` is not used.

## 6. Stopping budget

Wall-clock limit **7 h from 09:30 (stop launching arms at 15:45, write-up by 16:30)**; at most **45 arms**;
max offered R = 500 writes/s of 1 MiB. Stop a stage early if: coordinator or fast replica OOM (sender
failure is not a C1 positive), the controller/host load from our processes exceeds 28 of 32 cores, or the
victim fails for a reason other than the endpoint. No escalation after OOM beyond the planned budget search.
Resumability: every arm writes `/mydata/c1r4/runs/<arm>/` (args, samples, outcome) and appends one line to
`/mydata/c1r4/runs/summary.txt`; the batch scripts are in `harness-run4/`.

## Amendment 1 (2026-11-12 09:42, after A0 calibration, before any sweep/OOM-stage reading)

Calibration evidence (`/mydata/c1r4/runs/`):
- `INVALID_A0_nat_N8_r400`: **invalid** — the victim's 12 GiB safety scope OOM-killed it (dmesg
  `CONSTRAINT_MEMCG`, `c1r4V-*.scope`) because its tmpfs data (random 1 MiB blobs, ~8 GB of sstables in
  60 s) is charged to its cgroup. Not an endpoint; excluded.
- Fixes: blobs are **zero-filled** (sstables compress to ~nothing; commitlog bounded by
  `commitlog_total_space` 2 GiB), F gets 8 GiB heap and cores 8–15, coordinators 16–23.
- `A0_nat_N8_r300` (no Byteman, all defaults incl. T = 2 s): victim keeps up (received = processed,
  K_peak 57 MiB). `A0_nat_N8_r500`: **the receive queue reaches the ceiling naturally**: K_peak 543 MiB
  = K_max(8) (511 reserve + 8×4 exclusive), throttled 2945, expired 2486, MutationStage pending 511, for a
  ~25 s episode (memtable-flush / heap-pressure stall at the 2 GiB heap), then drains; U_peak 683 MiB
  direct (baseline 50); victim alive at direct 2 GiB; client 505/s, 0 errors.

Decisions (frozen from here):
1. **No Byteman.** All later arms run the natural path at **R = 500/s total** (design max), W = 90 s,
   default `write_request_timeout` 2 s on every instance. Byteman is dropped; the delay file is kept unused.
2. **Timeout check (run-3 open item) answered:** with T = 2 s the ceiling is reached because a
   blocked MutationStage does not dequeue (and so does not expire) queued messages; λ·T is not the cap
   while the stage is stalled. T stays at default.
3. Because fill is **episodic**, endpoint n/N may be < N/N; repetitions stay ≥ 3 and n/N is reported.
4. Arms: sweep N = 1/2/4 at direct 2048 ×1 (N=8 from A0_r500, + repeats from the 2048 arms if time);
   OOM stage N=8 at 512 ×3, N=4 at 512 ×1–3; control N=1 at 512 ×3; intervention N=2 at 512 ×3
   (same R); budget search for N=8 upward (768, then 640/704 …), ×3 at the largest failing budget.
5. Updated prediction: U ≈ 50 (baseline) + K + 20–80 MiB pool slack/retention ⇒ at N=8 U_peak ≈ 620–680 MiB
   when the ceiling is reached: **direct OOM at 512 MiB for N=8 and N=4**, survive at N=1 (≈ 230) and
   N=2 (≈ 360); largest failing budget ≈ 640 MiB, none at 768 MiB.

## Amendment 2 (2026-11-12 10:35, before any condition-D reading)

Readings so far (direct 512, N=8: 3/3 direct OOM; N=1 control and N=2 intervention r1 survive; 768 N=8
survives) depend on two non-capacity deviations: `hinted_handoff_enabled: false` (supporting deviation)
and `commitlog_total_space: 2048MiB` (disk, environment). To test whether the endpoint holds **without
any supporting deviation**, a second condition **D** is added: identical (natural path, R = 500/s,
heap 2 GiB, direct 512 MiB, same build, topology, client) but the yaml differs from the shipped file only
in environment keys (cluster name, addresses, seeds, snitch, tokens, directories). Arms: D N=8 ×3,
D N=1 ×3 (control), D N=2 ×3 (intervention), queued after the budget search. Prediction: same outcome as
the hints-off condition (hints only affect the coordinators' disk/heap, not the victim's receive queue);
a coordinator failure or tmpfs exhaustion in D would stop the condition (recorded, not a C1 result).
Harness: `DEFAULTS=1` in `ctl.sh gen`.

## Amendment 3 (2026-11-12 11:06, before readings of the arms named here)

Budget search so far (N=8, hints-off condition): 512 3/3, 640 2/3, 704 0/1, 768 0/1. Refinement queued
after condition D: 672 ×3, 704 ×2 more (→ ×3), 640 ×2 more (→ ×5). The largest failing budget is the largest
with n ≥ 1 in its repetitions; reported with n/N. No further arms after these.

## Amendment 4 (2026-11-12 12:30, coordinator request, before any dump-arm reading)

V5 needs a heap dump or histogram at failure that shows the holder, not only counters. Added: **dump arms**
`DD_N8_d512_r1..r3` in condition **D** (shipped yaml, N=8, heap 2048, direct 512, R=500/s, 90 s), identical
to D_N8_d512 except `-XX:+HeapDumpOnOutOfMemoryError` on the victim (env `HEAPDUMP=1` in `ctl.sh`). The
direct OOM is thrown by Java code (no VM dump), but Cassandra then forces a heap-space OOM, which triggers the
dump before `OnOutOfMemoryError` kills the JVM; nothing changes before the failure (no NMT, no jcmd
histogram, both of which would add pre-failure GC/overhead). The arms count toward V1 for D.
Dumps go to `/mydata/c1r4/runs/<arm>/` (never `/proj`). Analysis (`harness-run4/hprof_direct.py`): every
`java.nio.DirectByteBuffer` that owns native memory (non-null `cleaner`) is an allocation of `capacity`
bytes; slices/duplicates point to their owner via `att`. Each owner's bytes are attributed by walking
referrers (up to 5 levels) of the owner and its live slices, into: (a) receive queue — slices held by
`ShareableBytes` reachable from `InboundMessageHandler$LargeMessage` / queued `ProcessLargeMessage` tasks /
frame decoders; (b) `BufferPool` chunk memory not in a live slice (pool free/retained); (c) `DataOutputBuffer`
scratch; (d) other. Prediction: (a) ≥ 75 % of the ≈ 512 MiB live direct memory; (c) ≤ 50 MiB.
If the dump is not written (e.g. the JVM dies first), the arm still counts for V1 and the dump is retried
once more (≤ 2 extra arms).

## Amendment 5 (2026-11-12 12:44, coordinator request on Netty accounting, before this arm's reading)

The DD dumps show Netty's own `PlatformDependent.DIRECT_MEMORY_COUNTER` (no-cleaner buffers, not seen by the
JMX java.nio pool and capped separately at the same `MaxDirectMemorySize`). To learn whether that part varies
with load, one **diagnostic probe arm** `NP_N8_d2048` (condition D, N=8, direct 2048, R=500/s) takes
`jcmd GC.heap_dump` of the victim once before load (idle) and once when K first exceeds 440 MiB. Intrusive
(dumps pause the JVM); not used for V1–V4, only to read the Netty counter and the java.nio owners at idle
vs at the ceiling. Harness: `harness-run4/netty-probe.sh`.

## Resume note (2026-11-12 12:52, paused by the researcher's request)

**State:** no arm was running when the pause arrived; nothing is void. All planned arms are done:
calibration A0, sweep N=1/2/4 (2048), condition H (O/C/I at 512, N=4 at 512, budget search 640–768),
condition D (N=8 ×4, N=1 ×3, N=2 ×3 at 512), dump arms DD_N8_d512_r1–r3 (3/3, analysed), Netty probe
NP_N8_d2048. Case file `../internode_application_receive_queue_capacity--multiplicity--run4.md` is
up to date (§3.4b dumps, §3.4c Netty, V1–V7). Verified at 12:52: no c1r4 JVM, port, scope or tmpfs left.
Raw data and dumps: `/mydata/c1r4/runs/` (summary line per arm in `summary.txt`).

**Remaining (only if the reviewer asks):** heap dumps in condition H (H's V5 currently relies on D's dumps);
any further budget refinement. Nothing else is open in this design.

**Commands to continue** (from the C1 case folder, on pc96):
```
mkdir -p /mydata/c1r4/shm && sudo mount -t tmpfs -o size=24g,uid=$(id -u),gid=$(id -g) tmpfs /mydata/c1r4/shm
harness-run4/build.sh                     # only if /mydata/c1r4/cls is missing
# example: dump arms in condition H (hints off), N=8, 512 MiB direct
HEAPDUMP=1 nohup harness-run4/batch1.sh "DH_N8_d512_r1 8 500 512 none 90" "DH_N8_d512_r2 8 500 512 none 90" \
  "DH_N8_d512_r3 8 500 512 none 90" > /mydata/c1r4/runs/batch8.log 2>&1 &
# condition D instead: prefix DEFAULTS=1. Analyse a dump:
(cd /mydata/c1r4/runs/<arm> && python3 -I <case>/harness-run4/hprof_direct.py cassandra-*.hprof 6 --detail > direct-holders.txt)
# afterwards: harness-run4/ctl.sh stop all; rm -rf /mydata/c1r4/shm/*; sudo umount /mydata/c1r4/shm; rmdir /mydata/c1r4/shm
```
Run only one batch at a time; `batch1.sh` skips arms that already have `outcome.txt`.
