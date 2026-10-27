# repair_session_space — trace-back only  <!-- file: traceback-only/repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:4093` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `repair_session_space` is a configuration entry, declared at `src/java/org/apache/cassandra/config/Config.java:208` (`public volatile DataStorageSpec.IntMebibytesBound repair_session_space = null;`, replacing the deprecated `repair_session_space_in_mb` per `Config.java:207`); the target line `DatabaseDescriptor.java:4093` (`if (sizeInMiB < 1)` in `setRepairSessionSpaceInMiB(int)`, 4091) is the lower-bound check on the new value (it throws a ConfigurationException below 1 MiB, 4094-4095), and the same method warns at 4096-4098 if the value exceeds one quarter of the max heap (`Runtime.getRuntime().maxMemory() / (4 * 1048576)`, a runtime-queried JVM heap limit). It caps the memory (in heap) used by Merkle trees of a repair session (validation memory is derived from it at `src/java/org/apache/cassandra/repair/ValidationManager.java:62`); unit is mebibytes (yaml "Min unit: MiB", `conf/cassandra.yaml:840`). The default is null in Config.java:208 and is derived at startup in `DatabaseDescriptor.java:609-610` as `max(1, maxMemory / (16 * 1048576))`, i.e. 1/16 of the max heap in MiB; startup validation at 612-615 rejects values < 1 and warns above 1/4 of heap. It can be set via the yaml key `repair_session_space` (commented out at `conf/cassandra.yaml:840`; the old `repair_session_space_in_mb` name is still accepted), and at runtime through JMX on ActiveRepairService (`setRepairSessionSpaceInMiB`, `ActiveRepairService.java:334-338`, plus the deprecated setters at 307 and 322, all calling the DatabaseDescriptor setter), so no restart is needed to change it (the field is volatile, `Config.java:208`).
