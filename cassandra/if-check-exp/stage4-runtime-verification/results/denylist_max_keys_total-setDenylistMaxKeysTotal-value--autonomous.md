# denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous — stage-4 results  <!-- file: results/denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous.md -->

> **Case:** [`denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous`](../../stage3-ai-deep-read/cases/denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26. **Unit: Confirmed — caps only on some paths (bypass). Cluster: Confirmed — caps only on some paths (bypass).**
>
> **Outcome class:** undetermined — the stage-3 estimate (`undetermined`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/`](../harness/denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `529e3473…7a59` (DD batch 4). Frozen after the step-0 audit's seventeen amendments (2026-10-26): sha256 **`969d5e9191d196b7510cfc51bcac8bbff2e548a9663a95ee2bcc8b1fccb238b4`**, at which the unit tier's run 1 ran. Runbook fix 1 (B3d (iii)/B3e, the refresh-read instrument, found by the cluster shakedown before cluster run 1; §9a unchanged) gave **`7d8d3261bb3cb0ab89e126682fa645f56bb78b121f02eb5435a32969e54685e5`**, at which the cluster tier's run 1 ran. Both are new rows in `_INDEX-advisor.md` §2. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/`](../harness/denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/): `DenylistTotalTest.java` (B2e's skeleton plus the B2e amendment), `unit-run.sh`; `Jmx.java` (B3b verbatim, byte-identical to the sister case's copy), `make-node-conf.sh` (the sister case's, clone and node paths changed), `cluster-run.sh` (adapted from the sister case's; runbook fix 1). Not committed. Instrument checks: (i) the audit probe [`audit/EntrySize.java`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/audit/EntrySize.java) built `PartitionDenylist$DenylistEntry` with the build's classes, measured it with `ObjectSizes.measureDeep`, and computed the token order of the five `(ks, tN)` denylist partitions under each partitioner ([`audit/audit-entrysize.txt`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/audit/audit-entrysize.txt)); (ii) the test class compiled in the run clone (`BUILD SUCCESSFUL`, [`audit/compile-summary.txt`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/audit/compile-summary.txt)); (iii) two cluster shakedowns (5 × 400 keys, P = 400, T = 400, 2000, 400) ran every step; the first exposed defect 1 ([`shakedown/defect1-evidence.txt`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/shakedown/defect1-evidence.txt)), the second checked the fix (load reads 1 and 5, sampler 5 per access phase, drift 5.9 KB; [`shakedown/shake2-summary.txt`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/shakedown/shake2-summary.txt)); their readings are not judged. |
| **Tiers and values** | Unit (B2): five tables × 2000 keys of 2 KiB; P = 2000; setter values 0, −1 (rejection); T = 1000, 3000, 10000 (default), each a full load (phase A) followed by a timed-refresh phase with `denylist_refresh` 1 s (phase B); three runs. Cluster (B3): one node, 2 GiB heap, five tables × 4000 keys of 8 KiB, P = 4000, `denylist_refresh` 20 s; 0 (rejection), T = 4000, 20000, 4000, each set over JMX, followed by a JMX `loadPartitionDenylist` (phase A) and, after 25 s, an access phase of reads to the five tables (phase B). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone.

**What the source says, derived at the audit (the brief's questions).**
- *The setter.* `setDenylistMaxKeysTotal` (`DatabaseDescriptor.java:4825-4830`) rejects `value <= 0` at `:4827`; reached over JMX through the write-only attribute `DenylistMaxKeysTotal` (`StorageProxyMBean.java:83`, `StorageProxy.java:3116-3119`; no getter, so read back from `system_views.settings`). Default 10000 (`Config.java:780`).
- *The only path that applies the total* is the full `load()` (startup `initialLoad`, `PartitionDenylist.java:132-163`; JMX `loadPartitionDenylist`, `StorageProxy.java:3068-3071`) via `getDenylistForAllTablesFromCQL` (`PartitionDenylist.java:463-513`). It walks the tables in the order `SELECT DISTINCT ks_name, table_name` returns them — the token order of the `(ks_name, table_name)` partitions — gives each `limit = min(P, T − processed)` (`:497`), adds the keys held (`:499-500`), and once `T − processed <= 0` puts an **empty** entry with one `Hit limit …` ERROR per remaining table without reading it (`:484-493`). A table read with `limit < P` that has more rows logs `has exceeded the global allowance of (T)` (`:419-431`). **Split:** first-come in token order. Computed order: t1…t5 under ByteOrdered (unit), t1, t5, t4, t3, t2 under Murmur3 (node).
- *Paths that ignore the total* (read with `limit = P`, `:388-391`): the timer refresh (`refreshAfterWrite(denylist_refresh)`, `:185`; `reload`, `:201-213`), started by the first `denylist.get` after the interval, which every read, write and `isKeyDenylisted` of the table reaches (`:302-329`, `StorageProxy.java:1870-1880`, `:3166-3177`); the refresh after a JMX add/remove (`refreshTableDenylist`, `:243-286`, `:515-528`); and the cache-miss load of a table with no entry (`:190-198`). An entry emptied by the total is refreshed like any other. The class Javadoc (`:74-83`) calls this an accepted edge case.
- *What the held count can reach after refresh:* `Σ min(P, M_i)` over the tables accessed — up to P × (tables accessed), independent of T. Here 10000 keys (unit, 10× T = 1000) and 20000 keys (node, 5× T = 4000).
- *Heap per key* (build's `measureDeep`): 2 KiB keys under ByteOrdered 4,208 B (the `BytesToken` copies the key); 8 KiB keys under Murmur3 8,296.2 B; an empty entry 160 B.
- *Falsifiability of B1.* Part (1) is refuted by a phase-A count above `min(T, ΣM)`. Part (2), as filed, was not refutable: "phase B = phase A" matched both the refutation row and "refresh not triggered". The audit added refresh evidence (unit: entry objects replaced, read count; node: dl-table reads of `partition_denylist`), so "phase B = phase A with the refresh shown to have run" is a Refuted row.
- *Instruments vs quantities.* Every predicted quantity is persistent (held until the next load or refresh); the refresh event itself is transient, so it is read from a persistent trace (a replaced object, a read count, a sampler).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: keys held in the heap cache across tables, a count with a derivable byte size. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 1000, 3000, 10000 (default); B3b: 4000, 20000, 4000 (two values plus reversal; the unit tier has three). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit measured only counts and raw bytes; `measureDeep` per entry added. Cluster: live heap after GC. |
| A. Core question | usage driven to the limit and past it | Met | ΣM = 10000 > T = 1000, 3000 and = 10000; node ΣM = 20000 > 4000, = 20000. |
| B. Logic | each step says what it establishes | Partly | Phase A / phase B stated in B1; left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Totals stated; per-table split, deep size, ERROR lines and bands derived and added. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Rows had meanings without verdicts; row 2 (refuted) indistinguishable from row 4 (refresh not run); missing partial refresh, read failure, bytes, ERROR lines, drift, read-back, run disagreement. Added (B2g, B3g), both phases' outcomes covered. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Row 1 now needs the exact `Hit limit` / `global allowance` lines and the refresh evidence. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Read failure leaving an empty entry; the cache-miss path (no `dl` read before a load); baseline after the ingest with a drift control. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Output location, `printf`, read thresholds, read-back. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | **The B2e skeleton does not compile** (`static long total()` and `@Test void total()`); renamed. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Mapped to this host. |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit 20 MB rows, 42 MB entries in a 1 GiB JVM; node 328 MB CSV, 166 MB of entries in 2 GiB, 136 GiB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `DatabaseDescriptor.java:4772-4783`, `:4825-4830`; `StorageProxy.java:1870-1880`, `:3062-3177`; `StorageProxyMBean.java:73-84`; `PartitionDenylist.java:74-83`, `:92-111`, `:132-238`, `:243-329`, `:385-528`; `Config.java:759-786`; `SystemDistributedKeyspace.java:175-183`. All match. Not caught at the audit: the `system_schema` entries that cqlsh adds (defect 1). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B1: paths that apply/ignore the total, the split, the reachable count, refresh evidence | Amendment 2026-10-26 (uncommitted) | Brief; part (2) not falsifiable. |
| 2 | B2a: this host's clone and runner | Amendment 2026-10-26 | CloudLab path. |
| 3 | B2c: ByteOrdered and its key copy; token order and per-table counts; no `dl` access before load; read thresholds | Amendment 2026-10-26 | Decides B2f; known failure mimics the cap. |
| 4 | B2d: test log; per-table count/raw/deep; `replaced`, `reloadReads`; ERROR texts | Amendment 2026-10-26 | Group A, part (2). |
| 5 | B2e: rename the test method; `println`; disable read thresholds; print the readings | Amendment 2026-10-26 | Does not compile as filed. |
| 6 | B2f: exact totals, per-table counts, deep 4,209,008 · 12,625,408 · 42,082,800 B ±2 %; 7 `Hit limit` + 2 `global` lines; `replaced=5`, `reloadReads ≥ 5` | Amendment 2026-10-26 | Derived. |
| 7 | B2g, B2h: verdicts per row; added rows; controls' evidence | Amendment 2026-10-26 | Group B. |
| 8 | B3a: one node on this host, `denylist_refresh: 20s`, total default | Amendment 2026-10-26 | CloudLab paths. |
| 9 | B3b: write-only attribute; read-back | Amendment 2026-10-26 | No getter. |
| 10 | B3c: CSV path, 4000 rows per table; no `dl` read before load | Amendment 2026-10-26 | Cache-miss path. |
| 11 | B3d: histogram Total; **baseline after the ingest** with a 30-s drift control; refresh evidence (read count); segments | Amendment 2026-10-26 | Sister case's failure. |
| 12 | B3e: run order, shakedown | Amendment 2026-10-26 | Open. |
| 13 | B3f: derived ΔA_4000 = 31.65 MiB, ΔA_20000 = ΔB = 158.24 MiB; bands [23.65, 39.65] and [118.68, 197.80] MiB; 4 `Hit limit` lines per T = 4000 load; load reads 1 / 5; refresh reads ≥ 5; drift ≤ 6 MiB; reversal ≤ 6 MiB | Amendment 2026-10-26 | Derived. |
| 14 | B3g, B3h, B4: verdicts per row; added rows; controls; host paths | Amendment 2026-10-26 | Group B. |
| 15 | Test the add/remove refresh path and the cache-miss path against the total | Left for stage 3 | B1 names only the timed refresh. |
| 16 | A2 could note that `system_schema` (not excluded by `canDenylistKeyspace`) gets cache entries from every client's schema reads | Left for stage 3 (section D) | Found by defect 1; not in B1. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 EDT (clone and build 00:32–00:34; audit 00:35–00:40; compile check 00:40; unit run 1 00:43–00:45; shakedowns 00:45–00:50 and 00:51–00:57; cluster run 1 00:58–01:05) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 137 GiB free at start (136 GiB at the cluster runs); loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used); ports 7000, 7199, 9042, 9091 free; no Cassandra daemon before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork (1 GiB). Node: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (`-Xms2G -Xmx2G -XX:+UseG1GC` in `JVM Arguments`) |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`): `$W/cassandra-run26` (`ant -Dlocal.repository=$W/m2 build-test`, 48 s); `W=~/Library/Caches/stage4` |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-dlmt` (data, commit log, the 328 MB CSV), wiped before and after; JMX 7199 |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/denylist_max_keys_total-setDenylistMaxKeysTotal/` — `clone.log`, `build-test-run26.log`, `unit-compile/`, `unit-r{1,2,3}/` (ant log, JUnit XML, test log, `stdout.txt`, `error-lines.txt`), `cluster-shake/`, `cluster-shake2/`, `cluster-run1/` (`commands.log`, `summary.txt`, `settings.txt`, `rows-t*.txt`, `copy.log`, `set0*.txt`, `node/` node logs, `pre/`, `ingest/`, `ingest2/`, per label `L*-T*/` with `set.txt`, `readback.txt`, `load.txt`, `tablestats-r{0..3}.txt`, `segment-{A,B}.log`, `access.txt`, `profileload-access.txt`, `A/` and `B/` `heap_info.txt` and `histogram.txt`); audit probe `~/Library/Caches/stage4/audit-run26/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | first cluster shakedown, before cluster run 1 | B3d (iii) / B3e, `Local read count` as the refresh-read instrument | The count rose by 9 more than the dl-table reads in every window with a cqlsh command (load windows 10 and 14 for 1 and 5 dl reads; access windows 14 for 5): each cqlsh connection reads the `system_schema` tables, which `canDenylistKeyspace` does not exclude (`PartitionDenylist.java:292-300`), so each such read adds an empty cache entry (cache-miss load, `:190-198`) or refreshes one, and reads that table's empty denylist partition; 9 `DenylistEntry` instances after the ingest, 14 after an access phase ([`shakedown/defect1-evidence.txt`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/shakedown/defect1-evidence.txt)). | r0 read after the cqlsh read-back (no CQL client between r0, r1, r2); the access-phase dl-table reads counted by the READS sampler (`nodetool profileload -a READS … 40000`), which samples only non-empty partitions (`SinglePartitionReadCommand.java:911-917`, `:1052-1055`); `Local read count` r3 − r2 still recorded. Predicted quantities, values and rows unchanged. Second shakedown: 1 and 5 load reads, 5 sampler reads per access phase ([`shakedown/shake2-L1-profileload-access.txt`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/shakedown/shake2-L1-profileload-access.txt)). The cluster run 1 had not started; the unit tier is unaffected. | 2026-10-26 | sha256 `7d8d3261…85e5` |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/run1/unit/) (`r1`–`r3`: `commands.log`, `summary.txt`, `stdout.txt`, `error-lines.txt`, `junit-testsuite.txt`); [`run1/cluster/`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/run1/cluster/) (`commands.log`, `summary.txt`, `settings.txt`, `rows-t*.txt`, `copy-tail.txt`, `set0*.txt`, `system-log-denylist-lines.txt`; `pre/`, `ingest/`, `ingest2/`; per label `set.txt`, `readback.txt`, `load.txt`, `access.txt`, `profileload-access.txt`, `tablestats-readcount.txt`, `segment-{A,B}.log`, `A/` and `B/` `heap_info.txt`, `histogram-excerpt.txt`).

### 4.1 Readings

**Unit tier** (ByteOrdered partitioner, `rows tN=2000` for t1…t5, `getterTotal0=10000`; JUnit 1 test, 0 failures, 0 errors in each run; r1, r2, r3 identical except `reloadReads` and loop time)

| Test or assertion | r1 = r2 = r3 | Predicted | Evidence |
|---|---|---|---|
| set 0 / set −1 | `REJECTED 0 getter=10000`, `REJECTED -1 getter=10000`, `denylist_max_keys_total must be a positive integer.` | rejected, getter 10000 | `run1/unit/r*/stdout.txt` |
| T = 1000 phase A: per table t1…t5 / total / raw / deep | 1000, 0, 0, 0, 0 / 1000 / 2,048,000 / **4,209,008** | same; deep ±2 % | `stdout.txt` |
| T = 3000 phase A | 2000, 1000, 0, 0, 0 / 3000 / 6,144,000 / **12,625,408** | same | `stdout.txt` |
| T = 10000 phase A | 2000 × 5 / 10000 / 20,480,000 / **42,082,800** | same | `stdout.txt` |
| phase B, every T | 2000 × 5 / 10000 / 20,480,000 / **42,082,800**; `replaced=5` | same; `replaced=5` | `stdout.txt` |
| `reloadReads` (T = 1000, 3000, 10000) | r1 14, 10, 10; r2 14, 13, 10; r3 12, 10, 10 | ≥ 5 | `stdout.txt` |
| phase-B loop | 4,538–4,562 ms (stable after the first poll) | ≤ 12 s | `stdout.txt` |
| `Hit limit …` lines | 7: `Processed 1000` for t2, t3, t4, t5; `Processed 3000` for t3, t4, t5 | exactly these 7 | `error-lines.txt` |
| `has exceeded …` lines | 2: `dl_ks/t1 … global allowance of (1000)`, `dl_ks/t2 … global allowance of (3000)`; no `per-table` line | exactly these 2 | `error-lines.txt` |
| `Error reading …` lines | 0 | 0 | `error-lines.txt` |

**Cluster tier** (one node, Murmur3; settings read back: `partition_denylist_enabled true`, `denylist_consistency_level ONE`, `denylist_max_keys_per_table 4000`, `denylist_max_keys_total 10000`, `denylist_refresh 20s`, reads/writes/range reads `true`; `set 0` → `REJECTED 0 … IllegalArgumentException: denylist_max_keys_total must be a positive integer.`, read-back 10000; COPY `20000 rows imported … 3.574 seconds (0 skipped)`; `count` 4000 for each of t1…t5)

| Label | Set / read-back | Load reads (r1 − r0) | `Hit limit` lines (load) | dl refresh reads (sampler) / quiet (r2 − r1) | live heap A | ΔA | live heap B | ΔB | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| pre (empty load, before ingest; recorded) | — | — | 0 | — | 50,703,400 | — | — | — | `cluster/pre/` |
| used₀ (after COPY + flush, cache empty) | — | — | — | — | 292,366,552 | — | — | — | `cluster/ingest/` |
| used₀′ (30 s later; drift control) | — | — | — | — | 292,367,824 | **+1,272 B** | — | — | `cluster/ingest2/` |
| T = 4000 | `OK 4000` / 4000 | 1 | 4 (`Processed 4000`: t5, t4, t3, t2) | 5 (t1…t5 one each) / 0 | 325,728,392 | **31.82 MiB** | 458,461,344 | **158.40 MiB** | `cluster/L1-T4000/` |
| T = 20000 | `OK 20000` / 20000 | 5 | 0 | 5 / 0 | 458,471,048 | **158.41 MiB** | 458,485,888 | **158.42 MiB** | `cluster/L2-T20000/` |
| T = 4000 (again) | `OK 4000` / 4000 | 1 | 4 (t5, t4, t3, t2) | 5 / 0 | 325,755,424 | **31.84 MiB** | 460,079,896 | **159.94 MiB** | `cluster/L3-T4000/` |

Derived at the audit: ΔA_4000 = 31.65 MiB, ΔA_20000 = ΔB = 158.24 MiB. No `has exceeded` line and no `Error reading` line anywhere; one `Loaded` line per
load (five in all: startup, pre, three loads); no denylist line in any access phase. `Murmur3Partitioner$LongToken` instances: 183 at used₀, 4,183
after each T = 4000 load, 20,183 after every refresh and after the T = 20000 load (+4,000 and +20,000 tokens). `[B` above used₀: 32,871,920 B at
ΔA_4000 (8,218 B per key) and 164,210,440 B at ΔB_4000 (8,210 B per key; expected 8,208). `DenylistEntry` instances 5 after a load, 14 after an
access phase (the five dl entries and nine `system_schema` entries, defect 1). `Local read count` r3 − r2 = 14 in each access phase (5 dl + 9
`system_schema`, recorded). The ingest moved the heap by +230.47 MiB above `used_pre` (the flushed memtable: 20,013 `BTreeRow`), constant afterwards
(20,013 at every label except the last B, 20,982).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — three runs, each 1 test, 0 failures, 0 errors [observed: `run1/unit/r*/junit-testsuite.txt`]; `rows tN=2000` for each table, per-table getter 2000 at each T, refresh 1 s [observed: `stdout.txt`]; no `Error reading` line [observed: `error-lines.txt`]. Valid.
2. **Readings** — nothing unusual; `reloadReads` differ between runs (10–14), as expected for repeated 1-s refreshes during the poll loop [observed].
3. **Matched row** — B2g row 1, "Phase A = min(T,10000) and phase B = 10000 for all T", with the B2f amendment's (i)–(v): rejections with getter 10000 and the message; phase-A totals 1000 · 3000 · 10000 with per-table counts 1000/0/0/0/0 and 2000/1000/0/0/0; raw = 2048 × total; deep exactly the computed 4,209,008 · 12,625,408 · 42,082,800 B (0.0 % off); phase B 10000 (2000 per table), deep 42,082,800, `replaced=5`, `reloadReads` ≥ 10; exactly the 7 `Hit limit` and 2 `global allowance` lines and no `per-table` line; in all three runs [observed: `stdout.txt`, `error-lines.txt`].
4. **Excluded rows** — row 2 (phase B = phase A with the refresh run): phase B 10000 ≠ 1000, 3000 [observed]. Row 3 (phase A = 10000): 1000, 3000 [observed]. Row 4 (refresh not triggered): `replaced=5` [observed]. Row 5 (0 or −1 accepted): rejected [observed]. Added rows: refresh ran with neither count — 10000 is the per-table sum; partial refresh — `replaced=5`; read failure — none; deep off — 0.0 %; ERROR lines off — exact; getter off — 10000 / T; runs disagree — identical; compile/test failure — none [observed].
5. **Observed vs. inferred** — that phase B's growth is the per-table reload ignoring the total is inferred from the source (`:206` → `:388-391`); it is supported by the replaced objects, the reload reads, and the absence of any ERROR line in phase B (a reload with `limit = P = M` exceeds nothing).
6. **Deviations and gaps** — instruments added at the audit (per-table/deep/identity/reads); read thresholds disabled (known from the sister case). The add/remove and cache-miss paths are derived but not run.
7. **Core question** — right after a full load the total caps the cache exactly: the held keys and heap follow T (1000 → 3000 → 10000 keys; 4.2 → 12.6 → 42.1 MB), the excess tables are emptied with one ERROR each, and 0 and −1 are refused. Within seconds of the refresh interval, every accessed table is reloaded with the per-table cap only, and the cache returns to 10000 keys (42.1 MB) for every T — 10× the cap at T = 1000. The total caps usage only on the full-load path.

**Conclusion (unit tier):** B2g row 1 — **confirmed** (B1 parts 1 and 2).

**Cluster tier**

1. **Validity** — node up with the 2 GiB G1 heap [observed: `summary.txt` `JVM`]; settings read back, including `denylist_refresh 20s` and per table 4000 [observed: `settings.txt`]; 4000 rows per table [observed: `rows-t*.txt`, `copy-tail.txt`]; each set read back equal to T [observed: `*/readback.txt`]; no read error, one `Loaded` line per load [observed: `system-log-denylist-lines.txt`]; drift control +1,272 B [observed: `ingest/`, `ingest2/` histograms]; all 30 access reads exit 0 [observed: `*/access.txt`]. Valid.
2. **Readings** — the last ΔB (159.94 MiB) is 1.54 MiB above the first, with 969 more `BTreeRow` in that histogram than at every other label [observed: `L3-T4000/B/histogram-excerpt.txt`]; inside the 6-MiB reversal bound.
3. **Matched row** — B3g row 1, "ΔA follows T, ΔB ≈ 160 MiB for both T", with the B3f amendment's (i)–(vii): ΔA_4000 31.82 / 31.84 MiB in [23.65, 39.65], ΔA_20000 158.41 and every ΔB (158.40, 158.42, 159.94) in [118.68, 197.80], all within 1.1 % of the derived values; read-backs = T; `set 0` rejected with read-back 10000; 4 `Hit limit … Processed 4000` lines at each T = 4000 load and none at T = 20000; no `has exceeded`, no `Error reading`; load reads 1 / 5 / 1; quiet reads 0; sampler 5 dl refresh reads (one per table) in each access phase; drift +1,272 B; reversal +0.03 / +1.54 MiB [observed: the files of 4.1].
4. **Excluded rows** — row 2 (ΔA and ΔB both follow T): ΔB_4000 158.40 MiB, outside the 31.65-MiB band [observed]. Row 3 (ΔA_4000 ≈ 160 MiB): 31.82 [observed]. Row 4 (refresh not seen): 5 sampler reads, ΔB ≠ ΔA [observed]. Row 5 (0 accepted): rejected [observed]. Added rows: refresh ran with neither count — ΔB in the 158-MiB band; partial refresh — 5 of 5 tables; drift — 1,272 B; read error — none; rows/read-back/refresh setting — as designed; ERROR lines or load reads off — exact; band failure or not reversible — none; node failure — none [observed].
5. **Observed vs. inferred** — that the 9 extra entries and reads are `system_schema` tables touched by cqlsh is inferred from the source (`canDenylistKeyspace`, `:292-300`) and the counts (9 entries after the ingest, 14 after an access phase); it affects only the recorded `Local read count`, not the matched row.
6. **Deviations and gaps** — runbook fix 1 (before the run) changed the access-phase read instrument; the baseline is after the ingest (audit). The add/remove and cache-miss paths are not run on the node.
7. **Core question** — on a node, a JMX full load with T = 4000 holds one table's 4000 keys (31.8 MiB above the post-ingest heap, +4,000 tokens) and empties the other four with an ERROR each; T = 20000 holds all 20000 (158.4 MiB). Reads to the tables after `denylist_refresh` reload each table with the per-table cap only, and the heap rises to 158.4 MiB at T = 4000 as well — five times the total — and returns to 31.8 MiB only at the next full load.

**Conclusion (cluster tier):** B3g row 1 — **confirmed** (B1 parts 1 and 2 on a node).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/run1/selfcheck.py), written before any run-1 reading and
independent of the harness (it re-reads the JUnit XML and the raw test logs; the node's raw `system.log`, checking that each per-phase segment is a
verbatim piece of it and that the segment counts add up to the whole; the raw histograms, tablestats, sampler, Jmx and cqlsh outputs): **217 checks,
0 failed**; unit row 1 and cluster row 1 ([`run1/selfcheck.out`](denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous/run1/selfcheck.out)).
Changes after it was written, all before cluster run 1: (a) to read the instrument of runbook fix 1 (the sampler file; `Local read count` r3 − r2
printed only); (b) a parser fix found by running it on the second shakedown's files: an empty per-phase log segment (no denylist line in an access
phase) is accepted. No check or bound was changed; it was not changed after run 1.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit counts; settings, row counts, read-backs, drift, `Loaded` lines from the raw files. |
| 2. Readings | yes | The last ΔB and its extra `BTreeRow` re-read in the histogram excerpt; within the reversal bound. |
| 3. Matched row | yes | Unit: every row-1 check passes in r1–r3. Cluster: every row-1 check passes, including the bands, ERROR lines per segment, load/quiet/sampler reads, drift and reversal. |
| 4. Excluded rows | yes | Phase B / ΔB ≠ phase A; refresh evidence present; ERROR lines per load from the raw `system.log`. |
| 5. Observed vs. inferred | yes | The `system_schema` explanation is not used for the row. |
| 6. Deviations and gaps | yes | Stated. |
| 7. Core question | yes | Setter → `limit = min(P, T − processed)` on load → held keys (exact counts, per-table split, ERRORs) → heap (deep exact; live heap within 1.1 %); then refresh with `limit = P` → per-table sum, with the refresh shown to have run. |

### 5.2 Run 2?

**No** — decided 2026-10-26. Both tiers rest on exact or near-exact readings (unit: identical counts and deep sizes in three runs; node: every
quantity within 1.1 % of its derived value), observed directly with refresh evidence, and the self-check holds in every part. The result confirms a
bypass that the source documents (`PartitionDenylist.java:74-83`).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** undetermined.

**Claim tested:** "1. Right after a full `load()` with total cap T and per-table cap P, the cache holds `min(T, Σ min(P, M_i))` keys, so heap follows T.
2. After `denylist_refresh` has elapsed and each table has been accessed, the cache holds `Σ min(P, M_i)` keys whatever T is, so heap no longer follows
T." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: phase A = 1000 · 3000 · 10000 keys, per-table split first-come in token order, deep exactly as computed; phase B = 10000 keys for every T with all five entries replaced; 0 and −1 rejected; 7 `Hit limit` and 2 `global allowance` lines as derived; three identical runs) | caps only on some paths (bypass) | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (row 1: ΔA = 31.82 / 158.41 / 31.84 MiB for T = 4000 / 20000 / 4000; ΔB = 158.40 / 158.42 / 159.94 MiB after 5 dl refresh reads each; 4 `Hit limit` lines per T = 4000 load; `set 0` rejected; drift 1.3 KB) | caps only on some paths (bypass) | run 1 + self-check | 2026-10-26 |

**Feedback filed:** the case file's section D (uncommitted); the seventeen step-0 amendments and runbook fix 1 (B3d/B3e) are in the case file,
dated, with the two sha256 values as new rows in `_INDEX-advisor.md` §2; `_INDEX-advisor.md` §1 Stage 4 column and the coverage line updated. The
Estimate line is left as filed (`undetermined`); the runs resolve it as a bypass, recorded here and in section D. No section was amended for a
refutation (none occurred).
