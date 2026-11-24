# rowsize-checkcanread-bytesread--autonomous — stage-4 results  <!-- file: results/rowsize-checkcanread-bytesread--autonomous.md; written outside the repo at ~/writeup-ext/out/o122/results.md -->

> **Filed 2026-11-24 (coordinator):** case file (with the stage-4 amendments and section D) in [`../../stage3-ai-deep-read/cases/rowsize-checkcanread-bytesread--autonomous.md`](../../stage3-ai-deep-read/cases/rowsize-checkcanread-bytesread--autonomous.md), harness in [`../harness/rowsize-checkcanread-bytesread--autonomous/`](../harness/rowsize-checkcanread-bytesread--autonomous/); raw logs (`~/writeup-ext/out/o122/raw/`, 16 MB) and `logs/` stay outside the repo; small logs also on `ms0640` in `/mydata/jingsong-cass-s4/o122/`. Paths below that point to `~/writeup-ext/out/` are where the run kept them.
>
> **Case:** `rowsize-checkcanread-bytesread--autonomous` (stage-3 order 122, case file `~/writeup-ext/out/o122/rowsize-checkcanread-bytesread--autonomous.md`, outside the repo)
>
> **Status:** verdict filed (2026-11-24). Run 1 is done at both tiers and self-checked; there is no run 2.
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`). See the [definition](../../../stage4-runtime-verification/README.md#outcome-class).
>
> **Agent:** autonomous (the suffix of the case-file stem). Below, "§9a" means each tier's predictions and conclusions table: B2f and B2g for the unit tier, and B3f and B3g for the cluster tier, both with the audit amendments B2i and B3i. "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is its section D. The run was done as Jingsong.

## 1. Before run 1: design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | The case file is outside the repo (written by stage 3 for order 122). Repository HEAD at the audit: `8f76f2390`. sha256 as filed: `916617ab0399b8330b7b2088f6ddd635ef4283c61e4bea00ed49fd5c1203255e`. **The audit added amendments B2i and B3i (dated 2026-11-24) before any harness or reading. sha256 after them: `e4b8767ec2b77a9d797c95ad74992e7088fdfd8f0252ec550133946a640838fa`**, written to `logs/freeze.sha` at 2026-11-24T06:18:52Z. B2f, B2g, B3f and B3g with B2i and B3i are frozen at this hash. Section D was filled after the run; see §8 for that hash. |
| **Harness** | `~/writeup-ext/out/o122/harness/`, not committed. It holds `TrackedDataInputPlusLimitTest.java` (md5 `6436ef07…`), `unit-run.sh` (`f2e8b90a…`), `cluster-setup.sh` (`2e154baa…`), `cluster-cfg.sh` (`b45ef997…`, final version; its `stop_node` was fixed between C2 and C3, see §3 #2) and `analyze_cluster.py` (`3bb2396f…`, final version; two parsing fixes made before any verdict, see §3 #3–4). |
| **Instrument checks** | **Unit:** known-answer method `instrumentKnownAnswer`. A plain `new byte[33554432]` read as `allocB=33554448` (32 MiB + 16 B header), and `testLimitFires` passed, in a separate `ant testsome` run before run 1 (`raw/unit/check/`, results copied into `raw/unit/run1/` as `TEST-…-instrumentKnownAnswer,testLimitFires.xml`). **Cluster:** the uncorrupted sanity read of B3e step 4 is the in-run check. In each config it recorded `byte[]` events of exactly S + 16 B (3,145,744 B, or 6,291,472 B in C3) with the stack `ByteArrayAccessor.read:102 ← AbstractType.read:599 ← Cell$Serializer.deserialize:339` (`raw/analyze_cluster.out`). |
| **Tiers and values** | **Unit (B2):** rows r1–r6 of B2f: L ∈ {64 B, 1 MiB, 16 MiB}, V ∈ {16 MiB, 64 MiB}, maxValueSize ∈ {256 MiB, 8 MiB (control)}, plus the well-formed row L = V + 4. Each row ran 3 times after a warm-up, plus `testLimitFires`. **Cluster (B3):** C1 (S = 3 MiB, V = 100 MiB), C2 (3 MiB, 200 MiB), C3 (6 MiB, 200 MiB), C4 control (3 MiB, 200 MiB, `max_value_size: 64MiB`). Each config: 3 corrupt `SELECT v` reads 10 s apart, plus the optional `SELECT k`. |
| **Audit bottom line** | **Ready after amendments** (2026-11-24) |

### 1.1 Design audit

Estimate: **negative**. The per-row limit `TrackedDataInputPlus.limit` (= `rowSize`) is a framing guard. It is not a heap cap, because the value array is allocated before the limit is checked.

Citations checked against the pinned source (`systems/cassandra/source/`, `cassandra-5.0.9`; `git status` clean):
- `TrackedDataInputPlus.java:34, 40-53, 108-120, 174-189`
- `UnfilteredSerializer.java:583-587, 645-655`
- `AbstractType.java:582-600`
- `ByteArrayAccessor.java:100-104`
- `Cell.java:325-342`
- `Config.java:309-310`
- `DataInputPlus.java:81-84`
- `RebufferingInputStream.java:147-165`
- `DataInputBuffer.java:53-62`
- `DeserializationHelper.java:109-112`
- `build.xml:1245` and `:1382-1392`
- `conf/cassandra.yaml:471, 1864, 2143`

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1: heap bytes of the cell value array (`new byte[V]`, `ByteArrayAccessor.java:102`). |
| A. Core question | knob varied, ≥ 3 values incl. default, or another approach with the reason | Partly | The limit cannot be set; it is the row's own size (A1). The unit tier sets L directly at three values. The cluster tier varies it through S at two values (3 and 6 MiB). The design gives the reason: the 4-byte vint width and the 16 MiB frame and mutation limits. Left as a stage-3 recommendation. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Thread allocated bytes (unit) and JFR outside-TLAB allocation events (cluster) measure the heap allocation itself. Gap named in B2d and B3d: resident heap after the read is not observed, because the array is garbage at once. |
| A. Core question | usage driven to the limit and past it | Met | B2c and B3c arithmetic: `bytesRead + V > L` in every corrupt row, so the check fires. |
| A. Core question | positive control for a negative estimate | Met | `max_value_size < V` (unit 8 MiB, cluster 64 MiB): same input and instruments, and a cap known to bind before allocation (`AbstractType.java:594`). |
| B. Logic | each step says what it establishes | Met | B2h and B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f (A bands in MiB, exception, bytesRead) and B3f (one event of ≈ V per read, the message). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met | Rows for refuted, flat, limit never reached, instrument broken and control failed are present. A catch-all "any other mismatch" row was added (B2i.3, B3i.5). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For a "does not cap" claim: allocation follows V and not L, with the EOF (the limit's disallow branch) logged after the allocation. |
| B. Logic | alternative explanations and their controls | Met | Control row, well-formed row, varying L at fixed V, `testLimitFires`. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3 step 5 and B1. |
| C. Specific | an AI can run B2 and B3 without re-deriving the code path | Met | Commands and the patch script are exact. Tolerances and the per-read count were made explicit in B3i.4. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | JFR file names per phase (B3i.2), repetition reporting (B2i.2), insert fallback (B3i.3) and process check (B3i.6) were added. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ms0640`: JDK 11.0.33, Ant 1.10.12, `jcmd` and `jfr` present; a built `/mydata/s4/cassandra-base`. The test and driver are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Data under 20 MiB per config. The largest allocation is 200 MiB in a 1 GiB heap (cluster) or 64 MiB in a 4 GiB heap (unit). 18 GB free on `/mydata`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | All match. The only offset is cosmetic: the `max_value_size` throw statement starts at `:594` and the exception line is `:595`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Paths, prebuilt copy, `ulimit -n` | Applied, B2i.1 and B3i.1, 2026-11-24 | The node and directories are fixed by the assignment; the soft `nofile` limit is 1024. |
| 2 | Repetition reporting (3 reps plus median) | Applied, B2i.2 | B2d asked for medians but B2e printed one line per row. |
| 3 | Per-phase JFR file names | Applied, B3i.2 | B3e step 7 asked for "a fresh `rec.jfr` filename" without naming it. |
| 4 | Insert fallback if cqlsh cannot send a 12 MiB statement | Applied, B3i.3 (not needed in the run) | Risk of client-side lexer time. |
| 5 | Exact event band and per-read count; catch-all rows | Applied, B2i.3, B3i.4 and B3i.5 | Makes row 1 decidable and every outcome covered. |
| 6 | Process check by `ps … [C]assandraDaemon` | Applied, B3i.6 | Stage-4 safety rule. |
| 7 | A third cluster L value | Left for stage 3 | Needs S ≥ 2 MiB with a 4-byte vint and a mutation under 16 MiB, for example S = 12 MiB sent with a bound parameter. Not needed for B1, since the unit tier varies L three ways. |

**Agreement criteria:** not applicable. Run 2 was not done (§5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-24. Unit tier 06:20–06:21Z; cluster tier 06:23–06:37Z (C1, C2, then C3 and C4 after the harness fix). |
| Node (CloudLab name and type) | `ms0640` = `node1.jason92-326377.misconfiguration-pg0.utah.cloudlab.us`, **aarch64** (Utah m400), 8 cores, 62 GiB RAM, 8 GiB swap. Node lock `/mydata/s4/NODE-LOCK` held from 23:16:09 MST (06:16Z) to 06:37Z. |
| OS and kernel | Ubuntu 22.04.1 LTS, `5.15.0-191-generic` |
| JDK | OpenJDK 11.0.33 (`11.0.33+9-post-1ubuntu1-22.04.1`), arm64; G1 (`-XX:+UseG1GC`) |
| Ant | 1.10.12 |
| Local source copy | `/mydata/jingsong-cass-s4/o122/src` = `cp -a /mydata/s4/cassandra-base`, a `copy-source.sh` copy of `cassandra-5.0.9` that was already built (`git describe` gives `cassandra-5.0.9`, `git status` clean). The unit test ran there (`ant testsome`). The node ran from `cluster/node-tree`, a `cp -a` of it, in which `ant` was never run. Nothing was built in the repository. |
| Case-file commit / harness commit | Case file outside the repo, sha256 in §1. Harness not committed. |
| Storage for node data | `/dev/mapper/emulab-node1--bs` on `/mydata`, 39 GB, 18 GB free. Node data under `/mydata/jingsong-cass-s4/o122/cluster/` (removed after the run). |
| Unit JVM | `ant testsome` JUnit JVM, `-Xmx4G` (`build.xml:1245`: 4G for unit tests) |
| Node JVM | `-Xms1G -Xmx1G` (`MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M`). JFR `settings=profile`. Ports: storage 17100, native 19142, JMX 17299. `disk_failure_policy: ignore`. Each config's `cmdline-*.txt` records these. |
| Full logs | Kept outside the repo in `~/writeup-ext/out/o122/raw/`: `unit/{check,run1}/`, `results-C1..C4/` (`session.log`, `system.log`, `gc-*.log`, `alloc-{read,write}.json`, `cmdline-*.txt`, `schema.txt`, `sstables.txt`, `read*.out`), `jfr/rec-C*.jfr` and `analyze_cluster.out`. Small logs also remain on the node in `/mydata/jingsong-cass-s4/o122/` (9.9 MB). |

**Environment deviations (none changes B1):**
1. The copy is `cp -a` of a prebuilt `copy-source.sh` copy, not an `rsync` plus `ant jar build-test` (B2i.1 and B3i.1).
2. The GC log is written per phase (`gc-<cfg>-write.log`, `gc-<cfg>-read.log`) instead of one `$RUN/gc.log`.
3. The node is aarch64. No x86 node was used.
4. The cqlsh insert worked: 12.6 s for 3 MiB and 44.3 s for 6 MiB. The B3i.3 fallback was not used.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file change |
|---|---|---|---|---|---|---|
| 1 | audit | B2e, B3e | Unspecified details: repetition output, JFR file names, tolerance band, catch-all outcome. | B2i and B3i | 2026-11-24, before the freeze | B2i and B3i (case file outside the repo) |
| 2 | run 1, cluster | B3e step 10 / step 1 (harness) | The daemon deletes its pid file before it has exited. The harness's `stop_node` waited on the pid file, so it returned while the JVM was still shutting down. C3's first attempt then stopped at its own pre-start check, "port 17299 busy", before writing or starting anything (`raw/results-C3-attempt1-portcheck/session.log`). | `stop_node` now waits on the pid saved at start and until ports 17100, 19142 and 17299 are free. C3 and C4 ran from step 1 with the fixed script. C1 and C2 were unaffected: their stops followed the reads, and their dumps and logs were complete. | 2026-11-24, during run 1 | none (harness only) |
| 3 | analysis | B3d (1) (harness) | `jfr print --json` names the class `[B`, not `byte[]`, so the first analysis of C1 found no events. | The analyzer accepts both names. The raw JSON was unchanged, and the JFR text tool shows the same events (§5). | 2026-11-24, before any verdict | none |
| 4 | analysis | B3d (2) (harness) | Each failed read logs its exception twice (`JVMStabilityInspector.java:70` and `:76`), and the optional `SELECT k` read adds a fourth failure. A raw line count gives 8, not 3. | The analyzer counts the `:70` entries whose time falls in a `SELECT v` read window. | 2026-11-24, before any verdict | none |

## 4. Run 1

**Scope:** the unit tier, all six B2f rows (3 repetitions each) plus `testLimitFires`. The cluster tier, configs C1–C4, each with 3 corrupt `SELECT v` reads and the optional `SELECT k`. **Command logs:** `raw/unit/run1/session.log` and `raw/results-C*/session.log`. **Checks of the frozen numbers:** JUnit `Tests run: 8, Failures: 0, Errors: 0` (the B2f assertions are in the test), and `raw/analyze_cluster.out` with `CHECKS ok=26 bad=0`.

### 4.1 Readings

**Unit tier** (`raw/unit/run1/results.txt`, medians of 3; the exception and `bytesRead` were identical in all 3 repetitions of each row)

| Row | L | V | maxValueSize | Exception | A (median) | bytesRead | B2f |
|---|---|---|---|---|---|---|---|
| r1 | 64 B | 16 MiB | 256 MiB | `EOFException: EOF after 0 bytes out of 16777216` | 16,778,120 B = 16.0009 MiB | 64 | matches |
| r2 | 1 MiB | 16 MiB | 256 MiB | `EOFException: EOF after 1047548 bytes out of 16777216` | 16,778,128 B = 16.0009 MiB | 1028 | matches |
| r3 | 16 MiB | 64 MiB | 256 MiB | `EOFException: EOF after 16776188 bytes out of 67108864` | 67,109,776 B = 64.0009 MiB | 1028 | matches |
| r4 | 64 B | 64 MiB | 256 MiB | `EOFException: EOF after 0 bytes out of 67108864` | 67,109,768 B = 64.0009 MiB | 64 | matches |
| r5 (control) | 1 MiB | 64 MiB | 8 MiB | `IOException: Corrupt value length 67108864 encountered, as it exceeds the maximum of 8388608, …` | 2,408 B (0.0023 MiB) | 4 | matches |
| r6 (well-formed) | V + 4 | 16 MiB | 256 MiB | none (value of 16,777,216 B returned) | 16,777,296 B = 16.0001 MiB (rep 1: 17,064,384 B) | 16,777,220 | matches |
| `testLimitFires` | 100 / −1 | — | — | 101st `readByte`: `EOF after 0 bytes out of 1`; `readFully(150)`: `EOF after 0 bytes out of 150`, then bytesRead 100; unlimited: 200 bytes, no exception | — | — | passes |

**Cluster tier** (`raw/analyze_cluster.out`; event sizes are the JFR `allocationSize`, which includes the 16 B array header)

| Config | L ≈ S | V | `max_value_size` | Exception per `SELECT v` read (system.log) | `byte[]` ≥ 50 MiB per read window | Event size and stack | `SELECT k` (optional) | Evidence |
|---|---|---|---|---|---|---|---|---|
| C1 | 3 MiB | 100 MiB | 256 MiB | 3 × `CorruptSSTableException` caused by `EOFException: EOF after 0 bytes out of 104857600` | [1, 1, 1] | 104,857,616 B; `ByteArrayAccessor.read:102 ← ByteArrayAccessor.read:40 ← AbstractType.read:599 ← Cell$Serializer.deserialize:339` (thread `ReadStage-2`) | 1 event of 104,857,616 B, same EOF | `results-C1/{system.log,alloc-read.json,session.log}` |
| C2 | 3 MiB | 200 MiB | 256 MiB | 3 × `… out of 209715200` | [1, 1, 1] | 209,715,216 B; same stack | 1 event, same EOF | `results-C2/…` |
| C3 | 6 MiB | 200 MiB | 256 MiB | 3 × `… out of 209715200` | [1, 1, 1] | 209,715,216 B; same stack | 1 event, same EOF | `results-C3/…` |
| C4 (control) | 3 MiB | 200 MiB | 64 MiB | 3 × `IOException: Corrupt value length 209715200 encountered, as it exceeds the maximum of 67108864, …` at `AbstractType.read(AbstractType.java:595)` | [0, 0, 0] | no `byte[]` ≥ 50 MiB in the whole read session (largest `byte[]` 1.0 MB) | 0 events, same `Corrupt value length` | `results-C4/…` |

Further readings:
- **Where the EOF is thrown (C1–C3, all 12 failures):** `TrackedDataInputPlus.checkCanRead(TrackedDataInputPlus.java:187)` ← `TrackedDataInputPlus.readFully(:117)` ← `ByteArrayAccessor.read(ByteArrayAccessor.java:103)` ← `AbstractType.read(:599)` ← `Cell$Serializer.deserialize(:339)` ← `UnfilteredSerializer.readSimpleColumn(:652)`. `:103` is the `readFully` that follows `new byte[length]` at `:102` (`raw/results-C1/system.log:553-570`; the analyzer counts 4 of 4 such entries per config).
- **Sanity read (uncorrupted, after flush), every config:** `byte[]` events of exactly S + 16 B on the `ByteArrayAccessor.read:102` stack, 3,145,744 B (C1, C2, C4) and 6,291,472 B (C3). Each `SELECT v` returned 1 row (`session.log` `SANITY_READ … rc=0 rows=1`).
- **Patch:** in every config `PATCH … at 26`, `e0300000` or `e0600000` → `e6400000` or `ec800000`, with the file length unchanged (3,145,759 B, or 6,291,487 B for C3; `session.log`, `sstables.txt`). One sstable per config. Commit-log replay before the reads was `0 replayed mutations`.
- **Node stays up:** "node still up after reads" in every config. `disk_failure_policy=ignore` and the config's `max_value_size` are in the startup config dump (`config-dump.txt`).
- **GC log (secondary):**
  - C2 and C3: the third 200 MiB allocation triggered `Pause Young (Normal) (G1 Humongous Allocation)`, taking the heap from 773M to 479M and from 769M to 481M of 1024M (`gc-C2-read.log`, `gc-C3-read.log`).
  - C1 and C4: no humongous-allocation pause.

### 4.2 Conclusion and logic

1. **Validity: valid.**
   - **Unit tier.** The check was reached in every corrupt row (EOF thrown, `L < V`). The instrument gave the known answer (32 MiB + 16 B) [observed: `raw/unit/check/results.txt`]. The well-formed row shows the measured allocation is the value array [observed: r6].
   - **Cluster tier, settings held.** Every live command line has `-Xms1G -Xmx1G`, G1 and the JFR profile recording [observed: `cmdline-*.txt`]. The table has compression disabled [observed: `schema.txt`]. There is one sstable per config and the patch assertion passed [observed: `session.log`].
   - **Cluster tier, path exercised.** The read reached deserialization of the patched value: the EOF stack ends in `ByteArrayAccessor.read:103` [observed: `system.log`].
2. **Readings: nothing unusual.**
   - Every B2f assertion passed and the 26 cluster checks passed [observed].
   - r6 repetition 1 allocated 0.27 MiB more than repetitions 2 and 3. That is first-call allocation in the well-formed path, and the median is used per B2i.2 [observed].
   - The roughly 900 B above V in r1–r4 is the exception and its message [inferred: absent in r6, which throws nothing].
3. **Matched row.**
   - **Unit: B2g row 1, Confirmed.** "A ≈ V for every L < V, EOFException thrown, and the control (max = 8 MiB) shows A < 1 MiB" [observed: A = 16.0009 MiB for L = 64 B and 1 MiB at V = 16 MiB; A = 64.0009 MiB for L = 64 B and 16 MiB at V = 64 MiB; control 2,408 B].
   - **Cluster: B3g row 1, Confirmed** (as made exact by B3i.4). Each of C1–C3 shows one ≈ V `byte[]` per read with the `ByteArrayAccessor.read` stack, the `EOFException … out of V` is logged, and C4 shows none [observed: `analyze_cluster.out`].
4. **Excluded rows.**
   - Unit row 2, "A grows with L or stays ≤ L": ruled out. A is identical (to 8 B) across L = 64 B, 1 MiB and 16 MiB at fixed V, and A ≫ L at L = 64 B [observed].
   - Unit row 3, "A ≈ 0 everywhere": ruled out by r1–r4, r6 and the instrument check [observed].
   - Unit row 4, "no EOF when L < V": ruled out [observed].
   - Unit row 5, "control shows A ≈ V": ruled out, 2,408 B [observed].
   - Unit catch-all (B2i.3): no mismatch [observed].
   - Cluster row 2, "no large allocation but EOF logged": ruled out, 9 of 9 EOF reads have the event [observed].
   - Cluster row 3, "C3 differs from C2 in proportion to L": ruled out. Both are 209,715,216 B [observed].
   - Cluster row 4, "no EOF and no Corrupt value length": ruled out [observed].
   - Cluster row 5, "C4 still allocates ≈ 200 MiB": ruled out, 0 events ≥ 50 MiB [observed].
   - Cluster row 6, "no JFR events at all": ruled out. There are 29–31 outside-TLAB events per read session, and the sanity events are present [observed].
   - Cluster catch-all (B3i.5): no mismatch [observed].
5. **Observed vs. inferred.** The conclusion's inferred statements:
   - (i) "Allocation" equals heap demand. The array is garbage at once, so resident heap after the read is not measured (gap named in B2d and B3d). The G1 humongous pauses in C2 and C3, with the heap at 769–773M of 1024M, show the arrays occupied real heap until collected, but this is secondary.
   - (ii) Each read's event belongs to that read. This rests on the time window: each event falls within its cqlsh call and on `ReadStage-2`, and only one sstable and one row exist.
   - (iii) The unit-tier extra about 900 B comes from the exception.
6. **Deviations and gaps.**
   - Harness fixes #2–#4 in §3; the C3 first attempt was aborted before any action.
   - The cluster tier has two L values.
   - The optional `SELECT k` read also allocated V and threw the same EOF, so the value was read, not skipped. B3h expected "no large allocation"; that expectation was wrong for this query. It is supporting evidence only, and it agrees with B1: even a query that does not ask for `v` allocates V. The cause is inferred, not verified at runtime: the column filter of this query treats `v` as queried, so `DeserializationHelper.canSkipValue` (`:109-112`) is false.
   - Each config ran once. There was no run 2.
   - The node is aarch64.
7. **Core question.** The per-row limit does **not** cap memory.
   - The heap allocated while reading a row follows the encoded value length V (16 → 64 MiB in the unit tier, 100 → 200 MiB on the node) and is the same whatever the limit L is (64 B, 1 MiB or 16 MiB in the unit tier; about 3 vs 6 MiB on the node) [part 3].
   - The limit does fire on every one of these reads, but only in `readFully`, after `new byte[V]` has run [part 1, the stack].
   - On the same input and instruments, `max_value_size < V` removed the allocation entirely [part 3, controls].
   - The limit is therefore a framing/corruption guard on bytes consumed from the input, not a memory or disk cap. The claim holds.

**Conclusion (one line):** unit: B2g row 1, Confirmed, does not cap. Cluster: B3g row 1 (B3i.4), Confirmed, does not cap. Flags: resident heap not measured (allocation is the observable); two cluster L values; the B3h `SELECT k` expectation did not hold (supporting only).

## 5. Self-check of run 1 (AI)

### 5.1 Check of run 1's conclusion

The raw files were re-read with a tool other than the analyzer, before the bulk data was deleted from the node:
- **JFR text format.** `jfr print --events jdk.ObjectAllocationOutsideTLAB rec-<cfg>.jfr`, `byte[]` sizes counted:
  - C1: 4 × "100.0 MB", 12 × "1.0 MB"
  - C2: 4 × "200.0 MB", 13 × "1.0 MB"
  - C3: 4 × "200.0 MB", 8 × "1.0 MB"
  - C4: 13 × "1.0 MB" and nothing larger
  - `jfr summary`: 30, 30, 31 and 29 events of that type.

  In each of C1–C3 that is 3 `SELECT v` reads plus 1 `SELECT k`, which agrees with the JSON analysis.
- **Patched bytes.** C4's `Data.db` was read back: marker at offset 30, bytes `ec800000` at offset 26, length 3,145,759.
- **GC logs.** `G1 Humongous Allocation` pause counts were C1 0, C2 4, C3 4 and C4 0 (4 log lines = 2 pauses × 2 lines); `Humongous regions` reached 26 and 39.

The following were opened by hand: `raw/results-C1/system.log` (lines 534–570, the full EOF stack), `raw/results-C4/system.log` (the `Corrupt value length` stack at `AbstractType.java:595`), `raw/unit/run1/results.txt` (all 27 lines) and `raw/results-C1/alloc-write.json` (the sanity-read stacks).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cmdline-read.txt` (C1–C4) has `-Xms1G -Xmx1G`, `-XX:+UseG1GC` and the JFR option. `schema.txt` has `compression = {'enabled': 'false'}`. `session.log` has the `PATCH` line and `0 replayed mutations`. Unit `instrumentKnownAnswer`: 33,554,448 B. |
| 2. Readings | yes | `results.txt` rep lines agree with the medians quoted. The r6 rep-1 outlier is recorded. |
| 3. Matched row | yes | The JFR text tool gives the same 100.0 and 200.0 MB counts as the JSON. C2 and C3 sizes are identical. C4 has no large `byte[]`. The C1 EOF stack shows `ByteArrayAccessor.java:103` below `checkCanRead:187`. |
| 4. Excluded rows | yes | Each exclusion cites a reading that the text-format re-read reproduces. No Refuted row applies. |
| 5. Observed vs. inferred | yes | The list is complete; (i) is named as a gap in the design itself. |
| 6. Deviations and gaps | yes | The harness fixes, the aborted C3 attempt (nothing ran: `results-C3-attempt1-portcheck/session.log` ends at the port check), the `SELECT k` miss and the arch are all recorded. |
| 7. Core question | yes | B1's refuted-if ("allocation follows L" / "the limit stops the read before allocation") is excluded by r1–r4 and C2 vs C3, and by the throw site below the allocation. The positive control moved in both tiers. |

### 5.2 Run 2?

**No**, decided 2026-11-24. Both tiers are deterministic: three identical repetitions per unit row, and 3 of 3 identical events per cluster config. The throw site was read from the stack, not inferred. The result is the negative estimate's expected outcome, with a working positive control. A second run of the same design would not settle the one named gap (resident heap).

## 6. Run 2 (fresh AI session, optional)

Not done.

## 8. Verdict (AI)

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap; both tiers Confirmed).

**Claim tested (B1):** "The per-row limit set at `TrackedDataInputPlus.java:52` (= `rowSize`) does not bound the heap allocated while deserializing a row. When an encoded cell length V exceeds the row's size L, the node still allocates a `byte[V]` before the limit raises `EOFException`. The allocation follows V and not L. `max_value_size < V` prevents the allocation (positive control)." "Confirmed" below means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**: B2g row 1. A = 16.0009 MiB at L = 64 B and 1 MiB (V = 16 MiB); 64.0009 MiB at L = 64 B and 16 MiB (V = 64 MiB); EOF in every corrupt row; control 2,408 B with `Corrupt value length`; well-formed 16.0001 MiB; `testLimitFires` passes. | does not cap | run 1 + self-check | 2026-11-24 |
| Cluster | **Confirmed**: B3g row 1 (B3i.4). One `byte[]` of V + 16 B per corrupt read (104,857,616 B in C1; 209,715,216 B in C2 and C3, 3 of 3 each) on `ByteArrayAccessor.read:102`, then `EOF after 0 bytes out of V` thrown below it at `:103` → `checkCanRead:187`. C2 = C3 although L doubles. C4: none, `Corrupt value length 209715200 … 67108864` instead. | does not cap | run 1 + self-check | 2026-11-24 |

**Positive control:** `max_value_size` below V. Same input, same instruments, a cap that binds before allocation: unit 8 MiB (A drops from 64 MiB to 2.4 KB), cluster 64 MiB (C4: no ≥ 50 MiB `byte[]`, versus 209,715,216 B in C2).

**Nuance:**
- The limit is real and active. It fires on every corrupt read and turns it into a `CorruptSSTableException`, so it is a framing/corruption guard on the bytes consumed for one row.
- The only bound on the transient heap of a corrupt length is `max_value_size`, default 256 MiB per value.
- Even a query that does not select the value (`SELECT k`) allocated V on this path.

**Feedback filed:**
- The case file's section D "Stage-4 feedback" is filled. The case file is outside the repo, so there is no commit. sha256 of the file with D filled: `5bd5a7595ccd5387e5617cf5e429d58fb98bb27a5ee7965e7531013d8052a335`.
- The audit amendments B2i and B3i are dated 2026-11-24.
- B1, B2f, B2g, B3f and B3g are unchanged.
- Nothing was written in the repository: no `_INDEX.md`, HANDOFF or results-folder edit. Filing into the repo is left to the workflow.

**Other findings for stage 3:**
1. B3h's `SELECT k` expectation (value skipped) is wrong for this query: the value is deserialized.
2. The cluster tier has only two L values.
3. The `max_value_size` throw is reported at `AbstractType.java:595` (the statement starts at `:594`). Cosmetic.

**Left on the node (`ms0640`):**
- Nothing running: no `CassandraDaemon`, no JUnit JVM; ports 17100, 19142 and 17299 free.
- Files: `/mydata/jingsong-cass-s4/o122/` (9.9 MB: `harness/`, `logs/`, `unit/`, `cluster/results-*`, `cluster/gc-*.log`, `cluster/*.out`, `cluster/setup.log`).
- The source copy, node tree, data, commit log, JFR recordings and `ins.cql` were deleted. The corrupted sstable was not copied anywhere.
- Lock `/mydata/s4/NODE-LOCK` released at 06:37Z.
- `/mydata/s4/cassandra-base` was not modified.

## Time spent (UTC, 2026-11-24)

| Step | Start | End | Minutes | Remarks |
|---|---|---|---|---|
| lock + reading | 06:16 | 06:17 | 1 | lock acquired 06:16:09Z |
| audit | 06:17 | 06:19 | 2 | source spot-checks, amendments B2i and B3i, freeze 06:18:52Z, `cp -a` of the base (5 s) |
| unit harness + check | 06:19 | 06:20:35 | 2 | known-answer instrument run (45 s) |
| unit run 1 | 06:20:39 | 06:21:23 | 1 | one `ant testsome`, 8 tests |
| cluster harness + setup | 06:21 | 06:23 | 2 | yaml and env edits verified by parsing |
| cluster run 1 | 06:23:08 | 06:36:43 | 14 | C1 3 min, C2 3 min, C3 attempt 1 aborted at the port check, harness fix, C3 3.5 min, C4 3 min; analyzer fixes in parallel |
| self-check + cleanup | 06:36 | 06:38 | 2 | JFR text re-read, patched bytes, GC logs; bulk data deleted; lock released |
| report | 06:38 | 06:45 | 7 | results file, case file section D |

Total wall time from lock to report: about 30 minutes.
