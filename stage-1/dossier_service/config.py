"""Runtime configuration, read from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

LIVE_NIMBLE_HOST = "sdk.nimbleway.com"
BUILD_BUDGET_UNITS = 80


@dataclass(frozen=True)
class Settings:
    port: int
    live: bool                  # talking to the real Nimble, whose calls can take a minute
    call_timeout: float         # seconds one search or extract may wait
    research_timeout: float     # seconds a research run may be waited for
    gather_window: float        # no new provider call starts after this many seconds of a build
    research_start_limit: float # nor a research run, which needs the most time
    hard_limit: float           # a build is over by this many seconds, whatever is outstanding

    @classmethod
    def from_env(cls) -> "Settings":
        base_url = os.environ.get("NIMBLE_BASE_URL")
        host = (urlparse(base_url).hostname or "") if base_url else LIVE_NIMBLE_HOST
        live = host == LIVE_NIMBLE_HOST
        if live:
            return cls(_port(), True, call_timeout=45.0, research_timeout=150.0,
                       gather_window=200.0, research_start_limit=130.0, hard_limit=285.0)
        return cls(_port(), False, call_timeout=12.0, research_timeout=12.0,
                   gather_window=60.0, research_start_limit=60.0, hard_limit=90.0)


def _port() -> int:
    return int(os.environ.get("PORT", "8080"))
