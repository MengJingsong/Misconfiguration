# Convergence playbook — batch log

Append one entry per playbook run, per [`../../convergence-playbook.md`](../../convergence-playbook.md).

## 2026-11-02 — run 1

**Node:** `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB RAM, local disk `/dev/sda3` 63 GB). JDK 11.0.32.1 and Ant 1.10.12 installed fresh; source copied from repository commit `0be49fb6` to `~/cassandra-run1` via `copy-source.sh`, built with `ant build-test`.

**Shared-budget group surveyed:** on-heap JVM heap (`-Xmx`), using the two config-type true-positive cases the task pointed at: `memtable_heap_space` (memtable pool, soft/self-reclaiming cap) and `counter_cache_size` (counter cache, Caffeine weight cap, non-self-reclaiming). Both draw on the same single-node `-Xmx`.

**Combinations attempted:**

1. `memtable_heap_space` (M=550 MiB) + `counter_cache_size` (C=300 MiB), `-Xmx1024M`/`-Xms1024M`, concurrent `cassandra-stress write` + `cassandra-stress counter_write` — case file: [`memtable_heap_space+counter_cache_size.md`](memtable_heap_space+counter_cache_size.md). **Result: OOM reached** (14 genuine `OutOfMemoryError: Java heap space` throws across unrelated thread pools; both control arms safe with 33–39% free margin).

**Combinations considered and skipped (not built or run):**

- A larger 3-way combination (adding `index_summary_capacity`, `row_cache_size`, or `native_transport_max_request_data_in_flight` on top of the two already run) was not attempted this run: the 2-constraint combination above already reached OOM at a comfortable margin (126% of `-Xmx` predicted, 96.6% used + 0 young regions actually observed), so a 3-way combination would not add evidence about whether 2 constraints already suffice — it would need its own fresh sizing and control arms to be a real case, and the playbook asks for rigor over quantity on the first run.
- No other shared-budget group (off-heap/direct memory, disk) was surveyed this run; this run's budget was fixed by the task to on-heap JVM heap only.

**Stopping reason:** time/rigor budget for a first run — one combination was built, sized with a stated arithmetic prediction, run through both control arms and the convergence arm, and filed as a complete case with raw-log evidence for every claim. The shared-budget group (on-heap, these two constraints) is not marked exhausted: a 3-constraint extension on the same heap budget (e.g. adding `row_cache_size` or `index_summary_capacity`) remains open for a future run, as does trying smaller M/C values to find the actual minimum combined sizing that still OOMs (this run deliberately sized with margin to exceed, not to find the tightest boundary).

**Verification environment notes carried to the next run:** `jcmd GC.heap_info` and `jcmd GC.run` both slow down sharply (14 s and 74 s respectively, vs. <1 s normally) once the heap is genuinely under OOM pressure — budget extra wall-clock time for the final reading in a future convergence arm that pushes this hard. `sudo dmesg -T` needs `sudo` (plain `dmesg` fails with "Operation not permitted" on this node's kernel).
