CREATE KEYSPACE IF NOT EXISTS kvstore
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE kvstore;

CREATE TABLE IF NOT EXISTS kv (
  key text PRIMARY KEY,
  value text
);


COPY kv (key, value)
FROM 'kv_1000000.csv'
WITH HEADER = TRUE;
