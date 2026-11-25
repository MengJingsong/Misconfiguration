package org.apache.cassandra.transport;

// Stage-4 harness for case native-write-buffer-water-mark-initializechannel-pendingoutboundbytes--autonomous (o133).
// Verbatim B2a test, with the audit amendments of 2026-11-25 (case file section D):
//   S4-A2: the positive-control gate pauses reads with setAutoRead(isWritable()) ("wm.gate=autoread").
//          The as-filed gate (swallows read(); "wm.gate=read", or legacy -Dwm.gate=true) is kept as a diagnostic only:
//          with autoRead on, Netty's NIO read loop keeps OP_READ registered and never consults read().
//   D1:    the configurator uses the server's epoll choice (runbook defect found in the shakedown).
//   S4-A1: the WMRESULT line also echoes the channel's configured marks, the gate mode, the pipeline names and autoRead,
//          and is printed to stdout and stderr (both land in the junit XML and the console log).

import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.channel.*;
import org.apache.cassandra.config.EncryptionOptions;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.metrics.ClientMessageSizeMetrics;

public class WriteWaterMarkBacklogTest extends CQLTester
{
    static final List<Channel> CHANNELS = new CopyOnWriteArrayList<>();
    static int HIGH;  static String GATE;  static int SNDBUF;

    static class ProbeConfigurator extends PipelineConfigurator
    {
        // D1 (2026-11-25): match the server's transport (Server.java:107); epoll=false fails to bind on an epoll worker group
        ProbeConfigurator() { super(org.apache.cassandra.service.NativeTransportService.useEpoll(), false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED); }

        @Override
        protected void onInitialPipelineReady(ChannelPipeline p)
        {
            Channel ch = p.channel();
            ch.config().setOption(ChannelOption.SO_SNDBUF, SNDBUF);            // shrink kernel slack
            if (HIGH != 32 * 1024)                                              // knob: vary the constraint
                ch.config().setWriteBufferWaterMark(new WriteBufferWaterMark(HIGH / 4, HIGH));
            if ("read".equals(GATE))                                            // as filed (diagnostic only, S4-A2)
                p.addFirst("wm-gate", new ChannelDuplexHandler()
                {
                    boolean held;
                    @Override public void read(ChannelHandlerContext ctx)
                    { if (ctx.channel().isWritable()) ctx.read(); else held = true; }
                    @Override public void channelWritabilityChanged(ChannelHandlerContext ctx)
                    { if (ctx.channel().isWritable() && held) { held = false; ctx.read(); } ctx.fireChannelWritabilityChanged(); }
                });
            else if ("autoread".equals(GATE))                                   // S4-A2: a consumer of writability that binds
                p.addFirst("wm-gate", new ChannelInboundHandlerAdapter()
                {
                    @Override public void channelWritabilityChanged(ChannelHandlerContext ctx)
                    { ctx.channel().config().setAutoRead(ctx.channel().isWritable()); ctx.fireChannelWritabilityChanged(); }
                });
            CHANNELS.add(ch);
        }
    }

    @BeforeClass
    public static void setUpNet()
    {
        HIGH = Integer.getInteger("wm.high", 32 * 1024);
        String g = System.getProperty("wm.gate", "none");
        GATE = "true".equals(g) ? "read" : ("false".equals(g) ? "none" : g);
        SNDBUF = Integer.getInteger("wm.sndbuf", 16 * 1024);
        requireNetwork(b -> b.withPipelineConfigurator(new ProbeConfigurator()), c -> {});
    }

    static byte[] frame(int stream, int op, byte[] body)
    {
        ByteBuffer b = ByteBuffer.allocate(9 + body.length);
        b.put((byte) 0x04).put((byte) 0).putShort((short) stream).put((byte) op).putInt(body.length).put(body);
        return b.array();
    }
    static void str(DataOutputStream d, String s) throws IOException
    { byte[] x = s.getBytes(StandardCharsets.UTF_8); d.writeShort(x.length); d.write(x); }
    static byte[] startup() throws IOException
    { ByteArrayOutputStream o = new ByteArrayOutputStream(); DataOutputStream d = new DataOutputStream(o);
      d.writeShort(1); str(d, "CQL_VERSION"); str(d, "3.0.0"); return o.toByteArray(); }
    static byte[] query(String q) throws IOException
    { ByteArrayOutputStream o = new ByteArrayOutputStream(); DataOutputStream d = new DataOutputStream(o);
      byte[] x = q.getBytes(StandardCharsets.UTF_8); d.writeInt(x.length); d.write(x); d.writeShort(1); d.writeByte(0);
      return o.toByteArray(); }
    static int readFrame(DataInputStream in) throws IOException   // returns total bytes of one frame
    { byte[] h = new byte[9]; in.readFully(h); int len = ByteBuffer.wrap(h, 5, 4).getInt();
      in.readFully(new byte[len]); return 9 + len; }

    @Test
    public void backlog() throws Throwable
    {
        int B = Integer.getInteger("wm.blob", 64 * 1024);
        int K = Integer.getInteger("wm.k", 256);
        boolean clientReads = Boolean.getBoolean("wm.clientReads");
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob)");
        execute("INSERT INTO %s (k, v) VALUES (0, ?)", ByteBuffer.allocate(B));
        String q = formatQuery("SELECT v FROM %s WHERE k = 0");

        try (Socket s = new Socket())
        {
            s.setReceiveBufferSize(4096);
            s.connect(new InetSocketAddress(nativeAddr, nativePort));
            OutputStream out = s.getOutputStream();
            DataInputStream in = new DataInputStream(new BufferedInputStream(s.getInputStream()));
            out.write(frame(0, 0x01, startup())); out.flush();
            readFrame(in);                                             // READY
            Channel ch = CHANNELS.stream()
                                 .filter(c -> ((InetSocketAddress) c.remoteAddress()).getPort() == s.getLocalPort())
                                 .findFirst().get();
            AtomicLong clientBytes = new AtomicLong();
            Thread reader = null;
            if (clientReads)
            {
                reader = new Thread(() -> { try { for (int i = 0; i < K; i++) clientBytes.addAndGet(readFrame(in)); } catch (IOException e) {} });
                reader.start();
            }
            long sent0 = ClientMessageSizeMetrics.bytesSent.getCount();
            long max = 0;
            for (int i = 0; i < K; i++)
            {
                out.write(frame(i % 32768, 0x07, query(q))); out.flush();
                Thread.sleep(10);                                       // 100 requests/s trickle
                max = Math.max(max, pending(ch));
            }
            long last = -1; int stable = 0; long deadline = System.currentTimeMillis() + 30_000;
            while (stable < 20 && System.currentTimeMillis() < deadline)  // settle: 20 equal samples 100 ms apart
            {
                Thread.sleep(100);
                long p = pending(ch); max = Math.max(max, p);
                stable = (p == last) ? stable + 1 : 0; last = p;
            }
            long produced = ClientMessageSizeMetrics.bytesSent.getCount() - sent0;
            String line = String.format("WMRESULT high=%d gate=%s sndbuf=%d B=%d K=%d clientReads=%b produced=%d R=%d " +
                              "pendingMax=%d pendingSettled=%d writable=%b bytesBeforeUnwritable=%d clientBytes=%d " +
                              "cfgHigh=%d cfgLow=%d autoRead=%b stable=%d open=%b pipeline=%s",
                              HIGH, GATE, SNDBUF, B, K, clientReads, produced, K == 0 ? 0 : produced / K,
                              max, last, ch.isWritable(), ch.bytesBeforeUnwritable(), clientBytes.get(),
                              ch.config().getWriteBufferHighWaterMark(), ch.config().getWriteBufferLowWaterMark(),
                              ch.config().isAutoRead(), stable, ch.isOpen(), ch.pipeline().names());
            System.out.println(line);
            System.err.println(line);
            if (reader != null) reader.join(30_000);
        }
    }

    static long pending(Channel ch)
    {
        ChannelOutboundBuffer b = ch.unsafe().outboundBuffer();
        return b == null ? -1 : b.totalPendingWriteBytes();
    }
}
