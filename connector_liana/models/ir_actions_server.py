import json
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

IDENTITY_MODELS = ("res.partner", "crm.lead")

LIANA_EVENT_VERB_RE = re.compile(r"^[a-z0-9_]+$")


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(
        selection_add=[("liana", "Send Liana Automation Event")],
        ondelete={"liana": "cascade"},
    )

    liana_backend_id = fields.Many2one(
        comodel_name="liana.backend",
        string="Liana Backend",
        ondelete="restrict",
        default=lambda self: self.env["liana.backend"]._get_default_backend(),
        help="Backend used to send the event. If left empty and exactly one "
             "backend exists, that backend is used.",
    )
    liana_channel_id = fields.Many2one(
        comodel_name="liana.channel",
        string="Liana Channel",
        ondelete="restrict",
        domain="[('backend_id', '=', liana_backend_id), ('system_name', 'not in', ('system', 'esp'))]",
    )
    liana_no_duplicates = fields.Boolean(
        string="No Duplicates",
        default=False,
        help="When enabled, Liana Automation will ignore duplicate events.",
    )
    liana_identity_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Identity Field",
        domain="[('model_id', '=', model_id),"
               " ('ttype', '=', 'many2one'),"
               " ('relation', 'in', ['res.partner', 'crm.lead'])]",
        ondelete="cascade",
        help="Many2one field on the model pointing to the res.partner or crm.lead "
             "record used as the Liana identity. Leave empty when the model itself "
             "is res.partner or crm.lead.",
    )
    liana_event_verb = fields.Char(
        string="Event Verb",
        help="Event type. May contain only basic lowercase characters (a-z, not ä,ö,å,é,...), numbers and underscores.",
    )
    liana_event_item_ids = fields.One2many(
        comodel_name="liana.event.item",
        inverse_name="action_id",
        string="Event Items",
        copy=True,
        help="Mapping of payload keys to fields on the triggering record. "
             "Relational source fields can drill into a sub-field on the linked "
             "record(s); One2many and Many2many fields expand into multiple "
             "indexed keys (e.g. line_name_1, line_name_2).",
    )
    liana_sample_payload = fields.Text(
        string="Sample Payload",
        compute="_compute_liana_sample_payload",
    )

    @api.constrains("state", "base_automation_id")
    def _check_one_liana_action_per_automation(self):
        """Enforce at most one liana action per base.automation rule."""
        for action in self:
            if action.state != "liana" or not action.base_automation_id:
                continue
            sibling_liana = action.base_automation_id.action_server_ids.filtered(
                lambda a, current=action: a.state == "liana" and a.id != current.id
            )
            if sibling_liana:
                raise ValidationError(_(
                    "Automation rule %(rule)s already has a "
                    "'Send Liana Automation Event' action. "
                    "Each Liana automation may have at most one Liana action.",
                    rule=action.base_automation_id.display_name,
                ))

    @api.constrains("state", "liana_backend_id", "liana_channel_id")
    def _check_liana_channel_backend(self):
        for action in self:
            if (
                action.state == "liana"
                and action.liana_backend_id
                and action.liana_channel_id
                and action.liana_channel_id.backend_id != action.liana_backend_id
            ):
                raise ValidationError(_(
                    "Liana channel %(channel)s does not belong to backend %(backend)s.",
                    channel=action.liana_channel_id.display_name,
                    backend=action.liana_backend_id.display_name,
                ))

    def _get_liana_backend(self):
        """Return the backend that should be used for this action.

        Falls back to the unique backend in the database when the action
        does not pin one explicitly. Raises :class:`UserError` when the
        backend cannot be determined.
        """
        self.ensure_one()
        backend = self.liana_backend_id or self.env["liana.backend"]._get_default_backend()
        if not backend:
            raise UserError(_(
                "No Liana backend configured. Set 'Liana Backend' on the "
                "action or create a single backend record."
            ))
        return backend.sudo()

    @api.constrains("state", "liana_event_verb")
    def _check_liana_event_verb(self):
        for action in self:
            if action.state != "liana" or not action.liana_event_verb:
                continue
            if not LIANA_EVENT_VERB_RE.match(action.liana_event_verb):
                raise ValidationError(_(
                    "Liana event verb %(verb)r is invalid. It may only contain "
                    "lowercase ASCII letters (a-z), digits (0-9) and "
                    "underscores (_).",
                    verb=action.liana_event_verb,
                ))

    @api.model
    def _warning_depends(self):
        return super()._warning_depends() + [
            "liana_backend_id",
            "liana_channel_id",
            "liana_event_verb",
            "liana_identity_field_id",
            "liana_event_item_ids",
            "base_automation_id.active",
        ]

    def _get_warning_messages(self):
        self.ensure_one()
        warnings = super()._get_warning_messages()
        if self.state != "liana":
            return warnings

        # Skip Liana warnings for unconfigured template actions: no backend
        # pinned and parent rule still inactive. This lets the shipped
        # default automations (data/default_automations.xml) be created
        # without tripping base.automation._check_trigger_state, which
        # forbids actions in warning state. Warnings reappear as soon as
        # the user pins a backend or activates the rule.
        if (
            not self.liana_backend_id
            and self.base_automation_id
            and not self.base_automation_id.active
        ):
            return warnings

        if not self.liana_channel_id:
            warnings.append(_("Liana action requires a channel."))
        if not self.liana_event_verb:
            warnings.append(_("Liana action requires an event verb."))
        if (
            self.model_id
            and self.model_id.model not in IDENTITY_MODELS
            and not self.liana_identity_field_id
        ):
            warnings.append(_(
                "Liana action requires an identity field unless the model is "
                "res.partner or crm.lead."
            ))
        return warnings

    @api.depends(
        "state",
        "model_id",
        "liana_channel_id",
        "liana_no_duplicates",
        "liana_event_verb",
        "liana_event_item_ids",
        "liana_event_item_ids.key",
        "liana_event_item_ids.field_id",
        "liana_event_item_ids.subfield_id",
        "liana_identity_field_id",
    )
    def _compute_liana_sample_payload(self):
        for action in self:
            if action.state != "liana":
                action.liana_sample_payload = False
                continue
            sample_record = self.env["res.partner"]
            if action.model_id:
                sample_record = self.env[action.model_id.model].with_context(
                    active_test=False
                ).search([], limit=1)
            try:
                payload = action._build_liana_payload(sample_record) if sample_record else {
                    "channel": str(action.liana_channel_id.channel_id) or "",
                    "no_duplicates": action.liana_no_duplicates,
                    "data": [],
                }
            except Exception:  # noqa: BLE001 - sample is best-effort
                payload = {
                    "channel": str(action.liana_channel_id.channel_id) or "",
                    "no_duplicates": action.liana_no_duplicates,
                    "data": [],
                }
            action.liana_sample_payload = json.dumps(
                payload, indent=2, sort_keys=False, default=str, ensure_ascii=False
            )

    @api.onchange("liana_backend_id")
    def _onchange_backend_id(self):
        for action in self:
            if action.liana_backend_id:
                action.liana_channel_id = action.liana_backend_id.liana_channel_id
            else:
                action.liana_channel_id = False

    def _get_identity_record(self, record):
        """Return the res.partner / crm.lead record used for the Liana identity."""
        self.ensure_one()
        if not record:
            return record
        if self.liana_identity_field_id:
            return record[self.liana_identity_field_id.name]
        if record._name in IDENTITY_MODELS:
            return record
        return record.browse()

    def _build_identity(self, identity_record):
        """Build the Liana identity dict from a res.partner / crm.lead record."""
        self.ensure_one()
        if not identity_record:
            return {}
        identity = {}
        if identity_record._name == "res.partner":
            email = identity_record.email
            sms = identity_record.phone
        elif identity_record._name == "crm.lead":
            email = identity_record.email_from
            sms = identity_record.phone
        else:
            email = sms = False
        if email:
            identity["email"] = email
        if sms:
            identity["sms"] = sms
        if not identity_record.liana_extra1:
            identity_record.liana_extra1 = self.env["ir.sequence"].next_by_code("liana.extra1")
        identity["extra1"] = identity_record.liana_extra1
        if identity_record.liana_token:
            identity["token"] = identity_record.liana_token
        return identity

    def _build_event_items(self, record):
        """Build the Liana event items dict from the triggering record.

        Each configured :class:`liana.event.item` produces one or more entries:

        - scalar source field -> ``{key: value}``
        - Many2one source field -> ``{key: target_record[subfield]}`` (or
          ``False`` when the related record is empty)
        - One2many / Many2many -> ``{f"{key}_{i}": rec[subfield]}`` for each
          linked record, starting at index 1 in the comodel's default order.
        """
        self.ensure_one()
        if not record or not self.liana_event_item_ids:
            return {}
        items = {}
        for item in self.liana_event_item_ids:
            field = item.field_id
            value = record[field.name]
            if field.ttype == "many2one":
                sub_name = item.subfield_id.name
                if not value:
                    items[item.key] = False
                else:
                    items[item.key] = value.read([sub_name], load=None)[0][sub_name]
            elif field.ttype in ("one2many", "many2many"):
                sub_name = item.subfield_id.name
                for idx, rec in enumerate(value, start=1):
                    items[f"{item.key}_{idx}"] = rec.read(
                        [sub_name], load=None
                    )[0][sub_name]
            else:
                items[item.key] = record.read([field.name], load=None)[0][field.name]
        return items

    def _build_liana_payload(self, record):
        """Build the full Liana Automation payload for a triggering record."""
        self.ensure_one()
        identity_record = self._get_identity_record(record)
        identity = self._build_identity(identity_record)
        items = self._build_event_items(record)
        return {
            "channel": str(self.liana_channel_id.channel_id) or "",
            "no_duplicates": bool(self.liana_no_duplicates),
            "data": [
                {
                    "identity": identity,
                    "events": [
                        {
                            "verb": self.liana_event_verb or "",
                            "items": items,
                        }
                    ],
                }
            ],
        }

    def _run_action_liana(self, eval_context=None):
        """Send a Liana Automation event for the triggering record."""
        self.ensure_one()
        if not self.model_id:
            raise UserError(_("Liana action %s has no model.", self.name))
        active_id = self.env.context.get("active_id")
        if not active_id:
            return False
        record = self.env[self.model_id.model].browse(active_id).exists()
        if not record:
            return False

        backend = self._get_liana_backend()
        identity_record = self._get_identity_record(record)
        partner_id = (
            identity_record.id
            if identity_record and identity_record._name == "res.partner"
            else False
        )
        lead_id = (
            identity_record.id
            if identity_record and identity_record._name == "crm.lead"
            else False
        )
        event = self.env["liana.event"].sudo().create({
            "name": _("%(action)s on %(model)s #%(rid)s") % {
                "action": self.base_automation_id.name,
                "model": record._name,
                "rid": record.id,
            },
            "action_id": self.id,
            "backend_id": backend.id,
            "res_id": record.id,
            "partner_id": partner_id,
            "lead_id": lead_id,
            "payload": self._build_liana_payload(record),
            "state": "new",
        })
        try:
            event.sudo().action_send_payload_to_automation()
        except UserError as err:
            _logger.warning(
                "Liana Automation call failed for event %s: %s", event.id, err
            )
        return False
