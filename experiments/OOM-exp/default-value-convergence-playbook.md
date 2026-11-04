# Default-value convergence playbook (Direction 1, default-value variant)

**This playbook is [`convergence-playbook.md`](convergence-playbook.md) plus one
restriction: every constraint in a combination stays at its default value.**
Give the agent both files. Everything in the original playbook applies
unchanged (one agent end to end, a batch of cases per run, control arms
before the convergence arm, the four-section case template, process hygiene,
no commit unless asked) **except where this file overrides it**. Where the
two disagree, this file wins for a default-value run.

## Why this variant exists

The original convergence cases all raised their constraints above the
defaults. Run 1, for example, used `memtable_heap_space: 550MiB` (default 1/4
heap, 256 MiB at its 1 GiB heap) and `counter_cache_size: 300MiB` (default
`min(2.5% heap, 50MiB)`, 25 MiB there). Those cases show that Cassandra never
checks the **sum** of individually valid settings against the node's memory.
But they need an operator to change at least two settings.

This variant asks the stronger question: **does a node running Cassandra's
own defaults OOM when several default-capped pools fill at the same time?**
If yes, the gap needs no misconfiguration at all, only a workload. If no, the
arithmetic of why not (the defaults are sized to fit together, or the pool is
off by default) is the finding, and it bounds how far the original cases
depend on non-default values.

## The goal, per case

As in the original: two or more constraints from `if-check-exp` that draw on
the same budget, each safe alone at capacity, together exceeding the budget
and OOMing the node. Here, **"at capacity" means at the capacity the default
value gives on this node**.

## What "default value" means

1. **The constraint's own knob is not set by the run.**
   - **yaml key:** the value in the shipped `conf/cassandra.yaml` at the
     pinned tag (`cassandra-5.0.9`). If the key is commented out or empty
     there, the code default (`Config.java` / `DatabaseDescriptor`) applies.
     A commented-out example value is **not** the default (for example the
     shipped `# memtable_heap_space: 2048MiB`; the real default is 1/4 heap).
   - **JVM system property** (`-Dcassandra.*`): absent from the command
     line, so `CassandraRelevantProperties` supplies its default.
   - **Per-table option** (caching, compaction, compression and so on): left
     unset in the `CREATE TABLE`, so the table default applies.
   - **Hard-coded constant:** untouched by definition (never rebuild the
     source to change one).
2. **Heap-relative defaults follow the budget, and that is allowed.** Many
   defaults are a fraction of the heap: `memtable_heap_space` and
   `memtable_offheap_space` 1/4 heap, `counter_cache_size`
   `min(2.5% heap, 50MiB)`, `key_cache_size` `min(5% heap, 100MiB)`,
   `index_summary_capacity` 5% heap. Choosing the heap size changes their
   resolved values; the knob is still at its default. Record the **resolved**
   value at this budget, not just "default".
   **The memory limits themselves come from `conf/cassandra-env.sh`, not the
   JVM's own defaults.** With nothing set, `calculate_heap_sizes()` gives a
   heap of `min(1/2 RAM, 31744 MiB)` under G1 (15,872 MiB under CMS), and
   `-XX:MaxDirectMemorySize` of `1/4 RAM`, capped at half the heap limit
   (15,872 MiB under G1). The direct limit is computed from the node's RAM,
   **not** from the heap, so setting `MAX_HEAP_SIZE` alone leaves it large
   (run 8's command line showed 15,872M on a 251 GiB node before its own
   override). Both read RAM with `free -m`, i.e. the host's RAM, even inside
   a cgroup or container.
3. **Verify the default, do not assume it.** For every constraint, record in
   section 1:
   - the default rule, with `file:line` (shipped yaml line, `Config.java`,
     `DatabaseDescriptor`, or `CassandraRelevantProperties`);
   - the resolved value on this node, from Cassandra's own output where it
     prints one (for example `Global memtable on-heap threshold is enabled
     at …`, `Initializing counter cache with capacity of … MiBs`, or a JMX
     read) or by arithmetic from the rule and the measured heap;
   - evidence the knob was left alone: the arm's yaml diff against the
     shipped file does not touch it, and the JVM command line has no `-D` for
     it.

## What may change, and what must not

Every arm's `cassandra.yaml` diff against the shipped file and every non-default
JVM flag goes into a **defaults audit** table in section 2, each line in one
of these classes:

| Class | Allowed? | Examples |
|---|---|---|
| **Environment** | yes, freely | `cluster_name`, `listen_address`, `rpc_address`, `seed_provider`, `num_tokens`/`initial_token`, `auto_bootstrap`, data/commit log/hints/saved-caches directories (on local disk), `endpoint_snitch` and `cassandra-rackdc.properties` for a multi-node or multi-DC topology, JMX port, `-XX:NativeMemoryTracking` and other read-only instruments |
| **Budget** | yes, this is the experiment's dial | heap size (`MAX_HEAP_SIZE` / `-Xmx`, or the automatic heap `cassandra-env.sh` computes), the direct-memory limit (`MAX_DIRECT_MEMORY_SIZE` / `-XX:MaxDirectMemorySize`, or the automatic one), a cgroup or container memory limit, a dedicated disk mount |
| **Supporting deviation** | only if unavoidable, justified, and listed | anything else not a constraint in the combination: `memtable_cleanup_threshold`, `memtable_allocation_type`, `file_cache_enabled`, `concurrent_writes`, timeouts |
| **Constraint change** | **never** | setting any constraint in the combination to a non-default value |

**A case with no supporting deviation is a strict default case.** A case
with one or more is filed as **"default constraints, with supporting
deviations"**, and its conclusion must say whether the OOM still depends on
those deviations. Prefer a strict case. A supporting deviation that changes
how far a constrained pool can fill (for example run 1's
`memtable_cleanup_threshold: 0.99`, without which the memtable flushes long
before its limit) is a strong caveat, because it does part of what the
restriction forbids. Name it as such.

**Budget realism.** The heap may be set to any size, but the case file must
compare it with Cassandra's own guidance: the
[Hardware Choices page](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hardware.html)
says the heap "should be no less than 2GB, and no more than 50% of your
system RAM". Also compare it with the heap and direct limit
`cassandra-env.sh` would pick automatically for the node's RAM (see item 2 under
"What 'default value' means"). A budget below the documented minimum is
allowed (absolute defaults dominate at small heaps, which is often where
convergence is possible) but weakens the Target-3 note. Say so.

**The workload is not configuration.** Schema shape (columns, value sizes,
replication factor, number of tables), client concurrency, data volume,
topology (a down replica for hints), and timing are all free choices, as in
the original playbook. Only per-table options that are themselves
constraints must stay unset.

## Picking combinations (overrides)

Follow the original's "Picking combinations" with these changes:

1. **Use this playbook's own batch log,**
   [`cases/default-convergence/_batch-log.md`](cassandra/cases/default-convergence/_batch-log.md),
   and its group status table. The original's statuses do **not** carry
   over: a group marked exhausted for raised values is a different question
   at defaults. The disk group's **skipped** status does carry over until it
   is lifted in this batch log.
2. **Check that the pool exists at its default.** Several capped pools are
   off by default and cannot be used: in 5.0.9 `row_cache_size` defaults to
   `0MiB` (row cache disabled) and `file_cache_enabled` to `false` (the
   chunk cache holds no data). Turning one on is a supporting deviation at
   best. Read the resolved default first.
3. **Check that the default actually caps.** A default that means "no
   limit" (for example `max_hints_size_per_host: 0B`, unlimited) is not a
   capped pool at its default, so it is not a convergence candidate here.
   Note it in the batch log as a candidate for
   [`bypass-playbook.md`](bypass-playbook.md) or for a separate "unbounded at
   default" note.
4. **Do the default arithmetic before building anything.** For each group,
   write each candidate's default capacity as a function of the budget (heap
   fraction, absolute size, or per-thread × thread count). Then:
   - if every candidate is a fixed heap fraction, the summed fractions (times
     each pool's measured overhead factor from `if-check-exp`, plus
     baseline) either exceed 100% at every heap size or at none. If they
     never do, the group **cannot converge at defaults**: record the
     arithmetic and mark it so, without forcing a case;
   - **absolute** defaults (fixed MiB, or per-thread × a default thread
     count) shrink relative to a small budget and grow relative to a large
     one. Find the budget range, if any, where each alone is safe (≥ 30%
     free, as in the original) and the sum exceeds the budget. That range,
     and where it sits against the documented 2 GB minimum, is part of
     section 2;
   - absolute defaults on a budget the operator sizes independently are
     often where a window exists (for example `allocateDirect` pools such as
     the hints buffers, `MAX_HINT_BUFFERS` × 32 MiB = 96 MiB by default,
     under a `MaxDirectMemorySize` set for a container).
5. **Prefer combinations reachable from ordinary traffic** (the original's
   Target-3 preference applies doubly here, since the config is not the
   "misconfiguration").

## Designing, sizing and running (overrides)

- **Sizing step 1 ("size each one safe alone")** becomes **choose the
  budget**: the constraint values are fixed by the defaults, so the only
  sizing dial is the budget (and the workload). State the chosen budget, the
  window found in "Picking" step 4, and each arm's predicted margin.
- **Sizing step 2 ("size the combination to exceed it")** is the same
  arithmetic with the resolved default capacities.
- **Control arms** run at the same budget, with the same yaml and JVM flags
  as the convergence arm; only the workload differs (as in runs 7-8).
- **A useful extra arm, when a case OOMs:** if the original convergence
  playbook already has a case for the same constraints at raised values,
  cite it; if a supporting deviation was needed, run the convergence arm once
  without it, if feasible, to show whether the OOM depends on it.

## Output (additions to the original template)

Write one file per attempted combination to
`cases/default-convergence/<constraint-1>+<constraint-2>[+...].md`, with the
original four sections and these additions:

- **Section 1:** per constraint, add rows for *default rule (`file:line`)*,
  *resolved value at this budget (with the evidence line)*, and *knob left
  unset (evidence)*. State whether the case is **strict default** or
  **default constraints, with supporting deviations**.
- **Section 2:** add the **defaults audit** table (every yaml diff line and
  non-default JVM flag, classed environment / budget / supporting deviation),
  and the budget-window arithmetic from "Picking" step 4, including where the
  budget sits against the documented 2 GB minimum and the automatic heap.
- **Section 4:**
  - **if the node OOMed:** state it as *a node with Cassandra's default
    values for these constraints OOMs under this workload at this budget*,
    plus whether any supporting deviation was needed;
  - **if not, or if the group cannot converge at defaults:** state why from
    the arithmetic (defaults sized to fit together, pool off by default,
    default not a cap, or no budget window), and name the **smallest
    non-default change** that would make it converge, cross-referencing the
    original convergence case where one exists.

Keep the batch log at `cases/default-convergence/_batch-log.md` (one entry
per run, same content as the original's, plus the default-arithmetic verdict
per group surveyed). Track closed cases in [`_INDEX.md`](cassandra/_INDEX.md) under
their own "Default-value convergence cases" table.
