# Cassandra — config-first source

Method: [`../../source-config-first/README.md`](../../source-config-first/README.md). Pinned source:
`systems/cassandra/source` (Cassandra 5.0.9).

## Step 1 — coverage diff (2026-11-25; getter detection fixed 2026-11-26)

Run from the repository root (about 35 s, no agents):

```
python3 experiments/capacity-enforcement-exp/cassandra/source-config-first/coverage-diff.py
```

**Correction 2026-11-26:** the first run counted generic `DatabaseDescriptor` methods (`setConfig` and the private
methods after it) as getters of 94 entries, which moved entries into tiers 3–4. Getters are now public, getter-like
methods only. Tiers 3–5 changed (27/192/96 → 14/201/100); tiers 1, 2, 6 and the no-case total did not.

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
| 3 — a stage-1 unit names it, no case | 12 | 2 | 14 | 10 |
| 4 — a stage-1 unit near a read, no case | 90 | 111 | 201 | 55 |
| 5 — read, no stage-1 unit near it | 41 | 59 | **100** | 26 |
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

## Step 2 — banding (2026-11-26)

The 333 entries with no case (tiers 3–6), in 4 batches with the hinted entries first, plus 5 anchors in every
batch (`memtable_heap_space`, `key_cache_size`, `native_transport_max_frame_size`, `commitlog_segment_size`,
`MAX_HINT_BUFFERS`). One fresh banding agent per batch saw only the batch file: name, default, the `cassandra.yaml`
comment and up to two source lines that read the entry, built by `make-band-batches.py`. The anchor check
passed in all 4 batches. Merged by `record-config-bands.py` into [`config-bands.csv`](config-bands.csv), with the
columns `kind, name, tier, band, reason, model, date, batch`.

Bands as stage 2 uses them: A = a memory or disk capacity; B = plausibly bounds memory or disk (concurrency of
memory-holding work, retention, guardrail thresholds); C = the insurance band; D = clearly not.

| Band | yaml | JVM | Total | Tier 3 / 4 / 5 / 6 |
|---|---|---|---|---|
| A | 2 | 2 | **4** | 0 / 3 / 1 / 0 |
| B | 24 | 15 | **39** | 5 / 18 / 13 / 3 |
| C | 54 | 39 | 93 | 4 / 65 / 18 / 6 |
| D | 73 | 124 | 197 | 5 / 115 / 68 / 9 |
| **Total** | **153** | **180** | **333** | 14 / 201 / 100 / 18 |

Band A: `DROP_OVERSIZED_READ_REPAIR_MUTATIONS`, `NIO_DATA_OUTPUT_STREAM_PLUS_BUFFER_SIZE`,
`max_top_size_partition_count`, `max_top_tombstone_partition_count`.

Tier 2's 154 entries (mentioned in a case, not its constraint) are not banded yet.

## Step 3 — forward trace

Not started. The 43 A–B entries are the queue (A first); the first batch is 10.
