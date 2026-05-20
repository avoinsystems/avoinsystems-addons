from odoo import fields, models, tools


class LianaEventReport(models.Model):
    _name = "liana.event.report"
    _description = "Liana Event Statistics"
    _auto = False
    _order = "create_date desc"

    create_date = fields.Datetime(string="Event Date", readonly=True)
    base_automation_id = fields.Many2one(
        comodel_name="base.automation",
        string="Automation Rule",
        readonly=True,
    )
    action_id = fields.Many2one(
        comodel_name="ir.actions.server",
        string="Server Action",
        readonly=True,
    )
    backend_id = fields.Many2one(
        comodel_name="liana.backend",
        string="Backend",
        readonly=True,
    )
    res_model = fields.Char(string="Source Model", readonly=True)
    state = fields.Selection(
        selection=[
            ("new", "New"),
            ("exported", "Exported"),
            ("failed", "Export Failed"),
        ],
        string="State",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contact",
        readonly=True,
        aggregator="count_distinct",
    )
    lead_id = fields.Many2one(
        comodel_name="crm.lead",
        string="Lead",
        readonly=True,
        aggregator="count_distinct",
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    id,
                    create_date,
                    base_automation_id,
                    action_id,
                    backend_id,
                    res_model,
                    state,
                    partner_id,
                    lead_id
                FROM liana_event
            )
        """)
