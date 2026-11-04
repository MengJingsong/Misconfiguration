import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.apache.cassandra.cache.SerializingCache;
import org.apache.cassandra.io.ISerializer;
import org.apache.cassandra.io.util.DataInputPlus;
import org.apache.cassandra.io.util.DataOutputPlus;
import com.github.benmanes.caffeine.cache.Weigher;
import org.apache.cassandra.cache.RefCountedMemory;

/**
 * Unit tier of row_cache_size-create-serialized_size--autonomous (B2 as amended B2i).
 * Plain main. Usage: java ... SerializingCacheCapTest <outfile> [scale]   (scale: shakedown divisor for N / phase seconds)
 * Output: one line per observation, "OBS key=value ..." in <outfile>; analyze_unit.py reads it.
 */
public class SerializingCacheCapTest
{
    static final long MiB = 1024L * 1024;
    static PrintWriter out;
    static int SCALE = 1;

    static class BytesSer implements ISerializer<byte[]>
    {
        public void serialize(byte[] v, DataOutputPlus o) throws IOException { o.writeInt(v.length); o.write(v); }
        public byte[] deserialize(DataInputPlus in) throws IOException { int n = in.readInt(); byte[] b = new byte[n]; in.readFully(b); return b; }
        public long serializedSize(byte[] v) { return 4L + v.length; }
    }
    /** reports an absurd serialized size without any allocation (B2f: the 2^31 check) */
    static class HugeSer extends BytesSer
    {
        public long serializedSize(byte[] v) { return 1L << 31; }
    }

    static long rssAnon() throws IOException
    {
        for (String l : Files.readAllLines(Paths.get("/proc/self/status")))
            if (l.startsWith("RssAnon:")) return Long.parseLong(l.replaceAll("[^0-9]", "")) * 1024;
        return -1;
    }
    static long vmRss() throws IOException
    {
        for (String l : Files.readAllLines(Paths.get("/proc/self/status")))
            if (l.startsWith("VmRSS:")) return Long.parseLong(l.replaceAll("[^0-9]", "")) * 1024;
        return -1;
    }
    static void obs(String s) { out.println("OBS " + s); out.flush(); System.out.println("OBS " + s); }

    static void settle() throws Exception { System.gc(); Thread.sleep(300); System.gc(); Thread.sleep(300); }

    static void point(long C, int S, int rep, long phaseMs) throws Exception
    {
        String tag = "C=" + (C / MiB) + "MiB S=" + S + " rep=" + rep;
        settle();
        long base = rssAnon(), baseV = vmRss();
        SerializingCache<Integer, byte[]> cache = SerializingCache.create(C, new BytesSer());
        int N = (int) Math.max(1, Math.ceil(4.0 * C / S) / SCALE);
        long peakRss = base;
        byte[] val = new byte[S];
        for (int i = 0; i < N; i++)
        {
            cache.put(i, val);
            if ((i & 63) == 0) peakRss = Math.max(peakRss, rssAnon());
        }
        long afterRss = rssAnon();
        peakRss = Math.max(peakRss, afterRss);
        obs(tag + " phase=fill N=" + N + " offered=" + (long) N * (S + 4) + " weighted=" + cache.weightedSize() + " cap=" + cache.capacity()
            + " size=" + cache.size() + " rssAnonDelta=" + (afterRss - base) + " peakRssDelta=" + (peakRss - base) + " vmRssDelta=" + (vmRss() - baseV));
        int hits = 0;
        for (int i = 0; i < N; i++) if (cache.get(i) != null) hits++;
        obs(tag + " phase=get hits=" + hits + " size=" + cache.size());

        // concurrent phase: 16 threads put random keys
        final AtomicBoolean stop = new AtomicBoolean();
        final AtomicLong maxW = new AtomicLong(), maxRss = new AtomicLong(rssAnon());
        final SerializingCache<Integer, byte[]> c = cache;
        Thread sampler = new Thread(() -> {
            try { while (!stop.get()) { maxW.accumulateAndGet(c.weightedSize(), Math::max); maxRss.accumulateAndGet(rssAnon(), Math::max); Thread.sleep(10); } } catch (Exception e) { }
        });
        sampler.start();
        List<Thread> ts = new ArrayList<>();
        final int NK = N;
        for (int t = 0; t < 16; t++)
        {
            final int seed = t;
            Thread th = new Thread(() -> {
                Random r = new Random(seed);
                byte[] v = new byte[S];
                long end = System.currentTimeMillis() + phaseMs;
                while (System.currentTimeMillis() < end) c.put(r.nextInt(NK * 4), v);
            });
            ts.add(th); th.start();
        }
        for (Thread th : ts) th.join();
        stop.set(true); sampler.join();
        long endRss = rssAnon();
        obs(tag + " phase=concurrent maxWeighted=" + maxW.get() + " finalWeighted=" + cache.weightedSize() + " cap=" + cache.capacity() + " size=" + cache.size()
            + " peakRssDelta=" + (maxRss.get() - base) + " endRssDelta=" + (endRss - base) + " threads=16 inflightBound=" + 16L * (S + 4));

        cache.setCapacity(C / 2);
        long afterHalf = rssAnon();
        obs(tag + " phase=setCapacityHalf weighted=" + cache.weightedSize() + " cap=" + cache.capacity() + " size=" + cache.size() + " rssAnonDelta=" + (afterHalf - base));
        cache.clear();
    }

    static void control(int rep) throws Exception
    {
        SerializingCache<Integer, byte[]> c = SerializingCache.create(4, (Weigher<Integer, RefCountedMemory>) (k, v) -> 1, new BytesSer());
        for (int S : new int[]{ 4096, 262144 })
        {
            c.clear();
            for (int i = 0; i < 64; i++) c.put(i, new byte[S]);
            obs("control=singleton S=" + S + " rep=" + rep + " size=" + c.size() + " weighted=" + c.weightedSize() + " cap=" + c.capacity());
        }
        SerializingCache<Integer, byte[]> z = SerializingCache.create(0, new BytesSer());
        for (int i = 0; i < 100; i++) z.put(i, new byte[4096]);
        obs("control=zero-capacity rep=" + rep + " size=" + z.size() + " weighted=" + z.weightedSize() + " cap=" + z.capacity());
        SerializingCache<Integer, byte[]> h = SerializingCache.create(64 * MiB, new HugeSer());
        String r;
        try { h.put(1, new byte[8]); r = "accepted size=" + h.size(); }
        catch (IllegalArgumentException e) { r = "IllegalArgumentException:" + e.getMessage().replace(' ', '_') + " size=" + h.size(); }
        obs("control=huge-entry rep=" + rep + " result=" + r);
    }

    static void clearArm(int rep) throws Exception
    {
        long C = 64 * MiB; int S = 262144;
        settle();
        long base = rssAnon();
        SerializingCache<Integer, byte[]> cache = SerializingCache.create(C, new BytesSer());
        byte[] v = new byte[S];
        int N = (int) (2 * C / S) / SCALE;
        for (int i = 0; i < N; i++) cache.put(i, v);
        long r1 = rssAnon();
        obs("clear rep=" + rep + " phase=fill1 weighted=" + cache.weightedSize() + " size=" + cache.size() + " rssAnonDelta=" + (r1 - base));
        cache.clear();
        settle();
        long r2 = rssAnon();
        obs("clear rep=" + rep + " phase=afterClear weighted=" + cache.weightedSize() + " size=" + cache.size() + " rssAnonDelta=" + (r2 - base));
        long peak = r2;
        for (int i = 0; i < N; i++) { cache.put(1000000 + i, v); if ((i & 15) == 0) peak = Math.max(peak, rssAnon()); }
        long r3 = rssAnon(); peak = Math.max(peak, r3);
        obs("clear rep=" + rep + " phase=fill2 weighted=" + cache.weightedSize() + " size=" + cache.size() + " rssAnonDelta=" + (r3 - base) + " peakRssDelta=" + (peak - base) + " cap=" + C);
        cache.clear();
    }

    /** Usage: <outfile> <scale> control <rep> | point <C_MiB> <S_bytes> <rep> | clear <rep>.  One JVM per invocation (B2i.8). */
    public static void main(String[] a) throws Exception
    {
        out = new PrintWriter(new FileWriter(a[0], true));
        SCALE = Integer.parseInt(a[1]);
        long phaseMs = SCALE > 1 ? 2000 : 20000;
        obs("start scale=" + SCALE + " phaseMs=" + phaseMs + " maxMemory=" + Runtime.getRuntime().maxMemory() + " java=" + System.getProperty("java.version") + " args=" + String.join(",", a));
        switch (a[2])
        {
            case "control": control(Integer.parseInt(a[3])); break;
            case "point": point(Long.parseLong(a[3]) * MiB, Integer.parseInt(a[4]), Integer.parseInt(a[5]), phaseMs); break;
            case "clear": clearArm(Integer.parseInt(a[3])); break;
            default: throw new IllegalArgumentException(a[2]);
        }
        out.close();
        System.exit(0);
    }
}
