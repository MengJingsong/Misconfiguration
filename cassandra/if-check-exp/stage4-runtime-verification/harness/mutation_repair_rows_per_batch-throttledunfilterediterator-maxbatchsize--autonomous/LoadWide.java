import java.nio.ByteBuffer;
import java.util.Random;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicLong;

import com.datastax.driver.core.Cluster;
import com.datastax.driver.core.PreparedStatement;
import com.datastax.driver.core.ResultSetFuture;
import com.datastax.driver.core.Session;

/**
 * java -cp <driver jar> LoadWide <host> <keyspace.table> <rows> <valueBytes> [pk=1] [concurrency=256]
 * Writes one wide partition: (pk, ck 0..rows-1, v = valueBytes random bytes), prepared INSERT, async, CL ONE.
 * Prints the rate and the number of failures; exit code 1 on any failure.
 */
public class LoadWide
{
    public static void main(String[] a) throws Exception
    {
        String host = a[0], table = a[1];
        int rows = Integer.parseInt(a[2]), vb = Integer.parseInt(a[3]);
        int pk = a.length > 4 ? Integer.parseInt(a[4]) : 1, conc = a.length > 5 ? Integer.parseInt(a[5]) : 256;
        try (Cluster cl = Cluster.builder().addContactPoint(host).build(); Session s = cl.connect())
        {
            PreparedStatement ps = s.prepare("INSERT INTO " + table + " (pk, ck, v) VALUES (?, ?, ?)");
            Semaphore sem = new Semaphore(conc);
            AtomicLong fail = new AtomicLong();
            Random r = new Random(42);
            long t0 = System.nanoTime();
            for (int i = 0; i < rows; i++)
            {
                sem.acquire();
                byte[] b = new byte[vb];
                r.nextBytes(b);
                ByteBuffer v = ByteBuffer.wrap(b);
                final ResultSetFuture f = s.executeAsync(ps.bind(pk, i, v));
                f.addListener(() -> {
                    try { f.get(); } catch (Exception e) { fail.incrementAndGet(); }
                    finally { sem.release(); }
                }, Runnable::run);
            }
            sem.acquire(conc);
            double sec = (System.nanoTime() - t0) / 1e9;
            System.out.println("LOADED table=" + table + " rows=" + rows + " valueBytes=" + vb + " failures=" + fail.get() + " seconds=" + sec + " rate=" + (long) (rows / sec));
            System.exit(fail.get() == 0 ? 0 : 1);
        }
    }
}
