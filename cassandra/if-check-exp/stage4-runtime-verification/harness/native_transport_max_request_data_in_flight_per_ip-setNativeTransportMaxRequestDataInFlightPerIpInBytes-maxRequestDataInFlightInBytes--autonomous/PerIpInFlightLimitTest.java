package org.apache.cassandra.transport;

import java.net.InetAddress;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import com.google.common.collect.ImmutableList;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.db.virtual.AbstractVirtualTable;
import org.apache.cassandra.db.virtual.SimpleDataSet;
import org.apache.cassandra.db.virtual.VirtualKeyspace;
import org.apache.cassandra.db.virtual.VirtualKeyspaceRegistry;
import org.apache.cassandra.exceptions.OverloadedException;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.transport.messages.ErrorMessage;
import org.apache.cassandra.transport.messages.QueryMessage;

/**
 * Stage-4 unit tier for the per-IP bytes-in-flight limit (case file B2). Prints one "U,..." line per arm.
 * The test asserts only instrument sanity (the gate was released, every request was answered); the verdict is
 * read from the U lines against B2f/B2g.
 */
public class PerIpInFlightLimitTest extends NativeProtocolLimitsTestBase
{
    static final String VK = "pi_vk", VT = "pi_vt";
    static final int PAD = 262_144, C = 4, K = 48;
    static final long MiB = 1L << 20, GLOBAL = 512 * MiB;
    static volatile CountDownLatch gate = new CountDownLatch(1);
    static final AtomicInteger entered = new AtomicInteger();
    static final InetAddress EP = InetAddress.getLoopbackAddress();

    @BeforeClass
    public static void setUp()
    {
        DatabaseDescriptor.setNativeTransportConcurrentRequestDataInFlightInBytes(GLOBAL);
        DatabaseDescriptor.setNativeTransportMaxRequestDataInFlightPerIpInBytes(16 * MiB);
        requireNetwork();
        TableMetadata md = TableMetadata.builder(VK, VT)
                                        .kind(TableMetadata.Kind.VIRTUAL)
                                        .addPartitionKeyColumn("pk", UTF8Type.instance)
                                        .addRegularColumn("v", Int32Type.instance)
                                        .build();
        AbstractVirtualTable t = new AbstractVirtualTable.SimpleTable(md, () -> {
            entered.incrementAndGet();
            try { gate.await(180, TimeUnit.SECONDS); } catch (InterruptedException e) { /* leave */ }
            return new SimpleDataSet(md);
        });
        VirtualKeyspaceRegistry.instance.register(new VirtualKeyspace(VK, ImmutableList.of(t)));
    }

    static QueryOptions qo(ProtocolVersion v)
    {
        return QueryOptions.create(QueryOptions.DEFAULT.getConsistency(), QueryOptions.DEFAULT.getValues(), QueryOptions.DEFAULT.skipMetadata(),
                                   QueryOptions.DEFAULT.getPageSize(), QueryOptions.DEFAULT.getPagingState(), QueryOptions.DEFAULT.getSerialConsistency(),
                                   v, KEYSPACE);
    }

    static String padded(int pad)
    {
        StringBuilder sb = new StringBuilder("SELECT * FROM " + VK + "." + VT + " /* ");
        for (int i = 0; i < pad; i++) sb.append('a');
        return sb.append(" */").toString();
    }

    static ClientResourceLimits.Allocator allocator() { return ClientResourceLimits.getAllocatorForEndpoint(EP); }
    static long using() { return allocator().endpointUsing(); }
    static void signal() { new ClientResourceLimits.ResourceProvider.Default(allocator()).endpointWaitQueue().signal(); }

    interface Mid { void run(R r) throws Exception; }

    static class R
    {
        String arm; ProtocolVersion v; boolean thr; long L; int Q, c, k; long S; int offered;
        int enteredAtPlateau; long plateau, maxUsing, gUsing; long finalUsing; int ok, overloaded, other;
        long afterSetUsing = -1, afterSignalUsing = -1; int afterSetEntered = -1, afterSignalEntered = -1;
        String line()
        {
            StringBuilder sb = new StringBuilder();
            sb.append("U,").append(arm).append(",v=V").append(v.asInt()).append(",thr=").append(thr ? 1 : 0).append(",L=").append(L).append(",Q=").append(Q)
              .append(",C=").append(c).append(",K=").append(k).append(",S=").append(S).append(",offered=").append(offered)
              .append(",entered=").append(enteredAtPlateau).append(",admittedBytes=").append((long) enteredAtPlateau * S)
              .append(",plateau=").append(plateau).append(",globalUsing=").append(gUsing).append(",maxUsing=").append(maxUsing)
              .append(",ok=").append(ok).append(",overloaded=").append(overloaded).append(",other=").append(other).append(",final=").append(finalUsing);
            if (afterSetUsing >= 0)
                sb.append(",afterSetUsing=").append(afterSetUsing).append(",afterSetEntered=").append(afterSetEntered)
                  .append(",afterSignalUsing=").append(afterSignalUsing).append(",afterSignalEntered=").append(afterSignalEntered);
            return sb.toString();
        }
    }

    /** Waits until entered and the endpoint count are unchanged for 500 ms (8 s cap); tracks the maximum count. */
    static void settle(R r) throws Exception
    {
        long last = -1; int lastE = -1; long stableSince = System.nanoTime(); long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(8);
        while (System.nanoTime() < deadline)
        {
            long u = using(); int e = entered.get();
            r.maxUsing = Math.max(r.maxUsing, u);
            if (u != last || e != lastE) { last = u; lastE = e; stableSince = System.nanoTime(); }
            else if (System.nanoTime() - stableSince > TimeUnit.MILLISECONDS.toNanos(500)) break;
            Thread.sleep(20);
        }
    }

    R arm(String name, ProtocolVersion v, boolean thr, long L, int Q, int c, int k, boolean block, long global, Mid mid) throws Exception
    {
        R r = new R(); r.arm = name; r.v = v; r.thr = thr; r.L = L; r.Q = Q; r.c = c; r.k = k;
        DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes(Q);
        ClientResourceLimits.setGlobalLimit(global);
        ClientResourceLimits.setEndpointLimit(L);
        if (L == 0) DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(1 * MiB);   // control c only: the message-size default would be 0 (B2h amendment)
        gate = new CountDownLatch(block ? 1 : 0);
        entered.set(0);
        QueryMessage probe = new QueryMessage(padded(PAD), qo(v));
        r.S = QueryMessage.codec.encodedSize(probe, v);
        r.offered = c * k;
        List<SimpleClient> clients = new ArrayList<>();
        List<Thread> pollers = new ArrayList<>();
        AtomicInteger ok = new AtomicInteger(), ovl = new AtomicInteger(), oth = new AtomicInteger();
        AtomicBoolean stop = new AtomicBoolean();
        for (int i = 0; i < c; i++)
        {
            final SimpleClient cl = SimpleClient.builder(nativeAddr.getHostAddress(), nativePort).protocolVersion(v).useBeta().build().connect(false, thr);
            clients.add(cl);
            Thread p = new Thread(() -> {
                try
                {
                    while (!stop.get())
                    {
                        Message.Response resp = cl.responseHandler.responses.poll(100, TimeUnit.MILLISECONDS);
                        if (resp == null) continue;
                        if (resp instanceof ErrorMessage)
                        {
                            if (((ErrorMessage) resp).error instanceof OverloadedException) ovl.incrementAndGet(); else oth.incrementAndGet();
                        }
                        else ok.incrementAndGet();
                    }
                }
                catch (InterruptedException e) { /* leave */ }
            });
            p.setDaemon(true); p.start(); pollers.add(p);
        }
        ok.set(0); ovl.set(0); oth.set(0);     // the connect handshakes are not counted
        List<Thread> senders = new ArrayList<>();
        for (SimpleClient cl : clients)
        {
            Thread s = new Thread(() -> {
                for (int i = 0; i < k; i++)
                {
                    QueryMessage q = new QueryMessage(padded(PAD), qo(v));
                    q.setSource(new Envelope(Envelope.Header.dummy(i, q.type), null));
                    q.attach(cl.connection);
                    cl.channel.writeAndFlush(Collections.singletonList(q));
                }
            });
            s.setDaemon(true); s.start(); senders.add(s);
        }
        for (Thread s : senders) s.join();
        settle(r);
        r.plateau = using(); r.enteredAtPlateau = entered.get(); r.gUsing = ClientResourceLimits.getCurrentGlobalUsage();
        if (mid != null) mid.run(r);
        gate.countDown();
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(120);
        int expect = L == 0 ? r.enteredAtPlateau : r.offered;     // at L = 0 the refused messages wait for ever
        while (ok.get() + ovl.get() + oth.get() < expect && System.nanoTime() < deadline)
        {
            r.maxUsing = Math.max(r.maxUsing, using());
            Thread.sleep(20);
        }
        Thread.sleep(500);
        r.ok = ok.get(); r.overloaded = ovl.get(); r.other = oth.get();
        r.finalUsing = using();
        stop.set(true);
        for (Thread p : pollers) p.join();
        for (SimpleClient cl : clients) cl.close();
        System.out.println(r.line());
        // instrument sanity only
        org.junit.Assert.assertEquals("every request that can be answered is answered", expect, r.ok + r.overloaded + r.other);
        return r;
    }

    @Test public void uA_v5_default() throws Exception
    {
        for (int Q : new int[]{ (int) MiB, 64 * 1024 })
            for (long L : new long[]{ 1 * MiB, 4 * MiB, 16 * MiB })
                arm("A", ProtocolVersion.V5, false, L, Q, C, K, true, GLOBAL, null);
    }

    @Test public void uB_v5_throw() throws Exception
    {
        arm("B", ProtocolVersion.V5, true, 4 * MiB, (int) MiB, C, K, true, GLOBAL, null);
    }

    @Test public void uC_runtime_change() throws Exception
    {
        arm("C", ProtocolVersion.V5, false, 4 * MiB, (int) MiB, C, K, true, GLOBAL, r -> {
            ClientResourceLimits.setEndpointLimit(8 * MiB);
            Thread.sleep(1000);
            r.afterSetUsing = using(); r.afterSetEntered = entered.get();
            signal();
            settle(r);
            r.afterSignalUsing = using(); r.afterSignalEntered = entered.get();
        });
    }

    @Test public void uD_v4() throws Exception
    {
        arm("D", ProtocolVersion.V4, false, 4 * MiB, (int) MiB, C, K, true, GLOBAL, null);
        arm("E", ProtocolVersion.V4, true, 4 * MiB, (int) MiB, C, K, true, GLOBAL, null);
    }

    /** Instrument check (step 1), not a reading: a limit that cannot bind (1 GiB), two clients, 4 messages each; every message is admitted and counted beyond the queues. */
    @Test public void uZ_instrument_check() throws Exception
    {
        arm("Z", ProtocolVersion.V5, false, 1024 * MiB, (int) MiB, 2, 4, true, GLOBAL, null);
    }

    @Test public void uS_sentinel() throws Exception
    {
        DatabaseDescriptor.setNativeTransportMaxRequestDataInFlightPerIpInBytes(-1);
        System.out.println("U,S,limit=" + ClientResourceLimits.getEndpointLimit() + ",maxMemoryOver40=" + (Runtime.getRuntime().maxMemory() / 40));
        ClientResourceLimits.setEndpointLimit(16 * MiB);
    }

    @Test public void uX_controls() throws Exception
    {
        // (a) global low, per-IP high: the plateau must follow the global limit
        arm("Xa", ProtocolVersion.V5, false, 512 * MiB, (int) MiB, C, K, true, 1 * MiB, null);
        // (b) handler not blocked, small offered load: usage must return to 0 and stay below the cap
        arm("Xb", ProtocolVersion.V5, false, 16 * MiB, (int) MiB, C, 8, false, GLOBAL, null);
        // (c) L = 0 with the message-size invariant overridden: nothing beyond the queues is admitted
        arm("Xc", ProtocolVersion.V5, false, 0, (int) MiB, C, 16, true, GLOBAL, null);
        ClientResourceLimits.setEndpointLimit(16 * MiB);
    }
}
