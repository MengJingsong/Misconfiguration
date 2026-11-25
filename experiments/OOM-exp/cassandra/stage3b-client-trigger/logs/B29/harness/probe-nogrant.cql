# role 'nogrant': LOGIN only, no GRANT at all
SELECT broadcast_address FROM system.local
SELECT * FROM b29.t WHERE k = 1005 AND s = 'x' ALLOW FILTERING
UPDATE b29.t SET s = 'x' WHERE k = 1005
DELETE FROM b29.t WHERE k = 1005
