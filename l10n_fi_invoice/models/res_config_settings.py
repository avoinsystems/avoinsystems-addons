# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright (C) Avoin.Systems 2020

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_fi_invoice_set_default = fields.Boolean(
        related='company_id.l10n_fi_invoice_set_default',
        readonly=False,
    )
