# Cassandra — config-first source

Method: [`../../source-config-first/README.md`](../../source-config-first/README.md). Pinned source:
`systems/cassandra/source` (Cassandra 5.0.9).

## Step 1 — coverage diff (2026-11-25)

Run from the repository root (about 35 s, no agents):

```
python3 experiments/capacity-enforcement-exp/cassandra/source-config-first/coverage-diff.py
```

It reads `Config.java` (yaml entries), `CassandraRelevantProperties.java` (JVM properties), the
getters in `DatabaseDescriptor` and `GuardrailsOptions`, the stage-1 CodeQL rows
(`codeql-queries/results/cassandra/*.csv`), the 344 stage-3 case files and the OOM-exp case files. It writes
[`config-coverage.csv`](config-coverage.csv), with one row per entry.

**Entries 735 = in scope 645 + out of scope 90** (JVM properties for tests, the JDK, logging or JMX).
In scope 645 = yaml 409 + JVM 236:

| Tier | yaml | JVM | Total | of which name-hinted |
|---|---|---|---|---|
| 1 — constraint of a phase-1 case (ruled out) | 126 | 32 | **158** | 126 |
| 2 — mentioned in a case, not its constraint | 130 | 24 | **154** | 61 |
| 3 — a stage-1 unit names it, no case | 25 | 2 | 27 | 18 |
| 4 — a stage-1 unit near a read, no case | 81 | 111 | 192 | 47 |
| 5 — read, no stage-1 unit near it | 37 | 59 | **96** | 26 |
| 6 — not read in `src/java` | 10 | 8 | 18 | 7 |
| **Total** | **409** | **236** | **645** | **285** |

**No phase-1 case at all (tiers 3–6): 333** (yaml 153, JVM 180), of which **98 name-hinted** (yaml 54,
JVM 44). These go to step 2 first. Then come the 154 of tier 2.

Read with care:
- Tiers 3–4 do not mean the unit is about this entry. They mean CodeQL produced a unit close to where
  the entry is read, so the entry may already be reachable through stage 3's backlog (queued band-D set A,
  extension band C/D).
- Tier 6 holds deprecated or unused entries (`otc_*`, `back_pressure_*`, `windows_timer_interval`) and
  JVM properties read only outside `src/java`.
- Examples of name-hinted entries with no case: `ALLOW_UNLIMITED_CONCURRENT_VALIDATIONS`,
  `NIO_DATA_OUTPUT_STREAM_PLUS_BUFFER_SIZE`, `SEARCH_CONCURRENCY_FACTOR`, `max_top_size_partition_count`,
  `concurrent_materialized_view_builders`, `paxos_repair_parallelism`, `repair_command_pool_size`.

## Steps 2–3

Not started. Step 2 bands the 333 (then the 154) as stage 2 does; step 3 needs an owner-approved batch.
