import os, socket, sys, threading, time
LISTEN, TARGET, FLAG = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
def pump(src, dst, gated):
    try:
        while True:
            while gated and os.path.exists(FLAG): time.sleep(0.02)
            d = src.recv(65536)
            if not d: break
            dst.sendall(d)
    except OSError: pass
    finally:
        for s in (src, dst):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass
ls = socket.socket(); ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
ls.bind(('127.0.0.1', LISTEN)); ls.listen(16)
while True:
    c, _ = ls.accept()
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536); s.connect(('127.0.0.1', TARGET))
    threading.Thread(target=pump, args=(c, s, False), daemon=True).start()
    threading.Thread(target=pump, args=(s, c, True), daemon=True).start()
