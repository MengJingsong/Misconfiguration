# DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS (custom) — run history

The per-run case file of this case, kept verbatim after the case was verified and consolidated into
[`DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md`](DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md)
(filing rule: protocol *Case evidence and batch status*, amended 2026-11-11). It holds run 8
(2026-11-03, `pc41`) with its 2026-11-11 status line, followed by the R2 recheck design and its
amendment, both written before the recheck readings. Mechanical changes only: every heading is demoted
one level, and relative links are repointed for the new location (the harness folder link now points
to this folder; links to the protocol and to if-check-exp gain one `../`). The run-8 harness and logs
are unchanged beside this file (`oom-run.sh`, `dob.yaml`, `hints.yaml`, `logs/`); the recheck's are in
`recheck-2026-11-11/`.

| Part | Original file |
|---|---|
| [Run 8 — 2026-11-03, pc41](#run-8) | `cases/candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md` (before 2026-11-11: `cases/convergence/…`) |
| [R2 recheck design and amendment — 2026-11-11, apt140](#recheck-design-2026-11-11) | same file, sections appended 2026-11-11 before the recheck readings |

---

<a id="run-8"></a>

## DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS — convergence case (run 8)

> **Status (2026-11-11): `candidate (pre-protocol)`.** Moved from `convergence/` to `candidates/`: filed before the 2026-11-06 protocol and does not meet the V1–V5 promotion rule ([protocol](../../../../verification-protocol.md#verification-status-amended-2026-11-11)). Evidence held: converge 1 run; each alone 1 run; `converge_Ldefault` intervention 1 run; first-error stack and heap dump kept. The OOM recorded below stands; rerun ×3 with matched controls and an intervention ×3 to return it to `convergence/`.

> **Run:** 2026-11-03, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (`pc41`, 40 cores, 251 GiB), same build as runs 1-7 (`~/cassandra-run1`, cassandra-5.0.9, unchanged). Third off-heap pair; both constraints are new to OOM-exp.
>
> **Harness:** [`DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom/`](./) (`oom-run.sh`, the two `cassandra-stress` user profiles `dob.yaml` and `hints.yaml`, and per-arm `logs/<arm>/`: summaries with every 5-s sample, yaml diffs, JVM-flag excerpts, stress tails, thread-dump and histogram excerpts; for `converge`, the `OutOfMemoryError` stacks, the GC-log tail and the heap-dump listing). Full logs, thread dumps and the 687 MB heap dump stay on the node in `~/oom-direct-run8/logs/`.
>
> **Outcome: OOMed.** Each pool alone stayed at or under 70% of a 560 MiB `-XX:MaxDirectMemorySize` budget (hints pool 50%, DOB scratch buffers 69.5%). Together, with the hints pool parked at its 8-slab cap, the DOB burst hit `OutOfMemoryError: Direct buffer memory` about 7 s in. Cassandra turned it into a forced heap OOM and `-XX:OnOutOfMemoryError=kill -9` killed the JVM. Control: the same convergence arm with only `dob_max_recycle_bytes` back at its default did not OOM.

### 1. Constraints and capacities

| | `DOB_MAX_RECYCLE_BYTES` | `MAX_HINT_BUFFERS` |
|---|---|---|
| if-check-exp | [`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md), true positive (unit and cluster Confirmed) | [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md), true positive (unit and cluster Confirmed) |
| Capacity check | `DataOutputBuffer$1$1.close():73`: a thread's scratch buffer is kept if `capacity <= L`, else replaced by 128 B | `HintsBufferPool.switchCurrentBuffer():111-118`: a new slab only while `allocatedBuffers < n`, else the writer waits in `reserveBuffers.take()` |
| What it caps | Idle direct bytes kept per thread between uses: at most `T × max(L, 128)` per node, *T* = threads that ever serialized a large item | Direct slabs of the hints pool: at most `n × bufferSize`, `bufferSize = max(2 × max_mutation_size, 32 MiB)` |
| Standing pool? | Yes: a kept buffer stays on its thread until that thread next uses it (if-check-exp: persistence confirmed, 70 s) | Yes: slabs are recycled, never freed (`HintsBufferPool` has no free path except `close()`) |
| Knob, default | JVM property `-Dcassandra.dob_max_recycle_bytes`, default 1 MiB, restart-only | JVM property `-Dcassandra.MAX_HINT_BUFFERS`, default 3, restart-only |
| Setting here | **L = 8 MiB** (8,388,608) | **n = 8** (slab 32 MiB at the default `max_mutation_size` 16 MiB) |
| Allocation path | `ByteBuffer.allocateDirect` (default `cassandra.dob.allocate_type`) | `ByteBuffer.allocateDirect` (`HintsBuffer.create`, `HintsBuffer.java:77`) |

**Shared budget: the JVM's direct-buffer limit, `-XX:MaxDirectMemorySize=560m`.** Both pools are `java.nio.DirectByteBuffer`s, reserved through `Bits.reserveMemory`, so here the JVM flag is the literal budget both draw on. This is unlike runs 4-7, whose pools are JNA `malloc` and needed a cgroup. (Netty's pooled buffers use a separate counter and do not count against it. NMT `Other` is larger than the JDK direct pool for that reason; both are recorded.) Reading: the JDK `BufferPool` MXBean `java.nio:type=BufferPool,name=direct` (`MemoryUsed`, `Count`).

**Fixed in every arm:** `-Xmx3072M` (heap is not the budget; sized so it never fills: see §3), `-XX:MaxDirectMemorySize=560m`, `-Dcassandra.dob_max_recycle_bytes=8388608`, `-Dcassandra.MAX_HINT_BUFFERS=8`, `-XX:NativeMemoryTracking=summary`; shipped yaml plus ring settings only (`n1-cassandra.yaml.diff`: addresses, one token, `GossipingPropertyFileSnitch`, local directories, `max_hint_window: 24h`).

**Topology.** Hints need an unreachable replica, so this is a 2-node loopback ring like run 3's. N1 = 127.0.0.2, dc1, the node under test. N2 = 127.0.0.3, dc2, up only while the ring and schema are created, then `kill -9`'d before any reading. Run 3's two-JVM contention confound cannot arise: only N1 runs during measurement. Keyspaces: `dobks` `{dc1: 1}` (local only, never hinted) and `hintks` `{dc1: 1, dc2: 1}` (every write hints for N2). A fresh ring, with fresh data on both nodes, is built for every arm.

### 2. Verification solution

**Workloads** (`cassandra-stress user`, protocol v4, profiles without schema definitions: see "Harness defect" below):
- *hints*: 6,000,000 single-row inserts, 1 KiB blob, into `hintks`, 64 threads, CL ONE, capped at 240 s.
- *dob*: 1,500 single-row inserts, 4,000,000-byte blob, into `dobks`, 8 threads, CL ONE. Each insert is a mutation of *S* ≈ 4.0 MB, which `CommitLog.add` serializes into the thread's scratch buffer field by field, ending at *C* = 2(*S* − 1) ≈ 7.63 MiB (the end-of-partition byte doubles it; if-check-exp §Rough sizing). *C* ≤ *L* = 8 MiB, so every thread keeps it.

**Calibration** (budget 4096 MiB, same node, `logs/cal_*`):
- `cal_hints` (n = 12): the pool grew to 9 slabs (+289 MiB) under natural load and held it after the load stopped. So n = 8 is reachable without a Byteman hold.
- `cal_dob` (14 MiB blobs, L = 32 MiB): +1206 MiB kept (about 43 threads × 28 MiB). Too large against the hints pool, and the client hit write timeouts.
- `cal_dob2` (4 MB blobs, L = 8 MiB): +337 MiB kept (about 44 threads × 7.63 MiB), flat through the hold. This sizing was used.

**Sizing (prediction, before the 560 MiB arms).** Idle direct = 55 MiB, which includes the hints pool's first slab.

| Arm | Idle | Pool growth | Predicted total | % of 560 |
|---|---|---|---|---|
| hints alone (n = 8) | 55 | 7 × 32 = 224 | 279 | 50% |
| DOB alone (L = 8 MiB) | 55 | 337 | 392 | 70% |
| both | 55 | 561 | **616** | **110%** |

Margin used: each alone ≥ 30% free; together 56 MiB over the budget.

**Arms** (all at 560 MiB, all with the same JVM flags; only the workload differs):
`H_alone` (hints), `D_alone` (dob), `converge` (hints, then dob 20 s later once the pool is at its cap; both run together), and `converge_Ldefault`, an attribution control: `converge` with only `dob_max_recycle_bytes` at its 1 MiB default.

**Instruments.** Every 5 s: JDK direct `MemoryUsed`/`Count` (`nodetool sjk mx`), NMT `Other`, `RssAnon`, heap used (`jcmd GC.heap_info`). Every third sample during load, `jstack`: a thread in `LinkedBlockingQueue.take` under `HintsBufferPool.switchCurrentBuffer` is direct evidence the pool is at *n*. At the end, a `GC.class_histogram` count of live `HintsBuffer`s. After the arm: `system.log` and stdout for `OutOfMemoryError`, `gc.log`, heap-dump presence, `dmesg`. Command: `oom-run.sh arm <name> 560 <L> 8 <workloads> [overlap]`.

**Harness defect found and fixed (same family as run 6's).** `cassandra-stress write` always issues `CREATE KEYSPACE` before writing, even when the table exists. Under the other workload's load that statement timed out (driver `OperationTimedOutException`, 12 s) and the client exited having written nothing. This voided two convergence attempts, one per order (`logs/converge-void-schema-timeout`: DOB client wrote nothing; `logs/converge-void-hints-schema-timeout`: hints client wrote nothing, pool stayed at 1 slab). Fixed by switching both workloads to `cassandra-stress user` profiles with no `keyspace_definition`/`table_definition`, which issue no schema statement (`StressProfile.maybeCreateSchema`). Both controls were re-run with the user-mode workloads so every filed arm uses the same workload. The first write-mode controls (`logs/*-writemode`) gave the same numbers (282 / 397 MiB).

### 3. Runtime results

| Arm | Idle | Peak direct | % of 560 | Pool at its cap? | Outcome |
|---|---|---|---|---|---|
| `H_alone` | 55 | 282 | 50.4% | yes: 8 live `HintsBuffer`s at the end; a writer parked in `take()` in 7 of 9 dumps; 6,000,000 writes, hints dir 6279 MiB; 281 MiB held through the hold | alive, 0 ERROR |
| `D_alone` | 55 | 389 | 69.5% | yes: +334 MiB kept (`Count` +56), flat through the hold; 1,500 writes, 0 errors | alive, 0 ERROR |
| `converge` | 55 | 281 sampled before the burst; **560 at the OOM** (the `Bits` limit) | **100% → OOM** | hints pool at its cap (281 MiB, the `H_alone` level) when the burst started | **`OutOfMemoryError: Direct buffer memory`, JVM killed** |
| `converge_Ldefault` | 55 | 287 | 51% | hints pool at its cap (8 `HintsBuffer`s); DOB kept nothing (L = 1 MiB < *C*) | alive, 0 ERROR; 1,500 DOB writes |

**`converge` timeline (local time, EST = UTC−5; `system.log` timestamps are UTC).**
- 20:05:50: hints workload starts. 20:06:08: direct 280 MiB, the pool at its 8-slab level. 20:06:25: 281 MiB.
- 20:06:25: DOB workload starts (hints still running).
- 20:06:32.666: the first `java.lang.OutOfMemoryError: Direct buffer memory` (`Bits.reserveMemory:175` ← `DataOutputBuffer$1$1.allocate:87` ← `expandToFit:178`), thrown while a scratch buffer grew: at `UnfilteredSerializer.writeEndOfPartition:415` (the doubling of the last byte) and at `ByteBufferAccessor.write:63` (the 4 MB value). 8 throws in all, on `MutationStage-17`, `MutationStage-21` and `Native-Transport-Requests-51` (`logs/converge/oom-jvm.txt`, `n1-system-oom-excerpt.txt`).
- 20:06:32.668: `JVMStabilityInspector` logs "Force heap space OutOfMemoryError in the presence of" that direct OOM. This is Cassandra's own mechanism (CASSANDRA-15214/17128): a direct OOM cannot trigger the JVM's OOM options, so it forces a heap OOM. The heap held 570 of 3072 MiB at the forced full GCs (`n1-gc-tail.txt`), so heap pressure is not the cause.
- 20:06:34.946: `ReportJavaOutOfMemory` safepoint; heap dump written (687 MB, `hprof.txt`); `-XX:OnOutOfMemoryError=kill -9 %p` killed the JVM. 20:06:37: the next sample finds N1 gone.
- No kernel OOM-kill (none expected: the JVM's own limit fires first; the node has 251 GiB).

**Client totals after the kill are not writes.** Both clients printed "Total errors 0" and their full partition counts. The ops after the kill were `NoHostAvailableException` failures (1442 in the DOB client), which this cassandra-stress version still counts as completed. Trust the server-side counts (`tablestats` Write Count) in the alone arms, and the OOM timestamp here.

**Prediction vs observation.** Predicted demand 616 MiB against a 560 MiB limit; the limit was hit and the node died. The kill came about 7 s into the burst, sooner than `D_alone`'s retention curve would supply the missing ~280 MiB (+115 MiB at 7 s, +264 MiB at 15 s). So writes in flight at that moment (each grows a fresh buffer through 3(*S* − 1) ≈ 12 MB transiently; the coordinator thread serializes too) must have covered the rest. The 5-s sampling cannot split kept from in-flight bytes inside those 7 s. The attribution control settles which constraint matters: with L at its default, the same workloads, the same budget and the same full hints pool stayed at 51%.

**Heap check.** Heap used peaked under 3 GiB in every arm (G1 collects at that point; "used" includes garbage). `converge` OOMed with 570 MiB of heap after GC. No arm logged a heap OOM of its own.

### 4. Conclusion

**The pair converges to a real OOM.** Cassandra has no mechanism that caps the combined direct-memory usage of these two pools. Each is enforced: the hints pool stopped at 8 slabs with its writer parked, and every scratch buffer above L would have been dropped. Yet reaching both capacities together exhausted `MaxDirectMemorySize` and killed the node, though each alone left 30-50% of it free. Reproduced with L = 8 MiB, n = 8 (32 MiB slabs), a 560 MiB direct budget, 1 KiB hinted writes to a down replica and 4 MB local writes on 8 client threads. This is the sizing found, with a 10% predicted overshoot; the minimum boundary was not searched.

**What is new compared with runs 4-7.** (1) The budget is the JVM's own direct-memory limit, not a cgroup: both pools go through `ByteBuffer.allocateDirect`, so the flag binds them. Cassandra converts the resulting direct OOM into a JVM kill (forced heap OOM, then `OnOutOfMemoryError`), so a node configured with Cassandra's default OOM handling dies rather than limping. (2) Both knobs are JVM system properties, not yaml settings. (3) Hint backpressure interacts with the write path: with the pool at its cap, 32 `MutationStage` workers were in `switchCurrentBuffer`, one parked in `take()` and the rest blocked on the pool's monitor (`H_alone` dumps). Writes still ran, but slower: in `converge_Ldefault` the hints client reached only 2.89M of 6M rows in 240 s, against 6M in 3 min alone.

**Target-3 note.** Moderately realistic. Raising `dob_max_recycle_bytes` is a plausible tuning step for an operator who writes multi-MB rows and sees allocation churn. A down replica fills the hints pool by itself; raising `MAX_HINT_BUFFERS` is less common, and the default of 3 slabs (96 MiB) would need a proportionally smaller direct budget or larger L to converge. `MaxDirectMemorySize` defaults to `-Xmx` and is often set lower in containers. The two workloads (large local writes plus any write traffic while a replica is down) are ordinary and need no deliberate engineering beyond running at the same time; the order here (hints first) is only for a clean reading.

### Instrument check and process hygiene

- Every arm's N1 command line was checked for `-Xmx3072M`, `-XX:MaxDirectMemorySize=560m`, the two properties, and (for the control) L = 1048576 (`n1-jvm-args-excerpt.txt`). `MaxDirectMemorySize` appears twice on the command line (`cassandra-env.sh` sets 15872M first); the later value wins, confirmed by the OOM firing at the 560 MiB level.
- Pool-at-cap evidence for the hints pool: `HintsBuffer` histogram count = 8 and parked writers in `H_alone`/`converge_Ldefault`; for DOB, `Count` and `MemoryUsed` rose by about 44 buffers × 7.63 MiB and stayed flat, and `converge_Ldefault` shows the same workload keeps nothing at the default L.
- After every arm `pgrep` for `CassandraDaemon` and `cassandra-stress` was empty (`CHECK PASS` lines in each `session.log` on the node). Node data, commit log, hints and logs stayed under `~/oom-direct-run8/` on local disk; nothing written to `/proj` except this folder; the repository's `systems/cassandra/source/` untouched.

<a id="recheck-design-2026-11-11"></a>

### Recheck design (2026-11-11)

Written before any recheck reading. Campaign-plan row **R2** (pre-protocol recheck, V1–V5). Same build,
budget, settings, workload and harness as the filed run 8; only the node and the run-data paths change.

**Node (environment change, disclosed).** `apt140` (`node0.jason92-325433.misconfiguration-pg0.apt.emulab.net`):
APT r320, 16 threads Intel Xeon E5-2450 @ 2.10 GHz, 15.5 GiB RAM, 8 GiB swap (3 MiB used at start),
`/mydata` 1.7 TB local, Linux 5.15.0-198, cgroup v2, OpenJDK 11.0.33. Idle; this is the only case on the
node. The original run was on `pc41` (40 cores, 251 GiB). Fewer cores and less RAM can change hint and
DOB throughput, the number of threads that ever serialize a 4 MB mutation (*T*), and the time the hints
pool needs to reach 8 slabs. `cassandra-env.sh` derives a different first `-XX:MaxDirectMemorySize` on
this node; the harness's later `-XX:MaxDirectMemorySize=560m` still wins (checked per arm from
`n1-jvm-args.txt`; the OOM level is the second check).

**Build.** `cp -a ~/cassandra-b1 /mydata/oom-recheck/R2/cassandra` on apt140: cassandra-5.0.9, git tree
`b796bcfda7c9640fa41257544a9fe62c1aec634a` (same source tree as the filed `~/cassandra-run1`), unmodified,
`cassandra-stress` from `build/classes/stress`.

**Source re-check (pinned source `systems/cassandra/source/`, read-only).** Unchanged from §1:
`DataOutputBuffer.java:53` (`MAX_RECYCLE_BUFFER_SIZE = DOB_MAX_RECYCLE_BYTES`), `:63` (`scratchBuffer` is a
`FastThreadLocal<DataOutputBuffer>`: the kept direct buffer hangs off a per-thread
`DataOutputBuffer$1$1.buffer`), `:73` (keep if `capacity <= L`, else replace with 128 B), `:87`
(`ByteBuffer.allocateDirect`); `HintsBufferPool.java:111-118` (`switchCurrentBuffer`: new slab only while
`allocatedBuffers < MAX_ALLOCATED_BUFFERS`, else `reserveBuffers.take()`); `HintsBuffer.java:60,77`
(`slab` field, `ByteBuffer.allocateDirect(slabSize)`); `HintsService.java:110`
(`bufferSize = max(2 × max_mutation_size, 32 MiB)` = 32 MiB). `cassandra-env.sh:197-200` writes the OOM heap
dump to `$CASSANDRA_HEAPDUMP_DIR` (default the log dir); the harness sets it to the arm's log folder on
`/mydata`.

**Harness** (`/mydata/oom-recheck/R2/oom-run.sh`, diff against the filed script in
[`recheck-2026-11-11/harness-R2.diff`](recheck-2026-11-11/harness-R2.diff)):
paths (`CH=/mydata/oom-recheck/R2/cassandra`, `BASE=/mydata/oom-recheck/R2`, `dob.yaml`/`hints.yaml` in
BASE); the filed env overrides pinned as defaults (`N_HINTS=6000000`, `N_DOB=1500`, `HINT_LEAD=20`;
unchanged defaults `HINT_SECS=240`, `HINT_THREADS=64`, `DOB_THREADS=8`, `DOB_SIZE=4000000`); heap dump into
the arm folder (`CASSANDRA_HEAPDUMP_DIR=$D`); added instrumentation only: per-sample N1 `VmSwap`, system
swap used and `MemAvailable`; workload start timestamps; `tablestats` at the end of overlap arms (server-side
write counts for the intervention's throughput); N1 `gc.log` copied into the arm folder. Arms run detached
via `run-seq.sh` (sequential, clean ring per arm, `pgrep` check after each).

**Commands** (each from a clean ring; `N_HINTS=6000000 N_DOB=1500 HINT_LEAD=20` exported):
- validation (modest load, budget 4096 MiB, not a reading): `N_HINTS=300000 N_DOB=100 oom-run.sh arm val 4096 8388608 8 hints,dob`
- `H_alone` ×3: `oom-run.sh arm H_alone-rN 560 8388608 8 hints`
- `D_alone` ×3: `oom-run.sh arm D_alone-rN 560 8388608 8 dob`
- `converge` ×3: `oom-run.sh arm converge-rN 560 8388608 8 hints,dob overlap`
- intervention `converge_Ldefault` ×3: `oom-run.sh arm converge_Ldefault-rN 560 1048576 8 hints,dob overlap`

Order: validation; H_alone ×3 and D_alone ×3; then the lead-time check (below); then converge and
converge_Ldefault alternating.

**Lead-time check (before any converge reading).** The filed lead put the DOB start about 35 s after the
hints start (`HINT_LEAD=20` plus sampling time), when the pool was already at 280 MiB (8 slabs). From the
H_alone timelines on apt140 I take the time from hints start to direct ≥ 275 MiB. If the worst of the three
plus 5 s is longer than the effective lead (hints start → dob start, measured in the validation and
H_alone runs' sampling cadence), `HINT_LEAD` is raised in a dated amendment here before converge runs.
Each converge run must also show direct ≥ 275 MiB in the last `h` sample before the DOB start; a converge
run in which the pool is not at its cap at the burst is reported separately, not counted toward V1.

**Memory fit.** N1 `-Xms/-Xmx3072M` pre-touched (≈ 3.8 GB RSS idle) + ≤ 560 MiB direct + metaspace/threads
≈ 4.6 GB; N2 `-Xmx1024M` ≈ 1.4 GB only during ring setup (killed before readings); two `cassandra-stress`
JVMs ≤ ≈ 1 GB each in use. Peak ≈ 7.5 GB of 15.5 GiB. Pass condition: N1 `VmSwap` = 0 in every reading
(recorded per sample).

**Predictions** (560 MiB = 587,202,560 B budget; idle ≈ 55 MiB including the first slab):
| Arm | Prediction | Pass criterion |
|---|---|---|
| `H_alone` | ≈ 281 MiB (50%), 8 `HintsBuffer`s live at the end, writers parked in `take()` | alive, 0 ERROR, peak ≤ 392 MiB (70%) |
| `D_alone` | ≈ 55 + *T* × 7.63 MiB; filed *T* ≈ 44 → ≈ 389 MiB (69.5%). *T* may differ on 16 threads (MutationStage is 32 threads regardless of cores; native-transport threads also serialize): range 340–400 MiB | alive, 0 ERROR, peak ≤ 392 MiB (70%); a 70–75% reading is reported as a margin miss |
| `converge` | ≈ 281 + DOB demand → `OutOfMemoryError: Direct buffer memory` within ≈ 5–20 s of the burst, forced heap OOM, heap dump, `kill -9` | endpoint = first direct-buffer OOM in `system.log`; counted if the pool was at its cap at the burst |
| `converge_Ldefault` | ≈ 285 MiB (51%), DOB keeps nothing (C ≈ 7.63 MiB > L = 1 MiB) | alive, 0 ERROR, 1,500 DOB writes server-side (`tablestats`), hints writes recorded |

**Endpoint and V1–V5 criteria (protocol *Verification status*).**
- V1: direct-buffer `OutOfMemoryError` in `converge` ≥ 3 of N (N = 3; extend to ≤ 5 only for mixed outcomes).
- V2: `H_alone` and `D_alone` each 3/3 alive with no OOM, under the 70% margin.
- V3: U per domain independent of any control counter: hints domain = JDK direct `MemoryUsed`/`Count` plus
  `GC.class_histogram` live `HintsBuffer` count (the pool's own `allocatedBuffers` counter, K, is not read);
  DOB domain = direct `MemoryUsed` rise and `Count` rise in D_alone, and the heap-dump breakdown below.
- V4: `converge_Ldefault` 3/3 alive at the same budget with its throughput recorded (hints and DOB
  server-side write counts, client op rates).
- V5: first OOM with thread and stack from `system.log`/stdout; at least one OOM heap dump analysed with a
  small python hprof parser (`/mydata/oom-recheck/R2/tools/hprof_direct.py`, run with `python3 -I`; no MAT on the
  node): sum of `DirectByteBuffer` capacities of memory-owning buffers (`cleaner != null`) grouped by the
  referring holder (`HintsBuffer.slab` vs `DataOutputBuffer$1$1.buffer` scratch, reached from
  `InternalThreadLocalMap`/`FastThreadLocalThread`), with thread names, plus buffers with no strong
  referrer (dropped, awaiting their `Cleaner`, still charged to the `Bits` limit).

**Intervention.** `converge_Ldefault`: only `dob_max_recycle_bytes` back to its 1 MiB default. Predicted to
survive 3/3 with the hints pool still full (≈ 51%).

**Stopping budget.** ≤ 4 h wall (started 12:40 MST on apt140), ≤ 20 arm executions including validation.
No escalation after an OOM; no new sizing unless an alone arm breaks the filed premise (then a dated
amendment here first).

#### Amendment (2026-11-11, 13:23 MST, before any converge reading): lead time, and D_alone margin

**Evidence (apt140, first five alone arms; full numbers in the recheck results).**
- `H_alone` r1–r3: pool at 8 slabs (≥ 275 MiB direct, 8 live `HintsBuffer`s, writer parked in `take()`)
  reached 73 s, 84 s and 47 s after the hints start (pc41: ≈ 18 s). Plateau 277–278 MiB (49.6%).
  With `HINT_LEAD=20` the overlap loop runs 4 × (5 s sleep + one sample); a sample takes ≈ 5–9 s on
  this node, so the DOB burst would start ≈ 45–55 s after the hints start, before the pool is at its
  cap in two of three runs. **`HINT_LEAD` is raised to 50** (10 sample iterations, ≈ 100–130 s
  effective lead, ≥ 84 s + 5 s). This changes only when the burst starts, not what runs: the filed
  intent ("hints, then dob once the pool is at its cap; both run together") is kept, and the hints
  workload (240 s cap) still runs during the first ≈ 110–140 s of the burst. The per-run pass condition
  (direct ≥ 275 MiB in the last `h` sample before `dob start`) stays.
- `D_alone` r1–r2: idle 51 MiB, plateau 392–400 MiB (sampled peak 400 = 71.4%, 393 = 70.2%), i.e. a
  retained increment of +341–349 MiB (≈ 45 threads × 7.63 MiB; filed +334 MiB on pc41). The filed
  premise still holds (each alone survives with ≥ 28% of the budget free; together the predicted
  demand is 51 + 227 + ≈ 345 ≈ 623 MiB > 560 MiB), so the filed condition is **kept unchanged**
  (brief: prefer keeping it). But the declared 70% margin is missed by ≤ 1.5 pp on this node; this
  is reported as a margin miss in V2, not hidden by re-sizing.

Converge arms from here on: `HINT_LEAD=50 oom-run.sh arm converge-rN 560 8388608 8 hints,dob overlap` and
`HINT_LEAD=50 oom-run.sh arm converge_Ldefault-rN 560 1048576 8 hints,dob overlap` (other pins unchanged).
