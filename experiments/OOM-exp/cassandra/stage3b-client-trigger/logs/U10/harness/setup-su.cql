# 3-b confirm U10: everything the superuser (cassandra) does before the attack: two roles, the admin-made schema the data
# role is granted on (the case's table, unchanged), the victim's own keyspace/table, the grants, read-backs.
CREATE ROLE IF NOT EXISTS u10atk WITH PASSWORD = 'atk-3bU10' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE IF NOT EXISTS u10victim WITH PASSWORD = 'vic-3bU10' AND LOGIN = true AND SUPERUSER = false
CREATE KEYSPACE IF NOT EXISTS u10 WITH replication = {'class':'SimpleStrategy','replication_factor':1}
CREATE TABLE IF NOT EXISTS u10.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))
GRANT SELECT ON TABLE u10.t TO u10atk
GRANT MODIFY ON TABLE u10.t TO u10atk
CREATE KEYSPACE IF NOT EXISTS victimks WITH replication = {'class':'SimpleStrategy','replication_factor':1}
CREATE TABLE IF NOT EXISTS victimks.kv (k int PRIMARY KEY, v blob)
GRANT SELECT ON TABLE victimks.kv TO u10victim
GRANT MODIFY ON TABLE victimks.kv TO u10victim
LIST ROLES
LIST ALL PERMISSIONS OF u10atk
LIST ALL PERMISSIONS OF u10victim
SELECT name, value FROM system_views.settings
