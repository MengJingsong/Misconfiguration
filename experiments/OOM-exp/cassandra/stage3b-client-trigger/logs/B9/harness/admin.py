#!/usr/bin/env python3
"""B9 3-b confirm: superuser setup (default role `cassandra`, used only here) and the victim role's preload/check.
  admin.py setup <victim_pw>     # waits for the default superuser, creates role victim + keyspace vks + grants, lists
  admin.py check <victim_pw>     # as victim: write/read its own table; as no-credentials client: what it is refused
"""
import sys, time, struct
from cql4 import *

STMTS = [
    "CREATE ROLE IF NOT EXISTS victim WITH PASSWORD = '%(pw)s' AND LOGIN = true AND SUPERUSER = false",
    "CREATE KEYSPACE IF NOT EXISTS vks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
    "CREATE TABLE IF NOT EXISTS vks.kv (k int PRIMARY KEY, v text)",
    "GRANT SELECT ON TABLE vks.kv TO victim",
    "GRANT MODIFY ON TABLE vks.kv TO victim",
    "LIST ROLES",
    "LIST ALL PERMISSIONS",
    "SELECT role, is_superuser, can_login FROM system_auth.roles",
    "SELECT keyspace_name FROM system_schema.keyspaces",
]


def q(s, text, st=1):
    s.sendall(frame(OP['QUERY'], query_body(text), st)); _, op, b = rd(s)
    if op == OP['RESULT']:
        names, rs = rows(b)
        return 'OK %s %s' % (names, rs)
    return describe(op, b)


def main():
    cmd, pw = sys.argv[1], sys.argv[2]
    if cmd == 'setup':
        t0 = time.time(); s = None
        while time.time() - t0 < 120:
            try:
                s = sock(); r = login(s, 'cassandra', 'cassandra'); break
            except Exception as e:
                last = str(e); s = None; time.sleep(2)
        if s is None:
            print('SUPERUSER LOGIN FAILED', last); sys.exit(1)
        print('superuser login', r, 'after %.1f s' % (time.time() - t0))
        for st in STMTS:
            text = st % {'pw': pw}
            print('>', text.replace(pw, '***')); print('  ', q(s, text))
        s.close()
    elif cmd == 'check':
        s = sock(src='127.0.2.1'); print('victim login:', login(s, 'victim', pw))
        for t in ["INSERT INTO vks.kv (k, v) VALUES (0, 'seed')", 'SELECT v FROM vks.kv WHERE k = 0',
                  'SELECT * FROM system_auth.roles', "CREATE KEYSPACE x WITH replication = {'class':'SimpleStrategy','replication_factor':1}"]:
            print('victim>', t); print('  ', q(s, t))
        s.close()
        # attacker = no credentials at all
        s = sock(src='127.0.1.1'); s.sendall(frame(OP['STARTUP'], startup_body())); _, op, b = rd(s)
        print('no-credential client STARTUP ->', describe(op, b))
        print('no-credential client QUERY ->', q(s, 'SELECT * FROM vks.kv'))
        try:
            tok = b'\0cassandra\0wrong'; s.sendall(frame(OP['AUTH_RESPONSE'], struct.pack('>i', len(tok)) + tok)); _, op, b = rd(s)
            print('no-credential client wrong password ->', describe(op, b))
        except Exception as e:
            print('no-credential client wrong password -> io', e)
        s.close()


if __name__ == '__main__':
    main()
