# OOM-exp — Case Index

Every closed case, one row each, by direction. Update this file when a case
file is added or its result changes.

**Table-width rule.** Keep the table narrow enough that it never needs a
horizontal scrollbar: link text is the case's short name only (no full URL),
and **Result** is a one-line verdict phrase, not the finding — detail,
numbers and the conclusion live in the case file itself, linked from the row.
If a result needs more than one line to state, shorten it and let the case
file carry the rest.

## Convergence cases ([`convergence-playbook.md`](convergence-playbook.md))

| Constraints | Result |
|---|---|
| [`memtable_heap_space` + `counter_cache_size`](cases/convergence/memtable_heap_space+counter_cache_size.md) | **OOMed** — safe alone, combined usage exceeded the heap (14 `OutOfMemoryError` throws) |
| [`memtable_heap_space` + `counter_cache_size` + `key_cache_size`](cases/convergence/memtable_heap_space+counter_cache_size+key_cache_size.md) | **OOMed, JVM killed** — safe alone, combined drove heap to 96.6% and crashed the process |
| [`commitlog_total_space` + `max_hints_size_per_host`](cases/convergence/commitlog_total_space+max_hints_size_per_host.md) | **Not reached, blocked** — control arm ran the disk budget full from flush/compaction overhead before a convergence arm could run; retryable, not exhausted |
| [`row_cache_size` + `index_summary_capacity`](cases/convergence/row_cache_size+index_summary_capacity.md) | **Not reached** — safe alone (24-29% free), combined peak 90% of a cgroup budget (naive sum predicted 106%); each cache's own eviction/resize kept operating under combined load |

## Bypass cases ([`bypass-playbook.md`](bypass-playbook.md))

| Constraints | Result |
|---|---|
| *(none yet)* | |
