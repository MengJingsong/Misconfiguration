// B21 3-b confirm (pc72, 2026-11-23): superuser setup of roles / admin schema / grants, and the claim checks of the
// 3-b analysis that rested on code reading (privileges, downgrade, page-size override, MAX_TOP_K, guardrails for
// ordinary roles). Uses B21Load.cluster(host, conns, user, pass).
//   java B21Load admin-setup <host>     superuser cassandra/cassandra (default role; login retried up to 120 s)
//   java B21Load authcheck <host>       run in a discarded node copy (AUTHCHECK lifetime), never in a reading
import com.datastax.driver.core.*;
import java.util.*;

public class AuthCheck {
    static final String SU = "cassandra", SUPW = "cassandra";
    // roles: attacker = data role (SELECT, MODIFY on b21.docs); tenant = victim role (SELECT, MODIFY on vic.kv);
    // reader = SELECT on b21.docs only; ddl = CREATE ON ALL KEYSPACES; ddlks = CREATE ON KEYSPACE b21 (claim checks only)
    static final String[][] ROLES = {{"attacker", "atk-3b-B21"}, {"tenant", "ten-3b-B21"}, {"reader", "rd-3b-B21"},
                                     {"ddl", "ddl-3b-B21"}, {"ddlks", "ddlks-3b-B21"}};
    static String pw(String r) { for (String[] x : ROLES) if (x[0].equals(r)) return x[1]; return null; }

    static Session login(String host, String user, String pass, int waitSecs, List<Cluster> keep) throws Exception {
        long end = System.currentTimeMillis() + waitSecs * 1000L; Exception last = null;
        do {
            Cluster c = B21Load.cluster(host, 1, user, pass);
            try { Session s = c.connect(); keep.add(c); return s; }
            catch (Exception e) { last = e; c.close(); if (waitSecs == 0) break; Thread.sleep(3000); }
        } while (System.currentTimeMillis() < end);
        throw last;
    }

    static void run(Session s, String tag, String q) {
        try { ResultSet rs = s.execute(q); int n = 0; for (Row r : rs) n++; System.out.println(tag + " OK " + q + (n > 0 ? "  rows=" + n : "")); }
        catch (Exception e) { System.out.println(tag + " ERR " + q + "  -> " + e.getClass().getSimpleName() + ": " + e.getMessage()); }
    }

    public static void adminSetup(String host) throws Exception {
        List<Cluster> keep = new ArrayList<>();
        Session s = login(host, SU, SUPW, 120, keep);
        System.out.println("ADMIN login as superuser " + SU + " ok");
        for (String[] r : ROLES) run(s, "ADMIN", "CREATE ROLE IF NOT EXISTS " + r[0] + " WITH PASSWORD = '" + r[1] + "' AND LOGIN = true AND SUPERUSER = false");
        // admin-made schema (label: data role on an admin-made table); same DDL as stage 2
        run(s, "ADMIN", "CREATE KEYSPACE IF NOT EXISTS b21 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
        run(s, "ADMIN", "CREATE TABLE IF NOT EXISTS b21.docs (id int PRIMARY KEY, emb vector<float, 16>, body text)");
        run(s, "ADMIN", "CREATE INDEX IF NOT EXISTS docs_emb ON b21.docs(emb) USING 'sai'");
        run(s, "ADMIN", "CREATE KEYSPACE IF NOT EXISTS vic WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
        run(s, "ADMIN", "CREATE TABLE IF NOT EXISTS vic.kv (k int PRIMARY KEY, v text)");
        run(s, "ADMIN", "GRANT SELECT ON TABLE b21.docs TO attacker");
        run(s, "ADMIN", "GRANT MODIFY ON TABLE b21.docs TO attacker");
        run(s, "ADMIN", "GRANT SELECT ON TABLE vic.kv TO tenant");
        run(s, "ADMIN", "GRANT MODIFY ON TABLE vic.kv TO tenant");
        run(s, "ADMIN", "GRANT SELECT ON TABLE b21.docs TO reader");
        run(s, "ADMIN", "GRANT CREATE ON ALL KEYSPACES TO ddl");
        run(s, "ADMIN", "GRANT CREATE ON KEYSPACE b21 TO ddlks");
        for (Row r : s.execute("SELECT role, is_superuser, can_login, member_of FROM system_auth.roles")) System.out.println("ROLE " + r);
        for (String[] r : ROLES)
            for (Row p : s.execute("LIST ALL PERMISSIONS OF " + r[0])) System.out.println("PERM " + r[0] + " " + p.getString("resource") + " " + p.getString("permission"));
        for (Cluster c : keep) c.close();
        System.out.println("admin-setup done");
    }

    static String annQ(String tab, int limit, long seed) {
        Random r = new Random(seed); StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 16; i++) sb.append(i == 0 ? "" : ", ").append(0.1f + 0.9f * r.nextFloat());
        return "SELECT id, body FROM " + tab + " ORDER BY emb ANN OF [" + sb + "] LIMIT " + limit;
    }

    // one SELECT with explicit fetch size and CL; prints rows, pages, value bytes, warnings
    static void sel(Session s, String tag, String q, int fetch, ConsistencyLevel cl) {
        Statement st = new SimpleStatement(q).setFetchSize(fetch).setConsistencyLevel(cl);
        long t0 = System.nanoTime();
        try {
            ResultSet rs = s.execute(st); int n = 0; long vb = 0;
            for (Row r : rs) { n++; java.nio.ByteBuffer b = r.getBytesUnsafe("body"); if (b != null) vb += b.remaining(); }
            List<String> w = new ArrayList<>(); for (ExecutionInfo e : rs.getAllExecutionInfo()) if (e.getWarnings() != null) w.addAll(e.getWarnings());
            System.out.println(tag + " OK cl=" + cl + " fetch=" + fetch + " rows=" + n + " pages=" + rs.getAllExecutionInfo().size() + " vbytes=" + vb
                + " ms=" + (System.nanoTime() - t0) / 1000000 + " warnings=" + w + "  q=" + q.replaceAll("\\[[^\\]]*\\]", "[..]"));
        } catch (Exception e) {
            System.out.println(tag + " ERR cl=" + cl + " -> " + e.getClass().getSimpleName() + ": " + e.getMessage() + "  q=" + q.replaceAll("\\[[^\\]]*\\]", "[..]"));
        }
    }

    static void ins(Session s, String tag, String tab, int id, int chars) {
        try {
            PreparedStatement ps = s.prepare("INSERT INTO " + tab + " (id, emb, body) VALUES (?, ?, ?)");
            BoundStatement b = ps.bind(); b.setInt(0, id); b.setBytesUnsafe(1, B21Load.embBytes(B21Load.emb(id))); b.setString(2, B21Load.body(id, chars));
            s.execute(b); System.out.println(tag + " OK insert " + tab + " id=" + id + " body=" + chars + " chars");
        } catch (Exception e) { System.out.println(tag + " ERR insert " + tab + " id=" + id + " body=" + chars + " -> " + e.getClass().getSimpleName() + ": " + e.getMessage()); }
    }

    public static void check(String host) throws Exception {
        List<Cluster> keep = new ArrayList<>();
        // C1 pre-auth through the driver: no credentials, wrong password
        try { login(host, null, null, 0, keep); System.out.println("C1a no-credentials connect OK (unexpected)"); }
        catch (Exception e) { System.out.println("C1a no-credentials connect ERR -> " + e.getClass().getSimpleName() + ": " + e.getMessage()); }
        try { login(host, "attacker", "wrong", 0, keep); System.out.println("C1b wrong-password connect OK (unexpected)"); }
        catch (Exception e) { System.out.println("C1b wrong-password connect ERR -> " + e.getClass().getSimpleName() + ": " + e.getMessage()); }

        // C2 data role (attacker: SELECT, MODIFY on b21.docs)
        Session a = login(host, "attacker", pw("attacker"), 30, keep);
        System.out.println("C2 attacker login ok");
        sel(a, "C2a T-LIMIT10", annQ("b21.docs", 10, 1), 100, ConsistencyLevel.ONE);
        sel(a, "C2b T-LIMIT1000-fetch100 (page-size override)", annQ("b21.docs", 1000, 2), 100, ConsistencyLevel.ONE);
        sel(a, "C2c T-LIMIT1001 (MAX_TOP_K)", annQ("b21.docs", 1001, 3), 100, ConsistencyLevel.ONE);
        sel(a, "C2d T-LIMIT1000 CL QUORUM (downgrade)", annQ("b21.docs", 1000, 4), 100, ConsistencyLevel.QUORUM);
        sel(a, "C2e T-LIMIT1000 CL ALL (downgrade)", annQ("b21.docs", 1000, 5), 100, ConsistencyLevel.ALL);
        sel(a, "C2f T-LIMIT1000 fetch 5000", annQ("b21.docs", 1000, 6), 5000, ConsistencyLevel.ONE);
        ins(a, "C2g", "b21.docs", 900000, 122880);
        ins(a, "C2h", "b21.docs", 900001, 1048576);
        ins(a, "C2i", "b21.docs", 900002, 8 * 1048576);
        run(a, "C2j", "CREATE INDEX docs_body ON b21.docs(body) USING 'sai'");
        run(a, "C2k", "CREATE TABLE b21.mine (id int PRIMARY KEY, emb vector<float, 16>, body text)");
        run(a, "C2l", "CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
        run(a, "C2m", "SELECT k FROM vic.kv LIMIT 1");
        run(a, "C2n", "INSERT INTO vic.kv (k, v) VALUES (1, 'x')");
        run(a, "C2o", "SELECT count(*) FROM system_auth.roles");
        run(a, "C2p", "DROP TABLE b21.docs");

        // C3 SELECT-only role on the admin table (rows already exist)
        Session r = login(host, "reader", pw("reader"), 30, keep);
        sel(r, "C3a reader T-LIMIT1000-fetch100", annQ("b21.docs", 1000, 7), 100, ConsistencyLevel.ONE);
        ins(r, "C3b reader", "b21.docs", 900010, 100);

        // C4 DDL role (CREATE ON ALL KEYSPACES): own keyspace, vector table, SAI index, wide row, ANN query
        Session d = login(host, "ddl", pw("ddl"), 30, keep);
        run(d, "C4a", "CREATE KEYSPACE ddl1 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
        run(d, "C4b", "CREATE TABLE ddl1.docs (id int PRIMARY KEY, emb vector<float, 16>, body text)");
        run(d, "C4c", "CREATE INDEX ddl1_emb ON ddl1.docs(emb) USING 'sai'");
        ins(d, "C4d", "ddl1.docs", 1, 122880);
        sel(d, "C4e ddl T-LIMIT1000 own table", annQ("ddl1.docs", 1000, 8), 100, ConsistencyLevel.ONE);
        run(d, "C4f", "SELECT id FROM b21.docs LIMIT 1");
        // C5 guardrails do apply to ordinary roles (contrast: skipped for superusers / AllowAllAuthenticator):
        // sai_string_term_size_fail_threshold (8 KiB default) on an SAI-indexed text column
        run(d, "C5a", "CREATE TABLE ddl1.s (id int PRIMARY KEY, t text)");
        run(d, "C5b", "CREATE INDEX ddl1_s_t ON ddl1.s(t) USING 'sai'");
        String big = B21Load.body(5, 9 * 1024);
        try { d.execute(new SimpleStatement("INSERT INTO ddl1.s (id, t) VALUES (1, ?)", big)); System.out.println("C5c ddl insert 9 KiB into SAI text OK"); }
        catch (Exception e) { System.out.println("C5c ddl insert 9 KiB into SAI text ERR -> " + e.getClass().getSimpleName() + ": " + e.getMessage()); }
        Session su = login(host, SU, SUPW, 30, keep);
        try { su.execute(new SimpleStatement("INSERT INTO ddl1.s (id, t) VALUES (2, ?)", big)); System.out.println("C5d superuser insert 9 KiB into SAI text OK"); }
        catch (Exception e) { System.out.println("C5d superuser insert 9 KiB into SAI text ERR -> " + e.getClass().getSimpleName() + ": " + e.getMessage()); }

        // C6 keyspace-scoped DDL role (CREATE ON KEYSPACE b21)
        Session k = login(host, "ddlks", pw("ddlks"), 30, keep);
        run(k, "C6a", "CREATE TABLE b21.own (id int PRIMARY KEY, emb vector<float, 16>, body text)");
        run(k, "C6b", "CREATE INDEX own_emb ON b21.own(emb) USING 'sai'");
        ins(k, "C6c", "b21.own", 1, 122880);
        sel(k, "C6d ddlks T own table", annQ("b21.own", 10, 9), 100, ConsistencyLevel.ONE);
        run(k, "C6e", "CREATE KEYSPACE ks2 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
        for (Row p : su.execute("LIST ALL PERMISSIONS OF ddl")) System.out.println("C4g PERM ddl " + p.getString("resource") + " " + p.getString("permission"));
        for (Row p : su.execute("LIST ALL PERMISSIONS OF ddlks")) System.out.println("C6f PERM ddlks " + p.getString("resource") + " " + p.getString("permission"));
        for (Cluster c : keep) c.close();
        System.out.println("authcheck done");
    }
}
