// 3-b confirm victim (R24, pc72, 2026-11-24), from C10's C10Victim (pc91, 2026-11-23). A second tenant: its own role
// (-Dr24.user/-Dr24.pass), its own admin-made keyspace vks (RF 2) and table vks.kv (k int PRIMARY KEY, v blob). Three
// sessions, each open-loop at a fixed rate, half small reads and half small writes (100 B), driver read timeout 12 s,
// FallthroughRetryPolicy (raw outcomes, no driver retries):
//   V1 -> 127.0.0.1 only (the attacker's coordinator), QUORUM; V2 -> 127.0.0.2 only (the other node), QUORUM;
//   V3 -> 127.0.0.2 only, ONE.
//   java R24Victim preload <host> <rows>
//   java R24Victim run <opsPerSecPerSession> <maxSecs> <stopFile>
// run CSV (one line per second per session):
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

public class R24Victim {
    static final int ROWS = 10000;

    static Cluster cluster(List<String> hosts) {
        List<InetSocketAddress> wl = new ArrayList<>();
        for (String h : hosts) wl.add(new InetSocketAddress(h, 9042));
        Cluster.Builder b = Cluster.builder().addContactPoint(hosts.get(0)).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(), wl))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(12000).setConnectTimeoutMillis(5000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withReconnectionPolicy(new ConstantReconnectionPolicy(2000))
            .withPoolingOptions(new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1)
                .setMaxRequestsPerConnection(HostDistance.LOCAL, 2048).setMaxQueueSize(4096))
            .withoutJMXReporting();
        String u = System.getProperty("r24.user");
        if (u != null) b = b.withCredentials(u, System.getProperty("r24.pass", ""));
        return b.build();
    }

    static class Sess {
        final String name; Session s; PreparedStatement rd, wr;
        final AtomicLong issued = new AtomicLong(), ok = new AtomicLong(), err = new AtomicLong();
        final AtomicLong rto = new AtomicLong(), wto = new AtomicLong(), unav = new AtomicLong(), opto = new AtomicLong(),
            nohost = new AtomicLong(), auth = new AtomicLong(), other = new AtomicLong();
        final AtomicInteger inflight = new AtomicInteger();
        final ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
        final AtomicReference<String> lastErr = new AtomicReference<>("");
        long pIss, pOk, pErr;
        Sess(String n) { name = n; }
    }

    public static void main(String[] a) throws Exception {
        if (a[0].equals("preload")) {
            try (Cluster c = cluster(Collections.singletonList(a[1])); Session s = c.connect()) {
                PreparedStatement w = s.prepare("INSERT INTO vks.kv (k, v) VALUES (?, ?)");
                w.setConsistencyLevel(ConsistencyLevel.QUORUM);
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
        Sess[] ss = { new Sess("V1"), new Sess("V2"), new Sess("V3") };
        List<List<String>> hosts = Arrays.asList(Collections.singletonList("127.0.0.1"), Collections.singletonList("127.0.0.2"), Collections.singletonList("127.0.0.2"));
        ConsistencyLevel[] cls_ = { ConsistencyLevel.QUORUM, ConsistencyLevel.QUORUM, ConsistencyLevel.ONE };
        List<Cluster> cls = new ArrayList<>();
        boolean noV1 = System.getProperty("r24.noV1") != null;   // 3-b R24 (2026-11-24, after A-NV1): victim through node 2 only
        for (int i = 0; i < ss.length; i++) {
            if (i == 0 && noV1) continue;
            Cluster c = cluster(hosts.get(i)); cls.add(c);
            ss[i].s = c.connect();
            ss[i].rd = ss[i].s.prepare("SELECT v FROM vks.kv WHERE k = ?"); ss[i].rd.setConsistencyLevel(cls_[i]);
            ss[i].wr = ss[i].s.prepare("INSERT INTO vks.kv (k, v) VALUES (?, ?)"); ss[i].wr.setConsistencyLevel(cls_[i]);
        }
        ScheduledExecutorService ex = Executors.newScheduledThreadPool(3);
        Random rnd = new Random(1);
        for (Sess x : ss) {
            if (x.s == null) continue;
            AtomicLong seq = new AtomicLong();
            ex.scheduleAtFixedRate(() -> {
                if (x.inflight.get() >= 3000) { x.issued.incrementAndGet(); x.err.incrementAndGet(); x.other.incrementAndGet(); x.lastErr.set("client-side backlog cap"); return; }
                long q = seq.incrementAndGet(); int k = (int) ((q * 7919) % ROWS);
                Statement st = (q % 2 == 0) ? x.rd.bind(k) : x.wr.bind(k, ByteBuffer.wrap(new byte[100]));
                final long t0 = System.nanoTime();
                x.issued.incrementAndGet(); x.inflight.incrementAndGet();
                ResultSetFuture f;
                try { f = x.s.executeAsync(st); } catch (Exception e) { fail(x, e); return; }
                Futures.addCallback(f, new FutureCallback<ResultSet>() {
                    public void onSuccess(ResultSet r) { x.ok.incrementAndGet(); x.lat.add((System.nanoTime() - t0) / 1000); x.inflight.decrementAndGet(); }
                    public void onFailure(Throwable e) { fail(x, e); }
                }, MoreExecutors.directExecutor());
            }, 0, 1000000L / rate, TimeUnit.MICROSECONDS);
        }
        System.out.println("t,sess,issued,ok,err,p50ms,p99ms,maxms,inflight,e_rto,e_wto,e_unav,e_opto,e_nohost,e_auth,e_other,lastErr");
        long t0 = System.currentTimeMillis();
        while (!stop.exists() && System.currentTimeMillis() - t0 < maxSecs * 1000) {
            Thread.sleep(1000 - (System.currentTimeMillis() - t0) % 1000);
            long now = System.currentTimeMillis();
            for (Sess x : ss) {
                if (x.s == null) continue;
                List<Long> l = new ArrayList<>(); Long v; while ((v = x.lat.poll()) != null) l.add(v);
                Collections.sort(l);
                double p50 = l.isEmpty() ? -1 : l.get(l.size() / 2) / 1000.0, p99 = l.isEmpty() ? -1 : l.get(Math.min(l.size() - 1, (int) (l.size() * 0.99))) / 1000.0;
                double mx = l.isEmpty() ? -1 : l.get(l.size() - 1) / 1000.0;
                long i = x.issued.get(), o = x.ok.get(), e = x.err.get();
                System.out.printf("%d,%s,%d,%d,%d,%.1f,%.1f,%.1f,%d,%d,%d,%d,%d,%d,%d,%d,%s%n", now, x.name, i - x.pIss, o - x.pOk, e - x.pErr, p50, p99, mx,
                    x.inflight.get(), x.rto.get(), x.wto.get(), x.unav.get(), x.opto.get(), x.nohost.get(), x.auth.get(), x.other.get(), x.lastErr.getAndSet(""));
                x.pIss = i; x.pOk = o; x.pErr = e;
            }
        }
        ex.shutdownNow();
        for (Sess x : ss) System.out.printf("SUMMARY %s issued=%d ok=%d err=%d rto=%d wto=%d unav=%d opto=%d nohost=%d auth=%d other=%d%n", x.name,
            x.issued.get(), x.ok.get(), x.err.get(), x.rto.get(), x.wto.get(), x.unav.get(), x.opto.get(), x.nohost.get(), x.auth.get(), x.other.get());
        for (Cluster c : cls) c.closeAsync();
        System.exit(0);
    }

    static void fail(Sess x, Throwable e) {
        x.err.incrementAndGet(); x.inflight.decrementAndGet();
        if (e instanceof ReadTimeoutException) x.rto.incrementAndGet();
        else if (e instanceof WriteTimeoutException) x.wto.incrementAndGet();
        else if (e instanceof UnavailableException) x.unav.incrementAndGet();
        else if (e instanceof OperationTimedOutException) x.opto.incrementAndGet();
        else if (e instanceof NoHostAvailableException) x.nohost.incrementAndGet();
        else if (e instanceof AuthenticationException || e instanceof UnauthorizedException) x.auth.incrementAndGet();
        else x.other.incrementAndGet();
        x.lastErr.set(e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '));
    }
}
