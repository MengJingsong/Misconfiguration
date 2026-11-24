# 3-b confirm U8: everything the superuser (cassandra) does before the attack. Roles, grants, the victim's own schema.
CREATE ROLE IF NOT EXISTS u8atk WITH PASSWORD = 'atk-3bU8' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE IF NOT EXISTS u8victim WITH PASSWORD = 'vic-3bU8' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE IF NOT EXISTS u8nogrant WITH PASSWORD = 'nog-3bU8' AND LOGIN = true AND SUPERUSER = false
GRANT CREATE ON ALL KEYSPACES TO u8atk
CREATE KEYSPACE IF NOT EXISTS victimks WITH replication = {'class':'SimpleStrategy','replication_factor':1}
CREATE TABLE IF NOT EXISTS victimks.kv (k int PRIMARY KEY, v blob)
GRANT SELECT ON TABLE victimks.kv TO u8victim
GRANT MODIFY ON TABLE victimks.kv TO u8victim
LIST ROLES
LIST ALL PERMISSIONS OF u8atk
LIST ALL PERMISSIONS OF u8victim
LIST ALL PERMISSIONS OF u8nogrant
SELECT name, value FROM system_views.settings
