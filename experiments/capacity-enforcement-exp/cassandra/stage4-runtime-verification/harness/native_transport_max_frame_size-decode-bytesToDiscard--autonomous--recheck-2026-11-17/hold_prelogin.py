# Stage-4 recheck client (2026-11-17), native_transport_max_frame_size-decode-bytesToDiscard--autonomous.
# usage: python3 hold_prelogin.py partial|complete <host> <port> <k> <L> <hold>
#   partial : per connection, a v4 OPTIONS header (stream 1) declaring body length L, then L-1 zero body bytes; held pre-login.
#   complete: per connection, a v4 OPTIONS header with body length 0, then one response read; held pre-login, idle.
# After all k: "holding k"; sleep <hold>; liveness check ("alive"); partial: send the final byte and read one response each.
# Derived from harness/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/hold_frames.py.
import select, socket, struct, sys, time
mode, host, port, K, L, hold = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
assert mode in ('partial', 'complete')

def recvn(s, n):
    b = b''
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError('closed after %d of %d bytes' % (len(b), n))
        b += c
    return b

def read_resp(s, i, tag):
    try:
        s.settimeout(10)
        ver, flags, stream, op, n = struct.unpack('>BBhBI', recvn(s, 9))
        body = recvn(s, n)
        extra = ''
        if op == 0:
            code, mlen = struct.unpack('>iH', body[:6])
            extra = ' code=0x%04x msg=%s' % (code, body[6:6 + mlen].decode('utf-8', 'replace'))
        print('%s i=%d ver=0x%02x stream=%d opcode=%d len=%d%s' % (tag, i, ver, stream, op, n, extra), flush=True)
    except Exception as e:
        print('%s i=%d error=%r' % (tag, i, e), flush=True)
    finally:
        s.settimeout(None)

t0 = time.time()
socks = []
chunk = b'\0' * 65536
for i in range(K):
    try:
        s = socket.create_connection((host, port), timeout=30)
        s.settimeout(None)
        if mode == 'partial':
            s.sendall(struct.pack('>BBhBI', 0x04, 0, 1, 0x05, L))
            sent = 0
            while sent < L - 1:
                n = min(65536, L - 1 - sent); s.sendall(chunk[:n]); sent += n
        else:
            s.sendall(struct.pack('>BBhBI', 0x04, 0, 1, 0x05, 0))
            read_resp(s, i, 'ctrlresp')
        socks.append(s)
    except Exception as e:
        print('connect i=%d error=%r' % (i, e), flush=True)
print('holding %d after %.1f s' % (len(socks), time.time() - t0), flush=True)
time.sleep(hold)

alive = closed = unexpected = 0
r, _, _ = select.select(socks, [], [], 0)
rs = set(r)
for i, s in enumerate(socks):
    if s in rs:
        try:
            d = s.recv(1, socket.MSG_PEEK)
        except Exception as e:
            d = b''
        if d == b'':
            closed += 1; print('closedbyserver i=%d' % i, flush=True)
        else:
            unexpected += 1; alive += 1; print('unexpected i=%d' % i, flush=True)
    else:
        alive += 1
print('alive %d closed %d unexpected %d' % (alive, closed, unexpected), flush=True)

if mode == 'partial':
    for s in socks:
        try:
            s.sendall(b'\0')
        except Exception as e:
            pass
    for i, s in enumerate(socks):
        read_resp(s, i, 'resp')
for s in socks:
    s.close()
print('closed %d' % len(socks), flush=True)
