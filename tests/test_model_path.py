"""Local model outcomes exercised through the application service."""

import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from unittest.mock import Mock, patch

from hissatech.domain import Request
from hissatech.model import LocalModel
from hissatech.service import submit_request
from hissatech.store import Store


class ScriptedModel:
    """A model boundary double, independent of workflow keyword matching."""

    def __init__(self, *outputs: str):
        self.outputs = iter(outputs)

    def generate(self, prompt: str) -> str:
        return next(self.outputs)


class ModelPathTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def submit(self, text: str, model: ScriptedModel, role: str = "customer_service"):
        return submit_request(Request("model-path", role, text), self.store, model)

    def test_interpretation_routes_a_request_without_english_keywords(self):
        model = ScriptedModel(
            '{"department":"customer_service","clarification":null}',
            json.dumps({"text": "شكرًا لتواصلك، سنراجع تأكيد الدفع.", "source_ids": ["S02", "P02"]}),
        )
        result = self.submit("ساعدني بخصوص S02", model)
        self.assertEqual(result["department"], "customer_service")
        self.assertIn("شكرًا", result["result"]["draft_response"])
        self.assertEqual(result["action_status"], "pending_approval")

    def test_model_route_is_used_and_still_checked_against_trusted_role(self):
        model = ScriptedModel('{"department":"tech","clarification":null}')
        result = self.submit("Something failed behind the scenes", model)
        self.assertEqual(result["department"], "tech")
        self.assertEqual(result["action_status"], "denied")

    def test_uncertain_interpretation_returns_one_clarification(self):
        model = ScriptedModel('{"department":null,"clarification":"Which department should investigate this issue?"}')
        result = self.submit("Please handle this issue", model)
        self.assertEqual(result["action_status"], "needs_clarification")
        self.assertEqual(result["result"], "Which department should investigate this issue?")
        self.assertIsNone(result["proposed_action"])

    def test_invalid_interpretation_is_persisted_as_a_failed_model_result(self):
        model = ScriptedModel('{"department":"administrator","clarification":null}')
        result = self.submit("draft a ticket for S01", model)
        self.assertEqual(result["action_status"], "model_invalid_output")
        self.assertIsNone(result["proposed_action"])
        repeated = self.submit("draft a ticket for S01", ScriptedModel())
        self.assertEqual(repeated, result)

    def test_draft_with_an_unknown_source_cannot_create_a_proposal(self):
        model = ScriptedModel(
            '{"department":"customer_service","clarification":null}',
            '{"text":"Draft acknowledgement","source_ids":["HR01"]}',
        )
        result = self.submit("draft a ticket for S01", model)
        self.assertEqual(result["action_status"], "model_invalid_output")
        self.assertIsNone(result["proposed_action"])

    def test_invalid_json_during_drafting_returns_an_honest_failure(self):
        model = ScriptedModel(
            '{"department":"tech","clarification":null}',
            'This is not JSON',
        )
        result = self.submit("triage incident I01", model, "tech")
        self.assertEqual(result["action_status"], "model_invalid_output")
        self.assertIsNone(result["proposed_action"])

    def test_arabic_interpretation_works_without_a_source_id_or_english_keyword(self):
        result = self.submit(
            "حلل ملاحظات العملاء ورتب أولويات التحسين",
            ScriptedModel('{"department":"product","clarification":null}',
                          '{"text":"Prioritize the reported payment-confirmation gaps.","source_ids":["F01","F02"]}'),
            "product",
        )
        self.assertEqual(result["department"], "product")
        self.assertEqual(result["action_status"], "draft")
        self.assertEqual(result["result"]["draft_source_ids"], ["F01", "F02"])

    def test_empty_or_conflicting_interpretations_are_rejected(self):
        for output in ('[]', '{"department":null,"clarification":""}',
                       '{"department":"tech","clarification":"Which team?"}'):
            with self.subTest(output=output):
                store = Store(":memory:")
                self.addCleanup(store.close)
                result = submit_request(Request("invalid", "tech", "Investigate"), store, ScriptedModel(output))
                self.assertEqual(result["action_status"], "model_invalid_output")

    @patch("hissatech.model.http.client.HTTPConnection", autospec=True)
    def test_local_transport_uses_json_mode_and_closes_after_both_calls(self, connection_type):
        connection = connection_type.return_value
        connection.sock = Mock()
        reply = connection.getresponse.return_value
        reply.status = 200
        reply.read.side_effect = [
            json.dumps({"response": '{"department":"customer_service","clarification":null}', "done": True}).encode(),
            json.dumps({"response": '{"text":"We will investigate the missing confirmation.","source_ids":["S01","P02"]}', "done": True}).encode(),
        ]
        result = self.submit("draft a ticket for S01", LocalModel("test-local"))
        self.assertEqual(result["action_status"], "pending_approval")
        routing_schema = json.loads(connection.request.call_args_list[0].args[2])["format"]
        self.assertEqual(list(routing_schema["properties"]), ["department", "clarification"])
        for call in connection.request.call_args_list:
            payload = json.loads(call.args[2])
            self.assertEqual(payload["format"]["type"], "object")
            self.assertFalse(payload["format"]["additionalProperties"])
            self.assertFalse(payload["stream"])
        self.assertEqual(connection.close.call_count, 2)

    def test_trickling_local_server_cannot_extend_the_inference_deadline(self):
        class SlowReply(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.02)
                except OSError:
                    pass

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowReply)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            start = time.monotonic()
            result = self.submit("draft a ticket for S01", LocalModel("test-local", port=server.server_port, timeout=0.12))
            self.assertEqual(result["action_status"], "model_unavailable")
            self.assertLess(time.monotonic() - start, 0.8)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

    @patch("hissatech.model.http.client.HTTPConnection", autospec=True)
    def test_local_timeout_returns_a_failure_and_closes_connection(self, connection_type):
        connection_type.return_value.connect.side_effect = TimeoutError("test timeout")
        result = self.submit("draft a ticket for S01", LocalModel("test-local", timeout=1))
        self.assertEqual(result["action_status"], "model_unavailable")
        connection_type.return_value.close.assert_called_once()

    @patch("hissatech.model.http.client.HTTPConnection", autospec=True)
    def test_incomplete_transport_envelope_cannot_produce_a_success(self, connection_type):
        connection_type.return_value.sock = Mock()
        reply = connection_type.return_value.getresponse.return_value
        reply.status = 200
        reply.read.return_value = json.dumps({"response": '{"department":"customer_service","clarification":null}', "done": False}).encode()
        result = self.submit("draft a ticket for S01", LocalModel("test-local"))
        self.assertEqual(result["action_status"], "model_invalid_output")
        self.assertEqual(result["department"], "unrouted")


if __name__ == "__main__":
    unittest.main()
