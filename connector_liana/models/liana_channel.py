import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class LianaChannel(models.Model):
    _name = "liana.channel"
    _description = "Liana Channel"
    _order = "name"

    name = fields.Char(required=True)

    channel_id = fields.Integer(
        string="Channel ID",
        required=True,
        index=True,
        help="Channel ID from the Liana Automation API.",
    )
    system_name = fields.Char(
        help="Channel system name from the Liana Automation API. May be empty.",
    )
    channel_type = fields.Char(string="Type")
    color = fields.Char()
    backend_id = fields.Many2one(
        comodel_name="liana.backend",
        required=True,
        ondelete="cascade",
    )

    _sql_constraints = [
        (
            "channel_backend_unique",
            "UNIQUE(backend_id, channel_id)",
            "A Liana channel must be unique per backend.",
        ),
    ]

    def _selection_value(self):
        """Value sent as the Liana payload `channel` (system name preferred)."""
        self.ensure_one()
        return self.system_name or str(self.channel_id)

    @api.model
    def _update_from_api(self, backend, items):
        """Create/update channels for the given backend from API ChannelOut list.

        Stale channels for the backend that are not in the response are removed.
        Returns the recordset of the channels currently present for the backend.
        """
        if not isinstance(items, list):
            _logger.warning(
                "Liana channel/list returned unexpected payload: %r", items
            )
            return self.browse()

        seen_ids = []
        for item in items:
            if not isinstance(item, dict) or "id" not in item:
                continue
            try:
                api_id = int(item["id"])
            except (TypeError, ValueError):
                continue
            seen_ids.append(api_id)
            vals = {
                "name": item.get("name") or item.get("system_name") or str(api_id),
                "system_name": item.get("system_name") or False,
                "channel_type": item.get("type") or False,
                "color": item.get("color") or False,
            }
            existing = self.search(
                [("backend_id", "=", backend.id), ("channel_id", "=", api_id)],
                limit=1,
            )
            if existing:
                existing.write(vals)
            else:
                self.create({
                    **vals,
                    "channel_id": api_id,
                    "backend_id": backend.id,
                })

        stale = self.search([
            ("backend_id", "=", backend.id),
            ("channel_id", "not in", seen_ids),
        ])
        if stale:
            stale.unlink()

        return self.search([("backend_id", "=", backend.id)])
