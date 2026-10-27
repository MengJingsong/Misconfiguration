# Trace-back only: index

Unfinished set A cases (2026-10-27): only **A1. The constraint** is filled; see `HANDOFF-Jingsong.md`
("Trace-back only"). This index lists the cases whose constraint type is **not** a `cassandra.yaml` entry
or a JVM (`-D`) property; the 31 yaml and JVM-property cases are in this folder but not listed here.
**Rule:** for trace-back-only work, record in this index only the cases whose constraint type is not a yaml
entry or a JVM property.
Constraint types come from the agents' A1 text and were not re-verified. Rows are in CSV order.

| constraint | constraint type | case file |
|---|---|---|
| `SelectStatement.DEFAULT_PAGE_SIZE` | hard-coded constant | [default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md](default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md) |
| `AtomicBTreePartition.EXCESS_WASTE_BYTES` | hard-coded constant | [excess_waste_bytes-updatewastedallocationtracker-wastedbytes--autonomous.md](excess_waste_bytes-updatewastedallocationtracker-wastedbytes--autonomous.md) |
| `AtomicBTreePartition.EXCESS_WASTE_BYTES` | hard-coded constant | [excess_waste_bytes-uselock-wastetracker--autonomous.md](excess_waste_bytes-uselock-wastetracker--autonomous.md) |
| `AtomicBTreePartition.EXCESS_WASTE_BYTES` | hard-coded constant | [excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous.md](excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous.md) |
| `DiagnosticEventMemoryStore.maxSize` | hard-coded constant | [diagnostic_event_memory_store_max_size-store-keyhead--autonomous.md](diagnostic_event_memory_store_max_size-store-keyhead--autonomous.md) |
| — | none | [none-checklimit-length--autonomous.md](none-checklimit-length--autonomous.md) |
| `HintsWriteExecutor.WRITE_BUFFER_SIZE` | hard-coded constant | [hints_write_buffer_size-append-hint_remaining--autonomous.md](hints_write_buffer_size-append-hint_remaining--autonomous.md) |
| `HintsWriteExecutor.WRITE_BUFFER_SIZE` | hard-coded constant | [write_buffer_size-append-hint--autonomous.md](write_buffer_size-append-hint--autonomous.md) |
| `FBUtilities.MAX_UNSIGNED_SHORT` | hard-coded constant | [max_unsigned_short-validateindexedvalue-value_remaining--autonomous.md](max_unsigned_short-validateindexedvalue-value_remaining--autonomous.md) |
| `BlockBalancedTreeWriter.DEFAULT_MAX_POINTS_IN_LEAF_NODE` | hard-coded constant | [max_points_in_leaf_node-add-leafvaluecount--autonomous.md](max_points_in_leaf_node-add-leafvaluecount--autonomous.md) |
| Lucene `ArrayUtil.MAX_ARRAY_LENGTH` | hard-coded constant | [max_array_length-checkmaxleafnodecount-numleaves--autonomous.md](max_array_length-checkmaxleafnodecount-numleaves--autonomous.md) |
| `NumericValuesWriter.BLOCK_SIZE` / `MONOTONIC_BLOCK_SIZE` | hard-coded constant | [block_size-add-blockindex--autonomous.md](block_size-add-blockindex--autonomous.md) |
| `PostingsWriter.BLOCK_SIZE` | hard-coded constant | [block_size-writeposting-blocksize--autonomous.md](block_size-writeposting-blocksize--autonomous.md) |
| `TokenTreeBuilder.MAX_OFFSET` | hard-coded constant | [max_offset-createentry-offset--autonomous.md](max_offset-createentry-offset--autonomous.md) |
| `TokenTreeBuilder.OVERFLOW_TRAILER_CAPACITY` | hard-coded constant | [overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous.md](overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous.md) |
| `TokenTreeBuilder.TOKENS_PER_BLOCK` | hard-coded constant | [tokens_per_block-add-pos--autonomous.md](tokens_per_block-add-pos--autonomous.md) |
| `OnDiskIndexBuilder.SUPER_BLOCK_SIZE` | hard-coded constant | [super_block_size-flushsuperblock-datablockscnt--autonomous.md](super_block_size-flushsuperblock-datablockscnt--autonomous.md) |
| `OnDiskIndexBuilder.MAX_KEYS_SPARSE` | hard-coded constant | [max_keys_sparse-addinternal-keys--autonomous.md](max_keys_sparse-addinternal-keys--autonomous.md) |
| `min_compress_ratio` (compression option) | per-table/per-index option | [min_compress_ratio-flushdata-maxcompressedlength--autonomous.md](min_compress_ratio-flushdata-maxcompressedlength--autonomous.md) |
| `min_compress_ratio` (compression option) | per-table/per-index option | [min_compress_ratio-flushdata-maxcompressedlength-2--autonomous.md](min_compress_ratio-flushdata-maxcompressedlength-2--autonomous.md) |
| `LogMessagesTable.LOGS_VIRTUAL_TABLE_DEFAULT_ROWS` | hard-coded constant | [logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous.md](logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous.md) |
| `NativeAllocator.MAX_REGION_SIZE` | hard-coded constant | [max_region_size-tryswapregion-minsize--autonomous.md](max_region_size-tryswapregion-minsize--autonomous.md) |
| `FBUtilities.MAX_UNSIGNED_SHORT` | hard-coded constant | [max_unsigned_short-validatekey-key.remaining--autonomous.md](max_unsigned_short-validatekey-key.remaining--autonomous.md) |
| — | none | [none-validatekey-key_remaining--autonomous.md](none-validatekey-key_remaining--autonomous.md) |
| — | none | [none-compose-buffer_remaining--autonomous.md](none-compose-buffer_remaining--autonomous.md) |
| native protocol v1/v2 collection size limit (65535 elements) | hard-coded constant | [native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous.md](native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous.md) |
| native protocol v1/v2 element size limit (65535 bytes) | hard-coded constant | [native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous.md](native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous.md) |
| `SchemaConstants.NAME_LENGTH` | hard-coded constant | [name_length-validatecustomindexcolumnname-name--autonomous.md](name_length-validatecustomindexcolumnname-name--autonomous.md) |
| `SchemaConstants.FILENAME_LENGTH` | hard-coded constant | [filename_length-validatesnapshotname-snapshotname--autonomous.md](filename_length-validatesnapshotname-snapshotname--autonomous.md) |
| — | none | [none-addall-size--autonomous.md](none-addall-size--autonomous.md) |
| `sstable_size_in_mb` (LCS option) | per-table/per-index option | [sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize--autonomous.md](sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize--autonomous.md) |
| `sstable_size_in_mb` (LCS option) | per-table/per-index option | [sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize-2--autonomous.md](sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize-2--autonomous.md) |
| `Controller.MAX_SHARD_SPLIT` | hard-coded constant | [max_shard_split-getnumshards-count--autonomous.md](max_shard_split-getnumshards-count--autonomous.md) |
| `min_sstable_size` (UCS option) | per-table/per-index option | [min_sstable_size-validateoptions-sizeinbytes--autonomous.md](min_sstable_size-validateoptions-sizeinbytes--autonomous.md) |
| `AtomicBTreePartition.EXCESS_WASTE_OFFSET` (derived from `EXCESS_WASTE_BYTES`) | hard-coded constant | [excess_waste_offset-updatewastedallocationtracker-delta--autonomous.md](excess_waste_offset-updatewastedallocationtracker-delta--autonomous.md) |
| — | none | [no_constraint-avoidreservedvalues-wastetracker--autonomous.md](no_constraint-avoidreservedvalues-wastetracker--autonomous.md) |
| `InMemoryTrie` hard 2 GB limit (32-bit pointers) | hard-coded constant | [trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md](trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md) |
| `AbstractBlockPackedWriter.MIN_BLOCK_SIZE` / `MAX_BLOCK_SIZE` | hard-coded constant | [block_packed_max_block_size-checkblocksize-blocksize--autonomous.md](block_packed_max_block_size-checkblocksize-blocksize--autonomous.md) |
| — | none | [none-addterm-term_remaining--autonomous.md](none-addterm-term_remaining--autonomous.md) |
| `SegmentBuilder.LAST_VALID_SEGMENT_ROW_ID` | hard-coded constant | [last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous.md](last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous.md) |
| — | none | [no_constraint-shouldusebruteforce-numrows--autonomous.md](no_constraint-shouldusebruteforce-numrows--autonomous.md) |
| — | none | [none-readfully-dest_length--autonomous.md](none-readfully-dest_length--autonomous.md) |
| — | none | [none-read-count--autonomous.md](none-read-count--autonomous.md) |
| `TrieMemoryIndex.MAX_RECURSIVE_KEY_LENGTH` | hard-coded constant | [max_recursive_key_length-addterm-term--autonomous.md](max_recursive_key_length-addterm-term--autonomous.md) |
| `max_compaction_flush_memory_in_mb` (SASI index option) | per-table/per-index option | [max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous.md](max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous.md) |
| `SchemaConstants.NAME_LENGTH` | hard-coded constant | [schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md](schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous.md) |
| `SchemaConstants.TABLE_NAME_LENGTH` | hard-coded constant | [table_name_length-validatetablename-name_length--autonomous.md](table_name_length-validatetablename-name_length--autonomous.md) |
| — | none | [none-allocateoversize-peer--autonomous.md](none-allocateoversize-peer--autonomous.md) |
