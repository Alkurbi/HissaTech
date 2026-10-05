"""Evidence checks fail closed and use the application, not fabricated outputs."""

import unittest

from hissatech.demo import acceptance_checks
from tests.model_double import TemplateModel
from hissatech.store import Store


class DemoTests(unittest.TestCase):
    def test_acceptance_capture_checks_all_missing_failure_scenarios(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        checks = acceptance_checks(store, TemplateModel())
        self.assertEqual([check["scenario"] for check in checks], ["rejected", "edited_hash", "always_fail", "repeat_request", "model_unavailable", "missing_source"])
        self.assertTrue(all(check["passed"] for check in checks))
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM mock_actions").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
