import sys, os, glob, time
CH = os.environ['CASSANDRA_HOME']
z = glob.glob(CH + '/lib/cassandra-driver-internal-only-*.zip')
if z:
    ver = os.path.basename(z[0])[len('cassandra-driver-internal-only-'):-4]
    sys.path.insert(0, os.path.join(z[0], 'cassandra-driver-' + ver))
    for p in glob.glob(CH + '/lib/*.zip'):
        if p != z[0]: sys.path.insert(1, p)
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from cassandra import ConsistencyLevel
s = Cluster(['127.0.0.1'], port=int(os.environ.get('CQLPORT', '9042'))).connect()
if sys.argv[1] == 'load':
    s.execute("CREATE KEYSPACE IF NOT EXISTS dob WITH replication={'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS dob.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression={'enabled':false}")
    ins = s.prepare("INSERT INTO dob.t (pk, ck, v) VALUES (0, ?, ?)")
    for ck in range(200):
        s.execute(ins, (ck, os.urandom(1048576)))
    print('loaded', s.execute("SELECT count(*) FROM dob.t WHERE pk=0").one())
else:  # read <fetch_size or 0> <repeats>
    fs = int(sys.argv[2]); reps = int(sys.argv[3])
    for i in range(reps):
        st = SimpleStatement("SELECT max(v) FROM dob.t WHERE pk=0", consistency_level=ConsistencyLevel.ONE,
                             fetch_size=(fs if fs > 0 else None))
        t0 = time.time(); r = s.execute(st, timeout=120).one()
        print('read', i, 'fetch', fs, 'len', len(r[0]), 'secs', round(time.time() - t0, 2)); time.sleep(5)
