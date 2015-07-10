__author__ = 'aisopuro'
# Based on account_invoice_sale_link:
# https://github.com/akretion/odoo-usability/blob/8.0/account_invoice_sale_link/account_invoice.py
from openerp import models, fields, api
from itertools import cycle
import logging


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.one
    @api.depends('origin')
    def _compute_sale_ids(self):
        self.sale_ids = self.env['sale.order'].search([('name', '=', self.origin)]) or False

    @api.multi
    def _compute_ref_number(self):
        for record in self:
            base = str(record.id + 99)  # Need at least 3 digits
            factors = cycle((7, 3, 1))
            result = 0
            for digit in str(base):
                result += int(digit) * next(factors)
            record.ref_number = base + str((10 - (result % 10)) % 10)

    sale_ids = fields.Many2many(
        'sale.order',
        compute='_compute_sale_ids',
        store=True
    )

    ref_number = fields.Char(
        'Reference Number',
        compute='_compute_ref_number',
        help='Invoice reference number in accordance with https://www.fkl.fi/teemasivut/sepa/tekninen_dokumentaatio/Dokumentit/kotimaisen_viitteen_rakenneohje.pdf',
        store=True
    )