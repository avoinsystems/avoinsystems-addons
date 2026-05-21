{
    "name": "Liana Connector",
    "version": "19.0.1.0.0",
    "category": "Marketing",
    "author": "Liana Technologies & Avoin.Systems",
    "license": "Other proprietary",
    "website": "https://avoin.systems",
    "depends": [
        "base_automation",
        "crm",
        "sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/ir_actions_server_views.xml",
        "views/liana_backend_views.xml",
        "views/liana_event_views.xml",
        "views/liana_automation_views.xml",
        "views/liana_dashboard_views.xml",
        "views/crm_lead_views.xml",
        "views/res_partner_views.xml",
        "views/menus.xml",
        "data/default_automations.xml",
    ],
    "images": [
        "static/description/banner.png",
    ],
    "application": True,
    "installable": True,
    "auto_install": False  # Don't install when all dependencies are satisfied
}
