// B12 3-b confirm (ms0604, 2026-11-24; from B19 3-b's B19Admin): superuser setup through the Java driver 3.12.1
// (protocol v4). Used ONLY to create the roles, the admin-made schema (the stage-2 table b12.t and the tenant's vic.kv)
// and the grants, and to read back the resolved settings. The attacker never uses the superuser.
//   java -Duser=cassandra -Dpass=cassandra B12Admin <host> <attackerPw> <nograntPw> <tenantPw>
// (retries login for up to 90 s while the default superuser is being set up)
import com.datastax.driver.core.*;

public class B12Admin {
    public static void main(String[] a) throws Exception {
        String host = a[0], ap = a[1], np = a[2], tp = a[3];
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
            "CREATE ROLE IF NOT EXISTS attacker WITH PASSWORD = '" + ap + "' AND LOGIN = true AND SUPERUSER = false",
            "CREATE ROLE IF NOT EXISTS nogrant WITH PASSWORD = '" + np + "' AND LOGIN = true AND SUPERUSER = false",
            "CREATE ROLE IF NOT EXISTS tenant WITH PASSWORD = '" + tp + "' AND LOGIN = true AND SUPERUSER = false",
            "CREATE KEYSPACE IF NOT EXISTS b12 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
            "CREATE TABLE IF NOT EXISTS b12.t (k blob PRIMARY KEY, v int)",
            "CREATE KEYSPACE IF NOT EXISTS vic WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
            "CREATE TABLE IF NOT EXISTS vic.kv (k int PRIMARY KEY, v text)",
            "GRANT SELECT ON TABLE b12.t TO attacker",
            "GRANT SELECT ON TABLE vic.kv TO tenant",
            "GRANT MODIFY ON TABLE vic.kv TO tenant",
        };
        for (String q : st) {
            s.execute(new SimpleStatement(q).setConsistencyLevel(ConsistencyLevel.ONE));
            System.out.println("ADMIN ok: " + q.replace(ap, "…").replace(np, "…").replace(tp, "…"));
        }
        for (String q : new String[]{"LIST ALL PERMISSIONS", "SELECT role, is_superuser, can_login, member_of FROM system_auth.roles"}) {
            System.out.println("ADMIN " + q + ":");
            for (Row r : s.execute(q)) System.out.println("    " + r.toString());
        }
        System.out.println("ADMIN settings:");
        for (Row r : s.execute("SELECT name, value FROM system_views.settings")) {
            String n = r.getString(0);
            if (n.matches("paxos_.*|authenticator.*|authorizer.*|role_manager.*|network_authorizer.*|memtable_heap_space|memtable_allocation_type|key_cache_size|native_transport_max_request_data_in_flight.*|native_transport_max_frame_size|native_transport_max_concurrent_connections.*|native_transport_rate_limiting_enabled|read_consistency_levels_disallowed|read_consistency_levels_warned|cas_contention_timeout|read_request_timeout|write_request_timeout|native_transport_timeout|denylist_.*enabled.*|partition_keys_in_select.*"))
                System.out.println("    " + n + " = " + r.getString(1));
        }
        c.close();
    }
}
