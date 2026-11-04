package org.stage4;

// Byteman rule helper (B3i.5): histogram of array lengths at growth, cursor count, dumped to a file every 2 s. Loaded on the boot class path.
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class BtHelper
{
    static final ConcurrentHashMap<Integer, LongAdder> grow = new ConcurrentHashMap<>();
    static final AtomicLong cursors = new AtomicLong();
    static volatile String file;
    static
    {
        file = System.getProperty("stage4.bt.stats", "/tmp/bt-stats.txt");
        Thread th = new Thread(() -> {
            while (true)
            {
                try { Thread.sleep(2000); dump(); } catch (Throwable t) { }
            }
        }, "bt-stats-dump");
        th.setDaemon(true);
        th.start();
    }
    public static void grow(int oldLength) { grow.computeIfAbsent(oldLength, k -> new LongAdder()).increment(); }
    public static void cursor() { cursors.incrementAndGet(); }
    public static void init() { }   // called once at daemon start so that the stats file exists even when no cursor is ever created
    static synchronized void dump()
    {
        StringBuilder sb = new StringBuilder();
        sb.append("t=").append(System.currentTimeMillis()).append(" cursors=").append(cursors.get());
        for (java.util.Map.Entry<Integer, LongAdder> e : new java.util.TreeMap<>(grow).entrySet())
            sb.append(" grow").append(e.getKey()).append('=').append(e.getValue().sum());
        sb.append('\n');
        try (PrintWriter pw = new PrintWriter(new FileWriter(file, false))) { pw.print(sb); } catch (Exception e) { }
    }
}
