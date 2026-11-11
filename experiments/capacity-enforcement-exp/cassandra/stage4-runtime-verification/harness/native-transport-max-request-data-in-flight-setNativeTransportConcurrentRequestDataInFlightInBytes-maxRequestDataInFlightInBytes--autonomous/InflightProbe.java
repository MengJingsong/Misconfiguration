import javax.management.*; import javax.management.remote.*; import javax.management.openmbean.CompositeData;
public class InflightProbe {
  public static void main(String[] a) throws Exception {
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + ":" + a[1] + "/jmxrmi"));
    MBeanServerConnection m = c.getMBeanServerConnection(); long period = Long.parseLong(a[2]), dur = Long.parseLong(a[3]);
    ObjectName rs = new ObjectName("org.apache.cassandra.metrics:type=Client,name=RequestsSize");
    ObjectName pc = new ObjectName("org.apache.cassandra.metrics:type=Client,name=PausedConnections");
    ObjectName dp = new ObjectName("java.nio:type=BufferPool,name=direct");
    ObjectName me = new ObjectName("java.lang:type=Memory");
    long t0 = System.currentTimeMillis(); System.out.println("t_ms,requests_size,paused,direct_used,direct_count,heap_used");
    while (System.currentTimeMillis() - t0 < dur) {
      System.out.println((System.currentTimeMillis() - t0) + "," + m.getAttribute(rs, "Value") + "," + m.getAttribute(pc, "Value") + ","
        + m.getAttribute(dp, "MemoryUsed") + "," + m.getAttribute(dp, "Count") + ","
        + ((CompositeData) m.getAttribute(me, "HeapMemoryUsage")).get("used"));
      Thread.sleep(period);
    }
    c.close();
  }
}
