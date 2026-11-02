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

## 2026-11-02 — run 2

**Node:** same node (`pc41`/`node0.jason92-323989...`), same build (`~/cassandra-run1` at `cassandra-5.0.9`, unchanged since run 1 — no rebuild needed).

**Shared-budget group surveyed:** same on-heap JVM heap group as run 1, extended to a 3rd constraint — the open follow-up from `HANDOFF.md`. Checked the two candidates it suggested (`row_cache_size`, `index_summary_capacity`) against their stage-4 results for the first time: both are **off-heap** (`Native.malloc`/off-heap index-summary bytes), not on-heap, so neither is a clean addition to this group. Surveyed on-heap true positives instead and picked `key_cache_size` (config-type true positive, same Caffeine-weighted-cache family as `counter_cache_size`).

**Combinations attempted:**

1. `memtable_heap_space` (M=350 MiB) + `counter_cache_size` (C=250 MiB) + `key_cache_size` (K=200 MiB), `-Xmx1024M`/`-Xms1024M`, concurrent `write` + `counter_write` + `read` (the read arm needs a preloaded, flushed dataset — key cache only engages on sstable reads, not memtable reads) — case file: [`memtable_heap_space+counter_cache_size+key_cache_size.md`](memtable_heap_space+counter_cache_size+key_cache_size.md). **Result: OOM reached, JVM killed.** Smaller individual values than run 1's 2-constraint case (chosen so no pairwise subset was already enough to overshoot), each alone safe (46–87% heap free, 0 errors), combined drove the heap to 989/1024 MiB (96.6%) right after a forced full GC with a 72-byte allocation failing, a genuine `OutOfMemoryError`, a 1.35 GB heap dump, and — unlike run 1's case, where the JVM survived — `-XX:OnOutOfMemoryError=kill -9 %p` actually fired and killed the process.

**Combinations considered and skipped (not built or run):**

- A 4th constraint on top of M+C+K was not attempted: the 3-way combination already reached a harder outcome (genuine crash, not just caught `OutOfMemoryError`s) than run 1's 2-way case, so a 4th constraint wouldn't add evidence about whether 3 already suffice.
- The off-heap group (`row_cache_size` + `index_summary_capacity`, both off-heap true positives found while surveying this run) was noted but not run: off-heap convergence needs a different way to make the budget tight (the node's 251 GiB of physical RAM is not a usable ceiling for off-heap the way `-Xmx` is for on-heap; off-heap budgeting here would likely need a cgroup memory limit or similar, not yet set up) — left as a candidate for a future run, possibly closer to `bypass-playbook` territory if `-XX:MaxDirectMemorySize` turns out to be the more relevant constraint.
- Finding the tighter minimum M+C+K boundary (vs. this run's margin-sized values) was not attempted — same "rigor over quantity" reasoning as run 1.

**Stopping reason:** one new combination built, sized with a stated arithmetic prediction, run through three control arms plus the convergence arm, and filed as a complete case. One harness bug was hit and fixed mid-run (the `read` workload's `cassandra-stress` call needed `-col` to match the preload write's or validation failed immediately — see the case file §2.3/Instrument check) — the result reported is the corrected re-run, not the failed first attempt.

**Verification environment notes carried to the next run:** when the JVM genuinely runs out of room (not just gets close), `jcmd GC.run` can take minutes (3m40s here) to return, and a subsequent `jcmd GC.heap_info` can fail outright with `Premature EOF` if the process dies in between — treat a failed final heap sample as a signal to check `logs/gc.log`'s last lines (`ReportJavaOutOfMemory` safepoint) and for an `.hprof` file before assuming the harness itself broke. `set -Eeuo pipefail` scripts should expect this failure mode (a non-zero `jcmd` return) to trip the `ERR` trap and skip the harness's own post-run steps (error-count, oom-grep, dmesg) — recompute them manually from `system.log`/`dmesg` directly when that happens, which is what `converge/error-count.txt`'s comment in this case does.
