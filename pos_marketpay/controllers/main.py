import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosMarketpayController(http.Controller):

    @http.route("/pos_marketpay/notification/<string:terminal_id>/<string:transaction_id>", type="http", methods=["POST"], auth="public", csrf=False, save_session=False)
    def notification(self, terminal_id, transaction_id):
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
        request.env["bus.bus"].sudo()._sendone(pos_session_sudo._get_bus_channel_name(), "MARKETPAY_LATEST_RESPONSE", pos_session_sudo.config_id.id)

        return request.make_json_response("accepted")
