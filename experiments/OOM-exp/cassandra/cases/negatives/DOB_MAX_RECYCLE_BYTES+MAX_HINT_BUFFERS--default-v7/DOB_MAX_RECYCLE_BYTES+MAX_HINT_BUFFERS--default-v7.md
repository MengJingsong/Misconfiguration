# DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS at defaults, at an acceptable direct budget (R6-V)

**Direction:** convergence · standing-pool (hints slabs) × multiplicity (kept DOB scratch buffers).
**Regime:** default capacities (`dob_max_recycle_bytes` 1 MiB, `MAX_HINT_BUFFERS` 3), no supporting
deviation; budget `-Xmx2048M`, `-XX:MaxDirectMemorySize=512m` (standing-rule floor; V7 met without review).
**Run:** 2026-11-12, `apt179` (16 threads, 15,931 MiB, OpenJDK 11.0.33), cassandra-5.0.9 `28adf4907aed`
unmodified (copy of `~/cassandra-c1` at `/mydata/r6v/cassandra`). Campaign row R6 (V7 variant).
**Design:** [`design/R6V-design.md`](design/R6V-design.md) (dated before readings; amendments 1–3 dated).
**Harness:** [`harness/`](harness/). **Excerpts:** [`logs/`](logs/). **Raw logs, dumps:** `apt179:/mydata/r6v/logs/<arm>/`.

> **Filed 2026-11-12 in `negatives/`** as `negative` (default capacities; budget 512 MiB direct / 2 GiB heap, standing-rule floor).

| Condition | Status |
|---|---|
| S: both defaults, 523,000-byte values, up to 512 DOB + 256 fill + 64 read + 16 hint client threads, 2 GiB heap, **512 MiB direct** | **`negative`** (V1–V3 met; 0/3 converge, 0/6 controls) |
| S at 240–250 MiB direct (below the floor) | diagnostic boundary only: direct OOM 4/4 (250: 3/3, 240: 1/1); 270: 0/1. Not a status (V7 unmet, controls not rerun at 250) |
| L: 15 MB values (DOB in-flight growth, hints not needed) | separate lead, not this case: direct OOM at 512 MiB without hints |

## Summary

- **Conclusion:** with both settings at their defaults, the hints pool (3 × 32 MiB slabs) plus the
  DOB scratch buffers kept by every worker thread (≤ 1 MiB each) peak at **256–264 MiB** of direct
  memory under the heaviest write mix reachable here, 50–52% of a 512 MiB limit. The converge arm
  survived 3/3 at 512 MiB, as did hints-alone (121 MiB) and DOB-alone (194–203 MiB) ×3 each. Within the
  tested range this is a **negative**. The pair still OOMs below the floor: 250 MiB 3/3 and 240 MiB 1/1,
  with the same stack as default run 1 (`DataOutputBuffer.expandToFit`). 270 MiB survived 1/1. So the
  largest failing budget lies between 250 and 270 MiB, far below the 512 MiB floor.
- **Root cause / why it cannot reach 512 MiB:** at defaults both pools are absolute and small. The hints
  pool is capped at 96 MiB whatever the number of down replicas, and the DOB pool is ≤ 1 MiB × the
  number of threads that serialized a large item. Those threads are shared-pool workers, bounded by the
  pools' permits. Measured T = 171–177 threads (128 Native-Transport-Requests, about 33 MutationStage, a
  few read/flush/compaction) holding 131–139 MiB. The arithmetic ceiling with every shared-pool permit
  (276) holding a full 1 MiB buffer is ≈ 400 MiB (§2.3), still under 512 MiB.
- **Side finding (lead, not this mechanism):** with 15 MB values, a *single* consumer (DOB buffers
  **in flight**, which the recycle cap does not bound) hit a direct OOM at 512 MiB without any hints
  (4 of 5 runs at 512; the 5th was a heap OOM). At 1024 and 2048 MiB the 2 GiB heap ran out first.
  This is unprotected in-flight growth (concurrent writes × ≈ 2 × mutation size), recorded in §3.4 for
  a separate case.

## 1. Constraints, defaults and protection map

| | `DOB_MAX_RECYCLE_BYTES` | `MAX_HINT_BUFFERS` |
|---|---|---|
| Default rule | `CassandraRelevantProperties.java:204` = 1,048,576; kept if `capacity <= MAX_RECYCLE_BUFFER_SIZE` (`DataOutputBuffer.java:53,73`) | `CassandraRelevantProperties.java:351` = 3; slab = max(2 × `max_mutation_size`, 32 MiB) (`HintsService.java:110`); `max_mutation_size` unset → 16 MiB |
| Resolved (heap-independent) | 1 MiB per thread; observed kept buffers 1,046,098 B (523,000-byte values, doubled) | 3 × 32 MiB = 96 MiB; `HintsBuffer` = 3 at the end of every hinted arm |
| Left unset (evidence) | harness `CHECK PASS: N1 has no -D for either constraint` in every `session.log`; `logs/*/n1-jvm-args-excerpt.txt` | same; yaml diff is environment-only ([`logs/n1-cassandra.yaml.diff`](logs/n1-cassandra.yaml.diff)) |

Protection map (fixed in the design §4 before readings):

| Domain | Contract C | Multiplicity | Aggregate coverage | Measured U (dump at end of `S_conv_r1`, alive) |
|---|---|---|---|---|
| Hints pool | ≤ 3 slabs, 96 MiB (hard; writers wait in `reserveBuffers.take()`) | one per node, all destinations | JVM direct limit only | 3 slabs = 96.0 MiB |
| DOB kept scratch | ≤ 1 MiB per thread (retention only) | T = threads that serialized a ≤ ~0.52 MB item | none | 173 buffers = 137.2 MiB |
| DOB in-flight growth | none | threads concurrently serializing | none | (transient; see §3.4) |
| Other default direct | BufferPool chunks, Netty epoll arrays, compaction read-ahead, hints write buffer | — | — | 16.0 + 3.0 + 1.0 + 0.5 + 0.25 ≈ 21 MiB |

Total Bits-charged owners at that dump: 327 = 254.5 MiB (sampled MXBean 256 MiB). U = JDK
`BufferPool direct` `MemoryUsed` every ~8 s plus `hprof_direct.py` holder grouping (R2 tool). K
(`allocatedBuffers`) was not read; slab counts come from the heap.

**Labels:** capacities **default**; budget **explicit deployment budget at the standing-rule floor**
(512 MiB direct, 2048 MiB heap). On apt179 `cassandra-env.sh` would resolve heap 7,965 MiB (½ RAM) and
`MaxDirectMemorySize` 3,982 MiB (¼ RAM). The chosen values are below the automatic ones; the standing rule
accepts ≥ 512 MiB. A larger direct budget only adds headroom, because nothing else changes with it.
Heap-derived defaults at 2 GiB: `file_cache_size` 512 MiB, `networking_cache_size` 128 MiB, native
in-flight request bytes 204.8 MiB (global) / 51.2 MiB (per client IP).

## 2. Verification design

### 2.1 Defaults audit

| Change | Class |
|---|---|
| `cluster_name`, `num_tokens: 1`, `initial_token`, `auto_bootstrap: false`, addresses (127.0.0.2/3), `seed_provider`, `GossipingPropertyFileSnitch` + rackdc (dc1/dc2), data/commitlog/hints/caches/cdc directories under `/mydata/r6v/N1` | environment |
| `JMX_PORT` 7199/7200; `-XX:NativeMemoryTracking=summary`; `CASSANDRA_HEAPDUMP_DIR` = arm folder | environment (instrument) |
| `MAX_HEAP_SIZE=2048M`; `-XX:MaxDirectMemorySize=<budget>m` via `JVM_EXTRA_OPTS` (last occurrence on the command line, checked by the harness; `cassandra-env.sh` adds 3982M earlier) | budget |
| — | **no supporting deviation** |

### 2.2 Workloads and arms

2-node loopback ring as in default run 1. N1 (127.0.0.2, dc1) is the node under test. N2 (dc2) is
`kill -9`'d after schema creation. `dobks {dc1:1}`, `hintks {dc1:1, dc2:1}`. cassandra-stress user
profiles, CL ONE, protocol v4. Condition S workload (fixed after calibration, amendment 1):
*hints* 16 threads of 1 KiB into `hintks` (starts first; 30 s lead fills the pool to 3 slabs). Then
together: *dob* 512 threads of 523,000-byte values (12,000 rows, 120 s cap), *fill* 256 threads of 1 KiB
into `dobks` and *reads* 64 threads of the DOB rows, both added to drive more shared-pool workers.

| Arm | Change from `S_conv` | Role |
|---|---|---|
| `S_conv_r1..3` | — (512 MiB) | converge |
| `S_H_alone_r1..3` | DOB values 1,024 B (same threads and timing) | matched control: hints at the same total concurrency, no large buffer |
| `S_D_alone_r1..3` | hints workload → `local.yaml` (same 1 KiB writes into `dobks`, no hints) | matched control: DOB at the same concurrency, no down-replica hints. Also the "no down replica" intervention |
| `S_diag_270/250/240` | budget only | diagnostic boundary search below the floor |

Predictions (design amendment 1): converge ≈ 255–265 MiB, alive 3/3; H alone ≈ 120; D alone ≈ 195–200;
largest failing budget ≈ 240–255 MiB.

Commands: `harness/run-seq.sh list-*.txt` on the node. Lists are in [`logs/list-*.txt`](logs/), and each
line is `<arm> <budget> VAR=value…` for `harness/oom-run.sh arm <arm> <budget>`. Progress is in
[`logs/run-seq.log`](logs/run-seq.log).

**Limits:** ≤ 6 h wall (07:22–13:15 MST; used 07:22–09:13), ≤ 25 arms (used 23), arm caps 150/120 s.

### 2.3 Demand arithmetic at defaults

- Shared-pool (SEP) permits that can hold a DOB buffer: Native-Transport-Requests 128, ReadStage 32,
  MutationStage 32, CounterMutationStage 32, ViewMutationStage 32, RequestResponseStage 16 (cores), auth 4:
  Σ = 276 (`Stage.java:45-50`, `Dispatcher.java:58,77`). Parked SEP workers are reused, not terminated, so
  the number of physical workers ≈ peak concurrent tasks + spinners.
- Non-SEP holders: 2 flush writers, ≤ 2 compactors, 1 hints writer.
- **Ceiling:** 96 (hints) + 281 × 1 MiB (DOB) + ~21 (other) ≈ **398 MiB = 78% of 512 MiB**. Reaching it
  would need every stage, including counter and view, busy at once, with each worker serializing a
  ≤ 0.52 MB item.
- **Reached:** 96 + 131–139 (T = 171–177) + ~21 ≈ 250–258 MiB at the dumps. The sampled peak was 256–264.
- Down destinations do not help: one pool, plus a single 256 KiB hints write buffer.
- Convergence with matched safe-alone controls is limited by the hints increment (+64 MiB over idle):
  each alone ≤ (1 − m)·X with the sum > X needs X < 64/m. That is ≈ 215 MiB at the 30% margin and ≈ 640 MiB
  even at 10%, where the DOB window at 512 MiB would be only 14 MiB wide.

## 3. Results

### 3.1 Calibration (4096 MiB, alive)

| Arm | Peak | Hints slabs | DOB buffers (dump) | Note |
|---|---|---|---|---|
| `S_cal` (hints 64 + fill 256 from t0; DOB 512) | 225 | 2 | 171 = 138.7 MiB | fill starved the hints client: only 2 slabs |
| `S_cal2` (final workload) | 258 | 3 | 177 = 139.2 MiB (128 NTR, 33 MutationStage, 6 ReadStage names) | reads added ~6 holders |

### 3.2 Main arms at 512 MiB direct, 2048 MiB heap

| Arm | Idle | Before DOB | Peak (sampled) | % of 512 | End state | Outcome | Large DOB writes completed |
|---|---|---|---|---|---|---|---|
| `S_conv_r1` | 51 | 115 | 256 | 50.0% | 3 `HintsBuffer`; dump 254.5 MiB (DOB 173 = 137.2, slabs 96) | alive, 0 ERROR | 5,944 |
| `S_conv_r2` | 51 | 115–117 | 264 | 51.6% | 3 `HintsBuffer` | alive, 0 ERROR | 5,911 |
| `S_conv_r3` | 51 | 115 | 261 | 51.0% | 3 `HintsBuffer` | alive, 0 ERROR | 5,152 |
| `S_H_alone_r1..3` | 51 | 115 | 121 / 121 / 121 | 23.6% | 3 `HintsBuffer` | alive ×3, 0 ERROR | (1 KiB values) 12,000 |
| `S_D_alone_r1..3` | 51 | 51–53 | 203 / 196 / 194 | 37.9–39.6% | 1 `HintsBuffer`, hintks 0 writes | alive ×3, 0 ERROR | 5,385 / 5,109 / 5,195 |

The DOB increment is the same with or without hints (+146–149 MiB in converge, +143–152 MiB alone), and
the converge peak ≈ H alone + D alone − idle. The pools add up without interacting. The workload is
the same across arms: completed DOB writes 5,109–5,944 in 120 s in every DOB arm (all clients
time-capped, write timeouts retried). `MemAvailable` ≥ 5.1 GiB and N1 `VmSwap` 0 throughout
(`summary.txt` sample lines).

### 3.3 Diagnostic boundary (below the floor; V7 unmet)

| Arm | Budget | Outcome | First error | Holders at the OOM (dump) |
|---|---|---|---|---|
| `S_diag_270` | 270 | alive, 0 ERROR; peak 258 (95.6%) | — | — |
| `S_diag_250` | 250 | direct OOM, JVM killed | `PerDiskMemtableFlushWriter_0:3`: `Bits.reserveMemory` ← `DataOutputBuffer$1$1.allocate:87` ← `expandToFit:178` ← `UnfilteredSerializer.serializeRowBody` (flush) | 333 owners = 249.6 MiB: DOB 174 = 131.2, slabs 3 = 96.0, BufferPool 16, other ≈ 6 |
| `S_diag_250_r2` | 250 | direct OOM, killed | `Native-Transport-Requests-130`: … `expandToFit:178` ← `UnfilteredSerializer.writeEndOfPartition:415` (mutation serialization) | dump kept, not analysed |
| `S_diag_250_r3` | 250 | direct OOM, killed | `Native-Transport-Requests-64`: same path | dump kept, not analysed |
| `S_diag_240` | 240 | direct OOM, killed | `MutationStage-156`: same path | dump kept, not analysed |

Each OOM came ≈ 8–15 s into the DOB burst, after the hints pool had reached 3 slabs (115–117 MiB
sampled). `JVMStabilityInspector` forced a heap OOM and `-XX:OnOutOfMemoryError=kill -9` ended the JVM
(`logs/S_diag_*/n1-system-oom-excerpt.txt`, `n1-gc-tail.txt`). This reproduces default run 1's
mechanism and stack at a slightly higher budget (run 1: 192 MiB on pc41). **Largest failing budget:
250 MiB (3/3); 270 MiB survives (1/1); boundary ≈ 255–265 MiB** (the 512 MiB arms' peaks).

### 3.4 Side probe, condition L (15 MB values; a different holder: DOB in-flight growth)

| Arm | Budget | DOB client threads | Hints | Outcome |
|---|---|---|---|---|
| `L_D_alone` | 512 | 32 | none (local 8 thr) | **direct OOM** (`MutationStage-25`, `CommitLog.add:308` → `expandToFit`); dump: 180 owners = 453.6 MiB, DOB **56 buffers = 400.6 MiB** on MutationStage threads (15,000,050 B and 30,000,100 B), 1 slab |
| `L_D_alone_r2` | 512 | 32 | none | heap OOM (`ReportJavaOutOfMemory`, heap 1.92 of 2 GiB; no direct error logged) |
| `L_D_alone_r3` | 512 | 32 | none | direct OOM (`MutationStage-9`, same path) |
| `L_conv` | 512 | 32 | hints 8 | direct OOM (`MutationStage-12`, same path) |
| `L_D_8thr_512` | 512 | **8** | none | direct OOM (`MutationStage-18`); dump 482.2 MiB, DOB 54 buffers = 429 MiB (16 large) |
| `L_D_1024` | 1024 | 32 | none | heap OOM (Java heap space) |
| `L_D_2048` | 2048 | 32 | none | heap OOM (Java heap space) |

The recycle cap works here: buffers > 1 MiB are not kept after `close()`. But at the OOM 16–20
MutationStage threads were each holding a 15–30 MiB buffer inside `CommitLog.add`. Even 8 client
threads produced this, because timed-out writes keep running on MutationStage and the client retries
them (as in R2). Hints are not needed. This is **not** convergence of the two named pools. It is
unprotected in-flight DOB growth, bounded only by `concurrent_writes` (32) × ≈ 2 × the mutation size
(≤ 16 MiB): ≈ 1 GiB. At a 2 GiB heap the heap ends first above 512 MiB direct. One run each; no
matched control or intervention beyond the 8-thread arm. It is a lead for a new case (the in-flight
DOB growth of large mutations, at defaults, possibly with a larger heap). Why the buffers outlive
serialization (waiting for a commit-log segment or memtable space) was not attributed; one mid-run
`jstack` showed MutationStage threads waiting in `MemtableAllocator$SubAllocator.allocate`.

## 4. Conclusion

**Negative within the tested range.** With `dob_max_recycle_bytes` and `MAX_HINT_BUFFERS` at their
defaults, a 2 GiB heap and a 512 MiB direct limit, the default run 1 mechanism did not fail:
- hints to a down replica fill the 3-slab pool;
- about 175 shared-pool workers keep a ≤ 1 MiB DOB buffer each.

Under the heaviest reachable write/read mix tried, the converge arm survived 0/3 OOM at 50–52%, and the
controls survived 0/6. The two default pools are absolute and small (96 MiB + ~1 MiB per worker). Worker
multiplicity is bounded by the shared-pool permits, so their sum cannot reach 512 MiB at defaults:
- measured ≈ 260 MiB;
- arithmetic ceiling ≈ 400 MiB.

The mechanism is real below the floor: direct OOM at 250 MiB (3/3) and 240 MiB (1/1), the same
`expandToFit` path as run 1, with a holder split of 131 MiB DOB + 96 MiB slabs at the OOM. So the
largest failing budget is ≈ 250–265 MiB, about half the acceptable minimum. A larger direct budget
cannot bring it back. A larger heap only raises heap-derived pools that are not part of this mechanism.

**Scope and limits.** One node type (16 threads; RequestResponseStage permits scale with cores, so ±16
MiB on other hosts). Write-heavy mixes from one client host (per-IP in-flight bound 51 MiB); protocol
v4. Counter and view stages were not exercised (≤ 64 more holders, within the arithmetic ceiling). One
down replica: the hints pool is per node, so more down destinations add at most 256 KiB. Values ≤ 0.52 MB
for retention. Larger values change the holder to in-flight growth (§3.4), which is a separate,
DOB-alone lead.

**Effect on R6 (`candidate (pre-protocol)` default run 1).** At ≥ 512 MiB the case is a negative. Its OOM
reproduces only at a tightened budget (≤ 250 MiB): 4/4 OOMs there, the same stack, holder breakdown at
the OOM. Matched controls and an intervention were not rerun at 250 MiB, so the diagnostic condition is
not formally `reproduced-OOM` from this run. Running `S_H_alone`/`S_D_alone` ×3 at 250 MiB (≈ 30 min)
would close V2 for it.

### V1–V7 (condition S, 512 MiB direct, 2048 MiB heap)

| | Requirement | Evidence | Met? |
|---|---|---|---|
| V1 Repetition | ≥ 3 clean starts | `S_conv_r1..3`: 0/3 OOM, peaks 256/264/261 MiB | yes (for a negative: no failure 3/3) |
| V2 Matched control | ≥ 3, same budget/build | `S_H_alone` ×3 (121 MiB), `S_D_alone` ×3 (194–203 MiB), same concurrency, alive | yes |
| V3 Measurement | U independent of K | MXBean direct pool every ~8 s; heap-dump holder breakdown (`S_cal`, `S_cal2`, `S_conv_r1`, `S_diag_250`); `HintsBuffer` histogram | yes |
| V4 Intervention | — | no endpoint at 512 MiB; the no-hints arm (`S_D_alone` ×3) shows the hints share (≈ 64 MiB) | n/a (negative) |
| V5 Initiating failure | — | none at 512 MiB; diagnostic 250 MiB first error + dump kept (§3.3) | n/a |
| V6 Default constraints | both at defaults, resolved | no `-D`, yaml environment-only, 3 slabs × 32 MiB, kept buffers 1,046,098 B | yes |
| V7 Acceptable budget | ≥ 512 MiB (standing rule) | 512 MiB direct, 2048 MiB heap; auto values 3,982 / 7,965 MiB recorded | yes (no review needed) |

**Proposed:** status `negative`; label capacity **default**, budget **explicit, standing-rule floor**;
folder `cassandra/cases/negatives/` (file name `DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default-v7.md`, or
merged with default run 1's file at the researcher's choice). The L probe is proposed as a new
`candidate` lead (DOB in-flight growth of large mutations, default constraints).

## Instrument check and process hygiene

- Every N1 command line was checked for `-Xmx2048M`, for the arm's `MaxDirectMemorySize` as the last
  occurrence, and for the absence of both `-D` properties (`CHECK PASS` lines in each `session.log`).
- After every arm, `pgrep` found no `CassandraDaemon` and no `cassandra-stress`
  (`logs/run-seq.log`: "daemons left: 0; stress left: 0" on all 23 arms). Final check after the last
  arm: none running.
- Data stayed on `/mydata/r6v` (≈ 17 GiB, mostly heap dumps). The data/commitlog/hints directories were
  deleted after each arm. `/mydata/oom-recheck/R4` and `/mydata/jingsong-cass-s4` were untouched.
  Nothing large was written to `/proj` (excerpts 126 KiB). The repo's `systems/cassandra/source/` was untouched.
- Sampling: `jcmd`/`sjk` every ~8 s; `jstack` every 4th sample. Heap-dump analyses ran niced; two ran
  while an arm was active and are disclosed: the `S_conv_r1` dump during `S_conv_r2` (its peak, 264 MiB,
  is the highest of the three, so the extra load did not lower demand) and the `S_diag_250` dump during
  `L_conv` (an OOM arm of the side probe).
- Known harness artefacts: `run-seq.log` repeats the "run-seq DONE" line with the first parameter for
  `list-cal` (fixed before the next list). `stress-*.txt` lack summary lines because clients are stopped
  by time caps; counts come from the last `total,` line and `tablestats`.
