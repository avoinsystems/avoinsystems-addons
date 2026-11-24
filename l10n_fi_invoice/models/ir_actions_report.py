# Part of Odoo. See LICENSE file for full copyright and licensing details.
# Copyright (C) Avoin.Systems 2020

import io

from odoo import models
from odoo.tools.pdf import NameObject, OdooPdfFileReader, OdooPdfFileWriter, generic

# Distance between the bottom edge of the page and the overlaid bank transfer
# form: 5 mm in PDF points. A point is 1/72 inch and an inch is 25.4 mm, so
# 5 mm is 5 / 25.4 * 72 ≈ 14.2 pt. The placeholder in the template reserves
# the form plus the same 5 mm (its padding-bottom), so the two must match or
# the overlaid form can cover the invoice content above it.
BANK_TRANSFER_FORM_BOTTOM_MARGIN = 5 / 25.4 * 72


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _is_finnish_invoice_report(self):
        self.ensure_one()
        return self.report_name == 'l10n_fi_invoice.report_invoice_finnish_translate'

    def _needs_bank_transfer_form_overlay(self, res_id, stream_data):
        """Whether the PDF stream of ``res_id`` still needs its bank transfer
        form overlaid. Odoo returns a single stream under False when printing
        without records or with duplicated ids. A stream reloaded from a saved
        attachment already has its form."""
        self.ensure_one()
        if not res_id or not stream_data['stream']:
            return False
        return not self.attachment_use or not stream_data['attachment']

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

        The bank transfer form of the Finnish invoice is rendered on its own,
        with ``render_bank_transfer_form_only`` in ``data``, and overlaid on the
        bottom of the last page.
        """
        report = self._get_report(report_ref)
        if report.report_name == 'account.report_invoice_with_payments' and res_ids:
            invoices = self.env['account.move'].browse(res_ids)
            if invoices and all(
                move.company_id.l10n_fi_invoice_set_default for move in invoices
            ):
                report_ref = report = self.env.ref(
                    'l10n_fi_invoice.report_invoice_finnish'
                )
        streams = super()._render_qweb_pdf_prepare_streams(
            report_ref, data, res_ids=res_ids
        )
        if not report._is_finnish_invoice_report():
            return streams

        overlay_ids = [
            res_id
            for res_id, stream_data in streams.items()
            if report._needs_bank_transfer_form_overlay(res_id, stream_data)
        ]
        if not overlay_ids:
            return streams
        form_streams = super()._render_qweb_pdf_prepare_streams(
            report, dict(data or {}, render_bank_transfer_form_only=True), res_ids=overlay_ids
        )
        for res_id in overlay_ids:
            with (
                streams[res_id]['stream'] as invoice_stream,
                form_streams[res_id]['stream'] as form_stream,
            ):
                streams[res_id]['stream'] = self._l10n_fi_overlay_bank_transfer_form(
                    invoice_stream, form_stream
                )
        return streams

    def _l10n_fi_overlay_bank_transfer_form(self, invoice_stream, form_stream):
        """Overlay the single page of ``form_stream`` on the bottom of the last
        page of ``invoice_stream``. The invoice keeps an invisible form to make
        room for it, so its last page is free at the bottom."""
        invoice_pdf = OdooPdfFileReader(invoice_stream, strict=False)
        form_page = OdooPdfFileReader(form_stream, strict=False).getPage(0)
        links = form_page['/Annots']
        anchor = next(
            link for link in links
            if link.get_object()['/A'].get('/URI') == 'https://bank-transfer-form-anchor.invalid/'
        )
        links.remove(anchor)
        offset = BANK_TRANSFER_FORM_BOTTOM_MARGIN - float(anchor.get_object()['/Rect'][1])
        form_page.add_transformation((1, 0, 0, 1, 0, offset))
        self._l10n_fi_shift_links(links, offset)

        output_pdf = OdooPdfFileWriter()
        output_pdf.appendPagesFromReader(invoice_pdf)
        last_page = output_pdf.getPage(-1)
        last_page.mergePage(form_page)
        last_page.compressContentStreams()

        overlaid_stream = io.BytesIO()
        output_pdf.write(overlaid_stream)
        overlaid_stream.seek(0)
        return overlaid_stream

    def _l10n_fi_shift_links(self, links, offset):
        """Shift ``links`` vertically by ``offset`` points, the same way
        add_transformation shifts the content of their page. mergePage copies
        links without moving them along with the content."""
        for link in links:
            annotation = link.get_object()
            x1, y1, x2, y2 = (float(value) for value in annotation['/Rect'])
            annotation[NameObject('/Rect')] = generic.RectangleObject(
                [x1, y1 + offset, x2, y2 + offset]
            )
