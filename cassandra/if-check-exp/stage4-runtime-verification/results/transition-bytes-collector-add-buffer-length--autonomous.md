# transition-bytes-collector-add-buffer-length--autonomous — stage-4 results  <!-- file: results/transition-bytes-collector-add-buffer-length--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`transition-bytes-collector-add-buffer-length--autonomous`](../../stage3-ai-deep-read/cases/transition-bytes-collector-add-buffer-length--autonomous.md)
>
> **Status:** verdict filed 2026-10-26 (run 1, unit then cluster, self-checked; no run 2). Estimate negative. Unit **Confirmed — does not cap**; cluster **Confirmed — does not cap**. Run by the autonomous stage-4 session (tag tc) on `pc07` (node0).
>
> **Outcome class:** **true negative** (stage-3 estimate `negative`; stage-4 effect on the constraint: `does not cap`, both tiers) — [definition](../README.md#outcome-class)
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked in the repository at HEAD `e776524`. As filed (2026-10-26): written by the stage-3 agent. **Frozen version (after the audit amendments R1-R8, dated 2026-10-26 in the case file, written before any reading and before any harness run):** sha256 `ed475293bde40b537f9a537005f7793ba18005ca3188e9f6e186c81a6706e9e0`; frozen prediction and conclusion tables (B2f, B2g, B3f, B3g text extracted with `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p'` and the B3 pair, last line of each dropped): sha256 `332bdbd313f350b6451e4359ca799184650c95a6d9f4538ab3f2b6b040af7fcf` (copies `~/s4-b7-tc-logs/case-frozen.md`, `frozen-tables.txt`). This was version 1 (before the harness shakedowns). **Version 2 = the frozen version for run 1 (and the hash for `_INDEX.md` before the section D feedback is filled): `22eb4a24e28d1e92191a1ccaf50b80eaa4359b1004e454257cc49db49a48ef40`** (copy `~/s4-b7-tc-logs/case-frozen-v3.md`): version 1 plus two runbook-defect amendments from the cluster shakedowns, both before run 1 and both in B3a only (D1 `storage_compatibility_mode: NONE`; D2 `PasswordAuthenticator` and an ordinary role, see section 3). The prediction and conclusion tables are unchanged: sha256 of the extracted tables is `332bdbd313f350b6451e4359ca799184650c95a6d9f4538ab3f2b6b040af7fcf` for versions 1 and 2 (and after the feedback). After the verdict the case file's section D was filled, which changes only the whole-file hash: `b16a659340073d3b2761bbd8d6579bf2b5415327b853fdd3154a28dbabbda06f` (version 2 plus section D). |
| **Harness** | `harness/transition-bytes-collector-add-buffer-length--autonomous/` (written 2026-10-26 after the freeze, not committed; the orchestrator commits). Files and what checked each: its README. **Instrument checks and shakedowns (not readings; their output was looked at, so the harness fixes below were made after seeing it, and none touches a prediction):** shakedown 1 (unit): compiled and ran; the analyzer's two expectation slips were fixed (Java prints `true`, not `True`; a drained collecting iterator ends with `pos` = -1, because the root frame pops without an add). `instr-check.sh`: the unit test under `collector.btm` gave COLL lines (ctor count up to 43,000, add count up to 540,810,000) and LIVE lines, so the rules fire on the collector class when it is used. Cluster shakedowns 1-6 at `TC_SCALE=50`: (1) the node refused `bti` under `CASSANDRA_4` (D1); (2-4) with `AllowAllAuthenticator` the 8191-byte and 40960-byte values were accepted under a 1KiB threshold and SAI skipped them at flush (D2); (5) with PasswordAuthenticator and the ordinary role the writes were rejected with `Guardrail sai_string_term_size violated`; also found: Byteman appends to an existing trace file (the harness now deletes it at each lifetime start), the rejected writes log one rate-limited `ERROR ... Guardrail sai_string_term_size violated` line (counted apart from other errors), and a self-check regex matched `OutOfMemoryError` in the JVM-arguments line. (6) all four lifetimes end to end, analyzer and self-check ran. |
| **Tiers and values** | Both tiers. Unit: L in {8, 32, 33, 1024, 8192, 65535} (also 131072 standalone), `getMaxTerm`/`getMinTerm`/`collecting=true` iterator, guardrail 1KiB/8KiB/64KiB, `-Xmx` 256m/512m/1g. Cluster: four lifetimes T1k, T8k, T64k (bti), BIG (big format, 8KiB), workloads W1-W4 (B3c). Tree `~/s4-b7-tc`, run data `~/s4-b7-tc-run` (local disk), logs `~/s4-b7-tc-logs`; port slot 1: loopback 127.0.1.1, JMX 7110, Byteman 19110, native 9042. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A1/A2: heap bytes of a transient scratch `byte[]` (initial 32 B, hard-coded); no configured constraint exists; the byte size is derivable (capacity of the array). |
| A. Core question | knob varied, >= 3 values incl. default - or another approach, with the reason | Met | B1/B2b/B3b: the collector has no knob, so the design varies the path length L (6 values), the nearest real caps (SAI term-size guardrail 1KiB/8KiB/64KiB, `-Xmx`) and the format, and asks whether capacity follows any of them. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met after R3/R5 | Unit: `bytes.length` of the real array (same-package subclass, reflection on the iterator's collector) and thread-allocated bytes; for the collector local to `getMaxTerm` only allocation is available (named in B2d). Cluster: filed JFR sampling replaced by an exact Byteman trace (R5). |
| A. Core question | usage driven to the limit and past it | Met (nothing to reach) | There is no limit; "past" is L=65535 (unit) and 60,000-byte pk plus 40 KiB terms (cluster); the only bounds are the guardrails, which the cluster workload crosses (W2, W4). |
| A. Core question | positive control present (negative-estimate file) | Partly -> Met after R4/R7 | Filed controls (`file_cache_size`, unit `validateTermSize`) were not runnable as written; replaced by the guardrail itself (moves accepted/rejected counts with its threshold) plus liveness counters for the instrument. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e are procedures; the claim in B1 and the rows of B2g/B3g carry the logic (mapped as the README allows). |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met after R3/R5 | Filed numbers wrong (300 KB bound, "20-30 reallocations", "1.2L"); restated from the library's own growth function (L <= cap <= L + L/8 + 10; S(65535) = 622,768 B). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly -> Met after R3/R5 | rows added for "knob-independent but outside the band" and for "instrument or load inadequate"; "counter capped but resource grows" is not applicable (no counter). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | the claim is that there is no ceiling and no disallow branch; direct evidence is the exact trace of constructions/`add` calls (zero) and the capacity table over L and knobs. |
| B. Logic | alternative explanations and their controls | Met | SAI threshold (guardrail control), format (BIG lifetime), `-Xmx`, instrument blindness (liveness counters). |
| C. Specific | a human can follow it from the intro and B1 | Met | Estimate, Ground, A3, B1, B2g/B3g. |
| C. Specific | an AI can run B2a-B2e / B3a-B3e without re-deriving the code path | Partly -> Met after R2/R6 | The test and the driver are described but not given (the harness supplies them); the `/tmp` and `rsync` steps and `pgrep -f` cleanup are replaced. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met after R5/R6 | Cluster volume and read time were unspecified per knob; set in B3c. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | none exists; unit test, Byteman rules, driver, JMX/trace analysis are step-1 work; JDK 11.0.32.1, Ant 1.10.12 on pc07; build of the copy `~/s4-b7-tc` done (`ant build-test` 1 min 12 s). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly -> Met after R6 | filed 20,000 x 60 KiB keys = 1.2 GB per knob and 10-minute reads x many combinations; now about 0.3 GB and 3 minutes of reads per lifetime, 4 lifetimes (about 30 minutes); local disk 36 GB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `Walker.java:437-462`, `ValueIterator.java:74,107,226,250`, `PartitionIndex.java:395-407`, `Config.java:941-944`, `StorageAttachedIndex.java:147,207-210,773-830`, `TrieTermsDictionaryReader`/`Writer`, `conf/cassandra.yaml:742,2246-2251` re-read; no production caller of `getMinTerm`/`getMaxTerm` on a `Walker` and no `collecting=true` constructor call in `src/java` (grep). Only `validateTermSize` line range corrected. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Citations: no change needed except `validateTermSize` 807-830 | Applied 2026-10-26 (case file B2h; not committed) | spot-check |
| R2 | Build and harness mechanics: `copy-source.sh`, in-memory trie, deep writer, `-Xmx` through a plain JUnitCore run | Applied 2026-10-26 (B2a) | `ant testsome` forks 1 GiB; recursion at depth 65535 |
| R3 | Lucene growth arithmetic: band L..L+L/8+10, S(65535) = 622,768 B, 59 grows; allocation as auxiliary bounds; new B2g row | Applied 2026-10-26 (B2c, B2f, B2g), before the freeze, from running `ArrayUtil.grow` alone | filed numbers contradicted the library |
| R4 | Unit control: `Guardrails.saiStringTermSize.failsOn` with the config setter | Applied 2026-10-26 (B2h) | `validateTermSize` needs an index instance |
| R5 | Cluster instrument: JFR sampling -> exact Byteman trace with liveness counters; rows B3f/B3g rewritten | Applied 2026-10-26 (B3d, B3e, B3f, B3g) | samples can miss a short-lived 32-byte array; zero samples is not zero calls |
| R6 | Cluster workload and time sized (W1-W4, 3-minute reads, 4 lifetimes) | Applied 2026-10-26 (B3c) | time and disk |
| R7 | Drop the `file_cache_size` control (`file_cache_enabled: false` by default) in favour of the guardrail | Applied 2026-10-26 (B3h) | the setting would not change a quantity the workload reads |
| R8 | Freeze the tables | Applied 2026-10-26 | protocol |
| R9 | The `Ground` header says the object is "not memory- or disk-significant"; no run-based change | Left for stage 3 | header text |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 10:06 EDT; cluster 10:08 to 10:28) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; shared with other stage-4 sessions (own tree, ports and loopback) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-187-generic | |
| JDK (`java -version`) | openjdk 11.0.32.1 2026-08-18 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b7-tc` by `copy-source.sh` at repository HEAD `e776524` (tag `cassandra-5.0.9`, local baseline), `ant build-test` BUILD SUCCESSFUL in 1 min 12 s (`~/s4-b7-tc-logs/build-test.log`); Lucene 9.7.0 | |
| Case-file commit / harness commit | case file untracked (sha256 in §1); harness untracked (md5 list `results/transition-bytes-collector-add-buffer-length--autonomous/run1/harness.md5`, taken before the cluster run; `unit-run.sh`, `CollectorGrowthTest.java` and `unit-analyze.py` as run in the unit tier; the analyzers and `selfcheck.py` were not edited after) | |
| Storage for node data | local disk `/dev/sda3` (`~/s4-b7-tc-run/`), 34 GB free at the start; peak data about 0.62 GB per lifetime; JDK heap 1 GiB (`MAX_HEAP_SIZE=1G`), G1; ports JMX 7110, Byteman listener 19110, native 9042, storage 7000 (SSL 7001), loopback `127.0.1.1` | |
| Full logs (path, outside the repo) | `~/s4-b7-tc-logs/run1/unit`, `~/s4-b7-tc-logs/run1/cluster/{T1k,T8k,T64k,BIG}` (trace, 8 class histograms, `system.log` segment, `gc-*.log`, yaml), `~/s4-b7-tc-logs/run1-cluster.out`; excerpts under `results/transition-bytes-collector-add-buffer-length--autonomous/run1/` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown 1 (not a reading) | B3a (default `storage_compatibility_mode`) | node start failed: `Selected sstable format 'bti' is not available when in storage compatibility mode 'CASSANDRA_4'` | `NONE` in all four lifetimes (case file B3a, dated) | 2026-10-26, before run 1; tables unchanged | none (case file untracked) |
| D2 | cluster shakedowns 2-4 (not readings) | B3a/B3c/B3h (clients) | with `AllowAllAuthenticator` every client is a superuser; `Guardrail.enabled(state)` skips the SAI term-size guardrail (`Guardrail.java:93-96`, `ClientState.java:602-605`), so 8191 B and 40960 B values were accepted under 1KiB and B3f (c) / B3h could not hold | PasswordAuthenticator + CassandraAuthorizer; schema as the superuser, loads and reads as an ordinary role (case file B3a, dated) | 2026-10-26, before run 1; tables unchanged | none |
| D3 | unit/cluster harness (not case file) | B2e step 4 / B3e step 5 | `-Xmx` cannot be lowered through `ant testsome`; Byteman appends to an old trace file; the guardrail's own rate-limited `ERROR` line would count as an error | JUnitCore runs for -Xmx; trace deleted at each lifetime start; the rejection line counted apart | 2026-10-26, harness only | none |

## 4. Run 1

**Scope:** both tiers, all values of the case file. Unit: `tc-unit.txt` (Ant fork, 1 GiB) and two `JUnitCore` runs (`-Xmx256m`, `-Xmx512m`), each 3 guardrail values x 6 lengths x 3 repetitions; 582 `TC` lines. Cluster: four node lifetimes, W1-W4, flush, compact, 180 s of mixed reads each, scale 1. **Command log:** `results/transition-bytes-collector-add-buffer-length--autonomous/run1/unit/summary.txt`, `.../cluster/session.log`, `.../cluster/cells.jsonl`.

### 4.1 Readings

**Unit tier** (`run1/unit/analysis.txt` has every `EXPECTED:` line; capacity = `bytes.length`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| JUnit `CollectorGrowthTest.grid` | 1 test, 0 failures, 0 errors in each of the three JVMs (-Xmx 1056 MB, 260 MB, 519 MB as `Runtime.maxMemory()`) | `unit/summary.txt`, `unit/tc-unit*.txt` line `env` |
| B2f (1) capacity in the band | 162 standalone readings all in band: L=8 and 32 -> 32; L=33 -> 40; L=1024 -> 1088; L=8192 -> 8296; L=65535 -> 69,368; equal to the library simulation; `pos` = L, 0 after L pops | `unit/analysis.txt`, `unit/tc-unit.txt` |
| B2f (1) knob independence | one capacity per L across the 3 guardrail values, 3 repetitions and the 3 JVMs | `unit/analysis.txt` |
| beyond 65535 | L=131072 -> 140,656; L=1,048,576 -> 1,172,112 (the simulation's values), no exception | `unit/tc-unit.txt` |
| B2f (2) allocation (auxiliary) | getMaxTerm/getMinTerm: 324 readings inside S(L)+L .. S(L)+L+65536; e.g. L=65535: 688,336 B per call (bounds 688,303 .. 753,839); L=8: 112 B (56 .. 65,592); result equals the key in all | `unit/analysis.txt` |
| B2f (3) collecting iterator | 54 readings: capacity = standalone capacity for the same L, 1 entry, value length L, `pos` -1 after drain | `unit/analysis.txt` |
| Controls (B2h) | `failsOn` fails exactly the probe sizes above 1024 / 8192 / 65536 at the three settings (e.g. 8193 fails at 8KiB and passes at 64KiB, while the collector's capacity at every L is the same under all three settings); `new byte[L]` costs L+16 B per call (L=65535: 65,552) | `unit/analysis.txt` |

**Cluster tier** (`run1/cluster/cluster-analysis.txt`, `cells.jsonl`; one row per lifetime)

| Lifetime (format; fail threshold) | Observable | Reading | Evidence (file) |
|---|---|---|---|
| T1k (bti; 1KiB) | COLL lines (collector constructions or `add` calls) | 0 | `T1k/trace-*.txt`, `cluster-analysis.txt` |
| T8k (bti; 8KiB) | COLL lines | 0 | same |
| T64k (bti; 64KiB) | COLL lines | 0 | same |
| BIG (big; 8KiB) | COLL lines | 0 | same |
| all four | liveness (last sampled count of constructions): Walker / TrieTermsDictionaryReader | T1k 222,000 / 74,000; T8k 182,000 / 60,000; T64k 188,000 / 62,000; BIG 71,000 / 71,000 (Walker classes seen: `PartitionIndex$Reader`, `PartitionIterator`, `TrieTermsDictionaryReader`; BIG only the SAI reader) | `cluster-analysis.txt` |
| T1k / T8k / T64k / BIG | writes accepted / rejected by the term-size guardrail: W1 (v 900 B) | 20,000 / 0 in all | `cells.jsonl`, `session.log` |
| | W2 (v 8,191 B) | T1k 0 / 5,000; T8k, T64k, BIG 5,000 / 0 | same |
| | W3 (pk 60,000 B, v 900 B) | 2,000 / 0 in all | same |
| | W4 (v 40,960 B) | T64k 2,000 / 0; T1k, T8k, BIG 0 / 2,000 | same |
| all four | reads (180 s, 8 threads): point reads / SAI `v = ?` queries, every one returned its row | T1k 73,391 / 74,056; T8k 60,393 / 60,647; T64k 62,404 / 62,690; BIG 71,547 / 71,797; 0 errors | `cells.jsonl` |
| all four | `du` of the data directory after compaction | T1k 292.7 MB; T8k 457.7 MB; T64k 622.7 MB; BIG 621.9 MB | `cells.jsonl` |
| all four | heap `byte[]` total after reads (class histogram) | T1k 21.8 MB; T8k 21.1 MB; T64k 21.2 MB; BIG 74.3 MB | `cells.jsonl`, `*/histo-after-reads-head.txt` |
| all four | `system.log` ERROR / OOM lines other than the guardrail rejection line | 0 (rejection `ERROR` lines, rate-limited: 2, 1, 0, 1) | `cells.jsonl`, `*/system-log-errors.txt` |

### 4.2 Conclusion and logic

1. **Validity** — **[observed: `cluster/*/cassandra.yaml`]** each lifetime ran with its intended `sai_string_term_size_fail_threshold` (1KiB, 8KiB, 64KiB, 8KiB), format (bti, bti, bti, big), `PasswordAuthenticator` and `storage_compatibility_mode: NONE`; **[observed: `cells.jsonl`, `selfcheck-cluster.txt`]** the node's JVM arguments show the Byteman agent and `-Xmx1G`, all 16 loads completed with every write either accepted or rejected by the guardrail (0 other errors), and the ordinary role was used (rejections occurred); **[observed: trace files]** the rules were live: Walker constructions occurred 71,000 to 222,000 times per lifetime and the SAI reader 60,000 to 74,000; the same rule file, run in the unit JVM where the collector is used, produced COLL lines (instrument check, `unit/instr-check-shake1*.txt`). The limit (the term-size guardrail) was crossed in W2 and W4 where predicted. The unit run is valid: all three JVMs ran the whole grid and the allocation control read L+16 B per call.
2. **Readings** — **[observed]** nothing contradicts another reading. Two points: `du` after compaction for BIG (621.9 MB) is 36 % above T8k (457.7 MB) with the same accepted writes, and equals T64k's although T64k accepted 82 MB more (W4); not investigated (format difference, or obsolete files not yet deleted after compaction); heap `byte[]` in BIG is 74 MB against 21 MB in the bti lifetimes (big-format index structures). Neither involves the collector. The drained collecting iterator ends with `pos` = -1 (the root frame pops without an `add`), as in `ValueIterator.advanceNode` (`ValueIterator.java:226-227`); B2f did not state it.
3. **Matched row** — unit B2g row 1, *"capacity depends only on L; same under all guardrail/-Xmx values — claim confirmed"*: **[observed: `unit/analysis.txt`]** one capacity per L over all 162 standalone readings, the 54 iterator readings equal them, the guardrail varied across 1KiB/8KiB/64KiB and the JVM across 260/519/1056 MB. The auxiliary row (band or allocation outside the prediction) was not needed: **[observed]** all bounds of B2f (1) to (3) hold. Cluster B3g row 1, *"no collector lines in any lifetime, liveness counters nonzero, accepted counts follow the thresholds"*: **[observed: `cluster-analysis.txt`]** 0 COLL lines in four lifetimes, liveness 71,000 to 222,000, 16 of 16 load outcomes as predicted in B3f (c), and the auxiliary (d) ordering T1k < T8k < T64k holds.
4. **Excluded rows** — unit: *capacity or allocation changes when a config knob changes (refuted)* — **[observed]** one capacity per L across guardrail and `-Xmx`; *capacity grows without bound past 65535 with no exception* is consistent with the claim and was seen (140,656 at 131,072; 1,172,112 at 1,048,576); *allocation flat in L while the control moves* — **[observed]** allocation rose from 112 B (L=8) to 688,336 B (L=65535); *the control does not move (not confirmed)* — **[observed]** the guardrail flipped exactly at its threshold and `new byte[L]` read L+16. Cluster: *collector lines appear, scaling with key length / following the threshold* — **[observed]** none appear; *a liveness counter is zero, accepted counts do not follow the thresholds, or a load did not complete (not confirmed)* — **[observed]** all counters nonzero, 16/16 load outcomes as predicted, 0 load errors.
5. **Observed vs. inferred** — **[inferred: grep of `src/java`]** that no other path builds the collector: the only construction sites are `Walker.getMaxTerm`/`getMinTerm` (no production caller) and `ValueIterator` with `collecting=true` (no production constructor call); the cluster trace is exact for constructions and `add` calls but covers only this workload (write, flush, compaction, point read, SAI query, BTI partition index), not repair, streaming or index-summary paths. **[inferred: Java semantics]** that the collector's scratch array is on-heap and short-lived (not measured in the cluster because no instance was created). **[inferred: the library]** the capacity formula of `ArrayUtil.grow` is a property of Lucene 9.7.0; the test measured it by running it (simulation) and measured the collector's capacity equal to it.
6. **Deviations and gaps** — the workload and instrument follow the amendments (JFR replaced by the exact Byteman trace; 3-minute reads; ordinary role; `NONE` compatibility mode); the unit tier reads the capacity of the collector local to `getMaxTerm`/`getMinTerm` only through allocation (the standalone collector is the same class code); the cluster never exercised the collector, so the claim "the usage is the longest path walked" is a unit-tier result, and the cluster result is that the collector is not reached; the three JVM sizes in the unit tier are 260, 519 and 1056 MB, not the 256m/512m/1g label (JVM reports a little more or less than -Xmx).
7. **Core question** — Following B1: the collector's array length follows only the length of the walked path (32 up to 32 bytes, then `ArrayUtil.grow`'s geometric steps, 69,368 for 65,535; the same value under every guardrail setting and JVM size; no cap even at 1,048,576), and on a running node, in four lifetimes with the term-size guardrail at 1KiB, 8KiB and 64KiB and with the BTI and big formats, the collector was never constructed or called while the guardrail visibly bound the accepted writes (positive control). No configured constraint caps it, and nothing it does follows one.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 — Confirmed (claim: usage does not follow the constraint).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`selfcheck.py` (own parsers, does not import the analyzers; recomputes the Lucene growth with its own four lines) gave ALL PASS for the unit tier and the cluster tier (`run1/unit/selfcheck-unit.txt`, `run1/cluster/selfcheck-cluster.txt`). Raw files re-read by hand besides it: the four `trace.txt` heads and tails, `cassandra.yaml` and the JVM-argument line of `system.log` per lifetime, `phases.csv`, and `tc-unit.txt` lines for L=33, 8192 and 65535.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | per lifetime: yaml shows threshold, format, authenticator, `NONE`; `system.log` shows `javaagent:...byteman-4.0.20.jar=script:...collector.btm,listener:true,port:19110` and `-Xmx1G`; trace files non-empty with LIVE lines; no `Walker`-class lines contradict BIG having no PartitionIndex; `ps` shows no daemon of this tree after the run. The one thing not verified directly in the cluster is that the `COLL` rules were installed (the class is never loaded there); that rests on the unit-JVM instrument check with the same file. |
| 2. Readings | yes | `cells.jsonl` loads (16 rows) and `tc-unit.txt` re-read; the `du` and BIG `byte[]` oddities are real in the files and are recorded, not explained. |
| 3. Matched row | yes | B2g row 1 and B3g row 1 quoted above; each part (one capacity per L; knob values varied; zero COLL, liveness nonzero, 16/16 outcomes) re-found in the raw files. |
| 4. Excluded rows | yes | rows quoted in §4.2.4 each contradicted by a cited reading; no Refuted row has support (no COLL line exists; one capacity per L). |
| 5. Observed vs. inferred | yes | the inferred items are listed and none is needed for the row match; the "not reached in other paths" statement is limited to the workload and the grep, and is worded so in §8. |
| 6. Deviations and gaps | yes | listed; the only effect on the conclusion is the scope of "never exercised" (workload-bound). |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's claim has three parts (follows only path length; independent of every knob; never exercised by a node): the first is the unit capacity table, the second the knob columns, the third the zero-COLL trace with live counters; the guardrail control shows the instruments see a cap that binds. |

### 5.2 Run 2?

**No** (2026-10-26). Both conclusions rest on exact readings (library-simulated capacities; a trace of every construction and call), the inferred statements are not load-bearing for the matched rows, and the result neither refutes the case nor confirms a bypass. A run 2 would repeat the same deterministic unit grid and a half-hour cluster run for no new evidence.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1 — "the collector's memory (heap bytes of `bytes`) does not follow any configured limit: it tracks only the length of the longest path walked (about the oversized path length, minimum 32 bytes), is independent of every yaml/`-D` knob, and is never exercised by a running node's read/write/compaction path in 5.0.9." "Confirmed" means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (capacity depends only on L, same under all guardrail/-Xmx values) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed — B3g row 1 (no collector lines in any lifetime, liveness counters nonzero, accepted counts follow the thresholds) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** unit — `Guardrails.saiStringTermSize.failsOn` fails exactly the sizes above each threshold (1KiB, 8KiB, 64KiB) while the collector's capacity at the same L is unchanged, and `new byte[L]` read L+16 B per call; capacity itself moved with L (32, 40, 1088, 8296, 69,368). Cluster — the guardrail moved the accepted and rejected write counts exactly with its threshold (W2: 0 accepted at 1KiB, 5,000 at 8KiB/64KiB; W4: 2,000 accepted only at 64KiB), and the liveness counters showed 71,000 to 222,000 trie-reader constructions per lifetime with zero collector constructions.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (2026-10-26; not committed) and the audit amendments R1-R8 plus D1 and D2 in place in B2-B3 (dated, 2026-10-26); the prediction and conclusion tables were not changed after the freeze. Open points: the "never exercised" half of the claim is established for this workload and by `grep`, not for repair, streaming and other paths; the `du` of the `big` lifetime exceeds the `bti` lifetime with the same accepted data and was not investigated.

**Leftovers on the node:** none running (`ps` finds no `CassandraDaemon` or JUnit JVM of this harness). Files: `~/s4-b7-tc` (tree, about 1 GB with build), `~/s4-b7-tc-run` (conf, logs; data removed), `~/s4-b7-tc-logs` (all logs, `probe/` Lucene probe).
