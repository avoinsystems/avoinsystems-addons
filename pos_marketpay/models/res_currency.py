from odoo import fields, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    numeric_code = fields.Char(
        help="Currency code in ISO 4217 standard.",
    )
