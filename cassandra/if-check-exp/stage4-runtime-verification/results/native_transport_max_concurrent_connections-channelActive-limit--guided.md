# native_transport_max_concurrent_connections-channelActive-limit--guided — stage-4 results  <!-- file: results/native_transport_max_concurrent_connections-channelActive-limit--guided.md; the stem ends in --guided or --autonomous -->
> **Case:** [`native_transport_max_concurrent_connections-channelActive-limit--guided`](../../stage3-ai-deep-read/cases/native_transport_max_concurrent_connections-channelActive-limit--guided.md)
>
> **Status:** **Closed 2026-10-20** — estimate negative; claim under test: memory does not follow the connection limit. Unit: counts only (open = min(*k*, *L*) at every limit; no memory reading at this tier). Cluster: **Refuted — caps**: live heap follows min(4000, *L*) at 1,329.6 B per idle connection (plus one file descriptor); the positive control moved memory (after defect 1's fix). No run 2.
>
> **Agent:** guided (the suffix of the case-file stem). One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Guided file, hash of §9's text after the audit's amendments (`sed -n '/^## 9\. /,/^## 10\. /p' <file> | git hash-object --stdin`): `52393486b28d1c0f3a5aec5b16b1019a1ddac005`, computed 2026-10-20 before any harness or run. §9a is frozen at this version, including the dated block 9f. Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/native_transport_max_concurrent_connections-channelActive-limit--guided/` (written 2026-10-20 at step 1, before any reading; its README lists each file and its instrument check). Three runbook defects found from the source at step 1 are in §3; §9 was not changed (hash still `52393486…`, checked before run 1). |
| **Tiers and values** | Unit (9a step 1): `ConnectionLimitHandler` in an `EmbeddedChannel`, limits below, at and above *k*. Cluster (9e): one node `-Xmx2G`, limits 500 · 1,000 · 2,000 · −1 (default), 4,000 idle sockets from one address; positive control: 64 connections × 1 MiB with in-flight limits 1 GiB vs 16 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | 9a Claim, 9d: heap, live channel objects and `RssAnon` of connections. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 9b limits 500, 1,000, 2,000 and −1 (the default, off). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | 9d `RssAnon`, heap and the class histogram of channel objects; the JMX gauge counts only handshaken clients, so `ss` is the connection count (trap named). |
| A. Core question | usage driven to the limit and past it | Met | 4,000 sockets exceed every finite limit; 9a row 5 covers fewer connections than the lowest limit. |
| B. Logic | each step says what it establishes | Met | 9a block matches steps, prediction and rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | "Noise band" undefined. **Amended** (R1): range over three repeats of the −1 arm. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows: flat + control lowers (Confirmed), follows `min(4000, limit)` (Refuted), count does not follow (Not confirmed), flat + control flat (Not confirmed), fewer than the lowest limit (Invalid). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs the open count = `min(4000, limit)`, the "Exceeded maximum native connection limit" line / closed sockets, flat memory and the control moving. |
| B. Logic | alternative explanations and their controls | Partly | The control's arithmetic did not bind: 64 × 1 MiB = 64 MiB against a 64 MiB budget, and the per-ip default (heap/40 ≈ 51 MiB) already binds at the default. **Amended** (R2). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Intro explains why the handler is only installed for channels created after the limit is positive. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Knob, JMX attribute and restart rule are exact; the mechanism is not needed to run. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | Values, ulimit, idle timeout (0), sampling at 30 s and reset steps are exact; the control now is (R2). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | `hold_connections.py` and the 64-connection requester are named, not written (step 1); `ulimit -n` ≥ 10,000 on the node. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 4,000 idle sockets × a per-connection base cost of tens of KB is tens to hundreds of MiB against a 2 GiB heap; the 1,500-connection step between 500 and 2,000 is the slope to read. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `ConnectionLimitHandler.java:86-100` (`count > limit`, `ctx.close()`, log text) and `:117-131` (per-ip, `fireChannelActive`), `StorageProxyMBean.java:56-57`, `Config.java:139` (`native_transport_idle_timeout` 0). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Define the noise band (range over three repeats at −1) and the Refuted/Confirmed edges | Applied 2026-10-20 (9a, 9f) | numeric edges fixed before any reading |
| R2 | Control: two arms, in-flight limits both 1 GiB vs both 16 MiB, with 64 × 1 MiB held | Applied 2026-10-20 (9a step 3, 9e C, 9f) | the filed 64 MiB budget is not below the 64 MiB demand and the per-ip default binds first |
| R3 | Write `hold_connections.py` and the held-request client | step 1 (harness) | prerequisites, not design changes |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's runbook observables:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20 (node clock EDT): unit 23:25:52–23:26:05; cluster 23:26:08–23:37 (lifetimes `idle` 23:26–23:31, `C0-1g`, `C0-16m`, `C-1g`, `C-16m` about 1.5 min each). Shakedowns before it (not readings): unit 23:13 and 23:14, cluster 23:15–23:25 | not done |
| Node (CloudLab name and type) | `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (`pc07`), 40 cores, 251 GiB; this session ran on it directly | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 | — |
| Ant (`ant -version`) | Apache Ant 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54`), already built (`environment.md` §7) | — |
| Case-file commit / harness commit | `cd7fec5` (§9 hash `52393486…`, unchanged) / uncommitted at run time (md5 in each `summary.txt`; the repo copy and `~/stage4-harness-run/ncc/` compared equal before run 1) | — |
| Storage for node data | `/dev/sda3` (local ext3), `~/stage4-ncc/data`; nothing on `/proj` | — |
| Full logs (path, outside the repo) | `~/stage4-logs/ncc/run1/unit/` (`ant.log`, `test.out`), `~/stage4-logs/ncc/run1/cluster/<label>/` (`session.log`, `summary.txt`, `ncc.trace`, `histo-*.txt`, `status-*.txt`, `client-*.txt`, `system.log`, `poll-C.csv`), `~/stage4-logs/ncc/run1/selfcheck.txt`; shakedowns `~/stage4-logs/ncc/shakedown{1,2}/` | — |

Cluster node: `-Xms2G -Xmx2G`, G1, `-XX:+AlwaysPreTouch`, epoll transport; yaml `native_transport_idle_timeout: 0ms`, both connection limits −1, `native_transport_timeout` and `read_request_timeout` 120 s; open-file limit 1,048,576 on node and client (`run1/cluster/*/summary.txt`, the `jvm:`, `yaml keys` and `EXPECTED` lines). Control lifetimes add the in-flight limits (global = per-IP) and, for `C-…`, `native_transport_receive_queue_capacity: 0B`.

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | before run 1 (found at step 1 from the source, no reading) | 9a Procedure 3, 9e scenario C, as amended by 9f R2 | The control as frozen cannot bind. Every CQL connection has its own receive queue capacity, `native_transport_receive_queue_capacity`, 1 MiB by default (`Config.java:302`). `AbstractMessageHandler.acquireCapacity:419-426` takes a request from it first and draws only the excess from the in-flight reserves. A 1 MiB request of 1,048,650 B therefore takes 74 B from the 16 MiB reserves, and 64 of them take about 5 KB, so the 16 MiB arm would hold all 64 requests, like the 1 GiB arm. | Run both: the frozen arms `C0-1g` / `C0-16m` as written (source prediction recorded in the harness before run 1: both hold 64 requests), and the positive control `C-1g` / `C-16m` with `native_transport_receive_queue_capacity: 0B` in both arms, so every request byte comes from the reserves R2 sets. The claim, the prediction ("the positive control lowers memory") and the conclusions table are unchanged; R2's "held request bytes … near 16 MiB" becomes true. | 2026-10-20 | §9 not changed (the session's instruction: the §9 hash stays `52393486…`); the fix is recorded here and in the case's §10 |
| 2 | before run 1 (step 1, from the source) | 9d "Live channel objects" | The node uses the epoll transport (`NativeTransportService.useEpoll()`; `netty-transport-native-epoll` is in `lib/`), so a client channel is `io.netty.channel.epoll.EpollSocketChannel`, not `NioSocketChannel`. | Read `EpollSocketChannel`, and record the `NioSocketChannel` row too (always 0). | 2026-10-20 | as row 1 |
| 3 | before run 1 (step 1, from the shipped conf) | 9d "Real resource" | `conf/jvm-server.options:128` sets `-XX:+AlwaysPreTouch`: the whole 2 GiB heap is resident from start, so `RssAnon` cannot show heap growth, only native memory. | No change to the run. The heap is read as the class histogram's `Total` after its full GC (primary) and `GC.heap_info`, both named in 9d; `RssAnon` is still read and reported. | 2026-10-20 | as row 1 |

## 4. Run 1

**Scope:** unit tier (one `ant testsome`, steps u1–u4); cluster tier, one node, five lifetimes: `idle` (arms warm, m1a, L2000, m1b, L1000, m1c, L500; 4,000 idle sockets each, sampled at 30 s) and the control lifetimes `C0-1g`, `C0-16m` (9f R2 as frozen) and `C-1g`, `C-16m` (R2 with defect 1's fix). **Command log:** `native_transport_max_concurrent_connections-channelActive-limit--guided/run1/` (`unit/summary.txt`, `unit/test.out`; `cluster/<label>/summary.txt`, `arms.csv`, `phases.csv`, `client-*.txt`, `refusal-log-lines.txt`; `cluster/idle/histo-{m1a,L500}-{base,held}-top40.txt`, `cluster/idle/trace-kind-counts.txt`; `cluster/C*/poll-C.csv`, `trace-excerpt.txt`; `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

"Live heap" is the class histogram's `Total` after the full GC that `GC.class_histogram` forces (§3 row 3). Every idle reading is taken at 30 s of the hold.

**Unit tier** (`run1/unit/summary.txt`, `test.out`; 1 test, 0 failures, 44 checks, 0 mismatches)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| u1: 100 channels from one address at *L* = 99, 100, 101, 50, −1: open, downstream `channelActive`, `counter` | 99 / 100 / 100 / 50 / 100 each, = min(100, *L*); refused 1 / 0 / 0 / 50 / 0; the 100th channel kept iff 100 ≤ *L*; counter 0 after the close | `unit/test.out` |
| u2: per-IP limit 10, 15 channels from each of two addresses | 10 open per address | `unit/test.out` |
| u3: 3 channels open under 500, limit then set to 2 | the 3 stay open; a 4th is refused; counter 3 | `unit/test.out` |
| u4: `configureInitialPipeline` at (global, per-IP) = (−1, −1), (500, −1), (−1, 10), (0, 0) | handler absent / first / first / absent | `unit/test.out` |

**Cluster tier** — `idle` lifetime (`run1/cluster/idle/summary.txt`, `arms.csv`; band from the three −1 arms, R1)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| −1 (m1a / m1b / m1c) | control (default, 4,000 connections) | open (client / `ss` / live `EpollSocketChannel`) | 4,000 / 4,000 / 4,000 each; no `acc`/`rej`/`ina` line (no handler installed) | `idle/summary.txt`, `client-m1*.txt` |
| −1 | control | live heap | 79,327,392 / 79,412,808 / 79,421,352 B (band 93,960 B) | `idle/summary.txt` R1 |
| −1 | control | `RssAnon`; fd | 2,781,523,968 / 2,797,068,288 / 2,797,219,840 B (band 15,695,872 B); 4,637 / 4,638 / 4,638 | `idle/summary.txt` R1 |
| 2,000 (set live, read back 2000) | A | open; refused | 2,000 (client, `ss`, channels); 2,000 closed by the server, 2,000 `rej` lines (every `n` > 2,000), one log line "… limit of 2000 by using 2035 connections"; counter back to 0 | `idle/summary.txt`, `refusal-log-lines.txt`, `selfcheck.txt` |
| 1,000 (read back 1000) | B | open; refused | 1,000; 3,000 closed, 3,000 `rej`, one log line (by using 1001); counter back to 0 | same |
| 500 (read back 500) | B | open; refused | 500; 3,500 closed, 3,500 `rej`, one log line (by using 501); counter back to 0 | same |
| 500 / 1,000 / 2,000 | A, B | live heap | 74,944,904 / 75,610,488 / 76,939,320 B: L2000 − L500 = 1,994,416 B > 2 × band; segment slopes 1,331.2 and 1,328.8 B per connection → **follows the limit**, 1,329.6 B per connection | `idle/summary.txt` R1 |
| 500 / 1,000 / 2,000 | A, B | live `EpollSocketChannel`; fd | 500 / 1,000 / 2,000 (band 0); 1,138 / 1,638 / 2,638 (1.0 per connection) → follows | same |
| 500 / 1,000 / 2,000 | A, B | `RssAnon` | 2,798,084,096 / 2,796,388,352 / 2,796,101,632 B: spread 1,982,464 B < band → flat | same |
| −1 | control | heap composition per connection (held − base, mean of the −1 arms) | 1,285.5 B: `DefaultChannelHandlerContext` 168 (3 per channel; 4 with the limit handler), `EpollSocketChannel` 128, `Envelope$Decoder` 72, `EpollSocketChannelConfig` 72, … | `selfcheck.txt` |

**Cluster tier** — control lifetimes (64 connections × one 1,048,650-B request, held about 20 s; `run1/cluster/C*/summary.txt`)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| in-flight 1 GiB, queue capacity 1 MiB (as frozen) | `C0-1g` | requests held; reserve in use (`RequestsSize`); live heap held − base | 64; 4,736 B (= 64 × 74, the source prediction of §3 row 1); 76,437,288 B | `C0-1g/summary.txt` |
| in-flight 16 MiB, queue capacity 1 MiB (as frozen) | `C0-16m` | same | 64; 4,736 B; 76,327,160 B — **does not bind** | `C0-16m/summary.txt` |
| in-flight 1 GiB, queue capacity 0 | `C-1g` | same | 64; 67,113,600 B; 76,325,208 B; 64 live `QueryMessage` | `C-1g/summary.txt`, `poll-C.csv` |
| in-flight 16 MiB, queue capacity 0 | `C-16m` (positive control) | same | **15**; **15,729,750 B** (≤ 16 MiB; 49 acquires `INSUFFICIENT_GLOBAL`); **24,627,280 B**; 15 live `QueryMessage` | `C-16m/summary.txt`, `poll-C.csv`, `trace-excerpt.txt` |
| all four | — | client; reserve after release | 64 ok, 0 errors, 0 missing; `RequestsSize` 0 | `C*/client-C.txt` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached and passed at every finite value: 4,000 sockets against 500, 1,000 and 2,000, with 0 connect errors [observed: `idle/client-*.txt`]. The limit took effect: JMX read-back equal to the set value before each burst [observed: `idle/summary.txt`]; open connections = min(4000, *L*) on the client, in `ss` and as live channels [observed]. Hold-fixed settings: per-IP −1 [observed: JMX read at start, yaml]; idle timeout 0 ms [observed: yaml]; open-file limit 1,048,576 on node and client [observed: EXPECTED lines]; `-Xms2G -Xmx2G` [observed: `jvm:` line]. Reset between arms: every socket closed (`ss` 0) and the handler counter back to 0 [observed]. Not fewer connections than the lowest limit, so 9a row 5 (Invalid) does not apply.
2. **Readings** — no outlier. The −1 band is 0.12 % of the live heap; the heap at 500, 1,000 and 2,000 lies on one line (segments 1,331.2 and 1,328.8 B per connection, within 0.2 %) [observed: R1 lines]. The −1 mean (79.39 MB) is 0.21 MB below that line extended to 4,000. That is about 53 B per connection, the size of one `DefaultChannelHandlerContext` (56 B): a channel opened at −1 has 3 contexts, one opened under a limit has 4 [observed: `idle/summary.txt` SAMPLE lines, 12,002 vs 8,002 at 4,000 vs 2,000 channels; inferred: the extra context is the limit handler's]. `RssAnon` does not resolve the heap at all: its band (15.7 MB) is 8 × the whole 500 → 2,000 heap rise. That is the expected effect of `-XX:+AlwaysPreTouch` (§3 row 3) [observed: the flag on the `jvm:` line; inferred: the mechanism]. The "Exceeded…" log line appeared once per limit arm, as `NoSpamLogger` allows (one per minute); the client and the trace count every refusal [observed].
3. **Matched row** — "Memory follows `min(4000, limit)` (a fixed per-connection slope) → **Refuted** — usage follows the constraint, through a per-connection base cost; the rejection is too narrow for idle connections. Record the slope in bytes per connection." Each part:
   - Memory follows min(4000, *L*): live heap rises by 1,994,416 B from 500 to 2,000, against R1's edge of 2 × 93,960 B. The slope is consistent across the three limits [observed: R1].
   - The slope: **1,329.6 B of heap per idle connection** at 500–2,000, and 1,285.5 B per connection opened at −1 (no limit handler). Also one file descriptor per connection, and the live channel objects follow exactly [observed].
   - The disallow branch fired: 2,000 / 3,000 / 3,500 `rej` lines with `n` > *L*, the same number of sockets closed by the server, and the log line [observed].
4. **Excluded rows** —
   - **Confirmed** ("open connections follow the limit, memory is flat across limits, and the control lowers memory"): the heap is not flat; its spread across the limits is 21 × the band [observed]. Only `RssAnon` is flat, and it cannot see heap (part 2), so it is not evidence of flat memory. The control did lower memory (C-16m), but that part alone does not make the row.
   - "Open connections do not follow the limit" (Not confirmed): they follow exactly, on both tiers [observed].
   - "Memory is flat and the control does not move it" (Not confirmed): memory is not flat. The frozen control (C0) did not move, but the fixed one (C) did [observed].
   - "Fewer connections open than the lowest limit" (Invalid): 500 open at *L* = 500 [observed].
5. **Observed vs. inferred** — the conclusion depends on these inferred statements:
   - (a) The live-heap difference between arms is the connections' memory. [Inferred, with support: the arms differ only in the limit; the per-class histogram difference is all Netty channel and pipeline objects plus Cassandra's `InitialConnectionHandler` and `Envelope$Decoder` (`selfcheck.txt`); the −1 band is 94 KB.]
   - (b) `RssAnon` is flat because the heap is pre-touched, not because connections cost no memory. [Inferred from the observed `-XX:+AlwaysPreTouch` flag. The same `RssAnon` did rise in the control lifetimes, where the bytes are off-heap networking-pool frames (pool `UsedSize` 67 MB vs 22 MB).]
6. **Deviations and gaps** —
   - The positive control ran with `native_transport_receive_queue_capacity: 0B` (defect 1). The frozen arms ran too, and did not bind, as the source predicted to the byte (4,736 B).
   - 9d's channel class was read as `EpollSocketChannel` (defect 2).
   - Kernel socket buffers are outside the process and were not read.
   - The per-connection cost was measured for idle, unauthenticated sockets that never send a byte. A connection that completes STARTUP gets a `CQLMessageHandler` and more objects: the control's 64 connections show 3 more handler contexts each, and a `CQLMessageHandler`. Its cost per connection is larger, and the same count limit bounds it as well [inferred].
   - Connections opened while both limits are −1 are never counted (u4; §5 "Not covered"). Only the unit tier exercised that.
   - The unit tier reads counts, not memory.
   - No run 2.
7. **Core question** — usage followed the constraint: the node's heap for client connections rose by 1,329.6 B per connection admitted, and the limit decided how many were admitted. So the count limit caps that memory indirectly, at about *L* × 1.33 KB of heap (plus *L* file descriptors) for idle connections. The steps:
   - (1) The open count = min(4000, *L*) [part 1].
   - (2) The heap follows it [part 3].
   - (3) The positive control shows the instruments see a binding byte cap [§4.1, C-16m vs C-1g].
   - (4) Memory is not flat, so the claim fails [part 4].
   - It does not bound what an active connection's requests hold; the in-flight budget does that (control C).

**Conclusion (one line):** "Memory follows `min(4000, limit)` (a fixed per-connection slope)" — **refuted** (cluster): 1,329.6 B of heap per idle connection; the unit tier confirms the count behaviour only.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-open every raw file the conclusion cites and confirm it says what the
conclusion says. A part that does not hold is fixed, or the conclusion is
downgraded to *Not confirmed*.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
`run1/selfcheck.py` was written after the conclusion. It re-derives the figures from the raw files alone, without `cluster-run.py`'s parsing or `arms.csv`. It reads the client outputs, the Byteman trace cut by `phases.csv` timestamps, every class histogram, the `/proc` status snapshots, `system.log` and the control's poll files. Its result: 55 ok, 0 fail (`run1/selfcheck.txt`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Per arm from the raw client file: open = min(4000, *L*), 0 errors. Per arm from the trace: `acc` numbered exactly 1…*L*, `rej` all with `n` > *L*, 4,000 `ina` ending at 0. No handler line at −1 |
| 2. Readings | yes | The R1 band and slopes recomputed from the histogram files equal the run script's. The `DefaultChannelHandlerContext` counts (12,002 at 4,000 channels with no handler; 8,002 at 2,000 with it) re-read from the SAMPLE lines |
| 3. Matched row | yes | L2000 − L500 = 1,994,416 > 2 × 93,960; segments 1,331.2 and 1,328.8 B; three log lines, one per limit, each with "by using" > *L* |
| 4. Excluded rows | yes | heap spread across the limits / band = 21; `RssAnon` flat (spread 1.98 MB < band 15.7 MB) and recorded as unable to see heap |
| 5. Observed vs. inferred | yes | (a) The per-class difference re-derived: 1,285.5 B per −1 connection, all channel and pipeline classes. (b) `-XX:+AlwaysPreTouch` re-read on the `jvm:` line of every lifetime |
| 6. Deviations and gaps | yes | The control rows re-derived from the raw trace and poll files: C0 64 / 64 held; C 64 vs 15 held; reserve max 15,729,750 ≤ 16 MiB; heap 76.3 vs 24.6 MB |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | 9a's logic steps (1) count, (2) memory, (3) control, (4) compare map to parts 1, 3, §4.1 control, 4 |

### 5.2 Run 2?

**No** (2026-10-20). The result refutes the file's own (negative) claim, which is a reason for a run 2. Against it:
- The readings are exact and repeatable. The channel count is exact at every arm. The three −1 repeats agree within 0.12 %, and the slope is consistent within 0.2 % across the limits.
- The conclusion rests on observed readings. The one inferred statement that could change the row (part 5b) is settled by an observed JVM flag.
- The case file's own Notes predicted this outcome from the source.
- The same choice was made for the other Refuted guided case (`concurrent_compactors`).

## 6. Run 2 — fresh AI session (optional)

Not done.

**Scope:** the tiers and capacity values actually run. **Command log:**
`[case-file stem]/run2/<file>`.

### 6.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier**

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 6.2 Matched row

The §9a row these readings match, in one line.

## 7. Comparison — only if run 2 was done

| Observable | Run 1 | Run 2 | Criterion (§1) | Agree? |
|---|---|---|---|---|

**Same §9a row?** Not applicable (no run 2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative (Rule 2: it bounds the count of connections, not bytes). Left as filed; the refutation is recorded here and in the case's §10.

**Claim tested:** the connection limit does not bound the memory used for client connections; node memory after opening far more connections than the limit is the same as without a limit. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | no memory row at this tier (9a Procedure 1 reads counts): open = min(*k*, *L*) at *L* = *k*−1, *k*, *k*+1, *k*/2, −1; per-IP limit exact; the limit is read only at `channelActive`; the handler is installed only when a limit is > 0 (44/44 checks) | undetermined (counts only) | run 1 + self-check | 2026-10-20 |
| Cluster | **Refuted** — memory follows min(4000, *L*): live heap 74.94 / 75.61 / 76.94 MB at 500 / 1,000 / 2,000 against a band of 0.09 MB at −1 (79.33–79.42 MB at 4,000); **1,329.6 B of heap per idle connection**, plus one file descriptor; disallow fired for exactly 4,000 − *L* sockets | caps (indirectly, for idle connections: about *L* × 1.33 KB of heap) | run 1 + self-check | 2026-10-20 |

**Positive control:** the in-flight byte budget, with `native_transport_receive_queue_capacity: 0B` so the budget carries every request byte (defect 1). 64 connections each held one 1,048,650-B request:
- At 1 GiB, all 64 were held, the reserve held 67,113,600 B, and the live heap rose 76.3 MB.
- At 16 MiB, only 15 were held, the reserve held 15,729,750 B (49 acquires waited), and the heap rose 24.6 MB. All 64 completed after the release.
- The control as frozen in 9f R2 (queue capacity 1 MiB) did not bind: 64 held at both budgets, with 4,736 B in the reserve, as §3 row 1 predicted from the source.

**Where the bytes go (for the case's §8):** an idle, never-handshaken connection costs the node about 1.29 KB of heap: the channel, its config, `ChannelOutboundBuffer`, three or four pipeline contexts, `InitialConnectionHandler`, `Envelope$Decoder` and the address holders. It also costs one file descriptor. The process RSS does not show this cost, because the heap is pre-touched. A connection that completes STARTUP also gets a `CQLMessageHandler` and more objects. Request bytes are bounded by the in-flight budget and the per-connection queue capacity, not by this limit. Side observation: after the control's 1 MiB v5 requests, the networking pool kept `OverflowSize` 67 MB after release, the retention the closed `networking_cache_size` case recorded (its arm L).

**Feedback filed:** the case file's §10 "Stage-4 feedback" field and Notes (2026-10-20), with the three step-1 defects of §3 (§9 not changed, hash `52393486…`). Not committed. `_INDEX.md` and `HANDOFF.md` not edited (the session's instruction); their Stage 4 cell and state rows are left to the coordinating session.
