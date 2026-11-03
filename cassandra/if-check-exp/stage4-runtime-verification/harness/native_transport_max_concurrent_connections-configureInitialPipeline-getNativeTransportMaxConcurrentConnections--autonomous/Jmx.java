// Minimal JMX client for run R (amendment C7): java Jmx <port> <objectName> <attribute> [newLongValue]
// Prints "GET <attr>=<v>" (and "SET <attr>=<new>" then "GET <attr>=<v>" after a set).
import javax.management.*;
import javax.management.remote.*;

public class Jmx
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            ObjectName on = new ObjectName(a[1]);
            System.out.println("GET " + a[2] + "=" + m.getAttribute(on, a[2]));
            if (a.length > 3)
            {
                m.setAttribute(on, new Attribute(a[2], Long.parseLong(a[3])));
                System.out.println("SET " + a[2] + "=" + a[3]);
                System.out.println("GET " + a[2] + "=" + m.getAttribute(on, a[2]));
            }
        }
    }
}
