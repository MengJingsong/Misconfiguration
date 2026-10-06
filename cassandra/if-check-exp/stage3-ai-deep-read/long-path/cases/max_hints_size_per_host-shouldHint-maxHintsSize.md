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

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test sets `max_hints_size_per_host` over JMX, writes through a coordinator
while one replica is down, and checks that the down host's hint files stop
growing near the ceiling while client writes keep succeeding, and that at the
shipped default (`0B`) nothing stops them. **Run so far:** none. Converted to this
layout 2026-10-06.

### 9a. Procedure and conclusions

**Testability:** config, **live-settable** — the `Config` field is read at every
call, so a JMX change (`StorageProxy` MBean `MaxHintsSizePerHostInMiB`, **in MiB**
while the comparison is in bytes) takes effect on the next hint decision with no
restart; one cluster lifetime can run the whole sweep. There is no `nodetool`
subcommand.

**Two jobs.** (1) With the check enabled, confirm it bounds the hint files and what
the disallow does. (2) At the shipped default `0B` the guard `maxHintsSize > 0`
skips the comparison, so confirm that **nothing** bounds the files then. The second
is the Target-3-relevant result; a run that only does (1) overstates what an
out-of-the-box node is protected by.

**Claim under test:** `max_hints_size_per_host`, when above zero, stops new hints for
a destination host once the host's hint files on disk exceed it
(`StorageProxy.shouldHint():2488-2497`). The disallow returns `false` to every caller
(§5): no hint is stored, the client write still succeeds, no metric fires, and the
host stays short of the mutation until a repair. The bound is per host, so
node-wide hint bytes are at most `N × limit` for *N* down hosts, plus an overshoot
(below).

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** with the limit set, a down host's hint files stop growing just past
  it and no new hint is made for that host; with the limit at `0B` they keep growing.
- **Test:** vary the limit (16, 64, 256 MiB, then `0B`) over JMX on one coordinator
  with one replica down, at a steady write rate, reading the host's hint-file bytes
  (`du`, per host), `Hints_created`, the direct decision trace of `shouldHint`, and the
  client's write results; then repeat at the default with two hosts down.
- **Logic:** (1) at each value the files must reach the limit, or the run is invalid.
  (2) The files stop growing within the stated overshoot, and `Hints_created` goes
  flat: usage **stops at the limit**. (3) The plateau moves with the limit: usage
  **follows the constraint**. (4) The decision trace shows `shouldHint` returning
  `false` with the files above the limit, and no other reason (the time window
  contributes nothing): the **disallow branch** is what stops it. (5) Client writes
  still succeed; after the host returns, only the stored hints replay, so the rest is
  missing. (6) At `0B` there is no plateau; with two hosts down the total is about
  twice one host's.
- **Refuted if:** the files keep growing past the limit plus the overshoot with the
  check enabled; or the plateau does not move with the limit; or it is global rather
  than per host (rows of the Conclusions table). The `0B` arm cannot refute the case:
  unbounded growth there is its default-mode finding.

**Procedure:**

1. **Unit tier** — (a) run upstream `StorageProxyTest` (`testShouldHint`,
   `testShouldHintOnExceedingSize`: the operand is replaced by a Byteman stub there).
   (b) Run the harness test `ShouldHintSizeTest` (9c): the same `shouldHint` with the
   **real** operand, `HintsService.getTotalHintsSize`, over hint files written through
   `HintsService`, at the boundary, and at `0`.
2. **Cluster tier** — three nodes; node 1 coordinates and is under test; stop node 3
   (and node 2 in the two-host arm). One run per limit value, changed by JMX between
   bursts.
3. **At each value:** idle control → **A**, write until the host's files sit just below the
   limit → **B**, keep writing past it. No scenario C: no bypass is recorded.
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *L* = the limit in bytes; `T` = `HintsStore.getTotalFileSize` of the
host (the check's operand: the sizes of its hint files, the current writer's included,
as of each flush); `r` = bytes of hints accepted per second; *F* = `hints_flush_period`
(1 s here); *H* = the size of one hint (about 5 KiB).

- **A:** `T` rises toward *L*; `Hints_created` rises; every `shouldHint` returns `true`.
- **B:** once `T > L` the decision flips and stays `false`; `Hints_created` and
  `TotalHints` go flat while client writes keep succeeding. Hints already accepted
  into the in-memory buffers still reach the file when flushed, so the on-disk total
  rises past *L* by at most what was accepted since the last flush that left `T ≤ L`:
  **overshoot ≤ `r × F + H`**, with `r ≈ 1 MiB/s` the figure is at most about
  1 MiB (6 % of 16 MiB, under 0.5 % of 256 MiB). (§8 states the overshoot as one
  hint; the per-flush bound is the one the source gives, since the operand moves only
  when a flush closes its session, `HintsWriter.java:274`. The test reports the
  measured overshoot against both.)
- **Second knob, hosts:** with two hosts down, each host's files plateau at about *L*,
  so the directory total is about `2 × L`.
- **At `0B`:** no plateau; the files grow at `r` until the hint window (set above the
  run), the file-size roll (`max_hints_file_size`, 128 MiB, which starts a new file but
  does not stop growth) or the disk stops them.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Each enabled value: the host's files plateau within `L + r × F + H`, the trace shows `false` returns with `T > L`, `Hints_created` flat, writes succeeding; the plateau follows *L* across 16/64/256 MiB; at `0B` no plateau; with two hosts down the total is about `2 × L` | **Confirmed** — the check enforces as traced; at the default it bounds nothing. |
| As above, but the plateau is at `1 ×` *L* with two hosts down | **Confirmed per host; §8's multiplier refuted** — the bound is global; the config name misleads (Target-3 material). |
| Files grow past `L + r × F + H` with the check enabled and `false` returns in the trace | **Refuted** — the check does not stop hint creation, or `T` misses files (the operand covers `dispatchDequeue`, `corruptedFiles` and the current writer only). |
| Files grow past *L* and the trace shows `true` returns with `T > L` | **Invalid run** — the knob did not take (the MiB/bytes unit): read it back (9b) and re-run. |
| The plateau does not move with *L* while the trace shows `false` returns | **Refuted** — not the binding limit. Re-read, do not re-run. |
| At `0B` the files plateau anyway | **Not confirmed** (for the default-mode claim) — something else bounds them; find it (the time window and `Hints_not_stored` first). |
| Writes fail or block at the plateau | **Not confirmed** — §6b's silent skip is not shown; read the error. |
| After the host returns, replay delivers more than was stored, or all of it | **Not confirmed** for the loss claim — read the repair/replay path before concluding. |
| The files never reach *L* (rate too low for the run's length) | **Invalid run** — raise the rate or lower *L* (9c) and re-run. |
| `Hints_not_stored-<addr>` is non-zero | **Invalid run** — the time-window rejection fired; the arm measured the other rejection. |

**Why the decision trace and not only `Hints_created`:** a flat `Hints_created` also
happens when the host is not in the ring or the window expired; only the trace line
naming `T`, *L* and the return value ties it to this comparison.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `max_hints_size_per_host` in `cassandra.yaml` (commented out at [`conf/cassandra.yaml:111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L111); the default is `0B`). Live: `bin/nodetool sjk mx -ms -b 'org.apache.cassandra.db:type=StorageProxy' -f MaxHintsSizePerHostInMiB -v <MiB>` (`StorageProxyMBean.setMaxHintsSizePerHostInMiB(int)`, [`:36`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L36)); **MiB, not bytes**. Unit tier: `DatabaseDescriptor.setMaxHintsSizePerHostInMiB(int)`. |
| **Confirm it took effect** | `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.db:type=StorageProxy' -f MaxHintsSizePerHostInMiB` after every change; the decision trace's `limit=` field (9d) is the value the check used, in bytes: it must equal the MiB value × 1,048,576. |
| **Capacity values** | `16`, `64`, `256` (MiB), and `0` (the default, disabled): a separate arm, not the bottom of the curve. |
| **Scope** | **Per destination host.** *N* = hosts down: 1 for the sweep; 2 in the two-host arm, at one value (64 MiB) and at `0`. The check compares one host's `getTotalFileSize` ([`HintsStore.java:260-271`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsStore.java#L260-L271)); a file in none of `dispatchDequeue`, `corruptedFiles` or the current writer is invisible to it. |
| **Level** | Both. Unit: upstream `StorageProxyTest` and the harness `ShouldHintSizeTest`; `HintsCatalogTest`/`HintsStoreTest` cover the store. Cluster: the real down replica, host id and files. |

**Cluster layout.** Three nodes: separate processes on loopback addresses, or the
CloudLab nodes of [`environment.md`](../../../stage4-runtime-verification/environment.md) §5.
Keyspace `SimpleStrategy`, `replication_factor` 3, one table. Node 1 is the coordinator
and the node under test; write only through node 1.

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `max_hint_window` | `24h` | The time rejection sits four lines above this check in the same method ([`StorageProxy.java:2461-2477`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2461-L2477)); a window that expires first stops hints for another reason. Record when each node was stopped. |
| `hints_flush_period` | `1000ms` | Bounds how long accepted hints sit in the buffer, hence the overshoot (default `10s`, [`Config.java:445`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L445)). |
| `max_hints_file_size` | `128MiB` (default) | Rolling a file does not stop growth; record the number of files. |
| `hinted_handoff_enabled` | `true` (default) | With it off, no hint is written. |
| Consistency level | `ONE` (writes), `ALL` (read-back) | Writes succeed with the live replicas while hints accumulate. |
| Hint, data and log directories | local disk, never `/proj` | The `0B` arm writes GBs; see the stage-4 README's safety rules. |
| Client load | same rate at every value | `r` enters the prediction. |

**Controls:**

- **Idle run** — all three nodes up, writes at the same rate: the hints directory stays empty, `Hints_created` flat.
- **Default arm** — the same load at `0` (arm after the sweep).
- **Window-contamination check** — `Hints_not_stored-<addr>` read at the end of every arm; any non-zero value voids it.

**Reset between runs:** with node 3 (and 2) still down, a changed value needs no reset. To start a fresh sweep, stop all nodes, empty the hints directory of node 1, restart all, stop node 3 and wait for `DN`. **Never restart the down host between arms:** its return dispatches and deletes the hint files and the operand collapses.

### 9c. Workload

Hints accumulate only while a replica is down, so the cluster tier starts with node
3 stopped (and node 2 in the two-host arm), waiting until node 1 shows `DN`.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/max_hints_size_per_host-shouldHint-maxHintsSize`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `ShouldHintSizeTest.java` | Unit tier. Package `org.apache.cassandra.service`; modelled on `StorageProxyTest.shouldHintTest` (a fake endpoint with a host id, marked dead). Writes real hints through `HintsService.instance.write(hostId, hint)` and flushes with `flushAndFsyncBlockingly`. See 9e. |
| `should-hint.btm` | Byteman, observation only: one line at the exit of `StorageProxy.shouldHint(Replica, boolean)`: `shouldHint endpoint=<ep> result=<bool> total=<getTotalHintsSize> limit=<getMaxHintsSizePerHost> ms=<epoch millis>`. |
| `hints-du.sh` | Prints, per host id, the sum of `stat -c %s` of `data/hints/<hostid>-*.hints`, the file count, and a timestamp; run every second. |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.service.StorageProxyTest
cp <harness>/ShouldHintSizeTest.java test/unit/org/apache/cassandra/service/
ant testsome -Dtest.name=org.apache.cassandra.service.ShouldHintSizeTest

# cluster tier, once: schema (all nodes up)
bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 3};"
tools/bin/cassandra-stress write n=1000 no-warmup -node 127.0.0.1
# node 3 stopped and shown DN; then, per value (set the limit first, over JMX), a throttled stream through node 1 only:
tools/bin/cassandra-stress write n=<rows> no-warmup cl=ONE -col 'size=FIXED(1024)' -rate threads=8 throttle=200/s -node whitelist 127.0.0.1
```

**Starting values.** Estimates, not measurements:

| Setting | Value | Why |
|---|---|---|
| Hint size | 5 columns × `FIXED(1024)` ≈ 5 KiB | Stress's default column count. |
| Rate | `throttle=200/s` ≈ 1 MiB/s of hints | Makes the overshoot bound (`r × F`) about 1 MiB; 16 MiB is reached in about 16 s, 256 MiB in about 4.3 min. |
| Rows per burst | enough to reach `1.5 × L` at 200/s: `n=4,800` (16 MiB), `n=19,200` (64 MiB), `n=77,000` (256 MiB) | Past the limit long enough to see the plateau and the flat counter (60 s at least). |
| Window | the plateau is read over the last 60 s of each burst | Several `du` samples and two flush periods. |
| `0B` arm | `n=250,000` (about 1.2 GiB) | Longer than the largest limit, so a plateau at 256 MiB would show; disk needed about 1.5 GiB. |

**If the files do not reach the limit** (`T` flat below *L* with `shouldHint` returning `true`): check the rate (`TotalHints` rising) and that node 3 is `DN` and in the ring; raise `threads` to 16 and drop the throttle to `400/s`, and widen the overshoot bound accordingly in the results. Record each step.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — the host's hint-file bytes, `T` | `hints-du.sh` (per host id; `nodetool status` gives the host ids) every second; the trace's `total=` field is the operand as the check read it. | Throughout | The check's `T` is the **cached** per-file size, refreshed when a flush session closes ([`HintsWriter.java:274`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java#L274)), so `du` can sit above `total=` by what the current flush has written. Compare them; a persistent gap larger than one flush's bytes is a finding. `du` on the whole directory mixes hosts: use per-host-file sums. |
| **Disallow evidence** | The decision trace: `result=false` lines with `total` above `limit`. Also `Hints_created-<addr>` flat (`bin/nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=HintsService,name=Hints_created-<addr with : replaced by .>' -f Count`) and `StorageMetrics.TotalHints` flat, while the stress's result block shows writes succeeding. Request tracing on a sample of writes carries the line `Not hinting <ep> which has reached to the max hints size …` ([`StorageProxy.java:2494-2495`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2494-L2495)). | Every second (trace); counters at the start and end of each burst | **No metric fires on this disallow** (§6b). `Hints_not_stored-<addr>` is marked only by the time-window rejection, so it must stay at zero; **do not use it as the signal**, use it as the contamination check. `shouldHint` is read at seven sites (§5): the trace covers all of them. |
| **Bypass volume** | None recorded. A `result=true` line with `total > limit` and `limit > 0` would be one (it should not exist). | — | The guard `maxHintsSize > 0` makes every line at `limit=0` `true`: that is the default-mode finding, not a bypass. |
| **Real resource** — disk | `hints-du.sh` totals; `df` of the hints volume at the start and end. | Throughout | The hint-file bytes are the resource; no further read is needed. Do not read RSS or heap. |
| **Loss after the burst** | After the sweep (and not before), restart the stopped host and, once its hints have drained (`HintsService` `PendingHints`/`ls data/hints` empty), read `SELECT count(*)` at `ALL` against the rows written. | Once, at the end | Needs the host back; it destroys the operand, so it is the last step. At `0B` and at the limit the counts differ by the rows not hinted. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. Record pass or fail and the asserted values.

1. Run upstream `StorageProxyTest`. `testShouldHintOnExceedingSize` uses a Byteman stub
   for the operand (`return 2097152`) against a 1 MiB limit: it shows the disallow but
   not the real operand and not the boundary.
2. Run `ShouldHintSizeTest`, with a fake endpoint marked dead and a host id in the
   token metadata, as `shouldHintTest` does, and `max_hint_window` large:
   1. with the limit at `0` (the default), writes 2 MiB of hints through
      `HintsService` and flushes: `shouldHint` is `true` and `getTotalHintsSize` is the
      sum of the files' lengths;
   2. sets the limit to 1 MiB (`setMaxHintsSizePerHostInMiB(1)`) with the files at 2 MiB:
      `shouldHint` is `false`;
   3. at the boundary: removes the hints (`HintsService.instance.deleteAllHintsForEndpoint(<ep>)`)
      and writes until `getTotalHintsSize` is exactly 1,048,576 bytes (adjusting the last
      hint's payload): `shouldHint` is `true` (the comparison is `>`, [`:2492`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2492)); one byte more: `false`;
   4. the limit set back to `0`: `true` again with the same files;
   5. the operand: after each flush `getTotalHintsSize` equals the sum of `File.length()` over the host's files.

   Record pass or fail and, per step, the asserted numbers.

**Before the cluster tier.**

1. **Instrument check.** Run `ShouldHintSizeTest` with the rule attached and expect one
   trace line per `shouldHint` call, with `limit=1048576` in steps 2 and 3:

   ```bash
   ant testsome -Dtest.name=org.apache.cassandra.service.ShouldHintSizeTest \
     -Dtest.jvm.args="-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/should-hint.btm -Dstage4.byteman.out=$HOME/stage4-logs/cluster/instrument-check.txt"
   ```

2. **Start node 1 with the rule; nodes 2 and 3 without:**

   ```bash
   mkdir -p ~/stage4-logs/cluster/<run>
   export JVM_EXTRA_OPTS="-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/should-hint.btm,listener:true -Dstage4.byteman.out=$HOME/stage4-logs/cluster/<run>/should-hint.txt"
   bin/cassandra -p cassandra.pid > ~/stage4-logs/cluster/<run>/stdout.txt 2>&1   # in node 1's tree
   ```

   Confirm with `Submit -l` that the rule is loaded, and that `nodetool status` shows
   `UN` on all three; then stop node 3.

**Cluster tier, for each limit value:**

1. **Control run** — with all nodes up, 30 s of the stress stream: the hints directory stays empty. Stop node 3, wait for `DN`, record the time and the hint-window clock.
2. **Scenario A — reach the limit** — set the limit over JMX (and read it back), start `hints-du.sh` and the burst (9c) sized to stop just below *L*; record `T`, `Hints_created` and the trace. Expect `result=true` throughout.
3. **Scenario B — try to exceed it** — run the rest of the burst past *L*; record the same, plus the stress result block and one traced write (`-tracing`-style sample: `bin/cqlsh -e "TRACING ON; INSERT …"` against node 1 at the plateau) showing the `Not hinting …` line.
4. **Two-host arm** — at 64 MiB: stop node 2 as well (keyspace RF stays 3, writes at `ONE` need only node 1), repeat A and B; compare the per-host plateaus and the directory total.
5. **Default arm** — set `0`, run the `0B` burst; read the growth and the file count; stop the burst before the disk passes 70 %.
6. **Loss read-back** — start nodes 2 and 3, wait for `UN` and the hints to drain, read `count(*)` at `ALL`.

**Window-contamination check (9b)** — `Hints_not_stored-<addr>` at the end of every arm.

Stop when each scenario's records are taken; a run where the files never reach *L* is invalid (9a).

**Record for stage 4:** every node's `cassandra.yaml` diff and JVM options, the exact commands, the `Submit -l` output, the trace, `hints-du.sh` output, the stress headers and result blocks, the traced-write output, and the read-back counts, per value.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3a` — from [`../stage2-ai-preprocessing/bands.md`](../../../stage2-ai-preprocessing/bands.md)'s **band A1** list, row `StorageProxy.java:2492#1` ("total hints size on disk against the configured per-host maximum, dropping the hint"). Judged in the band-A1 pass on 2026-09-28 and recorded in `pending.md`; written up 2026-09-28. |
| **Filed by / Date** | Claude (`claude-opus-5`) session, 2026-09-28 |
| **Line numbers checked** | 2026-09-28 against the local `cassandra-5.0.9` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`). |
| **Escape hatch / Target-3 note** | **The default is the gap.** `max_hints_size_per_host` defaults to `0B`, and `if (maxHintsSize > 0)` at [`:2489`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2489) skips the comparison entirely — so on an unconfigured node this constraint does not exist. That is a stronger default-mode gap than the `native_transport_throw_on_overload` case (where the check runs and is then ignored) and comparable to the compaction guard's non-domination (where the check is never reached), but arrived at a third way: the operator simply has not switched it on. Two further Target-3 observations: the bound is **per host**, so `N` down hosts multiply it, and the disallow path is **silent** — no counter, no log — which makes the resulting data loss hard to detect operationally. |
| **Stage-4 feedback** | none yet. **§9 converted to the new layout 2026-10-06** (9a to 9e) from the old §9; not yet audited (stage-4 README, step 0) and not yet run. The new §9 lists its harness as work for step 1. |
| **Notes** | `getTotalFileSize()` sums `dispatchDequeue`, `corruptedFiles` and the current writer's file. A hint file in none of those three would be invisible to the check; whether such a state is reachable was not established here and is left as an open question for the "Files grow past" row of §9a's Conclusions. **Found while converting §9 (2026-10-06), for stage 3 to judge, not applied to §8:** the check's operand is the hint files' size as of the last flush session ([`HintsWriter.java:274`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java#L274)), and hints are buffered and flushed every `hints_flush_period` (default 10 s), so the overshoot past the limit is up to the hints accepted in one flush period (and buffered), not "one hint". §9a states the prediction as `L + r × F + H` and measures both. |

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
