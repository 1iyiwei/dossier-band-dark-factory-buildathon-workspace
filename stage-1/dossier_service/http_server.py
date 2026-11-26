"""The HTTP surface: routing, request parsing, error bodies. Business rules live in the store."""
from __future__ import annotations

import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from .clock import parse_timestamp
from .domains import parse_domain
from .errors import ApiError, malformed, validation_failed
from .store import Store

log = logging.getLogger("dossier.http")

MAX_KEY_LENGTH = 255
_DIGITS = re.compile(r"[0-9]+")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")


class Server(ThreadingHTTPServer):
    request_queue_size = 256
    daemon_threads = True

    def __init__(self, address, store: Store) -> None:
        super().__init__(address, Handler)
        self.store = store


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30
    server: Server

    def log_message(self, *args) -> None:
        pass

    # ------------------------------------------------------------ plumbing

    def _send(self, status: int, payload=None) -> None:
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _raw_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise malformed("bad Content-Length") from None
        return self.rfile.read(length) if length > 0 else b""

    def _json_object(self) -> dict:
        """The JSON object in the body ({} when there is no body)."""
        raw = self._raw_body()
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise malformed("body is not valid JSON") from None
        if not isinstance(parsed, dict):
            raise malformed("body must be a JSON object")
        return parsed

    def _user_id(self) -> str:
        parts = (self.headers.get("Authorization") or "").split()
        token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else None
        return self.server.store.authenticate(token)

    def _idempotency_key(self) -> str:
        key = self.headers.get("Idempotency-Key")
        if not key:
            raise ApiError(400, "missing_idempotency_key", "Idempotency-Key header is required")
        return key

    @staticmethod
    def _check_key_length(key: str) -> None:
        if len(key) > MAX_KEY_LENGTH:
            raise validation_failed("Idempotency-Key must be 1 to 255 characters")

    # ------------------------------------------------------------ dispatch

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        try:
            status, payload = self._route(method, urlsplit(self.path))
        except ApiError as error:
            status, payload = error.status, {"error": {"code": error.code, "message": error.message}}
        except Exception:   # noqa: BLE001 - never let a bug surface as a dropped connection
            log.exception("unhandled error")
            status, payload = 500, {"error": {"code": "internal_error", "message": "internal error"}}
        self._send(status, payload)

    def _route(self, method: str, url) -> tuple[int, dict | None]:
        path = url.path
        simple = {
            ("GET", "/health"): self._health,
            ("POST", "/_test/reset"): self._reset,
            ("POST", "/_test/clock"): self._set_clock,
            ("GET", "/_test/export"): self._export,
            ("POST", "/_test/import"): self._import,
            ("POST", "/auth/signup"): self._signup,
            ("POST", "/auth/login"): self._login,
            ("POST", "/dossiers"): self._create_dossier,
            ("GET", "/dossiers"): lambda: self._list_dossiers(url.query),
        }
        handler = simple.get((method, path.rstrip("/") or "/"))
        if handler is not None:
            return handler()
        if path.startswith("/dossiers/") and len(path) > len("/dossiers/"):
            rest = path[len("/dossiers/"):]
            if method == "GET":
                return self._get_dossier(unquote(rest))
            if method == "POST" and rest.endswith("/refresh"):
                return self._refresh_dossier(path, unquote(rest[:-len("/refresh")]))
        known = ("/health", "/auth/", "/dossiers", "/_test/")
        if path.startswith(known):
            raise ApiError(405, "method_not_allowed", "method not allowed for this path")
        raise ApiError(404, "not_found", "no such route")

    # ------------------------------------------------------------ control endpoints

    def _health(self):
        return 200, {"status": "ok"}

    def _reset(self):
        self.server.store.reset(self._json_object())
        return 204, None

    def _set_clock(self):
        body = self._json_object()
        now = body.get("now")
        if now is None:
            raise validation_failed("now is required")
        if not isinstance(now, str):
            raise malformed("now must be a string")
        self.server.store.clock.advance_to(parse_timestamp(now))
        return 204, None

    def _export(self):
        return 200, self.server.store.export_state()

    def _import(self):
        self.server.store.import_state(self._json_object())
        return 204, None

    # ------------------------------------------------------------ auth endpoints

    def _credentials(self, *names: str) -> list[str]:
        body = self._json_object()
        values = []
        for name in names:
            value = body.get(name)
            if value is None:
                raise validation_failed(f"{name} is required")
            if not isinstance(value, str):
                raise malformed(f"{name} must be a string")
            values.append(value)
        return values

    def _signup(self):
        email, password, display_name = self._credentials("email", "password", "display_name")
        if not _EMAIL.fullmatch(email):
            raise validation_failed("email must look like local@domain")
        if len(password) < 8:
            raise validation_failed("password must be at least 8 characters")
        if not 1 <= len(display_name) <= 100:
            raise validation_failed("display_name must be 1 to 100 characters")
        return 201, self.server.store.signup(email, password, display_name)

    def _login(self):
        email, password = self._credentials("email", "password")
        return 200, self.server.store.login(email, password)

    # ------------------------------------------------------------ dossier endpoints

    def _create_dossier(self):
        user_id = self._user_id()
        key = self._idempotency_key()
        body = self._json_object()
        self._check_key_length(key)
        store = self.server.store

        def action():
            domain = body.get("domain")
            if domain is None:
                raise validation_failed("domain is required")
            if not isinstance(domain, str):
                raise malformed("domain must be a string")
            normalised = parse_domain(domain)
            if normalised is None:
                raise validation_failed("domain is not a valid host name")
            return store.start_dossier(normalised)

        fingerprint = json.dumps({"domain": body["domain"]} if "domain" in body else {}, sort_keys=True)
        return store.idempotent(user_id, "POST", urlsplit(self.path).path, key, fingerprint, action)

    def _refresh_dossier(self, raw_path: str, raw_domain: str):
        user_id = self._user_id()
        key = self._idempotency_key()
        self._check_key_length(key)
        store = self.server.store

        def action():
            domain = parse_domain(raw_domain)
            if domain is None:
                raise validation_failed("domain is not a valid host name")
            return store.refresh_dossier(domain)

        return store.idempotent(user_id, "POST", raw_path, key, "", action)

    def _get_dossier(self, raw_domain: str):
        self._user_id()
        domain = parse_domain(raw_domain)
        if domain is None:
            raise validation_failed("domain is not a valid host name")
        return 200, self.server.store.get_dossier(domain)

    def _list_dossiers(self, query: str):
        self._user_id()
        params = parse_qs(query, keep_blank_values=True)
        limit = _int_param(params, "limit", 50, 1, 200)
        offset = _int_param(params, "offset", 0, 0, None)
        q = params.get("q", [""])[0]
        return 200, self.server.store.list_dossiers(q, limit, offset)


def _int_param(params: dict, name: str, default: int, low: int, high: int | None) -> int:
    if name not in params:
        return default
    text = params[name][0]
    if not _DIGITS.fullmatch(text):
        raise validation_failed(f"{name} must be written as plain decimal digits")
    value = int(text)
    if value < low or (high is not None and value > high):
        raise validation_failed(f"{name} is out of range")
    return value
