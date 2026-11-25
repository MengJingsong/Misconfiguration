// 3-b confirm B29 (pc82, 2026-11-24): read / set the auth read consistency level of a running node through its
// AuthProperties MXBean (org.apache.cassandra.auth:type=AuthProperties). Operator tool, used on node 2 only (deviation).
//   java AuthJmx <jmxport> [newReadCL]
import javax.management.*; import javax.management.remote.*;
public class AuthJmx {
    public static void main(String[] a) throws Exception {
        try (JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi"))) {
            MBeanServerConnection m = c.getMBeanServerConnection(); ObjectName n = new ObjectName("org.apache.cassandra.auth:type=AuthProperties");
            System.out.println("port " + a[0] + " before: read=" + m.getAttribute(n, "ReadConsistencyLevel") + " write=" + m.getAttribute(n, "WriteConsistencyLevel"));
            if (a.length > 1) { m.setAttribute(n, new Attribute("ReadConsistencyLevel", a[1]));
                System.out.println("port " + a[0] + " after:  read=" + m.getAttribute(n, "ReadConsistencyLevel") + " write=" + m.getAttribute(n, "WriteConsistencyLevel")); }
        }
    }
}
