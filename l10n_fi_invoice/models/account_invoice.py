##############################################################################
#
#    Author: Avoin.Systems
#    Copyright 2015-2019 Avoin.Systems
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

from odoo import models, fields, api
# noinspection PyProtectedMember
from odoo.tools.translate import _
import re
import logging

log = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def _get_invoice_pdf_filename(self):
        type_string = 'Invoice'
        invoice_numbers = self.number or ''
        if self.type in ('in_refund', 'out_refund'):
            type_string = 'Refund'
            invoice_numbers = '-'.join((
                invoice_numbers, self.refund_invoice_id.number))
        filename = '-'.join((
            type_string,
            invoice_numbers,
            self.company_id.display_name,
            self.partner_id.display_name)). \
            replace(' ', '-').replace(',', '').replace('--', '-')
        return filename

    @api.multi
    def _compute_barcode_string(self):
        for invoice in self:
            displayed_bank_accounts = invoice.company_id.partner_id.bank_ids.filtered('journal_id.include_on_invoice')
            primary_bank_account = invoice.partner_bank_id or \
                displayed_bank_accounts and displayed_bank_accounts[0]
            if (invoice.amount_total and primary_bank_account.acc_number
                    and invoice.ref_number and invoice.date_due):
                amount_total_string = str(invoice.amount_total)
                if amount_total_string[-2:-1] == '.':
                    amount_total_string += '0'
                amount_total_string = amount_total_string.zfill(9)
                receiver_bank_account = re\
                    .sub("[^0-9]", "", str(primary_bank_account.acc_number))
                ref_number_filled = invoice.ref_number.zfill(20)
                invoice.barcode_string = '4' \
                                      + receiver_bank_account \
                                      + amount_total_string[:-3] \
                                      + amount_total_string[-2:] \
                                      + "000" + ref_number_filled \
                                      + invoice.date_due.strftime('%y%m%d')
            else:
                invoice.barcode_string = False

    barcode_string = fields.Char(
        'Barcode String',
        compute='_compute_barcode_string',
        help=_('https://www.fkl.fi/teemasivut/sepa/tekninen_dokumentaatio/Dok'
               'umentit/Pankkiviivakoodi-opas.pdf')
    )

    @api.multi
    def invoice_print(self):
        """ Print the invoice and mark it as sent, so that we can see more
            easily the next step of the workflow
        """
        self.ensure_one()
        # noinspection PyAttributeOutsideInit
        self.sent = True
        return self.env.ref('l10n_fi_invoice.report_invoice_finnish').report_action(self)
