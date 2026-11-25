"""Deterministic option shuffle shared with js/text.js (displayOrder): FNV-1a 32-bit hash of
"<unitId>/<questionId>" seeds mulberry32, then Fisher-Yates. The app, the print sheet and its key,
and the blind/AI-student files all show options in this order."""
M = 0xFFFFFFFF


def _imul(a, b):
    return (a * b) & M


def fnv1a(s):
    h = 0x811C9DC5
    for ch in [ord(c) for c in s]:
        h ^= ch & 0xFFFF
        h = _imul(h, 0x01000193)
    return h


def mulberry32(seed):
    a = seed & M

    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & M
        t = a
        t = _imul(t ^ (t >> 15), t | 1)
        t ^= (t + _imul(t ^ (t >> 7), t | 61)) & M
        return ((t ^ (t >> 14)) & M) / 4294967296
    return rnd


def display_order(unit_id, q):
    n = len(q["options"])
    idx = list(range(n))
    rnd = mulberry32(fnv1a(f"{unit_id}/{q['id']}"))
    for i in range(n - 1, 0, -1):
        j = int(rnd() * (i + 1))
        idx[i], idx[j] = idx[j], idx[i]
    return idx
