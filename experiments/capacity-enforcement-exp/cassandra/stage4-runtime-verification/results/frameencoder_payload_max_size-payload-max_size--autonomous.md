# frameencoder_payload_max_size-payload-max_size--autonomous — stage-4 results  <!-- file: results/frameencoder_payload_max_size-payload-max_size--autonomous.md -->

> **Case:** [`frameencoder_payload_max_size-payload-max_size--autonomous`](../../stage3-ai-deep-read/cases/frameencoder_payload_max_size-payload-max_size--autonomous.md) (extension set, order 124, band B)
>
> **Status:** verdict filed (run 1 + self-check; no run 2)
>
> **Outcome class:** true negative (estimate `negative`; both tiers Confirmed, effect `does not cap`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the
> feedback section is section D.

Written outside the repository (`~/writeup-ext/out/o124/`) by a stage-4 agent working as Jingsong on 2026-11-25; the amended
case file is `~/writeup-ext/out/o124/case-amended.md`, the harness `~/writeup-ext/out/o124/harness/`, and the raw evidence
`~/writeup-ext/out/o124/raw/`. Nothing was committed.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed at repo commit `bef6bc8a6` (sha256 `439164f94df6ba35f0a2baf25de3143064eedabc7bf1613f0f4248942976f9e6`, matching `_INDEX.md` §4). The amended version, with audit amendments A1–A3, defect fixes D1–D2 and section D filled, is `case-amended.md`, sha256 `954ff8d928d1334537ffcc8ba02e0e9976be753cf72340d30ea9a9c7f6c51bd0`. B2f/B2g/B3f/B3g were not touched. |
| **Harness** | `harness/`: `FrameMaxSizeProbeTest.java`, `proxy.py`, `probe.py` and `sample.sh` (all four verbatim from B2e/B3e); `extract-probe.sh` (D1 fix); drivers `run-unit.sh` and `run-cluster.sh`; `analyze.py` (readings summary). Not committed (to go under `cassandra/stage4-runtime-verification/harness/frameencoder_payload_max_size-payload-max_size--autonomous/`). |
| **Tiers and values** | Unit: `MAX_SIZE` = `1 << 17`, `1 << 16`, `1 << 15` (M17/M16/M15), with S = 4 MiB and 8 MiB (×2). Cluster: M17/M16/M15 at K = 8; M17 at K = 4; M17 with `networking_cache_size: 16MiB`. |
| **Audit bottom line** | **Ready after amendments**, 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: off-heap networking `BufferPool` bytes held by outbound v5 frames |
| A | knob varied, ≥ 3 values incl. default — or another approach | Met | B2b/B3b: a constant, so it is varied by recompiling line 41 (131072/65536/32768). Values above 128 KiB are invalid on the wire (B2b) |
| A | real resource measured, not only the counter | Partly | `usedSizeInBytes()`/`UsedSize` sums the real buffer capacities (`BufferPool.java:950`, `:891`), not a check counter; NMT `Other` is the secondary real-memory reading (B3d). The unit tier does not measure the body allocator (B2d says so) |
| A | usage driven to the limit and past it | Met | B2c: envelope ≫ F, so the large-message branch is always taken; B3c: about 56 MB must stay in Netty, far above one frame |
| A | positive control (negative estimate) | Met | B2h: S 4→8 MiB; B3h: K 4→8, and `networking_cache_size: 16MiB` (a cap known to bind on the same pool) |
| B | each step says what it establishes | Met | B2h/B3h controls list what each establishes |
| B | prediction in numbers | Met | B2f is exact to the byte; B3f gives ±5% around R − B_k |
| B | every plausible outcome has a row | Met | B2g/B3g: flat, follows M, ≈ K × M, limit never reached, stale build, invalid run |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Met (adapted) | A negative claim: the "flat" row plus the positive controls moving, and the mechanism control (maxData follows F) showing that the edit took effect |
| B | alternative explanations and their controls | Met | stale inlined constant (printed constant, javap), kernel absorbing frames (B_k measured), proxy bypass (`pool hosts`) |
| C | a human can follow it from the intro and B1 | Met | |
| C | an AI can run it without re-deriving the code | Partly | Ran as written, except D1 (PROBE extraction) and D2 (pidfile wait) in §3 |
| C | values, commands, observables, sampling exact | Met | |
| D | harness and environment prerequisites | Partly | B2a's paths (`/mydata/o124-s3`, `~/cassandra-5.0.9`) do not exist on the stage-4 nodes: amendment A1 |
| D | workload arithmetic reaches the limit | Met | 64 MiB of data, about 2 GiB of disk, a 2 GiB heap; node has 125 GiB and 706 GiB free on `/mydata` |
| D | citations spot-checked | Met | `FrameEncoder.java:41`, `Flusher.java:47-49,152,163-206`, `FrameEncoderCrc.java:71-72`, `BufferPool.java:282-285`, `BufferPools.java:43-52`, `BufferPoolMetrics.java:52-64` checked in the copy (FrameEncoder.java and Flusher.java md5-identical to the repo's `systems/cassandra/source/`) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| A1 | Work directory `/mydata/jingsong-cass-s4/o124`; source copy `cp -a /mydata/s4/cassandra-base` | applied, 2026-11-25 (B2a) | environment.md; B2a's paths do not exist |
| A2 | Scope `JVM_EXTRA_OPTS`/heap variables to `bin/cassandra`; `ulimit -n 100000` | applied (B3a) | environment.md §6; soft limit 1024 on the node |
| A3 | Expect two server connections on 9042 (control + pool), both from the proxy; sum B_k over both | applied (B3h) | the driver's control connection also uses the contact point |
| R1 | State a tolerance for "OverflowSize rises by ≈ ΔU − 16 MiB" (the pool's allocated 16 MiB includes free space in other threads' local pools) | left for stage 3 | not needed for a B3g row |
| R2 | Run the cluster-tier NMT check in fresh JVMs only (load data in a separate JVM run) | left for stage 3 | see §4.2 part 6 |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 00:10–00:55 MST |
| Node | `pc72` (`node2.jason92-326665…`, UMass), **x86_64**, 40 cores, 125 GiB, local `/mydata` (753 GB LVM, 706 GB free) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK | OpenJDK 11.0.33 (2026-10-20) |
| Ant | Apache Ant 1.10.12 |
| Local source copy | `cp -a /mydata/s4/cassandra-base` → `/mydata/jingsong-cass-s4/o124/src` (the `copy-source.sh` copy of repo `systems/cassandra/source/`, `cassandra-5.0.9`); repo HEAD at run time `cd9e1cded` |
| Case-file commit / harness commit | `bef6bc8a6` / not committed |
| Storage for node data | `/mydata/jingsong-cass-s4/o124/src/data` (local disk) |
| Full logs | `~/writeup-ext/out/o124/raw/` (copied from the node); small logs also left in `pc72:/mydata/jingsong-cass-s4/o124/` (3.4 MB). The source copy, build and data were deleted |
| Kernel buffers | `tcp_wmem` max 4,194,304; `tcp_rmem` max 6,291,456 |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file version |
|---|---|---|---|---|---|---|
| D1 | 1 (unit) | B2e step 2 (and 3, 4) | `grep -o 'PROBE…' TEST-*.xml` found nothing: the `testsome` JVM sends `System.out` to a logger (`SubstituteLogger`), one log line per `printf` fragment, and the XML has no stdout. The test itself passed and its values were in the ant log (`raw/logs/attempt1-defectD1/`) | Capture the ant output and rebuild the PROBE lines from it (`harness/extract-probe.sh`) | 2026-11-25: B2f/B2g unchanged; unit tier restarted from M17 | amended (`case-amended.md` B2e) |
| D2 | 1 (cluster) | B3e step 6 | `while kill -0 $(cat cassandra.pid)` ended at once: the JVM deletes its pidfile (`deleteOnExit`, `CassandraDaemon.java:733`) at the start of shutdown, so the next start found 7000/7199 busy and the driver stopped (`raw/logs/attempt1-defectD2-cluster/`) | Read the pid once after start (`node.pid`) and wait on that copy | 2026-11-25: B3f/B3g unchanged; cluster tier restarted from step 4 with clean data | amended (`case-amended.md` B3e) |

The first cluster attempt's M17 K = 8 and K = 4 readings (before D2 stopped it) agree with the restart (ΔU 58,341,376 vs 57,948,160 B). They are kept as evidence but not used.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `raw/logs/unit-driver.typescript`, `raw/logs/cluster-driver.typescript`.

### 4.1 Readings

**Unit tier** (`raw/unit-M17.txt`, `raw/unit-M16.txt`, `raw/unit-M15.txt`; S = 8 MiB, envelope 8,388,617 B)

| Run | printed `MAX_SIZE` / `MAX_FRAMED_PAYLOAD_SIZE` | frames | maxData | maxWire | sumWire | heldDelta (8 MiB, ×2) | heldDelta (4 MiB) | releasedDelta | hardCheck 131071 / 131072 |
|---|---|---|---|---|---|---|---|---|---|
| M17 | 131072 / 131060 | 65 (4 MiB: 33) | 131054 | 131064 | 8,389,267 | 8,390,656 / 8,390,656 | 4,194,912 | 0 | accepted / rejected "Maximum payload size is 128KiB" |
| M16 | 65536 / 65524 | 129 (65) | 65518 | 65528 | 8,389,907 | 8,392,704 / 8,392,704 | 4,196,352 | 0 | accepted / rejected |
| M15 | 32768 / 32756 | 257 (129) | 32750 | 32760 | 8,391,187 | 8,394,752 / 8,394,752 | 4,198,400 | 0 | accepted / rejected |

Every value equals the B2f table exactly. heldDelta spread across `MAX_SIZE` at 8 MiB: 4,096 B (0.049%). Ratio 8 MiB / 4 MiB: 2.0002 (M17).

**Cluster tier** (`raw/cluster-*.txt`, summarised by `harness/analyze.py` in `raw/analysis.txt`; R = K × 8,388,617)

| Value | Run | baseline UsedSize | peak paused UsedSize | ΔU | B_k (srvSendQ + proxyRecvQ) | R − B_k | ΔU / (R − B_k) | pooled `Size − OverflowSize` at peak | after release − baseline | NMT Other committed, base → peak (KB) |
|---|---|---|---|---|---|---|---|---|---|---|
| M17 | K = 8 | 67,342,848 | 125,291,008 | 57,948,160 | 9,168,404 | 57,940,532 | 1.0001 | 67,108,864 | 0 | 417,764 → 409,706 |
| M17 | K = 4 | 67,342,848 | 91,204,096 | 23,861,248 | 9,757,698 | 23,796,770 | 1.0027 | 67,108,864 | 0 | 458,849 → 458,897 |
| M17 | cache 16 MiB, K = 8 | 0 | 57,552,208 | 57,552,208 | 9,627,471 | 57,481,465 | 1.0012 | **16,777,216** (OverflowSize 0 → 44,823,888) | −2,052 | 294,860 → 346,923 |
| M16 | K = 8 | 0 | 57,438,208 | 57,438,208 | 9,692,024 | 57,416,912 | 1.0004 | 67,108,864 | 0 | 286,649 → 344,142 |
| M15 | K = 8 | 0 | 57,878,528 | 57,878,528 | 9,266,899 | 57,842,037 | 1.0006 | 67,108,864 | 0 | 286,659 → 344,122 |

- Plateau: UsedSize was identical in all 10 paused samples of every run (0% spread).
- Every run: `pool hosts: ['127.0.0.1:19042']`; all `result sizes` = 8,388,608; two server-side connections on 9042 (two `srvSendQ` lines per sample).
- Startup log lines: `… 128.000MiB for networking` (M17/M16/M15) and `… 16.000MiB for networking` (cache 16 MiB).
- Rebuilt constants: `javap` of the node jar shows `ldc int 131072 / 65536 / 32768` in `Flusher.<clinit>` (`raw/cluster-buildcheck-M1*.javap`), and the B2 test after each `ant clean jar` printed 65524 / 32756 (`raw/cluster-buildcheck-M16.txt`, `-M15.txt`).
- Baseline UsedSize in the M17 runs includes OverflowSize 67,113,472 B left over after the 8 × 8 MiB INSERTs of the data load (same JVM); the later runs started fresh JVMs and show 0.

### 4.2 Conclusion and logic

1. **Validity.** Both tiers valid. Unit: the printed constants match B2b at each value [observed: `unit-M1*.txt`], the large-message branch was taken (frames > 1) [observed], and S moved heldDelta 2× [observed]. Cluster: the proxy was in the path [observed: `pool hosts` line, two 9042 connections in `cluster-*.txt`], the kernel queue was measured (B_k ≈ 9.2–9.8 MB) [observed], about 57 MB stayed in the pool during every pause [observed], the node ran the rebuilt jar [observed: `cluster-buildcheck-*.javap`], and data, heap, yaml and workload were the same across M values except the data-load step, which ran only before M17 [observed: `cluster-driver.typescript`].
2. **Readings.** Nothing unusual on the primary observables. Two secondary oddities: (a) the M17 K = 8 run's NMT `Other` fell by 8 MB during the pause while pooled `Size` grew by 56 MiB; (b) OverflowSize was 64 MiB at baseline after the data load and read −2,052 B after release in the cache-16 run [observed: `cluster-M17-K8.txt`, `cluster-M17-cache16.txt`].
3. **Matched rows.**
   - B2g "heldDelta ≈ envelope size (±1%) at all three `MAX_SIZE` values, and doubles from S = 4 to 8 MiB → Claim confirmed": heldDelta is 8,390,656 / 8,392,704 / 8,394,752 B, 1.0003–1.0007 × the envelope, and 2.0002× from 4 to 8 MiB [observed: `unit-M1*.txt`]. Mechanism row: maxData 131054 / 65518 / 32750 and frames 65 / 129 / 257 [observed].
   - B3g "ΔU ≈ R − B_k and equal (±5%) at M17/M16/M15; ΔU halves at K = 4; the cache-16 MiB run caps pooled `Size` at 16 MiB → Claim confirmed": ΔU / (R − B_k) = 1.0001 / 1.0004 / 1.0006, M16 and M15 = 0.991 and 0.999 × M17; K = 4 gives 1.0027 × (R/2 − B_k), which is the B3f form of "halves" (the raw ΔU is 0.41× because B_k is a fixed ~9.5 MB); cache 16 MiB: pooled part exactly 16,777,216 B, overflow took the rest, ΔU unchanged [observed: `analysis.txt`].
4. **Excluded rows.** Unit: "heldDelta scales with `MAX_SIZE` (M15 ≤ 0.6 × M17) or ≤ 2 × `MAX_SIZE`" (refuted row): M15/M17 = 1.0005, and heldDelta ≈ 64–256 × `MAX_SIZE` [observed]. "No move between 4 and 8 MiB, or frames = 1": moved 2×, frames ≥ 33. "Constant ≠ table": equal. "releasedDelta ≫ 0": 0. Cluster: "ΔU scales with `MAX_SIZE` or ≈ K × `MAX_SIZE`" (refuted row): ΔU(M15)/ΔU(M17) = 0.999, and ΔU ≈ 57 MB ≫ 8 × 128 KiB = 1 MiB [observed]. "ΔU ≈ 0, or K = 4 vs 8 no change": ΔU 57.9 vs 23.9 MB. "Cache-16 pooled `Size` > 16 MiB": exactly 16 MiB. "Results ≠ 8 MiB or timeouts": none.
5. **Observed vs. inferred.** The conclusion rests on observed readings. Inferred: (i) that the UsedSize delta is outbound frame buffers, not inbound or other pool users [inferred: the probe sends 8 small SELECTs; ΔU tracks R − B_k within 0.3% in five runs; the unit tier isolates frames on a heap body]; (ii) the explanation of the M17 NMT anomaly (part 6).
6. **Deviations and gaps.** (a) D1 and D2 (§3), each fixed and its tier restarted. (b) **NMT `Other`** rose by ≈ ΔU in the M16 and M15 runs (+57,493 and +57,463 KB = 58.9 MB ≥ ΔU, and the two within 0.05% of each other) and by 53.3 MB (0.93 × ΔU) in the cache-16 run. In the M17 K = 8 run it **fell** by 8 MB, which is not the B3f "rises by at least ΔU, similar across M (±10%)". That run followed the 64 MiB data load in the same JVM. A G1 humongous-allocation GC ran inside its pause window (`raw/logs/gc-M17-K8-K4.log`, GC(6) at 07:38:07 UTC). The pool still counted 64 MiB of inbound overflow buffers as in use. The likely cause is that GC freeing about 64 MB of direct memory that was no longer referenced but still counted by the pool, which hides the 56 MiB of new chunks [inferred]. The NMT line is a secondary observable with no row in B3g, so the verdict rests on the pool readings, which sum real buffer capacities. The NMT readings agree in the three fresh-JVM runs; recommendation R2. (c) B3f's "OverflowSize rises by ≈ ΔU − 16 MiB": it rose 44.8 MB against 40.8 MB predicted, because only 12.7 MB of the 16 MiB pooled allocation was in use (the rest was free space held by other threads' local pools). The B3g row requires only the 16 MiB cap, which held exactly (R1). (d) The unit tier does not see real socket draining or the Netty body allocator, as B2d says.
7. **Core question.** Usage did not follow the constraint. Cutting `MAX_SIZE` 4× cut frame size 4× and multiplied the frame count by 4 (part 3, mechanism). Total off-heap frame memory stayed within 0.05% (unit) and 1% (cluster) across the three values (part 3), while the positive controls moved it: response size 2× (unit), K = 4 vs 8 (cluster), and `networking_cache_size` 16 MiB capping the pooled part (cluster). `FrameEncoder.Payload.MAX_SIZE` sets frame granularity; it does not cap memory.

**Conclusion (one line):** B2g "Claim confirmed" and B3g "Claim confirmed": confirmed, does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `unit-M1*.txt` (constants), `cluster-M1*-K8.txt` (`pool hosts`, two `srvSendQ` lines, `result sizes`), `cluster-buildcheck-M1*.javap` (131072/65536/32768), and the `Global buffer pool limit` lines in `cluster-driver.typescript` |
| 2. Readings | yes | NMT and OverflowSize oddities re-read in `cluster-M17-K8.txt`, `cluster-M17-cache16.txt` and `gc-M17-K8-K4.log` (GC(6) 00:38:07.085-0700 = 07:38:07 UTC; pause window 07:38:02–07:39:10 UTC) |
| 3. Matched row | yes | Recomputed ΔU, B_k and the ratios from the raw samples (`analysis.txt`, regenerated after fixing the parser for negative values); unit figures compared to the B2f table cell by cell |
| 4. Excluded rows | yes | Every B2g/B3g row addressed, including both refuted rows |
| 5. Observed vs. inferred | yes | Inference (i) is backed by five runs and the unit isolation; inference (ii) affects only a secondary line |
| 6. Deviations and gaps | yes | D1/D2 restarts confirmed in the typescripts (`attempt1-*` folders hold the stopped attempts) |
| 7. Core question | yes | The logic follows B1: mechanism moved, total flat, controls moved |

### 5.2 Run 2?

**No** (2026-11-25). The conclusion rests on observed readings that match the byte-exact unit prediction and are tight in the cluster tier (≤ 1%). It confirms the filed estimate; it is neither a refutation nor a bypass. The one secondary anomaly (NMT in the M17 run) has an identified confound and does not decide any row.

## 6. Run 2 — not done

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap; both tiers agree).

**Claim tested (B1):** changing `FrameEncoder.Payload.MAX_SIZE` (131072 → 65536 → 32768, recompiled) changes the size and number of
outbound v5 frame buffers for a large CQL response, but does **not** change the total off-heap memory they occupy, which stays
about equal to the response bytes in flight (±1% unit, ±5% cluster).

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g "heldDelta ≈ envelope at all three values, doubles 4→8 MiB": **Confirmed** | does not cap | run 1 + self-check | 2026-11-25 |
| Cluster | B3g "ΔU ≈ R − B_k, equal across M17/M16/M15, halves at K = 4, cache-16 caps pooled Size": **Confirmed** | does not cap | run 1 + self-check | 2026-11-25 |

**Positive control:** unit: S 4 → 8 MiB moved heldDelta 4,194,912 → 8,390,656 B (M17). Cluster: K 4 → 8 moved ΔU 23.9 → 57.9 MB (each matching R − B_k), and `networking_cache_size: 16MiB` held the pooled part at exactly 16,777,216 B (known cap, same pool).

**Feedback filed:** section D of `~/writeup-ext/out/o124/case-amended.md` (not in the repo). Amendments A1–A3 and D1–D2 are dated in B2a, B2e, B3a, B3e and B3h. The new sha256 `954ff8d928d1334537ffcc8ba02e0e9976be753cf72340d30ea9a9c7f6c51bd0` is for `_INDEX.md` §4 when the files are filed. Index row: `Confirmed — does not cap` (both tiers), outcome class **TN**.

**Side observation for stage 3 (outside this case):** after 8 inbound 8 MiB INSERTs, networking-pool `OverflowSize` stayed at 67,113,472 B for the rest of the JVM's life (M17 K = 8 and K = 4 baselines, after release), and read −2,052 B after release in the 16 MiB run. This may be an overflow-accounting mismatch on the inbound large-message path (`CQLMessageHandler` large frames → `BufferPool` overflow).
