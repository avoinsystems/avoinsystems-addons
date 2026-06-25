# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright (C) Avoin.Systems 2020

from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        """Replace the standard invoice PDF with the Finnish invoice report.

        When every targeted invoice belongs to a company that enabled
        ``l10n_fi_invoice_set_default``, the render of the standard
        ``account.report_invoice_with_payments`` is delegated to the Finnish
        report action ``l10n_fi_invoice.report_invoice_finnish``. Delegating at
        the report-action level (instead of only swapping the QWeb template via
        ``account.move._get_name_invoice_report``) ensures the Finnish
        ``paperformat_finnish`` (zero margins, custom header/footer) and the
        Finnish attachment/filename are used.
        """
        report = self._get_report(report_ref)
        if report.report_name == 'account.report_invoice_with_payments' and res_ids:
            invoices = self.env['account.move'].browse(res_ids)
            if invoices and all(
                move.company_id.l10n_fi_invoice_set_default for move in invoices
            ):
                finnish_report = self.env.ref(
                    'l10n_fi_invoice.report_invoice_finnish'
                )
                return super()._render_qweb_pdf_prepare_streams(
                    finnish_report, data, res_ids=res_ids
                )
        return super()._render_qweb_pdf_prepare_streams(
            report_ref, data, res_ids=res_ids
        )
