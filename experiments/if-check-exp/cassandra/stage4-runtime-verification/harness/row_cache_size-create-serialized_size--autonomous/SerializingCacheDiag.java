import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import com.sun.jna.Library;
import com.sun.jna.Native;
import org.apache.cassandra.cache.SerializingCache;
import org.apache.cassandra.io.ISerializer;
import org.apache.cassandra.io.util.DataInputPlus;
import org.apache.cassandra.io.util.DataOutputPlus;

/** POST-HOC diagnostic (written after unit run 1 showed a large RssAnon peak in the 16-thread phase; not a B2f reading).
 *  Usage: SerializingCacheDiag <outfile> <C_MiB> <S_bytes> <threads> <seconds>
 *  Samples weightedSize, size()*(S+4) (entries present incl. those awaiting eviction), RssAnon every 250 ms; at the end reads RssAnon before and after glibc malloc_trim(0). */
public class SerializingCacheDiag
{
    public interface CLib extends Library { int malloc_trim(long pad); }
    static class BytesSer implements ISerializer<byte[]>
    {
        public void serialize(byte[] v, DataOutputPlus o) throws IOException { o.writeInt(v.length); o.write(v); }
        public byte[] deserialize(DataInputPlus in) throws IOException { int n = in.readInt(); byte[] b = new byte[n]; in.readFully(b); return b; }
        public long serializedSize(byte[] v) { return 4L + v.length; }
    }
    static long rssAnon() throws IOException
    {
        for (String l : Files.readAllLines(Paths.get("/proc/self/status"))) if (l.startsWith("RssAnon:")) return Long.parseLong(l.replaceAll("[^0-9]", "")) * 1024;
        return -1;
    }
    public static void main(String[] a) throws Exception
    {
        PrintWriter out = new PrintWriter(new FileWriter(a[0], true));
        final long MiB = 1024 * 1024; final long C = Long.parseLong(a[1]) * MiB; final int S = Integer.parseInt(a[2]); int T = Integer.parseInt(a[3]); long ms = Long.parseLong(a[4]) * 1000;
        String tag = "C=" + a[1] + "MiB S=" + S + " threads=" + T + " arenaMax=" + System.getenv("MALLOC_ARENA_MAX");
        CLib clib = Native.load("c", CLib.class);
        System.gc(); Thread.sleep(300); System.gc();
        long base = rssAnon();
        final SerializingCache<Integer, byte[]> cache = SerializingCache.create(C, new BytesSer());
        final int NK = (int) (4 * C / S);
        final AtomicBoolean stop = new AtomicBoolean();
        List<Thread> ts = new ArrayList<>();
        for (int t = 0; t < T; t++)
        {
            final int seed = t;
            Thread th = new Thread(() -> { Random r = new Random(seed); byte[] v = new byte[S]; while (!stop.get()) cache.put(r.nextInt(NK), v); });
            ts.add(th); th.start();
        }
        long end = System.currentTimeMillis() + ms; long maxR = 0, maxEntB = 0, maxW = 0;
        while (System.currentTimeMillis() < end)
        {
            Thread.sleep(250);
            long r = rssAnon() - base, eb = (long) cache.size() * (S + 4), w = cache.weightedSize();
            maxR = Math.max(maxR, r); maxEntB = Math.max(maxEntB, eb); maxW = Math.max(maxW, w);
            out.println("SAMPLE " + tag + " t=" + (System.currentTimeMillis() - (end - ms)) + " weighted=" + w + " entryBytes=" + eb + " size=" + cache.size() + " rssDelta=" + r); 
        }
        stop.set(true); for (Thread th : ts) th.join();
        long before = rssAnon() - base; int rc = clib.malloc_trim(0); long after = rssAnon() - base;
        out.println("DIAG " + tag + " maxWeighted=" + maxW + " maxEntryBytes=" + maxEntB + " maxRssDelta=" + maxR + " endWeighted=" + cache.weightedSize() + " endEntryBytes=" + (long) cache.size() * (S + 4)
            + " rssDeltaBeforeTrim=" + before + " rssDeltaAfterTrim=" + after + " trimRc=" + rc + " cap=" + C);
        out.close(); System.exit(0);
    }
}
