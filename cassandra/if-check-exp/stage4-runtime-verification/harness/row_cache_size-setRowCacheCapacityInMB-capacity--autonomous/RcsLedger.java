import java.lang.management.ManagementFactory;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import javax.management.ObjectName;

import org.jboss.byteman.rule.Rule;
import org.jboss.byteman.rule.helper.Helper;

/**
 * Stage-4 harness, cluster tier of row_cache_size-setRowCacheCapacityInMB-capacity--autonomous, added for the cluster re-run
 * (case-file amendment 2026-10-27 (after run 1, authorised by the user) — B3d). Byteman helper of rcs-ledger.btm: an
 * observe-only ledger of the native blocks OHC allocates and frees through its own bookkeeping points
 * org.caffinitas.ohc.linked.Uns.allocated(address, bytes) and Uns.freed(address) (ohc-core 0.5.1, Uns.java:104-113 and :90-102,
 * called from Uns.allocate(long, boolean) :338-346 after a successful malloc and from Uns.free(long) :361-367 before the free).
 * Nothing it does changes OHC's arguments, results or control flow; every method catches all throwables.
 *
 * Per live block it keeps {requested bytes, malloc_size(address)}; malloc_size is the macOS allocator's own block size,
 * called through JNA (the library OHC itself allocates with). Blocks of >= 65,536 requested bytes are counted as "table"
 * blocks (OHC hash tables: 8 B x a power of two >= 8,192 per segment, OffHeapLinkedMap.java:82-88, :586-591), smaller ones
 * as "entry" blocks (cache entries, sentinels and transient copies). Read through the platform MBean server as
 * stage4:type=RcsLedger (attributes below), i.e. over Cassandra's JMX port.
 */
public class RcsLedger extends Helper
{
    public interface LedgerMBean
    {
        long getLiveBlocks();
        long getLiveBytes();
        long getLiveMalloc();
        long getEntryBlocks();
        long getEntryBytes();
        long getEntryMalloc();
        long getTableBlocks();
        long getTableBytes();
        long getTableMalloc();
        long getAllocs();
        long getFrees();
        long getUnknownFrees();
        long getDuplicateAllocs();
        long getMallocSizeErrors();
        long getEntryMaxBytes();
        String getHistogram();
    }

    static final long TABLE_MIN = 65536L;
    static final ConcurrentHashMap<Long, long[]> LIVE = new ConcurrentHashMap<>(1 << 20);
    static final ConcurrentHashMap<Long, AtomicLong> HIST = new ConcurrentHashMap<>();
    static final AtomicLong eB = new AtomicLong(), eN = new AtomicLong(), eM = new AtomicLong();
    static final AtomicLong tB = new AtomicLong(), tN = new AtomicLong(), tM = new AtomicLong();
    static final AtomicLong allocs = new AtomicLong(), frees = new AtomicLong(), unknown = new AtomicLong(), dup = new AtomicLong(), msErr = new AtomicLong();
    static final AtomicLong eMax = new AtomicLong();
    static volatile com.sun.jna.Function mallocSize;

    public static class Ledger implements LedgerMBean
    {
        public long getLiveBlocks() { return eN.get() + tN.get(); }
        public long getLiveBytes() { return eB.get() + tB.get(); }
        public long getLiveMalloc() { return eM.get() + tM.get(); }
        public long getEntryBlocks() { return eN.get(); }
        public long getEntryBytes() { return eB.get(); }
        public long getEntryMalloc() { return eM.get(); }
        public long getTableBlocks() { return tN.get(); }
        public long getTableBytes() { return tB.get(); }
        public long getTableMalloc() { return tM.get(); }
        public long getAllocs() { return allocs.get(); }
        public long getFrees() { return frees.get(); }
        public long getUnknownFrees() { return unknown.get(); }
        public long getDuplicateAllocs() { return dup.get(); }
        public long getMallocSizeErrors() { return msErr.get(); }
        public long getEntryMaxBytes() { return eMax.get(); }
        public String getHistogram()
        {
            // live blocks by requested size: "size:count;size:count;..."
            StringBuilder sb = new StringBuilder();
            for (Map.Entry<Long, AtomicLong> e : new TreeMap<>(HIST).entrySet())
                if (e.getValue().get() != 0)
                    sb.append(e.getKey()).append(':').append(e.getValue().get()).append(';');
            return sb.toString();
        }
    }

    static
    {
        try
        {
            mallocSize = com.sun.jna.NativeLibrary.getProcess().getFunction("malloc_size");
        }
        catch (Throwable t)
        {
            mallocSize = null;
        }
        try
        {
            ManagementFactory.getPlatformMBeanServer().registerMBean(new Ledger(), new ObjectName("stage4:type=RcsLedger"));
            System.out.println("RCSLEDGER registered stage4:type=RcsLedger malloc_size=" + (mallocSize != null));
        }
        catch (Throwable t)
        {
            System.out.println("RCSLEDGER register failed " + t);
        }
    }

    public RcsLedger(Rule rule)
    {
        super(rule);
    }

    static long msize(long address)
    {
        try
        {
            com.sun.jna.Function f = mallocSize;
            if (f == null)
            {
                msErr.incrementAndGet();
                return 0L;
            }
            return f.invokeLong(new Object[]{ new com.sun.jna.Pointer(address) });
        }
        catch (Throwable t)
        {
            msErr.incrementAndGet();
            return 0L;
        }
    }

    public void alloc(long address, long bytes)
    {
        try
        {
            long ms = msize(address);
            if (LIVE.putIfAbsent(address, new long[]{ bytes, ms }) != null)
            {
                dup.incrementAndGet();
                return;
            }
            allocs.incrementAndGet();
            if (bytes >= TABLE_MIN)
            {
                tB.addAndGet(bytes); tN.incrementAndGet(); tM.addAndGet(ms);
            }
            else
            {
                eB.addAndGet(bytes); eN.incrementAndGet(); eM.addAndGet(ms);
                long m;
                while (bytes > (m = eMax.get()) && !eMax.compareAndSet(m, bytes)) { }
            }
            HIST.computeIfAbsent(bytes, k -> new AtomicLong()).incrementAndGet();
        }
        catch (Throwable t)
        {
            msErr.incrementAndGet();
        }
    }

    public void free(long address)
    {
        try
        {
            long[] v = LIVE.remove(address);
            if (v == null)
            {
                unknown.incrementAndGet();
                return;
            }
            frees.incrementAndGet();
            if (v[0] >= TABLE_MIN)
            {
                tB.addAndGet(-v[0]); tN.decrementAndGet(); tM.addAndGet(-v[1]);
            }
            else
            {
                eB.addAndGet(-v[0]); eN.decrementAndGet(); eM.addAndGet(-v[1]);
            }
            AtomicLong h = HIST.get(v[0]);
            if (h != null)
                h.decrementAndGet();
        }
        catch (Throwable t)
        {
            msErr.incrementAndGet();
        }
    }
}
