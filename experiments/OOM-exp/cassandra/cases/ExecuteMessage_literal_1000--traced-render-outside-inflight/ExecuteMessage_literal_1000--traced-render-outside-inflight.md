# B11 — ExecuteMessage literal `1000` (trace bound-value cut): a traced EXECUTE renders each bound blob to ≈ 6× its size of heap before the cut, outside the in-flight byte count  <!-- file: cassandra/cases/ExecuteMessage_literal_1000--traced-render-outside-inflight/ExecuteMessage_literal_1000--traced-render-outside-inflight.md -->

| Field | Value |
|---|---|
| Case ID | `B11` (bypass, accounting omission; README "ID prefixes") |
| From | `OC-38` of the phase 1 OOM candidate list |
| Phase-1 case file | [`ExecuteMessage_literal_1000-traceQuery-1000--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md); stage 4: [`results/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9), OpenJDK 11.0.33 (aarch64, Ubuntu 22.04) |
| Stage 1 (design) | OOM-agent stage-1 session (workflow wave 1), 2026-11-17 ~22:45–23:20 America/New_York |
| Stage 2 (verify) | fresh OOM-agent stage-2 session (workflow wave 1), 2026-11-17 22:55 – 2026-11-18 ~00:05 America/New_York, node `ms0611` (aarch64) |
| Verdict | **`retry`** (protocol status `candidate` · mixed: heap OOM at defaults and 2 GiB 3/3, control 0/3, intervention 0/3, but the largest holder at failure is the slow-query monitor's queue, not the render; design row O3) |

## Summary

- **Conclusion (stage 2): `retry`.** At shipped defaults and a 2 GiB heap, 13 connections (one per IP, K ≤ C) each sending
  traced 16 MB EXECUTEs ended in `OutOfMemoryError: Java heap space` 3/3 (15–22 s), the same frames untraced survived 3/3 and a
  build that renders only the first 1000 bytes survived 3/3. 4 GiB at N = 26 and 8 GiB at N = 256 did not fail (0/1 each), so
  the largest failing budget is 2 GiB. The design's attribution test failed (row O3): in every dump the largest holder was
  not the render buffers (32–38 % of the heap) but ≈ 51 completed read commands (≈ 780 MiB, 42–49 %) kept with their 16 MB
  bound values by the slow-query monitor (`MonitoringTask`), and 1 of 3 initiating errors came from that monitor's own
  uncut render of a value.
- **Root cause (as measured):** two uncharged holders, both outside the in-flight byte count. (1) `traceQuery` renders each
  bound blob to ≈ 4–6 × its size before the 1000-char cut. (2) Because the render makes traced requests slow (median 1.2 s >
  `slow_query_log_timeout` 500 ms), the slow-query monitor keeps up to 50 finished `ReadCommand`s, each with its bound value,
  for up to 5 s. It then renders each one uncut through `toCQLString`. The OOM needs both, so the case is mixed, not the
  pure render bypass the design claimed.
- **Hypothesis under test:** when a client sets the tracing flag on a prepared EXECUTE, `ExecuteMessage.traceQuery`
  renders every bound value to its full CQL literal before the 1000-char cut. For a blob of S bytes that is a `char[2S]`
  (4S bytes), a Latin-1 `String` (2S) and the `"0x" + hex` concatenation (2S), on top of the decoded heap copy of the value
  (S). The native-transport in-flight limits charge only the S body bytes, and no counter charges the render. With one
  traced 16 MB request on each of N client connections (each from its own IP, so the per-IP limit is never exceeded), N
  rendering requests hold ≈ 5–7 × 16 MB of humongous heap each, and the heap fails at a multiplicity that grows with the heap.
  Each such connection gets its request processed even above the global limit.

## 1. Candidate

**Candidate row (quoted from `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`, status as
handed to this session):**

> | OC-38 | 2026-11-16 | `ExecuteMessage_literal_1000-traceQuery-1000--autonomous` | legacy | [lead list, blind, E1] A traced EXECUTE renders each bound blob to ≈ 6 × its size of live heap (char[], then two String copies) before the 1000-character cut, outside the in-flight byte count; tracing is client-chosen, so at an 8 GiB heap ≈ 51 concurrent 16 MiB traced requests hold ≈ 4.8 GiB vs ≈ 0.8 GiB counted. | CP-12, CP-1 | picked: B11 |

**Phase-1 case (stage 3).** The constraint is a hard-coded literal `1000` in `ExecuteMessage.traceQuery`
(`ExecuteMessage.java:231-232`): each bound value's CQL literal is cut to 1000 chars + `...'` before it goes into the
`parameters` map of the `system_traces.sessions` row. Stage 3 estimated `positive` for what is persisted and named the
transient heap as uncapped: "the full literal is built first (`:230`)" (A3 step 6).

**Stage 4 (advisor's Mac, 2026-10-27, outcome class true positive for the persisted cap).** Unit and cluster tiers
confirmed the cut: stored value 1004 chars for every S ≥ 500 B, sessions bytes flat (≈ 1.1 KB per request) while the uncut
unprepared QUERY grows linearly. The informational JFR reading T recorded 60 allocations ≥ 1 MiB with a `toCQLLiteral`
frame for 20 traced 1 MiB EXECUTEs (3 per request), e.g. a 4.0 MB `char[]` in `Hex.bytesToHex` ←
`BytesSerializer.toCQLLiteralNonNull` ← `ExecuteMessage.traceQuery` line 230. Stage 4 did not measure liveness, concurrency
or an endpoint; its note S2 left "the transient heap of the full literal could be a case of its own" to a later stage.
That is this case.

**JIRA prior art (read only; nothing posted).** Survey file
`capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (604 rows): no row on trace rendering; nearest
patterns are CASSANDRA-2849 (Fixed 0.8.5: a validation exception hex-encoded the entire value, potential OOM) and
CASSANDRA-14925 (Fixed 3.0.24/3.11.10/4.0: `DecimalSerializer.toString()` usable as an OOM attack): the same shape (render an
unbounded value to a string), at other sites, both fixed. JIRA REST search (2026-11-17, `project = CASSANDRA AND …`):
`text ~ "traceQuery"` → 2 hits (CASSANDRA-7378 Won't Fix, autoprepare; CASSANDRA-19880 Fixed 5.0.1, tracing with `unset()`
on a map: a correctness bug in the same loop, not memory); `text ~ "bound_var"` → CASSANDRA-11719 (Fixed 3.8, "Add bind
variables to trace": the review comment asked "Since boundValue can become quite big, I'd prefer to limit it to 1000 chars",
and the limit was applied to the stored string after rendering); `text ~ "toCQLLiteral"`, `"tracing" AND "OutOfMemoryError"`,
`"trace" AND "bound values"`, `"tracing" AND "large blob"`, `"bytesToHex" AND "memory"` → no report of render memory.
**Verdict: `new`** (the cap's intent, per CASSANDRA-11719, was size; the render before it is not reported).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

- `Message.Request.execute` (`Message.java:237-241`) traces when the client sets the frame's TRACING flag (v4 header flag
  `0x02`); no permission or server setting is needed. `ExecuteMessage.execute` then calls `traceQuery` (`ExecuteMessage.java:160-161`)
  **before** `processPrepared`, so the render happens for every traced prepared statement, whatever it does next.
- `traceQuery` (`ExecuteMessage.java:213-239`), for each bound value, renders `cs.type.asCQL3Type().toCQLLiteral(bytes)` (`:230`)
  and only then cuts it (`:231-232`). For a blob: `BytesSerializer.toCQLLiteralNonNull` = `"0x" + toString(...)`
  (`BytesSerializer.java:65-68`) → `ByteBufferUtil.bytesToHex` (`ByteBufferUtil.java:635-639`, the value is heap-backed) →
  `Hex.bytesToHex(byte[],int,int)` allocates `char[2S]` (`Hex.java:78`) and `Hex.wrapCharArray` (`Hex.java:109-135`): on JDK 11
  the JDK-8 `String(int,int,char[])` constructor does not exist, so it falls back to `new String(c)` (compact Latin-1 `byte[2S]`,
  while `char[2S]` is still live); then the concatenation allocates another `byte[2S+2]`. Allocated per value: 8S bytes;
  peak simultaneously live: 6S (char[] + hex) then 4S (hex + concat). Stage 4's JFR saw exactly these three allocations.
- The value itself was copied from the frame into a heap `byte[S]` at decode (`CBUtil.readBoundValue` → `readRawBytes`,
  `CBUtil.java:480`, `:669`), on the Netty event loop, and stays referenced by the request until it completes.
- Admission (protocol v4, `PreV5Handlers.LegacyDispatchHandler.checkLimits`, default non-throwing mode): the request's body
  size is added to the channel count (`:179`) and tried against the per-IP (heap/40) and global (heap/10) in-flight limits
  (`DatabaseDescriptor.java:651`, `:656`). If that fails, it is **allocated anyway** (`:184`) and the connection is paused;
  the request is processed ("Even if backpressure is applied, the current request is allowed to finish", `:85`). The charge is
  released at response flush (`:106`). The counter charges S per request; the render's 4S–6S and the value copy are not
  charged separately (the copy is the charged S in a second form: the Netty frame stays in direct memory until flush).
- Concurrency of renders: `Native-Transport-Requests` pool, `native_transport_max_threads` = 128 (`Config.java:283`,
  `Dispatcher.java:58-61`); connections are unlimited at defaults (`native_transport_max_concurrent_connections: -1`).
- All four render arrays exceed half a G1 region (regions are 16 MiB, `jvm11-server.options:66`), so they are humongous
  objects: per rendering request 1 (value) + 4 (char[]) regions, 7 while `new String` copies, 5 during the concatenation.
- **Direction:** bypass, accounting omission (U > C, K ≤ C): the render buffers are request memory that the in-flight
  counter (K) does not see; K stays within the contract (each connection holds one request, which the contract admits).
  Multiplicity comes from client connections (one traced request each). Technique note:
  [`bypass-playbook.md`](../../../bypass-playbook.md) (accounting mismatch shape: matched payload on the protected path as
  control, a patch that removes the excess as intervention).

### 2.2 Protection map

| Domain | Holder (allocation → release) | Counter (K) | Limit (C), shipped default | At the limit |
|---|---|---|---|---|
| Request body in flight | Netty v4 frame (direct) and the decoded value `byte[S]` (heap, `CBUtil.java:669`) → released at response flush (`PreV5Handlers.java:106`) | channel / per-IP / global byte counters (`RequestsSize` gauge, `ClientMetrics.java:129`) | global heap/10, per IP heap/40 (`DatabaseDescriptor.java:651`, `:656`); contract: one request per connection is admitted even above the limit (`PreV5Handlers.java:85`, `:184`) | connection paused (`autoRead` off); the admitted request is processed |
| **Trace render buffers** (claimed holder) | `char[2S]`, `byte[2S]` (hex String), `byte[2S+2]` (concat), locals of the NTR thread in `traceQuery` (`ExecuteMessage.java:230`) → unreachable after `:232` | **none** | none; the literal `1000` (`:231`) cuts only the stored string, after allocation | — |
| Rendering concurrency | NTR pool workers | active tasks | `native_transport_max_threads` 128 (count, not bytes) | further requests wait in the queue (holding their value copy and frame) |
| Connections | one v4 connection per client IP | `connectedNativeClients` | `native_transport_max_concurrent_connections` −1 and `_per_ip` −1 (unlimited) | — |
| Request size | one frame | — | `native_transport_max_frame_size` 16 MiB (`Config.java:285`, check `Envelope.java:428-429`); `max_value_size` 256 MiB (not binding) | request rejected |
| Trace rows | `system_traces.sessions/events` mutations (≈ 1.2 KB per request after the cut) → memtable | memtable pool | `memtable_heap_space` heap/4, `heap_buffers` | flush (negligible here) |
| Heap budget | JVM heap | — | `-Xmx` (2 / 4 / 8 GiB arms) | `OutOfMemoryError: Java heap space` → shipped `-XX:OnOutOfMemoryError="kill -9 %p"` |
| Direct budget | Netty frames (≈ 2–2.5 × K, lead B9) | Netty / JDK direct counters | `MaxDirectMemorySize` auto = 15,872 MiB on this node | competing endpoint, not the claim (§2.7) |

### 2.3 Configuration and budget audit

- **Build:** Cassandra 5.0.9 from `systems/cassandra/source/` via `copy-source.sh` to `/mydata/s4/cassandra-base`, `ant jar`,
  unmodified. Intervention build: a copy with the one-file patch of §2.8 (`/mydata/b11/cassandra-iv`). Record repo commit,
  `git -C <tree> describe --tags` (`cassandra-5.0.9`), `git diff` of each tree (empty / the patch).
- **Configuration:** the shipped `conf/` unchanged: no `cassandra.yaml` edit at all (single node, `127.0.0.1`, data and
  commit log under the tree's `data/`, `heap_buffers`, `auto_snapshot` default). Every capacity constraint in §2.2 is at its
  shipped default (V6): `native_transport_max_request_data_in_flight` (heap/10), `…_per_ip` (heap/40),
  `native_transport_max_threads` 128, `native_transport_max_frame_size` 16 MiB, `native_transport_max_concurrent_connections`
  −1 / `_per_ip` −1, `native_transport_rate_limiting_enabled` false, `native_transport_timeout` 12 s,
  `native_transport_allow_older_protocols` true, `trace_type_query_ttl` 1d, `memtable_heap_space` heap/4.
- **Resolved at each heap** (`Runtime.maxMemory()` = `-Xmx` under G1): 2 GiB → global 214,748,364 B, per IP 53,687,091 B;
  4 GiB → 429,496,729 / 107,374,182; 8 GiB → 858,993,459 / 214,748,364; 12 GiB (stretch) → 1,288,490,188 / 322,122,547.
- **Environment settings (not capacity):** `MAX_HEAP_SIZE` (sets `-Xms = -Xmx`), `CASSANDRA_HEAPDUMP_DIR=<run dir>` (the
  shipped `-XX:+HeapDumpOnOutOfMemoryError` writes there), `ulimit -n 100000` in the launching shell (hard limit 1,048,576;
  the soft 1,024 would cap connections), the node in `systemd-run --user --scope -p MemorySwapMax=0` (swap 0 for the measured
  process; **no `MemoryMax`**: no container limit is a budget here), linger enabled for the run. GC log: the shipped
  `cassandra-env.sh` `-Xlog:gc=info,heap*=trace,…` to `logs/gc.log`. Everything else from `jvm-server.options` /
  `jvm11-server.options` (G1, `G1HeapRegionSize=16m`, `G1NewSizePercent=50`, `AlwaysPreTouch`, `PerfDisableSharedMem`).
- **Node claimed (V7):** `ms0611` (Utah m400, aarch64 X-Gene, 8 cores, 64,249 MB RAM, 8 GiB swap present, Ubuntu 22.04,
  kernel 5.15, OpenJDK 11.0.33, Ant 1.10.12, Python 3.10.12; `/mydata` 35 GiB free; nothing running; checked read-only
  2026-11-17 22:49 ET). `cassandra-env.sh` would resolve heap = 31,744 MiB and `MaxDirectMemorySize` = 15,872 MiB for this
  node (G1 ⇒ `heap_limit` 31,744; ½ RAM = 32,124 > 31,744). **Budgets:** heap 2 GiB (ideal), then 4 and 8 GiB (12 GiB stretch),
  all ≥ 512 MiB ⇒ V7 met without per-case review (standing rule 2026-11-11); direct left at the auto 15,872 MiB (record it
  from `VM.flags`); no container limit. Platform aarch64: never pool these runs with x86 runs.

### 2.4 Ceiling arithmetic

Payload: one blob S = 16,000,000 B (deterministic pattern `bytes(range(256)) * 62500`). EXECUTE body
B = 2 + 16 (statement id) + 2 + 1 + 2 + 4 + S = **16,000,027 B**; frame 16,000,036 B ≤ 16,777,216 ✓. Regions (16 MiB):
value `byte[16,000,000]` = 1, `char[32,000,000]` (64,000,016 B) = 4, hex `byte[32,000,000]` = 2, concat `byte[32,000,002]` = 2.
Per rendering request 5 regions (80 MiB) for most of the render, 7 (112 MiB) during `new String`; per queued or
executing-but-not-rendering request 1 region.

| Heap | regions | C global (= max requests within) | N where K ≤ C | Predicted live at N (R = rendering, baseline 15–25 regions) | Prediction |
|---|---|---|---|---|---|
| 2 GiB | 128 | 214.7 MB (13) | ≤ 13 | N=13: 13–65 + baseline ≤ 90 regions; N=24: R 14–24 → 84–130; N=32: R 19–32 → 108–175 | survive at 13 (but U_render/K ≈ 3–5); first failure at N 24–32 |
| 4 GiB | 256 | 429.5 MB (26) | ≤ 26 | N=64: R 38–64 → 216–340 | fail at N ≈ 48–64 |
| 8 GiB | 512 | 859.0 MB (53) | ≤ 53 | N=256: R ≤ 128 (f 0.6–0.9: 77–115) → 385–575 + 141–179 queued + 25 = 590–780 | fail at N = 256 |
| 12 GiB | 768 | 1,288 MB (80) | ≤ 80 | N=256: 590–780 | borderline (stretch only) |

Σ contract capacities that cover this memory: heap/10 (+ one 16 MB request per admitted connection); the render buffers
(4–6 × 16 MB per rendering request, up to 128 × 112 MiB = 14 GiB) are covered by no capacity. Feasibility: the uncharged
render demand alone exceeds every tested heap at the planned N, so the endpoint is arithmetically reachable at 2–8 GiB.
Netty direct (B9 factor 2–2.5 × K): N=256 ⇒ 8–10 GiB < 15,872 MiB ✓; do not exceed N=256 (N=384 would approach the direct limit).

### 2.5 Workload and environment

- **Node:** `ms0611` only (victim and client on the same node; the client is outside the node's scope). Work dirs:
  `/mydata/s4/cassandra-base` (base build), `/mydata/b11/cassandra-iv` (intervention build), `/mydata/b11/runs/<run-id>/`
  (logs, monitors, dumps). Before anything: `ps -eo cmd | grep '[C]assandraDaemon'` must be empty; do not touch
  `/mydata/s2r2`, `/mydata/u1r2` (other cases). `sudo loginctl enable-linger jason92` at start, `disable-linger` at the end.
- **Build** (`harness/build.sh`): `copy-source.sh /mydata/s4/cassandra-base` (rsync the repo's `systems/cassandra/source`
  to the node first, e.g. to `/mydata/b11/src-copy`, and run the script there with `CASSANDRA_SRC` pointing at it), then
  `cd /mydata/s4/cassandra-base && ant jar` (≈ 5–6 min on the m400; log to `/mydata/b11/build-base.log`). Then
  `cp -a /mydata/s4/cassandra-base /mydata/b11/cassandra-iv`, `git apply harness/iv.patch`, delete
  `build/classes/main/org/apache/cassandra/transport/messages/ExecuteMessage*.class` (Ant's 1 s timestamps), `ant jar`,
  and check `javap -c -classpath build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.transport.messages.ExecuteMessage | grep -c duplicate`
  ≥ 1 in the iv tree and = 0 in the base tree. Never run `ant` in a tree a node is running from.
- **Schema** (after each start, by `client.py --ddl` or `bin/cqlsh 127.0.0.1`):
  `CREATE KEYSPACE b11 WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
  `CREATE TABLE b11.t (k int, c int, v blob, PRIMARY KEY (k, c));` (empty table; no data is written).
- **Statement (prepared once per connection):** `SELECT c FROM b11.t WHERE k = 0 AND v = ? ALLOW FILTERING`, consistency ONE,
  one bound blob of S bytes. A legal read (single partition, filtering on a regular column, value within `max_value_size` and the
  frame limit) that returns 0 rows and writes nothing, so disk and memtables stay out of the measurement. The render happens
  before execution, so the statement shape does not change the mechanism; it only keeps the rest of the request cheap.
- **Client** (`harness/client.py`, Python 3 standard library, raw protocol v4, no driver):
  - N connections, connection i bound to source address `127.1.(i // 250).(1 + i % 250)` before `connect(('127.0.0.1', 9042))`
    (any 127/8 address is local), so each IP holds one request (16,000,027 B ≤ heap/40 at every heap tested).
  - Per connection: STARTUP (`{"CQL_VERSION":"3.0.0"}`) → READY; PREPARE (`[long string]`) → RESULT kind 4, read the
    `[short bytes]` id; then a closed loop: send one EXECUTE frame, wait for its response, repeat. Frame header v4:
    `0x04, flags, stream=0 (int16), opcode, length (int32 BE)`; EXECUTE (`0x0A`) body: `[short bytes] id`, consistency
    `0x0001`, flags byte `0x01` (values), `[short] 1`, `[int] S` + blob. **flags = `0x02` (tracing) in test and intervention
    arms, `0x00` in the control** — the only difference between test and control. Build the frame once per process and send the
    same `bytes` object on every connection (`sendall`). Responses: RESULT (`0x08`; with the tracing flag the body starts
    with the 16-byte session UUID) or ERROR (`0x00`: int code + string; log it and continue the loop).
  - Ramp mode: connections added in steps (`--ramp 8,13,16,24,32,48,64[,96,128,192,256] --step-s 60`); fixed mode: all N opened
    and started together, held for `--hold-s`.
  - Logs: one line per completion (`t_ms conn latency_ms status`), a once-per-second line (`t_ms open established
    outstanding completed errors K_client`), K_client = outstanding × 16,000,027 (an upper bound of the server's global count,
    exact while each connection has one request outstanding).
- **Run driver** (`harness/run.sh <run-id> <base|iv> <heap> <traced|untraced> <fixed N | ramp list> <hold-s>`): preflight
  (no daemon, ports 7000/7199/9042 free, `df /mydata` ≥ heap + 4 GiB free) → wipe `<tree>/data` and `<tree>/logs` → start
  `( ulimit -n 100000; MAX_HEAP_SIZE=<heap> CASSANDRA_HEAPDUMP_DIR=<run dir> systemd-run --user --scope -p MemorySwapMax=0
  --unit=b11-<run-id> -- bin/cassandra -f > <run dir>/stdout.txt 2>&1 < /dev/null & )` → wait for `Starting listening for CQL
  clients` (≤ 300 s, bounded poll) → `jcmd <pid> VM.flags` → schema → monitors → client → wait for OOM (daemon gone + stdout
  `java.lang.OutOfMemoryError`) or the hold end → stop the client, `kill <pid>` (then `-9` after 60 s), wait for the scope to
  end → copy `system.log`, `gc.log*`, stdout, client and monitor logs to the run dir → `summarize.py`. Never a foreground
  `sleep` in the agent's turn: launch with `( setsid nohup … & )` and poll.
- **Arms** (all: S = 16,000,000 B, base build unless stated, same instruments):

| Run | Build | Heap | Tracing | N | Hold | Purpose |
|---|---|---|---|---|---|---|
| `S0` shakedown | base | 2 GiB | on | 2 | 60 s | reachability (not a reading): requests succeed (RESULT Rows, 0 rows), a `system_traces.sessions` row has `bound_var_0_v` of 1004 chars ending `...'`, `Thread.print` shows `traceQuery` frames, `RequestsSize` readable |
| `R2` ramp | base | 2 GiB | on | 8, 13, 16, 24, 32, 48, 64 (then 96, 128, 192, 256 if no failure) | 60 s per step | calibration: first failing N (N_f); U vs K at N = 8 and 13 (K ≤ C) |
| `T2-1..3` test | base | 2 GiB | on | N₂ | ≤ 180 s | V1 at 2 GiB |
| `C2-1..3` control | base | 2 GiB | off | N₂ | 150 s | V2 (matched payload, protected path) |
| `I2-1..3` intervention | iv | 2 GiB | on | N₂ | 150 s | V4 |
| `T4-1` (→ `-2`, `-3`) | base | 4 GiB | on | N₄ = min(2 × N₂, 256) | ≤ 180 s | budget search |
| `T8-1` (→ `-2`, `-3`) | base | 8 GiB | on | 256 | ≤ 180 s | budget search |
| `C8-*`, `I8-*` (or at 4 GiB if 8 GiB survives) | base / iv | largest failing | off / on | as its test | 150 s | V2/V4 at the largest failing budget (as time allows) |
| `T12-1` (stretch) | base | 12 GiB | on | 256 | ≤ 180 s | only if `T8-1` failed and the time plan allows |

  **N₂ (frozen rule):** if the ramp's first failing step N_f ≤ 13, N₂ = 13 (the endpoint within K ≤ C); otherwise N₂ = the next
  ramp step above N_f (margin for 3/3), capped at 256. If the ramp reaches 256 without failure, skip T2/C2/I2 and run
  `T4-1`/`T8-1` only as readings of U (outcome O2). If `T8-1` survives, the largest failing budget is 4 GiB (or 2 GiB if
  `T4-1` survives too); do not raise N above 256.

### 2.6 Instruments

| What | How | Interval | Gives |
|---|---|---|---|
| Live humongous memory (U, independent of K) | `logs/gc.log` (shipped Xlog): per GC `Humongous regions: X->Y`, `Eden`, `Old`, heap before→after, `Pause Full`, `To-space exhausted`, causes (`G1 Humongous Allocation`) | every GC | U_h = Y × 16 MiB (live humongous after each GC); U_render ≈ U_h(test) − U_h(control) at matched N |
| Heap occupancy | `jcmd <pid> GC.heap_info` (no GC forced; `jstat` cannot attach: `PerfDisableSharedMem`) | 2 s | used / committed, region counts |
| Rendering concurrency R | `jcmd <pid> Thread.print` → count `Native-Transport-Requests` threads whose stack contains `ExecuteMessage.traceQuery`, and of those in `Hex.bytesToHex`, `String.<init>`/`StringUTF16.compress`, `StringConcatHelper` | 5 s | R(t), actual concurrency (not client threads) |
| K (server) | `bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSize -f Value --get` and `…name=PausedConnections` | 10 s | global in-flight bytes, paused connections |
| K (client) | client per-second line | 1 s | outstanding × B |
| Process | `RssAnon` from `/proc/<pid>/status`; scope `memory.current`, `memory.events` | 2 s | native growth (direct frames) |
| Throughput / completion | client completion lines | per request | completed requests, latency, errors per arm (an intervention that stops useful work is not protection) |
| Endpoint | `stdout.txt`: `java.lang.OutOfMemoryError: Java heap space`, `Dumping heap to …`, `OnOutOfMemoryError`; process exit; `system.log` ERROR lines | at end | endpoint type |
| Holder at failure (V5) | the shipped heap dump (`<run dir>/cassandra-*.hprof`): `hprof_oome_thread.py` (copy from `cases/candidates/memtable_heap_space+counter_cache_size/recheck-2026-11-11/tools/`: the OOME thread's stack, fake frame `OutOfMemoryError.<init>`), and a `bigarrays.py` (adapted from `hprof_histo.py` there) listing primitive arrays ≥ 1 MiB by (type, length) with counts and bytes, reachable vs not, plus the count of `ROOT_JAVA_FRAME` roots in NTR threads that point at them | first failing run per budget (full), every failing run (`hprof_oome_thread.py` only) | arrays of length 32,000,000 (`char[]`, `byte[]`), 32,000,002 (`byte[]`), 16,000,000 (`byte[]`) and their sum vs heap |
| Trace row check | `SELECT parameters FROM system_traces.sessions LIMIT 3` (cqlsh) | `S0`, and once in `I2-1` while running | stored `bound_var_0_v` = 1004 chars `0x0001…` + `...'` in both builds (the intervention does not change what is stored) |

The thread and `heap_info` samplers run identically in every arm (matched instrumentation); do not add forced GCs or
histograms during load. Each run's `summarize.py` writes `summary.txt`: endpoint, time to endpoint after the last connection
started, N established, completions, errors, max R, max/median U_h, max K_server, max K_client, max RssAnon, GC STW share over
the last 60 s, and the dump findings.

### 2.7 Predicted response, outcome rows and stopping budget

**Predicted protective response:** none for the render. The in-flight limit pauses connections above heap/10 but processes the
admitted request on each; NTR threads cap R at 128; no check charges or rejects the render. Predicted: test at 2 GiB fails with
a Java heap OOM within ≈ 60 s of full N (first failing ramp step 24 or 32, so N₂ = 32 or 48); dumps show ≥ 70 % of the heap in
arrays of length 32,000,000 / 32,000,002 / 16,000,000 held by NTR thread frames; the OOME thread is an NTR thread in
`Hex.bytesToHex` / `String.<init>` / `StringConcatHelper` under `ExecuteMessage.traceQuery`. Control (untraced, same N) survives
with U_h ≤ baseline + N × 16 MiB (≤ 1 GiB at N = 48). Intervention survives with U_h ≈ control. In the ramp at N = 8 and 13
(K ≤ C), U_render ≈ 3–5 × K. 4 GiB fails at N₄; 8 GiB fails at N = 256. Throughput: test, control and intervention complete
requests at comparable rates before the test's failure.

| Row | Observation | Reading |
|---|---|---|
| O1 | test heap OOM ≥ 2/3 (report n/N) at a budget, control 0/3, intervention 0/3, holder in the dump = render arrays, U_render ≫ K | endpoint reached: `true positive` candidate (`verified-OOM · deployment` if V1–V7 hold at that budget) |
| O2 | ramp reaches 256 at 2 GiB without OOM, or every test run survives | report U_render vs K and R; `retry` (name the better design) or `false positive` per the playbook |
| O3 | test OOMs but the dump's dominant holder is not the render arrays | attribution fails: `retry` |
| O4 | Netty `OutOfDirectMemoryError` / direct OOM first | competing endpoint (lead B9): record, rerun the arm once at the next lower N; if repeated, `retry` |
| O5 | control also OOMs | value copies × N alone suffice: not this mechanism, `retry` (rethink as convergence) |
| O6 | GC service loss (≥ 90 % STW over ≥ 60 s) without OOM | `verified-gap · service-loss` at best: `retry` |
| O7 | intervention also OOMs | the patch did not remove the holder or the holder is elsewhere: `retry` (no intervention evidence) |

**Stopping budget:** per run, ≤ 300 s to start, ≤ 180 s of load at full N (test) / 150 s (control, intervention), 60 s per ramp
step; one run at a time; no new run starts after **01:55 America/New_York (2026-11-18)**; at most 3 repeats per arm per budget,
plus one rerun per invalid run (node failed to start, client failed before full N). No arbitrary escalation after an OOM: only the
planned budget steps. Endpoint of a run = the first of: heap OOM, direct OOM, hold end.

**Time plan (stage 2 must end before 02:30 America/New_York on 2026-11-18; times as offsets from stage-2 start T0, expected
≈ 23:20):** T0+0:00–0:10 read, hash check, node check, linger; 0:10–0:30 copy + base build (background) while writing the
harness; 0:30–0:38 iv tree + rebuild + `javap` check; 0:38–0:46 `S0`; 0:46–0:56 `R2`; 0:56–1:46 `T2` ×3 (≈ 5 min each incl.
2 GiB dump), `C2` ×3 and `I2` ×3 (≈ 4.5 min each); 1:46–2:06 `T4-1`, `T8-1` (8 GiB dump ≈ 80–100 s on this SATA SSD);
2:06–2:40 repeats at the largest failing budget (test ×2, then control, then intervention) and `T12-1` only if time remains;
then stop, reduce dumps, self-check, §3/§4, cleanup by 02:30. **Priority if late:** `S0` → `R2` → `T2` ×3 → `C2` ×3 → `I2` ×3 →
`T4-1` → `T8-1` → repeats at the largest failing budget → `T12-1`. The 2 GiB set (V1–V7 at 2 GiB) needs ≈ 1 h 50 min from T0.
**Disk:** base + iv trees ≈ 3 GiB; dumps ≈ heap each: keep every 2 GiB dump and the first dump per larger budget, run
`hprof_oome_thread.py` on each other dump and then delete it; keep `/mydata` free ≥ heap + 4 GiB before every run.
**RAM/cores:** largest process ≈ 8 GiB heap + ≤ 10 GiB direct + 1 GiB native, client < 1 GiB: < 21 GiB of 62 GiB; 12 GiB stretch
< 25 GiB. 8 cores shared by node and client (the client mostly waits in `sendall`/`recv`).

### 2.8 Controls and intervention

- **Matched control (V2), ≥ 3 runs per condition:** the same EXECUTE frames, connections, N, heap and build with the tracing flag
  clear (`flags = 0x00`): the identical decode, value copy, frame, admission and SELECT, without `traceQuery`. Survival with
  U_h ≈ N × 16 MiB + baseline shows that the multiplicity and the charged bytes alone do not reach the endpoint.
- **Causal intervention (V4), ≥ 3 runs per condition:** a separate build (`/mydata/b11/cassandra-iv`) whose only change bounds
  the render to the first 1000 bytes of each value; the stored trace value is unchanged for a blob (2,002 chars → cut to the
  same 1000 + `...'`), so tracing and its writes stay identical. Diff saved as `harness/iv.patch`:

```diff
--- a/src/java/org/apache/cassandra/transport/messages/ExecuteMessage.java
+++ b/src/java/org/apache/cassandra/transport/messages/ExecuteMessage.java
@@ -227,6 +227,9 @@ public class ExecuteMessage extends Message.Request
             ColumnSpecification cs = prepared.statement.getBindVariables().get(i);
             String boundName = cs.name.toString();
             ByteBuffer bytes = options.getValues().get(i);
+            // B11 intervention (diagnostic build only): render at most 1000 bytes; the 1000-char cut below stores the same value for blobs
+            if (bytes != null && bytes != ByteBufferUtil.UNSET_BYTE_BUFFER && bytes.remaining() > 1000)
+                bytes = (ByteBuffer) bytes.duplicate().limit(bytes.position() + 1000);
             String boundValue = (bytes == ByteBufferUtil.UNSET_BYTE_BUFFER) ? "<unset>" : cs.type.asCQL3Type().toCQLLiteral(bytes);
             if (boundValue.length() > 1000)
                 boundValue = boundValue.substring(0, 1000) + "...'";
```

  (Apply with `git apply --recount` if the hunk header offsets differ; the context lines are `ExecuteMessage.java:227-232`.)
  The original failure must reproduce on the unmodified base build (`T2`). Record the intervention's completions/s against the
  test's pre-failure rate and the control's.
- **V-table plan:** V1 `T2-1..3` (and repeats at the largest budget); V2 `C2-1..3`; V3 U_h and dump arrays vs `RequestsSize`
  (K) in every arm, U_render/K in `R2` at N = 8, 13; V4 `I2-1..3`; V5 stdout OOM line + `hprof_oome_thread.py` stack + `bigarrays.py`
  on the first `T2` dump; V6 §2.3 (no constraint changed in any arm; the patch only in the intervention arm); V7 heap 2–8(12) GiB,
  direct auto 15,872 MiB, no container limit. Largest failing budget with n/N reported.

`sha256 of §1–§2 at freeze: 47a66c593518a086aa5c1a1c58633520ffe7311b39b9be27e9c1581b7c606634` (computed as `awk '/^## 1\. Candidate/{p=1} /^`sha256 of §1–§2 at freeze/{p=0} p' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-17) · amendments after the freeze: none.

## 3. Runs (stage 2)

*Stage-2 session, 2026-11-17 22:55 – 2026-11-18 ~00:05 America/New_York. The freeze hash was checked first:
`47a66c593518a086aa5c1a1c58633520ffe7311b39b9be27e9c1581b7c606634` recomputed with the stated `awk … | sha256sum`; it matches.
Design amendments: none. The execution deviations below change no arm, constraint, budget or workload.*

### 3.1 Environment (as run)

| Item | Value |
|---|---|
| Node | `ms0611` (`node3.jason92-326377…utah.cloudlab.us`): **aarch64**, 8 cores, 64,249 MB RAM, 8 GiB swap (`/dev/sda99`, unused), Ubuntu 22.04.1, kernel `5.15.0-191-generic`, cgroup v2. Checked idle before starting (`pgrep -af CassandraDaemon` empty, no `java`); other directories on `/mydata` (`s2r2`, `u1r2`) left untouched |
| Toolchain | OpenJDK 11.0.33+9 (Ubuntu build), Ant 1.10.12, Python 3.10.12 |
| Source / build | repo HEAD `e64ab8f2`; `systems/cassandra/source/` rsynced to `/mydata/s4/b11-w1/src-copy` and copied with `copy-source.sh` (from `capacity-enforcement-exp/cassandra/stage4-runtime-verification/`) to `/mydata/s4/b11-w1/cassandra-base` (`git describe --tags` = `cassandra-5.0.9`, `git diff` empty); `ant jar` BUILD SUCCESSFUL in 4 min 58 s. Intervention tree `/mydata/s4/b11-w1/cassandra-iv` = `cp -a` of the base + [`harness/iv.patch`](harness/iv.patch) (`git diff` = the patch, 3 insertions), `ExecuteMessage*.class` removed, `ant jar` 35 s. Check: `javap -p -c … ExecuteMessage \| grep -c ByteBuffer.duplicate` = **1** in iv, **0** in base ([`logs/series-and-build.txt`](logs/series-and-build.txt)) |
| Configuration | the shipped `conf/` unchanged (no `cassandra.yaml` edit) in every arm; tree `data/` and `logs/` wiped before each run |
| JVM (resolved, from `VM.flags` / `JVM Arguments`) | G1, `G1HeapRegionSize=16777216`, `-Xms = -Xmx` = 2/4/8 GiB per arm, **`MaxDirectMemorySize=16642998272` (15,872 MiB, auto from `cassandra-env.sh`)**, `+HeapDumpOnOutOfMemoryError` (path = run dir), `-XX:OnOutOfMemoryError=kill -9 %p`, `+AlwaysPreTouch`, `+PerfDisableSharedMem`, shipped `-Xlog:gc…`; open files soft/hard 100,000 |
| Budget isolation | each daemon in `systemd-run --user --scope -p MemorySwapMax=0 --unit=b11-<run>` (no `MemoryMax`); linger enabled for the session and disabled at the end |
| Resolved limits | 2 GiB: global in-flight 214,748,364 B, per IP 53,687,091 B; 4 GiB: 429,496,729 / 107,374,182; 8 GiB: 858,993,459 / 214,748,364 (§2.3) |
| Harness | [`harness/`](harness/): `build.sh`, `iv.patch`, `client.py` (raw v4), `run.sh` (one run), `series.sh` (sequential runs, no start after 01:55 ET), `monitor.sh` + `threadcount.py` (instruments of §2.6), `summarize.py`, dump tools `hprof_oome_thread.py` (copied), `bigarrays.py`, `retainers.py` (referrer chains), `stacks_grep.py` |
| Full logs | on `ms0611` under `/mydata/s4/b11-w1/runs/<run>/` (driver, stdout, `system.log`, `gc.log*`, client, completions, monitors, VM flags, summary) and `/mydata/s4/b11-w1/series.log`; heap dumps kept: `runs/R2`, `runs/T2-1`, `runs/T2-2`, `runs/T2-3` (`*.hprof`, 1.6–1.9 GB each). Excerpts: [`logs/`](logs/) (one file per run, [`logs/dump-analyses.txt`](logs/dump-analyses.txt)) |

### 3.2 Runs

S = 16,000,000 B, B (EXECUTE body) = 16,000,027 B in every arm. "U_h after GC" = live humongous regions after each GC from
`gc.log` (16 MiB each), over the whole run. K_server = `RequestsSize` samples. Throughput = ok completions / s at full N.

| Run | Build · heap · tracing · N | Endpoint | Time to endpoint at full N | ok completions (rate) · median latency | max R (traceQuery) | U_h after GC: median / max | K_server max · K_client max |
|---|---|---|---|---|---|---|---|
| `S0` | base · 2 GiB · on · 2 | hold end (60 s), no OOM | — | 710 (11.8/s) · 155 ms | 2 | 4 / 10 regions | 32,000,054 · 32,000,054 |
| `R2` | base · 2 GiB · on · ramp 8 → 13 | **heap OOM** at the N=13 step | N=8 held 60 s; OOM 9.3 s after N=13 | N=8: 796 (13.3/s) · 592 ms; N=13: 12 · 1,148 ms | 7 | N=8 window: 83 / 110; N=13: 103 / 112 | 96,000,162 · 208,000,351 |
| `T2-1` | base · 2 GiB · on · 13 | **heap OOM** | 15.3 s | 82 (5.4/s) · 1,176 ms | 9 | 90 / 117 | — (no sample) · 208,000,351 |
| `T2-2` | base · 2 GiB · on · 13 | **heap OOM** | 22.2 s | 127 (5.7/s) · 1,226 ms (2 read timeouts `0x1200`) | 13 | 103 / 119 | 96,000,162 · 208,000,351 |
| `T2-3` | base · 2 GiB · on · 13 | **heap OOM** | 20.5 s | 119 (5.8/s) · 1,228 ms | 10 | 102 / 119 | 160,000,270 · 208,000,351 |
| `C2-1` | base · 2 GiB · **off** · 13 | hold end (150 s) | — | 7,644 (51/s) · 244 ms | 0 | 2 / 29 | 16,000,027 · 208,000,351 |
| `C2-2` | base · 2 GiB · **off** · 13 | hold end | — | 8,343 (56/s) · 222 ms | 0 | 2 / 6 | 32,000,054 · 208,000,351 |
| `C2-3` | base · 2 GiB · **off** · 13 | hold end | — | 8,648 (58/s) · 213 ms | 0 | 2 / 6 | 48,000,081 · 208,000,351 |
| `I2-1` | **iv** · 2 GiB · on · 13 | hold end | — | 6,850 (46/s) · 270 ms | 1 | 2 / 30 | 32,000,054 · 208,000,351 |
| `I2-2` | **iv** · 2 GiB · on · 13 | hold end | — | 7,113 (47/s) · 261 ms | 1 | 3 / 33 | 32,000,054 · 208,000,351 |
| `I2-3` | **iv** · 2 GiB · on · 13 | hold end | — | 7,127 (48/s) · 260 ms | 2 | 2 / 21 | 32,000,054 · 208,000,351 |
| `T4-1` | base · 4 GiB · on · 26 | hold end (180 s), no OOM | — | 3,287 (18/s) · 1,403 ms | 20 | 145 / 189 (3,024 MiB) | 336,000,567 · 416,000,702 |
| `T8-1` | base · 8 GiB · on · 256 | hold end (180 s), no OOM | — | 3,623 (20/s) · 12,529 ms; 0 errors | 67 | 209 / 400 (6,400 MiB) | 832,001,404 (paused connections up to 41) · 4,096,006,912 |

Every OOM run: `stdout.txt` has `java.lang.OutOfMemoryError: Java heap space`, `Dumping heap to …`, `Heap dump file created`, then
`-XX:OnOutOfMemoryError="kill -9 %p"` executed. No direct-memory OOM (O4), no cgroup event (no limit), no run with ≥ 90 % STW
over 60 s (last-60 s STW share 3–11 %). GC: the T2 runs had 7–25 `Pause Full` before the OOM, the controls 0–1.

**Trace rows.** `S0` and `I2-1..3` (read right after the hold, daemon up): `bound_var_0_v` = 1,004 chars, `0x0001020304…f1f2...'`
in both builds, so the intervention leaves the stored value unchanged.

**U vs K (V3).** At N=8 in `R2` (K = 8 × B = 128 MB ≤ C = 214.7 MB, server samples 80–96 MB), live humongous after GC was a median of
83 regions (1,328 MiB), max 110, against 2 regions in the untraced control at N=13. At N=13 (K ≤ 208 MB ≤ C) the T2 runs held 90–103
regions (1.4–1.6 GiB) median, 117–119 max. At 8 GiB, N=256, U_h reached 6,400 MiB with K_server ≤ 832 MB ≤ C 859 MB. U ≫ K
holds in every traced base run. As the dumps show, though, U includes a second holder besides the render.

### 3.3 Dumps at failure (V5)

All four 2 GiB dumps (`R2`, `T2-1..3`) were analysed in full ([`logs/dump-analyses.txt`](logs/dump-analyses.txt)). MiB = shallow sizes.

| Dump | OOME-initiating thread (first frames) | value `byte[16,000,000]`: total · held by slow-query monitor · in-flight requests | render arrays (`char[32,000,000]`, `byte[32,000,000/…002]`) | arrays referenced from NTR thread frames | dump total |
|---|---|---|---|---|---|
| `R2` | NTR: `Hex.bytesToHex:78` ← … ← `ExecuteMessage.traceQuery:230` | 63 (961) · 52 (≈ 793, 43 %) · 11 | 701.9 (38.4 %) | ≈ 580 (32 %) | 1,828 |
| `T2-1` | NTR: `Hex.bytesToHex:78` ← … ← `ExecuteMessage.traceQuery:230` | 60 (916) · 51 (≈ 778, 49 %) · 9 | 518.8 (32.4 %) | ≈ 595 (37 %) | 1,600 |
| `T2-2` | NTR: `Hex.bytesToHex:78` ← … ← `ExecuteMessage.traceQuery:230` | 65 (992) · 52 (≈ 793, 42 %) · 13 | 701.9 (37.2 %) | ≈ 610 (32 %) | 1,886 |
| `T2-3` | **ScheduledTasks: `Hex.bytesToHex:78` ← `toCQLLiteral` ← `RowFilter$SimpleExpression.toString:876` ← `ReadCommand.toCQLString:91` ← `ReadCommand.name:897` ← `MonitoringTask$OperationsQueue.popOperations:242` ← `MonitoringTask.logSlowOperations:168`** | 64 (977) · 52 (≈ 793, 45 %) · 12 | 640.9 (36.5 %) | ≈ 747 (43 %) | 1,756 |

- **Second holder, not in the protection map.** The values not held by a running request have this referrer chain (`retainers.py`):
  `HeapByteBuffer.hb` ← `RowFilter$SimpleExpression.value` ← `RowFilter.expressions` ← `SinglePartitionReadCommand.rowFilter` ←
  `MonitoringTask$SlowOperation.operation` ← `LinkedBlockingQueue$Node.item` ← `MonitoringTask$OperationsQueue.queue`. This is
  the slow-query monitor (`db/monitoring/MonitoringTask.java`). Each read slower than `slow_query_log_timeout` (default 500 ms)
  is queued with its `ReadCommand`, including the filter's bound value. The queue holds at most `cassandra.monitoring_max_operations`
  = 50 operations (a count, not bytes; a separate queue of 50 holds failed operations) and is drained and logged every
  `cassandra.monitoring_report_interval_ms` = 5,000 ms. Logging renders each operation's name through `ReadCommand.toCQLString`,
  which writes the whole value as hex with no cut. In `T2-1` a `byte[64,000,086]` `StringBuilder` on that thread holds such
  a render, and in `T2-3` that render is the initiating failure. The traced requests take a median of 1.2 s (> 500 ms), so the
  queue stays full in the test. The control and intervention run at a median of 213–270 ms, and their live humongous stays at
  a median of 2 regions, which shows the queue is not full there.
- **Claimed holder present but not dominant.** Each dump has 8–10 `char[32,000,000]` live in NTR frames (488–610 MiB) plus
  hex/concat `byte[]`s, all under `traceQuery`. That is the predicted render, at 32–38 % of the heap, against the ≥ 70 % of
  the heap in NTR-frame-held render and value arrays that §2.7 predicted (measured: 32–43 %).

### 3.4 Arms not run, and why

- `T4-2/3`, `T8-2/3`: not triggered (each `-1` survived). `T12-1`: only if `T8-1` failed (it did not).
- `C8`/`I8` (or at 4 GiB): the frozen rule makes the largest failing budget 2 GiB (`T4-1` and `T8-1` survived), where `C2`/`I2`
  already ran 3× each. No further run was started. This is not a time limit: the series ended at 23:46 ET, before the 01:55 cutoff.
- No N above the planned values (`T4-1` used N₄ = min(2 × N₂, 256) = 26; `T8-1` used 256), per "do not raise N" and "no arbitrary
  escalation".

### 3.5 Deviations in execution (no design change)

1. **Paths.** Work directory `/mydata/s4/b11-w1/` (session instruction: a fresh directory per node), with the base tree at
   `/mydata/s4/b11-w1/cassandra-base` (not `/mydata/s4/cassandra-base`), the intervention tree at `…/cassandra-iv` (not
   `/mydata/b11/cassandra-iv`) and runs under `…/runs/<run>` (not `/mydata/b11/runs`). `/mydata/s4` was created with `sudo`
   (it did not exist and `/mydata` is root-owned).
2. **`javap` check.** The frozen command (`javap -c … | grep -c duplicate`) shows no private methods and gave 0 for both trees.
   `traceQuery` is private, so the check used `javap -p -c … | grep -c ByteBuffer.duplicate`: 1 in iv, 0 in base.
   `harness/build.sh` has the corrected line.
3. **Sampling intervals.** On the m400, `nodetool sjk mx` takes ≈ 10 s per call, so `RequestsSize`/`PausedConnections` were sampled
   every ≈ 25–31 s (not 10 s). The T2 runs have 0–1 K_server samples before the OOM, so K there is read from the client
   (outstanding × B ≤ 208,000,351 B ≤ C). `Thread.print` ran every ≈ 6–7 s (not 5 s) and `heap_info` every ≈ 2.5 s. The
   samplers were identical in every arm.
4. **Trace-row check** in `I2-1..3` ran right after the hold ended (load stopped, daemon up), not during load.
5. **S0 driver line.** The first OOM grep in `run.sh` used a regex that matched the `CompileCommand … java/lang/OutOfMemoryError`
   startup line, so `S0`'s `driver.txt` says `oom:…` although S0 had no OOM (no `java.lang.OutOfMemoryError:` line, the daemon
   was stopped at the hold end). Fixed (`grep -F`) before `R2`.
6. **Dump analysis location.** The dumps were analysed on the controller (`scp` to its scratch space). The `R2` and `T2-1`
   copies (≈ 55 s per 2 GB) overlapped with the `T2-2`/`T2-3`/`C2-1` runs on the victim's disk and network. The client and
   victim share the node as designed (§2.5).
7. `summarize.py`'s whole-run U_h includes start-up and DDL. The `R2` per-step values above come from the `gc.log` timestamps.

## 4. Conclusion (stage 2)

**Verdict: `retry`.** **Protocol status (detail):** `candidate` · mixed. V1 (T2 3/3 heap OOM), V2 (C2 0/3), V3 (U from GC log and
dumps independent of K; U ≫ K ≤ C), V4 (I2 0/3 at matched N, 46–48 ok/s vs control 51–58 ok/s), V6 (shipped `conf/`, every §2.2
constraint at its default) and V7 (2 GiB heap, auto direct 15,872 MiB, no container limit; standing rule) hold at 2 GiB. **V5 does not
hold as the design defined it**: the claimed holder is live at failure, but it is not the dominant one (§2.7 row O3). Largest failing
budget: **2 GiB (3/3)**; 4 GiB at N=26 0/1 and 8 GiB at N=256 0/1 (planned single readings). Platform aarch64 (m400); not pooled with x86.

**Reason.** With 13 connections (one per IP; K ≤ 208 MB against C = 214.7 MB), traced 16 MB EXECUTEs exhausted a 2 GiB heap in
15–22 s, 3/3 (and in `R2` 9.3 s after N reached 13). The same frames untraced ran 150 s (7,644–8,648 completions, live humongous
median 2 regions), and the render-bounded build ran 150 s (6,850–7,127 completions), 3/3 each. At failure, though, only 32–38 %
of the heap was render arrays (8–10 `char[32,000,000]` under `traceQuery`; 32–43 % counting all NTR-frame-held arrays, against
≥ 70 % predicted). The largest holder, 42–49 % (≈ 780–790 MiB), was ≈ 51 finished `SinglePartitionReadCommand`s with their
16 MB values in the slow-query monitor's queue (`MonitoringTask`, count cap 50, drained every 5 s). They are queued because
the render makes traced requests slow (median 1.2 s > 500 ms). One of three initiating errors (`T2-3`) was that monitor's own
uncut `toCQLString` render of a queued value. The OOM therefore needs the render (uncharged, ≈ 0.5–0.7 GiB) **and** the monitor's
retention (uncharged, ≈ 0.8 GiB, a side effect of the render's latency). The intervention removes both at once (the bounded render
also brings latency under 500 ms), so it does not attribute the endpoint to the render's memory alone. At 4 GiB (N=26, U_h up to
3.0 GiB) and 8 GiB (N=256, U_h up to 6.4 GiB at K ≤ 832 MB, R ≤ 67 renders at once) the heap held. The render bypass (U > C,
K ≤ C) is real, but the frozen design has not shown that it alone drives the OOM, and it reached no OOM above 2 GiB.

**What a better design should change.**
1. **Re-map it as a mixed (stacked) case.** Add the slow-query monitor to the protection map as its own domain: holder =
   `MonitoringTask` slow/failed queues → `ReadCommand` → bound value; counter none; limit `cassandra.monitoring_max_operations`
   50 per queue (a count), drained every 5 s; plus its uncut `toCQLString` render at log time.
2. **Separate the two holders with a second intervention arm**, e.g. a diagnostic patch that queues the slow operation without
   its filter value (or `-Dcassandra.monitoring_max_operations=0` in that arm only). Run it next to the render-bounded arm at 2 GiB.
   If the test still fails with the monitor's retention removed, the render alone drives the OOM (pure bypass). If it survives,
   the case is the stack (render + monitor), and the claim and pattern should say so.
3. **Search the budget by N at 4 GiB**, which the frozen N₄ = 26 left untested: 26 → 48 → 64 → 128 → 256, 60 s per step as in `R2`.
   At 8 GiB, R peaked at 67 of 128 with a 12.5 s median latency, so render concurrency was limited by the single-node client
   and the CPU, not by the server. Use a second client node, or a longer hold (≥ 600 s), before calling 8 GiB safe. N may go up
   to ≈ 384 within the 15,872 MiB direct limit (§2.4).
4. **Consider the monitor as a candidate of its own** (no tracing): reads with large bound values that exceed 500 ms (or fail)
   are kept up to 50 + 50 with their values and rendered uncut every 5 s. On their own, that is ≈ 1.6 GB of 16 MB values plus
   ≈ 4× renders at log time, held by count only.

**Left on the node.** `ms0611:/mydata/s4/b11-w1/` (≈ 8.4 GB): `src-copy/`, `cassandra-base/` (built), `cassandra-iv/` (built),
`harness/`, `runs/` (13 run directories with full logs; four 2 GiB heap dumps in `runs/R2`, `runs/T2-1`, `runs/T2-2`, `runs/T2-3`),
`series.log`, build logs. No process, scope or linger left (checked: `pgrep` empty, no `b11-*` scope, `Linger=no`).
