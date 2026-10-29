/*
 * Stage-4 unit tier for overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous (B2, as amended 2026-10-28, U1-U4).
 * Cases C1-C8 of B2c. "READ" lines are readings; "EXPECTED" lines print the frozen predictions of B2f/U3 next to what was read
 * (instrument self-check, not a verdict). Output file: -Dprobe.out.
 */
package org.apache.cassandra.index.sasi.disk;

import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.index.sasi.disk.OnDiskIndexBuilder.Mode;
import org.apache.cassandra.io.util.DataOutputBuffer;
import org.apache.cassandra.utils.ByteBufferUtil;

public class OverflowCapacityProbeTest
{
    static PrintWriter out;
    static int npass, nfail;
    static final String[] TYPES = { "SIMPLE", "FACTORED", "PACKED", "OVERFLOW" };
    static final String MSG = "THROW java.lang.AssertionError: cannot have more than 8 overflow collisions per leaf";

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
        if (ok) npass++; else nfail++;
        p("EXPECTED " + name + ": " + want + "  got " + got + "  " + (ok ? "PASS" : "FAIL"));
    }

    /** Result of one write: "OK bytes=.. numBlocks=.. slots=.. ..." or "THROW <class>: <msg>". */
    static String run(String label, long[][] offsets)
    {
        DynamicTokenTreeBuilder b = new DynamicTokenTreeBuilder();
        for (int t = 0; t < offsets.length; t++)
            for (long o : offsets[t])
                b.add((long) t, o);
        b.finish();
        DataOutputBuffer buf = new DataOutputBuffer();
        String res;
        try
        {
            long sizeBefore = b.serializedSize();
            b.write(buf);
            int len = buf.getLength();
            ByteBuffer bb = buf.asNewBuffer();
            StringBuilder extra = new StringBuilder();
            long slots;
            if (b.numBlocks == 1)
            {
                slots = (len - 64 - 16L * offsets.length) / 8;
                int ovf = 0;
                for (int i = 0; i < offsets.length; i++) if (bb.getShort(64 + 16 * i) == 3) ovf++;
                extra.append(" overflowEntries=").append(ovf);
            }
            else
            {
                slots = 0;
                for (int blk = 1; blk < b.numBlocks; blk++)
                {
                    int base = blk * 4096, tokens = bb.getShort(base + 1), s = 0, e = 0;
                    for (int i = 0; i < tokens; i++)
                        if (bb.getShort(base + 64 + 16 * i) == 3) { s += bb.getShort(base + 64 + 16 * i + 2); e++; }
                    slots += s;
                    extra.append(" leaf").append(blk).append("{tokens=").append(tokens).append(",overflowEntries=").append(e).append(",slots=").append(s).append("}");
                }
            }
            res = "OK bytes=" + len + " numBlocks=" + b.numBlocks + " slots=" + slots + " serializedSizeBeforeWrite=" + sizeBefore + extra;
        }
        catch (Throwable e)
        {
            res = "THROW " + e.getClass().getName() + ": " + e.getMessage();
        }
        p("READ " + label + " -> " + res);
        return res;
    }

    static long[][] tokens(int n, int[] bigRanks, int offsetsPerBig, boolean smallPair)
    {
        long[][] o = new long[n][];
        for (int i = 0; i < n; i++)
        {
            boolean big = false;
            for (int r : bigRanks) if (r == i) big = true;
            if (big) { o[i] = new long[offsetsPerBig]; for (int k = 0; k < offsetsPerBig; k++) o[i][k] = 40000L + 10000L * k + i; }
            else if (smallPair) o[i] = new long[]{ 100 + i, 200 + i };
            else o[i] = new long[]{ 100 + i };
        }
        return o;
    }

    static int[] range(int a, int n) { int[] r = new int[n]; for (int i = 0; i < n; i++) r[i] = a + i; return r; }

    static String num(String r, String key) { java.util.regex.Matcher m = java.util.regex.Pattern.compile("(?:^| )" + key + "=(-?\\d+)").matcher(r); return m.find() ? m.group(1) : "none"; }

    @Test
    public void probe() throws Exception
    {
        p("PROBE OVERFLOW_TRAILER_CAPACITY=" + TokenTreeBuilder.OVERFLOW_TRAILER_CAPACITY + " TOKENS_PER_BLOCK=" + TokenTreeBuilder.TOKENS_PER_BLOCK + " BLOCK_BYTES=" + TokenTreeBuilder.BLOCK_BYTES);

        String r = run("C1 4 tokens x 2 large offsets + 20 single (8 slots)", tokens(24, range(0, 4), 2, false));
        expect("C1 no throw, 512 bytes, 8 slots", "512|8", num(r, "bytes") + "|" + num(r, "slots"));
        r = run("C2 5 tokens x 2 large offsets + 19 single (10 slots)", tokens(24, range(0, 5), 2, false));
        expect("C2 throws", MSG, r);
        r = run("C3 1 token x 8 offsets", tokens(1, range(0, 1), 8, false));
        expect("C3 144 bytes, 8 slots", "144|8", num(r, "bytes") + "|" + num(r, "slots"));
        r = run("C4 1 token x 9 offsets", tokens(1, range(0, 1), 9, false));
        expect("C4 throws", MSG, r);

        // C5 token count drives the size
        r = run("C5 248 tokens x 1 small offset", tokens(248, new int[0], 0, false));
        expect("C5 248: numBlocks 1, 4032", "1|4032", num(r, "numBlocks") + "|" + num(r, "bytes"));
        r = run("C5 249 tokens x 1 small offset", tokens(249, new int[0], 0, false));
        expect("C5 249: numBlocks 3, 12288", "3|12288", num(r, "numBlocks") + "|" + num(r, "bytes"));

        // C6 two leaves with 8 slots each (600 tokens, ranks 0-3 and 300-303)
        int[] two = new int[8]; for (int i = 0; i < 4; i++) { two[i] = i; two[4 + i] = 300 + i; }
        r = run("C6 600 tokens, 8 slots in each of two leaves", tokens(600, two, 2, false));
        expect("C6 no throw, numBlocks 5, 20480", "5|20480", num(r, "numBlocks") + "|" + num(r, "bytes"));
        expect("C6 total slots 16", "16", num(r, "slots"));
        // control for C6: same 600 tokens without any overflow, block bytes equal
        r = run("C6 control 600 tokens, no overflow", tokens(600, new int[0], 0, false));
        expect("C6 control numBlocks 5, 20480", "5|20480", num(r, "numBlocks") + "|" + num(r, "bytes"));

        // C7 packed pairs
        r = run("C7 248 tokens x 2 small offsets (packed)", tokens(248, new int[0], 0, true));
        expect("C7 0 slots, 4032", "0|4032", num(r, "slots") + "|" + num(r, "bytes"));
        // block bytes with 0 and 8 slots in multi-block output: leaf of 248 tokens carrying 8 slots fills the block exactly
        r = run("extra: 249 tokens, 4 of them x 2 large offsets (8 slots in the first leaf)", tokens(249, range(0, 4), 2, false));
        expect("extra 8-slot full leaf: numBlocks 3, 12288", "3|12288", num(r, "numBlocks") + "|" + num(r, "bytes"));

        // C8 builder heap estimate vs terms
        for (int n : new int[]{ 1000, 10000 })
        {
            OnDiskIndexBuilder ob = new OnDiskIndexBuilder(UTF8Type.instance, UTF8Type.instance, Mode.PREFIX);
            for (int i = 0; i < n; i++)
            {
                DecoratedKey k = Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes("key" + i));
                ob.add(ByteBufferUtil.bytes(String.format("t%07d", i)), k, 1000L + i);
            }
            long est = ob.estimatedMemoryUse();
            p("READ C8 terms=" + n + " estimatedMemoryUse=" + est);
            expect("C8 estimate " + n + " terms of 8 bytes", String.valueOf(228L * n), est);
        }
        // C8 control: overflow does not enter the estimate: same term, 9 keys with the same token
        p("SUMMARY expectations pass=" + npass + " fail=" + nfail);
        out.close();
    }
}
