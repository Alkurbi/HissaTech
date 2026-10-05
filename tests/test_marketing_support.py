"""Marketing and support acceptance behavior at the application-service boundary."""

import json
from pathlib import Path
import tempfile
import unittest

from hissatech.domain import DATA, Request
from tests.model_double import TemplateModel
from hissatech.service import submit_request
from hissatech.store import Store


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.directory = tempfile.TemporaryDirectory(dir=DATA.parent)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        for name in ("leads", "spend", "policies", "support_messages"):
            (self.path / f"{name}.json").write_text((DATA / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8")

    def submit(self, role, text, request_id="workflow-test", model=None):
        return submit_request(Request(request_id, role, text), self.store, model or TemplateModel(), self.path)

    def test_marketing_reports_status_counts_missing_values_and_cost_denominators(self):
        result = self.submit("marketing", "summarize Prime lead performance")
        facts = result["result"]
        self.assertEqual(facts["status_counts"], {"Qualified": 3, "New": 2, "Unqualified": 1, "Contacted": 1})
        self.assertEqual(facts["by_source"]["Social"]["status_counts"], {"New": 1, "Contacted": 1})
        self.assertEqual(facts["missing_budget_count"], 2)
        self.assertEqual(facts["missing_source_count"], 1)
        self.assertEqual(facts["by_source"]["Paid Search"]["cost_per_unique_lead_sar"], 600)
        self.assertIn("unique leads", facts["by_source"]["Paid Search"]["cost_denominator"])
        self.assertIsNone(facts["by_source"]["Organic"]["spend_sar"])
        self.assertEqual(len(facts["recommendations"]), 2)
        self.assertNotIn("customer_id", str(facts))

    def test_conflicting_import_is_disclosed_without_contact_or_budget_values(self):
        leads = json.loads((self.path / "leads.json").read_text(encoding="utf-8"))
        leads.append({"row_id": "L09", "contact_id": "C01", "source": "Social", "status": "New", "budget_sar": 987654321})
        (self.path / "leads.json").write_text(json.dumps(leads), encoding="utf-8")
        result = self.submit("marketing", "summarize Prime lead performance")
        facts = result["result"]
        self.assertEqual(facts["unique_leads"], 7)
        self.assertEqual(facts["duplicate_conflicts"], [{"kept_row_id": "L01", "duplicate_row_id": "L09", "fields": ["source", "status", "budget_sar"]}])
        self.assertIn("first import", facts["duplicate_resolution"])
        self.assertTrue(any("conflict" in item.lower() for item in result["missing_information"]))
        self.assertNotIn("C01", str(facts))
        self.assertNotIn("987654321", str(facts))

    def test_empty_marketing_data_has_no_fabricated_rates_or_static_gaps(self):
        (self.path / "leads.json").write_text("[]", encoding="utf-8")
        (self.path / "spend.json").write_text('{"Email": 0}', encoding="utf-8")
        result = self.submit("marketing", "summarize Prime lead performance")
        self.assertIsNone(result["result"]["qualification_rate"])
        email = result["result"]["by_source"]["Email"]
        self.assertEqual(email["spend_sar"], 0)
        self.assertIsNone(email["cost_per_unique_lead_sar"])
        self.assertNotIn("Referral", str(result["missing_information"]))

    def test_payment_request_without_message_does_not_substitute_s01(self):
        result = self.submit("customer_service", "draft a customer ticket about payment")
        self.assertEqual(result["action_status"], "needs_clarification")
        self.assertIsNone(result["proposed_action"])
        self.assertNotIn("S01", result["sources"])

    def test_supplied_customer_message_is_preserved_in_the_pending_ticket(self):
        text = json.dumps({"message": "My payment succeeded but the confirmation is missing.", "customer_id": "C09", "language": "en"})
        result = self.submit("customer_service", text)
        self.assertEqual(result["action_status"], "pending_approval")
        self.assertEqual(result["result"]["priority"], "High")
        payload = result["proposed_action"]["payload"]
        self.assertEqual(payload["message_text"], "My payment succeeded but the confirmation is missing.")
        self.assertEqual(payload["customer_id"], "C09")
        self.assertEqual(payload["draft"], result["result"]["draft_response"])
        self.assertIn("REQUEST:workflow-test", payload["source_ids"])

    def test_support_priority_uses_actual_bilingual_evidence_not_just_keywords(self):
        cases = [
            ("My payment was successful and I received confirmation.", "en", "Normal", "payment inquiry"),
            ("My payment was not successful and confirmation is missing.", "en", "Normal", "payment inquiry"),
            ("I have not paid and no confirmation is visible.", "en", "Normal", "payment inquiry"),
            ("My payment was successful and confirmation is not missing.", "en", "Normal", "payment inquiry"),
            ("My payment was not confirmed as successful.", "en", "Normal", "payment inquiry"),
            ("تم الدفع بنجاح لكن لم يظهر التأكيد في حسابي.", "ar", "High", "payment confirmation missing"),
            ("لا أستطيع تسجيل الدخول إلى حسابي.", "ar", "Normal", "access request"),
        ]
        for index, (message, language, priority, classification) in enumerate(cases):
            with self.subTest(message=message):
                result = self.submit("customer_service", json.dumps({"message": message, "customer_id": "C09", "language": language}), f"priority-{index}")
                self.assertEqual(result["result"]["priority"], priority)
                self.assertEqual(result["result"]["classification"], classification)

    def test_unknown_and_multiple_message_references_do_not_choose_a_fixture(self):
        for index, text in enumerate(("draft a ticket for S010", "draft a ticket for S99", "draft a ticket for S01 and S02")):
            with self.subTest(text=text):
                result = self.submit("customer_service", text, f"reference-{index}")
                self.assertEqual(result["action_status"], "needs_clarification")
                self.assertIsNone(result["proposed_action"])

    def test_supplied_message_without_identity_requests_only_identity(self):
        result = self.submit("customer_service", json.dumps({"message": "My payment succeeded but confirmation is missing."}))
        self.assertEqual(result["action_status"], "needs_information")
        self.assertEqual(result["missing_information"], ["customer identity"])
        self.assertIsNone(result["proposed_action"])

    def test_malformed_supplied_message_metadata_cannot_create_a_ticket(self):
        result = self.submit("customer_service", json.dumps({"message": "Customer payment question", "language": ["ar"]}))
        self.assertEqual(result["action_status"], "needs_clarification")
        self.assertIsNone(result["proposed_action"])

    def test_customer_acknowledgement_cannot_promise_a_refund_or_resolution_time(self):
        class PromiseModel(TemplateModel):
            def __init__(self, text):
                self.text = text

            def generate(self, prompt):
                if prompt.startswith("DRAFT"):
                    return json.dumps({"text": self.text, "source_ids": ["S01", "P02"]})
                return super().generate(prompt)

        for index, text in enumerate(("We will refund you and resolve this within 24 hours.", "You will receive confirmation within 24 hours.", "Your refund is guaranteed tomorrow.", "We cannot promise a refund. We will refund you.")):
            with self.subTest(text=text):
                result = self.submit("customer_service", "draft a ticket for S01", f"promise-{index}", PromiseModel(text))
                self.assertEqual(result["action_status"], "blocked")
                self.assertIsNone(result["proposed_action"])
        result = self.submit("customer_service", "draft a ticket for S01", "safe-refusal", PromiseModel("We cannot promise a refund or resolution time."))
        self.assertEqual(result["action_status"], "pending_approval")

    def test_invalid_fixture_shapes_or_negative_spend_fail_without_a_proposal(self):
        cases = [("leads", {}, "marketing", "summarize lead performance"),
                 ("spend", {"Social": -1}, "marketing", "summarize lead performance"),
                 ("spend", {"Social": 10**500}, "marketing", "summarize lead performance"),
                 ("support_messages", [{"id": "S01", "text": []}], "customer_service", "draft a ticket for S01")]
        for index, (name, value, role, text) in enumerate(cases):
            with self.subTest(name=name):
                original = (self.path / f"{name}.json").read_text(encoding="utf-8")
                (self.path / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
                try:
                    result = self.submit(role, text, f"invalid-{index}")
                    self.assertEqual(result["action_status"], "source_unavailable")
                    self.assertIsNone(result["proposed_action"])
                finally:
                    (self.path / f"{name}.json").write_text(original, encoding="utf-8")

    def test_marketing_summary_cannot_turn_unknown_spend_into_zero(self):
        class FalseCostModel(TemplateModel):
            def generate(self, prompt):
                if prompt.startswith("DRAFT"):
                    return json.dumps({"text": "Organic has one qualified lead at SAR 0 cost per unique lead.", "source_ids": ["L06"]})
                return super().generate(prompt)

        result = self.submit("marketing", "summarize Prime lead performance", model=FalseCostModel())
        self.assertEqual(result["action_status"], "model_invalid_output")

    def test_observed_real_model_grounding_failures_create_no_proposal(self):
        class InvalidDraftModel(TemplateModel):
            def __init__(self, text, references):
                self.text, self.references = text, references

            def generate(self, prompt):
                if prompt.startswith("DRAFT"):
                    return json.dumps({"text": self.text, "source_ids": self.references})
                return super().generate(prompt)

        cases = [
            ("marketing", "summarize lead performance", "Paid Search spend is $1200.", ["L01"]),
            ("customer_service", "draft a ticket for S01", "Thank you for your report.", ["P02"]),
            ("customer_service", "draft a ticket for S01", "We are currently investigating.", ["S01"]),
            ("customer_service", "draft a ticket for S02", "نحن نعمل حاليًا على حل المشكلة.", ["S02"]),
        ]
        for index, (role, request, text, references) in enumerate(cases):
            with self.subTest(text=text):
                result = self.submit(role, request, f"grounding-{index}", InvalidDraftModel(text, references))
                self.assertEqual(result["action_status"], "model_invalid_output")
                self.assertIsNone(result["proposed_action"])

    def test_unknown_spend_guard_accepts_negation_and_separate_known_zero(self):
        class SummaryModel(TemplateModel):
            def __init__(self, text):
                self.text = text

            def generate(self, prompt):
                if prompt.startswith("DRAFT"):
                    return json.dumps({"text": self.text, "source_ids": ["L01", "L06"]})
                return super().generate(prompt)

        (self.path / "spend.json").write_text('{"Paid Search":0,"Social":800}', encoding="utf-8")
        for index, text in enumerate(("Organic spend is unknown, not zero.", "Paid Search cost is SAR 0. Organic spend is unknown.")):
            with self.subTest(text=text):
                result = self.submit("marketing", "summarize lead performance", f"truthful-{index}", SummaryModel(text))
                self.assertEqual(result["action_status"], "complete")


if __name__ == "__main__":
    unittest.main()
