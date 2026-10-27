# seed_count_warn_threshold — trace-back only  <!-- file: traceback-only/seed_count_warn_threshold-getseeds-seeds_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/locator/SimpleSeedProvider.java:110` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** The compared value is `SEED_COUNT_WARN_THRESHOLD`, a JVM system property (`cassandra.seed_count_warn_threshold`) declared at `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:490` and read into a static final int at `src/java/org/apache/cassandra/locator/SimpleSeedProvider.java:43` via `.getInt(20)`. Its unit is a count of seed nodes, and its default is the hard-coded 20 passed at that call. It can be set only with `-Dcassandra.seed_count_warn_threshold=<n>` at JVM start, so a change needs a restart. There is no yaml key and no JMX setter. The check at `SimpleSeedProvider.java:110` only logs a warning (lines 111-113) when the resolved seed list is longer than the threshold. It does not reject or truncate the list, so the line is not a memory or disk cap. The threshold exists because a large seed list may hurt the third gossip round (message at lines 111-112). In short, this line has no memory or disk constraint: it is an advisory count threshold on the number of seeds returned by `getSeeds()` (line 52).
