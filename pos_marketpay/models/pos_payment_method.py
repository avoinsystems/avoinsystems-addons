import json
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, AccessDenied, UserError
from ..client.marketpay import MarketPay


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _get_payment_terminal_selection(self):
        return super()._get_payment_terminal_selection() + [("marketpay", "Market Pay")]

    marketpay_path_to_certificate = fields.Char(
        string="Path to Certificate",
        groups="base.group_erp_manager",
    )

    marketpay_path_to_private_key = fields.Char(
        string="Path to Private Key",
        groups="base.group_erp_manager",
    )

    marketpay_terminal_identifier = fields.Char(
        string="Terminal Identifier",
        copy=False,
    )

    marketpay_terminal_lang_code = fields.Char(
        string="Language Code",
        groups="base.group_erp_manager",
        default="EN",
    )

    marketpay_printer_available = fields.Boolean(
        string="Printer Available",
        groups="base.group_erp_manager",
    )

    marketpay_test_mode = fields.Boolean(
        string="Test Mode",
        groups="base.group_erp_manager",
    )

    latest_marketpay_notification = fields.Char(
        copy=False,
        groups="base.group_erp_manager",
    )

    marketpay_store_code = fields.Char(
        string="Store Code",
        copy=False,
        groups="base.group_erp_manager",
    )

    marketpay_registered_terminals = fields.Text(
        copy=False,
        readonly=True,
        groups="base.group_erp_manager",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        result = super()._load_pos_data_fields(config)
        result.append("marketpay_terminal_identifier")
        return result

    def _loader_params_pos_payment_method(self):
        result = super()._loader_params_pos_payment_method()
        result["search_params"]["fields"].append("marketpay_terminal_identifier")
        return result

    @api.constrains("marketpay_terminal_identifier")
    def _check_marketpay_terminal_identifier(self):
        for rec in self:
            if not rec.marketpay_terminal_identifier:
                continue

            payment_method = self.sudo().search([
                ("id", "!=", rec.id),
                ("marketpay_terminal_identifier", "=", rec.marketpay_terminal_identifier),
            ], limit=1)

            if payment_method:
                if rec.company_id == payment_method.company_id:
                    raise ValidationError(
                        _("Terminal {terminal} is already used on payment method {method}.").format(
                            terminal=rec.marketpay_terminal_identifier,
                            method=rec.display_name,
                        )
                    )

                raise ValidationError(
                    _("Terminal {terminal} is already used in company {company} on payment method {method}.").format(
                        terminal=payment_method.marketpay_terminal_identifier,
                        company=payment_method.company_id.name,
                        method=payment_method.display_name,
                    )
                )

    def _is_write_forbidden(self, fields):
        return super()._is_write_forbidden(fields - {"latest_marketpay_notification"})

    def get_latest_marketpay_message(self):
        self.ensure_one()

        if not self.env.su and not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessDenied()

        latest_response = self.sudo().latest_marketpay_notification
        latest_response = json.loads(latest_response) if latest_response else False

        return latest_response

    def prevalidate_marketpay_request(self):
        self.ensure_one()

        if not self.env.su and not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessDenied()

    def marketpay_request_process_transaction(self, values):
        self.ensure_one()
        self.prevalidate_marketpay_request()

        self_sudo = self.sudo()

        is_refund = values["is_refund"]
        transaction_type = "REFUND" if is_refund else "PURCHASE"
        amount = values["amount"]

        if is_refund and amount >= 0:
            raise ValidationError(_("Amount must be negative."))

        if not is_refund and amount <= 0:
            raise ValidationError(_("Amount must be positive."))

        base_url = self_sudo.env["ir.config_parameter"].get_param("web.base.url").rstrip("/")
        transaction_id = values["ecrTransactionId"]

        payload = {
            "ecrTransactionId": transaction_id,
            "cashierId": values["cashierId"],
            "amount": abs(amount),
            "currency": values["currency"],
            "transactionReference": values["transactionReference"],
            "ecrParams": {
                "notificationUrl": f"{base_url}/pos_marketpay/notification/{self_sudo.marketpay_terminal_identifier}/{transaction_id}",
                "ecrId": values["ecrId"],
                "printerAvailable": self_sudo.marketpay_printer_available,
                "operatorLanguage": self_sudo.marketpay_terminal_lang_code,
            },
            "transactionType": transaction_type,
            "transactionMode": "DIRECT",
            "amountTip": 0,
            "amountCashback": 0,
            "merchantOption": "",
        }

        return MarketPay(self_sudo).process_transaction(payload)

    def marketpay_request_cancel_transaction(self, values):
        self.ensure_one()
        self.prevalidate_marketpay_request()

        self_sudo = self.sudo()

        base_url = self_sudo.env["ir.config_parameter"].get_param("web.base.url").rstrip("/")
        transaction_id = values["ecrTransactionId"]

        payload = {
            "terminalTransactionId": values["terminalTransactionId"],
            "ecrTransactionId": transaction_id,
            "cashierId": values["cashierId"],
            "amount": values["amount"],
            "currency": values["currency"],
            "ecrParams": {
                "ecrId": values["ecrId"],
                "notificationUrl": f"{base_url}/pos_marketpay/notification/{self_sudo.marketpay_terminal_identifier}/{transaction_id}",
                "printerAvailable": self_sudo.marketpay_printer_available,
                "operatorLanguage": self_sudo.marketpay_terminal_lang_code,
            }
        }

        return MarketPay(self_sudo).cancel_transaction(payload)

    def marketpay_request_abort_transaction(self, values):
        self.ensure_one()
        self.prevalidate_marketpay_request()

        self_sudo = self.sudo()

        return MarketPay(self_sudo).abort_transaction()

    def get_regitered_terminals_from_marketpay(self):
        self.ensure_one()

        if not self.marketpay_store_code:
            raise UserError(_("Store Code is required to fetch registered terminals."))

        terminals = MarketPay(self).get("/terminals", params={
            "storeCode": self.marketpay_store_code,
            "ecrId": 1, # currently required, but inactive option
        })

        self.marketpay_registered_terminals = terminals

    def test_certificate_access(self):
        self.ensure_one()
        MarketPay(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "sticky": False,
                "message": _("Market Pay terminal configuration looks good!"),
                "next": {"type": "ir.actions.act_window_close"},
            }
        }
