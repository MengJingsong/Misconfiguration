// R11 (2026-11-20): R8 S2Load plus -Dgate=host:port: connects to R11Gate on V before the first send (fail -> print
// GATEFAIL, exit 3); a reader thread sets a volatile stop on the line "STOP"; send loop runs while !stop && now < end;
// prints "STOP_RECEIVED t=<ms since first send> sent=<n> epochMs=<ms>" and "FIRST_SEND epochMs=". Keyspace b6 = NTS {c:3}
// (S2 G1), s2c = NTS {c:1}. The -Dtotal option of R8 is kept but unused.
// R8 (2026-11-17): S2 run-1 S2Load with (1) -Dtotal=N; (2) schema also creates keyspace s2c with tables kv and ctr;
// (3) FINAL line adds the first and last ok timestamps (epoch ms).
//   java S2Load schema <host>
//   java S2Load run <map|blob> <size> <inflightPerHost> <seconds> <pk0> <host1,host2,...> [ratePerSecondTotal]
// The blob value is serialized ONCE and bound with setBytesUnsafe (no per-insert encoding).
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.io.*;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class S2Load {
    static volatile boolean stop = false;
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
                s.execute("CREATE KEYSPACE IF NOT EXISTS b6 WITH replication = {'class':'NetworkTopologyStrategy','c':3}");
                s.execute("CREATE TABLE IF NOT EXISTS b6.t_blob (pk int PRIMARY KEY, b blob)");
                s.execute("CREATE KEYSPACE IF NOT EXISTS s2c WITH replication = {'class':'NetworkTopologyStrategy','c':1}");
                s.execute("CREATE TABLE IF NOT EXISTS s2c.kv (k blob PRIMARY KEY, v int)");
                s.execute("CREATE TABLE IF NOT EXISTS s2c.ctr (k blob PRIMARY KEY, c counter)");
                System.out.println("schema ok");
            }
            return;
        }
        String kind = a[1]; int size = Integer.parseInt(a[2]); int inflight = Integer.parseInt(a[3]);
        long secs = Long.parseLong(a[4]); int pk0 = Integer.parseInt(a[5]); String[] hosts = a[6].split(",");
        final com.google.common.util.concurrent.RateLimiter rl = a.length > 7 ? com.google.common.util.concurrent.RateLimiter.create(Double.parseDouble(a[7])) : null;
        byte[] bb = new byte[size]; new Random(1).nextBytes(bb); ByteBuffer val = ByteBuffer.wrap(bb);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), sent = new AtomicLong();
        final long total = Long.getLong("total", Long.MAX_VALUE); final AtomicLong tickets = new AtomicLong();
        final AtomicLong firstOk = new AtomicLong(0), lastOk = new AtomicLong(0), firstSend = new AtomicLong(0);
        AtomicReference<String> lastErr = new AtomicReference<>("");
        // gate connection (before any send)
        String gate = System.getProperty("gate", "");
        if (!gate.isEmpty()) {
            Socket gs;
            try {
                gs = new Socket(); gs.connect(new InetSocketAddress(gate.split(":")[0], Integer.parseInt(gate.split(":")[1])), 5000);
            } catch (IOException e) { System.out.println("GATEFAIL " + e); System.exit(3); return; }
            System.out.println("GATE_CONNECTED " + gate);
            Thread gr = new Thread(() -> {
                try (BufferedReader r = new BufferedReader(new InputStreamReader(gs.getInputStream()))) {
                    String l;
                    while ((l = r.readLine()) != null) {
                        if (l.trim().equals("STOP") && !stop) {
                            stop = true; long now = System.currentTimeMillis();
                            System.out.printf("STOP_RECEIVED t=%d sent=%d ok=%d epochMs=%d%n", now - firstSend.get(), sent.get(), ok.get(), now);
                        }
                    }
                } catch (IOException e) { System.out.println("gate reader: " + e); }
            });
            gr.setDaemon(true); gr.start();
        }
        List<Thread> ts = new ArrayList<>(); List<Cluster> cs = new ArrayList<>();
        final long[] endHolder = new long[1];
        for (int h = 0; h < hosts.length; h++) {
            Cluster c = cluster(hosts[h]); cs.add(c); Session s = c.connect();
            PreparedStatement ps = s.prepare("INSERT INTO b6.t_blob (pk, b) VALUES (?, ?)");
            ps.setConsistencyLevel(ConsistencyLevel.valueOf(System.getProperty("cl", "ONE")));
            final int base = pk0 + h * 100_000_000;
            Thread t = new Thread(() -> {
                Semaphore sem = new Semaphore(inflight); int pk = base;
                while (!stop && System.nanoTime() < endHolder[0] && tickets.getAndIncrement() < total) {
                    sem.acquireUninterruptibly(); if (rl != null) rl.acquire();
                    if (stop) { sem.release(); break; }
                    BoundStatement bs = ps.bind().setInt(0, pk++).setBytesUnsafe(1, val.duplicate());
                    firstSend.compareAndSet(0, System.currentTimeMillis());
                    ResultSetFuture f = s.executeAsync(bs); sent.incrementAndGet();
                    Futures.addCallback(f, new FutureCallback<ResultSet>() {
                        public void onSuccess(ResultSet r) { long now = System.currentTimeMillis(); firstOk.compareAndSet(0, now); lastOk.set(now); ok.incrementAndGet(); sem.release(); }
                        public void onFailure(Throwable e) { err.incrementAndGet(); lastErr.set(e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage())); sem.release(); }
                    }, MoreExecutors.directExecutor());
                }
                sem.acquireUninterruptibly(inflight);
            });
            ts.add(t);
        }
        long t0 = System.nanoTime(); endHolder[0] = t0 + secs * 1_000_000_000L;
        for (Thread t : ts) t.start();
        Thread rep = new Thread(() -> {
            long last = 0;
            while (true) {
                try { Thread.sleep(5000); } catch (InterruptedException e) { return; }
                long o = ok.get();
                System.out.printf("[%tT] t=%ds sent=%d ok=%d (%.0f/s) err=%d stop=%b %s%n", new Date(), (System.nanoTime() - t0) / 1_000_000_000L,
                    sent.get(), o, (o - last) / 5.0, err.get(), stop, lastErr.get()); last = o;
            }
        });
        rep.setDaemon(true); rep.start();
        for (Thread t : ts) t.join();
        System.out.printf("FIRST_SEND epochMs=%d%n", firstSend.get());
        System.out.printf("FINAL sent=%d ok=%d err=%d firstOkMs=%d lastOkMs=%d total=%d stop=%b endMs=%d %s%n", sent.get(), ok.get(), err.get(), firstOk.get(), lastOk.get(), total, stop, System.currentTimeMillis(), lastErr.get());
        for (Cluster c : cs) c.close();
        System.exit(0);
    }
}
