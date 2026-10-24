/*
 * Stage-4 harness for commitlog_segment_size-allocate-endOfBuffer--autonomous (B2, as amended 2026-10-23, B2i).
 * Copy to <tree>/test/unit/org/apache/cassandra/db/commitlog/. The segment size, compression and access mode come from the
 * per-arm yaml (-Dcassandra.config); system properties:
 *   seg.out      output prefix (CSV, PROBE and SUMMARY lines go to <out>.csv and <out>.summary)
 *   seg.entry    exact total entry size E in bytes (serialized mutation + 12), default 65536
 *   seg.adds     number of main-workload adds; default ceil(3*S/E)+10
 *   seg.fill     random | zero (payload bytes)
 *   seg.edge     true: run the B2i.4 exact-edge probes
 * Observations are taken after every add on a single writer thread; a segment's capacity is read when it is first seen
 * (a closed segment's buffer is null), endOfBuffer / allocatePosition by reflection.
 */
package org.apache.cassandra.db.commitlog;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.io.RandomAccessFile;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.marshal.AsciiType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.net.MessagingService;

public class SegmentSizeCapTest
{
    static final String KS = "SegCap";
    static final int OVERHEAD = 12; // CommitLog.ENTRY_OVERHEAD_SIZE
    static final Field F_END, F_ALLOC, F_WRITTEN;
    static
    {
        try
        {
            F_END = CommitLogSegment.class.getDeclaredField("endOfBuffer"); F_END.setAccessible(true);
            F_ALLOC = CommitLogSegment.class.getDeclaredField("allocatePosition"); F_ALLOC.setAccessible(true);
            F_WRITTEN = FileDirectSegment.class.getDeclaredField("lastWrittenPos"); F_WRITTEN.setAccessible(true);
        }
        catch (Exception e) { throw new RuntimeException(e); }
    }

    static int endOf(CommitLogSegment s) throws Exception { return F_END.getInt(s); }
    static int allocOf(CommitLogSegment s) throws Exception { return ((AtomicInteger) F_ALLOC.get(s)).get(); }

    static class Rec
    {
        long id; int capacity = -1; int endAtFirst; long headerLen = -1; int adds; int maxEnd = -1; long bytes; CommitLogSegment seg;
    }

    final Map<Long, Rec> recs = new LinkedHashMap<>();
    PrintWriter sum;
    TableMetadata md;
    int violations = 0;
    final Random rnd = new Random(12345);
    boolean zero;

    void observe() throws Exception
    {
        for (CommitLogSegment s : new ArrayList<>(CommitLog.instance.segmentManager.getActiveSegments()))
        {
            if (recs.containsKey(s.id)) continue;
            Rec r = new Rec();
            r.id = s.id; r.seg = s;
            r.capacity = s.buffer == null ? -1 : s.buffer.capacity();
            r.endAtFirst = endOf(s);
            if (s instanceof FileDirectSegment && !(s instanceof DirectIOSegment)) r.headerLen = F_WRITTEN.getLong(s);
            recs.put(s.id, r);
        }
    }

    Mutation mutation(long i, int payload)
    {
        byte[] v = new byte[payload];
        if (!zero) { new Random(i).nextBytes(v); } else Arrays.fill(v, (byte) 7);
        return new RowUpdateBuilder(md, 0, String.format("k%010d", i)).clustering("c").add("val", ByteBuffer.wrap(v)).build();
    }

    int totalOf(Mutation m) { return m.serializedSize(MessagingService.current_version) + OVERHEAD; }

    /** Payload length whose entry total (serialized + 12) is exactly `total`. */
    int payloadFor(long i, int total)
    {
        int len = Math.max(1, total - 120);
        for (int k = 0; k < 20; k++)
        {
            int t = totalOf(mutation(i, len));
            if (t == total) return len;
            len += total - t;
        }
        throw new AssertionError("no exact payload for total " + total);
    }

    long nextKey = 0;

    CommitLogPosition add(int payload) throws Exception
    {
        Mutation m = mutation(nextKey++, payload);
        int total = totalOf(m);
        CommitLogPosition p = CommitLog.instance.add(m);
        observe();
        Rec r = recs.get(p.segmentId);
        if (r == null) throw new AssertionError("unseen segment " + p.segmentId);
        r.adds++; r.bytes += total; r.maxEnd = Math.max(r.maxEnd, p.position);
        if (r.capacity >= 0 && p.position >= r.capacity) violations++;
        return p;
    }

    void probe(String s) { System.out.println("PROBE " + s); sum.println("PROBE " + s); sum.flush(); }

    /** Add E-sized entries until the allocating segment has remaining <= limit; returns the allocating segment. */
    CommitLogSegment fillTo(int limit, int payload) throws Exception
    {
        while (true)
        {
            CommitLogSegment s = CommitLog.instance.segmentManager.allocatingFrom();
            Rec r = recs.get(s.id);
            int remaining = r.capacity - allocOf(s);
            if (remaining <= limit) return s;
            add(payload);
        }
    }

    long rollTo() throws Exception
    {
        long id = CommitLog.instance.segmentManager.allocatingFrom().id;
        int payload = payloadFor(nextKey, Integer.getInteger("seg.entry", 65536));
        while (CommitLog.instance.segmentManager.allocatingFrom().id == id) add(payload);
        return CommitLog.instance.segmentManager.allocatingFrom().id;
    }

    @Test
    public void segmentCap() throws Throwable
    {
        String out = System.getProperty("seg.out", "build/test/segcap");
        zero = "zero".equals(System.getProperty("seg.fill", "random"));
        boolean edge = Boolean.getBoolean("seg.edge");
        DatabaseDescriptor.daemonInitialization();
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KS, "T", 0, AsciiType.instance, BytesType.instance));
        md = org.apache.cassandra.db.Keyspace.open(KS).getColumnFamilyStore("T").metadata();
        sum = new PrintWriter(new FileWriter(out + ".summary", true));
        long S = DatabaseDescriptor.getCommitLogSegmentSize();
        int maxMut = DatabaseDescriptor.getMaxMutationSize();
        int E = Integer.getInteger("seg.entry", 65536);
        int adds = Integer.getInteger("seg.adds", (int) (3 * S + E - 1) / E + 10);
        String info = "INFO S=" + S + " maxMutationSize=" + maxMut + " entry=" + E + " adds=" + adds + " fill=" + (zero ? "zero" : "random")
                      + " accessMode=" + DatabaseDescriptor.getCommitLogWriteDiskAccessMode()
                      + " compression=" + (DatabaseDescriptor.getCommitLogCompression() == null ? "none" : DatabaseDescriptor.getCommitLogCompression().class_name)
                      + " segments0=" + CommitLog.instance.segmentManager.getActiveSegments().size()
                      + " memtableHeapMiB=" + DatabaseDescriptor.getMemtableHeapSpaceInMiB();
        System.out.println(info); sum.println(info);
        observe();

        // --- main workload (B2c)
        int payload = payloadFor(nextKey, E);
        for (int i = 0; i < adds; i++) add(payload);
        probe("main adds=" + adds + " payload=" + payload + " entryTotal=" + totalOf(mutation(0, payload)));

        // --- max / oversize probes (B2c): in a fresh segment
        rollTo();
        int maxPayload = payloadFor(nextKey, maxMut);
        long before = CommitLog.instance.metrics.oversizedMutations.getCount();
        CommitLogPosition pm = add(maxPayload);
        probe("max-accepted total=" + maxMut + " seg=" + pm.segmentId + " end=" + pm.position);
        int bigPayload = maxPayload + 1;
        CommitLog.instance.sync(true);
        CommitLogSegment af = CommitLog.instance.segmentManager.allocatingFrom();
        int allocBefore = allocOf(af);
        String exc = "none";
        try { CommitLog.instance.add(mutation(nextKey++, bigPayload)); }
        catch (Throwable t) { exc = t.getClass().getSimpleName(); }
        long after = CommitLog.instance.metrics.oversizedMutations.getCount();
        probe("oversize total=" + (maxMut + 1) + " exception=" + exc + " oversizedMutations+" + (after - before)
              + " allocatePositionDelta=" + (allocOf(af) - allocBefore) + " sameSegment=" + (af == CommitLog.instance.segmentManager.allocatingFrom()));

        if (edge)
        {
            // --- (a) next == capacity-1 stays
            rollTo();
            CommitLogSegment sa = fillTo((int) (S / 2), payload);
            CommitLog.instance.sync(true);
            Rec ra = recs.get(sa.id);
            int posA = allocOf(sa), remA = ra.capacity - posA;
            int pl = payloadFor(nextKey, remA - 1);
            CommitLogPosition p = add(pl);
            probe("edge-a seg=" + sa.id + " capacity=" + ra.capacity + " posBefore=" + posA + " remaining=" + remA + " entryTotal=" + (remA - 1)
                  + " returnedSeg=" + p.segmentId + " returnedEnd=" + p.position + " allocPosAfter=" + allocOf(sa) + " stayed=" + (p.segmentId == sa.id));
            // --- (b) next == capacity rolls
            rollTo();
            CommitLogSegment sb = fillTo((int) (S / 2), payload);
            CommitLog.instance.sync(true);
            Rec rb = recs.get(sb.id);
            int posB = allocOf(sb), remB = rb.capacity - posB;
            int plb = payloadFor(nextKey, remB);
            CommitLogPosition q = add(plb);
            probe("edge-b seg=" + sb.id + " capacity=" + rb.capacity + " posBefore=" + posB + " remaining=" + remB + " entryTotal=" + remB
                  + " returnedSeg=" + q.segmentId + " returnedEnd=" + q.position + " oldEndOfBuffer=" + endOf(sb) + " oldAllocPos=" + allocOf(sb)
                  + " rolled=" + (q.segmentId != sb.id));
        }

        CommitLog.instance.sync(true);
        Thread.sleep(500);
        CommitLog.instance.sync(true);

        // --- per-segment census
        try (PrintWriter csv = new PrintWriter(new FileWriter(out + ".csv", true)))
        {
            csv.println("id,capacity,maxEnd,endOfBuffer,allocatePosition,stillAllocating,fileLength,onDiskSize,blocks,adds,bytes");
            for (Rec r : recs.values())
            {
                CommitLogSegment s = r.seg;
                long len = new java.io.File(s.getPath()).length();
                int blocks = -1;
                if (r.headerLen >= 0)
                {
                    blocks = 0;
                    try (RandomAccessFile f = new RandomAccessFile(s.getPath(), "r"))
                    {
                        long pos = r.headerLen;
                        while (pos + 12 <= len)
                        {
                            f.seek(pos);
                            int next = f.readInt();
                            blocks++;
                            if (next <= pos) break;
                            pos = next;
                        }
                    }
                }
                csv.println(r.id + "," + r.capacity + "," + r.maxEnd + "," + endOf(s) + "," + allocOf(s) + "," + s.isStillAllocating() + ","
                            + len + "," + s.onDiskSize() + "," + blocks + "," + r.adds + "," + r.bytes);
            }
        }
        String summary = "SUMMARY S=" + S + " segments=" + recs.size() + " violations=" + violations + " oversized=" + CommitLog.instance.metrics.oversizedMutations.getCount();
        System.out.println(summary); sum.println(summary); sum.close();
    }
}
