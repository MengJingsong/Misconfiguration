# cql-row-limit-incrementRowCount-rowsCounted--autonomous — recheck claim (2026-11-17) — stage-4 results  <!-- file: results/cql-row-limit-incrementRowCount-rowsCounted--autonomous--recheck-2026-11-17.md -->

> **Case:** [`cql-row-limit-incrementRowCount-rowsCounted--autonomous`](../../stage3-ai-deep-read/cases/cql-row-limit-incrementRowCount-rowsCounted--autonomous.md), section "Recheck — enforcement properties (guided, 2026-11-17, blind)", its **Stage-4 claim to add**; design in the case file's section "Stage-4 design for the recheck claim (2026-11-17)".
>
> **Status:** verdict filed (2026-11-17): run 1 done and self-checked; no run 2
>
> **Outcome class:** unchanged — true negative (the case file's estimate `negative`; this recheck run, like the 2026-10-27 run, finds `does not cap`; [definition](../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous file, recheck claim. "§9a" below means the design section's S6 (prediction) and S7 (conclusions); "§9b–§9e" means its S1–S5; the case file's feedback section is its section D. The earlier run of this case file (B2/B3, 2026-10-27) is [`cql-row-limit-incrementRowCount-rowsCounted--autonomous.md`](cql-row-limit-incrementRowCount-rowsCounted--autonomous.md) and is not redone here. This run has one tier (cluster: a real node); a unit tier is `n/a` because the claim is about a node's heap during a CQL read (coordinator and replica), which the earlier unit tier already covered for the counter itself.

**Relative links** are written for this file's place in `results/`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Case file at repository HEAD `2f76b847` (committed there in `c9022eb9`, with the recheck section) plus the appended section "Stage-4 design for the recheck claim (2026-11-17)" (uncommitted; the orchestrator commits). Frozen version: `sed -n '/^## Stage-4 design for the recheck claim (2026-11-17)/,$p' <case file> \| git hash-object --stdin` = **`d1174f2004c24cfcf03796d3e704d430d33f709a`** (sha256 of the same text `97c19539bf0f490ec9208e48e3b68df4e67473a58137c61f0573f2586063d124`), recorded before any query of this run. The section is the last one of the file; the only later change to the case file is one line in section D (feedback), above it, so the hash stays reproducible. |
| **Harness** | `harness/cql-row-limit-incrementRowCount-rowsCounted--autonomous--recheck-2026-11-17/` (`probes.btm`, `rc-run.py`, `client.py`, `Jmx.java` copied from the earlier harness, `analyze.py`, `setup.sh`, `README.md`); uncommitted (the orchestrator commits); md5 of the files run in `run1/harness.md5`. |
| **Tiers and values** | Cluster tier only (one node, RF 1, CL ONE, 8 GiB heap): LIMIT N in {32, 128, 512} x W in {16 KiB, 128 KiB, 1 MiB}, no LIMIT (600 rows) at 128 KiB, first page of fetch size 128 and 512 at 1 MiB, all at shipped guardrails (lifetime U); positive control `local_read_size_fail_threshold: 40MiB` (lifetime C) on 7 arms. Unit tier `n/a`: the counter itself was run in the earlier unit tier (B2, Confirmed); the recheck claim is about a node's heap. |
| **Audit bottom line** | **Ready** — 2026-11-17 (the design was written by this session from the one-sentence claim, then audited; two changes were made before the freeze and before any query: the cited `SelectStatement` line range corrected to `:1004-1014`, and a no-LIMIT arm added for the default `NO_LIMIT`). |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | The constraint is a row count (`rowsCounted`, case A2); the claim is about the heap bytes a row-limited read holds (design "How this verifies", H1-H4). Accepted: the point of a negative claim is that the count does not bound bytes. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met | S2: N in {32, 128, 512} plus no LIMIT (the default `NO_LIMIT`, 600 rows) at 128 KiB, and page size 128 / 512; W in three values at fixed N. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | S4: live-object histogram totals (full GC) during pauses at the replica's and the coordinator's end of the read (H_R, H_C), allocation A as secondary; rows returned as the counter. Gap named: the encoded response frame and the client copy are not seen; the held set between probes is not seen. |
| A. Core question | usage driven to the limit and past it | Met | Every partition has 600 rows > the largest N (S3), so every LIMIT and page stops on the count; the control's threshold (40 MiB) lies inside the N x W range (8 to 512 MiB). |
| A. Core question | positive control (negative-estimate file) | Met | S2/S6 R5: `local_read_size_fail_threshold` 40 MiB on the same tables and instruments, a byte cap Confirmed in case `local_read_size_fail_threshold-addSize-failBytes--guided` and in the earlier cluster tier of this case. |
| B. Logic | each step says what it establishes | Met | "How this verifies the claim": test -> logic per hypothesis; S5 steps. |
| B. Logic | prediction stated in numbers or a clear relation | Met | S6 R1-R5 with numeric bounds; model bands separately. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | S7: Confirmed; partial (H2 or H3 not shown); Refuted (flat or below 0.5 x N x W); control fails; counter fails; Invalid; anything else. "Counter capped but resource grows" is the Confirmed row of a negative claim. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Rows returned = N and the PC probe's row count (the count stop fired) next to H_C following N x W; the control's PA probe and client error show the byte cap's disallow branch fired. |
| B. Logic | alternative explanations and their controls | Met | Instrument artefact -> positive control (R5); baseline drift -> B2 - B noise check; histogram outside the pause -> `inside` flag per probe; GC timing -> forced full GC per reading. |
| C. Specific | a human can follow it from the intro and §9a | Met | The "How this verifies" block and S7. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | S1-S5 give paths, commands, rule points, yaml lines and order; the harness implements them. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | S2-S5 (seed 75, 3 repetitions, 8 s pauses, 25 ms allocation sampling, first-trigger checks with exit 3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc75: built `cassandra-base`, JDK 11.0.33, Byteman 4.0.20 in `build/lib/jars`, driver zip in `lib/`, `systemd-run --user --scope` with memory delegated (checked before the design). The three rules type-check with Byteman's `TestScript` against the built jars (`run1/bmcheck.txt`). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Data 720 MB on `/mydata` (714 GB free); largest predicted live set about 1.3 GiB of the 8 GiB heap; scope budget 12 GiB, swap 0; about 30 minutes of queries. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `DataLimits.java:509-510`; `ReadResponse.java:197-201` (`LocalDataResponse.build`); `BufferedDataOutputStreamPlus.java:75-77` (heap `allocate`); `DataOutputBuffer.java:158-171` (growth, 64 MiB doubling threshold, `CassandraRelevantProperties` `DOB_DOUBLING_THRESHOLD_MB` 64); `ByteBufferUtil.java:444-451` (copying read); `SelectStatement.java:427-429`, `:1004-1014` (corrected from `:1004-1013`); `ReadCommand.java:713-723` (local read size abort); `StorageProxy.java:2197-2212` (`LocalReadRunnable` -> `createResponse`). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Cite `SelectStatement.java:1004-1014` (the `build()` call is `:1014`) | Applied 2026-11-17 before the freeze | Wrong end line. |
| 2 | Add the default `NO_LIMIT` as an arm | Applied 2026-11-17 before the freeze (L(none, 128 KiB)) | Group A asks for the default among the knob values. |
| 3 | The OOM sub-claim (H5) needs a heap smaller than one read's held set | Left for stage 3 / a later run | This run is a measurement inside a budget by instruction; H5 is stated as an extrapolation only. |
| 4 | Coordinator and replica are one JVM; a two-node ring would separate them | Left (not needed for the claim's "at the same time") | On one node the two copies are told apart by the two probe points. |

**Agreement criteria** — not applicable (no run 2, §5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-17: setup 10:47, load lifetime 10:47-10:49, instrument check K 10:49-10:52, lifetime U 10:56-11:17, lifetime C 11:18-11:31 (MST, node clock) | not done |
| Node (CloudLab name and type) | `pc75` = `node4.jason92-326528.misconfiguration-pg0.cloudlab.umass.edu`, x86_64, 40 cores, 125 GiB, 8 GiB swap on (excluded from the node by `MemorySwapMax=0`) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.33 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 (not used: the tree was already built) | |
| Local source copy | `cp -a /mydata/s4/cassandra-base /mydata/s4/rowlim-rc/tree` (`copy-source.sh` copy of `systems/cassandra/source/`, tag `cassandra-5.0.9`, `ant build-test` done on 2026-11-17; `git status` clean); repository HEAD `2f76b847` | |
| Case-file commit / harness commit | case file `c9022eb9` + the uncommitted design section (hash in §1); harness uncommitted, md5s in `run1/harness.md5` (the files lifetimes K, U and C ran; `setup.sh` and the load lifetime ran the first `rc-run.py`, see §3) | |
| Storage for node data | `/mydata/s4/rowlim-rc/node/` on the node's local `/mydata` (ext4, 714 GB free); data 718 MB (`run1/load/session.log`) | |
| Node process and budget | `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0 bin/cassandra -f`, `MAX_HEAP_SIZE=8G` (`-Xms8G -Xmx8G`, G1, `AlwaysPreTouch`); highest sampled scope `memory.current` 9.51 GiB (U) and 9.00 GiB (C), heap pre-touch plus page cache; `memory.events` `oom 0; oom_kill 0` in K, U and C | |
| Full logs (path, outside the repo) | `pc75:/mydata/s4/rowlim-rc/logs/` (3.6 MB: `setup.log`, `bmcheck.txt`, `summary.txt`, `{load,K,U,C}/` with `session.log`, `queries.jsonl`, `histos.txt`, `alloc.csv` 42 567 / 24 516 samples, `memory.csv`, `marker.txt`, GC logs); node logs `pc75:/mydata/s4/rowlim-rc/node/logs-*` | |

## 3. Runbook defects

No step of the design (S1-S5) had to change. Two harness defects were found and fixed before any reading (the readings come from lifetimes U and C, which ran the fixed harness):

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | load lifetime | S5 (1)-(2), node stop | `bin/cassandra -f` writes no pidfile (only its background mode does), so `rc-run.py` found no pid and would have stopped the load node with SIGKILL after a 60 s wait | The load node was drained (`nodetool drain`, exit 0) and stopped with SIGTERM by hand after the load had finished (`count(*)` = 600 for all three tables, data flushed and compacted); `node_pid()` now finds the daemon by its command line | 2026-11-17, harness only | none (design unchanged) |
| 2 | load lifetime | S4, scope memory | `memory.events` was read after the scope had gone | read before the stop; K, U and C log `oom_kill 0` | 2026-11-17, harness only | none |

## 4. Run 1

**Scope:** the cluster tier, every arm of S2: lifetime U 12 arms x 3 repetitions (36 queries; plus 12 warm-ups and one trigger query), lifetime C 7 arms x 3 (21; plus 7 warm-ups and one trigger), instrument check K (2 queries, not readings). **Command log:** `cql-row-limit-incrementRowCount-rowsCounted--autonomous--recheck-2026-11-17/run1/` (`setup.log`, `bmcheck.txt`, `harness.md5`, `summary.txt` = `analyze.py` output with the EXPECTED lines, `load/session.log`, `{K,U,C}/session.log`, `queries.jsonl`, `histos.txt` (the top classes and total of every histogram), `marker.txt` (every probe line), `gc-heap-inspection.txt` (the GC log's forced-GC lines), `cassandra.yaml.<life>`, `system-log-grep.txt`, `alloc-memory-tail.txt`).

Notation: N x W = rows x value width (payload); H_R, H_C, H_A = live heap during the PR / PC / PA pause minus the live heap just before the query (histogram totals), median of 3; A = allocated bytes of the query (secondary).

### 4.1 Readings

**Cluster tier, lifetime U (shipped guardrails)** — `run1/summary.txt` ARM U lines; every value is the same in all 3 repetitions to within 0.2 MiB except where noted.

| Arm | N x W | Rows returned (3 reps) | H_R | H_C | H_C - H_R | H_C / (N x W) | Replica buffer: serialized size / capacity (PR probe) | A (secondary) |
|---|---|---|---|---|---|---|---|---|
| L(32, 16 KiB) | 0.5 MiB | 32, 32, 32 | 0.7 MiB | 1.2 MiB | 0.5 MiB | 2.49 | 0.5 / 0.5 MiB | -4.9 MiB (negative: thread exits, see 4.2 part 2) |
| L(128, 16 KiB) | 2 MiB | 128 x 3 | 2.2 MiB | 4.3 MiB | 2.0 MiB | 2.13 | 2.0 / 2.0 MiB | -17.1 MiB |
| L(512, 16 KiB) | 8 MiB | 512 x 3 | 16.2 MiB | 24.3 MiB | 8.1 MiB | 3.04 | 8.0 / 8.0 MiB | 28.0 MiB |
| L(32, 128 KiB) | 4 MiB | 32 x 3 | 4.2 MiB | 8.2 MiB | 4.0 MiB | 2.06 | 4.0 / 4.0 MiB | -16.6 MiB |
| L(128, 128 KiB) | 16 MiB | 128 x 3 | 16.2 MiB | 32.3 MiB | 16.0 MiB | 2.02 | 16.0 / 16.0 MiB | 34.3 MiB |
| L(512, 128 KiB) | 64 MiB | 512 x 3 | 64.3 MiB | 128.3 MiB | 64.1 MiB | 2.01 | 64.0 / 64.0 MiB | 202.2 MiB |
| L(none, 128 KiB) (default `NO_LIMIT`) | 75 MiB | 600 x 3 | 96.0 MiB | 171.1 MiB | 75.1 MiB | 2.28 | 75.0 / 96.0 MiB | 322.3 MiB |
| L(32, 1 MiB) | 32 MiB | 32 x 3 | 32.2 MiB | 64.2 MiB | 32.0 MiB | 2.01 | 32.0 / 32.0 MiB | 43.4 MiB |
| L(128, 1 MiB) | 128 MiB | 128 x 3 | 144.2 MiB | 272.2 MiB | 128.0 MiB | 2.13 | 128.0 / 144.0 MiB | 532.2 MiB |
| L(512, 1 MiB) | 512 MiB | 512 x 3 | 729.3 MiB | 1 241.4 MiB | 512.1 MiB | 2.42 | 512.0 / 729.0 MiB | 3 073.2 MiB |
| P(128, 1 MiB) first page | 128 MiB | 128 x 3 | 144.0 MiB | 272.0 MiB | 128.0 MiB | 2.13 | 128.0 / 144.0 MiB | 535.4 MiB |
| P(512, 1 MiB) first page | 512 MiB | 512 x 3 | 729.0 MiB | 1 241.1 MiB | 512.1 MiB | 2.42 | 512.0 / 729.0 MiB | 3 060.8 MiB |

| Derived (S6) | Reading | Evidence |
|---|---|---|
| R1: rows returned = N, PC logs N rows | 36 of 36 queries | `summary.txt` EXPECTED R1 |
| R2: width slope (H_C(N, 1 MiB) - H_C(N, 16 KiB)) / (N x (1 MiB - 16 KiB)) | 2.127 (N = 128), 2.415 (N = 512) | EXPECTED R2 |
| R2: count slope (H_C(512, W) - H_C(32, W)) / (480 x W) | 2.002 (128 KiB), 2.452 (1 MiB) | EXPECTED R2 |
| H_C(512, 1 MiB) / H_C(512, 16 KiB) | 51.0 (payload ratio 64; refuting bound < 4) | REFUTE-CHECK |
| R3: H_R / (N x W) and (H_C - H_R) / (N x W), large arms | 1.00 to 2.03 and 1.00 to 1.01 | EXPECTED R3 |
| R4: H_C page / H_C limit | 0.999 (N = 128), 1.000 (N = 512) | EXPECTED R4 |
| First-trigger check (U) | L(128, 1 MiB): 128 rows, H_C 285.5 MB (>= 64 MiB) | `U/session.log` |
| Noise B2 - B (36 queries) | median +0.23 MiB, range 0.00 to +0.23 MiB | `summary.txt` |
| Histograms inside their pause | 72 of 72 (PR and PC) | `summary.txt` "inside R/C/A 3/3/0" per arm |
| Cross-check: GC log after-size of the forced full GCs | largest 1 334 MiB in U (baseline about 80 MiB + H_C 1 241 MiB), 164 MiB in C (humongous objects counted in whole 16 MiB regions; §5.1 part 3) | `U/gc-heap-inspection.txt`, `C/gc-heap-inspection.txt` |
| `system.log` ERROR / `OutOfMemoryError` / scope `oom_kill` | 0 / 0 / 0 | `U/session.log` |

**Cluster tier, lifetime C (`read_thresholds_enabled: true`, `local_read_size_fail_threshold: 40MiB`)** — `run1/summary.txt` ARM C lines

| Arm | N x W | Client result (3 reps) | Counted bytes at abort (PA probe message) | H_A (live heap at the abort) | H_C | A (secondary; U value) |
|---|---|---|---|---|---|---|
| L(128, 1 MiB) | 128 MiB | `ReadFailure` code 1300, "loaded over 41951752 bytes ... READ_SIZE", 3 of 3 | 41 951 752 | 65.2 MiB | — (PC did not fire) | 116.2 MiB (532.2) |
| L(512, 1 MiB) | 512 MiB | same, 3 of 3 | 41 951 752 | 65.2 MiB | — | 108.0 MiB (3 073.2) |
| L(512, 128 KiB) | 64 MiB | same, 3 of 3 | 42 012 232 | 64.4 MiB | — | 118.8 MiB (202.2) |
| P(128, 1 MiB) first page | 128 MiB | same, 3 of 3 (the paged command reads as `LIMIT 128`) | 41 951 752 | 65.2 MiB | — | 134.2 MiB (535.4) |
| L(32, 1 MiB) | 32 MiB | 32 rows x 3 | — | — | 64.2 MiB (U 64.2) | 70.0 MiB (43.4) |
| L(128, 128 KiB) | 16 MiB | 128 rows x 3 | — | — | 32.3 MiB (U 32.3) | 1.2 MiB (34.3) |
| L(512, 16 KiB) | 8 MiB | 512 rows x 3 | — | — | 24.3 MiB (U 24.3) | -1.5 MiB (28.0) |

| Derived (S6 R5) | Reading | Evidence |
|---|---|---|
| H_A max / min over the four abort arms | 1.01 (64.4 to 65.2 MiB) while N x W spans 64 to 512 MiB | EXPECTED R5 |
| H_A <= 100 MiB | all four | EXPECTED R5 |
| Pass arms H_C (C / U) | 1.000, 1.000, 1.000 | EXPECTED R5 |
| First-trigger check (C) | L(128, 1 MiB) fails with READ_SIZE, PA fired | `C/session.log` |
| After an abort | the replica answers with an empty response: the PR probe fires a second time with a 2-byte response in a 128-byte buffer (H_R 0.2 MiB) | `C/marker.txt` |
| Noise B2 - B (21 queries) | median +0.23 MiB | `summary.txt` |
| `system.log` ERROR / `OutOfMemoryError` / scope `oom_kill` | 0 / 0 / 0 | `C/session.log` |

**Instrument check K** (`run1/K/`, not readings): L(32, 128 KiB) and P(128, 1 MiB): both probes fired, all histograms inside the pause, rows 32 and 128.

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit fired in every U query: rows returned and the PC probe's row count equal N (600 for no LIMIT) in 36 of 36 [observed: `summary.txt` EXPECTED R1; `U/marker.txt`]. Both first-trigger checks held [observed: `U/session.log`, `C/session.log`]. Fixed settings: shipped guardrail lines untouched in U (the yaml changes are the 11 lines of S1: directories, `num_tokens`, caches, timeouts, `auto_snapshot`) and `read_thresholds_enabled: true`, `local_read_size_fail_threshold: 40MiB` added only in C [observed: `U/cassandra.yaml.U`, `C/cassandra.yaml.C`]; heap `-Xms8G -Xmx8G`, the Byteman agent and the scope limits [observed: `U/system-log-grep.txt` JVM arguments, `U/session.log` "memory.max 12884901888 memory.swap.max 0"]; one client at a time [inferred: the driver runs one query and waits]. Every histogram ended inside its probe's pause (72 of 72 in U; in C 12 of 12 PA, 21 of 21 PR (9 pass-arm responses and 12 empty responses after an abort) and 9 of 9 PC) and B2 - B is 0.23 MiB at most [observed: `summary.txt`]. No `OutOfMemoryError`, no ERROR, `oom_kill 0` [observed: `U/session.log`, `C/session.log`].
2. **Readings** — (a) The readings are nearly exact repeats: every arm's three repetitions agree to within 0.2 MiB [observed: `summary.txt` rep lines]. (b) L(512, 16 KiB) holds 8 MiB more at PR than its 8 MiB buffer (H_R 2.03 x N x W): the extra is `int[]` arrays (`[I` grows from 16.1 to 24.5 MB in the PR and PC histograms and is back at 16.1 MB in B2), transient and not payload [observed: `U/histos.txt` "L512-w16k rep1 run"]; what owns them was not traced [inferred]. It is a model-band miss (H_R / capacity 2.03), not part of R1-R5. (c) Allocation A is negative for the four smallest arms (-17 to -5 MiB): the JMX counter sums live threads only and loses the counts of threads that exit, as in the earlier run; A is secondary and not used [observed: `summary.txt`]. (d) A of L(32, 1 MiB) is 1.36 x N x W, under the model band of 2 to 8 [observed]; the 128 and 512-row 1 MiB arms are 4.2 and 6.0 x.
3. **Matched row** — S7 row 1, **Confirmed**: "R1, R2, R3, R4 and R5 hold". R1: 36 of 36 queries return N rows [observed: EXPECTED R1]. R2: H_C >= 0.9 x N x W for all 10 large arms (2.01 to 3.04); width slopes 2.13 and 2.42; count slopes 2.00 and 2.45, all >= 0.9 [observed: EXPECTED R2]. R3: H_R >= 0.9 x N x W (1.00 to 2.03) and H_C - H_R >= 0.8 x N x W (1.00 to 1.01) for all 10 [observed: EXPECTED R3]. R4: page / limit 0.999 and 1.000 [observed: EXPECTED R4]. R5: the four abort arms fail with READ_SIZE on 3 of 3, PA fires and PC does not, H_A 64.4 to 65.2 MiB (<= 100 MiB, max/min 1.01), the three pass arms return N rows with H_C exactly as in U [observed: EXPECTED R5].
4. **Excluded rows** — **Refuted** (flat or below 0.5 x N x W): H_C(512, 1 MiB) / H_C(512, 16 KiB) = 51.0, not < 4; no arm has H_C < 0.5 x N x W [observed: REFUTE-CHECK]. Partial H2 row: R3 holds. Partial H3 row: R4 holds. Control-fails row: R5 holds. R1-fails row: R1 holds. **Invalid**: no probe missing, no histogram outside its pause, noise 0.23 MiB, no OOM, no `oom_kill` [observed: INVALID-CHECK none]. "Anything else": not needed, row 1 matches.
5. **Observed vs. inferred** — Inferred: (i) the histogram total during a pause minus the total just before is the heap the read holds at that point: other activity is quiet (B2 - B <= 0.23 MiB; the forced GC's after-size in the GC log agrees with the histogram totals to about 1 % for the largest arms; it rounds humongous objects up to whole 16 MiB regions), but the difference is not attributed object by object; (ii) H_R is the replica's serialized response buffer: H_R equals the buffer capacity the PR probe logs to within 0.1 to 6 % for all arms but L(512, 16 KiB) (part 2b); (iii) H_C - H_R is the coordinator's copy (`ResultSet` cell values copied by `ByteBufferUtil.read`): it equals N x W to within 1 % in every large arm, and the replica's buffer is still live then (H_C = H_R + N x W); (iv) H5 (OOM above the free heap) is extrapolated, not observed: at the measured 2.0 to 2.4 x N x W held, one read of about 3.3 GiB of payload would hold more than this run's 8 GiB heap, and about 6.5 GiB more than a 15.5 GiB default heap; the node was never driven there.
6. **Deviations and gaps** — One node: coordinator and replica are one JVM, told apart by the two probe points, not by two processes. The held set between the probes, the coordinator's encoded response frame (after PC) and the client's copy are not measured, so the peak can be higher than H_C. The pauses (8 s at each probe) and the 60 s read timeouts are instrumentation; they keep the read's objects live but do not add to them. H5 is not run (design). The load lifetime's node was stopped by hand (§3 #1), before any reading.

7. **Core question** — Usage does not follow the row limit alone: at a fixed N the heap a read holds rises with the row width in proportion to the payload (51 x from 16 KiB to 1 MiB rows at N = 512), and at a fixed width with N, at 2.0 to 2.4 bytes held per payload byte [parts 1, 3]. Both copies are live at the coordinator's end of the read: the replica's serialized buffer (1.0 to 1.4 x N x W, its capacity grows by doubling or by half) and the coordinator's `ResultSet` (1.0 x N x W) [parts 3, 5]; a first page of N rows holds exactly as much as `LIMIT N` [part 3]. A byte cap on the same workload and instruments binds: `local_read_size_fail_threshold` 40 MiB turns every read above it into a READ_SIZE failure and holds the heap at 64 to 65 MiB whatever N x W is (64 to 512 MiB) [part 3], so the instruments can see a cap where one exists; the row count is not one.

**Conclusion (one line):** S7 row 1 — confirmed (does not cap): one LIMIT-N read or one N-row page at the default guardrails holds 2.0 to 2.4 x N x W of heap, replica buffer and coordinator result at once; `local_read_size_fail_threshold` turns it into a read failure with the heap held near the threshold. H5 (OOM) is an extrapolation.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-read `run1/summary.txt`, `U/marker.txt`, `C/marker.txt`, `U/histos.txt`, `C/histos.txt`, `{U,C}/gc-heap-inspection.txt`, `{U,C}/session.log`, `{U,C}/cassandra.yaml.*`, `U/system-log-grep.txt`, and the frozen design section, part by part.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `U/marker.txt` has 196 lines: a PR and a PC start/end pair for each of the 49 U queries, each PC with `rows=N`; `cassandra.yaml.U` ends with the 11 S1 lines and has no guardrail line uncommented; `cassandra.yaml.C` adds the two control lines; `session.log` of U and C: `oom 0; oom_kill 0`, 0 ERROR, 0 `OutOfMemoryError`, "daemons left: []". |
| 2. Readings | yes | The L(512, 16 KiB) `[I` growth (16 076 592 -> 24 454 816 bytes at PR, back to 16 081 072 at B2) is in `U/histos.txt` as stated; the negative A values are in `summary.txt`. |
| 3. Matched row | yes | Recomputed by hand from the `histos.txt` totals of L(512, 1 MiB) rep 1: PR - B = 764.7 MB = 729.3 MiB, PC - B = 1 301.7 MB = 1 241.4 MiB; N x W = 512 MiB; ratios 1.42 and 2.42, as in `summary.txt`. Independent cross-check from the GC log (a different instrument, the JVM's own after-size of the same forced GCs): the largest after-sizes in U are 1 327 to 1 334 MiB (eight GCs: the PC pauses of the 512 x 1 MiB arms, warm-ups included) against a baseline of about 75 to 80 MiB, i.e. about 1 250 MiB held, within about 1 % of H_C 1 241 MiB; in C the largest is 164 MiB against about 78 MiB, i.e. about 86 MiB against H_A 65 MiB: the GC log counts whole 16 MiB regions for humongous objects (`G1HeapRegionSize=16m`), and the 64 MiB abort buffer plus its header takes five regions (80 MiB) [inferred from the region size; the histogram counts the object's bytes]. Both instruments place the capped read near the threshold and the uncapped 512 x 1 MiB read above 1.2 GiB. |
| 4. Excluded rows | yes | The refuting ratio (51.0) and the 0.5 x N x W floor (lowest H_C / N x W 2.01 over large arms) are far from their bounds. |
| 5. Observed vs. inferred | yes | The inferred items are the attribution of H_R and H_C to the two buffers (supported by the logged capacity and by H_C - H_R = N x W) and H5, which the conclusion labels as an extrapolation. |
| 6. Deviations and gaps | yes | No unlisted deviation found in `session.log` of K, U, C; the hand stop of the load node (§3) is before any reading. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Hypotheses H1-H4 -> rows = N (counter fired) -> H_C follows N x W in W and in N (H1) -> H_C = H_R + N x W (H2) -> page = limit (H3) -> byte threshold aborts and holds about 65 MiB flat (H4) -> S7 row 1. |

### 5.2 Run 2?

**No** (2026-11-17). Every reading repeats three times to within 0.2 MiB, a second instrument (the GC log) agrees with the first, the result confirms the claim rather than refuting it or finding a bypass, and the readings sit far from every refuting bound. The one part a run 2 would not settle either is H5, which needs a different (OOM) experiment.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative (case file Estimate; the recheck's "Real-memory estimate" is the same). **Outcome class:** true negative (negative, does not cap) — unchanged from the 2026-10-27 run.

**Claim tested:** (the case file's "Stage-4 claim to add", recheck section, 2026-11-17) "At default guardrails, a single `SELECT ... LIMIT N` (or one page of N rows) over rows of width W retains about N x W (or more) on the coordinator and the replica at the same time. With N x W above the free heap, the node fails with `OutOfMemoryError` instead of stopping gracefully; setting `local_read_size_fail_threshold` turns that into a read failure." Tested as H1-H4 of the design; H5 (the OOM sentence) is not run (a measurement inside a fixed budget) and is stated only as an extrapolation. "Confirmed" below means H1-H4 held.

| Tier | Verdict (S7 row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | not run: the recheck claim is about a node's heap during a CQL read; the counter itself was run in the earlier unit tier (B2, Confirmed, 2026-10-27) | — | — | 2026-11-17 |
| Cluster | **Confirmed** (S7 row 1: R1-R5 hold): held heap 2.0 to 2.4 x N x W at the coordinator's end of the read (replica buffer 1.0 to 1.4 x plus coordinator copy 1.0 x), the same for a first page; H_C(512, 1 MiB) / H_C(512, 16 KiB) = 51.0; the 40 MiB local-read threshold aborts every larger read and holds 64 to 65 MiB | does not cap | run 1 + self-check | 2026-11-17 |

**Positive control:** `local_read_size_fail_threshold: 40MiB` on the same tables, queries and instruments: 4 arms of N x W 64 to 512 MiB fail with READ_SIZE on 3 of 3 repetitions after counting about 42 MB, with 64.4 to 65.2 MiB held at the abort (uncapped the same arms hold 128 to 1 241 MiB); 3 arms under the threshold pass with H_C identical to lifetime U.

**Feedback filed:** one dated line in the case file's section D "Stage-4 feedback" pointing to this file (uncommitted; the orchestrator commits). No section of the case is amended; the design section is the frozen version of §1. Not edited: `recheck-flags.md`, `_INDEX.md`, HANDOFF.

**Leftovers on pc75:** no process (`ps -eo cmd | grep '[C]assandraDaemon'` empty, no `s4rc-*` scope, checked after lifetime C); directory `/mydata/s4/rowlim-rc/` (tree, node data 718 MB, driver, harness copy, logs 3.6 MB) kept as the run's raw evidence.
