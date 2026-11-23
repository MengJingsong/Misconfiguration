# U14 (OC-404) — per-table metrics and schema heap: empty, long-named tables created by DDL until the heap runs out, table count uncapped  <!-- file: cassandra/cases/per-table-metrics-heap--empty-long-named-table-ddl/per-table-metrics-heap--empty-long-named-table-ddl.md -->

| Field | Value |
|---|---|
| Case ID | `U14` (U = unprotected-accumulation case, memory with no applicable control; README "ID prefixes"). Measured class expected: **unprotected** — the only control is a count guardrail that ships disabled (unprotected configuration), and no byte budget covers the holder (unprotected accumulation); see §2.1 |
| From | `OC-404` of the phase 1 OOM candidate list (duplicates `OC-400`, `OC-401`, `OC-402`, `OC-403`, §1) |
| Phase-1 case file | [`table_name_length-validatetablename-name_length--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/table_name_length-validatetablename-name_length--autonomous.md) (also, for OC-400/OC-403, [`schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md)); stage-4 result: [`results/table_name_length-validatetablename-name_length--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/table_name_length-validatetablename-name_length--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml:36` `base.version` 5.0.9); on pc99 `/mydata/s4/cassandra-base` (built tree, no `.git`; jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`, read 2026-11-21 08:04), OpenJDK 11.0.33 |
| Stage 1 (design) | OOM-agent stage-1 session (subagent), 2026-11-21 08:02–≈ 08:50 America/New_York; nothing run (read-only check of pc99 only) |
| Stage 2 (verify) | pending (a fresh OOM-agent session; planned 2026-11-21 ≈ 09:00–14:00 EST on pc99) |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 2).
- **Root cause (claimed):** every table a node loads carries eager heap state that no budget counts: `TableMetrics` registers ≈ 112
  metrics twice (a `Table` and a `ColumnFamily` alias name), each with its own `MetricName` strings, JMX `ObjectName` and, for
  histograms and timers, two `AtomicLongArray`s of ≈ 2.6 KB each; every name string embeds the keyspace and table name, so the
  cost grows by ≈ 570 B per name character per table. The only control on the table count, `tables_fail_threshold`, ships
  disabled (−1), and the 222-character name cap bounds one name, not the sum. So ≈ 0.45–0.5 MiB of heap per empty
  long-named table accumulates with the table count until the heap is gone.
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

pending

## 4. Conclusion (stage 2)

pending
