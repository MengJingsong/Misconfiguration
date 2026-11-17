// U1 load generator (derived from S1Load / C1Load). Java driver 3.x, protocol v4, async INSERTs to one node.
// "Concurrent writers" = client connections, one per source IP (-Dsrcips=127.0.0.101,...; each Cluster binds its
// connections to that local address, so Cassandra's per-client-IP in-flight limit applies per writer, as with
// separate application hosts). Each writer keeps at most <inflight> requests outstanding; one shared RateLimiter
// caps the TOTAL offered rate. Keys cycle modulo -Dkeys (overwrite, bounded data). Values are zero-filled blobs.
//   java U1Load schema <host>
//   java U1Load run <blobBytes> <inflightPerWriter> <seconds> <totalRatePerSec> <host>
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.datastax.shaded.netty.bootstrap.Bootstrap;
import com.google.common.util.concurrent.*;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class U1Load {
    static final int KEYS = Integer.getInteger("keys", 200);
    static Cluster cluster(String host, String src) {
        Cluster.Builder b = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000))
            .withPoolingOptions(new PoolingOptions().setMaxRequestsPerConnection(HostDistance.LOCAL, 2048)
                .setConnectionsPerHost(HostDistance.LOCAL, 1, 1))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withoutJMXReporting();
        if (src != null) b.withNettyOptions(new NettyOptions() {
            @Override public void afterBootstrapInitialized(Bootstrap bs) { bs.localAddress(new InetSocketAddress(src, 0)); }
        });
        return b.build();
    }

    public static void main(String[] a) throws Exception {
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(a[1], null); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS u1 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS u1.t (pk int PRIMARY KEY, b blob)");
                System.out.println("schema ok");
            }
            return;
        }
        int size = Integer.parseInt(a[1]); int inflight = Integer.parseInt(a[2]);
        long secs = Long.parseLong(a[3]); double rate = Double.parseDouble(a[4]); String host = a[5];
        String[] srcs = System.getProperty("srcips", "").isEmpty() ? new String[]{null} : System.getProperty("srcips").split(",");
        final RateLimiter rl = RateLimiter.create(rate);
        final ByteBuffer val = ByteBuffer.wrap(new byte[size]);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), sent = new AtomicLong();
        ConcurrentHashMap<String, AtomicLong> errs = new ConcurrentHashMap<>();
        AtomicInteger key = new AtomicInteger();
        List<Thread> ts = new ArrayList<>(); List<Cluster> cs = new ArrayList<>();
        long end = System.nanoTime() + secs * 1_000_000_000L;
        for (String src : srcs) {
            Cluster c = cluster(host, src); cs.add(c); Session s = c.connect();
            PreparedStatement ps = s.prepare("INSERT INTO u1.t (pk, b) VALUES (?, ?)");
            ps.setConsistencyLevel(ConsistencyLevel.ONE);
            Thread t = new Thread(() -> {
                Semaphore sem = new Semaphore(inflight);
                while (System.nanoTime() < end) {
                    try { if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue; } catch (InterruptedException e) { return; }
                    rl.acquire();
                    BoundStatement bs = ps.bind().setInt(0, Math.floorMod(key.getAndIncrement(), KEYS)).setBytesUnsafe(1, val.duplicate());
                    ResultSetFuture f = s.executeAsync(bs); sent.incrementAndGet();
                    Futures.addCallback(f, new FutureCallback<ResultSet>() {
                        public void onSuccess(ResultSet r) { ok.incrementAndGet(); sem.release(); }
                        public void onFailure(Throwable e) { err.incrementAndGet(); errs.computeIfAbsent(e.getClass().getSimpleName(), k -> new AtomicLong()).incrementAndGet(); sem.release(); }
                    }, MoreExecutors.directExecutor());
                }
                try { sem.tryAcquire(inflight, 70, TimeUnit.SECONDS); } catch (InterruptedException e) {}
            });
            ts.add(t);
        }
        long t0 = System.nanoTime();
        for (Thread t : ts) t.start();
        Thread rep = new Thread(() -> {
            long last = 0, lastS = 0;
            while (true) {
                try { Thread.sleep(5000); } catch (InterruptedException e) { return; }
                long o = ok.get(), sn = sent.get();
                System.out.printf("[%tT] t=%ds sent=%d (%.1f/s) ok=%d (%.1f/s) err=%d %s%n", new Date(), (System.nanoTime() - t0) / 1_000_000_000L,
                    sn, (sn - lastS) / 5.0, o, (o - last) / 5.0, err.get(), errs); last = o; lastS = sn;
            }
        });
        rep.setDaemon(true); rep.start();
        for (Thread t : ts) t.join();
        double el = (System.nanoTime() - t0) / 1e9;
        System.out.printf("FINAL sent=%d ok=%d err=%d elapsed=%.0fs ok_rate=%.2f/s ok_MiBps=%.1f errs=%s%n", sent.get(), ok.get(), err.get(), el, ok.get() / el, ok.get() * (double) size / el / 1048576, errs);
        for (Cluster c : cs) c.close();
        System.exit(0);
    }
}
