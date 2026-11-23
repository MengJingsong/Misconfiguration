# U14 (OC-404) — per-table metrics and schema heap: empty, long-named tables created by DDL until the heap runs out, table count uncapped  <!-- file: cassandra/cases/per-table-metrics-heap--empty-long-named-table-ddl/per-table-metrics-heap--empty-long-named-table-ddl.md -->

| Field | Value |
|---|---|
| Case ID | `U14` (U = unprotected-accumulation case, memory with no applicable control; README "ID prefixes"). Measured class expected: **unprotected** — the only control is a count guardrail that ships disabled (unprotected configuration), and no byte budget covers the holder (unprotected accumulation); see §2.1 |
| From | `OC-404` of the phase 1 OOM candidate list (duplicates `OC-400`, `OC-401`, `OC-402`, `OC-403`, §1) |
| Phase-1 case file | [`table_name_length-validatetablename-name_length--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/table_name_length-validatetablename-name_length--autonomous.md) (also, for OC-400/OC-403, [`schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md)); stage-4 result: [`results/table_name_length-validatetablename-name_length--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/table_name_length-validatetablename-name_length--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml:36` `base.version` 5.0.9); on pc99 `/mydata/s4/cassandra-base` (built tree, no `.git`; jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`, read 2026-11-21 08:04), OpenJDK 11.0.33 |
| Stage 1 (design) | OOM-agent stage-1 session (subagent), 2026-11-21 08:02–≈ 08:50 America/New_York; nothing run (read-only check of pc99 only) |
| Stage 2 (verify) | runs: stage-2 OOM-agent session, 2026-11-21 08:18–11:18 EST on pc99 (12 lifetimes; the session was cut off before the write-up); analysis and write-up: a fresh stage-2 session (Claude Opus 5.5, `claude-opus-5-5`), 2026-11-23, from the node logs, no new runs; owner-approved follow-up (4 GiB ×3, `H4-T-2..4`): a stage-2 session (Claude Opus 5.5, `claude-opus-5-5`), 2026-11-23 11:45–15:07 EST on pc99 (§3.5) |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected: configuration, `tables_fail_threshold` −1; accumulation, no byte bound); largest failing heap **4 GiB (3/3**, follow-up 2026-11-23; 2 GiB 3/3; 8 GiB not run) (§4) |

## Summary

- **Conclusion:** true positive, `verified-OOM · deployment`. On a stock 5.0.9 node with a 2 GiB heap and every constraint at its
  default, an ordinary role creating empty tables with 222-character names (48-character keyspace) killed the node with
  `OutOfMemoryError: Java heap space` 3/3 at 3,975–3,978 tables, without writing a row (live heap +0.480 MiB per table,
  98 % of the heap live at the end, 85 % of the dump in per-table metrics/JMX/name classes). The same CREATEs with a DROP 500
  behind stayed at 0.16 × heap (0/3); the shipped `tables_fail_threshold` set to 1,900 stopped it at 0.45 × heap (0/3).
  Short names OOM at 5,736 tables (0.336 MiB per table). At 4 GiB (owner-approved follow-up, 2026-11-23) the same workload
  killed the node 3/3 at 8,137 / 8,187 / 8,225 tables after 45–85 min of DDL (the first 4 GiB lifetime, on 2026-11-21, had been
  stopped by the harness at 8,027 tables in GC service loss); largest failing heap: **4 GiB**.
- **Root cause (claimed):** every table a node loads carries eager heap state that no budget counts: `TableMetrics` registers ≈ 112
  metrics twice (a `Table` and a `ColumnFamily` alias name), each with its own `MetricName` strings, JMX `ObjectName` and, for
  histograms and timers, two `AtomicLongArray`s of ≈ 2.6 KB each; every name string embeds the keyspace and table name, so the
  cost grows by ≈ 570 B per name character per table. The only control on the table count, `tables_fail_threshold`, ships
  disabled (−1), and the 222-character name cap bounds one name, not the sum. So ≈ 0.45–0.5 MiB of heap per empty
  long-named table accumulates with the table count until the heap is gone.
- **Root cause (measured, stage 2):** confirmed, at 0.480 MiB per long-named table (0.336 with short names; ≈ 574 B per name
  character per table). The state is 214 MBeans per table: `ObjectName`/property strings carrying the names (`byte[]` ≈ 205 KB
  per table) and reservoir/histogram `long[]` (≈ 138 KB per table). The `MetricName` objects themselves are not retained (0 live).
  The guardrail at −1 lets the count reach heap / b.
- **Design in one line:** on a stock 5.0.9 node with a 2 GiB heap, an ordinary role creates empty tables with 222-character
  names in a keyspace with a 48-character name, one at a time, without writing any row; expect a Java heap OOM after
  ≈ 3,500–4,600 tables (3/3). Matched control = the same CREATE sequence with a DROP 500 tables behind (live tables ≤ 500, 3/3,
  no OOM); intervention = `tables_fail_threshold` set to half the observed N_OOM (3/3, no OOM); then a budget search at 4 GiB.

## 1. Candidate

**Candidate row (quoted from `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`, line 413):**

> | OC-404 | 2026-11-18 | `table_name_length-validatetablename-name_length--autonomous` | guided | Holder: per-table heap state, mainly metric and MBean names. TableMetrics builds every metric twice, through `factory` (Table) and `aliasFactory` (ColumnFamily). [details](runs/wave2.md#oc-404) | CP-15, CP-7, CP-8, CP-1 | picked: U14 (2026-11-21) |

**Full text (`runs/wave2.md#oc-404`):**

> Holder: per-table heap state, mainly metric and MBean names. TableMetrics builds every metric twice, through `factory` (Table) and `aliasFactory` (ColumnFamily). Each MetricName keeps a 'ks.table' scope and a full mbean-name string, and the registry/JMX ObjectNames keep further copies. Stage 4 measured about 112 MBeans per table and about 570 bytes held per table-name character per table. Why nothing stops it: nothing charges this state to any budget. The table count guardrails ship off (tables_warn_threshold / tables_fail_threshold = -1), and the 222-character cap bounds only one name's length. Size, measured by stage 4 cluster tier (refuted the 'does not cap' estimate): 500 tables gave about 255 MB heap after GC at 8-character names and about 317 MB at 222 characters, i.e. +60.7 MB, about 121 KB per table from name text alone. At 2,000-5,000 long-named tables that is 0.25-0.6 GB of name text on a heap of a few GiB, before the per-table histograms and memtable arena (see none-allocateoversize-peer). Also applies to schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous (keyspace name in the same strings).
>
> **Where:** src/java/org/apache/cassandra/metrics/TableMetrics.java:410-411, 942, 1290-1302; src/java/org/apache/cassandra/metrics/CassandraMetricsRegistry.java:913; src/java/org/apache/cassandra/config/Config.java:865-866

**Triage (`runs/triage-2026-11-18.md`, rank 16):**

> | 16 | OC-404 | yes | single ARM node | Each table carries eager heap state that no budget counts: about 112 metric MBeans, histograms of about 5.3 KB each, and name strings at about 570 B per name character per table. Stage 4 measured about 255-317 MB for 500 tables. At about 0.5-0.6 MB per long-named empty table, about 3,500-4,000 CREATE TABLEs (tables guardrails -1) fill a 2 GiB heap without writing data, which is feasible in 1-2 h of DDL. | High overlap with C6, whose D2 is already 'tables uncapped'. This holder is per-table metrics with no write needed. Duplicates OC-400, OC-401, OC-402 and OC-403. |

**The duplicates the triage names (quoted from `runs/wave2.md`), and what this design covers:**

> **OC-400** (`schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous`, autonomous): The number of keyspaces and tables is not capped at defaults: keyspaces_* and tables_* guardrails are -1, and CreateTableStatement guards only when the guardrail is enabled. Every table has a fixed heap cost that does not depend on its data. TableMetrics registers about 112 metric MBeans per table, built eagerly. Each DecayingEstimatedHistogramReservoir holds two AtomicLongArrays of 165 x 2 stripes, about 5.3 KB per reservoir. The MBean names keep copies of the keyspace and table names. Stage 4 measured about 210 MB of heap after GC for 200 keyspaces with 1 table each, after flush. Under the default heap_buffers, the first write to each table also pins a 1 MiB slab region that the memtable pool does not count, so no flush releases it. Rough size at defaults: about 0.3 MB per table after flush, or about 1.3 MB per table that has one live row. A client allowed to run DDL (anyone under the default AllowAllAuthenticator) can create about 6,000 to 25,000 tables or keyspaces and fill a default 8 GiB heap. The 48-character name limit bounds none of this.

> **OC-401** (`table_name_length-validatetablename-name_length--autonomous`, autonomous): The table count is not capped at defaults (tables_warn/fail_threshold = -1, and the guard runs only when enabled). Each table carries a fixed heap cost that no budget counts. Per-table TableMetrics are eager, with about 112 MBeans and reservoirs of about 5.3 KB each. Under the default heap_buffers, the first write pins a 1 MiB SlabAllocator region, but the pool is charged only the requested bytes. needsCleaning and the flush logic therefore see almost nothing, and the region stays. Rough size: about 0.3 to 0.5 MB per table with no live data (stage 4: about 257 MB of heap after GC for 500 tables with 8-character names), plus 1 MiB per table with a live row. That is about 6,000 written tables to fill a default 8 GiB heap.

> **OC-402** (`table_name_length-validatetablename-name_length--autonomous`, autonomous): The table-name text is copied many times on the node. Each of the about 112 per-table metric MBean names (ObjectName and MetricName strings) carries the name, with several retained copies of each. Stage 4 measured +60.7 MB of heap for 500 tables when names went from 8 to 222 characters, about 121 KB per table and about 0.5 KB per name character per table, held in byte[]. The 222-character limit caps the cost per table, but nothing caps the table count. At defaults, 10,000 tables with long names hold about 1.2 GB of name text alone, and this adds to the per-table cost in the previous clue.

> **OC-403** (`schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous`, guided, CP-15, CP-7, CP-8): Same mechanism as the per-table metric-name candidate filed under table_name_length-validatetablename-name_length--autonomous. File it once and name both stems. Holder: per-table metric/MBean state. Each table registers about 112 metrics twice, under the Table and ColumnFamily factories, and every metric and ObjectName string embeds the keyspace name and the table name. No limit applies. The keyspace count guardrails ship off (keyspaces_warn/fail_threshold = -1), and so do the table count guardrails. The 48-character keyspace cap bounds only the per-name text. Size: stage 4 here measured +4.2 MB of heap for 200 keyspaces x 1 table when names went from 3 to 48 characters (inside the 17 MB noise band). The sibling case measured about 570 B per name character per table. So the keyspace part costs up to about 27 KB per table at 48 characters, plus the per-table baseline below.

| Row | Covered here? |
|---|---|
| OC-404 (the pick) | **yes**: per-table metric/MBean/name heap, empty tables, 222-character table names |
| OC-402 | **yes**: the table-name text share is measured in the dumps (byte[] carrying a name marker, §2.6) and, if time allows, by the short-name dial arm S8 (§2.8) |
| OC-403 | **yes, for its keyspace-name text**: the one keyspace has a 48-character name (`NAME_LENGTH` = 48, `SchemaConstants.java:75`) in every arm |
| OC-401 | **yes, for the empty-table part** (per-table metrics and schema heap, guardrail −1). Its "1 MiB slab region per written table" part is C6's holder and is deliberately excluded here (no user row is written in any arm) |
| OC-400 | **partly**: the per-table cost with the table guardrail off is covered; its keyspace-count variant (many keyspaces with one table each, `KeyspaceMetrics` per keyspace, `keyspaces_*` guardrails) is **not** covered (one keyspace only); its slab part is C6's |

**Relation to C6 (not a rerun).** [C6](../memtable_heap_space-slab-region--written-table-multiplicity/memtable_heap_space-slab-region--written-table-multiplicity.md)
(`true positive`, `verified-OOM · deployment`, mixed) reached OOM by writing **one row into each** of ≈ 1,040 pre-built
short-named tables: its claimed holder D1 was the 1 MiB slab region per written table, and this case's holder was its D2
("per-table schema and metrics heap", "no control", ≈ 0.316–0.342 MiB per short-named table). C6 never ran D2 alone to an
endpoint: its matched control and intervention lifetimes held D2 at 2,500 tables (L0 = 922–923 MiB = 0.45 × 2 GiB) and
survived. U14 claims that D2 alone, **with no user write at all**, runs a 2 GiB heap out once the table count passes
≈ heap / b, and adds the name-length component (OC-402/403/404) that C6's `t<i>` names in keyspace `ks` did not exercise.
The workload (DDL only), holder (no slab region), endpoint and arms all differ.

**Phase-1 constraint and its check.** `TABLE_NAME_LENGTH` = 255 − 32 − 1 = **222** (`SchemaConstants.java:80`, `:91`), checked in
`TableMetadata.validateTableName()` (`TableMetadata.java:517-518`, `except(...)`, table not created). It bounds one table
name so its directory name `<name>-<32 hex>` fits 255 characters; it bounds no memory. Keyspace names are capped at
`NAME_LENGTH` = 48 (`SchemaConstants.java:75`).

**What stage 4 measured** (2026-10-28, pc29, verdict: unit Confirmed / cluster **Refuted — caps**): 500 tables × 1,000 rows,
1 GiB heap, heap after GC 255–257 MB at 8-character names vs 315–320 MB at 222 characters: **+60.7 MB = ≈ 121 KB per table**
(repetition spread 2.3 / 4.9 MB), all in `byte[]`; ≈ 567 B per extra name character per table; a supplementary count on 20
tables found **112 metric MBeans per table under `type=Table`** whose names grew by 112 × 214 characters per table. A
223-character `CREATE TABLE` is refused (code 2300). DDL + writes took ≈ 560 s per 500-table arm (four writer processes). No
OOM was attempted. The sibling keyspace case measured +4.2 MB for 200 keyspaces × 1 table at 3 → 48 characters (inside noise).
C6 (2026-11-18, pc91, 8 GiB build lifetimes) measured the per-table schema+metrics heap of **empty short-named tables**:
histogram totals 61.8 / 221.4 / 379.2 / 536.3 / 695.7 / 851.9 MiB at 0 / 500 / … / 2,500 tables (b = 0.316 MiB) and
879.5 → 1,563.3 MiB from 2,500 to 4,500 tables (b = 0.342 MiB); after a restart at a 2 GiB heap, 2,500 tables gave L0 = 923.4
MiB. DDL from empty: 2.9 min for 2,500 tables (49 → 88 ms per table) and 4.3 min for the next 2,000 (112 → 142 ms).

**JIRA prior art** (read only; nothing posted). Sources: `jira-oom-survey.csv` (rows CASSANDRA-5982, 6977 (not in the csv),
14840, 11748, 2006, 8245 read for scope); JIRA REST (issues.apache.org reachable, 2026-11-21 ≈ 08:06 EST):
`project=CASSANDRA AND text ~ "\"number of tables\"" AND text ~ "heap"` (15 hits),
`text ~ "TableMetrics" AND text ~ "memory"` (24), `summary ~ "tables" AND summary ~ "metrics" AND text ~ "heap"` (1),
`text ~ "\"too many tables\""` (5); issue reads below.

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-19567 "Minimize the heap consumption when registering metrics" | Fixed **6.0-alpha1 / 6.0** (trunk only, committed 2024-04-30) | The same holder: an in-JVM dtest OOM with "a lot of MetricName objects stored in the heap"; the patch reduced per-metric registration heap. Not in 5.0.x. It shrinks the per-table cost; it does not bound the table count. |
| CASSANDRA-21664 "Make schema changes cost O(1) in the number of tables and fail loudly at schema limits" | **Patch Available** (6.0.x, 7.x) | 10,000 tables take 28 min to create (6.0); "Table-count guardrails ship disabled"; proposes `tables_warn_threshold` default 1000 (a warning only). Confirms per-DDL cost grows with the table count (time plan, §2.9). |
| CASSANDRA-21659 "Adding a large amount of schema allocates excessively" | Duplicate (of 21664) | Each schema change allocates in proportion to the whole schema (292 KB at 400 tables → 3.77 MB at 3,200 per CREATE TABLE, trunk), "it is what produces the failure (a GC wall…)". A transient term on top of this case's standing holder (§2.1, D4). |
| CASSANDRA-14840 "Bootstrap of new node fails with OOM in a large cluster" | Unresolved | 3,000 tables, 80 nodes: concurrent schema pulls at bootstrap; a different holder (transient schema copies), same multiplier. |
| CASSANDRA-6977 "attempting to create 10K column families fails with 100 node cluster" | Duplicate (2.1.1) | Creating 10K tables fails on a large cluster (latency, timeouts); an old schema-propagation issue, no heap holder named. |
| CASSANDRA-5982, CASSANDRA-2006 | Fixed (1.2/2.0, 0.8) | Many tables × memtables, pre-`MemtablePool` era; different holder (memtable data, now C6's family). |

**Verdict: `known-open`.** The per-table metric heap is known upstream and was **reduced** in 6.0 only (CASSANDRA-19567, not
back-ported to 5.0.x); nothing bounds the table count in any release (21664 is unmerged and proposes a warning default only).
Not `known-fixed` for the pinned 5.0.9, so not a positive-control pick. 5.0.9's `cassandra.yaml:2037-2040` says only "The two
thresholds default to -1 to disable" and documents no per-table memory cost; the behaviour is not documented as by design.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

`CREATE TABLE` (`CreateTableStatement.apply`) checks the table-count guardrail only when it is enabled
(`CreateTableStatement.java:138-145`: `if (Guardrails.tables.enabled(state)) … guard(totalUserTables + 1, …)`); both thresholds
ship at −1 (`Config.java:865-866`; `cassandra.yaml:2039-2040` commented). `Guardrail.enabled(state)` is also false for a
superuser (`Guardrail.java:93-95`, `ClientState.isOrdinaryUser()` `:594-597`; with the shipped `AllowAllAuthenticator` every
client is a superuser, `ClientState.java:602-605`). The schema change then opens the table: a `ColumnFamilyStore` with its
`Tracker`, an empty memtable (its `SlabAllocator` takes no region until the first write, `SlabAllocator.java:126-153`),
`Directories`, compaction strategy, and **`TableMetrics`** (`TableMetrics.java:408-411`: `factory = new
TableMetricNameFactory(cfs, "Table")`, `aliasFactory = new TableMetricNameFactory(cfs, "ColumnFamily")`). Every per-table
metric is registered under both names (`createTableGauge` → `Metrics.register(factory.createMetricName(name),
aliasFactory.createMetricName(alias), gauge)`, `TableMetrics.java:938-945`; `CassandraMetricsRegistry.register(name,
aliasName, metric)` `:191`, which registers a JMX MBean for the name and again for the alias, `:234-263`, `:276`). Each
`MetricName` (`CassandraMetricsRegistry.java:751-755`, constructor `:818`) keeps a `ks.table` scope and a full mBean-name string
built from the keyspace and table names (`TableMetrics.java:1290-1302`), and `getMBeanName()` builds a JMX `ObjectName` from it
(`CassandraMetricsRegistry.java:905-913`), which the platform MBean server keeps in its repository. Histograms and timers get a
`DecayingEstimatedHistogramReservoir` with two `AtomicLongArray`s of (164 + 1) × 2 stripes longs (`:238`, `:454`,
`DEFAULT_BUCKET_COUNT` 164, stripes `cassandra.dehr_stripe_count` = 2, `CassandraRelevantProperties.java:185`) ≈ 2 × 2.6 KB.
All of this is eager (no row needs to be written) and lives until the table is dropped (`TableMetrics.release()` on
invalidate). No byte counter charges any of it; the 222-character name cap (`TableMetadata.java:517`) and the 48-character
keyspace cap bound one name each.

Measured sizes (§1): b ≈ 0.32–0.34 MiB per empty short-named table (C6), plus ≈ 567 B per name character per table
(stage 4): 216 more table-name characters add ≈ 0.117 MiB and 46 more keyspace-name characters ≈ 0.025 MiB, so
**b_long ≈ 0.46–0.49 MiB per empty table** (planning range 0.42–0.52). On top of the standing holder, each DDL allocates
transient garbage that grows with the schema (CASSANDRA-21659: whole-schema diffs; ≈ 3.8 MB per CREATE at 3,200 tables on
trunk) and flushes every `system_schema` table (`SchemaKeyspace.java:81`, `:1427`, `cassandra.test.flush_local_schema_changes`
default true, `CassandraRelevantProperties.java:563`).

When the live set reaches the heap, an allocation fails after a full GC: `java.lang.OutOfMemoryError: Java heap space`
(predicted on a `Native-Transport-Requests` thread inside the schema change, or on a GC-starved background thread),
`JVMStabilityInspector` handles it, the shipped `-XX:+HeapDumpOnOutOfMemoryError` (`jvm-server.options:120`) writes a dump and
`-XX:OnOutOfMemoryError=kill -9 %p` (`cassandra-env.sh:209`) kills the JVM.

**Direction.** By the protocol's classification table: **unprotected**. The only control applicable to the holder is the
table-count guardrail, which exists and ships disabled (**unprotected configuration**, labelled `tables_warn_threshold` /
`tables_fail_threshold` = −1 default); no control of any kind charges the per-table bytes (**unprotected accumulation**:
the only bound is implicit, tables × per-table cost). The prefix U is kept (README "ID prefixes" has no separate prefix for
unprotected configuration; U10 is filed the same way). Technique notes: [`combo-playbook.md`](../../../combo-playbook.md)
(multiplicity) and the protocol's *Unprotected results* (the intervention adds a bound and shows the failure stops).

### 2.2 Protection map

| Domain | Allocation and ownership | Local contract (counter K, limit C) | Scope and multiplicity | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|---|
| **D1 per-table metrics and JMX names (claimed holder)** | `TableMetrics` (`TableMetrics.java:408` on): ≈ 112 metrics × 2 names; `MetricName` strings, `ObjectName`s in the MBean server, reservoirs' `AtomicLongArray`s, global-metric children; owner = the table's `ColumnFamilyStore`; released by `TableMetrics.release()` at DROP | **none on bytes**; K = number of user tables, C = `tables_fail_threshold` = −1 (disabled, `Config.java:866`); guard only for ordinary users (`Guardrail.java:95`) | per table loaded (N); N bounded by nothing at defaults | none: no memtable, cache or reservation covers it | standing for the table's life | Java heap (`-Xmx`) |
| **D2 per-table schema and store objects (claimed, with D1)** | `TableMetadata`/`ColumnMetadata` (one copy per schema version kept), `ColumnFamilyStore`, `Tracker`, empty `SkipListMemtable` + `SlabAllocator` (no region), `Directories`, compaction strategy objects, keyspace maps | none on bytes; same K/C as D1 | per table | none | standing | heap |
| D3 memtable pool | system tables' memtables (`system_schema` written by every DDL, flushed after each local change, `SchemaKeyspace.java:1427`); no user row is written | K = pool `allocated`; C = `memtable_heap_space` = heap/4 (512 MiB at 2 GiB), cleaner at C/3 | per node | memtable pool | until flush (per DDL) | heap; recorded (`AllMemtablesOnHeapDataSize`), not claimed |
| D4 schema-change transients | whole-schema diffs and keyspace map rebuilds per DDL (CASSANDRA-21659), schema digest | none | one DDL at a time (one client, serial) | none | transient, per DDL | heap; sets the last allocation that fails, not claimed as the holder |
| D5 node baseline | caches (key cache min(5 % heap, 100 MiB) = 100 MiB cap; counter cache min(2.5 % heap, 50 MiB) = 50 MiB; prepared statements max(heap/256, 10 MiB) = 10 MiB; auth role/credential caches), system keyspaces, Netty, JMX | each its own cap | per node | separate caps | standing | heap; nearly empty here (no reads, no user writes) |
| D6 direct / native | Netty, `BufferPool` chunks, commit-log segments, tmpfs pages if §2.5's tmpfs rule applies | `MaxDirectMemorySize` (auto 15,872 MiB on pc99), networking pool | per node | separate | — | direct; not expected to move (recorded, not claimed) |

**Scope decision (fixed before any run).** U of D1 + D2 is the live-heap growth per loaded user table, measured by class
histograms and the dump (§2.6) independently of K (the table count). It is compared against **the only applicable control**,
the table-count guardrail, which is disabled → *unprotected configuration*; and against the heap budget, which no control
reserves for it → *unprotected accumulation*. D3–D6 are recorded to show they stay near baseline.

### 2.3 Configuration and budget audit

- **Build:** stock 5.0.9 tree copied with `cp -a /mydata/s4/cassandra-base /mydata/s4/u14/cassandra` on pc99 (jar sha256
  `570b5249…a90176e`, recorded above; this build differs from pc91's `960c9a00…` used by C6 — both 5.0.9 builds of the pinned
  source; record `build.xml` `base.version`). No patches, no Byteman, no agents. Never run `ant` in that tree.
- **Node (checked read-only 2026-11-21 08:04 EST):** pc99 = `node4.jason92-326665` (UMass), x86_64, 32 cores, 125 GiB RAM,
  kernel 5.15.0-203-generic, Ubuntu 22.04, cgroup v2, 8 GiB swap (`/dev/sda99`, 0 used; kept at 0 for the JVM), `/mydata` on
  `emulab-node4--bs` 753 GiB with 714 GiB free, backed by `sda` (**rotational**), `/dev/shm` tmpfs 63 GiB free; load 0.00; no
  `java` / `CassandraDaemon` running; `/mydata/s4/` holds only `cassandra-base`; `ant` present; `vm.max_map_count` 65530;
  `ulimit -n` 1024 in an ssh shell (record the JVM's `Max open files` from `/proc/<pid>/limits`; empty tables open no data files).
- **Capacity constraints (V6), all at shipped defaults, resolved per heap:**

| Constraint | Shipped default | Resolved at 2 GiB | at 4 GiB | Label |
|---|---|---|---|---|
| `tables_warn_threshold` / `tables_fail_threshold` | −1 / −1 (`Config.java:865-866`) | disabled | disabled | default (unprotected configuration); **intervention arm only**: `tables_fail_threshold` = X (§2.8) |
| `keyspaces_warn_threshold` / `keyspaces_fail_threshold` | −1 / −1 (`Config.java:862-863`) | disabled (one keyspace used) | same | default |
| `TABLE_NAME_LENGTH` / `NAME_LENGTH` | 222 / 48 (constants) | names used: 222 / 48 | same | compile-time; at their limits |
| `columns_per_table_*` | −1 | 2 columns used | same | default |
| `memtable_allocation_type` | `heap_buffers` (`cassandra.yaml:825`) | `heap_buffers` | same | default (no user write, so no slab region) |
| `memtable_heap_space` | heap/4 | 512 MiB | 1024 MiB | default |
| `key_cache_size` / `counter_cache_size` / `prepared_statements_cache_size` | auto | 100 / 50 / 10 MiB | 100 / 50 / 16 MiB | default (read back) |
| `auto_snapshot` | true (`cassandra.yaml:1147`) | true | true | default (matters for the control's DROPs) |
| `num_tokens`, timeouts, `commitlog_sync` periodic | shipped | read back | | default |

- **Other settings (all arms identical; disclosed):** `authenticator: PasswordAuthenticator` (shipped `AllowAllAuthenticator`,
  `cassandra.yaml:198`), `authorizer: AllowAllAuthorizer` (shipped), `role_manager: CassandraRoleManager` (shipped). Reason:
  guardrails apply only to ordinary users (`Guardrail.java:95`), so the intervention needs a non-superuser; the test and control
  arms use the same authentication so that the arms differ only by the one setting. `PasswordAuthenticator` is the documented
  production setting, an accepted value (conditions label stays `deployment`). With `AllowAllAuthorizer` the creator grant is a
  no-op (`AlterSchemaStatement.java:131-160`, `UnsupportedOperationException` caught), so no `system_auth` row per table.
  **Fallback (pre-declared):** if the node refuses `PasswordAuthenticator` with `AllowAllAuthorizer` in the shakedown, use
  `CassandraAuthorizer` in all arms with `GRANT CREATE, DROP, ALTER ON KEYSPACE <ks> TO u14` (each CREATE then grants the creator
  permissions on the new table, a `system_auth.role_permissions` row; disclosed as environment).
- **Config diff against shipped `conf/` (every lifetime; environment deviations):** `cluster_name: u14`; `listen_address`,
  `rpc_address`, seeds `127.0.14.1`; `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory`,
  `cdc_raw_directory` under the lifetime directory (on `/mydata`, or `/dev/shm` by the rule of §2.5); `JMX_PORT="7214"` in
  `cassandra-env.sh`; `authenticator` as above; `MAX_HEAP_SIZE` per arm (`HEAP_NEWSIZE` unset, G1). Intervention arm only:
  `tables_fail_threshold: X`. Save `yaml.diff`, `env.diff`, `jvm-cmdline.txt` per lifetime.
- **Shipped JVM options kept:** `jvm11-server.options` (G1, `-XX:G1HeapRegionSize=16m` `:66`), `jvm-server.options`
  (`-XX:+HeapDumpOnOutOfMemoryError` `:120`, `-XX:+AlwaysPreTouch` `:128`), `cassandra-env.sh` (`OnOutOfMemoryError=kill -9 %p`
  `:209`, GC log `-Xlog:gc=info,heap*=trace,…:file=${CASSANDRA_LOG_DIR}/gc.log` `:83`). `CASSANDRA_HEAPDUMP_DIR` =
  `/mydata/s4/u14/dumps/<label>/` (always on `/mydata`).
- **Budget (V7):** the Java heap. **2 GiB** (the ideal; what `cassandra-env.sh` resolves by itself on a 4 GiB-RAM host,
  `cassandra-env.sh:51-68`: min(RAM/2, 31,744 MiB) under G1) and, for the budget search, **4 GiB** (what it resolves on an
  8 GiB host). Both ≥ 512 MiB: V7 met by the standing rule. On pc99 the script would resolve 31,744 MiB; the smaller heaps are
  an explicit deployment budget, recorded as such. `MaxDirectMemorySize` left to `cassandra-env.sh` (expected 15,872 MiB = 
  31,744 / 2; read back). Process/container: the JVM runs in `systemd-run --user --scope -p MemoryMax=<heap+6G> -p
  MemorySwapMax=0` as a **safety guard only** (8G at 2 GiB, 10G at 4 GiB, 14G at 8 GiB); it must not bind (`memory.events`
  `oom_kill` = 0 is a validity check). No container limit is part of the budget, so no owner review is needed.

### 2.4 Ceiling arithmetic

Live heap with N user tables loaded, no user rows: `L(N) ≈ B0 + N × b_long` (+ D4 transients during a DDL).
B0 ≈ 62–75 MiB (C6: 61.8 MiB idle histogram; + `PasswordAuthenticator` and role setup, a few MiB).

- **Contract capacities:** D3 512 MiB + D5 ≈ 160 MiB (all nearly empty here) + B0 ≈ 0.73 GiB < 2 GiB: with every control
  honoured and every capped pool full, the heap cannot fill. The OOM needs the uncapped D1 + D2.
- **Endpoint:** OOM when L(N) + transients exceed what a full GC can free, at L ≈ f × heap. C6's three OOMs at 2 GiB came at
  live ≈ 0.96 × heap (923 + 1,044 MiB); planning range f = 0.93–0.98.
- **Predicted N_OOM at 2 GiB:** (f × 2,048 − B0) / b_long = central (0.96 × 2,048 − 65) / 0.47 ≈ **4,050**; range
  (0.93 × 2,048 − 75) / 0.52 ≈ **3,520** to (0.98 × 2,048 − 62) / 0.42 ≈ **4,630**.
- **At 4 GiB:** central (0.96 × 4,096 − 65) / 0.47 ≈ **8,230**; range ≈ 7,180–9,410.
- **Short names (dial S8, 2 GiB):** b_short ≈ 0.316–0.344 (+ ≈ 0.025 for the 48-character keyspace is *not* in S8: S8 uses `ks`)
  → N_OOM ≈ (0.96 × 2,048 − 65) / 0.33 ≈ 5,760 (range 5,500–6,170).
- **Control (churn, ≤ 500 live tables):** L ≈ 70 + 500 × 0.47 + system_schema growth (tombstones, sstables; ≤ 100 MiB) ≈
  300–400 MiB ≤ 0.2 × heap.
- **Intervention (X ≈ 0.5 × N_OOM ≈ 2,000):** L ≈ 70 + 2,000 × 0.47 ≈ 1,010 MiB ≈ 0.49 × heap (≥ 30 % margin below the
  observed endpoint).

### 2.5 Workload and environment (pc99 only)

**Directories (pc99, local only, never NFS):** `/mydata/s4/u14/cassandra` (the copied tree), `/mydata/s4/u14/harness/` (synced
from this folder's `harness/`), `/mydata/s4/u14/run/` (current lifetime: `conf/`, `logs/`, and — unless the tmpfs rule applies —
`data/`, `commitlog/`, `hints/`, `saved_caches/`, `cdc_raw/`; recreated per lifetime), `/mydata/s4/u14/dumps/<label>/`,
`/mydata/s4/u14/logs/<label>/` (kept). Address `127.0.14.1`, native 9042, storage 7000, JMX 7214 (all checked free before each
start). Before each lifetime: `ps -eo pid,cmd | grep '[C]assandraDaemon'`; another experiment's node on pc99 is recorded (PID,
heap) and this case proceeds only if `MemAvailable` ≥ 30 GiB and the ports are free.

**Disk rule for DDL speed (pre-declared; decided in the shakedown, before any reading).** Each DDL flushes every
`system_schema` table (§2.1) on a rotational disk. The shakedown S0 (2 GiB, `/mydata`) creates 1,000 long-named tables and fits
the per-CREATE latency t(n) = a + c·n. If the projected DDL time to 4,600 tables, Σ t(n), exceeds **25 min**, repeat S0's first
500 tables with `data/`, `commitlog/`, `hints/`, `saved_caches/`, `cdc_raw/` under `/dev/shm/u14/run/`; if that is ≥ 1.5× faster,
**every** arm uses `/dev/shm` for those directories (an environment deviation, disclosed; tmpfs pages are charged to the scope,
not to the heap budget; record `Shmem` at each checkpoint; `rm -rf /dev/shm/u14` after each lifetime and at the end). Logs and
dumps stay on `/mydata`. Expected (C6 on the same hardware type: 49 → 142 ms per CREATE from 0 to 4,500 tables, 8 GiB heap):
Σ ≈ 6–12 min, so `/mydata` is expected to be kept.

**Names.** Long (all arms except S8): keyspace `KS` = `u14` + 45 × `k` (48 characters); table *i* = `t` + 5-digit *i* +
216 × `x` (222 characters; the marker `x` × 64 appears in no system name). S8: keyspace `ks`, table `t` + 5-digit *i*
(6 characters). Schema: `CREATE TABLE IF NOT EXISTS "<KS>"."<t>" (k int PRIMARY KEY, v blob)` with shipped table options (as
C6). Keyspace: `CREATE KEYSPACE IF NOT EXISTS <KS> WITH replication = {'class':'SimpleStrategy','replication_factor':1}`.

**Harness to build in stage 2** (`harness/`; base it on C6's
[`harness/`](../memtable_heap_space-slab-region--written-table-multiplicity/harness/): `client.py`, `run.py`, `Jmx.java`,
`hprof_scan.py`, `instrument-check.sh`, `analyze.py`):

- `client.py` — bundled Python driver from `$CASSANDRA_HOME/lib`, protocol 4, `PlainTextAuthProvider('u14', …)`,
  `WhiteListRoundRobinPolicy(['127.0.14.1'])`, **`schema_metadata_enabled=False`, `token_metadata_enabled=False`,
  `max_schema_agreement_wait=0`**, one session, one statement at a time, request timeout 120 s. Commands:
  - `create <first> <last>` (T, S8): CREATE table *i* in order; per statement one line to `client.csv` (epoch ms, i, op,
    latency ms, result: ok / timeout / rejected / error + class). A timed-out CREATE is retried (≤ 3 tries; `IF NOT EXISTS`
    makes it idempotent). After every 500 successful CREATEs it calls `checkpoint` (below) and continues. Stops at `<last>`, at a
    connection loss with no reconnect within 60 s (node dead), or at the lifetime's wall cap.
  - `churn <first> <last> <W>` (C): for each *i*: CREATE table *i*; if *i* − W ≥ `<first>`, DROP table *i* − W; same logging; a
    checkpoint after every 500 CREATEs.
  - `create` under the intervention counts `rejected` = `InvalidRequest` whose message contains `Guardrail tables violated`
    (any other error is an `error`).
  - `checkpoint`: pause the client, run `jcmd <pid> GC.class_histogram` twice (keep both; **L(n)** = total of the second,
    plus its top 40 classes), read `SELECT count(*) FROM system_schema.tables WHERE keyspace_name = '<KS>'` (**K**), resume.
- `Sampler.java` (from C6's `Jmx.java`) — one long-lived local JMX client (port 7214, **fixed ObjectNames only, no pattern
  queries**; C6's stage-4 found a per-table pattern query leaves ≈ 21 MB live heap), every 1 s to `sampler.csv`: epoch ms;
  `HeapMemoryUsage.used`; `G1 Old Gen` `Usage.used` and `CollectionUsage.used`; `G1 Young/Old Generation`
  `CollectionCount`/`CollectionTime`; **`MBeanServerConnection.getMBeanCount()`**; `org.apache.cassandra.metrics:type=Table,
  name=AllMemtablesOnHeapDataSize` `Value` (D3). A shell loop samples `RssAnon` and `Shmem` (from `/proc/meminfo`) every 1 s
  to `rss.csv`.
- `hprof_scan.py` (extend C6's) — one sequential pass over an HPROF 1.0.2 dump: map class IDs to names (`LOAD CLASS` + `UTF8`
  records), tally per class the instance count and shallow bytes (instance and array records), and count/bytes of `byte[]`
  whose content contains the marker `x` × 64 (**name-text share**) and of `long[]` of length 330 (reservoir buckets). Output
  JSON with the top 40 classes and the named classes: `org.apache.cassandra.metrics.TableMetrics`,
  `org.apache.cassandra.db.ColumnFamilyStore`, `org.apache.cassandra.metrics.CassandraMetricsRegistry$MetricName`,
  `javax.management.ObjectName`, `org.apache.cassandra.metrics.DecayingEstimatedHistogramReservoir`,
  `java.util.concurrent.atomic.AtomicLongArray`, `org.apache.cassandra.schema.TableMetadata`. Run with `python3 -I`. If a 2 GB
  dump takes > 10 min, rewrite it in Java (same output), or scan T-1's dump in full and keep T-2/T-3 dumps on `/mydata` for a
  later scan (stated in §3).
- `instrument-check.sh` + `Hold.java` — known-answer check before any lifetime: a JVM holding 1,000 `String`s of 222 characters
  containing the marker plus 500 `long[330]`; `jcmd GC.heap_dump`; the scan must report ≥ 1,000 marker `byte[]` and exactly
  500 `long[330]` (else fix the scanner; not a reading). Also check `Sampler.java` against the shakedown node.
- `run.py <label> <arm> <heap> <names> [X]` — one lifetime, scripted, epoch ms per command, `EXPECTED:` lines (read-back,
  flags, scope), node stopped by PID on any exit; launch with `( setsid nohup … < /dev/null > /dev/null 2>&1 & )` and poll in
  bounded waits (never a foreground sleep); kill by PID (pidfile or `/proc/*/cmdline` match on `/mydata/s4/u14/`), never
  `pkill -f`.
- `analyze.py` — per lifetime: the readings of §2.6 and the checks of §2.7 from `client.csv`, `sampler.csv`, `rss.csv`,
  histograms, scans, `system.log`, `stdout.txt`, `gc.log`.

**Step A — tree and checks (not readings).** Copy the tree; versions and jar sha256; instrument check; **shakedown S0** (2 GiB,
the T settings, `/mydata`): start, role setup, `create 1 1000` with checkpoints at 500 and 1,000; stop the node, restart it on
the same data with `tables_fail_threshold: 1050` in the yaml and issue `create 1001 1100` as `u14`: expect 50 ok + 50
`rejected` (checks the intervention path and that `u14` is an ordinary user). S0 gives a, c (disk rule) and an informative b;
its numbers are not readings.

**Step B — lifetime procedure (every measured lifetime).** `rm -rf /mydata/s4/u14/run` (and `/dev/shm/u14`) and recreate;
write conf (§2.3 diff + the arm's settings); start under the scope; wait until 9042 answers (≤ 600 s); wait for the default
`cassandra` superuser (shipped `CassandraRoleManager` creates it ≈ 10 s after start), then as `cassandra`: `CREATE ROLE u14
WITH PASSWORD = '…' AND LOGIN = true AND SUPERUSER = false`; as `u14`: CREATE the keyspace. Read back
`system_views.settings` (`authenticator`, `authorizer`, `tables_warn_threshold`, `tables_fail_threshold`,
`keyspaces_fail_threshold`, `memtable_allocation_type`, `memtable_heap_space`, `key_cache_size`, `counter_cache_size`,
`prepared_statements_cache_size`, `auto_snapshot`, `num_tokens`), the JVM command line (`-Xmx`, `-XX:MaxDirectMemorySize`,
G1 flags, `AlwaysPreTouch`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError`), `/proc/<pid>/limits`, the scope's
`memory.max`/`memory.swap.max`, and that `u14` is not a superuser (`LIST ROLES`). Then:
- `s0`: start `Sampler` and the RSS loop; 10 s; `checkpoint` (L(0), K = 0); 10 s.
- **Workload** (the only difference between arms, §2.8).
- **End of a surviving lifetime:** 10 s idle; `checkpoint` (**U_end**); in the first lifetime of each surviving arm also
  `jcmd <pid> GC.heap_dump /mydata/s4/u14/dumps/<label>/end.hprof` and `hprof_scan.py`; stop the node by PID.
- **On OOM:** wait (bounded, ≤ 240 s) for `Heap dump file created` in `stdout.txt` and the JVM to exit; scan the dump; copy
  `system.log`, `debug.log`, `gc.log*`, `stdout.txt`, `client.csv`, `sampler.csv`, `rss.csv`, histograms, `memory.events`,
  scan JSON to `/mydata/s4/u14/logs/<label>/`; keep the `.hprof` on `/mydata` until the case file is written, then delete
  (disk: 714 GiB free, ≤ 10 dumps × ≤ 4.5 GB).
- After each lifetime: no process left (`ps`), `rm -rf` of the run directory (and `/dev/shm/u14`).

### 2.6 Instruments and readings (U measured independently of K)

| Reading | Source | When | Meaning |
|---|---|---|---|
| L(n) | histogram total (2nd of two `GC.class_histogram`) | every 500 CREATEs, `s0`, end | live heap with n tables (U of D1 + D2 + baseline) |
| b | least-squares slope of L(n) on n (T: all checkpoints up to the last before OOM) | per lifetime | per-table heap (MiB per table); predicted 0.42–0.52 |
| per-class slopes | histogram classes, slope per table (top 15 by bytes) | per lifetime | composition of D1 + D2 (e.g. `byte[]`, `String`, `ObjectName`, `MetricName`, `long[]`/`AtomicLongArray`, `ConcurrentHashMap$Node`) |
| MBeans per table | slope of `getMBeanCount()` on n | 1 s | eager JMX registrations per table (predicted ≈ 224 = 112 × 2 names; stage 4 counted 112 under `type=Table`) |
| K | `count(*)` of the keyspace's tables in `system_schema.tables`; client's ok count | checkpoints; per statement | the guardrail's quantity (user tables); not a byte counter |
| N_OOM | last CREATE acknowledged ok before the dump file's birth time (`stat %W`) or the connection loss | T arms | endpoint multiplicity |
| f | L(last checkpoint) and old-gen `CollectionUsage.used` at the last valid sample, / heap | T arms | live fraction at the endpoint |
| dump composition | `hprof_scan.py`: named class counts (expect `TableMetrics` and `ColumnFamilyStore` ≈ N_OOM + system tables), marker `byte[]` count/bytes (name text), `long[330]` count | at OOM; end of C-1, I-1 | V5: the claimed holder at failure |
| first error | `stdout.txt`/`system.log`: first `OutOfMemoryError`, thread, stack; `Heap dump file created`; exit | at OOM | V5 initiating failure |
| GC | `gc.log` (shipped), sampler GC times | continuous | service-loss window (≥ 90 % STW over ≥ 60 s) |
| D3 | `AllMemtablesOnHeapDataSize` | 1 s | memtables stay small (no user rows) |
| DDL latency | `client.csv` | per statement | time plan; per-DDL cost growth |
| RSS, Shmem | `/proc/<pid>/status`, `/proc/meminfo` | 1 s | process and tmpfs (not the budget) |

Instrument overhead: checkpoints force two full GCs each (identical in every arm, every 500 CREATEs); the sampler uses fixed
names only.

### 2.7 Predicted response, outcome rows and stopping budget

**Predictions (2 GiB, long names):**
- P1 (T): L(n) grows linearly, **b = 0.42–0.52 MiB per table** (central 0.47); MBeans ≈ 200–240 per table; D3 stays ≤ 20 MiB.
- P2 (T): **Java heap OOM 3/3** at **N_OOM ≈ 3,520–4,630** (central 4,050), f = 0.93–0.98; DDL latency rising from ≈ 50 ms to
  ≈ 150 ms per CREATE, then GC-bound in the last ≈ 5 % of tables.
- P3 (T dumps): `TableMetrics` and `ColumnFamilyStore` instances = N_OOM + the system tables (± the one in flight); per-table
  classes (`byte[]`, `String`, `ObjectName`, `MetricName`, `long[]`, maps) make up ≥ 70 % of live heap; marker `byte[]` hold
  ≥ 0.08 MiB per table (name text share ≥ 15 %).
- P4 (C): no OOM 3/3, U_end ≤ 0.25 × heap; live heap flat across the churn (slope after the first 500 tables ≤ 0.02 MiB per
  CREATE+DROP pair).
- P5 (I): no OOM 3/3; exactly X tables created, every further attempt `rejected`; U_end ≈ L(X) ≤ 0.6 × heap.
- P6 (4 GiB, T): OOM at N_OOM ≈ 7,180–9,410.
- P7 (S8): OOM at N_OOM ≈ 5,500–6,170; b_long − b_short ≈ 0.12–0.15 MiB (the name share; OC-402/403).

**Stopping budget (per lifetime; then the node is stopped):**
- T at 2 GiB: OOM, or **M_max = 6,500** CREATEs (above the short-name ceiling; L(6,500) would exceed 2 GiB for any b ≥ 0.31),
  or **40 min** of DDL, or the service-loss criterion held for 10 min without OOM.
- C: N_ctl CREATEs (and N_ctl − 500 DROPs), or 30 min.
- I: N_ctl attempts, or 20 min.
- T at 4 GiB: OOM, or M_max = 12,000, or 50 min of DDL **and** never past 13:55.
- S8: OOM, or M_max = 8,000, or 30 min.

**Validity (every lifetime):** read-back as §2.3; `u14` not a superuser; table count = client's ok count at each checkpoint;
names of 222/48 characters (one `system_schema.tables` row read back); `oom_kill` 0; no other JVM started in the window.

| Observation | Verdict row |
|---|---|
| T OOM 3/3 (heap OOM, dump), C and I survive 3/3, dumps show D1 + D2 dominating (P3), b in or near range | **true positive**: `verified-OOM · deployment`, unprotected (configuration: guardrail −1; accumulation: no byte bound) |
| T OOM, but C also OOMs | **retry**: not attributed to live table state (DDL churn, tombstones, schema transients, or a DROP release defect dominate); report C's L slope and dump |
| T OOM, I also OOMs at X tables | **retry**: the bound did not stop it (X too high or the holder is not per-table); report L(X) |
| T reaches the service-loss criterion but no OOM by the stop | **retry** (`verified-gap · service-loss` if V1–V7 otherwise met); a better design: larger transient per DDL (wider tables) or concurrent DDL clients |
| T reaches M_max with L < 0.9 × heap | **false positive** only if b ≪ 0.3 MiB (the per-table state is not retained at 5.0.9 as measured); otherwise an instrument or harness fault → retry |
| T OOM 1–2/3 | report n/N; true positive with the rate stated if V2/V4 hold; otherwise retry |

### 2.8 Controls and intervention (one setting or one workload step differs per arm)

- **T (test):** long names, `create 1 6500`, all settings default (plus §2.3's environment), 2 GiB. **×3.**
- **C (matched control, churn):** the same names, keyspace, client, statements and order, `churn 1 N_ctl 500` (W = 500 live
  tables): every CREATE of T is issued, plus a DROP 500 behind. N_ctl = N_OOM of H2-T-1 (or 6,500 if T-1 did not OOM). Matches
  DDL count, name lengths, schema-mutation and flush volume, client path and timing; the only difference is that tables do not
  accumulate past 500. Predicted to survive with ≥ 75 % margin (P4). **×3.**
- **I (intervention, add the bound):** the T workload with `tables_fail_threshold: X` (the shipped control, enabled; the user
  is an ordinary role so it applies), **X = floor(0.5 × N_OOM(H2-T-1) / 100) × 100** (fixed by this rule before any I reading;
  ≈ 2,000 predicted); the client issues N_ctl CREATE attempts. Throughput recorded: X ok, N_ctl − X rejected, so a bound that
  stops useful work is visible (it stops table creation past X, by design). **×3.**
- **Budget search:** `H4-T-1` (4 GiB, T workload to 12,000). 8 GiB is not planned (≈ 16,000 tables, quadratic DDL time ≈ 1 h+).
- **Dial (optional) S8:** the T arm at 2 GiB with short names (`ks`, `t00001`…) to separate the name share (OC-402/403) from
  the per-table baseline; one run.

### 2.9 Time plan (2026-11-21, EST; stage 2 ≈ 09:00–14:00; no run starts after 13:15; all stopped and §3–§4 written by 14:00)

DDL-time model (C6, same hardware type): t(n) ≈ 50 ms + 20 ms per 1,000 tables, ×1.5–2 near the endpoint for GC. T to ≈ 4,050:
≈ 6–12 min; C: ≈ 2 × 4,050 statements at ≈ 60 ms ≈ 8–12 min (DROPs snapshot an empty table); I: ≈ 3 min; node start + role
setup ≈ 1 min; dump write + scan ≈ 3–10 min.

| Window | Step |
|---|---|
| 09:00–09:40 | Step A: tree copy, checks, harness, instrument check |
| 09:40–10:00 | Shakedown S0 (2 GiB, 1,000 tables, intervention path check); disk rule decision |
| 10:00–10:20 | `H2-T-1` → fixes N_ctl and X |
| 10:20–10:35 | `H2-C-1` |
| 10:35–10:45 | `H2-I-1` |
| 10:45–11:45 | `H2-T-2`, `H2-C-2`, `H2-I-2` |
| 11:45–12:45 | `H2-T-3`, `H2-C-3`, `H2-I-3` |
| 12:45–13:15 | `H4-T-1` starts (≤ 13:15; DDL cap so that it stops by 13:55) |
| then, if a start ≤ 13:15 is still possible | `S8-1` (only if `H4-T-1` started before 12:45 and has ended) |
| 13:15–14:00 | analysis, `logs/` excerpts, §3, §4, write-back, cleanup |

**Drop order if behind (first dropped first):** `S8-1` → `H4-T-1` (then the budget search is reported as not run; largest
tested budget 2 GiB) → the end dumps of C-1/I-1 (keep their histograms). The nine 2 GiB lifetimes (V1, V2, V4) are never
dropped. **Fallback if `H2-T-1`'s DDL phase exceeds 25 min** (pre-declared): build once a 2,000-table long-name template at
8 GiB (`create 1 2000`, `nodetool drain`, copy `data`/`commitlog`/… to `/mydata/s4/u14/tmpl/`), and start `H2-T-2`, `H2-T-3`
and `H4-T-1` by restoring it and continuing `create 2001 …` (`H2-T-1`, from empty, stays the reference); C and I unchanged.
Record it as a dated amendment before those lifetimes.

**Cleanup at the end:** no Cassandra/Java process of this case on pc99; `/dev/shm/u14` removed; dumps deleted after their
scans are saved; `/mydata/s4/u14/{logs,harness}` kept, the copied tree and run directory may stay (state what is left).

sha256 of §1–§2 at freeze: `968539d5b819ac35d781ff90ecd46328fc68f42ca49d2e722449b9fb1dee8e2f` (sha256 of the lines from `## 1. Candidate` up to, not including, this line)

## 3. Runs (stage 2)

All lifetimes ran on 2026-11-21 08:18–11:18 EST on `pc99`, by the stage-2 session of that day, which was cut off before
writing up (except the owner-approved 4 GiB follow-up `H4-T-2..4` of 2026-11-23, §3.5). This section and §4 were written on 2026-11-23 by a fresh stage-2 session (Claude Opus 5.5, `claude-opus-5-5`)
from the node's logs. That session ran nothing, started no process and deleted nothing on `pc99`. Freeze hash checked
2026-11-23: the lines of §1–§2 hash to `968539d5…1dee8e2f`, equal to the frozen value. The case file's last change before
the runs was at 08:12:53 EST (file mtime), and the first lifetime started at 08:18:43 EST, so the design predates every
reading. Times are America/New_York. The node logs are in MST (two hours behind), and the Cassandra logs are in UTC.

### 3.1 Environment

- **Node `pc99`** = `node4.jason92-326665` (UMass, x86_64, 32 cores, 125 GiB RAM, swap kept at 0 for the JVM by
  `MemorySwapMax=0`, cgroup v2), OpenJDK 11.0.33. Before every lifetime, the harness checked for other JVMs: `cotenancy:
  {"daemons": "none"}` for all twelve, with `MemAvailable` 127,173–127,263 MiB. One measured node at a time; the client ran
  on the same node. Re-checked 2026-11-23 09:23 MST: no `java` process, no `/dev/shm/u14`, `/mydata` 710 GiB free.
- **Build:** `/mydata/s4/u14/cassandra` (copy of `/mydata/s4/cassandra-base`), `build.xml` `base.version` 5.0.9, jar
  `apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `570b5249…a90176e` (re-read 2026-11-23, equal to §2.3). Unmodified: no
  agents, no patches.
- **Configuration (every lifetime, `summary.json` → `settings`, `start`):** read back `authenticator
  PasswordAuthenticator`, `authorizer AllowAllAuthorizer`, `role_manager CassandraRoleManager`, `tables_warn_threshold -1`,
  `tables_fail_threshold -1` (I: `1900`; S0's second start: `1050`), `keyspaces_fail_threshold -1`,
  `columns_per_table_fail_threshold -1`, `memtable_allocation_type heap_buffers`, `memtable_heap_space 512MiB` (4 GiB:
  `1024MiB`), `key_cache_size 100MiB`, `counter_cache_size 50MiB`, `prepared_statements_cache_size 10MiB` (4 GiB:
  `16MiB`), `auto_snapshot true`, `num_tokens 16`: `ok: true` in all twelve. JVM flags checked in every lifetime
  (`flags_ok: true`): `-Xms = -Xmx` 2G (4G), `-XX:MaxDirectMemorySize=15872M`, G1 with `G1HeapRegionSize=16m`,
  `AlwaysPreTouch`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`. Scope `memory.max` 8 GiB (2 GiB heap)
  and 10 GiB (4 GiB heap), `memory.swap.max` 0. Roles: `u14` has `superuser = false` in every lifetime. Data was kept on
  `/mydata` by the §2.5 disk rule: S0's fit was t(n) = 40.9 ms + 28.2 ms per 1,000 tables, so Σ to 4,600 tables is 8.1 min,
  under 25 min, and `shm: false` in every lifetime.
- **Harness** (`harness/`, identical to `/mydata/s4/u14/harness/`, all files diffed 2026-11-23): `run.py` (one lifetime),
  `client.py`, `Jmx.java` (the §2.5 sampler: fixed ObjectNames, `getMBeanCount()`), `HprofScan.java` (the §2.5 scanner,
  written in Java as §2.5 allows), `instrument-check.sh` + `Hold.java`, `analyze.py`, `excerpts.sh`, `plan.sh` +
  `plan-main.txt` (the sequence after `H2-T-1`). Instrument check passed (`logs/instrument-summary.txt`: 1,001 marker
  `byte[]` ≥ 1,000, exactly 500 `long[330]`).
- **Logs:** full logs on `pc99:/mydata/s4/u14/logs/<label>/`. Excerpts in `logs/`: `<label>-summary.json`,
  `-session.log`, `-checkpoints.jsonl` (histogram totals, K, MBeans per checkpoint), `-excerpt.txt` (OOM lines, last GC
  lines, client first/last rows, `memory.events`, heap flags), `-scan-oom.json` / `-scan-end.json` (HprofScan of the dump),
  `-tail-per-minute.txt` (the last 15 min of the sampler for T, H4, S8), `hist/` (top 50 classes of the s0, last and end
  class histograms), `analyze.jsonl` (`analyze.py` over all twelve lifetimes, re-run 2026-11-23; the ten earlier lines
  are unchanged), `plan-main.out` (the sequence log), `instrument-*.{txt,json}`.
- **Dumps:** `plan.sh` deleted each lifetime's `.hprof` right after `run.py` had scanned it. The design kept them until the
  write-up (§2.5), so this is a deviation (§3.4). Only `H2-T-1`'s dump is left
  (`pc99:/mydata/s4/u14/dumps/H2-T-1/cassandra-1795267330-pid1712692.hprof`, 2.54 GB). Each dump was scanned in full
  before it was deleted. P3 therefore comes from the five dump scans (T-1..3 and S8-1 at the OOM; H4-T-1, C-1 and I-1 at
  the end), plus the class histograms.

### 3.2 Runs (in order)

Shakedown **S0** (not a reading, 08:18–08:22): 1,000 long-named tables created at 2 GiB. L = 64.7 → 290.9 → 516.8 MiB at
0 / 500 / 1,000 tables, b = 0.452 MiB per table, 214 MBeans per table, names read back 48 / 222. After a restart with
`tables_fail_threshold: 1050`, `create 1001 1100` as `u14` gave **50 ok + 50 `rejected`** ("Guardrail tables violated:
Cannot have more than 1050 tables"), and `tablecount` read 1,050. So the intervention path works and `u14` is an ordinary
user. `H2-T-1` then fixed **N_ctl = 3,978** and **X = floor(0.5 × 3,978 / 100) × 100 = 1,900** (`harness/plan-main.txt`,
written 08:40 before `H2-C-1`).

| Label | Arm | Heap | Names | EST (life) | Tables created (ok) | Stop reason | L(n) checkpoints (MiB at 0 / 1,000 / 2,000 / 3,000 / last) | b MiB/table (all / from 500) | End reading | Validity |
|---|---|---|---|---|---|---|---|---|---|---|
| H2-T-1 | T | 2G | 48/222 | 08:22–08:40 | **3,978** (last ok 08:38:57) | **heap OOM** (`java.lang.OutOfMemoryError: Java heap space`, dump 2.54 GB, `kill -9`) | 64.7 / 516.8 / 965.4 / 1,519.9 / 1,745.6 @3,500 | 0.480 / 0.487 | old-gen after GC 2,009.7 MiB = **0.981** × heap | ok |
| H2-C-1 | C | 2G | 48/222 | 08:40–08:53 | 3,978 + 3,478 DROPs | end of plan (all 3,978) | 64.7 / 292.8 / 303.5 / 312.6 / 317.7 @3,500 | 0.046 / **0.0094** | U_end 321.7 MiB = 0.157; K 500 | ok |
| H2-I-1 | I (X = 1,900) | 2G | 48/222 | 08:53–08:57 | **1,900**, 2,078 `rejected` | end of plan (3,978 attempts) | 64.7 / 516.8 / – / – / 741.6 @1,500 | 0.451 / 0.451 | U_end 925.3 MiB = 0.452; K 1,900 | ok |
| H2-T-2 | T | 2G | 48/222 | 08:57–09:15 | **3,975** (09:14:08) | **heap OOM** (dump 2.54 GB) | 64.7 / 516.8 / 965.4 / 1,519.7 / 1,745.5 | 0.480 / 0.487 | 2,007.5 MiB = **0.980** | ok |
| H2-C-2 | C | 2G | 48/222 | 09:15–09:27 | 3,978 + 3,478 DROPs | end | 64.7 / 289.8 / 302.6 / 311.8 / 316.8 | 0.046 / **0.0095** | 324.4 MiB = 0.158; K 500 | ok |
| H2-I-2 | I | 2G | 48/222 | 09:27–09:31 | **1,900**, 2,078 rejected | end | 64.7 / 516.8 / – / – / 741.7 | 0.451 / 0.451 | 925.2 MiB = 0.452; K 1,900 | ok |
| H2-T-3 | T | 2G | 48/222 | 09:31–09:49 | **3,976** (09:48:07) | **heap OOM** (dump 2.55 GB) | 64.7 / 516.8 / 965.4 / 1,520.1 / 1,745.9 | 0.480 / 0.487 | 2,012.5 MiB = **0.983** | ok |
| H2-C-3 | C | 2G | 48/222 | 09:49–10:01 | 3,978 + 3,478 DROPs | end | 64.7 / 289.8 / 302.2 / 311.4 / 316.5 | 0.046 / **0.0091** | 320.8 MiB = 0.157; K 500 | ok |
| H2-I-3 | I | 2G | 48/222 | 10:01–10:06 | **1,900**, 2,078 rejected | end | 64.7 / 516.8 / – / – / 741.6 | 0.451 / 0.451 | 925.2 MiB = 0.452; K 1,900 | ok |
| H4-T-1 | T (budget search) | 4G | 48/222 | 10:05–10:53 | **8,027** (8,026 open at the end dump) | **service-loss stop by the harness**: 10 min ≥ 90 % GC at 10:51:54 (44.6 min of DDL). Then end checkpoint, `jcmd` dump, **SIGTERM**. **No OOM** | 64.9 / 517.0 / 969.0 / 1,529.9 / 3,983.1 @8,000 | 0.483 / 0.484 | U_end 3,884.5 MiB = 0.948 (n8000: 0.972); old-gen after GC max 4,020.5 MiB = 0.98 | ok (§3.4) |
| S8-1 | dial (short names) | 2G | 2/6 | 10:53–11:18 | **5,736** (11:16:34) | **heap OOM** (dump 2.70 GB) | 64.7 / 381.5 / 698.8 / 1,009.2 / 1,871.2 @5,500 | **0.336** / 0.339 | 2,008.9 MiB = **0.981** | ok |
| *owner-approved follow-up (2026-11-23), §3.5:* | | | | | | | | | | |
| H4-T-2 | T (budget search) | 4G | 48/222 | 11-23 11:45–12:33 | **8,137** (12:31:38) | **heap OOM** (dump 5.09 GB, `kill -9`) | 64.9 / 517.0 / 968.9 / 1,531.8 / 3,812.3 @8,000 | 0.478 / 0.479 | old-gen after GC 4,048.1 MiB = **0.988** | ok |
| H4-T-3 | T (budget search) | 4G | 48/222 | 11-23 12:34–14:01 | **8,187** (13:41:09) | **heap OOM** (dump 5.08 GB) at 14:00:09 | 64.9 / 517.0 / 969.0 / 1,530.5 / 3,880.5 @8,000 | 0.480 / 0.481 | 4,048.2 MiB = **0.988** | ok |
| H4-T-4 | T (budget search) | 4G | 48/222 | 11-23 14:01–15:07 | **8,225** (15:04:43) | **heap OOM** (dump 5.07 GB) | 64.9 / 517.0 / 969.0 / 1,530.5 / 3,856.5 @8,000 | 0.477 / 0.478 | 4,047.3 MiB = **0.988** | ok |

Every lifetime: K (`count(*)` in `system_schema.tables`) equals the client's ok count at every checkpoint. C holds K = 500
from 500 tables on. `memory.events` `oom_kill 0` and `oom 0` in all twelve, and `max 0` in all but H4-T-1 (§3.4). RssAnon
peak 2.66–2.79 GiB at 2 GiB and 5.0 GiB at 4 GiB, Shmem ≤ 4 MiB. MBeans: 12,073 at s0 and **214 per table** in every T, I
and S8 lifetime (`K_vs_ok`: 119,073 at 500 … 1,724,073 at 8,000 tables). Names 48 / 222 were read back
(`system_schema.tables`) in S0, every C, every I and H4-T-1. The lifetimes that died have no read-back, but their dumps carry
the marker (T) or lack it (S8, §3.3).

### 3.3 Readings

**T at 2 GiB (P1, P2).** L(n) is linear: 64.7 → 290.9 → 516.8 → 741.7 → 965.4 → 1,189.4 → 1,519.9 → 1,745.6 MiB at 0, 500,
…, 3,500 tables, identical to ±0.4 MiB across the three repetitions. **b = 0.480 MiB per table** (0.487 from 500). The step of
+330 MiB between 2,500 and 3,000 tables, against +224 per 500 elsewhere, is the first five-minute `SizeEstimatesRecorder`
pass. It fills the `system.size_estimates` / `table_estimates` memtables (histogram diff n2500 → n3000: `byte[]` +134,
`HeapByteBuffer` +36, `BufferCell` +10 MiB). D3 (`AllMemtablesOnHeapDataSize`) then sits at **≤ 170.7 MiB**, which is the
memtable cleaner threshold (512 MiB × 1/3; flushes logged `Reason: MEMTABLE_LIMIT`). DDL latency medians per 500 tables:
48, 64, 81, 98, 115, 136, 162 ms, then 598 ms for 3,501–3,978. The last CREATEs took 12–47 s: the runs were GC-bound, with
≥ 90 % of wall time in GC over 60 s for the last 0.5–0.8 min (gc 66 → 96 % per minute from ≈ 3,640 tables on,
`logs/H2-T-*-tail-per-minute.txt`). Old-gen after collection at the last sample: 2,007.5–2,012.5 MiB of 2,048. The last
`GCInspector` lines show full GCs recovering ≈ 10–20 MB (`G1 Old Gen: 2,119,831,864 -> 2,109,699,016`).

**Initiating failure (V5).** In stdout of all three T lifetimes: `java.lang.OutOfMemoryError: Java heap space`, then
`Dumping heap to …`, `Heap dump file created [2,540,062,295 / 2,542,044,136 / 2,546,564,516 bytes]`, then `Executing
/bin/sh -c "kill -9 <pid>"` (`logs/H2-T-*-excerpt.txt`). Nothing reached `system.log`, because the kill came first. The
throwing thread's stack is in the dump (the only trace with `OutOfMemoryError.<init>`):
- T-2: `PerDiskMemtableFlushWriter`, `Slice.make` ← `RangeTombstoneList.rangeTombstone` ← `RowAndDeletionMergeIterator` ←
  `SortedTableWriter.append:148` ← `Flushing$FlushRunnable.writeSortedContents:171`. This is a memtable flush. The last
  log line before it is `Enqueuing flush of system.table_estimates, Reason: MEMTABLE_LIMIT, Usage: 93.530MiB`.
- T-3: the same flush path (`Columns.inOrderInclusionTester` ← `BTreeRow.filter` ← `SortedTableWriter.append:148`).
- T-1: no trace in its dump carries `OutOfMemoryError.<init>` (70 traces). The request thread is parked in
  `SchemaKeyspace.flush:367` ← `SchemaKeyspace.applyChanges:1428` ← `AlterSchemaStatement.execute`, waiting on the
  schema flush of CREATE 3,979.

In every case, a background allocation failed after the heap had filled with the standing per-table state, which is the
second outcome §2.1 predicted ("a GC-starved background thread").

**Dumps at the OOM (P3)** (`logs/H2-T-*-scan-oom.json`):

| | T-1 | T-2 | T-3 |
|---|---|---|---|
| `TableMetrics` / `ColumnFamilyStore` instances | 4,026 / 4,026 = **3,978 + 48** system tables | 4,023 = 3,975 + 48 | 4,024 = 3,976 + 48 |
| total shallow (live dump) | 2,013.5 MiB | 2,014.1 MiB | 2,018.1 MiB |
| marker `byte[]` (contain `x` × 64: strings carrying the table name) | 2,175,836 arrays, **789.4 MiB = 39.2 %** = 0.198 MiB per table | 794.1 MiB = 39.4 % | 794.3 MiB = 39.4 % |
| `long[]` (reservoir and histogram buckets) | 551 MiB (of which `long[330]` 72,664 = 184.1 MiB) | 547 MiB | 549 MiB |
| JMX and metric objects (`ObjectName` 863,371; `ObjectName$Property` 3.44 M; `NamedObject` / `StandardMBeanSupport` 863 k; `LongAdder`, `EWMA`, `JmxGauge`…; `String`, map nodes) | ≈ 370 MiB | ≈ 370 MiB | ≈ 370 MiB |
| per-table classes (marker `byte[]` + `long[]` + JMX/metric/schema classes + `String` + map nodes) | **1,707.8 MiB = 84.8 %** | 84.8 % | 84.7 % |
| memtable classes (`HeapByteBuffer`, `BufferCell`, `BTreeRow`…: D3) | 124.8 MiB (6.2 %) | 125.6 MiB | 127.1 MiB |

Per-class slopes of the histograms from s0 to 3,500 tables (`analyze.jsonl`), in bytes per table and instances per table:

| Class | B / table | instances / table |
|---|---|---|
| `byte[]` | 209,750 | 644 |
| `long[]` | 141,288 | 69 |
| `ObjectName$Property` | 20,496 | 854 |
| `String` | 15,240 | 635 |
| `ObjectName$Property[]` | 13,696 | 428 |
| `HeapByteBuffer` (D3) | 11,795 | 246 |
| `HashMap$Node` | 10,706 | 335 |
| `ObjectName` | 6,848 | 214 |
| `ConcurrentHashMap$Node` | 6,408 | 200 |
| `LongAdder` | 6,112 | 191 |
| `NamedObject` | 5,136 | 214 |
| `StandardMBeanSupport` | 5,136 | 214 |
| `EWMA` | 5,040 | 105 |

The per-class slopes total 503.6 KB per table. `CassandraMetricsRegistry$MetricName` has **0** live instances in every
histogram and dump: the `MetricName` objects are not retained, and the name copies live in the JMX `ObjectName` /
`Property` strings and the registry's keys.

**C (P4, V2).** 3/3 survived the same 3,978 CREATEs with the same names, order and client, plus a DROP 500 behind (3,478
DROPs, all ok). L stays at 290–318 MiB from 500 tables on, with a slope after 500 of **0.0091–0.0095 MiB per CREATE+DROP
pair** and U_end 320.8–324.4 MiB = **0.157–0.158 × heap**. MBeans stay at 119,073. D3 ≤ 8.4 MiB, worst 60 s GC fraction
1.1–1.2 %, no OutOfMemoryError. DDL latency 53 → 71 ms. C-1's end dump: `TableMetrics` / `ColumnFamilyStore` 548 = 500 + 48.
The small residual (+28.9 MiB from 1,000 tables to the end, ≈ 10 KB per pair) is mostly 38,714 queued
`ScheduledFutureTask`s of `AbstractAllocatorMemtable$1`, plus `byte[]` / `String` / `HashMap$Node`. `TableMetadata`
instances are 4,075 against 548 live stores, which suggests the metadata of dropped tables is still referenced. That is ≈ 1 %
of the T slope, and at that rate it would take ≈ 170,000 pairs to fill 2 GiB. It is not claimed and was not pursued.

**I (P5, V4).** 3/3: exactly **1,900 ok** and then **2,078 `rejected`** (`Guardrail tables violated: Cannot have more than
1900 tables, aborting the creation of table t01901…`). No other error and no OutOfMemoryError. L(1,500) = 741.6 MiB, as in
T. **U_end 925.2–925.3 MiB = 0.452 × heap**, flat after the bound: the last GCInspector lines show
`G1 Old Gen: 970,209,336 -> 970,209,264`, with no growth from the 2,078 rejected statements. b = 0.451 MiB per table.
I-1's end dump: 1,948 `TableMetrics` = 1,900 + 48, marker `byte[]` 352.7 MiB (38.2 %), per-table classes 86.4 %. Useful
work is stated plainly: the bound stops table creation at 1,900 by design.

**H4-T-1 (4 GiB, P6).** Same T workload to 12,000. L grew from 64.9 to 3,983.1 MiB at 8,000 tables (**b = 0.483**, 214 MBeans
per table). The per-1,000-table latency medians were 57, 90, 126, 163, 204, 246, 291 and then 839 ms, with 2.9 s for
8,001–8,027. GC per minute rose from 51–65 % (10:37–10:41) to **87–98 %** (10:42–10:51), with 99–111 full GCs per minute,
old gen after collection 3,903–3,997 MiB (0.95–0.98 × heap), and 3–19 CREATEs per minute
(`logs/H4-T-1-tail-per-minute.txt`). The last GCInspector lines read `G1 Old Gen: 4,171,217,184 -> 4,087,331,624`.

The harness's service-loss monitor (600 s window ≥ 0.9) fired at 10:51:54 at 0.900, after 44.6 min of DDL. `run.py` then
read the names (48 / 222) and took the end checkpoint: K = 8,027, U_end 3,884.5 MiB = 0.948 × heap, 1,729,637 MBeans. It
wrote a 4.88 GB end dump with `jcmd` and stopped the node with **SIGTERM** at 10:52:38. The client's "Server is shutting
down" errors (27) and the final `ConnectionShutdown` come from that SIGTERM: `system.log` shows `StorageServiceShutdownHook`
… `Cassandra shutdown complete`. **No OutOfMemoryError occurred in this lifetime.** The only stdout line containing
"OutOfMemoryError" is HotSpot's `CompileCommand: exclude …JVMStabilityInspector.forceHeapSpaceOomMaybe(Ljava/lang/OutOfMemoryError;)V`
at startup, which is present in every lifetime. End dump (`logs/H4-T-1-scan-end.json`): `TableMetrics` /
`ColumnFamilyStore` 8,074 = 8,026 + 48 (CREATE 8,027's schema row existed but its store was not yet open). Total 3,881.4
MiB, marker `byte[]` 1,561.7 MiB = **40.2 %** (0.195 MiB per table), per-table classes **87.2 %**, memtable classes 155.4 MiB.

**S8-1 (short names, P7).** Keyspace `ks`, tables `t00001`…, 2 GiB. L(n) linear: 64.7 → 223.1 → 381.5 → … → 1,871.2 MiB at
5,500 tables, **b_short = 0.336 MiB per table** (0.339 from 500), 214 MBeans per table. The size-estimates step came between
3,000 and 3,500 tables (+255 MiB). **Heap OOM at 5,736 tables** (last ok 11:16:34). The run was GC-bound from 11:09
(89–99 % per minute) and old gen after collection was 2,008.9 MiB = 0.981 × heap. Stdout has `java.lang.OutOfMemoryError:
Java heap space` → `Heap dump file created [2,702,416,663 bytes]` → `kill -9`. The throwing thread is
`SizeEstimatesRecorder.run:104` → `SystemKeyspace.updateTableEstimates:1644` → `Mutation.apply` → `SkipListMemtable.put`
→ `RangeTombstoneList.grow`. Dump: `TableMetrics` / `ColumnFamilyStore` 5,784 = **5,736 + 48**, marker `byte[]` **0**
(no long names, as expected), `long[330]` 104,308 (264.2 MiB), `byte[]` 346.7 MiB, `ObjectName` 1,239,582. The per-class
`byte[]` slope is 57,797 B per table (652 arrays), against 209,750 B (644 arrays) with long names: the same number of
strings per table, ≈ 152 KB shorter.

### 3.4 Deviations

- **Dumps deleted early.** `plan.sh` removed each `.hprof` after `run.py`'s scan (`rm -f $W/dumps/$label/*.hprof`), so the
  T-2, T-3, S8-1, H4-T-1 end, C-1 end and I-1 end dumps are gone. Their full-pass scans were saved first. `H2-T-1`'s dump
  is still on `pc99` (2.54 GB, left for the owner; this session deletes nothing). Effect: P3 rests on the saved scans
  (instance counts, marker and `long[330]` tallies, top 40 classes, thread traces) and the histograms. No retained-size
  or dominator analysis was made or is possible for the deleted dumps.
- **The service-loss stop also applied at 4 GiB.** §2.7 lists "service-loss criterion held for 10 min" only for T at
  2 GiB. For 4 GiB it lists OOM, M_max 12,000, or 50 min of DDL. `run.py`'s monitor applied it to every arm. H4-T-1 was
  stopped by it at 44.6 min of DDL, 5.4 min before its DDL cap, so the 4 GiB lifetime did not run its full stopping budget.
  Whether it would have ended in an OOM within the remaining 5.4 min is unknown. *(2026-11-23: the owner approved three more
  4 GiB lifetimes without this stop and with a 120-min DDL cap; all three ended in a heap OOM, §3.5.)*
- **The H4 client was not stopped.** The monitor's `p.kill()` killed the `sh -c` wrapper, not `client.py`, so the client
  kept one CREATE (8,027) in flight through the end checkpoint and the dump. It was acknowledged at 10:52:42, after the
  SIGTERM, and the client then logged the shutdown errors. The end readings therefore correspond to 8,026–8,027 tables.
  *(Fixed 2026-11-23, §3.5.)*
- **H4-T-1 `memory.events` `max 4543`.** The 10 GiB safety scope reached `memory.max` only between 10:52:29 and 10:52:37
  (`rss.csv` `cg_current`), while `jcmd` wrote the 4.88 GB end dump through the page cache. That was after the workload
  had stopped; RssAnon was 4.88 GiB at that moment, with `oom 0` and `oom_kill 0`. No reading is affected.
- **`run.py`'s OOM-line grep** also matches the startup `CompileCommand … OutOfMemoryError` line, so the `oom.stdout_lines` of
  the T and S8 summaries list it first. The real lines follow it. This analysis uses the real lines only, from `grep -n
  "^java.lang.OutOfMemoryError"`. *(Fixed 2026-11-23, §3.5.)*
- **Schedule:** the runs took place 08:18–11:18 EST, earlier than the 09:00–14:00 plan of §2.9. No lifetime started after
  13:15, and S8-1 started after H4-T-1 had ended, as §2.9 requires. The 2,000-table template fallback was not needed:
  `H2-T-1`'s DDL took 15.7 min.
- **Sampler and scanner names:** `Jmx.java` and `HprofScan.java` in place of `Sampler.java` and `hprof_scan.py`. The function
  is as designed, and the instrument check passed.
- **Checkpoint histograms:** in `H2-T-1` at n2500 (and H4 at n2500), the first of the two histograms read more than the
  second (1,685.6 vs 1,247.2 MB). L is the second one by definition (§2.6), so no reading changes.
- **Write-up** by a different session two days after the runs, from logs only (see the top of §3). No run was repeated.

### 3.5 Owner-approved follow-up (2026-11-23): 4 GiB budget search ×3 without the service-loss stop

**Approval and scope.** On 2026-11-23 the owner approved three more lifetimes of the 4 GiB budget-search arm (`H4-T-2`,
`H4-T-3`, `H4-T-4`), because `H4-T-1` had been stopped by a rule the design sets only for 2 GiB (§3.4). Changes against
`H4-T-1`, all owner-approved: **no service-loss stop** at 4 GiB; **DDL cap 120 min** per lifetime (was 50 min); M_max 12,000
unchanged; every other stop rule kept (OOM / node death, M_max, the wall cap = DDL cap + 15 min, node stopped on any exit).
Workload, names, build, configuration, scope (10 GiB, swap 0) and shipped OOM flags (`HeapDumpOnOutOfMemoryError`,
`OnOutOfMemoryError=kill -9 %p`) as `H4-T-1`. Run by a stage-2 session (Claude Opus 5.5, `claude-opus-5-5`), sequentially,
one lifetime at a time, under `setsid nohup` (`plan.sh harness/plan-h4-followup.txt`, log `logs/plan-h4-followup.out`).
The 13:15 no-start rule of §2.9 was the time plan of 2026-11-21 and was not applied. §1–§2 are unchanged.

**Harness changes** (`harness/NOTE-2026-11-23.txt`; `run.py`, `excerpts.sh`; new `tailmin.py`, `gcshare.py`,
`plan-h4-followup.txt`): (1) the service-loss stop applies only to T at 2 GiB, as §2.7 lists it; (2) T at 4 GiB DDL cap 7,200 s,
wall cap 8,100 s; (3) **bug (a) fixed**: OOM lines are matched only as a real `java.lang.OutOfMemoryError` line at runtime
(`^java.lang.OutOfMemoryError:`, `# java.lang.OutOfMemoryError:`, `Exception in thread … java.lang.OutOfMemoryError`), never
a line containing `CompileCommand`; the summaries carry `real_oom` / `first_real_oom` (all three: `real_oom: true`, first line
`java.lang.OutOfMemoryError: Java heap space`; the startup `CompileCommand` lines are no longer listed); (4) **bug (b) fixed**:
the client is started without a shell in its own session and a monitor stop kills its whole process group (`os.killpg`,
checked on pc99 with a child process before the runs). No monitor stop fired in these lifetimes (each ended by node death),
so fix (b) was not exercised in a lifetime.

**Environment and validity.** Before the runs (2026-11-23 09:44 MST): no `java` process on pc99, load 0.00, `/mydata` 710 GiB
free, `/dev/shm` empty; the harness's co-tenancy check read `daemons: none` and `MemAvailable` 127,170–127,196 MiB before each
lifetime. Every lifetime: settings read-back `ok` (`memtable_heap_space 1024MiB`, `prepared_statements_cache_size 16MiB`,
guardrails −1, `PasswordAuthenticator` / `AllowAllAuthorizer`), `flags_ok`, `scope_ok` (10 GiB, swap 0), `u14` not a
superuser, `shm: false`; K = the client's ok count at all 16 checkpoints (500 … 8,000); 214 MBeans per table (1,724,073 at
8,000 tables). `memory.events`: `oom 0`, `oom_kill 0`; `max` 7,065 / 4,480 / 4,092, all reached 23–44 s **after** the heap dump
file was created, while the 5 GB dump was written through the page cache (as in `H4-T-1`, §3.4); RssAnon peak 4.9–5.0 GiB.
The lifetimes that died have no name read-back; their dumps carry the marker (below).

**Readings** (`logs/H4-T-{2,3,4}-*`, `logs/hist/H4-T-{2,3,4}-*`, `analyze.jsonl` lines 13–15; times EST):

| | H4-T-2 | H4-T-3 | H4-T-4 |
|---|---|---|---|
| Endpoint | **heap OOM** (`java.lang.OutOfMemoryError: Java heap space` → dump → `kill -9`, exit 137) | **heap OOM** | **heap OOM** |
| N_OOM (last ok CREATE before the dump) | **8,137** | **8,187** | **8,225** |
| first CREATE → dump file | 11:47:22 → 12:32:45 = **45.4 min** (47.0 from JVM launch) | 12:35:34 → 14:00:09 = **84.6 min** (86.2) | 14:03:00 → 15:06:03 = **63.0 min** (64.6) |
| client DDL time; last ok → dump | 2,712 s; 67 s | 5,051 s; **1,139 s** (19 min without progress, 9 timeouts of 120 s) | 3,761 s; 80 s |
| b (MiB per table, all / from 500) | 0.478 / 0.479 | 0.480 / 0.481 | 0.477 / 0.478 |
| L(n) at 0 / 4,000 / 8,000 (MiB) | 64.9 / 1,992.4 / 3,812.3 | 64.9 / 1,991.1 / 3,880.5 | 64.9 / 1,991.0 / 3,856.5 |
| f: L(8,000) / heap; old gen after GC at the last sample | 0.931; 4,048.1 MiB = **0.988** | 0.947; 0.988 | 0.942; 0.988 |
| DDL latency (median first / last 200 CREATEs) | 44 / 1,467 ms | 45 / 3,508 ms | 45 / 3,006 ms |
| GC (sampler, per minute) | 45–58 % from 12:13, 87–95 % 12:22–12:24, 95–102 % 12:30–12:32 | 50–75 % from 13:03, **79–99 % every minute 13:13–13:41**, then sampler gaps and readings > 100 % (JMX starved) until the OOM | 84–95 % from 14:41, 74–101 % to 15:05 |
| GC (shipped `gc.log*`, which rotate and cover only the last ≈ 5 min) | 96 / 98 / 99 % STW in 12:30–12:32 | **99–100 % STW in 13:55–13:59** | 96 / 98 / 98 % STW in 15:03–15:05 |
| last GCInspector lines | `G1 Old Generation GC in 39,295 ms. G1 Old Gen: 4,201,263,896 -> 4,184,539,176` | `… GC in 104,285 ms. G1 Old Gen: 4,192,877,768 -> 4,133,360,168` | `… GC in 45,844 ms. G1 Old Gen: 4,235,303,192 -> 4,185,535,224` |
| D3 max (`AllMemtablesOnHeapDataSize`) | 341.8 MiB | 341.6 MiB | 341.7 MiB (memtable cleaner threshold 1,024 / 3) |
| dump total (shallow) | 4,046.9 MiB | 4,046.7 MiB | 4,044.2 MiB |
| `TableMetrics` / `ColumnFamilyStore` | 8,185 = **8,137 + 48** | 8,235 = **8,187 + 48** | 8,273 = **8,225 + 48** |
| marker `byte[]` (name text) | 4,448,940 arrays, 1,629.2 MiB = **40.3 %** (0.200 MiB per table) | 1,641.4 MiB = **40.6 %** (0.200) | 1,639.8 MiB = **40.5 %** (0.199) |
| `long[]` (of which `long[330]`) | 1,107.5 MiB (373.7) | 1,112.2 MiB (376.0) | 1,117.4 MiB (377.7) |
| per-table classes (`byte[]`, `long[]`, `String`, `ObjectName`, `ObjectName$Property` and `[]`, `NamedObject`, `StandardMBeanSupport`, `LongAdder`, `HashMap$Node`, `ConcurrentHashMap$Node`) | **86.2 %** | **86.6 %** | **86.8 %** |
| memtable classes (`HeapByteBuffer`, `BufferCell`, `BTreeRow`) | 137.5 MiB | 143.1 MiB | 133.8 MiB |
| throwing thread (the dump trace with `OutOfMemoryError.<init>`) | a Netty `FastThreadLocalRunnable` thread in `FastThreadLocal.removeAll:65` (thread exit) | none of the dump's traces carries `OutOfMemoryError.<init>` (as `H2-T-1`) | `SizeEstimatesRecorder.run:103` → `SystemKeyspace.updateSizeEstimates:1617` → `Mutation.apply` → `SkipListMemtable.put` → `RangeTombstoneList.grow:713` |
| `.hprof` | scanned in full, then deleted by `plan.sh` | same | same |

`CassandraMetricsRegistry$MetricName` is again 0 in every dump. The same 11-class share computed on `H4-T-1`'s end dump gives
87.4 %, so these shares are comparable with §3.3 (87.2 % there). Per-class histogram slopes from s0 to 8,000 tables total
491–497 KB per table (`analyze.jsonl`), as at 2 GiB.

**Readings against the 2026-11-21 stop rules.** Under `H4-T-1`'s 50-min DDL cap, `H4-T-2` (45.2 min of DDL) would still
have reached its OOM, while `H4-T-3` (84.2 min) and `H4-T-4` (62.7 min) would have been stopped first. The 10-min
service-loss stop (sampler GC fraction ≥ 0.9 over 600 s, `run.py`'s rule, recomputed from `sampler.csv`) would not have
fired in `H4-T-2` (maximum 0.831), and would have stopped `H4-T-3` at 13:19:15 (41 min before its OOM) and `H4-T-4` at
14:56:56 (9 min before); `H4-T-1` reached 0.903 at 10:51:53 and was stopped. Without these stops every lifetime ended in the
OOM, after a GC-bound stretch of ≈ 3 min (`H4-T-2`) to ≈ 45 min (`H4-T-3`).

**Deviations (follow-up).** The changes above are owner-approved amendments to the stopping budget of the 4 GiB arm only. The
dumps were deleted after their full scans (as on 2026-11-21; now allowed by the owner), so no dominator analysis exists. The
`gc.log*` files cover only the last ≈ 5 min of each lifetime (shipped rotation, 10 files, with `heap*=trace`); the longer GC
history comes from the sampler's JMX `CollectionTime`, which reads above 100 % for some minutes when JMX itself is starved
(`H4-T-3` 13:40–14:00). The H4-T-3 dump birth (14:00:09) is 19 min after its last ok CREATE; N_OOM is the table count, not
a time.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status (detail): **`verified-OOM · deployment`**, **unprotected**. This is an
unprotected configuration (`tables_warn_threshold` / `tables_fail_threshold` = −1, the shipped default) and an unprotected
accumulation (no byte bound covers the per-table metrics, JMX and schema state). Interpretation: configuration-sizing gap
(the count guardrail ships disabled and nothing charges per-table heap). It is known upstream as heavy and is reduced only in
6.0 (CASSANDRA-19567), and the per-table memory cost is not documented as by design.

| Condition (2 GiB unless stated; long names 48 / 222) | Result |
|---|---|
| T: empty tables created one by one, guardrail −1 | **heap OOM 3/3** at **3,978 / 3,975 / 3,976** tables, f = 0.980–0.983 |
| C: same CREATEs plus DROP 500 behind (≤ 500 live) | 0/3; U_end 0.157–0.158 × heap, slope 0.009 MiB per pair |
| I: `tables_fail_threshold` = 1,900 | 0/3; 1,900 ok, 2,078 rejected, U_end 0.452 × heap |
| T at **4 GiB** (budget search), `H4-T-1` (2026-11-21) | **no OOM**: GC service loss (87–98 % GC per minute for ≈ 10 min) at 7,916–8,027 tables, live 0.95–0.98 × heap; stopped by the harness's service-loss monitor at 44.6 of 50 min of DDL (§3.4) |
| T at **4 GiB**, `H4-T-2..4` (owner-approved follow-up, 2026-11-23: no service-loss stop, 120-min DDL cap, §3.5) | **heap OOM 3/3** at **8,137 / 8,187 / 8,225** tables, 45.4 / 84.6 / 63.0 min after the first CREATE; old gen after GC 0.988 × heap; dumps 86–87 % per-table classes |
| S8: T at 2 GiB with short names (`ks`, `t00001`) | heap OOM 1/1 at **5,736** tables |

**Predictions against readings (frozen §2.7):**

| | Predicted | Read | |
|---|---|---|---|
| P1 | b = 0.42–0.52 (central 0.47) MiB per table; 200–240 MBeans per table; D3 ≤ 20 MiB | b = **0.480** (0.487 from 500) 3/3; **214** MBeans per table; D3 rose to **170.7 MiB** (the memtable cleaner threshold), from the size-estimates tables | b, MBeans **met**; D3 sub-prediction **missed** (D3 grows with the table count too, but within its own pool) |
| P2 | heap OOM 3/3 at N_OOM 3,520–4,630 (central 4,050), f = 0.93–0.98; latency ≈ 50 → 150 ms, then GC-bound in the last ≈ 5 % | OOM **3/3** at 3,975–3,978; f = 0.980–0.983 (old gen after GC; 0.852 at the last checkpoint, 3,500); latency 48 → 162 ms by 3,500, GC-bound from ≈ 3,640 (≈ 8 %) | **met** (f at the top edge) |
| P3 | `TableMetrics` = `ColumnFamilyStore` = N_OOM + system tables; per-table classes ≥ 70 % of live heap; marker `byte[]` ≥ 0.08 MiB per table, name share ≥ 15 % | 4,026 / 4,023 / 4,024 = N_OOM + 48 exactly; per-table classes **84.7–84.8 %**; marker `byte[]` **0.198 MiB per table, 39.2–39.4 %** | **met** (dump scans; dominators not available, §3.4) |
| P4 | C: no OOM 3/3, U_end ≤ 0.25 × heap, slope after 500 ≤ 0.02 MiB per pair | 0/3, 0.157–0.158, 0.0091–0.0095 | **met** |
| P5 | I: no OOM 3/3, exactly X created, the rest rejected, U_end ≈ L(X) ≤ 0.6 × heap | 0/3, 1,900 + 2,078 rejected, 0.452 | **met** |
| P6 | 4 GiB: OOM at 7,180–9,410 | 2026-11-21: **no OOM** in 1 lifetime; service loss at 7,916–8,027, stopped early by the harness. **2026-11-23 follow-up: heap OOM 3/3 at 8,137 / 8,187 / 8,225** (b = 0.477–0.480, f = 0.988) | **met** (3/3, near the central 8,230; owner-approved follow-up, §3.5) |
| P7 | S8: OOM at 5,500–6,170; b_long − b_short = 0.12–0.15 MiB | OOM at **5,736**; 0.480 − 0.336 = **0.143** (0.487 − 0.339 = 0.148) | **met** |

**V1–V7 (condition: stock 5.0.9, 2 GiB heap, defaults, long names, one DDL client):**

| | Evidence |
|---|---|
| V1 Repetition | H2-T-1..3: heap OOM 3/3 from clean starts (fresh run directory each time), N_OOM 3,975–3,978 |
| V2 Matched control | H2-C-1..3: 0/3 with the same node, build, heap, keyspace, names, client, CREATE count (3,978) and order. Tables do not accumulate past 500. U_end 0.157–0.158 × heap |
| V3 Measurement | U = class-histogram totals (L(n) at every 500 tables, after two forced full GCs) and dump scans, measured independently of K (`count(*)` of `system_schema.tables`), which matched the client's count at every checkpoint. Per-table U = 0.480 MiB; at the OOM, 84.8 % of the live dump is per-table classes |
| V4 Intervention | H2-I-1..3: `tables_fail_threshold` = 1,900 (the shipped guardrail, enabled; `u14` an ordinary role) removed the OOM 3/3. Rejections 2,078 / 3,978 attempts, and the live heap stays at 0.452 × heap |
| V5 Initiating failure | first error `java.lang.OutOfMemoryError: Java heap space` in stdout 3/3, then the dump and the shipped `kill -9`. Throwing thread: memtable flush writer (`SortedTableWriter.append:148` ← `Flushing$FlushRunnable`) in T-2 and T-3; not identified in T-1's dump. Holder at failure: dumps with 4,026 `TableMetrics`, marker `byte[]` 39 %, per-table classes 85 % |
| V6 Default constraints | `tables_*` and `keyspaces_*` guardrails −1, `columns_per_table_*` −1, name caps 222 / 48 (compile-time), memtable pool 512 MiB (heap/4), caches auto (100 / 50 / 10 MiB), all read back. `tables_fail_threshold` differs only in arm I |
| V7 Acceptable budget | 2 GiB heap, the ideal, and what `cassandra-env.sh` resolves on a 4 GiB-RAM host; ≥ 512 MiB under the standing rule. Direct limit 15,872 MiB, as resolved on `pc99` and not involved. The 8 GiB scope (10 GiB at 4 GiB heap) is a safety guard only (`oom_kill 0`) |

**At 4 GiB (follow-up, 2026-11-23).** The same condition at a 4 GiB heap (what `cassandra-env.sh` resolves on an 8 GiB host)
meets V1 (heap OOM 3/3 from clean starts, `H4-T-2..4`), V3 (L(n) and dump scans, K = ok count), V5 (first error
`java.lang.OutOfMemoryError: Java heap space` 3/3, dumps with `TableMetrics` = N_OOM + 48, marker `byte[]` 40 %), V6 and V7
(≥ 512 MiB). Its matched control and intervention (V2, V4) were run at 2 GiB only; the 4 GiB endpoint is the same mechanism
at the same per-table slope (b = 0.477–0.480 against 0.480), so it is reported as the budget-search result of the verified
condition, not as a separately verified condition.

**Deployment label.** Every setting is a default or an accepted, documented value (`PasswordAuthenticator`, the documented
production authenticator, used in every arm so that the guardrail applies to an ordinary role, §2.3). There is no patch and
no agent. The forced full GCs of the checkpoints are identical in all arms and only remove garbage, so they cannot add to
the holder.

**Reason.** On a stock Cassandra 5.0.9 node with a 2 GiB heap and every capacity setting at its default, an ordinary role
created empty tables one at a time in one keyspace. The tables had 222-character names in a keyspace with a 48-character
name, and no row was written. Each table added **0.480 MiB** of live heap that stays for the table's life. The histograms and
dumps show that it is mostly the eager per-table metrics: 214 JMX MBeans per table (107 metrics under the `Table` and
`ColumnFamily` names), their `ObjectName` / property strings carrying the keyspace and table names (`byte[]` 205 KB and
`String` per table), and their reservoir and histogram `long[]` buckets (138 KB per table). The table-count guardrail ships
at −1 and no byte budget charges this state, so the live heap grew linearly and the node died with `OutOfMemoryError: Java
heap space` at 3,975–3,978 tables in 3/3 runs, with 98 % of the heap live and 85 % of the dump in per-table classes. The
same 3,978 CREATEs with a DROP 500 behind never passed 0.16 × heap (0/3), and enabling the shipped guardrail at 1,900
tables stopped the growth at 0.45 × heap (0/3). The failure therefore follows the number of live tables, which nothing
bounds at defaults, and not the DDL traffic.

**Budget search (updated 2026-11-23).** The largest budget that reached the endpoint is **4 GiB (3/3)**; 2 GiB also 3/3.
On 2026-11-21 the one 4 GiB lifetime (`H4-T-1`) reached 8,027 tables in sustained GC service loss and was stopped by the
harness's service-loss rule, which the design sets only for 2 GiB (§3.4). In the owner-approved follow-up of 2026-11-23
(no service-loss stop at 4 GiB, DDL cap 120 min, §3.5) the same workload ended in `OutOfMemoryError: Java heap space` in
**3/3** lifetimes at **8,137 / 8,187 / 8,225** tables (P6: 7,180–9,410, central 8,230), **45–85 min** after the first CREATE,
each after a GC-bound stretch of ≈ 3 to ≈ 45 min (≥ 79 % GC per minute, 96–100 % STW in the last minutes). The time to OOM
varies more than N_OOM does: the end is decided by GC thrash on a heap that is 0.99 live, and two of the three lifetimes
would not have reached it under `H4-T-1`'s 50-min DDL cap. 8 GiB was not planned (§2.8; ≈ 16,000 tables at ≈ 0.48 MiB, with
the DDL already at seconds per CREATE near 8,000 tables), so the upper boundary of the failing budgets is not established;
4 GiB is the largest **tested** failing budget.

**The name-length dial (OC-402 / OC-403).** Short names (`ks`, 6-character tables) cost **0.336 MiB per table** and failed at
**5,736** tables. Long names cost **0.480**, and the difference of **0.143 MiB per table** for 216 + 46 = 262 more
characters is **≈ 574 B per name character per table**, which agrees with stage 4's ≈ 567 B. So the name text is ≈ 30 % of
the long-name per-table cost and moves N_OOM at 2 GiB from ≈ 5,700 to ≈ 4,000 tables. The long names are not needed for the
OOM. The 222- and 48-character caps bound one name each and nothing in total. The baseline per-table cost without long
names (0.34 MiB) agrees with C6's D2 (0.316–0.342).

**Limits of attribution.**
- One node and one DDL client issuing serial CREATEs. Concurrent DDL, many keyspaces (OC-400's `KeyspaceMetrics` variant)
  and written tables (the slab region of OC-400/401, C6's holder) were not run.
- No retained-size (dominator) analysis. P3 uses shallow class totals from full dump scans and histogram slopes, and only
  `H2-T-1`'s dump still exists.
- D3 (the size-estimates memtables, which also grow with the table count) holds ≈ 125–170 MiB at the endpoint. It is bounded
  by `memtable_heap_space` and flushed at its cleaner threshold, and it is not claimed. It supplies the last allocations in
  T-2, T-3 and S8 (flush writer, `SizeEstimatesRecorder`).
- The 4 GiB result is 3/3 OOM (follow-up, 2026-11-23) plus `H4-T-1`, which was stopped by a rule the design did not set for
  that heap. No control or intervention lifetime was run at 4 GiB, and 8 GiB was not run.
- The C residual (≈ 10 KB per CREATE+DROP pair, queued `AbstractAllocatorMemtable$1` tasks and dropped tables' metadata) is
  noted only.
- Covered duplicates: OC-402 (name text, measured by S8 and the marker scan) and OC-403 (keyspace-name text, in every long
  arm) fully. OC-401 covers the empty-table part only; its slab part is C6's. OC-400 is covered partly: the per-table cost
  with the table guardrail off is covered, but its many-keyspaces variant was not run.
- **Owner's ruling (2026-11-23): OC-400 stays `open`** in the phase 1 candidate list, since its many-keyspaces variant
  (`KeyspaceMetrics` per keyspace, `keyspaces_*` guardrails) was not run here.

**What is left on `pc99`** (checked 2026-11-23 09:23 MST): no Cassandra, Java or harness process, and no `/dev/shm/u14`.
`/mydata/s4/u14/` holds `cassandra/` (the build copy), `harness/`, `jmxcls/`, `excerpts/`, `logs/` (full logs of all twelve
lifetimes, ≈ 1.4 GB, mostly `gc.log*` and `stdout.txt`), `dumps/` (empty folders except `H2-T-1`'s 2.54 GB `.hprof`) and
empty `*.out` files. The `run/` directory is gone. Nothing was deleted by this write-up. The `H2-T-1` dump and the tree are
for the owner to remove.

**Updated after the follow-up** (checked 2026-11-23 13:12 MST): no Cassandra, Java, client, `run.py` or `plan.sh` process, no
`u14-*` systemd scope, no `/dev/shm/u14`, no `run/`. `/mydata/s4/u14/` now also holds `logs/H4-T-{2,3,4}/` (285 / 731 / 584 MB,
full logs), `logs/plan-h4-followup.out` and `logs/H4-T-*.out`, `excerpts-2026-11-23/` (the excerpts copied here), and the
updated `harness/`. The three follow-up `.hprof` files (5.07–5.09 GB) were deleted after their scans; the only dump left is
still `H2-T-1`'s. Disk: `cassandra/` 419 MB, `dumps/` 2.4 GB, `logs/` 3.2 GB, the rest < 1 MB, ≈ 6.0 GB in all; `/mydata`
708 GiB free.
