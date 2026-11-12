// CacheFill.java - B7 (OOM-exp, 2026-11-11) workload client for filling Cassandra's key and counter caches
// through the real CQL path with entries of a chosen partition-key size.
//
// Usage: java -cp <cassandra lib/*>:. CacheFill <mode> <table> <keyBytes> <first> <count> <concurrency>
//   mode  counter : UPDATE b7.<table> SET c = c + 1 WHERE k = ?   (k blob; populates the counter cache, RF=1)
//         insert  : INSERT INTO b7.<table> (k, v) VALUES (?, 1)    (k blob)
//         read    : SELECT v FROM b7.<table> WHERE k = ?           (populates the key cache from the sstable index)
//   key i (first <= i < first+count) is a blob of exactly keyBytes bytes: the 8-byte big-endian mix64(i) (SplitMix64
//   finalizer, a bijection, so keys stay distinct), then 0x5A padding (keyBytes >= 8). Keys are visited in i order.
//   (Validation 2026-11-11: plain sequential i made Arrays.hashCode collide and the cache's ConcurrentHashMap treeify
//   its bins; scrambled keys spread like real partition keys.)
// Prints progress every 5 s and a final line: "DONE mode=.. ok=.. err=.. secs=.. ops/s=..".
// Uses the DataStax 3.x driver shipped in Cassandra's lib/ (cassandra-driver-core-3.12.1-shaded). CL = ONE.
import com.datastax.driver.core.*;
import com.google.common.util.concurrent.*;
import java.nio.ByteBuffer;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class CacheFill {
    static long mix64(long z) {
        z = (z ^ (z >>> 30)) * 0xbf58476d1ce4e5b9L;
        z = (z ^ (z >>> 27)) * 0x94d049bb133111ebL;
        return z ^ (z >>> 31);
    }

    public static void main(String[] a) throws Exception {
        String mode = a[0], table = a[1];
        int keyBytes = Integer.parseInt(a[2]);
        long first = Long.parseLong(a[3]), count = Long.parseLong(a[4]);
        int conc = Integer.parseInt(a[5]);
        if (keyBytes < 8) throw new IllegalArgumentException("keyBytes >= 8");
        Cluster cl = Cluster.builder().addContactPoint("127.0.0.1")
            .withQueryOptions(new QueryOptions().setConsistencyLevel(ConsistencyLevel.ONE))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000))
            .withPoolingOptions(new PoolingOptions().setMaxRequestsPerConnection(HostDistance.LOCAL, 2048))
            .build();
        Session s = cl.connect();
        String q;
        switch (mode) {
            case "counter": q = "UPDATE b7." + table + " SET c = c + 1 WHERE k = ?"; break;
            case "insert":  q = "INSERT INTO b7." + table + " (k, v) VALUES (?, 1)"; break;
            case "read":    q = "SELECT v FROM b7." + table + " WHERE k = ?"; break;
            default: throw new IllegalArgumentException(mode);
        }
        PreparedStatement ps = s.prepare(q);
        Semaphore sem = new Semaphore(conc);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), rows = new AtomicLong();
        AtomicReference<Throwable> lastErr = new AtomicReference<>();
        long t0 = System.nanoTime(), lastPrint = t0;
        for (long i = first; i < first + count; i++) {
            ByteBuffer k = ByteBuffer.allocate(keyBytes);
            k.putLong(mix64(i));
            while (k.hasRemaining()) k.put((byte) 0x5A);
            k.flip();
            sem.acquire();
            ResultSetFuture f = s.executeAsync(ps.bind(k));
            Futures.addCallback(f, new FutureCallback<ResultSet>() {
                public void onSuccess(ResultSet r) { ok.incrementAndGet(); if (r.one() != null) rows.incrementAndGet(); sem.release(); }
                public void onFailure(Throwable t) { err.incrementAndGet(); lastErr.set(t); sem.release(); }
            }, MoreExecutors.directExecutor());
            long now = System.nanoTime();
            if (now - lastPrint > 5_000_000_000L) {
                lastPrint = now;
                System.out.printf("progress i=%d ok=%d err=%d rows=%d secs=%.1f%n", i - first, ok.get(), err.get(), rows.get(), (now - t0) / 1e9);
            }
        }
        sem.acquire(conc);
        double secs = (System.nanoTime() - t0) / 1e9;
        System.out.printf("DONE mode=%s table=%s keyBytes=%d first=%d count=%d ok=%d err=%d rows=%d secs=%.1f ops/s=%.0f%n",
                          mode, table, keyBytes, first, count, ok.get(), err.get(), rows.get(), secs, ok.get() / secs);
        if (lastErr.get() != null) System.out.println("last error: " + lastErr.get());
        cl.close();
    }
}
