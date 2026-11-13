# DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS at defaults — default-value convergence case (run 1)

> **Update (2026-11-12, R6-V):** at the acceptable budget (512 MiB direct, 2 GiB heap, both settings at defaults) the pair does **not** OOM (0/3; peak ≈ 260 MiB, demand ceiling ≈ 398 MiB) → [`negative`](../negatives/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default-v7/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default-v7.md). The OOM below reproduces only under ≈ 255–265 MiB (250 MiB: 3/3), i.e. at tightened budgets. This file stays as the pre-protocol diagnostic record.
>
> **Status (2026-11-11): `candidate (pre-protocol)`.** Moved from `convergence/` to `candidates/`: filed before the 2026-11-06 protocol and does not meet the V1–V5 promotion rule ([protocol](../../../verification-protocol.md#verification-status-amended-2026-11-11)). Evidence held: design B converge 1 run; each alone 1 run; no valid intervention (design A's no-hints control also died); first-error stack and heap dump kept. The OOM recorded below stands; rerun ×3 with matched controls and an intervention ×3 to return it to `convergence/`.

> **Run:** 2026-11-04, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (`pc41`, 40 cores, 251 GiB), same build as convergence runs 1-8 (`~/cassandra-run1`, cassandra-5.0.9). First run of [`default-convergence-playbook.md`](../../../default-convergence-playbook.md). Same pair as convergence run 8 ([`DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md`](../candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md)), which raised both knobs. Here neither knob is set.
>
> **Harness:** [`DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default/`](DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default/) (`oom-run.sh` is run 8's harness with both `-D` properties and run 8's `max_hint_window: 24h` removed; profiles `dob.yaml`, `hints.yaml`, `local.yaml`; `excerpt.sh`; per-arm `logs/<arm>/` excerpts). Full logs on the node in `~/oom-default-run1/logs/`. Only `B_converge`'s heap dump (784 MB) is kept, in `~/oom-default-run1/N1-logs/`; each arm's start clears that folder, which deleted the earlier arms' dumps.
>
> **Outcome: OOMed, strict default.** The final design is design B, at a 192 MiB `-XX:MaxDirectMemorySize`:
> - The hints pool alone stayed at 63% of the budget.
> - The DOB scratch buffers alone stayed at 69.3%, under the same total request concurrency as the convergence arm.
> - Together they hit `OutOfMemoryError: Direct buffer memory` 7 s into the DOB burst. Cassandra forced a heap OOM and `kill -9`'d the JVM.
>
> The first design (A, 185 MiB) OOMed twice too. But its attribution control, which removed the hints, *also* died, so A is not filed as the result (§3.1). The window at defaults exists only within a band about 15 MiB wide (§2.2).

## 1. Constraints and capacities

**Strict default.** The arms set neither constraint, no other yaml key except environment lines, and only budget-class JVM flags (§2.1).

| | `DOB_MAX_RECYCLE_BYTES` | `MAX_HINT_BUFFERS` |
|---|---|---|
| if-check-exp | [`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided`](../../../../if-check-exp/cassandra/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md), true positive | [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided`](../../../../if-check-exp/cassandra/stage3-ai-deep-read/cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md), true positive |
| Capacity check | `DataOutputBuffer.java:73`: a thread's scratch buffer is kept if `capacity <= MAX_RECYCLE_BUFFER_SIZE`, otherwise replaced by 128 B | `HintsBufferPool.java:113-118`: a new slab only while `allocatedBuffers < MAX_ALLOCATED_BUFFERS`, otherwise the writer waits in `reserveBuffers.take()` |
| What it caps | Idle direct bytes per thread: at most *T* × 1 MiB, where *T* is the number of threads that have serialized an item of up to 1 MiB | Direct slabs of the hints pool: at most 3 × `bufferSize` |
| Standing pool? | Yes (kept until the thread's next use; flat through every hold below) | Yes (slabs recycled, never freed) |
| **Default rule** | `CassandraRelevantProperties.java:204`: `cassandra.dob_max_recycle_bytes` = 1024 × 1024; read at `DataOutputBuffer.java:53` | `CassandraRelevantProperties.java:351`: `cassandra.MAX_HINT_BUFFERS` = 3 (`HintsBufferPool.java:41`). Slab = `max(2 × max_mutation_size, 32 MiB)` (`HintsService.java:110`, `MIN_BUFFER_SIZE` at `:79`). `max_mutation_size` is unset in the shipped yaml, so it is `commitlog_segment_size / 2` = 16 MiB (`DatabaseDescriptor.java:898-899`; shipped `commitlog_segment_size: 32MiB`, yaml line 660) |
| **Resolved value at this budget** | 1 MiB (1,048,576 B). Heap-independent. Cassandra logs no line for it. Evidence: at 500,000-byte values each thread kept ≈ 0.95 MiB (§2.2); in run 8, 7.6 MiB buffers were dropped at this default (`converge_Ldefault`) | 3 slabs × 32 MiB = 96 MiB. Heap-independent. Evidence: `HintsBuffer` histogram count = 3 at the end of every hints arm (`logs/*/summary.txt`, "histo final"), direct flat at 120-121 MiB; node config line shows `max_mutation_size=null`, `commitlog_segment_size=32MiB` |
| **Knob left unset (evidence)** | No `-Dcassandra.dob_max_recycle_bytes` on any N1 command line: the harness checks it (`CHECK PASS: N1 has no -D for either constraint` in each `session.log` on the node; `n1-jvm-args-excerpt.txt`) | No `-Dcassandra.MAX_HINT_BUFFERS` (same check). `max_mutation_size`, `commitlog_segment_size` untouched (`n1-cassandra.yaml.diff`) |
| Allocation path | `ByteBuffer.allocateDirect` (`DataOutputBuffer.java:87`; default `cassandra.dob.allocate_type` = direct) | `ByteBuffer.allocateDirect` (`HintsBuffer.java:77`) |

**Shared budget:** the JVM's direct-buffer limit, `-XX:MaxDirectMemorySize`. Both pools go through `Bits.reserveMemory`, as run 8 established. Reading: the JDK `BufferPool` MXBean `java.nio:type=BufferPool,name=direct`.

**The budget in every arm:** `-Xms/-Xmx3072M` and `-XX:MaxDirectMemorySize=192m` (design B) or `185m` (design A). Both are budget-class settings.

## 2. Verification solution

### 2.1 Defaults audit

Every yaml line differing from the shipped `conf/cassandra.yaml` (`logs/*/n1-cassandra.yaml.diff`, identical in every arm), and every non-default JVM flag:

| Change | Class |
|---|---|
| `cluster_name`, `num_tokens: 1`, `initial_token`, `auto_bootstrap: false` | environment |
| `listen_address`, `rpc_address`, `broadcast_rpc_address` (127.0.0.2), `seed_provider` | environment |
| `endpoint_snitch: GossipingPropertyFileSnitch` + `cassandra-rackdc.properties` (dc1; N2 in dc2) | environment (multi-DC topology) |
| `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` (local disk under `~/oom-default-run1/`) | environment |
| `JMX_PORT` in `cassandra-env.sh` (7199 N1, 7200 N2) | environment |
| `-XX:NativeMemoryTracking=summary` | environment (read-only instrument) |
| `MAX_HEAP_SIZE=3072M` (→ `-Xms3072M -Xmx3072M`) | budget |
| `-XX:MaxDirectMemorySize=192m` (B) / `185m` (A), via `JVM_EXTRA_OPTS`; `cassandra-env.sh` still adds its own `15872M` earlier on the line, and the last one wins (confirmed by the OOM firing at the set level) | budget |
| — | **no supporting deviation** |

Run 8's `max_hint_window: 24h` was dropped. The default (3h) covers every arm: each arm runs a fresh ring and lasts under 10 minutes.

### 2.2 Budget window (default arithmetic, playbook "Picking" step 4)

Both defaults are **absolute**, not heap fractions: 96 MiB for the hints pool, and 1 MiB × *T* for the DOB buffers. So a window can exist only at a small direct budget.

Measured terms (calibration at 4096 MiB, `logs/cal_*`):
- Idle direct *I* = 55 MiB in every arm. This includes the hints pool's first slab, created at startup (`HintsBuffer=1` at idle).
- Hints growth to the cap: *Hg* = +65-66 MiB, so the hints pool alone sits at 120-121 MiB.
- DOB growth *g* = about 0.95 MiB × *T*.

**Why 500,000-byte values.** `calculateNewSize` doubles a small buffer's capacity. The value write takes it to about *S*, and `writeEndOfPartition` doubles it again: *C* ≈ 2*S* ≈ 1,000,500 B, which is at most 1 MiB, so the buffer is kept. A 4 MB value (run 8) gives *C* ≈ 7.6 MiB, which is dropped at the default.

**Conditions** (each alone ≥ 30% free, the sum over the budget *X*):

- hints alone: *I* + *Hg* ≤ 0.7*X*, so *X* ≥ 173 MiB;
- DOB alone: *I* + *g* ≤ 0.7*X*;
- together: *I* + *Hg* + *g* > *X*.

These hold together only when **51 < *g* < 94 MiB**, which needs about 55-100 threads keeping a buffer. The window is at most about 18 MiB wide, and the predicted overshoot is at most about 5-6%.

The window exists only because *I* is small. With the 30% rule, the larger pool (121 MiB) caps the window from below, and the smaller pool's growth must be within a factor of about 1.5 of the hints pool's. That is narrow.

**Calibrated *T*:**

| DOB client threads (500,000 B values, 6,000 rows) | Concurrent 1 KiB writers | DOB held (MiB) | *g* |
|---|---|---|---|
| 32 | none | 109-110 | 55 |
| 48 | none | 127 | 72 |
| 128 | none | 194 | 139 (*T* ≈ 146) |
| 48 | 64 threads, local (design A's matched control) | 183-184 | ≈ 128 |
| 48 | 8 threads, local (`cal_Dmatched_t8`) | 132 | 77 |

**Concurrency matters, and it is the lesson of design A.** *T* counts shared-pool (`SEPWorker`) threads that ever run a large mutation. Other traffic adds workers, and over a 6,000-row burst more of them pick up a DOB write. So a DOB-only control under-states the DOB pool in the convergence arm. The valid control runs the DOB burst with the same extra concurrency as the convergence arm, but with no hints. Design B keeps that concurrency small (8 hints threads; `cal_hints_t8` showed 8 threads still fill the 3-slab pool within 10 s).

**Design B sizing (prediction, before the 192 MiB arms):**

| Arm | Predicted direct (MiB) | % of 192 |
|---|---|---|
| `B_H_alone` (hints, 8 threads) | 55 + 66 = 121 | 63% |
| `B_D_matched` (DOB 48 threads + local 1 KiB writes on 8 threads, no hints) | 55 + 77 = 132 | 69% |
| `B_converge` (hints 8 threads + DOB 48 threads) | 55 + 66 + 77 = 198 | **103%** |

**Budget realism.**
- **Heap.** 3072 MiB is above the documented 2 GB minimum.
- **Direct limit.** 192 MiB is far below the automatic value: on this host `cassandra-env.sh` computes 15,872 MiB. For the automatic rule (RAM/4) to give 192 MiB, the node would need 768 MiB of RAM, with an automatic heap of 384 MiB, well under the documented minimum. So this budget is reachable only when an operator sets `MAX_DIRECT_MEMORY_SIZE` small explicitly (for example, budgeting a container), with a normal heap.
- **This weakens the Target-3 note (§4).**

### 2.3 Workloads, instruments, procedure

**Topology.** As in run 8: a 2-node loopback ring. N1 is 127.0.0.2 in dc1, the node under test. N2 is 127.0.0.3 in dc2; it is up only for ring and schema creation, then `kill -9`'d before any reading.

**Keyspaces:**
- `dobks {dc1:1}` (never hinted);
- `hintks {dc1:1, dc2:1}` (every write hints for N2).

**Workloads.** All are `cassandra-stress user` profiles with no schema statements (run 8's fix), protocol v4, CL ONE:
- *hints* (`hints.yaml`): 1 KiB values into `hintks`;
- *dob* (`dob.yaml`): 6,000 × 500,000-byte values into `dobks`, 48 threads;
- *local* (`local.yaml`): the hints workload's 1 KiB writes, but into `dobks`, so no hints. Population is offset to keys 10,000,001+.

**Instruments** (every ~8 s):
- direct `MemoryUsed`/`Count`, NMT `Other`, `RssAnon`, heap;
- `jstack` every third sample (writers parked in `HintsBufferPool.switchCurrentBuffer` → `take()`);
- a `HintsBuffer` histogram at idle and end;
- after each arm: `system.log`/stdout for `OutOfMemoryError`, `gc.log`, heap-dump listing, `dmesg`.

**Procedure** (on the node, in `~/oom-default-run1`):

```
# calibration (4096 MiB)
./oom-run.sh arm cal_dob 4096 dob                        # DOB_THREADS=128
DOB_THREADS=32 ./oom-run.sh arm cal_dob_t32 4096 dob
DOB_THREADS=48 ./oom-run.sh arm cal_dob_t48 4096 dob
./oom-run.sh arm cal_hints 4096 hints                     # 64 threads, 1.5M rows
N_HINTS=3000000 HINT_THREADS=8 HINT_SECS=120 ./oom-run.sh arm cal_hints_t8 4096 hints
N_HINTS=3000000 HINT_THREADS=8 HINT_SECS=120 HINT_LEAD=20 DOB_THREADS=48 HINT_PROFILE=local.yaml HINT_POP=10000001 \
  ./oom-run.sh arm cal_Dmatched_t8 4096 hints,dob overlap
# design A (185 MiB; hints 64 threads, 6M rows, 240 s cap; DOB 48 threads; DOB starts 20 s after hints)
export N_HINTS=6000000 HINT_SECS=240 DOB_THREADS=48 HINT_LEAD=20
./oom-run.sh arm H_alone 185 hints
./oom-run.sh arm D_alone 185 dob
./oom-run.sh arm converge 185 hints,dob overlap
./oom-run.sh arm converge_rep2 185 hints,dob overlap
HINT_PROFILE=local.yaml HINT_POP=10000001 ./oom-run.sh arm converge_nohints 185 hints,dob overlap
# design B (192 MiB; hints 8 threads, 3M rows, 150 s cap)
export N_HINTS=3000000 HINT_THREADS=8 HINT_SECS=150 HINT_LEAD=20 DOB_THREADS=48
./oom-run.sh arm B_H_alone 192 hints
HINT_PROFILE=local.yaml HINT_POP=10000001 ./oom-run.sh arm B_D_matched 192 hints,dob overlap
./oom-run.sh arm B_converge 192 hints,dob overlap
```

## 3. Runtime results

### 3.1 Design A (185 MiB), superseded by B for attribution

| Arm | Peak direct (MiB) | % of 185 | Outcome |
|---|---|---|---|
| `H_alone` (hints 64 thr) | 122 | 65.9% | alive, 0 ERROR; 3 `HintsBuffer`s; a writer parked in `take()` with 32 blocked on the pool monitor in 4 of 10 dumps; 6,000,000 writes |
| `D_alone` (DOB 48 thr) | 123 | 66.5% | alive, 0 ERROR; held 122; 6,000 writes |
| `converge` | 121 just before the burst | → 100% | DOB burst 13:23:27; first `OutOfMemoryError: Direct buffer memory` 13:23:36.5, in `DataOutputBuffer.expandToFit` (MutationStage and Native-Transport-Requests threads); forced heap OOM 13:23:37.5 (heap 499 of 3072 MiB after full GC); `ReportJavaOutOfMemory` 13:23:40.9; JVM killed |
| `converge_rep2` | 184 in a sample taken after the throw | → 100% | DOB burst 13:29:25; first direct OOM 13:29:34.4, same path; JVM killed |
| `converge_nohints` (attribution: hints → local) | **184** | **99.5%** | survived the burst with the hints pool at 1 slab. Died ~2 min later (13:36:29 local): direct OOM in `CompactionExecutor`, `ThreadLocalReadAheadBuffer.allocateBuffer` (compaction read-ahead, default `compressed_read_ahead_buffer_size` 256 KiB) |

Design A's controls were safe, and its convergence arm OOMed twice. But the attribution control shows that A's two alone arms do not bound the convergence arm. In A, 64 concurrent hints writers made the DOB pool grow to about +128 MiB, not the +72 MiB measured in `D_alone`. With no hints at all, direct still reached 99.5%, and a third direct consumer (compaction read-ahead buffers) ended it. So A's OOM cannot be credited to the hints pool. Design B fixes the control.

Excerpts: `logs/{H_alone,D_alone,converge,converge_rep2,converge_nohints}/` (`summary.txt`, `n1-system-oom-lines.txt`, `n1-system-oom-excerpt.txt`).

### 3.2 Design B (192 MiB), the filed result

| Arm | Idle | Peak direct (MiB) | % of 192 | Pool at its cap? | Outcome |
|---|---|---|---|---|---|
| `B_H_alone` | 55 | 121 | 63.0% | yes: 3 `HintsBuffer`s at the end, direct flat at 120-121 for 2 min of load | alive, 0 ERROR; 3,000,000 writes |
| `B_D_matched` | 55 | 133 | 69.3% | yes: DOB +75-78 MiB, held at 130-131 through the hold; `HintsBuffer` stayed 1 | alive, 0 ERROR; 6,000 DOB writes |
| `B_converge` | 55 | 120 sampled at the burst start, then **192 at the OOM** (the `Bits` limit) | **100% → OOM** | hints pool at 3 slabs (120 MiB) when the burst started | **`OutOfMemoryError: Direct buffer memory`, JVM killed** |

**`B_converge` timeline** (local EST; `system.log` is UTC; `logs/B_converge/`):
- 14:01:02: hints workload starts.
- 14:01:18: direct reaches 120 MiB (the 3-slab level). It holds there.
- 14:01:35: DOB workload starts; hints still running.
- 14:01:42.315: first `java.lang.OutOfMemoryError: Direct buffer memory`. The stack is `Bits.reserveMemory:175` ← `DataOutputBuffer$1$1.allocate:87` ← `expandToFit:178` ← `UnfilteredSerializer.writeEndOfPartition:415` ← `Mutation$MutationSerializer.serializeInternal:483`, on `Native-Transport-Requests-82`. This is a DOB scratch buffer doubling to keep a 1 MiB buffer (`n1-system-oom-excerpt.txt`).
- 14:01:42.318: `JVMStabilityInspector` "Force heap space OutOfMemoryError in the presence of" the direct OOM. Heap after the forced full GCs: 638 → 635 of 3072 MiB (`n1-gc-tail.txt`), so heap is not the cause.
- 14:01:44.9: `ReportJavaOutOfMemory`; heap dump written (784 MB, `hprof.txt`); `-XX:OnOutOfMemoryError=kill -9 %p`.
- 14:01:47: the next sample finds N1 gone.
- No kernel OOM-kill (`dmesg` shows only kills from Nov 3 runs).

**Prediction vs observation.** Predicted demand was 198 MiB against 192, an overshoot of 6 MiB (3%). The limit was hit 7 s into the burst. That is sooner than `B_D_matched`'s curve would supply the missing 72 MiB (its first sample, 8 s in, already showed +73 MiB). Writes in flight help: each grows a buffer through about 500 KB before the doubling. The ~8 s sampling cannot separate kept bytes from in-flight bytes, as in run 8. The matched control is what bounds attribution: the same concurrency without the hints pool's 64 MiB stayed at 69.3%, alive.

**Client totals after the kill are not writes** (run 8's note): the DOB client's "6,000 partitions, 0 errors" includes `NoHostAvailable` failures counted as done.

## 4. Conclusion

**A node with Cassandra's default values for these constraints OOMs under this workload at this budget, with no supporting deviation.** The two settings are `dob_max_recycle_bytes` = 1 MiB and `MAX_HINT_BUFFERS` = 3 (96 MiB of 32 MiB slabs).

The workload:
- a replica down, so ordinary 1 KiB writes are hinted (8 client threads);
- 500 KB values written by 48 client threads.

The budget is a 192 MiB `MaxDirectMemorySize` with a 3 GiB heap.

Each pool stays at its own default cap: the hints pool at 3 slabs, and every DOB buffer at or under 1 MiB. Each alone leaves at least 30% of the budget free, under the same total request concurrency. Together they exhaust the direct limit. Cassandra then turns the direct OOM into a JVM kill. Repeats: the A design OOMed 2 of 2; B ran once.

**How it differs from convergence run 8.** Run 8 needed L raised 8× and n raised to 8, at a 560 MiB budget. At the defaults, the same mechanism converges only below about 200 MiB of direct memory. The window is narrow, and it needs:
- values sized so the doubled buffer stays at or under 1 MiB (about 0.4-0.52 MB);
- enough concurrency for about 55-100 shared-pool workers to keep a buffer, but not more. With more, the DOB pool alone breaks the 30% margin; at 128 client threads it alone held 194 MiB.

**What design A adds.** The DOB pool's size at its default is set by total request concurrency, not by the large-value client. That makes it a **concurrency-scaled** default: about 1 MiB per shared-pool worker, up to the SEP worker count (`concurrent_writes` 32 + `native_transport_max_threads` 128 + other stages). For an operator, the DOB pool at default can reach about 150+ MiB on a busy node. Separately, compaction's `ThreadLocalReadAheadBuffer` (256 KiB × compaction threads, direct) is a third default direct consumer. It is not in `_constraint-groups.md` and was not studied here.

**Target-3 note.** Weak.
- The constraints are untouched, and both workloads are ordinary: any write traffic while a replica is down, plus a table with values of a few hundred KB.
- But the budget is far below what `cassandra-env.sh` picks (15,872 MiB here). For the automatic rule to give 192 MiB, the node would need 768 MiB of RAM, under the documented 2 GB heap minimum.
- So the gap at defaults needs an operator who sets `MAX_DIRECT_MEMORY_SIZE` small explicitly, for example for a container.
- With the automatic limit (RAM/4 or 15.5 GiB), these two default pools (≤ 96 MiB + ~1 MiB × workers) cannot exhaust it.
- **Smallest non-default change for a realistic budget:** raise either knob, as in convergence run 8 (L = 8 MiB with n = 8 at 560 MiB).

**Not tested:**
- the minimum boundary;
- whether the automatic `MaxDirectMemorySize` on a 2-4 GB node (512 MiB-1 GiB direct) can be reached at defaults with many more workers. That would take *T* ≈ 400-900, more than the SEP worker ceiling of about 200.

## Instrument check and process hygiene

- Every N1 command line was checked for `-Xmx3072M` and the arm's `MaxDirectMemorySize`, and for the absence of both `-D` properties. All arms show `CHECK PASS` lines in `session.log` on the node, and `n1-jvm-args-excerpt.txt` in each `logs/<arm>/`.
- Every arm's yaml diff is environment-only (§2.1).
- After every arm, `pgrep` for `CassandraDaemon` and `cassandra-stress` was empty (`CHECK PASS: no daemon left` / `no stress left`).
- Node data, commit log, hints and logs stayed under `~/oom-default-run1/` on local disk. Nothing was written to `/proj` except this folder. The repository's `systems/cassandra/source/` was untouched.
- Harness defect: `hprof.txt` in design A's converge arms was collected from the wrong folder, and the dumps were later deleted by the next arm's start. The OOMs are evidenced by `system.log` (`n1-system-oom-lines.txt`). Fixed for design B (`hprof.txt` lists the dump).
