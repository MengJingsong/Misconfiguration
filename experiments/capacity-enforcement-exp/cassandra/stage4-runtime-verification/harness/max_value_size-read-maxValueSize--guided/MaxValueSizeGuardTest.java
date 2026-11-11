/*
 * Stage-4 harness, unit tier of max_value_size-read-maxValueSize (case file section 9, 9e unit step 1, amended 2026-10-13).
 * Not part of upstream Cassandra. Copy into test/unit/org/apache/cassandra/db/marshal/ of a local clone at cassandra-5.0.9.
 * System property stage4.out: a file that also receives the STAGE4 lines. The limits are set live with
 * DatabaseDescriptor.setMaxValueSize(); the range controls choose a yaml with -Dcassandra.config=file:///<path>.
 * Delta = bytes the calling thread allocates across one call (com.sun.management.ThreadMXBean), inputs built before it is read.
 * Records "check ... MISMATCH" and goes on; fails at the end if any check mismatched.
 */
package org.apache.cassandra.db.marshal;

import java.io.EOFException;
import java.io.FileWriter;
import java.io.IOError;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.Callable;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Clustering;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.ReadResponse;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.SinglePartitionReadCommand;
import org.apache.cassandra.db.filter.ColumnFilter;
import org.apache.cassandra.db.partitions.PartitionUpdate;
import org.apache.cassandra.db.partitions.SingletonUnfilteredPartitionIterator;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.rows.Cell;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.db.rows.Unfiltered;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.io.util.DataInputBuffer;
import org.apache.cassandra.io.util.DataOutputBuffer;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.ColumnMetadata;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.Schema;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.FBUtilities;

public class MaxValueSizeGuardTest
{
    private static final String KS = "MvsGuard";
    private static final String CF = "t";
    private static final int V = MessagingService.current_version;
    private static final long EPS = 65536;                       // 9c
    private static final long DEFAULT = 268435456L;              // 256 MiB
    private static final long[] LIMITS = { 1048576L, 4194304L, 8388608L, DEFAULT };

    private static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    private static PrintWriter out;
    private static int mismatches = 0;
    private static boolean record = true;
    private static int pk = 0;

    @BeforeClass
    public static void beforeClass() throws Exception
    {
        String o = System.getProperty("stage4.out");
        out = o == null ? null : new PrintWriter(new FileWriter(o, true), true);
        SchemaLoader.prepareServer();   // daemonInitialization(): the range controls stop here with a ConfigurationException
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    TableMetadata.builder(KS, CF)
                                                 .addPartitionKeyColumn("pk", Int32Type.instance)
                                                 .addRegularColumn("v", BytesType.instance));
    }

    // ------------------------------------------------------------------ output

    private static void line(String s)
    {
        System.out.println(s);
        if (out != null) out.println(s);
    }

    private static void check(String name, Object expected, Object actual)
    {
        if (!record) return;
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    private static void note(String name, Object value)
    {
        if (record) line("STAGE4 note " + name + " " + value);
    }

    // ------------------------------------------------------------------ measurement

    /** the outcome of one call: what it returned or threw, and the bytes the thread allocated across it */
    private static final class R
    {
        Object value;
        Throwable thrown;
        long delta;

        String type() { return thrown == null ? "returned" : thrown.getClass().getName(); }
        Throwable root() { Throwable t = thrown; while (t != null && t.getCause() != null) t = t.getCause(); return t; }
        String rootType() { return root() == null ? "none" : root().getClass().getName(); }
        String rootMessage() { return root() == null ? "" : String.valueOf(root().getMessage()); }
        public String toString() { return type() + (thrown == null ? "" : " root=" + rootType() + ": " + rootMessage()) + " delta=" + delta; }
    }

    private static long allocated()
    {
        return TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    private static R measure(Callable<Object> c)
    {
        R r = new R();
        long a0 = allocated();
        try { r.value = c.call(); }
        catch (Throwable t) { r.thrown = t; }
        r.delta = allocated() - a0;
        return r;
    }

    private static String guard(long l, long m)
    {
        return String.format("Corrupt value length %d encountered, as it exceeds the maximum of %d, which is set via max_value_size in cassandra.yaml", l, m);
    }

    /** "accepted" = the guard passed and the array was allocated: EOFException after delta >= size */
    private static void expectAllocated(String name, R r, long size)
    {
        note(name, r);
        check(name + ".type", EOFException.class.getName(), r.type());
        check(name + ".delta_in_[" + size + "," + (size + EPS) + "]", true, r.delta >= size && r.delta <= size + EPS);
    }

    private static void expectGuard(String name, R r, long l, long m)
    {
        note(name, r);
        check(name + ".type", IOException.class.getName(), r.type());
        check(name + ".message_is_guard", true, guard(l, m).equals(r.rootMessage()));
        check(name + ".delta_lt_eps", true, r.delta < EPS);
    }

    /** the real deserializers throw an IOError whose cause is the guard's IOException (9a, amended 2026-10-13, rec. 2) */
    private static void expectWrappedGuard(String name, R r, long l, long m)
    {
        note(name, r);
        check(name + ".type", IOError.class.getName(), r.type());
        check(name + ".root_type", IOException.class.getName(), r.rootType());
        check(name + ".root_message_is_guard", true, guard(l, m).equals(r.rootMessage()));
        check(name + ".delta_lt_eps", true, r.delta < EPS);
    }

    // ------------------------------------------------------------------ inputs

    /** a vint length followed by 16 zero bytes (9c) */
    private static DataInputBuffer lengthInput(long l, boolean int32, boolean clusteringHeader) throws IOException
    {
        try (DataOutputBuffer o = new DataOutputBuffer())
        {
            if (clusteringHeader)
                o.writeUnsignedVInt(0L);       // header: value 0 is neither null nor empty
            if (int32)
                o.writeUnsignedVInt32((int) l);
            else
                o.writeUnsignedVInt(l);
            o.write(new byte[16]);
            return new DataInputBuffer(o.toByteArray());
        }
    }

    private static TableMetadata metadata()
    {
        return Schema.instance.getTableMetadata(KS, CF);
    }

    private static ColumnMetadata column()
    {
        return metadata().getColumn(ByteBufferUtil.bytes("v"));
    }

    private static RowUpdateBuilder builder(int payload)
    {
        return new RowUpdateBuilder(metadata(), 0, ++pk).add("v", ByteBuffer.allocate(payload));
    }

    private static byte[] serializedMutation(int payload) throws IOException
    {
        Mutation m = builder(payload).build();
        try (DataOutputBuffer dob = new DataOutputBuffer())
        {
            Mutation.serializer.serialize(m, dob, V);
            return dob.toByteArray();
        }
    }

    private static Object deserializeMutation(byte[] bytes) throws IOException
    {
        Mutation m = Mutation.serializer.deserialize(new DataInputBuffer(bytes), V);
        long size = -1;
        for (PartitionUpdate u : m.getPartitionUpdates())
            for (Row row : u)
                size = row.getCell(column()).valueSize();
        return size;
    }

    // ------------------------------------------------------------------ steps (9e unit step 1)

    private static void pass(long M) throws Exception
    {
        DatabaseDescriptor.setMaxValueSize((int) M);
        String p = "M" + M + ".";

        // 1.1 read-back
        check(p + "readback.getMaxValueSize", M, DatabaseDescriptor.getMaxValueSize());
        int m = DatabaseDescriptor.getMaxValueSize();

        // 1.2 at the check: readBuffer(in, M)
        DataInputBuffer in;
        final DataInputBuffer i1 = lengthInput(M, true, false);
        expectAllocated(p + "check.readBuffer.l=M", measure(() -> BytesType.instance.readBuffer(i1, m)), M);
        final DataInputBuffer i2 = lengthInput(M + 1, true, false);
        expectGuard(p + "check.readBuffer.l=M+1", measure(() -> BytesType.instance.readBuffer(i2, m)), M + 1, M);
        final DataInputBuffer i3 = lengthInput(Integer.MAX_VALUE, true, false);
        expectGuard(p + "check.readBuffer.l=2147483647", measure(() -> BytesType.instance.readBuffer(i3, m)), Integer.MAX_VALUE, M);
        final DataInputBuffer i4 = lengthInput(2147483648L, false, false);
        R r4 = measure(() -> BytesType.instance.readBuffer(i4, m));
        note(p + "check.readBuffer.l=2147483648", r4);
        check(p + "check.readBuffer.l=2147483648.type", "org.apache.cassandra.utils.vint.VIntCoding$VIntOutOfRangeException", r4.type());
        check(p + "check.readBuffer.l=2147483648.is_IOException", false, r4.thrown instanceof IOException);
        check(p + "check.readBuffer.l=2147483648.delta_lt_eps", true, r4.delta < EPS);
        final DataInputBuffer i5 = lengthInput(-1L, false, false);
        R r5 = measure(() -> BytesType.instance.readBuffer(i5, m));
        note(p + "check.readBuffer.vint=2^64-1", r5);
        check(p + "check.readBuffer.vint=2^64-1.type", IOException.class.getName(), r5.type());
        check(p + "check.readBuffer.vint=2^64-1.message", "Corrupt (negative) value length encountered", r5.rootMessage());
        check(p + "check.readBuffer.vint=2^64-1.delta_lt_eps", true, r5.delta < EPS);

        // 1.3 array path: readArray(in, M)
        final DataInputBuffer a1 = lengthInput(M, true, false);
        expectAllocated(p + "array.readArray.l=M", measure(() -> BytesType.instance.readArray(a1, m)), M);
        final DataInputBuffer a2 = lengthInput(M + 1, true, false);
        expectGuard(p + "array.readArray.l=M+1", measure(() -> BytesType.instance.readArray(a2, m)), M + 1, M);

        // 1.4 clustering site: reads the live limit from config
        List<AbstractType<?>> types = List.of(BytesType.instance);
        final DataInputBuffer c1 = lengthInput(M + 1, true, true);
        expectGuard(p + "clustering.l=M+1", measure(() -> Clustering.serializer.deserialize(c1, V, types)), M + 1, M);
        final DataInputBuffer c2 = lengthInput(M, true, true);
        expectAllocated(p + "clustering.l=M", measure(() -> Clustering.serializer.deserialize(c2, V, types)), M);

        // 1.5 controls
        in = new DataInputBuffer(new byte[]{ 0, 0, 0, 7 });
        final DataInputBuffer f1 = in;
        R rf = measure(() -> Int32Type.instance.read(ByteBufferAccessor.instance, f1, 0));
        note(p + "control.fixed_length.Int32Type_limit0", rf);
        check(p + "control.fixed_length.Int32Type_limit0.returned_bytes", 4, rf.value instanceof ByteBuffer ? ((ByteBuffer) rf.value).remaining() : rf.type());
        final DataInputBuffer z1 = lengthInput(1, true, false);
        expectGuard(p + "control.limit0.BytesType_l=1", measure(() -> BytesType.instance.readBuffer(z1, 0)), 1, 0);
        final DataInputBuffer s1 = lengthInput(M + 1, true, false);
        R rs = measure(() -> { BytesType.instance.skipValue(s1); return null; });
        note(p + "control.skip.l=M+1", rs);
        check(p + "control.skip.l=M+1.type", EOFException.class.getName(), rs.type());
        check(p + "control.skip.l=M+1.not_guard", false, rs.rootMessage().startsWith("Corrupt value length"));
        check(p + "control.skip.l=M+1.delta_lt_eps", true, rs.delta < EPS);
        final DataInputBuffer w1 = lengthInput(M + 1, true, false);
        R rw = measure(() -> ByteBufferUtil.readWithVIntLength(w1));
        note(p + "control.sibling.readWithVIntLength.l=M+1", rw);
        check(p + "control.sibling.readWithVIntLength.l=M+1.type", EOFException.class.getName(), rw.type());
        check(p + "control.sibling.readWithVIntLength.l=M+1.not_guard", false, rw.rootMessage().startsWith("Corrupt value length"));
        check(p + "control.sibling.readWithVIntLength.l=M+1.delta_in_[" + (M + 1) + "," + (M + 1 + EPS) + "]", true, rw.delta >= M + 1 && rw.delta <= M + 1 + EPS);

        if (M == DEFAULT)
            return;   // 9e step 6: the crafted-input steps cover 256 MiB

        // 1.6 real deserializer: Mutation.serializer
        final byte[] mb1 = serializedMutation((int) M);
        R rm1 = measure(() -> deserializeMutation(mb1));
        note(p + "mutation.payload=M", rm1);
        check(p + "mutation.payload=M.cell_length", M, rm1.value);
        check(p + "mutation.payload=M.delta_ge_M", true, rm1.delta >= M);
        final byte[] mb2 = serializedMutation((int) M + 1);
        expectWrappedGuard(p + "mutation.payload=M+1", measure(() -> deserializeMutation(mb2)), M + 1, M);

        // 1.6b local read response: the coordinator's deserialization of its own replica's response (added 2026-10-13, rec. 3)
        for (long size : new long[]{ M, M + 1 })
        {
            PartitionUpdate u = builder((int) size).buildUpdate();
            ReadResponse resp = ReadResponse.createSimpleDataResponse(new SingletonUnfilteredPartitionIterator(u.unfilteredIterator()),
                                                                      ColumnFilter.all(metadata()));
            SinglePartitionReadCommand cmd = SinglePartitionReadCommand.fullPartitionRead(metadata(), FBUtilities.nowInSeconds(), u.partitionKey());
            R rr = measure(() -> {
                long len = -1;
                try (UnfilteredPartitionIterator it = resp.makeIterator(cmd))
                {
                    while (it.hasNext())
                        try (UnfilteredRowIterator part = it.next())
                        {
                            while (part.hasNext())
                            {
                                Unfiltered un = part.next();
                                if (un.isRow())
                                {
                                    Cell<?> c = ((Row) un).getCell(column());
                                    len = c == null ? -2 : c.valueSize();
                                }
                            }
                        }
                }
                return len;
            });
            String n = p + "local_response.payload=" + (size == M ? "M" : "M+1");
            if (size == M)
            {
                note(n, rr);
                check(n + ".cell_length", M, rr.value);
                check(n + ".delta_ge_M", true, rr.delta >= M);
            }
            else
            {
                expectWrappedGuard(n, rr, M + 1, M);
            }
        }

        // 1.7 live change, once, in the 1 MiB pass
        if (M == 1048576L)
        {
            final byte[] two = serializedMutation(2097152);
            R before = measure(() -> deserializeMutation(two));
            expectWrappedGuard(p + "live.2MiB_under_1MiB", before, 2097152, 1048576);
            DatabaseDescriptor.setMaxValueSize(4194304);
            check(p + "live.readback_after_set_4MiB", 4194304, DatabaseDescriptor.getMaxValueSize());
            R after = measure(() -> deserializeMutation(two));
            note(p + "live.2MiB_under_4MiB", after);
            check(p + "live.2MiB_under_4MiB.cell_length", 2097152L, after.value);
            DatabaseDescriptor.setMaxValueSize((int) M);
        }
    }

    @Test
    public void guard() throws Exception
    {
        check("allocated_bytes_supported", true, TMX.isThreadAllocatedMemorySupported());
        if (!TMX.isThreadAllocatedMemoryEnabled())
            TMX.setThreadAllocatedMemoryEnabled(true);
        check("allocated_bytes_enabled", true, TMX.isThreadAllocatedMemoryEnabled());
        Assert.assertTrue("ThreadMXBean allocated-bytes measurement unsupported: invalid run (9a)", TMX.isThreadAllocatedMemorySupported());

        // read-back before any set: the yaml has no max_value_size line
        int found = DatabaseDescriptor.getMaxValueSize();
        check("readback.before_any_set", DEFAULT, found);

        // warm-up (9b): one full unrecorded pass at 1 MiB, so class loading and JIT compilation are outside the recorded deltas
        record = false;
        pass(1048576L);
        record = true;

        for (long M : LIMITS)
            pass(M);

        DatabaseDescriptor.setMaxValueSize(found);
        check("restored", found, DatabaseDescriptor.getMaxValueSize());
        line("STAGE4 done mismatches=" + mismatches);
        if (out != null) out.close();
        Assert.assertEquals("STAGE4 mismatches", 0, mismatches);
    }
}
