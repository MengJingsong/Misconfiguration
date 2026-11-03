# paxos_cache_size-close-active--autonomous — stage-4 results  <!-- file: results/paxos_cache_size-close-active--autonomous.md -->

> **Case:** [`paxos_cache_size-close-active--autonomous`](../../stage3-ai-deep-read/cases/paxos_cache_size-close-active--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/paxos_cache_size-close-active--autonomous/`](../harness/paxos_cache_size-close-active--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e;
> the case file's feedback section is its section D. Session: Claude Opus 5.5 (claude-opus-5-5), advisor-run, on the advisor's Mac.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Branch `advisor-run`, uncommitted on 2026-10-27 (last commit holding the file: `116a56c`'s tree, as filed with sha256 `95e7ac49…77a6`). Frozen after the audit's 15 amendments (U1–U7, C1–C8): sha256 `9f892ab93b5a3df642ebc4b4f6f06516eb4b928babf673e52b15d594ce2ae321`, recorded in `_INDEX-advisor.md` §2 before any harness run. **Both tiers of run 1 ran at this version.** Section D is filled after this hash. |
| **Harness** | `harness/paxos_cache_size-close-active--autonomous/`: `PaxosCacheBoundTest.java` (unit test, copied into the clone only for the run), `unit-run.sh`; `stage4/pcca/PcacheProbe.java` (observe-only helper) and `pcca.btm` (Byteman rule), `pcca-client.py` (bundled-driver LWT client), `cluster-run.sh`; self-check `results/paxos_cache_size-close-active--autonomous/run1/selfcheck.py`. Not committed (the user has not asked for a commit). Reused with attribution: `unit-run.sh` and `cluster-run.sh` adapt the structure and node start/stop functions of `harness/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/`; `pcca-client.py` adapts the driver set-up and `execute_concurrent` loop of `harness/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous/pcs-client.py` (keyspace, table, payload, consistency and modes are this case's). No value or derivation was taken from another case file or results file; every bound below is derived from the 5.0.9 source. |
| **Tiers and values** | Unit: `paxos_cache_size` P ∈ {0, 1, 4, 16, 64, auto} MiB at V = 8,192 B (N = 40,000) and P ∈ {0, 1, 4, 16} at V = 16 B (N = 200,000), each twice. Cluster: one node, 4 GiB heap, C ∈ {0, 8, 32, default (= 40), 128} MiB plus the 1024 MiB positive control, 50,000 LWTs `INSERT … IF NOT EXISTS` with an 8,192-byte blob (Paxos v1). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap held by `PaxosState.RECENT` (weigher sum and real retained heap). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly | B2b {0, 1, 4, 16, 64} and B3b {0, 8, 32, 128, 1024} MiB, but the default (`auto`, `DatabaseDescriptor.java:850-852`) was in neither tier. Added (U2, C2). |
| A. Core question | real resource measured, not only the counter | Partly | B2d `measureDeep` (real) next to W (counter): Met. B3d (3) needed MAT, which is not installed here; replaced by an in-process `measureDeep` probe via Byteman (C4). |
| A. Core question | usage driven to the limit and past it | Partly | Unit V = 8192: 40,000 × ≥ 8,208 B ≫ 64 MiB. V = 16 at 64 MiB: not shown from source to exceed the cap (B2c's own figure is 30 MiB < 64 MiB); dropped from the grid (U2 (ii)). Cluster: 50,000 × ≥ 8,208 B = 391 MiB ≫ 128 MiB. |
| B. Logic | each step says what it establishes | Met | B2c/B3c say each LWT leaves one Snapshot through `close()`; B2h/B3h tie controls to alternatives. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | "n ≈ 126·P", "W in [0.95, 1.0]·M", "n_S ≈ 126 × cap" are approximate. Amended to exact relations from source (U6, C6): n = ⌊M/w⌋ (unit), ⌊M/w⌋ − 1 ≤ n ≤ ⌊M/w⌋ (cluster), w constant, source bound 8,208 ≤ w ≤ 9,232 B. |
| B. Logic | every plausible outcome has a conclusions row | Partly | Missing: R below band (instrument blind), repeats disagree, knob not read back, histogram vs probe disagree, k outside band. Rows added (U7, C7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | Row 1 required only the plateau. Amended: disallow evidence = final n < offered (eviction is the only remover for distinct keys, `PaxosState.java:355-383`). |
| B. Logic | alternative explanations and their controls | Met | cap 0, `ACTIVE.size()` = 0, D1 subtraction, the 1024 MiB positive control, settings read-back. |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 and B1 state the mechanism and the overhead caveat. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Not met | `-Dpaxos.cap`/`-Dpaxos.v` on the `ant` line never reach the forked test JVM (`build.xml:1153-1192`); `schemaDefinition("PaxosCacheBoundTest")` creates `PaxosCacheBoundTestKeyspace1`, not `PaxosStateTestKeyspace1` (`SchemaLoader.java:99`). Amended (U1, U2 (iv)). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Value content, ballot base, sample points, output format, chunking, commit consistency, histogram class match, reset steps were open. Amended (U3–U5, C3–C5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | `/local` paths, `--depth 1` clone, MAT, `GC.heap_info` (fails a known-answer check here) replaced (U1, C1, C4, C8). |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit ≈ 330 MiB of `system.paxos` writes per V = 8192 run on 124 GiB free disk, 1 GiB test heap holds ≤ 64 MiB of RECENT; cluster ≈ 1.2 GB of commit log/data per round, 4 GiB heap ≫ 1024-MiB-control's ≈ 450 MB. |
| D. Runnable | load-bearing citations spot-checked | Met | `PaxosState.java:71-76` (maps, weigher, `ImmediateExecutor`), `:355-383` (`tryGetUnsafe`/`getUnsafe`), `:514-528` (`close()`, the `:520` check, `stash.getClass() == Snapshot.class`), `:211-243` (`Snapshot.merge`), `:672-681` (`commitDirect`), `:764-800` (`legacyPropose`); `Config.java:485`, `DatabaseDescriptor.java:850-860, 3942`; `PartitionUpdate.java:357-361`; `BTreeRow.java:532-541`; `BufferCell.java:141-144`; `ObjectSizes.java:155-175`; `CBUtil.java:466-481` — all match the clone at `b5f2a54210`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | U1: this host's clone and paths; system properties through `-Dtest.jvm.args` | applied, amendment 2026-10-27 | filed command cannot set the knob |
| 2 | U2: default (auto) added; V = 16 not at 64 MiB; two reps; keyspace name; Gossiper stop | applied | group A, C |
| 3 | U3: exact workload (printable-ASCII values, ballot base, accepted count) | applied | `AsciiType` column; group C |
| 4 | U4/U5: sample points, line format, script | applied | group C |
| 5 | U6: exact unit relations, w bound from source, disallow evidence, flatness test | applied | group B |
| 6 | U7: B2g rows added | applied | group B |
| 7 | C1/C8: host, node directory, heap, Byteman agent | applied | `/local` absent |
| 8 | C2: default (40 MiB at 4 GiB) added; effective cap read back in-process | applied | group A; the settings table shows `null` for the default |
| 9 | C3: Python-driver loop, chunks of 10,000, consistency, client checks | applied | group C |
| 10 | C4: histogram class match; MAT → in-process probe; `GC.heap_info` dropped; H informational | applied | MAT absent; known-answer failure |
| 11 | C5: exact per-round sequence | applied | group C |
| 12 | C6/C7: exact cluster relations and rows | applied | group B |
| 13 | Stage 3: note that `TableMetadata` is `@Unmetered` (`TableMetadata.java:82`), so `measureDeep` of RECENT never counts the shared schema and B2d's D1 needs no schema correction | left for stage 3 | a fact for A3/B2d; not needed for the run |
| 14 | Stage 3: the filed per-entry estimate (≈ 8.3 KiB, "≈ 126·P") is ≈ 4 % low in the unit tier (the clustering adds weight); state predictions as n = ⌊M/w⌋ | left for stage 3 | style; the amended relations already cover it |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 02:22–02:30, cluster 02:32–02:43 local time, EDT) |
| Node | `yangwang-mbp`, the advisor's MacBook Pro (Apple M1 Pro, T6000, arm64), single host; 10 cores, 32 GiB (`hw.memsize` 34359738368) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 (xnu-13432.1.9~1) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64) |
| Ant | Apache Ant 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run49` (`W=~/Library/Caches/stage4`), fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` BUILD SUCCESSFUL in 53 s; `git status` clean after both tiers |
| Case-file commit / harness commit | case file uncommitted at sha256 `9f892ab9…e321` (on `116a56c`); harness uncommitted |
| Storage for node data | internal SSD, APFS `/dev/disk3s1`, 124 GiB free; unit data `build/test/cassandra` (removed before each run); node files `$W/node-pcca/` (removed after each round; 0.3–1.0 GB each, `run1/cluster/C*/node-du.txt`) |
| Loopback / ports | `127.0.0.1`–`.3` on `lo0` (only `.1` used); 7000, 7199, 9042, 9091 free before the run |
| Full logs (outside the repo) | `$W/logs/paxos_cache_size-close-active/` (`clone.log`, `build-test.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-r1/`) |

Machine facts relied on: workspace `$W` and `env.sh`; commands touching `$W`/Java run unsandboxed; `-Dlocal.repository=$W/m2` on every ant call; test stdout read from `build/test/logs/**/TEST-<class>.log`; `-Dno-build-test=true` after the first compile; no `setsid` (node as a tracked background process with `bin/cassandra -f > log < /dev/null`); `CASSANDRA_CONF`/`CASSANDRA_LOG_DIR` outside the clone so it stays clean; `JVM_EXTRA_OPTS` scoped to the node command; `jstat` unusable, so `jcmd GC.class_histogram` (columns matched exactly, not by regex) and no `GC.heap_info`; no MAT, so an in-process probe; the bundled Python driver with `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, heartbeat off; a Byteman rule type-checked with `TestScript` before use; `pgrep` patterns written as `Cassandra[D]aemon`; long steps in the background; the self-check written before readings and run end to end on the shakedown output (exit status 0).

## 3. Runbook defects

None. The frozen runbook ran as written in both tiers. Shakedowns before run 1 (`unit-shake`: 4 small runs; `cluster-shake`: chunks of 1,000 at caps 0, 2, default) found no defect; the self-check ran on both with exit status 0 (51 and 37 checks).

Note (not a defect): the probe's `Mtm` column reads 0 in every round, because `TableMetadata` is annotated `@Unmetered` (`TableMetadata.java:82`) and jamm skips it. C4 (3)'s formula R = D − D_empty − Mtm is applied as written; the shared schema is simply never part of D.

## 4. Run 1

**Scope:** both tiers, all values of §1, at sha256 `9f892ab9…e321`. **Command logs:** `paxos_cache_size-close-active--autonomous/run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/<tag>.pcb`, extracted from the TEST logs; JUnit 1 test, 0 failures, 0 errors in every run, `run1/unit/TEST-<tag>.testsuite.txt`). M = P·2^20. Both repeats of every (P, V) gave identical final lines.

| P (MiB) | V (B) | w (B, all entries) | final n | ⌊M/w⌋ | final W | M − W | D − D1 (B) | (D − D1)/M | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 8192 | — | 0 | — | 0 | — | (D = 1,544 constant) | — | `P0-V8192-r1/r2.pcb` |
| 1 | 8192 | 8,632 | 121 | 121 | 1,044,472 | 4,104 | 1,100,176 | 1.049 | `P1-V8192-r*.pcb` |
| 4 | 8192 | 8,632 | 485 | 485 | 4,186,520 | 7,784 | 4,437,648 | 1.058 | `P4-V8192-r*.pcb` |
| 16 | 8192 | 8,632 | 1,943 | 1,943 | 16,771,976 | 5,240 | 17,805,840 | 1.061 | `P16-V8192-r*.pcb` |
| 64 | 8192 | 8,632 | 7,774 | 7,774 | 67,105,168 | 3,696 | 71,269,456 | 1.062 | `P64-V8192-r*.pcb` |
| auto (= 4; totalMemory 519,438,336 B) | 8192 | 8,632 | 485 | 485 | 4,186,520 | 7,784 | 4,437,648 | 1.058 | `Pauto-V8192-r*.pcb` |
| 0 | 16 | — | 0 | — | 0 | — | (D = 1,544 constant) | — | `P0-V16-r*.pcb` |
| 1 | 16 | 456 | 2,299 | 2,299 | 1,048,344 | 232 | 2,291,888 | 2.186 (k) | `P1-V16-r*.pcb` |
| 4 | 16 | 456 | 9,198 | 9,198 | 4,194,288 | 16 | 9,172,768 | 2.187 (k) | `P4-V16-r*.pcb` |
| 16 | 16 | 456 | 36,792 | 36,792 | 16,777,152 | 64 | 36,694,336 | 2.187 (k) | `P16-V16-r*.pcb` |

At every sample: `ACTIVE.size()` = 0; every `legacyPropose` returned true (accepted = N); `cap_mib` = P; below the cap n = i exactly, above it n = ⌊M/w⌋ and W = n·w exactly (e.g. P = 64: n = 1,000·k up to i = 7,000, then 7,774 from i = 8,000 on). D1 = 10,904 B (V = 8192) and 2,728 B (V = 16). V = 16: D − D1 identical at every sample past 2·M (max/min = 1.0000).

**Cluster tier** (`run1/cluster/C<cap>/`: `probe.txt`, `histo-<tag>-excerpt.txt`, `lwt-<i>.json`, `settings.json`, `yaml.diff`). w = 8,448 B for every entry in every round; every chunk 10,000 applied, 0 errors, 0 not applied (13.1–14.3 s of client time per round); `active` = 0 at every probe; effective `cap_mib` = intended value at every probe.

| cap (MiB) | Run | n at i = 10k / 20k / 30k / 40k / 50k / final | ⌊M/w⌋ | final W (B) | n_S (histogram) | R = D − D_empty (B) | R / M | R / W | H after flush (B, informational) | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | zero point | 0 / 0 / 0 / 0 / 0 / 0 | — | 0 | 0 at every sample | 0 | — | — | 54,977,584 | `C0/` |
| 8 | A | 992 at every probe | 992 | 8,380,416 | = n at every sample | 8,867,032 (8.46 MiB) | 1.057 | 1.058 | 62,739,896 | `C8/` |
| 32 | B | 3,971 at every probe | 3,971 | 33,547,008 | = n | 35,489,344 (33.85 MiB) | 1.058 | 1.058 | 91,383,072 | `C32/` |
| default (40) | C | 4,964 at every probe | 4,964 | 41,935,872 | = n | 44,380,040 (42.32 MiB) | 1.058 | 1.058 | 98,326,392 | `Cdefault/` (settings `paxos_cache_size` = null) |
| 128 | D | 10,000 / 15,887 / 15,887 / 15,887 / 15,887 / 15,887 | 15,887 | 134,213,376 | = n | 141,986,976 (135.41 MiB) | 1.058 | 1.058 | 196,992,704 | `C128/` |
| 1024 | positive control | 10,000 / 20,000 / 30,000 / 40,000 / 50,000 / 50,000 | (126,857) | 422,400,000 | = n | 446,834,664 (426.13 MiB) | 0.416 | 1.058 | 500,774,648 | `C1024/` |

Baseline probe in every round: n = 0, D_empty = 1,320 B. `n_K` (Key instances) equals n at every sample (`histo-<tag>-excerpt.txt`; no Snapshot or Key row at all when n = 0).

### 4.2 Conclusion and logic

1. **Validity.** Unit: knob read back as P in every run, auto = min(max(1, ⌊0.01·519,438,336/2^20⌋), 50) = 4 [observed: PCB-START lines]; V, N, `paxos_variant` = v1, purging = legacy as planned; offered weight N·w ≫ M for every P > 0 (smallest margin: P = 64, V = 8192, 40,000 × 8,632 B = 345 MB vs 67 MB) [observed: `.pcb`]. Cluster: yaml carries `paxos_cache_size: <C>MiB` (none for the default) [observed: `yaml.diff`]; settings table `paxos_variant` = v1 and `paxos_cache_size` = the configured string or null [observed: `settings.json`]; effective cap read in-process = intended [observed: `probe.txt` column 3]; 50,000 LWTs applied with 0 errors [observed: `lwt-*.json`]; offered 50,000 × 8,448 B = 422 MB > M for every capped round [observed: final W of the control]. The run is valid.
2. **Readings.** No gap, outlier or contradiction. Beyond the predictions: both repeats of every unit (P, V) are bit-identical in n, W and D [observed]; `Mtm` = 0 (`@Unmetered`, §3) [observed: `probe.txt`; inferred from `TableMetadata.java:82`]; R/W = 1.058 in every cluster round including the control, i.e. the real heap per entry is 1.058 × its weight for 8-KiB values [observed]; H after flush minus H(cap 0) is 7.8, 36.4, 43.3, 142.0, 445.8 MB, close to R (8.9, 35.5, 44.4, 142.0, 446.8 MB) [observed; informational only].
3. **Matched row.** Unit B2g row 1, "`W` and `D` plateau, and the plateau scales with P (×4 per step) — claim confirmed", with every U7 condition: U6 (a) w constant (8,632; 456); (c) W ≤ M everywhere, n = i below the cap and n = ⌊M/w⌋, W = n·w above it; (d) final n < N in every P > 0 run; (f) repeats identical; D − D1 for V = 8192 at 1.049–1.062·M ∈ [0.9, 1.3]; (h) cap 0 n = W = 0 [observed: `run1/unit/*.pcb`]. The V = 16 runs match the row "V = 16: D ≫ P·2^20 but flat, linear in P — confirmed with overshoot", k = 2.186–2.187 ∈ [2, 8] [observed]. Cluster B3g row 1, "`n_S`/`R` plateau at ≈ cap/w and scale with cap, while the 1024MiB control reaches ≈ 50,000 — claim confirmed", with every C7 condition: C6 (a) w = 8,448 constant; (b) W ≤ M and n = ⌊M/w⌋ exactly at every capped probe past the cap (n = i = 10,000 at C = 128's first probe); (c) final n < 50,000; (d) cap 0 n = W = n_S = 0; (e) control n = i, final 50,000, W = 50,000·w; (f) n_S = n at all 42 samples; (g) R in band (8.46 ∈ [8, 10.5], 33.85 ∈ [32, 42], 42.32 ∈ [40, 52], 135.41 ∈ [128, 166], 426.13 ∈ [410, 530] MiB); (h) active = 0 [observed: `run1/cluster/C*/`].
4. **Excluded rows.** Unit: "W exceeds P·2^20" (Refuted) — max W ≤ M − 16 B in every run; "D keeps rising linearly with N past the cap" (Refuted) — D constant from the first capped sample to N (the same value at every sample with the same n, in every run); "plateau the same for all P" (Refuted) — 121, 485, 1,943, 7,774; "cap 0 retains entries" (Refuted) — n = 0; "offered weight never exceeded the cap" — exceeded in every run; U7 rows: D − D1 never > 1.3·M or < 0.9·M; k inside [2, 8]; repeats agree; read-back, accepted and ACTIVE all as required; eviction (n < i) seen in every P > 0 run [observed]. Cluster: "n_S ≈ 50,000 at all caps" (Refuted) — 992 … 15,887; "plateau ≫ 1.3 × cap" (Refuted) — R/M ≤ 1.058; "control also stays low" — control 50,000; "n_S the same for every cap" — differs; C7 rows: R never above or below its band; n_S = n everywhere; read-back, client and active all as required; W ≤ M everywhere [observed].
5. **Observed vs. inferred.** The verdict rests on observed values only. Inferred and not load-bearing: that eviction is the only remover of a finished key's entry (from `PaxosState.java:355-383`, used to read n < offered as disallow evidence; it is also directly visible as n = ⌊M/w⌋ < i); that `Mtm` = 0 because of `@Unmetered`; that H differences track R (H is informational).
6. **Deviations and gaps.** None from the frozen runbook. Optional items not run: the B3a `paxos_variant: v2` repeat (optional in the case; not run). The cluster tier measures `RECENT` in-process (C4 (3)) instead of a heap-dump retained size; `measureDeep` counts everything reachable from `RECENT` except `@Unmetered` classes, so objects shared with another holder would be counted (none is expected after a commit; the R/W ratio equals the unit tier's V = 8192 ratio of ≈ 1.06). The source bound on w (8,208–9,232 B) and the k band were sub-predictions; all hit.
7. **Core question.** Hypothesis (B1): after Paxos operations on many partitions, the weigher sum never exceeds `paxos_cache_size` × 2^20 and the real heap of `RECENT` stays within 1.3× the cap for 8-KiB values. Test and logic (B2b–B2e, B3b–B3e): the unit tier drives `legacyPropose` → `close()` → the `:520` check directly and shows the entry count stop at exactly ⌊M/w⌋ for every cap, the weight at most M, the real heap at 1.05–1.06 M, and nothing retained at cap 0 (parts 1, 3); the cluster tier shows the same through real LWTs on a node: with the same 50,000 statements, the cache keeps all 50,000 entries (426 MiB) under a 1-GiB cap but stops at 992 / 3,971 / 4,964 / 15,887 entries (8.5 / 33.9 / 42.3 / 135.4 MiB) under 8 / 32 / 40 (default) / 128 MiB (parts 1, 3, 4). **Usage follows the constraint and the constraint caps it; the real heap exceeds the weighed amount by 5.8 % for 8-KiB values and by a factor of ≈ 2.19 for 16-byte values (A3 bypass (b)), as the case predicted.**

**Conclusion (one line):** unit — B2g row 1 (with the V = 16 overshoot row, k ≈ 2.19) — confirmed; cluster — B3g row 1 — confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-parses the raw files (unit: the copied TEST logs `<tag>.log` and JUnit XML; cluster: per round `probe.txt`, `histo-<tag>.txt`, `lwt-<i>.json`, `settings.json`, `yaml.diff`) and recomputes every amended B2f/U6 and B3f/C6 relation without using any harness summary line. It was written before run 1 and run end to end on the shakedown outputs (`unit-shake`: 51 checks, 0 failed; `cluster-shake`: 37 checks, 0 failed; exit status 0). On run 1: **358 checks, 0 failed, exit status 0**; sub-predictions (w bound, k band) **21 hit, 0 missed**; output `run1/selfcheck.out`.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: read-backs (incl. auto = 4 recomputed from `total_memory`), accepted = N, JUnit 1/0/0, yaml lines, settings, effective caps, client chunks — all PASS. |
| 2. Readings | yes | Re-read `C128/probe.txt` (7 lines, n 0 → 10,000 → 15,887 ×5, D_empty 1,320) and `P16-V16-r1.pcb` (W 16,777,152 at the end); `Mtm` = 0 in every `probe.txt`; `@Unmetered` at `TableMetadata.java:82`. |
| 3. Matched row | yes | Every U6 (a), (c)–(h) and C6 (a)–(h) relation recomputed from raw rows: PASS. |
| 4. Excluded rows | yes | The excluded rows' conditions are the negations of PASS checks (W ≤ M, exact n, bands, ordering, n_S = n, control n = 50,000). |
| 5. Observed vs. inferred | yes | No relation in the self-check uses the inferences of part 5. |
| 6. Deviations and gaps | yes | The v2 repeat is optional in B3a; no runbook step was skipped (`commands.log` of both tiers). |
| 7. Core question | yes | Ceiling follows the knob in both tiers (exact ⌊M/w⌋), direct disallow evidence (n < offered), positive control and zero point both as predicted. |

### 5.2 Run 2?

**No** — 2026-10-27. The conclusion rests on observed readings only, every self-check part holds, the unit repeats are identical, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** After Paxos operations on many distinct partitions, the heap held by `PaxosState.RECENT` stays bounded and scales with `paxos_cache_size`. The summed weigher value never exceeds `paxos_cache_size × 2^20` bytes. For values of 8 KiB the actual retained heap stays within 1.3× the cap.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1) — n = ⌊M/w⌋ exactly (121 / 485 / 1,943 / 7,774 at 1 / 4 / 16 / 64 MiB, w = 8,632 B; auto = 4 MiB → 485), W ≤ M, real heap 1.05–1.06 × M, cap 0 retains nothing; V = 16 bounded with overshoot k ≈ 2.19 | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed (B3g row 1) — v1 LWTs: n_S = 992 / 3,971 / 4,964 / 15,887 at 8 / 32 / 40 (default) / 128 MiB (= ⌊M/8,448⌋), R = 1.058 × weight, 0 at cap 0, 50,000 (426 MiB) under the 1024 MiB control | caps | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (uncommitted, after sha256 `9f892ab9…e321`); B2a–B4 carry the 15 dated audit amendments (U1–U7, C1–C8); `_INDEX-advisor.md` §2 has one new row and §1's Stage 4 column for this file is filled. Recommendations 13 and 14 are left for stage 3.
