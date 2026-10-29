# Hard-coded-constant cases not yet run at stage 4 — four batches of seven

Written 2026-10-28. The 28 non-config, hard-coded-constant case files that had no stage 4 verdict, grouped by code area so cases
that share a class share a harness. All are autonomous files with a `negative` estimate. Stems below omit the `--autonomous.md` suffix.

| Batch | Stems |
|---|---|
| 1 | `excess_waste_bytes-updatewastedallocationtracker-wastedbytes`, `excess_waste_bytes-uselock-wastetracker`, `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2`, `excess_waste_offset-updatewastedallocationtracker-delta`, `max_region_size-tryswapregion-minsize`, `hints_write_buffer_size-append-hint_remaining`, `write_buffer_size-append-hint` |
| 2 | `logs_virtual_table_default_rows-addtobuffer-messagebuffer_size`, `max_shard_split-getnumshards-count`, `max_unsigned_short-validateindexedvalue-value_remaining`, `name_length-validatecustomindexcolumnname-name`, `filename_length-validatesnapshotname-snapshotname`, `schemaconstants_name_length-validatekeyspacename-keyspacename`, `table_name_length-validatetablename-name_length` |
| 3 | `max_points_in_leaf_node-add-leafvaluecount`, `max_array_length-checkmaxleafnodecount-numleaves`, `block_size-add-blockindex`, `block_size-writeposting-blocksize`, `max_offset-createentry-offset`, `overflow_trailer_capacity-createoverflowentry-overflowcollisions`, `tokens_per_block-add-pos` |
| 4 | `super_block_size-flushsuperblock-datablockscnt`, `max_keys_sparse-addinternal-keys`, `native_protocol_v1_v2_collection_size_limit-writesize-size`, `native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize`, `block_packed_max_block_size-checkblocksize-blocksize`, `last_valid_segment_row_id-exceedssegmentlimit-sstablerowid`, `max_recursive_key_length-addterm-term` |

Progress: batches 1-4 all run 2026-10-28 (batch 1: 7 TN; batch 2: 5 TN + 2 undetermined; batches 3-4: 11 TN + 3 undetermined, nodes mixed across batches 3 and 4).
