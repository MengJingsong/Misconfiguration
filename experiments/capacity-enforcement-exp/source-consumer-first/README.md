# Lead source: consumer-first (added 2026-11-25, owner; designed, not started)

> **Paths (multi-system layout).** This is a system-agnostic method doc. Per-system data will live in
> `experiments/capacity-enforcement-exp/<system>/source-consumer-first/`.

## Why

Stage 1 and the [config-first source](../source-config-first/README.md) both start from a **constraint**.
Memory that **no constraint governs** has neither a check nor a configuration entry. Phase 1 reaches it
only when an agent reading a nearby case notices it. Several phase-2 true positives are of this kind
(unprotected accumulation: U3 whole-collection reads, U5/R14 the IN × IN key product, U6/R20 one error
message per bad character).

The consumer-first source starts from **the memory consumers**: where memory is allocated and kept.
It asks whether anything limits each consumer.

## Two parts

| Part | What it does | Finds | Misses |
|---|---|---|---|
| **A. Static allocation-site query** (CodeQL) | Allocation sites whose size comes from input or stored data (`new byte[len]`, `ByteBuffer.allocate*(n)`, `new T[n]`, `StringBuilder`/collection growth in a loop over input, `add`/`put` into a long-lived field) **with no capacity check on the path** between the input and the allocation. This is the complement of stage 1's enforcement-place set: README §3.7 calls a data-sized allocation an allocation site, not a capacity | paths no workload exercises | memory that grows over time rather than per request; flows CodeQL cannot follow |
| **B. Scaling profile** (runtime) | The same workload run at increasing values of **one** dimension (request size, items per collection, connections, tables, concurrency, idle time). Each run records allocation sites with stacks (async-profiler `alloc` mode, or JFR `ObjectAllocationSample`), retained heap per dominator (heap dump plus Eclipse MAT), and off-heap memory (`-XX:NativeMemoryTracking=summary`, Netty's used direct memory, memcg `memory.stat`). A consumer whose live size keeps growing with the dimension and does not level off is a lead | retention and accumulation over time; off-heap consumers | anything the workload does not reach |

Part A's leads give part B its targets: a workload is built to reach each site. Part B's leads that
part A did not find show where the static query is too narrow.

## Output

Each lead becomes a **unit for stage 3** (the site, the dimension that grows it, and the evidence).
A stage-3 autonomous agent traces whatever limits the consumer, if anything, and writes **an ordinary
stage-3 case file** with the header row `Lead source | consumer-first`. When the agent finds no constraint,
the case is a `none`-type case and goes through the `none`-type stage-4 design that awaits the owner
(FLOWCHART §5.2). Stages 4 and 5 then apply unchanged, and the `Lead source` row gives this source's
true-positive rate.

## Rules

- **Nodes:** part B runs on a test node under the usual node lock (`/mydata/s4/NODE-LOCK`), on a copy of
  the pinned source made with `copy-source.sh`, with nothing left running afterwards.
- **Workloads:** synthetic data only, with defaults for every capacity setting. A dimension that only
  grows past a non-default constraint is out of scope (phase-2 scope rule, 2026-11-23).
- **Order:** Cassandra first; Hadoop needs one workload per daemon (NameNode, DataNode, ResourceManager,
  NodeManager, task JVMs) and follows later.

## Status

| System | Part A | Part B |
|---|---|---|
| Cassandra | not started | not started |
| Hadoop | – | – |
