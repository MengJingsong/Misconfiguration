# Seed count warn threshold (SEED_COUNT_WARN_THRESHOLD) — verification solution  <!-- file: cases/seed_count_warn_threshold-getseeds-seeds_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SimpleSeedProvider.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/locator/SimpleSeedProvider.java#L110) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no memory or disk constraint; the check only logs a warning and bounds nothing. |
| Ground | Both outcomes return the full seed list; the list holds a handful of `InetAddressAndPort` objects (bytes to KB), so it is not a memory- or disk-significant object. |

**Type:** non-config (none). The constant rule applied: the compared value is the declared `private static final int SEED_COUNT_WARN_THRESHOLD`, initialised from the JVM property `cassandra.seed_count_warn_threshold` with the hard-coded literal default `20`. Both the constant and the literal take part, so this is not a skip.

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands: `seeds.size()` (local `ArrayList` built in the method, [`SimpleSeedProvider.java:81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/locator/SimpleSeedProvider.java#L81)) and `SEED_COUNT_WARN_THRESHOLD`, a constant declared at [`SimpleSeedProvider.java:43`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/locator/SimpleSeedProvider.java#L43) as `CassandraRelevantProperties.SEED_COUNT_WARN_THRESHOLD.getInt(20)`. The property is declared at [`CassandraRelevantProperties.java:490`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L490) (`cassandra.seed_count_warn_threshold`). Unit: number of seed hosts. Default 20 (literal in the `getInt` call). Set with `-Dcassandra.seed_count_warn_threshold=N`; read once at class init, so a restart is needed. Not a yaml entry.

**A2. What it caps.** Nothing. The check bounds no memory or disk object. The seed list is a small `List<InetAddressAndPort>` (one entry per seed in the `seeds` parameter of `seed_provider`), transient and returned to the caller.

**A3. Mechanism.** Method `SimpleSeedProvider.getSeeds()` (line 52). It loads the config (line 57), reads `seeds` and `resolve_multiple_ip_addresses_per_dns_record` from `conf.seed_provider.parameters` (lines 69-79), resolves each host and adds to `seeds` (lines 83-108). The if statement is [`SimpleSeedProvider.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/locator/SimpleSeedProvider.java#L110). True: `logger.warn(...)` (lines 111-113) saying a large seed list may hurt the third gossip round. False: nothing. Both outcomes then `return Collections.unmodifiableList(seeds)` (line 115): the list is never truncated or rejected. Callers: implements `SeedProvider.getSeeds()` (`locator/SeedProvider.java:24`); invoked via `DatabaseDescriptor.getSeeds()` (used at `service/StorageService.java:879, 1137, 1290, 1292`) and the gossiper (`StorageService.java:2235` reads `Gossiper.instance.getSeeds()`). No bypass is relevant since nothing is enforced.

**A4. Other consumers.** The seed set lives in the gossiper (gossip rounds contact seeds); that concerns network/CPU effectiveness, not a memory or disk cap. No other user of the property found.

**A5. Evidence beyond the source.** Searched `SEED_COUNT_WARN_THRESHOLD` across `src` (only SimpleSeedProvider lines 43, 110, 113, and the property enum at line 490); searched callers of `getSeeds()` (list above). The warning text itself states the concern is gossip effectiveness. No docs or tests consulted beyond that.

## B. Verification solution

**B1. Claim under test.** The check at line 110 does not cap memory or disk: with more seeds than the threshold the full list is still returned and only a WARN line is logged.

### B2. Unit tier

n/a: no constraint, there is no usage-side limit to push against. Evidence in A3 (both outcomes return the same list) answers the question. Optional cheap check if wanted: a small test calling `new SimpleSeedProvider(Map.of()).getSeeds()` with `seeds` set to 25 distinct IP literals (via a test yaml loaded through `-Dcassandra.config`) and `-Dcassandra.seed_count_warn_threshold=20`, expecting a returned size of 25 and one WARN log; and with threshold 30, size 25 and no WARN.

### B3. Cluster tier

n/a: no constraint, there is no memory or disk resource the check bounds; A2/A3 show the only effect is a log line. Alternative: start one node with 25 IP-literal seeds and the default threshold, confirm the WARN appears in `system.log` and `nodetool getseeds` lists all 25.

**B4. Risks and cleanup.** None beyond stopping any node started and removing its scratch data directory.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/locator/SimpleSeedProvider.java
- grep results over /users/jason92/cassandra-5.0.9/src for SEED_COUNT_WARN_THRESHOLD and getSeeds()

## D. Stage-4 feedback

`none yet`
