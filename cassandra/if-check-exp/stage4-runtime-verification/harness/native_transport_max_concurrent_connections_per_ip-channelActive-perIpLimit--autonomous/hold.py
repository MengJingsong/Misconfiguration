#!/usr/bin/env python3
# Stage-4 cluster-tier client (B3c, amendment C3 of 2026-10-27) of
# native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous.
# usage: hold.py HOST PORT M S SRC
#   opens M TCP connections from SRC, sends a partial v4 STARTUP envelope (9-byte header declaring a
#   16,000,000-byte body, then S zero bytes; S = -1 sends nothing), prints held=, holds until 60 s after start.
import errno
import socket
import sys
import time

HOLD_S = 60.0
HEADER = bytes([0x04, 0x00, 0x00, 0x00, 0x01, 0x00, 0xF4, 0x24, 0x00])  # v4 request, flags 0, stream 0, STARTUP, 16,000,000


def now_ms():
    return int(time.time() * 1000)


def probe(socks):
    """open = would block on a non-blocking peek; refused = EOF or a socket error."""
    alive = []
    for s in socks:
        if s is None:
            alive.append(False)
            continue
        try:
            s.setblocking(False)
            d = s.recv(1, socket.MSG_PEEK)
            alive.append(len(d) > 0)  # data from the node would be unexpected; count it as open
        except BlockingIOError:
            alive.append(True)
        except OSError:
            alive.append(False)
        finally:
            try:
                s.setblocking(True)
            except OSError:
                pass
    return alive


def main():
    host, port, m, s_bytes, src = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    t0 = time.time()
    socks = []
    connect_err = 0
    for _ in range(m):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        try:
            s.bind((src, 0))
            s.connect((host, port))
            socks.append(s)
        except OSError as e:
            connect_err += 1
            print("connect_error src=%s err=%s" % (src, e), file=sys.stderr, flush=True)
            s.close()
            socks.append(None)
    time.sleep(2)
    alive = probe(socks)
    send_err = 0
    if s_bytes >= 0:
        payload = HEADER + bytes(s_bytes)
        for i, s in enumerate(socks):
            if not alive[i]:
                continue
            try:
                s.settimeout(30)
                s.sendall(payload)
            except OSError as e:
                send_err += 1
                alive[i] = False
                if e.errno not in (errno.ECONNRESET, errno.EPIPE):
                    print("send_error src=%s err=%s" % (src, e), file=sys.stderr, flush=True)
    time.sleep(2)
    alive2 = probe(socks)
    held = sum(1 for a, b in zip(alive, alive2) if a and b)
    print("held=%d refused=%d src=%s s=%d connect_err=%d send_err=%d t=%d" % (held, m - held, src, s_bytes, connect_err, send_err, now_ms()), flush=True)
    rest = HOLD_S - (time.time() - t0)
    if rest > 0:
        time.sleep(rest)
    alive3 = probe(socks)
    print("end held=%d src=%s t=%d" % (sum(1 for a in alive3 if a), src, now_ms()), flush=True)
    for s in socks:
        if s is not None:
            s.close()


if __name__ == "__main__":
    main()
