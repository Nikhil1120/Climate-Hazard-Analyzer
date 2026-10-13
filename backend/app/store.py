"""NoSQL persistence.

Two collections (document model):
  weather_daily : one document per (cell, year) -> {cell, year, dates[], tmax[], tmin[], precip[], fetched_at, complete}
  analysis      : one document per parameter hash -> {_id, created_at, result}

MongoStore is used when MONGODB_URI is set (production / docker-compose).
FileStore is a zero-setup JSON document store with the same interface, for local dev.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional, Protocol


class Store(Protocol):
    def get_daily(self, cell: str, year: int) -> Optional[dict]: ...
    def put_daily(self, doc: dict) -> None: ...
    def get_analysis(self, key: str) -> Optional[dict]: ...
    def put_analysis(self, key: str, result: dict) -> None: ...
    def kind(self) -> str: ...


class MongoStore:
    def __init__(self, uri: str, db_name: str, client: Any = None):
        if client is None:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = client[db_name]
        self.daily = self.db["weather_daily"]
        self.analysis = self.db["analysis"]
        self.daily.create_index([("cell", 1), ("year", 1)], unique=True)

    def kind(self) -> str:
        return "mongodb"

    def get_daily(self, cell: str, year: int) -> Optional[dict]:
        return self.daily.find_one({"cell": cell, "year": year}, {"_id": 0})

    def put_daily(self, doc: dict) -> None:
        self.daily.replace_one({"cell": doc["cell"], "year": doc["year"]}, doc, upsert=True)

    def get_analysis(self, key: str) -> Optional[dict]:
        return self.analysis.find_one({"_id": key})

    def put_analysis(self, key: str, result: dict) -> None:
        self.analysis.replace_one({"_id": key}, {"_id": key, "created_at": time.time(), "result": result}, upsert=True)


class FileStore:
    """JSON-file document store: data/<collection>/<id>.json"""

    def __init__(self, root: Path):
        self.root = Path(root)
        (self.root / "weather_daily").mkdir(parents=True, exist_ok=True)
        (self.root / "analysis").mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def kind(self) -> str:
        return "file (local JSON document store)"

    def _path(self, coll: str, name: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        return self.root / coll / f"{safe}.json"

    def _read(self, p: Path) -> Optional[dict]:
        try:
            return json.loads(p.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _write(self, p: Path, doc: dict) -> None:
        tmp = p.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(json.dumps(doc))
            tmp.replace(p)

    def get_daily(self, cell: str, year: int) -> Optional[dict]:
        return self._read(self._path("weather_daily", f"{cell}_{year}"))

    def put_daily(self, doc: dict) -> None:
        self._write(self._path("weather_daily", f"{doc['cell']}_{doc['year']}"), doc)

    def get_analysis(self, key: str) -> Optional[dict]:
        return self._read(self._path("analysis", key))

    def put_analysis(self, key: str, result: dict) -> None:
        self._write(self._path("analysis", key), {"_id": key, "created_at": time.time(), "result": result})


def make_store() -> Store:
    from . import config

    if config.MONGODB_URI:
        return MongoStore(config.MONGODB_URI, config.MONGODB_DB)
    return FileStore(config.DATA_DIR)
