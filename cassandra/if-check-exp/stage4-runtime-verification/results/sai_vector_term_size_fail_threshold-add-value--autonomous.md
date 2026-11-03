# sai_vector_term_size_fail_threshold-add-value--autonomous — stage-4 results  <!-- file: results/sai_vector_term_size_fail_threshold-add-value--autonomous.md -->

> **Case:** [`sai_vector_term_size_fail_threshold-add-value--autonomous`](../../stage3-ai-deep-read/cases/sai_vector_term_size_fail_threshold-add-value--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/sai_vector_term_size_fail_threshold-add-value--autonomous/`](../harness/sai_vector_term_size_fail_threshold-add-value--autonomous/).
>
> **Unit: Confirmed — caps only on some paths (bypass)** (B2g rows 1 and 5).
> - Fail threshold 8191 B: no 8,192-byte vector entered the memtable graph. `MemtableIndexBytes` was 0, ANN returned 0 rows, live
>   `float[]` grew by 0 B, and `validateTermSize` returned false; the 500 rows themselves were stored.
> - At 32 KiB (default) and at exactly 8 KiB (strict `>`): 4,404,500 B index estimate, +4,218,672 B live `float[]`, ANN 10.
> - Overwriting the same 500 keys under the 8191 B cap put them in the graph anyway: +4,216,208 B live `float[]`. Against the
>   no-index control D0, memtable ownership rose by 4,404,500 B, the same as the insert-path estimate. `MemtableIndexBytes` stayed 0.
>
> **Cluster: Confirmed — caps only on some paths (bypass)** (B3g rows 1 and 5). One node, 10,000 rows of `vector<float, 2048>`.
> - Fail threshold 4 KiB: `MemtableIndexBytes` 0, live `float[]` +0 B, ANN 0, and 10,000 "too large and cannot be indexed" lines.
> - At 32 KiB: `MemtableIndexBytes` 90,010,000 B, live `float[]` +84,883,192 B, ANN 10.
> - Overwrite under 4 KiB: live `float[]` +84,894,168 B, the same as at 32 KiB, while `MemtableIndexBytes` read 0.
> - Arm E (ordinary role, PasswordAuthenticator): every write was refused with `Guardrail sai_vector_term_size violated: Value of column
>   'v' has size 8192, this exceeds the failure threshold of 4096.`
>
> No run 2.
>
> **Agent:** autonomous. In this file, "§9a" means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster). "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).
> An earlier stage-3 session wrote the case file; this session did not.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | As filed: sha256 `585f6e00…1fdec` (`_INDEX-advisor.md` §2; in git `HEAD` `780b696`). Frozen after the step-0 audit's sixteen amendments (2026-10-26, before any run-1 reading) at sha256 **`c1b87bd8ad5642005a18823bc0e75ced63d454518a60f32fa69c59f39c69f1c0`**. Both tiers' readings were taken at this version. A new row was added to `_INDEX-advisor.md` §2. `run1/freeze.txt` holds this hash plus the harness and self-check hashes. Section D was filled after the verdict (file sha256 now `cb69afbf…1421`); everything above section D still hashes to `c1b87bd8…f1c0`. Nothing committed: no commit was asked for. |
| **Harness** | [`../harness/sai_vector_term_size_fail_threshold-add-value--autonomous/`](../harness/sai_vector_term_size_fail_threshold-add-value--autonomous/) (Note 1) |
| **Tiers and values** | **Unit (B2):** one `ant testsome` JVM; arms A (16KiB/32KiB), B (4KiB/8KiB), C (2KiB/8191B), D (C, two passes), D0 (C, two passes, no index), plus the KA known-answer probe; N = 500, dim 2048. **Cluster (B3):** one node per arm, heap 4G, `memtable_heap_space` 2048MiB; arms A (16KiB/32KiB), C (2KiB/4KiB), D (C, two passes), E (C, PasswordAuthenticator, ordinary role); 10,000 rows each. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

**Note 1, harness files:**
- `VectorTermSizeCapTest.java`: an `SAITester` subclass with one `@Test` per arm plus KA. It prints `PROBE` lines and makes no
  assertions. Real heap is read in-process through the `DiagnosticCommand` MBean's `gcClassHistogram`.
- `unit-run.sh`: copies the test in, runs `testsome`, keeps the logs, removes the test.
- `probe.py`: a bundled-driver client (setup, with role and grants for E; load; ann; count).
- `JmxGet.java`: a JMX attribute reader (single-file `java` launch).
- `cluster-run.sh`: the four arms, one node lifetime each.

**Note 2, instrument checks before the freeze** (shakedowns, not evidence; excerpts in `shakedown/`):
- **Unit shakedown**, N = 100 (`shakedown/unit1-N100-summary.txt`): 6 tests ran, and KA read exactly 4,104,000 B. The clone was clean
  afterwards. No change was needed.
- **Cluster shakedown 1**, arms A and E at full size (`shakedown/cluster1-armsAE-summary.txt`): A's live `[F` moved by about 84.9 MB,
  so the instrument sees the graph (amendment B3d's check). E's role, grants and refusal worked.
  - One harness fix: the `READBACK` grep also matched `internode_authenticator=` and `network_authorizer=`. It was anchored to the
    exact key in `cluster-run.sh`.
- **Cluster shakedown 2**, arms C and D, 2,000 rows (`shakedown/cluster2-armsCD-rows2000-summary.txt`): the two-pass path and the log
  grep worked. `probe.py` gained a `VTS_ROWS` override for this shakedown only; run 1 used the default 10,000.
- No amendment text and no prediction was changed after a shakedown reading.

**Note 3, self-check:** [`run1/selfcheck.py`](sai_vector_term_size_fail_threshold-add-value--autonomous/run1/selfcheck.py) was written
before run 1. Its sha256 `d2cc8ed2…4597` is in `run1/freeze.txt` and was unchanged for run 1. On the shakedowns it parsed every line
and failed only the size-bound checks, as expected at reduced N (`shakedown/selfcheck-on-shakedown.out`, 27/42).

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap of the memtable vector graph; the threshold is compared with term bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Met | Unit: 32 KiB (default), 8 KiB (boundary), 8191 B. Cluster: 32 KiB and 4 KiB. Because the cap is per term, usage is all-or-nothing per column; the boundary arm tests the comparison. |
| A. Core question | real resource measured, not only the counter | Partly → Met after amendment | Cluster: the filed design already used live `[F`. Unit: B2d said real heap was not observable, but it is in-process (amendment B2d: the class histogram through the DiagnosticCommand MBean, with a KA probe). |
| A. Core question | usage driven to the limit and past it | Met | 8,192-B terms against 8191 B / 8 KiB / 32 KiB (unit) and 4 KiB / 32 KiB (cluster). |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f bounds; units fixed by amendment B3f. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | No verdict words; no row for a mixed D (bytes grow, ANN 0); no Not-confirmed or Invalid rows (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Disallow evidence: `validateTermSize` false and the check's own "too large and cannot be indexed" log lines; E: the guardrail's refusal text. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Unit D's `ownsOnHeap` also carries a second copy of base data (the slab is not reclaimed on overwrite), so "D grows" did not isolate the graph. Control arm D0 was added (amendments B2b, B2h). ANN in D depends on `primaryKeys`, which `update()` never fills, so it was made report-only (amendment B2f). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Data generation, output format, arm order, instruments (amendments B2c–B2e, B3c–B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Same amendments; E's authorizer and grants (amendment B3b). |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | `/local/disk`, Linux, `ant jar`, `bin/cassandra -p`, `pip` venv, `nodetool sjk`, `GC.heap_info` did not fit this host (amendments B2a, B3a, B3d, B4). |
| D. Runnable | workload arithmetic reaches the limit | Partly → Met after amendment | Data fits (≈ 260 MB largest memtable vs ≈ 683 MiB cleanup threshold, amendment B3a). But load concurrency 16 exceeds jvector's pool limit of 11 concurrent inserts, which throws, so it was set to 8 (amendment B3c). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Note 4. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: host clone, `build-test`, read thresholds off | Amendment 2026-10-26 | Paths; the unit yaml enables read thresholds. |
| 2 | B2b: control arm D0 | Amendment 2026-10-26 | Overwrite's base-data bytes confound D's `ownsOnHeap`. |
| 3 | B2c: exact data and query vectors | Amendment 2026-10-26 | Group C. |
| 4 | B2d: in-process live `float[]` with a KA probe; output format | Amendment 2026-10-26 | Group A (real resource). |
| 5 | B2e: arm order and reading order | Amendment 2026-10-26 | Group C. |
| 6 | B2f: predictions for the added observables; D's ANN report-only | Amendment 2026-10-26 | Group B (`update()` does not fill `primaryKeys`). |
| 7 | B2g: verdict words and closing rows, Effect per row | Amendment 2026-10-26 | Group B. |
| 8 | B2h: controls added | Amendment 2026-10-26 | Group B. |
| 9 | B3a: host node, heap 4G, bundled driver, flush arithmetic | Amendment 2026-10-26 | Paths. |
| 10 | B3b: run E with CassandraAuthorizer, role and grants | Amendment 2026-10-26 | `GRANT` is refused under AllowAllAuthorizer (`AllowAllAuthorizer.java:38`). |
| 11 | B3c: concurrency 8; data and query vectors | Amendment 2026-10-26 | jvector pool limit (`PoolingSupport$ThreadPooling.get`, `javap`). |
| 12 | B3d: JMX client; heap = histogram Total; summary lines | Amendment 2026-10-26 | `sjk` and `GC.heap_info` unreliable on this host. |
| 13 | B3e: one script, arm order, stop sequence | Amendment 2026-10-26 | Group C. |
| 14 | B3f: units; D judged on `[F`; ANN in D report-only | Amendment 2026-10-26 | Group B. |
| 15 | B3g: verdict words and closing rows; E reported separately | Amendment 2026-10-26 | Group B. |
| 16 | B4: host paths | Amendment 2026-10-26 | Paths. |
| 17 | A3.7: say that `update()` also skips `primaryKeys`, so whether bypassed keys are returned by ANN depends on the range path | Left for stage 3 (section D) | A trace detail; both tiers returned 10 here. |
| 18 | A3.7/B1: the bypass needs only an overwrite of a key whose row is still in the current memtable, which is an ordinary upsert, not a corner case | Left for stage 3 | Bears on how strong "caps" is in practice. |

**Note 4, citations checked** in `~/cassandra-src` at `cassandra-5.0.9`:
- `VectorMemoryIndex.java:88-104, 108-146, 170-201`; `OnHeapGraph.java:93-117, 133-205, 260-283`; `ConcurrentVectorValues.java:51-55`;
  `StorageAttachedIndex.java:147, 200-210, 521-530, 815-833, 989-1008`.
- `MemtableIndexManager.java:69-111, 141-159`; `MemtableIndex.java:90-104`; `IndexMetrics.java:43-63`; `AbstractMetrics.java:84-95`;
  `BTreePartitionUpdater.java:126-141`; `SecondaryIndexManager.java:1545-1590`.
- `Guardrails.java:544-551`; `MaxThreshold.java:50-60`; `Threshold.java:105-114`; `Guardrail.java:93-96`; `GuardrailsOptions.java:1034-1045,
  1207-1222`; `Config.java:945-946`; `AllowAllAuthorizer.java:38`; `DatabaseDescriptor.java:753-756, 1107, 4857`;
  `CassandraRelevantProperties.java:538`.
- `test/conf/cassandra.yaml:6, 63-69`; `conf/cassandra.yaml:783-790, 797, 811`; `conf/jvm11-server.options:63`; `CQLTester.java:1218-1230,
  2594-2600`.
- jvector 1.0.2 `PoolingSupport$ThreadPooling.get` (`javap -c -p`).

All hold as filed. A3.7 is right that `update()` skips the check. It does not mention that `update()` also skips `primaryKeys.add`
(amendment B2f).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 19:25:08–19:25:35 EDT; cluster 19:25:42–19:30:54 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro) |
| Hardware | 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 130 GiB free |
| Network and processes | Loopback 127.0.0.1–.3 present (one node on 127.0.0.1). Ports 7000/7199/9042 free and no daemon before the run; none after. |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: `ant testsome` forked JVM. Node: `-Xms4G -Xmx4G`, G1 (read back from `JVM Arguments`) |
| Ant | 1.10.18 |
| Python / driver | Python 3.8.11; bundled `cassandra-driver-internal-only-*.zip` (subfolder import), protocol 5 |
| Local `cassandra-src` clone | `$W/cassandra-run40` = `~/Library/Caches/stage4/cassandra-run40`, a fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`. `ant -Dlocal.repository=$W/m2 build-test`: `BUILD SUCCESSFUL`. `git status` clean after both tiers. |
| Case-file commit / harness commit | filed version in `HEAD` (`780b696`); amendments, harness and results uncommitted (sha256 in §1 and `run1/freeze.txt`) |
| Storage for node data | local SSD, `$W/node-vts/{data,commitlog,hints,saved_caches,cdc_raw,logs}` and `gc.log`, own `conf/`; wiped before and after each arm |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/sai_vector_term_size_fail_threshold-add-value--autonomous/` |

Full-log contents, under that directory:
- `clone-build-run40.log`, `stepE.txt`, `unit.out`, `cluster.out`;
- `shakedown/` (`unit1/`, `cluster1/`, `cluster2/`), which is not evidence;
- `unit/`: `ant.log`, `TEST.log`, `TEST.xml`, `probe.txt`, `oversize-log-lines.txt`, `commands.log`, `summary.txt`;
- `cluster/`: `summary.txt` and `commands.log`, plus per arm `armX/` (`node.out`, `system.log`, `gc.log`,
  `histo-{before,after}.txt`, `yaml-overrides.txt`, `error-warn.txt`, `client.err` (empty in all four arms)).

**Machine facts relied on** (from `environment-advisor.md` and earlier runs on this host):
- **Workspace:** every file lives under `$W`; every `ant` call takes `-Dlocal.repository=$W/m2`; commands touching `$W`, Java or the
  network ran unsandboxed.
- **Node start:** no `setsid`, so each node is a tracked background `bin/cassandra -f`, stopped with `drain` then `stopdaemon`. The
  daemon pattern is split so `pgrep -f` never matches the script. One node per arm with a fresh data directory, so no
  `disableautocompaction` issue arises; the table option `compaction = {…'enabled':'false'}` is set anyway.
- **Unit tests:** the unit yaml's read thresholds (lines 63–69) were turned off in `@Before`. Output came from
  `build/test/logs/**/TEST-<class>.log`, one line per write. `CQLTester.formatQuery` takes a single `%s`. No `executeNet`, so
  `requireNetwork()` was not needed.
- **Heap instruments:** `jstat` cannot attach. Live heap came from `jcmd GC.class_histogram` (cluster) and the same diagnostic command
  through its MBean (unit), both post-full-GC. Each arm's `gc.log` shows exactly 4 `Pause Full (Heap Inspection Initiated GC)` events and
  no other full GC (`run1/crosscheck.txt`). Baselines were taken after schema creation, with a full GC, right before the load.
  `GC.heap_info`, MAT, jmxterm and `nodetool sjk` were not used; a JMX client read the gauges.
- **Authentication:** the memtable check calls `failsOn(…, null)`, so it applies to everybody, superusers included
  (`Guardrail.java:93-96`). The client-side guard exempts superusers. So A, C and D keep `AllowAllAuthenticator`, and only E uses
  PasswordAuthenticator with a non-superuser role.
- **jvector pool:** at most `availableProcessors()+1` = 11 concurrent graph inserts, so load concurrency was 8.
- **Driver:** bundled driver, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, heartbeat off, connect retry.
- **Script hygiene:** long steps ran in the background and were polled. Shakedowns ran before run 1. Every bound came from source,
  and `selfcheck.py` was written before run 1. Byteman was not needed: a knob is varied, not a constant.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit | B2a/B3a/B4 | `/local/disk`, Linux, `ant jar` (no test classes), `bin/cassandra -p` (no `setsid` here), `pip` venv | host paths; `build-test`; tracked `bin/cassandra -f`; bundled driver (amendments B2a, B3a, B4) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B3c | Concurrency 16 exceeds jvector's 11-insert pool, which throws `IllegalStateException` | concurrency 8 (amendment B3c) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B3d | `nodetool sjk mx` exits 0 on failure here; `GC.heap_info` after `GC.run` failed a known-answer check on this host before | JMX client; heap = histogram `Total` (amendment B3d) | 2026-10-26, before the freeze | uncommitted |
| A4 | audit | B3b | Arm E needs `GRANT`, which AllowAllAuthorizer refuses | CassandraAuthorizer in E (amendment B3b) | 2026-10-26, before the freeze | uncommitted |
| A5 | shakedown | harness | The `READBACK` grep matched `internode_authenticator=` and `network_authorizer=` too | anchored to the exact key in `cluster-run.sh` | 2026-10-26, before the freeze | n/a (harness) |

Run 1: none. Both tiers ran as written at the frozen version.

## 4. Run 1

**Scope:** both tiers, every arm in §1. **Command logs:**
`sai_vector_term_size_fail_threshold-add-value--autonomous/run1/unit/commands.log`, `…/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier.** Sources: `run1/unit/summary.txt` and `probe.txt` (identical to the `PROBE` lines of the full `TEST.log`,
`run1/crosscheck.txt`).
- Ant `rc=0`, `Tests run: 6, Failures: 0, Errors: 0`, 10.4 s.
- The full log has 1,000 "too large and cannot be indexed" lines: C's 500 inserts and D's 500 first-pass inserts.
- KA: +4,104,000 B live `float[]` for 500 retained `float[2048]`, exactly 500 × 8,208.

| Arm (warn / fail) | failBytes | validateTermSize | MemtableIndexBytes | writeCount | ownsDelta | − C | floatDelta | ANN | rows | sstables |
|---|---|---|---|---|---|---|---|---|---|---|
| A (16KiB / 32KiB) | 32,768 | true | **4,404,500** | 500 | 8,752,000 | 4,404,500 | **4,218,672** | 10 | 500 | 0 |
| B (4KiB / 8KiB) | 8,192 | true | **4,404,500** | 500 | 8,752,000 | 4,404,500 | **4,218,672** | 10 | 500 | 0 |
| C (2KiB / 8191B) | 8,191 | **false** | **0** | 500 | 4,347,500 | 0 | **0** | **0** | 500 | 0 |
| D (C, two passes) | 8,191 | false | 0 | 500 | 12,848,000 | 8,500,500 | **4,216,208** | 10 | 500 | 0 |
| D0 (C, two passes, no index) | 8,191 | — | — | — | 8,443,500 | — | 0 | — | 500 | 0 |

D − D0 `ownsDelta` = **4,404,500 B**: the same as A's and B's index estimate.

**Cluster tier.** Sources: `run1/cluster/summary.txt`, `armX/histo-*-head.txt`, `armX/yaml-overrides.txt`, `armX/error-warn.txt`,
`run1/crosscheck.txt`.

Setup and validity:
- Thresholds and authenticator were read back from each node's configuration line. Heap was `-Xms4G -Xmx4G`, G1, and
  `memtable_heap_space=2048MiB`.
- Loads: A 10,000 ok; C 10,000 ok; D 10,000 + 10,000 ok; E 0 ok and 10,000 refused. `count(*)`: 10,000 / 10,000 / 10,000 / 0.
- SSTable count was 0 at every reading. The only flushes of `vt.t` were at `DRAIN`, after the readings. Their usage was 168.8 MiB (A),
  82.9 MiB (C) and 246.9 MiB (D).
- No `OutOfMemoryError`. `ERROR` lines: 0 in A, C and D; 1 in E, which is the guardrail's own no-spam line.

| Arm (warn / fail) | MemtableIndexBytes | LiveMemtableIndexWriteCount | `[F` before → after (Δ) | heap Total Δ | heap Δ vs C | ANN | "too large" lines |
|---|---|---|---|---|---|---|---|
| A (16KiB / 32KiB) | **90,010,000** | 10,000 | 240 → 84,883,432 (**+84,883,192**) | 183,664,128 | +87,917,408 | 10 | 0 |
| C (2KiB / 4KiB) | **0** | 10,000 | 240 → 240 (**0**) | 95,746,720 | 0 | **0** | **10,000** |
| D (C, two passes) | 0 | 10,000 | 240 → 84,894,408 (**+84,894,168**) | 268,205,080 | +172,458,360 | 10 | 10,000 |
| E (C, ordinary role) | 0 | 0 | 240 → 240 (0) | 1,798,848 | −93,947,872 | 0 | 0 |

`[F` instance count after the load: 20,021 in A and D, 5 in C and E. E's first error was `Error from server: code=2200 [Invalid query]
message="Guardrail sai_vector_term_size violated: Value of column 'v' has size 8192, this exceeds the failure threshold of 4096."`

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — Valid. [observed: `unit/summary.txt`]
   - All 6 tests ran. KA read exactly the retained bytes, so the instrument is exact.
   - Every arm stored 500 rows with 0 SSTables, and `failBytes` reads back the set value.
   - Arm A, the positive control, moved every observable.
2. **Readings** — Points worth noting.
   - A and B are identical (same data, same seed), which shows that the 8,192-byte term passes a fail threshold of exactly 8,192:
     the comparison is strict `>`. [observed]
   - D − D0 equals A's estimate to the byte (4,404,500). So the update path adds the same graph bytes as the insert path, and
     `MemtableIndexBytes` (0) does not count them. [observed; inferred: same per-vector graph cost]
   - D's ANN returned 10 (internal full-ring query searches the graph). It is report-only (amendment B2f). [observed]
3. **Matched row** — B2g row 1 ("C: bytes 0, ANN 0; A: bytes ≥ 4.1 MB, ANN 10") and row 5 ("D: ownsOnHeap grows ≥ 4.1 MB, ANN 10"), as
   read by amendment B2g: **Confirmed**, Effect *caps only on some paths (bypass)*. [observed]
   - Insert path holds:
     - C: `validateTermSize` false, `MemtableIndexBytes` 0, ANN 0, `floatDelta` 0 < 1,000,000.
     - A and B: true, 4,404,500 ≥ 4,096,000, ANN 10, `floatDelta` 4,218,672 ≥ 4,096,000.
   - Bypass holds: D `floatDelta` 4,216,208 ≥ 4,096,000, and D − D0 4,404,500 ≥ 4,096,000.
   - Every filed B2f value also holds: `writeCount` 500 in A–D, D `MemtableIndexBytes` 0, and D − C `ownsDelta` 8,500,500 ≥ 4,096,000.
4. **Excluded rows**
   - Row 2 (C indexed): C has 0 bytes, ANN 0 and `floatDelta` 0.
   - Row 3 (boundary `>=`): B has 4,404,500 bytes.
   - Row 4 / Invalid: A moved; there were no SSTables and no errors, and KA was in its band.
   - Row 6 (bypass refuted): D's `floatDelta` and D − D0 are both above the bound.
   - Not confirmed: there is no mixed reading.
5. **Observed vs. inferred** — The verdict rests on observed values only. Inferred and not used by the verdict: that the update path's
   bytes are the same per-vector graph cost (equal numbers suggest it).
6. **Deviations and gaps** — None in the run. The heap is the whole JVM's `float[]`. KA, C and D0 (all 0 B) show that nothing else
   produced `float[]` in the window.
7. **Core question** — The cap's quantity is the per-term graph entry. Below the term size (8191 B) no vector reaches the graph on
   insert: 0 B real heap, 0 B estimate, and direct disallow evidence (`validateTermSize` false, 1,000 log lines). At or above it,
   ≈ 8.4 KB per row enters. But overwriting a key in the same memtable puts the oversized vector into the graph regardless. So the
   threshold caps the insert path only.

**Unit tier conclusion:** B2g rows 1 and 5 — **confirmed**. Effect (amended B2g): **caps only on some paths (bypass)**.

**Cluster tier**

1. **Validity** — Valid. [observed: `cluster/summary.txt` READBACK, LOAD, COUNT, STATS, ERRORS lines; `crosscheck.txt`]
   - Thresholds and authenticator were read back in every arm. Loads were complete, and `count(*)` was 10,000 in A, C and D.
   - SSTable count was 0 at every reading. The flushes happened only at drain, after the readings.
   - Arm A, the positive control, moved; each histogram forced its own full GC (4 per arm, no other full GC).
2. **Readings** — Points worth noting.
   - D's live `[F` (+84,894,168) equals A's (+84,883,192) within 0.02 %, with the same 20,021 instances. Yet `MemtableIndexBytes` read 0
     in D against 90,010,000 in A: the counter misses the bypass entirely. [observed] At drain, D's memtable reported 246.9 MiB against
     A's 168.8 MiB and C's 82.9 MiB. So the memtable accounting does see D's graph bytes, as A3.7 says. [observed: `crosscheck.txt`]
   - Heap Total Δ in C (95.7 MB) is the base rows. A − C = 87.9 MB is the graph; D − C = 172.5 MB is the graph plus a second copy of
     the base rows (amendment B2b). [observed; inferred: attribution]
   - D's ANN returned 10 through the driver, so the coordinator's range reached the graph search here. It is report-only (amendment
     B3f). [observed]
3. **Matched row** — B3g row 1 ("C ≈ 0 on `[F` and MemtableIndexBytes, A ≥ 82 MB") and row 5 ("D grows like A"), as read by amendment
   B3g: **Confirmed**, Effect *caps only on some paths (bypass)*. [observed]
   - Insert path holds:
     - C: `[F` Δ 0 < 2,000,000, `MemtableIndexBytes` 0, ANN 0, and 10,000 log lines.
     - A: 90,010,000 ≥ 81,920,000, `[F` Δ 84,883,192 ≥ 81,920,000, ANN 10.
   - Bypass holds: D `[F` Δ 84,894,168 ≥ 81,920,000.
   - Every filed B3f row holds, including heap vs C (A +87.9 MB, D +172.5 MB, both ≥ 80 MB) and the log-line column.
   - Arm E matches its B3f row: writes refused with the filed text, `MemtableIndexBytes` 0, `[F` 0, heap below C, ANN 0, no log line.
4. **Excluded rows**
   - Row 2 (C `[F` ≥ 80 MB or ANN > 0): C's `[F` delta is 0 and its ANN 0.
   - Row 3 (A ≈ 0): A moved.
   - Row 4 (SSTable > 0): 0 everywhere.
   - Row 6 (D flat): D's `[F` delta is 84.9 MB.
   - Not confirmed: there is no mixed reading.
5. **Observed vs. inferred** — The verdict rests on observed values only. Inferred and not used by the verdict: the attribution of heap
   Total deltas to base rows versus graph.
6. **Deviations and gaps** — None in the run. The B3f heap column is read from the post-GC histogram Total, not `GC.heap_info`
   (amendment B3d).
7. **Core question** — Usage follows the constraint on the insert path. With the fail threshold below the term size, 10,000 vectors
   leave the graph empty: 0 B of live `float[]`, and the check logs each refusal. At the default, 84.9 MB of vectors are retained. But an
   overwrite in the same memtable bypasses the check and retains the same 84.9 MB, unseen by `MemtableIndexBytes`. For an ordinary user,
   the client front door refuses the write before it reaches the memtable (arm E).

**Cluster tier conclusion:** B3g rows 1 and 5 — **confirmed**. Effect (amended B3g): **caps only on some paths (bypass)**.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` was written before run 1 (sha256 in `run1/freeze.txt`, unchanged). It re-parses the unit `summary.txt` and the
cluster `summary.txt`, recomputes every filed and amended bound with its own code, and names the B2g and B3g rows. Output
`run1/selfcheck.out`: **42 checks, 42 pass, 0 fail**.
- U0–U12: 17 unit checks. Row: **Confirmed (rows 1 and 5) — caps only on some paths (bypass)**.
- C0–C9: 25 cluster checks. Row: **Confirmed (rows 1 and 5) — caps only on some paths (bypass)**.

Raw-file cross-checks outside the script (`run1/crosscheck.txt`):
- the `PROBE` lines of the full `TEST.log` are identical to `probe.txt`, and that log has 1,000 oversize lines;
- each arm's `JVM Arguments` heap line;
- the 4 full GCs per arm are all heap-inspection GCs;
- the histogram `Total` and `[F` lines re-read from the raw histograms;
- the "too large" counts in each `system.log`;
- the single ERROR line in E (the guardrail's);
- the `vt.t` flush reasons (SCHEMA_CHANGE at 0 B, DRAIN after the readings).

The first version of `crosscheck.txt` used a `[F` pattern that did not match the JDK 11 line format (`[F (java.base@…)`). It was
regenerated from the raw files with the harness's own field test (`$4=="[F"`). The histogram head excerpts were re-extracted the same
way. No raw file was edited.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U0–U5; C0–C5 per arm; `crosscheck.txt` JVM heap, full-GC and flush lines; READBACK lines in `cluster/summary.txt` |
| 2. Readings | yes | `unit/probe.txt` re-read: A = B to the byte; D − D0 = 4,404,500. Cluster histogram heads re-read: `[F` 20,021 instances in A and D; drain usages in `crosscheck.txt` |
| 3. Matched row | yes | U6–U12; C6–C9; both rows named by the script |
| 4. Excluded rows | yes | No reading falls in rows 2, 3, 4 or 6 of either table; no mixed reading |
| 5. Observed vs. inferred | yes | The two inferred statements (same per-vector cost; heap attribution) are not used by the verdict |
| 6. Deviations and gaps | yes | Defects A1–A5 were fixed before the freeze; the crosscheck regeneration touched derived files only; no prediction was changed after a reading |
| 7. Core question | yes | Insert-path usage follows the knob (0 vs ≈ 8.4 KB per row) with direct disallow evidence, and the overwrite path is measured to bypass it in both tiers |

### 5.2 Run 2?

**No** — 2026-10-26.
- Every verdict statement is observed, and the self-check settles every part from run 1's files.
- The result confirms a bypass, which the README lists as a reason to consider run 2. But the bypass is the file's own filed claim
  (B1's secondary claim). It is shown in both tiers by a real-heap instrument with a known-answer check, and by a no-index control
  (unit) that matches the insert-path estimate to the byte. A second run would repeat deterministic arithmetic.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive (with the caveat that the update path skips the check).

**Claim tested (B1):** for an SAI-indexed `vector<float, 2048>` column (8,192-byte terms) written by a superuser or internal path,
`sai_vector_term_size_fail_threshold` below 8,192 B keeps the memtable vector index heap at about zero, while at the default 32 KiB
the same workload grows it by at least 8,192 B per row. Secondary claim: overwriting the same keys within one memtable bypasses the
cap, and the graph grows anyway.

"Confirmed" below means this claim, both parts, held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g rows 1 and 5) | **caps only on some paths (bypass)** | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g rows 1 and 5) | **caps only on some paths (bypass)** | run 1 + self-check | 2026-10-26 |

1. **Insert path (cap holds).** Below the term size, no vector enters the graph: 0 B live `float[]`, `MemtableIndexBytes` 0, ANN 0,
   with the check's refusal logged per key. At 32 KiB, and at exactly 8 KiB (strict `>`), each row adds about 8.4 KB of graph
   (unit 4,218,672 B per 500 rows; cluster 84.9 MB per 10,000).
2. **Update path (bypass).** Overwriting a key whose row is in the current memtable puts the oversized vector into the graph anyway.
   It retains the same bytes as the uncapped insert (unit +4,216,208 B, D − D0 = 4,404,500 B; cluster +84,894,168 B), and
   `MemtableIndexBytes` reports 0 for it. Memtable ownership does count it (cluster drain usage 246.9 MiB vs 168.8 MiB in A).
3. **Front door.** For an ordinary (non-superuser) role, the client guard refuses the write outright (arm E), so neither the row nor
   the vector is stored. On a default node with `AllowAllAuthenticator`, every client is a superuser, and the memtable check is the
   only enforcement.

**Positive control:** not required, since this is not a negative-estimate file. Arm A in both tiers (and B, D in the unit tier) shows
that the instruments see the graph.

**Feedback filed:**
- The case file's section D is updated (uncommitted).
- Amendments B2a–B2h, B3a–B3g and B4 are in the case file (uncommitted).
- `_INDEX-advisor.md`: §2 row `c1b87bd8…f1c0` added, and the §1 Stage 4 column filled.
- `HANDOFF.md` not edited (`HANDOFF-ADVISOR.md` §8).
