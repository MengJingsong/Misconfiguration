import java.lang.management.ManagementFactory;
import java.lang.reflect.Method;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.Random;

import org.apache.cassandra.utils.bytecomparable.ByteComparable;
import org.apache.cassandra.utils.bytecomparable.ByteSource;
import org.apache.cassandra.utils.bytecomparable.ByteSourceInverse;

/**
 * Unit tier (B2) of initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous (case file as amended 2026-10-26).
 * A plain main class (ant testsome would override -Xmx). Run: java -Xmx<m> -XX:+UseSerialGC -cp <classes>:<jars> EnsureCapacityProbe <set> <out>
 *   set = small   N in 0 31 32 33 64 65 1000 65535 1<<20 (the 128m run)
 *         full    small + 16<<20 + 64<<20 (the 1g run)
 *         big     N = 1<<30 and (1<<30)+1 (the 4g run)
 * Per call it reads the calling thread's allocated bytes (com.sun.management.ThreadMXBean) around the public
 * ByteSourceInverse.readBytes / getUnescapedBytes, and compares with the exact sum over every array created of align8(16 + length)
 * (a mirror of ByteSourceInverse.java:366-386 and :422-432, written before any reading). Lines: "STAGE4 m ..." (a measurement),
 * "STAGE4 check <name> ok|MISMATCH <detail>", "STAGE4 info ...".
 */
public class EnsureCapacityProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static PrintWriter out;
    static String xmx;
    static int mismatches = 0;

    static void p(String s) { out.println(s); out.flush(); System.out.println(s); }
    static void check(String name, boolean ok, String detail)
    {
        if (!ok) mismatches++;
        p("STAGE4 check " + name + (ok ? " ok " : " MISMATCH ") + detail);
    }

    static long align8(long x) { return (x + 7) & ~7L; }
    static long arr(long len) { return align8(16 + len); }

    /** bytes allocated by readBytes(src of n bytes, init), mirroring the code */
    static long expected(long n, long init)
    {
        long len = init, total = arr(init), read = 0;
        for (long i = 0; i < n; i++)
        {
            if (read == len) { len = len * 2; total += arr(len); }
            read++;
        }
        if (read != len) total += arr(read);
        return total;
    }

    /** n bytes of non-zero data, then END_OF_STREAM */
    static final class Src implements ByteSource
    {
        long left; int v = 1;
        Src(long n) { left = n; }
        public int next() { if (left == 0) return END_OF_STREAM; left--; v = v == 255 ? 1 : v + 1; return v; }
    }

    static long measure(long n, int init, byte[][] res, String[] exc)
    {
        long tid = Thread.currentThread().getId();
        ByteSource s = new Src(n);
        long a0 = TMX.getThreadAllocatedBytes(tid);
        byte[] r = null; String e = null;
        try { r = ByteSourceInverse.readBytes(s, init); } catch (Throwable t) { e = t.getClass().getName(); }
        long a1 = TMX.getThreadAllocatedBytes(tid);
        res[0] = r; exc[0] = e;
        return a1 - a0;
    }

    static void one(long n, int init, int warm)
    {
        byte[][] r = new byte[1][]; String[] e = new String[1];
        for (int i = 0; i < warm; i++) { measure(n, init, r, e); r[0] = null; }
        // a one-off +536 B was seen in the shakedown on a single call (JIT/profile allocation on the measuring thread); the true cost is
        // deterministic, so each point is measured `reps` times after the warm-up and the median is judged (all values are printed)
        int reps = n >= (16 << 20) ? 3 : 5;
        long[] all = new long[reps];
        for (int i = 0; i < reps; i++) { all[i] = measure(n, init, r, e); if (i < reps - 1) r[0] = null; }
        long[] srt = all.clone(); Arrays.sort(srt);
        long alloc = srt[reps / 2];
        long exp = expected(n, init);
        int len = r[0] == null ? -1 : r[0].length;
        p("STAGE4 m xmx=" + xmx + " n=" + n + " init=" + init + " alloc=" + alloc + " all=" + Arrays.toString(all).replace(" ", "") + " expected=" + exp + " ratio=" + (n == 0 ? "0" : String.format("%.3f", alloc / (double) n)) + " len=" + len + " exc=" + e[0]);
        double tol = Math.max(256, exp * 0.01);
        check("alloc-n" + n + "-init" + init, e[0] == null && Math.abs(alloc - exp) <= tol, "alloc=" + alloc + " expected=" + exp + " tol=" + (long) tol);
        check("len-n" + n + "-init" + init, len == n, "len=" + len);
        r[0] = null;
    }

    static long used()
    {
        for (int i = 0; i < 3; i++) System.gc();
        Runtime rt = Runtime.getRuntime();
        return rt.totalMemory() - rt.freeMemory();
    }

    public static void main(String[] a) throws Exception
    {
        String set = a[0];
        out = new PrintWriter(new java.io.FileWriter(a[1], true));
        xmx = String.valueOf(Runtime.getRuntime().maxMemory() >> 20) + "m";
        p("STAGE4 info start set=" + set + " maxMemory=" + Runtime.getRuntime().maxMemory() + " java=" + System.getProperty("java.version"));

        if (set.equals("big"))
        {
            for (long n : new long[]{ 1L << 30, (1L << 30) + 1 })
            {
                byte[][] r = new byte[1][]; String[] e = new String[1];
                long alloc = measure(n, 32, r, e);
                int len = r[0] == null ? -1 : r[0].length;
                p("STAGE4 m xmx=" + xmx + " n=" + n + " init=32 alloc=" + alloc + " len=" + len + " exc=" + e[0]);
                if (n == 1L << 30)
                    check("big-n2^30", e[0] == null && len == (1 << 30), "len=" + len + " exc=" + e[0]);
                else
                    check("big-n2^30+1", "java.lang.NegativeArraySizeException".equals(e[0]) && len == -1, "len=" + len + " exc=" + e[0]);
                r[0] = null;
            }
            p("STAGE4 info end mismatches=" + mismatches);
            return;
        }

        // instrument check 1: ensureCapacity known answers (reflection on the private helper; the only reflective use)
        Method ec = ByteSourceInverse.class.getDeclaredMethod("ensureCapacity", byte[].class, int.class);
        ec.setAccessible(true);
        byte[] b8 = new byte[8];
        check("ensureCapacity-not-full-same-array", ec.invoke(null, b8, 7) == b8, "returns the same array when 7 < 8");
        byte[] g = (byte[]) ec.invoke(null, b8, 8);
        check("ensureCapacity-full-doubles", g != b8 && g.length == 16, "length=" + g.length);
        // instrument check 2: baseline Arrays.copyOf allocates exactly align8(16 + N)
        long tid = Thread.currentThread().getId();
        byte[] src = new byte[1000]; Arrays.fill(src, (byte) 5);
        for (int i = 0; i < 5; i++) Arrays.copyOf(src, 1000);
        long a0 = TMX.getThreadAllocatedBytes(tid); byte[] cp = Arrays.copyOf(src, 1000); long a1 = TMX.getThreadAllocatedBytes(tid);
        check("baseline-copyOf-1000", a1 - a0 == arr(1000) && cp.length == 1000, "alloc=" + (a1 - a0) + " expected=" + arr(1000));
        // instrument check 3: the mirror against a hand-computed sum (init 32): n=65535 -> 32..65536 doubled + copy of 65535
        long hand = 0; for (long l = 32; l <= 65536; l *= 2) hand += arr(l); hand += arr(65535);
        check("mirror-known-answer-65535", expected(65535, 32) == hand, "mirror=" + expected(65535, 32) + " hand=" + hand);

        long[] ns = set.equals("full") ? new long[]{ 0, 31, 32, 33, 64, 65, 1000, 65535, 1 << 20, 16 << 20, 64 << 20 }
                                       : new long[]{ 0, 31, 32, 33, 64, 65, 1000, 65535, 1 << 20 };
        for (long n : ns) one(n, 32, n >= (16 << 20) ? 2 : 5);
        // initial-capacity knob
        long[] nk = { 33, 1000, 65535, 1 << 20 };
        for (long n : nk)
            for (int init : new int[]{ 1, 24, 32, (int) n, (int) (2 * n) })
                if (init != 32) one(n, init, 5);
        {
            byte[][] r = new byte[1][]; String[] e = new String[1];
            long aN = measure(65535, 65535, r, e), a1c = measure(65535, 1, r, e);
            check("init-N-allocates-N", aN == arr(65535), "alloc=" + aN + " expected=" + arr(65535));
            check("init-1-more-garbage-same-length", a1c > aN && r[0].length == 65535, "alloc=" + a1c);
        }
        // initial capacity 0 (informational): never grows
        {
            byte[][] r = new byte[1][]; String[] e = new String[1];
            measure(0, 0, r, e); String e0 = e[0]; byte[][] r2 = new byte[1][]; String[] e2 = new String[1]; measure(1, 0, r2, e2);
            p("STAGE4 info init0 n=0 exc=" + e0 + " n=1 exc=" + e2[0]);
        }
        // getUnescapedBytes with zeros in the data (escape path)
        Random rnd = new Random(42);
        for (int n : new int[]{ 0, 31, 33, 1000, 65535, 1 << 20 })
        {
            byte[] d = new byte[n]; rnd.nextBytes(d); for (int i = 0; i < n; i += 7) d[i] = 0;
            for (int w = 0; w < 5; w++) ByteSourceInverse.getUnescapedBytes(ByteSource.peekable(ByteSource.of(d, ByteComparable.Version.OSS50)));
            ByteSource.Peekable ps = ByteSource.peekable(ByteSource.of(d, ByteComparable.Version.OSS50));
            long b0 = TMX.getThreadAllocatedBytes(tid);
            byte[] r = ByteSourceInverse.getUnescapedBytes(ps);
            long b1 = TMX.getThreadAllocatedBytes(tid);
            long exp = expected(n, 32);
            p("STAGE4 m xmx=" + xmx + " path=getUnescapedBytes n=" + n + " alloc=" + (b1 - b0) + " expected_readBytes=" + exp + " len=" + r.length);
            check("unescaped-roundtrip-n" + n, Arrays.equals(d, r), "len=" + r.length);
            check("unescaped-alloc-n" + n, (b1 - b0) >= exp && (b1 - b0) <= exp + Math.max(4096, exp / 20), "alloc=" + (b1 - b0) + " expected>=" + exp);
        }
        // retained heap: only the result survives
        for (int n : new int[]{ 1 << 20, (int) ns[ns.length - 1] })
        {
            long before = used();
            byte[][] r = new byte[1][]; String[] e = new String[1];
            measure(n, 32, r, e);
            long held = used() - before;
            int rl = r[0].length;
            r[0] = null;
            long after = used() - before;
            p("STAGE4 m xmx=" + xmx + " retained n=" + n + " held_with_result=" + held + " after_release=" + after + " len=" + rl);
            check("retained-only-result-n" + n, Math.abs(held - n) <= 65536, "held=" + held + " (heap-used difference after three System.gc(); tolerance 64 KiB)");
            check("released-n" + n, Math.abs(after) <= 65536, "after-before=" + after);
        }
        // positive control: copyBytes into a fixed array of M bytes is a binding cap
        for (long n : new long[]{ 33, 1000, 65535, 1 << 20 })
            for (long m : new long[]{ n - 1, n, n + 5 })
            {
                String e = null; byte[] dst = new byte[(int) m];
                try { ByteSourceInverse.copyBytes(new Src(n), dst); } catch (Throwable t) { e = t.getClass().getName(); }
                boolean shouldThrow = n > m;
                check("control-copyBytes-n" + n + "-M" + m, shouldThrow ? "java.lang.ArrayIndexOutOfBoundsException".equals(e) : e == null,
                      "exc=" + e + " throwExpected=" + shouldThrow);
            }
        p("STAGE4 info end mismatches=" + mismatches);
    }
}
