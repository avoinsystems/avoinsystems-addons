from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.connector_liana.models import liana_backend as liana_backend_module
from odoo.addons.connector_liana.models.liana_backend import LianaError


class TestLianaBackendAutomationConnection(TransactionCase):

    def _create_full_backend(self):
        return self.env["liana.backend"].create(
            {
                "name": "Test backend",
                "liana_automation_address": "https://automation.example.test",
                "liana_automation_secret": "test-secret-key",
                "liana_automation_user": "api-user",
                "liana_automation_realm": "TestRealm",
            }
        )

    @patch.object(liana_backend_module.requests, "post")
    def test_test_automation_connection_success(self, mock_post):
        mock_response = mock_post.return_value
        mock_response.json.return_value = {"pong": "pong"}
        mock_response.raise_for_status.return_value = None

        backend = self._create_full_backend()
        result = backend.test_automation_connection()

        mock_post.assert_called_once()
        called_kwargs = mock_post.call_args.kwargs
        self.assertEqual(called_kwargs.get("data"), '{"ping": "pong"}')
        self.assertIn("Authorization", called_kwargs["headers"])

        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["type"], "success")

    def test_test_automation_connection_missing_settings(self):
        backend = self.env["liana.backend"].create(
            {
                "name": "Incomplete",
                "liana_automation_address": "https://example.test",
            }
        )
        with self.assertRaises(UserError) as cm:
            backend.test_automation_connection()
        self.assertIn("Please fill in all Liana Automation settings", str(cm.exception))

    @patch.object(liana_backend_module.requests, "post")
    def test_test_automation_connection_unexpected_response(self, mock_post):
        mock_response = mock_post.return_value
        mock_response.json.return_value = {"unexpected": True}
        mock_response.raise_for_status.return_value = None

        backend = self._create_full_backend()
        with self.assertRaises(LianaError) as cm:
            backend.test_automation_connection()
        self.assertIn("Unexpected response from Liana Automation", str(cm.exception))
