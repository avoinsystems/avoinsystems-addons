# See LICENSE for licensing information

import logging
from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):

    _inherit = 'sale.order'

    def _prepare_invoice(self):
        self.ensure_one()
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.effective_date:
            invoice_vals['date_delivered'] = self.effective_date
        return invoice_vals
