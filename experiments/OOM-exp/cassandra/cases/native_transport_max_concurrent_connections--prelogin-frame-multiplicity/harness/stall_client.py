# U2 stage 2 (2026-11-17) stall client, derived from the stage-4 recheck hold_prelogin.py (case §2.5 item 2).
# usage: python3 stall_client.py <partial|complete> <host> <port> <k_max> <L> <rate_per_s> <hold_s>
#   partial : per connection a v4 OPTIONS header (stream 1) declaring body length L, then L-1 zero body bytes; held pre-login.
#   complete: per connection a v4 OPTIONS header with body length 0, then one response read; held idle.
# One line per connection: "conn i t_ms ok" or "conn i t_ms err=<repr>". Paced to rate_per_s connection starts per second.
# Never aborts on an error; stops early only after 20 consecutive connect failures ("stop: node gone at i").
# Then "holding <n_ok> of <attempted>", sleep hold_s, liveness check, close every socket WITHOUT the last byte, "done".
# Harness detail (not in the design text): sends use a 60 s socket timeout so a wedged peer cannot block the client forever.
import select, socket, struct, sys, time
mode, host, port, K, L, rate, hold = (sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]),
                                      float(sys.argv[6]), int(sys.argv[7]))
assert mode in ('partial', 'complete')
ms = lambda: int(time.time() * 1000)

def recvn(s, n):
    b = b''
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError('closed after %d of %d bytes' % (len(b), n))
        b += c
    return b

chunk = b'\0' * 65536
socks = []
t0 = time.time()
consec = 0
attempted = 0
for i in range(K):
    due = t0 + i / rate
    now = time.time()
    if due > now:
        time.sleep(due - now)
    attempted += 1
    s = None
    try:
        s = socket.create_connection((host, port), timeout=10)
    except Exception as e:
        print('conn %d %d err=%r' % (i, ms(), e), flush=True)
        consec += 1
        if consec >= 20:
            print('stop: node gone at %d' % i, flush=True)
            break
        continue
    consec = 0
    try:
        s.settimeout(60)
        if mode == 'partial':
            s.sendall(struct.pack('>BBhBI', 0x04, 0, 1, 0x05, L))
            sent = 0
            while sent < L - 1:
                n = min(65536, L - 1 - sent); s.sendall(chunk[:n]); sent += n
        else:
            s.sendall(struct.pack('>BBhBI', 0x04, 0, 1, 0x05, 0))
            v, f, st, op, n = struct.unpack('>BBhBI', recvn(s, 9)); recvn(s, n)
            if op != 6:
                raise RuntimeError('opcode %d' % op)
        s.settimeout(None)
        socks.append(s)
        print('conn %d %d ok' % (i, ms()), flush=True)
    except Exception as e:
        print('conn %d %d err=%r' % (i, ms(), e), flush=True)
        try:
            s.close()
        except Exception:
            pass
print('holding %d of %d after %.1f s' % (len(socks), attempted, time.time() - t0), flush=True)
time.sleep(hold)
alive = closed = unexpected = 0
try:
    r, _, _ = select.select(socks, [], [], 0) if socks else ([], [], [])
except Exception:
    r = []
rs = set(r)
for i, s in enumerate(socks):
    if s in rs:
        try:
            d = s.recv(1, socket.MSG_PEEK)
        except Exception:
            d = b''
        if d == b'':
            closed += 1
        else:
            unexpected += 1; alive += 1
    else:
        alive += 1
print('alive %d closed %d unexpected %d' % (alive, closed, unexpected), flush=True)
for s in socks:
    try:
        s.close()
    except Exception:
        pass
print('done %d' % ms(), flush=True)
