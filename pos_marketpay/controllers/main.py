import json
import logging
from odoo import http
from odoo.http import request
from werkzeug.exceptions import Forbidden

_logger = logging.getLogger(__name__)


class PosMarketpayController(http.Controller):

    @http.route(
        "/pos_marketpay/notification/<string:terminal_id>/<string:secret>/<string:transaction_id>",
        type="http",
        methods=["POST"],
        auth="public",
        csrf=False,
        save_session=False,
    )
    def notification(self, terminal_id, secret, transaction_id):
        message = json.loads(request.httprequest.data)

        _logger.info(
            f"""
            Notification received from Market Pay.
            Message: {message}
            Terminal ID: {terminal_id}
            Transaction ID: {transaction_id}
            """
        )

        marketpay_pm_sudo = request.env["pos.payment.method"].sudo().search([
            ("marketpay_terminal_identifier", "=", terminal_id),
        ], limit=1)
        if not marketpay_pm_sudo:
            _logger.warning("Received a Market Pay event notification for a terminal not registered in Odoo: %s", terminal_id)
            return

        # Validate the pre-shared secret embedded in the notification URL.
        # The URL is generated server-side and handed to Market Pay with each
        # transaction request, so a valid secret proves the caller received
        # that URL from us. Constant-time comparison avoids leaking the
        # secret via response timing.
        if not marketpay_pm_sudo._verify_marketpay_notification_secret(secret):
            _logger.warning(
                "Rejected Market Pay notification with invalid secret for terminal %s (transaction %s).",
                terminal_id,
                transaction_id,
            )
            raise Forbidden()

        received_data = {
            "message": message,
            "terminal_id": terminal_id,
            "transaction_id": transaction_id,
        }

        return self._process_payment_response(received_data, marketpay_pm_sudo)

    def _process_payment_response(self, data, marketpay_pm_sudo):
        transaction_id = data.get("transaction_id")

        if not transaction_id:
            return

        transaction_id_parts = transaction_id.split("--")
        if len(transaction_id_parts) != 2:
            return

        pos_session_id = int(transaction_id_parts[1])
        pos_session_sudo = request.env["pos.session"].sudo().browse(pos_session_id)

        marketpay_pm_sudo.latest_marketpay_notification = json.dumps(data)
        pos_session_sudo.config_id._notify("MARKETPAY_LATEST_RESPONSE", pos_session_sudo.config_id.id)

        return request.make_json_response("accepted")
