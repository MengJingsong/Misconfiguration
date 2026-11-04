/*
 * Stage 4, unit tier (B2) of internode_max_message_size-inferMessageSize-size--autonomous.
 * Copy into test/unit/org/apache/cassandra/net/ of a local clone of cassandra-5.0.9 (inferMessageSize is
 * package-private, Message.java:777) and run with
 *   ant testsome -Dtest.name=org.apache.cassandra.net.InferMessageSizeLimitTest -Dtest.jvm.args="-Dstage4.out=<file>"
 *
 * B2b/B2c: for L in {64 KiB, 1 MiB, 16 MiB}, set DatabaseDescriptor.setInternodeMaxMessageSizeInBytes(L), build a
 * Verb._TEST_2 message whose payload is P raw bytes, serialize it at the current messaging version and pass the bytes to
 * Message.serializer.inferMessageSize(buf, 0, limit). Messages: P = L - 1 KiB; size exactly L; size exactly L + 1;
 * P = 2L; P = 8L. Boundary by the limit: the L - 1 KiB message with the limit at size and at size - 1. Truncated input:
 * only the header and the payload-length vint (decision made without the payload), and one byte less (the vint
 * incomplete: -1). Controls (B2h): the 8L message at Integer.MAX_VALUE - 1 (the largest settable value) passes; two limits on the same bytes flip the result;
 * the returned size is compared with Message.serializedSize(version) and with the number of bytes written.
 * Every case writes one line "STAGE4 case ..." and one "STAGE4 check <name> ... ok|MISMATCH" to -Dstage4.out (and stdout);
 * the test fails at the end if any check is a MISMATCH, so every case is recorded first.
 */
package org.apache.cassandra.net;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.IVersionedSerializer;
import org.apache.cassandra.io.util.DataInputPlus;
import org.apache.cassandra.io.util.DataOutputBuffer;
import org.apache.cassandra.io.util.DataOutputPlus;
import org.apache.cassandra.utils.FBUtilities;

import static org.apache.cassandra.net.Message.serializer;
import static org.apache.cassandra.utils.MonotonicClock.Global.approxTime;
import static org.apache.cassandra.utils.vint.VIntCoding.computeUnsignedVIntSize;
import static org.junit.Assert.assertEquals;

public class InferMessageSizeLimitTest
{
    static final int KIB = 1024, MIB = 1 << 20;
    static final int VERSION = MessagingService.current_version;
    static PrintWriter out;
    static int checks, mismatches;

    @BeforeClass
    public static void setUpClass() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        Verb._TEST_2.unsafeSetSerializer(() -> new IVersionedSerializer<byte[]>()
        {
            public void serialize(byte[] value, DataOutputPlus o, int version) throws IOException
            {
                o.write(value);
            }

            public byte[] deserialize(DataInputPlus in, int version)
            {
                throw new UnsupportedOperationException("not used by this test");
            }

            public long serializedSize(byte[] value, int version)
            {
                return value.length;
            }
        });
        out = new PrintWriter(new FileWriter(System.getProperty("stage4.out", "build/test/stage4-imm.out"), true), true);
        say("STAGE4 env version=" + VERSION + " maxMemory=" + Runtime.getRuntime().maxMemory()
            + " default_limit=" + DatabaseDescriptor.getInternodeMaxMessageSizeInBytes());
    }

    @AfterClass
    public static void tearDownClass() throws Exception
    {
        Verb._TEST_2.unsafeSetSerializer(() -> NoPayload.serializer);
        if (out != null)
            out.close();
    }

    static void say(String s)
    {
        System.out.println(s);
        out.println(s);
    }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = expected.equals(actual);
        checks++;
        if (!ok)
            mismatches++;
        say("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
    }

    static Message<byte[]> message(int payloadBytes)
    {
        return Message.builder(Verb._TEST_2, new byte[payloadBytes])
                      .withId(1)
                      .from(FBUtilities.getLocalAddressAndPort())
                      .withCreatedAt(approxTime.now())
                      .withExpiresAt(approxTime.now() + 10_000_000_000L)
                      .build();
    }

    /** the serialized bytes of a message; asserts that serializedSize(version) is the number of bytes written */
    static ByteBuffer bytes(Message<byte[]> m) throws IOException
    {
        int size = m.serializedSize(VERSION);
        try (DataOutputBuffer o = new DataOutputBuffer(size))
        {
            serializer.serialize(m, o, VERSION);
            assertEquals(size, o.getLength());
            return o.asNewBuffer();
        }
    }

    /** payload size that gives a serialized size of exactly target (the header length depends on the payload's vint) */
    static int payloadFor(int target)
    {
        int p = target - 64;
        for (int i = 0; i < 8; i++)
        {
            int s = message(p).serializedSize(VERSION);
            if (s == target)
                return p;
            p += target - s;
        }
        throw new IllegalStateException("no payload size gives " + target);
    }

    /** "returned <size>" / "threw <message>" / "returned -1" */
    static String infer(ByteBuffer buf, int readerLimit, int limit)
    {
        DatabaseDescriptor.setInternodeMaxMessageSizeInBytes(limit);
        try
        {
            return "returned " + serializer.inferMessageSize(buf, 0, readerLimit);
        }
        catch (Message.OversizedMessageException e)
        {
            return "threw " + e.getMessage();
        }
    }

    static String threw(int size, int limit)
    {
        return "threw Message of size " + size + " bytes exceeds allowed maximum of " + limit + " bytes";
    }

    /** bytes of the header plus the payload-length vint, i.e. everything before the payload */
    static int prefixLength(int size, int payload)
    {
        return size - payload;
    }

    static void caseRow(int limit, String what, int payload, int size, int readerLimit, String result)
    {
        say("STAGE4 case L=" + limit + " " + what + " P=" + payload + " size=" + size + " given=" + readerLimit + " -> " + result);
    }

    @Test
    public void limitDecidesFromTheLengthPrefix() throws Exception
    {
        int defaultLimit = DatabaseDescriptor.getInternodeMaxMessageSizeInBytes();
        try
        {
            for (int limit : new int[]{ 64 * KIB, MIB, 16 * MIB })
                runLimit(limit);
            controls();
        }
        finally
        {
            DatabaseDescriptor.setInternodeMaxMessageSizeInBytes(defaultLimit);
        }
        say("STAGE4 summary checks=" + checks + " mismatches=" + mismatches);
        assertEquals("mismatches (see STAGE4 check lines)", 0, mismatches);
    }

    static void runLimit(int limit) throws IOException
    {
        // P = L - 1 KiB: under the limit, returns exactly the serialized size
        int p = limit - KIB;
        Message<byte[]> m = message(p);
        ByteBuffer b = bytes(m);
        int size = m.serializedSize(VERSION);
        String r = infer(b, b.limit(), limit);
        caseRow(limit, "under", p, size, b.limit(), r);
        check("L=" + limit + " under returns serializedSize", "returned " + size, r);
        check("L=" + limit + " under bytes written == serializedSize", size, b.limit());

        // boundary by the limit on the same bytes: limit = size passes, limit = size - 1 throws
        r = infer(b, b.limit(), size);
        caseRow(size, "limit=size", p, size, b.limit(), r);
        check("L=size(" + size + ") returns", "returned " + size, r);
        r = infer(b, b.limit(), size - 1);
        caseRow(size - 1, "limit=size-1", p, size, b.limit(), r);
        check("L=size-1(" + (size - 1) + ") throws", threw(size, size - 1), r);

        // truncated, size <= L: decided (returned) with only the header and the length vint
        int pre = prefixLength(size, p);
        r = infer(b, pre, limit);
        caseRow(limit, "under-truncated", p, size, pre, r);
        check("L=" + limit + " under, payload absent, returns size", "returned " + size, r);

        // size exactly L and exactly L + 1
        int pAt = payloadFor(limit);
        ByteBuffer bAt = bytes(message(pAt));
        r = infer(bAt, bAt.limit(), limit);
        caseRow(limit, "size=L", pAt, limit, bAt.limit(), r);
        check("L=" + limit + " size=L returns", "returned " + limit, r);
        int pOver = payloadFor(limit + 1);
        ByteBuffer bOver = bytes(message(pOver));
        r = infer(bOver, bOver.limit(), limit);
        caseRow(limit, "size=L+1", pOver, limit + 1, bOver.limit(), r);
        check("L=" + limit + " size=L+1 throws", threw(limit + 1, limit), r);

        // P = 2L and P = 8L: throw with N = serializedSize; 2L also truncated to header + vint, and one byte less
        for (int mult : new int[]{ 2, 8 })
        {
            int pp = mult * limit;
            Message<byte[]> mm = message(pp);
            ByteBuffer bb = bytes(mm);
            int s = mm.serializedSize(VERSION);
            r = infer(bb, bb.limit(), limit);
            caseRow(limit, mult + "L", pp, s, bb.limit(), r);
            check("L=" + limit + " P=" + mult + "L throws with N=serializedSize", threw(s, limit), r);
            if (mult == 2)
            {
                int pre2 = prefixLength(s, pp);
                r = infer(bb, pre2, limit);
                caseRow(limit, "2L-truncated", pp, s, pre2, r);
                check("L=" + limit + " 2L, payload absent, throws", threw(s, limit), r);
                r = infer(bb, pre2 - 1, limit);
                caseRow(limit, "2L-vint-incomplete", pp, s, pre2 - 1, r);
                check("L=" + limit + " 2L, length vint incomplete, returns -1", "returned -1", r);
                say("STAGE4 note L=" + limit + " 2L prefix=" + pre2 + " B of " + s + " (payload-length vint " + computeUnsignedVIntSize(pp) + " B)");
            }
        }
    }

    static void controls() throws IOException
    {
        // the 8 x 16 MiB message at the largest settable limit passes (B2h names Integer.MAX_VALUE, but
        // DataStorageSpec.IntBytesBound refuses it: the maximum is Integer.MAX_VALUE - 1, DataStorageSpec.java:111)
        int pp = 8 * 16 * MIB;
        Message<byte[]> m = message(pp);
        ByteBuffer b = bytes(m);
        int s = m.serializedSize(VERSION);
        String r = infer(b, b.limit(), Integer.MAX_VALUE - 1);
        caseRow(Integer.MAX_VALUE - 1, "control-max", pp, s, b.limit(), r);
        check("control L=Integer.MAX_VALUE-1 passes 8x16MiB", "returned " + s, r);

        // two limits on the same bytes flip the result (the knob alone decides)
        int p = 4 * MIB;
        Message<byte[]> m2 = message(p);
        ByteBuffer b2 = bytes(m2);
        int s2 = m2.serializedSize(VERSION);
        String a = infer(b2, b2.limit(), 16 * MIB);
        String c = infer(b2, b2.limit(), MIB);
        caseRow(16 * MIB, "control-flip-a", p, s2, b2.limit(), a);
        caseRow(MIB, "control-flip-b", p, s2, b2.limit(), c);
        check("control flip 4MiB at 16MiB returns", "returned " + s2, a);
        check("control flip 4MiB at 1MiB throws", threw(s2, MIB), c);
    }
}
