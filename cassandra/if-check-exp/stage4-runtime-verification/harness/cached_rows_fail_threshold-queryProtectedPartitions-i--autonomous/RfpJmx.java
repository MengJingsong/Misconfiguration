import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier (amendments C2/C4 of 2026-10-27) of cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.
 * (adapted from harness/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/Jmx.java)
 * usage: java RfpJmx host:port set <T>          sets StorageService CachedReplicaRowsFailThreshold, prints "fail=<read back> warn=<warn>"
 *        java RfpJmx host:port get              prints "fail=<..> warn=<..>"
 *        java RfpJmx host:port hist <ks> <tbl>  prints "count=<Count> max=<Max> recent=<i:n ...>" for
 *            org.apache.cassandra.metrics:type=Table,keyspace=<ks>,scope=<tbl>,name=ReplicaFilteringProtectionRowsCachedPerQuery
 *            (recent = the non-zero entries of RecentValues, i.e. the bucket counts recorded since the previous hist call)
 */
public class RfpJmx
{
    public static void main(String[] a) throws Exception
    {
        MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
        ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
        switch (a[1])
        {
            case "set":
                m.setAttribute(ss, new Attribute("CachedReplicaRowsFailThreshold", Integer.parseInt(a[2])));
            case "get":
                System.out.println("fail=" + m.getAttribute(ss, "CachedReplicaRowsFailThreshold") + " warn=" + m.getAttribute(ss, "CachedReplicaRowsWarnThreshold"));
                break;
            case "hist":
                ObjectName h = new ObjectName("org.apache.cassandra.metrics:type=Table,keyspace=" + a[2] + ",scope=" + a[3] + ",name=ReplicaFilteringProtectionRowsCachedPerQuery");
                long[] rv = (long[]) m.getAttribute(h, "RecentValues");
                StringBuilder sb = new StringBuilder();
                for (int i = 0; i < rv.length; i++)
                    if (rv[i] != 0)
                        sb.append(sb.length() == 0 ? "" : " ").append(i).append(':').append(rv[i]);
                System.out.println("count=" + m.getAttribute(h, "Count") + " max=" + m.getAttribute(h, "Max") + " len=" + rv.length + " recent=" + (sb.length() == 0 ? "-" : sb));
                break;
            default:
                throw new IllegalArgumentException(a[1]);
        }
    }
}
