# filename_length — trace-back only  <!-- file: traceback-only/filename_length-validatesnapshotname-snapshotname--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/ColumnFamilyStore.java:2185` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `SchemaConstants.FILENAME_LENGTH`, a compile-time constant (`public static final int`), first declared at `src/java/org/apache/cassandra/schema/SchemaConstants.java:80`. The unit is characters (the length of a file or directory name component). The default is the hard-coded literal 255 (SchemaConstants.java:80), which matches the common filesystem limit on a name component. It is not derived from anything else. The check is at `ColumnFamilyStore.java:2185` in `validateSnapshotName(String)` (declared at line 2168): `snapshotName.length() > SchemaConstants.FILENAME_LENGTH` throws IllegalArgumentException (lines 2187-2190). The comment at lines 2183-2184 says the cap follows the table-name limit. The same constant also bounds `TABLE_NAME_LENGTH` (SchemaConstants.java:91). It is not settable by yaml key, -D property or JMX, and changing it needs a code change and rebuild. The length check only runs when the JVM property `cassandra.snapshot.validation` (`CassandraRelevantProperties.SNAPSHOT_NAME_VALIDATION`, `config/CassandraRelevantProperties.java:517`) is true. Its default is "false", and it is read at call time via `.getBoolean()` (ColumnFamilyStore.java:2180), so it is set with -D at startup. This is a name-length validity limit that guards against path-component overflow. It is not a memory or disk-usage cap.
