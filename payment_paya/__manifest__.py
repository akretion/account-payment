# Copyright 2025 Chafique Delli <chafique.delli@akretion.com>
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    "name": "Payment Provider: PAYA ITS",
    "category": "Accounting/Payment Providers",
    "version": "16.0.1.0.0",
    "license": "LGPL-3",
    "summary": "Payment Provider: PAYA Implementation",
    "author": "Akretion, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/account-payment",
    "depends": ["account_payment", "base_iso3166"],
    "external_dependencies": {"python": ["requests", "dicttoxml", "xmltodict"]},
    "data": [
        "views/payment_provider_views.xml",
        "data/payment_provider_data.xml",
    ],
    "installable": True,
}
