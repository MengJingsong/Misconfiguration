/*
 * Stage-4 harness (unit tier B2, amended 2026-10-29) of none-readfully-dest_length--autonomous and none-read-count--autonomous.
 * Not upstream. Compiled by unit-run.sh into a separate directory (package org.apache.cassandra.index.sai.disk.v1.vector because the
 * RandomAccessReaderAdapter constructor is package-private); never copied into a source tree.
 *
 *   RaaProbe <label> <float|int> <N> <agent 0|1>
 * One JVM per (kind, N, pass). Arms: EMPTY, F1 (default MAX_SEGMENT_SIZE, check false), T1 (MAX_SEGMENT_SIZE=65536 set before the handle is
 * built, check true), F2, T2 (identical re-runs: noise floor). Start offset s = 65536 - min(2N,32768) bytes in both arms, inside region 0.
 * Window = ThreadMXBean.getThreadAllocatedBytes before/after ONE read call (the seek is outside). Then retained-heap blocks and controls.
 * Output: "STAGE4 ..." lines to stdout and to -Dstage4.out.
 */
package org.apache.cassandra.index.sai.disk.v1.vector;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileHandle;
import org.apache.cassandra.io.util.MmappedRegions;

public class RaaProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static PrintWriter out;
    static String label, kind;
    static int N, agent;
    static boolean isInt;
    static int checks, mismatches;
    static Object sink;

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

    static Path writeFile(Path dir) throws Exception
    {
        Path p = dir.resolve("raa-" + kind + ".bin");
        int n = 4 * 1024 * 1024;               // 4M elements = 16 MiB
        try (FileChannel ch = FileChannel.open(p, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE))
        {
            ByteBuffer bb = ByteBuffer.allocate(1 << 20);
            for (int base = 0; base < n; base += (1 << 18))
            {
                bb.clear();
                for (int i = 0; i < (1 << 18); i++)
                {
                    if (isInt) bb.putInt(base + i); else bb.putFloat((float) (base + i));
                }
                bb.flip();
                while (bb.hasRemaining()) ch.write(bb);
            }
        }
        return p;
    }

    static FileHandle handle(Path p, int seg)
    {
        int old = MmappedRegions.MAX_SEGMENT_SIZE;
        try
        {
            MmappedRegions.MAX_SEGMENT_SIZE = seg;
            return new FileHandle.Builder(new File(p.toString())).mmapped(true).complete();
        }
        finally { MmappedRegions.MAX_SEGMENT_SIZE = old; }
    }

    static float[] df; static int[] di;

    static void call(RandomAccessReaderAdapter r) throws Exception
    {
        if (isInt) r.read(di, 0, N); else r.readFully(df);
    }

    static boolean verify(RandomAccessReaderAdapter r, long start)
    {
        long first = start / 4;
        for (int i = 0; i < N; i++)
        {
            if (isInt) { if (di[i] != (int) (first + i)) return false; }
            else if (df[i] != (float) (first + i)) return false;
        }
        return r.getFilePointer() == start + 4L * N;
    }

    static int K()
    {
        if (N <= 1536) return 2000;
        if (N <= 16384) return 500;
        if (N <= 131072) return 100;
        return 20;
    }

    static long[] med(List<Long> v)
    {
        long[] a = new long[v.size()]; for (int i = 0; i < a.length; i++) a[i] = v.get(i);
        Arrays.sort(a);
        return new long[]{ a[a.length / 2], a[0], a[a.length - 1] };
    }

    /** one arm: warm-up 2K, then 5 reps x K calls; returns the median of the rep medians */
    static long arm(String name, RandomAccessReaderAdapter r, long start) throws Exception
    {
        int k = K();
        long h0 = stage4.Count.get();
        int calls = 0;
        for (int i = 0; i < 2 * k; i++) { r.seek(start); call(r); calls++; }
        List<Long> repMed = new ArrayList<>(); List<Long> all = new ArrayList<>();
        boolean dataOk = true;
        for (int rep = 0; rep < 5; rep++)
        {
            List<Long> v = new ArrayList<>(k);
            for (int i = 0; i < k; i++)
            {
                r.seek(start);
                long a0 = alloc();
                call(r);
                long a1 = alloc();
                calls++;
                if (i == 0) dataOk &= verify(r, start);
                v.add(a1 - a0);
            }
            long[] m = med(v);
            repMed.add(m[0]); all.addAll(v);
            say("STAGE4 rep " + label + " kind=" + kind + " N=" + N + " arm=" + name + " rep=" + rep + " med=" + m[0] + " min=" + m[1] + " max=" + m[2]);
        }
        long[] mm = med(repMed), ma = med(all);
        long hits = stage4.Count.get() - h0;
        say("STAGE4 arm " + label + " kind=" + kind + " N=" + N + " arm=" + name + " agent=" + agent + " calls=" + calls + " hits=" + hits
            + " repmedian=" + mm[0] + " repmin=" + mm[1] + " repmax=" + mm[2] + " allmin=" + ma[1] + " allmax=" + ma[2] + " data=" + (dataOk ? "ok" : "BAD"));
        check("data " + name, "ok", dataOk ? "ok" : "BAD");
        return mm[0];
    }

    static long retained(String name, RandomAccessReaderAdapter r, long start, int m) throws Exception
    {
        long u0 = usedAfterGc();
        for (int i = 0; i < m; i++) { r.seek(start); call(r); }
        long u1 = usedAfterGc();
        say("STAGE4 retained " + label + " kind=" + kind + " N=" + N + " arm=" + name + " calls=" + m + " usedBefore=" + u0 + " usedAfter=" + u1 + " delta=" + (u1 - u0));
        return u1 - u0;
    }

    public static void main(String[] a) throws Exception
    {
        label = a[0]; kind = a[1]; N = Integer.parseInt(a[2]); agent = Integer.parseInt(a[3]);
        isInt = kind.equals("int");
        String o = System.getProperty("stage4.out");
        if (o != null) out = new PrintWriter(new FileWriter(o, true));
        DatabaseDescriptor.daemonInitialization();
        say("STAGE4 info " + label + " kind=" + kind + " N=" + N + " pass=" + (agent == 1 ? "B" : "A") + " java=" + System.getProperty("java.version") + " maxHeap=" + Runtime.getRuntime().maxMemory());
        df = new float[N]; di = new int[N];
        long start = 65536 - Math.min(2L * N, 32768);
        Path dir = Files.createTempDirectory(Path.of(System.getProperty("stage4.tmp", System.getProperty("java.io.tmpdir"))), "raa");
        Path p = writeFile(dir);
        FileHandle hF = handle(p, Integer.MAX_VALUE), hT = handle(p, 65536);
        RandomAccessReaderAdapter rF = new RandomAccessReaderAdapter(hF), rT = new RandomAccessReaderAdapter(hT);
        say("STAGE4 info " + label + " start=" + start + " fileLength=" + hF.channel.size() + " MAX_SEGMENT_SIZE_now=" + MmappedRegions.MAX_SEGMENT_SIZE);
        try
        {
            // EMPTY window (instrument)
            long e1, e2;
            { long x0 = alloc(); long x1 = alloc(); e1 = x1 - x0; x0 = alloc(); x1 = alloc(); e2 = x1 - x0; }
            say("STAGE4 empty " + label + " kind=" + kind + " N=" + N + " e1=" + e1 + " e2=" + e2);
            rF.seek(start); rT.seek(start);
            long f1 = arm("F1", rF, start), t1 = arm("T1", rT, start);
            long f2 = arm("F2", rF, start), t2 = arm("T2", rT, start);
            say("STAGE4 branch " + label + " kind=" + kind + " N=" + N + " F1=" + f1 + " T1=" + t1 + " F2=" + f2 + " T2=" + t2 + " T1-F1=" + (t1 - f1) + " 4N=" + (4L * N));
            if (agent == 0)
            {
                // controls
                List<Long> c1 = new ArrayList<>();
                for (int i = 0; i < 25; i++)
                {
                    long x0 = alloc(); sink = isInt ? (Object) new int[N] : (Object) new float[N]; long x1 = alloc();
                    if (i >= 5) c1.add(x1 - x0);
                }
                long[] mc = med(c1);
                say("STAGE4 c1 " + label + " kind=" + kind + " N=" + N + " median=" + mc[0] + " min=" + mc[1] + " max=" + mc[2]);
                sink = null;
                int m = (int) Math.max(200, Math.min(20000, (1L << 30) / (4L * N)));
                retained("F", rF, start, m);
                retained("T", rT, start, m);
                // C2: retention control, 100 MiB of arrays kept alive
                int cnt = (int) Math.min(250000, (100L << 20) / (16 + 4L * N));
                long u0 = usedAfterGc();
                Object[] keep = new Object[cnt];
                for (int i = 0; i < cnt; i++) keep[i] = isInt ? (Object) new int[N] : (Object) new float[N];
                long u1 = usedAfterGc();
                say("STAGE4 c2 " + label + " kind=" + kind + " N=" + N + " arrays=" + cnt + " usedBefore=" + u0 + " usedAfter=" + u1 + " delta=" + (u1 - u0) + " keepLen=" + keep.length);
                keep = null;
            }
        }
        finally
        {
            say("STAGE4 summary " + label + " kind=" + kind + " N=" + N + " checks=" + checks + " mismatches=" + mismatches);
            rF.close(); rT.close(); hF.close(); hT.close();
            try (var s = Files.walk(dir)) { s.sorted(java.util.Comparator.reverseOrder()).forEach(q -> q.toFile().delete()); }
        }
    }
}
