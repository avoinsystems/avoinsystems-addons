from odoo import api, fields, models


class BaseAutomation(models.Model):
    _inherit = "base.automation"

    liana_action_server_count = fields.Integer(
        compute="_compute_liana_action_server_count",
    )

    @api.depends("action_server_ids.state")
    def _compute_liana_action_server_count(self):
        for rec in self:
            rec.liana_action_server_count = sum(
                1 for action in rec.action_server_ids if action.state == "liana"
            )
