/*
 * Stage-4 harness, cluster tier, for native_transport_receive_queue_capacity-acquireCapacity-queueCapacity
 * (case 9c, amended 2026-10-15). The client: N protocol-v5 connections of one mode (SimpleClient, so the
 * THROW_ON_OVERLOAD startup option is exact), W requests in flight on each, one stream id per slot. A successful
 * response re-sends its slot at once; an OverloadedException re-sends it after --retry-ms (100). At the end it stops
 * sending and waits for every outstanding response (up to 120 s), then closes the connections.
 *
 * The request: QUERY "SELECT pk FROM ks.t WHERE pk = 0 AND v = ? ALLOW FILTERING" at ONE, the value a blob of
 * --value-bytes bytes (a read of an empty table: the node writes nothing).
 *
 * Output (stdout): "conn <i> local=<address>" per connection (the server's trace names it as remote=), one line per
 * second "sec t=<s> sent= ok= warned= ovl_bytes= ovl_other= err= outstanding=" (cumulative counts), and at the end
 * "TOTAL ..." plus up to five texts of each error kind. warned = successful responses whose warnings contain
 * "bytes in flight"; ovl_bytes = OverloadedException whose text contains "bytes in flight".
 *
 * B27 stage 2 (2026-11-24), the two changes of case §2.5 only: (a) each connect is wrapped in try/catch; on failure
 * (server closing the channel, or SimpleClient's 10-s TIMEOUT_SECONDS) print "conn <i> refused <reason>", count refused,
 * shut that client's event loop group and continue; the per-second line adds refused= and connected=; (b) --window 0
 * is allowed (connect, STARTUP, then hold idle).
 *
 * Run from the cassandra-5.0.9 clone after `ant build`:
 *   java -Dio.netty.eventLoopThreads=1 -cp <classes>:build/classes/main:build/lib/jars/'*':lib/'*' \
 *     org.apache.cassandra.transport.NativeFlood --host 127.0.0.1 --connections 10 --window 128 \
 *     --value-bytes 65000 --seconds 60 --throw false [--retry-ms 100]
 */
package org.apache.cassandra.transport;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.exceptions.OverloadedException;
import org.apache.cassandra.transport.messages.ErrorMessage;
import org.apache.cassandra.transport.messages.QueryMessage;

public class NativeFlood
{
    static final AtomicLong sent = new AtomicLong(), ok = new AtomicLong(), warned = new AtomicLong(),
                            ovlBytes = new AtomicLong(), ovlOther = new AtomicLong(), err = new AtomicLong(),
                            outstanding = new AtomicLong(), refused = new AtomicLong(), connected = new AtomicLong();
    static final ConcurrentLinkedQueue<String> ovlOtherTexts = new ConcurrentLinkedQueue<>(), errTexts = new ConcurrentLinkedQueue<>();
    static volatile boolean running = true;

    static String query = "SELECT pk FROM ks.t WHERE pk = 0 AND v = ? ALLOW FILTERING";
    static ByteBuffer value;

    static QueryMessage request()
    {
        QueryOptions options = QueryOptions.create(ConsistencyLevel.ONE, Collections.singletonList(value.duplicate()), false,
                                                   -1, null, null, ProtocolVersion.V5, null);
        return new QueryMessage(query, options);
    }

    static void send(SimpleClient client, int streamId)
    {
        Message.Request request = request();
        request.setSource(new Envelope(Envelope.Header.dummy(streamId, request.type), null));
        request.attach(client.connection);
        sent.incrementAndGet();
        client.channel.writeAndFlush(Collections.singletonList(request));
    }

    static void note(ConcurrentLinkedQueue<String> q, String s)
    {
        if (q.size() < 5) q.add(s);
    }

    public static void main(String[] args) throws Exception
    {
        Map<String, String> a = new HashMap<>();
        for (int i = 0; i + 1 < args.length; i += 2)
            a.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        String host = a.getOrDefault("host", "127.0.0.1");
        int port = Integer.parseInt(a.getOrDefault("port", "9042"));
        int n = Integer.parseInt(a.get("connections"));
        int w = Integer.parseInt(a.get("window"));
        int valueBytes = Integer.parseInt(a.get("value-bytes"));
        double seconds = Double.parseDouble(a.get("seconds"));
        boolean throwOnOverload = Boolean.parseBoolean(a.get("throw"));
        long retryMs = Long.parseLong(a.getOrDefault("retry-ms", "100"));
        value = ByteBuffer.allocate(valueBytes);

        DatabaseDescriptor.clientInitialization();
        ScheduledExecutorService retry = Executors.newScheduledThreadPool(2);
        // Amendment 2026-11-24 (stage 2, before any reading): connects run on --connect-threads threads (default 1),
        // the same value in every arm, because a refused connect (I2) costs SimpleClient's 10-s timeout and 357
        // refusals per JVM in series would take an hour.
        int connectThreads = Integer.parseInt(a.getOrDefault("connect-threads", "1"));
        List<SimpleClient> clients = Collections.synchronizedList(new ArrayList<>());
        java.util.concurrent.ExecutorService cx = Executors.newFixedThreadPool(connectThreads);
        for (int i0 = 0; i0 < n; i0++)
        {
            final int i = i0;
            cx.submit(() -> {
                SimpleClient c = SimpleClient.builder(host, port).protocolVersion(ProtocolVersion.V5).build();
                try
                {
                    c.connect(false, throwOnOverload);
                }
                catch (Throwable t)
                {
                    refused.incrementAndGet();
                    System.out.println("conn " + i + " refused " + t.getClass().getSimpleName() + ": " + t.getMessage());
                    try { if (c.bootstrap != null) c.bootstrap.group().shutdownGracefully(); } catch (Throwable ignore) {}
                    return;
                }
                clients.add(c);
                connected.incrementAndGet();
                System.out.println("conn " + i + " local=" + c.channel.localAddress() + " throw=" + throwOnOverload);
            });
        }
        cx.shutdown();
        cx.awaitTermination(1, TimeUnit.HOURS);
        System.out.println("start ms=" + System.currentTimeMillis() + " connections=" + n + " window=" + w
                           + " value_bytes=" + valueBytes + " seconds=" + seconds + " throw=" + throwOnOverload
                           + " retry_ms=" + retryMs + " connected=" + connected.get() + " refused=" + refused.get());
        System.out.flush();

        List<Thread> readers = new ArrayList<>();
        for (SimpleClient c : clients)
        {
            Thread t = new Thread(() -> {
                while (running || outstanding.get() > 0)
                {
                    Message.Response r;
                    try { r = c.responseHandler.responses.poll(200, TimeUnit.MILLISECONDS); }
                    catch (InterruptedException e) { return; }
                    if (r == null)
                        continue;
                    int slot = r.getSource().header.streamId;
                    boolean overload = false;
                    if (r instanceof ErrorMessage)
                    {
                        Throwable e = (Throwable) ((ErrorMessage) r).error;
                        String text = String.valueOf(e.getMessage());
                        if (e instanceof OverloadedException && text.contains("bytes in flight"))
                        {
                            ovlBytes.incrementAndGet();
                            overload = true;
                        }
                        else if (e instanceof OverloadedException)
                        {
                            ovlOther.incrementAndGet();
                            note(ovlOtherTexts, text);
                            overload = true;
                        }
                        else
                        {
                            err.incrementAndGet();
                            note(errTexts, e.getClass().getSimpleName() + ": " + text);
                        }
                    }
                    else
                    {
                        ok.incrementAndGet();
                        if (r.getWarnings() != null && String.join("|", r.getWarnings()).contains("bytes in flight"))
                            warned.incrementAndGet();
                    }
                    if (!running)
                    {
                        outstanding.decrementAndGet();
                        continue;
                    }
                    if (overload)
                        retry.schedule(() -> {
                            if (running) send(c, slot);
                            else outstanding.decrementAndGet();
                        }, retryMs, TimeUnit.MILLISECONDS);
                    else
                        send(c, slot);
                }
            }, "reader-" + c.channel.localAddress());
            t.setDaemon(true);
            t.start();
            readers.add(t);
        }

        long start = System.currentTimeMillis();
        for (SimpleClient c : clients)
            for (int s = 1; s <= w; s++)
            {
                outstanding.incrementAndGet();
                send(c, s);
            }

        long end = start + (long) (seconds * 1000);
        int sec = 0;
        while (System.currentTimeMillis() < end)
        {
            Thread.sleep(Math.max(1, Math.min(1000, end - System.currentTimeMillis())));
            sec++;
            line("sec t=" + sec);
        }
        running = false;
        long stopMs = System.currentTimeMillis();
        System.out.println("stop ms=" + stopMs);
        long deadline = stopMs + 120_000;
        while (outstanding.get() > 0 && System.currentTimeMillis() < deadline)
        {
            Thread.sleep(500);
            line("drain t=" + (System.currentTimeMillis() - stopMs) / 1000.0);
        }
        retry.shutdownNow();
        line("TOTAL");
        for (String s : ovlOtherTexts) System.out.println("ovl_other_text " + s);
        for (String s : errTexts) System.out.println("err_text " + s);
        System.out.println("end ms=" + System.currentTimeMillis());
        System.out.flush();
        for (SimpleClient c : clients)
            try { c.close(); } catch (Throwable ignore) {}
        System.exit(outstanding.get() == 0 ? 0 : 3);
    }

    static void line(String head)
    {
        System.out.println(head + " sent=" + sent.get() + " ok=" + ok.get() + " warned=" + warned.get() + " ovl_bytes="
                           + ovlBytes.get() + " ovl_other=" + ovlOther.get() + " err=" + err.get() + " outstanding="
                           + outstanding.get() + " refused=" + refused.get() + " connected=" + connected.get()
                           + " ms=" + System.currentTimeMillis());
        System.out.flush();
    }
}
