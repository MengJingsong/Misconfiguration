# repair_session_space — trace-back only  <!-- file: traceback-only/repair_session_space-setrepairsessionspaceinmib-sizeinmib-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:4096` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `repair_session_space` is a configuration entry, first declared at `src/java/org/apache/cassandra/config/Config.java:208` as `public volatile DataStorageSpec.IntMebibytesBound repair_session_space = null` (it replaces the deprecated `repair_session_space_in_mb`, `Config.java:207`). It caps the heap used for Merkle trees during a repair session. The unit is mebibytes. The check at `DatabaseDescriptor.java:4096` is in `setRepairSessionSpaceInMiB(int sizeInMiB)` (declared at line 4091). It compares `sizeInMiB` with `Runtime.getRuntime().maxMemory() / (4 * 1048576)`, which is a quarter of the max JVM heap in MiB (`maxMemory()` is set by -Xmx). A value above that only logs a "likely to cause heap pressure" warning (lines 4097-4098). A value below 1 throws a ConfigurationException (lines 4093-4095). The default is null in `Config.java:208`. At startup `DatabaseDescriptor.java:609-610` sets it to `Math.max(1, maxMemory() / (16 * 1048576))`, which is 1/16 of the max heap in MiB, with a minimum of 1. The startup path validates the same bounds at lines 612-615: it throws below 1 and warns above 1/4 of the heap. The value can be set with the `repair_session_space` key in cassandra.yaml, and a change there needs a restart. It can also be changed at runtime through JMX on ActiveRepairService (`setRepairSessionSpaceInMegabytes`, `setRepairSessionSpaceInMebibytes` and `setRepairSessionSpaceInMiB`, `ActiveRepairService.java:305-338`), which call `DatabaseDescriptor.setRepairSessionSpaceInMiB` and need no restart. No -D system property sets it.
