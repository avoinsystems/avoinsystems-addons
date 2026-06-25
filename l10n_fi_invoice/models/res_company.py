# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright (C) Avoin.Systems 2020

from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_fi_invoice_set_default = fields.Boolean(
        string="Use Finnish invoice layout as default invoice PDF",
        help="When enabled, the standard invoice PDF "
             "(account.report_invoice_with_payments) is replaced by the "
             "Finnish invoice report for this company.",
    )
