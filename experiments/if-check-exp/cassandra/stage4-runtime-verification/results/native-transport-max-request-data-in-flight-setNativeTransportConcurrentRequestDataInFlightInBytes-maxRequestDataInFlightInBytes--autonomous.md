# native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous — stage-4 results  <!-- file: results/native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous`](../../stage3-ai-deep-read/cases/native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous.md)
>
> **Status:** verdict filed (run 1 at both tiers + self-check; no run 2) — 2026-10-26
>
> **Outcome class:** true positive — the stage-3 estimate (positive) against the stage-4 effect (`caps only on some paths (bypass)`) ([definition](../README.md#outcome-class))
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

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
| **Case-file version** | Not committed (untracked file; repo HEAD `93d6365`). Whole-file sha256 after the audit amendments (2026-10-26): see the freeze line below. **Frozen prediction and conclusion tables** = text of `B2f` to just before `B2h` plus `B3f` to just before `B3h` (including the 2026-10-26 prediction/verdict amendments placed there), sha256 **`d8015c6e4c6632930a13981873437e82dd355b6d4c3e552188c253ca252ff938`** (refrozen 2026-10-26 19:32 UTC, before run 1 of either tier's readings were read; first freeze `fe9e78cc4ce0…` was computed before any harness check; the only change between the two is the `-XX:MaxDirectMemorySize` value `1g` -> `4g` inside the B3a amendment bullet, found when a cluster shakedown (not a reading) showed that the v5 large-request frame buffers would fill 1 GiB of direct memory in a 90 s V5/256K arm; no prediction or verdict line was touched). Whole-file sha256 after the audit amendments: **`829b6e01c41ff2658c26320ad948b356c3c1323f96a4f9774b1126ec6aeaf977`**. |
| **Harness** | `harness/native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous/` (not committed; the orchestrator commits). `GlobalInFlightLimitProbe.java`, `unit-run.sh`, `NativeFlood.java`, `flood-logback.xml`, `hold-request.btm`, `InflightProbe.java`, `cluster-run.sh`, `cluster-all.sh`, `reduce.py`, `README.md`; sha256 list in "Step 1" below. Copies with the same hashes run from `pc12:~/s4-b8-cr-harness/`. |
| **Tiers and values** | Unit: fresh JVM per mode (sweep L = 1 / 8 / 64 MiB, default, -1, control 1 GiB, v4, msg-default, msg-explicit). Cluster: L = 16 MiB / 64 MiB / default (107,374,182 B) / control 1 GiB x arms V4/256K, V5/256K, V5/100K, plus the live arm (1 GiB -> 16 MiB through JMX); pass 2 repeats 16 MiB only. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes of request bodies in flight (pooled direct buffers plus decoded objects), one permit per byte (`AbstractMessageHandler.java:131`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly -> Met after R3 | B3b has 16 MiB / 64 MiB / default / 1 GiB-class values but its offered load (256 x 256 KB = 64 MiB) does not exceed 64 MiB or the default 102 MB; R3 raises the offered load and fixes the default arm (per-IP pinned). Unit tier B2b has -1 / 1 / 8 / 64 MiB. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met after R2 | B3d names the BufferPool direct MXBean and heap, but says the counter is not exported (wrong: `Client.RequestsSize`, `ClientMetrics.java:129`) and does not set `-Dio.netty.maxDirectMemory=0`, without which Netty direct memory is invisible to that MXBean. R2 adds both. |
| A. Core question | usage driven to the limit and past it | Not met -> Met after R3, R4 | B3c: `cassandra-stress` finishes requests in ms (no hold), offered in-flight 64 MiB never exceeds L = 64 MiB/default; B2c is fine (32 successes then failures). R3/R4: flood client plus Byteman hold, offered 244-250 MiB. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps and B2h/B3h controls; verdict words missing (R5). |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met after R6 | B2f exact. B3f used "about <= L + conns x 1 MiB", "factor of at least 2" with no operand for the real resource or slack; R6 defines Delta, Peak_RS and bound(L) = 1.5 L + 6 MiB (reproducing B3f's 30 / ~100 MiB). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly -> Met after R5 | B2g/B3g have meanings but no verdict words, no row for the control not reaching offered load, none for "counter capped, resource grows" with an effect, none for the live setter, none for an invalid probe. R5 adds U1-U4 and C1-C8. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly -> Met after R5 | B3g row 1 had no disallow evidence; C1 requires `PausedConnections` >= 1 in capped arms and 0 in the control; U1 requires the exact failure counts. |
| B. Logic | alternative explanations and their controls | Partly -> Met after R7 | Control L = 1 GiB and V4/V5 are filed; missing: a control for the known large-v5 frame-buffer residue (R7: V5/100K arm), and the effect of per-IP limit at the unit tier (R1). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly -> Met after R1, R8 | B2c needs `Allocator` (package-private) and a per-IP pin; B2a runs a test class by an unspecified command; B2b "-D is not available" leaves the explicit-size JVM undefined. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met after R1-R4 | Paths (`/local/c509`, `~/cassandra-5.0.9`), `pkill -f`, `ant jar`, the stress command and the sampler loop are replaced by exact node-specific ones in the amendments. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Build via `copy-source.sh` + `ant build-test`; Byteman jar in `build/lib/jars`; client class compiled from the sibling harness; JDK 11, Ant on pc12. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly -> Met after R3, R4 | No data is written (read of an empty table), 4 executor threads x 100 ms hold = ~40 req/s = 10 MiB/s; offered 250 MiB lasts 25 s in saturation of a 90 s load; heap 1 GiB holds 250 MiB of direct buffers plus decoded copies (checked in the shakedown). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (shifts) | `DatabaseDescriptor.java:649-652, 911-912, 3237-3245, 3384-3393`, `Config.java:297-298`, `ClientResourceLimits.java:42, 67-72, 74-76`, `StorageService.java:7044-7054`, `PreV5Handlers.java:182-185`, `ResourceLimits.java:130-143` confirmed; `CQLMessageHandler.java:~216` is `:223`/`:693`; "not an exported gauge" is wrong (Amendment A). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Unit: pin per-IP to 1 GiB (the default maxMemory/40 = 12.8 MB at 512 MiB would bind before 64 MiB); the probe lives in package `org.apache.cassandra.transport` (`Allocator` is package-private) | Applied 2026-10-26 (B2 amendments) | validity of the sweep |
| R2 | Cluster: the counter is exported (`Client.RequestsSize`); add `-Dio.netty.maxDirectMemory=0` so Netty direct memory is visible in `BufferPool direct` | Applied 2026-10-26 (Amendment A, B3 amendments) | the filed instrument list was wrong/incomplete |
| R3 | Cluster: values and arms - default arm with per-IP pinned; offered load 244-250 MiB (> 2 x the default L); live arm through JMX (the path that reaches the target setter) | Applied 2026-10-26 (B3 amendments) | audit group A (limit reached and passed; knob varied) |
| R4 | Cluster: replace `cassandra-stress` by the SimpleClient flood with a Byteman hold; read of an empty table instead of a write | Applied 2026-10-26 (B3c amendment) | stress cannot hold requests, so the limit is never reached; no write noise on heap/disk |
| R5 | Verdict lines U1-U4 and C1-C8 with the effect field | Applied 2026-10-26 (after B2g, B3g) | rows had meanings but no verdict words |
| R6 | Define Delta, Peak_RS, bound(L) | Applied 2026-10-26 (B3f amendment) | operands for a numeric prediction |
| R7 | Add the V5/100K arm as the control for the large-v5 frame-buffer residue; V5/256K kept as filed and judged separately | Applied 2026-10-26 (B3c, B3f) | alternative explanation named by the audit |
| R8 | Node-specific commands: `copy-source.sh` tree, one JVM per mode, kill by PID, tmpfs data | Applied 2026-10-26 (B2a, B3a, B3e/B4) | runnable as written |
| R9 | Stage 3: the "Estimate" line says "usage should plateau near the limit"; a V5 leak (large frames) may make the resource exceed it independently of the knob - the estimate stays `positive`, the arm V5/256K may report a bypass | Left for stage 3 | not a design error |

### 1.2 Step 1 - instruments (2026-10-26, before run 1)

| Check | Result | Evidence |
|---|---|---|
| Tree `pc12:~/s4-b8-cr` made by `copy-source.sh` (repo HEAD `93d6365`, `git status` of `cassandra/cassandra-5.0.9` empty), `ant build-test` | `cassandra-5.0.9`, BUILD SUCCESSFUL in 1 min 12 s | `pc12:~/s4-b8-cr-logs/build-test.log` |
| Unit probe known answer: sweep with a deliberately wrong expectation (`-Dprobe.mutant=1`) | `CHECK sweep successes expected=33 actual=32 MISMATCH`, exit 1 (the checks can fail) | `pc12:~/s4-b8-cr-logs/unit/ki-mutant.out` (first `unit-run.sh instrument`) |
| Unit probe: the v4 mode detects usage > L | `usage_gt_L expected=true actual=true OK` (forced allocate pushes usage to 9 MiB) | `pc12:~/s4-b8-cr-logs/unit/ki-v4.out` |
| Byteman hold rule loads and fires | `Submit -l` lists `ntq hold request`; `hold.trace` has one line per request in every shakedown | shakedown dir `pc12:~/s4-b8-cr-logs/shakedown-*` |
| JMX probe, tmpfs data, port slot 5 | `RequestsSize`, `PausedConnections`, `BufferPool direct` read at 200 ms; node on 127.0.5.1:9042, JMX 7150, agent 19150 | shakedown `run.csv` |
| Live set through JMX | first try used `-s` (jcommander "Expected a value after parameter -s"): script defect fixed to `-ms`; second try read back 16777216 | shakedown `live-set.txt` |
| Warm-up | the first warm-up used the arm's own value size; for V5/256K it left a direct-memory residue (baseline 772 MiB vs 232 MiB): warm-up value size set to 20000 B | shakedown `sh-v5-256k` |

Shakedowns (`sh-v4-16MiB`, `sh-live`, `sh-v5-100k`, `sh-v5-256k`, shorter load times) are instrument checks, not readings; none is cited as evidence. Harness sha256 (the files run 1 uses):

```
306091b302c1f65dc6547f3df51f5514af44e54a3d287ac54a4ad3aeb4fd314e  cluster-all.sh
4eff7f8bc336fc3c90d600b4287bcd4f87377d6c4e3f7ff42dbd8860f1ef73a7  cluster-run.sh
2505fa72d313135c2ac65be094efafad163b8c18eb41715ec5885a48db86fc03  flood-logback.xml
c308da9c5805e10fbde67bdb10c7a4fc2ad902764684954391da2d32284e2151  GlobalInFlightLimitProbe.java
3b34a0ed10ba1fdeb8374e20d3fed4e575fbc214b22b4b1ec93d941f181b6a71  hold-request.btm
cbf1d621a949a7f5c2be80431caefc7cb9ecb4546d553e4905babde1a548affe  InflightProbe.java
5b3af643d59dd538ad0233c9608cb36d6aa2ae7bf1a20eaef0af183534c95441  NativeFlood.java
764857de10d1bdd29506e9d76c4090a004a2448726f7eae7e145ad8cb01d111b  README.md
9ba00454d8ce7be57b2aaf87df465dabc4375bde38f1c44a63edc34118754c8f  reduce.py
cb733501056f6efff31d9380ac44256e95a2029500844f77f48245acb320acf4  unit-run.sh
```

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 19:06 UTC; cluster arms 19:30-20:38 UTC; diagnostic arms 20:38-20:50 UTC) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB) | - |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, `5.15.0-187-generic` | - |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | - |
| Ant (`ant -version`) | 1.10.12 | - |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `pc12:~/s4-b8-cr`, `copy-source.sh`, repository HEAD `93d6365`, tag `cassandra-5.0.9`, `ant build-test` once, never rebuilt | - |
| Case-file commit / harness commit | case file and harness not committed (untracked, repo HEAD `93d6365`; the orchestrator commits); case-file sha256 `829b6e01…df336bb` at freeze, harness sha256 list in 1.2; `cluster-run.sh` was changed after run 1 (the optional `HIST_TOP=1` diagnostic, new sha256 `b77efd06…2e4`); run 1's arms ran with the 1.2 hash `4eff7f8b…c7a73` | - |
| Storage for node data | tmpfs `/dev/shm/s4-b8-cr-data` (removed after each arm); no data is written by the workload | - |
| Full logs (path, outside the repo) | `pc12:~/s4-b8-cr-logs/{unit,cluster,shakedown-1}/` (cluster: one folder per arm with `run.log`, `base.csv`, `run.csv`, `nmt.txt`, `client.txt`, `hold.trace`, `logs/system.log`) | - |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | step 1 (shakedown) | B3a `-XX:MaxDirectMemorySize=1g` | v5 large-request frame buffers fill 1 GiB in a 90 s V5/256K arm (shakedown showed +550 MiB at 40 s) | `4g`, in the audit's B3a bullet | applied 2026-10-26 before run 1; prediction and verdict lines unchanged; the freeze hash was recomputed (1.1) | not committed |
| D2 | step 1 (shakedown) | B3e live set | `nodetool sjk mx ... -s` takes a value (jcommander error) | `-ms -v 16777216` | applied in the harness before run 1 | harness only |
| D3 | step 1 (shakedown) | B3e warm-up | warm-up with the arm's own 256 KiB value left a direct-memory residue (V5: baseline 772 MiB) | warm-up value 20,000 B | applied in the harness before run 1 | harness only |

No defect arose during run 1 itself (16 of 16 arms ended with a summary; no arm stopped at the first-trigger check).

## 4. Run 1

**Scope:** unit tier (8 fresh JVMs); cluster tier: L = 16 MiB, 64 MiB, default (107,374,182 B), control 1 GiB x arms V4/256K, V5/256K, V5/100K (pass 1, 12 arms), the live arm (1 GiB -> 16 MiB through JMX), and pass 2 at 16 MiB (3 arms). **Command log:** `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous/run1/unit/unit-run.log`, `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous/run1/cluster/<arm>/run-excerpt.log`, `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous/run1/cluster/all.log`; per-second series `run-1s.csv`, `base-1s.csv`; diagnostics `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous/run1/diag/`.

### 4.1 Readings

**Unit tier** (`run1/unit/*.lines`; all 68 CHECK lines `OK`, 0 `MISMATCH`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `sweep` L = 1 / 8 / 64 MiB (4 threads, 262,144-B chunks): successes 4 / 32 / 256, failures 16 (all `INSUFFICIENT_GLOBAL`), usage after fill = L, max usage seen <= L, half released then refilled exactly, usage 0 after release | 13 checks OK in each JVM | `sweep-1MiB.lines`, `sweep-8MiB.lines`, `sweep-64MiB.lines` |
| `default`: limit at startup and after `setGlobalLimit(-1)` = maxMemory/10 | 53,687,091 = 536,870,912 / 10, both | `default.lines` |
| `control` L = 1 GiB: 48 of 48 succeed, 0 failures | OK | `control-1GiB.lines` |
| `v4` L = 8 MiB: after the fill `tryAllocate` fails 4 times, each followed by a forced `allocate`: usage 9 MiB = L + 4 x 262,144 > L; later `tryAllocate` all fail; 0 after release | OK | `v4-8MiB.lines` |
| `msg-default`: message size = min(`max_mutation_size` 2,621,440; L; per-IP) after `setGlobalLimit` 1 MiB (1,048,576) and 64 MiB (2,621,440) | OK | `msg-default.lines` |
| `msg-explicit` (yaml 1 MiB): 1 MiB at start; 1 MiB after `setGlobalLimit(64MiB)`; 524,288 after `setGlobalLimit(524288)`; still 524,288 after `setGlobalLimit(8MiB)` | OK | `msg-explicit.lines` |

**Cluster tier** — one row per arm (Delta = peak `BufferPool direct` over the 30 s idle baseline; "live heap" = `GC.class_histogram` total at 60 s of load minus at the baseline; both are in `run1/cluster/<arm>/summary.txt` and `hist.txt`):

| Pass | L | Arm | Peak RequestsSize (MiB) | /L | Delta direct (MiB) (bound = 1.5 L + 6) | max PausedConnections | responses with "bytes in flight" warning | live heap at 60 s (MiB) | ok/s |
|---|---|---|---|---|---|---|---|---|---|
| p1 | 16 MiB | V4/256K | 16.75 | 1.047 | 128.0 (30) | 4 | 3271 | +16.8 | 39.3 |
| p1 | 64 MiB | V4/256K | 64.52 | 1.008 | 208.0 (102) | 4 | 3154 | +64.9 | 39.3 |
| p1 | default | V4/256K | 103.03 | 1.006 | 320.0 (159.6) | 4 | 2777 | +103.5 | 39.2 |
| p1 | 1 GiB | V4/256K | 250.07 | 0.244 | 576.0 | 0 | 0 | +251.4 | 39.2 |
| p1 | live | V4/256K | 250.07 | - | 576.1 | 4 (after the set) | 3208 | +16.6 | 39.3 |
| p1 | 16 MiB | V5/100K | 15.95 | 0.997 | 64.1 (30) | 4 | 2351 | +246.5 | 39.3 |
| p1 | 64 MiB | V5/100K | 63.95 | 0.999 | 64.1 (102) | 4 | 1848 | +246.6 | 39.3 |
| p1 | default | V5/100K | 102.32 | 0.999 | 64.0 (159.6) | 4 | 1446 | +246.4 | 39.3 |
| p1 | 1 GiB | V5/100K | 240.32 | 0.235 | 64.0 | 0 | 0 | +246.4 | 39.3 |
| p1 | 16 MiB | V5/256K | 15.76 | 0.985 | 784.4 (30) | 0 (gauge goes to -4501) | 0 | +20.3 | 39.2 |
| p1 | 64 MiB | V5/256K | 63.77 | 0.996 | 819.4 (102) | 0 | 0 | +68.8 | 39.1 |
| p1 | default | V5/256K | 102.28 | 0.999 | 812.4 (159.6) | 0 | 0 | +107.5 | 39.3 |
| p1 | 1 GiB | V5/256K | 246.07 | 0.240 | 818.8 | 0 | 0 | +252.5 | 39.1 |
| p2 | 16 MiB | V4/256K | 16.50 | 1.031 | 96.0 (30) | 4 | 3629 | +16.4 | 39.2 |
| p2 | 16 MiB | V5/100K | 15.95 | 0.997 | 64.0 (30) | 4 | 2351 | +246.4 | 39.3 |
| p2 | 16 MiB | V5/256K | 15.76 | 0.985 | 784.5 (30) | 0 | 0 | +20.4 | 39.3 |

Live arm (`run1/cluster/p1-live-v4-256k/`): before the set Peak_RS 250.07 MiB (offered 250.0); `NativeTransportMaxConcurrentRequestsInBytes` read back 16,777,216 after the set at +30 s of load; `RequestsSize` then fell monotonically at about 10 MiB/s (0 up-steps) and reached <= 20 MiB 22.9 s after the set, then stayed at 16.0-16.25 MiB for the remaining load (460 samples, max 19.26 MiB with the client drain).
Diagnostic arms (not rows; `run1/diag/`): `x1-16MiB-v5-100k` class histogram at 60 s: `[B` 272.5 MB live (109,219 instances); `x1-16MiB-v4-256k` at 60 s: `[B` 33.1 MB.

### 4.2 Conclusion and logic

1. **Validity** — [observed: `cluster/*/summary.txt`, `selfcheck.out`] The limit was reached in all 12 capped arm-passes (Peak_RS 0.985-1.047 L) and the control reached 0.80-1.00 of the offered load; each hold-fixed setting is confirmed per arm in `run-excerpt.log` (`jvm-arg:` lines: `-Xmx1G`, `-Dio.netty.maxDirectMemory=0`, `-XX:MaxDirectMemorySize=4g`, the Byteman agent with `hold-request.btm`; `yaml:` lines; `limits.txt`: global limit at start = L and per-IP = L; default arm 107,374,182). The hold fired for every request (`hold lines` = requests sent in all arms), every client drained with 0 errors, `system.log` has no OutOfMemoryError and no ERROR, the idle baseline had `RequestsSize` 0 and a constant direct pool (spread 0.0 MiB). Valid.
2. **Readings** — [observed: table in 4.1] (a) `PausedConnections` goes negative in the V5/256K arms (down to -4501 in the three capped arms, -4496 in pass 2): the gauge is unusable there, so prediction 3 ("Paused >= 1") is not met for V5/256K, which has no pause and no warning in any response; the counter plateau at 0.985-0.999 L for the whole load is then the only direct sign of refusal. (b) The direct pool grows in steps of 16 MiB (Netty chunk size) and does not fall back within the run. (c) V5/100K and V5/256K Delta is flat across L (64.0-64.1 MiB; 784-819 MiB) including the 1 GiB control. (d) The live heap of V5/100K is +246.4-246.6 MiB in all five V5/100K runs, a constant to 0.2 MiB, which equals the offered load 2560 x 100,000 B = 244.1 MiB plus overhead.
3. **Matched row** — **no single row of B3g covers the tier; the rows match per arm type:** C3 for V4/256K [observed: Peak_RS 16.75 / 64.52 / 103.03 MiB <= L + 4 MiB, Delta 128.0 / 208.0 / 320.0 MiB > bound 30 / 102 / 159.6 MiB in the three capped values, 96-128 MiB at 16 MiB in two passes]; C2 for V5/100K [observed: Delta 64.1 / 64.1 / 64.0 / 64.0 MiB across 16 MiB / 64 MiB / default / control, spread 0.2 %, with offered load 244 MB above every capped L]; C3 and C2 for V5/256K [observed: Delta 784-819 MiB at every L, spread 4 %, bound exceeded]. C1 does not hold (its V4/256K and V5/100K predictions 2 and the ordering fail). Prediction 1 (Peak_RS <= L + 4 MiB), the limit-reached check and the "client other_err = 0" check hold in all 12 capped arm-passes; prediction 3 holds in V4/256K and V5/100K (Paused 4, warnings 1446-3629) and fails in V5/256K; prediction 4 (control reaches 0.8 offered, no pause) holds for all three arm types; the live arm holds (C7 does not apply).
4. **Excluded rows** — C1: the Delta bound and ordering fail (V4/256K Delta/bound = 4.3 / 2.0 / 2.0; V5/100K not increasing). C4 (Peak_RS > L + 4 MiB): excluded, the highest Peak_RS over L is +0.75 MiB (V4/256K, 16 MiB). C5 (limit not reached): excluded, Peak_RS/L >= 0.985 and Paused >= 1 in V4/256K and V5/100K. C6 is informational: V4/256K exceeded the same-L V5/100K Peak_RS by 0.80 / 0.57 / 0.71 MiB (< 2 x 4 x 256 KiB = 2 MiB). C7: excluded (live arm holds). C8: excluded (baseline spread 0.0 MiB). U2 (unit): excluded, no success with usage > L.
5. **Observed vs. inferred** — Inferred and relied on: (i) that a pooled direct-buffer delta over a baseline is the memory the requests occupy (the 16 MiB step is the Netty chunk size; the V4/256K Delta is 4.3 x bound at 16 MiB but the live heap there follows L almost exactly: +16.8 / +64.9 / +103.5 / +251.4 MiB against L = 16 / 64 / 102.4 / offered 250), so the direct Delta mixes the request bytes with retained pool chunks; (ii) that the V5/100K live heap (`[B` 272.5 MB at 60 s) is the request bodies read and copied onto the heap before the in-flight limit applies (the diagnostic arm shows the bytes are live `byte[]`; the cause in `CQLMessageHandler`/`FrameDecoder` was not traced to a line); (iii) that the V5/256K growth is the known large-request frame-buffer residue (the V5/256K Delta is the same at every L and is flat on the live heap; the leak itself was not re-proved here).
6. **Deviations and gaps** — the workload is a read of an empty table with the value as a predicate (no write), with a Byteman 100 ms hold at `Dispatcher.processRequest` and four executor threads (audit amendment); `cassandra-stress` was not used. Pass 2 repeats only 16 MiB. The 30 s baseline (not 60 s). The direct-memory pool, not the process RSS, is the primary real-resource signal; NMT "Other" is recorded and moves with it (`nmt_other_peak_over_base_MiB` is within 1 % of the Delta in every arm). Heap is read as one live-heap total at 60 s per arm, not as a series. `PausedConnections` is unreliable for V5 large messages. One run per (L, arm) in pass 1.
7. **Core question** — [inferred from 2-6] The counter does what the code says: `GLOBAL_LIMIT` is never above L plus about one request in any arm and the live setter takes effect within one drain (hard on the V5 path, soft by one request per connection on V4; unit tier exact). The request memory follows the limit on the V4 path and on the V5 large-message path as live heap (+L to within 5 MiB), but not as the direct pool (Delta 2-4 x the bound), and on the V5 small-message path it does not follow the limit at all (live heap +246 MiB at every L); the V5 large path additionally grows the direct pool by 780-820 MiB per run independent of L. So the constraint caps the counter everywhere and caps the memory only on some paths (bypass).

**Conclusion (one line):** unit tier **U1** — Confirmed, caps; cluster tier — **Refuted** (the claim's second half): rows **C3** (V4/256K) and **C2** (V5/100K, V5/256K), counter capped in every arm — effect `caps only on some paths (bypass)`.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Done by `run1/selfcheck.py` (output `run1/selfcheck.out`; 165 checks OK, 0 failed), which re-parses `base.csv`, `run.csv`, `times.txt`, `client.txt`, `hold.trace`, `limits.txt`, `run.log` and `system.log` of every arm on the node without using `reduce.py`, compares with `summary.txt`, and evaluates the predictions and orderings; the live arm and the heap numbers were re-read from `live-set.txt`, `hist.txt` and `run.csv`.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: peak RS, Delta and Paused equal `reduce.py` in all 16 arms; limits at start match; JVM args present; hold lines = sent; clients drained with 0 errors; 0 OOM and 0 ERROR (the first self-check pass counted the `HeapDumpOnOutOfMemoryError` JVM argument as an OOM; the regex was corrected, nothing else) |
| 2. Readings | yes | negative `PausedConnections` seen in `run-1s.csv` (`paused_min` -4501 / -4304 / -4146 / -4496) only in the capped V5/256K arms; the V5/256K control stays at 0; V5/100K live-heap equality re-read in all five `hist.txt` |
| 3. Matched row | yes, per arm type | the tier has no single row; C3 / C2 assignments recomputed from `selfcheck.out` ("frozen predictions per arm", "ordering") |
| 4. Excluded rows | yes | C4 excluded by max(Peak_RS - L) = +0.75 MiB; C5 by Peak_RS/L >= 0.985 and Paused >= 1 (V4, V5/100K) |
| 5. Observed vs. inferred | partly | (i) and (iii) rest on the 16 MiB chunk granularity and on the known residue, not on a trace; (ii) is a histogram of the diagnostic arm; no part contradicts a reading |
| 6. Deviations and gaps | yes | listed above |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's two halves are answered separately: counter half holds, plateau half fails by the direct pool in all V4/V5 arms and by the live heap in the V5 small path |

### 5.2 Run 2?

**No** (2026-10-26). The unit tier is exact; the cluster conclusion rests on observed numbers that repeated within run 1 (pass 2 at 16 MiB: Delta 96.0 / 64.0 / 784.5 MiB against 128.0 / 64.1 / 784.4 MiB in pass 1, Peak_RS and warnings alike; the V4 Delta differs by one 16 MiB chunk). The inferred parts (5.ii, 5.iii) would need a trace, not a second run of the same readings. A rerun that could change the answer: a V5 small-message arm with the Byteman hold removed, or a trace of where the frames are copied, which stage 3 can design.

## 6. Run 2 — fresh AI session (optional)

Not done (5.2).

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (soft cap). **Outcome class:** **true positive** (positive, `caps only on some paths (bypass)` counts as `caps`). A reader who weights the V5 small-message path (live heap +246 MiB at L = 16 MiB) as the default client behaviour could class it a false positive; that is the one judgement in this file.

**Claim tested:** (B1) the global in-flight counter never exceeds `native_transport_max_request_data_in_flight` by more than the documented overshoot, and the node's actual native-transport request memory plateaus near that limit when it is lowered, instead of growing with offered load. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **U1 — Confirmed** (68 of 68 checks; the V4 forced `allocate` takes usage to L + 1 MiB as traced) | caps (hard through `tryAllocate`; overshoot only through the forced `allocate`) | run 1 + self-check | 2026-10-26 |
| Cluster | **Refuted** — C3 (V4/256K) and C2 (V5/100K, V5/256K); counter capped within +0.75 MiB of L in all arms, live setter effective, request memory follows L as live heap on V4 and V5-large but not as the direct pool, and not at all on V5 small messages | caps only on some paths (bypass) | run 1 + self-check | 2026-10-26 |

**Positive control:** not applicable (positive-estimate file; the 1 GiB control arms showed usage moves with the offered load: Peak_RS 240-250 MiB, live heap +250 MiB).

**Feedback filed:** the case file's section D updated (not committed; final whole-file sha256 `e828df09072c5ac9224af67f7b1bc63d7b0cc4dc372ec93a1f71fb9cb7d2834f`) and no other section amended; the audit amendments of 2026-10-26 (A, B2, B3, B2f/B2g, B3f/B3g) are in the case file next to the text they change.

**Upstream / doc candidates (JIRA check first):** (1) `Client.PausedConnections` goes to about -4500 over a 90 s V5 run of 256 KiB requests (unpause without pause on the large-message path; `ClientMetrics.java:145`, `CQLMessageHandler`); (2) native-v5 requests below `LARGE_MESSAGE_THRESHOLD` are read and copied onto the heap in full while `RequestsSize` sits at L (live `byte[]` 272.5 MB at L = 16 MiB, equal to the offered load): the in-flight limit bounds admission to the executor, not what the connection buffers; (3) the large-v5 frame-buffer residue reproduced (direct pool +780-820 MiB per 90 s, flat in L; already in HANDOFF's list). 

**Leftovers on the node:** no process of this case is running (checked with `pgrep -x java` and `ss`); `/dev/shm/s4-b8-cr-data` removed by the script; directories remain on `pc12`: `~/s4-b8-cr` (tree, 471 MB), `~/s4-b8-cr-logs` (27 MB: unit, cluster, shakedown-1), `~/s4-b8-cr-node`, `~/s4-b8-cr-harness`, `~/s4-b8-cr-unitwork`, `~/s4-b8-cr-excerpt`.
