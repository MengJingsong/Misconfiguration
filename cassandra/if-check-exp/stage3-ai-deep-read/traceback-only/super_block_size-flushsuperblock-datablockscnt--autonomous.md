# super_block_size — trace-back only  <!-- file: traceback-only/super_block_size-flushsuperblock-datablockscnt--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:497` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** SUPER_BLOCK_SIZE is a hard-coded constant (`public static final int SUPER_BLOCK_SIZE = 64`), first declared at `src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:129`, next to `BLOCK_SIZE = 4096` (line 127) and `MAX_TERM_SIZE = 1024` (line 128). Its unit is the number of 4096-byte data blocks (BLOCK_SIZE, line 127) per super block. The check at line 497 (`dataBlocksCnt == SUPER_BLOCK_SIZE`, or a forced final flush when `superBlockTree` is non-empty) compares against `dataBlocksCnt`, a per-level counter of data blocks written since the last super block. That counter is incremented at line 488 and reset to 0 at line 503. When it reaches 64, the accumulated token tree is written to disk (lines 499-501) and a new `DynamicTokenTreeBuilder` replaces it (line 504). This is an on-disk SASI index layout and grouping parameter that also bounds how many block keys the in-memory `superBlockTree` accumulates before it is flushed. It is not a configuration entry or a user-tunable memory or disk cap. The default is the literal 64, not derived from anything. It cannot be set through a yaml key, a -D property or JMX, and changing it requires editing the source and rebuilding. The reader side relies on the same value to locate super blocks (`OnDiskIndex.java:346`, `361`, `368`, `375`), so the value is fixed by the on-disk format.
