"""Exercise the browser boundary against a real loopback HTTP server."""

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from tests.model_double import TemplateModel
from hissatech.web import DashboardServer


class WebTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.server = DashboardServer(0, Path(folder.name) / "web.sqlite3", TemplateModel(), "test-double")
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def call(self, path, role="customer_service", body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        supplied = {"X-Demo-Role": role, "X-Demo-Token": self.server.token, "Content-Type": "application/json"}
        supplied.update(headers or {})
        try:
            connection.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, supplied)
            reply = connection.getresponse()
            return reply.status, json.loads(reply.read())
        finally:
            connection.close()

    def test_request_inspection_approval_and_history_use_the_existing_service(self):
        body = {"request_id": "browser-s01", "text": "draft a ticket for S01"}
        status, response = self.call("/api/requests", body=body)
        self.assertEqual(status, 200)
        self.assertEqual(response["action_status"], "pending_approval")
        proposal = response["proposed_action"]
        path = "/api/proposals/" + proposal["proposal_id"]
        self.assertEqual(self.call(path)[0], 403)
        self.assertEqual(self.call("/api/requests/browser-s01", role="marketing")[0], 403)
        self.assertEqual(self.call("/api/requests/browser-s01")[1], response)
        self.assertEqual(self.call("/api/history", role="marketing")[1], [])
        self.assertEqual(len(self.call("/api/history", role="ops_reviewer")[1]), 1)
        self.assertEqual(self.call(path, role="ops_reviewer")[1]["payload"], proposal["payload"])
        decision = {"decision": "approve", "payload_hash": proposal["payload_hash"]}
        self.assertEqual(self.call(path + "/decision", body=decision)[0], 403)
        outcome = self.call(path + "/decision", role="ops_reviewer", body=decision)[1]
        repeated = self.call(path + "/decision", role="ops_reviewer", body=decision)[1]
        self.assertEqual(outcome["action"]["action_id"], repeated["action"]["action_id"])
        self.assertEqual(self.call(path + "/outcome", role="ops_reviewer")[1]["outcome"], "succeeded")

    def test_browser_security_and_input_validation_fail_closed(self):
        body = {"request_id": "unsafe", "text": "draft a ticket for S01"}
        for headers in ({"Origin": "https://untrusted.example"}, {"Host": "untrusted.example"},
                        {"X-Demo-Token": ""}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.call("/api/requests", body=body, headers=headers)[0], 403)
        self.assertEqual(self.call("/api/requests", body={**body, "role": "ops_reviewer"})[0], 400)
        self.assertEqual(self.call("/api/requests", body={"request_id": "", "text": []})[0], 400)
        self.assertEqual(self.call("/api/config")[1]["model"], "test-double")
        self.assertEqual(self.call("/../data/hr01.json")[0], 404)

    def test_explicit_assets_are_local_and_sent_with_browser_protections(self):
        for path, kind in (("/", "text/html"), ("/app.css", "text/css"), ("/app.js", "text/javascript")):
            with self.subTest(path=path):
                connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
                try:
                    connection.request("GET", path)
                    reply = connection.getresponse()
                    self.assertEqual(reply.status, 200)
                    self.assertTrue(reply.getheader("Content-Type").startswith(kind))
                    self.assertIn("frame-ancestors 'none'", reply.getheader("Content-Security-Policy"))
                    self.assertEqual(reply.getheader("Cache-Control"), "no-store")
                    self.assertTrue(reply.read())
                finally:
                    connection.close()
