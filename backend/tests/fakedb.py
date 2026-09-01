"""Shared fake async Mongo for the Asha test suites."""


class UpdateResult:
    """Mirrors motor's UpdateResult surface used by the engine."""
    def __init__(self, matched, modified, upserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted_id
# ─────────────────────────── fake async mongo ────────────────────────────
def _match(doc, flt):
    for k, cond in flt.items():
        cur = doc
        for part in k.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if isinstance(cond, dict):
            if "$in" in cond and cur not in cond["$in"]:
                return False
            if "$lt" in cond and not (cur is not None and cur < cond["$lt"]):
                return False
            if "$gt" in cond and not (cur is not None and cur > cond["$gt"]):
                return False
            if "$lte" in cond and not (cur is not None and cur <= cond["$lte"]):
                return False
            if "$gte" in cond and not (cur is not None and cur >= cond["$gte"]):
                return False
            if "$ne" in cond and cur == cond["$ne"]:
                return False
        elif cur != cond:
            return False
    return True


def _set_path(doc, path, value):
    parts = path.split(".")
    cur = doc
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, flt, projection=None):
        for d in self.docs:
            if _match(d, flt):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def count_documents(self, flt):
        return sum(1 for d in self.docs if _match(d, flt))

    async def update_one(self, flt, update, upsert=False):
        target = next((d for d in self.docs if _match(d, flt)), None)
        upserted = None
        if target is None:
            if not upsert:
                return UpdateResult(0, 0)
            target = {k: v for k, v in flt.items() if not isinstance(v, dict)}
            for k, v in (update.get("$setOnInsert") or {}).items():
                _set_path(target, k, v)
            self.docs.append(target)
            upserted = target.get("id", True)
        for k, v in (update.get("$set") or {}).items():
            _set_path(target, k, v)
        for k, v in (update.get("$inc") or {}).items():
            parts = k.split(".")
            cur = target
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = cur.get(parts[-1], 0) + v
        for k, v in (update.get("$push") or {}).items():
            parts = k.split(".")
            cur = target
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur.setdefault(parts[-1], []).append(v)
        return UpdateResult(1, 1, upserted)


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        if isinstance(key, list):
            key, direction = key[0]
        self._docs.sort(key=lambda d: (d.get(key) is None, d.get(key)),
                        reverse=(direction == -1))
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length=None):
        return [dict(d) for d in (self._docs if length is None else self._docs[:length])]


def _find(self, flt=None, projection=None):
    return FakeCursor([d for d in self.docs if _match(d, flt or {})])

FakeCollection.find = _find


class FakeDB:
    def __init__(self):
        self._cols = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._cols.setdefault(name, FakeCollection())

    def __getitem__(self, name):
        return getattr(self, name)
