from odoo import api, fields, models, _
from odoo.exceptions import UserError

import requests
import json
import hashlib
import hmac
import datetime

# --- General variables ---
BASE_PATH    = 'rest'
CONTENT_TYPE = 'application/json'
METHOD       = 'POST'
# POST body: Liana Automation event/tracking payload (channel, no_duplicates, data, ...).
AUTOMATION_API_EVENT_PATH = "v1/import"
# POST body: empty object. Returns list of channels available on the account.
AUTOMATION_API_CHANNEL_LIST_PATH = "v1/channel/list"

# XML ids of the default Liana server actions shipped in
# ``data/default_automations.xml``. Used by
# :meth:`LianaBackend.action_install_default_automations`.
DEFAULT_AUTOMATION_ACTION_XMLIDS = (
    "connector_liana.ir_actions_server_crm_lead_stage_changed",
    "connector_liana.ir_actions_server_sale_order_state_changed",
)


class LianaError(Exception):
    pass


class LianaBackend(models.Model):
    _name = "liana.backend"
    _description = "Liana Integration Backend Configuration"

    name = fields.Char(required=True)

    liana_automation_address = fields.Char(
        string="Automation Address",
    )
    
    liana_automation_secret = fields.Char(
        string="Automation Secret",
        copy=False,
    )

    liana_automation_user = fields.Char(
        string="Automation User",
        copy=False,
    )

    liana_automation_realm = fields.Char(
        string="Automation Realm",
    )

    liana_channel_id = fields.Many2one(
        comodel_name="liana.channel",
        string="Default Liana Channel",
        domain="[('backend_id', '=', id), ('system_name', 'not in', ('system', 'esp'))]",
    )

    def automation_send_api_request(self, path, data):
        """
        Sends an authenticated API request to Liana Automation.
        """
        self.ensure_one()

        # 1. Prepare Data
        json_data = json.dumps(data)

        # 2. Get Current Date (ISO 8601)
        # PHP' 'c' format is roughly equivalent to isoformat()
        date_str = datetime.datetime.now().astimezone().isoformat(timespec='seconds')  #

        # 3. MD5 Hash of the body
        content_md5 = hashlib.md5(json_data.encode('utf-8')).hexdigest()

        # 4. Create Signature Content
        # Order: Method, MD5, Content-Type, Date, Data, Full Path
        full_api_path = f"/{BASE_PATH}/{path}"
        signature_payload = "\n".join([
            METHOD,
            content_md5,
            CONTENT_TYPE,
            date_str,
            json_data,
            full_api_path
        ])

        # 5. Generate HMAC SHA256 Signature
        signature = hmac.new(
            self.liana_automation_secret.encode('utf-8'),
            signature_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # 6. Create Authorization Header
        auth_header = f"{self.liana_automation_realm} {self.liana_automation_user}:{signature}"

        # 7. Setup Headers
        headers = {
            "Authorization": auth_header,
            "Date": date_str,
            "Content-MD5": content_md5,
            "Content-Type": CONTENT_TYPE
        }

        # 8. Send Request
        full_url = f"{self.liana_automation_address}/{BASE_PATH}/{path}"

        try:
            response = requests.post(full_url, data=json_data, headers=headers)
            response.raise_for_status()  # Raises an error for 4xx or 5xx responses
            return response.json()
        except requests.exceptions.RequestException as e:
            raise LianaError(f"API request failed: {str(e)}")

    def _check_automation_settings(self):
        if any((
            not self.liana_automation_address,
            not self.liana_automation_secret,
            not self.liana_automation_user,
            not self.liana_automation_realm,
        )):
            raise UserError("Please fill in all Liana Automation settings to test the connection.")

    def action_fetch_liana_channels(self):
        """Refresh `liana.channel` from the Liana Automation `channel/list` endpoint."""
        self.ensure_one()
        try:
            channels = self.fetch_channels()
        except LianaError as err:
            raise UserError(str(err)) from err
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Liana Channels"),
                "message": _("Fetched %s channel(s) from Liana Automation.") % len(channels),
                "type": "success",
                "sticky": False,
            },
        }

    def test_automation_connection(self):
        """Test connection to Liana Automation API using pingpong endpoint.
        
        Shows a notification message to the user on success.
                
        Raises:
            UserError: If connection fails or settings are missing
            LianaError: If API response is unexpected
            
        Returns:
            dict: Client action to display success notification
        """
        self._check_automation_settings()
        
        response = self.automation_send_api_request('v1/pingpong', {"ping": "pong"})
        expected_response = {"pong": "pong"}
        if response == expected_response:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': 'Liana Automation connection successful!',
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise LianaError(f"Unexpected response from Liana Automation: {response}")

    def fetch_channels(self):
        """Call channel/list and upsert results into liana.channel.

        Returns the recordset of channels present for this backend after sync.
        """
        self.ensure_one()
        self._check_automation_settings()

        response = self.automation_send_api_request(
            AUTOMATION_API_CHANNEL_LIST_PATH, {}
        )
        # Automation may return HTTP 200 with an auth-failure envelope.
        if isinstance(response, dict) and "message" in response:
            raise LianaError(
                f"Liana Automation channel/list failed: {response.get('message')}"
            )
        if not isinstance(response, list):
            raise LianaError(
                f"Unexpected response from Liana Automation channel/list: {response!r}"
            )
        return self.env["liana.channel"].sudo()._update_from_api(self, response)

    def action_install_default_automations(self):
        """Stamp this backend (+ its default channel) onto the shipped Liana
        automation templates and activate them.

        The two template rules are created (inactive, with no backend/channel)
        by ``data/default_automations.xml``. This action makes them runnable
        by filling in the missing backend/channel references and flipping the
        parent ``base.automation`` records to active.

        Re-running the action is safe: it overwrites the same fields on the
        same records (looked up by XML id).
        """
        self.ensure_one()
        if not self.liana_channel_id:
            raise UserError(_(
                "Pick a default Liana channel before installing the default "
                "automations."
            ))
        actions = self.env["ir.actions.server"]
        missing = []
        for xmlid in DEFAULT_AUTOMATION_ACTION_XMLIDS:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                actions |= action
            else:
                missing.append(xmlid)
        if missing:
            raise UserError(_(
                "Default Liana automation templates are missing: %s. "
                "Reinstall or update the connector_liana module."
            ) % ", ".join(missing))

        actions.write({
            "liana_backend_id": self.id,
            "liana_channel_id": self.liana_channel_id.id,
        })
        actions.mapped("base_automation_id").write({"active": True})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Liana Automations"),
                "message": _(
                    "Installed %s default Liana automation(s) using channel %s."
                ) % (len(actions), self.liana_channel_id.display_name),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def _get_default_backend(self):
        """Return the unique backend in the database, or empty recordset.

        Used as the implicit fallback when a Liana action does not pin a
        specific backend and exactly one is configured.
        """
        backends = self.sudo().search([], limit=2)
        return backends if len(backends) == 1 else self.browse()

