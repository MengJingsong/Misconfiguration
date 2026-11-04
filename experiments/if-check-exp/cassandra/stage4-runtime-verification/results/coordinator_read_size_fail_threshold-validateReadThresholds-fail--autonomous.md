# coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous — stage-4 results  <!-- file: results/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous.md -->

> **Case:** [`coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous`](../../stage3-ai-deep-read/cases/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous.md)
>
> **Status:** verdict filed, 2026-10-27. **Unit: Confirmed — caps only on some paths (bypass)** (unit re-run "run 1b" of 2026-10-27 at the re-frozen
> version `967d12bf…29ed6`, after the user-authorised amendment of the B2f (u3)/(u4) replica `len` relation to |`len` − S(P)| ≤ δ(P) = 8·P + 24 B and of
> the B2g Refuted (b) replica-buffer clause; §7, §8). Every clause of (u1)–(u6) held: refusals exactly where predicted, counted size and X as derived,
> the replica buffer under C within −5 … +14 B of N's (δ = 152 / 536 B), local allocation 0.74 / 3.11 / 12.6 MB independent of P, switch-off control
> and line 1101 as traced; self-check 111 of 111. **Cluster: Not confirmed — caps only on some paths (bypass)** (run 1; closed, not re-run). The run-1
> unit verdict below (Not confirmed) stays on record as filed.
>
> **Outcome class:** undetermined — the stage-3 estimate (`undetermined`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/`](../harness/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/).
>
> **Cluster re-run ("run 1b-cluster", 2026-10-28)** at the re-frozen version `0ab0b5ab…6fa1` (after the user-authorised amendment of B3a, B3d, B3e,
> B3f (n4, c4, l4, L4-3, V), B3g, B3h and B4 that restates the aggregate clauses as in-flight replica bytes by event, and runbook fix D2 from the
> shakedown): **Cluster: Confirmed — caps only on some paths (bypass)** (§7b). Every per-query clause held again (C refused all 155,383 queries at
> counted 1,048,704 B while every one of them held a full 8.39 / 33.57 MB replica buffer; L/L4 refused all 1,419,849 queries at X = 1,052,104 /
> 4,208,200 with 3.11 / 12.6 MB allocated per read at both P; Z refused to start), and the amended aggregate clauses held: at most 16 requests and
> 16 reads in flight; peak in-flight replica buffers 75.5 / 201.4 MB under N and 134.3 / 369.3 MB under C (ceilings 16 × page buffer 269.8 /
> 1,075.9 MB; floors one page), 1,280–1,408 B under L/L4 (every request held the 128-byte empty response); peak in-flight read allocation
> 49.6 / 49.1 MB under L and 193.9 / 195.8 MB under L4 (ceilings 96 / 336 MiB). Self-check 115 of 115. Post-GC heap is reported as an
> observation only (L again 1.6–2.1 GiB). The run-1 cluster verdict above stays on record as filed.
>
> **Run-1 status (as filed 2026-10-25):** verdict filed, 2026-10-25. **Unit: Not confirmed — caps only on some paths (bypass).** Every operand clause held exactly:
> - Coordinator arm: refused exactly where (P − 1)·65,544 > T, at counted size m·65,544. At P × 65,536 = T it did not refuse.
> - Local arm: refused exactly where b0 + k·h ≥ T, with X = 263,080 / 1,052,104 / 4,208,200. This includes P × 65,536 = T. The replica's work for a refused page was 0.74 / 3.11 / 12.6 MB at T = 256 KiB / 1 MiB / 4 MiB, the same at P = 16 and 64.
> - Switch-off control and the line-1101 asserts: as predicted.
>
> The frozen clause "replica `len` under C **equals** N's" failed by −1 to +13 B in 4 of 6 combinations, and an L table differed by −2 B. Two of the C differences are negative, so they meet the literal text of a *Refuted (b)* row. The self-check rejects that row: the difference is per-table timestamp encoding (`SerializationHeader.java:165-168`), not the coordinator threshold. The tier is downgraded to *Not confirmed* (§4.2, §5).
>
> **Cluster: Not confirmed — caps only on some paths (bypass)** (per query; node heap not shown). Every per-query clause and the start-up refusal held:
> - Under `coordinator_read_size_fail_threshold: 1MiB` all 144,362 queries were refused at counted size exactly 1,048,704 B. The replica still built the full page each time (8,390,292 / 33,561,620 B, the same as with no threshold).
> - Under `local_read_size_fail_threshold: 1MiB` / `4MiB` all 1,885,357 queries were refused at X = 1,052,104 / 4,208,200. No page buffer was completed, and the replica allocated 3.11 / 12.6 MB per query at both page sizes.
> - `Z` refused to start with the line-1101 message.
>
> The filed aggregate-heap clauses failed: N's post-GC heap above idle grew only 202 → 217 MiB (filed ≥ 3× and ≥ 400 MiB), and L's was 1.8–2.2 GiB (filed ≤ 64 MiB), dominated by promoted garbage. One runbook defect (D1, client reconnect) restarted the cluster tier. No run 2.
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e"
> means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`). The verdict is
> against this file's own predictions and conclusions only. Copied unchanged: `Alloc.java` and `Jmx.java` (from the guided
> `coordinator_read_size_fail_threshold-shouldReject-thresholdBytes` harness). Adapted (copied, then changed): `cluster-run.sh` (from the
> `max_value_size-applySimpleConfig` autonomous harness), `Sampler.java` (from the `memtable_heap_space-applySimpleConfig` autonomous harness),
> and the read-alloc rules in `vrt.btm` (from the guided harness's `read-alloc.btm`, keyspace changed). The mirror pass in the unit test follows the
> closed `local_read_size_fail_threshold` guided harness. No reading from another case is used.

**What the constraint is (kept apart throughout).** The entry pointer `DatabaseDescriptor.java:1101` is a start-up check between two limits: `*_read_size_fail_threshold` ≥ its warn threshold. The file's claim is about what the fail thresholds it guards cap.
- **(a)** The **local** threshold stops the replica serializing a page once the tracked heap size of its rows reaches T.
- **(b)** The **coordinator** threshold refuses once the counted result-set value bytes exceed T, after the replica has already serialized the whole page.

"Caps" below is per query. The aggregate node heap is reported separately.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `38240d9` (DD batch 3), sha256 `4e6f47ae…0d1c`, checked equal to the filed §2 row before the audit. The step-0 audit made **19 amendments** (2026-10-25, before any harness run or reading): A3 (audit statement, facts 1–7), B1 (operational reading, claim unchanged), B2a–B2h, B3a–B3h and B4. The file was frozen at sha256 **`4f2657bc8ab34d66a0249d78bafb74b8b443fda236165f7a259fd3e3611bd8ab`** (new row in `_INDEX.md` §4). Unit run 1 ran at this version. Runbook fix D1 (B3c, §3) made after cluster attempt 1 left claim, predictions and conclusions unchanged. The file was frozen again at **`3ed15193157574507e2e3abab7cb545955986a24c81b38c570011775bef824c7`** (new §2 row); cluster run 1 ran at that version, which was re-checked unchanged after the run. Section D was filled after that. Nothing is committed (no commit was asked for); base commit `38240d9`. |
| **Harness** | [`../harness/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/`](../harness/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/):<br>• `ReadSizeCapUnitTest.java` (B2: `CQLTester` + `requireNetwork()`; mirror; 15 combinations; replica `len`/`cap`/`alloc`; line-1101 by reflection; setter bypass)<br>• `unit-run.sh`<br>• `vrt.btm` (Byteman, observation only: `read-alloc`, `resp-buf len cap`, `resp-buf-abort`, `guard-fail size limit`, `local-abort` message)<br>• `Alloc.java`, `Jmx.java` (unchanged)<br>• `Sampler.java` (JMX, replaces `jstat`)<br>• `vrtclient.py` (bundled driver, protocol 5; settings, schema, load, 16-process paged reader)<br>• `cluster-run.sh`<br>• `summarize.py` (per-start digest)<br>• `selfcheck.py` (independent)<br>**Instrument checks before run 1:** `bash -n`, `ast.parse`; Byteman `TestScript: no errors`.<br>**Unit shakedown** (T = 524,288, P = 32, not an arm value; [`shakedown/unit-shakedown-stage4.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/shakedown/unit-shakedown-stage4.out)): h = 65,752 ∈ (65,536, 66,560); C refused at code 4; `len` 2,097,555 in the band; `alloc` 6.27 MB ≥ 4.19 MB; L X = 526,088 = b0 + 8h, `alloc` 1.53 MB < 5T + 1 MiB.<br>**Cluster shakedown** `sd` ([`shakedown/cluster-shakedown-summary.txt`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/shakedown/cluster-shakedown-summary.txt); 2 × 256 rows, 2 MiB thresholds, P = 128, 4 clients, 20 s): read-backs (settings and JMX) correct; agent and 2 MiB regions on the JVM; `guard-fail size=2097408 limit=2097152` (= 32·65,544); `local-abort` X = 2,104,136 = b0 + 32h; full-page `len` 8,390,292 in the band; `read-alloc` 25.2 MB (N, C) ≥ 16.8 MB and 6.27 MB (L) < 11.5 MB; full-GC baseline parsed (`Pause Full (Diagnostic Command)`).<br>No bound was changed. |
| **Tiers and values** | **Unit (B2):** N (no threshold) at P = 16, 64. C and L at T ∈ {262,144; 1,048,576; 4,194,304} B × P ∈ {16, 64}. OFF (switch off, both thresholds 262,144, P = 16). Line-1101 asserts ×3 pairs plus setter bypass ×3. Path: runtime setters.<br>**Cluster (B3):** one node, 4 GiB heap, G1 with 2 MiB regions, 8 × 1,024 rows × 64 KiB (539 MB on disk). Arms: N (control), C (`coordinator_read_size_fail_threshold: 1MiB`), L (`local_…: 1MiB`), L4 (`local_…: 4MiB`); P ∈ {128, 512}; 16 client processes × 180 s each. Then Z (warn 2 MiB, fail 1 MiB). Path: yaml (start-up, through line 1101). |
| **Audit bottom line** | **Ready after amendments**, 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap of one read (replica response buffer plus result set). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | Unit T ∈ {256 KiB, 1 MiB, 4 MiB} plus null (the default, control N). Cluster {1 MiB coordinator, 1 MiB and 4 MiB local} plus N. The amendment adds the path per arm (A3 fact 6). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Filed: post-GC heap Δ, humongous counts, `jstat`, `measureDeep` of the response. Added: per-query replica buffer (`resp-buf len/cap`), per-query replica allocation (`read-alloc`), the exact counted size (`guard-fail`) and X (`local-abort`), and unit thread allocation. `jstat` was replaced by JMX (cannot attach here). Gap named (B3d): post-GC heap includes old-generation garbage. |
| A. Core question | usage driven to the limit and past it | Met | Pages of 1–4 MiB (unit) and 8–32 MiB (cluster) against T = 256 KiB–4 MiB, and boundary pages P × 65,536 = T. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Exact refusal rules, counted sizes, X, histogram buckets (A3 facts 1–5), and bands for `len`/`cap`/`alloc` (B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Filed B2g/B3g had no exact rows per threshold, no Invalid, and no aggregate-vs-per-query split. Rows added for coordinator-only and local-only outcomes: confirmed, refuted (mechanism), refuted (buffer/heap), not confirmed (aggregate), switch inactive, positive control failed, catch-all. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after amendment | `guard-fail` / `local-abort` lines, meters, client code 4; L4 vs L for following T. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Switch-off control (u5). The other threshold's meter is unchanged in each arm. N vs C buffer equality. Fresh tables per unit combination. Timeouts raised so slow pages are not errors. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | `applyReadThresholdsValidations` is package-private (reflection). Driver schema refresh under a small coordinator threshold (tables created first). Idle node makes no GC pauses (forced full GC baseline). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | `/local` paths, venv, `jstat`, region size and the client process model fixed (B2a, B3a–B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | Clone `$W/cassandra-run22`, `build-test` (54 s), node `$W/node-vrt`. |
| D. Runnable | workload arithmetic reaches the limit | Met | 539 MB of data; pages 8.4 / 33.6 MB vs T ≤ 4 MiB. Writes of 64 KiB are far below `max_mutation_size` and the native message limit (16 MiB at 4 GiB). 4 GiB heap; 140 GiB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met, with corrections | Checked: `DatabaseDescriptor.java:785, 1091-1105, 4850-4936`; `Config.java:526-532`; `SelectStatement.java:334-335, 1004-1132`; `ResultSetBuilder.java:76-98`; `ReadCommand.java:457-491, 656-736`; `ReadResponse.java:193-204`; `DataOutputBuffer.java:158-183`; `BufferedDataOutputStreamPlus.java:70-139`; `StorageProxy.java:2197-2265`; `ReadCallback.java:192-198`; `WarningsSnapshot.java:113-115`; `CoordinatorWarnings.java:94`; `Dispatcher.java:376-441`; `QueryOptions.java:276-281`; `DecayingEstimatedHistogramReservoir.java:281-300, 537-550`; `EstimatedHistogram.java:91-106`; `ObjectSizes.java:155-174`; `BufferCell.java:141-144`; `BTreeRow.java:532-541`; `conf/jvm11-server.options:63-66`.<br>Corrections, recorded as A3 facts: the coordinator check runs before a row's values are added; the local check is `>=`; the shipped G1 region size is 16 MiB, not 2 MiB; the histogram max is a bucket offset; the master switch is not read by `ReadCommand`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | A3: facts 1–7 (exact refusal rules, switch scope, buffer growth, metric resolution, line-1101 reachability and path per arm, region size) | Amendment 2026-10-25 (audit statement) | The predictions depend on them; three filed statements were imprecise (boundary outcome, humongous at 2 MiB, histogram max). |
| 2 | B1: operational reading, so each claim has a refuting observation | Amendment 2026-10-25 (claim unchanged) | The brief: B1 must be falsifiable. |
| 3 | B2a–B2e: this host; 15 combinations incl. the switch-off control; tables created before thresholds; mirror; replica `len`/`cap`/`alloc`; reflection for line 1101; shakedown | Amendments 2026-10-25 | Paths, exactness, driver schema refresh. |
| 4 | B2f/B2g: exact per-combination predictions from the source (the filed "page bytes ≤ T: no abort in either arm" was wrong for the local arm at P × 65,536 = T); verdict rows | Amendments 2026-10-25 | Group B; a source mistake, independent of any reading. |
| 5 | B3a: this host; 2 MiB regions (the file's B3d basis); own GC log; timeouts 20 s; bundled driver; added Byteman/JMX instruments | Amendment 2026-10-25 | Real resource; `jstat` unavailable; region size. |
| 6 | B3b/B3c: start order, Z run (not optional), read-backs, 16 client **processes** | Amendments 2026-10-25 | Exactness; CPython's interpreter lock would serialize 16 threads. |
| 7 | B3d/B3e: Δ and H definitions, forced full-GC baseline, per-query observables | Amendments 2026-10-25 | An idle node makes no young pauses. |
| 8 | B3f/B3g/B3h: per-query predictions from the source added; filed aggregate relations kept except the L humongous clause (filed "≈ 0" contradicted by fact 4 at 2 MiB regions → "≤ 16"); rows for each threshold | Amendments 2026-10-25 | Group B; the brief. |
| 9 | B4: this host's cleanup | Amendment 2026-10-25 | `/local` paths. |
| 10 | Steps say what each establishes; aggregate heap relations are not derivable from the source (they depend on client concurrency and GC dynamics) | Left for stage 3 (the filed aggregate numbers were kept, not tuned) | See §8 feedback. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit 21:29:38–21:30:02 EDT; cluster attempt 1 21:30:59–21:44, stopped; cluster run 1 21:46:33–22:21:50 EDT) |
| Node | `yangwang-mbp` (advisor's laptop), 10 cores (Apple T6000, arm64), 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434) / Darwin 27.0.0 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Local clone commit | `$W/cassandra-run22` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (`cassandra-5.0.9`). `ant -Dlocal.repository=$W/m2 build-test` succeeded in 54 s. The copied test was removed after each unit run; `git status` is clean (test yaml untouched). |
| Case-file commit / harness commit | `38240d9` plus uncommitted amendments (sha256 above) / uncommitted |
| Storage for node data | internal APFS SSD, `$W/node-vrt` (wiped at the end), `$W/node-vrt-z` for Z (wiped); 141 GiB free before, 140 GiB after |
| Re-checked at step E | free disk 141–142 GiB; ports 7000, 7199, 9042, 9091 free; loopback 127.0.0.1–.3 present; no Cassandra daemon running |
| Full logs | `~/Library/Caches/stage4/logs/coordinator_read_size_fail_threshold-validateReadThresholds/`: `unit-shakedown/`, `unit-run1/`, `cluster-sd/`, `cluster-run1.attempt-1/` (stopped attempt), `cluster-run1/` (incl. `digest-v2.txt`), `selfcheck.out`, `selfcheck-unit.out`, `build-test.log` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster run 1, attempt 1 | B3c (read phase, arm N, P = 128) | 3 s into the phase the node logged `Unknown exception in client networking … No buffer space available` (macOS ENOBUFS on loopback, 4 lines at 01:32:43 UTC) and closed two client connections. With one host and no reconnection, those two workers failed every later query locally (`NoHostAvailable`, 34,745 times), so the phase did not run 16 concurrent clients as B3c requires. The attempt was stopped during arm C; the node was drained and stopped, and the directories wiped ([`run1/cluster-attempt-1/`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1/cluster-attempt-1/)). | The worker rebuilds its driver session after a client-side error and records `reconnect`; the first request of each worker is jittered by 0–500 ms. Claim, predictions and conclusions unchanged; dated fix in the case file's B3c. | Cluster tier restarted from its beginning (load, N, C, L, L4, Z), 2026-10-25. In run 1: 0 reconnects, 0 client-side errors. | sha256 `3ed15193…24c7` (`_INDEX.md` §4) |

**Not defects (no reading changed):**
- `summarize.py` and `selfcheck.py` first read only `gc.log`. The JVM's default `-Xlog` rotation (20 MB) split arm C's log into `gc.log.0` (holding the idle full GC) + `gc.log`. Both scripts were changed after run 1 to read every part, and the digest was regenerated (`digest-v2.txt`; `summary.txt` keeps the first digest, with C's baseline missing). No raw file changed, and no other arm's log rotated.
- The shakedown's final process check listed my own concurrent monitoring shell, whose command line contained the daemon's class name. It was not a node; no node was running. Run 1's final check reads `none`.

Re-freeze after run 1 (R1, a case-file amendment authorised by the user) and harness changes for the unit re-run (added 2026-10-27 by the unit re-run session):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| R1 | unit run 1 (readings, not a runbook defect) | B2f (u3), (u4) replica `len` relation; B2g Refuted (b) replica-buffer clause | The frozen equality "`len` = S(P) of N" missed by −1, +11, −7, +13 B in 4 of 6 C combinations and "`len` = S(16)" by −2 B for L (4,194,304, 16): pages of different tables differ by their timestamp vints. Two negative differences met the literal Refuted (b) text, which the self-check rejected (§5.1 part 3). The tier was Not confirmed (§4.2) | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-27:** two dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user) — B2f (u3) and (u4)` and `— B2g`. Equality replaced by \|`len` − S(P)\| ≤ δ(P), δ(P) = 8·P + 24 B, derived from the on-wire serializer (one liveness-timestamp vint per row, three `EncodingStats` vints per partition, each 1–9 B; §7.1). Refuted (b) replica clause now `len` < S(P) − δ(P). New sha256 `967d12bf…29ed6` as a new row in `_INDEX.md` §4. The whole unit tier was re-run from its beginning in a fresh clone `$W/cassandra-run66` (§7). B1, the relations that held, B2h and B3 unchanged; the cluster tier stays closed | user, 2026-10-27 | `967d12bf001c59f4edadba528f3b45fe091b30bdf1de4a4324ebb478db729ed6` (uncommitted) |
| H1 | unit re-run | self-check | The run-1 `selfcheck.py` evaluates run 1's wording and also the closed cluster tier, and cannot read a shakedown file | New `run1b-unit/selfcheck.py` (unit only, re-written from the unit part of `harness/<stem>/selfcheck.py`): `--relations run1\|amended`, `--shakedown`, `--xml`; prints the B2g rows met, including which combinations meet the old and the amended Refuted (b) wording; exit 0 / 1 / 2 = all hold / some fail / could not run. `harness/<stem>/selfcheck.py` unchanged. Known-answer pass on run 1's raw unit file before the re-run (§7.5) | AI, 2026-10-27 | n/a (harness) |
| — | unit re-run | harness | — | **No change** to `ReadSizeCapUnitTest.java` (sha256 `e2ddd0c5…`, as committed in `c373fa6`) or `unit-run.sh` (`a354a71c…`): the test already records `len`, and only the self-check evaluates the amended relation. The runner takes the clone from `C` | — | — |

Re-freeze after run 1 for the cluster re-run (R2, authorised by the user), the runbook defect found in its shakedown (D2) and the harness changes
for it (H2–H5), added 2026-10-28 by the cluster re-run session:

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| R2 | cluster run 1 (readings, not a runbook defect) | B3f n4, l4, L4-3 (and c4); B3g rows naming them | Every per-query clause held but the aggregate clauses failed: they bound the median post-GC heap above idle and humongous regions, which under refused-query floods measures GC promotion (L 1.8–2.2 GiB), set by client concurrency and GC dynamics, not by the code path (§4.2, §5) | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-28:** seven dated amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` (B3a, B3d, B3e, B3f, B3g, B3h, B4). n4, c4 (which held in run 1 but bounds the same quantity), l4 and L4-3 restated from the source as in-flight replica bytes by event: n, m ≤ 16; per-request held buffer bands; peaks ≤ 16 × per-request bound; L/L4 the 128-byte empty response; V extended (§7b.1). New sha256 `c7256799…f91a`, a new row in `_INDEX.md` §4. B1, the per-query relations and the unit tier unchanged | user, 2026-10-28 | `c725679900ecf6bcbe0d98e33c9ac182000606509748da88384a4b5cd126f91a` (uncommitted) |
| D2 | cluster re-run, shakedown `cluster-sd2` (harness check, before any re-run reading) | B3d (6) `inflight-read` window; B3f amendment item 1 | The shakedown printed max m = 5 with max n = 4 = nc in `sdC` and `sdL` (1 and 2 lines with m = 5; `run1b-cluster/shakedown/sd2-defect-D2/m-equals-5-lines.txt`); every other shakedown check held (self-check 40 of 42, exit 1). Source: `runMayThrow` hands its response to the request at `StorageProxy.java:2230` (failures `:2236`, catch blocks) and then runs latency bookkeeping (`:2239-2241`); the request no longer waits for it and the client's next read can start. The derivation bounds reads up to the hand-over; the instrument ended them at `runMayThrow`'s exit | The `inflight-read` window ends at the hand-over (`AT INVOKE ReadCallback.response` / `onFailure` in `runMayThrow`; exit and exception exit as fall-backs, which printed 0 lines in the re-run); item 1 reads "in flight before their hand-over". No clause or number changed. Said plainly in the case file: noticed because of a shakedown value. Shakedown repeated (`cluster-sd3`: 42 of 42) before the re-run | AI, 2026-10-28, within the user's authorisation of the re-run | `0ab0b5ab2a01939b4dc4aa9f4cefed197ff6ccf31b1db96380357b3fd3196fa1` (new §2 row; uncommitted) |
| H2 | cluster re-run | B3a/B4 paths | `cluster-run.sh` hard-coded run 1's clone, node and helper directories | `C`, `VRT_NODE`, `VRT_HB` from the environment (defaults run 1's); Z directory `$VRT_NODE-z`; `InFlight.java` compiled into the helper jar and listed in the harness hash line. sha256 `c8e9b6a0…` → `f73af5ce…` | AI, 2026-10-28 | n/a (harness) |
| H3 | cluster re-run | digest | — | `summarize.py` prints an `INFLIGHT` line per phase (not the self-check). `a319ef63…` → `569ed9de…` | AI, 2026-10-28 | n/a |
| H4 | cluster re-run | B3d (6) | — | `vrt.btm`: run 1's rules unchanged; new observe-only `inflight` rules (request entry/exit, command bind, buffer built, hold at `createResponse`/`createEmptyResponse`, read start, read end at the hand-over after D2); new helper `InFlight.java`. `TestScript: no errors` before the re-freeze, after D2 and at the start of every runner call. `vrt.btm` `9d5b8387…` → `d451b139…` (re-freeze) → `2cc406b1…` (D2); `InFlight.java` `7c00afec…` → `10f049ec…` (D2) | AI, 2026-10-28 | n/a |
| H5 | cluster re-run | self-check | `harness/<stem>/selfcheck.py` evaluates run 1's wording and needs the unit file; it cannot read a shakedown | `run1b-cluster/selfcheck.py` (sha256 `666d1535…`): the cluster part copied, `--relations run1\|amended`, `--shakedown`, VERDICT lines, exit 0/1/2. Written after the re-freeze and before the shakedown; not changed after it. `harness/<stem>/selfcheck.py` unchanged | AI, 2026-10-28 | n/a |

## 4. Run 1

**Scope:** both tiers, every value and arm of B2b and B3b. **Command log:** `unit-run1/commands.log`, `cluster-run1/commands.log`.
Excerpts are in [`coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1/`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1/):
- `unit/stage4.out`, `unit/summary.txt`
- `cluster/summary.txt`, `cluster/digest-v2.txt`, `cluster/phases.txt`
- `cluster/<arm>/{settings.json, jmx-readback.txt, meters-*.txt, clients-P*.txt, phase-P*.json, trace-head.txt, gc-excerpt.txt}`
- `cluster/Z/refusal.txt`
- `selfcheck.out`

### 4.1 Readings

**Unit tier** ([`unit/stage4.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1/unit/stage4.out); s = 65,544; mirror b0 = 72, h = 65,752 for all 128 rows)

| Combination | Client | Metrics (max = histogram bucket) | Step 3 (replica, page 1) |
|---|---|---|---|
| N P16 / P64 | 128 rows / 128 rows | coordMax 1,131,752 / 4,866,323; local 0; aborts 0 | `len` 1,048,787 / 4,195,098; `cap` 1,049,200 / 4,196,320; `alloc` 3,102,816 / 12,596,624 |
| C 256 KiB P16 / P64 | `ReadFailureException` `{127.0.0.1=4}`, 0 rows (both) | coordMax 263,210 (both); coordAborts 1; local 0 | `len` 1,048,786 / 4,195,109 |
| C 1 MiB P16 | 128 rows | coordMax 1,131,752; aborts 0 | `len` 1,048,787 |
| C 1 MiB P64 | refused, code 4 | coordMax 1,131,752; coordAborts 1 | `len` 4,195,091 |
| C 4 MiB P16 / P64 | 128 rows (both) | coordMax 1,131,752 / 4,866,323; aborts 0 | `len` 1,048,787 / 4,195,111 |
| L 256 KiB P16 / P64 | refused, code 4 (both) | localMax 263,210; localAborts 1; coord 0 | throws, X = 263,080; `alloc` 737,272 / 737,016 |
| L 1 MiB P16 / P64 | refused, code 4 (both) | localMax 1,131,752; localAborts 1 | throws, X = 1,052,104; `alloc` 3,110,576 / 3,110,512 |
| L 4 MiB P16 | 128 rows | localMax 1,131,752; aborts 0 | completes, `len` 1,048,785 |
| L 4 MiB P64 | refused, code 4 | localMax 4,866,323; localAborts 1 | throws, X = 4,208,200; `alloc` 12,604,400 |
| OFF (switch off, both 256 KiB) | 128 rows | coordMax 0; localMax 0; aborts 0 | throws (`trackWarnings()` by hand), X = 263,080 |
| Line 1101 | (1 KiB, 2 KiB) throws `ConfigurationException: <name>_fail_threshold (1KiB) must be greater than or equal to <name>_warn_threshold (2KiB)` for all three pairs; (2, 1) and (1, 1) accepted; setters accept fail 1 KiB under warn 2 KiB and read back `1KiB`/`2KiB` (×3) | | |
| Read-backs | every combination's getters equal the values set (`rb_*`); thread allocation supported and enabled | | |

**Cluster tier** (one node, 127.0.0.1; [`cluster/digest-v2.txt`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1/cluster/digest-v2.txt); idle full-GC baseline 73 MiB, 16 humongous regions in every arm; Δ, H = post-GC heap and humongous regions in [60, 180] s above baseline)

| Arm | P | Client (180 s, 16 processes) | Meters Δ / histogram max | Per query (Byteman, medians) | Δ (MiB) / H (regions) |
|---|---|---|---|---|---|
| N | 128 | 2,840 queries, all OK, 25,560 pages, 0 errors | aborts 0 / 0; CoordinatorReadSize 8,409,007; Local 0 | full-page `len` 8,390,420, `cap` 8,392,704; `read-alloc` 25,223,256 | 202 / 7 (549 pauses) |
| N | 512 | 1,457 queries, all OK, 4,371 pages | aborts 0 / 0; 36,157,190 | `len` 33,561,508, `cap` 33,570,304; `read-alloc` 101,104,648 | 217 / 10 (245) |
| C | 128 | 112,121 queries, all `ReadFailure` `127.0.0.1:4` | CoordinatorReadSizeAborts +112,121; Local +0; max 1,131,752 | 112,121 `guard-fail size=1048704 limit=1048576` (one value); `len` 8,390,292; `read-alloc` 25,207,880 | 284 / 49 (2,591) |
| C | 512 | 32,241, all `ReadFailure` code 4 | +32,241 / +0; 1,131,752 | 32,241 `guard-fail` 1,048,704; `len` 33,561,620; `read-alloc` 101,104,912 | 695.5 / 248 (2,580) |
| L | 128 | 633,654, all `ReadFailure` code 4 | LocalReadSizeAborts +633,654; Coord +0; LocalReadSize 1,131,752 | `local-abort` X = 1,052,104 (one value); 0 full-page `resp-buf`; 633,654 `resp-buf-abort`; `read-alloc` 3,108,608 | 1,802 / 27 (828) |
| L | 512 | 641,595, all code 4 | +641,595 / +0; 1,131,752 | X = 1,052,104; 0 full-page; `read-alloc` 3,111,728 | 2,195 / 24 (885) |
| L4 | 128 | 303,868, all code 4 | +303,868 / +0; 4,866,323 | X = 4,208,200; 0 full-page; `read-alloc` 12,589,736 | 219 / 22 (960) |
| L4 | 512 | 306,240, all code 4 | +306,240 / +0; 4,866,323 | X = 4,208,200; 0 full-page; `read-alloc` 12,595,904 | 219 / 22 (953) |
| Z | — | rc 3 after 2 s, no `Startup complete` | — | `ConfigurationException … coordinator_read_size_fail_threshold (1MiB) must be greater than or equal to coordinator_read_size_warn_threshold (2MiB)` | — |

Read-backs per arm (`system_views.settings` and `StorageService` JMX): switch `true`, the arm's one threshold set (`1MiB` / `1MiB` / `4MiB`), all others null. Each JVM had the Byteman agent, `G1HeapRegionSize=2m` and `-Xmx4G`. Every start reported 0 replayed mutations; 0 `^ERROR` lines in every arm.

### 4.2 Conclusion and logic

1. **Validity.** Both tiers valid.
   - Unit: every read-back equal [observed: `unit/stage4.out` `rb_*`]; thread allocation supported; mirror h equal for all rows (u1) [observed].
   - Cluster: V holds. Read-backs [observed: `cluster/<arm>/settings.json`, `jmx-readback.txt`]; agent/regions/heap [observed: `summary.txt` `PROCESS`]; ≥ 50 queries in every phase (min 1,457); ≥ 245 pauses in every window; a full-GC baseline per arm [observed: `digest-v2.txt`].
   - Limit reached and passed: pages of 8.4 / 33.6 MB against T ≤ 4 MiB [observed].
   - D1 fixed the concurrency deviation: 0 reconnects in run 1 [observed: `clients-P*.txt`].
2. **Readings.** Unusual:
   - (i) Unit replica `len` varies by a few bytes between tables [observed]. The source gives the cause: timestamps are vint deltas from the SSTable's minimum timestamp [inferred: `SerializationHeader.java:165-168`, `UnfilteredRowIteratorSerializer.java:97`].
   - (ii) L's post-GC heap is the largest of all arms, and its young pauses are mostly `G1 Humongous Allocation` with 2,744 mixed collections. The old generation cycles between 1.2 and 2.8 GB [observed: `L/gc.log`, `samples.csv`]. This is promoted garbage from ≈ 3,500 refused queries/s, each allocating a ≈ 1 MiB buffer that is humongous at 2 MiB regions [inferred].
   - (iii) N is client-bound at P = 512: 8 queries/s over 16 processes, so ≈ 2 s per query, and humongous regions after GC only 10 above idle [observed; inferred: CPython decoding of 33 MB pages].
3. **Matched row.**
   - **Unit:**
     - Clauses (u1), (u2), (u5), (u6) hold.
     - (u3) holds for every refusal and non-refusal, counted-size bucket, `LocalReadSizeAborts` = 0, `cap`/`alloc` band. It fails only "`len` = S(P) of N (equal)": −1, +11, −7, +13 B in four combinations [observed; `selfcheck.out`].
     - (u4) holds for every refusal, X, bucket, `alloc` bound and P-independence (ratio 1.000). It fails "completes with `len` = S(16)" for L 4 MiB P16: 1,048,785 vs 1,048,787.
     - So B2g's Confirmed row is not met.
     - By literal text, C 256 KiB P16 (−1 B) and C 1 MiB P64 (−7 B) meet the *Refuted (b)* condition "step 3 under C gives `len` < S(P) of N". **Part 7 of the self-check does not hold for that row** (§5), and the tier is downgraded to **Not confirmed**.
   - **Cluster:**
     - Every per-query clause holds: n1–n3, c1–c3, l1–l3, L4-1, L4-2.
     - c4 holds: 284 ≥ 0.4·202; 695.5 ≥ 0.4·217; 695.5 ≥ 2·284.
     - Z holds.
     - The filed aggregate clauses fail. N: n4 (217 < 3·202; 217 < 400 MiB; H = 10 < 64). L: l4 (1,802 / 2,195 > 64 MiB; grows by 393 > 32 MiB; H = 27 / 24 > 16). L4: L4-3 (219 > 128 MiB and < Δ_L) [observed: `selfcheck.out`].
     - B3g rows matched:
       - "n4 clauses only (Δ_N(512) = 217 ≥ 100 and > Δ_N(128) = 202) → **Not confirmed for the aggregate clauses of (b)**".
       - "L/L4: l1–l3 / L4-1–L4-2 hold but l4 or L4-3 fails → **Not confirmed (a)**: per-query bounded, aggregate heap not shown".
       - Z row: line 1101 as traced.
4. **Excluded rows.**
   - Unit **Refuted (b)** by refusal pattern or counted size: every C combination refused exactly where (P − 1)·s > T, with the predicted bucket [observed].
   - Unit **Refuted (b)** by replica buffer: see part 3 and §5. Under C, `len` stayed 1.05 / 4.20 MB against T = 0.26–4.2 MB, with differences of both signs that also occur between thresholdless tables. It did not shrink towards T.
   - Unit **Refuted (a)**: every L refusal at the predicted k with X ∈ [T, T + h); `alloc` < 5T + 1 MiB and P-independent; L 4 MiB P16 completed as predicted [observed].
   - Unit **Refuted (line 1101)**: messages exact; setters accepted.
   - Unit **Invalid**: read-backs equal, OFF did not refuse on the client path, mirror holds.
   - Cluster **Confirmed**: n4, l4, L4-3 fail.
   - Cluster **Refuted (b)** (buffer): C's full-page `len` is within 128 B of N's at both P (8,390,292 vs 8,390,420; 33,561,620 vs 33,561,508), and Δ_C grew with P (284 → 695.5) [observed].
   - Cluster **Refuted (b)** (mechanism): every query refused; one `guard-fail` size 1,048,704; max 1,131,752.
   - Cluster **Not confirmed (b)** via c4: c4 holds.
   - Cluster **Refuted (a)**: no completed query, X exact, 0 full-page buffers, `read-alloc` 3.1 / 12.6 MB < 6.3 / 22.0 MB, ratio 1.001 / 1.000.
   - Cluster L4 "not greater than L": 12.6 MB > 3.1 MB at both P.
   - Cluster **positive control failed**: no abort in N; n2–n3 hold; Δ_N(512) ≥ 100 and > Δ_N(128).
   - Cluster **switch inactive** and **Invalid**: aborts fired, read-backs equal, starts clean.
   - Cluster **Z starts**: rc 3.
5. **Observed vs. inferred.**
   - (a) The unit `len` differences come from per-table timestamp encoding [inferred from source; supported by L 4 MiB P16, which has no coordinator threshold, also differing by −2 B, and by C combinations above N]. This is what the downgrade rests on.
   - (b) L's large Δ is promoted garbage driven by GC frequency, not live in-flight data [inferred: humongous-allocation-triggered pauses, mixed cycles, per-query `read-alloc` of only 3.1 MB].
   - (c) N's small Δ comes from low server-side concurrency [inferred from query rate].
   - None of (b)–(c) changes a matched row: the rows are decided by the frozen clauses.
6. **Deviations and gaps.**
   - Cluster attempt 1 was stopped (D1).
   - The digest read only the current GC-log file until fixed (§3).
   - Δ is an upper bound on live data (named at the audit). Residency per query is not measured; the per-query observables are allocation and buffer capacity.
   - The row-index threshold is checked only at line 1101 (u6), not exercised on reads.
7. **Core question.**
   - Per query, the local threshold caps the replica's work at T: the refusal comes at the row that takes the tracked size to ≥ T. No page buffer is completed. Allocation is 3.1 MB at 1 MiB and 12.6 MB at 4 MiB, whatever the page size (unit parts 3–4; cluster l1–l3, L4-2).
   - The coordinator threshold caps only the counted result set, at T + less than one row. The replica still serializes the whole page (8.4 / 33.6 MB) under it (unit u3; cluster c1–c3).
   - So the constraint **caps only on some paths (bypass)** per query.
   - The node's aggregate heap did not show either cap. Under a flood of cheap refused queries, L's post-GC heap was the largest of all arms, through GC promotion. The filed aggregate numbers were not met for N or L.
   - The start-up check at line 1101 rejects `fail < warn` exactly as traced; the runtime setters bypass it (u6, Z).

**Conclusion (one line):** Unit — B2g Confirmed not met; literal *Refuted (b)* text met by 1 B and 7 B, rejected by the self-check → **Not confirmed**. Cluster — **Not confirmed (a)** and **Not confirmed (b)** (aggregate clauses), with every per-query clause and line 1101 as predicted.

## 5. Self-check of run 1 — AI

The independent script is [`harness/.../selfcheck.py`](../harness/coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/selfcheck.py). It was written before unit run 1 and before any cluster reading. It re-parses only raw files:
- unit `stage4.out`;
- per arm: `settings.json`, `jmx-readback.txt`, `meters-*.txt`, every `gc.log*`, `vrt.trace`, every worker's `w*.lines` (per-query lines, not the JSON totals);
- `phases.txt`;
- `Z/node.out`, `Z/system.log`.

It recomputes the histogram offsets itself. It was changed once after the run, to read rotated `gc.log.*` parts (§3).

**Result: 184 of 199 checks hold** ([`run1/selfcheck.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1/selfcheck.out)). The 15 failures:
- the 5 unit "equal `len`" clauses (4 C, 1 L);
- the 10 cluster aggregate clauses (n4 ×3, l4 ×5, L4-3 ×2).

These are exactly the deviations in §4.2.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Read-backs, query counts, pause counts and baselines re-derived (`V.*` checks). Thread-allocation line re-read. |
| 2. Readings | yes | `len` values re-read per table. L's `gc.log` pause causes and `samples.csv` old-gen series re-read. N's query rate from `clients-P512.txt`. |
| 3. Matched row | **no for the literal unit row, fixed by downgrade**; yes for the cluster rows | Unit: the literal *Refuted (b)* condition (`len` < S(P) of N) is met by C 256 KiB P16 (1,048,786 < 1,048,787) and C 1 MiB P64 (4,195,091 < 4,195,098). The row's stated meaning ("the coordinator threshold reaches the replica buffer") does not follow from these readings by the audited logic, for three reasons:<br>(i) Step 3 builds the replica response directly (`executeLocally` + `createResponse`) and never reaches `SelectStatement`, the only reader of the coordinator threshold (A3 facts 1 and 4).<br>(ii) The C differences have both signs (two below, two above), and the L 4 MiB P16 table, with no coordinator threshold, differs from N by −2 B.<br>(iii) `SerializationHeader.java:165-168` writes each row timestamp as a vint delta from the SSTable's minimum timestamp, so a page's length varies by a few bytes from table to table.<br>Under C the buffer stayed 1.05 / 4.20 MB against T = 0.26–4.2 MB. A *Refuted* verdict would assert an effect the readings contradict. Per the README, a part that does not hold downgrades the conclusion to **Not confirmed**, and that is what is filed. Cluster rows re-derived clause by clause. |
| 4. Excluded rows | yes | Each excluding reading is a `CHECK … holds` line (refusal patterns, buckets, X, `guard-fail` set, `len` vs N within 128 B, `read-alloc` bounds and ratios, Z). |
| 5. Observed vs. inferred | yes | (a) is supported by observed sign and table pattern and by the cited source. (b) and (c) do not decide any row. |
| 6. Deviations and gaps | yes | D1 evidence re-read (`cluster-attempt-1/enobufs-lines.txt`; 34,745 `NoHostAvailable` in two workers). The rotation fix changed no raw file. |
| 7. Core question | yes, with the part-3 note | Per-query cap (local) → result-set-only cap (coordinator) → aggregate not shown → line 1101, each with its part. |

### 5.2 Run 2?

**No**, decided 2026-10-25.
- The *Not confirmed* verdicts come from frozen clauses that the same harness would fail again: exact byte equality across tables, and aggregate heap numbers that depend on client concurrency and GC dynamics.
- A run 2 by hand on the same case-file version would add no information.
- Every per-query reading is observed directly and was re-derived by the script.
- A useful re-run needs amended predictions (see §8 feedback), which only an authorised re-run can bring.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Unit re-run ("run 1b") after the B2f (u3)/(u4) and B2g Refuted (b) amendment — 2026-10-27

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-27, **authorised by the user (Yang, the advisor) on 2026-10-27**.
Sections 1–6 above are run 1 as filed and are not changed. Run 1's excerpts under `run1/` are untouched. The cluster tier is closed and
was not re-run.

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | In unit run 1 every refusal, counted size, X, allocation bound, the switch-off control and line 1101 held, but the frozen equality "replica `len` under C = N's" (u3) missed by −1 to +13 B, and "`len` = S(16)" (u4, L 4 MiB P16) by −2 B; two negative differences met the literal Refuted (b) text, which the self-check rejected (§5.1 part 3). The tier was Not confirmed. The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised the amendment and a re-run of the whole unit tier on 2026-10-27. |
| **Amendment** | Two paragraphs `Amendment 2026-10-27 (after run 1, authorised by the user) — B2f (u3) and (u4), the replica len relation` and `— B2g, the replica-buffer clause of Refuted (b)`, under B2f and B2g. Each says plainly that it follows run 1's readings.<br>**Tolerance, from the source:** `len` is the length of `LocalDataResponse.build`'s buffer (`ReadResponse.java:197-203`), written by `UnfilteredPartitionIterators.java:329-343` and `UnfilteredRowIteratorSerializer.java:91-154`. For two B2c tables at the same P every byte is the same (key, flags, columns, clustering as a fixed 4-byte int, cell flags, the 65,536-byte value with its vint length; the cell has no timestamp because row liveness and cell share the `INSERT` timestamp, `UpdateParameters.java:126, 172`, `Cell.java:274, 292-293`; no row-size fields on the wire, `UnfilteredSerializer.java:193-209`) except: one unsigned vint per row for `timestamp − minTimestamp` (`UnfilteredSerializer.java:223-224`, `SerializationHeader.java:165-168`) and three unsigned vints per partition for `EncodingStats` (`EncodingStats.java:272-277`). An unsigned vint takes 1–9 B (`VIntCoding.java:535-540`, also for `writeUnsignedVInt32`, `:329-332`). So **δ(P) = 8·P + 24 B** (152 B at P = 16, 536 B at P = 64). A buffer cut towards T would lose ≥ one row (≥ 65,536 B ≫ δ).<br>**Amended relations:** (u3) \|`len` − S(P)\| ≤ δ(P); (u4) L (4,194,304, 16) completes with \|`len` − S(16)\| ≤ δ(16).<br>**Amended row wording, from B1:** B1 (b) says the coordinator threshold does not bound the replica buffer; its operational reading refutes (b) only by "a replica buffer that shrinks towards T". The old clause "`len` < S(P) of N" let through **C (262,144, 16) (−1 B) and C (1,048,576, 64) (−7 B)** in run 1, readings B1 predicts. The new clause is "`len` < S(P) − δ(P)". A `len` above S(P) + δ(P) goes to the existing catch-all → Not confirmed.<br>B1, the relations that held, B2h and B3 are unchanged. |
| **What was known of run 1, and would run 1 pass** | All of run 1's unit readings were known when the amendment was written: every `len` (S(16) = 1,048,787, S(64) = 4,195,098; C differences −1, 0, +11, −7, 0, +13 B; L 4 MiB P16 −2 B), run 1's attribution to `SerializationHeader.java:165-168`, and run 1's section-D suggestion of 9·P + 64 B. That suggestion was not used; δ(P) is the worst case of the vint widths and depends on no reading. **Run 1 would pass:** its largest \|difference\| was 2 B at P = 16 (δ 152) and 13 B at P = 64 (δ 536); under the amended wording no combination meets Refuted (b), and every other clause held, so run 1's unit readings match the Confirmed row (`run1b-unit/selfcheck-known-answer-on-run1.out`: 111 of 111 under `--relations amended`). No source-derived tolerance that admits per-row timestamp encoding could have failed run 1, so the amendment is not one run 1 could have failed; the re-run repeats the whole tier at the frozen version so that the verdict rests on readings taken after the freeze. |
| **Case-file version** | sha256 **`967d12bf001c59f4edadba528f3b45fe091b30bdf1de4a4324ebb478db729ed6`**. It is a new row in `_INDEX.md` §4, "re-frozen after run 1 for unit re-run (B2f (u3)/(u4) replica `len` relation, B2g Refuted (b) replica-buffer clause), authorised by the user". The earlier rows (`4e6f47ae…`, `4f2657bc…`, `3ed15193…`) are kept. Hashed at 19:04:10 EDT, before the fresh clone (19:04:31) and before any re-run reading (shakedown 19:05:59). Section D was filled afterwards. Base commit `bfbfb6c`; nothing committed. |
| **Harness** | Run 1's harness unchanged: `ReadSizeCapUnitTest.java` sha256 `e2ddd0c5…` and `unit-run.sh` `a354a71c…` (both as in commit `c373fa6`), plus the new self-check `run1b-unit/selfcheck.py` (H1, §3).<br>Commands: `C=$W/cassandra-run66 harness/<stem>/unit-run.sh run2-shakedown shakedown`, then `C=$W/cassandra-run66 harness/<stem>/unit-run.sh run2 run` (one forked test JVM each). |

### 7.2 Environment

Same host and storage as run 1 (§2). Shakedown 2026-10-27 19:05:59–19:06:20 EDT; unit re-run 19:07:52–19:08:15 EDT.

- **Clone:** fresh clone `$W/cassandra-run66` from `~/cassandra-src` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change. `ant -Dlocal.repository=$W/m2 build-test` finished `BUILD SUCCESSFUL` in 52 s (`run1b-unit/clone-build-run66.txt`).
- **Disk:** 113 GiB free. **JVM:** OpenJDK 11.0.32.1, max heap 1,056,309,248 B, thread allocation supported and enabled (as in run 1).
- **Before / after:** no `CassandraDaemon` (runner checks); clone `git status` clean after the runner removed the copied test; `$C/build/test/cassandra` removed afterwards.
- **Full logs:** `$W/logs/coordinator_read_size_fail_threshold-validateReadThresholds/`: `unit-run2-shakedown/`, `unit-run2/` (`commands.log`, `summary.txt`, `stage4.out`, `ant.log`, `TEST-*.xml`, `TEST-*.log`), `unit-run2-build/` (clone and build log, runner outputs, known-answer self-check), `selfcheck-unit-run2.out`, `selfcheck-unit-run2-shakedown.out`.
- **Excerpts:** [`run1b-unit/`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-unit/) (`unit/` and `shakedown/` with `stage4.out`, `summary.txt`, `commands.log` (and the JUnit XML for the run); `selfcheck.py`; `selfcheck.out`; `selfcheck-shakedown.out`; `selfcheck-known-answer-on-run1.out`; `clone-build-run66.txt`).

### 7.3 Readings

**Shakedown** (T = 524,288, P = 32; [`run1b-unit/shakedown/stage4.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-unit/shakedown/stage4.out)): mirror b0 = 72, h = 65,752 (all 128 rows); C refused, code 4, coordMax 545,791 = bucket(8·65,544), `len` 2,097,555, `cap` 2,098,240, `alloc` 6,267,456; L refused, code 4, X = 526,088 = b0 + 8h, `alloc` 1,528,480 < 5T + 1 MiB. Self-check 16 of 16, exit 0 (`run1b-unit/selfcheck-shakedown.out`). Not a reading.

**Unit re-run** ([`run1b-unit/unit/stage4.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-unit/unit/stage4.out); `ant` rc 0, `Tests run: 1, Failures: 0, Errors: 0`; s = 65,544; mirror b0 = 72, h = 65,752 for all 128 rows; δ(16) = 152, δ(64) = 536)

| Combination | Client | Metrics (max = histogram bucket) | Step 3 (replica, page 1): `len` (− S(P)), `cap`, `alloc` / X |
|---|---|---|---|
| N P16 / P64 | 128 rows / 128 rows | coordMax 1,131,752 / 4,866,323; local 0; aborts 0 | S(16) = 1,048,786, S(64) = 4,195,095 (ratio 3.99997); `cap` 1,049,200 / 4,196,320; `alloc` 3,102,816 / 12,596,760 |
| C 256 KiB P16 / P64 | `ReadFailureException` `{/127.0.0.1=4}`, 0 rows (both) | coordMax 263,210 (both); coordAborts 1; local 0 | 1,048,785 (−1) / 4,195,109 (+14); `alloc` 3,102,768 / 12,596,624 |
| C 1 MiB P16 | 128 rows | coordMax 1,131,752; aborts 0 | 1,048,786 (0); `alloc` 3,101,936 |
| C 1 MiB P64 | refused, code 4 | coordMax 1,131,752; coordAborts 1 | 4,195,090 (−5); `alloc` 12,593,488 |
| C 4 MiB P16 / P64 | 128 rows (both) | coordMax 1,131,752 / 4,866,323; aborts 0 | 1,048,784 (−2) / 4,195,102 (+7); `alloc` 3,101,936 / 12,593,488 |
| L 256 KiB P16 / P64 | refused, code 4 (both) | localMax 263,210; localAborts 1; coord 0 | throws, X = 263,080; `alloc` 737,064 / 736,808 |
| L 1 MiB P16 / P64 | refused, code 4 (both) | localMax 1,131,752; localAborts 1 | throws, X = 1,052,104; `alloc` 3,109,792 / 3,109,792 |
| L 4 MiB P16 | 128 rows | localMax 1,131,752; aborts 0 | completes, 1,048,786 (0) |
| L 4 MiB P64 | refused, code 4 | localMax 4,866,323; localAborts 1 | throws, X = 4,208,200; `alloc` 12,601,344 |
| OFF (switch off, both 256 KiB) | 128 rows | coordMax 0; localMax 0; aborts 0 | throws (`trackWarnings()` by hand), X = 263,080 |
| Line 1101 | (1 KiB, 2 KiB) throws `ConfigurationException: <name>_fail_threshold (1KiB) must be greater than or equal to <name>_warn_threshold (2KiB)` for all three pairs; (2, 1) and (1, 1) accepted; setters accept fail 1 KiB under warn 2 KiB and read back `1KiB`/`2KiB` (×3) | | |
| Read-backs | every combination's getters equal the values set; warn thresholds null | | |

Every C `cap` was 1,049,200 (P16) or 4,196,320 (P64), as in N. Under run 1's wording these raw files would again fail 5 equalities (C: −1, +14, −5, −2, +7) and again meet the literal old Refuted (b) text in three combinations (C 256 KiB P16, C 1 MiB P64, C 4 MiB P16), different ones from run 1 (`run1b-unit/selfcheck.out`, informational part).

### 7.4 Unit re-run — conclusion and logic

1. **Validity.**
   - The re-run used the re-frozen version (`967d12bf…`), hashed before the clone and the first runner command [observed: `_INDEX.md` §4; `run1b-unit/unit/commands.log` 19:07:53; `run1b-unit/shakedown/commands.log`].
   - Fresh clone at `b5f2a54210…`, unchanged harness (sha256 in `summary.txt` `e2ddd0c5…`), shakedown first [observed].
   - Every read-back equal; thread allocation supported; mirror h equal for all 128 rows, 65,536 < 65,752 < 66,560 (u1) [observed].
   - The run is valid; no Invalid condition is met.
2. **Readings.** As in run 1 to the byte for every refusal, counted size, X and bucket; `len` differed between tables by a few bytes with both signs (C: −5 … +14 B; L 4 MiB P16 0 B), within δ(P) [observed]. The cause is the per-row timestamp vint [inferred: source, §7.1].
3. **Matched row.** B2g **Confirmed** (claims (a) and (b) at the unit tier), read with (u3) and (u4) as amended on 2026-10-27:
   - (u1), (u2) (N: 128 rows, coordMax = bucket(P·s), local 0, `len`/`cap`/`alloc` in band, S(64) ≥ 3.9·S(16)), (u5) (OFF: 128 rows, both histograms 0, step 3 throws at X(262,144)), (u6) hold [observed].
   - (u3): refused exactly where (P − 1)·s > T (256 KiB P16/P64, 1 MiB P64) at bucket(m·s) = 263,210 / 263,210 / 1,131,752; not refused at 1 MiB P16 and 4 MiB P16/P64 with bucket(P·s); `LocalReadSizeAborts` 0; \|`len` − S(P)\| ≤ 14 B ≤ δ(P); `cap`/`alloc` in N's bands [observed].
   - (u4): refused exactly where k(T) ≤ P (all but 4 MiB P16) with X = 263,080 / 1,052,104 / 4,208,200 ∈ [T, T + h), localMax = bucket(X), coordAborts 0, `alloc` < 5T + 1 MiB (0.74 / 3.11 / 12.6 MB against 2.36 / 6.29 / 22.0 MB) and P-independent (ratio 0.9997 / 1.0000); 4 MiB P16 completes with `len` = S(16) (0 B) [observed].
   - Effect: **caps only on some paths (bypass)** — the local threshold caps the replica's page work at T; the coordinator threshold caps the counted result set only, and the replica still builds the full page.
4. **Excluded rows.**
   - **Refuted (b)**, mechanism: every C refusal and non-refusal as predicted, every bucket equal [observed].
   - **Refuted (b)**, replica buffer (amended): no C `len` < S(P) − δ(P); the smallest is S(P) − 5 B [observed].
   - **Refuted (a)**: every L refusal at the predicted k, X in range, `alloc` bounded and P-independent, 4 MiB P16 completed [observed].
   - **Refuted (line 1101)**: messages exact; (2, 1), (1, 1) accepted; setters accepted.
   - **Not confirmed**: S(64)/S(16) = 3.99997 ≥ 3.9; every band of (u2) holds for N and C; every refusal is a `ReadFailureException` with code 4; no C `len` > S(P) + δ(P) and L 4 MiB P16 within δ(16); no other deviation.
   - **Invalid**: read-backs equal; OFF not refused on the client path; mirror holds; allocation supported.
5. **Observed vs. inferred.** Every clause is decided by observed readings. Inferred, and not deciding any row: the cause of the few-byte `len` differences (timestamp vints, §7.1).
6. **Deviations and gaps.** None against the re-frozen runbook. As in run 1, the row-index threshold is checked only at line 1101 (u6), not exercised on reads; `cap` is `measureDeep` of the response (the backing array), not a residency measure.
7. **Core question.** Per query, `local_read_size_fail_threshold` caps the replica's work for a page at T: it refuses at the row that takes the tracked size to ≥ T, completes no page buffer, and allocates 0.74 / 3.11 / 12.6 MB at T = 256 KiB / 1 MiB / 4 MiB whatever the page size. `coordinator_read_size_fail_threshold` caps only the counted result set (T plus less than one row); the replica still serializes the whole page under it, within a few bytes of the no-threshold page. So the constraint caps only on some paths (bypass). Line 1101 rejects fail < warn at start-up only; the setters bypass it.

**Conclusion (one line):** B2g row **Confirmed** (with (u3)/(u4) as amended 2026-10-27). Effect: caps only on some paths (bypass).

### 7.5 Self-check of the unit re-run — AI

`run1b-unit/selfcheck.py` re-reads the raw `stage4.out` and the JUnit XML, not `summary.txt`; it recomputes the histogram offsets, m, k(T), X(T), δ(P) and every band itself, and prints which B2g rows are met. Written and checked before the re-run.

- **Pass 0 (shakedown, end to end):** `--shakedown --relations amended` on `unit-run2-shakedown/stage4.out`: 16 of 16 hold, exit 0 ([`run1b-unit/selfcheck-shakedown.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-unit/selfcheck-shakedown.out)). The shakedown has no N table, so the `len`-vs-N relation is exercised only by the known-answer pass and the run.
- **Known answer (run 1's raw unit file `unit-run1/stage4.out`, before the re-run):** [`run1b-unit/selfcheck-known-answer-on-run1.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-unit/selfcheck-known-answer-on-run1.out).
  - `--relations run1`: 106 of 111 hold, exit 1. The 5 failures are exactly run 1's 5 unit failures in §5 (4 C equalities, L 4 MiB P16), and the script reports the old Refuted (b) wording met by C 256 KiB P16 (−1) and C 1 MiB P64 (−7), as found in §5.1 part 3.
  - `--relations amended`: 111 of 111 hold, exit 0; amended Refuted (b) met by none; Confirmed met. Run 1 passes the amended relations (§7.1).
- **Pass 1 (re-run raw files, amended relations):** [`run1b-unit/selfcheck.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-unit/selfcheck.out). **111 of 111 hold, exit 0.** Rows: Invalid, Refuted (a), Refuted (b), Refuted (line 1101) not met; Confirmed met. Informational: the same files under `--relations run1` give 106 of 111, exit 1.
- **Re-opened by hand:** the N, C and L `STAGE4 row` lines of `unit/stage4.out` (`len`, `cap`, `X`, `codes`, buckets), the twelve `v1101` lines, the mirror line and the JUnit XML header (`tests="1" failures="0" errors="0"`).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-frozen hash and its time before the clone; read-backs, mirror and allocation line re-read. |
| 2. Readings | yes | Every value in §7.3 re-read from `unit/stage4.out`; differences recomputed. |
| 3. Matched row | yes | All (u1)–(u6) clauses hold with the amended (u3)/(u4); no Refuted, Invalid or Not confirmed condition is met. |
| 4. Excluded rows | yes | Each excluding reading is a `CHECK … holds` line; the smallest C `len` − S(P) is −5 B against −152 / −536 B. |
| 5. Observed vs. inferred | yes | Only the cause of the byte differences is inferred, and it decides nothing. |
| 6. Deviations and gaps | yes | None; harness unchanged; H1 recorded. |
| 7. Core question | yes | Local caps the replica's page work; coordinator caps the result set only; line 1101 start-up only. |

**Run 2?** No, decided 2026-10-27. The verdict rests on direct readings that the independent script reproduces, and run 1 gave the same readings to the byte for every refusal, counted size and X.

### 7.6 Verdict of the unit re-run

**Confirmed — caps only on some paths (bypass)** (B2g Confirmed row, with (u3)/(u4) as amended 2026-10-27). Filed in §8 as a new unit row; the run-1 unit row (Not confirmed) is kept.

## 7b. Cluster re-run ("run 1b-cluster") after the B3a, B3d, B3e, B3f, B3g, B3h, B4 amendment — 2026-10-28

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-28, **authorised by the user (Yang, the advisor) on 2026-10-28**.
Sections 1–7 above are kept as filed; run 1's excerpts under `run1/` and the unit re-run's under `run1b-unit/` are untouched; the unit tier
(Confirmed at the unit re-run) was not re-run. Excerpts: [`run1b-cluster/`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/).

### 7b.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | In cluster run 1 every per-query clause and Z held, and the tier was Not confirmed (a) and (b) only on the filed aggregate clauses n4, l4, L4-3: post-GC heap ceilings and floors (≤ 64 MiB; ≥ 400 MiB, ≥ 3×, ≥ 64 regions). Under a flood of refused queries the post-GC heap measures GC promotion (L: 1.8–2.2 GiB of promoted garbage), which depends on client concurrency and GC dynamics, not on the code path (§4.2 parts 2 and 5). The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised on 2026-10-28 that the aggregate clauses be restated from what the source determines and the whole cluster tier re-run. |
| **Source derivation** | (B3f amendment, with `file:line`) The node's in-flight replica heap is the sum over in-flight `ks` requests of what each holds. **Concurrency:** 16 client processes, each with one synchronous session (`Session.execute` → `.result()`, `cluster.py:2677`; `fetch_next_page` waits, `:5224-5225`; no speculative execution, `:383, 438`, in the bundled driver zip); one client request = one `SelectStatement.execute` (`QueryProcessor.java:276`, `SelectStatement.java:280`) reading one page (`:541-544`) through one executor (`StorageProxy.java:2105-2133`) that with RF 1 never speculates (`AbstractReadExecutor.java:207-212`) and makes one local read with its own command (`:116-119, 162-166`), which builds one response (`StorageProxy.java:2209-2219`) — so ≤ 16 requests and ≤ 16 reads before their hand-over. The local read runs on a READ-stage thread (`SEPExecutor.java:188-203, 218-224`: `takeWorkPermit(false)` fails when no task is queued), so the instrument links buffer and request by the command object. **Held per request:** a full-page buffer has len ∈ [P·65,536, P·65,600 + 512] (n2) and cap ∈ [len, 2·len + 65,664] (A3 fact 4), so ≤ capmax(P) = 16,860,288 / 67,241,088 B; the same under C (the replica serializes before the coordinator counts); under L/L4 the read is refused and `createEmptyResponse()` (`StorageProxy.java:2213-2219`, `ReadCommand.java:377-384`) writes two booleans (`UnfilteredPartitionIterators.java:333, 342`) into a fresh 128-byte heap buffer (`DataOutputBuffer.java:57, 94-97`): len 2, cap 128; a refused read allocates < 5·T + 1 MiB (A3 fact 4). The buffer is reachable until `execute` returns; the result set holds copies (`ByteBufferUtil.java:444-452`). |
| **Amendment** | Seven dated amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` (B3a, B3d, B3e, B3f, B3g, B3h, B4), each saying that it follows run 1's readings, plus runbook fix D2 (§3). **Instrument (B3d (6)):** observe-only Byteman `inflight-req` (n and H just before each request's release — exact peaks — and per request cmds, bufs, len, held, pending, orphans) and `inflight-read` (m, rsum at each read's hand-over). **Clauses (B3f, nc = 16):** V + one buffer per request, request counts = client pages (N) / queries (C, L, L4) ± 16, orphans 0, pending ≤ nc; **n4** (i) n, m ≤ nc, (ii) every full-page request P·65,536 ≤ len ≤ held ≤ 2·len + 65,664 ≤ capmax(P), (iii) max H ≤ 16·capmax(P) = 269,764,608 / 1,075,857,408 B, (iv) max H ≥ P·65,536; **c4** the same with (ii) for every request; **l4** (i), (ii) every request len 2 and held 128, max H ≤ 2,048 B, (iii) max rsum < 16·(5T + 1 MiB) = 100,663,296 B; **L4-3** as l4 with 352,321,536 B. **c4 held in run 1** and was restated anyway, because its reference Δ_N is the measure withdrawn. Δ and H are reported as observations. **B3g:** the rows naming the aggregate clauses read the amended clauses; Refuted (b) row 2 "Δ_C flat and small like L with c3 failing" → "C requests hold buffers below P·65,536 with c3 failing"; the N positive-control floor → n4 (ii)/(iv); Invalid gains the in-flight V clause. B1, every per-query relation, Z and the unit tier are unchanged. |
| **What was known of run 1 when writing it, and would run 1 pass** | **Everything in run 1's §4–§5 and section D was known** — all per-query readings (len, cap, `read-alloc` medians, counts), the Δ and H values, the GC-promotion reading — and, while designing V, run 1's `digest-v2.txt` counts of `resp-buf` lines (= client pages under N, = queries under C, L, L4). No number was taken from a reading: nc is B3c's 16 processes; the bands are A3 fact 4 and n2, frozen 2026-10-25 before any reading; 128 B is the source's initial buffer. **Would run 1 pass? Not evaluable:** run 1's raw files have no in-flight lines, so V and the amended n4, c4, l4, L4-3 fail as "missing" (known-answer pass, `run1b-cluster/selfcheck-known-answer-on-run1-relations-amended.out`: 63 of 115, all 52 failures are in-flight checks with no lines; verdict note "not evaluable"). Given run 1's per-query values, the ceilings would be met **if** at most 16 requests and reads overlapped, since they are concurrency × per-query bounds that run 1's per-query values satisfied; the parts run 1 never measured, and the re-run could newly fail, are the concurrency on the node (n, m ≤ 16), one held buffer per request with none outliving it, the band for every request instead of the median, the exact 128-byte empty response, and the peaks. |
| **Case-file version** | Re-frozen at sha256 **`c725679900ecf6bcbe0d98e33c9ac182000606509748da88384a4b5cd126f91a`** (03:29:05 EDT, after the fresh clone and build 03:22:15–03:23:18 and before any shakedown or re-run reading), new `_INDEX.md` §4 row "re-frozen after run 1 for cluster re-run (B3a, B3d, B3e, B3f (n4, c4, l4, L4-3, V), B3g, B3h, B4), authorised by the user"; frozen again after D2 at **`0ab0b5ab2a01939b4dc4aa9f4cefed197ff6ccf31b1db96380357b3fd3196fa1`** (03:37:42 EDT, before the repeated shakedown and the re-run), a further §2 row. The earlier rows (`4e6f47ae…`, `4f2657bc…`, `3ed15193…`, `967d12bf…`) are kept. Hash record [`run1b-cluster/refreeze-run2.txt`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/refreeze-run2.txt); copies of the file at both hashes are in `cluster-run2-build/` of the log folder. Section D was filled afterwards. Base commit `24ee5e63`; nothing committed. |
| **Harness** | Run 1's harness with H2–H5 only (§3; hashes in [`run1b-cluster/harness-sha-run2.txt`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/harness-sha-run2.txt)): `vrtclient.py`, `Alloc.java`, `Jmx.java`, `Sampler.java` unchanged; run 1's Byteman rules unchanged. Commands: `C=$W/cassandra-run74 VRT_NODE=$W/node-vrt74 VRT_HB=$W/harness-bin-vrt74 caffeinate -ims harness/<stem>/cluster-run.sh sd2 sd` (shakedown), `… sd3 sd` (after D2), `… run2 run1` (the whole tier). |

### 7b.2 Environment

Same host as run 1 (§2): `yangwang-mbp`, macOS 27.0.1 / Darwin 27.0.0 arm64, OpenJDK 11.0.32.1, Ant 1.10.18, Python 3.8.11 with the bundled driver 3.29.0; free disk 106 GiB before, 104 GiB after; loopback `.1`–`.3` present (only `.1` used); no `CassandraDaemon` and ports 7000/7199/9042/9091 free before every runner call (runner pre-checks). 2026-10-28 (EDT): fresh clone and build 03:22:15–03:23:18; re-freeze 03:29:05; known-answer self-check passes on run 1's files 03:30–03:33; shakedown `sd2` 03:31:44–03:35:00; D2 re-freeze 03:37:42; shakedown `sd3` 03:38:00–03:41:15; **re-run 03:42:11–04:17:52** under `caffeinate -ims`. Clone `$W/cassandra-run74` from `~/cassandra-src` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change (`ant -Dlocal.repository=$W/m2 build-test`, `BUILD SUCCESSFUL`, 56 s; [`run1b-cluster/clone-build-run74.txt`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/clone-build-run74.txt)). Node as in run 1: 4 GiB heap, G1 with 2 MiB regions, Byteman agent, yaml lines as run 1 (read-backs below); data 2 Data.db files, 539,453,732 B; node data `$W/node-vrt74` (Z: `$W/node-vrt74-z`), wiped at the end.

**Full logs:** `~/Library/Caches/stage4/logs/coordinator_read_size_fail_threshold-validateReadThresholds/`: `cluster-run2-build/` (clone and build log, `refreeze-run2.txt`, `harness-sha-run2.txt`, case-file copies at `c7256799` and `0ab0b5ab`), `cluster-sd2/` and `cluster-sd2.out` (shakedown with D2), `cluster-sd3/` and `cluster-sd3.out`, `cluster-run2/` (as run 1's `cluster-run1/`: `summary.txt`, `commands.log`, `phases.txt`, `testscript.txt`, per start `system.log`, `gc.log*`, `vrt.trace`, `samples.csv`, `read-P*/w*.lines|json`, meters, read-backs; `Z/`), `cluster-run2.out`, `selfcheck-cluster-sd2.out`, `selfcheck-cluster-sd3.out`, `selfcheck-cluster-run2.out`, `selfcheck-cluster-run2-under-run1-relations.out`, `selfcheck-cluster-ka-run1-relations-{run1,amended}.out`.
**Excerpts** in `run1b-cluster/`: `cluster/` (`summary.txt`, `phases.txt`, `testscript.txt`, `commands-excerpt.txt`, `hand-checked-lines.txt`; per arm `settings.json`, `jmx-readback.txt`, `meters-*.txt`, `clients-P*.txt`, `phase-P*.json`, `reconnects-P*.txt`, `trace-head.txt`, `inflight-req-head.txt`, `inflight-read-head.txt`, `gc-excerpt.txt`; `N/enobufs-lines.txt`; `Z/refusal.txt`), `shakedown/sd2-defect-D2/` and `shakedown/sd3/` (summary, phases, TestScript, in-flight heads, self-check), `selfcheck.py`, `selfcheck.out`, `selfcheck-rerun-under-run1-relations.out`, `selfcheck-known-answer-on-run1-relations-{run1,amended}.out`, `refreeze-run2.txt`, `harness-sha-run2.txt`, `clone-build-run74.txt`.

### 7b.3 Readings

**Shakedowns** (harness checks, not readings; 2 × 256 rows, 2 MiB thresholds, P = 128, 4 clients, 20 s). `sd2`: every check held except max m = 5 > 4 in `sdC` and `sdL` (max n = 4) → D2. `sd3` (after D2): 42 of 42, exit 0 — max n = m = 4; `sdN` max H 25,177,728 B, held 8,392,320–8,392,576 B; `sdC` every request one full-page buffer, max H 33,570,304 B, `guard-fail size=2097408 limit=2097152` (= 32·65,544); `sdL` every request len 2 / held 128, max H 512 B, max rsum 25,091,808 B < 4·11 MiB, X = 2,104,136; fall-back read ends 0.

**Re-run** (one node, 127.0.0.1; [`run1b-cluster/cluster/summary.txt`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/cluster/summary.txt), recomputed from the raw files by `selfcheck.py`; idle full-GC baseline 73 MiB / 16 humongous regions in every arm). Read-backs (`system_views.settings` and `StorageService` JMX): switch `true`, the arm's one threshold (`1MiB`, `1MiB`, `4MiB`), all others null; each JVM had the agent, 2 MiB regions and `-Xmx4G`; every start 0 replayed mutations; 0 `^ERROR` lines.

| Arm | P | Client (180 s, 16 processes) | Per query (Byteman, medians) | In-flight (amended clauses) | Δ / H (obs.) |
|---|---|---|---|---|---|
| N | 128 | 2,365 queries, 2,363 OK, 21,277 pages; 2 `ConnectionShutdown` (ENOBUFS on loopback at 07:44:03 UTC, 2 log lines; both workers reconnected, D1) | full-page `len` 8,390,292, `cap` 8,392,576; `read-alloc` 25,216,464; aborts 0 / 0 | 21,279 requests (2 abandoned by the two closed connections), all cmds 1 / bufs 1, orphans 0, pending ≤ 8; max n 13, m 12; 18,916 full-page requests held 8,392,320–8,392,704 B; **max H 75,533,568 B** (≤ 269,764,608; ≥ 8,388,608); max rsum 221,995,552 (info) | 768 MiB / 67 |
| N | 512 | 1,031 OK, 3,093 pages, 0 errors | `len` 33,561,108, `cap` 33,570,304; `read-alloc` 101,089,992 | 3,093 requests; max n 10, m 8; 2,062 full-page held 33,569,280–33,570,816 B; **max H 201,424,384 B** (≤ 1,075,857,408; ≥ 33,554,432); max rsum 577,969,632 (info) | 804 / 85 |
| C | 128 | 121,746, all `ReadFailure` `127.0.0.1:4`; CoordinatorReadSizeAborts +121,746, Local +0, max 1,131,752 | 121,746 `guard-fail size=1048704 limit=1048576` (one value); `len` 8,390,292; `read-alloc` 25,206,040 | 121,746 requests, every one held one full-page buffer 8,392,320–8,392,704 B; max n 16, m 16; **max H 134,281,984 B** (≤ 269,764,608; ≥ 8,388,608); max rsum 399,403,912 (info) | 267 / 53 |
| C | 512 | 33,637, all code 4; +33,637 / +0 | 33,637 `guard-fail` 1,048,704; `len` 33,561,108; `read-alloc` 101,040,848 | 33,637 requests, all full-page 33,569,280–33,570,816 B; max n 16, m 16; **max H 369,276,928 B** (≤ 1,075,857,408); max rsum 1,426,372,312 (info) | 690 / 243 |
| L | 128 | 467,932, all code 4; LocalReadSizeAborts +467,932, Coord +0, LocalReadSize max 1,131,752 | `local-abort` X = 1,052,104 (one value); 0 full-page `resp-buf`; `read-alloc` 3,111,296 | 467,932 requests, every one len 2 / held 128; max n 16, m 16; **max H 1,280 B** (≤ 2,048); **max rsum 49,609,208 B** (< 100,663,296) | 1,591 / 16 |
| L | 512 | 471,905, all code 4 | X = 1,052,104; 0 full-page; `read-alloc` 3,111,376 | 471,905 requests, len 2 / held 128; max n 16, m 16; max H 1,280 B; **max rsum 49,137,304 B** | 2,057 / 18 |
| L4 | 128 | 264,741, all code 4; max 4,866,323 | X = 4,208,200; 0 full-page; `read-alloc` 12,586,016 | 264,741 requests, len 2 / held 128; max n 16, m 16; max H 1,280 B; **max rsum 193,943,080 B** (< 352,321,536) | 231 / 17 |
| L4 | 512 | 215,271, all code 4 | X = 4,208,200; 0 full-page; `read-alloc` 12,598,344 | 215,271 requests; max n 16, m 16; max H 1,408 B; **max rsum 195,786,352 B** | 176 / 18 |
| Z | — | rc 3 after 1 s, no `Startup complete` | — | `ConfigurationException … coordinator_read_size_fail_threshold (1MiB) must be greater than or equal to coordinator_read_size_warn_threshold (2MiB)` | — |

Every per-query value repeats run 1 to the byte where it is exact (guard size, X, histogram maxima) and within a few hundred bytes where it is a median (`len`, `read-alloc`). The fall-back read ends (exit, exception exit) printed 0 lines. Under run 1's relations these raw files fail 8 of 89 checks (§7b.5 pass 4) — a different set from run 1's: n4's 400 MiB and 64-region floors now hold, and **c4 at P = 128, which held in run 1, now fails** (Δ_C 267 < 0.4 × Δ_N 768); Δ_N moved from 202 / 217 MiB (run 1) to 768 / 804 MiB with the same code, data and client.

### 7b.4 Cluster re-run — conclusion and logic

1. **Validity.**
   - The re-run used the version frozen after D2 (`0ab0b5ab…`, hashed 03:37:42, before the repeated shakedown and the re-run at 03:42:11) [observed: `refreeze-run2.txt`, `cluster/summary.txt` start line, `_INDEX.md` §4].
   - Fresh clone, unchanged per-query instruments, TestScript no errors, shakedown first (twice, D2 between) [observed: `testscript.txt`, `shakedown/`].
   - V holds: read-backs equal the yaml; agent, regions and heap on every JVM; ≥ 1,031 queries per phase; in every phase the `inflight-req` lines equal the server requests (client pages under N, queries under C, L, L4; N P = 128: 21,279 against 21,277, the 2 requests of the two connections closed by ENOBUFS), each with cmds 1, bufs 1, orphans 0, pending ≤ 15 [observed: `selfcheck.out` `V.*`].
   - The two N `ConnectionShutdown` errors are the D1 condition (ENOBUFS), handled by D1's reconnect; they are not `ReadFailure`, so n1 holds, and 2 of 2,365 queries do not change any clause.
2. **Readings.** As in run 1 per query. New: the node held at most 16 requests and 16 reads in flight; under N and C each in-flight request held one page-sized buffer (8.39 / 33.57 MB) and the peaks were 75.5 / 201.4 MB (N) and 134.3 / 369.3 MB (C), i.e. up to 9 / 6 (N) and 16 / 11 (C) page buffers at once; under L/L4 each request held 128 B and the peaks of what the in-flight reads had allocated were 49.6 / 49.1 MB (L) and 193.9 / 195.8 MB (L4) [observed]. The post-GC heap again moved independently of the code path (Δ_N ×3.8 from run 1; Δ_L 1.6–2.1 GiB) [observed; obs. only].
3. **Matched row.** B3g **Confirmed** (row 1), with V, n4, c4, l4, L4-3 as amended 2026-10-28 [observed; computed by `run1b-cluster/selfcheck.py`]:
   - V; n1–n3 (no abort; full-page `len` in band, ratio 4.000; `read-alloc` ≥ 2·P·65,536); **n4** (i) 13 / 10 ≤ 16 and m 12 / 8; (ii) all 18,916 / 2,062 full-page requests in [P·65,536, 2·len + 65,664]; (iii) 75.5 / 201.4 MB ≤ 269.8 / 1,075.9 MB; (iv) ≥ 8.4 / 33.6 MB;
   - c1–c3 (all 155,383 refused with code 4, meter = refused, one `guard-fail` value 1,048,704, max 1,131,752, `len` within 0 B of N's median, `read-alloc` ≥ floor); **c4** (i) n = m = 16; (ii) every C request held a full-page buffer (≥ 8·T at P = 128, ≥ 32·T at P = 512); (iii) 134.3 / 369.3 MB ≤ ceilings; (iv) ≥ floors;
   - l1–l3 and L4-1–L4-2 (all 1,419,849 refused, X exact, maxima exact, 0 full-page buffers, `read-alloc` 3.11 / 12.6 MB < 6 / 21 MiB, ratio 1.000 / 1.001, L4 > L at both P); **l4** (i) 16 / 16; (ii) all 939,837 requests len 2 / held 128, max H 1,280 ≤ 2,048; (iii) 49.6 / 49.1 MB < 96 MiB at both P; **L4-3** (ii) all 480,012 len 2 / held 128, max H ≤ 1,408; (iii) 193.9 / 195.8 MB < 336 MiB;
   - Z refused with the line-1101 message.
   - Effect: **caps only on some paths (bypass)** — the local threshold caps the replica's work for a page at T and, with 16 clients, the node's in-flight replica bytes at 16 × (5T + 1 MiB), whatever P; the coordinator threshold caps the counted result set only, and every in-flight query still holds a page-sized replica buffer, so the node's in-flight replica bytes follow P (up to 16 × page), not T.
4. **Excluded rows.**
   - **Refuted (b)** (mechanism): no C query completed; one `guard-fail` value; max 1,131,752. (buffer): C's held buffers 8.39 / 33.57 MB, never below P·65,536; `len` equal to N's median.
   - **Not confirmed (b)**: c4 holds.
   - **Refuted (a)**: no L/L4 query completed; X exact; 0 full-page buffers; `read-alloc` bounded and P-independent.
   - **Not confirmed (a)**: l4, L4-3 and L4-2 hold.
   - **Positive control failed / n4 only**: n1–n4 hold.
   - **Switch inactive, Invalid**: aborts fired, read-backs equal, V holds, starts clean.
   - **Z starts**: rc 3.
5. **Observed vs. inferred.** Every clause is decided by observed lines. Inferred, deciding nothing: that "held" (completion to request end) bounds the time a buffer is reachable from its request; that the ENOBUFS closures are a loopback property of this host (as D1).
6. **Deviations and gaps.** None against the re-frozen runbook after D2 (§3). D2 changed the instrument window after a shakedown value, with no clause or number changed; it is stated plainly in the case file and here. The amendment was written knowing all of run 1's readings (§7b.1). Gaps named in B3d (6): the coordinator's result-set copy and Netty's direct encoding buffers are not in H; rsum is allocation, not residency; post-GC heap is not live in-flight data (observation only). The row-index threshold is checked only at line 1101.
7. **Core question.** Per query and in aggregate: `local_read_size_fail_threshold` caps what the replica builds for a page at T (no page buffer, 3.11 / 12.6 MB per read at T = 1 / 4 MiB whatever P), and the node's in-flight replica bytes stay below 16 × (5T + 1 MiB) — 49.6 MB at 1 MiB and 196 MB at 4 MiB, the same at P = 128 and 512, and moving with T. `coordinator_read_size_fail_threshold` caps the counted result set at T plus less than one row, but every refused query still held a full page buffer on the replica, so the node's in-flight replica bytes under it followed the page size (134 MB at P = 128, 369 MB at P = 512) as under no threshold. Line 1101 rejects fail < warn at start-up only. **Caps only on some paths (bypass).**

**Conclusion (one line):** B3g row **Confirmed** (with V, n4, c4, l4, L4-3 as amended 2026-10-28 and runbook fix D2). Effect: caps only on some paths (bypass).

### 7b.5 Self-check of the cluster re-run — AI

`run1b-cluster/selfcheck.py` (H5) re-reads the raw `settings.json`, `jmx-readback.txt`, `meters-*.txt`, `gc.log*`, `vrt.trace`, every worker's `w*.lines`, `phases.txt` and Z's `node.out`/`system.log`; it takes b0 = 72 and h = 65,752 from the unit re-run's mirror line, recomputes the histogram offsets, m, k, X, capmax and every ceiling itself, and does not read `summary.txt` or `summarize.py` output. Written after the re-freeze and before the shakedown; not changed afterwards (sha256 `666d1535…` throughout).
- **Pass 0a (shakedown `sd2`, end to end):** 40 of 42, exit 1 — the two failures are c4/l4 (i) with max m = 5 > 4 ([`shakedown/sd2-defect-D2/selfcheck.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/shakedown/sd2-defect-D2/selfcheck.out)) → D2.
- **Pass 0b (shakedown `sd3`, after D2):** 42 of 42, exit 0; verdict line "all clauses hold (shakedown, not a reading)" ([`shakedown/sd3/selfcheck.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/shakedown/sd3/selfcheck.out)).
- **Known answer (run 1's raw files, before the shakedown):** `--relations run1`: 79 of 89, exit 1; its 97 CHECK/INFO lines are **identical** to the cluster part of `run1/selfcheck.out` (`diff` empty), i.e. the same 10 aggregate failures ([`selfcheck-known-answer-on-run1-relations-run1.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/selfcheck-known-answer-on-run1-relations-run1.out)). `--relations amended`: 63 of 115, exit 1; all 52 failures are in-flight checks with no lines; verdict note "not evaluable" ([`…-relations-amended.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/selfcheck-known-answer-on-run1-relations-amended.out)).
- **Pass 1 (re-run raw files, amended relations):** **115 of 115 hold, exit 0**; `VERDICT tier: Confirmed -- caps only on some paths (bypass)` ([`selfcheck.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/selfcheck.out)).
- **Pass 2 (information: re-run raw files, run 1's relations):** 81 of 89, exit 1 — n4 3×, c4 P = 128 (held in run 1), l4 × 4, L4-3 × 2, l4 not-grow ([`selfcheck-rerun-under-run1-relations.out`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/selfcheck-rerun-under-run1-relations.out)).
- **Re-opened by hand:** the `inflight-req` lines at each peak H and the `inflight-read` lines at each peak rsum ([`cluster/hand-checked-lines.txt`](coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous/run1b-cluster/cluster/hand-checked-lines.txt): e.g. C P = 512 `n=14 H=369276928 cmds=1 bufs=1 held=33570816 len=33561620`, L P = 128 `m=16 rsum=49609208 own=3109232`), a `guard-fail` and an L4 `local-abort` line, the N ENOBUFS lines and the two reconnects, the Z refusal lines, and 0 fall-back read ends.
- Note: the per-query check names for L4 inherit run 1's naming (`L4-2.L4.P*.X`, `L4-3.L4.P*.no_full_page`, …); they are the per-query L4-1/L4-2 clauses, kept so that the run-1 identity holds.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Hash times; read-backs; V counts, cmds/bufs, orphans, pending re-derived. |
| 2. Readings | yes | Every number in §7b.3 recomputed from the raw files. |
| 3. Matched row | yes | All amended and unchanged clauses pass; no Refuted, Not confirmed or Invalid condition is met. |
| 4. Excluded rows | yes | Each excluding reading is a `CHECK … holds` line. |
| 5. Observed vs. inferred | yes | Only the meaning of "held" and the cause of ENOBUFS are inferred; neither decides a row. |
| 6. Deviations and gaps | yes | D2 and the non-blind amendment stated; gaps named. |
| 7. Core question | yes | Local: caps per query and in aggregate (16 × (5T + 1 MiB)); coordinator: result set only, in-flight replica bytes follow P. |

**Run 2?** No (2026-10-28). Per-query readings repeat run 1 exactly, the amended clauses are decided by exact event counts and peaks with margins of 1.45–5.3× below the ceilings, and the independent script reproduces them.

### 7b.6 Verdict of the cluster re-run

**Confirmed — caps only on some paths (bypass)** (B3g row 1, with V, n4, c4, l4, L4-3 as amended 2026-10-28). Filed in §8 as a new cluster row; the run-1 cluster row (Not confirmed (a) and (b)) is kept.

**End of the re-run:** no `CassandraDaemon` process (runner `final … none`; re-checked); ports 7000/7199/9042/9091 free; `$W/node-vrt74` and `$W/node-vrt74-z` removed; `git -C $W/cassandra-run74 status` clean; no `cassandra.logdir_IS_UNDEFINED/` folder; `results/<stem>/run1/` and `run1b-unit/` unchanged.

## 8. Verdict — AI

**Stage-3 estimate:** undetermined.

**Claim tested (B1):** with `read_thresholds_enabled: true` and fail threshold T,
- (a) `local_read_size_fail_threshold = T` bounds the per-query read heap (replica response buffer plus result set) to about T plus one row;
- (b) `coordinator_read_size_fail_threshold = T` bounds the counted result-set size to about T plus one row, but **not** the replica response buffer, so node heap per in-flight query still follows the page size.

Separately, the line-1101 check only rejects `fail < warn` at start-up.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed**. Every refusal, counted size (bucket), X, allocation bound, switch-off control and line-1101 assert held exactly. The frozen "replica `len` equal to N's" failed by −7 to +13 B, from per-table timestamp encoding. The literal *Refuted (b)* text met by two combinations was rejected by the self-check (§5.1 part 3). | caps only on some paths (bypass): local caps the replica's page work at T; coordinator caps the result set only, and the replica still builds the full page | run 1 + self-check | 2026-10-25 |
| Cluster | **Not confirmed (a)** and **Not confirmed (b)**: aggregate clauses n4, l4, L4-3 failed. Per query, all as predicted: C refused all 144,362 queries at counted 1,048,704 B while the replica built 8.4 / 33.6 MB pages as with no threshold; L/L4 refused 1,885,357 queries at X = 1,052,104 / 4,208,200 with 3.1 / 12.6 MB allocated per query at both P; Z refused to start. | caps only on some paths (bypass), per query. Node heap: not shown (L's post-GC heap 1.8–2.2 GiB) | run 1 + self-check | 2026-10-25 |
| Unit (re-run at `967d12bf…`, after the user-authorised B2f (u3)/(u4) and B2g Refuted (b) amendment) | **Confirmed** (B2g Confirmed row, with (u3)/(u4) as amended). Every clause of (u1)–(u6) held: C refused exactly where (P − 1)·65,544 > T at counted size m·65,544 (buckets 263,210 / 263,210 / 1,131,752), not at P × 65,536 = T; the replica `len` under C was within −5 … +14 B of N's (δ = 152 / 536 B), `cap` equal to N's; L refused exactly where 72 + k·65,752 ≥ T, X = 263,080 / 1,052,104 / 4,208,200, allocation 0.74 / 3.11 / 12.6 MB independent of P, L 4 MiB P16 completed with `len` = S(16); OFF and line 1101 as traced; self-check 111 of 111 | caps only on some paths (bypass): local caps the replica's page work at T; coordinator caps the result set only, and the replica still builds the full page | unit re-run (§7) + self-check | 2026-10-27 |
| Cluster (re-run at `0ab0b5ab…`, after the user-authorised B3a, B3d, B3e, B3f (n4, c4, l4, L4-3, V), B3g, B3h, B4 amendment and runbook fix D2) | **Confirmed** (B3g row 1, with V, n4, c4, l4, L4-3 as amended 2026-10-28). Per query as in run 1: C refused all 155,383 queries at counted 1,048,704 B while the replica built 8.39 / 33.56 MB pages as with no threshold; L/L4 refused all 1,419,849 queries at X = 1,052,104 / 4,208,200 with 3.11 / 12.6 MB allocated per read at both P; Z refused. In-flight (amended): ≤ 16 requests and reads; every N full-page and every C request held one page buffer (8.39 / 33.57 MB), peaks 75.5 / 201.4 MB (N) and 134.3 / 369.3 MB (C) ≤ 16 × page buffer; every L/L4 request held the 128-B empty response (peak ≤ 1,408 B); peak in-flight read allocation 49.6 / 49.1 MB (L) and 193.9 / 195.8 MB (L4) < 96 / 336 MiB; self-check 115 of 115. Post-GC heap reported only (L 1.6–2.1 GiB; under run 1's relations c4 would now fail) | caps only on some paths (bypass): local caps the replica's page work at T and the node's in-flight replica bytes at 16 × (5T + 1 MiB) whatever P; coordinator caps the counted result set only, and the node's in-flight replica bytes follow P (up to 16 page buffers) | cluster re-run (§7b) + self-check | 2026-10-28 |

**What each outcome means here.**
- The **local** threshold stops a replica read at the row that takes its tracked heap size to ≥ T. The replica's per-query work is bounded by a small multiple of T and does not depend on the page size.
- The **coordinator** threshold refuses after counting T plus at most one row of result values. The replica's response buffer is still page-sized (bypass on the replica side).
- Neither bounds the node's aggregate heap in this workload. A high rate of refused queries kept the old generation full of promoted garbage: 1.8–2.2 GiB under `local_read_size_fail_threshold: 1MiB`.
- `read_thresholds_enabled` gates only the client path. A command tracked by hand is checked with the switch off (u5).
- Line 1101 is a start-up check only. The `DatabaseDescriptor` setters (the JMX path) accept fail < warn.

**Feedback filed:**
- The case file's section D was filled (uncommitted). Amendments: 19 audit amendments, plus runbook fix D1 in B3c (dated). No section was amended after any reading other than D1, which is a runbook fix with predictions unchanged.
- Index rows: `_INDEX.md` §1 (Stage 4), §2 (two new hash rows: audit freeze, D1 re-freeze), §3 (coverage line 17 / 0).
- For stage 3:
  - (1) A byte-exact equality between tables is not derivable; serialized pages differ by up to ≈ 9 B per row (vint timestamp deltas). A tolerance of 9·P + 64 B would have been the source-derived form.
  - (2) Post-GC heap is not "live in-flight data". Under refused-query floods it measures GC promotion; the filed Δ ceilings (≤ 64 MiB) and floors (≥ 400 MiB, ≥ 3×, ≥ 64 regions) depend on client concurrency and GC dynamics, not on the code path.
  - (3) The shipped `jvm11-server.options` sets 16 MiB G1 regions; the file's humongous reasoning assumed 2 MiB.
  - (4) A CPython client is client-bound at 33 MB pages: about 8 queries/s over 16 processes.

**Processes:** after the cluster tier, `final CassandraDaemon processes: none`, and `node-vrt` was wiped (`run1/cluster/summary.txt`). Re-checked at the end of the session:
- `ps -eo command | grep '[C]assandraDaemon'` was empty;
- ports 7000/7199/9042/9091 were free;
- `$W/node-vrt*` were removed;
- the run clone was clean (copied test removed, test yaml untouched);
- the repository root had no `build/` or log folder.

**Feedback filed for the unit re-run (2026-10-27):** the two amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` in the case file (B2f (u3)/(u4); B2g Refuted (b) replica-buffer clause); a new `_INDEX.md` §4 row (`967d12bf…`); the case file's section D (new entry); the §1 Stage 4 column (run-1 text kept, re-run verdict appended). The §3 coverage line is unchanged, because the case was already counted as closed. No refutation, so no other case section is amended. Stage-3 recommendation (1) above was applied in this form, authorised by the user, with δ(P) = 8·P + 24 B derived from the serializer instead of the 9·P + 64 B suggested after run 1.

**Processes (unit re-run):** no `CassandraDaemon` before or after (runner checks `none`), no test JVM left; ports 7000/7199/9042/9091 free; clone `$W/cassandra-run66` clean (`git status` 0 entries) after the runner removed the copied test, `$C/build/test/cassandra` removed; no `cassandra.logdir_IS_UNDEFINED/` folder; no `build/` or log folder in the repository root; `run1/` unchanged. Re-checked at the end of the session.

**Feedback filed for the cluster re-run (2026-10-28):** the seven amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` in the case file (B3a, B3d, B3e, B3f — n4, c4, l4, L4-3 and V restated as in-flight replica bytes by event —, B3g, B3h, B4) and runbook fix D2 (B3d (6)); two new `_INDEX.md` §4 rows (`c7256799…`, `0ab0b5ab…`); the case file's section D (new entry); the §1 Stage 4 column (earlier text kept, cluster re-run verdict appended). The coverage section is not touched. No refutation, so no other case section is amended. Run-1 observations kept: post-GC heap under refused-query floods measures GC promotion (seen again: Δ_L 1.6–2.1 GiB, Δ_N 768 / 804 MiB against run 1's 202 / 217 MiB); the `DatabaseDescriptor`/JMX setters accept fail < warn (u6). Recommendation for stage 3: an aggregate-heap prediction should be stated as concurrency × per-query bytes with an instrument that sees in-flight bytes (allocation and release by event), not as post-GC heap; and a read's "in flight" window should end where it hands its response over, since `LocalReadRunnable.runMayThrow` keeps running after that (D2).

**Processes (cluster re-run):** runner `final CassandraDaemon processes: none` after `sd2`, `sd3` and `run2`; re-checked at the end of the session: `ps -eo command | grep '[C]assandraDaemon'` empty; ports 7000/7199/9042/9091 free; `$W/node-vrt74*` removed; clone `$W/cassandra-run74` clean (`git status` 0 entries); `$W/harness-bin-vrt74` holds compiled helpers only; no `cassandra.logdir_IS_UNDEFINED/` folder; no `build/` or log folder in the repository root; `run1/` and `run1b-unit/` unchanged.
