# repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous — stage-4 results  <!-- file: results/repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous.md -->

> **Case:** [`repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous`](../../stage3-ai-deep-read/cases/repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous.md)
>
> **Status:** verdict filed (2026-10-27) — unit **Refuted on one sub-claim (row b), effect: does not cap**; cluster **Confirmed — does not cap**; run 1 + self-check, no run 2
>
> **Outcome class:** true negative (estimate `negative`; effect `does not cap` at both tiers; the unit "Refuted" concerns a sub-clause of B1, the top accepted value, and not the capping question)
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `6e6cf92` (the case file is committed there without the amendments; the amendments are uncommitted). The file as filed declared both tiers `n/a`; they were un-declared by Amendments U1–U7 and C1–C6. sha256 of the whole file after those: `1c55da3d3fd1e72b8a5b54f7f5b18e03c139ac911b3497f477ffbb237f3dbb5d` (frozen 2026-10-27 02:33 UTC before the unit run; copy `run1/case-frozen.md`). After the unit tier, Amendment C7 (cluster tier only, before any cluster reading; see section 3) gave `c1434030dca13bfa80dd2aa0b2c8f7dcbe03159b243b4039f27ff98a5de83665` (copy `run1/case-frozen-2.md`); B2f and B2g are byte-identical in both. Section D changes after the run and is outside the freeze. |
| **Harness** | `harness/repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous/`: new `SessionSpaceSetterTest.java`, `selfcheck.py`; copied from the closed `repair_session_space-split-maxsize--guided/` harness with changes: `RepairSessionSpaceTreeTest.java` (unchanged), `unit-run.sh` (mode `setter`, paths), `cluster-run.py` (label `m-range`, paths), `Jmx.java` (prints `SETFAIL …` on a refused write), `make-node-yaml.sh` (path), `hold-trees.btm`, `split-trace.btm`, `Rss.java` (unchanged). Untracked; the orchestrator commits. |
| **Tiers and values** | Unit (B2): setter `v` rejected {0, −1, MIN}, accepted {1, 2, 4, 128, 251, 252, 2048, MAX}; real validations at stored 1 · 2 · 4 · 1024 · 2047 · 2048 · MAX (2^14 partitions, RF 1); raw field 0 · −1 · −1000; closed `RepairSessionSpaceTreeTest` (positive control, 78 checks), `MerkleTreeTest`, `ValidatorTest`, `ActiveRepairServiceTest`. Cluster (B3): two nodes on loopback, RF 2, Murmur3, 2^20 rows, 2 GiB heap each; control sweep default (128) · 1 · 4 · 16 · 64; range arm accept 4 · reject 0, −5 · refuse 2147483647 · accept 2147483646 · accept 1. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the check bounds a setter argument in MiB; the stored value sets the Merkle-tree heap and off-heap budget (82 L + 32 B off-heap, ~120 B heap per leaf) downstream (`ValidationManager.java:62-79`). Accepted as memory with a derivable byte size; the check itself holds nothing (named). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Not met → Met | Both tiers were `n/a: no constraint` (B2, B3). The claim (B1) is testable, so U2/C2 give a value set for the setter and a sweep for the control. |
| A. Core question | real resource measured, not only the counter | Not met → Met | none in the file; U3 reads leaves and the tree's deep size; C3 reads class-histogram counts of the held tree and the logged off-heap allocation sizes. |
| A. Core question | usage driven to the limit and past it | Not met → Met | the check's limit is 1: 0 and −1 are past it, 1 is at it (S1); the control spans 1 to 128 MiB over 2^20 rows. |
| A. Core question | positive control (negative file) | Not met → Met | none in the file; the closed same-knob case (`repair_session_space-split-maxsize--guided`, both tiers Confirmed) supplies it with its harness (U1, U6, C2). |
| B. Logic | each step says what it establishes | Not met → Met | no steps existed; U3, C3. |
| B. Logic | prediction stated in numbers or a clear relation | Not met → Met (partly wrong, see 4.2 part 6) | U4, C4. Two numbers were wrong (the top accepted value, and 1024 / 2047 MiB leaves) and are reported as misses, not edited. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met | U5, C5 (rows a–e, 1–6; row 7 added by C7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | for a negative claim: the setter's own exception text and the unchanged stored value, plus the control that moves. |
| B. Logic | alternative explanations and controls | Met | U6, C6. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1–A3, B1. |
| C. Specific | an AI can run it without re-deriving the code path | Not met → Met | U2–U3, C2–C3. |
| C. Specific | knob, values, workload, commands, observables exact | Not met → Met | same. |
| D. Runnable | harness and prerequisites exist or are listed | Met | the closed harness exists; additions listed. |
| D. Runnable | workload arithmetic reaches the limit | Met | pc32: 2^20 rows, 2 nodes, 2 GiB heaps, 56 GB disk (the closed run used the same sizes). |
| D. Runnable | citations spot-checked against the pinned source | Partly | `DatabaseDescriptor.java:4091-4101` (check, warn, assignment), `ValidationManager.java:62-79`, `ActiveRepairService.java:334-345`, `Config.java:208`: as cited. **Missed:** the audit did not read the constructor `DataStorageSpec.IntMebibytesBound` called at `DatabaseDescriptor.java:4100`; it rejects negative values and values above 2147483646 (`DataStorageSpec.java:108-111`), which changes B1's "up to Integer.MAX_VALUE" (section 4.2). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1–U7 | run the unit tier: setter outcomes, tree sizes from a real validation, raw-field counterfactual, closed control, rows, verdict wording | applied 2026-10-27 | the `n/a` left the negative claim without a control |
| C1–C6 | run the cluster tier: the closed ring with a new `m-range` label, predictions, rows | applied 2026-10-27 | same |
| C7 | the large accepted value is 2147483646; 2147483647 is attempted and must fail | applied 2026-10-27 before any cluster reading | source fact found by the unit run (section 3, R1) |
| left | A1's remark "the value later stored belongs to … `IntMebibytesBound`, default null" and A3's "Bypass: none needed" | left for stage 3 | the type bound is the upper bound; recorded in section D of the case file |

**Agreement criteria** — run 2 not chosen (see 5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (node clock MDT; unit 20:33–20:37, cluster chain 20:37–20:43) |
| Node | `pc32` (`node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 2026-08-18 |
| Ant | Apache Ant 1.10.12 |
| Local source copy | unit: `~/cassandra-run4` (`copy-source.sh` from repository commit `6e6cf92`, `git describe`: `cassandra-5.0.9`, `ant build-test`); cluster: `~/cassandra-run1` (the built, unmodified copy), Byteman 4.0.20 from its build |
| Case-file commit / harness commit | `6e6cf92` plus uncommitted amendments (sha256 in section 1) / harness untracked |
| Storage for node data | cluster: `~/s4b-rss/N1`, `~/s4b-rss/N2` on local `/dev/sda3` (about 1 GB per node), never under `/proj`; removed after the run |
| Full logs | `pc32:~/s4b-logs/rss2/` (`unit/`, `unit/attempt1/`, `m-setup/`, `m-control/`, `m-a/`, `m-range/` each with `summary.txt`, `readings.csv`, `session.log`, `raw/`, `chain.out`, `selfcheck.txt`, `case-frozen*.md`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| R1 | unit attempt 1 | U3 (S1–S3) | The harness test caught only `ConfigurationException` from the setter and let an `IllegalArgumentException` escape: `Integer.MAX_VALUE` passes the `< 1` check and is then refused by `new IntMebibytesBound(…)` (`DatabaseDescriptor.java:4100`, bound 2147483646); the raw fields −1 and −1000 cannot be constructed either. 3 test errors; 59 checks ok before the crash (`unit/attempt1/`) | The test records any `Throwable` as a reading and counts it as a mismatch against the frozen prediction; the prediction is **not** edited; the setter test was re-run (`unit/setter.out`: 64 checks, 59 ok, 5 mismatches, all recorded in 4.1). The other unit classes were not re-run | 2026-10-27 | untracked |
| R2 | cluster, first start (no reading) | B3 set-up | `make-node-yaml.sh` still defaulted to `~/stage4-rss` while `cluster-run.py` used `~/s4b-rss` (`Directory nonexistent`) | default changed to `~/s4b-rss`; chain restarted from `m-setup` | 2026-10-27 | untracked |
| C7 | cluster, before run 1 | B3e/B3f | The unit run showed that 2147483647 is not storable (R1). The cluster text (C2/C4) predicted it accepted. Amended before any cluster reading as a source fact (Amendment C7 in the case file): attempt 2147483647 (must fail), accept 2147483646 (L = 2). The unit tier's frozen text is not changed. | | 2026-10-27 | untracked |

## 4. Run 1

**Scope:** unit — all of U3 (S1–S3), the closed `RepairSessionSpaceTreeTest`, `MerkleTreeTest`, `ValidatorTest`, `ActiveRepairServiceTest`; cluster — `m-setup`, `m-control`, `m-a`, `m-range`, `down` once each. **Command log:** `repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous/run1/` (`unit/{summary.txt,setter.out,harness.out,attempt1/}`, `cluster/<label>/{summary.txt,readings.csv}`, `cluster/m-range/raw-lines/`, `selfcheck.txt`, `chain.out`).

### 4.1 Readings

**Unit tier** (JVM `maxMemory` 1,056,309,248 B, so the heap-pressure warning threshold T is 251 MiB)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Known answers: `MerkleTreeTest` / `ValidatorTest` / `ActiveRepairServiceTest` / closed `RepairSessionSpaceTreeTest` | 27 / 6 / 16 / 4 tests, 0 failures; the closed test printed 78 `STAGE4 check` lines, 78 `ok` (depth table leaf 80 B, inner 120 B, d(1 MiB) = 12) | `unit/attempt1/summary.txt`, `unit/harness.out` |
| S1, rejected 0, −1, `MIN_VALUE` | `ConfigurationException("Cannot set repair_session_space to <v> < 1 mebibyte")`; getter stays 7; MBean wrapper throws `IllegalArgumentException`; the call allocates 824 · 824 · 832 B | `unit/setter.out` |
| S1, accepted 1 · 2 · 4 · 128 · 251 · 252 · 2048 | stored exactly (getter = v); the call allocates 72 B (v ≤ 251) and 4,192 / 4,136 B (252, 2048: above T, the warning is logged) | `unit/setter.out` |
| S1, `Integer.MAX_VALUE` (2147483647) | **not stored**: `IllegalArgumentException: Invalid data storage: 2147483647 mebibytes. It shouldn't be more than 2147483646 in mebibytes` from the constructor after the check and the warning; getter stays 2048 (the previous value); call allocates 6,624 B | `unit/setter.out` (`S1 accept v=2147483647` MISMATCH ×2) |
| S2, real validation at stored 1 · 2 · 4 (2^14 partitions) | 4096 · 8192 · 16384 leaves, equal to the formula, `measureDeep` 497,952 · 991,200 · 1,976,448 B (~120 B per leaf) | `unit/setter.out` |
| S2, rejected 0 then −1 after stored 2 | next validation: 8192 leaves both times (unchanged) | same |
| S2, large stored values | 1024 MiB → 16384; 2047 → 16384 (both bound by the partition term 2^14); 2048 → **2** leaves (32-bit product −2,147,483,648); `Integer.MAX_VALUE`: the setter threw, no validation | same |
| S3, raw field 0 (no setter, no check) | **2 leaves** (`measureDeep` 480 B), not more than the 4096 at s = 1 | same |
| S3, raw −1 and −1000 | not constructible: `IntMebibytesBound` constructor throws `value must be non-negative` | same |
| Totals of the setter test | 64 checks: 59 ok, 5 MISMATCH (S1 `MAX_VALUE` ×2, S2 `MAX_VALUE`, S3 −1 and −1000: the recorded misses) | `unit/summary.txt`, `selfcheck.txt` |

**Cluster tier** (`n` ≈ 524,288 per node; both nodes always read the same L)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| default 128 (read back on both) | control, control-hold | L; off-heap; N2 histogram; calls | L = 262,144; two off-heap buffers of 21,495,840 B = 82 L + 32; hold: `OnHeapLeaf` +262,144, `OnHeapInner` +262,143 (8,388,608 + 12,582,864 B); `split calls` 0 | `cluster/m-control/summary.txt` |
| 1 · 4 · 16 · 64 MiB | A, A-hold (control sweep) | same | L = 2,048 · 8,192 · 32,768 · 131,072; off-heap per buffer 167,968 · 671,776 · 2,687,008 · 10,747,936 B; hold: `OnHeapLeaf` +L, `OnHeapInner` +(L − 1) at all four; knob read back equal on both nodes | `cluster/m-a/summary.txt` |
| 4 | R-accepted (+ hold) | L; histogram | 8,192; +8,192 / +8,191 | `cluster/m-range/summary.txt` |
| 4, JMX write 0 | rejected on N1 and N2 | write result; read-back | `SETFAIL … IllegalArgumentException: Cannot set repair_session_space to 0 < 1 mebibyte` on both; read back 4 on both | same |
| 4, then repair | after rejected 0 | L; off-heap | 8,192; 671,776 B ×2 (unchanged) | same |
| 4, JMX write −5, then repair | rejected | same | `… to -5 < 1 mebibyte`, read back 4; L 8,192; 671,776 B ×2 | same |
| 4, JMX write 2147483647 | refused on both | write result; read-back | `SETFAIL … Invalid data storage: 2147483647 mebibytes. It shouldn't be more than 2147483646 in mebibytes`; read back 4 | same |
| 2147483646 | accepted on both, repair | read-back; L; off-heap; WARN | read back 2147483646; L = **2** (32-bit product −2,097,152, /RF 2 → 1-byte budget); off-heap 196 B ×2; 4 `likely to cause heap pressure` WARN lines in the two nodes' logs (the refused 2147483647 attempt logs the warning before the constructor throws) | same |
| 1, then 128 | accepted | L | 2,048, then default restored | same |
| all | split trace | `split calls` | 0 at every repair on both nodes (Murmur3 init path) | `cluster/*/readings.csv` |
| all | stop | daemons | `both nodes stopped; daemons left: none` | `cluster/down/summary.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The check's limit was reached and passed on the setter (0, −1, −5 at and below the bound) and the control spans 1 to 128 MiB with trees of 2,048 to 262,144 leaves [observed: `unit/setter.out`, `cluster/m-a/summary.txt`]. Hold-fixed settings: the knob read back equal on both nodes before every repair; same data (2^20 rows, three sstables per node); autocompaction off; `split calls` 0 and `Created`/`Prepared` lines present at every repair, so the instruments fired [observed: `cluster/*/summary.txt`]. Unit: known answers pass (27 / 6 / 16 / 4 tests, 78 ok) [observed: `unit/attempt1/summary.txt`].
2. **Readings** — (a) the unit tier's top accepted value 2147483647 is refused by `IntMebibytesBound`, not stored; (b) the partition term, not the budget, binds at 1024 and 2047 MiB (16,384 leaves, n = 16,384 keys); (c) raw negative values cannot exist in the config object; (d) the heap-pressure WARN is logged for the refused 2147483647 attempt as well; (e) no other gap or outlier.
3. **Matched rows** — The unit rows are those of Amendments U5/U7; the cluster rows are those of C5 with C7.
   - **Unit, row (b)** "An accepted value is clamped or rejected above some bound (getter differs from v): **Refuted** (claim: stored without upper bound)": `Integer.MAX_VALUE` passes the `< 1` check and is rejected by a different bound (the `IntMebibytesBound` constructor, maximum 2147483646); the getter stays at the previous value [observed: `unit/setter.out`]. Rows (a) (rejected value changes the getter or the next tree), (c) (raw value builds a larger tree), (d) (control does not move) and (e) (leaves differ from the 32-bit formula) did **not** fire: rejected 0 and −1 leave 8192 leaves; raw 0 builds 2 leaves against 4096; leaves move 4096 → 8192 → 16384 for s = 1, 2, 4; every leaf count equals the formula [observed: same].
   - **Cluster, row (1)** (with C7): rejected writes fail with the setter's text and change neither the read-back nor the next repair's L (8,192 before and after), the large storable value 2147483646 is accepted and yields L = 2, 2147483647 is refused by the type bound, and the control sweep moves L ×4 per ×4 with heap and off-heap bytes [observed: `cluster/m-range/summary.txt`, `cluster/m-a/summary.txt`, `selfcheck.txt`]: **Confirmed — does not cap**.
4. **Excluded rows** — Unit (a), (c), (d), (e): see part 3. Cluster rows (2) rejected write changes read-back or L: read-back 4 and L 8,192 after each; (3) 2147483646 refused or clamped: read back 2147483646; (4) sweep does not move or hold silent: L moved ×2 per ×2 (control also for default 128), every hold started; (5) L differs from formula: 100 percent equal (`selfcheck.txt`); (6) 2147483646 yields a larger tree than s = 4: L = 2 against 8,192; (7) 2147483647 accepted over JMX: refused.
5. **Observed vs. inferred** — Inferred: (i) "the check cannot enlarge usage" from the raw-field arm (a zero budget builds 2 leaves) — the counterfactual is the unit's raw field, not a build without the check, and negative raw values cannot be built at all; (ii) that heap/off-heap bytes scale with L is read from the class-histogram deltas and logged allocation sizes (observed) but the tree's full heap (hash arrays) is not attributed (the closed case's caveat); (iii) the unit tier measures leaves and `measureDeep`, not whole-JVM heap.
6. **Deviations and gaps** — Frozen predictions missed three numbers: (1) the top accepted value is not storable (R1); (2) 1024 and 2047 MiB were predicted 32,768 leaves from a hand-computed n = 16,385, read 16,384 (n = 16,384 estimated keys, partition term 2^14; the test's formula line agrees with the read value); (3) raw −1 and −1000 were predicted 2 leaves but cannot be constructed. Only (1) matches a conclusions row (b). Cluster: one repair per value (the control was not repeated); two nodes on one host; Byteman and the hold are the closed harness's.
7. **Core question** — No: usage does not follow the `< 1` check. The check is a lower bound on a setter argument: it refuses 0 and negatives and changes nothing that was stored; a refused write leaves the next Merkle tree at the previous value's size (unit S2; cluster L 8,192 before and after) [part 3]. In range, the stored value is the input of the downstream budget formula, which does set the tree's leaves, heap and off-heap bytes (control: ×4 per ×4; 82 L + 32 B off-heap) [observed]. The setter is not unbounded above (the type bound 2147483646), and values from 2048 MiB up do not enlarge the tree but shrink it (32-bit overflow, L = 2). The constraint under test, the `< 1` check, **does not cap** memory.

**Conclusion (one line):** unit — B2g row (b) fired (sub-claim "stored without upper bound" refuted at 2147483647), rows (a) (c) (d) (e) did not: the check still caps nothing; cluster — B3g row (1): claim confirmed (effect: does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed the cluster `raw/` files with its own code (the `Created … merkle trees … partitions` and `Prepared AEService trees of size` lines, the off-heap allocation lines, the histograms' `OnHeapLeaf` / `OnHeapInner` counts, the rejected-write lines) and the unit `setter.out` / `harness.out`; it recomputes L from the unit tier's depth table with 32-bit arithmetic and does not use the run script's `EXPECTED` lines: every check PASS (`run1/selfcheck.txt`). By hand I re-opened `unit/setter.out` (the five MISMATCH lines and the `S1`, `S2`, `S3` values), `unit/attempt1/summary.txt`, and `cluster/m-range/summary.txt` (`REJECT`/`ACCEPT` lines).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | read-backs and instrument lines in `cluster/*/summary.txt`; known answers in `unit/attempt1/summary.txt` |
| 2. Readings | yes | (a)–(d) are each a line in `unit/setter.out` or `cluster/m-range/summary.txt` |
| 3. Matched row | yes | unit row (b) fired on the quoted lines; cluster row (1) reproduced by `selfcheck.txt` |
| 4. Excluded rows | yes | each cites a number in the raw files |
| 5. Observed vs. inferred | yes | (i) is the weakest link: it rests on the raw field 0 giving 2 leaves; it does not change the matched rows |
| 6. Deviations and gaps | yes | the three misses and R1 / R2 / C7 are recorded as found |
| 7. Core question | yes | hypothesis B1 → setter test and ring → predictions → rows; the control moved (4,096 → 16,384; 2,048 → 131,072) |

### 5.2 Run 2?

**No** (2026-10-27). The exceptions and values are deterministic (JVM exceptions with fixed text, exact leaf counts), the cluster readings are exact counts that equal the formula to the byte, and the independent re-parse agrees. The inferred statement (i) would not change with a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) The `sizeInMiB < 1` check does not cap memory or disk: it only rejects non-positive input, and any accepted value (1 up to Integer.MAX_VALUE) is stored without upper bound. "Confirmed" below means this claim held; the unit tier's row (b) is the literal reading of the last clause.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row (b): **Refuted** for the sub-claim "stored without upper bound" (2147483647 is refused by `IntMebibytesBound`, bound 2147483646). Rows (a), (c), (d), (e) did not fire: rejected values change nothing, the control moves (4096 → 16384 leaves), raw 0 builds 2 leaves | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | B3g row (1) (with C7): **Confirmed** — rejected 0 and −5 change neither read-back nor L (8,192); 2147483647 refused; 2147483646 stored and L = 2; control sweep L = 2,048 → 131,072, heap +L / +(L − 1), off-heap 82 L + 32 | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control:** the stored value moves the Merkle tree under a real validation: unit 4,096 / 8,192 / 16,384 leaves at 1 / 2 / 4 MiB; cluster 2,048 / 8,192 / 32,768 / 131,072 leaves at 1 / 4 / 16 / 64 MiB, `OnHeapLeaf` +L and off-heap buffers of 82 L + 32 bytes (the closed same-knob case's instruments, re-run).

**Feedback filed:** the case file's section D updated (amendments U1–U7, C1–C7 and these results). **Open points:** (1) B1's "up to Integer.MAX_VALUE" is wrong by one: the maximum storable value is 2147483646 (`DataStorageSpec.java:111`), and 2048 MiB and above shrink the tree (overflow at `ValidationManager.java:62`, a downstream finding already in the closed case); (2) `A3` should add `IntMebibytesBound` as a second validation; (3) the audit's missed citation is the reason for the sub-claim refutation. **Leftovers on `pc32`:** no `CassandraDaemon` running (checked with `ps -eo cmd | grep '[C]assandraDaemon'` on the node); node folders `~/s4b-rss` removed; logs kept in `~/s4b-logs/rss2/`; `~/cassandra-run4` kept for the next cases.
