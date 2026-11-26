# INTERNODE_EVENT_THREADS (`-Dcassandra.internode-event-threads`) — size of the internode messaging event-loop group — verification solution  <!-- file: cases/INTERNODE_EVENT_THREADS-SocketFactory-defaultGroup--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the place the value becomes a capacity, **linked**: [`SocketFactory.java:192`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/SocketFactory.java#L192) (`defaultGroup = provider.makeEventLoopGroup(EVENT_THREADS, ... "Messaging-EventLoop")`) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code agent (config-first unit, order 10), 2026-11-26 |
| Estimate | `positive` (small magnitude). The property is the exact executor count of the `Messaging-EventLoop` group; each executor eagerly holds a fixed native epoll event array and 3 fds, and each executor thread that starts holds a stack plus up to 3 pinned 128 KiB networking-pool chunks, so this memory follows `min(N, channels)` and `N`. It is a few MiB at default and does not bound internode message memory, which other limits govern. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `INTERNODE_EVENT_THREADS`, a JVM system property (`cassandra.internode-event-threads`) declared in
[`CassandraRelevantProperties.java:285`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L285)
with no default of its own. Unit: a count of event-loop executors (threads).
It is read once into a `static final` at `SocketFactory.java:86`:
`EVENT_THREADS = INTERNODE_EVENT_THREADS.getInt(FBUtilities.getAvailableProcessors())`.
`getInt(int)` (`CassandraRelevantProperties.java:881-888`) returns the override default when the property is absent, else parses the string (no range check).
Default derivation: `FBUtilities.getAvailableProcessors()` (`FBUtilities.java:135`, `150-156`) = `-Dcassandra.available_processors` if set and > 0, else yaml `available_processors` (`Config.java:183`, default `-1`, read via `DatabaseDescriptor.java:2464`), else `Runtime.availableProcessors()` (which follows cgroup / `-XX:ActiveProcessorCount`).
Set only with `-D` (e.g. `JVM_EXTRA_OPTS`, `conf/jvm-server.options`). No yaml key, no JMX. Needs a restart (static final, read when `SocketFactory` is first loaded, i.e. when `MessagingService` is built, `MessagingService.java:301`).
Edge values: `0` passes through to Netty, whose `MultithreadEventLoopGroup` replaces 0 by its default `max(1, io.netty.eventLoopThreads or 2 x availableProcessors)` (Netty, not in this tree). A negative value makes Netty throw `IllegalArgumentException` when the group is built, so the node fails to start.

**A2. What it caps.** It caps the **number of executors (and thus threads) in the internode messaging event-loop group**, not a byte count. The memory each executor or thread holds:
- *Eager, per executor (all N, at construction):* with the epoll provider (the default on Linux, `SocketFactory.java:162-165`, `NativeTransportService.java:168-176`, `CassandraRelevantProperties.java:371`), Netty's `EpollEventLoop` constructor allocates an `EpollEventArray` of 4096 `epoll_event`s as a direct `ByteBuffer` (12 B each on x86_64, so E = 49,152 B; 16 B on aarch64, so 65,536 B) and opens an epoll fd, an eventfd and a timerfd (Netty 4.1.130.Final, `.build/parent-pom-template.xml:749`. This is from the Netty source and is not in this tree; stage 4 confirms it, see B2e step 2).
- *Lazy, per started thread:* threads start on first task (Netty `ThreadPerTaskExecutor`, `SocketFactory.java:106`, `132`). Each started thread has a Java stack (`-Xss256k`, `conf/jvm-server.options:123`) and, once it allocates from the networking `BufferPool`, its own `LocalPool` (`BufferPool.java:168`), which holds up to **3 chunks of 128 KiB** (`BufferPool.java:128`, `543`). Messaging handshakes set `recycleWhenFree=false` on the event-loop thread (`InboundConnectionInitiator.java:445`, `474`; `OutboundConnectionInitiator.java:385`), so fully freed chunks stay pinned in that thread's pool instead of going back to the global pool (`BufferPool.java:839`).

The quantity the code "compares against the limit" is the executor count of the group (`Iterables.size(defaultGroup)`), and the number of distinct threads that serve channels, `min(N, channels assigned)`.

**A3. Mechanism.**
1. `SocketFactory.java:86`: `EVENT_THREADS` is fixed at class load.
2. **The capacity is set here:** [`SocketFactory.java:192`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/SocketFactory.java#L192) → `Provider.makeEventLoopGroup(int, String)` (`SocketFactory.java:152-156`) → `new EpollEventLoopGroup(threadCount, new ThreadPerTaskExecutor(...), ..., capacity -> new ManyToOneConcurrentLinkedQueue<>())` (`SocketFactory.java:129-137`), or the NIO version (`103-111`). Netty builds exactly `threadCount` child executors in the constructor.
3. Channels are spread round-robin over those executors (Netty `DefaultEventExecutorChooserFactory`):
   - every outbound messaging connection object takes `defaultGroup().next()` once at construction (`OutboundConnection.java:310`), 3 per peer (`OutboundConnections.java:86-88`);
   - every accepted inbound channel (messaging and inbound streaming) is registered on the child group `defaultGroup` (`SocketFactory.java:211`).
4. A thread starts when its executor first runs a task. Once started it lives until `SocketFactory.shutdownNow()` (`SocketFactory.java:279-285`, called at `MessagingService.java:658`). So the started-thread count only grows, up to N.
5. On each started thread, `BufferPoolAllocator` (`BufferPoolAllocator.java:40`, set as channel allocator at `InboundConnectionInitiator.java:108`, `169`, `OutboundConnectionInitiator.java:192`) allocates from the thread's `LocalPool`, which takes 128 KiB chunks from the global pool (`BufferPool.java:1014`), and keeps up to 3 of them.

What happens "at the limit": nothing is refused. With more channels than N, several channels share one executor (more work per thread), and no new thread or array is created. Bypass and overshoot:
- the global networking pool is capped separately by `networking_cache_size` (`BufferPool.java:443`, default `min(128 MiB, heap/16)`, `DatabaseDescriptor.java:573-574`). Past that cap, allocations become unpooled overflow (`BufferPool.java:263`), freed on release, so the per-thread pinning never exceeds the global pool cap;
- `LARGE_MESSAGES` inbound connections use a per-connection `LocalBufferPoolAllocator` (`InboundConnectionInitiator.java:479`, `LocalBufferPoolAllocator.java:40`), which scales with connections, not N;
- each executor's task queue is unbounded (`ManyToOneConcurrentLinkedQueue`, `SocketFactory.java:111`, `136`). N does not bound queued work.

**A4. Other consumers.**
- `outboundStreamingGroup`, sized by the same property (`SocketFactory.java:193`), is a separate case file.
- `Messaging-AcceptLoop`: fixed at 1 executor (`SocketFactory.java:191`).
- CQL native transport worker group: `new EpollEventLoopGroup()` with Netty's default thread count (`NativeTransportService.java:69`). It has the same per-executor cost but is governed by `io.netty.eventLoopThreads`, not this property.
- `Messaging-SynchronousWork` (`SocketFactory.java:181`): unbounded pool, independent of N.
- In-flight internode message memory is capped by `internode_application_{send,receive}_queue_*` (`Config.java:253-261`), not by N.
- The networking `BufferPool` is shared with the CQL transport.

**A5. Evidence beyond the source.**
- Netty 4.1 sources for `EpollEventLoop` (event array of 4096 when `maxEvents == 0`, `openFileDescriptors` = epoll, eventfd, timerfd), `EpollEventArray`, `io.netty.channel.unix.Buffer.allocateDirectWithNativeOrder` (`ByteBuffer.allocateDirect`), and `MultithreadEventLoopGroup` (0 → `DEFAULT_EVENT_LOOP_THREADS`): https://github.com/netty/netty/tree/netty-4.1.130.Final/transport-classes-epoll/src/main/java/io/netty/channel/epoll. This comes from recollection and was not opened in this session (the rules allow only the source tree). Stage 4 must confirm it from the jar (B2e step 2).
- The property was introduced with the 4.0 internode messaging rewrite (CASSANDRA-15066, https://issues.apache.org/jira/browse/CASSANDRA-15066). This was not re-checked. `git` history is not present in the given tree.
- No test in `test/` references the property.

## Config-first: places found

1. `SocketFactory.java:86`: the value is read into `static final EVENT_THREADS` (default = available processors). This is the read point and restricts nothing by itself.
2. **`SocketFactory.java:192`**: `defaultGroup` gets `EVENT_THREADS` executors (`Messaging-EventLoop`). It caps the executors, each holding an eager epoll event array (about 48 KiB direct) and 3 fds, and the threads, each holding a stack and up to 3 pinned 128 KiB networking chunks. **This file.**
3. **`SocketFactory.java:193`**: `outboundStreamingGroup` gets `EVENT_THREADS` executors (`Streaming-EventLoop`), with the same per-executor and per-thread costs, for outbound streaming channels. **Case file `INTERNODE_EVENT_THREADS-SocketFactory-outboundStreamingGroup--autonomous.md`.**
4. `SocketFactory.java:211`: the server bootstrap uses `defaultGroup` as child group. All accepted inbound messaging and streaming channels are spread over the N messaging threads. This is assignment only; the bound is place 2.
5. `OutboundConnection.java:310`: each outbound messaging connection is pinned to `defaultGroup().next()` (round-robin). It decides how many of the N threads ever start, `min(N, channels)`.
6. `NettyStreamingConnectionFactory.java:53`: each outbound streaming channel is pinned to `outboundStreamingGroup().next()`. Same role as place 5, for place 3.
7. `InboundConnectionInitiator.java:445`, `:474`, `OutboundConnectionInitiator.java:385` (with `BufferPool.java:839`, `543`): `setRecycleWhenFreeForCurrentThread(false)` on the event-loop thread makes each loop thread keep up to 3 freed 128 KiB chunks. This is the per-thread memory that places 2 and 3 multiply.

## B. Verification solution

**B1. Claim under test.** On a Linux node with the epoll provider, `-Dcassandra.internode-event-threads=N` sets the `Messaging-EventLoop` group to exactly N executors. Native memory and fds held by the group grow linearly in N (per executor about E = 49,152 B direct plus 3 fds). The number of live `Messaging-EventLoop` threads, with their stacks and pinned networking chunks (≤ 3 × 128 KiB each), is `min(N, channels assigned)` and never exceeds N.

### B2. Unit tier

**B2a. Environment and build.** Linux x86_64, JDK 11, Ant. Copy the pinned tree to local disk, never building in the shared tree:
`SRC=/mydata/$USER-s4/iet/cassandra-5.0.9; mkdir -p $(dirname $SRC); rsync -a <pinned cassandra-5.0.9 tree>/ $SRC/`.
Check `df -T $(dirname $SRC)` shows a local filesystem (not nfs) with ≥ 10 GiB free.
`cd $SRC && ant build-test` (builds the main jar, dependencies into `build/lib/jars`, and test classes).
Add the probe below as `$SRC/test/unit/org/apache/cassandra/net/InternodeEventThreadsProbeTest.java`. It is in package `org.apache.cassandra.net` because the `SocketFactory` constructor and `defaultGroup()` are package-private.
Test JVM (from `build.xml:1153-1192`): 1024 MiB heap (so the networking pool cap is 64 MiB), `-Xss256k` on x86, `-XX:ActiveProcessorCount=2` (so the unset default is 2), and our extra args through `-Dtest.jvm.args`.

```java
package org.apache.cassandra.net;

import java.io.File;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.management.ObjectName;

import com.google.common.collect.Iterables;
import org.junit.Test;

import io.netty.channel.EventLoopGroup;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.service.NativeTransportService;
import org.apache.cassandra.utils.FBUtilities;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

public class InternodeEventThreadsProbeTest
{
    private static final String GROUP = System.getProperty("probe.group", "default"); // default | streaming | control
    private static final int TASKS = Integer.getInteger("probe.tasks", 64);
    private static final int CONTROL_THREADS = Integer.getInteger("probe.controlThreads", 8);
    private static final String OUT = System.getProperty("probe.out", "/tmp/iet-probe.txt");

    @Test
    public void probe() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        BufferPool pool = BufferPools.forNetworking();
        Method numChunks = BufferPool.class.getDeclaredMethod("unsafeNumChunks"); // per-thread LocalPool chunk count
        numChunks.setAccessible(true);
        boolean epoll = NativeTransportService.useEpoll();             // load native transport before "before"
        Class.forName("io.netty.channel.epoll.EpollEventLoopGroup");

        try (PrintWriter out = new PrintWriter(OUT))
        {
            out.println("prop=" + System.getProperty("cassandra.internode-event-threads", "<unset>"));
            out.println("availableProcessors=" + FBUtilities.getAvailableProcessors() + " epoll=" + epoll);
            out.println("poolThreshold=" + pool.memoryUsageThreshold());
            System.gc(); Thread.sleep(500);
            snapshot(out, "before");
            SocketFactory sf = new SocketFactory();
            snapshot(out, "constructed");
            out.println("executors.default=" + Iterables.size(sf.defaultGroup()));
            out.println("executors.streaming=" + Iterables.size(sf.outboundStreamingGroup()));

            ExecutorService control = GROUP.equals("control") ? Executors.newFixedThreadPool(CONTROL_THREADS) : null;
            EventLoopGroup group = GROUP.equals("streaming") ? sf.outboundStreamingGroup() : sf.defaultGroup();
            Map<String, Integer> chunksByThread = new ConcurrentHashMap<>();
            List<Future<?>> futures = new ArrayList<>();
            for (int i = 0; i < TASKS; i++)
            {
                Runnable task = () -> {
                    pool.setRecycleWhenFreeForCurrentThread(false); // as InboundConnectionInitiator:474 / OutboundConnectionInitiator:385
                    ByteBuffer a = pool.get(100 << 10, BufferType.OFF_HEAP); // 3 x 100 KiB live at once -> 3 chunks
                    ByteBuffer b = pool.get(100 << 10, BufferType.OFF_HEAP);
                    ByteBuffer c = pool.get(100 << 10, BufferType.OFF_HEAP);
                    pool.put(a); pool.put(b); pool.put(c);                  // freed, but kept by the LocalPool
                    try { chunksByThread.put(Thread.currentThread().getName(), (Integer) numChunks.invoke(pool)); }
                    catch (Exception e) { throw new RuntimeException(e); }
                };
                futures.add(control != null ? control.submit(task) : group.next().submit(task));
            }
            for (Future<?> f : futures)
                f.get(60, TimeUnit.SECONDS);
            out.println("distinctThreads=" + chunksByThread.size());
            out.println("pinnedChunks=" + chunksByThread.values().stream().mapToInt(Integer::intValue).sum());
            out.println("poolSize=" + pool.sizeInBytes() + " poolOverflow=" + pool.overflowMemoryInBytes());
            snapshot(out, "driven");

            if (control != null) { control.shutdownNow(); control.awaitTermination(10, TimeUnit.SECONDS); }
            sf.shutdownNow();
            sf.awaitTerminationUntil(System.nanoTime() + TimeUnit.SECONDS.toNanos(10));
            Thread.sleep(1000);
            snapshot(out, "shutdown");
        }
    }

    private static void snapshot(PrintWriter out, String tag) throws Exception
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                out.println(tag + ".direct.count=" + b.getCount() + " " + tag + ".direct.used=" + b.getMemoryUsed());
        out.println(tag + ".fds=" + new File("/proc/self/fd").list().length);
        int msg = 0, str = 0;
        for (ThreadInfo t : ManagementFactory.getThreadMXBean().dumpAllThreads(false, false))
        {
            if (t.getThreadName().contains("Messaging-EventLoop")) msg++;
            if (t.getThreadName().contains("Streaming-EventLoop")) str++;
        }
        out.println(tag + ".threads.messaging=" + msg + " " + tag + ".threads.streaming=" + str);
        String nmt = (String) ManagementFactory.getPlatformMBeanServer().invoke(
            new ObjectName("com.sun.management:type=DiagnosticCommand"), "vmNativeMemory",
            new Object[]{ new String[]{ "summary" } }, new String[]{ String[].class.getName() });
        Matcher m = Pattern.compile("-\\s+(Thread|Other) \\(reserved=(\\d+)KB, committed=(\\d+)KB\\)").matcher(nmt);
        while (m.find())
            out.println(tag + ".nmt." + m.group(1) + ".reservedKB=" + m.group(2) + " " + tag + ".nmt." + m.group(1) + ".committedKB=" + m.group(3));
        Matcher t = Pattern.compile("\\(thread #(\\d+)\\)").matcher(nmt);
        if (t.find())
            out.println(tag + ".nmt.threads=" + t.group(1));
    }
}
```

**B2b. Knobs.** `-Dcassandra.internode-event-threads` = unset (the default, 2 under `ActiveProcessorCount=2`), `0` (Netty fallback), `1`, `4`, `16`, `64`, and `-1` (rejection). These span 1 to 64 across a range where the driven chunks (`3 × 64 × 128 KiB = 24 MiB`) stay under the 64 MiB pool cap, so there is no overflow. It is set through `-Dtest.jvm.args`, one JVM per value, because the value is a static final.
`-Dprobe.group=default` for the case runs. The controls use `probe.group=control` and `-Dcassandra.native.epoll.enabled=false` (B2h).

**B2c. Workload.** `TASKS = 64` tasks submitted with `defaultGroup().next()` (the same round-robin call as `OutboundConnection.java:310`). Every executor gets ⌈64/N⌉ tasks, so all `min(N, 64)` threads start.
Each task sets `recycleWhenFree=false` (as the real handshake does), holds three 100 KiB buffers at once (100 + 100 > 128 KiB, so each needs its own chunk) and frees them. The thread's `LocalPool` then keeps 3 chunks.
Arithmetic: pinned = `3 × min(N, 64) × 128 KiB`. At N = 64 that is 192 chunks = 24 MiB = 3 macro chunks of 8 MiB (`BufferPool.java:385`), under the 64 MiB threshold.

**B2d. Observables and instruments.** All values are written by the probe to `probe.out`:
- `executors.default`: the group size, the operand itself;
- `distinctThreads` and `pinnedChunks`: Σ over threads of `BufferPool.unsafeNumChunks()` read on each thread through reflection;
- `poolSize`: `BufferPool.sizeInBytes()`, at 8 MiB macro granularity;
- `direct.count` and `direct.used`: the JDK `BufferPoolMXBean "direct"`, which catches the epoll arrays and the macro chunks;
- `/proc/self/fd` count;
- `Messaging-EventLoop` thread count (ThreadMXBean);
- NMT `Thread` and `Other` reserved/committed and `thread #`, from the DiagnosticCommand MBean (requires `-XX:NativeMemoryTracking=summary`).

Sampled at four points: before, constructed, driven, shutdown.
Not directly observable: how much of each thread's stack is committed (NMT gives an aggregate only), and the native epoll array when it is not allocated through `ByteBuffer.allocateDirect` (then it shows only in NMT `Other`).

**B2e. Procedure.**
1. B2a build. `OUT=/mydata/$USER-s4/iet/readings; mkdir -p $OUT`.
2. Confirm the Netty facts used in A2 from the jar in the copy:
   `J=$(ls $SRC/build/lib/jars/netty-transport-classes-epoll-*.jar $SRC/build/lib/jars/netty-all-*.jar 2>/dev/null | head -1)`;
   `javap -c -p -classpath $J io.netty.channel.epoll.EpollEventLoop | grep -n -E 'sipush +4096|EpollEventArray|newEpollCreate|newEventFd|newTimerFd'`.
   Record the event-array length and the fds opened. If they differ, restate E and the fd slope before step 3.
3. For each N in `unset 0 1 4 16 64 -1`:
   ```
   A="-XX:NativeMemoryTracking=summary -Dprobe.group=default -Dprobe.out=$OUT/unit-default-$N.txt"
   [ "$N" != unset ] && A="$A -Dcassandra.internode-event-threads=$N"
   (cd $SRC && ant testsome -Dtest.name=org.apache.cassandra.net.InternodeEventThreadsProbeTest -Dtest.jvm.args="$A") > $OUT/unit-default-$N.log 2>&1
   ```
4. Controls:
   - `N=1` with `-Dprobe.group=control -Dprobe.controlThreads=8`;
   - `N=64` with `-Dcassandra.native.epoll.enabled=false` (NIO), written to `$OUT/unit-ctl-*.txt`.
5. Compute deltas for each run, constructed − before (eager) and driven − constructed (lazy), and fill B2g.
6. `pgrep -f InternodeEventThreadsProbeTest` must print nothing. The test JVMs exit when ant exits.

**B2f. Predictions (stated before any run; x86_64, epoll, E = 49,152 B).** Eager deltas include the accept loop (1) and the streaming group (N) built in the same constructor, so they cover 1 + 2N executors. The defaultGroup share is N/(1+2N) of the delta and is checked through `executors.default`.

| N | executors.default | distinctThreads | pinnedChunks (bytes) | Δdirect.count / Δdirect.used (constructed − before) | Δfds | poolSize after drive |
|---|---|---|---|---|---|---|
| unset (→2) | 2 | 2 | 6 (768 KiB) | 5 / 245,760 | 15 | 8 MiB |
| 0 (→ Netty 2 × 2 = 4) | 4 | 4 | 12 (1.5 MiB) | 9 / 442,368 | 27 | 8 MiB |
| 1 | 1 | 1 | 3 (384 KiB) | 3 / 147,456 | 9 | 8 MiB |
| 4 | 4 | 4 | 12 (1.5 MiB) | 9 / 442,368 | 27 | 8 MiB |
| 16 | 16 | 16 | 48 (6 MiB) | 33 / 1,622,016 | 99 | 8 MiB |
| 64 | 64 | 64 | 192 (24 MiB) | 129 / 6,340,608 | 387 | 24 MiB |
| −1 | `IllegalArgumentException` from `new SocketFactory()`; no readings | | | | | |

Also predicted:
- `threads.messaging` at "constructed" = 0 (lazy start); at "driven" = `distinctThreads`; at "shutdown" = 0.
- NMT `thread #` grows from constructed to driven by `distinctThreads` (± 2 for unrelated threads). NMT `Thread` reserved grows by ≈ 256–320 KiB per started thread.
- `poolOverflow` = 0 in all runs.
- If the absolute eager deltas carry a constant offset from class loading, the slope must still hold: Δdirect.used(N) − Δdirect.used(1) = 2(N − 1)·E, and Δfds(N) − Δfds(1) = 6(N − 1).

The claim is wrong if `executors.default ≠ N`, if `distinctThreads` exceeds N, if pinnedChunks does not scale with `min(N, 64)`, or if the eager deltas do not grow with N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `executors.default = N`, `distinctThreads = min(N,64)`, `pinnedChunks = 3·min(N,64)`, eager slopes as predicted | Claim confirmed: the property sets the executor and thread count, and the per-executor and per-thread memory follows it. |
| `distinctThreads > N` or `executors.default ≠ N` | Claim wrong: the group size is not governed by the property (check that the property reached the JVM: `prop=` line). |
| pinnedChunks flat across N, while the control (`probe.group=control`, 8 threads) gives 24 | Per-thread pinning does not follow the group; the claim's memory part is wrong. |
| pinnedChunks flat and the control also flat | Instrument broken (reflection or `recycleWhenFree` not effective); not confirmed. |
| Δdirect.count flat in N, Δfds slope 6 per N | The epoll array is not a direct `ByteBuffer` in this Netty build. Use NMT `Other` for the eager memory; the executor part is still confirmed. |
| Δdirect and Δfds both flat in N | Executors are not built eagerly; the eager part is refuted. |
| `poolOverflow > 0` | Pool cap reached; the run does not test pinning. Rerun with fewer TASKS or a larger heap. |
| N=0 gives 4 executors | Confirms the Netty fallback (0 does not mean "none"). |
| N=−1 starts | Netty does not validate negative values; amend A1. |

**B2h. Controls.**
- *Positive control:* the same task on a plain `FixedThreadPool(8)` with N=1 must give `distinctThreads=8`, `pinnedChunks=24`. This shows the pinning instrument moves when a thread cap that is known to bind is the only change.
- *Attribution control:* N=64 with `-Dcassandra.native.epoll.enabled=false` (NIO). Δdirect.count is expected ≈ 0, because JDK selectors do not use direct `ByteBuffer`s. The executor and thread readings stay the same. This ties the direct slope to Netty's epoll arrays.
- *Fixed control:* `Messaging-AcceptLoop` is always 1 executor, so its fixed share is in every run.
- `DatabaseDescriptor`, native-library loading and Netty class loading happen before "before", to keep one-time costs out of the eager delta.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host with at least 8 GiB RAM free and `ulimit -n` ≥ 8192 (`ulimit -n` to check). Three Cassandra processes on loopback 127.0.0.1, .2 and .3, each with a 1 GiB heap. The JDK 11 copy is in `$SRC` from B2a: `cd $SRC && ant jar && ant stress-build`.
```
WORK=/mydata/$USER-s4/iet/cluster; OUT=/mydata/$USER-s4/iet/readings; mkdir -p $OUT
for i in 1 2 3; do
  rm -rf $WORK/n$i; mkdir -p $WORK/n$i/{data,commitlog,hints,saved_caches,cdc_raw,logs}
  cp -r $SRC/conf $WORK/n$i/conf; Y=$WORK/n$i/conf/cassandra.yaml
  sed -i -e "s/^listen_address:.*/listen_address: 127.0.0.$i/" -e "s/^rpc_address:.*/rpc_address: 127.0.0.$i/" \
         -e "s/- seeds:.*/- seeds: \"127.0.0.1:7000\"/" -e "s/^cluster_name:.*/cluster_name: 'iet'/" $Y
  printf "data_file_directories:\n    - $WORK/n$i/data\ncommitlog_directory: $WORK/n$i/commitlog\nhints_directory: $WORK/n$i/hints\nsaved_caches_directory: $WORK/n$i/saved_caches\ncdc_raw_directory: $WORK/n$i/cdc_raw\n" >> $Y
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"7${i}99\"/" $WORK/n$i/conf/cassandra-env.sh
done
start() { i=$1; N=$2; X="-XX:NativeMemoryTracking=summary $3"; [ "$N" != default ] && X="$X -Dcassandra.internode-event-threads=$N"
  CASSANDRA_CONF=$WORK/n$i/conf CASSANDRA_LOG_DIR=$WORK/n$i/logs MAX_HEAP_SIZE=1G JVM_EXTRA_OPTS="$X" $SRC/bin/cassandra -p $WORK/n$i/pid >/dev/null; }
stop()  { kill $(cat $WORK/n$1/pid); while kill -0 $(cat $WORK/n$1/pid) 2>/dev/null; do sleep 1; done; }
upn()   { until [ "$($SRC/bin/nodetool -p 7199 status 2>/dev/null | grep -c '^UN')" = "$1" ]; do sleep 5; done; }
NT="$SRC/bin/nodetool -p 7199"
sample() { P=$(cat $WORK/n1/pid); f=$OUT/cluster-$1.txt
  echo "fds=$(ls /proc/$P/fd | wc -l) rss_kb=$(ps -o rss= -p $P)" >> $f
  jcmd $P Thread.print > $OUT/tmp.threads
  echo "msgLoops=$(grep -c '^"Messaging-EventLoop-' $OUT/tmp.threads) strLoops=$(grep -c '^"Streaming-EventLoop-' $OUT/tmp.threads) accept=$(grep -c '^"Messaging-AcceptLoop-' $OUT/tmp.threads)" >> $f
  jcmd $P VM.native_memory summary | grep -E -A1 '^-\s+(Thread|Other) ' >> $f
  for a in MemoryUsed Count; do echo "direct.$a=$($NT sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f $a | tail -1)" >> $f; done
  for s in networking chunk-cache; do echo "pool.$s=$($NT sjk mx -mg -b "org.apache.cassandra.metrics:type=BufferPool,scope=$s,name=Size" -f Value | tail -1)" >> $f; done; }
```
Nodes 2 and 3 always run with the default property. Only node 1 varies.

**B3b. Knobs.** Node 1 `-Dcassandra.internode-event-threads` ∈ {1, 4, 16, 64, 256}, plus `default` (= `nproc` of the host; record `nproc`). The value 256 is above the channel count, so it measures the unbound thread count M and makes the eager slope large (≈ 24 MiB). Each value is a fresh cluster (wipe B3a dirs) and needs a node restart.

**B3c. Workload.**
- *Eager part:* only startup, sampled 60 s after the cluster shows 3 UN.
- *Lazy part:* node 1 must assign enough channels to its group.
  - `cassandra-stress write n=300000 cl=QUORUM -schema "replication(factor=3)" -node 127.0.0.1 -rate threads=32`, about 1 GB across the 3 nodes.
  - Then R = 6 rounds of restarting nodes 2 and 3. Each round gives node 1 at least 2 new inbound channels per peer (urgent + small, and large if used).
  - Then `cassandra-stress read n=100000 cl=QUORUM -node 127.0.0.1 -rate threads=32`.
  - Channels assigned on node 1: 6 outbound connection objects plus ≥ 2 × 2 × 7 = 28 inbound, so M ≥ 34 > 16. All executors for N ≤ 16 receive at least one inbound (always active) channel.
  - Duration ≈ 15 min per N.

**B3d. Observables and instruments.** On node 1:
- `/proc/<pid>/fd` count;
- `Messaging-EventLoop-*` thread count (`jcmd Thread.print`);
- NMT `Thread` (reserved/committed, `thread #`) and NMT `Other`;
- JDK direct pool `MemoryUsed` and `Count` via `nodetool sjk mx`;
- Cassandra `BufferPool` `Size` for `networking` and `chunk-cache` (`BufferPoolMetrics.java:58-64`);
- RSS.

Samples: T0 (eager, after startup) and T1 (after the workload).
- *Eager residual* = `direct.MemoryUsed − pool.networking − pool.chunk-cache`. This removes Cassandra's own direct pools, which grow in 8 MiB macro steps.
- *Not observable at this tier:* chunks pinned per thread (no metric). `pool.networking` grows in 8 MiB steps and the cap is `min(128 MiB, 1 GiB/16) = 64 MiB`, so it cannot resolve 3 × 128 KiB per thread. The unit tier covers that part.

**B3e. Procedure.** For each N in `1 4 16 64 256 default`:
1. Wipe and recreate B3a dirs, then start: `start 1 $N; sleep 30; start 2 default; sleep 30; start 3 default; upn 3; sleep 60; sample $N-T0`.
2. Run the write stress, the 6 restart rounds (`for r in $(seq 6); do stop 2; stop 3; start 2 default; start 3 default; upn 3; done`) and the read stress. Then `sample $N-T1`.
3. Stop the cluster: `stop 3; stop 2; stop 1`. `pgrep -f "$WORK/n"` must be empty.
4. Positive control run (B3h): N=1 with `start 1 1 "-Dio.netty.eventLoopThreads=256"`, T0 only, as `ctl-netty256-T0`.

**B3f. Predictions.** Let M = msgLoops at N=256, T1 (expected 20–40, ≤ channels assigned) and E = 49,152 B. Values are relative to N=1.

| N | msgLoops T0 | msgLoops T1 | Δfds T0 vs N=1 | Δ eager residual T0 vs N=1 | Δ NMT Thread reserved T1 vs N=1 |
|---|---|---|---|---|---|
| 1 | ≤ 1 | 1 | 0 | 0 | 0 |
| 4 | ≤ 4 | 4 | 18 | 294,912 B (±1 MiB noise) | ≈ 3 × 256–320 KiB |
| 16 | ≤ 12 | 14–16 | 90 | 1.47 MB (±1 MiB) | ≈ 15 × 256–320 KiB |
| 64 | ≤ 12 | M | 378 | 6.19 MB | ≈ (M − 1) × 256–320 KiB |
| 256 | ≤ 12 | M | 1,530 | 25.07 MB | ≈ (M − 1) × 256–320 KiB |
| default (`nproc`) | ≤ 12 | min(nproc, M) | 6(nproc − 1) | 2(nproc − 1)·E | per thread as above |

Δfds and Δresidual count both groups, because node-wide the property sizes both: 2 × 3 fds and 2E per unit of N. msgLoops never exceeds N in any run, and msgLoops at N=64 equals msgLoops at N=256 (both = M, since N does not bind). The `Messaging-AcceptLoop` count is 1 in every run.
The claim is wrong if msgLoops > N anywhere, if Δfds or the residual stays flat from N=1 to N=256, or if msgLoops(T1) at N=4 or N=16 is below N while M ≥ 34.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| msgLoops = min(N, M), fds and residual slopes as predicted | Confirmed: the property bounds the group's threads and executors, and their native memory follows it at node level. |
| msgLoops > N | Claim wrong: the thread count is not capped by the property. |
| Δfds slope ≈ 6/N but residual flat | The epoll array is not counted in the direct pool. Check NMT `Other` slope ≈ 2E/N instead; the executor part stands. |
| fds and residual flat, while the positive control (`io.netty.eventLoopThreads=256`) moves fds by ≈ 3 × (256 − 2·nproc) | Executors are not eager for this group, or the property did not reach node 1 (check `ps -o args`); the eager claim is refuted. |
| Positive control also flat | Instruments not sensitive; not confirmed. |
| msgLoops(T1) < N for N ≤ 16 | Too few channels assigned; raise R. Not a refutation of the cap. |
| NMT Thread reserved delta ≫ (threads × 320 KiB) | Other threads started; compare `thread #` deltas before concluding. |

**B3h. Controls.**
- *Positive control:* `-Dio.netty.eventLoopThreads=256` on node 1 sizes the CQL worker group (`NativeTransportService.java:69`, Netty default thread count). This cap is known to bind and uses the same Netty executor type, so fds and the residual must rise by ≈ 3 and E per extra executor. It shows the instruments see this per-executor cost.
- *Constant control:* `Messaging-AcceptLoop` is 1 thread in every run.
- *Peer control:* nodes 2 and 3 are unchanged across runs, so channel counts M come from the same workload.
- *Noise:* the residual subtracts Cassandra's own direct pools. The N=1 and N=4 contrasts are within noise by design; the slope is judged on N = 64 and 256.

**B4. Risks and cleanup.**
- **Disk:** unit tier uses none beyond the build (~2 GB in `$SRC/build`). The cluster uses about 3 GB under `$WORK`, which must be local disk (`df -T`). Never use the shared source tree or shared storage.
- **fds:** N=256 adds ~1,500 fds to node 1, so check `ulimit -n`.
- **Ports:** 7000, 9042 and 7199/7299/7399 are used on 127.0.0.1–3. Check `ss -ltn` first; nothing else may use them.
- **Processes:** after each N, `stop 3; stop 2; stop 1`. At the end, `pgrep -af "$WORK/n|InternodeEventThreadsProbeTest|cassandra-stress"` must print nothing; kill anything listed.
- **Cleanup:** copy `$OUT` to the results location, then `rm -rf $WORK $SRC/build/test` (and `$SRC` if no other case needs it).

## C. Sources read

- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (285, 371, 526, 799, 881-888)
- src/java/org/apache/cassandra/net/SocketFactory.java (60-290)
- src/java/org/apache/cassandra/utils/FBUtilities.java (130-157)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (573-574, 2464, 3796-3805)
- src/java/org/apache/cassandra/config/Config.java (183, 253-261, 493-494)
- src/java/org/apache/cassandra/net/OutboundConnection.java (300-315)
- src/java/org/apache/cassandra/net/OutboundConnections.java (58-88)
- src/java/org/apache/cassandra/net/MessagingService.java (301, 315, 651-659)
- src/java/org/apache/cassandra/net/InboundConnectionInitiator.java (108, 169, 438-490)
- src/java/org/apache/cassandra/net/OutboundConnectionInitiator.java (192, 375-392)
- src/java/org/apache/cassandra/net/BufferPoolAllocator.java, GlobalBufferPoolAllocator.java, LocalBufferPoolAllocator.java
- src/java/org/apache/cassandra/utils/memory/BufferPool.java (128-300, 380-480, 533-560, 764-920, 1014, 1095-1101, 1599-1650)
- src/java/org/apache/cassandra/utils/memory/BufferPools.java
- src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
- src/java/org/apache/cassandra/service/NativeTransportService.java (60-80, 168-176)
- src/java/org/apache/cassandra/streaming/async/NettyStreamingConnectionFactory.java (40-70)
- src/java/org/apache/cassandra/streaming/async/StreamingMultiplexedChannel.java (90-145)
- src/java/org/apache/cassandra/net/AbstractMessageHandler.java (grep for event-loop use)
- src/java/org/apache/cassandra/concurrent/NamedThreadFactory.java (34-44)
- src/java/org/apache/cassandra/tools/nodetool/Sjk.java (67)
- conf/jvm-server.options (123, 174), conf/cassandra-env.sh (88-160, 228-247, 307), conf/cassandra.yaml (keys listed in B3a)
- build.xml (94, 136, 225-230, 1017, 1153-1192, 1382), .build/parent-pom-template.xml (744-750)
- Netty 4.1 sources (cited from memory, not opened): https://github.com/netty/netty/tree/netty-4.1.130.Final

## D. Stage-4 feedback

none yet
