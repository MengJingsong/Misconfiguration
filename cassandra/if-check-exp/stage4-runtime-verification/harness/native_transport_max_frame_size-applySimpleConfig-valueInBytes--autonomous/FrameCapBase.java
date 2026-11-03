/*
 * Stage-4 harness, unit tier (B2, amended 2026-10-24) of
 * native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous. Not upstream.
 * Shared code of FrameCap1MiBTest, FrameCap4MiBTest, FrameCapDefaultTest: read-back, envelopes L1/L2/L3 fed to
 * Envelope.Decoder.decode(ByteBuf) in 65,536-byte chunks through one heap cumulation, and the v5 extractHeader control.
 * Writes "STAGE4 ..." lines to the file named by -Dstage4.out (appends).
 */
package org.apache.cassandra.transport;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.transport.messages.ErrorMessage;

public abstract class FrameCapBase
{
    static final int CHUNK = 65536;

    static synchronized void out(String line)
    {
        String f = System.getProperty("stage4.out");
        System.out.println(line);
        if (f == null) return;
        try (PrintWriter w = new PrintWriter(new FileWriter(f, true))) { w.println(line); }
        catch (IOException e) { throw new RuntimeException(e); }
    }

    /** knobMiB < 0: no override (yaml/Config default). */
    static void init(String label, int knobMiB)
    {
        if (knobMiB < 0)
            DatabaseDescriptor.daemonInitialization();
        else
            DatabaseDescriptor.daemonInitialization(() -> {
                Config c = DatabaseDescriptor.loadConfig();
                c.native_transport_max_frame_size = new DataStorageSpec.IntMebibytesBound(knobMiB + "MiB");
                return c;
            });
        out("STAGE4 " + label + " readback=" + DatabaseDescriptor.getNativeTransportMaxFrameSize());
    }

    static byte[] header(int version, long bodyLength)
    {
        byte[] h = new byte[9];
        h[0] = (byte) version; h[1] = 0; h[2] = 0; h[3] = 1; h[4] = 7;
        h[5] = (byte) (bodyLength >>> 24); h[6] = (byte) (bodyLength >>> 16); h[7] = (byte) (bodyLength >>> 8); h[8] = (byte) bodyLength;
        return h;
    }

    /** Feeds one v4 envelope with body length L; prints one STAGE4 line. */
    static void feed(String label, String name, long L)
    {
        long total = L + 9;
        byte[] h = header(4, L);
        int chunks = (int) ((total + CHUNK - 1) / CHUNK);
        Envelope.Decoder decoder = new Envelope.Decoder();
        ByteBuf cum = Unpooled.buffer();
        long maxBefore = 0, maxAfter = 0;
        String outcome = "none";
        int at = -1;
        long pos = 0;
        for (int i = 0; i < chunks; i++)
        {
            int len = (int) Math.min(CHUNK, total - pos);
            byte[] chunk = new byte[len];
            for (int j = 0; j < len; j++)
            {
                long p = pos + j;
                if (p < 9) chunk[j] = h[(int) p];
            }
            pos += len;
            cum.writeBytes(chunk);
            maxBefore = Math.max(maxBefore, cum.readableBytes());
            Envelope e;
            try
            {
                e = decoder.decode(cum);
            }
            catch (RuntimeException ex)
            {
                Throwable c = ex.getCause();
                outcome = "exception class=" + ex.getClass().getName() + " cause=" + (c == null ? "null" : c.getClass().getName())
                          + " message=\"" + (c == null ? ex.getMessage() : c.getMessage()) + "\""
                          + (ex instanceof ErrorMessage.WrappedException ? " stream=" + ((ErrorMessage.WrappedException) ex).getStreamId() : "");
                at = i;
                maxAfter = Math.max(maxAfter, cum.readableBytes());
                break;
            }
            maxAfter = Math.max(maxAfter, cum.readableBytes());
            if (e != null)
            {
                outcome = "envelope bodySizeInBytes=" + e.header.bodySizeInBytes + " bodyReadable=" + e.body.readableBytes()
                          + " version=" + e.header.version + " type=" + e.header.type;
                at = i;
                e.release();
                break;
            }
            cum.discardReadBytes();
        }
        out("STAGE4 " + label + " " + name + " L=" + L + " total=" + total + " chunks=" + chunks + " at=" + at
            + " maxBefore=" + maxBefore + " maxAfter=" + maxAfter + " outcome=" + outcome);
        cum.release();
    }

    static void control(String label, String name, long L)
    {
        Envelope.Decoder decoder = new Envelope.Decoder();
        Envelope.Decoder.HeaderExtractionResult r = decoder.extractHeader(ByteBuffer.wrap(header(5, L)));
        out("STAGE4 " + label + " control-v5 " + name + " L=" + L + " isSuccess=" + r.isSuccess() + " bodyLength=" + r.bodyLength());
    }

    static void runAll(String label, long knobBytes)
    {
        long[] Ls = { knobBytes - 9, knobBytes - 8, 2 * knobBytes };
        String[] names = { "L1", "L2", "L3" };
        for (int i = 0; i < 3; i++) feed(label, names[i], Ls[i]);
        for (int i = 0; i < 3; i++) control(label, names[i], Ls[i]);
        out("STAGE4 " + label + " done");
    }
}
