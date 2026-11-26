# INTERNODE_EVENT_THREADS (`-Dcassandra.internode-event-threads`) — size of the outbound streaming event-loop group — verification solution  <!-- file: cases/INTERNODE_EVENT_THREADS-SocketFactory-outboundStreamingGroup--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the place the value becomes a capacity, **linked**: [`SocketFactory.java:193`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/SocketFactory.java#L193) (`outboundStreamingGroup = provider.makeEventLoopGroup(EVENT_THREADS, "Streaming-EventLoop")`) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code agent (config-first unit, order 10), 2026-11-26 |
| Estimate | `positive` (small magnitude). The property is the exact executor count of the `Streaming-EventLoop` group. Each executor eagerly holds a fixed native epoll event array and 3 fds, even on a node that never streams. Each started thread (one per outbound streaming channel until N is reached) holds a stack and up to 3 pinned 128 KiB networking chunks. This memory follows N and `min(N, streaming channels)`, but it does not bound streaming data memory. |
| Ground | — |

The full list of places found for this entry is in the companion case file `INTERNODE_EVENT_THREADS-SocketFactory-defaultGroup--autonomous.md`, under "Config-first: places found". This file is place 3.

## A. Constraint trace

**A1. The constraint.** `INTERNODE_EVENT_THREADS`, a JVM system property (`cassandra.internode-event-threads`) declared in
[`CassandraRelevantProperties.java:285`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L285)
with no default of its own. Unit: a count of event-loop executors (threads).
It is read once into `static final EVENT_THREADS` at `SocketFactory.java:86` via `getInt(FBUtilities.getAvailableProcessors())` (`CassandraRelevantProperties.java:881-888`: the default when absent, otherwise parsed with no range check).
Default: `-Dcassandra.available_processors`, else yaml `available_processors` (`Config.java:183`, default `-1`), else `Runtime.availableProcessors()` (`FBUtilities.java:135`, `150-156`).
Set only with `-D`, and needs a restart (static final, loaded with `MessagingService`, `MessagingService.java:301`).
The same value also sizes `defaultGroup` (`SocketFactory.java:192`, companion file). `0` falls back to Netty's default (`2 × availableProcessors` unless `io.netty.eventLoopThreads` is set). A negative value throws `IllegalArgumentException` when the group is built (Netty), so the node fails to start.

**A2. What it caps.** The **number of executors (and threads) in the outbound streaming event-loop group**.
- *Eager, per executor (all N, at construction, with or without streaming):* Netty's `EpollEventLoop` builds a 4096-entry `EpollEventArray` as a direct `ByteBuffer` (E = 49,152 B on x86_64) and opens an epoll fd, an eventfd and a timerfd (Netty 4.1.130.Final, `.build/parent-pom-template.xml:749`. This is not in this tree; it is confirmed in B2e step 2).
- *Lazy, per started thread:* a stack (`-Xss256k`, `conf/jvm-server.options:123`) and the thread's networking `BufferPool` `LocalPool` (`BufferPool.java:168`). After a successful outbound handshake, `OutboundConnectionInitiator.java:385` sets `recycleWhenFree=false` on that event-loop thread, so freed chunks stay pinned, up to 3 × 128 KiB (`BufferPool.java:128`, `543`, `839`).

Operand: the group's executor count, and the number of live `Streaming-EventLoop` threads = `min(N, outbound streaming channels created)`.

**A3. Mechanism.**
1. **Capacity set:** [`SocketFactory.java:193`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/SocketFactory.java#L193) → `makeEventLoopGroup` (`SocketFactory.java:152-156`) → `EpollEventLoopGroup(threadCount, new ThreadPerTaskExecutor(...), ...)` (`SocketFactory.java:131-136`), or NIO (`105-111`). The provider is epoll when `cassandra.native.epoll.enabled` is true (default) and epoll is available (`SocketFactory.java:162-165`, `NativeTransportService.java:168-176`). The group is separate "because sendFile is blocking" (comment, `SocketFactory.java:179-180`).
2. **Assignment:** every outbound streaming connection calls `outboundStreamingGroup().next()` (round-robin) in `NettyStreamingConnectionFactory.connect` (`NettyStreamingConnectionFactory.java:53`). Connections are created:
   - for a session's control channel (`StreamingMultiplexedChannel.java:171`);
   - for each file-transfer thread's file channel (`StreamingMultiplexedChannel.java:188`, `383-406`). File-transfer threads come from a per-session pool of up to `MAX_PARALLEL_TRANSFERS` = `cassandra.streaming.session.parallelTransfers`, default available processors (`StreamingMultiplexedChannel.java:94-98`, `133-135`), with a 1 s keep-alive. New threads therefore create new channels, and each new channel takes a new `next()`.
3. A loop thread starts on its executor's first task (the connect) and lives until `SocketFactory.shutdownNow()` (`SocketFactory.java:279-285`). The count only grows, to at most N.
4. On the loop thread, the handshake reply is read through the channel allocator `GlobalBufferPoolAllocator` (`OutboundConnectionInitiator.java:192`, `BufferPoolAllocator.java:40`), which creates the thread's `LocalPool`. Then `OutboundConnectionInitiator.java:385` stops recycling for it.

At the limit, nothing is refused: channels share executors. Bypass and overshoot:
- inbound streaming channels are on `defaultGroup` (`SocketFactory.java:211`), not on this group;
- the data written by file transfers is allocated on `NettyStreaming-Outbound-*` threads (`AsyncStreamingOutputPlus.java:92`, `143`), not on the loop threads;
- the networking pool as a whole is capped by `networking_cache_size` (`BufferPool.java:443`, `DatabaseDescriptor.java:573-574`), so per-thread pinning cannot exceed that pool.

**A4. Other consumers.**
- `defaultGroup`, same property, companion file.
- CQL worker group (`NativeTransportService.java:69`, Netty default size). Same per-executor cost, not this property.
- Streaming throughput, parallel transfers and file-transfer threads are governed by `stream_throughput_outbound`, `cassandra.streaming.session.parallelTransfers` and the `fileTransferSemaphore` (`StreamingMultiplexedChannel.java:98`), not by N.
- Entire-sstable streaming uses `sendFile` (zero copy), with no heap buffer.

**A5. Evidence beyond the source.**
- Netty 4.1 `EpollEventLoop`, `EpollEventArray`, `unix.Buffer.allocateDirectWithNativeOrder`, `MultithreadEventLoopGroup`: https://github.com/netty/netty/tree/netty-4.1.130.Final/transport-classes-epoll/src/main/java/io/netty/channel/epoll. This comes from recollection and was not opened (the rules allow only the source tree). Stage 4 checks it with `javap` (B2e step 2).
- CASSANDRA-15066 (4.0 internode messaging and streaming rewrite that introduced `SocketFactory`), not re-checked: https://issues.apache.org/jira/browse/CASSANDRA-15066.
- No test references the property.

## B. Verification solution

**B1. Claim under test.** With the epoll provider, `-Dcassandra.internode-event-threads=N` makes the `Streaming-EventLoop` group exactly N executors. The group's native memory and fds grow linearly in N even if the node never streams (about E = 49,152 B direct plus 3 fds per executor). The live `Streaming-EventLoop` threads, with their stacks and pinned networking chunks (≤ 3 × 128 KiB each), equal `min(N, outbound streaming channels created)` and never exceed N.

### B2. Unit tier

**B2a. Environment and build.** Linux x86_64, JDK 11, Ant, and a local-disk copy of the tag:
`SRC=/mydata/$USER-s4/iet/cassandra-5.0.9; rsync -a <pinned tree>/ $SRC/`. Check `df -T` shows a local filesystem.
Then `cd $SRC && ant build-test`.
Test JVM per `build.xml:1153-1192`: 1 GiB heap (networking pool cap 64 MiB), `-Xss256k`, `-XX:ActiveProcessorCount=2`.
Add `$SRC/test/unit/org/apache/cassandra/net/InternodeEventThreadsProbeTest.java`. This is the same probe as the companion case; it is repeated here so this file is complete:

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
                    pool.setRecycleWhenFreeForCurrentThread(false); // as OutboundConnectionInitiator:385
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

**B2b. Knobs.** `-Dcassandra.internode-event-threads` ∈ {unset (→2), 0 (→ Netty 4), 1, 4, 16, 64, −1}. Each value runs in its own JVM, because the value is a static final. Use `-Dprobe.group=streaming`.
Range: 1 to 64 keeps the pinned total (`3 × 64 × 128 KiB = 24 MiB`) under the 64 MiB pool cap.

**B2c. Workload.** 64 tasks submitted via `outboundStreamingGroup().next()` (the call at `NettyStreamingConnectionFactory.java:53`), so all `min(N, 64)` threads start.
Each task sets `recycleWhenFree=false` (as `OutboundConnectionInitiator.java:385` does on that thread), holds three 100 KiB networking buffers at once and frees them, which leaves 3 chunks pinned per thread.
Pinned = `3 × min(N,64) × 128 KiB`, at most 24 MiB.

**B2d. Observables and instruments.** As written by the probe:
- `executors.streaming`: the operand;
- `distinctThreads`, `pinnedChunks` (Σ `unsafeNumChunks()` per thread), `poolSize`, `poolOverflow`;
- JDK direct pool count and used;
- `/proc/self/fd` count;
- `threads.streaming`;
- NMT `Thread` and `Other` and `thread #` (needs `-XX:NativeMemoryTracking=summary`).

Sampled at before, constructed, driven and shutdown. Not observable: per-thread committed stack, and the epoll array if Netty does not allocate it through `ByteBuffer.allocateDirect` (then it shows only in NMT `Other`).

**B2e. Procedure.**
1. Build (B2a). `OUT=/mydata/$USER-s4/iet/readings; mkdir -p $OUT`.
2. Confirm the Netty facts from the jar:
   `J=$(ls $SRC/build/lib/jars/netty-transport-classes-epoll-*.jar $SRC/build/lib/jars/netty-all-*.jar 2>/dev/null | head -1)`;
   `javap -c -p -classpath $J io.netty.channel.epoll.EpollEventLoop | grep -n -E 'sipush +4096|EpollEventArray|newEpollCreate|newEventFd|newTimerFd'`.
   If the array length or fd count differ, restate E and the fd slope before running.
3. For each N in `unset 0 1 4 16 64 -1`:
   ```
   A="-XX:NativeMemoryTracking=summary -Dprobe.group=streaming -Dprobe.out=$OUT/unit-streaming-$N.txt"
   [ "$N" != unset ] && A="$A -Dcassandra.internode-event-threads=$N"
   (cd $SRC && ant testsome -Dtest.name=org.apache.cassandra.net.InternodeEventThreadsProbeTest -Dtest.jvm.args="$A") > $OUT/unit-streaming-$N.log 2>&1
   ```
4. Controls:
   - N=1 with `-Dprobe.group=control -Dprobe.controlThreads=8`;
   - N=64 with `-Dprobe.group=streaming -Dcassandra.native.epoll.enabled=false`.
5. Compute constructed − before and driven − constructed for each run.
6. `pgrep -f InternodeEventThreadsProbeTest` must be empty.

**B2f. Predictions (x86_64, epoll, E = 49,152 B).** Eager deltas cover all 1 + 2N executors built by the constructor (accept 1, default N, streaming N). This group's share is N executors (`executors.streaming`).

| N | executors.streaming | distinctThreads (threads.streaming at driven) | pinnedChunks (bytes) | Δdirect.count / Δdirect.used | Δfds | poolSize |
|---|---|---|---|---|---|---|
| unset (→2) | 2 | 2 | 6 (768 KiB) | 5 / 245,760 | 15 | 8 MiB |
| 0 (→4) | 4 | 4 | 12 (1.5 MiB) | 9 / 442,368 | 27 | 8 MiB |
| 1 | 1 | 1 | 3 (384 KiB) | 3 / 147,456 | 9 | 8 MiB |
| 4 | 4 | 4 | 12 (1.5 MiB) | 9 / 442,368 | 27 | 8 MiB |
| 16 | 16 | 16 | 48 (6 MiB) | 33 / 1,622,016 | 99 | 8 MiB |
| 64 | 64 | 64 | 192 (24 MiB) | 129 / 6,340,608 | 387 | 24 MiB |
| −1 | `IllegalArgumentException` in `new SocketFactory()` | | | | | |

Also predicted:
- `threads.streaming` = 0 at "constructed" and at "shutdown";
- `threads.messaging` stays 0 throughout (only the streaming group is driven);
- NMT `thread #` rises by `distinctThreads` (± 2);
- `poolOverflow` = 0.

Slope form, robust to a constant class-load offset: Δdirect.used(N) − Δdirect.used(1) = 2(N−1)E and Δfds(N) − Δfds(1) = 6(N−1).
The claim is wrong if `executors.streaming ≠ N`, if `distinctThreads > N`, or if pinnedChunks or the eager slopes are flat in N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| All columns as predicted | Confirmed: the property sets the streaming loop count, and the per-executor and per-thread memory follows it. |
| `executors.streaming ≠ N` or `distinctThreads > N` | Claim wrong. Check the `prop=` line first. |
| pinnedChunks flat in N, control (8-thread pool) gives 24 | Per-thread pinning does not follow the group; the memory part is refuted. |
| pinnedChunks flat and control flat | Instrument broken; not confirmed. |
| Δfds slope 6/N but Δdirect flat | The epoll array is not a direct `ByteBuffer` here. Use NMT `Other`; the executor part stands. |
| Δdirect and Δfds flat | Executors are not eager; the eager part is refuted. |
| `poolOverflow > 0` | Pool cap hit; reduce TASKS and rerun. |

**B2h. Controls.**
- *Positive control:* the same task on a `FixedThreadPool(8)` (a cap known to bind) gives 8 threads and 24 chunks.
- *Attribution control:* NIO provider (`-Dcassandra.native.epoll.enabled=false`) at N=64. Δdirect.count is expected ≈ 0 while executors and threads are unchanged.
- *Isolation:* `threads.messaging` stays 0, which shows the probe drives only this group.
- Native-library and class loading are done before "before".

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, at least 8 GiB RAM free, `ulimit -n` ≥ 8192. Three nodes on 127.0.0.1, .2 and .3 with 1 GiB heap each; `$SRC` from B2a, then `ant jar && ant stress-build`.
Per node configuration, with `hinted_handoff_enabled: false` so that node 3 misses writes and repair must stream:
```
WORK=/mydata/$USER-s4/iet/cluster; OUT=/mydata/$USER-s4/iet/readings; mkdir -p $OUT
for i in 1 2 3; do
  rm -rf $WORK/n$i; mkdir -p $WORK/n$i/{data,commitlog,hints,saved_caches,cdc_raw,logs}
  cp -r $SRC/conf $WORK/n$i/conf; Y=$WORK/n$i/conf/cassandra.yaml
  sed -i -e "s/^listen_address:.*/listen_address: 127.0.0.$i/" -e "s/^rpc_address:.*/rpc_address: 127.0.0.$i/" \
         -e "s/- seeds:.*/- seeds: \"127.0.0.1:7000\"/" -e "s/^cluster_name:.*/cluster_name: 'iet'/" \
         -e "s/^hinted_handoff_enabled:.*/hinted_handoff_enabled: false/" $Y
  printf "data_file_directories:\n    - $WORK/n$i/data\ncommitlog_directory: $WORK/n$i/commitlog\nhints_directory: $WORK/n$i/hints\nsaved_caches_directory: $WORK/n$i/saved_caches\ncdc_raw_directory: $WORK/n$i/cdc_raw\n" >> $Y
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"7${i}99\"/" $WORK/n$i/conf/cassandra-env.sh
done
start() { i=$1; N=$2; X="-XX:NativeMemoryTracking=summary $3"; [ "$N" != default ] && X="$X -Dcassandra.internode-event-threads=$N"
  CASSANDRA_CONF=$WORK/n$i/conf CASSANDRA_LOG_DIR=$WORK/n$i/logs MAX_HEAP_SIZE=1G JVM_EXTRA_OPTS="$X" $SRC/bin/cassandra -p $WORK/n$i/pid >/dev/null; }
stop()  { kill $(cat $WORK/n$1/pid); while kill -0 $(cat $WORK/n$1/pid) 2>/dev/null; do sleep 1; done; }
upn()   { until [ "$($SRC/bin/nodetool -p 7199 status 2>/dev/null | grep -c '^UN')" = "$1" ]; do sleep 5; done; }
NT="$SRC/bin/nodetool -p 7199"; ST=$SRC/tools/bin/cassandra-stress
sample() { P=$(cat $WORK/n1/pid); f=$OUT/cluster-str-$1.txt
  echo "fds=$(ls /proc/$P/fd | wc -l) rss_kb=$(ps -o rss= -p $P)" >> $f
  jcmd $P Thread.print > $OUT/tmp.threads
  echo "strLoops=$(grep -c '^"Streaming-EventLoop-' $OUT/tmp.threads) msgLoops=$(grep -c '^"Messaging-EventLoop-' $OUT/tmp.threads) fileThreads=$(grep -c '^"NettyStreaming-Outbound-' $OUT/tmp.threads)" >> $f
  jcmd $P VM.native_memory summary | grep -E -A1 '^-\s+(Thread|Other) ' >> $f
  for a in MemoryUsed Count; do echo "direct.$a=$($NT sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f $a | tail -1)" >> $f; done
  for s in networking chunk-cache; do echo "pool.$s=$($NT sjk mx -mg -b "org.apache.cassandra.metrics:type=BufferPool,scope=$s,name=Size" -f Value | tail -1)" >> $f; done; }
```

**B3b. Knobs.** Node 1 `-Dcassandra.internode-event-threads` ∈ {1, 4, 16, 64, 256, default (= `nproc`, recorded)}. Nodes 2 and 3 use the default. 256 exceeds the expected channel count, so it measures the unbound count C. Each value uses a fresh cluster.

**B3c. Workload.** Node 1 must open many outbound streaming channels.
1. Start all 3 nodes, then stop node 3.
2. Create the schema: `$ST write n=1000 cl=ONE -schema "replication(factor=3)" -node 127.0.0.1`. Then `$NT disableautocompaction keyspace1` (and the same on node 2 with `-p 7299`).
3. Write 16 batches: `for b in $(seq 16); do $ST write n=25000 cl=QUORUM -pop seq=$(( (b-1)*25000+1 ))..$(( b*25000 )) -node 127.0.0.1 -rate threads=16; $NT flush keyspace1; done`. This gives node 1 about 16 sstables, about 400k rows and roughly 100 MB that node 3 lacks.
4. Start node 3 and wait for 3 UN.
5. Run `$SRC/bin/nodetool -p 7399 repair --full keyspace1`. Node 3 is the initiator; node 1 is a follower that sends files over new FILE channels (`StreamingMultiplexedChannel.java:188`), one per file-transfer thread, in each of the per-range sessions (default `num_tokens: 16`).

C (channels node 1 opens) is expected to be ≥ 16. It is measured as strLoops at N=256. Duration ≈ 10–20 min per N.

**B3d. Observables and instruments.** On node 1:
- `Streaming-EventLoop-*` thread count (`jcmd Thread.print`);
- `/proc/<pid>/fd` count;
- NMT `Thread` (reserved, `thread #`) and `Other`;
- JDK direct pool `MemoryUsed` and `Count` (`nodetool sjk mx`);
- Cassandra `BufferPool` Size for `networking` and `chunk-cache` (`BufferPoolMetrics.java:58-64`);
- RSS.

Samples: T0 (after 3 UN, before any streaming) and T1 (after repair completes).
Eager residual = `direct.MemoryUsed − pool.networking − pool.chunk-cache`.
Not observable here: per-thread pinned chunks (no metric; the networking pool Size moves in 8 MiB steps). The unit tier covers that part.

**B3e. Procedure.** For each N:
1. Recreate dirs (B3a), then `start 1 $N; sleep 30; start 2 default; sleep 30; start 3 default; upn 3; sleep 60; sample $N-T0`.
2. `stop 3`, then B3c steps 2–4 (`start 3 default; upn 3`) and step 5 (repair). Wait for `nodetool -p 7399 repair` to return with exit 0. `sleep 10; sample $N-T1`.
3. `stop 3; stop 2; stop 1`. `pgrep -f "$WORK/n"` must be empty.
4. Positive control: N=1 with `start 1 1 "-Dio.netty.eventLoopThreads=256"`, T0 sample only (`ctl-netty256-T0`).

**B3f. Predictions.** C = strLoops at N=256, T1 (expected ≥ 16). E = 49,152 B. Deltas are relative to N=1.

| N | strLoops T0 | strLoops T1 | Δfds T0 | Δ eager residual T0 | Δ NMT Thread reserved T1 (streaming share) |
|---|---|---|---|---|---|
| 1 | 0 | 1 | 0 | 0 | 0 |
| 4 | 0 | 4 | 18 | 294,912 B (±1 MiB) | ≈ 3 × 256–320 KiB |
| 16 | 0 | min(16, C) | 90 | 1.47 MB (±1 MiB) | ≈ (min(16,C) − 1) × 256–320 KiB |
| 64 | 0 | min(64, C) | 378 | 6.19 MB | ≈ (min(64,C) − 1) × 256–320 KiB |
| 256 | 0 | C | 1,530 | 25.07 MB | ≈ (C − 1) × 256–320 KiB |
| default (`nproc`) | 0 | min(nproc, C) | 6(nproc − 1) | 2(nproc − 1)E | as above |

Δfds and Δresidual include both groups, because the property sizes both: 3 fds and E per executor, 2 groups.
strLoops is 0 at T0 in every run: the streaming group's eager cost is paid with no streaming at all.
strLoops never exceeds N. The repair completes in every run, including N=1 (sharing a loop does not refuse work).
The claim is wrong if strLoops > N anywhere, if strLoops(T1) for N=4 is below 4 while C ≥ 16, or if Δfds or the residual is flat from 1 to 256.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| strLoops(T1) = min(N, C), strLoops(T0) = 0, eager slopes as predicted | Confirmed: the property caps the streaming loop threads, and the group's eager native memory follows N without any streaming. |
| strLoops > N | Claim wrong. |
| strLoops(T0) > 0 | Something streams at startup; note it. The cap claim is unaffected. |
| fds and residual flat in N, while the positive control moves fds by ≈ 3 × (256 − 2·nproc) | Eager part refuted, or the property did not reach node 1 (check `ps -o args`). |
| Positive control flat too | Instruments insensitive; not confirmed. |
| C < 4 (strLoops at 256 small) | Repair streamed too little; increase data or `num_tokens`. Not confirmed, not refuted. |
| Repair fails at N=1 | Not a memory result; note it as a functional effect of a single sendFile loop. |

**B3h. Controls.**
- *Positive control:* `-Dio.netty.eventLoopThreads=256` sizes the CQL worker group (`NativeTransportService.java:69`). This Netty cap is known to bind on the same executor type, so fds and the residual must rise per extra executor.
- *Unbound reference:* N=256 gives C, the thread count with no cap binding.
- *Constant peers:* nodes 2 and 3 are unchanged.
- *Same-time baseline:* T0 precedes all streaming, which separates the eager and lazy parts.

**B4. Risks and cleanup.**
- **Disk:** the build needs about 2 GB in `$SRC/build`. The cluster needs about 1–2 GB under `$WORK`, which must be local disk (`df -T`). Never use the shared source tree.
- **fds:** N=256 adds ~1,500 fds on node 1.
- **Ports:** 7000, 9042 and 7199/7299/7399 on 127.0.0.1–3. Check `ss -ltn` first.
- **Processes:** after each N, `stop 3; stop 2; stop 1`. Also check that no `nodetool repair` or `cassandra-stress` is still running. At the end, `pgrep -af "$WORK/n|InternodeEventThreadsProbeTest|cassandra-stress|NodeTool"` must be empty; kill anything listed.
- **Cleanup:** copy `$OUT` to the results location; `rm -rf $WORK $SRC/build/test`.

## C. Sources read

- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (285, 371, 526, 881-888)
- src/java/org/apache/cassandra/net/SocketFactory.java (60-290)
- src/java/org/apache/cassandra/utils/FBUtilities.java (130-157)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (573-574, 2464, 3796-3805)
- src/java/org/apache/cassandra/config/Config.java (183)
- src/java/org/apache/cassandra/streaming/async/NettyStreamingConnectionFactory.java (40-100)
- src/java/org/apache/cassandra/streaming/async/StreamingMultiplexedChannel.java (90-145, 171, 188, 280-414, 519-521)
- src/java/org/apache/cassandra/streaming/StreamSession.java (198, 268-283, 372)
- src/java/org/apache/cassandra/net/OutboundConnectionInitiator.java (118-139, 188-192, 375-392)
- src/java/org/apache/cassandra/net/InboundConnectionInitiator.java (108, 169, 438-490)
- src/java/org/apache/cassandra/net/AsyncStreamingOutputPlus.java (92, 143)
- src/java/org/apache/cassandra/net/BufferPoolAllocator.java, GlobalBufferPoolAllocator.java, LocalBufferPoolAllocator.java
- src/java/org/apache/cassandra/utils/memory/BufferPool.java (128-300, 380-480, 533-560, 764-920, 1014, 1095-1101, 1636-1650)
- src/java/org/apache/cassandra/utils/memory/BufferPools.java
- src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
- src/java/org/apache/cassandra/service/NativeTransportService.java (60-80, 168-176)
- src/java/org/apache/cassandra/net/MessagingService.java (301, 651-659)
- conf/jvm-server.options (123), conf/cassandra-env.sh (88-160, 228-247, 307), conf/cassandra.yaml (68, 97, 395-431, 611, 706, 960-1090)
- build.xml (136, 225-230, 565-577, 1017, 1153-1192, 1382), .build/parent-pom-template.xml (744-750)
- Netty 4.1 sources (cited from memory, not opened): https://github.com/netty/netty/tree/netty-4.1.130.Final

## D. Stage-4 feedback

none yet
