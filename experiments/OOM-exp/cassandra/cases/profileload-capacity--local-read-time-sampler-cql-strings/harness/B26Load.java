// B26 client (pc91, loopback), adapted from B17Load. Java driver 3.12.1 (shaded), protocol v4, CL ONE, 4 connections,
// read timeout 60 s, FallthroughRetryPolicy, fetch size default (5000).
//   java B26Load schema <host>
//   java B26Load load   <host>                         tables t1..t4: partitions 0..63, 10 rows each, ck = first 10 of L_p, v = 0..9
//   java B26Load count  <host>                         SELECT count(*) per table (expect 640)
//   java B26Load one    <host> <S16|S30> <table> [pk] one read; prints rows, latency, request bytes
//   java B26Load run    <host> <S16|S30> <t1,t2,..> <c> <secs>
//       closed loop, c threads; thread k, iteration i reads pk = (k + 4 i) mod 64; table round-robin (global counter).
// L_p: 3,750 distinct 4,000-byte blobs from new Random(1000 + p), drawn in order (S16 = first 2,000, S30 = all 3,750).
// Output (stdout): per second "S t,c,ok,err_by_class,reads_s,p50ms,p99ms,maxms,lastErr"; at the end "SUMMARY ...".
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B26Load {
    static final int PARTS = 64, NVAL = 3750, VB = 4000, ROWS = 10;

    static Cluster cluster(String host) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 4, 4)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 1024).setMaxQueueSize(4096);
        return Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000).setConnectTimeoutMillis(30000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withQueryOptions(new QueryOptions().setConsistencyLevel(ConsistencyLevel.ONE))
            .withPoolingOptions(po).withoutJMXReporting().build();
    }

    static final ConcurrentHashMap<Integer, List<ByteBuffer>> LISTS = new ConcurrentHashMap<>();

    static List<ByteBuffer> values(int p) {
        return LISTS.computeIfAbsent(p, q -> {
            Random r = new Random(1000 + q);
            List<ByteBuffer> l = new ArrayList<>(NVAL);
            for (int i = 0; i < NVAL; i++) { byte[] b = new byte[VB]; r.nextBytes(b); l.add(ByteBuffer.wrap(b)); }
            return Collections.unmodifiableList(l);
        });
    }

    static int n(String shape) {
        switch (shape) { case "S16": return 2000; case "S30": return 3750; }
        throw new IllegalArgumentException(shape);
    }

    static Session S;
    static final Map<String, PreparedStatement> PREP = new ConcurrentHashMap<>();

    static PreparedStatement ps(String table) {
        return PREP.computeIfAbsent(table, t -> S.prepare("SELECT v FROM b26." + t + " WHERE pk = ? AND ck IN ?"));
    }

    static BoundStatement bind(String table, int pk, String shape) {
        BoundStatement bs = ps(table).bind();
        bs.setInt(0, pk);
        bs.setList(1, values(pk).subList(0, n(shape)), ByteBuffer.class);
        return bs;
    }

    static final AtomicLong ok = new AtomicLong();
    static final ConcurrentHashMap<String, AtomicLong> errs = new ConcurrentHashMap<>();
    static final AtomicReference<String> lastErr = new AtomicReference<>("");
    static final ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
    static final AtomicInteger rr = new AtomicInteger();
    static volatile boolean stop = false;

    static String esc(String s) { return String.valueOf(s).replace(",", ";").replace("\n", " "); }

    public static void main(String[] a) throws Exception {
        String mode = a[0], host = a[1];
        Cluster c = cluster(host);
        S = c.connect();
        try {
            switch (mode) {
                case "schema": schema(); break;
                case "load": load(); break;
                case "count": count(); break;
                case "one": one(a[2], a[3], a.length > 4 ? Integer.parseInt(a[4]) : 0); break;
                case "run": run(a[2], a[3].split(","), Integer.parseInt(a[4]), Integer.parseInt(a[5])); break;
                default: throw new IllegalArgumentException(mode);
            }
        } finally {
            c.close();
        }
        System.exit(0);
    }

    static void schema() {
        S.execute("CREATE KEYSPACE IF NOT EXISTS b26 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
        for (int t = 1; t <= 4; t++)
            S.execute("CREATE TABLE IF NOT EXISTS b26.t" + t + " (pk int, ck blob, v int, PRIMARY KEY (pk, ck))");
        System.out.println("schema ok");
    }

    static void load() {
        for (int t = 1; t <= 4; t++) {
            PreparedStatement p = S.prepare("INSERT INTO b26.t" + t + " (pk, ck, v) VALUES (?, ?, ?)");
            int n = 0;
            for (int pk = 0; pk < PARTS; pk++)
                for (int i = 0; i < ROWS; i++) {
                    for (int tr = 0; ; tr++) {
                        try { S.execute(p.bind(pk, values(pk).get(i), i)); break; }
                        catch (DriverException e) { if (tr >= 5) throw e; }
                    }
                    n++;
                }
            System.out.println("loaded t" + t + " rows=" + n);
        }
    }

    static void count() {
        for (int t = 1; t <= 4; t++) {
            long cnt = S.execute(new SimpleStatement("SELECT count(*) FROM b26.t" + t).setReadTimeoutMillis(120000)).one().getLong(0);
            System.out.println("count t" + t + " = " + cnt);
        }
    }

    static void one(String shape, String table, int pk) {
        long t0 = System.nanoTime();
        int rows = 0;
        for (Row r : S.execute(bind(table, pk, shape))) rows++;
        long ms = (System.nanoTime() - t0) / 1_000_000;
        System.out.println("ONE shape=" + shape + " table=" + table + " pk=" + pk + " in=" + n(shape) + " rows=" + rows + " ms=" + ms
                           + " approxRequestBytes=" + ((long) n(shape) * (VB + 4) + 4));
    }

    static void run(String shape, String[] tables, int conc, int secs) throws Exception {
        for (String t : tables) ps(t);
        for (int p = 0; p < PARTS; p++) values(p);
        ExecutorService ex = Executors.newFixedThreadPool(conc);
        long start = System.currentTimeMillis();
        for (int k = 0; k < conc; k++) {
            final int th = k;
            ex.submit(() -> {
                for (int i = 0; !stop; i++) {
                    int pk = (th + 4 * i) % PARTS;
                    String t = tables[Math.floorMod(rr.getAndIncrement(), tables.length)];
                    long t0 = System.nanoTime();
                    try {
                        int rows = 0;
                        for (Row r : S.execute(bind(t, pk, shape))) rows++;
                        ok.incrementAndGet();
                        lat.add((System.nanoTime() - t0) / 1_000_000);
                    } catch (Throwable e) {
                        String cls = e.getClass().getSimpleName();
                        errs.computeIfAbsent(cls, x -> new AtomicLong()).incrementAndGet();
                        lastErr.set(cls + ": " + esc(e.getMessage()));
                        if (e instanceof NoHostAvailableException) {
                            try { Thread.sleep(500); } catch (InterruptedException ie) { return; }
                        }
                    }
                }
            });
        }
        long prevOk = 0, totalOk = 0;
        List<Long> all = new ArrayList<>();
        System.out.println("# S t,c,ok,err_by_class,reads_s,p50ms,p99ms,maxms,lastErr");
        for (int s = 1; s <= secs; s++) {
            long due = start + s * 1000L;
            long d = due - System.currentTimeMillis();
            if (d > 0) Thread.sleep(d);
            List<Long> l = new ArrayList<>();
            Long x;
            while ((x = lat.poll()) != null) l.add(x);
            Collections.sort(l);
            all.addAll(l);
            long o = ok.get();
            StringBuilder eb = new StringBuilder();
            for (Map.Entry<String, AtomicLong> e : new TreeMap<>(errs).entrySet())
                eb.append(eb.length() == 0 ? "" : "|").append(e.getKey()).append(':').append(e.getValue().get());
            System.out.println("S " + s + "," + conc + "," + o + "," + eb + "," + (o - prevOk) + ","
                               + pct(l, 50) + "," + pct(l, 99) + "," + (l.isEmpty() ? -1 : l.get(l.size() - 1)) + "," + lastErr.get());
            System.out.flush();
            prevOk = o;
        }
        stop = true;
        ex.shutdown();
        ex.awaitTermination(70, TimeUnit.SECONDS);
        Collections.sort(all);
        long errTotal = errs.values().stream().mapToLong(AtomicLong::get).sum();
        System.out.println("SUMMARY shape=" + shape + " tables=" + String.join("+", tables) + " c=" + conc + " secs=" + secs
                           + " ok=" + ok.get() + " err=" + errTotal + " reads_s=" + String.format("%.1f", ok.get() / (double) secs)
                           + " p50=" + pct(all, 50) + " p99=" + pct(all, 99) + " max=" + (all.isEmpty() ? -1 : all.get(all.size() - 1))
                           + " errs=" + errs + " lastErr=" + lastErr.get());
    }

    static long pct(List<Long> l, int p) {
        if (l.isEmpty()) return -1;
        return l.get(Math.min(l.size() - 1, (int) Math.ceil(p / 100.0 * l.size()) - 1 < 0 ? 0 : (int) Math.ceil(p / 100.0 * l.size()) - 1));
    }
}
