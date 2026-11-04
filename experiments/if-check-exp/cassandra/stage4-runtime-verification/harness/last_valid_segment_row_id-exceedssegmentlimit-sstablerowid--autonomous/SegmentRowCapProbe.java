package org.apache.cassandra.index.sai.disk.v1;

import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import com.google.common.base.Stopwatch;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Clustering;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.db.rows.BTreeRow;
import org.apache.cassandra.db.rows.BufferCell;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.index.sai.SAITester;
import org.apache.cassandra.index.sai.StorageAttachedIndex;
import org.apache.cassandra.index.sai.disk.format.IndexDescriptor;
import org.apache.cassandra.index.sai.disk.v1.segment.SegmentBuilder;
import org.apache.cassandra.index.sai.disk.v1.segment.SegmentMetadata;
import org.apache.cassandra.index.sai.utils.NamedMemoryLimiter;
import org.apache.cassandra.io.sstable.Descriptor;
import org.apache.cassandra.io.sstable.SequenceBasedSSTableId;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.ColumnMetadata;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.utils.ByteBufferUtil;

/**
 * Stage-4 unit probe for last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous (B2), set-up copied from SegmentFlushTest.
 * usage: SegmentRowCapProbe grid  <cap|-1> <limitMiB> <N> <S>     N rows with ids 0..N-1, S-byte distinct UTF8 terms, own NamedMemoryLimiter(limitMiB)
 *        SegmentRowCapProbe pair  <cap|-1> <id1> <id2>            two rows at the given sstable row ids (1 MiB-free limiter 1024 MiB)
 * Prints STAGE4 lines. Temp index files under -Dprobe.tmp (default java.io.tmpdir), deleted at the end.
 */
public class SegmentRowCapProbe
{
    static Row row(ColumnMetadata column, ByteBuffer value)
    {
        Row.Builder b = BTreeRow.sortedBuilder();
        b.newRow(Clustering.EMPTY);
        b.addCell(BufferCell.live(column, 0, value));
        return b.build();
    }

    static void rmrf(java.io.File f)
    {
        java.io.File[] k = f.listFiles();
        if (k != null) for (java.io.File c : k) rmrf(c);
        f.delete();
    }

    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.toolInitialization();
        DatabaseDescriptor.setPartitionerUnsafe(Murmur3Partitioner.instance);
        StorageService.instance.setPartitionerUnsafe(Murmur3Partitioner.instance);

        String mode = a[0];
        long cap = Long.parseLong(a[1]);
        SegmentBuilder.updateLastValidSegmentRowId(cap);
        long limitMiB = mode.equals("grid") ? Long.parseLong(a[2]) : 1024;
        NamedMemoryLimiter limiter = new NamedMemoryLimiter(limitMiB * 1024 * 1024, "probe");

        Path base = Files.createTempDirectory(java.nio.file.Paths.get(System.getProperty("probe.tmp", System.getProperty("java.io.tmpdir"))), "s4-b3-");
        IndexDescriptor id = IndexDescriptor.create(new Descriptor(new File(base.toFile()), "ks", "cf", new SequenceBasedSSTableId(1)),
                                                    Murmur3Partitioner.instance, SAITester.EMPTY_COMPARATOR);
        ColumnMetadata column = ColumnMetadata.regularColumn("sai", "internal", "column", UTF8Type.instance);
        StorageAttachedIndex index = SAITester.createMockIndex(column);
        SSTableIndexWriter writer = new SSTableIndexWriter(id, index, limiter, () -> true);

        long peak = 0;
        long n;
        long t0 = System.nanoTime();
        if (mode.equals("grid"))
        {
            n = Long.parseLong(a[3]);
            int s = Integer.parseInt(a[4]);
            List<DecoratedKey> keys = new ArrayList<>();
            for (long i = 0; i < n; i++)
                keys.add(Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes("key" + i)));
            Collections.sort(keys);
            char[] pad = new char[s];
            java.util.Arrays.fill(pad, 'x');
            for (long i = 0; i < n; i++)
            {
                String head = Long.toString(i, 36);
                String t = new String(pad, 0, s - head.length()) + head; // distinct, S bytes, differing in the last bytes
                writer.addRow(SAITester.TEST_FACTORY.create(keys.get((int) i)), row(column, UTF8Type.instance.decompose(t)), i);
                peak = Math.max(peak, limiter.currentBytesUsed());
            }
        }
        else
        {
            n = 2;
            long id1 = Long.parseLong(a[2]), id2 = Long.parseLong(a[3]);
            List<DecoratedKey> keys = new ArrayList<>(List.of(Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes("1")), Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes("2"))));
            Collections.sort(keys);
            writer.addRow(SAITester.TEST_FACTORY.create(keys.get(0)), row(column, UTF8Type.instance.decompose("a")), id1);
            peak = Math.max(peak, limiter.currentBytesUsed());
            writer.addRow(SAITester.TEST_FACTORY.create(keys.get(1)), row(column, UTF8Type.instance.decompose("b")), id2);
            peak = Math.max(peak, limiter.currentBytesUsed());
        }
        peak = Math.max(peak, limiter.currentBytesUsed());
        writer.complete(Stopwatch.createStarted());
        long ms = (System.nanoTime() - t0) / 1_000_000;

        org.apache.cassandra.index.sai.disk.v1.MetadataSource source = MetadataSource.loadColumnMetadata(id, index.identifier());
        List<SegmentMetadata> segs = SegmentMetadata.load(source, id.primaryKeyFactory);
        long min = Long.MAX_VALUE, max = 0, sum = 0;
        for (SegmentMetadata m : segs) { min = Math.min(min, m.numRows); max = Math.max(max, m.numRows); sum += m.numRows; }
        StringBuilder offs = new StringBuilder();
        for (int i = 0; i < Math.min(3, segs.size()); i++) offs.append(segs.get(i).rowIdOffset).append('/').append(segs.get(i).numRows).append(' ');
        SegmentMetadata last = segs.get(segs.size() - 1);
        System.out.printf("STAGE4 RESULT mode=%s cap=%d limitMiB=%d N=%d segments=%d rowsMin=%d rowsMax=%d rowsSum=%d lastRows=%d firstSegs=[%s] peakLimiterBytes=%d elapsedMs=%d%n",
                          mode, cap, limitMiB, n, segs.size(), min, max, sum, last.numRows, offs.toString().trim(), peak, ms);
        System.out.printf("STAGE4 LIMITER finalBytes=%d%n", limiter.currentBytesUsed());
        SegmentBuilder.updateLastValidSegmentRowId(-1);
        rmrf(base.toFile());
        System.exit(0);
    }
}
