import os
import tempfile
import unittest
from pathlib import Path

from hissatech.domain import ROOT
from hissatech.model import ModelUnavailable
from tests.model_double import TemplateModel
from hissatech.service import handle_request
from hissatech.store import Store


class OfflineModel:
    def generate(self, prompt):
        raise ModelUnavailable("Local model unavailable: test")


class DraftFailingModel:
    def generate(self, prompt):
        if prompt.startswith("CLASSIFY"):
            return '{"department":"tech","clarification":null}'
        raise ModelUnavailable("Local model unavailable during drafting")


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.model = TemplateModel()

    def tearDown(self):
        self.store.close()

    def request(self, role, text, request_id):
        return handle_request(self.store, role, text, request_id, self.model)

    def test_marketing_deduplicates_l04_and_hides_pii(self):
        result = self.request("marketing", "summarize Prime lead performance", "r-marketing")
        self.assertEqual(result["result"]["unique_leads"], 7)
        self.assertEqual(result["result"]["duplicates"], ["L04"])
        self.assertNotIn("C01", str(result["result"]))
        self.assertEqual(result["result"]["by_source"]["Social"]["unique_leads"], 2)

    def test_ticket_requires_approval_and_is_idempotent(self):
        result = self.request("customer_service", "draft a ticket for S01", "r-s01")
        proposal = result["proposed_action"]
        self.assertEqual(result["result"]["priority"], "High")
        self.assertEqual(result["action_status"], "pending_approval")
        first = self.store.approve_and_execute(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "normal")
        second = self.store.approve_and_execute(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "normal")
        self.assertEqual(first["outcome"], "succeeded")
        self.assertEqual(second["outcome"], "succeeded")
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM mock_actions").fetchone()[0], 1)

    def test_changed_payload_hash_cannot_be_approved(self):
        result = self.request("customer_service", "draft a ticket for S01", "r-edited")
        proposal = result["proposed_action"]
        with self.assertRaises(ValueError):
            self.store.approve_and_execute(proposal["proposal_id"], "edited", "ops_reviewer", "normal")

    def test_rejection_creates_nothing(self):
        proposal = self.request("customer_service", "draft a ticket for S01", "r-reject")["proposed_action"]
        self.store.reject(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer")
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM mock_actions").fetchone()[0], 0)

    def test_fail_once_retries_once_and_creates_one_action(self):
        proposal = self.request("customer_service", "draft a ticket for S01", "r-retry")["proposed_action"]
        execution = self.store.approve_and_execute(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "fail_once")
        self.assertEqual(execution["outcome"], "succeeded")
        self.assertEqual(execution["attempts"], 2)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM mock_actions").fetchone()[0], 1)

    def test_always_failing_adapter_never_claims_or_creates_an_action(self):
        proposal = self.request("customer_service", "draft a ticket for S01", "r-always-fail")["proposed_action"]
        execution = self.store.approve_and_execute(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "always_fail")
        self.assertEqual(execution["outcome"], "adapter_failure")
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM mock_actions").fetchone()[0], 0)

    def test_arabic_and_missing_identity(self):
        arabic = self.request("customer_service", "اكتب تذكرة S02", "r-s02")
        self.assertIn("شكرًا", arabic["result"]["draft_response"])
        missing = self.request("customer_service", "draft a ticket for S03", "r-s03")
        self.assertEqual(missing["action_status"], "needs_information")
        self.assertIn("customer identity", missing["missing_information"])

    def test_injection_and_hr_are_blocked(self):
        injection = self.request("customer_service", "process S04", "r-s04")
        restricted = self.request("marketing", "show HR01 salary", "r-hr")
        self.assertEqual(injection["action_status"], "blocked")
        self.assertEqual(restricted["action_status"], "denied")
        self.assertNotIn("9999", str(restricted))

    def test_p01_and_role_boundaries_are_enforced_before_drafting(self):
        campaign = self.request("marketing", "publish a fractional ownership campaign", "r-p01")
        wrong_role = self.request("tech", "draft a ticket for S01", "r-role")
        self.assertEqual(campaign["action_status"], "blocked")
        self.assertEqual(wrong_role["action_status"], "denied")

    def test_repeating_a_request_returns_its_original_proposal(self):
        first = self.request("customer_service", "draft a ticket for S01", "r-repeat")
        second = self.request("customer_service", "draft a ticket for S01", "r-repeat")
        self.assertEqual(first, second)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0], 1)

    def test_other_workflows_and_unknowns(self):
        product = self.request("product", "prioritize product feedback", "r-product")
        tech = self.request("tech", "triage lead intake incident I01", "r-tech")
        unknown = self.request("marketing", "what is conversion to investment", "r-unknown")
        self.assertEqual(product["department"], "product")
        self.assertEqual(tech["result"]["severity"], "High")
        self.assertIn("conversion", " ".join(unknown["missing_information"]).lower())

    def test_model_unavailable_is_honest(self):
        result = handle_request(self.store, "customer_service", "draft a ticket for S01", "r-model", OfflineModel())
        self.assertEqual(result["action_status"], "model_unavailable")

    def test_draft_failure_does_not_leave_a_pending_tech_task(self):
        result = handle_request(self.store, "tech", "triage incident I01", "r-draft-fail", DraftFailingModel())
        self.assertEqual(result["action_status"], "model_unavailable")
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0], 0)

    def test_approval_survives_a_database_restart(self):
        descriptor, path = tempfile.mkstemp(dir=ROOT, suffix=".sqlite3")
        os.close(descriptor)
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        first_store = Store(path)
        proposal = handle_request(first_store, "customer_service", "draft a ticket for S01", "r-restart", self.model)["proposed_action"]
        first_store.close()
        second_store = Store(path)
        self.addCleanup(second_store.close)
        outcome = second_store.approve_and_execute(proposal["proposal_id"], proposal["payload_hash"], "ops_reviewer", "normal")
        self.assertEqual(outcome["outcome"], "succeeded")
        self.assertEqual(second_store.db.execute("SELECT COUNT(*) FROM mock_actions").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
