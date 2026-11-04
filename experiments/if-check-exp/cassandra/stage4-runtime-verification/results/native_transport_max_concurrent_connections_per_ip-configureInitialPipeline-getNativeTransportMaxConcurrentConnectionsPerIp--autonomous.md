# native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous — stage-4 results  <!-- file: results/native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous.md -->

> **Case:** [`native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous`](../../stage3-ai-deep-read/cases/native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous/`](../harness/native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster) as amended; "§9b–§9e" means B2a–B2e / B3a–B3e;
> the feedback section is the case file's section D.
>
> **Session:** Claude Opus 5.5 (`claude-opus-5-5`), Claude Code CLI, 2026-10-27, on the advisor's Mac (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | filed in commit `339e0b1` (sha256 `7c82fcb1…` as filed); the 12 audit amendments of 2026-10-27 (U1–U4, C1–C8) are uncommitted in the working tree at the time of the run. Frozen sha256 after the amendments: `ba3b32eb87542965adcaa4e02ddbab2d5d53068ab57b519ea2defaa806ca76a9` (new row in `_INDEX.md` §4). Both tiers of run 1 ran at this version; section D was filled after this hash. |
| **Harness** | `harness/native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous/`: `PerIpLimitProbeTest.java`, `unit-run.sh`, `hold_frames.py` (the case's B3c script plus C2's optional source address), `cluster-run.sh` (uncommitted). `unit-run.sh` is adapted from the harness folder of `native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous` (sed of names and clone), and the node start/stop and logging skeleton of `cluster-run.sh` from the same folder; the sampling, the per-address counting and the two-script schedule are new. Every value and derivation here was made from the pinned source and the Netty 4.1.130 bytecode; none was taken from another case or results file. |
| **Tiers and values** | unit: per-IP limits -1 (default), 0, 3, 5 with 8 channels (6 from 10.0.0.1, 2 from 10.0.0.2). cluster: per-IP limits -1 (default, run A), 16 (run B), 32 (run C, added by C1); K1 = 64 connections from 127.0.0.1 then K2 = 16 from 127.0.0.2, each holding exactly 4 MiB (L = 4194296, C2) |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: the memory pinned by one source IP's open native connections (count × per-connection cumulation); the cluster tier measures NMT `Other` (direct memory). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met | B2b had -1 and 3 (U2 adds 0 and 5); B3b had -1 and 16 (C1 adds 32). |
| A. Core question | real resource measured, not only the counter | Partly → Met | Unit reads only channel state and the per-IP map (the gap is named in U4: memory is the cluster tier's). Cluster B3d measures NMT `Other`, but with the default pooled allocator 16 capped connections could commit 16 MiB arena chunks each and look like run A (C1 (3)). |
| A. Core question | usage driven to the limit and past it | Met | Unit: 6 channels from one address against 3 and 5. Cluster: 64 against 16 and 32. |
| B. Logic | each step says what it establishes | Partly → Met | B3e did not name the readings per step or the sample times; C4 defines E1, E1', E2, O1, O2, D, P, F1, F2, G, Gg. |
| B. Logic | prediction stated in numbers | Partly → Met | B2f exact counts but not per channel (U3). B3f bands assumed 4 MiB per connection; with the filed L = 4194304 Netty's growth makes 8 MiB (C2). C5 gives exact counts, run C and D's band. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met | B2g/B3g had no verdict wording, no "limit not reached" row, no "count capped but memory grows" row, no no-row-fits row; U4 and C6 add them. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | C6 row R requires E1 = limit at two values, O1 in band and ordered B < C < A, and G ≥ 1 per-IP log line in each capped run. |
| B. Logic | alternative explanations and their controls | Met | Run A is the positive control; the second IP checks per-address scope; the post sample ties memory to connections; -1/0 are the unit controls. |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 and B1 are clear. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | Unit: `runPendingTasks()`, where to read handler presence and the output format were missing (U2). Cluster: Linux-only commands and a LAN-exposed second IP (C1–C3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | C4 fixes order, timings (s1–s3 at t0+20/25/30, script 2 at t0+35, s4–s6 at t0+55/60/65, post 15 s after exit) and stop conditions. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met | No `/local`, `ss`, `/proc`, `setsid` here; second IP via loopback alias 127.0.0.2 (present on `lo0`). |
| D. Runnable | workload arithmetic reaches the limit | Met | Peak 80 × 4 MiB = 320 MiB direct, against a 2 GiB direct cap, 32 GiB RAM and 120 GiB free disk. |
| D. Runnable | load-bearing citations spot-checked | Partly → Met | `PipelineConfigurator.java:73, 138, 240-245`, `Config.java:290`, `DatabaseDescriptor.java:3173-3181`, `StorageProxy.java:2854-2855`, `StorageProxyMBean.java:59-60`, `conf/cassandra.yaml:1050-1052`, `Envelope.java:429, 441` hold; `ConnectionLimitHandler` line numbers are about 2 high (U3 corrects them). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | This host's clone `$W/cassandra-run56`, harness paths, `-Dlocal.repository` | applied 2026-10-27 (uncommitted) | no `/local` here |
| U2 | Values -1, 0, 3, 5; exact procedure (`register()` + `runPendingTasks()`, handler presence read in `initChannel`, map by reflection); READBACK/CH/PROBE/CLOSED/END lines | applied | ≥ 3 values; runnable without re-deriving |
| U3 | Exact per-channel predictions; corrected line citations | applied | prediction in numbers |
| U4 | B2g rows with verdicts (I, W1, W2, W3, C, N1, N2) | applied | every outcome has a row |
| C1 | macOS node set-up; **third value 32**; **second IP = source 127.0.0.2 with `rpc_address` 127.0.0.1**; **`-Dcassandra.netty_use_heap_allocator=true`** on every node | applied | ≥ 3 values; no LAN exposure; with the pooled allocator (`CBUtil.java:60`, `maxOrder=11` → 16 MiB chunks, 20 event loops and 20 direct arenas on 10 cores) 16 held connections could commit up to 256 MiB and run B could not be told from run A |
| C2 | `hold_frames.py` with an optional source-address argument; **L = 4194296** instead of 4194304 | applied | 9 + L − 1 = 4194312 bytes would grow the cumulation to 8 MiB (Netty 4.1.130 `calculateNewCapacity`: powers of two up to 4 MiB, then 4 MiB steps); with 4194296 a connection holds exactly 4 MiB, as B3c's arithmetic assumes |
| C3 | `netstat` grouped by peer address, NMT `Other` committed delta, `ps` RSS; G and Gg; `send_failed` context only | applied | this host; a refused socket's `sendall` can race the node's close |
| C4 | exact procedure and readings; shakedown first | applied | exact sampling and stop conditions |
| C5 | exact counts; run C prediction (E1 = 32, O1 in [115, 256] MiB); D in [55, 130] MiB; P ≤ 0.1 × O2 | applied | prediction in numbers |
| C6 | B3g rows with verdicts (I, N1, W1, W2, W3, R, N2, N3) | applied | every outcome has a row |
| C7 | B3h: controls named; runtime-enable overshoot not run | applied | scope |
| C8 | macOS clean-up | applied | this host |
| S1 | For stage 3: the unit tier could feed each channel an incomplete frame and read the cumulation's capacity, so that the unit tier also speaks about bytes | left for stage 3 | not needed for a valid run |
| S2 | For stage 3: the runtime-enable overshoot named in A3 (channels accepted while the gate was off are never counted) has no test in the file; a run that enables the limit by JMX with connections open would show it | left for stage 3 | outside B1's claim |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 07:11; cluster 07:11–07:24 local time, EDT; node logs in UTC) |
| Node | `yangwang-mbp`, the advisor's laptop, single host (Apple T6000, 10 cores, 32 GiB) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Python | 3.8.11 (system `python3`, for `hold_frames.py`) |
| Local clone commit | `$W/cassandra-run56` (`W=~/Library/Caches/stage4`), fresh clone of `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` succeeded in 52 s; Netty 4.1.130.Final; `git status` clean after the run |
| Case-file commit / harness commit | `339e0b1` + uncommitted amendments (sha256 `ba3b32eb…`) / harness uncommitted |
| Storage for node data | internal SSD, APFS, 120 GiB free; node files `$W/node-ntpip`, fresh per node, removed at the end |
| Loopback | 127.0.0.1–.3 on `lo0`; the node on .1, clients from .1 and .2 (checked before the run that a listener on 127.0.0.1 sees a client bound to 127.0.0.2 as 127.0.0.2) |
| Free ports | 7000, 7199, 9042, 9091 free before the run |
| Full logs | `$W/logs/native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous/` (`clone.log`, `build-test.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-r1/`) |

Machine facts relied on (from earlier runs on this Mac): no `mkdir` in `$HOME` outside `$W`; commands touching `$W`/Java run unsandboxed;
`-Dlocal.repository=$W/m2` on every `ant` call; no `setsid` (node started as a tracked background `bin/cassandra -f > log 2>&1 < /dev/null`);
loopback aliases .2/.3 present; `cassandra-env.sh` sets `-XX:MaxDirectMemorySize=8192M` and the later `JVM_EXTRA_OPTS` flag `2G` wins
(both on the command line, `run1/cluster/A-jvmflags.txt`); Netty `ioBuffer()` is direct whenever Unsafe is available and pooled arenas
commit 16 MiB chunks (re-derived here from the bytecode and `conf/jvm11-server.options:145`; hence the heap-allocator flag); Netty growth
rounds a cumulation just over a power of two up (re-derived; hence L = 4194296); `EmbeddedChannel` closes a refused channel during
`register()`/`runPendingTasks()` and empties its pipeline (hence handler presence read in `initChannel`); CQLTester-free unit test with
`DatabaseDescriptor.daemonInitialization()` once per JVM; test stdout lands in `build/test/logs/**/TEST-<class>.log`; `-D` knobs reach the
forked test JVM only through `-Dtest.jvm.args` (shakedown values); bash 3.2 EXIT trap guarded to the main shell; node `system.log`
timestamps are UTC with `T`; the daemon class name kept out of `pkill` patterns; long steps in the background and polled; shakedown before
run 1; `selfcheck.py` written before run 1 and run end to end on both shakedowns (exit 0).

## 3. Runbook defects

None. Both shakedowns (unit with values -1, 2; cluster with K1 = 6, K2 = 3, 1 MiB held per connection (L = 1048568), limits -1 and 2)
ran as written and are not readings (`run1/shake/`). The cluster shakedown was also the instrument's known-answer check: 6 held 1 MiB
connections gave `Other` +6147 KB, 2 gave +2051 KB (`run1/shake/cluster-shake-commands.log`). One cosmetic harness fix was made after the
shakedown and before run 1: the grep that copies `rpc_address` into `<tag>-config.txt` matched `broadcast_rpc_address` first; it now
matches `; rpc_address=` (no runbook step or reading depends on it).

## 4. Run 1

**Scope:** unit tier, values -1, 0, 3, 5; cluster tier, runs A (-1), B (16), C (32). **Command logs:** `run1/unit/commands.log`,
`run1/cluster/commands.log`. Raw excerpts: `run1/unit/TEST-excerpt.log` (the probe lines of the TEST log), `run1/cluster/<run>/nmt-*.txt`,
`hold*.out`, `netstat-*-9042.txt` (the lines of each raw `netstat` file that mention port 9042), `<run>-config.txt`, `<run>-jvmflags.txt`,
`<run>-limit-log-lines.txt`, `<run>-system-excerpt.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/TEST-excerpt.log`, `run1/unit/probe.txt`; JUnit 1 test, 0 failures, `run1/unit/ant-summary.txt`)

| Value | Channels open from 10.0.0.1 (of 6) | open from 10.0.0.2 (of 2) | Map .1 / .2 after the 8 channels | Handler present | `CLOSED` map size | READBACK |
|---|---|---|---|---|---|---|
| -1 | 6 (1–6) | 2 | 0 / 0 | 0 of 8 | 0 | -1,-1 |
| 0 | 6 (1–6) | 2 | 0 / 0 | 0 of 8 | 0 | -1,0 |
| 3 | 3 (1–3; 4–6 closed) | 2 | 3 / 2 | 8 of 8 | 0 | -1,3 |
| 5 | 5 (1–5; 6 closed) | 2 | 5 / 2 | 8 of 8 | 0 | -1,5 |

**Cluster tier** (`run1/cluster/commands.log`, raw files per run). E counts are node-side ESTABLISHED connections on 127.0.0.1:9042 by peer
address; O is the committed delta of NMT `Other` against the baseline.

| Per-IP limit | Run | E1 (from .1, s1–s3) | E1' (from .1, s4–s6) | E2 (from .2, s4–s6) | O1 (s1–s3) | O2 (s4–s6) | D = O2 − O1 | P (post) | F1 / F2 (send_failed) | G / Gg (log lines) |
|---|---|---|---|---|---|---|---|---|---|---|
| -1 | A (control) | 64 | 64 | 16 | +262144 KB = 256.0 MiB | +327680 KB = 320.0 MiB | 64.0 MiB | 0 KB | 0 / 0 | 0 / 0 |
| 16 | B | 16 | 16 | 16 | +65536 KB = 64.0 MiB | +131072 KB = 128.0 MiB | 64.0 MiB | 0 KB | 48 / 0 | 1 / 0 |
| 32 | C | 32 | 32 | 16 | +131072 KB = 128.0 MiB | +196608 KB = 192.0 MiB | 64.0 MiB | 0 KB | 32 / 0 | 1 / 0 |

The three samples of each window were identical (`commands.log`). The log lines are `Exceeded maximum native connection limit per ip of 16
by using 17 connections` (run B, 11:17:35 UTC) and `… of 32 by using 33 connections` (run C, 11:21:42 UTC) (`B-`/`C-limit-log-lines.txt`).
Node configuration lines: `native_transport_max_concurrent_connections=-1; native_transport_max_concurrent_connections_per_ip=-1/16/32`,
idle timeout 0ms, frame size 16MiB, `rpc_address=127.0.0.1` (`<run>-config.txt`). RSS (context only): 1.33 GB at baseline, up to
1.54 GB (`commands.log`).

### 4.2 Conclusion and logic

1. **Validity.** Unit: an `END` line, 32 CH lines, every READBACK echoes `-1,<value>` [observed: `run1/unit/TEST-excerpt.log`]; channel 1 is
   open at every value, so the `remoteAddress0` override was seen (row I excluded) [observed: same]. Cluster: in run A all 64 and 16
   connections were held (E1 = 64, E2 = 16, F1 = F2 = 0), so the workload passed both limits [observed: `run1/cluster/commands.log`,
   `A/hold1.out`, `A/hold2.out`]; each node ran with global -1, the per-IP value, idle 0ms, frame 16MiB [observed: `<run>-config.txt`] and
   with `-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2G -Dcassandra.netty_use_heap_allocator=true` [observed:
   `<run>-jvmflags.txt`]; both scripts printed their `attempted` lines before their stop times [observed: `commands.log`]. Valid.
2. **Readings.** Nothing unusual. Every `Other` delta is an exact multiple of 4096 KB = 4 MiB: 64, 80, 16, 32, 32, 48 connections ×
   4 MiB [observed: `<run>/nmt-s3.txt`, `nmt-s6.txt`], which matches C2's derivation of exactly 4 MiB per connection [inferred: C2]. The
   release was complete (P = 0 KB, E = 0/0 at post) [observed: `<run>/nmt-post.txt`, `netstat-post-9042.txt`]. F1 = 48 and 32 equal the
   refused counts exactly; F1 is context only (C3).
3. **Matched row.** Unit **C (Confirmed — caps the per-IP connection count)**: -1 and 0 install no handler and keep all 8 channels with an
   empty map; 3 keeps exactly channels 1–3 of 10.0.0.1 (map 3) and both of 10.0.0.2 (map 2); 5 keeps channels 1–5 (map 5) and both of
   10.0.0.2; the map is empty after every close [observed: `run1/unit/TEST-excerpt.log`]. Cluster **R (Confirmed — caps, per source IP)**:
   E1 = E1' = 16 in B and 32 in C; E2 = 16 in B and C; O1 = 256.0 ∈ [230, 520], 64.0 ∈ [55, 130], 128.0 ∈ [115, 256] MiB with
   64 < 128 < 256; D = 64.0 ∈ [55, 130] MiB in every run; G = 1 in B and C, Gg = 0 everywhere; P = 0 ≤ 0.1 × O2 in every run
   [observed: `run1/cluster/commands.log`, raw files, recomputed in `run1/selfcheck.out`].
4. **Excluded rows.** Unit: I (channel 1 open at 3 and 5); W1 (open from .1 = 3 and 5, not more); W2 (both .2 channels open at 3 and 5);
   W3 (handler 0/8 at -1 and 0, 8/8 at 3 and 5); N1 (every `CLOSED` map size 0); N2 (C fits). Cluster: I (run A held 64 + 16, F1 = 0,
   attempted lines present); N1 (O1 of A = 256.0 ≥ 230); W1 (E1 = 16 and 32, not more); W2 (E2 = 16 in B and C); W3 (O1 of B = 64.0 ≤ 130,
   of C = 128.0 ≤ 256); N2 (release observed, P = 0); N3 (R fits). [observed: same files]
5. **Observed vs. inferred.** The conclusion depends on: (a) NMT `Other` is where the held cumulations live under the heap-allocator flag
   [inferred: C1's bytecode reading; supported by the shakedown known answer, 6 × 1 MiB → +6147 KB, and by every delta being an exact
   multiple of 4 MiB per held connection]; (b) the refused connections were closed by `ConnectionLimitHandler`'s per-IP branch and not by
   something else [inferred: the per-IP log line with "by using 17/33 connections", i.e. the first refusal at limit + 1, Gg = 0, and the
   node-side count stopping exactly at the limit]; (c) the handler was installed by line 240's second operand with the global limit at -1
   [observed in the unit tier: handler present at 3/5, absent at -1/0, global READBACK -1; inferred for the cluster tier from the same
   code path and the configuration line].
6. **Deviations and gaps.** None from the frozen runbook. The unit tier measures no memory (U4). The cluster tier measures direct memory
   only: per-connection heap objects (channel, pipeline) are not in `Other` and were not measured; they are small next to 4 MiB and do not
   affect the rows. Only one source address pair and one held size (4 MiB) were run. The runtime-enable overshoot (A3) was not tested (C7, S2).
7. **Core question.** Usage followed the constraint: with one source address offering 64 connections of 4 MiB each, the node held
   min(64, P) connections and min(64, P) × 4 MiB of direct memory for P = -1 (unlimited), 16 and 32 (parts 3, 2), the refusals were logged by
   the per-IP branch (parts 3, 5b), a second address got its own allowance on top (E2 = 16, D = 64 MiB in every run; part 3), and the memory
   went back to baseline when the connections closed (part 2). So the constraint caps the memory one source IP can pin through open native
   connections, per source IP only (part 6: many IPs each get P).

**Conclusion (one line):** unit — row C, confirmed; cluster — row R, confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1 and run end to end on both shakedowns, exit 0: `run1/shake/selfcheck-unit-shake.out`,
`run1/shake/selfcheck-cluster-shake.out`) re-reads the raw files — the TEST log's probe lines; every `netstat-*.txt`, `nmt-*.txt`,
`hold*.out`, `<run>-system.log` and `<run>-config.txt` of the full log folder — recomputes every reading without the run scripts' summary
lines, cross-checks each sample against `commands.log`, and matches the U4/C6 rows. Unit: 10 checks, 0 failed, row C
(`run1/selfcheck-unit.out`, exit 0). Cluster: 27 checks (21 raw-vs-log sample matches, 3 attempted-line checks, 3 configuration checks),
0 failed, all 22 row-R conditions hold, row R (`run1/selfcheck.out`, exit 0).

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `TEST-excerpt.log` has END and channel 1 open at 3 and 5; `A/hold1.out` "attempted 64 send_failed 0", `A/hold2.out` "attempted 16 send_failed 0"; `A/netstat-s3-9042.txt` 64 node-side ESTABLISHED from 127.0.0.1; `*-config.txt`, `*-jvmflags.txt` show the frozen settings. |
| 2. Readings | yes | `A/nmt-s3.txt` `Other … committed=320134KB +262144KB`; `B/nmt-s3.txt` `+65536KB`; `C/nmt-s3.txt` `+131072KB`; `*/nmt-post.txt` with no delta; `selfcheck.out` recomputed values equal the table. |
| 3. Matched row | yes | Each C6 row-R condition re-evaluated from raw files by `selfcheck.py` (all hold); unit row C re-evaluated per channel. |
| 4. Excluded rows | yes | `selfcheck.py` evaluates the rows in C6/U4 order; no earlier row fires. |
| 5. Observed vs. inferred | yes | (a) shakedown known answer in `shake/cluster-shake-commands.log` (+6147 KB for 6 × 1 MiB; +2051 KB for 2); run 1 deltas exact multiples of 4096 KB. (b) `B-limit-log-lines.txt`, `C-limit-log-lines.txt` show the per-IP message at 17 and 33; Gg = 0. (c) unit handler presence per channel in `TEST-excerpt.log`. |
| 6. Deviations and gaps | yes | `commands.log` shows the frozen parameters (`K1=64 K2=16 LEN=4194296 HOLD1=120 HOLD2=90 IDLE=60`, runs A:-1 B:16 C:32) and the C4 schedule (samples at t0+20…65, post at t0+140/141). |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Ceiling follows the knob at two values (16 → 64 MiB, 32 → 128 MiB, unlimited → 256 MiB), disallow branch evidenced, per-address scope and release shown, as B1 and C6 require. |

### 5.2 Run 2?

**No** — decided 2026-10-27. The readings are exact counts and exact 4 MiB multiples, every inferred statement has direct support in run 1's
raw files, the self-check settles every part, and the result confirms the case (no refutation, no bypass).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** (B1) With `native_transport_max_concurrent_connections_per_ip = P > 0` and the global limit at -1, a single client IP keeps
at most P connections open; the memory those connections pin with incomplete frames scales with min(attempted, P); a second IP gets its own P.
"Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (U4 row C): -1 and 0 install no handler and keep all 8 channels; 3 and 5 keep exactly 3 and 5 channels of 10.0.0.1 and both of 10.0.0.2; map empty after every close | caps (the connection count per source address) | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** (C6 row R): 64/16/32 connections held from 127.0.0.1 at -1/16/32, NMT `Other` +256.0/64.0/128.0 MiB = min(64, P) × 4 MiB; 16 more from 127.0.0.2 in every run (+64.0 MiB); one per-IP log line in each capped run; back to 0 after close | caps (per source IP) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted, 2026-10-27); the amended sections are U1–U4 (B2a–B2g)
and C1–C8 (B3a–B4), applied before any reading. `_INDEX.md` §4 has the frozen-hash row and §1's Stage 4 column is filled.
