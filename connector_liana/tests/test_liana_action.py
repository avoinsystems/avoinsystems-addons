from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.connector_liana.models import liana_backend as liana_backend_module


@tagged("post_install", "-at_install")
class TestLianaServerAction(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.backend = cls.env["liana.backend"].create({
            "name": "Test backend",
            "liana_automation_address": "https://automation.example.test",
            "liana_automation_secret": "test-secret-key",
            "liana_automation_user": "api-user",
            "liana_automation_realm": "TestRealm",
        })
        channels = cls.env["liana.channel"].create([
            {
                "name": "Test channel",
                "channel_id": 1,
                "system_name": "test-channel",
                "backend_id": cls.backend.id,
            },
            {
                "name": "Leads channel",
                "channel_id": 2,
                "system_name": "leads",
                "backend_id": cls.backend.id,
            },
        ])
        cls.test_channel = channels[0]
        cls.leads_channel = channels[1]
        cls.partner_model = cls.env.ref("base.model_res_partner")
        cls.name_field = cls.env["ir.model.fields"]._get("res.partner", "name")
        cls.email_field = cls.env["ir.model.fields"]._get("res.partner", "email")

    def _create_automation(self, **action_overrides):
        automation = self.env["base.automation"].create({
            "name": "Liana export on partner write",
            "model_id": self.partner_model.id,
            "trigger": "on_create_or_write",
            "trigger_field_ids": [(6, 0, [self.name_field.id, self.email_field.id])],
        })
        action_vals = {
            "name": "Send to Liana",
            "model_id": self.partner_model.id,
            "state": "liana",
            "usage": "base_automation",
            "base_automation_id": automation.id,
            "liana_channel_id": self.test_channel.id,
            "liana_no_duplicates": True,
            "liana_event_verb": "subscribe",
            "liana_event_item_ids": [
                (0, 0, {"field_id": self.name_field.id}),
                (0, 0, {"field_id": self.email_field.id}),
            ],
        }
        action_vals.update(action_overrides)
        self.env["ir.actions.server"].create(action_vals)
        return automation

    @patch.object(liana_backend_module.requests, "post")
    def test_run_action_creates_event_and_calls_api(self, mock_post):
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status.return_value = None
        self._create_automation()

        partner = self.env["res.partner"].create({
            "name": "Liana Lover",
            "email": "lover@example.test",
            "phone": "+358111222",
            "liana_extra1": "EXT-1",
            "liana_token": "TKN-1",
        })

        events = self.env["liana.event"].search([("res_id", "=", partner.id)])
        self.assertEqual(len(events), 1, "Exactly one liana.event should be logged")
        event = events
        self.assertEqual(event.state, "exported")
        self.assertEqual(event.res_model, "res.partner")
        self.assertEqual(event.partner_id, partner)
        self.assertFalse(event.lead_id)
        self.assertEqual(event.payload["channel"], str(self.test_channel.channel_id))
        self.assertTrue(event.payload["no_duplicates"])
        data = event.payload["data"][0]
        self.assertEqual(data["identity"]["email"], "lover@example.test")
        self.assertEqual(data["identity"]["sms"], "+358111222")
        self.assertEqual(data["identity"]["extra1"], "EXT-1")
        self.assertEqual(data["identity"]["token"], "TKN-1")
        self.assertEqual(data["events"][0]["verb"], "subscribe")
        self.assertEqual(data["events"][0]["items"]["name"], "Liana Lover")
        self.assertEqual(data["events"][0]["items"]["email"], "lover@example.test")
        mock_post.assert_called_once()

    @patch.object(liana_backend_module.requests, "post")
    def test_run_action_missing_backend(self, mock_post):
        self.backend.unlink()
        self._create_automation(liana_channel_id=False)

        with self.assertRaises(UserError):
            self.env["res.partner"].create({"name": "No backend partner"})
        mock_post.assert_not_called()

    @patch.object(liana_backend_module.requests, "post")
    def test_run_action_api_failure_logs_failed_event(self, mock_post):
        mock_post.return_value.raise_for_status.side_effect = (
            liana_backend_module.requests.exceptions.HTTPError("boom")
        )
        self._create_automation()

        partner = self.env["res.partner"].create({"name": "API failure partner"})

        event = self.env["liana.event"].search([("res_id", "=", partner.id)])
        self.assertEqual(len(event), 1)
        self.assertEqual(event.state, "failed")
        self.assertIn("error", event.response)

    @patch.object(liana_backend_module.requests, "post")
    def test_identity_via_field_on_lead(self, mock_post):
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status.return_value = None

        lead_model = self.env.ref("crm.model_crm_lead")
        partner_field = self.env["ir.model.fields"]._get("crm.lead", "partner_id")
        lead_name_field = self.env["ir.model.fields"]._get("crm.lead", "name")

        partner = self.env["res.partner"].create({
            "name": "Lead Owner",
            "email": "owner@example.test",
            "liana_extra1": "OWN-1",
        })
        automation = self.env["base.automation"].create({
            "name": "Liana export on lead create",
            "model_id": lead_model.id,
            "trigger": "on_create_or_write",
            "trigger_field_ids": [(6, 0, [lead_name_field.id])],
        })
        self.env["ir.actions.server"].create({
            "name": "Send lead to Liana",
            "model_id": lead_model.id,
            "state": "liana",
            "usage": "base_automation",
            "base_automation_id": automation.id,
            "liana_channel_id": self.leads_channel.id,
            "liana_event_verb": "lead_created",
            "liana_identity_field_id": partner_field.id,
            "liana_event_item_ids": [
                (0, 0, {"field_id": lead_name_field.id}),
            ],
        })

        lead = self.env["crm.lead"].create({
            "name": "Liana opportunity",
            "partner_id": partner.id,
        })

        event = self.env["liana.event"].search([("res_id", "=", lead.id)])
        self.assertEqual(len(event), 1)
        self.assertEqual(event.state, "exported")
        self.assertEqual(event.partner_id, partner)
        self.assertFalse(event.lead_id)
        identity = event.payload["data"][0]["identity"]
        self.assertEqual(identity["email"], "owner@example.test")
        self.assertEqual(identity["extra1"], "OWN-1")
        self.assertEqual(
            event.payload["data"][0]["events"][0]["items"]["name"],
            "Liana opportunity",
        )

    @patch.object(liana_backend_module.requests, "post")
    def test_event_lead_id_denormalized_when_lead_is_identity(self, mock_post):
        """When the trigger record itself is a crm.lead, lead_id is filled."""
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status.return_value = None

        lead_model = self.env.ref("crm.model_crm_lead")
        lead_name_field = self.env["ir.model.fields"]._get("crm.lead", "name")
        automation = self.env["base.automation"].create({
            "name": "Liana export on lead create (self identity)",
            "model_id": lead_model.id,
            "trigger": "on_create_or_write",
            "trigger_field_ids": [(6, 0, [lead_name_field.id])],
        })
        self.env["ir.actions.server"].create({
            "name": "Send lead to Liana",
            "model_id": lead_model.id,
            "state": "liana",
            "usage": "base_automation",
            "base_automation_id": automation.id,
            "liana_channel_id": self.leads_channel.id,
            "liana_event_verb": "lead_created",
            "liana_event_item_ids": [
                (0, 0, {"field_id": lead_name_field.id}),
            ],
        })

        lead = self.env["crm.lead"].create({
            "name": "Self-identity lead",
            "email_from": "lead@example.test",
        })

        event = self.env["liana.event"].search([("res_id", "=", lead.id)])
        self.assertEqual(len(event), 1)
        self.assertEqual(event.lead_id, lead)
        self.assertFalse(event.partner_id)

    def test_liana_event_verb_constraint_rejects_invalid_chars(self):
        for bad_verb in ("Subscribe", "tilaa-uutiskirje", "tilauspäivitys",
                         "order!", "sub scribe", "résumé"):
            with self.assertRaises(ValidationError, msg=bad_verb):
                self.env["ir.actions.server"].create({
                    "name": "Send to Liana",
                    "model_id": self.partner_model.id,
                    "state": "liana",
                    "liana_channel_id": self.test_channel.id,
                    "liana_event_verb": bad_verb,
                })

    def test_liana_event_verb_constraint_accepts_valid_chars(self):
        action = self.env["ir.actions.server"].create({
            "name": "Send to Liana",
            "model_id": self.partner_model.id,
            "state": "liana",
            "liana_channel_id": self.test_channel.id,
            "liana_event_verb": "order_42",
        })
        self.assertEqual(action.liana_event_verb, "order_42")

    @patch.object(liana_backend_module.requests, "post")
    def test_event_items_many2one_subfield(self, mock_post):
        """Many2one source field exports the chosen sub-field of the target."""
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status.return_value = None

        parent_field = self.env["ir.model.fields"]._get("res.partner", "parent_id")
        partner_name_field = self.name_field

        parent = self.env["res.partner"].create({
            "name": "Parent Co",
            "email": "ops@parent.example",
        })

        automation = self.env["base.automation"].create({
            "name": "Liana export on partner create",
            "model_id": self.partner_model.id,
            "trigger": "on_create_or_write",
            "trigger_field_ids": [(6, 0, [self.name_field.id])],
        })
        self.env["ir.actions.server"].create({
            "name": "Send to Liana",
            "model_id": self.partner_model.id,
            "state": "liana",
            "usage": "base_automation",
            "base_automation_id": automation.id,
            "liana_channel_id": self.test_channel.id,
            "liana_event_verb": "subscribe",
            "liana_event_item_ids": [
                (0, 0, {
                    "field_id": parent_field.id,
                    "subfield_id": partner_name_field.id,
                }),
            ],
        })

        child = self.env["res.partner"].create({
            "name": "Child Contact",
            "email": "child@example.test",
            "parent_id": parent.id,
        })

        event = self.env["liana.event"].search([("res_id", "=", child.id)])
        self.assertEqual(len(event), 1)
        items = event.payload["data"][0]["events"][0]["items"]
        self.assertEqual(items[f"{parent_field.name}_{partner_name_field.name}"], "Parent Co")

    @patch.object(liana_backend_module.requests, "post")
    def test_event_items_many2one_empty(self, mock_post):
        """Empty Many2one source field exports False under the configured key."""
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status.return_value = None

        parent_field = self.env["ir.model.fields"]._get("res.partner", "parent_id")
        partner_name_field = self.name_field

        automation = self.env["base.automation"].create({
            "name": "Liana export on partner create",
            "model_id": self.partner_model.id,
            "trigger": "on_create_or_write",
            "trigger_field_ids": [(6, 0, [self.name_field.id])],
        })
        self.env["ir.actions.server"].create({
            "name": "Send to Liana",
            "model_id": self.partner_model.id,
            "state": "liana",
            "usage": "base_automation",
            "base_automation_id": automation.id,
            "liana_channel_id": self.test_channel.id,
            "liana_event_verb": "subscribe",
            "liana_event_item_ids": [
                (0, 0, {
                    "field_id": parent_field.id,
                    "subfield_id": partner_name_field.id,
                }),
            ],
        })

        orphan = self.env["res.partner"].create({"name": "Orphan"})

        event = self.env["liana.event"].search([("res_id", "=", orphan.id)])
        self.assertEqual(len(event), 1)
        items = event.payload["data"][0]["events"][0]["items"]
        self.assertFalse(items[f"{parent_field.name}_{partner_name_field.name}"])

    @patch.object(liana_backend_module.requests, "post")
    def test_event_items_one2many_expansion(self, mock_post):
        """One2many source field expands into indexed keys."""
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status.return_value = None

        child_ids_field = self.env["ir.model.fields"]._get("res.partner", "child_ids")
        partner_name_field = self.name_field

        automation = self.env["base.automation"].create({
            "name": "Liana export on partner write",
            "model_id": self.partner_model.id,
            "trigger": "on_create_or_write",
            "trigger_field_ids": [(6, 0, [self.name_field.id])],
        })
        self.env["ir.actions.server"].create({
            "name": "Send to Liana",
            "model_id": self.partner_model.id,
            "state": "liana",
            "usage": "base_automation",
            "base_automation_id": automation.id,
            "liana_channel_id": self.test_channel.id,
            "liana_event_verb": "subscribe",
            "liana_event_item_ids": [
                (0, 0, {
                    "field_id": child_ids_field.id,
                    "subfield_id": partner_name_field.id,
                }),
            ],
        })

        parent = self.env["res.partner"].create({
            "name": "Multi Parent",
            "child_ids": [
                (0, 0, {"name": "Alpha"}),
                (0, 0, {"name": "Bravo"}),
                (0, 0, {"name": "Charlie"}),
            ],
        })

        event = self.env["liana.event"].search([("res_id", "=", parent.id)])
        self.assertEqual(len(event), 1)
        items = event.payload["data"][0]["events"][0]["items"]
        children = parent.child_ids
        key_base = f"{child_ids_field.name}_{partner_name_field.name}"
        for idx, child in enumerate(children, start=1):
            self.assertEqual(items[f"{key_base}_{idx}"], child.name)
        self.assertNotIn(key_base, items)
        self.assertNotIn(f"{key_base}_{len(children) + 1}", items)

    def test_event_item_key_is_computed_from_fields(self):
        parent_field = self.env["ir.model.fields"]._get("res.partner", "parent_id")
        action = self.env["ir.actions.server"].create({
            "name": "Send to Liana",
            "model_id": self.partner_model.id,
            "state": "liana",
            "liana_channel_id": self.test_channel.id,
            "liana_event_verb": "subscribe",
            "liana_event_item_ids": [
                (0, 0, {"field_id": self.name_field.id}),
                (0, 0, {
                    "field_id": parent_field.id,
                    "subfield_id": self.email_field.id,
                }),
            ],
        })
        keys = action.liana_event_item_ids.mapped("key")
        self.assertEqual(keys, ["name", "parent_id_email"])

    def test_event_item_key_ignores_explicit_value(self):
        """Explicit ``key`` writes are silently overridden by the compute."""
        action = self.env["ir.actions.server"].create({
            "name": "Send to Liana",
            "model_id": self.partner_model.id,
            "state": "liana",
            "liana_channel_id": self.test_channel.id,
            "liana_event_verb": "subscribe",
            "liana_event_item_ids": [
                (0, 0, {
                    "key": "user-supplied",
                    "field_id": self.name_field.id,
                }),
            ],
        })
        self.assertEqual(action.liana_event_item_ids.key, "name")

    def test_event_item_subfield_required_for_relational(self):
        parent_field = self.env["ir.model.fields"]._get("res.partner", "parent_id")
        with self.assertRaises(ValidationError):
            self.env["ir.actions.server"].create({
                "name": "Send to Liana",
                "model_id": self.partner_model.id,
                "state": "liana",
                "liana_channel_id": self.test_channel.id,
                "liana_event_verb": "subscribe",
                "liana_event_item_ids": [
                    (0, 0, {"field_id": parent_field.id}),
                ],
            })

    def test_event_item_subfield_forbidden_for_scalar(self):
        with self.assertRaises(ValidationError):
            self.env["ir.actions.server"].create({
                "name": "Send to Liana",
                "model_id": self.partner_model.id,
                "state": "liana",
                "liana_channel_id": self.test_channel.id,
                "liana_event_verb": "subscribe",
                "liana_event_item_ids": [
                    (0, 0, {
                        "field_id": self.name_field.id,
                        "subfield_id": self.email_field.id,
                    }),
                ],
            })

    def test_event_item_subfield_must_match_relation(self):
        parent_field = self.env["ir.model.fields"]._get("res.partner", "parent_id")
        lead_name_field = self.env["ir.model.fields"]._get("crm.lead", "name")
        with self.assertRaises(ValidationError):
            self.env["ir.actions.server"].create({
                "name": "Send to Liana",
                "model_id": self.partner_model.id,
                "state": "liana",
                "liana_channel_id": self.test_channel.id,
                "liana_event_verb": "subscribe",
                "liana_event_item_ids": [
                    (0, 0, {
                        "field_id": parent_field.id,
                        "subfield_id": lead_name_field.id,
                    }),
                ],
            })

    def test_event_item_duplicate_keys_rejected(self):
        """Two items resolving to the same computed key on the same action fail."""
        with self.assertRaises(ValidationError):
            self.env["ir.actions.server"].create({
                "name": "Send to Liana",
                "model_id": self.partner_model.id,
                "state": "liana",
                "liana_channel_id": self.test_channel.id,
                "liana_event_verb": "subscribe",
                "liana_event_item_ids": [
                    (0, 0, {"field_id": self.name_field.id}),
                    (0, 0, {"field_id": self.name_field.id}),
                ],
            })

    @patch.object(liana_backend_module.requests, "post")
    def test_run_action_uses_action_backend_id(self, mock_post):
        """Action's explicit backend_id wins over the implicit single-backend rule."""
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status.return_value = None

        other_backend = self.env["liana.backend"].create({
            "name": "Other backend",
            "liana_automation_address": "https://other.example.test",
            "liana_automation_secret": "other-secret",
            "liana_automation_user": "other-user",
            "liana_automation_realm": "OtherRealm",
        })
        other_channel = self.env["liana.channel"].create({
            "name": "Other channel",
            "channel_id": 99,
            "system_name": "other-channel",
            "backend_id": other_backend.id,
        })
        self._create_automation(
            liana_backend_id=other_backend.id,
            liana_channel_id=other_channel.id,
        )

        partner = self.env["res.partner"].create({"name": "Backend pinning partner"})
        event = self.env["liana.event"].search([("res_id", "=", partner.id)])
        self.assertEqual(len(event), 1)
        self.assertEqual(event.backend_id, other_backend)

        called_url = mock_post.call_args.args[0]
        self.assertTrue(called_url.startswith(other_backend.liana_automation_address))

    @patch.object(liana_backend_module.requests, "post")
    def test_run_action_falls_back_to_single_backend(self, mock_post):
        """Without backend_id on the action, the unique backend is picked up."""
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status.return_value = None
        self._create_automation()

        partner = self.env["res.partner"].create({"name": "Single backend partner"})
        event = self.env["liana.event"].search([("res_id", "=", partner.id)])
        self.assertEqual(event.backend_id, self.backend)

    @patch.object(liana_backend_module.requests, "post")
    def test_run_action_ambiguous_backend_raises(self, mock_post):
        """Multiple backends + no explicit pin -> UserError, no API call."""
        self.env["liana.backend"].create({
            "name": "Second backend",
            "liana_automation_address": "https://second.example.test",
            "liana_automation_secret": "second-secret",
            "liana_automation_user": "second-user",
            "liana_automation_realm": "SecondRealm",
        })
        self._create_automation()

        with self.assertRaises(UserError):
            self.env["res.partner"].create({"name": "Ambiguous backend partner"})
        mock_post.assert_not_called()

    @patch.object(liana_backend_module.requests, "post")
    def test_event_resend_uses_event_backend(self, mock_post):
        """Manual resend uses the event's stored backend, not the action's current one."""
        mock_post.return_value.json.return_value = {"ok": True}
        mock_post.return_value.raise_for_status.return_value = None
        self._create_automation()

        partner = self.env["res.partner"].create({"name": "Resend partner"})
        event = self.env["liana.event"].search([("res_id", "=", partner.id)])
        self.assertEqual(event.backend_id, self.backend)
        original_address = self.backend.liana_automation_address
        mock_post.reset_mock()

        new_backend = self.env["liana.backend"].create({
            "name": "New backend",
            "liana_automation_address": "https://new.example.test",
            "liana_automation_secret": "new-secret",
            "liana_automation_user": "new-user",
            "liana_automation_realm": "NewRealm",
        })
        event.action_id.write({
            "liana_channel_id": False,
            "liana_backend_id": new_backend.id,
        })

        event.action_send_payload_to_automation()

        self.assertEqual(event.backend_id, self.backend)
        called_url = mock_post.call_args.args[0]
        self.assertTrue(called_url.startswith(original_address))

    def test_event_resend_without_backend_raises(self):
        """Events with no backend assigned cannot be resent."""
        event = self.env["liana.event"].sudo().create({
            "name": "Orphan",
            "payload": {"channel": "test", "data": []},
            "state": "new",
        })
        event.backend_id = False
        self.assertFalse(event.backend_id)
        with self.assertRaises(UserError):
            event.action_send_payload_to_automation()

    def test_only_one_liana_action_per_automation(self):
        """A base.automation may have at most one ir.actions.server in 'liana' state."""
        automation = self._create_automation()
        with self.assertRaises(ValidationError):
            self.env["ir.actions.server"].create({
                "name": "Second Liana action",
                "model_id": self.partner_model.id,
                "state": "liana",
                "usage": "base_automation",
                "base_automation_id": automation.id,
                "liana_channel_id": self.test_channel.id,
                "liana_event_verb": "subscribe",
            })

    def test_liana_action_server_count_compute(self):
        """liana_action_server_count counts only liana-state actions."""
        automation = self._create_automation()
        self.assertEqual(automation.liana_action_server_count, 1)

        self.env["ir.actions.server"].create({
            "name": "Non-liana sibling",
            "model_id": self.partner_model.id,
            "state": "code",
            "code": "model.search([], limit=1)",
            "usage": "base_automation",
            "base_automation_id": automation.id,
        })
        automation.invalidate_recordset(["liana_action_server_count"])
        self.assertEqual(automation.liana_action_server_count, 1)

    def test_action_channel_must_match_backend(self):
        """Picking a channel that belongs to another backend is rejected."""
        other_backend = self.env["liana.backend"].create({
            "name": "Other backend",
            "liana_automation_address": "https://other.example.test",
            "liana_automation_secret": "other-secret",
            "liana_automation_user": "other-user",
            "liana_automation_realm": "OtherRealm",
        })
        other_channel = self.env["liana.channel"].create({
            "name": "Other channel",
            "channel_id": 77,
            "system_name": "other-channel",
            "backend_id": other_backend.id,
        })
        with self.assertRaises(ValidationError):
            self.env["ir.actions.server"].create({
                "name": "Mismatched channel",
                "model_id": self.partner_model.id,
                "state": "liana",
                "liana_backend_id": self.backend.id,
                "liana_channel_id": other_channel.id,
                "liana_event_verb": "subscribe",
            })
