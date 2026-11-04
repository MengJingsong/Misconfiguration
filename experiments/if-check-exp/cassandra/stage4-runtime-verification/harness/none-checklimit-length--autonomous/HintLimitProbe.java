/*
 * Stage-4 harness (unit tier B2, amended 2026-10-29) of none-checklimit-length--autonomous. Not upstream. Compiled by unit-run.sh into a
 * separate directory (package org.apache.cassandra.hints: ChecksummedDataInput's constructor path and Hint.Serializer.readBufferIfLive
 * are package-private); never copied into a source tree.
 *
 *   HintLimitProbe <label> <S bytes> <agent 0|1>
 * One JVM per (S, pass). Arms: EMPTY, F1 (limit S, check false), T1 (limit S-1: the check throws at the third read), F2, T2 (noise floor),
 * N (no limit call), D (dead hint, limit S: positive control, the liveness gate). Window = ThreadMXBean.getThreadAllocatedBytes before/after
 * ONE Hint.serializer.readBufferIfLive call; the open and the limit() call are outside. Then retained blocks and controls.
 * Output: "STAGE4 ..." lines to stdout and to -Dstage4.out.
 */
package org.apache.cassandra.hints;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.DataOutputBuffer;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.net.MessagingService;

public class HintLimitProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static PrintWriter out;
    static String label;
    static int S, agent, checks, mismatches;
    static Object sink, held;

    static void say(String s) { System.out.println(s); if (out != null) { out.println(s); out.flush(); } }
    static long alloc() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++; if (!ok) mismatches++;
        say("STAGE4 check " + label + " " + name + " expected=" + expected + " actual=" + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static long usedAfterGc() throws Exception
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(60); }
        Runtime rt = Runtime.getRuntime();
        return rt.totalMemory() - rt.freeMemory();
    }

    static Path writeRecord(Path dir, String name, long creationTime, int gcgs) throws Exception
    {
        Path p = dir.resolve(name);
        try (DataOutputBuffer b = new DataOutputBuffer())
        {
            b.writeLong(creationTime);
            b.writeUnsignedVInt32(gcgs);
            byte[] head = b.toByteArray();
            byte[] all = new byte[S];
            System.arraycopy(head, 0, all, 0, Math.min(head.length, S));
            Files.write(p, all);
        }
        return p;
    }

    static long[] med(List<Long> v)
    {
        long[] a = new long[v.size()]; for (int i = 0; i < a.length; i++) a[i] = v.get(i);
        Arrays.sort(a);
        return new long[]{ a[a.length / 2], a[0], a[a.length - 1] };
    }

    static int K() { return S <= 65536 ? 200 : S <= (1 << 20) ? 20 : S <= (16 << 20) ? 3 : 1; }
    static int WARM() { return S <= 65536 ? 400 : S <= (1 << 20) ? 40 : S <= (16 << 20) ? 3 : 2; }

    static int threw; static String lastMsg; static int lastCap; static boolean lastNull;

    /** one call: limitArg < 0 means no limit() call; returns the allocation of the window */
    static long one(Path p, long now, long limitArg) throws Exception
    {
        ChecksummedDataInput in = ChecksummedDataInput.open(new File(p.toString()));
        try
        {
            if (limitArg >= 0) in.limit(limitArg);
            ByteBuffer res = null; IOException ex = null;
            long a0 = alloc();
            try { res = Hint.serializer.readBufferIfLive(in, now, S, MessagingService.current_version); }
            catch (IOException e) { ex = e; }
            long a1 = alloc();
            lastNull = res == null && ex == null;
            lastCap = res == null ? -1 : res.capacity();
            lastMsg = ex == null ? "" : ex.getMessage();
            if (ex != null) threw++;
            sink = res;
            return a1 - a0;
        }
        finally { sink = null; in.close(); }
    }

    static long arm(String name, Path p, long now, long limitArg) throws Exception
    {
        int k = K();
        long h0 = stage4.Count.get();
        threw = 0;
        int calls = 0;
        for (int i = 0; i < WARM(); i++) { one(p, now, limitArg); calls++; }
        List<Long> repMed = new ArrayList<>(), all = new ArrayList<>();
        for (int rep = 0; rep < 5; rep++)
        {
            List<Long> v = new ArrayList<>();
            for (int i = 0; i < k; i++) { v.add(one(p, now, limitArg)); calls++; }
            long[] m = med(v);
            repMed.add(m[0]); all.addAll(v);
            say("STAGE4 rep " + label + " S=" + S + " arm=" + name + " rep=" + rep + " med=" + m[0] + " min=" + m[1] + " max=" + m[2]);
        }
        long[] mm = med(repMed), ma = med(all);
        long hits = stage4.Count.get() - h0;
        say("STAGE4 arm " + label + " S=" + S + " arm=" + name + " agent=" + agent + " calls=" + calls + " threw=" + threw + " hits=" + hits
            + " hitsPerCall=" + (calls == 0 ? -1 : (double) hits / calls) + " lastNull=" + lastNull + " lastCap=" + lastCap + " lastMsg=" + lastMsg.replace(' ', '_')
            + " repmedian=" + mm[0] + " repmin=" + mm[1] + " repmax=" + mm[2] + " allmin=" + ma[1] + " allmax=" + ma[2]);
        return mm[0];
    }

    static void retained(String name, Path p, long now, long limitArg, boolean hold) throws Exception
    {
        long u0 = usedAfterGc();
        ChecksummedDataInput in = ChecksummedDataInput.open(new File(p.toString()));
        if (limitArg >= 0) in.limit(limitArg);
        try { held = Hint.serializer.readBufferIfLive(in, now, S, MessagingService.current_version); }
        catch (IOException e) { held = null; }
        in.close();
        long u1 = usedAfterGc();
        say("STAGE4 retained " + label + " S=" + S + " arm=" + name + " held=" + (held == null ? "none" : "buffer") + " usedBefore=" + u0 + " usedAfter=" + u1 + " delta=" + (u1 - u0));
        held = null;
    }

    public static void main(String[] a) throws Exception
    {
        label = a[0]; S = Integer.parseInt(a[1]); agent = Integer.parseInt(a[2]);
        String o = System.getProperty("stage4.out");
        if (o != null) out = new PrintWriter(new FileWriter(o, true));
        DatabaseDescriptor.daemonInitialization();
        say("STAGE4 info " + label + " S=" + S + " pass=" + (agent == 1 ? "B" : "A") + " java=" + System.getProperty("java.version") + " maxHeap=" + Runtime.getRuntime().maxMemory() + " msgVersion=" + MessagingService.current_version);
        Path dir = Files.createTempDirectory(Path.of(System.getProperty("stage4.tmp", System.getProperty("java.io.tmpdir"))), "hint");
        long now = System.currentTimeMillis();
        Path live = writeRecord(dir, "live.bin", now, 864000), dead = writeRecord(dir, "dead.bin", 1L, 0);
        say("STAGE4 info " + label + " liveLen=" + live.toFile().length() + " deadLen=" + dead.toFile().length());
        try
        {
            long e1, e2;
            { long x0 = alloc(); long x1 = alloc(); e1 = x1 - x0; x0 = alloc(); x1 = alloc(); e2 = x1 - x0; }
            say("STAGE4 empty " + label + " S=" + S + " e1=" + e1 + " e2=" + e2);
            long f1 = arm("F1", live, now, S);
            check("F1 returns buffer of S", S, lastCap);
            long t1 = arm("T1", live, now, S - 1);
            check("T1 message", "Digest_mismatch_exception", lastMsg.replace(' ', '_'));
            check("T1 threw every call", "all", threw > 0 ? "all" : "none");
            long f2 = arm("F2", live, now, S);
            long t2 = arm("T2", live, now, S - 1);
            long n = arm("N", live, now, -1);
            check("N returns buffer of S", S, lastCap);
            long d = arm("D", dead, now, S);
            check("D returns null", "true", lastNull);
            say("STAGE4 branch " + label + " S=" + S + " F1=" + f1 + " T1=" + t1 + " F2=" + f2 + " T2=" + t2 + " N=" + n + " D=" + d + " T1-F1=" + (t1 - f1));
            if (agent == 0)
            {
                List<Long> c1 = new ArrayList<>();
                for (int i = 0; i < 8; i++)
                {
                    long x0 = alloc(); sink = new byte[S]; long x1 = alloc();
                    if (i >= 3) c1.add(x1 - x0);
                }
                sink = null;
                long[] mc = med(c1);
                say("STAGE4 c1 " + label + " S=" + S + " median=" + mc[0] + " min=" + mc[1] + " max=" + mc[2]);
                retained("F", live, now, S, true);
                retained("T", live, now, S - 1, false);
            }
        }
        finally
        {
            say("STAGE4 summary " + label + " S=" + S + " checks=" + checks + " mismatches=" + mismatches);
            try (var s = Files.walk(dir)) { s.sorted(java.util.Comparator.reverseOrder()).forEach(q -> q.toFile().delete()); }
        }
    }
}
