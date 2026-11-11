import javax.management.*; import javax.management.remote.*; import javax.management.openmbean.CompositeData;
/** usage: PiProbe HOST PORT PERIOD_MS DURATION_MS -> CSV on stdout (JMX: RequestsSize, PausedConnections, direct pool, heap, by-IP histogram max). */
public class PiProbe {
  static Object get(MBeanServerConnection m, ObjectName o, String a) { try { return m.getAttribute(o, a); } catch (Exception e) { return "NA"; } }
  public static void main(String[] a) throws Exception {
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + ":" + a[1] + "/jmxrmi"));
    MBeanServerConnection m = c.getMBeanServerConnection(); long period = Long.parseLong(a[2]), dur = Long.parseLong(a[3]);
    ObjectName rs = new ObjectName("org.apache.cassandra.metrics:type=Client,name=RequestsSize");
    ObjectName pc = new ObjectName("org.apache.cassandra.metrics:type=Client,name=PausedConnections");
    ObjectName bi = new ObjectName("org.apache.cassandra.metrics:type=Client,name=RequestsSizeByIpDistribution");
    ObjectName dp = new ObjectName("java.nio:type=BufferPool,name=direct");
    ObjectName me = new ObjectName("java.lang:type=Memory");
    long t0 = System.currentTimeMillis(); System.out.println("t_ms,requests_size,paused,direct_used,direct_count,heap_used,byip_max,epoch_ms");
    while (System.currentTimeMillis() - t0 < dur) {
      long now = System.currentTimeMillis();
      System.out.println((now - t0) + "," + get(m, rs, "Value") + "," + get(m, pc, "Value") + "," + get(m, dp, "MemoryUsed") + "," + get(m, dp, "Count") + ","
        + ((CompositeData) m.getAttribute(me, "HeapMemoryUsage")).get("used") + "," + get(m, bi, "Max") + "," + now);
      Thread.sleep(period);
    }
    c.close();
  }
}
