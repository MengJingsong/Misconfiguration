# native-write-buffer-water-mark-initializechannel-pendingoutboundbytes--autonomous — stage-4 results  <!-- file: results/native-write-buffer-water-mark-initializechannel-pendingoutboundbytes--autonomous.md -->

> **Case:** [`native-write-buffer-water-mark-initializechannel-pendingoutboundbytes--autonomous`](../../stage3-ai-deep-read/cases/native-write-buffer-water-mark-initializechannel-pendingoutboundbytes--autonomous.md) (stage-3 order o133, writeup-set-ext.csv, band B; amended working copy `~/writeup-ext/out/o133/case-amended.md`, outside the repo)
>
> **Status:** self-checked, verdict filed by the stage-4 session (2026-11-25); run 2 not chosen
>
> **Outcome class:** undetermined (estimate `negative`; unit **Not confirmed**, cluster **Not confirmed**: each tier missed one frozen control threshold; every main reading points to `does not cap`)
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the case
> file's feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `cd9e1cded`; the case file is committed (`bef6bc8a6`). Filing sha256 `d1395d14645bed32ae00ce34ec6a4de89d66f173a366644ce49493b270c1a376` (equal to `_INDEX.md` §4; copy `harness/case-as-filed.md`). Audit amendments S4-A1 to S4-A5 written into the working copy and frozen at 2026-11-25 08:32:08 UTC (`5becb582…`) before any reading; fix D1 (runbook, from the K = 8 shakedown, B2f/B2g unchanged) at 08:33:53 UTC, before the sweep: **frozen sha256 `a1875cc59e66caa8e48ef984a62f8c19ad1f3379b97a4a1a03e84f46cde1aa95`** (`harness/case-frozen.md`, `harness/freeze.sha256`). Final file sha256 after the section-D result paragraph: `b3f16968aaac4e241149d6e1e03c8942dd7c6c413358ad743a0fdd9a616bd49f`. Sections A, B1, the B2f/B2g/B3f/B3g rows and every other line of the filed text are byte-identical (the only removed line is section D's "none yet"). |
| **Harness** | `~/writeup-ext/out/o133/harness/` (to become `harness/native-write-buffer-water-mark-initializechannel-pendingoutboundbytes--autonomous/`): `WriteWaterMarkBacklogTest.java` (B2a with S4-A1, S4-A2, D1), `WriteWaterMarkBacklogTest-as-filed.java` (verbatim B2a), `unit-run.sh`, `unit-all.sh`, `wm_client.py` (verbatim B3c), `mkconf.py`, `cluster-sampler.sh`, `cluster-cell.sh`, `cluster-all.sh`, `analyze_unit.py`, `analyze_cluster.py`, `md5-node.txt`, `md5-repo.txt`. Not committed by this session. |
| **Tiers and values** | Unit (B2): high mark ∈ {32768 (stock), 1048576, 67108864} × blob B ∈ {16384, 65536, 262144} × K ∈ {64, 256}; client-reads control (32768, 65536, 256); gate control (`autoread`, S4-A2) at B ∈ {65536, 262144}, K = 256; three repeats of (32768, 65536, 256); the as-filed gate once as a diagnostic. Cluster (B3): one node, 1 GiB heap, `MaxDirectMemorySize=1G`, NMT summary; cells A (K 64, unpaged), B (K 256, unpaged), C (K 256, page 64), D (K 256, client reads), B repeated. The mark itself is n/a in this tier (hard-coded, B3b). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 (S4-A1 to S4-A5, D1; in the case file next to the text they change and listed in section D) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: queued response bytes per channel (`totalPendingWriteBytes`) backed by pooled direct memory. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | Hard-coded; B2 varies it in a test subclass (32 KiB stock, 1 MiB, 64 MiB); B3 says n/a and why. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit reads Netty's own operand (the counter); cluster measures NMT "Other" committed and RSS; the gap (pooled-arena memory not seen in B2, per-channel operand not seen in B3) is named in B2d/B3d. |
| A. Core question | usage driven to the limit and past it | Met | Unit K·R from 1 MiB to 64 MiB vs a 32 KiB mark; cluster 67–270 MB. |
| A. Core question | positive control (negative claim) | Partly → Met after S4-A2 | B2: the gate is the right idea, but as filed it overrides `read()`, which an `autoRead` channel never consults (Netty 4.1.130 bytecode: `OP_READ`/`EPOLLIN` cleared only when `autoRead` is off). Replaced by `setAutoRead(isWritable())`. B3: page size (cell C) and client reads (cell D). |
| B. Logic | each step says what it establishes | Met | B2h, B3h. |
| B. Logic | prediction in numbers | Partly → Met after S4-A3 | B2f's stock band K·R − 64 KiB … K·R omits Netty's 96-byte per-entry overhead × 2 messages per v4 response (`Envelope.java:503-512`), up to +48 KiB at K = 256; "64 MiB is above every backlog" is false for the largest cell. |
| B. Logic | every plausible outcome has a row | Partly → Met after S4-A4, S4-A5 | Rows exist for every outcome, but "≈", "same", "near", "scale" and "hundreds of MiB" had no thresholds and no verdict labels; ΔOther in B3 had no defined window. |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met (negative claim) | Flat across the mark, `writable=false` with pending ≫ mark (the flag fires but nothing acts), controls bind. |
| B. Logic | alternative explanations and controls | Met | Client-reads (leak), gate / page size (workload can show a cap), fixed `SO_SNDBUF` (kernel share), heap-after-GC (off-heap), repeats. |
| C. Specific | understandable from the intro and B1 | Met | Estimate, Ground, A3, B1. |
| C. Specific | an AI can run the runbook without re-deriving | Partly → Met after S4-A1, S4-A5, D1 | Paths are generic (`~/cassandra-5.0.9`); end-of-hold BytesSent not read; epoll mismatch found in the shakedown (D1). |
| C. Specific | values, commands, observables exact | Met | B2e, B3e. |
| D. Runnable | prerequisites exist | Met | JDK 11.0.33, Ant 1.10.12, built 5.0.9 copy `/mydata/s4/cassandra-base` (md5 of `PipelineConfigurator`, `Flusher`, `Envelope`, `PreV5Handlers`, `CBUtil`, `CQLTester`, `build.xml`, `cassandra.yaml`, `cassandra-env.sh` equal to the repository's source); Netty 4.1.130. |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit ≤ 64 MiB direct in a 4 GiB test JVM; cluster ≤ 270 MB vs 1 GiB direct; 700 GB free on `/mydata`; `tcp_wmem` max 4 MiB. |
| D. Runnable | citations spot-checked | Met | `PipelineConfigurator.java:139` (the mark), `:117-127` (the 4-arg test constructor), `:273`/`:347` (`onInitialPipelineReady`); `Flusher.java:145`, `:205`, `:249-250`; `Envelope.java:503-512`; `CBUtil.java:60`; `CQLTester.java:621-632`; `PreV5Handlers.java:224/236` (the only `setAutoRead`); grep of `transport/` for `writab`/`watermark`: line 139 only. All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | Node paths, built copy, echo fields (`cfgHigh`, `cfgLow`, gate, `autoRead`, `open`, pipeline) | applied 2026-11-25 | runnable on this node; makes "the knob took effect" observable |
| S4-A2 | Gate control by `setAutoRead(isWritable())`; as-filed gate kept as a diagnostic | applied 2026-11-25, before any reading | the as-filed gate cannot bind on an `autoRead` channel |
| S4-A3 | B2f band includes Netty's 192 B per v4 response | applied 2026-11-25, before any reading | arithmetic from Netty and `Envelope.Encoder` |
| S4-A4 | B2g thresholds and verdict labels | applied 2026-11-25, before any reading | undefined words |
| S4-A5 | B3e per-cell NMT window, BytesSent at end of hold, B3g thresholds and labels | applied 2026-11-25, before any reading | row 2 needs produced-before-drain; ΔOther had no window |
| D1 | Configurator `epoll` flag follows the server's | applied 2026-11-25 after the shakedown, before the sweep | bind failure (section 3) |
| R-a | Stage 3: when a design adds a Netty handler as a control, check `autoRead` semantics | left for stage 3 | general lesson |

**Agreement criteria** — run 2 not planned.

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-25 UTC: unit shakedowns 08:32:13 (D1) and 08:33:13; unit sweep 08:33:54–08:43:44; cluster attempt 08:44:55 aborted before any cell (D2); cluster run 08:45:53–08:53:24 | not done |
| Node | `pc75` (`node3.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`), **x86_64**, Intel Xeon E5-2660 v2, 40 cores, 125 GiB RAM, `/mydata` 753 GB (700 GB free); held under `/mydata/s4/NODE-LOCK` for the whole run | |
| OS / kernel | Ubuntu 22.04.2 LTS / `5.15.0-203-generic`; `tcp_wmem` 4096 16384 4194304 | |
| JDK / Ant | openjdk 11.0.33 (2026-10-20) / Ant 1.10.12; Netty 4.1.130.Final | |
| Local source copy | `cp -a /mydata/s4/cassandra-base` → `/mydata/jingsong-cass-s4/o133/c509` (both tiers); 5.0.9, md5 of 9 cited files equal to repo `systems/cassandra/source` (repo HEAD `cd9e1cded`, source clean); `ant build-test` 14 s after adding the test | |
| Storage | unit: the tree's `build/test`; cluster: `c509/{data,logs}` on `/mydata`, ports 19142/17100/17101/17199 — tree removed after the run | |
| Logs | node `pc75:/mydata/jingsong-cass-s4/o133/{unit,cluster,logs,harness}` (8 MB kept); copies here: `run1/unit/{shakedown,run1}/` (`run-<label>.log`, `TEST-<label>.xml`, `wmresult.txt`, one test log), `run1/cluster/run1/{A,B,C,D,B-rep}/` (`session.txt`, `samples.txt`, `client.txt`, `nmt-diff-*.txt`, `heapinfo-*.txt`, `ss-*.txt`), `run1/cluster/run1/{session.txt,system.log,jvm-args.txt}`, `run1/cluster/aborted-D2/`, `run1/analysis-{unit,cluster}.txt` | |

No partial `o133` folder from earlier attempts existed on `pc75`. An earlier unmodified copy of the case file in `~/writeup-ext/out/o133/` (sha256 = filing) was moved to `prior-draft/` and not used.

## 3. Runbook defects

| # | Step | Problem | Fix | §9a changed? |
|---|---|---|---|---|
| D1 | B2a test / B2e.2 | `ProbeConfigurator` called `super(false, …)` (NIO). `CQLTester`'s `Server` uses an `EpollEventLoopGroup` on this node (`Server.java:98-99`), so the NIO server channel cannot register: `IllegalStateException: Failed to bind port … Caused by: incompatible event loop type: io.netty.channel.epoll.EpollEventLoop` (`run1/unit/shakedown/TEST-shake-h32768-B16384-K8.xml`) | pass `NativeTransportService.useEpoll()` as `Server.java:107` does | no |
| D1b | B2e.2 "collect the WMRESULT line from the XML" | the line reaches the `ant` console log, not the XML `system-out` | `unit-run.sh` collects it from the console log | no |
| D2 | B3e.1 (harness `cluster-all.sh`) | the start wait used `grep -q running`, which matches `nodetool statusbinary`'s "not running"; the driver went on 7 s after start, insert and warm-up were refused (`run1/cluster/aborted-D2/session.txt`); stopped before any cell | exact match `grep -qx running`, plus abort checks after start, insert and warm-up; node data wiped, tier restarted from step 1 | no |

Found in the unit shakedown (high 32768, B 16384, K 8). The second shakedown passed and gave the known answer: R = 16455, produced = 131,640 = 8·R exactly, pendingSettled 116,424 (inside 8·R − 64 KiB … 8·(R + 192)), `writable=false`, `cfgHigh=32768 cfgLow=8192` (`run1/unit/shakedown/`).

## 4. Run 1

**Scope:** unit tier B2 as amended (25 JVMs: 18 grid cells, client-reads control, 2 gate controls, 3 repeats, 1 as-filed gate diagnostic); cluster tier B3 as amended (one node; cells A, B, C, D and a repeat of B). **Command log:** `run1/unit/run1/run-<label>.log`, `run1/cluster/run1/session.txt` and `<cell>/session.txt`. **Analyzers:** `harness/analyze_unit.py` → `run1/analysis-unit.txt`; `harness/analyze_cluster.py` → `run1/analysis-cluster.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/run1/wmresult.txt`; every JVM 1 test, 0 failures, 0 errors; every channel `open=true`, `stable=20`, `cfgHigh` = the intended mark, `cfgLow` = high/4)

| (B, K) | R | K·R | P at 32 KiB (stock) | P at 1 MiB | P at 64 MiB | S4-A3 band | writable 32K / 1M / 64M |
|---|---|---|---|---|---|---|---|
| 16384, 64 | 16455 | 1,053,120 | 1,048,656 | 1,048,656 | 1,048,656 | 987,584 … 1,065,408 ✓ | false / false / true |
| 16384, 256 | 16455 | 4,212,480 | 4,244,880 | 4,244,880 | 4,244,880 | 4,146,944 … 4,261,632 ✓ | false / false / true |
| 65536, 64 | 65607 | 4,198,848 | 4,211,031 | 4,211,031 | 4,211,031 | 4,133,312 … 4,211,136 ✓ | false / false / true |
| 65536, 256 | 65607 | 16,795,392 | **16,844,439** | 16,844,439 | 16,844,439 | 16,729,856 … 16,844,544 ✓ | false / false / true |
| 262144, 64 | 262215 | 16,781,760 | 16,793,943 | 16,793,943 | 16,793,943 | 16,716,224 … 16,794,048 ✓ | false / false / true |
| 262144, 256 | 262215 | 67,127,040 | **67,176,087** | 67,176,087 | 67,176,087 | 67,061,504 … 67,176,192 ✓ | false / false / false (S4-A3) |

P = pendingSettled = pendingMax in every cell; produced = K·R exactly. Ratios at the stock mark: K 256 / 64 = 4.048, 4.000, 4.000; B ×4 steps 3.97–4.02. Repeats (32768, 65536, 256): 16,844,439 four times (spread 0, noise n = 64 KiB).

| Control | P | produced | other | Frozen bound | Holds? |
|---|---|---|---|---|---|
| Client reads (32768, 65536, 256) | 0 | 16,795,392 | clientBytes 16,795,392 | P ≤ 64 KiB, clientBytes = produced | **yes** |
| Gate `autoread` (32768, 65536, 256) | **394,689** | 393,642 (6 responses) | `autoRead=false`, `wm-gate` first in pipeline | ≤ 295,964 and ≤ 2 % of stock (336,889); produced < K·R | **no** (6 responses held vs ≤ 4; 2.34 %) |
| Gate `autoread` (32768, 262144, 256) | **1,574,337** | 1,573,290 (6 responses) | `autoRead=false` | ≤ 1,082,396 and ≤ 1,343,522 | **no** (2.34 %) |
| As-filed gate, diagnostic (32768, 65536, 256) | 16,844,439 | 16,795,392 | `autoRead=true`, `wm-gate` in pipeline | — (not used) | did not bind, as S4-A2 predicted |

**Cluster tier** (`run1/cluster/run1/`; 1 GiB heap, `-XX:MaxDirectMemorySize=1G` effective (last flag), NMT summary; 0 `^ERROR` lines, no `OutOfDirectMemoryError`; client `--hold 60`)

| Cell | produced at end of hold (BytesSent Δ) | Send-Q / Recv-Q | backlog | ΔOther (NMT committed) | ΔRSS | heap after GC pre → end | after drain |
|---|---|---|---|---|---|---|---|
| A: K 64, unpaged | 67,373,385 (R 1,052,709) | 1,617,920 / 4,096 | **65.75 MB** | **+80.0 MiB** (summary.diff Other +81,896 KB) | +50.6 MiB | 66.8 → 66.9 MiB | Other 287 → 207 MiB |
| B: K 256, unpaged | 269,493,513 | 1,617,920 / 4,096 | **267.87 MB** | **+336.0 MiB** (diff +344,080 KB) | +187.1 MiB | 66.8 → 67.2 MiB | 543 → 271 MiB |
| C: K 256, page 64 | 16,857,865 (R 65,851) | 1,617,920 / 4,096 | 15.24 MB | **+16.0 MiB** | +3.8 MiB | 67.0 → 67.2 MiB | 287 (unchanged) |
| D: K 256, client reads | 269,493,513 = client read bytes | 1,519,616 / 0 (mid-burst) | — | **+112.0 MiB** peak, +96 MiB in the last sample before exit, **0** after exit | +15.2 MiB | 67.1 → — | 399 → 287 MiB (baseline) |
| B-rep | 269,493,513 | 1,617,920 / 4,096 | 267.87 MB | +256.0 MiB (from a 287 MiB start; same 543 MiB end as B) | +16.8 MiB | 69.7 → 70.0 MiB | 543 → 271 MiB |

Ratios: backlog B/A = 4.07; ΔOther B/A = 4.20; ΔOther B/C = 21.0.

### 4.2 Conclusion and logic

1. **Validity** — Valid. Unit: every JVM echoed the intended mark on the measured channel (`cfgHigh`, `cfgLow`), produced exactly K·R, the channel stayed open and the operand settled (20 equal samples). Cluster: the node ran with the intended flags (`jvm-args.txt`), every client exited 0 and drained exactly the BytesSent delta (67,373,376 / 269,493,504 / 16,857,856 B, = Δ − 9 for the STARTUP's READY), no ERROR frame, no `^ERROR` log line [observed].
2. **Readings** — Unusual: (i) the kernel holds almost none of the stock backlog in the unit tier: P = K·(R + 192) − 105 B in the B ≥ 64 KiB cells (only the first header entry was removed; Netty keeps a partly written message's full size in `totalPendingSize`) [observed: arithmetic on `wmresult.txt`]; (ii) the gate held exactly 6 responses at both B; (iii) cell D's transient rise while the 4 KiB-buffer Python reader lagged the 100 MB/s response stream; (iv) B-rep's ΔOther is 80 MiB smaller than B's because 80 MiB of pool chunks from cell A/C were still committed at its start; both end at 543 MiB [observed: `samples.txt`].
3. **Matched row** — Unit: the stock / flat / follows-workload conditions of B2g row 1 hold exactly (S4-A4); the client-reads control holds; the gate control misses its S4-A4 bound → per S4-A4 "a control fails" → **B2g row 5: Not confirmed**. Cluster: B3g row 1 thresholds hold (ΔOther A 80 ≥ 48 MiB, B 336 ≥ 200 MiB, backlog ratio 4.07 ∈ [3, 5], ΔOther ratio 4.20 ∈ [2.5, 6]); cell C holds (16 ≤ 336/7 = 48 MiB); cell D misses ΔOther ≤ 32 MiB in every in-run reading → S4-A5 control row fails → **Not confirmed** [observed].
4. **Excluded rows** — Unit row 2 (stock P ≤ 32 KiB + 4 R): P ≥ 1.05 MB in every cell [observed]. Row 3 (P follows the mark): P byte-identical at 32 KiB, 1 MiB, 64 MiB [observed]. Row 6 (P = −1): never [observed]. Cluster row 2 (enforced): backlog 65.8 / 267.9 MB and produced = K·R before the drain [observed]. Row 4 (instrument blind): ΔOther moved (+80 / +336 MiB, NMT diff agrees) [observed]. Row 6 (OOM / close): none [observed].
5. **Observed vs. inferred** — Inferred: (i) that the gate's extra two responses are requests already read and dispatched before the first response marked the channel unwritable (first-query latency on a fresh connection), not a failure of the gate to stop reading: supported by produced being exactly 6·R at both B and P = produced + 6·192 − 105, flat for the rest of the run [inferred]. (ii) That cell D's rise is a reader lagging, not a leak: Other is back to the pre-cell 287 MiB in the first sample after the client exits [observed numbers; cause inferred]. (iii) That ΔOther in A/B is the queued response buffers: heap flat, rise ≈ backlog rounded up to 16 MiB chunks, released on the drain [inferred from observed numbers; no allocation trace].
6. **Deviations and gaps** — S4-A1 to S4-A5, D1, D2 (sections 1 and 3). The ΔOther window for a read-mode cell (D) was not defined in S4-A5 (it names the "last sample before `draining`", which D does not have); this run reports the peak, the last in-run sample and the post-exit sample and takes no favourable one. The node is x86_64 (`pc75`); the design does not depend on timing beyond the gate's in-flight count.
7. **Core question** — Every main reading says the 32 KiB mark does not cap usage: on a client that stops reading, the server queues every response (1 MB to 67 MB in the unit tier, 268 MB of off-heap growth on a real node), independent of the mark (32 KiB, 1 MiB and 64 MiB give byte-identical pending bytes) and linear in K and response size; the mark only flips `isWritable()`. The positive controls show the same workload can show a cap (gate: held at 6 of 256 responses; page size: 21× less off-heap). But the frozen design required each control to meet a numeric bound, and the gate (unit) and the client-reads cell (cluster) missed theirs, so neither tier may be filed Confirmed.

**Conclusion (one line):** Unit B2g row 5, cluster B3g (S4-A5) control row failed — **Not confirmed** in both tiers; the readings themselves are all those of B2g/B3g row 1 (usage ≫ mark, flat in the mark, linear in the workload), so the effect is undetermined by the frozen rule and points to `does not cap`.

## 5. Self-check of run 1 — AI

Re-read by hand: all 25 `WMRESULT` lines in the console logs (fields `cfgHigh`, `cfgLow`, `gate`, `autoRead`, `open`, `pendingSettled`, `produced`, `pipeline`) and the `<testsuite>` tags; the band arithmetic for the six stock cells; for each cluster cell `session.txt` (BytesSent pre/endhold/post, client lines), every line of `samples.txt`, `nmt-diff-endhold.txt` (Other and Total), `heapinfo-pre/endhold.txt`, `errors-count.txt`; `system.log` WARN lines (startup only) and `jvm-args.txt`.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Echoes, exact produced, exact drained bytes. |
| 2. Readings | yes | The −105 B and the 6-response hold re-derived from the raw numbers. |
| 3. Matched row | yes | The gate figures 394,689 / 1,574,337 B re-read against 295,964 / 1,082,396 B and 2 %; D 399 / 383 / 287 MiB re-read. |
| 4. Excluded rows | yes | Each exclusion cites a re-read number. |
| 5. Observed vs. inferred | yes | Causes of both control misses marked inferred; they do not change the verdict. |
| 6. Deviations and gaps | yes | D window gap stated; no favourable window chosen. |
| 7. Core question | yes | Stated what the readings show and why the frozen rule still gives Not confirmed. |

### 5.2 Run 2?

**No** (2026-11-25). A run 2 repeats the same runbook and would hit the same two control bounds (the gate held exactly 6 responses at both B; D's reader is the same script). What would settle the tiers is a re-specified control, which is stage-3 work (section 8).

## 6. Run 2 — not done. ## 7. Comparison — not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** undetermined (both tiers Not confirmed; the weak rule does not apply because the unit tier did not settle).

**Claim tested:** (B1) On a native-transport (CQL v4) connection whose client stops reading, the server-side queued response bytes (`ChannelOutboundBuffer.totalPendingWriteBytes()`) and the matching off-heap memory grow in proportion to (requests sent × response size), far past the 32 KiB high water mark; changing the high mark leaves them unchanged.

| Tier | Verdict | Effect | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 5: **Not confirmed** — stock pending 1.05–67.2 MB = K·(R + 192) − ≤ 105 B, byte-identical at marks 32 KiB / 1 MiB / 64 MiB, ×4.0 in K and B, `writable=false`; client-reads control 0 B; **gate control held 6 responses (394,689 B, 2.34 % of stock) against a frozen ≤ 4 (295,964 B, 2 %)** | undetermined (readings point to does not cap) | run 1 + self-check | 2026-11-25 |
| Cluster | S4-A5 control row failed: **Not confirmed** — ΔOther +80 / +336 MiB for K 64 / 256 (backlog 65.8 / 267.9 MB, ratio 4.07), heap flat, released on drain; page-size control +16 MiB (21× less); **client-reads cell D +112 MiB peak / +96 MiB before exit against a frozen ≤ 32 MiB** (0 after exit) | undetermined (readings point to does not cap) | run 1 + self-check | 2026-11-25 |

**Positive control:** unit gate (`autoread`) bound the workload at 6 of 256 responses but missed its numeric bound; cluster page size (cell C) met its bound.

**Feedback filed:** the amended case file's section D (`~/writeup-ext/out/o133/case-amended.md`: amendments S4-A1 to S4-A5, fix D1, and the stage-4 result paragraph). No part of the trace was refuted. **For stage 3:** (1) the gate control's allowance must cover the requests read before the first response makes the channel unwritable (here 6 at 100 requests/s on a fresh connection), or the client should wait for the first response before trickling; (2) cell D needs a reader that keeps pace with the server (or a measurement window after it catches up) and a stated window; (3) a design that adds a Netty handler as a control should check `autoRead` semantics: the as-filed `read()`-swallowing gate cannot pause an `autoRead` channel, confirmed here (pending = stock with the gate in the pipeline). With those re-specified, a fresh run of both tiers should be able to settle the effect. **Leftovers on pc75:** nothing running (no CassandraDaemon, test JVM, Ant, client, sampler or driver; ports 19142/17100/17101/17199/9091 free); source tree and node data removed; kept `/mydata/jingsong-cass-s4/o133/{unit,cluster,logs,harness}` (8 MB). Driver PID file removed; node lock released at the end.
