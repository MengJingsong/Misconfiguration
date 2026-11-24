# superuser: data-role variant. An admin-made keyspace at RF 2 on the 3-node ring (N > RF), and a role with only
# SELECT + MODIFY on its table (it cannot create anything).
CREATE KEYSPACE adm WITH replication = {'class':'SimpleStrategy','replication_factor':2}
CREATE TABLE adm.t (pk bigint PRIMARY KEY, b int, v blob)
CREATE ROLE dataatk WITH PASSWORD = 'dat-pw' AND LOGIN = true AND SUPERUSER = false
GRANT SELECT ON TABLE adm.t TO dataatk
GRANT MODIFY ON TABLE adm.t TO dataatk
LIST ALL PERMISSIONS OF dataatk
