/*
 * Stage-4 harness, unit tier of column_index_cache_size-indexSamples-cacheSizeThreshold (case file section 9, 9e unit step 2 as amended
 * 2026-10-14). Not part of upstream Cassandra. Copy into test/unit/org/apache/cassandra/io/sstable/format/big/ of a local clone at
 * cassandra-5.0.9. System property stage4.out: a file that also receives the STAGE4 lines.
 *
 * Builds one partition of n blocks with the real BigFormatPartitionWriter (the convenience constructor, which reads
 * column_index_cache_size once, BigFormatPartitionWriter.java:73), one block per row (rows carry 1,024 value bytes and
 * column_index_size is 1 KiB), creates the entry with RowIndexEntry.create() as BigTableWriter does, serializes it, and
 * deserializes it at each read-time threshold (RowIndexEntry.java:360). Every assertion is a STAGE4 check line; a mismatch is
 * recorded and the test goes on, and fails at the end.
 */
package org.apache.cassandra.io.sstable.format.big;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.junit.Assert;
import org.junit.Assume;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.Util;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.statements.schema.CreateTableStatement;
import org.apache.cassandra.db.BufferDecoratedKey;
import org.apache.cassandra.db.Clustering;
import org.apache.cassandra.db.ClusteringComparator;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.DeletionTime;
import org.apache.cassandra.db.LivenessInfo;
import org.apache.cassandra.db.SerializationHeader;
import org.apache.cassandra.db.TypeSizes;
import org.apache.cassandra.db.marshal.AbstractType;
import org.apache.cassandra.db.marshal.LongType;
import org.apache.cassandra.db.rows.BTreeRow;
import org.apache.cassandra.db.rows.BufferCell;
import org.apache.cassandra.db.rows.ColumnData;
import org.apache.cassandra.db.rows.EncodingStats;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.sstable.IndexInfo;
import org.apache.cassandra.io.sstable.format.Version;
import org.apache.cassandra.io.util.DataInputBuffer;
import org.apache.cassandra.io.util.DataOutputBuffer;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileUtils;
import org.apache.cassandra.io.util.SequentialWriter;
import org.apache.cassandra.io.util.SequentialWriterOption;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.serializers.LongSerializer;
import org.apache.cassandra.utils.ObjectSizes;
import org.apache.cassandra.utils.btree.BTree;

public class ColumnIndexThresholdTest extends CQLTester
{
    static final List<AbstractType<?>> CLUSTER_TYPES = Collections.singletonList(LongType.instance);
    static final ClusteringComparator COMP = new ClusteringComparator(CLUSTER_TYPES);
    static final int[] NS = { 2, 10, 34, 270, 2200, 18000 };
    static final int[] TS_KIB = { 0, 2, 16, 256 };
    static final int BOUNDARY_KIB = 2;
    static final int ROW_VALUE_BYTES = 1024;

    static PrintWriter out;
    static int mismatches = 0, checks = 0;

    static TableMetadata metadata;
    static SerializationHeader header;
    static Version version;
    static RowIndexEntry.IndexSerializer ser;

    static void line(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    static void check(String name, Object expected, Object actual)
    {
        checks++;
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    @BeforeClass
    public static void setup() throws Exception
    {
        Assume.assumeTrue(BigFormat.isSelected());
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        metadata = CreateTableStatement.parse("CREATE TABLE pipe.cics (pk bigint, ck bigint, v blob, PRIMARY KEY(pk, ck))", "pipe").build();
        header = new SerializationHeader(true, metadata, metadata.regularAndStaticColumns(), EncodingStats.NO_STATS);
        version = BigFormat.getInstance().getLatestVersion();
        ser = new RowIndexEntry.Serializer(version, header, null);
        DatabaseDescriptor.setColumnIndexSizeInKiB(1);
        line("STAGE4 info jvm " + System.getProperty("java.version") + " version " + version + " column_index_size " + DatabaseDescriptor.getColumnIndexSize(-1)
             + " storage_compatibility " + DatabaseDescriptor.getStorageCompatibilityMode());
    }

    static class Built
    {
        int n, tw, blocks, S, size, h, hFormula, bufCapacity = -1;
        long headerLength;
        boolean samplesNull, bufferNull;
        RowIndexEntry entry;
        ByteBuffer serialized;
    }

    static Row row(long ck)
    {
        BTree.Builder<ColumnData> b = BTree.builder(ColumnData.comparator);
        b.add(BufferCell.live(metadata.regularAndStaticColumns().iterator().next(), 1L, ByteBuffer.allocate(ROW_VALUE_BYTES)));
        return BTreeRow.create(Util.clustering(COMP, ck), LivenessInfo.EMPTY, Row.Deletion.LIVE, b.build());
    }

    static DecoratedKey key(long l)
    {
        ByteBuffer k = LongSerializer.instance.serialize(l);
        return new BufferDecoratedKey(Murmur3Partitioner.instance.getToken(k), k);
    }

    /** Builds a partition of n rows (one block each) with the write-time threshold twKiB; nothing is asserted here. */
    static Built build(int n, int twKiB) throws Exception
    {
        DatabaseDescriptor.setColumnIndexCacheSize(twKiB);
        Built r = new Built();
        r.n = n; r.tw = twKiB * 1024;
        File f = FileUtils.createTempFile("ColumnIndexThresholdTest-", "db");
        try (SequentialWriter w = new SequentialWriter(f, SequentialWriterOption.newBuilder().bufferSize(65536).build()))
        {
            BigFormatPartitionWriter pw = new BigFormatPartitionWriter(header, w, version, ser.indexInfoSerializer());
            pw.start(key(42L), DeletionTime.LIVE);
            for (int i = 0; i < n; i++)
                pw.addUnfiltered(row(i));
            pw.finish();
            r.blocks = pw.getColumnIndexCount();
            r.S = pw.indexInfoSerializedSize();
            List<IndexInfo> samples = pw.indexSamples();
            r.samplesNull = samples == null;
            ByteBuffer buf = pw.buffer();
            r.bufferNull = buf == null;
            if (buf != null) r.bufCapacity = buf.capacity();
            r.headerLength = pw.getHeaderLength();
            r.entry = RowIndexEntry.create(0L, 0L, DeletionTime.LIVE, pw.getHeaderLength(), pw.getColumnIndexCount(), pw.indexInfoSerializedSize(),
                                           samples, pw.offsets(), ser.indexInfoSerializer(), version);
            DataOutputBuffer o = new DataOutputBuffer();
            ser.serialize(r.entry, o, buf);
            r.serialized = o.buffer();
        }
        finally
        {
            f.tryDelete();
        }
        // parse the serialized header: position, size, headerLength, deletion time, count (RowIndexEntry.java:343-354)
        DataInputBuffer in = new DataInputBuffer(r.serialized.duplicate(), false);
        in.readUnsignedVInt();
        r.size = in.readUnsignedVInt32();
        long hl = in.readUnsignedVInt();
        DeletionTime dt = DeletionTime.getSerializer(version).deserialize(in);
        int count = in.readUnsignedVInt32();
        r.h = r.size - r.S;
        r.hFormula = TypeSizes.sizeofUnsignedVInt(hl) + (int) DeletionTime.getSerializer(version).serializedSize(dt) + TypeSizes.sizeofUnsignedVInt(count);
        return r;
    }

    static RowIndexEntry readBack(Built b, int trKiB) throws Exception
    {
        DatabaseDescriptor.setColumnIndexCacheSize(trKiB);
        check("tr_effective_" + trKiB, trKiB * 1024, DatabaseDescriptor.getColumnIndexCacheSize());
        return ser.deserialize(new DataInputBuffer(b.serialized.duplicate(), false), 0L);
    }

    static String cls(Object e) { return e.getClass().getSimpleName(); }

    @Test
    public void sweep() throws Exception
    {
        Map<Integer, Integer> sByN = new TreeMap<>();
        Map<Integer, Long> wIndexedRead = new TreeMap<>();
        List<Long> shallowWeights = new ArrayList<>();
        for (int n : NS)
        {
            for (int twKiB : TS_KIB)
            {
                Built b = build(n, twKiB);
                String id = "n" + n + "_tw" + twKiB;
                check(id + "_blocks", n, b.blocks);
                if (sByN.containsKey(n)) check(id + "_S_same_for_every_tw", sByN.get(n), b.S);
                else sByN.put(n, b.S);
                check(id + "_h_is_formula", b.hFormula, b.h);
                boolean expectIndexed = b.S <= b.tw && n > 1;
                check(id + "_write_class", expectIndexed ? "IndexedEntry" : "ShallowIndexedEntry", cls(b.entry));
                check(id + "_indexSamples_null_iff_S_gt_T", b.S > b.tw, b.samplesNull);
                check(id + "_buffer_allocated_iff_S_gt_T", b.S > b.tw, !b.bufferNull);
                if (!b.bufferNull)
                {
                    if (b.S <= 2 * b.tw) check(id + "_buffer_capacity_2T", 2 * b.tw, b.bufCapacity);
                    else check(id + "_buffer_capacity_ge_S", true, b.bufCapacity >= b.S);
                }
                long ww = b.entry.unsharedHeapSize();
                if (!expectIndexed) shallowWeights.add(ww);
                line("STAGE4 row n=" + n + " tw=" + b.tw + " S=" + b.S + " h=" + b.h + " size=" + b.size + " headerLength=" + b.headerLength
                     + " write_class=" + cls(b.entry) + " write_weight=" + ww + " buffer_capacity=" + b.bufCapacity
                     + " offsets_unmetered=" + ObjectSizes.sizeOfArray(new int[n]));
                for (int trKiB : TS_KIB)
                {
                    RowIndexEntry e = readBack(b, trKiB);
                    String rid = id + "_tr" + trKiB;
                    boolean readIndexed = b.size <= trKiB * 1024;
                    check(rid + "_read_class", readIndexed ? "IndexedEntry" : "ShallowIndexedEntry", cls(e));
                    check(rid + "_read_blocks", n, e.blockCount());
                    long rw = e.unsharedHeapSize();
                    if (readIndexed) wIndexedRead.put(n, rw); else shallowWeights.add(rw);
                    line("STAGE4 read n=" + n + " tw=" + b.tw + " tr=" + trKiB * 1024 + " size=" + b.size + " read_class=" + cls(e) + " read_weight=" + rw);
                }
            }
        }

        // weights: shallow constant for every n, threshold and path; indexed (read path) linear in n
        check("shallow_weight_constant", 1L, shallowWeights.stream().distinct().count());
        line("STAGE4 info shallow_weight " + shallowWeights.get(0) + " over " + shallowWeights.size() + " entries");
        List<Integer> ns = new ArrayList<>(wIndexedRead.keySet());
        double slope = (wIndexedRead.get(ns.get(ns.size() - 1)) - wIndexedRead.get(ns.get(0))) / (double) (ns.get(ns.size() - 1) - ns.get(0));
        for (int i = 1; i < ns.size(); i++)
        {
            double s = (wIndexedRead.get(ns.get(i)) - wIndexedRead.get(ns.get(i - 1))) / (double) (ns.get(i) - ns.get(i - 1));
            check("indexed_weight_linear_n" + ns.get(i - 1) + "_n" + ns.get(i), true, Math.abs(s - slope) <= 1.0);
            line("STAGE4 info indexed_weight_slope n" + ns.get(i - 1) + "-n" + ns.get(i) + " " + s + " (overall " + slope + ")");
        }
        line("STAGE4 info indexed_read_weights " + wIndexedRead);

        // boundary at 2 KiB: both flip points, every n from 50 to 90
        int t = BOUNDARY_KIB * 1024, nw = -1, nr = -1, lo = 50, hi = 90;
        List<Built> bs = new ArrayList<>();
        for (int n = lo; n <= hi; n++)
        {
            Built b = build(n, BOUNDARY_KIB);
            bs.add(b);
            if (b.S <= t) nw = n;
            if (b.size <= t) nr = n;
        }
        line("STAGE4 info boundary T=" + t + " nw=" + nw + " nr=" + nr);
        check("boundary_nw_inside_range", true, nw > lo && nw < hi);
        check("boundary_nr_inside_range", true, nr > lo && nr < hi);
        check("boundary_nr_le_nw", true, nr <= nw);
        for (Built b : bs)
        {
            RowIndexEntry e = readBack(b, BOUNDARY_KIB);
            check("boundary_n" + b.n + "_write_class", b.n <= nw ? "IndexedEntry" : "ShallowIndexedEntry", cls(b.entry));
            check("boundary_n" + b.n + "_read_class", b.n <= nr ? "IndexedEntry" : "ShallowIndexedEntry", cls(e));
            line("STAGE4 boundary n=" + b.n + " S=" + b.S + " h=" + b.h + " size=" + b.size + " write_class=" + cls(b.entry) + " read_class=" + cls(e));
        }
        DatabaseDescriptor.setColumnIndexCacheSize(2);
        line("STAGE4 done checks " + checks + " mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }
}
