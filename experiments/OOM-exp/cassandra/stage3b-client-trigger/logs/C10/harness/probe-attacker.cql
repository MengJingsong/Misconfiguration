# role 'attacker' (CREATE ON ALL KEYSPACES; owner of c10): isolation from the victim, tracing tables, system tables
SELECT k FROM vks.kv LIMIT 1
INSERT INTO vks.kv (k, v) VALUES (1, 0x00)
SELECT session_id FROM system_traces.sessions LIMIT 1
SELECT count(*) FROM system_traces.events LIMIT 1
SELECT peer, tokens FROM system.peers LIMIT 1
SELECT pk, b FROM c10.t LIMIT 2
GRANT SELECT ON TABLE vks.kv TO attacker
ALTER KEYSPACE vks WITH replication = {'class':'SimpleStrategy','replication_factor':1}
