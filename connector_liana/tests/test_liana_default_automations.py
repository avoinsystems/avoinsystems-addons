from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


CRM_ACTION_XMLID = "connector_liana.ir_actions_server_crm_lead_stage_changed"
CRM_RULE_XMLID = "connector_liana.base_automation_crm_lead_stage_changed"
SALE_ACTION_XMLID = "connector_liana.ir_actions_server_sale_order_state_changed"
SALE_RULE_XMLID = "connector_liana.base_automation_sale_order_state_changed"


@tagged("post_install", "-at_install")
class TestLianaDefaultAutomations(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.backend = cls.env["liana.backend"].create({
            "name": "Default-automations backend",
            "liana_automation_address": "https://automation.example.test",
            "liana_automation_secret": "secret",
            "liana_automation_user": "api-user",
            "liana_automation_realm": "TestRealm",
        })
        cls.channel = cls.env["liana.channel"].create({
            "name": "Default channel",
            "channel_id": 42,
            "system_name": "default",
            "backend_id": cls.backend.id,
        })

    def _crm_pair(self):
        return (
            self.env.ref(CRM_RULE_XMLID),
            self.env.ref(CRM_ACTION_XMLID),
        )

    def _sale_pair(self):
        return (
            self.env.ref(SALE_RULE_XMLID),
            self.env.ref(SALE_ACTION_XMLID),
        )

    def test_default_templates_exist_inactive_and_unconfigured(self):
        crm_rule, crm_action = self._crm_pair()
        sale_rule, sale_action = self._sale_pair()

        self.assertFalse(crm_rule.active)
        self.assertFalse(sale_rule.active)

        self.assertEqual(crm_action.state, "liana")
        self.assertEqual(crm_action.model_id.model, "crm.lead")
        self.assertEqual(crm_action.liana_event_verb, "lead_stage_changed")
        self.assertEqual(crm_rule.trigger, "on_create_or_write")
        self.assertEqual(crm_rule.trigger_field_ids.mapped("name"), ["stage_id"])
        self.assertFalse(crm_action.liana_backend_id)
        self.assertFalse(crm_action.liana_channel_id)
        self.assertEqual(
            set(crm_action.liana_event_item_ids.mapped("key")),
            {"name", "stage_id_name", "email_from", "expected_revenue"},
        )

        self.assertEqual(sale_action.state, "liana")
        self.assertEqual(sale_action.model_id.model, "sale.order")
        self.assertEqual(sale_action.liana_event_verb, "order_state_changed")
        self.assertEqual(sale_rule.trigger, "on_create_or_write")
        self.assertEqual(sale_rule.trigger_field_ids.mapped("name"), ["state"])
        self.assertEqual(sale_action.liana_identity_field_id.name, "partner_id")
        self.assertFalse(sale_action.liana_backend_id)
        self.assertFalse(sale_action.liana_channel_id)
        self.assertEqual(
            set(sale_action.liana_event_item_ids.mapped("key")),
            {
                "name",
                "state",
                "amount_total",
                "order_line_name",
                "order_line_product_uom_qty",
                "order_line_price_unit",
            },
        )

    def test_install_requires_default_channel(self):
        self.backend.liana_channel_id = False
        with self.assertRaises(UserError) as cm:
            self.backend.action_install_default_automations()
        self.assertIn("default Liana channel", str(cm.exception))

    def test_install_stamps_backend_and_channel_and_activates(self):
        self.backend.liana_channel_id = self.channel
        result = self.backend.action_install_default_automations()

        crm_rule, crm_action = self._crm_pair()
        sale_rule, sale_action = self._sale_pair()

        for action in (crm_action, sale_action):
            self.assertEqual(action.liana_backend_id, self.backend)
            self.assertEqual(action.liana_channel_id, self.channel)
        self.assertTrue(crm_rule.active)
        self.assertTrue(sale_rule.active)

        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["params"]["type"], "success")

    def test_install_is_idempotent(self):
        self.backend.liana_channel_id = self.channel
        self.backend.action_install_default_automations()
        crm_rule_first = self.env.ref(CRM_RULE_XMLID)
        crm_action_first = self.env.ref(CRM_ACTION_XMLID)

        self.backend.action_install_default_automations()
        crm_rule_second = self.env.ref(CRM_RULE_XMLID)
        crm_action_second = self.env.ref(CRM_ACTION_XMLID)

        self.assertEqual(crm_rule_first, crm_rule_second)
        self.assertEqual(crm_action_first, crm_action_second)
        self.assertTrue(crm_rule_second.active)
        self.assertEqual(crm_action_second.liana_backend_id, self.backend)
        self.assertEqual(crm_action_second.liana_channel_id, self.channel)
