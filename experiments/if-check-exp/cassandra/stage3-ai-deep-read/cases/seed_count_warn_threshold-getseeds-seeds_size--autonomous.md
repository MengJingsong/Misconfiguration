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

> **Amendment 2026-10-27 (stage-4 audit, before any run; node pc29; none of it depends on a reading).**
> (1) *Why the two `n/a` tiers become real tiers.* The claim is negative ("does not cap"). The protocol lets a negative claim reach `Confirmed` only with a positive control (the same workload and instruments shown to move usage where a cap does bind), and a source reading alone cannot supply one. The file's own "optional cheap check" is therefore promoted to the tiers below, with a source copy that does cap as the control.
> (2) *The quantity.* There is no limit on memory or disk here; the question is whether any retained or transient memory is bounded by the threshold. The resource is the heap of the seed list: the list `getSeeds()` returns (`K` `InetAddressAndPort` objects, plus the `ImmutableSet` copy `DatabaseDescriptor.getSeeds()` builds on each call, `DatabaseDescriptor.java:2922`) and, on a node, what the gossiper builds per seed it contacts (one `OutboundConnections` per peer address). `K` is varied (25, 1000, 20000 in the unit tier; 25 and 1000 on a node) so that the object is large enough to measure.
> (3) *Citation check.* Lines 43, 81, 110-115 and 115 of `SimpleSeedProvider.java` and line 490 of `CassandraRelevantProperties.java` match the pinned source; `getSeeds()` is not cached (it calls `DatabaseDescriptor.loadConfig()` each time, line 57), which the unit tier uses (repeated calls).
> (4) *The control (arm P).* A copy `~/s4-seed-b` in which line 115 returns `seeds.subList(0, SEED_COUNT_WARN_THRESHOLD)` when `seeds.size()` exceeds the threshold, i.e. a real cap on exactly this object with the same threshold knob. Arm U is the unmodified copy `~/s4-base`.

> **B2 replaced 2026-10-27 (was `n/a`; the old text below stays as the stage-3 record).**
> *B2a.* JDK 11, Ant, copies `~/s4-base` (arm U) and `~/s4-seed-b` (arm P), built with `ant build-test`. Test class `SeedCountFootprintTest` (harness folder), copied into `test/unit/org/apache/cassandra/locator/`; one JVM per cell, because the threshold is a `static final` read at class init (`-Dcassandra.seed_count_warn_threshold=T`, or unset for the default 20) and the seeds come from a generated yaml (`-Dcassandra.config`).
> *B2b.* K = 25, 1000, 20000 seeds (distinct IP literals, no DNS). Per K, arm U with T = default (20, below K: the warn branch) and T = 2K (above K: the no-warn branch); arm P with T = default. Three repetitions.
> *B2c.* One `getSeeds()` call per cell for the size, the WARN and the deep size; then ten more calls kept alive to read the live heap after GC (per copy).
> *B2d.* `returned` (size of the list), `warn_lines` (logback appender on `SimpleSeedProvider`), `deepBytes` (`ObjectSizes.measureDeep` of the returned list), `heapPerCopy` (live heap after 3 GCs, ten kept copies, divided by ten), `databaseDescriptorGetSeeds` (size of the set). Resolution: `heapPerCopy` moves by a few KB between identical runs, so it is read in shape; `deepBytes` is exact.
> *B2f. Predictions (before the run).* Arm U: `returned = K` in every cell; `warn_lines = 1` when T = default (K > 20) and `0` when T = 2K; `deepBytes` is identical for T = default and T = 2K at the same K and grows with K (20000 : 1000 within 15 % of 20 : 1); `heapPerCopy` equal across the two T within 20 %. Arm P (control): `returned = 20` for every K > 20 (`returned = 20` also at K = 25), `deepBytes` at K = 20000 below 1/100 of arm U's, `heapPerCopy` likewise far below. The instrument can therefore see a cap when there is one.
> *Runbook fix 2026-10-27 (after the first unit attempt, before any accepted reading; claim, predictions and rows unchanged).* (i) `heapPerCopy` was polluted: each `getSeeds()` logs K DEBUG lines ("Only resolving one IP per DNS record"), which sit in the async log queue and the ListAppender; the first attempt read 375 KB per copy at K = 1000 for arm U and 245 KB for arm P, which is not the list. The test now sets the `SimpleSeedProvider` logger to WARN after the first call and waits 2 s before the baseline; the resolution sentence in B2d ("a few KB") was wrong and `heapPerCopy` is read in shape only, with a constant offset of about -43 KB at small K (the baseline is taken after the first call's garbage). (ii) 20000 seeds exceed the single-argument limit of the yaml generator; the seed string is passed in a file. The tier was restarted from its beginning (attempts kept at `results/.../run1/attempts/`).
> *B2g. Readings.*
>
> | Observation | Meaning |
> |---|---|
> | `returned` or `deepBytes` or `heapPerCopy` of arm U follows T (smaller for T below K) | Refuted: the threshold bounds the list |
> | Arm U identical across T at each K (returned = K, deepBytes equal, heapPerCopy within 20 %), WARN present only for T below K, arm P cell at the same K and T smaller by the factors above | Confirmed: the threshold caps nothing and the control moved |
> | Arm U identical across T but arm P does not shrink | Control failed: Not confirmed |
> | `warn_lines = 0` where T < K or `> 0` where T > K | Branch reading wrong: Not confirmed |
> | `deepBytes` at K = 25 too small to read | read at K = 1000 and 20000 |


n/a: no constraint, there is no usage-side limit to push against. Evidence in A3 (both outcomes return the same list) answers the question. Optional cheap check if wanted: a small test calling `new SimpleSeedProvider(Map.of()).getSeeds()` with `seeds` set to 25 distinct IP literals (via a test yaml loaded through `-Dcassandra.config`) and `-Dcassandra.seed_count_warn_threshold=20`, expecting a returned size of 25 and one WARN log; and with threshold 30, size 25 and no WARN.

### B3. Cluster tier

> **B3 replaced 2026-10-27 (was `n/a`; the old text below stays as the stage-3 record).**
> *B3a.* One node on loopback, `MAX_HEAP_SIZE=1G`, own `CASSANDRA_CONF`, data on local disk under `~/s4-seed`, never under `/proj`; `cassandra.yaml` seeds = `127.0.0.1` (the node itself, so it starts without bootstrap) followed by K-1 distinct unrouted IP literals; the threshold goes in with `JVM_EXTRA_OPTS=-Dcassandra.seed_count_warn_threshold=T` on the `bin/cassandra` command only. Arm U from `~/s4-base`, arm P (control) from `~/s4-seed-b`.
> *B3b.* K = 25 and 1000. Cells: U with T default (20) and T = 2K, at both K; P with T default at K = 1000. Five node starts, one lifetime each, 150 s of gossip after the listener is up.
> *B3d.* `system.log` WARN lines `Seed provider returned more than` (counted from this start's offset), `nodetool getseeds` (the gossiper's list; count), `jmap -histo:live` (full GC) total live bytes and the instance counts and bytes of `org.apache.cassandra.locator.InetAddressAndPort` and `org.apache.cassandra.net.OutboundConnections` (one per peer address ever messaged; gossip picks a seed per round), `GC.heap_info`.
> *B3f. Predictions (before the run).* U: `getseeds` count = K for both T; WARN present when T = default and absent when T = 2K; `OutboundConnections` and `InetAddressAndPort` instance counts and total live bytes equal across the two T at the same K within 25 % (gossip picks seeds at random, so the touched set is not identical), and larger at K = 1000 than at K = 25. P (control): `getseeds` count = 20, `OutboundConnections` at most 21, far below U's at K = 1000.
> *B3g. Readings.*
>
> | Observation | Meaning |
> |---|---|
> | U's counts or live bytes follow T (fewer for T = default at the same K) | Refuted |
> | U equal across T at each K, WARN only for T < K, P's counts far below U's at K = 1000 | Confirmed: caps nothing, instrument moved under a real cap |
> | U equal across T, P not smaller | Control failed: Not confirmed |
> | `OutboundConnections` too few at K = 1000 for the 150 s (less than 30 touched peers in U) | usage not driven far enough: Not confirmed |


n/a: no constraint, there is no memory or disk resource the check bounds; A2/A3 show the only effect is a log line. Alternative: start one node with 25 IP-literal seeds and the default threshold, confirm the WARN appears in `system.log` and `nodetool getseeds` lists all 25.

**B4. Risks and cleanup.** None beyond stopping any node started and removing its scratch data directory.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/locator/SimpleSeedProvider.java
- grep results over /users/jason92/cassandra-5.0.9/src for SEED_COUNT_WARN_THRESHOLD and getSeeds()

## D. Stage-4 feedback

**2026-10-27, stage 4 (results: `stage4-runtime-verification/results/seed_count_warn_threshold-getseeds-seeds_size--autonomous.md`).** Frozen sha256 before the runs `9dfc9412…1251`; one runbook-fix note added after the first unit attempt (B2, dated). The two `n/a` tiers were promoted to real tiers with a source copy that truncates the list to the threshold as the positive control.

- **Unit and cluster: Confirmed, Effect `does not cap`; outcome class true negative.** Unit: `getSeeds()` returns all K (25, 1000, 20000) whether T is below or above K, the WARN appears only when T is below K, the deep size is identical across T (132,064 B at K = 1000, 2,640,064 B at K = 20000, 3 repetitions each) while the truncating copy returns 20 and 2,704 B. Cluster (one node, K = 25 and 1000): live heap 65.9 MB vs 99.6 MB for K = 25 vs 1000 and identical across T at each K (99,614,856 vs 99,614,008 B); `OutboundConnections` = K-1 in both (999), 19 in the truncating copy (live heap 65.8 MB).
- Worth stage 3's attention: the seed list is not the memory that grows with K. A node builds one `OutboundConnections` set per seed it messages (about 34 KB per seed at K = 1000, all seeds contacted within the first minutes), and `getSeeds()` re-reads the yaml and warns on every call (12 WARN lines in 150 s). The threshold neither caps nor mitigates that.

