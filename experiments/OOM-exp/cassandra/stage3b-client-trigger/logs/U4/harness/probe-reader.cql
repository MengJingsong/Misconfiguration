-- SELECT-only role: read allowed, writes refused
INSERT INTO u4.t (pk, ck, v) VALUES (99, 0, 0x00);
SELECT pk, ck FROM u4.t WHERE pk = 0 LIMIT 1;
