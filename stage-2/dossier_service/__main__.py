"""Entry point: ``python -m dossier_service``."""
import logging

from .config import Settings
from .http_server import Server
from .service import create_store


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings.from_env()
    server = Server(("0.0.0.0", settings.port), create_store(settings))
    logging.getLogger("dossier").info("listening on 0.0.0.0:%d (live=%s)", settings.port, settings.live)
    server.serve_forever()


if __name__ == "__main__":
    main()
