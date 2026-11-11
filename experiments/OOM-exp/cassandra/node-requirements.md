# Nodes for the next Cassandra OOM batch

Planning guidance for C1, B1, C2 (2026-11-06), not an inventory of live allocations.
Revalidate allocation hostnames and resources before using any historical node.

> **Note (2026-11-10).** The current allocation (see [`HANDOFF.md`](../HANDOFF.md),
> *Available nodes*) is `pc96` (32 cores, ~125 GiB) plus five r320 nodes
> `apt138/140/149/179/190` at 8 cores / **16 GiB** — below the 32 GiB victim
> recommendation below. C1 run 3 used `apt140` as its victim with a 1 GiB heap /
> 3072 MiB direct / 7168 MiB cgroup budget, which fit; B6 run 1 ran all three
> instances on `pc96` (2 GiB measured heap, 8 GiB peers) and run 2 six (8/6 GiB replica,
> five 8 GiB peers, a dm-delay device under `/mydata/b6/slow`). Use `pc96` for any victim
> or peer that needs several GiB of heap (e.g. B6's 8 GiB deployment-heap arm);
> an r320 victim is fine when the experimental budget is small and recorded.
Baseline setup: [stage-4 environment](../../if-check-exp/cassandra/stage4-runtime-verification/environment.md).

## Recommended allocation

**Four owned CloudLab nodes** is a useful starting allocation: one exclusive
victim, two peer hosts, and one controller/load-generator host. C1 needs multiple
peer identities, not merely many native client connections. Sweep initially
1/2/4/8 active peer instances as host resources permit; several isolated Cassandra
instances may run per peer host with distinct addresses, ports, directories and
budgets. Calibrate their CPU/RAM/network headroom. This is an initial range, not
a guarantee of reproducing OOM; more peer hosts may be needed if sender limits
or topology prevent the intended overlap. Never count configured but inactive
peers as multiplicity. Multiple processes per peer host are a documented topology
choice, not equivalent to independent physical machines in every respect.

**Two nodes** can start B1 and C2 (victim + client/controller). A C1 topology can
be piloted with colocated peers but must account for shared-host interference.
Do not let insufficient C1 resources block the independent B1/C2 investigations.

## Resource and access checklist

| Item | Requirement / planning recommendation |
|---|---|
| Ownership/exclusivity | Researcher's allocated nodes, one measured experiment per victim; no competing research workloads on that victim |
| OS/toolchain | Prefer the existing Ubuntu 22.04/JDK 11/Ant baseline; record exact patch versions and keep them consistent across arms. Python, git, rsync, jcmd/jstack, Cassandra stress/cqlsh or a protocol-capable driver |
| CPU/RAM | Practical starting recommendation: victim at least 8 cores and 32 GiB RAM; 64 GiB+ preferred. Size peer hosts for all instances (often 64 GiB+ useful). These are planning estimates, not Cassandra minimums. Large physical RAM is fine: control victim heap/direct/cgroup budgets explicitly |
| Local storage | Prefer at least 100 GiB free per data host; actual admission check is data + compaction/flush headroom + logs + planned dumps. A smaller disk is usable for a sized workload; reject a run whose projected footprint does not fit |
| SSH/privileges | SSH from controller; sudo or equivalent delegated cgroup permissions, kernel/journal access, and ability to recover/restart owned processes. Console/reboot access for unexpected node failure |
| Isolation | Prefer cgroup v2 for victim process limits and memory.events; controller/client outside victim group. Record all limits, memory accounting and swap policy. Keep swap fixed; disable for victim if supported, without changing unrelated workloads |
| Network | Owned peer/client connectivity; required Cassandra internode/native/JMX ports available within test network, unique ports/addresses for multiple instances; synchronized clocks |
| Build dependencies | Outbound package/Maven access during setup or a validated dependency cache; pinned source copied to local disk, never built in vendored source/shared NFS |
| Evidence | GC logs, JMX/low-overhead metrics, process/cgroup counters, kernel kill evidence and persistent per-run output paths. Save original OOM before cleanup |

## Preflight before each case

Record machine inventory, allocation expiry, repository/source/build identity,
resolved JVM flags, cgroups and swap. Build and smoke-test Cassandra; verify node
and native protocol readiness. Confirm driver protocol selection for B1 and actual
read-threshold applicability for C2. Confirm workload completion and sufficient
sender/client headroom. Check local free space, timestamps, metrics, and kill-event
visibility. Make cleanup target run-owned PIDs/directories only. Budget and measure
the victim process independently of host RAM and colocated peers.

Freeze the experiment's exact heap/direct/cgroup budgets after calibration; use
the same values in matched arms. Physical node capacity is not the experimental
budget. Keep remote control available if the victim JVM is killed.
