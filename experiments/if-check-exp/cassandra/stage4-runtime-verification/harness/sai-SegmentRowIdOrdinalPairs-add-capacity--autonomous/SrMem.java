import java.lang.management.ManagementFactory;
import io.github.jbellis.jvector.graph.NeighborSimilarity;
import org.apache.cassandra.index.sai.disk.v1.vector.SegmentRowIdOrdinalPairs;

/**
 * Unit tier of sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous (B2c-B2e). One JVM per (mode, N).
 * usage: SrMem pairs|plain <N> <rep>
 * pairs: new SegmentRowIdOrdinalPairs(N); plain: new int[2*N] (baseline control). Prints one line "RESULT k=v ...".
 * alloc_ctor = bytes the constructing thread allocated across the constructor call (com.sun.management.ThreadMXBean);
 * alloc_obj_plus_arr = same across "new" (object + array) -- measured by constructing a second, identical object after warm-up.
 */
public class SrMem
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static long tb() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }
    static long used() { for (int i = 0; i < 3; i++) System.gc(); Runtime r = Runtime.getRuntime(); return r.totalMemory() - r.freeMemory(); }
    static Object sink;

    public static void main(String[] a) throws Exception
    {
        String mode = a[0]; int n = Integer.parseInt(a[1]); int rep = Integer.parseInt(a[2]);
        StringBuilder sb = new StringBuilder("RESULT mode=" + mode + " N=" + n + " rep=" + rep
            + " ea=" + SrMem.class.desiredAssertionStatus() + " maxheap=" + Runtime.getRuntime().maxMemory());
        // warm-up: load classes, JIT the constructor path (not the measured N)
        if (mode.equals("pairs")) { for (int i = 0; i < 2000; i++) sink = new SegmentRowIdOrdinalPairs(1); }
        else { for (int i = 0; i < 2000; i++) sink = new int[2]; }
        sink = null;
        long u0 = n >= 1000000 ? used() : -1;
        long b0 = tb();
        Object o;
        try
        {
            o = mode.equals("pairs") ? new SegmentRowIdOrdinalPairs(n) : (Object) new int[2 * n];
        }
        catch (Throwable t)
        {
            sb.append(" ctor_throw=").append(t.getClass().getName()).append(" msg=").append(String.valueOf(t.getMessage()).replace(' ', '_'));
            System.out.println(sb);
            return;
        }
        long b1 = tb();
        sink = o;
        sb.append(" ctor_ok=true alloc_ctor_plus_new=").append(b1 - b0).append(" formula_16_8N=").append(16L + 8L * n);
        if (n >= 1000000) { long u1 = used(); sb.append(" retained_delta=").append(u1 - u0); }
        if (mode.equals("pairs") && n <= 100000000)
        {
            SegmentRowIdOrdinalPairs p = (SegmentRowIdOrdinalPairs) o;
            long t0 = System.nanoTime();
            for (int i = 0; i < n; i++) p.add(i, i);
            sb.append(" adds_ms=").append((System.nanoTime() - t0) / 1000000).append(" size=").append(p.size());
            try { p.add(n, n); sb.append(" add_n1=NO_THROW"); }
            catch (Throwable t) { sb.append(" add_n1=").append(t.getClass().getName()).append(":").append(t.getMessage()); }
            sb.append(" size_after=").append(p.size());
            if (n <= 100000000)
            {
                NeighborSimilarity.ScoreFunction sf = new NeighborSimilarity.ScoreFunction()
                {
                    public boolean isExact() { return true; }
                    public float similarityTo(int ord) { return 1f / (1 + ord); }
                };
                long m0 = tb();
                try
                {
                    Object q = p.mapToSegmentRowIdScoreHeap(sf);
                    sb.append(" map_alloc=").append(tb() - m0).append(" queue=").append(q.getClass().getSimpleName());
                    sink = q;
                }
                catch (Throwable t) { sb.append(" map_throw=").append(t.getClass().getName()); }
            }
        }
        System.out.println(sb);
    }
}
