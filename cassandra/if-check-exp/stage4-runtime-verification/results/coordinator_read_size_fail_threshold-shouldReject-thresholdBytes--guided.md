# coordinator_read_size_fail_threshold-shouldReject-thresholdBytes — stage-4 results  <!-- file: long-path/results/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes.md -->

> **Case:** [`coordinator_read_size_fail_threshold-shouldReject-thresholdBytes`](../../stage3-ai-deep-read/cases/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md)
>
> **Status:** verdict filed (2026-10-15) — **unit: Confirmed; cluster: Confirmed** (§9a row 1): the guard refuses exactly the reads whose rows before the last exceed the limit, the counter at every abort is *X* = (⌊*F*/1,008⌋ + 1)·1,008 whatever the rows asked for (263,088 · 1,049,328 · 4,195,296 at 262,144 · 1,048,576 · 4,194,304), *n\** = 261 · 1,041 · 4,162 follows the knob, an abort builds no result and no frame and allocates on the coordinator what the (*n\**+1)-row read allocates (406,520 B vs 11,638,752 B for the unset read); **bypass as recorded** (paging delivers all 8,000 rows at 262,144, `count(*)`, switch off); **replica answer not withheld, as recorded** (28.09 MB built at every value); no run 2
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
| **Case-file version** | Base commit `d47b932` (the last commit touching the case file) plus the step-0 amendments of 2026-10-15 (uncommitted at freeze). §9 hash before the amendments `7d8b511276e9cd0ab9226b2d47e716a5930c6a4f`, §9a `d5e836e3d60b9cdbc41eaf67dba6b8560b3f7e9e`; **after the amendments §9 `56689bfe4441a3468e532ac1664e8ae7ebea5e27`, §9a `d563a86ec4131072ea7208cc80582eed02987721`** (§9a changed by amendment (1), the unit allocation fit, for a reason taken from the source). §9a is frozen at this version. Recorded 2026-10-15 08:55 EDT, before any reading of this case existed (no `crs` folder under `pc57:~/stage4-logs/` or `~/stage4-harness-run/`). |
| **Harness** | `../harness/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes/`, written after the freeze (§1.2). Node copy `pc57:~/stage4-harness-run/crs/`. |
| **Tiers and values** | Unit: `CoordinatorReadSizeGuardTest` at 65,536 · 262,144 · 1,048,576 · 4,194,304 B and unset, boundary 100,800 / 100,799, arms at 262,144 / 65,536 / 1 B. Cluster (one node on `pc57`, 4 GiB heap, one lifetime): 262,144 · 1,048,576 · 4,194,304 · 16,777,216 B and unset, 1 B for arm C4. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-15 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Value bytes of one request's `ResultSet` (heap) and the response frame built from it (§7). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | Cluster 262,144 · 1,048,576 · 4,194,304 · 16,777,216 B and unset (the default); unit four values and unset (9b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Allocated bytes of the coordinator thread inside `process()` (`coord-alloc`), the encoded result size (`frame`), the replica's allocation (`read-alloc`); **retention is inferred**, not measured (9d names the gap: the result set is short-lived). Accepted: a post-GC heap reading cannot see a set that lives for milliseconds. |
| A. Core question | usage driven to the limit and past it | Met | 8,064,000 B of value bytes against limits up to 4,194,304; one value (16 MiB) above the data. |
| B. Logic | each step says what it establishes | Met | 9a Logic (1)–(5). |
| B. Logic | prediction stated in numbers or a clear relation | Met | *n\**, *X* per value (table), 1,020 B per row in the frame, 0.25 ± 0.03 allocation increments, 5 % pair equality. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | 10 rows incl. *usage exceeds the limit* (completed read with (*n* − 1)·*s* > *F*), *flat* (*n\** the same at every value), *counter capped but the real resource grows* (whole-partition abort allocates more), *another guard binds*, invalid. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | 9a "Two rules": `guard-fail` line, WARN text, `CoordinatorReadSizeAborts`. |
| B. Logic | alternative explanations and their controls | Met | Replica-side guards held unset (code 4 shared); switch-off arm; unset control; `read-alloc` as the not-withheld control. |
| C. Specific | a human can follow it from the intro and §9a | Met | — |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after rec. 2 | The sibling's client reconnects per call; a reconnect re-reads `system_schema` with client `SELECT`s, which the guard refuses at a small limit (rec. 2). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after rec. 1 | "within 15 % (stage 4 sets the final tolerance from the spread)" left a tolerance to be chosen after the readings (rec. 1). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Listed as step-1 work (9c); `~/cassandra-run1` at `b5f2a54` is built (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`), JDK 11.0.32.1, Ant 1.10.12. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 8,000 × 1,008 B = 8,064,000 B > 4,194,304; about 8 MB on disk; 4 GiB heap; about 6 min. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `SelectStatement.java:994-1022` (`process()`: new builder, `build()` then `maybeWarn()` only), `:1057-1081` (`maybeFail()`: switch, `shouldReject`, WARN, two metrics, `recordReadRegularAbort`, throw), `:1086-1153` (`processPartition()`: `:1092` check at entry, `:1125-1132` row *j* pulled, row *j*−1 added by `newRow()`, then the check), `:280-360` (`execute()`: `trackWarnings` when the switch is on; unpaged vs pager; aggregates always go through the pager); `ResultSetBuilder.java:60-171` (`size`, `addSize()` over value `remaining()`, `shouldReject` `>`, `newRow()` adds the previous row, `build()` adds the last row); `QueryOptions.java:257-320` (captured per options object; `-1` for `null`); `DatabaseDescriptor.java:4878-4888` (INFO `updating  coordinator_read_size_fail_threshold to {}`); `StorageService.java:7274-7307`, `:7357-7373` (String attribute, read back as `quantity + unit`, e.g. `262144B`); `TableMetrics.java:859`, `ClientRequestMetrics.java:50-69`, `StorageProxy.java:2061-2065` (meters); `ResultSet.java:48`, `:142-187`, `:347-367` (public `metadata`, `encodedSize` = metadata + 4 + Σ (4 + length), `toString()` prints `(ks, table)` per column); `ResultMessage.java:172-192` (Rows encode → `ResultSet.codec.encode`). Python driver 3.29.0 (bundled): `ReadFailureMessage` reads the error-code map from protocol 5 (`protocol.py:253-277`), warnings kept for any response (`cluster.py:4627`). Arithmetic of the *n\**/*X* table re-done: all four rows hold. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Replace the unit tier's absolute allocation fit Δ(*F*) = Δ0 + *a*·(*n\** + 1) by a slope fit over the three aborts, with the 15 % tolerance fixed now. | Applied 2026-10-15 (9 intro amendment (1), 9a unit "Allocation", 9c "Starting values"); uncommitted | An abort has a fixed cost no completed read has (message formatting, `asCQL`, WARN line, client warning, exception with stack trace, `SelectStatement.java:1063-1079`); the old relation would fail for that reason alone. A tolerance chosen after the readings would tune the prediction. |
| 2 | One driver session for the whole cluster lifetime, held by the run script; `send-read.py` only for `probe` and `load`. | Applied 2026-10-15 (9 intro amendment (2), 9c `send-read.py` row) | 9b requires one connection; the sibling's client reconnects per call, and each reconnect's schema refresh is refused at a small limit (at 1 B every multi-row read). |
| 3 | Unit table name: `createTable()` in `cql_test_keyspace`. | Applied 2026-10-15 (amendment (3)) | `CQLTester` convention; *s* unchanged. |
| 4 | Keep the 1 B window (C4) to one read, then 16 MiB; record other keyspaces' WARN lines in it. | Applied 2026-10-15 (amendment (4)) | No exemption (§5): the node's own multi-row internal reads are refused in that window too. |
| 5 | Measure retention, not only allocation (e.g. a held read with a heap histogram). | Left for stage 3 | Would need a hold point inside `process()`; the design's allocation reading answers the core question with the gap named. |

**Agreement criteria** — not filled (run 2 not chosen yet).

### 1.2 Instrument checks (not readings)

- **Unit instrument run** (`unit-run.sh harness`, 08:58 EDT, `~/cassandra-run1`, log root `~/stage4-logs/crs/instrument/`):
  101 checks, 0 MISMATCH, `Tests run: 1, Failures: 0`. Not a reading; run 1 repeats the tier.
- **Byteman:** `coord-read.btm` + `read-alloc.btm` type-check (`TestScript: no errors`, logged by every `cluster-run.py` start).
- **Shakedown 1** (`cluster-run.py shakedown1`, 09:00–09:04): every instrument check passed (probe at protocol 5, JMX read-backs,
  one line of each kind for a `ks1` read and none for `system.local`, 10 s idle silent, one `Data.db`); 28/29 `EXPECTED` yes. The
  one miss was an instrument defect, not a reading: **the first abort of the lifetime allocated 807,656 B** against 406,680 B for
  the next abort at the same value (every later pair agreed within 1.4 %). Fixed by a warm-up abort and a JMX `null` write before
  the control (runbook defect 1, §3).
- **Shakedown 2** (09:04–09:05) with the fix: 29/29; the first counted abort 407,168 B against 405,624 B.
- Harness copy `~/stage4-harness-run/crs/` identical to the repository by `md5sum` (`~/stage4-harness-run/crs.md5`) before run 1.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-15, 09:05 EDT on |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu`), 32 cores, 251 GiB RAM |
| OS and kernel (`uname -r`) | Ubuntu, 5.15.0-187-generic |
| JDK (`java -version`) | OpenJDK 11.0.32.1 |
| Ant (`ant -version`) | 1.10.12 |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54` (`cassandra-5.0.9`) |
| Case-file commit / harness commit | `d47b932` + uncommitted amendments (§1) / harness uncommitted, md5 list in `~/stage4-harness-run/crs.md5` |
| Storage for node data | local disk, `~/cassandra-run1/data` (`/dev/sda3`) |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/crs/` (`instrument/`, `shakedown1/`, `shakedown2/`, `run1/` with `unit/` and `cluster/`, `run1/chain.log`) |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown 1 (before run 1) | 9e cluster, step 2 (first scenario B) | The first abort of a node lifetime allocates about 400 KB of one-off costs (807,656 B vs 406,680 B for the next abort at the same *F*), which would fail the 5 % pair check at 262,144 for a reason unrelated to the guard. | Step 0 added to 9e: one uncounted abort (`ck < 300` at 262,144), then the limit written back to `null` over JMX (`Jmx.java null:`, read back `null`); 9b's knob row amended. §9a unchanged (hash `d563a86e…`); §9 hash after the fix `aa118b1f267c9384db25d409694f34415a63ba74`. | Applied 2026-10-15 09:04, before run 1 | uncommitted |

## 4. Run 1

**Scope:** unit tier (`CoordinatorReadSizeGuardTest`, 09:05–09:06 EDT) and cluster tier (one node lifetime, 09:06–09:07 EDT),
every value of 9b; the optional upstream dtest `CoordinatorReadSizeWarningTest` (09:08). **Command log:** `run1/chain-head.txt`
(the chain and its exit lines), `run1/cluster/summary.txt` (every command's result line and `EXPECTED:` line; full
`session.log` on the node). Raw excerpts: `run1/unit/harness.out`, `run1/cluster/crs.trace` (the whole Byteman trace, 392
lines), `run1/cluster/system-excerpt.log` (every WARN and INFO line of the guard), `run1/cluster/readings.csv`.

### 4.1 Readings

**Unit tier** (101 checks, 0 MISMATCH, `Tests run: 1, Failures: 0`; `run1/unit/harness.out`):

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Known answer: completed `getSize()` = 1,008·*n* for *n* = 100 · 1,000 · 2,000 | 100,800 · 1,008,000 · 2,016,000, rows pulled = *n* | `harness.out` `known_*` |
| Read-back: getter and new options = *F*; −1 when unset | equal at 65,536 · 262,144 · 1,048,576; −1 | `readback_*` |
| Stop at *F* = 65,536 · 262,144 · 1,048,576: `ck < n*` completes with *X*; `ck < n*+1` and whole abort with *X* and *n\** + 1 rows pulled | *n\** 66 · 261 · 1,041; *X* 66,528 · 263,088 · 1,049,328 (> *F*); 67 · 262 · 1,042 pulled for both aborts | `A_*`, `B_*` |
| Boundary `>`: *F* = 100,800 → `ck<101` completes 101,808, `ck<102` aborts 101,808; *F* = 100,799 → `ck<100` completes 100,800, `ck<101` aborts 100,800 | as predicted | `boundary_*` |
| Above the data (4,194,304) and unset: whole completes, 2,016,000; unset leaves both meters unchanged | as predicted | `above_*`, `unset_*` |
| Client path (protocol 5): `ck < n*` returns *n\** rows; both longer reads `ReadFailureException` with map `{/127.0.0.1=4}`; meters +2 per value | as predicted at each *F* | `client_*` |
| Frame: `encodedSize(ck<200) − encodedSize(ck<100)` | 204,068 − 102,068 = **102,000** | `frame_slope_102000` |
| Allocation: abort slope vs completed-read *a*; increment ratio | Δ = 112,152 · 396,552 · 1,530,256 B; slope **1,454.5** vs *a* **1,456.9** B/row (−0.2 %); ratio **0.2509** | `info abort allocs` |
| Replica response size the same at every *F* and unset | 2,023,987 B each | `replica_resp_same_*` |
| Arms: paging 100 at 262,144 → 2,000 rows; paging 1,000 → code 4; `count(*)` at 65,536 → 2,000; switch off → whole completes, meters unchanged; internal query → `ReadSizeAbortException`; `system_schema.keyspaces` at 1 B → code 4, client meter +1 | as predicted | `C1_*`, `C2_*`, `C3_*`, `C_internal_*`, `C4_*` |
| Upstream dtest `CoordinatorReadSizeWarningTest` (optional) | 10/10 pass | `run1/unit/upstream-summary.txt` |

**Cluster tier** — *F* in bytes; *n\** = ⌊*F*/1,008⌋ + 1; all from `run1/cluster/crs.trace`, `summary.txt`, `system-excerpt.log`:

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| — | instrument | lines per `ks1` read; `system.local`; idle 10 s; read-backs | one each of `coord-alloc`, `frame`, `read-alloc`, `result`; none; none; `null` / `true` | `summary.txt` `INSTRUMENT` |
| 262,144 | warm-up (not a reading) | first abort of the lifetime | aborted, `coord-alloc` 808,304 B (the one-off cost of runbook defect 1); limit then written back to `null` (read back `null`) | `crs.trace` line 6, `summary.txt` `WARMUP` |
| unset | control | `result size`; `frame bytes`; `coord-alloc`; `read-alloc` | 1,008,000 · 2,016,000 · **8,064,000** (valid); 1,020,037 · 2,040,037 · 8,160,037 = 37 + 1,020·rows; 1,460,904 · 2,920,344 · 11,638,752 (*a* = 1,454.0 B/row); whole 28,113,848 | `crs.trace` |
| 262,144 | A `ck<261` | rows, `result`, `frame` | 261 rows, size 263,088, frame 266,257 = 37 + 1,020·261 | `crs.trace`, `summary.txt` |
| 262,144 | B `ck<262` / whole | `guard-fail`; client; meters; WARN; frame | `size=263088 limit=262144` both; `ReadFailure {127.0.0.1: 4}` + client warning `… 262,144 bytes …`; table and client meters +1 each; one WARN each; **no `frame`, no `result`** | `crs.trace`, `summary.txt`, `system-excerpt.log` |
| 262,144 | B `coord-alloc` | (*n\**+1)-row vs whole | 407,280 vs 406,520 B (−0.19 %) | `crs.trace` |
| 1,048,576 | A / B | as above | 1,041 rows, 1,049,328, frame 1,061,857; aborts `size=1049328`; `coord-alloc` 1,554,536 vs 1,506,920 (−3.06 %) | `crs.trace` |
| 4,194,304 | A / B | as above | 4,162 rows, 4,195,296, frame 4,245,277; aborts `size=4195296`; `coord-alloc` 5,937,608 vs 5,936,504 (−0.02 %) | `crs.trace` |
| 16,777,216 | whole | completes | 8,000 rows, 8,064,000, frame 8,160,037, no `guard-fail` | `crs.trace` |
| all | real resource | `coord-alloc` increments (whole aborts) | (1,506,920 − 406,520) : (5,936,504 − 1,506,920) = **0.2484**; 262,144 abort = 3.49 % of the unset whole read | `crs.trace` |
| all | replica | `read-alloc` of the whole-partition read | 28,113,848 (unset) · 28,087,432 · 28,087,432 · 28,087,384 · 28,087,432 (all within 0.1 %) | `crs.trace` |
| 262,144 | C1 | `fetch_size` 100 / 1,000 | 8,000 rows over 81 pages (80 × 100 + an empty last page), every page `result size` 100,800, no `guard-fail` / aborts on page 1, `size=263088` | `crs.trace`, `summary.txt` |
| 262,144 | C2 | `count(*)` | 8,000; one output row of 8 value bytes (`result size=8`) | same |
| 262,144 | C3 | switch off (`ReadThresholdsEnabled` false) | whole completes, 8,000 rows, meters unchanged, no `guard-fail` | same |
| 262,144 | C5 | scan `SELECT * FROM ks1.t` | aborts, `size=263088 limit=262144` | same |
| 1 B | C4 | `SELECT keyspace_name FROM system_schema.keyspaces` | `ReadFailure {127.0.0.1: 4}`, `guard-fail ks=system_schema size=11 limit=1`, client meter +1; no other WARN line in the window | same |
| — | stop | WARN lines vs aborts | 10 = 9 aborts + the warm-up; INFO `updating  coordinator_read_size_fail_threshold to …` for each set, in order | `system-excerpt.log` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The unset whole-partition read reports 8,064,000 [observed: `crs.trace` `result size=8064000 rows=8000`];
   every read-back equals the value set and the node logged each update [observed: `summary.txt` `SET … read back`,
   `system-excerpt.log`]; `read_thresholds_enabled: true`, the other read guards unset (only `CoordinatorLargeReadAbortThreshold`
   moves) [observed: `summary.txt` yaml line, `INSTRUMENT jmx`]; one `Data.db` [observed: `DATASET`]; one driver session at
   protocol 5 [observed: `SESSION`]; `getThreadAllocatedBytes` supported [observed: `harness.out` `allocatedBytesSupported true`].
   The limit was reached and passed at three values and not at the fourth (above the data), as planned.
2. **Readings** — nothing contradicts another. The first abort of the lifetime is the one outlier (808,304 B); it is the
   warm-up, excluded by the runbook before run 1 (§3) [observed: `crs.trace` line 6]. The (*n\**+1)/whole pair at 1,048,576 differs
   by 3.06 %, inside 5 % [observed]. The last page of C1 is empty (81 pages): the pager returns a paging state after a full page.
3. **Matched row** — "Unit: completed counters are *n*·1,008 exactly; each abort has `getSize()` = *X*(*F*) and *n\** + 1 rows
   pulled; the boundary pair behaves as `>`; the allocation follows *n\**. Cluster: *n\**, *X* and `coord-alloc` follow the knob
   (1 : 4); every abort has the WARN line, the meters, code 4 and no frame; *X* does not depend on the rows asked for" →
   **Confirmed**. Unit: `known_*`, `B_*` (*X*, *n\** + 1 pulled), `boundary_*`, slope 1,454.5 vs *a* 1,456.9 and ratio 0.2509
   [observed: `harness.out`]. Cluster: *n\** 261 · 1,041 · 4,162 (increments 780 : 3,121 = 1 : 4.00), *X* 263,088 · 1,049,328 ·
   4,195,296 identical for `ck<n*+1` and the whole partition, `coord-alloc` increments 0.2484; each of the 6 scenario-B aborts
   has the WARN line, both meters +1, `{127.0.0.1: 4}` and no `frame` [observed: `crs.trace`, `summary.txt`, `system-excerpt.log`].
   Also matched: "**Bypass as recorded**" (C1 paging 8,000 rows, 8,064,000 B over 81 pages against *F* = 262,144; `count(*)`;
   the switch-off read; completed reads hold up to one row above *F*: 263,088 > 262,144) and "**As recorded**" for the replica
   (28.09 MB at every value) [observed].
4. **Excluded rows** — *Refuted (completes above the line / wrong counter)*: no read with (*n* − 1)·1,008 > *F* completed and
   every abort printed *X*(*F*) [observed]. *Refuted (abort allocates more / frame for an abort)*: the pairs agree within 3.1 %
   and no aborted read has a `frame` or `result` line [observed]. *Not as recorded (replica falls with F)*: flat within 0.1 %.
   *Refuted (X depends on rows / n\* fixed)*: *X* identical for both aborts at each value, *n\** moves 1 : 4. *Not confirmed
   (another `READ_SIZE` source)*: every abort has this guard's WARN text and its table meter; the replica-side guards are
   unset. *Refuted in part (exemption)*: the `system_schema` read (cluster and unit) and the internal query (unit) were
   refused. *Invalid*: excluded by part 1.
5. **Observed vs. inferred** — Every statement above is observed. Inferred, and named as the gap: that the result set is
   **resident** up to the abort (the reading is allocated bytes, not a retained-heap reading) [inferred: §7, 9d trap]; that
   the response frame follows the encoded size measured at `ResultSet$Codec.encode` (the rule reads `encodedSize`, not the
   `ByteBuf`) [inferred: `ResultMessage.java:185-192`, `Message.java:367`].
6. **Deviations and gaps** — The warm-up abort and the JMX `null` write before the control (runbook defect 1, applied before
   run 1, §9a unchanged). `limit × N` (concurrent requests) is not tested (9b scope). Retention is not measured (rec. 5,
   left for stage 3).
7. **Core question** — Following 9a's logic: (1) the known answer holds exactly (part 1, unit `known_*`); (2) reads of *n\** rows
   complete and *n\** + 1 abort with `size` = *X*, and the boundary pair shows `>` (part 3): usage **stops at the limit**, at most
   one row above it; (3) *n\**, *X* and the coordinator's allocation follow the knob 1 : 4 (part 3): usage **follows the
   constraint**; (4) every abort carries this guard's WARN, meters, code 4 and no frame (part 3): **this guard** enforces it;
   (5) the whole-partition abort allocates what the (*n\**+1)-row abort allocates while the replica's 28 MB answer is built
   at every value (part 3): the guard withholds the result, not the replica answer. So the constraint caps the value bytes
   of one request's result set (per page) at *F* + one row, and the coordinator's allocation for the result follows it.

**Conclusion (one line):** §9a row 1 — **confirmed**, both tiers; rows "Bypass as recorded" (paging, `count(*)`, switch
off) and "As recorded" (replica answer) also observed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

An independent script, `run1/selfcheck.py` (re-parses `crs.trace` grouped into reads by time, `system-excerpt.log`, the
client lines of `summary.txt` and `harness.out`; recomputes *n\**, *X*, the frame relation, the pair and ratio checks from the
source constants, not from the run script's `EXPECTED:` lines), exited 0: **41 ok, 0 fail** (`run1/selfcheck.txt`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `crs.trace` control group `result size=8064000`; `system-excerpt.log` nine INFO updates in order (selfcheck lines 4–6, 33). |
| 2. Readings | yes | The 808,304-B line is the warm-up group (selfcheck "warm-up (not a reading)"); the 3.06 % pair re-computed from the trace. |
| 3. Matched row | yes | Each scenario-B group: one `guard-fail` with *X*(*F*), `coord-alloc exit=exception`, no `result`, no `frame` (selfcheck); WARN text per abort (selfcheck "10 WARN lines … limits in order"); client `{127.0.0.1: 4}` × 9; meters +1 per abort. Unit numbers re-derived from `harness.out`. |
| 4. Excluded rows | yes | Re-derived from the same groups; C4's group has only the `system_schema` line. |
| 5. Observed vs. inferred | yes | The two inferred statements are the gap §9d names; neither is needed for row 1's evidence (counter, verdicts, allocation, no frame). |
| 6. Deviations and gaps | yes | Runbook defect 1 is before run 1 and leaves §9a's hash unchanged (`d563a86e…` re-computed after the fix). |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Logic (1)–(5) of 9a each map to an observed reading (part 7). |

### 5.2 Run 2?

**No** (2026-10-15). Every load-bearing statement is observed and exact (counters, verdicts, frame sizes, meters), the
self-check holds in every part, the allocation relations hold with wide margins (0.2484 against 0.25 ± 0.03; pairs within
3.1 % against 5 %), and the result neither refutes the case nor confirms a new bypass (the escapes are the recorded ones).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** (row 1); escapes "as recorded" (paging, `count(*)`, switch off); internal query and `system_schema` not exempt | run 1 + self-check | 2026-10-15 |
| Cluster | **Confirmed** (row 1); **Bypass as recorded** (paging delivers 8,000 rows at 262,144; `count(*)`; switch off); **As recorded** (replica answer built at every value) | run 1 + self-check | 2026-10-15 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" updated (2026-10-15, uncommitted); the §9 intro amendments and the
9b/9e runbook fix are in the case file (uncommitted). No refutation, so no other section is amended.
