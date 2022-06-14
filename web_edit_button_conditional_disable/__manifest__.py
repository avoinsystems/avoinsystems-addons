# Copyright 2016 Camptocamp SA, Avoin.Systems
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Web Conditionally Disable Editing",
    "summary": "Allow other modules to disable the edit button conditionally",
    "version": "15.0.1.0.0",
    "author": "Camptocamp, Onestein, Avoin.Systems, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "category": "Web",
    "depends": [
        "web",
    ],
    "assets": {
        "web.assets_backend": [
            "web_edit_button_conditional_disable/static/src/js/form_controller.js",
        ]
    },
    "installable": True,
    # Does currently the same thingas web_access_rule_buttons, but based on a different logic.
    # There is no built-in compatibility (at least yet), so the two modules would potentially
    # undo each other's changes to the form.
    "excludes": [
        "web_access_rule_buttons",  # OCA/web
    ],
}
