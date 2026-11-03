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
| [`row_cache_size` + `index_summary_capacity`](cases/convergence/row_cache_size+index_summary_capacity.md) | **Not reached (superseded by run 6)** — safe alone (24-29% free), combined peak 90% of a cgroup budget (naive sum predicted 106%); each cache's own eviction/resize kept operating under combined load |
| [`row_cache_size` + `index_summary_capacity` (run 5 retry)](cases/convergence/row_cache_size+index_summary_capacity--run5.md) | **Void** — the concurrent burst wrote 0 partitions (stress client's CREATE TABLE timed out); superseded by run 6 |
| [`row_cache_size` + `index_summary_capacity` (run 6, retries A and B)](cases/convergence/row_cache_size+index_summary_capacity--run6.md) | **OOMed (schedule B)** — row cache full, then index-summary burst: kernel cgroup OOM-kill at 1973 MiB of 2000 (alone 78% / 80%); concurrent schedule A peaked at 93%, no kill; with a 1 m resize, no off-heap kill (93%) but an unattributed Java heap OOM |
| [`memtable_offheap_space` + `file_cache_size`](cases/convergence/memtable_offheap_space+file_cache_size.md) | **OOMed** — each alone 78% of a 3500 MiB cgroup budget; chunk cache full, then a write burst: kernel OOM-kill 16 s in (3465 MiB anon) |

## Bypass cases ([`bypass-playbook.md`](bypass-playbook.md))

| Constraints | Result |
|---|---|
| *(none yet)* | |
