__author__ = 'aisopuro'
# Based on account_invoice_sale_link:
# https://github.com/akretion/odoo-usability/blob/8.0/account_invoice_sale_link/account_invoice.py
from openerp import models, fields, api
from openerp.tools.translate import _
from itertools import cycle
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
            checksum = sum((7, 3, 1)[idx % 3] * int(val) for idx, val in enumerate(invoice_number[::-1]))
            self.ref_number = invoice_number + str((10 - (checksum % 10)) % 10)
            self.invoice_number = invoice_number
        else:
            self.invoice_number = False
            self.ref_number = False

    @api.one
    def _decide_date_delivered(self, sales):
        log.warning('_decide_date')
        # Takes a recordset of sale.orders and determines a
        # default date_delivered value based on them
        picking_delivered_dates = sorted(sales.mapped('picking_ids.date_done'))
        log.warning(picking_delivered_dates)
        # Select the last date_done
        return picking_delivered_dates[-1] if picking_delivered_dates else False

    invoice_number = fields.Char(
        'Invoice number',
        compute='_compute_ref_number',
        store=True,
        help=_('Identifier number used to refer to this invoice in accordance with https://www.fkl.fi/teemasivut/sepa/tekninen_dokumentaatio/Dokumentit/kotimaisen_viitteen_rakenneohje.pdf')
    )

    ref_number = fields.Char(
        'Reference Number',
        compute='_compute_ref_number',
        store=True,
        help=_('Invoice reference number in accordance with https://www.fkl.fi/teemasivut/sepa/tekninen_dokumentaatio/Dokumentit/kotimaisen_viitteen_rakenneohje.pdf')
    )

    date_delivered = fields.Date(
        'Date delivered',
        help=_('The date when the invoiced product or service was considered delivered, for taxation purposes.')
    )