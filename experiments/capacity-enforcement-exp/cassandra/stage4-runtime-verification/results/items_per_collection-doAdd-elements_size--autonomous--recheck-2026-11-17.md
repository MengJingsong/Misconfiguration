# items_per_collection-doAdd-elements_size--autonomous — stage-4 results for the recheck claim (2026-11-17)  <!-- file: results/items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17.md -->

> **Case:** [`items_per_collection-doAdd-elements_size--autonomous`](../../stage3-ai-deep-read/cases/items_per_collection-doAdd-elements_size--autonomous.md),
> section `## Recheck — enforcement properties (guided, 2026-11-16, blind)` and its **Stage-4 claim to add**; the design that was run is the case
> file's section `## Stage-4 design for the recheck claim (2026-11-17)` (R1–R9). The case's earlier stage-4 results (claims (i)–(iii) of B1) are in
> [`items_per_collection-doAdd-elements_size--autonomous.md`](items_per_collection-doAdd-elements_size--autonomous.md) and are not changed here.
>
> **Status:** verdict filed, 2026-11-17. **Confirmed (clauses a–d) — does not cap** (R7 row 1). At shipped defaults one `SELECT` of a `set<int>`
> grown by appends to M = 10⁵, 10⁶, 10⁷ items succeeds and returns all M items; the node allocates **334–352 B per item** and, while the coordinator
> holds the row, **holds 148–154 B per item** of live heap (1.53 GB for 10⁷ items), against **4.0 B per item on disk** and 8 B per item serialized.
> With the guardrail binding (T = 5,000, ordinary user), a set grown by 200 accepted appends to 200·T = 10⁶ items costs the same per item.
> No run 2.
>
> **Outcome class (recheck claim):** true negative — the recheck's real-memory estimate `negative` against the Effect `does not cap`
> ([definition](../../../stage4-runtime-verification/README.md#outcome-class)). One tier (a single real node); the unit tier is n/a (§1). The case's
> own outcome class from the earlier results file is not changed by this file.
>
> **Agent:** autonomous case file; the design is the recheck section's R1–R9 (R6 = prediction, R7 = conclusions table, R8 = runbook), written by
> this session, not by stage 3.
>
> **Session:** Claude Opus 5.5 (`claude-opus-5-5`), Claude Code, 2026-11-17, driving `pc99` over SSH.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `2f76b847` (case file last committed in `832b828a`; the design section is uncommitted). Frozen 2026-11-17 12:47:55 EST, before the shakedown and before any reading: `sed -n '/^## Stage-4 design for the recheck claim (2026-11-17)/,$p' <case file> \| git hash-object --stdin` = **`d40b0ab80034aef16db1237ef5ac7161307e1602`** (107 lines; the section is the file's last, and section D's new line is above it, so the hash still holds). Whole file sha256 at freeze `334d74b5…b981`. [`run1/freeze.txt`](items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/run1/freeze.txt). |
| **Harness** | [`../harness/items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/`](../harness/items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/): `run.sh` (one script, both node lifetimes), `s4.py` (bundled-driver client), `HeapProbe.java` (JMX: all threads' allocated bytes, read-threshold setters, metrics), `pause.btm` (Byteman hold at `ResultSetBuilder.newRow`), `analyze.py` (readings and every R6 condition). Uncommitted (no commit asked). sha256 at run 1: [`run1/harness-sha256.txt`](items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/run1/harness-sha256.txt); four instrument fixes S1–S5 after the freeze (§3), none touching R1–R9. |
| **Tiers and values** | One real node (cluster-style tier). Unit tier **n/a**: the claim is about the heap of a running node serving a CQL read through the native protocol (replica + coordinator + result encoding); a unit test would read the memtable path inside the test JVM. Arms: Z (1 item), S5/S6/S7 (M = 10⁵/10⁶/10⁷), B (8,000,004-byte blob), P (read-size threshold 64 MiB on S5–S7), G (guardrail 2,500/5,000, ordinary user, M = 10⁶). |
| **Audit bottom line** | **Ready** — 2026-11-17 (the design was written for this run against groups A–D; no amendment needed before the freeze). |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | R1/R5: heap bytes allocated and held by one read (O1, O2), next to disk bytes and serialized bytes (O5). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met (operand sweep) | The claim is that nothing caps the read, so the operand is swept (M = 10⁵, 10⁶, 10⁷ at defaults, R4); the guardrail knob is run at its default −1 and at T = 5,000 (arm G); the read-size knob is the binding knob of the positive control (arm P). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | O1 is the JVM's per-thread allocation counter, O2 a forced-GC live histogram; Cassandra's own estimate (`LocalReadSize`) is recorded only as a comparison (P6). Gap named: replica and coordinator share the JVM (R1 b). |
| A. Core question | usage driven to the limit and past it | Met (no limit at defaults) | No limit exists at defaults; dose spans 100× (R4) inside a recorded 14 GiB budget (R3); arm P shows a binding limit. |
| A. Core question | positive control (negative-estimate claim) | Met | Arm P (R4, R6 P6): `local_read_size_fail_threshold` on, a limit known to bind (`ReadCommand.java:709-722`). |
| B. Logic | each step says what it establishes | Met | R2 Logic steps 1–6. |
| B. Logic | prediction stated in numbers or a clear relation | Met | R6 P1–P7, with bands and ratios. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | R7 rows 1–10, incl. limit stops it (4), flat (5), magnitude miss (3), control fails (7, 8), invalid (9), none fits (10). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (as adapted for a negative claim) | Row 1 needs the dose-response (P2, P3) and the positive control's disallow evidence (P6: rejection, no coordinator pause). |
| B. Logic | alternative explanations and their controls | Met | Bytes vs items: blob B (P5); constant per-read cost: baseline Z subtracted; background allocation: idle window; guardrail on: arm G. |
| C. Specific | a human can follow it from the intro and §9a | Met | R1–R2. |
| C. Specific | an AI can run it without re-deriving the code path | Met | R8 and `run.sh`. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | R3–R5, R8. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc99 has JDK 11.0.33, Ant, built `cassandra-base`, Byteman jars in `build/lib/jars`, `jcmd`, `javac`, user systemd with the memory controller (checked: a test scope showed `memory.max` and `memory.swap.max` = 0). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 10⁷ cells ≈ 2 GB held at ~200 B/item in an 8 GiB heap; 14 GiB budget; disk < 200 MB of 715 GiB; expected < 60 min. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `UnfilteredSerializer.java:672-688`, `ReadResponse.java:182-194`, `ReadCommand.java:655-730`, `SelectStatement.java:1089-1126`, `ResultSetBuilder.java:126`, `StorageService.java:7315-7335`, `Config.java:145, 526, 1399`, `conf/cassandra.yaml:198, 825, 1322`, `conf/cassandra-env.sh` heap and gc.log lines, `conf/jvm11-server.options:63-84`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | For stage 3: the recheck claim names "replica's and coordinator's" heap; on one node they are one JVM — a two-node run would split them | left for stage 3 | Not needed for the claim's direction or magnitude. |
| 2 | For stage 3: the claim's "about 200 B per item" was derived from `local_read_size` (an estimate); the measured held heap is ~150 B/item and allocation ~345 B/item — state which quantity is meant | left for stage 3 | Found by the run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-17; shakedown attempt 1 12:48:16–12:51:41 EST, Byteman debug ~12:52–12:53, attempt 2 12:54:00–13:00:00; **run 1 13:00:56–13:08:34 EST (458 s)** |
| Node | `pc99` = `node3.jason92-326528.misconfiguration-pg0.cloudlab.umass.edu`, x86_64, 32 cores, 125 GiB RAM, 8 GiB swap (on), `/mydata` 715 GiB free ([`run1/env.txt`](items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/run1/env.txt)) |
| OS and kernel | Ubuntu 22.04.2, `5.15.0-203-generic`, cgroup v2 |
| JDK | OpenJDK 11.0.33 (`11.0.33+9-post-1ubuntu1-22.04.1`); node `-Xms8G -Xmx8G`, G1 (shipped `jvm11-server.options`), jamm and Byteman 4.0.20 agents |
| Ant | 1.10.12 (not used: the copy was already built) |
| Local source copy | `cp -a /mydata/s4/cassandra-base /mydata/s4/ipc-recheck/cassandra` (base copied from this repository's `systems/cassandra/source/` with `copy-source.sh`, `git describe` = `cassandra-5.0.9`; release string `5.0.9-SNAPSHOT`) |
| Case-file commit / harness commit | `2f76b847` + uncommitted design section (hash in §1) / harness uncommitted (sha256 in §1) |
| Storage for node data | `/mydata/s4/ipc-recheck/node/` (local LVM volume), data removed after the run |
| Budget | node in `systemd-run --user --scope -p MemoryMax=14G -p MemorySwapMax=0` (units `s4-ipc-recheck-L1`, `-L2`); peak `memory.current` 9.21 GiB (L1), 8.98 GiB (L2); `oom_kill` 0 ([`memory-L1.txt`](items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/run1/memory-L1.txt)) |
| Full logs (path, outside the repo) | `pc99:/mydata/s4/ipc-recheck/logs/` — `run1/` (`summary-raw.txt`, `commands.log`, `analysis.txt`, `node-L1.out`, `node-L2.out`, `system-L*.log`, `L1-gc.log`, `L2-gc.log*`, `snaps/`, `histo/` full histograms, `memory-L*.txt`), `run1.console`, `shake-attempt1/`, `shake/`, `bmdebug/` |

## 3. Runbook defects

None in run 1. The shakedown (instrument check, after the freeze; R8) found five instrument faults, all fixed in the harness before run 1; none changes R1–R9:

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| S1 | shakedown 1 | R5 O2 (`pause.btm`) | The rule never fired: Byteman cannot parse `new java.io.File(..).exists()` inside `IF` ("invalid expression", [`shakedown/bmdebug-rule-parse-error.txt`](items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/shakedown/bmdebug-rule-parse-error.txt)); errors are printed only with `-Dorg.jboss.byteman.verbose=true` | `BIND flag : java.io.File = new java.io.File(...)`, `IF … && flag.exists()`; checked with `org.jboss.byteman.check.TestScript` ("no errors") | AI, 2026-11-17 | n/a (harness) |
| S2 | shakedown 1 | R4 arm P (`HeapProbe readthresholds`) | `No such operation: setReadThresholdsEnabled` — the setters are MBean attributes, not operations | `setAttribute` on `ReadThresholdsEnabled`, `LocalReadTooLargeAbortThreshold`; read-back worked in shakedown 2 | AI, 2026-11-17 | n/a |
| S3 | shakedown 2 | `run.sh` pause detection | `grep -c` prints `0` and exits 1, so `|| echo 0` gave "0\n0" and the first pause of each node lifetime (Z, G) was not detected (the pause itself happened) | `pauses()` echoes `${n:-0}`; tested on the shakedown files | AI, 2026-11-17 | n/a |
| S4 | shakedown 2 | `analyze.py` P5 | crashed when Z's held reading was missing | guard | AI, 2026-11-17 | n/a |
| S5 | shakedown 2 | `analyze.py` P6 info | the `LocalReadSize` regex took the aborts count | match `LocalReadSize Max = N` | AI, 2026-11-17 | n/a |

**Shakedown readings were seen before run 1** (at M = 10³–10⁵: allocation ≈ 300–330 B/item; no held reading, S1). The predictions were frozen at
12:47:55, before the shakedown, and were not changed. One shakedown condition failed for a scale reason, not a fault: P7 `a_G/a_S6` = 1.39 at M = 10⁴,
where G's authenticated connection's fixed cost is divided by only 10⁴ items; left as frozen.

**Lost threads (R7 row 9).** Every snapshot pair loses 1–2 threads; all are `JMX server connection timeout NNN` threads of the probe's own previous
JMX connection (checked by name in shakedown 2 and run 1), so they carry instrument allocation, not the read's. Read as "no lost thread of the read".

## 4. Run 1

**Scope:** every arm of R4. **Command log:** [`run1/commands.log`](items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/run1/commands.log); all lines summarised in [`run1/summary-raw.txt`](items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/run1/summary-raw.txt); computed by [`run1/analysis.txt`](items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/run1/analysis.txt) (30 checks, 30 pass).

### 4.1 Readings

Loads: every append accepted (z 1, s5 1, s6 10, s7 100 statements of 10⁵ items; s7 in 26.1 s; blob accepted); after flush and compaction one sstable per table.

| Arm | M | Read outcome (×3) | Server time | alloc_net per read (median) | a (B/item, − Z) | held at pause | h (B/item, − Z) | cell objects at pause (Δ) | Disk (du) | Serialized value |
|---|---|---|---|---|---|---|---|---|---|---|
| Z | 1 | accepted, count 1 | 3–6 ms | 4,471,289 B | — | 254,128 B | — | +1 | 9,210 B | 12 B |
| S5 | 100,000 | accepted, count 100,000, 800,004 B | 51–139 ms | 37,894,920 B | **334.2** | 15,095,400 B | **148.4** | +100,000 | 410,636 B (4.11 B/item) | 8 B/item |
| S6 | 1,000,000 | accepted, count 1,000,000, 8,000,004 B | 0.61–0.69 s | 350,642,131 B | **346.2** | 153,997,920 B | **153.7** | +1,000,000 | 4,031,001 B (4.03 B/item) | 8 B/item |
| S7 | 10,000,000 | accepted, count 10,000,000, 80,000,004 B | 10.1 / 20.3 / 11.0 s | 3,522,579,462 B | **351.8** | 1,529,319,888 B | **152.9** | +10,000,000 | 40,251,305 B (4.03 B/item) | 8 B/item |
| B (blob) | 1 cell, 8,000,004 B | accepted, 8,000,004 B | ~0.1 s | 44,272,995 B | (B − Z = 39.8 MB = 0.115 × S6's) | 25,004,088 B | (B − Z = 24.7 MB = 0.161 × S6's) | +1 | 53,607 B (zeros, LZ4) | 8,000,004 B |
| G (T = 5,000, `app`) | 1,000,000 | accepted, count 1,000,000 | 0.64–0.82 s | 350,233,501 B | **345.8** (0.999 × S6) | 153,976,184 B | **153.7** (1.000 × S6) | +1,000,000 | 4,042,062 B | 8 B/item |

Sources: `analysis.txt`; `snaps/*.tsv` (O1); `histo-head/*-base.txt`, `*-pause.txt` (O2 `Total` lines; at the S7 pause the top classes are
`HeapByteBuffer` 10,000,829 / 480 MB, `ArrayCell` 10,000,000 / 400 MB, `byte[]` 10,107,168 / 392 MB, `CellPath$SingleItemCellPath` 10,000,018 / 160 MB,
`Object[]` 124 MB — the coordinator's deserialized row, ~150 B per item); `byteman-pause-lines.txt` (a pause in every default arm and G).
Idle background 0.12–0.17 MB/s in L1, 1.14 MB/s in L2.

**Positive control P** (thresholds read back `enabled=true localAbort=64MiB`, `summary-raw.txt`):

| Table | Outcome | Coordinator reached `newRow`? | alloc_net (B/item) | `LocalReadSize` Max (Cassandra's estimate) | system.log |
|---|---|---|---|---|---|
| s5 | accepted, count 100,000 | yes (1 pause) | (includes the 15 s pause; not a condition) | 17,436,917 B = 174.4 B/item | — |
| s6 | **rejected** (`ReadFailure … 1 nodes loaded over 148919632 bytes`) | no | 149,824,127 B = 149.8 B/item | 155,469,300 B = 155.5 B/item | `CoordinatorWarnings … loaded over 148919632 bytes and aborted the query` |
| s7 | **rejected** (`… loaded over 1489193880 bytes`) | no | 1,506,375,981 B = 150.6 B/item, **0.428 ×** the accepted S7 read | 1,663,415,872 B = 166.3 B/item | `… loaded over 1489193880 bytes and aborted the query` |

**Clause d (L2):** `app` (not a superuser) writing 5,001 items in one statement: rejected, `Guardrail items_per_collection violated: Detected collection v with 5001 items, this exceeds the failure threshold of 5000.`; then 200/200 appends of 5,000 accepted (13.5 s); the flush logged `… in row 424242 in table probe.g6 with 1000000 items, this exceeds the failure threshold` and completed (`system-log-guard-and-readsize-lines.txt`).

**GC log (O3, recorded):** during the second and third S7 reads G1 reported **`To-space exhausted`** twice (GC 15: `5898M->5386M(8192M)` 1.57 s; GC 16:
`7898M->7898M(8192M)` 1.15 s) and then a **`Pause Full (G1 Evacuation Pause) 7898M->796M`** (GC 17), with 100 humongous regions (16 MiB each)
([`run1/gc-L1-pauses.txt`](items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17/run1/gc-L1-pauses.txt)). The second S7 read took 20.3 s
instead of ~10 s. Three sequential 10⁷-item reads filled the 8 GiB heap to the point of evacuation failure, though one read holds only ~1.5 GB live.

### 4.2 Conclusion and logic

1. **Validity** — Every load accepted and reached count M; one sstable per table before the reads [observed: `summary-raw.txt` RESULT load, SIZE].
   Defaults held: `authenticator`/`authorizer` AllowAll, guardrail −1/−1, `read_thresholds_enabled=false`, `localAbort=null` [observed: `yaml-diff-L1.txt`
   shows only directories, the two timeouts and AllowAll re-stated; `READTHRESHOLDS-DEFAULT` line]. The hold was reached in all six held reads [observed:
   `byteman-pause-lines.txt`]. No `oom_kill`, peak 9.21 GiB of the 14 GiB budget, no swap allowed [observed: `memory-L*.txt`]. Lost threads are the probe's
   own JMX threads (§3). The run is valid.
2. **Readings** — Allocation and held heap per item are flat across 100× of M (334/346/352 and 148/154/153 B/item). The S7 reads show heap pressure in
   the GC log (to-space exhausted, a full GC), recorded, not a condition. The G arm's L2 idle rate is higher (auth caches), subtracted.
3. **Matched row** — R7 row 1, "Validity holds; P1, P2, P3, P5, P6 and P7 hold" [observed: `analysis.txt`]: P1 9/9 default reads accepted with count M and
   4 + 8M bytes; P2 a₆ = 346.2, a₇ = 351.8 ∈ [200, 2000], a₇/a₆ = 1.016, a₅/a₆ = 0.966; P3 h = 148.4/153.7/152.9 ∈ [100, 400], h₇/h₆ = 0.995, cell Δ = M
   exactly; P5 blob 0.115 (alloc) and 0.161 (held) ≤ 0.5 of S6; P6 read-back true/64MiB, S5 accepted, S6 and S7 rejected, no pause for S6/S7, rejected S7
   alloc 0.428 < 0.8 × default; P7 T+1 write rejected with the guardrail message, 200/200 appends, G reads accepted with count 10⁶, a_G/a₆ = 0.999, h_G/h₆ = 1.000.
   P4 (recorded relation) holds: 4.0–4.1 B/item on disk ≤ 20, h ≥ 18.6 × the 8 B serialized (≥ 10).
4. **Excluded rows** — Row 2: P7 holds. Row 3: every h in [100, 400]. Row 4: no default read rejected or truncated. Row 5: ratios 1.016 and 0.995. Row 6:
   the guardrail-on read costs 0.999/1.000 × S6 and the T+1 write was rejected. Row 7: blob 0.115/0.161. Row 8: P6 holds. Row 9: no invalidating event.
   Row 10: row 1 fits [observed: `analysis.txt`].
5. **Observed vs. inferred** — Inferred: that the held bytes at the pause are the coordinator's deserialized row (from the class histogram: `ArrayCell`
   and `SingleItemCellPath` counts equal to M, the coordinator side deserializing with `ByteArrayAccessor`, `UnfilteredSerializer.java:685`); and that the
   rejected P read allocated ~150 B/item because the replica built the whole row before the per-row size check (`ReadCommand.java:691-694, 709-722`;
   consistent with the coordinator warning "loaded over 1489193880 bytes"). Neither is needed for row 1.
6. **Deviations and gaps** — Heap 8 GiB (not the node's computed default of 31 GiB) and `read_request_timeout`/`native_transport_timeout` 120 s, both in
   the frozen design (R3); the guardrail and read-size knobs are at their shipped defaults. Replica and coordinator share one JVM, so O1/O2 cannot be split
   between them. The 15 s Byteman hold is only in the held read of each arm. The S7 reads were sequential, not concurrent (E3's ×32 was not tested).
7. **Core question** — R2 steps: (1) the reads succeed at every M with all items returned, so no limit stops them (part 3, P1); (2) allocation and held heap
   follow M linearly across 10⁵–10⁷ (part 3, P2/P3); (3) the held heap is ~150 B per item, ~19× the serialized and ~38× the on-disk size (P3/P4); (4) the
   same bytes as one blob cost 0.12–0.16× as much, so the cost is per item (P5); (5) the instrument sees a binding limit: with the read-size threshold on,
   the large reads are refused before the coordinator materializes them (P6); (6) with the guardrail binding on the ordinary user, appends still grow the
   set to 200·T and the read costs the same (P7). The `items_per_collection` constraint does not cap the read heap of the stored collection; at defaults
   nothing does.

**Conclusion (one line):** R7 row 1 — **confirmed** (clauses a–d).

## 5. Self-check of run 1 — AI

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `yaml-diff-L1.txt` / `-L2.txt` re-read (only directories, two timeouts, auth lines, and in L2 the guardrail pair); `summary-raw.txt` READTHRESHOLDS-DEFAULT `enabled=false localAbort=null`; SIZE lines all `SSTable count: 1`; `memory-L1.txt`/`-L2.txt` max 9.21/8.98 GiB, oom_kill column all 0; `byteman-pause-lines.txt` 7 begin lines (6 arms + P s5). |
| 2. Readings | yes | Recomputed h by hand from the `Total` lines of `histo-head/*.txt`: (1,605,607,056 − 76,287,168 − 254,128)/10⁷ = 152.9; S6 153.7; S5 148.4; G 153.7. |
| 3. Matched row | yes | `analysis.txt` "checks=30 pass=30 fail=0", each R6 condition present; P7 guard line re-read in `system-log-guard-and-readsize-lines.txt`. |
| 4. Excluded rows | yes | No `error` in the 9 default-arm read lines; P rejections only in the P lines (4th s6/s7 read). |
| 5. Observed vs. inferred | yes | The two inferred statements are explanations; the row needs neither. |
| 6. Deviations and gaps | yes | Heap and timeouts are in R3, frozen before the run; no step changed in run 1. |
| 7. Core question — logic | yes | Each R2 step maps to a passed R6 condition; the positive control moved (0.428) and the knob-on arm G matched the default arm. |

### 5.2 Run 2?

**No** — 2026-11-17. Every verdict statement is observed and the self-check settles all parts from run 1's files; the readings are tight (three alloc
reads per arm within 0.1 %, held per item 148–154 B across 100× of M).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** case file `undetermined` (2026-10-26); the recheck's real-memory estimate `negative` (2026-11-16). **Outcome class (recheck claim):** true negative.

**Claim tested** (recheck "Stage-4 claim to add", R1): with defaults (guard off, read thresholds off), one `SELECT` of a `set<int>` row grown by appends
to M items (M = 10⁵, 10⁶, 10⁷) raises the node's transient heap in proportion to M, roughly 200 B per item, with no limit stopping it; and with
`items_per_collection_fail_threshold` = T set the same holds at M = 200·T. "Confirmed" means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | not run: n/a — the claim is about a running node's heap during a native-protocol read (§1) | — | — | 2026-11-17 |
| Node (single real node, pc99) | **Confirmed** (R7 row 1, clauses a–d). Measured per item: **allocated 334–352 B**, **held 148–154 B** (the claim's "roughly 200" falls inside its frozen band [100, 400]; the measured value is ~150), on disk 4.0 B, serialized 8 B. At M = 10⁷ one read allocates 3.52 GB and holds 1.53 GB | **does not cap** — the guardrail counts only the written fragment and is not consulted on reads; at T = 5,000 a set reaches 10⁶ items and its read costs the same as at defaults; at defaults no read limit applies | run 1 + self-check | 2026-11-17 |

**Positive control:** `local_read_size_fail_threshold` = 64 MiB with `read_thresholds_enabled` = true rejected the 10⁶- and 10⁷-item reads (S5 accepted),
the coordinator never reached `newRow`, and the rejected 10⁷ read allocated 0.428 × the accepted one. Recorded alongside: even this binding limit does not
cap the replica's heap for a single row — the rejected read still allocated ~150 B per item (1.51 GB at 10⁷), because the size check runs per row after
the row is built (`ReadCommand.java:691-694, 709-722`; coordinator warning "1 nodes loaded over 1489193880 bytes").

**Feedback filed:** one dated line in the case file's section D pointing here (uncommitted). The design section `## Stage-4 design for the recheck claim
(2026-11-17)` was appended to the case file before the run. Not edited: `oom-lead-list.md`, `_INDEX.md`, any HANDOFF (per the session's instructions).
For stage 3: the claim's per-item figure should name the quantity — Cassandra's `unsharedHeapSize` estimate (155–174 B/item here), the held heap
(~150 B/item) or the allocation (~345 B/item); and a 10⁷-item read at an 8 GiB heap already drives G1 to evacuation failure and a full GC on its own
(sequential reads; E3's 32 concurrent reads were not tested).
