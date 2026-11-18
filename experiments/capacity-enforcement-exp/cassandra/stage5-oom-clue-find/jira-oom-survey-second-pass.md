# J1 second pass (Cassandra JIRA OOM survey) — 2026-11-16

> Filed 2026-11-16 as the second-pass record of [`jira-oom-survey.md`](jira-oom-survey.md). Paths below (`j1/…`,
> `j1sp/…`) are the session's working files (scratchpad, not in the repo); the result is [`jira-oom-survey.csv`](jira-oom-survey.csv).

Input `j1/merged-v1.csv` (604 rows, 245 kept) → output `j1/merged-v2.csv` (604 rows, 246 kept).
Columns: v1 columns + `shard` + `second_pass`. Note: v1 had **no `shard` column** (the brief said it did);
it is derived here from `j1/out-shard{1..4}.csv` (every key found in exactly one shard file).
Scripts: `j1sp/show.py` (row + cached JIRA text), `j1sp/d.sh` (diff reader over `/mydata/j1/cassandra-history.git`),
`j1sp/apply.py` (all edits, reproducible). Full per-row change list: `j1sp/changelog.txt`.

`second_pass` values: `normalized` (task 1 changed class or flow), `diff-checked` (task 2),
`spot-checked:agree` / `spot-checked:corrected:<what>` (task 3); combined with `;` where several apply.

## Task 1 — conventions

Rules applied (from verification-protocol.md "Unprotected results" and the brief):

- **1a.** All 73 kept plain `unprotected` rows split. `unprotected:configuration` only where a control exists and its
  default/configured value leaves it off or unbounded (11 rows: 1445, 4856, 8116, 8763, 10689, 10930, 10985, 13931,
  15531, 19976, 21227). One row moved to `bypass:exempt-path` (12707, threshold exists but not applied in that loop;
  low confidence). The other 61 → `unprotected:accumulation` (no control, or only an implicit timeout×rate /
  concurrency×size bound; corrupt-length allocations are included here).
- **1b.** Leaks and other rows whose `control_before` names no applicable control were moved out of
  convergence/bypass to `unprotected:accumulation` (14 rows): 436, 2301, 4142, 5222, 6191, 10797, 10821
  (was `convergence:replacement-overlap`), 13754, 14834, 19942, 15452 (only MaxDirectMemorySize = the budget),
  11854 and 3537 (were `bypass:release-defect`; 3537's only bound is implicit timeout expiry), 13126 (low confidence).
  Leaks with no control keep/receive `fix_kind = release fix` when fixed (651, 2868, 6047, 8499, 2708, 9549,
  11739, 13754, 14834, 15902, 17895, 19942). Leaks inside a controlled pool stay `bypass:release-defect`
  (157, 3163, 8164, 11026, 11159, 11838, 12796, 19703). Two leak-like rows keep a non-release fix_kind because
  the fix was not a release (6191 warning only, 6541 JVM flag).
  Boundary used: `convergence:multiplicity` requires an explicit per-owner cap (configured or hard-coded limit,
  e.g. 4265 frame size, 14096 tree depth, 19336 repair_session_space); a per-owner natural object size with no
  cap counts as accumulation. Rows kept as convergence under that boundary but worth a look: 3171, 3535.
- **1c.** Flows folded (13 rows): commit log / commit-log replay (264, 885, 14474), SASI flush (11383) and MV
  build (12268) → `replica mutation stage → memtable → flush`; sstable open/startup (8052, 9573) →
  `read path and caches`; JVM/runtime, JMX, JDK NIO cache, direct budget (2868, 6541, 10930, 13931, 19976) →
  `other:jvm-runtime`; spelling normalised to `other:<x>` (19959 `other:multiple`). Original one-off name kept in
  `flow_detail`. Remaining `other:` flows: jvm-runtime 5, accord 1, multiple 1, logging 1. `unknown` flow: 8.

## Task 2 — diff-backed check of the 36 `subject+files only` rows

Every listed commit was read in the bare clone (non-test source hunks). All 36 **confirmed** for class and
fix_kind as judged against the issue (class changes on 14 of them come only from the task-1 conventions, e.g.
`unprotected` → `unprotected:accumulation`; 14834 → accumulation under 1b). `diff_read` set to `diff read` for all 36.
Remarks recorded but not changed: 2868's fix is an API workaround (kept `release fix` per rule 1b);
4555's fix also adds a 64K validation (kept `other`); 6357's fix was reverted (ee950b41) and class stays `unknown`;
20298's only commit is test-only (kept `none (unfixed)` although resolution is Fixed);
19336's new limit `concurrent_merkle_tree_requests` defaults to unlimited (in 5.0.9 an unprotected-configuration variant lead).

## Task 3 — random spot-check

`random.seed(20261116)`; `random.sample(kept_diff_read, 25)` then `random.sample(excluded, 15)`, both lists in
merged-v1 file order; `kept_diff_read` = the 79 kept rows with v1 `diff_read == 'diff read'`.
Each issue was re-read from the cached JSON (description and comments); for kept Fixed rows the fix commit was re-read.

| Key | v1 screen / class / fix_kind | Result |
|---|---|---|
| CASSANDRA-4141 | kept / bypass:accounting-mismatch / accounting change | corrected:fix_kind accounting change→other |
| CASSANDRA-4142 | kept / convergence:multiplicity / other | corrected:class convergence:multiplicity→unprotected:accumulation (no per-owner control, rule 1b) |
| CASSANDRA-9530 | kept / unprotected / new limit | agree (class refined to `unprotected:accumulation`) |
| CASSANDRA-8116 | kept / unprotected / other | agree (class refined to `unprotected:configuration`) |
| CASSANDRA-12769 | kept / unprotected / other | agree (class refined to `unprotected:accumulation`) |
| CASSANDRA-7743 | kept / convergence:multiplicity / other | agree |
| CASSANDRA-157 | kept / bypass:release-defect / release fix | agree |
| CASSANDRA-18513 | kept / unprotected / new limit | agree (class refined to `unprotected:accumulation`) |
| CASSANDRA-3741 | kept / bypass:accounting-mismatch / accounting change | agree |
| CASSANDRA-16 | kept / unprotected / new limit | agree (class refined to `unprotected:accumulation`) |
| CASSANDRA-14096 | kept / convergence:multiplicity / new limit | agree |
| CASSANDRA-15902 | kept / unprotected:accumulation / release fix | agree |
| CASSANDRA-8499 | kept / unprotected / release fix | agree (class refined to `unprotected:accumulation`) |
| CASSANDRA-14855 | kept / unprotected / other | agree (class refined to `unprotected:accumulation`) |
| CASSANDRA-4860 | kept / bypass:accounting-mismatch / accounting change | agree |
| CASSANDRA-10972 | kept / unprotected / backpressure | agree (class refined to `unprotected:accumulation`) |
| CASSANDRA-6087 | kept / bypass:late-enforcement / other | agree |
| CASSANDRA-3537 | kept / bypass:release-defect / release fix | corrected:class bypass:release-defect→unprotected:accumulation (implicit timeout bound only, rule 1b) |
| CASSANDRA-12618 | kept / unprotected / other | agree (class refined to `unprotected:accumulation`) |
| CASSANDRA-3163 | kept / bypass:release-defect / release fix | agree |
| CASSANDRA-9573 | kept / unprotected:accumulation / other | agree |
| CASSANDRA-12689 | kept / unprotected:accumulation / other | corrected:flow internode messaging→replica mutation stage |
| CASSANDRA-8285 | kept / bypass:late-enforcement / other | agree |
| CASSANDRA-208 | kept / unprotected / other | agree (class refined to `unprotected:accumulation`) |
| CASSANDRA-2708 | kept / unprotected:accumulation / release fix | agree |
| CASSANDRA-18263 | excluded / - / - | agree |
| CASSANDRA-14190 | excluded / - / - | agree |
| CASSANDRA-12034 | excluded / - / - | agree |
| CASSANDRA-14937 | excluded / - / - | agree |
| CASSANDRA-20564 | excluded / - / - | agree |
| CASSANDRA-3398 | excluded / - / - | agree |
| CASSANDRA-15118 | excluded / - / - | agree |
| CASSANDRA-6193 | excluded / - / - | agree |
| CASSANDRA-5727 | excluded / - / - | agree |
| CASSANDRA-6552 | excluded / - / - | agree |
| CASSANDRA-18322 | excluded / - / - | agree |
| CASSANDRA-218 | excluded / - / - | agree |
| CASSANDRA-262 | excluded / - / - | agree |
| CASSANDRA-6404 | excluded / - / - | agree |
| CASSANDRA-11845 | excluded / - / - | corrected:screen excluded→kept + class unprotected:configuration |

**Agreement (kept 25, excluded 15):**

- Screen: 39/40 (97.5 %). Kept 25/25; excluded 14/15. Disagreement: 11845 (`OutOfMemoryError: Map failed` in
  StreamReceiveTask, fixed by raising vm.max_map_count; excluded as "OOM only in a later comment", but the same
  family 13008/13523/14474 is kept) → re-screened kept, `unprotected:configuration`, repair / streaming, native.
- Class (kept, n = 25): 23/25 (92 %) against v1 strictly. The 2 disagreements (4142 convergence → accumulation,
  3537 release-defect → accumulation) come from the convention in 1b, not from a different reading of the issue.
  9 further rows changed only from plain `unprotected` to a subclass (task 1a); counted as agree.
  Judged on mechanism only: 25/25.
- fix_kind (kept, n = 25): 24/25 (96 %). 4141: `accounting change` → `other` (the fix only removes the
  `initialCapacity(capacity)` preallocation; cache weighing unchanged).
- Flow (not asked, recorded): 24/25; 12689 `internode messaging` → `replica mutation stage → memtable → flush`
  (MutationStage threads blocked on MV locks).

## Rows a human should look at

1. **12707** now `bypass:exempt-path` (tombstone_failure_threshold not applied in QueryFilter.gatherTombstones per
   reporter; a comment says 3.0+ is not affected). Low confidence; alternative is `unprotected:accumulation`.
2. **13126** moved release-defect → accumulation (dead SSL buffers held against MaxDirectMemorySize until GC);
   v1 already had low confidence.
3. **11082** Netty high/low water marks configured but not checked: kept `unprotected:accumulation`, but this could
   be read as a control that is not enforced (bypass).
4. **8295, 10766**: memtable space limit exceeded while flush cannot keep up, classed unprotected (configuration /
   accumulation). May be `bypass:late-enforcement` as 5982/6079/8285 are.
5. Configuration-vs-accumulation boundary: **1445** (per-CF cache sizes in rows), **15531** (disk_access_mode mmap),
   **21227/21233** (UDF heap; UDFs off by default).
6. Convergence-vs-accumulation boundary (rule in 1b): **3171, 3535** kept convergence; **4142, 5222, 436, 2301,
   6191** moved to accumulation.
7. **11845** newly kept; similar excluded rows with an OOM only in comments that might deserve the same treatment:
   **6862** (schema digest; see 11748), **8917**, **14653** ('Map failed' in description).
8. **42 kept rows remain `unknown`** (mostly closed without root cause); not reworked in this pass.
9. **20298** resolution Fixed but its only commit is test-only; **2868** fix_kind `release fix` though the fix is an
   API workaround.

## Counts after the second pass (246 kept)

- Class: unprotected:accumulation 131 · unknown 42 · unprotected:configuration 22 · bypass:accounting-mismatch 18 ·
  convergence:multiplicity 14 · bypass:release-defect 8 · bypass:late-enforcement 5 · bypass:exempt-path 4 ·
  convergence:standing-pool 2.
- Flow: replica mutation stage → memtable → flush 54 · read path and caches 39 · repair / streaming 30 · compaction 28 ·
  client request intake 28 · coordinator read 19 · coordinator write 11 · internode messaging 9 · hints 8 · unknown 8 ·
  other:jvm-runtime 5 · gossip / schema 4 · other:accord 1 · other:multiple 1 · other:logging 1.
- fix_kind: none (unfixed) 124 · other 47 · release fix 24 · new limit 20 · accounting change 14 ·
  doc or default change 11 · backpressure 6.
- Budget: heap 197 · direct 19 · native 17 · cgroup-kernel 12 · unknown 1.
- Resolution group: fixed 120 · unfixed-open 45 (Unresolved 42, Later 3) · closed-not-fixed 81
  (by design or invalid 45: Won't Fix 17, Not A Problem 13, Invalid 8, Not A Bug 4, Information Provided 2,
  Incomplete 1; Duplicate 26; Cannot Reproduce 10).
- `diff_read` (kept): diff read 115 · n/a 126 · no commit found 5.
