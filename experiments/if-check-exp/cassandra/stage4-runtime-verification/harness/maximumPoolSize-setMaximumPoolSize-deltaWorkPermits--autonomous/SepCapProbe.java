import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.management.ManagementFactory;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.concurrent.ExecutorPlus;
import org.apache.cassandra.concurrent.LocalAwareExecutorPlus;
import org.apache.cassandra.concurrent.SEPExecutor;
import org.apache.cassandra.concurrent.SharedExecutorPool;

/**
 * Unit tier (B2) of maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous. A main class (B2a allows "a JUnit test or main"),
 * built directly with SharedExecutorPool.newExecutor, no DatabaseDescriptor. Prints one "PROBE ..." / "RESIZE ..." / "CTRL ..." line per reading.
 * Variant A: each task allocates a 1 MiB byte[] when it RUNS and registers it, then blocks on a latch. Variant B: the SUBMITTING thread allocates the
 * 1 MiB byte[] per task, so a queued task holds it too. Control: ThreadPoolExecutor(n, n) with ArrayBlockingQueue(64) + AbortPolicy, variant B.
 * usage: java ... SepCapProbe <label>
 */
public class SepCapProbe
{
    static final int MIB = 1 << 20;
    static final ConcurrentLinkedQueue<byte[]> registry = new ConcurrentLinkedQueue<>();
    static final AtomicLong allocatedMiB = new AtomicLong();

    static long heapUsed()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(100); } catch (InterruptedException e) { } }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static long nmtThreadCommittedKB()
    {
        try
        {
            long pid = ProcessHandle.current().pid();
            Process p = new ProcessBuilder("jcmd", Long.toString(pid), "VM.native_memory", "summary").redirectErrorStream(true).start();
            BufferedReader br = new BufferedReader(new InputStreamReader(p.getInputStream()));
            String l; boolean in = false;
            Pattern pat = Pattern.compile("committed=(\\d+)KB");
            while ((l = br.readLine()) != null)
            {
                if (l.startsWith("-                    Thread (")) in = true;
                if (in) { Matcher m = pat.matcher(l); if (m.find()) { p.waitFor(); return Long.parseLong(m.group(1)); } }
            }
            p.waitFor();
        }
        catch (Exception e) { }
        return -1;
    }

    static int poolThreads(String prefix)
    {
        int c = 0;
        for (Thread t : Thread.getAllStackTraces().keySet())
            if (t.getThreadGroup() != null && t.getThreadGroup().getName().endsWith(prefix)) c++;
        return c;
    }

    static void sleep(long ms) { try { Thread.sleep(ms); } catch (InterruptedException e) { throw new RuntimeException(e); } }

    static void sepRun(String variant, int n, int T, String label) throws Exception
    {
        registry.clear(); allocatedMiB.set(0);
        long base = heapUsed();
        long nmt0 = nmtThreadCommittedKB();
        int th0 = ManagementFactory.getThreadMXBean().getThreadCount();
        SharedExecutorPool pool = new SharedExecutorPool("probe");
        LocalAwareExecutorPlus ex = pool.newExecutor(n, "internal", "probe");
        CountDownLatch gate = new CountDownLatch(1);
        AtomicInteger running = new AtomicInteger();
        AtomicInteger done = new AtomicInteger();
        long ts = System.nanoTime();
        int submitErr = 0;
        long maxSubmitNs = 0;
        for (int i = 0; i < T; i++)
        {
            final byte[] pre = variant.equals("B") ? new byte[MIB] : null;
            if (pre != null) allocatedMiB.incrementAndGet();
            long s = System.nanoTime();
            try
            {
                ex.execute(() -> {
                    byte[] b = pre != null ? pre : new byte[MIB];
                    if (pre == null) allocatedMiB.incrementAndGet();
                    registry.add(b);
                    running.incrementAndGet();
                    try { gate.await(); } catch (InterruptedException e) { }
                    registry.remove(b);
                    done.incrementAndGet();
                });
            }
            catch (Throwable t) { submitErr++; }
            maxSubmitNs = Math.max(maxSubmitNs, System.nanoTime() - s);
        }
        long submitMs = (System.nanoTime() - ts) / 1_000_000;
        sleep(2000);
        int active = ex.getActiveTaskCount(), pending = ex.getPendingTaskCount(), maxPool = ex.getMaximumPoolSize();
        int th1 = ManagementFactory.getThreadMXBean().getThreadCount();
        int poolTh = poolThreads("probe");
        long regMiB = registry.size();
        long heap = heapUsed();
        long nmt1 = nmtThreadCommittedKB();
        System.out.println(String.format("PROBE %s n=%d T=%d label=%s maxPool=%d active=%d pending=%d running=%d registryMiB=%d allocatedMiB=%d heapDeltaMiB=%.1f threads=%d threadsDelta=%d poolThreads=%d nmtThreadDeltaKB=%d submitErr=%d submitMs=%d maxSubmitUs=%d",
                                         variant, n, T, label, maxPool, active, pending, running.get(), regMiB, allocatedMiB.get(),
                                         (heap - base) / (double) MIB, th1, th1 - th0, poolTh, (nmt1 < 0 || nmt0 < 0) ? -1 : nmt1 - nmt0, submitErr, submitMs, maxSubmitNs / 1000));
        gate.countDown();
        long t0 = System.currentTimeMillis();
        while (done.get() < T && System.currentTimeMillis() - t0 < 120_000) sleep(50);
        System.out.println(String.format("PROBE-DONE %s n=%d completed=%d", variant, n, done.get()));
        pool.shutdownAndWait(1, TimeUnit.MINUTES);
        registry.clear();
    }

    static void control(int n, int T) throws Exception
    {
        registry.clear(); allocatedMiB.set(0);
        long base = heapUsed();
        CountDownLatch gate = new CountDownLatch(1);
        ThreadPoolExecutor tpe = new ThreadPoolExecutor(n, n, 0, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(64), new ThreadPoolExecutor.AbortPolicy());
        int accepted = 0, rejected = 0;
        for (int i = 0; i < T; i++)
        {
            final byte[] pre = new byte[MIB];
            try
            {
                tpe.execute(() -> { registry.add(pre); try { gate.await(); } catch (InterruptedException e) { } });
                accepted++;
            }
            catch (RejectedExecutionException e) { rejected++; }
        }
        sleep(2000);
        int queued = tpe.getQueue().size(), active = tpe.getActiveCount();
        long heap = heapUsed();
        System.out.println(String.format("CTRL n=%d T=%d accepted=%d rejected=%d queue=%d active=%d heapDeltaMiB=%.1f", n, T, accepted, rejected, queued, active, (heap - base) / (double) MIB));
        gate.countDown();
        tpe.shutdown(); tpe.awaitTermination(1, TimeUnit.MINUTES);
        registry.clear();
    }

    static void resize() throws Exception
    {
        Logger lg = (Logger) LoggerFactory.getLogger(SEPExecutor.class);
        lg.setLevel(Level.INFO);
        ListAppender<ILoggingEvent> app = new ListAppender<>();
        app.start();
        lg.addAppender(app);
        AtomicInteger listener = new AtomicInteger();
        SharedExecutorPool pool = new SharedExecutorPool("probe");
        LocalAwareExecutorPlus ex = pool.newExecutor(4, (ExecutorPlus.MaximumPoolSizeListener) i -> listener.incrementAndGet(), "internal", "probe");
        Semaphore sem = new Semaphore(0);
        AtomicInteger started = new AtomicInteger(), finished = new AtomicInteger();
        for (int i = 0; i < 600; i++)
            ex.execute(() -> { started.incrementAndGet(); sem.acquireUninterruptibly(); finished.incrementAndGet(); });
        step("initial n=4", ex, listener, app, started, finished);
        ex.setMaximumPoolSize(32); sleep(2000); step("set 4->32", ex, listener, app, started, finished);
        ex.setMaximumPoolSize(32); sleep(1000); step("set 32->32 (line 384 no-op)", ex, listener, app, started, finished);
        ex.setMaximumPoolSize(32); sleep(1000); step("set 32->32 again", ex, listener, app, started, finished);
        ex.setMaximumPoolSize(8); sleep(1000); step("set 32->8 (32 tasks running)", ex, listener, app, started, finished);
        sem.release(4); sleep(1500); step("released 4 tasks", ex, listener, app, started, finished);
        sem.release(20); sleep(1500); step("released 24 tasks in total", ex, listener, app, started, finished);
        sem.release(2); sleep(1500); step("released 26 tasks in total", ex, listener, app, started, finished);
        sem.release(100000);
        long t0 = System.currentTimeMillis();
        while (finished.get() < 600 && System.currentTimeMillis() - t0 < 60000) sleep(50);
        System.out.println("RESIZE finished=" + finished.get());
        pool.shutdownAndWait(1, TimeUnit.MINUTES);
    }

    static void step(String what, LocalAwareExecutorPlus ex, AtomicInteger listener, ListAppender<ILoggingEvent> app, AtomicInteger started, AtomicInteger finished)
    {
        int resized = 0;
        StringBuilder sb = new StringBuilder();
        for (ILoggingEvent e : new java.util.ArrayList<>(app.list))
            if (e.getFormattedMessage().startsWith("Resized"))
            {
                resized++;
                sb.append(e.getFormattedMessage().replace(' ', '_')).append(';');
            }
        System.out.println(String.format("RESIZE step=[%s] maxPool=%d active=%d pending=%d started=%d finished=%d listenerCalls=%d resizedLogLines=%d lines=%s",
                                         what, ex.getMaximumPoolSize(), ex.getActiveTaskCount(), ex.getPendingTaskCount(), started.get(), finished.get(), listener.get(), resized, sb));
    }

    public static void main(String[] a) throws Exception
    {
        String label = a.length > 0 ? a[0] : "rep";
        ((Logger) LoggerFactory.getLogger(Logger.ROOT_LOGGER_NAME)).setLevel(Level.WARN);
        System.out.println("PROBE-ENV label=" + label + " maxHeapMiB=" + Runtime.getRuntime().maxMemory() / MIB + " jvm=" + ManagementFactory.getRuntimeMXBean().getInputArguments());
        int[] ns = { 1, 4, 32, 128 };
        for (int n : ns) sepRun("A", n, 2000, label);
        for (int n : ns) sepRun("B", n, 600, label);
        for (int n : new int[] { 4, 32, 128 }) control(n, 600);
        resize();
        System.out.println("PROBE-END label=" + label);
        System.exit(0);
    }
}
