# Band D, non-config autonomous agent: processed rows

Written by the non-config autonomous agent job (decided 2026-10-27; playbook:
[`playbook-non-config-autonomous.md`](playbook-non-config-autonomous.md)). Inputs are the band D units of
[`../stage2-ai-preprocessing/bands.csv`](../stage2-ai-preprocessing/bands.csv), helper units first, then rows, in file order.
One line per unit the job has handled. Outcomes: `CASE <stem>` (a non-config case file was written), `SKIP` (config-type;
the record is in [`skipped-config-type.md`](skipped-config-type.md)), `UNRESOLVED` (the target could not be fixed to one method;
waits for a `file:line`), `covered` (already a case's target). A batch ends when it has 5 non-config case files; a wave keeps
all it produced. The CSV line is the line number in `bands.csv`.

| CSV line | Unit | Outcome | Note |
|---|---|---|---|
| 4155 | `<anonymous class>.hasNext()` | UNRESOLVED | ~40 anonymous-class `hasNext()` definitions with different bodies; only `IndexSummary.java:333` has a numeric comparison (`idx > current.upperPosition`). Needs a `file:line` before it can be traced. |
| 4156 | `<anonymous class>.isAllZero()` | CASE `no_constraint-isallzero-vectorelement` | negative, no constraint, type none |
| 4157 | `org.apache.cassandra.config.DataStorageSpec.equals()` | CASE `no_constraint-equals-quantity` | negative, no constraint, type none |
| 4158 | `org.apache.cassandra.config.DurationSpec.equals()` | CASE `no_constraint-equals-quantity-2` | negative, no constraint, type none |
| 4159 | `org.apache.cassandra.cql3.CIDR.overlaps()` | CASE `no_constraint-overlaps-iprangeends` | negative, no constraint, type none |
| 4160 | `org.apache.cassandra.cql3.Duration.hasDayPrecision()` | CASE `no_constraint-hasdayprecision-nanoseconds` | negative, no constraint, type none |
| 4161 | `org.apache.cassandra.cql3.Duration.hasMillisecondPrecision()` | CASE `no_constraint-hasmillisecondprecision-nanoseconds` | negative, no constraint, type none |
| 4162 | `org.apache.cassandra.cql3.Duration.isNegative()` | CASE `no_constraint-isnegative-duration_fields` | negative, no constraint, type none |
| 4163 | `org.apache.cassandra.cql3.ErrorCollector.isTokenValid()` | CASE `no_constraint-istokenvalid-token_position` | negative, no constraint, type none |
| 4164 | `org.apache.cassandra.cql3.ResultSet.isEmpty()` | CASE `no_constraint-isempty-size` | negative, no constraint, type none |
| 4165 | `org.apache.cassandra.cql3.UntypedResultSet.isEmpty()` | CASE `no_constraint-isempty-size-2` | negative, no constraint, type none |
| 4166 | `org.apache.cassandra.cql3.functions.FunctionName.isNameValid()` | CASE `no_constraint-isnamevalid-disallowed_characters` | negative, no constraint, type none |
| 4167 | `org.apache.cassandra.cql3.functions.UDAggregate.equalsWithoutTypesAndFunctions()` | CASE `no_constraint-equalswithouttypesandfunctions-initcond` | negative, no constraint, type none |
| 4168 | `org.apache.cassandra.cql3.functions.UDFunction.equalsWithoutTypes()` | CASE `no_constraint-equalswithouttypes-body` | negative, no constraint, type none |
| 4169 | `org.apache.cassandra.cql3.functions.types.ParseUtils.isLongLiteral()` | CASE `no_constraint-islongliteral-char` | negative, no constraint, type none |
| 4170 | `org.apache.cassandra.cql3.functions.types.ParseUtils.isQuoted()` | CASE `no_constraint-isquoted-value` | negative, no constraint, type none |
| 4171 | `org.apache.cassandra.cql3.restrictions.ClusteringColumnRestrictions.handleInFilter()` | CASE `no_constraint-handleinfilter-restriction_position` | negative, no constraint, type none |
| 4172 | `org.apache.cassandra.cql3.restrictions.MultiColumnRestriction$SliceRestriction.hasComponent()` | CASE `no_constraint-hascomponent-componentbounds_size` | negative, no constraint, type none |
| 4173 | `org.apache.cassandra.cql3.restrictions.SingleColumnRestriction$ContainsRestriction.isSupportedBy()` | CASE `no_constraint-issupportedby-index_capability` | negative, no constraint, type none |
| 4174 | `org.apache.cassandra.cql3.restrictions.StatementRestrictions.hasUnrestrictedClusteringColumns()` | CASE `no_constraint-hasunrestrictedclusteringcolumns-clustering_count` | negative, no constraint, type none |
| 4175 | `org.apache.cassandra.cql3.restrictions.StatementRestrictions.isColumnRange()` | CASE `no_constraint-iscolumnrange-clustering_restrictions` | negative, no constraint, type none |
| 4176 | `org.apache.cassandra.cql3.restrictions.StatementRestrictions.needFiltering()` | CASE `no_constraint-needfiltering-restriction_count` | negative, no constraint, type none |
| 4177 | `org.apache.cassandra.cql3.selection.ResultSetBuilder.shouldReject()` | covered | already the target of `coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided` |
| 4178 | `org.apache.cassandra.cql3.selection.ResultSetBuilder.shouldWarn()` | covered | in `predicted-negative.md` as the warn twin of `shouldReject()` (`ResultSetBuilder.java:87`) |
| 4179 | `org.apache.cassandra.cql3.selection.SelectorFactories.doesAggregation()` | CASE `no_constraint-doesaggregation-aggregatefactories` | negative, no constraint, type none |
| 4180 | `org.apache.cassandra.cql3.statements.schema.CreateAggregateStatement.isNullOrEmpty()` | CASE `no_constraint-isnullorempty-initcond` | negative, no constraint, type none |
| 4181 | `org.apache.cassandra.db.CBuilder$ArrayBackedBuilder.isDone()` | CASE `no_constraint-isdone-remainingcount` | negative, no constraint, type none |
| 4182 | `org.apache.cassandra.db.ClusteringPrefix$Deserializer.hasComponent()` | CASE `no_constraint-hascomponent-i_nextsize` | negative, no constraint, type none |
| 4183 | `org.apache.cassandra.db.ClusteringPrefix$Serializer.isEmpty()` | CASE `no_constraint-isempty-header_mask` | negative, no constraint, type none |
| 4184 | `org.apache.cassandra.db.ClusteringPrefix$Serializer.isNull()` | CASE `no_constraint-isnull-header_bit` | negative, no constraint, type none |
| set A row 7 | `db/SystemKeyspace.java:1919` | CASE `prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded` | negative |
| set A row 85 | `db/virtual/LogMessagesTable.java:193` | CASE `virtual_logs_max_rows-boundedlinkedlist_add-size` | positive |
| set A row 102 | `io/util/SafeMemoryWriter.java:52` | CASE `no_constraint-resizeto-newcapacity` | negative |
| set A row 103 | `locator/SimpleSeedProvider.java:110` | CASE `seed_count_warn_threshold-getseeds-seeds_size` | negative |
| set A row 104 | `net/BufferPoolAllocator.java:121` | CASE `no_constraint-capacity-newcapacity` | negative |
| set A row 107 | `cache/NopCacheProvider.java:39` | CASE `nopcache_capacity-setcapacity-capacity` | positive |
| set A row 108 | `config/DatabaseDescriptor.java:911` | CASE `native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize` | positive |
| set A row 109 | `config/DatabaseDescriptor.java:914` | CASE `native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxmessagesize` | positive |
| set A row 114 | `config/DatabaseDescriptor.java:1016` | CASE `max_space_usable_for_compactions_in_percentage-applysimpleconfig-range` | negative |
| set A row 115 | `config/DatabaseDescriptor.java:4093` | CASE `repair_session_space-setrepairsessionspaceinmib-sizeinmib` | negative |
| set A row 116 | `config/DatabaseDescriptor.java:4096` | CASE `repair_session_space-setrepairsessionspaceinmib-sizeinmib-2` | negative |
| set A row 117 | `config/DatabaseDescriptor.java:5347` | CASE `repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value` | negative |
| set A row 119 | `config/GuardrailsOptions.java:1257` | CASE `data_disk_usage_max_disk_size-validatedatadiskusagemaxdisksize-disksize` | negative |
| set A row 120 | `config/StorageAttachedIndexOptions.java:41` | CASE `segment_write_buffer_size-validate-maximum_segment_buffer_mb` | negative |
| set A row 127 | `helper org.apache.cassandra.db.ColumnFamilyStore.isCounterCacheEnabled()` | CASE `counter_cache_size-iscountercacheenabled-capacity` | positive |
| set A row 128 | `helper org.apache.cassandra.db.ColumnFamilyStore.isRowCacheEnabled()` | CASE `row_cache_size-isrowcacheenabled-rowcachecapacity` | positive |
| set A row 130 | `db/ColumnFamilyStore.java:2501` | CASE `counter_cache_size-getcachedcounter-capacity` | positive |
| set A row 131 | `db/ColumnFamilyStore.java:2508` | CASE `counter_cache_size-putcachedcounter-capacity` | positive |
| set A row 132 | `db/CounterMutation.java:213` | CASE `counter_cache_size-processmodifications-capacity` | positive |
| set A row 138 | `db/monitoring/MonitoringTask.java:221` | CASE `monitoring_max_operations-operationsqueue_offer-maxoperations` | positive |
| set A row 141 | `db/rows/ThrottledUnfilteredIterator.java:234` | CASE `mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize` | positive |
| set A row 142 | `db/tries/InMemoryTrie.java:64` | CASE `row_overhead_size-intrie_init-limitinmb` | positive |
| set A row 143 | `db/tries/InMemoryTrie.java:145` | CASE `no_constraint-allocateblock-inchunkpointer` | negative |
| set A row 145 | `index/sai/StorageAttachedIndex.java:503` | CASE `sai_vector_search_max_top_k-validate-limit_count` | positive |
| set A row 146 | `index/sai/StorageAttachedIndex.java:791` | CASE `no_constraint-validatetermsizeforcell-cellbufferremaining` | negative |
| set A row 154 | `index/sai/memory/VectorMemoryIndex.java:190` | CASE `vector_memory_index_cost_model-orderby-bruteforcerows` | negative |
| set A row 155 | `index/sai/memory/VectorMemoryIndex.java:229` | CASE `vector_memory_index_cost_model-orderresultsby-maxbruteforcerows` | negative |
| set A row 110 | `config/DatabaseDescriptor.java:978` | SKIP | config-type; record in `skipped-config-type.md` |
| set A row 111 | `config/DatabaseDescriptor.java:981` | SKIP | config-type; record in `skipped-config-type.md` |
| set A row 112 | `config/DatabaseDescriptor.java:984` | SKIP | config-type; record in `skipped-config-type.md` |
| set A row 113 | `config/DatabaseDescriptor.java:987` | SKIP | config-type; record in `skipped-config-type.md` |
| set A row 118 | `config/GuardrailsOptions.java:1219` | SKIP | config-type; record in `skipped-config-type.md` |

**Batch 1 (2026-10-27):** wave 1 took the first 8 band D helper units (CSV lines 4155-4162): 7 case files, 1 unresolved, 0 skips.

**Batch 2 (2026-10-27):** waves 2 and 3 took the next 20 band D helper units that were not covered (CSV lines 4163-4176 and 4179-4184): 20 case files, 0 skips, 0 unresolved; lines 4177 and 4178 were covered. Next unit: CSV line 4185.

**Set A open rows (2026-10-27):** the 32 set A rows that had no case file (`writeup-set-A.csv`, the "skip the 32 open rows" decision) were run through the non-config agent with the widened constant rule (a numeric literal counts as a constant): 27 case files (13 positive, 14 negative) and 5 config-type skips. Row 7 (`SystemKeyspace.java:1919`) was earlier settled as a second check site of `prepared_statements_cache_size` (`undetermined.md` §5.2); it now has its own case file.
