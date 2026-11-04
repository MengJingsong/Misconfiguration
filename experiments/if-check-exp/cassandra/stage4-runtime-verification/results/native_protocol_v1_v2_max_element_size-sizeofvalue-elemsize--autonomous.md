# native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous — stage-4 results  <!-- file: results/native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous.md -->

> **Case:** [`native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous`](../../stage3-ai-deep-read/cases/native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit Confirmed (does not cap); cluster (the file's alternative, which does not reach line 250) Confirmed (does not cap); no run 2
>
> **Outcome class:** true negative (stage-3 estimate `negative`, stage-4 effect `does not cap`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 after the audit's amendments, taken before any reading: `88366b34559be307bb7e4a7d070d02cf6a7385a25a813b2fd4379e3ca1205287`. File committed at `b68711e5` (HEAD); the amendments of 2026-10-28 are uncommitted. The control mechanism was amended once more (the intermediate sha256 after that amendment, before section D, was not recorded) before this file's own cluster run (the defect found by the sibling file's run, defect 2 below; claim, predictions and rows unchanged), and section D (stage-4 feedback) was filled after run 1: final sha256 `0dab663fe8abe6659e0d6800b90f9c8e737d3258881f10b68b2f73da62491ec2`. |
| **Harness** | `harness/native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous/` (uncommitted; README there) |
| **Tiers and values** | Unit: V2 / V3 x S = 65535, 65536, 8 MiB (N = 1) and N = 100 at S = 65535, null element, payload-growth control N = 1..1000. Cluster: declared n/a for the traced V1/V2 branch (file); the file's alternative is run as a tier that exercises the V3+ branch: one node, v4 `set<blob>` writes at S = 65535 / 65536 / 1 MiB, a UDF returning `list<blob>`, a V2 probe, and a second node start with `column_value_size_fail_threshold: 512KiB` as positive control. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note |
|---|---|---|---|
| A | quantity is memory or disk bytes | Met | Allocated bytes (unit), heap/memtable/disk bytes (cluster); the check's own quantity is element bytes. |
| A | knob varied (>= 3 values) or other approach | Partly -> Met | Hard-coded literal: dose = element size S across 65535 and the protocol version (B2b). |
| A | real resource measured | Met after amendment | `getThreadAllocatedBytes` added. |
| A | driven to the limit and past it | Met | S = 65535, 65536, 8 MiB. |
| A | positive control (negative claim) | Partly -> Met | Unit: N sweep (numeric proportionality added). Cluster: `max_value_size` is a deserialization-side check (`AbstractType.java:590-597`), not a write-time cap; amended to `column_value_size_fail_threshold` (`Config.java:916`). |
| B | prediction in numbers; rows; disallow evidence | Met after amendment | Result sizes added (checked by hand: V2 N=1 S=65535 = 65 539; V3 S=8 MiB = 8 388 616). The file's note that a V2 throw leaves the result buffer unallocated (A3 step 5) is checked in the source: `ByteBuffer.allocate` is after the loop (`CodecUtils.java:56`). |
| B | alternatives and controls | Met | Version isolates the check; null case isolates the NPE. |
| C | human / AI can follow; values exact | Partly -> Met | Probe run line and instruments fixed. |
| D | harness exists | Met (listed) | Step 1. |
| D | workload reaches the limit | Partly | Unit: yes. Cluster: the file declares it n/a for V1/V2; the alternative's plain `set<blob>` write does not call `CodecUtils`; amended with a UDF workload and a Byteman rule on `sizeOfValue` so V3+ is shown evaluated. |
| D | citations | Met | `CodecUtils.java:48-57,226-241,243-262`, `ProtocolVersion.java:42-43,66,106-115`, `UDFunction.java:111`, `Config.java:916` match; `value.remaining()` at 249 does throw an NPE for null on V1/V2 (`value == null` is handled only in the V3+ branch, 257). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Cluster alternative: add a UDF workload and a Byteman rule so the V3+ branch is shown evaluated; control = `column_value_size_fail_threshold` | Applied (B3 amendment 2026-10-28) | Groups A/D |
| R2 | Probe details, result sizes, numeric control | Applied (B2 amendments) | Group B/C |
| R3 | Run the file's alternative although the tier is declared n/a | Decision of this audit; the verdict states the tier does not exercise line 250 | README: n/a tiers are not run, but the alternative is what answers the core question |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (unit 17:49 MDT; cluster default node start about 18:28 MDT, control about 18:33 MDT) |
| Node | `pc41` (`node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`) |
| OS / kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-b34/src` (`copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `b68711e5`, `ant build-test`; shared with the two sibling cases, never edited except for the copied probe test classes) |
| Case-file / harness commit | `b68711e5` with the uncommitted amendments (sha256 in §1) / uncommitted |
| Node data | local disk `~/stage4-tmp/b34/es/node` (recreated at each node start) |
| Full logs | `pc41:~/s4-b34/logs/max_element_size/run1/` (`unit/`, `cluster/default/`, `cluster/control/`, `selfcheck.out`); an aborted cluster attempt is in `attempt3-aborted-control-flaw/` |

**Attempts before the run 1 recorded here:** unit tier, first try: the probe could not be copied (the test directory is absent from the tag) — defect 1, nothing ran. Cluster tier, first try: the chain was stopped during its default node start (about 18:14 MDT) once the sibling file's control run showed that guardrails do not apply to superusers (defect 2); no reading of that attempt is used. The tier restarted with the amended control.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | unit, first try | B2a | `test/unit/org/apache/cassandra/cql3/functions/types/` does not exist in the tag, so the probe could not be copied | the run script creates it | harness-only | none |
| 2 | cluster, first try (found by the sibling file) | B3h control (my audit amendment) | `column_value_size_fail_threshold` is not enforced for superusers, and with `AllowAllAuthenticator` every client is one (`ClientState.java:594-605`, `Guardrail.java:93-96`) | control node runs `PasswordAuthenticator`, writer is an ordinary role | claim, predictions and rows unchanged; case file amended (dated); tier restarted | none |
| 3 | run 1 | B3d | the memtable data size of `tw_1048576` is not valid: a `MEMTABLE_LIMIT` flush (87.05 MiB on-heap, 34 %) happened during the 100 inserts, so the memtable held only the last 12 MB at the reading | the disk leg (sum of all `Data.db`: 105 334 768 B) is used for 1 MiB; the memtable leg only for 65535 and 65536 | reading | none |
| 4 | run 1 | B3d | `heapmax_kB` is 0 for the UDF queries that finish between two 0.5 s heap samples | not used for the verdict (Byteman carries the UDF leg) | reading | none |

## 4. Run 1

**Scope:** unit tier (27 cells x 3 reps, plus the null case); cluster tier (the file's alternative), two node starts. **Command log:** `native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous/run1/` (`unit/summary.txt`, `unit/test.out`, `cluster/default/readings.txt`, `es-byteman-lines.txt`, `cluster/control/readings.txt`); checker `harness/.../selfcheck.py`, output `run1/selfcheck.out` (19 PASS, 0 FAIL).

### 4.1 Readings

**Unit tier** (`run1/unit/test.out`; `CodecUtils.pack` on `ByteBuffer[N]` of S bytes; median of 3 thread-allocated-byte readings; 1 test passes):

| Cell | V2 | V3 and V4 |
|---|---|---|
| N=1, S=65535 | ok, 65 539 B (= 2+2+65535); alloc 65 656 | ok, 65 543 B; 65 656 |
| N=1, S=65536 | **IllegalArgumentException** "Native protocol version 2 supports only elements with size up to 65535 bytes - but element size is 65536 bytes"; alloc 2 192 B (max 2 344) | ok, 65 544 B; 65 656 |
| N=1, S=8 MiB | **IllegalArgumentException** (element size is 8388608 bytes); alloc 2 192 B | ok, 8 388 616 B; 8 388 728 |
| N=100, S=65535 | ok, 6 553 702 B; alloc 6 558 568 | ok, 6 553 904 B; 6 558 768 |
| null element, N=1 | `NullPointerException` | ok, 8 B (4 + 4) |
| control, S=65535, N = 1 / 2 / 10 / 100 / 1000 | alloc 65 656 / 131 240 / 655 920 / 6 558 568 / 65 585 072 | 65 656 / 131 248 / 655 944 / 6 558 768 / 65 587 328 (V3), same for V4 |

Allocated bytes per element in the control are 65 656, 65 620, 65 592, 65 586 and 65 585 (V2): flat within 0.2 %, no step where N*S crosses 65535.

**Cluster tier, the file's alternative** (`run1/cluster/default/readings.txt`, `es-byteman-lines.txt`):

| Item | Reading |
|---|---|
| V2 probe | client `connected=no` ("Connection ... was closed"); server log: "Protocol exception ... Invalid or unsupported protocol version (2); supported versions are (3/v3, 4/v4, 5/v5, 6/v6-beta)" |
| W: plain `set<blob>` on v4, 100 rows each with one element of S = 65535 / 65536 / 1 048 576 | all 300 rows accepted, 0 errors; read back 1 element; Byteman `ES_PACK` calls during W: 0; memtable data 6 559 600 / 6 559 700 B for the first two (1.0009 per payload byte); SSTable `Data.db` 6 586 673 / 6 586 757 / 105 334 768 B (1.0050, 1.0050, 1.0046 per payload byte); for 1 MiB a `MEMTABLE_LIMIT` flush occurred during the insert (defect 3) |
| U: UDF `RETURNS list<blob>` with one S-byte element, v4 then v3 | all six queries returned the element (`first_len` = S); Byteman: `ES_SIZEOF ver=V4/V3 remaining=65535, 65536, 1048576`, one `ES_PACK elements=1` each; no V1/V2 line |

Control node start (`column_value_size_fail_threshold: 512KiB`, `PasswordAuthenticator`, writer `ord`, `SUPERUSER = false`): S=65535 and 65536 accepted (100 rows each, 6 559 600 / 6 559 700 B in the memtable); S = 1 MiB rejected, 0 rows: `InvalidRequest ... Guardrail column_value_size violated: Value of column 's' has size 1048576, this exceeds the failure threshold of 524288.`; nothing stored.

### 4.2 Conclusion and logic

1. **Validity.** Unit: the element size crossed 65535 (65536 and 8 MiB) and V2 threw the size message in all 3 reps [observed: `unit/test.out`]. Cluster: elements of 65536 and 1 MiB reached `sizeOfValue` under V3 and V4 on the node [observed: `es-byteman-lines.txt`]. "Hold fixed": JUnit under `ant testsome` with `-Xmx512m`; `user_defined_functions_enabled: true`; control yaml line [observed: `unit/summary.txt`, `extra.yaml`]. The positive control moved. Valid for what the tiers can reach: the **cluster tier does not reach line 250** (it cannot, as the file says); it exercises the V3+ branch and the node's usage.
2. **Readings.** (a) The memtable leg for 1 MiB is invalid (defect 3); the disk leg covers it. (b) The client text of the V2 probe is "connection closed"; the server log names the protocol [observed]. (c) The heap sampler missed the UDF queries (defect 4).
3. **Matched row.** Unit B2g rows "V2 throws at S=65536, succeeds at 65535; V3 succeeds at 8 MiB -> mechanism as traced; it is a per-element wire-format check" and "heap used by successful calls scales with payload for both versions, with no step at 65535 -> usage does not follow the constraint (claim confirmed)": V2 threw exactly for S > 65535 (S = 65536 and 8 MiB) and succeeded at 65535 and N = 100; V3 and V4 succeeded at 65535, 65536 and 8 MiB with the exact length `4 + N*(4+S)`; allocated bytes per element in the N = 1..1000 sweep are flat to 0.2 % for V2, V3 and V4 [observed: `selfcheck.out`]. The failing V2 calls allocated 2.2 KB, as `pack` loops over `sizeOfValue` before allocating the result [observed]. Cluster B3g row "V2 refused; V4 accepts elements above 65535; usage linear in bytes -> claim confirmed": V2 refused by the server (protocol version); v4 accepted 65536-byte and 1 MiB elements; disk bytes per payload byte are 1.0050 / 1.0050 / 1.0046 (no step); the node evaluated `sizeOfValue` at V3/V4 with 65536 and 1 048 576 bytes and never at V1/V2 [observed]. Cluster control row "positive control (a column with a real cap) rejects while this case does not": `column_value_size_fail_threshold` rejected the 1 MiB insert and accepted 65535 and 65536 [observed: `cluster/control/readings.txt`].
4. **Excluded rows.** "V2 does not throw at 65536, or V3 throws": V2 threw, V3 and V4 did not. "Heap/result size capped near 65535 for V3 or V2 totals": N = 100 at 65535 gave 6.55 MB, 8 MiB gave 8.39 MB. "V4 rejects elements just above 65535 with the message from line 253 (refuted)": accepted; the message appears in no log (`selfcheck.out`: node log and stdout have no "supports only elements"). "Usage plateaus at a size related to 65535 (refuted)": none. "Large writes rejected by another limit before reaching this code": none rejected in the default start. "Control heap does not move": it moved with N. "Limit never reached": reached. No Refuted row applies.
5. **Observed vs. inferred.** Inferred: that a plain `set<blob>` write does not call `CodecUtils` **[inferred: the source and 0 `ES_PACK` lines during W, observed]**; that the V1/V2 branch is unreachable on a 5.0.9 node **[inferred: the server refuses protocol 2 (observed) and the source has no other caller of `pack`; a UDF is handed the client's version, which is 3 or higher]**.
6. **Deviations and gaps.** The cluster tier is the file's alternative, run although the tier is declared n/a: it does not test line 250, it shows the V3+ branch and node usage. The V1/V2 branch was reached only in the unit tier by calling the class directly. Heap during the UDF queries was not captured (defect 4). One run per tier (unit 3 repetitions).
7. **Core question.** Usage did not follow the constraint: the 65535-byte check applies only to V1 and V2; at V2 an element of 65536 bytes is rejected before the result buffer is allocated (2.2 KB allocated), while V3 and V4 accept elements to 8 MiB (unit) and 1 MiB (node, through the UDF path and plain writes) and allocate and store in proportion to the bytes (flat 0.2 % per element across the sweep; 1.005 disk bytes per payload byte at 65535, 65536 and 1 MiB). A guardrail on value size, applied to an ordinary role, does reject at its threshold, so the node's write path can show a cap when one exists. So the check at `CodecUtils.java:250` does not cap memory or disk usage.

**Conclusion (one line):** unit B2g rows 1 and 2 and cluster B3g row 1 plus its control row (the alternative tier; line 250 itself not reachable on a node) — Confirmed (does not cap; positive control moved).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit/test.out`, the cluster `stdout.txt` (Byteman lines, protocol error), `readings.txt` for the client-side results and `system.log` (the `MEMTABLE_LIMIT` flush): 19 PASS, 0 FAIL (`run1/selfcheck.out`). Two checks were rewritten after the first look because the first versions were wrong about the harness: the V2 probe check reads the server log, and the memtable-per-byte check excludes the 1 MiB table, which had a `MEMTABLE_LIMIT` flush (defect 3). The case's rows were not changed.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | exception texts and Byteman remaining values re-read. |
| 2. Readings | yes | |
| 3. Matched row | yes | lengths recomputed. |
| 4. Excluded rows | yes | same script. |
| 5. Observed vs. inferred | yes | no inferred statement carries the verdict. |
| 6. Deviations and gaps | yes | the alternative tier is labelled as such. |
| 7. Core question | yes | follows B1. |

### 5.2 Run 2?

No — 2026-10-28. The unit tier repeats to the byte; the cluster readings are exact Byteman lines, server log lines and byte counts; nothing inferred carries the verdict.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative.

**Claim tested (B1):** the 65535-byte element check at `CodecUtils.java:250` does not bound memory or disk used by a node: it only rejects V1/V2 serialization of an oversized element, usage is unchanged by it, and it is never applied for V3 to V6. (Falsified if heap held by serialization differs by protocol version in a way explained by this check, or if a 5.0.9 node ever evaluates the V1/V2 branch.)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (V2 throws only above 65535 before allocating the result; V3/V4 accept to 8 MiB; allocation proportional to payload, no step) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster (the file's alternative; does not reach line 250) | Confirmed (V2 refused by the server; v4 accepts 65536 B and 1 MiB elements; disk bytes proportional, no step; `sizeOfValue` evaluated only at V3/V4; control rejects) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** unit: the payload-growth sweep (N = 1..1000 at S = 65535) moved allocation from 65.7 KB to 65.6 MB in proportion; cluster: `column_value_size_fail_threshold: 512KiB` with an ordinary role rejected the 1 MiB insert and accepted 65535 and 65536 (the first form of the control, with the shipped authenticator, could not bind: defect 2).

**Feedback filed:** section D of the case file (uncommitted); the audit's amendments (B2 notes, B3 alternative, B3 control mechanism; 2026-10-28, uncommitted) are in the case file, final sha256 in §1 and in the final report; `_INDEX.md` is for the orchestrator.
