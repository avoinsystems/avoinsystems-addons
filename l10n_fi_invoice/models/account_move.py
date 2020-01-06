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
            type_string = 'Refund'
            invoice_numbers = '-'.join((
                invoice_numbers, self.refund_invoice_id.name))
        filename = '-'.join((
            type_string,
            invoice_numbers,
            self.company_id.display_name,
            self.partner_id.display_name)). \
            replace(' ', '-').replace(',', '').replace('--', '-')
        return filename

    def _compute_barcode_string(self):
        for invoice in self:
            displayed_bank_accounts = invoice.company_id.partner_id.bank_ids.filtered('journal_id.include_on_invoice')
            primary_bank_account = invoice.invoice_partner_bank_id or \
                displayed_bank_accounts and displayed_bank_accounts[0]
            if invoice.amount_total \
                and primary_bank_account.acc_number \
                and invoice.ref_number \
                and invoice.invoice_date_due:
                if invoice.currency_id.compare_amounts(BARCODE_AMOUNT_LIMIT, invoice.amount_total) == -1:
                    # Amount is too large, we choose the option of replacing the amount with zeros (in accordance with
                    # https://www.finanssiala.fi/maksujenvalitys/dokumentit/Pankkiviivakoodi-opas.pdf)
                    # so that at least some use can be gotten from the barcode
                    euros = "000000"
                    cents = "00"
                else:
                    full_amount = invoice.currency_id.round(invoice.amount_total)
                    euros, cents = "{:.2f}".format(full_amount).zfill(9).split('.')
                receiver_bank_account = re\
                    .sub("[^0-9]", "", str(primary_bank_account.acc_number))
                ref_number_filled = invoice.ref_number.zfill(20)
                invoice.barcode_string = '4' \
                                      + receiver_bank_account \
                                      + str(euros) \
                                      + str(cents) \
                                      + "000" + ref_number_filled \
                                      + invoice.invoice_date_due.strftime('%y%m%d')
            else:
                invoice.barcode_string = False

    barcode_string = fields.Char(
        'Barcode String',
        compute='_compute_barcode_string',
        help=_('https://www.finanssiala.fi/maksujenvalitys/dok'
               'umentit/Pankkiviivakoodi-opas.pdf')
    )

    def invoice_print(self):
        """ Print the invoice and mark it as sent, so that we can see more
            easily the next step of the workflow
        """
        self.ensure_one()
        # noinspection PyAttributeOutsideInit
        self.sent = True
        return self.env.ref('l10n_fi_invoice.report_invoice_finnish').report_action(self)
