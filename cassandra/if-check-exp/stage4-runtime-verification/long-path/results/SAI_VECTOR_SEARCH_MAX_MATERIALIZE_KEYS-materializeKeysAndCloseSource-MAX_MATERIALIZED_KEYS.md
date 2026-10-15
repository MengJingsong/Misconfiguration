# SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS — stage-4 results

> **Case:** [`SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS`](../../../stage3-ai-deep-read/long-path/cases/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS.md)
>
> **Status:** **Closed 2026-10-15 — unit Confirmed; cluster Confirmed (§9a row 1), escape values and disallow retention as recorded; two sub-predictions missed; no run 2.** The limit caps the per-query key list at exactly *L* + 1 and the held keys follow *L* (8,040 → 512,040 for 8 queries); past it the ANN plan read 30,656 rows and held 245,256 keys on far-matching data, and at *L* = 0 a five-match query read 115,401 rows and timed out.
>
> **Path:** long. Unit tier and cluster tier.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Last commit of the case file before the audit: `3010ab8`; the audit's amendments are not committed yet (commit on request). **§9a's hash: `1088e8cdb8cb346c1e12cd9800e031186df2483b`** (`sed -n '/^### 9a\. /,/^### 9b\. /p' <case file> \| git hash-object --stdin`); §9's hash `04578de759fc2d9cb3ca6b218fce7ec2da924eec`; both recorded 2026-10-15 03:06 EDT after the amendments and **before any harness code or reading existed**. |
| **Harness** | written after the freeze under `../harness/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS/` (uncommitted); listed in its `README.md` |
| **Tiers and values** | **Unit:** upstream `VectorTypeTest#testTooManyMaterializedKeys` (control); `MaterializedKeysLimitTest` U1–U5. **Cluster** (`pc57`, one node, client on the same host): *L* = 1,000 · 4,000 · 16,000 (default, no `-D`) · 64,000; C1 *L* = 0 and 2,147,483,647; scenarios control, A, B, C1, C2 (9e). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-15. One defect would have produced a wrong reading (C2's partition-read counter is never recorded for top-k queries, rec. 1); one design risk had no conclusions row (C2's antipodal clusters, rec. 2); three are wording or wiring (rec. 3–5). Everything else in §5–§8 and 9a's numbers re-derived and held. |

### 1.1 Design audit

Checked against the pinned clone `cassandra-5.0.9` (`/proj/misconfiguration-PG0/git-repos/cassandra-src`, `git describe --tags` = `cassandra-5.0.9`). **Re-read in context:** `QueryController.java` 90-100, 360-457; `Operation.java` 320-345; `StorageAttachedIndexSearcher.java` 120-155, 500-530, 613-833; `RangeCommands.java` 60-100; `ScanAllRangesCommandIterator.java` 40-140; `VectorTopKProcessor.java` 160-190; `VectorIndexSegmentSearcher.java` 100-215, 270-345; `DiskAnn.java` 95-135; `SegmentRowIdOrdinalPairs.java` 35-50; `PrimaryKey.java` 95-160, 169-372 (class names); `SkinnyPrimaryKeyMap.java` 140-215; `PostingListRangeIterator.java` 95-125; `TableQueryMetrics.java` 40-160; `QueryContext.java` 39-95; `StorageAttachedIndexQueryPlan.java` 125-145; `StorageAttachedIndex.java` 295-305; `CassandraRelevantProperties.java:476`; upstream `VectorTypeTest.java:697-722`.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | heap: `PrimaryKey` objects retained in one list per query (§4, §7) |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 1,000 · 4,000 · 16,000 (default) · 64,000 by restart; 0 and 2^31 − 1 (9b) |
| A. Core question | real resource measured, not only the counter (gap named) | Met | live `SkinnyPrimaryKey` / `BufferDecoratedKey` from class histograms during holds; bytes per key from U2's `measureDeep` (9d) |
| A. Core question | usage driven to the limit and past it | Met | *M* = *L*, *L* + 1, 4*L* per value (B at 64,000 uses *M* = *N* = 200,000 > *L*) |
| B. Logic | each step says what it establishes | Met | "How this verifies" logic (1)–(6) |
| B. Logic | prediction stated in numbers or a clear relation | Met | exact list sizes, *Q*·(*L* + 1) held counts with tolerance, *b* band, C2 bounds |
| B. Logic | every plausible outcome has a conclusions row with its evidence | **Partly** | no row for a C2 query that ends with fewer than *k* rows (possible with the filed antipodal data, rec. 2): row added |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | `mat refuse` + `ann` + trace event; held counts across *L* |
| B. Logic | alternative explanations and their controls | Met | ANN-only control; idle histogram; memtables flushed (memtable keys are references); one command per query checked by one `mat` line |
| C. Specific | a human can follow it from the intro and §9a | Met | |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | the rules' methods and fields are named; locals visible (`build.xml:33` `debuglevel="source,lines,vars"`) |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | **Partly** | C2's observable `TotalPartitionReads` never moves for top-k (rec. 1); `ann` also fires on the ANN-only control (rec. 3); hold point (c) named as `AT INVOKE <init>` (rec. 5) |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | listed in 9c, none exists (step 1). `pc57`: JDK 11, Ant, `~/cassandra-run1` at `cassandra-5.0.9` built with test classes, Byteman 4.0.20 and jamm 0.4.0 in `build/lib/jars`, 32 cores, 251 GiB, 50 GB free on `/`; bundled driver 3.29.0 has `VectorType` (`cqltypes.py:1408`) |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | *N* = 200,000 ≥ 4*L* up to *L* = 16,000 and > 64,000; C1's held 8 × 200,000 keys ≈ 0.24 GB of a 4 GB heap plus ≈ 8 × 4 × 2.4 MB per-segment arrays after the hold; data ≈ 0.1 GB on disk; timeouts 120/120/180 s against 15 s holds |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `CassandraRelevantProperties.java:476`, `QueryController.java:96`, `:390-398`, `:428-457` (check `:449`) as quoted in §1; `Operation.java:331-340`; `RangeCommands.java:81-82` (top-k → `ScanAllRangesCommandIterator`, one message per replica for the whole key range); `PostingListRangeIterator.java:114` → `SkinnyPrimaryKeyMap.java:148-151`, `:205-208` → `PrimaryKey.java:151-155`, `:102-108` (a new `byte[]`, `HeapByteBuffer`, `LongToken`, `BufferDecoratedKey`, `SkinnyPrimaryKey` per key); `VectorIndexSegmentSearcher.java:288-299`; `StorageAttachedIndexSearcher.java:773`, `:782`, `:802`, `:816`; `QueryContext.java:85-92`; `StorageAttachedIndexQueryPlan.java:134-141`; `StorageAttachedIndex.java:302-303` |

**Findings the audit rests on, all from the source.**

1. **`TotalPartitionReads` is not recorded for top-k queries.** `TableQueryMetrics.record(queryContext)` → `PerQueryMetrics.record()` increments it (`TableQueryMetrics.java:59-64`, `:146-147`), but the only caller is the plain `ResultRetriever.close()` (`StorageAttachedIndexSearcher.java:520-524`); `ScoreOrderedResultRetriever.close()` (`:828-831`) only closes its iterator. C2's prediction would have read 0 reads on every query. The same quantity is `queryContext.partitionsRead` (`:773`), read at the retriever's close through the outer instance.
2. **The filed far-matches data risks a search that never reaches the matches.** With matches at −*q* + ε and the rest at *q* + ε (|ε| ≤ 0.01), the vectors form two tight antipodal clusters of near-duplicates under cosine similarity. The ANN plan's search resumes "until the graph is exhausted" (`DiskAnn.java:117-120`), but only over what it can reach from its entry point; nothing in the graph build guarantees edges between the clusters. A C2 query could then return fewer than 10 rows, an outcome with no conclusions row. Ranking draws from one distribution by similarity keeps the graph ordinary and still makes the matches exactly the *M* farthest rows.
3. **The `ann` rule marks both the hybrid disallow branch and the ANN-only query** (`Operation.java:333-335` → `QueryController.getTopKRows(QueryExpressionView)`), so the control's expectation is one `ann` line and no `mat` line, and "iff" holds for hybrid queries.
4. **No SAI unit test uses `BMUnitRunner`** (`grep -rl BMUnitRunner test/unit/org/apache/cassandra/index/sai` is empty); the rules are loaded with `-javaagent` as in the `native_transport_receive_queue_capacity` harness. Not a change to what is observed.
5. **`takeTopKThenSortByPrimaryKey()` has one caller** (`StorageAttachedIndexSearcher.java:148`); `AT NEW InMemoryUnfilteredPartitionIterator` there is reached only with the retriever open (`try (partitions)`, `VectorTopKProcessor.java:170-185`).

Checked and held, recorded because a run depends on them: the hybrid check runs **once per query per replica** (`ScanAllRangesCommandIterator.sendNextRequests()` sends one message with the command's whole key range; the full-ring `mergeRange` has a minimum right bound, so `hasLimitingMaxToken` is false and no key is skipped); `SegmentRowIdOrdinalPairs` is also built at `VectorIndexSegmentSearcher.java:164`, but only for a key range that does not cover the ring (`:133-134` returns first), so the ANN plan on these full-ring queries prints no `pairs` line; the allow plan's `keysInRange` needs the list in key order, which the key-ordered iterator gives; `SkinnyPrimaryKey`'s histogram name is `org.apache.cassandra.index.sai.utils.PrimaryKey$Factory$SkinnyPrimaryKey` (an inner class of `Factory`, so each key also references the factory: a shared object, constant in U2's `measureDeep`, cancelled by the slope).

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | C2 partition reads from `reads=` (`queryContext.partitionsRead` at the retriever's close, rule (7)); `TotalPartitionReads` kept as a side reading, expected unchanged | **applied** 2026-10-15 to §9 (amendment note), 9a C2 bullet, 9c rule (7), 9d, 9e step 5 (uncommitted) | finding 1 |
| 2 | `ks.far` and U5's table by rank of cosine similarity; conclusions row for a C2 query with fewer than *k* rows | **applied** 2026-10-15 to 9b, 9e U5, 9a conclusions | finding 2 |
| 3 | "iff" scoped to hybrid queries; the control expects one `ann` line | **applied** 2026-10-15 to 9a | finding 3 |
| 4 | Unit rules by `-javaagent` | **applied** 2026-10-15 to 9c | finding 4 |
| 5 | Hold point (c) `AT NEW InMemoryUnfilteredPartitionIterator` | **applied** 2026-10-15 to 9c | finding 5 |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-15, unit 03:13–03:16 EDT, cluster 03:28–03:43 EDT | not done |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347…`), 32 cores, 251 GiB; shared with another session's node, run in turns (that session's node was down throughout this run) | |
| OS and kernel (`uname -r`) | Ubuntu, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `b5f2a54` (`cassandra-5.0.9`), both `~/cassandra-run1` (run) and the citation clone | |
| Case-file commit / harness commit | case `3010ab8` + uncommitted amendments (§9a `1088e8cd…`); harness uncommitted (md5s in each `summary.txt`) | |
| Storage for node data | `~/stage4-mmk/{data,commitlog,…}` on `/dev/sda3` (local disk), own `CASSANDRA_CONF` | |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/mmk/run1/` (`unit/`, `load/`, one folder per value; raw histograms and `system.end.log` there); shakedowns `shakedown1`–`3` | |

## 3. Runbook defects

None in run 1. Shakedowns (not readings) found and fixed before run 1: unit shakedown 1, a second Byteman agent from
`SAITester` and the parameterized upstream test (9c note dated 2026-10-15, §9a unchanged); cluster shakedown 3, the SSTable count
also matched SAI `…TermsData.db` files, and the `TotalPartitionReads` side reading was cut from the session log (narrower JMX
pattern). The self-check's own read-back parser matched the run script's note line once; fixed in `selfcheck.py` before its
recorded run.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|

## 4. Run 1

**Scope:** unit tier (upstream `VectorTypeTest`, harness U1–U5); cluster tier at *L* = 1,000 · 4,000 · 16,000 (default) · 64,000
(control, A, B, and C2 at 1,000 · 16,000 · 64,000), C1 at 0 and 2,147,483,647, one load. **Command log:**
`SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS/run1/` (`chain.log`, per value `session.log`, `summary.txt`, `mat.trace`, `histo.csv`, histogram excerpts; unit `summary.txt`, `harness.out`); `selfcheck.py`, `selfcheck.out`.

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `VectorTypeTest` (whole class; `testTooManyMaterializedKeys[forceBruteForceQueries=true/false/null]`) | 84/84 pass, the three cases pass | `run1/unit/summary.txt` |
| U1 boundary, *L* = 10 · 100 · 1,000 × *M* = *L* − 1, *L*, *L* + 1, 4*L*, SSTable; and memtable at *L* = 100 | every *M* ≤ *L*: list = `hybrid size` = *M*, no `ann`; every *M* > *L*: `refuse size=count=L+1`, `returned=null`, one `ann`, no `hybrid`; 3 rows, `i` ≤ *M* | `run1/unit/harness.out` |
| U2 heap per key (`measureDeep` of the list at the refusal, 101 · 1,001 · 4,001 keys) | 16,048 · 157,344 · 625,064 B; slopes *b* = 157.00 · 155.91 · 156.16 B/key, max/min 1.0070 | `harness.out` (`STAGE4 deep`) |
| U3 escape values | *L* = 0, *M* = 5: `refuse size=1 count=1`; *L* = 2^31 − 1, *M* = 16,000: `returned=16000`, no refusal | `harness.out` |
| U4 per-segment arrays, *S* = 4, *L* = *M* = 4,000 | `pairs cap` = 3,995 · 3,999 · 3,998 · 3,996 | `harness.out` |
| U5 far matches (*N* = 2,000, `i` ≤ 101 least similar) | *L* = 100: refusal, `processed=1888`; *L* = 1,000: list plan, `processed=3`; 3 rows `i` ≤ 101 both | `harness.out` |
| All harness checks | 83/83 | `run1/unit/summary.txt` |

**Cluster tier** (load: `ks.t` 200,000 rows in 4 SSTables, `ks.far` 50,000 in 1, counts by `count(*)`; `run1/load/summary.txt`). Idle baseline at every value: 20 live `SkinnyPrimaryKey`. Every query returned 10 rows with `i` ≤ *M* except the one at *L* = 0 (below).

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| all | read-back | `-D`, `VM.system_properties`, `limit=` | 1,000 · 4,000 · none (default) · 64,000 · 0 · 2,147,483,647; one `limit=<L>` line each | `<v>/jvm-args.txt`, `session.log`, `mat.trace` |
| all | control | ANN-only query | 10 rows, no `mat` line, one `ann` line | `<v>/summary.txt` |
| 1,000 · 4,000 · 16,000 · 64,000 | A single, *M* = *L* | list | `returned` = `hybrid size` = *L*; no refusal; `pairs cap` 1,000×4 · 4,000×4 · 16,000/15,999×3 · 63,999/63,999/63,996/63,997 | `<v>/mat.trace` |
| same | A held, *Q* = 8 at point b | live `SkinnyPrimaryKey` / `BufferDecoratedKey` change | +8,000 / +8,000 · +32,000 / +32,000 · +128,000 / +128,000 · +512,000 / +512,000 (= 8*L* exactly); five-class bytes 150.0 · 151.6 · 151.9 · 152.0 B/key | `<v>/histo-*.excerpt.txt`, `selfcheck.out` |
| same | B traced, *M* = *L* + 1 | list, plan, trace | `refuse size=count=L+1`, `returned=null`, one `ann`; trace event "WHERE clause generated more than *L* rows. Switching to ORDER BY then post filter." at every *L* | `<v>/mat.trace`, `trace-events-B_traced.txt` |
| same | B held at point a, *M* = 4,000 · 16,000 · 64,000 · 200,000 | live `SkinnyPrimaryKey` / `BufferDecoratedKey` change | +8,040 / +8,042 · +32,040 / +32,042 · +128,040 / +128,042 · +512,040 / +512,042 (8(*L* + 1) + 32); ratio 1 : 3.985 : 15.925 : 63.687; five-class bytes 632.5 · 234.4 · 169.3 · 156.2 B/key | same |
| 1,000 · 16,000 | C2 single on `ks.far`, *M* = 16,001 | list, `reads=`, `processed=` | refusal at 1,001 / 16,001; `reads` = `processed` = 30,656 at both; 37 s / 42 s | `<v>/mat.trace`, `summary.txt` |
| 1,000 · 16,000 | C2 held at point c | live `SkinnyPrimaryKey` change | +245,256 at both | `selfcheck.out` |
| 64,000 | C2 single | list | `returned` = `hybrid size` = 16,001, `reads` = 10, 0.05 s | `64000/mat.trace` |
| 64,000 | C2 held at point c | live `SkinnyPrimaryKey` change | +88 (no prediction) | `selfcheck.out` |
| all | `TotalPartitionReads` side reading | | unchanged by top-k queries, as rec. 1 found in the source (`64000`/`default` session logs) | `<v>/session.log` |
| 0 | C1, *M* = 5 | list, plan, result | `refuse size=1 count=1`, one `ann`; then `processed=115400 reads=115401` and the client's **`ReadTimeout`** after 120.0 s: no rows | `0/summary.txt`, `0/mat.trace` |
| 2,147,483,647 | C1, *M* = 200,000 | list; held at point b | `returned` = `hybrid size` = 200,000, `pairs cap` 199,993–199,997; held +1,600,000 / +1,600,000; 152.0 B/key | `2147483647/` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The knob read back at every value [observed: `jvm-args.txt`, `session.log`, `mat.trace` `limit=`]; the
   check was reached once per hybrid query (one `mat exit` line per query, 8 per held reading) [observed: `selfcheck.out`]; 9b's
   hold-fixed settings were in force (timeouts 120/120/180 s, one data directory, compaction disabled with 4 + 1 SSTables
   unchanged, 4 G G1, flushed data) [observed: `cassandra.yaml` diff in `summary.txt`, `jvm-args.txt`, `load/summary.txt`]; every
   held histogram was taken with all 8 queries inside the hold (last start < `jcmd` end < first end) [observed: `selfcheck.out`].
2. **Readings** — (i) B held carries 32 keys above 8(*L* + 1) at every *L* (4 per query, constant): within tolerance [observed];
   (ii) the B-held byte figure at *L* = 1,000 and 4,000 is far above *b*: the extra is `system_traces` rows (`ExpiringLivenessInfo`
   5,818 and 1,765 live against 5,806 and 1,750 trace events of the preceding traced query, with their `BufferCell`, `[B`,
   `HeapByteBuffer`), written after the idle histogram [observed counts; cause inferred from the match]; (iii) at *L* = 0 the
   query timed out (below); (iv) at hold point c on the list plan only 88 keys are live.
3. **Matched row** — "Lists stop at *L* + 1 with a refusal, reach *M* below it, the plan switch and trace appear exactly at
   refusals, held keys move 1 : 4 : 16 : 64 and match *Q* × list size" → **Confirmed**: lists stop at exactly *L* + 1 and reach *M*
   at *M* = *L* (unit and cluster); `ann` and the trace event appear at every refusal and never with a list; held keys equal *Q* ×
   list size within 1 % + 100 at every value (A exactly). Also **"C1: … *L* = 2^31 − 1 never refuses and holds *M*"** (1,600,000
   keys) and *L* = 0 refuses at 1 key → **Escape values as recorded**; and **"C2: the ANN plan reads and holds about *N* − *M*
   keys at *L* < *M*, more than the list would"** (30,656 reads, 245,256 held vs 128,008) → **Disallow retention as recorded**.
4. **Excluded rows** — "list holds more than *L* + 1 / refusal at another count": every refusal at exactly *L* + 1. "Held
   count does not move with *L*": 8,040 → 512,040. "Histogram does not match *Q* × list size": matches to ≤ 0.4 % + 32. "Refusal
   without `ann` or `ann` without refusal" (hybrid): none. "C2 reads ≤ 20 at *L* < *M*": 30,656. "C2 returns fewer than 10 rows
   (no error)": 10 rows. "`pairs` near *M*/*S*": caps ≥ *M* − 7. "A row with `i` > *M*": none. "Invalid run": read-backs held,
   one `mat` line per query.
5. **Observed vs. inferred** — the conclusion rests on observed counts only. Inferred: the cause of the B-held byte excess (trace
   rows; does not bear on the key counts, which decide); that the list plan releases the list before hold point c (88 keys:
   `getTopKRows(List, …)` keeps only per-segment `int` pairs and memtable results, `VectorIndexSegmentSearcher.java:288-336`).
6. **Deviations and gaps** — two frozen sub-predictions missed: (a) "Bytes: the change in the five classes … is the count ×
   *b* within 10 %" fails for B held at *L* = 1,000 and 4,000 (holds for every A held, for B held at 16,000 and 64,000, and for
   C1), by the trace rows of reading (ii); (b) "Every query returns 10 rows" fails at *L* = 0, *M* = 5: the query hit the
   120 s quota after reading 115,401 partitions and returned an error. The latter has **no §9a row** (it is neither a wrong row nor
   a short result without error): fed back to stage 3 (§8 escape values, §10). Not run: none.
7. **Core question** — the knob caps the list: at every value the list stopped at exactly *L* + 1 keys and the held keys moved 8,040
   : 32,040 : 128,040 : 512,040 with *L* (parts 1, 3), each key a new ~152 B heap object (U2, A held). It does not cap the query:
   past the limit the ANN plan read 30,656 rows and held 245,256 rejected keys on the far table at *L* = 1,000 and 16,000, more than
   the list plan's 128,008, and at *L* = 0 a five-match query read 115,401 rows and timed out (parts 3, 6).

**Conclusion (one line):** Lists capped at *L* + 1, plan switch and held keys follow *L* — **confirmed**; escape values and the disallow
plan's retention **as recorded**, with the *L* = 0 timeout beyond §9a (no row; fed back).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-parses `mat.trace`, the client JSON in `session.log` (per call, the trace lines from its first query's start
to the next call's), the raw `jcmd` histograms (with their mtimes against the hold lines), the trace-event files, `jvm-args.txt` and
the raw `VM.system_properties` lines, and the unit `harness.out`. Result: **153 checks, 150 ok, 3 failed** = exactly the two B-held
byte readings (6a) and the *L* = 0 row count (6b) (`run1/selfcheck.out`).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | read-backs and `limit=` lines per value; one `mat exit` per query; histogram timing vs hold lines (`selfcheck.out`) |
| 2. Readings | yes | `ExpiringLivenessInfo` counts re-read from the raw histograms (5,818 / 1,765 vs 5,806 / 1,750 trace events); +32 per B held from the same files |
| 3. Matched row | yes | every A/B/C1/C2 relation recomputed from raw lines: 150 checks |
| 4. Excluded rows | yes | each refuted row's reading re-read in `mat.trace` and the histogram excerpts |
| 5. Observed vs. inferred | yes | the two inferred statements are not load-bearing for the matched rows |
| 6. Deviations and gaps | yes | the 3 failures are exactly the two recorded misses |
| 7. Core question | yes | cap: refusal sizes and held counts; not a query bound: C2 and *L* = 0 |

### 5.2 Run 2?

**No** (2026-10-15). Every load-bearing reading is an exact observed count (list sizes, refusal counts, live instances) re-derived
by an independent parser; nothing rests on an inferred statement; the result refutes no row and the bypass-like outcomes are
the recorded Target-3 rows of §9a (escape values, disallow retention), observed directly.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** (U1–U5 and the upstream control; *b* = 156 B/key) | run 1 + self-check | 2026-10-15 |
| Cluster | **Confirmed** (row 1), **Escape values as recorded**, **Disallow retention as recorded**; two sub-predictions missed (B-held bytes at 1,000 / 4,000; the *L* = 0 query timed out instead of returning rows, no §9a row) | run 1 + self-check | 2026-10-15 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" updated (uncommitted); §9 amendments listed in §1 (uncommitted).
