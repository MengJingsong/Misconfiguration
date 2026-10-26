"""Deterministic data for the cluster tier (B3c, amended): 80,500 rows, grp 1..4 with 500 / 10000 / 20000 / 50000 rows, vector<float,16>."""
import random
N_BY_GRP = {1: 500, 2: 10000, 3: 20000, 4: 50000}
N = sum(N_BY_GRP.values())   # 80500
DIM = 16
SEED = 20261026
def rows():
    rnd = random.Random(SEED)
    grps = [g for g, n in N_BY_GRP.items() for _ in range(n)]
    rnd.shuffle(grps)
    return [(pk, grps[pk], [rnd.uniform(-1, 1) for _ in range(DIM)]) for pk in range(N)]
def query_vec(i=0):
    rnd = random.Random(SEED + 1 + i)
    return [rnd.uniform(-1, 1) for _ in range(DIM)]
def lit(v):
    return '[' + ', '.join(repr(round(x, 6)) for x in v) + ']'
