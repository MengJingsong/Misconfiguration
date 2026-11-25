import javax.management.*; import javax.management.remote.*; import java.lang.management.*;
public class Sampler { public static void main(String[] a) throws Exception {
  JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi"));
  MBeanServerConnection m = c.getMBeanServerConnection(); String p = a[1]; int n = Integer.parseInt(a[2]);
  ObjectName pb = new ObjectName("org.apache.cassandra.metrics:type=Connection,scope=" + p + ",name=SmallMessagePendingBytes");
  ObjectName ov = new ObjectName("org.apache.cassandra.metrics:type=Connection,scope=" + p + ",name=SmallMessageDroppedTasksDueToOverload");
  ObjectName nu = new ObjectName("org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize");
  ObjectName dm = new ObjectName("java.nio:type=BufferPool,name=direct");
  ObjectName hp = new ObjectName("java.lang:type=Memory");
  System.out.println("ms,pendingBytes,overloadDrops,netPoolUsed,directUsed,heapUsed");
  for (int i = 0; i < n; i++) {
    Object h = m.getAttribute(hp, "HeapMemoryUsage");
    System.out.println(System.currentTimeMillis() + "," + m.getAttribute(pb, "Value") + "," + m.getAttribute(ov, "Value") + ","
      + m.getAttribute(nu, "Value") + "," + m.getAttribute(dm, "MemoryUsed") + "," + ((javax.management.openmbean.CompositeData) h).get("used"));
    Thread.sleep(500); }
  c.close(); } }
