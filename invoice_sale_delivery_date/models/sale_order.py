# See LICENSE for licensing information

import logging
from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):

    _inherit = 'sale.order'

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.effective_date:  # super ensures_one
            invoice_vals['date_delivered'] = self.effective_date.date()
        return invoice_vals
