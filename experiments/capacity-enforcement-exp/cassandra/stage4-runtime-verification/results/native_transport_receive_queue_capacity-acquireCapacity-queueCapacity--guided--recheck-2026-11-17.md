# native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided — stage-4 results, recheck claim (2026-11-17)

> **Case:** [`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided`](../../stage3-ai-deep-read/cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md), section "Stage-4 design for the recheck claim (2026-11-17)" (the recheck's "Stage-4 claim to add"). The case's earlier stage-4 result (§9a, closed 2026-10-15) is [`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md`](native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) and is not changed by this file.
>
> **Status:** **Verdict filed 2026-11-17 — Confirmed — does not cap** (design row 3: confirmed for the heap; direct memory undetermined). Run 1 on `pc72`, 11:04:57–11:14:58 MST; 79/80 `EXPECTED` lines yes (the miss: direct `MemoryUsed` stepped up 85.1 MB once at the start of `D40` and stayed flat, above the 64 MiB line but not following the decoded bytes); independent self-check 38/39 (the miss is a non-predicted `U10` mean, 2.5 % apart between two averaging methods). Design section frozen 12:42 EST, amended once before run 1 (hold 50 → 250 ms, §3), hash as run `4211db0a…`, verified unchanged after run 1. No run 2.
>
> **Outcome class:** true negative for the recheck claim — the recheck's estimate is `negative` for one-frame requests in the default mode, and the effect found is `does not cap`. The case's own outcome class from its 2026-10-15 results (true positive, about §9a) is not changed by this file.
>
> **Agent:** guided. "§9a" below means the design section's prediction and conclusions table; "the runbook" its arms, settings and observables. Cluster tier only (one node; the recheck claim is about a node at its shipped defaults, and the earlier run's unit tier already isolates each mechanism).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Last commit of the case file: `832b828a`; the design section is appended and uncommitted (no commit asked). **Frozen: `git hash-object` of the section from its heading `## Stage-4 design for the recheck claim (2026-11-17)` to the end of the file = `1c452cd6cc97830c3418c9b04f0d315af7e2bd24`** (`sed -n '/^## Stage-4 design for the recheck claim (2026-11-17)/,$p' <case file> \| git hash-object --stdin`), recorded 2026-11-17 12:42 EST after the audit below and before any harness file was written or run. **Amended once before run 1** (13:01 EST, results §3 defect 1: the hold 50 ms → 250 ms in the settings table, a runbook value; claim, prediction and conclusions unchanged): **hash of the section as run: `4211db0ad7dbe644cdda7d3e00b9054a8fe7f6a7`**, verified unchanged after run 1 (§5). §9's hash is unchanged by this work. |
| **Harness** | `../harness/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided--recheck-2026-11-17/` (uncommitted): `ntq-trace.btm`, `hold-request.btm`, `NativeFlood.java`, `Jmx.java`, `make-node-yaml.sh`, `flood-logback.xml` copied unchanged from the earlier harness; `recheck-run.py` and `README.md` new. Run copy `pc72:/mydata/s4/ntq-recheck/harness/`, `md5sum` identical to the repo (every `summary.txt` prints them). **Instrument checks (not readings):** Byteman `TestScript` type-checks all 9 rules of the two `.btm` files ("no errors"); `javac` of both Java files at every run start; shakedown `shake1` (`RECHECK_SCALE` 0.2, from 10:45 MST) ran every arm and the node stop, then the analysis stopped on a script bug (a list initialised as an integer in `parse_trace`); fixed, and arm results are now also written to `arms.jsonl` so the analysis can be re-run from the raw files. `shake2` (same scale, 10:56–11:00 MST) ran end to end (70/80 `EXPECTED` yes; most misses are the scaled-down windows, which lie below *K* or *G* by construction) and showed two defects, fixed before run 1 (§3): the client, not the node, set the pace with a 50 ms hold, and the `OutOfMemoryError` check matched the `-XX:+HeapDumpOnOutOfMemoryError` JVM-arguments line. `shake3` (hold 250 ms, 11:01–11:05 MST): the decoded sum stays at the client window (e.g. `D40` at scale 0.2: 124.9 MB for 15 s); 72/80, every remaining miss is a scaled window below *K* or *G*. Shakedown numbers are not readings. |
| **Tiers and values** | **Cluster only**, one node on `pc72`, every capacity knob at its default (capacity 1 MiB, `throw_on_overload` false, both reserves heap-derived, max message size default), heap pinned at 2 GiB. Arms: `idle`; `U10` (default, *N* 10, *W* 80); `D20`, `D30`, `D40` (default, small requests, *W* 240, *N* = 20 · 30 · 40); `T40` (throwing, *N* 40, *W* 240); `L20` (default, multi-frame, *N* 20, *W* 60). |
| **Audit bottom line** | **Ready** — 2026-11-17. The design was written by this session for the recheck claim and audited before the freeze; no amendment after the freeze. |

### 1.1 Design audit

Checked against the pinned source `systems/cassandra/source/` (`cassandra-5.0.9`): `CQLMessageHandler.java` 176-292 (`processOneContainedMessage`, `processRequestAndUpdateMetrics`, `discardAndThrow`), 370-395 (`composeRequest`, `processRequest`), 495-512 (both `release`); `AbstractMessageHandler.java` 200-260, 405-476 (`acquireCapacity`, `releaseCapacity`); `FrameDecoder.java` 310-332 (`deliver`: a consumed frame is released); `CBUtil.java` 443-450 (`readValue` copies onto the heap); `DatabaseDescriptor.java` 570-575, 649-657; `Config.java` 283, 286-302, 1394-1399; `conf/cassandra-env.sh` (heap 31 GiB and direct 15.5 GiB if not set, on this node).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | decoded request bytes on heap (`QueryMessage` + value copy) and frame bytes in direct memory; counted bytes `queueSize` and reserve use |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | the capacity is held at its default (the claim is about the defaults; the earlier run varied it over 4 values); the multiplier the claim names, the number of connections, is varied over 3 values (20 · 30 · 40), with an under-limit control at 10 |
| A. Core question | real resource measured, not only the counter (gap named) | Met | class histograms (live `QueryMessage`, `[B`), direct `MemoryUsed`, networking pool, scope `memory.current` (context) next to `queueSize` per handler and reserve use |
| A. Core question | usage driven to the limit and past it | Met | client windows 312–625 MB against *K_N* 75–96 MB and *G* ≈ 215 MB |
| A. Core question | negative claim: positive control | Met | `T40`: same workload, instruments and *N*/*W* as `D40`, throwing mode, where the cap binds (closed Confirmed mechanism of the earlier run) |
| B. Logic | each step says what it establishes | Met | logic steps (1)–(8) of "How this verifies" map onto predictions 1–10 |
| B. Logic | prediction stated in numbers or a clear relation | Met | exact equalities (refusals = warned = `dec bp=BYTES_IN_FLIGHT`; end `A_i` = −*k_i*·*M*), bands ([0.85 *V*, *V*], > *G*, ±10 % per connection), thresholds (64 MiB direct) |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | rows for: confirmed with direct flat / direct following / direct undetermined; exceeds *K* but not *G*; not linear; bounded (Refuted); not decoded; no drift; heap not following; invalid (no refusal, control fails, other overload, OOM) |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (for a negative claim) | disallow evidence: `INSUFFICIENT_*` acquires, warned responses; the positive control shows the binding cap with discards |
| B. Logic | alternative explanations and their controls | Met | another overload path (texts, `TimedOutBeforeProcessing`, timeouts raised to 60 s), path specificity (`L20`), under-limit behaviour (`U10`), the instruments' ability to see a cap (`T40`) |
| C. Specific | a human can follow it from the intro and §9a | Met | |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | arms table, settings, harness README |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `pc72`: JDK 11.0.33, Ant 1.10.12, built `cassandra-base`, Byteman 4.0.20 in `build/lib/jars`, cgroup v2 with the memory controller, `systemd-run --user --scope` works, 40 cores, 125 GiB, 714 GB free on `/mydata` |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≈ 2,560 requests/s through the 50 ms hold, so the largest window (9,600 requests) queues ≈ 4 s, under the 60 s timeouts; heap ≤ ≈ 0.7 GB of decoded values in a 2 GiB heap; direct capped at 2 GiB; scope 6 GiB; trace ≈ 0.5 GB on `/mydata`; total ≈ 12 min |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | the lines listed above |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Vary the capacity as well, at the default reserves | left for stage 3 / a later run | not needed for the claim, which is about the defaults; the earlier run covers the capacity |

**Agreement criteria** — not needed (no run 2 planned unless §5.2 chooses it).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-17, run 1 11:04:57–11:14:58 MST (epoch ms 1794938697307–1794939298841; node logs in UTC) |
| Node | `pc72` (`node2.jason92-326528.misconfiguration-pg0.cloudlab.umass.edu`), x86_64, 40 cores, 125 GiB, 8 GiB swap on (the node's scope has `MemorySwapMax=0`); node and client both on `pc72` (client outside the node's scope) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK | OpenJDK 11.0.33 (node: `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=2G`, G1; client `-Xmx4g`, `conf/jvm11-clients.options`, `-Dio.netty.eventLoopThreads=1`) |
| Ant | 1.10.12 |
| Local source copy | `pc72:/mydata/s4/ntq-recheck/cassandra`, `cp -a` of `/mydata/s4/cassandra-base` (from `systems/cassandra/source/`, `cassandra-5.0.9`, built 2026-11-17) |
| Case-file commit / harness commit | case file `832b828a` + the uncommitted design section (`1c452cd6…`); harness uncommitted, run copy `md5sum`-identical |
| Node budget | `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0` (read back from the scope's `memory.max` / `memory.swap.max`) |
| Storage for node data | `pc72:/mydata/s4/ntq-recheck/node` (local disk) |
| Full logs (outside the repo) | `pc72:/mydata/s4/ntq-recheck/logs/run1/` (`session.log`, `summary.txt`, `arms.csv`, `arms.jsonl`, `ntq.trace`, `stdout.txt`, `system.log`, one folder per arm); shakedowns `logs/shake1/`, `logs/shake2/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown `shake2` (before run 1) | settings table, "Hold" (50 ms) | With 128 executor threads and a 50 ms hold the node serves ≈ 2,560 requests/s, but one client JVM sends only ≈ 2,300–2,550 requests/s of 65 kB (`shake2` `D20`: 43,134 requests in 18 s), so the client set the pace and most of the window sat outside the node (`shake2` `U10` last-third `ΣD` 21.0 MB of a 52.1 MB window; `D40` swinging 11–125 MB) — the design's premise "the window queues in the node" did not hold | hold 250 ms (≈ 512 requests/s), dated amendment in the design's settings table; claim, prediction and conclusions unchanged; `shake3` confirmed the window then stays in the node | 2026-11-17 13:01 EST, before run 1 | uncommitted (section hash `4211db0a…`) |
| 2 | shakedown `shake2` | prediction 10, `OutOfMemoryError` in `system.log` | the harness's text check matched the JVM-arguments INFO line (`-XX:+HeapDumpOnOutOfMemoryError`) | the check looks for `java.lang.OutOfMemoryError` (harness only; the design unchanged) | 2026-11-17, before run 1 | — (harness) |

No defect in run 1 itself: every step of the design (as amended) ran as written.

## 4. Run 1

**Scope:** cluster tier, one node lifetime, arms `idle`, `U10`, `D20`, `D30`, `D40`, `T40`, `L20` at the shipped
defaults (heap 2 GiB). **Command log and excerpts:**
`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided--recheck-2026-11-17/run1/`
(`session.log`, `summary.txt` with every `EXPECTED:` line, `arms.csv`, `arms.jsonl`, `submit-l.txt`, `system.log`,
`trace-new-lines.txt`, `ntq.trace.md5`; per arm `flood.out`, `handlers.csv`, `series.csv`, `jmx-poll.csv`,
`cg-poll.csv`, `meters-*.txt`, histogram excerpts `histo-*.txt`; `D40/trace-excerpt-4fc9b3a4.txt`; the self-check
`selfcheck.py` and `selfcheck.out`). Full trace (126 MB) on the node: `pc72:/mydata/s4/ntq-recheck/logs/run1/ntq.trace`.

Read-backs: *M* = 65,074 B for every small request and 262,074 B for every large one (every `dec` line); *E* =
53,687,091 B and *G* = 214,748,364 B (the `ep=`/`gl=` limits of every configured-reserve `acq` line, = 2,147,483,648/40
and /10); *K_N* = *N*·1,048,576 + *E*; every handler `cap=1048576`, `throw=` the arm's mode; yaml sets none of the knobs;
`-Xms2G -Xmx2G -XX:MaxDirectMemorySize=2G`; scope `memory.max` 6,442,450,944, `memory.swap.max` 0.

### 4.1 Readings

**Default mode, one-frame requests (the claim)** — `arms.csv`, `summary.txt`, `<arm>/handlers.csv`, `<arm>/series.csv`

| Arm | *N* | Client window *V_N* | *K_N* (counted bound) | Refusals Σ*k* (= `dec bp=BYTES_IN_FLIGHT` = client warned) | When | Peak `ΣA` (counted) | Last-third mean `ΣD` (decoded) | `ΣD`/*G* | `ΣD`/*K_N* | End `Σ queueSize` (= −Σ*k*·*M*) | Per handler end `queueSize` | Live `QueryMessage` at 1/3, 2/3 | Live `[B` at 2/3 (idle 16.4 MB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `D20` | 20 | 312,355,200 | 74,658,611 | 3,654 | within 4 s of start | 74,639,878 | 312,337,847 | 1.45 | 4.18 | −237,780,396 | every one = −*k_i*·*M* | 4,800 · 4,800 | 329.0 MB |
| `D30` | 30 | 468,532,800 | 85,144,371 | 5,892 | within 2 s | 85,116,792 | 467,541,506 | 2.18 | 5.49 | −383,416,008 | every one = −*k_i*·*M* | 7,200 · 7,200 | 484.7 MB |
| `D40` | 40 | 624,710,400 | 95,630,131 | 8,132 | within 4 s | 95,593,706 | 624,066,167 | 2.91 | 6.53 | −529,181,768 | every one = −*k_i*·*M* (−11.5 to −13.8 MB) | 9,598 · 9,600 | 643.0 MB |

- Last-third mean `ΣD` per connection: 15,616,892 · 15,584,717 · 15,601,654 B (mean 15,601,088; *W*·*M* = 15,617,760): linear in *N*.
- Every handler's peak `D_i` = 15,617,760 B = *W*·*M* (> *C* = 1,048,576) in all three arms.
- Refusal totals equal *N*·*W* − *K_N*/*M* to within one request (3,652.6 · 5,891.6 · 8,131.5 expected; 3,654 · 5,892 · 8,132 seen): each connection is refused once per request its window holds beyond its share of the bound, then never again.
- During the arms the counted figures stay at the bound: `ΣA` within 2*M* of *K_N* for the whole arm, global reserve in use (`Client.RequestsSize`) 53.5–53.7 MB = the per-IP reserve full (`<arm>/jmx-poll.csv`), while the node holds 4–6.5× that in decoded requests. Each drift release is matched by a new charge, so `queueSize` reads "full" while the uncharged requests sit beside it; it falls to −*k_i*·*M* only when the client stops.
- `RequestDiscarded` +0, client overloads 0, `ovl_other` 0, `err` 0, `outstanding` 0, `TimedOutBeforeProcessing` and `ProtocolException` +0, global reserve back to 0 after each drain.
- Histogram counts lie within `ΣD`/*M* over each histogram's interval ±1 s (6/6); `[B` above idle = 312.5 · 468.2 · 626.6 MB against count × 65,000 = 312.0 · 468.0 · 624.0 MB.

**Controls**

| Arm | Reading | Evidence |
|---|---|---|
| `idle` | direct `MemoryUsed` 58.65 MB, pool 0, live `[B` 16.4 MB, no `QueryMessage` | `idle/jmx-poll.csv`, `idle/histo-1.txt` |
| `U10` (default, *N* 10, *W* 80, window 52,059,200 < *K_10* 64,172,851) | refusals 0; peak `ΣA` = peak `ΣD` = 52,059,200; `ΣD` ≤ `ΣA` at every line; every handler ends at 0 | `summary.txt`, `U10/handlers.csv` |
| `T40` (throwing, same *N*, *W* as `D40`) — positive control | refusals 263,391 = `disc` lines = `RequestDiscarded` +263,391 = client `bytes in flight` overloads; `dec` = `SUCCESS` per handler (no refused request decoded); `ΣA` ≤ *K_40* at every line, peak 95,593,706 (0.9996 *K_40*); `ΣD` ≤ `ΣA`, last-third mean 95,265,082 (0.44 *G*); live `QueryMessage` 1,469 · 1,469 (≤ *K_40*/*M* + 10 = 1,479.6); every handler ends at 0 | `summary.txt`, `T40/*` |
| `L20` (default, multi-frame, window 314,488,800) | refusals 26,987, none decoded with backpressure, warned 0, `dec` = `SUCCESS` per handler; `ΣA` ≤ *K_20* at every line (peak 74,429,016), `ΣD` ≤ `ΣA`; live `QueryMessage` 284 · 284 (= ⌊*K_20*/*M_l*⌋); every handler ends at 0 | `summary.txt`, `L20/*` |
| every arm | no `requests/second`, `spent over`, `timed out before it could start`, `java.lang.OutOfMemoryError`, no `ERROR` line in `system.log`; scope `memory.events` `oom_kill` 0 | `summary.txt`, `system.log` |

**Memory domains** (`<arm>/jmx-poll.csv`, `<arm>/cg-poll.csv`; not predictions except P6)

| Arm | Direct `MemoryUsed` (min / max) | Networking pool `UsedSize`+`OverflowSize` max | Heap used max (before GC) | Scope `memory.current` max |
|---|---|---|---|---|
| `idle` | 58.63 / 58.67 MB | 0 | 0.18 GB | 2.80 GB |
| `U10` | 58.63 / 58.80 MB | 0.66 MB | 1.06 GB | 2.92 GB |
| `D20` | 58.77 / 59.10 MB | 1.31 MB | 1.44 GB | 3.03 GB |
| `D30` | 59.09 / 59.58 MB | 1.97 MB | 1.99 GB | 3.08 GB |
| `D40` | 59.58 / **143.77 MB** (one step of +84.2 MB and +26 buffers in the first 2 s, then flat for the whole arm) | 2.62 MB | 1.96 GB | 3.12 GB |
| `T40` | 143.77 / 143.77 MB | 5.37 MB | 2.05 GB | 3.46 GB |
| `L20` | 143.77 MB / 1.34 GB (count up to 9,073; rises and falls) | 16.5 GB (gauge; above the 2 GiB direct cap, so not bytes held) | 1.42 GB | 4.47 GB |

### 4.2 Conclusion and logic

1. **Validity.** Valid. The limit was reached and passed in every default arm: refusals 3,654 · 5,892 · 8,132, every
   one `INSUFFICIENT_ENDPOINT`/`_GLOBAL` with the per-IP reserve full [observed: `summary.txt`,
   `D40/trace-excerpt-4fc9b3a4.txt`]. Held fixed: every knob under test at its default (yaml read-back, `cap=1048576` on
   all 162 handlers, the mode from the startup option, *E* and *G* from the `acq` lines) [observed: `summary.txt`,
   `trace-new-lines.txt`]; heap and direct sizes, the scope's limits [observed: `summary.txt` `jvm:` and scope lines]. No
   other overload path fired and every client drained [observed: `summary.txt`, `<arm>/flood.out`]. The positive control
   moved: the throwing mode held the same workload to *K_40* [observed: `T40` rows].
2. **Readings.** One frozen threshold missed: P6's 64 MiB line for direct `MemoryUsed` in `D40` (+85.1 MB over idle,
   one step at the arm's start, then flat while `ΣD` ran to 624 MB; the networking pool stayed ≤ 2.6 MB) [observed:
   `D40/jmx-poll.csv`]. Beyond the predictions: (a) the counters sit at the bound for the whole arm (`ΣA` ≈ *K_N*, the
   per-IP reserve full) and the drift is visible only after the client stops [observed: `<arm>/series.csv`,
   `jmx-poll.csv`]; (b) refusals happen only while the window first fills, one per request beyond each connection's
   share, after which every drift release is offset by a new charge [observed: refusal timing in §4.1; inferred: the
   steady state, from `AbstractMessageHandler.java:419-423`, `:461-475`]; (c) the multi-frame control churns direct
   memory (up to 1.34 GB, freed again) and its pool gauge reaches 16.5 GB, a figure above the 2 GiB direct cap and so
   not bytes held [observed: `L20/jmx-poll.csv`]; this is the earlier run's §10 item (5), seen again; (d) the node's
   stdout holds Byteman's per-rule `Rule.execute` lines (129 MB) because `-Dorg.jboss.byteman.verbose=false` turns
   verbose on (Byteman tests the property's presence), inherited from the earlier harness [observed: `stdout.txt` on
   the node; it did not change any reading].
3. **Matched row** — design row 3: *"As row 1 or 2, but direct moves by more than 64 MiB without following `ΣD` (<
   0.5·`ΣD`) → Confirmed — does not cap, for the heap; direct memory: undetermined (recorded)."*
   - Predictions 1–5 and 7–10 hold (79/80 `EXPECTED`): uncharged dispatch (`dec bp=BYTES_IN_FLIGHT` = refusals per
     handler; warned = refusals; no discard) [observed: P1 lines]; the drift (every handler ends at −*k_i*·*M*, exactly)
     [observed: P2 lines, `handlers.csv`]; counted vs real (`ΣA` ≤ *K_N* at every line; last-third `ΣD` 0.999 *V_N*, 1.45–2.91
     *G*; every `D_i` = 15.6 MB > *C*) [observed: P3]; linear in *N* (per-connection means within 0.2 %) [observed: P4];
     heap (live `QueryMessage` = `ΣD`/*M*; `[B` above idle ≥ count × 65,000; count·*M* > *G*) [observed: P5];
     controls `U10`, `T40`, `L20` [observed: P7–P9]; validity [observed: P10].
   - Direct: +85.1 MB in `D40` = 0.136 `ΣD` (< 0.5), flat across the arm and unchanged through `T40` [observed:
     `D40/jmx-poll.csv`, `T40/jmx-poll.csv`] — the condition of row 3.
4. **Excluded rows.** Row 1 (direct flat): the 64 MiB line was crossed in `D40`. Row 2 (direct follows): 0.136 < 0.5,
   and `D20`/`D30` moved < 1 MB. Row 4 (`ΣD` ≤ *G*): `ΣD` ≥ 1.45 *G* in every arm. Row 5 (not linear): within 0.2 %.
   Row 6 (**Refuted**, `ΣD` ≤ *K_N* or flat in *N*): `ΣD` 4.2–6.5 *K_N*, slope *W*·*M* per connection. Row 7 (**Refuted**,
   refused not decoded): every refusal decoded. Row 8 (**Refuted**, no drift): every handler ends at −*k_i*·*M*. Row 9
   (**Refuted**, heap not following): 6/6 histograms in band, `[B` matching. Row 10 (**Invalid**, no refusal or control
   fails): refusals in every `D` arm, `T40` held to *K_40* with refusals = discards. Row 11 (**Invalid**, other overload,
   OOM, not drained): none.
5. **Observed vs. inferred.** The verdict rests on observed counts and exact equalities. Inferred: (i) that the
   `[B` rise is the decoded values' heap copies (`CBUtil.java:443-450`; the byte match is observed); (ii) the steady-state
   reading of item 2(b); (iii) what the one-time +84 MB direct step is (26 new direct buffers when 40 connections
   start — likely read buffers or pool chunks; not followed further), which is why the direct-memory part is
   undetermined rather than refuted.
6. **Deviations and gaps.** The hold was changed from 50 to 250 ms before run 1 (§3, defect 1; the design amended and
   re-hashed, claim and table unchanged). Heap pinned at 2 GiB instead of the 31 GiB `cassandra-env.sh` would choose on
   this node (stated in the design; the reserves still take their heap-derived defaults). Timeouts raised to 60 s
   (design). The client ran on the node, outside the node's scope (one client address; the per-IP reserve binds before
   the global one, so the global reserve is passed by the decoded bytes but is never the binding counter). The Byteman
   verbose output (item 2(d)). The capacity knob itself was not varied (earlier run). No run 2.
7. **Core question.** At the shipped defaults the capacity does not cap the decoded request bytes of one-frame
   requests: the refusals occur (step 1, part 1), each refused request is decoded and dispatched uncharged (step 2,
   P1), its release drives `queueSize` to −*k*·*M* (step 3, P2), the decoded bytes run to the client window — 4–6.5×
   the capacity-plus-reserve bound and 1.45–2.9× the heap/10 global reserve — while the counters report the bound (step
   4, P3), they follow the number of connections with slope *W*·*M* (step 5, P4), and the heap holds them (step 6, P5).
   The same workload in the throwing mode is held to the bound (step 7, `T40`), and multi-frame requests in the default
   mode are held too (step 8, `L20`): the escape is the default mode's one-frame path. Direct memory does not follow the
   decoded bytes; one unexplained 84 MB step leaves that part undetermined.

**Conclusion (one line):** design row 3 — **confirmed, does not cap** (heap); the claim's "and `BufferPool` direct
memory" is not borne out (flat in `D20`/`D30`, one non-following 84 MB step in `D40`: undetermined).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written after run 1, its own tokenizer and arm matching, a time-weighted mean instead of the run
script's per-second samples) re-parsed the full 126 MB trace on the node. Result `run1/selfcheck.out`: **38 ok, 1 FAIL**.
Refusals, peak `ΣA`, peak `ΣD`, end `Σ queueSize` agree with `arms.csv` exactly in all six arms; end `Σ queueSize` =
−refusals·*M* and `dec bp=BYTES_IN_FLIGHT` = refusals in every `D` arm; time-weighted last-third `ΣD` 312.29 · 468.45 ·
624.65 MB, > *G*. The FAIL: `U10`'s last-third mean differs by 2.5 % between the two averaging methods (51.95 vs
50.67 MB); `U10`'s mean is not part of any prediction. The design section's hash was re-computed after run 1:
`4211db0a…`, unchanged.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `summary.txt` read-back and scope lines; `trace-new-lines.txt` (162 handlers, `cap=1048576`); `T40` lines |
| 2. Readings | yes | `D40/jmx-poll.csv` re-read: direct 59,580,478 → 143,769,662 between the first two samples, then 143,769,662–143,769,918 to the end; `D40/series.csv` `ΣA` ≈ *K_40* throughout |
| 3. Matched row | yes | every P1–P10 line in `summary.txt`; `selfcheck.out` |
| 4. Excluded rows | yes | as part 3 |
| 5. Observed vs. inferred | yes | the three inferred items are not load-bearing for row 3 (item iii is why direct is "undetermined") |
| 6. Deviations and gaps | yes | §3 defects; `summary.txt` `jvm:` line (hold 250) |
| 7. Core question | yes | steps 1–8 of the design's logic each cite an observed prediction |

### 5.2 Run 2?

**No** (2026-11-17). The verdict rests on exact equalities reproduced by an independent parser at three connection
counts, with a positive control; the only open item (the direct step) is recorded as undetermined, which a repeat of
the same instruments would not settle (it needs NMT or a buffer-level trace).

## 6. Run 2

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate (the recheck's):** `negative` for one-frame requests in the default mode. **Outcome class:** true
negative (negative, does not cap) for this claim.

**Claim tested:** with every relevant knob at its shipped default and protocol-v5 clients sending one-frame requests
with a large window, a request refused for capacity is decoded and dispatched without being charged, its release
drives the connection's `queueSize` negative, and the decoded in-flight request bytes exceed both the per-connection
capacity and the global reserve (heap/10), grow linearly with the number of connections, and are held on the heap
(and, per the recheck, in `BufferPool` direct memory), while the counters stay within capacity plus reserve.
"Confirmed" means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | not run: the earlier run's unit tier (2026-10-15, u2–u3) already isolates the uncharged decode and the drift; this claim is about a node at its defaults | — | — | — |
| Cluster | **Confirmed** (design row 3): uncharged dispatch, drift to −*k*·*M*, decoded bytes 4.2–6.5× *K_N* and 1.45–2.91× heap/10, linear in connections, held on the heap; direct memory **undetermined** (does not follow; one 84 MB step) | **does not cap** (default mode, one-frame requests; the throwing mode and multi-frame requests are capped) | run 1 + self-check | 2026-11-17 |

**Positive control:** `T40` — the same 40 × 240 window in the throwing mode: `ΣA` and `ΣD` held to *K_40* (95.6 MB),
263,391 refusals all discarded and answered, 1,469 live requests against 9,600 in `D40`.

**Feedback filed:** one dated line in the case file's §10 "Stage-4 feedback" field pointing here; the design section
was appended (and amended once before run 1, §3). Nothing else in the case file changed. Not committed (not asked).
