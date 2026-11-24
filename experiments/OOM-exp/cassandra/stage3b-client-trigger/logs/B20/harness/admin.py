#!/usr/bin/env python3
"""3-b confirm B20 admin steps, as the default superuser (cassandra), only to create roles, keyspaces and grants.
  admin.py setup   roles attacker (LOGIN, no superuser) and victim (LOGIN); keyspace atk (admin-made, RF 1) with
                   GRANT CREATE ON KEYSPACE atk TO attacker (the only grant); victim keyspace vks + table vks.kv with
                   GRANT SELECT, MODIFY ON TABLE vks.kv TO victim
  admin.py perms   LIST ROLES; LIST ALL PERMISSIONS OF attacker / victim (records what the attacker holds)
"""
import sys, drv
cl, s = drv.session('cassandra', retry_s=120)
def ex(q):
    print('cql> ' + q)
    for r in s.execute(q):
        print('     ' + ' | '.join(str(x) for x in r))
if sys.argv[1] == 'setup':
    for q in [
        "CREATE ROLE attacker WITH PASSWORD = 'attacker-pw' AND LOGIN = true AND SUPERUSER = false",
        "CREATE ROLE victim WITH PASSWORD = 'victim-pw' AND LOGIN = true AND SUPERUSER = false",
        "CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
        "GRANT CREATE ON KEYSPACE atk TO attacker",
        "CREATE KEYSPACE vks WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
        "CREATE TABLE vks.kv (k int PRIMARY KEY, v blob)",
        "GRANT SELECT ON TABLE vks.kv TO victim",
        "GRANT MODIFY ON TABLE vks.kv TO victim",
    ]:
        ex(q)
for q in ["LIST ROLES", "LIST ALL PERMISSIONS OF attacker", "LIST ALL PERMISSIONS OF victim"]:
    ex(q)
cl.shutdown()
