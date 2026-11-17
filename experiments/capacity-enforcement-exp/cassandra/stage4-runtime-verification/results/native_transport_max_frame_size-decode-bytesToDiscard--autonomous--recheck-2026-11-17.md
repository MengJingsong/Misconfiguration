# native_transport_max_frame_size-decode-bytesToDiscard--autonomous — stage-4 results, recheck claim (2026-11-17)  <!-- file: results/native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17.md -->

> **Case:** [`native_transport_max_frame_size-decode-bytesToDiscard--autonomous`](../../stage3-ai-deep-read/cases/native_transport_max_frame_size-decode-bytesToDiscard--autonomous.md), section "Recheck — enforcement properties (guided, 2026-11-16, blind)", its **Stage-4 claim to add**
>
> **Status:** verdict filed (2026-11-17)
>
> **Outcome class:** not reclassified. This run tests the recheck claim (the multiplier), not the stage-3 estimate; the case keeps the class of its 2026-10-27 results ([`..--autonomous.md`](native_transport_max_frame_size-decode-bytesToDiscard--autonomous.md): true positive, per-connection cap). The node-level finding is in §8.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Case file at commit `fe46a36a` (HEAD `2f76b847`), plus the appended section `## Stage-4 design for the recheck claim (2026-11-17)` (uncommitted). Frozen design = that section through the end of the file, after amendment S1: `sed -n '/^## Stage-4 design for the recheck claim (2026-11-17)/,$p' <case file> \| git hash-object --stdin` = **`b20c07daf3c2af783b6cf0ec1e1617164eb0e3c2`** (134 lines), recorded before run 1. The section as first written, before S1, hashed `1434b91f42ac69ce4f43165facb502f4bc00dd1f`. |
| **Harness** | [`harness/native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17/`](../harness/native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17/): `run.sh` (per-arm node in a systemd user scope, samples, logs), `hold_prelogin.py` (client, `partial` / `complete`), `ntfr.btm` (observe-only Byteman rules `NTFDISCARD`, `NTFFAIL`, `NTFMEM`), `probe/ntfr/Probe.java` (read-only helper the `NTFMEM` rule calls; compiled by `run.sh` against the run copy's Netty 4.1.130 jars). `NTFDISCARD`/`NTFFAIL`, the node start/stop and NMT parsing are adapted from the 2026-10-27 harness `harness/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/` (tools only). Self-check: [`run1/selfcheck.py`](native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17/run1/selfcheck.py). Uncommitted (no commit asked). Instrument checks before run 1: Byteman `TestScript: no errors` (every run), two shakedowns on `pc84` (§3), self-check known-answer runs (a control that holds frames → N2; a control without probe fields → Invalid). |
| **Tiers and values** | Cluster tier only (one node). The knob stays at its default (16 MiB); the dose is the number of stalled pre-login connections `k` = 64, 256, 512, with a matched control of 512 complete small OPTIONS requests. Unit tier: `n/a` for this claim (the claim is about connection count and real process memory, which a unit test of `Envelope.Decoder` cannot show; the decoder's per-connection behaviour was the 2026-10-27 unit tier). |
| **Audit bottom line** | **Ready after amendments** (amendment S1, from the shakedown, before the freeze) — 2026-11-17 |

### 1.1 Design audit

Audited: the new section `## Stage-4 design for the recheck claim (2026-11-17)` (written in this session from the recheck's one-sentence claim).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Hypothesis: bytes held by stalled pre-login cumulations, Netty pooled direct memory. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met (other approach) | Test: knob held at default (the claim is about the multiplier at defaults; the dose-response on the knob was the 2026-10-27 run); the dose is `k` at three values plus a matched control. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | O1 Netty's limit-checked counter, O2 pool, O3 NMT `Other`, O4 scope `memory.current`; O6 Cassandra's own counts beside them. |
| A. Core question | usage driven to the limit and past it | Partly | By instruction a measurement, not exhaustion: the largest arm reaches about 60 % of the 15,872 MiB direct limit. "Not tested" names the gap (behaviour above `MaxDirectMemorySize`); the limit Netty enforces is read. |
| B. Logic | each step says what it establishes | Met | Logic (1)–(5). |
| B. Logic | prediction stated in numbers or a clear relation | Met | P1–P5 with `U` = 16,777,216 B, exact counts and bands (S1). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Not held (R1), refused (R2), counted (R3), control moves (N1), size differs (N2), not released (N3), catch-all (N4), invalid (I); "limit never reached" is by design and stated. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (adapted) | Here the claim is "no refusal": the direct evidence is the absence of the disallow branch (`NTFDISCARD`/`NTFFAIL` = 0) plus every frame accepted (`SUPPORTED` after the last byte), and the held count follows `k` exactly (`held16`). |
| B. Logic | alternative explanations and their controls | Met | Controls paragraph: CTRL (connection cost), D0 (drift), R (release); O1 is direct-only. S1 replaced the CTRL subtraction on the chunk-granular counter, which the shakedown showed unsound, by the direct `held16` count. |
| C. Specific | a human can follow it from the intro and the block | Met | Intro and "How this verifies the claim". |
| C. Specific | an AI can run it without re-deriving the code path | Met | Procedure and `run.sh`. |
| C. Specific | values, workload, commands, observables, sampling, stop conditions exact | Met | Workload, Procedure (sample times, 300-s stops), Observables. |
| D. Runnable | harness and environment prerequisites exist | Met | `pc84` built copy, JDK 11.0.33, Python 3.10.12, Byteman 4.0.20 from the build, cgroup v2 with the memory controller delegated to the user manager (checked). |
| D. Runnable | workload arithmetic reaches the target (data, time, memory) | Met | Arithmetic: up to 8 GiB of client traffic over loopback; ≈ 9.5 GiB peak Netty direct of a 15.5 GiB limit; `memory.current` well inside 24 GiB; ≈ 6 min per arm. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `Envelope.java:197, 424-442`; `Config.java:139, 285, 289`; `PipelineConfigurator.java:148, 236-265`; `InitialConnectionHandler.java:52-95`; `CBUtil.java:59-60`; `NativeTransportService.java:69`; `ClientResourceLimits.java:74-77`; `Server.java:150-153, 333-341`; `ClientMetrics.java:44, 125, 158`; `conf/cassandra-env.sh:53-66, 96-104, 141-158`; `conf/jvm11-server.options:63, 141-145`; Netty 4.1.130 `AbstractByteBufAllocator.calculateNewCapacity` (4 MiB steps, `javap -c`), `PoolArena.allocate` (normal vs huge by `nSizes`), `PlatformDependent.DIRECT_MEMORY_LIMIT` / `io.netty.maxDirectMemory` (`javap`). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S1 | Count held 16 MiB buffers directly (`held16` from `ntfr.Probe`); replace the CTRL subtraction on Netty's counter by `k·U ≤ ΔO2 ≤ (k+64)·U`; OOM grep on the exception text | applied 2026-11-17 before the freeze (in hash `b20c07da…`) | shakedown 1 (§3 D1): per-arena chunks come and go independently of the held frames |
| Q1 | Stage 3: when a design reads Netty pooled memory, state which allocations are whole chunks and which share per-arena chunks whose lifetime follows the thread caches | left for stage 3 | led to S1 |
| Q2 | Stage 3: the recheck's E4 example ("256 × 16 MiB = 4 GiB = the default direct budget of a 16-GiB host") should add the per-arena chunks (up to 2 × cores × 16 MiB) the pool keeps once connections arrive | left for stage 3 | context for the threshold estimate |

**Agreement criteria** — not filled (no run 2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-17 (shakedowns 10:45–10:58 MST, run 1 from 11:00:02 local (UTC−7); node logs in UTC) |
| Node | `pc84` = `node1.jason92-326528.misconfiguration-pg0.cloudlab.umass.edu`, x86_64, 32 cores, 125 GiB RAM, 8 GiB swap on; node, client and samplers all on `pc84` |
| OS and kernel | Ubuntu 22.04.2, `5.15.0-203-generic`, cgroup v2 (user manager delegates `memory pids`) |
| JDK | OpenJDK 11.0.33 (2026-10-20) |
| Ant | 1.10.12 (build only; the base copy was built with `ant build-test` on 2026-11-17) |
| Python | 3.10.12 (client) |
| Local source copy | `/mydata/s4/ntfs-rc`, `cp -a` of `/mydata/s4/cassandra-base` (`copy-source.sh` copy of repo `systems/cassandra/source/` at `cassandra-5.0.9`, built); `git status --short` empty before the run; Netty 4.1.130.Final, Byteman 4.0.20 from `build/lib/jars` |
| Case-file commit / harness commit | case file `fe46a36a` + the uncommitted design section (hash `b20c07da…`); harness uncommitted |
| Node settings | shipped `conf/` with only `listen_address`, `rpc_address` (127.0.0.1) and the data/commitlog/hints/saved_caches/cdc_raw directories overridden; `MAX_HEAP_SIZE=4G` (G1, `-Xms4G -Xmx4G`, `AlwaysPreTouch`), `MAX_DIRECT_MEMORY_SIZE=15872M` → `-XX:MaxDirectMemorySize=16642998272`; default pooled allocator (`maxOrder=11`, 64 direct arenas, 16 MiB chunks); `-XX:NativeMemoryTracking=summary`; Byteman `script:ntfr.btm,sys:ntfr-probe.jar`; `ulimit -n 100000` |
| Memory budget | `systemd-run --user --scope -p MemoryMax=24G -p MemorySwapMax=0` (`memory.max` 25,769,803,776, `memory.swap.max` 0, read back per arm); started from an ssh session from the repo host kept open for the whole run |
| Storage for node data | `/mydata` (local, 714 GiB free), `/mydata/s4/ntfs-rc/node-<arm>`, fresh per arm, removed at the end |
| Full logs (path, outside the repo) | `pc84:/mydata/s4/ntfs-rc/logs/{shake,shake2,r1}/` (`commands.log`, per arm `system.log`, `node-stdout.log`, NMT files) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Design version with the fix |
|---|---|---|---|---|---|---|
| D1 | shakedown 1 (`shake`: CTRL `k`=8, H8, hold 30 s; before the freeze and run 1) | Prediction P2/P3 and row R1 (CTRL subtraction on O1) | The native-transport pool keeps one chunk per arena an event loop touched, and frees it at times the workload does not control: H8 read Netty used direct +268,435,456 B (16 chunks) at S1 and +134,217,728 B (8 chunks) at S2–S3 with all 8 connections still holding their frames (8 `SUPPORTED` after the last byte), while CTRL kept +134,217,728 B (8 chunks) for 8 idle connections; H8 − CTRL = 0 at S2–S3 would have matched R1 although `memory.current` showed +219 MiB held vs +2.5 MiB. The `OutOfMemoryError` count matched `-XX:+HeapDumpOnOutOfMemoryError` in the JVM-argument log line (1 in `system.log`, 2 in stdout). (`pc84:/mydata/s4/ntfs-rc/logs/shake/commands.log`) | Amendment S1: count held 16 MiB buffers directly (`ntfr.Probe`: chunks with no free bytes + huge allocations), bound ΔO2 by `k·U … (k+64)·U`, keep CTRL for O4 and as a ceiling on connection cost; match the exception text. Shakedown 2 (`shake2`: H8, H72, hold 60 s) with the fix: `held16` = 8 and 72 at S1–S3 and 0 at base, D0, R; `activeHuge` 0 (a 16 MiB request is a whole-chunk normal allocation); 64 per-arena chunks at H72; OOM counts 0. | applied 2026-11-17, before the freeze; run 1 not yet started | `b20c07da…` |

## 4. Run 1

**Scope:** cluster tier, one node, arms CTRL (`complete`, `k` = 512), H64, H256, H512 (`partial`, `L` = 16,777,207), hold 90 s, fresh
node per arm; 11:00:02–11:18:02 local. **Command log:** [`run1/r1/commands.log`](native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17/run1/r1/commands.log).
Excerpts per arm under `run1/r1/<arm>/` (`config.txt`, `jvm-args.txt`, `base|D0|S1|S2|S3|R.txt` samples, `counts.txt`, `client.out`,
`btm-lines.txt`, `system-warn-error.txt`, `nmt-S2.txt`); shakedown logs under `run1/shake/`. Full logs: `pc84:/mydata/s4/ntfs-rc/logs/r1/`.

### 4.1 Readings

Δ = sample − base (base after 60 s idle), MiB = 1,048,576 B, `U` = 16 MiB. O1 Netty `usedDirectMemory` (limit-checked), O2 the
native-transport pool, O3 NMT `Other` committed, O4 scope `memory.current`. S1–S3 were identical within 0.5 MiB in every arm; S2 shown.

| Arm | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| all | — | effective config | `native_transport_max_frame_size=16MiB`, `max_concurrent_connections=-1` (and per-IP -1), `idle_timeout=0ms`, `max_request_data_in_flight=null` (default), `-XX:MaxDirectMemorySize=16642998272`, heap 4 GiB, scope `memory.max` 25,769,803,776 / `memory.swap.max` 0 | `r1/<arm>/config.txt` |
| all | — | Netty limit, allocator | `nettyMax=16642998272` (= `MaxDirectMemorySize`), `PooledByteBufAllocator`, 64 direct arenas, chunk 16,777,216 | `r1/<arm>/S2.txt` |
| all | drift | ΔO1 / ΔO4 at D0 | 0 / ≤ +1.1 MiB | `r1/<arm>/D0.txt` |
| all | — | `memory.events` `max` / `oom_kill` | 0 / 0 at every sample | `r1/<arm>/*.txt` |
| CTRL (512) | control | client | `holding 512`, 512 `SUPPORTED` at connect, `alive 512 closed 0` | `r1/CTRL/client.out` |
| CTRL | control | ΔO1 = ΔO2 / ΔO3 / ΔO4; `held16`, chunks | +1,024.0 / +1,025.0 / +15.6; 0 held, 64 chunks (one per arena) | `r1/CTRL/S2.txt` |
| H64 | A | ΔO1 = ΔO2 / ΔO3 / ΔO4; `held16`, chunks | +2,048.0 / +2,048.0 / +1,817.8; 64 held, 128 chunks | `r1/H64/S2.txt` |
| H256 | B | ΔO1 = ΔO2 / ΔO3 / ΔO4; `held16`, chunks | +5,120.0 / +5,120.0 / +4,902.4; 256 held, 320 chunks | `r1/H256/S2.txt` |
| H512 | C | ΔO1 = ΔO2 / ΔO3 / ΔO4; `held16`, chunks | +9,216.0 / +9,216.0 / +9,012.9; 512 held, 576 chunks; Netty used 9,680,453,632 B = 58.2 % of the limit; `memory.current` 14,455,300,096 B (13.5 GiB of 24 GiB) | `r1/H512/S2.txt`, `S3.txt` |
| H64→H256→H512 | slopes | per added stalled connection, S1–S3 | O4: 1.004 U and 1.004 U (16.07 MiB); O1: exactly 1.000 U | `run1/selfcheck.out` |
| held arms | — | what Cassandra counts (O6) | `inflight=0` (bytes charged to `native_transport_max_request_data_in_flight`) and `clients=0` (`ConnectedNativeClients`) at every sample | `r1/<arm>/S*.txt` |
| held arms | — | refusal evidence | `holding k`, 0 connect errors, `alive k closed 0 unexpected 0`; `NTFDISCARD` 0, `NTFFAIL` 0; `k` responses, all opcode 6 `SUPPORTED`; 0 `OutOfDirectMemoryError`, 0 `java.lang.OutOfMemoryError:`, 0 `Request is too big`, 0 `ERROR` lines | `r1/<arm>/client.out`, `counts.txt` |
| held arms | release | at R: `held16`; ΔO2; ΔO4 | 0; +1,024.0 (the 64 per-arena chunks) in each; ΔO4 +1,802.7 / +2,565.8 / +2,854.3 (not returned to the OS) | `r1/<arm>/R.txt` |
| all | — | `system.log` WARN/ERROR | 5 start-up WARN lines each (jemalloc not preloaded, JMX local only, swap on, `vm.max_map_count`, new host ID), no ERROR | `r1/<arm>/system-warn-error.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Every node ran with the shipped limits (frame size 16 MiB, connections unlimited, idle timeout 0, in-flight
   default) and the recorded direct limit 16,642,998,272 B, which Netty reports as its own limit [observed: `r1/<arm>/config.txt`,
   `S2.txt` `nettyMax`]. Drift at D0 was 0 on O1 and ≤ 1.1 MiB on O4 [observed: `D0.txt`]. The budget never bound: `memory.events`
   `max` and `oom_kill` 0, peak `memory.current` 13.5 GiB of 24 GiB [observed: `H512/S3.txt`]. Every client held all its
   connections; the control got 512 `SUPPORTED` [observed: `client.out`]. Valid. By design the direct limit was not reached (58 %).
2. **Readings.** S1–S3 identical in every arm (the per-arena chunk drop seen in shakedown 1 did not recur). O1, O2 and O3 agree to
   within 1 MiB [observed: `S*.txt`, `nmt-S2.txt`]. `memory.current` is not returned at R although Netty freed the chunks
   [observed: `R.txt`; inferred: glibc keeps freed blocks, jemalloc was not preloaded per the start-up WARN]; context only.
   Cassandra's connected-client gauge read 0 with up to 512 connections open [observed: `S*.txt` `clients=0`].
3. **Matched row: C** — "P1–P5 all hold". P1a: `held16` = 64 / 256 / 512 at S1–S3, 0 in CTRL and at base/D0 [observed: `S*.txt`,
   `base.txt`, `D0.txt`]; P1b: O4 slopes 1.004 U ∈ [0.9, 1.25] U [observed: `selfcheck.out`]. P2: ΔO2 = (k + 64)·U exactly
   (2,048 / 5,120 / 9,216 MiB) ∈ [k·U, (k+64)·U]; |ΔO1 − ΔO2| = 0; ΔO4 − ΔO4(CTRL) = 1,802 / 4,887 / 8,997 MiB ≥ 0.9·k·U
   (922 / 3,686 / 7,373) [observed: `S*.txt`]. P3: ΔO2(CTRL) = 1,024 MiB = 64·U ≤ 64·U; ΔO4(CTRL) 15.6 MiB ≤ 512 [observed:
   `CTRL/S*.txt`]. P4: as in the refusal-evidence row; in-flight 0 [observed: `client.out`, `counts.txt`, `S*.txt`]. P5: `held16` 0 and
   ΔO2 = 64·U at R [observed: `R.txt`].
4. **Excluded rows.** I — config, limit, drift, budget events, holding lines all as required (part 1). R1 (Refuted) — `held16` = k,
   not < 0.5·k; ΔO2 ≥ k·U; slopes 1.004 U, not < 0.5 U. R2 (Refuted) — 0 connect errors, 0 closed, 0 discard/fail, all responses
   `SUPPORTED`, 0 OOM. R3 (Refuted) — in-flight 0 at every held sample. N1 — control within P3. N2 — P1, P2 hold. N3 — P5 holds.
   N4 — C matched.
5. **Observed vs. inferred.** Inferred and load-bearing: (a) a chunk with no free bytes is one stalled connection's cumulation — the
   probe counts chunks, not channels; supported by `held16` = k exactly in three arms and 0 in the control and after the final bytes,
   and by `activeHuge` = 0 (`S2.txt`); (b) `PlatformDependent.usedDirectMemory()` is the counter `OutOfDirectMemoryError` is thrown from
   (Netty 4.1.130 bytecode, `DIRECT_MEMORY_LIMIT`, `javap`); (c) the bytes are pre-login: the client never sends STARTUP, and the
   response to the completed frame is `SUPPORTED` from `InitialConnectionHandler` (`InitialConnectionHandler.java:77-95`).
6. **Deviations and gaps.** Above-limit behaviour (`OutOfDirectMemoryError`) not tested (by instruction); the `k` at which the limit
   would be reached is extrapolated in §8. Heap 4 GiB instead of the 31 GiB the env script would pick on this host (the direct limit
   is the env script's own value). One client host, loopback, one IP (per-IP limits are -1 by default too). Design amended once
   before the freeze (S1, §3). Protocol v5 is not exercised (its framed path does not use this decoder).
7. **Core question.** Each stalled pre-login connection held one 16 MiB pooled direct chunk (parts 3, 5a), so held direct memory
   rose exactly `k × 16 MiB` above a fixed 1 GiB per-arena cost, and resident memory rose 16.07 MiB per connection (part 3); Cassandra
   counted none of it and refused nothing (parts 3, 4). `native_transport_max_frame_size` caps each connection at about one frame, as
   the 2026-10-27 run found, but nothing at the defaults caps the node: held direct memory follows the number of connections.

**Conclusion (one line):** row **C** — confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1; known-answer runs on shakedown files: a control that holds frames → N2, files without
probe fields → Invalid) re-reads every arm's `config.txt`, samples, `client.out` and `counts.txt` and applies the frozen rows.
Output [`run1/selfcheck.out`](native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17/run1/selfcheck.out): no flag set, **ROW C Confirmed (P1-P5 hold)**.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | four `config.txt` re-read (16MiB, -1, 0ms, 16642998272, scope 24G/0); `S2.txt` `nettyMax=16642998272 allocator=PooledByteBufAllocator arenas=64`; `S3.txt` `events.max=0 oom_kill=0`; H512 `memory.current=14455300096`. |
| 2. Readings | yes | H512 `nmt-S2.txt` `Other … committed=9500991KB +9437184KB` = 9,216 MiB = ΔO1; `R.txt` O4 not released; `system-warn-error.txt` jemalloc WARN. |
| 3. Matched row | yes | `S2.txt` `fullChunks=64/256/512 activeHuge=0`; `selfcheck.out` slopes 1.004 U; `client.out` 64/256/512 opcode-6 `resp` lines; `counts.txt` all 0. |
| 4. Excluded rows | yes | each refuting condition re-checked against `client.out` (`alive k closed 0 unexpected 0`, no `connect` lines) and `counts.txt`; `inflight=0` in every `S*.txt`. |
| 5. Observed vs. inferred | yes | (a) `held16` 0 → k → 0 across base / S / R in each arm, and 0 in CTRL with 512 connections; (b) bytecode check recorded in §1.1; (c) client sends only OPTIONS headers and body bytes (`hold_prelogin.py`). |
| 6. Deviations and gaps | yes | recorded above and in §3; the not-tested part is stated in the design. |
| 7. Core question | yes | the design's logic (1)–(5) runs: control isolates connection cost (1,024 MiB, not resident), slopes give 16 MiB per connection, real resource and counters both read, no refusal, release ties it to the connections. |

Process check after the run: `ps -eo cmd | grep '[C]assandraDaemon'` 0, `grep '[h]old_prelogin'` 0, no `ntfs-rc-*` user scopes, no
`:9042` listener, node directories removed (`commands.log` last lines and a separate check on `pc84`).

### 5.2 Run 2?

**No** (2026-11-17). The matched row rests on observed counts that agree across four instruments, and the one inference the row
depends on (chunk = connection) is backed by exact counts in all arms; the result neither refutes the case nor needs a by-hand repeat.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive (the case's Estimate line; unchanged). The recheck's real-memory estimate was "positive per
connection; undetermined for the node".

**Claim tested** (the recheck's Stage-4 claim to add, as designed in the case file's section "Stage-4 design for the recheck claim
(2026-11-17)"): at the shipped defaults, `k` pre-login v4 connections each holding a header declaring a body of 16 MiB − 9 B and all
but its last byte hold direct memory ≈ `k × (16 MiB + slack)`, and nothing in Cassandra charges or refuses them below the
direct-memory limit.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | not run: the claim is about connection count and process memory (the decoder's per-connection behaviour was the 2026-10-27 unit tier) | — | — | 2026-11-17 |
| Cluster | **Confirmed** (design row C) | **does not cap** the node: each connection is capped at one 16 MiB frame (slack 0 at this size), but held direct memory is `k × 16 MiB` + 1 GiB of per-arena chunks with no Cassandra limit on `k` | run 1 + self-check | 2026-11-17 |

Key numbers: `k` = 64 / 256 / 512 → Netty direct +2,048 / +5,120 / +9,216 MiB (exactly `k` held 16 MiB chunks + 64 per-arena
chunks), `memory.current` +1,818 / +4,902 / +9,013 MiB, 16.07 MiB resident per added connection; control (512 complete requests) +1,024 MiB
Netty / +15.6 MiB resident. Counted by Cassandra: 0 bytes in flight, 0 connected clients.

**Extrapolation (inferred, not tested).** Netty's limit is `MaxDirectMemorySize` (read: 16,642,998,272 B). On this host at the
env script's default limit (15,872 MiB), the native-transport pool alone would reach it at about `(15,872 − 1,024 − 16) / 16` ≈ 927
stalled connections. On the recheck's 16-GiB host (default direct limit a quarter of RAM, about 4,096 MiB, `cassandra-env.sh:58-66`)
the pool has `min(2 × cores, 4,096 / 16 / 6 = 42)` arenas, each keeping a 16 MiB chunk once used, so the threshold is about
`(4,096 − arenas × 16) / 16`, roughly 214–254 connections rather than the recheck's 256. What happens at the limit (`OutOfDirectMemoryError`
on these or other direct allocations) is not tested here.

**Feedback filed:** one dated line in the case file's section D pointing here; the design section and its amendment S1 in the case
file (written in this session). Not edited: `recheck-flags.md`, `_INDEX.md`, HANDOFF (by instruction). Nothing committed.
