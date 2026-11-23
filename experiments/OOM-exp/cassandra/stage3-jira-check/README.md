# Cassandra — stage 3-a JIRA check (snapshot 2026-11-23)

Rules: [`../../oom-agent-playbook.md`](../../oom-agent-playbook.md#stage-3-a--jira-check) (added 2026-11-23). Every Cassandra
**true positive** of stage 2 (30 cases; false positives and retries excluded by the owner) was checked read-only against
Apache JIRA (`project = CASSANDRA`, REST API, requests ≥ 2 s apart, 340 JQL queries in all, each logged with its hit count
in the case's file). Fix commits were tested against `cassandra-5.0.9` in a blobless clone of apache/cassandra (trunk to
2026-11-21); docs were read at the pinned 5.0.9 source. Four fresh agents, one per area; nothing was posted to JIRA.
The 2026-11-16 prior-art check of B6, C1, C2, S1, S2, R1-V
([`jira-prior-art-verified-cases.md`](../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-prior-art-verified-cases.md))
was re-run under these rules, not copied.

## Counts

*Updated 2026-11-23 with the owner's rulings (B8, R13, R21; see below).*

| | Cases |
|---|---|
| True positives checked | **30** |
| **Mentioned in JIRA** (exact or partial match) | **13 / 30 (43 %)** — exact 6, partial 7 |
| · still open | 10 (exact: C2, R14, B19, U9, B23; partial: S1, S2, R22, U15, U14) |
| · fixed upstream, fix not in 5.0.9 | 2, partial (U10 and B20: CASSANDRA-11745, 6.0-alpha3) |
| · fixed in 5.0.9 but the fix does not cover it (`known-fixed (incomplete)`) | 1, exact (B8: CASSANDRA-8639 bounds serialized bytes, not heap) |
| Not mentioned, but fixed incidentally in a newer version | 1 (R21: CASSANDRA-20780, 6.0/trunk) |
| Not mentioned, but the shipped docs warn (`documented only`) | 3 (R1-V, R18, U12) |
| **New** (no exact/partial issue, no fix, no doc warning) | **13 / 30** — B6, C1, C9, R12, R13, R20, U7, U8, B16, B17, B21, U13, C10 |
| Docs warn at all (with or without an issue), source labelled in each file | 4 fully (R1-V, R18, U12, R14), 2 partly (U9, B16) |

Label totals: known-open 10, known-fixed (not in 5.0.9) 3 (U10, B20, R21), known-fixed (incomplete) 1 (B8), documented only 3,
new 13.

## Per case

| Case | Label | Best match | Issues (state, match) | Documented (source) |
|---|---|---|---|---|
| [B6](B6.md) | new | related | none exact/partial; related CASSANDRA-15066 (Fixed 4.0), CASSANDRA-8639 (Fixed 3.2, same ratio on CL replay), CASSANDRA-9318 (Fixed 3.10, removed 4.0), CASSANDRA-7402 (Open) | no (cassandra.yaml:1371-1372 only states the unit: "These limits are applied to the on-wire size of the message being sent or received."; no heap warning) |
| [C2](C2.md) | known-open | exact | CASSANDRA-11082 (Open, exact); related CASSANDRA-15013 (Fixed, in 5.0.9), CASSANDRA-21508 (Fixed 5.0.9), CASSANDRA-21766 (Fixed 5.0.10, not in 5.0.9) | no |
| [C1](C1.md) | new | related | none exact/partial; related CASSANDRA-15066, CASSANDRA-15358 (Fixed, in 5.0.9), CASSANDRA-20296 (Fixed 5.0.4), CASSANDRA-21529 (Open, other holder), CASSANDRA-10930 (Open) | no (cassandra.yaml:1375-1377 documents N*3*(send+receive) on-wire multiplicity, not direct memory) |
| [S1](S1.md) | known-open | partial | CASSANDRA-21656 (In Progress, partial); related CASSANDRA-16471 (Fixed 5.0-alpha1, in 5.0.9, design origin not a fix), CASSANDRA-11937, CASSANDRA-10971 | no (only changelog CHANGES.txt:601 "DataOutputBuffer#scratchBuffer can use off-heap or on-heap memory ... (CASSANDRA-16471)") |
| [S2](S2.md) | known-open | partial | CASSANDRA-19958 (Needs Committer, partial), CASSANDRA-13213 (Open, partial); related CASSANDRA-6510/4753 (Fixed, by design), CASSANDRA-19534 (Fixed, in 5.0.9), CASSANDRA-10937 (Won't Fix) | no (cassandra.yaml:1306-1317 timeout memory-build-up warning does not cover default-timeout CL=ONE local backlog) |
| [R1-V](R1-V.md) | documented only | related | none exact/partial; related CASSANDRA-10930 (Open), CASSANDRA-20491 (Open), CASSANDRA-11681 (Open), CASSANDRA-21529 (Open) | cassandra.yaml:747-748 "This pool is allocated off-heap, so is in addition to the memory allocated for heap."; cassandra.yaml:792-795 memtable spaces default to 1/4 heap; hardware.adoc:36-37 "The Cassandra heap should be no less than 2GB, and no more than 50% of your system RAM" |
| [B8](B8.md) | known-fixed (incomplete) | exact | CASSANDRA-8639 (Fixed 3.2, exact; fix 1c41a9ac2c in 5.0.9 bounds serialized bytes); 7533, 6087, 16878 related | no (NEWS.txt:1292-1293 only announces 'bound maximum in-flight commit log replay mutation bytes to 64 megabytes'; no serialized-vs-heap warning) |
| [R12](R12.md) | new | related | CASSANDRA-7392 (Fixed 3.2, related: review comment on query retention), 12403, 13001, 15500/15503, 11719 related | no (cassandra.yaml:1393-1398 slow_query_log_timeout comment has no retention/memory warning) |
| [R13](R13.md) | new | related | CASSANDRA-20166 (Fixed 6.0, related by owner ruling: reduces, does not bound); 20052, 8518, 7402, 19959 related | no (native_transport_max_request_data_in_flight not in cassandra.yaml, doc/ or NEWS.txt) |
| [R14](R14.md) | known-open | exact | CASSANDRA-15250 (Open, exact on root cause); CASSANDRA-17187 (Fixed 4.1, opt-in guardrail, 3233c82311 in 5.0.9, ships -1) | cassandra.yaml:2101-2105 "Guardrail to warn or fail when an IN query creates a cartesian product with a size exceeding threshold ... The two thresholds default to -1 to disable." |
| [R20](R20.md) | new | related | none on point; 7111, 7569, 17655 (Open), 11428 related | no |
| [U7](U7.md) | new | related | CASSANDRA-15250 (Open, related: SELECT form, different holder); 17187, 12618, 12829, 19959 related | no (nearest cassandra.yaml:2101-2105 describes the SELECT in_select_cartesian_product guardrail, off by default; it does not cover modification row build or P x Q) |
| [U8](U8.md) | new | none | none (closest related: CASSANDRA-18730 Fixed, guardrail ships -1; CASSANDRA-18504 Fixed) | no (conf/cassandra.yaml:2183-2186 names the vector_dimensions guardrail, no memory hazard; side finding: doc/modules/cassandra/pages/reference/vector-data-type.adoc:15 'Vectors are limited to a maximum dimension of 8K (2^13) items.' is not enforced in 5.0.9) |
| [U9](U9.md) | known-open | exact | CASSANDRA-16764 (Triage Needed/Unresolved, exact); CASSANDRA-9754 (Triage Needed, related, read side) | partly: conf/cassandra.yaml:1174-1183 'if large rows, or a very large number of rows per partition are present, it is recommended to increase the index granularity or switch to the BTI SSTable format' (sizing advice, no memory warning) |
| [U10](U10.md) | known-fixed (not in 5.0.9) | partial | CASSANDRA-11745 (Fixed 6.0-alpha3/7.0, fix 8f6787959e not in 5.0.9, partial); 9724 (Not A Problem, related); 6492, 17222, 11528 (Open, related) | no |
| [R22](R22.md) | known-open | partial | CASSANDRA-13235 (Open, partial); CASSANDRA-21492 (Triage Needed, related); 13213 (Open, related); 11460, 5039 (Won't Fix, related); 19958 (Needs Committer, related) | no |
| [B16](B16.md) | new | none | none (closest related: CASSANDRA-6117 Fixed, count threshold by design; 12707 Open, 2.x holder; 16896/16850 Fixed, byte guard) | partly (hazard, not the bypass): conf/cassandra.yaml:1805-1809 'we need to keep the tombstones seen in memory ... this can cause performance problems and even exaust the server heap', with tombstone_failure_threshold: 100000 at l.1815 presented as the guard |
| [B17](B17.md) | new | related | CASSANDRA-10729 (Fixed 3.0.1, related: origin of NO_LIMIT read), 6722 (Fixed 2.0.6, by-design paging refusal), 11556, 11745 (6.0 only), 9454, 4304 related | no (dml.adoc:205-218 ordering/limit sections silent on post-query ordering) |
| [R21](R21.md) | known-fixed (not in 5.0.9) | related | CASSANDRA-20780 (6.0/trunk, commit 54e39a90b0, fixes it incidentally; no issue reports the retention) | no |
| [C9](C9.md) | new | related | none exact/partial; related CASSANDRA-15452 (Fixed 5.0.4, in 5.0.9; review OOM attributed to retention, borderline partial), CASSANDRA-21671 (Fixed 5.0.10, not in 5.0.9), CASSANDRA-21684, CASSANDRA-21522, CASSANDRA-20551 | no |
| [R18](R18.md) | documented only | related | none exact/partial; related CASSANDRA-5519 (Fixed, design of periodic pool), CASSANDRA-14649 (Fixed, in 5.0.9), CASSANDRA-8552 (Cannot Reproduce), CASSANDRA-10821 (Won't Fix), CASSANDRA-20491 (Open) | cassandra.yaml:931-936 "However, this is a best-effort process. In extreme conditions Cassandra may need to use more than this amount of memory." (pool overshoot only; merge transient memory not documented) |
| [U12](U12.md) | documented only | related | none exact/partial (related: CASSANDRA-16471 Fixed 5.0, made scratch buffer direct; 16764 Open, actually U9's row-index holder; 21529 Open, pool sizing) | doc/modules/cassandra/pages/developing/cql/types.adoc:216-221 'Collections are meant for storing/denormalizing relatively small amount of data. ... when items are expected to grow unbounded ... collections are not appropriate' (data-modelling advisory, no memory/size figure) |
| [B19](B19.md) | known-open | exact | CASSANDRA-14997 (Open, exact for T2; no commit); 15556, 20052, 15299/13304 related | no (cassandra.yaml:1040-1041 frame-size comment does not say it applies to the compressed body) |
| [B21](B21.md) | new | related | none exact/partial; related: CASSANDRA-18715 (Fixed 5.0-alpha2, by-design unpaged Top-K), CASSANDRA-20086 (Fixed 5.0.7, in 5.0.9), CASSANDRA-11745 (Fixed 6.0 only, still skips Top-K) | no (doc/modules/cassandra/pages/vector-search/_query-vector-data-cycling.adoc:28 "The limit must be 1,000 or fewer." states the row cap only, no memory warning) |
| [B20](B20.md) | known-fixed (not in 5.0.9) | partial | CASSANDRA-11745 (Fixed 6.0-alpha3/7.0, fix 8f6787959e not in 5.0.9, partial); 12796 (Fixed 3.10, related); 13400/13448 (related) | no |
| [U13](U13.md) | new | related | none exact/partial; related: CASSANDRA-20752 (Fixed 5.0.6), CASSANDRA-18216 (Fixed 6.0-alpha3), CASSANDRA-21529 (Open, chunk-cache direct OOM) | no (cassandra.yaml:1791-1794 covers only segment_write_buffer_size; sai-read-write-paths.adoc:34 even says flush avoids "creating an additional in-memory representation") |
| [U15](U15.md) | known-open | partial | CASSANDRA-13213 (Open, partial: OOM from pending mutations, no root cause); CASSANDRA-19564 (Fixed 5.0.7, in 5.0.9, partial, other trigger); CASSANDRA-20084 (Fixed 5.0.4, in 5.0.9, partial, other trigger); CASSANDRA-12689 (Fixed 3.0.10, partial); CASSANDRA-11882 (Fixed 3.0.8, related: INSERT-path validation only) | no |
| [C10](C10.md) | new | related | none exact/partial; related: CASSANDRA-15774 (Open, request count only), CASSANDRA-15752 (Fixed 4.0, in 5.0.9), CASSANDRA-16896 (Fixed 4.1), CASSANDRA-11528 (Open, single-page holder) | no (max_concurrent_range_requests not in conf/doc/NEWS/CHANGES; cassandra.yaml:2014-2020 read thresholds off, no fan-out warning) |
| [B23](B23.md) | known-open | exact | CASSANDRA-10825 (Open, exact: comments 2016-2017 identify hintsInProgress as a bare CacheLoader so the check never fires; LoadingCache fix agreed, never committed); related: CASSANDRA-6007 (introducing commit 53e48edc30, in 5.0.9), 14736 (Open), 8415, 10972, 19958 | no |
| [U14](U14.md) | known-open | partial | CASSANDRA-20446 (Triage Needed/open, partial: JMX ObjectName string duplication per table); CASSANDRA-20332 (Open, partial: per-table metric memory x table count); related: CASSANDRA-19567 (Fixed 6.0 only, MetricName holder not retained in 5.0.9), CASSANDRA-21664 (Patch Available) | no (cassandra.yaml:2037-2040 "The two thresholds default to -1 to disable." — no per-table memory cost) |

## Owner rulings (2026-11-23)

1. **B8** → `known-fixed (incomplete)`: fixed in 5.0.9, but 8639's bound counts serialized bytes, not heap. New label added to
   the playbook.
2. **R13** → CASSANDRA-20166 rated `related` (its 6.0 fix reduces the decode expansion, does not bound it), so `new`.
3. **B19**: the label covers condition T2 (CASSANDRA-14997, open); condition T (body charged at its compressed size) is new.
4. **R21** → a fix in a newer version counts as known-fixed even if its issue does not describe the mechanism:
   `known-fixed (not in 5.0.9)` via CASSANDRA-20780 (6.0/trunk). Rule added to the playbook.
5. **U12** `documented only` accepted (rests on a CQL data-modelling advisory in types.adoc).

Not ruled, as filed: **C9** (CASSANDRA-15452's review OOM attributed to retention, rated `related`); **R1-V** `documented
only` (verified failures use heaps below hardware.adoc's 2 GB minimum).

Changes from stage 1's "JIRA prior art" in the case files: B23, U9 (exact), U15, R22 (partial) were `new` and are now
known; U10 and B20 are fixed upstream in 6.0-alpha3; R18 is now `documented only`.

Side findings: `doc/.../vector-data-type.adoc:15` says vectors are limited to 8K dimensions, but 5.0.9 does not enforce it
(U8); the 2026-11-16 docs findings (`MaxDirectMemorySize` default described inconsistently; CASSANDRA-16471 without a NEWS
entry) still stand. `IN` is a JIRA stop word, so `text ~ "IN"` queries return nothing (noted in the logs).
