import javax.management.*; import javax.management.remote.*; import javax.management.openmbean.*;
var env = System.getenv();
var c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + env.get("PORT") + "/jmxrmi"));
var m = c.getMBeanServerConnection();
var sp = new ObjectName("org.apache.cassandra.db:type=StorageProxy");
if (env.get("MODE").equals("set")) { m.setAttribute(sp, new Attribute("MaxHintsInProgress", Integer.parseInt(env.get("L")))); System.out.println("MaxHintsInProgress=" + m.getAttribute(sp, "MaxHintsInProgress")); }
else {
  var thp = new ObjectName("org.apache.cassandra.metrics:type=Storage,name=TotalHintsInProgress");
  var pend = new ObjectName("org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks");
  var una = new ObjectName("org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Unavailables");
  var mem = new ObjectName("java.lang:type=Memory");
  var w = new java.io.PrintWriter(new java.io.FileWriter(env.get("OUT")), true);
  w.println("ms,limit,hintsInProgress,mutationPending,unavailables,heapUsed");
  while (!new java.io.File(env.get("OUT") + ".stop").exists()) {
    w.println(System.currentTimeMillis() + "," + m.getAttribute(sp, "MaxHintsInProgress") + "," + m.getAttribute(thp, "Count") + "," + m.getAttribute(pend, "Value") + "," + m.getAttribute(una, "Count") + "," + ((CompositeData) m.getAttribute(mem, "HeapMemoryUsage")).get("used"));
    Thread.sleep(200);
  }
  w.close();
}
c.close();
/exit
