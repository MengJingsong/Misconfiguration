// o127 cluster-tier driver: the case file's B3a Drive.java (Drive-as-filed.java) with stage-4 amendment S4-A3:
//  (a) the batch wait falls back to the Repair-Task pool's ActiveTasks = PendingTasks = 0 (JMX gauges) once the
//      batch's last cmd has read null for 5 s (the file's own note: a small N can evict it before the poll);
//  (b) mode "probe <cmd>" prints one entry's status and message length (B3g row 6's check, made before the readings);
//  (c) "count" also reports how many cmds in the range are IN_PROGRESS / FAILED.
// Everything else (repairAsync options, batch 500, getParentRepairStatus reads) is the filed driver unchanged.
import javax.management.*; import javax.management.remote.*; import java.util.*;
public class Drive {
  static MBeanServerConnection s; static ObjectName ss;
  static final String[] sigR = {String.class.getName(), Map.class.getName()}, sigS = {"int"};
  static List<?> st(int cmd) throws Exception { return (List<?>) s.invoke(ss, "getParentRepairStatus", new Object[]{cmd}, sigS); }
  static long gauge(String name) throws Exception {
    Object v = s.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=Repair-Task,name=" + name), "Value");
    return ((Number) v).longValue();
  }
  public static void main(String[] a) throws Exception {
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"));
    s = c.getMBeanServerConnection();
    ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
    if (a[0].equals("repair")) {               // repair <M> <batch>
      int m = Integer.parseInt(a[1]), batch = Integer.parseInt(a[2]); int last = 0, fallbacks = 0;
      long t0 = System.currentTimeMillis();
      Map<String,String> o = new HashMap<>(); o.put("ignoreUnreplicatedKeyspaces","true"); o.put("columnFamilies","t");
      for (int i = 1; i <= m; i++) {
        last = (Integer) s.invoke(ss, "repairAsync", new Object[]{"o127", o}, sigR);
        if (last == 0) throw new IllegalStateException("cmd 0: RF<2 short-circuit, no status recorded");
        if (i % batch == 0 || i == m) {        // wait for this batch to finish
          long nullSince = -1; String how = "status";
          while (true) {
            List<?> x = st(last);
            if (x != null && !"IN_PROGRESS".equals(x.get(0))) break;
            if (x == null) {
              long now = System.currentTimeMillis();
              if (nullSince < 0) nullSince = now;
              if (now - nullSince > 5000 && gauge("ActiveTasks") == 0 && gauge("PendingTasks") == 0) { how = "pool-idle"; fallbacks++; break; }
            } else nullSince = -1;
            Thread.sleep(50);
          }
          System.out.println("DRIVE issued=" + i + " lastCmd=" + last + " wait=" + how + " t_ms=" + (System.currentTimeMillis() - t0));
        }
      }
      System.out.println("DRIVE done issued=" + m + " lastCmd=" + last + " fallbacks=" + fallbacks + " t_ms=" + (System.currentTimeMillis() - t0));
    } else if (a[0].equals("count")) {         // count <firstCmd> <lastCmd>
      int lo = Integer.parseInt(a[1]), hi = Integer.parseInt(a[2]), present = 0, completed = 0, inprog = 0, failed = 0;
      for (int i = lo; i <= hi; i++) { List<?> x = st(i);
        if (x != null) { present++; String k = String.valueOf(x.get(0));
          if ("COMPLETED".equals(k)) completed++; else if ("IN_PROGRESS".equals(k)) inprog++; else if ("FAILED".equals(k)) failed++; } }
      System.out.println("COUNT present=" + present + " completed=" + completed + " in_progress=" + inprog + " failed=" + failed);
    } else if (a[0].equals("probe")) {         // probe <cmd>
      int cmd = Integer.parseInt(a[1]); List<?> x = st(cmd);
      if (x == null) System.out.println("PROBE cmd=" + cmd + " null");
      else { String msg = x.size() > 1 ? String.valueOf(x.get(1)) : "";
        System.out.println("PROBE cmd=" + cmd + " status=" + x.get(0) + " parts=" + x.size() + " msg_len=" + msg.length()
                           + " head=" + msg.substring(0, Math.min(160, msg.length())).replace('\n', ' ')); }
    } else if (a[0].equals("pool")) {
      System.out.println("POOL active=" + gauge("ActiveTasks") + " pending=" + gauge("PendingTasks") + " completed=" + gauge("CompletedTasks"));
    }
    c.close();
  }
}
