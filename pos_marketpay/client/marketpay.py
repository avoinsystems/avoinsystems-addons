import logging
import json
import os
import time
from requests import request
from requests.exceptions import ReadTimeout, SSLError, ConnectionError
from odoo import _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

MARKETPAY_ENV_HOST_MAP = {
    "test": "https://eci-stg.market-pay.com",
    "prod": "https://eci.market-pay.com",
}

MARKETPAY_TIMEOUT = 310 # Market Pay timeout is 300s


class MarketPay():

    def __init__(self, pos_payment_method):
        super().__init__()

        if pos_payment_method.use_payment_terminal != "marketpay":
            raise UserError(_(
                "This client is only meant to be used with Market Pay."
            ))

        self.environment = "test" if pos_payment_method.marketpay_test_mode else "prod"
        self.host = MARKETPAY_ENV_HOST_MAP.get(self.environment)

        if not pos_payment_method.marketpay_terminal_identifier:
            raise UserError(_(
                "Market Pay Terminal Identifier is not set."
            ))
        self.terminal_id = pos_payment_method.marketpay_terminal_identifier

        if not pos_payment_method.marketpay_path_to_certificate:
            raise UserError(_(
                "The path to the Market Pay certificate is not configured. "
                "To set it, go to the Market Pay payment method settings "
                "and enter the path in the \"Path to Certificate\" field."
            ))

        if not os.path.exists(pos_payment_method.marketpay_path_to_certificate):
            raise UserError(_(
                "Market Pay certificate file does not exist."
            ))

        if not os.access(pos_payment_method.marketpay_path_to_certificate, os.R_OK):
            raise UserError(_(
                "Odoo does not have permissions to read Market Pay certificate file."
            ))

        self.path_certificate = pos_payment_method.marketpay_path_to_certificate

        if not pos_payment_method.marketpay_path_to_private_key:
            raise UserError(_(
                "The path to the Market Pay private key is not configured. "
                "To set it, go to the Market Pay payment method settings "
                "and enter the path in the \"Path to Private Key\" field."
            ))

        if not os.path.exists(pos_payment_method.marketpay_path_to_private_key):
            raise UserError(_(
                "Market Pay private key file does not exist."
            ))

        if not os.access(pos_payment_method.marketpay_path_to_private_key, os.R_OK):
            raise UserError(_(
                "Odoo does not have permissions to read Market Pay private key file."
            ))

        self.path_privatekey = pos_payment_method.marketpay_path_to_private_key

    def _get_url(self, endpoint):
        url = self.host.rstrip("/")
        endpoint = endpoint.lstrip("/")
        return f"{url}/{endpoint}"

    def _request(self, method, endpoint, data, params=None, **kwargs):
        request_uid = time.time()

        if params is None:
            params = {}

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Odoo",
        }

        url = self._get_url(endpoint)

        _logger.debug(
            (
                "\n"
                "Market Pay request:\n"
                "- UID: {request_uid}\n"
                "- endpoint: {url}\n"
                "- method: {method}\n"
                "- params: {params}\n"
                "- payload: \n{data}\n"
            ).format(
                request_uid=request_uid,
                url=url,
                method=method,
                params=params,
                data=json.dumps(data, indent=4),
            )
        )

        try:
            res = request(
                method=method,
                url=url,
                params=params,
                data=data and json.dumps(data) or None,
                headers=headers,
                cert=(self.path_certificate, self.path_privatekey),
                verify=True,
                **kwargs
            )

            _logger.debug(
                (
                    "\n"
                    "Market Pay response:\n"
                    "- UID: {request_uid}\n"
                    "- request endpoint: {url}\n"
                    "- request method: {method}\n"
                    "- request params: {params}\n"
                    "- request payload: \n{data}\n"
                    "- response code: {response_code}\n"
                    "- response content: \n{response_content}\n"
                ).format(
                    request_uid=request_uid,
                    url=url,
                    method=method,
                    params=params,
                    data=json.dumps(data, indent=4),
                    response_code=res.status_code,
                    response_content=res.text,
                )
            )

            if res.status_code in [200, 201]:
                try:
                    return res.json()
                except json.decoder.JSONDecodeError:
                    return res

            elif res.status_code in [204]:
                return {
                    "status": "OK",
                    "debug": "204 received. Success without content.",
                }

            elif res.status_code == 202:
                res = {
                    "status": "NEUTRAL",
                    "debug": "202 received. Response will be sent as a notification...",
                }
                return res

            else:
                raise ValidationError("Market Pay responded with non-ok status code [%s]: %s" % (res.status_code, res.text))

        except SSLError:
            res = {
                "status": "NOK",
                "message": _("Authentication failed. Please verify that the certificate and private key are valid."),
            }

        except ValidationError as err:
            res = {
                "status": "NOK",
                "debug": str(err),
            }

        except ConnectionError as err:
            res = {
                "status": "NOK",
                "debug": str(err),
            }

        except ReadTimeout:
            # ReadTimeout is OK because we'll receive notifications from MarkerPay about status changes
            res = {
                "status": "NEUTRAL",
                "debug": "ReadTimeout occurred. Continuing...",
            }

        return res

    def post(self, endpoint, data, **kwargs):
        return self._request("POST", endpoint, data, **kwargs)

    def get(self, endpoint, **kwargs):
        return self._request("GET", endpoint, None, **kwargs)

    def process_transaction(self, data):
        return self.post(f"/process-transaction/{self.terminal_id}", data, timeout=MARKETPAY_TIMEOUT)

    def cancel_transaction(self, data):
        return self.post(f"/cancel-transaction/{self.terminal_id}", data, timeout=MARKETPAY_TIMEOUT)

    def abort_transaction(self):
        return self.post(f"/abort-transaction/{self.terminal_id}", {})
