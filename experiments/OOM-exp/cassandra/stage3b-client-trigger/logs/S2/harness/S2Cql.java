// 3-b confirm S2 (pc91, 2026-11-23): run CQL statements over the native protocol (Java driver 3.12.1, v4) as a role
// (-Ds2.user/-Ds2.pass; unset = no credentials). One statement per line; blank lines and lines starting with '#' are
// echoed as comments. Each statement prints its rows (up to 50) or the error class and message; it never stops on an
// error (the privilege probes expect refusals). CL of each statement: -Ds2.cl (default ONE).
//   java S2Cql <host> <file.cql>
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import java.nio.file.*;
import java.util.*;

public class S2Cql {
    public static void main(String[] a) throws Exception {
        Cluster.Builder b = Cluster.builder().addContactPoint(a[0]).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(a[0], 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000)).withoutJMXReporting();
        String u = System.getProperty("s2.user");
        if (u != null && !u.isEmpty()) b = b.withCredentials(u, System.getProperty("s2.pass", ""));
        System.out.println("# as role: " + (u == null || u.isEmpty() ? "(no credentials)" : u) + " via " + a[0]);
        Cluster c = b.build(); Session s;
        try { s = c.connect(); } catch (Exception e) {
            System.out.println("CONNECT FAILED: " + e.getClass().getSimpleName() + ": " + e.getMessage()); c.close(); System.exit(0); return;
        }
        ConsistencyLevel cl = ConsistencyLevel.valueOf(System.getProperty("s2.cl", "ONE"));
        for (String line : Files.readAllLines(Paths.get(a[1]))) {
            String q = line.trim();
            if (q.isEmpty()) continue;
            if (q.startsWith("#")) { System.out.println(q); continue; }
            System.out.println("> " + q.replaceAll("PASSWORD = '[^']*'", "PASSWORD = '***'"));
            try {
                ResultSet rs = s.execute(new SimpleStatement(q).setConsistencyLevel(cl));
                int n = 0;
                for (Row r : rs) {
                    if (n++ >= 50) { System.out.println("  ..."); break; }
                    StringBuilder sb = new StringBuilder("  ");
                    for (int i = 0; i < r.getColumnDefinitions().size(); i++) {
                        if (i > 0) sb.append(" | ");
                        Object o = r.getObject(i); String v = String.valueOf(o);
                        sb.append(v.length() > 120 ? v.substring(0, 120) + "..." : v);
                    }
                    System.out.println(sb);
                }
                System.out.println("  ok (" + n + " rows)");
            } catch (Exception e) {
                System.out.println("  ERROR " + e.getClass().getSimpleName() + ": " + e.getMessage());
            }
        }
        c.close();
        System.exit(0);
    }
}
