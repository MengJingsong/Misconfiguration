# hints_PAGE_SIZE-computeNext-position--autonomous — stage-4 results  <!-- file: results/hints_PAGE_SIZE-computeNext-position--autonomous.md -->

> **Case:** [`hints_PAGE_SIZE-computeNext-position--autonomous`](../../stage3-ai-deep-read/cases/hints_PAGE_SIZE-computeNext-position--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26.
>
> **Outcome class:** undetermined — the stage-3 estimate (`undetermined`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/hints_PAGE_SIZE-computeNext-position--autonomous/`](../harness/hints_PAGE_SIZE-computeNext-position--autonomous/).
>
> **Unit: Not confirmed — undetermined** (amended B2g row "a non-last page with c ≠ ⌈524,288 / e⌉ but P < 524,288 + e").
> - 11 of the 12 reads hold every B2f prediction. For entries of e = 1,089 / 16,450 / 614,466 B, every non-last page held c = 482 / 32 / 1 hints and
>   P = 524,898 / 526,400 / 614,466 B. That is within one entry above 512 KiB, the same for both iterators, and the same for plain and LZ4 files.
>   The LZ4 files were 61×, 197× and 243× smaller than the plain ones.
> - The exception is the LZ4 file of 600 KiB entries, read with either iterator: 28 pages, not 14. Pages with c = 0 and P = 0 alternate with
>   pages of c = 1 and P = e. Each empty page comes with an `Unexpected EOF replaying hints … continuing` warning.
> - No page in any read went past 524,288 + e bytes.
>
> **Cluster: Confirmed — caps** (B3g row 1). Two nodes on loopback. Node 1 sends a backlog of N = 16,384 / 4,096 / 256 hints of v = 16 KiB /
> 64 KiB / 1 MiB to node 2, which holds each hint for 300 ms.
> - Every page was `CONTINUE`. Each non-last page carried k = 32 / 8 / 1 hints, which equals ⌈524,288 / (bytes/sent + 12)⌉.
> - Node 2's live `Hint` count over the delivery window had a maximum and median of 32 / 8 / 1, against 0 in the paused baseline.
> - Node 2's live `[B` rose by at most 1.23 / 1.39 / 1.18 MB over its baseline.
> - The whole backlog was delivered: HintsSucceeded rose by exactly N.
>
> No run 2.
>
> **Agent:** autonomous. In this file, "§9a" means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster). "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).
> An earlier stage-3 session wrote the case file; this session did not.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed at commit `f35af30` with sha256 `dba775c7…e10b` (index §2, "as filed (hints batch)"). Frozen after the step-0 audit's twelve amendments (2026-10-26, before any run-1 reading) at sha256 **`86862af88ac0963c47271d0b3d3e1e7778ba3422299969ac192eceaed0b85a09`**. Both tiers' readings were taken at this version. A new row was added to `_INDEX-advisor.md` §2. `run1/freeze.txt` holds this hash, the harness hashes and the self-check hash. Nothing was committed, because no commit was asked for. |
| **Harness** | [`../harness/hints_PAGE_SIZE-computeNext-position--autonomous/`](../harness/hints_PAGE_SIZE-computeNext-position--autonomous/) (Notes 1–3 below the table) |
| **Tiers and values** | **Unit (B2):** one `ant testsome` JVM, default test JVM options. Entry value v ∈ {1 KiB, 16 KiB, 600 KiB} × format ∈ {plain, LZ4} × iterator ∈ {buffers, hints}: 12 reads of 8 MiB files (N = 8,192 / 512 / 14 hints). **Cluster (B3):** two nodes from one clone, heap 2G each. Stress value v ∈ {16 KiB, 64 KiB, 1 MiB}, with N = 16,384 / 4,096 / 256 hints for node 2 (≈ 256 MiB each). PAGE_SIZE is a constant and is not varied (B2b, B3b). The entry size varies k = ⌈512 KiB / e⌉ instead. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

**Note 1, harness files:**
- `HintsPageCapTest.java` (B2c–B2e as amended) and `unit-run.sh`.
- `hp1.btm`: the two filed rules unchanged, plus three observe-only rules. `file start` and `file end` mark each `HintsDispatcher.dispatch()`;
  `count sent decoded` watches the decode path. `hp2.btm` is the filed hold rule, unchanged.
- `HpJmx.java`: one JMX read of node 1's TotalHints, HintsSucceeded, HintsFailed and HintsTimedOut. It replaces `nodetool sjk mx`.
- `cluster-run.sh`: three arms, with node 2's class-histogram sampler built in. `summarize.py` builds the readings tables.

**Note 2, instrument checks before the freeze:**
- **Byteman:** `TestScript` type-checks all six rules with no errors (`shakedown/testscript-hp-btm.txt`). The cluster script repeats the check
  before any start (`run1/cluster/btm-check.txt`).
- **Unit shakedown:** v = 16 KiB only (`shakedown/unit-16KiB-readings.txt`). It showed the line format, a constant e = 16,450, and an LZ4 file
  190× smaller. It is not evidence.
- **Cluster shakedown 1:** arm 64k with N = 512 (`shakedown/cluster1-64k-N512-stop-condition-defect.txt`). Two problems appeared.
  - `listpendinghints` printed "no pending hints" while a 33.6 MB hints file existed, and again 12 s after resume, while that file was still being
    dispatched. Only 352 of 512 hints were delivered by the end of the arm. Source: `listpendinghints` lists only the files queued in
    `dispatchDequeue`. The open writer and the file being dispatched are not listed (`HintsStore.java:108-125`). Defect S1; amendments B3d and B3e.
  - The sampler's error filter matched class names containing `Exception`. It also listed the histogram header. Harness defect H1.
  - The JMX client failed on the HintsService meters before the first dispatch. Those meters are registered lazily, so a missing bean now reads
    as 0 (H1).
- **Cluster shakedown 2:** the same arm, after the fixes (`shakedown/cluster2-64k-N512-*`). Every step ran: 64 pages of 8, 512 hints
  delivered, `Hint` maximum 8, baseline 0. It is not evidence.

**Note 3, self-check:** [`run1/selfcheck.py`](hints_PAGE_SIZE-computeNext-position--autonomous/run1/selfcheck.py) was written before run 1.
- Its parsers were tested on the shakedowns (`SHAKEDOWN=1`): 37 of 37 checks passed on the shakedown files.
- It does not use `summarize.py`, `hpcap.txt` or `readings.txt`.
- It re-reads `unit/ant.log` and `unit/TEST.log`. For the cluster tier it re-reads each arm's raw `node1.out`, sliced by the byte offsets in the
  `MARK` lines. It also reads `hist.txt`, `stress.log`, both nodes' `system.log` (the `Node configuration` line), and the JMX client's `RESULT`
  lines.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the hint bytes one dispatcher has outstanding per page, and the heap their hints occupy on the receiver |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | PAGE_SIZE is a `private static final int` (A1). The design varies the entry size so k = 32 / 8 / 1 (cluster) and 482 / 32 / 1 (unit). It reads whether usage follows k (B2b, B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Node 2's live `Hint` count and `[B` bytes come from a class histogram after a full GC (B3d). As filed, node 2's `heap_buffers` memtable copies every delivered value into on-heap regions (`SlabAllocator.java:89-139`), so `[B` would grow by the whole backlog whatever the page did. Amendment B3a sets node 2 to `offheap_buffers`. Unit tier: no heap reading, as filed (B2d); the held list is the payload. |
| A. Core question | usage driven to the limit and past it | Met | Unit: an 8 MiB file is ≈ 16 pages. Cluster: ≈ 512 pages per arm. Each 300 ms hold makes a page's hints coexist on node 2 (B3a). |
| B. Logic | each step says what it establishes | Met | B2h/B3h |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Numbers as filed (B2f, B3f). Three terms had no definition: the `[B` "pre-delivery baseline", "the last page of each file", and the "median" window. They are defined in amendments B3c and B3d, which add a paused baseline window, file markers and the delivery window. No predicted number was changed. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Verdict words, an Effect rule, Invalid rows, "limit not reached on node 2", "`[B` only fails" and the arm combination were added (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Disallow evidence: each page ends at the `:186`/`:292` test, seen as c (unit) and `sent` (node 1) at ⌈512 KiB / e⌉ with N ≫ k. The ceiling follows k at three sizes. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Added a paused baseline (`Hint` = 0), TotalHints and HintsSucceeded = N, and no page lines before resume (amendment B3h). Unit: the filed random values make the LZ4 arm unable to tell on-disk counting from uncompressed counting, since random bytes do not compress. Amendment B2c uses compressible values. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1 |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Schema, line formats, scripts and log paths were added (amendments B2c–B2e, B3d, B3e) |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | `no-warmup` was added: stress's warm-up adds n/4 writes (`StressAction.java:70`). Also added: the pause/resume windows and the sampler definition. The stop condition was replaced after shakedown 1 (S1). |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | The filed design assumes Linux, two copies of the clone, `~/hp-*` paths and `SchemaLoader.standardCFMD` for an `int`/`blob` table. `standardCFMD` builds a clustered ascii table instead. All fixed before the freeze (amendments B2a, B2c, B3a, B4). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≈ 270 MB of hints and ≈ 256 MB of data per node per arm, against 132 GiB free. A 2G heap per node on 32 GiB. Delivery ≈ 512 × 0.32 s ≈ 165 s per arm. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `~/cassandra-src` at `cassandra-5.0.9`: see Note 4 below the recommendations. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone `$W/cassandra-run37`, `build-test`, harness test file and script | Amendment 2026-10-26 | No Linux node; clean clone |
| 2 | B2c: schema by `CreateTableStatement.parse`; compressible values `(byte)(j % 13)`; e and file size printed | Amendment 2026-10-26 | Group D (the schema helper), group A/B (the LZ4 arm must discriminate) |
| 3 | B2d: line formats with an iterator field | Amendment 2026-10-26 | Group C |
| 4 | B2e: `unit-run.sh`, six `@Test` | Amendment 2026-10-26 | Group C |
| 5 | B2g: verdict words, added rows, Effect rule | Amendment 2026-10-26 | Group B |
| 6 | B3a: one clone with per-node conf, JMX 7299, `auto_bootstrap: false`, node 2 `offheap_buffers`, three observe-only rules | Amendment 2026-10-26 | Group D; group A (the `[B` instrument) |
| 7 | B3c: `no-warmup`; `pausehandoff`, schema agreement and a baseline window before `resumehandoff` | Amendment 2026-10-26 | Group C; group B (baseline); a hint that arrives before node 2 knows the table is dropped without a `Hint` instance (`HintVerbHandler.java:61-69`) |
| 8 | B3d: sampler format, windows, k and "last page" definitions, JMX counters | Amendment 2026-10-26 | Group C; `sjk` exits 0 on failure |
| 9 | B3e: one script; stop condition = `listpendinghints` empty **and** no `.hints` file (after shakedown 1) | Amendment 2026-10-26 | Defect S1 |
| 10 | B3g: rows read against B3f, arm combination | Amendment 2026-10-26 | Group B |
| 11 | B3h, B4: controls; host paths | Amendment 2026-10-26 | Group B; paths |
| 12 | A3 cites `HintsReader.java:232-233, 340-341` for the rate limiter. The raw path's `acquire` is at `:338-339`. B3b says a page of ≤ 64 hints finishes "in one 300 ms wave", but the shakedown measured ≈ 0.5 s per page and run 1 ≈ 0.32 s. B3c's "≈ 512 pages" comes to 513 pages over 3 files in the 16k and 64k arms. | Left for stage 3 | Not needed for B1's claim |

**Note 4, citations checked:**
- `HintsReader.java:55-56, 75-100, 125-161, 170-205, 276-330`;
- `HintsDispatcher.java:97-106, 120-172, 180-215`; `HintsDispatchExecutor.java:97-111, 202-323`; `HintsDispatchTrigger.java:51-70`;
- `HintsStore.java:108-125, 242, 290, 322-327`; `HintsWriter.java:157-161, 200-287`; `CompressedHintsWriter.java:48-69`;
- `ChecksummedDataInput.java:86-105`; `CompressedChecksummedDataInput.java:50-81, 108-150`;
- `Hint.java:200-243`; `HintVerbHandler.java:51-110`; `HintsService.java:168-172, 294-312`; `HintsServiceMetrics.java:39-43`;
- `Verb.java:118`; `SlabAllocator.java:52, 66-139`; `StressAction.java:70`; `SettingsCommand.java:124`;
- `conf/cassandra.yaml:80, 88, 93, 102, 106, 723, 825, 1330`;
- `test/unit/.../HintsReaderTest.java:66-101`, `HintsCompressionTest.java:35-43`.

All hold. The filed A3 citations hold, apart from the line drift in recommendation 12.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 16:42:32–16:42:55 EDT; cluster 16:44:33–17:00:44 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro) |
| Hardware | 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 132 GiB free |
| Network and processes | Loopback 127.0.0.1–.3 present. Ports 7000/7001/7199/7299/9042/9091 were free and no Cassandra daemon ran before the run; none after. |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: the `ant testsome` forked JVM with default options. Nodes: `-Xms2G -Xmx2G`, plus the Byteman 4.0.20 agent (`script:` only, no listener) on both nodes (the `JVMARGS` lines in `run1/cluster/summary.txt`). |
| Ant | 1.10.18 |
| Python | 3.8.11 (harness scripts only; the load is cassandra-stress from the clone) |
| Local `cassandra-src` clone | `$W/cassandra-run37` = `~/Library/Caches/stage4/cassandra-run37`, a fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`. `ant -Dlocal.repository=$W/m2 build-test`: `BUILD SUCCESSFUL` in 1 min 1 s. `git status` clean after both tiers. |
| Case-file commit / harness commit | Filed at `f35af30` (sha256 `dba775c7…e10b`). Amendments, harness and results are uncommitted (sha256 values in §1 and `run1/freeze.txt`). |
| Storage for node data | local SSD under `$W/node-hp1` and `$W/node-hp2` (`conf`, `data`, `commitlog`, `hints`, `saved_caches`, `cdc_raw`, `logs`), wiped after each arm and at the end |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/hints_PAGE_SIZE-computeNext-position--autonomous/` |

Full-log contents, under that directory:
- `clone-build-run37.log`, `stepE.txt`, `testscript.txt`, `unit-run.out`, `cluster-run.out`;
- `shakedown-unit/`, `shakedown-cluster-attempt1/` and `shakedown-cluster/`, which are not evidence;
- `unit/`: `ant.log`, `TEST.log`, `TEST.xml`, `hpcap.txt`, `commands.log`, `summary.txt`, `readings.txt`;
- `cluster/`: `commands.log`, `summary.txt`, `readings.txt`, `btm-check.txt`;
- `cluster/arm-{16k,64k,1m}/`:
  - `node1.out` (the Byteman lines), `node2.out` and `node2-first.out`;
  - `node1-system.log`, `node2-system.log` and `node2-first-system.log`;
  - `hist.txt`, `stress.log` and `hpcap.txt`;
  - the yaml overrides, status files, `describecluster.txt` and the hints-directory listings.

**Machine facts relied on** (from `environment-advisor.md` and earlier runs on this host):
- **Workspace:** every file lives under `$W`. Every `ant` call takes `-Dlocal.repository=$W/m2`. Commands touching `$W`, Java or the network ran
  unsandboxed.
- **Node start:** there is no `setsid`, so each node is a tracked background `bin/cassandra -f`. `JVM_EXTRA_OPTS` (the agent) is scoped to that
  command only.
- **Streaming:** zero-copy bootstrap streaming fails on this host, so both nodes run with `auto_bootstrap: false`.
- **Instruments:** `jstat` cannot attach, so node 2's heap is read by `jcmd GC.class_histogram` (live totals, after a forced full GC).
  `nodetool sjk mx` exits 0 on failure, so the counters come from a JMX client. BSD tools: `stat -f %z` and `sed -i ''`.
- **Authentication:** no guardrail is on this path (dispatch → `HINT_REQ` → `HintVerbHandler`), so the default `AllowAllAuthenticator` was kept.
- **Unit tests:** test stdout lands in `build/test/logs/**/TEST-<class>.log`. The unit yaml's read thresholds do not matter here: nothing is
  read through CQL.
- **Constants and Byteman:** the constant PAGE_SIZE is not patched. The design varies entry size instead. The Byteman rules only count and
  observe, except node 2's filed 300 ms hold. `TestScript` type-checked them.
- **Script hygiene:**
  - The daemon pattern in the scripts is split. Long steps ran in the background and were polled with sleeps under 2 minutes.
  - Shakedowns ran before run 1. Bounds came from source.
  - Baselines were taken after ingest, with handoff paused. `selfcheck.py` was written before run 1.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit | B2a/B3a/B4 | Linux, `~/hp-*` paths, two copies of the clone, `--depth 1` clone from origin | Host clone; one clone with per-node conf; host paths (amendments B2a, B3a, B4) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B2c | `SchemaLoader.standardCFMD` does not build `t (k int PRIMARY KEY, v blob)` | `CreateTableStatement.parse` (amendment B2c) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B2c | Random values do not compress, so the LZ4 arm cannot tell row 3 from row 1 | Compressible values (amendment B2c) | 2026-10-26, before the freeze | uncommitted |
| A4 | audit | B3a/B3f | With `heap_buffers`, node 2's memtable holds every delivered value in `[B`, so the filed `[B` bound cannot hold from source | Node 2 `offheap_buffers` (amendment B3a); B3f unchanged | 2026-10-26, before the freeze | uncommitted |
| A5 | audit | B3c | Stress warm-up adds n/4 hints; no pre-delivery window; a hint delivered before schema agreement is dropped without a `Hint` instance | `no-warmup`; `pausehandoff` / `resumehandoff` around a baseline window (amendment B3c) | 2026-10-26, before the freeze | uncommitted |
| S1 | shakedown | B3d(3)/B3e step 4 | `listpendinghints` omits the open writer and the file being dispatched (`HintsStore.java:108-125`), so "empty" fired with 160 of 512 hints undelivered | Stop when `listpendinghints` is empty **and** no `.hints` file is left; JMX counters for the backlog (amendments B3d, B3e) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| H1 | shakedown | harness | The sampler's error filter matched class names and the histogram header. The JMX client failed on the not-yet-registered HintsService meters. | Filter on non-histogram lines only; a missing bean reads 0 | 2026-10-26, before the freeze | none (harness only; `run1/freeze.txt`) |

Run 1: no defect. Both tiers ran as written at the frozen version.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:**
`hints_PAGE_SIZE-computeNext-position--autonomous/run1/unit/commands.log` and `…/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier.** Sources: `run1/unit/test-log-hpcap-lines.txt`, `ant-tests-run.txt`, `readings.txt`, `test-log-eof-warning-first.txt`.
- Ant: `Tests run: 6, Failures: 0, Errors: 0`.
- e was constant in every file (`emin` = `emax`).

| v | e (B) | ⌈524,288/e⌉ | plain / LZ4 file bytes (ratio) | format, iterator | pages (⌈N/c⌉) | c on non-last pages | P on non-last pages | last page c, P | sum = P − 12c |
|---|---|---|---|---|---|---|---|---|---|
| 1,024 | 1,089 | 482 | 8,921,130 / 146,349 (61×) | plain and LZ4, both iterators | 17 (17) | 482 | 524,898 | 480, 522,720 | yes |
| 16,384 | 16,450 | 32 | 8,422,442 / 42,667 (197×) | plain and LZ4, both iterators | 16 (16) | 32 | 526,400 | 32, 526,400 | yes |
| 614,400 | 614,466 | 1 | 8,602,566 / 35,352 (243×) | plain, both iterators | 14 (14) | 1 | 614,466 | 1, 614,466 | yes |
| 614,400 | 614,466 | 1 | (as above) | **LZ4, both iterators** | **28** (14) | **0 and 1, alternating** (pages 0, 2, 4, … have c = 0) | **0** (c = 0 pages) and 614,466 | 1, 614,466 | yes |

- `TEST.log` has 28 `Unexpected EOF replaying hints (…-2.hints), likely due to unflushed hint file on shutdown; continuing` warnings. The
  stack goes through `RebufferingInputStream.readInt` ← `HintsReader$BuffersIterator.computeNextInternal(HintsReader.java:319)` ←
  `HintsPageCapTest.run(…:140)` in `v600KiBLz4`. That is 14 per iterator, one for each empty page.
- Largest P in any read: 614,466 = e (v = 600 KiB). For e < 524,288, the largest non-last P is 526,400 < 524,288 + e.

**Cluster tier.** Sources: `run1/cluster/summary.txt`, `readings.txt`, and `arm-*/hpcap.txt`, `node1-hpcap-with-offsets.txt`, `hist.txt`,
`stress-results.txt`, `node*-config-readback.txt`.

Setup and validity, for every arm:
- Read-backs (`Node configuration`):
  - Node 1: `hinted_handoff_throttle=0KiB`, `max_hints_delivery_threads=1`, `concurrent_writes=64`, `write_request_timeout=5000ms`,
    `max_hint_window=3h`, `auto_bootstrap=false`, `memtable_allocation_type=heap_buffers`.
  - Node 2: `memtable_allocation_type=offheap_buffers`, `concurrent_writes=64`.
- Status UN/UN at the start, and `DN 127.0.0.2` on node 1 during stress. Schema agreement (one version) before resume.
- Stress: N partitions and 0 errors in every arm.
- Node 1, before pause: TotalHints = N, and 3 / 3 / 2 `.hints` files of 269.6 / 268.7 / 268.5 MB.
- No page line before the resume offset. No `decoded` line. No agent error, no ERROR line and no `OutOfMemoryError` on either node. Both nodes
  were alive to the end.

| Arm (v, N) | files / pages | non-last `sent` (formula) | last page of each file (sent) | max `bytes` (bound v + 524,388) | `action` | node-2 `Hint` in delivery: samples, max, median (counts) | baseline `Hint` (samples) | `[B` baseline median → delivery max (Δ; bound k·v + 8 MiB) | HintsSucceeded Δ / Failed / TimedOut | delivery time |
|---|---|---|---|---|---|---|---|---|---|---|
| 16k (16,384 B, 16,384) | 3 / 513 | **32** (32) | 28, 28, 8 | 526,240 (540,772) | all CONTINUE | 76, **32**, 32 (0 ×2, 32 ×74) | 0 (9) | 10,826,064 → 12,058,136 (**1,232,072**; 8,912,896) | 16,384 / 0 / 0 | 164 s |
| 64k (65,536 B, 4,096) | 3 / 513 | **8** (8) | 6, 6, 4 | 524,776 (589,924) | all CONTINUE | 76, **8**, 8 (0 ×3, 2 ×1, 5 ×1, 8 ×71) | 0 (9) | 10,817,544 → 12,203,144 (**1,385,600**; 8,912,896) | 4,096 / 0 / 0 | 164 s |
| 1m (1,048,576 B, 256) | 2 / 256 | **1** (1) | 1, 1 | 1,048,637 (1,572,964) | all CONTINUE | 39, **1**, 1 (0 ×4, 1 ×35) | 0 (9) | 10,818,320 → 11,998,328 (**1,180,008**; 9,437,184) | 256 / 0 / 0 | 86 s |

- Hint bytes per page: 16,445 B (16k), 65,597 B (64k) and 1,048,637 B (1m). With the 12-byte framing, e = 16,457 / 65,609 / 1,048,649.
- After each arm, `listpendinghints` showed none and node 1's hints directory held no `.hints` file.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — Valid. [observed: `unit/ant-tests-run.txt`, `test-log-hpcap-lines.txt`]
   - All six tests passed, and every read returned `read=N`.
   - Every (v, format, iterator) printed its lines. e was constant.
   - Each file spans ≥ 14 pages, so the limit was reached over and over.
2. **Readings** — 11 of 12 reads are exact. The LZ4 600 KiB file, read with either iterator, gives an empty page (c = 0, P = 0) before each
   real page, with an `Unexpected EOF` warning. [observed]
   - Mechanism [inferred from source]: `Session.append(ByteBuffer)` (`HintsWriter.java:205-210`) flushes the aggregation buffer, without checking
     that it holds data, when an entry larger than the buffer's free space arrives. The test's `append(Hint)` hands every 600 KiB entry to it
     (`:240-262`), with a 256 KiB session buffer.
   - The plain writer writes 0 bytes. `CompressedHintsWriter.writeBuffer` (`:48-69`) writes a chunk with uncompressed size 0.
   - When reading, `readInt` reaches that empty chunk and gets an `EOFException`. The iterator logs `Unexpected EOF … continuing` (`HintsReader.java:195`
     / `:301`) and ends the page with no hint. The next page starts after the empty chunk.
   - The production writer uses the same `append(ByteBuffer)` with a 256 KiB buffer (`HintsWriteExecutor.java:50, 241-245`). So a node with
     `hints_compression` set would likely do the same for hints over 256 KiB. This was not run on a node; the cluster arms use plain hints files.
3. **Matched row** — amended B2g: "a non-last page with c ≠ ⌈524,288 / e⌉ but P < 524,288 + e" → **Not confirmed**, Effect **undetermined**.
   [observed]
   - The LZ4 600 KiB reads have 14 non-last pages with c = 0 ≠ 1 and P = 0.
   - In the same reads, B2f's "number of pages = ⌈N / c⌉" (28 ≠ 14) and "same c and P for the LZ4 file" fail.
4. **Excluded rows**
   - Row 1: fails on the LZ4 600 KiB reads (above).
   - Row 2: no page holds all N, and no P reaches 524,288 + e. The largest is P = e for v = 600 KiB.
   - Row 3, by its filed meaning ("c differing from plain by the compression ratio … the cap counts on-disk bytes"): excluded.
     - At 1 KiB and 16 KiB the LZ4 files are 61× and 197× smaller, yet c and P equal the plain ones exactly.
     - Every non-empty LZ4 600 KiB page has c = 1 and P = e, as in the plain file.
     - The amendment's parenthetical restates row 3 as "c or P differs from the plain file's". The 600 KiB reads do differ, so read literally the
       row matches. But its label ("Refuted for compressed files … caps only on some paths") states that the cap fails for compressed files. No
       compressed page exceeds 524,288 + e, and no c exceeds the formula. The specific row in item 3 describes the reading exactly, so it is the
       match. (See §5.1 part 3.)
   - Row 4: every read has ≥ 14 pages.
   - Invalid: none of its conditions holds.
5. **Observed vs. inferred** — The empty-chunk mechanism is inferred from source. The verdict rests only on the observed c and P values.
6. **Deviations and gaps** — None in the run. Heap is not measured in this tier (B2d, as filed).
7. **Core question** — As far as this tier can show, usage follows the constraint.
   - A page holds ⌈512 KiB / e⌉ entries, so c moves inversely with e: 482 → 32 → 1. Its bytes stay below 512 KiB + e, counted in uncompressed
     bytes for both formats.
   - The tier cannot reach Confirmed because claim (1) says *each* page holds k hints. On the LZ4 file of 600 KiB entries, half the pages hold
     none.

**Unit tier conclusion:** amended B2g row "c ≠ ⌈524,288/e⌉ with P < 524,288 + e" — **not confirmed**. Effect: **undetermined**. On every page
of every read the bytes stayed below 512 KiB + e.

**Cluster tier**

1. **Validity** — Valid in all three arms. [observed: `cluster/summary.txt`; self-check C0, C1, C5, C6, C10]
   - The read-backs show each arm's settings. Node 2 was DN during stress, and the schema agreed before resume.
   - The agents loaded with no error. Stress had 0 errors and wrote N partitions.
   - TotalHints = N, and HintsSucceeded rose by N with 0 failed and 0 timed out.
   - No page line appeared before resume, and no hints file was left.
2. **Readings** — Points worth noting:
   - Each arm's backlog was 3 or 2 files of 128 MiB or less, so 3 or 2 short last pages.
   - Of the delivery samples, 74 of 76, 71 of 76 and 35 of 39 read exactly k. [observed: `arm-*/hist.txt`] The few at 0 or below k are taken
     to fall between pages: at the start or end of delivery, at a file boundary, or as a page drains. [inferred; not timed against node 1's lines]
   - The `[B` rise over baseline is 1.18–1.39 MB in every arm, roughly the held hints' values (k × v = 0.5 / 0.5 / 1 MiB) plus about 0.2–0.9 MB.
     [observed values; the split is inferred]
3. **Matched row** — B3g row 1: every condition holds in all three arms. [observed: `readings.txt`, `hpcap.txt`, `hist.txt`]
   - Every page is `CONTINUE`.
   - Non-last `sent` = 32 / 8 / 1 = ⌈524,288 / (bytes/sent + 12)⌉, and no page has sent > k.
   - Bytes per page are below 524,288 + v + 100.
   - The node-2 maximum is 32 / 8 / 1. It is ≤ min(k + 2, ⌊1.1k⌋) = 34 / 8 / 1 and ≥ ⌈k/2⌉. The medians are 32 / 8 / 1, all > 0.
   - The `[B` deltas are below k·v + 8 MiB. The maxima are ordered 32 > 8 > 1.
4. **Excluded rows**
   - Row 2: the maximum is never above k.
   - Row 3: no `sent` is above the formula.
   - Row 4: no `ABORT`.
   - Row 5: the counts are non-zero.
   - "Limit not reached": maximum = k.
   - "`[B` only": every Δ is within its bound.
   - "Other prediction fails": none fails.
   - Invalid: every validity condition holds.
5. **Observed vs. inferred**
   - Inferred: that the live `Hint` instances on node 2 are the hints of the current page. Each is held in `HintVerbHandler.doVerb` or queued for
     the MUTATION stage. The paused baseline reads 0, and the count equals node 1's `sent` per page.
   - Inferred: that the `[B` rise is mostly the held hints' values. The verdict uses only the bound.
6. **Deviations and gaps**
   - None in the run.
   - The outbound bytes on node 1 are not observable, as the filed design says. Node 1's `bytes` per page bounds what one dispatcher hands to
     messaging.
   - The amended setup changes two things: node 2's memtable allocation type (off-heap values) and the pause around a baseline window. Neither
     changes the dispatch path.
7. **Core question** — On a real two-node cluster, the page caps what one dispatcher has outstanding.
   - About 512 KiB of hints go out (32, 8 or 1 hints by size). The dispatcher then waits.
   - The receiver holds exactly that many hints at once, never the backlog of 16,384, 4,096 or 256. Its heap rises by about 1.2–1.4 MB, not by
     256 MiB.
   - Usage follows the page: 32 : 8 : 1 as e goes 16 → 64 → 1,024 KiB.

**Cluster tier conclusion:** B3g row 1 — **confirmed**. Effect: **caps**.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1; sha256 in `run1/freeze.txt`) re-reads the raw files with its own parsers:
- `unit/ant.log` and the `HPCAP` lines of `unit/TEST.log`;
- `cluster/summary.txt` (the RUN, ARM, MARK, STATUS, SCHEMA, PENDING, JMXCOUNT and ARM-END lines);
- each arm's raw `node1.out`, sliced by the `resume` and `tail-end` byte offsets;
- each arm's raw `hist.txt` (its own windows and medians), `stress.log`, and both nodes' `system.log`.

Output `run1/selfcheck.out`: **105 checks, 98 pass, 7 fail**.
- All 7 failures are the LZ4 600 KiB unit cells: U3, U4 and U5 for each iterator, and U7. The script prints `UNIT-ROW NOT row 1`.
- It prints `CLUSTER-ROW Confirmed (B3g row 1)`. All 35 cluster checks pass (C00, C0–C10 per arm, C11); the 70 unit checks include the 7 failures.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U0–U2, C0, C1, C5, C6 and C10 pass. `summary.txt` re-read: DN lines, `agree=1`, `done=1`, `daemons_left=0` after each arm, 0 ERROR and OOM 0. |
| 2. Readings | yes | `test-log-hpcap-lines.txt` re-read: `v=614400 fmt=lz4` pages alternate `c=0 P=0` / `c=1 P=614466` for both iterators; 28 EOF warnings in `TEST.log`. `hist.txt` re-read for the count distributions in §4.1. |
| 3. Matched row | yes, with a note | Unit: two rows of amended B2g are literally triggered, "c ≠ formula with P < 524,288 + e" and row 3's parenthetical "c or P differs". Row 3's filed text and label are about the cap counting on-disk bytes or failing for compressed files. The readings exclude that (identical c at 61× and 197× compression; no compressed page above the bound). The specific row was chosen; choosing row 3 would claim a Refuted the readings contradict. Recorded so a reviewer can overrule. Cluster: C2–C9 and C11 pass. |
| 4. Excluded rows | yes | No P ≥ 524,288 + e in any read; no `sent` above the formula; no ABORT; maxima = k |
| 5. Observed vs. inferred | yes | The empty-chunk mechanism and the composition of `[B` are inferred. Neither decides a row. |
| 6. Deviations and gaps | yes | A1–A5 and S1 were fixed before the freeze; H1 touched only the harness. The open questions are named: production `hints_compression` with large hints, and outbound bytes on node 1. |
| 7. Core question | yes | Cluster: the receiver's live hints follow k at 3 sizes, and the disallow branch is seen directly (pages end at k with N ≫ k). Unit: the per-page bound holds everywhere, but claim (1) as worded fails on one cell, so the tier stays Not confirmed. |

### 5.2 Run 2?

**No** — 2026-10-26.
- The cluster verdict rests on exact observed counts (`sent` per page, live `Hint` maxima equal to k, HintsSucceeded = N).
- The unit Not-confirmed rests on an exact, repeatable reading: the same alternation with both iterators, from a deterministic file.
- Neither result refutes the case or confirms a bypass, and the self-check settles every part from run 1's files.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** undetermined.

**Claim tested (B1):**
- (1) Each dispatch page contains k = ⌈524,288 / e⌉ hints of entry size e (k = 1 when e ≥ 524,288). The hint bytes one dispatcher has
  outstanding are therefore < 512 KiB + e, whatever the file size.
- (2) On a real two-node cluster, the hints held at once on the receiving node from one dispatcher, and so the heap they occupy, number at most
  k, not the whole backlog N.

"Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed** (amended B2g row "c ≠ ⌈524,288/e⌉ with P < 524,288 + e") | **undetermined** | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g row 1) | **caps** | run 1 + self-check | 2026-10-26 |

1. **Unit:**
   - In 11 of 12 reads a page holds exactly ⌈512 KiB / e⌉ entries (482 / 32 / 1), with P in [512 KiB, 512 KiB + e). The count is in uncompressed
     bytes for plain and LZ4 files alike.
   - In the LZ4 file of 600 KiB entries, an empty compressed chunk written before each oversize entry ends every other page with no hint. The
     bound still holds there; only "each page holds k" fails.
2. **Cluster:**
   - The page caps one dispatcher's outstanding hints at k = 32 / 8 / 1, with every page `CONTINUE`.
   - The receiver held exactly k hints at its peak, out of backlogs of 16,384 / 4,096 / 256. Its live `[B` rose by ≤ 1.4 MB.

**Positive control:** not required, since this is not a negative-estimate file. The backlog N ≫ k is the filed control. The instruments moved:
node-2 `Hint` went from 0 when paused to k during delivery, and c and `sent` changed inversely with e.

**Feedback filed:**
- The case file's section D is updated (uncommitted).
- Amendments B2a, B2c, B2d, B2e, B2g, B3a, B3c, B3d, B3e, B3g, B3h and B4 are in the case file (uncommitted).
- `_INDEX-advisor.md`: the §2 row `86862af8…5a09` was added, and the §1 Stage 4 column filled.
- `HANDOFF.md` was not edited (`HANDOFF-ADVISOR.md` §8).
