/*
 * Stage-4 unit tier for max_offset-createentry-offset--autonomous (B2, as amended 2026-10-28, U1-U4).
 * One JUnit method; every case prints a "READ" line, and the frozen predictions of B2f/U3 are printed as
 * "EXPECTED <name>: <value>  got <value>  PASS|FAIL" lines (instrument self-check, not a verdict).
 * Output goes to the file named by -Dprobe.out (and to stdout).
 */
package org.apache.cassandra.index.sasi.disk;

import java.io.PrintWriter;
import java.nio.ByteBuffer;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.DataOutputBuffer;

public class MaxOffsetProbeTest
{
    static PrintWriter out;
    static int pass, fail;
    static final long MAX = TokenTreeBuilder.MAX_OFFSET;
    static final String[] TYPES = { "SIMPLE", "FACTORED", "PACKED", "OVERFLOW" };

    @BeforeClass
    public static void init() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        out = new PrintWriter(new java.io.FileWriter(System.getProperty("probe.out", "/dev/stdout")), true);
    }

    static void p(String s) { out.println(s); System.out.println(s); }

    static void expect(String name, Object want, Object got)
    {
        boolean ok = String.valueOf(want).equals(String.valueOf(got));
        if (ok) pass++; else fail++;
        p("EXPECTED " + name + ": " + want + "  got " + got + "  " + (ok ? "PASS" : "FAIL"));
    }

    /** Builds one tree with the given tokens (token i gets offsets[i]) and writes it. Returns a result line. */
    static String run(String label, long[][] offsets, boolean typeLines)
    {
        DynamicTokenTreeBuilder b = new DynamicTokenTreeBuilder();
        for (int t = 0; t < offsets.length; t++)
            for (long o : offsets[t])
                b.add((long) (t + 1), o);
        b.finish();
        DataOutputBuffer buf = new DataOutputBuffer();
        String res;
        try
        {
            b.write(buf);
            int len = buf.getLength();
            ByteBuffer bb = buf.asNewBuffer();
            StringBuilder types = new StringBuilder();
            if (typeLines && b.numBlocks == 1)
                for (int i = 0; i < offsets.length && i < 4; i++)
                    types.append(TYPES[bb.getShort(64 + 16 * i)]).append(' ');
            long slots = b.numBlocks == 1 ? (len - 64 - 16L * offsets.length) / 8 : -1;
            res = "OK bytes=" + len + " numBlocks=" + b.numBlocks + " slots=" + slots + " serializedSizeAfterWrite=" + b.serializedSize() + " types=" + types.toString().trim();
        }
        catch (Throwable e)
        {
            res = "THROW " + e.getClass().getName() + ": " + e.getMessage();
        }
        p("READ " + label + " -> " + res);
        return res;
    }

    static long[][] one(long... offs) { return new long[][]{ offs }; }

    @Test
    public void probe()
    {
        p("PROBE MAX_OFFSET=" + MAX + " OVERFLOW_TRAILER_CAPACITY=" + TokenTreeBuilder.OVERFLOW_TRAILER_CAPACITY + " TOKENS_PER_BLOCK=" + TokenTreeBuilder.TOKENS_PER_BLOCK);
        Runtime rt = Runtime.getRuntime();
        System.gc();
        long h0 = rt.totalMemory() - rt.freeMemory();

        // B2b single offset, passing values: 80 bytes each; SIMPLE up to Integer.MAX_VALUE, FACTORED above
        long[] passing = { 1, Integer.MAX_VALUE, Integer.MAX_VALUE + 1L, MAX - 1, MAX };
        for (long o : passing)
        {
            String r = run("single offset=" + o, one(o), true);
            expect("single " + o + " no throw, 80 bytes", "true", String.valueOf(r.startsWith("OK bytes=80 ")));
            expect("single " + o + " type", o <= Integer.MAX_VALUE ? "SIMPLE" : "FACTORED", r.substring(r.indexOf("types=") + 6));
        }
        // offset 0 is an allowed value (position 0)
        run("single offset=0", one(0), true);

        // boundary + 1 and Long.MAX_VALUE: throw with the exact message
        String r = run("single offset=MAX+1", one(MAX + 1), true);
        expect("single MAX+1 throws", "THROW java.lang.AssertionError: offset 140737488355328 cannot be greater than 140737488355327", r);
        r = run("single offset=Long.MAX_VALUE", one(Long.MAX_VALUE), true);
        expect("single Long.MAX throws", "THROW java.lang.AssertionError: offset 9223372036854775807 cannot be greater than 140737488355327", r);

        // two / three offsets: bypass (no MAX_OFFSET test on the multi-offset path)
        r = run("two offsets {5, MAX+1}", one(5, MAX + 1), true);
        expect("two offsets MAX+1 no throw, 96 bytes, OVERFLOW", "true", String.valueOf(r.startsWith("OK bytes=96 ") && r.endsWith("types=OVERFLOW")));
        r = run("three offsets {5, 6, MAX+1}", one(5, 6, MAX + 1), true);
        expect("three offsets MAX+1 no throw, 104 bytes", "true", String.valueOf(r.startsWith("OK bytes=104 ")));
        r = run("two offsets {5, Long.MAX_VALUE}", one(5, Long.MAX_VALUE), true);
        expect("two offsets Long.MAX no throw", "true", String.valueOf(r.startsWith("OK ")));
        r = run("two offsets {6, 7} (packed control)", one(6, 7), true);
        expect("two small offsets PACKED, 80 bytes", "true", String.valueOf(r.startsWith("OK bytes=80 ") && r.endsWith("types=PACKED")));

        // size controls (B2h): tokens with one small offset
        for (int n : new int[]{ 1, 248, 249, 1000 })
        {
            long[][] o = new long[n][];
            for (int i = 0; i < n; i++) o[i] = new long[]{ 100 + i };
            r = run("size control tokens=" + n, o, false);
            if (n == 1) expect("1 token bytes", "80", r.replaceAll(".*bytes=(\\d+).*", "$1"));
            if (n == 248) expect("248 tokens bytes", "4032", r.replaceAll(".*bytes=(\\d+).*", "$1"));
            if (n == 249) expect("249 tokens numBlocks/bytes", "numBlocks=3|12288", r.replaceAll(".*bytes=(\\d+) numBlocks=(\\d+).*", "numBlocks=$2|$1"));
        }
        // the cap that binds in the same method (B2h): 8 offsets pass, 9 throw
        long[] eight = new long[8], nine = new long[9];
        for (int i = 0; i < 9; i++) { if (i < 8) eight[i] = 40000 + i; nine[i] = 40000 + i; }
        r = run("8 offsets on one token", one(eight), true);
        expect("8 offsets passes, 144 bytes", "true", String.valueOf(r.startsWith("OK bytes=144 ")));
        r = run("9 offsets on one token", one(nine), true);
        expect("9 offsets throws", "THROW java.lang.AssertionError: cannot have more than 8 overflow collisions per leaf", r);

        System.gc();
        long h1 = rt.totalMemory() - rt.freeMemory();
        p("CONTEXT heap_used_before=" + h0 + " heap_used_after=" + h1);
        p("SUMMARY expectations pass=" + pass + " fail=" + fail);
        out.close();
    }
}
