# -*- coding: utf-8 -*-
# Copyright 2018 Akretion (Alexis de Lattre <alexis.delattre@akretion.com>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'E-invoice extension for Finland',
    'version': '10.0.1.0.0',
    'category': 'Localization',
    'license': 'AGPL-3',
    'summary': 'Add reference_number in XML e-invoices',
    'author': 'Akretion',
    'website': 'http://www.akretion.com',
    'depends': [
        'account_e-invoice_generate',
        'l10n_fi_invoice',
        ],
    'installable': True,
    'auto_install': True,
}
