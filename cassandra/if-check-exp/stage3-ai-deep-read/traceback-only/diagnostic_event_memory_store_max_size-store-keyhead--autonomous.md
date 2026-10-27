# diagnostic_event_memory_store_max_size — trace-back only  <!-- file: traceback-only/diagnostic_event_memory_store_max_size-store-keyhead--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/diag/store/DiagnosticEventMemoryStore.java:56` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `maxSize` in DiagnosticEventMemoryStore is a hard-coded constant (a non-final private int field) that caps the number of diagnostic events buffered on-heap; it is first declared at `src/java/org/apache/cassandra/diag/store/DiagnosticEventMemoryStore.java:39` as `private int maxSize = 200;`. The unit is events (entry count, not bytes). The default is the literal 200, with no derivation. It is not settable by any yaml key, -D property or JMX: the only writer is the package-private `setMaxSize(int)` at line 92-95, marked `@VisibleForTesting` (line 91), so it is effectively fixed and changing it needs a code change and a restart. The check at line 56 (`if (keyHead > maxSize) events.tailMap(keyHead - maxSize).clear();`) compares the running event counter `keyHead` (`lastKey.incrementAndGet()`, line 52) to it and evicts older events. The store is only instantiated by `DiagnosticEventPersistence.java:151` (`new DiagnosticEventMemoryStore()`), and is only used when `diagnostic_events_enabled` (`Config.java:708`, default false, `conf/cassandra.yaml:1936`) is on; that flag only enables event publishing and does not set the cap.
