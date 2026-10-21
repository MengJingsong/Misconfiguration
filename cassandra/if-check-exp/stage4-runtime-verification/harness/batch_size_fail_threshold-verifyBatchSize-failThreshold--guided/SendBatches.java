/*
 * Stage-4 harness, both tiers, for batch_size_fail_threshold-verifyBatchSize-failThreshold--guided (case 9c, amended
 * R4, R7, R8 on 2026-10-20). The client: one protocol-v5 connection (SimpleClient), one batch in flight. Each batch is
 * UNLOGGED, --partitions prepared INSERTs "INSERT INTO <ks>.<table> (pk, v) VALUES (?, ?)", pk 0..P-1, v a blob of
 * --bytes / P bytes, at ONE. After each response it waits for the request's Byteman lines (batch-alloc.btm) in the
 * trace file, joins them to the request and prints one line:
 *   req arm=<arm> k=<i> nominal=<bytes> outcome=<ok|ERR:<class>:<message>> dec=<b> exe=<b> bst=<b> size=<dataSize>
 *       fail=<threshold bytes> rej=<0|1> lines=<dec>/<exe>/<bst>/<siz>/<rej> ms=<epoch>
 * A missing reading prints as -1; lines= counts each kind found for the request (1/1/1/1/0|1 for a batch that reached
 * the check; 0/0/0/0/0 for one the transport discarded).
 *
 * Cluster tier (from the clone, after ant build):
 *   java -cp <classes>:build/classes/main:build/lib/jars/'*':lib/'*' org.apache.cassandra.transport.SendBatches \
 *     --host 127.0.0.1 --keyspace ks --table t --trace <file> --arm <name> --bytes <B> --partitions 64 --count 20
 * Unit tier: BatchSizeAllocTest calls run(...) against CQLTester's in-process server.
 */
package org.apache.cassandra.transport;

import java.io.IOException;
import java.io.PrintStream;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
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

public class SendBatches
{
    static final Pattern BYTES = Pattern.compile("bytes=(-?\\d+)");
    static final Pattern SIZE = Pattern.compile("size=(\\d+) fail=(\\d+)");

    public static ResultMessage.Prepared prepare(SimpleClient client, String keyspace, String table)
    {
        return client.prepare("INSERT INTO " + keyspace + '.' + table + " (pk, v) VALUES (?, ?)");
    }

    static BatchMessage batch(ResultMessage.Prepared prepared, int partitions, long bytes)
    {
        int each = (int) (bytes / partitions);
        List<Object> ids = new ArrayList<>(partitions);
        List<List<ByteBuffer>> values = new ArrayList<>(partitions);
        for (int p = 0; p < partitions; p++)
        {
            ids.add(prepared.statementId);
            List<ByteBuffer> v = new ArrayList<>(2);
            v.add(ByteBufferUtil.bytes(p));
            v.add(ByteBuffer.allocate(each));
            values.add(v);
        }
        QueryOptions options = QueryOptions.create(ConsistencyLevel.ONE, Collections.emptyList(), false, -1, null, null,
                                                   ProtocolVersion.V5, null);
        return new BatchMessage(BatchStatement.Type.UNLOGGED, ids, values, options);
    }

    static long length(String trace)
    {
        java.io.File f = new java.io.File(trace);
        return f.exists() ? f.length() : 0;
    }

    static List<String> linesAfter(String trace, long offset) throws IOException
    {
        List<String> out = new ArrayList<>();
        if (!new java.io.File(trace).exists())
            return out;
        try (RandomAccessFile f = new RandomAccessFile(trace, "r"))
        {
            if (f.length() <= offset)
                return out;
            f.seek(offset);
            byte[] b = new byte[(int) (f.length() - offset)];
            f.readFully(b);
            String s = new String(b, StandardCharsets.UTF_8);
            int end = s.lastIndexOf('\n');
            if (end < 0)
                return out;
            for (String l : s.substring(0, end).split("\n"))
                if (!l.isEmpty())
                    out.add(l);
        }
        return out;
    }

    static long bytesOf(String line)
    {
        Matcher m = BYTES.matcher(line);
        return m.find() ? Long.parseLong(m.group(1)) : -1;
    }

    /** Sends count batches one at a time; returns the req lines (also printed to out). */
    public static List<String> run(SimpleClient client, ResultMessage.Prepared prepared, String trace, String arm,
                                   long bytes, int partitions, int count, long pauseMs, PrintStream out) throws Exception
    {
        List<String> result = new ArrayList<>();
        for (int k = 0; k < count; k++)
        {
            BatchMessage msg = batch(prepared, partitions, bytes);
            long offset = length(trace);
            Message.Response r = client.execute(msg, false);
            String outcome;
            if (r instanceof ErrorMessage)
            {
                Throwable e = (Throwable) ((ErrorMessage) r).error;
                outcome = "ERR:" + e.getClass().getSimpleName() + ":" + String.valueOf(e.getMessage()).replace(' ', '_');
            }
            else
                outcome = "ok";
            // the exe line is written when BatchMessage.execute returns, just before the response is sent; wait for
            // it up to 3 s (a request the transport discarded writes none), then a further pause for stragglers
            long deadline = System.currentTimeMillis() + 3000;
            while (System.currentTimeMillis() < deadline && linesAfter(trace, offset).stream().noneMatch(l -> l.startsWith("exe ")))
                Thread.sleep(20);
            Thread.sleep(pauseMs);
            List<String> lines = linesAfter(trace, offset);
            Map<String, Integer> n = new HashMap<>();
            long dec = -1, exe = -1, bst = -1, size = -1, fail = -1;
            for (String l : lines)
            {
                String tag = l.split(" ", 2)[0];
                n.merge(tag, 1, Integer::sum);
                switch (tag)
                {
                    case "dec": dec = bytesOf(l); break;
                    case "exe": exe = bytesOf(l); break;
                    case "bst": bst = bytesOf(l); break;
                    case "siz":
                        Matcher m = SIZE.matcher(l);
                        if (m.find()) { size = Long.parseLong(m.group(1)); fail = Long.parseLong(m.group(2)); }
                        break;
                }
            }
            String line = "req arm=" + arm + " k=" + k + " nominal=" + bytes + " outcome=" + outcome + " dec=" + dec
                          + " exe=" + exe + " bst=" + bst + " size=" + size + " fail=" + fail
                          + " rej=" + n.getOrDefault("rej", 0) + " lines=" + n.getOrDefault("dec", 0) + '/'
                          + n.getOrDefault("exe", 0) + '/' + n.getOrDefault("bst", 0) + '/' + n.getOrDefault("siz", 0)
                          + '/' + n.getOrDefault("rej", 0) + " ms=" + System.currentTimeMillis();
            out.println(line);
            out.flush();
            result.add(line);
        }
        return result;
    }

    public static void main(String[] args) throws Exception
    {
        Map<String, String> a = new HashMap<>();
        for (int i = 0; i + 1 < args.length; i += 2)
            a.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        DatabaseDescriptor.clientInitialization();
        SimpleClient client = SimpleClient.builder(a.getOrDefault("host", "127.0.0.1"), Integer.parseInt(a.getOrDefault("port", "9042")))
                                          .protocolVersion(ProtocolVersion.V5).build().connect(false);
        ResultMessage.Prepared prepared = prepare(client, a.getOrDefault("keyspace", "ks"), a.getOrDefault("table", "t"));
        System.out.println("start ms=" + System.currentTimeMillis() + " arm=" + a.get("arm") + " protocol=" + client.connection.getVersion());
        run(client, prepared, a.get("trace"), a.get("arm"), Long.parseLong(a.get("bytes")),
            Integer.parseInt(a.getOrDefault("partitions", "64")), Integer.parseInt(a.getOrDefault("count", "20")),
            Long.parseLong(a.getOrDefault("pause-ms", "300")), System.out);
        System.out.println("end ms=" + System.currentTimeMillis());
        client.close();
        System.exit(0);
    }
}
