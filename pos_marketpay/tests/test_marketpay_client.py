import json
import os
import tempfile
from unittest.mock import Mock, patch

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout, SSLError

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.pos_marketpay.client.marketpay import (
    MARKETPAY_ABORT_TIMEOUT,
    MARKETPAY_ENV_HOST_MAP,
    MARKETPAY_TIMEOUT,
    MARKETPAY_WAIT_TIME_DEFAULT,
    MarketPay,
)

# The `requests.request` callable as imported inside the client module.
REQUEST_PATH = "odoo.addons.pos_marketpay.client.marketpay.request"
OS_ACCESS_PATH = "odoo.addons.pos_marketpay.client.marketpay.os.access"


@tagged("post_install", "-at_install")
class TestMarketPayClientCommon(TransactionCase):
    """Shared fixtures for the Market Pay HTTP client tests."""

    def setUp(self):
        super().setUp()
        self._pm_seq = 0
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.cert_path = os.path.join(self._tmpdir.name, "cert.pem")
        self.key_path = os.path.join(self._tmpdir.name, "key.pem")
        with open(self.cert_path, "w", encoding="utf-8") as fobj:
            fobj.write("cert")
        with open(self.key_path, "w", encoding="utf-8") as fobj:
            fobj.write("key")

    def _make_pm(self, **vals):
        self._pm_seq += 1
        values = {
            "name": "MP %s" % self._pm_seq,
            "use_payment_terminal": "marketpay",
            "payment_method_type": "terminal",
            "marketpay_terminal_identifier": "PAX:%s" % self._pm_seq,
            "marketpay_test_mode": True,
        }
        values.update(vals)
        return self.env["pos.payment.method"].create(values)

    def _make_client(self, pm=None):
        """Build a client while bypassing the certificate checks."""
        pm = pm or self._make_pm()

        def fake_validate(client_self, _pm):
            client_self.path_certificate = "/tmp/cert.pem"
            client_self.path_privatekey = "/tmp/key.pem"

        with patch.object(MarketPay, "_validate_credentials", fake_validate):
            return MarketPay(pm)

    @staticmethod
    def _response(status_code, json_body=None, text="", json_error=False):
        res = Mock()
        res.status_code = status_code
        res.text = text
        if json_error:
            res.json.side_effect = json.decoder.JSONDecodeError("Expecting value", "", 0)
        else:
            res.json.return_value = json_body
        return res


class TestMarketPayRequestMapping(TestMarketPayClientCommon):
    """The status-code -> body mapping in MarketPay._request."""

    def test_200_dict_body_is_returned(self):
        client = self._make_client()
        with patch(REQUEST_PATH, return_value=self._response(200, {"status": "OK"})):
            result = client._request("POST", "/x", {"a": 1})
        self.assertEqual(result, {"status": "OK"})

    def test_201_dict_body_is_returned(self):
        client = self._make_client()
        with patch(REQUEST_PATH, return_value=self._response(201, {"status": "OK"})):
            result = client._request("POST", "/x", {"a": 1})
        self.assertEqual(result, {"status": "OK"})

    def test_non_json_success_returns_raw_response(self):
        client = self._make_client()
        raw = self._response(200, json_error=True, text="not json")
        with patch(REQUEST_PATH, return_value=raw):
            result = client._request("POST", "/x", {"a": 1})
        self.assertIs(result, raw)

    def test_204_maps_to_ok_ack(self):
        client = self._make_client()
        with patch(REQUEST_PATH, return_value=self._response(204)):
            result = client._request("POST", "/x", {})
        self.assertEqual(result["status"], "OK")

    def test_202_maps_to_neutral(self):
        client = self._make_client()
        with patch(REQUEST_PATH, return_value=self._response(202)):
            result = client._request("POST", "/x", {})
        self.assertEqual(result["status"], "NEUTRAL")

    def test_500_is_caught_as_nok(self):
        client = self._make_client()
        with patch(REQUEST_PATH, return_value=self._response(500, text="boom")):
            result = client._request("POST", "/x", {})
        self.assertEqual(result["status"], "NOK")
        self.assertIn("500", result["debug"])

    def test_ssl_error_maps_to_nok(self):
        client = self._make_client()
        with patch(REQUEST_PATH, side_effect=SSLError()):
            result = client._request("POST", "/x", {})
        self.assertEqual(result["status"], "NOK")
        self.assertIn("message", result)

    def test_connection_error_maps_to_nok(self):
        client = self._make_client()
        with patch(REQUEST_PATH, side_effect=RequestsConnectionError("down")):
            result = client._request("POST", "/x", {})
        self.assertEqual(result["status"], "NOK")
        self.assertIn("down", result["debug"])

    def test_read_timeout_maps_to_neutral(self):
        # ReadTimeout is expected: the outcome arrives later via a notification.
        client = self._make_client()
        with patch(REQUEST_PATH, side_effect=ReadTimeout()):
            result = client._request("POST", "/x", {})
        self.assertEqual(result["status"], "NEUTRAL")


class TestMarketPayRequestWiring(TestMarketPayClientCommon):
    """Endpoint, body and timeout wiring of the public client methods."""

    def test_process_transaction_endpoint_and_timeout(self):
        client = self._make_client()
        with patch(REQUEST_PATH, return_value=self._response(201, {"status": "OK"})) as mocked:
            client.process_transaction({"a": 1})

        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["method"], "POST")
        self.assertTrue(kwargs["url"].endswith("/process-transaction/PAX:1"))
        self.assertEqual(kwargs["data"], json.dumps({"a": 1}))
        self.assertEqual(kwargs["timeout"], MARKETPAY_TIMEOUT)
        self.assertEqual(kwargs["cert"], ("/tmp/cert.pem", "/tmp/key.pem"))
        self.assertTrue(kwargs["verify"])
        self.assertEqual(kwargs["params"], {"waitTime": MARKETPAY_WAIT_TIME_DEFAULT})

    def test_process_transaction_rejects_wait_time_out_of_range(self):
        client = self._make_client()
        with self.assertRaises(ValueError):
            client.process_transaction({"a": 1}, wait_time=0)
        with self.assertRaises(ValueError):
            client.process_transaction({"a": 1}, wait_time=301)

    def test_abort_transaction_endpoint_timeout_and_empty_body(self):
        client = self._make_client()
        with patch(REQUEST_PATH, return_value=self._response(204)) as mocked:
            client.abort_transaction()

        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["method"], "POST")
        self.assertTrue(kwargs["url"].endswith("/abort-transaction/PAX:1"))
        # An empty payload is serialized to None rather than "{}".
        self.assertIsNone(kwargs["data"])
        self.assertEqual(kwargs["timeout"], MARKETPAY_ABORT_TIMEOUT)

    def test_get_sends_no_body(self):
        client = self._make_client()
        with patch(REQUEST_PATH, return_value=self._response(200, [])) as mocked:
            client.get("/terminals", params={"storeCode": "S1"})

        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["method"], "GET")
        self.assertTrue(kwargs["url"].endswith("/terminals"))
        self.assertIsNone(kwargs["data"])
        self.assertEqual(kwargs["params"], {"storeCode": "S1"})


class TestMarketPayInit(TestMarketPayClientCommon):
    """Constructor guards and environment/host resolution."""

    def test_rejects_non_marketpay_payment_method(self):
        pm = self.env["pos.payment.method"].create({
            "name": "Cash only",
            "payment_method_type": "none",
        })
        with self.assertRaises(UserError):
            MarketPay(pm)

    def test_requires_terminal_identifier(self):
        pm = self._make_pm(marketpay_terminal_identifier=False)
        with self.assertRaises(UserError):
            MarketPay(pm)

    def test_test_mode_selects_staging_host(self):
        pm = self._make_pm(
            marketpay_test_mode=True,
            marketpay_path_to_certificate=self.cert_path,
            marketpay_path_to_private_key=self.key_path,
        )
        client = MarketPay(pm)
        self.assertEqual(client.environment, "test")
        self.assertEqual(client.host, MARKETPAY_ENV_HOST_MAP["test"])
        self.assertEqual(client.terminal_id, pm.marketpay_terminal_identifier)

    def test_prod_mode_selects_prod_host(self):
        pm = self._make_pm(
            marketpay_test_mode=False,
            marketpay_path_to_certificate=self.cert_path,
            marketpay_path_to_private_key=self.key_path,
        )
        client = MarketPay(pm)
        self.assertEqual(client.environment, "prod")
        self.assertEqual(client.host, MARKETPAY_ENV_HOST_MAP["prod"])
