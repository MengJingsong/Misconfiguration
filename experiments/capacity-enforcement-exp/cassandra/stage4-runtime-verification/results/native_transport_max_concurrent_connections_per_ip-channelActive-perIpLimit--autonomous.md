# native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous — stage-4 results  <!-- file: results/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous.md -->

> **Case:** [`native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous`](../../stage3-ai-deep-read/cases/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous/`](../harness/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e;
> the case file's feedback section is its section D. Session: Claude Opus 5.5 (claude-opus-5-5), advisor-run, on the advisor's Mac.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Branch `advisor-run`, uncommitted on 2026-10-27 (as filed in `b95104d`'s tree with sha256 `4cceb34d…5f6d`). Frozen after the audit's 13 amendments (U1–U4, C1–C9): sha256 `99c7a5030f79fbc4ebc7340c5a33463464f059fae58e504453270fe85703bb60`, recorded in `_INDEX.md` §4 before any harness run. The unit shakedown then found runbook defect D1 (sha256 `26418c8f…8c24`), and the cluster shakedown D2 and D3 (§3): final sha256 **`ceb0cbc5bb2e7a93d1abb27f8ca397298756b5b248cef3a061e06e805bdcff28`** (fourth §2 row). **Both tiers of run 1 ran at this version.** Section D is filled after this hash. |
| **Harness** | `harness/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous/`: `ConnectionLimitPerIpProbeTest.java` (unit probe, copied into the clone only for the run), `unit-run.sh`; `hold.py` (client, C3), `ntpip.btm` (three observe-only Byteman rules: per-event `NTPIP` lines; the on-demand `NTPIPMEM` line of D2/D3), `cluster-run.sh`; self-check `results/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous/run1/selfcheck.py`. Not committed (the user has not asked for a commit). Reused with attribution: `unit-run.sh` and `cluster-run.sh` adapt the structure and node start/stop functions of `harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/`. The client, rules, workload and every bound are this case's; no value or derivation was taken from another case file or results file (the companion case the filed text points to was not read; C1/C3 replace those pointers). |
| **Tiers and values** | Unit: one test, runs `P-1`, `P2`, `P4` (8 IPs × 8 channels), `ONEIP` (P = 4, 64 channels from one IP), `EDGE` (global 0, P = 4), S = 1,048,576. Cluster: one node (127.0.0.1), P ∈ {-1 (default), 40, 10}, k = 3 source IPs × M = 60 connections, each sending a 9-byte header and S = 4,194,295 bytes of a declared 16,000,000-byte STARTUP body; controls S = 0 (`s = -1`, P = -1), scope k = 1 (P = 10); edge global 0 / per-IP 10. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: live connections per source IP, a count whose byte size is the decoder's cumulation of a partly received envelope (≤ `native_transport_max_frame_size`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b {-1, 2, 4}, B3b {-1, 40, 10}; -1 is the default (`Config.java:290`). |
| A. Core question | real resource measured, not only the counter | Partly | Unit: `readableBytes()` of the decoder buffer (a direct reading of the held bytes, not heap). Cluster: B3d ΔH from heap; found at the shakedown not to see the bytes at all (D2: the cumulation is direct memory); replaced by the native-transport allocator's own capacity metric. The per-IP map was "not observable" (heap dump, no MAT here): replaced by Byteman (C4, D3). |
| A. Core question | usage driven to the limit and past it | Met | M = 8 > P ∈ {2, 4} (unit), M = 60 > P ∈ {40, 10} (cluster); P = -1 positive control. |
| B. Logic | each step says what it establishes | Met | B2h/B3h: positive control, per-address control, S = 0 control, edge. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | Unit exact, but "map values while open" left the step order open (U2/U3). Cluster bands for k = 5 (C2/C6 rescale to k = 3, same relative tolerance). |
| B. Logic | every plausible outcome has a conclusions row | Partly | Missing: over-refusal, missing disallow evidence, instrument failure, byte term outside band while counts right, S = 0 control failing. Added (U4, C7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | Disallow evidence named only as the NoSpamLogger line; added the Byteman `active` values > P and the client's refusals (C4, C7). |
| B. Logic | alternative explanations and their controls | Met | Global path ruled out by global -1; S = 0 control for "bytes from something else"; scope control for per-address. |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 gives the chain to `:102`/`:121`/`:142`. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Not met | B2a, B2d, B3a, B3c point to the companion case ("same as the global case", "/local/probe/hold.py"); `/local`, `ss`, Linux 127/8 routing. Amended (U1, C1, C3, C4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Unit step order and print points, client behaviour, run order, stop conditions open (U2, C3, C5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Only 127.0.0.1–.3 exist on `lo0` (no `sudo` for more): k = 3, scope control k = 1 (C2, C8). |
| D. Runnable | workload arithmetic reaches the limit | Met | 180 × 4 MiB = 720 MiB at P = -1 on a 4 GiB heap node; 64 × 1 MiB in the 1 GiB test JVM. |
| D. Runnable | load-bearing citations spot-checked | Met | Against the clone at `b5f2a54210`: `ConnectionLimitHandler.java:53-54, 60-74, 86-130, 134-148` (target `:102`, increment `:121`, release `:142-144`); `PipelineConfigurator.java:73, 116-127, 136-138, 240-245, 265`; `Envelope.java:197, 425-442`; `Config.java:290`; `DatabaseDescriptor.java:3173-3181`; `StorageProxy.java:2854-2855`; `CBUtil.java:59-60`; `conf/cassandra.yaml:1050-1052`. All as filed. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | U1/C1: this host's clone, paths and node set-up, replacing the pointers to the companion case | applied, amendments 2026-10-27 | `/local` absent; group C |
| 2 | U2/U3/U4: exact unit procedure, a row per printed step, the single-IP control row, added rows | applied | group B, C |
| 3 | C2/C6/C8: k = 3 source IPs, totals 180/120/30, bands scaled by 3/5, scope control k = 1 | applied | only three loopback addresses on this host |
| 4 | C3: `hold.py` specified | applied | the filed text refers to another case's script |
| 5 | C4/C5: `netstat` instead of `ss`; histogram totals instead of `GC.heap_info`; a Byteman rule for the map; exact sequence | applied | macOS; group A, C |
| 6 | C7: rows for over-refusal, missing disallow evidence, instrument failure, byte term, S = 0 control | applied | group B |
| 7 | Stage 3: the claim's per-connection bytes ("decoder-held") live in **direct** memory on a real node even with `cassandra.netty_use_heap_allocator=true`, because `ioBuffer()` returns direct buffers when Unsafe is available; a heap instrument cannot see them (D2) | left for stage 3 (the instrument was fixed by D2) | A2/B3d wording |
| 8 | Stage 3: the logged "by using N connections" value of `ConnectionLimitHandler.java:124` is the `AtomicLong` formatted later, and refused connections stay counted until their `channelInactive`, so the per-IP counter transiently exceeds P + 1 (cluster: up to 46 at P = 40) while the live connections are capped at P | left for stage 3 | A3 step 4 wording |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 04:49:12–04:49:28, cluster 04:49:35–04:58:57 local time, EDT; shakedowns 04:28–04:48) |
| Node | `yangwang-mbp`, the advisor's MacBook Pro (arm64), single host; 10 cores, 32 GiB (`hw.memsize` 34359738368) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64) |
| Ant | Apache Ant 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run52` (`W=~/Library/Caches/stage4`), fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` BUILD SUCCESSFUL in 52 s; Netty 4.1.130.Final; `git status` clean after both tiers |
| Case-file commit / harness commit | case file uncommitted at sha256 `ceb0cbc5…ff28` (on `b95104d`); harness uncommitted |
| Storage for node data | internal SSD, APFS `/dev/disk3s1`, 122 GiB free; unit data under the clone's `build/test`; node files `$W/node-ntpip` (fresh per node start, removed at the end) |
| Loopback / ports / limits | `127.0.0.1`–`.3` on `lo0` (all used as source addresses); 7000, 7199, 9042, 9091 free before the run; `ulimit -n` 1,048,576; `kern.ipc.somaxconn` 128; Python 3.8.11 |
| Full logs (outside the repo) | `$W/logs/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit/` (`clone.log`, `build-test.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-shake2/`, `cluster-r1/`) |

Machine facts relied on: workspace `$W` and `env.sh`; commands touching `$W`/Java run unsandboxed; `-Dlocal.repository=$W/m2` on every ant call; test stdout read from `build/test/logs/**/TEST-<class>.log`; no `setsid` (the node as a tracked background process, `bin/cassandra -f > log < /dev/null`); loopback aliases `.2`/`.3` checked with `ifconfig lo0` (macOS does not route 127/8 without aliases, so k ≤ 3); `CASSANDRA_CONF`/`CASSANDRA_LOG_DIR` outside the clone so it stays clean; `JVM_EXTRA_OPTS` scoped to the node command (a later flag wins); no `jstat`/`GC.heap_info`: `jcmd GC.class_histogram` totals (full GC first) as the heap reading; the Byteman rules type-checked with `TestScript` before use; observe-only Byteman lines instead of a heap dump (no MAT); `pgrep` patterns written as `Cassandra[D]aemon`; long steps in the background and polled; shakedowns of both tiers before run 1; the self-check written before run 1 and run end to end on the shakedowns with its exit status checked. Host facts found here: `/usr/bin/env bash` is bash 3.2 (no `BASHPID`); the tool shell is zsh (a glob with no match aborts the command).

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown (before run 1) | U3 `before` column | U3 assumed a refused channel's close stays queued until `runPendingTasks()`. Netty 4.1.130's `EmbeddedChannel` wraps its `Unsafe` and runs pending tasks when the outermost unsafe call (`register`, `close`) returns (`EmbeddedChannel$EmbeddedUnsafe$1`, `maybeRunPendingTasks` checks `executingStackCnt`), so the `before` state already equals `after`. | `before` cells corrected to equal `after`; the unit disallow evidence named (closed channels with the handler installed, plus the NoSpamLogger line). `after`/`held`/`close`, the claim and rows unchanged. | dated fix D1, 2026-10-27; sha256 `26418c8f…8c24` | uncommitted (on `b95104d`) |
| D2 | cluster shakedown 1 (before run 1) | B3d (3) ΔH | The partly received envelopes are in **direct** memory: `ioBuffer()` returns a direct buffer whenever `PlatformDependent.hasUnsafe()` (`AbstractByteBufAllocator.ioBuffer` bytecode), whatever `cassandra.netty_use_heap_allocator` says, and the cumulation grows in place. The shakedown's heap delta was 1.0 MiB for 36 × 1 MiB. | ΔA = Δ(direct + heap) of `CBUtil.allocator.metric()` (instrumented capacity bytes), printed by an observe-only rule on `StorageService.getReleaseVersion` (`nodetool version`) at baseline, reading and post; same numbers, bands and rows; ΔH kept as informational. | dated fix D2, 2026-10-27; the cluster tier restarted | uncommitted |
| D3 | cluster shakedown 1 (before run 1) | C4 (4) "map after all scripts end = last `inactive` line" | Connections of a killed script close on several event loops in the same millisecond; each rule line reads counter and map at its own moment and prints in no fixed order (shakedown: last line `size=1 map={/127.0.0.1=2}` after a line with `size=0`). | The on-demand `NTPIPMEM` line also prints the shared handler's `mapSize`, `counter` and map; the post reading (≥ 7 s after the kill) is the map after close. | dated fix D3, 2026-10-27; sha256 `ceb0cbc5…ff28` (D2 + D3) | uncommitted |

No defect in run 1 itself: both tiers ran the frozen runbook (at `ceb0cbc5…ff28`) as written. Harness errors fixed before run 1 and not in the case file: in cluster shakedown 1 a `grep -c … || echo 0` produced two lines, the arithmetic on them failed inside a pipeline subshell and that subshell's EXIT trap stopped the node mid-run (fixed: one number, the arithmetic in the main shell, and the trap acts only in the main shell, checked by `$PPID` of a child since bash 3.2 has no `BASHPID`). Shakedown self-check (unit-shake + cluster-shake2, M = 12, S = 1,048,566): 86 checks, 3 failed, exit status 1 — `U.junit` (the shakedown test still asserted the pre-D1 `before` values), and `p40-main.ntpip` / `p40-main.log` (M = 12 < P = 40 cannot refuse). All three are expected for that input; no instrument fault.

## 4. Run 1

**Scope:** both tiers, all values of §1, at sha256 `ceb0cbc5…ff28`. **Command logs:** `native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous/run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/probe.txt`, `run1/unit/TEST-log-excerpt.txt`; JUnit: 1 test, 0 failures, `run1/unit/TEST-*.xml`)

| Run | `after`: open per IP / total; map; counter | held (bytes) | `close`: map size / counter | Predicted (U3 + D1) |
|---|---|---|---|---|
| `P-1` | 8 / 64; `{}` (handler not installed, `handler=false`); 0 | 67,109,440 | 0 / 0 | 8 / 64; empty; 0; 67,109,440; 0 / 0 |
| `P2` | 2 / 16; 2 per IP for all 8; 16 | 16,777,360 | 0 / 0 | 2 / 16; 2 per IP; 16; 16,777,360; 0 / 0 |
| `P4` | 4 / 32; 4 per IP for all 8; 32 | 33,554,720 | 0 / 0 | 4 / 32; 4 per IP; 32; 33,554,720; 0 / 0 |
| `ONEIP` | 4 / 4; `{127.0.0.1=4}`; 4 | 4,194,340 | 0 / 0 | 4 / 4; 4; 4; 4,194,340; 0 / 0 |
| `EDGE` | 0 / 0; `{}` (global branch); 0 | 0 | 0 / 0 | 0 / 0; empty; 0; 0; 0 / 0 |

`before` equals `after` in every run (D1). `held` capacity equals `held` (the test buffers are exact-size). Disallow evidence in the TEST log: "Exceeded maximum native connection limit per ip of 2 by using 3 connections" (`P2`, first refusal; NoSpamLogger suppresses later ones within a minute) and "Exceeded maximum native connection limit of 0 by using 1 connections" (`EDGE`). Note: `handler=` reads whether the first channel's pipeline still holds the handler after registration; for `EDGE` the first channel was closed in `channelActive`, which removes its handlers, so `false` there says nothing about installation (the global-limit line shows the handler ran).

**Cluster tier** — one row per value, run and observable (`run1/cluster/<run>/`):

| Value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| P = -1 | main (k = 3, S = 4,194,295) | `held=` per IP / node-side established per IP | 60, 60, 60 / 60, 60, 60 (total 180) | `pm1-main/hold-*.out`, `netstat-2-9042.txt` |
| | | ΔA (direct + heap of `CBUtil.allocator`) | 754,974,720 B = 720.00 MiB (direct 720, heap 0); 4.0000 MiB per connection | `pm1-main/alloc-base.txt`, `alloc-read.txt` |
| | | ΔH (heap histogram, informational) | +0.3 MiB (`[B` +0.0) | `histo-*-excerpt.txt` |
| | | NTPIP lines; post map | 0 (handler not installed); `mapSize=0 counter=0` | `ntpip.txt`, `alloc-post.txt` |
| P = -1 | S = 0 control (`s = -1`) | held / established | 60 × 3 / 60 × 3 | `pm1-s0/` |
| | | ΔA | 0.00 MiB (limit < 18) | `pm1-s0/alloc-*.txt` |
| P = 40 | main | held / established | 40, 40, 40 (refused 20 each) / 40, 40, 40 (total 120) | `p40-main/` |
| | | ΔA | 503,316,480 B = 480.00 MiB; 4.0000 MiB per connection | `p40-main/alloc-*.txt` |
| | | at the reading: handler map / counter | `{/127.0.0.1=40, /127.0.0.2=40, /127.0.0.3=40}` / 120 | `p40-main/alloc-read.txt` |
| | | disallow evidence | log "per ip of 40 by using 43 connections" (1 line, NoSpamLogger); 328 map entries > 40 in 360 rule lines (max 46) | `cluster/limit-log-lines-all.txt`, `p40-main/ntpip.txt` |
| | | post map | `mapSize=0 counter=0` | `p40-main/alloc-post.txt` |
| P = 10 | main | held / established | 10, 10, 10 (refused 50 each) / 10, 10, 10 (total 30) | `p10-main/` |
| | | ΔA | 125,829,120 B = 120.00 MiB | `p10-main/alloc-*.txt` |
| | | at the reading: map / counter | `{/127.0.0.1=10, /127.0.0.2=10, /127.0.0.3=10}` / 30 | `p10-main/alloc-read.txt` |
| | | disallow evidence | log "per ip of 10 by using 12 connections"; 822 map entries > 10 (max 15) | `limit-log-lines-all.txt`, `p10-main/ntpip.txt` |
| | | post map | `mapSize=0 counter=0` | `p10-main/alloc-post.txt` |
| P = 10 | scope control k = 1 | held / established / ΔA | 10 (refused 50) / 10 / 41,943,040 B = 40.00 MiB; ΔA(k = 3)/ΔA(k = 1) = 3.000 | `p10-scope1/` |
| | | post map | `mapSize=0 counter=0` | `p10-scope1/alloc-post.txt` |
| global 0, per-IP 10 | edge | cqlsh / `held=` / logs / map | "Unable to connect … Connection to 127.0.0.1:9042 was closed", rc 1 / `held=0 refused=5` / 1 global-limit line, 0 per-IP lines / every rule line `size=0`, final `mapSize=0 counter=0` | `edge/` |

Every run: no established :9042 connection before the scripts and after the kill; post heap and post allocator within 0.3 MiB and 0.00 MiB of the baseline; config lines read back from the node's "Node configuration" log line (`run1/cluster/*-config.txt`).

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached and passed at every P > 0: refused 20/IP at P = 40 and 50/IP at P = 10 [observed: `p40-main/hold-*.out`, `p10-main/hold-*.out`]; the global limit was -1 in every run but the edge [observed: `cluster/*-config.txt`]; the heap allocator flag was set as configured (`heapAllocatorFlag=true`) [observed: `alloc-*.txt`]; the unit tier ran every printed step [observed: `unit/probe.txt`, 27 lines].
2. **Readings** — nothing contradicts another. ΔA is an exact multiple of 4 MiB at every value (180, 120, 30, 10 connections) [observed: `alloc-*.txt`], matching the capacity rule of C3 [inferred: Netty `calculateNewCapacity` returns the 4 MiB threshold for 4,194,304 readable bytes]. The rule lines show per-IP counter values up to 46 at P = 40 and 15 at P = 10 [observed: `ntpip.txt`]; these are refused connections still counted until their `channelInactive` runs, not live connections: the client and `netstat` show exactly P per IP and the quiescent map reads P per IP [observed: `hold-*.out`, `netstat-2-9042.txt`, `alloc-read.txt`]. ΔH stays ≤ 0.3 MiB everywhere, as D2 predicts for direct buffers [observed: `histo-*-excerpt.txt`].
3. **Matched row** — Unit B2g row 1: "open per IP = min(8, P), held = open × (S + 9), map empty after close": open per IP 8/2/4, held 67,109,440 / 16,777,360 / 33,554,720 = open × 1,048,585, map size 0 and counter 0 at every `close`, `ONEIP` 4 [observed: `unit/probe.txt`]; disallow evidence: refused channels closed with the handler installed and the per-IP error line [observed: `unit/TEST-log-excerpt.txt`]. Cluster B3g row 1: "held per IP = min(60, P) and ΔA ≈ total × 4 MiB": 60/40/10 per IP, ΔA 720.00 / 480.00 / 120.00 MiB, each inside its C6 band [observed: `hold-*.out`, `netstat-2-9042.txt`, `alloc-*.txt`]; plus C7's confirmation conditions: the per-IP log line and rule values > P at P > 0, the map empty after close, and the scope control ΔA(k = 1) = 40.00 MiB in [36, 52] [observed: `limit-log-lines-all.txt`, `ntpip.txt`, `alloc-post.txt`, `p10-scope1/alloc-*.txt`].
4. **Excluded rows** — Unit: "an IP holds more than P" — no IP above min(8, P), sequential test; "map not empty after all closes" — size 0 in all five `close` lines; "global 0 / P 4 admits" — `EDGE` open 0; "held per channel ≪ S" — held = open × 1,048,585 exactly; U4 (a) over-refusal — counts equal min(8, P); (c) counter leak — counter 0 at every close; (d) invalid — every line present. Cluster: "held per IP > P" — 40 and 10 exactly; "counts capped but ΔA the same at every P" — 720 / 480 / 120 MiB; "ΔA ≪ 300 × 4 MiB at P = -1" (k = 3: 180 × 4 MiB) — 720.00 MiB; "edge admits" — cqlsh refused, `held=0`; C7 (a) over-refusal — no IP below min(60, P); (b) disallow evidence missing — present at both P > 0; (c) map not empty — `mapSize=0` after every run; (d) byte term outside band — all inside; (e) S = 0 control — 0.00 MiB < 18; (f) instrument failure — every line present. The refutation limit (ΔA at P = 10 ≤ 240 MiB) holds at 120.00 MiB. The scope row ("ΔA at P = 10 grows when more IPs are added") is observed as expected: 40 → 120 MiB from k = 1 to k = 3.
5. **Observed vs. inferred** — (i) that ΔA is the decoder's cumulation and not other native-transport buffers: inferred from the S = 0 control (ΔA 0.00 with the same 180 connections) and the 4 MiB-per-connection quantum; (ii) that the allocator metric counts capacity bytes of live buffers: inferred from the Netty bytecode of the instrumented buffer classes (D2), and it returned to 0 after every kill; (iii) that refused connections hold no bytes: inferred from ΔA = held × 4 MiB with refused connections present.
6. **Deviations and gaps** — k = 3 instead of 5 and the scope control at k = 1 instead of 10 (C2, C8; host limit). The heap instrument of the filed design was replaced by the allocator metric (D2); kernel socket buffers and the client side are outside every instrument. The overshoot path (a) of A3 (a race at `:142–:144`) was not exercised (sequential connections per IP; not part of the predictions). The per-IP counter's transient excess over P is recorded but not a row (§1 recommendation 8).
7. **Core question** — Usage follows the constraint: per source IP the node keeps exactly min(M, P) connections and their decoder-held bytes are min(M, P) × 4 MiB, falling from 720 to 480 to 120 MiB as P goes from -1 to 40 to 10 (parts 3, 1), with direct evidence that the refusal branch at `:121-126` fired (part 3) and the release at `:142-144` emptied the map (part 4). The key caps usage per address only: the node total scaled 3.000 × with the number of addresses at fixed P (part 3, scope control), as B1 states.

**Conclusion (one line):** Unit B2g row 1 — confirmed; cluster B3g row 1 ("Confirmed per IP") — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`selfcheck.py` re-read the raw files under `$W/logs/…/unit-r1/` (the TEST log and the JUnit XML, not `probe.txt`) and `cluster-r1/` (`hold-*.out`, `netstat-*.txt`, `histo-*.txt`, `alloc-*.txt`, `ntpip.txt`, the node system logs, the config lines) and re-derived every reading: **86 checks, 0 failed, exit status 0** (`run1/selfcheck.out`). On the shakedown output it ran end to end with exit status 1 and the three expected failures (§3, `run1/selfcheck-shakedown.out`).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster/*-config.txt` (global -1 except edge; per-IP as set), `hold-*.out` refusals 20/50 per IP, `alloc-*.txt` flag `true`; `unit/probe.txt` 27 lines incl. `PROBE end`. |
| 2. Readings | yes | `alloc-read.txt` direct = 754,974,720 / 503,316,480 / 125,829,120 / 41,943,040 = 4 MiB × 180/120/30/10; rule maxima 46 and 15 re-counted from `ntpip.txt` by the script; heap deltas ≤ 0.3 MiB. |
| 3. Matched row | yes | Unit values re-parsed from the TEST log (30 checks); cluster `held`, `netstat`, ΔA bands, log lines, map-empty and scope band re-derived (56 checks). |
| 4. Excluded rows | yes | Each excluded row's reading re-read: close lines size 0; `EDGE` open 0; edge `cqlsh.txt` and `held=0`; S = 0 ΔA 0.00; ΔA(P = 10) 120 ≤ 240. |
| 5. Observed vs. inferred | yes | (i) S = 0 control re-read (`pm1-s0/alloc-*.txt`: 0 → 0 with 180 connections established, `netstat-2-9042.txt`); (ii) the allocator returned to 0 at every `alloc-post.txt`; (iii) ΔA / held = 4 MiB exactly with refused connections in `hold-*.out`. |
| 6. Deviations and gaps | yes | k = 3 / k = 1 recorded in C2/C8; D2/D3 in §3; the race path not tested. |
| 7. Core question — the steps follow the audited logic | yes | knob varied (3 values incl. default) → count = min(M, P) per IP → bytes = count × 4 MiB → refusal and release evidenced → per-address scope shown by k = 1 vs 3. |

### 5.2 Run 2?

**No** — 2026-10-27. Every reading is exact (counts and 4 MiB multiples), the conclusion rests on no inferred statement the self-check could not settle from run 1's files, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** with k source IPs each opening M > P connections that each hold a partly sent envelope of S bytes, each IP keeps exactly min(M, P) connections open; decoder-held bytes are k × min(M, P) × S; with P = -1 all k × M are kept; after every connection closes, the per-IP map is empty. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — row 1 (open per IP = min(8, P), held = open × (S + 9), map empty after close) | caps (per source IP) | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** — row 1 ("Confirmed per IP": held per IP = min(60, P), ΔA = total × 4 MiB at 720 / 480 / 120 MiB) | caps (per source IP; the node total grows with the number of addresses, 3.000 × from k = 1 to 3) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (uncommitted); amendments U1–U4, C1–C9 and runbook fixes D1–D3 in the file (dated 2026-10-27); `_INDEX.md` §4 rows (four hashes) and the §1 Stage 4 cell. No `HANDOFF.md` row was changed (the advisor files are kept apart; §8 of HANDOFF-ADVISOR).
