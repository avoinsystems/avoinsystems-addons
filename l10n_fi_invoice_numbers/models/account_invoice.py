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

    @api.multi
    @api.depends('number', 'state')
    def _compute_ref_number(self):
        for invoice in self:
            if invoice.number:
                invoice_number = re.sub(r'\D', '', invoice.number)
                checksum = sum((7, 3, 1)[idx % 3] * int(val)
                               for idx, val in enumerate(invoice_number[::-1]))
                invoice.ref_number = invoice_number + str((10 - (checksum % 10)) % 10)
                invoice.invoice_number = invoice_number
            else:
                invoice.invoice_number = False
                invoice.ref_number = False

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
