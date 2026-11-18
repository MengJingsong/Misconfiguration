// B9 load generator (derived from U1Load). Java driver 3.12.1 (shaded), protocol V4, prepared INSERT of one blob.
// W writers = one Cluster each, bound to its own source IP (-Dsrcips=127.0.1.1,...), with exactly P connections
// (core = max = P). All clusters share one NioEventLoopGroup(2) and one HashedWheelTimer.
// Burst: every writer connects, prepares and waits until P connections are open; then all wait on one latch,
// BURST_START is printed and each writer issues its Q requests at once (no rate limiter). Sustain: each completion
// frees one permit; the next request also waits on one shared RateLimiter(R) until <seconds> after BURST_START.
// BURST_DONE when all W*Q burst requests have completed (ok or error). No client disconnects before the window ends.
//   java B9Load schema <host>
//   java B9Load run <blobBytes> <connsPerWriter P> <inflightPerWriter Q> <seconds> <sustainRate R> <host>
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.datastax.shaded.netty.bootstrap.Bootstrap;
import com.datastax.shaded.netty.channel.EventLoopGroup;
import com.datastax.shaded.netty.channel.nio.NioEventLoopGroup;
import com.datastax.shaded.netty.channel.socket.SocketChannel;
import com.datastax.shaded.netty.channel.socket.nio.NioSocketChannel;
import com.datastax.shaded.netty.util.HashedWheelTimer;
import com.datastax.shaded.netty.util.Timer;
import com.google.common.util.concurrent.*;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B9Load {
    static final int KEYS = Integer.getInteger("keys", 16);
    static NioEventLoopGroup ELG; static HashedWheelTimer TIMER;

    static Cluster cluster(String host, String src, int p) {
        PoolingOptions po = new PoolingOptions().setMaxRequestsPerConnection(HostDistance.LOCAL, 2048)
            .setConnectionsPerHost(HostDistance.LOCAL, p, p);
        Cluster.Builder b = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000).setConnectTimeoutMillis(20000))
            .withPoolingOptions(po)
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withoutJMXReporting().withoutMetrics();
        b.withNettyOptions(new NettyOptions() {
            @Override public EventLoopGroup eventLoopGroup(ThreadFactory tf) { return ELG; }
            @Override public Class<? extends SocketChannel> channelClass() { return NioSocketChannel.class; }
            @Override public Timer timer(ThreadFactory tf) { return TIMER; }
            @Override public void onClusterClose(EventLoopGroup g) { }
            @Override public void onClusterClose(Timer t) { }
            @Override public void afterBootstrapInitialized(Bootstrap bs) { if (src != null) bs.localAddress(new InetSocketAddress(src, 0)); }
        });
        return b.build();
    }

    static String ts() { return String.format("%tT", new Date()); }

    public static void main(String[] a) throws Exception {
        ELG = new NioEventLoopGroup(2); TIMER = new HashedWheelTimer();
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(a[1], null, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS b9 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS b9.t (pk int PRIMARY KEY, b blob)");
                System.out.println("schema ok");
            }
            System.exit(0);
        }
        int size = Integer.parseInt(a[1]); int P = Integer.parseInt(a[2]); int Q = Integer.parseInt(a[3]);
        long secs = Long.parseLong(a[4]); double rate = Double.parseDouble(a[5]); String host = a[6];
        String[] srcs = System.getProperty("srcips", "").isEmpty() ? new String[]{null} : System.getProperty("srcips").split(",");
        int W = srcs.length;
        final ByteBuffer val = ByteBuffer.wrap(new byte[size]);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), sent = new AtomicLong(), burstDone = new AtomicLong();
        ConcurrentHashMap<String, AtomicLong> errs = new ConcurrentHashMap<>();
        AtomicInteger key = new AtomicInteger();
        List<Cluster> cs = new ArrayList<>(); List<Session> ss = new ArrayList<>(); List<PreparedStatement> pss = new ArrayList<>();
        for (String src : srcs) {
            Cluster c = cluster(host, src, P); cs.add(c); Session s = c.connect(); ss.add(s);
            PreparedStatement ps = s.prepare("INSERT INTO b9.t (pk, b) VALUES (?, ?)");
            ps.setConsistencyLevel(ConsistencyLevel.ONE); pss.add(ps);
        }
        Host h0 = null;
        for (int i = 0; i < W; i++) {
            Session s = ss.get(i); long dl = System.currentTimeMillis() + 30000; int open = 0;
            while (System.currentTimeMillis() < dl) {
                for (Host h : s.getState().getConnectedHosts()) { h0 = h; open = s.getState().getOpenConnections(h); }
                if (open >= P) break;
                Thread.sleep(100);
            }
            System.out.printf("[%s] writer %d src=%s open_connections=%d%n", ts(), i, srcs[i], open);
        }
        final CountDownLatch go = new CountDownLatch(1);
        final long burstTotal = (long) W * Q;
        final long[] burstDoneAt = {0};
        final RateLimiter[] rlH = new RateLimiter[1];
        final long[] endNs = {0};
        List<Thread> threads = new ArrayList<>();
        for (int i = 0; i < W; i++) {
            final Session s = ss.get(i); final PreparedStatement ps = pss.get(i);
            Thread t = new Thread(() -> {
                Semaphore sem = new Semaphore(Q);
                try { go.await(); } catch (InterruptedException e) { return; }
                // burst: Q requests at once
                for (int j = 0; j < Q; j++) {
                    sem.acquireUninterruptibly();
                    BoundStatement bs = ps.bind().setInt(0, Math.floorMod(key.getAndIncrement(), KEYS)).setBytesUnsafe(1, val.duplicate());
                    ResultSetFuture f = s.executeAsync(bs); sent.incrementAndGet();
                    Futures.addCallback(f, cb(ok, err, errs, sem, true, burstDone, burstTotal, burstDoneAt), MoreExecutors.directExecutor());
                }
                // sustain
                while (System.nanoTime() < endNs[0]) {
                    try { if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue; } catch (InterruptedException e) { return; }
                    if (System.nanoTime() >= endNs[0]) { sem.release(); break; }
                    rlH[0].acquire();
                    BoundStatement bs = ps.bind().setInt(0, Math.floorMod(key.getAndIncrement(), KEYS)).setBytesUnsafe(1, val.duplicate());
                    ResultSetFuture f = s.executeAsync(bs); sent.incrementAndGet();
                    Futures.addCallback(f, cb(ok, err, errs, sem, false, burstDone, burstTotal, burstDoneAt), MoreExecutors.directExecutor());
                }
                try { sem.tryAcquire(Q, 70, TimeUnit.SECONDS); } catch (InterruptedException e) {}
            });
            threads.add(t); t.start();
        }
        Thread.sleep(500);
        long t0 = System.nanoTime(); endNs[0] = t0 + secs * 1_000_000_000L; rlH[0] = RateLimiter.create(rate);
        long burstStartMs = System.currentTimeMillis();
        System.out.printf("BURST_START %d W=%d P=%d Q=%d burst=%d size=%d%n", burstStartMs, W, P, Q, burstTotal, size);
        System.out.flush();
        go.countDown();
        Thread rep = new Thread(() -> {
            boolean printed = false;
            while (true) {
                try { Thread.sleep(1000); } catch (InterruptedException e) { return; }
                if (!printed && burstDoneAt[0] > 0) { System.out.printf("BURST_DONE %d (+%.1fs)%n", burstDoneAt[0], (burstDoneAt[0] - burstStartMs) / 1000.0); printed = true; }
                System.out.printf("[%s] t=%ds sent=%d ok=%d err=%d burst_done=%d/%d %s%n", ts(), (System.nanoTime() - t0) / 1_000_000_000L,
                    sent.get(), ok.get(), err.get(), burstDone.get(), burstTotal, errs);
            }
        });
        rep.setDaemon(true); rep.start();
        for (Thread t : threads) t.join();
        double el = (System.nanoTime() - t0) / 1e9;
        if (burstDoneAt[0] > 0) System.out.printf("BURST_DONE %d (+%.1fs)%n", burstDoneAt[0], (burstDoneAt[0] - burstStartMs) / 1000.0);
        System.out.printf("FINAL sent=%d ok=%d err=%d burst_done=%d/%d elapsed=%.0fs ok_rate=%.2f/s errs=%s%n", sent.get(), ok.get(), err.get(),
            burstDone.get(), burstTotal, el, ok.get() / el, errs);
        System.out.flush();
        for (Cluster c : cs) { try { c.closeAsync().get(10, TimeUnit.SECONDS); } catch (Exception e) {} }
        System.exit(0);
    }

    static FutureCallback<ResultSet> cb(AtomicLong ok, AtomicLong err, ConcurrentHashMap<String, AtomicLong> errs, Semaphore sem,
                                         boolean burst, AtomicLong burstDone, long burstTotal, long[] burstDoneAt) {
        return new FutureCallback<ResultSet>() {
            void fin() { sem.release(); if (burst && burstDone.incrementAndGet() == burstTotal) burstDoneAt[0] = System.currentTimeMillis(); }
            public void onSuccess(ResultSet r) { ok.incrementAndGet(); fin(); }
            public void onFailure(Throwable e) { err.incrementAndGet(); errs.computeIfAbsent(e.getClass().getSimpleName(), k -> new AtomicLong()).incrementAndGet(); fin(); }
        };
    }
}
