# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright (C) Avoin.Systems 2020

from odoo import models, fields
# noinspection PyProtectedMember
from odoo.tools.translate import _
import re
import logging

log = logging.getLogger(__name__)

BARCODE_AMOUNT_LIMIT = 999999.99


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_invoice_pdf_filename(self):
        type_string = 'Invoice'
        invoice_numbers = self.name or ''
        if self.type in ('in_refund', 'out_refund'):
            type_string = 'Credit_Note'
        filename = '-'.join((
            type_string,
            invoice_numbers,
            self.company_id.display_name,
            self.partner_id.display_name)). \
            replace(' ', '-').replace(',', '').replace('--', '-')
        return filename

    def invoice_print(self):
        """ Print the invoice and mark it as sent, so that we can see more
            easily the next step of the workflow
        """
        self.ensure_one()
        # noinspection PyAttributeOutsideInit
        self.sent = True
        return self.env.ref('l10n_fi_invoice.report_invoice_finnish').report_action(self)
