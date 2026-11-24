# role 'nogrant': LOGIN only, no GRANT at all
SELECT broadcast_address, tokens FROM system.local
SELECT peer, tokens FROM system.peers
SELECT peer, tokens FROM system.peers_v2
CREATE KEYSPACE probe_ng WITH replication = {'class':'SimpleStrategy','replication_factor':1}
SELECT pk FROM c10.t LIMIT 1
SELECT * FROM c10.t WHERE b = 1 LIMIT 1 ALLOW FILTERING
SELECT k FROM vks.kv LIMIT 1
SELECT session_id FROM system_traces.sessions LIMIT 1
