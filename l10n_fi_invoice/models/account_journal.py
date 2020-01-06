# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright (C) Avoin.Systems 2020

from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    include_on_invoice = fields.Boolean(
        "Include on Invoice",
        help="Include this bank account in Finnish invoices generated for the associated company",
        default=True
    )
