# Copyright 2026 Akretion (https://www.akretion.com).
# @author Benoît Guillot <benoit.guillot@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Account Payment Validation",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Two-step approval of the vendor bill payments by third-party approvers",
    "author": "Akretion, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/account-payment",
    "depends": ["account"],
    "data": [
        "security/payment_validation_security.xml",
        "security/ir.model.access.csv",
        "data/mail_template.xml",
        "views/account_move_views.xml",
        "views/account_move_line_views.xml",
        "views/res_partner_views.xml",
    ],
    "installable": True,
    "application": False,
}
