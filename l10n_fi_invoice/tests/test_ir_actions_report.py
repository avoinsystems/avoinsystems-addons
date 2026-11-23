import io

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged
from odoo.tools.pdf import OdooPdfFileReader


@tagged("post_install", "-at_install")
class TestFinnishInvoicePdf(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The invoice is printed in the customer's language, and the test looks
        # for the English label of the bank transfer form
        cls.partner_a.lang = "en_US"

    def test_batch_with_multi_page_invoice_has_every_bank_transfer_form(self):
        short_invoice = self._create_invoice_one_line(product_id=self.product_a)
        long_invoice = self._create_invoice(
            invoice_line_ids=[
                self._prepare_invoice_line(product_id=self.product_a) for _ in range(40)
            ],
        )

        pdf, _report_type = (
            self.env["ir.actions.report"]
            .with_context(force_report_rendering=True)
            ._render_qweb_pdf(
                "l10n_fi_invoice.report_invoice_finnish", (short_invoice + long_invoice).ids
            )
        )

        pages = OdooPdfFileReader(io.BytesIO(pdf), strict=False).pages
        pages_with_form = [page for page in pages if "Debtor" in page.extract_text()]
        self.assertEqual(2, len(pages_with_form))
