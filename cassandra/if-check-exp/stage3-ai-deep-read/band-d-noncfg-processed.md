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

**Batch 1 (2026-10-27):** wave 1 took the first 8 band D helper units (CSV lines 4155-4162): 7 case files, 1 unresolved, 0 skips. Next unit: CSV line 4163.
