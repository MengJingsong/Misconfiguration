# max_recursive_key_length — trace-back only  <!-- file: traceback-only/max_recursive_key_length-addterm-term--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java:228` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** MAX_RECURSIVE_KEY_LENGTH; a hard-coded constant (not a configuration entry, JVM property or runtime-queried limit); first declared at `src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java:64` as `private static final int MAX_RECURSIVE_KEY_LENGTH = 128`; it is compared at line 228 inside `addTerm(PrimaryKey, ByteBuffer)` (declared line 218) against `term.limit()`, and the unit is bytes of the indexed term. It is not a memory or disk cap: it only chooses between `data.putRecursive(...)` (line 230) for terms of 128 bytes or fewer and `data.apply(Trie.singleton(...))` (line 234) for longer terms, so it picks the insertion path and rejects nothing. A separate constant with the same name and value is declared at `src/java/org/apache/cassandra/db/memtable/TrieMemtable.java:98`, and that one is used at line 483. The default is the literal 128 with no derivation. It cannot be set by yaml, -D property or JMX, and changing it requires a code change and rebuild. Whether the recursion depth is the reason for the value is not verified (no comment on it was read). The actual term-size limit is checked just before it, at line 220, by `index.validateTermSize(...)`, which I did not trace.
