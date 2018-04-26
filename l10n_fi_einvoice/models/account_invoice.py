# -*- coding: utf-8 -*-
# Copyright 2018 Akretion (Alexis de Lattre <alexis.delattre@akretion.com>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def get_payment_identifier(self):
        if self.ref_number:
            return self.ref_number
        else:
            return super(AccountInvoice, self).get_payment_identifier()
