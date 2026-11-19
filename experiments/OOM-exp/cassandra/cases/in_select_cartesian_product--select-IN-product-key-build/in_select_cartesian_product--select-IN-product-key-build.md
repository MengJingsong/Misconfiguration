# U5 — in_select_cartesian_product: one SELECT with IN × IN builds the whole cartesian product of keys on the coordinator heap  <!-- file: cassandra/cases/in_select_cartesian_product--select-IN-product-key-build/in_select_cartesian_product--select-IN-product-key-build.md -->

| Field | Value |
|---|---|
| Case ID | `U5` (U = unprotected accumulation / unprotected configuration; README "ID prefixes") |
| From | cluster of phase-1 candidates `OC-412` (primary), `OC-351`, `OC-352`, `OC-365`, `OC-276` (phase 1 OOM candidate list) |
| Phase-1 case file | [`no_constraint-handleinfilter-restriction_position--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-handleinfilter-restriction_position--autonomous.md) (OC-412), [`none-queryprocessor-validatekey-key_remaining--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/none-queryprocessor-validatekey-key_remaining--autonomous.md) (OC-351, OC-365), [`none-validatekey-key_remaining--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/none-validatekey-key_remaining--autonomous.md) (OC-352), [`batch_size_warn_threshold-verifyBatchSize-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/batch_size_warn_threshold-verifyBatchSize-size--autonomous.md) (OC-276) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built tree `ms0617:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`, sha256 `e55f4f29…5a942`), OpenJDK 11.0.33 **aarch64**, Ubuntu 22.04.1, kernel 5.15.0-191 |
| Stage 1 (design) | phase-2 OOM agent, stage-1 session (workflow, wave 4), 2026-11-18 13:40–14:15 America/New_York; nothing run (node checked read-only) |
| Stage 2 (verify) | phase-2 OOM agent, stage-2 session (fresh, not the designer), 2026-11-18 13:55–16:08 America/New_York (suspended with the wave; every lifetime had ended); resumed in a fresh session 18:20–18:50 the same day (§3 "Resumed session"): no new lifetimes, P4 write-up, re-reading of existing logs and dumps |
| Verdict | `retry` (CK decides; §4) |

## Summary

- **Conclusion (stage 2, 2026-11-18; corrected after the resumed session's re-reading): retry.** The CK condition
  decides the case. One ≈ 8 MB `SELECT … pk = ? AND c1 IN (64) AND c2 IN (1,000,000)` fills a 2 GiB heap at shipped
  defaults every time (5/5) and puts the node into a G1 full-GC spiral. A `Java heap space` error was thrown inside the
  240 s window in **4 of 5** runs, but only **2 of 5** meet the frozen rule (the request thread throwing in the build
  frames: `T-CK-2G-3` at +22 s, `T-CK-2G-4` at ≈ +103 s). In `T-CK-2G-5` a background metrics task threw (+178 s);
  in `T-CK-2G-1` the thread is unknown (the dump never started); `T-CK-2G-2` threw nothing. Only `T-CK-2G-3` died in the
  window; in the other three the post-OOM dump and `kill -9` were held up by the spiral. Service loss (≥ 90 % STW
  ≥ 60 s) 4/5. At **8 GiB** (160 × 1.6M = 256M) the heap OOM is regular: **3/3** (`CAL-CK-8G`, `REP-8192M-1,2`, all
  at +158–160 s after two failed humongous-allocation full GCs), but without a dump, matched control or intervention
  at that budget. 4 GiB, 15.5 GiB and 31 GiB (auto) spiralled without an OOM in their windows.
- **Condition PK met the true-positive bar on its own:** `a IN (16) AND b IN (500,000)` on a composite partition key
  (≈ 4 MB) gave a Java heap OOM **3/3** at 2 GiB (plus 1/1 in calibration), in `SinglePartitionReadCommand.create` ←
  `SelectStatement.getSliceCommands`. The dump holds 8.0M keys and 5.95M read commands. The matched control did not
  OOM (0/3) and the pre-allocation check stopped it (3/3). That is `verified-OOM · deployment` for that condition, which
  covers OC-351 and the product form of OC-365. The frozen rules make CK decide the case verdict.
- **Shipped guardrail switched on (arm G, diagnostic):** enforcement is late. A 16M product is rejected only after it
  was built (1.27 GiB heap); a 64M product OOMs before the check (2/2).
- **Root cause (hypothesis, stage 1; confirmed for the holder in both conditions):** IN restrictions on two key columns are expanded by `MultiCBuilder` into their
  full cartesian product on the request thread (one `ArrayList` per combination, then one `Clustering` per
  combination in a `BTreeSet`; for a partition key also one serialized key, one cloned key, one `DecoratedKey` and one
  `SinglePartitionReadCommand` per combination), all before any limit runs. The only control on that count,
  `in_select_cartesian_product`, ships disabled (−1) and is skipped for superusers (every client under the shipped
  `AllowAllAuthenticator`); when enabled it checks `buildSize()` only after each column's product has been allocated.
  The native byte limits charge the request bytes (≤ 16 MiB), not the product. So one ≈ 8 MB request
  (`c1 IN (64 values) AND c2 IN (1,000,000 values)`) asks for 64M combinations, ≈ 3.5–7 GB of heap, and a 2 GiB heap
  should die of `Java heap space` on that one request.

## 1. Candidate

**Cluster rows (quoted from `phase1-oom-candidates.md`; Status cells as they stand at stage 1).**

> | OC-412 | 2026-11-18 | `no_constraint-handleinfilter-restriction_position--autonomous` | guided | Holder: MultiCBuilder.elementsList, the cartesian product of the IN lists on clustering columns (valuesAsClustering), and likewise on composite partition key columns. [details](runs/wave2.md#oc-412) | CP-8, CP-11, CP-12, CP-13 | picked: U5 |

> | OC-351 | 2026-11-18 | `none-queryprocessor-validatekey-key_remaining--autonomous` | autonomous | IN lists on a composite partition key are expanded into their full cartesian product on the heap before any key is validated or counted. [details](runs/wave2.md#oc-351) | — | picked: U5 |

> | OC-352 | 2026-11-18 | `none-validatekey-key_remaining--autonomous` | autonomous | A single UPDATE/DELETE with IN on the partition key and IN on clustering columns builds keys x clusterings rows in memory before max_mutation_size is checked. [details](runs/wave2.md#oc-352) | — | picked: U5 |

> | OC-365 | 2026-11-18 | `none-queryprocessor-validatekey-key_remaining--autonomous` | guided | A SELECT with IN on partition-key columns builds every key, and the cartesian product for composite keys, before any limit applies. [details](runs/wave2.md#oc-365) | CP-2, CP-8, CP-11, CP-13, CP-1 | picked: U5 |

> | OC-276 | 2026-11-18 | `batch_size_warn_threshold-verifyBatchSize-size--autonomous` | autonomous | The batch's mutations are built in full on the coordinator heap before any batch-size check runs, and IN lists make that build far larger than the request. [details](runs/wave2.md#oc-276) | — | picked: U5 |

**Full text of each row (quoted from `runs/wave2.md`).**

> **OC-412** — Holder: MultiCBuilder.elementsList, the cartesian product of the IN lists on clustering columns (valuesAsClustering), and likewise on composite partition key columns. Each combination is a new ArrayList copy, and build() then turns them into a NavigableSet<Clustering>. Why nothing stops it: the only cap is the in_select_cartesian_product guardrail, which ships off (-1) and is skipped when disabled. Even when it is enabled, it checks builder.buildSize() only after each column's product has been allocated. The query is only about 16 MiB at most, but the product is multiplicative. Size at defaults: a SELECT with c1 IN (1,000 values) AND c2 IN (100,000 values), a query of about 600 KB, builds 1e8 combinations at about 140 B each (ArrayList + Object[] + Clustering + TreeSet entry), roughly 14 GB, from one request. ArrayList.remove(0) in the loop makes it CPU-heavy (memmoves), but memory still grows to the full product within about a minute. Any user with SELECT can reach it, with no authentication at the default authenticator.
> **Where:** src/java/org/apache/cassandra/cql3/restrictions/ClusteringColumnRestrictions.java:105-119 (guard at :112-113, after appendTo); src/java/org/apache/cassandra/db/MultiCBuilder.java:339-370 (addEachElementToAll product); src/java/org/apache/cassandra/cql3/restrictions/PartitionKeySingleRestrictionSet.java:95-96; src/java/org/apache/cassandra/config/Config.java:877-878 (thresholds -1)

> **OC-351** — IN lists on a composite partition key are expanded into their full cartesian product on the heap before any key is validated or counted. MultiCBuilder.addEachElementToAll builds one ArrayList per combination; build() then copies these into a BTreeSet of Clustering objects, and toByteBuffers serializes each one. SelectStatement then clones each key into a DecoratedKey and creates one SinglePartitionReadCommand per key. Both guardrails that could stop this, in_select_cartesian_product and partition_keys_in_select, are -1 (disabled) by default, and partitionKeysInSelect is checked only after the list exists. There is no cap on IN-list length beyond the 16 MiB native frame. Rough size: (a,b) IN 5,000 x 5,000 values (~80 KB request) gives 25M composites. That is ~60-70 B per composite in elementsList, ~80-100 B per BTreeSet Clustering, ~60 B per serialized key and as much again for the clone, ~40 B per DecoratedKey and ~150 B+ per read command: several GB on one coordinator request. 2,000 x 2,000 already gives 4M keys, ~1-2 GB.
> **Where:** PartitionKeySingleRestrictionSet.java:60-71,88-101; MultiCBuilder.java:339-372,416-436; SelectStatement.java:716-735; ModificationStatement.java:368-375; Guardrails.java:251,294; conf/cassandra.yaml:2098-2105

> **OC-352** — A single UPDATE/DELETE with IN on the partition key and IN on clustering columns builds keys x clusterings rows in memory before max_mutation_size is checked. Both lists are materialized by MultiCBuilder as full cartesian products (in_select_cartesian_product is disabled by default and not applied across pk x ck). ModificationStatement then loops over every key (Validation.validateKey) and every clustering, calling addUpdateForKey into one PartitionUpdate.Builder per key. Mutation.validateSize runs only later, at the commit-log add or the remote MutationVerbHandler, after everything is built. Rough size: pk IN 5,000 x ck IN 5,000 (a ~80 KB request) is 25M rows at ~100-200 B per row and cell, so ~2.5-5 GB on the coordinator heap. A 2-column composite pk IN 5,000 x 5,000 also gives 25M keys at ~60-70 B each in elementsList plus Clustering and ByteBuffer copies.
> **Where:** ModificationStatement.java:368-375,776-818; MultiCBuilder.java:339-372,416-436; PartitionKeySingleRestrictionSet.java:88-101; ClusteringColumnRestrictions.java:112-113; Mutation.java:169; CommitLog.java:304; MutationVerbHandler.java:54; conf/cassandra.yaml:2104-2105

> **OC-365** — A SELECT with IN on partition-key columns builds every key, and the cartesian product for composite keys, before any limit applies. Both guardrails, partition_keys_in_select and in_select_cartesian_product, ship off (-1). Even when enabled, they run after the product has been built: MultiCBuilder.addEachElementToAll copies a composite list per combination before PartitionKeySingleRestrictionSet calls guard(builder.buildSize()), and partitionKeysInSelect runs after keys are returned. SelectStatement then clones and decorates each key (ByteBufferUtil.clone + DecoratedKey + token) and creates one SinglePartitionReadCommand per key, all up front, even when paged. The native in-flight limits charge request bytes, not the expansion. Holder: the coordinator's request thread, for the life of the query. Size: about 250-350 B per key. Two IN lists of 3,000 values on a two-column key (about 50 KB request) give 9M keys, about 2.5-3 GB from one request. A single-column IN bound list inside the 16 MiB frame gives about 1.3M keys, about 400 MB, times up to 128 concurrent native requests. The write-side twin is filed under none-validatekey-key_remaining--autonomous.
> **Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:716-736; src/java/org/apache/cassandra/cql3/restrictions/PartitionKeySingleRestrictionSet.java:89-99; src/java/org/apache/cassandra/db/MultiCBuilder.java:339-358; src/java/org/apache/cassandra/config/Config.java:875-878

> **OC-276** — The batch's mutations are built in full on the coordinator heap before any batch-size check runs, and IN lists make that build far larger than the request. In a batch statement such as `UPDATE t SET v=? WHERE k IN ? AND c IN ?`, addUpdates builds one row for every (partition key x clustering) pair. Nothing caps that product at defaults: the in_select_cartesian_product guardrail on the shared restriction code is -1 (off), and the batch_size_warn and batch_size_fail checks (5 KiB / 50 KiB) and Mutation.validateSize (max_mutation_size 16 MiB) all run only after every PartitionUpdate has been built. Each row is about 150 B of heap (BTreeRow, cell, liveness info, btree array). A bound list of ints costs about 8 B per element, so a 1.6 MB request with 1,000 keys x 100,000 clusterings builds about 1e8 rows, or about 15 GB. That is past any default heap (8 GB at most), from one request well under the 16 MiB message cap.
> **Where:** cql3/statements/BatchStatement.java:428,439 (verifyBatchSize after getMutations); BatchStatement.java:312 (addUpdates per statement); cql3/statements/ModificationStatement.java:792,802-816 (row per key x clustering); cql3/restrictions/ClusteringColumnRestrictions.java:112-113 and PartitionKeySingleRestrictionSet.java:95-96 (guardrail only if enabled); config/Config.java:877-878 (default -1); cql3/statements/SingleTableUpdatesCollector.java:112 and db/Mutation.java:169-176 (size check after build)

**Triage row (quoted from [`runs/triage-2026-11-18.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/triage-2026-11-18.md), rank 1):**

> | 1 | OC-412 | yes | single ARM node | One SELECT with c1 IN (1,000) AND c2 IN (100,000), a request of about 600 KB, makes MultiCBuilder build all 1e8 clustering combinations on the coordinator heap. At about 140 B each that is roughly 14 GB, and the in_select_cartesian_product and partition_keys_in_select guardrails ship at -1. Even 2,000 x 2,000 (4M keys, 1-2 GB) passes a 2 GiB heap, so one request on one node is a sub-hour test. | No existing case. Same root as OC-351 and OC-365 (composite partition-key IN) and the write-side OC-352, OC-366 and OC-276 (batch). OC-96 (names-filter point reads with ck IN) is a related read path. |

Triage notes: §4 lists the cluster "IN cartesian product: OC-351, 352, 365, 366, 412 and 276"; §5 ranks OC-412 among the
"likely fastest first wins … one request … on a single 2 GiB node" and notes that it depends on the superuser and
AllowAll defaults, "where guardrails are skipped, but they are off at -1 anyway". OC-366 (the single-statement write
form, same text as OC-352) was picked separately as **U7**
([`in_select_cartesian_product--modification-IN-product-row-build`](../in_select_cartesian_product--modification-IN-product-row-build/in_select_cartesian_product--modification-IN-product-row-build.md), on ms0625).

**What this design covers (stated before any reading).** The cluster's shared mechanism is the unguarded
`MultiCBuilder` expansion of IN × IN into its full cartesian product on the request thread, with
`in_select_cartesian_product` off by default and, when on, checked only after the product is allocated.

| Row | Covered? | By which condition | Not covered |
|---|---|---|---|
| OC-412 (primary) | **yes, fully** | condition **CK**: `pk = ? AND c1 IN ? AND c2 IN ?` → `ClusteringColumnRestrictions.valuesAsClustering` → `MultiCBuilder` product → `BTreeSet<Clustering>` → `ClusteringIndexNamesFilter`; plus the diagnostic arm **G** for its "guard only after each column's product" claim | its composite-pk remark is condition PK |
| OC-351 | **yes** | condition **PK**: `a IN ? AND b IN ?` on a composite partition key → `PartitionKeySingleRestrictionSet.values` → product → serialized keys → clone + `DecoratedKey` → one `SinglePartitionReadCommand` per key (+ pagers) | — |
| OC-365 | **yes, its product form** | condition **PK** (same path; "all up front, even when paged": the design pages at 5,000 rows) | its single-column variant (≈ 1.3M keys from one 16 MiB IN list × up to 128 concurrent requests) is a multiplicity design and is **not** tested |
| OC-352 | **root only** | the same `MultiCBuilder` product runs for UPDATE/DELETE restrictions, but this design sends no write | the write-side holder (one `PartitionUpdate` row per key × clustering before `Mutation.validateSize`) is **not** tested here; it is U7's design (OC-366, same text) |
| OC-276 | **root only** | as OC-352 | the batch form (`BatchStatement.getMutations` before `verifyBatchSize`) is **not** tested; overlaps U7 and B14 |

So a CK result decides OC-412; a PK result decides OC-351 and the product form of OC-365; OC-352 and OC-276 get only
the shared-root evidence and should be closed against U7 (or a batch case) by the owner, not by this case.

**Phase-1 constraints, checks and stage 4.**
- OC-412's phase-1 file is about `ClusteringColumnRestrictions.handleInFilter` (`:226-229`), estimate `negative`
  (planning metadata, caps nothing); its A4 notes that the guardrail `inSelectCartesianProduct` sits in
  `valuesAsClustering` (`:105-119`), a different method. No stage 4.
- OC-351 / OC-365: `QueryProcessor.java:251` (`validateKey`: non-null, non-empty key), estimate `negative`. No stage 4.
- OC-352: `Validation.java:47` (empty-key check), estimate `negative`. No stage 4.
- OC-276: `BatchStatement.java:340` (`batch_size_warn_threshold`), estimate `negative`. **Stage 4**
  ([results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/batch_size_warn_threshold-verifyBatchSize-size--autonomous.md),
  2026-10-26): unit Refuted / cluster Not confirmed — the warn threshold does not cap; acceptance, rows and bytes
  identical at warn 5 KiB and 90,000 KiB; a +14–20 % allocation step in the warn branch; a warn above fail silently
  disables the fail check. No IN product was measured; it is not evidence for or against this mechanism.

None of the four files names the cartesian product as the constraint; the candidates come from their stage-5 clue
pass. The control actually involved is the guardrail pair below.

**Contract and default (checked against the pinned source, 2026-11-18).**
- `in_select_cartesian_product_warn_threshold = -1`, `_fail_threshold = -1` (`Config.java:877-878`; yaml commented
  `cassandra.yaml:2104-2105`); `partition_keys_in_select_* = -1` (`Config.java:875-876`; `cassandra.yaml:2098-2099`).
  `Threshold.enabled` is false when both thresholds are ≤ 0 (`Threshold.java:80-86`), and `Guardrail.enabled(state)`
  is false unless the client is an ordinary user (`Guardrail.java:93-96`). The shipped
  `authenticator: AllowAllAuthenticator` (`cassandra.yaml:198`) makes every client non-ordinary, so both guardrails are
  skipped twice over at defaults. **Unprotected configuration.**
- Where the guard would run: `ClusteringColumnRestrictions.valuesAsClustering` (`:105-119`) calls `r.appendTo(builder)`
  and only then `guard(builder.buildSize())` (`:112-113`); `PartitionKeySingleRestrictionSet.values` likewise
  (`:88-101`, guard `:95-96`); `partitionKeysInSelect` runs on `keys.size()` after `values()` returned
  (`SelectStatement.java:715-723`). For the last IN column the product is complete before any guard sees it
  (**late check** when enabled).
- The product: `MultiCBuilder.MultiClusteringBuilder.addEachElementToAll` (`MultiCBuilder.java:339-372`): for each
  existing composite, `elementsList.remove(0)` (`:354`, an O(n) array shift) and one `new ArrayList<>(oldComposite)`
  per value (`:358`). `build()` (`:419-437`) adds one `Clustering` per composite (`CBuilder.buildWith`, `CBuilder.java:173-182`:
  a new `ByteBuffer[]` + `BufferClustering`) to a `BTreeSet.Builder` (`Object[]` doubling, `BTree.java:1539`) while
  `elementsList` is still reachable.
- No limit on the number of values in an `IN ?` bound list: `InRestrictionWithMarker.getValues`
  (`SingleColumnRestriction.java:331-339`) returns the deserialized list. The only byte bounds are on the request:
  `native_transport_max_message_size` = min(`max_mutation_size` 16 MiB, heap/10, heap/40) (`DatabaseDescriptor.java:3237-3244`),
  `native_transport_max_frame_size` 16 MiB (`Config.java:285`), in-flight heap/10 global and heap/40 per IP
  (`DatabaseDescriptor.java:649-656`). They charge request bytes, not the expansion.

**JIRA prior art (read only; nothing posted).** Survey
[`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv):
**CASSANDRA-15250** *Large cartesian produces in IN queries cause the server to run out of memory* (kept; Unresolved;
"guardrail added later (CASSANDRA-17187) but off by default"); CASSANDRA-9454 *Log WARN on Multi Partition IN clause
Queries* (Duplicate, completed by the 17186 guardrail, off by default); CASSANDRA-3911 *Basic QoS support* (Won't Fix);
CASSANDRA-12420 (duplicate IN keys with a small fetch size loop, Fixed 2.1.16, excluded). The survey's summary groups
15250 / 9454 under "Guardrails off by default". **JIRA REST, 2026-11-18 13:50 EST:** CASSANDRA-15250 is still
**Open** (created 2019-07-27, no fix version; Avi Kivity: nine-column composite pk `IN (1..10)` each, 1e9 combinations,
"a garbage collection spiral from which it does not recover"; the only comment suggests "simpler to just limit the
number of rows"). CASSANDRA-17187 *Guardrail for SELECT IN terms and their cartesian product* Resolved/Fixed 4.1
(the shipped-off guardrail); CASSANDRA-17186 *Guardrail for number of partition keys on IN queries* Fixed 4.1.
Search `project = CASSANDRA AND (text ~ "cartesian" OR summary ~ "IN clause" OR summary ~ "IN query" OR summary ~
"IN restrictions") AND (text ~ "memory" OR text ~ "OOM" OR text ~ "OutOfMemoryError" OR text ~ "guardrail")`: 79
hits; none fixes the product materialization or the guard order (CASSANDRA-19341, the 6.0 restriction-hierarchy
rewrite, is a refactor, not a limit). **Verdict: `known-open`** (15250, the same shape on the partition key) with the
mitigating guardrail **`documented`** as opt-in and off by default. Not known-fixed, so this is not a positive control.
This case adds the clustering-key form, a sub-hour reproduction at a 2 GiB heap from an ≈ 8 MB request, and the late
guard order.

## 2. Design solution (stage 1; frozen)

**Mechanism.** Direction: **unprotected configuration** (protocol "Unprotected results": the control exists and ships
disabled) with an **unprotected accumulation** shape (one request's own expansion); diagnostic sub-claim for arm G:
**bypass by late enforcement** when the guardrail is enabled. Technique notes:
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) for the boundary and budget search at
default capacities, [`bypass-playbook.md`](../../../bypass-playbook.md) row "Periodic/late enforcement" for arm G.
A prepared `SELECT * FROM u5.ck WHERE pk = ? AND c1 IN ? AND c2 IN ?` with bound lists of k1 and k2 ints reaches
`SelectStatement.makeClusteringIndexFilter` (`SelectStatement.java:812-843`) → `getRequestedRows` (`:972-977`) →
`StatementRestrictions.getClusteringColumns` (`:934-942`) → `ClusteringColumnRestrictions.valuesAsClustering`
(`:105-119`), which builds N = k1 × k2 composites in `MultiCBuilder.elementsList` (`MultiCBuilder.java:339-372`) and
then a `BTreeSet<Clustering>` of N entries (`:419-437`) on the Native-Transport-Requests thread, before the read and
before any limit. Condition PK sends `SELECT * FROM u5.pk WHERE a IN ? AND b IN ?` on a composite partition key:
`StatementRestrictions.getPartitionKeys` (`:811`) → `PartitionKeySingleRestrictionSet.values` (`:88-101`: product,
`build()`, then `toByteBuffers` `:60-71`: one serialized composite key per entry) → `SelectStatement.getSliceCommands`
(`:713-742`: `ByteBufferUtil.clone` + `decorateKey` per key, `SinglePartitionReadQuery.createGroup` = one
`SinglePartitionReadCommand` per key) → `MultiPartitionPager` (`MultiPartitionPager.java:58-77`: one pager per
command). Nothing between the request bytes (≤ 16 MiB) and these per-combination objects is counted.

**Protection map** (fixed before any run).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| IN cartesian product (CK and PK) | `MultiCBuilder.elementsList` (`ArrayList` + `Object[2]` per composite, `MultiCBuilder.java:358`) → `BTreeSet<Clustering>` (`ByteBuffer[2]` + `BufferClustering` per composite, `:435`); released when the statement's read command completes (CK: held by `ClusteringIndexNamesFilter`) or after `values()` returns (PK) | `builder.buildSize()` = composites | `in_select_cartesian_product_fail_threshold: -1` (**off**), and skipped for non-ordinary users (AllowAll) | nothing at defaults → **unprotected configuration**. When enabled: request fails with `InvalidRequestException`, but only after the column's product is allocated (late) |
| Partition keys in SELECT (PK) | serialized keys (`toByteBuffers`), clones, `DecoratedKey` + `LongToken`, one `SinglePartitionReadCommand` and one `SinglePartitionPager` per key; released at the end of the query | `keys.size()` | `partition_keys_in_select_fail_threshold: -1` (off); checked after the key list exists (`SelectStatement.java:720-723`) | nothing |
| Native request size | the request frame (bound lists ≈ 8 B per int value) | message bytes | `native_transport_max_message_size` = 16 MiB at heaps ≥ 640 MiB; `native_transport_max_frame_size` 16 MiB | rejects the frame (request bytes only) |
| Native in-flight request bytes | request bytes while the request is processed | in-flight bytes | heap/10 global (204.8 MiB at 2 GiB), heap/40 per IP (51.2 MiB) | back-pressure on reads from the socket; charges ≈ 8 MB, not the product |
| Concurrency | one request per NTR thread | NTR threads | `native_transport_max_threads` 128 | not used: the design sends **one** request |
| Read after the build (CK, PK) | names-filter read of one 1-row partition (CK); one read per key (PK); page ≤ 5,000 rows | rows | page size 5,000; read thresholds off; `read_request_timeout` 5 s | irrelevant to the claimed holder (built before the read) |
| Slow/failed-query monitor (**ledgered, not claimed**) | `MonitoringTask` renders `ReadCommand.name()` = `toCQLString()` (`ReadCommand.java:895-898`), which lists every requested clustering (`ClusteringIndexNamesFilter.java:166-194`) for a read that was slow (> `slow_query_log_timeout` 500 ms) or aborted, every 5 s | none | none | a survivor of the build may later grow a string of ≈ 12 B × N; an OOM there is **not** this case's endpoint (verdict rules) |
| Baseline | memtable heap pool (H/4, nearly empty), key cache (min(5 % H, 100 MiB)), schema, system keyspaces | own counters | defaults | evict / flush |

**Configuration and budget audit.**
- Build: copy of `ms0617:/mydata/s4/cassandra-base` (cassandra 5.0.9, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`
  sha256 `e55f4f2974cb6120712a5cdfbbed9ee1ba25d97b887cbe71b64fd194f3b5a942`, shipped `conf/cassandra.yaml` md5
  `714ee9bf58b3bc1710377ac16bcbba03`), JDK 11.0.33 aarch64, G1 with the shipped `jvm11-server.options`
  (`G1HeapRegionSize=16m` `:66`, `MaxGCPauseMillis=300` `:79`), `jvm-server.options:120`
  `-XX:+HeapDumpOnOutOfMemoryError`, `cassandra-env.sh:209` `-XX:OnOutOfMemoryError="kill -9 %p"` (so the first OOM
  ends the JVM: it is the initiating failure). Ubuntu 22.04.1, kernel 5.15.0-191, cgroup v2 (user delegation:
  memory, pids), 8 GiB swap present (excluded per scope).
- **Every capacity constraint at its shipped default (V6)** in arms A (test, control, budget search):
  `in_select_cartesian_product_*` −1, `partition_keys_in_select_*` −1, `AllowAllAuthenticator`,
  `native_transport_max_message_size` (derived: 16 MiB), `native_transport_max_frame_size` 16 MiB, in-flight limits
  derived from the heap, `native_transport_max_threads` 128, `read_request_timeout` 5 s, `native_transport_timeout`
  12 s, `slow_query_log_timeout` 500 ms, `num_tokens` 16. Constraints differ only in arm G (guardrail on, diagnostic)
  and in the intervention build I (patched; below).
- `cassandra.yaml` diff from the shipped file (**environment only**, every arm): `data_file_directories`,
  `commitlog_directory`, `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under the lifetime's node
  dir. Addresses stay at the shipped `localhost`; the client runs on the same node.
- **Budgets (V7; standing rule: heap and direct ≥ 512 MiB meet V7, 2 GiB ideal; record resolved values).**
  - **Primary: heap 2 GiB** (`MAX_HEAP_SIZE=2G`; `HEAP_NEWSIZE` unset, G1), `MAX_DIRECT_MEMORY_SIZE` unset → resolved by
    `cassandra-env.sh` on ms0617 (MemTotal 65,791,808 kB; `free -m` 64,249 MB; G1 → `heap_limit = 31744`; ½ RAM
    32,124 > 31,744) to **`-XX:MaxDirectMemorySize=15872M`** (record from the process command line). 2 GiB is the ideal
    budget and what `cassandra-env.sh` resolves for a 4 GiB-RAM node; a hand-set 2 GiB heap on a large node is common
    practice (U4, C2 used the same pair). The direct budget is not the claimed domain.
  - **Upward search** (heap only, direct as resolved): **4096M**, **8192M**, **15872M**, and **31744M** = ms0617's own
    automatic resolution (heap and direct both unset: `-Xmx31744M`, direct 15872M), the largest heap
    `cassandra-env.sh` ever resolves. Compressed oops stay on below 32 GiB, so per-object sizes do not change.
  - **No container budget.** Every Cassandra JVM runs in `systemd-run --user --scope -p MemoryMax=<heap + 6G>
    -p MemorySwapMax=0` (isolation and swap off only). A scope `oom_kill` makes the lifetime **invalid**; record
    `memory.events` at the end of every lifetime.

**Ceiling arithmetic.** No contract capacity bounds the product: N = Π (IN list lengths), and the only bound on a
list is the 16 MiB request (≈ 2M int values in total). Per-composite live heap (estimates, compressed oops, 16 B
array headers; ±25 %):

| Stage | CK (2 int clustering columns) | PK (2 int partition-key columns) |
|---|---|---|
| `elementsList` entry: `ArrayList` 24 B + `Object[2]` 24 B + list slot 4 B (×≤ 1.5 growth slack; transient copy at growth) | 52–58 B | 52–58 B |
| `build()`: `ByteBuffer[2]` 24 B + `BufferClustering` 16 B + `BTree.Builder` slot 4–8 B (+ copy at doubling) + tree ≈ 4.5 B | +50–56 B | +50–56 B |
| `toByteBuffers`: `HeapByteBuffer` 48 B + `byte[14]` 32 B + slot 4 B | — | +84 B |
| `getSliceCommands`: clone 80 B + `BufferDecoratedKey` 24 B + `LongToken` 24 B + slot 4 B; `SinglePartitionReadCommand` ≈ 100–120 B + slot 4 B (the `elementsList`/`BTreeSet` are garbage by now) | — | +235–255 B |
| `MultiPartitionPager`: one `SinglePartitionPager` ≈ 40 B + slot 4 B | — | +44 B |
| **Peak live per composite / key** | **≈ 108 B** (band 90–140) | **≈ 370 B** (band 280–450) |

Baseline at 2 GiB (empty node, a few rows): ≈ 0.15–0.3 GiB. Predicted smallest failing N at 2 GiB:
CK ≈ (2048 − 250) MiB / 108 B ≈ **17M** (band 12–24M) for the whole build, and ≈ 33M (band 28–40M) for
`elementsList` alone; PK ≈ 1.8 GiB / 370 B ≈ **5M** (band 4–7M). Humongous objects (≥ 8 MiB with 16 MiB regions:
`elementsList`'s backing `Object[]` is ≥ 8 MiB from 2M entries, 256 MB at 64M, and grows ×1.5 by copy) need contiguous
regions and can lower these. At the chosen test size (CK N_T = 64M) the build needs ≈ 6.9 GB and `elementsList` alone
≈ 3.5 GB: **1.7× the 2 GiB heap before `build()` even starts**. Request bytes K ≈ 8.0 MB against the 16 MiB message
limit and 51.2 MiB per-IP in-flight limit (K ≪ C, U ≫ K: amplification ≈ 870× per request byte).
CPU: `elementsList.remove(0)` shifts the list once per first-column value, ≈ N × k1 / 2 references in total
(64M × 32 = 2.0e9 references ≈ 8 GB of memmove at N_T); k1 is kept small (≤ 400) so that the build takes seconds to a
few minutes on the m400, not hours. Values are sent sorted and distinct so `BTree.Builder` needs no sort.

**Workload and environment.**
- **Node `ms0617` only** (Utah m400, **aarch64**, 8 cores, MemTotal 65,791,808 kB, 8 GiB swap excluded per scope,
  `/mydata` 39 GB with **36 GiB free**; checked 2026-11-18 13:40 EST read-only: no java process, load 0.00; node clock
  is **MST = EST − 2 h**). `/mydata/s2r2/` and `/mydata/u1r2/` (≈ 210 MB each) are other cases' run data and
  `/mydata/s4/cassandra-base` is the shared build: **do not touch them**. Victim = one Cassandra node; client = one
  stdlib-only Python 3.10 process on the same node (loopback).
- Work dir `/mydata/u5/` (local disk, not NFS): `tree/` (copy of `cassandra-base`), `tree-I/` (intervention copy),
  `conf-pristine/`, `template-A/`, `template-G/`, `node/` (per lifetime), `runs/<label>/`.
- Schema (created once in lifetime `LOAD`, heap 2G, not a reading):
  `CREATE KEYSPACE u5 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE u5.ck (pk int, c1 int, c2 int, v int, PRIMARY KEY (pk, c1, c2))`;
  `CREATE TABLE u5.pk (a int, b int, v int, PRIMARY KEY ((a, b)))`; default table options. Rows:
  `INSERT INTO u5.ck (pk,c1,c2,v) VALUES (0,0,0,1)` and `INSERT INTO u5.pk (a,b,v) VALUES (0,0,1)`, so a completed
  request returns exactly **1 row** (correctness check). Then `nodetool flush u5`, `nodetool drain`, SIGTERM by PID;
  `cp -a node template-A` and empty `template-A/saved_caches/`. **Every measured lifetime starts from a fresh `cp -a`
  of its template.**
- `LOAD-G` (for arm G only, P4): a second template from the same steps with `authenticator: PasswordAuthenticator`;
  wait for "Created default superuser role" in `system.log`, then as `cassandra`/`cassandra`:
  `CREATE ROLE u5 WITH PASSWORD = 'u5' AND LOGIN = true AND SUPERUSER = false` (with the shipped
  `AllowAllAuthorizer` no GRANT is needed; `u5` is an ordinary user, so guardrails apply), then the schema and rows.
- **Client `u5client.py`** (write it from B11's stdlib raw-protocol client,
  [`../ExecuteMessage_literal_1000--traced-render-outside-inflight/harness/client.py`](../ExecuteMessage_literal_1000--traced-render-outside-inflight/harness/client.py)):
  native protocol **v4** (not v5: lessons, large v5 requests), one connection, STARTUP (arm G: `AUTHENTICATE` →
  `AUTH_RESPONSE` `\0u5\0u5`), PREPARE the condition's statement, one EXECUTE with consistency ONE, flags
  VALUES | PAGE_SIZE, **page size 5,000** (driver default), values: CK `[int 0][list<int> 0..k1−1][list<int> 0..k2−1]`;
  PK `[list<int> 0..k1−1][list<int> 0..k2−1]`; a list is `[int n]` then n × `[int 4][int v]` (build the bytes with
  `array`/`struct` in bulk). **Never send IN literals in the query string** (that would test the parser, OC-278/409).
  Logs one JSON line per event: `t_send` (wall clock, ms), frame body bytes (= K), `t_resp`, response opcode, rows
  count or error code + message, or `conn_closed`. Socket timeout = the lifetime's window. Before the first reading,
  check the frame: EXECUTE body ≤ 16,777,216 B.
- **Conditions and labels.** `N = k1 × k2`. Arm **A** = shipped defaults (stock jar). Arm **I** = stock config, patched
  jar (`tree-I`) and `JVM_EXTRA_OPTS += -Du5.max_in_product=1100000`. Arm **G** = template-G, stock jar,
  `authenticator: PasswordAuthenticator`, `in_select_cartesian_product_fail_threshold: 1000000` (warn −1), client logs
  in as `u5`. Priorities P1 > P2 > P3 > P4 (time plan).

| Pri | Label | Arm | Heap | Cond. | k1 × k2 (N) | Reps |
|---|---|---|---|---|---|---|
| P1 | `IC` instrument check (not a reading) | A | 2G | CK, PK | 4×4, 1×1,000, 64×1,000 (CK); 4×4, 1×1,000 (PK); one request each, same lifetime | 1 |
| P1 | `CAL-CK-2G-<N>` boundary (one lifetime per point, ascending, stop after the first OOM) | A | 2G | CK | k1 = 64: 4M (k2 62,500), 8M (125,000), 16M (250,000), 24M (375,000), 32M (500,000), 64M (1,000,000) | 1 each |
| P1 | `T-CK-2G-1..3` test | A | 2G | CK | **64 × 1,000,000 = 64M** (body ≈ 8.0 MB) | 3 |
| P1 | `M-CK-2G-1..3` matched control | A | 2G | CK | **1 × 1,000,063** (same number of values and bytes; N ≈ 1.0M) | 3 |
| P1 | `I-CK-2G-1..3` intervention | I | 2G | CK | 64 × 1,000,000 | 3 |
| P1 | `IM-CK-2G` useful work under I | I | 2G | CK | 1 × 1,000,063 | 1 |
| P2 | `CAL-CK-4G` budget search | A | 4096M | CK | 128 × 1,000,000 = 128M | 1 |
| P2 | `CAL-CK-8G` | A | 8192M | CK | 160 × 1,600,000 = 256M (body ≈ 12.8 MB) | 1 |
| P3 | `CAL-PK-2G-<N>` boundary (ascending, stop after the first OOM) | A | 2G | PK | k1 = 16: 1M (k2 62,500), 2M (125,000), 4M (250,000), 8M (500,000), 16M (1,000,000) | 1 each |
| P3 | `T-PK-2G-1..3` | A | 2G | PK | N_T-PK = the smallest failing `CAL-PK-2G` point (predicted 16 × 500,000 = 8M) | 3 |
| P3 | `M-PK-2G-1..3` | A | 2G | PK | 1 × (k2_T + 15) | 3 |
| P3 | `I-PK-2G-1..3` | I | 2G | PK | as T-PK | 3 |
| P4 | `CAL-CK-15872M` | A | 15872M | CK | 200 × 1,600,000 = 320M | 1 |
| P4 | `G-CK-2G-64M-1..2` diagnostic | G | 2G | CK | 64 × 1,000,000 | 2 |
| P4 | `G-CK-2G-Nf` diagnostic | G | 2G | CK | the smallest failing `CAL-CK-2G` point, only if it is ≤ 28M (its `elementsList` alone fits the heap) | 1 |
| P4 | `CAL-CK-auto` | A | auto (31744M) | CK | 400 × 1,600,000 = 640M | 1 |
| P4 | `REP-<H>-1..2` | A | the largest failing heap | CK | that heap's N | 2 |

  If `CAL-CK-2G` survives 64M (not predicted), run 128 × 1,000,000 once before deciding (verdict rules). If `T-PK`
  has fewer than 3 OOMs at its N, add up to 2 repetitions, then use the next CAL point.
- **Intervention build (arm I; diagnostic patch, separate tree).** Patch `src/java/org/apache/cassandra/db/MultiCBuilder.java`
  in `MultiClusteringBuilder.addEachElementToAll` (`:339`) and `addAllElementsToAll` (`:376`), as the first statement
  after `checkUpdateable()`, a **check before allocation**:
  ```java
  long u5Limit = Long.getLong("u5.max_in_product", -1L);
  if (u5Limit > 0 && (long) Math.max(1, elementsList.size()) * values.size() > u5Limit)
      throw new org.apache.cassandra.exceptions.InvalidRequestException(
          "u5: IN cartesian product " + Math.max(1, elementsList.size()) + " x " + values.size() + " exceeds " + u5Limit);
  ```
  Compile only that file against the stock jar (`javac -nowarn -d patchcls -cp 'tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:tree/lib/*' MultiCBuilder.java`),
  `cp -a tree tree-I`, `jar uf tree-I/build/apache-cassandra-5.0.9-SNAPSHOT.jar -C patchcls org/apache/cassandra/db/`
  (only `MultiCBuilder*.class`); save the exact diff as `harness/u5-pre-allocation-check.patch` and both jar sha256s in
  `run.meta`. Never run `ant` in a tree a node runs from. The limit 1,100,000 lets M (1 × 1,000,063) through and
  rejects every T size (≥ 64 × 62,500 = 4M). Since the stock `-1` keeps the check off, `tree-I` without the property
  behaves as stock (not used as a reading).
- **Harness** (build under `harness/` in this folder; adapt U4's
  [`../cql-row-limit--wide-row-default-pages/harness/`](../cql-row-limit--wide-row-default-pages/harness/)):
  1. `setup.sh`: `mkdir -p /mydata/u5`; `cp -a /mydata/s4/cassandra-base /mydata/u5/tree`; `cp -a tree/conf conf-pristine`;
     build `tree-I` (above); write `harness/` copies to `/mydata/u5/h/`.
  2. `victim-ctl.sh` (from U4's): `ROOT=/mydata/u5`; per lifetime `rm -rf $ROOT/node && cp -a $ROOT/template-<A|G> $ROOT/node`
     (`LOAD*` start empty); conf = pristine + the yaml diff of the arm; launch `bin/cassandra -f` from `tree` (arms A, G)
     or `tree-I` (arm I) under `systemd-run --user --scope --unit=u5-<label> -p MemoryMax=<heap+6G> -p MemorySwapMax=0`,
     as `( setsid nohup … < /dev/null > $RUN/stdout.log 2>&1 & )`, with `MAX_HEAP_SIZE` (unset for `auto`),
     `MAX_DIRECT_MEMORY_SIZE` unset, `CASSANDRA_HEAPDUMP_DIR=$RUN`,
     `JVM_EXTRA_OPTS="-Xlog:gc*,safepoint:file=$RUN/gc.log:time,uptime,level,tags"` (+ `-Du5.max_in_product=1100000` in
     arm I; + `-XX:-HeapDumpOnOutOfMemoryError` for heaps > 4096M, disk); save `yaml.diff`, `run.meta` (label, arm,
     cond, k1, k2, N, heap, resolved `-Xmx` / `-XX:MaxDirectMemorySize` from `ps`, jar sha256, start time EST).
  3. `run-arm.sh <label> <A|I|G> <heap|auto> <CK|PK> <k1> <k2> <window_s>`: refuse if any `CassandraDaemon` runs;
     check `df /mydata` (free ≥ heap + 8 GiB, else delete the oldest hprof not kept, after its summaries exist, and log
     it); clone; start; ready = "Starting listening for CQL clients" in `system.log` within 180 s (else invalid, retry
     once); start samplers; run the client; end at client exit + 15 s (three monitoring report periods), or JVM death,
     or `window_s` after `t_send`; outcome; stop a surviving node by PID (SIGTERM, then SIGKILL after 30 s); copy small
     files to `logs/<label>/`. Launch each lifetime as a background job; poll with bounded waits inside the turn.
  4. `u5client.py` (above).
  5. Parsers: `hprofstacks.py` (from U4, unchanged: `… MultiCBuilder`, `… PartitionKeySingleRestrictionSet`,
     `… SelectStatement`); `hprofhist.py` (from U4) with **U5 lines**: counts and shallow bytes of `java.util.ArrayList`,
     `Object[]` of length 2, `Object[]` ≥ 8 MiB (largest = `elementsList` / `BTree.Builder` backing), `ByteBuffer[]` of
     length 2, `org.apache.cassandra.db.BufferClustering`, `java.nio.HeapByteBuffer`, `byte[]` of length 14,
     `BufferDecoratedKey`, `Murmur3Partitioner$LongToken`, `SinglePartitionReadCommand`, `SinglePartitionPager`; top 15
     classes by shallow bytes. `gcwin.py` from U4 (STW fraction per 60 s window).
- **Window per lifetime** (from `t_send`): 2G 240 s; 4096M 420 s; 8192M 600 s; 15872M and auto 900 s.
  A lifetime that reaches its window with the request still running and no OOM is `not reached (time)`, not a survival.

**Instruments (U independent of K).** K = request frame body bytes (client) against the request-byte controls
(16 MiB message, per-IP heap/40, global heap/10), and, in arm G only, the guardrail's own count (`buildSize`, in its
error message). U = (a) `jstat -gc -t <pid> 1000` (S0U+S1U+EU+OU, and OU) from ready to the end, one line per second;
(b) the GC log (`-Xlog:gc*`): heap after each GC, pause times, `Pause Full`, humongous allocations; (c) `RssAnon`
every 5 s; (d) `jcmd <pid> Thread.print` at `t_send` + 2 s and + 6 s (one safepoint each; shows the NTR thread in
`MultiCBuilder` / `BTree` / `CBuilder` / `PartitionKeySingleRestrictionSet` / `SelectStatement` frames); (e) at an OOM:
the JVM's own lines in `stdout.log` (`java.lang.OutOfMemoryError: Java heap space`, `Dumping heap to …`,
`Executing /bin/sh -c "kill -9 …"`), then the hprof (heaps ≤ 4096M): thread stacks (`hprofstacks.py`) for every
OOM lifetime and the U5 histogram (`hprofhist.py`) for `T-CK-2G-1`, `T-PK-2G-1` and `CAL-CK-4G` at least (others if
time); (f) baseline: one `jcmd <pid> GC.class_histogram` in `IC` after the small requests (live baseline heap);
(g) `system.log` / `debug.log` lines from `MonitoringTask` ("operations were slow" / "timed out"), and any guardrail
or `InvalidRequest` line; (h) scope `memory.events`. Parse hprofs only between lifetimes or under `nice -n 19` while an
M or I lifetime runs (their endpoint is not timing-sensitive); never during T, CAL or G lifetimes. Keep at most three
hprofs on disk (`T-CK-2G-1`, `T-PK-2G-1`, `CAL-CK-4G`); delete the others once their stacks and histogram lines are
saved (record each deletion).

**Predicted response.**
- `IC`: every small request returns exactly 1 row; frames and samplers present; baseline live heap 100–250 MiB.
- `CAL-CK-2G`: 4M and 8M return 1 row (old-gen peak ≈ 0.6 and ≈ 1.0 GiB); **Java heap OOM at 16M or 24M** (band
  12–24M); `t_send` → OOM ≤ 60 s.
- `T-CK-2G`: **Java heap OOM 3/3** ≤ 120 s after `t_send`, JVM killed by `OnOutOfMemoryError`; no response to the
  client (`conn_closed`). Thread stacks: the NTR thread in `MultiCBuilder$MultiClusteringBuilder.addEachElementToAll`
  (via `ArrayList.<init>` / `ArrayList.grow` / `Arrays.copyOf`) under `ClusteringColumnRestrictions.valuesAsClustering`
  ← `SelectStatement.makeClusteringIndexFilter`. Histogram: `ArrayList` and `Object[2]` ≈ 25–38M each, the largest
  `Object[]` ≥ 100 MB; these classes ≥ 70 % of the heap. jstat: OU climbing to ≈ 100 % within the window.
- `M-CK-2G`: 1 row 3/3, no OOM; old-gen peak < 0.6 GiB. A `MonitoringTask` line for the slow read is possible
  (≈ 12 MB string): recorded, harmless.
- `I-CK-2G`: `InvalidRequest` "u5: IN cartesian product 64 x 1000000 exceeds 1100000" 3/3 within 1 s of `t_send`;
  heap peak < baseline + 0.2 GiB; no OOM. `IM-CK-2G`: 1 row.
- Budget search: OOM at 4096M (128M), 8192M (256M); P4: 15872M (320M) and auto 31744M (640M). **Largest failing heap
  predicted: 31744M** if `CAL-CK-auto` runs, else 15872M or 8192M (the last one run).
- `CAL-PK-2G`: 1M and 2M survive (the query may time out after its build: reads of 1–2M empty partitions; record
  the response); **OOM at 4M or 8M**. `T-PK-2G`: OOM 3/3; stacks in `PartitionKeySingleRestrictionSet.toByteBuffers`,
  `SelectStatement.getSliceCommands`, `SinglePartitionReadCommand` creation, `MultiPartitionPager.<init>` or
  `MultiCBuilder`; histogram with `HeapByteBuffer` ≈ 1–2 × N, `BufferDecoratedKey`/`LongToken`/
  `SinglePartitionReadCommand` up to N. `M-PK-2G`: no OOM (1 row, or a read timeout after the build); old-gen
  < 0.6 GiB. `I-PK-2G`: rejected 3/3.
- `G-CK-2G-64M`: **OOM 2/2 even with the guardrail on** (the product of the last column is allocated before the guard
  at `ClusteringColumnRestrictions.java:113`); `G-CK-2G-Nf`: rejected by the guardrail ("…cartesian product of the IN
  restrictions on clustering key produces … values, this exceeds failure threshold of 1000000"), no OOM.
- No scope `oom_kill`; no service-loss window (single request; G1 throws once the humongous `elementsList` copy fails).

**Stopping budget and time plan** (deadline: everything stopped and §3–§4 written by **18:07 EST, 2026-11-18**;
ms0617's clock is MST = EST − 2 h). Planned durations from the stage-2 start S (expected ≈ 14:20 EST); a lifetime is
≈ 2–3 min at 2G (start ≈ 45–70 s on the m400, request + OOM ≤ 2 min, 2 GiB dump ≈ 20–40 s):
- S → S+35: setup, `tree-I` build, harness, `LOAD`, `IC`.
- S+35 → S+55: `CAL-CK-2G` (≤ 6 lifetimes).
- S+55 → S+90: `T-CK` ×3, `M-CK` ×3, `I-CK` ×3, `IM-CK` (P1 complete: V1–V5 for CK).
- S+90 → S+115: `CAL-CK-4G`, `CAL-CK-8G` (P2).
- S+115 → S+160: `CAL-PK-2G`, `T-PK` ×3, `M-PK` ×3, `I-PK` ×3 (P3).
- S+160 → 17:35: P4 in its listed order, each only if it can end by 17:45.
- **Hard limits:** no lifetime starts after 17:35 EST unless it ends by 17:45; all processes stopped by **17:50**;
  §3–§4 and the write-backs by 18:05. If S is later than 15:00, skip P4; if later than 15:45, also skip `CAL-PK-2G`
  (run `T-PK` at 8M directly, then `M-PK`, `I-PK`) and `CAL-CK-8G`. No escalation after an OOM beyond the listed plan.

**Controls and intervention.**
- **Matched control `M-CK-2G` ×3 (V2):** same build, budget, template, statement, connection and request bytes
  (the same 1,000,064 int values, 8.0 MB), with the values moved from c1 to c2 so the product is additive
  (N ≈ 1.0M instead of 64M). It isolates the multiplication as the cause, not the request size or the number of values.
  The largest surviving `CAL-CK-2G` point is reported as the boundary (one run). `M-PK-2G` ×3 likewise for PK.
- **Intervention `I-CK-2G` ×3 (V4):** the T request against the diagnostic patch that checks the product **before**
  allocating it (the order the shipped guardrail does not use). Removing the OOM attributes it to the unchecked
  expansion. `IM-CK-2G` shows useful work continues (M's request served under the same patch). `I-PK-2G` ×3 for PK.
- **Diagnostic arm G (P4; not a V-item):** the shipped guardrail switched on for an ordinary user. Predicted to stop
  only products whose last-column list still fits the heap, showing the late check (`G-CK-2G-64M` vs `G-CK-2G-Nf`).

**Verdict rules (stated before readings).**
- **true positive (CK decides the case):** `T-CK-2G` heap OOM in ≥ 3 runs (n/N stated; 2/3 → add up to 2
  repetitions), initiating thread = the NTR thread in the CK build frames listed above, histogram for `T-CK-2G-1`
  showing `ArrayList` + `Object[2]` (+ `BufferClustering` + `ByteBuffer[2]`) ≥ 50 % of the heap; `M-CK-2G` 0/3;
  `I-CK-2G` 0/3 with rejection → `verified-OOM · deployment`, **unprotected configuration**, largest failing heap from
  the search. PK is reported as a second condition with its own status line (decides OC-351 and the product form of
  OC-365); a PK failure does not change the CK verdict.
- **retry:** OOM attributed to another holder (e.g. the first OOM in `MonitoringTask` / `toCQLString`, in the
  parser, or in Netty); OOM in fewer than 3 of 5 runs; time ran out before V1, V2 or V4; service loss
  (≥ 90 % STW over ≥ 60 s) without OOM (`verified-gap`).
- **false positive:** the T request **completes** (1 row, or a timeout/abort after the build, with
  `Thread.print` past `makeClusteringIndexFilter`) at 64M and at 128M on a 2 GiB heap with old-gen post-GC below 90 %,
  i.e. the product is built and held within the budget, and no named factor is left untried; or a default control
  rejects it (that control is then named and the case is negative).
- **invalid lifetime:** scope `oom_kill`; client error before `t_send`; frame rejected for size; node not ready;
  wrong row count (≠ 1) in IC or M. Fix, rerun, record as a deviation.
- **Cleanup:** stop every process started (Cassandra by PID, samplers, client); keep `/mydata/u5/runs/` (logs,
  ≤ 3 hprofs), templates and trees; delete nothing outside `/mydata/u5/`; report what is left.

`sha256 of §1–§2 at freeze: c9634d848dfac02a5be1426174c4227eab62af01dafd6629b2f707435050ea60` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.

**Amendments (stage 2, 2026-11-18, fresh session; hash checked at 13:55 EST: `c9634d84…ea60`, matches).**
- **A1 (13:58 EST, environment).** Work directory `ms0617:/mydata/s4/u5-w4/` instead of `/mydata/u5/` (the wave's node
  instruction: a fresh directory under `/mydata/s4/`). Sub-directories as designed (`tree/`, `tree-I/`, `conf-pristine/`,
  `template-A/`, `node/`, `runs/<label>/`), harness copied to `h/`. No effect on memory.
- **A2 (14:01 EST, instrument).** `jstat` cannot attach: the shipped `jvm-server.options:137` sets
  `-XX:+PerfDisableSharedMem` (IC: "MonitorException: … not found"). Replaced by U4's JMX sampler `C2Sampler`
  (unchanged, 1 s): heap used, G1 Old Gen used and old-gen post-GC usage (`CollectionUsage`), NTR active/pending,
  young/old GC times. Same quantities as jstat's EU+OU / OU. Limitation: its JMX calls stall during full GCs, so in a GC
  spiral its rows freeze; the GC log (`-Xlog:gc*`) covers those windows and is the U source there.
- **A3 (14:06 EST, plan).** `CAL-CK-2G` stopped at its first OOM (16M) as designed, but that OOM is **not in the claimed
  holder** (it is in the ledgered logging path, §3), so the boundary of the build itself is unknown. The two remaining
  listed points (24M, 32M) are run after P3 if time allows, as boundary readings only (not V-items).
- **A4 (14:25 EST, repetitions).** `T-CK-2G` gave 1 OOM in 3 → 2 more repetitions (`T-CK-2G-4`, `-5`; protocol §6 "expand
  repetitions if timing produces mixed outcomes"; the verdict rule's bound is 5).
- **A5 (14:45 EST, P3 driver).** `harness/p3.sh`: if no `CAL-PK-2G` point OOMs, `N_T-PK` = 16 × 500,000 (the design's
  prediction); `T-PK` gets the 2 extra repetitions only if ≥ 1 of 3 OOMed (otherwise 3/5 is unreachable); "then use
  the next CAL point" is not run (time).
- **Reading note.** The harness outcome `SURVIVED` means "JVM alive at the end of the lifetime"; for a T/CAL lifetime
  whose client hit the window it is the design's **`not reached (time)`**.

## 3. Runs (stage 2)

**Environment (as run).** Node `ms0617` (`node4.jason92-326377`, Utah m400, **aarch64**, 8 cores, MemTotal 65,791,808 kB,
8 GiB swap present, `MemorySwapMax=0` on every scope), Ubuntu 22.04.1, kernel 5.15.0-191-generic, cgroup v2 (user
delegation: memory, pids), OpenJDK 11.0.33+9 aarch64, G1 (shipped `jvm11-server.options`: `G1HeapRegionSize=16m`,
`MaxGCPauseMillis=300`, `G1NewSizePercent=50`, `InitiatingHeapOccupancyPercent=70`, `AlwaysPreTouch`). Checked 13:55 EST:
no java process, load 0.02, `/mydata` 36 GiB free. Build: `ms0617:/mydata/s4/u5-w4/tree` = copy of
`/mydata/s4/cassandra-base`, jar sha256 `e55f4f29…5a942` (as frozen), shipped `cassandra.yaml` md5 `714ee9bf…bba03` (as
frozen). Intervention tree `tree-I`: jar sha256 `80794e5b…e328bf9` (stock jar + `MultiCBuilder*.class` compiled from
[`harness/u5-pre-allocation-check.patch`](harness/u5-pre-allocation-check.patch), 2 methods patched as designed).
Resolved budgets read from every process command line: `-Xms/-Xmx` as listed, **`-XX:MaxDirectMemorySize=15872M`** (unset
`MAX_DIRECT_MEMORY_SIZE`, resolved by `cassandra-env.sh` as predicted), `-XX:OnOutOfMemoryError=kill -9 %p`,
`HeapDumpOnOutOfMemoryError` on at ≤ 4096M and off above. `yaml.diff` = the five directory lines only (arms A, I);
scope `MemoryMax` = heap + 6 GiB. Scope `memory.events` `oom 0 / oom_kill 0` in every lifetime, and the user-manager
parent's `oom_kill` count unchanged before/after (`logs/<label>/parent.memory.events.*`): **no kernel/cgroup OOM kill**.
Harness: [`harness/`](harness/) (`setup.sh`, `run-arm.sh`, `seq.sh`, `p3.sh`, `u5client.py`, `C2Sampler.java`,
`hprofstacks.py`, `hs_full.py`, `hprofhist.py`, `gcwin.py`, `summarize.py`, `pull-logs.sh`). Full run data on the node in
`ms0617:/mydata/s4/u5-w4/runs/<label>/` (gc.log, system/debug logs, stdout, samples, thread dumps, hprofs); small
excerpts in [`logs/<label>/`](logs/). Times are EST (the node logs MST = EST − 2 h; Cassandra logs UTC).

**Setup lifetimes.** `LOAD` (13:58–13:59): schema and the two rows, flush, drain, SIGTERM → `template-A` (1.2 MB).
`IC` (14:00): CK 4×4, 1×1,000, 64×1,000 and PK 4×4, 1×1,000 each returned **1 row** (0.03–0.63 s); EXECUTE bodies
107–8,563 B; baseline live heap after a full GC (`GC.class_histogram` total) **56.7 MiB** (predicted 100–250 MiB; lower
is harmless); JMX sampler, RssAnon and `memory.events` samplers present (jstat absent → A2).

**Condition CK, arm A and I, 2 GiB heap (P1).** One lifetime per row, each from a fresh copy of `template-A`; one
request. K = EXECUTE body bytes (≤ 16,777,216 checked by the client). Heap columns: JMX sampler maxima (heap used / G1
Old Gen used / old-gen post-GC), MiB; frozen during full GCs (A2). GC column: full GCs, max STW share in any 60 s,
longest window with ≥ 90 % STW (`gcwin.py`, whole JVM life).

| Lifetime | Arm | -Xmx / MaxDirect | Cond | k1 × k2 = N | K (B) | Client result | Latency s | Heap / old / old post-GC max | GC | Outcome |
|---|---|---|---|---|---|---|---|---|---|---|
| `CAL-CK-2G-4M` | A | 2G / 15872M | CK | 64 × 62,500 = 4,000,000 | 500,563 | ReadTimeout (0x1200) | 12.6 | 1813 / 1653 / 608 | 1, 0 %, 0 s | survived (built; read timed out) |
| `CAL-CK-2G-8M` | A | 2G / 15872M | CK | 64 × 125,000 = 8,000,000 | 1,000,563 | ReadTimeout (0x1200) | 18.8 | 1795 / 1363 / 805 | 3, 0 %, 0 s | survived (built; read timed out) |
| `CAL-CK-2G-16M` | A | 2G / 15872M | CK | 64 × 250,000 = 16,000,000 | 2,000,563 | conn_closed | 68.7 | 2032 / 1958 / 1622 | 7, 29 %, 0 s | **Java heap OOM** +43 s after `t_send` — in the **logging path**, not the build (below) |
| `T-CK-2G-1` | A | 2G / 15872M | CK | 64 × 1,000,000 = 64,000,000 | 8,000,563 | timeout (240 s) | 240.1 | 2025 / 2025 / 2025 | 81, **100 %**, **307 s** | GC spiral; **corrected (resumed session):** `Java heap space` thrown at ≈ +105 s (thread unknown: the dump file was created, 0 B, and the dump never ran); JVM not dead at window end |
| `T-CK-2G-2` | A | 2G / 15872M | CK | 64M | 8,000,563 | timeout (240 s) | 240.1 | 2034 / 2022 / 1996 | 85, **100 %**, **308 s** | not reached (time): GC spiral, no OOM (checked again: no OOM line in `stdout.log`) |
| `T-CK-2G-3` | A | 2G / 15872M | CK | 64M | 8,000,563 | conn_closed | 68.9 | 1920 / 1792 / 1336 | 3, 0 %, 0 s | **Java heap OOM** +22 s after `t_send`, in `elementsList` growth (below) |
| `T-CK-2G-4` (A4) | A | 2G / 15872M | CK | 64M | 8,000,563 | timeout (240 s) | 240.1 | 2031 / 2029 / 2029 | 66, **100 %**, **191 s** | GC spiral; **corrected:** **Java heap OOM ≈ +103 s on the NTR thread in `addEachElementToAll:368`** (dump written +183…+238 s); JVM not dead at window end |
| `T-CK-2G-5` (A4) | A | 2G / 15872M | CK | 64M | 8,000,563 | timeout (240 s) | 240.1 | 2038 / 2030 / 2000 | 66, **100 %**, **229 s** | GC spiral; **corrected:** `Java heap space` ≈ +178 s on a **background thread** (`CassandraDaemon` table-metrics task), not the NTR thread; JVM not dead at window end |
| `M-CK-2G-1` | A | 2G / 15872M | CK | 1 × 1,000,063 = 1,000,063 | 8,000,563 | **1 row** | 3.2 | 1305 / 297 / 0 | 0, 0 %, 0 s | survived |
| `M-CK-2G-2` | A | 2G / 15872M | CK | 1 × 1,000,063 | 8,000,563 | **1 row** | 3.2 | 1321 / 297 / 0 | 0, 0 %, 0 s | survived |
| `M-CK-2G-3` | A | 2G / 15872M | CK | 1 × 1,000,063 | 8,000,563 | **1 row** | 3.2 | 1321 / 313 / 0 | 0, 0 %, 0 s | survived |
| `I-CK-2G-1` | I | 2G / 15872M | CK | 64M | 8,000,563 | InvalidRequest (0x2200) "u5: IN cartesian product 64 x 1000000 exceeds 1100000" | 0.41 | 544 / 0 / 0 | 0, 0 %, 0 s | rejected, no OOM |
| `I-CK-2G-2` | I | 2G / 15872M | CK | 64M | 8,000,563 | same rejection | 0.40 | 512 / 0 / 0 | 0, 0 %, 0 s | rejected, no OOM |
| `I-CK-2G-3` | I | 2G / 15872M | CK | 64M | 8,000,563 | same rejection | 0.40 | 528 / 0 / 0 | 0, 0 %, 0 s | rejected, no OOM |
| `IM-CK-2G` | I | 2G / 15872M | CK | 1 × 1,000,063 | 8,000,563 | **1 row** | 3.2 | 1321 / 313 / 0 | 0, 0 %, 0 s | survived (useful work under I) |

Readings (CK, 2 GiB):
- **Reachability and the build.** Every T/CAL lifetime's `Thread.print` at `t_send` + 2 s and + 6 s shows the
  `Native-Transport-Requests-1` thread RUNNABLE in `MultiCBuilder$MultiClusteringBuilder.addEachElementToAll`
  (`MultiCBuilder.java:356`, the `elementsList.remove(0)` line) ← `SingleColumnRestriction$INRestriction.appendTo:241`
  ← `ClusteringColumnRestrictions.valuesAsClustering:110` ← `StatementRestrictions.getClusteringColumns:942` ←
  `SelectStatement.getRequestedRows:977` ← `makeClusteringIndexFilter:835` ← `getSliceCommands:725`
  ([`logs/T-CK-2G-1/ntr-t6.txt`](logs/T-CK-2G-1/ntr-t6.txt)). No control rejected or deferred any request in arm A (no
  guardrail line; K = 0.5–8.0 MB, far below the 16 MiB message limit and 51.2 MiB per-IP in-flight limit).
- **The heap fills from one request.** T lifetimes: first full GC ≈ 10–11 s after `t_send` (`2048M->1325M`, T-1;
  `2048M->1336M`, T-3), old gen at ≈ 2.0 GiB of 2 GiB from ≈ +20 s on; the matched control holds old-gen ≤ 313 MiB with
  **no** full GC; under the intervention the heap never leaves the young generation (≤ 544 MiB used, old 0).
- **T-CK-2G-3, the OOM (V5).** GC log: `GC(14) Pause Full (G1 Humongous Allocation) 1968M->1687M`, then `GC(15) Pause
  Full (G1 Humongous Allocation) 1687M->1687M` at uptime 48.6 s, then `HeapDumper` (`t_send` ≈ uptime 26.2 s →
  OOM ≈ +22 s); `stdout.log`: `java.lang.OutOfMemoryError: Java heap space`, `Heap dump file created [2990748255 bytes
  in 46.025 secs]`, `Executing /bin/sh -c "kill -9 194808"` ([`logs/T-CK-2G-3/oom-excerpt.txt`](logs/T-CK-2G-3/oom-excerpt.txt)).
  The hprof's stack for the thread holding the `OutOfMemoryError` ([`hprofstacks-oom-thread.txt`](logs/T-CK-2G-3/hprofstacks-oom-thread.txt)):
  `OutOfMemoryError.<init>` ← `Arrays.copyOf` ← `ArrayList.grow:238/243` ← `ArrayList.add:486/499` ←
  **`MultiCBuilder$MultiClusteringBuilder.addEachElementToAll:359`** (`elementsList.add(newComposite)`) ←
  `INRestriction.appendTo:241` ← `ClusteringColumnRestrictions.valuesAsClustering:110` ← … `SelectStatement.getSliceCommands:725`
  ← `ExecuteMessage.execute` ← `Dispatcher.processRequest`: the `elementsList` backing array could not grow (a humongous
  `Object[]`), i.e. the **claimed holder, in the predicted frame**.
- **T-CK-2G-1, -2, -4, -5, the spiral.** The same build fills the old gen, then G1 runs back-to-back
  `Pause Full (G1 Evacuation Pause) 2035M->2035M(2048M)` of ≈ 3.3 s each (T-1: 81 full GCs, 236 s of pauses in the
  window; T-2: 85; T-4: 66; T-5: 66). Each full GC frees only the small garbage the loop makes per composite
  (the one-slot `Object[]` replaced when `ArrayList.add` grows a new composite), so the loop advances a little and never
  reaches the next `elementsList` growth (the step that throws in T-3); G1 in JDK 11 has no GC-overhead limit, so no
  `OutOfMemoryError` is thrown. **Service-loss criterion (≥ 90 % STW over ≥ 60 s) met in 4/4** (100 % over 191–308 s);
  the client times out at 240 s with no response; the JVM is still in the spiral when stopped (SIGKILL after 30 s of
  SIGTERM, all four). Which branch a lifetime takes (OOM at the growth vs. spiral before it) depends on G1's timing and
  heap layout at the growth point (`elementsList` capacity steps 31.2M → 46.7M entries, ≈ 1.6–2.0 GiB live at that point
  on a 2 GiB heap).
  **Correction (resumed session, 2026-11-18 18:40 EST): "no `OutOfMemoryError` is thrown" is wrong for three of the four.**
  The harness outcome looked only at JVM death and the client; `stdout.log` and the hprof files show that the spiral
  ends in a thrown `Java heap space` error in T-1, T-4 and T-5, inside the window, but the JVM's post-OOM steps (the
  `HeapDumper` VM operation, then `ReportJavaOutOfMemory` → `kill -9`) wait behind the back-to-back full GCs, so none of
  them died before the harness stopped it. See "Resumed session" at the end of §3 for times and stacks.
- **CAL-CK-2G-16M, a different holder.** The build **completed** (old-gen post-GC 1.62 GiB), the names-filter read
  timed out, and the NTR thread OOMed in `StorageProxy.logRequestException:2695` → `NoSpamLogger` → logback
  `StringBuilder.append` → `Arrays.copyOf` ([`logs/CAL-CK-2G-16M/oom-thread-full.txt`](logs/CAL-CK-2G-16M/oom-thread-full.txt)).
  The message is `ReadTimeoutException … while executing SELECT * FROM u5.ck WHERE pk = 0 AND (c1, c2) IN ((0, 0), (0, 1),
  …` with every requested clustering (`logs/CAL-CK-2G-4M/monitor-guard-excerpt.txt` shows the same line at 4M, which
  survived). That is the ledgered rendering path (protection map row "Slow/failed-query monitor"; here the request-
  exception logger, same `toCQLString` rendering), **not this case's endpoint** (verdict rules) → A3.
- **Matched control.** Same 1,000,064 values and 8,000,563 B: 1 row in 3.2 s, 3/3, old-gen ≤ 313 MiB, no full GC, no
  service loss. The multiplication, not the request size, fills the heap.
- **Intervention.** The pre-allocation check rejects the T request 3/3 in ≈ 0.4 s with no product built; `IM` serves the
  M request (1 row) under the same patch.

**Budget search, condition CK (P2).**

| Lifetime | Arm | -Xmx / MaxDirect | k1 × k2 = N | K (B) | Client result | Latency s | Heap / old / old post-GC max | GC | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| `CAL-CK-4G` | A | 4096M / 15872M | 128 × 1,000,000 = 128,000,000 | 8,001,075 | timeout (420 s) | 420.1 | 4065 / 4049 / 4049 | 70, **100 %**, **489 s** | not reached (time): GC spiral (`4073M->4057M(4096M)` full GCs of ≈ 6 s), no OOM |
| `CAL-CK-8G` | A | 8192M / 15872M | 160 × 1,600,000 = 256,000,000 | 12,801,331 | conn_closed | 159.4 | 8092 / 7971 / 7971 | 6, **92 %**, **61 s** | **Java heap OOM** ≈ +158 s: `Pause Full (G1 Humongous Allocation) 8014M->8014M(8192M)` then `ReportJavaOutOfMemory`; no dump (> 4096M by design); NTR thread in `addEachElementToAll:356` at +6 s |

The 4 GiB point ends like four of the five 2 GiB T lifetimes (spiral at the heap ceiling, no throw in 420 s); the
8 GiB point throws at a humongous allocation after ≈ 60 s of ≥ 90 % STW (the failing allocation is not attributable
without a dump; the only running request is in `addEachElementToAll` at +6 s and old-gen holds 7.97 GB at the end).

**CK boundary points run after P3 (A3; boundary readings, not V-items).**

| Lifetime | Arm | -Xmx | k1 × k2 = N | K (B) | Client result | Latency s | Heap / old / old post-GC max | GC | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| `CAL-CK-2G-24M` | A | 2G | 64 × 375,000 = 24,000,000 | 3,000,563 | timeout (240 s) | 240.1 | 2018 / 2020 / 2020 | 80, **100 %**, **302 s** | not reached (time): GC spiral, no OOM |
| `CAL-CK-2G-32M` | A | 2G | 64 × 500,000 = 32,000,000 | 4,000,563 | conn_closed | 88.7 | 1965 / 1949 / 1949 | 5, 35 %, 0 s | **Java heap OOM +35.7 s** after `Pause Full (G1 Humongous Allocation) 1974M->1974M(2048M)`; OOM thread: `Arrays.copyOf` ← **`BTree$Builder.add:1539`** ← `BTreeSet$Builder.add:604` ← **`MultiCBuilder$MultiClusteringBuilder.build:435`** ← `ClusteringColumnRestrictions.valuesAsClustering:118` ← `getClusteringColumns:942` ← `SelectStatement.getRequestedRows:977` ([`oom-thread-full.txt`](logs/CAL-CK-2G-32M/oom-thread-full.txt)): the product's second stage (the `BTreeSet<Clustering>` builder's backing array), dump deleted after the stack was saved |

With the 16M logging-path OOM, the 2 GiB CK picture is: 4M and 8M build and answer (read timeout); 16M builds and dies
in the logger; 24M spirals; 32M completes `elementsList` and throws in `build()` at the `BTree.Builder` array doubling;
64M spirals 4/5 and throws 1/5 at the `elementsList` growth (corrected below: an error is thrown later in the spiral in 3 of
those 4: once on the request thread in the build frames, once on a background thread, once unattributed). Both throws are failed **humongous** allocations (an
`Object[]` growth step of the product's own containers). Between growth steps the remaining allocations are small
(≈ 24–48 B), so G1 keeps reclaiming crumbs and spirals instead of throwing. The `elementsList` capacity steps (k1 = 64;
JDK 11 growth ×1.5 from 73) are …, 13,845,150, 20,767,725, **31,151,587**, 46,727,380, …. The `T-CK-2G-3` dump ends
exactly at the 31.15M → 46.7M step (`elementsList` length 31,151,587; the step needs a 178 MiB `Object[]` next to
≈ 1.7 GiB of live composites). Whether a lifetime throws or spirals depends on whether the heap ceiling arrives at
such a step.

**Condition PK, arm A and I, 2 GiB heap (P3; driver `harness/p3.sh`).**

| Lifetime | Arm | -Xmx / MaxDirect | k1 × k2 = N | K (B) | Client result | Latency s | Heap / old / old post-GC max | GC | Outcome (OOM time from `t_send`, GC log) |
|---|---|---|---|---|---|---|---|---|---|
| `CAL-PK-2G-1M` | A | 2G / 15872M | 16 × 62,500 = 1,000,000 | 500,171 | ReadTimeout (0x1200) | 5.0 | 1008 / 12 / 0 | 0, 0 %, 0 s | survived (built; reads of 1M empty partitions timed out) |
| `CAL-PK-2G-2M` | A | 2G / 15872M | 16 × 125,000 = 2,000,000 | 1,000,171 | ReadTimeout | 7.0 | 1017 / 505 / 0 | 0, 0 %, 0 s | survived |
| `CAL-PK-2G-4M` | A | 2G / 15872M | 16 × 250,000 = 4,000,000 | 2,000,171 | ReadTimeout | 13.8 | 2000 / 1536 / 1009 | 1, 0 %, 0 s | survived |
| `CAL-PK-2G-8M` | A | 2G / 15872M | 16 × 500,000 = 8,000,000 | 4,000,171 | conn_closed | 165.2 | 2007 / 2007 / 2007 | 35, 100 %, 81 s | **Java heap OOM +90 s** (first OOM → N_T-PK = 8M, as predicted) |
| `T-PK-2G-1` | A | 2G / 15872M | 8M | 4,000,171 | conn_closed | 213.2 | 2016 / 2016 / 2016 | 55, 100 %, 86 s | **Java heap OOM +75 s** |
| `T-PK-2G-2` | A | 2G / 15872M | 8M | 4,000,171 | conn_closed | 165.8 | 1991 / 1991 / 1991 | 35, 93 %, 66 s | **Java heap OOM +76 s** |
| `T-PK-2G-3` | A | 2G / 15872M | 8M | 4,000,171 | conn_closed | 203.6 | 2032 / 2032 / 2032 | 51, 100 %, 131 s | **Java heap OOM +133 s** |
| `M-PK-2G-1` | A | 2G / 15872M | 1 × 500,015 = 500,015 | 4,000,171 | ReadTimeout | 5.1 | 848 / 0 / 0 | 0, 0 %, 0 s | survived (built; read timed out, as allowed by the prediction) |
| `M-PK-2G-2` | A | 2G / 15872M | 1 × 500,015 | 4,000,171 | ReadTimeout | 5.1 | 832 / 0 / 0 | 0, 0 %, 0 s | survived |
| `M-PK-2G-3` | A | 2G / 15872M | 1 × 500,015 | 4,000,171 | ReadTimeout | 5.1 | 816 / 0 / 0 | 0, 0 %, 0 s | survived |
| `I-PK-2G-1` | I | 2G / 15872M | 8M | 4,000,171 | InvalidRequest "u5: IN cartesian product 16 x 500000 exceeds 1100000" | 0.29 | 480 / 0 / 0 | 0, 0 %, 0 s | rejected, no OOM |
| `I-PK-2G-2` | I | 2G / 15872M | 8M | 4,000,171 | same rejection | 0.30 | 496 / 0 / 0 | 0, 0 %, 0 s | rejected, no OOM |
| `I-PK-2G-3` | I | 2G / 15872M | 8M | 4,000,171 | same rejection | 0.29 | 448 / 0 / 0 | 0, 0 %, 0 s | rejected, no OOM |

Readings (PK, 2 GiB):
- **Path.** `Thread.print` at +2 s / +6 s: NTR thread in `MultiCBuilder$MultiClusteringBuilder.build:435` →
  `CBuilder$ArrayBackedBuilder.buildWith:179`, then `PartitionKeySingleRestrictionSet.toByteBuffers:67-68`
  (`ClusteringPrefix.validate` / `serializeAsPartitionKey`), under `PartitionKeySingleRestrictionSet.values:101` ←
  `StatementRestrictions.getPartitionKeys:813` ([`logs/T-PK-2G-1/ntr-t2.txt`](logs/T-PK-2G-1/ntr-t2.txt)).
- **OOM thread (V5), all four dumps** (CAL-PK-2G-8M, T-PK-2G-1..3, [`oom-thread-full.txt`](logs/T-PK-2G-1/oom-thread-full.txt)):
  `OutOfMemoryError.<init>` ← **`SinglePartitionReadCommand.create:149`** ← `create:187` ← `create:222` ←
  `SinglePartitionReadCommand$Group.create:1283` ← `SinglePartitionReadQuery.createGroup:56` ←
  **`SelectStatement.getSliceCommands:737`** ← `getQuery:414` ← `execute:332` ← … `ExecuteMessage.execute` ←
  `Dispatcher.processRequest`: one read command per key, all created before any read.
- **Holder (V3/V5), `T-PK-2G-1` histogram** ([`logs/T-PK-2G-1/hprofhist.txt`](logs/T-PK-2G-1/hprofhist.txt); hprof shallow
  sizes use 8-byte ids, so they over-count the compressed-oop heap): `SinglePartitionReadCommand` **5,949,738** (777 MiB),
  `HeapByteBuffer` 8,008,511 (420 MiB), `PreHashedDecoratedKey` **8,000,047** (366 MiB), `byte[14]` (serialized
  composite keys) **8,000,978** (244 MiB), `Murmur3Partitioner$LongToken` 8,000,159 (183 MiB), `Bounds` and `DataRange`
  5,949,7xx each (182 MiB each), two `Object[8,000,000]` (61 MiB, the key lists); `ArrayList` only 2,392 (the
  `MultiCBuilder` product is garbage by then). These per-key classes are ≈ 97 % of the 2,461 MiB shallow total. The
  request died at command 5,949,738 of 8,000,000.
- **Lifetime of the failure.** Each T-PK lifetime spends 66–131 s at ≥ 90 % STW (full GCs `2039M->2039M`) before the
  allocation that throws; `HeapDumper` → `ReportJavaOutOfMemory` (`kill -9`) after a 90–137 s dump. OOM 3/3 at N_T-PK
  (and 4/4 counting `CAL-PK-2G-8M`).
- **Matched control** (same 500,016 values and 4,000,171 B, product additive: 500,015 keys): the reads of 500,015 empty
  partitions time out after 5 s, 3/3; old-gen 0 MiB, no full GC, no OOM. **Intervention**: rejected 3/3 in 0.29 s, heap
  ≤ 496 MiB, no product built.

**P4 (run by the first stage-2 session 15:18–16:08 EST; written up by the resumed session).** Sequencer
`seq-A3-P4` (after the A3 points), then `harness/rep.sh` (REP at the largest failing heap: `CAL-CK-auto` did not OOM,
so 8192M). All lifetimes ran to their end before the suspension (the last, `REP-8192M-2`, ended 16:08:23 EST). Scope
`memory.events` `oom 0 / oom_kill 0` in every lifetime. Logs: [`logs/<label>/`](logs/).

| Lifetime | Arm | -Xmx / MaxDirect | k1 × k2 = N | K (B) | Client result | Latency s | Heap / old / old post-GC max | GC (full GCs, max 60 s STW, longest ≥ 90 % window) | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| `CAL-CK-15872M` | A | 15872M / 15872M | 200 × 1,600,000 = 320,000,000 | 12,801,651 | timeout (900 s) | 900.2 | 15841 / 15798 / 15798 | 28, **100 %**, **738 s** | not reached (time): spiral (`15826M->15810M(15872M)` full GCs of ≈ 23.7 s), no OOM line; NTR in `addEachElementToAll:356` at +6 s |
| `LOADG` | — | 2G | template-G: `PasswordAuthenticator`, role `u5` (LOGIN, not superuser), schema + 2 rows | — | — | — | — | — | loaded (setup, not a reading) |
| `G-CK-2G-64M-1` | G | 2G / 15872M | 64 × 1,000,000 = 64M | 8,000,563 | timeout (240 s) | 240.1 | 2024 / 2025 / 2025 | 65, **100 %**, 148 s | **Java heap OOM ≈ +91 s on the NTR thread**: `Arrays.copyOf` ← `ArrayList.<init>` ← `MultiCBuilder$MultiClusteringBuilder.addEachElementToAll:358` ← `INRestriction.appendTo:241` ← `ClusteringColumnRestrictions.valuesAsClustering:110` ([`oom-thread-full.txt`](logs/G-CK-2G-64M-1/oom-thread-full.txt)); dump +144…+199 s; JVM not dead at window end (harness outcome said `SURVIVED`; corrected) |
| `G-CK-2G-64M-2` | G | 2G / 15872M | 64M | 8,000,563 | conn_closed | 165.8 | 2021 / 2021 / 2021 | 46, **100 %**, 170 s | **Java heap OOM**; first error ≈ +117 s on the **JMX `ServerCommunicatorAdmin` timeout thread** (the sampler's JMX connection; [`oom-thread-full.txt`](logs/G-CK-2G-64M-2/oom-thread-full.txt)); at +164 s a full GC dropped the heap `2032M->63M` (the product was released), then the 94 MB dump and `kill -9` at +165 s |
| `G-CK-2G-Nf` | G | 2G / 15872M | 64 × 250,000 = 16M | 2,000,563 | **InvalidRequest (0x2200)** "Guardrail in_select_cartesian_product violated: … produces 16000000 values, this exceeds fail threshold of 1000000." | 6.5 | **1298 / 626** / 0 | 0, 0 %, 0 s | rejected by the guardrail after 6.5 s, **after** the 16M product was built (NTR in `addEachElementToAll:356` at +2 s; heap 1.27 GiB, old 626 MiB at rejection) |
| `CAL-CK-auto` | A | **31744M (auto)** / 15872M | 400 × 1,600,000 = 640,000,000 | 12,803,251 | timeout (900 s) | 900.1 | 31668 / 31615 / 31615 | 9, **100 %**, **337 s** | not reached (time): spiral (`31727M->31662M(31744M)` full GCs of ≈ 48 s), no OOM line; NTR in `addEachElementToAll:356` at +6 s |
| `REP-8192M-1` | A | 8192M / 15872M | 160 × 1,600,000 = 256M | 12,801,331 | conn_closed | 158.8 | 8075 / 7999 / 7999 | 6, 91 %, 60 s | **Java heap OOM** ≈ +158 s: `Pause Full (G1 Humongous Allocation) 8016M->8014M`, `8014M->8014M(8192M)`, `ReportJavaOutOfMemory`, `kill -9`; no dump (> 4096M by design) |
| `REP-8192M-2` | A | 8192M / 15872M | 256M | 12,801,331 | conn_closed | 159.2 | 8091 / 7970 / 7970 | 6, 92 %, 61 s | **Java heap OOM** ≈ +159 s, the same sequence (`8106M->8014M`, `8014M->8014M`, `ReportJavaOutOfMemory`) |

Readings (P4):
- **Budget search, CK.** 8192M (256M): heap OOM **3/3** (`CAL-CK-8G`, `REP-8192M-1`, `-2`), each the same sequence at
  +158–160 s: old gen at ≈ 7.8 GiB, two `G1 Humongous Allocation` full GCs that free nothing (`8014M->8014M`), then
  `ReportJavaOutOfMemory` and `kill -9`; the only humongous allocator in the build is the `elementsList` /
  `BTree.Builder` backing array, but no dump exists at this heap, so the thread is inferred. 4096M (128M), 15872M (320M)
  and 31744M (640M, ms0617's automatic heap) all fill the heap and spiral (full GCs of 6 s, 24 s, 48 s) without an OOM
  line in their windows (420 s, 900 s, 900 s). **Largest heap with a reached OOM: 8192M (3/3).** The larger heaps reach
  service loss (≥ 90 % STW for 489–738 s), not an OOM, within their windows.
- **Arm G (diagnostic, late guardrail, not a V-item).** With the shipped guardrail on (fail 1,000,000) for an ordinary
  user, the 16M request is rejected, but only after its whole product was built (1.27 GiB heap, 6.5 s): U ≈ 16M
  composites against C = 1M, K = 16M reported in the message — **bypass by late enforcement** (the check runs after each
  column's product, `ClusteringColumnRestrictions.java:113`). The 64M request never reaches the check: OOM 2/2 (one on
  the NTR thread in the build frame, one first on the JMX thread with the heap full of the product). Prediction met
  (OOM 2/2 with the guardrail on; Nf rejected).

**Resumed session (2026-11-18, 18:20–18:50 EST; fresh session after the wave's suspension at 16:08).**
- **State found.** No process on ms0617 (load 0.02). §1–§2 hash re-checked (`c9634d84…ea60`, matches). Every lifetime
  of the frozen plan (P1–P4 including `REP`) had ended before the suspension with complete driver logs (`END` line,
  outcome, `small/` excerpts); none is incomplete, so **nothing was re-run**. Reused as is: `tree`, `tree-I`,
  `template-A`, `template-G`, all of `runs/`. Pulled the missing excerpts (`logs/REP-8192M-1`, `logs/REP-8192M-2`).
- **Re-reading the spiral lifetimes.** The `outcome` files say `SURVIVED` for T-1, T-4, T-5 and G-64M-1, but their
  `stdout.log` holds `java.lang.OutOfMemoryError: Java heap space` / `Dumping heap to …` (excerpts `late-oom-stdout.txt`)
  and hprof files exist. OOM time = dump start (hprof mtime − the JVM's "created in N secs"; for T-1 the 0-byte file's
  creation time), checked against the preceding `StatusLogger` lines; the gc.log `HeapDumper` safepoint gives when the
  dump actually ran:

  | Lifetime | OOM thrown (from `t_send`) | `HeapDumper` ran | Thread holding the `OutOfMemoryError` (`harness/hs_full.py`) |
  |---|---|---|---|
  | `T-CK-2G-1` | ≈ +105 s | never (0-byte file; SIGKILL at +290 s) | unknown (no dump) |
  | `T-CK-2G-2` | — (no OOM line) | — | — |
  | `T-CK-2G-4` | ≈ +103 s | +183 s (done +238 s) | **NTR**: `Arrays.copyOf` ← `ArrayList.grow` ← `ArrayList.add` ← **`addEachElementToAll:368`** (`newComposite.add`) ← `INRestriction.appendTo:241` ← `valuesAsClustering:110` ← `getClusteringColumns:942` ← `getRequestedRows:977` ← `makeClusteringIndexFilter:835` ← `getSliceCommands:725` ← … `Dispatcher.processRequest` ([`oom-thread-full.txt`](logs/T-CK-2G-4/oom-thread-full.txt)) |
  | `T-CK-2G-5` | ≈ +178 s | +218 s (done +273 s) | **background**: `Collections.unmodifiableCollection` ← `Keyspace.getColumnFamilyStores:212` ← `CassandraDaemon.lambda$static$0:194` (periodic table-metrics task, `ScheduledThreadPoolExecutor`) ([`oom-thread-full.txt`](logs/T-CK-2G-5/oom-thread-full.txt)) |
  | `G-CK-2G-64M-1` | ≈ +91 s | +144 s (done +199 s) | NTR, `addEachElementToAll:358` (above) |
  | `G-CK-2G-64M-2` | ≈ +117 s | +164 s | JMX `ServerCommunicatorAdmin$Timeout.run` (above) |

  So in the 2 GiB CK spiral, G1 does eventually fail an allocation (a small one: a per-composite array, or any other
  thread's allocation) and throws, ≈ 90–180 s after `t_send`; the throwing thread is whichever thread allocates at that
  moment. The JVM then needs two more VM operations (heap dump, then the OOM report that runs `kill -9`), and those wait
  behind the back-to-back full GCs of the other threads (T-1: > 185 s without the dump starting), so the node stays in
  the spiral and does not exit. The design's endpoint "JVM killed by `OnOutOfMemoryError`" happened in the window only in
  T-3 (and, outside the T arm, in G-64M-2).
- **Histograms of the two new dumps** (`harness/hprofhist.py`, under `nice -n 19`, no lifetime running): `T-CK-2G-4` ([`hprofhist.txt`](logs/T-CK-2G-4/hprofhist.txt)): 37,290,260 `ArrayList` (1,138 MiB) + 37,289,381 `Object[2]`
  (854 MiB) + one `Object[46,727,380]` (178 MiB, the `elementsList` after its 31.15M → 46.7M growth) ≈ **94 %** of the
  2,311 MiB shallow total; `T-CK-2G-5` ([`hprofhist.txt`](logs/T-CK-2G-5/hprofhist.txt)): 37,231,926 `ArrayList` +
  37,231,045 `Object[2]` + the same 46,727,380-slot array ≈ 94 % of 2,308 MiB. Both had passed the growth step at which
  `T-CK-2G-3` died (31,151,587 entries) and filled the heap at ≈ 37.2M composites (58 % of 64M): the claimed holder, also
  in `T-CK-2G-5`, whose throwing thread was a background task.
- **hprof housekeeping (design: at most three on disk).** Kept on the node: `T-CK-2G-3`, `T-CK-2G-4` (the two NTR-thread CK OOMs) and `T-PK-2G-1`. Deleted
  18:39 EST after their stacks (and for T-5 the histogram) were saved: `T-CK-2G-5`, `G-CK-2G-64M-1`, `G-CK-2G-64M-2` and
  `T-CK-2G-1` (0 B) ([`logs/hprof-deletions-and-seq.txt`](logs/hprof-deletions-and-seq.txt)).
- **Processes.** The resumed session started only the two `hprofhist.py` parsers (pids 247754, 247756, exited by
  themselves 18:38 EST). Nothing of this case runs on ms0617.

## 4. Conclusion (stage 2)

*Written by the first stage-2 session (before the 16:08 EST suspension) and completed and corrected by the resumed session (2026-11-18,
18:20–18:50 EST): P4 added; the CK 2 GiB OOM counts corrected after re-reading `stdout.log` and the dumps (§3,
"Resumed session").*

**Verdict: `retry`** (CK decides the case. Frozen verdict rules: "true positive" needs the `T-CK-2G` heap OOM in ≥ 3
runs **with the initiating thread = the NTR thread in the CK build frames**; that holds in 2 of 5. "Retry: OOM in fewer
than 3 of 5 runs … service loss without OOM").

| Condition | Status (detail) | n/N | Direction |
|---|---|---|---|
| **CK** (`pk = ? AND c1 IN (64) AND c2 IN (1,000,000)`, 2 GiB, defaults) | **`verified-gap · service-loss · deployment`** (an OOM status needs ≥ 3 attributed OOMs) | heap fills 5/5; `Java heap space` thrown in the window **4/5**; thrown **on the NTR thread in the build frames 2/5** (`T-CK-2G-3` +22 s, `T-CK-2G-4` ≈ +103 s); background thread 1/5 (`T-CK-2G-5`); unknown 1/5 (`T-CK-2G-1`); JVM exit in the window 1/5; service loss (≥ 90 % STW ≥ 60 s) 4/5 | unprotected configuration (guardrail shipped off, and skipped for AllowAll clients) |
| **CK at 8 GiB** (160 × 1,600,000 = 256M, defaults; budget search + REP) | `reproduced`-level evidence only (no matched control, intervention or dump at this budget) | heap OOM **3/3** at +158–160 s, JVM exit 3/3 | same |
| **PK** (`a IN (16) AND b IN (500,000)` on a composite partition key, 2 GiB, defaults) | **`verified-OOM · deployment`** | heap OOM **3/3** (+ 1/1 calibration), NTR thread in `SinglePartitionReadCommand.create` ← `getSliceCommands` | unprotected configuration |
| CK budget search | heap OOM at **8192M (3/3)**; spiral, no OOM in the window, at 4096M (128M), 15872M (320M), 31744M auto (640M) | 1 run each (8192M: 3) | — |
| Arm G (guardrail on, diagnostic) | **bypass by late enforcement**: 16M rejected only after its product was built (1.27 GiB); 64M OOM 2/2 before the check | 1 + 2 runs | late check |

**V1–V7.**

| | CK, 2 GiB (status `verified-gap · service-loss`) | PK, 2 GiB (status `verified-OOM`) |
|---|---|---|
| V1 Repetition | service loss 4/5 (`T-CK-2G-1,2,4,5`: 100 % STW over 191–308 s); heap OOM on the NTR thread in the claimed frames **2/5** (`T-3`, `T-4`) → fails V1 for an OOM status under the frozen rule; any-thread `Java heap space` 4/5 | OOM 3/3 (`T-PK-2G-1..3`) |
| V2 Matched control | `M-CK-2G-1..3`: 1 row in 3.2 s, old-gen ≤ 313 MiB, 0 full GCs (same 1,000,064 values, 8,000,563 B) | `M-PK-2G-1..3`: read timeout at 5 s, old-gen 0, no OOM (same 500,016 values, 4,000,171 B) |
| V3 Measurement (U independent of K) | GC log heap after GC (`2035M->2035M(2048M)`), JMX old gen; `T-CK-2G-3` dump: 31,153,975 `ArrayList` + 31,153,070 `Object[2]` + the 31,151,587-slot `elementsList` array ≈ 92 % of the dump; `T-CK-2G-4` / `-5` dumps: 37.3M / 37.2M `ArrayList` + `Object[2]` + the 46.7M-slot `elementsList` array ≈ 94 % each; K = 8.0 MB request bytes | `T-PK-2G-1` dump: 8.0M `PreHashedDecoratedKey`/`LongToken`/`byte[14]`/`HeapByteBuffer`, 5.95M `SinglePartitionReadCommand` ≈ 97 %; K = 4.0 MB |
| V4 Intervention | `I-CK-2G-1..3`: rejected in 0.4 s, heap ≤ 544 MiB; `IM-CK-2G`: 1 row (useful work kept) | `I-PK-2G-1..3`: rejected in 0.3 s, heap ≤ 496 MiB |
| V5 Initiating failure | service loss: GC log over the windows; OOMs: `ArrayList.grow` ← `addEachElementToAll:359` (T-3), `:368` (T-4) + T-3 histogram; T-5: a background thread; T-1: no dump | `SinglePartitionReadCommand.create:149` ← `SelectStatement.getSliceCommands:737` (4/4 dumps) + histogram |
| V6 Default constraints | all shipped (`in_select_cartesian_product_*` −1, `partition_keys_in_select_*` −1, AllowAll, message/frame 16 MiB, in-flight heap/10 and heap/40, NTR 128, timeouts) | same |
| V7 Acceptable budget | heap 2 GiB (standing rule: ideal), direct 15872M resolved, no container budget | same |

**Reason.** The mechanism is confirmed in both conditions: nothing at defaults counts the IN cartesian product, and one
request of 4–8 MB fills a 2 GiB heap with per-combination objects (amplification ≈ 250–500× per request byte). The
matched controls (same values, same bytes, additive product) stay below 0.32 GiB of old gen, and a check before
allocation removes the failure 6/6 (CK and PK). PK ends in a request-thread heap OOM 3/3 and is `verified-OOM ·
deployment` on its own. CK, which the frozen rules make decide the case, behaves differently: its build is a long run of
small allocations, so on a full 2 GiB heap G1 keeps finding a few bytes per full GC and spirals. A `Java heap space`
error came in 4 of 5 runs, but at +22 s to +178 s and from whichever thread allocated at that moment: the request
thread in the build frames in only 2 runs (`T-CK-2G-3` at the 31.15M → 46.7M `elementsList` growth, `T-CK-2G-4` at a
per-composite array), a table-metrics task in `T-CK-2G-5` (its dump still shows the claimed holder, ≈ 94 % of the heap), unknown in
`T-CK-2G-1`; `T-CK-2G-2` threw nothing in 240 s.
And only `T-CK-2G-3` died: elsewhere the dump and `kill -9` waited behind the spiral, so the node stayed in 100 % STW
(service loss 4/5). That is 2/5 against the frozen "≥ 3 on the NTR thread", hence `retry` with `verified-gap ·
service-loss · deployment` for CK. The larger budgets show the same split: at 8 GiB (256M) the OOM is regular, 3/3 at
+158–160 s after two failed humongous-allocation full GCs, while 4 GiB, 15.5 GiB and the automatic 31 GiB heap spiral
without an OOM inside 420–900 s. With the guardrail switched on (arm G), enforcement is late: a 16M product is fully
built (1.27 GiB) before the rejection and a 64M product OOMs before the check (2/2). The `CAL-CK-2G-16M` OOM was in the
request-exception logger rendering every requested clustering (`StorageProxy.logRequestException`), a ledgered
secondary holder, not this endpoint.

**What a better design should change (retry row).** (1) Pre-register CK at the budget where its OOM is regular:
**8 GiB heap, `c1 IN (160) AND c2 IN (1,600,000)`** (OOM 3/3 here, +158–160 s, JVM exit each time), with its matched
control (1 × 1,600,159 values) and the pre-allocation intervention at 8 GiB, ×3 each, and keep the OOM thread
attributable there (`HeapDumpOnOutOfMemoryError` on, ≈ 8.5 GB per dump, keep one; or a `jcmd Thread.print` triggered by
the first `G1 Humongous Allocation` full GC). (2) Or at 2 GiB use **N = 32M (64 × 500,000)**, where the throw lands on a
humongous growth step of the product (`CAL-CK-2G-32M`: `BTree.Builder` array, +36 s, 1/1), with ≥ 3 repetitions.
(3) State in the frozen rule how a thrown OOM is counted: any thread, with the dump showing the claimed holder
≥ 50 % of the heap (CK here would then be 3/5: T-3, T-4, T-5, with T-1 unattributed), versus the request thread only; and score "error thrown" and "JVM exit" separately (the spiral
delays `OnOutOfMemoryError` by minutes), with the window extended past the dump. (4) Keep PK, already
`verified-OOM · deployment`. The write-side twins (OC-352 / OC-276) remain U7's and a batch case's.

**Limits of attribution.** The hprof shallow sizes count references as 8 B (the heap uses compressed oops), so the
class percentages are upper bounds. The JMX sampler stalls during full GCs (A2), so the GC log is the U source there.
At 8 GiB and above there are no dumps (by design), so the 8 GiB OOMs' failing allocation is inferred (the GC cause is
`G1 Humongous Allocation`, the only request was in `addEachElementToAll` at +6 s, old gen ≈ 7.8 GiB). OOM times in the
spiral lifetimes come from the dump start (file times and the JVM's dump duration), ±15 s. The sampler's own JMX
connection is one of the threads that can take the first `OutOfMemoryError` (`G-CK-2G-64M-2`), and the harness
`outcome` file looked only at JVM death, which is why the first write-up missed the late throws.
