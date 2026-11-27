"""Composition root: the store, the WebRouter and the build function that joins them."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .builder import Builder, BuildResult
from .config import BUILD_BUDGET_UNITS, Settings
from .gateway import Gateway, make_router
from .ledger import Ledger
from .store import Store

CALL_WORKERS = 32


def create_store(settings: Settings) -> Store:
    router = make_router()
    pool = ThreadPoolExecutor(max_workers=CALL_WORKERS, thread_name_prefix="provider-call")

    def build(domain, on_spend, stop) -> BuildResult:
        ledger = Ledger(BUILD_BUDGET_UNITS, on_spend)
        return Builder(domain, Gateway(router, settings, ledger, stop), pool).run()

    return Store(build)
