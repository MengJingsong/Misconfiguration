/*
 * Stage-4 harness, both tiers, for batch_size_warn_threshold-verifyBatchSize-size--autonomous (case B2c/B3c as amended
 * A1, A6, A8, 2026-10-26). One protocol-v4 SimpleClient connection, one batch in flight. Each batch is
 * "INSERT INTO <ks>.<table> (k, c, v) VALUES (?, ?, ?)" statements, v a zero blob of --value-bytes:
 *   --partitions P  distinct partitions per batch (multi-partition when P > 1); --rows R rows per partition (c = 0..R-1)
 *   --type LOGGED|UNLOGGED
 *   --random true   incompressible values (java.util.Random seeded 42, one generator per client run) instead of zeros
 * Keys never repeat inside an arm (k = request * P + p, offset --key-base), so rows written = requests * P * R when every
 * batch is accepted. After each response one line is printed:
 *   req arm=<arm> k=<i> type=<T> parts=<P> rows=<R> nominal=<bytes> outcome=<ok|ERR:<class>:<message>> warns=<n> wsize=<size> ms0=<epoch> ms1=<epoch>
 * warns counts response warnings containing "is of size" (the verifyBatchSize warning, BatchStatement.java:365); wsize is
 * the dataSize in that warning (-1 when none). Arms are delimited by "arm <name> begin|end ms=<epoch>" lines.
 * Byteman lines (warn-size.btm) are joined to arms by time window in analyze.py.
 *
 * Cluster tier: java ... org.apache.cassandra.transport.WarnBatches --host 127.0.1.1 --port 9042 --keyspace ks --table t
 *   --arm <name> --type LOGGED --partitions 50 --rows 1 --value-bytes 1024 --count 2000 [--key-base N]
 * Unit tier: BatchWarnProbeTest calls run(...) against CQLTester's in-process server.
 */
package org.apache.cassandra.transport;

import java.io.PrintStream;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.cql3.statements.BatchStatement;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.transport.messages.BatchMessage;
import org.apache.cassandra.transport.messages.ErrorMessage;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.ByteBufferUtil;

public class WarnBatches
{
    static final Pattern WSIZE = Pattern.compile("is of size (\\d+),");

    public static ResultMessage.Prepared prepare(SimpleClient client, String keyspace, String table)
    {
        return client.prepare("INSERT INTO " + keyspace + '.' + table + " (k, c, v) VALUES (?, ?, ?)");
    }

    /** null: zero-filled values (the default, as in the unit tier); set by --random true: incompressible values from a seeded generator, so data-directory bytes track the data written */
    static java.util.Random random = null;

    static BatchMessage batch(ResultMessage.Prepared prepared, BatchStatement.Type type, long keyBase, int partitions, int rows, int valueBytes)
    {
        List<Object> ids = new ArrayList<>(partitions * rows);
        List<List<ByteBuffer>> values = new ArrayList<>(partitions * rows);
        for (int p = 0; p < partitions; p++)
        {
            for (int r = 0; r < rows; r++)
            {
                ids.add(prepared.statementId);
                List<ByteBuffer> v = new ArrayList<>(3);
                v.add(ByteBufferUtil.bytes((int) (keyBase + p)));
                v.add(ByteBufferUtil.bytes(r));
                ByteBuffer blob = ByteBuffer.allocate(valueBytes);
                if (random != null)
                    random.nextBytes(blob.array());
                v.add(blob);
                values.add(v);
            }
        }
        QueryOptions options = QueryOptions.create(ConsistencyLevel.ONE, Collections.emptyList(), false, -1, null, null,
                                                   ProtocolVersion.V4, null);
        return new BatchMessage(type, ids, values, options);
    }

    /** Sends count batches one at a time; returns the req lines (also printed to out). */
    public static List<String> run(SimpleClient client, ResultMessage.Prepared prepared, String arm, BatchStatement.Type type,
                                   int partitions, int rows, int valueBytes, int count, long keyBase, PrintStream out) throws Exception
    {
        List<String> result = new ArrayList<>();
        out.println("arm " + arm + " begin ms=" + System.currentTimeMillis() + " type=" + type + " parts=" + partitions + " rows=" + rows
                    + " value_bytes=" + valueBytes + " count=" + count);
        for (int k = 0; k < count; k++)
        {
            BatchMessage msg = batch(prepared, type, keyBase + (long) k * partitions, partitions, rows, valueBytes);
            long t0 = System.currentTimeMillis();
            Message.Response r = client.execute(msg, false);
            long t1 = System.currentTimeMillis();
            String outcome;
            if (r instanceof ErrorMessage)
            {
                Throwable e = (Throwable) ((ErrorMessage) r).error;
                outcome = "ERR:" + e.getClass().getSimpleName() + ":" + String.valueOf(e.getMessage()).replace(' ', '_');
            }
            else
                outcome = "ok";
            int warns = 0;
            long wsize = -1;
            List<String> w = r.getWarnings();
            if (w != null)
            {
                for (String s : w)
                {
                    Matcher m = WSIZE.matcher(s);
                    if (m.find()) { warns++; wsize = Long.parseLong(m.group(1)); }
                }
            }
            String line = "req arm=" + arm + " k=" + k + " type=" + type + " parts=" + partitions + " rows=" + rows
                          + " nominal=" + ((long) partitions * rows * valueBytes) + " outcome=" + outcome + " warns=" + warns
                          + " wsize=" + wsize + " ms0=" + t0 + " ms1=" + t1;
            out.println(line);
            out.flush();
            result.add(line);
        }
        out.println("arm " + arm + " end ms=" + System.currentTimeMillis());
        out.flush();
        return result;
    }

    public static void main(String[] args) throws Exception
    {
        Map<String, String> a = new HashMap<>();
        for (int i = 0; i + 1 < args.length; i += 2)
            a.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        DatabaseDescriptor.clientInitialization();
        SimpleClient client = SimpleClient.builder(a.getOrDefault("host", "127.0.0.1"), Integer.parseInt(a.getOrDefault("port", "9042")))
                                          .protocolVersion(ProtocolVersion.V4).build().connect(false);
        if (Boolean.parseBoolean(a.getOrDefault("random", "false")))
            random = new java.util.Random(42);
        ResultMessage.Prepared prepared = prepare(client, a.getOrDefault("keyspace", "ks"), a.getOrDefault("table", "t"));
        System.out.println("start ms=" + System.currentTimeMillis() + " arm=" + a.get("arm") + " protocol=" + client.connection.getVersion());
        run(client, prepared, a.get("arm"), BatchStatement.Type.valueOf(a.getOrDefault("type", "LOGGED")),
            Integer.parseInt(a.getOrDefault("partitions", "50")), Integer.parseInt(a.getOrDefault("rows", "1")),
            Integer.parseInt(a.getOrDefault("value-bytes", "1024")), Integer.parseInt(a.getOrDefault("count", "20")),
            Long.parseLong(a.getOrDefault("key-base", "0")), System.out);
        client.close();
        System.exit(0);
    }
}
