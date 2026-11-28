import http.client
import json
import threading
import unittest

from dossier_service.http_server import Server
from dossier_service.store import Store
from tests.test_store import FIXTURE, build_fn


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store(build_fn)
        cls.server = Server(("127.0.0.1", 0), cls.store)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.store.reset(FIXTURE)
        self.conn = http.client.HTTPConnection("127.0.0.1", self.port)
        self.conn.request("POST", "/auth/login", json.dumps({"email": "ada@example.com", "password": "correct horse"}))
        self.token = json.loads(self.conn.getresponse().read())["token"]

    def tearDown(self):
        self.conn.close()

    def call(self, method, path, body=None, headers=None, **kw):
        self.conn.request(method, path, body, {"Authorization": "Bearer " + self.token, **(headers or {})}, **kw)
        response = self.conn.getresponse()
        raw = response.read()
        return response.status, (json.loads(raw) if raw else None)

    def raw(self, path, headers=None):
        self.conn.request("GET", path, headers=headers or {})
        response = self.conn.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()

    def test_browser_routes_serve_the_ui(self):
        for path in ("/", "/login", "/signup", "/contested", "/dossiers/acme.test/evidence"):
            with self.subTest(path=path):
                status, kind, body = self.raw(path)
                self.assertEqual((status, kind), (200, "text/html; charset=utf-8"))
                self.assertIn(b'id="app"', body)
        for asset, kind in (("app.js", "text/javascript"), ("app.css", "text/css")):
            self.assertEqual(self.raw("/static/" + asset)[:2], (200, kind + "; charset=utf-8"))
        self.assertEqual(self.raw("/static/../store.py")[0], 404)

    def test_dossier_path_is_ui_for_html_and_api_otherwise(self):
        self.call("POST", "/dossiers", '{"domain":"acme.test"}', {"Idempotency-Key": "k"})
        status, kind, body = self.raw("/dossiers/acme.test", {"Accept": "text/html,application/xhtml+xml"})
        self.assertEqual((status, kind), (200, "text/html; charset=utf-8"))
        status, kind, body = self.raw("/dossiers/acme.test", {"Authorization": "Bearer " + self.token})
        self.assertEqual((status, kind), (200, "application/json; charset=utf-8"))
        self.assertEqual(json.loads(body)["fields"]["ceo"]["candidates"][0]["selected"], True)
        self.assertEqual(self.raw("/dossiers/acme.test")[0], 401)

    def test_chunked_body(self):
        chunks = iter([b'{"domain":', b'"chunked.test"}'])
        status, body = self.call("POST", "/dossiers", chunks, {"Idempotency-Key": "k"}, encode_chunked=True)
        self.assertEqual((status, body["domain"]), (202, "chunked.test"))

    def test_refused_request_leaves_connection_in_step(self):
        self.conn.request("POST", "/dossiers", '{"domain":"a.test"}', {"Idempotency-Key": "k"})   # 401: no token
        response = self.conn.getresponse()
        response.read()
        self.assertEqual(response.status, 401)
        self.assertEqual(self.call("GET", "/dossiers")[0], 200)

    def test_wrong_method_is_not_found(self):
        status, body = self.call("PUT", "/health")
        self.assertEqual((status, body["error"]["code"]), (404, "not_found"))

    def test_empty_or_non_object_body_is_malformed(self):
        for path in ("/_test/import", "/_test/reset", "/_test/clock", "/auth/signup", "/auth/login", "/dossiers"):
            for body in ("", "  \n", "[]", "null"):
                with self.subTest(path=path, body=body):
                    status, error = self.call("POST", path, body, {"Idempotency-Key": "k"})
                    self.assertEqual((status, error["error"]["code"]), (400, "malformed_request"))

    def test_null_required_field_is_wrong_type(self):
        for path, body in (("/dossiers", {"domain": None}), ("/_test/clock", {"now": None}),
                           ("/auth/login", {"email": None, "password": "x"})):
            with self.subTest(path=path):
                status, error = self.call("POST", path, json.dumps(body), {"Idempotency-Key": "k"})
                self.assertEqual((status, error["error"]["code"]), (400, "malformed_request"))
        status, error = self.call("POST", "/dossiers", "{}", {"Idempotency-Key": "k"})
        self.assertEqual((status, error["error"]["code"]), (422, "validation_failed"))

    def test_unauthenticated_empty_body_is_401(self):
        self.conn.request("POST", "/dossiers", "", {"Idempotency-Key": "k"})
        response = self.conn.getresponse()
        response.read()
        self.assertEqual(response.status, 401)

    def test_refresh_ignores_its_body(self):
        self.call("POST", "/dossiers", '{"domain":"acme.test"}', {"Idempotency-Key": "a"})
        status, body = self.call("POST", "/dossiers/acme.test/refresh", "not json", {"Idempotency-Key": "b"})
        self.assertEqual((status, body["domain"]), (202, "acme.test"))


if __name__ == "__main__":
    unittest.main()
