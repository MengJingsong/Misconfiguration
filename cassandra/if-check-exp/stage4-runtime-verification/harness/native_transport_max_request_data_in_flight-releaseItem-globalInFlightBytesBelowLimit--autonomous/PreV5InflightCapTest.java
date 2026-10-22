package org.apache.cassandra.transport;

import java.lang.reflect.Field;
import java.net.InetAddress;
import java.util.*;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import io.netty.channel.Channel;
import io.netty.channel.embedded.EmbeddedChannel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.metrics.ClientMetrics;
import org.apache.cassandra.transport.messages.ErrorMessage;
import org.apache.cassandra.transport.messages.QueryMessage;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.FBUtilities;

public class PreV5InflightCapTest
{
    static final long S = 100_000;
    static InetAddress EP;

    static final class Held { Channel ch; Message.Request req; Dispatcher.FlushItemConverter<Object> conv; Object param; }

    static final class HoldingDispatcher extends Dispatcher
    {
        final Deque<Held> held = new ArrayDeque<>();
        HoldingDispatcher() { super(false); }
        @Override @SuppressWarnings("unchecked")
        public <P> void dispatch(Channel channel, Message.Request request, FlushItemConverter<P> f, P param, ClientResourceLimits.Overload bp)
        { Held h = new Held(); h.ch = channel; h.req = request; h.conv = (FlushItemConverter<Object>) f; h.param = param; held.add(h); }
        @Override public boolean hasQueueCapacity() { return true; }
        void complete(Held h) { h.conv.toFlushItem(h.param, h.ch, h.req, new ResultMessage.Void()).release(); }
    }

    static final class Conn { EmbeddedChannel ch; Connection c; HoldingDispatcher d = new HoldingDispatcher(); LegacyHandlerRef h; }
    static final class LegacyHandlerRef { PreV5Handlers.LegacyDispatchHandler h; }

    @BeforeClass
    public static void init() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        ClientMetrics.instance.init(Collections.emptyList());
        EP = FBUtilities.getJustLocalAddress();
    }

    static Conn open(boolean throwOnOverload)
    {
        Conn k = new Conn();
        k.h = new LegacyHandlerRef();
        k.h.h = new PreV5Handlers.LegacyDispatchHandler(k.d, QueueBackpressure.NO_OP, ClientResourceLimits.getAllocatorForEndpoint(EP));
        k.ch = new EmbeddedChannel(k.h.h);
        k.c = new Connection(k.ch, ProtocolVersion.V4, new Connection.Tracker() {
            public void addConnection(Channel ch, Connection c) {}
            public boolean isRunning() { return true; } });
        k.c.setThrowOnOverload(throwOnOverload);
        return k;
    }

    static int stream = 1;
    /** returns true if admitted, false if rejected with OverloadedException */
    static boolean send(Conn k)
    {
        ByteBuf frame = Unpooled.buffer((int) (9 + S));
        frame.writeByte(0x04).writeByte(0).writeShort(stream++ & 0x7fff).writeByte(0x07).writeInt((int) S);
        frame.writeZero((int) S);
        Envelope env = new Envelope.Decoder().decode(frame);
        frame.release();                       // env.body (retained slice) keeps it alive
        QueryMessage q = new QueryMessage("SELECT 1", QueryOptions.DEFAULT);
        q.setSource(env); q.attach(k.c);
        try { k.ch.writeInbound(q); return true; }
        catch (ErrorMessage.WrappedException e) { return false; }
    }

    static long chanInFlight(Conn k) throws Exception
    { Field f = PreV5Handlers.LegacyDispatchHandler.class.getDeclaredField("channelPayloadBytesInFlight"); f.setAccessible(true); return f.getLong(k.h.h); }

    static void limits(long L) { ClientResourceLimits.setGlobalLimit(L); ClientResourceLimits.setEndpointLimit(L); }
    static long g() { return ClientResourceLimits.getCurrentGlobalUsage(); }
    static void drain(Conn k) { while (!k.d.held.isEmpty()) k.d.complete(k.d.held.poll()); }

    @Test public void uA_sweep() throws Exception
    {
        for (long L : new long[]{ 1_000_000, 4_000_000, 16_000_000 })
        {
            limits(L); Conn k = open(false); int n = 0;
            while (k.ch.config().isAutoRead() && n < 10_000) { send(k); n++; }
            long peak = g();
            int completedAtUnpause = -1, i = 0;
            while (!k.d.held.isEmpty()) { k.d.complete(k.d.held.poll()); i++; if (completedAtUnpause < 0 && k.ch.config().isAutoRead()) completedAtUnpause = i; }
            System.out.println("U,A,L=" + L + ",admitted=" + n + ",peak=" + peak + ",unpausedAfterCompletions=" + completedAtUnpause + ",final=" + g());
            k.ch.close();
        }
    }

    @Test public void uB_connections() throws Exception
    {
        long L = 1_000_000;
        for (int C : new int[]{ 1, 8, 64 })
        {
            limits(L);
            Conn a = open(false); while (a.ch.config().isAutoRead()) send(a);     // saturate: usage = L + S
            List<Conn> bs = new ArrayList<>();
            for (int j = 0; j < C; j++) { Conn b = open(false); send(b); bs.add(b); }
            long peak = g(); int paused = 0; for (Conn b : bs) if (!b.ch.config().isAutoRead()) paused++;
            // cycle: each B completes its only request -> line 127 unpauses it although global >= L -> it sends again
            long maxDuringCycles = peak; boolean unpausedAboveLimit = false;
            for (int r = 0; r < 100; r++) for (Conn b : bs)
            {
                b.d.complete(b.d.held.poll());
                if (b.ch.config().isAutoRead() && g() >= L) unpausedAboveLimit = true;
                send(b); maxDuringCycles = Math.max(maxDuringCycles, g());
            }
            System.out.println("U,B,L=" + L + ",C=" + C + ",peak=" + peak + ",pausedB=" + paused + ",maxDuring100Cycles=" + maxDuringCycles + ",unpausedWhileGlobalAboveLimit=" + unpausedAboveLimit);
            drain(a); for (Conn b : bs) { drain(b); b.ch.close(); } a.ch.close();
            System.out.println("U,B,afterDrain=" + g());
        }
    }

    @Test public void uC_ignorePause() throws Exception
    {
        limits(1_000_000); Conn k = open(false);
        for (int n = 0; n < 50; n++) send(k);          // frames already decoded in one read batch
        System.out.println("U,C,L=1000000,sent=50,usage=" + g() + ",chan=" + chanInFlight(k) + ",autoRead=" + k.ch.config().isAutoRead());
        drain(k); k.ch.close();
    }

    @Test public void uD_throwOnOverload_control() throws Exception
    {
        limits(1_000_000); Conn k = open(true); int ok = 0, rej = 0; long max = 0;
        for (int n = 0; n < 20; n++) { if (send(k)) ok++; else rej++; max = Math.max(max, g()); }
        System.out.println("U,D,L=1000000,admitted=" + ok + ",rejected=" + rej + ",maxUsage=" + max);
        drain(k); k.ch.close();
    }

    @Test public void uE_unlimited_control() throws Exception
    {
        limits(1_000_000_000_000L); Conn k = open(false);
        for (int n = 0; n < 200; n++) send(k);
        System.out.println("U,E,L=1e12,sent=200,usage=" + g() + ",autoRead=" + k.ch.config().isAutoRead());
        drain(k); k.ch.close();
    }
}
