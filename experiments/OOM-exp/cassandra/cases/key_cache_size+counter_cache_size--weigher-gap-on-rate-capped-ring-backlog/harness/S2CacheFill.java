// R11 (2026-11-20): R8 S2CacheFill with -Dvrange=<token>: candidate index i -> 8-byte key mix64(i); the key is KEPT only
// if its Murmur3 token (MurmurHash.hash3_x64_128(k,0,8,0)[0], Long.MIN_VALUE normalized to Long.MAX_VALUE, as
// Murmur3Partitioner) is > vrange (V's primary range when V holds token -2^63 and the highest other token is vrange).
// The j-th kept key is fill key j; <first> <count> index the kept keys. At start, the first 1,000 kept keys must have
// driver replicas {V} and 1,000 rejected keys must not (else RANGEFAIL, exit 4). -Dvip = V's address (10.10.1.4).
// R8/S2/B7 header: java S2CacheFill <mode> <table> <keyBytes> <first> <count> <concurrency>
//   mode counter: UPDATE ks.<table> SET c = c + 1 WHERE k = ? | insert: INSERT INTO ks.<table> (k, v) VALUES (?, 1)
//        read: SELECT v FROM ks.<table> WHERE k = ?   (CL ONE; default token-aware policy routes to the replica)
//   key = 8-byte big-endian mix64(i) (SplitMix64 finalizer), then 0x5A padding to keyBytes.
import com.datastax.driver.core.*;
import com.google.common.util.concurrent.*;
import org.apache.cassandra.utils.MurmurHash;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class S2CacheFill {
    static long mix64(long z) {
        z = (z ^ (z >>> 30)) * 0xbf58476d1ce4e5b9L;
        z = (z ^ (z >>> 27)) * 0x94d049bb133111ebL;
        return z ^ (z >>> 31);
    }
    static ByteBuffer key(long i, int keyBytes) {
        ByteBuffer k = ByteBuffer.allocate(keyBytes); k.putLong(mix64(i));
        while (k.hasRemaining()) k.put((byte) 0x5A); k.flip(); return k;
    }
    static long token(ByteBuffer k) {
        long[] r = new long[2]; MurmurHash.hash3_x64_128(k, k.position(), k.remaining(), 0, r);
        return r[0] == Long.MIN_VALUE ? Long.MAX_VALUE : r[0];
    }

    public static void main(String[] a) throws Exception {
        String mode = a[0], table = a[1];
        int keyBytes = Integer.parseInt(a[2]);
        long first = Long.parseLong(a[3]), count = Long.parseLong(a[4]);
        int conc = Integer.parseInt(a[5]);
        long vrange = Long.parseLong(System.getProperty("vrange"));
        String vip = System.getProperty("vip", "10.10.1.4"), ks = System.getProperty("ks", "s2c");
        if (keyBytes < 8) throw new IllegalArgumentException("keyBytes >= 8");
        Cluster cl = Cluster.builder().addContactPoint(System.getProperty("host", "10.10.1.4"))
            .withQueryOptions(new QueryOptions().setConsistencyLevel(ConsistencyLevel.ONE))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000))
            .withPoolingOptions(new PoolingOptions().setMaxRequestsPerConnection(HostDistance.LOCAL, 2048))
            .build();
        Session s = cl.connect();
        // range check
        int keptChk = 0, rejChk = 0; long i0 = 0;
        Metadata md = cl.getMetadata();
        while (keptChk < 1000 || rejChk < 1000) {
            ByteBuffer k = key(i0++, keyBytes); boolean kept = token(k) > vrange;
            Set<Host> rep = md.getReplicas(ks, k);
            boolean isV = rep.size() == 1 && rep.iterator().next().getAddress().getHostAddress().equals(vip);
            if (kept && keptChk < 1000) { if (!isV) { System.out.println("RANGEFAIL kept key i=" + (i0 - 1) + " replicas=" + rep); System.exit(4); } keptChk++; }
            if (!kept && rejChk < 1000) { if (isV || rep.isEmpty()) { System.out.println("RANGEFAIL rejected key i=" + (i0 - 1) + " replicas=" + rep); System.exit(4); } rejChk++; }
        }
        System.out.println("RANGEOK kept=" + keptChk + " rejected=" + rejChk + " candidates=" + i0);
        String q;
        switch (mode) {
            case "counter": q = "UPDATE " + ks + "." + table + " SET c = c + 1 WHERE k = ?"; break;
            case "insert":  q = "INSERT INTO " + ks + "." + table + " (k, v) VALUES (?, 1)"; break;
            case "read":    q = "SELECT v FROM " + ks + "." + table + " WHERE k = ?"; break;
            default: throw new IllegalArgumentException(mode);
        }
        PreparedStatement ps = s.prepare(q);
        Semaphore sem = new Semaphore(conc);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), rows = new AtomicLong();
        AtomicReference<Throwable> lastErr = new AtomicReference<>();
        long t0 = System.nanoTime(), lastPrint = t0;
        long i = 0, j = 0;   // i candidate index, j kept index
        while (j < first + count) {
            ByteBuffer k = key(i++, keyBytes);
            if (token(k) <= vrange) continue;
            long jj = j++;
            if (jj < first) continue;
            sem.acquire();
            ResultSetFuture f = s.executeAsync(ps.bind(k));
            Futures.addCallback(f, new FutureCallback<ResultSet>() {
                public void onSuccess(ResultSet r) { ok.incrementAndGet(); if (r.one() != null) rows.incrementAndGet(); sem.release(); }
                public void onFailure(Throwable t) { err.incrementAndGet(); lastErr.set(t); sem.release(); }
            }, MoreExecutors.directExecutor());
            long now = System.nanoTime();
            if (now - lastPrint > 5_000_000_000L) {
                lastPrint = now;
                System.out.printf("progress j=%d ok=%d err=%d rows=%d secs=%.1f%n", jj - first, ok.get(), err.get(), rows.get(), (now - t0) / 1e9);
            }
        }
        sem.acquire(conc);
        double secs = (System.nanoTime() - t0) / 1e9;
        System.out.printf("DONE mode=%s table=%s keyBytes=%d first=%d count=%d candidates=%d ok=%d err=%d rows=%d secs=%.1f ops/s=%.0f%n",
                          mode, table, keyBytes, first, count, i, ok.get(), err.get(), rows.get(), secs, ok.get() / secs);
        if (lastErr.get() != null) System.out.println("last error: " + lastErr.get());
        cl.close();
    }
}
