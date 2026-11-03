import javax.management.*; import javax.management.remote.*;
public class Jmx { public static void main(String[] a) throws Exception {
  MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
  ObjectName sp = new ObjectName("org.apache.cassandra.db:type=StorageProxy");
  if (a[1].equals("set")) { try { m.setAttribute(sp, new Attribute(a[2], Integer.parseInt(a[3]))); System.out.println("OK " + a[3]); } catch (Exception e) { System.out.println("REJECTED " + a[3] + " " + e); } }
  if (a[1].equals("load")) { m.invoke(sp, "loadPartitionDenylist", new Object[0], new String[0]); System.out.println("loaded"); } } }
