{
    "name": "PoS - Market Pay",
    "summary": "Market Pay payment connector — elevate Odoo POS with integrated European-grade terminals",
    "version": "19.0.1.1.0",
    "license": "Other proprietary",
    "author": "Avoin.Systems",
    "category": "Sales/Point of Sale",
    "website": "https://market-pay.com/en/contact",
    "support": "https://market-pay.com/en/contact",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        "views/pos_payment_method.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_marketpay/static/**/*",
        ],
    },
    "images": [
        "static/description/banner.png",
    ],
    "installable": True,
    "application": False,
}
