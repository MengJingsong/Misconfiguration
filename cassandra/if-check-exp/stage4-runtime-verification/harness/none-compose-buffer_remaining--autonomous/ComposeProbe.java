/*
 * Stage-4 harness (unit tier B2, amended 2026-10-29) of none-compose-buffer_remaining--autonomous. Not upstream. Compiled by unit-run.sh into a
 * separate directory (UDFDataType.wrap/compose are public); never copied into a source tree.
 *
 *   ComposeProbe <label> <agent 0|1>
 * One JVM per pass. Cells = (type, L): BytesType (check never true) and IntegerType (check true at L=0) at L in {0,1,1KiB,1MiB,16MiB,64MiB},
 * Int32Type at L=0 and L=4, and a null buffer. Window = ThreadMXBean.getThreadAllocatedBytes before/after ONE compose() call.
 * Then the noise-floor repeats, C1 (new byte[L]) and the positive control (BytesType.read with a 2048 vint and max 1024).
 * Output: "STAGE4 ..." lines to stdout and to -Dstage4.out.
 */
package org.apache.cassandra.cql3.functions;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.marshal.AbstractType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.marshal.IntegerType;
import org.apache.cassandra.db.marshal.ByteBufferAccessor;
import org.apache.cassandra.io.util.DataInputBuffer;
import org.apache.cassandra.io.util.DataOutputBuffer;
import org.apache.cassandra.transport.ProtocolVersion;

public class ComposeProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static PrintWriter out;
    static String label;
    static int agent, checks, mismatches;
    static Object sink;

    static void say(String s) { System.out.println(s); if (out != null) { out.println(s); out.flush(); } }
    static long alloc() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++; if (!ok) mismatches++;
        say("STAGE4 check " + label + " " + name + " expected=" + expected + " actual=" + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static long[] med(List<Long> v)
    {
        long[] a = new long[v.size()]; for (int i = 0; i < a.length; i++) a[i] = v.get(i);
        Arrays.sort(a);
        return new long[]{ a[a.length / 2], a[0], a[a.length - 1] };
    }

    static ByteBuffer buf(int len, boolean intPattern)
    {
        byte[] b = new byte[len];
        if (intPattern && len > 0) b[0] = 1;
        return ByteBuffer.wrap(b);
    }

    static int K(int len) { return len <= 1024 ? 200 : len <= (1 << 20) ? 20 : 1; }
    static int WARM(int len) { return len <= 1024 ? 200 : len <= (1 << 20) ? 20 : 2; }

    static long cell(String name, AbstractType<?> type, ByteBuffer b, int len)
    {
        UDFDataType t = UDFDataType.wrap(type, false);
        int k = K(len);
        long h0 = stage4.Count.get();
        Object r = null;
        int calls = 0;
        for (int i = 0; i < WARM(len); i++) { r = t.compose(ProtocolVersion.CURRENT, b == null ? null : b.duplicate()); calls++; }
        List<Long> repMed = new ArrayList<>(), all = new ArrayList<>();
        for (int rep = 0; rep < 5; rep++)
        {
            List<Long> v = new ArrayList<>();
            for (int i = 0; i < k; i++)
            {
                ByteBuffer arg = b == null ? null : b.duplicate();   // outside the window
                long a0 = alloc();
                r = t.compose(ProtocolVersion.CURRENT, arg);
                long a1 = alloc();
                calls++;
                v.add(a1 - a0);
                sink = r;
            }
            long[] m = med(v);
            repMed.add(m[0]); all.addAll(v);
        }
        long[] mm = med(repMed), ma = med(all);
        long hits = stage4.Count.get() - h0;
        say("STAGE4 cell " + label + " cell=" + name + " type=" + type.getClass().getSimpleName() + " L=" + len + " agent=" + agent + " calls=" + calls + " hits=" + hits
            + " resultNull=" + (r == null) + " resultClass=" + (r == null ? "null" : r.getClass().getSimpleName())
            + " repmedian=" + mm[0] + " repmin=" + mm[1] + " repmax=" + mm[2] + " allmin=" + ma[1] + " allmax=" + ma[2]);
        sink = null;
        return mm[0];
    }

    public static void main(String[] a) throws Exception
    {
        label = a[0]; agent = Integer.parseInt(a[1]);
        String o = System.getProperty("stage4.out");
        if (o != null) out = new PrintWriter(new FileWriter(o, true));
        DatabaseDescriptor.daemonInitialization();
        say("STAGE4 info " + label + " pass=" + (agent == 1 ? "B" : "A") + " java=" + System.getProperty("java.version") + " maxHeap=" + Runtime.getRuntime().maxMemory());
        long e1, e2;
        { long x0 = alloc(); long x1 = alloc(); e1 = x1 - x0; x0 = alloc(); x1 = alloc(); e2 = x1 - x0; }
        say("STAGE4 empty " + label + " e1=" + e1 + " e2=" + e2);
        int[] Ls = { 0, 1, 1024, 1 << 20, 16 << 20, 64 << 20 };
        cell("null", BytesType.instance, null, 0);
        for (int l : Ls)
        {
            cell("bytes", BytesType.instance, buf(l, false), l);
            cell("integer", IntegerType.instance, buf(l, true), l);
        }
        cell("int32", Int32Type.instance, buf(0, false), 0);
        cell("int32", Int32Type.instance, buf(4, false), 4);
        // noise floor: identical repeats
        cell("bytes-rep", BytesType.instance, buf(0, false), 0);
        cell("integer-rep", IntegerType.instance, buf(0, true), 0);
        cell("integer-rep", IntegerType.instance, buf(1 << 20, true), 1 << 20);
        if (agent == 0)
        {
            for (int l : new int[]{ 1, 1 << 20, 64 << 20 })
            {
                List<Long> c1 = new ArrayList<>();
                for (int i = 0; i < 8; i++) { long x0 = alloc(); sink = new byte[l]; long x1 = alloc(); if (i >= 3) c1.add(x1 - x0); }
                sink = null;
                long[] mc = med(c1);
                say("STAGE4 c1 " + label + " L=" + l + " median=" + mc[0] + " min=" + mc[1] + " max=" + mc[2]);
            }
            // positive control: a real size cap in the same harness
            String msg = "none"; String cls = "none";
            try (DataOutputBuffer w = new DataOutputBuffer())
            {
                w.writeUnsignedVInt32(2048);
                w.write(new byte[2048]);
                try (DataInputBuffer in = new DataInputBuffer(w.buffer(), false))
                {
                    BytesType.instance.read(ByteBufferAccessor.instance, in, 1024);
                }
                catch (IOException e) { msg = e.getMessage(); cls = e.getClass().getSimpleName(); }
            }
            say("STAGE4 control " + label + " read2048max1024 class=" + cls + " msg=" + msg.replace(' ', '_'));
            check("control throws with max_value_size text", "true", String.valueOf(msg.contains("exceeds the maximum of 1024")));
        }
        say("STAGE4 summary " + label + " checks=" + checks + " mismatches=" + mismatches);
    }
}
