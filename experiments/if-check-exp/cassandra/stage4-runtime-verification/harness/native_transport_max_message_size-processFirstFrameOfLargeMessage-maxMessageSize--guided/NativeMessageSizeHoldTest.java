/*
 * Stage-4 harness, unit tier, for native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided
 * (case 9a Procedure 1; frozen 9 hash 14c3b5fd...). Copy into test/unit/org/apache/cassandra/transport/ of a
 * cassandra-5.0.9 clone (unit-run.sh does it).
 *
 * One in-process server (CQLTester). A raw protocol-v5 client on a plain socket (no SimpleClient: it cannot stop
 * before a message's last frame): STARTUP and READY unframed, then CRC frames written by hand (the FrameEncoderCrc
 * layout: 3-byte little-endian header = payload length | selfContained << 17, its CRC24, the payload, the payload's
 * CRC32 with Crc.crc32()'s initial bytes, little-endian). Each request is a QUERY "SELECT pk FROM <t> WHERE pk = 0 AND
 * v = ? ALLOW FILTERING" with one blob bound value sized so the envelope body is exactly the target; the read touches no
 * disk and is unaffected by the unit yaml's small max_mutation_size. Every frame but the last is sent, the server's
 * CQLMessageHandler for the connection is found through CQLTester.server's ConnectionTracker, and the state of its
 * LargeMessage is read on its event loop once it has received every byte sent: tooBig, the number of buffers kept and
 * their bytes. Then the last frame is sent and the response read.
 *
 * Steps: control (one 64 KiB single-frame request); then for each limit L in 1, 4, 16 MiB (set live with
 * DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes, after the in-flight limits, which would reset it):
 * bodies L + 1, L, L - 1 and the cluster tier's request (blob 8 MiB), then a 64 KiB request on the same connection.
 * Readings are printed as
 *   STAGE4 reading step=<s> limit=<L> body=<B> frames=<n> sent_frames=<k> lm=<0|1> toobig=<t> buffers=<b>
 *       buffer_bytes=<x> received=<r> discarded_delta=<d> pool_size_delta=<p> pool_overflow_delta=<o>
 *       resp_opcode=<op> resp_code=<c> resp_msg=<m>
 * and judged by unit-run.sh's summary and the results file, not here. The test asserts only instrument and set-up
 * conditions (STAGE4 check ... ok|MISMATCH): the handler is found, the hold is reached, a response arrives for every
 * request; it fails at the end if any check mismatched.
 */
package org.apache.cassandra.transport;

import java.io.BufferedInputStream;
import java.io.DataInputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketAddress;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.zip.CRC32;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import com.codahale.metrics.Meter;
import io.netty.channel.Channel;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.metrics.ClientMetrics;
import org.apache.cassandra.net.AbstractMessageHandler;
import org.apache.cassandra.net.Crc;
import org.apache.cassandra.net.ShareableBytes;
import org.apache.cassandra.transport.messages.QueryMessage;
import org.apache.cassandra.transport.messages.StartupMessage;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;

public class NativeMessageSizeHoldTest extends NativeProtocolLimitsTestBase
{
    static final int KiB = 1024, MiB = 1 << 20;
    static final int MAX_PAYLOAD = (1 << 17) - 1;       // 131,071: the largest frame payload (17-bit length)
    static final int BLOB_8M = 8 * MiB;

    // ---------------------------------------------------------------- output

    private static PrintWriter out;
    private static int checks, mismatches;

    private static void say(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    private static void check(String name, boolean cond, String detail)
    {
        checks++;
        if (!cond) mismatches++;
        say("STAGE4 check " + name + " " + detail + (cond ? " ok" : " MISMATCH"));
    }

    @BeforeClass
    public static void setUp() throws IOException
    {
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true));
        requireNetwork();
    }

    @AfterClass
    public static void tearDown()
    {
        say("STAGE4 summary checks=" + checks + " mismatches=" + mismatches);
        if (out != null) out.close();
    }

    // ---------------------------------------------------------------- the raw v5 client

    static int crc24(long bytes, int len)      // Crc.crc24 (package-private there), the same naive algorithm
    {
        int crc = 0x875060;
        while (len-- > 0)
        {
            crc ^= (bytes & 0xff) << 16;
            bytes >>= 8;
            for (int i = 0; i < 8; i++)
            {
                crc <<= 1;
                if ((crc & 0x1000000) != 0)
                    crc ^= 0x1974F0B;
            }
        }
        return crc;
    }

    static void put3b(ByteBuffer b, int v)
    {
        b.put((byte) (v & 0xff)); b.put((byte) ((v >>> 8) & 0xff)); b.put((byte) ((v >>> 16) & 0xff));
    }

    static byte[] frame(byte[] data, int off, int len, boolean selfContained)
    {
        ByteBuffer f = ByteBuffer.allocate(6 + len + 4).order(ByteOrder.LITTLE_ENDIAN);
        int h = len | (selfContained ? 1 << 17 : 0);
        put3b(f, h);
        put3b(f, crc24(h, 3));
        f.put(data, off, len);
        CRC32 c = Crc.crc32();
        c.update(data, off, len);
        f.putInt((int) c.getValue());
        return f.array();
    }

    static byte[] envelopeBytes(Message.Request m, int stream)
    {
        Envelope e = m.encode(ProtocolVersion.V5, stream);
        try
        {
            ByteBuffer bb = ByteBuffer.allocate(Envelope.Header.LENGTH + e.body.readableBytes());
            e.encodeInto(bb);
            return bb.array();
        }
        finally
        {
            e.release();
        }
    }

    static final class Resp
    {
        int opcode, code = -1;
        String msg = "";
        public String toString() { return "resp_opcode=" + opcode + " resp_code=" + code + " resp_msg=" + msg.replace(' ', '_'); }
    }

    static final class RawV5 implements AutoCloseable
    {
        final Socket s;
        final DataInputStream in;
        final OutputStream os;
        int stream = 1;

        RawV5(java.net.InetAddress addr, int port) throws IOException
        {
            s = new Socket(addr, port);
            s.setTcpNoDelay(true);
            s.setSoTimeout(60_000);
            in = new DataInputStream(new BufferedInputStream(s.getInputStream()));
            os = s.getOutputStream();
            os.write(envelopeBytes(new StartupMessage(Collections.singletonMap(StartupMessage.CQL_VERSION, "3.0.0")), 0));
            os.flush();
            byte[] h = new byte[9];
            in.readFully(h);
            int len = ByteBuffer.wrap(h, 5, 4).getInt();
            in.readFully(new byte[len]);
            if (h[4] != 0x02)
                throw new IOException("expected READY, got opcode " + h[4]);
        }

        SocketAddress local() { return s.getLocalSocketAddress(); }

        /** Splits the envelope into frames as the drivers do (131,071-byte payloads; one self-contained frame if it fits). */
        static java.util.List<byte[]> frames(byte[] env)
        {
            java.util.List<byte[]> l = new java.util.ArrayList<>();
            if (env.length <= MAX_PAYLOAD)
                l.add(frame(env, 0, env.length, true));
            else
                for (int off = 0; off < env.length; off += MAX_PAYLOAD)
                    l.add(frame(env, off, Math.min(MAX_PAYLOAD, env.length - off), false));
            return l;
        }

        void write(byte[] b) throws IOException { os.write(b); os.flush(); }

        Resp read() throws IOException
        {
            byte[] h = new byte[6];
            in.readFully(h);
            int hdr = (h[0] & 0xff) | ((h[1] & 0xff) << 8) | ((h[2] & 0xff) << 16);
            int len = hdr & 0x1FFFF;
            byte[] p = new byte[len];
            in.readFully(p);
            in.readFully(new byte[4]);
            ByteBuffer b = ByteBuffer.wrap(p);
            Resp r = new Resp();
            b.position(4);
            r.opcode = b.get() & 0xff;
            int blen = b.getInt();
            if (r.opcode == 0x00 && blen >= 6)
            {
                r.code = b.getInt();
                int sl = b.getShort() & 0xffff;
                byte[] sb = new byte[sl];
                b.get(sb);
                r.msg = new String(sb, StandardCharsets.UTF_8);
            }
            else if (r.opcode == 0x08)
                r.code = b.getInt();              // the RESULT kind
            return r;
        }

        public void close() throws IOException { s.close(); }
    }

    // ---------------------------------------------------------------- the server's handler

    @SuppressWarnings("unchecked")
    private static CQLMessageHandler<Message.Request> serverHandler(SocketAddress local) throws Exception
    {
        Server server = (Server) field(CQLTester.class, "server").get(null);
        Server.ConnectionTracker tracker = (Server.ConnectionTracker) field(Server.class, "connectionTracker").get(server);
        for (int attempt = 0; attempt < 100; attempt++)
        {
            for (Channel ch : tracker.allChannels)
                if (local.equals(ch.remoteAddress()) && ch.pipeline().get("cqlProcessor") != null)
                    return (CQLMessageHandler<Message.Request>) ch.pipeline().get("cqlProcessor");
            Thread.sleep(50);
        }
        return null;
    }

    private static Field field(Class<?> c, String name) throws NoSuchFieldException
    {
        Field f = c.getDeclaredField(name);
        f.setAccessible(true);
        return f;
    }

    /** [lm present, toobig, buffers, buffer bytes, received], read on the handler's event loop. */
    private static long[] largeState(CQLMessageHandler<?> h) throws Exception
    {
        Channel ch = (Channel) field(AbstractMessageHandler.class, "channel").get(h);
        Field lmF = field(AbstractMessageHandler.class, "largeMessage");
        Class<?> base = Class.forName("org.apache.cassandra.net.AbstractMessageHandler$LargeMessage");
        Class<?> cql = Class.forName("org.apache.cassandra.transport.CQLMessageHandler$LargeMessage");
        Field bufF = field(base, "buffers"), recF = field(base, "received"), tooF = field(cql, "tooBig");
        return ch.eventLoop().submit(() -> {
            Object lm = lmF.get(h);
            if (lm == null)
                return new long[]{ 0, 0, 0, 0, 0 };
            List<?> bufs = (List<?>) bufF.get(lm);
            long bytes = 0;
            for (Object o : bufs)
                bytes += ((ShareableBytes) o).get().remaining();
            return new long[]{ 1, tooF.getBoolean(lm) ? 1 : 0, bufs.size(), bytes, recF.getInt(lm) };
        }).get(10, TimeUnit.SECONDS);
    }

    private static long discarded() throws Exception
    {
        return ((Meter) field(ClientMetrics.class, "requestDiscarded").get(ClientMetrics.instance)).getCount();
    }

    // ---------------------------------------------------------------- requests

    private String select;

    private QueryMessage request(int blob)
    {
        QueryOptions o = QueryOptions.create(ConsistencyLevel.ONE, Collections.singletonList(ByteBuffer.allocate(blob)), false, -1,
                                             null, null, ProtocolVersion.V5, null);
        return new QueryMessage(select, o);
    }

    private int bodySize(int blob)
    {
        Envelope e = request(blob).encode(ProtocolVersion.V5, 1);
        try { return e.body.readableBytes(); } finally { e.release(); }
    }

    /** One request: every frame but the last, read the server's state, then the last frame and the response. */
    private void one(RawV5 c, CQLMessageHandler<?> h, String step, long limit, int body) throws Exception
    {
        int blob = body - bodySize(0);
        byte[] env = envelopeBytes(request(blob), c.stream++);
        int realBody = env.length - Envelope.Header.LENGTH;
        List<byte[]> frames = RawV5.frames(env);
        BufferPool pool = BufferPools.forNetworking();
        long pool0 = pool.sizeInBytes(), ovf0 = pool.overflowMemoryInBytes(), d0 = discarded();
        long sentPayload = 0;
        for (int i = 0; i < frames.size() - 1; i++)
        {
            c.write(frames.get(i));
            sentPayload += frames.get(i).length - 10;
        }
        long[] st = largeState(h);
        if (frames.size() > 1)
        {
            for (int i = 0; i < 400 && (st[0] == 0 || st[4] != sentPayload); i++)
            {
                Thread.sleep(25);
                st = largeState(h);
            }
            check(step + "-hold", st[0] == 1 && st[4] == sentPayload,
                  "lm=" + st[0] + " received=" + st[4] + " sent=" + sentPayload);
        }
        long pool1 = pool.sizeInBytes(), ovf1 = pool.overflowMemoryInBytes(), d1 = discarded();
        c.write(frames.get(frames.size() - 1));
        Resp r;
        try { r = c.read(); }
        catch (IOException e) { r = new Resp(); r.opcode = -1; r.msg = e.toString(); }
        check(step + "-response", r.opcode >= 0, r.toString());
        say("STAGE4 reading step=" + step + " limit=" + limit + " body=" + realBody + " frames=" + frames.size() + " sent_frames="
            + (frames.size() - 1) + " lm=" + st[0] + " toobig=" + st[1] + " buffers=" + st[2] + " buffer_bytes=" + st[3]
            + " received=" + st[4] + " discarded_delta=" + (d1 - d0) + " pool_size_delta=" + (pool1 - pool0)
            + " pool_overflow_delta=" + (ovf1 - ovf0) + " " + r);
    }

    @Test
    public void largeRequestRetention() throws Throwable
    {
        // 9b hold fixed: in-flight limits 256 MiB (they reset the knob, so they come first), queue capacity 128 MiB, default mode
        DatabaseDescriptor.setNativeTransportThrowOnOverload(false);
        DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes(128 * MiB);
        ClientResourceLimits.setGlobalLimit(256L * MiB);
        ClientResourceLimits.setEndpointLimit(256L * MiB);
        createTable("CREATE TABLE %s (pk int PRIMARY KEY, v blob)");
        select = "SELECT pk FROM " + KEYSPACE + '.' + currentTable() + " WHERE pk = 0 AND v = ? ALLOW FILTERING";
        say("STAGE4 info queue_capacity=" + DatabaseDescriptor.getNativeTransportReceiveQueueCapacityInBytes()
            + " inflight=" + DatabaseDescriptor.getNativeTransportMaxRequestDataInFlightInBytes()
            + " inflight_per_ip=" + DatabaseDescriptor.getNativeTransportMaxRequestDataInFlightPerIpInBytes()
            + " body(0)=" + bodySize(0) + " large_threshold=" + CQLMessageHandler.LARGE_MESSAGE_THRESHOLD);

        try (RawV5 c = new RawV5(nativeAddr, nativePort))
        {
            CQLMessageHandler<Message.Request> h = serverHandler(c.local());
            check("handler", h != null, "local=" + c.local());
            Assert.assertNotNull(h);
            check("mode", !field(CQLMessageHandler.class, "throwOnOverload").getBoolean(h), "throwOnOverload=false");
            check("queue-capacity", field(AbstractMessageHandler.class, "queueCapacity").getLong(h) == 128L * MiB,
                  "queueCapacity=" + field(AbstractMessageHandler.class, "queueCapacity").getLong(h));

            DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(16L * MiB);
            one(c, h, "control-64k", 16L * MiB, 64 * KiB);

            for (int lm : new int[]{ 1, 4, 16 })
            {
                long L = (long) lm * MiB;
                DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(L);
                check("knob-" + lm + "m", DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes() == L,
                      "read back " + DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
                one(c, h, "L" + lm + "m-above", L, (int) L + 1);
                one(c, h, "L" + lm + "m-at", L, (int) L);
                one(c, h, "L" + lm + "m-below", L, (int) L - 1);
                one(c, h, "L" + lm + "m-req8m", L, bodySize(BLOB_8M));
                one(c, h, "L" + lm + "m-after-64k", L, 64 * KiB);
            }
        }
        DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(16L * MiB);
        Assert.assertEquals("instrument or set-up checks mismatched (see STAGE4 check lines)", 0, mismatches);
    }
}
