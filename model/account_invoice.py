__author__ = 'aisopuro'
# Based on account_invoice_sale_link:
# https://github.com/akretion/odoo-usability/blob/8.0/account_invoice_sale_link/account_invoice.py
from openerp import models, fields, api
from openerp.tools.translate import _
from itertools import cycle
import re
import logging


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.one
    @api.depends('origin')
    def _compute_sale_ids(self):
        self.sale_ids = self.env['sale.order'].search([('name', '=', self.origin)]) or False

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

    sale_ids = fields.Many2many(
        'sale.order',
        compute='_compute_sale_ids',
        store=True
    )

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