// U1 run 2 load generator (from run 1's U1Load). Java driver 3.12.1, protocol v4, async INSERTs.
// Runs on a coordinator node and talks ONLY to that node's coordinator (whitelist), which forwards each mutation over
// internode messaging to the victim V (the only replica, keyspace u1r2 = NTS {v:1}). The victim never sees a client
// request frame. "Writers" = client connections (one Cluster each); each keeps at most <inflight> requests outstanding;
// one shared RateLimiter caps the client's total offered rate (0 = no cap). Keys cycle modulo -Dkeys (overwrite,
// bounded data). Values are zero-filled blobs. No driver retries.
//   java U1R2Load schema <host> <replication-map>      e.g. "{'class':'NetworkTopologyStrategy','v':1}"
//   java U1R2Load run <blobBytes> <inflightPerWriter> <seconds> <totalRatePerSec|0> <host>   (-Dwriters=N, -Dkeys=K)
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class U1R2Load {
    static final int KEYS = Integer.getInteger("keys", 200);
    static Cluster cluster(String host) {
        return Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000).setConnectTimeoutMillis(10000))
            .withPoolingOptions(new PoolingOptions().setMaxRequestsPerConnection(HostDistance.LOCAL, 2048)
                .setConnectionsPerHost(HostDistance.LOCAL, 1, 1).setConnectionsPerHost(HostDistance.REMOTE, 1, 1)
                .setMaxRequestsPerConnection(HostDistance.REMOTE, 2048))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withoutJMXReporting().build();
    }

    public static void main(String[] a) throws Exception {
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(a[1]); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS u1r2 WITH replication = " + a[2]);
                s.execute("CREATE TABLE IF NOT EXISTS u1r2.t (pk int PRIMARY KEY, b blob)");
                System.out.println("schema ok " + a[2]);
            }
            return;
        }
        int size = Integer.parseInt(a[1]); int inflight = Integer.parseInt(a[2]);
        long secs = Long.parseLong(a[3]); double rate = Double.parseDouble(a[4]); String host = a[5];
        int writers = Integer.getInteger("writers", 1);
        final RateLimiter rl = rate > 0 ? RateLimiter.create(rate) : null;
        final ByteBuffer val = ByteBuffer.wrap(new byte[size]);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), sent = new AtomicLong();
        ConcurrentHashMap<String, AtomicLong> errs = new ConcurrentHashMap<>();
        AtomicInteger key = new AtomicInteger(new Random().nextInt(KEYS));
        List<Thread> ts = new ArrayList<>(); List<Cluster> cs = new ArrayList<>();
        long end = System.nanoTime() + secs * 1_000_000_000L;
        for (int w = 0; w < writers; w++) {
            Cluster c = cluster(host); cs.add(c); Session s = c.connect();
            PreparedStatement ps = s.prepare("INSERT INTO u1r2.t (pk, b) VALUES (?, ?)");
            ps.setConsistencyLevel(ConsistencyLevel.ONE);
            Thread t = new Thread(() -> {
                Semaphore sem = new Semaphore(inflight);
                while (System.nanoTime() < end) {
                    try { if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue; } catch (InterruptedException e) { return; }
                    if (rl != null) rl.acquire();
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
        System.out.printf("[%tT] start epoch_ms=%d writers=%d inflight/writer=%d blob=%d rate=%s%n", new Date(), System.currentTimeMillis(), writers, inflight, size, rate);
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
