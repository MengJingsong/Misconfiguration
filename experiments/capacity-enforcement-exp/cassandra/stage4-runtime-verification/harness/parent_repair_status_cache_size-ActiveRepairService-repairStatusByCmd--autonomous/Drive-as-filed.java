import javax.management.*; import javax.management.remote.*; import java.util.*;
public class Drive {
  public static void main(String[] a) throws Exception {
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"));
    MBeanServerConnection s = c.getMBeanServerConnection();
    ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
    String[] sigR = {String.class.getName(), Map.class.getName()}, sigS = {"int"};
    if (a[0].equals("repair")) {               // repair <M> <batch>
      int m = Integer.parseInt(a[1]), batch = Integer.parseInt(a[2]); int last = 0;
      Map<String,String> o = new HashMap<>(); o.put("ignoreUnreplicatedKeyspaces","true"); o.put("columnFamilies","t");
      for (int i = 1; i <= m; i++) {
        last = (Integer) s.invoke(ss, "repairAsync", new Object[]{"o127", o}, sigR);
        if (last == 0) throw new IllegalStateException("cmd 0: RF<2 short-circuit, no status recorded");
        if (i % batch == 0 || i == m) {        // wait for this batch to finish
          while (true) { List<?> st = (List<?>) s.invoke(ss, "getParentRepairStatus", new Object[]{last}, sigS);
            if (st != null && !"IN_PROGRESS".equals(st.get(0))) break; Thread.sleep(50); }
          System.out.println("DRIVE issued=" + i + " lastCmd=" + last);
        }
      }
    } else if (a[0].equals("count")) {         // count <firstCmd> <lastCmd>
      int lo = Integer.parseInt(a[1]), hi = Integer.parseInt(a[2]), present = 0, completed = 0;
      for (int i = lo; i <= hi; i++) { List<?> st = (List<?>) s.invoke(ss, "getParentRepairStatus", new Object[]{i}, sigS);
        if (st != null) { present++; if ("COMPLETED".equals(st.get(0))) completed++; } }
      System.out.println("COUNT present=" + present + " completed=" + completed);
    }
    c.close();
  }
}
