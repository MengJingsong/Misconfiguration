# schemaconstants_name_length — trace-back only  <!-- file: traceback-only/schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/schema/KeyspaceMetadata.java:68` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** SchemaConstants.NAME_LENGTH is a hard-coded constant, not a configuration entry, JVM property, or runtime-queried limit. It is declared as `public static final int NAME_LENGTH = 48;` at src/java/org/apache/cassandra/schema/SchemaConstants.java:75, and its javadoc (lines 69-74) calls it the longest permissible keyspace or table name. The unit is characters (the check at src/java/org/apache/cassandra/schema/KeyspaceMetadata.java:68, inside `validateKeyspaceName` (declared at line 63), compares `keyspaceName.length()` against it). The default is the literal 48, with no derivation. It cannot be set through a yaml key, -D property, or JMX; changing it needs a source edit and rebuild (a restart follows trivially). The javadoc at lines 72-73 says an older limit tied to the 255-character total path length (CASSANDRA-16956) is no longer in effect. The limit is on the name's length, and it does not cap memory or disk use directly. Table names are checked against the separate constant TABLE_NAME_LENGTH (SchemaConstants.java:91, used at TableMetadata.java:517), which is not the target here.
