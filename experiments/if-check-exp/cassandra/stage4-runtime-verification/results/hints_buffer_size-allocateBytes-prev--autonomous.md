# hints_buffer_size-allocateBytes-prev--autonomous — stage-4 results  <!-- file: results/hints_buffer_size-allocateBytes-prev--autonomous.md -->

> **Case:** [`hints_buffer_size-allocateBytes-prev--autonomous`](../../stage3-ai-deep-read/cases/hints_buffer_size-allocateBytes-prev--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/hints_buffer_size-allocateBytes-prev--autonomous/`](../harness/hints_buffer_size-allocateBytes-prev--autonomous/).
>
> **Unit: Confirmed — caps** (B2g row 1).
> - For B = 1, 32 and 64 MiB, a slab took exactly ⌊B / e⌋ entries of e = 4,173 B (251, 8,040 and 16,081), holding 1,047,423, 33,550,920 and
>   67,106,013 B. That is within one entry of B and never above it.
> - The slab was refused, then closed: a 13-byte request after the refusal was refused too, though 1,153–3,512 B were still free (the closed-slab test
>   at `:187`).
> - The direct pool rose by exactly B on `create` (Count +1), did not move while the slab filled, and went back to its baseline on `free()`.
> - A single hint of B/2 − 11 B threw `IllegalArgumentException`. The pool case: exactly 3 slabs, 3 × B of direct memory, and the writer waiting in
>   `take()`.
>
> **Cluster: Confirmed — caps** (B3g row 1). Two nodes on loopback; node 1 is the hint writer and has `max_mutation_size` unset, 32MiB and 64MiB.
> - Every slab node 1 created was B = 32, 64 and 128 MiB (33,554,432 / 67,108,864 / 134,217,728).
> - Every refusal (66, 45 and 37 `full` lines in phase D) reported `cap` = B.
> - Each arm held 2 slabs at most: the periodic flush's slab before phase U, and one more in phase D.
> - The settled direct-memory step over phase D was B + 0.14 MB, B + 0.29 MB and B + 0.14 MB, so per-slab memory scales 1:2:4.
> - 250,000 hints (274,000,142 B on disk) were written in every arm. On-disk hints are not bounded by B.
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
| **Case-file version** | Filed with sha256 `eacd4e28…4695` (index §2, "as filed (hints batch)"). Frozen after the step-0 audit's thirteen amendments (2026-10-26, before any run-1 reading) at sha256 **`198eb1ce2924b51fd0e626f7363c95f8ded2920ecf659a6bbf4ddcb6923c13a2`**. Both tiers' readings were taken at this version. A new row was added to `_INDEX.md` §4. `run1/freeze.txt` holds this hash, the harness hashes and the self-check hash. Nothing was committed, because no commit was asked for. |
| **Harness** | [`../harness/hints_buffer_size-allocateBytes-prev--autonomous/`](../harness/hints_buffer_size-allocateBytes-prev--autonomous/) (Notes 1–3 below the table) |
| **Tiers and values** | **Unit (B2):** one `ant testsome` JVM with `-XX:MaxDirectMemorySize=1g`. Slab sizes B ∈ {1 MiB, 32 MiB, 64 MiB} (cases 1, 2); a pool at B = 32 MiB with 3.5 × B offered (case 3); the formula lines. **Cluster (B3):** two nodes from one clone, heap 2G, direct 2g. Node 1's knob arms are (i) default → B = 32 MiB, (ii) `max_mutation_size: 32MiB` → 64 MiB, (iii) `64MiB` → 128 MiB. Per arm: phase U and phase D, each 200,000 stress writes of 1 KiB at RF 2. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

**Note 1, harness files:**
- `HintsBufferCapTest.java` (B2c as amended) and `unit-run.sh`.
- `hb.btm`: the three filed Byteman rules unchanged, plus two observation-only rules, `slab dmem before` and `slab dmem after`. Those two print the
  direct pool's `MemoryUsed` and `Count` around each `HintsBuffer.create`.
- `HbJmx.java`: a JMX sampler on node 1, once a second. It records the direct and mapped pools, `TotalHints`, and the exact bytes and file count
  of the hints directory.
- `cluster-run.sh`: three arms, each with two node lifetimes and phases U and D. `summarize.py` builds the readings tables.

**Note 2, instrument checks before the freeze:**
- **Byteman:** `TestScript` type-checks all five rules with no errors (`shakedown/testscript-hb-btm.txt`).
- **Unit shakedown:** B = 256 KiB, pool case off (`shakedown/unit-B256KiB-summary.txt`). It confirmed the line format, a constant e = 4,173, and an
  exact dmem step of B with Count +1.
- **Cluster shakedown 1:** 20,000 writes, arm (i). Node 2 never left `UJ`.
  - Its bootstrap streams `system_auth` by zero-copy `FileChannel.transferTo`, and on this host that fails with `IOException: Operation not
    permitted` (`shakedown/cluster1-bootstrap-transferTo-error.txt`).
  - Fix: `auto_bootstrap: false` on both nodes (amendment B3a). The ring is empty when node 2 joins, so nothing needs streaming. Defect S1.
- **Cluster shakedown 2:** 20,000 writes, arm (i) (`shakedown/cluster2-*`).
  - The agent loaded. The `dmem` pair for the startup slab read exactly B, with Count +1.
  - Node 2 went DN. The sampler wrote 138 lines.
  - TotalHints rose by 25,000: cassandra-stress adds a warm-up of n/4, at most 50,000.
  - Two harness bugs were fixed before the freeze. A log line split the `STRESS` summary line. The OOM count matched the
    `HeapDumpOnOutOfMemoryError` JVM argument and a `CompileCommand` line.
  - 20,000 hints cannot fill a 32 MiB slab, so this shakedown has no `full` line and no second slab. It is not evidence.

**Note 3, self-check:** [`run1/selfcheck.py`](hints_buffer_size-allocateBytes-prev--autonomous/run1/selfcheck.py) was written before run 1. Its
parsers were tested on the shakedowns (`SHAKEDOWN=1`, `shakedown/selfcheck-on-shakedown.out`: 12 of 17 pass; the 5 failures are the cells that
shakedown sizes cannot reach). It does not use `summarize.py`, `hbcap.txt` or `readings.txt`. Instead it re-reads the test log, `node1.out` (each
line placed by its own byte offset), `samples.tsv`, the raw stress logs and node 1's `system.log`.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the direct memory of one hints slab, and the hint bytes it holds |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | Unit: B ∈ {1, 32, 64} MiB. Cluster: `max_mutation_size` unset / 32MiB / 64MiB, giving B = 32 / 64 / 128 MiB (B2b, B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit: the direct-pool MXBean, as filed. Cluster: the filed ΔD − ΔU = k × B cannot isolate slab memory, for two reasons in source (see B. Logic). Amendment B3d adds the per-slab `dmem` lines and the settled step S1 − S0. The gap named in B2d stays: the JDK's accounting, not the native allocation. |
| A. Core question | usage driven to the limit and past it | Partly → Met after amendment | Unit cases 1 and 2: met. Case 3: at 2.5 × B the writer never needs a fourth buffer, so it is never "blocked" (`HintsBufferPool.java:107-134`); it now offers 3.5 × B (amendment B2c). Cluster: ≈ 220 MiB of hints as filed, ≥ 1.6 × B at 128 MiB. |
| B. Logic | each step says what it establishes | Met | B2h/B3h |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Unit: made exact (n = ⌊B/e⌋, found = n, dmem steps, cnt steps; amendment B2f). Cluster: the filed direct-memory relation is wrong from source. (a) The first slab is created before phase U by the periodic flush (`HintsService.java:116-121` → `HintsWriteExecutor.java:166-168` → `HintsBufferPool.java:93-105`), so k counts a slab that phase D does not add. (b) ΔU includes networking-pool chunks that stay allocated (`BufferPool.java:128, 385`) and that phase D does not need again. Replaced by P1–P8 (amendment B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Added verdict words, Invalid rows and the Effect rule. For the cluster: a P5-only failure, k1 < 2, and how arms combine (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Disallow evidence: `nextNull`, `alloc1Null` and `found` in the unit tier; `full … cap` lines in the cluster tier. Ceiling follows the knob: n, dmem and slabSize at 3 values. |
| B. Logic | alternative explanations and their controls | Met | Unit: `free()` restores the baseline, and warm-ups keep the per-thread scratch buffer out of the deltas. Cluster: Count steps per pair, and S0/S1 with no load (amendment B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1 |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Line formats, scripts and log locations added (amendments B2d, B2e, B3e) |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | S0/S1 windows, k0/k1, quiet window, tail, sampler rate (amendments B3d, B3e) |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | The filed design assumes Linux, `cp -r` node copies, `sjk mx` and `du -sb`. Shakedown 1 found that zero-copy bootstrap fails here. All fixed before the freeze (amendments B2a, B3a, B3d, B4). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≈ 274 MB of hints per arm against 134 GiB free; 3 × 128 MiB direct against 2g; a 2G heap per node on 32 GiB |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `~/cassandra-src` at `cassandra-5.0.9`: see Note 4 below the recommendations. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone, `build-test`, `-Dtest.jvm.args` | Amendment 2026-10-26 | No Linux node; clean clone |
| 2 | B2c: case 3 offers 3.5 × B; fixed-size hints; warm-ups; slab contents counted | Amendment 2026-10-26 | Group A (limit), group B (exact e) |
| 3 | B2d: line formats | Amendment 2026-10-26 | Group C |
| 4 | B2e: `unit-run.sh` | Amendment 2026-10-26 | Group C |
| 5 | B2f: exact predictions | Amendment 2026-10-26 | Group B |
| 6 | B2g: verdict words, added rows, Effect rule | Amendment 2026-10-26 | Group B |
| 7 | B3a: one clone, per-node conf, JMX 7299, heap and direct options, tracked nodes; `auto_bootstrap: false` (after shakedown 1) | Amendment 2026-10-26 | Group D |
| 8 | B3d: JMX sampler; `dmem` Byteman rules; offsets; S0/S1/k0/k1 definitions | Amendment 2026-10-26 | `sjk`/`du -sb`; group A |
| 9 | B3e: one script, quiet window, tail | Amendment 2026-10-26 | Group C |
| 10 | B3f: P1–P8 replace ΔD − ΔU = k × B | Amendment 2026-10-26 | Wrong from source (group B); a §9a change made in the audit, for a reason that depends on no reading |
| 11 | B3g: rows read against P1–P8; arm combination | Amendment 2026-10-26 | Group B |
| 12 | B3h, B4: controls; host paths | Amendment 2026-10-26 | Paths |
| 13 | B2b's formula case only re-computes `Math.max(M × 2, 32 << 20)` in the test. A unit case that sets `max_mutation_size` and builds a `HintsService` would test the wiring (the cluster tier does). B3c's arithmetic leaves out cassandra-stress's warm-up (n/4, at most 50,000 writes), so phase D writes 250,000 hints, not 200,000. | Left for stage 3 | Not needed for B1's claim |

**Note 4, citations checked:**
- `HintsBuffer.java:55-58, 75-105, 148-197, 212-257`;
- `HintsBufferPool.java:41-53, 59-134, 136-139`;
- `HintsService.java:79, 102-121, 161-172`; `HintsWriteExecutor.java:60, 83-94, 130-180`;
- `DatabaseDescriptor.java:573-574, 891-901, 2827-2830`; `Config.java:406-407, 444-445`; `CassandraRelevantProperties.java:351`;
- `BufferPool.java:74, 128-132, 384-385`; `Mutation.java:445-458`;
- `test/unit/.../HintsBufferTest.java:63-92, 196-209`; `SchemaLoader.java:362-392`;
- `build.xml:94, 1192`; `conf/cassandra.yaml:68, 80, 102, 660, 706, 825`; `conf/cassandra-env.sh:235-238`.

All hold. The filed A3 citations hold as well.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 16:05–16:06 EDT; cluster 16:06–16:18 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro) |
| Hardware | 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 134 GiB free |
| Network and processes | Loopback 127.0.0.1–.3 present. Ports 7000/7001/7199/7299/9042/9091 free and no Cassandra daemon before the run; none after. |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: the `ant testsome` forked JVM with `-XX:MaxDirectMemorySize=1g`. Nodes: `-Xms2G -Xmx2G`. `cassandra-env.sh` adds `-XX:MaxDirectMemorySize=8192M` and the later `-XX:MaxDirectMemorySize=2g` from `JVM_EXTRA_OPTS` wins (order in the JVM-arguments line). Node 1 also gets the Byteman 4.0.20 agent (`script:`, `boot:`, no listener). |
| Ant | 1.10.18 |
| Python | 3.8.11 (harness scripts only; the load is cassandra-stress from the clone) |
| Local `cassandra-src` clone | `$W/cassandra-run36` = `~/Library/Caches/stage4/cassandra-run36`, a fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`. `ant -Dlocal.repository=$W/m2 build-test`: `BUILD SUCCESSFUL` in 1 min 1 s. `git status` clean after both tiers. |
| Case-file commit / harness commit | Filed version sha256 `eacd4e28…4695`. Amendments, harness and results are uncommitted (sha256 in §1 and `run1/freeze.txt`). |
| Storage for node data | local SSD under `$W/node-hb1` and `$W/node-hb2` (`conf`, `data`, `commitlog`, `hints`, `saved_caches`, `cdc_raw`, `logs`), wiped between arms and at the end |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/hints_buffer_size-allocateBytes-prev--autonomous/` |

Full-log contents, under that directory:
- `clone-build-run36.log`, `stepE.txt`, `testscript.txt`, `unit-run.out`, `cluster-run.out`;
- `shakedown-unit/`, `shakedown-cluster-attempt1/` and `shakedown-cluster/`, which are not evidence;
- `unit/`: `ant.log`, `TEST.log`, `TEST.xml`, `hbcap.txt`, `commands.log`, `summary.txt`, `readings.txt`;
- `cluster/`: `commands.log`, `summary.txt`, `readings.txt`;
- `cluster/arm-{i,ii,iii}/`:
  - `node1.out` (the Byteman lines) and `node2.out`;
  - `node1-system.log` and `node2-system.log`;
  - `samples.tsv`, `stress-U.log` and `stress-D.log`, `hbcap.txt`;
  - the yaml overrides, status files and hints-directory listing.

**Machine facts relied on** (from `environment-advisor.md` and earlier runs on this host):
- **Workspace:** every file lives under `$W`, since there is no `mkdir` in `$HOME` outside it. Every `ant` call takes `-Dlocal.repository=$W/m2`. Commands touching `$W`, Java or the network ran unsandboxed.
- **Node start:** there is no `setsid`, so each node is a tracked background `bin/cassandra -f`. `JVM_EXTRA_OPTS` (direct size, the agent) is scoped to that command only. The loopback aliases were checked.
- **JMX:** `nodetool sjk mx` exits 0 on failure, so a JMX client was used. BSD tools: no `du -sb`, so the sampler sums file sizes; `sed -i ''`.
- **Unit tests:** test stdout lands in `build/test/logs/**/TEST-<class>.log`. The unit yaml's read thresholds are irrelevant here, since nothing is read back through CQL.
- **Authentication:** no guardrail is on this path (`HintsService.write` → `HintsBufferPool.write`), so the default `AllowAllAuthenticator` was kept.
- **Constants and Byteman:** the knob (`max_mutation_size`) is a yaml key, so nothing is patched. The 32 MiB floor is a constant and is not varied. The Byteman rules only observe, and `TestScript` type-checked them.
- **Script hygiene:**
  - The daemon pattern in the scripts is split. Long steps ran in the background and were polled.
  - Shakedowns ran before run 1, and bounds were derived from source.
  - Direct baselines (S0) were taken after ingest, with node 2 down and no load. `selfcheck.py` was written before run 1.
  - One foreground `sleep 240` while polling hit the 2-minute tool timeout. Only the poll was killed; the run was in the background and was unaffected.
- **New on this host:** zero-copy streaming (`FileChannel.transferTo` over a socket) fails with `Operation not permitted`. A ring that needs a bootstrap or a stream must avoid it (`auto_bootstrap: false`; `stream_entire_sstables: false` would be the general fix).

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit | B2a/B3a/B4 | Linux, `~/hb-*` paths, node copies by `cp -r`, `--depth 1` clone | Host clone, one clone with per-node conf, host paths (amendments B2a, B3a, B4) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B3d | `nodetool sjk mx` exits 0 on failure, one JVM per call; `du -sb` is GNU-only | `HbJmx` sampler (amendment B3d) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B3f/B3g | ΔD − ΔU = k × B is wrong from source: the first slab predates phase U, and ΔU holds retained internode chunks | P1–P8 with per-slab `dmem` lines and the settled step S1 − S0 (amendments B3d, B3f, B3g) | 2026-10-26, before the freeze; a §9a change, made in the audit for a reason that depends on no reading | uncommitted |
| A4 | audit | B2c/B2f | Case 3 at 2.5 × B never reaches `take()`, so "the writer is blocked" could not hold | 3.5 × B (amendment B2c) | 2026-10-26, before the freeze | uncommitted |
| S1 | shakedown | B3a/B3e step 1 | Node 2's bootstrap stream fails on this host (`transferTo`: Operation not permitted), so node 2 stays `UJ` | `auto_bootstrap: false` on both nodes (amendment B3a) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| H1 | shakedown | harness | `STRESS` summary line split by a log line; OOM count matched JVM-argument text | `log … >&2` in `stress()`; OOM pattern `java.lang.OutOfMemoryError` excluding JVM-argument and CompileCommand lines | 2026-10-26, before the freeze | none (harness only; `run1/freeze.txt`) |

Run 1: no defect. Both tiers ran as written at the frozen version.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:**
`hints_buffer_size-allocateBytes-prev--autonomous/run1/unit/commands.log` and `…/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier.** Sources: `run1/unit/test-log-hbcap-lines.txt`, `ant-tests-run.txt`, `readings.txt`.
- Ant: `Tests run: 2, Failures: 0, Errors: 0`.
- Setup line: `maxDirectMemorySize=1g`; e = 4,173 B for every hint (`emin` = `emax`).

| B | n | ⌊B/e⌋ | sum (B) | leftover | `nextNull` / `remaining` | `alloc1Null` | found / foundBytes | dmem1 − dmem0 | cnt step | dmem2 − dmem1 | dmem3 − dmem0 | case 2 (request) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1,048,576 | 251 | 251 | 1,047,423 | 1,153 | true / 0 | true | 251 / 1,047,423 | **1,048,576** | +1 | 0 | 0 | IAE (524,277) |
| 33,554,432 | 8,040 | 8,040 | 33,550,920 | 3,512 | true / 0 | true | 8,040 / 33,550,920 | **33,554,432** | +1 | 0 | 0 | IAE (16,777,205) |
| 67,108,864 | 16,081 | 16,081 | 67,106,013 | 2,851 | true / 0 | true | 16,081 / 67,106,013 | **67,108,864** | +1 | 0 | 0 | IAE (33,554,421) |

- n(64 MiB) = 16,081 = 2 × 8,040 + 1.
- Case 3 (B = 32 MiB): `allocatedBuffers` = 3 (`max` = 3) and `held` = 2. The writer is `WAITING` with `inTake=true`, after writing 24,120 of 28,143
  hints (= 3 × 8,040). The direct step is 100,663,296 = 3 × B, with Count +3. After the frees the direct pool is back to 27,372.
- Formula lines: M = 8, 16 and 32 MiB give B = 33,554,432; 33,554,432; 67,108,864.

**Cluster tier.** Sources: `run1/cluster/summary.txt`, `readings.txt`, and `arm-*/hbcap-with-offsets.txt`, `samples.tsv`, `stress-*-results.txt`.

Setup and validity, for every arm:
- Read-backs (node 1's `Node configuration` line):
  - (i) `commitlog_segment_size=32MiB`, `max_mutation_size=null` (the default, M = 16 MiB);
  - (ii) `64MiB` and `32MiB`;
  - (iii) `128MiB` and `64MiB`.
  - All arms also show `hinted_handoff_enabled=true`, `max_hint_window=3h`, `max_hints_size_per_host=0B` and `hints_flush_period=10000ms`.
- Status UN/UN at the start, and `DN 127.0.0.2` on node 1 after the drain and kill.
- Agent: no rule error, and 4 `HBCAP` lines before phase U.
- Stress: 200,000 partitions and 0 errors in U and in D. Each phase also writes cassandra-stress's 50,000-iteration warm-up.
- Node 1: 0 ERROR lines and no `java.lang.OutOfMemoryError`; alive at the end of each arm.
- S0 and S1: 15 samples each.

| Arm (B_arm) | `create slabSize` (where) | `dmem` pairs (cap, step, Count step) | `full` lines in D, caps | `allocatedBuffers` (k0 → k1) | S0 → S1 (B) | S1 − S0 − (k1 − k0) × B | ΔU / ΔD (reported) | TotalHints Δ(D) | hints dir at tail end |
|---|---|---|---|---|---|---|---|---|---|
| (i) 33,554,432 | 2 × B (pre-U, D) | (B, **33,554,432**, 1); (B, 33,597,920, 7) | 66, all `cap=33554432` | 1, 2 (1 → 2) | 51,030,628 → 84,726,400 | **+141,340** | 2,196,587 / 33,695,772 | 250,000 | 274,000,142 B, 3 files |
| (ii) 67,108,864 | 2 × B (pre-U, D) | (B, **67,108,864**, 1); (B, **67,108,864**, 1) | 45, all `cap=67108864` | 1, 2 (1 → 2) | 84,389,104 → 151,792,705 | **+294,737** | 2,178,371 / 67,403,601 | 250,000 | 274,000,142 B, 3 files |
| (iii) 134,217,728 | 2 × B (pre-U, D) | (B, **134,217,728**, 1); (B, 134,241,312, 12) | 37, all `cap=134217728` | 1, 2 (1 → 2) | 151,663,394 → 286,019,097 | **+137,975** | 1,082,665 / 134,355,703 | 250,000 | 274,000,142 B, 3 files |

Per-slab steps with a Count step of 1: 33,554,432; 67,108,864; 134,217,728, a ratio of exactly 1 : 2 : 4. The first `create` of each arm is
at about 56.8 KB into `node1.out`, before phase U (from the periodic flush). The second is after phase D's start offset.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — Valid. [observed: `unit/test-log-hbcap-lines.txt`, `ant-tests-run.txt`]
   - The test ran with `maxDirectMemorySize=1g`, and all three B values printed.
   - The limit was reached and passed: each fill ended on a refused allocation (`nextNull=true`).
2. **Readings** — Nothing unusual. e was constant, so every cell is exact. Every Count step was the slab's own (+1 / 0 / −1). [observed]
3. **Matched row** — B2g row 1: "Σ ≤ B < Σ + e and dmem delta = B for each B, n doubles with B". [observed]
   - sum ≤ B < sum + e for all three B; dmem1 − dmem0 = B with Count +1.
   - n goes 251 → 8,040 → 16,081 (16,081 = 2 × 8,040 + 1).
   - Every other amended B2f cell holds: `found` = n, `foundBytes` = sum, `alloc1Null`, dmem2 = dmem1, dmem3 = dmem0, and case 2 throws.
4. **Excluded rows**
   - Σ > B: max sum − B = −1,153.
   - `allocate(1)` succeeds: false in all three, with leftover ≥ 1,153.
   - dmem delta ≠ B: exact in all three.
   - n flat: it doubles.
   - Case 3 > 3: it is 3.
   - Limit never reached: `nextNull=true`.
   - Not confirmed / Invalid: none of their conditions holds.
5. **Observed vs. inferred** — Inferred: that the JDK's direct-pool accounting equals the native memory of the slab (the gap named in B2d). The
   verdict does not depend on anything else that is inferred.
6. **Deviations and gaps** — None in the run. One `@Test` loops over B instead of one `@Test` per B (amendment B2e); this does not change what is
   measured.
7. **Core question** — Usage follows the constraint. A slab's direct memory is exactly B, and the bytes it accepts stop within one entry below B. A
   refusal closes the slab for good (`:187`). So the check caps both the hint bytes in one buffer and that buffer's memory at B.

**Unit tier conclusion:** B2g row 1 — **confirmed**. Effect: **caps**.

**Cluster tier**

1. **Validity** — Valid in all three arms. [observed: `cluster/summary.txt`; self-check C0, C7, C8]
   - The read-backs show each arm's knob, and node 2 was DN in phase D.
   - The agent loaded with no error, and stress had 0 errors.
   - Hints were written: TotalHints +250,000 in phase D.
   - The limit was passed: 66, 45 and 37 refusals per arm.
2. **Readings** — Points worth noting:
   - In arms (i) and (iii), the phase-D slab's `dmem` pair also caught other direct buffers (Count step 7 and 12). The extra bytes over B were 43,488
     and 23,584. Under amended B3f P4 these pairs are reported and not used; the settled step P5 covers that slab. [observed: `arm-*/hbcap-with-offsets.txt`]
   - Each arm held only 2 slabs, although phase D wrote 274 MB, which is 8.2, 4.1 and 2.0 slabs' worth. The flush executor recycled the first slab
     before the second filled (`HintsWriteExecutor.java:141-154`). [inferred: from k1 = 2 with 66 / 45 / 37 refusals]
   - ΔD equals S1 − S0 in every arm: the tail's direct level was the peak. [observed: `readings.txt`]
3. **Matched row** — B3g row 1: P1–P5, P7 and P8 hold in all three arms. [observed: `readings.txt`, `hbcap-with-offsets.txt`, `samples.tsv`]
   - P1: every `create slabSize` and `dmem after cap` equals B_arm.
   - P2: all `full` lines have `cap` = B_arm and all lie in phase D.
   - P3: k1 = 2.
   - P4: steps with a Count step of 1 equal B_arm exactly.
   - P5: S1 − S0 − B_arm = +141,340, +294,737 and +137,975 B, against a tolerance of ±8,388,608.
   - P6: the steps are in a ratio of 1 : 2 : 4.
   - P7: TotalHints Δ(D) = 250,000 ≥ 190,000. The hints directory holds 274,000,142 B ≥ B_arm, identical in all arms.
   - P8: 200,000 partitions and 0 errors in each phase.
4. **Excluded rows**
   - Row 2 (slabSize ≠ B_arm): none.
   - Row 3 (cap or per-slab step ≠ B_arm): none.
   - Row 4 (P5 fails): within 0.3 MB.
   - Row 5 (no `full` in D): 66 / 45 / 37.
   - Row 6 (no hints): +250,000.
   - Row 7: k1 = 2 (not > 3, not < 2).
   - Row 8 (Invalid): every validity condition holds.
5. **Observed vs. inferred**
   - Inferred: that the direct pool's step is the slab's real memory (as in the unit tier).
   - Inferred: that the 0.14–0.29 MB above (k1 − k0) × B in P5 is other direct buffers (the networking pool and the per-thread scratch buffers of
     new write threads), not slab memory. The clean per-slab pairs read exactly B, so the slab itself adds no extra bytes.
   - The verdict rests on observed values.
6. **Deviations and gaps** — None in the run.
   - Hint bytes accepted per slab are not observable on the node. The cluster tier shows the refusals at B_arm and the memory per slab; the unit
     tier shows the bytes.
   - The shakedown fix (`auto_bootstrap: false`) affects only how node 2 joins the empty ring.
7. **Core question** — On a real node, `max_mutation_size` sets B = max(2 × M, 32 MiB):
   - Every hints slab has exactly that capacity and costs exactly B of direct memory.
   - Every refusal reports that capacity.
   - Per-slab memory scales 1 : 2 : 4 as M goes 16 → 32 → 64 MiB.
   - The constraint therefore caps the memory of each hints buffer. Hints on disk (274 MB in every arm) are not bounded by B, as the case says.

**Cluster tier conclusion:** B3g row 1 — **confirmed**. Effect: **caps**.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1; sha256 in `run1/freeze.txt`) re-reads the raw files with its own parsers:
- `unit/ant.log` and the `HBCAP` lines of `unit/TEST.log`;
- `cluster/summary.txt` (the RUN, MARK and STATUS lines only);
- each arm's `node1.out`, re-sliced by byte offset;
- each arm's `samples.tsv` (its own median), the raw `stress-{U,D}.log`, and `node1-system.log` (the `Node configuration` line and JVM arguments).

Output `run1/selfcheck.out`: **46 checks, 46 pass, 0 fail**. It names `UNIT-ROW Confirmed (B2g row 1)` and
`CLUSTER-ROW Confirmed (B3g row 1)`.
- U0–U8: 17 unit checks.
- C00 and C0–C10: 29 cluster checks.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U0–U2, C00, C0, C7 and C8 pass. `summary.txt` re-read: DN lines, 0 ERROR, OOM 0, `daemons_left=0` after each arm. |
| 2. Readings | yes | `hbcap-with-offsets.txt` re-read: pairs with Count steps 7 and 12 in (i) and (iii); the first `create` before phase U and the second after phase D's start in every arm |
| 3. Matched row | yes | U3–U6 and C1–C6, C9 and C10 pass. The unit table above matches `test-log-hbcap-lines.txt` line by line. |
| 4. Excluded rows | yes | Max unit sum is below B; `alloc1Null=true` in all three; no cap other than B_arm; P5 deviations ≤ 294,737 B |
| 5. Observed vs. inferred | yes | The two inferred statements (JDK accounting = native memory; the P5 excess is other buffers) do not decide the row. P4 shows exact B for clean pairs in all three arms. |
| 6. Deviations and gaps | yes | A1–A4 and S1 were fixed before the freeze; H1 touched only the harness. Bytes accepted per slab on the node are named as not observable. |
| 7. Core question | yes | The memory per slab follows B at 3 values in both tiers. The disallow branch is seen directly (unit `nextNull` and `alloc1Null`; node `full … cap=B`). |

### 5.2 Run 2?

**No** — 2026-10-26. The verdict rests on exact observed values: slab sizes, per-slab direct steps, refusal capacities, n = ⌊B/e⌋, and slab
contents. The self-check settles every part from run 1's files. The result confirms the design's own claim; it neither refutes it nor confirms a
bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):**
- (1) Each hints buffer allocates exactly B = max(2 × `max_mutation_size`, 32 MiB) bytes of direct memory.
- (2) The serialized hint bytes accepted into one buffer never exceed B. Once the next hint would pass B, the buffer is closed and later hints go to
  another buffer.

"Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1) | **caps** | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g row 1) | **caps** | run 1 + self-check | 2026-10-26 |

1. **Unit:**
   - At B = 1, 32 and 64 MiB a slab accepts ⌊B/e⌋ entries, at most B bytes, and after its first refusal refuses even a 13-byte request.
   - It costs exactly B of direct memory, which does not grow while it fills.
   - The pool holds 3 × B with the writer waiting.
2. **Cluster:**
   - With M unset, 32MiB and 64MiB, every slab and every refusal is at B = 32, 64 and 128 MiB.
   - Each slab adds exactly B of direct memory (per-slab steps 1 : 2 : 4; the settled steps within 0.3 MB of B).
   - Hints on disk are 274 MB in every arm.

**Positive control:** not required, since this is not a negative-estimate file. The instrument moved with each slab (per-slab steps of B, settled
steps of B).

**Feedback filed:**
- The case file's section D is updated (uncommitted).
- Amendments B2a, B2c–B2g, B3a, B3d–B3h and B4 are in the case file (uncommitted).
- `_INDEX.md`: the §2 row `198eb1ce…13a2` was added, and the §1 Stage 4 column filled.
- `HANDOFF.md` was not edited (`HANDOFF-ADVISOR.md` §8).
