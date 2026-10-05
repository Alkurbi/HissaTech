"""Behavioral checks at the application boundary shared by future interfaces."""

import io
import unittest
from unittest.mock import patch

from hissatech.cli import main as cli_main
from hissatech.domain import Request
from hissatech.service import submit_request
from hissatech.store import Store
from hissatech.web import main as web_main
from tests.model_double import TemplateModel


class ServiceTests(unittest.TestCase):
    def test_entry_points_reject_canned_inference_before_opening_storage(self):
        entries = ((cli_main, ["--model", "template", "request", "--role", "marketing", "--text", "summarize leads"]),
                   (web_main, ["--model", "template"]))
        for main, arguments in entries:
            with self.subTest(entry=main.__module__), patch("sys.argv", ["hissatech", *arguments]), \
                    patch("sys.stderr", new_callable=io.StringIO) as error, patch(main.__module__ + ".Store") as store:
                with self.assertRaises(SystemExit) as caught:
                    main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("Template responses are not available", error.getvalue())
                store.assert_not_called()

    def test_support_request_is_pending_and_repeating_it_preserves_the_proposal(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        request = Request("service-s01", "customer_service", "draft a ticket for S01")
        first = submit_request(request, store, TemplateModel())
        second = submit_request(request, store, TemplateModel())
        self.assertEqual(first["result"]["priority"], "High")
        self.assertEqual(first["action_status"], "pending_approval")
        self.assertEqual(first["sources"], ["S01", "P02"])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
