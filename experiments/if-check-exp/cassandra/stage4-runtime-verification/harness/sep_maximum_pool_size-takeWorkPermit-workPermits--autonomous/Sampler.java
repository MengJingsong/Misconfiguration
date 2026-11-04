import java.io.BufferedReader;
import java.io.File;
import java.io.FileWriter;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * B3d sampler (runbook fixes 2026-10-26, defects 2 and 3) of sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.
 * One persistent JMX connection to the node (127.0.0.1:7199):
 *  - every 1 s: the gauges `nodetool tpstats` prints (NodeProbe.getThreadPoolMetric), NTR and ReadStage ActiveTasks /
 *    PendingTasks, plus NTR MaxPoolSize -> <dir>/tpjmx.log ("t=<ms> ntrA= ntrP= ntrMax= readA= readP= ms=")
 *  - every 5 s: the diagnostic commands Thread.print and VM.native_memory summary, run through the JVM's own
 *    DiagnosticCommand MBean (the same DCmds `jcmd` runs, without a process spawn), saved raw as
 *    <dir>/samples/td-<t>.txt and nmt-<t>.txt; the latest poll line as tp-<t>.txt; `ps -o rss=` (one spawn);
 *    one CSV line in <dir>/samples.csv (phase from <dir>/phase); durations in <dir>/sample-timing.txt.
 * usage: java Sampler <dir> <pid>     (stops when <dir>/stop exists)
 */
public class Sampler
{
    static volatile String lastPoll = "";

    static ObjectName tp(String path, String pool, String m) throws Exception
    {
        return new ObjectName("org.apache.cassandra.metrics:type=ThreadPools,path=" + path + ",scope=" + pool + ",name=" + m);
    }

    static int count(Pattern p, String s)
    {
        Matcher m = p.matcher(s);
        int n = 0;
        while (m.find())
            n++;
        return n;
    }

    static String grp(Pattern p, String s, int g)
    {
        Matcher m = p.matcher(s);
        return m.find() ? m.group(g) : "";
    }

    public static void main(String[] a) throws Exception
    {
        final String dir = a[0];
        final String pid = a[1];
        final File stop = new File(dir, "stop");
        new File(dir, "samples").mkdirs();
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            final MBeanServerConnection m = c.getMBeanServerConnection();
            final ObjectName ntrA = tp("transport", "Native-Transport-Requests", "ActiveTasks");
            final ObjectName ntrP = tp("transport", "Native-Transport-Requests", "PendingTasks");
            final ObjectName ntrM = tp("transport", "Native-Transport-Requests", "MaxPoolSize");
            final ObjectName rsA = tp("request", "ReadStage", "ActiveTasks");
            final ObjectName rsP = tp("request", "ReadStage", "PendingTasks");
            final ObjectName dcmd = new ObjectName("com.sun.management:type=DiagnosticCommand");
            Thread poller = new Thread(() -> {
                try (PrintWriter out = new PrintWriter(new FileWriter(new File(dir, "tpjmx.log"), true), true))
                {
                    while (!stop.exists())
                    {
                        long t0 = System.currentTimeMillis();
                        String line;
                        try
                        {
                            line = "t=" + t0 + " ntrA=" + m.getAttribute(ntrA, "Value") + " ntrP=" + m.getAttribute(ntrP, "Value")
                                   + " ntrMax=" + m.getAttribute(ntrM, "Value") + " readA=" + m.getAttribute(rsA, "Value")
                                   + " readP=" + m.getAttribute(rsP, "Value") + " ms=" + (System.currentTimeMillis() - t0);
                            lastPoll = line;
                        }
                        catch (Exception e)
                        {
                            line = "t=" + t0 + " error=" + e.toString().replace('\n', ' ');
                        }
                        out.println(line);
                        long sl = 1000 - (System.currentTimeMillis() - t0);
                        if (sl > 0)
                            Thread.sleep(sl);
                    }
                }
                catch (Exception e)
                {
                    e.printStackTrace();
                }
            });
            poller.setDaemon(true);
            poller.start();

            Pattern W = Pattern.compile("^\"SharedPool-Worker-\\d+\"", Pattern.MULTILINE);
            Pattern RN = Pattern.compile("Dispatcher\\$RequestProcessor\\.run\\(");
            Pattern RR = Pattern.compile("StorageProxy\\$LocalReadRunnable\\.runMayThrow\\(");
            Pattern TH = Pattern.compile("Thread \\(reserved=(\\d+)KB, committed=(\\d+)KB\\)\\s*\\n\\s*\\(thread #(\\d+)\\)\\s*\\n\\s*\\(stack: reserved=(\\d+)KB, committed=(\\d+)KB\\)");
            Pattern PV = Pattern.compile(" (ntrA|ntrP|readA|readP)=(\\d+)");
            try (PrintWriter csv = new PrintWriter(new FileWriter(new File(dir, "samples.csv"), true), true);
                 PrintWriter tim = new PrintWriter(new FileWriter(new File(dir, "sample-timing.txt"), true), true))
            {
                csv.println("t_ms,phase,W,R_ntr,R_read,ntr_active,ntr_pending,read_active,read_pending,nmt_threads,nmt_thread_res_kb,nmt_thread_com_kb,nmt_stack_res_kb,nmt_stack_com_kb,rss_kb");
                while (!stop.exists())
                {
                    long t = System.currentTimeMillis();
                    String phase = new String(Files.readAllBytes(Paths.get(dir, "phase")), StandardCharsets.UTF_8).trim();
                    String td, nmt;
                    try
                    {
                        td = (String) m.invoke(dcmd, "threadPrint", new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
                    }
                    catch (Exception e)
                    {
                        td = "error " + e;
                    }
                    long t1 = System.currentTimeMillis();
                    try
                    {
                        nmt = (String) m.invoke(dcmd, "vmNativeMemory", new Object[]{ new String[]{ "summary" } }, new String[]{ String[].class.getName() });
                    }
                    catch (Exception e)
                    {
                        nmt = "error " + e;
                    }
                    long t2 = System.currentTimeMillis();
                    String poll = lastPoll;
                    String rss = "";
                    try
                    {
                        Process p = new ProcessBuilder("ps", "-o", "rss=", "-p", pid).redirectErrorStream(true).start();
                        try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream())))
                        {
                            String l = r.readLine();
                            rss = l == null ? "" : l.trim();
                        }
                        p.waitFor();
                    }
                    catch (Exception e)
                    {
                        rss = "";
                    }
                    long t3 = System.currentTimeMillis();
                    Files.write(Paths.get(dir, "samples", "td-" + t + ".txt"), td.getBytes(StandardCharsets.UTF_8));
                    Files.write(Paths.get(dir, "samples", "nmt-" + t + ".txt"), nmt.getBytes(StandardCharsets.UTF_8));
                    Files.write(Paths.get(dir, "samples", "tp-" + t + ".txt"), (poll + "\n").getBytes(StandardCharsets.UTF_8));
                    String na = "", np = "", ra = "", rp = "";
                    Matcher pm = PV.matcher(poll);
                    while (pm.find())
                    {
                        switch (pm.group(1))
                        {
                            case "ntrA": na = pm.group(2); break;
                            case "ntrP": np = pm.group(2); break;
                            case "readA": ra = pm.group(2); break;
                            case "readP": rp = pm.group(2); break;
                        }
                    }
                    csv.println(t + "," + phase + "," + count(W, td) + "," + count(RN, td) + "," + count(RR, td) + "," + na + "," + np + "," + ra + "," + rp
                                + "," + grp(TH, nmt, 3) + "," + grp(TH, nmt, 1) + "," + grp(TH, nmt, 2) + "," + grp(TH, nmt, 4) + "," + grp(TH, nmt, 5) + "," + rss);
                    tim.println(t + " td " + (t1 - t) + " nmt " + (t2 - t1) + " ps " + (t3 - t2) + " total " + (System.currentTimeMillis() - t));
                    long sl = 5000 - (System.currentTimeMillis() - t);
                    if (sl > 0)
                        Thread.sleep(sl);
                }
            }
        }
    }
}
