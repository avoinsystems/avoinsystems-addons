from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestPosMarketpayJS(HttpCase):
    """Run the Market Pay QUnit modules on /pos/ui/tests.

    The filter matches the QUnit module names in static/tests/unit. The page
    needs an opened session because the controller reads it for the test user.
    """

    def test_pos_marketpay_qunit(self):
        env = self.env(user=self.env.ref("base.user_admin"))
        config = env["pos.config"].create({"name": "Market Pay JS"})
        config.open_ui()
        config.current_session_id.set_cashbox_pos(0, None)

        self.browser_js(
            "/pos/ui/tests?filter=pos_marketpay",
            "",
            "",
            login="admin",
            timeout=300,
        )
