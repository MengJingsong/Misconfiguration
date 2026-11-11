# native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous — stage-4 results  <!-- file: results/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous.md -->

> **Case:** [`native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous`](../../stage3-ai-deep-read/cases/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous/`](../harness/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster) as amended; "§9b–§9e" means B2a–B2e / B3a–B3e;
> the feedback section is the case file's section D.
>
> **Session:** Claude Opus 5.5 (`claude-opus-5-5`), Claude Code CLI, 2026-10-27, on the advisor's Mac (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | filed in commit `339e0b1`; the 12 audit amendments of 2026-10-27 (U1–U4, C1–C8) are uncommitted in the working tree at the time of the run. Frozen sha256 after the amendments: `d59f24607d61abd3ca25e225563948246fc1d007d7e95f739107b98f13ddfd13` (new row in `_INDEX.md` §4). Both tiers of run 1 ran at this version; section D was filled after this hash. |
| **Harness** | `harness/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous/`: `ConnLimitProbeTest.java`, `unit-run.sh`, `hold_frames.py` (the case's B3c script, verbatim), `Jmx.java`, `cluster-run.sh` (uncommitted; the node start/stop and logging skeleton of `cluster-run.sh` and the structure of `unit-run.sh` are adapted from the harness folders of `native_transport_max_concurrent_connections-channelActive-limit--autonomous` and `native_transport_max_frame_size-decode-bytesToDiscard--autonomous`; no value or derivation was taken from them) |
| **Tiers and values** | unit: limits -1 (default), 0, 5, 20 with M = 10 channels. cluster: limits -1 (default, run A), 16 (run B), 32 (run C, added by C1), K = 64 connections, each holding exactly 4 MiB (L = 4194296, C2); informational run R (C7) |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: memory held by open native connections (count × footprint); cluster measures NMT `Other` (direct memory). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met | Unit B2b has -1, 0, 5, 20. Cluster B3b had only -1 and 16; C1 adds 32. |
| A. Core question | real resource measured, not only the counter | Partly → Met | Unit measures only channel state and `counter` (memory is the cluster tier's job; U4 says so). Cluster B3d measures NMT `Other`, but the default pooled allocator would hide per-connection bytes behind 16 MiB chunks per event-loop arena (C1). |
| A. Core question | usage driven to the limit and past it | Met | Unit: 10 channels against 5. Cluster: K = 64 against 16 and 32. |
| B. Logic | each step says what it establishes | Partly → Met | B3e steps did not say which reading is which; C4 defines E/O/P/F/G. |
| B. Logic | prediction stated in numbers | Partly → Met | B2f had exact counts. B3f bands assumed 4 MiB per connection, but with L = 4194304 Netty's cumulation growth makes 8 MiB (C2). C5 gives exact counts and the run C band. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met | B2g/B3g had no invalid row, no "limit not reached" row and no no-row-fits row; U4 and C6 add them with verdicts. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | C6 row R needs E ≤ limit, O in band, O_B < O_C < O_A, a log line and send failures. |
| B. Logic | alternative explanations and their controls | Met | Run A is the positive control; release (P) ties memory to connections; -1/0/20 are the unit controls. |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 and B1 are clear. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | Unit: `runPendingTasks()`, where to read handler presence, and the output format were missing (U2). Cluster: Linux-only commands (C1, C3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | C4 fixes the order, timings, stop condition and readings. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met | No `/local`, `ss`, `/proc`, `setsid` on this host (C1, C3, C8). |
| D. Runnable | workload arithmetic reaches the limit | Met | 64 × 4 MiB = 256 MiB direct against a 2 GiB direct cap and 32 GiB RAM; 120 GiB disk free. |
| D. Runnable | load-bearing citations spot-checked | Partly → Met | `PipelineConfigurator.java:73, 136, 240-245`, `Config.java:289-290`, `DatabaseDescriptor.java:3163-3171`, `StorageProxy.java:2851-2852` hold; `ConnectionLimitHandler` line numbers are off by 2-3 (U3 corrects them). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | Use this host's clone `$W/cassandra-run55`, harness paths, `-Dlocal.repository` | applied 2026-10-27 (uncommitted) | no `/local` here |
| U2 | Exact unit procedure: `register()` then `runPendingTasks()`; handler presence read inside `initChannel` (a refused channel's pipeline is emptied on close); CH/PROBE/CLOSED/READBACK lines | applied | runnable without re-deriving; the handler-presence clause was added while writing the harness, before any run, and is in the frozen hash |
| U3 | Exact unit predictions; corrected line citations | applied | prediction in numbers |
| U4 | B2g rows with verdicts (I, R1, R2, C, N1, N2) | applied | every outcome has a row |
| C1 | macOS node set-up; **third value 32**; **every node with `-Dcassandra.netty_use_heap_allocator=true`** | applied | ≥ 3 values; with the pooled allocator (`CBUtil.java:59-60`, `maxOrder=11` → 16 MiB chunks, 20 event loops/arenas) 16 held connections could commit up to 256 MiB and run B could not be told from run A |
| C2 | `hold_frames.py` verbatim; **L = 4194296** instead of 4194304 | applied | 9 + L − 1 = 4194312 bytes would grow the merge cumulation to 8 MiB (Netty 4.1.130 `calculateNewCapacity`: powers of two up to 4 MiB, then 4 MiB steps); with 4194296 each connection holds exactly 4 MiB, as B3c's arithmetic assumes |
| C3 | `netstat` instead of `ss`, `ps` RSS instead of `/proc`, NMT `Other` committed delta | applied | this host |
| C4 | exact procedure and readings E/O/P/F/G; shakedown first | applied | exact sampling and stop conditions |
| C5 | exact counts; run C prediction (E = 32, F = 32, O in [115, 256] MiB); release P ≤ 0.1 × O | applied | prediction in numbers |
| C6 | B3g rows with verdicts (I, R, W1, W2, N1, N2, N3) | applied | every outcome has a row |
| C7 | optional runtime check as informational run R (prediction 36 established, 4 refused) | applied | the B3h option, run with no row |
| C8 | macOS clean-up | applied | this host |
| S1 | For stage 3: a unit tier could also measure the cumulation bytes per channel (feed an incomplete frame), which would let the unit tier speak about memory | left for stage 3 | not needed for a valid run |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 06:35; cluster 06:35–06:50 local time; node logs in UTC) |
| Node | `yangwang-mbp`, the advisor's laptop, single host (Apple M1 Pro, 10 cores, 32 GiB) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Python | 3.8.11 (system `python3`, for `hold_frames.py`) |
| Local clone commit | `$W/cassandra-run55` (`W=~/Library/Caches/stage4`), fresh clone of `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` succeeded in 51 s; `git status` clean after the run |
| Case-file commit / harness commit | `339e0b1` + uncommitted amendments (sha256 `d59f2460…`) / harness uncommitted |
| Storage for node data | internal SSD, APFS, 120 GiB free; node files `$W/node-ntcc`, fresh per node, removed at the end |
| Loopback | 127.0.0.1–.3 on `lo0` (only .1 used) |
| Full logs | `$W/logs/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous/` (`clone.log`, `build-test.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-r1/`) |

Machine facts relied on (from earlier runs on this Mac): no `mkdir` in `$HOME` outside `$W`; commands touching `$W`/Java run unsandboxed; no `setsid` (node started as a tracked background `bin/cassandra -f`); `-Dlocal.repository=$W/m2` on every `ant` call; `cassandra-env.sh` sets `-XX:MaxDirectMemorySize=8192M` and the later `JVM_EXTRA_OPTS` flag `2G` wins (both are on the command line, `cluster-r1/A-jvmflags.txt`); Netty `ioBuffer()` is direct whenever Unsafe is available; pooled arenas commit 16 MiB chunks (hence the heap-allocator flag); `bash` 3.2 EXIT trap guarded to the main shell; node `system.log` timestamps are UTC; daemon class name kept out of `pkill` patterns; long steps in the background; shakedown before run 1; `selfcheck.py` written before run 1 and run end to end on the shakedown output (exit 0).

## 3. Runbook defects

None. Both shakedowns (unit with values -1, 3 and M = 4; cluster with K = 6, 1 MiB held per connection, limits -1 and 2, run R with 3 + 3) ran as written and are not readings (`run1/shake/`). The cluster shakedown was also the instrument's known-answer check: 6 held 1 MiB connections gave `Other` +6147 KB, 2 gave +2051 KB (`run1/shake/cluster-shake-commands.log`).

## 4. Run 1

**Scope:** unit tier, all four values; cluster tier, runs A, B, C and the informational run R. **Command logs:** `run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/probe.txt`, from `run1/unit/TEST.log`; JUnit `Tests run: 1, Failures: 0, Errors: 0`)

| Value | Open channels | Handler present (of 10) | `counter` after 10 channels | `counter` after closing all | Evidence |
|---|---|---|---|---|---|
| -1 | 1–10 (10) | 0 | 0 | 0 | `PROBE,-1,10,0,0`, `CLOSED,-1,0` |
| 0 | 1–10 (10) | 0 | 0 | 0 | `PROBE,0,10,0,0`, `CLOSED,0,0` |
| 5 | 1–5 (5); 6–10 closed | 10 | 5 (rises 1..5, stays 5 for 6–10) | 0 | `PROBE,5,5,5,10`, `CLOSED,5,0` |
| 20 | 1–10 (10) | 10 | 10 | 0 | `PROBE,20,10,10,10`, `CLOSED,20,0` |

Every `READBACK` line echoes the value and per-IP -1.

**Cluster tier** (`run1/cluster/<run>/`; K = 64, L = 4194296, hold 120 s; samples at t0 + 20/40/60 s)

| Limit | Run | E (established, 3 samples) | O = `Other` committed Δ (3 samples) | P (Δ 15 s after exit) | F (`send_failed`) | G (log lines) | RSS Δ at s1 (context) |
|---|---|---|---|---|---|---|---|
| -1 | A | 64, 64, 64 | 262144 KB = 256.0 MiB (all three) | 0 KB | 0 | 0 | +259 MiB |
| 16 | B | 16, 16, 16 | 65536 KB = 64.0 MiB (all three) | 0 KB | 48 | 1: `…limit of 16 by using 17 connections…` | +34 MiB |
| 32 | C | 32, 32, 32 | 131072 KB = 128.0 MiB (all three) | 0 KB | 32 | 1: `…limit of 32 by using 33 connections…` | +68 MiB |

Every run: baseline and post established 0; node config line shows the limit, per-IP -1, `native_transport_idle_timeout=0ms`, `native_transport_max_frame_size=16MiB` (`run1/cluster/<run>-config.txt`); JVM flags include NMT summary, `-XX:MaxDirectMemorySize=2G` (last) and `-Dcassandra.netty_use_heap_allocator=true` (`<run>-jvmflags.txt`).

**Run R (informational, C7):** the first script held 20 connections (`send_failed 0`, 20 established); JMX `GET -1`, `SET 16`, `GET 16`; the second script `attempted 20 send_failed 4`; established 36, 36, 36; one log line `…limit of 16 by using 17 connections…` (`run1/cluster/R/`, `R-limit-log-lines.txt`). Exactly as predicted from source: 20 uncounted pre-existing channels + 16 counted.

### 4.2 Conclusion and logic

1. **Validity.** Unit: all four values ran, every `READBACK` matches [observed: `run1/unit/probe.txt`]; the handler fired on channel activation (the counter rises with each channel at 5 and 20) [observed: `probe.txt` CH lines]. Cluster: run A held all 64 (`send_failed 0`, E = 64) and each capped run reached its limit (E_B = 16, E_C = 32) [observed: `run1/cluster/{A,B,C}/hold.out`, `netstat-s*-9042.txt`]; every hold-fixed setting is confirmed in `<run>-config.txt` and `<run>-jvmflags.txt`; no STOP CONDITION line in `commands.log` [observed]. Valid.
2. **Readings.** Nothing unusual in the rows. RSS (context only, no row uses it) rose by 259 MiB in A but only 34 and 68 MiB in B and C and did not fall after release [observed: `commands.log`]; macOS RSS is not a byte-exact measure of freed or reused malloc memory [inferred: macOS memory accounting; RSS was named context-only in C3 before the run], so it is not used.
3. **Matched row.** Unit: **C (Confirmed — caps the connection count)**: -1 and 0 → 10 open, no handler, counter 0; 5 → exactly channels 1–5 open, counter 5; 20 → 10 open, counter 10; counter 0 after every close [observed: `probe.txt`]. Cluster: **R (Confirmed — caps)**: E_B = 16 ≤ 16 and E_C = 32 ≤ 32; O_A = 256.0 in [230, 520], O_B = 64.0 in [55, 130], O_C = 128.0 in [115, 256] MiB and 64 < 128 < 256; G_B = G_C = 1, F_B = 48, F_C = 32 (disallow branch fired); P = 0 ≤ 0.1 × O in every run [observed: `run1/cluster/*`].
4. **Excluded rows.** Unit: I excluded (counter moves at 5 and 20); R1 excluded (5 open at limit 5); R2 excluded (no handler at -1 or 0); N1 excluded (all `CLOSED` counters 0). Cluster: I excluded (F_A = 0, E_A = 64, E_B = 16, E_C = 32, every `attempted` line printed before t0 + 20 s); W1 excluded (E_B = 16, E_C = 32, not above the limit); W2 excluded (O_B = 64 ≤ 130, O_C = 128 ≤ 256); N1 excluded (O_A = 256 ≥ 230); N2 excluded (release holds); N3 not needed [observed: as in part 3].
5. **Observed vs. inferred.** The conclusion depends on two inferred statements: (a) NMT `Other` sees the decoder's held bytes (the cumulations are unpooled direct buffers allocated through Unsafe) — supported by the shakedown's known answer (6 × 1 MiB → +6147 KB) and by run A's exact 256 MiB = 64 × 4 MiB [inferred from source, checked by the readings]; (b) the refused connections never allocated a cumulation — supported by P and O being exact multiples of the held connections and by the source (`ctx.close()` before `fireChannelActive`, `ConnectionLimitHandler.java:93-98`) [inferred].
6. **Deviations and gaps.** All nodes ran with the heap-allocator flag (C1), so the default pooled-allocator configuration was not measured; under it the bytes committed per held connection would be quantised to 16 MiB chunks per event-loop arena, which C1 derived from source but did not run. The unit tier measures the connection count only. Run R is informational.
7. **Core question.** Usage followed the constraint: with the same 64-connection workload, held direct memory was 256 MiB unlimited, 128 MiB at 32 and 64 MiB at 16, that is exactly min(attempted, N) × 4 MiB (parts 3, 1), with the disallow branch observed (log lines and refused sends, part 3) and the memory released when the connections closed (part 3). So the constraint caps the memory held by connections by capping their count, for a limit set before the connections are opened; a limit raised from -1 at run time does not count connections opened before it (run R, 36 > 16).

**Conclusion (one line):** unit row C — confirmed; cluster row R — confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1; run end to end on both shakedowns with exit 0, `run1/shake/selfcheck-*-shake.out`) re-reads the raw files (`run1/unit/probe.txt` and `TEST.log`; the full cluster log directory `$W/logs/<stem>/cluster-r1/`: raw `netstat`, NMT diffs, `hold*.out`, `system.log`, config and flag files), recomputes every reading, cross-checks them against the harness's `commands.log`, and evaluates the U4 and C6 rows. Output `run1/selfcheck.out`: **62/62 checks hold, exit 0**, unit row C, cluster row R (equal to the conclusion's rows).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `A/hold.out` `attempted 64 send_failed 0`; `netstat-s*` give 64/16/32; config and flag files checked by the script |
| 2. Readings | yes | three equal samples per run; post 0 KB in all runs (`nmt-post.txt`) |
| 3. Matched row | yes | recomputed bands and counts; log lines name limit 16/32 and count 17/33 |
| 4. Excluded rows | yes | each excluded by the recomputed values |
| 5. Observed vs. inferred | yes | shakedown known answer (+6147 KB for 6 MiB) re-read in `shake/cluster-shake-commands.log`; A's `Other` +262144 KB = 64 × 4096 KB exactly |
| 6. Deviations and gaps | yes | the flag is on every node's command line (`*-jvmflags.txt`) |
| 7. Core question | yes | readings → rows R and C by the amended rows, which follow B1 |

### 5.2 Run 2?

**No** (2026-10-27): every reading is an exact source-derived count or byte total, the self-check holds in full, and the result neither refutes the case nor confirms a bypass row.

## 6. Run 2 — not done

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** with `native_transport_max_concurrent_connections = N > 0`, at most N client connections stay open, and memory held by connections that each keep an incomplete frame scales with min(attempted, N); with -1 it scales with the number attempted.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (U4 row C): -1/0 install no handler; 5 keeps exactly 5 of 10 channels; counter returns to 0 | caps (the connection count; no memory measured at this tier) | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed (C6 row R): 64/16/32 established; NMT `Other` +256.0/+64.0/+128.0 MiB = min(64, N) × 4 MiB; refusals logged; released to 0 | caps | run 1 + self-check | 2026-10-27 |

Informational (run R, no row): raising the limit from -1 to 16 at run time left 36 connections open (20 uncounted + 16), as A3's runtime-enabling note predicts.

**Feedback filed:** the case file's section D (uncommitted); amendments U1–U4 and C1–C8 in the case file; `_INDEX.md` §4 new row and §1 Stage 4 column.
