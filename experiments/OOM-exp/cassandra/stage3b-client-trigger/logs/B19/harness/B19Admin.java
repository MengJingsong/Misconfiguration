// B19 3-b confirm (ms0625, 2026-11-23): superuser setup through the Java driver 3.12.1 (protocol v4). Used ONLY to create
// the victim role, the victim's (admin-made) keyspace and table, and its grants. The attacker has no role (pre-auth).
//   java -Duser=cassandra -Dpass=cassandra B19Admin <host> <tenantPassword>      (retries login for up to 90 s while the
//   default superuser is being set up)
// Prints every statement, then LIST ALL PERMISSIONS, LIST ROLES and system_auth.roles.
import com.datastax.driver.core.*;

public class B19Admin {
    public static void main(String[] a) throws Exception {
        String host = a[0], tp = a[1];
        Cluster c = null; Session s = null; long t0 = System.currentTimeMillis(); Exception last = null;
        while (System.currentTimeMillis() - t0 < 90000) {
            try {
                c = Cluster.builder().addContactPoint(host).withPort(9042).withProtocolVersion(ProtocolVersion.V4)
                    .withCredentials(System.getProperty("user"), System.getProperty("pass")).withoutJMXReporting().build();
                s = c.connect(); break;
            } catch (Exception e) { last = e; if (c != null) c.close(); c = null; Thread.sleep(2000); }
        }
        if (s == null) { System.out.println("ADMIN LOGIN FAILED " + last); System.exit(1); }
        System.out.println("ADMIN login as " + System.getProperty("user") + " after " + (System.currentTimeMillis() - t0) + " ms");
        String[] st = {
            "CREATE ROLE IF NOT EXISTS tenant WITH PASSWORD = '" + tp + "' AND LOGIN = true AND SUPERUSER = false",
            "CREATE KEYSPACE IF NOT EXISTS vic WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
            "CREATE TABLE IF NOT EXISTS vic.kv (k int PRIMARY KEY, v text)",
            "GRANT SELECT ON TABLE vic.kv TO tenant",
            "GRANT MODIFY ON TABLE vic.kv TO tenant",
        };
        for (String q : st) { s.execute(new SimpleStatement(q).setConsistencyLevel(ConsistencyLevel.ONE)); System.out.println("ADMIN ok: " + q.replace(tp, "…")); }
        for (String q : new String[]{"LIST ALL PERMISSIONS", "LIST ROLES", "SELECT role, is_superuser, can_login, member_of FROM system_auth.roles"}) {
            System.out.println("ADMIN " + q + ":");
            for (Row r : s.execute(q)) System.out.println("    " + r.toString());
        }
        c.close();
    }
}
