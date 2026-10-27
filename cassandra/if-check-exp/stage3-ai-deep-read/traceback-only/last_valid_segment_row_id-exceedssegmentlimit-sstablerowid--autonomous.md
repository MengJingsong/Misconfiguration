# last_valid_segment_row_id — trace-back only  <!-- file: traceback-only/last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java:260` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** SegmentBuilder.LAST_VALID_SEGMENT_ROW_ID, the per-segment row-id cap used by `exceedsSegmentLimit` (target line 260, `getRowCount() == 0`, only returns false for an empty builder; the real comparison is line 266, `ssTableRowId - segmentRowIdOffset > lastValidSegmentRowID`). Kind: constant (compile-time `public static final long`), first declared at `src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java:46` with the comment on line 45 calling it a "safe net in case memory limit is not triggered or when merger merges small segments" and the comment at lines 263-265 tying it to the 2B limit of the on-disk index structure (so it bounds segment size/row count, not bytes directly). Unit: segment-relative SSTable row IDs (row count). Default: `(Integer.MAX_VALUE / 2) - 1L` (line 46), i.e. 1073741822, derived from Integer.MAX_VALUE; each builder copies it into the instance field `lastValidSegmentRowID` (declared line 55) in the constructor at line 147, unless the static `testLastValidSegmentRowId` (line 47, default -1) is >= 0. Settable: not settable via yaml, -D property or JMX (none found in this file); only the test hook `updateLastValidSegmentRowId` (`@VisibleForTesting`, lines 269-273) overrides it, and changing the constant requires a code change and rebuild/restart. The memory-related limit in the same class is a different value, `limiter.limitBytes()` (lines 149, 234), whose source I did not trace and is not verified here.
