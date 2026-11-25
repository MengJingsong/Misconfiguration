import os, socket, sys, threading, time
PAUSE = sys.argv[1]; LISTEN = ('127.0.0.1', 19042); UP = ('127.0.0.1', 9042)
def pump(src, dst, pausable):
    try:
        while True:
            while pausable and os.path.exists(PAUSE):
                time.sleep(0.01)
            d = src.recv(65536)
            if not d: break
            dst.sendall(d)
    except OSError: pass
    finally:
        for s in (src, dst):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(LISTEN); srv.listen(16)
while True:
    c, _ = srv.accept(); u = socket.create_connection(UP)
    threading.Thread(target=pump, args=(c, u, False), daemon=True).start()
    threading.Thread(target=pump, args=(u, c, True), daemon=True).start()
