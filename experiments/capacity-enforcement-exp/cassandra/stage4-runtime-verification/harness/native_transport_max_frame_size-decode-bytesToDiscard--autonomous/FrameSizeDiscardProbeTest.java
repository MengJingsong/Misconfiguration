/*
 * Stage-4 unit tier (B2, amendments U1-U8 of 2026-10-27) of
 * native_transport_max_frame_size-decode-bytesToDiscard--autonomous.
 * Copied into test/unit/org/apache/cassandra/transport/ of the run clone only for the run.
 * Prints one CONFIG line per JVM and one PROBE line per decode call; asserts nothing about the predictions
 * (the readings are judged by the self-check script from the PROBE lines).
 *
 * -Dprobe.mfs=<4MiB|8MiB|16MiB>          the knob (required)
 * -Dprobe.L=<bytes>                       MAIN body length (default 8388608)
 * -Dprobe.ctrlL=<bytes>                   CTRL body length (default 1048576)
 * -Dprobe.subruns=<list>                  default: 4MiB -> MAIN,CTRL1M,C436; 8MiB -> MAIN,EDGE; else MAIN
 */
package org.apache.cassandra.transport;

import java.lang.reflect.Field;

import org.junit.BeforeClass;
import org.junit.Test;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.transport.messages.ErrorMessage;

public class FrameSizeDiscardProbeTest
{
    static String mfs;
    static final int CHUNK = 65536;

    @BeforeClass
    public static void setUp()
    {
        mfs = System.getProperty("probe.mfs");
        if (mfs == null)
            throw new IllegalStateException("probe.mfs not set");
        DatabaseDescriptor.daemonInitialization(() -> {
            Config c = DatabaseDescriptor.loadConfig();
            c.native_transport_max_frame_size = new DataStorageSpec.IntMebibytesBound(mfs);
            return c;
        });
    }

    static Object field(Object o, Class<?> k, String name) throws Exception
    {
        Field f = k.getDeclaredField(name);
        f.setAccessible(true);
        return f.get(o);
    }

    static byte[] header(long L)
    {
        return new byte[]{ 0x04, 0x00, 0x00, 0x01, 0x05,
                           (byte) (L >>> 24), (byte) (L >>> 16), (byte) (L >>> 8), (byte) L };
    }

    void call(String sub, int idx, Envelope.Decoder d, ByteBuf buf, byte[] feed) throws Exception
    {
        buf.writeBytes(feed);
        int before = buf.readableBytes();
        String outcome;
        int after;
        try
        {
            Envelope e = d.decode(buf);
            after = buf.readableBytes();
            if (e == null)
                outcome = "null";
            else
            {
                outcome = "ENVELOPE(" + e.header.type + "," + e.header.streamId + "," + e.header.bodySizeInBytes + ")";
                e.release();
            }
        }
        catch (ErrorMessage.WrappedException w)
        {
            after = buf.readableBytes();
            outcome = "WRAPPED(" + w.getStreamId() + "," + w.getCause().getMessage() + ")";
        }
        buf.discardReadBytes();
        long btd = (Long) field(d, Envelope.Decoder.class, "bytesToDiscard");
        boolean disc = (Boolean) field(d, Envelope.Decoder.class, "discardingTooLongMessage");
        System.out.println("PROBE," + mfs + "," + sub + "," + idx + "," + feed.length + "," + before + "," + after + ","
                           + buf.capacity() + "," + btd + "," + disc + "," + outcome);
    }

    void stream(String sub, long L) throws Exception
    {
        Envelope.Decoder d = new Envelope.Decoder();
        ByteBuf buf = Unpooled.buffer();
        int idx = 0;
        call(sub, idx++, d, buf, header(L));
        long left = L - 1;
        while (left > 0)
        {
            int n = (int) Math.min(CHUNK, left);
            call(sub, idx++, d, buf, new byte[n]);
            left -= n;
        }
        call(sub, idx, d, buf, new byte[1]);
        buf.release();
    }

    void whole(String sub, long L) throws Exception
    {
        Envelope.Decoder d = new Envelope.Decoder();
        ByteBuf buf = Unpooled.buffer();
        byte[] all = new byte[(int) (L + 9)];
        System.arraycopy(header(L), 0, all, 0, 9);
        call(sub, 0, d, buf, all);
        buf.release();
    }

    @Test
    public void probe() throws Exception
    {
        int max = (Integer) field(null, Envelope.Decoder.class, "MAX_TOTAL_LENGTH");
        System.out.println("CONFIG," + mfs + "," + DatabaseDescriptor.getNativeTransportMaxFrameSize() + "," + max);
        long L = Long.parseLong(System.getProperty("probe.L", "8388608"));
        long ctrlL = Long.parseLong(System.getProperty("probe.ctrlL", "1048576"));
        String def = mfs.equals("4MiB") ? "MAIN,CTRL1M,C436" : mfs.equals("8MiB") ? "MAIN,EDGE" : "MAIN";
        for (String sub : System.getProperty("probe.subruns", def).split(","))
        {
            switch (sub)
            {
                case "MAIN": stream(sub, L); break;
                case "CTRL1M": stream(sub, ctrlL); break;
                case "C436": whole(sub, L); break;
                case "EDGE": stream(sub, max - 9L); break;
                default: throw new IllegalArgumentException(sub);
            }
        }
        System.out.println("DONE," + mfs);
    }
}
