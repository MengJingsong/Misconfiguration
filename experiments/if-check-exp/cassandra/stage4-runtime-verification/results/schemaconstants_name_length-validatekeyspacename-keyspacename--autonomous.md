# schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous — stage-4 results  <!-- file: results/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md; the stem ends in --autonomous -->

> **Case:** [`schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous`](../../stage3-ai-deep-read/cases/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md)
>
> **Status:** **Closed 2026-10-28 — unit Confirmed, cluster Confirmed — does not cap** (estimate negative, matched); no run 2
>
> **Outcome class:** true negative — stage-3 estimate (negative) vs the stage-4 effect (does not cap)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments (block B5, 2026-10-28): `54b4efeb4c21932426c4bcdb658e261e8d7c8fd00e32bc3cc397a94bb978a361` (`sha256sum`, run 2026-10-28 after B5 item 1 was corrected for defect D1 and before any cluster reading; an earlier freeze, `e5c8761d…`, was superseded by D1; the final file, with section D filled after the verdict, has the sha256 in §8). The file before the amendments had sha256 `a1899a8633fca73fff28986c93808d16fa977d6b33c58c48f5011508f782ee89` (in `b68711e5`). The amended file is not committed by this session. |
| **Harness** | [`harness/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous/`](../harness/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous/README.md), written 2026-10-28; not committed by this session. |
| **Tiers and values** | Unit (B2): keyspace-name length L = 1 · 10 · 47 · 48 · 49 · 100, N = 1000 (36 at L = 1), T = 0 · 10 tables per keyspace, 3 repetitions. Cluster (B3): 200 keyspaces x 1 table x 10000 rows; arms L = 3 and L = 48 (2 repetitions each), 49-character `CREATE KEYSPACE` rejection, control B `memtable_heap_space` 64MiB vs 256MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the operand is a name length in characters, not bytes of memory or disk; its byte effect is the per-name string (tens of bytes), derivable (A1, B2c arithmetic). Counted as a count with a derivable byte size. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: a hard-coded constant, not settable. The design varies the input name length across 1/3, 10, 47, 48, 49, 100 (unit) and 3, 48, 49 (cluster) (B2b/B3b) and compares usage, with the limit at the boundary. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d deep size (unit), B3d heap after GC and `du` on a real node; B3d names what is not observable (per-name string retention). |
| A. Core question | usage driven to the limit and past it | Met | L = 48 (limit) and L = 49, 100 (past it) in the unit tier; 49 at the node. |
| A. Core question | positive control (negative estimate) | Met | T tables per keyspace (unit) and `memtable_heap_space` (cluster): known to move retained objects / heap. |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after B5 item 6 | "within noise", "comparable", "small" had no threshold; thresholds set before any reading. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover accepted-over-limit, usage follows, usage flat, control not moving. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The rejection at limit+1 (message text) plus flat usage with a moving control. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h controls. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1–A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after B5 | name generation, N at the shortest length, client, control size were open. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after B5 | see B5 items. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | JDK 11.0.32.1, Ant 1.10.12 on pc29; probe test, node scripts, client are step-1 work. JOL not on classpath: jamm used (B5). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 200 keyspaces x 10000 x ~100 B = about 200 MB per arm; 2 GiB heap; 49 GB free on local disk; four arms plus two control runs. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-read in `cassandra/cassandra-5.0.9/` on 2026-10-28: `SchemaConstants.java:75`; `KeyspaceMetadata.java:63-71,338`; `TableMetadata.java:482`; `AlterSchemaStatement.java:116-118`; `CreateIndexStatement.java:213-214`; `Mutation.java` (no keyspace name in `MutationSerializer`, which writes table ids). All hold; the file's own A1 correction (table names use `TABLE_NAME_LENGTH`) is confirmed. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | B5 item 1: size instrument jamm (JOL absent) | Applied 2026-10-28 (B5; not committed) | classpath |
| R2 | B5 item 2: unique-name generation, N = 36 at L = 1 | Applied | L = 1 cannot give 1000 names |
| R3 | B5 items 3-4: arms, client, heap/disk readings | Applied | unspecified |
| R4 | B5 item 5: control B made exact (workload, observable, "clearly") | Applied | "same write load" and "clearly" undefined |
| R5 | B5 item 6: thresholds for "within noise" | Applied | no numbers |

**Agreement criteria** — run 2 is not planned.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (node clock, MDT): unit 13:00 (after one discarded run, D1); cluster 13:00:16–13:41:06 |
| Node | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB RAM). One Cassandra node on 127.0.0.1 per arm, fresh directories each |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 (2026-08-18) |
| Ant | Apache Ant 1.10.12 |
| Local source copy | `~/s4-b2/base` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e5` by `copy-source.sh` (tag `cassandra-5.0.9`), `ant build-test` (1 min 17 s) |
| Case-file commit / harness commit | `b68711e5` holds the file before amendments (sha256 `a1899a8633fca73fff28986c93808d16fa977d6b33c58c48f5011508f782ee89`); the amended file and the harness are uncommitted in the working tree |
| Storage for node data | node-local `/dev/sda3` (63 GB, 49 GB free before the run), under `~/s4-b2/run/ks/<label>/`; nothing on `/proj` |
| Full logs (outside the repo) | `~/s4-b2/logs/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous/run1/{unit,cluster}/` on `pc29` (histograms, `cmd.log`, samples, json); node directories `~/s4-b2/run/ks/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| D1 | unit | B2a/B2d (size instrument) | `ObjectSizes.measureDeep` stops at `@Unmetered` `TableMetadata` and `ColumnMetadata` (jamm), so the table-name case's shakedown measured 4 bytes per table, and in this case the T = 10 control was undercounted (9,310 B per keyspace by the corrected sizer vs about 2,108 B by `ObjectSizes`). A first unit run of this case with `ObjectSizes` was discarded (`run1-discarded-D1` on the node); its numbers are not used. | B5 item 1: a reflective walker with jamm's shallow `measure`; `ObjectSizes.measureDeep` printed beside it. B2f/B2g unchanged. | 2026-10-28, tier restarted | uncommitted |
| D2 | cluster | harness shakedown (not a case-file step) | `nodetool statusbinary` prints `not running` before the port opens and the harness matched `running` in it; `compactionstats` prints `pending tasks   0` without a colon; `grep -c` with two files; a format-string slip in the control writer. All were harness bugs found in the discarded shakedown runs `shake1`/`shake2`. | harness fixed | 2026-10-28 | n/a |

## 4. Run 1

**Scope:** unit tier (all of B2) and cluster tier (all of B3: four arms, the 49-character rejection in both long arms, control B). **Command log:** `ks/run1/cluster/cmd.log`, `ks/run1/unit/summary.txt` under [`results/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous/run1/`](schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous/run1/).

### 4.1 Readings

**Unit tier** (`unit/test.out`, `selfcheck.txt`)

| Test or assertion | Result | Evidence |
|---|---|---|
| `validateKeyspaceName` L = 1, 10, 47, 48 | pass | `unit/test.out` case lines |
| `validateKeyspaceName` L = 49, 100 | `ConfigurationException`, message `Keyspace name must not be more than 48 characters long (got 49 characters for "…")` | same |
| `KeyspaceMetadata.validate()` and `TableMetadata.validate()` (keyspace of that length) | pass at L <= 48, throw at 49 and 100 | same |
| known-answer checks | 18 of 18 ok, 0 MISMATCH | `unit/summary.txt` |
| retained size per keyspace, T = 0, L = 10 / 47 / 48 / 49 / 100 | 284.26 / 316.26 / 316.26 / 324.26 / 372.26 B (3 repetitions identical; L = 1: 283.11 B at N = 36) | `test.out` size lines |
| retained size per keyspace, T = 10 | 9,278.07 / 9,310.07 / 9,310.07 / 9,318.07 / 9,366.07 B (L = 10 / 47 / 48 / 49 / 100) | same |
| L = 10 to 48 at T = 0 | +32.00 B per keyspace | `selfcheck.txt` |
| T = 0 to 10 at L = 48 (positive control) | +8,993.82 B per keyspace = 281 x the L change | `selfcheck.txt` |
| upstream `KeyspaceMetadataTest` (sanity) | 1 test, 0 failures | `unit/summary.txt` |

**Cluster tier** — arms (200 keyspaces x 1 table x 10,000 x 100-byte values = 2,000,000 rows each; heap 2 GiB; settle 60 s after `nodetool flush`):

| Arm | Name length | Observable | Reading | Evidence |
|---|---|---|---|---|
| A1 | 3 | histogram Total / heap used after GC / data dir | 214,713,208 / 214,664,088 / 49,293,477 B | `cluster/A1.json`, `A1.histo-head.txt` |
| A2 | 3 | same | 197,847,624 / 197,798,504 / 49,293,976 B | `A2.json` |
| B1 | 48 | same | 210,542,952 / 210,493,792 / 49,347,406 B | `B1.json` |
| B2 | 48 | same | 210,509,024 / 210,459,200 / 49,339,392 B | `B2.json` |
| B1, B2 | 49 | `CREATE KEYSPACE` with 49 `k` | rejected, `InvalidRequest`, `Keyspace name must not be more than 48 characters long (got 49 characters for "kkk…")` | `B1.json`, `B2.json`, `cmd.log` |
| all | 3 / 48 | longest user keyspace directory | 3 / 48 characters | `selfcheck.txt` |
| all | | `ERROR` lines in `system.log`, OutOfMemoryError | 0, 0 | `summary.txt` |

Long-arm mean minus short-arm mean: **+4,245,572 B** (histogram Total; heap used +4,245,200 B); spread between the two repetitions of the short arm 16,865,584 B, of the long arm 33,928 B; name-byte budget (B5 item 6) 450,000 B. Data dir: +49,672 B = 0.101 % of 49.3 MB. Write rate 22 k rows/s, DDL 276 s per arm.

Control B (one keyspace `kc3`, 3,000,000 x 100-byte rows in three client processes, `memtable_heap_space` set, `heap_buffers`):

| Setting | Peak `AllMemtablesHeapSize` | Flush enqueues (script / selfcheck) | Evidence |
|---|---|---|---|
| 64MiB | 22,343,119 B | 110 / 117 | `C64.json`, `C64.samples.csv` |
| 256MiB | 89,445,598 B | 49 / 56 | `C256.json`, `C256.samples.csv` |

Ratio 0.25 (<= 0.5 needed) and more flushes at 64MiB: control B moves clearly. (The script counted before the node was stopped; the self-check counts the whole log, which includes the flushes at shutdown, hence 7 more in both.)

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached at the node: a 48-character keyspace was created in B1/B2 and a 49-character one was refused [observed: `B1.json`, `B2.json`, `selfcheck.txt`]. Hold-fixed settings: same build, heap (2 GiB), rows and values in all four arms, fresh data directories [observed: `cmd.log`, `A1.json`..`B2.json`]. All writes succeeded (failed = 0) [observed: `*.json`]. The control moved [observed: `C64.json`, `C256.json`]. Valid.
2. **Readings.** The two short-arm repetitions differ by 16.9 MB (A1 214.7 MB, A2 197.8 MB) while the two long-arm repetitions agree to 34 KB; the long-arm mean (210.5 MB) lies between the two short-arm values [observed: `summary.txt`]. By the rule fixed before the run (B5 item 6) +4.2 MB is "within noise". It is probably not zero, though: the sibling table-name case measured 112 metric MBeans per table whose names carry the table's keyspace and table name and about 4.8 retained copies of that text per table (its `supplementary-metrics-mbeans.txt`); 200 tables x 112 x 45 extra characters x 4.8 is about 4.8 MB, the size of the difference seen here [inferred: sibling case's count, not measured in this case]. So the +4.2 MB is most likely a small real name-length effect of about 2 % of the heap (6 % of control B's peak difference) rather than pure noise, and the unit tier's 32 B per keyspace object does not include it.
3. **Matched row.** Unit: "Deep size changes by tens of bytes per name while the T control moves it by orders more" -> claim confirmed: +32 B per keyspace for 38 more characters against +8,994 B for ten tables (281 x), and L = 49/100 are rejected with the traced message [observed: `test.out`]. Cluster: "Difference is within noise, while control B moves heap/flush clearly" -> claim confirmed: the arm difference (+4.2 MB) is below the larger of the budget and the short-arm repetition spread (16.9 MB), 6 % of control B's peak difference (67.1 MB), and `du` differs by 0.1 % [observed: `summary.txt`, `selfcheck.txt`]; the 49-character keyspace is refused in both long arms [observed].
4. **Excluded rows.** "L = 49 accepted or 48 rejected": refuted by the unit cases and by the node (49 refused, 48 created). "Deep size scales with L by more than a few name copies": the unit slope is one copy (+32 B for 38 characters; the tables in T = 10 share the keyspace's name string, identical slope at T = 0 and T = 10). "Usage differs between L = 3 and L = 48 by more than noise and name arithmetic": the +4.2 MB is inside the 16.9 MB spread, and the long arms agree with each other to 34 KB. "Control does not move / limit never reached": control B moved 4x in peak and 2.2x in flushes; the limit was reached.
5. **Observed vs. inferred.** Inferred: that the 4.2 MB heap difference is small and mostly metric-name text (the cluster tier cannot resolve a difference below about 17 MB; the rule calls it noise; the arithmetic from the sibling case says it is probably real but small); that `AllMemtablesHeapSize` peak at 22 MB / 89 MB is the cap acting (the 64MiB and 256MiB settings with the default cleanup threshold flush at about a third of the space) [inferred: control ratio 0.25 against 64/256].
6. **Deviations and gaps.** (a) The size sizer is a reflective walker, not JOL (B5 item 1, D1). (b) The arm writers ran as four client processes (each every 4th keyspace) and the control as three, not "one client" (B5 item 3), for run time; the rows and values are identical across arms. (c) Heap-after-GC resolution is about 17 MB (8 % of the 210 MB), so the cluster tier alone cannot show a difference smaller than that; the unit tier does not see the metric-name copies (see 4.2 part 2), so the true size of the effect is bracketed (0 to about 17 MB) rather than measured. The "tens of bytes per name" wording of B1 holds for the schema objects, not for the node as a whole. (d) Not exercised: the custom-index target-column use of `NAME_LENGTH` (CreateIndexStatement.java:213) and the bypass of validation for schema loaded at startup (A3) [not run]. (e) No run 2.
7. **Core question.** Usage did not follow the constraint in any significant way: going from 3 to 48 characters (45 more per keyspace name) moved retained size by a few tens of bytes per keyspace object (unit, 32 B) and left node heap and disk within the rule's noise (cluster, +4.2 MB of 210 MB, probably a real but small metric-name effect, against a 17 MB repetition spread; data dir +0.1 %), while a condition known to bind (`memtable_heap_space`) moved peak memtable heap 4-fold and flushes 2.2-fold on the same instruments. The constant caps a name length and nothing that scales with data.

**Conclusion (one line):** unit B2g row "deep size changes by tens of bytes per name while the T control moves it by orders more" and cluster B3g row "difference within noise while control B moves clearly" — Confirmed (does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` re-parses the raw files (unit `test.out`; cluster `*.histo.txt`, `*.samples.csv`, node `system.log`, `cmd.log`, the node data directories re-walked) and prints the numbers cited; output in `run1/selfcheck.txt`. Final output (run after both cases' runs ended): `SELFCHECK-RESULT: INTEGRITY OK`; the `[claim …]` lines restate the case's own thresholds (all hold here).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: 49 refused with the message in both long arms (two readings); longest user keyspace directory 3 / 48; no ERROR or OutOfMemoryError in any `system.log`. |
| 2. Readings | yes | histogram Totals re-read from `A1.histo.txt`..`B2.histo.txt` equal the json; data dirs re-walked (49,293,477 .. 49,347,406). |
| 3. Matched row | yes | unit deltas recomputed from `test.out` (+32.00 vs +8,993.82); cluster difference recomputed (+4,245,572 vs max(450,000, 16,865,584)). |
| 4. Excluded rows | yes | refuting rows each need a reading that is absent; the control ratio 0.25 and flush counts recomputed from `samples.csv` and `system.log`. |
| 5. Observed vs. inferred | yes | the inferred points are flagged in 4.2; the weak one is noise attribution at the cluster tier, backed by the unit tier. |
| 6. Deviations and gaps | yes | listed in 4.2 part 6. |
| 7. Core question | yes | follows B1 -> B2/B3 steps; no step relies on a missing reading. |

### 5.2 Run 2?

**No** — 2026-10-28. The unit tier is exact (three identical repetitions) and the cluster tier's weak point (17 MB resolution) is a recorded limit, not an unsettled part; the result confirms the estimate rather than refuting it.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) memory and disk usage do not follow `NAME_LENGTH`: moving keyspace names from 1 (here 3) characters to the 48-character maximum changes retained heap and on-disk size only by an amount proportional to the extra name bytes, negligible beside a control that does bind; and the check rejects exactly lengths above 48. "Confirmed" means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — "deep size changes by tens of bytes per name while the T control moves it by orders more" | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed — "difference is within noise while control B moves heap/flush clearly"; 49-character keyspace refused | does not cap | run 1 + self-check | 2026-10-28 |

**Final sha256 of the case file (section D filled):** `a15a8a4e58f3977f245fb981f2b56c9ec0b004a060d919a3d281e3a8cedb663f`.

**Positive control:** unit, tables per keyspace (+8,994 B per keyspace for T = 10 against +32 B for the whole 38-character range); cluster, `memtable_heap_space` 64MiB vs 256MiB (peak `AllMemtablesHeapSize` 22.3 MB vs 89.4 MB, flushes 110 vs 49).

**Feedback filed:** the case file's section D filled 2026-10-28 (uncommitted); amendments B5 (items 1-6, dated 2026-10-28) in section B.
