import json
from unittest.mock import MagicMock, patch

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.pos_marketpay.client.marketpay import MARKETPAY_WAIT_TIME_DEFAULT

# The client factory on the model, patched so the request methods never touch
# the network or certificates.
CLIENT_FACTORY_PATH = (
    "odoo.addons.pos_marketpay.models.pos_payment_method."
    "PosPaymentMethod._get_marketpay_client"
)


@tagged("post_install", "-at_install")
class TestPosPaymentMethodCommon(TransactionCase):
    """Shared fixtures for the pos.payment.method Market Pay tests."""

    def setUp(self):
        super().setUp()
        self._seq = 0
        self.pm = self._make_pm()

    def _make_pm(self, **vals):
        self._seq += 1
        values = {
            "name": "MP %s" % self._seq,
            "use_payment_terminal": "marketpay",
            "payment_method_type": "terminal",
            "marketpay_terminal_identifier": "PAX:%s" % self._seq,
            "marketpay_test_mode": True,
        }
        values.update(vals)
        return self.env["pos.payment.method"].create(values)


class TestMarketPayRequestMethods(TestPosPaymentMethodCommon):
    """Payload assembly and result forwarding of the request methods."""

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", "https://example.com"
        )

    def _process_values(self, **over):
        values = {
            "is_refund": False,
            "amount": 3300,
            "ecrTransactionId": "1-2-3--4",
            "cashierId": 7,
            "currency": 978,
            "transactionReference": "ref-uuid",
            "ecrId": "Shop-1",
        }
        values.update(over)
        return values

    def test_process_purchase_builds_expected_payload(self):
        mock_client = MagicMock()
        mock_client.process_transaction.return_value = {"status": "OK"}

        with patch(CLIENT_FACTORY_PATH, return_value=mock_client):
            result = self.pm.marketpay_request_process_transaction(self._process_values())

        self.assertEqual(result, {"status": "OK"})
        mock_client.process_transaction.assert_called_once()
        payload = mock_client.process_transaction.call_args.args[0]
        self.assertEqual(payload["transactionType"], "PURCHASE")
        self.assertEqual(payload["transactionMode"], "DIRECT")
        self.assertEqual(payload["amount"], 3300)
        self.assertEqual(payload["currency"], 978)
        self.assertEqual(payload["ecrParams"]["ecrId"], "Shop-1")
        notification_url = payload["ecrParams"]["notificationUrl"]
        self.assertTrue(notification_url.endswith("/1-2-3--4"))
        self.assertIn(self.pm.marketpay_terminal_identifier, notification_url)
        self.assertEqual(
            mock_client.process_transaction.call_args.kwargs["wait_time"],
            MARKETPAY_WAIT_TIME_DEFAULT,
        )

    def test_process_refund_uses_abs_amount_and_refund_type(self):
        mock_client = MagicMock()
        mock_client.process_transaction.return_value = {"status": "OK"}

        with patch(CLIENT_FACTORY_PATH, return_value=mock_client):
            self.pm.marketpay_request_process_transaction(
                self._process_values(is_refund=True, amount=-3300)
            )

        payload = mock_client.process_transaction.call_args.args[0]
        self.assertEqual(payload["transactionType"], "REFUND")
        self.assertEqual(payload["amount"], 3300)

    def test_process_refund_with_positive_amount_raises(self):
        with self.assertRaises(ValidationError):
            self.pm.marketpay_request_process_transaction(
                self._process_values(is_refund=True, amount=100)
            )

    def test_process_purchase_with_non_positive_amount_raises(self):
        with self.assertRaises(ValidationError):
            self.pm.marketpay_request_process_transaction(
                self._process_values(is_refund=False, amount=0)
            )

    def test_cancel_builds_expected_payload(self):
        mock_client = MagicMock()
        mock_client.cancel_transaction.return_value = {"status": "OK"}
        values = {
            "terminalTransactionId": "TTX",
            "ecrTransactionId": "1-2-3--4",
            "cashierId": 7,
            "amount": 3300,
            "currency": 978,
            "ecrId": "Shop-1",
        }

        with patch(CLIENT_FACTORY_PATH, return_value=mock_client):
            self.pm.marketpay_request_cancel_transaction(values)

        mock_client.cancel_transaction.assert_called_once()
        payload = mock_client.cancel_transaction.call_args.args[0]
        self.assertEqual(payload["terminalTransactionId"], "TTX")
        self.assertEqual(payload["amount"], 3300)
        self.assertTrue(payload["ecrParams"]["notificationUrl"].endswith("/1-2-3--4"))
        self.assertEqual(
            mock_client.cancel_transaction.call_args.kwargs["wait_time"],
            MARKETPAY_WAIT_TIME_DEFAULT,
        )

    def test_abort_forwards_client_result(self):
        mock_client = MagicMock()
        ack = {"status": "OK", "debug": "204 received. Success without content."}
        mock_client.abort_transaction.return_value = ack

        with patch(CLIENT_FACTORY_PATH, return_value=mock_client):
            result = self.pm.marketpay_request_abort_transaction({})

        self.assertEqual(result, ack)
        mock_client.abort_transaction.assert_called_once_with()


class TestMarketPayWaitTime(TestPosPaymentMethodCommon):
    """System parameter `pos_marketpay.wait_time` and its fallbacks."""

    def test_default_wait_time(self):
        self.assertEqual(self.pm._get_marketpay_wait_time(), MARKETPAY_WAIT_TIME_DEFAULT)

    def test_custom_wait_time_is_used(self):
        self.env["ir.config_parameter"].sudo().set_param("pos_marketpay.wait_time", "45")
        self.assertEqual(self.pm._get_marketpay_wait_time(), 45)

    def test_invalid_wait_time_falls_back_to_default(self):
        self.env["ir.config_parameter"].sudo().set_param("pos_marketpay.wait_time", "nope")
        self.assertEqual(self.pm._get_marketpay_wait_time(), MARKETPAY_WAIT_TIME_DEFAULT)

    def test_out_of_range_wait_time_falls_back_to_default(self):
        self.env["ir.config_parameter"].sudo().set_param("pos_marketpay.wait_time", "0")
        self.assertEqual(self.pm._get_marketpay_wait_time(), MARKETPAY_WAIT_TIME_DEFAULT)
        self.env["ir.config_parameter"].sudo().set_param("pos_marketpay.wait_time", "301")
        self.assertEqual(self.pm._get_marketpay_wait_time(), MARKETPAY_WAIT_TIME_DEFAULT)
