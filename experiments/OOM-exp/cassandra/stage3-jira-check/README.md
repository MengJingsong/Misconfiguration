# Cassandra — stage 3-a JIRA check (snapshot 2026-11-24)

> **Scope (2026-11-24).** The 2026-11-23 check covered **30 of the 44** Cassandra true positives. The 14 wave 1–3 true
> positives it missed (B9, B10, B12, B13, B15, C4, C5, C6, C7, C8, U2, U3, U4, R7; their verdicts are written without bold
> in `_INDEX.md`) and R15's condition B were checked on 2026-11-24 under the same rules. All **45** are now checked
> (44 true positives + R15-B).

Rules: [`../../oom-agent-playbook.md`](../../oom-agent-playbook.md#stage-3-a--jira-check) (added 2026-11-23). Every Cassandra
**true positive** of stage 2 then known (30 cases; false positives and retries excluded by the owner) was checked read-only against
Apache JIRA (`project = CASSANDRA`, REST API, requests ≥ 2 s apart, 340 JQL queries in all, each logged with its hit count
in the case's file). Fix commits were tested against `cassandra-5.0.9` in a blobless clone of apache/cassandra (trunk to
2026-11-21); docs were read at the pinned 5.0.9 source. Four fresh agents, one per area; nothing was posted to JIRA.
The 2026-11-16 prior-art check of B6, C1, C2, S1, S2, R1-V
([`jira-prior-art-verified-cases.md`](../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-prior-art-verified-cases.md))
was re-run under these rules, not copied. The 15 cases of 2026-11-24 were checked the same way (requests ≥ 3–3.5 s apart,
each query logged in the case's file; fix commits tested in the same blobless clone).

## Counts

*Updated 2026-11-23 with the owner's rulings (B8, R13, R21; see below); 2026-11-24 with the 15 missed cases.*

| | Cases |
|---|---|
| True positives checked | **45** (44 + R15-B) |
| **Mentioned in JIRA** (exact or partial match) | **21 / 45 (47 %)** — exact 10, partial 11 |
| · still open | 13 (exact: C2, R14, B19, U9, B23, B13, C6; partial: S1, S2, R22, U15, U14, R7) |
| · fixed upstream, fix not in 5.0.9 | 4 — exact: U4 (CASSANDRA-11745, opt-in, 6.0-alpha3; owner ruling 2026-11-24: an opt-in fix counts); partial: U10 and B20 (CASSANDRA-11745, 6.0-alpha3), U2 (CASSANDRA-21755, 5.0.10 / 6.0-alpha3) |
| · fixed in 5.0.9 but the fix does not cover it (`known-fixed (incomplete)`) | 4 — exact: B8 (CASSANDRA-8639 bounds serialized bytes, not heap), C7 (CASSANDRA-19336's bound ships off); partial: B10 (CASSANDRA-20052 covers multi-frame messages only), B15 (CASSANDRA-8639, as B8) |
| Not mentioned, but fixed incidentally in a newer version | 1 (R21: CASSANDRA-20780, 6.0/trunk) |
| Not mentioned, but the shipped docs warn (`documented only`) | 5 (R1-V, R18, U12, C4, U3) |
| **New** (no exact/partial issue, no fix, no doc warning) | **18 / 45** — B6, C1, C9, R12, R13, R20, U7, U8, B16, B17, B21, U13, C10, B9, B12, C5, C8, R15-B |
| Docs warn at all (with or without an issue), source labelled in each file | 7 fully (R1-V, R18, U12, R14, C4, C7, U3), 2 partly (U9, B16) |

Label totals: known-open 13, known-fixed (not in 5.0.9) 5 (U10, B20, R21, U2, U4), known-fixed (incomplete) 4 (B8, B10, B15,
C7), documented only 5, new 18.

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
| [B9](B9.md) | new | related | none exact/partial; related CASSANDRA-15013 (Fixed, in 5.0.9: the v4 limit checked after decode), CASSANDRA-8670, 12034, 21556 (Triage Needed), 20052 (v5 sibling), 21766 (Fixed 5.0.10) | no (cassandra.yaml:1046-1052 connections unlimited by default; `native_transport_max_request_data_in_flight` not in yaml, doc/ or NEWS.txt) |
| [B10](B10.md) | known-fixed (incomplete) | partial | CASSANDRA-20052 (Fixed 5.0.3, in 5.0.9, partial: its fix covers multi-frame messages only, the single-frame path is unchanged); related 20202, 15299, 21091 (Patch Available), 15013, 19534, 21508, 16663. **For the owner:** if 20052 is rated related, the label is `new` | no (native_protocol_v5.spec:483-487 and cassandra.yaml:1069-1075 describe backpressure, not uncharged admission) |
| [B12](B12.md) | new | related | none exact/partial; related CASSANDRA-4315 (Fixed 1.2, same defect class in the key cache), 17164, 9754, 14096, 19617/21893/12126 | no (`paxos_cache_size` not in cassandra.yaml, doc/, NEWS.txt or CHANGES.txt) |
| [B13](B13.md) | known-open | exact | CASSANDRA-11082 (Open, exact); CASSANDRA-19535 (Cannot Reproduce, partial); related 15013, 14855, 11380, 21117, 15229, 21529/16154/10689 | no (cassandra.yaml:729-737 presents the networking pool as the maximum) |
| [B15](B15.md) | known-fixed (incomplete) | partial | CASSANDRA-8639 (Fixed 3.2, in 5.0.9, partial: bounds serialized bytes, not heap; no issue reports the writer-heap replay volume); related 7533, 6087, 885/609, 3535, 1967, 20084 | no (NEWS.txt:1292-1293 and CHANGES.txt only announce the bounds) |
| [C4](C4.md) | documented only | related | none exact/partial; related CASSANDRA-5519 (Fixed 2.1, by design best-effort pool), 20491 (Open), 6359, 10512, 21913, 21832 (Patch Available), 17735, 8552/10821/20565 | cassandra.yaml:931-936 "However, this is a best-effort process. In extreme conditions Cassandra may need to use more than this amount of memory."; :941-944 the 60-min resize interval (no import path, no size or duration) |
| [C5](C5.md) | new | related | none exact/partial; related CASSANDRA-9428 (Fixed 3.0.3, buffer per writer), 6230 (shared buffer intended, never done), 21657 (Fixed 5.0.10), 15006 (Open), 11678, 20491 | no (cassandra.yaml:122-128; side finding: hints.adoc:81-82 says hints are LZ4-compressed by default, the yaml and NEWS.txt:1296 say uncompressed) |
| [C6](C6.md) | known-open | exact | CASSANDRA-6794 (Open, exact); CASSANDRA-5935 (Fixed 1.2.10, exact cost, opt-in `unslabbed_heap_buffers` only); CASSANDRA-20298 (Fixed test-only, partial); related 17298, 7882, 7884, 21019 (Fixed 5.0.10), 21664 (Patch Available) | no (cassandra.yaml:792-795 says writes stop at the limit; no per-table cost anywhere) |
| [C7](C7.md) | known-fixed (incomplete) | exact | CASSANDRA-17787 (Duplicate of 19336, exact), CASSANDRA-19336 (Fixed 5.0-rc1, in 5.0.9, exact; its bound `concurrent_merkle_tree_requests` ships 0 = unlimited); 16909 (umbrella, In Progress), 21377 (Triage Needed, partial); related 21378, 14096, 15202, 18762/20565, 20491. **For the owner:** could read as by design (documented default) or known-open (16909, 21377) | cassandra.yaml:848-849 "There isn't a limit by default for backwards compatibility, but this can produce OOM for commands repairing multiple tables or multiple virtual nodes."; :827-829; CHANGES.txt:352 |
| [C8](C8.md) | new | related | none exact/partial; related CASSANDRA-20752 (Fixed 5.0.6, in 5.0.9, same holder, other root cause: borderline partial, flagged), 18673, 18598, 16052, 11383/12662/16071 (SASI), 20491 | no (cassandra.yaml:1791-1794; sai-read-write-paths.adoc:86 presents the buffer as a heap protection; side finding: monitoring.adoc:73 names a non-existent `segment_write_buffer_space_mb`) |
| [U2](U2.md) | known-fixed (not in 5.0.9) | partial | CASSANDRA-21755 (Fixed 5.0.10 / 6.0-alpha3, fix `5f11d4bd5c` not in 5.0.9, partial: caps every pre-STARTUP message); related 21756 (Review In Progress), 4265, 8086, 12034, 21529, 20052. Stage 1's `known-open` superseded | no (cassandra.yaml:1046-1048 connections unlimited, :1059-1067 idle timeouts off; no pre-auth memory warning) |
| [U3](U3.md) | documented only | related | none exact/partial; related CASSANDRA-17153 (Fixed 4.1, fragment-only guardrail, ships off), 12623 (Open), 6534, 19959, 11745 (6.0 only), 16896, 21374 | types.adoc:216-227 "even to access a single element of a collection, the whole collection has to be read (and reading one is not paged internally)"; collection-create.adoc:11-28; cassandra.yaml:2152-2169 (no heap or OOM figure) |
| [U4](U4.md) | known-fixed (not in 5.0.9) | exact | CASSANDRA-11528 (Open, exact); CASSANDRA-6492 (Open, partial); 11745 (Fixed 6.0-alpha3, not in 5.0.9, exact in a 2025 comment, but its fix is opt-in byte paging, so not counted as known-fixed; **for the owner**); 9413 (Won't Fix, partial); related 4304, 16896/16850, 17189 | no (cassandra.yaml:2013-2025 read thresholds off; NEWS.txt:442-448) |
| [R7](R7.md) | known-open | partial | CASSANDRA-21656 (In Progress, partial: same DOB holder as S1, reported as per-write over-allocation); related 16471 (Fixed 5.0, in 5.0.9), 11838, 8670, 10971, 12783 (Open), 8639 | no (cassandra.yaml:652-657, :716-724; only CHANGES.txt:601 names the scratch buffer) |
| [R15-B](R15-B.md) | new | related | none exact/partial; related CASSANDRA-5598 (Fixed 1.2.13, the after-parse marker check), 18813 (6.0), 12618/12769, 17655 (Open), 2475, 20052 | no (marker limit not in cassandra.yaml, NEWS.txt or doc/) |

## Owner rulings (2026-11-23)

1. **B8** → `known-fixed (incomplete)`: fixed in 5.0.9, but 8639's bound counts serialized bytes, not heap. New label added to
   the playbook.
2. **R13** → CASSANDRA-20166 rated `related` (its 6.0 fix reduces the decode expansion, does not bound it), so `new`.
3. **B19**: the label covers condition T2 (CASSANDRA-14997, open); condition T (body charged at its compressed size) is new.
4. **R21** → a fix in a newer version counts as known-fixed even if its issue does not describe the mechanism:
   `known-fixed (not in 5.0.9)` via CASSANDRA-20780 (6.0/trunk). Rule added to the playbook.
5. **U12** `documented only` accepted (rests on a CQL data-modelling advisory in types.adoc).

Not ruled, as filed: **C9** (CASSANDRA-15452's review OOM attributed to retention, rated `related`); **R1-V** `documented
only` (verified failures use heaps below hardware.adoc's 2 GB minimum). Flagged for the owner on 2026-11-24, as filed:
**B10** (`new` if CASSANDRA-20052 is rated related), **C7** (by design, or known-open via 16909/21377), **C8**
(CASSANDRA-20752 borderline partial). **U4** ruled 2026-11-24: an opt-in fix counts, so `known-fixed (not in 5.0.9)`.

Changes from stage 1's "JIRA prior art" in the case files: B23, U9 (exact), U15, R22 (partial) were `new` and are now
known; U10 and B20 are fixed upstream in 6.0-alpha3; R18 is now `documented only`. 2026-11-24: U2 was `known-open`
(21756, 4265) and is now `known-fixed (not in 5.0.9)` (21755); C4 was `new` and is now `documented only`; B10 was `new` and
is now `known-fixed (incomplete)` (20052 rated partial).

Side findings: `doc/.../vector-data-type.adoc:15` says vectors are limited to 8K dimensions, but 5.0.9 does not enforce it
(U8); the 2026-11-16 docs findings (`MaxDirectMemorySize` default described inconsistently; CASSANDRA-16471 without a NEWS
entry) still stand. 2026-11-24: `hints.adoc:81-82` says hints are LZ4-compressed by default while the shipped yaml and
`NEWS.txt:1296` say uncompressed (C5); `monitoring.adoc:73` names a setting `segment_write_buffer_space_mb` that 5.0.9 does
not have (C8). `IN` is a JIRA stop word, so `text ~ "IN"` queries return nothing (noted in the logs).
