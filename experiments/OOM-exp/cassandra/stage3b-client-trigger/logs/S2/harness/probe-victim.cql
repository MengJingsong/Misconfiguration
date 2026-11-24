# as victim (SELECT, MODIFY on vks.kv only)
SELECT k FROM vks.kv LIMIT 1
INSERT INTO b6.t_blob (pk, b) VALUES (-2, 0x00)
