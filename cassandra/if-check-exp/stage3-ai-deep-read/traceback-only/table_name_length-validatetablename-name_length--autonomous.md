# table_name_length — trace-back only  <!-- file: traceback-only/table_name_length-validatetablename-name_length--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/schema/TableMetadata.java:517` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** TABLE_NAME_LENGTH, a hard-coded constant (not a configuration entry, JVM property or runtime-queried value), checked at schema/TableMetadata.java:517 (`name.length() > TABLE_NAME_LENGTH` in `validateTableName()`, declared at :512) and first declared at schema/SchemaConstants.java:91 as `FILENAME_LENGTH - TABLE_UUID_AS_HEX_LENGTH - TABLE_DIRECTORY_NAME_SEPARATOR.length()`, where FILENAME_LENGTH = 255 (SchemaConstants.java:80, "longest acceptable file name"), TABLE_UUID_AS_HEX_LENGTH = 32 (SchemaConstants.java:85) and TABLE_DIRECTORY_NAME_SEPARATOR = "-" (db/Directories.java:123, imported at SchemaConstants.java:35), so the default is 255 - 32 - 1 = 222 characters. The unit is characters of the table name; it caps the length of the table's on-disk directory name (name + "-" + 32-hex table id) so it fits the filesystem file-name limit, not memory or heap. It is not settable (no yaml key, -D property or JMX; changing it requires editing the source and rebuilding, then restarting). A related assert at TableMetadata.java:520 re-checks the generated directory name against FILENAME_LENGTH.
