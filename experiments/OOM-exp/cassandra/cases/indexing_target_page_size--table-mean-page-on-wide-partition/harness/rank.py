#!/usr/bin/env python3
"""B20: rank of pk = 0 in token order among pk = 0..1,000,000 (offline; Murmur3 of the 8-byte big-endian bigint)."""
import glob, os, struct, sys
CASS = os.environ["CASSANDRA_HOME"]
z = max(glob.glob(os.path.join(CASS, "lib", "cassandra-driver-internal-only-*.zip")))
ver = os.path.splitext(os.path.basename(z))[0][len("cassandra-driver-internal-only-"):]
sys.path.insert(0, os.path.join(z, "cassandra-driver-" + ver))
from cassandra.metadata import Murmur3Token
h = lambda pk: Murmur3Token.hash_fn(struct.pack(">q", pk))
t0 = h(0)
below = sum(1 for pk in range(1, 1000001) if h(pk) < t0)
print(f"token(0)={t0} small_partitions_before_pk0={below} of 1000000 ({100*below/1e6:.2f}%)")
