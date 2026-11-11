# native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous — stage-4 results

> **Case:** [`native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous`](../../stage3-ai-deep-read/cases/native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous.md)
> (target `DatabaseDescriptor.java:3369`, the `-1` sentinel in `setNativeTransportMaxRequestDataInFlightPerIpInBytes`; the per-IP bytes-in-flight limit)
>
> **Status:** verdict filed (run 1 at both tiers + self-check; no run 2) — 2026-10-26
>
> **Outcome class:** true positive — stage-3 estimate `positive` vs the stage-4 effect `caps` (V5 strict; V4 soft, bypass recorded). The cluster tier's formal verdict is *Not confirmed (no matching row)* because one frozen clause (`PausedConnections` max ≥ 1) cannot be met: the gauge goes negative on V5 (see §4.2, §8). Open point for the user.
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster), "§9b–§9e" means B2a–B2e or B3a–B3e, and the
> case file's feedback section is its section D. Set A batch 8, tag `pi`, node `pc12`, port slot 4.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Not committed (untracked file; repo HEAD `93d6365`). sha256 **as filed** `bea9e8ca9c3b264438d98b395429ff80b9f5048248ba550c47ea2168a16aca8e`. **Frozen after the step-0 audit** (2026-10-26) `3836d40f1ccb03af2813e8ce7cc49757b8e7f3f8da32dd566ec42e9914f16f57` (whole file). Prediction and conclusion tables frozen separately: B2f + B2g (`**B2f.` up to `**B2h.`, 30 lines) sha256 `c4e7507af21fd23203320740621670766669132644b9adfb3e3f2f6f220aa8bf`; B3f + B3g (`**B3f.` up to `**B3h.`, 29 lines) sha256 `1fa191014d978cb9eadc6b352949e86452b1de52cf7ea00bbb0aa22c87dd926e` (extracted with `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' <file> \| sed '$d' \| sha256sum`, likewise for B3). Recorded before any harness check or run. Final (after section D feedback): see §8. |
| **Harness** | `harness/native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous/` (not committed); see its README and §1.2 below. |
| **Tiers and values** | Unit: V5 default L = 1 / 4 / 16 MiB x queue Q = 1 MiB / 64 KiB, C = 4, K = 48 messages of ~256 KiB per client; THROW, runtime change, V4 default/THROW, sentinel, controls a/b/c. Cluster: per-IP L = 8 / 32 / 128 MiB at V5 (r1–r3) and V4 (r4–r6), positive control r7 (global 16 MiB), second IP r8, JMX variant r9; 64 connections, 4 MiB blobs, 8 INSERTs per thread, 5 s write hold. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: inbound request payload bytes (pooled direct buffers), counted by `ResourceLimits.Concurrent.using` of the IP's limit object. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly (left) | B2b/B3b vary L three times (1/4/16 MiB; 8/32/128 MiB); the default (`maxMemory()/40`) is covered only by the sentinel check in the unit tier. At the cluster tier the default is about 51 MiB of a 2 GiB heap; a fourth value was not added (left for stage 3; the three values already span 16x). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after R12, R19 | B3d names direct pool, NMT, RSS, heap and the gap (payload share of direct memory). The unit tier measures the counter only, stated in B2d. The audit added the Netty flag needed to see the pool and withdrew the absolute direct-memory figure (R19). |
| A. Core question | usage driven to the limit and past it | Not met → Met after R3, R10, R16 | B2c: 64 messages (16 MiB) do not pass L = 16 MiB with 1 MiB queues (the held total is about 20 MiB); B3c: a 4 MiB write finishes in milliseconds on this node, so the held total need not reach 32/128 MiB (the filed text holds nothing). R3: K = 48 per client; R10: a 5 s Byteman hold. |
| B. Logic | each step says what it establishes | Met | B2e, B3e with controls B2h, B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after R6, R19 | "plateau ≈ L" is not decidable; R6 makes it `L - S < plateau <= L` and the queue term exact; R19 does the same for the cluster counter. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Not met → Met after R7, R20 | B2g/B3g gave meanings, no verdict words, no row for V4 overshoot per connection or a failed control; U1–U5 and C1–C7 added. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after R7, R20 | U3 needs plateaus increasing in L, THROW refusals counted, `endpointUsing()` back to 0; C3 needs peaks in band, `PausedConnections` ≥ 1 and 512/512 ok. |
| B. Logic | alternative explanations and their controls | Met | B2h (global low, unblocked, L = 0 with R8), B3h (global-limit positive control r7, idle baseline, second IP r8, V4 arms). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, B1, A3. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after R3, R4 | "Block the handler like `backPressureTest`" does not hold permits (it relies on the pause); no instruction for sending without waiting; both given in R4. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after R1, R9–R18 | Paths `/local/*`, `pgrep -f`, 5-minute run, "load generator" and "second host" were not runnable as written on a shared node. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Node `pc12` built; test class and scripts are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met after R3, R10, R16 | see A row 4. Data written is 2 GiB through a 512 MiB commit-log cap on tmpfs; heap 2 GiB holds 256 MiB of requests plus decoded mutations. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (two shifts) | `Config.java:296`, `DatabaseDescriptor.java:654-657/914-915/3367-3377/3237-3244`, `ClientResourceLimits.java:84-91/160-162`, `ResourceLimits.java:130-140`, `StorageService.java:7062`, `StorageServiceMBean.java:685` as cited; `getAllocatorForEndpoint` is `:50-58`, not `:73-80` (R2). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Environment: working tree `~/s4-b8-pi` from `copy-source.sh`, not `/local/c509`; `ant testsome` JVM is 1 GiB, so the sentinel is compared with `maxMemory()/40` read in the test | Applied 2026-10-26 (B2a) | HANDOFF Lessons; the filed paths do not exist |
| R2 | Citation `ClientResourceLimits.java:73-80` → `:50-58` | Applied (A3) | wrong range, not load-bearing |
| R3 | Offered load K = 48 messages per client (192, about 48 MiB) so every V5 arm passes L + C·Q | Applied (B2c) | 64 messages do not reach L = 16 MiB |
| R4 | Blocking via a latch in a virtual-table supplier; sending by `channel.writeAndFlush` with pollers; the arm list | Applied (B2c) | `backPressureTest` does not hold permits; `SimpleClient.execute` is one-in-flight |
| R5 | Step 8: raising the limit does not wake paused connections; signal the wait queue, record before and after | Applied (B2e) | `setEndpointLimit` only calls `setLimit` (`ClientResourceLimits.java:84-91`); the existing test signals (`ClientResourceLimitsTest.java:162-167`) |
| R6 | Exact bands: `L - S < plateau <= L`; `admitted - plateau <= C·Q`; V4 overshoot per connection | Applied (B2f) | prediction must be decidable; `PreV5Handlers.java:182-186` is per connection |
| R7 | Verdict lines U1–U5 | Applied (B2g) | no verdict words, no row for V4 per connection |
| R8 | Control (c): L = 0 also sets the message size, or every large message is rejected as too big | Applied (B2h) | `setNativeTransportMaxRequestDataInFlightPerIpInBytes` recomputes the default message size to `min(…, L)` (`DatabaseDescriptor.java:3373-3376`) |
| R9 | Node `pc12`, slot 4 addresses and ports, tmpfs data, PID-based stop | Applied (B3a) | shared node |
| R10 | 5 s Byteman hold at `CommitLog.add` for keyspace `ks` | Applied (B3a) | the larger limits are otherwise not reached; hold-fixed |
| R11 | `write_request_timeout` and `native_transport_timeout` 600000ms | Applied (B3a) | HANDOFF Lessons |
| R12 | `MaxDirectMemorySize` 8g instead of 2g; Netty flag; NMT | Applied (B3a) | a retained-buffer leak would crash the node at 2g and give no reading |
| R13 | `commitlog_total_space: 512MiB`, `max_mutation_size: 16MiB`, `auto_snapshot: false` | Applied (B3a) | disk bound |
| R14 | Client: 64 driver `Cluster` objects, synchronous loops, protocol per run | Applied (B3a) | the case names the python driver |
| R15 | V4 arms r4–r6 at the three values; JMX variant on V5 | Applied (B3b) | the filed V4 control; HANDOFF: large V5 requests leave unreturned direct buffers, so the direct-memory comparison is clean only at V4 |
| R16 | 8 INSERTs per thread instead of 5 minutes | Applied (B3c) | with the hold the run is about 80 s |
| R17 | `RequestsSize` is the primary reading; the by-IP histogram max is a bucket bound | Applied (B3d) | |
| R18 | Run list r1–r9 | Applied (B3e) | |
| R19 | Withdraw the absolute direct-pool figure; exact counter bands | Applied (B3f) | sibling result (1.2 GiB L-independent pool) and the V5 buffer lesson, not readings of this case |
| R20 | Verdict lines C1–C7 | Applied (B3g) | |
| R21 | Second IP `127.0.4.3`, bound by the client | Applied (B3h) | |
| R22 | A fourth cluster value at the default (about 51 MiB at a 2 GiB heap) | Left for stage 3 | already spans 16x; covered by the unit sentinel |

**Agreement criteria** — only if run 2 is chosen; not filled (no run 2 is planned).

### 1.2 Step 1 — instruments (2026-10-26, before any tier run)

| Check | Result | Evidence |
|---|---|---|
| Working tree `~/s4-b8-pi` from `copy-source.sh` (`cassandra-5.0.9`, local one-commit baseline), `ant build-test` | BUILD SUCCESSFUL, 1 min 10 s | `pc12:~/s4-b8-pi-logs/{copy,build-test}.log` |
| Unit test compiles as written | yes, first try (`unit-check.sh`) | `pc12:~/s4-b8-pi-logs/unit-compile.log` |
| Unit test runs; known answer | arm Z (limit 1 GiB, cannot bind; 2 clients x 4 messages of S = 262,205 B, queue 1 MiB): `plateau` = 488 = 2 x (4S - 1 MiB) exactly, `entered` 8, `ok` 8, `final` 0. First attempt failed to start (gossip seed still `127.0.0.1:7012` in the test yaml); the seed and storage ports were moved to `127.0.4.1:7042` in the working tree (harness fix H1) | `pc12:~/s4-b8-pi-logs/unit-check-Z.log` |
| Byteman rule parses and type-checks | `TestScript: no errors` | `bmcheck` output (session log) |
| Python driver imports from `lib/cassandra-driver-internal-only-3.29.0.zip` (path `…zip/cassandra-driver-3.29.0`) | yes | session log |
| Node starts with slot-4 addresses, JMX 7140, hold, Netty flag, NMT; `MaxDirectMemorySize` | `jvm-flag: MaxDirectMemorySize=8589934592` (the later `-XX:MaxDirectMemorySize=8g` wins over `cassandra-env.sh`'s 15872M), `MaxHeapSize` 2 GiB, listening on `127.0.4.1:9042` and `127.0.0.1:7140` only | `run1/cluster/*/run-log-excerpt.txt` |
| Hold works | instrument check 1 (limit 1 GiB, not an experiment value): 62 + 2 writes finished in 11.0 s (two 5-s windows of 32 mutation threads), peak `RequestsSize` 252 MiB, 0 errors | `pc12:~/s4-b8-pi-logs/cluster/check1/` |
| JMX variant works | check 4: trigger at `RequestsSize` 243.6 MB, `JmxSet` read-back unchanged 1073741824 (set to the same value). First version used `invoke`, which fails: the get/set pair is a writable attribute (harness fix H2: `setAttribute`) | `check1/run.log`, `check4/jmxset.txt` |
| Second source IP | check 1 ran with 2 workers bound to `127.0.4.3` (64 of 64 ok); the binding itself is shown in r8 (`ss-mid.txt`: 64 connections from `127.0.4.3`, 128 from `127.0.4.1`) | `run1/cluster/r8-v5-twoIP-32MiB/ss-mid.txt` |
| Instability seen in checks | check 2 (limit 1 GiB): 40 of 62 connections failed `NoHostAvailable` and the server logged CRC mismatches (read value `0xabababab`, the blob byte) on the survivors; checks 1, 3, 4 with the same settings were clean. Not explained; handled by making a run fail when not all connections come up (H3, below) | `pc12:~/s4-b8-pi-logs/cluster/check2/` |

The checks used limits that cannot bind (1 GiB), so none is a reading of a verdict row; no prediction or row was changed after them. Harness
copies and `SHA256SUMS` are in `pc12:~/s4-b8-pi-harness/`.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 19:23–19:27 UTC; cluster 19:27 UTC to 22:21 UTC) |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; shared with other cases (slot 4 only used here) |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` |
| JDK (`java -version`) | OpenJDK 11.0.32.1 |
| Ant (`ant -version`) | 1.10.12 |
| Local source copy | `~/s4-b8-pi` from `cassandra/cassandra-5.0.9/` at repository commit `93d6365` (`copy-source.sh`, local tag `cassandra-5.0.9`) |
| Case-file commit / harness commit | not committed; case-file sha256 `3836d40f…6f57` (§1) for both tiers; harness sha256s in `pc12:~/s4-b8-pi-harness/SHA256SUMS` |
| Storage for node data | tmpfs `/dev/shm/s4-b8-pi` (deleted afterwards); unit tier uses the tree's `build/test/cassandra` |
| Full logs (path, outside the repo) | `pc12:~/s4-b8-pi-logs/` (`unit-run1/`, `cluster/<run>/`) |

Node JVM: G1, `-Xms2G -Xmx2G`, `-XX:MaxDirectMemorySize=8g`, `-Dio.netty.maxDirectMemory=0 -XX:NativeMemoryTracking=summary`, Byteman rule
`hold.btm`; `concurrent_writes` 32; `native_transport_receive_queue_capacity` 64KiB; `native_transport_max_message_size` 8MiB; timeouts 600 s.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| H1 | step 1 | B2a (unit environment) | test node gossip seed `127.0.0.1:7012` unreachable after the ports were moved | seed moved to `127.0.4.1:7042` in the tree's `test/conf/cassandra.yaml` (`unit-run.sh`) | 2026-10-26, before the unit run | harness only |
| H2 | step 1 | B3e step 7 (JMX variant) | `StorageService.setNativeTransportMaxConcurrentRequestsInBytesPerIp` is not an invocable operation (get/set pair = attribute) | `JmxSet` uses `setAttribute` | 2026-10-26, before the cluster run | harness only |
| H3 | run 1 | B3e (client) | python driver: one of 64 connections hangs in its connect phase (r2 attempt 1, r5 attempts 1 and 2, r9 attempts 1 and 2); with the first `loadgen.py` the barrier broke and no load was sent (r2 attempt 1, 37 min lost) | `loadgen.py` exits 3 without sending load unless all workers connect within 240 s; `cluster-run.sh` fails a run without a `RESULT` line; `cluster-all3.sh` retries up to three times. Failed attempts sent no load, are kept on the node as `*-INVALID` and are not readings | 2026-10-26; B3f/B3g unchanged | harness only |
| D1 | run 1 | B3c (run length) | arithmetic: with the cap at L only L/S requests are in flight, so r1 (8 MiB, 512 requests) took 1,287 s, r2 323 s, r3 83 s | no change to r1–r6; r7 and r9 use 4 INSERTs per thread (the amendment said 8 and 16) so they finish in 5–10 min | 2026-10-26 | harness only; recorded as a deviation |

## 4. Run 1

**Scope:** unit tier (all seven tests, 14 arm lines) and cluster tier (r1–r9, 64 connections). **Command logs:** `run1/unit/unit-run.log`,
`run1/cluster/<run>/run-log-excerpt.txt` (full CSVs, NMT samples and node logs on `pc12`). Per-message counted bytes at the cluster tier are
S − 64 KiB = 4,128,836 (S ≈ 4,194,372); unit S = 262,205 (V5), 262,183 (V4).

### 4.1 Readings

**Unit tier** (`run1/unit/U-lines.txt`; 7 tests, 0 failures)

| Arm | Reading | Evidence |
|---|---|---|
| A, V5 default, Q = 1 MiB, L = 1 / 4 / 16 MiB | `plateau` 787,591 / 3,934,051 / 16,519,891; `entered` 19 / 31 / 79; admitted − plateau = 4,194,304 = C·Q in all three; `maxUsing` ≤ L; `ok` 192; `final` 0 | `run1/unit/U-lines.txt` |
| A, V5 default, Q = 64 KiB | `plateau` 786,676 / 3,933,136 / 16,518,976; `entered` 4 / 16 / 64; admitted − plateau = 262,144 = C·Q; `maxUsing` 852,212 (L = 1 MiB), others = plateau; `final` 0 | same |
| B, V5 THROW, L = 4 MiB | `plateau` 3,934,051 ≤ L; `entered` 31, `overloaded` 161 (31 + 161 = 192); `final` 0 | same |
| C, V5 runtime change 4 → 8 MiB | after `setEndpointLimit` alone: 3,934,051 (unchanged), `entered` 31; after the wait-queue signal: 8,129,331, `entered` 47; `final` 0 | same |
| D, V4 default, L = 4 MiB | `plateau` 4,981,477 = L + 787,173 (3.0 messages), `entered` 19; `final` 0 | same |
| E, V4 THROW, L = 4 MiB | `plateau` 3,932,745 ≤ L; `entered` 15, `overloaded` 177; `final` 0 | same |
| S, sentinel | `getEndpointLimit()` 26,407,731 = `maxMemory()/40` | same |
| Xa (global 1 MiB, per-IP 512 MiB) | `plateau` = `globalUsing` = 787,591 ∈ (1 MiB − S, 1 MiB] | same |
| Xb (unblocked, K = 8, L = 16 MiB) | `maxUsing` 0, `final` 0, `ok` 32 | same |
| Xc (L = 0, message size 1 MiB) | `entered` 12 (= C × 3 messages in the queues), admitted 3,146,460 ≤ C·Q, `plateau` 0 | same |
| Z (instrument check, 1 GiB) | `plateau` 488 | same |

**Cluster tier** (`run1/cluster/<run>/summary.txt`; Δdirect = peak BufferPool direct `MemoryUsed` − median of the 20-s idle baseline;
`RequestsSize` samples every 200 ms)

| Capacity value | Run | Peak `RequestsSize` (B) | = n × 4,128,836 | `PausedConnections` max / min | Δdirect (MiB) | Client ok / errors | Run time |
|---|---|---|---|---|---|---|---|
| V5 L = 8 MiB | r1 | 8,257,672 (≤ L 8,388,608) | 2 | 0 / −510 | 1,502.8 | 512 / 0 | 1,287 s |
| V5 L = 32 MiB | r2 | 33,030,688 (≤ 33,554,432) | 8 | 0 / −504 | 1,610.0 | 512 / 0 | 323 s |
| V5 L = 128 MiB | r3 | 132,122,752 (≤ 134,217,728) | 32 | 0 / −480 | 1,652.0 | 512 / 0 | 83 s |
| V4 L = 8 MiB | r4 | 268,438,464 (= 64 × 4,194,351) | — | 64 / 0 | 2,149.5 | 512 / 0 | 82 s |
| V4 L = 32 MiB | r5 | 268,438,464 | — | 64 / 0 | 1,969.5 | 512 / 0 | 82 s |
| V4 L = 128 MiB | r6 | 268,438,464 | — | 64 / 0 | 2,037.5 | 512 / 0 | 82 s |
| V5 global 16 MiB, per-IP 128 MiB (positive control) | r7 | 16,515,344 (global limit 16,777,216) | 4 | 0 / −252 | 1,448.3 | 256 / 0 | 323 s |
| V5 two IPs, per-IP 32 MiB each | r8 | 66,061,376 (≤ 2 × 33,554,432) | 16 | 0 / −495 | 1,644.7 | 512 / 0 | 163 s |
| V5 L = 128 → 8 MiB over JMX | r9 | before the set 132,122,752; ≥ 60 s after the set (2,520 samples) max 8,257,672; knob read back 8,388,608 | 32 → 2 | 0 / −224 | 1,553.0 | 256 / 0 | 570 s |

The `byip_max_peak` (bucketed histogram maximum) was 8.4 / 36.2 / 155.5 MB at r1 / r2 / r3: a bucket bound, not used. 0 `LEAK:` lines and 0
`ERROR` lines in every run's `system.log`. All nine runs connected 64 of 64. Idle direct baseline ≈ 301 MB.

### 4.2 Conclusion and logic

1. **Validity.** Unit: controls valid — Xa moved the plateau to the global limit, Xb never reached the cap and ended at 0, Xc admitted only queue
   bytes **[observed: `run1/unit/U-lines.txt`]**. Cluster: the limit was reached in every limited run (V5 peaks sit one message below L; run times
   scale with 1/L: 1,287 / 323 / 83 s) and the positive control r7 plateaued at 15.75 MiB under a 16 MiB global limit **[observed:
   `run1/cluster/r*/summary.txt`]**; hold-fixed settings confirmed in each `run-log-excerpt.txt` and `yaml.diff` (heap 2 GiB, direct 8 GiB,
   Netty flag, Byteman agent, queue 64 KiB, timeouts) **[observed]**. All nine runs connected 64/64 and had 0 client errors
   **[observed: `summary.txt`]**. Both tiers valid.
2. **Readings.** `PausedConnections` is 0 at its maximum on every V5 run and its **minimum is −224 to −510**: the V5 gauge goes negative (it is
   decremented more often than incremented) **[observed: `run1/selfcheck.txt`, from `run.csv`]**, so it cannot show a pause. On V4 it behaves
   (max 64, min 0). Δdirect is 1.45–2.15 GiB on every run, about 1.1× across a 16× change in L at V5 (1,503 → 1,652 MiB) and not ordered at
   V4 (2,150 / 1,970 / 2,038 MiB) **[observed]**. Peaks are exact integer multiples of the counted message size **[observed]**.
3. **Matched row.** Unit **U3**: every clause holds — all six V5 default arms have L − S < plateau ≤ L and 0 ≤ admitted − plateau = C·Q;
   plateaus increase with L at each Q; THROW refuses 161 and holds ≤ L; runtime arm 8,129,331 ∈ (8 MiB − S, 8 MiB] after the signal; sentinel
   equal; V4 THROW ≤ L; V4 default ≥ L and L + 3 messages (recorded); controls pass; every arm `final` 0 **[observed: `run1/selfcheck.txt`]**.
   Cluster: no row matches. **C3** needs, among other clauses, "`PausedConnections` max ≥ 1 in each" of r1–r3; the readings are 0, 0, 0.
   Every other C3 clause holds (L − S < peak ≤ L in r1–r3; increasing; 512/512 ok; Δdirect r3 > r1 by 10 %; r7 passes). **[observed]**
4. **Excluded rows.** U1 (controls pass; limit reached: entered × S − C·Q ≥ L − S in every arm), U2 (no sample above L in any V5 arm; plateaus
   differ by 15.7 MB; admitted − plateau = C·Q exactly; runtime arm rose), U4 (runtime arm followed after the signal). C1 (knob read back =
   yaml in every run, r1 reached 7.9 MiB ≥ 4 MiB, r7 in band, no client error, node alive). C2 (no V5 peak above L; r1 < r2 < r3). C4 (Δdirect
   r3 − r1 = +149 MiB > 0). C5 (V4 peaks 256 MiB ≤ L + 64·S for all L; r8 63.0 MiB ≤ 64 MiB). C6 (r9 max after 60 s = 8,257,672 ≤ 8 MiB; knob
   8,388,608). **[observed: `run1/selfcheck.txt`]**
5. **Observed vs. inferred.** The unit and cluster counter statements are observed. Inferred: (a) the V5 gauge defect is an accounting error in
   `ClientMetrics.pauseConnection/unpauseConnection` (negative minima are observed; the cause is not isolated); (b) that back-pressure, not
   something else, holds the V5 counter at the cap — supported by the constant `RequestsSize` of 8,257,672 over 5,821 consecutive samples in r1
   and the 1/L run times, not by a pause counter; (c) the ~1.5 GiB direct-memory floor is retained buffers and pool slack (the sibling case
   measured ~1.2 GiB independent of L; HANDOFF lists retained V5 large-request frame buffers), not isolated here.
6. **Deviations and gaps.** H1–H3 and D1 (§3). Sub-predictions missed (do not change the row): B3f's V4 sentence "direct-pool rise increases with
   L at V4 (r4 < r5 < r6)" — the V4 counter is flat at 256 MiB (every connection force-allocates its first request), so no ordering was expected
   in the data, and the direct rise is 2,150 / 1,970 / 2,038 MiB. r7 and r9 ran 4 INSERTs per thread. r1 used the barrier version of `loadgen.py`.
   The held-write hold (5 s) is part of the workload: throughput at L is L/(S − Q)/5 s. The by-IP histogram is a bucket bound and was not used.
   No run 2.
7. **Core question.** The counted per-IP bytes follow the knob exactly on V5: one message below L at 8, 32 and 128 MiB, a third and fourth arm
   with a different limit (global 16 MiB) and a live JMX change to 8 MiB behaving the same way (parts 1, 3, 4). The disallow path is observed at
   the unit tier (admission stops at L, THROW refuses the excess, the connection waits) and at the cluster tier through the constant plateau and
   the 1/L throughput; it is not observed through the pause gauge, which is broken (part 2). On V4 the cap is soft: the first request of every
   connection is force-allocated, so 64 connections hold 256 MiB at any L ≥ 4 MiB before they pause (part 3). The real resource (direct memory) is
   not governed in proportion: it rose only 10 % for a 16× change of L, on top of a ~1.5 GiB floor (part 2, inferred 5c). So the constraint caps
   the counter and the memory it admits, as a hard cap on V5 and a soft one on V4 and for the 64 KiB per-connection queues; it does not bound the
   node's total direct memory.

**Conclusion (one line):** unit **U3 — confirmed**; cluster **C7 — Not confirmed (no matching row)**: the frozen C3 requires `PausedConnections`
max ≥ 1 and the V5 gauge reads 0 at its maximum (it goes negative); every other C3 clause holds.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.txt` (`harness/…/selfcheck.py`) re-parses `U-lines.txt` and each run's `base.csv`, `run.csv`, `client.txt`, `yaml.diff`, `times.txt`,
`jmxset.txt` itself, without `reduce.py`, and evaluates the frozen U and C lines; its values equal `reduce.py`'s.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `U-lines.txt` controls Xa/Xb/Xc; `yaml.diff` and `run-log-excerpt.txt` of each run show the knob and JVM flags; `client.txt` 64/64 connected |
| 2. Readings | yes | recomputed peaks, paused max/min, Δdirect, ok counts from the CSVs: identical to `summary.txt`; the negative paused minima are in `run.csv` itself |
| 3. Matched row | yes | U3 clause list printed true; C3 clause list printed true except the paused clause (`selfcheck.txt`: `PausedConnections max>=1 in each: False [0, 0, 0]`) |
| 4. Excluded rows | yes | printed conditions for C1, C2, C4, C5, C6 and U1, U2, U4 are false as stated |
| 5. Observed vs. inferred | yes | the verdict uses only observed values; the three inferred items are labelled and not used by U3 |
| 6. Deviations and gaps | yes | invalid attempts sent no load (`FAIL_CONNECT`), kept as `*-INVALID`; the B2f+B2g and B3f+B3g hashes recomputed after the runs equal the frozen ones (§8) |
| 7. Core question | yes | the steps follow B1: ceiling follows L (V5 exact), disallow evidence at the unit tier and by plateau constancy at the cluster tier, soft cap on V4; the gap named is the missing pause gauge and the direct-memory floor |

### 5.2 Run 2?

**No** (2026-10-26). The unit result is exact and the cluster counter result is exact in nine runs; a second session would not change the
unmatched clause, which is a property of a broken gauge. The cluster tier is cheap to repeat only after stage 3 decides what replaces the
pause clause (see §8 open point).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps), with the cluster tier formally Not confirmed (below).

**Claim tested (B1):** for one client IP the bytes held by in-flight request payloads stay at or near the per-IP limit plus the per-connection
allowance (and the forced-allocation overshoot) and move proportionally when the limit changes; a flat reading, or one above
L + connections × 1 MiB + one message, shows the claim wrong. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (U3) — V5 plateau 0.79 / 3.93 / 16.52 MB at L = 1 / 4 / 16 MiB (one message below L), admitted − plateau = C·Q exactly, THROW refuses 161, runtime change follows after a wait-queue signal | caps (hard on V5; V4 default soft: L + 3 messages) | run 1 + self-check | 2026-10-26 |
| Cluster | **Not confirmed (no matching row)** (C7) — V5 peak 7.9 / 31.5 / 126.0 MiB at 8 / 32 / 128 MiB, positive control 15.75 MiB, JMX change followed (max 7.9 MiB ≥ 60 s later); the C3 clause "`PausedConnections` max ≥ 1" is 0 on every V5 run because the gauge goes negative | caps (V5 counter exact; V4 soft: 256 MiB at every L; direct memory not proportional) | run 1 + self-check | 2026-10-26 |

**Findings beyond the verdict.** (1) `Client.PausedConnections` goes negative on native protocol V5 under back-pressure (minimum −224 to −510 in
r1–r3, r7–r9; V4 correct): upstream candidate (JIRA check first). (2) V4 default: the first request of every connection is force-allocated, so
64 connections hold 64 × 4 MiB = 256 MiB at any L from 8 to 128 MiB before pausing; the per-IP limit only gates further requests (A3 amendment ii).
(3) The direct-memory rise is 1.45–2.15 GiB in every run (including the 16 MiB global-limit control) and only 10 % higher for a 16× larger L on V5: the limit
governs admission, not the node's direct-memory footprint at this load. (4) A cap of L admits only L/S requests, so throughput at the cap is
L/S per write time; with a 5-s write that is 0.4 request/s at 8 MiB — a client behind a small limit and slow storage looks hung for 20 minutes.
(5) The python driver intermittently fails to bring up one of 64 connections (H3); the earlier check 2 also showed CRC mismatches on V5 with blob
bytes read as the CRC, not reproduced.

**Open point for the user.** The cluster tier is Not confirmed only because a frozen clause names a metric that is broken. If the user prefers,
overrule it to "Confirmed (C3) — caps (V5), soft on V4" and record the date and reason here; the outcome class stays true positive either way.

**Positive control:** not required (positive estimate); the global-limit control r7 (16 MiB) plateaued at 15.75 MiB, so the harness sees a binding
cap.

**Feedback filed:** the case file's section D (audit amendments and stage-4 results). Not committed. Case-file sha256: as filed `bea9e8ca…8e`,
frozen `3836d40f…6f57`, final after section D `6cee01dd54f39ac4310be9c207c1b53081092aa8ff8babc6bb097b5c839ce24c`. The B2f+B2g and B3f+B3g hashes were recomputed after section D and are unchanged (`c4e7507a…a8bf`, `1fa19101…926e`).

## Leftovers on the node

None running (checked `ps` for `s4-b8-pi`, `ss -ltn` for `127.0.4.1` and port 7140: empty). Left on `pc12`: `~/s4-b8-pi` (working tree, 474 MB,
modified `conf/` and `test/conf/cassandra.yaml`, one untracked test file), `~/s4-b8-pi-harness/`, `~/s4-b8-pi-logs/` (34 MB, including the
`*-INVALID` attempts and `check1`–`check4`). `/dev/shm/s4-b8-pi` was deleted.
