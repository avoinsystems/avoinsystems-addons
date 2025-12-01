from odoo.addons.stock_account.tests.test_anglo_saxon_valuation_reconciliation_common import \
    ValuationReconciliationTestCommon
from odoo.tests import tagged, Form, new_test_user, users


@tagged('post_install', '-at_install')
class TestSaleExpectedDate(ValuationReconciliationTestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.test_user = new_test_user(
            cls.env,
            login='sale_user',
            groups='sales_team.group_sale_salesman,stock.group_stock_user'
        )
        cls.partner = cls.env['res.partner'].create(
            {'name': 'A Customer'}
        )

        product = cls.env['product.product']
        cls.product_A = product.create(
            {
                'name': 'Product A',
                'is_storable': True,
                'sale_delay': 5,
                'uom_id': 1,
            }
        )
        cls.product_B = product.create(
            {
                'name': 'Product B',
                'is_storable': True,
                'sale_delay': 10,
                'uom_id': 1,
            }
        )
        cls.product_C = product.create(
            {
                'name': 'Product C',
                'is_storable': True,
                'sale_delay': 15,
                'uom_id': 1,
            }
        )

        cls.env['stock.quant']._update_available_quantity(
            cls.product_A,
            cls.company_data['default_warehouse'].lot_stock_id,
            10
        )
        cls.env['stock.quant']._update_available_quantity(
            cls.product_B,
            cls.company_data['default_warehouse'].lot_stock_id,
            10
        )
        cls.env['stock.quant']._update_available_quantity(
            cls.product_C,
            cls.company_data['default_warehouse'].lot_stock_id,
            10
        )

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

    @users('sale_user')
    def test_expected_date_goes_to_invoice(self):
        sale_order = self.env['sale.order'].create(
            {
                'partner_id': self.partner.id,
                'picking_policy': 'direct',
                'order_line': [(0, 0, {
                    'name': self.product_A.name,
                    'product_id': self.product_A.id,
                    'customer_lead': self.product_A.sale_delay,
                    'product_uom_qty': 5
                }), (0, 0, {
                    'name': self.product_B.name,
                    'product_id': self.product_B.id,
                    'customer_lead': self.product_B.sale_delay,
                    'product_uom_qty': 5
                }), (0, 0, {
                    'name': self.product_C.name,
                    'product_id': self.product_C.id,
                    'customer_lead': self.product_C.sale_delay,
                    'product_uom_qty': 5
                })],
            }
        )

        sale_order.write({'picking_policy': 'one'})

        sale_order.action_confirm()

        picking = sale_order.picking_ids[0]
        for ml in picking.move_line_ids:
            ml.quantity = ml.move_id.product_uom_qty
        picking.button_validate()
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
