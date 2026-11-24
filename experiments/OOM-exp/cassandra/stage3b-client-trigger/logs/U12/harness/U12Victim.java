// U12 3-b confirm victim client: a second LOGIN role doing a steady light workload on its own keyspace/table (vks.kv)
// through the same node. Java driver 3.12.1, protocol v4, one connection, one request in flight, CL ONE.
//   java -Du12.user=victim -Du12.pass=<pw> U12Victim <host> <outCsv> <stopFile> [opsPerSec=20]
// Alternates a 1 KiB write (k = i % 1000) and a read of a written key, one op every 1000/opsPerSec ms (fixed schedule; a
// late op is not made up). Request timeout 2 s. One CSV line per second:
//   epoch_s,attempts,ok_w,ok_r,err,lat_p50_ms,lat_p99_ms,lat_max_ms,errors
// (latencies over the successful ops of that second; errors = "<class>:<count>;...").
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import java.io.*;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.util.*;

public class U12Victim {
    public static void main(String[] a) throws Exception {
        String host = a[0]; File out = new File(a[1]); File stop = new File(a[2]);
        int ops = a.length > 3 ? Integer.parseInt(a[3]) : 20; long period = 1000 / ops;
        PrintWriter csv = new PrintWriter(new FileWriter(out, true), true);
        csv.println("epoch_s,attempts,ok_w,ok_r,err,lat_p50_ms,lat_p99_ms,lat_max_ms,errors");
        Cluster c = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withCredentials(System.getProperty("u12.user"), System.getProperty("u12.pass"))
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(2000).setConnectTimeoutMillis(2000))
            .withPoolingOptions(new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1))
            .withReconnectionPolicy(new ConstantReconnectionPolicy(1000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withoutJMXReporting().build();
        Session s = c.connect();
        PreparedStatement w = s.prepare("INSERT INTO vks.kv (k, v) VALUES (?, ?)");
        PreparedStatement r = s.prepare("SELECT v FROM vks.kv WHERE k = ?");
        w.setConsistencyLevel(ConsistencyLevel.ONE); r.setConsistencyLevel(ConsistencyLevel.ONE);
        Random rnd = new Random(12); byte[] v = new byte[1024];
        long sec = System.currentTimeMillis() / 1000; int att = 0, okw = 0, okr = 0, err = 0;
        List<Long> lat = new ArrayList<>(); Map<String, Integer> errs = new TreeMap<>();
        long next = System.currentTimeMillis(); long i = 0; int written = 0;
        while (!stop.exists()) {
            long t0 = System.currentTimeMillis();
            long cs = t0 / 1000;
            if (cs != sec) {
                Collections.sort(lat);
                String p50 = lat.isEmpty() ? "" : String.valueOf(lat.get(lat.size() / 2));
                String p99 = lat.isEmpty() ? "" : String.valueOf(lat.get(Math.min(lat.size() - 1, (int) Math.ceil(lat.size() * 0.99) - 1)));
                String mx = lat.isEmpty() ? "" : String.valueOf(lat.get(lat.size() - 1));
                StringBuilder e = new StringBuilder();
                for (Map.Entry<String, Integer> en : errs.entrySet()) e.append(en.getKey()).append(':').append(en.getValue()).append(';');
                csv.println(sec + "," + att + "," + okw + "," + okr + "," + err + "," + p50 + "," + p99 + "," + mx + "," + e);
                for (long g = sec + 1; g < cs; g++) csv.println(g + ",0,0,0,0,,,,blocked;");  // a request held this second
                sec = cs; att = okw = okr = err = 0; lat.clear(); errs.clear();
            }
            boolean isWrite = (i % 2 == 0) || written == 0; i++;
            att++;
            try {
                if (isWrite) {
                    rnd.nextBytes(v);
                    s.execute(w.bind((int) (written % 1000), ByteBuffer.wrap(v.clone())));
                    written++; okw++;
                } else {
                    s.execute(r.bind(rnd.nextInt(Math.min(written, 1000)))); okr++;
                }
                lat.add(System.currentTimeMillis() - t0);
            } catch (Exception ex) {
                err++; errs.merge(ex.getClass().getSimpleName(), 1, Integer::sum);
            }
            next += period;
            long now = System.currentTimeMillis();
            if (next < now) next = now + (period - (now - next) % period); // late: skip to the next slot
            Thread.sleep(Math.max(0, next - now));
        }
        csv.close();
        try { c.close(); } catch (Exception e) {}
        System.exit(0);
    }
}
