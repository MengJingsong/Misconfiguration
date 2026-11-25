-- 3-b R24 probes as selonly (SELECT on r24.w2k only)
LIST ALL PERMISSIONS OF selonly;
INSERT INTO r24.w2k (k, c, v, pad) VALUES (5, 0, 'x', 0x00);
SELECT k, c, v FROM r24.w2k LIMIT 1;
