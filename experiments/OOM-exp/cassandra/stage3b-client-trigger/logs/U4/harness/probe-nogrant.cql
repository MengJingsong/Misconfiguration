-- login role, no grants: the attack read and writes refused
SELECT pk, ck FROM u4.t WHERE pk = 0 LIMIT 1;
INSERT INTO u4.t (pk, ck, v) VALUES (99, 0, 0x00);
SELECT release_version FROM system.local;
