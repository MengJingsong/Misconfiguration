# role 'attacker': SELECT + MODIFY on b29.t only (data role). What it can and cannot do.
SELECT broadcast_address, tokens FROM system.local
SELECT peer, tokens FROM system.peers
CREATE KEYSPACE probe_att WITH replication = {'class':'SimpleStrategy','replication_factor':1}
CREATE TABLE b29.probe (k int PRIMARY KEY)
ALTER TABLE b29.t WITH gc_grace_seconds = 0
CREATE INDEX ON b29.t (pad)
SELECT k FROM vks.kv LIMIT 1
SELECT * FROM b29.t WHERE k = 1005 AND s = 'x' ALLOW FILTERING
SELECT k, s FROM b29.t WHERE k = 1005 AND s = 'x'
SELECT session_id FROM system_traces.sessions LIMIT 1
