// C5 stage 2 client. Java driver 3.12.1 (shaded), protocol V4, DCAwareRoundRobinPolicy(dc1) behind a whitelist of
// A (127.0.5.1:9042), CL LOCAL_ONE, one request in flight, synchronous, no driver retries.
//   java C5Load schema
//   java C5Load run <keysFile> <k> <W> <blobBytes> <seed> <outCsv>
// Write i (0..W-1) goes to range (i mod k) with that range's key; value = fresh random blob from new Random(seed+i).
// Per write: epoch_ms,i,range,key,latency_ms,outcome. Keeps going after a WriteTimeout; stops on NoHostAvailable.
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import java.io.*;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.file.*;
import java.util.*;

public class C5Load {
    static Cluster cluster() {
        return Cluster.builder().addContactPoint("127.0.5.1").withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(DCAwareRoundRobinPolicy.builder().withLocalDc("dc1").build(),
                Collections.singletonList(new InetSocketAddress("127.0.5.1", 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000).setConnectTimeoutMillis(10000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE).withoutJMXReporting().build();
    }
    public static void main(String[] a) throws Exception {
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS c5 WITH replication = {'class':'NetworkTopologyStrategy','dc1':1,'dc2':3}");
                s.execute("CREATE TABLE IF NOT EXISTS c5.t (k int PRIMARY KEY, v blob)");
                System.out.println("schema ok");
            }
            return;
        }
        List<String> lines = Files.readAllLines(Paths.get(a[1]));
        int[] key = new int[64]; for (String l : lines) { String[] f = l.trim().split(" "); key[Integer.parseInt(f[0])] = Integer.parseInt(f[1]); }
        int k = Integer.parseInt(a[2]), W = Integer.parseInt(a[3]), size = Integer.parseInt(a[4]); long seed = Long.parseLong(a[5]);
        PrintWriter out = new PrintWriter(new FileWriter(a[6]), true);
        out.println("epoch_ms,i,range,key,latency_ms,outcome");
        int ok = 0, to = 0, err = 0;
        try (Cluster c = cluster(); Session s = c.connect()) {
            PreparedStatement ps = s.prepare("INSERT INTO c5.t (k, v) VALUES (?, ?)");
            ps.setConsistencyLevel(ConsistencyLevel.LOCAL_ONE);
            byte[] blob = new byte[size];
            for (int i = 0; i < W; i++) {
                int r = i % k; new Random(seed + i).nextBytes(blob);
                long t0 = System.currentTimeMillis(); String oc;
                try { s.execute(ps.bind(key[r], ByteBuffer.wrap(blob))); oc = "ok"; ok++; }
                catch (WriteTimeoutException e) { oc = "timeout"; to++; }
                catch (NoHostAvailableException e) { oc = "nohost:" + e.getMessage().replace(',', ';'); err++; out.println(t0 + "," + i + "," + r + "," + key[r] + "," + (System.currentTimeMillis() - t0) + "," + oc); break; }
                catch (Exception e) { oc = "error:" + e.getClass().getSimpleName() + ":" + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '); err++; }
                out.println(t0 + "," + i + "," + r + "," + key[r] + "," + (System.currentTimeMillis() - t0) + "," + oc);
            }
        }
        System.out.println("FINAL ok=" + ok + " timeout=" + to + " error=" + err);
        System.exit(0);
    }
}
