/*
 * Stage-4 harness, unit tier of max_mutation_size-validateSize-MAX_MUTATION_SIZE (case file section 9, 9e unit steps 2.1-2.6).
 * Not part of upstream Cassandra. Copy into test/unit/org/apache/cassandra/db/commitlog/ of a local clone at cassandra-5.0.9.
 * System properties: stage4.expect_mms (bytes, required), stage4.out (a file that also receives the STAGE4 lines).
 * The yaml is chosen with -Dcassandra.config=file:///<path> (make-unit-yaml.sh). Records "check ... MISMATCH" and goes on;
 * fails at the end if any check mismatched.
 */
package org.apache.cassandra.db.commitlog;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.UUID;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.db.CounterMutation;
import org.apache.cassandra.db.IMutation;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.MutationExceededMaxSizeException;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.marshal.AsciiType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.MemtableParams;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.utils.FBUtilities;

import static org.apache.cassandra.db.commitlog.CommitLogSegment.ENTRY_OVERHEAD_SIZE;

public class MaxMutationSizeGuardTest
{
    private static final String KS = "MmsGuard";
    private static final String CF = "Standard1";
    private static final int V = MessagingService.current_version;

    private static PrintWriter out;
    private static int mismatches = 0;

    @BeforeClass
    public static void beforeClass() throws Exception
    {
        String o = System.getProperty("stage4.out");
        out = o == null ? null : new PrintWriter(new FileWriter(o, true), true);
        // as CommitLogTest.beforeClass(): keep system-keyspace writes out of the log (9b hold fixed)
        KeyspaceParams.DEFAULT_LOCAL_DURABLE_WRITES = false;
        SchemaLoader.prepareServer();
        StorageService.instance.getTokenMetadata().updateHostId(UUID.randomUUID(), FBUtilities.getBroadcastAddressAndPort());
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(KS, CF, 0, AsciiType.instance, BytesType.instance)
                                                .memtable(MemtableParams.get("skiplist")));
        CompactionManagerHolder.disable();
    }

    private static void line(String s)
    {
        System.out.println(s);
        if (out != null) out.println(s);
    }

    private static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    private static void note(String name, Object value)
    {
        line("STAGE4 note " + name + " " + value);
    }

    private static Mutation m(int payload)
    {
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(CF);
        return new RowUpdateBuilder(cfs.metadata(), 0, "k").clustering("bytes").add("val", ByteBuffer.allocate(payload)).build();
    }

    /** the check's operand: serializedSize + 12 (Mutation.validateSize():171 with CommitLog.add()'s overhead) */
    private static long T(int payload)
    {
        return (long) m(payload).serializedSize(V) + ENTRY_OVERHEAD_SIZE;
    }

    private static long meter()
    {
        return CommitLog.instance.metrics.oversizedMutations.getCount();
    }

    private static int position()
    {
        return CommitLog.instance.getCurrentPosition().position;
    }

    @Test
    public void guard() throws Exception
    {
        CommitLog.instance.resetUnsafe(true);
        long expect = Long.parseLong(System.getProperty("stage4.expect_mms"));

        // 2.1 read-back
        note("commitlog_segment_size", DatabaseDescriptor.getCommitLogSegmentSize());
        check("readback.getMaxMutationSize", expect, DatabaseDescriptor.getMaxMutationSize());
        check("readback.IMutation.MAX_MUTATION_SIZE", expect, IMutation.MAX_MUTATION_SIZE);
        long M = IMutation.MAX_MUTATION_SIZE;

        // 2.2 calibrate: p* = the largest payload with T(p) <= M (T is non-decreasing in p)
        int lo = 1, hi = (int) M;
        while (lo < hi)
        {
            int mid = lo + (hi - lo + 1) / 2;
            if (T(mid) <= M) lo = mid; else hi = mid - 1;
        }
        int p = lo;
        long tp = T(p), tp1 = T(p + 1);
        note("p_star", p);
        note("T_p_star", tp);
        note("T_p_star_plus_1", tp1);
        note("k", tp - p);
        check("calibrate.T_p_star_equals_M", M, tp);
        check("calibrate.T_p_star_plus_1_equals_M_plus_1", M + 1, tp1);

        // 2.3 boundary at the check itself
        long n0 = meter();
        String accepted;
        try { m(p).validateSize(V, ENTRY_OVERHEAD_SIZE); accepted = "returned"; }
        catch (MutationExceededMaxSizeException e) { accepted = "threw " + e.mutationSize; }
        check("validate.at_limit", "returned", accepted);
        check("validate.at_limit.meter_delta", 0, meter() - n0);
        n0 = meter();
        try
        {
            m(p + 1).validateSize(V, ENTRY_OVERHEAD_SIZE);
            check("validate.over_limit", "threw", "returned");
        }
        catch (MutationExceededMaxSizeException e)
        {
            check("validate.over_limit", "threw", "threw");
            check("validate.over_limit.mutationSize", M + 1, e.mutationSize);
            check("validate.over_limit.message_has_operands", true, e.getMessage().contains("(" + (M + 1) + "/" + M + ")"));
            note("validate.over_limit.message", e.getMessage());
        }
        check("validate.over_limit.meter_delta", 1, meter() - n0);

        // 2.4 at CommitLog.add(): the accepted entry moves the position by M (or M + 8 with a sync marker), the refused one by 0
        // after resetUnsafe() no segment is active and getCurrentPosition() reads the last closed one (end of buffer + 1);
        // one small warm-up entry opens a live segment, so P0 and P1 are in the same segment (instrument check, 2026-10-11)
        CommitLog.instance.add(m(1));
        CommitLog.instance.sync(true);
        CommitLogPosition q0 = CommitLog.instance.getCurrentPosition();
        int s0 = CommitLog.instance.segmentManager.getActiveSegments().size();
        CommitLogPosition ret = CommitLog.instance.add(m(p));
        CommitLogPosition q1 = CommitLog.instance.getCurrentPosition();
        note("add.at_limit.before", q0 + " segments=" + s0);
        note("add.at_limit.after", q1 + " segments=" + CommitLog.instance.segmentManager.getActiveSegments().size() + " returned=" + ret);
        int p0 = q0.position, p1 = q1.position;
        note("add.at_limit.position_delta", p1 - p0);
        long d = p1 - p0;
        check("add.at_limit.same_segment", q0.segmentId, q1.segmentId);
        check("add.at_limit.position_delta_is_M_or_M_plus_8", true, d == M || d == M + CommitLogSegment.SYNC_MARKER_SIZE);
        CommitLog.instance.sync(true);
        int P = position();
        int s = CommitLog.instance.segmentManager.getActiveSegments().size();
        long c = CommitLog.instance.getActiveContentSize();
        long n = meter();
        String r;
        try { CommitLog.instance.add(m(p + 1)); r = "returned"; }
        catch (MutationExceededMaxSizeException e) { r = "threw"; }
        check("add.over_limit", "threw", r);
        check("add.over_limit.position_delta", 0, position() - P);
        check("add.over_limit.segment_count", s, CommitLog.instance.segmentManager.getActiveSegments().size());
        check("add.over_limit.meter_delta", 1, meter() - n);
        CommitLog.instance.sync(true);
        check("add.over_limit.content_size_delta", 0, CommitLog.instance.getActiveContentSize() - c);

        // 2.5 counter site: refused iff T + 2 + len("ONE") > M, and the meter does not move
        CounterMutation cm5 = new CounterMutation(m(p - 5), ConsistencyLevel.ONE);
        CounterMutation cm4 = new CounterMutation(m(p - 4), ConsistencyLevel.ONE);
        check("counter.size_is_T_plus_5", T(p - 5) - ENTRY_OVERHEAD_SIZE + 5, cm5.serializedSize(V));
        n0 = meter();
        try { cm5.validateSize(V, ENTRY_OVERHEAD_SIZE); r = "returned"; }
        catch (MutationExceededMaxSizeException e) { r = "threw"; }
        check("counter.p_star_minus_5", "returned", r);
        try { cm4.validateSize(V, ENTRY_OVERHEAD_SIZE); r = "returned"; }
        catch (MutationExceededMaxSizeException e) { r = "threw " + e.mutationSize; }
        check("counter.p_star_minus_4", "threw " + (M + 1), r);
        check("counter.meter_delta", 0, meter() - n0);

        // 2.6 idle
        CommitLog.instance.sync(true);
        int i0 = position();
        Thread.sleep(2000);
        check("idle.position_delta", 0, position() - i0);

        line("STAGE4 done mismatches=" + mismatches);
        if (out != null) out.close();
        Assert.assertEquals("STAGE4 mismatches", 0, mismatches);
    }

    /** keeps background compaction off this keyspace; nothing here depends on it */
    private static final class CompactionManagerHolder
    {
        static void disable()
        {
            Keyspace.open(KS).getColumnFamilyStore(CF).disableAutoCompaction();
        }
    }
}
