# default_page_size — trace-back only  <!-- file: traceback-only/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/filter/DataLimits.java:1041` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** `SelectStatement.DEFAULT_PAGE_SIZE`, a compile-time constant (not a yaml/JVM property) that caps the internal row page size of GROUP BY queries so they are "always paged internally to avoid OOM"; it is first declared at `src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:114` as `public static final int DEFAULT_PAGE_SIZE = 10000`, in rows per internal page, with a hard-coded default of 10000 (no derivation). The check at `db/filter/DataLimits.java:1041` (`CQLGroupByLimits` counter `onClose`, `rowsCounted < rowLimit`) compares the rows counted against `rowLimit`, which is the third argument of `DataLimits.groupByLimits(...)` (`DataLimits.java:116-121`) and is stored by the `CQLGroupByLimits` constructor via `super(rowLimit, NO_LIMIT, false)` (`DataLimits.java:679`, field at `DataLimits.java:349`). `SelectStatement.getDataLimits` supplies this value as `pageSize` (`SelectStatement.java:911-914`): it is the client-supplied page size from `options.getPageSize()` (`SelectStatement.java:291`) when that is positive, and otherwise falls back to `DEFAULT_PAGE_SIZE` (`SelectStatement.java:900-902`). The constant cannot be changed by yaml, -D property or JMX and needs a rebuild and restart. The only way to change the effective value is per request through the client page size, which the `page_size` guardrail can bound (`Guardrails.pageSize.guard`, `SelectStatement.java:517`; `page_size_warn_threshold` and `page_size_fail_threshold`, both default -1 and volatile, at `config/Config.java:873-874`).
