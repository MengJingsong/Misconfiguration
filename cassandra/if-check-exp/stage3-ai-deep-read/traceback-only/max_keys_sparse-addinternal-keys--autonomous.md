# max_keys_sparse — trace-back only  <!-- file: traceback-only/max_keys_sparse-addinternal-keys--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:598` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `MAX_KEYS_SPARSE` is a hard-coded constant (not a configuration entry, JVM property or runtime-queried limit), declared as `private static final int MAX_KEYS_SPARSE = 5;` in the nested class `MutableDataBlock` at src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:575. It is checked at OnDiskIndexBuilder.java:598 in `MutableDataBlock.addInternal`, where `keys.getTokenCount()` (declared `long getTokenCount()` in TokenTreeBuilder.java:72; returned from the `tokenCount` field in StaticTokenTreeBuilder.java:101-104) is compared against it only when `mode == Mode.SPARSE` (line 594); if the term maps to more than 5 keys an IOException ("belongs to more than %d keys in %s mode, which is not allowed") is thrown at lines 598-600. The unit is a count of keys (partition tokens) per term; the default is 5 and is a literal with no derivation. It is not settable by yaml, -D property or JMX, and can change only by modifying the source and rebuilding. Because it limits the number of token entries inlined per term in the SPARSE-mode index block, it is a format and validity limit on the on-disk SASI index layout rather than an explicit memory or disk cap; the other size constants in the class (`BLOCK_SIZE = 4096`, `MAX_TERM_SIZE = 1024`, `SUPER_BLOCK_SIZE = 64`, lines 127-129) are likewise hard-coded.
