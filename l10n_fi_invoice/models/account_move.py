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
        if self.move_type in ('in_refund', 'out_refund'):
            type_string = 'Credit_Note'
        filename = '-'.join((
            type_string,
            invoice_numbers,
            self.company_id.display_name,
            self.partner_id.display_name or '')). \
            replace(' ', '-').replace(',', '').replace('--', '-')
        return filename
