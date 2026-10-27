# none — trace-back only  <!-- file: traceback-only/none-addterm-term_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:221` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** None: the target line (SSTableIndexWriter.java:221, inside `private void addTerm(ByteBuffer term, PrimaryKey key, long sstableRowId)`, declared at line 205) is `if (term.remaining() == 0 && index.termType().skipsEmptyValue()) return;`, which is a data-validity check, not a memory or disk cap. It compares the term's remaining byte count to the literal 0 and skips empty values for index types that do not allow them or are not literal; `skipsEmptyValue()` returns `!indexType.allowsEmpty() || !isLiteral()` (IndexTermType.java:282-285), a property of the column type with no configuration entry, JVM property, constant or runtime-queried limit behind it, not settable and with no restart question. The nearby memory-related checks in the same method are separate from this line: `limiter.increment(...)` at lines 225 and 235 is bookkeeping against a `NamedMemoryLimiter`, and `shouldFlush` (line 245) tests `limiter.usageExceedsLimit()` at line 248. That limiter is `V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMITER` (V1OnDiskFormat.java:128), sized from `DatabaseDescriptor.getSAISegmentWriteBufferSpace().toBytes()` (V1OnDiskFormat.java:126). I did not trace that value further (yaml key, default, whether it needs a restart), so those details are not verified.
