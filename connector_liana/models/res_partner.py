from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    liana_extra1 = fields.Char(
        string="Liana ID",
        help="External unique identifier sent to Liana Automation as 'extra1'.",
        readonly=True,
    )

    liana_token = fields.Char(
        string="Liana Token",
        copy=False,
        help="Cookie identifier sent to Liana Automation as 'token'.",
        readonly=True,
    )
