-- 3-b R24 probes as nogrant (login role, no grants)
LIST ALL PERMISSIONS OF nogrant;
SELECT k, c, v FROM r24.w2k WHERE v = 'x' LIMIT 1 ALLOW FILTERING;
INSERT INTO r24.w2k (k, c, v, pad) VALUES (5, 0, 'x', 0x00);
CREATE KEYSPACE ng WITH replication = {'class':'SimpleStrategy','replication_factor':1};
SELECT keyspace_name, replication FROM system_schema.keyspaces WHERE keyspace_name = 'system_traces';
SELECT session_id FROM system_traces.sessions LIMIT 1;
SELECT session_id FROM system_traces.events LIMIT 1;
INSERT INTO system_traces.events (session_id, event_id, activity) VALUES (uuid(), now(), 'probe');
INSERT INTO system_traces.sessions (session_id, request) VALUES (uuid(), 'probe');
SELECT session_id, activity FROM system_traces.events WHERE activity = 'x' ALLOW FILTERING;
