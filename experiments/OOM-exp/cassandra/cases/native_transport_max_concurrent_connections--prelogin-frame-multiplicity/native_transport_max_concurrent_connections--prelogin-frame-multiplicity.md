# U2 — native_transport_max_concurrent_connections (unset): stalled pre-login 16 MiB frames × connections exhaust Netty direct memory  <!-- file: cassandra/cases/native_transport_max_concurrent_connections--prelogin-frame-multiplicity/native_transport_max_concurrent_connections--prelogin-frame-multiplicity.md -->

| Field | Value |
|---|---|
| Case ID | `U2` (unprotected; README "ID prefixes") |
| From | `OC-21` of the phase 1 OOM candidate list (campaign row U2 / P1, retired campaign plan) |
| Phase-1 case file | [`native_transport_max_concurrent_connections-channelActive-limit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/native_transport_max_concurrent_connections-channelActive-limit--autonomous.md); stage-4 evidence from the sibling case [`native_transport_max_frame_size-decode-bytesToDiscard--autonomous` recheck 2026-11-17](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9), Netty 4.1.130.Final, OpenJDK 11.0.33 |
| Stage 1 (design) | OOM-agent stage-1 session (workflow wave 1), 2026-11-17 ~22:45 America/New_York |
| Stage 2 (verify) | OOM-agent stage-2 session, runs 2026-11-17 22:53 – 2026-11-18 00:04 America/New_York on pc84; cut off by an API usage limit before writing §3–§4; resumed by a fresh stage-2 session 2026-11-18 02:54 (§3 "Resume note") |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected configuration) |

## Summary

- **Conclusion:** true positive. At shipped defaults and the budget `cassandra-env.sh` resolves by itself for a ≥ 64 GiB host
  (heap 31,744 MiB, `MaxDirectMemorySize` 15,872 MiB), 927 unauthenticated v4 connections each holding a stalled 16 MiB − 1 B
  pre-login frame exhaust Netty's direct limit (`OutOfDirectMemoryError`, used = max = 16,642,998,272 B); Cassandra turns the
  error into a forced "Java heap space" OOM and the shipped `OnOutOfMemoryError="kill -9 %p"` kills the node (exit 137) 40 s
  later, 4/4 runs (3 instrumented + 1 uninstrumented). The 2 GiB-direct budget fails the same way at 106 connections (3/3), an
  8 GiB one at 447 (1/1). Controls (448 stalled frames; 1,120 idle complete connections) survive 3/3 and 1/1; the intervention
  `native_transport_max_concurrent_connections: 512` removes the endpoint 3/3.
- **Root cause:** the per-connection bound (`native_transport_max_frame_size` 16 MiB) holds, but the only per-node bound on the
  number of such connections (`native_transport_max_concurrent_connections`) ships disabled (−1), there is no idle/auth timeout,
  and the pre-STARTUP cumulation buffer is charged by no Cassandra counter; nothing refuses before Netty's own direct limit, and
  5.0.9 escalates that limit's error to node death (`PreV5Handlers$ExceptionHandler` → `JVMStabilityInspector`).
- **Hypothesis tested:** at shipped defaults no connection limit and no idle timeout apply, so each unauthenticated v4
  connection that sends a 9-byte header declaring a 16 MiB − 9 B body and all but the last byte pins one 16 MiB chunk of
  Netty pooled direct memory that no Cassandra counter charges; about (MaxDirectMemorySize − per-arena chunks) / 16 MiB such
  connections reach Netty's direct limit. The open question this design settles by measurement: does the resulting
  `OutOfDirectMemoryError` kill only that connection or the node? (Source reading predicts the node: the pre-V5 exception
  handler passes it to `JVMStabilityInspector`, which forces a heap OOM and the shipped `-XX:OnOutOfMemoryError="kill -9 %p"`.)

## 1. Candidate

**Candidate row (quoted from `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`):**

> | OC-21 | 2026-11-16 | `native_transport_max_concurrent_connections-channelActive-limit--autonomous` | legacy | [lead list ×6 (blind, E2/E3/E4): `native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit`, `native_transport_max_frame_size-decode-bytesToDiscard`, `native_transport_max_concurrent_connections-channelActive-limit`, `…_per_ip-configureInitialPipeline-…`, `native_transport_max_concurrent_connections-configureInitialPipeline-…`, budget ledger heap (unlimited connections, 1.3 KB each); N14; queued as U2] At defaults (connection limits −1, no limit handler `PipelineConfigurator.java:240-245`, idle timeout 0) each unauthenticated connection can hold a partial pre-STARTUP envelope of up to 16 MiB in Netty pooled direct memory, charged by no in-flight limit: stage 4 measured 300 × 4 MiB = 1.2 GiB, so ≈ 256 connections reach 4 GiB. | CP-7, CP-6 | picked: U2 |

**Phase-1 constraint and check.** `native_transport_max_concurrent_connections` (and `…_per_ip`) is enforced by
`ConnectionLimitHandler.channelActive` (`ConnectionLimitHandler.java:84-96`), which closes a channel past the limit. The handler
is added to the pipeline only when either limit is > 0 (`PipelineConfigurator.java:240-245`); both default to −1
(`Config.java:289-290`), so at defaults the check is never in the pipeline. The per-connection bound is
`native_transport_max_frame_size` = 16 MiB (`Config.java:285`), enforced in `Envelope.Decoder.decode` (`Envelope.java:429-438`:
a frame of total length ≤ 16 MiB is accepted and waited for).

**Stage-4 measurement** ([recheck 2026-11-17, pc84](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17.md),
row C confirmed): at shipped defaults (heap 4 GiB, `MaxDirectMemorySize` 15,872 MiB = the `cassandra-env.sh` value for pc84),
k = 64 / 256 / 512 stalled pre-login connections (header declaring 16,777,207 B, all but the last byte sent) raised Netty's
limit-checked counter `PlatformDependent.usedDirectMemory()` by exactly (k + 64) × 16 MiB (64 per-arena chunks = 1 GiB fixed),
`held16` = k exactly (one whole 16 MiB chunk per connection), `memory.current` +16.07 MiB per connection; Cassandra counted
0 bytes in flight and 0 connected clients; nothing refused; the control (512 complete OPTIONS, idle) held only the 64 per-arena
chunks. By instruction the run stopped at 58 % of the limit: what happens at the limit was **not tested**. The campaign row's
open question (Netty `OutOfDirectMemoryError` per channel or fatal, "12034 handling") is the question this design answers.

**Source reading of the endpoint (stage 1, 2026-11-17; prediction, to be measured):**
- The pre-STARTUP pipeline is `[ConnectionLimitHandler only if a limit > 0] → IdleStateHandler only if idle timeout > 0 →
  Envelope.Encoder → InitialConnectionHandler (a ByteToMessageDecoder) → PreV5Handlers.ExceptionHandler`
  (`PipelineConfigurator.java:235-273`); the channel allocator is `CBUtil.allocator` = `new PooledByteBufAllocator(true)`
  (`PipelineConfigurator.java:138`, `CBUtil.java:60`), whose chunks are counted against Netty's own direct limit (=
  `MaxDirectMemorySize`, read at stage 4).
- An `OutOfDirectMemoryError` (a `java.lang.OutOfMemoryError`) from the cumulation growth (`ByteToMessageDecoder` catches only
  `Exception`) or from the epoll read-buffer allocation is delivered to `exceptionCaught` and reaches
  `PreV5Handlers.ExceptionHandler.exceptionCaught` (`PreV5Handlers.java:328-369`), which closes the channel (no stream id) and then
  calls `JVMStabilityInspector.inspectThrowable(cause)` (`:368`). With an empty `client_error_reporting_exclusions` (default,
  `Config.java:857`) nothing returns early.
- `JVMStabilityInspector.inspectThrowable` (`JVMStabilityInspector.java:105-131`) logs "OutOfMemory error letting the JVM handle the
  error", removes the shutdown hook and calls `forceHeapSpaceOomMaybe` (`:193-205`), which allocates `long[Integer.MAX_VALUE / 2]`
  until a real "Java heap space" OOM occurs (CASSANDRA-15214/17128), so the JVM's own OOM actions run:
  `-XX:+HeapDumpOnOutOfMemoryError` (`conf/jvm-server.options:120`) then `-XX:OnOutOfMemoryError="kill -9 %p"`
  (`conf/cassandra-env.sh:209`, passed by `bin/cassandra:195-203`).
- No special handling of Netty's `OutOfDirectMemoryError` exists in 5.0.9 (`grep -rl OutOfDirectMemoryError src/` → none),
  although CASSANDRA-12034 (Fixed 3.8) once handled it as "not a condition that destabilizes the system".
- Prediction: the first `OutOfDirectMemoryError` kills the node (SIGKILL), not just the connection.

**JIRA prior art** (read only; nothing posted). Survey `jira-oom-survey.csv` (604 rows) filtered for connection / frame /
handshake / authentication / direct terms; JIRA REST searches 2026-11-17: `text ~ "OutOfDirectMemoryError"` (1 hit),
`text ~ "unauthenticated" AND text ~ "memory"` (1), `text ~ "native_transport_max_concurrent_connections" AND (text ~ "memory" OR
text ~ "OOM")` (22, none on this mechanism), and the named keys below.

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-4265 *Limit total open connections (HSHA server)* | Won't Fix (2.0 beta 1) | same shape in the Thrift era: per-connection frame buffers × open connections → OOM; no total-connection limit added then |
| CASSANDRA-21756 *Adding authentication timeout* | Review In Progress (open) | proposes `native_transport_auth_timeout` (5 s) to bound how long a connection stays pre-READY; bounds time, not bytes; not in 5.0.9 |
| CASSANDRA-12034 *Special handling for Netty's direct memory allocation failure* | Fixed 3.8 | handled Netty `OutOfDirectMemoryError` by returning an error instead of passing it to `JVMStabilityInspector`; that handling is absent from 5.0.9 |
| CASSANDRA-15214, CASSANDRA-17128 | Fixed 4.0-beta4 / 4.1 | make every non-heap OOM reaching the inspector force a heap OOM so the JVM's OOM flags halt it (the predicted escalation) |
| CASSANDRA-20052 *Size of CQL messages is not limited in V5* | Fixed 5.0.3 | v5 multi-frame size; not the v4 pre-STARTUP decoder |
| CASSANDRA-16886 *Reduce native_transport_max_frame_size* | Fixed 4.1 | lowered the per-frame cap (256 → 16 MiB): bounds one connection, not the node |
| CASSANDRA-1743, CASSANDRA-4856 | Won't Fix / Invalid | per-connection buffers or threads × unlimited connections (Thrift) |

**Verdict: `known-open`** (design gap; the bound proposed in 21756 is open; 4265 Won't Fix). Not known-fixed, so this is a
real candidate, not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

A v4 client connects to port 9042 and, without STARTUP or authentication, sends a 9-byte header (version 0x04, flags 0,
stream 1, opcode 0x05 OPTIONS, body length 16,777,207) and 16,777,206 body bytes (all but the last). `InitialConnectionHandler`
(a Netty `ByteToMessageDecoder`, `InitialConnectionHandler.java:52-68`) cumulates the bytes in a buffer from `CBUtil.allocator`
(pooled direct, `CBUtil.java:60`, `PipelineConfigurator.java:138`), growing it in 4 MiB steps to 16 MiB = one whole pool
chunk; `Envelope.Decoder.decode` (`Envelope.java:424-442`) sees total length 16,777,216 ≤ `native_transport_max_frame_size`
(16 MiB) and waits for the rest (returns null). The frame stays in direct memory as long as the connection stays open. At
defaults no limit applies to the number of such connections (`PipelineConfigurator.java:240-245`, `Config.java:289-290`), no idle
timeout closes them (`Config.java:139`, `PipelineConfigurator.java:247-259`), and no in-flight limit charges them
(`native_transport_max_request_data_in_flight` is charged only after decode in the post-STARTUP handlers; stage 4 read 0).
Held direct memory is therefore k × 16 MiB plus up to one 16 MiB chunk per touched arena, until Netty's
`PlatformDependent.incrementMemoryCounter` throws `OutOfDirectMemoryError` at `MaxDirectMemorySize`; §1 gives the predicted
escalation from that error to node death. **Direction: unprotected configuration** (the control that applies when set,
`native_transport_max_concurrent_connections`, is disabled at its default; not a bypass) with unprotected accumulation of
pre-login frames. Technique note: [`default-convergence-playbook.md`](../../../default-convergence-playbook.md) ("Picking and
sizing": express capacity as multiplicity × footprint at fixed defaults and budget; vary multiplicity before anything else).

### 2.2 Protection map

| Domain | Holder, allocation, release | Counter (K) | Limit | At the limit |
|---|---|---|---|---|
| Pre-login cumulation (claimed holder) | `InitialConnectionHandler` cumulation buffer, `CBUtil.allocator` pooled direct, one 16 MiB chunk per stalled connection; released when the frame completes or the channel closes | none in Cassandra (stage 4: in-flight 0, `ConnectedNativeClients` 0) | per connection: `native_transport_max_frame_size` 16 MiB (holds: slack 0); per node: **none** at defaults | Netty `OutOfDirectMemoryError` at `MaxDirectMemorySize` |
| Connection count | channels on 9042 | `ConnectionLimitHandler.counter` only when installed | `native_transport_max_concurrent_connections` / `…_per_ip` = −1 (not installed) | (intervention arm only) channel closed in `channelActive`, ERROR "Exceeded maximum native connection limit" |
| Connection lifetime | channel | none | `native_transport_idle_timeout` = 0 ms (no `IdleStateHandler`) | — |
| Per-arena pool chunks | one 16 MiB chunk kept per direct arena touched by an event-loop thread (64 `EpollEventLoopGroup` threads = 2 × 32 cores) | Netty pool metric | arenas = min(2 × cores, D / 16 MiB / 6) | part of the same Netty counter |
| Netty direct budget | all `CBUtil.allocator` chunks (`allocateDirectNoCleaner`) | `PlatformDependent.usedDirectMemory()` (U, independent of Cassandra's K) | `PlatformDependent.maxDirectMemory()` = `MaxDirectMemorySize` (no `io.netty.maxDirectMemory` set) | `OutOfDirectMemoryError` thrown to the allocating handler |
| JDK direct (separate) | Cassandra `BufferPool`, internode, chunk cache (`ByteBuffer.allocateDirect`, `Bits` counter) | JDK `Bits` | `MaxDirectMemorySize` (a separate count of the same size) | not part of this mechanism; reported as baseline |
| Heap | ordinary heap; the forced `long[]` arrays of `forceHeapSpaceOomMaybe` | GC | `-Xmx` | "Java heap space" OOM → heap dump → `kill -9` |
| Process | RssAnon of the JVM | cgroup `memory.current` of the run scope | **guard only** `MemoryMax=64G`, `MemorySwapMax=0` (not the budget; must not bind) | a bind invalidates the run |

### 2.3 Configuration and budget audit

- **Build:** `pc84:/mydata/s4/cassandra-base` (copy of `systems/cassandra/source/` at 5.0.9, built with `ant build-test`
  2026-11-17, jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar`, Netty 4.1.130.Final, Byteman 4.0.20 in `build/lib/jars`). Stage 2
  makes one run copy `cp -a /mydata/s4/cassandra-base /mydata/s4/u2-oc21` and never builds in it.
- **Environment (checked read-only 2026-11-17 20:45 MST):** pc84 = node1.jason92-326528 (UMass), x86_64, 32 cores, 125 GiB RAM,
  8 GiB swap, `/mydata` 714 GiB free, Ubuntu 22.04, kernel 5.15, cgroup v2, OpenJDK 11.0.33, Python 3.10.12, `ulimit -Hn`
  1,048,576, `somaxconn` 4096, ports 32768–60999, `vm.overcommit_memory` 0, `Linger=no` for `jason92`; idle (no
  `CassandraDaemon`, nothing on 9042, no user scopes). Node clock is MST (UTC−7): node midnight = 02:00 America/New_York, when
  logback rolls `system.log`.
- **cassandra.yaml:** shipped file; overrides only `listen_address`/`rpc_address` 127.0.0.1 and the data / commitlog / hints /
  saved_caches / cdc_raw directories (environment). Intervention arm adds one line (§2.8). Nothing else changes.
- **Constraints at shipped defaults (V6), resolved:**

| Setting | Default | Resolved at A (heap 31,744 MiB) | Resolved at B (heap 4,096 MiB) | Role |
|---|---|---|---|---|
| `native_transport_max_frame_size` | 16 MiB | 16 MiB | 16 MiB | per-connection cap (holds) |
| `native_transport_max_concurrent_connections` | −1 | −1 (no handler) | −1 | node control, disabled |
| `native_transport_max_concurrent_connections_per_ip` | −1 | −1 | −1 | disabled |
| `native_transport_idle_timeout` | 0 ms | 0 | 0 | disabled |
| `native_transport_max_request_data_in_flight` / `_per_ip` | heap/10, heap/40 | 3,174 / 794 MiB | 410 / 102 MiB | not charged pre-STARTUP |
| `native_transport_receive_queue_capacity` | 1 MiB | 1 MiB | 1 MiB | v5 only, not on this path |
| `client_error_reporting_exclusions` | empty | empty | empty | would skip the inspector |
| Netty pool (`CBUtil.allocator`) | `PooledByteBufAllocator(true)` defaults | chunk 16 MiB, arenas min(64, 15,872/16/6 = 165) = **64** | arenas min(64, 2,048/16/6 = 21) = **21** | per-arena chunks |
| Netty direct limit | `MaxDirectMemorySize` | 16,642,998,272 B | 2,147,483,648 B | the OOM threshold |
| JVM OOM actions | `jvm-server.options`, `cassandra-env.sh` | `+HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError="kill -9 %p"`, G1, `AlwaysPreTouch` | same | escalation |

- **Budgets (V7), heap and JVM direct limit; standing rule (≥ 512 MiB meets V7 without review; 2 GiB ideal; search for the
  largest failing budget):**
  - **Condition A (primary, the largest):** budget **automatic** — `MAX_HEAP_SIZE` and `MAX_DIRECT_MEMORY_SIZE` **unset**, so
    `cassandra-env.sh:53-66` resolves for pc84 (125 GiB, G1): heap min(½ RAM, 31,744) = **31,744 MiB**, direct
    31,744 / 2 = **15,872 MiB** (the largest `MaxDirectMemorySize` the shipped script produces on any host: every host with
    ≥ 62 GiB RAM gets it). Claimed node: any ≥ 64 GiB host at shipped settings.
  - **Condition B (the 2 GiB ideal):** `MAX_HEAP_SIZE=4096M MAX_DIRECT_MEMORY_SIZE=2048M` = what the script resolves for an
    8 GiB host (½ and ¼ RAM). Explicit deployment budget. (On an 8 GiB host with fewer cores the arena count would be ≤ 21;
    recorded as a difference, it only lowers the per-arena overhead.)
  - **No container/cgroup limit is a budget here.** The run scope's `MemoryMax=64G`, `MemorySwapMax=0` is a guard for the
    controller only; a run where `memory.events` `max` or `oom_kill` > 0 is **invalid**, not a result.
- **Supporting settings (environment, disclosed):** `ulimit -n 100000` for node and client shells; `-XX:NativeMemoryTracking=summary`
  and the observe-only Byteman agent in instrumented arms (§2.6); client and probe on the same host over loopback, one source IP.

### 2.4 Ceiling arithmetic

No contract capacity exists for the node (connection limit off), so the sum of contract capacities is unbounded and the only
ceiling is Netty's limit. With D = `MaxDirectMemorySize` in 16 MiB chunks, a = arenas touched, k stalled connections:
Netty used ≈ (k + a) × 16 MiB (stage 4: exact). The first `OutOfDirectMemoryError` occurs when a chunk allocation would pass D:

| Condition | D (chunks) | a | Predicted k* (first OODME) | Client attempts k_max | Bytes sent by client |
|---|---|---|---|---|---|
| A | 16,642,998,272 B = 992 | 64 | 992 − 64 − ε ≈ **900–930** | 1,120 | ≤ 17.5 GiB over loopback |
| B | 2,147,483,648 B = 128 | ≤ 21 | 128 − 21 − ε ≈ **90–110** | 256 | ≤ 4 GiB |

(ε = 0–4 chunks for in-flight 4/8/12 MiB growth pieces and small allocations.) Process memory at A: pre-touched heap 31 GiB +
Netty ≤ 15.5 GiB + JDK direct and metaspace ≈ 1.5 GiB ≈ **48 GiB** peak, inside the 64 GiB guard and the 125 GiB node; B ≈ 7 GiB.
The heap dump at the forced heap OOM is ≤ the heap size (A ≤ 31 GiB, B ≤ 4 GiB) on `/mydata`, deleted after each run (§2.6).

### 2.5 Workload and environment

All on **pc84** (node, stall client, service probe, samplers), loopback 127.0.0.1, one measured node at a time, fresh node
directory per run (`/mydata/s4/u2-oc21/node-<run>`), removed after the run's excerpts are copied. Before starting: check
`ps -eo cmd | grep '[C]assandraDaemon'` is empty and 7000/7199/9042 are free; keep one ssh session to pc84 open for the whole
stage (Linger=no: a background `ssh pc84 'sleep 13000'` from the local node, killed at the end) because the node runs in a
`systemd-run --user --scope`. Launch the run script with `( setsid nohup bash run.sh … < /dev/null > /dev/null 2>&1 & )` and
poll its `commands.log` with bounded background polls.

**Harness to build in stage 2** (`harness/` in this case folder; copy to `pc84:/mydata/s4/u2-oc21/harness/` with `scp`; record
sha256 of each file in `commands.log`):

1. `run.sh` — derived from the stage-4 recheck harness
   `capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17/run.sh`
   (`make_node`, `start_node`, `wait_up`, `stop_node`, `nmt_other`, `amem`, cleanup trap, final process check). Changes:
   - `usage: run.sh <run-id> <cond A|B> <mode partial|complete> <k> <hold_s> <yaml_extra or -> <btm on|off>`; `C=/mydata/s4/u2-oc21`.
   - Budget: cond A → start the node with `env -u MAX_HEAP_SIZE -u MAX_DIRECT_MEMORY_SIZE` (automatic); cond B →
     `MAX_HEAP_SIZE=4096M MAX_DIRECT_MEMORY_SIZE=2048M`. Scope `-p MemoryMax=64G -p MemorySwapMax=0`. Record from the java
     command line `-Xmx`, `-Xms`, `-XX:MaxDirectMemorySize`, `OnOutOfMemoryError`, `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`.
   - `btm on`: `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -javaagent:…byteman-4.0.20.jar=script:ntfr.btm,sys:ntfr-probe.jar"`
     as in stage 4; `btm off`: no agent and no NMT.
   - yaml_extra (intervention only): appended to the node's `cassandra.yaml`; record the diff.
   - After `wait_up`: record `config.txt` as stage 4 (the `Node configuration:[…]` values for the settings in §2.3 plus
     `client_error_reporting_exclusions`), idle 30 s, sample `base`, start `service_probe.py` (§3 below) and wait 20 s, sample
     `P0`, then start `stall_client.py`.
   - **Sampler** (background, from base until the end): every 2 s append to `samples.tsv`: `t_ms`, node alive (`kill -0`),
     `memory.current`, `memory.events` `max`/`oom_kill`, `RssAnon` (`/proc/<pid>/status`), server-side established connections
     on 9042 (`ss -tnH state established '( sport = :9042 )' | wc -l`). With `btm on` also every 5 s one `NTFMEM` line via
     `nodetool version` (timeout 10 s; write `nt-fail` on failure) and every 10 s NMT `Other` committed delta.
   - **Endpoint watch** (every 2 s): first time any of `OutOfDirectMemoryError`, `java.lang.OutOfMemoryError`,
     `OutOfMemory error letting the JVM handle` appears in `logs/system*.log*` or `node-stdout.log` → `t_oom` (log the line);
     node process exit → `t_exit` and the launcher's exit status (`wait $PID`; 137 = SIGKILL).
   - **Arm end:** (a) partial-mode test arms: at node exit + 10 s; or 10 min after `t_oom` with the node alive (extend to 20 min
     only while a `*.hprof` in the node's log dir is still growing); or 5 min after the client printed `done` with no `t_oom`.
     (b) control / intervention arms: when the client has exited (it holds `hold_s` after its last connection) and one more
     sample is taken. Then stop the probe, stop the node (if alive), run the stage-4 final checks (no daemon, no client, no
     9042 listener, no `u2-oc21-*` scope).
   - **Collect** to `$C/logs/<run-id>/`: `commands.log`, `config.txt`, `jvm-args.txt`, `samples.tsv`, `client.out`, `probe.out`,
     `btm-lines.txt` (`^NTF`), `nmt-*.txt`, `system*.log*` (logback rolls at node midnight), `node-stdout.log`, `gc.log*` tail
     (last 300 lines), `first-oom.txt` = the first `ERROR` block containing `OutOfMemory` with 60 lines of stack (and the first
     `OutOfDirectMemoryError` line wherever it appears), `exit.txt` (exit status, `t_oom`, `t_exit`), `hprof.txt`
     (`ls -l --time-style=+%s` of `*.hprof`), `kernel.txt` (`sudo journalctl -k --since "<run start>" | grep -i -E 'oom|killed process'`).
     Then **delete** the `*.hprof` (only its listing is kept) and the node directory.
   - `summary.txt` per run (the readings table of §2.6, computed in Python, not `awk`).
2. `stall_client.py` — from the stage-4 `hold_prelogin.py`. `usage: stall_client.py <partial|complete> <host> <port> <k_max>
   <L> <rate_per_s> <hold_s>`. Connection i: `create_connection` (timeout 10 s), then partial: header `struct.pack('>BBhBI', 4, 0,
   1, 5, L)` and L − 1 zero bytes in 64 KiB `sendall`s; complete: header with length 0, read one response. Print one line per
   connection `conn i t_ms ok` or `conn i t_ms err=<repr>` (flush). Pace to `rate_per_s` connections per second from the start of
   each connection. Never abort on an error; stop early only after 20 consecutive connect failures (`ConnectionRefusedError`,
   i.e. the node is gone), printing `stop: node gone at i`. Then print `holding <n_ok> of <attempted>`, sleep `hold_s`, run the
   stage-4 liveness check (`alive / closed / unexpected`), close every socket **without** sending the last byte, print `done`.
   L = 16,777,207 in every partial arm; rate 10/s; launched with `ulimit -n 100000`.
3. `service_probe.py` — new (the authenticated service measure). Default `AllowAllAuthenticator`: STARTUP needs no credentials.
   v4 frames: header `>BBhBI` (version 0x04, flags 0, stream, opcode, length). STARTUP opcode 0x01, body = string map
   `>H` 1, then `>H` len + `CQL_VERSION`, `>H` len + `3.0.0`; expect READY 0x02. QUERY opcode 0x07, body = `>i` len +
   `SELECT release_version FROM system.local`, `>H` 0x0001 (ONE), `>B` 0x00; expect RESULT 0x08 (ERROR 0x00 → record code and
   message). Persistent connection: one QUERY every 0.5 s, 2 s timeout, line `P t_ms ok lat_ms` / `P t_ms err <e>`; on a broken
   connection try to reconnect every 5 s. Every 5 s also one **new** connection (STARTUP + one QUERY + close, 2 s timeouts):
   `N t_ms ok lat_ms` / `N t_ms err <e>`. Runs until killed.
4. `ntfr.btm` and `probe/ntfr/Probe.java` — copied **unchanged** from the stage-4 recheck harness (observe-only: `NTFMEM` fires
   only on `nodetool version`; `NTFDISCARD`/`NTFFAIL` fire only in the decoder's discard / fail branches, expected 0);
   `run.sh` compiles the probe and type-checks the rules (`TestScript: no errors`) as stage 4 does.
5. `selfcheck.py` — written **before** the first reading: re-parses every run's files and assigns the outcome row of §2.7;
   known-answer check on the shakedown files.

**Run matrix** (each run from a clean start: fresh node directory, fresh JVM, no data carried over):

| Run ID | Arm | Cond | Mode, k | Hold | yaml_extra | btm | Purpose / protocol item |
|---|---|---|---|---|---|---|---|
| SH | shakedown | B | partial, 256 | 60 | – | on | harness check end to end; not a reading |
| AT1–AT3 | **test** | A | partial, k_max 1,120 | 60 | – | on | V1 (≥ 3), V3, V5 at the largest budget |
| AC1–AC3 | **control** | A | partial, **448** | 180 | – | on | V2: same frames at low multiplicity, (448 + 64) × 16 MiB = 8 GiB = 51.6 % of D (margin 48 % ≥ 30 %) |
| AI1–AI3 | **intervention** | A | partial, k_max 1,120 | 60 | `native_transport_max_concurrent_connections: 512` | on | V4: bound multiplicity; ≤ 511 stalled + probe ⇒ ≤ (511 + 64) × 16 MiB ≈ 9.0 GiB < D |
| BT1–BT3 | test | B | partial, k_max 256 | 60 | – | on | budget search: the 2 GiB ideal, n/N |
| AU1 | test, uninstrumented | A | partial, k_max 1,120 | 60 | – | **off** | the endpoint without Byteman/NMT (`deployment` label) |
| AX1 | connection-count control | A | complete, 1,120 | 120 | – | on | connections alone (no frames) at k_max are safe |

Order (interleaved so a partial finish still gives matched sets): SH, AT1, AC1, AI1, AT2, AC2, AI2, AT3, AC3, AI3 (priority 1),
then BT1, BT2, BT3 (priority 2), then AU1, AX1 (priority 3). Intermediate budgets (4 / 8 GiB) are not run: k* is linear in D
(stage 4 exact), A is the maximum the script resolves, and B the ideal; a stage-2 session with time left may add one
`MAX_HEAP_SIZE=16384M MAX_DIRECT_MEMORY_SIZE=8192M` test run (the 32 GiB-host resolution) after priority 3.

### 2.6 Instruments

| # | What | How | When | Domain / role |
|---|---|---|---|---|
| O1 | Netty `usedDirectMemory`, `maxDirectMemory`, pool used, arenas, `held16`, chunks | `NTFMEM` Byteman line (stage-4 rule + `ntfr.Probe`) | every 5 s (btm on) | **U** for the claimed holder; `held16` = stalled frames |
| O2 | NMT `Other` committed delta | `jcmd VM.native_memory summary.diff` | every 10 s (btm on) | U, independent of Netty's own counter |
| O3 | `RssAnon`, cgroup `memory.current`, `memory.events` | `/proc`, cgroup files | every 2 s | process U; guard validity |
| O4 | server-side established connections on 9042 | `ss` | every 2 s | multiplicity, independent of the client's count |
| K1 | Cassandra in-flight bytes, `ConnectedNativeClients` | `NTFMEM` fields `inflight`, `clients` | every 5 s | **K** (predicted 0 and ≤ 2 = the probe) |
| E1 | first `OutOfDirectMemoryError`: message (`failed to allocate N byte(s) of direct memory (used: U, max: M)`), thread, stack | `system*.log*`, `node-stdout.log` | on event | V5 initiating failure; the stack shows the allocation site (pool → cumulation / epoll read) |
| E2 | escalation: "OutOfMemory error letting the JVM handle", "Force heap space OutOfMemoryError", "Java heap space", "Dumping heap to", `kill -9`, exit status | logs, `wait` | on event | the endpoint |
| S1 | service: probe `P` and `N` lines | `probe.out` | 0.5 s / 5 s | service before / after the event |
| G1 | GC log tail | `gc.log` | at end | heap OOM context |

The heap dump at the forced heap OOM shows only `forceHeapSpaceOomMaybe`'s `long[]` arrays, not the off-heap holder; V5's
"near-failure evidence of the holder" for direct memory is the last `NTFMEM` before `t_oom` (`held16` ≈ k, `nettyUsed` within
16 MiB × (a + few) of `nettyMax`) plus the `OutOfDirectMemoryError` message's own used/max numbers. The dump is listed and deleted.

**Per-run readings (`summary.txt`):** resolved `-Xmx` / `MaxDirectMemorySize` / `nettyMax` / arenas; client `ok` connections
before `t_oom` (= k*); last `NTFMEM` before `t_oom` (`nettyUsed`, `held16`, `inflight`, `clients`); first-OODME message, thread
and top 15 frames; escalation lines and their times; exit status and `t_exit − t_oom`; probe: last `P ok` before `t_oom`, first
`P err` after, longest run of consecutive `P err` and `N err` while the node was alive; peak `RssAnon` and `memory.current`;
`memory.events`; NTFDISCARD/NTFFAIL counts; for AI: `Exceeded maximum native connection limit` count, client `err` count,
max `held16`, max O4.

### 2.7 Predicted response, outcome rows and stopping budget

Predictions (written before any reading):

- **P-A (AT, AU):** resolved `-Xmx31744M`, `MaxDirectMemorySize` 16,642,998,272 = `nettyMax`, arenas 64. Netty used rises
  16 MiB per stalled connection (O1 slope 1.00 × 16 MiB, O2 and O3 within 10 %), `inflight` 0, `clients` ≤ 2. The first
  `OutOfDirectMemoryError` occurs at **k* ∈ [900, 930]** on a native-transport event-loop thread from `CBUtil.allocator`; it
  reaches `PreV5Handlers$ExceptionHandler` and `JVMStabilityInspector`; "Force heap space OutOfMemoryError" follows, then
  "java.lang.OutOfMemoryError: Java heap space", a heap dump, and `kill -9`; the node **exits by SIGKILL (status 137) within
  10 min of `t_oom`**; the probe is `ok` up to `t_oom` and fails from `t_exit` on. No cgroup event.
- **P-B (BT):** `-Xmx4096M`, `MaxDirectMemorySize` 2,147,483,648, arenas 21; k* ∈ [90, 110]; same escalation and exit.
- **P-C (AC):** 448 frames held 180 s: `held16` = 448, Netty used = (448 + a) × 16 MiB ≤ 8.0 GiB, no OOM line, node alive,
  probe `P` ok ≥ 99 % and `N` ok 100 %.
- **P-I (AI):** ERROR "Exceeded maximum native connection limit of 512" logged; client `err` ≥ 600 of 1,120; `held16` ≤ 511,
  O4 ≤ 512, Netty used ≤ (511 + 64) × 16 MiB ≈ 9.0 GiB; no OOM line; node alive; probe `P` ok ≥ 99 %; `N` may fail while 512
  connections are open (recorded as the intervention's cost, not a failure).
- **P-X (AX):** Netty used ≤ 64 × 16 MiB + 64 MiB; no OOM; alive.

| Row | Observation (test arms) | Endpoint / meaning | Verdict contribution |
|---|---|---|---|
| **E1** (predicted) | first OODME at k* with `held16` ≈ k, then forced heap OOM and node exit (SIGKILL / any exit) | JVM direct-buffer OOM (Netty limit) escalating to node death | with V1–V4 met at A: **true positive** (`verified-OOM · deployment`, unprotected configuration) |
| E2a | OODME logged, node alive 10 min later, probe `P` and `N` all fail for ≥ 60 s while alive | OOM contained per channel but service lost | `verified-gap · service-loss` → **retry** |
| E2b | OODME logged, node alive, probe keeps being served (no ≥ 60 s outage) | the Netty limit acted as a per-connection rejection | with AC/AI valid: **false positive** (protective rejection at the direct limit) |
| E3 | no OOM line by k_max with all connections held and Netty used < D | mechanism did not reach the limit (e.g. chunks freed) | **retry** (state why) |
| E4 | connections refused or closed by the node before k* without OOM | an unexpected bound on k | record which; **retry** unless the bound is a default control (then false positive) |
| E5 | node dies without an OODME first (other error) | other failure | record cause; **retry** |
| I | guard bound (`memory.events` max/oom_kill > 0), wrong config, client never reached 100 connections, probe never got READY | invalid run | repeat once; else retry |

The verdict needs E1 (or E2) in ≥ 3 of AT1–AT3 (n/N reported) **and** AC1–AC3 surviving (P-C) **and** AI1–AI3 removing the
endpoint (P-I). BT n/N is reported as the 2 GiB budget's result; AU1 supports the `deployment` label. If AT gives mixed rows,
add AT4–AT5 before anything in priority 2.

**Stopping budget.** Per run: the arm-end rules of §2.5 (at most ≈ 30 min for a test run in the worst case). No escalation
after an OOM (no larger k, no second attempt in the same JVM). Whole stage 2 (time plan, America/New_York, stage 2 starting
≈ 23:15 on 2026-11-17):

| Block | Estimate | Planned window |
|---|---|---|
| Read case file, check hash and node, run copy, write and sync harness, `selfcheck.py` | 35–45 min | 23:15–00:00 |
| SH shakedown (B, ≈ 4 min) and fixes | 10 min | 00:00–00:10 |
| Priority 1: AT ×3 (≈ 6–8 min each: start with 31 GiB pre-touched heap ≈ 1 min, idle and probe 1 min, ≈ 93 s to k*, forced OOM + ≤ 31 GiB dump + kill ≤ 5 min), AC ×3 (≈ 6 min), AI ×3 (≈ 5 min) | 55–65 min | 00:10–01:15 |
| Priority 2: BT ×3 (≈ 3.5 min each) | 11 min | 01:15–01:30 |
| Priority 3: AU1, AX1 | 12 min | 01:30–01:45 |
| Self-check, §3/§4, write-backs, cleanup | 20 min | 01:45–02:05 |

Hard rules: start no new run after **02:00**; at **02:15** stop whatever runs (node, client, probe, samplers, ssh keeper),
remove node directories, confirm nothing is left; everything finished before **02:30** America/New_York, 2026-11-18. If priority 1
is not complete by 01:40, drop priorities 2–3 and finish priority 1; an incomplete priority 1 is a **retry** with the reason.

### 2.8 Controls and intervention

- **Matched control (V2), AC1–AC3:** same build, same automatic budget, same frames (16 MiB − 9 B declared, all but one byte
  sent), same client, probe and instruments, at k = 448 (low multiplicity, 48 % margin to D), held 180 s (longer than a test
  arm's time from k = 448 to k*). Shows the frames and the probe alone, below the limit, cause no failure; the endpoint
  depends on multiplicity reaching D.
- **Causal intervention (V4), AI1–AI3:** the node control that defaults to off, set: `native_transport_max_concurrent_connections:
  512` (the yaml line; a custom value only in this arm, as V6 allows), same client attempting k_max = 1,120 at the same rate. If
  the endpoint is removed in 3/3 with the limit rejecting the excess, the multiplicity of stalled pre-login connections is the
  cause. Throughput cost recorded: rejected stall connections (intended) and any `N` probe failures while saturated.
- **Supporting control AX1:** 1,120 complete-OPTIONS idle connections (no held frames) — connection count alone does not exhaust
  the budget.
- **Not used:** a diagnostic patch (none needed); `native_transport_idle_timeout` as an alternative intervention (it would also
  close the probe's idle connections between queries only if idle longer than the timeout; left for a later run if the limit
  intervention is ambiguous).

`sha256 of §1–§2 at freeze: 5376be17101fe834f7c3cae9bb2c294e2441092bf449827d52ca9200b824ad35` (computed as `awk '/^## 1\. Candidate/{p=1} /^`sha256 of §1–§2 at freeze/{p=0} p' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-17) · amendments after the freeze: none.

## 3. Runs (stage 2)

**Resume note (2026-11-18 02:54–03:10 America/New_York, fresh stage-2 session).** The first stage-2 session ran the whole
run matrix on pc84 (2026-11-17 20:53–22:03 node time MST = 22:53–00:03 America/New_York) and was then cut off by an API usage
limit before it wrote §3–§4. Nothing was running when this session started (no `CassandraDaemon`, no client/probe/matrix
process, no listener on 7000/7199/9042, no `u2-w1-*` scope; checked 00:54 node time). The freeze hash of §1–§2 was re-checked:
`5376be17…ad35`, unchanged. Every run directory `pc84:/mydata/s4/u2-w1/logs/<run>/` was inspected: all 16 runs (SH, AT1–3,
AC1–3, AI1–3, BT1–3, AU1, AX1, M1) have their complete file set, a `final: daemon=0 client=0 probe=0 9042=0 scopes=0` line
and a `summary.txt`; `selfcheck.py` (sha256 `071da824…`, the one the runs used) was re-run over all 16 and reproduces every
OUTCOME row (`logs/selfcheck-resume-2026-11-18.txt`). **Reused: everything** (build copy, harness, all 16 runs); **nothing was
redone and no new run was started**, because no arm had an incomplete log. The node harness files are byte-identical to
`harness/` here (sha256 compared).

**Environment.** pc84 (node1.jason92-326528, UMass), x86_64, 32 cores, 125 GiB RAM, 8 GiB swap, Ubuntu 22.04, kernel
5.15.0-203-generic, cgroup v2, OpenJDK 11.0.33, Python 3.10.12. Build: run copy `pc84:/mydata/s4/u2-w1` (a `cp -a` of
`/mydata/s4/cassandra-base`, Cassandra 5.0.9, Netty 4.1.130.Final, Byteman 4.0.20; never rebuilt). Node, stall client and
service probe on pc84 over loopback 127.0.0.1. Each run in `systemd-run --user --scope -p MemoryMax=64G -p MemorySwapMax=0`
(guard only), `nofile` 100,000. `cassandra.yaml`: shipped, plus addresses/directories only (`logs/AT1-commands-ntfmem-samples.txt`
has the diff); AI arms add `native_transport_max_concurrent_connections: 512`. `config.txt` of every run read back the §2.3
settings at default (`native_transport_max_concurrent_connections=-1`, `…_per_ip=-1`, `idle_timeout=0ms`, `max_frame_size=16MiB`,
`client_error_reporting_exclusions` empty, `AllowAllAuthenticator`). JVM flags as shipped (G1, `AlwaysPreTouch`,
`HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError="kill -9 %p"`, `io.netty.allocator.maxOrder=11`).
**Resolved budgets:** A (automatic, `MAX_HEAP_SIZE`/`MAX_DIRECT_MEMORY_SIZE` unset): `-Xms/-Xmx31744M`,
`-XX:MaxDirectMemorySize=15872M` = 16,642,998,272 B = Netty `maxDirectMemory`, 64 arenas; B: `-Xmx4096M`,
`MaxDirectMemorySize` 2,147,483,648 B, 21 arenas; M (optional 32 GiB-host resolution): `-Xmx16384M`, `MaxDirectMemorySize`
8,589,934,592 B, 64 arenas. Logs (all runs) at `pc84:/mydata/s4/u2-w1/logs/` (`<run>/`, `<run>.console`, `matrix-*.log`);
heap dumps listed in `hprof.txt` then deleted; node directories removed.

| Run | Arm | Budget (heap / direct) | Load reached | Endpoint | Key reading (U vs K) |
|---|---|---|---|---|---|
| SH | shakedown (not a reading) | B 4 / 2 GiB | 106 stalled (129 attempted) | OODME → forced heap OOM → `kill -9`, rc 137 | harness check passed; first summary printed "after 0" (selfcheck read log times as local; fixed to UTC before AT1; the re-run gives 106) |
| AT1 | test | A 31 / 15.5 GiB | **927** stalled ok, 952 attempted | OODME (used = max = 16,642,998,272) on `epollEventLoopGroup-5-57` → "letting the JVM handle" → "Force heap space" → `Java heap space` → 8.8 GB dump (32 s) → `kill -9`; **rc 137, t_exit − t_oom 40 s** | last NTFMEM 3 s before: `nettyUsed` 15,408 MiB, `held16` 898, chunks 962 (= held16 + 64), headroom 464 MiB; NMT Other Δ max 15,856 MiB (= 991 chunks); RssAnon peak 47.7 GiB; K: `inflight` 0, `clients` ≤ 1 (the probe); O4 max 929 |
| AT2 | test | A | 927 / 952 | same, rc 137, 40 s | held16 898, `nettyUsed` 15,408 MiB, NMT Δ 15,856 MiB, RssAnon 47.7 GiB, inflight 0 |
| AT3 | test | A | 927 / 952 | same, rc 137, 40 s | held16 897, 15,392 MiB, NMT Δ 15,856 MiB, RssAnon 47.7 GiB, inflight 0 |
| AU1 | test, uninstrumented (no Byteman, no NMT) | A | 927 / 952 | same OODME message, same escalation, rc 137, 42 s | RssAnon 47.7 GiB, O4 929 (no NTFMEM by design) |
| AC1 | control (448 frames, 180 s hold) | A | 448 / 448 held, all alive | **none**, node alive | held16 448, `nettyUsed` max 8,208 MiB (= 448 + 64 chunks + 16 MiB), NMT Δ 8,193 MiB; probe P 494/0, N 50/0 |
| AC2 | control | A | 448 / 448 | none, alive | same readings; probe P 494/0, N 50/0 |
| AC3 | control | A | 448 / 448 | none, alive | same readings; probe P 498/0, N 50/0 |
| AI1 | intervention (`max_concurrent_connections: 512`) | A | 511 held, **609 refused** of 1,120 | none, alive | held16 max 511, `nettyUsed` max 9,216 MiB, O4 max 512; "Exceeded maximum native connection limit of 512" (NoSpamLogger, 1/min: 2 lines in system.log); probe P 390/0; N 15 ok / 24 err (refused while the limit was full, longest 115 s) |
| AI2 | intervention | A | 511 / 1,120 | none, alive | same; N err span 115 s |
| AI3 | intervention | A | 511 / 1,120 | none, alive | same; O4 max 513; N err span 115 s |
| BT1 | test | B 4 / 2 GiB | **106** / 129 | OODME (used = max = 2,147,483,648) → forced heap OOM → dump → `kill -9`, rc 137, 2 s | last NTFMEM 5 s before: held16 51, chunks 72 (= 51 + 21); peak RssAnon 6.5 GiB; inflight 0 |
| BT2 | test | B | 106 / 129 | same, rc 137, 1 s | held16 53 at last sample, inflight 0 |
| BT3 | test | B | 106 / 129 | same, rc 137, 2 s | held16 52 at last sample, inflight 0 |
| AX1 | connection-count control (complete OPTIONS, idle, 120 s) | A | 1,120 / 1,120 held | none, alive | held16 0, `nettyUsed` max 1,040 MiB (64 arena chunks); probe P 510/0, N 51/0 |
| M1 | optional budget run | M 16 / 8 GiB | **447** / 471 | OODME (used = max = 8,589,934,592) → same escalation, rc 137, 10 s | held16 414 at last sample, chunks 478 (= 414 + 64); RssAnon 24.6 GiB |

Readings common to every run: `memory.events` `max` 0 and `oom_kill` 0 (the guard never bound; peak `memory.current` 56.2 GiB
in A test arms, including page cache from writing the dump), `kernel.txt` 0 OOM lines (the death is the JVM's own `kill -9`,
not a kernel/cgroup kill), NTFDISCARD 0 and NTFFAIL 0 (the frame-size check never fired: each frame was legal). Growth is exact:
between two AT1 samples `held16` rose 544 and `nettyUsed` 9,126,805,504 B = 544 × 16 MiB (slope 1.00); the first OODME falls
at k* = D/16 MiB − arenas − 1 in every budget (A: 992 − 64 − 1 = 927; B: 128 − 21 − 1 = 106; M: 512 − 64 − 1 = 447; the one
extra 16 MiB is Netty usage outside the pool present from start). Service while alive: in A test arms the persistent probe was
`ok` up to t_oom and then timed out for 38.6–40.5 s (heap dump) until the kill; in B ≤ 0.8 s. The OODME arrives through
`ByteToMessageDecoder.cumulate` → `PooledByteBuf.capacity` reallocation → `PoolArena.newChunk` → `PlatformDependent.incrementMemoryCounter`
on an epoll event-loop thread; it is logged by `ExceptionHandlers.java:181` ("Unknown exception in client networking") and passed
to `JVMStabilityInspector.inspectThrowable` (`PreV5Handlers.java:367-368`); three event-loop threads (5-57/58/59) each hit
it within 190 ms (`logs/AT1-initiating-failure.txt`, `logs/BT1-initiating-failure.txt`).

Predictions vs readings: P-A held (k* 927 ∈ [900, 930]; SIGKILL within 10 min, 40 s); P-B held (106 ∈ [90, 110]); P-C held
(no OOM, probe 100 %); P-I held (limit message, 609 ≥ 600 refused, held16 ≤ 511, ≤ 9.0 GiB, probe P 100 %; N refused while
saturated = the intervention's cost); P-X held. Outcome row **E1** in 3/3 AT, 1/1 AU, 3/3 BT, 1/1 M.

**Deviations from the design (all from the first stage-2 session's logs; none changes a constraint, budget or workload):**
- Run copy `/mydata/s4/u2-w1` (scope names `u2-w1-*`) instead of `/mydata/s4/u2-oc21`; same `cp -a` of `cassandra-base`.
- Orchestration helpers `harness/matrix.sh` (runs a list in order; refuses to start a run after 02:00 America/New_York or when
  a `STOP` file exists) and `harness/chain-p23.sh` (starts priorities 2–3 after priority 1) were added; the order became SH,
  AT1, AC1, [AI1 invalid], AT2, then (after a STOP to fix AI) AI1, AC2, AI2, AT3, AC3, AI3, BT1–3, AU1, AX1, M1, so AI1 ran
  after AT2 rather than before it. Matched sets are unaffected.
- **AI1 first attempt invalid** (row I): `matrix.sh` turned the `_` used as a space placeholder into spaces inside the key, the
  yaml line read `native transport max concurrent connections: 512`, and Cassandra refused to start ("Invalid yaml"). No node
  ran; the placeholder was changed to `@` and AI1 repeated from a clean start (`logs/AI1-invalid-harness/`).
- **A duplicate launch of the p1b list** at 21:16:36 (node time) aborted in every run's pre-check ("a Cassandra daemon is already
  running": the `ps | grep '[C]assandraDaemon'` check matched some other process command line; the user journal shows no Cassandra
  scope started between AT2's end, 21:09:33, and the real p1b AI1 start, 21:16:56). No node started; its files are kept under
  `logs/aborted-race/`. No two measured runs overlapped (each valid run's pre-check found 0 daemons, and the matrix runs serially).
- The ssh keeper and the stopping-time plan of §2.7 were overtaken by the interruption; all runs ended by 00:04 America/New_York,
  inside the 02:00 rule. The optional M run (16 / 8 GiB) was run once (1/1).
- `kill9` counts of 2 in control arms are the `OnOutOfMemoryError` flag text in the logged JVM arguments, not kills.

**Excerpts in `logs/`:** `summaries-all-runs.txt` (every run's `summary.txt`), `selfcheck-resume-2026-11-18.txt`,
`matrix-logs.txt` (matrix, aborted and invalid launches), `AT1-initiating-failure.txt`, `BT1-initiating-failure.txt`,
`AT1-commands-ntfmem-samples.txt` (commands.log, every NTFMEM line, sampler tail), `AI-AC-excerpts.txt`.

**Left on the node:** `pc84:/mydata/s4/u2-w1` (run copy with build, harness, full logs of all runs; 478 MiB on
`/mydata`); no heap dumps, no node data directories, no process, no scope. `/mydata/s4/cassandra-base`, `src-5.0.9`, `ntfs-rc`
predate this case and were not touched.

## 4. Conclusion (stage 2)

- **Verdict:** **`true positive`** ([`oom-agent-playbook.md`](../../../oom-agent-playbook.md)).
- **Protocol status (detail):** `verified-OOM · deployment`, **unprotected configuration** (`native_transport_max_concurrent_connections`
  disabled at its default −1; no idle/auth timeout) with unprotected accumulation of pre-login frames; endpoint a JVM
  direct-buffer OOM (Netty `OutOfDirectMemoryError`) escalated by Cassandra to a forced heap OOM and the shipped `kill -9`.

| | Requirement | Evidence |
|---|---|---|
| V1 | ≥ 3 runs reach the endpoint | AT1–AT3 3/3 (k* = 927 each), plus AU1 1/1, BT1–BT3 3/3, M1 1/1 |
| V2 | matched control survives ≥ 3 | AC1–AC3 3/3 (same frames, 448 = 51.6 % of D, 180 s, probe 100 %); AX1 1/1 (1,120 connections without frames) |
| V3 | U measured independently of K | U: Netty `usedDirectMemory` (1.00 × 16 MiB per stalled connection), NMT Other Δ (991 chunks at failure), RssAnon 47.7 GiB, `held16`; K: Cassandra in-flight 0, connected clients ≤ 1 |
| V4 | intervention removes the endpoint ≥ 3 | AI1–AI3 3/3 at the same 1,120-attempt load: 609 refused, held16 ≤ 511, ≤ 9,216 MiB, node alive; cost: new legitimate connections refused while the limit is full |
| V5 | initiating failure + holder near failure | first OODME with thread and full stack (cumulation reallocation on an epoll event loop), "letting the JVM handle" → "Force heap space" → `Java heap space` → dump → `kill -9 %p`, rc 137; last NTFMEM 3 s before: held16 898 of 962 chunks, 464 MiB headroom; OODME message used = max |
| V6 | constraints at shipped defaults | `config.txt` of every test run: frame size 16 MiB, both connection limits −1, idle timeout 0, exclusions empty |
| V7 | acceptable budget | A = the budget `cassandra-env.sh` resolves itself for pc84 and any ≥ 64 GiB host (heap 31,744 MiB, direct 15,872 MiB, the largest the script produces); ≥ 512 MiB standing rule; also 2 GiB direct (3/3) and 8 GiB direct (1/1). No container limit is part of the endpoint (guard never bound) |

Conditions label `deployment`: every setting shipped or environment-only (addresses, directories, `nofile` 100,000); AU1 without
Byteman/NMT reaches the same endpoint at the same k*; the only fault is an external client behaviour (stall after sending all
but one byte of a legal frame).

- **Reason:** At shipped defaults and the automatically resolved budget (heap 31,744 MiB, `MaxDirectMemorySize` 15,872 MiB =
  16,642,998,272 B), each unauthenticated v4 connection holding a legal 16 MiB frame minus one byte pinned exactly one 16 MiB
  Netty pool chunk that no Cassandra counter charged (in-flight 0), and the 927th such connection raised `OutOfDirectMemoryError`
  (used = max) in 3/3 runs (and 1/1 uninstrumented); `PreV5Handlers$ExceptionHandler` passed it to `JVMStabilityInspector`, which
  forced a heap OOM, and the shipped `-XX:OnOutOfMemoryError="kill -9 %p"` killed the node 40 s later (rc 137, no kernel/cgroup
  event). The failure point is exact arithmetic, k* = D/16 MiB − arenas − 1 (927 at 15.5 GiB, 106 at 2 GiB 3/3, 447 at 8 GiB 1/1),
  so every budget the shipped script can resolve fails, at about 14.5 GiB of client-sent bytes for the largest. 448 held frames
  (51.6 % of the limit, 3/3) and 1,120 frameless connections (1/1) left the node healthy, and setting the disabled control
  `native_transport_max_concurrent_connections: 512` removed the endpoint 3/3 (511 held, 609 refused, ≤ 9.0 GiB). Limits of
  attribution: one source IP over loopback; `AllowAllAuthenticator` (the frames are sent before STARTUP, so a password
  authenticator should not change the path, but it was not run); with a 2 GiB direct budget the 512 limit would not be enough
  (k* = 106), so the intervention shows causality, not a safe default value.
- **For retry:** not applicable.
- **Pattern:** covered by CP-7 (per-connection frame cap × unbounded connections) with CP-6 (nothing refuses before the
  direct limit; the JVM error is the enforcement) and CP-8 (the node-level limit ships off); no new pattern needed.
