import java.nio.ByteBuffer;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ArrayClustering;
import org.apache.cassandra.db.BufferClustering;
import org.apache.cassandra.db.Clustering;
import org.apache.cassandra.db.ClusteringPrefix;
import org.apache.cassandra.exceptions.InvalidRequestException;

/**
 * Stage-4 unit driver for max-unsigned-short-validate-sum--autonomous (B2 with amendments B2i; sum branch ClusteringPrefix.java:284).
 *   grid                       ClusteringPrefix.validate() on the S x N grid, mixed cells, null/empty/static, ArrayClustering;
 *                              the rule (B2i.2) decides the expected outcome and the exact message
 *   stream <M> <S1> <S2>       M fresh distinct two-component clusterings validated, none held; heap after a full GC
 *   series <S1> <S2> <step> <cap>  hold two-component clusterings (cap 0 = all, else the newest cap), heap after full GC at each step up to 10 steps
 * Output lines start with "STAGE4 ". Comparisons with a prediction print "STAGE4 check <what> ok|MISMATCH ...".
 */
public class ClusterKeyDriver
{
    static long heap()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(50); } catch (InterruptedException e) {} }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static void check(String what, boolean ok, String detail)
    {
        System.out.println("STAGE4 check " + what + (ok ? " ok" : " MISMATCH") + " " + detail);
    }

    static String run(ClusteringPrefix<?> c)
    {
        try { c.validate(); return "accepted"; }
        catch (InvalidRequestException e) { return "rejected:" + e.getMessage(); }
    }

    /** B2i.2: sizes of the components, -1 = null component. */
    static String expect(int... sizes)
    {
        long total = 0; boolean over = false;
        for (int s : sizes) { if (s > 0) total += s; if (s > 65535) over = true; }
        if (over || total > 65535) return "rejected:Key length of " + total + " is longer than maximum of 65535";
        return "accepted";
    }

    static ByteBuffer buf(int s) { return s < 0 ? null : ByteBuffer.allocate(s); }

    static void cell(String name, int... sizes)
    {
        ByteBuffer[] v = new ByteBuffer[sizes.length];
        for (int i = 0; i < v.length; i++) v[i] = buf(sizes[i]);
        String got = run(new BufferClustering(v)), want = expect(sizes);
        System.out.println("STAGE4 cell " + name + " got=" + got);
        check("cell " + name, got.equals(want), "want=" + want + " got=" + got);
    }

    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        System.out.println("STAGE4 info maxmemory=" + Runtime.getRuntime().maxMemory() + " java=" + System.getProperty("java.version"));
        switch (a[0])
        {
            case "grid":
            {
                int[] ss = { 1, 1000, 32767, 32768, 65534, 65535, 65536, 70000 };
                for (int s : ss)
                    for (int n = 1; n <= 3; n++)
                    {
                        int[] sizes = new int[n];
                        java.util.Arrays.fill(sizes, s);
                        cell("S=" + s + ",N=" + n, sizes);
                    }
                int[] n1000 = new int[65]; java.util.Arrays.fill(n1000, 1000); cell("S=1000,N=65", n1000);
                int[] n1001 = new int[66]; java.util.Arrays.fill(n1001, 1000); cell("S=1000,N=66", n1001);
                cell("mixed 65535+1", 65535, 1);
                cell("mixed 65535+0", 65535, 0);
                cell("mixed 65535+null", 65535, -1);
                cell("mixed 32768+32767", 32768, 32767);
                cell("mixed 32768+32768", 32768, 32768);
                cell("mixed 32767+32768+1", 32767, 32768, 1);
                cell("mixed 65536+1", 65536, 1);
                cell("mixed null+65536", -1, 65536);
                cell("mixed 1+70000", 1, 70000);
                String e = run(Clustering.EMPTY), st = run(Clustering.STATIC_CLUSTERING);
                System.out.println("STAGE4 cell EMPTY=" + e + " STATIC=" + st);
                check("cell Clustering.EMPTY", e.equals("accepted"), e);
                check("cell Clustering.STATIC_CLUSTERING", st.equals("accepted"), st);
                String g1 = run(new ArrayClustering(new byte[32768], new byte[32767])), w1 = expect(32768, 32767);
                check("cell ArrayClustering 32768+32767", g1.equals(w1), "want=" + w1 + " got=" + g1);
                String g2 = run(new ArrayClustering(new byte[32768], new byte[32768])), w2 = expect(32768, 32768);
                System.out.println("STAGE4 cell ArrayClustering 32768+32768 got=" + g2);
                check("cell ArrayClustering 32768+32768", g2.equals(w2), "want=" + w2 + " got=" + g2);
                break;
            }
            case "stream":
            {
                int m = Integer.parseInt(a[1]), s1 = Integer.parseInt(a[2]), s2 = Integer.parseInt(a[3]);
                long h0 = heap(), accepted = 0, rejected = 0, bytes = 0, t0 = System.nanoTime();
                for (int i = 0; i < m; i++)
                {
                    ByteBuffer b1 = ByteBuffer.allocate(s1), b2 = ByteBuffer.allocate(s2);
                    b1.putInt(0, i);
                    if (run(new BufferClustering(b1, b2)).equals("accepted")) accepted++; else rejected++;
                    bytes += s1 + s2;
                }
                long ms = (System.nanoTime() - t0) / 1000000, h1 = heap();
                System.out.println("STAGE4 stream m=" + m + " S=" + (s1 + s2) + " accepted=" + accepted + " rejected=" + rejected + " bytes_validated=" + bytes
                                   + " ms=" + ms + " heap_before=" + h0 + " heap_after=" + h1);
                check("stream all accepted", accepted == m && rejected == 0, "accepted=" + accepted + " rejected=" + rejected);
                check("stream heap after gc below 100 MB", h1 < 100_000_000L, "heap_after=" + h1);
                check("stream total bytes 100,000 times the per-key cap", bytes >= 100_000L * 65535, "bytes=" + bytes);
                break;
            }
            case "series":
            {
                // series <s1> <s2> <step> <cap>   10 samples at step, 2*step, ... 10*step
                int s1 = Integer.parseInt(a[1]), s2 = Integer.parseInt(a[2]), step = Integer.parseInt(a[3]), cap = Integer.parseInt(a[4]);
                int s = s1 + s2;
                List<Clustering<?>> keep = new ArrayList<>();
                ArrayDeque<Clustering<?>> ring = new ArrayDeque<>();
                long h0 = heap(); long[] h = new long[11]; int thrown = 0;
                for (int i = 1; i <= 10 * step; i++)
                {
                    ByteBuffer b1 = ByteBuffer.allocate(s1), b2 = ByteBuffer.allocate(s2);
                    if (s1 >= 4) b1.putInt(0, i); else b1.put(0, (byte) i);
                    BufferClustering c = new BufferClustering(b1, b2);
                    if (!run(c).equals("accepted")) thrown++;
                    if (cap == 0) keep.add(c); else { ring.addLast(c); if (ring.size() > cap) ring.removeFirst(); }
                    if (i % step == 0)
                    {
                        h[i / step] = heap();
                        System.out.println("STAGE4 series S=" + s + " cap=" + cap + " M=" + i + " heap=" + h[i / step] + " retained=" + (h[i / step] - h0));
                    }
                }
                double slope = (h[10] - h[1]) / (9.0 * step), mean = (h[10] - h[1]) / 9.0; boolean steady = true;
                for (int k = 2; k <= 10; k++) if (Math.abs((h[k] - h[k - 1]) - mean) > 0.10 * Math.abs(mean)) steady = false;
                System.out.println("STAGE4 series S=" + s + " cap=" + cap + " slope_bytes_per_key=" + slope + " delta_first_to_last=" + (h[10] - h[1]) + " delta_3_to_10=" + (h[10] - h[3]) + " thrown=" + thrown);
                check("series S=" + s + " cap=" + cap + " validate never threw", thrown == 0, "thrown=" + thrown);
                if (cap == 0)
                {
                    if (s > 1000) check("series S=" + s + " slope within S+40..S+300", slope >= s + 40 && slope <= s + 300, "slope=" + slope);
                    else check("series S=" + s + " slope below 600", slope < 600, "slope=" + slope);
                    check("series S=" + s + " every step within 10 percent of the mean step", steady, "");
                }
                else
                {
                    check("series S=" + s + " cap=" + cap + " heap at M=10*step within 10 MB of heap at M=3*step", Math.abs(h[10] - h[3]) < 10_000_000L, "delta=" + (h[10] - h[3]));
                }
                System.out.println("STAGE4 keep " + keep.size() + " " + ring.size());
                break;
            }
            default: throw new IllegalArgumentException(a[0]);
        }
    }
}
