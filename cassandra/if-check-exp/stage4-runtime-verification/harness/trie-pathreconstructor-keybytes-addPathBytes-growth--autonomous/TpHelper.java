package org.stage4;

// Byteman rule helper (B3i.6). Loaded on the boot class path. Logs one line per growth of TriePathReconstructor.keyBytes
// (site 34 = addPathByte doubling, site 42 = addPathBytes), counts reconstructors by class and the per-entry copies of toByteComparable,
// and dumps the counters to a file every 2 s. The phase tag is read from the file named by -Dstage4.tp.phase on each growth event.
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class TpHelper
{
    static final ConcurrentHashMap<String, LongAdder> ctors = new ConcurrentHashMap<>();
    static final LongAdder copies = new LongAdder(), copyBytes = new LongAdder();
    static final AtomicLong seq = new AtomicLong();
    static final String statsFile = System.getProperty("stage4.tp.stats", "/tmp/tp-stats.txt");
    static final String eventsFile = System.getProperty("stage4.tp.events", "/tmp/tp-events.txt");
    static final String phaseFile = System.getProperty("stage4.tp.phase", "/tmp/tp-phase.txt");
    static PrintWriter events;
    static
    {
        try { events = new PrintWriter(new FileWriter(eventsFile, true), true); } catch (Exception e) { events = null; }
        Thread th = new Thread(() -> {
            while (true)
            {
                try { Thread.sleep(2000); dump(); } catch (Throwable t) { }
            }
        }, "tp-stats-dump");
        th.setDaemon(true);
        th.start();
    }

    static String phase()
    {
        try { return new String(Files.readAllBytes(Paths.get(phaseFile))).trim(); } catch (Throwable t) { return "?"; }
    }

    /** site 34: new capacity = need*2 (need = keyPos). site 42: new capacity = max(need+16, old*2) (need = keyPos + count). */
    public static void grow(int site, Object recv, int oldCap, int need)
    {
        long newCap = site == 34 ? (long) need * 2 : Math.max((long) need + 16, (long) oldCap * 2);
        long n = seq.incrementAndGet();
        if (events != null)
            events.println(n + "," + System.currentTimeMillis() + "," + phase() + "," + site + "," + recv.getClass().getSimpleName() + "," + System.identityHashCode(recv) + "," + oldCap + "," + need + "," + newCap);
    }
    public static void ctor(String cls) { ctors.computeIfAbsent(cls, k -> new LongAdder()).increment(); }
    public static void copy(int len) { copies.increment(); copyBytes.add(len); }
    public static void init() { }
    static synchronized void dump()
    {
        StringBuilder sb = new StringBuilder("t=" + System.currentTimeMillis() + " events=" + seq.get() + " copies=" + copies.sum() + " copybytes=" + copyBytes.sum());
        for (Map.Entry<String, LongAdder> e : new TreeMap<>(ctors).entrySet())
            sb.append(" ctor.").append(e.getKey().replaceAll("^.*\\.", "")).append('=').append(e.getValue().sum());
        sb.append('\n');
        try (PrintWriter pw = new PrintWriter(new FileWriter(statsFile, false))) { pw.print(sb); } catch (Exception e) { }
    }
}
