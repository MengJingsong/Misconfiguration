// B6 run-2 load generator (Java driver 3.x, async). One session per coordinator, each whitelisted
// to its own coordinator, so every coordinator sends to the replicas independently.
//   java B6Load schema <host>
//   java B6Load run <map|blob> <size> <inflightPerHost> <seconds> <pk0> <host1,host2,...>
// The map/blob value is serialized ONCE and bound with setBytesUnsafe (no per-insert encoding).
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B6Load {
    static Cluster cluster(String host) {
        return Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000))
            .withPoolingOptions(new PoolingOptions().setMaxRequestsPerConnection(HostDistance.LOCAL, 2048))
            .withoutJMXReporting().build();
    }

    public static void main(String[] a) throws Exception {
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(a[1]); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS b6 WITH replication = {'class':'NetworkTopologyStrategy','v':1,'f':1}");
                s.execute("CREATE TABLE IF NOT EXISTS b6.t_map (pk int PRIMARY KEY, m map<int,int>)");
                s.execute("CREATE TABLE IF NOT EXISTS b6.t_blob (pk int PRIMARY KEY, b blob)");
                System.out.println("schema ok");
            }
            return;
        }
        String kind = a[1]; int size = Integer.parseInt(a[2]); int inflight = Integer.parseInt(a[3]);
        long secs = Long.parseLong(a[4]); int pk0 = Integer.parseInt(a[5]); String[] hosts = a[6].split(",");
        ByteBuffer val;
        if (kind.equals("map")) {
            Map<Integer, Integer> m = new HashMap<>();
            for (int i = 0; i < size; i++) m.put(i, i);
            val = TypeCodec.map(TypeCodec.cint(), TypeCodec.cint()).serialize(m, ProtocolVersion.V4);
        } else {
            byte[] b = new byte[size]; new Random(1).nextBytes(b); val = ByteBuffer.wrap(b);
        }
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), sent = new AtomicLong();
        AtomicReference<String> lastErr = new AtomicReference<>("");
        List<Thread> ts = new ArrayList<>(); List<Cluster> cs = new ArrayList<>();
        long end = System.nanoTime() + secs * 1_000_000_000L;
        for (int h = 0; h < hosts.length; h++) {
            Cluster c = cluster(hosts[h]); cs.add(c); Session s = c.connect();
            PreparedStatement ps = s.prepare(kind.equals("map") ? "INSERT INTO b6.t_map (pk, m) VALUES (?, ?)"
                                                               : "INSERT INTO b6.t_blob (pk, b) VALUES (?, ?)");
            ps.setConsistencyLevel(ConsistencyLevel.ONE);
            final int base = pk0 + h * 100_000_000;
            Thread t = new Thread(() -> {
                Semaphore sem = new Semaphore(inflight); int pk = base;
                while (System.nanoTime() < end) {
                    sem.acquireUninterruptibly();
                    BoundStatement bs = ps.bind().setInt(0, pk++).setBytesUnsafe(1, val.duplicate());
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
            long last = 0;
            while (true) {
                try { Thread.sleep(5000); } catch (InterruptedException e) { return; }
                long o = ok.get();
                System.out.printf("[%tT] t=%ds sent=%d ok=%d (%.0f/s) err=%d %s%n", new Date(), (System.nanoTime() - t0) / 1_000_000_000L,
                    sent.get(), o, (o - last) / 5.0, err.get(), lastErr.get()); last = o;
            }
        });
        rep.setDaemon(true); rep.start();
        for (Thread t : ts) t.join();
        System.out.printf("FINAL sent=%d ok=%d err=%d %s%n", sent.get(), ok.get(), err.get(), lastErr.get());
        for (Cluster c : cs) c.close();
        System.exit(0);
    }
}
