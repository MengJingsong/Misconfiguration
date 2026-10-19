# max_hints_size_per_host-shouldHint-maxHintsSize — stage-4 results  <!-- file: long-path/results/max_hints_size_per_host-shouldHint-maxHintsSize.md -->

> **Case:** [`max_hints_size_per_host-shouldHint-maxHintsSize`](../../stage3-ai-deep-read/cases/max_hints_size_per_host-shouldHint-maxHintsSize--guided.md)
>
> **Status:** verdict filed (2026-10-14) — **unit: Confirmed; cluster: Confirmed** (§9a row 1: per-host plateau 0.2–0.97 MB past *L* at 16 · 64 · 256 MiB, every refusal with the operand above *L*, refused rows lost exactly and silently; at the default `0B` no bound, +622.7 MB per down host in 600 s); the amended tighter band with the literal *F′* missed at 64 and 256 MiB (recorded); no run 2
>
> **Path:** long. One results file per path, each in its path's folder.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `531c3ba` (the last commit touching the case file) plus the step-0 amendments of 2026-10-14 (uncommitted at freeze). §9 hash before the amendments `856983a1b435fb7cbf45274fbb87c8775e53b9a7`, §9a `8858045e63bc24d797245178636b745fe13a8c96`; **after the amendments §9 `cf5c0601317dc8043b93be881b331f8e0b7979db`, §9a `c91d82d690f83e06aff463aa548b4c7760c7a6ce`** (`sed -n '/^## 9\. /,/^## 10\. /p' <case> \| git hash-object --stdin`; §9a: `'/^### 9a\. /,/^### 9b\. /p'`). §9a is frozen at this version. Recorded 2026-10-14 21:30 EDT, before any reading of this case existed (no earlier session started it: `pc57:~/stage4-logs/` and `~/stage4-harness-run/` had no folder for it, and the recent session transcripts only read the handoff). |
| **Harness** | `../harness/max_hints_size_per_host-shouldHint-maxHintsSize/`, written by this session after the freeze (§1.2). Node copy `pc57:~/stage4-harness-run/mhs/`. |
| **Tiers and values** | Unit: upstream `StorageProxyTest`; harness `ShouldHintSizeTest` (limit 0 and 1 MiB, the boundary, the flush lag). Cluster (three nodes on `pc57`, loopback, RF 3, one lifetime): control (all up) → N3 down: `max_hints_size_per_host` 16 · 64 · 256 MiB (A until the first refusal, B 90 s) → N2 down too: 64 MiB → `0` (default) 600 s → loss read-back. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-14 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Bytes of one host's hint files on disk (`HintsStore.getTotalFileSize()`, §4, 9a claim). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 16 · 64 · 256 MiB and `0` (the default) over JMX, live (9b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Per-host `.hints` file bytes by `stat` every second beside the operand the check read; the gap (the operand moves only at a flush-session close) is named in 9d. |
| A. Core question | usage driven to the limit and past it | Partly | Yes for the first value; but 9c's fixed burst sizes are computed from zero while the sweep continues from the previous plateau (no reset, 9b), so at 64 MiB the burst leaves about 49 s past the limit, under the 60 s window 9c asks for (rec. 1). |
| B. Logic | each step says what it establishes | Met | 9a "How this verifies", Logic (1)–(6). |
| B. Logic | prediction stated in numbers or a clear relation | Partly | The plateau band `L + r × F + H` is a relation, but *F* is the flush *period*, not the interval between the operand's updates, *H* and *r* are estimates, and the two-host and default arms and the read-back have no number a reading could miss (rec. 2). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows cover over-limit, not following, knob not taken, never reached, window contamination, writes failing, replay. Missing: hints with all nodes up (a contaminated control) and a read-back that misses by a few rows (rec. 6, 7). The "plateau at 1 × L with two hosts down" row cannot occur in the run order of 9e (rec. 2). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Plateau per value and the decision trace (`false` with `T > L`); no metric exists for this refusal (§6b), so the trace is the direct evidence. |
| B. Logic | alternative explanations and their controls | Met | Time window (`Hints_not_stored`, 24 h), host not in the ring (the trace's `checked`/`limit` fields), knob not taken (read-back and `limit=` field), idle control. |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro, §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | The trace rule as written re-reads `getTotalHintsSize` at exit, which is not the value the check used if a flush closes in between, and calls it when the guard skipped it; the read-back "count(*) at ALL" cannot show a loss (rec. 4, 6). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | The phase boundaries depend on when the limit is crossed, which a fixed `n=` cannot express; no stop condition for "never reached"; the layout (CloudLab or loopback) is open (rec. 1, 3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness listed as step-1 work (9c). `pc57` (this host): JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54`), built, Byteman 4.0.20, the bundled Python driver 3.29.0; 32 cores, 251 GiB RAM, 54 GB free on `/`; no daemon running, ports 7010, 7102–7104, 9042, 9091 free. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met after rec. 1 | At 200 rows/s × ≈ 5.2 KB the host's files grow ≈ 1.04 MB/s: 16 MiB in ≈ 16 s, 64 MiB from 17 MiB in ≈ 47 s, 256 MiB from 65 MiB in ≈ 190 s; with a 90 s B each the lifetime is ≈ 30 min; ≈ 1.3 GB of table data per node and ≈ 1.6 GB of hints, far below 54 GB. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `Config.java:112-117`, `:438-453` (`max_hints_size_per_host` `0B` volatile, `hints_flush_period` 10 s, `max_hints_file_size` 128 MiB, `max_hint_window` 3 h, `hint_window_persistent_enabled`); `DatabaseDescriptor.java:3585-3604` (MiB setter, byte getter, `getRawConfig()` `:385`); `StorageProxy.java:189` (MBean name), `:2413-2421` (JMX getter/setter), `:2423-2500` (`shouldHint`: window `:2461-2486`, persistent window `:2472-2479`, the guard `:2489`, operand `:2491`, check `:2492`, trace `:2494-2495`), `:1548-1563` (the primary decision point), `:1585-1597` (`checkHintOverload`, the only other write-path caller, reached only above `maxHintsInProgress`), `:2790-2824` (`submitHint`, `Hint.create`, `incrCreatedHints`); `HintsService.java:117-121` (the flush is *submitted* every period), `:161-172`, `:253-259`; `HintsStore.java:167-181`, `:260-271` (the operand: queued, corrupted and current writer, each by its cached size), `closeWriter()`; `HintsDescriptor.java:97-98` (file names), `:229-243` (the cached size, `-1` until first read); `HintsWriter.java:84` (size = header at creation), `:118-122`, `:167-275` (`Session`, size set at `close()` `:274`); `HintsWriteExecutor.java` (`FlushBufferPoolTask`, the roll at `max_hints_file_size`); `HintsDispatchTrigger.run()` (dispatch only to live hosts); `HintsDispatchExecutor.java:219-221` (throttle 0 = unthrottled); `HintedHandoffMetrics.java:43-53`, `:93` (metric names `Hints_created-/<ip>.<port>`, `Hints_not_stored-…` created only on first use); upstream `StorageProxyTest` (`shouldHintTest`, the Byteman stub). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Run each value as one stream at the fixed rate whose phases are set by the run, not by `n=`: A until the first `false` for the host, B 90 s after it; stop as invalid if no `false` comes within 2 × (*L* − `T₀`)/*r* + 60 s. Replace `cassandra-stress` with a fixed-rate writer that logs every key (`write-load.py`), same rate and hint size. | Applied 2026-10-14 (9a procedure, 9c, 9e); uncommitted | The sweep has no reset between values, so a burst sized from zero does not hold 60 s past the limit; a run-determined boundary needs a writer the run controls; exact keys are needed by rec. 6. |
| 2 | State the prediction as numbers per arm: the `decide` rule (`true` iff `checked ≤ limit`), the plateau band (*L*, *L* + *r* · *F′* + *H*] with *F′* the measured interval between the flushes bracketing the first `false` and a hard ceiling of *L* + 2 MiB, 0 bytes over B's last 60 s, `Hints_created` = the `true` count exactly; for the two-host arm in the 9e order (node 3 already above 64 MiB) node 2 fills to its own band while node 3 gets nothing; the default arm's growth (≈ 620 MB per host in 600 s, a roll). | Applied 2026-10-14 (9a "How this verifies", Prediction, the two-host Conclusions row) | So that each arm can be contradicted. The two-host arm as ordered tests per-host against global more sharply than "total ≈ 2 × L", which cannot occur after the sweep. |
| 3 | Fix the layout: three nodes on `pc57` on loopback (127.0.0.2–.4, JMX 7102–7104, storage port 7010), `num_tokens: 1`, local directories under `~/stage4-mhs/`, 2 GiB heaps; `ks.t (pk bigint PRIMARY KEY, v blob)`. | Applied 2026-10-14 (9b) | `pc66` is unreachable and the loopback ring worked for `repair_session_space`. |
| 4 | Replace the single exit rule: capture the operand and limit **after the check's own call** (`:2491`), print `-1` when the guard skipped it, trace the primary decision point's result, every flush-session close (when `T` moves) and every writer roll. | Applied 2026-10-14 (9c harness table) | The exit rule's fresh `getTotalHintsSize` can differ from what the check compared; the flush lines give *F′* and the operand's history for the self-check. |
| 5 | List the run script, JMX client, yaml builder and unit runner as step-1 harness. | Applied 2026-10-14 (9c) | Completes D. |
| 6 | Loss read-back on the returned host alone (others stopped), every key at `ONE`, compared as sets with the `decide` lines; `hinted_handoff_throttle` 0 on N1 for the replay; add the "sets differ by a few rows" row. | Applied 2026-10-14 (9a Logic (5), Prediction, Conclusions; 9b; 9d) | A read at `ALL` merges replicas (N1 holds every row) and read-repairs, so it cannot show N3's loss; the default throttle would replay ≈ 1.6 GB in over 25 min. |
| 7 | Add the contaminated-control row (hints or `decide` lines with all nodes up) and record `hint_window_persistent_enabled`. | Applied 2026-10-14 (9a Conclusions, 9b) | An outcome without a row. |
| 8 | Unit step 3: a fresh endpoint instead of deleting hints (`deleteAllHints()` leaves the open writer counted) and "one byte more" on the limit side (raw config 1,048,575 B); add step 6, buffered hints do not move the operand until a flush. | Applied 2026-10-14 (9e unit steps) | Step 3 as written cannot reach `T` = 0 after a delete, nor `T` + 1 byte; step 6 is the unit-level evidence for the overshoot mechanism. |
| 9 | §6b: "No metric fires on this path" holds, but `Tracing.trace` is a request-trace event, so the refusal is visible only for traced requests; §5's seven decision points: `checkHintOverload` (`:1593`) reads `shouldHint` for **live** replicas too, but only when `totalHintsInProgress > maxHintsInProgress` (128 × cores). | Left for stage 3 | Precision; not load-bearing here (the run stays far below the in-flight cap). |
| 10 | §8 / §6a: the operand is each file's **cached** size (`HintsDescriptor.java:229-243`), set at writer creation (header only, `HintsWriter.java:84`) and at each session close (`:274`); between flushes the check reads a size up to one flush period old. §8's "overshoot by one hint" should read "by up to one flush period's hints" (already noted in §10). | Left for stage 3 | The frozen prediction already uses the per-flush bound. |

### 1.2 Instrument checks (not readings)

- **Unit harness:** compiled with `javac` against the clone's classpath. It first named `Hint.Serializer`, which is
  package-private, so the test moved to package `org.apache.cassandra.hints` (9c said `service`; recorded in the harness
  README). The exact-fill search was rewritten before any run to probe payload sizes near the remainder with zero-filled
  payloads and the real key (the entry size depends on the key's length).
- **Byteman:** `TestScript: no errors` for all six rules (re-run by `cluster-run.py` before every start, `testscript.txt`).
  The capture after the check's own `getTotalHintsSize()` call reads the local `$maxHintsSize` (the build keeps local
  variable tables, `debuglevel=source,lines,vars`); a value ternary in the exit rule type-checks. The `site send` rule
  gained the row key (`key=<hex>`) before any cluster start, so the read-back can be compared row by row.
- **Unit instrument run** (`unit-run.sh instrument`, 21:35, `pc57:~/stage4-logs/mhs/unit-instrument/`): 3 tests, 0
  failures; 58 `decide` lines (54 with `limit=1048576`, 5 `false`, 3 with `checked=-1` at limit 0), 51 `flush` lines, no
  `site send` line (the unit test calls `shouldHint` directly). The raw-config boundary line reads `checked=1048576
  limit=1048575 result=false`.
- **Shakedown 1** (`cluster-run.py run` with values 4 · 8 MiB, two-host 4 MiB, B 20 s, control 10 s, default 40 s;
  21:42–21:48, `pc57:~/stage4-logs/mhs/shakedown1/`): ring up in about 25 s, `Submit -l` lists the six rules, knob
  read-back exact, every arm's pipeline ran. Two harness defects, neither touching §9a: (1) the read-back's lone N2 died at
  start-up, `Unable to gossip with any peers` (a non-seed node runs a collision shadow round, `StorageService.java:868-877`);
  fixed by starting it with `-Dcassandra.allow_unsafe_join=true`, which skips only that check, and 9d corrected (dated,
  §9 hash now `2d05e15c…`, §9a still `c91d82d6…`); (2) the "last 60 s" windows were measured from before the refusal when
  B (or the default arm) is shorter than 60 s, a shakedown-only artifact; clamped to start no earlier than 5 s after the
  refusal (or the arm's start). One more thing seen, not a defect: the sub-prediction "files minus the last checked
  operand ≤ *r* · *F′* + *H*" missed by 96 B in the two-host arm (one flush of 201 hints against a bound of 200.98 hints'
  worth); §9a is not changed for it, and run 1 judges it as frozen.
- **Shakedown 2** (same settings, 21:49–21:56, `pc57:~/stage4-logs/mhs/shakedown2/`): the whole lifetime ran, including
  the read-back of both hosts alone (key sets exact on both), 0 `ERROR` lines on the three nodes, no daemon left. The only
  `NO` lines are the two 128 MiB-roll checks, which a 40 s default arm cannot reach. **Instrument check passed.**
- The repository folder and the node copy `~/stage4-harness-run/mhs/` are byte-identical (`md5sum`, 22:00). md5s:
  `cluster-run.py` `85233d20`, `Jmx.java` `46dc9f56`, `make-node-yaml.sh` `4e12e7b9`, `README.md` `7383d45c`,
  `should-hint.btm` `53adfad2`, `ShouldHintSizeTest.java` `a1d61127`, `unit-run.sh` `68f9e0ab`, `write-load.py` `c3001b36`.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-14: unit 22:00:59–22:01:41 EDT, cluster 22:02:46–22:35 EDT (one lifetime) | not done |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347`), 32 cores, 251 GiB; this session runs on it | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54` (`cassandra-5.0.9`); `ShouldHintSizeTest.java` copied into `test/unit/org/apache/cassandra/hints/`, untracked | |
| Case-file commit / harness commit | base `531c3ba` + uncommitted amendments (§1; §9 at run 1 `2d05e15c…`, §9a `c91d82d6…`) / uncommitted (md5s in §1.2; `cluster-run.py` `6317a980` after the phases fix, below) | |
| Storage for node data | local `/dev/sda3`, `~/stage4-mhs/N1..N3/` (53 GB free at the start) | |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/mhs/` (`unit/`, `unit-instrument/`, `shakedown1/`, `shakedown2/`, `run1/`: `mhs.trace` 65 MB, `keys/` the writer's per-row logs, `readback/N2-keys.txt`, `N3-keys.txt`, the three nodes' `system.log` and yaml) | |

## 3. Runbook defects

None in run 1: every step ran as written. One harness defect was found after the unit tier and before the cluster tier, by
dry-running the self-check on shakedown 2's files: `phases.csv` was written through an unflushed `csv.writer` and came
out empty (the run script's own judgments never read it; the same phases are in `session.log` as `PHASE` lines). Fixed
(flush after each row; `cluster-run.py` md5 `85233d20` → `6317a980`), node copy re-synced and compared, then the cluster
tier started. The shakedown defects are in §1.2.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| — | — | — | none | — | — | — |

## 4. Run 1

**Scope:** unit tier (upstream `StorageProxyTest`; harness `ShouldHintSizeTest`, steps 1–6); cluster tier, one lifetime
of three nodes on `pc57`: control (all up, 30 s) → N3 down → `max_hints_size_per_host` 16 · 64 · 256 MiB (A until the
first refusal for N3, B 90 s) → N2 down → 64 MiB for N2 → `0` for 600 s → loss read-back. **Command log:**
`run1/unit/summary.txt`, `run1/cluster/summary.txt` (every `EXPECTED:` line; full `session.log` on the node). Raw
excerpts: `run1/cluster/arms.csv`, `counters.csv`, `phases.csv`, `du.csv` (1 s per-host `.hints` bytes),
`mhs.trace.excerpt` (every `flush` and `roll` line, 12 lines either side of each first refusal), `readback/*.json`, the
yaml tails and WARN/ERROR lines of each node. Rate 199.95–199.99 rows/s in every stream; *H* = 5,189.0 B per hint
(ΔT / hints, every arm).

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `StorageProxyTest` (incl. `testShouldHintOnExceedingSize`, the Byteman stub `return 2097152` against 1 MiB) | 5 tests, 0 failures, 0 errors | `run1/unit/summary.txt`, `TEST-…StorageProxyTest.xml` |
| `ShouldHintSizeTest` | 3 tests, **80 checks, 0 mismatches** | `run1/unit/harness.out` |
| Steps 1, 2, 4: limit 0 with 2,114,002 B on disk | `shouldHint` `true` (both overloads); at 1 MiB (1,048,576 B read back) `false`; at 0 again `true`, operand unchanged | `harness.out` |
| Step 3, boundary: operand filled to exactly 1,048,576 B | `true` at *T* = *L*; *L* = 1,048,575 B (raw config) `false`; one more hint (+171 B) → *T* = 1,048,747 B, `false` | `harness.out` |
| Step 5, the operand | after each of 53 flushes `getTotalHintsSize` = Σ `File.length()` of the host's files | `harness.out` (`operand=` lines) |
| Step 6, the lag | *T*₀ = 948,576 B; 412,480 B of hints written but not flushed: operand still 948,576, `shouldHint` `true` though *T*₀ + buffered > 1 MiB; after the flush *T* = 1,361,056 B (312,480 B past *L*), `false` | `harness.out` |

**Cluster tier** — `T` = the host's `.hints` bytes on N1 (sampler); *checked* = the operand the check read (trace);
"site true/false" = the verdict at `sendToHintedReplicas()`.

| Value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| all up | control | hints, decisions, writes | 6,000 writes, 0 failed; no `.hints` file, no `decide`/`site`/`flush` line, `Hints_created` 0 | `cluster/summary.txt` |
| 16 MiB (N3) | A | decisions | 3,420 `true`, all with *checked* ≤ 16,777,216; *T* 0 → 16,708,622 B at the last flush before the refusal | `arms.csv`, `mhs.trace.excerpt` |
| 16 MiB | B | refusal | first `false` at +17.6 s with *checked* 17,746,422 > *L*; then 18,082 `false`, 0 `true`; every `false` has *checked* > *L* | `arms.csv`, `summary.txt` |
| 16 MiB | B | plateau | *T*_end **17,746,422 B** (overshoot 969,206 B = 0.924 MiB); 0 B over B's last 60 s; *F′* 1,002 ms | `arms.csv`, `du.csv` |
| 16 MiB | A+B | counters, writes | `Hints_created` +3,420 = site `true` 3,420; `TotalHints` +3,420; 21,502 writes, 0 failed; `Hints_not_stored` never created | `counters.csv` |
| 64 MiB (N3) | A / B | decisions | 9,668 `true` (*checked* ≤ *L*), first `false` at +48.9 s with *checked* 67,913,674; 18,056 `false`, 0 `true` after | `arms.csv` |
| 64 MiB | B | plateau | *T*_end **67,913,674 B** (overshoot 804,810 B); 0 B over the last 60 s; *F′* 768 ms — the previous `flush` line (229 ms earlier) is the extra flush of a full 32 MiB `HintsBuffer` | `arms.csv`, `mhs.trace.excerpt` |
| 64 MiB | A+B | counters, writes | `Hints_created` +9,668 = site `true`; 27,724 writes, 0 failed | `counters.csv` |
| 256 MiB (N3) | A / B | decisions | 38,683 `true`, first `false` at +193.9 s with *checked* 268,639,845; 18,080 `false`, 0 `true` after | `arms.csv` |
| 256 MiB | B | plateau | *T*_end **268,639,845 B** in 3 files (two 128 MiB rolls; overshoot 204,389 B); 0 B over the last 60 s; the crossing flush rolled a file, so its two session lines are 5 ms apart | `arms.csv`, `mhs.trace.excerpt` |
| 256 MiB | A+B | counters, writes | `Hints_created` +38,683 = site `true`; 56,763 writes, 0 failed | `counters.csv` |
| 64 MiB (N2; N3 at 268.6 MB) | A / B | N2 | 13,036 `true`, first `false` at +65.7 s with *checked* 67,643,846; 18,090 `false`, 0 `true` after; *T*_end **67,643,846 B** (overshoot 534,982 B); 0 B over the last 60 s | `arms.csv` |
| 64 MiB (N2) | whole arm | N3 | 31,126 `decide` for N3, all `false` with *checked* 268,639,845 > *L*; N3's files unchanged (268,639,845 B), no `flush` line for N3; `Hints_created` N3 +0 | `summary.txt` |
| 64 MiB (N2) | whole arm | total | directory 336,283,691 B = N3 268,639,845 + N2 67,643,846 | `summary.txt` |
| `0` | 600 s, N2 and N3 down | decisions | 120,000 `decide` per host, all `true`, `limit=0`, `checked=-1` | `summary.txt` |
| `0` | 600 s | growth | N2 +622,680,210 B (files 1 → 6, 5 rolls), N3 +622,680,168 B (files 3 → 7, 4 rolls); predicted 623,332,105 B (0.999); +63.1 MB in the last 60 s; N3 ends at **891,320,013 B**, N2 at 690,324,056 B | `summary.txt`, `du.csv` |
| `0` | 600 s | counters, writes | `Hints_created` +120,000 per host = site `true`; 120,000 writes, 0 failed | `counters.csv` |
| all arms | — | contamination | `Hints_not_stored-*` never created (no MBean at any read); N2's and N3's own hints directories empty in all 3,130 samples | `counters.csv`, `du.csv` |
| read-back | after the drain (45 s, throttle 0) | N3 alone | 263,115 rows written in all; N3 holds **177,771** = control 6,000 + its 171,771 `true` rows exactly; **85,344 missing = exactly its `false` rows** (0 extra, 0 short) | `readback/N3-summary.json` |
| read-back | — | N2 alone | holds **245,025** = rows written while up + its `true` rows exactly; **18,090 missing = exactly its `false` rows** | `readback/N2-summary.json` |
| whole run | — | logs | 0 `ERROR` lines on the three nodes; no log line of any level for the 103,434 refusals (only `Finished hinted handoff …` and `Deleted hint file …` mention hints) | `N*-system.warn-error.log`; full logs on the node |

**The frozen plateau band, three readings of *F′*** (`selfcheck.txt`; the run script's *r* is the writer's rate, the
self-check's the key log's, 0.04 % apart):

| Value | overshoot | *L* + *r*·*F′* + *H*, *F′* literal (the two `flush` lines bracketing the refusal) | *F′* between flush tasks | *F* = 1 s (Conclusions row 1) |
|---|---|---|---|---|
| 16 MiB | 969,206 | holds (*F′* 1,002 ms, margin 76 KB) | holds | holds (margin 74 KB) |
| 64 MiB | 804,810 | **missed by 2,361–2,670 B** (*F′* 768 ms) | **missed** (same task) | holds (margin 238 KB) |
| 256 MiB | 204,389 | **missed** (*F′* 5 ms: a roll inside the crossing flush) | holds (*F′* 212 ms) | holds (margin 839 KB) |
| 64 MiB (N2) | 534,982 | holds (*F′* 715 ms) | holds | holds (margin 508 KB) |

### 4.2 Conclusion and logic

1. **Validity** — valid. Every enabled value was reached and passed (first refusal at +17.6, +48.9, +193.9 and +65.7 s,
   each followed by 90 s of B) [observed: `phases.csv`, `arms.csv`]. Hold-fixed settings: `max_hint_window: 24h` and
   `hints_flush_period: 1000ms` in every node's yaml, `max_hints_file_size` and `hinted_handoff_enabled` at their
   defaults [observed: `N*-yaml-tail.txt`]; the knob read back equal to the value set at every change, and the trace's
   `limit=` equals MiB × 1,048,576 on every line [observed: `summary.txt` `KNOB` lines, `arms.csv`]; the time window did
   not fire (`Hints_not_stored` never created, no `false` with *checked* ≤ *limit*) [observed: `counters.csv`,
   `selfcheck.txt`]; the control made no hint [observed: `summary.txt`]; rate 199.95–199.99 rows/s at every value
   [observed: `summary.txt` `WRITER` lines].
2. **Readings** — two things are unusual. (a) The extra flushes: about every 32 MiB of hints a full `HintsBuffer` is
   handed to `FlushBufferTask` between the periodic flushes (`flush` lines 34 ms and 229 ms after the previous one at
   33.7 MB and 67.1 MB) [observed: `mhs.trace.excerpt`]; the session after it then carries the hints accepted since the
   buffer switch, which precedes that flush's close, so the bytes of a session exceed *r* × (interval between closes) by
   the switch-to-close lag [inferred: `HintsBufferPool.switchCurrentBuffer()` → `HintsWriteExecutor.flushBuffer()`, the
   case's sibling `MAX_HINT_BUFFERS`; 156 hints in a 768 ms interval at 200/s]. (b) At 256 MiB a 128 MiB roll fell inside
   the crossing flush, giving two session lines 5 ms apart (the old file closed at 134,218,716 B, the new one carried
   202,413 B) [observed: `mhs.trace.excerpt`, `roll` line].
3. **Matched row** — §9a row 1: "Each enabled value: the host's files plateau within `L + r × F + H`, the trace shows
   `false` returns with `T > L`, `Hints_created` flat, writes succeeding; the plateau follows *L* across 16/64/256 MiB; at
   `0B` no plateau; with two hosts down the total is about `2 × L`" → **Confirmed — the check enforces as traced; at the
   default it bounds nothing.** Each part:
   - *plateau within L + r × F + H* (*F* = 1 s): overshoots 969,206 · 804,810 · 204,389 · 534,982 B against
     *r* · *F* + *H* ≈ 1,043,000 B, flat over B's last 60 s [observed: `arms.csv`, `du.csv`, `selfcheck.txt`];
   - *`false` with T > L*: every one of 72,308 `false` decisions in the enabled arms has *checked* > *limit*, and none is
     earlier than the first *checked* > *L* [observed: `arms.csv`, `selfcheck.txt`];
   - *`Hints_created` flat*: no site `true` after any first refusal; the counter equals the `true` count exactly in every
     arm [observed: `counters.csv`, `arms.csv`];
   - *writes succeeding*: 263,115 writes, 0 failed [observed: `summary.txt`];
   - *follows L*: plateaus 17.7 · 67.9 · 268.6 MB at 16 · 64 · 256 MiB, each 0.2–0.97 MB past *L* [observed: `arms.csv`];
   - *at `0B` no plateau*: both hosts grew 622.7 MB in 600 s (0.999 × predicted), still +63 MB in the last minute, past
     every enabled plateau and across 4–5 rolls [observed: `summary.txt`, `du.csv`];
   - *per host* (as amended for the run order): with N3 already at 268.6 MB, N2 filled from 0 to its own 64 MiB band
     and stopped, while N3 got no hint and no byte [observed: `summary.txt`];
   - *the loss* (Logic (5), amended): after the replay each host holds exactly the rows it was hinted plus those it took
     while up; its missing rows are exactly its refused rows (85,344 on N3, 18,090 on N2) [observed: `readback/*.json`].
4. **Excluded rows** —
   - *Plateau at 1 × L with two hosts down / node 2 gets no hint* (§8's multiplier refuted): N2 took 13,036 hints and
     reached 67.6 MB while N3 held 268.6 MB [observed: `arms.csv`].
   - *Files grow past L + r × F + H with `false` returns* (**Refuted**): no; the largest overshoot is 969,206 B, under the
     1 s band and the 2 MiB ceiling, and the files are flat after the crossing flush [observed: `arms.csv`].
   - *Files past L with `true` and T > L* (**Invalid**, knob not taken): 0 such lines in the whole run [observed:
     `selfcheck.txt`].
   - *Plateau does not move with L* (**Refuted**): it moves 17.7 → 67.9 → 268.6 MB [observed: `arms.csv`].
   - *At `0B` the files plateau anyway* (Not confirmed): no, +63 MB per host in the last 60 s [observed: `summary.txt`].
   - *Writes fail or block* (Not confirmed): 0 failed; the stream kept 200 rows/s through every B [observed: `summary.txt`].
   - *Replay delivers more than stored, or all of it* (Not confirmed): no, exact sets [observed: `readback/*.json`].
   - *Never reached L* (Invalid): every value reached [observed: `phases.csv`].
   - *`Hints_not_stored` non-zero* (Invalid): never created [observed: `counters.csv`].
   - *Control writes hints* (Invalid, added): none [observed: `summary.txt`].
   - *Read-back sets differ by a few rows* (added): 0 extra, 0 short on both hosts [observed: `readback/*.json`].
5. **Observed vs. inferred** — the conclusion rests on observed statements only. Inferred and not load-bearing: the cause
   of the two missed band readings (the buffer-switch lag at 64 MiB, the roll at 256 MiB) — the observed part is that
   the lines are there and the margins are as stated; and that the trace's `checked` is the value compared at `:2492`
   (the rule captures it right after the check's own call, `:2491`; observed in the unit instrument run, where the
   boundary line reads `checked=1048576 limit=1048575 result=false`).
6. **Deviations and gaps** — (a) **Missed frozen sub-predictions** (recorded, not tuned): the amended Prediction's
   tighter band `T_end ≤ L + r · F′ + H` with *F′* the two bracketing `flush` lines is missed at 64 MiB by 2,361–2,670 B
   (half a hint; the session carried the hints since the buffer switch, not since the previous close) and, read
   literally, at 256 MiB, where a roll put two session lines 5 ms apart (with *F′* between flush tasks it holds, 212 ms,
   margin 21 KB). The Conclusions row's own band (*F* = 1 s) and the hard ceiling (*L* + 2 MiB) hold at every value.
   (b) The writer replaced `cassandra-stress` (audit rec. 1); the unit test sits in package `hints`, not `service`.
   (c) Request tracing was not sampled (9e cluster step 3's traced write); the per-call `decide` lines cover the same
   verdict for every write, and the case says the `Tracing.trace` event is the only other place the refusal appears.
   (d) No reset between values, as 9b intends: 16 MiB started from an empty host, 64 and 256 MiB from the previous
   plateau, the two-host arm with N2 empty, and the default arm from each host's plateau; growth is measured from each
   arm's start.
7. **Core question** — usage follows the constraint and the constraint caps it, per host: at 16, 64 and 256 MiB the down
   host's hint files stop 0.2–0.97 MB past the limit and stay there while writes keep succeeding (parts 3 and 4: Logic
   (1)–(3)); the stop is this check's disallow branch — every refusal carries *checked* > *limit*, no hint is created
   after it, and nothing logs or counts it (part 3, Logic (4)); the refused rows are lost to that host, exactly, after
   the replay (Logic (5)); with a second host down the second host gets its own full allowance while the first gets
   nothing (Logic (6)). At the shipped default (`0B`) the same load grows each down host's hints without bound, about
   1 MB/s per host, here to 0.89 GB.

**Conclusion (one line):** §9a row 1 — **confirmed**, at both tiers; the plateau is per host, follows *L* within one
flush period's hints (the amended tighter band with the literal *F′* missed at 64 and 256 MiB, recorded); at the default
it bounds nothing; the disallow loses exactly the refused rows and is silent.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` re-parses the raw files with its own code (the full trace, 408,241 `decide` and 408,241
`site send` lines, 1,586 `flush`, 13 `roll`; `du.csv`; `counters.csv`; the key logs of all 263,115 rows; both read-back
key lists; the unit outputs) and re-judges the frozen relations: **118 ok, 3 fail** (`run1/selfcheck.txt`). The three
fails are the missed band readings of §4.2 part 6(a) (64 MiB under both *F′* readings, 256 MiB under the literal one); no
other judgment differs from the run script's, and every figure it recomputes agrees (overshoots to the byte; *r* within
0.04 %). Run before the cluster tier on a copy of shakedown 2's files, it caught the empty `phases.csv` (§3).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `phases.csv`: four first refusals, each followed by ≥ 90 s; yaml tails show the 24 h window and 1 s flush; `counters.csv` has no `Hints_not_stored` row; knob read-backs in `summary.txt`. |
| 2. Readings | yes | The extra flushes are in `mhs.trace.excerpt` (lines at 33,655,896 and 67,104,190 B, 34 and 229 ms after the previous); the 256 MiB roll pair is there with its `roll` line. |
| 3. Matched row | yes | Each part re-derived: plateaus and margins (`selfcheck.txt` "F = 1 s" lines), `false` only with *checked* > *limit* (whole-run check), `Hints_created` = `true` count per arm, 0 failed rows in every key log, default growth 0.999, per-host arm, read-back sets exact. |
| 4. Excluded rows | yes | No `true` with *checked* > *limit* > 0 anywhere; no `false` without it; N2's own hints directory empty; read-back extra/short 0. |
| 5. Observed vs. inferred | yes | The buffer-switch explanation is stated as inferred and carries no part of the verdict. |
| 6. Deviations and gaps | yes | The band misses are reported under all three readings, as frozen. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Logic (1) reached (`phases.csv`), (2) flat files and counter (`du.csv`, `counters.csv`), (3) plateau follows *L* (`arms.csv`), (4) `false` with *checked* > *L* (trace), (5) exact loss (read-back), (6) default unbounded and per host (`summary.txt`). |

### 5.2 Run 2?

**No** — decided 2026-10-14. The conclusion rests on observed statements; every part of §5.1 is settled from run 1's raw
files by an independent parser; the result neither refutes the case nor confirms a bypass (the default-mode gap is the
claim's own `0B` arm, which §9a says cannot refute). The only misses are of a tighter sub-band whose cause is visible in
the trace.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** — the check with the real operand: `true` at *T* = *L*, `false` at *T* = *L* + 1 and above, nothing at limit 0; the operand is the files' length after each flush and does not move with buffered hints (the mechanism of the overshoot) | run 1 + self-check | 2026-10-14 |
| Cluster | **Confirmed** (row 1) — per-host plateau 17.7 · 67.9 · 268.6 MB at 16 · 64 · 256 MiB (0.2–0.97 MB past *L*), every refusal with *checked* > *L*, no hint after it, writes unaffected; N2 fills its own 64 MiB while N3 gets nothing; **at the default no bound** (+622.7 MB per host in 600 s); the refused rows are lost exactly and silently. Amended tighter band (literal *F′*) missed at 64 and 256 MiB, recorded | run 1 + self-check | 2026-10-14 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" field updated (uncommitted); §8's "by one hint's worth"
amended with a dated note (the measured overshoot is up to one flush period's hints, 0.2–0.97 MB here); recommendations 9
and 10 of §1.1 and the overshoot-bound note of §4.2 part 2 left for stage 3 in §10.
