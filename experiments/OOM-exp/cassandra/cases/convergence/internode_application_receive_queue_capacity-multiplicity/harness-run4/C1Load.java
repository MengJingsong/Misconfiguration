// C1 run-4 load generator (derived from B6 run-4 B6Load). Java driver 3.x, async.
// One Cluster/Session per ACTIVE coordinator, each whitelisted to that coordinator only, so the number
// of loaded inbound peers at the victim equals the number of hosts given. One shared RateLimiter caps the
// TOTAL offered rate (matched aggregate load across N). Keys cycle modulo KEYS (overwrite, bounded data).
//   java C1Load schema <host>
//   java C1Load run <blobBytes> <inflightPerHost> <seconds> <totalRatePerSec> <host1,host2,...>
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class C1Load {
    static final int KEYS = 2000;
    static Cluster cluster(String host) {
        return Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000))
            .withPoolingOptions(new PoolingOptions().setMaxRequestsPerConnection(HostDistance.LOCAL, 2048))
            .withoutJMXReporting().build();
    }

    public static void main(String[] a) throws Exception {
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(a[1]); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS c1 WITH replication = {'class':'NetworkTopologyStrategy','v':1,'f':1}");
                s.execute("CREATE TABLE IF NOT EXISTS c1.t (pk int PRIMARY KEY, b blob)");
                System.out.println("schema ok");
            }
            return;
        }
        int size = Integer.parseInt(a[1]); int inflight = Integer.parseInt(a[2]);
        long secs = Long.parseLong(a[3]); double rate = Double.parseDouble(a[4]); String[] hosts = a[5].split(",");
        final RateLimiter rl = RateLimiter.create(rate);
        byte[] b = new byte[size]; /* zero-filled: compressible on disk (sstables) -> bounded tmpfs volume */ final ByteBuffer val = ByteBuffer.wrap(b);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), sent = new AtomicLong();
        AtomicReference<String> lastErr = new AtomicReference<>("");
        AtomicInteger key = new AtomicInteger();
        List<Thread> ts = new ArrayList<>(); List<Cluster> cs = new ArrayList<>();
        long end = System.nanoTime() + secs * 1_000_000_000L;
        for (int h = 0; h < hosts.length; h++) {
            Cluster c = cluster(hosts[h]); cs.add(c); Session s = c.connect();
            PreparedStatement ps = s.prepare("INSERT INTO c1.t (pk, b) VALUES (?, ?)");
            ps.setConsistencyLevel(ConsistencyLevel.ONE);
            Thread t = new Thread(() -> {
                Semaphore sem = new Semaphore(inflight);
                while (System.nanoTime() < end) {
                    sem.acquireUninterruptibly(); rl.acquire();
                    BoundStatement bs = ps.bind().setInt(0, Math.floorMod(key.getAndIncrement(), KEYS)).setBytesUnsafe(1, val.duplicate());
                    ResultSetFuture f = s.executeAsync(bs); sent.incrementAndGet();
                    Futures.addCallback(f, new FutureCallback<ResultSet>() {
                        public void onSuccess(ResultSet r) { ok.incrementAndGet(); sem.release(); }
                        public void onFailure(Throwable e) { err.incrementAndGet(); lastErr.set(e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage())); sem.release(); }
                    }, MoreExecutors.directExecutor());
                }
                sem.acquireUninterruptibly(inflight);
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
                System.out.printf("[%tT] t=%ds sent=%d (%.0f/s) ok=%d (%.0f/s) err=%d %s%n", new Date(), (System.nanoTime() - t0) / 1_000_000_000L,
                    sn, (sn - lastS) / 5.0, o, (o - last) / 5.0, err.get(), lastErr.get()); last = o; lastS = sn;
            }
        });
        rep.setDaemon(true); rep.start();
        for (Thread t : ts) t.join();
        double el = (System.nanoTime() - t0) / 1e9;
        System.out.printf("FINAL sent=%d ok=%d err=%d elapsed=%.0fs ok_rate=%.1f/s %s%n", sent.get(), ok.get(), err.get(), el, ok.get() / el, lastErr.get());
        for (Cluster c : cs) c.close();
        System.exit(0);
    }
}
