from datetime import timedelta

from odoo import fields
from odoo.addons.stock_account.tests.test_anglo_saxon_valuation_reconciliation_common import \
    ValuationReconciliationTestCommon
from odoo.tests import tagged, Form


@tagged('post_install', '-at_install')
class TestSaleExpectedDate(ValuationReconciliationTestCommon):

    def _do_invoicing(self, sale: 'sale.order') -> 'account.move':
        """
        Invoice the given sale
        """
        context = {
            "active_model": sale._name,
            "active_id": sale.id,
            "active_ids": sale.ids,
            "open_invoices": True,  # To get the invoices back
        }
        InvoiceWizard = \
            self.env["sale.advance.payment.inv"].with_context(**context)
        wizard: InvoiceWizard = Form(InvoiceWizard)
        action = wizard.save().create_invoices()
        invoice = self.env["account.move"].browse(action["res_id"])
        assert invoice
        return invoice

    def test_expected_date_goes_to_invoice(self):
        Product = self.env['product.product']

        product_A = Product.create(
            {
                'name': 'Product A',
                'type': 'product',
                'sale_delay': 5,
                'uom_id': 1,
            }
        )
        product_B = Product.create(
            {
                'name': 'Product B',
                'type': 'product',
                'sale_delay': 10,
                'uom_id': 1,
            }
        )
        product_C = Product.create(
            {
                'name': 'Product C',
                'type': 'product',
                'sale_delay': 15,
                'uom_id': 1,
            }
        )

        self.env['stock.quant']._update_available_quantity(
            product_A,
            self.company_data['default_warehouse'].lot_stock_id,
            10
        )
        self.env['stock.quant']._update_available_quantity(
            product_B,
            self.company_data['default_warehouse'].lot_stock_id,
            10
        )
        self.env['stock.quant']._update_available_quantity(
            product_C,
            self.company_data['default_warehouse'].lot_stock_id,
            10
        )

        sale_order = self.env['sale.order'].create(
            {
                'partner_id': self.env['res.partner'].create(
                    {'name': 'A Customer'}
                ).id,
                'picking_policy': 'direct',
                'order_line': [(0, 0, {
                    'name': product_A.name,
                    'product_id': product_A.id,
                    'customer_lead': product_A.sale_delay,
                    'product_uom_qty': 5
                }), (0, 0, {
                    'name': product_B.name,
                    'product_id': product_B.id,
                    'customer_lead': product_B.sale_delay,
                    'product_uom_qty': 5
                }), (0, 0, {
                    'name': product_C.name,
                    'product_id': product_C.id,
                    'customer_lead': product_C.sale_delay,
                    'product_uom_qty': 5
                })],
            }
        )

        sale_order.write({'picking_policy': 'one'})

        sale_order.action_confirm()

        picking = sale_order.picking_ids[0]
        for ml in picking.move_line_ids:
            ml.qty_done = ml.product_uom_qty
        picking._action_done()
        self.assertEqual(
            picking.state,
            'done',
            "Picking not processed correctly!"
        )

        self.assertTrue(
            sale_order.effective_date,
            "Wrong effective date on sale order!"
        )

        invoice = self._do_invoicing(sale_order)
        self.assertEqual(
            invoice.date_delivered,
            sale_order.effective_date.date(),
        )
