"""Evidence checks fail closed and use the application, not fabricated outputs."""

import unittest
from pathlib import Path
import tempfile
import zipfile

from hissatech.demo import acceptance_checks
from tests.model_double import TemplateModel
from hissatech.store import Store
from scripts.package_submission import ROOT, package


class DemoTests(unittest.TestCase):
    def test_acceptance_capture_checks_all_missing_failure_scenarios(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        checks = acceptance_checks(store, TemplateModel())
        self.assertEqual([check["scenario"] for check in checks], ["rejected", "edited_hash", "always_fail", "repeat_request", "model_unavailable", "missing_source"])
        self.assertTrue(all(check["passed"] for check in checks))
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM mock_actions").fetchone()[0], 0)

    def test_packaging_requires_complete_evidence_and_never_overwrites(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            evidence = Path(directory)
            output = evidence / "test.zip"
            with self.assertRaises(ValueError):
                package(evidence, output)
            for name in ("acceptance.json", "evidence.json", "report.html"):
                (evidence / name).write_text("{}", encoding="utf-8")
            self.assertGreater(package(evidence, output), 0)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertIn("data/feedback.json", names)
                self.assertNotIn("PRODUCT.md", names)
                self.assertNotIn("DESIGN.md", names)
                self.assertNotIn("scripts/generate_diagrams.py", names)
                self.assertFalse(any(name.startswith("docs/diagrams/") for name in names))
            with self.assertRaises(FileExistsError):
                package(evidence, output)


if __name__ == "__main__":
    unittest.main()
