# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Avoin.Systems
#    Copyright 2015-2017 Avoin.Systems
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

    @api.one
    @api.depends('number', 'state')
    def _compute_ref_number(self):
        if self.number:
            invoice_number = re.sub(r'\D', '', self.number)
            checksum = sum((7, 3, 1)[idx % 3] * int(val)
                           for idx, val in enumerate(invoice_number[::-1]))
            self.ref_number = invoice_number + str((10 - (checksum % 10)) % 10)
            self.invoice_number = invoice_number
        else:
            self.invoice_number = False
            self.ref_number = False

    @api.one
    def _compute_barcode_string(self):
        displayed_bank_accounts = self.company_id.partner_id.bank_ids\
          .filtered(lambda bank_id: bank_id.journal_id.display_on_footer)
        primary_bank_account = self.partner_bank_id or \
            displayed_bank_accounts and displayed_bank_accounts[0]
        if (self.amount_total and primary_bank_account.acc_number
                and self.ref_number and self.date_due):
            amount_total_string = str(self.amount_total)
            if amount_total_string[-2:-1] == '.':
                amount_total_string += '0'
            amount_total_string = amount_total_string.zfill(9)
            receiver_bank_account = re\
                .sub("[^0-9]", "", str(primary_bank_account.acc_number))
            ref_number_filled = self.ref_number.zfill(20)
            self.barcode_string = '4' \
                                  + receiver_bank_account \
                                  + amount_total_string[:-3] \
                                  + amount_total_string[-2:] \
                                  + "000" + ref_number_filled \
                                  + self.date_due[2:4] \
                                  + self.date_due[5:-3] \
                                  + self.date_due[-2:]
        else:
            self.barcode_string = False

    invoice_number = fields.Char(
        'Invoice number',
        compute='_compute_ref_number',
        store=True,
        help=_('Identifier number used to refer to this invoice in '
               'accordance with https://www.fkl.fi/teemasivut/sepa/'
               'tekninen_dokumentaatio/Dokumentit/kotimaisen_viitte'
               'en_rakenneohje.pdf')
    )

    ref_number = fields.Char(
        'Reference Number',
        compute='_compute_ref_number',
        store=True,
        help=_('Invoice reference number in accordance with https://'
               'www.fkl.fi/teemasivut/sepa/tekninen_dokumentaatio/Do'
               'kumentit/kotimaisen_viitteen_rakenneohje.pdf')
    )

    date_delivered = fields.Date(
        'Date delivered',
        help=_('The date when the invoiced product or service was considered '
               'delivered, for taxation purposes.')
    )

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
        assert len(self) == 1, \
            'This option should only be used for a single id at a time.'
        # noinspection PyAttributeOutsideInit
        self.sent = True
        return self.env['report']\
            .get_action(self,
                        'l10n_fi_invoice.report_invoice_finnish_translate')
