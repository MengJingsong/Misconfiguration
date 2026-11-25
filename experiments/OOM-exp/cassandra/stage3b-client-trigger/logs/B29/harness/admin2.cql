# superuser: roles, the admin-made schema (keyspace b29 RF 2, a table with a static column), the only GRANTs, the victim's schema
CREATE ROLE attacker WITH PASSWORD = 'att-pw' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE victim WITH PASSWORD = 'vic-pw' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE nogrant WITH PASSWORD = 'nog-pw' AND LOGIN = true AND SUPERUSER = false
CREATE KEYSPACE b29 WITH replication = {'class':'SimpleStrategy','replication_factor':2}
CREATE TABLE b29.t (k int, c int, s text STATIC, pad blob, PRIMARY KEY (k, c))
GRANT SELECT ON TABLE b29.t TO attacker
GRANT MODIFY ON TABLE b29.t TO attacker
CREATE KEYSPACE vks WITH replication = {'class':'SimpleStrategy','replication_factor':2}
CREATE TABLE vks.kv (k int PRIMARY KEY, v blob)
GRANT SELECT ON TABLE vks.kv TO victim
GRANT MODIFY ON TABLE vks.kv TO victim
LIST ROLES
LIST ALL PERMISSIONS OF attacker
LIST ALL PERMISSIONS OF victim
LIST ALL PERMISSIONS OF nogrant
