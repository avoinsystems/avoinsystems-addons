# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Avoin.Systems
#    Copyright 2015 Avoin.Systems
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
import logging
import math

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class InvoiceBarcode(models.Model):
    _inherit = 'account.move'

    bank_barcode = fields.Char(string='Bank Barcode', compute='_compute_bank_barcode', store=True)

    def _get_amount_str(self, amount):
        if amount and amount > 0: # No negative payments
            snt, eur = math.modf(amount)
            eur_str = str(int(eur)).rjust(6, '0')
            snt_str = str(int(round(snt * 100))).rjust(2, '0')
            return eur_str + snt_str
        return None

    def _get_date_str(self, date):
        if date:
            return fields.Date.from_string(date).strftime("%y%m%d")
        return None

    def _get_iban_str(self, bank_account):
        if bank_account:
            acc_num = bank_account.acc_number
            if len(acc_num) == 18 and acc_num[:2] == 'FI' and acc_num[2:].isdigit():
                return acc_num[2:]
            return None
        return None

    def _get_version(self, ref):
        if ref and ' ' not in ref:
            if ref[:2] == 'RF' and ref[2:].isdigit():
                return 5
            elif ref.isdigit():
                return 4
            return None
        return None

    def _get_rf_ref_str(self, ref):
        if ref and ref[:2] == 'RF' and ref[2:].isdigit() and len(ref) <= 25 and len(ref) >= 8:
            start = ref[2:4]
            end = ref[4:].rjust(21, '0')
            return start + end
        return None

    def _get_fin_ref_str(self, ref):
        if ref and len(ref) <= 20 and len(ref) >= 4:
            return ref.rjust(20, '0')
        return None

    @api.depends('currency_id', 'amount_total', 'invoice_date_due',
                 'invoice_payment_ref', 'invoice_partner_bank_id')
    def _compute_bank_barcode(self):
        for record in self:

            # Only EUR invoices are supported
            # Since the default company currency is now USD, we have to bypass
            # this check in the unit tests using the test_bank_barcode flag.
            if record.company_currency_id.name != 'EUR' \
                    and not self._context.get('test_bank_barcode'):
                record.bank_barcode = False
                continue

            if record.is_invoice():
                version = record._get_version(record.invoice_payment_ref)  # Barcode version

                if version:
                    inv_sum_str = record._get_amount_str(record.amount_total)
                    inv_date_str = record._get_date_str(record.invoice_date_due)
                    inv_iban_str = record._get_iban_str(record.invoice_partner_bank_id)

                    if version == 5:
                        inv_extra_str = ''  # No padding for version 5
                        inv_ref_str = record._get_rf_ref_str(record.invoice_payment_ref)
                    else:
                        inv_extra_str = '000'  # Padding for version 4
                        inv_ref_str = record._get_fin_ref_str(record.invoice_payment_ref)

                    if inv_sum_str and inv_date_str and inv_ref_str and inv_iban_str:
                        record.bank_barcode = str(version) + inv_iban_str + \
                            inv_sum_str + inv_extra_str + inv_ref_str + inv_date_str
                    else:
                        record.bank_barcode = False
                else:
                    record.bank_barcode = False
            else:
                record.bank_barcode = False
