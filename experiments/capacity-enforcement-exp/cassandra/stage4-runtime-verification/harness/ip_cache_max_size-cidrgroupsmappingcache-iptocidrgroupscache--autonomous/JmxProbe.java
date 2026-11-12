// B3e step 6 (W1), as filed, with the JMX port as a third argument (amendment AM2).
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.*;
public class JmxProbe {
  public static void main(String[] a) throws Exception {
    int start = Integer.parseInt(a[0]), n = Integer.parseInt(a[1]);
    int port = a.length > 2 ? Integer.parseInt(a[2]) : 7199;
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi"));
    MBeanServerConnection m = c.getMBeanServerConnection();
    ObjectName on = new ObjectName("org.apache.cassandra.db:type=CIDRGroupsMappingManager");
    long t0 = System.nanoTime();
    Object first = null, last = null;
    for (int i = start; i < start + n; i++) {
      String ip = "127." + ((i >>> 16) & 255) + "." + ((i >>> 8) & 255) + "." + (i & 255);
      last = m.invoke(on, "getCidrGroupsOfIP", new Object[]{ ip }, new String[]{ "java.lang.String" });
      if (i == start) first = last;
    }
    System.out.printf("done %d lookups in %.1f s (first result %s, last result %s)%n", n, (System.nanoTime() - t0) / 1e9, first, last);
    c.close();
  }
}
