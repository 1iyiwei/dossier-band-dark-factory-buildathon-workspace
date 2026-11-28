"""Composition root: the store, the WebRouter and the build function that joins them."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from .builder import Builder, BuildResult
from .config import Settings
from .gateway import Gateway, make_router
from .persistence import Journal
from .store import Store

CALL_WORKERS = 32
JOURNAL_FILE = "state.journal"


def create_store(settings: Settings) -> Store:
    router = make_router()
    pool = ThreadPoolExecutor(max_workers=CALL_WORKERS, thread_name_prefix="provider-call")

    def build(domain, ledger, stop) -> BuildResult:
        return Builder(domain, Gateway(router, settings, ledger, stop), pool).run()

    return Store(build, Journal(os.path.join(settings.data_dir, JOURNAL_FILE)) if settings.data_dir else None)
