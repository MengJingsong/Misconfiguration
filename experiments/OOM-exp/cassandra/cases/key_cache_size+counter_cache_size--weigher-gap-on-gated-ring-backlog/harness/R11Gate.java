// R11 gate (2026-11-20), runs on V:  java -Xmx32m R11Gate <G or 0> <port> <log>
// Every 200 ms reads MutationStage PendingTasks over local JMX (127.0.0.1:7199) and appends "<epoch ms> pending=<n>"
// to <log>. Accepts TCP clients on <port>; on the first reading >= G (G > 0) writes "STOP\n" to every connected
// client (and to any client connecting later) and logs "GATE t=<epoch ms> pending=<n>". Keeps logging until killed;
// a JMX failure is logged as "<epoch ms> JMXERR <msg>" and the connection retried every 1 s.
import javax.management.*;
import javax.management.remote.*;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;

public class R11Gate {
    static final List<Socket> clients = new CopyOnWriteArrayList<>();
    static volatile boolean fired = false;
    static synchronized void send(Socket s) {
        try { OutputStream o = s.getOutputStream(); o.write("STOP\n".getBytes()); o.flush(); } catch (IOException e) { }
    }
    public static void main(String[] a) throws Exception {
        long G = Long.parseLong(a[0]); int port = Integer.parseInt(a[1]);
        PrintWriter log = new PrintWriter(new FileWriter(a[2], true), true);
        ServerSocket ss = new ServerSocket(port);
        Thread acc = new Thread(() -> {
            while (true) {
                try { Socket s = ss.accept(); clients.add(s); log.println(System.currentTimeMillis() + " CLIENT " + s.getRemoteSocketAddress()); if (fired) send(s); }
                catch (IOException e) { return; }
            }
        });
        acc.setDaemon(true); acc.start();
        log.println(System.currentTimeMillis() + " START G=" + G + " port=" + port);
        ObjectName on = new ObjectName("org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks");
        MBeanServerConnection c = null; JMXConnector j = null;
        while (true) {
            long t0 = System.currentTimeMillis();
            try {
                if (c == null) {
                    j = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"));
                    c = j.getMBeanServerConnection();
                }
                long p = ((Number) c.getAttribute(on, "Value")).longValue();
                long now = System.currentTimeMillis();
                log.println(now + " pending=" + p);
                if (G > 0 && !fired && p >= G) {
                    fired = true;
                    for (Socket s : clients) send(s);
                    log.println("GATE t=" + now + " pending=" + p + " clients=" + clients.size());
                }
            } catch (Exception e) {
                log.println(System.currentTimeMillis() + " JMXERR " + e.getClass().getSimpleName() + ": " + e.getMessage());
                try { if (j != null) j.close(); } catch (Exception x) { }
                c = null; j = null; Thread.sleep(1000); continue;
            }
            long sl = 200 - (System.currentTimeMillis() - t0);
            if (sl > 0) Thread.sleep(sl);
        }
    }
}
