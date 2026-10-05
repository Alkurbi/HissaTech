"""Remaining department and reviewer acceptance checks through the service."""

import json
import sqlite3
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import unittest

from hissatech.domain import DATA, Request, digest
from tests.model_double import TemplateModel
from hissatech import service
from hissatech.service import submit_request
from hissatech.store import Store


class RemainingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=DATA.parent)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        for name in ("policies", "feedback", "incidents", "support_messages"):
            (self.path / f"{name}.json").write_text((DATA / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8")
        self.store = Store(self.path / "state.sqlite3")
        self.addCleanup(self.store.close)

    def submit(self, role, text, request_id="remaining"):
        return submit_request(Request(request_id, role, text), self.store, TemplateModel(), self.path)

    def test_product_preserves_novel_feedback_and_updates_evidence_counts(self):
        feedback = json.loads((self.path / "feedback.json").read_text(encoding="utf-8"))
        feedback.extend([{"id": "F06", "text": "Payment confirmation is missing after a successful payment."},
                         {"id": "F07", "text": "Please add a dark theme."}])
        (self.path / "feedback.json").write_text(json.dumps(feedback), encoding="utf-8")
        result = self.submit("product", "prioritize product feedback")
        facts = result["result"]
        self.assertEqual(facts["themes"][0]["record_count"], 3)
        self.assertEqual(facts["unclassified_feedback_ids"], ["F07"])
        self.assertIn("F07", result["sources"])
        self.assertEqual(len(facts["top_three_backlog_items"]), 3)
        self.assertIn("P02", facts["top_three_backlog_items"][0]["priority_rationale"])
        for item in facts["themes"]:
            self.assertTrue(item["implementation_dependencies"])
            self.assertIn("not verified", item["dependency_status"])
        research = next(item for item in facts["themes"] if item["theme"] == "fractional ownership research")
        self.assertIn("P01", " ".join(research["implementation_dependencies"]))

    def test_tech_uses_changed_log_ids_and_does_not_claim_complete_recovery(self):
        records = [
            {"id": "I10", "timestamp": "2026-09-28T10:00:00+03:00", "service": "lead_intake", "event": "HTTP 500", "request_id": "R201"},
            {"id": "I11", "timestamp": "2026-09-28T10:00:05+03:00", "service": "crm_mock", "event": "timeout", "request_id": "R201"},
            {"id": "I12", "timestamp": "2026-09-28T10:01:00+03:00", "service": "lead_intake", "event": "HTTP 503", "request_id": "R202"},
            {"id": "I13", "timestamp": "2026-09-28T10:03:00+03:00", "service": "lead_intake", "event": "HTTP 200", "request_id": "R203"},
        ]
        (self.path / "incidents.json").write_text(json.dumps(records), encoding="utf-8")
        result = self.submit("tech", "triage lead intake failures")
        facts = result["result"]
        self.assertEqual(facts["severity"], "High")
        self.assertIn("R201", facts["next_diagnostic_step"])
        self.assertIn("not prove", facts["recovery_assessment"])
        self.assertEqual(result["proposed_action"]["payload"]["source_ids"], ["I10", "I11", "I12", "I13", "P02"])
        self.assertNotIn("I01", str(result))

    def test_tech_empty_logs_create_no_incident_and_single_error_is_not_repeated(self):
        (self.path / "incidents.json").write_text("[]", encoding="utf-8")
        empty = self.submit("tech", "triage incident logs", "empty")
        self.assertEqual(empty["action_status"], "needs_information")
        self.assertIsNone(empty["proposed_action"])

    def test_reviewer_inspects_persisted_payload_and_action_survives_restart(self):
        proposal = self.submit("customer_service", "draft a ticket for S01")["proposed_action"]
        inspected = service.inspect_proposal(proposal["proposal_id"], "ops_reviewer", self.store)
        self.assertEqual(inspected["payload"], proposal["payload"])
        outcome = service.decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", self.store)
        self.assertEqual(outcome["outcome"], "succeeded")
        self.store.close()
        self.store = Store(self.path / "state.sqlite3")
        self.addCleanup(self.store.close)
        repeated = service.decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", self.store)
        self.assertEqual(repeated["action"]["payload"], proposal["payload"])
        self.assertEqual(repeated["action"]["action_id"], outcome["action"]["action_id"])
        self.assertEqual(len(repeated["attempt_history"]), 1)

    def test_uncertain_execution_reconciles_by_key_without_duplicate_creation(self):
        proposal = self.submit("customer_service", "draft a ticket for S01")["proposed_action"]
        unknown = service.decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", self.store, "uncertain_once")
        self.assertEqual(unknown["outcome"], "uncertain")
        self.assertIsNone(unknown["action"])
        reconciled = service.decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", self.store, "uncertain_once")
        self.assertEqual(reconciled["outcome"], "succeeded")
        self.assertEqual(reconciled["action"]["payload"], proposal["payload"])
        self.assertEqual([item["outcome"] for item in reconciled["attempt_history"]], ["uncertain", "succeeded"])

    def test_two_competing_reviewers_observe_one_action(self):
        proposal = self.submit("customer_service", "draft a ticket for S01")["proposed_action"]
        barrier = Barrier(2)

        def approve(actor):
            store = Store(self.path / "state.sqlite3")
            try:
                barrier.wait(timeout=5)
                return service.decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", store, actor_id=actor)
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(approve, ("reviewer-a", "reviewer-b")))
        self.assertEqual(results[0]["action"]["action_id"], results[1]["action"]["action_id"])
        self.assertEqual(len(results[0]["attempt_history"]), 1)

    def test_processing_request_can_resume_after_lease_expiry(self):
        request = Request("interrupted", "customer_service", "draft a ticket for S01")
        fingerprint = digest({"role": request.role, "text": request.text, "actor_id": "customer_service-test"})
        with patch("hissatech.store.time.time", return_value=100):
            self.store.start_request(request.request_id, request.role, fingerprint)
            processing = submit_request(request, self.store, TemplateModel(), self.path)
            self.assertEqual(processing["action_status"], "processing")
        with patch("hissatech.store.time.time", return_value=401):
            recovered = submit_request(request, self.store, TemplateModel(), self.path)
            self.assertEqual(recovered["action_status"], "pending_approval")

    def test_permanent_failure_stays_terminal_and_rejection_is_idempotent(self):
        proposal = self.submit("customer_service", "draft a ticket for S01")["proposed_action"]
        failed = service.decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", self.store, "always_fail")
        repeated = service.decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", self.store, "normal")
        self.assertEqual(failed["outcome"], "adapter_failure")
        self.assertEqual(repeated["attempts"], 1)
        self.assertIsNone(repeated["action"])
        other = self.submit("customer_service", "draft a ticket for S02", "reject")["proposed_action"]
        first = service.decide_proposal(other["proposal_id"], other["payload_hash"], "ops_reviewer", "reject", self.store)
        self.assertEqual(service.decide_proposal(other["proposal_id"], other["payload_hash"], "ops_reviewer", "reject", self.store), first)
        with self.assertRaises(PermissionError):
            service.inspect_proposal(other["proposal_id"], "marketing", self.store)

    def test_stale_worker_cannot_create_a_second_proposal_after_takeover(self):
        request = Request("takeover", "customer_service", "draft a ticket for S01")
        second_results = []
        test = self

        class SuspendedModel(TemplateModel):
            def generate(self, prompt):
                if prompt.startswith("DRAFT"):
                    with patch("hissatech.store.time.time", return_value=401):
                        second_results.append(submit_request(request, test.store, TemplateModel(), test.path))
                    return json.dumps({"text": "A different stale draft.", "source_ids": ["S01", "P02"]})
                return super().generate(prompt)

        with patch("hissatech.store.time.time", return_value=100):
            stale = submit_request(request, self.store, SuspendedModel(), self.path)
        self.assertEqual(stale["action_status"], "processing")
        history = service.get_history("ops_reviewer", self.store)
        self.assertEqual(len(history[0]["proposals"]), 1)
        self.assertEqual(history[0]["proposals"][0]["payload"]["draft"], second_results[0]["result"]["draft_response"])

    def test_legacy_action_without_executed_payload_remains_unverified(self):
        proposal = self.submit("customer_service", "draft a ticket for S01")["proposed_action"]
        service.decide_proposal(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "approve", self.store)
        self.store.close()
        legacy = sqlite3.connect(self.path / "state.sqlite3")
        try:
            legacy.execute("DROP TRIGGER immutable_mock_action")
            legacy.execute("UPDATE mock_actions SET payload_canonical_json=NULL,payload_hash=NULL")
            legacy.commit()
        finally:
            legacy.close()
        self.store = Store(self.path / "state.sqlite3")
        self.addCleanup(self.store.close)
        result = service.get_outcome(proposal["proposal_id"], "ops_reviewer", self.store)
        self.assertEqual(result["outcome"], "legacy_unverified")
        self.assertIsNone(result["action"])

    def test_generic_help_cannot_become_an_arbitrary_department_action(self):
        class OverconfidentModel:
            def generate(self, prompt):
                return '{"department":"tech","clarification":null}'

        result = submit_request(Request("help", "marketing", "Please help"), self.store, OverconfidentModel(), self.path)
        self.assertEqual(result["action_status"], "needs_clarification")
        self.assertIsNone(result["proposed_action"])


if __name__ == "__main__":
    unittest.main()
