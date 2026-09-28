# max_hints_size_per_host — hint file on disk

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MAX_HINTS_SIZE_PER_HOST-SHOULDHINT-MAXHINTSSIZE |
| **Constraint** | `max_hints_size_per_host` — a **configuration entry** ([`Config.java:448`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L448), `volatile DataStorageSpec.LongBytesBound`, default **`0B`, which means disabled**). Present but commented out in the shipped [`conf/cassandra.yaml:111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L111). |
| **Enforcement pattern** | **(b)** — the comparison sets the return value of `shouldHint()`, which **seven separate decision points** read. |
| **Capacity check** | [`StorageProxy.shouldHint():2492`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2492) — `actualTotalHintsSize > maxHintsSize`, inside the enabling guard `if (maxHintsSize > 0)` at [`:2489`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2489). |
| **Decision point** | Primary: [`StorageProxy.sendToHintedReplicas():1552-1558`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1552-L1558) — `if (shouldHint(destination))` adds the replica to `endpointsToHint`, which is what `submitHint` is later called with at [`:1562-1563`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1562-L1563). Six further decision points read the same verdict — see §5. |
| **Allocation site** | [`StorageProxy.submitHint():2811`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2811) — `HintsService.instance.write(hostIds, Hint.create(mutation, creationTime))` → [`HintsService.write():161-172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L161-L172) → `bufferPool.write(hostIds, hint)`, which lands the hint in an off-heap buffer and ultimately in a hint file on disk. |
| **Related cases** | [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md`](MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md) — the same subsystem, the other resource. That case bounds the **off-heap buffers** hints pass through; this one bounds the **files they land in**. Neither subsumes the other; see §11. |

```java
// StorageProxy.shouldHint():2488-2500 — the capacity check.
// Note :2489: the whole check is skipped unless the operator has enabled it.
long maxHintsSize = DatabaseDescriptor.getMaxHintsSizePerHost();
if (maxHintsSize > 0)                                              // <-- enabling guard, default 0 = off
{
    long actualTotalHintsSize = HintsService.instance.getTotalHintsSize(hostIdForEndpoint);
    if (actualTotalHintsSize > maxHintsSize)                       // <-- capacity check, :2492
    {
        Tracing.trace("Not hinting {} which has reached to the max hints size {} bytes on disk. The actual hints size on disk: {}",
                      endpoint, maxHintsSize, actualTotalHintsSize);
        return false;                                              // <-- the verdict
    }
}

return true;
```

```java
// StorageProxy.sendToHintedReplicas():1548-1563 — the primary decision point.
else
{
    //Immediately mark the response as expired since the request will not be sent
    responseHandler.expired();
    if (shouldHint(destination))                                   // <-- reads the verdict, :1552
    {
        if (endpointsToHint == null)
            endpointsToHint = new ArrayList<>();

        endpointsToHint.add(destination);                          // ALLOW: queued for hinting
    }
    // DISALLOW: falls through — the replica is simply never added, and no hint is created
}

if (endpointsToHint != null && requestTime.shouldSendHints())
    submitHint(mutation, EndpointsForToken.copyOf(mutation.key().getToken(), endpointsToHint), responseHandler);
```

## 2. Context

When a Cassandra node cannot deliver a write to one of its replicas — because
that replica is down, overloaded, or simply not answering — it does not throw
the write away. It stores a small record of the missed write locally, called a
hint, and replays it once the replica comes back. Hints are what make a brief
outage invisible to the cluster.

The cost is that hints accumulate on the disk of whichever node is still up,
and they accumulate fastest exactly when things are going worst. A replica
that stays down under heavy write load can cause the surviving nodes to fill
their own disks with hints for it, turning one node's outage into several.
Cassandra's older defence against this is a *time* limit: stop hinting a node
that has been down longer than a set window. This check is the *size* limit
that complements it — before creating a hint for a given destination, it adds
up the bytes of hint files already on disk for that destination and refuses to
create another if the total is over a configured ceiling. The write itself is
unaffected; only the hint is skipped, which means the missed data is
permanently lost for that replica and a repair will be needed to restore it.

The limit is **off by default**, so out of the box a node's hint directory is
bounded only by the time window and the disk.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | `hints` — hinted handoff: writes stashed for temporarily-unreachable replicas (`hints/`, with the decision in `service/StorageProxy`) |
| **One-line role** | When a replica cannot be written to, the coordinator records the mutation as a hint and replays it on recovery; `HintsService` owns the buffers, files and dispatch, while `StorageProxy` decides whether a hint should be created at all. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | **Yes** — a running total of on-disk bytes for one destination host, compared against a configured byte ceiling, gating whether more bytes are written for that host. |
| **Usage-side operand** | `actualTotalHintsSize` — [`HintsService.getTotalHintsSize(hostId):253-259`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L253-L259) → [`HintsStore.getTotalFileSize():260-271`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsStore.java#L260-L271). **Real file sizes, summed live**: every descriptor in `dispatchDequeue` plus `corruptedFiles`, plus the file the current `HintsWriter` is appending to. Not an estimate and not a counter — it stats the files. |
| **Limit-side operand** | `maxHintsSize` — the local read of `DatabaseDescriptor.getMaxHintsSizePerHost()` at [`:2488`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2488). |
| **Limit type** | **Configuration entry**, used raw (bytes). |

**Limit initialization path.**

1. [`Config.max_hints_size_per_host:448`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L448) — declared, `volatile DataStorageSpec.LongBytesBound`, default `"0B"`, with the in-place comment `// 0 means disabled`.
2. [`DatabaseDescriptor.getMaxHintsSizePerHost():3601-3604`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3601-L3604) — `conf.max_hints_size_per_host.toBytes()`.
3. Read **live at every call** into the local `maxHintsSize` at [`StorageProxy.java:2488`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2488). There is no cached copy and no `final` field: because the `Config` field is `volatile` and re-read per call, a change through JMX takes effect on the very next hint decision.

**Hot-settable through JMX**, unusually for this folder:
[`StorageProxyMBean.setMaxHintsSizePerHostInMiB(int)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L36)
→ [`DatabaseDescriptor.java:3590-3593`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3590-L3593).
**No `nodetool` subcommand exists** — `tools/nodetool/` has
`SetMaxHintWindow` (the *time* limit) but nothing for the size limit, so a
JMX client is required. Note the setter's unit is **MiB** while the config and
the check are in **bytes**.

**The limit's default disables the check.** `0B` fails the `> 0` guard at
`:2489`, so on an unconfigured node the comparison at `:2492` never executes.
This is not an escape hatch bolted on elsewhere — it is the shipped default,
and §8 and §10 treat it accordingly.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`StorageProxy.sendToHintedReplicas():1552-1558`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1552-L1558) (primary) |
| **Verdict** | Pattern (b): the **boolean return of `shouldHint()`**. Set by `return false` at [`:2496`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2496), or `return true` at [`:2500`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2500). The two-argument overload at [`:2442`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2442) carries the logic; the one-argument form at [`:2423-2425`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2423-L2425) delegates to it. |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `actualTotalHintsSize <= maxHintsSize`, or the check is disabled (`maxHintsSize <= 0`) | `shouldHint()` returns `true`; the replica is added to `endpointsToHint` and `submitHint()` creates and writes the hint. |
| **Disallow** | `actualTotalHintsSize > maxHintsSize` | `shouldHint()` returns `false`; the replica is **never added**, so no `Hint` is created and no bytes are written. The mutation is **not** retried, deferred or queued — the hint is silently skipped and that replica's copy of the write is permanently missing until a repair. |

```java
// allow: the replica is queued, and submitHint() later creates the hint
if (endpointsToHint == null)
    endpointsToHint = new ArrayList<>();
endpointsToHint.add(destination);
```

```java
// disallow: the verdict is a bare `false` — there is no else branch at any
// decision point; the replica is simply omitted.
Tracing.trace("Not hinting {} which has reached to the max hints size {} bytes on disk. ...", ...);
return false;
```

### One verdict, seven decision points

Unusually for a pattern-(b) case, the verdict is not read in one place. Every
caller of `shouldHint()` is a decision point, and they do not all gate the same
allocation:

| Decision point | What the verdict decides |
|---|---|
| [`StorageProxy.sendToHintedReplicas():1552`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1552) | **Primary** — whether an unreachable replica is queued for hinting on the normal write path. |
| [`StorageProxy:818`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L818) | Whether to hint on the batchlog/`allowHints` path. |
| [`StorageProxy:986`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L986) | Filters a replica stream by hintability. |
| [`StorageProxy:1593`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1593) | Conjunct of the in-flight-hints overload check (itself refused — see `rejected.md`). |
| [`AbstractWriteResponseHandler:309`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java#L309) | Whether to hint on a failed write response. |
| [`PaxosCommit:230`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/paxos/PaxosCommit.java#L230) | Whether to hint a failed Paxos commit. |
| [`HintsService:198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L198) | Passes `tryEnablePersistentWindow = false`; used when deciding transfer/dispatch eligibility. |

Rule 3 is satisfied at all of them in the same way — the `true` branch leads to
hint creation, the `false` branch omits the replica — but the **count of
decision points is the point**: one config value suppresses hint creation
across every path that can produce one, which is why §8's bound is per host
rather than per code path.

## 6. Code path

### 6a. Allow path → object creation

1. [`StorageProxy.sendToHintedReplicas():1551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1551) — the destination is unreachable; `responseHandler.expired()`.
2. [`:1552`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1552) — `shouldHint(destination)` returns `true` (the size check passed, or is disabled).
3. [`:1554-1557`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1554-L1557) — the replica is added to `endpointsToHint`.
4. [`:1562-1563`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1562-L1563) — `submitHint(mutation, EndpointsForToken.copyOf(...), responseHandler)`.
5. [`submitHint():2790-2802`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2790-L2802) — resolves each target to a host id inside a `HintRunnable`.
6. [`:2811`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2811) — **object creation**: `Hint.create(mutation, creationTime)` and `HintsService.instance.write(hostIds, hint)`.
7. [`HintsService.write():161-172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L161-L172) — `catalog.maybeLoadStores(hostIds)`, then `bufferPool.write(hostIds, hint)`; `StorageMetrics.totalHints` is incremented.
8. The buffer is later flushed by `HintsWriteExecutor` into a hint file under the hints directory — **the on-disk bytes this case bounds**, and exactly what `getTotalFileSize()` measures on the next call.
9. [`:2812`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2812) — `incrCreatedHints` per target, which is the `Hints_created-<addr>` counter.

### 6b. Disallow path effect

**A clean, silent skip — and the data is lost, not deferred.**

1. [`shouldHint():2492-2497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2492-L2497) — `Tracing.trace(...)` then `return false`. No exception, no counter, no log at any normal level.
2. At the decision point the replica is simply **not added** to `endpointsToHint`. If it was the only unreachable replica, `endpointsToHint` stays `null` and `submitHint` is never called at all.
3. **Nothing is retried or queued.** Unlike the memtable and internode cases, which park the caller, and unlike `cdc_total_space`, which throws a `CDCWriteException` the client sees, this branch is invisible to the writer: the write succeeds at whatever consistency level it satisfied with the reachable replicas, and the hint for the skipped replica is never created. That replica's copy of the mutation is permanently absent until an anti-entropy repair.
4. **The bound is therefore self-enforcing but lossy.** Once a host's hint files exceed the ceiling, no further hints for it are created, so its total stops growing — but the cost is paid in consistency, not in backpressure.

**No metric fires on this path, and that is the case's main instrumentation
problem.** The neighbouring *time*-window rejection at
[`:2482-2485`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2482-L2485)
calls `HintsService.instance.metrics.incrPastWindow(endpoint)`, which marks the
`Hints_not_stored-<addr>` counter
([`HintedHandoffMetrics.java:63-66, 93`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/HintedHandoffMetrics.java#L63-L66)).
**The size rejection has no equivalent.** A hint dropped for exceeding
`max_hints_size_per_host` increments nothing and is visible only through
request tracing, or inferentially as `Hints_created-<addr>` going flat. §9
works around this; it is also a reasonable upstream bug report.

**No escape hatch, and none needed** — the check is disabled by default
(§4). There is no flag that bypasses it once enabled.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `Hint` ([`Hint.create(mutation, creationTime)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2811)), serialized into a `HintsBuffer` and ultimately appended to a hint file for the destination host. |
| **Resource consumed** | **On-disk bytes** — the hint files under the hints directory, one set per destination host id. Secondarily off-heap bytes while the hint sits in a `HintsBuffer`, but that is the sibling case's resource, not this one's. |
| **Rough sizing** | Per hint, the serialized mutation plus hint overhead — so it scales with the write's payload, not a fixed struct. The *gated* quantity is the running total `getTotalFileSize()`, which is measured rather than derived. |
| **Lifetime / release** | A hint file is released when its hints are dispatched to the recovered replica and the file is deleted, or when the hint TTL expires, or on an operator `nodetool truncatehints`. Because `getTotalFileSize()` stats live files, deletion lowers the operand immediately and hinting for that host resumes on the next call. |

## 8. Maximum disk bound

`max_hints_size_per_host` caps the on-disk hint bytes held **for one
destination host**, and the mechanism is refusal to create more:

- **Per host.** Once `getTotalFileSize(hostId)` exceeds the ceiling, every path that could create a hint for that host stops doing so (§5's seven decision points), so the host's hint files stop growing. The bound is not byte-exact: the comparison is `>` against the total *before* the new hint, so the last admitted hint can carry the total past the ceiling by one hint's worth.
- **Node-wide, multiply by hosts.** There is no global hint-size limit in this check. A node hinting `H` unreachable hosts can hold up to `H × max_hints_size_per_host` bytes plus overshoot. **The config name says "per host" and means it** — an operator sizing a hints partition must multiply by the number of peers that could plausibly be down at once, which in a large cluster is not a small number.
- **Raising it** lets each host's backlog grow proportionally before hints start being dropped, trading disk for a smaller repair surface. **Lowering it** caps disk sooner at the cost of losing more writes to the down replica.
- **At the default it bounds nothing.** `0B` disables the check (§4), leaving the hint directory bounded only by `max_hint_window_in_ms` and the device. This is the single most important thing to know about the constraint, and it distinguishes this case from the sibling `MAX_HINT_BUFFERS`, whose cap of 3 is always in force.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** Method and pitfalls:
[README.md §8](../../README.md#8-designing-a-test-for-a-case). Where stage 4's
numbers go: [`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).

**Two jobs, as with the compaction guard.** (1) Confirm the constraint enforces
when enabled, by sweeping it. (2) Confirm it does **nothing** at the shipped
default of `0B`, which is the Target-3-relevant result. A run that only does
(1) overstates what an out-of-the-box node is protected by.

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable and hot-settable** — the best combination in this folder. The `Config` field is `volatile` and re-read at every call, so a JMX change takes effect on the next hint decision with no restart, and the sweep can run within a single cluster lifetime. |
| **Constraint knob** | `max_hints_size_per_host` in `cassandra.yaml` (commented out at [line 111](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L111); uncomment and set). At runtime: JMX [`StorageProxyMBean.setMaxHintsSizePerHostInMiB(int)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L36) — **note the unit is MiB**, while the config and the comparison are bytes. **No `nodetool` subcommand**; use a JMX client. |
| **Capacity values to test** | `max_hints_size_per_host` ∈ {**`0B`** (default, = disabled), `16MiB`, `64MiB`, `256MiB`}. The `0B` arm is not a zero-capacity arm — it is the *disabled* arm, and must be read as a separate condition, not as the bottom of the curve. Values are per host, so with one down replica they are also the node total. |
| **Usage-side observable** | `getTotalFileSize(hostId)` — the summed size of that host's hint files. |
| **Instrument** | **The operand is a set of files, so measure it directly**: `du -sb` on the hints directory, and per-host by hint-file name (`HintsDescriptor` encodes the host id in the filename). This is not a proxy — it is what the check itself stats. For the *disallow* signal, note §6b: **there is no metric.** Use instead (1) `Hints_created-<addr>` ([`HintedHandoffMetrics.java:51-53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/HintedHandoffMetrics.java#L51-L53)) **going flat while writes continue** — the clearest available evidence; (2) request tracing, which carries the `Tracing.trace` line at [`:2494-2495`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2494-L2495) naming both operands; (3) `StorageMetrics.TotalHints` ([`StorageMetrics.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/StorageMetrics.java#L46)) as the node-wide counterpart. **Do not use `Hints_not_stored-<addr>`** — it is marked only by the *time-window* rejection, never by this one, and would read as zero throughout a successful run. |
| **Scope of the limit** | **Per destination host.** `N` = the number of simultaneously unreachable hosts being hinted, and node-wide hint bytes go as `N × limit`. **Run the sweep at `N = 1` first** (one down replica) so the per-host figure and the directory total coincide, then a second arm at `N = 2` or `3` to confirm §8's multiplier — which is the part an operator is most likely to get wrong. |
| **Suggested level** | **Cluster only, realistically.** The check needs a real down replica, a real host id and real hint files on disk, so the unit tier has little to offer: `test/unit/org/apache/cassandra/hints/` has `HintsCatalogTest`, `HintsStoreTest` and `HintsBufferPoolTest` covering the store and buffers, but nothing exercises `StorageProxy.shouldHint()`. A focused unit test asserting `getTotalFileSize()` against files written by `HintsStore` would be worth having as an arithmetic check on the operand, and is cheap. |

### 9a. Workload — driving the usage operand

Hints accumulate only while a replica is unreachable, so the workload has a
prerequisite the other cases do not.

- **Three-node cluster**, keyspace at `RF = 3`, one table. Node 1 is the coordinator and the node under test.
- **Stop node 3.** Leave node 2 up so writes still satisfy a quorum.
- Write from node 1 at `CONSISTENCY QUORUM` with `cassandra-stress` or a CQL client, so writes succeed while hints accumulate for node 3.
- **Set `max_hint_window_in_ms` large** (hours) so the *time* limit does not fire first and mask the size limit — see §9g; the two rejections are adjacent in the same method and are easily confused.
- Payload should be large enough that hint files grow to the smallest tested ceiling (16MiB) within a minute or two, so a sweep is practical.

**Deterministic single-shot form:** enable the check at a small value
(`1MiB`), write enough to exceed it, then keep writing. The transition from
"hints created" to "hints silently skipped" should be a step at a known
directory size — and because the knob is hot-settable, the whole sweep can be
done by changing it over JMX between write bursts without restarting anything.

### 9b. Scenario A — just reach capacity

With the check enabled, write until the hint directory for node 3 sits just
below the ceiling, then stop.

Expect: `du -sb` on node 3's hint files ≈ but below `max_hints_size_per_host`;
`Hints_created-<node3>` rising throughout; no tracing line about max hints
size. The plateau should move with the knob across 16 / 64 / 256 MiB. This arm
establishes that the knob moves the ceiling at all.

### 9c. Scenario B — try to exceed capacity

Keep writing past the ceiling. **Nothing fails and nothing blocks** (§6b):

| Expected | Evidence |
|---|---|
| Hint file total for node 3 **plateaus** at the ceiling (plus at most one hint of overshoot) | `du -sb` per host flat while writes continue. |
| `Hints_created-<node3>` **stops rising** while client writes keep succeeding | The primary available evidence, since no rejection counter exists. |
| The tracing line at `:2494` appears on traced writes, naming both operands | Enable tracing on a sample of writes — this is the only direct statement that *this* check fired. |
| **Client writes continue to succeed**, at whatever CL the reachable replicas satisfy | Distinguishes this case from `cdc_total_space`, whose disallow the client sees as an exception. |
| On restarting node 3, replay covers only the hints that were stored; the rest are **permanently missing** until a repair | Read back at `CONSISTENCY ALL` after replay, or compare row counts. Worth measuring: it quantifies the consistency cost of the bound. |

### 9d. Expected dose-response

If the traced path is the binding limit:

- **Per-host hint bytes plateau linearly in `max_hints_size_per_host`** across 16 / 64 / 256 MiB, landing at or just above the configured value. The overshoot should be bounded by one hint's serialized size — worth confirming, since §8 claims exactly that.
- **`Hints_created-<addr>` flattens earlier as the ceiling falls**, at constant write rate; the count of hints stored before flattening should scale with the ceiling.
- **At `0B` (default) there is no plateau at all.** Hint bytes grow until the time window or the disk stops them. This is a *different curve shape*, not a low point on the same curve, and it is the arm that matters most.
- **At `N = 2` down hosts**, total hint-directory size should plateau at roughly `2 ×` the per-host ceiling, confirming §8's multiplier. If it plateaus at `1 ×`, the limit is global and §8 is wrong.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| Per-host hint bytes plateau at the ceiling; `Hints_created` flattens; writes keep succeeding | The check enforces as traced. |
| Hint bytes keep growing past the ceiling | Either the check is disabled (confirm the knob actually took — the MiB/bytes unit mismatch in the setter is the likeliest cause), or `getTotalFileSize()` is not seeing files it should. The latter would be a real finding: the operand stats `dispatchDequeue`, `corruptedFiles` and the current writer, so a file in none of those is invisible to the check. |
| Directory total plateaus at `1 ×` the ceiling with two hosts down | The bound is global, not per host. §8's multiplier claim is wrong and the config name is misleading — Target-3 material. |
| Nothing plateaus and `Hints_created` never flattens, but hints *are* being written | The time window fired first, or the check was never enabled. Check `max_hint_window_in_ms` and `Hints_not_stored-<addr>` before concluding — a non-zero `Hints_not_stored` means the *other* rejection is what you measured. |
| At `0B`, hint bytes plateau anyway | Something else bounds them. Find it: that would mean the default is not as unprotected as §8 claims. |

### 9f. What would refute this case

The case claims the comparison at `shouldHint():2492` gates hint creation, so
on-disk hint bytes per destination host are bounded by
`max_hints_size_per_host` when it is set above zero. It is refuted if, with
the check demonstrably enabled and a single host down, that host's hint files
grow materially past the configured ceiling while writes continue.

**The `0B` arm cannot refute the case** — §4 and §8 already state that the
default disables the check, so a run at the default showing unbounded growth
is a confirmation of the case's most important claim, not a contradiction of
it. Stage 4 should report it as such.

A separate claim worth refuting on its own: §8 says the bound is per host and
node-wide usage goes as `N × limit`. A two-host arm settles it, and a negative
result there changes §8 without touching §5 or §6.

### 9g. Confounders and controls

- **The hint *time* window is the dominant confounder**, and it lives four lines above this check in the same method. If `max_hint_window_in_ms` expires first, hints stop for a completely different reason and the directory plateaus anyway. Set it large, and watch `Hints_not_stored-<addr>` — **any** non-zero value there means the time-window rejection fired and the arm is contaminated.
- **Hint dispatch lowers the operand.** `getTotalFileSize()` stats live files, so as soon as node 3 returns, files are dispatched and deleted and the total collapses. Keep node 3 down for the entire measurement, and do not let it be restarted between arms without re-establishing the baseline.
- **The MiB/bytes unit mismatch** in `setMaxHintsSizePerHostInMiB` is an easy way to set a value 2²⁰ times larger than intended. Read the value back through the MBean getter and confirm against `du` scale before trusting an arm.
- **Other down hosts** contribute their own hint files to the same directory. Keep exactly one host down in the primary arms, and per-host-file accounting (not `du` on the whole directory) in the multi-host arm.
- **`max_hints_delivery_threads` and throttling** affect how fast files drain, not the ceiling — but they do affect how quickly the operand recovers after a restart.
- **Baseline** at `0B` (default) with the same workload, to establish the unbounded growth curve; **idle control** with all three nodes up so no hints are generated, to confirm the directory stays empty.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — from [`../stage2-ai-preprocessing/bands.md`](../../stage2-ai-preprocessing/bands.md)'s **band A1** list, row `StorageProxy.java:2492#1` ("total hints size on disk against the configured per-host maximum, dropping the hint"). Judged in the band-A1 pass on 2026-09-28 and recorded in `pending.md`; written up 2026-09-28. |
| **Filed by / Date** | Claude (`claude-opus-5`) session, 2026-09-28 |
| **Line numbers checked** | 2026-09-28 against the local `cassandra-5.0.9` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). |
| **Escape hatch / Target-3 note** | **The default is the gap.** `max_hints_size_per_host` defaults to `0B`, and `if (maxHintsSize > 0)` at [`:2489`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2489) skips the comparison entirely — so on an unconfigured node this constraint does not exist. That is a stronger default-mode gap than the `native_transport_throw_on_overload` case (where the check runs and is then ignored) and comparable to the compaction guard's non-domination (where the check is never reached), but arrived at a third way: the operator simply has not switched it on. Two further Target-3 observations: the bound is **per host**, so `N` down hosts multiply it, and the disallow path is **silent** — no counter, no log — which makes the resulting data loss hard to detect operationally. |
| **Stage-4 feedback** | none yet |
| **Notes** | `getTotalFileSize()` sums `dispatchDequeue`, `corruptedFiles` and the current writer's file. A hint file in none of those three would be invisible to the check; whether such a state is reachable was not established here and is left as an open question for §9e's second row. |

---

## 11. Notes

- **Why this is a separate case from `MAX_HINT_BUFFERS`.** Both are in the
  hints subsystem and both bound hint accumulation, so the overlap is worth
  stating:

  | | This case | `MAX_HINT_BUFFERS` |
  |---|---|---|
  | Resource | **on-disk bytes** — hint files | **off-heap bytes** — `HintsBuffer`s |
  | Limit | `max_hints_size_per_host`, config, **disabled by default** | `cassandra.MAX_HINT_BUFFERS`, JVM property, default 3, **always in force** |
  | Scope | per destination host | node-wide, one pool |
  | Usage operand | live file sizes, stat'd | a count of buffers ever created |
  | Disallow | silently skip the hint — **data loss** | block the writer until a buffer recycles — **backpressure** |
  | Pattern | (b) | (a) |

  They sit at opposite ends of the same pipeline: `MAX_HINT_BUFFERS` throttles
  hints on the way into memory, this one refuses them on the way onto disk.

- **First case whose disallow branch loses data.** Every other filed case
  parks the caller, throws an error the client sees, or switches
  representation. Here the write succeeds, the client is told nothing, and a
  replica is left permanently short of a mutation until repair. Worth
  remembering when judging other `shouldHint`-shaped verdicts: a "clean
  reject" is not always cheap.

- **The missing counter is a real gap.** The time-window rejection four lines
  above increments `Hints_not_stored-<addr>`; this one increments nothing.
  §9's instrument section works around it, but it is worth reporting upstream
  — an operator who enables this limit has no way to see it firing.

- **Seven decision points, one verdict.** This is the first case where the
  pattern-(b) verdict is consumed in more than one place. The rule that Rule 3
  must be traced "to whoever reads it" meant seven reads here rather than one.
  Recorded in §5 in full, since a later pass touching `shouldHint()` will
  otherwise have to re-derive the list.
