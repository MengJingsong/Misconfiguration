# concurrent_compactors — compaction_task

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | CONCURRENT_COMPACTORS-COMPACTION_TASK |
| **If-statement** | [`CompactionManager.submitBackground():245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L245) |

```java
public List<Future<?>> submitBackground(final ColumnFamilyStore cfs)
{
    if (cfs.isAutoCompactionDisabled())
    {
        logger.trace("Autocompaction is disabled");
        return Collections.emptyList();
    }

    int count = compactingCF.count(cfs);
    if (count > 0 && executor.getActiveTaskCount() >= executor.getMaximumPoolSize())
    {
        logger.trace("Background compaction is still running for {}.{} ({} remaining). Skipping",
                     cfs.getKeyspaceName(), cfs.name, count);
        return Collections.emptyList();
    }

    List<Future<?>> futures = new ArrayList<>(1);
    Future<?> fut = executor.submitIfRunning(new BackgroundCompactionCandidate(cfs), "background task");
    if (!fut.isCancelled())
        futures.add(fut);
    else
        compactingCF.remove(cfs);
    return futures;
}
```

## 2. Module

| Field | Content |
|-------|---------|
| **Module** | `compaction` — background compaction scheduling (`db/compaction`) |
| **One-line role** | Decides when to schedule a background compaction task for a table, and runs scheduled tasks on a bounded thread pool. |

## 3. Capacity-overflow check

| Field | Content |
|-------|---------|
| **Is this a capacity/overflow check?** | Yes — it compares the compaction executor's currently active task count against the executor's maximum pool size (a thread-pool capacity), gated additionally on whether this CF already has a compaction pending (`count > 0`). |
| **Usage-side operand** | `executor.getActiveTaskCount()` — number of threads currently busy running compaction tasks in the `CompactionExecutor` pool. |
| **Limit-side operand** | `executor.getMaximumPoolSize()` — the compaction executor's configured thread-pool size. |
| **Limit type** | Configuration (`concurrent_compactors`), with a computed default if unset. |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L335) — declared: `public volatile Integer concurrent_compactors;`
2. [`DatabaseDescriptor.java:777-781`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L777-L781) — configured/derived: if unset in `cassandra.yaml`, defaults to `Math.min(8, Math.max(2, Math.min(availableProcessors, dataFileDirectories.length)))`; validated `> 0` or throws `ConfigurationException`.
3. [`CompactionManager.CompactionExecutor():2022-2038`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L2022-L2038) — stored: `DatabaseDescriptor.getConcurrentCompactors()` is passed as the `threads` count when the singleton `CompactionExecutor` (a `WrappedExecutorPlus`/pooled `ThreadPoolExecutor`) is constructed, fixing its maximum pool size.
4. [`CompactionManager.submitBackground():245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L245) — read at the point of comparison via `executor.getMaximumPoolSize()`.

Note: `concurrent_compactors` can also be resized live via `setConcurrentCompactors()`/JMX (`ResizableThreadPool`), which reconfigures the same underlying pool's max size — the check always reads the live value, not a cached one.

## 4. Branch semantics

| Branch | Condition | Effect |
|--------|-----------|--------|
| **Allow** | `count == 0` OR `executor.getActiveTaskCount() < executor.getMaximumPoolSize()` | proceeds past the if-block to submit a new `BackgroundCompactionCandidate` task to the executor |
| **Disallow** | `count > 0 && executor.getActiveTaskCount() >= executor.getMaximumPoolSize()` | returns `Collections.emptyList()` immediately — no task is submitted this call |

```java
// allow-branch: falls through to
List<Future<?>> futures = new ArrayList<>(1);
Future<?> fut = executor.submitIfRunning(new BackgroundCompactionCandidate(cfs), "background task");
```

```java
// disallow-branch
{
    logger.trace("Background compaction is still running for {}.{} ({} remaining). Skipping",
                 cfs.getKeyspaceName(), cfs.name, count);
    return Collections.emptyList();
}
```

## 5. Code path: allow-branch → object creation

1. [`CompactionManager.submitBackground():245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L245) — allow branch taken (condition false), execution falls through the if-block.
2. [`CompactionManager.submitBackground():256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L256) — `new BackgroundCompactionCandidate(cfs)` constructed; its constructor adds `cfs` to `compactingCF` (`CompactionManager.java:349`).
3. [`CompactionManager.submitBackground():256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L256) — `executor.submitIfRunning(task, "background task")` called on the `CompactionExecutor`.
4. [`CompactionManager.CompactionExecutor.submitIfRunning():2056-2069`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionManager.java#L2056-L2069) — **object creation**: `submit(task)` hands the `Callable` to the underlying pooled `ThreadPoolExecutor`, which either runs it on an existing/new pool thread or queues it (queue is unbounded — `Integer.MAX_VALUE`, per `CompactionExecutor()`'s constructor at line 2024).

## 6. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | A `BackgroundCompactionCandidate` `Runnable` (wrapped as a `Callable` via `submitIfRunning`) submitted to the `CompactionExecutor`'s `ThreadPoolExecutor`; if fewer than `getMaximumPoolSize()` threads exist yet, a new pool thread is created to run it. |
| **Resource consumed** | A compaction thread-pool slot (thread), not memory directly. The task itself, once run, will go on to select SSTables and run an actual compaction (I/O + heap for the merge), but this specific if-check only gates *scheduling* — i.e., whether a new pool thread/task-slot is claimed now. |
| **Rough sizing** | Not byte-sized; sizing is a thread count bounded by `concurrent_compactors` (default `min(8, max(2, min(availableProcessors, numDataDirs)))`). |
| **Lifetime / release** | The pool thread is released back to the pool when `BackgroundCompactionCandidate.run()` completes (compaction finishes or determines there's nothing to do); `compactingCF` entry for `cfs` is removed at the end of `run()` (not shown above — see `CompactionManager.java:343-`). |

## Verification

See [README.md § Verifying a case](README.md#verifying-a-case-triggering-the-disallow-branch)
before setting `Status: verified` — line-number checking alone is not enough;
a designed experiment must have actually driven execution into the disallow
branch with recorded evidence.

| Field | Content |
|--------|---------|
| **Status** | pending |
| **Verified By / Date** | — |
| **Trigger method** | — |
| **Evidence** | — |
| **Notes** | The disallow branch here is a soft/best-effort skip, not a rejection: `submitBackground()` is documented as safe to over-call, and a skipped call just means the caller waits for the next `submitBackground()` invocation (Cassandra calls this frequently, e.g. after flush/compaction completion) to retry — no error, no blocking, no escape hatch observed yet. This differs from the memtable cases' park-or-force-through behavior; worth confirming by reading callers of `submitBackground()` before designing a trigger. A live-cluster or `CompactionManager`-level unit test (see `test/unit/org/apache/cassandra/db/compaction/CompactionManagerTest.java`, `CompactionExecutorTest.java` for existing harness patterns) driving `getActiveTaskCount() >= getMaximumPoolSize()` with `concurrent_compactors` set low (e.g. 1) is the natural first pass. |

---

## Notes

- The `count > 0` co-condition means this if-check is really "already have compaction(s) pending for this CF AND the pool is saturated" — a table with `count == 0` (no pending compaction tracked) always takes the allow branch regardless of pool saturation, so pool-capacity alone does not block a *first* task for an idle CF, only additional concurrent submissions for the same CF while the pool is full.
- `executor`'s queue itself is unbounded (`Integer.MAX_VALUE` queue limit at construction), so once past this check, task submission itself cannot be rejected for being "too many" — the real capacity control is entirely this if-check, upstream of `submit()`.
