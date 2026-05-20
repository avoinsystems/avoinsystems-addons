import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

LIANA_EVENT_ITEM_KEY_RE = re.compile(r"^[a-z0-9_-]+$")

RELATIONAL_TTYPES = ("many2one", "one2many", "many2many")


class LianaEventItem(models.Model):
    _name = "liana.event.item"
    _description = "Liana Event Item Mapping"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)

    action_id = fields.Many2one(
        "ir.actions.server",
        string="Server Action",
        required=True,
        ondelete="cascade",
        index=True,
    )
    model_id = fields.Many2one(
        "ir.model",
        related="action_id.model_id",
        string="Source Model",
        store=False,
    )

    key = fields.Char(
        help="Key used in the Liana event 'items' payload. For One2many/Many2many "
             "fields, each linked record produces '<key>_1', '<key>_2', ... entries. "
             "May contain only lowercase ASCII letters (a-z), digits, underscores "
             "and dash-characters.",
        compute="_compute_key",
        store=True,
    )

    field_id = fields.Many2one(
        "ir.model.fields",
        string="Source Field",
        required=True,
        ondelete="cascade",
        domain="[('model_id', '=', model_id)]",
        help="Field read from the triggering record.",
    )
    field_ttype = fields.Selection(
        related="field_id.ttype",
        string="Field Type",
        store=False,
    )
    field_relation = fields.Char(
        related="field_id.relation",
        string="Related Model",
        store=False,
    )

    subfield_id = fields.Many2one(
        "ir.model.fields",
        string="Sub-field",
        ondelete="cascade",
        domain="[('model', '=', field_relation)]",
        help="Field read from the target record when the source field is "
             "Many2one, One2many or Many2many.",
    )

    @api.constrains("key")
    def _check_key(self):
        for item in self:
            if not item.key or not LIANA_EVENT_ITEM_KEY_RE.match(item.key):
                raise ValidationError(_(
                    "Liana event item key %(key)r is invalid. It may only contain "
                    "lowercase ASCII letters (a-z), digits (0-9), underscores (_) "
                    "and dash-characters (-).",
                    key=item.key or "",
                ))

    @api.constrains("field_id", "subfield_id")
    def _check_subfield(self):
        for item in self:
            ttype = item.field_id.ttype
            if ttype in RELATIONAL_TTYPES:
                if not item.subfield_id:
                    raise ValidationError(_(
                        "Liana event item %(key)r: a sub-field is required when "
                        "the source field %(field)r is %(ttype)s.",
                        key=item.key or "",
                        field=item.field_id.name or "",
                        ttype=ttype,
                    ))
                if item.subfield_id.model != item.field_id.relation:
                    raise ValidationError(_(
                        "Liana event item %(key)r: sub-field %(sub)r must belong "
                        "to model %(model)r.",
                        key=item.key or "",
                        sub=item.subfield_id.name or "",
                        model=item.field_id.relation or "",
                    ))
            elif item.subfield_id:
                raise ValidationError(_(
                    "Liana event item %(key)r: a sub-field can only be set when "
                    "the source field is Many2one, One2many or Many2many.",
                    key=item.key or "",
                ))

    @api.constrains("action_id", "key")
    def _check_unique_key_per_action(self):
        for item in self:
            duplicate = self.search_count([
                ("action_id", "=", item.action_id.id),
                ("key", "=", item.key),
                ("id", "!=", item.id),
            ])
            if duplicate:
                raise ValidationError(_(
                    "Liana event item key %(key)r is used more than once on "
                    "action %(action)s.",
                    key=item.key,
                    action=item.action_id.display_name,
                ))

    @api.depends("field_id", "subfield_id")
    def _compute_key(self):
        for item in self:
            item.key = (
                item.field_id.name
                if not item.subfield_id
                else "%s_%s" % (item.field_id.name, item.subfield_id.name)
            )

    @api.onchange("field_id")
    def _onchange_field_id(self):
        if self.field_id.ttype not in RELATIONAL_TTYPES:
            self.subfield_id = False
