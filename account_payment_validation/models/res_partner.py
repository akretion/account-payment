# Copyright 2026 Akretion (https://www.akretion.com).
# @author Benoît Guillot <benoit.guillot@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from .account_move import LEVEL1_GROUP, LEVEL2_GROUP


class ResPartner(models.Model):
    _inherit = "res.partner"

    payment_validation_level1_user_id = fields.Many2one(
        "res.users",
        string="Default Level 1 Approver",
        domain=lambda self: [("groups_id", "in", self.env.ref(LEVEL1_GROUP).ids)],
        help="Level 1 approver set by default on the vendor bills of this "
        "partner. It can be changed on each bill.",
    )
    payment_validation_level2_user_id = fields.Many2one(
        "res.users",
        string="Default Level 2 Approver",
        domain=lambda self: [("groups_id", "in", self.env.ref(LEVEL2_GROUP).ids)],
        help="Level 2 approver set by default on the vendor bills of this "
        "partner. It can be changed on each bill.",
    )
