/*
 * Stage-4 harness, both tiers, for native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided
 * (case 9b/9c, amended 9f R2-R3, 2026-10-20). Replaces the fixed_rate_writer.py named in 9c (R5): the fixed-rate writer on
 * one protocol-v5 connection (SimpleClient). connect(false, false) sends no THROW_ON_OVERLOAD startup option, so the
 * connection takes the node's yaml native_transport_throw_on_overload (R3, PipelineConfigurator.java:309-313); the unit
 * test may pass throwOnOverload explicitly.
 *
 * The request: EXECUTE of the prepared "INSERT INTO <ks>.<table> (pk, v) VALUES (?, ?)" at ONE, pk = k, v a blob of
 * --value-bytes bytes (65,536 = 64 KiB). Request k uses stream id k + 1; request k is due at start + k / rate (sent on
 * time, never waiting for a response). Responses are read on one reader thread and never retried.
 *
 * Outcome classes (per response): ok; warned (ok, with a "spent over" client warning); ovl_queue (OverloadedException
 * "Request has spent over ... in the queue", the queue-age refusal); ovl_late (OverloadedException "timed out before it
 * could start", Dispatcher.java:367); ovl_bytes ("bytes in flight"); ovl_other; err (any other error).
 *
 * Cluster tier (main): prints "start", one "sec" line per second while sending, "sendend ms=", then waits for every
 * response for up to --wait-s (180) after the last send, prints one "r" line per request and "TOTAL"; exit 0 when every
 * request has its response, 3 otherwise:
 *   r k=<k> sent_ms=<epoch> resp_ms=<epoch|-1> outcome=<class>
 *   sec t=<s> sent= ok= warned= ovl_queue= ovl_late= ovl_bytes= ovl_other= err= outstanding= ms=
 *   java -cp <classes>:build/classes/main:build/lib/jars/'*':lib/'*' org.apache.cassandra.transport.QueueAgeWriter \
 *     --host 127.0.0.1 --port 9042 --keyspace ks --table t --rate 100 --value-bytes 65536 --seconds 60 [--wait-s 180]
 */
package org.apache.cassandra.transport;

import java.io.PrintStream;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.LockSupport;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.exceptions.OverloadedException;
import org.apache.cassandra.transport.messages.ErrorMessage;
import org.apache.cassandra.transport.messages.ExecuteMessage;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.ByteBufferUtil;

public class QueueAgeWriter
{
    public static final String[] CLASSES = { "ok", "warned", "ovl_queue", "ovl_late", "ovl_bytes", "ovl_other", "err" };

    final SimpleClient client;
    final ResultMessage.Prepared prepared;
    final ByteBuffer value;
    final int max;
    final long[] sentMs, respMs;
    final String[] outcome;
    final Map<String, AtomicLong> counts = new HashMap<>();
    final AtomicLong sent = new AtomicLong(), received = new AtomicLong();
    final String[] firstText = new String[CLASSES.length];
    volatile boolean reading = true;
    Thread reader;

    public QueueAgeWriter(SimpleClient client, ResultMessage.Prepared prepared, int valueBytes, int maxRequests)
    {
        this.client = client;
        this.prepared = prepared;
        this.value = ByteBuffer.allocate(valueBytes);
        this.max = maxRequests;
        sentMs = new long[max];
        respMs = new long[max];
        Arrays.fill(respMs, -1);
        outcome = new String[max];
        for (String c : CLASSES)
            counts.put(c, new AtomicLong());
    }

    public static ResultMessage.Prepared prepare(SimpleClient client, String keyspace, String table)
    {
        return client.prepare("INSERT INTO " + keyspace + '.' + table + " (pk, v) VALUES (?, ?)");
    }

    public long count(String c)
    {
        return counts.get(c).get();
    }

    public long sent()
    {
        return sent.get();
    }

    public long outstanding()
    {
        return sent.get() - received.get();
    }

    static String classify(Message.Response r)
    {
        if (r instanceof ErrorMessage)
        {
            Throwable e = (Throwable) ((ErrorMessage) r).error;
            String text = String.valueOf(e.getMessage());
            if (e instanceof OverloadedException)
            {
                if (text.contains("spent over")) return "ovl_queue";
                if (text.contains("timed out before it could start")) return "ovl_late";
                if (text.contains("bytes in flight")) return "ovl_bytes";
                return "ovl_other";
            }
            return "err";
        }
        List<String> w = r.getWarnings();
        if (w != null && String.join("|", w).contains("spent over"))
            return "warned";
        return "ok";
    }

    /** starts the reader thread; call after any synchronous request (prepare) on this client */
    public void startReader()
    {
        reader = new Thread(() -> {
            while (reading)
            {
                Message.Response r;
                try { r = client.responseHandler.responses.poll(100, TimeUnit.MILLISECONDS); }
                catch (InterruptedException e) { return; }
                if (r == null)
                    continue;
                int k = r.getSource().header.streamId - 1;
                String c = classify(r);
                if (k >= 0 && k < max && respMs[k] < 0)
                {
                    respMs[k] = System.currentTimeMillis();
                    outcome[k] = c;
                }
                counts.get(c).incrementAndGet();
                int ci = Arrays.asList(CLASSES).indexOf(c);
                if (firstText[ci] == null && r instanceof ErrorMessage)
                    firstText[ci] = String.valueOf(((Throwable) ((ErrorMessage) r).error).getMessage());
                received.incrementAndGet();
            }
        }, "qaw-reader");
        reader.setDaemon(true);
        reader.start();
    }

    public void send(int k)
    {
        List<ByteBuffer> values = Arrays.asList(ByteBufferUtil.bytes(k), value.duplicate());
        QueryOptions options = QueryOptions.create(ConsistencyLevel.ONE, values, false, -1, null, null, ProtocolVersion.V5, null);
        Message.Request request = new ExecuteMessage(prepared.statementId, prepared.resultMetadataId, options);
        request.setSource(new Envelope(Envelope.Header.dummy(k + 1, request.type), null));
        request.attach(client.connection);
        sentMs[k] = System.currentTimeMillis();
        sent.incrementAndGet();
        client.channel.writeAndFlush(java.util.Collections.singletonList(request));
    }

    /** sends requests first..first+n-1 at the rate (requests/s), each on time; prints a "sec" line per second if out != null */
    public int sendAtRate(int first, double rate, double seconds, PrintStream out)
    {
        int n = (int) Math.round(rate * seconds);
        long t0 = System.nanoTime();
        long nextSec = t0 + TimeUnit.SECONDS.toNanos(1);
        int sec = 0;
        for (int i = 0; i < n; i++)
        {
            long due = t0 + (long) (i * 1e9 / rate);
            long now;
            while ((now = System.nanoTime()) < due)
                LockSupport.parkNanos(Math.min(due - now, 1_000_000));
            send(first + i);
            if (out != null && System.nanoTime() >= nextSec)
            {
                sec++;
                nextSec += TimeUnit.SECONDS.toNanos(1);
                out.println(line("sec t=" + sec));
                out.flush();
            }
        }
        return n;
    }

    public boolean awaitAll(long timeoutMs) throws InterruptedException
    {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (outstanding() > 0 && System.currentTimeMillis() < deadline)
            Thread.sleep(20);
        return outstanding() == 0;
    }

    public void stopReader()
    {
        reading = false;
    }

    public String line(String head)
    {
        StringBuilder sb = new StringBuilder(head).append(" sent=").append(sent.get());
        for (String c : CLASSES)
            sb.append(' ').append(c).append('=').append(counts.get(c).get());
        return sb.append(" outstanding=").append(outstanding()).append(" ms=").append(System.currentTimeMillis()).toString();
    }

    public void printRequests(PrintStream out, int first, int n)
    {
        for (int k = first; k < first + n; k++)
            out.println("r k=" + k + " sent_ms=" + sentMs[k] + " resp_ms=" + respMs[k] + " outcome=" + (outcome[k] == null ? "none" : outcome[k]));
        for (int i = 0; i < CLASSES.length; i++)
            if (firstText[i] != null)
                out.println("text " + CLASSES[i] + " " + firstText[i]);
        out.flush();
    }

    public static void main(String[] args) throws Exception
    {
        Map<String, String> a = new HashMap<>();
        for (int i = 0; i + 1 < args.length; i += 2)
            a.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        double rate = Double.parseDouble(a.getOrDefault("rate", "100"));
        double seconds = Double.parseDouble(a.getOrDefault("seconds", "60"));
        int valueBytes = Integer.parseInt(a.getOrDefault("value-bytes", "65536"));
        long waitS = Long.parseLong(a.getOrDefault("wait-s", "180"));
        DatabaseDescriptor.clientInitialization();
        SimpleClient client = SimpleClient.builder(a.getOrDefault("host", "127.0.0.1"), Integer.parseInt(a.getOrDefault("port", "9042")))
                                          .protocolVersion(ProtocolVersion.V5).build().connect(false, false);
        ResultMessage.Prepared prepared = prepare(client, a.getOrDefault("keyspace", "ks"), a.getOrDefault("table", "t"));
        int n = (int) Math.round(rate * seconds);
        QueueAgeWriter w = new QueueAgeWriter(client, prepared, valueBytes, n);
        w.startReader();
        System.out.println("start ms=" + System.currentTimeMillis() + " protocol=" + client.connection.getVersion() + " rate=" + rate
                           + " seconds=" + seconds + " value_bytes=" + valueBytes + " n=" + n + " startup_throw_option=absent");
        System.out.flush();
        w.sendAtRate(0, rate, seconds, System.out);
        System.out.println(w.line("sendend"));
        System.out.flush();
        boolean all = w.awaitAll(waitS * 1000);
        w.stopReader();
        w.printRequests(System.out, 0, n);
        System.out.println(w.line("TOTAL") + " all_answered=" + all);
        System.out.flush();
        client.close();
        System.exit(all ? 0 : 3);
    }
}
