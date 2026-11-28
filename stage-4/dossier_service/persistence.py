"""A durable append-only journal of the service's state, so it survives an abrupt stop.

The file holds one JSON document per line. The first line is a snapshot of all state; every later
line is one batch of records, written and flushed to disk before the request that made the change
is answered. A batch is one line, so a stop in the middle of a write leaves at most a torn last
line, which the next start ignores: the request it belonged to was never answered. The file is
rewritten as a single snapshot, atomically, at every start and whenever it has grown large.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("dossier.persistence")

COMPACT_BYTES = 32 * 1024 * 1024


class Journal:
    def __init__(self, path: str) -> None:
        self.path = path
        self._handle = None
        self.size = 0

    def load(self) -> tuple[dict | None, list[list]]:
        """The snapshot and the batches written after it; a torn or unreadable line ends the reading."""
        try:
            with open(self.path, "rb") as handle:
                data = handle.read()
        except FileNotFoundError:
            return None, []
        snapshot, batches = None, []
        for line in data.split(b"\n")[:-1]:      # the part after the last newline was never completed
            try:
                document = json.loads(line)
            except ValueError:
                log.warning("ignoring an unreadable journal line and what follows it")
                break
            if snapshot is None:
                snapshot = document["snapshot"]
            else:
                batches.append(document["records"])
        return snapshot, batches

    def rewrite(self, snapshot: dict) -> None:
        """Atomically replace the journal by a single snapshot."""
        self._close()
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        temporary = self.path + ".tmp"
        line = _line({"snapshot": snapshot})
        with open(temporary, "wb") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        _sync_directory(directory)
        self.size = len(line)
        self._handle = open(self.path, "ab")

    def append(self, records: list, sync: bool = True) -> None:
        """Write one batch of records. It is forced to disk unless ``sync`` is off; it is then in the operating
        system's hands, which is enough to survive the process being killed."""
        line = _line({"records": records})
        self._handle.write(line)
        self._handle.flush()
        if sync:
            os.fsync(self._handle.fileno())
        self.size += len(line)

    def _close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _line(document: dict) -> bytes:
    return json.dumps(document, separators=(",", ":")).encode("utf-8") + b"\n"


def _sync_directory(directory: str) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
