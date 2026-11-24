// B17 3-b confirm (pc75, 2026-11-23): checks of the 3-b analysis claims that rested on code reading, run as each role through
// the native protocol (Java driver 3.12.1, protocol v4, CL ONE) on a discarded copy of the template (lifetime AUTHCHECK).
//   java B17Auth <host>
// Prints "CHECK <role> | <what> | OK <detail>" or "CHECK <role> | <what> | ERR <ExceptionClass>: <message>".
import com.datastax.driver.core.*;
import java.nio.ByteBuffer;
import java.util.*;

public class B17Auth {
    static void chk(String role, String what, Session s, Statement st) {
        try {
            long t0 = System.nanoTime();
            ResultSet rs = s.execute(st);
            int rows = 0; long vb = 0; StringBuilder first = new StringBuilder();
            boolean hasV = rs.getColumnDefinitions().contains("v"), hasPk = rs.getColumnDefinitions().contains("pk") && rs.getColumnDefinitions().contains("ck");
            for (Row r : rs) {
                if (hasV) { ByteBuffer v = r.getBytesUnsafe("v"); if (v != null) vb += v.remaining(); }
                if (hasPk && rows < 10) first.append(rows == 0 ? "" : " ").append(r.getInt("pk")).append('/').append(r.getInt("ck"));
                rows++;
            }
            List<String> w = rs.getExecutionInfo().getWarnings();
            System.out.println("CHECK " + role + " | " + what + " | OK rows=" + rows + " vbytes=" + vb + " ms=" + (System.nanoTime() - t0) / 1000000
                + (first.length() > 0 ? " first=[" + first + "]" : "") + (w.isEmpty() ? "" : " warnings=" + w));
        } catch (Exception e) {
            System.out.println("CHECK " + role + " | " + what + " | ERR " + e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace('\n', ' '));
        }
    }

    static Session login(String role, String user, String pass, String host) {
        try {
            Cluster c = B17Load.cluster(host, 1, user, pass);
            Session s = c.connect();
            System.out.println("CHECK " + role + " | login as " + user + " | OK");
            return s;
        } catch (Exception e) {
            System.out.println("CHECK " + role + " | login as " + user + " | ERR " + e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace('\n', ' '));
            return null;
        }
    }

    static Statement q(String cql, int fetch, Object... v) {
        SimpleStatement st = new SimpleStatement(cql, v);
        st.setFetchSize(fetch == -1 ? Integer.MAX_VALUE : fetch);
        return st;
    }

    static ByteBuffer blob(int n) { byte[] b = new byte[n]; new Random(n).nextBytes(b); return ByteBuffer.wrap(b); }

    public static void main(String[] a) throws Exception {
        String host = a[0];
        // pre-login
        login("none", null, null, host);
        login("attacker-wrongpw", "attacker", "wrong", host);
        Session at = login("attacker", "attacker", "atk-3b-B17", host);
        String T2 = "SELECT * FROM b17.t WHERE pk IN (3, 7) ORDER BY ck LIMIT 10";
        if (at != null) {
            chk("attacker", "T k=2 paged (fetch 5000): paging refused for every role", at, q(T2, 5000));
            chk("attacker", "T k=2 unpaged (fetch -1): the client's choice", at, q(T2, -1));
            chk("attacker", "I k=2 (PER PARTITION LIMIT 10) unpaged", at, q("SELECT * FROM b17.t WHERE pk IN (3, 7) ORDER BY ck PER PARTITION LIMIT 10 LIMIT 10", -1));
            StringBuilder in = new StringBuilder(); for (int i = 1000; i < 1200; i++) in.append(i == 1000 ? "" : ",").append(i);
            chk("attacker", "IN with 200 keys, ORDER BY, unpaged (partition_keys_in_select guardrail off for this role)", at,
                q("SELECT pk, ck FROM b17.t WHERE pk IN (" + in + ") ORDER BY ck LIMIT 10", -1));
            chk("attacker", "INSERT 256 KiB value (MODIFY)", at, q("INSERT INTO b17.t (pk, ck, v) VALUES (?, ?, ?)", 5000, 900, 0, blob(262144)));
            chk("attacker", "INSERT 8 MiB value (no value-size guardrail for this role)", at, q("INSERT INTO b17.t (pk, ck, v) VALUES (?, ?, ?)", 5000, 900, 1, blob(8 << 20)));
            chk("attacker", "INSERT 17 MiB value (max_mutation_size 16 MiB applies)", at, q("INSERT INTO b17.t (pk, ck, v) VALUES (?, ?, ?)", 5000, 900, 2, blob(17 << 20)));
            chk("attacker", "CREATE TABLE in b17 (no CREATE)", at, q("CREATE TABLE b17.x (k int PRIMARY KEY)", 5000));
            chk("attacker", "CREATE KEYSPACE (no CREATE)", at, q("CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}", 5000));
            chk("attacker", "ALTER TABLE b17.t (no ALTER)", at, q("ALTER TABLE b17.t WITH comment = 'x'", 5000));
            chk("attacker", "DROP TABLE b17.t (no DROP)", at, q("DROP TABLE b17.t", 5000));
            chk("attacker", "SELECT vic.kv (another tenant's table)", at, q("SELECT * FROM vic.kv LIMIT 1", 5000));
            chk("attacker", "INSERT vic.kv (another tenant's table)", at, q("INSERT INTO vic.kv (k, v) VALUES (1, 'x')", 5000));
            chk("attacker", "SELECT system_auth.roles", at, q("SELECT role FROM system_auth.roles", 5000));
            chk("attacker", "LIST ALL PERMISSIONS OF attacker", at, q("LIST ALL PERMISSIONS OF attacker", 5000));
            at.getCluster().close();
        }
        Session rd = login("reader", "reader", "rd-3b-B17", host);
        if (rd != null) {
            chk("reader", "T k=2 unpaged (SELECT only)", rd, q(T2, -1));
            chk("reader", "INSERT into b17.t (no MODIFY)", rd, q("INSERT INTO b17.t (pk, ck, v) VALUES (901, 0, 0x00)", 5000));
            rd.getCluster().close();
        }
        Session tn = login("tenant", "tenant", "ten-3b-B17", host);
        if (tn != null) {
            chk("tenant", "SELECT b17.t (attacker's table)", tn, q("SELECT pk FROM b17.t LIMIT 1", 5000));
            chk("tenant", "SELECT vic.kv (own)", tn, q("SELECT k FROM vic.kv LIMIT 1", 5000));
            tn.getCluster().close();
        }
        System.out.println("authcheck done");
        System.exit(0);
    }
}
