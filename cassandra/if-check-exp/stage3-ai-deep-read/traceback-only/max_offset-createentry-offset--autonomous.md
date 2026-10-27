# max_offset — trace-back only  <!-- file: traceback-only/max_offset-createentry-offset--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sasi/disk/AbstractTokenTreeBuilder.java:297` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `TokenTreeBuilder.MAX_OFFSET` is a hard-coded constant (kind: constant), first declared at `src/java/org/apache/cassandra/index/sasi/disk/TokenTreeBuilder.java:37` as `long MAX_OFFSET = (1L << 47) - 1; // 48 bits for (signed) offset` (an interface field, so implicitly `public static final`). It is checked in `AbstractTokenTreeBuilder.Leaf.createEntry` at `AbstractTokenTreeBuilder.java:297-298`, where a single-offset token whose `offset` (read from `offsets.toArray()[0]` at line 296) exceeds it throws an `AssertionError`. The unit is bytes: the offset is the position of the partition in the SSTable data file that the SASI token tree points to. The value is 2^47 - 1 = 140,737,488,355,327, about 128 TiB. It is not derived from any configuration or runtime query. It follows from the on-disk token-tree leaf format, which stores the offset in 48 bits with the sign bit excluded (comment at `TokenTreeBuilder.java:37`). Larger offsets that exceed `Integer.MAX_VALUE` are stored as factored offsets (`AbstractTokenTreeBuilder.java:299-302`). It cannot be set through a yaml key, a -D property or JMX. Changing it requires editing the source and rebuilding, and it would break the on-disk format. Practically it is a format-capacity ceiling on SSTable data file size for SASI indexes, and it is not a tunable memory or disk-use cap.
