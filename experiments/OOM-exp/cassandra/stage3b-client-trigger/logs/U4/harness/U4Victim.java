// 3-b confirm victim (U4, pc91, 2026-11-24), from C10Victim. A second tenant: its own role (-Du4.user/-Du4.pass), its
// own admin-made keyspace vks (RF 1, the single node) and table vks.kv (k int PRIMARY KEY, v blob). One session (V1)
// through 127.0.0.1 (the only node = the attacker's coordinator and replica), open-loop at a fixed rate, half small
// reads and half small writes (100 B), CL ONE, driver read timeout 12 s, FallthroughRetryPolicy (raw outcomes).
//   java U4Victim preload <host> <rows>
//   java U4Victim run <opsPerSec> <maxSecs> <stopFile>
// run CSV (one line per second):
//   t,sess,issued,ok,err,p50ms,p99ms,maxms,inflight,e_rto,e_wto,e_unav,e_opto,e_nohost,e_auth,e_other,lastErr
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class U4Victim {
    static final int ROWS = 10000;

    static Cluster cluster(String host) {
        Cluster.Builder b = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(), Collections.singletonList(new InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(12000).setConnectTimeoutMillis(5000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withReconnectionPolicy(new ConstantReconnectionPolicy(2000))
            .withPoolingOptions(new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1)
                .setMaxRequestsPerConnection(HostDistance.LOCAL, 2048).setMaxQueueSize(4096))
            .withoutJMXReporting();
        String u = System.getProperty("u4.user");
        if (u != null) b = b.withCredentials(u, System.getProperty("u4.pass", ""));
        return b.build();
    }

    static final AtomicLong issued = new AtomicLong(), ok = new AtomicLong(), err = new AtomicLong();
    static final AtomicLong rto = new AtomicLong(), wto = new AtomicLong(), unav = new AtomicLong(), opto = new AtomicLong(),
        nohost = new AtomicLong(), auth = new AtomicLong(), other = new AtomicLong();
    static final AtomicInteger inflight = new AtomicInteger();
    static final ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
    static final AtomicReference<String> lastErr = new AtomicReference<>("");

    public static void main(String[] a) throws Exception {
        if (a[0].equals("preload")) {
            try (Cluster c = cluster(a[1]); Session s = c.connect()) {
                PreparedStatement w = s.prepare("INSERT INTO vks.kv (k, v) VALUES (?, ?)");
                w.setConsistencyLevel(ConsistencyLevel.ONE);
                int n = Integer.parseInt(a[2]); Semaphore sem = new Semaphore(32); AtomicLong e = new AtomicLong();
                for (int k = 0; k < n; k++) {
                    sem.acquireUninterruptibly();
                    Futures.addCallback(s.executeAsync(w.bind(k, ByteBuffer.wrap(new byte[100]))), new FutureCallback<ResultSet>() {
                        public void onSuccess(ResultSet r) { sem.release(); }
                        public void onFailure(Throwable t) { e.incrementAndGet(); sem.release(); }
                    }, MoreExecutors.directExecutor());
                }
                sem.acquireUninterruptibly(32);
                System.out.println("victim preload rows=" + n + " errors=" + e.get());
            }
            return;
        }
        int rate = Integer.parseInt(a[1]); long maxSecs = Long.parseLong(a[2]); java.io.File stop = new java.io.File(a[3]);
        Cluster c = cluster("127.0.0.1");
        Session s = c.connect();
        PreparedStatement rd = s.prepare("SELECT v FROM vks.kv WHERE k = ?"); rd.setConsistencyLevel(ConsistencyLevel.ONE);
        PreparedStatement wr = s.prepare("INSERT INTO vks.kv (k, v) VALUES (?, ?)"); wr.setConsistencyLevel(ConsistencyLevel.ONE);
        ScheduledExecutorService ex = Executors.newScheduledThreadPool(1);
        AtomicLong seq = new AtomicLong();
        ex.scheduleAtFixedRate(() -> {
            if (inflight.get() >= 3000) { issued.incrementAndGet(); err.incrementAndGet(); other.incrementAndGet(); lastErr.set("client-side backlog cap"); return; }
            long q = seq.incrementAndGet(); int k = (int) ((q * 7919) % ROWS);
            Statement st = (q % 2 == 0) ? rd.bind(k) : wr.bind(k, ByteBuffer.wrap(new byte[100]));
            final long t0 = System.nanoTime();
            issued.incrementAndGet(); inflight.incrementAndGet();
            ResultSetFuture f;
            try { f = s.executeAsync(st); } catch (Exception e) { fail(e); return; }
            Futures.addCallback(f, new FutureCallback<ResultSet>() {
                public void onSuccess(ResultSet r) { ok.incrementAndGet(); lat.add((System.nanoTime() - t0) / 1000); inflight.decrementAndGet(); }
                public void onFailure(Throwable e) { fail(e); }
            }, MoreExecutors.directExecutor());
        }, 0, 1000000L / rate, TimeUnit.MICROSECONDS);
        System.out.println("t,sess,issued,ok,err,p50ms,p99ms,maxms,inflight,e_rto,e_wto,e_unav,e_opto,e_nohost,e_auth,e_other,lastErr");
        long t0 = System.currentTimeMillis(); long pIss = 0, pOk = 0, pErr = 0;
        while (!stop.exists() && System.currentTimeMillis() - t0 < maxSecs * 1000) {
            Thread.sleep(1000 - (System.currentTimeMillis() - t0) % 1000);
            long now = System.currentTimeMillis();
            List<Long> l = new ArrayList<>(); Long v; while ((v = lat.poll()) != null) l.add(v);
            Collections.sort(l);
            double p50 = l.isEmpty() ? -1 : l.get(l.size() / 2) / 1000.0, p99 = l.isEmpty() ? -1 : l.get(Math.min(l.size() - 1, (int) (l.size() * 0.99))) / 1000.0;
            double mx = l.isEmpty() ? -1 : l.get(l.size() - 1) / 1000.0;
            long i = issued.get(), o = ok.get(), e = err.get();
            System.out.printf("%d,V1,%d,%d,%d,%.1f,%.1f,%.1f,%d,%d,%d,%d,%d,%d,%d,%d,%s%n", now, i - pIss, o - pOk, e - pErr, p50, p99, mx,
                inflight.get(), rto.get(), wto.get(), unav.get(), opto.get(), nohost.get(), auth.get(), other.get(), lastErr.getAndSet(""));
            pIss = i; pOk = o; pErr = e;
        }
        ex.shutdownNow();
        System.out.printf("SUMMARY V1 issued=%d ok=%d err=%d rto=%d wto=%d unav=%d opto=%d nohost=%d auth=%d other=%d%n",
            issued.get(), ok.get(), err.get(), rto.get(), wto.get(), unav.get(), opto.get(), nohost.get(), auth.get(), other.get());
        c.closeAsync();
        System.exit(0);
    }

    static void fail(Throwable e) {
        err.incrementAndGet(); inflight.decrementAndGet();
        if (e instanceof ReadTimeoutException) rto.incrementAndGet();
        else if (e instanceof WriteTimeoutException) wto.incrementAndGet();
        else if (e instanceof UnavailableException) unav.incrementAndGet();
        else if (e instanceof OperationTimedOutException) opto.incrementAndGet();
        else if (e instanceof NoHostAvailableException) nohost.incrementAndGet();
        else if (e instanceof AuthenticationException || e instanceof UnauthorizedException) auth.incrementAndGet();
        else other.incrementAndGet();
        lastErr.set(e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '));
    }
}
