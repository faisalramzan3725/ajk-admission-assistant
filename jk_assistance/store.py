"""Tiny JSON-file persistence for students, applications, events and the escalation queue.

Swap for a real database in production; the interface (load/save/upsert/list) is all the rest of the code uses.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from .config import DATA_DIR

_LOCK = threading.Lock()
COLLECTIONS = ("students", "applications", "events", "escalations")


def _path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


def load(name: str) -> list[dict]:
    p = _path(name)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save(name: str, rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(name).with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(_path(name))


def get(name: str, row_id: str) -> dict | None:
    return next((r for r in load(name) if r.get("id") == row_id), None)


def upsert(name: str, row: dict) -> dict:
    with _LOCK:
        rows = load(name)
        for i, r in enumerate(rows):
            if r.get("id") == row["id"]:
                rows[i] = row
                break
        else:
            rows.append(row)
        save(name, rows)
    return row


def append(name: str, row: dict) -> dict:
    with _LOCK:
        rows = load(name)
        rows.append(row)
        save(name, rows)
    return row


def next_id(name: str, prefix: str) -> str:
    rows = load(name)
    return f"{prefix}-{len(rows) + 1:04d}"
