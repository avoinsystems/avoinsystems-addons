import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .liana_backend import AUTOMATION_API_EVENT_PATH, LianaError

_logger = logging.getLogger(__name__)


class LianaEvent(models.Model):
    _name = "liana.event"
    _description = "Liana Automation Event"
    _order = "id desc"

    name = fields.Char(string="Name")

    state = fields.Selection(
        selection=[
            ("new", "New"),
            ("exported", "Exported"),
            ("failed", "Export Failed"),
        ],
        default="new",
        required=True,
    )

    action_id = fields.Many2one(
        string="Server Action",
        comodel_name="ir.actions.server",
        domain="[('state', '=', 'liana')]",
        ondelete="set null",
    )

    backend_id = fields.Many2one(
        string="Liana Backend",
        comodel_name="liana.backend",
        ondelete="restrict",
        readonly=True,
        default=lambda self: self.env["liana.backend"]._get_default_backend(),
        help="Backend that handled (or should handle, on retry) this event.",
    )

    base_automation_id = fields.Many2one(
        string="Automation Rule",
        comodel_name="base.automation",
        related="action_id.base_automation_id",
        store=True,
    )

    res_model = fields.Char(
        string="Source Model",
        related="action_id.model_id.model",
        store=True,
    )

    res_id = fields.Integer(string="Source Record ID", readonly=True)

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contact",
        readonly=True,
        index=True,
        ondelete="set null",
        help="Liana identity record when it is a res.partner.",
    )

    lead_id = fields.Many2one(
        comodel_name="crm.lead",
        string="Lead",
        readonly=True,
        index=True,
        ondelete="set null",
        help="Liana identity record when it is a crm.lead.",
    )

    payload = fields.Json()

    payload_text = fields.Text(
        string="Payload (JSON)",
        compute="_compute_payload_text",
        inverse="_inverse_payload_text",
    )

    response = fields.Json()

    @api.depends("payload")
    def _compute_payload_text(self):
        for rec in self:
            if rec.payload in (False, None):
                rec.payload_text = ""
            else:
                rec.payload_text = json.dumps(rec.payload, indent=2, ensure_ascii=False)

    def _inverse_payload_text(self):
        for rec in self:
            rec.payload = rec._parse_payload_text(rec.payload_text)

    @api.model
    def _parse_payload_text(self, text):
        if text is None or (isinstance(text, str) and not text.strip()):
            return False
        try:
            return json.loads(text)
        except json.JSONDecodeError as err:
            raise ValidationError(_("Invalid JSON in payload: %s") % err.msg) from err

    def action_send_payload_to_automation(self):
        """Re-send the stored payload to Liana Automation (manual retry)."""
        self.ensure_one()
        if self.payload in (False, None):
            raise UserError(_("There is no payload to send."))

        backend = self.backend_id
        if not backend:
            raise UserError(_("This event has no Liana backend assigned."))
        backend.sudo()._check_automation_settings()

        data = self.payload
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as err:
                raise UserError(_("Payload is not valid JSON: %s") % err.msg) from err

        try:
            response = backend.sudo().automation_send_api_request(
                AUTOMATION_API_EVENT_PATH, data,
            )
            _logger.debug("Liana Automation response: %s", response)
            self.write({"state": "exported", "response": response})
        except LianaError as err:
            self.write({"state": "failed", "response": {"error": str(err)}})
            raise UserError(str(err)) from err

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Event payload was sent to Liana Automation."),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            payload_text = vals.pop("payload_text", None)
            if payload_text is not None:
                vals["payload"] = self._parse_payload_text(payload_text)
        return super().create(vals_list)
