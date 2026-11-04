import javax.management.*; import javax.management.remote.*;
public class Jmx { public static void main(String[] a) throws Exception {
  MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
  ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
  if (a[1].equals("set")) { try { m.setAttribute(ss, new Attribute("RepairSessionMaximumTreeDepth", Integer.parseInt(a[2]))); System.out.println("OK"); } catch (Exception e) { System.out.println("REJECTED " + e); } }
  System.out.println("now " + m.getAttribute(ss, "RepairSessionMaximumTreeDepth"));
  if (a[1].equals("poll")) { ObjectName d = new ObjectName("java.nio:type=BufferPool,name=direct"); long end = System.currentTimeMillis() + Long.parseLong(a[2]) * 1000;
    while (System.currentTimeMillis() < end) { System.out.println(System.currentTimeMillis() + "," + m.getAttribute(d, "MemoryUsed")); Thread.sleep(200); } } } }
