# Stage 4 — DRAFT designs for `none`-type cases, "kind 1" batch

Drafted 2026-10-28. **Documents only: nothing here was run, built or filed into a case file.** Each section below is written to be pasted into B2 (and B3 where
the kind allows) of `stage3-ai-deep-read/cases/<stem>--autonomous.md` as a dated audit amendment, following [`none-type-design.md`](none-type-design.md) §3-4.
Every `file:line` cited was re-read in `cassandra/cassandra-5.0.9/` on 2026-10-28; where a case file's own citation is wrong, the section says so.
`Alloc` below means the existing `stage4.Alloc` helper (`ThreadMXBean.getThreadAllocatedBytes` between `start(tag)`/`end(tag)`,
`harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/Alloc.java`), or the same call made directly in a JUnit method.

## Summary

| Stem | Operand kind (confirmed?) | Runnable? | Instrument | Effort | Recommendation |
|---|---|---|---|---|---|
| no_constraint-isempty-size | 1 (`rows.size()`), confirmed | unit; cluster n/a | Alloc around `ResultSetBuilder.build()` via Byteman | 0.5 d (low value) | run in shared class, or close from source |
| no_constraint-isempty-size-2 | 1 for `FromResultSet`/`FromResultList` only; pager variants throw (A1 wrong) | no | none | 0 | Confirmed from source, not run |
| no_constraint-needfiltering-restriction_count | not kind 1: count is only compared with 0 (kind 2); outcome rejects a query | unit, needs a reachability probe first | Alloc of the statement | 1 d | run only if the probe shows line 992 can be true; else from source |
| no_constraint-hasunrestrictedclusteringcolumns-clustering_count | 1 by letter (schema-limited counts of a few), really kind 2 | no | none | 0 | Confirmed from source, not run |
| no_constraint-isdone-remainingcount | 1 (array slots left), confirmed, but the array is allocated before the check | no | none | 0 | Confirmed from source, not run |
| no_constraint-hascomponent-componentbounds_size | 1 (tuple element count), confirmed; bounded by clustering columns | no | none | 0 | Confirmed from source, not run |
| no_constraint-iscolumnrange-clustering_restrictions | not kind 1: a boolean over restriction shape (kind 2) | unit via CQLTester | Alloc around the read command | 1 d | worth running (two arms, same result) |
| no_constraint-doesaggregation-aggregatefactories | not kind 1: count compared with 0 is a flag (kind 2), but the branch gates result retention | unit via CQLTester | Alloc + retained result size | 1 d | worth running |
| no_constraint-hascomponent-i_nextsize | 1 (`nextSize` component count, `i` index), confirmed | unit, new test class | Alloc around `compareNextTo` | 1 d | worth running |
| none-addall-size | 1 (`size` vs `tombstones.size`, element counts), confirmed | unit; cluster optional | Alloc + `unsharedHeapSize()` + capacity | 1.5 d | worth running (best case) |

---

## 1. no_constraint-isempty-size (`ResultSet.isEmpty()`)

**Kind.** 1 confirmed: `size()` is `rows.size()` (`ResultSet.java:64-66`), `isEmpty()` is `size() == 0` (`:67-70`). The data is the `rows` list itself (field `:49`).
**What the branch gates.** The only caller of the typed `ResultSet` is `ResultSetBuilder.build()` (`ResultSetBuilder.java:157`; check at `:168`): empty AND `groupMaker != null` AND `groupMaker.returnAtLeastOneRow()` adds ONE output row. The true branch allocates one row; it can never remove data.
**Trigger.** `CQLTester` (home: `validation/operations/AggregationTest`): table `t(pk int, ck int, v int, primary key(pk, ck))`. Arm A `SELECT count(*) FROM t WHERE pk=1` (aggregate; `returnAtLeastOneRow()` true), arm B `SELECT v FROM t WHERE pk=1` (plain). At 0 rows both reach `:168`.
**Proof the check ran.** Byteman rule AT EXIT of `ResultSet.isEmpty` with a counter, plus `Alloc.start/end` AT ENTRY/EXIT of `ResultSetBuilder.build`. Counter 0 = Invalid.
**Sweep (rows inserted before the select):** 0, 1, 1,000, 100,000. Only 0 is in the branch for arm A; 1 and above are the other side.
**Measured.** `Alloc` bytes of `build()` only, median and range of 7 repeats per value (3 warm-up discarded), plus `resultSet.size()` from the return value.
**Branch flip.** At 0 rows: A minus B. Prediction: A − B is one output row (an `ArrayList` of one `ByteBuffer` for the count, 100 to 300 B). At 1,000 and 100,000 rows: no branch difference, growth equals the rows added, same slope in both arms.
**Positive control.** The same `Alloc` around `build()` for a plain select of 1,000 vs 100,000 rows must move by about 100x (the instrument sees result growth). Per-call reader model: `batch_size_fail_threshold-verifyBatchSize-failThreshold--guided`.
**Noise floor.** Two identical 0-row runs, 7 repeats each; difference must be under 64 B or A − B is "not resolved".
**Conclusions.** Confirmed / does not cap: A − B equals one row, growth tracks rows equally, control moved. Refuted / caps: branch removes or bounds rows (impossible by source: it only adds). Not confirmed: A − B under the noise floor. Invalid: counter zero, or control did not move.
**Honest note.** The expected result is what the source already says (one added row). Run only because the shared class makes it nearly free; otherwise close from source.

## 2. no_constraint-isempty-size-2 (`UntypedResultSet.isEmpty()`)

**Kind.** Not runnable. **Correction to A1/A3:** `FromPager.size()` (`UntypedResultSet.java:203-206`) and `FromDistributedPager.size()` (`:269-272`) throw `UnsupportedOperationException`; they do not "iterate pages". Only `FromResultSet.size()` (`:113`) and `FromResultList.size()` (`:155-158`) return a count, read from an already built list. The case's `:247` for `FromDistributedPager` is not its `size()` line.
**Why no run.** `isEmpty()` (`:88-91`) allocates nothing, and neither branch allocates; callers (e.g. `PasswordAuthenticator.java:183`) use it as found/not-found on one-row system queries. A per-call measurement would read 0 B on both sides, which shows only that the instrument reads zero for a no-allocation call. No operand exists that the check acts on.
**Recommendation.** Close as *Confirmed from source, not run*; B2/B3 stay `n/a`. Send the pager correction back to stage 3 (section D).

## 3. no_constraint-needfiltering-restriction_count (`StatementRestrictions.needFiltering`)

**Kind.** Better kind 2. At `StatementRestrictions.java:992` the count `numberOfRestrictions` (built `:988-990`) is only compared with 0 and combined with `!clusteringColumnsRestrictions.isEmpty()`; `:985` is an index-support predicate. The count is a handful of parsed WHERE terms.
**Possible under-reading by stage 3.** `SelectStatement.java:1602-1611` (`checkNeedsFiltering`) rejects the statement at prepare time (`checkFalse(restrictions.needFiltering(table), ...)`, `:1610`) when ALLOW FILTERING is absent and the query is a key range or uses an index. A true result thus stops a filtering scan from ever running: a gate on work, not a size cap.
**Reachability probe first (audit).** The true branch at `:992` needs zero non-PK restrictions with non-empty clustering restrictions, AND `isKeyRange()||usesSecondaryIndexing()` AND `requiresAllowFilteringIfNotSpecified()`. Not established from source. Probe: Byteman on `needFiltering` return while `CQLTester` runs `SELECT * FROM t WHERE ck1 = ?` on a two-clustering-column table, with and without an index. If no query makes `:992` return true, close as *Confirmed from source, not run*.
**If reachable.** Sweep: table of N rows, N = 1,000 / 100,000 / 1,000,000 (100 B rows). Arm R: the rejected query (needFiltering true, no ALLOW FILTERING). Arm F: the same query with ALLOW FILTERING. `Alloc` around prepare+execute. Prediction: arm R constant (tens of kB, parse cost) at every N; arm F grows about linearly with N (at least N x row size, bounded by fetch size). Executed proof: Byteman counter at `:992` true.
**Positive control.** `coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided`: a read-size guardrail that rejects a large read must show a flat rejected arm at the same N.
**Noise floor.** Two identical arm-R runs; arm R is flat by construction.
**Conclusions.** Refuted / caps (soft, rejects scans): arm R flat while arm F grows, caused by `:992`. Confirmed / does not cap: probe shows unreachable, or arms equal. Not confirmed: below noise. Invalid: `:992` never true. A Refuted outcome would be a false negative; keep the estimate unchanged (README rule).

## 4. no_constraint-hasunrestrictedclusteringcolumns-clustering_count

**Kind.** Counts of schema columns vs restricted columns (`StatementRestrictions.java:749-752`), both at most the table's few clustering columns: kind 1 by letter, kind 2 in substance (a validity flag). Call sites verified: `:695` (throws `invalidRequest("Some clustering keys are missing: ...")`, block `:692-698`) and `:1012` inside `hasAllPKColumnsRestrictedByEqualities` (`:1007-1014`).
**Why no run.** The guarded objects are a few small restriction objects and an exception. Sweeping 1 to 5 clustering columns changes per-statement allocation by hundreds of bytes, below the noise of CQL parsing (tens of kB) and far below heap noise (+-16 MiB). The operand is bounded by schema, not by data, so no sweep reaches MiB.
**Recommendation.** *Confirmed from source, not run.* B2/B3 stay `n/a`. The existing test home, `test/unit/org/apache/cassandra/cql3/restrictions/ClusteringColumnRestrictionsTest.java`, would report parse noise, not a branch effect.

## 5. no_constraint-isdone-remainingcount (`CBuilder.ArrayBackedBuilder.isDone`)

**Kind.** 1 confirmed: `remainingCount()` is `values.length - size` (`CBuilder.java:122-125`), `isDone()` is `remainingCount() == 0 || built` (`:145-148`, check `:147`), sole caller `add` (`:134`).
**Why no run.** The only memory, `values = new ByteBuffer[type.size()]` (`:114`), is allocated in the constructor before the check can run, so the branch cannot change it. True throws `IllegalStateException` (API-misuse guard); false stores a reference in an existing slot (`:136`). Per-call `add` allocation is 0 B false, one exception object true.
**Optional zero-cost record.** In the shared class: `CBuilder.create(new ClusteringComparator(types))` with 1, 4, 16, 64, 1,024 columns; constructor allocation is 16 + 4n B (compressed oops), independent of `add`. Confirms usage follows the schema, not the check.
**Recommendation.** *Confirmed from source, not run.*

## 6. no_constraint-hascomponent-componentbounds_size (`MultiColumnRestriction.SliceRestriction.hasComponent`)

**Kind.** 1 confirmed: `componentBounds.get(b).size() > index` (`MultiColumnRestriction.java:578-581`); callers `:453`, `:457`, `:475` in `appendBoundTo`. The lists are built before the check by `componentBounds(...)` (`:563-572` per the case file) and are at most the clause's column count.
**Why no run.** Tuple length is bounded by the table's clustering columns (a handful). The outcome adds one `ByteBuffer` reference to a short-lived `values` list or skips it (`:475-478`); the lists exist before the check. A sweep of tuple length 0..8 moves allocation by 8 references (32 B) per call, below the noise of the `EnumMap` and `ArrayList`s around it.
**Recommendation.** *Confirmed from source, not run.*

## 7. no_constraint-iscolumnrange-clustering_restrictions (`StatementRestrictions.isColumnRange`)

**Kind.** Not kind 1: the result is a boolean over restriction shape (`StatementRestrictions.java:962-976`: `clusteringColumnsRestrictions.size() < numberOfClusteringColumns || !hasOnlyEqualityRestrictions()`). Kind 2. The branch at `SelectStatement.java:826` picks the read filter (`ClusteringIndexSliceFilter`, `:826-832`, vs the names filter); what the read allocates may depend on the filter.
**Trigger.** `CQLTester`, table `t(pk int, ck1 int, ck2 int, v blob, primary key(pk,(ck1,ck2)))`, one partition of N rows, N = 1,000 / 10,000 / 100,000, v = 100 B. Two arms returning the SAME single row: names arm `WHERE pk=1 AND ck1=5 AND ck2=7` (all EQ, false branch); slice arm `WHERE pk=1 AND ck1=5 AND ck2>=7 AND ck2<=7` (true branch). Run on the memtable and again after `flush()`.
**Proof of execution.** Byteman counter on the `isColumnRange` return value (true only in the slice arm); result row count 1 in both.
**Measured.** `Alloc` bytes of the local read (Byteman ENTRY/EXIT of `ReadCommand.executeLocally`), median and range of 7 repeats per arm, per N, per memtable/sstable state.
**Prediction.** Memtable: arms within 20 percent of each other, independent of N. SSTable: names arm independent of N, slice arm at most 2x names and independent of N. N-dependence of the slice arm only would mean the branch gates an allocation.
**Positive control.** `SELECT *` over the whole partition at the same N: allocation grows about linearly with N.
**Noise floor.** Two identical runs per arm; a difference counts only above the larger run-to-run range.
**Conclusions.** Confirmed / does not cap: arms equal within noise and flat in N, control moved. Refuted / caps (path-dependent): arm difference above noise and N-dependent. Not confirmed: below noise. Invalid: results differ between arms, or the counter shows the wrong branch.

## 8. no_constraint-doesaggregation-aggregatefactories (`SelectorFactories.doesAggregation`)

**Kind.** Better kind 2: `numberOfAggregateFactories` (`SelectorFactories.java:62`, incremented `:106`) only matters as `> 0` (`:158-161`). But the branch gates result size: callers `Selection.java:575` and `:592` set `isAggregate()`, so an aggregating query returns one row while a plain one holds one row per input row in `ResultSet.rows` (`ResultSet.java:49`).
**Trigger.** `CQLTester` (home `validation/operations/AggregationTest` or `SelectGroupByTest`): one partition, N = 1,000 / 10,000 / 100,000 rows of int v; fetch size above N so the result is one `ResultSet`. Arms: P `SELECT v FROM t WHERE pk=1` (0 aggregate factories), A1 `SELECT max(v) ...` (1), A2 `SELECT max(v), min(v) ...` (2).
**Proof of execution.** Byteman counter on the `doesAggregation` return value per arm (false, true, true); result rows N vs 1.
**Measured.** `Alloc` of `ResultSetBuilder.build()` (Byteman ENTRY/EXIT) and retained size of the returned `ResultSet.rows` (`size()` x measured per-row bytes). No cluster tier: the sweep stays under heap noise.
**Prediction.** Arm P retained result about N x (80 to 150 B) = 0.1 / 1.4 / 14 MB; arms A1, A2: one row, flat in N (about 200 to 300 B). Total read allocation still grows with N in all arms (rows are scanned); only the retained result differs.
**Positive control.** Arm P with `LIMIT 100` at N=100,000: retained result drops to 100 rows (a known result bound, same instrument).
**Noise floor.** Two identical arm-P runs at N=100,000; relative difference under 5 percent.
**Conclusions.** Refuted / caps (by query shape, bypass; semantics of aggregation): retained result flat for A arms, linear for P. Confirmed / does not cap: retained and read allocation grow equally in all arms. Not confirmed: P and A arms differ below noise. Invalid: counter shows the same branch in P and A, or control did not move. If Refuted, record "gate by query shape, not a configured limit"; estimate stays `negative`.

## 9. no_constraint-hascomponent-i_nextsize (`ClusteringPrefix.Deserializer.hasComponent`)

**Kind.** 1 confirmed: `nextSize` (`ClusteringPrefix.java:597`, set in `prepare` `:609-627`: `nextSize = nextIsRow ? comparator.size() : in.readUnsignedShort()`) is a component count; `i` is the loop index (`:633`). Check `:653`, loop `:656-657`. **Citation correction:** `nextValues = new byte[nextSize][]` is at `:626`, not `:620`. Components are read by `deserializeOne` (`:662-678`) with `readArray(in, DatabaseDescriptor.getMaxValueSize())` (`:677`).
**What the branch gates.** The false return (`i >= nextSize`) stops deserialization at the stored component count; the true path allocates each component `byte[]` up to index `i`. Allocation therefore tracks `min(bound.size(), nextSize)` components, bounded by the data's own `nextSize`.
**Trigger.** No existing test drives the Deserializer (nothing under `test/unit` calls it; `ClusteringPrefixTest` is not a home). A new JUnit class in `org.apache.cassandra.db`: `Deserializer` is public static (`:588`, constructor `:603`); serialize one `ClusteringBound` of `nextSize` components into a `DataOutputBuffer`, build `Deserializer(comparator, in, header)`, call `prepare(flags, extendedFlags)` (`:609`), then `compareNextTo(bound)` (`:632`) with a probe bound of size S. Components 1 KiB each (`byte[1024]` = 1,040 B).
**Sweep (nextSize, S).** (2,1), (2,2), (2,4), (4,2), (4,4), (4,8), (8,8), (8,16): S below, equal and above nextSize. Probe components equal the stored ones so the compare does not return early on a mismatch.
**Proof of execution.** Byteman counts of `deserializeOne` entries and of the `false` return at `:653`; the S > nextSize rows must show exactly one false return per call.
**Measured.** `Alloc` bytes around `compareNextTo` (5 repeats, median and range); `deserializedSize` by reflection.
**Prediction.** About `min(S, nextSize) x 1,040 B`: 1.0 KB (2,1), 2.1 KB (2,2), 2.1 KB (2,4), 2.1 KB (4,2), 4.2 KB (4,4), 4.2 KB (4,8), 8.3 KB (8,8), 8.3 KB (8,16); tolerance +-10 percent. (`byte[nextSize][]` is allocated in `prepare`, outside the window.) Same bytes for S above nextSize: the branch stops work at the stored count.
**Positive control.** Component size 1 KiB vs 64 KiB at (4,4): allocation moves 64x. Real knob: `max_value_size` below the component size makes `readArray` (`:677`) throw instead of allocating; run in the same class.
**Noise floor.** Two identical (4,4) calls; difference under 1 percent of the reading.
**Conclusions.** Confirmed / does not cap anything beyond the data (allocation follows stored `nextSize`, equal on both sides for equal components, control moved). Refuted / caps: allocation at S > nextSize differs from the closed form by more than tolerance because of `:653`. Not confirmed: below noise. Invalid: false return never observed. The operand is the data itself, so "usage follows the operand" is expected and not a positive finding (none-type-design.md §6).

## 10. none-addall-size (`RangeTombstoneList.addAll`, `size > 10 * tombstones.size`)

**Kind.** 1 confirmed: `size` (field `RangeTombstoneList.java:66`) and `tombstones.size` are element counts; check `:213`; the literal 10 is hard-coded. The case already has a B2/B3 design; this amendment adds per-call allocation, branch proof and a noise floor.
**Trigger.** Production caller `MutableDeletionInfo.add(DeletionInfo)` (`MutableDeletionInfo.java:131`, `ranges.addAll(newRanges)` at `:142`). Unit: a copy of `RangeTombstoneListTest` (`test/unit/org/apache/cassandra/db/RangeTombstoneListTest.java`; it has `cmp`, `DatabaseDescriptor.daemonInitialization()` in `@BeforeClass`, helper `rt(start,end,tstamp)` at `:719`). Public constructor `RangeTombstoneList(cmp, capacity)` (`:86`). `MutableDeletionInfo` is an optional outer driver.
**Proof the check ran and which branch.** Byteman counting calls to `add(...)` made from inside `addAll` (add branch: m calls) and `insertFrom` calls (merge branch), per run.
**Sweep (frozen).** n = 10,000 in A; m in {500, 999, 1,000, 1,001, 2,000, 10,000}. `10,000 > 10*m`: 5,000 true; 9,990 true; 10,000 false; 10,010 false; false; false. Both sides, 999 and 1,000 adjacent to the literal. Ranges disjoint with gaps (A `[4i,4i+1]`, B interleaved `[4k+2,4k+3]`), same markedAt, so the result has n+m entries and identical content (`equals`, `:490`) in both branches.
**Measured.** (1) `Alloc` of the `addAll` call, median and range of 7 repeats on a freshly built A (A built outside the window). (2) `unsharedHeapSize()` (`:770-778`) and reflective capacity (`capacity()`, `:658`) after the call. (3) Class-histogram bytes of the four arrays as an independent reading. Two capacity arms: A pre-sized to n+m (no growth; isolates the branch) and A at capacity n (growth through `growToFree`, `:680-686`, in both branches).
**Prediction.** Pre-sized arm: `Alloc` under 1 KiB at every m, no step at m=1,000. Capacity-n arm: `Alloc` about 4 arrays at the new capacity: growth 1.5 gives 15,000 x about 24 B = about 360 kB (compressed oops: 4+4+8+4 B), the same in both branches (+-10 percent); `unsharedHeapSize()` equal for equal content within capacity slack, `boundaryHeapSize` equal (this settles the open point in A3 about `:178` vs `insertFrom`). No step at the ratio 10.
**Positive control.** `DatabaseDescriptor.setRangeTombstoneListGrowthFactor(3.0)` vs 1.5 (`DatabaseDescriptor.java:4654`): capacity-n arm `Alloc` and `unsharedHeapSize()` must rise (new capacity 30,000 vs 15,000, about 2x). Closed-case equivalent for heap: `memtable_heap_space`.
**Noise floor.** Two identical calls on identical A and B; floor = difference of medians; a branch difference below it is "not resolved".
**Cluster tier.** Optional and weak: 100,000 tombstones are tens of MB, comparable to heap noise (+-16 MiB). Keep B3 as filed or declare it `n/a: below heap noise`; the unit tier decides.
**Conclusions.** Confirmed / does not cap: per-call and retained size equal across branches within slack, no step at m=1,000, control moved, both branches observed. Refuted / caps: branch difference above noise, explained by what each branch allocates (a `boundaryHeapSize` mismatch or extra arrays). Not confirmed: below floor, or control did not move. Invalid: only one branch observed, or result `size()` differs from n+m.

---

## Shared harness

One JUnit class, `NoneKind1AllocTest` (package `org.apache.cassandra.db`, files under `harness/none-kind1--autonomous/`, copied into `test/unit/` like `BatchSizeAllocTest.java`), serves cases 1, 5, 9, 10 directly and, as a `CQLTester` subclass, cases 3, 7, 8:
- a static `alloc(Runnable)` helper: 3 warm-up calls, then 7 timed calls, each `getThreadAllocatedBytes(Thread.currentThread().getId())` before and after; returns median and range. `stage4.Alloc` (`Alloc.java`) is reused where the window cannot sit inside the test (`build()`, `compareNextTo` inside a query);
- a known-answer check (8 MiB `byte[]` reads 8 MiB to 8 MiB + 64 KiB), as in `BatchSizeAllocTest`;
- a noise mode that runs every measured call twice for the noise-floor step, and CSV output (case, arm, value, repeat, bytes) for one analysis script;
- one Byteman file with branch counters: `ResultSet.isEmpty` exit, `StatementRestrictions.needFiltering` exit, `isColumnRange` exit, `SelectorFactories.doesAggregation` exit, `RangeTombstoneList.addAll` (add/insertFrom calls), `ClusteringPrefix$Deserializer.deserializeOne` entry.
Two JVM modes, plain (instrument) and Byteman (branch proof), as in `transform-stack-capacity-splice-newCount--autonomous`.

## Cases I would drop from kind 1

- **no_constraint-isempty-size-2**: not kind 1 in effect (pager `size()` throws; no count is read there); close from source.
- **no_constraint-hasunrestrictedclusteringcolumns-clustering_count**, **no_constraint-isdone-remainingcount**, **no_constraint-hascomponent-componentbounds_size**: schema-limited counts of a few items, nothing allocated either way; *Confirmed from source, not run*.
- **no_constraint-needfiltering-restriction_count**, **no_constraint-iscolumnrange-clustering_restrictions**, **no_constraint-doesaggregation-aggregatefactories**: move to kind 2 (flag over query shape). Runnable only because the outcome selects a different read or result path; needfiltering and doesaggregation could in principle yield `caps`, that is a false-negative.
