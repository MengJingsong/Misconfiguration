# native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous — stage-4 results  <!-- file: results/native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous.md -->

> **Case:** [`native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous`](../../stage3-ai-deep-read/cases/native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit and cluster Confirmed (does not cap); no run 2
>
> **Outcome class:** true negative (stage-3 estimate `negative`, stage-4 effect `does not cap`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 after the audit's amendments, taken before any reading: `3949ad4274e3a2e3d09405d12b9357fc6f44b65d5ef57d9985001e083efed1e1`. File committed at `b68711e5` (HEAD); the amendments of 2026-10-28 are uncommitted. The control mechanism was amended once more during run 1 (the intermediate sha256 after that amendment, before section D, was not recorded) (defect 2 below; claim, predictions and rows unchanged), and section D (stage-4 feedback) was filled after run 1: final sha256 `6c83b5be9abaf9c0fbf73daa7feaaea582be5f4a1c4ffdb019d01a029325da11`. |
| **Harness** | `harness/native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous/` (uncommitted; README there) |
| **Tiers and values** | Unit: V2 / V3 / V4 x N = 65535, 65536, 200 000 x payload 1 B / 100 B, 3 repetitions; control payload sweep. Cluster: one node; workload W (plain `set<int>` writes, N = 1000 / 65536 / 500 000, v4), workload U (Java UDF returning `list<int>` of the same N, v3 and v4), V2 probe, and a second node start with `collection_size_fail_threshold: 200KiB` as positive control. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note |
|---|---|---|---|
| A | quantity is memory or disk bytes | Met | Allocated bytes of the serialize call (unit); heap, memtable and disk bytes (cluster). |
| A | knob varied (>= 3 values) or other approach | Partly -> Met | The literal is hard-coded; the dose is N across 65535 (65535, 65536, 200 000) and the protocol version, which switches the check on and off (B2b). Stated in A1/B2b. |
| A | real resource measured | Met after amendment | Amended to `ThreadMXBean.getThreadAllocatedBytes` (exact) beside the coarse heap delta. |
| A | driven to the limit and past it | Met | N = 65535 (at), 65536 and 200 000 (past). |
| A | positive control (negative claim) | Partly -> Met | Unit: payload 1 B vs 100 B (numeric floor added). Cluster: B3h named no knob; amended to `collection_size_fail_threshold` (exists, `Config.java:918`). |
| B | prediction in numbers; rows; disallow evidence | Partly -> Met | "roughly as much" made numeric (>= 0.8 x V3 and >= V2 result size; < 0.5 is refuted); result sizes added. Disallow evidence: the "65535 elements" exception at V2. |
| B | alternatives and controls | Met | Version isolates the literal; payload sweep isolates bytes. |
| C | human / AI can follow; values exact | Partly -> Met | Amended: factory names verified (`TypeCodec.list` :345, `TypeCodec.blob` :265), JUnit run line. |
| D | harness exists | Met (listed) | Step 1. |
| D | workload reaches the limit | Not met -> Met after amendment | B3c's plain `set<int>` insert never calls `CodecUtils` (`grep` finds callers only in `TypeCodec`, reached on a node only by the UDF layer), so a cluster run as written would test nothing about the traced path. Amended: workload U (UDF) reaches `pack`/`writeSize` with the client's version; workload W is kept as the usage comparison. |
| D | citations | Met | `CodecUtils.java:48-57,95-117,101-106`, `TypeCodec.java:2083-2127,2479`, `ProtocolVersion.java:42-43,66,104-105` match. `pack` allocates (56) before `writeSize` (57): A3 step 5 holds in the source. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Cluster workload must reach `CodecUtils` (UDF), keep the plain write as the usage comparison | Applied (B3 amendment 2026-10-28) | Group D |
| R2 | Numeric "roughly as much", exact instrument, result sizes | Applied (B2 amendments) | Group B |
| R3 | Named positive-control knob | Applied (`collection_size_fail_threshold: 200KiB`) | Group A |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (unit 17:49 MDT; cluster default node start about 18:14 MDT, control about 18:20 MDT) |
| Node | `pc41` (`node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`) |
| OS / kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-b34/src` (`copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `b68711e5`, `ant build-test`; shared with the two sibling cases, never edited except for the copied probe test classes) |
| Case-file / harness commit | `b68711e5` with the uncommitted amendments (sha256 in §1) / uncommitted |
| Node data | local disk `~/stage4-tmp/b34/cs/node` (recreated at each node start) |
| Full logs | `pc41:~/s4-b34/logs/collection_size_limit/run1/` (`unit/`, `cluster/default/`, `cluster/control/`, `selfcheck.out`); the first cluster attempt is in `attempt3-control-guardrail-not-applied-under-AllowAll/` |

**Attempts before the run 1 recorded here:** unit tier, first try: the probe could not be copied (`test/unit/.../cql3/functions/types/` did not exist in the tag) — defect 1, nothing ran. Cluster tier, first try (both node starts ran, 2026-10-28 18:08 to 18:14 MDT): the default node start produced the same readings as run 1; the control node start (guardrail with the shipped `AllowAllAuthenticator`) accepted all three inserts — defect 2; the tier restarted from its beginning with the amended control. The frozen predictions and rows were not touched (the case file's control paragraph was amended, dated, see §1).

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | unit, first try | B2a | the test directory `test/unit/org/apache/cassandra/cql3/functions/types/` does not exist in the tag, so the copy of the probe failed | the run script creates it | harness-only | none |
| 2 | cluster, first try | B3h control (my audit amendment) | `collection_size_fail_threshold: 200KiB` rejected nothing: guardrails are skipped for superusers and `ClientState.isSuper()` is true when the authenticator requires no authentication (`ClientState.java:594-605`, `Guardrail.java:93-96`); the threshold only produced the flush-time ERROR log ("Detected collection s in row 1 ... of size 1572876, this exceeds the failure threshold of 204800") | control node runs `authenticator: PasswordAuthenticator` and the writer is an ordinary role | claim, predictions and rows unchanged; amended in the case file (dated) and the tier restarted | none |
| 3 | run 1 | B3d | `heapmax_kB` is 0 for the UDF queries that finish between two 0.5 s heap samples | none; the heap leg is not used for the verdict (the Byteman lines carry the UDF leg) | reading | none |
| 4 | run 1 | B2d | thread-allocated bytes are exact for large arrays but the many small per-element buffers are counted at TLAB granularity, and the first measured V4 cell carries warm-up noise (min 3.7 MB, max 6.1 MB over 3 reps) | all other cells repeat to the byte; the verdict uses ratios with margin | reading | none |

## 4. Run 1

**Scope:** unit tier (18 cells x 3 reps); cluster tier, two node starts (default, control). **Command log:** `native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous/run1/` (`unit/summary.txt`, `unit/test.out`, `cluster/default/readings.txt`, `cluster/default/cs-byteman-lines.txt`, `cluster/control/readings.txt`); checker `harness/.../selfcheck.py`, output `run1/selfcheck.out` (22 PASS, 0 FAIL).

### 4.1 Readings

**Unit tier** (`run1/unit/test.out`, median of 3 thread-allocated-byte readings; `TypeCodec.list(TypeCodec.blob())`, 1 test passes):

| Payload S, N | V2 | V3 | V4 |
|---|---|---|---|
| S=1, N=65535 | ok, 196 607 B, count field 65535; alloc 6.75 MB | ok, 327 679 B; 6.88 MB | ok, 327 679 B; 4.13 MB (warm-up cell) |
| S=1, N=65536 | **IllegalArgumentException** "Native protocol version 2 supports up to 65535 elements in any collection - but collection contains 65536 elements"; alloc 3.61 MB | ok, 327 684 B, count 65536; 3.74 MB | same as V3 |
| S=1, N=200 000 | **IllegalArgumentException** (200 000 elements); alloc 11.00 MB | ok, 1 000 004 B; 11.40 MB | same as V3 |
| S=100, N=65535 | ok, 6 684 572 B; 10.09 MB | ok, 6 815 644 B; 10.22 MB | same |
| S=100, N=65536 | exception; 10.09 MB | ok, 6 815 748 B; 10.22 MB | same |
| S=100, N=200 000 | exception; 30.80 MB | ok, 20 800 004 B; 31.20 MB | same |

Failing V2 / succeeding V3 allocation at the same N and S: 0.965 (S=1, N=65536 and 200 000), 0.987 and 0.987 (S=100); the failing call's own result size (`2 + N*(2+S)`) is 196 610 / 600 002 / 6 684 674 / 20 400 002 B, all below its allocation. Control: V3, N=200 000: 11.40 MB at S=1, 31.20 MB at S=100, a rise of 19.8 MB against the 17.8 MB floor (0.9 x 99 x N).

**Cluster tier**, default node start (`run1/cluster/default/readings.txt`, `cs-byteman-lines.txt`):

| Item | Reading |
|---|---|
| V2 probe (python driver, protocol 2) | client: `connected=no` ("Connection ... was closed"); server log: "Protocol exception ... Invalid or unsupported protocol version (2); supported versions are (3/v3, 4/v4, 5/v5, 6/v6-beta)" |
| W: plain `set<int>` insert on v4, N = 1000 / 65536 / 500 000 | all accepted; read back 1000 / 65 536 / 500 000 elements; Byteman `CS_PACK` calls during W: 0; memtable data 24 041 / 1 572 905 / 12 000 041 B (24.0 B per element at the two large N); SSTable `Data.db` 4 039 / 262 801 / 2 004 854 B (4.01 B per element) |
| U: UDF `RETURNS list<int>`, v4 then v3, N = 1000 / 65536 / 500 000 | all six queries returned N elements; Byteman: `CS_PACK ver=V4/V3 elements=N`, `CS_WRITESIZE ver=V4/V3 size=N`, `CS_PACK_RET len=4+8N` (8 004 / 524 292 / 4 000 004), 6 calls, no V1/V2 |

**Cluster tier**, control node start (`collection_size_fail_threshold: 200KiB`, `PasswordAuthenticator`, writer `ord`, `SUPERUSER = false`): N=1000 accepted (24 041 B in the memtable); N=65536 rejected: `InvalidRequest ... Guardrail collection_size violated: Detected collection s of size 1572864, this exceeds the failure threshold of 204800.`; N=500 000 rejected (size 12 000 000); nothing was stored for the two rejected sizes (memtable 0, SSTable 0).

### 4.2 Conclusion and logic

1. **Validity.** The literal's range was crossed: N = 65536 and 200 000 exceed 65535 and the V2 call threw the count message in all 3 reps [observed: `unit/test.out`]; the cluster UDF calls had N = 65536 and 500 000 under V3 and V4 [observed: `cs-byteman-lines.txt`]. "Hold fixed": heap and copy as in B2a (JUnit under `ant testsome`, `-Xmx512m`), 1 GiB G1 node heap, `user_defined_functions_enabled: true` and (control only) the guardrail yaml line [observed: `extra.yaml`, `unit/summary.txt`]. The cluster positive control moved (below). Valid.
2. **Readings.** (a) The first measured V4 cell is noisy (defect 4); all other cells repeat to the byte. (b) The V2 client error text does not name the protocol; the server log does [observed]. (c) The control's first form did not bind (defect 2). (d) The heap sampler missed fast UDF queries (defect 3).
3. **Matched row.** Unit B2g rows "V2 throws above 65535, V3/V4 do not" and "V2 failing call still allocates about as much as V3 at same N (claim confirmed)": V2 throws at 65536 and 200 000, V3/V4 succeed with the exact length `4 + N*(4+S)` and count field N; the failing V2 call allocated 96.5 to 98.7 % of the V3 call and more than its own V2 result size (the result buffer is allocated before `writeSize` throws) [observed]. Control row: the payload sweep moved allocation by 19.8 MB (floor 17.8 MB) [observed]. Cluster B3g row "Smooth growth across 65535, no 65535 error -> claim confirmed" (with its V2-refused row): V2 refused by the server with a protocol-version error; the set writes at 1000 / 65536 / 500 000 on v4 were accepted with no 65535 text; bytes per element at 65536 and 500 000 are 24.00 and 24.00 in the memtable and 4.01 and 4.01 on disk (no step); the UDF path, the only one that reaches `CodecUtils`, called `writeSize` with sizes up to 500 000 under V3 and V4 without error [observed]. Cluster positive control row: the guardrail rejected N = 65536 and 500 000 and accepted 1000 where the same inserts were all accepted without it [observed: `cluster/control/readings.txt`].
4. **Excluded rows.** "V3 throws at 65536": it did not. "V2 failing call allocates far less than V3 (claim refuted)": ratio 0.965 to 0.987, not < 0.5. "Allocation flat while N and payload grow": it grew. "N never exceeds 65535": it reached 200 000 (unit) and 500 000 (cluster). "Error mentioning 65535 at N above 65535 on V3+ (refuted)": none in the client results, the node log or the Byteman lines [observed: `selfcheck.out`]. "V2 accepted by the server": refused. "Positive control does not move usage": it moved. "N never above 65535 achieved (other limits fail first)": the 12 MB insert was accepted. No Refuted row applies.
5. **Observed vs. inferred.** Inferred: that a plain `set<int>` write never reaches `CodecUtils` **[inferred: the source (`TypeCodec` is reached only by the UDF layer) and 0 `CS_PACK` lines during W, observed]**; the 24 B per element in the memtable is the node's accounting, not a measured heap object **[inferred: `nodetool tablestats` memtable data size]**.
6. **Deviations and gaps.** The V1/V2 branch is reachable only by calling the codec directly (unit), as the file says; the cluster tier shows the V3+ branch and the usage, not line 101. Heap during the UDF queries was not captured (defect 3). The file's `collection_size_warn_threshold` was not used. One run per tier (unit 3 repetitions). No server path with V1/V2 was found: not verified beyond "the server refuses protocol 2".
7. **Core question.** Usage did not follow the literal: the V2 call that the literal rejects had already allocated 96.5 to 98.7 % of what the accepted V3 call allocates, and under V3 and V4 the same method writes a 4-byte count with no cap (unit lengths `4 + N*(4+S)`, up to 200 000 elements; node UDF results up to 500 000 elements); on the node, set writes of 1000 to 500 000 elements grow linearly with no step at 65535 (24.0 B per element in the memtable, 4.0 B on disk). A guardrail on the same collection bytes does bind (it rejected two of three inserts), so the harness can see a cap when one exists. So the 65535 literal does not cap memory or disk.

**Conclusion (one line):** unit B2g (V2 throws above 65535, V3/V4 do not; failing call allocates about as much as V3) and cluster B3g (smooth growth, no 65535 error, V2 refused, positive control moved) — Confirmed (does not cap; positive control moved).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit/test.out`, the cluster `stdout.txt` (Byteman lines, server protocol error, guardrail errors), `readings.txt` for the client-side results, and `system.log`: 22 PASS, 0 FAIL (`run1/selfcheck.out`). Two checks were corrected after the first look: the V2 probe check reads the server log (the client text is "connection closed"), and the V3-versus-V4 equality check excludes the first, warm-up cell (defect 4); both are checker issues, not changes to the case's rows.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | exception messages and Byteman sizes re-read. |
| 2. Readings | yes | noise and misses stated. |
| 3. Matched row | yes | ratios recomputed from the medians; lengths recomputed. |
| 4. Excluded rows | yes | same script. |
| 5. Observed vs. inferred | yes | no inferred statement carries the verdict. |
| 6. Deviations and gaps | yes | |
| 7. Core question | yes | follows B1. |

### 5.2 Run 2?

No — 2026-10-28. The unit tier repeats to the byte (outside one warm-up cell); the cluster readings are exact Byteman lines, server log lines and byte counts; nothing inferred carries the verdict.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative.

**Claim tested (B1):** usage does not follow the literal 65535: it limits only the count representable under V1/V2, and a collection with more than 65535 elements serializes with a count that grows with it under V3+ with no cap, so the check does not bound heap or disk.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (V2 throws above 65535, V3/V4 do not; the failing V2 call allocates 96.5 to 98.7 % of V3; payload control moved) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (smooth growth across 65535 with no 65535 error, V2 refused by the server, UDF path called with sizes to 500 000 under V3/V4; positive control moved) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** unit: payload 100 B against 1 B at V3, N=200 000: +19.8 MB allocated (floor 17.8 MB); cluster: `collection_size_fail_threshold: 200KiB` with an ordinary (non-superuser) role rejected N = 65536 and 500 000 sets and accepted N = 1000, where the same inserts were all accepted without it; the first form of the control did not bind (defect 2).

**Feedback filed:** section D of the case file (uncommitted); the audit's amendments (B2 note 2026-10-28, B3 workload and control, B3 control mechanism) are in the case file, final sha256 in §1 and in the final report; `_INDEX.md` is for the orchestrator.
