from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_pos_payment_method(self):
        result = super()._loader_params_pos_payment_method()
        result["search_params"]["fields"].append("marketpay_terminal_identifier")
        return result

    def _loader_params_res_currency(self):
        result = super()._loader_params_res_currency()
        result["search_params"]["fields"].append("numeric_code")
        return result
