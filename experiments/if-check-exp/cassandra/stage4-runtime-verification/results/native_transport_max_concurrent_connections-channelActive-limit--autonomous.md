# native_transport_max_concurrent_connections-channelActive-limit--autonomous — stage-4 results  <!-- file: results/native_transport_max_concurrent_connections-channelActive-limit--autonomous.md -->

> **Case:** [`native_transport_max_concurrent_connections-channelActive-limit--autonomous`](../../stage3-ai-deep-read/cases/native_transport_max_concurrent_connections-channelActive-limit--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/native_transport_max_concurrent_connections-channelActive-limit--autonomous/`](../harness/native_transport_max_concurrent_connections-channelActive-limit--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e;
> the case file's feedback section is its section D. Session: Claude Opus 5.5 (claude-opus-5-5), advisor-run, on the advisor's Mac.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Branch `advisor-run`, uncommitted on 2026-10-27 (as filed in `419619f`'s tree with sha256 `f565aebd…c190`). Frozen after the audit's 13 amendments (U1–U4, C1–C9): sha256 `8f7f52023b602252247f78a3a655169d0132f4f4a4832b6d19d3a4906a238153`, recorded in `_INDEX.md` §4 before any harness run or reading. No runbook fix followed, so this is the version both tiers ran. Section D is filled after the hash. |
| **Harness** | `harness/native_transport_max_concurrent_connections-channelActive-limit--autonomous/`: `ConnectionLimitProbeTest.java` (unit probe, copied into the clone only for the run), `unit-run.sh`; `hold.py` (the case's B3c client, verbatim, C2), `ntc.btm` (two observe-only Byteman rules: `NTCREFUSE` at the global-limit close in `channelActive`, C5; `NTCMEM` = `CBUtil.allocator` metric and `counter` on each `nodetool version`, C4), `cluster-run.sh`. Structure of `unit-run.sh`, `cluster-run.sh` and the `NTCMEM` rule adapted from `harness/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous/` (tools only; every number and expectation here derived from source). Self-check: `results/<stem>/run1/selfcheck.py`. Uncommitted (no commit asked). |
| **Tiers and values** | Unit: one test, runs `L-1`, `L0`, `L8`, `L32` (64 `EmbeddedChannel`s each, S = 1,048,576 body bytes written to each open channel) and control `S0` (L = 8, nothing written); per-IP limit -1. Cluster: one node (127.0.0.1, 4 GiB heap), L ∈ {-1 (default), 200, 50}, a fresh node per value; N = 300 connections each sending a 9-byte v4 STARTUP header declaring 16,000,000 body bytes plus S = 4,194,295 body bytes (4 MiB in all); on the L = -1 node also the positive control N = 100 and the `s0` control (N = 300, nothing sent). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: live native connections, a count whose byte size is the decoder's cumulation of a partly received envelope (≤ `native_transport_max_frame_size`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b {-1, 0, 8, 32}; B3b {-1, 200, 50}; -1 is the default (`Config.java:289`). |
| A. Core question | real resource measured, not only the counter | Partly | Unit: `internalBuffer().readableBytes()` (the held bytes themselves, not process memory; gap named in B2d). Cluster: B3d's heap ΔH cannot see the bytes, by source: the cumulation is direct memory with or without the heap-allocator flag (C4: Netty `ioBuffer()` returns direct when Unsafe is present; the merge cumulator keeps and grows the first read buffer). Replaced by the native-transport allocator's own metric (C4); heap kept as context. |
| A. Core question | usage driven to the limit and past it | Met | N = 64 > L ∈ {8, 32} (unit); N = 300 > L ∈ {200, 50} (cluster); L = -1 positive control. |
| B. Logic | each step says what it establishes | Met | B2h/B3h controls: positive control, S = 0 control, counter reset, independent socket count. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | Exact for unit, but the L = -1 `counter` = 64 is wrong by source (no handler is installed when both limits are ≤ 0, `PipelineConfigurator.java:240-245`); corrected to n/a, reads 0 (U3). Cluster bands numeric. |
| B. Logic | every plausible outcome has a conclusions row | Partly | Missing: counter mismatch rows, S0 failing, missing disallow evidence, bands missed with the right shape, controls failing, "no row". Added (U4, C7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | Disallow evidence only the NoSpamLogger line (≤ 1 per minute); added `NTCREFUSE` lines per refused channel (C5) and named the Confirmed rows' full conditions (U4, C7). |
| B. Logic | alternative explanations and their controls | Partly | S = 0 and positive controls fine; the no-flag control rests on a premise the source contradicts; not run, with reason (C8). |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 gives the chain to `:89`/`:93`/`:97`, B1 the claim. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | `/local`, Linux and `ss` paths (U1, C1, C3); output location of test stdout (U2). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Unit print points and run order; cluster run order on the L = -1 node, stop conditions, stop method (U2, C6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, Python 3, Byteman jar from the build; no extra loopback address needed. |
| D. Runnable | workload arithmetic reaches the limit | Met | 300 × 4 MiB = 1,200 MiB direct at L = -1, under the node's default `MaxDirectMemorySize` (8 GiB here); 64 × ~1 MiB in the test JVM. ~10 min for the cluster tier. |
| D. Runnable | load-bearing citations spot-checked | Met | Clone at `b5f2a54210`: `ConnectionLimitHandler.java:54, 86-97, 129, 136`; `PipelineConfigurator.java:73, 138, 157-163, 240-245, 264-265`; `Envelope.java:197, 429, 441`; `InitialConnectionHandler.java:52, 111` (cited as 107-108: off by a few lines, harmless); `CBUtil.java:59-60`; `Config.java:285, 289-290`; `DatabaseDescriptor.java:3163-3171`; Netty `AbstractByteBufAllocator.ioBuffer`/`calculateNewCapacity`, `ByteToMessageDecoder$1.cumulate` (`javap -c`, 4.1.130). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | B2a: this host's clone `$W/cassandra-run53`, harness test path and script | applied 2026-10-27 (uncommitted, in hash `8f7f5202…`) | `/local` does not exist here |
| U2 | B2e: exact run order (L-1, L0, L8, L32, S0), buffer allocation, read points, one PROBE line per run, stdout location | applied | step order and collection were open |
| U3 | B2f: L = -1 `counter` is n/a (reads 0), not 64; S0 row; capacity = 9 + S | applied | source error in the table (handler gate `PipelineConfigurator.java:240-245`), not a reading |
| U4 | B2g: counter rows, S0 row, catch-all; name Confirmed/Refuted rows | applied | every outcome needs a row |
| C1 | B3a: macOS paths, node start, Byteman agent, `ulimit` | applied | host differs from the design's Linux node |
| C2 | B3c: `hold.py` verbatim in the harness; SIGTERM by PID | applied | path only |
| C3 | B3d: `netstat` instead of `ss` | applied | no `ss` on macOS |
| C4 | B3d: held bytes from `CBUtil.allocator.metric()`; heap as context; `GC.heap_info` dropped | applied | the cumulation is direct by source; heap tools cannot see it |
| C5 | B3d: `NTCREFUSE` line per refused channel | applied | direct disallow evidence beyond one NoSpamLogger line per minute |
| C6 | B3e: exact procedure and run order | applied | controls' placement, stop conditions open |
| C7 | B3g: full Confirmed conditions; control bands; added rows | applied | every outcome needs a row |
| C8 | B3h: no-flag control not run (premise contradicted by source) | applied | the flag does not move the cumulation to heap |
| C9 | B4: clean-up checks on this host | applied | paths |
| R1 | Stage 3: when a design reads Netty-held bytes, check where the allocator puts them (`ioBuffer()` is direct whenever Unsafe is available) | left for stage 3 | design-level lesson |
| R2 | Stage 3: re-check prediction tables against the install gate of the handler (both limits ≤ 0 → no handler, no counter) | left for stage 3 | the L = -1 counter cell |

**Agreement criteria** — not filled (no run 2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 05:19:11–05:19:27; cluster 05:19:35–05:28:52, EDT) |
| Node | `yangwang-mbp`, Apple T6000 (arm64), 10 cores, 32 GiB RAM, single host |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Python | 3.8.11 |
| Local `cassandra-src` clone commit | `$W/cassandra-run53`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (`cassandra-5.0.9`); `ant -Dlocal.repository=$W/m2 build-test` BUILD SUCCESSFUL in 50 s |
| Case-file commit / harness commit | case file frozen at sha256 `8f7f5202…8153` on `advisor-run` (uncommitted; parent `419619f`); harness uncommitted |
| Storage for node data | internal SSD, APFS; node files `$W/node-ntc` (fresh per node, removed at the end) |
| Loopback / ports | only 127.0.0.1 used; 7000, 7199, 9042, 9091 free before each run (checked by the script); `ulimit -n` 1,048,576 |
| Full logs (outside the repo) | `$W/logs/native_transport_max_concurrent_connections-channelActive-limit/` (`clone-build.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-r1/`); `W=~/Library/Caches/stage4` |

Machine facts relied on (from earlier runs on this host, given in the session prompt): workspace and proxy set-up in `$W/env.sh`; no `setsid` (node started as a tracked background process); `jstat` cannot attach and `GC.heap_info` failed a known-answer check (class-histogram totals used instead, as context only); Netty `ioBuffer()` returns direct buffers whenever Unsafe is available, so native-transport bytes are read from `CBUtil.allocator.metric()` (re-derived from the jar here, C4); `EmbeddedChannel` closes a refused channel before `register()` returns (U2 note); test stdout lands in `build/test/logs/**/TEST-<class>.log`; a `-D` reaches the forked test JVM only via `-Dtest.jvm.args` (used for the shakedown's small N, S); bash 3.2 (EXIT trap guarded to the main shell); avoid the literal daemon class name in pkill patterns; shakedown before run 1 and `selfcheck.py` written and run end to end on it before readings.

## 3. Runbook defects

None. Both tiers ran as written in the frozen version.

Shakedown notes (not defects of the case file): the unit shakedown (N = 16, S = 1,024) and the cluster shakedown (N = 30, NC = 10, S = 1,048,566, L ∈ {-1, 20, 5}, WARM 5 s, SETTLE 3 s) ran through. The cluster shakedown's S was chosen one byte short of a power of two (9 + S = 1,048,575), which exposed a bug in the first draft of `selfcheck.py` (it asserted 9 + S is a power of two); fixed to the C4 rule (smallest power of two ≥ 9 + S), then the self-check ran end to end on the shakedown output with exit 0, 34/34 PASS (`run1/selfcheck-shakedown.out`). Neither changes the case file.

## 4. Run 1

**Scope:** unit tier (all five runs) and cluster tier (three nodes, five runs). **Command logs:** `native_transport_max_concurrent_connections-channelActive-limit--autonomous/run1/unit-r1/commands.log`, `run1/cluster-r1/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit-r1/probe.txt`; JUnit `Tests run: 1, Failures: 0, Errors: 0` in `run1/unit-r1/ant-excerpt.txt`)

| Run | L | open (pred.) | counter (pred.) | held B (pred.) | capacity B | closeCounter | Evidence |
|---|---|---|---|---|---|---|---|
| L-1 | -1 | 64 (64) | 0 (n/a, 0) | 67,109,440 (67,109,440) | 67,109,440 | 0 | `run1/unit-r1/probe.txt` |
| L0 | 0 | 64 (64) | 0 (n/a, 0) | 67,109,440 (67,109,440) | 67,109,440 | 0 | same |
| L8 | 8 | 8 (8) | 8 (8) | 8,388,680 (8,388,680) | 8,388,680 | 0 | same |
| L32 | 32 | 32 (32) | 32 (32) | 33,554,720 (33,554,720) | 33,554,720 | 0 | same |
| S0 | 8 | 8 (8) | 8 (8) | 0 (0) | 0 | 0 | same |

Init line: `maxFrame=16777216 idleTimeout=0 perIp=-1 counter=0`.

**Cluster tier** (ΔH = allocator `direct + heap`, reading − baseline; MiB = 2^20 B)

| L | Run | held: script / netstat at reading (pred.) | ΔH (band) | log lines (node) | `NTCREFUSE` (N − L) | counter at reading | after kill: netstat / ΔH vs baseline | heap context Δ`[B` / ΔTotal | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| -1 | main, N = 300 | 300 / 300 (300) | 1,258,291,200 B = 1,200.0 MiB ([1,150, 1,450]) | 0 (0) | 0 (0) | 0 (no handler) | 0 / 0 | +0.04 / +0.67 MiB | `run1/cluster-r1/lm1-main/` |
| -1 | positive control, N = 100 | 100 / 100 (100) | 419,430,400 B = 400.0 MiB ([383, 484]) | 0 | 0 | 0 | 0 / 0 | +0.01 / +0.19 MiB | `run1/cluster-r1/lm1-n100/` |
| -1 | s0 control, N = 300, nothing sent | 300 / 300 (300) | 0 B (< 30 MiB) | 0 | 0 | 0 | 0 / 0 | +0.02 / +0.50 MiB | `run1/cluster-r1/lm1-s0/` |
| 200 | main, N = 300 | 200 / 200 (200) | 838,860,800 B = 800.0 MiB ([760, 980]) | 1 (≥ 1) | 100 (100) | 200 | 0 / 0 | +0.06 / +0.61 MiB | `run1/cluster-r1/l200-main/` |
| 50 | main, N = 300 | 50 / 50 (50) | 209,715,200 B = 200.0 MiB ([180, 260]) | 1 (≥ 1) | 250 (250) | 50 | 0 / 0 | +0.05 / +0.32 MiB | `run1/cluster-r1/l50-main/` |

Ratios ΔH(L)/ΔH(-1): L = 200: 0.6667 (want 0.6667 ± 0.05); L = 50: 0.1667 (want 0.1667 ± 0.05). Every `NTCREFUSE` line at L = 200 reads `counter=201 limit=200`, and at L = 50 `counter=51 limit=50` (`run1/cluster-r1/l*-main/ntcrefuse.txt`). The log line reads "Exceeded maximum native connection limit of 50 by using 51 connections" (`run1/cluster-r1/l50-main/limit-log-lines.txt`). Each node logged its L, `native_transport_max_concurrent_connections_per_ip=-1` and `native_transport_idle_timeout=0ms` (`run1/cluster-r1/*-config.txt`); `NTCMEM` shows `allocator=UnpooledByteBufAllocator heapAllocatorFlag=true` (`alloc-*.txt`).

### 4.2 Conclusion and logic

1. **Validity.** Unit: per-IP -1, max frame 16 MiB > 16,000,009 declared, idle timeout 0 [observed: `run1/unit-r1/probe.txt` init line]; N = 64 exceeds L ∈ {8, 32} [observed: same]. Cluster: each node ran with its L, per-IP -1, idle 0 [observed: `run1/cluster-r1/*-config.txt`]; the heap-allocator flag applied, so the metric covers every native-transport buffer [observed: `alloc-*.txt`]; N = 300 exceeds L ∈ {200, 50}, and the refusal branch fired [observed: `ntcrefuse.txt`, `limit-log-lines.txt`]; no `held=` stop condition [observed: `run1/cluster-r1/commands.log`]. The run is valid.
2. **Readings.** No gap or outlier. ΔH equals held × 4,194,304 B exactly at every L and in the positive control [observed: `alloc-*.txt`]; baselines and post-kill readings are 0 B [observed: same]. The heap context moved by < 1 MiB in every run while ΔH moved by up to 1,200 MiB [observed: `histo-*-excerpt.txt`], as C4 derived. The `counter` stays 0 on the L = -1 node [observed: `run1/cluster-r1/lm1-*/alloc-read.txt`], as U3's gate implies for the cluster too.
3. **Matched rows.** Unit, B2g row 1: "open = min(64, L) for L > 0, 64 for L ∈ {-1, 0}; held = open × (S + 9)" — open 64/64/8/32, held 67,109,440/67,109,440/8,388,680/33,554,720 = open × 1,048,585; plus U4's conditions: counter = open at L ∈ {8, 32}, 0 at L ∈ {-1, 0}, closeCounter 0 everywhere, S0 held 0 [observed: `run1/unit-r1/probe.txt`]. Cluster, B3g row 1: "held = min(300, L) and ΔH ≈ held × 4 MiB at each L" with C7's conditions — held 300/200/50 by script and netstat; ΔH 1,200/800/200 MiB inside the bands; log lines 0/1/1; ratios 0.6667 and 0.1667; return to 0 B; n100 400 MiB in [383, 484]; s0 0 MiB < 30 [observed: files in §4.1].
4. **Excluded rows.** Unit: row 2 (open > L) — open 8 and 32 at L 8 and 32; row 3 (refused channels hold bytes) — held = open × (S + 9) exactly, so refused channels hold 0; row 4 (held ≪ S) — 1,048,585 per open channel; row 5 (L = 0 refuses) — 64 open at L = 0; row 6 (counter not back to 0) — closeCounter 0; U4 rows — counter 0 at L ∈ {-1, 0}, counter = open, S0 held 0 [observed: `run1/unit-r1/probe.txt`]. Cluster: row 2 (ΔH the same at every L, Refuted) — 1,200 vs 800 vs 200 MiB; row 3 (held > L, Refuted) — 200 and 50; row 4 (positive control did not move) — 4 MiB per held connection; row 5 (no return) — 0 B after kill; C7 rows — log and `NTCREFUSE` lines present, bands and ratios met, s0 0 MiB, n100 in band [observed: §4.1 files].
5. **Observed vs. inferred.** (a) That the allocator metric counts the decoder's cumulation and nothing else of note in the window [inferred: C4's source derivation; supported by ΔH = held × 4 MiB exactly, s0 = 0 and post = 0]. (b) That refused channels never allocate a cumulation [inferred: the head handler reads only after `channelActive` propagates, which the limit handler stops; supported by ΔH exact at L ∈ {200, 50} and `NTCREFUSE` = N − L]. (c) That the netstat count is the node's side only [inferred: local address `127.0.0.1.9042` filter; equal to the script's count every time].
6. **Deviations and gaps.** Only the amendments made before the freeze. Process RSS and kernel socket memory were not measured (B2d/B3d gaps, named in the design). The no-flag control was not run (C8). The pooled default allocator (production default, flag off) was not measured: the cap acts on the count, which does not depend on the allocator, but bytes under the pooled allocator are not shown here.
7. **Core question.** B1's hypothesis: the node keeps min(N, L) connections and their decoder-held bytes scale as min(N, L) × S. The unit tier shows the count capped at L with the refusal closing the channel and the held bytes exactly open × (S + 9) (parts 3–4); the cluster tier shows the same on a real node, with the native-transport memory 1,200 → 800 → 200 MiB as L goes -1 → 200 → 50 and the refusal branch firing N − L times (parts 1, 3). So usage follows the constraint and the constraint caps it (count × per-connection bytes).

**Conclusion (one line):** unit B2g row 1 — confirmed; cluster B3g row 1 — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` (written before any frozen-value reading, run end to end on the shakedown first: exit 0, 34/34 PASS, `run1/selfcheck-shakedown.out`) re-reads the raw files in `$W/logs/.../unit-r1` and `cluster-r1` (TEST log, ant log, netstat dumps recounted, `NTCMEM` lines, class histograms, node system logs, `NTCREFUSE` lines), recomputes every observable, checks B2f/B3f as amended and checks that `commands.log` says the same. Run-1 result: **exit 0, 34 checks, 34 PASS, 0 FAIL, 0 parse errors; unit row B2g row 1, cluster row B3g row 1** (`run1/selfcheck.out`).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit-r1/probe.txt` init line; `cluster-r1/*-config.txt`; `alloc-read.txt` flag; selfcheck "hold-fixed" PASS ×3 |
| 2. Readings | yes | re-read `alloc-base/read/post.txt` per run and `histo-*` totals; selfcheck recomputed ΔH and heap deltas |
| 3. Matched row | yes | selfcheck unit runs PASS ×5 with literal B2f numbers asserted; cluster held/band/return/log PASS ×4 runs, ratios ×2, s0 control |
| 4. Excluded rows | yes | each Refuted row contradicted by a recounted value (held ≤ L; ΔH differs across L); `ntcrefuse.txt` counts 100 and 250 |
| 5. Observed vs. inferred | yes | (a) s0 = 0 B, post = 0 B, ΔH exact multiples; (b) ΔH at L ∈ {200, 50} exact with N − L refusals; (c) netstat recount = script count in all runs |
| 6. Deviations and gaps | yes | no runbook defect; gaps as listed |
| 7. Core question | yes | the steps follow B1 → B2g/B3g row 1 |

### 5.2 Run 2?

**No** — 2026-10-27. The readings are exact (counts equal to the predictions, bytes equal to held × 4 MiB to the byte), the inferred statements are each backed by a control, and the result confirms the case without a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** With N > L clients each holding a partly sent envelope of S bytes on the native port, the node keeps exactly min(N, L) of those connections open; the bytes held for them in the decoders grow as min(N, L) × S, about S per kept connection; with L = -1 (or 0) all N are kept and the held bytes are N × S (B1). "Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (open = min(64, L), 64 at L ∈ {-1, 0}; held = open × 1,048,585 exactly; counter = open, 0 when no handler; S0 held 0) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** — B3g row 1 (held 300/200/50; ΔH 1,200/800/200 MiB of native-transport direct memory; refusals N − L; return to baseline; controls 400 MiB and 0 MiB) | caps | run 1 + self-check | 2026-10-27 |

**Effect:** caps — the count of live native connections is capped at L, and the decoder-held memory follows min(N, L) × 4 MiB.

**Feedback filed:** the case file's section D updated (after the frozen hash); `_INDEX.md` §1 Stage 4 column filled. Not committed (no commit asked).
