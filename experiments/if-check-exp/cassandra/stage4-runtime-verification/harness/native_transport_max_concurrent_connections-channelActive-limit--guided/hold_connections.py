#!/usr/bin/env python3
"""Stage-4 harness, cluster tier (9c), native_transport_max_concurrent_connections-channelActive-limit--guided.
Written 2026-10-20 before any reading.

usage: hold_connections.py --count 4000 --hold-s 30 --stop-file <path> [--host 127.0.0.1] [--port 9042]

Opens --count idle TCP connections to the native port from one address, one after another (blocking connect, then
non-blocking), and never sends a byte. A selector watches every socket: a socket the server closes reads EOF (b'') or a
reset, and is counted as closed by the server (the disallow evidence on the client side, 9d). At --hold-s seconds
after the first connect it prints the HELD line, then keeps holding (and watching) until --stop-file exists, prints
the final counts and closes every socket.

Output (stdout, flushed):
  start ms=<epoch ms> count=<n>
  connected n=<connects that succeeded> errors=<connect errors> first_error=<text> ms=      (after the last connect)
  HELD open=<sockets still open> closed_by_server=<n> errors=<n> ms=                         (at --hold-s)
  FINAL open= closed_by_server= errors= ms=                                                 (when the stop file appears)
  close-latency median_ms=<median ms from connect to server close> max_ms=                  (closed sockets only)
"""
import argparse, os, selectors, socket, statistics, sys, time

ap = argparse.ArgumentParser()
ap.add_argument('--count', type=int, default=4000)
ap.add_argument('--hold-s', type=float, default=30)
ap.add_argument('--stop-file', required=True)
ap.add_argument('--host', default='127.0.0.1')
ap.add_argument('--port', type=int, default=9042)
ap.add_argument('--max-s', type=float, default=600)
a = ap.parse_args()


def now():
    return int(time.time() * 1000)


def say(s):
    print(s, flush=True)


sel = selectors.DefaultSelector()
socks, opened_at, closed_at = {}, {}, {}
errors, first_error = 0, ''
t0 = now()
say(f'start ms={t0} count={a.count}')


def poll(timeout):
    for key, _ in sel.select(timeout):
        s = key.fileobj
        try:
            data = s.recv(65536)
        except BlockingIOError:
            continue
        except OSError:
            data = b''
        if data == b'':
            closed_at[key.data] = now()
            sel.unregister(s)
            s.close()
        # bytes from the server (none expected: the client never sends) are discarded


for i in range(a.count):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(10)
        s.connect((a.host, a.port))
        s.setblocking(False)
        opened_at[i] = now()
        socks[i] = s
        sel.register(s, selectors.EVENT_READ, i)
    except OSError as e:
        errors += 1
        first_error = first_error or f'{type(e).__name__}: {e}'
        s.close()
    if i % 200 == 199:
        poll(0)
say(f'connected n={len(opened_at)} errors={errors} first_error={first_error!r} ms={now()}')


def counts():
    return len(opened_at) - len(closed_at), len(closed_at)


while now() - t0 < a.hold_s * 1000:
    poll(0.2)
o, c = counts()
say(f'HELD open={o} closed_by_server={c} errors={errors} ms={now()}')
while not os.path.exists(a.stop_file) and now() - t0 < a.max_s * 1000:
    poll(0.2)
poll(0)
o, c = counts()
say(f'FINAL open={o} closed_by_server={c} errors={errors} ms={now()}')
lat = [closed_at[i] - opened_at[i] for i in closed_at]
if lat:
    say(f'close-latency median_ms={statistics.median(lat):.0f} max_ms={max(lat)}')
for i, s in socks.items():
    if i not in closed_at:
        try:
            sel.unregister(s)
        except Exception:
            pass
        s.close()
say(f'closed-all ms={now()}')
