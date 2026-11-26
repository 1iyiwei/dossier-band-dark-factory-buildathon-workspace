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


if __name__ == "__main__":
    unittest.main()
