# See LICENSE for licensing information

from odoo import models, fields


class AccountMove(models.Model):
    _inherit = "account.move"

    date_delivered = fields.Date(
        "Date Delivered",
        help=(
            "The date when the invoiced product or service was considered "
            "delivered, for taxation purposes."
        ),
    )
