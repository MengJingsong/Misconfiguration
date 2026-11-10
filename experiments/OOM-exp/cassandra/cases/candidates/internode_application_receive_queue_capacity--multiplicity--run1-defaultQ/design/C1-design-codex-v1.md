# C1 revised run design, Codex v1

Draft for review, 2026-11-09. This document specifies a proposed experiment. Runtime results remain to be collected.

## 1. Purpose and claim

Test whether multiplying Cassandra's exclusive per-connection receive allowances causes live memory to exceed a fixed victim budget while the local admission rules and shared reserves continue to work.

The main experiment keeps the receive capacities at their Cassandra 5.0.9 defaults and uses a deliberately tightened diagnostic memory budget. The intended evidence is a surviving low-multiplicity condition with the global reserve already saturated, followed by a failing higher-multiplicity condition, accompanied by measured growth in exclusive occupancy and physical memory. A reduction in the exclusive allowance at the same high multiplicity supplies a causal control.

Source identity supplied by the original design is `cassandra-5.0.9` (`b5f2a54210`). Verify the deployed source and build before execution. Follow the [verification protocol](../../../../../verification-protocol.md), [default convergence playbook](../../../../../default-convergence-playbook.md), and [campaign scope](../../../../campaign-plan.md).

## 2. Protection map and corrected model

`AbstractMessageHandler.acquireCapacity`, lines 411–459, admits bytes within a connection's Q without borrowing. Excess bytes require both global and endpoint reserve permits. Release occurs after processing or expiry through the corresponding release paths.

| Symbol | Scope | Default |
|---|---|---|
| Q | Exclusive allowance per receive connection | 4 MiB |
| E | Reserve shared by receive connections from one endpoint | 128 MiB |
| G | Receive reserve shared across endpoints | 512 MiB |
| N | Active workload senders reaching the victim | Swept |
| k | Loaded connection types per active sender | Initially 1 |

For the intended workload, the modeled upper bound on charged bytes is

`A_max(N, k) = N × k × Q + min(G, N × E)`.

Endpoint reserves are shared across connection types, so k multiplies Q only. This model assumes one relevant connection of each loaded type per sender and excludes separately measured background traffic. Reconnects and additional handlers must be detected and incorporated into the measured connection count.

| N, with k = 1 | Exclusive allowance | Available shared borrowing | Charged-byte upper bound |
|---:|---:|---:|---:|
| 1 | 4 MiB | 128 MiB | 132 MiB |
| 2 | 8 MiB | 256 MiB | 264 MiB |
| 4 | 16 MiB | 512 MiB | 528 MiB |
| 8 | 32 MiB | 512 MiB | 544 MiB |
| 16 | 64 MiB | 512 MiB | 576 MiB |
| 32 | 128 MiB | 512 MiB | 640 MiB |

These are ceilings, subject to message granularity, admission timing, and achievable overlap. One peer cannot saturate G because E limits its borrowing. The primary reference is therefore four active peers with measured reserve saturation. Four to 32 peers adds a modeled 112 MiB of exclusive allowance.

Physical memory depends on baseline allocations, queued representations, processing allocations, buffer fragmentation and retention. The historical 1.4–1.5 multiplier for large-message buffers is a calibration lead. Estimate physical memory from measured occupancy and pool allocations in this workload.

## 3. Fixed topology and workload

The proposed allocation from the original draft is one victim on apt140 and peer hosts apt179, apt138, apt190 and apt149. Revalidate ownership, allocation lifetime, addresses and resources. Up to eight Cassandra instances per peer host yield 32 sender identities. Record explicit heap/process budgets and demonstrate host headroom under the full replication load.

Use a fixed ring of 33 instances throughout the principal comparison, with a fixed `SimpleStrategy` RF of 33 in the single-datacenter test topology. All instances remain joined while N selects the coordinators receiving generated writes. This keeps membership and replica fanout constant. Every write is replicated to the victim and the other replicas, so peer capacity must be calibrated against the full fanout.

Proposed alias blocks are `10.10.1.32–39`, `10.10.1.48–55`, `10.10.1.64–71`, and `10.10.1.80–87`, one block per peer host. These are provisional addresses requiring confirmation against the allocated LAN and existing assignments. Each instance uses its own address, directories, and JMX endpoint. Verify that native transport binds to the intended identity and that the workload actually uses the selected coordinator. Record and remove only aliases created for this run.

Use a driver or stress configuration whose actual coordinator selection is verifiable. Restrict coordinator selection to the selected N senders. Record victim-side peer identities and connection types. Spread selected senders across physical hosts where possible, and repeat boundary conditions with balanced assignments to check host-placement effects.

Freeze payload, schema, consistency level, timeout settings, total offered rate and total outstanding-request limit for the principal sweep after calibration. A separate fixed-per-sender load sweep may establish reachability. Record offered, accepted and completed work separately. Choose and document a consistency level that makes victim participation observable, with sufficient client concurrency to sustain the intended backlog.

## 4. Allocation domain and slow-consumer condition

Start with Arm D, large internode mutations whose measured serialized sizes exceed the configured large-message threshold, approximately 64 KiB at default. Queued frames use the networking buffer pool, whose backing allocations use `ByteBuffer.allocateDirect`. Use a fixed `MaxDirectMemorySize` as the intended stopping budget and measure both pool allocations and the JVM direct-buffer pool. Large messages also consume heap during processing.

Arm H is a separately calibrated follow-up using small messages and a heap budget. Its deserialized object footprint requires its own measurements. It proceeds only if the batch time permits after Arm D's required controls and repeats.

First establish whether the unmodified victim can accumulate the required simultaneous backlog under the chosen load. Any reduction of `concurrent_writes`, including the original proposal of 2, is a disclosed supporting capacity change. The label “default capacities” applies specifically to Q/E/G and must be accompanied by a complete defaults audit.

The current campaign defers disk-to-memory causal-chain work. Use ordinary local storage and measure its behavior. Deliberately introducing disk pressure requires an explicit scope change. If disk behavior dominates the proposed mechanism, record that limitation before proceeding.

A bounded Byteman handler delay is an optional diagnostic condition if natural overlap is unreachable. Freeze its duration and injection point across matched arms, save the rule, and label all affected results as conditional on injected delay. Removing the delay supplies an additional control. Reproduction without the delay remains a separate reachability result and may be negative.

## 5. Calibration gates and budget selection

Complete these gates before freezing the main experiment.

1. Verify all instances are healthy, schema agreement holds, selected senders coordinate as intended, and the victim sees the expected data-bearing handlers. Quantify other connection traffic.
2. At N = 1 and 2, validate admission, endpoint borrowing, throttling and drain behavior with sufficient budget. These runs check the model and instrumentation.
3. At N = 4, demonstrate simultaneous occupancy and shared-reserve saturation. Use an initial tolerance of the larger of 5% of G or four maximum serialized messages, then freeze the justified tolerance before the sweep. Correlate saturation with admission failures or throttling. If four peers cannot fill the reserve, diagnose sender bounds and drainage. A higher reference N requires a dated amendment and a revised exclusive-growth range.
4. At sufficient diagnostic headroom, compare N = 4 and higher N. Measure memory distributions, baseline variance, queue occupancy, pool allocation, and drain behavior. Confirm that increasing N adds simultaneous exclusive occupancy while reserve occupancy remains comparable.
5. Choose a direct budget above the measured four-peer requirement, with a declared margin exceeding observed noise, and below the reproducible high-N requirement if such a window exists. Record the margin, uncertainty and chosen value. If the distributions overlap substantially, file the sensitivity limit or improve the design before an exhaustion sweep.
6. Freeze all budgets and settings. Choose cgroup `memory.max` from total process demand, including heap, direct buffers, other native allocations and charged file memory. Provide enough headroom for the intended JVM OOM to occur first. Use victim-only `memory.swap.max = 0` where supported.

Fresh JVM starts and matched warmup/data preparation are required because retained pool buffers can carry high-water allocations across sequential arms. Save baseline measurements for every run.

## 6. Experimental arms and causal controls

| Arm | Purpose | Fixed conditions and change |
|---|---|---|
| Idle and normal-drain controls | Quantify topology baseline and ordinary work | Fixed ring, warmup and data state, with the specified active sender set |
| N = 1 and 2 | Validate endpoint-limited borrowing | Q/E/G defaults, ample calibration budget |
| N = 4 reference | Establish survival with G saturated | Frozen experimental budget and workload |
| N = 8, 16, 32 | Search for multiplicity boundary | Same ring, RF, budget, capacities, payload and aggregate offered workload |
| Refined boundary | Identify nearest tested survivor and failure | Intermediate N inside the observed interval |
| Reduced-Q control | Test causal contribution of exclusive allowances | Same failing N, offered workload, E, G and budget, lower Q |
| Delay removed, if applicable | Test dependence on injected accumulation | Same N and settings, remove the diagnostic delay |

Predeclare the reduced-Q value after calibration. For example, Q = 1 MiB at N = 32 reduces exclusive allowance by 96 MiB while leaving shared borrowing available. Verify the new effective value and actual occupancy. Report useful throughput and rejection/timeout behavior, including whether the intervention merely prevents useful work.

The principal sweep holds aggregate offered workload fixed. If occupancy cannot be sustained at all N under that load, record the limitation and distinguish the reachability sweep from the matched comparison. Sender-count changes are performed through workload assignment while the ring remains healthy.

Repeat the failing condition and nearest tested surviving condition at least three times each from clean starts. If the survivor differs from N = 4, also retain a repeated four-peer reference. Repeat the reduced-Q control three times where a causal success is claimed. Report every outcome and peak distribution, including mixed outcomes.

## 7. Measurements and attribution

Synchronize clocks and use timestamped samples shorter than the growth window. Begin with 250 ms lightweight samples where practical, validate overhead, and adjust before freezing the design. Record lower-frequency expensive diagnostics separately.

- Per-handler queue size, connection type and peer identity. Virtual-table `using_bytes` aggregates handlers by peer, so validate the one-loaded-type assumption or add per-handler instrumentation.
- Per-endpoint reserve use and directly instrumented global reserve use. Account for temporary reservations and non-atomic observations when checking invariants.
- Simultaneous sums of queue occupancy, with exclusive and borrowed portions derived using the actual Q. Retain local enforcement and throttle evidence near failure.
- Networking pool allocated/used memory, JVM direct-buffer metrics, heap and GC, process RSS, cgroup memory statistics and OOM events.
- Sender pending bytes, overloads, expirations, actual coordinator use, offered/completed operations, latency, hints, topology events, and peer-host resource use.

Compare synchronized sums rather than adding independent per-peer peaks. Background urgent/small traffic, readback traffic and replica-response work must be quantified. If background growth explains the failure, attribution to the selected receive queues remains unresolved.

Enable native-memory tracking at startup if used. Forced GC, heap histograms and intrusive tracing belong in separate diagnostic runs or failure investigation when they alter the timing. Record pool retention after drain without treating retained buffers as an accumulating leak.

Preserve the initiating JVM error and allocation stack, subsequent shutdown messages, exit status and cgroup/kernel evidence. A direct-buffer OOM, heap OOM, cgroup kill, GC service loss and protective throttling each have separate outcome fields.

## 8. Decision rules

A supported C1 convergence result requires all of the following.

1. The reference survives at the frozen budget while G is demonstrably saturated.
2. Higher N produces increased simultaneous exclusive occupancy and corresponding physical memory growth, with comparable reserve use and accounted background work.
3. An actual OOM occurs reproducibly while local admission and reserve rules continue to hold within validated measurement tolerances.
4. The reduced-Q control reduces the predicted occupancy and memory and prevents failure under matched offered work, or the missing causal evidence is explicitly recorded.

A failure dominated by rising reserve use, altered replica fanout, a sender bottleneck, or unrelated allocations leaves the exclusive-allowance claim unresolved. A demonstrated local-contract violation requires analysis as a mixed convergence/bypass mechanism. Protective throttling or survival yields a result bounded by the tested N, workload and memory budget.

Injected-delay results establish a conditional mechanism. Deployment relevance requires a separately documented workload and budget assessment, including any successful reproduction without injection.

## 9. Time, stopping and recovery

Proposed execution budget is three hours after the cluster, build and instrumentation are ready, with up to 32 senders. Provisioning and readiness time is recorded separately. Each workload lifetime has a proposed five-minute cap after readiness, with an earlier stop at its terminal outcome or an invalidating condition. Freeze exact warmup and measurement windows during calibration.

Stop the batch when the boundary conditions, required repeats and causal control are complete, or when the time limit is reached. A first OOM ends that lifetime and triggers evidence preservation and recovery. Remaining planned controls and repetitions proceed within the batch limit. If the limit prevents completion, file the evidence and missing checks explicitly. Infeasible calibration, inadequate sender resources or overlapping memory distributions are reportable endpoints.

Use one measured victim at a time. Keep workload drivers and recovery control outside its cgroup. Size local data, logs and dump storage before execution. Clean up run-owned processes, aliases and temporary network changes, verifying recovery and process exit. Keep experiment builds and data on local storage.

## 10. Reviewable deliverables

Produce one default-capacity convergence case with the four sections required by the protocol, explicit supporting deviations, per-run settings, measurements, outcomes and limitations. Include executable harnesses, config diffs, instrumentation rules, source identity and small evidence excerpts. Record full-log locations and append index/batch-log entries when the investigation closes.

The reduced-Q control is explicitly custom-capacity. If Arm H proceeds, it receives its own calibration and results. This draft supplies the design for review. Node readiness, workload reachability, memory inflation and the failing boundary are open empirical questions.
