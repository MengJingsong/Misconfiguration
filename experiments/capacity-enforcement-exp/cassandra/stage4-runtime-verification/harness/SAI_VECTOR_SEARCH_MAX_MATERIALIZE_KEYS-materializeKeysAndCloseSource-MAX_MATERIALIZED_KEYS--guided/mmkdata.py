"""Shared data definitions for load.py and query.py (case 9b, amended 2026-10-15). Vectors are rounded to float32 (as stored)
before any similarity is computed, so the rank order of ks.far is the order of the stored vectors."""
import math, random, struct

DIM = 8
N_T, N_FAR, M_FAR = 200000, 50000, 16001
SEED_T_VEC, SEED_T_ORDER = 101, 102
SEED_FAR_VEC, SEED_FAR_ORDER = 201, 202
SEED_Q = 301


def f32(x):
    return struct.unpack('f', struct.pack('f', x))[0]


def gaussian_vecs(seed, n):
    r = random.Random(seed)
    return [[f32(r.gauss(0.0, 1.0)) for _ in range(DIM)] for _ in range(n)]


def query_vector():
    return gaussian_vecs(SEED_Q, 1)[0]


def cosine(a, b):
    ab = sum(x * y for x, y in zip(a, b))
    return ab / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def t_rows():
    """[(pk, vector)] for ks.t, pk = i = 1..N, in the seeded insertion order"""
    v = gaussian_vecs(SEED_T_VEC, N_T)
    order = list(range(1, N_T + 1))
    random.Random(SEED_T_ORDER).shuffle(order)
    return [(pk, v[pk - 1]) for pk in order]


def far_rows():
    """[(pk, vector)] for ks.far: pk = i = rank by cosine similarity to q, ascending (1 = least similar), seeded insertion order"""
    q = query_vector()
    v = gaussian_vecs(SEED_FAR_VEC, N_FAR)
    v.sort(key=lambda x: cosine(x, q))
    order = list(range(1, N_FAR + 1))
    random.Random(SEED_FAR_ORDER).shuffle(order)
    return [(pk, v[pk - 1]) for pk in order]


def vec_literal(v):
    return '[' + ', '.join(repr(x) for x in v) + ']'
