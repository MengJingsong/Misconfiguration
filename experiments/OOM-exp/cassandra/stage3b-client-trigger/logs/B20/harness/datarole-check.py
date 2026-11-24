#!/usr/bin/env python3
"""3-b confirm B20 negative check (code-reading claim: a data role cannot start an index build).
Superuser: admin-made keyspace dks + table dks.t (B20 shape) + role datarole with ONLY SELECT and MODIFY on dks.t.
datarole: one write, then CREATE INDEX / ALTER TABLE / DROP INDEX attempts (expected Unauthorized)."""
import json, drv
cl, s = drv.session('cassandra', retry_s=120)
for q in ["CREATE ROLE datarole WITH PASSWORD = 'datarole-pw' AND LOGIN = true AND SUPERUSER = false",
          "CREATE KEYSPACE dks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
          "CREATE TABLE dks.t (pk bigint, ck int, v blob, PRIMARY KEY (pk, ck))",
          "GRANT SELECT ON TABLE dks.t TO datarole", "GRANT MODIFY ON TABLE dks.t TO datarole"]:
    s.execute(q); print('admin> ' + q)
for r in s.execute("LIST ALL PERMISSIONS OF datarole"): print('perm> ' + ' | '.join(map(str, r)))
cl.shutdown()
cl, s = drv.session('datarole')
out = {}
for name, q in [('insert', "INSERT INTO dks.t (pk, ck, v) VALUES (1, 1, 0x00)"),
                ('create_index', "CREATE INDEX t_ck ON dks.t (ck)"),
                ('alter_table', "ALTER TABLE dks.t ADD w int"),
                ('create_table_in_dks', "CREATE TABLE dks.u (a int PRIMARY KEY)")]:
    try: s.execute(q); out[name] = 'ALLOWED'
    except Exception as e: out[name] = type(e).__name__ + ': ' + str(e)[:200]
print(json.dumps(out, indent=1))
cl.shutdown()
