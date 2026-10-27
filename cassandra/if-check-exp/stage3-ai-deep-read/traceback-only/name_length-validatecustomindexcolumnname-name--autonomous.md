# name_length — trace-back only  <!-- file: traceback-only/name_length-validatecustomindexcolumnname-name--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/statements/schema/CreateIndexStatement.java:213` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `SchemaConstants.NAME_LENGTH`; kind: hard-coded constant (`public static final int`), declared at `src/java/org/apache/cassandra/schema/SchemaConstants.java:75`; the check is at `cql3/statements/schema/CreateIndexStatement.java:213` inside `validateCustomIndexColumnName(String name)` (line 209), which rejects a custom-index target column name longer than the limit (`TOO_LONG_CUSTOM_INDEX_TARGET`, line 214). Unit: characters (`String.length()`). Default/value: the literal 48 (SchemaConstants.java:75), not derived from anything; its javadoc (lines 69-74) calls it the longest permissible keyspace/table name and notes the old 255-character path concern was dropped by CASSANDRA-16956. It is also used for keyspace names at `schema/KeyspaceMetadata.java:68`. It is not settable (no yaml key, -D property or JMX), so changing it requires editing the source and rebuilding/restarting. It is a schema-naming limit rather than a direct memory or disk cap; its only link to disk is that it bounds names that end up in file and directory names (the separate FILENAME_LENGTH = 255 at SchemaConstants.java:80 and TABLE_NAME_LENGTH at line 91 do that for tables).
