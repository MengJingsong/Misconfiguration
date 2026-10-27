import javax.management.*; import javax.management.remote.*;
/** usage: JmxSet HOST PORT BYTES -> StorageService.setNativeTransportMaxConcurrentRequestsInBytesPerIp(BYTES), prints the read-back. */
public class JmxSet {
  public static void main(String[] a) throws Exception {
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + ":" + a[1] + "/jmxrmi"));
    MBeanServerConnection m = c.getMBeanServerConnection(); ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
    System.out.println("before=" + m.getAttribute(ss, "NativeTransportMaxConcurrentRequestsInBytesPerIp") + " t=" + System.currentTimeMillis());
    m.setAttribute(ss, new Attribute("NativeTransportMaxConcurrentRequestsInBytesPerIp", Long.parseLong(a[2])));   // get/set pair = writable attribute
    System.out.println("after=" + m.getAttribute(ss, "NativeTransportMaxConcurrentRequestsInBytesPerIp") + " t=" + System.currentTimeMillis());
    c.close();
  }
}
