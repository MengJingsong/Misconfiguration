import socket, struct, sys, time, signal
host, port, n, s = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
src = sys.argv[5] if len(sys.argv) > 5 else None
hdr = struct.pack('>BBhBI', 0x04, 0x00, 0, 0x01, 16000000)
body = b'\0' * max(s, 0)          # s = -1: connect only, send nothing
socks, refused = [], 0
for i in range(n):
    c = socket.socket()
    if src:
        c.bind((src, 0))
    c.connect((host, port))
    try:
        if s >= 0: c.sendall(hdr + body)
        socks.append(c)
    except OSError:
        refused += 1; c.close()
    time.sleep(0.01)
time.sleep(3)
alive = []
for c in socks:
    try:
        r = c.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
        if r == b'':
            refused += 1
        else:
            alive.append(c)
    except BlockingIOError:
        alive.append(c)
    except OSError:
        refused += 1
print(f"held={len(alive)} refused={refused}", flush=True)
signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
try:
    while True: time.sleep(1)
finally:
    for c in alive: c.close()
