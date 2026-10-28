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

**Batch 1 (2026-10-27):** wave 1 took the first 8 band D helper units (CSV lines 4155-4162): 7 case files, 1 unresolved, 0 skips.

**Batch 2 (2026-10-27):** waves 2 and 3 took the next 20 band D helper units that were not covered (CSV lines 4163-4176 and 4179-4184): 20 case files, 0 skips, 0 unresolved; lines 4177 and 4178 were covered. Next unit: CSV line 4185.
