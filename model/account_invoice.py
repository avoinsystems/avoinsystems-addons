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

from openerp import models, fields, api
# noinspection PyProtectedMember
from openerp.tools.translate import _
import re
import logging

log = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def _compute_barcode_string(self):
        for invoice in self:
            primary_bank_account = invoice.partner_bank_id or \
                invoice.company_id.partner_id.bank_ids and \
                invoice.company_id.partner_id.bank_ids[0]
            if not (invoice.amount_total and
                    primary_bank_account and
                    primary_bank_account.acc_number and
                    invoice.payment_reference_type and
                    invoice.payment_reference and
                    invoice.date_due):
                invoice.barcode_string = False
                return
            if invoice.payment_reference_type == 'fi':
                version = '4'
                reserved = '000'
                pay_ref = invoice.payment_reference.zfill(20)
            elif invoice.payment_reference_type == 'rf':
                version = '5'
                reserved = ''
                pay_ref = invoice.payment_reference[2:]  # Cut off RF
                length = 23 - len(pay_ref)
                pay_ref = pay_ref[:2] + '0'*length + pay_ref[2:]
            else:
                invoice.barcode_string = False
                return
            # Bank account sans letters
            bank_account = re.sub("[^0-9]", "", str(primary_bank_account.acc_number))
            amount_total_string = '%.2f' % invoice.amount_total
            amount_total_string = amount_total_string.zfill(9)
            amount_euros = amount_total_string[:-3]
            amount_cents = amount_total_string[-2:]
            invoice.barcode_string = ''.join([
                version,
                bank_account,
                amount_euros,
                amount_cents,
                reserved,
                pay_ref,
                invoice.date_due[2:4],  # Year
                invoice.date_due[5:7],  # Month
                invoice.date_due[8:],  # Date
            ])


    def _compute_default_delivered(self):
        return fields.Date.today()

    date_delivered = fields.Date(
        'Date delivered',
        default=_compute_default_delivered,
        help=_('The date when the invoiced product or service was considered '
               'delivered, for taxation purposes.')
    )

    barcode_string = fields.Char(
        'Barcode String',
        compute='_compute_barcode_string',
        help=_('Barcode generated in accordance with http://www.finanssiala.fi/maksujenvalitys/dokumentit/Pankkiviivakoodi-opas.pdf')
    )
